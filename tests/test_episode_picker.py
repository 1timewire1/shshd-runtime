from io import BytesIO
import json
from types import SimpleNamespace
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

import pygame

from exp_runtime import episode_thumbnails
from exp_runtime.content import ContentLibrary, digest, import_game
from exp_runtime.desktop_episode_picker import HdEpisodePicker, ROW_HEIGHT, TILE_STEP, TILE_X
from exp_runtime.episode_catalog import CatalogEntry, EpisodeCatalog
from exp_runtime.episode_picker import PickerModel, TILE_PIXELS
from test_content import FAKE_NATIVE, archive, make_apk
from test_episode_index import png, record
from test_vm import program

BUNDLE = 'Payload/Surviving_HS.app/'


def picture(size, color):
    surface = pygame.Surface(size)
    surface.fill(color)
    stream = BytesIO()
    pygame.image.save(surface, stream, 'x.png')
    return stream.getvalue()


def meta(pack, episode, title):
    result = struct.pack('>HH', pack, episode)
    for _ in range(5):
        data = title.encode()
        result += struct.pack('>H', len(data)) + data
    return result


class FakeLibrary:
    def __init__(self, directory, episodes, catalog=None, ipa=None):
        self.directory, self.episodes = Path(directory), episodes
        self.catalog = catalog or EpisodeCatalog()
        self.hd_ipa = ipa
        self.hd_members = {}
        self.hd_art_mode = 'off'
        self._twins = None

    def twin_store(self):
        from exp_runtime.hd_twins import TwinStore
        if self._twins is None:
            self._twins = TwinStore(self.directory)
        return self._twins


def library_with(root, episodes, catalog=None, previews=None):
    ipa = None
    if previews is not None:
        stream = BytesIO()
        with ZipFile(stream, 'w') as archive_:
            for name, data in previews.items():
                archive_.writestr(BUNDLE + name, data)
        ipa = ZipFile(stream)          # in memory: nothing to keep open on disk
    return FakeLibrary(root, episodes, catalog, ipa)



