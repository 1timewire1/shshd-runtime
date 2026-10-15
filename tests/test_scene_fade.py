import unittest

from exp_runtime.scene_fade import blind_rects, coverage, in_ms, out_ms, resolve


class SceneFadeTests(unittest.TestCase):
    def test_out_closes_in_1_2_seconds_and_holds(self):
        self.assertEqual(coverage(2, 'out', 0), 0)
        self.assertAlmostEqual(coverage(2, 'out', 600), .5)
        self.assertEqual(coverage(2, 'out', 1500), 1)
        self.assertEqual(out_ms(2), 1500)

    def test_blinds_wait_before_opening_but_the_fade_holds_black_first(self):
        self.assertEqual(coverage(1, 'in', 299), 1)
        self.assertAlmostEqual(coverage(1, 'in', 900), .5)
        self.assertEqual(coverage(1, 'in', 1800), 0)
        self.assertEqual(in_ms(1), 1800)
        self.assertEqual(coverage(6, 'in', 1199), 1)
        self.assertAlmostEqual(coverage(6, 'in', 1350), .5)
        self.assertEqual(in_ms(6), 1500)

    def test_sixteen_strips(self):
        rects = blind_rects(2, .5, (768, 1024))
        self.assertEqual(len(rects), 16)
        self.assertEqual(rects[1], (48, 0, 24, 1024))
        self.assertEqual(blind_rects(1, 1, (768, 1024))[1], (0, 64, 768, 64))
        self.assertEqual(blind_rects(2, 0, (768, 1024)), [])

    def test_random_type_picks_a_blind(self):
        self.assertEqual((resolve(20, 0), resolve(20, 1)), (1, 2))
        self.assertEqual((resolve(6, 0), resolve(3, 0), resolve(0, 0)), (6, 0, 0))


if __name__ == '__main__':
    unittest.main()
