"""The player's "Ask to skip mini-games" option: the result a skipped football game or word grid hands the script."""
from types import SimpleNamespace
import unittest

from exp_runtime.runtime import Session
from exp_runtime.vm import VMError


def waiting(kind, **game):
    resumed = []
    session = SimpleNamespace(pending=SimpleNamespace(name=kind), vm=SimpleNamespace(resume=resumed.append),
                              engine=SimpleNamespace(football=None, word_grid=None, football_scores=None),
                              advance=lambda: 'advanced')
    setattr(session.engine, kind, SimpleNamespace(**game))
    return session, resumed


class SkipMinigameTests(unittest.TestCase):
    def test_a_skipped_football_game_is_won_or_lost_by_a_touchdown_from_its_starting_score(self):
        session, resumed = waiting('football', home=0, away=0)
        self.assertEqual(Session.skip_minigame(session, True), 'advanced')
        self.assertEqual((session.engine.football_scores, resumed), ([7, 0], [7]))
        self.assertIsNone(session.pending)
        self.assertIsNone(session.engine.football)
        session, resumed = waiting('football', home=0, away=0)
        Session.skip_minigame(session, False)
        self.assertEqual((session.engine.football_scores, resumed), ([0, 7], [-7]))

    def test_a_game_that_starts_mid_match_still_ends_the_way_asked(self):
        # Football Star's second-half game starts at 35-21: a loss must still be a loss.
        session, resumed = waiting('football', home=35, away=21)
        Session.skip_minigame(session, False)
        self.assertEqual(session.engine.football_scores, [35, 42])
        self.assertLess(resumed[0], 0)
        session, resumed = waiting('football', home=35, away=21)
        Session.skip_minigame(session, True)
        self.assertEqual(session.engine.football_scores, [42, 21])

    def test_a_skipped_word_grid_passes_or_fails(self):
        for won, result in ((True, 1), (False, 0)):
            session, resumed = waiting('word_grid', score=0, target=1000)
            Session.skip_minigame(session, won)
            self.assertEqual(resumed, [result])
            self.assertIsNone(session.engine.word_grid)

    def test_only_a_football_game_or_word_grid_can_be_skipped(self):
        session = SimpleNamespace(pending=SimpleNamespace(name='word_game'))
        with self.assertRaises(VMError):
            Session.skip_minigame(session, True)


if __name__ == '__main__':
    unittest.main()
