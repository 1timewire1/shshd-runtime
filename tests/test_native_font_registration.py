"""The native backend's font registration (platforms/drawing.Fonts): a supplied font file the host cannot register
(iOS refused Arial Rounded MT Bold from a library's fonts/ folder, a name its own system font has, and the runtime
stopped) is drawn in a system face and logged instead."""
import unittest

from exp_runtime.platforms.drawing import Fonts


class FontRegistrationTests(unittest.TestCase):
    def test_a_registered_font_is_named_by_the_hosts_face_once(self):
        calls = []

        def bridge(request):
            calls.append(request['operation'])
            return {'face': 'ArialRoundedMTBold'}
        fonts = Fonts(bridge)
        self.assertEqual(fonts.register(b'font bytes'), 'ArialRoundedMTBold')
        self.assertEqual(fonts.register(b'font bytes'), 'ArialRoundedMTBold')
        self.assertEqual(calls, ['register'])

    def test_a_font_the_host_refuses_falls_back_and_is_logged(self):
        calls = []

        def bridge(request):
            calls.append(request['operation'])
            raise RuntimeError('Cannot register supplied font (Core Text error 305)')
        fonts = Fonts(bridge)
        with self.assertLogs(level='WARNING') as logged:
            self.assertEqual(fonts.register(b'font bytes'), Fonts.FALLBACK_FACE)
        self.assertIn('Core Text error 305', logged.output[0])
        self.assertEqual(fonts.register(b'font bytes'), Fonts.FALLBACK_FACE)   # not asked again
        self.assertEqual(calls, ['register'])


if __name__ == '__main__':
    unittest.main()
