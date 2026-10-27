"""shshd-runtime: an episode's opt-in to the translated games' presentation (resource 3) and the creator's options."""
from copy import deepcopy
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from exp_runtime.content import EpisodeResources, digest, presentation_feature
from exp_runtime.creator import Character, Node, Project, ProjectError, compile_project
from exp_runtime.creator.compiler import BUBBLE_KEY, DUET_KEYS, EMOTICON_KEY, compile_details
from exp_runtime.creator.model import EMOTICONS, project_from_record, project_record
from exp_runtime.creator.schema import node_schema
from exp_runtime.creator.workspace import Workspace
from exp_runtime.exp import ContentError, ExpArchive, encode_exp
from exp_runtime.presentation import MAGIC, RESOURCE, presentation_bytes, presentation_record
from exp_runtime.runtime import Session
from test_creator import image_bytes
from test_runtime import answer_screen

AUDIO = b'ID3' + bytes(64)


def with_resource_3(data, payload):
    archive = ExpArchive(data)
    entries = {key: archive.read(key) for key in archive.entries}
    entries[RESOURCE] = payload
    return encode_exp(entries)


def session(data, game='shs', pack_id=30000):
    """A session over an export, with the episode record and declaration the library's EpisodeResources gives."""
    archive = ExpArchive(data)
    resources = SimpleNamespace(library=SimpleNamespace(game_id=game, directory=Path('.')),
                                identity=dict(profile='authored', episode_sha256=digest(data)),
                                program=archive.programs().__getitem__, exists=lambda key: key in archive.entries,
                                record=dict(pack_id=pack_id), presentation=presentation_record(archive) or {})
    return Session(resources)


def cast():
    """A project with two reusable characters, each with a portrait (authored images)."""
    project = Project(title='Presentation', nodes=[Node('end', 'end')], start='end')
    alex, jo = project.add_image('Alex', image_bytes()), project.add_image('Jo', image_bytes())
    project.characters = [Character('alex', 'Alex', alex.id, 1), Character('jo', 'Jo', jo.id, 2)]
    return project


def line(project, *nodes):
    nodes = list(nodes)
    for left, right in zip(nodes, nodes[1:] + [project.node('end')]):
        left.next = right.id
    project.nodes[:0] = nodes
    project.start = nodes[0].id
    return project


