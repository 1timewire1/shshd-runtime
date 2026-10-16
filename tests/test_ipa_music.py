"""Optional APK music fills verified IPA gaps without changing story assets."""
from contextlib import redirect_stderr, redirect_stdout
from concurrent.futures import ThreadPoolExecutor
import importlib.util
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import warnings
from zipfile import ZipFile

from exp_runtime.audio import music_cue
from exp_runtime.shs.audio import IOS_DOWNLOADED_MUSIC
from exp_runtime.cli import main
from exp_runtime.content import ContentError, ContentLibrary, NATIVE_MEMBER, digest, import_game
from exp_runtime.runtime import Session
from test_content import FAKE_NATIVE, archive, metadata
from test_ipa import ASSETS, ASSET_DATA, LOCAL_IPA, make_ipa
from test_vm import program


def make_music_apk(path, *, native=FAKE_NATIVE, omit=None):
    with ZipFile(path, 'w') as apk:
        apk.writestr(NATIVE_MEMBER, native)
        for resource in (*IOS_DOWNLOADED_MUSIC, 8203, 8204):
            if resource != omit:
                apk.writestr(f'assets/Assets/audio/music/{resource}.mp3', f'authored music {resource}'.encode())
        apk.writestr('assets/Assets/126', b'Android UI must not fill IPA numeric gaps')
        apk.writestr('assets/Assets/505', b'Android font must not replace installed IPA fonts')
        apk.writestr('assets/Assets/fonts/ArialMT14.fnt', b'Android font metrics')
        apk.writestr('assets/Assets/26001', b'Android art must not fill the episode bank')
        apk.writestr('assets/Assets/Android.exp', archive({1: metadata('APK story'),
                                                      25001: program(0x33).to_bytes()}))


class IPAMusicImportTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.ipa, self.apk = self.root / 'source.ipa', self.root / 'music.apk'
        self.path = self.root / 'library'
        self.episode = archive({1: metadata(), 25001: program(0x33).to_bytes(), 26000: b'episode art'})
        make_ipa(self.ipa, self.episode)
        # A future/repacked IPA may already contain a downloaded track.
        with ZipFile(self.ipa, 'a') as ipa:
            ipa.writestr(ASSETS + '8201', b'preferred IPA music')
        make_music_apk(self.apk)
        profile = patch('exp_runtime.shs.content.NATIVE_SHA256', digest(FAKE_NATIVE))
        profile.start(); self.addCleanup(profile.stop)

    def test_legacy_ipa_manifest_upgrades_only_when_music_is_added(self):
        manifest = import_game(self.ipa, [], self.path)
        manifest.update(format='shs-content-library', version=2)
        del manifest['game']
        path = self.path / 'library.json'
        path.write_text(json.dumps(manifest))
        with ContentLibrary(self.path) as library:
            original = Session(library.open_episode('Test.exp'))
            original.advance()
            saved = original.snapshot(); saved['format'] = 'shs-runtime-save'
            self.assertEqual(library.add_music_apk(self.apk), 9)
            self.assertEqual(library.manifest['version'], 3)
            self.assertEqual(library.manifest['format'], 'shs-content-library')
        with ContentLibrary(self.path) as reopened:
            self.assertEqual(reopened.missing_music_ids, ())
            self.assertEqual(reopened.read_asset(8201), b'preferred IPA music')
            self.assertEqual(reopened.read_asset(8217), b'authored music 8217')
            restored = Session.from_snapshot(reopened.open_episode('Test.exp'), saved)
            self.assertEqual(restored.snapshot(), original.snapshot())

    def test_optional_import_preserves_ipa_precedence_namespaces_and_relocation(self):
        manifest = import_game(self.ipa, [], self.path, music_apk=self.apk)
        self.assertEqual((manifest['format'], manifest['version'], manifest['game']), ('exp-content-library', 1, 'shs'))
        self.assertEqual(len(manifest['episodes']), 1)
        self.assertNotIn('apk', manifest)
        moved = self.root / 'moved'; self.path.rename(moved)
        self.ipa.unlink(); self.apk.unlink()
        with ContentLibrary(moved) as library:
            r = library.open_episode('Test.exp')
            self.assertEqual(r.read_asset(8201), b'preferred IPA music')
            self.assertEqual(r.read_asset(8203), ASSET_DATA[8203])
            for resource in IOS_DOWNLOADED_MUSIC[1:]:
                self.assertTrue(r.exists(resource))
                self.assertEqual(r.read_asset(resource), f'authored music {resource}'.encode())
            self.assertEqual(r.read_asset(26000), b'episode art')
            self.assertEqual(r.read_ui_resource(126), ASSET_DATA[125])
            for resource in (126, 505, 8204, 26001):
                self.assertFalse(r.exists(resource))
                with self.assertRaises(ContentError): r.read_asset(resource)
            with self.assertRaisesRegex(ContentError, 'IPA has no named UI asset'):
                library.read_ui_asset('fonts/ArialMT14.fnt')
            self.assertEqual(library.missing_music_ids, ())
            self.assertEqual(r.program(25001).to_bytes(), program(0x33).to_bytes())

    def test_existing_checkpoints_and_live_resources_survive_adding_music(self):
        import_game(self.ipa, [], self.path)
        with ContentLibrary(self.path) as library:
            r = library.open_episode('Test.exp')
            session = Session(r); session.advance()
            session.engine.music_id = 8217
            save = session.save(); before = save.read_bytes()
            snapshot, identity = session.snapshot(), r.identity
            with self.assertRaises(ContentError): r.read_asset(8217)
            self.assertEqual(library.add_music_apk(self.apk), 9)
            self.assertEqual(r.identity, identity)
            self.assertEqual(save.read_bytes(), before)
            self.assertEqual(Session.load(r, save).snapshot(), snapshot)
            self.assertEqual(r.read_asset(8217), b'authored music 8217')
            manifest = (self.path / 'library.json').read_bytes()
            self.assertEqual(library.add_music_apk(self.apk), 0)
            self.assertEqual((self.path / 'library.json').read_bytes(), manifest)
            extra = self.root / 'extra.exp'
            extra.write_bytes(archive({1: metadata('Extra'), 25001: program(0x33).to_bytes()}))
            self.assertEqual(library.add_episodes([extra]), 1)
        with ContentLibrary(self.path) as reopened:
            self.assertEqual(Session.load(reopened.open_episode('Test.exp'), save).snapshot(), snapshot)
            self.assertEqual(reopened.read_asset(8217), b'authored music 8217')
            self.assertEqual(len(reopened.episodes), 2)

    def test_bad_donors_leave_new_and_existing_libraries_unchanged(self):
        import_game(self.ipa, [], self.path)
        before = (self.path / 'library.json').read_bytes()
        files = sorted(p.name for p in (self.path / 'content').iterdir())
        for mutation in ('zip', 'profile', 'missing', 'duplicate'):
            with self.subTest(mutation=mutation):
                make_music_apk(self.apk, native=b'wrong native' if mutation == 'profile' else FAKE_NATIVE,
                               omit=8217 if mutation == 'missing' else None)
                if mutation == 'zip': self.apk.write_bytes(b'not a ZIP')
                if mutation == 'duplicate':
                    with ZipFile(self.apk, 'a') as apk, warnings.catch_warnings():
                        warnings.simplefilter('ignore', UserWarning)
                        apk.writestr('assets/Assets/audio/music/8217.mp3', b'ambiguous')
                target = self.root / ('new-' + mutation)
                with self.assertRaises(ContentError):
                    import_game(self.ipa, [], target, music_apk=self.apk)
                self.assertFalse(target.exists())
                with ContentLibrary(self.path) as library, self.assertRaises(ContentError):
                    library.add_music_apk(self.apk)
                self.assertEqual((self.path / 'library.json').read_bytes(), before)
                self.assertEqual(sorted(p.name for p in (self.path / 'content').iterdir()), files)
                self.assertFalse(list(self.path.glob('.exp-import-*')))
        self.assertFalse(list(self.root.glob('.exp-import-*')))

    def test_manifest_and_music_source_tampering_are_rejected(self):
        manifest = import_game(self.ipa, [], self.path, music_apk=self.apk)
        path = self.path / 'library.json'
        for field, value in (('file', '../music.apk'), ('sha256', '0' * 64), ('native_sha256', '0' * 64)):
            changed = json.loads(json.dumps(manifest)); changed['music_apk'][field] = value
            path.write_text(json.dumps(changed))
            with self.subTest(field=field), self.assertRaises(ContentError): ContentLibrary(self.path)
        changed = dict(manifest, version=2)
        path.write_text(json.dumps(changed))
        with self.assertRaises(ContentError): ContentLibrary(self.path)
        path.write_text(json.dumps(manifest))
        with (self.path / manifest['music_apk']['file']).open('ab') as stream: stream.write(b'changed')
        with self.assertRaisesRegex(ContentError, 'content changed'): ContentLibrary(self.path)

    def test_failed_publication_and_stale_import_do_not_change_library(self):
        import_game(self.ipa, [], self.path)
        before = (self.path / 'library.json').read_bytes()
        files = sorted(p.name for p in (self.path / 'content').iterdir())
        replace = Path.replace
        def fail_manifest(path, destination):
            if path.name == 'library.json': raise OSError('authored write failure')
            return replace(path, destination)
        with ContentLibrary(self.path) as library:
            with patch.object(Path, 'replace', fail_manifest), self.assertRaises(OSError):
                library.add_music_apk(self.apk)
            self.assertEqual((self.path / 'library.json').read_bytes(), before)
            self.assertEqual(sorted(p.name for p in (self.path / 'content').iterdir()), files)
            self.assertIn(8217, library.missing_music_ids)
            with self.assertRaises(ContentError): library.read_asset(8217)
            changed = dict(library.manifest, authored_concurrent_edit=True)
            (self.path / 'library.json').write_text(json.dumps(changed))
            with self.assertRaisesRegex(ContentError, 'library changed'):
                library.add_music_apk(self.apk)
            self.assertEqual(sorted(p.name for p in (self.path / 'content').iterdir()), files)

    def test_apk_libraries_cannot_receive_an_ipa_music_supplement(self):
        with self.assertRaisesRegex(ContentError, 'only supplement an SHS IPA'):
            import_game(self.apk, [], self.path, music_apk=self.apk)
        self.assertFalse(self.path.exists())
        import_game(self.apk, [], self.path)
        with ContentLibrary(self.path) as library, self.assertRaisesRegex(ContentError, 'only supplement an SHS IPA'):
            library.add_music_apk(self.apk)

    def test_cli_supports_optional_music_during_import_and_afterward(self):
        for at_import in (False, True):
            with self.subTest(at_import=at_import), redirect_stdout(StringIO()):
                path = self.root / str(at_import)
                args = ['import', '--ipa', str(self.ipa), '--library', str(path)]
                if at_import: args += ['--music-apk', str(self.apk)]
                main(args)
                if not at_import: main(['add-music', '--apk', str(self.apk), '--library', str(path)])
                with ContentLibrary(path) as library:
                    self.assertEqual(library.read_asset(8217), b'authored music 8217')
                    self.assertEqual(library.read_asset(8201), b'preferred IPA music')
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            main(['import', '--apk', str(self.apk), '--music-apk', str(self.apk), '--library', str(self.path)])
        self.assertFalse(self.path.exists())

    @unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is absent')
    def test_desktop_drop_accepts_ipa_and_optional_apk_in_either_order(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        from exp_runtime.application import Application
        pygame.display.init(); self.addCleanup(pygame.quit)
        for order in ((self.ipa, self.apk), (self.apk, self.ipa)):
            # Exercise the real background importer without requiring fonts
            # or original menu art in this authored-container test.
            with ThreadPoolExecutor(max_workers=1) as executor:
                app = Application.__new__(Application)
                from exp_runtime.pointer import ButtonPress
                app.press, app.game = ButtonPress(), None
                app.selected_game = 'shs'
                app.job, app.library, app.executor = None, None, executor
                app.directory = self.root / order[0].suffix[1:]
                app.import_paths(order)
                manifest = app.job.result(timeout=10)
                self.assertEqual((manifest['format'], manifest['version'], manifest['game']), ('exp-content-library', 1, 'shs'))
                self.assertEqual(manifest['episodes'][0]['name'], 'Test.exp')
                with ContentLibrary(app.directory) as library:
                    self.assertEqual(library.read_asset(8201), b'preferred IPA music')
                    self.assertEqual(library.read_asset(8217), b'authored music 8217')


@unittest.skipUnless(LOCAL_IPA.is_file() and Path('.shs-library/library.json').is_file()
                     and importlib.util.find_spec('pygame'), 'optional original game content/desktop is absent')
class LocalIPAMusicTests(unittest.TestCase):
    def test_menu_adds_original_music_preserves_live_story_and_plays_all_missing_cues(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        from exp_runtime.application import Application
        from test_runtime import answer_screen
        self.addCleanup(pygame.quit)
        with ContentLibrary(Path('.shs-library')) as android:
            if android.kind != 'apk': self.skipTest('local Android library is absent')
            source = android.directory / android.manifest['apk']['file']
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'library'; import_game(LOCAL_IPA, [], path)
                app = Application(path, audio=True, check_updates=False)
                try:
                    app.selected = app.library.select('The_New_Girl.exp')['id']
                    app.start()
                    for _ in range(5):
                        if app.game.session.engine.music_id == 8217: break
                        answer_screen(app.game.session)
                    self.assertEqual(app.game.session.engine.music_id, 8217)
                    with self.assertLogs(level='WARNING'):
                        app.game._sync_audio()
                    self.assertFalse(app.game.music_loaded)
                    app.return_to_menu()
                    saved = app.game.session.snapshot()
                    checkpoint = app.state.resume_path(app.selected)
                    before = checkpoint.read_bytes()
                    app.show('library'); app.tick(400); app.render()
                    self.assertIn(('browse', 'music_apk'), [command for _, command in app.buttons])
                    app.browse('music_apk'); app.read_folder(source.parent)
                    self.assertTrue(all(p.is_dir() or p.suffix.lower() == '.apk' for p in app.files))
                    app.import_paths([source]); self.assertEqual(app.job.result(timeout=10), 10)
                    app.tick(0)
                    self.assertEqual(app.screen, 'library')
                    self.assertEqual(app.game.session.snapshot(), saved)
                    self.assertEqual(checkpoint.read_bytes(), before)
                    self.assertEqual(app.library.missing_music_ids, ())
                    app.command(('dismiss',)); app.start()
                    app.tick(1000)  # The native menu track fades before restoring story audio.
                    app.game._sync_audio()
                    self.assertTrue(app.game.music_loaded)
                    self.assertTrue(pygame.mixer.music.get_busy())
                    requests = [n for n in range(8201, 8233) if music_cue(n).asset_id in IOS_DOWNLOADED_MUSIC]
                    for request in requests:
                        with self.subTest(request=request), self.assertNoLogs(level='WARNING'):
                            app.game.session.engine.music_id = request
                            app.game._sync_audio()
                            self.assertTrue(pygame.mixer.music.get_busy())
                            resource = music_cue(request).asset_id
                            self.assertEqual(app.library.read_asset(resource), android.read_asset(resource))
                finally:
                    app.close()
