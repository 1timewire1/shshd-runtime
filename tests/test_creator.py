"""Authored projects must survive native export, import and actual VM execution."""
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image
from exp_runtime.creator import (Asset, Choice, Node, Project, ProjectError, compile_project,
                                  export_project, export_native_slot, load_project, save_project)
from exp_runtime.creator.compiler import _Assembler
from exp_runtime.creator.assets import import_library_image
from exp_runtime.creator.preview import preview_resources
from exp_runtime.content import ContentLibrary, digest, import_game
from exp_runtime.exp import ExpArchive
from exp_runtime.runtime import Session
from test_content import FAKE_NATIVE, make_apk
from test_runtime import answer_screen


def image_bytes():
    output = BytesIO()
    Image.new('RGBA', (32, 48), (90, 160, 70, 255)).save(output, format='PNG')
    return output.getvalue()


def story(game='shs'):
    return Project(title='An authored fork', game=game, start='ask', nodes=[
        Node('end', 'end'),  # Physical order does not determine entry or control flow.
        Node('bad', text='We stayed.', next='end'),
        Node('good', text='We explored.', speaker='Alex', next='end'),
        Node('test', 'branch', variable='curiosity', value=7, next='good', otherwise='bad'),
        Node('set', 'set', variable='curiosity', value=7, next='test'),
        Node('ask', 'choice', text='Which way?', timeout_ms=900, timeout_option=1,
             options=[Choice('Explore | together', 'set'), Choice('Stay', 'test'), Choice('Skip', 'end')]),
    ])


def session_for(project):
    data = compile_project(project)
    archive = ExpArchive(data)
    resources = SimpleNamespace(library=SimpleNamespace(game_id=project.game, directory=Path('.')),
        identity=dict(profile='authored', episode_sha256=digest(data)),
        program=archive.programs().__getitem__, exists=lambda key: key in archive.entries)
    return Session(resources)


