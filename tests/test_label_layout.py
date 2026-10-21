"""Label placement regressions using authored fonts and layout rectangles."""
import copy
from dataclasses import replace
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import unittest

from exp_runtime.dialogue import DialogueLayout
from exp_runtime.fonts import BitmapFont, Glyph, TextStyle, layout_label, layout_text
from exp_runtime.runtime import SaveError, Session
from exp_runtime.scene_badge import SceneBadge, outline_badge_text
from exp_runtime.speaker_names import (NameFontState, SpeakerNames, hd_speaker_label, outline_speaker_label,
                                      speaker_label)
from exp_runtime.ui_assets import Rect
from test_runtime import Resources, answer_screen, host_call, text_words
from test_vm import program


def authored_font(line_height=16, ink_height=12, yoffset=2):
    glyphs = {code: Glyph(code, 0, 0, 8, ink_height, 0, yoffset, 5 if code == 32 else 9)
              for code in range(32, 127)}
    return BitmapFont('Authored label font', 16, line_height, 'unused.png', glyphs, {})


def authored_dialogue(*, outline=False):
    # A compact layout bank, constructed without copying an APK resource.
    rects = {0x4c: Rect(8, 265, 190, 31), 0x43: Rect(8, 233, 190, 63),
             0x4e: Rect(196, 225, 128, 128), 8: Rect(40, 304, 240, 98),
             0x2e: Rect(122, 265, 190, 31), 0x25: Rect(122, 233, 190, 63),
             0x30: Rect(-6, 225, 128, 128),
             0x6a: Rect(18, 265, 284, 31), 0x61: Rect(18, 233, 284, 63)}
    layout = DialogueLayout.__new__(DialogueLayout)
    layout.resources = SimpleNamespace(library=SimpleNamespace(game_id='shs'))
    layout.bank = SimpleNamespace(rectangle=lambda bank, node: rects[node])
    layout.border_widths = lambda theme: (10, 10)
    name_font, body_font = authored_font(33, 30, 0), authored_font()
    if outline:
        from exp_runtime.ios_fonts import IOSFont
        name_font = IOSFont(**authored_font(26, 24, 4).__dict__, cap_height=20, descent=5)
        body_font = IOSFont(**body_font.__dict__, cap_height=12, descent=4)
    layout.font = lambda name: name_font if name.startswith('PajamaHip') else body_font
    return layout


