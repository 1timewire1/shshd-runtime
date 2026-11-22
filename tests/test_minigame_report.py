"""shshd-runtime: the open mini-game as a player reads it (exp_runtime.minigame_report, shared by the Creator's playtests and
the app's test channel), and the channel's `play` command (owner, 2026-11-21)."""
import importlib.util
from types import SimpleNamespace
import unittest
from unittest import mock

from exp_runtime.minigame_report import claire_round, describe

try:                                    # (Claire Hart's rounds: the claire-hart branch's; master has none to report)
    from exp_runtime import claire_rounds as cr
    from test_claire_rounds import a_round, find_next
    HAS_ROUNDS = True
except ImportError:
    HAS_ROUNDS = False

HAS_PYGAME = importlib.util.find_spec('pygame') is not None


@unittest.skipUnless(HAS_ROUNDS, "Claire Hart's rounds are not in this build")
class ClaireRoundReportTests(unittest.TestCase):
    def test_it_lists_the_names_with_their_objects_and_follows_the_round(self):
        game = a_round(seed=3)
        report = claire_round(game)
        self.assertEqual((report['kind'], report['found'], report['to_find'], len(report['listed'])),
                         ('claire_round', 0, cr.SOL_SIZE, cr.AOL_SIZE))
        first = report['listed'][0]
        self.assertEqual((first['name'], first['found']), (game.names[first['object']], False))
        self.assertEqual(report['waits_for'], 'taps on the listed objects')
        self.assertTrue(report['hint']['ready'])
        self.assertEqual(report['powerups']['locator'], dict(left=1, usable=True))
        game.started = False
        self.assertEqual(claire_round(game, skippable=True)['waits_for'], 'skip prompt or go-ahead')
        found = find_next(game)
        self.assertEqual(claire_round(game)['found'], 1)
        self.assertNotIn(found, [item['object'] for item in claire_round(game)['listed'] if not item['found']])
        game.locate()
        self.assertEqual(claire_round(game)['waits_for'], 'a listed name (the Psychic Locator)')
        game.pick_located(0)
        while not game.over:
            find_next(game)
        self.assertEqual(claire_round(game)['waits_for'], 'continue')

    def test_describe_reads_the_pending_game_only(self):
        game = a_round()
        engine = SimpleNamespace(nr_arena=None, claire_round=game)
        session = SimpleNamespace(engine=engine, pending=SimpleNamespace(name='claire_round'))
        self.assertEqual(describe(session)['scene'], 'ClairesOffice')
        session.pending = SimpleNamespace(name='dialogue')
        self.assertIsNone(describe(session))
        session.pending = None
        self.assertIsNone(describe(session))


@unittest.skipUnless(HAS_PYGAME, 'the desktop extra is unavailable')
class ChannelPlayTests(unittest.TestCase):
    def setUp(self):
        from exp_runtime import test_channel
        self.module = test_channel

    def channel(self, name, *, prompt=None, ready=True):
        answers, commands = [], []
        session = SimpleNamespace(pending=SimpleNamespace(name=name), answer=answers.append, engine=SimpleNamespace())
        game = SimpleNamespace(session=session, host_prompt=prompt, command=commands.append, fade=None,
                               _attempt=lambda act: act(), _claire_ready=lambda: ready, error=None)
        session.transitioning = False
        channel = self.module.Commands(None, SimpleNamespace(screen='game', game=game, shell=None))
        return channel, answers, commands

    @staticmethod
    def finish(job):
        if not hasattr(job, '__next__'):
            return job
        try:
            while True:
                next(job)
        except StopIteration as stop:
            return stop.value

    def play(self, channel, words):
        with mock.patch.object(channel, 'do_state', lambda *_: dict(ok=True)):
            return self.finish(channel.do_play(words))

    def test_press_goes_through_the_desktops_own_calls(self):
        channel, answers, commands = self.channel('shs11_memory')
        self.assertTrue(self.play(channel, 'press 4')['ok'])
        self.assertTrue(self.play(channel, 'press')['ok'])
        self.assertEqual(answers, [4, None])
        self.assertFalse(self.play(channel, 'press 9')['ok'])
        channel, answers, commands = self.channel('arena_frame')
        self.play(channel, 'press -5')
        self.assertEqual(commands, [('arena_key', -5)])
        self.assertFalse(self.play(channel, 'press')['ok'])             # (the arena wants a key code)
        channel, answers, _ = self.channel('x360_slot')
        self.play(channel, 'press')
        self.assertEqual(answers, [None])

    def test_football_the_word_game_and_the_grid_take_their_own_input(self):
        channel, answers, commands = self.channel('football')
        self.play(channel, 'press')
        self.play(channel, 'press 4')
        self.assertEqual(answers, [None, 4])
        self.assertFalse(self.play(channel, 'press 9')['ok'])
        channel, answers, commands = self.channel('word_game')
        channel.app.game.session.engine.word_game = SimpleNamespace(options=['cat', 'dog'])
        self.play(channel, 'press 1')
        self.assertEqual(commands, [('choose', 1)])
        self.assertFalse(self.play(channel, 'press 2')['ok'])
        channel, _, _ = self.channel('word_grid')
        moves = []
        channel.app.game.session.grid_pointer = lambda phase, cell: moves.append((phase, cell))
        self.play(channel, 'cells 0 1 5')
        self.assertEqual(moves, [('down', 0), ('move', 1), ('move', 5), ('up', 5)])
        moves.clear()
        self.play(channel, 'press')
        self.assertEqual(moves, [('down', None), ('up', None)])

    def test_it_refuses_what_a_player_couldnt_do(self):
        channel, _, _ = self.channel('x360_slot', prompt=dict(options=['Win', 'Lose', 'Play']))
        self.assertIn('skip prompt', self.play(channel, 'press')['error'])
        channel, _, _ = self.channel('dialogue')
        self.assertIn('no mini-game', self.play(channel, 'press')['error'])
        self.assertIn('Claire Hart', self.play(channel, 'find Apple')['error'])
        channel, _, _ = self.channel('claire_round', ready=False)
        self.assertIn('not ready', self.play(channel, 'find Apple')['error'])

    @unittest.skipUnless(HAS_ROUNDS, "Claire Hart's rounds are not in this build")
    def test_a_round_finds_only_a_listed_name(self):
        channel, _, _ = self.channel('claire_round')
        game = a_round(seed=5)
        channel.app.game.session.engine.claire_round = game
        channel.app.game.claire_round_renderer = SimpleNamespace()
        error = self.play(channel, 'find Not Listed')['error']
        self.assertIn('not listed', error)
        self.assertIn(game.names[game.listed[0]], error)                 # (it says what is)
        self.assertIn('still being played', self.play(channel, 'continue')['error'])


if __name__ == '__main__':
    unittest.main()
