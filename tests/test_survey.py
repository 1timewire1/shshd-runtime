import copy
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from exp_runtime.engine import EngineAction
from exp_runtime.content import ContentLibrary
from exp_runtime.runtime import SaveError, Session
from exp_runtime.shs.survey import CONNECTION_ERROR, SURVEY_TEXT
from exp_runtime.vm import VMError
from test_runtime import Resources, answer_screen, host_call, text_words
from test_vm import program


def resources(*, dynamic=False, upload_type=2, response=CONNECTION_ERROR, intervening=False):
    words, (error, story, results) = text_words(response, 'The story continues.', 'Server percentages')
    # Deliberately opaque unused fields and an untouched aggregate buffer.
    # Offline completion must not dereference or populate any of them.
    args = (1234, upload_type, -32768, 32767, -1, 30000, 4)
    call = ([(0x1a, a) for a in args] + [(0x20, len(args)), (0x1e, 9)]
            if dynamic else host_call(9, *args))
    code = [(0x1a, 77), *call]
    if intervening:
        code += host_call(27, 100)
    code += [0x21, 0x5b, 0x0a]
    branch = len(code)
    code += [(0x2b, 0)]
    # A fabricated success would expose a results screen, then an unknown
    # service. Neither may execute during offline survey completion.
    code += host_call(65, -1, results, 0) + host_call(254, 999)
    jump = len(code)
    code += [(0x28, 0)]
    failure = len(code)
    code += host_call(65, -1, error, 0)
    join = len(code)
    code += host_call(54, 900, 1234) + host_call(13, story, -1) + host_call(63)
    code[branch] = (0x2b, failure - branch)
    code[jump] = (0x28, join - jump)
    return Resources(program(*code, words=words))


def original_survey(r):
    """Enter the original caller of an episode's isolated survey routine."""
    scene = next(scene for scene in r.record['scripts']
                 if any(i.yield_id == 9 for i in r.program(scene).instructions))
    p = r.program(scene)
    submission = next(i.pc for i in p.instructions if i.yield_id == 9)
    entry = max(i.pc for i in p.instructions[:submission]
                if i.opcode == 0x48 and p.instructions[i.pc + 1].opcode == 0x4a)
    caller = next(i.pc for i in p.instructions[:-1]
                  if i.opcode == 0x42 and p.instructions[i.pc + 1].branch_target() == entry)
    s = Session(r, start_script=scene)
    # Execute the real call/prologue and choices; do not construct its frame,
    # patch bytecode, fill answers, or fabricate aggregate percentages.
    s.vm.pc = caller
    s.advance()
    return s


