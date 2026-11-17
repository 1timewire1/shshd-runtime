"""The Creator's playtest plays and skips every translated mini-game and storyboard cutscene as the player does: the same
Session calls, the skip prompt's options and outcomes, time passing in frames (Creator catch-up Stage 1, 2026-11-17)."""
from copy import deepcopy
from importlib.util import find_spec
import unittest

from exp_runtime.creator.addons import NODE_ADDONS, OPTIONAL_NODE_ADDONS
from exp_runtime.creator.cutscenes import blank_shot, blank_spec, save_cutscene
from exp_runtime.creator.debugger import DebugSession
from exp_runtime.creator.features import DEFAULTS
from exp_runtime.creator.model import Node, Project, ProjectError
from exp_runtime.creator.playtest import ENDS, Playtest, run_scenario

QUERY = {'x360_slot': '', 'x360_leash': '', 'x360_puzzle': '', 'x360_diss': '', 'x360_battle': 'x360_battle',
         'shs11_memory': 'shs11', 'shs11_reflex': 'shs11', 'brew_catch': 'brew_catch'}
SIZES = {'109': [20, 24], '149': [18, 18], '156': [16, 16]}
# What each game hands its story when won, and the line after that tells the two ways apart.
WON = {'x360_slot': ('slot_points >= 3', 3), 'x360_leash': ('leash_won == 1', 1), 'x360_diss': ('diss_score > 0', None),
       'x360_battle': ('battle_grade >= 5', 10), 'shs11_memory': ('memory_result >= 2', 2),
       'shs11_reflex': ('reflex_result >= 2', 2), 'brew_catch': ('catch_score >= 45', 45)}


def image_bytes():
    from io import BytesIO
    from PIL import Image
    output = BytesIO()
    Image.new('RGBA', (32, 48), (90, 160, 70, 255)).save(output, format='PNG')
    return output.getvalue()


def project(kind, branch=True):
    params = deepcopy(DEFAULTS[kind])
    if kind == 'brew_catch':
        params['sizes'] = dict(SIZES)
    addon = NODE_ADDONS.get(kind) or OPTIONAL_NODE_ADDONS.get(kind)
    after = (Node('b', 'branch', params={'expression': WON[kind][0]}, next='won', otherwise='lost') if branch and kind in WON
             else Node('b', 'dialogue', text='After.', next='end'))
    return Project(title='Games', game='shs', start='q', nodes=[
        Node('q', 'minigames_available', params={'for': QUERY[kind], 'result': 'real'}, next='a'),
        Node('a', kind, params=params, next='b'), after,
        Node('won', 'dialogue', text='Won.', next='end'), Node('lost', 'dialogue', text='Lost.', next='end'),
        Node('end', 'end')], addons=[dict(id=addon, revision=99)] if addon else [])


def playtest(kind, **options):
    debugger = DebugSession(project(kind, **{k: options.pop(k) for k in ('branch',) if k in options}), seed=1, **options)
    test = Playtest(debugger)
    return debugger, test