class ModelTests(unittest.TestCase):
    def setUp(self):
        pygame.display.init()
        pygame.display.set_mode((1, 1))
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_duplicates_are_hidden_in_favour_of_the_hd_release_and_standard_episodes_are_marked(self):
        hd = record(1, 101, 1, 'Making Some Dough', variant='hd')
        twin = record(2, 101, 1, 'Making Some Dough', variant='standard')
        lone = record(3, 101, 2, 'Only Standard', variant='standard')
        catalog = EpisodeCatalog([CatalogEntry(101, 1, 'Making Some Dough', 'SEASON 1', '', 'hd')])
        model = PickerModel(library_with(self.root, [hd, twin, lone], catalog, previews={}))
        self.assertEqual({r['id'] for r in model.records}, {hd['id'], lone['id']})
        self.assertEqual([row.title for row in model.rows], ['Season 1'])
        self.assertFalse(model.is_standard(hd))
        self.assertTrue(model.is_standard(lone))
        self.assertEqual(model.position[lone['id']], (0, 1))

    def test_a_translated_episode_shows_its_games_tag_beside_its_twin(self):
        # shs profile LEGACY_GAMES: a New Rules translation (tagged on import) shows "NR" in New Rules' blue in place
        # of "SD", under its own category, and beside its smartphone twin rather than hidden as its copy.
        from exp_runtime.shs.profile import LEGACY_GAMES
        hd = record(1, 101, 1, 'Making Some Dough', variant='hd')
        lone = record(3, 101, 2, 'Only Standard', variant='standard')
        translated = dict(record(4, 31300, 2, 'Making Some Dough', variant='standard'), legacy='SHSNR',
                          category='New Rules')
        catalog = EpisodeCatalog([CatalogEntry(101, 1, 'Making Some Dough', 'SEASON 1', '', 'hd')])
        model = PickerModel(library_with(self.root, [hd, lone, translated], catalog, previews={}))
        self.assertIn(translated['id'], {r['id'] for r in model.records})
        self.assertEqual([model.mark(r) for r in (hd, lone, translated)], [None, 'SD', 'NR'])
        self.assertEqual([model.mark_color(r) for r in (lone, translated)], [None, LEGACY_GAMES['SHSNR']['color']])
        self.assertIn('New Rules', [row.title for row in model.rows])

    def test_chronological_mode_groups_by_year_instead_of_category(self):
        early = record(1, 101, 1, 'Early One', variant='hd')
        later = record(2, 201, 1, 'Later One', variant='hd')
        bundle = record(3, 1401, 1, 'A Redundant Bundle', variant='hd')
        catalog = EpisodeCatalog([CatalogEntry(101, 1, 'Early One', 'SEASON 1', '', 'hd'),
                                  CatalogEntry(201, 1, 'Later One', 'SEASON 2', '', 'hd')])
        dates = {'Early One': '2010-01-01', 'Later One': '2011-06-01', 'A Redundant Bundle': '2011-01-01'}
        with patch('exp_runtime.episode_picker.RELEASE_DATES', dates), \
             patch('exp_runtime.episode_picker.REDUNDANT_BUNDLES', frozenset({'A Redundant Bundle'})), \
             patch('exp_runtime.episode_picker.VOTE_PACKAGES', frozenset()):
            model = PickerModel(library_with(self.root, [early, later, bundle], catalog, previews={}),
                                chronological=True)
        self.assertTrue(model.chronological)
        self.assertEqual([row.title for row in model.rows], ['2010', '2011', 'Season Bundles'])

    def test_subtitle_names_the_category_only_in_chronological_mode(self):
        early = record(1, 101, 1, 'Early One', variant='hd')
        undated = record(2, 201, 1, 'No Date Yet', variant='hd')
        catalog = EpisodeCatalog([CatalogEntry(101, 1, 'Early One', 'SEASON 1', '', 'hd'),
                                  CatalogEntry(201, 1, 'No Date Yet', 'SEASON 2', '', 'hd')])
        dates = {'Early One': '2010-01-22'}
        library = library_with(self.root, [early, undated], catalog, previews={})
        with patch('exp_runtime.episode_picker.RELEASE_DATES', dates), \
             patch('exp_runtime.episode_picker.REDUNDANT_BUNDLES', frozenset()), \
             patch('exp_runtime.episode_picker.VOTE_PACKAGES', frozenset()):
            chronological = PickerModel(library, chronological=True)
            self.assertEqual(chronological.subtitle(early), 'SEASON 1 - Airdate: 01/22/2010')
            self.assertEqual(chronological.subtitle(undated), 'SEASON 2')     # no date: category alone
        categorized = PickerModel(library)
        with patch('exp_runtime.episode_picker.RELEASE_DATES', dates):
            self.assertEqual(categorized.subtitle(early), 'Airdate: 01/22/2010')     # no category, redundant
            self.assertIsNone(categorized.subtitle(undated))                         # no date at all

    def test_without_an_hd_bundle_the_standard_release_shows_and_nothing_is_marked(self):
        hd = record(1, 101, 1, 'Making Some Dough', variant='hd')
        twin = record(2, 101, 1, 'Making Some Dough', variant='standard')
        model = PickerModel(library_with(self.root, [hd, twin]))
        self.assertEqual([r['id'] for r in model.records], [twin['id']])
        self.assertFalse(model.is_standard(twin))

    def test_only_standard_episodes_next_to_an_hd_bundle_get_no_marker(self):
        only = record(1, 101, 1, 'Plain', variant='standard')
        model = PickerModel(library_with(self.root, [only], previews={}))
        self.assertFalse(model.is_standard(only))

    def test_with_hd_art_on_full_coverage_drops_the_marker_but_partial_or_unmeasured_keeps_it(self):
        hd = record(1, 101, 1, 'Making Some Dough', variant='hd')
        full = record(2, 101, 2, 'Fully Covered', variant='standard')
        partial = record(3, 101, 3, 'Partially Covered', variant='standard')
        unmeasured = record(4, 101, 4, 'Unmeasured', variant='standard')
        library = library_with(self.root, [hd, full, partial, unmeasured], previews={})
        library.hd_art_mode = 'twins'
        library.twin_store().write_coverage({
            full['id']: {'total': 5, 'matched': 5},
            partial['id']: {'total': 5, 'matched': 4},
        })
        model = PickerModel(library)
        self.assertFalse(model.is_standard(full))
        self.assertTrue(model.is_standard(partial))
        self.assertTrue(model.is_standard(unmeasured))

    def test_apk_bundled_episodes_are_never_marked_standard(self):
        bundled = dict(record(1, 5, 9, 'Football Star', variant='standard'), builtin='football-star', file='content/x.exp')
        hd = record(2, 101, 1, 'HD one', variant='hd')
        model = PickerModel(library_with(self.root, [bundled, hd], previews={}))
        self.assertFalse(model.is_standard(bundled))

    def test_preview_prefers_the_bundle_then_the_generated_card_then_the_placeholder(self):
        episode = record(1, 401, 24, 'Typo id')
        library = library_with(self.root, [episode], previews={
            'preview_401_64.jpg': picture((216, 290), (200, 0, 0)),
            episode_thumbnails.MISSING: picture((216, 290), (0, 0, 200))})
        model = PickerModel(library)
        self.assertEqual(model.preview(episode).get_size(), TILE_PIXELS)
        self.assertEqual(model.preview(episode).get_at((5, 5))[:3], (200, 0, 0))
        # Without a bundled preview a cached card wins, and without that the placeholder.
        other = record(2, 5, 5, 'Nothing bundled')
        model = PickerModel(library_with(self.root, [other], previews={episode_thumbnails.MISSING: picture((216, 290), (0, 0, 200))}))
        self.assertEqual(model.preview(other).get_at((5, 5))[:3], (0, 0, 200))
        path = episode_thumbnails.thumbnail_path(model.library, other)
        path.parent.mkdir(parents=True)
        path.write_bytes(picture((432, 580), (0, 200, 0)))
        model.forget_preview(other['id'])
        self.assertEqual(model.preview(other).get_at((5, 5))[:3], (0, 200, 0))

    def test_a_flat_card_stands_in_when_nothing_else_exists(self):
        lone = record(1, 5, 5, 'Nothing')
        model = PickerModel(library_with(self.root, [lone]))
        self.assertEqual(model.preview(lone).get_size(), TILE_PIXELS)

    def test_missing_records_skips_bundled_cached_and_already_failed_episodes(self):
        bundled, cached, failed, todo = (record(i, 101, i, f'T{i}') for i in range(1, 5))
        library = library_with(self.root, [bundled, cached, failed, todo], previews={'preview_101_1.jpg': picture((4, 4), (1, 1, 1))})
        thumbs = self.root / 'thumbs'
        thumbs.mkdir()
        (thumbs / f'{cached["id"]}.jpg').write_bytes(b'x')
        (thumbs / f'{failed["id"]}.none').write_bytes(episode_thumbnails.MARKER)
        self.assertEqual(episode_thumbnails.missing_records(library, library.episodes), [todo])


