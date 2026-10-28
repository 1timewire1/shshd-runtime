"""Controllers on the desktop (gamepad.py): buttons and the left stick read as keys, and service 82 as rumble."""
import importlib.util
import os
import unittest
from unittest.mock import Mock, patch


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class GamepadTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        from exp_runtime import gamepad, graphics
        self.pygame, self.gamepad, self.graphics = pygame, gamepad, graphics
        self.pad = Mock()
        self.pad.as_joystick.return_value.get_instance_id.return_value = 7
        controller = Mock()
        controller.Controller.return_value = self.pad
        self.pads = gamepad.Gamepads(controller)
        previous = graphics.install_gamepads(self.pads)
        self.addCleanup(graphics.install_gamepads, previous)

    def frame(self, *events, now=0):
        with patch('pygame.event.get', return_value=[self.pygame.event.Event(t, **a) for t, a in events]):
            return [(e.type, getattr(e, 'key', None)) for e in self.pads.events(now)]

    def button(self, name, down=True, instance_id=7):
        pygame = self.pygame
        return (pygame.CONTROLLERBUTTONDOWN if down else pygame.CONTROLLERBUTTONUP,
                dict(button=getattr(pygame, 'CONTROLLER_BUTTON_' + name), instance_id=instance_id))

    def stick(self, axis, value):
        return (self.pygame.CONTROLLERAXISMOTION,
                dict(axis=getattr(self.pygame, 'CONTROLLER_AXIS_LEFT' + axis), value=value, instance_id=7))

    def test_buttons_are_the_keys_the_player_already_answers(self):
        pygame, down = self.pygame, self.pygame.KEYDOWN
        self.assertEqual(self.frame(self.button('A'), self.button('B'), self.button('START'), self.button('X'),
                                    self.button('BACK'), self.button('A', down=False)),
                         [(down, pygame.K_RETURN), (down, pygame.K_ESCAPE), (down, pygame.K_ESCAPE),
                          (down, pygame.K_BACKSPACE), (down, pygame.K_TAB)])
        click = (pygame.MOUSEBUTTONDOWN, dict(button=1, pos=(0, 0)))
        self.assertEqual(self.frame(click, self.button('GUIDE')), [(pygame.MOUSEBUTTONDOWN, None)])

    def test_a_held_direction_repeats_until_released(self):
        k = self.pygame.K_DOWN
        down = (self.pygame.KEYDOWN, k)
        self.assertEqual(self.frame(self.button('DPAD_DOWN'), now=0), [down])
        self.assertEqual(self.frame(now=self.gamepad.REPEAT_DELAY_MS - 1), [])
        self.assertEqual(self.frame(now=self.gamepad.REPEAT_DELAY_MS), [down])
        self.assertEqual(self.frame(now=self.gamepad.REPEAT_DELAY_MS + self.gamepad.REPEAT_MS - 1), [])
        self.assertEqual(self.frame(now=self.gamepad.REPEAT_DELAY_MS + self.gamepad.REPEAT_MS), [down])
        self.assertEqual(self.frame(self.button('DPAD_DOWN', down=False), now=10_000), [])
        self.frame(self.button('A'), now=0)
        self.assertEqual(self.frame(now=10_000), [])        # only directions repeat

    def test_the_left_stick_presses_once_per_push_with_hysteresis(self):
        pygame, full = self.pygame, self.gamepad.AXIS_RANGE
        self.assertEqual(self.frame(self.stick('X', round(.4 * full))), [])
        self.assertEqual(self.frame(self.stick('X', round(.6 * full))), [(pygame.KEYDOWN, pygame.K_RIGHT)])
        self.assertEqual(self.frame(self.stick('X', round(.35 * full))), [])         # still held: no second press
        self.assertEqual(self.frame(self.stick('X', round(.2 * full))), [])          # released
        self.assertEqual(self.frame(self.stick('Y', -full)), [(pygame.KEYDOWN, pygame.K_UP)])
        self.assertEqual(self.frame(now=10_000), [(pygame.KEYDOWN, pygame.K_UP)])    # held, it repeats
        self.frame(self.stick('Y', 0))
        self.assertEqual(self.frame(now=20_000), [])     # back at rest it does not

    def test_a_connected_controller_rumbles_for_the_vibrator(self):
        pygame, graphics = self.pygame, self.graphics
        self.assertFalse(graphics.supports_vibration())
        graphics.vibrate()
        self.frame((pygame.CONTROLLERDEVICEADDED, dict(device_index=0)))
        self.assertTrue(graphics.supports_vibration())
        graphics.vibrate()
        self.pad.rumble.assert_called_once_with(self.gamepad.RUMBLE_STRENGTH, self.gamepad.RUMBLE_STRENGTH,
                                                self.gamepad.RUMBLE_MS)
        self.frame((pygame.CONTROLLERDEVICEREMOVED, dict(instance_id=7)))
        self.assertFalse(graphics.supports_vibration())
        self.pad.quit.assert_called_once()

    def test_rumble_replaces_the_simulated_buzz(self):
        from exp_runtime.desktop import Desktop
        from exp_runtime.runtime import Session
        from test_vibration import resources
        self.addCleanup(self.pygame.quit)
        self.frame((self.pygame.CONTROLLERDEVICEADDED, dict(device_index=0)))
        with patch('pygame.mixer.Sound') as Sound:
            ui = Desktop(Session(resources('shs')), audio=False, vibration_enabled=True)
            ui.audio, ui._sync_music = True, Mock()
            ui._sync_audio()
            Sound.assert_not_called()
        self.assertEqual(self.pad.rumble.call_count, 2)      # the fixture's two service-82 requests


if __name__ == '__main__':
    unittest.main()
