import copy
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest

from exp_runtime.shs.grid_layout import heading_lines, portrait_ring_scale, prompt_position, tile_opacity, tutorial_box
from exp_runtime.randomness import NativeRandom
from exp_runtime.runtime import SaveError, Session
from test_word_grid import play_phase, resources, tutorial_resources


class GridLayoutTests(unittest.TestCase):
    def test_dimmed_cube_keeps_opaque_letters_shine_and_black_underlay(self):
        from exp_runtime import graphics
        from exp_runtime.platforms.drawing import Backend, Surface, raster
        from exp_runtime.shs.desktop_grid import GridRenderer
        backend = Backend(None, None)
        previous = graphics.install(backend)
        self.addCleanup(graphics.install, previous)
        tile = Surface((20, 20)); tile.fill((200, 100, 50, 255))
        glyph = Surface((2, 2)); glyph.fill((0, 255, 0, 255))
        shine = Surface((20, 20)); shine.fill((0, 0, 255, 255))
        renderer = GridRenderer.__new__(GridRenderer)
        renderer.frame = lambda asset, frame: shine if frame == 35 else tile
        renderer.glyph = lambda asset, char: glyph if char else None
        dimmed = raster(renderer.cell_image(41, 'A', None, alpha=128).snapshot())
        self.assertEqual(dimmed.getpixel((0, 0)), (100, 50, 25, 255))
        self.assertEqual(dimmed.getpixel((10, 10)), (0, 255, 0, 255))
        glowing = raster(renderer.cell_image(41, '', None, glint=0, alpha=26).snapshot())
        self.assertEqual(glowing.getpixel((0, 0)), (0, 0, 255, 255))
        self.assertEqual(raster(tile.snapshot()).getpixel((0, 0)), (200, 100, 50, 255))

    def test_tile_brightness_uses_countdown_offsets_and_first_selected_cell(self):
        offsets = {0: 1500, 3: 0}
        for remaining, expected in ((10000, 1.), (5000, 1.), (3250, .5), (1500, .1), (-1, .1)):
            with self.subTest(remaining=remaining):
                self.assertAlmostEqual(tile_opacity(remaining, offsets, 0, highlighted=True), expected)
        self.assertEqual(tile_opacity(10000, offsets, 4, selection=[0, 4]), 1.)
        self.assertAlmostEqual(tile_opacity(7100, offsets, 4, selection=[0, 4]), .8)
        self.assertEqual(tile_opacity(1500, offsets, 4, selection=[0, 4]), .7)
        self.assertEqual(tile_opacity(1500, offsets, 4, selection=[0, 4], bad=True), 1.)
        self.assertEqual(tile_opacity(0, offsets, 2), 1.)
        self.assertEqual(tile_opacity(0, None, 0, highlighted=True), 1.)

    def test_highlight_shuffle_commits_with_visuals_and_survives_save(self):
        session = Session(resources(tutorial=True)); session.engine.random = NativeRandom(1)
        session.advance()
        game = session.engine.word_grid
        # Native full-range swaps, in column-major start order. Both draws
        # select slot zero, so the second swap exchanges the two offsets.
        self.assertEqual(game.highlight_offsets, {0: 1500, 3: 0})
        self.assertEqual(session.engine.random.state, 2524885223)
        saved = session.snapshot()
        restored = Session.from_snapshot(session.resources, json.loads(json.dumps(saved)))
        self.assertEqual(restored.snapshot(), saved)
        play_phase(session)
        game.round_success = False
        game.tutorials[0].failure_next = 0
        game.next_problem(session.engine.random)
        self.assertEqual(game.highlight_offsets, {})
        self.assertEqual(game.transition.highlight_offsets, {0: 1500, 3: 0})
        self.assertEqual(session.engine.random.state, 2524885223)
        saved = session.snapshot()
        restored = Session.from_snapshot(session.resources, saved)
        for _ in range(4):
            session.tick(200); restored.tick(200)
            self.assertEqual(session.snapshot(), restored.snapshot())
        expected = NativeRandom(2524885223); expected.next(); expected.next()
        self.assertEqual(session.engine.random, expected)
        self.assertEqual(sorted(game.highlight_offsets.values()), [0, 1500])
        for offsets in ({6: 0}, {0: -1}, {0: 3000}):
            bad = copy.deepcopy(saved)
            bad['engine']['word_grid']['highlight_offsets'] = offsets
            with self.subTest(offsets=offsets), self.assertRaises(SaveError):
                Session.from_snapshot(session.resources, bad)
        old = copy.deepcopy(saved); old['version'] = 21
        del old['engine']['word_grid']['highlight_offsets']
        del old['engine']['word_grid']['transition']['highlight_offsets']
        del old['engine']['word_grid']['transition']['round_ms']
        migrated = Session.from_snapshot(session.resources, old)
        self.assertIsNone(migrated.engine.word_grid.highlight_offsets)
        self.assertEqual(migrated.engine.random.state, saved['engine']['random']['state'])

    def test_portrait_ring_uses_staggered_native_entrance_then_periodic_pulse(self):
        game = SimpleNamespace(phase=0, phase_ms=2800, visual_ms=0)
        self.assertEqual(portrait_ring_scale(game), 0)
        # Android reuses the ring node: the last started stagger supplies its
        # scale. It reaches 1.3 at the end of the 2800ms entrance.
        game.phase_ms = 0
        self.assertAlmostEqual(portrait_ring_scale(game), 1.3)
        game.phase = 1
        self.assertAlmostEqual(portrait_ring_scale(game), .85)
        game.visual_ms = 625
        self.assertEqual(portrait_ring_scale(game), 1)
        game.visual_ms = 1250
        self.assertAlmostEqual(portrait_ring_scale(game), .85, places=6)

    def test_score_flies_from_first_tile_then_transfers_without_changing_game_result(self):
        from exp_runtime.shs.grid_motion import project
        session = Session(resources(tutorial=True)); session.advance(); play_phase(session)
        for phase, cell in (('down', 0), ('move', 1), ('move', 2)):
            session.grid_pointer(phase, cell)
        game = session.engine.word_grid
        self.assertEqual((game.score, game.display_score, game.score_pending), (100, 0, 0))
        effect, = game.score_effects
        self.assertEqual((effect.x, effect.y), project(3, 2, 225, 225)[:2])
        self.assertEqual((effect.value, effect.remaining_ms), (100, 400))
        held, random = session.vm.snapshot(), session.engine.random.state
        session.tick(200)
        saved = session.snapshot()
        restored = Session.from_snapshot(session.resources, saved)
        for dt in (200, 100, 25, 200, 100, 100):
            session.tick(dt); restored.tick(dt)
            self.assertEqual(session.snapshot(), restored.snapshot())
        self.assertEqual((game.score, game.display_score, game.score_pending, game.score_phase), (100, 100, 0, 0))
        self.assertFalse(game.score_effects)
        self.assertEqual(session.vm.snapshot(), held)
        self.assertEqual(session.engine.random.state, random)
        for key, value in (('display_score', 101), ('score_phase', 3), ('score_pending', 100)):
            bad = copy.deepcopy(saved)
            bad['engine']['word_grid'][key] = value
            with self.subTest(key=key), self.assertRaises(SaveError):
                Session.from_snapshot(session.resources, bad)
        old = copy.deepcopy(saved); old['version'] = 21
        for key in ('score_effects', 'score_pending', 'score_phase', 'score_target', 'display_score'):
            del old['engine']['word_grid'][key]
        migrated = Session.from_snapshot(session.resources, old).engine.word_grid
        self.assertEqual(migrated.display_score, migrated.score)
        self.assertFalse(migrated.score_effects)

    def test_solid_tile_faces_follow_flip_and_keep_the_native_front_plane(self):
        import math
        from exp_runtime.shs.grid_motion import cube_faces, project
        front = cube_faces(3, 2, 1, 0)
        self.assertIn('front', [face for _, face, _ in front])
        self.assertNotIn('back', [face for _, face, _ in front])
        corners = next(points for _, face, points in front if face == 'front')
        self.assertEqual(corners[0], project(3, 2, 522, 0)[:2])
        self.assertEqual(corners[2], project(3, 2, 972, 450)[:2])
        back = cube_faces(3, 2, 1, 0, math.pi)
        self.assertIn('back', [face for _, face, _ in back])
        self.assertNotIn('front', [face for _, face, _ in back])
        edge = cube_faces(3, 2, 1, 0, math.pi / 2)
        self.assertIn('side', [face for _, face, _ in edge])
        self.assertTrue(all(len(points) == 4 for _, _, points in edge))
        self.assertEqual(cube_faces(3, 2, 1, 0, scale=0), [])

    def test_tutorial_panels_follow_position_and_measured_paragraph_height(self):
        top = tutorial_box(128, 0)
        center = tutorial_box(128, 1)
        bottom = tutorial_box(128, 2)
        self.assertEqual((top.x, top.top, top.body_y, top.bottom), (7, 11, 33, 196))
        self.assertEqual((center.top, center.bottom), (147, 332))
        self.assertEqual((bottom.top, bottom.bottom), (283, 468))
        longer = tutorial_box(192, 0)
        self.assertEqual(longer.top, top.top)
        self.assertEqual(longer.bottom - top.bottom, 64)
        zooming = tutorial_box(128, 1, .5)
        self.assertEqual(zooming.x, 83.5)
        self.assertAlmostEqual((zooming.top + zooming.bottom + 1) / 2, 240)

    def test_native_heading_and_bottom_word_positions(self):
        g = SimpleNamespace(phase=1, phase_ms=0, problem=SimpleNamespace(heading='One\nTwo\nThree'))
        self.assertEqual(heading_lines(g), (('One', 110, 60, 1.), ('Two', 104, 80, 1.), ('Three', 95, 100, 1.)))
        self.assertEqual(prompt_position(1, 0, 100, 2), (47, 377, .65))
        self.assertEqual(prompt_position(1, 1, 100, 2), (70, 402, .65))
        g.phase, g.phase_ms = 2, 1600
        moving = heading_lines(g)
        self.assertGreater(moving[0][1], 110)
        g.phase_ms = 0
        self.assertEqual(heading_lines(g)[0][1], 110)
        g.phase = 6
        self.assertEqual(heading_lines(g), ())

    def test_decorative_clocks_banner_and_transition_survive_save_without_random_draws(self):
        r = tutorial_resources(); s = Session(r); s.advance()
        held, random = s.vm.snapshot(), s.engine.random.state
        for _ in range(5): s.tick(250)
        g = s.engine.word_grid
        self.assertEqual((g.visual_ms, g.banner.kind, g.banner.age_ms), (1250, 'ready', 250))
        saved = json.loads(json.dumps(s.snapshot()))
        restored = Session.from_snapshot(r, saved)
        for _ in range(20):
            s.tick(16); restored.tick(16)
            self.assertEqual(s.snapshot(), restored.snapshot())
        self.assertEqual(s.vm.snapshot(), held)
        self.assertEqual(s.engine.random.state, random)
        play_phase(s)
        s.answer()
        # Successful tutorial pages suppress ordinary success text.
        self.assertIsNone(g.banner)
        for _ in range(5): s.tick(250)
        self.assertEqual(g.phase, 4)
        self.assertEqual(g.transition.problem.tutorial_text, 'Touch to continue.')
        self.assertEqual(g.problem.tutorial_text, 'Trace the word.')
        saved = json.loads(json.dumps(s.snapshot()))
        restored = Session.from_snapshot(r, saved)
        self.assertEqual(restored.snapshot(), s.snapshot())
        for _ in range(40):
            s.tick(50); restored.tick(50)
            self.assertEqual(s.snapshot(), restored.snapshot())
        bad = copy.deepcopy(saved)
        bad['engine']['word_grid']['transition']['board'] = []
        with self.assertRaises(SaveError): Session.from_snapshot(r, bad)

    def test_version_six_grid_migration_keeps_board_vm_score_and_random_state(self):
        r = resources(tutorial=True); s = Session(r); s.advance(); play_phase(s)
        s.grid_pointer('down', 0); s.grid_pointer('move', 4)
        old = json.loads(json.dumps(s.snapshot())); old['version'] = 6
        for key in ('visual_ms', 'board_entry_ms', 'banner', 'transition'):
            del old['engine']['word_grid'][key]
        before = copy.deepcopy(old)
        restored = Session.from_snapshot(r, old)
        self.assertEqual(old, before)
        self.assertEqual(restored.vm.snapshot(), s.vm.snapshot())
        self.assertEqual(restored.engine.random, s.engine.random)
        g = restored.engine.word_grid
        self.assertEqual((g.board, g.selection, g.starts, g.score),
                         (s.engine.word_grid.board, [0, 4], [0, 3], 0))
        self.assertEqual((g.visual_ms, g.banner, g.transition), (0, None, None))
        self.assertEqual(g.board_entry_ms, 2000)

    def test_tile_entry_continues_through_target_banner_without_restarting(self):
        s = Session(resources()); s.advance()
        for _ in range(10): s.tick(250)
        g = s.engine.word_grid
        self.assertEqual((g.phase, g.board_entry_ms), (6, 0))
        for _ in range(7): s.tick(250)
        self.assertEqual((g.phase, g.board_entry_ms), (2, 1750))
        self.assertEqual(g.banner.kind, 'target')
        saved = s.snapshot()
        self.assertEqual(Session.from_snapshot(s.resources, saved).snapshot(), saved)
        s.tick(250)
        self.assertEqual(g.board_entry_ms, 2000)

    @unittest.skipUnless(importlib.util.find_spec('pygame') and Path('.shs-library/library.json').exists(),
                         'desktop extra and user library required')
    def test_original_assets_render_instruction_motion_pause_save_and_resized_grid_input(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        from exp_runtime.content import ContentLibrary
        from exp_runtime.desktop import Desktop
        self.addCleanup(pygame.quit)
        with ContentLibrary(Path('.shs-library')) as lib:
            r = lib.open_episode('The_New_Girl.exp')
            r.programs[25001] = tutorial_resources().program(25001)
            ui = Desktop(Session(r), audio=False)
            s = ui.session
            # Initial tutorial reveal begins after the native 3200ms delay.
            for _ in range(13): ui.tick(250)
            frames = set()
            held = s.vm.snapshot()
            for _ in range(20):
                ui.render(); self.assertIsNone(ui.error)
                frames.add(pygame.image.tobytes(ui.grid_renderer.canvas, 'RGB'))
                ui.tick(16)
            self.assertGreater(len(frames), 15)
            self.assertEqual(s.vm.snapshot(), held)
            saved = s.snapshot()
            ui.render(); pixels = pygame.image.tobytes(ui.grid_renderer.canvas, 'RGB')
            self.assertEqual(s.snapshot(), saved)
            ui.session = Session.from_snapshot(r, saved)
            ui.render()
            self.assertEqual(pygame.image.tobytes(ui.grid_renderer.canvas, 'RGB'), pixels)
            ui.command(('menu',)); ui.tick(1000)
            self.assertEqual(ui.session.snapshot(), saved)
            ui.command(('resume',))
            ui.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST)); ui.tick(1000)
            self.assertEqual(ui.session.snapshot(), saved)
            ui.handle_event(pygame.event.Event(pygame.WINDOWFOCUSGAINED))
            s = ui.session
            play_phase(s); s.answer(); play_phase(s)
            ui.window = pygame.display.set_mode((800, 600), pygame.RESIZABLE)
            ui.render(); self.assertIsNone(ui.error)
            for kind, index in ((pygame.MOUSEBUTTONDOWN, 0), (pygame.MOUSEMOTION, 1), (pygame.MOUSEMOTION, 2)):
                x, y = ui.grid_renderer.cells[index][1].center
                pos = (ui.viewport.x + x * ui.viewport.width / 320,
                       ui.viewport.y + y * ui.viewport.height / 480)
                ui.handle_event(pygame.event.Event(kind, button=1, pos=pos))
            self.assertEqual(s.engine.word_grid.score, 100)
            self.assertEqual(s.vm.snapshot(), held)
