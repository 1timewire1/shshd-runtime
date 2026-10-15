import unittest

from exp_runtime.glyph_outline import MITER_LIMIT, _stroke_polygons, flatten


class StrokeTests(unittest.TestCase):
    def test_square_corners_are_mitered_not_rounded(self):
        # CGContext's default join: a square's outline corners stay square, reaching (half, half) past each corner.
        square = [(0, 0), (10, 0), (10, 10), (0, 10)]
        joins = [shape for shape in _stroke_polygons(square, 1) if len(shape) == 4 and shape[0] in square]
        corners = {shape[2] for shape in joins}
        self.assertEqual(len(corners), 4)
        for x, y in corners:
            self.assertIn(round(x), (-1, 11))
            self.assertIn(round(y), (-1, 11))

    def test_a_join_sharper_than_the_miter_limit_is_bevelled(self):
        spike = [(0, 0), (100, 1), (0, 2)]
        bevels = [shape for shape in _stroke_polygons(spike, 1) if len(shape) == 3]
        self.assertTrue(bevels)
        self.assertGreater(MITER_LIMIT, 1)

    def test_quadratic_contours_flatten_through_their_on_curve_points(self):
        # An on, off, on triangle-ish contour: the curve passes through both on-curve points.
        polyline = flatten([(0, 0, True), (50, 100, False), (100, 0, True)], 1)
        self.assertEqual(polyline[0], (0, 0))
        self.assertIn((100, 0), [(round(x), round(y)) for x, y in polyline])
        self.assertTrue(all(y <= 0 for _, y in polyline))          # y flips: font units up, pixels down
