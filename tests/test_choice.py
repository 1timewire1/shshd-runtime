import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from exp_runtime.choice import ChoiceLayout
from exp_runtime.content import ContentLibrary
from exp_runtime.fonts import BitmapFont, Glyph, layout_text
from exp_runtime.runtime import Session
from exp_runtime.vm import VMError
from exp_runtime.ui_assets import Layout, LayoutBank, LayoutNode
from test_runtime import Resources, answer_screen, host_call, text_words
from test_vm import program


def timed_resources(service=1, timeout=2000, count=3, default=1):
    labels = [f'Option {i}' for i in range(count)]
    words, refs = text_words('Choose', 'A question.', '|'.join(labels), *labels)
    if service == 1:
        calls = host_call(1, refs[0], refs[2], refs[1], timeout, default, -1, -1, 1)
    else:
        calls = host_call(2, refs[0], refs[1], timeout, default, -1, 1)
        for i, ref in enumerate(refs[3:]):
            calls += host_call(3, ref, 100 + i, 1)
        calls += host_call(4, 0)
    return Resources(program(*calls, 0x21, (0x1f, 0xfe01), words=words))


def authored_layout():
    font = BitmapFont('Authored choice', 14, 16, 'unused.png',
                      {c: Glyph(c, 0, 0, 3, 6, 0, 0, 7) for c in range(32, 127)}, {})
    geometry = LayoutNode((0, 0, 256, 20), (0, 0, 0, 0), 6, ())
    layouts = [Layout(280, 40, (geometry,) * 9) for _ in range(67)]
    # Different dimensions and solid art exercise the timer without native assets.
    clock = LayoutNode((130, 0, 150, 20), (0, 0, 0, 0), 17, (2, 9))
    hidden_score = LayoutNode((175, 0, 205, 20), (0, 0, 0, 0), 23, (66,))
    layouts[22] = Layout(280, 40, (geometry,) * 9 + (clock, geometry, geometry, hidden_score))
    layouts[66] = Layout(30, 20, (LayoutNode((0, 0, 30, 20), (0, 0, 0, 0), 17, (2, 10)),))
    layout = ChoiceLayout.__new__(ChoiceLayout)
    layout.bank = LayoutBank(3, 0, 0, (), tuple(layouts))
    layout.font = lambda _: font
    return layout


