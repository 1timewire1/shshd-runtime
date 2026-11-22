"""Authored RAR archives exercise the same atomic game import as ZIP/EXP."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from exp_runtime.content import ContentError, ContentLibrary, digest, import_game, _episode_inputs
from exp_runtime.rar import RarError
from exp_runtime.runtime import Session
from ios.probe.rar_fixture import rar4, rar5
from test_content import FAKE_NATIVE, archive, make_apk, metadata
from test_episode_catalog import cod_options, entry, options
from test_games import make_cod_ipa
from test_ipa import make_ipa
from test_vm import program


class EpisodeRarTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        native = patch('exp_runtime.shs.content.NATIVE_SHA256', digest(FAKE_NATIVE))
        native.start(); self.addCleanup(native.stop)
        self.base = archive({1: metadata('Base'), 25001: program(0x33).to_bytes()})
        self.extra = archive({1: metadata('RAR story'), 25001: program(0x33).to_bytes()})

    def test_rar4_and_rar5_import_catalogs_deduplicate_and_survive_source_removal(self):
        for make, encode in ((make_apk, options), (make_ipa, options), (make_cod_ipa, cod_options)):
            for pack in (rar4, rar5):
                with self.subTest(make=make.__name__, pack=pack.__name__):
                    game = 'cod' if make is make_cod_ipa else 'shs'
                    suffix = '.apk' if make is make_apk else '.ipa'
                    source = self.root / f'{make.__name__}-{pack.__name__}{suffix}'
                    make(source, self.base)
                    rar = self.root / 'episodes.RAR'
                    catalog = encode([entry(7, 2, 'RAR story', 'RAR Collection', 'story.EXP')])
                    rar.write_bytes(pack([('Episodes/nested/story.EXP', self.extra),
                                          ('Episodes/base.exp', self.base),
                                          (f'Episodes/{game}_options.sav', catalog),
                                          ('__MACOSX/._story.EXP', b'ignored')]))
                    raw = rar.read_bytes()
                    dest = self.root / f'{make.__name__}-{pack.__name__}-library'
                    manifest = import_game(source, [rar], dest, game=game)
                    self.assertEqual(len(manifest['episodes']), 2)
                    self.assertEqual(rar.read_bytes(), raw)
                    with ContentLibrary(dest) as lib:
                        s = Session(lib.open_episode('story.EXP')); s.advance()
                        saved = s.save(); before = saved.read_bytes()
                        self.assertEqual(lib.add_episodes([rar, rar]), 0)
                        self.assertEqual(lib.catalog.category(s.resources.record), 'RAR Collection')
                        self.assertEqual(saved.read_bytes(), before)
                    rar.unlink(); source.unlink()
                    with ContentLibrary(dest) as lib:
                        self.assertEqual(Session.load(lib.open_episode('story.EXP'), saved).pending.name, 'finished')
                    self.assertFalse((dest / 'Episodes').exists())

    def test_bad_members_abort_batch_and_temporary_staging_is_removed(self):
        source = self.root / 'base.apk'; make_apk(source, self.base)
        dest = self.root / 'library'; import_game(source, [], dest)
        for pack in (rar4, rar5):
            for bad in ('../bad.exp', '/bad.exp', 'C:\\bad.exp', 'bad.exp'):
                rar = self.root / 'bad.rar'
                rar.write_bytes(pack([('good.exp', self.extra), (bad, b'invalid EXP')]))
                with ContentLibrary(dest) as lib:
                    before = (dest / 'library.json').read_bytes()
                    files = set((dest / 'content').iterdir())
                    with self.assertRaises(ContentError):lib.add_episodes([rar])
                    self.assertEqual((dest / 'library.json').read_bytes(), before)
                    self.assertEqual(set((dest / 'content').iterdir()), files)
            rar.write_bytes(pack([('same.exp', self.extra), ('./same.exp', self.extra)]))
            with self.assertRaisesRegex(ContentError, 'duplicate'):
                with _episode_inputs([rar], game='shs'):pass
            rar.write_bytes(pack([('good.exp', self.extra)]))
            with _episode_inputs([rar], game='shs') as (items, _):
                staged = items[0].path
                self.assertTrue(staged.is_file())
            self.assertFalse(staged.exists())

    def test_truncation_size_limits_empty_and_invalid_archives(self):
        rar = self.root / 'bad.rar'
        for pack in (rar4, rar5):
            raw = pack([('good.exp', self.extra)])
            for data in (b'not a rar', raw[:-20], pack([('readme.txt', b'notes')])):
                rar.write_bytes(data)
                with self.assertRaises(ContentError):
                    with _episode_inputs([rar], game='shs'):pass
            rar.write_bytes(raw)
            # shshd-runtime: a member past MAX_PAYLOAD may be an add-on (streamed, refused at install if it isn't one), so
            # the members' bound here is MAX_ADDON_BYTES (test_large_addon_import.py).
            for key in ('MAX_ADDON_BYTES', 'MAX_EPISODE_ZIP_BYTES', 'MAX_EPISODE_ZIP_MEMBERS'):
                with patch('exp_runtime.content.' + key, 0), self.assertRaises(ContentError):
                    with _episode_inputs([rar], game='shs'):pass

    def test_missing_decoder_reports_a_useful_error_without_affecting_loose_exp_import(self):
        rar = self.root / 'story.rar'; rar.write_bytes(rar5([('story.exp', self.extra)]))
        with patch('exp_runtime.rar.library', side_effect=RarError('RAR decoder unavailable')):
            with self.assertRaisesRegex(ContentError, 'RAR decoder unavailable'):
                with _episode_inputs([rar], game='shs'):pass
            exp = self.root / 'story.exp'; exp.write_bytes(self.extra)
            with _episode_inputs([exp], game='shs') as (items, _):
                self.assertEqual(items[0].read_bytes(), self.extra)


if __name__ == '__main__':
    unittest.main()