class SkipPrompt(unittest.TestCase):
    def test_each_game_stops_for_input_with_its_state_and_the_skip_prompt(self):
        for kind in QUERY:
            with self.subTest(kind):
                debugger, test = playtest(kind)
                try:
                    state = test.run()
                    self.assertEqual((state['action'], state['stop_reason']), (kind, 'input'))
                    self.assertIn('press', state['next_actions'])
                    self.assertIn('skip', state['next_actions'])
                    self.assertEqual(state['minigame']['kind'], kind)
                    self.assertFalse(state['minigame']['started'])
                    self.assertEqual(state['minigame']['waits_for'], 'skip prompt or go-ahead')
                    labels = [option['label'] for option in test.skip_options()]
                    self.assertEqual(labels, ['Skip', 'Play'] if kind == 'x360_puzzle' else ['Win', 'Lose', 'Play'])
                finally:
                    debugger.close()

    def test_win_and_lose_hand_the_story_what_the_player_s_skip_does(self):
        for kind, (_, best) in WON.items():
            for label, line in (('Win', 'Won.'), ('Lose', 'Lost.')):
                with self.subTest(kind=kind, option=label):
                    debugger, test = playtest(kind)
                    try:
                        test.run()
                        result = test.input('skip', value=label)
                        self.assertIsNone(result['error'])
                        variable = DEFAULTS[kind]['result']
                        if label == 'Lose':
                            self.assertEqual(result['variables'][variable], 0)
                        elif best is not None:
                            self.assertEqual(result['variables'][variable], best)
                        self.assertIn(test.run(until='choice')['action'], ENDS)
                        self.assertIn(line, [row['text'] for row in test.transcript])
                    finally:
                        debugger.close()

    def test_a_story_that_goes_one_way_offers_skip_and_an_option_by_index(self):
        debugger, test = playtest('x360_slot', branch=False)
        try:
            test.run()
            self.assertEqual([o['label'] for o in test.skip_options()], ['Skip', 'Play'])
            test.input('skip', value=0)
            self.assertEqual(test.run()['text'], 'After.')
        finally:
            debugger.close()

    def test_an_unknown_option_is_refused_and_the_game_stays(self):
        debugger, test = playtest('x360_leash')
        try:
            test.run()
            result = test.input('skip', value='Maybe')
            self.assertIn('Win, Lose, Play', result['error'])
            self.assertEqual(result['action'], 'x360_leash')
        finally:
            debugger.close()

    def test_options_leave_the_live_session_where_it_was(self):
        # The outcomes are worked out on copies; the debugger's stepping wrapper must not step this session's VM for them.
        debugger, test = playtest('x360_slot')
        try:
            test.run()
            before = (debugger.session.vm.pc, debugger.session.vm.steps_executed, debugger.session.pending)
            test.skip_options()
            self.assertEqual((debugger.session.vm.pc, debugger.session.vm.steps_executed, debugger.session.pending), before)
            self.assertIn('run', debugger.session.vm.__dict__)          # the wrapper is back
        finally:
            debugger.close()

    def test_play_starts_the_game_and_no_prompt_is_offered_after(self):
        debugger, test = playtest('x360_slot')
        try:
            test.run()
            state = test.input('skip', value='Play')
            self.assertTrue(state['minigame']['started'])
            self.assertNotIn('skip', state['next_actions'])
            with self.assertRaises(ProjectError):
                test.skip_options()
        finally:
            debugger.close()


class Played(unittest.TestCase):
    def play_out(self, kind, seconds=150):
        """Play as someone following what the state says it waits for: OKs, presses and cells, a second apart."""
        debugger, test = playtest(kind)
        try:
            state = test.run()
            waited = set()
            for second in range(seconds):
                waits = state['minigame']['waits_for']
                waited.add(waits)
                if waits in ('press', 'skip prompt or go-ahead'):
                    state = test.input('press', milliseconds=1000)
                elif waits == 'cell':
                    state = test.input('press', value=second % 9, milliseconds=1000)
                else:
                    state = test.input('tick', milliseconds=1000)
                self.assertIsNone(state['error'], kind)
                if state['action'] != kind:
                    break
            self.assertNotEqual(state['action'], kind)                  # it ended, as the player's does
            return test.run(until='choice'), waited
        finally:
            debugger.close()

    def test_each_game_plays_to_its_end_following_what_it_waits_for(self):
        for kind in QUERY:
            with self.subTest(kind):
                state, waited = self.play_out(kind)
                self.assertIn(state['action'], ENDS)
                if kind in ('shs11_memory', 'shs11_reflex'):
                    self.assertIn('cell', waited)

    def test_a_press_while_running_counts_and_time_passes_in_frames(self):
        debugger, test = playtest('x360_slot')
        try:
            test.run()
            test.input('tick', milliseconds=1000)                       # its opening ignores presses
            state = test.input('press', milliseconds=100)
            self.assertEqual(state['minigame']['phase'], 'running')
            left = state['minigame']['time_left_ms']
            state = test.input('tick', milliseconds=2000)
            # One 2000 ms tick would count as a single capped frame; in frames, the whole 2 s pass.
            self.assertLessEqual(state['minigame']['time_left_ms'], left - 1900)
        finally:
            debugger.close()

    def test_a_cell_out_of_range_or_a_value_on_a_button_game_is_refused(self):
        debugger, test = playtest('shs11_memory')
        try:
            test.run()
            self.assertIn('cell 0-8', test.input('press', value=9)['error'])
        finally:
            debugger.close()
        debugger, test = playtest('x360_diss')
        try:
            test.run()
            self.assertIn('no value', test.input('press', value=1)['error'])
        finally:
            debugger.close()

    def test_without_the_minigames_the_query_answers_no(self):
        debugger, test = playtest('x360_slot', minigames=False)
        try:
            state = test.run()
            self.assertEqual(state['variables']['real'], 0)
        finally:
            debugger.close()

    def test_the_switches_must_be_true_or_false(self):
        with self.assertRaises(ProjectError):
            DebugSession(project('x360_slot'), cutscenes=1)


