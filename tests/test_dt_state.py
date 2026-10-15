"""The tree's game-state snapshots, deltas and automatic branches (`exp_runtime.dt_state`), on authored values."""
from pathlib import Path
import tempfile
import unittest

from exp_runtime.dt_state import (ABSOLUTE_COUNT, GLOBAL_COUNT, SLOTS, STATE_IDS, apply_deltas, autobranch, compute_deltas,
                                  install_state, read_state, zero_state)
from exp_runtime.dtview_faceplace import DTNode, DTView
from exp_runtime.engine import EngineState
from exp_runtime.runtime import Session
from test_runtime import Resources, host_call
from test_vm import program


def state_with(**slots):
    state = zero_state()
    for slot, value in slots.items():
        state[int(slot[1:])] = value
    return state


class DeltaTests(unittest.TestCase):
    def test_the_first_slots_are_kept_absolute_and_the_rest_as_differences(self):
        previous = state_with(s2=5, s30=5)
        live = state_with(s2=7, s30=9, s60=3)
        snapshot, deltas = compute_deltas(previous, live, [])
        self.assertEqual(deltas, [(-STATE_IDS[2], 7), (STATE_IDS[30], 4), (STATE_IDS[60], 3)])
        self.assertEqual(snapshot, live)
        self.assertEqual(apply_deltas(previous, deltas), live)

    def test_a_cleared_accumulator_is_kept_as_an_absolute_value_once(self):
        accumulators = [STATE_IDS[30]]
        previous = state_with(s30=5)
        snapshot, deltas = compute_deltas(previous, state_with(s30=2), accumulators)
        self.assertEqual(deltas, [(-STATE_IDS[30], 2)])
        self.assertEqual(accumulators, [])                                # emptied by the computation
        self.assertEqual(apply_deltas(previous, deltas)[30], 2)

    def test_nothing_changed_means_no_deltas(self):
        snapshot, deltas = compute_deltas(state_with(s31=1), state_with(s31=1), [])
        self.assertEqual(deltas, [])

    def test_slots_split_between_the_global_properties_and_the_characters(self):
        self.assertEqual((SLOTS, GLOBAL_COUNT, ABSOLUTE_COUNT), (67, 0x26, 0x1a))
        engine = EngineState()
        engine.numbers[engine.number_key(0, STATE_IDS[0])] = 44
        engine.numbers[engine.number_key(STATE_IDS[40], 0x197)] = -2
        state = read_state(engine)
        self.assertEqual((state[0], state[40]), (44, -2))

    def test_installing_a_snapshot_sets_the_variables_and_each_characters_display_properties(self):
        engine = EngineState()
        snapshot = state_with(s1=STATE_IDS[GLOBAL_COUNT + 1], s39=3, s45=-1, s40=0)
        install_state(engine, snapshot)
        number = lambda owner, key: engine.numbers[engine.number_key(owner, key)]
        self.assertEqual(number(0, 601), STATE_IDS[GLOBAL_COUNT + 1])
        dated = STATE_IDS[39]
        self.assertEqual((number(dated, 3001), number(dated, 3000)), (4, 3010))     # value + 1; the character now dated
        self.assertEqual((number(STATE_IDS[45], 3001), number(STATE_IDS[45], 3000)), (0, 3011))   # ~(-1); a negative one
        self.assertEqual((number(STATE_IDS[40], 3001), number(STATE_IDS[40], 3000)), (1, 3012))   # anyone else


class AutobranchTests(unittest.TestCase):
    def test_conditions_on_the_person_dated(self):
        self.assertEqual([autobranch(0x4b, state_with(s0=v)) for v in (44, 11, 3)], [0, 1, 2])
        self.assertEqual([autobranch(0x4c, state_with(s0=v)) for v in (11, 12)], [0, 1])
        self.assertEqual([autobranch(0x51, state_with(s0=v)) for v in (44, 11, 50, 7)], [0, 1, 2, 3])

    def test_threshold_conditions(self):
        self.assertEqual([autobranch(0x58, state_with(s32=v)) for v in (7, 5, 3)], [0, 1, 2])
        self.assertEqual([autobranch(0x55, state_with(s31=v)) for v in (4, 2, 1)], [0, 1, 2])
        self.assertEqual([autobranch(0x5d, state_with(s2=v)) for v in (503, 504, 0)], [0, 1, 2])
        self.assertEqual(autobranch(0x54, state_with(s28=3, s29=4)), 1)           # 3 * 400 / 4 = 300 > 299
        self.assertEqual(autobranch(0x54, state_with(s28=2, s29=3)), 0)
        self.assertEqual(autobranch(0x54, state_with(s28=5, s29=0)), 0)

    def test_flag_conditions_and_the_one_that_falls_through(self):
        self.assertEqual([autobranch(0x52, state_with(s3=v)) for v in (0, 1)], [0, 1])
        self.assertEqual([autobranch(0x53, state_with(s3=v)) for v in (0, 1)], [1, 0])
        self.assertEqual(autobranch(0x67, state_with(s4=0, s10=5)), autobranch(0x68, state_with(s4=0, s10=5)))
        self.assertEqual(autobranch(0x67, state_with(s4=3)), 0)

    def test_codes_the_app_does_not_decide_leave_the_result_alone(self):
        for code in (0, 0x4a, 0x69, 0x4c5):
            self.assertIsNone(autobranch(code, zero_state()))


