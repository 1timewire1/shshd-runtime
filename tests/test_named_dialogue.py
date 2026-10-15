"""Service 76: authored group speakers and optional original call verification."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from exp_runtime.engine import EngineAction
from exp_runtime.runtime import SaveError, Session
from exp_runtime.vm import VMError
from test_label_layout import authored_dialogue
from test_runtime import Resources, answer_screen, host_call, text_words
from test_vm import program


def resources(speaker='The $GROUP', text='We agree with $PLAYER.', *, dynamic=False, extra=(),
              service=76, prefix=()):
    words, refs = text_words(speaker, text)
    args = (*prefix, *refs, *extra)
    call = ([(0x1a, a) for a in args] + [(0x20, len(args)), (0x1e, service)]
            if dynamic else host_call(service, *args))
    r = Resources(program((0x1a, 77), *call, 0x21, (0x1f, 0xfe02), 0x33, words=words))
    layout = authored_dialogue()
    r.dialogue_layout = lambda: layout
    return r


def sequence(*, service=76, prefix=()):
    words, refs = text_words('A question.', 'The group', 'Yes!', 'Another group',
                            'We agree.', 'A reply.')
    r = Resources(program(*host_call(27, 100), *host_call(13, refs[0], 1),
                          *host_call(89), *host_call(service, *prefix, refs[1], refs[2]),
                          *host_call(service, *prefix, refs[3], refs[4]), *host_call(13, refs[5], 1),
                          0x33, words=words))
    layout = authored_dialogue()
    r.dialogue_layout = lambda: layout
    s = Session(r)
    s.engine.random.state = 123
    s.engine.ui_defaults = {74: 0, 75: 7}
    s.engine.character_names[1] = 'Riley'
    s.engine.character_art_variants[1] = [100] * 5
    s.engine.numbers[s.engine.number_key(1, 651)] = 2
    s.engine.numbers[s.engine.number_key(1, 3001)] = -1
    s.advance()
    return s


class NamedDialogueTests(unittest.TestCase):
    def test_frame_substitution_mode_and_callback_preserve_game_state(self):
        for dynamic in (False, True):
            for extra in ((), (123, -4)):
                with self.subTest(dynamic=dynamic, extra=extra):
                    s = Session(resources(dynamic=dynamic, extra=extra))
                    s.engine.strings = {'$GROUP': 'class', '$PLAYER': 'Alex'}
                    s.engine.panel.background_id = 1042
                    s.engine.panel.emphasis_theme = 2
                    s.engine.character_names[1] = 'Original name'
                    s.engine.numbers[123] = 9
                    s.engine.result_cells[0] = 42
                    before = copy.deepcopy(s.engine)
                    action = s.advance()
                    d = action.details
                    self.assertEqual((action.name, d['speaker'], d['text']),
                                     ('dialogue', 'The class', 'We agree with Alex.'))
                    self.assertEqual((d['character_id'], d['visible_character_id'], d['expression'],
                                      d['mode'], d['presentation_mode'], d['theme'], d['relationship']),
                                     (-1, -1, 0, 0, 3, -1, None))
                    self.assertEqual(d['emphasis_theme'], 2)
                    self.assertEqual(s.engine.panel.background_id, 1042)
                    page = s.dialogue_page()
                    self.assertIsNone(page.portrait)
                    self.assertEqual((page.name_font, page.body_font),
                                     ('PajamaHipY26', 'ArialRoundedMTBold16'))
                    self.assertEqual(page.body.glyphs[0].x, 0)
                    held = s.vm.snapshot()
                    self.assertIs(s.answer(), action)
                    self.assertEqual(s.vm.snapshot(), held)
                    s.tick(1000)
                    self.assertEqual(s.vm.snapshot(), held)
                    self.assertEqual(s.answer().request.args, (77, 0))
                    for key in ('numbers', 'character_names', 'character_expressions',
                                'character_art_variants', 'result_cells', 'random', 'random48',
                                'sound_serial', 'strings'):
                        self.assertEqual(getattr(s.engine, key), getattr(before, key), key)

    def test_empty_and_dynamic_strings_are_names_not_character_ids(self):
        r = Resources(program(*host_call(76, -1, 0x7ff5),
                              *host_call(76, 0x7ff6, -1), 0x33))
        s = Session(r)
        s.engine.dynamic_strings[:2] = ['A $WORD.', 'A voice']
        s.engine.strings['$WORD'] = 'reply'
        s.advance()
        self.assertEqual((s.pending.details['speaker'], s.pending.details['text'],
                          s.pending.details['presentation_mode']), ('', 'A reply.', 3))
        answer_screen(s)
        self.assertEqual((s.pending.details['speaker'], s.pending.details['text']), ('A voice', ''))
        self.assertFalse(s.engine.dialogue_animation.changed)
        self.assertEqual(answer_screen(s).name, 'finished')

    def test_named_lines_use_shared_portrait_exit_name_fade_and_next_speaker_entry(self):
        s = sequence()
        answer_screen(s)
        motion = s.engine.dialogue_animation
        self.assertEqual((motion.previous.character_id, motion.previous.mode), (1, 2))
        self.assertIsNone(motion.portrait)
        self.assertIsNone(motion.relationship)
        self.assertEqual((motion.name_delay_ms, motion.text_delay_ms), (370, 650))
        self.assertEqual(motion.wobble_direction, -20)
        self.assertFalse(s.engine.next_dialogue_wobble)
        s.tick(150)
        self.assertEqual((motion.previous_scale, motion.name_alpha), (.5, 0))
        answer_screen(s)
        motion = s.engine.dialogue_animation
        self.assertEqual(s.pending.details['speaker'], 'Another group')
        self.assertFalse(motion.changed)  # Native compares character IDs, both -1.
        self.assertEqual((motion.name_alpha, motion.text_delay_ms), (255, 250))
        answer_screen(s)
        self.assertEqual(s.pending.details['speaker'], 'Riley')
        self.assertEqual(s.engine.dialogue_animation.portrait.character_id, 1)
        self.assertTrue(s.engine.dialogue_animation.changed)

    def test_pagination_and_mid_reveal_saves_keep_the_pending_frame(self):
        r = resources(text='A long reply from the assembled crowd. ' * 35)
        s = Session(r)
        s.advance()
        held = s.vm.snapshot()
        first_page = s.dialogue_page()
        self.assertLess(first_page.end, len(s.pending.details['text']))
        s.tick(600)
        restored = Session.from_snapshot(r, json.loads(json.dumps(s.snapshot())))
        self.assertEqual(restored.snapshot(), s.snapshot())
        name_state = copy.deepcopy(s.engine.speaker_names)
        pages = 0
        while s.pending.name == 'dialogue':
            s.tick(100000)
            self.assertEqual(s.vm.snapshot(), held)
            self.assertEqual(s.engine.speaker_names, name_state)
            s.answer()
            pages += 1
            if s.pending.name == 'dialogue':
                self.assertTrue(s.engine.dialogue_animation.page_turn)
                self.assertEqual(s.dialogue_page().name_origin, first_page.name_origin)
                s = Session.from_snapshot(r, s.snapshot())
        self.assertGreater(pages, 2)
        self.assertEqual(s.pending.request.args, (77, 0))

    def test_shared_transition_draw_occurs_once_after_the_last_dialogue_page(self):
        for service in (13, 15, 65, 76):
            for transition in (0, 3, 20):
                with self.subTest(service=service, transition=transition):
                    words, refs = text_words('A group', 'Many words in this reply. ' * 20)
                    args = {13: (refs[1], -1), 15: (-3, *refs), 65: (-1, refs[1], 0), 76: tuple(refs)}[service]
                    r = Resources(program(*host_call(16, transition), *host_call(service, *args),
                                          0x21, (0x1f, 0xfe01), words=words))
                    layout = authored_dialogue()
                    r.dialogue_layout = lambda: layout
                    s = Session(r)
                    s.engine.ui_defaults[75] = 7
                    s.advance()
                    random = copy.deepcopy(s.engine.random48)
                    while s.pending.name == 'dialogue':
                        self.assertEqual(s.engine.scene_value, transition)
                        self.assertEqual(s.engine.random48, random)
                        answer_screen(s)
                    if transition == 20:
                        random.next()
                    self.assertEqual(s.engine.random48, random)
                    self.assertEqual(s.engine.scene_value, 0)
                    self.assertEqual(s.pending.request.args, (0,))

    def test_unsupported_save_upgrades_once_using_retained_panel_without_vm_replay(self):
        original = sequence()
        dispatch = original.engine.dispatch

        def old_dispatch(vm, **kwargs):
            if vm.pending.yield_id == 76:
                return EngineAction('unhandled_yield', vm.pending, False)
            return dispatch(vm, **kwargs)

        with patch.object(original.engine, 'dispatch', side_effect=old_dispatch):
            answer_screen(original)
        fresh = sequence()
        answer_screen(fresh)
        self.assertIsNotNone(original.engine.dialogue_animation)
        for legacy in (False, True):
            saved = json.loads(json.dumps(original.snapshot()))
            if legacy:
                saved['version'] = 24          # shshd-runtime's last version before the v0.4.2 lifecycle
                saved['engine']['dialogue_animation'] = None  # Old unsupported stops discarded it.
                del saved['engine']['dialogue_history']
            untouched = copy.deepcopy(saved)
            restored = Session.from_snapshot(original.resources, saved)
            self.assertEqual(saved, untouched)
            self.assertEqual(restored.vm.snapshot(), original.vm.snapshot())
            self.assertEqual(restored.snapshot(), fresh.snapshot())
            self.assertEqual(Session.from_snapshot(original.resources, restored.snapshot()).snapshot(),
                             restored.snapshot())

    def test_bad_frames_inputs_and_mismatched_saved_text_stay_explicit_errors(self):
        for args in ((), (-1,)):
            s = Session(Resources(program(*host_call(76, *args))))
            with self.subTest(args=args), self.assertRaises(VMError):
                s.advance()
            self.assertEqual(s.vm.pending.args, args)
            self.assertEqual(s.engine.panel.presentation_mode, 0)
        s = Session(resources())
        s.advance()
        saved = s.snapshot()
        with self.assertRaises(ValueError):
            s.answer(1)
        self.assertEqual(s.snapshot(), saved)
        for key, value in (('speaker', 'Someone else'), ('raw_text', 'Changed'), ('text', 'Changed'),
                           ('presentation_mode', 4), ('character_id', 123), ('theme', 1)):
            bad = copy.deepcopy(saved)
            bad['pending']['details'][key] = value
            with self.subTest(key=key), self.assertRaises(SaveError):
                Session.from_snapshot(s.resources, bad)

    @unittest.skipUnless(importlib.util.find_spec('pygame') and Path('.shs-library/library.json').is_file(),
                         'desktop extra and user content required')
    def test_original_reported_frame_renders_and_reaches_the_following_coach_and_team_lines(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        from exp_runtime.content import ContentLibrary
        from exp_runtime.desktop import Desktop
        self.addCleanup(pygame.quit)
        with ContentLibrary(Path('.shs-library')) as library:
            s = Session(library.open_episode('Football Star'), start_script=25011)
            # Isolated inspection of the two original PUSHes and reported yield.
            # A private player save separately verifies the actual route here.
            s.vm.pc = 4301
            s.engine.ui_defaults[75] = 35
            s.engine.panel.background_id = 1068
            s.engine.character_names[12] = 'Coach'
            ui = Desktop(s, audio=False)
            self.assertEqual((s.pending.request.pc, s.pending.request.yield_id), (4303, 76))
            self.assertEqual(s.pending.details['speaker'], 'The team')
            self.assertEqual(s.engine.panel.speaker, 'Th e team')
            s.tick(500)
            ui.render()
            self.assertIsNone(ui.error)
            self.assertIsNone(s.dialogue_page().portrait)
            self.assertEqual(s.dialogue_page().name_font, 'PajamaHipY26')
            saved = s.snapshot()
            before = pygame.image.tobytes(ui.canvas, 'RGB')
            ui.session = Session.from_snapshot(s.resources, saved)
            ui.render()
            self.assertEqual(pygame.image.tobytes(ui.canvas, 'RGB'), before)
            ui.command(('menu',)); ui.tick(5000); ui.command(('resume',))
            ui.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST)); ui.tick(5000)
            ui.handle_event(pygame.event.Event(pygame.WINDOWFOCUSGAINED))
            self.assertEqual(ui.session.snapshot(), saved)
            ui.session.tick(3000)
            ui.window = pygame.display.set_mode((800, 600), pygame.RESIZABLE)
            ui.render()
            ui.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=ui.viewport.center))
            self.assertEqual((ui.session.pending.request.pc, ui.session.pending.request.yield_id), (4307, 65))
            answer_screen(ui.session)
            self.assertEqual((ui.session.pending.request.pc, ui.session.pending.request.yield_id), (4311, 76))
            self.assertEqual(ui.session.pending.details['speaker'], 'The team')
            self.assertEqual(ui.session.engine.dialogue_animation.wobble_direction, -20)


if __name__ == '__main__':
    unittest.main()
