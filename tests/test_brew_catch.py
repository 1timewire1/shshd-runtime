"""The BREW games' catch game: its rules (brew_catch.py, shs08.5.mod's own code), and the translator's call (brew.py catch_game)."""
from dataclasses import asdict
import random
import unittest

from exp_runtime.brew_catch import (ANGLED, CIRCLE_POINTS, END_MS, FIELD_HEIGHT, FIELD_WIDTH, ORBIT, SIDEWAYS, TICK_MS, CatchGame)
from exp_runtime.runtime import _typed_value
from exp_runtime.vm import KiwiVM, StopKind

import test_translate
from test_translate import HAS_PIL, Rewriter, call, program

SIZES = {133: (29, 26), 151: (30, 30), 152: (30, 30)}
ITEMS = [(-2, 151, 20), (4, 152, 30)]


class Rng:
    def __init__(self, seed=1):
        self.random = random.Random(seed)

    def next(self):
        return self.random.getrandbits(31)

    def below(self, bound):
        return self.random.randrange(bound)


def opened(mode=ORBIT, target=45, items=ITEMS, rng=None, chance=0, angle=0):
    return CatchGame.opened(mode, target, 350, 350, 50 if mode == ORBIT else 0, chance, angle, 133, items, SIZES, rng or Rng())


def play(game, rng, ms=60000, step=33):
    for elapsed in range(0, ms, step):
        if game.tick(step, rng):
            return elapsed
    raise AssertionError('the game never finished')


