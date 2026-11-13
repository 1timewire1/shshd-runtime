"""HD's tree zoom tab (`SHSDTZButton` / `toggleDTZ`, desktop_tree_zoom.py): its place, its 0.5 s move and its tap."""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
import pygame

from exp_runtime import desktop_tree_zoom
from exp_runtime.desktop_tree_zoom import TreeZoom


class TreeZoomTests(unittest.TestCase):
    def test_the_tab_is_where_hd_lays_it_out_shut_and_zoomed(self):
        """`SHSDTZButton setupViewOrientation_internal:`: portrait 50 x 60 at (25, 30) -> (25, 994); landscape (as
        the rotation shows it) 60 x 50 at (196, 25) -> (994, 25). The screen is fitted to the game's frame."""
        zoom = TreeZoom()
        portrait = pygame.Rect(0, 0, 384, 512)                     # a 768 x 1024-point screen at half size
        self.assertEqual(zoom.tab_rect('portrait', portrait), pygame.Rect(0, 0, 25, 30))
        landscape = pygame.Rect(224, 0, 576, 768)                  # the game between the panels, 1 px a point
        self.assertEqual(zoom.tab_rect('landscape', landscape), pygame.Rect(166, 0, 60, 50))
        zoom.toggle()
        zoom.advance(desktop_tree_zoom.DURATION_MS)
        self.assertEqual(zoom.tab_rect('portrait', portrait).center, (12, 497))
        self.assertEqual(zoom.tab_rect('landscape', landscape).center, (994, 25))

    def test_it_moves_in_half_a_second_easing_in_and_out_and_back(self):
        zoom = TreeZoom()
        self.assertFalse(zoom.showing)
        zoom.toggle()
        zoom.advance(125)
        self.assertLess(zoom.amount, 0.25)                         # slow at first
        zoom.advance(125)
        self.assertAlmostEqual(zoom.amount, 0.5)
        self.assertFalse(zoom.settled)
        zoom.advance(250)
        self.assertEqual((zoom.amount, zoom.settled), (1.0, True))
        zoom.close()
        zoom.advance(250)
        self.assertTrue(zoom.showing)                              # still on its way back
        zoom.close(instantly=True)
        self.assertFalse(zoom.showing)

    def test_a_press_and_release_on_the_tab_toggles_and_the_game_never_sees_the_press(self):
        zoom = TreeZoom()
        zoom.tab = pygame.Rect(0, 0, 50, 60)
        down, up = pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP
        press = lambda kind, pos: zoom.pointer(SimpleNamespace(type=kind, pos=pos, button=1), down=down, up=up)
        self.assertEqual(press(down, (10, 10)), 'taken')
        self.assertEqual(press(up, (10, 10)), 'toggled')
        self.assertTrue(zoom.zoomed)
        self.assertEqual(press(down, (10, 10)), 'taken')
        self.assertEqual(press(up, (200, 200)), 'taken')           # dragged off: no toggle
        self.assertTrue(zoom.zoomed)
        self.assertIsNone(press(down, (200, 200)))                 # elsewhere: not the tab's

    def test_portrait_needs_an_upright_window_and_landscape_the_open_panels(self):
        self.assertEqual(TreeZoom.mode((768, 1024), False), 'portrait')
        self.assertIsNone(TreeZoom.mode((1024, 768), False))
        self.assertEqual(TreeZoom.mode((1024, 768), True), 'landscape')

    def test_the_portrait_button_is_where_hd_lays_it_out(self):
        """`SHSPZButton setupViewOrientation_internal:` case 1: 64 x 64 at (736, 992), (480, 992) zoomed, and 256 lower
        with the tree zoom in."""
        zoom = TreeZoom()
        portrait = pygame.Rect(0, 0, 768, 1024)
        self.assertEqual(zoom.portrait_tab_rect(portrait), pygame.Rect(704, 960, 64, 64))
        zoom.toggle_portrait()
        zoom.advance(desktop_tree_zoom.DURATION_MS)
        self.assertEqual(zoom.portrait_tab_rect(portrait).center, (480, 992))
        zoom.toggle()
        zoom.advance(desktop_tree_zoom.DURATION_MS)
        self.assertEqual(zoom.portrait_tab_rect(portrait).center, (480, 1248))

    def test_the_portrait_zoom_shrinks_the_game_around_the_centre_and_the_tree_zoom_undoes_it(self):
        """`setupLocalInterfaceOrientation:`: 0.75 with HD's zero offsets; the tree zoom's layout has no scale."""
        zoom = TreeZoom()
        frame = pygame.Rect(100, 0, 768, 1024)
        self.assertEqual(zoom.game_rect(frame), frame)
        zoom.toggle_portrait()
        self.assertFalse(zoom.settled)
        zoom.advance(desktop_tree_zoom.DURATION_MS)
        self.assertTrue(zoom.showing and zoom.settled)
        self.assertEqual(zoom.game_rect(frame), pygame.Rect(196, 128, 576, 768))
        zoom.toggle()
        zoom.advance(desktop_tree_zoom.DURATION_MS)
        self.assertEqual(zoom.game_rect(frame), pygame.Rect(100, 1024, 768, 1024))
        zoom.toggle()
        zoom.advance(desktop_tree_zoom.DURATION_MS)
        self.assertEqual(zoom.game_rect(frame).size, (576, 768))   # a warp's closeDTZ leaves the portrait zoom alone
        zoom.close(instantly=True)
        self.assertFalse(zoom.showing)

    def test_a_touch_on_the_shrunken_game_lands_where_it_would_at_full_size(self):
        zoom = TreeZoom()
        frame = pygame.Rect(0, 0, 768, 1024)
        zoom.toggle_portrait()
        zoom.advance(desktop_tree_zoom.DURATION_MS)
        self.assertEqual(zoom.to_game(frame, (96, 128)), (0, 0))
        self.assertEqual(zoom.to_game(frame, (384, 512)), (384, 512))
        self.assertEqual(zoom.to_game(frame, (0, 0)), (0, 0))      # a press the game holds, dragged off it

    def test_the_portrait_button_toggles_on_its_own_tap(self):
        zoom = TreeZoom()
        zoom.portrait_tab = pygame.Rect(0, 0, 64, 64)
        down, up = pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP
        press = lambda kind, pos: zoom.portrait_pointer(SimpleNamespace(type=kind, pos=pos, button=1), down=down, up=up)
        self.assertEqual(press(down, (10, 10)), 'taken')
        self.assertEqual(press(up, (10, 10)), 'toggled')
        self.assertTrue(zoom.portrait_zoomed)
        self.assertFalse(zoom.zoomed)

    def test_the_offsets_to_try_are_read_as_x_y(self):
        self.assertEqual(desktop_tree_zoom.portrait_align('-96,-128'), (-96.0, -128.0))
        self.assertEqual(desktop_tree_zoom.portrait_align(''), (0.0, 0.0))
        self.assertEqual(desktop_tree_zoom.portrait_align('nonsense'), (0.0, 0.0))


if __name__ == '__main__':
    unittest.main()
