"""HD football's pure helpers (the art itself is verified against photos, not shipped)."""
import importlib.util
import os
import unittest


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class HdFootballTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime import desktop_football_hd as module
        self.module = module

    def test_slots_are_a_three_by_three_grid_in_frame_pixels(self):
        slots = self.module.SLOTS
        self.assertEqual(len(slots), 9)
        self.assertEqual(sorted({x for x, _ in slots}), [184, 384, 584])
        self.assertEqual(sorted({y for _, y in slots}), [440, 600, 760])

    def test_hit_uses_the_140_by_140_box_above_each_slot(self):
        hit = self.module.HdFootballRenderer.hit
        self.assertEqual(hit((184, 440)), 0)
        self.assertEqual(hit((584, 760)), 8)
        self.assertEqual(hit((184, 440 - 106)), 0)
        self.assertIsNone(hit((184, 440 - 107)))
        self.assertIsNone(hit((184, 440 + 35)))
        self.assertIsNone(hit((184 + 71, 440)))
        self.assertIsNone(hit((0, 0)))

    def test_wrap_positive_keeps_values_in_the_negative_span(self):
        wrap = self.module.wrap_positive
        self.assertEqual(wrap(0, 1024), 0)
        self.assertEqual(wrap(1024, 1024), 0)
        self.assertEqual(wrap(10, 1024), -1014)
        self.assertEqual(wrap(-10, 1024), -10)

    def test_hd_strings_follow_the_android_text(self):
        strings = self.module.HdStrings({1: 'Touch icons', 2: 'Missing'}, {'Touch icons', 'Other'})
        self.assertEqual(strings[1], 'Touch icons')
        self.assertEqual(strings[2], 'Missing')


if __name__ == '__main__':
    unittest.main()