class FakeSession:
    """Serves a fixed list of pending actions; each answer moves to the next one."""
    transitioning = False

    def __init__(self, *names):
        self.queue = [SimpleNamespace(name=name, details=dict(enabled=[False, True, True])) for name in names]
        self.pending = None
        self.answers, self.ticks, self.skips = [], [], []
        self.engine = SimpleNamespace(dialogue_animation=SimpleNamespace(complete=True))

    def advance(self):
        self.pending = self.queue.pop(0) if self.queue else None

    def answer(self, value=None):
        self.answers.append(value)
        self.advance()

    def skip_minigame(self, success):
        self.skips.append((self.pending.name, success))
        self.advance()

    def tick(self, milliseconds):
        self.ticks.append(milliseconds)
        if self.pending.name == 'loading':
            self.advance()


class PreviewMemoryTests(unittest.TestCase):
    def test_each_preview_leaves_the_renderers_method_caches(self):
        """A preview runs a whole episode view; a class-level method cache keeps every renderer it saw with that
        episode's art (~40 MB an episode, until Android stopped the first-time setup at ~3 GB). Their instance
        methods' caches empty after each preview; a static method's or a module function's stay."""
        import functools
        import sys
        import types
        module = types.ModuleType('exp_runtime.preview_memory_probe')

        class Renderer:
            @functools.lru_cache(maxsize=None)
            def art(self, key):
                return bytearray(16)

            @staticmethod
            @functools.lru_cache(maxsize=None)
            def font(size):
                return size

        Renderer.__module__ = module.__name__
        module.Renderer = Renderer
        module.table = functools.lru_cache(maxsize=None)(lambda key: key)
        sys.modules[module.__name__] = module
        self.addCleanup(sys.modules.pop, module.__name__)
        Renderer().art(1)
        Renderer.font(12)
        module.table(3)
        kept = types.ModuleType('exp_runtime.platforms.test_host')

        class Fonts:
            @functools.lru_cache(maxsize=None)
            def measure(self, text):
                return len(text)

        Fonts.__module__ = kept.__name__
        kept.Fonts = Fonts
        sys.modules[kept.__name__] = kept
        self.addCleanup(sys.modules.pop, kept.__name__)
        Fonts().measure('Mg')
        episode_thumbnails.release_episode_caches()
        self.assertEqual(Renderer.art.cache_info().currsize, 0)
        self.assertEqual((Renderer.font.cache_info().currsize, module.table.cache_info().currsize), (1, 1))
        # The drawing hosts' text and the menus' art stay (on iOS each is a CoreText call or a picture again).
        self.assertEqual(Fonts.measure.cache_info().currsize, 1)
        self.assertIn('exp_runtime.hd_ui', episode_thumbnails.KEPT_CACHES)