@unittest.skipUnless(find_spec('PIL'), 'needs Pillow')
class Cutscenes(unittest.TestCase):
    def project(self):
        story = Project(title='Film', game='shs', start='q', nodes=[
            Node('q', 'cutscene_available', params={'result': 'real'}, next='c'),
            Node('end', 'end')])
        picture = story.add_image('Still', image_bytes())
        spec = blank_spec()
        spec.update(hold=3000, skip=1000, shots=[dict(blank_shot(0), image=picture.id, end=3000)])
        asset = save_cutscene(story, 'Film', spec)
        story.nodes[1:1] = [Node('c', 'cutscene', params={'spec': asset.id}, next='b'),
                            Node('b', 'dialogue', text='After.', next='end')]
        return story

    def test_it_stops_at_the_cutscene_and_skips_it(self):
        debugger = DebugSession(self.project(), seed=1)
        try:
            test = Playtest(debugger)
            state = test.run()
            self.assertEqual(state['action'], 'cutscene')
            self.assertEqual(state['minigame']['waits_for'], 'time or press')
            self.assertEqual(test.skip_options(), [dict(index=0, label='Skip', outcome=None)])
            test.input('skip')
            self.assertEqual(test.run()['text'], 'After.')
        finally:
            debugger.close()

    def test_watched_it_holds_for_a_press(self):
        debugger = DebugSession(self.project(), seed=1)
        try:
            test = Playtest(debugger)
            test.run()
            state = test.input('tick', milliseconds=5000)
            self.assertTrue(state['minigame']['held'])
            self.assertEqual(state['minigame']['waits_for'], 'press')
            test.input('press')
            self.assertEqual(test.run()['text'], 'After.')
        finally:
            debugger.close()

    def test_running_to_the_end_watches_it(self):
        debugger = DebugSession(self.project(), seed=1)
        try:
            self.assertEqual(Playtest(debugger).run(until='end')['stop_reason'], 'end')
        finally:
            debugger.close()

    def test_without_cutscenes_the_story_goes_on_without_it(self):
        debugger = DebugSession(self.project(), seed=1, cutscenes=False)
        try:
            state = Playtest(debugger).run()
            self.assertEqual(state['variables']['real'], 0)
        finally:
            debugger.close()


class Scenarios(unittest.TestCase):
    def test_a_scenario_skips_and_presses(self):
        debugger = DebugSession(project('shs11_memory'), seed=1)
        try:
            report = run_scenario(debugger, dict(steps=[dict(action='run'), dict(action='skip', value='Win'),
                                                         dict(action='run', until='end')],
                                                  assertions=[dict(kind='variable', name='memory_result', equals=2),
                                                              dict(kind='visited', node_id='won'), dict(kind='ended')]))
            self.assertTrue(report['passed'], report['failures'])
        finally:
            debugger.close()

    def test_a_scenario_takes_the_switches(self):
        debugger = DebugSession(project('x360_slot'), seed=1, minigames=False)
        try:
            report = run_scenario(debugger, dict(minigames=False, steps=[dict(action='run')],
                                                 assertions=[dict(kind='variable', name='real', equals=0)]))
            self.assertTrue(report['passed'], report['failures'])
        finally:
            debugger.close()


if __name__ == '__main__':
    unittest.main()