class SpeakerPlacementTests(unittest.TestCase):
    def assert_name_fits(self, page):
        if not page.name.glyphs:
            return
        x, y = page.name_origin
        left, top, right, bottom = page.name.ink_bounds
        scale = page.name_scale
        body_top = page.body_origin[1] + page.body.ink_bounds[1]
        self.assertLessEqual(y + scale * bottom, body_top + 1e-6)
        bounds = page.name_bounds
        self.assertGreaterEqual(x + scale * left, bounds.x - 1e-6)
        self.assertLessEqual(x + scale * right, bounds.x + bounds.width + 1e-6)
        self.assertGreaterEqual(y + scale * top, bounds.y - 1e-6)
        self.assertLessEqual(y + scale * bottom, bounds.y + bounds.height + 1e-6)
        self.assertGreaterEqual(x + scale * left, -1e-6)
        self.assertLessEqual(x + scale * right, 320 + 1e-6)
        if page.portrait:
            if page.portrait.x < 0:
                self.assertGreaterEqual(x + scale * left, page.portrait.x + page.portrait.width - 1e-6)
            else:
                self.assertLessEqual(x + scale * right, page.portrait.x + 1e-6)
        previous_bottom = None
        for line in page.name.lines:
            row = [g for g in page.name.glyphs if line.start <= g.index < line.end]
            if row:
                if previous_bottom is not None:
                    self.assertGreaterEqual(min(g.y for g in row), previous_bottom)
                previous_bottom = max(g.y + g.glyph.height for g in row)

    def test_native_named_branches_and_retained_size_are_distinct_from_generic_fit(self):
        layout = authored_dialogue()
        for text, width, height, scale in (("Howard's Mom", 235, 63, .9),
                                           ("Howard's Dad", 223, 63, .9),
                                           ('French Teacher', 225, 81, .8),
                                           ("Neighbor's Wife", 270, 91, .8)):
            with self.subTest(text=text):
                result = speaker_label(text, 2, 1, layout.bank, layout.font, {})
                self.assertEqual(result.content_size, (width, height))
                self.assertEqual((result.flags, result.scale), (0x3d, scale))
                self.assertEqual(result.text, text)
        states = {'PajamaHip26': NameFontState(width=242, height=77)}
        result = speaker_label('Brendizzle', 1, 1, layout.bank, layout.font, states)
        self.assertEqual((result.content_size, result.scale), ((242, 77), .9))

    def test_native_spacing_rewrites_and_previous_line_count(self):
        layout = authored_dialogue()
        for mode, text, expected in ((2, 'The Boss', 'Th e Boss '),
                                     (2, 'The Mayor', 'Th e Mayor'),
                                     (2, 'Judge Tigh', 'Judge Ti gh'),
                                     (2, 'Animal Thief', 'Animal Th ief'),
                                     (3, 'The team', 'Th e team'),
                                     (3, 'The Whole Room', 'Th e Whole Room'),
                                     (3, 'The Crowd', 'Th e Crowd')):
            with self.subTest(text=text):
                self.assertEqual(speaker_label(text, mode, 1, layout.bank, layout.font, {}).text, expected)
        states = {'PajamaHip26': NameFontState(lines=2)}
        result = speaker_label('Spud The Stud', 2, 1, layout.bank, layout.font, states)
        self.assertEqual((result.text, result.scale, result.content_size),
                         ('Spud Th e Stud', .7, (270, 61)))
        states = {'PajamaHip26': NameFontState(lines=2)}
        result = speaker_label('A very long speaker name', 2, 1, layout.bank, layout.font, states)
        self.assertEqual((result.content_size, result.scale), ((300, 95), .7))
        self.assertEqual(states['PajamaHip26'].gap, 8)

    def test_all_modes_fit_long_and_multiline_names_after_spacing_changes(self):
        layout, names = authored_dialogue(), SpeakerNames()
        labels = ('A very long speaker name', 'Mr. Fernley', 'Miss Harper', 'Mrs. West',
                  'Alex', 'A\nSecond\nThird', 'W' * 60, "Howard's Mom", "Howard's Dad")
        for mode in (2, 1, 3):
            for theme in (1, 2, 3, -1):
                for speaker in labels:
                    with self.subTest(mode=mode, theme=theme, speaker=speaker):
                        details = dict(presentation_mode=mode, theme=theme, emphasis_theme=1,
                                       speaker=speaker, text='Please read the question.')
                        layout.prepare_name(details, names)
                        before = copy.deepcopy(names)
                        page = layout.page(details, names=names)
                        self.assert_name_fits(page)
                        self.assertEqual(layout.page(details, names=names), page)
                        self.assertEqual(names, before)

    def test_a_long_name_not_individually_hardcoded_still_actually_wraps_to_two_lines(self):
        """`speaker_label()`'s hand-measured names above (`"Howard's Mom"`, `'French Teacher'`, ...) use widths
        tight enough to force their own wrap; a name that isn't one of them falls into the generic
        `elif state.lines < 2:` padding branch (`w + 20`), sized for breathing room rather than for actually
        constraining the wrap -- and for a sufficiently long two-word name, that padded width can still be wider
        than the name's own natural (unwrapped) width, so it never wraps at all: left on one line, floating
        above a box sized for two (reproduced live against "Mrs. Sworelin", not in the hardcoded list)."""
        layout = authored_dialogue()
        text = 'N' * 11 + ' ' + 'N' * 10                    # exceeds the mode-2 rect's own width unwrapped
        unwrapped = layout_text(layout.font('PajamaHip26'), text, 2 ** 31, TextStyle(16, -16)).width
        self.assertGreater(unwrapped, 190)                  # confirms this reproduces the "large" case at all
        result = speaker_label(text, 2, 1, layout.bank, layout.font, {})
        self.assertEqual(len(result.layout.lines), 2)
        self.assertLess(result.content_size[0], unwrapped)
    def test_header_fits_tall_outline_glyphs_and_remains_attached_after_long_names(self):
        # Wider/taller substitute faces expose both defects: the previous fit
        # constrained only viewport width and allowed unlimited upward motion.
        # All metrics, strings and skin widths here are authored.
        for ink_height, yoffset, border in ((30, 0, (10, 10)), (61, -8, (6, 14))):
            layout, names = authored_dialogue(), SpeakerNames()
            name_font = authored_font(33, ink_height, yoffset)
            name_font.glyphs.update({code: replace(g, xoffset=-3, width=14)
                                     for code, g in name_font.glyphs.items()})
            native_font = layout.font
            layout.font = lambda name: name_font if name.startswith('PajamaHip') else native_font(name)
            layout.border_widths = lambda theme: border
            for mode in (2, 1, 3):
                for theme in (1, 2, 3, -1):
                    for speaker in ('Inspector Avery Stone', 'Jo', 'A\nSecond\nThird', 'W' * 60):
                        with self.subTest(ink_height=ink_height, mode=mode, theme=theme, speaker=speaker):
                            details = dict(presentation_mode=mode, theme=theme, emphasis_theme=1,
                                           speaker=speaker, text='Read this authored paragraph. ' * 20)
                            layout.prepare_name(details, names)
                            before = copy.deepcopy(names)
                            page = layout.page(details, names=names)
                            self.assert_name_fits(page)
                            extra = 304 - page.box.y
                            self.assertEqual(page.name_bounds.y, 233 if extra == 40 else 265)
                            self.assertLessEqual(page.name_bounds.height, 63 if extra == 40 else 31)
                            self.assertGreaterEqual(page.name_bounds.y + page.name_bounds.height, page.box.y)
                            self.assertGreaterEqual(page.name_bounds.x, page.box.x - border[0])
                            self.assertLessEqual(page.name_bounds.x + page.name_bounds.width,
                                                 page.box.x + page.box.width + border[1])
                            if ink_height * .9 > page.name_bounds.height:
                                self.assertLess(page.name_scale, .9)
                            later = layout.page(details, start=page.end, names=names)
                            self.assertEqual((later.name, later.name_origin, later.name_scale),
                                             (page.name, page.name_origin, page.name_scale))
                            self.assertEqual(names, before)

    def test_outline_titles_wrap_in_native_regions_at_full_size_for_both_games(self):
        # Authored advances: this title exceeds the 190-wide normal region;
        # the old widened Cocos label would put it on one line and shrink it.
        for game in ('shs', 'cod'):
            layout = authored_dialogue(outline=True)
            layout.resources.library.game_id = game
            for mode in (1, 2):
                details = dict(presentation_mode=mode, theme=1, emphasis_theme=1,
                               speaker='Inspector Avery Stone', text='An authored sentence.')
                # Make the last word too wide to fit beside the others, using
                # only authored metrics and the same algorithm for every name.
                font = layout.font('PajamaHip26')
                font.glyphs[ord('I')] = replace(font.glyphs[ord('I')], advance=24)
                label = outline_speaker_label(details['speaker'], mode, 'PajamaHip26', layout.bank, font)
                self.assertEqual([details['speaker'][r.start:r.end] for r in label.layout.lines],
                                 ['Inspector Avery', 'Stone'])
                self.assertEqual((label.extra, label.scale, label.header.height), (40, 1, 63))
                self.assertEqual(label.layout.lines[1].x, 20 if mode == 1 else 5)
                self.assertEqual(label.layout.lines[1].y - label.layout.lines[0].y, 28)
                self.assertEqual(label.origin[1], 240.5)
                page = layout.page(details)
                self.assertEqual((page.box.y, page.name_scale), (264, 1))
                left, top, right, bottom = page.name.ink_bounds
                self.assertLess(page.name_origin[1] + top, page.box.y)
                self.assertGreater(page.name_origin[1] + bottom, page.box.y)
                self.assert_name_fits(page)

    def test_outline_short_titles_keep_native_alignment_and_ignore_previous_name_size(self):
        layout, names = authored_dialogue(outline=True), SpeakerNames()
        for mode, flags, origin_x in ((1, 0x1b, 108), (2, 0x19, 21), (3, 0x1a, 18)):
            for theme in (1, 2, 3, -1):
                d = dict(presentation_mode=mode, theme=theme, emphasis_theme=1,
                         speaker='Jo', text='Read this authored paragraph. ' * 30)
                fresh = layout.page(d)
                label = outline_speaker_label('Jo', mode, 'PajamaHip26', layout.bank, layout.font('PajamaHip26'))
                self.assertEqual((label.extra, label.flags, label.origin), (8, flags, (origin_x, 270.5)))
                for speaker in ('A very long previous speaker name', 'Jo', 'A\nSecond\nThird', 'Jo'):
                    d['speaker'] = speaker
                    layout.prepare_name(d, names)
                    before = copy.deepcopy(names)
                    page = layout.page(d, names=names)
                    self.assert_name_fits(page)
                    if speaker == 'Jo':
                        self.assertEqual(page, fresh)
                    later = layout.page(d, start=page.end, names=names)
                    self.assertEqual((page.name, page.name_origin, page.name_scale),
                                     (later.name, later.name_origin, later.name_scale))
                    self.assertEqual(names, before)

    def test_outline_body_region_does_not_move_or_gain_lines_from_a_tall_title(self):
        layout = authored_dialogue(outline=True)
        text = 'Read the authored paragraph. ' * 40
        for mode in (1, 2, 3):
            short = layout.page(dict(presentation_mode=mode, theme=1, emphasis_theme=1,
                                     speaker='Jo', text=text))
            tall = layout.page(dict(presentation_mode=mode, theme=1, emphasis_theme=1,
                                    speaker='An exceptionally long authored speaker name', text=text))
            self.assertEqual((short.box.y, tall.box.y), (296, 264))
            self.assertEqual(short.body_origin, (40, 304))
            self.assertEqual((short.body_origin, short.body, short.end),
                             (tall.body_origin, tall.body, tall.end))
            self.assertEqual(len(tall.body.lines), 4)
            self.assertEqual([r.y for r in tall.body.lines], [0, 22, 44, 66])
            self.assertEqual(tall.body.lines[0].x, 80 if mode == 1 else 0)
            self.assertLessEqual(tall.body_origin[1] + tall.body.ink_bounds[3],
                                 tall.box.y + tall.box.height)

    def test_outline_substitute_ink_is_bounded_without_altering_font_history(self):
        layout, names = authored_dialogue(outline=True), SpeakerNames()
        font = layout.font('PajamaHip26')
        font.glyphs.update({code: replace(g, xoffset=-3, width=14, height=61, yoffset=-8)
                            for code, g in font.glyphs.items()})
        for mode in (1, 2, 3):
            for theme in (1, 2, 3, -1):
                for speaker in ('Jo', 'Inspector Avery Stone', 'A\nSecond\nThird', 'W' * 60):
                    d = dict(presentation_mode=mode, theme=theme, emphasis_theme=1,
                             speaker=speaker, text='Read this paragraph. ' * 20)
                    layout.prepare_name(d, names)
                    before = copy.deepcopy(names)
                    page = layout.page(d, names=names)
                    self.assert_name_fits(page)
                    self.assertLess(page.name_scale, 1)
                    later = layout.page(d, start=page.end, names=names)
                    self.assertEqual((page.name, page.name_origin, page.name_scale),
                                     (later.name, later.name_origin, later.name_scale))
                    self.assertEqual(names, before)

    def test_eleven_byte_names_clear_the_body_without_moving_or_repaginating_it(self):
        layout = authored_dialogue()
        details = dict(presentation_mode=2, theme=1, emphasis_theme=1,
                       speaker='Ms. Vale', text='Read the question. ' * 30)
        short = layout.page(details)
        for speaker in ('Mr. Fernley', 'Miss Harper'):
            with self.subTest(speaker=speaker):
                details['speaker'] = speaker
                original = copy.deepcopy(details)
                page = layout.page(details)
                name_bottom = page.name_origin[1] + page.name_scale * page.name.ink_bounds[3]
                body_top = page.body_origin[1] + page.body.ink_bounds[1]
                self.assertLessEqual(name_bottom, body_top)
                self.assertLess(body_top - name_bottom, 5)
                self.assertEqual((page.box, page.body, page.body_origin, page.portrait, page.end),
                                 (short.box, short.body, short.body_origin, short.portrait, short.end))
                self.assertEqual(details, original)

    def test_name_placement_preserves_pending_vm_and_saved_page(self):
        words, (ref,) = text_words('Read the question. ' * 30)
        resources = Resources(program(*host_call(13, ref, 1), 0x33, words=words))
        resources.dialogue_layout = lambda: authored_dialogue()
        session = Session(resources)
        session.engine.character_names[1] = 'Mr. Fernley'
        session.engine.character_art_variants[1] = [100] * 5
        session.advance()
        session.tick(1000)
        original = session.snapshot()
        page = session.dialogue_page()
        self.assertEqual(session.snapshot(), original)
        restored = Session.from_snapshot(resources, original)
        self.assertEqual(restored.snapshot(), original)
        self.assertEqual(restored.dialogue_page(), page)
        answer_screen(restored)
        self.assertEqual(restored.pending.details['page_start'], page.end)
        self.assertEqual(restored.vm.snapshot(), session.vm.snapshot())
        self.assertEqual(restored.dialogue_page().name_origin, page.name_origin)

    def test_font_history_survives_save_and_old_saves_reflow_without_vm_replay(self):
        words, (ref,) = text_words('Read the question. ' * 30)
        resources = Resources(program(*host_call(13, ref, 1), *host_call(13, ref, 2),
                                      0x33, words=words))
        resources.dialogue_layout = lambda: authored_dialogue()
        session = Session(resources)
        session.engine.character_names = {1: 'A very long speaker name', 2: 'Mr. Fernley'}
        session.engine.character_art_variants = {1: [100] * 5, 2: [200] * 5}
        session.advance()
        self.assertEqual(session.engine.speaker_names.fonts['PajamaHip26'].gap, 8)
        while session.pending.details['character_id'] == 1:
            answer_screen(session)
        self.assert_name_fits(session.dialogue_page())
        answer_screen(session)
        self.assertGreater(session.pending.details['page_start'], 0)
        original = session.snapshot()
        restored = Session.from_snapshot(resources, original)
        self.assertEqual(restored.snapshot(), original)
        self.assertEqual(restored.dialogue_page(), session.dialogue_page())
        for bank, key, value in (('fonts', 'gap', 7), ('fonts', 'width', -1),
                                 ('basis', 'lines', -1), ('fonts', 'indents', [200]),
                                 ('fonts', 'lines', 15)):
            bad = copy.deepcopy(original)
            bad['engine']['speaker_names'][bank]['PajamaHip26'][key] = value
            with self.subTest(bank=bank, key=key), self.assertRaises(SaveError):
                Session.from_snapshot(resources, bad)
        bad = copy.deepcopy(original)
        bad['engine']['speaker_names']['basis'] = None
        with self.assertRaises(SaveError):
            Session.from_snapshot(resources, bad)
        old = copy.deepcopy(original)
        old['version'] = 9
        del old['engine']['speaker_names']
        untouched = copy.deepcopy(old)
        restored = Session.from_snapshot(resources, old)
        self.assertEqual(old, untouched)
        self.assertEqual(restored.vm.snapshot(), session.vm.snapshot())
        self.assertEqual(restored.pending.details['page_start'],
                         original['pending']['details']['page_start'])
        self.assertEqual(restored.engine.numbers, session.engine.numbers)
        self.assertEqual(restored.engine.random48, session.engine.random48)

    def test_name_clears_taller_body_glyphs_on_later_pages_without_moving(self):
        words, (ref,) = text_words('Read the question.\n' * 15 + 'QQQQ\n')
        resources = Resources(program(*host_call(13, ref, 1), 0x33, words=words))
        layout, body_font = authored_dialogue(), authored_font()
        body_font.glyphs[ord('Q')] = replace(body_font.glyphs[ord('Q')], yoffset=-5)
        native_font = layout.font
        layout.font = lambda name: native_font(name) if name.startswith('PajamaHip') else body_font
        resources.dialogue_layout = lambda: layout
        session = Session(resources)
        session.engine.character_names[1] = 'Mr. Fernley'
        session.engine.character_art_variants[1] = [100] * 5
        session.engine.speaker_names.fonts['PajamaHip26'] = NameFontState(gap=8)
        session.advance()
        origin = session.dialogue_page().name_origin
        pages = 0
        while session.pending.name == 'dialogue':
            page = session.dialogue_page()
            self.assert_name_fits(page)
            self.assertEqual(page.name_origin, origin)
            pages += 1
            answer_screen(session)
        self.assertGreater(pages, 1)

    @unittest.skipUnless(Path('.shs-library/library.json').is_file(), 'user library is not present')
    def test_original_roster_and_parent_teacher_sequence_clear_dialogue_and_portraits(self):
        from exp_runtime.content import ContentError, ContentLibrary

        with ContentLibrary(Path('.shs-library')) as library:
            try:
                library.select('Football Star')
            except ContentError:
                self.skipTest('Football Star is not in the local library')
            resources = library.open_episode('Football Star')
            session = Session(resources)
            session.advance()  # Original initialization supplies the character metadata.
            layout = resources.dialogue_layout()
            names = SpeakerNames()
            characters = [26, 27, 17, 19, 16, 18, 20, *session.engine.character_names]
            for character in characters:
                details = session.engine.present_dialogue(character, 0, 'Read the question.', 0)
                if details['presentation_mode'] not in (1, 2):
                    continue
                with self.subTest(speaker=details['speaker']):
                    layout.prepare_name(details, names)
                    page = layout.page(details, names=names)
                    self.assert_name_fits(page)


