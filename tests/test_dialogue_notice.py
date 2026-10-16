"""Authored service-88 messages; no original scripts, fonts or art fixtures."""
import copy
import importlib.util
from io import BytesIO
import json
import os
from types import SimpleNamespace
import unittest

from exp_runtime.dialogue_notice import (
    NOTICE_FONT, NoticeMotion, hd_letter_start_ms, hd_letter_state, hd_notice_lifetime, notice_lifetime,
)
from exp_runtime.runtime import SaveError, Session
from exp_runtime.ui_assets import Rect
from test_fonts import descriptor
from test_runtime import Resources, answer_screen, host_call, text_words
from test_vm import program


class HdNoticeTimelineTests(unittest.TestCase):
    # SHSUIDialog::startLetterEffectAnimation: letter i starts i * 50 ms in,
    # rises from 3 cap heights below over 200 ms while fading in, holds, then
    # leaves 3 caps upward over its last 150 ms; every letter ends at
    # (n - 1) * 50 + 1550 ms.
    text = 'Strength Up'

    def test_letters_arrive_in_order_and_end_together(self):
        end = hd_notice_lifetime(self.text)
        self.assertEqual(end, 10 * 50 + 1550)
        self.assertIsNone(hd_letter_state(self.text, 0, 1))          # not started
        self.assertEqual(hd_letter_state(self.text, 0, 0), (0.0, 3.0))
        alpha, offset = hd_letter_state(self.text, 100, 0)           # halfway up
        self.assertAlmostEqual(alpha, .5)
        self.assertAlmostEqual(offset, 1.5)
        self.assertEqual(hd_letter_state(self.text, 300, 0), (1.0, 0.0))
        for index in range(len(self.text)):
            self.assertIsNotNone(hd_letter_state(self.text, end - 1, index))
            self.assertIsNone(hd_letter_state(self.text, end, index))

    def test_letters_leave_upward_while_fading(self):
        end = hd_notice_lifetime(self.text)
        alpha, offset = hd_letter_state(self.text, end - 75, 10)     # halfway through the exit
        self.assertAlmostEqual(alpha, .5)
        self.assertAlmostEqual(offset, -1.5)
        self.assertEqual(hd_letter_state(self.text, end - 150, 10), (1.0, 0.0))

    def test_a_photographed_moment_matches(self):
        # At ~510 ms the HD photo shows "Strengt" settled, the 'h' (index 7)
        # nearly landed and the 'U' (index 9) barely started and faint.
        self.assertEqual(hd_letter_state(self.text, 510, 6), (1.0, 0.0))
        alpha, offset = hd_letter_state(self.text, 510, 7)
        self.assertGreater(alpha, .7)
        self.assertLess(offset, 1)
        alpha, offset = hd_letter_state(self.text, 510, 9)
        self.assertLess(alpha, .4)
        self.assertGreater(offset, 1.8)


def notice_session(text='Skill improved', character=0):
    words, (notice, line) = text_words(text, 'A long enough sentence to keep revealing.')
    r = Resources(program(*host_call(88, notice), *host_call(13, line, character),
                          *host_call(13, line, character), 0x33, words=words))
    s = Session(r)
    s.advance()
    return s


class CodNoticeTests(unittest.TestCase):
    def test_cause_of_death_times_its_score_notice_as_the_letter_effect(self):
        # CoD's "Detective Score Up!" is SHS HD's letter effect (cod.profile.LETTER_NOTICE), not Android's typed
        # notice: the clock covers the portrait's entrance plus the letters, whatever the build.
        words, (notice, line) = text_words('Detective Score Up!', 'A long enough sentence to keep revealing.')
        s = Session(Resources(program(*host_call(88, notice), *host_call(13, line, 0), 0x33, words=words)))
        s.engine.game_key = 'cod'
        s.advance()
        self.assertEqual(s.engine.notice, 'Detective Score Up!')
        self.assertEqual(s.engine.notice_ms, hd_letter_start_ms(s.engine.dialogue_animation)
                         + hd_notice_lifetime('Detective Score Up!'))

    def test_a_reveal_tap_keeps_the_letters_until_the_line_ends(self):
        words, (notice, line) = text_words('Detective Score Up!', 'A long enough sentence to keep revealing.')
        s = Session(Resources(program(*host_call(88, notice), *host_call(13, line, 0),
                                      *host_call(13, line, 0), 0x33, words=words)))
        s.engine.game_key = 'cod'
        s.advance()
        remaining = s.engine.notice_ms
        s.answer()
        self.assertTrue(s.engine.dialogue_animation.finish_requested)
        self.assertEqual((s.engine.notice, s.engine.notice_ms), ('Detective Score Up!', remaining))
        s.tick(100)
        s.answer()
        self.assertEqual(s.pending.name, 'dialogue')
        self.assertEqual((s.engine.notice, s.engine.notice_ms), ('Detective Score Up!', remaining - 100))
        s.tick(remaining - 100)
        self.assertEqual((s.engine.notice, s.engine.notice_ms), ('', 0))

    def test_the_letters_stay_on_their_speakers_side(self):
        words, (notice, mine, theirs) = text_words('Detective Score Up!', 'My line.', 'Their line.')
        r = Resources(program(*host_call(88, notice), *host_call(13, mine, 0), *host_call(13, theirs, 1),
                              0x33, words=words))
        s = Session(r)
        s.engine.game_key = 'cod'
        s.engine.ui_defaults[74] = 0
        s.engine.character_art_variants.update({0: [2000], 1: [2001]})
        s.advance()
        self.assertEqual((s.engine.dialogue_animation.portrait.mode, s.engine.notice_mode), (1, 1))
        answer_screen(s)
        self.assertEqual(s.engine.dialogue_animation.portrait.mode, 2)
        self.assertEqual((s.engine.notice, s.engine.notice_mode), ('Detective Score Up!', 1))

    def test_a_save_keeps_the_letters_side(self):
        s = notice_session('Detective Score Up!')
        s.engine.notice_mode = 1
        r = s.resources
        saved = json.loads(json.dumps(s.snapshot()))
        self.assertEqual(Session.from_snapshot(r, saved).engine.notice_mode, 1)
        saved['engine']['notice_mode'] = 3
        with self.assertRaises(SaveError):
            Session.from_snapshot(r, saved)
        saved['version'] = 25
        del saved['engine']['notice_mode']
        self.assertEqual(Session.from_snapshot(r, saved).engine.notice_mode, 0)


