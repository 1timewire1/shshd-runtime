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
