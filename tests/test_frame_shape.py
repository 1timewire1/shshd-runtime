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
    def test_3_4_and_2_3_keep_hds_width_and_9_16_is_the_column_wide(self):
        # 3:4 is HD's own frame; 2:3 only grows taller; from 9:16 the frame is the 320-unit column, as on SD's iPhone
        # screen (owner, 2026-11-11).
        for choice, size in (('3:4', (384, 512)), ('2:3', (384, 576)), ('9:16', (320, 320 * 16 / 9))):
            with self.subTest(choice):
                self.assertEqual(frame_shape.frame_units(choice, (100, 100)), size)

    def test_between_2_3_and_9_16_the_width_goes_from_one_to_the_other(self):
        self.assertEqual(frame_shape.width_for(0.75), 384)
        self.assertEqual(frame_shape.width_for(2 / 3), 384)
        self.assertAlmostEqual(frame_shape.width_for((2 / 3 + 9 / 16) / 2), 352)        # halfway
        self.assertTrue(352 < frame_shape.width_for(0.625) < 384)                       # a 10:16 tablet
        self.assertEqual(frame_shape.width_for(9 / 16), 320)
        self.assertEqual(frame_shape.width_for(9 / 20), 320)

    def test_fit_screen_takes_the_windows_shape_within_its_limits(self):
        phone = (1080, 2400)                                    # a g54: 9:20
        self.assertAlmostEqual(frame_shape.frame_units('fit', phone, fixed_window=True)[1], 320 * 20 / 9)
        self.assertEqual(frame_shape.frame_units('fit', (2400, 1080), fixed_window=True), (384, 512))   # wider: 3:4
        self.assertAlmostEqual(frame_shape.frame_units('fit', (1080, 4000), fixed_window=True)[1], 320 * 21 / 9)
        self.assertEqual(frame_shape.frame_units('fit', (960, 1440), fixed_window=True), (384, 576))    # a phone's 2:3
        self.assertEqual(frame_shape.frame_units('fit', (0, 0)), (384, 512))

    def test_a_computer_shows_2_3_only_when_it_is_picked(self):
        # Between 3:4 and 2:3 a location's panning fades out, so a window of that shape keeps 3:4 (owner, 2026-11-11).
        for size in ((960, 1440), (1000, 1400), (960, 1280)):
            with self.subTest(size):
                self.assertEqual(frame_shape.frame_units('fit', size)[1], 512)
        self.assertAlmostEqual(frame_shape.frame_units('fit', (900, 1600))[1], 320 * 16 / 9)    # taller: follows
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
        self.assertAlmostEqual(ui.frame_units()[1], 320 * 20 / 9)
        from exp_runtime.desktop_pause_hd import ASPECT_NAMES
        self.assertEqual(list(ASPECT_NAMES), list(frame_shape.CHOICES))


if __name__ == '__main__':
    unittest.main()


