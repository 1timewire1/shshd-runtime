"""Explicit minigame cheats retain the real VM callback and input boundaries."""
import copy
import importlib.util
import json
import os
import unittest
from unittest.mock import Mock

from exp_runtime.runtime import SaveError, Session
from test_football import resources as football_resources
from test_minigames import word_resources
from test_runtime import Resources, branching_program, host_call, text_words
from test_vm import program
from test_word_grid import resources as grid_resources


FACTORIES = (football_resources, grid_resources, word_resources)


class MinigameSkipTests(unittest.TestCase):
    def test_word_selection_returns_score_and_result_cell_for_both_games(self):
        for game in ('shs', 'cod'):
            for success in (False, True):
                with self.subTest(game=game, success=success):
                    resources = word_resources()
                    resources.library.game_id = game
                    session = Session(resources); session.advance()
                    session.engine.result_cells[1:] = [2, 3, 4]
                    random = copy.deepcopy((session.engine.random, session.engine.random48))
                    result = session.skip_minigame(success)
                    score = 32767 if success else 0
                    self.assertEqual(result.request.args, (score,))
                    self.assertEqual(session.engine.result_cells, [score, 2, 3, 4])
                    self.assertIsNone(session.engine.word_game)
                    self.assertEqual((session.engine.random, session.engine.random48), random)

    def test_football_winner_matches_both_score_queries_without_overflow(self):
        for home, away in ((0, 0), (5, 3), (21, 28), (32767, 32767)):
            for success in (False, True):
                with self.subTest(scores=(home, away), success=success):
                    session = Session(football_resources(home=home, away=away)); session.advance()
                    session.engine.result_cells[0] = 37
                    random = copy.deepcopy(session.engine.random)
                    result = session.skip_minigame(success)
                    difference, final_home, final_away = result.request.args
                    self.assertEqual(difference, final_home - final_away)
                    self.assertEqual(difference > 0, success)
                    self.assertGreaterEqual(abs(difference), 7)
                    self.assertTrue(all(0 <= value <= 32767 for value in (final_home, final_away)))
                    self.assertEqual(session.engine.football_scores, [final_home, final_away])
                    self.assertEqual(session.engine.result_cells[0], 37)
                    self.assertIsNone(session.engine.football)
                    self.assertEqual(session.engine.random, random)

    def test_grid_returns_success_or_failure_even_for_zero_target_tutorials(self):
        for tutorial in (False, True):
            for target in (0, 200):
                for success in (False, True):
                    session = Session(grid_resources(tutorial=tutorial)); session.advance()
                    session.engine.word_grid.target = target
                    session.engine.result_cells[0] = 37
                    random = copy.deepcopy(session.engine.random)
                    result = session.skip_minigame(success)
                    self.assertEqual(result.request.args, (int(success),))
                    self.assertEqual(session.engine.result_cells[0], 37)
                    self.assertIsNone(session.engine.word_grid)
                    self.assertEqual(session.engine.random, random)

    def test_hold_freezes_before_entry_and_play_decision_survives_save(self):
        for factory in FACTORIES:
            with self.subTest(factory=factory):
                session = Session(factory()); session.advance()
                self.assertTrue(session.minigame_unstarted)
                frozen = session.snapshot()
                session.tick(60000, pause_minigame=True)
                self.assertEqual(session.snapshot(), frozen)
                session = Session.from_snapshot(session.resources, json.loads(json.dumps(frozen)))
                self.assertTrue(session.minigame_unstarted)
                session.start_minigame()
                self.assertFalse(session.minigame_unstarted)
                session = Session.from_snapshot(session.resources, session.snapshot())
                self.assertFalse(session.minigame_unstarted)
                before = session.snapshot()
                session.tick(250)
                self.assertNotEqual(session.snapshot(), before)
                # Old saves already in play must not acquire an entry prompt.
                session.pending.details.pop('minigame_started')
                self.assertFalse(Session.from_snapshot(session.resources, session.snapshot()).minigame_unstarted)

    def test_invalid_started_marker_and_skip_arguments_leave_live_state_intact(self):
        for factory in FACTORIES:
            session = Session(factory()); session.advance()
            frozen = session.snapshot()
            for invalid in (None, 0, 1, 'true'):
                with self.assertRaises(ValueError):
                    session.skip_minigame(invalid)
                self.assertEqual(session.snapshot(), frozen)
                bad = copy.deepcopy(frozen)
                bad['pending']['details']['minigame_started'] = invalid
                with self.assertRaises(SaveError):
                    Session.from_snapshot(session.resources, bad)

    def test_story_choices_and_unknown_services_are_never_skippable(self):
        scripts = [branching_program(timeout) for timeout in (0, 1000)]
        scripts += [program(*host_call(254, 123))]
        for script in scripts:
            session = Session(Resources(script)); session.advance()
            frozen = session.snapshot()
            self.assertFalse(session.minigame_unstarted)
            for success in (False, True):
                with self.assertRaises(ValueError):
                    session.skip_minigame(success)
                self.assertEqual(session.snapshot(), frozen)
            if session.pending.name == 'choice' and session.remaining_ms:
                session.tick(1001, pause_minigame=True)
                self.assertEqual(session.pending.details['raw_text'], 'Went right.')

    def test_skipped_word_callback_survives_native_fade_and_save(self):
        for game in ('shs', 'cod'):
            session = Session(word_resources()); session.resources.library.game_id = game
            session = Session(session.resources); session.advance()
            session.engine.scene_value = 1
            held = session.vm.snapshot()
            session.skip_minigame(True)
            self.assertTrue(session.transitioning)
            self.assertEqual(session.vm.snapshot(), held)
            session = Session.from_snapshot(session.resources, session.snapshot())
            self.assertFalse(session.minigame_unstarted)
            while session.transitioning:
                session.tick(1800)
            self.assertEqual(session.pending.request.args, (32767,))
            self.assertEqual(session.engine.result_cells[0], 32767)
            finished = session.snapshot()
            session.tick(1000)
            self.assertEqual(session.snapshot(), finished)

    def test_incoming_fade_finishes_while_new_game_remains_frozen(self):
        words, refs = text_words('Before.', 'Title', 'Pick', 'yes|right', 'no|wrong|bad')
        resources = Resources(program(*host_call(16, 1), *host_call(13, refs[0], 0),
            *host_call(71, *refs[1:], 20000, -1, 1, 3000), 0x33, words=words))
        resources.library.game_id = 'cod'
        session = Session(resources); session.advance(); session.tick(4000); session.answer()
        session.tick(1800)
        self.assertEqual(session.pending.name, 'word_game')
        self.assertTrue(session.transitioning)
        initial = copy.deepcopy(session.engine.word_game)
        session.tick(1800, pause_minigame=True)
        self.assertFalse(session.transitioning)
        self.assertEqual(session.engine.word_game, initial)
        # (CoD's quiz is the iOS action menu in this fork, with its own entry clocks, so exp-runtime's
        # `minigame_unstarted` test of the Android ones does not apply.)


