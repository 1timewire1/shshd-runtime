"""Claire Hart Classic's hidden-object round (Claire Hart plan Stage 3, step 1): build 157's rules (hogscene, activeobjectlist,
touchdetector, combometer, timer, levelsummary, the power-ups; gamebalance.json), against the numbers its play-test showed:
7,000 for a quick clean round of 12, 10,000 with Clairvoyance's 18, a skill bonus of 900 for one misclick."""
from dataclasses import asdict
import json
import unittest

from exp_runtime import claire_rounds as cr
from exp_runtime.randomness import Random48
from exp_runtime.runtime import _typed_value

NAMES = [f'Thing {i}' for i in range(50)]


def a_round(story=(), powerups=cr.ONCE_EACH, seed=7, names=NAMES):
    return cr.ClaireRound.opened('ClairesOffice', names, list(story), Random48(seed), powerups)


def find_next(game):
    """Find a listed, unfound object, then let its name leave (the next comes in)."""
    target = next(o for o in game.listed if o not in game.found)
    assert game.tap([target]) == target
    game.tick(cr.FOUND_MS + cr.NAME_HIDE_MS)
    return target


class PickingTests(unittest.TestCase):
    def test_twelve_and_six_more_are_picked_with_the_story_objects_first(self):
        game = a_round(story=[40, 3])
        self.assertEqual(len(game.picked), cr.SOL_SIZE + cr.ADD_OBJECTS)
        self.assertEqual(game.picked[:2], [40, 3])                      # forced in, listed first (G2)
        self.assertEqual(len(set(game.picked)), 18)
        self.assertEqual(game.slots, game.picked[:6])
        self.assertEqual(game.to_find, 12)
        self.assertEqual(a_round(story=[40, 3]).picked, game.picked)    # the session's random: the same pick on reload
        self.assertNotEqual(a_round(seed=8).picked, a_round(seed=7).picked)

    def test_a_small_scene_picks_what_it_has(self):
        game = a_round(names=NAMES[:10])
        self.assertEqual((len(game.picked), game.to_find), (10, 10))
        self.assertFalse(game.can_use(cr.CLAIRVOYANCE))                  # nothing left to add


class ScoringTests(unittest.TestCase):
    def test_a_quick_clean_round_scores_7000_and_five_stars(self):
        game = a_round()
        for _ in range(12):
            find_next(game)
        self.assertTrue(game.over)
        self.assertEqual(game.score, 100 + 200 + 300 + 400 + 8 * 500)  # the combo rises to x5
        summary = game.summary()
        self.assertEqual((summary['time_bonus'], summary['skill_bonus'], summary['total'], summary['half_stars']),
                         (1000, 1000, 7000, 10))
        self.assertEqual(game.result, 7000)
        self.assertFalse(game.finished)
        game.finish()
        self.assertTrue(game.finished)

    def test_clairvoyance_makes_eighteen_and_10000(self):
        game = a_round()
        self.assertTrue(game.clairvoyance())
        self.assertEqual(game.to_find, 18)
        self.assertFalse(game.can_use(cr.CLAIRVOYANCE))                  # once a round, whatever the setting
        while not game.over:
            find_next(game)
        self.assertEqual(game.found_count, 18)
        self.assertEqual(game.summary()['total'], 10000)
        self.assertTrue(any(game.extra))                                # the six extra names were blue

    def test_one_misclick_leaves_900_skill(self):
        game = a_round()
        self.assertIsNone(game.tap([]))
        self.assertIsNone(game.tap([game.picked[-1]]))                  # picked but not listed: also a miss
        self.assertEqual(game.misclicks, 2)
        self.assertEqual(game.summary()['skill_bonus'], 800)
        game.misclicks = 11
        self.assertEqual(game.summary()['skill_bonus'], 0)

    def test_the_time_bonus_falls_from_three_minutes_to_six(self):
        game = a_round()
        for seconds, bonus in ((179, 1000), (180, 1000), (181, 995), (270, 500), (360, 0), (361, 0)):
            game.elapsed_ms = seconds * 1000
            self.assertEqual(game.summary()['time_bonus'], bonus, seconds)
        game.elapsed_ms = 1499
        self.assertEqual(game.seconds, 1)                               # rounded, as timer.js shows it

    def test_the_combo_drains_in_ten_seconds_and_resets(self):
        game = a_round()
        find_next(game)
        find_next(game)
        self.assertEqual(game.multiplier, 3)
        game.tick(9000)
        self.assertEqual(game.multiplier, 3)
        game.tick(1200)
        self.assertEqual((game.multiplier, game.combo_running), (1, False))
        before = game.score
        find_next(game)
        self.assertEqual(game.score - before, 100)

    def test_time_warp_halves_the_drain_until_the_combo_empties(self):
        game = a_round()
        find_next(game)
        self.assertTrue(game.warp_time())
        game.tick(12000)
        self.assertTrue(game.combo_running)                             # at half speed: 20 s
        game.tick(9000)
        self.assertFalse(game.combo_running)
        self.assertFalse(game.time_warp)                                # over once the combo emptied
        self.assertFalse(game.warp_time())                              # once each a round (the default)


