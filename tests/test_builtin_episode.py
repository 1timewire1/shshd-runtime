import json
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from exp_runtime.shs.builtin_episode import FOOTBALL_SCRIPTS, extract_football
from exp_runtime.content import ContentError, ContentLibrary, ExpArchive, digest, import_game, is_bundled
from exp_runtime.randomness import NativeRandom
from exp_runtime.runtime import Session
from test_content import FAKE_NATIVE, archive, make_apk, metadata
from test_runtime import answer_screen
from test_vm import program


def add_base_story(apk_path, *, broken=None):
    # An authored string bank using the native offsets, not copied game text.
    strings = [''] * 198
    strings[193:198] = ['Authored base story', 'Épisode', 'Storia', 'Geschichte', 'Historia']
    head = 9 + 2 * len(strings)
    offsets, body = [], bytearray()
    for text in strings:
        offsets.append(head + len(body))
        body += text.encode('latin-1') + b'\0'
    bank = struct.pack('>iBhh', 1, 0, 0, len(strings)) + struct.pack(f'>{len(offsets)}h', *offsets) + body
    with ZipFile(apk_path, 'a') as apk:
        apk.writestr('assets/Assets/13', bank)
        for script in FOOTBALL_SCRIPTS:
            apk.writestr(f'assets/Assets/{script}', b'broken' if script == broken
                         else program((0x1a, script), (0x1f, 0xfe01)).to_bytes())


class BuiltinExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.apk = self.root / 'input.apk'
        make_apk(self.apk, archive({1: metadata(), 25001: program(0x33).to_bytes()}))
        add_base_story(self.apk)
        self.profile = patch('exp_runtime.shs.content.NATIVE_SHA256', digest(FAKE_NATIVE))
        self.profile.start(); self.addCleanup(self.profile.stop)

    def test_exact_scripts_deterministic_container_and_resource_namespaces(self):
        with ZipFile(self.apk) as apk:
            data = extract_football(apk)
            self.assertEqual(data, extract_football(apk))
            exp = ExpArchive(data)
            self.assertEqual(set(exp.entries), {1, *FOOTBALL_SCRIPTS})
            self.assertEqual((exp.metadata().pack_id, exp.metadata().episode_id), (0, 0))
            self.assertEqual(exp.metadata().titles[1], 'Épisode')
            for script in FOOTBALL_SCRIPTS:
                self.assertEqual(exp.read(script), apk.read(f'assets/Assets/{script}'))
        library_path = self.root / 'library'
        manifest = import_game(self.apk, [], library_path)
        self.assertEqual(len(manifest['episodes']), 2)
        with ContentLibrary(library_path) as library:
            r = library.open_episode('footballseason')
            self.assertTrue(is_bundled(r.record))
            self.assertEqual(r.record['titles'][0], 'Authored base story')
            self.assertEqual(r.program(25001).instructions[0].operand, 25001)
            self.assertEqual(library.open_episode('Test.exp').program(25001).instructions[0].opcode, 0x33)
            self.assertEqual(r.read_asset(42), b'base image')
            self.assertEqual(library.ensure_builtin_episodes(), 0)
        moved = self.root / 'moved'; library_path.rename(moved); self.apk.unlink()
        with ContentLibrary(moved) as library:
            self.assertEqual(library.open_episode('Football Season').archive.data, data)

    def test_existing_library_migration_keeps_selection_saves_and_other_episodes(self):
        target = self.root / 'library'
        manifest = import_game(self.apk, [], target)
        # Reproduce the old manifest, which knew only APK .exp members.
        manifest['episodes'] = [e for e in manifest['episodes'] if 'builtin' not in e]
        path = target / 'library.json'
        path.write_text(json.dumps(manifest))
        player = target / 'player.json'; player.write_bytes(b'untouched preferences')
        saves = target / 'saves'; saves.mkdir()
        save = saves / 'existing.json'; save.write_bytes(b'untouched progress')
        with ContentLibrary(target) as library:
            self.assertEqual(library.ensure_builtin_episodes(), 1)
            self.assertEqual(library.episodes[0], manifest['episodes'][0])
            self.assertEqual(library.ensure_builtin_episodes(), 0)
            state = path.read_bytes()
        with ContentLibrary(target) as reopened:
            self.assertEqual(len(reopened.episodes), 2)
            self.assertEqual(reopened.ensure_builtin_episodes(), 0)
        self.assertEqual(path.read_bytes(), state)
        self.assertEqual(player.read_bytes(), b'untouched preferences')
        self.assertEqual(save.read_bytes(), b'untouched progress')

    def test_bad_builtin_script_aborts_whole_import(self):
        bad = self.root / 'bad.apk'
        make_apk(bad, archive({1: metadata(), 25001: program(0x33).to_bytes()}))
        add_base_story(bad, broken=25003)
        target = self.root / 'failed'
        with self.assertRaises(ContentError):
            import_game(bad, [], target)
        self.assertFalse(target.exists())


