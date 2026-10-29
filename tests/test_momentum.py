import inspect
import math
import unittest
from unittest.mock import patch

from exp_runtime import momentum
from exp_runtime.momentum import Fling


class FlingTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(momentum, 'ENABLED', True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def flicked(self, *samples):
        fling = Fling()
        for ms, value in samples:
            fling.track(value, now=ms)
        fling.release(now=samples[-1][0])
        return fling

    def test_a_flick_glides_on_slowing_as_uiscrollview_does(self):
        fling = self.flicked((0, 0.0), (20, 20.0), (40, 40.0))          # 1 point a millisecond
        value, = fling.step(40.0, now=140)
        self.assertAlmostEqual(value, 40 + (0.998 ** 100 - 1) / -0.0020020027, places=3)
        self.assertAlmostEqual(fling.velocity[0], 0.998 ** 100)
        while fling.moving:
            last = value
            value, = fling.step(value, now=fling.time + 16)
        self.assertLess(value - last, 1)
        self.assertLess(value, 40 + 1 / 0.0020020027)                   # never past the glide's whole distance

    def test_the_story_tree_slows_at_uiscrollviews_fast_rate(self):
        """`SHSDTView scrollViewWillBeginDecelerating:` sets UIScrollViewDecelerationRateFast: the tree's glide is a
        fifth of the wall's or the pickers' (1 / -ln 0.99 against 1 / -ln 0.998)."""
        def whole(rate):
            fling = Fling(rate)
            for ms, value in ((0, 0.0), (20, 20.0), (40, 40.0)):
                fling.track(value, now=ms)
            fling.release(now=40)
            value = 40.0
            while fling.moving:
                value, = fling.step(value, now=fling.time + 16)
            return value - 40
        self.assertAlmostEqual(whole(momentum.RATE_FAST), 1 / -math.log(0.99), delta=2)
        self.assertGreater(whole(momentum.RATE), 4 * whole(momentum.RATE_FAST))
        from exp_runtime.desktop import Desktop
        self.assertIn('momentum.Fling(momentum.RATE_FAST), momentum.Fling()', inspect.getsource(Desktop.__init__))

    def test_a_finger_held_still_or_a_slow_drag_does_not_glide(self):
        self.assertFalse(self.flicked((0, 0.0), (20, 20.0), (40, 40.0), (200, 40.0)).moving)
        fling = Fling()
        fling.track(0.0, now=0)
        fling.track(10.0, now=30)
        fling.release(now=200)                                          # lifted long after the last move
        self.assertFalse(fling.moving)
        self.assertFalse(self.flicked((0, 0.0), (100, 0.5)).moving)

    def test_a_clamp_or_another_hand_ends_the_glide(self):
        fling = self.flicked((0, 0.0), (20, 20.0), (40, 40.0))
        value, = fling.step(40.0, now=56)
        self.assertIsNone(fling.step(value - 5, now=72))                # the owner clamped it at an edge
        self.assertFalse(fling.moving)
        fling = self.flicked((0, 0.0), (20, 20.0), (40, 40.0))
        fling.step(40.0, now=56)
        fling.settled(41.0)
        self.assertFalse(fling.moving)

    def test_two_axes_glide_together(self):
        fling = Fling()
        for ms in (0, 20, 40):
            fling.track(ms * 0.5, -ms * 1.0, now=ms)
        fling.release(now=40)
        down, across = fling.step(20.0, -40.0, now=56)
        self.assertGreater(down, 20)
        self.assertLess(across, -40)

    def test_off_by_default_a_mouse_drag_stops_where_it_ends(self):
        with patch.object(momentum, 'ENABLED', False):
            self.assertFalse(self.flicked((0, 0.0), (20, 20.0), (40, 40.0)).moving)

    def test_a_jittery_last_sample_is_capped(self):
        fling = self.flicked((0, 0.0), (10, 1000.0))
        self.assertEqual(fling.velocity, (momentum.TOP_SPEED,))


if __name__ == '__main__':
    unittest.main()
