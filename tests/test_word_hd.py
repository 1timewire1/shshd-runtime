"""HD word game: layout math, projection, hit testing and the score/shard clock (no art)."""
import importlib.util
import os
from types import SimpleNamespace
import unittest


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class HdWordTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        pygame.init()
        pygame.display.set_mode((16, 16))
        self.addCleanup(pygame.quit)
        from exp_runtime import desktop_word_hd as module
        self.module = module

    @staticmethod
    def problem(width, height, heading='Pass the\nball!', prompt='Pass\nBall'):
        return SimpleNamespace(width=width, height=height, heading=heading, prompt=prompt)

    def test_projection_centers_the_board_and_tilts_it_back(self):
        project = self.module.project
        left = project(5, 3, 0, 0, 0)
        right = project(5, 3, 5 * 450 + 4 * 72, 0, 0)
        self.assertAlmostEqual((left[0] + right[0]) / 2, 384, delta=1)
        # A cell further down the board lands lower on the screen and a little wider.
        top = project(5, 3, 0, 0, 0)
        bottom = project(5, 3, 0, 2 * 522, 0)
        self.assertGreater(bottom[1], top[1])
        self.assertLess(bottom[0], top[0])

    def test_depth_table_matches_the_native_sizes(self):
        depth = self.module.board_depth
        self.assertEqual(depth(5, 5), -3800)
        self.assertEqual(depth(5, 3), -3400)
        self.assertEqual(depth(4, 4), -3400)
        self.assertEqual(depth(5, 1), -3000)

    def test_heading_lines_slide_in_from_the_right_then_rest(self):
        game = SimpleNamespace(phase=0, phase_ms=2800)
        problem = self.problem(4, 4)
        lines = self.module.heading_lines(game, problem)
        self.assertEqual([(l[0], l[2]) for l in lines], [('Pass the', 120), ('ball!', 160)])
        self.assertTrue(all(0 < x - rest <= 352 for (_, x, _, _), rest in zip(lines, (280, 268))))
        game.phase, game.phase_ms = 1, 0
        self.assertEqual([(l[1], l[2]) for l in self.module.heading_lines(game, problem)],
                         [(280, 120), (268, 160)])
        game.phase = 6
        self.assertEqual(self.module.heading_lines(game, problem), ())

    def test_heading_fades_while_the_board_turns(self):
        game = SimpleNamespace(phase=4, phase_ms=400)
        lines = self.module.heading_lines(game, self.problem(4, 4))
        self.assertAlmostEqual(lines[0][3], .3)

    def test_keywords_travel_from_the_right_through_the_center_to_the_corner(self):
        pose = self.module.keyword_pose
        self.assertIsNone(pose(.1, 0, 200, 2, 104))
        self.assertEqual(pose(.6, 0, 200, 2, 104), (384., (1024 - 208) / 2, 1.))
        x, y, scale = pose(.95, 1, 100, 2, 104)
        self.assertAlmostEqual(x, 30 + 46 + 100 * .65 / 2)
        self.assertEqual((y, scale), (804, .65))
        # Continuous where the middle stretch ends and the last begins.
        early = pose(.89, 0, 200, 2, 104)
        self.assertAlmostEqual(early[0], 30 + 200 * .65 / 2, delta=.5)

    def test_hit_uses_projected_cells_and_the_inset_after_a_drag_starts(self):
        from exp_runtime.desktop_word_hd import HdWordRenderer, project
        renderer = HdWordRenderer.__new__(HdWordRenderer)
        game = SimpleNamespace(problem=self.problem(5, 3), selection=[])
        center = project(5, 3, 2 * 522 + 225, 1 * 522 + 225, 0)
        self.assertEqual(renderer.hit(center, game), 1 * 5 + 2)
        edge = project(5, 3, 2 * 522 + 5, 1 * 522 + 225, 0)
        self.assertEqual(renderer.hit(edge, game), 1 * 5 + 2)
        game.selection = [0]
        self.assertIsNone(renderer.hit(edge, game))
        self.assertEqual(renderer.hit(center, game), 1 * 5 + 2)
        self.assertIsNone(renderer.hit((5, 5), game))

    def test_perspective_of_a_rectangle_is_the_identity(self):
        from exp_runtime.hd_gl import perspective_coefficients
        coefficients = perspective_coefficients([(0, 0), (10, 0), (10, 20), (0, 20)], (10, 20))
        for actual, expected in zip(coefficients, (1, 0, 0, 0, 1, 0, 0, 0)):
            self.assertAlmostEqual(actual, expected)

    def test_a_quad_paints_its_texture_where_it_lands(self):
        import pygame
        from PIL import Image
        from exp_runtime.hd_gl import draw_quad
        canvas = pygame.Surface((40, 40), pygame.SRCALPHA)
        red = Image.new('RGBA', (8, 8), (255, 0, 0, 255))
        draw_quad(canvas, red, [(10, 10), (30, 12), (30, 30), (10, 32)])
        self.assertEqual(tuple(canvas.get_at((20, 21)))[:3], (255, 0, 0))
        self.assertEqual(canvas.get_at((2, 2)).a, 0)
        draw_quad(canvas, red, [(0, 0), (4, 0), (4, 4), (0, 4)], alpha=.5)
        self.assertAlmostEqual(canvas.get_at((1, 1)).a, 128, delta=2)

    def scene_renderer(self, background=None):
        """A renderer with made-up art, counting the haze's turns."""
        import pygame
        module = self.module

        class Atlas:
            @staticmethod
            def image(_):
                return pygame.Surface((256, 256), pygame.SRCALPHA).convert_alpha()

            @staticmethod
            def draw(*_, **__):
                pass

        class Counting(module.HdWordRenderer):
            def __init__(self):
                self.canvas = pygame.Surface(module.FRAME).convert()
                self.art = SimpleNamespace(image=lambda _: background)
                self._haze, self._haze_shown, self.turned = None, None, 0

            def atlas(self, _):
                return Atlas

            def turned_haze(self, game):
                self.turned += 1
                return super().turned_haze(game)
        return Counting()

    def test_the_haze_turns_clear_of_the_frame_at_any_angle(self):
        renderer = self.scene_renderer()
        for ms in range(0, 18000, 137):
            part = renderer.turned_haze(SimpleNamespace(visual_ms=ms))
            self.assertEqual(part.get_size(), (192, 256))

    def test_off_a_phone_the_haze_turns_every_frame(self):
        renderer = self.scene_renderer()
        game = SimpleNamespace(visual_ms=0, phase='play', phase_ms=0)
        for ms in range(6):
            game.visual_ms = ms
            renderer.backdrop(game, 1)
        self.assertEqual(renderer.turned, 6)

    def test_a_phones_haze_is_frame_sized_and_turns_at_most_thirty_times_a_second(self):
        from unittest.mock import patch
        renderer = self.scene_renderer()
        game = SimpleNamespace(visual_ms=0, phase='play', phase_ms=0)
        with patch.object(self.module, 'QUICK_DRAWING', True):
            for ms in range(0, 1000, 17):               # 60 frames a second
                game.visual_ms = ms
                self.assertEqual(renderer.haze_layer(game).get_size(), self.module.FRAME)
            self.assertLessEqual(renderer.turned, 31)
            self.assertGreaterEqual(renderer.turned, 24)

    def test_at_a_low_frame_rate_a_phones_haze_still_turns_every_frame(self):
        from unittest.mock import patch
        renderer = self.scene_renderer()
        game = SimpleNamespace(visual_ms=0, phase='play', phase_ms=0)
        with patch.object(self.module, 'QUICK_DRAWING', True):
            for frame in range(20):                     # 20 frames a second
                game.visual_ms = frame * 50
                renderer.haze_layer(game)
        self.assertEqual(renderer.turned, 20)

    def test_a_phones_haze_starts_over_for_a_new_game_or_an_earlier_time(self):
        from unittest.mock import patch
        renderer = self.scene_renderer()
        game = SimpleNamespace(visual_ms=500, phase='play', phase_ms=0)
        with patch.object(self.module, 'QUICK_DRAWING', True):
            renderer.haze_layer(game)
            renderer.haze_layer(SimpleNamespace(visual_ms=500, phase='play', phase_ms=0))
            self.assertEqual(renderer.turned, 2)
            renderer.haze_layer(game)
            game.visual_ms = 0                          # a restored game's clock
            renderer.haze_layer(game)
            self.assertEqual(renderer.turned, 4)

    def test_off_a_phone_a_cube_turns_smoothly(self):
        self.assertEqual([self.module.turn_ms(ms, 3) for ms in (0, 7, 200)], [0, 7, 200])

    def test_a_phones_cube_turns_in_steps_that_move_at_once(self):
        from unittest.mock import patch
        with patch.object(self.module, 'QUICK_DRAWING', True):
            for cell in range(9):
                steps = {self.module.turn_ms(ms, cell) for ms in range(0, 300, 16)}
                self.assertGreater(min(steps), 0)
                self.assertLessEqual(len(steps), 11)
                self.assertGreaterEqual(self.module.turn_ms(300, cell), 300)     # it finishes

    def test_a_phones_odd_and_even_cubes_change_pose_on_different_frames(self):
        from unittest.mock import patch
        with patch.object(self.module, 'QUICK_DRAWING', True):
            changes = {}
            for cell in (0, 1):
                poses = [self.module.turn_ms(ms, cell) for ms in range(0, 300, 17)]
                changes[cell] = {i for i in range(1, len(poses)) if poses[i] != poses[i - 1]}
            self.assertLess(len(changes[0] & changes[1]), min(len(changes[0]), len(changes[1])) / 3)

    def test_only_a_phones_turning_cube_gives_up_smoothing(self):
        from unittest.mock import patch
        from PIL import Image
        import pygame
        seen = []
        renderer = self.module.HdWordRenderer.__new__(self.module.HdWordRenderer)
        tile = Image.new('RGBA', (32, 32), (10, 20, 30, 255))
        renderer.face = lambda _: tile

        def record(_canvas, _image, _quad, _alpha=1., resample=None):
            seen.append(resample)
        cube = self.module.HdWordRenderer.cube_image
        with patch.object(self.module, 'draw_quad', record):
            cube.cache_clear()
            cube(renderer, 3, 3, 0, 0, 0, '', '', 50, 200, 0, (None, None))
            self.assertEqual(set(seen), {Image.Resampling.BILINEAR})
            with patch.object(self.module, 'QUICK_DRAWING', True):
                seen.clear()
                cube.cache_clear()
                cube(renderer, 3, 3, 0, 0, 0, '', '', 50, 200, 0, (None, None))
                self.assertEqual(set(seen), {Image.Resampling.BILINEAR})         # at rest
                seen.clear()
                cube(renderer, 3, 3, 0, 0, 0, '', '', 50, 200, 120, (None, None))
                self.assertEqual(set(seen), {Image.Resampling.NEAREST})
            cube.cache_clear()
        self.assertTrue(pygame.get_init())

    def test_an_opaque_background_stays_opaque_and_needs_no_black_behind_it(self):
        import pygame
        picture = pygame.Surface((960, 1440), pygame.SRCALPHA).convert_alpha()
        picture.fill((10, 200, 30, 255))
        renderer = self.scene_renderer(picture)
        image = renderer.background(1)
        self.assertFalse(image.get_flags() & pygame.SRCALPHA)
        self.assertEqual(image.get_height(), round(1440 * self.module.BACKGROUND_SCALE_Y))
        renderer.canvas.fill((255, 0, 255))
        game = SimpleNamespace(visual_ms=0, phase=-2, phase_ms=0)
        renderer.draw_scene(renderer.canvas, game, 1, pygame.Surface(self.module.FRAME, pygame.SRCALPHA).convert_alpha())
        self.assertLess(abs(renderer.canvas.get_at((5, 5)).g - 200), 3)      # the picture, not the magenta or black
        self.assertLess(renderer.canvas.get_at((5, 5)).b, 40)

    def test_a_background_with_holes_or_too_small_has_black_behind_it(self):
        import pygame
        holes = pygame.Surface((960, 1440), pygame.SRCALPHA).convert_alpha()
        holes.fill((10, 200, 30, 255))
        holes.fill((0, 0, 0, 0), (0, 0, 400, 400))
        small = pygame.Surface((100, 100)).convert()
        haze = pygame.Surface(self.module.FRAME, pygame.SRCALPHA).convert_alpha()
        game = SimpleNamespace(visual_ms=0, phase=-2, phase_ms=0)
        for picture, spot in ((holes, (5, 5)), (small, (700, 900)), (None, (5, 5))):
            renderer = self.scene_renderer(picture)
            renderer.canvas.fill((255, 0, 255))
            renderer.draw_scene(renderer.canvas, game, 1, haze)
            self.assertEqual(tuple(renderer.canvas.get_at(spot))[:3], (0, 0, 0))

    def test_a_found_word_flies_lands_and_the_digits_count_up(self):
        from exp_runtime.desktop_word_hd import EffectState, FLY_MS
        game = SimpleNamespace(visual_ms=0, score=300)
        state = EffectState(game)
        game.score = 569
        state.score = 569
        state.flying.append([269, (100, 400), 0.])
        state.inflight += 269
        state.tick(200)
        self.assertEqual((state.shown, state.pending, len(state.flying)), (300, 0, 1))
        state.tick(200)
        self.assertEqual(state.pending, 269 - int(.2 * 800))
        self.assertEqual(state.shown, 300 + int(.2 * 800))
        for _ in range(10):
            state.tick(100)
        self.assertEqual((state.shown, state.pending), (569, 0))

    def test_shards_fall_and_leave(self):
        from exp_runtime.desktop_word_hd import EffectState, Shard
        game = SimpleNamespace(visual_ms=0, score=0)
        state = EffectState(game)
        state.shards.append(Shard(100, 900, 1., 100, 0, 90, 0, 0))
        state.tick(100)
        shard = state.shards[0]
        self.assertAlmostEqual(shard.x, 110)
        self.assertGreater(shard.vy, 0)
        for _ in range(10):
            state.tick(100)
        self.assertEqual(state.shards, [])


if __name__ == '__main__':
    unittest.main()
