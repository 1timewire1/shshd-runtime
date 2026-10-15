from pathlib import Path
import tempfile
import unittest

from exp_runtime.dtview_faceplace import DTNode, DTView
from exp_runtime.engine import EngineState
from exp_runtime.runtime import Session
from exp_runtime.vm import KiwiVM
from test_runtime import Resources, host_call, text_words
from test_vm import program


class DTViewFaceplaceTests(unittest.TestCase):
    """Native argument semantics recovered by hand-disassembling the raw
    Thumb-2 SHSScript::syscall call sites for native cases 0x66/0x67/0x6a/
    0x6b/0x73/0x74/0x75/0x76 -- see docs/ENGINE_ABI.md section 6.2. Each
    program below pushes exactly the words the raw disassembly showed being
    read at that yield, in that order, matching the engine.py handlers this
    session wired up in place of the previous no-op drains."""

    def setUp(self):
        # The fixture library's directory is the working directory, where the tree and its per-node saves would land.
        import os
        temporary = tempfile.TemporaryDirectory()
        previous = os.getcwd()
        os.chdir(temporary.name)
        self.addCleanup(temporary.cleanup)
        self.addCleanup(os.chdir, previous)

    def test_yield_102_add_node_hardcodes_exw_zero(self):
        vm = KiwiVM(program((0x1A, 1203), (0x1A, -1), (0x1F, 0x6602)))
        engine = EngineState()
        vm.run()
        action = engine.dispatch(vm)
        self.assertEqual(action.name, 'dt_add_node')
        root = engine.dt_view.root
        self.assertIsNotNone(root)
        self.assertEqual((root.node_type, root.lower_label, root.exw), (1203, '', 0))
        self.assertIs(engine.dt_view.current, root)

    def test_yield_103_add_node_reads_exw_from_third_argument(self):
        vm = KiwiVM(program((0x1A, 1206), (0x1A, -1), (0x1A, 20), (0x1F, 0x6703)))
        engine = EngineState()
        vm.run()
        engine.dispatch(vm)
        root = engine.dt_view.root
        self.assertEqual((root.node_type, root.lower_label, root.exw), (1206, '', 20))

    def test_yield_103_second_node_attaches_at_the_pending_result_index(self):
        vm = KiwiVM(program(
            (0x1A, 1206), (0x1A, -1), (0x1A, 20), (0x1F, 0x6703),  # root
            (0x1A, 1), (0x1A, -1), (0x1F, 0x6A02),  # addResult(index=1, exitLabel='')
            (0x1A, 1216), (0x1A, -1), (0x1A, 0), (0x1F, 0x6703),  # child
        ))
        engine = EngineState()
        vm.run()
        engine.dispatch(vm)
        vm.run()
        engine.dispatch(vm)
        vm.run()
        engine.dispatch(vm)
        root = engine.dt_view.root
        self.assertEqual(set(root.children), {1})
        self.assertEqual(root.children[1].node_type, 1216)
        self.assertIs(engine.dt_view.current, root.children[1])

    def test_yield_106_add_result_reads_a_real_exit_label(self):
        vm = KiwiVM(program((0x1A, 1216), (0x1A, -1), (0x1F, 0x6602),  # a node to attach the result to
                            (0x1A, 1), (0x1A, -1), (0x1F, 0x6A02)))
        engine = EngineState()
        vm.run()
        engine.dispatch(vm)
        vm.run()
        action = engine.dispatch(vm)
        self.assertEqual(action.name, 'dt_add_result')
        root = engine.dt_view.root
        self.assertEqual((root.result_index, root.exit_label), (1, ''))
        self.assertEqual(engine.dt_view.pending_result_index, 1)

    def test_yield_107_stringifies_the_result_index_as_its_own_exit_label(self):
        vm = KiwiVM(program((0x1A, 1216), (0x1A, -1), (0x1F, 0x6602),
                            (0x1A, 3), (0x1F, 0x6B01)))
        engine = EngineState()
        vm.run()
        engine.dispatch(vm)
        vm.run()
        engine.dispatch(vm)
        root = engine.dt_view.root
        self.assertEqual((root.result_index, root.exit_label), (3, '3'))

    def test_faceplace_incoming_message_records_from_and_expression(self):
        vm = KiwiVM(program((0x1A, -1), (0x1A, 8), (0x1A, 2), (0x1F, 0x7303)))
        engine = EngineState()
        vm.run()
        action = engine.dispatch(vm)
        self.assertEqual(action.name, 'faceplace_incoming_message')
        message = engine.faceplace.messages[-1]
        self.assertEqual((message.kind, message.text, message.from_id, message.expression),
                         ('message', '', 8, 2))

    def test_faceplace_incoming_message_substitutes_usr(self):
        # Real device correction: an earlier pass read Faceplace message text
        # without substitution (a "NoTranslation" native helper was read as
        # "skip token substitution"), but real gameplay clearly substitutes
        # $USR in wall posts -- confirmed live ("Say what you will about
        # $USR..." showed up literally, unsubstituted, before this fix).
        words, (text,) = text_words('Say what you will about $USR, but...')
        vm = KiwiVM(program((0x1A, text), (0x1A, 8), (0x1A, 2), (0x1F, 0x7303), words=words))
        engine = EngineState()
        engine.strings['$USR'] = 'Alex'
        vm.run()
        engine.dispatch(vm)
        self.assertEqual(engine.faceplace.messages[-1].text, 'Say what you will about Alex, but...')

    def test_faceplace_continuation_text_reads_text_then_url(self):
        vm = KiwiVM(program((0x1A, -1), (0x1A, -1), (0x1F, 0x7402)))
        engine = EngineState()
        vm.run()
        action = engine.dispatch(vm)
        self.assertEqual(action.name, 'faceplace_continuation_text')
        self.assertEqual(engine.faceplace.messages[-1].kind, 'continuation_text')

    def test_faceplace_continuation_image_needs_three_words_not_two(self):
        # Native case 0x75 was mistakenly assumed to share case 0x74's
        # 2-word shape before this session's raw disassembly; it actually
        # reads 3 (image id, text, url) via two back-to-back objc_msgSend
        # calls -- see docs/ENGINE_ABI.md section 6.2.
        vm = KiwiVM(program((0x1A, 99), (0x1A, -1), (0x1A, -1), (0x1F, 0x7503)))
        engine = EngineState()
        vm.run()
        action = engine.dispatch(vm)
        self.assertEqual(action.name, 'faceplace_continuation_image')
        message = engine.faceplace.messages[-1]
        self.assertEqual((message.kind, message.image_id), ('continuation_image', 99))

    def test_a_continuation_extends_the_post_and_its_alert_instead_of_adding_a_second(self):
        from exp_runtime.dtview_faceplace import FaceplaceToast, FaceplaceWall
        engine = EngineState()
        engine.faceplace.incoming_message('Like football? Try Madden NFL 11!', -1, 0)
        engine.faceplace_toast = FaceplaceToast(engine.faceplace.messages[-1])
        engine.faceplace_toast.tick(150)
        post = engine.faceplace.incoming_continuation_text('Tap here to try Madden NFL 11!', 'http://x')
        engine._alert_for(post)
        self.assertEqual(len(engine.faceplace.messages), 1)
        self.assertEqual(engine.faceplace.messages[0].continuations[0].text, 'Tap here to try Madden NFL 11!')
        self.assertEqual(engine.faceplace_toast.elapsed_ms, 150)     # the alert did not restart
        # With nothing before it, a continuation stands alone; after the alert was dismissed it alerts again.
        wall = FaceplaceWall()
        wall.incoming_continuation_text('Alone', '')
        self.assertEqual([m.kind for m in wall.messages], ['continuation_text'])
        engine.faceplace_toast = None
        engine._alert_for(post)
        self.assertEqual(engine.faceplace_toast.elapsed_ms, 0)

    def test_version_14_save_migrates_faceplace_posts_in_with_no_continuations(self):
        resources = Resources(program(0x33))
        session = Session(resources)
        session.engine.faceplace.incoming_message('Hi', 1, 0)
        old = session.snapshot()
        old['version'] = 14
        for message in old['engine']['faceplace']['messages']:
            del message['continuations']
        restored = Session.from_snapshot(resources, old)
        self.assertEqual(restored.engine.faceplace.messages[0].continuations, [])

    def test_faceplace_clear_wall_empties_the_message_list(self):
        vm = KiwiVM(program((0x1A, -1), (0x1A, 8), (0x1A, 2), (0x1F, 0x7303), (0x1F, 0x7600)))
        engine = EngineState()
        vm.run()
        engine.dispatch(vm)
        self.assertEqual(len(engine.faceplace.messages), 1)
        vm.run()
        action = engine.dispatch(vm)
        self.assertEqual(action.name, 'faceplace_clear_wall')
        self.assertEqual(engine.faceplace.messages, [])

    def test_choice_action_labels_every_result_slot_on_the_current_node(self):
        # Real device confirmed (see dtview_faceplace.py module docstring, a
        # live tree_<serial>.sav captured over USB from a jailbroken iPad):
        # every result slot is labeled with the choice button text the
        # player actually saw, not just the slot taken. That text isn't in
        # addNode's own (hardcoded empty) arguments -- it comes from the
        # separate choice-presentation syscall (yield 1), captured here via
        # Session.advance() while this node is still `current`.
        words, (options,) = text_words('Sports|Girls|TV')
        resources = Resources(program(
            *host_call(102, 1216, -1),
            *host_call(1, -1, options, -1, 0, 1, -1, -1, 0),
            0x33, words=words,
        ))
        session = Session(resources)
        action = session.advance()
        self.assertEqual(action.name, 'choice')
        current = session.engine.dt_view.current
        self.assertEqual(current.node_type, 1216)
        self.assertEqual(current.choice_labels, {0: 'Sports', 1: 'Girls', 2: 'TV'})

    def test_choice_labels_round_trip_through_to_dict_from_dict(self):
        root = DTNode(1216, 'What are you into?', 0)
        root.choice_labels = {0: 'Sports', 1: 'Girls', 2: 'TV'}
        restored = DTNode.from_dict(root.to_dict())
        self.assertEqual(restored.choice_labels, {0: 'Sports', 1: 'Girls', 2: 'TV'})

    def test_to_dict_from_dict_persists_shape_but_resets_current(self):
        # Confirmed against a real device: a fresh playthrough starts back
        # at the root, not wherever an earlier playthrough left off, even
        # though the full tree (including that earlier branch) is still
        # there.
        dt = DTView()
        dt.add_node(1203, 'Week 1', 0)
        dt.add_result(0, '')
        dt.add_node(1206, 'Meet Beth', 20)
        restored = DTView.from_dict(dt.to_dict())
        self.assertEqual(restored.root.lower_label, 'Week 1')
        self.assertEqual(restored.root.children[0].lower_label, 'Meet Beth')
        self.assertIsNone(restored.current)
        self.assertEqual(restored.pending_result_index, 0)
        self.assertFalse(restored.awaiting_result)

    def test_a_fresh_playthrough_starts_at_the_root_with_history_intact(self):
        with tempfile.TemporaryDirectory() as temporary:
            resources = Resources(program(
                *host_call(102, 1203, -1), *host_call(106, 0, -1),
                *host_call(102, 1206, -1), 0x33,
            ))
            resources.library.directory = Path(temporary)
            first = Session(resources)
            first.advance()  # Walks node 1203 -> 1206, saving as it goes.
            self.assertEqual(first.engine.dt_view.current.node_type, 1206)

            second = Session(resources)
            # The persisted tree is already there before this playthrough
            # advances a single step, but "current" starts fresh, not
            # resumed from where the first session left off.
            self.assertIsNone(second.engine.dt_view.current)
            self.assertEqual(second.engine.dt_view.root.node_type, 1203)
            self.assertEqual(second.engine.dt_view.root.children[0].node_type, 1206)
            second.advance()
            # Revisiting reuses the same node object the first session built.
            self.assertIs(second.engine.dt_view.current, second.engine.dt_view.root.children[0])

    def test_dt_view_and_faceplace_survive_a_real_save_round_trip(self):
        # Regression test: DTNode originally carried a `parent` back-
        # reference, which made root<->child a cycle that sent
        # dataclasses.asdict() (runtime.py's save format) into infinite
        # recursion. No unit test or audit tool caught this because none of
        # them ever called session.save()/snapshot() -- only running the
        # real desktop app against a real episode surfaced it, at the
        # first automatic checkpoint on close.
        with tempfile.TemporaryDirectory() as temporary:
            resources = Resources(program(
                *host_call(102, 1203, -1), *host_call(106, 1, -1), *host_call(103, 1216, -1, 20),
                *host_call(115, -1, 8, 2), *host_call(116, -1, -1), 0x33,
            ))
            resources.library.directory = Path(temporary)
            session = Session(resources)
            session.advance()
            restored = Session.from_snapshot(resources, session.snapshot())
            root = restored.engine.dt_view.root
            self.assertEqual(root.node_type, 1203)
            self.assertEqual(root.children[1].node_type, 1216)
            # The continuation (116) belongs to the message (115) before it.
            self.assertEqual(len(restored.engine.faceplace.messages), 1)
            self.assertEqual(len(restored.engine.faceplace.messages[0].continuations), 1)
            self.assertEqual(restored.engine.faceplace.messages[0].from_id, 8)

    def test_version_12_save_migrates_in_an_empty_dt_view_and_wall(self):
        # Real saves from before this feature existed have no dt_view/
        # faceplace/faceplace_toast keys at all -- simulate one rather than
        # relying on a fixture file, matching this codebase's existing
        # legacy-save-migration test style (see test_dialogue.py).
        resources = Resources(program(0x33))
        session = Session(resources)
        legacy = session.snapshot()
        legacy['version'] = 12
        for key in ('dt_view', 'faceplace', 'faceplace_toast'):
            del legacy['engine'][key]
        restored = Session.from_snapshot(resources, legacy)
        self.assertIsNone(restored.engine.dt_view.root)
        self.assertEqual(restored.engine.faceplace.messages, [])
        self.assertIsNone(restored.engine.faceplace_toast)

    def test_faceplace_message_triggers_a_toast(self):
        vm = KiwiVM(program((0x1A, -1), (0x1A, 8), (0x1A, 2), (0x1F, 0x7303)))
        engine = EngineState()
        vm.run()
        engine.dispatch(vm)
        toast = engine.faceplace_toast
        self.assertIsNotNone(toast)
        self.assertIs(toast.message, engine.faceplace.messages[-1])
        self.assertEqual(toast.alpha, 0)  # not yet faded in

    def test_a_newer_toast_replaces_an_older_one(self):
        vm = KiwiVM(program(
            (0x1A, -1), (0x1A, 8), (0x1A, 2), (0x1F, 0x7303),
            (0x1A, -1), (0x1A, 9), (0x1A, 3), (0x1F, 0x7303),
        ))
        engine = EngineState()
        vm.run()
        engine.dispatch(vm)
        first = engine.faceplace_toast
        vm.run()
        engine.dispatch(vm)
        second = engine.faceplace_toast
        self.assertIsNot(first, second)
        self.assertEqual(second.message.from_id, 9)
        self.assertEqual(len(engine.faceplace.messages), 2)

    def test_faceplace_toast_ticks_in_but_never_auto_fades(self):
        # Real device confirmed: unlike an earlier assumption, the toast has
        # no timed fade-out -- it persists indefinitely on its own, however
        # long tick() runs, until something explicitly dismisses it.
        from exp_runtime.dtview_faceplace import FACEPLACE_TOAST_ENTER_MS

        resources = Resources(program(*host_call(115, -1, 8, 2), 0x33))
        session = Session(resources)
        session.advance()
        self.assertIsNotNone(session.engine.faceplace_toast)
        session.tick(FACEPLACE_TOAST_ENTER_MS)
        self.assertEqual(session.engine.faceplace_toast.alpha, 255)
        session.tick(FACEPLACE_TOAST_ENTER_MS * 1000)
        self.assertIsNotNone(session.engine.faceplace_toast)
        self.assertEqual(session.engine.faceplace_toast.alpha, 255)

    def test_a_dialogue_advance_dismisses_a_showing_toast(self):
        # Real device confirmed: advancing dialogue is one of the toast's
        # three explicit dismissal triggers (the other two -- opening the
        # settings menu and opening the side panels -- are Desktop-layer UI
        # state, covered in test_desktop.py instead).
        words, (text,) = text_words('Story continues')
        resources = Resources(program(
            *host_call(115, -1, 8, 2), *host_call(13, text, 0), 0x33, words=words))
        session = Session(resources)
        action = session.advance()
        self.assertIsNotNone(session.engine.faceplace_toast)
        self.assertEqual(action.name, 'dialogue')
        session.answer()
        self.assertIsNone(session.engine.faceplace_toast)

    def test_faceplace_toast_does_not_survive_close_episode(self):
        vm = KiwiVM(program((0x1A, -1), (0x1A, 8), (0x1A, 2), (0x1F, 0x7303)))
        engine = EngineState()
        vm.run()
        engine.dispatch(vm)
        self.assertIsNotNone(engine.faceplace_toast)
        engine.close_episode()
        self.assertIsNone(engine.faceplace_toast)
        self.assertIsNotNone(engine.faceplace.messages)  # the wall itself persists

    def test_dt_view_and_faceplace_survive_close_episode(self):
        # DTNode::addNode auto-saves to its own tree_<serial>.sav file,
        # independent of the episode save -- confirmed persistent across
        # sessions in the native decompile (docs/ENGINE_ABI.md section 6.1).
        vm = KiwiVM(program((0x1A, 1203), (0x1A, -1), (0x1F, 0x6602)))
        engine = EngineState()
        vm.run()
        engine.dispatch(vm)
        engine.close_episode()
        self.assertIsNotNone(engine.dt_view.root)