class SurveyTests(unittest.TestCase):
    def test_local_receipt_holds_submission_and_continues_original_story_without_network(self):
        for dynamic in (False, True):
            with self.subTest(dynamic=dynamic), \
                    patch('socket.socket', side_effect=AssertionError('Survey attempted a connection')):
                r = resources(dynamic=dynamic); s = Session(r)
                s.engine.result_cells[0] = 42
                random = s.engine.random.state, s.engine.random48.state
                before_data = s.vm.data.copy()
                action = s.advance()
                self.assertEqual(action.name, 'survey_confirmation')
                self.assertEqual(action.request.yield_id, 9)
                self.assertEqual(s.engine.message_panel.text, SURVEY_TEXT)
                held = s.vm.snapshot()
                self.assertIs(s.answer(), action)
                with self.assertRaises(ValueError):
                    s.answer(1)
                s.tick(999); self.assertIs(s.answer(), action)
                self.assertEqual(s.vm.snapshot(), held)
                self.assertEqual((s.engine.random.state, s.engine.random48.state), random)
                s.tick(1)
                next_action = s.answer()
                self.assertFalse(s.episode_exited)
                self.assertEqual(next_action.name, 'dialogue')
                self.assertEqual(next_action.details['text'], 'The story continues.')
                self.assertEqual(s.engine.numbers[900], 1234)
                self.assertEqual(s.engine.result_cells[0], 42)
                self.assertEqual(s.vm.data, before_data)
                self.assertEqual(s.vm.stack, (77, *next_action.request.args))
                self.assertEqual((s.engine.random.state, s.engine.random48.state), random)
                self.assertIsNone(s.engine.message_panel)
                self.assertEqual(answer_screen(s).name, 'episode_exit')

    def test_save_restores_reading_gate_frame_and_single_transition_callback(self):
        for age in (0, 500, 1000):
            r = resources(); s = Session(r)
            s.engine.scene_value = 20
            random = copy.deepcopy(s.engine.random48)
            s.advance(); s.tick(age)
            before = s.snapshot()
            saved = json.loads(json.dumps(before))
            original = copy.deepcopy(saved)
            s = Session.from_snapshot(r, saved)
            self.assertEqual(saved, original)
            self.assertEqual(s.snapshot(), before)
            self.assertEqual(s.engine.message_panel.elapsed_ms, age)
            s.tick(1000 - age); s.answer()
            random.next()  # Exactly the original response-dialogue callback.
            self.assertEqual(s.engine.random48, random)
            self.assertEqual(s.engine.scene_value, 0)
            s.tick(0)
            self.assertEqual(s.pending.details['text'], 'The story continues.')
            self.assertEqual(Session.from_snapshot(r, s.snapshot()).snapshot(), s.snapshot())

    def test_old_unsupported_submission_recovers_without_replaying_answers(self):
        for version in (8, 12, 13):
            r = resources(); s = Session(r)
            request = s.vm.run()
            s.pending = EngineAction('unhandled_yield', request, False)
            s.engine.result_cells[0] = 3
            saved = json.loads(json.dumps(s.snapshot()))
            saved['version'] = version
            if version < 9:
                del saved['engine']['message_panel']
            original = copy.deepcopy(saved)
            restored = Session.from_snapshot(r, saved)
            self.assertEqual(saved, original)
            self.assertEqual(restored.pending.name, 'survey_confirmation')
            self.assertEqual(restored.vm.snapshot(), s.vm.snapshot())
            self.assertEqual(restored.engine.random, s.engine.random)
            self.assertEqual(restored.engine.random48, s.engine.random48)
            self.assertEqual(restored.engine.result_cells[0], 3)
            restored.tick(1000)
            self.assertEqual(restored.answer().details['text'], 'The story continues.')

    def test_unfamiliar_uploads_or_continuations_remain_explicit_stops(self):
        for kwargs in ({'upload_type': 1}, {'response': 'A remaining story line.'}, {'intervening': True}):
            r = resources(**kwargs); s = Session(r)
            s.vm.run()
            held = s.vm.snapshot()
            random = s.engine.random.state, s.engine.random48.state
            # This fork treats them as HD's poll download (shs/services.py), not an unsupported stop.
            self.assertEqual(s.advance().name, 'download_poll')
            self.assertEqual(s.vm.snapshot(), held)
            self.assertEqual((s.engine.random.state, s.engine.random48.state), random)
            self.assertIsNone(s.engine.message_panel)
            restored = Session.from_snapshot(r, s.snapshot())
            self.assertEqual(restored.pending.name, 'download_poll')
            self.assertEqual(restored.vm.snapshot(), held)

    def test_missing_submission_arguments_and_unbounded_branches_do_not_mutate_vm(self):
        for code in (host_call(9, 1234), host_call(9, 1234, 2) + [(0x28, 0)]):
            r = Resources(program(*code))
            s = Session(r); s.vm.run()
            before = s.vm.snapshot()
            # Neither is a verified survey, so this fork waits on HD's poll download (shs/services.py).
            self.assertEqual(s.advance().name, 'download_poll')
            self.assertEqual(s.vm.snapshot(), before)
            self.assertIsNone(s.engine.message_panel)

    def test_invalid_confirmation_saves_and_false_terminal_state_are_rejected(self):
        r = resources(); s = Session(r); s.advance()
        changes = [(('version',), 12), (('pending', 'name'), 'episode_exit'),
                   (('pending', 'details', 'response_pc'), 0),
                   (('engine', 'message_panel'), None),
                   (('engine', 'message_panel', 'title'), 'Changed'),
                   (('engine', 'message_panel', 'text'), 'Changed'),
                   (('engine', 'message_panel', 'argument'), 1),
                   (('engine', 'message_panel', 'elapsed_ms'), 1001)]
        for path, value in changes:
            saved = s.snapshot(); target = saved
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            original = copy.deepcopy(saved)
            with self.subTest(path=path), self.assertRaises(SaveError):
                Session.from_snapshot(r, saved)
            self.assertEqual(saved, original)

    @unittest.skipUnless(Path('.shs-library/library.json').is_file(), 'user content required')
    def test_original_surveys_allow_declining_and_recover_submission_without_skipping_the_ending(self):
        with ContentLibrary(Path('.shs-library')) as lib:
            for name, pc in (('44_Green_With_Kenji.exp', 882), ('10_1_300s_A_Crowd.exp', 559)):
                with self.subTest(episode=name):
                    if name not in {e['name'] for e in lib.episodes}:
                        self.skipTest(f'{name} unavailable')
                    r = lib.open_episode(name)
                    skipped = original_survey(r)
                    self.assertEqual(skipped.pending.name, 'choice')
                    self.assertEqual(answer_screen(skipped, 1).name, 'message_panel')
                    s = original_survey(r)
                    for _ in range(10):
                        if s.pending.name != 'choice':
                            break
                        answer_screen(s, 0)
                    self.assertEqual((s.pending.name, s.pending.request.pc), ('survey_confirmation', pc))
                    vm = s.vm.snapshot()
                    submitted_data = s.vm.data.copy()
                    old = s.snapshot(); old['version'] = 12
                    old['pending'] = dict(name='unhandled_yield', details={})
                    old['engine']['message_panel'] = None
                    original = copy.deepcopy(old)
                    s = Session.from_snapshot(r, json.loads(json.dumps(old)))
                    self.assertEqual(old, original)
                    self.assertEqual(s.vm.snapshot(), vm)
                    s.tick(500)
                    s = Session.from_snapshot(r, s.snapshot())
                    self.assertEqual(s.engine.message_panel.elapsed_ms, 500)
                    s.tick(500)
                    self.assertEqual(s.answer().name, 'message_panel')
                    self.assertFalse(s.episode_exited)
                    self.assertEqual(s.pending.request, skipped.pending.request)
                    self.assertEqual(s.vm.data, submitted_data)
                    self.assertEqual(s.engine.panel.text, SURVEY_TEXT)
                    s.tick(1000)
                    self.assertEqual(s.answer().name, 'episode_exit')

    @unittest.skipUnless(importlib.util.find_spec('pygame') and Path('.shs-library/library.json').is_file(),
                         'desktop extra and user content required')
    def test_receipt_render_pause_focus_input_gate_and_save_restore(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        from exp_runtime.desktop import Desktop
        self.addCleanup(pygame.quit)
        with ContentLibrary(Path('.shs-library')) as lib:
            r = lib.open_episode('44_Green_With_Kenji.exp')
            s = original_survey(r)
            for _ in range(10):
                if s.pending.name != 'choice':
                    break
                answer_screen(s, 0)
            ui = Desktop(s, audio=False)
            before = s.snapshot()
            ui.render(); self.assertIsNone(ui.error)
            self.assertEqual(s.snapshot(), before)
            pixels = pygame.image.tobytes(ui.canvas, 'RGB')
            ui.command(('continue',))  # Still behind the reading gate.
            ui.command(('menu',)); ui.tick(5000); ui.command(('resume',))
            ui.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST)); ui.tick(5000)
            ui.handle_event(pygame.event.Event(pygame.WINDOWFOCUSGAINED))
            self.assertEqual(s.snapshot(), before)
            ui.session = Session.from_snapshot(r, json.loads(json.dumps(before)))
            ui.render(); self.assertIsNone(ui.error)
            self.assertEqual(pygame.image.tobytes(ui.canvas, 'RGB'), pixels)
            for _ in range(10):
                ui.tick(100)
            ui.command(('continue',))
            self.assertIsNone(ui.error)
            self.assertEqual(ui.session.pending.name, 'message_panel')
            self.assertFalse(ui.session.episode_exited)


if __name__ == '__main__':
    unittest.main()