class TitleCardRunTests(unittest.TestCase):
    def test_answers_what_an_episode_asks_before_its_title_card(self):
        session = FakeSession('dialogue', 'choice', 'character_picker', 'text_input', 'loading', 'presentation')
        self.assertTrue(episode_thumbnails.run_to_title_card(session))
        self.assertEqual(session.answers, [None, 1, 0, 'Player'])        # the first enabled choice option
        self.assertEqual(session.ticks, [episode_thumbnails.CHOICE_PACE_MS, 3001])
        self.assertEqual(session.pending.name, 'presentation')

    def test_minigames_are_skipped_and_choices_are_answered_at_a_persons_pace(self):
        # CoD's Sunset (16.7): its "Squeeze!" fight repeats until its clock runs out.
        session = FakeSession('word_game', 'choice', 'presentation')
        self.assertTrue(episode_thumbnails.run_to_title_card(session))
        self.assertEqual(session.skips, [('word_game', True)])
        self.assertEqual((session.answers, session.ticks), ([1], [episode_thumbnails.CHOICE_PACE_MS]))

    def test_fourth_of_july_part_two_borrows_part_ones_card_with_its_own_subtitle(self):
        pygame.display.init()
        pygame.display.set_mode((1, 1))
        self.addCleanup(pygame.display.quit)
        part1 = dict(id='one', pack_id=20000, episode_id=13)
        part2 = dict(id='two', pack_id=20000, episode_id=14)
        opened = []
        library = SimpleNamespace(game_id='cod', episodes=[part1, part2], open_episode=lambda key: opened.append(key))
        details = dict(title='Side Stories', subtitle='Fourth of July Special, Part 1')
        session = SimpleNamespace(pending=SimpleNamespace(details=details), engine=SimpleNamespace(title_screen=None))
        view = SimpleNamespace(tick=lambda ms: None, render=lambda: None, error=None)
        with patch.object(episode_thumbnails, 'Session', return_value=session), \
                patch.object(episode_thumbnails, 'run_to_title_card', return_value=True), \
                patch('exp_runtime.desktop.Desktop', return_value=view):
            self.assertIsNotNone(episode_thumbnails.capture_title_card(library, part2))
        self.assertEqual(opened, ['one'])
        self.assertEqual(details['subtitle'], 'Fourth of July Special, Part 2')

    def test_an_episode_with_no_title_card_or_an_unhandled_stop_is_given_up_on(self):
        self.assertFalse(episode_thumbnails.run_to_title_card(FakeSession('dialogue')))
        self.assertFalse(episode_thumbnails.run_to_title_card(FakeSession('episode_exit')))