class MisclickTests(unittest.TestCase):
    def test_six_quick_misclicks_lock_taps_for_five_seconds(self):
        game = a_round()
        for _ in range(6):
            game.tap([])
            game.tick(100)
        self.assertGreater(game.lock_ms, 0)
        listed = game.listed[0]
        self.assertIsNone(game.tap([listed]))                          # locked: even a listed object is a miss
        game.tick(cr.SPAM_LOCK_MS)
        self.assertEqual(game.tap([listed]), listed)

    def test_misclicks_spread_out_dont_lock(self):
        game = a_round()
        for _ in range(8):
            game.tap([])
            game.tick(2000)
        self.assertEqual(game.lock_ms, 0)


class HintAndPowerupTests(unittest.TestCase):
    def test_the_hint_points_at_a_listed_object_and_refills_after(self):
        game = a_round(story=[5])
        random = Random48(1)
        target = game.hint(random)
        self.assertIn(target, game.listed)
        self.assertFalse(game.hint_ready)                               # its star is out
        self.assertFalse(game.can_use(cr.FOCUS))                        # and locks Focus and the Locator
        game.tap([target])
        self.assertFalse(game.hint_ready)                               # the orb refills
        game.tick(cr.HINT_REFILL_MS)
        self.assertTrue(game.hint_ready)

    def test_the_hint_may_point_at_a_story_object(self):
        """R5 (owner, 2026-11-20): Classic's hint skipped story objects; here it doesn't."""
        hinted = set()
        for seed in range(40):
            game = a_round(story=[5])
            hinted.add(game.hint(Random48(seed)))
        self.assertIn(5, hinted)

    def test_the_psychic_locator_marks_the_name_picked(self):
        game = a_round()
        self.assertTrue(game.locate())
        self.assertTrue(game.locating)
        self.assertIsNone(game.hint(Random48(1)))                       # locked while it waits
        obj = game.pick_located(2)
        self.assertEqual(obj, game.slots[2])
        self.assertEqual(game.locator_target, obj)
        game.tap([obj])
        self.assertEqual(game.locator_target, cr.NO_OBJECT)

    def test_focus_marks_a_random_listed_object(self):
        game = a_round()
        target = game.focus(Random48(3))
        self.assertIn(target, game.listed)
        self.assertFalse(game.can_use(cr.FOCUS))                        # once each a round

    def test_the_power_ups_setting(self):
        game = a_round(powerups=cr.UNLIMITED)
        for _ in range(3):
            self.assertTrue(game.warp_time())
            game.time_warp = False
        self.assertIsNone(game.uses_left(cr.FOCUS))
        self.assertEqual(game.uses_left(cr.CLAIRVOYANCE), 1)            # still once a round
        off = a_round(powerups=cr.OFF)
        self.assertFalse(any(off.can_use(p) for p in cr.POWERUPS))
        self.assertIsNotNone(off.hint(Random48(1)))                     # the hint is free whatever the setting


class StateTests(unittest.TestCase):
    def test_a_round_saves_and_resumes_exactly(self):
        """R3 (owner, 2026-11-20): a save mid-round resumes it as it was."""
        game = a_round(story=[9])
        find_next(game)
        game.tap([])
        game.warp_time()
        game.tick(1234)
        saved = json.loads(json.dumps(asdict(game)))
        restored = _typed_value(saved, cr.ClaireRound)
        restored.validate()
        self.assertEqual(restored, game)

    def test_bad_state_is_refused(self):
        game = a_round()
        game.slots[0] = 49 if 49 not in game.picked else 48
        with self.assertRaises(ValueError):
            game.validate()


class PixelHitTests(unittest.TestCase):
    def test_a_tap_hits_within_a_nine_pixel_window(self):
        # a 20 x 20 sprite with one opaque pixel at (10, 10)
        def alpha(x, y):
            return 255 if (x, y) == (10, 10) else 0
        self.assertTrue(cr.pixel_hit(alpha, 20, 20, 10, 10))
        self.assertTrue(cr.pixel_hit(alpha, 20, 20, 14, 6))             # 4 away each way: inside the window
        self.assertFalse(cr.pixel_hit(alpha, 20, 20, 15, 10))
        self.assertFalse(cr.pixel_hit(alpha, 20, 20, 0, 0))


if __name__ == '__main__':
    unittest.main()
