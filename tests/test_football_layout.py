"""Authored football scenarios; optional rendering uses the player's APK."""
import copy
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest

from exp_runtime.shs.football import FootballTarget, Play
from exp_runtime.shs.football_layout import (countdown_motion, feedback_motion, feedback_text,
                                         footer_id, heading_id, help_motion, legend_codes,
                                         target_position, team_name, yard_glyphs, score_strip)
from exp_runtime.runtime import SaveError, Session
from test_football import resources, start_play, wait_for


PRESENTATION_FIELDS = ('visual_ms', 'camera_position', 'hud_position', 'message_ids',
                       'message_values', 'message_hold_ms', 'effects')


def game_session():
    s = Session(resources(100, 100, home=0, away=0))
    s.advance()
    return s


class FootballLayoutTests(unittest.TestCase):
    def test_scoreboard_keeps_team_names_and_both_scores_on_one_row(self):
        from exp_runtime.shs.desktop_football import FootballRenderer
        renderer = FootballRenderer.__new__(FootballRenderer)
        widths = {'You': 21, 'Opp': 23, '14': 15, '7': 8, '-': 5}
        font = SimpleNamespace(width=lambda text: widths[text])
        renderer.score_font = lambda: (font, None)
        renderer.strings = lambda: {167: 'You', 168: 'Opp'}
        renderer.atlas = lambda: SimpleNamespace(literals=lambda frame: ((0, -154, -8),))
        renderer.score_text = lambda text: text
        strips, placed = [], []
        renderer.composite = lambda *args: strips.append(args)
        renderer.canvas = SimpleNamespace(blit=lambda image, point: placed.append((image, point)))
        renderer.scoreboard(SimpleNamespace(teams=[1, 2], home=14, away=7))
        self.assertEqual(strips, [(-38, 253, 50)])
        self.assertEqual(placed, [('You', (123, 42)), ('14', (149, 42)),
                                  ('-', (169, 42)), ('7', (183, 42)), ('Opp', (200, 42))])
        self.assertEqual([score_strip(w, 0) for w in (0, 9, 10, 31, 32)],
                         [(-40, 51), (-40, 51), (-39, 62), (-39, 62), (-38, 73)])

    def test_team_and_help_content_follow_all_six_script_plans(self):
        g = game_session().engine.football
        strings = {i: f'Label {i}' for i in range(42, 180)}
        self.assertEqual([team_name(strings, i) for i in (0, 1, 3, 9, 10, 255)],
                         ['', 'Label 167', 'Label 169', 'Label 175', '', ''])
        for half in (1, 2, 3):
            for defense in (False, True):
                g.half, g.defense = half, defense
                idx = (half - 1) * 2 + defense
                g.plans[idx] = [Play(4, 0, 0, 1), Play(3, 0, 0, 0), Play(2, 12, 0, 1),
                                Play(6, 12, 0, 1), Play(1, 14, 0, 1), Play(7, 14, 0, 1)]
                self.assertEqual(legend_codes(g), (4, 3, 2, 1))
                self.assertEqual(heading_id(g), (176, 178, 177, 179, 71, 72)[idx])
                g.phase = 3
                self.assertEqual(footer_id(g), 74 if defense else 73)

    def test_instruction_motion_and_countdown_keep_the_native_input_gate(self):
        s = game_session(); g = s.engine.football
        initial = help_motion(g, 92)
        self.assertEqual((initial.x, initial.y, initial.scale, initial.alpha), (320., 440., 0., 0.))
        s.tick(250)
        self.assertGreater(help_motion(g, 92).scale, 0)
        for _ in range(13): s.tick(250)
        self.assertIsNone(footer_id(g))
        s.answer(); self.assertEqual(g.phase, 20)
        s.tick(1)
        self.assertEqual(footer_id(g), 75)
        self.assertEqual(help_motion(g, 92).coach_x, 228)
        s.answer(); self.assertEqual(g.phase, 25)
        s.tick(250)
        self.assertGreater(help_motion(g, 92).coach_x, 228)
        self.assertEqual([countdown_motion(ms).frame for ms in (2100, 1500, 900, 300)], [4, 3, 2, 5])
        self.assertEqual(countdown_motion(2400).alpha, 0)
        self.assertAlmostEqual(countdown_motion(300).scale, 1 / 1.3)
        self.assertAlmostEqual(countdown_motion(300).alpha, 1 / 1.8)
        self.assertGreater(countdown_motion(120).angle, 0)

    def test_an_explicit_frame_width_moves_the_coachs_resting_edge_with_it(self):
        """The HD renderer's own 768-wide frame, not this module's native 320 (`desktop_football_hd.py`'s own
        coach art is independently measured, not an SD image scaled up) -- a regression test for the coach
        resting far short of the HD frame's own right edge instead of flush against it."""
        s = game_session(); g = s.engine.football
        for _ in range(14): s.tick(250)
        s.answer(); s.tick(1)
        self.assertEqual(help_motion(g, 92, frame_width=320).coach_x, 228)     # unchanged default: 320 - 92
        self.assertEqual(help_motion(g, 92, frame_width=768).coach_x, 676)     # HD frame: 768 - 92

    def test_feedback_uses_native_yardage_next_down_scores_and_half_results(self):
        s = game_session(); g = s.engine.football
        strings = {i: f'Text {i}' for i in range(42, 180)}
        strings[58], strings[62], strings[63] = 'GAIN %d', 'RUN %d +5', 'PASS %d +5'
        g.apply_play(1, 12, s.engine.random)
        self.assertEqual((g.message_ids, g.message_values, g.message_hold_ms), ([58, 50], [12, 1000], 0))
        self.assertEqual(feedback_text(g, strings, 0), 'GAIN 12')
        g.apply_play(6, 4, s.engine.random)
        self.assertEqual(feedback_text(g, strings, 0), 'PASS 4 +5')
        g.apply_play(7, 3, s.engine.random)
        self.assertEqual(feedback_text(g, strings, 0), 'RUN 3 +5')
        g.apply_play(3, 0, s.engine.random)
        self.assertEqual(g.message_ids, [58, 55])
        g.defense = True; g.down = 0
        g.apply_play(-6, 100, s.engine.random)
        self.assertEqual((g.message_ids, g.message_values), ([61, 50], [0, 1000]))
        g.apply_play(-4, 0, s.engine.random)
        self.assertEqual(g.message_ids, [60, 55])
        g.defense = False; g.position = 4
        g.apply_play(1, 4, s.engine.random)
        self.assertEqual(g.message_ids, [48, -102])
        self.assertEqual(feedback_text(g, strings, 1), 'Text 167: 7\nText 168: 0')
        g.half = 1; g.end_half(); self.assertEqual(g.message_ids, [42, -102])
        g.half = 2; g.end_half(); self.assertEqual(g.message_ids, [57, -102, 44])
        g.home = g.away; g.end_half(); self.assertEqual(g.message_ids, [57, -102, 43])
        g.half = 3; g.away += 7; g.end_half(); self.assertEqual(g.message_ids, [-102, 45])

    def test_message_animation_visits_each_message_without_resuming_the_vm(self):
        s = game_session(); g = s.engine.football
        g.half = 2; g.end_half()
        held, random = s.vm.snapshot(), copy.deepcopy(s.engine.random)
        first = feedback_motion(g)
        self.assertEqual((first.x, first.scale, first.visible), (-423., 0., False))
        seen = set()
        for _ in range(600):
            motion = feedback_motion(g)
            if motion is None:
                break
            if motion.visible: seen.add(motion.index)
            s.tick(16)
            self.assertEqual(s.vm.snapshot(), held)
        self.assertEqual(seen, {0, 1, 2})
        self.assertEqual(s.engine.random, random)
        # Ordinary plays hold for zero ms; result/score announcements for 800.
        g.apply_play(3, 0, s.engine.random)
        g.tick_message(800); self.assertEqual(g.message_phase, 1)
        g.tick_message(300); self.assertEqual((g.message_phase, g.message_ms), (2, 0))
        g.tick_message(16); self.assertEqual(g.message_phase, 3)

    def test_camera_effects_and_feedback_save_without_replaying_play_or_random(self):
        s = game_session(); g = s.engine.football
        g.plans[0] = [Play(1, 12, 0, 1)]
        start_play(s)
        wait_for(s, lambda: any(t.phase == 3 for t in g.targets))
        index = next(i for i,t in enumerate(g.targets) if t.phase == 3)
        held, random = s.vm.snapshot(), copy.deepcopy(s.engine.random)
        clock = g.remaining_ms
        s.answer(index)
        self.assertEqual((g.position, g.camera_position, g.hud_position, g.score), (48, 60., 60., 24))
        self.assertEqual(sum(e.selected for e in g.effects), 1)
        s.tick(16)
        self.assertGreater(g.camera_position, 48)
        self.assertLess(g.camera_position, 60)
        self.assertEqual(g.remaining_ms, clock)
        saved = json.loads(json.dumps(s.snapshot())); restored = Session.from_snapshot(s.resources, saved)
        self.assertEqual(restored.snapshot(), s.snapshot())
        for _ in range(90):
            s.tick(16); restored.tick(16)
            self.assertEqual(s.snapshot(), restored.snapshot())
        self.assertEqual(s.engine.random, random)
        self.assertEqual(s.vm.snapshot(), held)
        for key, value in (('camera_position', float('nan')), ('hud_position', float('inf')),
                           ('message_ids', [1]), ('message_hold_ms', 20), ('visual_ms', -1)):
            bad = copy.deepcopy(saved); bad['engine']['football'][key] = value
            with self.subTest(key=key), self.assertRaises(SaveError): Session.from_snapshot(s.resources, bad)
        bad = copy.deepcopy(saved); bad['engine']['football']['effects'][0]['remaining_ms'] = 9000
        with self.assertRaises(SaveError): Session.from_snapshot(s.resources, bad)

    def test_version_seven_migration_preserves_recorded_feedback_and_vm(self):
        s = game_session(); g = s.engine.football
        g.apply_play(1, 10, s.engine.random); s.tick(33)
        old = json.loads(json.dumps(s.snapshot())); old['version'] = 7
        for key in PRESENTATION_FIELDS: del old['engine']['football'][key]
        before = copy.deepcopy(old)
        restored = Session.from_snapshot(s.resources, old)
        self.assertEqual(old, before)
        self.assertEqual(restored.vm.snapshot(), s.vm.snapshot())
        self.assertEqual(restored.engine.random, s.engine.random)
        migrated = restored.engine.football
        self.assertEqual((migrated.phase, migrated.message_phase, migrated.message_ms),
                         (g.phase, g.message_phase, g.message_ms))
        self.assertEqual(migrated.camera_position, 50.)
        self.assertEqual(feedback_text(migrated, {}, 0), g.message)
        migrated.apply_play(3, 0, restored.engine.random)
        self.assertTrue(migrated.message_ids)

    def test_target_coordinates_keep_fixed_bounds_and_slanted_yardage(self):
        target = FootballTarget(1, 12, 0, 800, phase=3, elapsed_ms=400)
        x, y = target_position(target, (60, 220))
        self.assertEqual(x, 25)
        self.assertAlmostEqual(y, 170.5)
        glyphs = yard_glyphs(12, 60, 182)
        self.assertEqual([g[0] for g in glyphs], [-23, -24, -33])
        self.assertGreater(glyphs[1][2], glyphs[0][2])
        self.assertEqual([g[0] for g in yard_glyphs(-8, 60, 182)], [-14, -17])

    @unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra required')
    def test_sprite_node_does_not_apply_composite_origin_twice(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'; os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        from exp_runtime.shs.desktop_football import FootballRenderer
        pygame.init(); pygame.display.set_mode((320, 480)); self.addCleanup(pygame.quit)
        renderer = FootballRenderer(None, None, None)
        renderer.atlas = lambda: SimpleNamespace(literals=lambda i: ((0, -40, -32),))
        square = pygame.Surface((60, 60)); square.fill('white')
        renderer.frame = lambda i: square
        renderer.canvas.fill('black'); renderer.node(-47, 25, 167)
        bounds = pygame.mask.from_threshold(renderer.canvas, 'white', (1, 1, 1, 255)).get_bounding_rects()
        self.assertEqual(bounds, [pygame.Rect(25, 167, 60, 60)])
        renderer.canvas.fill('black'); renderer.node(-47, 25, 167, scale=.5)
        bounds = pygame.mask.from_threshold(renderer.canvas, 'white', (1, 1, 1, 255)).get_bounding_rects()
        self.assertEqual(bounds, [pygame.Rect(40, 182, 30, 30)])
        for point, expected in (((25, 167), 0), ((95, 237), 0), ((96, 237), None), ((300, 300), None)):
            self.assertEqual(renderer.hit(point), expected)
        # The clock's colon has four extra pixels of advance. Omitting them
        # lets the next digit cover the colon even though total width fits.
        renderer.frame = lambda i: pygame.Surface((2, 7) if i == 150 else (4, 10) if i == 129 else (7, 11))
        placed = []
        renderer.blit = lambda image, x, y: placed.append((image.get_width(), x, y))
        renderer.hud_digits('0:01', 165, 37, clock=True)
        self.assertGreater(placed[2][1], placed[1][1] + placed[1][0])

    @unittest.skipUnless(importlib.util.find_spec('pygame') and Path('.shs-library/library.json').exists(),
                         'desktop extra and user library required')
    def test_original_assets_render_save_pause_and_resized_target_input(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'; os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        from exp_runtime.content import ContentLibrary
        from exp_runtime.desktop import Desktop
        self.addCleanup(pygame.quit)
        with ContentLibrary(Path('.shs-library')) as lib:
            r = lib.open_episode('Football_Star.exp')
            r.programs[25001] = resources(100, 100).program(25001)
            ui = Desktop(Session(r), audio=False)
            s = ui.session; g = s.engine.football
            frames = set()
            held = s.vm.snapshot()
            for _ in range(35):
                ui.tick(16); ui.render(); self.assertIsNone(ui.error)
                frames.add(pygame.image.tobytes(ui.football_renderer.canvas, 'RGB'))
            self.assertGreater(len(frames), 30)
            start_play(s)
            wait_for(s, lambda: all(t.phase in (3, 6) for t in g.targets))
            ui.render(); saved = json.loads(json.dumps(s.snapshot()))
            pixels = pygame.image.tobytes(ui.football_renderer.canvas, 'RGB')
            ui.session = Session.from_snapshot(r, saved); ui.render()
            self.assertEqual(pygame.image.tobytes(ui.football_renderer.canvas, 'RGB'), pixels)
            saved = ui.session.snapshot()
            ui.command(('menu',)); ui.tick(1000)
            self.assertEqual(ui.session.snapshot(), saved)
            ui.command(('resume',))
            ui.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST)); ui.tick(1000)
            self.assertEqual(ui.session.snapshot(), saved)
            ui.handle_event(pygame.event.Event(pygame.WINDOWFOCUSGAINED))
            ui.window = pygame.display.set_mode((800, 600), pygame.RESIZABLE); ui.render()
            pos = (ui.viewport.x + 60 * ui.viewport.width / 320,
                   ui.viewport.y + 200 * ui.viewport.height / 480)
            ui.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
            self.assertEqual(ui.session.engine.football.down, 1)
            self.assertEqual(ui.session.vm.snapshot(), held)
            for _ in range(160):
                ui.tick(16); ui.render(); self.assertIsNone(ui.error)
            self.assertEqual(ui.session.engine.football.effects, [])