@unittest.skip("exp-runtime's Minigame skips prompt; this fork asks with its own (desktop._host_prompt)")
class MinigamePromptTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        from exp_runtime.desktop import Desktop, MINIGAME_OPTIONS
        self.pg, self.Desktop, self.entries = pygame, Desktop, MINIGAME_OPTIONS
        self.addCleanup(pygame.quit)

    def ui(self, factory=word_resources, *, enabled=True):
        ui = self.Desktop(Session(factory()), audio=False, minigame_skips=enabled)
        ui.viewport = self.pg.Rect(80, 0, 480, 720)
        ui.buttons = [(self.pg.Rect(15, 230 + i * 66, 450, 66), command)
                      for i, (_, command) in enumerate(self.entries)]
        return ui

    def pointer(self, ui, phase, point):
        pg = self.pg
        ui.handle_event(pg.event.Event({'down': pg.MOUSEBUTTONDOWN, 'move': pg.MOUSEMOTION,
                                       'up': pg.MOUSEBUTTONUP}[phase], button=1, pos=point))

    def test_prompt_blocks_game_controls_and_timers_then_plays_with_entry_gate(self):
        for factory in FACTORIES:
            ui = self.ui(factory)
            before = ui.session.snapshot()
            ui.tick(60000)
            ui.command(('choose', 0)); ui.command(('continue',))
            self.pointer(ui, 'down', (300, 100)); self.pointer(ui, 'up', (300, 100))
            self.assertTrue(ui.minigame_prompt)
            self.assertEqual(ui.session.snapshot(), before)
            token, press = ui._screen_token(), ui._press_token()
            ui.handle_event(self.pg.event.Event(self.pg.KEYDOWN, key=self.pg.K_RETURN))
            self.assertFalse(ui.minigame_prompt)
            self.assertNotEqual(ui._screen_token(), token)
            self.assertNotEqual(ui._press_token(), press)
            ui.session = Session.from_snapshot(ui.session.resources, ui.session.snapshot())
            self.assertFalse(ui.minigame_prompt)
            before = ui.session.snapshot()
            ui.tick(1)
            self.assertNotEqual(ui.session.snapshot(), before)

    def test_native_rows_select_on_release_and_dragging_off_cancels(self):
        for factory in FACTORIES:
            for success, y in ((True, 260), (False, 326)):
                ui = self.ui(factory)
                frozen = ui.session.snapshot()
                self.pointer(ui, 'down', (300, y))
                self.assertEqual(ui.press.pressed, ('minigame_skip', success))
                ui.tick(2000)
                self.assertEqual(ui.session.snapshot(), frozen)
                self.pointer(ui, 'move', (300, 100))
                self.assertIsNone(ui.press.pressed)
                self.pointer(ui, 'up', (300, 100))
                self.assertEqual(ui.session.snapshot(), frozen)
                ui._menu_sound = Mock()
                self.pointer(ui, 'down', (300, y)); self.pointer(ui, 'up', (300, y))
                ui._menu_sound.assert_called_once_with()
                self.assertFalse(ui.minigame_prompt)
                self.assertEqual(ui.session.pending.name, 'unhandled_yield')
                self.assertEqual(ui.session.pending.request.args[0] > 0, success)

    def test_focus_loss_cancels_held_skip_and_pause_freezes_prompt(self):
        ui = self.ui()
        before = ui.session.snapshot()
        self.pointer(ui, 'down', (300, 260))
        ui.handle_event(self.pg.event.Event(self.pg.WINDOWFOCUSLOST))
        self.pointer(ui, 'up', (300, 260))
        ui.command(('minigame_skip', True))
        ui.tick(10000)
        self.assertEqual(ui.session.snapshot(), before)
        ui.handle_event(self.pg.event.Event(self.pg.WINDOWFOCUSGAINED))
        ui.command(('menu',)); ui.tick(400)
        self.assertEqual(ui.session.snapshot(), before)
        ui.command(('resume',))
        self.assertTrue(ui.minigame_prompt)

    def test_pause_allows_a_later_skip_after_choosing_play(self):
        for factory in FACTORIES:
            ui = self.ui(factory)
            ui.command(('minigame_play',)); ui.tick(100)
            self.assertFalse(ui.minigame_prompt)
            ui.command(('menu',)); ui.tick(400)
            ui.command(('minigame_skip', False))
            self.assertFalse(ui.menu_open)
            self.assertEqual(ui.session.pending.name, 'unhandled_yield')
            self.assertLessEqual(ui.session.pending.request.args[0], 0)

    def test_disabled_cheat_and_timed_choices_run_normally(self):
        ui = self.ui(enabled=False)
        self.assertFalse(ui.minigame_prompt)
        ui.tick(20001)
        self.assertEqual(ui.session.pending.request.args, (0,))
        for enabled in (False, True):
            ui = self.ui(lambda: Resources(branching_program(1000)), enabled=enabled)
            self.assertFalse(ui.minigame_prompt)
            ui.tick(1001)
            self.assertEqual(ui.session.pending.details['raw_text'], 'Went right.')

    def test_play_applies_only_to_one_minigame(self):
        words, refs = text_words('Title', 'Pick', 'yes|right', 'no|wrong|bad')
        script = program(*(host_call(71, *refs, 1000, -1, 1, 3000) * 2), 0x33, words=words)
        ui = self.ui(lambda: Resources(script))
        ui.command(('minigame_play',))
        ui.tick(1001)
        self.assertTrue(ui.minigame_prompt)
        before = ui.session.snapshot()
        ui.tick(60000)
        self.assertEqual(ui.session.snapshot(), before)
