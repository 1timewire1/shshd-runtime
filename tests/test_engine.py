from pathlib import Path
import unittest

from exp_runtime.engine import EngineState
from exp_runtime.trace import trace_archive
from exp_runtime.vm import KiwiVM, StopKind, VMError
from test_vm import program


class EngineTests(unittest.TestCase):
    def test_variable_query_result_drives_the_vm(self):
        vm = KiwiVM(program((0x1A, 1000), (0x1A, -9), (0x1F, 0x2C02),
                            (0x1A, 1000), (0x1F, 0x2D01), 0x21, (0x1F, 0x0D01)))
        engine = EngineState()
        vm.run()
        engine.dispatch(vm)
        vm.run()
        self.assertEqual(engine.dispatch(vm).details['result'], -9)
        self.assertEqual(vm.run().args, (-9,))
        self.assertEqual(engine.number_key(1, -1), 65535)

    def test_missing_numbers_are_zero_and_unknown_yields_stay_pending(self):
        vm = KiwiVM(program((0x1A, 1000), (0x1F, 0x2D01), (0x1F, 0xFA00)))
        engine = EngineState()
        vm.run()
        self.assertEqual(engine.dispatch(vm).details['result'], 0)
        event = vm.run()
        action = engine.dispatch(vm)
        self.assertFalse(action.completed)
        self.assertEqual(action.name, 'unhandled_yield')
        self.assertIs(vm.run(), event)

    def test_get_character_art_base_on_an_unset_character_reads_zero(self):
        # Real HD Football Star bytecode calls yield 73 (0x49) without a
        # prior yield 72 (0x48) for that character -- confirmed live: HD's
        # scene 25001 is byte-identical to Android's own script up through
        # this exact point, then diverges (Android calls a subroutine here;
        # HD's compiled script goes straight to this yield instead). Native's
        # entity table is zero-initialized storage, not a sentinel/error
        # path -- raising here was an untested assumption from Android-only
        # evidence, and made real HD content unplayable.
        vm = KiwiVM(program((0x1A, 0), (0x1F, 0x4901)))
        engine = EngineState()
        vm.run()
        action = engine.dispatch(vm)
        self.assertEqual(action.details['result'], 0)

    def test_packed_and_dynamic_text_default(self):
        # '$X\0' at word 0, 'Zoe\0' at word 2.
        vm = KiwiVM(program((0x1A, 0), (0x1A, 2), (0x1A, -1), (0x1F, 0x2F03),
                            0x21, (0x1F, 0x0101), words=(0x2458, 0, 0x5A6F, 0x6500)))
        engine = EngineState()
        vm.run()
        engine.dispatch(vm)
        self.assertEqual(vm.run().args, (0x7FF5,))
        self.assertEqual(engine.read_text(vm, 0x7FF5), 'Zoe')
        self.assertEqual(engine.resolve_text(vm, 0), 'Zoe')
        self.assertEqual(engine.read_text(vm, -1), '')
        with self.assertRaises(VMError):
            engine.read_text(vm, -2)

    def test_existing_player_name_is_preserved(self):
        vm = KiwiVM(program((0x1A, 0), (0x1A, 2), (0x1A, -1), (0x1F, 0x2F03),
                            words=(0x2458, 0, 0x5A6F, 0x6500)))
        engine = EngineState(strings={'$X': 'Alex'})
        vm.run()
        engine.dispatch(vm)
        self.assertEqual(engine.dynamic_strings[0], 'Alex')

    def test_cyclic_substitution_fails_explicitly(self):
        vm = KiwiVM(program(0x33, words=(0x2458, 0)))
        engine = EngineState(strings={'$X': '$Y', '$Y': '$X'})
        with self.assertRaises(VMError):
            engine.resolve_text(vm, 0)

    def test_character_name_formatting_matches_space_boundaries(self):
        self.assertEqual(EngineState._format_name('MR. RUSSELL'), 'Mr. Russell')
        self.assertEqual(EngineState._format_name('MARY-JANE'), 'Mary-jane')
        self.assertEqual(EngineState._format_name('$ZOE'), '$ZOE')

    def test_next_script_preserves_registers_and_stack_backing(self):
        vm = KiwiVM(program((0x01, 123), (0x1A, 77), 0x33))
        self.assertEqual(vm.run().kind, StopKind.HALT)
        vm.load_next(program(0x07, (0x1F, 0x0101)))
        self.assertEqual((vm.pc, vm.sp, vm.fp), (0, 0, 0))
        self.assertEqual(vm.read_word(vm.stack_base), 77)
        self.assertEqual(vm.run().args, (123,))


class BundledEpisodeTests(unittest.TestCase):
    archive = Path(__file__).resolve().parents[1] / 'extract/assets/Assets/The_New_Girl.exp'

    @unittest.skipUnless(archive.exists(), 'local APK fixture is not present')
    def test_native_initialization_and_first_presentation(self):
        result = trace_archive(self.archive)
        self.assertEqual(result['status'], 'presentation')
        self.assertEqual(result['scene'], 25002)
        self.assertEqual(result['steps'], 2561)
        self.assertEqual(len(result['state']['character_names']), 33)
        self.assertEqual(result['state']['character_names'][1], 'Keith')
        self.assertEqual(result['state']['strings'], {'$ZOE': 'Zoe'})
        self.assertEqual(result['state']['scheduled_scripts'], [(25001, True)])
        self.assertEqual(result['events'][-1]['details'], dict(
            title='The New Girl', subtitle='So it begins...', asset_id=1057, flag=0))
        self.assertFalse(result['events'][-1]['completed'])


if __name__ == '__main__':
    unittest.main()
