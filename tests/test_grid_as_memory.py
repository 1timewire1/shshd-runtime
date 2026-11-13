"""The "Use '11's Memory for Word Grid" switch: a letter grid plays as SHS '11's Memory, and its story gets a grid's result."""
import importlib.util
import os
from types import SimpleNamespace
import unittest

from exp_runtime.randomness import NativeRandom
from exp_runtime.runtime import Session
from exp_runtime.shs.word_grid import GridProblem
from exp_runtime.shs11_games import (BAD_BOX, BLANK, GRID_LEAST_SECONDS, MemoryGame, PLAY, WIN_PERCENT, grid_memory, grid_target)
from test_runtime import Resources, host_call, text_words
from test_vm import program


def problem(heading='Sneak and\nsteal.', words=('sneak', 'steal')):
    return GridProblem(3, 2, heading, 'Sneak\nSteal...', list(words), 'abc', True, False, 1, 1001)


def grid(*problems, seconds=45, target=1600, symbols=None, shuffle=False):
    return SimpleNamespace(problems=list(problems) or [problem()], symbols=symbols or {}, target=target, duration_ms=seconds * 1000,
                           shuffle=shuffle)


def round_of(word):
    return ['cue', word, 20, 10, 570, 4250]


class TargetTests(unittest.TestCase):
    def test_it_comes_to_what_elevens_own_stories_ask(self):
        # Best Party Ever's 60 s of five-letter words asks 350; The New Girl, 300.
        self.assertTrue(300 <= grid_target([round_of('HELLO')] * 10, 60) <= 400)

    def test_a_usual_grid_gets_through_its_words_about_once(self):
        rounds = [round_of(word) for word in ('SNEAK', 'STEAL', 'FIND', 'WAY', 'SING')]
        target = grid_target(rounds, 45)
        self.assertLess(target, sum(len(r[1]) * 10 + 20 for r in rounds))
        self.assertGreater(target, 150)

    def test_it_is_a_score_the_game_can_show_and_never_nothing(self):
        for seconds in (30, 45, 50, 60):
            for rounds in ([round_of('A')], [round_of('ABCDEFGHI')], [round_of('CAT'), round_of('DOG')]):
                target = grid_target(rounds, seconds)
                self.assertGreater(target, 0)
                self.assertEqual(target % 10, 0)


class OpeningTests(unittest.TestCase):
    def test_each_word_is_a_round_under_its_cue_in_capitals(self):
        game = grid_memory(grid(), NativeRandom(1))
        self.assertEqual([r[:2] for r in game.rounds], [['Sneak and steal.', 'SNEAK'], ['Sneak and steal.', 'STEAL']])
        self.assertTrue(game.grid)
        self.assertEqual(game.total_ms, 45000)
        self.assertEqual(game.target, grid_target(game.rounds, 45))

    def test_a_long_word_gets_time_for_its_letters(self):
        game = grid_memory(grid(problem(words=['cat', 'clockwork'])), NativeRandom(1))
        self.assertEqual(game.rounds[0][5], 4250)
        self.assertEqual(game.rounds[1][5], 6300)

    def test_what_stays_a_grid(self):
        for stays in (grid(problem(words=['handspring'])),          # ten letters: nine cells
                      grid(problem(words=['457123'])),              # a picture grid's numbers
                      grid(problem(words=[])),                      # no word
                      grid(symbols={1: 2}),                         # pictures
                      grid(target=0),                               # no score to reach
                      grid(seconds=GRID_LEAST_SECONDS - 1)):        # a scene of its own
            self.assertIsNone(grid_memory(stays, NativeRandom(1)))

    def test_one_word_that_does_not_fit_keeps_the_whole_grid(self):
        self.assertIsNone(grid_memory(grid(problem(), problem(words=['handspring'])), NativeRandom(1)))

    def test_a_shuffled_grid_shuffles_its_problems_not_its_pairs(self):
        problems = [problem(f'Cue {k}', [f'w{"abcdefgh"[k]}', f'x{"abcdefgh"[k]}']) for k in range(6)]
        game = grid_memory(grid(*problems, shuffle=True), NativeRandom(3))
        self.assertEqual(len(game.rounds), 12)
        for k in range(0, 12, 2):
            self.assertEqual(game.rounds[k][0], game.rounds[k + 1][0])
        self.assertNotEqual([r[0] for r in game.rounds[::2]], [f'Cue {k}' for k in range(6)])

    def test_its_result_is_a_grids(self):
        game = grid_memory(grid(), NativeRandom(1))
        self.assertEqual(game.best_result, 1)
        game.score = game.win_score
        self.assertEqual(game.result, 1)
        game.score = game.target * (WIN_PERCENT - 10) // 100
        self.assertEqual(game.result, 0)

    def test_elevens_own_games_keep_their_three_results(self):
        game = MemoryGame.opened([round_of('CAT')], 60, 300)
        self.assertFalse(game.grid)
        self.assertEqual(game.best_result, 2)
        game.score = 300
        self.assertEqual(game.result, 2)
        game.score = 240
        self.assertEqual(game.result, 1)


