"""shshd-runtime: what a story asks before its first screen gets the player's answers even when an intro skip runs the opening
first (Day of Diss on the g54, Skip Upsell Intros on, took its no-cutscene branch; owner, 2026-11-11)."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from exp_runtime.cutscene_spec import CUTSCENE_QUERY
from exp_runtime.menu import MenuState
from exp_runtime.runtime import Session
from test_runtime import Resources, host_call, text_words
from test_vm import program

ANSWER = 500


def asking():
    """A story that asks whether cutscenes play, keeps the answer in global ANSWER, then shows a line."""
    words, (line,) = text_words('Hello.')
    body = [(0x1a, CUTSCENE_QUERY), (0x1f, 70 << 8 | 1), (0x1a, ANSWER), 0x21, (0x1f, 54 << 8 | 2),
            *host_call(13, line, 0), 0x33]
    return Resources(program(*body, words=words))


class IntroSkipAnswerTests(unittest.TestCase):
    def answer(self, *, cutscenes, upsell=True, ad=False):
        with tempfile.TemporaryDirectory() as directory:
            resources = asking()
            record = dict(id='a' * 64, pack_id=31400, episode_id=1, titles=['t'] * 5, name='x.exp')
            resources.record = record
            library = SimpleNamespace(directory=Path(directory), episodes=[record], select=lambda selector: record,
                                      open_episode=lambda record: resources)
            state = MenuState(library)
            state.cutscenes = cutscenes
            state.skip_upsell_intros, state.skip_ad_intros = upsell, ad
            session = state.session(record, resume=False)
            session.advance() if session.pending is None else None
            return session.engine.numbers.get(session.engine.number_key(0, ANSWER))

    def test_the_players_answer_reaches_a_story_the_intro_skips_run_first(self):
        self.assertEqual(self.answer(cutscenes=True), 1)                  # Skip Upsell Intros on, as the g54
        self.assertEqual(self.answer(cutscenes=True, upsell=False, ad=True), 1)
        self.assertEqual(self.answer(cutscenes=False), 0)                 # a headless state draws none

    def test_a_menu_state_draws_no_cutscenes_unless_its_player_says(self):
        self.assertFalse(MenuState.cutscenes)
        self.assertFalse(Session.cutscenes)


if __name__ == '__main__':
    unittest.main()
