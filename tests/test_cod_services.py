"""Authored callers for CoD's recovered build query and default services."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from exp_runtime.content import ContentLibrary, import_game
from exp_runtime.engine import EngineAction, EngineState
from exp_runtime.runtime import SaveError, Session
from exp_runtime.trace import trace_archive
from exp_runtime.vm import KiwiVM, VMError
from test_content import archive, metadata
from test_games import LOCAL_COD_IPA, make_cod_ipa
from test_runtime import Resources, answer_screen, host_call, text_words
from test_vm import program


LOCAL_PROMOTION_EPISODES = tuple(Path('decomp/cod/CoD Episodes') / name for name in (
    'What_Happened_To_Colt_Part_2.exp', 'Halloween_Special_Dead_Man_Walking_1.exp'))


def caller(service, args=(), *, dynamic=False, retained=None):
    prefix = [(0x1a, 77)]
    if retained is not None:
        prefix += [(0x1a, retained), 0x15]
    call = ([(0x1a, a) for a in args] + [(0x20, len(args)), (0x1e, service)]
            if dynamic else host_call(service, *args))
    return program(*prefix, *call, 0x21, (0x1f, 0xfe02), 0x33)


def resources(p, *, version=None):
    r = Resources(p)
    r.library.game_id = 'cod'
    r.library.app_info = {'CFBundleVersion': version} if version is not None else {}
    return r


class CoDServiceTests(unittest.TestCase):
    def test_default_services_pop_only_their_frame_without_minigame_side_effects(self):
        for service, count in ((94, 22), (96, 20), (100, 2)):
            for dynamic in (False, True):
                for args in ((), (-1,), tuple(range(count)), (32767, -1, 432)):
                    with self.subTest(service=service, dynamic=dynamic, count=len(args)):
                        s = Session(resources(caller(service, args, dynamic=dynamic)))
                        s.engine.football_scores = [14, 7]
                        s.engine.result_cells[0] = 42
                        s.engine.numbers[901] = 123
                        s.engine.next_dialogue_notice = 'Retained notice'
                        s.vm.write_word(s.vm.stack_base + 1023, 456)
                        request = s.vm.run()
                        before = copy.deepcopy(s.engine)
                        pc, steps = s.vm.pc, s.vm.steps_executed
                        action = s.engine.dispatch(s.vm)
                        self.assertEqual((action.name, action.completed, action.details),
                                         ('native_noop', True, {'result': 0}))
                        self.assertIs(action.request, request)
                        self.assertEqual((s.vm.pc, s.vm.steps_executed), (pc, steps))
                        self.assertEqual(s.engine, before)
                        self.assertEqual(s.vm.run().args, (77, 0))
                        self.assertEqual(s.vm.read_word(s.vm.stack_base + 1023), 456)
        # SHS's 94/96 still invoke its actual minigame contracts.
        for service in (94, 96):
            vm = KiwiVM(caller(service)); request = vm.run()
            with self.assertRaisesRegex(VMError, 'expected .* arguments'):
                EngineState().dispatch(vm)
            self.assertIs(vm.pending, request)

    def test_promotional_urls_continue_locally_and_other_unknown_services_stay_pending(self):
        for target in ('https://example.invalid/game', 'authored-game://promotion'):
            for next_story in (False, True):
                with self.subTest(target=target, next_story=next_story):
                    words, refs = text_words(target, 'The story continues.')
                    continuation = host_call(13, refs[1], 0) if next_story else []
                    r = resources(program(*host_call(100, refs[0], -1), *continuation,
                                          *host_call(7), 0x33, words=words))
                    s = Session(r)
                    with patch('webbrowser.open', side_effect=AssertionError('Opened a promotion')), \
                            patch('socket.socket', side_effect=AssertionError('Connected to a promotion')):
                        action = s.advance()
                        if next_story:
                            self.assertEqual(action.name, 'dialogue')
                            self.assertEqual(action.details['text'], 'The story continues.')
                            action = answer_screen(s)
                        self.assertEqual(action.name, 'episode_exit')
                        self.assertEqual(s.vm.sp, 0)
                        # CoD 1.4.7 opens it (exitAndShowURL); it is kept for the host to offer instead.
                        self.assertEqual(s.engine.store_link, target)
        # (This fork's SHS takes HD's default case for 100: test_shs_services.py.)
        for game, services in (('cod', (9, 91, 95, 101, 255)),):
            for service in services:
                with self.subTest(game=game, service=service):
                    vm = KiwiVM(caller(service, (1, -1)))
                    request = vm.run()
                    before = vm.snapshot()
                    engine = EngineState(); engine.game_key = game
                    action = engine.dispatch(vm)
                    self.assertEqual(action.name, 'unhandled_yield')
                    self.assertIs(action.request, request)
                    self.assertEqual(vm.snapshot(), before)

    @unittest.skipUnless(LOCAL_COD_IPA.is_file() and all(p.is_file() for p in LOCAL_PROMOTION_EPISODES),
                         'original user CoD IPA/promotion episodes are unavailable')
    def test_original_promotion_call_sites_restore_and_follow_the_script(self):
        dispatch = EngineState.dispatch

        def old_dispatch(engine, vm, **kwargs):
            if vm.pending.yield_id == 100:
                return EngineAction('unhandled_yield', vm.pending, False)
            return dispatch(engine, vm, **kwargs)

        cases = ((0, {}, 5375, 'presentation'),
                 (1, {1: 1}, 135, 'finished'),
                 (1, {1: 0, 2: 0}, 725, 'dialogue'),
                 (1, {1: 0, 2: 1}, 734, 'dialogue'))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'library'
            import_game(LOCAL_COD_IPA, LOCAL_PROMOTION_EPISODES, root, game='cod')
            with ContentLibrary(root) as library:
                for episode, choices, pc, continuation in cases:
                    with self.subTest(episode=episode, choices=choices):
                        s = Session(library.open_episode(LOCAL_PROMOTION_EPISODES[episode].name))
                        choice_count = 0
                        with patch.object(EngineState, 'dispatch', old_dispatch):
                            action = s.advance()
                            for _ in range(1000):
                                if action.name == 'unhandled_yield':
                                    break
                                if action.name == 'choice':
                                    choice_count += 1
                                    first = next(i for i, on in enumerate(action.details['enabled']) if on)
                                    action = answer_screen(s, choices.get(choice_count, first))
                                else:
                                    self.assertIn(action.name, ('presentation', 'dialogue', 'vm_pause'))
                                    action = answer_screen(s)
                            else:
                                self.fail('Original promotion was not reached within the screen budget')
                        self.assertEqual((s.scene, action.request.yield_id, action.request.pc), (25001, 100, pc))
                        saved = json.loads(json.dumps(s.snapshot()))
                        restored = Session.from_snapshot(s.resources, saved)
                        self.assertEqual(json.loads(json.dumps(s.snapshot())), saved)
                        self.assertEqual(restored.pending.name, continuation)
                        self.assertEqual(Session.from_snapshot(restored.resources, restored.snapshot()).snapshot(),
                                         restored.snapshot())

    def test_query_results_and_version_write_preserve_other_state_and_extra_words(self):
        cases = ((2, 2), (3, 6), (6, 0x7ff5), (9, 1), (10, 1),
                 (0, 0), (1, 0), (4, 0), (5, 0), (7, 0), (8, 0), (11, 0),
                 (12, 0), (32767, 0), (-1, 0), (-32768, 0))
        for dynamic in (False, True):
            for extra in ((), (432, -4)):
                for selector, expected in cases:
                    with self.subTest(dynamic=dynamic, extra=extra, selector=selector):
                        s = Session(resources(caller(70, (selector, *extra), dynamic=dynamic),
                                              version='Authored build 17'))
                        s.engine.dynamic_strings[0] = 'Old slot text'
                        s.engine.last_input = 'Player name'
                        s.engine.result_cells[0] = 31
                        before = copy.deepcopy(s.engine)
                        request = s.vm.run()
                        pc, steps = s.vm.pc, s.vm.steps_executed
                        with patch('socket.socket', side_effect=AssertionError('Store query attempted a connection')):
                            action = s.engine.dispatch(s.vm)
                        self.assertTrue(action.completed)
                        self.assertEqual(action.details, dict(result=expected, selector=selector))
                        self.assertIs(action.request, request)
                        self.assertEqual((s.vm.pc, s.vm.steps_executed), (pc, steps))
                        if selector == 6:
                            before.dynamic_strings[0] = 'Authored build 17'
                        self.assertEqual(s.engine, before)
                        self.assertEqual(s.vm.run().args, (77, expected))

    def test_zero_argument_query_uses_retained_selector_and_rejects_unknown_backing(self):
        for dynamic in (False, True):
            for selector, expected in ((0, 0), (2, 2), (6, 0x7ff5), (10, 1), (11, 0)):
                with self.subTest(dynamic=dynamic, selector=selector):
                    s = Session(resources(caller(70, dynamic=dynamic, retained=selector), version='Build'))
                    self.assertEqual(s.advance().request.args, (77, expected))
                    self.assertEqual(s.engine.dynamic_strings[0], 'Build' if selector == 6 else '')
            s = Session(resources(caller(70, dynamic=dynamic)))
            request = s.vm.run()
            before = s.vm.snapshot(), copy.deepcopy(s.engine)
            with self.assertRaisesRegex(VMError, 'uninitialized'):
                s.engine.dispatch(s.vm)
            self.assertIs(s.vm.pending, request)
            self.assertEqual((s.vm.snapshot(), s.engine), before)

    def test_version_query_without_bundle_metadata_stays_pending_in_session_and_trace(self):
        r = resources(caller(70, (6, 99)))
        # A short/display version does not substitute for CFBundleVersion.
        r.library.app_info = {'CFBundleShortVersionString': 'Display only'}
        s = Session(r); s.engine.dynamic_strings[0] = 'Keep this'
        self.assertEqual(s.advance().name, 'unhandled_yield')
        self.assertIn('CFBundleVersion', s.pending.details['reason'])
        before = s.snapshot()
        self.assertEqual(Session.from_snapshot(r, json.loads(json.dumps(before))).snapshot(), before)
        self.assertEqual(s.vm.stack, (77, 6, 99))
        self.assertEqual(s.engine.dynamic_strings[0], 'Keep this')
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'authored.exp'
            path.write_bytes(archive({1: metadata(), 25001: caller(70, (6,)).to_bytes()}))
            trace = trace_archive(path, game='cod')
            self.assertEqual(trace['status'], 'unhandled_yield')
            self.assertEqual(trace['events'][-1]['request']['args'], (6,))
            self.assertIn('CFBundleVersion', trace['events'][-1]['details']['reason'])

    def test_version_comes_from_retained_ipa_and_restores_as_context_not_saved_state(self):
        p = program(*host_call(70, 6), 0x32, *host_call(70, 6), 0x32, 0x33)
        episode = archive({1: metadata(), 25001: p.to_bytes()})
        for version in ('Authored build 17', '', None):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); source = root / 'game.ipa'; target = root / 'library'
                info = dict(CFBundleIdentifier='com.ea.causeofdeath.bv',
                            CFBundleShortVersionString='Display version')
                if version is not None:
                    info['CFBundleVersion'] = version
                make_cod_ipa(source, episode, info=info)
                manifest = import_game(source, [], target, game='cod')
                # Informational manifest metadata is not the native source.
                manifest['ipa']['app']['CFBundleVersion'] = 'Wrong manifest version'
                (target / 'library.json').write_text(json.dumps(manifest))
                source.unlink()
                with ContentLibrary(target) as library:
                    r = library.open_episode('Volume_One.exp')
                    s = Session(r)
                    self.assertEqual(s.engine.app_version, version)
                    if version is None:
                        self.assertEqual(s.advance().name, 'unhandled_yield')
                        self.assertEqual(Session.from_snapshot(r, s.snapshot()).snapshot(), s.snapshot())
                        continue
                    self.assertEqual(s.advance().name, 'vm_pause')
                    self.assertEqual(s.vm.result, 0x7ff5)
                    self.assertEqual(s.engine.read_text(s.vm, s.vm.result), version)
                    # The returned handle remains live after its slot changes.
                    s.engine.dynamic_strings[0] = 'Later script text'
                    saved = json.loads(json.dumps(s.snapshot()))
                    self.assertNotIn('app_version', saved['engine'])
                    restored = Session.from_snapshot(r, saved)
                    self.assertEqual(json.loads(json.dumps(restored.snapshot())), saved)
                    self.assertEqual(restored.engine.read_text(restored.vm, restored.vm.result), 'Later script text')
                    self.assertEqual(restored.answer().name, 'vm_pause')
                    self.assertEqual(restored.engine.read_text(restored.vm, restored.vm.result), version)
                    bad = copy.deepcopy(saved); bad['engine']['app_version'] = 'Forged version'
                    with self.assertRaises(SaveError):
                        Session.from_snapshot(r, bad)

    def test_old_stops_resume_their_actual_frame_without_replaying_randomness(self):
        for service, args, result in ((70, (6,), 0x7ff5), (70, (10,), 1), (70, (11,), 0),
                                      (94, (), 0), (94, tuple(range(22)), 0),
                                      (96, (), 0), (96, tuple(range(20)), 0),
                                      (100, (), 0), (100, (32767, -1), 0)):
            with self.subTest(service=service, args=args):
                r = resources(program((0x1a, 77), *host_call(27, 100), *host_call(54, 901, 23),
                                      *host_call(service, *args), 0x21, (0x1f, 0xfe02)), version='Build')
                s = Session(r)
                while (request := s.vm.run()).yield_id != service:
                    self.assertTrue(s.engine.dispatch(s.vm).completed)
                s.pending = EngineAction('unhandled_yield', request, False)
                saved = json.loads(json.dumps(s.snapshot()))
                untouched = copy.deepcopy(saved)
                expected = copy.deepcopy(s.engine)
                if service == 70 and args[0] == 6:
                    expected.dynamic_strings[0] = 'Build'
                restored = Session.from_snapshot(r, saved)
                self.assertEqual(saved, untouched)
                self.assertEqual(restored.pending.request.args, (77, result))
                self.assertEqual(restored.engine, expected)
                self.assertEqual(restored.vm.steps_executed, s.vm.steps_executed + 2)
                self.assertEqual(Session.from_snapshot(r, restored.snapshot()).snapshot(), restored.snapshot())

    def test_old_stops_retain_previous_portrait_for_the_next_dialogue(self):
        words, refs = text_words('First reply.', 'Next reply.')
        for service, args in ((70, (10,)), (94, ()), (96, ()), (100, (0, -1))):
            with self.subTest(service=service):
                r = resources(program(*host_call(13, refs[0], 0), *host_call(service, *args),
                                      *host_call(13, refs[1], 0), 0x33, words=words))

                def start():
                    s = Session(r)
                    s.engine.character_names[0] = 'Alex'
                    s.engine.character_art_variants[0] = [100] * 5
                    s.advance()
                    return s

                old = start()
                dispatch = old.engine.dispatch

                def unsupported(vm, **kwargs):
                    if vm.pending.yield_id == service:
                        return EngineAction('unhandled_yield', vm.pending, False)
                    return dispatch(vm, **kwargs)

                with patch.object(old.engine, 'dispatch', side_effect=unsupported):
                    answer_screen(old)
                restored = Session.from_snapshot(r, old.snapshot())
                fresh = start()
                fresh.engine.random = copy.deepcopy(old.engine.random)
                answer_screen(fresh)
                self.assertEqual(restored.snapshot(), fresh.snapshot())
                self.assertFalse(restored.engine.dialogue_animation.changed)



class DisplayCharacterTests(unittest.TestCase):
    def test_the_truncated_quotes_show_as_apostrophes_and_scripts_keep_the_byte(self):
        # U+2019 stored as 0x19 (Volume 6 "You\x19re not Janice!"): the device draws a missing-glyph box (IMG_0513);
        # the owner chose to show the apostrophe. Display only.
        words, refs = text_words('You\x19re not Janice!')
        vm = KiwiVM(program(0x33, words=words))
        cod, shs = EngineState(), EngineState()
        cod.game_key = 'cod'
        self.assertEqual(cod.resolve_text(vm, refs[0]), "You're not Janice!")
        self.assertEqual(cod.read_text(vm, refs[0]), 'You\x19re not Janice!')
        self.assertEqual(cod.substitute('You\x19re', display=False), 'You\x19re')
        # SHS has the same truncated quotes (11_3_The_Endorsement: cupcakes that say "\x18BEN\x19") and shows them too.
        self.assertEqual(shs.resolve_text(vm, refs[0]), "You're not Janice!")
        self.assertEqual(shs.substitute('say \x18BEN\x19?'), "say 'BEN'?")

if __name__ == '__main__':
    unittest.main()
