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


def timed_resources(service=1, timeout=2000, count=3, selection=1, default=None):
    selection = selection if default is None else default
    labels = [f'Option {i}' for i in range(count)]
    words, refs = text_words('Choose', 'A question.', '|'.join(labels), *labels)
    if service == 1:
        calls = host_call(1, refs[0], refs[2], refs[1], timeout, selection, -1, -1, 1)
    else:
        calls = host_call(2, refs[0], refs[1], timeout, selection, -1, 1)
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
    def test_choice_attachment_ignores_early_taps_and_restores_its_clock(self):
        from exp_runtime.runtime import SaveError
        for service in (1, 2):
            r = timed_resources(service)
            s = Session(r); action = s.advance()
            held = s.vm.snapshot()
            for elapsed in (0, 100, 149):
                s.tick(elapsed)
                self.assertIs(s.answer(1), action)
                self.assertEqual(s.vm.snapshot(), held)
                self.assertEqual(s.engine.sound_serial, 0)
            saved = s.snapshot()
            restored = Session.from_snapshot(r, saved)
            self.assertFalse(restored.choice_ready)
            restored.tick(1)
            self.assertTrue(restored.choice_ready)
            self.assertEqual(restored.answer(1).request.args, (1 if service == 1 else 101,))
            for invalid in (-1, 251, True):
                malformed = copy.deepcopy(saved)
                malformed['engine']['choice_ms'] = invalid
                with self.assertRaises(SaveError):
                    Session.from_snapshot(r, malformed)
            saved['version'] = 23
            del saved['engine']['choice_ms']
            migrated = Session.from_snapshot(r, saved)
            self.assertTrue(migrated.choice_ready)
            self.assertEqual(migrated.vm.snapshot(), held)

    def test_portrait_modes_select_opposite_native_header_and_text_insets(self):
        layout = authored_layout()
        details = dict(title='Choose a response', text='An authored prompt with enough words to wrap. ' * 3,
                       options=['First', 'Second'], enabled=[True, True])
        for kind in ('apk', 'ipa'):
            layout.resources = SimpleNamespace(library=SimpleNamespace(kind=kind))
            left = layout.page(dict(details, portrait_mode=1), has_portrait=True)
            right = layout.page(dict(details, portrait_mode=2), has_portrait=True)
            self.assertEqual(left.portrait.center[0], 57)
            self.assertEqual(right.portrait.center[0], 263)
            self.assertEqual(left.description.lines[0].x, 95 if kind == 'ipa' else 105)
            self.assertEqual(right.description.lines[0].x, 0)
            self.assertTrue(all(row.index == i for i, row in enumerate(right.rows)))

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
        # This fork returns -1's slot as 0 (cod/profile.py TIMEOUT_NO_OPTION_RESULT) and 1000 unmapped.
        for default, result in ((-1, 0), (1000, 1000)):
            with self.subTest(default=default):
                r = timed_resources(2, default=default); r.library.game_id = 'cod'
                s = Session(r); s.advance(); held = s.vm.snapshot()
                s.tick(2000)
                self.assertEqual(s.vm.snapshot(), held)
                restored = Session.from_snapshot(r, json.loads(json.dumps(s.snapshot())))
                self.assertEqual(restored.tick(0).name, 'choice')
                self.assertEqual(restored.tick(1).request.args, (result,))
                self.assertEqual(restored.engine.result_cells[0], result)
                after = restored.vm.snapshot()
                restored.tick(100)
                self.assertEqual(restored.vm.snapshot(), after)

    def test_other_invalid_timeouts_keep_the_pending_call_in_both_games(self):
        for game in ('shs', 'cod'):
            # CoD returns any selection past its options unmapped in this fork (TIMEOUT_PAST_OPTIONS_UNMAPPED).
            defaults = (-2,) if game == 'cod' else (-2, 3, 1000, 32767)
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

    def test_an_incremental_timeout_selecting_no_option(self):
        from exp_runtime.vm import VMError
        # Both games read the never-written slot before their mapping table (TIMEOUT_NO_OPTION_RESULT in each
        # profile); any other out-of-range selection keeps the explicit error.
        # A selection past the options returns itself unmapped for CoD (the adaptation for Volume 2's 1000).
        for game, selection, expected in (('cod', -1, 0), ('shs', -1, 0), ('cod', -2, None), ('cod', 3, 3),
                                          ('cod', 1000, 1000), ('shs', 1000, None)):
            with self.subTest(game=game, selection=selection):
                r = timed_resources(2, selection=selection); r.library.game_id = game
                s = Session(r); s.advance()
                if expected is None:
                    with self.assertRaisesRegex(VMError, 'out of range'):
                        s.tick(2001)
                else:
                    self.assertEqual(s.tick(2001).request.args, (expected,))
                    self.assertEqual(s.engine.result_cells[0], expected)

    def test_nonpositive_durations_have_no_timer_and_do_not_expire(self):
        for service in (1, 2):
            for timeout in (-1, 0):
                s = Session(timed_resources(service, timeout)); s.advance(); s.tick(250)
                before = s.snapshot()
                s.tick(100000)
                self.assertIsNone(s.remaining_ms)
                self.assertEqual(s.snapshot(), before)
                self.assertIsNone(authored_layout().page(s.pending.details).timer_panel)

    def test_every_row_and_timer_fit_above_the_footer_without_scrolling(self):
        layout = authored_layout()
        for count in (2, 3, 9):
            s = Session(timed_resources(count=count)); s.advance()
            page = layout.page(s.pending.details)
            self.assertLessEqual(page.timer_panel.y + page.timer_panel.height, 421)
            last = page.rows[-1].rect
            self.assertEqual(last.y + last.height, page.timer_panel.y)
            self.assertEqual(page.max_scroll, 0)
            self.assertEqual(len(page.rows), count)
            plain = layout.page(dict(s.pending.details, timeout_ms=0))
            if count < 9:
                self.assertEqual(page.box.height - plain.box.height, 20)
                self.assertEqual(page.text_scale, 1)
            self.assertIsNone(plain.timer_panel)

    def test_tall_quiz_repositions_before_shrinking_and_extreme_text_reflows(self):
        layout = authored_layout()
        details = dict(title='Make your choice!', text='Choose the correct response.',
                       options=['Answer'] * 6, enabled=[True] * 6, timeout_ms=1000)
        original = copy.deepcopy(details)
        page = layout.page(details)
        self.assertEqual(page.text_scale, 1)
        self.assertEqual(page.box.y + page.box.height, 421)
        self.assertEqual(details, original)
        for kind in ('apk', 'ipa'):
            layout.resources = SimpleNamespace(library=SimpleNamespace(kind=kind))
            for portrait in (False, True):
                for timed in (0, 1000):
                    d = dict(details, text='A longer authored question. ' * 8,
                             options=['A long answer with multiple words. ' * 4] * 9,
                             enabled=[True, False, True] * 3, timeout_ms=timed)
                    before = copy.deepcopy(d)
                    page = layout.page(d, has_portrait=portrait)
                    self.assertEqual(d, before)
                    self.assertEqual(page.max_scroll, 0)
                    self.assertLess(page.text_scale, 1)
                    self.assertGreaterEqual(page.box.y, 32)
                    self.assertLessEqual(page.box.y + page.box.height, 421)
                    self.assertEqual([row.index for row in page.rows], list(range(9)))
                    self.assertEqual([row.enabled for row in page.rows], d['enabled'])
                    for row, label in zip(page.rows, d['options']):
                        self.assertEqual(len(row.text.glyphs), len(label.replace(' ', '')))
                        left, top, right, bottom = row.text.ink_bounds
                        self.assertGreaterEqual(row.origin[0] + left * page.text_scale, row.rect.x)
                        self.assertLessEqual(row.origin[0] + right * page.text_scale, row.rect.x + row.rect.width)
                        self.assertGreaterEqual(row.origin[1] + top * page.text_scale, row.rect.y)
                        self.assertLessEqual(row.origin[1] + bottom * page.text_scale, row.rect.y + row.rect.height)


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
        art.frame_scaled = lambda asset, index, scale: frame(asset, index)
        art.draw_bottom_bar = lambda *args, **kwargs: None
        art.box = lambda *args, **kwargs: None
        text = SimpleNamespace(layout=lambda name, value, width, style, **kwargs:
                               layout_text(layout.font(name), value, width, style, **kwargs),
                               draw_layout=lambda *args, **kwargs: None, draw_footer=lambda *args: None)
        renderer = ChoiceRenderer(None, text, art)
        renderer.layout = layout
        return renderer

    @unittest.skip("exp-runtime's iPhone choice entrance fade (SHSUIMenu::internalTransitionOn); not ported to this fork's choice renderer yet")
    @unittest.skip("exp-runtime's iPhone choice entrance fade (SHSUIMenu::internalTransitionOn); not ported to this fork's choice renderer yet")
    def test_ipa_choice_fades_over_background_and_restores_mid_entrance(self):
        import pygame
        r = timed_resources(timeout=0)
        r.library.kind = 'ipa'
        s = Session(r); s.advance()
        renderer = self.renderer()
        renderer.resources = r
        renderer.art.draw_background = lambda canvas, engine: canvas.fill((20, 40, 60))
        renderer.art.box = lambda canvas, rect, *args, **kwargs: pygame.draw.rect(
            canvas, (220, 140, 80), (rect.x, rect.y, rect.width, rect.height))
        target = pygame.Surface((320, 480))
        page, _ = renderer.draw(target, s)
        point = page.box.x + 12, page.box.y + 12
        self.assertEqual(target.get_at(point)[:3], (20, 40, 60))
        s.tick(125)
        before = s.snapshot()
        renderer.draw(target, s)
        self.assertEqual(s.snapshot(), before)
        color = target.get_at(point)[:3]
        self.assertTrue(all(abs(a - b) <= 1 for a, b in zip(color, (120, 90, 70))))
        pixels = pygame.image.tobytes(target, 'RGB')
        restored = Session.from_snapshot(r, before)
        renderer.draw(target, restored)
        self.assertEqual(pygame.image.tobytes(target, 'RGB'), pixels)
        restored.tick(125)
        renderer.draw(target, restored)
        self.assertEqual(target.get_at(point)[:3], (220, 140, 80))
        # Android attaches its panel immediately, with the same input gate.
        r.library.kind = 'apk'
        s = Session(r); s.advance()
        renderer.draw(target, s)
        self.assertEqual(target.get_at(point)[:3], (220, 140, 80))
        self.assertFalse(s.choice_ready)

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

    def test_all_option_hits_fit_above_the_timer_and_rendering_preserves_state(self):
        import pygame
        s = Session(timed_resources(count=9)); s.advance(); s.tick(1000)
        renderer = self.renderer(); target = pygame.Surface((320, 480))
        page, buttons = renderer.draw(target, s)
        panel = pygame.Rect(page.timer_panel.x, page.timer_panel.y,
                            page.timer_panel.width, page.timer_panel.height)
        pixels = pygame.image.tobytes(target.subsurface(panel), 'RGB')
        before = s.snapshot()
        for _ in range(2):
            _, buttons = renderer.draw(target, s)
            self.assertEqual(pygame.image.tobytes(target.subsurface(panel), 'RGB'), pixels)
            self.assertTrue(all(not rect.colliderect(panel) for rect, _ in buttons))
        self.assertEqual([command for _, command in buttons],
                         [('choose', i) for i in range(9)] + [('menu',)])
        self.assertEqual(before, s.snapshot())
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
        self.assertEqual(long.max_scroll, 0)
        self.assertLessEqual(long.box.y + long.box.height, 421)
        self.assertEqual(len(long.rows), 9)
        for row in long.rows:
            _, top, _, bottom = row.text.ink_bounds
            self.assertGreaterEqual(row.origin[1] + top * long.text_scale, row.rect.y)
            self.assertLessEqual(row.origin[1] + bottom * long.text_scale, row.rect.y + row.rect.height)

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
    def test_arrow_keys_skip_disabled_options_and_draw_the_focused_row(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop import Desktop
        import pygame

        self.addCleanup(pygame.quit)
        resources = self.resources()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        resources.library.directory = Path(temporary.name)
        words, (title, prompt, no, yes) = text_words('Make your choice!', 'A question.', 'No', 'Yes')
        resources.programs[65000] = program(
            *host_call(2, title, prompt, 0, 1, -1, 0),
            *host_call(3, no, 77, 0), *host_call(3, yes, 88, 1),
            *host_call(4, 0), 0x21, (0x1f, 0xfe01), words=words)
        ui = Desktop(Session(resources, start_script=65000), audio=False)
        ui.render()
        plain = pygame.image.tobytes(ui.choice_renderer.canvas, 'RGBA')
        ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP))
        self.assertEqual(ui.choice_focus, 1)                    # 'No' is disabled, only 'Yes' takes the focus
        ui.render()
        self.assertNotEqual(pygame.image.tobytes(ui.choice_renderer.canvas, 'RGBA'), plain)
        ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        for _ in range(10):                                     # an HD menu fades out before it answers
            ui.tick(100)
        self.assertEqual(ui.session.pending.request.args, (88,))
        self.assertIsNone(ui.error)

    @unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
    def test_real_choice_and_last_index_remain_reachable_without_scrolling(self):
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
            ui.session.tick(250)
            ui.render()
            ui.command(('choose', choice))
            self.assertEqual(ui.session.pending.request.pc, pc)

        words, (title, options, prompt) = text_words('Make your choice!', '|'.join(['An option'] * 9), 'Pick one.')
        resources.programs[65000] = program(*host_call(1, title, options, prompt, 0, -1, -1, 0, 1),
                                            0x21, (0x1f, 0xfe01), words=words)
        ui.session = Session(resources, start_script=65000)
        ui.session.advance(); ui.session.tick(250)
        ui.render()
        self.assertEqual(ui.max_scroll, 0)
        before = ui.session.snapshot()
        hits = [(tuple(rect), command) for rect, command in ui.buttons]
        for event in (pygame.event.Event(pygame.MOUSEWHEEL, y=-5),
                      pygame.event.Event(pygame.KEYDOWN, key=pygame.K_PAGEDOWN)):
            ui.handle_event(event)
            self.assertEqual(ui.scroll, 0)
        ui.render()
        self.assertEqual(hits, [(tuple(rect), command) for rect, command in ui.buttons])
        self.assertEqual(before, ui.session.snapshot())
        rect = next(rect for rect, command in ui.buttons if command == ('choose', 8))
        gear = next(rect for rect, command in ui.buttons if command == ('menu',))
        self.assertFalse(rect.colliderect(gear))
        ui.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center))
        ui.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=rect.center))
        self.assertEqual(ui.session.pending.request.args, (8,))
