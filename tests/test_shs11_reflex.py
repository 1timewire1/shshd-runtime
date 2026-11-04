"""SHS '11's Reflex: its rules (shs11_games.py, N73's `av`, `bl`, `am`), and the story's call."""
import json
from pathlib import Path
import random
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from exp_runtime.shs11_games import (AGE, BARS, DELAY, ENTER, GAUGE, GOAL, GUARD_MS, KIND, MARKER_MS, PAUSE, PENALTY, PLAY, READY, ReflexGame,
                                     RIGHT, RIGHT_ICON, SELECT, SKULL, SKULL_ICON, SOUND_DONE, SOUND_TIME_UP, SOUND_WRONG, TIME_UP, WRONG,
                                     WRONG_ICON, lowest_score)

from test_translate_shs11 import FIRST, HAS_PIL, call, push, setup_script, story_jar

if HAS_PIL:
    import shs11
    import shs11_story
    from exp_runtime.decode.bytecode import decode_program
    from exp_runtime.exp import ExpArchive
    from exp_runtime.runtime import SaveError, Session
    from exp_runtime.shs11_services import SHS11_REFLEX

ROW = [5, 10, 20, 5, 13, 3, 8, 25, 40, 20, 15, 300, 2100]       # as Secret Ingredient's first


class Rng:
    def __init__(self, seed=1):
        self.random = random.Random(seed)

    def below(self, bound):
        return self.random.randrange(bound)


def game(rows=(ROW,), target=350, seconds=60, tutorial=False):
    return ReflexGame.opened(rows, seconds, target, tutorial=tutorial)


