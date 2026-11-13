"""SHS '11's Memory: its rules (shs11_games.py, N73's `bg`, `cv`, `am`), its saves and the story's call."""
import random
import unittest

from exp_runtime.shs11_games import (SOUND_MISSED_BONUS, BAD, BAD_BOX, CUE, CUE_MS, DEAL, GOAL, HIDDEN, LOOK, MemoryGame, NEXT, NEXT_MS, PENALTY_MS,
                                     PLAY, POINTS_DELAY_MS, READY, RIGHT, SHOWN, SOUND_DONE, SOUND_TIME_UP, SOUND_WRONG, TIME_UP,
                                     TIME_UP_MS, TUTORIAL_CELLS, WRONG)

ROUND = ['I wish I was an elf!', 'ELF', 20, 10, 600, 4000]


class Rng:
    """NativeRandom's one method, from Python's."""

    def __init__(self, seed=1):
        self.random = random.Random(seed)

    def below(self, bound):
        return self.random.randrange(bound)


def game(rounds=(ROUND,), target=300, seconds=60, tutorial=False):
    return MemoryGame.opened(rounds, seconds, target, tutorial=tutorial)


def run(found, ms, rng=None, step=10):
    rng = rng or Rng()
    finished = False
    for _ in range(ms // step):
        finished = found.tick(step, rng) or finished
    return finished


def until(found, phase, limit=20000, rng=None):
    rng = rng or Rng()
    for _ in range(limit // 10):
        if found.phase == phase:
            return
        found.tick(10, rng)
    raise AssertionError(f'never reached {phase}: at {found.phase}')


class RoundTests(unittest.TestCase):
    def playing(self, **kwargs):
        found = game(**kwargs)
        until(found, PLAY)
        return found

    def test_a_round_starts_with_its_cue_and_only_then_deals(self):
        found = game()
        until(found, CUE)
        self.assertEqual(found.landing, [])
        run(found, CUE_MS - 20)
        self.assertEqual(found.phase, CUE)
        run(found, 40)
        self.assertEqual(found.phase, DEAL)

    def test_each_letter_starts_half_a_letter_time_after_the_last_and_takes_a_letter_time(self):
        found = game()
        until(found, DEAL)
        run(found, 300)
        self.assertEqual(len(found.landing), 1)
        run(found, 300)
        self.assertEqual(len(found.landing), 2)
        until(found, PLAY)
        self.assertGreater(found.landing[-1], 600)

    def test_every_cell_is_a_letter_or_a_bad_box_and_all_are_hidden_to_play(self):
        found = self.playing()
        self.assertEqual(sorted(found.cells[cell] for cell in found.order), ['E', 'F', 'L'])
        self.assertEqual(found.cells.count(BAD_BOX), 6)
        self.assertEqual(found.shows, [HIDDEN] * 9)

    def test_the_clock_waits_for_the_first_round_to_be_played(self):
        found = game()
        run(found, 2000)
        self.assertEqual(found.clock_ms, 60000)
        until(found, PLAY)
        self.assertEqual(found.clock_ms, 60000)
        run(found, 500)
        self.assertLess(found.clock_ms, 60000)

    def test_letters_in_order_keep_the_bonus_and_the_points_come_a_second_later(self):
        found = self.playing()
        for cell in found.order:
            found.press(cell)
        self.assertEqual(found.phase, NEXT)
        self.assertIn(SOUND_DONE, found.sounds)
        self.assertEqual(found.score, 0)
        self.assertGreater(found.bonus_ms, 0)
        run(found, POINTS_DELAY_MS + 20)
        self.assertEqual(found.score, 3 * 10 + 20)

    def test_a_letter_out_of_order_scores_but_loses_the_bonus(self):
        found = self.playing()
        for cell in reversed(found.order):
            found.press(cell)
        self.assertEqual(found.phase, NEXT)
        self.assertNotIn(SOUND_DONE, found.sounds)
        self.assertIn(SOUND_MISSED_BONUS, found.sounds)
        self.assertEqual(found.bonus_ms, 0)
        run(found, POINTS_DELAY_MS + 20)
        self.assertEqual(found.score, 30)

    def test_a_bad_box_costs_five_seconds_and_the_bonus(self):
        found = self.playing()
        before = found.clock_ms
        bad = found.cells.index(BAD_BOX)
        self.assertTrue(found.press(bad))
        self.assertEqual(found.clock_ms, before - PENALTY_MS)
        self.assertEqual(found.shows[bad], WRONG)
        self.assertIn(SOUND_WRONG, found.sounds)
        self.assertTrue(found.missed)
        self.assertEqual(found.phase, PLAY)

    def test_a_cell_counts_once(self):
        found = self.playing()
        cell = found.order[0]
        self.assertTrue(found.press(cell))
        self.assertFalse(found.press(cell))
        self.assertEqual(found.found, 1)
        self.assertEqual(found.shows[cell], RIGHT)

    def test_in_relax_a_bad_box_is_the_x_when_it_comes_next_as_in_11(self):
        found = self.playing(rounds=(['Relax!', 'RELAX', 20, 10, 600, 4000],))
        for cell in found.order[:4]:
            found.press(cell)
        bad = next(c for c in range(9) if c not in found.order)
        before = found.clock_ms
        found.press(bad)
        self.assertEqual(found.clock_ms, before)
        self.assertEqual(found.phase, NEXT)

    def test_a_round_ends_at_its_limit_and_the_next_comes_two_seconds_later(self):
        found = self.playing()
        run(found, 3990)
        self.assertEqual(found.phase, PLAY)
        run(found, 30)
        self.assertEqual(found.phase, NEXT)
        self.assertTrue(found.missed)
        run(found, NEXT_MS - 40)
        self.assertEqual(found.phase, NEXT)
        run(found, 60)
        self.assertEqual(found.phase, CUE)

    def test_after_the_last_round_they_repeat_at_random_until_the_clock_runs_out(self):
        rounds = [['One', 'ONE', 20, 10, 600, 500], ['Two', 'TWO', 20, 10, 600, 500]]
        found = game(rounds)
        rng = Rng(5)
        seen = []
        for _ in range(8):
            until(found, CUE, rng=rng)
            seen.append(found.word)
            until(found, NEXT, rng=rng)
        self.assertEqual(seen[:2], ['ONE', 'TWO'])
        self.assertEqual(set(seen[2:]), {'ONE', 'TWO'})


class EndTests(unittest.TestCase):
    def ended(self, score, target=300):
        found = game(target=target)
        until(found, PLAY)
        found.score = score
        found.clock_ms = 10
        self.assertFalse(found.tick(20, Rng()))
        return found

    def test_times_up_holds_three_seconds_and_then_the_story_goes_on(self):
        found = self.ended(0)
        self.assertEqual(found.phase, TIME_UP)
        self.assertIn(SOUND_TIME_UP, found.sounds)
        self.assertFalse(run(found, TIME_UP_MS - 20))
        self.assertTrue(run(found, 40))

    def test_points_still_on_their_way_count_and_it_waits_for_them(self):
        found = game()
        until(found, PLAY)
        found.pending.append([TIME_UP_MS + 500, 10, -1])
        found.clock_ms = 10
        found.tick(20, Rng())
        self.assertFalse(run(found, TIME_UP_MS + 200))
        self.assertTrue(run(found, 400))
        self.assertEqual(found.score, 10)

    def test_the_result_is_2_at_98_percent_1_above_75_and_else_0(self):
        for score, result in ((400, 2), (392, 2), (391, 1), (304, 1), (300, 0), (0, 0)):
            self.assertEqual(self.ended(score, 400).result, result, score)

    def test_a_penalty_can_end_it(self):
        found = game()
        until(found, PLAY)
        found.clock_ms = 3000
        found.press(found.cells.index(BAD_BOX))
        self.assertEqual(found.clock_ms, 0)
        found.tick(10, Rng())
        self.assertEqual(found.phase, TIME_UP)


class TutorialTests(unittest.TestCase):
    def test_its_boxes_wait_for_a_press_and_then_the_game_starts_from_the_first_round(self):
        found = game(tutorial=True)
        self.assertEqual(found.phase, GOAL)
        run(found, 10000)
        self.assertEqual(found.phase, GOAL)
        self.assertTrue(found.press())
        self.assertEqual(found.phase, CUE)
        until(found, LOOK)
        self.assertEqual(found.order, list(TUTORIAL_CELLS[:3]))
        run(found, 10000)
        self.assertEqual(found.phase, LOOK)
        found.press()
        self.assertEqual(found.phase, SHOWN)
        self.assertEqual([cell for cell in range(9) if found.shows[cell] == RIGHT], sorted(found.order))
        found.press()
        self.assertEqual(found.phase, BAD)
        self.assertEqual(found.shows.count(WRONG), 6)
        found.press()
        self.assertEqual(found.phase, READY)
        found.press()
        self.assertEqual(found.phase, NEXT)
        self.assertFalse(found.tutorial)
        until(found, PLAY)
        self.assertEqual(found.round, 0)
        self.assertEqual(found.clock_ms, 60000)

    def test_a_pick_does_nothing_in_its_boxes_and_a_bare_press_nothing_in_play(self):
        found = game(tutorial=True)
        self.assertFalse(found.press(3))
        self.assertEqual(found.phase, GOAL)
        found = game()
        until(found, PLAY)
        self.assertFalse(found.press())

    def test_a_state_that_doesnt_add_up_is_refused(self):
        found = game()
        found.validate()
        found.phase = 'nope'
        with self.assertRaises(ValueError):
            found.validate()


if __name__ == '__main__':
    unittest.main()
