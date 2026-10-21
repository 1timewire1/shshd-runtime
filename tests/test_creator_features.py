"""Execute authored features through the same engine used by desktop and iOS."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from exp_runtime.creator import Character, Choice, Node, Project, ProjectError, compile_project
from exp_runtime.creator.compiler import compile_details
from exp_runtime.creator.debugger import DebugSession
from exp_runtime.creator.editing import Recovery, auto_layout, copy_nodes, paste_nodes
from exp_runtime.creator.features import parameters
from exp_runtime.creator.model import project_from_record, project_record
from exp_runtime.creator.native import import_exp, set_data_words
from exp_runtime.exp import ExpArchive, encode_exp
from test_creator import image_bytes, session_for
from test_runtime import answer_screen


def sequence(*nodes, game='shs'):
    nodes = list(nodes) + [Node('end', 'end')]
    for left, right in zip(nodes, nodes[1:]):
        if not left.next: left.next = right.id
    return Project(game=game, start=nodes[0].id, nodes=nodes)


class CreatorFeatureTests(unittest.TestCase):
    def test_arithmetic_short_circuit_conditions_and_scene_variables(self):
        for shared in (False, True):
            p = sequence(Node('a', 'set', variable='points', params={'expression': '2 + 3 * 4'}),
                Node('b', 'set', variable='points', params={'expression': 'points - 4'}),
                Node('c', 'choice', text='Choose', options=[Choice('Ready', 'yes', 'points == 10'),
                                                          Choice('Wait', 'end', 'points < 10')]),
                Node('yes', text='Ready'), Node('test', 'branch', params={'expression': 'zero != 0 and 5 // zero > 1'},
                     next='wrong', otherwise='end'), Node('wrong', text='Wrong'))
            if shared:
                for node in p.nodes[1:]: node.scene = 25002
            session = session_for(p)
            action = session.advance()
            self.assertEqual(action.details['enabled'], [True, False])
            self.assertEqual(answer_screen(session, 0).details['text'], 'Ready')
            self.assertEqual(answer_screen(session).name, 'episode_exit')

    def test_text_input_answer_comparison_substitutions_and_translations(self):
        p = sequence(Node('input', 'input', params={'result': 'name', 'prompt': 'Your name?'}),
                     Node('check', 'text_branch', params={'variable': 'name', 'equals': 'Alex'},
                          next='hello', otherwise='end'), Node('hello', text='Hello, {name}!'))
        p.language = 'fr'; p.locales = {'fr': {'title': 'Une histoire', 'node.hello.text': 'Bonjour, {name}!'}}
        s = session_for(p)
        self.assertEqual(s.advance().name, 'text_input')
        self.assertEqual(s.answer('Alex').details['text'], 'Bonjour, Alex!')
        self.assertEqual(ExpArchive(compile_project(p)).metadata().titles[1], 'Une histoire')

    def test_audio_native_properties_and_character_expression_banks(self):
        p = sequence(Node('music', 'music', params={'loop': True}), Node('sfx', 'sound'),
                     Node('score', 'score', params={'owner': 12, 'key': 81, 'value': 9}),
                     Node('rel', 'relationship', character='alex', params={'value': 2}),
                     Node('talk', character='alex', expression=3, text='Hello'), Node('stop', 'stop_audio'))
        image = p.add_image('Alex', image_bytes())
        p.characters = [Character('alex', 'Alex', image.id, 1, [image.id] * 5)]
        s = session_for(p); action = s.advance()
        self.assertEqual(action.details['speaker'], 'Alex')
        self.assertEqual(action.details['expression'], 3)
        self.assertEqual(s.engine.music_id, 8201)
        self.assertTrue(s.engine.music_flag)
        self.assertEqual(s.engine.numbers[s.engine.number_key(12, 81)], 9)
        self.assertEqual(s.engine.numbers[s.engine.number_key(1, 407)], 2)
        self.assertEqual(len(set(s.engine.character_art_variants[1])), 5)
        answer_screen(s)
        self.assertEqual(s.engine.music_id, -1)

    def test_minigames_parse_native_tables_and_return_results(self):
        for kind, action in (('word_game', 'word_game'), ('football', 'football'), ('grid', 'word_grid')):
            p = sequence(Node('game', kind, text='Play'), Node('result', text='Done'))
            s = session_for(p)
            with self.subTest(kind=kind):
                self.assertEqual(s.advance().name, action)
                # Clock expiry uses real game state; no synthetic return is injected.
                for _ in range(1000):
                    if s.pending.name not in ('word_game', 'word_grid', 'football'): break
                    s.tick(1000)
                    if s.pending.name == 'football': s.answer(None)
                    elif s.pending.name == 'word_grid': s.answer()
                self.assertEqual(s.pending.name, 'dialogue')
                result = parameters(p.nodes[0])['result']
                address = compile_details(p).variables[result]
                self.assertIsInstance(s.vm.data[address], int)
        for kind in ('football', 'grid'):
            with self.assertRaisesRegex(ProjectError, 'CoD'):
                compile_project(sequence(Node('game', kind), game='cod'))

    def test_authored_roundtrip_and_native_blocks_preserve_all_resources(self):
        p = sequence(Node('music', 'music'), Node('talk', text='Hello'))
        p.add_image('Portrait', image_bytes())
        data = compile_project(p)
        self.assertEqual(compile_project(import_exp(data)), data)
        archive = ExpArchive(data)
        original = {key: archive.read(key) for key in archive.entries if key != 2}
        original[12345] = b'unknown retained data'
        q = import_exp(encode_exp(original))
        rebuilt = ExpArchive(compile_project(q))
        self.assertEqual({key: rebuilt.read(key) for key in rebuilt.entries}, original)
        # Editing one literal changes only its original instruction.
        node = next(n for n in q.nodes if any(row == [0x1a, 8201] for row in n.params['instructions']))
        next(row for row in node.params['instructions'] if row == [0x1a, 8201])[1] = 8203
        self.assertEqual(session_for(q).advance().name, 'dialogue')
        node.params['instructions'].pop()
        with self.assertRaisesRegex(ProjectError, 'every instruction'): compile_project(q)

    def test_large_native_graph_has_bounded_positions_and_text_edits_preserve_addresses(self):
        from exp_runtime.creator.compiler import _Assembler
        from exp_runtime.creator.native import packed_strings, edit_packed_text
        from exp_runtime.exp import Metadata
        asm = _Assembler(); address = asm.text('Original dialogue')
        for _ in range(5000): asm.call(250)  # Unknown native services must remain explicit.
        asm.emit(0x33)
        original = encode_exp({1: Metadata(30000, 1, ('Test',) * 5).to_bytes(), 25001: asm.finish()})
        project = import_exp(original)
        self.assertEqual(len(project.nodes), 5001)
        self.assertLess(max(abs(n.x) + abs(n.y) for n in project.nodes), 100000)
        self.assertEqual(packed_strings(project, 25001)[0]['address'], address)
        edit_packed_text(project, 25001, address, 'Edited dialogue')
        program = ExpArchive(compile_project(project)).programs()[25001]
        self.assertEqual(len(program.instructions), 5001)
        self.assertEqual(packed_strings(project, 25001)[0]['text'], 'Edited dialogue')
        with self.assertRaisesRegex(ProjectError, 'allocation'):
            edit_packed_text(project, 25001, address, 'This replacement is much too long')

    def test_debugger_steps_breakpoints_and_mutable_variables(self):
        p = sequence(Node('set', 'set', variable='points', value=3), Node('talk', text='Hi'),
                     Node('branch', 'branch', variable='points', value=8, next='yes', otherwise='end'),
                     Node('yes', text='Pass'))
        d = DebugSession(p)
        self.assertEqual(d.state()['node'], 'set')
        self.assertEqual(d.resume(step=True)['node'], 'talk')
        self.assertEqual(d.state()['variables']['points'], 3)
        d.set_variable('points', 8)
        self.assertEqual(d.resume()['action'], 'dialogue')
        d.resume(provide_answer=True); d.resume(milliseconds=2000)
        d.breakpoints = {'branch'}
        self.assertEqual(d.resume(provide_answer=True)['node'], 'branch')
        self.assertEqual(d.resume()['details']['text'], 'Pass')

    def test_recovery_v1_migration_clipboard_and_layout(self):
        p = Project(); record = project_record(p)
        record['version'] = 1
        for key in ('characters', 'locales', 'language', 'native'): record.pop(key)
        for node in record['nodes']:
            for key in ('scene', 'character', 'expression', 'params'): node.pop(key)
        self.assertEqual(project_from_record(record), p)
        with tempfile.TemporaryDirectory() as directory:
            recovery = Recovery(directory); recovery.write(p)
            self.assertEqual(Recovery.read(recovery.path)[0], p)
            recovery.remove(); self.assertFalse(recovery.path.exists())
        ids = paste_nodes(p, copy_nodes(p, {'start', 'end'}))
        self.assertEqual(p.node(ids[0]).next, ids[1])
        auto_layout(p)
        self.assertEqual(len({(n.x, n.y) for n in p.nodes}), 4)
        before = deepcopy(p)
        with self.assertRaises(ProjectError): paste_nodes(p, '{bad')
        self.assertEqual(p, before)


class CreatorEndingTests(unittest.TestCase):
    def test_unreleased_links_keep_closing_text_and_use_native_exit_after_migration(self):
        from exp_runtime.authored import MAGIC, RESOURCE, authoring_record
        from exp_runtime.exp import Metadata
        from test_vm import program
        for closing in ('', 'Thanks for playing.'):
            p = Project(start='next', nodes=[Node('next', 'end', text=closing), Node('next_end', 'end')])
            p.language = 'fr'
            p.locales = {'fr': {'node.next.text': 'Merci.', 'node.next.param.title': 'Fin'}}
            record = project_record(p)
            record['nodes'][0].update(kind='episode_link', params={'pack_id': 30000, 'episode_id': 2, 'title': 'The end'})
            original = deepcopy(record)
            migrated = project_from_record(record)
            self.assertEqual(record, original)
            self.assertEqual(migrated.node('next_end').kind, 'end')
            self.assertFalse(any(n.kind == 'episode_link' for n in migrated.nodes))
            s = session_for(migrated)
            if closing:
                self.assertEqual(migrated.node('next').kind, 'message')
                self.assertEqual(migrated.node('next').next, 'next_end_1')
                self.assertEqual(s.advance().name, 'message_panel')
                self.assertEqual(s.engine.message_panel.text, 'Merci.')
                self.assertEqual(s.engine.message_panel.title, 'Fin')
                s.tick(1000)
                self.assertEqual(s.answer().name, 'episode_exit')
            else:
                self.assertEqual(migrated.node('next').kind, 'end')
                self.assertEqual(s.advance().name, 'episode_exit')
            self.assertEqual(s.pending.request.yield_id, 7)
            self.assertNotIn('links', authoring_record(ExpArchive(compile_project(migrated))))
            # The same migration handles older authored EXP imports.
            old_exp = encode_exp({1: Metadata(30000, 1, ('Old export',) * 5).to_bytes(),
                25001: program((0x1f, 0x0700), 0x33).to_bytes(),
                RESOURCE: MAGIC + json.dumps(dict(format='exp-runtime-authored', version=1,
                                                  project=record, links=[])).encode()})
            self.assertEqual(import_exp(old_exp), migrated)

    def test_creator_end_reuses_the_existing_menu_and_episode_picker_for_both_games(self):
        import os
        from unittest.mock import patch
        from exp_runtime.application import Application
        from exp_runtime.authored import authoring_record, MAGIC, RESOURCE
        from exp_runtime.content import ContentLibrary, import_game, digest
        from exp_runtime.menu import MenuState
        from test_content import make_apk, FAKE_NATIVE
        from test_games import make_cod_ipa
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        with tempfile.TemporaryDirectory() as directory, patch('exp_runtime.shs.content.NATIVE_SHA256', digest(FAKE_NATIVE)):
            root = Path(directory)
            for game, make, suffix in (('shs', make_apk, '.apk'), ('cod', make_cod_ipa, '.ipa')):
                with self.subTest(game=game):
                    first = Project(game=game, start='end', nodes=[Node('end', 'end')])
                    second = Project(game=game, title='Next story', episode_id=2)
                    from test_vm import program
                    second_archive = ExpArchive(compile_project(second))
                    second_resources = {key: second_archive.read(key) for key in second_archive.entries}
                    second_resources[25001] = program(0x32, 0x33).to_bytes()
                    episode = root / f'{game}.exp'; episode.write_bytes(encode_exp(second_resources))
                    first_archive = ExpArchive(compile_project(first))
                    first_resources = {key: first_archive.read(key) for key in first_archive.entries}
                    metadata = authoring_record(first_archive)
                    self.assertNotIn('links', metadata)
                    # An old export's routing metadata must not intercept the native exit.
                    metadata['links'] = [dict(script=25001, pc=compile_details(first).locations[25001]['end'],
                                              pack_id=30000, episode_id=2)]
                    first_resources[RESOURCE] = MAGIC + json.dumps(metadata).encode()
                    package = root / (game + suffix); make(package, encode_exp(first_resources))
                    import_game(package, [episode], root / game, game=game)
                    with ContentLibrary(root / game) as library:
                        app = Application(root / 'empty', game_key=game, audio=False, check_updates=False)
                        try:
                            app.library, app.directory = library, library.directory
                            app.state = MenuState(library)
                            source = next(r for r in library.episodes if r['episode_id'] == 1)
                            target = next(r for r in library.episodes if r['episode_id'] == 2)
                            app.selected = source['id']; app.start(resume=False)
                            self.assertEqual(app.screen, 'main')
                            self.assertEqual(app.selected, source['id'])
                            self.assertEqual(app.message, '')
                            self.assertFalse(app.can_resume())
                            app.command(('episodes', 'all'))
                            self.assertEqual(app.screen, 'episodes')
                            app.tick(1550)
                            app.command(('episode', target['id']))
                            app.command(('start', False))
                            if getattr(app, 'game_entry', None) is not None:   # (no menu-to-story fade here)
                                app.tick(1500)
                            self.assertEqual(app.game.session.resources.record['id'], target['id'])
                            self.assertEqual(app.game.session.pending.name, 'vm_pause')
                        finally: app.close()


if __name__ == '__main__':
    unittest.main()
