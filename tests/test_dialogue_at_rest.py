"""A phone's dialogue frames: a settled line's layer is kept, and what never shows isn't drawn."""
import importlib.util
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from exp_runtime.dialogue_animation import CONTINUE_MS, EXPRESSION_END_MS, EXPRESSION_MS, REST_AGE_MS, DialogueAnimation


def settled(**fields):
    motion = DialogueAnimation(text_length=3, revealed=3, complete=True, continue_ms=CONTINUE_MS, **fields)
    motion.elapsed_ms = motion.duration_ms
    return motion


class AtRestTests(unittest.TestCase):
    def test_a_finished_line_with_nothing_running_is_at_rest(self):
        self.assertTrue(settled().at_rest)

    def test_still_typing_or_the_continue_tab_still_opening_is_not(self):
        self.assertFalse(DialogueAnimation(text_length=3).at_rest)
        motion = settled()
        motion.continue_ms = CONTINUE_MS - 1
        self.assertFalse(motion.at_rest)
        motion = settled()
        motion.elapsed_ms = motion.duration_ms - 1
        self.assertFalse(motion.at_rest)

    def test_a_changed_expression_waits_for_its_effects(self):
        motion = settled(initial_expression=0, expression=6)
        self.assertFalse(motion.at_rest)
        motion.presentation_ms = motion.expression_end_ms
        self.assertFalse(motion.at_rest)
        motion.age_ms = REST_AGE_MS
        self.assertTrue(motion.at_rest)

    def test_the_effects_are_over_by_then(self):
        from exp_runtime.portrait_effects import ball_alpha, starburst
        for expression in (6, 7, 8, 9):
            self.assertEqual(ball_alpha(expression, REST_AGE_MS), 0)
        self.assertIsNone(starburst(REST_AGE_MS))

    def test_a_running_expression_track_or_relationship_is_not_at_rest(self):
        from exp_runtime.dialogue_animation import ExpressionTransition
        portrait = SimpleNamespace(character_id=1, mode=1, theme=0)
        motion = settled()
        motion.expression_transition = ExpressionTransition(portrait, portrait, 1, 0)
        self.assertFalse(motion.at_rest)
        motion.expression_transition.elapsed_ms = EXPRESSION_END_MS - EXPRESSION_MS
        self.assertTrue(motion.at_rest)
        motion = settled()
        motion.relationship = SimpleNamespace(elapsed_ms=10, duration_ms=800, change=SimpleNamespace(extra_delay_ms=0))
        self.assertFalse(motion.at_rest)
        motion.relationship.elapsed_ms = 800
        self.assertTrue(motion.at_rest)


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class RendererTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        pygame.init()
        pygame.display.set_mode((16, 16))
        self.addCleanup(pygame.quit)
        from exp_runtime import desktop_dialogue
        self.module = desktop_dialogue

    def renderer(self, *, autoplay=False, hd=True, progress=1):
        renderer = self.module.DialogueRenderer.__new__(self.module.DialogueRenderer)
        renderer.autoplay = autoplay
        renderer.wide = object()
        renderer.has_hd_bundle = lambda: hd
        renderer.continue_progress = lambda _: progress
        return renderer

    @staticmethod
    def session(notice=0, effect=None):
        return SimpleNamespace(engine=SimpleNamespace(notice_ms=notice), portrait_effect=lambda: effect)

    def rest(self, renderer, session=None, motion=None, target=None):
        return renderer._at_rest(target, session or self.session(), motion or settled(), (1, 2, 3, 0), 1, None)

    def test_off_a_phone_nothing_is_kept(self):
        self.assertIsNone(self.rest(self.renderer()))

    def test_a_phone_keeps_a_settled_line(self):
        with patch.object(self.module, 'REUSE_AT_REST', True):
            self.assertIsNotNone(self.rest(self.renderer()))

    def test_what_keeps_a_line_moving_stops_it(self):
        with patch.object(self.module, 'REUSE_AT_REST', True):
            self.assertIsNone(self.rest(self.renderer(), self.session(notice=500)))
            self.assertIsNone(self.rest(self.renderer(), self.session(effect=(1, 2))))
            self.assertIsNone(self.rest(self.renderer(), motion=DialogueAnimation(text_length=3)))
            self.assertIsNone(self.rest(self.renderer(), target=object()))

    def test_a_restored_lines_pill_finishes_opening_first(self):
        with patch.object(self.module, 'REUSE_AT_REST', True):
            self.assertIsNone(self.rest(self.renderer(progress=.5)))
            self.assertIsNotNone(self.rest(self.renderer(progress=.5, hd=False)))

    def test_autoplay_has_no_pill_to_wait_for_and_switching_it_redraws(self):
        with patch.object(self.module, 'REUSE_AT_REST', True):
            renderer = self.renderer(autoplay=True, progress=0)
            on = self.rest(renderer)
            self.assertIsNotNone(on)
            renderer.autoplay = False
            renderer.continue_progress = lambda _: 1
            self.assertNotEqual(self.rest(renderer), on)

    def test_a_repeated_box_is_the_same_box_and_a_changed_one_is_rebuilt(self):
        import pygame
        from exp_runtime.ui_assets import Rect
        renderer = self.module.DialogueRenderer.__new__(self.module.DialogueRenderer)
        made = []

        def frame_scaled(pack, index, scale):
            made.append(index)
            picture = pygame.Surface((8, 8), pygame.SRCALPHA).convert_alpha()
            picture.fill((index * 20, pack % 200, 50, 200))
            return picture
        renderer.frame_scaled = frame_scaled
        renderer.hd_chrome = lambda: True
        def draw(rect):
            surface = pygame.Surface((90, 90), pygame.SRCALPHA).convert_alpha()
            renderer.box(surface, rect, 1)
            return surface
        first = pygame.image.tobytes(draw(Rect(20, 20, 30, 30)), 'RGBA')
        count = len(made)
        self.assertEqual(pygame.image.tobytes(draw(Rect(20, 20, 30, 30)), 'RGBA'), first)
        self.assertEqual(len(made), count)
        self.assertNotEqual(pygame.image.tobytes(draw(Rect(10, 20, 30, 30)), 'RGBA'), first)
        self.assertGreater(len(made), count)


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class BackgroundLayerTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        pygame.init()
        pygame.display.set_mode((16, 16))
        self.addCleanup(pygame.quit)
        from exp_runtime.desktop import Desktop
        self.pygame = pygame
        desktop = Desktop.__new__(Desktop)
        desktop.window = pygame.Surface((100, 100)).convert()
        desktop.viewport_for_test = pygame.Rect(0, 0, 100, 100)
        desktop._background_layer_cache = None
        desktop._frame_backdrop = lambda size: None
        desktop._location_change = lambda background, placement: None
        desktop._background_placement = lambda background, size: (0, 0, 100, 100)
        desktop.pending_background_alpha = 255
        self.desktop = desktop

    def picture(self, alpha=255):
        picture = self.pygame.Surface((200, 200), self.pygame.SRCALPHA).convert_alpha()
        picture.fill((10, 200, 30, alpha))
        return picture

    def draw(self, picture):
        self.desktop.pending_background = picture
        self.desktop._draw_background_layer((100, 100), self.desktop.viewport_for_test)

    def test_an_opaque_picture_filling_the_frame_needs_nothing_under_it_from_the_second_frame(self):
        picture = self.picture()
        self.draw(picture)
        self.assertIsNotNone(self.desktop._background_cover)
        self.desktop.window.fill((255, 0, 255), (0, 0, 100, 100))
        self.draw(picture)
        self.assertEqual(tuple(self.desktop.window.get_at((5, 5)))[:3], tuple(self.desktop._background_layer_cache[1].get_at((5, 5)))[:3])

    def test_the_kept_layer_never_takes_a_whole_surface_alpha(self):
        picture = self.picture()
        self.draw(picture)
        kept = self.desktop._background_layer_cache[1]
        self.assertFalse(kept.get_masks()[3])
        self.desktop.pending_background_alpha = 128
        self.draw(picture)
        self.assertIs(self.desktop._background_layer_cache[1], kept)
        self.assertIn(kept.get_alpha(), (None, 255))

    def test_a_fading_picture_shows_what_is_under_it(self):
        picture = self.picture()
        self.draw(picture)
        self.desktop.pending_background_alpha = 128
        self.desktop.window.fill((255, 0, 255), (0, 0, 100, 100))
        self.draw(picture)
        self.assertLess(self.desktop.window.get_at((5, 5)).g, 150)              # on the black it fills, not the old magenta
        self.assertLess(self.desktop.window.get_at((5, 5)).r, 100)

    def test_a_see_through_picture_always_has_black_under_it(self):
        picture = self.picture(alpha=100)
        self.draw(picture)
        self.assertIsNone(self.desktop._background_cover)
        self.desktop.window.fill((255, 0, 255), (0, 0, 100, 100))
        self.draw(picture)
        self.assertLess(self.desktop.window.get_at((5, 5)).r, 100)

    def test_a_new_picture_or_a_changing_location_fills_again(self):
        first, second = self.picture(), self.picture()
        self.draw(first)
        self.desktop._location_change = lambda background, placement: dict(p=.5, old=None, **{'from': None})
        self.desktop._location_progress = None
        self.desktop.window.fill((255, 0, 255), (0, 0, 100, 100))
        self.draw(second)
        self.assertNotEqual(tuple(self.desktop.window.get_at((5, 5)))[:3], (255, 0, 255))


if __name__ == '__main__':
    unittest.main()
