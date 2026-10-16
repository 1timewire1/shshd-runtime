"""Authored names/fonts exercise input without distributing player content."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from exp_runtime.fonts import BitmapFont, Glyph
from exp_runtime.runtime import SaveError, Session
from exp_runtime.text_input import (
    CURSOR_FONT, MAX_NAME_LENGTH, NAME_ENTRY_ERROR, NAME_FONT,
    accept_name_character, validate_name,
)
from exp_runtime.ui_assets import Layout, LayoutBank, LayoutNode
from test_runtime import Resources, host_call, text_words
from test_vm import program


def font(advance=8):
    return BitmapFont('Authored input', 16, 20, 'unused.png',
                      {c: Glyph(c, 0, 0, 3, 7, 0, 2, advance) for c in range(32, 127)},
                      {(ord('A'), ord('A')): -2})


def resources(service=17, default='Alex'):
    words, refs = text_words('Name', 'Who are you?', default)
    return Resources(program((0x1a, 77), *host_call(service, *refs),
                             0x21, (0x1f, 0xfe02), words=words))


class NameInputTests(unittest.TestCase):
    def test_typing_ascii_case_conversion_and_rejection(self):
        for current, char, expected in (('', 'A', 'A'), ('A', 'B', 'Ab'), ('1', 'Z', '1z'),
                                         ('Alex', '8', 'Alex8'), ('', 'a', 'a')):
            self.assertEqual(accept_name_character(current, char), (expected, None))
        for char in ('', 'AB', '!', '-', ' ', '\n', '\x00', 'é', 'Ａ', '١', '😀'):
            with self.subTest(char=char):
                self.assertEqual(accept_name_character('Alex', char), ('Alex', NAME_ENTRY_ERROR))
        sixteen = 'a' * MAX_NAME_LENGTH
        self.assertEqual(accept_name_character(sixteen[:-1], 'A'), (sixteen, None))
        self.assertEqual(accept_name_character(sixteen, 'a'), (sixteen, NAME_ENTRY_ERROR))

    def test_spaces_are_accepted_only_when_the_game_allows_them(self):
        # Optional ASCII-space policy; native CoD puzzles do not require it.
        metrics = dict(font=font(), cursor_width=12)
        with self.assertRaisesRegex(ValueError, 'alphanumeric'):
            validate_name('Blue door', **metrics)
        validate_name('Blue door', allow_space=True, **metrics)
        for value in ('Blue-door', ' ', 'Blue door!'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_name(value, allow_space=True, **metrics)

    def test_cod_spaces_work_through_typing_validation_width_and_saved_drafts(self):
        draft = ''
        for char in 'blue Door':
            draft, error = accept_name_character(draft, char, allow_space=True, capitalize_first=True,
                                                font=font(), cursor_width=12)
            self.assertIsNone(error)
        self.assertEqual(draft, 'Blue Door')
        for char in ('\t', '\n', '\u00a0', '-', '!'):
            self.assertEqual(accept_name_character(draft, char, allow_space=True), (draft, NAME_ENTRY_ERROR))
        # A space still counts toward both existing native limits.
        self.assertEqual(accept_name_character('A' * 16, ' ', allow_space=True), ('A' * 16, NAME_ENTRY_ERROR))
        self.assertEqual(accept_name_character('A' * 12, ' ', allow_space=True, font=font(19), cursor_width=12),
                         ('A' * 12, NAME_ENTRY_ERROR))
        for service in (17, 40):
            r = resources(service)
            r.library.game_id = 'cod'
            s = Session(r)
            s.advance()
            s.pending.details['draft'] = draft
            saved = Session.from_snapshot(r, json.loads(json.dumps(s.snapshot())))
            self.assertEqual(saved.pending.details['draft'], draft)
            self.assertEqual(saved.answer(draft).request.args, (77, 0x7ff5))
            self.assertEqual(saved.engine.last_input, draft)

    def test_cod_first_character_capitalization_preserves_the_remaining_case(self):
        for current, char, expected in (('', 'b', 'B'), ('B', 'L', 'BL'), ('1', 'Z', '1Z'),
                                       ('', '1', '1'), ('Blue ', 'D', 'Blue D')):
            self.assertEqual(accept_name_character(current, char, allow_space=True, capitalize_first=True),
                             (expected, None))

    def test_native_width_gate_checks_existing_text_and_cursor_before_append(self):
        metrics = dict(font=font(19), cursor_width=12)
        # Exactly 240 fails, despite ink being narrower from AA kerning.
        self.assertEqual(accept_name_character('A' * 12, 'B', **metrics),
                         ('A' * 12, NAME_ENTRY_ERROR))
        validate_name('A' * 12, **metrics)  # Prefix width 209 + cursor 12.
        with self.assertRaisesRegex(ValueError, 'alphanumeric'):
            validate_name('A' * 13, **metrics)
        metrics['font'] = font(20)
        self.assertEqual(accept_name_character('A' * 11, 'B', **metrics), ('A' * 11 + 'b', None))
        validate_name('A' * 11 + 'b', **metrics)  # Last append crosses 240.
        validate_name('a' * 16, font=font(), cursor_width=12)

    def test_both_services_validate_before_mutating_the_vm_or_host(self):
        for service in (17, 40):
            s = Session(resources(service)); action = s.advance()
            s.engine.dynamic_strings[0] = s.engine.last_input = 'Previous'
            s.engine.result_cells[0] = 42
            before = s.snapshot()
            for value in ('', 'Zoé', 'Alex!', 'a' * 17, 'A B', 'A\x00', 7, None):
                with self.subTest(service=service, value=value), self.assertRaises(ValueError):
                    s.answer(value)
                self.assertEqual(s.snapshot(), before)
                self.assertIs(s.pending, action)
            self.assertEqual(s.answer('McKay8').request.args, (77, 0x7ff5))
            self.assertEqual((s.engine.last_input, s.engine.dynamic_strings[0]), ('McKay8', 'McKay8'))
            self.assertEqual(s.engine.result_cells[0], 42)

    def test_headless_submission_uses_the_same_font_gate_as_typing(self):
        r = resources()
        r.dialogue_layout = lambda: SimpleNamespace(font=lambda name: font(12 if name == CURSOR_FONT else 20))
        s = Session(r); s.advance(); before = s.snapshot()
        with self.assertRaises(ValueError):
            s.answer('a' * 13)
        self.assertEqual(s.snapshot(), before)
        self.assertEqual(s.answer('a' * 12).request.args, (77, 0x7ff5))

    def test_saved_draft_is_typed_but_not_a_confirmed_name(self):
        r = resources(); s = Session(r); s.advance()
        s.pending.details['draft'] = 'Abc12'
        state = json.loads(json.dumps(s.snapshot()))
        self.assertEqual(Session.from_snapshot(r, state).pending.details['draft'], 'Abc12')
        self.assertEqual(s.engine.last_input, '')
        for value in (None, 1, [], {}):
            changed = copy.deepcopy(state)
            changed['pending']['details']['draft'] = value
            with self.subTest(value=value), self.assertRaises(SaveError):
                Session.from_snapshot(r, changed)
        # Preserve old prototype drafts for editing, without allowing them to
        # bypass the new confirmation contract or rewrite an old last-input.
        state['pending']['details']['draft'] = 'Zoé'
        restored = Session.from_snapshot(r, state)
        with self.assertRaises(ValueError):
            restored.answer(restored.pending.details['draft'])
        self.assertEqual(restored.engine.last_input, '')


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class DesktopInputTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        self.addCleanup(pygame.quit)

    def desktop(self, default=''):
        import pygame
        from exp_runtime.desktop import Desktop

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        r = resources(default=default)
        r.library.directory = Path(temporary.name)
        glyph_font = font()
        # Authored geometry and solid surfaces: no copied native assets.
        fill = LayoutNode((0, 0, 280, 45), (0, 0, 4096, 4096), 17, (0, 0))
        geometry = LayoutNode((0, 0, 240, 20), (0, 0, 0, 0), 6, ())
        layouts = [Layout(280, 45, (fill,)) for _ in range(47)]
        layouts[46] = Layout(280, 45, (geometry,) * 18 + (fill,))
        bank = LayoutBank(4, 0, 0, (), tuple(layouts))
        r.dialogue_layout = lambda: SimpleNamespace(bank=bank, font=lambda _: glyph_font)
        ui = Desktop(Session(r), audio=False)
        atlas = pygame.Surface((3, 7), pygame.SRCALPHA); atlas.fill((255, 255, 255))
        for name in ('ArialRoundedMTBold30', 'ArialRoundedMTBold16', 'ArialRoundedMTBold20',
                     NAME_FONT, CURSOR_FONT):
            ui.story_text.fonts[name] = (glyph_font, atlas)
        image = pygame.Surface((4, 4)); image.fill((230, 230, 230))
        shadow = pygame.Surface((260, 40)); shadow.fill((100, 100, 100))
        alert = pygame.Surface((280, 160)); alert.fill((60, 60, 80))
        ui.dialogue_renderer.frame = lambda *_: image
        ui.dialogue_renderer.image = lambda asset: {706: shadow, 707: alert}.get(asset)
        ui.input_renderer.strings = lambda: {258: 'Alert', 260: NAME_ENTRY_ERROR, 164: 'OK'}
        # Opening the host pause menu also needs a box, but no system fonts.
        ui.dialogue_renderer.box = lambda target, rect, *_: pygame.draw.rect(
            target, (20, 20, 20), (rect.x, rect.y, rect.width, rect.height))
        return ui

    def test_typing_alert_empty_return_backspace_and_callback(self):
        import pygame
        ui = self.desktop(); s = ui.session
        held = s.vm.snapshot()
        ui.render()
        self.assertIsNone(ui.error)
        self.assertTrue(ui.text_input_started)
        ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        self.assertFalse(ui.text_input_started)
        self.assertEqual(s.vm.snapshot(), held)
        ui.command(('input_focus',))
        token = ui._screen_token()
        ui.handle_event(pygame.event.Event(pygame.TEXTINPUT, text='AB3!ignored'))
        self.assertEqual(s.pending.details['draft'], 'Ab3')
        self.assertNotEqual(ui._screen_token(), token)
        self.assertEqual(ui.input_error, NAME_ENTRY_ERROR)
        self.assertFalse(ui.text_input_started)
        self.assertEqual(s.vm.snapshot(), held)
        self.assertEqual(s.engine.last_input, '')
        ui.render(); self.assertIsNone(ui.error)
        ui.handle_event(pygame.event.Event(pygame.TEXTINPUT, text='Z'))
        self.assertEqual(s.pending.details['draft'], 'Ab3')
        ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        self.assertIsNone(ui.input_error)  # Acknowledge alert, never the VM.
        self.assertEqual(s.vm.snapshot(), held)
        ui.handle_event(pygame.event.Event(pygame.TEXTINPUT, text='!'))
        ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_BACKSPACE))
        self.assertEqual(s.pending.details['draft'], 'Ab')
        self.assertIsNone(ui.input_error)
        ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        self.assertEqual(s.pending.request.args, (77, 0x7ff5))
        self.assertEqual(s.engine.last_input, 'Ab')
        self.assertFalse(ui.text_input_started)

    def test_cod_accepts_a_spaced_answer_through_the_shared_desktop_and_ios_input_path(self):
        import pygame
        ui = self.desktop()
        ui.session.resources.library.game_id = ui.session.engine.game_key = 'cod'
        ui.render()
        ui.handle_event(pygame.event.Event(pygame.TEXTINPUT, text='blue Door'))
        self.assertEqual(ui.session.pending.details['draft'], 'Blue Door')
        self.assertIsNone(ui.input_error)
        ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        self.assertIsNone(ui.error)
        self.assertIsNone(ui.input_error)
        self.assertEqual(ui.session.engine.last_input, 'Blue Door')
        self.assertEqual(ui.session.pending.request.args, (77, 0x7ff5))

    def test_pause_focus_save_load_and_resized_alert_click(self):
        import pygame
        ui = self.desktop('Alex'); ui.render()
        held = ui.session.vm.snapshot()
        for event in (pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE),
                      pygame.event.Event(pygame.WINDOWFOCUSLOST)):
            ui.handle_event(event)
            self.assertFalse(ui.text_input_started)
            ui.handle_event(pygame.event.Event(pygame.TEXTINPUT, text='B'))
            ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
            self.assertEqual(ui.session.pending.details['draft'], 'Alex')
            self.assertEqual(ui.session.vm.snapshot(), held)
            ui.handle_event(pygame.event.Event(pygame.WINDOWFOCUSGAINED))
            ui.command(('resume',))
        ui.handle_event(pygame.event.Event(pygame.TEXTINPUT, text='B'))
        ui.command(('save',))
        ui.handle_event(pygame.event.Event(pygame.TEXTINPUT, text='!'))
        ui.command(('load',))
        self.assertEqual(ui.session.pending.details['draft'], 'Alexb')
        self.assertIsNone(ui.input_error)
        self.assertEqual(ui.session.vm.snapshot(), held)
        ui.handle_event(pygame.event.Event(pygame.TEXTINPUT, text='!'))
        ui.window = pygame.display.set_mode((800, 600), pygame.RESIZABLE)
        ui.render()
        self.assertIsNone(ui.error)
        rect, command = ui.buttons[0]
        self.assertEqual(command, ('input_dismiss',))
        pos = (ui.viewport.x + rect.centerx * ui.viewport.width / 480,
               ui.viewport.y + rect.centery * ui.viewport.height / 720)
        ui.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
        self.assertIsNone(ui.input_error)
        self.assertEqual(ui.session.vm.snapshot(), held)
        self.assertTrue(ui.text_input_started)

    def test_cursor_uses_active_time_and_title_uses_cumulative_kerning(self):
        import pygame
        ui = self.desktop('Alex')
        ui.tick(250)
        ui.render()
        before = ui.session.snapshot()
        visible = pygame.image.tobytes(ui.canvas, 'RGB')
        with patch('pygame.time.get_ticks', return_value=600):
            ui.render()
        self.assertTrue(pygame.image.tobytes(ui.canvas, 'RGB') == visible)
        self.assertEqual(ui.session.snapshot(), before)
        ui.active = False
        ui.tick(250)
        self.assertEqual(ui.session.snapshot(), before)
        ui.active = True
        ui.tick(250)
        ui.render()
        self.assertFalse(pygame.image.tobytes(ui.canvas, 'RGB') == visible)
        self.assertEqual(ui.session.vm.snapshot(), before['vm'])
        layout, width, scale = ui.input_renderer.title('AAA')
        self.assertEqual(([g.x for g in layout.glyphs], width, scale), ([0, 6, 12], 20, 1))
        self.assertEqual([command for _, command in ui.buttons], [('input_focus',)])

    def test_hidden_layout_reference_hides_its_visible_children(self):
        ui = self.desktop()
        bank = ui.session.resources.dialogue_layout().bank
        layouts = list(bank.layouts)
        layouts[43] = Layout(40, 20, (
            LayoutNode((0, 0, 20, 20), (0, 0, 0, 0), 7, (44,)),
            LayoutNode((20, 0, 40, 20), (0, 0, 0, 0), 17, (0, 0)),
        ))
        layouts[44] = Layout(20, 20, (LayoutNode((0, 0, 20, 20), (0, 0, 0, 0), 17, (0, 0)),))
        bank = LayoutBank(4, 0, 0, (), tuple(layouts))
        ui.session.resources.dialogue_layout = lambda: SimpleNamespace(bank=bank)
        layer = ui.input_renderer.layout_image(43, 40, 20)
        self.assertEqual(layer.get_at((1, 1)).a, 0)
        self.assertEqual(layer.get_at((21, 1)).a, 255)

    @unittest.skipUnless(Path('.shs-library/library.json').is_file(), 'user content is absent')
    def test_player_apk_fonts_layouts_alert_and_callback(self):
        import pygame
        from exp_runtime.content import ContentLibrary
        from exp_runtime.desktop import Desktop

        with ContentLibrary(Path('.shs-library')) as library:
            r = library.open_episode('The_New_Girl.exp')
            r.programs[25001] = resources(40, 'John').program(25001)
            ui = Desktop(Session(r), audio=False)
            ui.render(); self.assertIsNone(ui.error)
            held = ui.session.vm.snapshot()
            self.assertEqual(ui.input_renderer.canvas.get_size(), (320, 480))
            self.assertIn(NAME_FONT, ui.story_text.fonts)
            self.assertIn('ArialRoundedMTBold30', ui.story_text.fonts)
            self.assertIn(706, ui.images)
            self.assertNotIn(707, ui.images)
            ui.handle_event(pygame.event.Event(pygame.TEXTINPUT, text='é'))
            ui.render(); self.assertIsNone(ui.error)
            self.assertIn(707, ui.images)
            self.assertEqual(ui.session.vm.snapshot(), held)
            ui.command(('input_dismiss',)); ui.command(('continue',))
            self.assertEqual(ui.session.engine.last_input, 'John')
            self.assertEqual(ui.session.pending.request.args, (77, 0x7ff5))
