"""General's Text Animation (owner, 2026-11-22): a dialogue page letter by letter (Android's, the default), in the iOS
builds' line wipe (`-[SHSTextLayer addTypingAnimations:lineTime:]`: 0.6 s a region's width, a tap hurrying it to 0.2 s),
or at once; Autoplay waits as long as the letters would have taken; saves keep the page's mode (version 45, 46 with the Claire Hart branch)."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

from exp_runtime.dialogue_animation import (CONTINUE_MS, WIPE_FAST_LINE_MS, WIPE_LINE_MS, DialogueAnimation)
from exp_runtime.runtime import SaveError, Session
from test_runtime import Resources, host_call, text_words
from test_vm import program


def page(mode, lines=(), length=40):
    motion = DialogueAnimation(length).set_text(mode, lines)
    motion.validate()
    return motion


class TextModeTests(unittest.TestCase):
    def test_instant_shows_the_page_when_its_text_would_start(self):
        motion = page('instant')
        motion.tick(motion.text_delay_ms - 1)
        self.assertFalse(motion.complete)
        motion.validate()
        motion.tick(11)
        self.assertTrue(motion.complete)
        self.assertEqual((motion.revealed, motion.continue_ms), (40, 10))
        motion.validate()
        motion.tick(10_000)                                       # its clock runs on to where the letters would end
        self.assertEqual(motion.elapsed_ms, motion.duration_ms)
        self.assertGreaterEqual(motion.elapsed_ms, motion.letters_end_ms)
        motion.validate()

    def test_a_wipe_crosses_each_line_in_turn_then_completes(self):
        lines = [300, 600, 150]                                   # half, all and a quarter of the region's width
        motion = page('wipe', lines)
        motion.tick(motion.text_delay_ms)
        self.assertEqual(motion.wipe_edges(), [0, 0, 0])
        motion.tick(150)
        self.assertEqual(motion.wipe_edges(), [.25, 0, 0])
        motion.tick(300)                                          # the first line's text is out: the second begins
        self.assertEqual(motion.wipe_edges(), [.75, .25, 0])
        motion.validate()
        motion.tick(599)
        self.assertFalse(motion.complete)
        motion.validate()
        motion.tick(2)
        self.assertTrue(motion.complete)
        self.assertIsNone(motion.wipe_edges())
        self.assertEqual((motion.revealed, motion.continue_ms), (40, 1))
        motion.validate()

    def test_a_tap_hurries_a_wipe_to_speed_up_typings_line_time(self):
        motion = page('wipe', [600, 600])
        motion.tick(motion.text_delay_ms + 300)
        motion.finish()
        self.assertFalse(motion.complete)                         # (it hurries, it does not end)
        rate = WIPE_LINE_MS // WIPE_FAST_LINE_MS
        motion.tick(900 // rate - 1)
        self.assertFalse(motion.complete)
        motion.validate()
        motion.tick(1)
        self.assertTrue(motion.complete)
        motion.validate()

    def test_letters_stay_androids_cadence_and_a_page_turn_keeps_the_mode(self):
        plain, letters = DialogueAnimation(40), page('letters')
        for motion in (plain, letters):
            motion.tick(motion.text_delay_ms + 500)
            motion.validate()
        self.assertEqual((plain.revealed, plain.complete), (letters.revealed, letters.complete))
        wipe = page('wipe', [600])
        wipe.tick(10_000)
        wipe.next_page(20)
        self.assertEqual((wipe.text_mode, wipe.wipe_ms), ('wipe', 0))
        wipe.set_text('wipe', [120])
        wipe.validate()
        wipe.stop_layers()
        self.assertEqual(wipe.wipe_ms, 120)
        wipe.validate()

    def test_bad_states_are_refused(self):
        for broken in (dict(text_mode='typewriter'), dict(wipe_ms=5), dict(text_mode='wipe', wipe_lines=[100], wipe_ms=101),
                       dict(text_mode='instant', revealed=3)):
            motion = page('letters')
            for key, value in broken.items():
                setattr(motion, key, value)
            with self.assertRaises(ValueError, msg=broken):
                motion.validate()


class TextModeSessionTests(unittest.TestCase):
    def session(self, mode):
        words, (first, second) = text_words('The first line of the page.', 'Next.')
        resources = Resources(program(*host_call(13, first, 0), *host_call(13, second, 0), 0x33, words=words))
        resources.library.text_animation = mode
        session = Session(resources)
        session.advance()
        return session

    def test_the_library_sets_each_pages_mode_and_a_save_keeps_it(self):
        session = self.session('instant')
        motion = session.engine.dialogue_animation
        self.assertEqual(motion.text_mode, 'instant')
        session.tick(motion.text_delay_ms + 1)
        self.assertTrue(motion.complete)
        state = session.snapshot()
        self.assertEqual(state['version'], 47)
        restored = Session.from_snapshot(session.resources, state)
        self.assertEqual(restored.engine.dialogue_animation.text_mode, 'instant')

    def test_both_lines_older_saves_load_with_what_their_line_left_out(self):
        # Version 46 joins the Claire Hart branch's 43 / 44 and v1.1.1's 45 (both from 42).
        session = self.session('instant')
        state = session.snapshot()

        def older(version, *, animation=True, claire=True):
            saved = dict(state, version=version)
            saved['engine'] = dict(state['engine'])
            if not animation:
                saved['engine']['dialogue_animation'] = {
                    key: value for key, value in state['engine']['dialogue_animation'].items()
                    if key not in ('text_mode', 'wipe_lines', 'wipe_ms')}
            if not claire:
                for key in ('claire_round', 'story_objects_due', 'story_objects', 'story_objects_speaker'):
                    saved['engine'].pop(key, None)
            return Session.from_snapshot(session.resources, saved)
        for version in (42, 43, 44):        # (no Text Animation yet: letter by letter, as they typed)
            restored = older(version, animation=False, claire=version > 42)
            self.assertEqual(restored.engine.dialogue_animation.text_mode, 'letters')
        restored = older(45, claire=False)  # (v1.1.1's: its mode kept, no round or story objects open)
        self.assertEqual(restored.engine.dialogue_animation.text_mode, 'instant')
        self.assertIsNone(restored.engine.claire_round)
        self.assertEqual(restored.engine.story_objects, [])
        for version in (48, 60):
            with self.assertRaises(SaveError):
                Session.from_snapshot(session.resources, dict(state, version=version))


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class TextModeDesktopTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        from exp_runtime.desktop import Desktop
        self.Desktop = Desktop
        self.addCleanup(pygame.quit)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)

    def ui(self, mode):
        words, (first, second) = text_words('Hi there, this is a longer line.', 'Next.')
        resources = Resources(program(*host_call(13, first, 0), *host_call(13, second, 0), 0x33, words=words))
        resources.library.directory = self.directory
        ui = self.Desktop(Session(resources), audio=False)
        ui.text_animation = mode
        ui.session.engine.dialogue_animation.set_text(mode)      # (the first page began before the setting)
        return ui

    def test_autoplay_waits_out_the_letters_time_on_an_instant_page(self):
        ui = self.ui('instant')
        ui.autoplay = True
        line, motion = ui.session.pending, ui.session.engine.dialogue_animation
        ui.tick(motion.text_delay_ms + 16)
        self.assertTrue(motion.complete)
        while motion.elapsed_ms < motion.letters_end_ms - 16:
            ui.tick(16)
            self.assertIs(ui.session.pending, line)              # (not yet: the letters would still be typing)
        ui.tick(16 + ui.AUTOPLAY_WAIT_MS + 16)
        self.assertIsNot(ui.session.pending, line)

    def test_the_setting_is_the_librarys_and_the_pause_page_picks_it(self):
        ui = self.ui('letters')
        ui.command(('pause_cycle', 'text_animation'))
        self.assertEqual((ui.text_animation, ui.session.resources.library.text_animation), ('wipe', 'wipe'))
        self.assertEqual(ui._pause_settings()['text_animation'], 'Line Wipe')
        ui.command(('pause_cycle', 'text_animation', 'instant'))
        self.assertEqual(ui.text_animation, 'instant')

    def test_a_wipe_draws_its_lines_clipped_while_it_runs(self):
        ui = self.ui('wipe')
        motion = ui.session.engine.dialogue_animation
        page = ui.session.dialogue_page()
        if page is None or not page.body_width:
            self.skipTest('the fixture has no dialogue layout')
        motion.set_text('wipe', [300] * len(page.body.lines))
        ui.tick(motion.text_delay_ms + 150)
        self.assertIsNotNone(motion.wipe_edges())
        ui.render()                                               # (draws each line clipped at its edge)


if __name__ == '__main__':
    unittest.main()
