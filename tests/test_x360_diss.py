"""exp_runtime.x360_diss: Diss Practice's rules, from MS4's Lua."""
from dataclasses import asdict
import importlib.util
import io
import json
import os
from types import SimpleNamespace
import unittest

from exp_runtime.x360_diss import (BAD, BLANK, COUNTDOWN, COUNTDOWN_MS, DEFAULT_VELOCITY, DOUBLE, ENDED, FIRE, INPUT_BLOCK_MS,
                                   NOTE, PUSH_MS, REMIX, SPIN_DOWN, TUTORIAL, TUTORIAL_MS, DissPractice, arm_angle, head)
from exp_runtime.x360_games import OPENING_MS, READY, RUNNING


class Dealer:
    """random.below in order, then notes (0) from there on, as a cap's re-roll needs something else to come up."""

    def __init__(self, *values):
        self.values = list(values)

    def below(self, n):
        return (self.values.pop(0) if self.values else 0) % n


def running(*deal):
    game = DissPractice()
    random = Dealer(*(deal or (0,)))
    game.tick(OPENING_MS + 20, random)
    game.press()
    game.tick(COUNTDOWN_MS + 40, random)
    return game, random


def under_head(game, index):
    """The record turned so element `index` waits at the arm's lowest reach."""
    import math
    from exp_runtime.x360_diss import ELEMENTS
    (hx, hz), _ = head(20)
    x, z = ELEMENTS[index]
    game.angle = math.degrees(math.atan2(x * hz - z * hx, x * hx + z * hz)) % 360


class FlowTests(unittest.TestCase):
    def test_it_waits_for_a_press_then_counts_down_with_input_blocked_past_it(self):
        game = DissPractice()
        random = Dealer(0)
        game.tick(OPENING_MS + 20, random)
        self.assertEqual(game.phase, READY)
        game.tick(5000, random)
        self.assertEqual(game.phase, READY)
        self.assertTrue(game.press())
        self.assertEqual(game.phase, COUNTDOWN)
        self.assertFalse(game.press())
        game.tick(COUNTDOWN_MS + 20, random)
        self.assertEqual(game.phase, RUNNING)
        self.assertEqual(game.total_time, 60)
        self.assertFalse(game.press())                  # BlockInputTimed(3) outlasts the countdown
        game.tick(INPUT_BLOCK_MS - COUNTDOWN_MS, random)
        self.assertTrue(game.press())

    def test_the_skip_prompts_play_is_the_go_ahead(self):
        game = DissPractice()
        game.start()
        random = Dealer(0)
        game.tick(OPENING_MS + 20, random)
        self.assertEqual(game.phase, COUNTDOWN)

    def test_the_first_practices_tutorial_is_held_for_a_press_and_starts_it(self):
        game = DissPractice.opened(True)
        random = Dealer(0)
        game.tick(OPENING_MS + 20, random)
        self.assertEqual(game.phase, TUTORIAL)
        self.assertFalse(game.press())                  # its cards are still coming in
        game.tick(TUTORIAL_MS, random)
        self.assertTrue(game.press())
        self.assertEqual(game.phase, COUNTDOWN)

    def test_time_runs_out_the_record_spins_down_and_the_score_shows(self):
        game, random = running()
        game.score = 700
        finished = False
        for _ in range(61):
            finished = game.tick(1000, random) or finished
        self.assertFalse(finished)
        self.assertIn(game.phase, (SPIN_DOWN, ENDED))
        self.assertEqual(game.total_time, 0)
        for _ in range(100):
            if game.tick(100, random):
                finished = True
                break
        self.assertTrue(finished)
        self.assertEqual(game.result, 700)

    def test_a_reversed_record_ends_the_spin_down_at_once(self):
        game, random = running()
        game.reversed, game.velocity = True, -40
        game.total_time, game.prev_total_ms = 1, game.now_ms
        game.tick(1000, random)
        self.assertEqual(game.phase, SPIN_DOWN)
        game.tick(20, random)
        self.assertEqual(game.phase, ENDED)

    def test_the_result_stays_in_a_word(self):
        game = DissPractice(score=900000)
        self.assertEqual(game.result, 32767)