if __name__ == '__main__':
    unittest.main()


class DtJoinTests(unittest.TestCase):
    def test_a_duplicate_join_sends_the_next_node_back_to_the_original(self):
        from exp_runtime.dtview_faceplace import DTView
        view = DTView()
        first = view.add_node(1203, 'Start', 0, uid=7)          # an event: no result to wait for
        self.assertTrue(first.primary)
        self.assertFalse(view.awaiting_result)
        join = view.add_node(0x4c8, '', 0, uid=7)               # the same ids as `first`: not primary
        self.assertFalse(join.primary)
        again = view.add_node(1204, 'After the join', 0, uid=9)
        self.assertIs(view.find(7, 0), first)
        self.assertIs(first.children[0], again)

    def test_decision_nodes_wait_for_a_result_and_keep_one_branch(self):
        from exp_runtime.dtview_faceplace import DTView
        view = DTView()
        view.add_node(0x4c0, 'Choose', 0)
        self.assertTrue(view.awaiting_result)
        view.add_result(0, 'A')
        view.add_node(1204, 'After A', 0)
        view.current, view.pending_result_index = view.root, 1
        moved = view.add_node(1204, 'After B', 0)
        self.assertEqual(sorted(view.root.children), [1])
        self.assertIs(view.root.children[1], moved)
