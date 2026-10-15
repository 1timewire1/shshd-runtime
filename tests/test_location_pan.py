import unittest

from exp_runtime.engine import EngineState
from exp_runtime.location_pan import LocationPan, center_x, default_ease
from exp_runtime.vm import KiwiVM
from test_runtime import host_call
from test_vm import program


class LocationPanTests(unittest.TestCase):
    def test_alignment_positions(self):
        # A 960 point image in the 768 point frame: flush left, centered, flush right.
        self.assertEqual([center_x(a, 960) for a in (1, 2, 3)], [480, 384, 288])
        self.assertEqual(center_x(1, 960) - center_x(3, 960), 192)

    def test_ease_is_monotonic_and_bounded(self):
        values = [default_ease(i / 20) for i in range(21)]
        self.assertAlmostEqual(values[0], 0, places=3)
        self.assertAlmostEqual(values[-1], 1, places=3)
        self.assertEqual(values, sorted(values))

    def test_move_takes_a_quarter_second(self):
        pan = LocationPan()
        self.assertEqual(pan.x(1, 960, 1000), 480)
        self.assertEqual(pan.x(1, 960, 1500), 480)
        self.assertAlmostEqual(pan.x(3, 960, 2000), 480, places=3)
        middle = pan.x(3, 960, 2125)
        self.assertTrue(288 < middle < 480)
        self.assertEqual(pan.x(3, 960, 2250), 288)
        # Reversing midway starts from where the layer is.
        pan.x(1, 960, 3000)
        halfway = pan.x(1, 960, 3100)
        self.assertAlmostEqual(pan.x(3, 960, 3100), halfway, places=3)


class LocationStateTests(unittest.TestCase):
    def engine(self):
        engine = EngineState()
        engine.ui_defaults = {74: 0, 75: 7}
        engine.character_names = {0: 'Player', 7: 'A narrator', 32: 'Event'}
        engine.character_art_variants = {0: [100] * 5, 32: [200] * 5, 7: [-1] * 5}
        return engine

    def test_speaker_side_moves_the_layer_and_narration_leaves_it(self):
        engine = self.engine()
        panel = engine.panel
        self.assertEqual(panel.location_align, 1)
        for presentation, expected in ((2, 3), (4, 3), (3, 3), (1, 1), (4, 1)):
            panel.presentation_mode = presentation
            engine.align_location()
            self.assertEqual(panel.location_align, expected)

    def test_pinned_pan_mode_ignores_the_speaker(self):
        engine = self.engine()
        vm = KiwiVM(program(*host_call(97, 0, 2), 0x33))
        vm.run()
        self.assertEqual(engine.dispatch(vm).name, 'set_background_pan')
        self.assertEqual(engine.panel.location_align, 2)
        for presentation in (1, 2):
            engine.panel.presentation_mode = presentation
            engine.align_location()
            self.assertEqual(engine.panel.location_align, 2)
        engine.panel.location_follow = True   # every script load restores the speaker-following pan
        engine.align_location()
        self.assertEqual(engine.panel.location_align, 3)


if __name__ == '__main__':
    unittest.main()
