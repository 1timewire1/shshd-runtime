"""One-shot device feedback stays separate from saves, previews and audio."""
import base64
import importlib.util
from io import BytesIO
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from exp_runtime.choice_hints import preview_choices
from exp_runtime.runtime import Session
from test_runtime import Resources, host_call, text_words
from test_vm import program


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
        for active, menu, closing, enabled in ((False, False, 0, True), (True, True, 0, True),
                                               (True, False, 100, True), (True, False, 0, False),
                                               (True, False, 0, True)):
            with self.subTest(active=active, menu=menu, closing=closing, enabled=enabled), \
                    patch('exp_runtime.graphics.vibrate') as vibrate:
                ui.active, ui.menu_open, ui.pause_closing_ms, ui.vibration_enabled = active, menu, closing, enabled
                ui.session = Session(resources('cod'))
                ui._attempt(ui.session.advance)
                expected = 2 if active and not menu and not closing and enabled else 0
                self.assertEqual(vibrate.call_count, expected)
                ui.active, ui.menu_open, ui.pause_closing_ms, ui.vibration_enabled = True, False, 0, True
                ui.tick(0)
                self.assertEqual(vibrate.call_count, expected)


class NativeVibrationTests(unittest.TestCase):
    def test_native_bridge_drains_feedback_and_drops_background_or_unsupported_requests(self):
        from PIL import Image, ImageDraw, ImageFont
        from exp_runtime import graphics
        from exp_runtime.app_icon import icon_surface
        from exp_runtime.platforms.drawing import Backend
        from exp_runtime.platforms.ios import Host

        def font(request):
            face = ImageFont.load_default(size=request['size'])
            width, height = max(1, round(face.getlength(request['text']))), request['size'] + 5
            result = dict(width=width, height=height)
            if not request.get('measure'):
                image = Image.new('RGBA', (width, height))
                ImageDraw.Draw(image).text((0, 0), request['text'], font=face, fill=tuple(request['color']))
                stream = BytesIO(); image.save(stream, format='PNG')
                result['png'] = base64.b64encode(stream.getvalue()).decode('ascii')
            return result

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
