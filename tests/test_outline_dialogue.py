"""Native outline dialogue contracts with authored font metrics and text."""
from copy import deepcopy
from dataclasses import replace
import unittest

from exp_runtime.dialogue import BODY_FONT, EMPHASIS_FONT, dialogue_styles
from exp_runtime.fonts import Glyph, TextStyle, layout_text
from exp_runtime.ios_fonts import IOSFont
from exp_runtime.runtime import SaveError, Session
from exp_runtime.speaker_names import SpeakerNames, outline_speaker_label
from test_label_layout import authored_dialogue
from test_runtime import Resources, answer_screen, host_call, text_words
from test_vm import program


def font(advance=8, cap=12):
    # Give every glyph a visible pixel at the baseline. Distinct face advances
    # and cap heights make font switches observable without original assets.
    return IOSFont('Authored', 16, 16, '', {
        code: Glyph(code, 0, 0, 1, 1, 0, 16, 4 if code == 32 else advance)
        for code in range(32, 127)}, {}, cap, 4)


class OutlineDialogueTests(unittest.TestCase):
    def test_switch_faces_wrap_with_their_own_advances_on_one_baseline(self):
        base, italic = font(), font(6, 13)
        style = TextStyle(13, 10, (20, 30, 40), (('`', (200, 30, 40)),))
        text = 'a `long italic` passage here'
        page = layout_text(base, text, 75, style, switch_fonts={'`': ('italic', italic)})
        # Also checked by executing SHS's CSFont::drawText with these authored
        # metrics: wrapping, font selection and baseline coordinates agree.
        self.assertEqual([(line.start, line.end) for line in page.lines],
                         [(0, 7), (8, 15), (16, 23), (24, 28)])
        self.assertEqual([line.width for line in page.lines], [36, 36, 56, 32])
        self.assertEqual([line.y for line in page.lines], [0, 23, 46, 69])
        self.assertEqual(page.height, 82)
        for glyph in page.glyphs:
            highlighted = 3 <= glyph.index <= 13
            self.assertEqual(glyph.font, 'italic' if highlighted else None)
            self.assertEqual(glyph.color, (200, 30, 40) if highlighted else (20, 30, 40))
            line = next(row for row in page.lines if row.start <= glyph.index < row.end)
            self.assertEqual(glyph.y, line.y + 12)
        punctuated = layout_text(base, 'a `b;c` d', 75, style, switch_fonts={'`': ('italic', italic)})
        self.assertEqual([chr(p.glyph.code) for p in punctuated.glyphs], list('ab;cd'))
        self.assertEqual([p.x for p in punctuated.glyphs], [0, 12, 18, 24, 34])
        self.assertEqual([p.index for p in punctuated.glyphs], [0, 3, 4, 5, 8])

    def test_native_colors_follow_the_current_theme_and_leave_bitmap_styles_intact(self):
        for game in ('shs', 'cod'):
            for theme in (1, 2, 3, -1):
                for inherited in (1, 2):
                    style = dialogue_styles(theme, emphasis_theme=inherited, game=game, outline=True)[3]
                    colors = ({1: (41, 104, 221), 2: (180, 78, 78), 3: (137, 137, 137), -1: (180, 109, 26)}
                              if game == 'shs' else {1: (0, 0, 0), 2: (180, 78, 78), 3: (0, 0, 0), -1: (0, 0, 0)})
                    self.assertEqual(style.color, colors[theme])
                    self.assertEqual(style.markers, (('`', (41, 104, 221) if theme == 2 else (254, 53, 53)),))
        style = dialogue_styles(3, emphasis_theme=2)[3]
        self.assertEqual((style.color, style.markers),
                         ((108, 108, 108), (('`', (41, 104, 221)), (';', (1, 76, 215)))))

    def test_native_names_keep_size_origin_and_wrapping_with_no_ink_refit(self):
        for game in ('shs', 'cod'):
            layout, names = authored_dialogue(outline=True), SpeakerNames()
            layout.resources.library.game_id = game
            # An overhanging outline exposes the old fit even on short names.
            name = layout.font('PajamaHip26')
            native = replace(name, native_face=True, glyphs={
                code: replace(g, xoffset=-4, width=16, yoffset=-3, height=32)
                for code, g in name.glyphs.items()})
            original = layout.font
            layout.font = lambda role: native if role.startswith('PajamaHip') else original(role)
            for mode in (1, 2, 3):
                for speaker in ('Jo', 'Inspector Avery Stone', 'A\nSecond\nThird'):
                    details = dict(presentation_mode=mode, theme=1, emphasis_theme=1,
                                   speaker=speaker, text='Read this paragraph. ' * 30)
                    layout.prepare_name(details, names)
                    before = deepcopy(names)
                    expected = outline_speaker_label(speaker, mode, 'PajamaHip26', layout.bank, native)
                    page = layout.page(details, names=names)
                    self.assertEqual((page.name, page.name_origin, page.name_scale),
                                     (expected.layout, expected.origin, 1))
                    later = layout.page(details, start=page.end, names=names)
                    self.assertEqual((page.name, page.name_origin, page.name_scale),
                                     (later.name, later.name_origin, later.name_scale))
                    self.assertEqual(names, before)

    def test_ipa_save_reflows_old_font_switches_without_replaying_the_vm(self):
        for game in ('shs', 'cod'):
            text = 'An `emphasized paragraph; with several words` continues here. ' * 30
            words, (ref,) = text_words(text)
            resources = Resources(program(*host_call(13, ref, 1), 0x33, words=words))
            resources.library.kind = 'ipa'
            resources.library.game_id = game
            old_layout, layout = authored_dialogue(), authored_dialogue(outline=True)
            # Simulate old single-face advances, then install the corrected
            # two-face layout for the very same content identity/checkpoint.
            original = layout.font
            layout.font = lambda role: font(6, 13) if role == EMPHASIS_FONT else original(role)
            resources.dialogue_layout = lambda: old_layout
            session = Session(resources)
            session.engine.character_names[1] = 'Inspector Avery Stone'
            session.engine.character_art_variants[1] = [100] * 5
            session.advance()
            answer_screen(session)
            session.tick(250)
            saved = session.snapshot()
            saved['version'] = 25
            untouched = deepcopy(saved)
            # Name history is still validated using the original font bank.
            layout.prepare_name = old_layout.prepare_name
            resources.dialogue_layout = lambda: layout
            restored = Session.from_snapshot(resources, saved)
            self.assertEqual(saved, untouched)
            self.assertEqual(restored.vm.snapshot(), session.vm.snapshot())
            self.assertEqual(restored.engine, session.engine)
            self.assertEqual(restored.pending.details['page_start'], saved['pending']['details']['page_start'])
            self.assertNotEqual(restored.pending.details['page_end'], saved['pending']['details']['page_end'])
            page = restored.dialogue_page()
            self.assertTrue(any(p.font == EMPHASIS_FONT for p in page.body.glyphs))
            self.assertEqual(page.body_font, BODY_FONT)
            self.assertEqual([line.y for line in page.body.lines], [0, 23, 46, 69])
            current = restored.snapshot()
            self.assertEqual(current['version'], 26)
            self.assertEqual(Session.from_snapshot(resources, current).snapshot(), current)
            current['pending']['details']['page_end'] -= 1
            with self.assertRaisesRegex(SaveError, 'page does not match'):
                Session.from_snapshot(resources, current)


if __name__ == '__main__':
    unittest.main()
