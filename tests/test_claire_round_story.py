"""Claire Hart's round in a story (Claire Hart plan Stage 3, step 4): service 226 opens round `key` from the session's round
source (chcrounds), the session takes its moves, a save mid-round comes back exactly (R3, save version 44), Skip goes on,
and the story goes on after the Level Summary's Continue."""
import json
import unittest

from exp_runtime import claire_rounds as cr
from exp_runtime.claire_round_services import CLAIRE_ROUND, round_key, round_of
from exp_runtime.runtime import Session
from test_runtime import Resources, host_call, text_words
from test_vm import program

NAMES = [f'Thing {i}' for i in range(30)]


def source(key):
    return ('Office', NAMES, [4], "Claire's Office") if key == 183 else None


def story():
    words, (ann, line) = text_words('Ann', 'Found it.')
    return Resources(program(*host_call(CLAIRE_ROUND, 183), *host_call(15, ann, line), 0x33, words=words))


def opened():
    session = Session(story())
    session.engine.claire_round_source = source
    session.advance()
    return session


class RoundStoryTests(unittest.TestCase):
    def test_a_round_key_is_its_episode_and_number(self):
        self.assertEqual(round_key('E018', 3), 183)
        self.assertEqual(round_of(183), ('E018', 3))

    def test_service_226_opens_the_round_with_its_story_object_first(self):
        session = opened()
        self.assertEqual(session.pending.name, 'claire_round')
        game = session.engine.claire_round
        self.assertEqual((game.scene, game.title, game.picked[0]), ('Office', "Claire's Office", 4))
        self.assertTrue(session.minigame_unstarted)

    def test_a_round_the_add_on_lacks_stops_plainly(self):
        session = Session(story())
        session.engine.claire_round_source = lambda key: None
        self.assertEqual(session.advance().name, 'unhandled_yield')

    def test_played_saved_resumed_and_on_with_the_story(self):
        session = opened()
        first = session.engine.claire_round.listed[0]
        self.assertEqual(session.claire_tap([first]), first)
        self.assertTrue(session.claire_use('hint'))
        session.tick(500)
        state = json.loads(json.dumps(session.snapshot()))
        self.assertEqual(state['version'], 47)
        restored = Session.from_snapshot(story(), state)
        restored.engine.claire_round_source = source
        self.assertEqual(restored.engine.claire_round, session.engine.claire_round)      # exactly where it was (R3)
        game = restored.engine.claire_round
        while not game.over:
            target = next((o for o in game.listed if o not in game.found), None)
            if target is not None:
                restored.claire_tap([target])
            restored.tick(cr.FOUND_MS + cr.NAME_HIDE_MS)       # (the last names leave before the round ends)
        with self.assertRaises(ValueError):
            restored.claire_use('nonsense')
        restored.claire_continue()
        while restored.pending is None or restored.pending.name != 'dialogue':
            restored.advance()
        self.assertEqual(restored.pending.details['raw_text'], 'Found it.')

    def test_skipping_goes_on(self):
        session = opened()
        session.skip_minigame(True)
        while session.pending is None or session.pending.name != 'dialogue':
            session.advance()
        self.assertEqual(session.pending.details['raw_text'], 'Found it.')


if __name__ == '__main__':
    unittest.main()
