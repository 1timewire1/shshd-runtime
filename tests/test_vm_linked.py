"""shshd-runtime: a script running beside a linked segment (VM_SPEC.md §2.3), as New Rules runs its stories beside
its minigame library 25200."""
import struct
import unittest

from exp_runtime.decode.bytecode import OPERAND_OPCODES, decode_program
from exp_runtime.vm import KiwiVM, StopKind, VMError, linked_layout
from test_vm import program


def linked(*instructions, words=(), data_boundary, code_boundary):
    """A segment whose header sets previous_flag, its data at `data_boundary` and its PCs from `code_boundary`."""
    code = bytearray()
    for item in instructions:
        op, arg = item if isinstance(item, tuple) else (item, None)
        code.append(op)
        if op in OPERAND_OPCODES:
            code.extend(struct.pack('>H', arg & 0xFFFF))
    header = (b'kiwi\x02\x01' + struct.pack('>HH', data_boundary, code_boundary) + b'\x00'
              + struct.pack('>4H', len(words), 0, 0, len(instructions)))
    return decode_program(header + struct.pack(f'>{len(words)}H', *words) + code)


# The library at PC 100 adds its data word 50 (7) to the story's word 0 (5) and keeps the sum in its word 51.
LIBRARY = linked((0x1A, 51), (0x40, 50), (0x40, 0), 0x50, 0x3E, 0x15, 0x43,
                 words=(7, 0), data_boundary=50, code_boundary=100)
# The story calls it (SAVE_RET, JMP_ABS 100), then reads the sum and shows it (service 13).
STORY = program(0x42, (0x29, 100), (0x40, 51), (0x1F, 0x0D01), 0x33, words=(5,))


class LinkedSegmentTests(unittest.TestCase):
    def test_a_story_calls_into_its_linked_segment_and_both_data_banks_are_addressable(self):
        vm = KiwiVM(STORY, **linked_layout(LIBRARY))
        stop = vm.run()
        self.assertEqual((stop.yield_id, stop.args), (13, (12,)))
        self.assertEqual(vm.linked_data, [7, 12])
        self.assertEqual(vm.instruction_at(104).opcode, 0x3E)          # an absolute PC in the segment
        self.assertEqual(vm.read_word(51), 12)

    def test_the_segment_and_its_data_survive_a_save_and_the_next_scene(self):
        vm = KiwiVM(STORY, **linked_layout(LIBRARY))
        vm.run()
        state = vm.snapshot()
        self.assertEqual(state['linked_data'], [7, 12])
        restored = KiwiVM.from_snapshot(STORY, state, linked=LIBRARY)
        restored.resume(0)
        self.assertEqual(restored.run().kind, StopKind.HALT)
        restored.load_next(program((0x40, 51), (0x1F, 0x0D01), 0x33))   # the next scene still sees the library
        self.assertEqual(restored.run().args, (12,))
        with self.assertRaises(VMError):
            KiwiVM.from_snapshot(STORY, state)                          # without its segment: a different machine

    def test_a_plain_save_keeps_its_shape(self):
        self.assertNotIn('linked_data', KiwiVM(STORY).snapshot())

    def test_the_stack_fits_above_the_segment_as_new_rules_places_it(self):
        self.assertEqual(linked_layout(LIBRARY)['stack_capacity'], 0x400)
        # New Rules' library: data from 29396, 3,105 words, ending at 32501 = 0x7FF5 - 256 (its engine's stack).
        library = linked(0x43, words=(0,) * 3105, data_boundary=29396, code_boundary=26942)
        self.assertEqual(linked_layout(library)['stack_capacity'], 256)
        self.assertEqual(linked_layout(None), {})

    def test_overlaps_are_refused(self):
        with self.assertRaisesRegex(VMError, 'beside a primary script'):
            KiwiVM(LIBRARY)
        too_long = program(*([0] * 101), 0x33)
        with self.assertRaisesRegex(VMError, "overlaps its linked segment's code"):
            KiwiVM(too_long, linked=LIBRARY)
        with self.assertRaisesRegex(VMError, "overlaps its linked segment's data"):
            KiwiVM(program(0x33, words=(0,) * 51), linked=LIBRARY)
        with self.assertRaisesRegex(VMError, 'overlaps the VM stack'):
            KiwiVM(STORY, linked=linked(0x43, words=(0,) * 3105, data_boundary=29396, code_boundary=26942))


if __name__ == '__main__':
    unittest.main()
