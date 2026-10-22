"""Service 82: this fork's simulated buzz (vibration.py) and exp-runtime's device vibration (take_vibrations)."""
import importlib.util
from io import BytesIO
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import wave

from exp_runtime.choice_hints import preview_choices
from exp_runtime.runtime import Session
from exp_runtime.vibration import AMPLITUDE, BUZZ_MS, RAMP, RATE, buzz_wav
from test_choice_hints import choice_session
from test_runtime import Resources, host_call, text_words
from test_vm import program


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
        self.ui.vibration_enabled = True      # switched on: the buzz is off by default
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
        ui.audio = True
        ui.command(('pause_toggle', 'vibration'))        # switched on: one buzz of feedback (setVibrationEnabled)
        self.assertEqual(self.Sound.return_value.play.call_count, 1)
        engine.vibration_serial += 1
        ui._sync_audio()
        self.assertEqual(self.Sound.return_value.play.call_count, 2)


def resources(game):
    result = Resources(program(*host_call(82), *host_call(82), 0x33))
    result.library.game_id = game
    return result


class VibrationTests(unittest.TestCase):
    def test_requests_drain_once_and_never_replay_from_saved_progress(self):
        for game in ('shs', 'cod'):
            with self.subTest(game=game):
                r = resources(game)
                session = Session(r)
                self.assertEqual(session.advance().name, 'finished')
                before = session.snapshot()
                self.assertEqual(Session.from_snapshot(r, before).take_vibrations(), 0)
                self.assertEqual(session.take_vibrations(), 2)
                self.assertEqual(session.take_vibrations(), 0)
                session.tick(1000)
                self.assertEqual(session.take_vibrations(), 0)
                self.assertEqual(session.snapshot(), before)

    def test_choice_previews_do_not_request_live_device_feedback(self):
        words, refs = text_words('Choose', 'One|Two', 'Prompt', 'Continue')
        for game in ('shs', 'cod'):
            with self.subTest(game=game):
                r = Resources(program(*host_call(1, *refs[:3], 0, 0, -1, -1, 0),
                                      *host_call(82), *host_call(13, refs[3], 0), 0x33, words=words))
                r.library.game_id = game
                session = Session(r); session.advance(); session.tick(250)
                before = session.snapshot()
                preview_choices(session)
                self.assertEqual(session.take_vibrations(), 0)
                self.assertEqual(session.snapshot(), before)
                session.answer(0)
                self.assertEqual(session.take_vibrations(), 1)


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra required')
class PlayerVibrationTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        self.addCleanup(pygame.quit)

    def test_disabled_preference_applies_to_the_first_script_in_a_session(self):
        from exp_runtime.desktop import Desktop
        for enabled in (False, True):
            with self.subTest(enabled=enabled), patch('exp_runtime.graphics.vibrate') as vibrate:
                ui = Desktop(Session(resources('shs')), audio=False, vibration_enabled=enabled)
                self.assertEqual(vibrate.call_count, 2 if enabled else 0)
                ui.vibration_enabled = True
                ui.tick(0); ui.render(); ui.render()
                self.assertEqual(vibrate.call_count, 2 if enabled else 0)

    def test_vibration_is_independent_of_audio_and_discards_inactive_requests(self):
        from exp_runtime.desktop import Desktop
        ui = Desktop(Session(Resources(program(0x33))), audio=False)
        ui.music_enabled = ui.sound_enabled = False
        # (This fork has no closing pause menu of exp-runtime's; its HD pause menu closes at once.)
        for active, menu, enabled in ((False, False, True), (True, True, True), (True, False, False),
                                      (True, False, True)):
            with self.subTest(active=active, menu=menu, enabled=enabled), \
                    patch('exp_runtime.graphics.vibrate') as vibrate:
                ui.active, ui.menu_open, ui.vibration_enabled = active, menu, enabled
                ui.session = Session(resources('cod'))
                ui._attempt(ui.session.advance)
                expected = 2 if active and not menu and enabled else 0
                self.assertEqual(vibrate.call_count, expected)
                ui.active, ui.menu_open, ui.vibration_enabled = True, False, True
                ui.tick(0)
                self.assertEqual(vibrate.call_count, expected)


class NativeVibrationTests(unittest.TestCase):
    def test_native_bridge_drains_feedback_and_drops_background_or_unsupported_requests(self):
        from PIL import Image
        from exp_runtime import graphics
        from exp_runtime.app_icon import icon_surface
        from exp_runtime.platforms.drawing import Backend
        from exp_runtime.platforms.ios import Host
        from native_host_fonts import FontHost
        font = FontHost()

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            icon = root / 'authored-icon.png'; Image.new('RGBA', (2, 2), 'green').save(icon)
            backend = Backend(font, icon)
            previous = graphics.install(backend)
            self.addCleanup(graphics.install, previous)
            icon_surface.cache_clear()
            self.addCleanup(icon_surface.cache_clear)
            host = Host(root, backend=backend, library_root=root / 'libraries', check_updates=False)
            self.addCleanup(host.app.close)
            host.request(dict(vibration_available=True))
            self.assertTrue(graphics.supports_vibration())
            graphics.vibrate(); graphics.vibrate()
            self.assertEqual(host.request({})['vibrations'], 2)
            self.assertEqual(host.request({})['vibrations'], 0)
            graphics.vibrate()
            self.assertEqual(host.request(dict(operation='active', active=False))['vibrations'], 0)
            self.assertEqual(host.request(dict(operation='active', active=True))['vibrations'], 0)
            graphics.vibrate()
            self.assertEqual(host.request(dict(vibration_available=False))['vibrations'], 0)
            self.assertFalse(graphics.supports_vibration())
            graphics.vibrate()
            self.assertEqual(host.request(dict(vibration_available=True))['vibrations'], 0)
