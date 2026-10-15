import unittest

from exp_runtime.engine import EngineState, NATIVE_DEFAULT_YIELDS
from exp_runtime.vm import KiwiVM
from test_runtime import host_call, text_words
from test_vm import program


def dispatch(engine, *call, words=None):
    vm = KiwiVM(program(*call, 0x33, words=words) if words else program(*call, 0x33))
    vm.run()
    return engine.dispatch(vm), vm


class ScriptServiceTests(unittest.TestCase):
    def test_ids_without_a_native_case_are_no_ops_whatever_their_arguments(self):
        for y in sorted(NATIVE_DEFAULT_YIELDS):
            for count in (0, 2):
                action, _ = dispatch(EngineState(), *host_call(y, *range(1, count + 1)))
                self.assertEqual((action.name, action.completed), ('native_noop', True), y)

    def test_the_poll_waits_for_its_failed_download_then_the_script_gets_zero(self):
        from exp_runtime.engine import POLL_WAIT_MS
        from exp_runtime.runtime import Session
        from test_runtime import Resources, text_words
        words, refs = text_words('After the poll')
        resources = Resources(program(*host_call(9, 1, 2), *host_call(13, refs[0], 0), 0x33, words=words))
        session = Session(resources)
        action = session.advance()
        self.assertEqual((action.name, action.completed), ('download_poll', False))     # the bar shows; the script waits
        session.tick(POLL_WAIT_MS - 1)
        self.assertEqual(session.pending.name, 'download_poll')
        self.assertIs(session.answer(), session.pending)                                # it takes no input
        restored = Session.from_snapshot(resources, session.snapshot())                 # and can be saved mid-wait
        self.assertEqual(restored.pending.details, {'elapsed_ms': POLL_WAIT_MS - 1})
        for waiting in (session, restored):
            waiting.tick(1)
            self.assertEqual(waiting.pending.name, 'dialogue')

    def test_the_loading_screen_of_service_91_is_not_the_polls(self):
        from exp_runtime.runtime import Session
        from test_runtime import Resources
        session = Session(Resources(program(*host_call(91, 1), 0x33)))
        self.assertEqual(session.advance().name, 'loading')
        self.assertIsNotNone(session.engine.loading)                                    # the poll never touches this state
        poll = Session(Resources(program(*host_call(9, 1, 2), 0x33)))
        poll.advance()
        self.assertIsNone(poll.engine.loading)

    def test_titled_dialogue_is_the_named_dialogue(self):
        words, (title, text) = text_words('Coach', 'Hustle up.')
        details = {}
        for y in (15, 76):
            action, _ = dispatch(EngineState(), *host_call(y, title, text), words=words)
            self.assertEqual(action.name, 'dialogue')
            details[y] = {k: v for k, v in action.details.items()}
        self.assertEqual(details[15], details[76])
        self.assertEqual((details[15]['speaker'], details[15]['text'], details[15]['presentation_mode']),
                         ('Coach', 'Hustle up.', 3))

    def test_branch_and_join_nodes_join_the_tree(self):
        engine = EngineState()
        words, refs = text_words('one', 'two', 'three')
        action, vm = dispatch(engine, *host_call(111, 1221, 104, *refs), words=words)
        self.assertEqual(action.name, 'dt_add_node')
        node = engine.dt_view.root
        self.assertEqual((node.node_type, node.condition, node.lower_label), (1221, 104, 'three'))
        engine.dt_view.awaiting_result = False
        action, _ = dispatch(engine, *host_call(112))
        self.assertEqual(engine.dt_view.current.node_type, 0x4c8)

    def test_pan_yield_needs_both_arguments(self):
        action, _ = dispatch(EngineState(), *host_call(97, 1, 3))
        self.assertEqual(action.name, 'set_background_pan')


if __name__ == '__main__':
    unittest.main()


class MoreServiceTests(unittest.TestCase):
    def test_a_negative_title_pointer_is_an_empty_title(self):
        words, (text,) = text_words('Hello')
        engine = EngineState()
        engine.hd_version = '1.4.38'      # HD's own case 0xf; Android's and the iPhone's skip the prefix instead
        action, _ = dispatch(engine, *host_call(15, -3, text, 2, -1), words=words)
        self.assertEqual((action.details['speaker'], action.details['text']), ('', 'Hello'))

    def test_int_arrays_and_weighted_pick(self):
        engine = EngineState()
        for value in (5, 7):
            dispatch(engine, *host_call(56, 3, 40, value))
        self.assertEqual(dispatch(engine, *host_call(58, 3, 40))[0].details['result'], 2)
        self.assertEqual(dispatch(engine, *host_call(57, 3, 40, 1))[0].details['result'], 7)
        dispatch(engine, *host_call(59, 3, 40, 0))
        self.assertEqual(dispatch(engine, *host_call(57, 3, 40, 0))[0].details['result'], 7)
        self.assertEqual(dispatch(engine, *host_call(66, 0, 0, 5))[0].details['result'], 2)      # only one nonzero weight

    def test_sprintf_writes_into_memory(self):
        engine = EngineState()
        words, (pattern, text) = text_words('%d of %s!', 'ten')
        buffer = len(words)
        words = list(words) + [0] * 16
        vm = KiwiVM(program(*host_call(22, buffer, pattern, 3, text), 0x33, words=words))
        vm.run()
        engine.dispatch(vm)
        self.assertEqual(engine.read_text(vm, buffer), '3 of ten!')

    def test_music_pause_and_default_ids(self):
        engine = EngineState()
        dispatch(engine, *host_call(83))
        self.assertTrue(engine.music_paused)
        dispatch(engine, *host_call(84))
        self.assertFalse(engine.music_paused)


class HdBuildServiceTests(unittest.TestCase):
    def test_hd_build_query_table(self):
        engine = EngineState()
        engine.hd_version = '1.2.3'
        results = {selector: dispatch(engine, *host_call(70, selector))[0].details['result']
                   for selector in (2, 3, 6, 9, 10, 11, 5)}
        self.assertEqual(results, {2: 2, 3: 6, 6: 0x7ff5, 9: 1, 10: 2, 11: 0, 5: 0})
        self.assertEqual(engine.dynamic_strings[0], '1.2.3')

    def test_status_icons_show_on_the_next_text_without_a_speaker_change(self):
        engine = EngineState()
        engine.ui_defaults = {74: 0, 75: 7}
        engine.character_names = {0: 'Player', 10: 'Adam'}
        engine.character_art_variants = {0: [100] * 5, 10: [200] * 5}
        engine.present_dialogue(10, 0, 'Hi', 0)
        dispatch(engine, *host_call(38, 3012, 3))
        words, (text,) = text_words('And more.')
        action, _ = dispatch(engine, *host_call(37, text), words=words)
        self.assertEqual(action.name, 'dialogue')
        change = action.details['relationship']
        self.assertEqual((change['asset_id'], change['count'], change['previous_count']), (3012, 3, 3))
        self.assertEqual(engine.status_icons, [-1, -1])
