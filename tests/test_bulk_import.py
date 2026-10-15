"""One .zip/.rar holding the import folder's layout sets up both games (staged_import.py, this fork's bulk import)."""
import os
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

from exp_runtime.content import ContentError, ContentLibrary, digest
from exp_runtime.staged_import import extract_bulk, import_bulk, staged_archive
from ios.probe.rar_fixture import rar4, rar5
from test_content import FAKE_HD_EXECUTABLE, FAKE_NATIVE, archive, make_apk, make_hd_ipa, metadata
from test_games import make_cod_ipa
from test_vm import program


def episode(title):
    return archive({1: metadata(title), 25001: program(0x33).to_bytes()})


class BulkImportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for target, value in (('exp_runtime.shs.content.NATIVE_SHA256', digest(FAKE_NATIVE)),
                              ('exp_runtime.content.HD_APP_SHA256', digest(FAKE_HD_EXECUTABLE))):
            patcher = patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        source = self.root / 'source'
        source.mkdir()
        make_apk(source / 'game.apk', episode('A staged story'))
        make_hd_ipa(source / 'hd.ipa', {311: b'HD portrait mask'})
        make_cod_ipa(source / 'cod.ipa', episode('A staged case'), free=True)
        self.members = {name: (source / name).read_bytes() for name in ('game.apk', 'hd.ipa', 'cod.ipa')}
        self.members.update({'ArialRoundedMTBold.ttf': b'font bytes',
                             'shs_episodes/Set1/Extra.exp': episode('An extra story'),
                             'cod_episodes/Case.exp': episode('Another case'),
                             'cod_episodes/Burstly/burstly.cookies': b'device clutter, never extracted',
                             '__MACOSX/._game.apk': b'resource fork', 'README.txt': b'notes'})
        self.targets = {'shs': self.root / 'libraries' / 'shs', 'cod': self.root / 'libraries' / 'cod'}

    def make_zip(self, name='games.zip', prefix='', members=None):
        path = self.root / name
        with ZipFile(path, 'w', ZIP_DEFLATED) as package:
            for member, data in (members or self.members).items():
                package.writestr(prefix + member, data)
        return path

    def check_both_games(self):
        for game, title in (('shs', 'An extra story'), ('cod', 'Another case')):
            library = self.targets[game]
            self.assertEqual((library / 'fonts' / 'ArialRoundedMTBold.ttf').read_bytes(), b'font bytes')
            with ContentLibrary(library) as opened:
                self.assertEqual(opened.game_id, game)
                self.assertIn(title, [t for e in opened.episodes for t in e['titles']])
                if game == 'cod':
                    self.assertEqual(opened.hd_asset(268), b'HD portrait mask')
        self.assertEqual([p.name for p in (self.root / 'libraries').iterdir()], ['cod', 'shs'])  # stage removed

    def test_a_zip_with_the_layout_at_its_root_imports_both_games(self):
        imported, errors = import_bulk(self.make_zip(), self.targets)
        self.assertEqual((sorted(imported), errors), (['cod', 'shs'], []))
        self.check_both_games()

    def test_one_wrapping_folder_is_looked_inside(self):
        stage = self.root / 'stage'
        stage.mkdir()
        root = extract_bulk(self.make_zip(prefix='My Games/'), stage)
        self.assertEqual(root, stage / 'My Games')
        self.assertEqual(sorted(p.name for p in root.iterdir()),
                         ['ArialRoundedMTBold.ttf', 'cod.ipa', 'cod_episodes', 'game.apk', 'hd.ipa', 'shs_episodes'])
        self.assertEqual([p.name for p in (root / 'cod_episodes').iterdir()], ['Case.exp'])   # clutter skipped

    def test_rar4_and_rar5_archives_import_too(self):
        members = [(name, data) for name, data in self.members.items()]
        for pack in (rar4, rar5):
            with self.subTest(pack=pack.__name__):
                for library in self.targets.values():
                    if library.exists():
                        shutil.rmtree(library)
                path = self.root / 'games.rar'
                path.write_bytes(pack(members))
                imported, errors = import_bulk(path, self.targets)
                self.assertEqual((sorted(imported), errors), (['cod', 'shs'], []))
                self.check_both_games()

    def test_an_existing_library_is_left_as_it_is_and_said_so(self):
        archive_path = self.make_zip()
        self.targets['shs'].mkdir(parents=True)
        (self.targets['shs'] / 'library.json').write_text('{}')
        imported, errors = import_bulk(archive_path, self.targets)
        self.assertEqual(sorted(imported), ['cod'])
        self.assertIn('already had a library', str(errors[0]))
        self.assertEqual((self.targets['shs'] / 'library.json').read_text(), '{}')
        self.targets['cod'].mkdir(exist_ok=True)
        with self.assertRaisesRegex(ContentError, 'Nothing was imported'):
            import_bulk(archive_path, self.targets)

    def test_unsafe_paths_duplicates_and_archives_without_games_are_refused(self):
        for bad in ('../escape.apk', '/abs/game.apk', 'C:\\game.apk'):
            with self.subTest(bad=bad), self.assertRaisesRegex(ContentError, 'invalid path'):
                import_bulk(self.make_zip(members={**self.members, bad: b'x'}), self.targets)
        with self.assertRaisesRegex(ContentError, 'two files'):
            import_bulk(self.make_zip(members={**self.members, 'GAME.apk': b'x'}), self.targets)
        with self.assertRaisesRegex(ContentError, 'no game files'):
            import_bulk(self.make_zip(members={'README.txt': b'notes'}), self.targets)
        (self.root / 'broken.zip').write_bytes(b'not a zip')
        with self.assertRaisesRegex(ContentError, 'not a readable ZIP'):
            import_bulk(self.root / 'broken.zip', self.targets)
        self.assertFalse(any(p.name.startswith('.exp-bulk-') for p in (self.root / 'libraries').iterdir()))

    def test_too_little_disk_space_is_reported_before_extracting(self):
        with patch('exp_runtime.staged_import.shutil.disk_usage', return_value=SimpleNamespace(free=1024)), \
                self.assertRaisesRegex(ContentError, 'GB free'):
            import_bulk(self.make_zip(), self.targets)

    def test_the_import_folder_takes_one_archive(self):
        folder = self.root / 'import'
        folder.mkdir()
        self.assertIsNone(staged_archive(folder))
        (folder / 'games.zip').write_bytes(b'x')
        self.assertEqual(staged_archive(folder), folder / 'games.zip')
        (folder / 'more.rar').write_bytes(b'x')
        with self.assertRaisesRegex(ContentError, 'more than one'):
            staged_archive(folder)


