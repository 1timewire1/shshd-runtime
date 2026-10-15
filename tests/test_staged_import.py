"""The "drop your files here before first boot" folder (staged_import.py)."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from exp_runtime.content import ContentError
from exp_runtime.staged_import import (COD_EPISODES_DIRNAME, HD_EPISODES_DIRNAME, SD_EPISODES_DIRNAME, discover,
                                       staged_import_directory)
from test_content import make_hd_ipa
from test_games import make_cod_ipa
from test_ipa import make_ipa


class DiscoverTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def touch(self, *names):
        for name in names:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'x')

    def hd(self, name='hd.ipa'):
        make_hd_ipa(self.root / name, {})
        return self.root / name

    def cod(self, name='cod.ipa'):
        make_cod_ipa(self.root / name, b'episode', free=True)
        return self.root / name

    def test_an_absent_or_empty_folder_is_not_an_error_theres_simply_nothing_to_import(self):
        self.assertIsNone(discover(self.root / 'does-not-exist'))
        self.assertIsNone(discover(self.root))               # exists, but empty

    def test_the_builds_empty_skeleton_and_stray_files_are_nothing_to_import(self):
        for name in (SD_EPISODES_DIRNAME, HD_EPISODES_DIRNAME, COD_EPISODES_DIRNAME):
            (self.root / name / 'nested').mkdir(parents=True)
        self.touch('desktop.ini', 'README.txt', f'{COD_EPISODES_DIRNAME}/Thumbs.db')
        self.assertIsNone(discover(self.root))

    def test_a_bare_apk_alone_is_enough(self):
        self.touch('game.apk')
        staged = discover(self.root)
        self.assertEqual(staged.apk, self.root / 'game.apk')
        self.assertIsNone(staged.hd_ipa)
        self.assertEqual(staged.fonts, [])
        self.assertEqual(staged.episode_paths, [])
        self.assertEqual(staged.games, ['shs'])

    def test_the_full_set_is_discovered_and_episode_folders_are_handed_over_as_directories(self):
        self.touch('game.apk', 'ArialRoundedMTBold.ttf', f'{SD_EPISODES_DIRNAME}/Some_Episode.exp',
                   f'{HD_EPISODES_DIRNAME}/Other_Episode.exp', f'{COD_EPISODES_DIRNAME}/Caches/Case.exp')
        hd, cod = self.hd('b.ipa'), self.cod('a.ipa')      # told apart by contents, not by name
        staged = discover(self.root)
        self.assertEqual(staged.apk, self.root / 'game.apk')
        self.assertEqual((staged.hd_ipa, staged.cod_ipa), (hd, cod))
        self.assertEqual(staged.fonts, [self.root / 'ArialRoundedMTBold.ttf'])
        self.assertEqual(set(staged.episode_paths), {self.root / SD_EPISODES_DIRNAME, self.root / HD_EPISODES_DIRNAME})
        self.assertEqual(staged.cod_episode_paths, [self.root / COD_EPISODES_DIRNAME])
        self.assertEqual(staged.games, ['shs', 'cod'])

    def test_cause_of_death_alone_and_with_the_hd_ipa_as_its_art_source(self):
        cod = self.cod()
        self.touch(f'{COD_EPISODES_DIRNAME}/Case.exp')
        staged = discover(self.root)
        self.assertEqual((staged.games, staged.cod_ipa, staged.apk, staged.hd_ipa), (['cod'], cod, None, None))
        hd = self.hd()
        self.assertEqual((discover(self.root).games, discover(self.root).hd_ipa), (['cod'], hd))

    def test_episodes_for_a_game_that_is_not_staged_are_an_error(self):
        self.cod()
        self.touch(f'{SD_EPISODES_DIRNAME}/Some_Episode.exp')
        with self.assertRaisesRegex(ContentError, 'no SHS Android .apk'):
            discover(self.root)
        (self.root / 'cod.ipa').unlink()
        (self.root / SD_EPISODES_DIRNAME / 'Some_Episode.exp').unlink()
        self.touch('game.apk', f'{COD_EPISODES_DIRNAME}/Case.exp')
        with self.assertRaisesRegex(ContentError, 'Cause of Death .ipa'):
            discover(self.root)

    def test_the_standard_shs_ios_app_and_unreadable_ipas_are_refused(self):
        make_ipa(self.root / 'shs.ipa', b'episode')
        self.touch('game.apk')
        with self.assertRaisesRegex(ContentError, 'standard SHS iOS app'):
            discover(self.root)
        (self.root / 'shs.ipa').write_bytes(b'not a zip')
        with self.assertRaisesRegex(ContentError, 'not a readable IPA'):
            discover(self.root)

    def test_multiple_font_files_are_all_kept_not_just_one(self):
        self.touch('game.apk', 'ArialRoundedMTBold.ttf', 'TrebuchetMS-Bold.ttf')
        staged = discover(self.root)
        self.assertEqual(set(staged.fonts), {self.root / 'ArialRoundedMTBold.ttf', self.root / 'TrebuchetMS-Bold.ttf'})

    def test_files_staged_with_no_game_is_a_real_error_not_a_silent_skip(self):
        self.hd()
        with self.assertRaises(ContentError):
            discover(self.root)
        (self.root / 'hd.ipa').unlink()
        self.touch('Font.ttf')
        with self.assertRaises(ContentError):
            discover(self.root)

    def test_an_episode_folder_with_no_apk_is_also_a_real_error(self):
        self.touch(f'{SD_EPISODES_DIRNAME}/Some_Episode.exp')
        with self.assertRaises(ContentError):
            discover(self.root)

    def test_more_than_one_apk_or_ipa_is_rejected(self):
        self.touch('a.apk', 'b.apk')
        with self.assertRaises(ContentError):
            discover(self.root)
        for p in self.root.glob('*.apk'):
            p.unlink()
        self.touch('game.apk')
        self.hd('a.ipa'), self.hd('b.ipa')
        with self.assertRaisesRegex(ContentError, 'more than one SHS HD'):
            discover(self.root)
        for p in self.root.glob('*.ipa'):
            p.unlink()
        self.cod('a.ipa'), self.cod('b.ipa')
        with self.assertRaisesRegex(ContentError, 'more than one Cause of Death'):
            discover(self.root)


class StagedImportDirectoryTests(unittest.TestCase):
    def test_an_explicit_override_always_wins(self):
        with patch.dict(os.environ, {'SHS_IMPORT_DIR': '/custom/path'}):
            self.assertEqual(staged_import_directory(), Path('/custom/path'))

    def test_a_source_checkout_with_no_override_has_nowhere_safe_to_look(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('SHS_IMPORT_DIR', None)
            with patch('exp_runtime.staged_import.sys') as fake_sys:
                fake_sys.frozen = False
                self.assertIsNone(staged_import_directory())

    def test_a_frozen_build_looks_beside_its_own_executable(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('SHS_IMPORT_DIR', None)
            with patch('exp_runtime.staged_import.sys') as fake_sys:
                fake_sys.frozen = True
                exe_dir = Path.cwd() / 'dist' / 'SHSHD Runtime'
                fake_sys.executable = str(exe_dir / 'SHSHD Runtime.exe')
                self.assertEqual(staged_import_directory(), exe_dir / 'import')


if __name__ == '__main__':
    unittest.main()
