import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from exp_runtime.engine import EngineAction, EngineState
from exp_runtime.runtime import SaveError, Session
from test_runtime import Resources, answer_screen, host_call, text_words
from test_vm import program


def resources(*, shuffle=1, count=4, timeout=0, enabled=(1, 1, 1, 1)):
    words, refs = text_words('Choose', 'A question.', 'Alpha', 'Beta', 'Gamma', 'Delta')
    calls = [(0x1a, 77)] + host_call(2, refs[0], refs[1], timeout, 3, -1, 1)
    for ref, value, flag in zip(refs[2:2 + count], (101, -999, -303, 32767), enabled):
        calls += host_call(3, ref, value, flag)
    calls += host_call(4, shuffle)
    # Capture the actual choice callback and next service-27 draw with a
    # retained stack word; neither rendering nor a save may redraw the order.
    calls += [0x21] + host_call(27, 100) + [0x21, (0x1f, 0xfe03)]
    return Resources(program(*calls, words=words))


def stopped_session(r, seed=1):
    """An old unsupported service-4 checkpoint, before any shuffle draws."""
    s = Session(r)
    s.engine.random.state = seed
    while True:
        request = s.vm.run()
        if request.yield_id == 4:
            s.pending = EngineAction('unhandled_yield', request, False,
                                    dict(reason='Native randomized option order is not implemented'))
            return s
        if not s.engine.dispatch(s.vm).completed:
            raise AssertionError('Unexpected input before the choice builder was complete')