def episode(*, word='cat', target=200):
    """Service 96 with this word, then its result kept where the test can read it."""
    words, refs = text_words('Find a word', 'CAT', word, 'catx', 'Correct', 'Try again')
    table = len(words)
    words += [3, 2, *refs[:4], 1, 0, 1, -1]
    args = [45, target, 1000, 500, 0, -1, 5, 2, 7, 3, 0, 1, table, 1, refs[4], refs[5], 0, 0, 0, 0]
    return Resources(program(*host_call(96, *args), 0x21, (0x1f, 0xfe01), words=[w & 0xffff for w in words]))


class SessionTests(unittest.TestCase):
    def opened(self, on=True, **kwargs):
        session = Session(episode(**kwargs))
        session.engine.random = NativeRandom(1)
        session.grids_as_memory = on
        session.advance()
        return session

    def test_off_a_grid_stays_a_grid(self):
        session = self.opened(on=False)
        self.assertEqual(session.pending.name, 'word_grid')
        self.assertIsNone(session.engine.shs11_memory)

    def test_on_it_opens_memory_with_the_grids_scene(self):
        session = self.opened()
        self.assertEqual(session.pending.name, 'shs11_memory')
        self.assertIsNone(session.engine.word_grid)
        self.assertEqual(session.pending.details,
                         dict(background_id=-1, left_character=5, left_expression=2, right_character=7, right_expression=3))
        self.assertEqual(session.engine.shs11_memory.rounds[0][1], 'CAT')

    def test_a_word_that_will_not_fit_stays_a_grid(self):
        session = self.opened(word='ca7')          # (fits the grid's board, not Memory's letter font)
        self.assertEqual(session.pending.name, 'word_grid')

    def test_its_tutorial_shows_once_and_a_real_grids_is_kept_for_a_real_grid(self):
        session = self.opened()
        self.assertTrue(session.engine.shs11_memory.tutorial)
        self.assertTrue(session.engine.shs11_tutorial_seen)
        self.assertFalse(session.engine.grid_tutorials_seen)

    def play_to_the_end(self, session, score):
        game = session.engine.shs11_memory
        session.start_minigame()
        game.tutorial, game.phase, game.phase_ms = False, PLAY, 0
        game.running = True
        game.score = score
        game.clock_ms = 1
        for _ in range(100):
            if session.pending.name != 'shs11_memory':
                break
            session.tick(100)
        return session.pending

    def test_the_story_gets_one_or_nothing_as_a_grid_gives(self):
        for score, expected in ((1000, 1), (0, 0)):
            session = self.opened()
            self.assertEqual(self.play_to_the_end(session, score).request.args, (expected,))

    def test_a_skip_finishes_it_with_a_grids_result(self):
        session = self.opened()
        self.assertEqual(session.skip_shs11(1).request.args, (1,))
        session = self.opened()
        self.assertEqual(session.skip_shs11(0).request.args, (0,))

    def heard(self, session):
        return [*session.engine.sound_ids] if session.engine.sound_ids else [session.engine.sound_id]

    def in_play(self):
        session = self.opened()
        session.start_minigame()
        game = session.engine.shs11_memory
        game.tutorial, game.phase, game.running, game.word, game.next_letter = False, PLAY, True, 'CAT', 0
        game.cells = ['C', 'A', 'T', *[BAD_BOX] * 6]
        game.shows = [1] * 9
        return session, game

    def test_a_wrong_pick_has_the_grids_wrong_trace(self):
        session, game = self.in_play()
        session.answer(5)
        self.assertEqual(self.heard(session), [8109])

    def test_a_word_with_its_bonus_has_the_grids_found_word(self):
        session, game = self.in_play()
        session.answer(0)
        session.answer(1)
        session.answer(2)
        self.assertEqual(self.heard(session), [8110, 8111])

    def test_a_word_without_its_bonus_has_the_quizs_right_answer(self):
        session, game = self.in_play()
        session.answer(1)                           # out of order: the bonus is gone
        session.answer(0)
        session.answer(2)
        self.assertEqual(self.heard(session), [8001, 8111])

    def test_time_up_has_the_grids(self):
        session, game = self.in_play()
        game.clock_ms = 1
        session.tick(50)
        self.assertEqual(self.heard(session), [8113])

    def sounds_of(self, game, sound, *, skin):
        played = []
        game.sounds.append(sound)
        Session._shs11_sounds(SimpleNamespace(shs11_hd_sounds=skin, shs11_seen_this_run=None, engine=SimpleNamespace(
            request_sound=lambda *assets: played.extend(assets))), game)
        self.assertEqual(game.sounds, [])
        return played

    def test_elevens_own_game_keeps_elevens_sounds_in_its_own_look(self):
        from exp_runtime.shs11_games import ReflexGame, SOUND_DONE, SOUND_WRONG
        memory = MemoryGame.opened([round_of('CAT')], 60, 300)
        self.assertEqual(self.sounds_of(memory, SOUND_WRONG, skin=False), [SOUND_WRONG])
        reflex = ReflexGame.opened([[5, 10, 20, 5, 13, 3, 8, 25, 40, 20, 15, 300, 2100]], 60, 300)
        self.assertEqual(self.sounds_of(reflex, SOUND_DONE, skin=False), [SOUND_DONE])

    def test_elevens_own_memory_in_the_skin_has_the_swapped_sounds(self):
        from exp_runtime.shs11_games import SOUND_DONE, SOUND_MISSED_BONUS, SOUND_TIME_UP, SOUND_WRONG
        memory = MemoryGame.opened([round_of('CAT')], 60, 300)
        for sound, heard in ((SOUND_WRONG, [8109]), (SOUND_MISSED_BONUS, [8001, 8111]), (SOUND_DONE, [8110, 8111]), (SOUND_TIME_UP, [8113])):
            self.assertEqual(self.sounds_of(memory, sound, skin=True), heard)

    def test_elevens_reflex_in_the_skin_has_them_too(self):
        from exp_runtime.shs11_games import ReflexGame, SOUND_DONE, SOUND_TIME_UP, SOUND_WRONG
        reflex = ReflexGame.opened([[5, 10, 20, 5, 13, 3, 8, 25, 40, 20, 15, 300, 2100]], 60, 300)
        for sound, heard in ((SOUND_WRONG, [8109]), (SOUND_DONE, [8110, 8111]), (SOUND_TIME_UP, [8113])):
            self.assertEqual(self.sounds_of(reflex, sound, skin=True), heard)

    def reflex_with_a_right_icon(self):
        from exp_runtime.shs11_games import GUARD_MS, RIGHT_ICON, ReflexGame
        game = ReflexGame.opened([[5, 100, 20, 5, 13, 3, 8, 25, 40, 20, 15, 300, 2100]], 60, 300)
        game.tutorial, game.phase, game.guard_ms = False, PLAY, GUARD_MS
        game.row = game.rounds[0]
        game.cells = [[RIGHT_ICON, 13, 2, 0, 10000, -1], *[None] * 8]
        game.shows = [BLANK] * 9
        return game

    def picks_right(self, *, skin):
        game = self.reflex_with_a_right_icon()
        self.assertTrue(game.press(0))
        played = []
        Session._shs11_sounds(SimpleNamespace(shs11_hd_sounds=skin, shs11_seen_this_run=None, engine=SimpleNamespace(
            request_sound=lambda *assets: played.extend(assets))), game)
        self.assertEqual(game.sounds, [])
        return played

    def test_a_right_pick_in_reflex_has_the_quizs_right_answer_in_the_skin(self):
        self.assertEqual(self.picks_right(skin=True), [8001])

    def test_a_right_pick_in_reflex_stays_silent_in_elevens_look(self):
        self.assertEqual(self.picks_right(skin=False), [])

    def test_a_sound_outside_the_swaps_is_left_alone(self):
        memory = MemoryGame.opened([round_of('CAT')], 60, 300)
        self.assertEqual(self.sounds_of(memory, 12345, skin=True), [12345])

    def test_with_a_runs_set_a_second_story_skips_it_but_a_skipped_game_does_not_count(self):
        seen = set()
        skipped = Session(episode())
        skipped.grids_as_memory, skipped.shs11_seen_this_run = True, seen
        skipped.advance()
        self.assertTrue(skipped.engine.shs11_memory.tutorial)
        skipped.skip_shs11(1)
        self.assertEqual(seen, set())               # never shown: the next one still has it
        played = Session(episode())
        played.grids_as_memory, played.shs11_seen_this_run = True, seen
        played.advance()
        game = played.engine.shs11_memory
        self.assertTrue(game.tutorial)
        game.tutorial = False
        played._shs11_sounds(game)
        self.assertEqual(seen, {'memory'})
        last = Session(episode())
        last.grids_as_memory, last.shs11_seen_this_run = True, seen
        last.advance()
        self.assertFalse(last.engine.shs11_memory.tutorial)
        self.assertTrue(last.engine.shs11_memory.grid)

    def test_a_new_run_shows_it_again(self):
        again = Session(episode())
        again.grids_as_memory, again.shs11_seen_this_run = True, set()
        again.advance()
        self.assertTrue(again.engine.shs11_memory.tutorial)

    def test_a_save_comes_back_as_the_same_game(self):
        session = self.opened()
        state = session.snapshot()
        self.assertEqual(state['version'], 39)
        restored = Session.from_snapshot(episode(), state)
        self.assertEqual(restored.pending.name, 'shs11_memory')
        self.assertTrue(restored.engine.shs11_memory.grid)
        self.assertEqual(restored.engine.shs11_memory.best_result, 1)

    def test_a_save_from_before_has_elevens_own_game(self):
        session = self.opened()
        state = session.snapshot()
        state['version'] = 36
        del state['engine']['shs11_memory']['grid']
        restored = Session.from_snapshot(episode(), state)
        self.assertFalse(restored.engine.shs11_memory.grid)


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class SwitchTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        pygame.init()
        pygame.display.set_mode((16, 16))
        self.addCleanup(pygame.quit)

    def test_extras_lists_it_only_where_its_offered(self):
        from exp_runtime.desktop_pause_hd import EXTRAS_KEYS, SWITCH_BADGES
        self.assertIn('grids_as_memory', EXTRAS_KEYS)
        self.assertNotIn('grids_as_memory', SWITCH_BADGES)                  # the name says whose it is

    def renderer_for(self, *, grid, skin, available=True):
        from exp_runtime.desktop import Desktop
        ui = SimpleNamespace(word_grid_skin=skin, shs11_hd=SimpleNamespace(available=lambda: available, art_available=lambda: available),
                             shs11_memory_renderer='own memory',
                             shs11_reflex_renderer='own reflex',
                             session=SimpleNamespace(engine=SimpleNamespace(shs11_memory=SimpleNamespace(grid=grid))))
        return ui, Desktop.shs11_renderer(ui, SimpleNamespace(name='shs11_memory'))

    def test_memory_in_a_grids_place_has_the_skin_whatever_the_switch_says(self):
        ui, found = self.renderer_for(grid=True, skin=False)
        self.assertIs(found, ui.shs11_hd)

    def test_without_the_hd_art_it_falls_back_to_elevens_look(self):
        _, found = self.renderer_for(grid=True, skin=False, available=False)
        self.assertEqual(found, 'own memory')

    def test_elevens_own_memory_still_follows_the_switch(self):
        _, found = self.renderer_for(grid=False, skin=False)
        self.assertEqual(found, 'own memory')
        ui, found = self.renderer_for(grid=False, skin=True)
        self.assertIs(found, ui.shs11_hd)

    def test_the_skin_switch_stays_out_of_a_smartphone_episodes_add_ons(self):
        from exp_runtime.desktop import Desktop
        import inspect
        source = inspect.getsource(Desktop._pause_settings)
        self.assertIn("{'word_grid_skin': self.word_grid_skin} if self.smartphone_switch() and self.word_grid_switch()", source)

    def test_without_the_addon_memory_in_a_grids_place_still_has_the_skin(self):
        from exp_runtime.desktop import Desktop
        hd = SimpleNamespace(available=lambda: False, art_available=lambda: True)
        ui = SimpleNamespace(word_grid_skin=False, shs11_hd=hd, session=SimpleNamespace(engine=SimpleNamespace(
            shs11_memory=SimpleNamespace(grid=True))))
        self.assertIs(Desktop.shs11_renderer(ui, SimpleNamespace(name='shs11_memory')), hd)

    def test_it_is_offered_with_the_hd_art_or_the_addon_and_only_in_shs(self):
        from exp_runtime import desktop as module
        from unittest.mock import patch
        def offered(art, spec, game='shs'):
            ui = SimpleNamespace(shs11_hd=SimpleNamespace(art_available=lambda: art),
                                 session=SimpleNamespace(resources=SimpleNamespace(library=SimpleNamespace(game_id=game))))
            with patch.object(module, 'memory_spec', lambda _: spec):
                return module.Desktop.memory_grid_switch(ui)
        self.assertTrue(offered(True, None))
        self.assertTrue(offered(False, ({}, None)))
        self.assertFalse(offered(False, None))
        self.assertFalse(offered(True, ({}, None), game='cod'))

    def test_its_words_need_no_addon_and_say_nothing_of_keys(self):
        from exp_runtime.shs11_games import GRID_TEXT
        self.assertEqual(set(GRID_TEXT), {'spelling', 'goal', 'look', 'select', 'careful', 'ready', 'time_up'})
        self.assertNotIn('key', ' '.join(GRID_TEXT.values()).lower())

    def test_a_hidden_cell_shows_the_hd_question_mark_only_in_a_grids_place(self):
        from exp_runtime.desktop_shs11_hd import GRID_QUESTION, Shs11HdRenderer
        from exp_runtime.shs11_games import HIDDEN
        game = SimpleNamespace(shows=[HIDDEN], grid=True)
        self.assertEqual(Shs11HdRenderer.memory_cell(game, 0)[0], GRID_QUESTION)
        game.grid = False
        self.assertEqual(Shs11HdRenderer.memory_cell(game, 0)[0], '?')

    def test_the_hd_question_mark_is_its_fill_without_its_stroke_in_the_letters_blue(self):
        import pygame
        from exp_runtime.desktop_shs11_hd import ICON_TINT, Shs11HdRenderer
        sheet = pygame.Surface((10, 10), pygame.SRCALPHA).convert_alpha()
        sheet.fill((214, 149, 77, 255), (0, 0, 10, 10))     # the stroke
        sheet.fill((255, 255, 255, 255), (3, 3, 4, 4))      # the fill
        renderer = Shs11HdRenderer.__new__(Shs11HdRenderer)
        renderer._pictures = {}
        renderer._spec = lambda: None
        renderer.font = lambda name: SimpleNamespace(height=10, sheet=sheet, font=SimpleNamespace(glyph=lambda char: (0, 0, 10)))
        image = renderer.grid_question_mark()
        self.assertEqual(image.size, (4, 4))
        self.assertEqual(image.getpixel((1, 1))[:3], ICON_TINT[:3])
        self.assertEqual(image.getpixel((1, 1))[3], 255)

    def test_with_the_addon_the_question_mark_is_elevens(self):
        from exp_runtime.desktop_shs11_hd import Shs11HdRenderer
        renderer = Shs11HdRenderer.__new__(Shs11HdRenderer)
        renderer._pictures = {}
        renderer._spec = lambda: ({}, None)
        renderer.question_mark = lambda: "'11's"
        self.assertEqual(renderer.grid_question_mark(), "'11's")

    def test_a_damaged_addon_falls_back_to_the_hd_question_mark(self):
        import pygame
        from exp_runtime.desktop_shs11_hd import Shs11HdRenderer
        sheet = pygame.Surface((4, 4), pygame.SRCALPHA).convert_alpha()
        sheet.fill((255, 255, 255, 255))
        renderer = Shs11HdRenderer.__new__(Shs11HdRenderer)
        renderer._pictures = {}

        def damaged():
            raise ValueError('damaged')
        renderer._spec = damaged
        renderer.font = lambda name: SimpleNamespace(height=4, sheet=sheet, font=SimpleNamespace(glyph=lambda char: (0, 0, 4)))
        self.assertEqual(renderer.grid_question_mark().size, (4, 4))

    def test_a_win_reads_the_skip_prompt_with_a_grids_result(self):
        from exp_runtime.desktop import shs11_skip_options
        self.assertEqual(shs11_skip_options(None, 1), (('Win', 'Lose', 'Play'), (1, 0)))
        self.assertEqual(shs11_skip_options([1], 1), (('Skip', 'Play'), (1,)))
        self.assertEqual(shs11_skip_options([1, 2]), (('Win', 'Lose', 'Play'), (2, 0)))

    def test_the_skin_switch_only_brings_its_sounds_where_it_really_draws(self):
        from exp_runtime.desktop import Desktop
        session = SimpleNamespace(shs11_hd_sounds=False)
        ui = Desktop.__new__(Desktop)
        ui._session = session
        ui.shs11_hd = SimpleNamespace(available=lambda: True)
        ui.word_grid_skin = True
        self.assertTrue(session.shs11_hd_sounds)
        ui.word_grid_skin = False
        self.assertFalse(session.shs11_hd_sounds)
        ui.shs11_hd = SimpleNamespace(available=lambda: False)
        ui.word_grid_skin = True
        self.assertFalse(session.shs11_hd_sounds)

    def test_the_preference_is_kept(self):
        from exp_runtime.menu import SHARED_PREFERENCES
        self.assertIs(SHARED_PREFERENCES['grids_as_memory'], bool)




if __name__ == '__main__':
    unittest.main()
