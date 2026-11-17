"""Per-frame costs found on the g54 (2026-11-17): what is read or drawn once instead of every frame, drawing the same."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import pygame  # noqa: E402

from exp_runtime import desktop_x360_slot, vector_text  # noqa: E402
from exp_runtime.desktop import _covers  # noqa: E402
from exp_runtime.desktop_x360_slot import X360SlotRenderer  # noqa: E402


class X360SkinSpecTests(unittest.TestCase):
    def test_the_skin_is_read_once_per_episode(self):
        skin = ({'slot': {}}, object())
        with patch.object(desktop_x360_slot, 'addon_skin', Mock(return_value=skin)) as read:
            renderer = X360SlotRenderer(object())
            for _ in range(3):
                self.assertIs(renderer._spec(), skin)
            self.assertEqual(read.call_count, 1)
            renderer.resources = object()                   # another episode's resources: read again
            renderer._spec()
            self.assertEqual(read.call_count, 2)

    def test_a_missing_skin_is_looked_for_again(self):
        with patch.object(desktop_x360_slot, 'addon_skin', Mock(return_value=None)) as read:
            renderer = X360SlotRenderer(object())
            self.assertIsNone(renderer._spec())
            self.assertIsNone(renderer._spec())
            self.assertEqual(read.call_count, 2)


class BackdropCoverTests(unittest.TestCase):
    def test_only_an_opaque_picture_of_the_areas_size_covers_it(self):
        opaque = pygame.Surface((8, 6))
        self.assertTrue(_covers(opaque, (8, 6)))
        self.assertFalse(_covers(opaque, (8, 7)))
        self.assertFalse(_covers(pygame.Surface((8, 6), pygame.SRCALPHA), (8, 6)))
        faded = pygame.Surface((8, 6))
        faded.set_alpha(128)
        self.assertFalse(_covers(faded, (8, 6)))
        keyed = pygame.Surface((8, 6))
        keyed.set_colorkey((0, 0, 0))
        self.assertFalse(_covers(keyed, (8, 6)))


class OutlineCoverageTests(unittest.TestCase):
    def setUp(self):
        vector_text._COVERAGE.clear()
        self.addCleanup(vector_text._COVERAGE.clear)

    def test_a_mask_is_drawn_once_for_every_colour(self):
        outlines = SimpleNamespace()
        mask = (object(), 0, 0)
        with patch('exp_runtime.glyph_outline.coverage', Mock(return_value=mask)) as draw:
            for _ in range(4):                                  # four colours of one name font: the same mask
                self.assertIs(vector_text._coverage(outlines, 65, 52, 8.0), mask)
            self.assertEqual(draw.call_count, 1)
            vector_text._coverage(outlines, 65, 52, 8.0, fill=False)   # another width or part is its own
            vector_text._coverage(outlines, 65, 52)
            vector_text._coverage(outlines, 66, 52, 8.0)
            self.assertEqual(draw.call_count, 4)

    def test_a_glyph_without_an_outline_is_kept_as_none(self):
        with patch('exp_runtime.glyph_outline.coverage', Mock(return_value=None)) as draw:
            self.assertIsNone(vector_text._coverage(SimpleNamespace(), 9, 20))
            self.assertIsNone(vector_text._coverage(SimpleNamespace(), 9, 20))
        self.assertLessEqual(draw.call_count, 2)

    def test_the_kept_masks_are_bounded(self):
        with patch('exp_runtime.glyph_outline.coverage', Mock(return_value=None)), \
                patch.object(vector_text, 'COVERAGE_KEPT', 3):
            outlines = SimpleNamespace()
            for code in range(10):
                vector_text._coverage(outlines, code, 20)
            self.assertEqual(len(vector_text._COVERAGE), 3)


if __name__ == '__main__':
    unittest.main()
