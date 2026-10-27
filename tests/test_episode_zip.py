"""Authored episode ZIPs exercising the shared desktop/iOS import path."""
from pathlib import Path
import shutil
import stat
import struct
import tempfile
import unittest
from unittest.mock import patch
import warnings
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from exp_runtime.content import ContentError, ContentLibrary, digest, import_game
from exp_runtime.runtime import Session
from test_content import FAKE_NATIVE, archive, make_apk, metadata
from test_episode_catalog import cod_options, entry, options
from test_games import make_cod_ipa
from test_ipa import make_ipa
from test_vm import program


def write_zip(path, members, *, compression=ZIP_DEFLATED):
    with ZipFile(path, 'w', compression=compression) as package:
        for name, data in members:
            package.writestr(name, data)
    return path


class EpisodeZipTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        native = patch('exp_runtime.shs.content.NATIVE_SHA256', digest(FAKE_NATIVE))
        native.start()
        self.addCleanup(native.stop)
        self.base = archive({1: metadata('Bundled story'), 25001: program(0x33).to_bytes()})
        self.extra = archive({1: metadata('ZIP story'), 25001: program(0x33).to_bytes(),
                              26000: b'Authored episode art'})
        self.sources = [('shs', self.root / 'shs.apk', options),
                        ('shs', self.root / 'shs.ipa', options),
                        ('cod', self.root / 'cod.ipa', cod_options)]
        for (_, source, _), make in zip(self.sources, (make_apk, make_ipa, make_cod_ipa)):
            make(source, self.base)

    def catalog(self, encode):
        return encode([entry(7, 2, 'ZIP story', 'ZIP Collection', 'story.EXP')])

    def test_initial_import_subfolders_catalogs_and_relocation_without_zip(self):
        for game, source, encode in self.sources:
            with self.subTest(source=source.name):
                bundle = write_zip(self.root / 'episodes.ZIP', [
                    ('Episodes/', b''), ('Episodes/./nested/story.EXP', self.extra),
                    ('Episodes/base-copy.exp', self.base),
                    (f'Episodes/{game.upper()}_OPTIONS.SAV', self.catalog(encode)),
                    ('Episodes/cod_options.sav' if game == 'shs' else 'Episodes/shs_options.sav', b'foreign catalog'),
                    ('__MACOSX/Episodes/._story.EXP', b'AppleDouble metadata'),
                    ('Episodes/._story.EXP', b'AppleDouble metadata'),
                    ('__MACOSX/fake.exp', b'ignored metadata'),
                    ('README.txt', b'authored collection notes'), ('other.zip', b'not recursively expanded')])
                before = bundle.read_bytes()
                directory = self.root / (source.name + '-library')
                manifest = import_game(source, [bundle], directory, game=game)
                self.assertEqual(len(manifest['episodes']), 2)
                self.assertEqual(bundle.read_bytes(), before)
                self.assertFalse((directory / 'Episodes').exists())
                self.assertFalse(list(directory.rglob('*.zip')))
                bundle.unlink()
                moved = directory.with_name(directory.name + '-moved')
                directory.rename(moved)
                source.unlink()
                with ContentLibrary(moved) as library:
                    resources = library.open_episode('story.EXP')
                    self.assertEqual(resources.read_asset(26000), b'Authored episode art')
                    self.assertEqual(library.catalog.category(resources.record), 'ZIP Collection')
                    self.assertEqual(library.select('base-copy.exp')['id'], digest(self.base))
                    self.assertEqual(resources.program(25001).instructions[0].opcode, 0x33)

    def test_mixed_sources_reimports_and_catalog_only_zip_preserve_progress(self):
        for game, source, encode in self.sources:
            with self.subTest(source=source.name):
                directory = self.root / (source.name + '-library')
                import_game(source, [], directory)
                folder = self.root / (source.name + '-inputs')
                folder.mkdir()
                loose = folder / 'loose.exp'
                loose.write_bytes(self.extra)
                first = write_zip(folder / 'one.zip', [('nested/story.EXP', self.extra), ('base.exp', self.base)])
                second = write_zip(folder / 'two.zip', [('Windows\\episodes\\alias.exp', self.extra)])
                with ContentLibrary(directory) as library:
                    self.assertEqual(library.add_episodes([folder, first, second, loose]), 1)
                    resources = library.open_episode('story.EXP')
                    self.assertEqual(library.select('alias.exp')['id'], resources.record['id'])
                    session = Session(resources)
                    session.advance()
                    saved = session.save()
                    snapshot, save_bytes = session.snapshot(), saved.read_bytes()
                    contents = set((directory / 'content').iterdir())
                    sidecar = write_zip(folder / 'catalog.zip', [(f'Catalog/{game}_options.sav', self.catalog(encode))])
                    self.assertEqual(library.add_episodes([sidecar]), 0)
                    self.assertEqual(library.catalog.category(library.select('story.EXP')), 'ZIP Collection')
                    manifest = (directory / 'library.json').read_bytes()
                    self.assertEqual(library.add_episodes([first, folder, second, loose]), 0)
                    self.assertEqual((directory / 'library.json').read_bytes(), manifest)
                    self.assertEqual(set((directory / 'content').iterdir()), contents)
                    self.assertEqual(saved.read_bytes(), save_bytes)
                    self.assertEqual(Session.from_snapshot(resources, snapshot).snapshot(), snapshot)
                shutil.rmtree(folder)
                with ContentLibrary(directory) as reopened:
                    self.assertEqual(Session.load(reopened.open_episode('alias.exp'), saved).snapshot(), snapshot)

    def test_a_legacy_games_tag_is_dropped_from_the_title_and_files_the_episode(self):
        # shshd-runtime: a New Rules translation is titled "... (SHSNR)" (shs profile LEGACY_GAMES); on import, in the
        # first library or added later, the tag leaves every title and the episode is tagged and filed under New Rules.
        tagged = archive({1: metadata('ZIP story (SHSNR)'), 25001: program(0x33).to_bytes(), 26000: b'art'})
        for initial in (True, False):
            with self.subTest(initial=initial):
                directory = self.root / f'legacy-{initial}'
                story = self.root / 'story.exp'
                story.write_bytes(tagged)
                import_game(self.sources[0][1], [story] if initial else [], directory)
                with ContentLibrary(directory) as library:
                    if not initial:
                        self.assertEqual(library.add_episodes([story]), 1)
                    record = library.select(digest(tagged))
                    self.assertEqual(record['titles'][0], 'ZIP story')
                    self.assertEqual((record['legacy'], record['category']), ('SHSNR', 'New Rules'))
                    plain = library.select('Bundled story')
                    self.assertNotIn('legacy', plain)
                    self.assertNotIn('order', record)                   # only LEGACY_GAMES' listed episodes
                with ContentLibrary(directory) as reopened:            # the manifest accepts the new fields
                    self.assertEqual(reopened.select(digest(tagged))['legacy'], 'SHSNR')

    def test_same_basename_and_metadata_do_not_merge_different_editions(self):
        directory = self.root / 'library'
        import_game(self.sources[0][1], [], directory)
        variant = archive({1: metadata('ZIP story'), 25001: program(0x33).to_bytes(), 26000: b'variant art'})
        bundle = write_zip(self.root / 'editions.zip', [('first/story.exp', self.extra), ('second/story.exp', variant)])
        with ContentLibrary(directory) as library:
            self.assertEqual(library.add_episodes([bundle]), 2)
            self.assertNotEqual(library.select(digest(self.extra))['id'], library.select(digest(variant))['id'])
            self.assertEqual(library.open_episode(digest(variant)).read_asset(26000), b'variant art')

    def test_bad_exp_or_catalog_rolls_back_initial_and_existing_imports(self):
        for game, source, encode in self.sources:
            for bad_catalog in (False, True):
                with self.subTest(source=source.name, bad_catalog=bad_catalog):
                    bad = (f'{game}_options.sav', b'bad catalog') if bad_catalog else ('zz-bad.exp', b'bad EXP')
                    bundle = write_zip(self.root / 'broken.zip', [('first.exp', self.extra), ('base-alias.exp', self.base), bad])
                    directory = self.root / f'{source.name}-{bad_catalog}'
                    with self.assertRaises(ContentError):
                        import_game(source, [bundle], directory)
                    self.assertFalse(directory.exists())
                    self.assertFalse(list(self.root.glob('.exp-import-*')))
                    import_game(source, [], directory)
                    with ContentLibrary(directory) as library:
                        session = Session(library.open_episode(library.episodes[0]['id']))
                        session.advance()
                        save = session.save()
                        saved = save.read_bytes()
                        manifest = (directory / 'library.json').read_bytes()
                        files = set((directory / 'content').iterdir())
                        with self.assertRaises(ContentError):
                            library.add_episodes([bundle])
                        self.assertEqual((directory / 'library.json').read_bytes(), manifest)
                        self.assertEqual(set((directory / 'content').iterdir()), files)
                        self.assertFalse(list(directory.glob('.exp-import-*')))
                        self.assertNotIn('aliases', library.episodes[0])
                        self.assertEqual(save.read_bytes(), saved)

    def test_invalid_empty_and_metadata_only_zips_report_content_errors(self):
        directory = self.root / 'library'
        import_game(self.sources[0][1], [], directory)
        bundle = self.root / 'bad.zip'
        with ContentLibrary(directory) as library:
            before = (directory / 'library.json').read_bytes()
            bundle.write_bytes(b'not a ZIP')
            with self.assertRaisesRegex(ContentError, 'Invalid episode ZIP'):
                library.add_episodes([bundle])
            for members in ([], [('__MACOSX/._a.exp', b'metadata')], [('nested.zip', b'not expanded')]):
                write_zip(bundle, members)
                with self.assertRaisesRegex(ContentError, 'No EXP episodes'):
                    library.add_episodes([bundle])
            self.assertEqual((directory / 'library.json').read_bytes(), before)

    def test_unsafe_member_paths_and_links_are_rejected_without_extraction(self):
        directory = self.root / 'library'
        import_game(self.sources[0][1], [], directory)
        link = ZipInfo('link.exp')
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        names = ('../escape.exp', '/absolute.exp', 'nested/../../escape.exp',
                 'C:\\escape.exp', '\\server\\escape.exp', link)
        with ContentLibrary(directory) as library:
            before = (directory / 'library.json').read_bytes()
            for name in names:
                with self.subTest(name=name):
                    bundle = write_zip(self.root / 'unsafe.zip', [(name, self.extra)])
                    with self.assertRaises(ContentError):
                        library.add_episodes([bundle])
                    self.assertEqual((directory / 'library.json').read_bytes(), before)
            self.assertFalse((self.root / 'escape.exp').exists())

    def test_duplicate_normalized_member_names_are_rejected(self):
        directory = self.root / 'library'
        import_game(self.sources[0][1], [], directory)
        with ContentLibrary(directory) as library:
            for duplicate in ('folder/story.exp', './folder/story.exp', 'folder\\story.exp'):
                with self.subTest(duplicate=duplicate), warnings.catch_warnings():
                    warnings.simplefilter('ignore', UserWarning)
                    bundle = write_zip(self.root / 'duplicate.zip', [('folder/story.exp', self.extra), (duplicate, self.base)])
                    with self.assertRaisesRegex(ContentError, 'duplicate member names'):
                        library.add_episodes([bundle])
            self.assertEqual(len(library.episodes), 1)

    def test_crc_encryption_and_unsupported_compression_fail_without_partial_imports(self):
        directory = self.root / 'library'
        import_game(self.sources[0][1], [], directory)
        bundle = self.root / 'broken.zip'
        with ContentLibrary(directory) as library:
            before = (directory / 'library.json').read_bytes()
            for failure in ('crc', 'encrypted', 'compression'):
                write_zip(bundle, [('first.exp', self.extra), ('last.exp', self.extra)], compression=ZIP_STORED)
                data = bytearray(bundle.read_bytes())
                if failure == 'crc':
                    with ZipFile(bundle) as package:
                        member = package.getinfo('last.exp')
                        offset = member.header_offset + 30 + len(member.filename)
                    data[offset] ^= 1
                else:
                    central = data.rfind(b'PK\x01\x02')
                    struct.pack_into('<H', data, central + (8 if failure == 'encrypted' else 10),
                                     1 if failure == 'encrypted' else 99)
                bundle.write_bytes(data)
                with self.subTest(failure=failure), self.assertRaisesRegex(ContentError, 'Cannot read ZIP member'):
                    library.add_episodes([bundle])
                self.assertEqual((directory / 'library.json').read_bytes(), before)
                self.assertFalse(list((directory / 'content').glob('*.exp')))

    def test_size_and_entry_limits_are_checked_before_member_reads(self):
        directory = self.root / 'library'
        import_game(self.sources[0][1], [], directory)
        bundle = write_zip(self.root / 'large.zip', [('story.exp', self.extra)])
        with ContentLibrary(directory) as library:
            for setting, value in (('MAX_EPISODE_ZIP_MEMBERS', 0), ('MAX_EPISODE_ZIP_BYTES', 1), ('MAX_PAYLOAD', 1)):
                with self.subTest(setting=setting), patch('exp_runtime.content.' + setting, value), \
                        patch.object(ZipFile, 'read', side_effect=AssertionError('Member was read before size validation')):
                    with self.assertRaises(ContentError):
                        library.add_episodes([bundle])
            write_zip(bundle, [('shs_options.sav', self.catalog(options))])
            with patch('exp_runtime.episode_catalog.MAX_CATALOG_BYTES', 1), \
                    patch.object(ZipFile, 'read', side_effect=AssertionError('Oversized catalog was read')):
                with self.assertRaises(ContentError):
                    library.add_episodes([bundle])

    def test_archive_handles_close_on_success_and_validation_failure(self):
        directory = self.root / 'library'
        import_game(self.sources[0][1], [], directory)
        bundle = self.root / 'episodes.zip'
        with ContentLibrary(directory) as library:
            for data in (self.extra, b'broken EXP'):
                write_zip(bundle, [('story.exp', data)])
                opened = []
                def open_zip(*args, **kwargs):
                    package = ZipFile(*args, **kwargs)
                    opened.append(package)
                    return package
                with patch('exp_runtime.content.ZipFile', side_effect=open_zip):
                    if data == self.extra:
                        self.assertEqual(library.add_episodes([bundle]), 1)
                    else:
                        with self.assertRaises(ContentError):
                            library.add_episodes([bundle])
                self.assertTrue(opened)
                self.assertTrue(all(package.fp is None for package in opened))


if __name__ == '__main__':
    unittest.main()
