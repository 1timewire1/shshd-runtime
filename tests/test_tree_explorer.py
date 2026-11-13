from types import SimpleNamespace
import unittest

from exp_runtime.tree_explorer import Explorer
from test_runtime import Resources, branching_program, host_call, text_words
from test_vm import program


class ExplorerTests(unittest.TestCase):
    def test_every_alternative_of_a_choice_is_taken_and_each_run_reaches_the_end(self):
        explorer = Explorer(Resources(branching_program()), seed=1, ephemeral=True)
        runs = explorer.explore(runs=10)
        self.assertTrue(all(run.finished and not run.error for run in runs))
        self.assertEqual(sorted(alternative for counts in explorer.taken.values() for alternative in counts), [0, 1])
        self.assertEqual(explorer.unexplored(), {})
        self.assertLess(len(runs), 10)              # it stops once nothing is left to try

    def test_a_run_takes_the_least_tried_alternative_and_counts_new_results(self):
        explorer = Explorer(Resources(branching_program()), seed=0, ephemeral=True)
        first, second = explorer.play(1), explorer.play(2)
        self.assertEqual((first.new_alternatives, second.new_alternatives), (1, 1))
        self.assertNotEqual(first.decisions[0][2], second.decisions[0][2])

    def test_a_timed_choice_can_also_be_left_to_run_out(self):
        explorer = Explorer(Resources(program(0x33)), ephemeral=True)

        def session(timeout_ms, ticks=None, answers=None):
            details = dict(enabled=[True, False], timeout_ms=timeout_ms)
            return SimpleNamespace(
                pending=SimpleNamespace(name='choice', details=details, request=SimpleNamespace(pc=7)),
                scene=25001, engine=SimpleNamespace(dt_view=SimpleNamespace(current=None)),
                tick=lambda ms: ticks.append(ms), answer=lambda index: answers.append(index))
        self.assertEqual(explorer.alternatives(session(0)), [0])
        self.assertEqual(explorer.alternatives(session(3000)), [0, 'timeout'])
        ticks, answers = [], []
        playthrough = SimpleNamespace(decisions=[], new_alternatives=0)
        for _ in range(2):
            explorer.act(session(3000, ticks, answers), playthrough)
        self.assertEqual((ticks, answers), ([3001], [0]))     # one run each way, the timeout past the last 0 ms

    def test_a_fade_queued_by_a_dialogue_tap_is_played_out(self):
        # CoD MTX_Secret_Files_02's exit: service 16 queues fade 6, so the tap on the next line starts the fade and
        # the line stays pending, ignoring taps, until the fade ends.
        words, refs = text_words('Come down and visit anytime!')
        resources = Resources(program(*host_call(16, 6), *host_call(13, refs[0], 0), 0x33, words=words))
        resources.library.game_id = 'cod'
        run = Explorer(resources, ephemeral=True).play(1)
        self.assertEqual((run.finished, run.error), (True, ''))
        self.assertLess(run.screens, 10)

    def test_mini_games_are_decided_with_their_result_values(self):
        explorer = Explorer(Resources(program(0x33)), ephemeral=True)
        for kind, outcomes in (('football', {'win', 'tie', 'loss'}), ('word_grid', {'pass', 'fail'}),
                               ('word_game', {'good', 'none'}), ('dialogue', None)):
            session = SimpleNamespace(pending=SimpleNamespace(name=kind))
            found = explorer.alternatives(session)
            self.assertEqual(found if outcomes is None else set(found), outcomes)


if __name__ == '__main__':
    unittest.main()
