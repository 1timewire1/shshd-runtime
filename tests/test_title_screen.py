"""Authored title cards and optional checks of player-supplied intro assets."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from exp_runtime.atlas import AtlasFont
from exp_runtime.runtime import SaveError, Session
from exp_runtime.title_screen import TitleScreen, title_labels
from exp_runtime.ui_assets import Rect
from test_runtime import Resources, host_call, text_words
from test_vm import program


def resources(title='Chapter $N', subtitle='A new beginning.', *, negative=None, flag=0):
    words, (first, second) = text_words(title, subtitle)
    return Resources(program((0x1a, 77), *host_call(8, first if negative is None else negative,
                                                 second, 1000, flag),
                             0x21, (0x1f, 0xfe02), 0x33, words=words))


def bank():
    rects = {9: Rect(14, 41, 302, 188), 10: Rect(9, 253, 295, 176)}
    return SimpleNamespace(rectangle=lambda layout, node: rects[node])


def font(height):
    return AtlasFont(4, 1, -1, height, {code: (0, 0, 8) for code in range(33, 127)})


class TitleScreenTests(unittest.TestCase):
    def test_early_taps_reveal_without_acknowledging_and_callback_preserves_result_cells(self):
        for negative in (None, -1, -2, -32768):
            with self.subTest(negative=negative):
                s = Session(resources(negative=negative, flag=-2))
                s.engine.strings['$N'] = 'One'
                s.engine.result_cells[0] = 42
                action = s.advance()
                self.assertEqual(action.details['title'], 'Chapter One' if negative is None else '')
                self.assertEqual(action.details['flag'], -2)
                held = s.vm.snapshot()
                self.assertIs(s.answer(), action)
                self.assertEqual(s.engine.title_screen.reveal_width, 320)
                self.assertIs(s.answer(), action)  # A queued second tap cannot acknowledge.
                s.tick(33)
                self.assertFalse(s.engine.title_screen.ready)
                self.assertEqual(s.vm.snapshot(), held)
                s.tick(1)
                self.assertTrue(s.engine.title_screen.ready)
                self.assertEqual(s.answer().request.args, (77, 0))
                self.assertIsNone(s.engine.title_screen)
                self.assertEqual(s.engine.result_cells[0], 42)

    def test_wipe_gate_tweens_and_clock_partitioning(self):
        a, b = TitleScreen(), TitleScreen()
        for elapsed, width, ready, alpha, scale in ((500, 75, False, 0., .5),
                                                   (1000, 150, False, 0., 1.),
                                                   (1666, 245, False, 666 / 3000, 1.),
                                                   (1667, 250, True, 667 / 3000, 1.),
                                                   (4000, 320, True, 1., 1.)):
            delta = elapsed - a.elapsed_ms
            a.tick(delta)
            while delta:
                part = min(delta, 17)
                b.tick(part)
                delta -= part
            self.assertEqual(a, b)
            self.assertEqual((a.reveal_width, a.ready), (width, ready))
            self.assertAlmostEqual(a.background_alpha, alpha)
            self.assertAlmostEqual(a.subtitle_scale_y, scale)
            a.validate()
        a.tick(100000)
        self.assertEqual(a, b)

    def test_saved_entrance_and_random_transition_resume_once(self):
        for skip in (False, True):
            for elapsed in (0, 500, 1666, 1667, 4000):
                with self.subTest(skip=skip, elapsed=elapsed):
                    r = resources()
                    s = Session(r)
                    s.engine.scene_value = 20
                    s.advance()
                    s.tick(elapsed)
                    if skip and not s.engine.title_screen.ready:
                        s.answer()
                    saved = json.loads(json.dumps(s.snapshot()))
                    untouched = copy.deepcopy(saved)
                    restored = Session.from_snapshot(r, saved)
                    self.assertEqual(saved, untouched)
                    self.assertEqual(restored.snapshot(), s.snapshot())
                    random = copy.deepcopy(s.engine.random48)
                    restored.tick(4000)
                    self.assertEqual(restored.vm.snapshot(), s.vm.snapshot())
                    self.assertEqual(restored.engine.random48, random)
                    restored.answer()
                    random.next()
                    self.assertEqual(restored.engine.random48, random)
                    self.assertEqual(restored.engine.scene_value, 0)
                    self.assertEqual(restored.pending.request.args, (77, 0))

    def test_old_saves_settle_the_intro_and_invalid_current_saves_are_rejected(self):
        r = resources()
        s = Session(r)
        s.advance()
        original = s.snapshot()
        for version in (9, 10):
            old = copy.deepcopy(original)
            old['version'] = version
            del old['engine']['title_screen']
            restored = Session.from_snapshot(r, old)
            self.assertEqual(restored.vm.snapshot(), s.vm.snapshot())
            self.assertEqual(restored.engine.title_screen, TitleScreen.settled())
            self.assertEqual(restored.answer().request.args, (77, 0))
        for key, value in (('elapsed_ms', -1), ('elapsed_ms', 4001), ('reveal_width', 12),
                           ('reveal_width', 325), ('ready', True)):
            bad = copy.deepcopy(original)
            bad['engine']['title_screen'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(SaveError):
                Session.from_snapshot(r, bad)
        for field, value in (('title', 'Wrong title'), ('subtitle', 'Wrong subtitle'),
                             ('asset_id', 1001), ('flag', 1)):
            bad = copy.deepcopy(original)
            bad['pending']['details'][field] = value
            with self.subTest(field=field), self.assertRaises(SaveError):
                Session.from_snapshot(r, bad)
        bad = copy.deepcopy(original)
        bad['engine']['title_screen'] = None
        with self.assertRaises(SaveError):
            Session.from_snapshot(r, bad)

    def test_native_atlas_positions_right_alignment_and_long_subtitle_branch(self):
        title, sub = title_labels(bank(), font(33), font(23), 'ABC\nDE', 'AB\nC')
        self.assertEqual((title.asset_id, title.origin, title.scale), (528, (4, 84), .85))
        self.assertEqual([(g.x, g.y) for g in title.glyphs],
                         [(0, -33), (7, -33), (14, -33), (0, 1), (7, 1)])
        self.assertEqual((sub.asset_id, sub.origin), (530, (0, 390)))
        self.assertEqual([(g.x, g.y) for g in sub.glyphs], [(305, -23), (312, -23), (312, 1)])
        _, sub = title_labels(bank(), font(33), font(23), '', 'A' * 25)
        self.assertEqual(sub.glyphs[0].y, -42)
        _, sub = title_labels(bank(), font(33), font(23), '', 'A ' * 50)
        self.assertEqual(sub.origin, (0, 315))
        self.assertEqual(sub.glyphs[0].y, -23)
        self.assertGreater(sub.glyphs[-1].y, sub.glyphs[0].y)


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class TitleRendererTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        pygame.display.init()
        pygame.display.set_mode((480, 720))
        self.addCleanup(pygame.quit)

    def test_authored_atlas_pixels_wipe_background_fade_and_subtitle_scale(self):
        import pygame
        from exp_runtime.desktop_title import TitleRenderer
        metrics, images = {}, {}
        for asset, height in ((528, 33), (530, 23)):
            images[asset] = pygame.Surface((8, height), pygame.SRCALPHA)
            images[asset].fill((240, 220, 20))
            glyphs = b''.join(struct.pack('>Bhhb', code, 0, 0, 8) for code in range(33, 127))
            metrics[asset + 1] = struct.pack('>bBbhb', 4, 1, -1, 94, height) + glyphs
        images[1000] = pygame.Surface((64, 48))
        images[1000].fill((60, 120, 180))
        transparent = pygame.Surface((1, 1), pygame.SRCALPHA)
        r = resources(title='A' * 35, subtitle='BC')
        r.read_asset = metrics.__getitem__
        r.dialogue_layout = lambda: SimpleNamespace(bank=bank())
        renderer = TitleRenderer(r, Mock(), SimpleNamespace(image=images.get, frame=lambda *_: transparent,
                                                     draw_bottom_bar=lambda *args, **kwargs: None))
        renderer.hint = Mock(return_value=None)
        s = Session(r)
        s.advance()
        target = pygame.Surface((320, 480))
        renderer.draw(target, s)
        self.assertEqual(target.get_at((10, 60))[:3], (0, 0, 0))
        # SDL smoothscale backends round resampled alpha/color differently.
        for actual, expected in zip(target.get_at((310, 385))[:3], (240, 220, 20)):
            self.assertAlmostEqual(actual, expected, delta=8)
        s.tick(500)
        saved = s.snapshot()
        buttons = renderer.draw(target, s)
        self.assertEqual(s.snapshot(), saved)
        for actual, expected in zip(target.get_at((10, 60))[:3], (240, 220, 20)):
            self.assertAlmostEqual(actual, expected, delta=8)
        self.assertEqual(target.get_at((100, 60))[:3], (0, 0, 0))
        self.assertEqual(buttons[0][1], ('menu',))
        s.tick(2000)
        renderer.draw(target, s)
        # The background is no longer blitted into target/canvas directly --
        # Desktop composites it separately, at real window resolution, from
        # these tracked fields (see desktop.py's _draw_background_layer).
        self.assertIs(renderer.pending_background, images[1000])
        self.assertAlmostEqual(renderer.pending_background_alpha, 128, delta=1)
        s.tick(1500)
        renderer.draw(target, s)
        self.assertIs(renderer.pending_background, images[1000])
        self.assertEqual(renderer.pending_background_alpha, 255)

    @unittest.skipUnless(Path('.shs-library/library.json').is_file(), 'user content is absent')
    def test_original_week_and_episode_intro_render_pause_resize_and_saved_pixels(self):
        import pygame
        from exp_runtime.content import ContentError, ContentLibrary
        from exp_runtime.desktop import Desktop
        with ContentLibrary(Path('.shs-library')) as library:
            checked = 0
            for episode in ('Football Star', 'The_New_Girl.exp'):
                try:
                    library.select(episode)
                except ContentError:
                    continue
                s = Session(library.open_episode(episode))
                ui = Desktop(s, audio=False)
                self.assertEqual(s.pending.name, 'presentation')
                held, frames = s.vm.snapshot(), set()
                for elapsed in (0, 500, 1000, 1667, 2500, 4000):
                    s.tick(elapsed - s.engine.title_screen.elapsed_ms)
                    ui.render()
                    self.assertIsNone(ui.error)
                    self.assertEqual(s.vm.snapshot(), held)
                    before = pygame.image.tobytes(ui.canvas, 'RGB')
                    frames.add(before)
                    ui.session = Session.from_snapshot(s.resources, s.snapshot())
                    ui.render()
                    self.assertEqual(pygame.image.tobytes(ui.canvas, 'RGB'), before)
                    ui.session = s
                self.assertGreaterEqual(len(frames), 5)
                saved = s.snapshot()
                ui.command(('menu',))
                ui.tick(5000)
                self.assertEqual(s.snapshot(), saved)
                ui.command(('resume',))
                ui.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST))
                ui.tick(5000)
                self.assertEqual(s.snapshot(), saved)
                ui.handle_event(pygame.event.Event(pygame.WINDOWFOCUSGAINED))
                ui.window = pygame.display.set_mode((800, 600), pygame.RESIZABLE)
                ui.render()
                point = ui.viewport.center
                ui.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=point))
                self.assertNotEqual(s.vm.snapshot(), held)
                self.assertIsNone(s.engine.title_screen)
                checked += 1
            if not checked:
                self.skipTest('The reference episodes are not in the local library')
