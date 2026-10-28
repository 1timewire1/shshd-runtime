import copy
import json
from pathlib import Path
import unittest

from exp_runtime.content import ContentLibrary
from exp_runtime.randomness import Random48
from exp_runtime.runtime import SaveError, Session
from exp_runtime.vm import VMError
from test_runtime import Resources, answer_screen, host_call, text_words
from test_vm import program


def word_resources(duration=20000, good='yes|right', bad='no|wrong|bad'):
    words, refs = text_words('Snacks!', 'Pick the right word', good, bad)
    return Resources(program(*host_call(71, *refs, duration, -1, 1, 3000),
                             0x21, (0x1f, 0xfe01), words=words))


class WordGameTests(unittest.TestCase):
    def test_libc_random_vectors_and_native_first_deal(self):
        random = Random48()
        # Compared with libc seed48({0x330e,0xabcd,0x1234}) / lrand48.
        self.assertEqual([random.next() for _ in range(8)],
                         [851401618, 1804928587, 758783491, 959030623,
                          684387517, 1903590565, 33463914, 1254324197])
        s = Session(word_resources())
        a = s.advance()
        self.assertEqual(a.name, 'word_game')
        self.assertEqual(a.details['title'], 'Snacks!')
        self.assertEqual(s.engine.word_game.options, ['no', 'wrong', 'bad', 'yes'])
        self.assertEqual(s.engine.word_game.weights, [-1, -1, -1, 1])
        self.assertEqual(s.engine.random48.state, 0x5e37dc5a3f85)

    def test_translated_new_rules_quiz_plays_its_own_jingles_when_the_episode_has_them(self):
        # shs profile TRANSLATED_WORD_GAME_SOUNDS: pack 31300 -> New Rules' right/wrong jingles at 26980 + 13 / + 1
        right, wrong = 26980 + 13, 26980 + 1
        for pack, present, expected in ((None, {right, wrong}, (8001, 8002)), (31300, set(), (8001, 8002)),
                                        (31300, {right}, (8001, 8002)), (31300, {right, wrong}, (right, wrong))):
            resources = word_resources()
            resources.record['pack_id'] = pack
            resources.exists = present.__contains__
            s = Session(resources)
            s.advance()
            s.tick(400)
            game = s.engine.word_game
            s.answer(game.weights.index(1))
            heard = [s.engine.sound_id]
            s.answer(game.weights.index(-1))
            heard.append(s.engine.sound_id)
            self.assertEqual(tuple(heard), expected, pack)

    def test_score_clamp_entry_gate_and_actual_vm_callback(self):
        s = Session(word_resources())
        a = s.advance()
        held = s.vm.snapshot()
        before = s.snapshot()
        s.answer(3)  # Native 400 ms transition gate discards early taps.
        self.assertEqual(before, s.snapshot())
        for value in [None, True, -1, 4, '1']:
            with self.assertRaises(ValueError): s.answer(value)
        s.tick(400)
        game = s.engine.word_game
        s.answer(game.weights.index(-1))
        self.assertEqual(game.score, 0)
        self.assertEqual(s.engine.sound_id, 8002)
        for _ in range(3):
            s.answer(game.weights.index(1))
        s.answer(game.weights.index(-1))
        self.assertEqual(game.score, 2)
        self.assertEqual(s.vm.snapshot(), held)
        self.assertIsNone(s.engine.result_cells[0])
        s.tick(game.remaining_ms)
        self.assertIs(s.pending, a)  # Native expiry is < 0, not <= 0.
        result = s.tick(1)
        self.assertEqual(result.request.args, (2,))
        self.assertEqual(s.engine.result_cells[0], 2)
        self.assertIsNone(s.engine.word_game)

    def test_cause_of_death_quiz_uses_the_ios_pacing_and_its_own_sounds(self):
        r = word_resources(); r.library.game_id = 'cod'
        s = Session(r); s.advance()
        game = s.engine.word_game
        self.assertTrue(game.hd)
        s.answer(game.weights.index(1)); s.tick(150)   # the score lands after the 0.1 s selection
        self.assertEqual(s.engine.sound_id, 8003)
        for _ in range(100):                           # the fly-off and fly-on, in frames, then input reopens
            s.tick(20)
        s.answer(s.engine.word_game.weights.index(-1)); s.tick(150)
        self.assertEqual(s.engine.sound_id, 8004)
        plain = Session(word_resources()); plain.advance()
        self.assertFalse(plain.engine.word_game.hd)    # SHS without the HD bundle keeps Android's pacing

    def test_save_preserves_deal_clock_score_random_and_future_deals(self):
        resources = word_resources()
        s = Session(resources); s.advance(); s.tick(1000)
        s.answer(s.engine.word_game.weights.index(1)); s.tick(50)
        saved = json.loads(json.dumps(s.snapshot()))
        restored = Session.from_snapshot(resources, saved)
        self.assertEqual(restored.snapshot(), s.snapshot())
        for _ in range(12):
            s.answer(0); restored.answer(0)
            s.tick(33); restored.tick(33)
            self.assertEqual(s.snapshot(), restored.snapshot())
        # The native per-deal refresh counter expires without a redeal.
        before = restored.engine.word_game.options[:]
        restored.tick(4000)
        self.assertEqual(before, restored.engine.word_game.options)
        for path, value in [(('engine', 'random48', 'state'), -1),
                            (('engine', 'word_game', 'score'), -1),
                            (('engine', 'word_game', 'remaining_ms'), 30000),
                            (('engine', 'word_game', 'weights'), [1]*4),
                            (('engine', 'word_game', 'options'), ['forged']*4),
                            (('engine', 'word_game'), None),
                            (('pending', 'name'), 'unhandled_yield')]:
            invalid = copy.deepcopy(saved); target = invalid
            for key in path[:-1]: target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(SaveError):
                Session.from_snapshot(resources, invalid)

    def test_invalid_lists_do_not_consume_random_or_resume_vm(self):
        for good, bad, duration in [('one', 'a|b|c', 1000), ('a|b', 'one', 1000),
                                     ('a|b', 'x|y|z', 0)]:
            s = Session(word_resources(duration, good, bad)); rng = s.engine.random48.state
            self.assertEqual(s.advance().name, 'unhandled_yield')
            self.assertEqual(s.engine.random48.state, rng)
            held = s.snapshot()
            with self.assertRaises(VMError): s.answer(1)
            s.tick(5000)
            self.assertEqual(held, s.snapshot())

    def test_old_blocked_save_enters_game_without_replaying_instructions(self):
        r = word_resources(); s = Session(r); s.advance()
        old = s.snapshot(); old['version'] = 2
        old['engine'].pop('word_game'); old['engine'].pop('random48')
        old['pending'] = dict(name='unhandled_yield', details={})
        restored = Session.from_snapshot(r, old)
        self.assertEqual(restored.vm.snapshot(), s.vm.snapshot())
        self.assertEqual(restored.pending.name, 'word_game')
        self.assertEqual(restored.engine.word_game.options, s.engine.word_game.options)

    @unittest.skipUnless(Path('.shs-library/library.json').exists(), 'user library absent')
    def test_new_girl_success_and_failure_use_original_branches(self):
        with ContentLibrary(Path('.shs-library')) as lib:
            r = lib.open_episode('The_New_Girl.exp'); s = Session(r); s.advance()
            for _ in range(100):
                if s.pending.name == 'word_game': break
                answer_screen(s, 0 if s.pending.name == 'choice' else None)
            self.assertEqual(s.pending.details['text'], 'Try to catch Sam!')
            saved = s.snapshot(); results = []
            for score in (0, 10):
                branch = Session.from_snapshot(r, saved); branch.tick(400)
                for _ in range(score):
                    branch.answer(branch.engine.word_game.weights.index(1)); branch.tick(500)
                branch.tick(branch.engine.word_game.remaining_ms + 1)
                results.append((branch.pending.request.pc, branch.pending.details['text']))
                self.assertEqual(branch.engine.result_cells[0], score)
            self.assertNotEqual(results[0], results[1])