class ChoiceTimingTests(unittest.TestCase):
    def test_both_choice_forms_expire_after_zero_and_keep_their_result_mapping(self):
        for game in ('shs', 'cod'):
            for service, result in ((1, 1), (2, 101)):
                with self.subTest(game=game, service=service):
                    r = timed_resources(service); r.library.game_id = game
                    s = Session(r); s.advance()
                    s.engine.result_cells[0] = 42
                    held = s.vm.snapshot()
                    s.tick(2000)
                    self.assertEqual(s.remaining_ms, 0)
                    self.assertEqual(s.vm.snapshot(), held)
                    self.assertEqual(s.engine.result_cells[0], 42)
                    saved = json.loads(json.dumps(s.snapshot()))
                    restored = Session.from_snapshot(r, saved)
                    self.assertEqual(restored.tick(0).name, 'choice')
                    self.assertEqual(restored.tick(1).request.args, (result,))
                    self.assertEqual(restored.engine.result_cells[0], result)
                    # A click at exactly zero still wins before the next active tick.
                    self.assertEqual(s.answer(2).request.args, (2 if service == 1 else 102,))

    def test_cod_observed_timeout_sentinels_survive_save_and_resume_once(self):
        # Explicit compatibility policy; the native out-of-bounds read has no
        # defined callback. In-range indices still use the mapped values above.
        for default in (-1, 1000):
            with self.subTest(default=default):
                r = timed_resources(2, default=default); r.library.game_id = 'cod'
                s = Session(r); s.advance(); held = s.vm.snapshot()
                s.tick(2000)
                self.assertEqual(s.vm.snapshot(), held)
                restored = Session.from_snapshot(r, json.loads(json.dumps(s.snapshot())))
                self.assertEqual(restored.tick(0).name, 'choice')
                self.assertEqual(restored.tick(1).request.args, (default,))
                self.assertEqual(restored.engine.result_cells[0], default)
                after = restored.vm.snapshot()
                restored.tick(100)
                self.assertEqual(restored.vm.snapshot(), after)

    def test_other_invalid_timeouts_keep_the_pending_call_in_both_games(self):
        for game in ('shs', 'cod'):
            defaults = (-2, 3, 32767) if game == 'cod' else (-2, -1, 3, 1000, 32767)
            for default in defaults:
                with self.subTest(game=game, default=default):
                    r = timed_resources(2, default=default); r.library.game_id = game
                    s = Session(r); action = s.advance()
                    s.engine.result_cells[0] = 42
                    held = s.vm.snapshot()
                    with self.assertRaisesRegex(VMError, 'timeout index is out of range'):
                        s.tick(2001)
                    self.assertIs(s.pending, action)
                    self.assertEqual(s.vm.snapshot(), held)
                    self.assertEqual(s.engine.result_cells[0], 42)

    def test_nonpositive_durations_have_no_timer_and_do_not_expire(self):
        for service in (1, 2):
            for timeout in (-1, 0):
                s = Session(timed_resources(service, timeout)); s.advance()
                before = s.snapshot()
                s.tick(100000)
                self.assertIsNone(s.remaining_ms)
                self.assertEqual(s.snapshot(), before)
                self.assertIsNone(authored_layout().page(s.pending.details).timer_panel)

    def test_timer_has_room_below_rows_and_stays_visible_above_scrolling_choices(self):
        layout = authored_layout()
        for count in (2, 3, 9):
            s = Session(timed_resources(count=count)); s.advance()
            page = layout.page(s.pending.details)
            self.assertLessEqual(page.timer_panel.y + page.timer_panel.height, 421)
            last = page.rows[-1].rect
            self.assertEqual(last.y + last.height - page.max_scroll, page.timer_panel.y)
            plain = layout.page(dict(s.pending.details, timeout_ms=0))
            self.assertEqual(page.box.height - plain.box.height, 20)
            self.assertIsNone(plain.timer_panel)


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class ChoiceTimerRenderTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        pygame.display.init(); pygame.display.set_mode((320, 480))
        self.addCleanup(pygame.quit)

    def renderer(self):
        import pygame
        from exp_runtime.desktop_choice import ChoiceRenderer
        from exp_runtime.desktop_dialogue import DialogueRenderer
        layout = authored_layout()
        def frame(asset, index):
            surface = pygame.Surface((20, 20), pygame.SRCALPHA)
            surface.fill({708: (0, 200, 0), 709: (200, 0, 0)}.get(asset, (80, 80, 80)))
            if asset not in (708, 709) and index == 10:
                self.fail('Ordinary choices must hide the score capsule')
            return surface
        art = DialogueRenderer.__new__(DialogueRenderer)
        art.frame, art.image = frame, lambda _: None
        art.box = lambda *args, **kwargs: None
        text = SimpleNamespace(layout=lambda name, value, width, style:
                               layout_text(layout.font(name), value, width, style),
                               draw_layout=lambda *args: None)
        renderer = ChoiceRenderer(None, text, art)
        renderer.layout = layout
        return renderer

    def test_clock_sweep_restores_from_saved_time_and_rendering_does_not_advance_vm(self):
        import pygame
        for service in (1, 2):
            with self.subTest(service=service):
                r = timed_resources(service); s = Session(r); s.advance()
                renderer = self.renderer()
                target = pygame.Surface((320, 480))
                before = s.snapshot()
                page, _ = renderer.draw(target, s)
                self.assertEqual(s.snapshot(), before)
                clock = renderer.layout.bank.rectangle(22, 10, page.timer_panel)
                right, left = (clock.x + 15, clock.y + 5), (clock.x + 5, clock.y + 5)
                self.assertEqual(target.get_at(right)[:3], (0, 200, 0))
                s.tick(1000)
                renderer.draw(target, s)
                self.assertEqual(target.get_at(right)[:3], (200, 0, 0))
                self.assertEqual(target.get_at(left)[:3], (0, 200, 0))
                pixels = pygame.image.tobytes(target, 'RGB')
                restored = Session.from_snapshot(r, json.loads(json.dumps(s.snapshot())))
                renderer.draw(target, restored)
                self.assertEqual(pygame.image.tobytes(target, 'RGB'), pixels)
                self.assertEqual(restored.vm.snapshot(), before['vm'])
                restored.tick(1000)
                renderer.draw(target, restored)
                self.assertEqual(target.get_at(left)[:3], (200, 0, 0))
                self.assertEqual(restored.pending.name, 'choice')

    def test_scroll_keeps_timer_fixed_and_out_of_option_hit_rectangles(self):
        import pygame
        s = Session(timed_resources(count=9)); s.advance(); s.tick(1000)
        renderer = self.renderer(); target = pygame.Surface((320, 480))
        page, buttons = renderer.draw(target, s)
        panel = pygame.Rect(page.timer_panel.x, page.timer_panel.y,
                            page.timer_panel.width, page.timer_panel.height)
        pixels = pygame.image.tobytes(target.subsurface(panel), 'RGB')
        for scroll in (0, page.max_scroll // 2, page.max_scroll):
            _, buttons = renderer.draw(target, s, scroll=scroll)
            self.assertEqual(pygame.image.tobytes(target.subsurface(panel), 'RGB'), pixels)
            self.assertTrue(all(not rect.colliderect(panel) for rect, _ in buttons))
        self.assertIn(('choose', 8), [command for _, command in buttons])
        self.assertEqual(s.pending.name, 'choice')


@unittest.skipUnless(Path('.shs-library/library.json').is_file(), 'user library is not present')
class ChoiceTests(unittest.TestCase):
    def resources(self):
        library = ContentLibrary(Path('.shs-library'))
        self.addCleanup(library.close)
        return library.open_episode('The_New_Girl.exp')

    def test_original_fonts_portrait_insets_and_variable_option_lengths(self):
        layout = ChoiceLayout(self.resources())
        details = dict(title='Make your choice!', text='Are you gonna make a move on her?',
                       options=['Definitely.', "Take another man's girl? No way!", "She's not really my type."],
                       enabled=[True, False, True])
        original = copy.deepcopy(details)
        page = layout.page(details, theme=1, has_portrait=True)
        self.assertEqual(details, original)
        self.assertEqual((page.box.x, page.box.width), (20, 280))
        self.assertEqual(page.title_font, 'PajamaHip26')
        self.assertEqual(len(page.title.lines), 2)
        self.assertEqual(page.portrait.center[0], 57)
        self.assertEqual([row.rect.height for row in page.rows], [44, 44, 44])
        self.assertEqual([row.index for row in page.rows], [0, 1, 2])
        self.assertFalse(page.rows[1].enabled)
        self.assertGreater(page.description.lines[0].x, 0)
        plain = layout.page(details, theme=2, has_portrait=False)
        self.assertEqual(plain.title_font, 'PajamaHip266')
        self.assertIsNone(plain.portrait)
        self.assertEqual(plain.description.lines[0].x, 0)

        details['options'] = ['A long option with multiple lines. ' * 4] * 9
        details['enabled'] = [True] * 9
        long = layout.page(details, theme=1, has_portrait=True)
        self.assertGreater(long.max_scroll, 0)
        self.assertEqual(len(long.rows), 9)
        for row in long.rows:
            _, top, _, bottom = row.text.ink_bounds
            self.assertGreater(row.rect.height, 44)
            self.assertGreaterEqual(row.origin[1] + top, row.rect.y)
            self.assertLessEqual(row.origin[1] + bottom, row.rect.y + row.rect.height)

    @unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
    def test_translucent_panel_matches_on_rgb_and_cocoa_default_canvases(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop import Desktop
        import pygame

        self.addCleanup(pygame.quit)
        resources = self.resources()
        ui = Desktop(Session(resources), audio=False)
        for _ in range(35):
            answer_screen(ui.session)
        saved = ui.session.snapshot()
        ui.render()
        expected = pygame.image.tobytes(ui.canvas, 'RGB')
        surface = pygame.Surface

        def cocoa_surface(size, flags=0, depth=0, masks=None):
            if depth == 0 and masks is None:
                return surface(size, flags, 32, (0xff0000, 0xff00, 0xff, 0xff000000))
            return surface(size, flags, depth) if masks is None else surface(size, flags, depth, masks)

        with patch('pygame.Surface', side_effect=cocoa_surface):
            simulated = Desktop(Session.from_snapshot(resources, saved), audio=False)
            simulated.render()
            self.assertIsNone(simulated.error)
            self.assertEqual(pygame.image.tobytes(simulated.canvas, 'RGB'), expected)

    @unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
    def test_native_choice_menu_timer_save_and_resized_selection(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop import Desktop
        import pygame

        self.addCleanup(pygame.quit)
        resources = self.resources()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        resources.library.directory = Path(temporary.name)
        words, (title, prompt, no, yes) = text_words('Make your choice!', 'A timed question.', 'No', 'Yes')
        resources.programs[65000] = program(
            *host_call(2, title, prompt, 1000, 1, -1, 0),
            *host_call(3, no, 77, 0), *host_call(3, yes, 88, 1),
            *host_call(4, 0), 0x21, (0x1f, 0xfe01), words=words)
        ui = Desktop(Session(resources, start_script=65000), audio=False)
        before = ui.session.snapshot()
        ui.render()
        self.assertIsNone(ui.error)
        self.assertEqual(before, ui.session.snapshot())
        self.assertEqual([command for _, command in ui.buttons], [('choose', 1), ('menu',)])

        ui.command(('menu',))
        ui.render()
        ui.tick(5000)
        ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_2))
        self.assertEqual(before, ui.session.snapshot())
        ui.command(('save',))
        self.assertTrue(ui.session.save_path.is_file())
        ui.command(('load',))
        self.assertFalse(ui.menu_open)
        self.assertEqual(before, ui.session.snapshot())
        ui.tick(250)
        self.assertEqual(ui.session.remaining_ms, 750)
        ui.render()
        timed = pygame.image.tobytes(ui.canvas, 'RGB')
        ui.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST)); ui.tick(5000)
        ui.handle_event(pygame.event.Event(pygame.WINDOWFOCUSGAINED)); ui.render()
        self.assertEqual(ui.session.remaining_ms, 750)
        self.assertEqual(pygame.image.tobytes(ui.canvas, 'RGB'), timed)
        self.assertIsNotNone(ui.choice_renderer.page(ui.session).timer_panel)

        ui.window = pygame.display.set_mode((800, 600), pygame.RESIZABLE)
        ui.render()
        rect = next(rect for rect, command in ui.buttons if command == ('choose', 1))
        x = ui.viewport.x + rect.centerx * ui.viewport.width / 480
        y = ui.viewport.y + rect.centery * ui.viewport.height / 720
        ui.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(x, y)))
        self.assertEqual(ui.session.remaining_ms, 750)
        ui.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(x, y)))
        self.assertEqual(ui.session.pending.request.args, (88,))
        self.assertEqual(ui.session.engine.result_cells[0], 88)
        self.assertIsNone(ui.error)

    @unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
    def test_real_choice_survives_rendering_and_scroll_keeps_last_index_reachable(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop import Desktop
        import pygame

        self.addCleanup(pygame.quit)
        resources = self.resources()
        ui = Desktop(Session(resources), audio=False)
        for _ in range(35):
            answer_screen(ui.session)
        before = ui.session.snapshot()
        ui.render()
        self.assertIsNone(ui.error)
        self.assertEqual(before, ui.session.snapshot())
        self.assertEqual([c for _, c in ui.buttons], [('choose', 0), ('choose', 1), ('menu',)])
        for choice, pc in ((0, 336), (1, 352)):
            ui.session = Session.from_snapshot(resources, before)
            ui.render()
            ui.command(('choose', choice))
            self.assertEqual(ui.session.pending.request.pc, pc)

        words, (title, options, prompt) = text_words('Make your choice!', '|'.join(['An option'] * 9), 'Pick one.')
        resources.programs[65000] = program(*host_call(1, title, options, prompt, 0, -1, -1, 0, 1),
                                            0x21, (0x1f, 0xfe01), words=words)
        ui.session = Session(resources, start_script=65000)
        ui.session.advance()
        ui.render()
        self.assertGreater(ui.max_scroll, 0)
        ui.scroll = ui.max_scroll
        ui.render()
        rect = next(rect for rect, command in ui.buttons if command == ('choose', 8))
        gear = next(rect for rect, command in ui.buttons if command == ('menu',))
        self.assertFalse(rect.colliderect(gear))
        ui.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center))
        ui.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=rect.center))
        self.assertEqual(ui.session.pending.request.args, (8,))
