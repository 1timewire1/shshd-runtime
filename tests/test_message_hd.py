import os
import unittest

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
import pygame

from exp_runtime.desktop_message_hd import CodMessageRenderer, HdMessageRenderer

MIN_HEIGHT, SHORT_HEADER = HdMessageRenderer.MIN_HEIGHT, HdMessageRenderer.SHORT_HEADER


class FakeRenderer(HdMessageRenderer):
    """Geometry only: fixed line counts and pitches instead of fonts."""
    def __init__(self, lines, title_lines=1):
        self._lines, self._title = lines, title_lines

    def wrap(self, text, points, width):
        return [''] * (self._title if points == self.TITLE_POINTS else self._lines)

    def pitch(self, points):
        return (46 if points == self.TITLE_POINTS else 32.5) * self.SHORT_HEADER / 94


class FakeCodRenderer(FakeRenderer, CodMessageRenderer):
    pass


class HdMessageGeometryTests(unittest.TestCase):
    def test_short_text_keeps_the_authored_size_and_matches_the_instructions_photo(self):
        header, height, total, top, center = FakeRenderer(5).geometry('Instructions', '')
        self.assertEqual((header, height, total, top, center), (SHORT_HEADER, MIN_HEIGHT, 384, 414, 528))
        # The bubble (total tall around `center`) spans 336-720; photo IMG_0240: 338-717.
        self.assertEqual((center - total / 2, center + total / 2), (336, 720))

    def test_long_text_grows_the_body_like_the_end_photo(self):
        header, height, total, top, center = FakeRenderer(16).geometry('The End', '')
        self.assertEqual(height, 60 + 522)
        self.assertEqual(total, 94 + 582 + 33 + 1)      # IMG_0242's box is about 705 tall

    def test_a_wrapped_title_takes_the_tall_header(self):
        self.assertEqual(FakeRenderer(5, title_lines=2).geometry('x', '')[0], 156)


class CodMessageGeometryTests(unittest.TestCase):
    """Cause of Death's form: the same SHSUIForm on its own bank, whose layouts are HD's at half size."""

    def test_the_cod_form_is_hds_at_half_size(self):
        hd, cod = HdMessageRenderer, CodMessageRenderer
        for name in ('WIDTH', 'MIN_HEIGHT', 'SHORT_HEADER', 'TALL_HEADER', 'FOOTER', 'BODY_INSET', 'BUBBLE_EDGE',
                     'PILL_INSET', 'PILL_DROP', 'TITLE_DROP', 'TITLE_POINTS', 'BODY_POINTS', 'LABEL_POINTS'):
            self.assertEqual(getattr(cod, name) * 2, getattr(hd, name), name)
        self.assertEqual(tuple(v * 2 for v in cod.BODY), hd.BODY)
        self.assertEqual(tuple(v * 2 for v in cod.SHORT_TITLE), hd.SHORT_TITLE)
        self.assertEqual(tuple(v * 2 for v in cod.TALL_TITLE), hd.TALL_TITLE)

    def test_thanks_for_playing_sits_on_the_cod_screen_like_the_photo(self):
        renderer = FakeCodRenderer(1)
        header, height, total, top, center = renderer.geometry('Cause of Death', 'Thanks for playing!')
        self.assertEqual((header, height, total), (47, 128, 192))
        # The owner's photo (1.05 x 2 px per point) measures about 38 and 23 points for these two bands.
        self.assertEqual(top - (center - total / 2), 39)                # box top to the first body row
        self.assertEqual((center + total / 2) - (top + height), 25)     # last body row to the box's bottom
        # The column's middle (y 240) on the HD frame: 53 + 2 * 240.
        self.assertEqual(renderer.frame_point(160, 240), (384, 533))

    def test_the_cod_form_writes_black_and_stands_on_black(self):
        self.assertEqual(CodMessageRenderer.INK, (0, 0, 0))
        self.assertIsNone(CodMessageRenderer.background(object.__new__(CodMessageRenderer), None))
        self.assertTrue(CodMessageRenderer.TITLE_FADE and not HdMessageRenderer.TITLE_FADE)


if __name__ == '__main__':
    unittest.main()