class CatchRulesTests(unittest.TestCase):
    def test_a_lap_of_the_orbit_takes_two_seconds_whatever_the_frame_rate(self):
        for step in (16, 33, 50, 100):
            game = opened(items=[(4, 152, 1)])
            game.spawn_ms = -10 ** 6
            start = game.orbit_at
            for _ in range(2000 // step):
                game.tick(step, Rng())
            game.tick(2000 % step, Rng())
            self.assertEqual(game.orbit_at, start, step)
        self.assertEqual(TICK_MS * CIRCLE_POINTS, 2000)

    def test_turning_back_goes_the_other_way_round(self):
        game = opened(items=[(4, 152, 1)])
        game.spawn_ms = -10 ** 6                # nothing comes, and it isn't over
        start, direction = game.orbit_at, game.direction
        game.press()
        game.tick(TICK_MS, Rng())
        self.assertEqual(game.orbit_at, (start - direction) % CIRCLE_POINTS)

    def test_an_item_touching_the_player_scores_its_value_and_goes(self):
        game = opened(items=[(4, 152, 1), (-2, 151, 1)])
        game.objects = [[game.x, game.y, 0, 0, 0], [game.x, game.y, 0, 0, 1]]
        game.spawn_ms = -10 ** 6                # nothing new
        game.tick(11, Rng())
        self.assertEqual((game.score, game.objects), (2, []))

    def test_the_score_stays_between_nothing_and_the_target(self):
        game = opened(items=[(-2, 151, 1)])
        game.objects = [[game.x, game.y, 0, 0, 0]]
        game.spawn_ms = -10 ** 6
        game.tick(11, Rng())
        self.assertEqual(game.score, 0)
        game = opened(target=3, items=[(4, 152, 1)])
        game.objects = [[game.x, game.y, 0, 0, 0]]
        game.tick(11, Rng())
        self.assertEqual((game.score, game.result, game.over, game.out_of_items), (3, 3, True, False))

    def test_every_kind_ends_once_its_items_are_gone_and_a_second_after(self):
        for mode in (ORBIT, ANGLED, SIDEWAYS):
            rng = Rng(mode)
            game = opened(mode, target=500, rng=rng, chance=50, angle=40)
            play(game, rng)
            self.assertEqual((game.remaining, game.objects, game.digit), (0, [], 0), mode)
            self.assertTrue(game.out_of_items and 0 <= game.result <= 500)
            self.assertGreater(game.end_ms, END_MS)

    def test_items_stay_in_play_only_inside_the_field(self):
        rng = Rng(3)
        game = opened(ANGLED, target=500, rng=rng, chance=100, angle=40)
        for _ in range(300):
            game.tick(33, rng)
            for item in game.objects:
                # (one step past an edge at most: the next step takes it away)
                self.assertTrue(-60 <= item[0] >> 8 <= FIELD_WIDTH + 10 and -60 <= item[1] >> 8 <= FIELD_HEIGHT + 10)
            self.assertTrue(0 < game.x >> 8 < FIELD_WIDTH)

    def test_the_ring_counts_down_from_nine(self):
        game = opened(items=[(4, 152, 9)])
        self.assertEqual(game.digit, 9)
        game.remaining = 0
        game.objects = [[0, 0, 0, 0, 0]]
        self.assertEqual(game.digit, 1)            # not over yet: an item's still in play
        game.objects = []
        self.assertEqual(game.digit, 0)

    def test_a_game_in_progress_saves_and_comes_back(self):
        rng = Rng(5)
        game = opened(rng=rng)
        for _ in range(40):
            game.tick(33, rng)
        back = _typed_value(asdict(game), CatchGame)
        back.validate()
        self.assertEqual(back, game)
        broken = _typed_value(dict(asdict(game), direction=0), CatchGame)
        with self.assertRaises(ValueError):
            broken.validate()


@unittest.skipUnless(HAS_PIL, 'needs Pillow for the translator')
class CatchCallTests(unittest.TestCase):
    def run_call(self, query, word_result=5, game_result=40, page=None):
        import brew
        words = [2, -2 & 0xffff, 151, 20, 4, 152, 30]
        code = [(0x1A, 45), (0x1A, 350), (0x1A, 350), (0x1A, 50), (0x1A, 0), (0x1A, 133), call(19, 6), 0x21, call(99, 1), 0x33]
        if page is not None:                # BREW's page before the game: (title, text) to 12
            title, text = len(words), len(words) + len(test_translate.text_words(page[0]))
            words += test_translate.text_words(page[0]) + test_translate.text_words(page[1])
            code = [(0x1A, title), (0x1A, text), call(12, 2)] + code
        prog = program(*code, words=words)
        rewriter = Rewriter(prog)
        context = brew.script_context(rewriter, 25001, {}, True, prog, SIZES)
        for pc, service, argc in rewriter.calls():
            if service == 19:
                brew.catch_game(rewriter, pc, argc, context)
            elif service == 12:
                brew.game_page(rewriter, pc, argc, context)
        vm = KiwiVM(rewriter.finish())
        seen, store = {}, {}

        def read(address):
            out = bytearray()
            for w in vm.data[address:]:
                w &= 0xffff
                for c in (w >> 8, w & 255):
                    if not c:
                        return out.decode()
                    out.append(c)
        for _ in range(20000):
            stop = vm.run()
            if stop.kind == StopKind.HALT:
                return seen
            args, answer = stop.args, 0
            if stop.yield_id == 70:
                answer = query
            elif stop.yield_id == 25:
                test_translate.BrewShimTests.brew_append(vm, args)
            elif stop.yield_id == 71:
                seen[71] = (read(args[0]), read(args[1]), read(args[2]), read(args[3]))
                answer = word_result
            elif stop.yield_id == 33:
                seen[33] = (read(args[0]), read(args[1]))
            elif stop.yield_id == 221:
                seen[221] = list(args[:8]) + [list(vm.data[args[8]:args[8] + 7])]
                answer = game_result
            elif stop.yield_id == 99:
                seen[99] = args[0]
            elif stop.yield_id == 52:
                store[args[0], args[1]] = args[2]
            elif stop.yield_id == 53:
                answer = store.get((args[0], args[1]), 0)
            vm.resume(answer)
        self.fail('did not halt')

    def test_with_the_switch_on_it_plays_the_catch_game_and_returns_its_score(self):
        seen = self.run_call(1)
        self.assertNotIn(71, seen)
        self.assertEqual(seen[221][:8], [ORBIT, 45, 350, 350, 50, 0, 0, 133])
        self.assertEqual(seen[221][8], [2, -2, 151, 20, 4, 152, 30])
        self.assertEqual(seen[99], 40)

    def test_with_it_off_it_plays_a_word_game_and_scales_its_result_onto_the_target(self):
        for result, score in ((6, 45), (9, 45), (5, 37), (4, 30), (0, 0)):
            seen = self.run_call(0, result)
            self.assertNotIn(221, seen)
            self.assertEqual(seen[71][2:], ('Happy|Smile', 'Scared|Nervous'))
            self.assertEqual(seen[99], score, result)

    def test_the_word_game_drops_the_catch_games_points_and_its_generic_title(self):
        page = ('Instructions', 'Dodge the scared faces to keep fear out of your heart! Try to stay happy. 45 pts to pass.')
        seen = self.run_call(0, 6, page=page)
        self.assertEqual(seen[71][:2], ('Think fast!', 'Dodge the scared faces to keep fear out of your heart! Try to stay happy.'))
        seen = self.run_call(0, 6, page=('Bowl right!', 'Knock down the pins! 55 points to win!'))
        self.assertEqual(seen[71][:2], ('Bowl right!', 'Knock down the pins!'))

    def test_the_real_game_keeps_brews_page_as_it_is(self):
        page = ('Instructions', 'Dodge the scared faces. 45 pts to pass.')
        self.assertEqual(self.run_call(1, page=page)[33], page)

    def test_every_picture_has_two_words(self):
        import brew
        self.assertTrue(all(len(pair) == 2 and all(pair) for pair in brew.CATCH_WORDS.values()))
        self.assertEqual(set(SIZES) - set(brew.CATCH_WORDS), set())


if __name__ == '__main__':
    unittest.main()
