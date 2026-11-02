"""The X360 translations' jewel puzzle: MS4's rules, the session's part, the drawing and all four inputs."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from exp_runtime import x360_games as games
from exp_runtime import x360_puzzle as x
from exp_runtime.randomness import NativeRandom
from exp_runtime.runtime import SaveError, Session
from exp_runtime.x360_puzzle import JewelPuzzle
from test_runtime import host_call
from test_vm import program

CODE = (*host_call(x.X360_PUZZLE), 0x21, 0x33)


def resources():
    from test_desktop import Resources
    return Resources(program(*CODE))


class Rolls:
    """A stand-in for the game's randomness, rolling a fixed kind."""
    def __init__(self, kinds=(0,)):
        self.kinds, self.n = list(kinds), 0

    def below(self, bound):
        self.n += 1
        return self.kinds[(self.n - 1) % len(self.kinds)] % bound


def laid_out(rows):
    """A running game with this board: eight strings of eight digits, 1-5."""
    game = JewelPuzzle(pieces=[[] for _ in range(x.KINDS)], phase=games.RUNNING, started=True)
    game.board = [[x._jewel() for _ in range(x.SIZE)] for _ in range(x.SIZE)]
    for i, row in enumerate(rows, 1):
        for j, kind in enumerate(row, 1):
            game._at(i, j).update(index=int(kind), i=i, j=j)
            game.pieces[int(kind) - 1].append([i, j])
    return game


STRIPES = ['12345123', '23451234', '34512345', '45123451', '51234512', '12345123', '23451234', '34512345']


def kinds(game):
    return [''.join(str(p['index']) for p in row) for row in game.board]