class BackgroundShapeTests(unittest.TestCase):
    """A location's picture in each shape (owner, 2026-11-11): HD's at 3:4, whole at 2:3, SD's iPhone view from 9:16."""

    def setUp(self):
        import os
        os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
        import pygame
        from exp_runtime.desktop import Desktop
        from exp_runtime.location_pan import LocationPan
        self.pygame, self.LocationPan = pygame, LocationPan

        class Frame:
            _background_placement = Desktop._background_placement
            _shaped_placement = Desktop._shaped_placement
            _location_pans = Desktop._location_pans
            STRIP_RISE = Desktop.STRIP_RISE
        self.Frame = Frame

    def ui(self, units, align=2, origin=(160, 180), hd=True):
        ui = self.Frame()
        ui.pending_background_origin = origin
        ui.dialogue_renderer = SimpleNamespace(has_hd_bundle=lambda: hd, game_id=lambda: 'shs')
        ui.location_pan = self.LocationPan()
        ui.session = SimpleNamespace(engine=SimpleNamespace(panel=SimpleNamespace(location_align=align)))
        if units is not None:
            ui._frame_width, ui._frame_tall = units
        return ui

    def place(self, choice, art=(960, 1440), **options):
        units = frame_shape.frame_units(choice, (1080, 2400), fixed_window=True)
        target = (768, round(768 * units[1] / units[0]))
        return self.ui(units, **options)._background_placement(self.pygame.Surface(art), target), target

    def test_3_4_is_hds(self):
        art = self.pygame.Surface((960, 1440))
        self.assertEqual(self.ui(None)._background_placement(art, (768, 1024)), (-96, -337, 960, 1440))
        self.assertEqual(self.place('3:4')[0], (-96, -337, 960, 1440))

    def test_2_3_shows_the_whole_picture(self):
        for align in (1, 2, 3):
            with self.subTest(align):
                (x, y, w, h), target = self.place('2:3', align=align)
                self.assertEqual((round(x), round(y), round(w), round(h)), (0, 0, *target))

    def test_9_16_shows_it_as_sd_does_one_art_unit_a_unit(self):
        (x, y, w, h), (tw, th) = self.place('9:16')
        unit = tw / 320
        self.assertAlmostEqual(w / unit, 480)
        self.assertAlmostEqual(h / unit, 720, delta=.5)
        self.assertAlmostEqual(x, (tw - w) / 2)                             # centred speaker: centred
        self.assertTrue(y <= 0 and y + h >= th)                             # covers the frame
        for align, edge in ((1, 'left'), (3, 'right')):
            with self.subTest(edge):
                (x, y, w, h), _ = self.place('9:16', align=align)
                self.assertAlmostEqual(x if edge == 'left' else x + w - tw, 0)

    def test_past_its_height_the_picture_is_enlarged_to_the_frame(self):
        units = frame_shape.frame_units('fit', (900, 2400), fixed_window=True)      # past 9:21: 9:21
        target = (768, round(768 * units[1] / units[0]))
        x, y, w, h = self.ui(units)._background_placement(self.pygame.Surface((960, 1440)), target)
        self.assertAlmostEqual(y, 0)
        self.assertAlmostEqual(h, target[1], delta=1)
        self.assertGreater(w, target[0])

    def test_a_strip_keeps_its_size_and_rises_with_the_frame(self):
        strip = (2160, 720)                                                 # New Rules: 3:1
        (_, y34, _, h34), (_, th34) = self.place('3:4', art=strip, hd=False)
        (_, y, _, h), (tw, th) = self.place('9:16', art=strip, hd=False)
        unit = tw / 320
        self.assertAlmostEqual(h / unit, 160, delta=.5)                     # one art unit a unit, as at 3:4
        # The strip's bottom, units below the column's top: at 3:4 245; risen by half the height added past HD's frame.
        below_top = (y + h) / unit - (th / unit - 485.5)
        self.assertAlmostEqual((y34 + h34) / 2 - (512 - 485.5), 245, delta=.5)
        self.assertAlmostEqual(below_top, 245 - (320 * 16 / 9 - 512) / 2, delta=.5)


class FrameWideLayerTests(unittest.TestCase):
    def test_a_frame_wide_layer_is_known_at_any_density(self):
        import os
        os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
        from exp_runtime.desktop import frame_wide
        for scale in (2, 2.4, 2.2, 3):
            margin = round(32 * scale)
            with self.subTest(scale):
                self.assertTrue(frame_wide((round(320 * scale) + 2 * margin, round(480 * scale))))
                self.assertFalse(frame_wide((round(320 * scale), round(480 * scale))))      # the column alone


class TitleCardShapeTests(unittest.TestCase):
    def test_a_card_is_the_frames_shape_with_its_subtitle_kept_from_the_bottom(self):
        from exp_runtime.desktop_title import CodTitleRenderer, HdTitleRenderer
        card = object.__new__(HdTitleRenderer)
        self.assertEqual((card.canvas_size(), card.subtitle_region()), ((768, 1024), HdTitleRenderer.SUBTITLE_REGION))
        card.frame_units = frame_shape.frame_units('fit', (1080, 2400), fixed_window=True)       # a 9:20 phone
        self.assertEqual(card.canvas_size(), (768, round(768 * 20 / 9)))
        self.assertEqual(card.subtitle_region()[1], 544 + card.canvas_size()[1] - 1024)
        cod = object.__new__(CodTitleRenderer)
        self.assertEqual((cod.SCALE, cod.ORIGIN), (2, (64, 53)))                      # HD's frame: as before
        cod.frame_units = (320, 320 * 20 / 9)
        self.assertEqual(cod.SCALE, 2.4)                                               # the column the frame's width
        self.assertAlmostEqual(cod.ORIGIN[0], 0)
        self.assertAlmostEqual(cod.ORIGIN[1], cod.canvas_size()[1] - 485.5 * 2.4)