class NoticeTests(unittest.TestCase):
    def test_queue_replaces_and_substitutes_before_the_next_dialogue(self):
        words, (first, second, line) = text_words('Old message', '$SKILL improved', 'A new day.')
        r = Resources(program(*host_call(88, first), *host_call(88, second),
                              *host_call(8, line, line, -1, 0), *host_call(13, line, 0),
                              0x33, words=words))
        s = Session(r)
        s.engine.strings['$SKILL'] = 'Agility'
        s.engine.numbers[401] = 7
        s.engine.result_cells[0] = 42
        random_before = copy.deepcopy((s.engine.random, s.engine.random48))
        self.assertEqual(s.advance().name, 'presentation')
        self.assertEqual((s.engine.notice, s.engine.notice_ms), ('', 0))
        s.tick(10000)
        self.assertEqual(s.engine.next_dialogue_notice, 'Agility improved')
        s = Session.from_snapshot(r, json.loads(json.dumps(s.snapshot())))
        s.engine.strings['$SKILL'] = 'Focus'
        self.assertEqual(s.answer().name, 'dialogue')
        self.assertEqual(s.engine.notice, 'Agility improved')
        self.assertEqual(s.engine.next_dialogue_notice, '')
        self.assertEqual(s.engine.numbers[401], 7)
        self.assertEqual(s.engine.result_cells[0], 42)
        self.assertEqual((s.engine.random, s.engine.random48), random_before)
        self.assertEqual(s.engine.sound_serial, 0)

    def test_varied_messages_resume_each_animation_phase_without_resuming_the_vm(self):
        for text in ('Power gained', 'Confidence lost', '+2 to Study', 'A much longer announcement!', 'New\nSkill'):
            with self.subTest(text=text):
                s = notice_session(text)
                held = s.vm.snapshot()
                for age in (15, 75, (len(text) + 1) * 165, notice_lifetime(text) - 150):
                    s.tick(age - NoticeMotion(s.engine.notice, s.engine.notice_ms).elapsed_ms)
                    saved = json.loads(json.dumps(s.snapshot()))
                    restored = Session.from_snapshot(s.resources, saved)
                    self.assertEqual(restored.snapshot(), s.snapshot())
                    s.tick(1); restored.tick(1)
                    self.assertEqual(restored.snapshot(), s.snapshot())
                    self.assertEqual(s.vm.snapshot(), held)
                s.tick(s.engine.notice_ms)
                self.assertEqual((s.engine.notice, s.engine.notice_ms), ('', 0))
                self.assertEqual(s.vm.snapshot(), held)
                self.assertEqual(s.pending.name, 'dialogue')

    def test_first_tap_hides_notice_without_bypassing_reveal_or_page_input(self):
        s = notice_session()
        # An authored four-character page separates reveal, page, and VM gates.
        s.resources.dialogue_layout = lambda: SimpleNamespace(
            page=lambda details, start, **kwargs: SimpleNamespace(end=min(start + 4, len(details['text']))))
        s._prepare_dialogue()
        held = s.vm.snapshot()
        s.answer()
        self.assertEqual((s.engine.notice, s.engine.notice_ms), ('', 0))
        self.assertEqual(s.vm.snapshot(), held)
        self.assertTrue(s.engine.dialogue_animation.finish_requested)
        s.tick(2000)
        s.answer()
        self.assertEqual(s.pending.details['page_start'], 4)
        self.assertEqual(s.vm.snapshot(), held)
        self.assertEqual(s.engine.notice_ms, 0)

    def test_old_notice_countdown_is_preserved_and_invalid_timers_are_rejected(self):
        s = notice_session('New skill')
        old = s.snapshot()
        # Previous rendering stored the shorter lifetime without a motion clock.
        old['engine']['notice_ms'] = len(s.engine.notice) * 165 + 300 - 800
        untouched = copy.deepcopy(old)
        restored = Session.from_snapshot(s.resources, old)
        self.assertEqual(old, untouched)
        self.assertEqual(restored.engine.notice_ms, old['engine']['notice_ms'])
        self.assertEqual(restored.vm.snapshot(), s.vm.snapshot())
        for text, remaining in (('', 1), ('New skill', -1), ('New skill', 1951)):
            bad = copy.deepcopy(old)
            bad['engine'].update(notice=text, notice_ms=remaining)
            with self.subTest(text=text, remaining=remaining), self.assertRaises(SaveError):
                Session.from_snapshot(s.resources, bad)

    def test_letter_motion_uses_drawn_indices_and_exit_moves_the_parent(self):
        # Spaces affect the deadline, but do not allocate animated child tags.
        motion = NoticeMotion('A V', 930)  # Full 960ms lifetime, 30ms elapsed.
        self.assertEqual((motion.glyph_rise(0), motion.glyph_rise(1)), (40, 20))
        self.assertEqual(motion.origin(Rect(0, 200, 120, 120), 1), (0, 205))
        self.assertEqual(motion.origin(Rect(200, 200, 120, 120), 2), (0, 205))
        for length, scale in ((18, 1.0), (19, .88)):
            exiting = NoticeMotion('A' * length, 150)
            self.assertEqual(exiting.scale, scale)
            self.assertEqual(exiting.alpha, 127)
            self.assertAlmostEqual(exiting.glyph_rise(0), 40 * scale + 25)

    @unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra required')
    def test_authored_font_pixels_follow_the_wave_and_hidden_parent(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        import pygame
        from exp_runtime.desktop import Desktop
        from exp_runtime.desktop_dialogue import DialogueRenderer
        from exp_runtime.desktop_text import BitmapTextRenderer
        pygame.display.init()
        pygame.display.set_mode((320, 480))
        self.addCleanup(pygame.quit)
        atlas = pygame.Surface((2, 3), pygame.SRCALPHA)
        atlas.fill((240, 50, 20, 255))
        encoded = BytesIO()
        pygame.image.save(atlas, encoded, 'test.png')
        assets = {f'fonts/{NOTICE_FONT}.fnt': descriptor(), 'fonts/test.dat': encoded.getvalue()}
        text = BitmapTextRenderer(SimpleNamespace(read_ui_asset=assets.__getitem__))
        bank = SimpleNamespace(rectangle=lambda *_: Rect(0, 200, 120, 120))
        r = SimpleNamespace(dialogue_layout=lambda: SimpleNamespace(bank=bank))
        renderer = DialogueRenderer(r, text, lambda _: None)
        s = notice_session('A V')
        s.engine.dialogue_animation.portrait = SimpleNamespace(mode=1)
        s.tick(30)
        renderer.canvas.fill((0, 0, 0))
        renderer.draw_notice(s.engine)
        # +HD offset rows: DialogueRenderer._portrait_rect's HD vertical correction
        # (see desktop_dialogue.py) shifts the housing rect this test's fake
        # bank returns, and the notice is positioned relative to it.
        shift = DialogueRenderer._HD_PORTRAIT_VERTICAL_OFFSET
        self.assertEqual(renderer.canvas.get_at((1, 171 + shift))[:3], (240, 50, 20))
        self.assertEqual(renderer.canvas.get_at((8, 191 + shift))[:3], (240, 50, 20))
        # Painting is pure and never mutates the glyph cache during the fade.
        before = pygame.image.tobytes(renderer.canvas, 'RGB')
        s.engine.notice_ms = 150
        renderer.draw_notice(s.engine)
        s.engine.notice_ms = 930
        renderer.canvas.fill((0, 0, 0))
        renderer.draw_notice(s.engine)
        self.assertEqual(pygame.image.tobytes(renderer.canvas, 'RGB'), before)
        s.engine.dialogue_animation.portrait = None
        renderer.canvas.fill((0, 0, 0))
        renderer.draw_notice(s.engine)
        self.assertEqual(pygame.image.tobytes(renderer.canvas, 'RGB'), bytes(320 * 480 * 3))
        # The frontend must not spend notice time while its menu or focus is lost.
        ui = Desktop.__new__(Desktop)
        ui.session, ui.error, ui.menu_open, ui.active = s, None, True, True
        ui.panels_open, ui.panels_progress, ui._panels_wide = False, 0.0, False
        ui.pause_elapsed_ms = 400
        remaining = s.engine.notice_ms
        ui.tick(1000)
        ui.menu_open, ui.active = False, False
        ui.tick(1000)
        self.assertEqual(s.engine.notice_ms, remaining)
        ui.active = True
        ui.tick(16)
        self.assertEqual(s.engine.notice_ms, remaining - 16)
