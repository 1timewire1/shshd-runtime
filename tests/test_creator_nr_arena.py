"""The Creator's New Rules minigame node (CREATOR_CATCHUP_PLAN.md Stage 4; decision D, owner 2026-11-17): the library's own game
where the arena plays (after Ask to Skip), the translators' fallback elsewhere. The library itself is the owner's (the shsnr
add-on), so here the call into it is checked as compiled, and the fallbacks are played in the engine."""
from copy import deepcopy
import unittest

from exp_runtime.creator import nr_arena
from exp_runtime.creator.compiler import compile_project
from exp_runtime.creator.debugger import DebugSession
from exp_runtime.creator.features import DEFAULTS
from exp_runtime.creator.model import Node, Project, ProjectError
from exp_runtime.creator.playtest import Playtest
from exp_runtime.decode.bytecode import decode_program
from exp_runtime.exp import ExpArchive


def project(game='rhythm', **params):
    p = deepcopy(DEFAULTS['nr_arena'])
    defaults = nr_arena.DEFAULTS.get(game, nr_arena.DEFAULTS['rhythm'])
    p.update(game=game, target=defaults['target'], intro=defaults['intro'])
    if 'good' in defaults:
        p.update(good=list(defaults['good']), bad=list(defaults['bad']))
    p.update(params)
    nodes = [Node('a', 'nr_arena', params=p, next='b'), Node('b', text='Score {arena_score}.', next='end'), Node('end', 'end')]
    return Project(title='Arena', game='shs', start='a', nodes=nodes, addons=[dict(id='shsnr', revision=3)])


def instructions(game):
    return decode_program(ExpArchive(compile_project(project(game))).read(25001)).instructions


class Compiled(unittest.TestCase):
    def test_each_game_is_called_at_its_entry_as_the_stories_call_it(self):
        for game, (entry, arguments) in nr_arena.GAMES.items():
            with self.subTest(game):
                code = instructions(game)
                jump = next(k for k, i in enumerate(code) if i.opcode == 0x29 and i.operand == entry)
                self.assertEqual(code[jump - 1].opcode, 0x42)                    # SAVE_RETURN, then the jump
                self.assertEqual((code[jump + 1].opcode, code[jump + 1].operand), (0x19, len(arguments)))
                self.assertEqual(code[jump + 2].opcode, 0x08)                    # B, the score
                pushed = code[jump - 1 - len(arguments):jump - 1]
                self.assertEqual(pushed[0].operand, nr_arena.DEFAULTS[game]['target'])
                if game in ('dance_steps', 'beat_boxing'):
                    self.assertEqual([i.operand for i in pushed if i.opcode == 0x40][0], 32426 if game == 'dance_steps' else 32427)

    def test_it_asks_for_the_arena_then_ask_to_skip(self):
        code = instructions('rhyme')
        calls = [(k, i.operand >> 8) for k, i in enumerate(code) if i.opcode == 0x1f]
        query = next(n for n, (k, service) in enumerate(calls) if service == 70)
        self.assertEqual(code[calls[query][0] - 1].operand, nr_arena.ARENA_QUERY)
        self.assertEqual(calls[query + 1][1], nr_arena.ARENA_SKIP)

    def test_it_needs_new_rules_add_on_and_this_runtime(self):
        from exp_runtime.creator.addons import mechanics
        bare = project()
        bare.addons = []
        with self.assertRaisesRegex(ProjectError, 'shsnr'):
            compile_project(bare)
        self.assertEqual(mechanics(project()), ["New Rules' minigame arena"])

    def test_bad_settings_are_refused(self):
        for change in (dict(game='chess'), dict(target=11), dict(bad=['a', 'b']), dict(rhymes=[['a', 'b']]), dict(good=['a|b', 'c'])):
            with self.subTest(change=change):
                with self.assertRaises(ProjectError):
                    compile_project(project(**change))


class Fallbacks(unittest.TestCase):
    """Without the library (no add-on in the playtest's library), service 70 selector 200 answers 0: the fallback plays."""

    def run_to(self, debugger, wanted):
        test = Playtest(debugger)
        state = test.run(until='input')
        self.assertEqual(state['action'], wanted)
        return test

    def test_a_word_game_passed_gives_the_target_and_missed_one_less(self):
        # Rhythm at target 6 needs 16 hits, past the skip prompt's previews (0-15), so its one option, Skip, passes it.
        for skipped, score in ((True, 6), (False, 5)):
            with self.subTest(skipped=skipped):
                debugger = DebugSession(project('rhythm'), seed=1)
                try:
                    test = self.run_to(debugger, 'word_game')
                    if skipped:
                        self.assertEqual([o['label'] for o in test.skip_options()], ['Skip', 'Play'])
                        test.input('skip', value='Skip')
                    else:
                        test.input('tick', milliseconds=31000)                  # no word picked: missed
                    self.assertEqual(test.run()['text'], f'Score {score}.')
                finally:
                    debugger.close()

    def test_rhyme_is_a_speed_diss_of_timed_choices(self):
        debugger = DebugSession(project('rhyme'), seed=1)
        rounds = nr_arena.speed_diss_rounds(DEFAULTS['nr_arena']['rhymes'])
        try:
            test = self.run_to(debugger, 'choice')
            for target, options, answer in rounds[:10]:
                state = test.run(until='choice')
                self.assertIn(target.capitalize(), state['text'])
                test.choose(state['choices'][answer]['id'])
            self.assertEqual(test.run()['text'], 'Score 10.')                  # ten hits win it
        finally:
            debugger.close()

    def test_the_rounds_mix_a_rhyme_among_others(self):
        families = DEFAULTS['nr_arena']['rhymes']
        family = {w: n for n, f in enumerate(families) for w in f}
        rounds = nr_arena.speed_diss_rounds(families)
        self.assertEqual(len(rounds), nr_arena.SPEED_DISS_ROUNDS)
        for target, options, answer in rounds:
            self.assertEqual([family[o] == family[target] for o in options].count(True), 1)
            self.assertEqual(family[options[answer]], family[target])


if __name__ == '__main__':
    unittest.main()
