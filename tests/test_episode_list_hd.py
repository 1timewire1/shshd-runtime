import tempfile
import unittest

import pygame

from exp_runtime.desktop_episode_list_hd import (BLUE_HEADER, HEADER_HEIGHT, ORANGE_HEADER, PANEL_BOTTOM,
                                                  PANEL_RADIUS, PANEL_TOP, ROW_HEIGHT, ROW_WHITE, S, TITLE_HEIGHT,
                                                  HdEpisodeList)
from exp_runtime.episode_catalog import CatalogEntry, EpisodeCatalog
from exp_runtime.episode_picker import PickerModel
from test_episode_index import record
from test_episode_picker import library_with


class ListTests(unittest.TestCase):
    def setUp(self):
        pygame.display.init()
        pygame.display.set_mode((1, 1))
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        records = []
        for season in (1, 2, 3):
            for episode in range(1, 4 if season == 1 else 2):
                records.append(record(season * 100 + episode, season * 100 + 1, season * 10 + episode,
                                      f'E{season}{episode}', variant='hd'))
        catalog = EpisodeCatalog(CatalogEntry(r['pack_id'], r['episode_id'], r['titles'][0], f'SEASON {r["pack_id"] // 100}', '', 'hd')
                                 for r in records)
        library = library_with(self.temporary.name, records, catalog, previews={})
        self.model = PickerModel(library)
        self.list = HdEpisodeList(library, self.model, lambda r: None)

    def test_every_row_starts_expanded_and_lists_every_episode_under_its_header(self):
        entries, total = self.list.entries()
        headers = [record for _, _, row, record in entries if record is None]
        self.assertEqual(len(headers), len(self.model.rows))
        episodes = [record for _, _, _, record in entries if record is not None]
        self.assertEqual({r['id'] for r in episodes}, {r['id'] for row in self.model.rows for r in row.episodes})
        self.assertGreater(total, 0)

    def test_collapsing_a_row_hides_its_episodes_but_keeps_its_header(self):
        key = self.model.rows[0].key
        self.list.expanded.discard(key)
        entries, _ = self.list.entries()
        shown = {row.key for _, _, row, record in entries if record is not None}
        self.assertNotIn(key, shown)
        headers = [row.key for _, _, row, record in entries if record is None]
        self.assertIn(key, headers)

    def test_a_choice_lists_only_its_episodes_and_ticks_them_by_tap_and_key(self):
        from exp_runtime.desktop_episode_list_hd import CHOICE_ACT, EpisodeChoice
        first, *rest = [r for row in self.model.rows for r in row.episodes]
        allowed = {first['id'], rest[-1]['id']}
        self.list.choosing = EpisodeChoice('Delete Episodes', 'Delete', allowed)
        self.assertEqual(self.list.title_text(), 'Delete Episodes')
        entries, _ = self.list.entries()
        self.assertEqual({record['id'] for _, _, _, record in entries if record is not None}, allowed)
        self.assertEqual(sum(1 for *_, record in entries if record is None), 2)    # groups with nothing are left out
        rect = pygame.Rect(0, 0, 700, 72)
        self.list.hits = [(rect, ('pick', first['id']))]
        self.list.pointer_down(rect.center)
        self.assertIsNone(self.list.pointer_up(rect.center))                      # a tick, not an app command
        self.assertEqual(self.list.choosing.chosen, {first['id']})
        for key in (pygame.K_DOWN, pygame.K_DOWN, pygame.K_RETURN):               # highlight, the second row, tick
            self.assertIsNone(self.list.key(key))
        self.assertEqual(self.list.choosing.chosen, allowed)
        self.list.key(pygame.K_DOWN)                                               # past the last row: the verb
        self.assertTrue(self.list.act_focus)
        self.assertEqual(self.list.key(pygame.K_RETURN), CHOICE_ACT)
        self.list.choosing.chosen.clear()
        self.assertIsNone(self.list.key(pygame.K_RETURN))                          # nothing ticked: inert
        self.list.key(pygame.K_UP)
        self.assertFalse(self.list.act_focus)
        self.list.choosing.toggle('not offered')
        self.assertEqual(self.list.choosing.chosen, set())

    def test_a_header_tap_toggles_its_row_and_is_never_forwarded_as_an_app_command(self):
        key = self.model.rows[0].key
        rect = pygame.Rect(0, 0, 700, 52)
        self.list.hits = [(rect, ('toggle', key))]
        self.list.pointer_down(rect.center)
        self.assertIsNone(self.list.pointer_up(rect.center))
        self.assertNotIn(key, self.list.expanded)
        self.list.hits = [(rect, ('toggle', key))]
        self.list.pointer_down(rect.center)
        self.assertIsNone(self.list.pointer_up(rect.center))
        self.assertIn(key, self.list.expanded)

    def test_a_row_tap_is_a_normal_tile_command_not_swallowed_like_a_toggle(self):
        episode_id = self.model.rows[0].episodes[0]['id']
        rect = pygame.Rect(0, 60, 700, 64)
        self.list.hits = [(rect, ('tile', episode_id))]
        self.list.pointer_down(rect.center)
        self.assertEqual(self.list.pointer_up(rect.center), ('tile', episode_id))

    def test_reveal_scrolls_a_far_down_episode_into_view_above_the_footer(self):
        last_row = self.model.rows[-1]
        last_episode = last_row.episodes[-1]['id']
        self.list.reveal(last_episode)
        entries, _ = self.list.entries()
        top, height = next((top, height) for top, height, _, record in entries
                           if record is not None and record['id'] == last_episode)
        self.assertGreaterEqual(top - self.list.scroll_y, 0)
        self.assertLessEqual(top + height - self.list.scroll_y, self.list.list_height())

    def test_reveal_does_nothing_for_an_episode_hidden_in_a_collapsed_row(self):
        key = self.model.rows[0].key
        episode_id = self.model.rows[0].episodes[0]['id']
        self.list.expanded.discard(key)
        self.list.scroll_y = 123
        self.list.reveal(episode_id)
        self.assertEqual(self.list.scroll_y, 123)          # no matching visible entry, so nothing moves

    def test_keys_move_between_visible_episodes_in_order_and_enter_opens(self):
        episodes = [r for row in self.model.rows for r in row.episodes]
        self.assertIsNone(self.list.key(pygame.K_DOWN))          # first press only shows the focus
        self.assertEqual(self.list.selected, episodes[0]['id'])
        self.list.key(pygame.K_DOWN)
        self.assertEqual(self.list.selected, episodes[1]['id'])
        self.list.key(pygame.K_UP)
        self.assertEqual(self.list.selected, episodes[0]['id'])
        self.assertEqual(self.list.key(pygame.K_RETURN), ('tile', episodes[0]['id']))

    def test_keys_skip_episodes_in_a_collapsed_row(self):
        first_key = self.model.rows[0].key
        self.list.expanded.discard(first_key)
        self.list.key(pygame.K_DOWN)
        self.assertNotIn(self.list.selected, {r['id'] for r in self.model.rows[0].episodes})

    def test_content_height_shrinks_when_every_row_collapses(self):
        expanded_height = self.list.content_height()
        self.list.expanded = set()
        self.assertLess(self.list.content_height(), expanded_height)
        self.assertEqual(self.list.content_height(), len(self.model.rows) * HEADER_HEIGHT)   # all collapsed

    def test_row_at_reports_no_row_so_a_drag_is_always_vertical(self):
        self.assertIsNone(self.list.row_at((100, 100)))

    def test_list_height_matches_the_clip_rect_draw_actually_uses(self):
        # `list_height()` (the scroll-clamping math's idea of the visible area) used to overstate the rect
        # `draw()` actually clips rows to by 24px -- the 2px gap under the title divider, plus `PANEL_RADIUS`
        # inset from the panel's own rounded bottom corners, that the clip rect is built with but this method
        # left out. Recomputed independently here (not via `draw()`, which now shares this same method and so
        # could no longer disagree with it even if the formula regressed) to pin the actual pixel figure down.
        divider_y = PANEL_TOP + TITLE_HEIGHT
        expected = PANEL_BOTTOM - divider_y - 2 - PANEL_RADIUS
        self.assertEqual(self.list.list_height(), expected)

    def test_a_subtitle_adds_a_second_duller_line_below_the_title(self):
        record_ = self.model.rows[0].episodes[0]
        rect = pygame.Rect(0, 0, 400, ROW_HEIGHT)

        def painted_lower_third(subtitle):
            layer = pygame.Surface((rect.width * S, rect.height * S))
            layer.fill(ROW_WHITE)
            self.list.model.subtitle = lambda record: subtitle
            self.list.draw_row(layer, record_, rect, True)
            lower = pygame.Rect(18 * S, (rect.height * 2 // 3) * S, 200 * S, (rect.height // 3 - 4) * S)
            return sum(1 for x in range(lower.x, lower.right) for y in range(lower.y, lower.bottom)
                      if layer.get_at((x, y))[:3] != ROW_WHITE)

        self.assertEqual(painted_lower_third(None), 0)                      # single-line title stays centered
        self.assertGreater(painted_lower_third('A Category - Airdate: 01/01/2010'), 0)

    def test_only_the_mega_packs_header_is_orange_the_rest_are_blue(self):
        # `PickerModel.mega_label` keeps whatever raw string it was constructed with (here the APK's own all-caps
        # string), but `episode_index.build_rows()` title-cases every row's own label before storing it -- so an
        # exact `==` between the two never matched, even for the real Mega Packs row, and every header drew blue.
        mega = dict(record(900, 900, 1, 'Mega Ep', variant='hd'), apk_member='fake_bundled.exp')
        catalog = EpisodeCatalog(CatalogEntry(r['pack_id'], r['episode_id'], r['titles'][0],
                                              f'SEASON {r["pack_id"] // 100}', '', 'hd')
                                 for r in self.model.records)
        library = library_with(self.temporary.name, list(self.model.records) + [mega], catalog, previews={})
        model = PickerModel(library, mega_label='MEGA PACKS')
        episode_list = HdEpisodeList(library, model, lambda r: None)
        mega_row = next(row for row in model.rows if row.title.casefold() == 'mega packs')
        other_row = next(row for row in model.rows if row.title.casefold() != 'mega packs')
        layer = pygame.Surface((HEADER_HEIGHT * 10, HEADER_HEIGHT * 4))
        rect = pygame.Rect(0, 0, HEADER_HEIGHT * 10, HEADER_HEIGHT)
        episode_list.draw_header(layer, mega_row, rect)
        self.assertEqual(layer.get_at((4, 4))[:3], ORANGE_HEADER)
        layer.fill((0, 0, 0))
        episode_list.draw_header(layer, other_row, rect)
        self.assertEqual(layer.get_at((4, 4))[:3], BLUE_HEADER)


if __name__ == '__main__':
    unittest.main()
