"""The X360 Monday Planner's real Diss Battle (owner, 2026-11-16): New Rules' Rhyme on Diss Practice's turntable, with
the practice's streak tiers multiplying the points."""
from dataclasses import asdict
import json
import unittest

from exp_runtime import x360_battle as xb
from exp_runtime.randomness import Random48

ROUNDS = [['crash', 'trash', 'chatter', 'ride', 'rat'], ['rude', 'lewd', 'crook', 'socks', 'store'],
          ['cradle', 'ladle', 'crime', 'tool', 'door']]
FRAME = 50 / 3


def running(**kwargs):
    game = xb.DissBattle.opened(ROUNDS, tutorial=False, **kwargs)
    random = Random48()
    game.start()
    game.tick(xb.OPENING_MS + xb.COUNTDOWN_MS + 40, random)
    game.block_ms = 0
    return game, random


def catch(game, random, word):
    """Turn the record until the place holding `word` (0 the rhyme) is in the arm's reach, press, and let the arm reach it."""
    place = next(i for i, slot in enumerate(game.slots) if slot['word'] == word)
    for start in range(360):
        trial = xb.DissBattle(**json.loads(json.dumps(asdict(game))))
        trial.angle = (game.angle + start) % 360
        trial.press()
        before = (trial.right, trial.wrong)
        for _ in range(30):
            trial.tick(FRAME, Random48())
            if (trial.right, trial.wrong) != before:
                break
        wanted = (before[0] + 1, before[1]) if word == 0 else (before[0], before[1] + 1)
        if (trial.right, trial.wrong) == wanted and trial.slots[place]['word'] == xb.NO_WORD:
            game.angle = (game.angle + start) % 360
            game.press()
            for _ in range(30):
                game.tick(FRAME, random)
                if game.slots[place]['word'] == xb.NO_WORD:
                    return
    raise AssertionError(f'word {word} never came under the arm')


class DissBattleTests(unittest.TestCase):
    def test_it_needs_whole_rounds(self):
        with self.assertRaises(ValueError):
            xb.DissBattle.opened([['crash', 'trash', 'rat']])
        with self.assertRaises(ValueError):
            xb.DissBattle.opened([['crash', 'trash', 'rat', 'rat', 'ride']])

    def test_four_words_ride_the_record_and_the_rhyme_scores_with_a_new_target(self):
        game, random = running()
        self.assertEqual(sorted(slot['word'] for slot in game.slots), [0, 1, 2, 3])
        target = game.target
        catch(game, random, 0)
        self.assertEqual((game.score, game.right, game.streak), (3, 1, 1))
        game.tick(xb.REDEAL_MS + 50, random)
        self.assertNotEqual(game.target, target)            # never the same target twice running
        self.assertEqual(sorted(slot['word'] for slot in game.slots), [0, 1, 2, 3])

    def test_a_wrong_word_costs_three_never_below_zero_and_keeps_the_target(self):
        game, random = running()
        target = game.target
        catch(game, random, 1)
        self.assertEqual((game.score, game.wrong), (0, 1))
        self.assertEqual(game.target, target)
        self.assertEqual(sorted(slot['word'] for slot in game.slots), [xb.NO_WORD, 0, 2, 3])
        catch(game, random, 0)
        self.assertEqual(game.score, 3)
        game.tick(xb.REDEAL_MS + 50, random)
        catch(game, random, 2)
        catch(game, random, 3)
        self.assertEqual(game.score, 0)                     # 3 - 3 - 3, floored at 0

    def test_the_streak_doubles_then_triples_the_points_and_a_miss_resets_it(self):
        game, random = running()
        total = 0
        for n in range(1, xb.FIRE_STREAK + 2):
            catch(game, random, 0)
            game.tick(xb.REDEAL_MS + 50, random)
            tier = 3 if n > xb.FIRE_STREAK else 2 if n > xb.DOUBLE_STREAK else 1
            total += 3 * tier
            self.assertEqual(game.score, total, n)
        self.assertEqual(game.tier, 3)
        catch(game, random, 1)
        self.assertEqual((game.streak, game.tier, game.score), (0, 1, total - 3))

    def test_new_rules_scoring_has_no_tiers(self):
        game, random = running()
        game.tiers = False
        for _ in range(xb.DOUBLE_STREAK + 2):
            catch(game, random, 0)
            game.tick(xb.REDEAL_MS + 50, random)
        self.assertEqual(game.score, 3 * (xb.DOUBLE_STREAK + 2))

    def test_the_grade_uses_the_tuned_thresholds_and_the_first_play_bonus(self):
        self.assertEqual(xb.grade(0), 0)
        self.assertEqual(xb.grade(xb.GRADE_THRESHOLDS[6]), 7)
        self.assertEqual(xb.grade(xb.GRADE_THRESHOLDS[6] - 1), 6)
        self.assertEqual(xb.nr_grade(35), 7)
        game = xb.DissBattle.opened(ROUNDS, bonus=xb.FIRST_PLAY_BONUS)
        game.score = xb.GRADE_THRESHOLDS[4]
        self.assertEqual(game.result, 7)
        game.score = 10 ** 4
        self.assertEqual(game.result, 10)

    def test_it_runs_forty_seconds_spins_down_and_closes(self):
        game, random = running()
        steps = 0
        while not game.tick(100, random):
            steps += 1
            if game.phase == xb.ENDED:
                game.press()
            self.assertLess(steps, 1000)
        self.assertEqual(game.total_time, 0)
        self.assertEqual(game.velocity, 0)

    def test_a_saved_game_plays_on_identically(self):
        game, random = running()
        catch(game, random, 0)
        game.tick(2345, random)
        saved = json.loads(json.dumps(asdict(game)))
        copy, copy_random = xb.DissBattle(**saved), Random48(random.state)
        copy.validate()
        for g, r in ((game, random), (copy, copy_random)):
            g.press()
            g.tick(5000, r)
        self.assertEqual(asdict(game), asdict(copy))
        saved['tier'] = 4
        with self.assertRaises(ValueError):
            xb.DissBattle(**saved).validate()


if __name__ == '__main__':
    unittest.main()
