import copy
import unittest

from exp_runtime.process import RuntimeProcess
from exp_runtime.randomness import NativeRandom
from exp_runtime.runtime import Session
from exp_runtime.speaker_names import NameFontState
from test_runtime import Resources
from test_vm import program


def session(game='shs'):
    resources = Resources(program(0x33))
    resources.library.game_id = game
    return Session(resources)


class RuntimeProcessTests(unittest.TestCase):
    def test_episode_teardown_retains_streams_and_fonts_but_not_panels(self):
        for game in ('shs', 'cod'):
            with self.subTest(game=game):
                process = RuntimeProcess()
                first = process.attach(session(game))
                first.engine.random = NativeRandom(17)
                first.engine.random.next()
                first.engine.random48.next()
                first.engine.speaker_names.fonts['PajamaHip26'] = NameFontState(width=235, gap=8)
                first.engine.speaker_names.basis = {}
                first.engine.text_history.previous_glyph = ord('z')
                first.engine.text_history.labels['dialogue_name'] = ord('a')
                if game == 'cod' and first.engine.scene_transition is not None:   # unset in this fork
                    first.engine.scene_transition.start(20, 0)
                saved = copy.deepcopy(first.engine)
                second = process.attach(session(game))
                self.assertEqual(second.engine.random.next(), saved.random.next())
                self.assertEqual(second.engine.random48.next(), saved.random48.next())
                self.assertEqual(second.engine.speaker_names.fonts, saved.speaker_names.fonts)
                self.assertIsNone(second.engine.speaker_names.basis)
                self.assertEqual(second.engine.text_history, saved.text_history)
                self.assertFalse(second.transitioning)
                if game == 'cod' and second.engine.scene_transition is not None:
                    self.assertEqual(second.engine.scene_transition.random_state, 16807)
                self.assertIs(second.process, process)

    def test_explicit_restore_replaces_process_state_and_other_games_stay_isolated(self):
        process = RuntimeProcess()
        first = process.attach(session())
        saved = first.snapshot()
        first.engine.random.next()
        restored = Session.from_snapshot(first.resources, saved)
        process.attach(restored, restored=True)
        next_episode = process.attach(session())
        self.assertEqual(next_episode.engine.random.state, saved['engine']['random']['state'])
        with self.assertRaises(ValueError):
            process.attach(session('cod'))
        self.assertIs(process.current, next_episode)
        separate = RuntimeProcess().attach(session('cod'))
        self.assertIsNot(separate.engine.random, next_episode.engine.random)
