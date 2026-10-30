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

    def test_general_vibration_rumbles_the_controller_and_the_buzz_stays_its_own_switch(self):
        """A connected controller is the device's vibrator: General's Vibration rumbles it for service 82. Sound's
        Simulated Vibration Sound is a separate switch (off here), so nothing buzzes."""
        from exp_runtime.desktop import Desktop
        from exp_runtime.runtime import Session
        from test_vibration import resources
        self.addCleanup(self.pygame.quit)
        self.frame((self.pygame.CONTROLLERDEVICEADDED, dict(device_index=0)))
        with patch('pygame.mixer.Sound') as Sound:
            ui = Desktop(Session(resources('shs')), audio=False, vibration_enabled=False, device_vibration_enabled=True)
            ui.audio, ui._sync_music = True, Mock()
            ui._sync_audio()
            Sound.assert_not_called()
        self.assertEqual(self.pad.rumble.call_count, 2)      # the fixture's two service-82 requests
        self.pad.rumble.reset_mock()
        ui = Desktop(Session(resources('shs')), audio=False, device_vibration_enabled=False)
        ui._sync_audio = Mock()
        ui._sync_vibration()
        self.pad.rumble.assert_not_called()                  # General's Vibration off: no rumble

    def presses(self, *events, now=0):
        with patch('pygame.event.get', return_value=[self.pygame.event.Event(t, **a) for t, a in events]):
            return [(e.controller, e.key) for e in self.pads.events(now)]

    def test_each_press_names_its_button_and_a_nintendo_layout_swaps_what_the_face_buttons_mean(self):
        """Buttons by position (a Switch Pro's B is `south`); confirm is the bottom button, or the right one."""
        pygame, faces = self.pygame, ('A', 'B', 'X', 'Y')
        self.assertEqual(self.presses(*(self.button(name) for name in faces)),
                         [('south', pygame.K_RETURN), ('east', pygame.K_ESCAPE), ('west', pygame.K_BACKSPACE),
                          ('north', pygame.K_i)])
        self.pads.confirm = 'east'
        self.assertEqual(self.presses(*(self.button(name) for name in faces)),
                         [('south', pygame.K_ESCAPE), ('east', pygame.K_RETURN), ('west', pygame.K_i),
                          ('north', pygame.K_BACKSPACE)])
        self.assertEqual(self.presses(self.button('RIGHTSTICK'), self.button('START')),
                         [('r3', pygame.K_UNKNOWN), ('start', pygame.K_ESCAPE)])

    def test_a_trigger_presses_once_past_half_its_travel(self):
        pygame, full = self.pygame, self.gamepad.AXIS_RANGE

        def trigger(value):
            return (pygame.CONTROLLERAXISMOTION, dict(axis=pygame.CONTROLLER_AXIS_TRIGGERLEFT, value=value,
                                                      instance_id=7))
        self.assertEqual(self.presses(trigger(round(.4 * full))), [])
        self.assertEqual(self.presses(trigger(round(.6 * full)), trigger(full)), [('lt', pygame.K_UNKNOWN)])
        self.assertEqual(self.presses(trigger(round(.2 * full)), trigger(round(.7 * full))), [('lt', pygame.K_UNKNOWN)])


