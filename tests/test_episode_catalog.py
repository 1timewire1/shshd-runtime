import importlib.util
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from exp_runtime.content import ContentError, ContentLibrary, ExpArchive, digest, import_game
from exp_runtime.episode_catalog import CatalogEntry, EpisodeCatalog, read_options_catalog
from exp_runtime.menu import group_episodes
from exp_runtime.runtime import Session
from test_content import FAKE_NATIVE, archive, make_apk, metadata
from test_games import make_cod_ipa
from test_ipa import make_ipa
from test_vm import program


SHS_EPISODE_FOLDERS = (Path('decomp/shs/Episodes'), Path('Episodes'))


def text(value):
    data = value.encode('utf-8') if isinstance(value, str) else value
    return struct.pack('>H', len(data)) + data


def entry(pack, episode, title, category, filename, translated=None):
    titles = [title, translated or title, title, title, title]
    return (struct.pack('>BHH', 1, pack, episode)
            + b''.join(text(s) for s in [*titles, *([category] * 5), filename]) + struct.pack('>i', -1))


def options(entries, *, prefix=32, version=18):
    header = b'SHS_OPTIONS\0' + struct.pack('>ii', version, 0) + bytes(prefix - 20)
    # Current episode is absent. Native runtime strings are deliberately
    # present to check that only catalog metadata reaches the new library.
    return (header + b'\0' + struct.pack('>i', len(entries)) + b''.join(entries)
            + struct.pack('>h', 1) + text('$PLAYER') + text('Private player name')
            + bytes([1] * (version - 16)))


def cod_options(entries, *, current=b'\0'):
    # CoD 1.3.4 writes five preference flags and two integers after version
    # and the discarded integer. There are no flags after the rename table.
    header = b'SHS_OPTIONS\0' + struct.pack('>ii5Bii', 17, 0, 1, 0, 1, 0, 1, 37, 63)
    return (header + current + struct.pack('>i', len(entries)) + b''.join(entries)
            + struct.pack('>h', 1) + text('$PLAYER') + text('Private player name'))


def record(identity, pack, episode, title, name='story.exp'):
    return dict(id=f'{identity:064x}', pack_id=pack, episode_id=episode,
                titles=[title] * 5, name=name)


