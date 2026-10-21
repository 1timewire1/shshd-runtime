import copy
import importlib.util
import json
import os
import unittest

from exp_runtime.cod.scene_transition import SceneTransition
from exp_runtime.runtime import SaveError, Session
from test_runtime import Resources, host_call, text_words
from test_vm import program


def story(selector=6, *, game='cod', next_title=False):
    words, (first, second) = text_words('Before the transition.', 'After the transition.')
    following = host_call(8, second, -1, -1, 0) if next_title else host_call(13, second, 0)
    resources = Resources(program(*host_call(16, selector), *host_call(13, first, 0),
                                  *following, 0x33, words=words))
    resources.library.game_id = game
    session = Session(resources)
    session.advance()
    session.tick(4000)
    return session


@unittest.skip("exp-runtime's engine-level SceneTransition is unset in this fork's profiles (scene_fade.py draws its transitions)")
class SceneTransitionTests(unittest.TestCase):
    def test_native_backend_draws_the_same_blind_anchors_and_opacity(self):
        from exp_runtime import graphics
        from exp_runtime.desktop_transition import draw_transition
        from exp_runtime.platforms.drawing import Backend, Surface, raster
        previous = graphics.install(Backend(None, None))
        self.addCleanup(graphics.install, previous)
        for selector in (1, 2, 6):
            surface = Surface((320, 480)); surface.fill((255, 255, 255))
            transition = SceneTransition(); transition.start(selector, 0); transition.tick(600)
            draw_transition(surface, transition)
            pixels = raster(surface.snapshot())
            if selector == 1:
                self.assertEqual(pixels.getpixel((100, 14)), (0, 0, 0, 255))
                self.assertEqual(pixels.getpixel((100, 15)), (255, 255, 255, 255))
            elif selector == 2:
                self.assertEqual(pixels.getpixel((9, 100)), (0, 0, 0, 255))
                self.assertEqual(pixels.getpixel((10, 100)), (255, 255, 255, 255))
            else:
                self.assertEqual(pixels.getpixel((100, 100)), (127, 127, 127, 255))

    def test_callback_is_held_until_covered_and_input_stays_locked_through_reveal(self):
        session = story()
        old, vm = session.pending, session.vm.snapshot()
        self.assertIs(session.answer(), old)
        self.assertEqual(session.vm.snapshot(), vm)
        self.assertEqual(session.engine.scene_value, 0)
        session.tick(600)
        self.assertEqual(session.engine.scene_transition.coverage, .5)
        session.answer()
        self.assertEqual(session.vm.snapshot(), vm)
        session.tick(899)
        self.assertIs(session.pending, old)
        session.tick(1)
        self.assertEqual(session.pending.details['text'], 'After the transition.')
        self.assertEqual(session.engine.scene_transition.phase, 3)
        # Native stopAnimation removes the new layer entrances, while the
        # separate delayed expression change has not received a UI tick.
        motion = session.engine.dialogue_animation
        self.assertTrue(motion.complete)
        self.assertEqual(motion.presentation_ms, 0)
        incoming = session.vm.snapshot()
        session.answer()
        session.tick(1499)
        self.assertEqual(session.vm.snapshot(), incoming)
        self.assertEqual(motion.presentation_ms, 0)
        session.tick(1)
        self.assertFalse(session.transitioning)
        self.assertEqual(motion.presentation_ms, 1)
        self.assertEqual(session.answer().name, 'finished')

    def test_blinds_hold_before_opening_and_do_not_spend_overshoot_on_the_next_phase(self):
        for selector in (1, 2):
            with self.subTest(selector=selector):
                session = story(selector)
                session.answer()
                session.tick(9000)
                transition = session.engine.scene_transition
                self.assertEqual((transition.phase, transition.elapsed_ms), (3, 0))
                session.tick(300)
                self.assertEqual(transition.coverage, 1)
                session.tick(600)
                self.assertEqual(transition.coverage, .5)
                session.tick(600)
                self.assertEqual(transition.coverage, 0)
                self.assertTrue(session.transitioning)
                session.tick(300)
                self.assertFalse(session.transitioning)

    def test_saves_resume_both_directions_without_repeating_callback_or_random_draw(self):
        session = story(20)
        streams = copy.deepcopy((session.engine.random48, session.engine.random))
        session.answer()
        transition = session.engine.scene_transition
        self.assertEqual((transition.selector, transition.random_state), (2, 16807))
        self.assertEqual((session.engine.random48, session.engine.random), streams)
        for elapsed in (400, 1099, 1, 299, 1, 600, 899, 1):
            session.tick(elapsed)
            saved = json.loads(json.dumps(session.snapshot()))
            restored = Session.from_snapshot(session.resources, saved)
            self.assertEqual(json.loads(json.dumps(restored.snapshot())), saved)
            session = restored
        self.assertFalse(session.transitioning)
        self.assertEqual(session.engine.scene_transition.random_state, 16807)
        self.assertEqual(session.pending.details['text'], 'After the transition.')

    def test_random_fades_use_the_darwin_sequence_independently(self):
        transition = SceneTransition()
        for value in (16807, 282475249, 1622650073, 984943658, 1144108930):
            transition.start(20, 0)
            self.assertEqual(transition.random_state, value)
            self.assertEqual(transition.selector, 1 + value % 2)
            transition.clear()
            self.assertEqual(transition.random_state, value)

    def test_title_card_skips_fade_in_and_keeps_its_own_entrance(self):
        session = story(next_title=True)
        session.answer()
        session.tick(1500)
        self.assertEqual(session.pending.name, 'presentation')
        self.assertFalse(session.transitioning)
        self.assertEqual(session.engine.title_screen.elapsed_ms, 0)

    def test_unknown_selector_uses_native_watchdog_without_inventing_visuals(self):
        session = story(5)
        old = session.pending
        session.answer()
        session.tick(7000)
        self.assertIs(session.pending, old)
        self.assertEqual(session.engine.scene_transition.coverage, 0)
        session.tick(1)
        self.assertEqual(session.engine.scene_transition.phase, 3)
        session.tick(7001)
        self.assertFalse(session.transitioning)

    def test_choice_result_and_timer_callback_wait_for_fade_out(self):
        words, (title, options, prompt, after) = text_words('Pick', 'Left|Right', 'Choose.', 'Done.')
        for timeout in (False, True):
            with self.subTest(timeout=timeout):
                resources = Resources(program(*host_call(16, 1),
                    *host_call(1, title, options, prompt, 100 if timeout else 0, 1, -1, -1, 0),
                    *host_call(13, after, 0), 0x33, words=words))
                resources.library.game_id = 'cod'
                session = Session(resources)
                old = session.advance()
                if timeout:
                    session.tick(101)
                else:
                    session.tick(250)
                    session.answer(1)
                self.assertIs(session.pending, old)
                self.assertIsNone(session.engine.result_cells[0])
                session = Session.from_snapshot(resources, session.snapshot())
                session.tick(1500)
                self.assertEqual(session.engine.result_cells[0], 1)
                self.assertEqual(session.pending.details['text'], 'Done.')

    def test_shs_keeps_the_android_transition_policy(self):
        session = story(20, game='shs')
        previous = session.engine.random48.state
        before = session.pending
        self.assertIs(session.answer(), before)
        self.assertNotEqual(session.engine.random48.state, previous)
        self.assertEqual(session.engine.scene_transition.coverage, 0.)
        self.assertIs(session.answer(), before)
        session = Session.from_snapshot(session.resources, session.snapshot())
        self.assertEqual(session.tick(0).details['text'], 'After the transition.')
        self.assertEqual(session.engine.scene_transition.phase, 3)
        self.assertEqual(session.engine.dialogue_animation.presentation_ms, 0)
        restored = Session.from_snapshot(session.resources, session.snapshot())
        session.tick(33); restored.tick(33)
        self.assertEqual(session.snapshot(), restored.snapshot())
        self.assertFalse(session.transitioning)
        self.assertEqual(session.engine.dialogue_animation.presentation_ms, 33)

    def test_old_save_keeps_pending_request_and_does_not_start_or_draw_a_fade(self):
        session = story(20)
        state = session.snapshot()
        state['version'] = 21
        del state['engine']['scene_transition']
        restored = Session.from_snapshot(session.resources, state)
        self.assertEqual(restored.vm.snapshot(), session.vm.snapshot())
        self.assertFalse(restored.transitioning)
        self.assertEqual(restored.engine.scene_value, 20)
        self.assertEqual(restored.engine.scene_transition.random_state, 1)

    def test_invalid_saved_phase_result_clock_or_random_state_is_rejected(self):
        session = story()
        session.answer()
        state = session.snapshot()
        for key, value in [('phase', 2), ('selector', 20), ('elapsed_ms', 1500),
                           ('result', 4), ('random_state', -1)]:
            with self.subTest(key=key):
                bad = copy.deepcopy(state)
                bad['engine']['scene_transition'][key] = value
                with self.assertRaises(SaveError):
                    Session.from_snapshot(session.resources, bad)

    def test_vm_pause_retains_coverage_until_the_next_ui_without_repeating_return(self):
        words, (first, second) = text_words('Before.', 'After.')
        resources = Resources(program(*host_call(16, 6), *host_call(13, first, 0),
                                      0x32, *host_call(13, second, 0), 0x33, words=words))
        resources.library.game_id = 'cod'
        session = Session(resources); session.advance(); session.tick(4000); session.answer()
        session.tick(1500)
        self.assertEqual(session.pending.name, 'vm_pause')
        self.assertEqual(session.engine.scene_transition.phase, 1)
        self.assertEqual(session.engine.scene_transition.coverage, 1.)
        session = Session.from_snapshot(resources, session.snapshot())
        session.tick(20)
        self.assertEqual(session.pending.details['text'], 'After.')
        self.assertEqual(session.engine.scene_transition.phase, 3)

    def test_debugger_stop_after_callback_can_resume_and_save_before_the_next_ui(self):
        session = story()
        session.answer()
        run = session.vm.run
        def pause(*args):
            raise InterruptedError('debugger stopped before the next instruction')
        session.vm.run = pause
        with self.assertRaises(InterruptedError):
            session.tick(1500)
        self.assertIsNone(session.pending)
        self.assertIsNone(session.vm.pending)
        self.assertEqual(session.engine.scene_transition.phase, 1)
        restored = Session.from_snapshot(session.resources, session.snapshot())
        session.vm.run = run
        session.advance(); restored.advance()
        self.assertEqual(session.snapshot(), restored.snapshot())
        self.assertEqual(session.engine.scene_transition.phase, 3)


