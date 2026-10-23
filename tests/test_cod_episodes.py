"""Cause of Death's episode lists in SHS HD's picker (cod/episodes.py, desktop_cod_episodes.py)."""
import os
from types import SimpleNamespace
import unittest

from exp_runtime.cod import episodes
from exp_runtime.content import is_bundled
from exp_runtime.episode_catalog import CatalogEntry, EpisodeCatalog
from test_episode_index import record


def entry(pack, episode, title, category, filename=''):
    return CatalogEntry(pack, episode, title, category, filename, '')


class CodGroupingTests(unittest.TestCase):
    def setUp(self):
        base = dict(record(1, 101, 1, 'Volume One', name='Volume_One.exp'), builtin='volume-one')
        self.records = [
            base,
            record(2, 101, 10, 'Volume 2 Set', name='Volume_2.exp'),
            record(3, 101, 60, 'Volume 7: The Ladykiller', name='Volume_7.exp'),
            record(4, 101, 120, 'Volume 13: Spinnerette', name='Volume_13.exp'),
            record(5, 1201, 45, 'Interlude: Perfect Getaway', name='13_Interlude_Airing.exp'),
            record(6, 1301, 20, 'Chapter Two: Accelerant', name='14_2_Accelerant.exp'),
            record(7, 1301, 10, 'Chapter One: Joint Forces', name='14_1_Joint_Forces.exp'),
            record(8, 101, 140, 'Volume 15: The Cleaners', name='Volume_15.exp'),
            record(9, 20000, 1, 'Side Stories: Detective Kalaba, Part 1', name='SS01_Detective_Kalaba_1.exp'),
            record(10, 7, 6, 'Halloween Special: Dead Man Walking, Part 1', name='Halloween_Special_Dead_Man_Walking_1.exp'),
            record(11, 1001, 1, 'Now Airing Special', name='Now_Airing_Special.exp'),
            record(12, 7, 13, 'Halloween Special: Undying Love', name='MTX_Halloween_Special_Undying_Love.exp'),
            record(13, 7, 14, 'Holiday Interlude: A Fallon Family Christmas', name='12_Fallon_Family_Christmas.exp'),
            record(14, 7, 15, 'Secret Files 02', name='MTX_Secret_Files_02.exp'),
            record(15, 7, 999, 'Your Case: The Missing Child', name='Your_Case_Missing_Child.exp'),
        ]
        self.catalog = EpisodeCatalog([
            entry(0, 0, 'Volume One: The Maskmaker', 'VOLUME ONE'),
            entry(101, 10, 'Volume 2 Set', 'VOLUME TWO', 'volume_2.exp'),
            entry(101, 60, 'Volume 7: The Ladykiller', 'Season 7', 'volume_7.exp'),
            entry(101, 120, 'Volume 13: Spinnerette', 'Season 13', 'volume_13.exp'),
            entry(1301, 10, 'Chapter One: Joint Forces', 'Volume 14', '14_1_joint_forces.exp'),
            entry(1301, 20, 'Chapter Two: Accelerant', 'Volume 14', '14_2_accelerant.exp'),
            entry(101, 140, 'Volume 15: The Cleaners', 'Season 15', 'volume_15.exp'),
            entry(20000, 1, 'Side Stories: Detective Kalaba, Part 1', 'SIDE STORIES', 'ss01_detective_kalaba_1.exp'),
            entry(7, 6, 'Halloween Special: Dead Man Walking, Part 1', 'SIDE STORIES',
                  'halloween_special_dead_man_walking_1.exp'),
            entry(7, 13, 'Halloween Special: Undying Love', 'PREMIUM CONTENT', 'mtx_halloween_special_undying_love.exp'),
            entry(7, 15, 'Secret Files 02', 'PREMIUM CONTENT', 'mtx_secret_files_02.exp'),
            entry(7, 999, 'Your Case: The Missing Child', 'PREMIUM CONTENT', 'your_case_missing_child.exp'),
        ])
        self.rows = episodes.build_rows(self.records, self.catalog, bundled=is_bundled)

    def titles(self, row):
        return [episodes.label(r, bundled=is_bundled) for r in row.episodes]

    def test_categories_follow_the_volumes_then_side_stories_and_premium_content(self):
        self.assertEqual([row.title for row in self.rows],
                         ['Volume One', 'Volume Two', 'Season 7', 'Season 13', 'Volume 14', 'Season 15',
                          'Side Stories', 'Premium Content', 'Now Airing Special'])
        self.assertEqual(self.titles(self.rows[0]), ['Volume One: The Maskmaker'])        # the catalogue's title

    def test_one_volume_named_two_ways_is_one_row_in_release_order(self):
        self.assertEqual(self.titles(self.rows[3]), ['Volume 13: Spinnerette', 'Interlude: Perfect Getaway'])
        self.assertEqual(self.titles(self.rows[4]), ['Chapter One: Joint Forces', 'Chapter Two: Accelerant'])

    def test_owner_placements(self):
        side, premium, special = self.rows[6], self.rows[7], self.rows[8]
        self.assertEqual(self.titles(side), ['Side Stories: Detective Kalaba, Part 1',
                                             'Halloween Special: Dead Man Walking, Part 1'])
        self.assertEqual(self.titles(special), ['Now Airing Special'])        # the store's category and name
        self.assertEqual(self.titles(premium), ['Your Case: The Missing Child', 'Halloween Special: Undying Love',
                                                'Holiday Interlude: A Fallon Family Christmas', 'Secret Files 02'])

    def test_an_uncatalogued_episode_falls_back_to_premium_content(self):
        stray = record(20, 500, 1, 'Something Else', name='Something_Else.exp')
        self.assertEqual(episodes.category(stray, self.catalog), 'Premium Content')

    def test_now_airing_groups_by_year_of_first_release(self):
        rows = episodes.build_airing_rows(self.records)
        self.assertEqual([row.title for row in rows], ['2010', '2011', '2012', '2013'])
        self.assertEqual([r['titles'][0] for r in rows[0].episodes], ['Volume One', 'Volume 2 Set'])
        self.assertEqual(rows[1].episodes[0]['titles'][0], 'Your Case: The Missing Child')

    def test_every_dated_title_is_an_iso_date(self):
        import re
        self.assertTrue(all(re.fullmatch(r'20(1[0-4])-\d\d-\d\d', date) for date in episodes.RELEASE_DATES.values()))
        self.assertEqual(episodes.RELEASE_DATES['Volume 2 Set'], episodes.RELEASE_DATES['Volume One'])


