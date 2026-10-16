import copy
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock

from exp_runtime.engine import EngineAction
from exp_runtime.runtime import SaveError, Session
from exp_runtime.vm import VMError
from test_runtime import Resources, answer_screen, host_call
from test_vm import program


def resources(*arguments, dynamic_count=False, retained=None):
    prefix = [(0x1a, 77)]
    if retained is not None:
        prefix += [(0x1a, retained), 0x15]  # Leave a known word above SP.
    call = ([(0x1a, arg) for arg in arguments] + [(0x20, len(arguments)), (0x1e, 91)]
            if dynamic_count else host_call(91, *arguments))
    return Resources(program(*prefix, *call, 0x21, (0x1f, 0xfe02), 0x33))


class LoadingTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
    def test_runner_uses_native_cadence_without_changing_loading_wait_or_saved_clock(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        from exp_runtime.desktop_loading import LoadingRenderer
        pygame.display.init()
        pygame.display.set_mode((320, 480))
        self.addCleanup(pygame.quit)
        for kind in ('apk', 'ipa'):
            with self.subTest(kind=kind):
                r = resources(1)
                r.library.game_id, r.library.kind = 'shs', kind
                session = Session(r)
                session.advance()
                frozen = session.vm.snapshot()
                frames = {}
                for index in range(23, 28):
                    frames[index] = pygame.Surface((8, 8))
                    frames[index].fill((index, 40, 80))
                art = Mock()
                art.frame.side_effect = lambda bank, index: frames[index]
                renderer = LoadingRenderer(r, None, art)
                renderer.panel = Mock(return_value=pygame.Surface((320, 480)))
                target = pygame.Surface((320, 480))
                timeline = ((0, 23), (69, 23), (70, 24), (139, 24), (140, 25),
                            (210, 26), (280, 27), (349, 27), (350, 23), (420, 24),
                            (1500, 24), (3000, 25)) if kind == 'ipa' else (
                            (0, 23), (70, 23), (499, 23), (500, 24), (1000, 25),
                            (1500, 26), (2000, 27), (2499, 27), (2500, 23), (3000, 24))
                for elapsed, expected in timeline:
                    session.tick(elapsed - session.engine.loading.elapsed_ms)
                    self.assertEqual(session.vm.snapshot(), frozen)
                    saved = session.snapshot()
                    session = Session.from_snapshot(r, saved)
                    for _ in range(2):
                        renderer.draw(target, session)
                        self.assertEqual(target.get_at((155, 317))[:3], (expected, 40, 80))
                        self.assertEqual(session.snapshot(), saved)
                self.assertEqual(session.tick(1).request.args, (77, 0))
                self.assertIsNone(session.engine.loading)

    def test_timer_gate_call_frame_return_and_save_for_both_argument_forms(self):
        for arguments, retained in (((), 0), ((), 407), ((), -1),
                                    ((0,), None), ((1,), None), ((-1,), None),
                                    ((0, 88), None), ((1, 88), None)):
            wait = bool(arguments[0] if arguments else retained)
            for dynamic in (False, True):
                with self.subTest(arguments=arguments, retained=retained, dynamic=dynamic):
                    r = resources(*arguments, dynamic_count=dynamic, retained=retained)
                    s = Session(r)
                    s.engine.result_cells[0] = 42
                    action = s.advance()
                    self.assertEqual(action.name, 'loading')
                    self.assertEqual(action.request.args, arguments)
                    self.assertEqual(s.vm.stack, (77, *arguments) if wait else (77,))
                    self.assertEqual(s.vm.pending, action.request if wait else None)
                    self.assertEqual(s.vm.result, -1 if wait else 0)
                    frozen = s.vm.snapshot()
                    with self.assertRaises(VMError):
                        s.answer()
                    self.assertEqual(s.vm.snapshot(), frozen)
                    s.tick(1500)
                    self.assertEqual(s.pending.name, 'loading')  # Ignored native constructor argument.
                    s = Session.from_snapshot(r, json.loads(json.dumps(s.snapshot())))
                    self.assertEqual(s.pending.request, action.request)
                    self.assertEqual(s.engine.loading.frame, 26)
                    s.tick(1500)
                    self.assertEqual(s.pending.name, 'loading')  # Strict >, not >=.
                    self.assertEqual(s.vm.snapshot(), frozen)
                    s = Session.from_snapshot(r, s.snapshot())
                    self.assertEqual(s.tick(1).request.args, (77, 0))
                    self.assertIsNone(s.engine.loading)
                    self.assertEqual(s.engine.result_cells[0], 42)
                    self.assertEqual(Session.from_snapshot(r, s.snapshot()).snapshot(), s.snapshot())

    def test_zero_argument_call_does_not_invent_an_uninitialized_wait_flag(self):
        for dynamic in (False, True):
            with self.subTest(dynamic=dynamic):
                s = Session(resources(dynamic_count=dynamic))
                request = s.vm.run()
                before = s.vm.snapshot()
                with self.assertRaisesRegex(VMError, 'uninitialized stack word'):
                    s.advance()
                self.assertEqual(s.vm.pending, request)
                self.assertEqual(s.vm.snapshot(), before)
                self.assertIsNone(s.engine.loading)

    def test_old_unsupported_checkpoint_upgrades_without_replaying_script(self):
        for arguments, retained in (((0,), None), ((1,), None), ((), 0), ((), 407)):
            r = resources(*arguments, retained=retained)
            s = Session(r)
            request = s.vm.run()
            s.pending = EngineAction('unhandled_yield', request, False)
            old = s.snapshot(); old['version'] = 5
            del old['engine']['loading']
            original = copy.deepcopy(old)
            restored = Session.from_snapshot(r, old)
            self.assertEqual(old, original)
            self.assertEqual(restored.pending.name, 'loading')
            self.assertEqual(restored.vm.steps_executed, s.vm.steps_executed)
            self.assertEqual(restored.tick(3001).request.args, (77, 0))

    def test_saved_gate_rejects_invalid_timer_argument_and_completed_call(self):
        for argument in (0, 1):
            r = resources(argument)
            s = Session(r); s.advance()
            changes = [(('engine', 'loading', 'elapsed_ms'), -1),
                       (('engine', 'loading', 'elapsed_ms'), 3001),
                       (('engine', 'loading', 'elapsed_ms'), True),
                       (('engine', 'loading', 'blocking'), not bool(argument)),
                       (('engine', 'loading'), None), (('pending',), None)]
            if argument == 0:
                changes += [(('vm', 'result'), 1), (('vm', 'pc'), s.vm.pc + 1)]
            for path, value in changes:
                state = s.snapshot(); target = state
                for key in path[:-1]: target = target[key]
                target[path[-1]] = value
                with self.subTest(argument=argument, path=path), self.assertRaises(SaveError):
                    Session.from_snapshot(r, state)

    def test_zero_argument_save_checks_retained_word_and_register_count_metadata(self):
        for wait in (0, 407):
            for dynamic in (False, True):
                r = resources(dynamic_count=dynamic, retained=wait)
                s = Session(r); s.advance()
                changes = [(('vm', 'stack', s.vm.sp), None),
                           (('vm', 'stack', s.vm.sp), int(not wait)),
                           (('pending', 'details'), {'argument_count': 0, 'extra': 1})]
                if not wait and dynamic:
                    changes += [(('pending', 'details', 'argument_count'), count)
                                for count in (-1, True, 1024, 2)]
                for path, value in changes:
                    state = s.snapshot(); target = state
                    for key in path[:-1]: target = target[key]
                    target[path[-1]] = value
                    with self.subTest(wait=wait, dynamic=dynamic, path=path, value=value), self.assertRaises(SaveError):
                        Session.from_snapshot(r, state)

    @unittest.skipUnless(Path('.shs-library/library.json').is_file(), 'user content required')
    def test_new_girl_bundled_and_imported_loading_frames_resume_original_script(self):
        from exp_runtime.content import ContentLibrary
        with ContentLibrary(Path('.shs-library')) as lib:
            for selector, pc, args in (('The_New_Girl.exp', 60, ()), ('SHS_The_New_Girl.exp', 61, (1,))):
                with self.subTest(episode=selector):
                    if selector not in {entry['name'] for entry in lib.episodes}:
                        self.skipTest(f'{selector} unavailable')
                    r = lib.open_episode(selector)
                    s = Session(r); s.advance()
                    for _ in range(300):
                        action = s.pending
                        if action.name == 'loading':
                            break
                        if action.name == 'word_game':
                            s.tick(400)
                            for _ in range(10):
                                s.answer(s.engine.word_game.weights.index(1)); s.tick(500)
                            s.tick(s.engine.word_game.remaining_ms + 1)
                        elif action.name == 'text_input':
                            s.answer('Alex')
                        elif action.name == 'character_picker':
                            s.answer(0); s.tick(25); s.answer()
                        else:
                            self.assertIn(action.name, ('choice', 'dialogue', 'presentation', 'vm_pause'))
                            answer_screen(s, 0 if action.name == 'choice' else None)
                    self.assertEqual((s.scene, s.pending.name, s.pending.request.pc,
                                      s.pending.request.args), (25004, 'loading', pc, args))
                    self.assertTrue(s.engine.loading.blocking)
                    if not args:
                        self.assertEqual(s.vm.read_word(s.vm.stack_base + s.vm.sp), 407)
                    s.tick(1500)
                    restored = Session.from_snapshot(r, json.loads(json.dumps(s.snapshot())))
                    self.assertEqual(restored.snapshot(), s.snapshot())
                    before = s.vm.snapshot()
                    for branch in (s, restored):
                        branch.tick(1500)
                        self.assertEqual(branch.vm.snapshot(), before)
                        self.assertEqual(branch.tick(1).name, 'word_grid')
                        self.assertIsNone(branch.engine.loading)
                    self.assertEqual(restored.snapshot(), s.snapshot())

    @unittest.skipUnless(importlib.util.find_spec('pygame') and Path('.shs-library/library.json').is_file(),
                         'desktop extra and user content required')
    def test_original_frames_render_and_input_focus_pause_and_restore_preserve_timer(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        from exp_runtime.content import ContentLibrary
        from exp_runtime.desktop import Desktop
        self.addCleanup(pygame.quit)
        with ContentLibrary(Path('.shs-library')) as lib:
            r = lib.open_episode('Football Star')
            r.programs[25001] = resources(1).program(25001)
            ui = Desktop(Session(r), audio=False)
            ui.render(); self.assertIsNone(ui.error)
            first = pygame.image.tobytes(ui.canvas, 'RGB')
            # Desktop ticks are capped; a half second of active frames changes the icon.
            for _ in range(5): ui.tick(100)
            ui.render(); self.assertIsNone(ui.error)
            second = pygame.image.tobytes(ui.canvas, 'RGB')
            self.assertNotEqual(first, second)
            saved = ui.session.snapshot()
            ui.command(('continue',)); ui.command(('choose', 0))
            ui.command(('menu',)); ui.tick(5000); ui.command(('resume',))
            ui.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST)); ui.tick(5000)
            ui.handle_event(pygame.event.Event(pygame.WINDOWFOCUSGAINED))
            self.assertEqual(ui.session.snapshot(), saved)
            ui.session = Session.from_snapshot(r, saved)
            ui.render(); self.assertIsNone(ui.error)
            self.assertEqual(pygame.image.tobytes(ui.canvas, 'RGB'), second)