class CreatorTests(unittest.TestCase):
    def test_each_choice_branches_in_both_games_and_timer_survives_save(self):
        for game in ('shs', 'cod'):
            for answer, expected in ((0, 'We explored.'), (1, 'We stayed.'), (2, None)):
                with self.subTest(game=game, answer=answer):
                    session = session_for(story(game))
                    first = session.advance()
                    self.assertEqual(first.name, 'choice')
                    self.assertEqual(first.details['options'][0], 'Explore | together')
                    result = session.answer(answer)
                    if expected is None:
                        self.assertEqual(result.name, 'episode_exit')
                    else:
                        self.assertEqual(result.details['text'], expected)
                        self.assertEqual(answer_screen(session).name, 'episode_exit')
            session = session_for(story(game))
            session.advance()
            session.tick(300)
            restored = Session.from_snapshot(session.resources, session.snapshot())
            self.assertEqual(restored.remaining_ms, 600)
            self.assertEqual(restored.tick(601).details['text'], 'We stayed.')

    def test_comparisons_signed_values_defaults_and_backward_links(self):
        for op, value, expected in (('==', 0, True), ('!=', 0, False), ('<', 1, True),
                                    ('<=', 0, True), ('>', -1, True), ('>=', 1, False)):
            project = story()
            project.start = 'test'
            project.node('test').operator = op
            project.node('test').value = value
            session = session_for(project)
            self.assertEqual(session.advance().details['text'], 'We explored.' if expected else 'We stayed.')
        project = story()
        project.node('good').next = 'ask'  # Legal loop through a player input gate.
        session = session_for(project)
        session.advance()
        for _ in range(5):
            self.assertEqual(session.answer(0).details['text'], 'We explored.')
            self.assertEqual(answer_screen(session).name, 'choice')

    def test_custom_portrait_background_and_metadata_keep_exact_resources(self):
        project = Project(title='Authored café', start='background')
        portrait = project.add_image('Alex', image_bytes())
        background = project.add_image('Place', image_bytes())
        project.nodes.insert(0, Node('background', 'background', asset=background.id, next='start'))
        node = project.node('start')
        node.speaker, node.portrait, node.theme = 'Alex', portrait.id, 2
        data = compile_project(project)
        archive = ExpArchive(data)
        self.assertEqual(archive.metadata().title, project.title)
        self.assertEqual(archive.read(portrait.id), image_bytes())
        session = session_for(project)
        action = session.advance()
        self.assertEqual(action.details['speaker'], 'Alex')
        self.assertEqual(action.details['theme'], 2)
        self.assertEqual(session.engine.panel.background_id, background.id)
        self.assertEqual(session.engine.character_art_variants[1], [portrait.id] * 5)
        self.assertEqual(session.engine.character_art_variants[0], [-1] * 5)

    def test_native_limits_and_narrator_slot_are_enforced(self):
        project = Project()
        session = session_for(project)
        action = session.advance()
        self.assertEqual(action.details['character_id'], 0)
        self.assertEqual(action.details['presentation_mode'], 4)
        for key in ('pack_id', 'episode_id'):
            bad = deepcopy(project)
            setattr(bad, key, 32768)
            with self.assertRaises(ProjectError):
                compile_project(bad)
        image = project.add_image('Portrait', image_bytes())
        project.nodes.extend(Node(f'person{i}', speaker=f'Person {i}', text='Hi',
                                  portrait=image.id, next='end') for i in range(200))
        with self.assertRaisesRegex(ProjectError, '199 portrait'):
            compile_project(project)
        asm = _Assembler()
        asm.code = [(0x33, None)] * 32768
        with self.assertRaisesRegex(ProjectError, 'native single-script'):
            asm.finish()

    def test_variables_use_initialized_vm_memory_without_global_property_collisions(self):
        session = session_for(story())
        session.engine.numbers[session.engine.number_key(0, -10000)] = 77
        session.advance()
        self.assertEqual(session.answer(0).details['text'], 'We explored.')
        self.assertEqual(session.engine.numbers[session.engine.number_key(0, -10000)], 77)
        saved = Session.from_snapshot(session.resources, session.snapshot())
        self.assertEqual(saved.vm.data, session.vm.data)
        self.assertEqual(saved.vm.data[0], 7)

    def test_native_slot_export_keeps_catalog_ids_but_never_replaces_reference(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference, output = root / 'installed.exp', root / 'replacement.exp'
            original = Project(title='Existing native slot', pack_id=101, episode_id=7)
            export_project(original, reference)
            before = reference.read_bytes()
            authored = story('cod')
            metadata = export_native_slot(authored, reference, output)
            exported = ExpArchive(output.read_bytes())
            self.assertEqual((exported.metadata().pack_id, exported.metadata().episode_id), (101, 7))
            self.assertEqual(metadata.title, 'Existing native slot')
            self.assertEqual(exported.metadata().title, authored.title)
            self.assertEqual(reference.read_bytes(), before)
            self.assertEqual(authored.pack_id, 30000)
            with self.assertRaisesRegex(ProjectError, 'separate replacement'):
                export_native_slot(authored, reference, reference)
            self.assertEqual(reference.read_bytes(), before)

    def test_projects_and_export_survive_relocation_without_source_image(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            project = story()
            project.add_image('Author image', image_bytes())
            project.library = str(root / 'original' / 'game-library')
            (root / 'original').mkdir()
            path = root / 'original' / 'story.expproj'
            save_project(project, path)
            self.assertEqual(json.loads(path.read_text())['library'], 'game-library')
            moved = root / 'moved'
            shutil.move(root / 'original', moved)
            restored = load_project(moved / path.name)
            self.assertEqual(restored.library, str(moved / 'game-library'))
            self.assertEqual(restored.assets[0].data, image_bytes())
            export_project(restored, moved / 'episode.exp')
            self.assertEqual((moved / 'episode.exp').read_bytes(), compile_project(project))

    def test_incomplete_projects_can_save_but_bad_graphs_cannot_replace_exports(self):
        cases = []
        project = story()
        project.node('ask').options[0].target = 'missing'
        cases.append(project)
        project = story()
        project.node('set').next = 'set'
        cases.append(project)
        project = story()
        project.node('good').text = 'Unsupported emoji: 🙂'
        cases.append(project)
        project = story()
        project.node('ask').timeout_option = 7
        cases.append(project)
        project = story()
        project.node('good').portrait = 42
        cases.append(project)
        project = story()
        project.nodes.append(deepcopy(project.nodes[0]))
        cases.append(project)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'keep.exp'
            output.write_bytes(b'previous export')
            for project in cases:
                with self.assertRaises(ProjectError):
                    export_project(project, output)
                self.assertEqual(output.read_bytes(), b'previous export')
            save_project(cases[0], Path(temporary) / 'unfinished.expproj')
            self.assertEqual(load_project(Path(temporary) / 'unfinished.expproj'), cases[0])

    def test_malformed_projects_rejected_before_any_external_file_access(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'episode.expproj'
            project = story()
            project.add_image('Image', image_bytes())
            save_project(project, path)
            original = json.loads(path.read_text())
            for change in (lambda d: d.update(version=99), lambda d: d.update(extra='not supported'),
                           lambda d: d['nodes'][0].update(kind='execute'),
                           lambda d: d['nodes'][0].update(x=float('nan')),
                           lambda d: d['assets'][0].update(data='../not-base64'),
                           lambda d: d['assets'][0].update(id=42),
                           lambda d: d['nodes'][0].update(options=None)):
                data = deepcopy(original)
                change(data)
                path.write_text(json.dumps(data))
                with self.assertRaises(ProjectError):
                    load_project(path)

    def test_export_import_and_preview_do_not_modify_the_original_library(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'game.apk'
            make_apk(source, compile_project(Project()))
            with patch('exp_runtime.shs.content.NATIVE_SHA256', digest(FAKE_NATIVE)):
                library_path = root / 'library'
                import_game(source, [], library_path)
                export = root / 'created.exp'
                export_project(story(), export)
                with ContentLibrary(library_path) as library:
                    self.assertEqual(library.add_episodes([export]), 1)
                    self.assertEqual(library.add_episodes([export]), 0)
                    resources = library.open_episode('An authored fork')
                    self.assertEqual(resources.program(25001).to_bytes(),
                                     ExpArchive(export.read_bytes()).read(25001))
                before = {p.relative_to(library_path): p.read_bytes() for p in library_path.rglob('*') if p.is_file()}
                with preview_resources(export.read_bytes(), library_path, 'shs') as resources:
                    session = Session(resources)
                    self.assertEqual(session.advance().name, 'choice')
                    saved = session.save(session.save_path)
                    self.assertTrue(saved.exists())
                    self.assertNotEqual(resources.library.directory, library_path)
                self.assertFalse(saved.exists())
                after = {p.relative_to(library_path): p.read_bytes() for p in library_path.rglob('*') if p.is_file()}
                self.assertEqual(before, after)
                with self.assertRaisesRegex(ProjectError, 'does not match'):
                    with preview_resources(export.read_bytes(), library_path, 'cod'):
                        self.fail('Mismatched profile accepted')

    def test_library_base_references_and_episode_copies_stay_in_their_banks(self):
        png = image_bytes()
        library = SimpleNamespace(game_id='cod', read_asset=lambda key: png)
        episode = SimpleNamespace(read_asset=lambda key: png)
        project = Project(game='cod')
        base = import_library_image(project, library, 42)
        self.assertIs(import_library_image(project, library, 42), base)
        self.assertIsNone(base.data)
        first = import_library_image(project, library, 26010, episode)
        second = import_library_image(project, library, 26010, episode)
        self.assertEqual(second.id - first.id, 5)
        archive = ExpArchive(compile_project(project))
        self.assertNotIn(42, archive.entries)
        self.assertEqual(archive.read(first.id), png)
        with self.assertRaisesRegex(ProjectError, 'match'):
            import_library_image(Project(), library, 42)


if __name__ == '__main__':
    unittest.main()