class ChoiceShuffleTests(unittest.TestCase):
    def test_native_orders_draw_counts_and_mapped_callbacks(self):
        # Fixed vectors for 000aeee4 / 0004c1bc / 00122554. The full-list
        # swaps differ from a shrinking Fisher-Yates shuffle and libc lrand48.
        vectors = ((1, [2, 1, 3, 0], 0xc46b9b3d, 43),
                   (0x12345678, [3, 2, 0, 1], 0x99946224, 64),
                   (0xffffffff, [1, 0, 3, 2], 0xe85e9d1b, 49))
        for seed, order, state, next_draw in vectors:
            for flag in (1, -1):
                with self.subTest(seed=seed, shuffle=flag):
                    r = resources(shuffle=flag)
                    s = stopped_session(r, seed)
                    held, libc = s.vm.snapshot(), s.engine.random48.state
                    s.engine.result_cells[0] = 42
                    builder = copy.deepcopy(s.engine.choice_builder)
                    s.pending = None
                    action = s.advance()
                    self.assertEqual(action.name, 'choice')
                    self.assertEqual(action.request.args, (flag,))
                    self.assertIsNone(s.engine.choice_builder)
                    for key in ('options', 'values'):
                        self.assertEqual(action.details[key], [builder[key][i] for i in order])
                    self.assertEqual(s.engine.random.state, state)
                    self.assertEqual(s.engine.random48.state, libc)
                    self.assertEqual(s.vm.snapshot(), held)
                    self.assertEqual(s.engine.result_cells[0], 42)
                    s.tick(250)
                    before = s.snapshot()
                    saved = json.loads(json.dumps(before))
                    for row, original_index in enumerate(order):
                        restored = Session.from_snapshot(r, saved)
                        self.assertEqual(restored.snapshot(), before)
                        restored.advance(); restored.tick(500)
                        self.assertEqual(restored.snapshot(), before)
                        value = builder['values'][original_index]
                        self.assertEqual(restored.answer(row).request.args, (77, value, next_draw))
                        self.assertEqual(restored.engine.result_cells[0], value)
                        self.assertEqual(restored.engine.random48.state, libc)

    def test_zero_flag_does_not_draw_or_reorder(self):
        s = stopped_session(resources(shuffle=0))
        builder = copy.deepcopy(s.engine.choice_builder)
        s.pending = None
        self.assertEqual(s.advance().details, builder)
        self.assertEqual(s.engine.random.state, 1)
        self.assertEqual(answer_screen(s, 1).request.args, (77, 1, 38))

    def test_empty_list_draws_nothing_but_singleton_still_draws_once(self):
        for count, state in ((0, 1), (1, 0x41c67ea6)):
            with self.subTest(count=count):
                r = resources(count=count)
                s = stopped_session(r); s.pending = None
                self.assertEqual(s.advance().name, 'choice')
                self.assertEqual(len(s.pending.details['options']), count)
                self.assertEqual(s.engine.random.state, state)
                self.assertEqual(Session.from_snapshot(r, s.snapshot()).snapshot(), s.snapshot())
                if count:
                    self.assertEqual(answer_screen(s, 0).request.args, (77, 101, 82))

    def test_native_shuffle_leaves_enabled_flags_at_their_row_positions(self):
        s = stopped_session(resources(enabled=(0, 1, 1, 0)))
        s.pending = None; s.advance()
        self.assertEqual(s.pending.details['options'], ['Gamma', 'Beta', 'Delta', 'Alpha'])
        self.assertEqual(s.pending.details['enabled'], [False, True, True, False])
        before = s.snapshot()
        for row in (0, 3):
            with self.assertRaises(ValueError):
                s.answer(row)
            self.assertEqual(s.snapshot(), before)
        self.assertEqual(answer_screen(s, 2).request.args, (77, 32767, 43))

    def test_timeout_uses_shuffled_mapping_even_for_a_disabled_row(self):
        r = resources(timeout=1000, enabled=(1, 1, 1, 0))
        s = stopped_session(r); s.pending = None; s.advance()
        held = s.vm.snapshot()
        s.tick(250)
        before = s.snapshot()
        saved = json.loads(json.dumps(before))
        s = Session.from_snapshot(r, saved)
        self.assertEqual(s.snapshot(), before)
        self.assertEqual(s.remaining_ms, 750)
        s.tick(750)
        self.assertEqual(s.vm.snapshot(), held)
        self.assertEqual(s.tick(0).name, 'choice')
        self.assertEqual(s.tick(1).request.args, (77, 101, 43))
        self.assertEqual(s.engine.result_cells[0], 101)

    def test_old_stopped_saves_shuffle_once_without_replaying_previous_calls(self):
        for timeout in (0, 1000):
            r = resources(timeout=timeout)
            s = stopped_session(r)
            saved = json.loads(json.dumps(s.snapshot()))
            original = copy.deepcopy(saved)
            restored = Session.from_snapshot(r, saved)
            self.assertEqual(saved, original)
            self.assertEqual(restored.pending.name, 'choice')
            self.assertEqual(restored.vm.snapshot(), s.vm.snapshot())
            self.assertEqual(restored.engine.random.state, 0xc46b9b3d)
            self.assertEqual(restored.engine.random48, s.engine.random48)
            self.assertEqual(restored.remaining_ms, timeout or None)
            self.assertEqual(restored.pending.details['values'], [-303, 1, 32767, 101])
            self.assertIsNone(restored.engine.choice_builder)
            again = Session.from_snapshot(r, restored.snapshot())
            self.assertEqual(again.snapshot(), restored.snapshot())
            self.assertEqual(answer_screen(again, 0).request.args, (77, -303, 43))

    def test_invalid_stopped_builder_is_rejected_without_changing_the_save(self):
        r = resources()
        s = stopped_session(r)
        for builder in (None, {}, dict(s.engine.choice_builder, values=[101])):
            saved = s.snapshot()
            saved['engine']['choice_builder'] = builder
            original = copy.deepcopy(saved)
            with self.assertRaises(SaveError):
                Session.from_snapshot(r, saved)
            self.assertEqual(saved, original)

    def test_invalid_stopped_argument_count_is_rejected_before_shuffling(self):
        words, (title, prompt) = text_words('Choose', 'A question.')
        for args in ((), (1, 2)):
            r = Resources(program(*host_call(2, title, prompt, 0, 0, -1, 1),
                                  *host_call(4, *args), 0x33, words=words))
            saved = stopped_session(r).snapshot()
            original = copy.deepcopy(saved)
            with self.assertRaisesRegex(SaveError, 'shuffle argument'):
                Session.from_snapshot(r, saved)
            self.assertEqual(saved, original)

    @unittest.skipUnless(Path('.shs-library/library.json').is_file(), 'user content required')
    def test_both_new_girl_versions_recover_the_reported_scene_and_continue(self):
        from exp_runtime.content import ContentLibrary

        dispatch = EngineState.dispatch
        def old_dispatch(engine, vm, **kwargs):
            if vm.pending.yield_id == 4 and vm.pending.args[0]:
                return EngineAction('unhandled_yield', vm.pending, False,
                                    dict(reason='Native randomized option order is not implemented'))
            return dispatch(engine, vm, **kwargs)

        with ContentLibrary(Path('.shs-library')) as lib:
            for selector, pc in (('The_New_Girl.exp', 1465), ('SHS_The_New_Girl.exp', 1478)):
                with self.subTest(episode=selector):
                    if selector not in {entry['name'] for entry in lib.episodes}:
                        self.skipTest(f'{selector} unavailable')
                    r = lib.open_episode(selector)
                    s = Session(r); s.engine.random.state = 1
                    # Reproduce the old stop through genuine story inputs and
                    # elapsed minigame time, without editing script state.
                    with patch.object(EngineState, 'dispatch', old_dispatch):
                        s.advance()
                        for _ in range(6000):
                            action = s.pending
                            if action.name == 'unhandled_yield':
                                break
                            if action.name == 'word_game':
                                s.tick(400)
                                for _ in range(10):
                                    s.answer(s.engine.word_game.weights.index(1)); s.tick(500)
                                s.tick(s.engine.word_game.remaining_ms + 1)
                            elif action.name == 'word_grid':
                                game = s.engine.word_grid
                                if game.phase == 1 and game.tutorial:
                                    if game.problem.tap_to_advance:
                                        s.answer()
                                    else:
                                        path = next((path for start in game.starts for word in game.problem.words
                                                     if (path := game.find_path(start, word))), None)
                                        self.assertIsNotNone(path)
                                        s.grid_pointer('down', path[0])
                                        for cell in path[1:]:
                                            s.grid_pointer('move', cell)
                                        s.grid_pointer('up')
                                s.tick(250)
                            elif action.name == 'loading':
                                s.tick(3001)
                            elif action.name == 'text_input':
                                s.answer('Alex')
                            elif action.name == 'character_picker':
                                s.answer(0); s.tick(25); s.answer()
                            elif action.name == 'choice':
                                options = action.details['options']
                                selection = (options.index('Just hang out alone.')
                                             if 'Just hang out alone.' in options else
                                             options.index('Algebra.') if 'Algebra.' in options else 0)
                                answer_screen(s, selection)
                            else:
                                self.assertIn(action.name, ('dialogue', 'presentation', 'vm_pause'))
                                answer_screen(s)
                        else:
                            self.fail('Did not reach the randomized choice')
                    self.assertEqual((s.scene, s.pending.request.yield_id, s.pending.request.pc,
                                      s.pending.request.args), (25005, 4, pc, (1,)))
                    saved = json.loads(json.dumps(s.snapshot()))
                    original = copy.deepcopy(saved)
                    restored = Session.from_snapshot(r, saved)
                    self.assertEqual(saved, original)
                    self.assertEqual(restored.pending.name, 'choice')
                    self.assertEqual(restored.vm.snapshot(), s.vm.snapshot())
                    self.assertEqual(restored.remaining_ms, s.engine.choice_builder['timeout_ms'] or None)
                    self.assertIsNone(restored.engine.choice_builder)
                    self.assertCountEqual(restored.pending.details['values'], s.engine.choice_builder['values'])
                    for row, value in enumerate(restored.pending.details['values']):
                        branch = Session.from_snapshot(r, restored.snapshot())
                        self.assertEqual(branch.snapshot(), restored.snapshot())
                        self.assertEqual(answer_screen(branch, row).name, 'dialogue')
                        self.assertEqual(branch.engine.result_cells[0], value)
                        self.assertGreater(branch.vm.steps_executed, restored.vm.steps_executed)


if __name__ == '__main__':
    unittest.main()
