"""Authored answer checks; no original episode text or assets."""
import json
from types import SimpleNamespace
import unittest

from exp_runtime.input_hints import preview_answer
from exp_runtime.runtime import Session
from test_runtime import Resources, host_call, text_words
from test_text_input import font
from test_vm import program


def answer_session(answers, *, default='Guess', service=40, otherwise=None, prefix=(), ending=()):
    """Each (spelling, body) takes its real equality branch or retries input."""
    words, refs = text_words('Answer', 'Enter the code', default, *(text for text, _ in answers))
    scratch = len(words)
    words.extend([0] * 20)
    code = [*prefix, *host_call(service, *refs[:3]), *host_call(28, scratch)]
    for ref, (_, body) in zip(refs[3:], answers):
        code += [*host_call(24, scratch, ref), 0x21, (0x2b, len(body) + len(ending) + 2),
                 *body, *ending, 0x33]
    code += list(otherwise) if otherwise is not None else [(0x29, len(prefix))]
    resources = Resources(program(*code, words=words))
    resources.library.game_id = 'cod'
    session = Session(resources)
    session.advance()
    return session


class InputHintTests(unittest.TestCase):
    def test_both_services_skip_wrong_guesses_and_preserve_the_entire_session(self):
        for service in (17, 40):
            session = answer_session([
                ('Quartz', host_call(79, 8001)),
                ('Cedar', host_call(27, 10) + host_call(82) + host_call(79, 8002)),
            ], service=service, otherwise=host_call(79, 8001) + [0x33])
            session.pending.details['draft'] = 'My guess'
            session.engine.random.state = 135
            before = json.loads(json.dumps(session.snapshot()))
            action, sounds, vibrations = session.pending, session.engine.sound_serial, session._vibrations
            self.assertEqual(preview_answer(session), 'Cedar')
            self.assertEqual(json.loads(json.dumps(session.snapshot())), before)
            self.assertIs(session.pending, action)
            self.assertEqual((session.engine.sound_serial, session._vibrations), (sounds, vibrations))
            restored = Session.from_snapshot(session.resources, before)
            self.assertEqual(preview_answer(restored), 'Cedar')

    def test_only_playable_exact_spellings_are_suggested(self):
        success = host_call(79, 8002)
        session = answer_session([(text, success) for text in
                                  ('a' * 17, 'Blue-door', 'blue door', 'Blue door', 'BLUE DOOR')])
        self.assertEqual(preview_answer(session), 'Blue door')
        # The same font/advance limit used by real entry applies to hints.
        session.resources.dialogue_layout = lambda: SimpleNamespace(font=lambda _: font(40))
        self.assertIsNone(preview_answer(session))

    def test_free_names_easter_eggs_and_unrelated_comparisons_have_no_answer(self):
        for game in ('cod', 'shs'):
            session = answer_session([('Studio', ())], otherwise=[0x33])
            session.engine.game_key = game
            self.assertIsNone(preview_answer(session))
        words, refs = text_words('Name', 'Choose a name', '', 'ExpHintA', 'Cedar')
        # Comparing two constants must not turn a free-form name into a puzzle.
        p = program(*host_call(40, *refs[:3]), *host_call(24, *refs[3:]),
                    0x21, (0x2b, 3), *host_call(79, 8002), 0x33, words=words)
        r = Resources(p); r.library.game_id = 'cod'
        session = Session(r); session.advance()
        self.assertIsNone(preview_answer(session))
        self.assertIsNone(preview_answer(Session(r)))

    def test_silent_retry_acceptance_requires_one_unambiguous_continuation(self):
        # Two accepted spellings jump to the very same continuation.
        session = answer_session([('Cedar', [(0x29, 100)]), ('CEDAR', [(0x29, 100)])])
        p = session.resources.program(25001)
        code = [(op.opcode, op.operand) if op.operand is not None else op.opcode for op in p.instructions]
        code += [0x33] * (101 - len(code))
        session.resources.programs[25001] = program(*code, words=p.main_words)
        session = Session(session.resources); session.advance()
        self.assertEqual(preview_answer(session), 'Cedar')
        # A separate silent branch may be a story-corrected wrong answer.
        ambiguous = answer_session([('Quartz', ()), ('Cedar', ())])
        self.assertIsNone(preview_answer(ambiguous))

    def test_common_later_feedback_does_not_hide_the_actual_answer(self):
        common = host_call(79, 8001)
        session = answer_session([('Cedar', host_call(79, 8002))],
                                 ending=common, otherwise=common + [0x33])
        self.assertEqual(preview_answer(session), 'Cedar')
        # Conversely a later common reward cannot make a special name correct.
        session = answer_session([('Studio', ())], ending=host_call(79, 8002),
                                 otherwise=host_call(79, 8002) + [0x33])
        self.assertIsNone(preview_answer(session))

    def test_unknown_services_and_execution_limits_never_guess(self):
        for body in (host_call(254), host_call(79, 8002) + host_call(254), [(0x28, 0)]):
            session = answer_session([('Cedar', body)], otherwise=[0x33])
            before = session.snapshot()
            self.assertIsNone(preview_answer(session, max_steps=100))
            self.assertEqual(session.snapshot(), before)
        session = answer_session([('Cedar', host_call(79, 8002)), ('Fir', host_call(79, 8002))])
        self.assertIsNone(preview_answer(session, max_steps=1))
        self.assertIsNone(preview_answer(session, max_candidates=1))
        with self.assertRaises(ValueError):
            preview_answer(session, max_panels=0)

    def test_native_transition_and_pause_keep_the_callback_and_observer(self):
        session = answer_session([('Cedar', [0x34, *host_call(79, 8002)])],
                                 prefix=host_call(16, 6), otherwise=[0x33])
        self.assertEqual(preview_answer(session), 'Cedar')
        self.assertTrue(session.engine.scene_value)


