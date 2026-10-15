"""Native dialogue lifecycle, using authored scripts and portrait pixels."""
from copy import deepcopy
import importlib.util
import json
from math import degrees
import os
from types import SimpleNamespace
import unittest

from exp_runtime.dialogue_animation import DialogueAnimation, DialoguePortrait
from exp_runtime.runtime import SaveError, Session
from exp_runtime.ui_assets import Rect
from test_label_layout import authored_dialogue
from test_runtime import Resources, answer_screen, host_call, text_words
from test_vm import program


def story(calls, *, game='shs', text='Hello.', second=None):
    words, refs = text_words(text, 'Continue', 'Yes|No')
    resources = Resources(program(*calls(*refs), 0x33, words=words), second)
    resources.library.game_id = game
    resources.dialogue_layout = authored_dialogue
    session = Session(resources)
    session.engine.ui_defaults = {74: 0, 75: 7}
    session.engine.character_names = {0: 'Player', 1: 'Alex', 2: 'Sam', 7: 'Event'}
    session.engine.character_art_variants = {0: list(range(100, 105)), 1: list(range(200, 205)),
                                             2: list(range(300, 305)), 7: [-1] * 5}
    for character in (1, 2):
        session.engine.numbers[session.engine.number_key(character, 3001)] = -1
    session.advance()
    return session


