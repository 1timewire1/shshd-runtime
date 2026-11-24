"""Claire Hart's cases in their own 4:3 (owner, 2026-11-22; reference/Other Games/docs/CLAIRE_HART_43_PLAN.md): the
"Claire Hart 4:3" switch, the 4:3 frame only in a Claire Hart case and only where the window has room, its scenes whole,
its dialogue 1.35x, and the round's HUD text at Classic's sizes."""
import os
from types import SimpleNamespace
import unittest

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')


class WideRoomTests(unittest.TestCase):
    def test_a_window_takes_the_4_3_frame_once_it_is_4_3_or_wider(self):
        from exp_runtime import frame_shape
        self.assertTrue(frame_shape.has_wide_room((1024, 768)))         # an iPad in landscape
        self.assertTrue(frame_shape.has_wide_room((1023, 768)))         # (a pixel of rounding spared)
        self.assertTrue(frame_shape.has_wide_room((2400, 1080)))        # a phone in landscape
        self.assertTrue(frame_shape.has_wide_room((1920, 1080)))        # a maximized window
        self.assertFalse(frame_shape.has_wide_room((1000, 768)))
        self.assertFalse(frame_shape.has_wide_room((768, 1024)))        # portrait
        self.assertFalse(frame_shape.has_wide_room((0, 0)))
        width, tall = frame_shape.WIDE_UNITS
        self.assertEqual(tall, 512)                                     # HD's frame height, so the column keeps its size
        self.assertAlmostEqual(width / tall, 4 / 3)


def a_desktop(window, *, on=True, case=True, aspect='3:4', fixed=False):
    """Desktop's frame choice on a stand-in: the window's usable size, the switch, whether a Claire Hart case is open."""
    from exp_runtime.desktop import Desktop
    fake = SimpleNamespace(ch_43=on, aspect_ratio=aspect, fixed_window=fixed, usable_size=lambda: window,
                           ch_43_switch=lambda: case)
    fake.wide_frame = lambda: Desktop.wide_frame(fake)
    return fake


class WideFrameTests(unittest.TestCase):
    def test_the_frame_is_4_3_only_with_the_switch_a_case_and_room(self):
        from exp_runtime import frame_shape
        from exp_runtime.desktop import Desktop
        self.assertEqual(Desktop.frame_units(a_desktop((1280, 720))), frame_shape.WIDE_UNITS)
        self.assertEqual(Desktop.frame_units(a_desktop((1280, 720), on=False)), (384, 512))    # the switch off
        self.assertEqual(Desktop.frame_units(a_desktop((1280, 720), case=False)), (384, 512))  # another game's episode
        self.assertEqual(Desktop.frame_units(a_desktop((576, 768))), (384, 512))               # no room: 3:4 as before
        # Fit Screen on a phone held upright stays its own tall shape; turned to landscape, 4:3.
        upright = Desktop.frame_units(a_desktop((1080, 2400), aspect='fit', fixed=True))
        self.assertLess(upright[0] / upright[1], 3 / 4)
        self.assertEqual(Desktop.frame_units(a_desktop((2400, 1080), aspect='fit', fixed=True)), frame_shape.WIDE_UNITS)

    def test_only_the_4_3_frame_enlarges_the_dialogue(self):
        from exp_runtime import frame_shape
        from exp_runtime.desktop import Desktop
        self.assertEqual(Desktop.column_zoom(Desktop, frame_shape.WIDE_UNITS), 1.35)
        for units in ((384, 512), (384, 576), (320, 569)):
            self.assertEqual(Desktop.column_zoom(Desktop, units), 1)

    def test_the_switch_is_offered_in_a_claire_hart_case_only(self):
        from exp_runtime.desktop import Desktop
        from test_backdrop_slices import with_scenes
        self.assertTrue(Desktop.ch_43_switch(SimpleNamespace(_session=SimpleNamespace(resources=with_scenes()))))
        self.assertFalse(Desktop.ch_43_switch(SimpleNamespace(_session=SimpleNamespace(resources=with_scenes(pack=31000)))))
        self.assertFalse(Desktop.ch_43_switch(SimpleNamespace()))                  # (no story open)


class WholeSceneTests(unittest.TestCase):
    def setUp(self):
        import pygame
        pygame.init()
        pygame.display.set_mode((1, 1))
        self.addCleanup(pygame.quit)

    def test_the_slice_keeps_its_whole_scene(self):
        import pygame
        from exp_runtime.desktop import Desktop, SLICED_BACKDROPS, WHOLE_BACKDROPS
        from test_backdrop_slices import with_scenes
        picture = pygame.Surface((1024, 768))
        fake = SimpleNamespace(images={26160: picture}, session=SimpleNamespace(resources=with_scenes()))
        Desktop._slice_backdrop(fake, 26160)
        sliced = fake.images[26160]
        self.assertIn(sliced, SLICED_BACKDROPS)
        self.assertIs(WHOLE_BACKDROPS[sliced], picture)          # (a 4:3 frame draws this; the frame may switch any time)

    def test_the_whole_scene_fills_the_4_3_frame(self):
        import pygame
        from exp_runtime.desktop import Desktop
        picture = pygame.Surface((1024, 768))
        self.assertEqual(Desktop._whole_placement(picture, (800, 600)), (0, 0, 800, 600))
        x, y, w, h = Desktop._whole_placement(pygame.Surface((1026, 770)), (1024, 768))   # (a round's base, 2 px over)
        self.assertAlmostEqual(w / h, 1026 / 770)
        self.assertLessEqual(x, 0)
        self.assertLessEqual(y, 0)


class OptionTests(unittest.TestCase):
    def test_claire_hart_4_3_is_a_chc_switch_on_by_default(self):
        from exp_runtime.desktop_pause_hd import ADDON_KEYS, SWITCH_BADGES, SWITCH_LABELS
        from exp_runtime.menu import SHARED_PREFERENCES, preference_defaults
        self.assertIn('ch_43', ADDON_KEYS)                         # (Per-Game Settings from the main menu, Add-Ons in a story)
        self.assertEqual(SWITCH_LABELS['ch_43'], 'Claire Hart 4:3')
        self.assertEqual(SWITCH_BADGES['ch_43'], 'CHC')
        self.assertIs(SHARED_PREFERENCES['ch_43'], bool)
        self.assertIs(preference_defaults()['ch_43'], True)

    def test_it_is_written_and_read_with_the_library(self):
        import inspect
        from exp_runtime.menu import MenuState
        source = inspect.getsource(MenuState)
        self.assertIn("ch_43=self.ch_43", source)                       # (persist)
        self.assertIn("data.get('ch_43')", source)                       # (read back as a bool)


class RoundTextTests(unittest.TestCase):
    def test_the_hud_text_is_classics_romic_regular_at_its_sizes(self):
        from exp_runtime import desktop_claire_round as r
        self.assertEqual((r.NAME_PX, r.COMBO_PX, r.SCORE_PX, r.COUNT_PX, r.HINT_PX, r.LABEL_PX), (19, 20, 22, 19, 27, 17))
        self.assertEqual((r.NAME_PLATE, r.SCORE_AT), ((370, 18), (596, 17)))   # (chc_05/06: the plate's and pill's middles)
        self.assertEqual((r.MENU_SCALE, r.MENU_AT), (1.0, (32, 91)))


if __name__ == '__main__':
    unittest.main()
