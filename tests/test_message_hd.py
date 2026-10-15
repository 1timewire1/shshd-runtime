import os
import unittest

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
import pygame

from exp_runtime.desktop_message_hd import HdMessageRenderer, MIN_HEIGHT, SHORT_HEADER


class FakeRenderer(HdMessageRenderer):
    """Geometry only: fixed line counts and pitches instead of fonts."""
    def __init__(self, lines, title_lines=1):
        self._lines, self._title = lines, title_lines

    def wrap(self, text, points, width):
        return [''] * (self._title if points == 40 else self._lines)

    def pitch(self, points):
        return 46 if points == 40 else 32.5


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


if __name__ == '__main__':
    unittest.main()