class ScreenTests(unittest.TestCase):
    def setUp(self):
        pygame.display.init()
        pygame.display.set_mode((1, 1))
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        records = []
        for season in (1, 2, 3, 4):
            for episode in range(1, 7 if season == 1 else 3):
                records.append(record(season * 100 + episode, season * 100 + 1, season * 10 + episode, f'E{season}{episode}', variant='hd'))
        catalog = EpisodeCatalog(CatalogEntry(r['pack_id'], r['episode_id'], r['titles'][0], f'SEASON {r["pack_id"] // 100}', '', 'hd')
                                 for r in records)
        library = library_with(self.temporary.name, records, catalog, previews={})
        self.model = PickerModel(library)
        self.picker = HdEpisodePicker(library, self.model, lambda r: None)
        self.first = self.model.rows[0].episodes[0]['id']

    def test_keys_move_between_tiles_and_rows_and_enter_opens(self):
        picker = self.picker
        self.assertIsNone(picker.key(pygame.K_RIGHT))          # the first key press only shows the focus
        self.assertEqual(picker.selected, self.first)
        picker.key(pygame.K_RIGHT)
        picker.key(pygame.K_RIGHT)
        self.assertEqual(self.model.position[picker.selected], (0, 2))
        picker.key(pygame.K_DOWN)
        self.assertEqual(self.model.position[picker.selected], (1, 1))          # row 2 has two tiles
        picker.key(pygame.K_UP)
        self.assertEqual(self.model.position[picker.selected], (0, 1))
        picker.key(pygame.K_LEFT)
        self.assertEqual(self.model.position[picker.selected], (0, 0))
        self.assertEqual(picker.key(pygame.K_RETURN), ('tile', picker.selected))
        self.assertIsNone(picker.key(pygame.K_a))

    def test_navigation_scrolls_the_selection_into_view(self):
        picker = self.picker
        picker.enter(self.model.rows[0].episodes[5]['id'])
        self.assertGreater(picker.row_x[self.model.rows[0].key], 0)
        picker.enter(self.first)
        self.assertEqual(picker.row_x.get(self.model.rows[0].key, 0), 0)
        picker.key(pygame.K_DOWN)
        picker.key(pygame.K_DOWN)
        picker.key(pygame.K_DOWN)
        self.assertGreaterEqual(picker.scroll_y, 0)

    def test_wheel_scrolls_within_bounds(self):
        picker = self.picker
        picker.wheel(0, -50, (100, 100))
        self.assertEqual(picker.scroll_y, picker.max_scroll_y())
        picker.wheel(0, 200, (100, 100))
        self.assertEqual(picker.scroll_y, 0)
        picker.wheel(-30, 0, (100, 100))
        self.assertEqual(picker.row_x[self.model.rows[0].key], picker.max_scroll_x(self.model.rows[0]))
        self.assertNotIn(self.model.rows[1].key, picker.row_x)

    def test_a_click_is_a_command_and_a_drag_is_not(self):
        picker = self.picker
        rect = pygame.Rect(TILE_X, 15, 216, 290)
        picker.hits = [(rect, ('tile', self.first))]
        picker.pointer_down((50, 50))
        self.assertEqual(picker.pointer_up((52, 51)), ('tile', self.first))
        picker.pointer_down((50, 50))
        picker.pointer_move((10, 55))
        picker.pointer_move((-100, 55))
        self.assertIsNone(picker.pointer_up((-100, 55)))
        self.assertGreater(picker.row_x[self.model.rows[0].key], 0)
        self.assertEqual(picker.scroll_y, 0)
        picker.pointer_down((50, 50))
        self.assertIsNone(picker.pointer_up((300, 50)))        # released elsewhere

    def test_a_vertical_drag_scrolls_the_rows(self):
        picker = self.picker
        picker.pointer_down((300, 500))
        picker.pointer_move((302, 300))
        picker.pointer_up((302, 300))
        self.assertGreater(picker.scroll_y, 0)
        self.assertEqual(picker.row_x, {})

    def test_popup_and_alert_capture_keys_and_pointer_scrolling(self):
        picker = self.picker
        picker.popup = self.model.records[0]
        self.assertEqual(picker.key(pygame.K_ESCAPE), ('close',))
        self.assertIsNone(picker.key(pygame.K_RIGHT))
        picker.wheel(0, -5, (10, 10))
        picker.pointer_down((300, 500))
        picker.pointer_move((302, 300))
        self.assertEqual(picker.scroll_y, 0)
        picker.popup, picker.alert = None, ('Title', 'Text')
        self.assertEqual(picker.key(pygame.K_RETURN), ('dismiss',))

    def test_geometry_constants_match_the_native_row_layout(self):
        self.assertEqual((ROW_HEIGHT, TILE_STEP, TILE_X), (320, 236, 20))
        self.assertEqual(self.picker.max_scroll_y(), 4 * ROW_HEIGHT - 965)


class IndexingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        profile = patch('exp_runtime.shs.content.NATIVE_SHA256', digest(FAKE_NATIVE))
        profile.start()
        self.addCleanup(profile.stop)
        words = (0x6162,) * 12
        self.data = archive({1: meta(7, 2, 'Indexed'), 25001: program(0x33, words=words).to_bytes(),
                             26000: png(256), 26001: png(256), 26002: png(128)})
        self.apk = self.root / 'user.apk'
        make_apk(self.apk, self.data)

    def test_import_records_the_release_and_a_script_signature(self):
        manifest = import_game(self.apk, [], self.root / 'library')
        record_ = next(e for e in manifest['episodes'] if e['name'] == 'Test.exp')
        self.assertEqual(record_['variant'], 'hd')
        self.assertIn('signature', record_)

    def test_an_older_library_is_indexed_once_and_atomically(self):
        target = self.root / 'library'
        import_game(self.apk, [], target)
        manifest = json.loads((target / 'library.json').read_text(encoding='utf-8'))
        for episode in manifest['episodes']:
            episode.pop('signature'), episode.pop('variant')
        (target / 'library.json').write_text(json.dumps(manifest), encoding='utf-8')
        with ContentLibrary(target) as library:
            self.assertEqual(library.index_missing(), len(manifest['episodes']))
            self.assertTrue(all('signature' in e for e in library.episodes))
            self.assertEqual(library.index_missing(), 0)
        saved = json.loads((target / 'library.json').read_text(encoding='utf-8'))
        self.assertTrue(all('signature' in e for e in saved['episodes']))
        self.assertFalse(list(target.glob('.shs-import-*')))

    def test_a_release_older_rules_left_undecided_is_read_again_once(self):
        target = self.root / 'library'
        import_game(self.apk, [], target)
        manifest = json.loads((target / 'library.json').read_text(encoding='utf-8'))
        for episode in manifest['episodes']:
            episode.pop('index')
            if episode['name'] == 'Test.exp':
                episode['variant'] = None                 # what widths-only detection left some HD episodes with
        (target / 'library.json').write_text(json.dumps(manifest), encoding='utf-8')
        with ContentLibrary(target) as library:
            undecided = [e['name'] for e in manifest['episodes'] if e['variant'] is None]
            self.assertEqual(sorted(e['name'] for e in library.unindexed()), sorted(undecided))
            library.index_missing()
            self.assertEqual(next(e for e in library.episodes if e['name'] == 'Test.exp')['variant'], 'hd')
            self.assertEqual(library.unindexed(), [])      # art-less ones stay undecided, but are not read again


if __name__ == '__main__':
    unittest.main()