class NativeLabelTests(unittest.TestCase):
    def test_alignment_indents_and_height_limit_use_line_boxes_before_glyph_ink(self):
        font = authored_font()
        style = TextStyle(16, 8, indents=(0, 5))
        left = layout_label(font, 'AA\nAA', 40, 80, style, 0x11)
        center = layout_label(font, 'AA\nAA', 40, 80, style, 0x1a)
        bottom = layout_label(font, 'AA\nAA', 40, 80, style, 0x3d)
        self.assertEqual([(l.x, l.y) for l in left.lines], [(0, 0), (5, 24)])
        self.assertEqual([(l.x, l.y) for l in center.lines], [(11, -20), (13.5, 4)])
        self.assertEqual([(l.x, l.y) for l in bottom.lines], [(0, -36), (5, -12)])
        clipped = layout_label(font, 'AA\nAA\nAA', 40, 36, style, 0x35)
        self.assertEqual([g.index for g in clipped.glyphs], [0, 1])
        self.assertEqual(len(clipped.lines), 1)


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class BadgeDrawingTests(unittest.TestCase):
    def test_outline_badge_wraps_and_bounds_substitute_ink_in_the_native_region(self):
        from exp_runtime.ios_fonts import IOSFont
        # Normal and deliberately oversized substitute glyphs, authored here.
        for width, height, bearing in ((6, 10, 4), (12, 20, -9), (110, 42, -12)):
            glyphs = {c: Glyph(c, 0, 0, width, height, -2, bearing, width + 1)
                      for c in range(32, 127)}
            font = IOSFont('Authored outline', 14, 14, '', glyphs, {}, 10, 3)
            region = Rect(68, 15, 98, 30)
            for text in ('Before School', 'Morning', 'A longer scene caption', 'Wideglyph'):
                with self.subTest(width=width, text=text):
                    layout, (x, y), scale = outline_badge_text(text, font, region, (200, 150, 50))
                    left, top, right, bottom = layout.ink_bounds
                    self.assertGreaterEqual(x + left * scale, region.x - 1e-6)
                    self.assertLessEqual(x + right * scale, region.x + region.width + 1e-6)
                    self.assertGreaterEqual(y + top * scale, region.y - 1e-6)
                    self.assertLessEqual(y + bottom * scale, region.y + region.height + 1e-6)
                    self.assertEqual(''.join(chr(g.glyph.code) for g in layout.glyphs),
                                     text.replace(' ', ''))
                    if width == 6 and text == 'Before School':
                        self.assertEqual(len(layout.lines), 1)
                        self.assertEqual(scale, 1)
                        self.assertEqual(y, 25)

    def test_badge_text_is_inside_the_frame_and_left_aligned_on_every_line(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        from exp_runtime.desktop import Desktop
        from exp_runtime.desktop_text import BitmapTextRenderer

        pygame.display.init()
        pygame.display.set_mode((480, 720))
        self.addCleanup(pygame.quit)
        atlas = pygame.Surface((8, 12), pygame.SRCALPHA)
        atlas.fill((255, 255, 255, 255))
        ui = Desktop.__new__(Desktop)
        ui.story_text = BitmapTextRenderer(None)
        ui.story_text.fonts['ArialRoundedMTBold16'] = (authored_font(), atlas)
        frame = pygame.Surface((171, 60), pygame.SRCALPHA)  # Only text contributes pixels.
        ui.dialogue_renderer = SimpleNamespace(frame=lambda *args: frame)
        ui._image = lambda asset: None
        ui.canvas = pygame.Surface((480, 720), pygame.SRCALPHA)
        for label, line_count in (('Evening', 1), ('Authored Office', 2),
                                  ('Unsupervised Study', 2), ('Before School', 2)):
            with self.subTest(label=label):
                ui.canvas.fill((0, 0, 0, 0))
                badge = SceneBadge(1, label, False, 200)
                original = copy.deepcopy(badge)
                ui._draw_scene_badge(badge)
                glyphs = pygame.mask.from_surface(ui.canvas).get_bounding_rects()
                rows = sorted({rect.top for rect in glyphs})
                self.assertEqual(len(rows), line_count)
                lefts = [min(rect.left for rect in glyphs if rect.top == y) for y in rows]
                self.assertEqual(len(set(lefts)), 1)
                # Logical badge interior is y=10..50 and text sits after the icon.
                # At the desktop's 1.5 scale and top inset 15 these avoid both borders.
                self.assertGreaterEqual(min(rows), 30)
                self.assertLessEqual(max(rect.bottom for rect in glyphs), 90)
                self.assertTrue(all(115 <= x <= 135 for x in lefts))
                self.assertEqual(badge, original)

class HdTitleTests(unittest.TestCase):
    """SHSUIDialog's HD title (updateTitleBounds / animateTitleLayer), with authored metrics: 9-unit advances."""
    rects = {0x2e: Rect(122, 259.5, 194, 31), 0x25: Rect(122, 227.5, 194, 63),
             0x4c: Rect(4, 259.5, 194, 31), 0x43: Rect(4, 227.5, 194, 63),
             0x6a: Rect(17, 259.5, 286, 31), 0x61: Rect(14, 227.5, 292, 63)}

    def label(self, text, mode, cap=20):
        return hd_speaker_label(text, mode, 'PajamaHip26', self.rects.__getitem__, authored_font(38, 24, 0), cap)

    def test_regions_flags_and_short_title_shifts(self):
        # Seven characters = 63 units = 126 points: "short" (< 135 points), shifted 7.5 units (15 points).
        short, long = 'A' * 7, 'A' * 8
        for mode, flags, shift, nudge in ((1, 0x1b, -7.5, 1), (2, 0x19, 7.5, -2), (3, 0x1a, 0, 0)):
            with self.subTest(mode=mode):
                label = self.label(short, mode)
                normal = self.rects[{1: 0x2e, 2: 0x4c, 3: 0x6a}[mode]]
                self.assertEqual((label.flags, label.extra, label.header), (flags, 8, Rect(normal.x + nudge, normal.y,
                                                                                           normal.width, normal.height)))
                self.assertEqual(label.origin[0], normal.x + nudge + shift)
                self.assertEqual(self.label(long, mode).origin[0], normal.x + nudge)
                # One cap-high line, centred in the 31-unit region, baseline cap below its top (line_height - base).
                self.assertEqual(label.origin[1], normal.y + (31 - 20) / 2 + 38 - 0)   # (authored base 0)

    def test_cause_of_death_measures_short_titles_and_shifts_them_in_its_own_points(self):
        # CoD's animateTitleLayer keeps 135 and 15 in its 320-point screen (one point per unit): 14 characters
        # (126 units) are short there, shifted 15; 15 characters (135) are not. In HD units they would be long.
        rect = self.rects[0x2e]
        cod = dict(points_per_unit=1, shift=15)
        short = hd_speaker_label('A' * 14, 1, 'PajamaHip26', self.rects.__getitem__, authored_font(38, 24, 0), 20,
                                 **cod)
        self.assertEqual(short.origin[0], rect.x + 1 - 15)
        long = hd_speaker_label('A' * 15, 1, 'PajamaHip26', self.rects.__getitem__, authored_font(38, 24, 0), 20,
                                **cod)
        self.assertEqual(long.origin[0], rect.x + 1)

    def test_a_name_too_tall_for_the_normal_region_takes_the_tall_one_unshifted(self):
        name = ' '.join(['A' * 17] * 2)                     # 311 units: 2 lines in every region; 20 + 8 + 20 > 31
        for mode, tall, flags in ((1, 0x25, 0x19), (2, 0x43, 0x19), (3, 0x61, 0x1a)):
            with self.subTest(mode=mode):
                label = self.label(name, mode)
                self.assertEqual((label.extra, label.flags, label.header.height), (40, flags, 63))
                self.assertEqual(len(label.layout.lines), 2)
                self.assertEqual(label.origin[0], self.rects[tall].x + {1: 1, 2: -2, 3: 0}[mode])
                if mode in (1, 2):
                    # The second line takes the title's line offset (40 / 10 points).
                    self.assertEqual(label.layout.lines[1].x, {1: 20, 2: 5}[mode])


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class HdTallNameCapacityTests(unittest.TestCase):
    def test_a_two_line_name_does_not_give_the_page_more_lines(self):
        # Issue #11 (Hector's Guide To Girls, "Spud The Stud"): HD text starts at node 8 whatever the title does,
        # so the tall title's extra 40 units hold no body lines.
        from exp_runtime.vector_text import VectorFont
        layout = authored_dialogue()
        name = layout.font('PajamaHip26')
        body = VectorFont(**layout.font('Body').__dict__, source=object())      # HD's vector text branch
        layout.font = lambda role: name if role.startswith('PajamaHip') else body
        pages = []
        for speaker in ('Jo', 'Spud The Stud Who Wraps To Two Lines'):
            page = layout.page(dict(presentation_mode=2, theme=1, emphasis_theme=1, speaker=speaker,
                                    text='word ' * 120))
            last = page.body.lines[-1]
            self.assertLessEqual(page.body_origin[1] + last.y + 14, page.box.y + page.box.height)
            pages.append(page)
        self.assertLess(pages[1].box.y, pages[0].box.y)                        # the tall header
        self.assertEqual(len(pages[1].body.lines), len(pages[0].body.lines))