class ArmTests(unittest.TestCase):
    def test_push_swings_out_then_in_in_a_quarter_of_the_animation(self):
        self.assertEqual(arm_angle(-1), 0)
        self.assertAlmostEqual(arm_angle(67 / 4), -8.26)
        self.assertAlmostEqual(arm_angle(367 / 4), 20)
        self.assertEqual(arm_angle(PUSH_MS), 0)
        self.assertLess(PUSH_MS, 250)

    def test_the_head_is_clear_of_the_notes_at_rest_and_reaches_them_at_the_swing(self):
        import math
        (x, z), _ = head(0)
        self.assertGreater(math.hypot(x, z) - .05, .85 + .075)
        (x, z), _ = head(20)
        self.assertAlmostEqual(math.hypot(x, z), .851, places=2)

    def test_a_press_restarts_the_swing_and_a_note_at_rest_isnt_caught(self):
        game, random = running()
        game.tick(INPUT_BLOCK_MS, random)
        under_head(game, 0)
        game.velocity = 0
        game.tick(500, random)
        self.assertEqual(game.score, 0)                 # no press: the head stays clear of it
        game.press()
        game.tick(30, random)
        at = game.arm_ms
        game.press()
        self.assertEqual(game.arm_ms, 0)
        self.assertGreater(at, 0)

    def test_a_press_catches_the_note_under_the_head_as_the_arm_comes_in(self):
        game, random = running(0)
        game.tick(INPUT_BLOCK_MS, random)
        under_head(game, 0)
        game.velocity = 0
        game.press()
        game.tick(60, random)
        self.assertEqual(game.score, 0)                 # still swinging out
        game.tick(60, random)
        self.assertEqual(game.score, 10)
        self.assertEqual(game.elements[0]['kind'], BLANK)
        self.assertEqual(game.effects[-1][0], 'good')

    def test_a_note_far_round_the_record_isnt_caught(self):
        game, random = running(0)
        game.tick(INPUT_BLOCK_MS, random)
        under_head(game, 0)
        game.angle += 22.5                              # half way between two of the eight
        game.velocity = 0
        game.press()
        game.tick(300, random)
        self.assertEqual(game.score, 0)


