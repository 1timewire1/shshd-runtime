import importlib.util
from io import BytesIO
import math
import os
import unittest
from unittest.mock import Mock, patch
import wave

from exp_runtime.vibration import AMPLITUDE, BUZZ_MS, RAMP, RATE, buzz_wav
from test_choice_hints import choice_session


class BuzzTests(unittest.TestCase):
    def test_buzz_runs_its_length_then_fades_out_silent(self):
        with wave.open(BytesIO(buzz_wav()), 'rb') as file:
            self.assertEqual((file.getnchannels(), file.getsampwidth(), file.getframerate()), (1, 2, RATE))
            self.assertEqual(file.getnframes(), RATE * BUZZ_MS // 1000 + math.ceil(RAMP * RATE) + 1)   # then the 12 ms ramp
            frames = file.readframes(file.getnframes())
        samples = [int.from_bytes(frames[i:i + 2], 'little', signed=True) for i in range(0, len(frames), 2)]
        self.assertEqual((samples[0], samples[-1]), (0, 0))
        self.assertLessEqual(max(map(abs, samples)), round(32767 * AMPLITUDE))
        self.assertGreater(max(map(abs, samples)), 0.9 * 32767 * AMPLITUDE)


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class DesktopBuzzTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        from exp_runtime.desktop import Desktop
        self.addCleanup(pygame.quit)
        self.ui = Desktop(choice_session(lambda refs: []), audio=False)
        self.ui.audio, self.ui._sync_music = True, Mock()
        patcher = patch('pygame.mixer.Sound')
        self.Sound = patcher.start()
        self.addCleanup(patcher.stop)

    def test_each_request_buzzes_once_at_the_sound_volume(self):
        ui, engine = self.ui, self.ui.session.engine
        ui.sound_volume = 0.5
        ui._sync_audio()
        self.Sound.assert_not_called()
        engine.vibration_serial += 1
        ui._sync_audio()
        ui._sync_audio()
        self.assertEqual(self.Sound.return_value.play.call_count, 1)
        self.Sound.return_value.set_volume.assert_called_with(0.5)

    def test_sound_off_and_a_restored_session_stay_silent(self):
        ui, engine = self.ui, self.ui.session.engine
        ui.sound_enabled = False
        engine.vibration_serial += 1
        ui._sync_audio()
        ui.sound_enabled = True
        engine.vibration_serial = 0         # an unsaved counter restarts in a restored session
        ui._sync_audio()
        self.Sound.return_value.play.assert_not_called()
        engine.vibration_serial += 1
        ui._sync_audio()
        self.assertEqual(self.Sound.return_value.play.call_count, 1)

    def test_the_vibration_switch_silences_the_buzz(self):
        ui, engine = self.ui, self.ui.session.engine
        ui.command(('pause_toggle', 'vibration'))
        self.assertFalse(ui.vibration_enabled)
        engine.vibration_serial += 1
        ui._sync_audio()
        self.Sound.return_value.play.assert_not_called()
        ui.command(('pause_toggle', 'vibration'))
        engine.vibration_serial += 1
        ui._sync_audio()
        self.assertEqual(self.Sound.return_value.play.call_count, 1)


if __name__ == '__main__':
    unittest.main()