class InputHintRenderingTests(unittest.TestCase):
    def test_shared_ipa_rendering_uses_faint_empty_field_only_and_never_submits(self):
        from exp_runtime import graphics
        from exp_runtime.desktop_input import InputRenderer
        from exp_runtime.desktop_text import BitmapTextRenderer
        from exp_runtime.platforms import drawing as d
        from exp_runtime.ui_assets import Rect
        from unittest.mock import patch

        backend = d.Backend(None, None)
        previous = graphics.install(backend)
        self.addCleanup(graphics.install, previous)
        session = answer_session([('Cedar', host_call(79, 8002))])
        regions = {18: Rect(20, 10, 260, 35), 9: Rect(20, 10, 260, 35),
                   23: Rect(20, 60, 260, 35), 44: Rect(30, 180, 245, 29)}
        bank = SimpleNamespace(layouts={46: SimpleNamespace(width=280, height=120)},
                               rectangle=lambda layout, node, *args: regions[node], walk=lambda *args: ())
        resources = session.resources
        resources.library.kind = 'ipa'
        resources.dialogue_layout = lambda: SimpleNamespace(bank=bank, font=lambda _: font())
        text = BitmapTextRenderer(resources)
        atlas = d.Surface((3, 7), d.SRCALPHA); atlas.fill((255, 255, 255))
        for name in ('ArialRoundedMTBold16', 'ArialRoundedMTBold30', 'PajamaHip24'):
            text.fonts[name] = font(), atlas
        art = SimpleNamespace(draw_background=lambda canvas, _: canvas.fill((0, 0, 0)))
        renderer = InputRenderer(resources, text, art)
        target = d.Surface((320, 480))

        def entry():
            return d.raster(target.snapshot()).crop((30, 180, 275, 209))

        with patch('exp_runtime.desktop_input.preview_answer', wraps=preview_answer) as lookup:
            renderer.draw(target, session, choice_hints=True, cursor_visible=False)
            lookup.assert_not_called()  # Keep the script's default visible.
            session.pending.details['draft'] = ''
            before = session.snapshot()
            renderer.draw(target, session, cursor_visible=False)
            empty = entry().tobytes()
            lookup.assert_not_called()  # Off by default, including computation.
            renderer.draw(target, session, choice_hints=True, cursor_visible=False)
            faint = entry()
            self.assertNotEqual(faint.tobytes(), empty)
            self.assertEqual(faint.getextrema()[0], (0, 96))
            self.assertEqual(session.snapshot(), before)
            session.tick(50)
            renderer.draw(target, session, choice_hints=True, cursor_visible=False)
            self.assertEqual(lookup.call_count, 1)
            session.pending.details['draft'] = 'C'
            renderer.draw(target, session, choice_hints=True, cursor_visible=False)
            typed = entry().tobytes()
            renderer.draw(target, session, choice_hints=False, cursor_visible=False)
            self.assertEqual(entry().tobytes(), typed)
            session.pending.details['draft'] = ''
            renderer.draw(target, session, choice_hints=True, cursor_visible=False)
            self.assertEqual(entry().tobytes(), faint.tobytes())
            self.assertEqual(lookup.call_count, 1)
            with self.assertRaises(ValueError):
                session.answer('')
            self.assertEqual(session.engine.last_input, '')
