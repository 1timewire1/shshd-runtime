"""Authored dialogue/background scripts and pixels; no original game content."""
import copy
import importlib.util
import json
import unittest

from PIL import Image

from exp_runtime.background import BackgroundPan
from exp_runtime.engine import EngineAction, EngineState
from exp_runtime.runtime import SaveError, Session
from exp_runtime.vm import KiwiVM, VMError
from test_runtime import Resources, answer_screen, host_call, text_words
from test_vm import program


def story(game='shs'):
    words, (text,) = text_words('Authored dialogue.')
    calls = [call for character in (0, 1, 2, 7, 4, 0)
             for call in host_call(13, text, character)]
    resources = Resources(program(*host_call(34, -1, 1000), *calls, 0x33, words=words))
    resources.library.game_id = game
    session = Session(resources)
    session.engine.ui_defaults = {74: 0, 75: 7}
    session.engine.character_art_variants = {0: [100], 1: [200], 2: [300]}
    session.advance()
    return session


def dispatch(engine, service, *args):
    vm = KiwiVM(program(*host_call(service, *args), 0x33))
    vm.run()
    return engine.dispatch(vm), vm


class BackgroundTests(unittest.TestCase):
    def test_both_games_follow_speaker_side_with_existing_dialogue_timing(self):
        for game in ('shs', 'cod'):
            with self.subTest(game=game):
                session = story(game)
                pan = session.engine.background_pan
                self.assertEqual((pan.position, pan.target), (.5, 0))
                before = session.vm.snapshot()
                session.tick(125)
                self.assertEqual(pan.origin(640, 360), (-80, 0))
                session.tick(125)
                self.assertEqual(pan.origin(640, 360), (0, 0))
                self.assertEqual(session.vm.snapshot(), before)
                self.assertEqual(session.engine.dialogue_animation.portrait_delay_ms, 250)
                self.assertEqual(session.engine.dialogue_animation.revealed, 0)
                answer_screen(session)  # Player -> NPC.
                self.assertEqual((pan.position, pan.target), (0, 1))
                session.tick(125)
                self.assertEqual(pan.origin(640, 360), (-160, 0))
                session.tick(125)
                self.assertEqual(pan.origin(640, 360), (-320, 0))
                answer_screen(session)  # A different NPC remains on the same side.
                self.assertEqual((pan.position, pan.target), (1, 1))
                for _ in range(2):  # Narrator and a character with no portrait.
                    answer_screen(session)
                    self.assertIn(session.engine.panel.presentation_mode, (3, 4))
                    self.assertEqual(pan.position, 1)
                answer_screen(session)
                self.assertEqual((pan.position, pan.target), (1, 0))

    def test_service_97_fixed_alignment_reenable_and_ignored_extra_words(self):
        for game in ('shs', 'cod'):
            for alignment, expected in ((1, 0), (2, .5), (3, 1)):
                with self.subTest(game=game, alignment=alignment):
                    engine = EngineState()
                    engine.game_key = game
                    action, vm = dispatch(engine, 97, 0, alignment, 999)
                    self.assertTrue(action.completed)
                    self.assertEqual((action.name, vm.result, vm.sp), ('set_background_pan', 0, 0))
                    self.assertEqual(engine.result_cells, [None] * 10)
                    pan = engine.background_pan
                    pan.tick(250)
                    for mode in (1, 2):
                        pan.dialogue(mode)
                        pan.tick(250)
                        self.assertEqual(pan.position, expected)
                    dispatch(engine, 97, -1, 2)  # Every nonzero word enables auto-pan.
                    pan.tick(250)
                    self.assertTrue(pan.automatic)
                    self.assertEqual(pan.position, .5)
                    pan.dialogue(2)
                    pan.tick(250)
                    self.assertEqual(pan.position, 1)
            for args in ((), (1,)):
                with self.assertRaises(VMError):
                    dispatch(engine, 97, *args)

    def test_interrupted_pan_starts_at_current_position_and_unknown_alignment_holds_it(self):
        pan = BackgroundPan()
        pan.align(1)
        pan.tick(100)
        self.assertEqual(pan.position, .3)
        pan.align(3)
        self.assertEqual(pan.position, .3)
        pan.tick(125)
        self.assertAlmostEqual(pan.position, .65)
        pan.configure(False, -1)
        pan.tick(1000)
        self.assertAlmostEqual(pan.position, .65)
        pan.dialogue(1)
        pan.tick(250)
        self.assertAlmostEqual(pan.position, .65)

    def test_viewport_width_and_narrow_images_use_native_targets_without_scaling(self):
        pan = BackgroundPan()
        for alignment, narrow_x in ((1, 0), (2, 60), (3, 120)):
            pan.align(alignment)
            for _ in range(5):
                pan.tick(50)
                self.assertEqual(pan.origin(320, 400), (0, -20))
            self.assertEqual(pan.origin(200, 100), (narrow_x, 130))

    def test_background_replacement_sentinel_hide_and_character_setup(self):
        for service, args in ((11, (-1, 1000)), (34, (-1, 1000)),
                              (35, (1, -1, 1000, 0)), (86, (1000, -1, 1))):
            with self.subTest(service=service):
                engine = EngineState()
                engine.panel.background_id = 1000
                engine.panel.presentation_mode = 2
                engine.character_art_variants = {0: [100], 1: [200]}
                engine.ui_defaults[74] = 0
                pan = engine.background_pan
                pan.align(3)
                pan.tick(250)
                dispatch(engine, service, *args)
                self.assertEqual((pan.position, pan.target), (.5, 1))
                pan.tick(125)
                dispatch(engine, 11, -1, -2)  # Keep the existing background node.
                self.assertEqual((pan.position, pan.target), (.75, 1))
                self.assertEqual(engine.panel.background_id, 1000)
                dispatch(engine, 35, 0, -1, 1001, 0)
                self.assertEqual((pan.position, pan.target), (.5, 0))
                self.assertEqual(engine.panel.background_id, 1001)
                dispatch(engine, 11, -1, -1)
                # This fork keeps the background for any negative base (an HD real-device correction, engine.py).
                self.assertEqual(engine.panel.background_id, 1001)

    def test_pause_focus_loss_and_page_turn_do_not_restart_motion(self):
        from exp_runtime.desktop import Desktop
        session = story()
        host = Desktop.__new__(Desktop)
        from exp_runtime.desktop_pause_hd import HdPauseMenu
        host.session, host.active, host.error, host.menu_open = session, True, None, False
        host.pause_hd = HdPauseMenu.__new__(HdPauseMenu)
        host._attempt = lambda operation: operation()
        host.tick(100)
        pan = session.engine.background_pan
        self.assertEqual(pan.elapsed_ms, 100)
        host.menu_open, host.pause_elapsed_ms = True, 0
        host.tick(5000)
        self.assertEqual(pan.elapsed_ms, 100)
        host.menu_open, host.active = False, False
        host.tick(5000)
        self.assertEqual(pan.elapsed_ms, 100)
        host.active = True
        host.tick(150)
        before = copy.deepcopy(pan)
        session.engine.dialogue_animation.next_page(10)
        self.assertEqual(pan, before)

    def test_save_restores_in_flight_pan_and_policy_without_replaying_vm(self):
        for game in ('shs', 'cod'):
            session = story(game)
            session.engine.background_pan.configure(False, 3)
            session.tick(83)
            saved = json.loads(json.dumps(session.snapshot()))
            restored = Session.from_snapshot(session.resources, saved)
            self.assertEqual(restored.snapshot(), session.snapshot())
            self.assertEqual(saved['version'], 25)
            for ms in (42, 125, 1000):
                session.tick(ms)
                restored.tick(ms)
                self.assertEqual(restored.snapshot(), session.snapshot())

    def test_old_saves_keep_centered_view_and_stopped_service_97_can_continue(self):
        for game in ('shs', 'cod'):
            session = story(game)
            session.tick(90)
            old = session.snapshot()
            old['version'] = 18
            del old['engine']['background_pan']
            before = copy.deepcopy(old)
            restored = Session.from_snapshot(session.resources, old)
            self.assertEqual(old, before)
            self.assertEqual(restored.vm.snapshot(), session.vm.snapshot())
            self.assertEqual(restored.pending, session.pending)
            self.assertEqual(restored.engine.background_pan, BackgroundPan())
            answer_screen(restored)
            self.assertEqual(restored.engine.background_pan.target, 1)

            words, (ref,) = text_words('Continued after the retained call.')
            resources = Resources(program(*host_call(97, 0, 1, 42),
                                          *host_call(13, ref, 0), 0x33, words=words))
            resources.library.game_id = game
            stopped = Session(resources)
            request = stopped.vm.run()
            stopped.pending = EngineAction('unhandled_yield', request, False)
            old = stopped.snapshot()
            old['version'] = 18
            del old['engine']['background_pan']
            before = copy.deepcopy(old)
            restored = Session.from_snapshot(resources, old)
            self.assertEqual(old, before)
            self.assertEqual(restored.pending.name, 'dialogue')
            self.assertEqual(restored.pending.request.args, (ref, 0))
            self.assertEqual(restored.engine.background_pan.target, 0)
            self.assertFalse(restored.engine.background_pan.automatic)
            self.assertEqual(restored.engine.random, stopped.engine.random)
            self.assertEqual(Session.from_snapshot(resources, restored.snapshot()).snapshot(), restored.snapshot())

    def test_invalid_saved_motion_is_rejected(self):
        session = story()
        for field, values in (('automatic', (0, 'yes')), ('alignment', (True, -32769, 32768)),
                              ('elapsed_ms', (-1, 251, True, 0.5)),
                              ('start', (-.1, 1.1, float('nan'), float('inf'), 0)),
                              ('target', (-.1, 1.1, float('nan'), float('inf'), 1))):
            for value in values:
                with self.subTest(field=field, value=value):
                    saved = session.snapshot()
                    saved['engine']['background_pan'][field] = value
                    with self.assertRaises(SaveError):
                        Session.from_snapshot(session.resources, saved)

    def test_panel_close_retains_policy_and_episode_exit_reenables_automatic_pan(self):
        engine = EngineState()
        engine.background_pan.configure(False, 3)
        engine.background_pan.tick(125)
        dispatch(engine, 39)
        self.assertFalse(engine.background_pan.automatic)
        # This fork's panel close keeps the scene background (engine.py), and with it the node's pan.
        self.assertEqual(engine.background_pan.position, .75)
        engine.close_episode()
        self.assertTrue(engine.background_pan.automatic)
        self.assertEqual(engine.background_pan.alignment, 3)
        self.assertEqual(engine.background_pan.position, .5)

    def test_shared_renderer_crops_identically_on_desktop_and_native_without_mutation(self):
        from exp_runtime.desktop_dialogue import DialogueRenderer
        from exp_runtime.platforms import drawing
        source = Image.new('RGBA', (640, 360))
        source.putdata([(x % 256, x // 256, y % 256, 255) for y in range(360) for x in range(640)])
        backends = [('native', drawing.Surface.from_pixels(source), drawing.Surface,
                     lambda canvas: drawing.raster(canvas.snapshot()).tobytes())]
        if importlib.util.find_spec('pygame'):
            import pygame
            backends.append(('desktop', pygame.image.frombytes(source.tobytes(), source.size, 'RGBA'),
                             pygame.Surface, lambda canvas: pygame.image.tobytes(canvas, 'RGBA')))
        frames = {}
        for backend, image, surface, pixels in backends:
            art = DialogueRenderer.__new__(DialogueRenderer)
            art.image = lambda resource: image if resource == 1000 else None
            session = story()
            for ms, source_x in ((0, 160), (125, 80), (125, 0)):
                session.tick(ms)
                before = session.snapshot()
                canvas = surface((320, 480))
                canvas.fill((0, 0, 0))
                art.draw_background(canvas, session.engine)
                rendered = Image.frombytes('RGBA', (320, 480), pixels(canvas))
                self.assertEqual(rendered.getpixel((0, 20)), source.getpixel((source_x, 20)))
                self.assertEqual(rendered.getpixel((319, 20)), source.getpixel((source_x + 319, 20)))
                self.assertEqual(rendered.getpixel((0, 360)), (0, 0, 0, 255))
                self.assertEqual(session.snapshot(), before)
                if backend == 'native':
                    frames[source_x] = rendered.tobytes()
                else:
                    self.assertEqual(rendered.tobytes(), frames[source_x])


if __name__ == '__main__':
    unittest.main()
