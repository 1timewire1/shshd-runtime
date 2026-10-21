"""Authored service-33 calls; original-content checks remain optional."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import unittest

from exp_runtime.engine import EngineAction
from exp_runtime.message_panel import MessagePanel
from exp_runtime.runtime import SaveError, Session
from exp_runtime.vm import VMError
from test_runtime import Resources, host_call, text_words
from test_vm import program


def resources(argument=4000, *, dynamic=False, extra=()):
    words, refs = text_words('A $NAME', 'A literal $NAME\n\nSecond paragraph.')
    args = (*refs, argument, *extra)
    call = ([(0x1a, arg) for arg in args] + [(0x20, len(args)), (0x1e, 33)]
            if dynamic else host_call(33, *args))
    return Resources(program((0x1a, 77), *call, 0x21, (0x1f, 0xfe02), 0x33, words=words))


class MessagePanelTests(unittest.TestCase):
    def test_raw_text_frame_gate_and_zero_callback_for_both_call_encodings(self):
        for argument in (-1, 0, 4000, 32767):
            for dynamic in (False, True):
                with self.subTest(argument=argument, dynamic=dynamic):
                    r = resources(argument, dynamic=dynamic, extra=(99,))
                    s = Session(r)
                    s.engine.strings['$NAME'] = 'Replacement'
                    s.engine.result_cells[0] = 42
                    action = s.advance()
                    self.assertEqual(action.name, 'message_panel')
                    self.assertEqual(s.engine.message_panel.title, 'A $NAME')
                    self.assertIn('$NAME', s.engine.message_panel.text)
                    self.assertEqual(s.engine.message_panel.argument, argument)
                    self.assertEqual(s.vm.stack, (77, *action.request.args))
                    vm, random = s.vm.snapshot(), copy.deepcopy(s.engine.random48)
                    self.assertIs(s.answer(), action)
                    s.tick(999); self.assertIs(s.answer(), action)
                    self.assertEqual(s.vm.snapshot(), vm)
                    s.tick(1)
                    self.assertTrue(s.engine.message_panel.ready)
                    s.tick(100000)  # Never auto-dismiss; elapsed time is capped.
                    self.assertEqual(s.vm.snapshot(), vm)
                    self.assertEqual(s.answer().request.args, (77, 0))
                    self.assertIsNone(s.engine.message_panel)
                    self.assertEqual(s.engine.result_cells[0], 42)
                    self.assertEqual(s.engine.random48, random)
                    self.assertEqual(Session.from_snapshot(r, s.snapshot()).snapshot(), s.snapshot())

    def test_saved_reading_time_and_transition_randomness_are_resumed_once(self):
        for transition in (0, 1, 2, 20):
            for age in (0, 500, 999, 1000):
                with self.subTest(transition=transition, age=age):
                    r = resources(); s = Session(r)
                    s.engine.scene_value = transition
                    s.advance(); s.tick(age)
                    snapshot = json.loads(json.dumps(s.snapshot()))
                    saved = copy.deepcopy(snapshot)
                    restored = Session.from_snapshot(r, snapshot)
                    self.assertEqual(snapshot, saved)
                    self.assertEqual(json.loads(json.dumps(restored.snapshot())), saved)
                    random = copy.deepcopy(s.engine.random48)
                    if transition == 20:
                        random.next()
                    restored.tick(1000 - age)
                    restored.answer()
                    self.assertEqual(restored.engine.scene_value, 0)
                    self.assertEqual(restored.engine.random48, random)
                    if transition:
                        self.assertEqual(restored.pending.name, 'message_panel')
                        restored.tick(0)
                    self.assertEqual(restored.pending.request.args, (77, 0))

    def test_older_unsupported_stop_upgrades_without_replaying_vm_or_random(self):
        for version in (8, 9):
            r = resources(); s = Session(r)
            request = s.vm.run()
            s.pending = EngineAction('unhandled_yield', request, False)
            old = s.snapshot(); old['version'] = version
            if version < 9:
                del old['engine']['message_panel']
            original = copy.deepcopy(old)
            restored = Session.from_snapshot(r, old)
            self.assertEqual(old, original)
            self.assertEqual(restored.vm.snapshot(), s.vm.snapshot())
            self.assertEqual(restored.engine.random48, s.engine.random48)
            self.assertEqual(restored.pending.name, 'message_panel')
            self.assertFalse(restored.engine.message_panel.ready)
            restored.tick(1000)
            self.assertEqual(restored.answer().request.args, (77, 0))

    def test_saved_panel_rejects_mismatched_arguments_text_timer_and_screen(self):
        r = resources(); s = Session(r); s.advance()
        changes = [(('engine', 'message_panel', 'elapsed_ms'), value) for value in (-1, 1001, True, 1.5)]
        changes += [(('engine', 'message_panel', 'argument'), 9),
                    (('engine', 'message_panel', 'title'), 'Replaced'),
                    (('engine', 'message_panel', 'text'), 'Replaced'),
                    (('engine', 'message_panel'), None), (('pending',), None),
                    (('pending', 'name'), 'unhandled_yield'),
                    (('pending', 'details'), {'elapsed_ms': 1000})]
        for path, value in changes:
            state = s.snapshot(); target = state
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path, value=value), self.assertRaises(SaveError):
                Session.from_snapshot(r, state)

    def test_dynamic_and_empty_strings_bad_input_and_missing_arguments(self):
        r = Resources(program(*host_call(33, -1, 0x7ff5, -20), 0x33))
        s = Session(r); s.engine.dynamic_strings[0] = 'Dynamic\ntext'
        s.advance()
        self.assertEqual((s.engine.message_panel.title, s.engine.message_panel.text), ('', 'Dynamic\ntext'))
        snapshot = s.snapshot()
        with self.assertRaises(ValueError):
            s.answer(0)
        self.assertEqual(s.snapshot(), snapshot)
        for args in ((), (-1,), (-1, -1)):
            s = Session(Resources(program(*host_call(33, *args), 0x33)))
            with self.assertRaises(VMError):
                s.advance()
            self.assertEqual(s.vm.pending.args, args)
            self.assertIsNone(s.engine.message_panel)
        panel = MessagePanel('', '', 1)
        self.assertEqual(panel.countdown, 1)
        panel.tick(901)
        self.assertEqual(panel.countdown, 0)
        self.assertFalse(panel.ready)

    @unittest.skipUnless(importlib.util.find_spec('pygame') and Path('.shs-library/library.json').is_file(),
                         'desktop extra and user content required')
    def test_original_reported_call_renders_and_continues_to_word_game(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        from exp_runtime.content import ContentLibrary
        from exp_runtime.desktop import Desktop
        self.addCleanup(pygame.quit)
        with ContentLibrary(Path('.shs-library')) as lib:
            r = lib.open_episode('Football Star')
            s = Session(r, start_script=25011)
            # Run the three original PUSH instructions, then the reported call.
            # Full playthrough is checked separately with private local saves.
            s.vm.pc = 626
            s.engine.panel.background_id = 1051
            s.engine.scene_value = 20
            ui = Desktop(s, audio=False)
            ui.render(); self.assertIsNone(ui.error)
            self.assertEqual((s.pending.request.pc, s.pending.request.yield_id), (629, 33))
            self.assertEqual(s.engine.message_panel.title, 'Instructions')
            self.assertEqual(s.engine.message_panel.argument, 4000)
            ui.tick(500); ui.render()
            before = pygame.image.tobytes(ui.canvas, 'RGB')
            saved = s.snapshot()
            ui.command(('continue',))
            ui.command(('menu',)); ui.tick(5000); ui.command(('resume',))
            ui.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST)); ui.tick(5000)
            ui.handle_event(pygame.event.Event(pygame.WINDOWFOCUSGAINED))
            self.assertEqual(s.snapshot(), saved)
            ui.session = Session.from_snapshot(r, saved)
            ui.render(); self.assertEqual(pygame.image.tobytes(ui.canvas, 'RGB'), before)
            ui.tick(500); ui.render(); self.assertIsNone(ui.error)
            self.assertNotEqual(pygame.image.tobytes(ui.canvas, 'RGB'), before)
            # Any screen click acknowledges, except the gear's menu region.
            ui.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                              pos=ui.viewport.center))
            ui.tick(0)  # Native SHS defers its nonvisual callback to the next tick.
            self.assertEqual(ui.session.pending.name, 'word_game')
            self.assertEqual(ui.session.pending.request.pc, 638)
            self.assertIsNone(ui.session.engine.message_panel)
