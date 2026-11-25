"""Round Style and Secret in the Shadows' rounds in a story (Claire Hart plan S3 step 5; claire_round_style.py): service 226
opens a sequel round (keys from 20000) under the sequel's rules, either game's round plays under the other's rules by the
setting, a style whose screen's add-on is gone falls back to each game's own, the session takes the sequel's moves (the
sensor, the close-up, its backing), a save mid-round comes back exactly (version 48), an older save's Classic round gains
its source, and the Creator puts a sequel round behind its own question (208)."""
import json
import unittest

from exp_runtime import shadows_rounds as sr
from exp_runtime.claire_round_services import CLAIRE_ROUND, SHADOWS_KEY_BASE, is_shadows_key, shadows_key
from exp_runtime.claire_round_style import RoundData, open_round
from exp_runtime.claire_rounds import ClaireRound
from exp_runtime.randomness import Random48
from exp_runtime.runtime import Session
from test_runtime import Resources, host_call, text_words
from test_vm import program

NAMES = [f'Thing {i}' for i in range(30)]
# A sequel scene: 24 ordinary objects, three close-up ones, a multi-part object (two parts and its whole) and the Gold Key
KINDS = [sr.ORDINARY] * 24 + [sr.CLOSE_UP] * 3 + [sr.PART, sr.PART, sr.WHOLE]
KINDS[5] = sr.GOLD_KEY
SEQUEL = RoundData('ch2rounds', 'ClairesBedroom_HO', NAMES, [29], "Claire's Bedroom", KINDS, {29: [27, 28]})
KEY = shadows_key(1, 1, 3)


def classic(key):
    return ('Office', NAMES, [4], "Claire's Office") if key == 183 else None


def sequel(key):
    return SEQUEL if key == KEY else None


def story(key):
    words, (ann, line) = text_words('Ann', 'Found it.')
    return Resources(program(*host_call(CLAIRE_ROUND, key), *host_call(15, ann, line), 0x33, words=words))


def opened(key, source, style='own', classic_ready=True, sequel_ready=True):
    session = Session(story(key))
    session.engine.claire_round_source = source
    session.engine.claire_round_style = style
    session.engine.claire_rounds_ready, session.engine.claire2_rounds_ready = classic_ready, sequel_ready
    session.advance()
    return session