class PresentationRecordTests(unittest.TestCase):
    def test_the_record_round_trips_and_rejects_what_it_does_not_know(self):
        data = presentation_bytes(dict(duet=[31310, 31311], narration_theme=31312,
                                       portrait_effects=dict(key=31410, images=[26000, None, None, 26005, None, None]),
                                       music_loops={26010: 26015}))
        self.assertTrue(data.startswith(MAGIC))
        archive = ExpArchive(encode_exp({1: b'meta', RESOURCE: data}))
        self.assertEqual(presentation_record(archive), dict(
            duet=(31310, 31311), narration_theme=31312,
            portrait_effects=(31410, (26000, None, None, 26005, None, None)), music_loops={26010: 26015}))
        self.assertIsNone(presentation_record(ExpArchive(encode_exp({1: b'meta'}))))
        self.assertIsNone(presentation_record(ExpArchive(encode_exp({1: b'meta', RESOURCE: b'\x89PNG'}))))
        for bad in (b'{"format":"shshd-presentation","version":2}',
                    b'{"format":"shshd-presentation","version":1,"sparkles":1}',
                    b'{"format":"shshd-presentation","version":1,"portrait_effects":{"key":1,"images":[1,2]}}',
                    b'{"format":"shshd-presentation","version":1,"duet":[1,-2]}', b'{'):
            with self.subTest(bad=bad), self.assertRaises(ContentError):
                presentation_record(ExpArchive(encode_exp({1: b'meta', RESOURCE: MAGIC + bad})))

    def test_a_malformed_record_is_set_aside_and_the_episode_plays(self):
        data = with_resource_3(compile_project(line(cast(), Node('a', text='Hi'))), MAGIC + b'{')
        resources = EpisodeResources(SimpleNamespace(game_id='shs'), dict(pack_id=30000, name='a.exp'),
                                     ExpArchive(data))
        with self.assertLogs(level='WARNING'):
            self.assertEqual(resources.presentation, {})
        self.assertIsNone(presentation_feature(resources, 'duet'))

    def test_the_translated_packs_keep_their_tables_and_other_episodes_use_their_own(self):
        declared = dict(duet=(1, 2), narration_theme=3, portrait_effects=(4, (5,) * 6), music_loops={6: 7})
        resources = SimpleNamespace(record=dict(pack_id=31300), library=SimpleNamespace(game_id='shs'),
                                    presentation=declared)
        self.assertEqual(presentation_feature(resources, 'duet'), (31310, 31311))       # the profile wins
        self.assertEqual(presentation_feature(resources, 'narration_theme'), 31312)
        self.assertEqual(presentation_feature(resources, 'portrait_effects'), (4, (5,) * 6))  # no 31300 entry
        resources.record = dict(pack_id=31400)
        self.assertEqual(presentation_feature(resources, 'portrait_effects'), (31410, tuple(range(26990, 26996))))
        self.assertEqual(presentation_feature(resources, 'music_loops'), {26900: 26901})
        resources.record = dict(pack_id=30000)
        for name, value in declared.items():
            self.assertEqual(presentation_feature(resources, name), value)
        resources.presentation = {}
        self.assertIsNone(presentation_feature(resources, 'duet'))
        resources.presentation, resources.library = declared, SimpleNamespace(game_id='cod')
        self.assertIsNone(presentation_feature(resources, 'duet'))                     # CoD has no opt-in

    @unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
    def test_the_desktop_chains_a_declared_intro_into_its_loop(self):
        from exp_runtime.desktop import Desktop
        resources = SimpleNamespace(record=dict(pack_id=30000), library=SimpleNamespace(game_id='shs'),
                                    presentation=dict(music_loops={26005: 26010}),
                                    read_asset=lambda resource: b'loop %d' % resource)
        desktop = SimpleNamespace(session=SimpleNamespace(resources=resources))
        self.assertEqual(Desktop._music_loop(desktop, 26005), b'loop 26010')
        self.assertIsNone(Desktop._music_loop(desktop, 26010))
        resources.presentation = {}
        self.assertIsNone(Desktop._music_loop(desktop, 26005))


