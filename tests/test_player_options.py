"""This player's options in HD's General page: Autoplay Dialogue and Disable Choice Timer, and the skip prompt over a
word quiz."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

from exp_runtime.runtime import Session
from test_choice import timed_resources
from test_runtime import Resources, branching_program, host_call, text_words
from test_vm import program


class ExpireChoiceTests(unittest.TestCase):
    def test_a_held_clock_waits_and_expire_runs_the_native_timeout(self):
        session = Session(timed_resources(1, timeout=2000, selection=1))
        session.advance()
        session.choice_timer = False
        session.tick(5000)
        self.assertEqual((session.pending.name, session.remaining_ms), ('choice', 2000))
        held = Session(timed_resources(1, timeout=2000, selection=1))
        held.advance()
        held.tick(2001)                                          # the clock running out by itself, for comparison
        session.expire_choice()
        self.assertEqual(session.pending.request.args, held.pending.request.args)
        self.assertFalse(session.choice_timer)                   # the hold stays as the host set it
        with self.assertRaises(ValueError):
            session.expire_choice()

    def test_an_untimed_choice_has_nothing_to_expire(self):
        session = Session(Resources(branching_program()))
        session.advance()
        with self.assertRaises(ValueError):
            session.expire_choice()


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class DesktopOptionTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        from exp_runtime.desktop import Desktop
        self.Desktop = Desktop
        self.addCleanup(pygame.quit)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)

    def ui(self, resources):
        resources.library.directory = self.directory
        return self.Desktop(Session(resources), audio=False)

    def test_disable_choice_timer_shows_an_untimed_choice_with_a_run_out_row(self):
        from exp_runtime.desktop import LET_TIME_RUN_OUT_LABEL
        ui = self.ui(timed_resources(1, timeout=2000, selection=1))
        ui.disable_choice_timer = True
        self.assertFalse(ui.session.choice_timer)
        source = ui._choice_source()
        self.assertIsNot(source, ui.session)
        self.assertIsNone(source.remaining_ms)
        self.assertEqual(source.pending.details['options'][-1], LET_TIME_RUN_OUT_LABEL)
        self.assertEqual(source.pending.details['timeout_ms'], 0)
        self.assertIs(ui._choice_source(), source)               # one stand-in per choice
        ui.tick(5000)
        self.assertEqual((ui.session.pending.name, ui.session.remaining_ms), ('choice', 2000))
        action = ui.session.pending
        self.assertTrue(ui._timeout_row(action, 3))
        self.assertFalse(ui._timeout_row(action, 2))
        ui._pick(action, 3)                                      # the last row: the time runs out
        self.assertIsNot(ui.session.pending, action)
        expected = Session(timed_resources(1, timeout=2000, selection=1))
        expected.advance(); expected.tick(2001)
        self.assertEqual(ui.session.pending.request.args, expected.pending.request.args)

    def test_disable_choice_timer_leaves_ordinary_picks_and_untimed_choices_alone(self):
        ui = self.ui(timed_resources(1, timeout=2000, selection=1))
        ui.disable_choice_timer = True
        action = ui.session.pending
        ui.session.tick(250)
        ui._pick(action, 0)
        expected = Session(timed_resources(1, timeout=2000, selection=1))
        expected.advance(); expected.tick(250); expected.answer(0)
        self.assertEqual(ui.session.pending.request.args, expected.pending.request.args)
        plain = self.ui(Resources(branching_program()))
        plain.disable_choice_timer = True
        self.assertIs(plain._choice_source(), plain.session)
        plain.disable_choice_timer = False
        self.assertTrue(plain.session.choice_timer)

    def test_autoplay_ignores_taps_and_advances_after_the_text_is_out(self):
        words, (first, second) = text_words('The first line.', 'The second line.')
        ui = self.ui(Resources(program(*host_call(13, first, 0), *host_call(13, second, 0), 0x33, words=words)))
        ui.autoplay = True
        first_line = ui.session.pending
        ui.command(('continue',))                                # taps do nothing, not even finish the reveal
        self.assertIs(ui.session.pending, first_line)
        self.assertFalse(ui.session.engine.dialogue_animation.complete)
        for _ in range(400):                                     # the letters, then the wait
            if ui.session.pending is not first_line:
                break
            ui.tick(16)
        self.assertEqual(ui.session.pending.details['text'], 'The second line.')

    def test_autoplay_waits_once_the_text_is_out(self):
        words, (first, second) = text_words('Hi.', 'Next.')
        ui = self.ui(Resources(program(*host_call(13, first, 0), *host_call(13, second, 0), 0x33, words=words)))
        ui.autoplay = True
        line = ui.session.pending
        while not ui.session.engine.dialogue_animation.complete:
            ui.tick(16)
        self.assertEqual(ui.AUTOPLAY_WAIT_MS, 750)
        ui.tick(ui.AUTOPLAY_WAIT_MS - 20)
        self.assertIs(ui.session.pending, line)
        ui.tick(20)
        self.assertIsNot(ui.session.pending, line)

    def test_autoplay_gives_a_title_card_longer(self):
        words, (title, subtitle, line) = text_words('Chapter One', 'A beginning.', 'After the card.')
        ui = self.ui(Resources(program(*host_call(8, title, subtitle, 1000, 0), *host_call(13, line, 0), 0x33,
                                       words=words)))
        ui.autoplay = True
        card = ui.session.pending
        self.assertEqual(card.name, 'presentation')
        while not ui.session.engine.title_screen.ready:
            ui.tick(16)
        ui.tick(ui.AUTOPLAY_WAIT_MS)                             # a dialogue's wait is not enough
        self.assertIs(ui.session.pending, card)
        ui.tick(ui.AUTOPLAY_TITLE_WAIT_MS - ui.AUTOPLAY_WAIT_MS)
        self.assertIsNot(ui.session.pending, card)

    def test_autoplay_leaves_choices_to_the_player(self):
        ui = self.ui(Resources(branching_program()))
        ui.autoplay = True
        choice = ui.session.pending
        for _ in range(200):
            ui.tick(16)
        self.assertIs(ui.session.pending, choice)

    def test_the_skip_prompt_opens_over_a_word_quiz_and_draws_as_a_choice(self):
        words, refs = text_words('Title', 'Pick', 'yes|right', 'no|wrong|bad')
        ui = self.ui(Resources(program(*host_call(71, *refs, 20000, -1, 1, 3000), 0x33, words=words)))
        self.assertEqual(ui.session.pending.name, 'word_game')
        ui.skip_minigames = True
        prompt = ui._host_prompt()
        self.assertIsNotNone(prompt)
        self.assertIn('Word quiz', prompt['session'].pending.details['text'])
        self.assertIsNone(prompt['session'].engine.word_game)     # drawn as an ordinary choice
        self.assertIsNotNone(ui.session.engine.word_game)
        prompt['resolve'](1)                                      # Lose: the quiz scores nothing
        self.assertNotEqual(getattr(ui.session.pending, 'name', None), 'word_game')


if __name__ == '__main__':
    unittest.main()
