"""A staged import folder (staged_import.py) is picked up automatically on Application startup."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from exp_runtime.content import ContentLibrary, digest
from test_content import FAKE_HD_EXECUTABLE, FAKE_NATIVE, archive, make_apk, make_hd_ipa, metadata
from test_games import make_cod_ipa
from test_vm import program


class StagedImportOnStartupTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        self.pygame = pygame
        self.addCleanup(pygame.quit)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.profile = patch('exp_runtime.shs.content.NATIVE_SHA256', digest(FAKE_NATIVE))
        self.profile.start()
        self.addCleanup(self.profile.stop)

    def make_staged_folder(self, *, with_font=True):
        staged = self.root / 'import'
        staged.mkdir()
        make_apk(staged / 'game.apk', archive({1: metadata(), 25001: program(0x33).to_bytes()}))
        if with_font:
            (staged / 'ArialRoundedMTBold.ttf').write_bytes(b'not a real font, the path alone matters here')
        return staged

    def wait_for_import(self, app):
        self.assertIsNotNone(app.job, 'expected a staged import to have started a background job')
        app.job.result(timeout=5)       # let the background import finish before processing its result
        app.tick(0)

    def test_a_staged_apk_is_imported_automatically_with_no_manual_browsing(self):
        # The fixture APK is bare-bones (no menu string bank, layout bank or fonts), so opening the resulting
        # library to show a full menu still fails here the same way it would for any such library -- unrelated
        # to staged import specifically. What this confirms is the part that is new: the import itself ran with
        # no manual browsing or drag-and-drop at all, producing a real library on disk.
        self.make_staged_folder()
        with patch.dict(os.environ, {'SHS_IMPORT_DIR': str(self.root / 'import')}):
            from exp_runtime.application import Application
            app = Application(self.root / 'library', audio=False)
            self.wait_for_import(app)
            self.assertTrue((self.root / 'library' / 'library.json').is_file())

    def test_a_staged_font_is_copied_into_the_new_librarys_fonts_folder(self):
        self.make_staged_folder(with_font=True)
        with patch.dict(os.environ, {'SHS_IMPORT_DIR': str(self.root / 'import')}):
            from exp_runtime.application import Application
            app = Application(self.root / 'library', audio=False)
            self.wait_for_import(app)
            copied = self.root / 'library' / 'fonts' / 'ArialRoundedMTBold.ttf'
            self.assertTrue(copied.is_file())
            self.assertEqual(copied.read_bytes(), b'not a real font, the path alone matters here')

    def test_one_folder_sets_up_both_games_with_fonts_and_the_cod_art_source(self):
        staged = self.make_staged_folder(with_font=True)
        episode = archive({1: metadata('A staged case'), 25001: program(0x33).to_bytes()})
        make_cod_ipa(staged / 'cod.ipa', episode, free=True)
        make_hd_ipa(staged / 'hd.ipa', {311: b'HD portrait mask'})
        (staged / 'cod_episodes' / 'Caches').mkdir(parents=True)
        (staged / 'cod_episodes' / 'Caches' / 'Case.exp').write_bytes(
            archive({1: metadata('Another case'), 25001: program(0x33).to_bytes()}))
        (staged / 'cod_episodes' / 'Caches' / 'Cache.db').write_bytes(b'device clutter, skipped')
        cod = self.root / 'cod'
        with patch.dict(os.environ, {'SHS_IMPORT_DIR': str(staged)}), \
                patch('exp_runtime.content.HD_APP_SHA256', digest(FAKE_HD_EXECUTABLE)):
            from exp_runtime.application import Application
            app = Application(self.root / 'library', audio=False, game_libraries={'cod': cod})
            self.wait_for_import(app)
        for library in (self.root / 'library', cod):
            self.assertTrue((library / 'library.json').is_file())
            self.assertTrue((library / 'fonts' / 'ArialRoundedMTBold.ttf').is_file())
        with patch('exp_runtime.content.HD_APP_SHA256', digest(FAKE_HD_EXECUTABLE)):
            with ContentLibrary(self.root / 'library') as shs:
                self.assertIsNotNone(shs.hd_ipa)
            with ContentLibrary(cod) as library:
                self.assertEqual(library.game_id, 'cod')
                self.assertEqual(library.hd_asset(268), b'HD portrait mask')     # linked as CoD's art source
                self.assertIn('Another case', [t for e in library.episodes for t in e['titles']])

    def test_cause_of_death_alone_opens_its_own_library(self):
        staged = self.root / 'import'
        staged.mkdir()
        make_cod_ipa(staged / 'cod.ipa', archive({1: metadata('A staged case'), 25001: program(0x33).to_bytes()}),
                     free=True)
        cod = self.root / 'cod'
        with patch.dict(os.environ, {'SHS_IMPORT_DIR': str(staged)}):
            from exp_runtime.application import Application
            app = Application(self.root / 'library', audio=False, game_libraries={'cod': cod})
            self.addCleanup(app.release_library, checkpoint=False)
            self.wait_for_import(app)
        self.assertFalse((self.root / 'library').exists())
        self.assertTrue((cod / 'library.json').is_file())
        self.assertEqual(app.selected_game, 'cod')
        self.assertEqual(app.directory, cod)

    def test_an_empty_or_absent_staged_folder_falls_back_to_the_normal_setup_screen(self):
        with patch.dict(os.environ, {'SHS_IMPORT_DIR': str(self.root / 'nowhere')}):
            from exp_runtime.application import Application
            app = Application(self.root / 'library', audio=False)
            self.assertIsNone(app.job)
            self.assertIsNone(app.library)
            self.assertEqual(app.screen, 'setup')

    def test_staged_files_with_no_apk_surface_a_clear_message_not_a_silent_skip(self):
        staged = self.root / 'import'
        staged.mkdir()
        (staged / 'Font.ttf').write_bytes(b'x')
        with patch.dict(os.environ, {'SHS_IMPORT_DIR': str(staged)}):
            from exp_runtime.application import Application
            app = Application(self.root / 'library', audio=False)
            self.assertIsNone(app.job)
            self.assertIsNotNone(app.message)
            self.assertEqual(app.screen, 'setup')


if __name__ == '__main__':
    unittest.main()
