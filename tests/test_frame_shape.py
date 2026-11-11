"""General's Aspect Ratio (owner, 2026-11-11): the frame's shape, this device's own setting."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from exp_runtime import frame_shape
from exp_runtime.settings import AppSettings


class FrameShapeTests(unittest.TestCase):
    def test_the_shapes_keep_the_frames_width_and_grow_taller(self):
        for choice, height in (('3:4', 512), ('2:3', 576), ('9:16', 384 * 16 / 9)):
            with self.subTest(choice):
                self.assertEqual(frame_shape.frame_units(choice, (100, 100)), (384, height))

    def test_fit_screen_takes_the_windows_shape_within_its_limits(self):
        phone = (1080, 2400)                                    # a g54: 9:20
        self.assertAlmostEqual(frame_shape.frame_units('fit', phone, fixed_window=True)[1], 384 * 20 / 9)
        self.assertEqual(frame_shape.frame_units('fit', (2400, 1080), fixed_window=True)[1], 512)   # wider: 3:4
        self.assertEqual(frame_shape.frame_units('fit', (1080, 4000), fixed_window=True)[1], 384 * 21 / 9)  # narrowest
        self.assertEqual(frame_shape.frame_units('fit', (960, 1440), fixed_window=True)[1], 576)    # a phone's 2:3
        self.assertEqual(frame_shape.frame_units('fit', (0, 0)), (384, 512))

    def test_a_computer_shows_2_3_only_when_it_is_picked(self):
        # Between 3:4 and 2:3 a location's panning fades out, so a window of that shape keeps 3:4 (owner, 2026-11-11).
        for size in ((960, 1440), (1000, 1400), (960, 1280)):
            with self.subTest(size):
                self.assertEqual(frame_shape.frame_units('fit', size)[1], 512)
        self.assertAlmostEqual(frame_shape.frame_units('fit', (900, 1600))[1], 384 * 16 / 9)    # taller: follows
        self.assertEqual(frame_shape.frame_units('2:3', (1000, 1440))[1], 576)

    def test_phones_default_to_fit_screen_and_computers_to_3_4(self):
        self.assertEqual(frame_shape.default(True), 'fit')
        self.assertEqual(frame_shape.default(False), '3:4')


class AspectSettingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'settings.json'

    def test_it_is_kept_beside_start_in_and_none_means_the_devices_default(self):
        settings = AppSettings(self.path)
        self.assertIsNone(settings.aspect_ratio)
        self.assertEqual((settings.aspect(True), settings.aspect(False)), ('fit', '3:4'))
        settings.set_aspect_ratio('9:16')
        again = AppSettings(self.path)
        self.assertEqual((again.aspect_ratio, again.aspect(True)), ('9:16', '9:16'))
        again.set_aspect_ratio(None)
        self.assertIsNone(AppSettings(self.path).aspect_ratio)
        with self.assertRaises(ValueError):
            settings.set_aspect_ratio('16:9')

    def test_it_never_travels_with_the_shared_preferences(self):
        # Sync and backups carry the shared preferences (sync_flow.shared_options, progress_bundle's options.json),
        # never settings.json's own fields, so this device's shape stays its own.
        from exp_runtime.menu import SHARED_PREFERENCES
        settings = AppSettings(self.path)
        settings.set_aspect_ratio('2:3')
        self.assertNotIn('aspect_ratio', SHARED_PREFERENCES)
        self.assertEqual(settings.preferences, {})
        self.assertEqual(json.loads(self.path.read_text())['aspect_ratio'], '2:3')

    def test_a_damaged_value_is_left_at_the_default(self):
        self.path.write_text(json.dumps(dict(version=1, check_for_updates=True, aspect_ratio='wide')))
        self.assertIsNone(AppSettings(self.path).aspect_ratio)


class AppAspectTests(unittest.TestCase):
    def app(self, fixed_window=False):
        from exp_runtime.application import Application
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        app = Application.__new__(Application)
        app.settings = AppSettings(Path(temporary.name) / 'settings.json')
        app.fixed_window = fixed_window
        app.game = SimpleNamespace(aspect_ratio='3:4')
        return app

    def test_a_change_reaches_the_open_game_and_steps_round_the_shapes(self):
        app = self.app()
        app.set_aspect_ratio('2:3')
        self.assertEqual((app.settings.aspect_ratio, app.game.aspect_ratio), ('2:3', '2:3'))
        self.assertEqual(app.next_aspect_ratio(), '9:16')
        app.set_aspect_ratio('fit')
        self.assertEqual(app.next_aspect_ratio(), '3:4')
        phone = self.app(fixed_window=True)
        phone.set_aspect_ratio(None)
        self.assertEqual(phone.game.aspect_ratio, 'fit')

    def test_the_pause_menus_choice_is_kept_by_the_app(self):
        app = self.app(fixed_window=True)
        app.state = SimpleNamespace(persist=Mock())
        game = app.game = SimpleNamespace(aspect_ratio='fit')
        for key in ('music_enabled', 'sound_enabled', 'controller_confirm', 'grid_controls', 'vibration_enabled',
                    'device_vibration_enabled', 'choice_hints', 'skip_minigames', 'skip_ad_intros', 'autoplay',
                    'disable_choice_timer', 'hd_backdrop', 'hires_portraits', 'ms3_characters', 'java_look',
                    'brew_08_backgrounds', 'smartphone_music', 'word_grid_skin', 'grids_as_memory', 'skip_ahead', 'undo',
                    'ch_portraits', 'ch_backdrop', 'arena_minigames', 'arena_skin'):
            setattr(game, key, False)
        game.music_volume = game.sound_volume = .5
        app.save_game_settings()
        self.assertIsNone(app.settings.aspect_ratio)            # unchanged: the phone's default isn't written down
        game.aspect_ratio = '9:16'
        app.save_game_settings()
        self.assertEqual(app.settings.aspect_ratio, '9:16')


class PauseMenuAspectTests(unittest.TestCase):
    def test_a_shape_picked_in_the_pause_menu_is_used_and_kept(self):
        import os
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        import pygame
        pygame.display.init()
        from exp_runtime.desktop import Desktop
        ui = Desktop.__new__(Desktop)
        ui.press, ui._sync_text_input, ui._menu_sound = Mock(), Mock(), Mock()
        ui.fade, ui.session = None, SimpleNamespace(transitioning=False)
        ui.pause_hd, ui.on_settings = Mock(), Mock()
        ui.command(('pause_cycle', 'aspect_ratio', '9:16'))
        self.assertEqual(ui.aspect_ratio, '9:16')
        ui.on_settings.assert_called_once_with()
        ui.pause_hd.back.assert_called_once_with()              # back to General from the choice page
        ui.command(('pause_cycle', 'aspect_ratio'))             # a button stepping through them
        self.assertEqual(ui.aspect_ratio, 'fit')
        ui.window = pygame.Surface((1080, 2400))
        ui.fixed_window = True
        self.assertAlmostEqual(ui.frame_units()[1], 384 * 20 / 9)
        from exp_runtime.desktop_pause_hd import ASPECT_NAMES
        self.assertEqual(list(ASPECT_NAMES), list(frame_shape.CHOICES))


if __name__ == '__main__':
    unittest.main()