class TreeStateTests(unittest.TestCase):
    def numbers(self, **values):
        engine = EngineState()
        for name, value in values.items():
            engine.numbers[engine.number_key(0, STATE_IDS[int(name[1:])])] = value
        return read_state(engine)

    def test_a_scene_records_what_changed_since_the_one_before_and_a_sweep_rebuilds_the_state(self):
        view = DTView()
        first = view.add_node(1203, 'One', 0, uid=1, script=1, state=self.numbers())
        self.assertEqual(first.deltas, [])                                  # nothing before the first scene
        view.add_result(0, '')
        second = view.add_node(0x4c5, 'Branch', 0, uid=2, script=2, state=self.numbers(s0=44))
        second.condition = 0x4b
        self.assertEqual(second.deltas, [(-STATE_IDS[0], 44)])
        view.add_result(0, '')
        third = view.add_node(1203, 'Three', 0, uid=3, script=3, state=self.numbers(s0=44, s31=2))
        self.assertEqual(third.deltas, [(STATE_IDS[31], 2)])
        third.snapshot = zero_state()
        view.sweep_forward(view.root)
        self.assertEqual((third.snapshot[0], third.snapshot[31]), (44, 2))    # rebuilt from the deltas along the story
        self.assertEqual(second.result_index, 0)                              # decided by the branch's own scene: 44 -> 0

    def test_an_automatic_branch_follows_its_scene_state_not_the_result_last_recorded(self):
        view = DTView()
        view.add_node(1203, 'One', 0, uid=1, script=1, state=self.numbers())
        view.add_result(0, '')
        branch = view.add_node(0x4c5, '', 0, uid=2, script=2, state=self.numbers(s0=11))
        branch.condition = 0x4b
        view.add_result(0, '')                                                # the script's own answer
        self.assertEqual(branch.result_index, 1)                              # the state says 11 -> slot 1

    def test_scenes_recorded_before_state_was_kept_are_left_alone(self):
        view = DTView()
        view.add_node(1203, 'One', 0, uid=1, script=1)
        view.add_result(0, '')
        branch = view.add_node(0x4c5, '', 0, uid=2, script=2)
        branch.condition = 0x4b
        view.add_result(2, '')
        self.assertEqual(branch.result_index, 2)                              # unknown state decides nothing

    def test_deltas_survive_the_tree_file(self):
        view = DTView()
        view.add_node(1203, 'One', 0, uid=1, script=1, state=self.numbers())
        view.add_result(0, '')
        view.add_node(1203, 'Two', 0, uid=2, script=2, state=self.numbers(s30=3))
        again = DTView.from_dict(view.to_dict())
        self.assertEqual(again.root.children[0].deltas, [(STATE_IDS[30], 3)])
        old = view.to_dict()
        del old['root']['children']['0']['deltas']
        self.assertIsNone(DTView.from_dict(old).root.children[0].deltas)      # a tree from before: unknown


class ServiceTests(unittest.TestCase):
    def test_clearing_an_accumulator_empties_the_counter_and_marks_it(self):
        resources = Resources(program(0x33))
        session = Session(resources)
        engine = session.engine
        engine.numbers[engine.number_key(0, 3100)] = 6
        engine.numbers[engine.number_key(13, 0x197)] = 4
        for identifier in (3100, 13):
            from test_script_services import dispatch
            action, _ = dispatch(engine, *host_call(108, identifier))
            self.assertEqual(action.name, 'dt_clear_global_accumulator')
        self.assertEqual(engine.numbers[engine.number_key(0, 3100)], 0)      # a property of entity 0
        self.assertEqual(engine.numbers[engine.number_key(13, 0x197)], 0)    # below 600: a character's relationship value
        self.assertEqual(engine.dt_view.accumulators, [3100, 13])

    def test_the_accumulators_are_part_of_a_game_save_and_a_warp_installs_the_scene_state(self):
        with tempfile.TemporaryDirectory() as directory:
            resources = Resources(program(*host_call(102, 1203, -1), *host_call(106, 0, -1), *host_call(102, 1206, -1), 0x33))
            resources.library.directory = Path(directory)
            session = Session(resources)
            session.engine.dt_view.accumulators.append(3038)
            state = session.snapshot()
            self.assertEqual(state['engine']['dt_view']['accumulators'], [3038])
            restored = Session.from_snapshot(resources, state)
            self.assertEqual(restored.engine.dt_view.accumulators, [3038])
            older = session.snapshot()
            del older['engine']['dt_view']['accumulators']
            older['version'] = 21
            self.assertEqual(Session.from_snapshot(resources, older).engine.dt_view.accumulators, [])


if __name__ == '__main__':
    unittest.main()
