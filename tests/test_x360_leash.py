"""The X360 translations' leash game: the prototype's rules, the session's part, the drawing and all four inputs."""
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from exp_runtime import x360_games as x
from exp_runtime.runtime import SaveError, Session
from exp_runtime.x360_games import LeashGame
from test_runtime import host_call
from test_vm import program

CODE = (*host_call(x.X360_LEASH), 0x21, 0x33)


def running(swap_ms=3000):
    game = LeashGame(swap_ms=swap_ms)
    game.tick(x.OPENING_MS)
    game.press()
    return game


def resources():
    from test_desktop import Resources
    return Resources(program(*CODE))


class RuleTests(unittest.TestCase):
    def test_it_opens_then_waits_for_a_press_however_long_it_takes(self):
        game = LeashGame(swap_ms=3000)
        self.assertFalse(game.press())                          # (one left over from the dialogue can't start it)
        game.tick(x.OPENING_MS)
        self.assertEqual(game.phase, x.READY)
        for _ in range(100):
            self.assertFalse(game.tick(250))
        self.assertEqual((game.phase, game.level), (x.READY, x.LEVEL_START))
        self.assertTrue(game.press())
        self.assertEqual(game.phase, x.RUNNING)
        self.assertFalse(game.press())

    def test_the_skip_prompts_play_is_its_go_ahead(self):
        game = LeashGame(swap_ms=3000)
        self.assertTrue(game.start())
        game.tick(x.OPENING_MS)
        self.assertEqual(game.phase, x.RUNNING)

    def test_doing_nothing_loses_in_about_four_seconds(self):
        game = running()
        for _ in range(4150 // 10):
            self.assertFalse(game.tick(10))
        self.assertEqual(game.phase, x.RUNNING)
        for _ in range(10):
            game.tick(10)
        self.assertEqual((game.phase, game.result), (x.CLOSING, 0))

    def test_a_shake_is_a_new_direction_on_the_same_axis_within_the_window(self):
        game = running()
        self.assertFalse(game.shake(x.LEFT))                    # the first direction has none before it
        game.tick(10)
        self.assertTrue(game.shake(x.RIGHT))
        self.assertEqual(game.level, x.LEVEL_START - 120 + x.LEVEL_GAIN)
        self.assertFalse(game.shake(x.RIGHT))                   # holding it isn't one
        game.tick(10)
        self.assertTrue(game.shake(x.LEFT))

    def test_a_frame_with_a_shake_doesnt_drain(self):
        game = running()
        game.shake(x.LEFT)
        game.shake(x.RIGHT)
        level = game.level
        game.tick(10)
        self.assertEqual(game.level, level)
        game.tick(10)
        self.assertEqual(game.level, level - 120)

    def test_too_slow_scores_nothing_but_the_next_quick_one_does(self):
        game = running()
        game.shake(x.LEFT)
        game.tick(x.SHAKE_WINDOW_MS)
        self.assertFalse(game.shake(x.RIGHT))
        self.assertEqual(game.since_ms, 0)                      # any new direction restarts the time
        game.tick(10)
        self.assertTrue(game.shake(x.LEFT))

    def test_the_stick_has_the_prototypes_shorter_window(self):
        game = running()
        game.shake(x.LEFT, x.SHAKE_WINDOW_STICK_MS)
        game.tick(100)
        self.assertFalse(game.shake(x.RIGHT, x.SHAKE_WINDOW_STICK_MS))
        game.tick(99)
        self.assertTrue(game.shake(x.LEFT, x.SHAKE_WINDOW_STICK_MS))

    def test_the_other_axis_scores_nothing_and_the_wanted_one_swaps_at_its_interval(self):
        game = running(swap_ms=2000)
        game.shake(x.UP)
        self.assertFalse(game.shake(x.DOWN))                    # left and right are wanted first
        self.assertFalse(game.shake(x.LEFT))                    # nor does changing axis count
        for _ in range(8):
            game.tick(250)
        self.assertEqual(game.wanted, x.UP_DOWN)
        game.shake(x.UP)
        self.assertTrue(game.shake(x.DOWN))
        for _ in range(8):
            game.tick(250)
        self.assertEqual(game.wanted, x.LEFT_RIGHT)             # the same interval, picked once

    def test_it_wins_at_100_and_ends_after_the_full_bar_has_faded(self):
        game = running()
        game.shake(x.LEFT)
        for turn in range(8):
            game.shake(x.RIGHT if turn % 2 == 0 else x.LEFT)
        self.assertEqual((game.phase, game.level, game.result), (x.CLOSING, x.LEVEL_FULL, 1))
        self.assertFalse(game.shake(x.LEFT))
        self.assertFalse(game.tick(100))
        self.assertTrue(game.tick(200))


class ServiceTests(unittest.TestCase):
    def play(self):
        session = Session(resources(), ephemeral=True)
        action = session.advance()
        self.assertEqual(action.name, 'x360_leash')
        return session

    def test_the_interval_is_two_to_five_seconds_from_the_games_randomness(self):
        seen = {self.play().engine.x360_leash.swap_ms}
        self.assertTrue(seen <= {2000, 3000, 4000, 5000})

    def test_a_press_is_the_sessions_answer(self):
        session = self.play()
        session.tick(250)
        session.tick(250)
        self.assertTrue(session.minigame_unstarted)
        session.answer(None)
        self.assertFalse(session.minigame_unstarted)
        self.assertEqual(session.engine.x360_leash.phase, x.RUNNING)
        with self.assertRaises(ValueError):
            session.answer(3)

    def test_it_ends_and_the_story_goes_on_without_it(self):
        session = self.play()
        session.engine.x360_leash.start()
        for _ in range(800):
            if session.pending is None or session.pending.name != 'x360_leash':
                break
            session.tick(30)
        self.assertIsNone(session.engine.x360_leash)

    def test_a_game_in_progress_saves_and_comes_back_where_it_was(self):
        session = self.play()
        session.tick(250)
        session.tick(250)
        session.answer(None)
        session.engine.x360_leash.shake(x.LEFT)
        state = json.loads(json.dumps(session.snapshot()))
        self.assertEqual(state['version'], 37)
        again = Session.from_snapshot(resources(), state)
        self.assertEqual(again.engine.x360_leash, session.engine.x360_leash)
        self.assertEqual(again.pending.name, 'x360_leash')

    def test_a_damaged_save_is_refused(self):
        state = json.loads(json.dumps(self.play().snapshot()))
        state['engine']['x360_leash']['level'] = -1
        with self.assertRaises(SaveError):
            Session.from_snapshot(resources(), state)

    def test_an_older_save_has_none(self):
        state = json.loads(json.dumps(Session(resources(), ephemeral=True).snapshot()))
        state['version'] = 31
        del state['engine']['x360_leash']
        self.assertIsNone(Session.from_snapshot(resources(), state).engine.x360_leash)

    def test_the_skip_is_win_or_lose(self):
        session = self.play()
        session.skip_minigame(True)
        self.assertIsNone(session.engine.x360_leash)


class PlayerTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        pygame.init()
        pygame.display.set_mode((64, 64))
        self.pygame = pygame

    def skin(self):
        import exp_runtime.desktop_nr_arena_x360 as arena
        pygame = self.pygame
        out = {}

        def png(resource, colour=(10, 200, 10, 255), size=(64, 64)):
            surface = pygame.Surface(size, pygame.SRCALPHA)
            surface.fill(colour)
            buffer = io.BytesIO()
            pygame.image.save(surface, buffer, 'x.png')
            out[resource] = buffer.getvalue()
            return resource
        spec = dict(pictures=dict(power_bar=png(1, (90, 90, 90, 255), (32, 8))),
                    slot=dict(font=dict(line_height=12, base=10, kerning={}, pages=[png(2, (0, 0, 0, 255))],
                                        chars={str(ord(ch)): [0, 0, 8, 10, 0, 0, 9, 0]
                                               for ch in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz !'})),
                    leash=dict(fill=png(3, (220, 30, 20, 255), (32, 8)), arrows=dict(leftright=png(4), updown=png(5)),
                               stick=dict(leftright=png(6), updown=png(7))))
        archive = SimpleNamespace(read=out.__getitem__)
        real = arena.addon_skin
        arena.addon_skin = lambda _: (spec, archive)
        self.addCleanup(setattr, arena, 'addon_skin', real)
        import exp_runtime.desktop_x360_slot as slot
        real_slot = slot.addon_skin
        slot.addon_skin = lambda _: (spec, archive)
        self.addCleanup(setattr, slot, 'addon_skin', real_slot)
        return SimpleNamespace()

    def test_it_draws_every_phase_in_the_whole_frame_and_the_bar_fills_with_the_level(self):
        from exp_runtime.desktop_x360_leash import BAR_CENTRE, BAR_SIZE, FRAME, X360LeashRenderer
        renderer = X360LeashRenderer(self.skin())
        game = LeashGame(swap_ms=3000)
        session = SimpleNamespace(engine=SimpleNamespace(x360_leash=game))
        renderer.draw(session)
        self.assertEqual(renderer.canvas.get_size(), FRAME)
        self.assertAlmostEqual(renderer.alpha(game), 0, delta=.01)
        game.tick(x.OPENING_MS)
        renderer.draw(session)
        self.assertIsNone(renderer.alpha(game))
        waiting = renderer.canvas.get_bounding_rect()
        game.press()
        renderer.draw(session)
        self.assertLess(waiting.left, renderer.canvas.get_bounding_rect().left)     # the prompt is gone
        x0, bottom = BAR_CENTRE[0], BAR_CENTRE[1] + BAR_SIZE[1] // 2
        red = (220, 30, 20)
        self.assertEqual(renderer.canvas.get_at((x0, bottom - 20))[:3], red)
        self.assertNotEqual(renderer.canvas.get_at((x0, BAR_CENTRE[1] - 20))[:3], red)
        game.level = x.LEVEL_FULL
        renderer.draw(session)
        self.assertEqual(renderer.canvas.get_at((x0, BAR_CENTRE[1] - BAR_SIZE[1] // 2 + 20))[:3], red)
        game.phase, game.phase_ms = x.CLOSING, 150
        self.assertAlmostEqual(renderer.alpha(game), .5)

    def test_the_stick_reads_past_three_quarters_and_left_and_right_come_first(self):
        from exp_runtime.desktop_x360_leash import stick_direction
        self.assertIsNone(stick_direction(.7, -.7))
        self.assertEqual(stick_direction(.8, 0), x.RIGHT)
        self.assertEqual(stick_direction(-.8, .9), x.LEFT)
        self.assertEqual(stick_direction(.1, -.8), x.UP)
        self.assertEqual(stick_direction(.1, .8), x.DOWN)

    def test_a_drag_needs_some_distance_and_goes_by_its_longer_side(self):
        from exp_runtime.desktop_x360_leash import DRAG_UNITS, drag_direction
        self.assertIsNone(drag_direction((100, 100), 100 + DRAG_UNITS - 1, 100))
        self.assertEqual(drag_direction((100, 100), 100 + DRAG_UNITS, 120), x.RIGHT)
        self.assertEqual(drag_direction((100, 100), 100 - DRAG_UNITS, 100), x.LEFT)
        self.assertEqual(drag_direction((100, 100), 110, 100 - DRAG_UNITS), x.UP)
        self.assertEqual(drag_direction((100, 100), 110, 100 + DRAG_UNITS), x.DOWN)

    def desktop(self, temporary):
        from exp_runtime.desktop import Desktop
        story = resources()
        story.library.directory = Path(temporary)
        session = Session(story, ephemeral=True)
        session.advance()
        ui = Desktop(session, audio=False)
        ui.bg_viewport = self.pygame.Rect(100, 20, 384, 512)    # (where the story last drew)
        for _ in range(3):
            session.tick(250)
        return ui, session.engine.x360_leash

    def test_a_click_starts_it_a_drag_shakes_it_and_the_gear_opens_the_menu(self):
        import tempfile
        pygame = self.pygame
        with tempfile.TemporaryDirectory() as temporary:
            ui, game = self.desktop(temporary)
            frame = ui.bg_viewport

            def event(kind, x, y, **more):
                ui.handle_event(pygame.event.Event(kind, pos=(frame.x + x // 2, frame.y + y // 2), **more))
            event(pygame.MOUSEMOTION, 300, 300, rel=(0, 0), buttons=(0, 0, 0))
            self.assertEqual(game.phase, x.READY)
            event(pygame.MOUSEBUTTONDOWN, 300, 300, button=1)
            self.assertEqual(game.phase, x.RUNNING)
            event(pygame.MOUSEMOTION, 200, 300, rel=(0, 0), buttons=(1, 0, 0))
            self.assertEqual(game.last, x.LEFT)
            level = game.level
            event(pygame.MOUSEMOTION, 300, 300, rel=(0, 0), buttons=(1, 0, 0))
            self.assertEqual((game.last, game.level), (x.RIGHT, level + x.LEVEL_GAIN))
            event(pygame.MOUSEBUTTONUP, 300, 300, button=1)
            event(pygame.MOUSEMOTION, 100, 300, rel=(0, 0), buttons=(0, 0, 0))
            self.assertEqual(game.last, x.RIGHT)                # moving without holding isn't a shake
            event(pygame.MOUSEBUTTONDOWN, 40, 980, button=1)
            self.assertTrue(ui.menu_open)

    def test_keys_shake_it_and_ok_only_starts_it(self):
        import tempfile
        pygame = self.pygame
        with tempfile.TemporaryDirectory() as temporary:
            ui, game = self.desktop(temporary)

            def key(code):
                ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=code, mod=0, unicode=''))
            key(pygame.K_LEFT)
            self.assertIsNone(game.last)                        # it hasn't started
            key(pygame.K_RETURN)
            self.assertEqual(game.phase, x.RUNNING)
            key(pygame.K_a)
            self.assertEqual(game.last, x.LEFT)
            key(pygame.K_RIGHT)
            self.assertEqual(game.level, x.LEVEL_START + x.LEVEL_GAIN)
            key(pygame.K_w)
            self.assertEqual(game.last, x.UP)

    def test_a_d_pad_shakes_it_but_the_sticks_arrow_keys_dont(self):
        import tempfile
        from exp_runtime.gamepad import key_event
        from exp_runtime import desktop
        pygame = self.pygame
        pads = SimpleNamespace(holding=Mock(side_effect=lambda button: button == 'left'), sticks={})
        with tempfile.TemporaryDirectory() as temporary:
            ui, game = self.desktop(temporary)
            game.press()
            real = desktop.pygame.gamepads
            desktop.pygame.gamepads = lambda: pads
            self.addCleanup(setattr, desktop.pygame, 'gamepads', real)
            ui.handle_event(key_event(pygame.K_RIGHT, 'right'))
            self.assertIsNone(game.last)                        # not held: the stick's own arrow
            ui.handle_event(key_event(pygame.K_LEFT, 'left'))
            self.assertEqual(game.last, x.LEFT)

    def test_a_stick_is_read_each_frame_with_the_prototypes_window(self):
        import tempfile
        from exp_runtime import desktop
        pads = SimpleNamespace(sticks={1: [-.9, 0.]})
        with tempfile.TemporaryDirectory() as temporary:
            ui, game = self.desktop(temporary)
            game.press()
            real = desktop.pygame.gamepads
            desktop.pygame.gamepads = lambda: pads
            self.addCleanup(setattr, desktop.pygame, 'gamepads', real)
            ui._leash_stick()
            self.assertEqual(game.last, x.LEFT)
            pads.sticks[1] = [.9, 0.]
            game.since_ms = 99
            ui._leash_stick()
            self.assertEqual((game.last, game.level), (x.RIGHT, x.LEVEL_START + x.LEVEL_GAIN))
            pads.sticks[1] = [-.9, 0.]
            game.since_ms = 100                                 # a key or a drag would still have time; a stick hasn't
            ui._leash_stick()
            self.assertEqual((game.last, game.level), (x.LEFT, x.LEVEL_START + x.LEVEL_GAIN))

    def test_nothing_shakes_it_under_the_menu(self):
        import tempfile
        pygame = self.pygame
        with tempfile.TemporaryDirectory() as temporary:
            ui, game = self.desktop(temporary)
            game.press()
            ui.menu_open = True
            ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_LEFT, mod=0, unicode=''))
            self.assertIsNone(game.last)
            ui.leash_anchor = (1, 1)
            ui._leash_stick()
            self.assertIsNone(ui.leash_anchor)


if __name__ == '__main__':
    unittest.main()
