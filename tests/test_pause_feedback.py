"""Pause feedback uses authored input, font and pixel fixtures."""
import importlib.util
import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from exp_runtime.runtime import Session
from test_runtime import Resources, branching_program


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class PauseFeedbackTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        from exp_runtime.desktop import Desktop
        self.pygame, self.Desktop = pygame, Desktop
        self.addCleanup(pygame.quit)

    def ui(self, resources=None):
        pg = self.pygame
        ui = self.Desktop(Session(resources or Resources(branching_program())), audio=False)
        if ui.session.pending.name == 'choice':
            ui.tick(250)
        ui.viewport = pg.Rect(80, 0, 480, 720)  # A letterboxed window.
        ui.buttons = [(pg.Rect(0, 633, 90, 87), ('menu',)),
                      (pg.Rect(0, 0, 480, 720), ('continue',))]
        return ui

    def pointer(self, ui, phase, point=(110, 660)):
        pg = self.pygame
        ui.handle_event(pg.event.Event({'down': pg.MOUSEBUTTONDOWN, 'move': pg.MOUSEMOTION,
                                       'up': pg.MOUSEBUTTONUP}[phase], button=1, pos=point))

    def test_gear_holds_and_releases_in_shared_panel_and_minigame_input(self):
        from test_character_picker import picker_resources
        from test_football import resources as football_resources
        from test_minigames import word_resources
        from test_word_grid import resources as grid_resources
        for factory in (lambda: Resources(branching_program()), picker_resources,
                        football_resources, word_resources, grid_resources):
            ui = self.ui(factory())
            with self.subTest(panel=ui.session.pending.name):
                before = ui.session.snapshot()
                self.pointer(ui, 'down')
                self.assertEqual(ui.press.pressed, ('menu',))
                self.assertFalse(ui.menu_open)
                self.assertEqual(ui.session.snapshot(), before)
                self.pointer(ui, 'move', (300, 300))
                self.assertIsNone(ui.press.pressed)
                self.pointer(ui, 'move')
                self.assertEqual(ui.press.pressed, ('menu',))
                self.pointer(ui, 'up')
                self.assertTrue(ui.menu_open)
                ui.tick(200)
                self.assertEqual(ui.pause_elapsed_ms, 200)
                self.assertEqual(ui.session.snapshot(), before)
                ui.active = False
                ui.tick(200)
                self.assertEqual(ui.pause_elapsed_ms, 200)

    def test_drag_out_focus_cancel_and_replaced_panel_never_open_pause(self):
        pg = self.pygame
        for reason in ('outside', 'focus', 'cancel', 'replacement'):
            ui = self.ui()
            before = ui.session.snapshot()
            self.pointer(ui, 'down')
            if reason == 'focus':
                ui.handle_event(pg.event.Event(pg.WINDOWFOCUSLOST))
            elif reason == 'cancel':
                ui.cancel_pointer()
            elif reason == 'replacement':
                ui.session = Session(Resources(branching_program()))
                ui.session.advance()
                before = ui.session.snapshot()
            self.pointer(ui, 'up', (10, 660) if reason == 'outside' else (110, 660))
            self.assertFalse(ui.menu_open, reason)
            self.assertIsNone(ui.press.pressed, reason)
            self.assertEqual(ui.session.snapshot(), before, reason)

    def test_opening_gate_does_not_consume_a_held_touch_as_resume(self):
        pg = self.pygame
        ui = self.ui()
        self.pointer(ui, 'down'); self.pointer(ui, 'up')
        ui.buttons = [(pg.Rect(0, 0, 480, 720), ('resume',))]
        self.pointer(ui, 'down')
        ui.tick(400)
        self.pointer(ui, 'up')
        self.assertTrue(ui.menu_open)
        self.pointer(ui, 'down'); self.pointer(ui, 'up')
        self.assertFalse(ui.menu_open)

    def test_gear_uses_original_alternate_frame_without_rescaling_the_layout(self):
        from exp_runtime.desktop_pause import draw_pause_gear
        pg = self.pygame
        pg.display.init(); pg.display.set_mode((1, 1))
        frames = {}
        for index, color in ((49, (90, 90, 90)), (50, (255, 150, 0))):
            frames[index] = pg.Surface((60, 72)); frames[index].fill(color)
        art = SimpleNamespace(frame=lambda bank, index: frames[index], gear_pressed=False)
        target = pg.Surface((480, 720))
        draw_pause_gear(target, art, scale=1.5)
        self.assertEqual(target.get_at((20, 650))[:3], (90, 90, 90))
        art.gear_pressed = True
        draw_pause_gear(target, art, scale=1.5)
        self.assertEqual(target.get_at((20, 650))[:3], (255, 150, 0))

    def test_native_zoom_timing_has_fixed_endpoints_and_symmetric_easing(self):
        from exp_runtime.desktop_pause import pause_scale
        self.assertEqual(pause_scale(0), .001)
        self.assertAlmostEqual(pause_scale(200), .5005, places=5)
        self.assertEqual(pause_scale(400), 1)
        self.assertEqual(pause_scale(5000), 1)
        self.assertLess(pause_scale(100), .25)
        self.assertGreater(pause_scale(300), .75)

    def test_a_notice_window_zooms_in_and_takes_no_input_until_open(self):
        from exp_runtime.desktop_pause import PAUSE_OPEN_MS
        ui = self.ui()
        pressed = []
        ui.notice_stack = SimpleNamespace(stack=[28], current=28, press=pressed.append, pop=lambda: None)
        ui.notice_windows = SimpleNamespace(hits=[(self.pygame.Rect(0, 0, 768, 1024), ('item', 1))])
        ui.notice_data = SimpleNamespace(action=lambda number: number)
        ui.bg_viewport = self.pygame.Rect(0, 0, 768, 1024)
        ui.notice_shown, ui.notice_ms = 28, 0                    # just opened (as `_draw_notice` sets it)
        click = lambda kind: ui._notice_pointer(self.pygame.event.Event(kind, button=1, pos=(10, 10)))
        click(self.pygame.MOUSEBUTTONDOWN); click(self.pygame.MOUSEBUTTONUP)
        self.assertEqual(pressed, [])
        ui.tick(PAUSE_OPEN_MS)
        self.assertEqual(ui.notice_ms, PAUSE_OPEN_MS)
        click(self.pygame.MOUSEBUTTONDOWN); click(self.pygame.MOUSEBUTTONUP)
        self.assertEqual(pressed, [1])

    def test_both_games_play_open_and_row_sounds_from_base_bank_and_respect_mute(self):
        for game, opening, click in (('shs', 8011, 8010), ('cod', 8006, 8005)):
            ui = self.ui()
            ui.audio = True
            ui._sync_music = Mock()
            ui.session.resources.library.game_id = game
            ui.session.resources.library.read_asset = Mock(side_effect=lambda asset: str(asset).encode())
            ui.session.resources.read_asset = Mock(side_effect=AssertionError('Episode bank used for UI sound'))
            before = ui.session.snapshot()
            with patch('pygame.mixer.Sound') as sound:
                ui.command(('menu',))
                self.assertEqual(sound.call_args.kwargs['file'].getvalue(), str(opening).encode())
                ui.command(('menu',))  # Repeated open cannot restart the sound/animation.
                self.assertEqual(sound.return_value.play.call_count, 1)
                ui.command(('resume',))
                self.assertEqual(sound.call_args.kwargs['file'].getvalue(), str(click).encode())
                ui.music_enabled = False
                ui.command(('menu',)); ui.command(('resume',))
                self.assertEqual(sound.call_count, 2)
                self.assertEqual(sound.return_value.play.call_count, 4)
                ui.sound_enabled = False
                ui.command(('menu',)); ui.command(('resume',))
                self.assertEqual(sound.return_value.play.call_count, 4)
                self.assertEqual(ui.session.snapshot(), before)
                self.assertEqual([c.args[0] for c in ui.session.resources.library.read_asset.call_args_list],
                                 [opening, click])

    def test_picker_continue_resumes_paused_without_the_gear_sound(self):
        from exp_runtime.application import Application
        for kind, paused in (('continue', True), ('new', False)):
            with self.subTest(kind=kind):
                app = Application.__new__(Application)
                app.shell, app.saved = None, set()
                app.picker = SimpleNamespace(popup=object())
                app.game = self.ui()
                app.game._menu_sound = Mock()

                def start(*, resume, app=app):
                    app.screen = 'game'
                app.start = start
                app.picker_command((kind, 'episode'))
                self.assertIsNone(app.picker.popup)
                self.assertEqual(app.game.menu_open, paused)
                self.assertEqual(app.game.pause_elapsed_ms == 0, paused)     # the zoom starts from its first frame
                self.assertEqual(app.skip_elapsed, paused)
                app.game._menu_sound.assert_not_called()                      # resumed paused with no gear sound
