import copy
import importlib.util
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from exp_runtime.runtime import Session
from test_character_picker import picker_resources
from test_runtime import Resources, host_call, text_words
from test_vm import program


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra required')
class PresentationControlTests(unittest.TestCase):
    def make_ui(self, resources):
        import pygame
        from exp_runtime.desktop import Desktop
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        self.addCleanup(pygame.quit)
        ui = Desktop(Session(resources), audio=False)
        ui.viewport = pygame.Rect(0, 0, 480, 720)
        return ui

    def test_cod_menu_entry_switches_under_black_without_a_story_callback(self):
        import pygame
        from exp_runtime.application import Application
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        app = Application(Path(temporary.name) / 'empty', audio=False, game_key='cod', check_updates=False)
        self.addCleanup(app.close)
        words, (line,) = text_words('An authored opening scene.')
        resources = Resources(program(*host_call(13, line, 0), 0x33, words=words))
        resources.library.game_id, resources.library.kind = 'cod', 'ipa'
        ui = self.make_ui(resources)
        held = copy.deepcopy(ui.session.snapshot())
        app.state = SimpleNamespace(sound=False, checkpoint=lambda session: None)
        app.screen, app.history = 'episode', ['main']
        def start(**kwargs):
            app.screen, app.game = 'game', ui
        with patch.object(app, 'start', side_effect=start) as begin:
            app.command(('start', False))
            self.assertFalse(app.ready)
            app.tick(600)
            self.assertEqual(app.game_entry.coverage, .5)
            app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
            app.command(('start', True))
            begin.assert_not_called()
            app.active = False
            app.tick(9000)
            self.assertEqual(app.game_entry.elapsed_ms, 600)
            app.active = True
            app.tick(899)
            begin.assert_not_called()
            app.tick(1)
            begin.assert_called_once_with(resume=False)
            self.assertEqual(app.game_entry.phase, 3)
            self.assertEqual(app.game_entry.coverage, 1)
            self.assertEqual(ui.session.vm.snapshot(), held['vm'])
            self.assertEqual(ui.session.snapshot()['engine']['random'], held['engine']['random'])
            self.assertTrue(ui.session.engine.dialogue_animation.complete)
            incoming = copy.deepcopy(ui.session.snapshot())
            app.tick(1499)
            app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
            self.assertEqual(ui.session.snapshot(), incoming)
            app.tick(1)
            self.assertIsNone(app.game_entry)
            self.assertIsNone(ui.entry_transition)
            self.assertEqual(ui.session.engine.dialogue_animation.presentation_ms, 1)
            self.assertEqual(ui.session.vm.snapshot(), held['vm'])

    def test_failed_cod_menu_entry_releases_the_input_gate(self):
        from exp_runtime.application import Application
        from exp_runtime.exp import ContentError
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        app = Application(Path(temporary.name) / 'empty', audio=False, game_key='cod', check_updates=False)
        self.addCleanup(app.close)
        app.screen = 'episode'
        app.start_from_menu()
        with patch.object(app, 'start', side_effect=ContentError('Missing episode')), self.assertLogs(level='WARNING'):
            app.tick(1500)
        self.assertIsNone(app.game_entry)
        self.assertTrue(app.ready)
        self.assertEqual(app.message, 'Missing episode')

    def test_picker_press_tracks_drag_off_reentry_and_cancel_without_answering(self):
        import pygame
        ui = self.make_ui(picker_resources())
        held = ui.session.snapshot()
        def event(kind, position):
            ui.handle_event(pygame.event.Event(kind, pos=tuple(value * 1.5 for value in position), button=1))
        event(pygame.MOUSEBUTTONDOWN, (240, 365))
        self.assertTrue(ui.picker_pressed)
        event(pygame.MOUSEMOTION, (300, 400))
        self.assertFalse(ui.picker_pressed)
        event(pygame.MOUSEMOTION, (240, 365))
        self.assertTrue(ui.picker_pressed)
        self.assertEqual(ui.session.snapshot(), held)
        ui.cancel_pointer()
        self.assertFalse(ui.picker_pressed)
        event(pygame.MOUSEBUTTONUP, (240, 365))
        self.assertEqual(ui.session.snapshot(), held)
        event(pygame.MOUSEBUTTONDOWN, (240, 365))
        event(pygame.MOUSEBUTTONUP, (240, 365))
        self.assertIsNone(ui.session.engine.character_picker)

    def test_ios_pause_settles_layers_holds_timers_and_resumes_after_close(self):
        words, (line,) = text_words('An authored dialogue line.')
        resources = Resources(program(*host_call(13, line, 0), 0x33, words=words))
        resources.library.kind = 'ipa'
        ui = self.make_ui(resources)
        held = ui.session.vm.snapshot()
        motion = ui.session.engine.dialogue_animation
        clock = motion.presentation_ms
        self.assertFalse(motion.complete)
        ui.command(('menu',))
        self.assertTrue(motion.complete)
        self.assertEqual(motion.presentation_ms, clock)
        paused = copy.deepcopy(ui.session.snapshot())
        ui.tick(1000)
        self.assertEqual(ui.session.snapshot(), paused)
        ui.command(('resume',))
        ui.tick(399)
        self.assertEqual(ui.session.snapshot(), paused)
        ui.command(('continue',))
        self.assertEqual(ui.session.vm.snapshot(), held)
        ui.tick(1)
        self.assertEqual(ui.pause_closing_ms, 0)
        ui.tick(17)
        self.assertEqual(motion.presentation_ms, clock + 17)
        self.assertEqual(ui.session.vm.snapshot(), held)

