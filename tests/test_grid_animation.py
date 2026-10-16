import copy
from dataclasses import replace
import json
import math
import unittest

from exp_runtime.randomness import NativeRandom
from exp_runtime.runtime import SaveError, Session
from exp_runtime.shs.grid_animation import GridTile
from test_word_grid import play_phase, resources


class GridAnimationTests(unittest.TestCase):
    def test_delayed_cube_clocks_match_native_frame_boundary_behavior(self):
        tile = GridTile()
        tile.flip(160); tile.grow(160); tile.shine(160)
        tile.tick(100)
        self.assertEqual((tile.flip_ms, tile.flip_delay, tile.grow_ms, tile.grow_delay), (600, 60, 500, 60))
        self.assertEqual((tile.angle, tile.scale, tile.glint), (math.pi, 0, -1))
        tile.tick(100)
        self.assertEqual((tile.flip_ms, tile.flip_delay, tile.grow_ms, tile.grow_delay), (560, -40, 460, -40))
        self.assertAlmostEqual(tile.angle, .8 * math.pi)
        self.assertAlmostEqual(tile.scale, (1 - 460 / 600) / .8)
        # Glint's delay-crossing path reads the retained growth delay, even
        # when no growth animation is active.
        tile = GridTile(grow_delay=-25)
        tile.shine(160); tile.tick(100); tile.tick(100)
        self.assertEqual((tile.glint_ms, tile.glint_delay), (475, -40))
        tile = GridTile(); tile.flip(100); tile.grow(100); tile.shine(100)
        tile.tick(100)  # Landing exactly on zero still spends the full frame.
        self.assertEqual((tile.flip_ms, tile.grow_ms, tile.glint_ms), (600, 500, 500))

    def test_pop_glint_and_shrink_endpoints_keep_native_inclusive_frames(self):
        tile = GridTile(); tile.grow(0)
        for _ in range(6): tile.tick(100)
        self.assertTrue(tile.growing)
        tile.tick(1)
        self.assertFalse(tile.growing)
        tile.grow(0, shrinking=True)
        for _ in range(7): tile.tick(100)
        self.assertTrue(tile.growing)
        self.assertEqual(tile.scale, 0)
        # Android converts the fraction to float32 before its double
        # multiply; the exact 400ms boundary still uses shine frame 1.
        for remaining, frame in ((600, 0), (500, 1), (400, 1), (300, 3), (200, 3), (100, 4), (0, 5)):
            tile = GridTile(glinting=True, glint_ms=remaining)
            self.assertEqual(tile.glint, frame)

    def test_intro_holds_cube_clocks_and_glint_waits_for_active_board_ticks(self):
        session = Session(resources(tutorial=True)); session.advance()
        game = session.engine.word_grid
        initial = copy.deepcopy(game.tiles)
        play_phase(session)
        self.assertEqual(game.tiles, initial)
        self.assertEqual(game.glint_ms, -4000)
        # Untimed tutorial: the board clock moves, the round clock does not.
        for _ in range(16): session.tick(250)
        self.assertFalse(any(tile.glinting for tile in game.tiles))
        session.tick(1)
        self.assertTrue(all(tile.glinting for tile in game.tiles))
        self.assertEqual(game.round_ms, game.round_limit_ms)

    def test_shrink_defers_generation_and_random_draws_until_the_old_board_leaves(self):
        session = Session(resources(tutorial=True)); session.engine.random = NativeRandom(1)
        session.advance(); play_phase(session)
        game = session.engine.word_grid
        board, round_number, random = game.board.copy(), game.round, session.engine.random.state
        game.round_success = True
        game.next_problem(session.engine.random)
        self.assertEqual(game.transition.mode, 'shrink')
        self.assertTrue(game.transition.deferred)
        self.assertEqual((game.board, game.round, session.engine.random.state), (board, round_number, random))
        saved = json.loads(json.dumps(session.snapshot()))
        restored = Session.from_snapshot(session.resources, saved)
        for dt in (250, 250, 250, 49):
            session.tick(dt); restored.tick(dt)
            self.assertEqual(session.snapshot(), restored.snapshot())
        self.assertEqual(session.engine.random.state, random)
        session.tick(1); restored.tick(1)
        self.assertEqual(session.snapshot(), restored.snapshot())
        self.assertEqual(game.round, round_number + 1)
        self.assertNotEqual(session.engine.random.state, random)
        self.assertEqual(game.phase, 6)
        self.assertTrue(all(tile.growing for tile in game.tiles))
        for field, value in (('flip_delay', 641), ('grow_ms', -1001), ('glint_ms', 601)):
            bad = copy.deepcopy(saved)
            bad['engine']['word_grid']['tiles'][0][field] = value
            with self.subTest(field=field), self.assertRaises(SaveError):
                Session.from_snapshot(session.resources, bad)

    def test_deferred_tutorial_path_uses_native_advance_index_instead_of_peek_index(self):
        session = Session(resources(tutorial=True)); session.advance(); play_phase(session)
        game = session.engine.word_grid
        first = game.tutorials[0]
        first.success_next = 2
        game.tutorials += [replace(first, heading='Sequential'),
                           replace(first, width=2, height=2, words=['ca'], fixed_board='ca\nca', heading='Peeked')]
        game.round_success = True; game.next_problem(session.engine.random)
        self.assertTrue(game.transition.deferred)
        self.assertEqual(game.problem_index, 1)
        for _ in range(4): session.tick(200)
        self.assertEqual(game.problem.heading, 'Sequential')
        self.assertEqual(game.board, list('catcat'))
        game.validate()

    def test_legacy_grid_keeps_existing_motion_until_the_next_native_setup(self):
        session = Session(resources(tutorial=True)); session.advance(); play_phase(session)
        old = session.snapshot(); old['version'] = 21
        del old['engine']['word_grid']['tiles']
        restored = Session.from_snapshot(session.resources, old)
        self.assertIsNone(restored.engine.word_grid.tiles)
        self.assertEqual(restored.engine.random, session.engine.random)
        restored.engine.word_grid.next_problem(restored.engine.random)
        self.assertIsNotNone(restored.engine.word_grid.tiles)