class RuleTests(unittest.TestCase):
    def test_a_good_note_scores_the_streak_times_the_tier_and_speeds_up(self):
        game, random = running()
        game._add_score((0, 0), random)
        game._add_score((0, 0), random)
        game._add_score((0, 0), random)
        self.assertEqual(game.score, 10 + 20 + 30)
        self.assertEqual(game.velocity, DEFAULT_VELOCITY + 30)
        self.assertEqual(game.streak, 4)
        self.assertEqual(game.popup[0], 3)

    def test_ten_in_a_row_brings_double_notes_and_twenty_on_fire_ones(self):
        game, random = running()
        for element in game.elements:
            element.update(kind=NOTE, shown=NOTE)
        for _ in range(10):
            game._add_score((0, 0), random)
        self.assertEqual(game.tier, 2)
        self.assertEqual({e['kind'] for e in game.elements}, {DOUBLE})
        for _ in range(11):
            game._add_score((0, 0), random)
        self.assertEqual(game.tier, 3)
        self.assertEqual({e['kind'] for e in game.elements}, {FIRE})

    def test_twenty_three_good_notes_are_the_least_that_pass(self):
        game, random = running()
        for _ in range(22):
            game._add_score((0, 0), random)
        self.assertLessEqual(game.score, 5000)
        game._add_score((0, 0), random)
        self.assertGreater(game.score, 5000)

    def test_a_broken_note_resets_streak_tier_and_speed(self):
        game, random = running()
        game.streak, game.tier, game.velocity = 9, 2, 150
        game.elements[0].update(kind=DOUBLE, shown=DOUBLE)
        game._bad_choice((0, 0))
        self.assertEqual((game.streak, game.tier, game.velocity), (1, 1, DEFAULT_VELOCITY))
        self.assertEqual(game.elements[0]['kind'], NOTE)

    def test_a_remix_swaps_good_and_broken_and_reverses_keeping_the_streak(self):
        game, random = running()
        game.elements[0].update(kind=NOTE, shown=NOTE)
        game.elements[1].update(kind=BAD, shown=BAD)
        game.elements[2].update(kind=BLANK, shown=BLANK)
        game.elements[3].update(kind=REMIX, shown=REMIX)
        game.streak, game.velocity = 5, 70
        game._change_direction((0, 0))
        self.assertEqual([e['kind'] for e in game.elements[:4]], [BAD, NOTE, BLANK, REMIX])
        self.assertEqual((game.velocity, game.reversed, game.streak), (-70, True, 5))

    def test_a_reversed_record_cant_bring_double_notes_but_a_streak_still_brings_on_fire(self):
        game, random = running()
        game.reversed, game.velocity, game.streak = True, -200, 5
        game._add_score((0, 0), random)
        self.assertEqual((game.tier, game.velocity), (1, -210))
        game.streak = 20
        game._add_score((0, 0), random)
        self.assertEqual(game.tier, 3)

    def test_speed_stops_at_its_top(self):
        game, random = running()
        game.velocity = 300
        game._add_score((0, 0), random)
        self.assertEqual(game.velocity, 300)

    def test_dealing_keeps_to_the_caps_of_broken_notes_and_remix_arrows(self):
        game, random = running(0)
        game.bad_count, game.remix_count = 6, 3
        element = game.elements[0]
        game._deal(element, Dealer(1, 2, 1, 0))
        self.assertEqual(element['kind'], NOTE)
        self.assertEqual((game.bad_count, game.remix_count), (6, 3))

    def test_a_new_good_note_takes_the_tiers_look(self):
        game, random = running()
        game.tier = 3
        element = game.elements[0]
        game._deal(element, Dealer(0))
        self.assertEqual(element['kind'], FIRE)

    def test_a_caught_note_goes_blank_after_three_frames_and_comes_back_two_seconds_on(self):
        # REBORN_SECONDS is 3, but Element:Step counts its first second at once: for those three frames the type is
        # blank and prevTotalTime is still the old one.
        game, random = running(0)
        game.velocity = 0
        element = game.elements[0]
        game.touched = 0
        game.touching = [0]
        game._check_touch(random)
        self.assertEqual((element['kind'], element['shown']), (BLANK, NOTE))
        game.tick(60, random)
        self.assertEqual(element['shown'], BLANK)
        game.tick(1900, random)
        self.assertEqual(element['kind'], BLANK)
        game.tick(200, random)
        self.assertEqual(element['kind'], NOTE)

    def test_a_save_holds_it(self):
        game, random = running(0, 1, 2)
        game.tick(4000, random)
        state = asdict(game)
        again = DissPractice(**state)
        again.validate()
        self.assertEqual(again, game)
        again.phase = 'nonsense'
        with self.assertRaises(ValueError):
            again.validate()


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class DrawingTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        pygame.init()
        pygame.display.set_mode((1, 1))
        self.pygame = pygame
        from exp_runtime.desktop_x360_diss import X360DissRenderer
        from test_nr_arena_x360 import library, x360_skin
        files = x360_skin(pygame, parts=True)
        spec = json.loads(files[26300])
        note = pygame.Surface((20, 40), pygame.SRCALPHA)
        note.fill((255, 0, 0, 255))
        out = io.BytesIO()
        pygame.image.save(note, out, 'x.png')
        files[26790] = out.getvalue()
        spec['booth']['parts']['camera'] = [-.0175, 3.0619, -11.7855, .6349, 18.7875, .9874, 20.875]
        spec['booth']['notes'] = dict(frame=[2560, 1440], height=.25, wheel=[-.1447, 1.0085, -7.8384], out=1.19, kinds={
            kind: dict(id=26790, anchor=[10, 20], depth=3.5) for kind in ('note', 'bad', 'swap', 'double')})
        files[26300] = json.dumps(spec).encode()
        self.renderer = X360DissRenderer(SimpleNamespace(library=library(files)))

    def draw(self, game):
        session = SimpleNamespace(engine=SimpleNamespace(x360_diss=game))
        self.renderer.draw(session)
        return self.renderer.canvas

    def test_the_deck_shows_and_a_note_only_once_dealt(self):
        game, random = running()
        for element in game.elements:
            element.update(kind=BLANK, shown=BLANK)
        empty = self.pygame.image.tobytes(self.draw(game), 'RGBA')
        game.elements[3].update(kind=NOTE, shown=NOTE, born_ms=game.now_ms - 5000)
        with_note = self.pygame.image.tobytes(self.draw(game), 'RGBA')
        self.assertNotEqual(empty, with_note)
        self.assertTrue(self.renderer.canvas.get_bounding_rect().height > 0)

    def test_a_note_nearer_the_camera_is_drawn_lower_and_larger(self):
        game, random = running()
        near = self.renderer._project(0, -.8)
        far = self.renderer._project(0, .8)
        self.assertLess(near[2], far[2])
        self.assertGreater(near[1], far[1])

    def test_every_phase_and_kind_draws(self):
        for tutorial in (True, False):
            game = DissPractice.opened(tutorial)
            random = Dealer()
            self.draw(game)
            game.tick(OPENING_MS + 20, random)
            self.draw(game)
            game.tick(TUTORIAL_MS, random)
            self.draw(game)
            game.press()
            game.tick(100, random)
            self.draw(game)
            game.tick(COUNTDOWN_MS, random)
            for kind, element in zip((NOTE, BAD, REMIX, DOUBLE, FIRE), game.elements):
                element.update(kind=kind, shown=kind)
            game.popup = [5, game.now_ms]
            game.effects.append(['good', 0, -.8, game.now_ms])
            game.effects.append(['swap', 0, -.8, game.now_ms])
            game.arm_ms = 90.0
            self.draw(game)
            self.assertEqual(len(self.renderer.effects), 2)
            self.draw(game)
            self.assertEqual(len(self.renderer.effects), 2)         # each effect starts once
            game.total_time = 1
            game.tick(1200, random)
            self.draw(game)

    def test_the_arm_drawn_is_the_arm_that_catches(self):
        game, random = running()
        self.renderer.game = game
        arm = self.renderer.x360()[0]['booth']['parts']['arm']
        game.arm_ms = 367 / 4
        angle = self.renderer._arm_frame(arm, 0)['angle']
        self.assertEqual(angle, max(frame['angle'] for frame in arm['frames']))
        game.arm_ms = -1
        rest = self.renderer._arm_frame(arm, 0)['angle']
        self.assertLess(rest, angle)


if __name__ == '__main__':
    unittest.main()