class DialogueLifecycleTests(unittest.TestCase):
    def test_new_speaker_enters_neutral_then_changes_expression_without_changing_script_defaults(self):
        for game in ('shs', 'cod'):
            with self.subTest(game=game):
                session = story(lambda ref, *_: host_call(13, ref, 1, 2), game=game)
                motion = session.engine.dialogue_animation
                vm = session.vm.snapshot()
                self.assertEqual((motion.initial_portrait.asset_id, motion.portrait.asset_id), (200, 202))
                self.assertEqual(motion.expression_alphas, (255, 0))
                for elapsed, cache, alphas in ((999, 0, (255, 0)), (1000, 2, (255, 0)),
                                                (1400, 2, (255, 0)), (1500, 2, (255, 128)),
                                                (1600, 2, (255, 255)), (2000, 2, (128, 255)),
                                                (2400, 2, (0, 255))):
                    session.tick(elapsed - motion.presentation_ms)
                    self.assertEqual(session.engine.dialogue_history.expressions, {1: cache})
                    self.assertEqual(motion.expression_alphas, alphas)
                    self.assertEqual(session.engine.character_expressions, {})
                    self.assertEqual(session.vm.snapshot(), vm)
                    restored = Session.from_snapshot(session.resources, json.loads(json.dumps(session.snapshot())))
                    self.assertEqual(restored.snapshot(), session.snapshot())

    def test_same_speaker_uses_last_expression_but_switching_speakers_resets_to_neutral(self):
        session = story(lambda ref, *_: [word for character, expression in ((1, 2), (1, 3), (2, 4), (1, 1))
                                        for word in host_call(13, ref, character, expression)])
        for character, initial, changed in ((1, 0, True), (1, 2, False), (2, 0, True), (1, 0, True)):
            motion = session.engine.dialogue_animation
            self.assertEqual((motion.portrait.character_id, motion.initial_expression, motion.changed),
                             (character, initial, changed))
            self.assertEqual(motion.initial_portrait.asset_id, 100 + 100 * character + initial)
            session.tick(2400)
            answer_screen(session)

    def test_expression_clock_survives_page_turn_without_restarting_and_rendering_is_pure(self):
        session = story(lambda ref, *_: host_call(13, ref, 1, 3), text='Long authored text. ' * 80)
        session.answer()  # Cancels the grow/name tracks, not the expression timer.
        session.tick(900)
        motion = session.engine.dialogue_animation
        self.assertTrue(motion.complete)
        self.assertFalse(motion.housing_clipped)
        session.answer()
        self.assertTrue(motion.page_turn)
        self.assertEqual(motion.presentation_ms, 900)
        restored = Session.from_snapshot(session.resources, session.snapshot())
        session.tick(700)
        for _ in range(100):
            restored.tick(7)
        self.assertEqual(restored.snapshot(), session.snapshot())
        self.assertEqual(motion.expression_alphas, (255, 255))
        self.assertFalse(motion.housing_clipped)  # Cancelled grow has no completion callback.
        before = session.snapshot()
        for _ in range(3):
            _ = motion.expression_alphas, motion.box_rect(Rect(1, 2, 30, 40), None)
        self.assertEqual(session.snapshot(), before)

    def test_choices_retain_speaker_but_do_not_tick_hidden_dialogue(self):
        for game in ('shs', 'cod'):
            for elapsed, expected in ((900, 0), (1600, 2)):
                with self.subTest(game=game, elapsed=elapsed):
                    session = story(lambda ref, title, options: [*host_call(13, ref, 1, 2),
                        *host_call(1, title, options, ref, 0, 0, -1, -1, 0), *host_call(13, ref, 1, 3)], game=game)
                    session.tick(elapsed)
                    session.answer()
                    self.assertEqual(session.pending.name, 'choice')
                    before = deepcopy(session.engine.dialogue_animation)
                    session.tick(10000)
                    self.assertEqual(session.engine.dialogue_animation, before)
                    restored = Session.from_snapshot(session.resources, session.snapshot())
                    self.assertEqual(restored.snapshot(), session.snapshot())
                    restored.answer(0)
                    motion = restored.engine.dialogue_animation
                    self.assertFalse(motion.changed)
                    self.assertEqual(motion.initial_expression, expected)
                    self.assertEqual(motion.expression, 3)
                    self.assertEqual(motion.portrait_scale, 1)

    def test_narration_grows_from_initial_or_retained_hidden_portrait_position(self):
        box = Rect(25, 115, 216, 214)
        session = story(lambda ref, *_: host_call(13, ref, 7))
        self.assertEqual(session.engine.dialogue_animation.box_rect(box, None), Rect(0, 0, 1, 1))
        for character, mode in ((0, 1), (1, 2)):
            for close in (False, True):
                session = story(lambda ref, *_: [*host_call(13, ref, character),
                    *(host_call(39) if close else []), *host_call(13, ref, 7)])
                answer_screen(session)
                motion = session.engine.dialogue_animation
                self.assertEqual(motion.anchor_mode, mode)
                self.assertEqual(motion.previous is None, close)
                self.assertTrue(motion.box_grow)
                portrait = session.resources.dialogue_layout().bank.rectangle(17, 0x30 if mode == 1 else 0x4e)
                x, y = portrait.center
                self.assertEqual(motion.box_rect(box, portrait), Rect(x, y - 5, 1, 1))
                restored = Session.from_snapshot(session.resources, session.snapshot())
                self.assertEqual(restored.engine.dialogue_history, session.engine.dialogue_history)
                restored.tick(570)
                self.assertEqual(restored.engine.dialogue_animation.box_rect(box, portrait), box)

    def test_scene_load_clears_both_expression_tables_and_outgoing_portrait_but_retains_anchor(self):
        words, (ref,) = text_words('Next scene')
        second = program(*host_call(13, ref, 1), 0x33, words=words)
        for game in ('shs', 'cod'):
            session = story(lambda ref, *_: [*host_call(5, 1, 3), *host_call(13, ref, 1),
                *host_call(10, 25002, 0)], second=second, game=game)
            session.tick(1600)
            self.assertEqual(session.engine.dialogue_history.expressions, {1: 3})
            session.engine.character_expressions[250] = 5  # The native reset spans exactly 200 bytes.
            answer_screen(session)
            motion = session.engine.dialogue_animation
            self.assertEqual(session.scene, 25002)
            self.assertEqual(session.engine.character_expressions, {250: 5})
            self.assertEqual(session.engine.dialogue_history.expressions, {1: 0})
            self.assertEqual((motion.initial_expression, motion.expression, motion.previous), (0, 0, None))
            self.assertEqual(session.engine.dialogue_history.anchor_mode, 2)
            self.assertTrue(motion.changed)

    def test_native_shake_has_hold_scale_rotation_and_text_delay_on_both_sides(self):
        for character, angle in ((0, .25), (1, -.25)):
            for changed in (False, True):
                session = story(lambda ref, *_: [*host_call(13, ref, character),
                    *host_call(89), *host_call(13, ref, character if not changed else 2)])
                if changed:
                    # First presentation gets the shake for this side.
                    session = story(lambda ref, *_: [*host_call(89), *host_call(13, ref, character)])
                else:
                    answer_screen(session)
                motion = session.engine.dialogue_animation
                start = 700 if changed else 100
                self.assertFalse(motion.box_grow)
                self.assertEqual(motion.text_delay_ms, 950 if changed else 650)
                self.assertEqual((motion.box_alpha, motion.box_scale), (0, .5))
                session.tick(start)
                self.assertEqual((motion.box_alpha, motion.box_scale), (255, .5))
                self.assertAlmostEqual(motion.box_rotation, degrees(angle))
                session.tick(125)
                self.assertEqual((motion.box_scale, motion.box_rotation, motion.housing_clipped), (1, 0, False))
                session.tick(75)
                self.assertAlmostEqual(motion.box_rotation, degrees(-angle * .4))
                session.tick(50)
                self.assertEqual((motion.box_rotation, motion.housing_clipped), (0, True))

    def test_tap_cancels_box_and_title_but_not_portrait_or_expression_and_never_acknowledges_unread_line(self):
        for shake in (False, True):
            session = story(lambda ref, *_: [*(host_call(89) if shake else []), *host_call(13, ref, 1, 2)])
            motion = session.engine.dialogue_animation
            vm = session.vm.snapshot()
            session.tick(400)
            self.assertEqual(motion.portrait_scale, .5)
            session.answer()
            self.assertEqual((motion.box_alpha, motion.box_scale, motion.box_rotation, motion.name_alpha), (255, 1, 0, 255))
            self.assertEqual(motion.portrait_scale, .5)
            session.answer()
            self.assertEqual(session.vm.snapshot(), vm)
            session.tick(1200)
            self.assertTrue(motion.complete)
            self.assertEqual(motion.portrait_scale, 1)
            self.assertEqual(motion.expression_alphas, (255, 255))
            self.assertFalse(motion.housing_clipped)
            self.assertEqual(session.vm.snapshot(), vm)

    def test_grow_clips_housing_only_after_completion_and_same_speaker_clips_immediately(self):
        session = story(lambda ref, *_: [*host_call(13, ref, 1), *host_call(13, ref, 1)])
        motion = session.engine.dialogue_animation
        session.tick(869)
        self.assertFalse(motion.housing_clipped)
        session.tick(1)
        self.assertTrue(motion.housing_clipped)
        session.tick(130)  # Finish the text before acknowledging this line.
        session.answer()
        self.assertTrue(session.engine.dialogue_animation.housing_clipped)
        self.assertFalse(session.engine.dialogue_animation.box_grow)

    def test_v20_save_preserves_old_expression_and_shake_without_replaying_timing(self):
        for shake in (False, True):
            session = story(lambda ref, *_: [*(host_call(89) if shake else []), *host_call(13, ref, 1, 2)])
            # An actual v20 checkpoint, whose expression already appears and
            # whose shake uses the Android 70/2/70ms track.
            old = session.snapshot()
            old['version'] = 20
            del old['engine']['dialogue_history']
            del old['pending']['details']['initial_expression']
            state = old['engine']['dialogue_animation']
            for key in ('native_lifecycle', 'anchor_mode', 'initial_portrait', 'initial_expression',
                        'expression', 'presentation_ms', 'visuals_finished', 'housing_clipped'):
                del state[key]
            before = deepcopy(old)
            restored = Session.from_snapshot(session.resources, old)
            motion = restored.engine.dialogue_animation
            self.assertEqual(old, before)
            self.assertEqual(restored.vm.snapshot(), session.vm.snapshot())
            self.assertFalse(motion.native_lifecycle)
            self.assertEqual(motion.initial_portrait.asset_id, 202)
            self.assertEqual(motion.expression_alphas, (0, 255))
            if shake:
                self.assertEqual(motion.box_rotation, 20)
                restored.tick(35)
                self.assertEqual(motion.box_rotation, 0)
            self.assertEqual(Session.from_snapshot(session.resources, restored.snapshot()).snapshot(), restored.snapshot())

    def test_lifecycle_and_cached_expression_corruption_is_rejected(self):
        session = story(lambda ref, *_: host_call(13, ref, 1, 2))
        for key, value in (('native_lifecycle', 1), ('presentation_ms', -1), ('presentation_ms', 2401),
                           ('visuals_finished', True), ('housing_clipped', 'yes'), ('housing_clipped', True), ('anchor_mode', 1),
                           ('expression', 3), ('initial_expression', 2)):
            bad = session.snapshot()
            bad['engine']['dialogue_animation'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(SaveError):
                Session.from_snapshot(session.resources, bad)
        for key, value in (('anchor_mode', 9), ('expressions', {1: 128}), ('expressions', {1: 2}),
                           ('expressions', {-1: 0}), ('expressions', {1: True})):
            bad = session.snapshot()
            bad['engine']['dialogue_history'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(SaveError):
                Session.from_snapshot(session.resources, bad)

    def test_saves_predating_animation_state_restore_the_visible_expression_as_settled(self):
        session = story(lambda ref, *_: [*host_call(13, ref, 1, 2), *host_call(13, ref, 1, 3)])
        for version in (1, 2, 3):
            old = session.snapshot()
            old['version'] = version
            del old['engine']['dialogue_history']
            del old['engine']['dialogue_animation']
            del old['pending']['details']['initial_expression']
            restored = Session.from_snapshot(session.resources, old)
            self.assertEqual(restored.vm.snapshot(), session.vm.snapshot())
            motion = restored.engine.dialogue_animation
            self.assertTrue(motion.complete)
            self.assertFalse(motion.box_grow)
            self.assertEqual(motion.expression_alphas, (0, 255))
            self.assertEqual(motion.initial_portrait.asset_id, 202)
            self.assertEqual(Session.from_snapshot(session.resources, restored.snapshot()).snapshot(), restored.snapshot())
            restored.answer()
            self.assertEqual(restored.engine.dialogue_animation.initial_expression, 2)


class PortraitLayerTests(unittest.TestCase):
    @unittest.skip("shshd-runtime composes the housing in DialogueRenderer.portrait_parts / housing_polygon (HD's "
                   "layered ring, disc and art; tested in test_desktop and test_cod_hd_art), not upstream's "
                   "portrait_group(portrait, clip, old, old_alpha, alpha)")
    def test_housing_cut_preserves_beveled_corner_colored_ring_and_both_expression_layers(self):
        from exp_runtime import graphics
        from exp_runtime.desktop_dialogue import DialogueRenderer
        from exp_runtime.platforms import drawing as native
        backends = [('native', SimpleNamespace(Surface=native.Surface, SRCALPHA=native.SRCALPHA, draw=native.Draw))]
        if importlib.util.find_spec('pygame'):
            import pygame
            os.environ['SDL_VIDEODRIVER'] = 'dummy'
            pygame.display.init(); pygame.display.set_mode((320, 480))
            self.addCleanup(pygame.quit)
            backends.append(('desktop', pygame))
        for name, backend in backends:
            with self.subTest(backend=name):
                previous = graphics.install(backend)
                try:
                    art = DialogueRenderer.__new__(DialogueRenderer)
                    housing = backend.Surface((60, 60), backend.SRCALPHA); housing.fill((200, 0, 0, 255))
                    ring = backend.Surface((30, 30), backend.SRCALPHA); ring.fill((0, 200, 0, 255))
                    old = backend.Surface((10, 30), backend.SRCALPHA); old.fill((0, 0, 200, 255))
                    new = backend.Surface((10, 30), backend.SRCALPHA); new.fill((200, 200, 0, 255))
                    new.fill((0, 0, 0, 0), (0, 0, 5, 30))
                    art.frame = lambda _, index: housing if index == 37 else ring
                    art.portrait = lambda asset, _: old if asset == 100 else new
                    portrait, initial = DialoguePortrait(0, 101, 1, 1), DialoguePortrait(0, 100, 1, 1)
                    for old_alpha, alpha, expected in ((255, 0, (0, 0, 200)), (255, 128, (100, 100, 100)),
                                                       (255, 255, (200, 200, 0)), (128, 255, (200, 200, 0)),
                                                       (0, 255, (200, 200, 0))):
                        layer, origin = art.portrait_group(portrait, (-30, 0, 60, 35), initial, old_alpha, alpha)
                        pixel = native.raster(layer.snapshot()).getpixel if name == 'native' else layer.get_at
                        self.assertEqual(origin, (-30, -30))
                        self.assertEqual(tuple(pixel((1, 31))), (200, 0, 0, 255))  # Bevel survives.
                        self.assertEqual(tuple(pixel((1, 42)))[3], 0)  # Housing cut.
                        self.assertEqual(tuple(pixel((20, 42))), (0, 200, 0, 255))  # Ring survives.
                        actual = tuple(pixel((30, 42)))[:3]
                        self.assertTrue(all(abs(a - b) <= 1 for a, b in zip(actual, expected)), actual)
                        expected = (0, round(200 * (1 - old_alpha / 255)), round(200 * old_alpha / 255))
                        actual = tuple(pixel((27, 42)))[:3]
                        self.assertTrue(all(abs(a - b) <= 1 for a, b in zip(actual, expected)), actual)
                    # Cached source artwork must not be punched through or tinted.
                    pixel = native.raster(housing.snapshot()).getpixel if name == 'native' else housing.get_at
                    self.assertEqual(tuple(pixel((1, 42))), (200, 0, 0, 255))
                finally:
                    graphics.install(previous)
