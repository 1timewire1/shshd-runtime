"""Recovered SHS defaults and named dialogue, using authored bytecode."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from exp_runtime.engine import EngineAction, EngineState
from exp_runtime.content import ContentLibrary, import_game
from exp_runtime.runtime import SaveError, Session
from exp_runtime.vm import KiwiVM, VMError
from test_named_dialogue import resources, sequence
from test_runtime import Resources, answer_screen, host_call, text_words
from test_vm import program


ORIGINAL_SHS_PACKAGES = tuple(Path('decomp/shs') / name for name in (
    'surviving-high-school-1-0-9.apk', 'SurvivingHighSchoolPaid1.4.2.ipa'))
ORIGINAL_NAMED_CALLS = (
    (Path('decomp/shs/Episodes/10_4_The_Spartan_Games_Part_2.exp'), 25002, 153, 156, 4),
    (Path('decomp/shs/Episodes/20_Party_Fowl.exp'), 25004, 219, 223, 5),
)


class ShsServiceTests(unittest.TestCase):
    def test_named_dialogue_prefixes_extra_words_and_both_call_encodings(self):
        for prefix in ((), (-1,), (-2,), (-3,), (-32768,)):
            for dynamic in (False, True):
                for extra in ((), (-1, 27, -1, 99)):
                    with self.subTest(prefix=prefix, dynamic=dynamic, extra=extra):
                        s = Session(resources(service=15, prefix=prefix, dynamic=dynamic, extra=extra))
                        s.engine.strings = {'$GROUP': 'class', '$PLAYER': 'Alex'}
                        s.engine.result_cells[0] = 42
                        action = s.advance()
                        self.assertEqual((action.name, action.details['speaker'], action.details['text']),
                                         ('dialogue', 'The class', 'We agree with Alex.'))
                        self.assertEqual((action.details['mode'], action.details['presentation_mode'],
                                          action.details['visible_character_id'], action.details['theme'],
                                          action.details['relationship']), (0, 3, -1, -1, None))
                        self.assertIsNone(s.dialogue_page().portrait)
                        held = s.vm.snapshot()
                        self.assertIs(s.answer(), action)  # Reveal, do not acknowledge the call yet.
                        self.assertEqual(s.vm.snapshot(), held)
                        s.tick(1000)
                        self.assertEqual(Session.from_snapshot(s.resources, s.snapshot()).snapshot(), s.snapshot())
                        self.assertEqual(s.answer().request.args, (77, 0))
                        self.assertEqual(s.engine.result_cells[0], 42)

    def test_named_dialogue_dynamic_empty_strings_pagination_and_saved_prefix_validation(self):
        for prefix in ((), (-3,)):
            s = Session(resources(service=15, prefix=prefix, text='A long reply from the group. ' * 35))
            s.advance(); s.tick(400)
            pages = 0
            held = s.vm.snapshot()
            while s.pending.name == 'dialogue':
                saved = json.loads(json.dumps(s.snapshot()))
                s = Session.from_snapshot(s.resources, saved)
                self.assertEqual(json.loads(json.dumps(s.snapshot())), saved)
                self.assertEqual(s.vm.snapshot(), held)
                answer_screen(s)
                pages += 1
            self.assertGreater(pages, 2)
            self.assertEqual(s.pending.request.args, (77, 0))
        r = Resources(program(*host_call(15, -3, -1, 0x7ff5),
                              *host_call(15, 0x7ff6, -1, 111), 0x33))
        s = Session(r); s.engine.dynamic_strings[:2] = ['A $WORD.', 'A voice']
        s.engine.strings['$WORD'] = 'reply'
        s.advance()
        self.assertEqual((s.pending.details['speaker'], s.pending.details['text']), ('', 'A reply.'))
        answer_screen(s)
        self.assertEqual((s.pending.details['speaker'], s.pending.details['text']), ('A voice', ''))
        self.assertEqual(answer_screen(s).name, 'finished')
        s = Session(resources(service=15, prefix=(-3,)))
        s.advance(); saved = s.snapshot()
        for key, value in (('speaker', 'Wrong name'), ('raw_text', 'Wrong body'),
                           ('mode', -3), ('presentation_mode', 4)):
            bad = copy.deepcopy(saved); bad['pending']['details'][key] = value
            with self.subTest(key=key), self.assertRaises(SaveError):
                Session.from_snapshot(s.resources, bad)

    def test_named_dialogue_old_stops_retain_portrait_and_continue_without_replay(self):
        for prefix in ((), (-3,)):
            original = sequence(service=15, prefix=prefix)
            dispatch = original.engine.dispatch

            def old_dispatch(vm, **kwargs):
                if vm.pending.yield_id == 15:
                    return EngineAction('unhandled_yield', vm.pending, False)
                return dispatch(vm, **kwargs)

            with patch.object(original.engine, 'dispatch', side_effect=old_dispatch):
                answer_screen(original)
            saved = json.loads(json.dumps(original.snapshot()))
            restored = Session.from_snapshot(original.resources, saved)
            fresh = sequence(service=15, prefix=prefix); answer_screen(fresh)
            self.assertEqual(restored.snapshot(), fresh.snapshot())
            self.assertEqual(restored.vm.snapshot(), original.vm.snapshot())
            self.assertEqual(saved, json.loads(json.dumps(original.snapshot())))
            self.assertEqual(restored.engine.dialogue_animation.previous.character_id, 1)
            self.assertEqual(restored.engine.dialogue_animation.wobble_direction, -20)
            answer_screen(restored)
            self.assertFalse(restored.engine.dialogue_animation.changed)
            self.assertEqual(restored.pending.details['speaker'], 'Another group')
            answer_screen(restored)
            self.assertEqual(restored.engine.dialogue_animation.portrait.character_id, 1)

    def test_named_dialogue_bad_frames_leave_the_original_request_and_panel_intact(self):
        for args in ((), (0,), (-3,), (-3, 0), (-3, 0, 9999)):
            vm = KiwiVM(program(*host_call(15, *args), words=(0,)))
            request = vm.run(); before = vm.snapshot(); engine = EngineState()
            unchanged = copy.deepcopy(engine)
            with self.subTest(args=args), self.assertRaises(VMError):
                engine.dispatch(vm)
            self.assertIs(vm.pending, request)
            self.assertEqual(vm.snapshot(), before)
            self.assertEqual(engine, unchanged)

    def test_native_defaults_preserve_state_and_pop_only_the_actual_frame(self):
        for service in (14, 21):
            for args in ((), (32767,), (0, -1), (123, 32767, -3, -1)):
                for dynamic in (False, True):
                    with self.subTest(service=service, args=args, dynamic=dynamic):
                        call = ([(0x1a, v) for v in args] + [(0x20, len(args)), (0x1e, service)]
                                if dynamic else host_call(service, *args))
                        vm = KiwiVM(program((0x1a, 77), *call, 0x21, (0x1f, 0xfe02)))
                        engine = EngineState()
                        engine.numbers[123] = 19; engine.result_cells[0] = 42
                        engine.panel.speaker = 'Retained speaker'
                        engine.next_dialogue_notice = 'Retained notice'
                        engine.scene_value = 20
                        before = copy.deepcopy(engine)
                        request = vm.run()
                        pc, steps = vm.pc, vm.steps_executed
                        action = engine.dispatch(vm)
                        self.assertIs(action.request, request)
                        self.assertEqual((action.name, action.completed, action.details),
                                         ('native_noop', True, {'result': 0}))
                        self.assertEqual(engine, before)
                        self.assertEqual((vm.pc, vm.steps_executed), (pc, steps))
                        self.assertEqual(vm.run().args, (77, 0))
        # These are explicit SHS cases, not a blanket fallback for any game.
        # (This fork's SHS follows HD's syscall table, where 12, 19 and 100 take the default case and 101
        # enables the Decision Tree.)
        for game, services in (('cod', (14, 21)),):
            for service in services:
                vm = KiwiVM(program(*host_call(service, 123, -1)))
                vm.run(); before = vm.snapshot(); engine = EngineState(); engine.game_key = game
                self.assertEqual(engine.dispatch(vm).name, 'unhandled_yield')
                self.assertEqual(vm.snapshot(), before)

    def test_native_default_old_stops_restore_outgoing_portrait_and_execute_once(self):
        words, refs = text_words('Before.', 'After.')
        for service in (14, 21):
            r = Resources(program(*host_call(13, refs[0], 1), *host_call(27, 100),
                                  *host_call(service, 32767, -1), *host_call(13, refs[1], 1),
                                  0x33, words=words))
            s = Session(r); s.engine.character_art_variants[1] = [100] * 5
            s.advance()
            dispatch = s.engine.dispatch

            def old_dispatch(vm, **kwargs):
                if vm.pending.yield_id == service:
                    return EngineAction('unhandled_yield', vm.pending, False)
                return dispatch(vm, **kwargs)

            with patch.object(s.engine, 'dispatch', side_effect=old_dispatch):
                answer_screen(s)
            before = json.loads(json.dumps(s.snapshot()))
            random, random48, steps = copy.deepcopy(s.engine.random), copy.deepcopy(s.engine.random48), s.vm.steps_executed
            restored = Session.from_snapshot(r, before)
            self.assertEqual(restored.pending.details['text'], 'After.')
            self.assertFalse(restored.engine.dialogue_animation.changed)
            self.assertEqual((restored.engine.random, restored.engine.random48), (random, random48))
            self.assertEqual(restored.vm.steps_executed, steps + 3)
            self.assertEqual(before, json.loads(json.dumps(s.snapshot())))
            self.assertEqual(Session.from_snapshot(r, restored.snapshot()).snapshot(), restored.snapshot())

    @unittest.skipUnless(importlib.util.find_spec('pygame') and
                         all(p.is_file() for p in ORIGINAL_SHS_PACKAGES) and
                         all(p.is_file() for p, *_ in ORIGINAL_NAMED_CALLS),
                         'original user SHS packages/episodes or desktop extra are unavailable')
    def test_original_named_calls_render_and_restore_with_apk_and_ipa_assets(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        from exp_runtime.desktop import Desktop
        self.addCleanup(pygame.quit)
        dispatch = EngineState.dispatch

        def old_dispatch(engine, vm, **kwargs):
            if vm.pending.yield_id == 15:
                return EngineAction('unhandled_yield', vm.pending, False)
            return dispatch(engine, vm, **kwargs)

        for source in ORIGINAL_SHS_PACKAGES:
            with tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary) / 'library'
                import_game(source, [p for p, *_ in ORIGINAL_NAMED_CALLS], directory, game='shs')
                with ContentLibrary(directory) as library:
                    for path, scene, start, pc, count in ORIGINAL_NAMED_CALLS:
                        with self.subTest(source=source.suffix, episode=path.name):
                            r = library.open_episode(path.name)
                            # Isolate original argument pushes and call, not a full route.
                            s = Session(r, start_script=scene); s.vm.pc = start
                            with patch.object(EngineState, 'dispatch', old_dispatch):
                                action = s.advance()
                            self.assertEqual((action.request.yield_id, action.request.pc, len(action.request.args)),
                                             (15, pc, count))
                            before = s.vm.snapshot(), copy.deepcopy(s.engine.random), copy.deepcopy(s.engine.random48)
                            s = Session.from_snapshot(r, s.snapshot())
                            self.assertEqual((s.vm.snapshot(), s.engine.random, s.engine.random48), before)
                            self.assertEqual((s.pending.name, s.pending.details['presentation_mode'],
                                              s.pending.details['mode']), ('dialogue', 3, 0))
                            ui = Desktop(s, audio=False); s.tick(4000); ui.render()
                            self.assertIsNone(ui.error)
                            pixels = pygame.image.tobytes(ui.canvas, 'RGB')
                            ui.session = Session.from_snapshot(r, s.snapshot()); ui.render()
                            self.assertEqual(pygame.image.tobytes(ui.canvas, 'RGB'), pixels)
                            self.assertIsNone(s.dialogue_page().portrait)


if __name__ == '__main__':
    unittest.main()