def run(found, ms, rng=None, step=10):
    rng = rng or Rng()
    finished = False
    for _ in range(ms // step):
        finished = found.tick(step, rng) or finished
    return finished


def until(found, phase, limit=30000, rng=None):
    rng = rng or Rng()
    for _ in range(limit // 10):
        if found.phase == phase:
            return
        found.tick(10, rng)
    raise AssertionError(f'never reached {phase}: at {found.phase}')


def ready_to_pick(found):
    """On until every icon is in and picks are open."""
    until(found, PLAY)
    while found.guard_ms < GUARD_MS or not all(found.revealed(c) for c in range(9) if found.cells[c]):
        found.tick(10, Rng())


def cell_of(found, kind):
    return next((c for c in range(9) if found.cells[c] and found.cells[c][KIND] == kind), None)


class RoundTests(unittest.TestCase):
    def test_a_deal_fills_every_cell_with_at_least_the_rounds_right_icons(self):
        for seed in range(50):
            found = game()
            found.row = list(ROW)
            found._deal(Rng(seed))
            kinds = [icon[KIND] for icon in found.cells]
            self.assertEqual(len(kinds), 9)
            self.assertGreaterEqual(kinds.count(RIGHT_ICON), ROW[0])

    def test_icons_come_in_after_their_delay_and_its_flash(self):
        found = game()
        until(found, PLAY)
        for icon in found.cells:
            self.assertLess(icon[DELAY], 650)
        self.assertFalse(any(found.revealed(c) for c in range(9)))
        run(found, 650 + 300 + 20)
        self.assertTrue(all(found.revealed(c) for c in range(9)))

    def test_the_clock_starts_with_the_first_deal(self):
        found = game()
        run(found, 200)
        self.assertEqual(found.clock_ms, 60000)
        until(found, PLAY)
        run(found, 100)
        self.assertLess(found.clock_ms, 60000)

    def test_a_right_icon_moves_the_gauge_by_its_bars_and_scores_a_second_later(self):
        found = game()
        ready_to_pick(found)
        cell = cell_of(found, RIGHT_ICON)
        bars = found.cells[cell][2]
        self.assertTrue(found.press(cell))
        self.assertEqual(found.gauge, bars)
        self.assertEqual(found.shows[cell], RIGHT)
        self.assertEqual(found.phase, PAUSE)
        run(found, 1020)
        self.assertEqual(found.score, 5 * bars)

    def test_a_wrong_icon_moves_it_back_and_never_past_empty(self):
        rows = [[0, 10, 20, 5, 13, 3, 8, 100, 0, 0, 0, 300, 2100]]
        found = game(rows)
        ready_to_pick(found)
        found.gauge = 3
        cell = cell_of(found, WRONG_ICON)
        self.assertTrue(found.press(cell))
        self.assertEqual(found.gauge, 2)
        self.assertEqual(found.shows[cell], WRONG)
        self.assertIn(SOUND_WRONG, found.sounds)
        found.gauge = 0
        found._change_gauge(-3)
        self.assertEqual(found.gauge, 0)

    def test_a_skull_empties_it(self):
        rows = [[0, 10, 20, 5, 13, 3, 8, 0, 0, 0, 99, 300, 2100]]
        found = game(rows)
        ready_to_pick(found)
        found.gauge = 7
        cell = cell_of(found, SKULL_ICON)
        self.assertIsNotNone(cell)
        found.press(cell)
        self.assertEqual(found.gauge, 0)
        self.assertEqual(found.shows[cell], WRONG)

    def test_nothing_can_be_picked_for_a_while_after_a_pick(self):
        found = game()
        ready_to_pick(found)
        found.press(cell_of(found, RIGHT_ICON))
        until(found, PLAY)
        run(found, 650 + 300 + 20)
        self.assertLess(found.guard_ms + 0, 2000)
        found.guard_ms = GUARD_MS - 1
        self.assertFalse(found.press(cell_of(found, RIGHT_ICON)))

    def test_the_other_icons_shut_at_a_pick_and_the_next_deal_comes_soon_after(self):
        found = game()
        ready_to_pick(found)
        cell = cell_of(found, RIGHT_ICON)
        found.press(cell)
        self.assertTrue(all(icon[5] == 0 for c, icon in enumerate(found.cells) if c != cell))
        self.assertEqual(found.cells[cell][5], -1)
        run(found, 120)
        self.assertEqual(found.phase, PLAY)

    def test_a_deal_nobody_picks_from_gives_way_after_its_hold(self):
        found = game()
        until(found, PLAY)
        first = [list(icon) for icon in found.cells]
        run(found, 650 + 300 + 2100 + 200)
        self.assertEqual(found.phase, PLAY)
        self.assertLess(found.cells[0][AGE], first[0][AGE] + 3000)
        self.assertEqual(found.gauge, 0)

    def test_a_full_gauge_pays_its_bonus_and_starts_the_next_round_once_the_marker_is_there(self):
        rows = [[5, 3, 20, 5, 13, 3, 8, 0, 0, 100, 0, 300, 2100], [5, 15, 20, 5, 13, 3, 8, 0, 0, 100, 0, 300, 2100]]
        found = game(rows)
        ready_to_pick(found)
        found.press(cell_of(found, RIGHT_ICON))
        self.assertTrue(found.full)
        run(found, MARKER_MS - 50)
        self.assertEqual((found.round, found.phase), (0, PAUSE))
        run(found, 100)
        self.assertEqual((found.round, found.phase), (1, ENTER))
        self.assertIn(SOUND_DONE, found.sounds)
        self.assertEqual(found.marker_at, 0)
        self.assertEqual(found.row[1], 15)
        run(found, 1100)
        self.assertEqual(found.score, 5 * 3 + 20)

    def test_after_the_last_round_they_repeat_at_random(self):
        rows = [[5, 1, 0, 5, 1, 2, 8, 100, 0, 0, 0, 300, 100], [5, 1, 0, 5, 4, 2, 8, 100, 0, 0, 0, 300, 100]]
        found = game(rows)
        rng = Rng(9)
        seen = []
        for _ in range(10):
            until(found, PLAY, rng=rng)
            seen.append(found.row[4])
            while found.guard_ms < GUARD_MS or not found.revealed(cell_of(found, RIGHT_ICON)):
                found.tick(10, rng)
            found.press(cell_of(found, RIGHT_ICON))
            until(found, ENTER, rng=rng)
        self.assertEqual(seen[:2], [1, 4])
        self.assertEqual(set(seen[2:]), {1, 4})


class EndTests(unittest.TestCase):
    def test_times_up_holds_and_then_the_story_goes_on(self):
        found = game()
        until(found, PLAY)
        found.clock_ms = 10
        found.tick(20, Rng())
        self.assertEqual(found.phase, TIME_UP)
        self.assertIn(SOUND_TIME_UP, found.sounds)
        self.assertFalse(run(found, 2980))
        self.assertTrue(run(found, 40))

    def test_results_and_the_score_a_win_takes(self):
        found = game(target=350)
        self.assertEqual(found.win_score, 345)
        self.assertEqual(game(target=400).win_score, 395)
        self.assertEqual(lowest_score(350, 98, 10), 350)
        for score, result in ((345, 2), (343, 2), (342, 1), (270, 1), (266, 1), (265, 0), (0, 0)):
            found.score = score
            self.assertEqual(found.result, result, score)


class TutorialTests(unittest.TestCase):
    def test_its_boxes_go_in_order_with_its_picks_shown_between_and_the_real_game_starts_from_the_first_round(self):
        found = game(tutorial=True)
        self.assertEqual(found.phase, GOAL)
        run(found, 5000)
        self.assertEqual(found.phase, GOAL)
        self.assertFalse(found.press(3))
        found.press()
        self.assertEqual(found.phase, GAUGE)
        found.press()
        self.assertEqual(found.phase, SELECT)
        self.assertEqual([found.cells[c][KIND] for c in (6, 7, 8)], [SKULL_ICON, WRONG_ICON, RIGHT_ICON])
        found.press()
        self.assertEqual((found.phase, found.gauge, found.shows[8]), (BARS, 3, RIGHT))
        self.assertFalse(found.press())
        run(found, MARKER_MS + 20)
        self.assertEqual(found.shows[8], 0)
        found.press()
        self.assertEqual(found.phase, PENALTY)
        found.press()
        self.assertEqual((found.phase, found.gauge, found.shows[7]), (SKULL, 2, WRONG))
        run(found, MARKER_MS + 20)
        found.press()
        self.assertEqual((found.phase, found.gauge, found.shows[6]), (READY, 0, WRONG))
        run(found, MARKER_MS + 20)
        found.press()
        self.assertFalse(found.tutorial)
        self.assertEqual(found.clock_ms, 60000)
        until(found, PLAY)
        self.assertEqual(found.round, 0)

    def test_a_state_that_doesnt_add_up_is_refused(self):
        found = game()
        found.validate()
        found.phase = 'nope'
        with self.assertRaises(ValueError):
            found.validate()


def reflex_script():
    """A script whose game is Reflex, called as '11's are, jumping past the routine's call. Its words: the rows' address at 1, the
    times' at 2, two rows, six difficulties."""
    rows = [[5, 10, 13, 3, 8, 25, 40, 20, 15], [4, 15, 13, 3, 8, 30, 25, 15, 30]]
    times = [word for level in range(1, 7) for word in (level * 100, level * 1000)]
    table = [3, 3 + 18, *rows[0], *rows[1], *times]
    site = [(0x28, 9), (0x1B, 1 | 5 << 8), (0x40, 1), *push(2), *push(350), 0x42, (0x29, 11), (0x19, 5), 0x61, call(49, 0), 0x33,
            (0x1B, 20 | 5 << 8), (0x40, 2), call(52, 13), 0x43]
    return setup_script(*site, table=table), site.index(call(49, 0))


def resources(code):
    return SimpleNamespace(library=SimpleNamespace(game_id='shs', directory=Path('.')),
                           record={'titles': ['x'], 'pack_id': 31600, 'episode_id': 5},
                           identity=dict(profile='reflex-test', episode_sha256='0' * 64),
                           program=lambda rid: code, exists=lambda rid: False, linked_program=lambda: None)


@unittest.skipUnless(HAS_PIL, 'needs Pillow')
class StoryTests(unittest.TestCase):
    def built(self):
        data, pc = reflex_script()
        res, story = story_jar(data, fallbacks={(FIRST, pc): shs11_story.OwnWords('Do it', 'Yes|Yep', 'No|Nope|Never')})
        return decode_program(ExpArchive(shs11_story.translate(res, story, None)).read(shs11_story.FIRST_SCRIPT))

    def session(self, switch=True):
        session = Session(resources(self.built()), ephemeral=True)
        session.nr_arena = switch
        session.advance()
        return session

    def test_with_the_switch_on_it_plays_reflex_with_the_routines_numbers(self):
        session = self.session()
        self.assertEqual(session.pending.name, 'shs11_reflex')
        game_ = session.engine.shs11_reflex
        self.assertEqual(game_.rounds, [[5, 10, 20, 5, 13, 3, 8, 25, 40, 20, 15, 500, 5000], [4, 15, 20, 5, 13, 3, 8, 30, 25, 15, 30, 500, 5000]])
        self.assertEqual(game_.target, 350)
        self.assertTrue(session.engine.shs11_reflex_tutorial_seen)
        self.assertFalse(session.engine.shs11_tutorial_seen)

    def test_with_the_switch_off_it_plays_what_the_smartphone_has(self):
        self.assertEqual(self.session(False).pending.name, 'word_game')

    def test_a_skip_gives_the_story_the_result_it_asks_for(self):
        for result in (2, 1, 0):
            session = self.session()
            session.skip_shs11(result)
            self.assertIsNone(session.engine.shs11_reflex)
            self.assertEqual(session.vm.result, result)

    def test_it_saves_and_comes_back_as_it_was(self):
        session = self.session()
        session.answer(None)
        session.tick(500)
        state = json.loads(json.dumps(session.snapshot()))
        again = Session.from_snapshot(resources(self.built()), state)
        self.assertEqual(again.engine.shs11_reflex, session.engine.shs11_reflex)

    def test_a_damaged_save_is_refused(self):
        state = json.loads(json.dumps(self.session().snapshot()))
        state['engine']['shs11_reflex']['phase'] = 'nope'
        with self.assertRaises(SaveError):
            Session.from_snapshot(resources(self.built()), state)

    def test_the_skip_prompt_offers_each_of_its_storys_results(self):
        from exp_runtime.desktop import shs11_skip_options
        self.assertEqual(shs11_skip_options(None), (('Win', 'Lose', 'Play'), (2, 0)))
        self.assertEqual(shs11_skip_options([(0, 1), (2, None)]), (('Win', 'Lose', 'Play'), (2, 0)))
        self.assertEqual(shs11_skip_options([(0, None)]), (('Skip', 'Play'), (2,)))
        self.assertEqual(shs11_skip_options([(0, 0), (1, 1), (2, None)]), (('Win', 'Come close', 'Lose', 'Play'), (2, 1, 0)))

    def test_a_tap_or_a_key_picks_a_cell(self):
        import pygame
        from exp_runtime.desktop import Desktop
        pygame.init()
        pygame.display.set_mode((768, 1024))
        session = self.session()
        session.answer = Mock(wraps=session.answer)
        ui = Desktop(session, audio=False)
        found = session.engine.shs11_reflex
        found.tutorial, found.phase, found.row = False, PLAY, list(ROW)
        self.assertTrue(ui._memory_key(SimpleNamespace(key=pygame.K_3)))
        session.answer.assert_called_with(2)
        ui.bg_viewport = pygame.Rect(0, 0, 768, 1024)
        ui.shs11_reflex_renderer.cell_at = lambda x, y: 6
        ui.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(300, 500)))
        session.answer.assert_called_with(6)


@unittest.skipUnless(HAS_PIL, 'needs Pillow')
class ArtTests(unittest.TestCase):
    def test_a_clear_pixel_takes_the_colour_of_the_ink_beside_it(self):
        from PIL import Image
        picture = Image.new('RGBA', (2, 1), (255, 0, 255, 0))
        picture.putpixel((1, 0), (10, 20, 30, 255))
        self.assertEqual(shs11.without_key_colour(picture).getpixel((0, 0)), (10, 20, 30, 0))

    def test_a_cut_off_round_bottom_takes_the_top_mirrored_and_one_more_row(self):
        from PIL import Image
        picture = Image.new('RGBA', (2, 5), (0, 0, 0, 255))
        picture.putpixel((0, 0), (1, 1, 1, 255))
        whole = shs11.rounded_bottom(picture, 2)
        self.assertEqual(whole.size, (2, 6))
        self.assertEqual(whole.getpixel((0, 5)), (1, 1, 1, 255))


if __name__ == '__main__':
    unittest.main()
