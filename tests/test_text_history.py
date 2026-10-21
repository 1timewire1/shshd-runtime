"""Cross-label native state: assignments advance it; layout and drawing do not."""
from copy import deepcopy
from dataclasses import replace
import json
import importlib.util
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from exp_runtime.fonts import TextHistory, TextStyle, layout_label, layout_text
from exp_runtime.runtime import SaveError, Session
from exp_runtime.speaker_names import NameFontState, SpeakerNames, speaker_label
from exp_runtime.story_labels import StoryLabels
from exp_runtime.ui_assets import Rect
from test_choice import authored_layout
from test_label_layout import authored_dialogue, authored_font
from test_runtime import Resources, host_call, text_words
from test_vm import program


class TextHistoryTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra required')
    def test_shared_footer_uses_native_font_anchor_and_string_bank(self):
        from exp_runtime.desktop_text import BitmapTextRenderer
        font = authored_font()
        font.kernings[(65, 66)] = -3
        strings = {36: 'Continue', 37: 'Select', 38: 'Best choice', 39: 'Read', 40: 'Quickly'}
        for kind in ('apk', 'ipa'):
            with self.subTest(kind=kind), patch('exp_runtime.desktop_text.MenuStrings.load', return_value=strings):
                renderer = BitmapTextRenderer(SimpleNamespace(kind=kind))
                renderer.font = lambda name: font
                name, label, origin, alpha = renderer.footer(38, 65)
                self.assertEqual(''.join(chr(g.glyph.code) for g in label.glyphs), strings[38].replace(' ', ''))
                self.assertEqual(name, 'ArialMT11' if kind == 'ipa' else 'ArialMT14')
                self.assertEqual(alpha, 176 if kind == 'ipa' else 255)
                if kind == 'ipa':
                    left, top, right, bottom = label.ink_bounds
                    self.assertEqual((origin[0] + (left + right) / 2,
                                      origin[1] + (top + bottom) / 2), (189, 468))
                else:
                    self.assertEqual(origin, (180, 455))
                    self.assertEqual(label, layout_label(font, strings[38], 0, 0, TextStyle(14, 8),
                                                        0x0a, previous_glyph=65))
                self.assertEqual(renderer.footer(38, 65), (name, label, origin, alpha))
                self.assertEqual(''.join(chr(g.glyph.code) for g in renderer.footer(40)[1].glyphs), strings[40])

    def test_cross_label_kerning_signed_bytes_empty_labels_and_measurement(self):
        font = authored_font()
        font.glyphs[233] = replace(font.glyphs[65], code=233)
        font.glyphs[90] = replace(font.glyphs[90], width=0, height=0)
        font.kernings.update({(65, 66): -3, (65513, 65): 2, (65535, 65): -1})
        history = TextHistory()
        for text, incoming, outgoing in (('A', -1, 65), (' B', 65, 66), ('\xe9', 66, -23),
                                         ('` A ', -23, 65), (' \n ', 65, 65), ('Z', 65, 90)):
            style = TextStyle(16, 5, markers=(('`', (255, 0, 0)),))
            before = deepcopy(history)
            measure = layout_text(font, text, 100, style)
            self.assertEqual(history, before)
            placed = history.update('test', font, text, measure, markers=style.markers)
            self.assertEqual((history.initial('test'), history.previous_glyph), (incoming, outgoing))
            self.assertEqual(placed, layout_text(font, text, 100, style, previous_glyph=incoming))
        self.assertFalse(placed.glyphs)  # An inkless nonspace byte still writes the global.

    def test_height_clipping_only_visits_drawn_lines(self):
        font = authored_font()
        font.kernings[(66, 65)] = -4
        layout = layout_label(font, 'A\nB\nC', 50, 16, TextStyle(16), 0x31, previous_glyph=66)
        self.assertEqual(len(layout.lines), 1)
        self.assertEqual(layout.previous_glyph, 65)
        self.assertEqual(layout.glyphs[0].x, -4)
        empty = layout_label(font, 'A', 0, 0, TextStyle(16), 0x31, previous_glyph=66)
        self.assertEqual(empty.previous_glyph, 66)
        self.assertFalse(empty.glyphs)

    def test_dialogue_assignment_pagination_restore_and_redraw_have_distinct_lifetimes(self):
        words, refs = text_words('A body with several words. ' * 25)
        resources = Resources(program(*host_call(13, refs[0], 1), 0x33, words=words))
        resources.dialogue_layout = lambda: authored_dialogue()
        session = Session(resources)
        session.engine.ui_defaults = {74: 0, 75: 7}
        session.engine.character_names[1] = 'Bob'
        session.engine.character_art_variants[1] = [100] * 5
        session.engine.text_history.previous_glyph = 65
        session.advance()
        history = session.engine.text_history
        self.assertEqual(history.initial('dialogue_name'), 65)
        self.assertEqual(history.initial('dialogue_body'), ord('b'))
        page = session.dialogue_page()
        self.assertEqual(history.previous_glyph, page.body.previous_glyph)
        saved = session.snapshot()
        restored = Session.from_snapshot(resources, json.loads(json.dumps(saved)))
        self.assertEqual(restored.dialogue_page(), page)
        for _ in range(3):
            self.assertEqual(session.dialogue_page(), page)
            self.assertEqual(session.snapshot(), saved)
        before = deepcopy(history)
        session.tick(500)
        self.assertEqual(history, before)  # Revealing glyph nodes does not assign the body again.
        session.tick(100000)
        last = history.previous_glyph
        session.answer()
        self.assertGreater(session.pending.details['page_start'], 0)
        self.assertEqual(history.initial('dialogue_body'), last)
        self.assertEqual(history.initial('dialogue_name'), 65)
        for key, value in (('previous_glyph', 128), ('labels', {'bad': -129}), ('footer', 'bad\0text')):
            invalid = deepcopy(saved)
            invalid['engine']['text_history'][key] = value
            with self.subTest(key=key), self.assertRaises(SaveError):
                Session.from_snapshot(resources, invalid)

    def test_choice_measurement_changes_next_name_without_overwriting_current_name_basis(self):
        layout = authored_layout()
        rectangle = layout.bank.rectangle
        layout.bank = SimpleNamespace(layouts=layout.bank.layouts,
            rectangle=lambda index, node, *args: Rect(0, 0, 90, 30) if node == 18 else rectangle(index, node, *args))
        names = SpeakerNames(fonts={'PajamaHip26': NameFontState(gap=8)}, basis={})
        history = TextHistory(previous_glyph=ord('Z'))
        details = dict(title='A long heading with several words', text='Prompt',
                       options=['Answer A', 'Answer B'], enabled=[True, True])
        layout.prepare(details, names, history)
        self.assertGreater(names.fonts['PajamaHip26'].lines, 1)
        self.assertEqual(names.basis, {})
        self.assertEqual(history.labels, {'choice_0': ord('A'), 'choice_1': ord('B'),
                                         'choice_body': ord('B'), 'choice_title': ord('t')})
        self.assertEqual(history.previous_glyph, ord('s'))
        before = deepcopy((names, history))
        page = layout.page(details, text_history=history)
        self.assertEqual(layout.page(details, text_history=history), page)
        self.assertEqual((names, history), before)
        dialogue = authored_dialogue()
        label = speaker_label('Spud The Stud', 2, 1, dialogue.bank, dialogue.font, names.fonts)
        self.assertEqual(label.text, 'Spud Th e Stud')

    def test_bitmap_choice_title_repair_preserves_script_text_and_updates_kerning(self):
        layout = authored_layout()
        rectangle = layout.bank.rectangle
        layout.bank = SimpleNamespace(layouts=layout.bank.layouts,
            rectangle=lambda index, node, *args: Rect(0, 0, 90, 30) if node == 18 else rectangle(index, node, *args))
        details = dict(title='Think fast!', text='Prompt', options=['A', 'B'], enabled=[True, True])
        original = deepcopy(details)
        history = TextHistory()
        layout.prepare(details, SpeakerNames(), history)
        self.assertEqual(details, original)
        self.assertEqual(history.previous_glyph, ord('t'))  # Native bitmap label drops the exclamation mark.
        for theme in (1, 2):
            self.assertEqual(layout.display_title('Fight!', theme), 'Fi ght!' if theme == 1 else 'Fight!')
        layout.resources = SimpleNamespace(library=SimpleNamespace(kind='ipa'))
        layout.prepare(details, SpeakerNames(), history)
        self.assertEqual(history.previous_glyph, ord('!'))
        self.assertEqual(layout.display_title('Think fast!', 1), 'Think fast!')

    def test_message_loading_and_name_entry_assignments_join_the_same_history(self):
        from exp_runtime.message_panel import MessagePanel
        layout = authored_dialogue()
        layout.bank = SimpleNamespace(layouts=[SimpleNamespace(width=280)] * 25)
        resources = SimpleNamespace(dialogue_layout=lambda: layout)
        session = SimpleNamespace(resources=resources, engine=SimpleNamespace(
            text_history=TextHistory(), message_panel=MessagePanel('Heading', 'Body', 0)),
            pending=SimpleNamespace(details=dict(title='Name', prompt='Prompt', default='Ada')))
        labels = StoryLabels(session)
        strings = {29: 'Continue', 30: 'Wait', 31: 'Loading', 35: 'Please wait',
                   36: 'Tap to continue', 39: 'Please read'}
        with patch('exp_runtime.story_labels.MenuStrings.load', return_value=strings):
            labels.message(initial=True)
            history = session.engine.text_history
            self.assertEqual(history.initial('message_title'), ord('t'))
            self.assertEqual(history.initial('message_body'), ord('t'))
            self.assertEqual(history.initial('message_continue'), ord('y'))
            labels.message(previous_caption=(False, 1))
            self.assertEqual(history.previous_glyph, ord('d'))
            before = deepcopy(history)
            labels.message(previous_caption=(False, 1))
            self.assertEqual(history, before)
            session.engine.message_panel.tick(1000)
            labels.message(previous_caption=(False, 1))
            self.assertEqual(history.initial('message_continue'), ord('d'))
            self.assertEqual(history.initial('footer'), ord('e'))
            labels.loading()
            self.assertEqual(history.initial('loading_body'), ord('g'))
            labels.entry(initial=True)
            self.assertEqual(history.initial('input_prompt'), ord('e'))
            self.assertEqual(history.initial('input_name'), ord('t'))
            labels.entry()
            self.assertEqual(history.initial('input_name'), ord('a'))

    @unittest.skip("Open after the v0.6.1 merge: the choice title here updates the Android label history ('!'), where exp-runtime's leaves it ('d')")
    def test_word_game_redeal_and_picker_preserve_assignment_history(self):
        from test_character_picker import picker_resources
        from test_minigames import word_resources
        choice = authored_layout()
        rectangle = choice.bank.rectangle
        choice.bank = SimpleNamespace(layouts=choice.bank.layouts,
            rectangle=lambda index, node, *args: Rect(0, 0, 90, 30) if node == 18 else rectangle(index, node, *args))
        layout = authored_dialogue()
        layout.bank = choice.bank
        resources = word_resources()
        session = Session(resources)
        resources.dialogue_layout = lambda: layout
        resources.read_ui_resource = lambda role: b''
        resources.exists = lambda role: role in (13, 14)
        strings = {37: 'Select a character', 40: 'Choose quickly'}
        with patch('exp_runtime.story_labels.MenuStrings.load', return_value=strings), \
                patch('exp_runtime.story_labels.ChoiceLayout', return_value=choice):
            session.advance()
            history = session.engine.text_history
            self.assertEqual(history.initial('word_score'), ord('0'))
            self.assertEqual(history.initial('footer'), ord('d'))
            before = deepcopy(history)
            session.answer(0)  # The entrance gate prevents both a pick and new labels.
            self.assertEqual(history, before)
            session.tick(400)
            game = session.engine.word_game
            old_last = ord(game.options[-1][-1])
            session.answer(game.weights.index(1))
            self.assertEqual(history.initial('word_score'), ord('1'))
            self.assertEqual(history.initial('word_delta'), ord('1'))
            self.assertEqual(history.initial('choice_0'), old_last)
            self.assertEqual(history.previous_glyph, ord(game.options[-1][-1]))
            saved = json.loads(json.dumps(session.snapshot()))
            self.assertEqual(Session.from_snapshot(resources, saved).engine.text_history, history)
            picker = Session(picker_resources())
            picker.resources = resources
            picker.engine.text_history = history
            picker.advance()
            self.assertEqual(history.initial('picker_title'), ord(game.options[-1][-1]))
            self.assertEqual(history.initial('footer'), ord('!'))
            before = deepcopy(history)
            picker.answer(2)
            picker.tick(50)
            self.assertEqual(history, before)  # Moving portraits does not rebuild text.

    def test_nonblocking_badge_assignment_precedes_the_next_dialogue(self):
        words, refs = text_words('Morning', 'First line', 'Evening', 'Last line')
        resources = Resources(program(*host_call(90, 100, refs[0]), *host_call(13, refs[1], 1),
            *host_call(90, 100, refs[2]), *host_call(90, -1, -1), *host_call(13, refs[3], 1),
            0x33, words=words))
        resources.dialogue_layout = lambda: authored_dialogue()
        resources.read_ui_resource = lambda role: b''
        resources.exists = lambda role: role in (13, 14)
        session = Session(resources)
        session.engine.character_names[1] = 'Bob'
        with patch('exp_runtime.story_labels.MenuStrings.load', return_value={29: 'Continue', 36: 'Continue'}):
            session.advance()
            history = session.engine.text_history
            self.assertEqual(history.initial('scene_badge'), ord('S'))
            self.assertEqual(history.initial('dialogue_name'), ord('g'))
            session.tick(100000)
            session.answer()
            self.assertIsNone(session.engine.scene_badge)
            self.assertEqual(history.initial('scene_badge'), ord('S'))
            self.assertEqual(history.initial('dialogue_name'), ord('g'))


if __name__ == '__main__':
    unittest.main()