class BackdropFitTests(unittest.TestCase):
    """Step 2c: a translated pack's frame backdrop, lengthened so its bars stay round the strip."""

    def setUp(self):
        import os
        os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
        import pygame
        from exp_runtime import backdrop_fit
        self.pygame, self.fit = pygame, backdrop_fit

    def checks(self, width=384, height=512, square=16, bars=((92, 112), (272, 292))):
        """A checkerboard from the top with two yellow bars round the strip (rows 112-272), as the translators build
        them, one pixel per frame unit."""
        image = self.pygame.Surface((width, height), self.pygame.SRCALPHA)
        for y in range(0, height, square):
            for x in range(0, width, square):
                light = ((x // square) + (y // square)) % 2
                image.fill((160, 168, 220, 255) if light else (140, 150, 210, 255), (x, y, square, square))
        for top, bottom in bars:
            image.fill((230, 230, 0, 255), (0, top, width, bottom - top))
        return image

    def test_the_repeat_is_the_patterns_not_a_squares_rows(self):
        rows = self.fit._rows(self.checks())
        self.assertEqual(self.fit.repeat(rows, 300, 500), 32)
        self.assertEqual(self.fit.repeat(rows, 2, 14), 1)             # inside one square's rows: plain

    def test_the_bars_follow_the_strip_and_the_pattern_runs_on(self):
        image = self.checks()
        long = self.fit.lengthen(image, (112, 272), (112 + 171, 272 + 171), 683)
        self.assertEqual(long.get_size(), (384, 683))
        yellow = [y for y in range(683) if long.get_at((5, y))[:3] == (230, 230, 0)]
        self.assertEqual((yellow[0], yellow[-1]), (92 + 171, 291 + 171))    # both bars, moved with the strip
        # Above the upper bar and below the lower one, every row is the row a whole repeat away: no seams.
        rows = self.fit._rows(long)
        for lo, hi in ((0, 92 + 171), (292 + 171, 683)):
            self.assertTrue(all(rows[y] == rows[y + 32] for y in range(lo, hi - 32)), (lo, hi))
        # The bottom of the picture is its own, as at 3:4.
        self.assertEqual(rows[-200:], self.fit._rows(image)[-200:])


class WindowShapeTests(unittest.TestCase):
    """2f: a computer's window takes a picked shape at its own height; Fit Screen leaves it to the person."""

    def app(self, choice, size, fixed_window=False):
        import os
        os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
        import pygame
        pygame.display.init()
        self.addCleanup(pygame.display.quit)
        from exp_runtime.application import Application
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        app = Application.__new__(Application)
        app.settings = AppSettings(Path(temporary.name) / 'settings.json')
        app.settings.set_aspect_ratio(choice)
        app.fixed_window, app.game = fixed_window, None
        app.window = pygame.display.set_mode(size, pygame.RESIZABLE)
        return app

    def test_a_picked_shape_reshapes_the_window_at_its_height(self):
        for choice, width in (('9:16', 405), ('2:3', 480), ('3:4', 540)):
            with self.subTest(choice):
                app = self.app(choice, (540, 720))
                app.shape_window()
                self.assertEqual(app.window.get_size(), (width, 720))

    def test_fit_screen_a_wide_window_and_a_phone_are_left_as_they_are(self):
        for choice, size, fixed in (('fit', (500, 900), False), ('9:16', (960, 720), False), ('9:16', (1080, 2400), True)):
            with self.subTest(choice=choice, size=size):
                app = self.app(choice, size, fixed)
                app.shape_window()
                self.assertEqual(app.window.get_size(), size)


class MenuFrameTests(unittest.TestCase):
    """3 (menus, stage 1): a menu's frame is 768 points across and the frame's shape, never shorter than HD's 1024."""

    app = WindowShapeTests.app

    def test_heights(self):
        for choice, size, fixed, height in (('3:4', (768, 1707), True, 1024), ('2:3', (768, 1707), True, 1152),
                                            ('9:16', (768, 1707), True, 1365), ('fit', (1080, 2400), True, 1707),
                                            ('fit', (1200, 900), False, 1024), ('fit', (700, 1000), False, 1024)):
            with self.subTest(choice=choice, size=size):
                self.assertEqual(self.app(choice, size, fixed).menu_frame(), (768, height))