class CreatorPresentationTests(unittest.TestCase):
    def test_a_second_speaker_joins_the_line_and_leaves_after_it(self):
        project = line(cast(), Node('a', character='alex', text='Both of us!',
                                    params=dict(partner='jo', partner_expression=2)), Node('b', text='Later.'))
        details = compile_details(project)
        jo = details.characters['jo']
        archive = ExpArchive(details.data)
        self.assertEqual(presentation_record(archive), dict(duet=DUET_KEYS))
        s = session(details.data)
        action = s.advance()
        self.assertEqual(action.details['text'], 'Both of us!')
        duet = s.dialogue_duet()
        self.assertEqual((duet.character_id, duet.expression), (jo, 2))
        self.assertEqual(duet.mode, 3 - action.details['presentation_mode'])
        answer_screen(s)
        self.assertEqual(s.engine.numbers[s.engine.number_key(0, DUET_KEYS[0])], 0)
        self.assertIsNone(s.dialogue_duet())
        # Without the declaration (another app's view of the same globals), the line has one speaker.
        bare = session(with_resource_3(details.data, b'not a record'))
        bare.advance()
        self.assertIsNone(bare.dialogue_duet())

    def test_a_named_line_takes_its_bubble_colour(self):
        project = line(cast(), Node('a', speaker='TV', text='Breaking news.', params=dict(bubble=3)),
                       Node('b', speaker='Radio', text='Static.'))
        data = compile_project(project)
        self.assertEqual(presentation_record(ExpArchive(data)), dict(narration_theme=BUBBLE_KEY))
        s = session(data)
        self.assertEqual(s.advance().details['presentation_mode'], 3)
        self.assertEqual(s.narration_theme(), 3)
        answer_screen(s)
        self.assertIsNone(s.narration_theme())

    def test_an_emoticon_shows_its_project_image_over_the_speaker(self):
        project = cast()
        heart = project.add_image('Heart', image_bytes())
        project.emoticons[3] = heart.id
        line(project, Node('a', character='jo', text='Aww.', params=dict(emoticon=4)), Node('b', character='jo', text='Ok.'))
        data = compile_project(project)
        self.assertEqual(presentation_record(ExpArchive(data)),
                         dict(portrait_effects=(EMOTICON_KEY, (None, None, None, heart.id, None, None))))
        s = session(data)
        s.advance()
        self.assertEqual(s.portrait_effect(), (4, heart.id))
        answer_screen(s)
        self.assertIsNone(s.portrait_effect())

    def test_music_names_the_loop_its_intro_runs_into(self):
        project = cast()
        intro, loop = project.add_audio('intro.mp3', AUDIO), project.add_audio('loop.mp3', AUDIO + b'\1')
        line(project, Node('m', 'music', params=dict(resource=intro.id, then_loop=loop.id)), Node('a', text='Hi'))
        data = compile_project(project)
        self.assertEqual(presentation_record(ExpArchive(data)), dict(music_loops={intro.id: loop.id}))
        s = session(data)
        s.advance()
        self.assertEqual(s.engine.music_id, intro.id)

    def test_an_episode_without_the_options_has_no_record(self):
        archive = ExpArchive(compile_project(line(cast(), Node('a', character='alex', text='Hi'))))
        self.assertNotIn(RESOURCE, archive.entries)

    def test_each_option_is_checked(self):
        def fails(project, message):
            with self.assertRaisesRegex(ProjectError, message):
                compile_project(project)
        fails(line(cast(), Node('a', text='Narration', params=dict(partner='jo'))), 'with a portrait')
        fails(line(cast(), Node('a', character='alex', text='Hi', params=dict(partner='alex'))), 'another character')
        fails(line(cast(), Node('a', character='alex', text='Hi', params=dict(partner='nobody'))), 'unknown second')
        fails(line(cast(), Node('a', character='alex', text='Hi', params=dict(partner='jo', partner_expression=5))),
              'expression 0 to 4')
        fails(line(cast(), Node('a', character='alex', text='Hi', params=dict(bubble=1))), 'without a portrait')
        fails(line(cast(), Node('a', speaker='TV', text='Hi', params=dict(bubble=4))), '1 \\(blue\\)')
        fails(line(cast(), Node('a', character='alex', text='Hi', params=dict(emoticon=2))), 'Sweat emoticon')
        fails(line(cast(), Node('a', text='Hi', params=dict(emoticon=1))), "speaker's portrait")
        cod = line(cast(), Node('a', character='alex', text='Hi', params=dict(partner='jo')))
        cod.game = 'cod'
        fails(cod, 'CoD has none')
        project = cast()
        intro = project.add_audio('intro.mp3', AUDIO)
        fails(line(deepcopy(project), Node('m', 'music', params=dict(resource=intro.id, then_loop=8201))),
              'embedded MP3 or WAV')
        fails(line(deepcopy(project), Node('m', 'music', params=dict(resource=intro.id, then_loop=intro.id))),
              'another track')
        loop = project.add_audio('loop.mp3', AUDIO)
        fails(line(deepcopy(project), Node('m', 'music', params=dict(resource=intro.id, then_loop=loop.id)),
                   Node('n', 'music', params=dict(resource=intro.id))), 'same way')
        project = cast()
        project.emoticons[0] = 29999
        fails(line(project, Node('a', text='Hi')), 'Lightning emoticon needs an imported image')

    def test_a_score_may_set_a_presentation_key_only_while_no_line_owns_it(self):
        # The X360 translation sets the emoticon number with score nodes of its own (tools/translate x360.py).
        score = Node('s', 'score', params=dict(owner=0, key=EMOTICON_KEY, operation='set', value=4))
        compile_project(line(cast(), deepcopy(score), Node('a', character='alex', text='Hi')))
        project = cast()
        project.emoticons[3] = project.assets[0].id
        with self.assertRaisesRegex(ProjectError, 'use another key'):
            compile_project(line(project, deepcopy(score), Node('a', character='alex', text='Hi',
                                                                params=dict(emoticon=4))))
        flag = Node('f', 'flag', params=dict(owner=0, key=DUET_KEYS[0], bit=1, value=True))
        with self.assertRaisesRegex(ProjectError, 'use another key'):
            compile_project(line(cast(), flag, Node('a', character='alex', text='Hi', params=dict(partner='jo'))))

    def test_projects_upgrade_to_version_3_and_keep_their_emoticons(self):
        project = cast()
        record = project_record(project)
        self.assertEqual((record['version'], record['emoticons']), (3, [None] * len(EMOTICONS)))
        old = dict(record, version=2)
        del old['emoticons']
        self.assertEqual(project_from_record(old).emoticons, [None] * 6)
        project.emoticons[5] = project.assets[0].id
        self.assertEqual(project_from_record(project_record(project)).emoticons[5], project.assets[0].id)
        bad = dict(project_record(project), emoticons=[None] * 5)
        with self.assertRaisesRegex(ProjectError, 'six|6'):
            project_from_record(bad)

    def test_the_schema_and_workspace_expose_the_options(self):
        dialogue = node_schema('dialogue')
        params = dialogue['schema']['properties']['params']['properties']
        self.assertEqual((params['emoticon']['minimum'], params['emoticon']['maximum']), (0, 6))
        self.assertEqual(params['bubble']['maximum'], 3)
        self.assertIn('partner', params)
        self.assertIn('emoticons', dialogue['notes'])
        self.assertEqual(node_schema('music')['schema']['properties']['params']['properties']['then_loop']['minimum'], -1)
        with tempfile.TemporaryDirectory() as directory:
            w = Workspace(directory)
            first = w.create('story.expproj')
            (Path(directory) / 'heart.png').write_bytes(image_bytes())
            second = w.import_image('story.expproj', first['revision'], 'heart.png')
            image = w.describe('story.expproj')['assets'][0]['id']
            third = w.update('story.expproj', second['revision'], {'emoticons': [None, None, None, image, None, None]})
            self.assertEqual(w.describe('story.expproj')['emoticons'][3], image)
            w.node('story.expproj', third['revision'], 'start', {'speaker': 'TV', 'params': {'bubble': 2}})


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'Install the creator extra to test the optional Qt editor')
class CreatorPresentationUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_the_inspector_offers_each_option_where_it_applies(self):
        from PySide6.QtWidgets import QComboBox, QLabel
        from exp_runtime.creator.ui import Editor
        editor = Editor(discover_library=False)
        try:
            editor.project = cast()
            editor.project.nodes.insert(0, Node('start', text='Hello', next='end'))
            editor.project.start = editor.selected = 'start'
            editor.refresh()

            def row(label):
                form = editor.inspector.widget().layout()
                for i in range(form.rowCount()):
                    item = form.itemAt(i, form.ItemRole.LabelRole)
                    if item is not None and isinstance(item.widget(), QLabel) and item.widget().text() == label:
                        return form.itemAt(i, form.ItemRole.FieldRole).widget()
                return None
            editor.show_properties()
            self.assertFalse(row('Second speaker').isEnabled())       # narration: no portrait
            self.assertTrue(row('Bubble color').isEnabled())
            editor.set_node('character', 'alex')
            self.assertTrue(row('Second speaker').isEnabled())
            self.assertFalse(row('Bubble color').isEnabled())
            partner = row('Second speaker')
            partner.setCurrentIndex(partner.findData('jo'))
            self.assertEqual(editor.project.node('start').params['partner'], 'jo')
            self.assertTrue(row('Their expression').isEnabled())
            self.assertIn('(no image yet)', row('Emoticon').itemText(1))
            editor.set_project('emoticons', [editor.project.assets[0].id] + [None] * 5)
            editor.show_properties()
            emoticon = row('Emoticon')
            self.assertEqual(emoticon.itemText(1), 'Lightning')
            emoticon.setCurrentIndex(emoticon.findData(1))
            self.assertTrue(compile_project(editor.project))
            editor.add_node('music')
            self.assertIsInstance(row('Then loop'), QComboBox)
            editor.project.game = 'cod'
            editor.show_properties()
            self.assertIsNone(row('Then loop'))
        finally:
            editor.dirty = False
            editor.close()


if __name__ == '__main__':
    unittest.main()