class CatalogTests(unittest.TestCase):
    def test_cod_reads_current_and_downloaded_entries_without_shs_trailing_flags(self):
        first = entry(101, 3, 'First', 'Volume Three', 'folder/first.exp', b'Caf\xe9')
        second = entry(101, 4, 'Second', 'Volume Four', 'second.exp')
        catalog = read_options_catalog(cod_options([first, b'\0', second], current=first), game='cod')
        self.assertEqual([e.category for e in catalog.entries], ['Volume Three', 'Volume Four'])
        self.assertEqual(catalog.category(record(1, 101, 4, 'Second', 'renamed.exp')), 'Volume Four')
        self.assertNotIn('Private player name', json.dumps(catalog.to_data()))
        self.assertEqual(EpisodeCatalog.from_data(catalog.to_data()).entries, catalog.entries)

    def test_cod_rejects_corruption_and_other_games_envelopes(self):
        good = cod_options([entry(101, 3, 'First', 'Volume Three', 'first.exp')])
        bad_count, bad_presence, bad_string = bytearray(good), bytearray(good), bytearray(good)
        struct.pack_into('>i', bad_count, 34, 4097)
        bad_presence[33] = 2
        struct.pack_into('>H', bad_string, 43, 32768)
        bad_pairs = bytearray(cod_options([]))
        struct.pack_into('>h', bad_pairs, 38, -1)
        corruptions = [good[:length] for length in (0, 12, 16, 33, 38, len(good) - 1)]
        corruptions += [good + b'\0', b'prefix' + good, bytes(bad_count), bytes(bad_presence),
                        bytes(bad_string), bytes(bad_pairs), options([]), options([], version=17)]
        for version in (16, 18, 19):
            corruptions.append(good[:12] + struct.pack('>i', version) + good[16:])
        for data in corruptions:
            with self.subTest(data=data[:40]), self.assertRaises(ContentError):
                read_options_catalog(data, game='cod')
        with self.assertRaises(ContentError):
            read_options_catalog(good, game='shs')
        with self.assertRaisesRegex(ContentError, 'Unknown catalog game'):
            read_options_catalog(good, game='unknown')

    def test_reads_native_sections_from_both_validated_prefixes(self):
        entries = [entry(301, 57, 'First', 'Season Three', 'one.exp', b'Caf\xe9'),
                   entry(301, 58, 'Second', 'Season Four', 'two.exp')]
        for prefix in (32, 36):
            for version in (16, 17, 18):
                with self.subTest(prefix=prefix, version=version):
                    catalog = read_options_catalog(options(entries, prefix=prefix, version=version))
                    self.assertEqual([e.category for e in catalog.entries], ['Season Three', 'Season Four'])
                    self.assertEqual(catalog.category(record(1, 301, 58, 'Second', 'renamed.exp')), 'Season Four')
                    serialized = catalog.to_data()
                    self.assertNotIn('Private player name', json.dumps(serialized))
                    self.assertEqual(EpisodeCatalog.from_data(serialized).entries, catalog.entries)

    def test_invalid_catalog_does_not_accept_partial_records_or_scan_for_magic(self):
        good = options([entry(1, 2, 'Story', 'Chapter Set', 'story.exp')])
        bad_count = bytearray(good)
        struct.pack_into('>i', bad_count, 33, 1000000)
        invalid_string = bytearray(good)
        struct.pack_into('>H', invalid_string, 42, 32768)
        corruptions = [good[:length] for length in (0, 12, 32, 37, len(good) - 1)]
        corruptions += [good + b'junk', b'prefix' + good, bytes(bad_count), bytes(invalid_string),
                        options([], version=19), good[:-1] + b'\x02']
        for data in corruptions:
            with self.subTest(size=len(data)), self.assertRaises(ContentError):
                read_options_catalog(data)
        for data in ({}, [dict(pack_id=True, episode_id=2, title='x', category='a', filename='x')], [None]):
            with self.assertRaises(ContentError):
                EpisodeCatalog.from_data(data)

    def test_filename_matches_native_alias_ids_and_conflicting_categories_stay_unknown(self):
        catalog = EpisodeCatalog([
            CatalogEntry(3737, 3737, 'Catalog Title', 'Novel Group', 'Assets/novel.exp'),
            CatalogEntry(1, 2, 'Shared Title', 'First Set', 'a.exp'),
            CatalogEntry(1, 2, 'Shared Title', 'Second Set', 'b.exp')])
        self.assertEqual(catalog.category(record(1, 7, 230, 'Embedded Title', 'NOVEL.EXP')), 'Novel Group')
        self.assertEqual(catalog.category(record(2, 1, 2, 'Shared Title', 'b.exp')), 'Second Set')
        self.assertIsNone(catalog.category(record(3, 1, 2, 'Shared Title', 'renamed.exp')))
        self.assertIsNone(catalog.category(record(4, 1, 3, 'Another Title')))

    def test_grouping_uses_catalog_and_keeps_saves_as_shortcuts(self):
        records = [record(1, 301, 57, 'Before'), record(2, 301, 58, 'After'),
                   record(3, 501, 1, 'Unknown')]
        catalog = EpisodeCatalog([CatalogEntry(301, 57, 'Before', 'Season Three', 'a.exp'),
                                  CatalogEntry(301, 58, 'After', 'Season Four', 'b.exp')])
        sections = group_episodes(records, catalog, mega_label='Included Stories', novel_label='Novel',
                                  saved_label='Saved Games', saved={records[1]['id']})
        self.assertEqual([s.title for s in sections], ['Saved Games', 'Season Three', 'Season Four', 'Pack 501'])
        self.assertEqual(sections[0].episodes, (records[1],))
        self.assertEqual(sections[2].episodes, (records[1],))
        self.assertEqual(sum(len(s.episodes) for s in sections[1:]), len(records))

    def test_duplicate_filename_aliases_match_synthetic_catalog_ids_without_guessing(self):
        catalog = EpisodeCatalog([CatalogEntry(9, 1, 'Catalog title', 'Original Group', 'original.exp'),
                                  CatalogEntry(9, 2, 'Other title', 'Other Group', 'other.exp')])
        episode = record(1, 7, 3, 'Embedded title', 'renamed.exp')
        self.assertIsNone(catalog.category(episode))
        episode['aliases'] = ['ORIGINAL.EXP']
        self.assertEqual(catalog.category(episode), 'Original Group')
        episode['aliases'].append('other.exp')
        self.assertIsNone(catalog.category(episode))

    @unittest.skipUnless(Path('decomp/cod/CoD Episodes/cod_options.sav').is_file(),
                         'original user CoD catalog is unavailable')
    def test_original_cod_catalog_and_available_corpus(self):
        folder = Path('decomp/cod/CoD Episodes')
        catalog = read_options_catalog((folder / 'cod_options.sav').read_bytes(), game='cod')
        self.assertEqual(len(catalog.entries), 80)
        self.assertIn('VOLUME ONE', {e.category for e in catalog.entries})
        episodes = {}
        for path in sorted(folder.glob('*.exp')):
            data = path.read_bytes()
            meta = ExpArchive(data).metadata()
            episodes.setdefault(digest(data), record(0, meta.pack_id, meta.episode_id, meta.title, path.name))
        if episodes:
            self.assertEqual(len(episodes), 80)
            unmatched = [e['name'] for e in episodes.values() if catalog.category(e) is None]
            self.assertEqual(unmatched, ['12_Fallon_Family_Christmas.exp'])

    @unittest.skipUnless(any((folder / 'shs_options.sav').is_file() for folder in SHS_EPISODE_FOLDERS),
                         'original user catalog is unavailable')
    def test_original_catalog_covers_local_corpus_and_crosses_pack_boundary(self):
        folder = next(p for p in SHS_EPISODE_FOLDERS if (p / 'shs_options.sav').is_file())
        catalog = read_options_catalog((folder / 'shs_options.sav').read_bytes(), game='shs')
        self.assertEqual(len(catalog.entries), 274)
        paths = sorted(p for p in folder.rglob('*') if p.is_file() and p.suffix.lower() == '.exp')
        if not paths:
            self.skipTest('original user SHS episodes are unavailable')
        episodes = []
        for index, path in enumerate(paths):
            meta = ExpArchive(path.read_bytes()).metadata()
            episode = record(index, meta.pack_id, meta.episode_id, meta.title, path.name)
            self.assertIsNotNone(catalog.category(episode), path.name)
            episodes.append(episode)
        a = next(e for e in episodes if (e['pack_id'], e['episode_id']) == (301, 57))
        b = next(e for e in episodes if (e['pack_id'], e['episode_id']) == (301, 58))
        self.assertEqual(catalog.category(a), 'SEASON 3')
        self.assertEqual(catalog.category(b), 'SEASON 4')


class CatalogImportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        profile = patch('exp_runtime.shs.content.NATIVE_SHA256', digest(FAKE_NATIVE))
        profile.start()
        self.addCleanup(profile.stop)
        self.episode = archive({1: metadata('Test Story'), 25001: program(0x33).to_bytes()})
        self.apk = self.root / 'input.apk'
        make_apk(self.apk, self.episode)
        self.folder = self.root / 'episodes'
        self.folder.mkdir()
        (self.folder / 'story.exp').write_bytes(self.episode)
        meta = ExpArchive(self.episode).metadata()
        self.options = options([entry(meta.pack_id, meta.episode_id, meta.title, 'Original Section', 'story.exp')])
        (self.folder / 'shs_options.sav').write_bytes(self.options)

    def test_folder_import_and_later_catalog_only_import_persist_without_affecting_identity(self):
        first, second = self.root / 'first', self.root / 'second'
        import_game(self.apk, [self.folder], first)
        import_game(self.apk, [], second)
        with ContentLibrary(second) as library:
            resources = library.open_episode('Test Story')
            identity = resources.identity
            self.assertEqual(library.add_episodes([self.folder / 'shs_options.sav']), 0)
            self.assertEqual(resources.identity, identity)
            manifest = (second / 'library.json').read_bytes()
            self.assertEqual(library.add_episodes([self.folder / 'story.exp']), 0)
            self.assertIn('story.exp', library.episodes[0]['aliases'])
            self.assertNotEqual((second / 'library.json').read_bytes(), manifest)
            manifest = (second / 'library.json').read_bytes()
            self.assertEqual(library.add_episodes([self.folder / 'story.exp']), 0)
            self.assertEqual((second / 'library.json').read_bytes(), manifest)
        for directory in (first, second):
            with ContentLibrary(directory) as reopened:
                self.assertEqual(reopened.catalog.category(reopened.episodes[0]), 'Original Section')
                self.assertNotIn('Private player name', (directory / 'library.json').read_text())
                self.assertFalse((directory / 'shs_options.sav').exists())
        self.assertEqual((self.folder / 'shs_options.sav').read_bytes(), self.options)

    def test_failed_batch_publishes_neither_catalog_nor_episode(self):
        directory = self.root / 'library'
        import_game(self.apk, [], directory)
        with ContentLibrary(directory) as library:
            before = (directory / 'library.json').read_bytes()
            bad = self.folder / 'bad.exp'
            bad.write_bytes(b'corrupt')
            with self.assertRaises(ContentError):
                library.add_episodes([self.folder])
            self.assertFalse(library.catalog.entries)
            self.assertEqual((directory / 'library.json').read_bytes(), before)
            bad.unlink()
            (self.folder / 'shs_options.sav').write_bytes(self.options[:-1])
            with self.assertRaises(ContentError):
                library.add_episodes([self.folder / 'story.exp'])
            self.assertEqual((directory / 'library.json').read_bytes(), before)


class GameCatalogImportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        native = patch('exp_runtime.shs.content.NATIVE_SHA256', digest(FAKE_NATIVE))
        native.start()
        self.addCleanup(native.stop)
        self.base = archive({1: metadata('Bundled Story'), 25001: program(0x33).to_bytes()})
        self.extra = archive({1: metadata('Additional Story'), 25001: program(0x33).to_bytes()})
        self.sources = [('shs', self.root / 'shs.apk', options),
                        ('shs', self.root / 'shs.ipa', options),
                        ('cod', self.root / 'cod.ipa', cod_options)]
        for (_, path, _), make in zip(self.sources, (make_apk, make_ipa, make_cod_ipa)):
            make(path, self.base)

    def test_initial_and_repeated_imports_deduplicate_copies_and_preserve_saves_for_both_games(self):
        for game, source, encode in self.sources:
            with self.subTest(source=source.name):
                folder = self.root / (source.name + '-case') / 'episodes'
                folder.mkdir(parents=True)
                (folder / 'base-original.exp').write_bytes(self.base)
                (folder / 'next.exp').write_bytes(self.extra)
                (folder / 'another-copy.EXP').write_bytes(self.extra)
                sidecar = folder / f'{game}_options.sav'
                sidecar.write_bytes(encode([
                    entry(900, 1, 'Native catalog name', 'First Collection', 'base-original.exp'),
                    entry(7, 2, 'Additional Story', 'Next Collection', 'next.exp')]))
                # A mixed folder's foreign catalog must not supply labels or
                # cause this game's valid import to fail.
                (folder / ('cod_options.sav' if game == 'shs' else 'shs_options.sav')).write_bytes(b'foreign')
                directory = folder.parent / 'library'
                manifest = import_game(source, [folder, folder / 'next.exp'], directory)
                self.assertEqual(len(manifest['episodes']), 2)
                with ContentLibrary(directory) as library:
                    base = library.open_episode('base-original.exp')
                    extra = library.open_episode('next.exp')
                    self.assertEqual(library.select('another-copy.EXP')['id'], extra.record['id'])
                    self.assertEqual(library.catalog.category(base.record), 'First Collection')
                    session = Session(extra); session.advance()
                    saved = session.save()
                    snapshot, save_bytes = session.snapshot(), saved.read_bytes()
                    identity = extra.identity
                    before = (directory / 'library.json').read_bytes()
                    contents = set((directory / 'content').iterdir())
                    self.assertEqual(library.add_episodes([folder, folder / 'next.exp', sidecar]), 0)
                    self.assertEqual(library.ensure_builtin_episodes(), 0)
                    self.assertEqual((directory / 'library.json').read_bytes(), before)
                    self.assertEqual(set((directory / 'content').iterdir()), contents)
                    self.assertEqual(saved.read_bytes(), save_bytes)
                    self.assertEqual(extra.identity, identity)
                    self.assertEqual(Session.from_snapshot(extra, snapshot).snapshot(), snapshot)
                with ContentLibrary(directory) as reopened:
                    self.assertEqual(len(reopened.episodes), 2)
                    self.assertEqual(len(reopened.catalog.entries), 2)

    def test_late_catalog_and_renamed_duplicate_update_only_metadata_atomically(self):
        for game, source, encode in self.sources:
            with self.subTest(source=source.name):
                folder = self.root / (source.name + '-case')
                folder.mkdir()
                renamed = folder / 'renamed.exp'
                renamed.write_bytes(self.extra)
                directory = folder / 'library'
                import_game(source, [renamed], directory)
                original = folder / 'original.exp'
                original.write_bytes(self.extra)
                sidecar = folder / f'{game.upper()}_OPTIONS.SAV'
                sidecar.write_bytes(encode([entry(800, 12, 'Catalog title', 'Native Category', original.name)]))
                with ContentLibrary(directory) as library:
                    resources = library.open_episode(renamed.name)
                    session = Session(resources); session.advance()
                    saved = session.save(); save_bytes = saved.read_bytes()
                    before = (directory / 'library.json').read_bytes()
                    bad = folder / 'bad.exp'; bad.write_bytes(b'corrupt')
                    with self.assertRaises(ContentError):
                        library.add_episodes([original, bad])
                    self.assertEqual((directory / 'library.json').read_bytes(), before)
                    self.assertNotIn('aliases', library.select(renamed.name))
                    self.assertFalse(library.catalog.entries)
                    bad.unlink()
                    # A duplicate alone discovers the sibling catalog too.
                    self.assertEqual(library.add_episodes([original]), 0)
                    episode = library.select(original.name)
                    self.assertEqual(episode['id'], resources.record['id'])
                    self.assertEqual(episode['name'], renamed.name)
                    self.assertEqual(library.catalog.category(episode), 'Native Category')
                    self.assertEqual(saved.read_bytes(), save_bytes)
                    before = (directory / 'library.json').read_bytes()
                    self.assertEqual(library.add_episodes([sidecar]), 0)
                    self.assertEqual((directory / 'library.json').read_bytes(), before)
                    # Identical metadata does not justify dropping different
                    # scripts or assets, or replacing the existing saved edition.
                    variant = folder / 'variant.exp'
                    variant.write_bytes(archive({1: metadata('Additional Story'),
                                                 25001: program(0x33).to_bytes(), 26000: b'other art'}))
                    self.assertEqual(library.add_episodes([variant]), 1)
                    self.assertNotEqual(library.select(variant.name)['id'], episode['id'])
                    self.assertEqual(saved.read_bytes(), save_bytes)

    def test_wrong_catalog_and_corrupt_catalog_are_rejected_without_partial_imports(self):
        for game, source, encode in self.sources:
            with self.subTest(source=source.name):
                folder = self.root / (source.name + '-case')
                folder.mkdir()
                sidecar = folder / f'{game}_options.sav'
                sidecar.write_bytes(encode([entry(7, 2, 'Additional Story', 'Category', 'new.exp')])[:-1])
                episode = folder / 'new.exp'; episode.write_bytes(self.extra)
                directory = folder / 'library'
                with self.assertRaises(ContentError):
                    import_game(source, [folder], directory)
                self.assertFalse(directory.exists())
                import_game(source, [], directory)
                foreign = folder / ('cod_options.sav' if game == 'shs' else 'shs_options.sav')
                foreign.write_bytes(cod_options([]) if game == 'shs' else options([]))
                with ContentLibrary(directory) as library:
                    before = (directory / 'library.json').read_bytes()
                    for paths in ([episode], [sidecar], [foreign]):
                        with self.assertRaises(ContentError):
                            library.add_episodes(paths)
                        self.assertEqual((directory / 'library.json').read_bytes(), before)
                        self.assertEqual(len(library.episodes), 1)

    @unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is unavailable')
    def test_episode_picker_shows_the_selected_games_catalog(self):
        from exp_runtime.application import Application
        (self.root / 'shs_options.sav').write_bytes(options([]))
        (self.root / 'COD_OPTIONS.SAV').write_bytes(cod_options([]))
        with patch.dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy'):
            for game in ('shs', 'cod'):
                app = Application(self.root / 'absent-library', audio=False, game_key=game, check_updates=False)
                try:
                    app.browser_kind = 'episodes'
                    app.read_folder(self.root)
                    names = {p.name.casefold() for p in app.files if p.is_file()}
                    self.assertEqual(names, {f'{game}_options.sav'})
                finally:
                    app.close()