@unittest.skipUnless(__import__('importlib').util.find_spec('pygame'), 'pygame is absent')
class CodPickerStyleTests(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
        import pygame
        pygame.display.init()
        pygame.display.set_mode((1, 1))
        self.addCleanup(pygame.display.quit)

    def test_the_popup_border_takes_cods_colour_and_keeps_its_blend(self):
        import pygame
        from exp_runtime.desktop_cod_episodes import BORDER, recolor_border
        card = pygame.Surface((3, 1), pygame.SRCALPHA)
        card.set_at((0, 0), (117, 137, 255, 255))           # the border
        card.set_at((1, 0), (186, 196, 255, 230))           # half way to white
        card.set_at((2, 0), (255, 255, 255, 191))           # the translucent fill
        out = recolor_border(card, BORDER)
        self.assertEqual(tuple(out.get_at((0, 0))), (*BORDER, 255))
        r, g, b, a = out.get_at((1, 0))
        self.assertEqual(a, 230)
        self.assertTrue(BORDER[0] < r < 255 and BORDER[2] < b < 255)
        self.assertEqual(tuple(out.get_at((2, 0))), (255, 255, 255, 191))

    def test_needs_a_cod_library_with_the_shs_hd_art_source(self):
        from exp_runtime.desktop_cod_episodes import CodEpisodePicker
        self.assertFalse(CodEpisodePicker.available(SimpleNamespace(game_id='shs')))
        self.assertFalse(CodEpisodePicker.available(SimpleNamespace(game_id='cod', shs_hd_art=None)))


@unittest.skipUnless(__import__('importlib').util.find_spec('pygame'), 'pygame is absent')
class CodTitleCardFrameTests(unittest.TestCase):
    """CoD's chapter card on the whole HD frame (desktop_title.CodTitleRenderer)."""

    def test_the_card_covers_the_frame_and_maps_cod_points_onto_it(self):
        from exp_runtime.desktop_title import CodTitleRenderer
        card = object.__new__(CodTitleRenderer)
        self.assertEqual(card.FRAME, (768, 1024))                 # the black opening layer covers the whole frame
        clip = card.wipe_clip(10, 100)                             # CoD points 10..110 of the title region
        self.assertEqual((clip.x, clip.width, clip.height), (64 + 20, 200, 1024))

    def test_the_black_layer_holds_for_1_8_s_and_clears_by_3_s(self):
        # "revealLocation": opacity (1, 1, 0) at keyTimes (0, .6, 1) over 3.0 s in both CoD 1.4.7 and SHS HD; TouchHLE
        # shows CoD's picture starting at 1.84 s. Ours used 2.125 s (black until 1.275 s).
        from exp_runtime.desktop_title import CodTitleRenderer, HdTitleRenderer
        for card in (HdTitleRenderer, CodTitleRenderer):
            self.assertEqual((card.BLACK_HOLD_S, card.BLACK_END_S), (1.8, 3.))
            self.assertEqual((card.WIPE_S, card.SUBTITLE_FROM_S, card.SUBTITLE_TO_S), (2., 1., 2.))


if __name__ == '__main__':
    unittest.main()