def run(game, ms, random=None, step=10):
    random = random or Rolls()
    for _ in range(ms // step):
        if game.tick(step, random):
            return True
    return False


class DealTests(unittest.TestCase):
    def test_the_deal_never_joins_three(self):
        for seed in range(30):
            random = NativeRandom()
            random.state = seed * 7919 + 1
            game = JewelPuzzle.dealt(random)
            game.validate()
            self.assertEqual(sum(len(kind) for kind in game.pieces), 64)
            for i in range(1, 9):
                for j in range(1, 9):
                    same = [(a, b) for a, b in ((i - 1, j), (i + 1, j), (i, j - 1), (i, j + 1))
                            if 1 <= a <= 8 and 1 <= b <= 8 and game._at(a, b)['index'] == game._at(i, j)['index']]
                    self.assertLess(len(same), 2)
                    if same:
                        a, b = same[0]
                        more = [(c, d) for c, d in ((a - 1, b), (a + 1, b), (a, b - 1), (a, b + 1))
                                if 1 <= c <= 8 and 1 <= d <= 8 and (c, d) != (i, j)
                                and game._at(c, d)['index'] == game._at(i, j)['index']]
                        self.assertEqual(more, [])

    def test_it_starts_with_the_cursor_at_the_bottom_left_and_a_minute_on_the_clock(self):
        game = JewelPuzzle.dealt(Rolls())
        self.assertEqual((game.cursor_i, game.cursor_j, game.total_time, game.score), (8, 1, 60, 0))


class GateTests(unittest.TestCase):
    def test_it_opens_then_waits_for_a_press_however_long_it_takes(self):
        game = JewelPuzzle.dealt(Rolls())
        self.assertFalse(game.press())                          # (one left over from the dialogue can't start it)
        run(game, games.OPENING_MS)
        self.assertEqual(game.phase, games.READY)
        run(game, 60000, step=250)
        self.assertEqual((game.phase, game.total_time), (games.READY, 60))
        self.assertFalse(game.move(x.UP))
        self.assertTrue(game.press())
        self.assertEqual((game.phase, game.button), (games.RUNNING, False))     # the go-ahead doesn't hold the button

    def test_the_skip_prompts_play_is_its_go_ahead(self):
        game = JewelPuzzle.dealt(Rolls())
        self.assertTrue(game.start())
        run(game, games.OPENING_MS)
        self.assertEqual(game.phase, games.RUNNING)


class MoveTests(unittest.TestCase):
    def test_the_cursor_steps_a_cell_with_a_pause_and_stops_at_the_edges(self):
        game = laid_out(STRIPES)
        self.assertFalse(game.move(x.DOWN))                     # already on the bottom row
        self.assertFalse(game.move(x.LEFT))
        self.assertTrue(game.move(x.UP))
        self.assertEqual((game.cursor_i, game.cursor_j), (7, 1))
        self.assertFalse(game.move(x.UP))                       # the step's 0.07 s
        run(game, x.MOVE_MS)
        self.assertTrue(game.move(x.UP))
        self.assertEqual(kinds(game), STRIPES)                  # no button: nothing else moves
        self.assertEqual(game.sounds, [])                       # and the cursor's silent

    def test_with_the_button_held_the_row_comes_along_wrapping_round(self):
        game = laid_out(STRIPES)
        game.press()
        game.move(x.RIGHT)
        self.assertEqual(kinds(game)[7], STRIPES[7][-1] + STRIPES[7][:-1])
        self.assertEqual(kinds(game)[:7], STRIPES[:7])
        self.assertEqual(game.sounds, [x.SOUND_DRAG])
        run(game, x.MOVE_MS)
        game.move(x.LEFT)
        self.assertEqual(kinds(game), STRIPES)                  # and back

    def test_with_the_button_held_the_column_comes_along_wrapping_round(self):
        game = laid_out(STRIPES)
        game.press()
        game.move(x.UP)
        column = [row[0] for row in STRIPES]
        self.assertEqual([row[0] for row in kinds(game)], column[1:] + column[:1])
        self.assertEqual([row[1:] for row in kinds(game)], [row[1:] for row in STRIPES])
        run(game, x.MOVE_MS)
        game.release()
        game.move(x.UP)
        self.assertEqual([row[0] for row in kinds(game)], column[1:] + column[:1])   # let go: only the cursor moves

    def test_the_record_of_each_kind_follows_the_jewels(self):
        game = laid_out(STRIPES)
        game.press()
        for direction in (x.RIGHT, x.UP, x.LEFT, x.RIGHT, x.UP):
            game.move(direction)
            run(game, x.MOVE_MS)
        for kind, cells in enumerate(game.pieces, 1):
            self.assertEqual(sorted(map(tuple, cells)),
                             sorted((i, j) for i in range(1, 9) for j in range(1, 9) if game._at(i, j)['index'] == kind))
        for i in range(1, 9):
            for j in range(1, 9):
                self.assertEqual((game._at(i, j)['i'], game._at(i, j)['j']), (i, j))

    def test_a_dragged_jewel_slides_but_the_one_that_wraps_jumps(self):
        game = laid_out(STRIPES)
        game.press()
        game.move(x.RIGHT)
        moved, wrapped = game._at(8, 2), game._at(8, 1)
        self.assertEqual((moved['anim'], moved['off_j']), (x.MOVE_MS, -1))
        self.assertEqual(wrapped['anim'], 0)
        run(game, x.MOVE_MS)
        self.assertEqual(moved['anim'], 0)


GROUP = ['11115123', '23451234', '34512345', '45123451', '51234512', '12345123', '23451234', '34512345']


class ClearTests(unittest.TestCase):
    def test_three_joined_isnt_enough_but_four_are_selected(self):
        game = laid_out(['11145123'] + STRIPES[1:])
        game.check_pieces()
        self.assertEqual([p['state'] for p in game.board[0][:3]], [x.NORMAL] * 3)
        game = laid_out(GROUP)
        game.check_pieces()
        self.assertEqual([p['state'] for p in game.board[0][:4]], [x.SELECTED] * 4)
        self.assertEqual(game.board[0][4]['state'], x.NORMAL)

    def test_an_l_shape_counts(self):
        game = laid_out(['11145123', '13451234'] + STRIPES[2:])
        game.check_pieces()
        self.assertEqual([game._at(*c)['state'] for c in ((1, 1), (1, 2), (1, 3), (2, 1))], [x.SELECTED] * 4)

    def test_jewels_joined_are_one_group_whatever_order_the_record_holds_them_in(self):
        # MS4's scan looks like it could split them, but the first of a group it meets reaches all the rest.
        for order in ([[1, 1], [1, 2], [1, 4], [1, 5], [1, 3]], [[1, 3], [1, 5], [1, 1], [1, 4], [1, 2]],
                      [[1, 5], [1, 4], [1, 3], [1, 2], [1, 1]]):
            game = laid_out(['11211234'] + STRIPES[1:])
            game._at(1, 3)['index'] = 1
            game.pieces[1].remove([1, 3])
            game.pieces[0] = [list(c) for c in order] + [c for c in game.pieces[0] if c[0] != 1 or c[1] > 5]
            game.check_pieces()
            self.assertEqual([p['state'] for p in game.board[0][:5]], [x.SELECTED] * 5)

    def test_they_go_after_three_seconds_score_and_fall(self):
        game = laid_out(GROUP)
        game.check_pieces()
        self.assertFalse(run(game, 2900))
        self.assertEqual(game.score, 0)
        run(game, 200)
        self.assertEqual(game.score, 4)
        self.assertEqual(game.bars[0], 4)
        self.assertEqual(game.sounds, [x.SOUND_CLEAR])          # once for the group
        self.assertTrue(game.in_chain)
        self.assertTrue(game.check_falling)
        self.assertFalse(game.move(x.UP))                       # no moves while they fall
        run(game, x.FALL_WAIT_MS + 20)
        self.assertFalse(game.check_falling)
        self.assertTrue(all(p['index'] != -1 for row in game.board for p in row))
        self.assertEqual(sum(len(kind) for kind in game.pieces), 64)

    def test_moving_one_out_cancels_the_group_and_its_time(self):
        game = laid_out(GROUP)
        game.check_pieces()
        run(game, 2000)
        self.assertEqual(game.board[0][0]['own'], 2)
        game.cursor_i, game.cursor_j = 2, 1
        game.press()
        game.move(x.DOWN)                                       # the first column down: (1,1) leaves the row
        self.assertEqual(sum(p['state'] == x.SELECTED for p in game.board[0]), 0)
        self.assertEqual(game.board[0][1]['own'], 0)
        run(game, 4000)
        self.assertEqual(game.score, 0)

    def test_during_a_chain_they_go_in_a_second_for_three_each(self):
        game = laid_out(GROUP)
        game.in_chain, game.prev_chain_ms = True, 0
        game.check_pieces()
        run(game, 950)
        self.assertEqual(game.score, 0)
        run(game, 100)
        self.assertEqual(game.score, 12)

    def test_a_chain_lasts_two_seconds_after_the_fall(self):
        game = laid_out(GROUP)
        game.check_pieces()
        run(game, 3000 + x.FALL_WAIT_MS + 50)
        self.assertTrue(game.in_chain)
        run(game, 1700)
        self.assertTrue(game.in_chain)
        run(game, 300)
        self.assertFalse(game.in_chain)

    def test_jewels_above_fall_and_new_ones_fill_the_top(self):
        game = laid_out(['12345123', '21451234', '31512345', '41123451', '51234512', '12345123', '23451234', '34512345'])
        above = game._at(1, 2)['index']
        for i in (2, 3, 4, 5):
            game._at(i, 2)['index'] = 1
        game.pieces = [[] for _ in range(x.KINDS)]
        for i in range(1, 9):
            for j in range(1, 9):
                game.pieces[game._at(i, j)['index'] - 1].append([i, j])
        game._at(1, 2)['index'] = 3
        game.pieces[1].remove([1, 2]) if [1, 2] in game.pieces[1] else None
        game.pieces[0] = [c for c in game.pieces[0] if c != [1, 2]]
        game.pieces[2].append([1, 2])
        game.check_pieces()
        run(game, 3100 + x.FALL_WAIT_MS, Rolls((3,)))
        self.assertEqual(game._at(5, 2)['index'], 3)             # the one above came down four rows...
        self.assertNotEqual(game._at(5, 2)['anim_total'], 0)
        self.assertEqual(sum(len(kind) for kind in game.pieces), 64)
        for kind, cells in enumerate(game.pieces, 1):            # ...and the record keeps up
            for i, j in cells:
                self.assertEqual(game._at(i, j)['index'], kind)
        self.assertEqual(above, 2)


class EndTests(unittest.TestCase):
    def test_a_minute_later_its_times_up_then_the_score_until_a_press(self):
        game = laid_out(STRIPES)
        game.button = True
        run(game, 59900, step=100)
        self.assertEqual(game.phase, games.RUNNING)
        run(game, 200, step=100)
        self.assertEqual((game.phase, game.total_time, game.button), (games.TIME_UP, 0, False))
        self.assertFalse(game.move(x.UP))
        self.assertFalse(game.press())
        run(game, x.TIME_UP_MS)
        self.assertEqual(game.phase, x.SHOWING_SCORE)
        self.assertFalse(run(game, 30000, step=250))             # it waits
        self.assertTrue(game.press())
        self.assertFalse(game.tick(100, Rolls()))
        self.assertTrue(run(game, x.CLOSING_MS))


    def test_after_the_clock_everything_selected_clears_and_whatever_that_sets_off_before_the_score(self):
        game = laid_out(GROUP)
        game.total_time = 1
        run(game, 900, step=100)
        self.assertEqual(game.phase, games.RUNNING)
        game.check_pieces()                                      # selected with 0.1 s on the clock
        run(game, 200, step=100)
        self.assertEqual(game.phase, games.TIME_UP)
        self.assertEqual(game._at(1, 1)['state'], x.SELECTED)
        self.assertFalse(game.move(x.UP))                        # no more moves
        run(game, x.TIME_UP_MS, step=100)
        self.assertEqual((game.phase, game.score), (games.TIME_UP, 0))      # still going: three seconds to clear
        run(game, 400, step=100)
        self.assertEqual(game.score, 4)
        self.assertEqual(game.total_time, 0)                     # and the clock doesn't go below
        run(game, 500, step=100)
        self.assertEqual(game.phase, x.SHOWING_SCORE)
        self.assertFalse(game.in_chain)

    def test_a_group_a_fall_makes_after_the_clock_clears_too(self):
        game = laid_out(GROUP)
        game.total_time = 0
        game.phase, game.phase_ms = games.TIME_UP, 100
        game.check_pieces()
        # New jewels are forced to make another group as they land on the top row's neighbours.
        real = game._fall

        def fall(random):
            real(random)
            game.pieces = [[] for _ in range(x.KINDS)]
            for j in range(1, 5):
                game._at(1, j)['index'] = 2
            for i in range(1, 9):
                for j in range(1, 9):
                    game.pieces[game._at(i, j)['index'] - 1].append([i, j])
            game._fall = real
        game._fall = fall
        run(game, 3000 + x.FALL_WAIT_MS + 50, step=50)
        self.assertEqual(game.phase, games.TIME_UP)              # the second group is selected, and it waits for that
        self.assertTrue(any(p['state'] == x.SELECTED for row in game.board for p in row))
        run(game, 1500, step=50)
        self.assertEqual(game.phase, x.SHOWING_SCORE)
        self.assertEqual(game.score, 4 + 15)                     # the second group's five, in a chain: +3 each

    def test_a_settled_board_goes_straight_on_after_times_up(self):
        game = laid_out(STRIPES)
        game.phase, game.phase_ms = games.TIME_UP, x.TIME_UP_MS
        run(game, x.TIME_UP_MS)
        self.assertEqual(game.phase, x.SHOWING_SCORE)


class PointerTests(unittest.TestCase):
    def test_hovering_points_the_cursor_only_with_the_button_up(self):
        game = laid_out(STRIPES)
        game.point(3, 4)
        self.assertEqual((game.cursor_i, game.cursor_j), (3, 4))
        game.point(0, 4)
        self.assertEqual((game.cursor_i, game.cursor_j), (3, 4))
        game.press()
        game.point(5, 5)
        self.assertEqual((game.cursor_i, game.cursor_j), (3, 4))

    def test_a_drag_takes_the_row_along_a_cell_at_a_time_and_locks_to_its_first_direction(self):
        game = laid_out(STRIPES)
        game.grab(3, 2)
        self.assertEqual((game.cursor_i, game.cursor_j, game.button), (3, 2, True))
        game.drag(3, 5)
        game.tick(1, Rolls())
        self.assertEqual((game.cursor_j, game.lock), (3, 'row'))
        run(game, x.MOVE_MS * 2 + 40)
        self.assertEqual(game.cursor_j, 5)
        self.assertEqual(kinds(game)[2], STRIPES[2][-3:] + STRIPES[2][:-3])
        game.drag(6, 5)                                          # the finger strays down: still the row
        run(game, x.MOVE_MS * 2)
        self.assertEqual(game.cursor_i, 3)
        game.let_go()
        self.assertEqual((game.button, game.target, game.lock), (False, None, ''))

    def test_a_drag_down_takes_the_column(self):
        game = laid_out(STRIPES)
        game.grab(2, 3)
        game.drag(4, 3)
        run(game, x.MOVE_MS * 2 + 40)
        self.assertEqual((game.cursor_i, game.lock), (4, 'col'))
        column = [row[2] for row in STRIPES]
        self.assertEqual([row[2] for row in kinds(game)], column[-2:] + column[:-2])

    def test_a_drag_off_the_board_stays_on_it(self):
        game = laid_out(STRIPES)
        game.grab(3, 7)
        game.drag(3, 40)
        self.assertEqual(game.target, [3, 8])


class ServiceTests(unittest.TestCase):
    def play(self):
        session = Session(resources(), ephemeral=True)
        action = session.advance()
        self.assertEqual(action.name, 'x360_puzzle')
        return session

    def test_a_press_is_the_sessions_answer_and_its_sounds_are_the_sessions(self):
        session = self.play()
        session.tick(250)
        session.tick(250)
        self.assertTrue(session.minigame_unstarted)
        session.answer(None)
        game = session.engine.x360_puzzle
        self.assertFalse(session.minigame_unstarted)
        self.assertEqual(game.phase, games.RUNNING)
        session.answer(None)
        self.assertTrue(game.button)
        game.cursor_j = 4
        game.move(x.LEFT)
        before = session.engine.sound_serial
        session.tick(16)
        self.assertEqual((session.engine.sound_serial, session.engine.sound_ids), (before + 1, [x.SOUND_DRAG]))
        with self.assertRaises(ValueError):
            session.answer(3)

    def test_it_ends_and_the_story_goes_on_without_it(self):
        session = self.play()
        game = session.engine.x360_puzzle
        game.start()
        for _ in range(400):
            session.tick(250)
            if game.phase == x.SHOWING_SCORE:
                break
        self.assertEqual(game.phase, x.SHOWING_SCORE)
        session.answer(None)
        session.tick(250)
        session.tick(250)
        self.assertIsNone(session.engine.x360_puzzle)
        self.assertNotEqual(getattr(session.pending, 'name', None), 'x360_puzzle')

    def test_a_game_in_progress_saves_and_comes_back_where_it_was(self):
        session = self.play()
        session.engine.x360_puzzle.start()
        session.tick(250)
        session.tick(250)
        session.answer(None)
        session.engine.x360_puzzle.move(x.UP)
        session.tick(16)
        state = json.loads(json.dumps(session.snapshot()))
        self.assertEqual(state['version'], 34)
        again = Session.from_snapshot(resources(), state)
        self.assertEqual(again.engine.x360_puzzle, session.engine.x360_puzzle)
        self.assertEqual(again.pending.name, 'x360_puzzle')
        again.tick(100)                                          # and it carries on

    def test_a_damaged_save_is_refused(self):
        state = json.loads(json.dumps(self.play().snapshot()))
        state['engine']['x360_puzzle']['cursor_i'] = 40
        with self.assertRaises(SaveError):
            Session.from_snapshot(resources(), state)

    def test_an_older_save_has_none(self):
        state = json.loads(json.dumps(Session(resources(), ephemeral=True).snapshot()))
        state['version'] = 32
        del state['engine']['x360_puzzle']
        self.assertIsNone(Session.from_snapshot(resources(), state).engine.x360_puzzle)

    def test_the_skip_goes_straight_on(self):
        session = self.play()
        session.skip_minigame(False)
        self.assertIsNone(session.engine.x360_puzzle)


class PlayerTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        pygame.init()
        pygame.display.set_mode((64, 64))
        self.pygame = pygame

    def desktop(self, temporary):
        from exp_runtime.desktop import Desktop
        story = resources()
        story.library.directory = Path(temporary)
        session = Session(story, ephemeral=True)
        session.advance()
        ui = Desktop(session, audio=False)
        ui.bg_viewport = self.pygame.Rect(0, 0, 768, 1024)      # (frame units, here)
        for _ in range(3):
            session.tick(250)
        return ui, session.engine.x360_puzzle

    def press_key(self, ui, code, **more):
        ui.handle_event(self.pygame.event.Event(self.pygame.KEYDOWN, key=code, mod=0, unicode='', **more))

    def skin(self):
        import io
        import exp_runtime.desktop_x360_slot as slot
        pygame = self.pygame
        out = {}

        def png(resource, colour=(10, 200, 10, 255), size=(32, 32)):
            surface = pygame.Surface(size, pygame.SRCALPHA)
            surface.fill(colour)
            buffer = io.BytesIO()
            pygame.image.save(surface, buffer, 'x.png')
            out[resource] = buffer.getvalue()
            return resource
        box = [-.5, -.5, .5, .5]
        chars = {str(ord(ch)): [0, 0, 8, 10, 0, 0, 9, 0] for ch in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 !:\'4'}
        digits = dict(atlas=png(1, (220, 30, 20, 255), (100, 128)), score=list(range(6)), time=[6, 7],
                      slots=[[dict(rect=[n * 10, i * 16, 10, 16]) for n in range(10)] for i in range(8)])
        spec = dict(pictures=dict(power_bar=png(2, (90, 90, 90, 255)), power_fill_green=png(3), power_fill_blue=png(4),
                                  power_fill_yellow=png(5)),
                    booth=dict(digits=digits),
                    slot=dict(font=dict(line_height=12, base=10, kerning={}, pages=[png(6, (0, 0, 0, 255))], chars=chars)),
                    puzzle=dict(placed=dict(jewels={str(n): box for n in range(1, 6)}, cursor=[-.6, -.6, .6, .6],
                                            board=[-.1, -.1, 8.1, 8.1]),
                                shine_ms=5000, cursor=png(7, (0, 200, 0, 255)), board=png(8, (43, 43, 0, 255)),
                                board_metal=png(9, (40, 40, 40, 255)), fill_red=png(10), fill_purple=png(11),
                                jewels={str(n): [png(100 + n * 10 + k, (200, n * 20, 100, 255)) for k in range(2)]
                                        for n in range(1, 6)}))
        archive = SimpleNamespace(read=out.__getitem__)
        real = slot.addon_skin
        slot.addon_skin = lambda _: (spec, archive)
        self.addCleanup(setattr, slot, 'addon_skin', real)
        return SimpleNamespace()

    def test_it_draws_every_phase_in_the_whole_frame(self):
        from exp_runtime.desktop_x360_puzzle import CELL, FRAME, GRID_LEFT, GRID_TOP, X360PuzzleRenderer
        renderer = X360PuzzleRenderer(self.skin())
        game = laid_out(STRIPES)
        game.phase, game.phase_ms = games.OPENING, games.OPENING_MS
        session = SimpleNamespace(engine=SimpleNamespace(x360_puzzle=game))
        renderer.draw(session)
        self.assertEqual(renderer.canvas.get_size(), FRAME)
        self.assertAlmostEqual(renderer.alpha(game), 0, delta=.01)
        for phase in (games.READY, games.RUNNING, games.TIME_UP, x.SHOWING_SCORE):
            game.phase, game.phase_ms = phase, 1000
            renderer.draw(session)
            self.assertIsNone(renderer.alpha(game))
        game.phase, game.phase_ms = games.CLOSING, x.CLOSING_MS // 2
        self.assertAlmostEqual(renderer.alpha(game), .5)
        # A jewel lies in its cell, and a sliding one lies part of the way back along its slide.
        game.phase = games.RUNNING
        renderer.draw(session)
        middle = (GRID_LEFT + 2 * CELL + CELL // 2, GRID_TOP + CELL // 2)
        self.assertEqual(renderer.canvas.get_at(middle)[0], 200)
        game._at(1, 3).update(off_i=0, off_j=-4, anim=x.MOVE_MS, anim_total=x.MOVE_MS)
        renderer.draw(session)
        self.assertEqual(renderer.canvas.get_at(middle)[:3], (43, 43, 0))       # four cells off: only the board's left there

    def test_a_selected_jewel_glows_a_chains_board_turns_metal_and_a_clearing_throws_sparks(self):
        from exp_runtime.desktop_x360_puzzle import CELL, GRID_LEFT, GRID_TOP, X360PuzzleRenderer
        renderer = X360PuzzleRenderer(self.skin())
        game = laid_out(GROUP)
        session = SimpleNamespace(engine=SimpleNamespace(x360_puzzle=game))
        renderer.draw(session)
        corner = (GRID_LEFT - 4, GRID_TOP - 4)                   # the board's rim, clear of the jewels
        self.assertEqual(renderer.canvas.get_at(corner)[:3], (43, 43, 0))
        centre = (GRID_LEFT + CELL // 2, GRID_TOP + CELL // 2)
        plain = renderer.canvas.get_at(centre)[:3]
        game.check_pieces()
        renderer.draw(session)
        self.assertGreater(sum(renderer.canvas.get_at(centre)[:3]), sum(plain))
        game.in_chain = True
        game.now_ms = 1200
        renderer.draw(session)
        self.assertNotEqual(renderer.canvas.get_at(corner)[:3], (43, 43, 0))
        game.in_chain = False
        game.board[3][3].update(index=-1, state=x.DESTROYED)
        game.cleared = [[4, 4, 1, game.now_ms - 100]]
        renderer.draw(session)                                   # (and it draws with one gone)

    def test_cells_lie_under_the_pointer(self):
        from exp_runtime.desktop_x360_puzzle import CELL, GRID_LEFT, GRID_TOP, cell_at, on_board
        self.assertEqual(cell_at(GRID_LEFT + 1, GRID_TOP + 1), (1, 1))
        self.assertEqual(cell_at(GRID_LEFT + 8 * CELL - 1, GRID_TOP + 8 * CELL - 1), (8, 8))
        self.assertEqual(cell_at(GRID_LEFT + CELL + 1, GRID_TOP + 3 * CELL + 1), (4, 2))
        self.assertTrue(on_board(GRID_LEFT, GRID_TOP))
        self.assertFalse(on_board(GRID_LEFT - 1, GRID_TOP))
        self.assertFalse(on_board(GRID_LEFT, GRID_TOP + 8 * CELL))

    def test_keys_start_it_hold_it_and_move_the_cursor_with_a_repeat(self):
        import tempfile
        from exp_runtime.gamepad import REPEAT_DELAY_MS, REPEAT_MS
        pygame = self.pygame
        with tempfile.TemporaryDirectory() as temporary:
            ui, game = self.desktop(temporary)
            self.press_key(ui, pygame.K_UP)
            self.assertEqual(game.cursor_i, 8)                  # it hasn't started
            self.press_key(ui, pygame.K_RETURN)
            self.assertEqual((game.phase, game.button), (games.RUNNING, False))
            ui.handle_event(pygame.event.Event(pygame.KEYUP, key=pygame.K_RETURN, mod=0))
            self.press_key(ui, pygame.K_w)
            self.assertEqual(game.cursor_i, 7)
            run(game, x.MOVE_MS)
            ui._puzzle_frame(REPEAT_DELAY_MS - 1)
            self.assertEqual(game.cursor_i, 7)
            ui._puzzle_frame(1)
            self.assertEqual(game.cursor_i, 6)
            run(game, x.MOVE_MS)
            ui._puzzle_frame(REPEAT_MS)
            self.assertEqual(game.cursor_i, 5)
            ui.handle_event(pygame.event.Event(pygame.KEYUP, key=pygame.K_w, mod=0))
            self.assertIsNone(ui.puzzle_key)
            before = kinds(game)
            self.press_key(ui, pygame.K_SPACE)
            self.assertTrue(game.button)
            run(game, x.MOVE_MS)
            self.press_key(ui, pygame.K_RIGHT)
            self.assertNotEqual(kinds(game), before)
            ui.handle_event(pygame.event.Event(pygame.KEYUP, key=pygame.K_SPACE, mod=0))
            self.assertFalse(game.button)

    def test_a_controllers_confirm_holds_until_it_lets_go(self):
        import tempfile
        from exp_runtime import desktop
        from exp_runtime.gamepad import key_event
        pygame = self.pygame
        pads = SimpleNamespace(holding=Mock(return_value=True), sticks={})
        with tempfile.TemporaryDirectory() as temporary:
            ui, game = self.desktop(temporary)
            game.press()
            real = desktop.pygame.gamepads
            desktop.pygame.gamepads = lambda: pads
            self.addCleanup(setattr, desktop.pygame, 'gamepads', real)
            ui.handle_event(key_event(pygame.K_RETURN, 'south'))
            self.assertTrue(game.button)
            ui._puzzle_frame(16)
            self.assertTrue(game.button)
            pads.holding.return_value = False
            ui._puzzle_frame(16)
            self.assertFalse(game.button)
            ui.handle_event(key_event(pygame.K_UP, 'up'))
            self.assertEqual(game.cursor_i, 7)                  # a controller's direction
            self.assertIsNone(ui.puzzle_key)                    # repeats by itself

    def test_a_mouse_hovers_grabs_drags_and_lets_go_and_the_gear_opens_the_menu(self):
        import tempfile
        from exp_runtime.desktop_x360_puzzle import CELL, GRID_LEFT, GRID_TOP
        pygame = self.pygame
        with tempfile.TemporaryDirectory() as temporary:
            ui, game = self.desktop(temporary)

            def at(i, j):
                return (GRID_LEFT + (j - .5) * CELL, GRID_TOP + (i - .5) * CELL)

            def event(kind, pos, **more):
                ui.handle_event(pygame.event.Event(kind, pos=pos, **more))
            event(pygame.MOUSEBUTTONDOWN, at(3, 3), button=1)   # a press anywhere is its go-ahead
            self.assertEqual((game.phase, game.button), (games.RUNNING, False))
            event(pygame.MOUSEBUTTONUP, at(3, 3), button=1)
            event(pygame.MOUSEMOTION, at(5, 6), rel=(0, 0), buttons=(0, 0, 0))
            self.assertEqual((game.cursor_i, game.cursor_j), (5, 6))
            event(pygame.MOUSEBUTTONDOWN, at(2, 2), button=1)
            self.assertEqual((game.cursor_i, game.cursor_j, game.button), (2, 2, True))
            before = kinds(game)
            event(pygame.MOUSEMOTION, at(2, 3), rel=(0, 0), buttons=(1, 0, 0))
            run(game, x.MOVE_MS)
            self.assertEqual(game.cursor_j, 3)
            self.assertEqual(kinds(game)[1], before[1][-1] + before[1][:-1])
            event(pygame.MOUSEBUTTONUP, at(2, 3), button=1)
            self.assertEqual((game.button, game.target), (False, None))
            event(pygame.MOUSEBUTTONDOWN, (40, 980), button=1)
            self.assertTrue(ui.menu_open)
            self.assertFalse(game.button)

    def test_ok_or_a_click_goes_on_past_the_score(self):
        import tempfile
        pygame = self.pygame
        with tempfile.TemporaryDirectory() as temporary:
            ui, game = self.desktop(temporary)
            game.phase = x.SHOWING_SCORE
            self.press_key(ui, pygame.K_RETURN)
            self.assertEqual(game.phase, games.CLOSING)
            game.phase = x.SHOWING_SCORE
            ui.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(380, 300), button=1))
            self.assertEqual(game.phase, games.CLOSING)

    def test_nothing_holds_it_under_the_menu(self):
        import tempfile
        pygame = self.pygame
        with tempfile.TemporaryDirectory() as temporary:
            ui, game = self.desktop(temporary)
            game.press()
            game.grab(3, 3)
            ui.menu_open = True
            ui._puzzle_frame(16)
            self.assertEqual((game.button, game.target), (False, None))
            self.press_key(ui, pygame.K_UP)
            self.assertEqual(game.cursor_i, 3)


if __name__ == '__main__':
    unittest.main()