class ControllerScreenTests(unittest.TestCase):
    """Football's plays by position, the word grid's highlighted cell, notices' buttons by key."""

    def desktop(self, pending, **fields):
        from types import SimpleNamespace
        from exp_runtime.desktop import Desktop
        ui = Desktop.__new__(Desktop)
        ui.press, ui.gear_pointer_down, ui._sync_text_input = Mock(), False, Mock()
        ui.fade, ui.menu_open, ui.error, ui.host_prompt, ui.notice_stack = None, False, None, None, None
        ui.pause_closing, ui._tree_zoom = False, SimpleNamespace(tab=None, showing=False)
        ui.session = SimpleNamespace(pending=SimpleNamespace(name=pending), transitioning=False,
                                     engine=SimpleNamespace(**fields), grid_pointer=Mock())
        ui.command, ui._attempt = Mock(), (lambda operation: operation())
        return ui

    def key(self, ui, key, button=None):
        from exp_runtime.gamepad import key_event
        return ui.handle_event(key_event(key, button))

    def test_football_takes_its_nine_plays_by_position_and_from_the_number_pad(self):
        import pygame
        ui = self.desktop('football', word_grid=None)
        for button, slot in (('lt', 0), ('north', 1), ('rt', 2), ('west', 3), ('r3', 4), ('east', 5), ('lb', 6),
                             ('south', 7), ('rb', 8)):
            self.key(ui, pygame.K_UNKNOWN, button)
            self.assertEqual(ui.command.call_args.args[0], ('choose', slot))
        self.key(ui, pygame.K_ESCAPE, 'east')               # the right button is a play here, not the pause menu
        self.assertEqual(ui.command.call_args.args[0], ('choose', 5))
        self.key(ui, pygame.K_KP7)
        self.assertEqual(ui.command.call_args.args[0], ('choose', 0))
        self.key(ui, pygame.K_KP3)
        self.assertEqual(ui.command.call_args.args[0], ('choose', 8))
        self.key(ui, pygame.K_ESCAPE, 'start')              # Start still pauses
        self.assertEqual(ui.command.call_args.args[0], ('menu',))

    def test_the_word_grid_draws_a_word_from_a_highlighted_cell(self):
        import pygame
        from types import SimpleNamespace
        game = SimpleNamespace(problem=SimpleNamespace(width=3), board=list('ABCDEFGHI'), selection=[])
        ui = self.desktop('word_grid', word_grid=game)
        ui.grid_controls = 'tap'                              # (Hold is the default)
        grid = ui.session.grid_pointer
        self.key(ui, pygame.K_RETURN, 'south')                # the first key shows the highlight, in the middle
        self.assertEqual(ui.grid_cursor, 4)
        grid.assert_not_called()
        self.key(ui, pygame.K_UP, 'up')
        self.key(ui, pygame.K_LEFT, 'left')
        self.key(ui, pygame.K_LEFT, 'left')                   # held at the edge
        self.assertEqual(ui.grid_cursor, 0)
        self.key(ui, pygame.K_RETURN, 'south')
        grid.assert_called_with('down', 0)
        game.selection = [0]
        self.key(ui, pygame.K_RIGHT, 'right')
        self.key(ui, pygame.K_RETURN, 'south')
        grid.assert_called_with('move', 1)
        self.key(ui, pygame.K_BACKSPACE, 'west')              # let go, as lifting the finger
        grid.assert_called_with('up')

    def test_the_highlighted_cell_is_outlined_on_the_face_a_touch_is_tested_on(self):
        import pygame
        from types import SimpleNamespace
        from exp_runtime.desktop_word_hd import HdWordRenderer
        pygame.init()
        self.addCleanup(pygame.quit)
        renderer = HdWordRenderer.__new__(HdWordRenderer)
        renderer.canvas = pygame.Surface((768, 1024), pygame.SRCALPHA)
        game = SimpleNamespace(problem=SimpleNamespace(width=3, height=3), selection=[])
        renderer.cursor = None
        renderer.cursor_outline(game.problem)
        self.assertIsNone(renderer.canvas.get_bounding_rect().width or None)       # nothing without a highlight
        renderer.cursor = 4
        renderer.cursor_outline(game.problem)
        outline = renderer.canvas.get_bounding_rect()
        self.assertTrue(outline.width and outline.height)
        centre = outline.center
        self.assertEqual(renderer.hit((centre[0], centre[1] + 1), game), 4)          # around the middle cell

    def test_a_notice_takes_enter_on_its_only_button_and_the_arrows_on_several(self):
        import pygame
        from types import SimpleNamespace
        from exp_runtime.desktop_pause import PAUSE_OPEN_MS
        ui = self.desktop('dialogue')
        ui.notice_stack = SimpleNamespace(stack=[28], press=Mock(), pop=Mock())
        ui.notice_data = SimpleNamespace(action=lambda number: ('action', number))
        ui.notice_windows = SimpleNamespace(hits=[(pygame.Rect(0, 0, 1, 1), ('item', 80))])
        ui.notice_ms = PAUSE_OPEN_MS
        self.key(ui, pygame.K_RETURN, 'south')
        ui.notice_stack.press.assert_called_once_with(('action', 80))
        ui.notice_windows.hits = [(pygame.Rect(0, 0, 1, 1), ('item', 17)), (pygame.Rect(0, 0, 1, 1), ('item', 18))]
        ui.notice_stack.press.reset_mock()
        self.key(ui, pygame.K_RETURN, 'south')                # two buttons: the first is highlighted
        self.assertEqual(ui.notice_focus, ('item', 17))
        self.key(ui, pygame.K_RIGHT, 'right')
        self.key(ui, pygame.K_RETURN, 'south')
        ui.notice_stack.press.assert_called_once_with(('action', 18))

    def test_steering_reads_eight_ways_from_the_stick_or_two_dpad_buttons(self):
        from exp_runtime import gamepad
        pads = gamepad.Gamepads(Mock())
        self.assertEqual(pads.steering(), (0, 0))
        pads.down = {(1, 'up'), (1, 'left')}
        self.assertEqual(pads.steering(), (-1, -1))
        pads.down = {(1, 'south')}
        self.assertTrue(pads.holding('confirm'))
        pads.confirm = 'east'
        self.assertFalse(pads.holding('confirm'))
        pads.sticks = {1: [.7, .7]}
        self.assertEqual(pads.steering(), (1, 1))
        pads.sticks = {1: [.9, .2]}
        self.assertEqual(pads.steering(), (1, 0))
        pads.sticks = {1: [.2, .2]}                         # inside the dead zone
        self.assertEqual(pads.steering(), (0, 0))

    def test_hold_mode_drags_a_word_while_confirm_is_held(self):
        """Word Grid Controls' Hold: confirm down lays the finger on the highlighted cell; held, the steering adds each
        cell the highlight reaches (diagonals too); let go, the finger lifts."""
        import pygame
        from types import SimpleNamespace
        from exp_runtime import graphics
        game = SimpleNamespace(problem=SimpleNamespace(width=3), board=list('ABCDEFGHI'), selection=[])
        ui = self.desktop('word_grid', word_grid=game)
        ui.grid_controls, ui.active = 'hold', True
        pads = SimpleNamespace(held=True, steer=(0, 0))
        pads.holding = lambda button: pads.held
        pads.steering = lambda: pads.steer
        previous = graphics.install_gamepads(pads)
        self.addCleanup(graphics.install_gamepads, previous)
        grid = ui.session.grid_pointer
        self.key(ui, pygame.K_RETURN, 'south')                # the highlight first, in the middle
        self.key(ui, pygame.K_RETURN, 'south')
        grid.assert_called_with('down', 4)
        self.assertTrue(ui.grid_drag)
        pads.steer = (1, -1)                                 # up and right, as one diagonal step
        ui._grid_hold(16)
        grid.assert_called_with('move', 2)
        ui._grid_hold(16)                                    # held: the next step waits for its turn
        grid.assert_called_with('move', 2)
        self.key(ui, pygame.K_LEFT, 'left')                  # the arrows' own presses do not move it during a drag
        self.assertEqual(ui.grid_cursor, 2)
        pads.held = False
        ui._grid_hold(16)
        grid.assert_called_with('up')
        self.assertFalse(ui.grid_drag)

    def test_vibration_is_the_controller_pages_when_only_a_controller_vibrates(self):
        from exp_runtime.desktop_pause_hd import HdPauseMenu
        menu = HdPauseMenu.__new__(HdPauseMenu)
        phone = dict(device_vibration=True)
        pad = dict(device_vibration=True, controller_confirm='Bottom', grid_controls='Tap', controller_vibration=True)
        self.assertIn('device_vibration', [key for _, _, key in menu.option_rows('general', phone, [])])
        self.assertNotIn('device_vibration', [key for _, _, key in menu.option_rows('general', pad, [])])
        self.assertEqual([key for _, _, key in menu.option_rows('controller', pad, [])],
                         ['controller_confirm', 'grid_controls', 'device_vibration'])

    def test_the_controller_page_shows_while_a_controller_is_connected(self):
        from exp_runtime import gamepad, graphics
        from exp_runtime.desktop_pause_hd import HdPauseMenu
        menu = HdPauseMenu.__new__(HdPauseMenu)
        self.assertEqual(menu.option_rows('controller', {}, []), [])
        self.assertEqual(menu.option_rows('controller', {'controller_confirm': 'Bottom'}, []),
                         [('cycle', 'Confirm Button', 'controller_confirm')])
        pads = gamepad.Gamepads(Mock())
        previous = graphics.install_gamepads(pads)
        self.addCleanup(graphics.install_gamepads, previous)
        self.assertFalse(graphics.controller_connected())
        pads.pads[1] = Mock()
        self.assertTrue(graphics.controller_connected())


if __name__ == '__main__':
    unittest.main()
