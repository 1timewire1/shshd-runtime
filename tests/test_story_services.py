import copy
import unittest

from exp_runtime.engine import EngineState
from exp_runtime.randomness import NativeRandom
from exp_runtime.runtime import Session
from exp_runtime.vm import KiwiVM, VMError
from test_runtime import Resources, answer_screen, host_call, text_words
from test_vm import program


def invoke(engine, service, *args, words=(), gap=0):
    vm = KiwiVM(program(*host_call(service, *args), 0x21, (0x1f, 0xfe01), words=words, gap=gap))
    vm.run()
    return vm, engine.dispatch(vm)


class StoryServiceTests(unittest.TestCase):
    def test_format_slots_types_literal_percents_and_aliased_scratch(self):
        engine = EngineState()
        words, refs = text_words('%c/%d/%s %% %q %', 'Hi')
        vm, _ = invoke(engine, 0, -8, refs[0], 0x1ff, -17, refs[1], words=words)
        self.assertEqual(vm.run().args, (0x7ffe,))
        self.assertEqual(engine.dynamic_strings[9], 'ÿ/-17/Hi %% %q %')
        self.assertEqual(engine.dynamic_strings[10], engine.dynamic_strings[9])
        engine.dynamic_strings[10] = 'A%sB'
        vm, _ = invoke(engine, 0, 0x7fff, 0x7fff)
        self.assertEqual(engine.dynamic_strings[0], 'AAB')
        self.assertEqual(vm.run().args, (0x7ff5,))
        words, refs = text_words('')
        invoke(engine, 0, refs[0], words=words)
        self.assertEqual(engine.dynamic_strings[0], '')
        with self.assertRaises(VMError):
            invoke(engine, 0, -10, 0, words=words)

    def test_packed_name_copy_padding_append_and_invalid_extent(self):
        for text, expected in (('', [0]), ('A', [0x4100]), ('AB', [0x4142, 0]), ('Zoé', [0x5a6f, 0xe900])):
            engine = EngineState(last_input=text)
            vm, _ = invoke(engine, 28, 0, words=(0xffff,) * 5)
            self.assertEqual([vm.read_word(i) & 0xffff for i in range(len(expected))], expected)
            self.assertEqual(vm.read_word(len(expected)), -1)
            self.assertEqual(engine.read_text(vm, 0), text)
        engine = EngineState(last_input='ABC')
        vm = KiwiVM(program(*host_call(28, 0), words=(0x1234,)))
        vm.run(); before = vm.snapshot()
        with self.assertRaises(VMError):
            engine.dispatch(vm)
        self.assertEqual(vm.snapshot(), before)
        words, refs = text_words('AB', 'CD')
        vm, _ = invoke(engine, 25, refs[0], refs[1], words=words, gap=4)
        self.assertEqual(engine.read_text(vm, 0), 'ABCD')  # Both sources copied before overlap.
        words, refs = text_words('same', 'same', 'different')
        for index, result in ((1, 1), (2, 0)):
            vm, _ = invoke(engine, 24, refs[0], refs[index], words=words)
            self.assertEqual(vm.run().args, (result,))

    def test_bit_services_share_32_bit_numbers_and_use_arm_shift_rules(self):
        e = EngineState()
        invoke(e, 50, 1, -1, 31, 1)
        self.assertEqual(e.numbers[65535], -2147483648)
        for bit, expected in ((31, 1), (32, 1), (-1, 1), (0, 0)):
            vm, _ = invoke(e, 51, 1, -1, bit)
            self.assertEqual(vm.run().args, (expected,))
        invoke(e, 50, 1, -1, 0, 1)
        vm, _ = invoke(e, 53, 1, -1)
        self.assertEqual(vm.run().args, (1,))  # Numeric read narrows to a word.
        invoke(e, 50, 1, -1, 31, 2)  # Exactly one sets; all other values clear.
        self.assertEqual(e.numbers[65535], 1)
        invoke(e, 50, 1, -1, 32, 1)
        self.assertEqual(e.numbers[65535], 1)

    def test_random_service_shares_saved_native_stream_and_nonpositive_is_zero(self):
        e = EngineState(random=NativeRandom(123))
        expected = NativeRandom(123)
        for bound in (0, -3, 15, 7, 30000):
            vm, _ = invoke(e, 27, bound)
            self.assertEqual(vm.run().args, (expected.below(bound) if bound > 0 else 0,))
            self.assertEqual(e.random.state, expected.state)
        before = copy.deepcopy(e)
        for service, args in ((82, ()), (99, (0,)), (99, (1,))):
            vm, action = invoke(e, service, *args)
            self.assertTrue(action.completed)
            self.assertEqual(vm.run().args, (0,))
            self.assertEqual(e, before)  # No vibration hardware; service 99 is a native stub.
        self.assertEqual(e.vibration_serial, 1)

    def test_scene_badge_and_one_shot_dialogue_wobble_survive_save(self):
        words, refs = text_words('Before School', 'Hello', 'Again')
        r = Resources(program(*host_call(90, 3121, refs[0]), *host_call(89),
                              *host_call(13, refs[1], 0), *host_call(90, -1, -1),
                              *host_call(13, refs[2], 0), 0x33, words=words))
        s = Session(r)
        self.assertEqual(s.advance().name, 'dialogue')
        self.assertEqual(s.engine.scene_badge.text, 'Before School')
        self.assertEqual(s.engine.dialogue_animation.box_alpha, 0)
        self.assertFalse(s.engine.next_dialogue_wobble)
        s.tick(825)  # Native 700ms hold, then the middle of the 250ms shake.
        self.assertEqual(s.engine.dialogue_animation.box_rotation, 0)
        restored = Session.from_snapshot(r, s.snapshot())
        self.assertEqual(restored.snapshot(), s.snapshot())
        restored.tick(125)
        self.assertEqual(restored.engine.scene_badge.elapsed_ms, 200)
        self.assertEqual(restored.engine.dialogue_animation.box_rotation, 0)
        answer_screen(restored)
        self.assertEqual(restored.pending.details['text'], 'Again')
        self.assertEqual(restored.engine.dialogue_animation.wobble_direction, 0)
        self.assertIsNone(restored.engine.scene_badge)