@unittest.skipUnless(Path('.shs-library/library.json').is_file(), 'user content unavailable')
class FootballStarContentTests(unittest.TestCase):
    def test_original_opening_name_look_classes_and_checkpoint(self):
        with ContentLibrary(Path('.shs-library')) as library:
            library.ensure_builtin_episodes()
            r = library.open_episode('Football Season')
            self.assertEqual(r.record['scripts'], list(FOOTBALL_SCRIPTS))
            for script in FOOTBALL_SCRIPTS:
                self.assertEqual(r.archive.read(script), library.read_asset(script))
            s = Session(r); s.engine.random = NativeRandom(1)
            self.assertEqual(s.advance().details['title'], 'Week 1 of 8')
            scenes, looks, names, choices = set(), 0, 0, 0
            for _ in range(300):
                action = s.advance(); scenes.add(s.scene)
                if action.name == 'character_picker':
                    s.answer(2); s.tick(25)
                    s = Session.from_snapshot(r, s.snapshot())
                    s.answer(); looks += 1
                elif action.name == 'text_input':
                    s.answer('Alex'); names += 1
                elif action.name == 'choice':
                    answer_screen(s, next(i for i,e in enumerate(action.details['enabled']) if e)); choices += 1
                elif action.name in ('dialogue', 'presentation', 'vm_pause'):
                    answer_screen(s)
                else:
                    break
            self.assertEqual((looks, names), (1, 1))
            self.assertGreater(choices, 10)
            self.assertIn(25004, scenes)  # Classes execute bit tests, RNG and packed-string concatenation.
            self.assertEqual(s.engine.strings['$USR'], 'Alex')
            self.assertEqual(s.pending.name, 'loading')
            self.assertEqual(s.pending.request.yield_id, 91)
            self.assertEqual(Session.from_snapshot(r, s.snapshot()).snapshot(), s.snapshot())
            s = Session.from_snapshot(r, s.snapshot())
            self.assertEqual(s.tick(3000).name, 'loading')
            self.assertEqual(s.tick(1).name, 'football')
            self.assertEqual((s.scene, s.pending.request.pc), (25006, 1270))
            self.assertEqual(s.pending.request.yield_id, 94)
            self.assertEqual(Session.from_snapshot(r, s.snapshot()).snapshot(), s.snapshot())
            # Play using the same public taps/ticks as the desktop, without
            # assigning a score or bypassing either mini-game half.
            for _ in range(5000):
                if s.pending.name != 'football':
                    break
                game = s.engine.football
                if game.phase in (20, 21, 22, 23):
                    s.answer()
                elif game.phase == 3:
                    visible = [i for i, target in enumerate(game.targets) if target.visible]
                    if visible:
                        s.answer(visible[0])
                s.tick(250)
            self.assertEqual(s.pending.name, 'dialogue')
            self.assertEqual(s.pending.details['character_id'], 1)
            self.assertTrue(all(score is not None for score in s.engine.football_scores))

    def test_menu_alias_sort_and_resume_after_restart(self):
        import os
        os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
        try:
            from exp_runtime.application import Application
        except ModuleNotFoundError:
            self.skipTest('desktop extra is not installed')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copyfile('.shs-library/library.json', root / 'library.json')
            (root / 'content').symlink_to(Path('.shs-library/content').resolve())
            app = Application(root, audio=False, check_updates=False)
            try:
                record = app.library.select('Football Season')
                self.assertEqual(app.visible_episodes()[0]['id'], record['id'])
                app.query = 'footballseason'
                self.assertEqual([e['id'] for e in app.visible_episodes()], [record['id']])
                app.selected = record['id']; app.start(resume=False)
                self.assertEqual(app.game.session.pending.details['title'], 'Week 1 of 8')
                app.return_to_menu()
            finally:
                app.close()
            reopened = Application(root, audio=False, check_updates=False)
            try:
                self.assertEqual(reopened.state.selected, record['id'])
                self.assertTrue(reopened.can_resume(record['id']))
                self.assertEqual(len(reopened.library.episodes), len(json.loads((root / 'library.json').read_text())['episodes']))
            finally:
                reopened.close()