@unittest.skipUnless(importlib.util.find_spec('pygame') and Path('.shs-library/library.json').is_file(),
                     'desktop extra or user artwork is unavailable')
class CatalogBrowserTests(unittest.TestCase):
    def test_collapse_search_navigation_and_scrolled_hit_targets(self):
        import pygame
        from exp_runtime.application import Application
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        with tempfile.TemporaryDirectory() as directory:
            root, source = Path(directory), Path('.shs-library').resolve()
            (root / 'library.json').write_bytes((source / 'library.json').read_bytes())
            (root / 'content').symlink_to(source / 'content', target_is_directory=True)
            app = Application(root, audio=False, check_updates=False)
            self.addCleanup(app.close)
            app.library.catalog = EpisodeCatalog()
            app.query = app.renderer.strings[82]  # APK-derived category, no options sidecar.
            self.assertIn(app.library.select('footballseason')['id'], [e['id'] for e in app.visible_episodes()])
            app.query = ''
            template = app.library.episodes[0]
            records = [dict(template, **record(i + 1, 301, i + 1, f'Story {i:02}', f'{i}.exp')) for i in range(20)]
            app.library.episodes = records
            app.library.catalog = EpisodeCatalog(CatalogEntry(301, i + 1, f'Story {i:02}',
                                                             'First Season' if i < 10 else 'Second Season',
                                                             f'{i}.exp') for i in range(20))
            app.show('episodes')
            app.scope = 'all'
            app.tick(1550)
            app.render()
            headers = [(rect, cmd) for rect, cmd in app.buttons if cmd[0] == 'episode_group']
            self.assertEqual(len(headers), 2)
            self.assertFalse([cmd for _, cmd in app.buttons if cmd[0] == 'episode'])
            app.command(headers[1][1])
            app.render()
            self.assertEqual([cmd for _, cmd in app.buttons if cmd[0] == 'episode'][0], ('episode', records[10]['id']))
            app._scroll(140)
            app.render()
            row_rect, row_command = next((r, c) for r, c in app.buttons if c[0] == 'episode')
            self.assertGreaterEqual(row_rect.top, 150)
            scroll = app.scroll
            point = (app.viewport.x + row_rect.centerx * app.viewport.width / 320,
                     app.viewport.y + row_rect.centery * app.viewport.height / 480)
            for type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
                app.handle_event(pygame.event.Event(type, button=1, pos=point))
            self.assertEqual(app.screen, 'episode')
            self.assertEqual(app.selected, row_command[1])
            app.back()
            self.assertEqual(app.scroll, scroll)
            self.assertIn('category:second season', app.expanded_groups)
            app.command(('search',))
            app.tick(200)
            app.handle_event(pygame.event.Event(pygame.TEXTINPUT, text='First Season'))
            app.render()
            self.assertEqual(len(app.visible_episodes()), 10)
            self.assertTrue([c for _, c in app.buttons if c[0] == 'episode'])
            self.assertNotIn('category:first season', app.expanded_groups)
            app.command(('clear_search',))
            self.assertEqual(len(app.visible_episodes()), 20)
            app.command(('episode_groups',))
            self.assertTrue({'category:first season', 'category:second season'} <= app.expanded_groups)
            app.command(('episode_groups',))
            self.assertFalse(app.episode_rows()[0][0][3])
            self.assertEqual(len(app.episode_rows()[0]), 2)


if __name__ == '__main__':
    unittest.main()
