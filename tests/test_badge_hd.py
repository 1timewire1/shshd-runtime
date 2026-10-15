import unittest

from exp_runtime.desktop_badge_hd import KEYS, ease_out, leave_x, slide_x


class BadgeMotionTests(unittest.TestCase):
    def test_entrance_settles_at_rest(self):
        self.assertEqual(slide_x(0), KEYS[0])
        self.assertEqual(slide_x(2), KEYS[2])

    def test_dismissal_slides_back_out_in_three_tenths_of_a_second(self):
        self.assertEqual(leave_x(30, 0), 30)
        middle = leave_x(30, .15)
        self.assertLess(KEYS[0], middle)
        self.assertLess(middle, 30)
        self.assertEqual(leave_x(30, .3), KEYS[0])
        self.assertEqual(leave_x(30, 1), KEYS[0])

    def test_ease_out_is_front_loaded(self):
        self.assertGreater(ease_out(.5), .5)


if __name__ == '__main__':
    unittest.main()