class BulkImportAppTests(BulkImportTests):
    """The app: first boot lands on Bulk Import; an archive in the import folder, or chosen there, imports both."""

    def setUp(self):
        super().setUp()
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        self.addCleanup(pygame.quit)
        self.folder = self.root / 'import'
        (self.folder / 'cod_episodes').mkdir(parents=True)         # the build's empty skeleton
        environment = patch.dict(os.environ, {'SHS_IMPORT_DIR': str(self.folder)})
        environment.start()
        self.addCleanup(environment.stop)

    def app(self):
        from exp_runtime.application import Application
        app = Application(audio=False, check_updates=False, game_key='shs', library_root=self.root / 'libraries',
                          settings_path=self.root / 'settings.json')
        self.addCleanup(app.release_library, checkpoint=False)
        return app

    def finish(self, app):
        self.assertEqual(app.job_kind, 'bulk')
        app.job.result(timeout=20)
        app.tick(0)

    def test_first_boot_with_nothing_staged_lands_on_bulk_import(self):
        app = self.app()
        self.assertEqual((app.screen, app.message, app.job), ('bulk', '', None))
        app.command(('back',))
        self.assertEqual(app.screen, 'games')
        app.command(('bulk',))
        self.assertEqual(app.screen, 'bulk')

    def test_an_archive_in_the_import_folder_imports_both_games_at_first_boot(self):
        self.make_zip()
        (self.root / 'games.zip').rename(self.folder / 'games.zip')
        app = self.app()
        self.finish(app)
        self.check_both_games()
        self.assertEqual(app.selected_game, 'shs')

    def test_an_archive_dropped_or_chosen_on_the_page_imports_both_games(self):
        app = self.app()
        app.import_paths([self.make_zip()])
        self.finish(app)
        self.check_both_games()

    def test_only_the_other_games_library_opens_that_game(self):
        app = self.app()
        app.import_paths([self.make_zip(members={k: v for k, v in self.members.items() if 'cod' in k
                                                 or k.endswith('.ttf')})])
        self.finish(app)
        app.release_library(checkpoint=False)
        again = self.app()
        self.assertEqual((again.selected_game, again.screen != 'bulk'), ('cod', True))

    # The engine-level cases above need not run again through the app.
    test_a_zip_with_the_layout_at_its_root_imports_both_games = None
    test_one_wrapping_folder_is_looked_inside = None
    test_rar4_and_rar5_archives_import_too = None
    test_an_existing_library_is_left_as_it_is_and_said_so = None
    test_unsafe_paths_duplicates_and_archives_without_games_are_refused = None
    test_too_little_disk_space_is_reported_before_extracting = None
    test_the_import_folder_takes_one_archive = None


if __name__ == '__main__':
    unittest.main()