class RoundStyleTests(unittest.TestCase):
    def test_a_sequel_key_is_a_signed_word_clear_of_classics(self):
        self.assertEqual(KEY, 20113)
        self.assertTrue(is_shadows_key(KEY) and not is_shadows_key(2665))
        self.assertLessEqual(shadows_key(107, 9, 9), 32767)
        self.assertEqual(SHADOWS_KEY_BASE, 20000)

    def test_each_games_own_rules(self):
        game = open_round(SEQUEL, Random48(1), 'once')
        self.assertIsInstance(game, sr.ShadowsRound)
        self.assertEqual((game.source, game.picked[0], game.key), ('ch2rounds', 29, 5))     # (its multi-part object first)
        game = open_round(classic(183), Random48(1), 'once')
        self.assertIsInstance(game, ClaireRound)
        self.assertEqual((game.source, game.picked[0]), ('chcrounds', 4))

    def test_a_sequel_scene_under_classics_rules_picks_its_ordinary_objects(self):
        game = open_round(SEQUEL, Random48(1), 'once', 'classic')
        self.assertIsInstance(game, ClaireRound)
        self.assertEqual(game.source, 'ch2rounds')
        self.assertTrue(all(KINDS[o] == sr.ORDINARY for o in game.picked))
        self.assertNotIn(29, game.picked)                   # (its multi-part object can't be shown there)

    def test_a_classic_scene_under_the_sequels_rules_has_no_extras(self):
        game = open_round(classic(183), Random48(1), 'once', 'shadows')
        self.assertIsInstance(game, sr.ShadowsRound)
        self.assertEqual((game.source, game.key, game.picked[0]), ('chcrounds', sr.NO_OBJECT, 4))
        self.assertEqual(set(game.kinds), {sr.ORDINARY})

    def test_service_226_opens_a_sequel_round_and_a_missing_style_falls_back(self):
        session = opened(KEY, sequel)
        self.assertEqual(session.pending.name, 'claire_round')
        self.assertIsInstance(session.engine.claire_round, sr.ShadowsRound)
        self.assertIsInstance(opened(KEY, sequel, 'classic').engine.claire_round, ClaireRound)
        fallback = opened(KEY, sequel, 'classic', classic_ready=False)      # (Classic's screen's add-on is gone)
        self.assertIsInstance(fallback.engine.claire_round, sr.ShadowsRound)
        self.assertIsInstance(opened(183, classic, 'shadows', sequel_ready=False).engine.claire_round, ClaireRound)

    def test_the_sequels_moves_a_save_and_on_with_the_story(self):
        session = opened(KEY, sequel)
        game = session.engine.claire_round
        self.assertTrue(session.claire_use('sensor'))
        self.assertTrue(game.sensor_on)
        self.assertTrue(session.claire_use('open_pip'))
        session.claire_backing()
        self.assertEqual(game.misclicks, 0)                 # (the backing feeds the spam check, no misclick)
        self.assertTrue(session.claire_use('close_pip'))
        self.assertEqual(session.claire_tap([5]), 5)       # the Gold Key
        with self.assertRaises(ValueError):
            session.claire_use('focus')                     # (Classic's, not the sequel's)
        session.tick(500)
        state = json.loads(json.dumps(session.snapshot()))
        self.assertEqual(state['version'], 48)
        restored = Session.from_snapshot(story(KEY), state)
        self.assertEqual(restored.engine.claire_round, game)        # exactly where it was (R3)
        game = restored.engine.claire_round
        game.open_pip()
        while not game.over:
            target = next((o for o in game.listed if o not in game.found), None)
            if target is not None:
                for obj in game.parts.get(target, [target]):
                    restored.claire_tap([obj])
            restored.tick(sr.FOUND_MS + sr.NAME_GAP_MS)
        restored.claire_continue()
        while restored.pending is None or restored.pending.name != 'dialogue':
            restored.advance()
        self.assertEqual(restored.pending.details['raw_text'], 'Found it.')

    def test_an_older_saves_classic_round_gains_its_source(self):
        session = opened(183, classic)
        state = json.loads(json.dumps(session.snapshot()))
        state['version'] = 47
        del state['engine']['claire_round']['source']
        restored = Session.from_snapshot(story(183), state)
        self.assertEqual(restored.engine.claire_round.source, 'chcrounds')


class CreatorTests(unittest.TestCase):
    def project(self, key, asks):
        from exp_runtime.creator.model import Node, Project
        return Project(title='Rounds', game='cod', start='q', nodes=[
            Node('q', 'minigames_available', params={'for': asks, 'result': 'real'}, next='a'),
            Node('a', 'claire_round', params=dict(round=key), next='b'), Node('b', 'end')])

    def test_a_sequel_round_asks_its_own_question(self):
        from exp_runtime.creator.compiler import compile_project
        from exp_runtime.creator.model import ProjectError
        from exp_runtime.decode.bytecode import decode_program
        from exp_runtime.exp import ExpArchive
        code = decode_program(ExpArchive(compile_project(self.project(KEY, 'claire2_round'))).read(25001))
        pushed = [i.operand for i in code.instructions if i.opcode == 0x1a]
        self.assertIn(208, pushed)
        self.assertIn(KEY, pushed)
        with self.assertRaisesRegex(ProjectError, "Secret in the Shadows' rounds"):
            compile_project(self.project(KEY, 'claire_round'))      # (Classic's question doesn't say ch2rounds is there)


if __name__ == '__main__':
    unittest.main()