@unittest.skip("exp-runtime's engine-level SceneTransition is unset in this fork's profiles (scene_fade.py draws its transitions)")
class TransitionDrawingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
        import pygame
        pygame.display.init()

    def test_blinds_keep_the_native_top_left_anchor_and_black_fade_uses_opacity(self):
        import pygame
        from exp_runtime.desktop_transition import draw_transition
        for selector in (1, 2, 6):
            with self.subTest(selector=selector):
                surface = pygame.Surface((320, 480))
                surface.fill('white')
                transition = SceneTransition()
                transition.start(selector, 0)
                transition.tick(600)
                draw_transition(surface, transition)
                if selector == 1:
                    for row in range(16):
                        self.assertEqual(surface.get_at((100, row * 30 + 14))[:3], (0, 0, 0))
                        self.assertEqual(surface.get_at((100, row * 30 + 15))[:3], (255, 255, 255))
                elif selector == 2:
                    for column in range(16):
                        self.assertEqual(surface.get_at((column * 20 + 9, 100))[:3], (0, 0, 0))
                        self.assertEqual(surface.get_at((column * 20 + 10, 100))[:3], (255, 255, 255))
                else:
                    self.assertEqual(surface.get_at((100, 100))[:3], (127, 127, 127))

    def test_pause_and_pointer_commands_do_not_interrupt_a_transition(self):
        import pygame
        from exp_runtime.desktop import Desktop
        ui = Desktop.__new__(Desktop)
        ui.audio_stored = False
        ui.pause_closing_ms = 0
        ui.session, ui.error = story(), None
        ui.session.answer()
        ui.menu_open = False
        ui.command(('menu',))
        self.assertFalse(ui.menu_open)
        ui._sync_text_input = lambda: None
        ui.cancel_pointer = lambda: None
        ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        self.assertFalse(ui.menu_open)
        before = ui.session.snapshot()
        ui.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(120, 200)))
        self.assertEqual(ui.session.snapshot(), before)
