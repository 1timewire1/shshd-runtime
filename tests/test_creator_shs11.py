"""SHS '11's Memory and Reflex as creator nodes: what they compile to, what they refuse, and that the player plays them."""
from copy import deepcopy
import struct
import unittest

from exp_runtime.creator.addons import mechanics
from exp_runtime.creator.compiler import compile_project
from exp_runtime.creator.features import DEFAULTS
from exp_runtime.creator.model import Node, Project, ProjectError
from exp_runtime.decode.bytecode import decode_program
from exp_runtime.exp import ExpArchive
from exp_runtime.shs11_services import SHS11_MEMORY, SHS11_REFLEX


def project(kind, params=None, game='shs'):
    return Project(title='Games', game=game, start='a', nodes=[
        Node('a', kind, params=params if params is not None else {}, next='b'),
        Node('b', 'end')])


def compiled(kind, params=None):
    exp = compile_project(project(kind, params))
    return decode_program(ExpArchive(exp).read(25001))


def host_calls(program):
    return [i.operand >> 8 if i.operand is not None else None for i in program.instructions if i.opcode == 0x1f]


class CreatorShs11(unittest.TestCase):
    def test_each_node_calls_its_service(self):
        self.assertIn(SHS11_MEMORY, host_calls(compiled('shs11_memory')))
        self.assertIn(SHS11_REFLEX, host_calls(compiled('shs11_reflex')))

    def test_a_word_must_fit_the_nine_tiles(self):
        for word in ('TOOLONGWORD', 'lower', 'TWO WORD', ''):
            params = deepcopy(DEFAULTS['shs11_memory'])
            params['rounds'][0]['word'] = word
            with self.assertRaises(ProjectError, msg=word):
                compiled('shs11_memory', params)

    def test_a_memory_round_needs_every_field(self):
        params = deepcopy(DEFAULTS['shs11_memory'])
        del params['rounds'][0]['bonus']
        with self.assertRaises(ProjectError):
            compiled('shs11_memory', params)

    def test_reflex_odds_are_out_of_100(self):
        params = deepcopy(DEFAULTS['shs11_reflex'])
        params['rounds'][0]['skulls'] = 60
        with self.assertRaises(ProjectError):
            compiled('shs11_reflex', params)

    def test_the_target_cannot_be_zero(self):
        for kind in ('shs11_memory', 'shs11_reflex'):
            params = deepcopy(DEFAULTS[kind])
            params['target'] = 0
            with self.assertRaises(ProjectError):
                compiled(kind, params)

    def test_cause_of_death_refuses_them(self):
        for kind in ('shs11_memory', 'shs11_reflex'):
            with self.assertRaises(ProjectError):
                compile_project(project(kind, game='cod'))

    def test_they_count_as_this_runtimes_mechanics(self):
        self.assertTrue(any('Memory' in name for name in mechanics(project('shs11_memory'))))
        self.assertTrue(any('Reflex' in name for name in mechanics(project('shs11_reflex'))))
        for service in (SHS11_MEMORY, SHS11_REFLEX):
            native = project('end')
            native.nodes.append(Node('n', 'native', params={'instructions': [[0x1a, 1], [0x1f, service << 8 | 5]]}))
            self.assertTrue(any("'11" in name for name in mechanics(native)), service)


class PlayedInTheEngine(unittest.TestCase):
    def session(self, kind, params=None):
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from exp_runtime.runtime import Session
        exp = compile_project(project(kind, params))
        archive = ExpArchive(exp)
        resources = SimpleNamespace(library=SimpleNamespace(game_id='shs', directory=Path(tempfile.gettempdir())),
                                    record={'titles': ['T'] * 5, 'id': 'x'}, identity=dict(profile='test', episode_sha256='0' * 64),
                                    program=archive.programs().__getitem__, linked_program=lambda: None,
                                    exists=lambda key: key in archive.entries, read_asset=archive.read)
        session = Session(resources, ephemeral=True)
        session.advance()
        return session

    def test_memory_opens_with_the_authored_rounds(self):
        session = self.session('shs11_memory')
        self.assertEqual(session.pending.name, 'shs11_memory')
        game = session.engine.shs11_memory
        self.assertEqual((game.target, game.total_ms), (200, 60000))
        self.assertEqual(game.rounds[0], ['A word for a small, mischievous helper.', 'ELF', 20, 10, 200, 2000])
        self.assertEqual(session.pending.details['right_character'], -1)

    def test_reflex_opens_with_the_authored_rounds(self):
        session = self.session('shs11_reflex')
        self.assertEqual(session.pending.name, 'shs11_reflex')
        game = session.engine.shs11_reflex
        self.assertEqual(game.rounds[0], [5, 10, 20, 5, 13, 3, 8, 25, 40, 20, 15, 300, 2100])

    def test_its_result_reaches_the_variable(self):
        session = self.session('shs11_memory')
        session._complete_minigame(result=2)
        self.assertNotEqual(session.pending and session.pending.name, 'shs11_memory')


if __name__ == '__main__':
    unittest.main()
