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


class StoryTests(unittest.TestCase):
    """A creator story calls it as the translated Monday Planner will: service 222 behind the minigames query."""

    def project(self, **params):
        from exp_runtime.creator import Node
        from test_creator_features import sequence
        rounds = [{'target': r[0], 'words': r[1:]} for r in ROUNDS]
        node = Node('b', 'x360_battle', params=dict(result='grade', bonus=2, tutorial=1, rounds=rounds, **params))
        project = sequence(node, Node('said', text='Grade {grade}'))
        project.addons = [dict(id='shsx360', revision=1)]
        return project

    def session(self):
        from test_creator import session_for
        session = session_for(self.project())
        action = session.advance()
        self.assertEqual(action.name, 'x360_battle')
        return session

    def test_the_story_hands_over_its_rounds_and_bonus(self):
        game = self.session().engine.x360_battle
        self.assertEqual(game.rounds, ROUNDS)
        self.assertEqual((game.bonus, game.tutorial), (2, True))

    def test_it_plays_to_the_end_and_the_story_reads_the_grade(self):
        session = self.session()
        for _ in range(2000):
            if session.pending is None or session.pending.name != 'x360_battle':
                break
            game = session.engine.x360_battle
            if game.phase in (xb.TUTORIAL, xb.READY, xb.ENDED) or game.phase == xb.RUNNING:
                session.answer(None)
            session.tick(100)
        self.assertIsNone(session.engine.x360_battle)
        self.assertEqual(session.pending.name, 'dialogue')
        self.assertRegex(session.pending.details['text'], r'^Grade (\d|10)$')

    def test_the_skip_gives_ten_or_none(self):
        for success, grade in ((True, 10), (False, 0)):
            session = self.session()
            self.assertTrue(session.minigame_unstarted)
            action = session.skip_minigame(success)
            self.assertEqual(action.details['text'], f'Grade {grade}')

    def test_a_game_in_progress_saves_and_comes_back_where_it_was(self):
        from exp_runtime.runtime import SaveError, Session
        from test_creator import session_for
        session = self.session()
        session.engine.x360_battle.tutorial = False
        session.engine.x360_battle.start()
        session.tick(250)
        for _ in range(20):
            session.tick(250)
        state = json.loads(json.dumps(session.snapshot()))
        self.assertEqual(state['version'], 40)
        again = Session.from_snapshot(session_for(self.project()).resources, state)
        self.assertEqual(again.engine.x360_battle, session.engine.x360_battle)
        state['engine']['x360_battle']['tier'] = 7
        with self.assertRaises(SaveError):
            Session.from_snapshot(session_for(self.project()).resources, state)

    def test_an_older_save_loads_with_no_battle(self):
        from exp_runtime.runtime import Session
        from test_creator import session_for
        session = session_for(self.project())
        state = json.loads(json.dumps(session.snapshot()))
        state['version'] = 39
        del state['engine']['x360_battle']
        self.assertIsNone(Session.from_snapshot(session_for(self.project()).resources, state).engine.x360_battle)

    def test_the_creator_refuses_rounds_that_arent_whole(self):
        from exp_runtime.creator import ProjectError, compile_project
        for rounds in ([], [{'target': 'cat', 'words': ['hat', 'dog']}], [{'target': 'cat', 'words': ['hat', 'hat', 'a', 'b']}]):
            with self.subTest(rounds=rounds), self.assertRaises(ProjectError):
                compile_project(self._with(rounds))

    def _with(self, rounds):
        project = self.project()
        project.nodes[0].params['rounds'] = rounds
        return project


if __name__ == '__main__':
    unittest.main()
