"""shshd-runtime: Secret in the Shadows' round rules (shadows_rounds.ShadowsRound; Claire Hart plan S3,
CLAIRE_HART_SHADOWS_ENGINE.md section 5): the pick, the combo to x6 and its tiers, the spam lock, the Gold Key, multi-part
objects, the close-up, the Psychic Sensor, the Power-Ups, and the summary against the play-test's own numbers."""
from dataclasses import asdict
import json
import unittest

from exp_runtime import shadows_rounds as sr
from exp_runtime.randomness import Random48

# A scene: 40 ordinary objects (0-39), 4 close-up ones (40-43), a multi-part object (44) of two parts (45, 46), the key (47)
KINDS = [sr.ORDINARY] * 40 + [sr.CLOSE_UP] * 4 + [sr.WHOLE, sr.PART, sr.PART, sr.GOLD_KEY]
NAMES = [f'Thing {i}' for i in range(len(KINDS))]
PARTS = {44: [45, 46]}
KEY = 47


def a_round(story=(), powerups=sr.ONCE_EACH, seed=7):
    return sr.ShadowsRound.opened('Den_HO', NAMES, KINDS, PARTS, list(story), Random48(seed), powerups, "Claire's Den")


def find_listed(game, count, step_ms=1000):
    """Find `count` listed objects one after another (`step_ms` apart), opening the close-up for close-up ones."""
    for _ in range(count):
        obj = next(o for o in game.listed if o not in game.found)
        if game.kinds[obj] == sr.CLOSE_UP:
            game.open_pip()
        if game.kinds[obj] == sr.WHOLE:
            for part in game.parts[obj]:
                game.tap([part])
        else:
            game.tap([obj])
        game.tick(step_ms)
        while game.leaving:
            game.tick(100)


class PickingTests(unittest.TestCase):
    def test_eighteen_picked_the_first_six_ordinary(self):
        for seed in range(30):
            game = a_round(seed=seed)
            self.assertEqual(len(game.picked), 18)
            self.assertTrue(all(KINDS[o] == sr.ORDINARY for o in game.picked[:6]))
            self.assertFalse(set(game.picked) & {44, 45, 46, KEY})        # (no multi-part object or key at random)
            self.assertEqual(len(game.listed), 6)
        self.assertTrue(any(set(a_round(seed=s).picked) & {40, 41, 42, 43} for s in range(30)))    # (close-ups from the 7th)
        self.assertEqual(a_round(seed=3).picked, a_round(seed=3).picked)  # (the session's random: the same pick on reload)

    def test_story_objects_are_forced_a_multi_part_one_first(self):
        game = a_round(story=[44, 41, 5])
        self.assertEqual(game.picked[:3], [44, 41, 5])
        self.assertEqual(game.slots[0], 44)
        self.assertEqual(len(game.picked), 18)
        self.assertEqual(game.story, [44, 41, 5])


class ScoringTests(unittest.TestCase):
    def test_a_perfect_chain_of_twelve_is_5700(self):
        """ENGINE 5.4: 100 x (1+2+3+4+5+6x7); x6 holds 3 s, so a find a second finds it still there."""
        game = a_round()
        find_listed(game, 12, step_ms=500)
        self.assertTrue(game.over)
        self.assertEqual(game.find_points, 5700)
        self.assertEqual(game.x6_finds, 7)

    def test_the_combo_drops_a_tier_at_a_time(self):
        """From x6 with no finds: 3 + 3 + 5 + 7 + 9 = 27 s back to x1 (after the 0.1 s leeway)."""
        game = a_round()
        find_listed(game, 5, step_ms=200)
        self.assertEqual(game.multiplier, 6)
        game.tick(100)
        game.tick(3000)
        self.assertEqual(game.multiplier, 5)
        game.tick(3000 + 5000 + 7000)
        self.assertEqual(game.multiplier, 2)
        game.tick(9000)
        self.assertEqual(game.multiplier, 1)
        self.assertFalse(game.combo_running)

    def test_time_warp_halves_the_drain_until_x1(self):
        game = a_round()
        for obj in [o for o in game.listed if game.kinds[o] == sr.ORDINARY][:5]:
            game.tap([obj])                               # (five finds at once: x6 with its full 3 s)
        self.assertEqual(game.multiplier, 6)
        self.assertTrue(game.warp_time())
        game.tick(100)
        game.tick(5900)                                   # (x6 holds 6 s)
        self.assertEqual(game.multiplier, 6)
        game.tick(200)
        self.assertEqual(game.multiplier, 5)
        game.tick(60000)
        self.assertEqual((game.multiplier, game.time_warp), (1, False))
        self.assertFalse(game.warp_time())                # (once each round)


class MisclickTests(unittest.TestCase):
    def test_six_in_a_second_or_nine_in_six_lock_for_five(self):
        game = a_round()
        for _ in range(6):
            game.tap([])
            game.tick(100)
        self.assertEqual(game.lock_ms, sr.SPAM_LOCK_MS - 100)
        slow = a_round()
        for _ in range(9):
            slow.tap([])
            slow.tick(600)
        self.assertGreater(slow.lock_ms, 0)
        self.assertEqual(slow.misclicks, 9)

    def test_taps_in_the_lock_count_and_find_nothing(self):
        game = a_round()
        game.lock_ms = 2000
        obj = game.listed[0]
        self.assertIsNone(game.tap([obj]))
        self.assertEqual((game.misclicks, game.found), (1, []))

    def test_the_close_ups_backing_is_no_misclick(self):
        game = a_round()
        game.open_pip()
        game.backing_tap()
        self.assertEqual(game.misclicks, 0)
        self.assertEqual(len(game.clicks), 1)


class ExtrasTests(unittest.TestCase):
    def test_the_gold_key_scores_and_keeps_its_time(self):
        game = a_round()
        game.tick(42000)
        self.assertEqual(game.tap([KEY]), KEY)
        self.assertEqual((game.key_found_ms, game.find_points, game.multiplier, game.found_count), (42000, 100, 2, 0))
        self.assertIsNone(game.tap([KEY]))               # (once)

    def test_a_multi_part_object_needs_its_parts_back_to_back(self):
        game = a_round(story=[44])
        self.assertEqual(game.tap([45]), sr.PART)
        game.tap([])                                     # a misclick puts the part back
        self.assertEqual(game.collecting, [])
        self.assertEqual(game.tap([45]), sr.PART)
        self.assertEqual(game.tap([46]), 44)
        self.assertIn(44, game.found)
        loose = a_round()                                # (its object not listed: a part is a misclick)
        self.assertIsNone(loose.tap([45]))
        self.assertEqual(loose.misclicks, 1)

    def test_close_up_objects_need_the_close_up_open(self):
        game = a_round(story=[41])
        self.assertIsNone(game.tap([41]))
        game.open_pip()
        self.assertEqual(game.tap([41]), 41)
        self.assertFalse(game.pip_glow)

    def test_the_sensor_targets_by_priority_and_cools_down_after_a_find(self):
        game = a_round(story=[41])
        target = game.use_sensor()
        self.assertEqual(sr.ORDINARY, game.kinds[target])  # (ordinary objects before story and close-up ones)
        self.assertIsNone(game.use_sensor())             # (not while on)
        game.tap([target])
        self.assertFalse(game.sensor_on)
        self.assertEqual(game.sensor_cooldown_ms, sr.SENSOR_COOLDOWN_MS)
        game.tick(sr.SENSOR_COOLDOWN_MS)
        self.assertTrue(game.sensor_ready)
        self.assertEqual(game.sensor_uses, 1)

    def test_the_hint_marks_and_follows_the_power_ups_setting(self):
        game = a_round(story=[44], powerups=sr.UNLIMITED)
        first = game.hint()
        second = game.hint()
        self.assertNotEqual(first, second)               # (several markers may be out)
        off = a_round(powerups=sr.OFF)
        self.assertEqual(off.hint(), [])
        once = a_round()
        once.hint()
        self.assertEqual(once.hint(), [])
        whole = a_round(story=[44], powerups=sr.UNLIMITED)
        marked = [whole.hint() for _ in range(7)]
        self.assertIn([45, 46], marked)                  # (a multi-part object: every part marked)

    def test_clairvoyance_adds_six(self):
        game = a_round()
        self.assertTrue(game.clairvoyance())
        self.assertEqual(game.to_find, 18)
        self.assertFalse(game.clairvoyance())


class SummaryTests(unittest.TestCase):
    def test_the_play_tests_own_round(self):
        """chs_25: one misclick, the key at 89 s, about 1 1/2 minutes, no sensor, 5,300 find points -> 6,500 (the Gold Key's
        500 for every player here) and checks 1-5, 7, 9, 10: 8 half-stars."""
        game = a_round()
        game.find_points, game.misclicks, game.key_found_ms, game.elapsed_ms, game.over = 5300, 1, 89000, 92000, True
        s = game.summary()
        self.assertEqual((s['found'], s['time_bonus'], s['sensor_bonus'], s['key_bonus'], s['perfect_bonus'], s['total']),
                         (5300, 200, 500, 500, 0, 6500))
        self.assertEqual(s['half_stars'], 8)
        self.assertEqual([i + 1 for i, ok in enumerate(s['checks']) if ok], [1, 2, 3, 4, 5, 7, 9, 10])

    def test_time_bonus_by_whole_minutes(self):
        game = a_round()
        for seconds, bonus in ((59, 300), (61, 200), (239, 200), (241, 100), (361, 50), (601, 0)):
            game.elapsed_ms = seconds * 1000
            self.assertEqual(game.summary()['time_bonus'], bonus, seconds)


class RoundStyleTests(unittest.TestCase):
    def test_classics_rules_pick_a_sequel_scenes_ordinary_objects_only(self):
        """Round Style (owner, 2026-11-24): a sequel scene under Classic's rules; its screen can't show close-ups, parts
        or the key, so they're never picked, and a story object among them is left out."""
        from exp_runtime import claire_rounds as cr
        ordinary = [i for i, k in enumerate(KINDS) if k == sr.ORDINARY]
        for seed in range(10):
            game = cr.ClaireRound.opened('Den_HO', NAMES, [41, 5], Random48(seed), pool=ordinary)
            self.assertTrue(set(game.picked) <= set(ordinary))
            self.assertEqual(game.picked[0], 5)
            self.assertEqual(len(game.picked), 18)
            game.validate()
        whole = cr.ClaireRound.opened('Den_HO', NAMES[:30], [3], Random48(1))        # (no pool: every object, as before)
        self.assertEqual(whole.picked[0], 3)

    def test_the_sequels_rules_play_a_classic_scene(self):
        """...and a Classic scene under the sequel's: all ordinary, the extras never occur."""
        game = sr.ShadowsRound.opened('Office', NAMES[:30], [sr.ORDINARY] * 30, {}, [2], Random48(4))
        self.assertEqual((game.picked[0], game.key, len(game.picked)), (2, sr.NO_OBJECT, 18))
        find_listed(game, 12, step_ms=500)
        self.assertEqual(game.summary()['key_bonus'], 0)

    def test_a_scene_with_no_key_doesnt_lose_its_two_half_stars(self):
        """(owner, 2026-11-25): a Classic scene under the sequel's rules scored two stars of five at most otherwise."""
        keyless = sr.ShadowsRound.opened('Office', NAMES[:30], [sr.ORDINARY] * 30, {}, [], Random48(4))
        with_key = a_round()
        for game in (keyless, with_key):
            find_listed(game, 12, step_ms=500)
        self.assertEqual(keyless.summary()['checks'][6:8], [True, True])
        self.assertEqual(with_key.summary()['checks'][6:8], [False, False])      # (its key not found)


class SensorFeelTests(unittest.TestCase):
    def test_the_feel_follows_the_games_points(self):
        feel = sr.sensor_feel
        self.assertEqual(feel(0)[:3], (3.0, 0.30, (0, 255, 84)))        # (on it: green, three a second, particles)
        self.assertTrue(feel(0)[7])
        self.assertEqual(feel(700)[2], (127, 127, 127))                  # (far: grey, the coldest)
        self.assertEqual(feel(700)[6], 0)
        middle = feel(201)                                               # (halfway from 2 to 400)
        self.assertAlmostEqual(middle[0], 1.4, places=2)
        self.assertEqual(middle[2], (5, 162, 168))
        self.assertEqual([feel(d)[6] for d in (1.5, 100, 500, 650)], [3, 2, 1, 0])   # (1.5: the warmest, the game's slip fixed)

    def test_the_distance_is_to_the_targets_box_and_its_hint_offset(self):
        box = (100, 100, 40, 20)
        self.assertEqual(sr.sensor_distance(box, (0, 0), (110, 105)), 0)
        self.assertEqual(sr.sensor_distance(box, (0, 0), (150, 100)), 30)
        self.assertEqual(sr.sensor_distance(box, (30, 0), (150, 100)), 0)    # (shifted by its hint offset)
        self.assertAlmostEqual(sr.sensor_distance(box, (0, 0), (150, 140)), (30 ** 2 + 30 ** 2) ** 0.5)

    def test_the_ring_smooths_and_beats_at_its_rate(self):
        ring = sr.SensorRing()
        beats = []
        for _ in range(120):                                             # two seconds right on the target
            beats += ring.step(1 / 60, 0.0)
        self.assertLess(ring.distance, 1)
        self.assertGreater(len(beats), 3)
        self.assertEqual(beats[-1], 3)
        far = sr.SensorRing()
        far_beats = []
        for _ in range(240):                                             # four seconds far off
            far_beats += far.step(1 / 60, 900.0)
        self.assertTrue(1 <= len(far_beats) <= 3)                        # (half a beat a second)
        self.assertEqual(set(far_beats), {0})

    def test_the_sensor_steps_from_part_to_part(self):
        game = sr.ShadowsRound.opened('Den_HO', NAMES, KINDS, PARTS, [44], Random48(1), sr.ONCE_EACH)
        for obj in [o for o in game.listed if game.kinds[o] == sr.ORDINARY]:
            game.slots[game.slots.index(obj)] = sr.NO_OBJECT             # (only the multi-part object left listed)
        self.assertEqual(game.use_sensor(), 45)
        self.assertEqual(game.tap([45]), sr.PART)
        self.assertEqual((game.sensor_on, game.sensor_target), (True, 46))
        self.assertEqual(game.tap([46]), 44)
        self.assertFalse(game.sensor_on)


class TouchAndSpotlightTests(unittest.TestCase):
    def test_a_tap_counts_near_the_ring_only(self):
        self.assertTrue(sr.touch_counts((150, 100), (100, 100), 2))
        self.assertFalse(sr.touch_counts((250, 100), (100, 100), 2))     # (too far)
        self.assertFalse(sr.touch_counts((110, 100), (100, 100), 12))    # (a drag)

    def test_the_spotlight_follows_on_its_spring_and_breathes(self):
        import random
        light = sr.Spotlight()
        source = random.Random(5).random                                 # (Math.random: uniform)
        for _ in range(240):
            light.step(1 / 60, (300, -100), source)
        self.assertAlmostEqual(light.x, 300, delta=40)
        self.assertAlmostEqual(light.y, -100, delta=40)
        self.assertGreaterEqual(light.scale, 1.0)
        far = sr.Spotlight()
        for _ in range(240):
            far.step(1 / 60, (5000, 0), lambda: 0.5)
        self.assertEqual(far.x, sr.SPOTLIGHT_SIZE[0] / 4)                # (clamped to a quarter of its overlay)


class SaveTests(unittest.TestCase):
    def test_a_round_survives_json_and_validates(self):
        game = a_round(story=[44, 41])
        game.tap([45])
        game.tick(1500)
        data = json.loads(json.dumps(asdict(game)))
        back = sr.ShadowsRound(**data)
        back.validate()
        self.assertEqual(back.parts, {44: [45, 46]})
        self.assertEqual(back.tap([46]), 44)
        broken = sr.ShadowsRound(**dict(data, multiplier=9))
        with self.assertRaises(ValueError):
            broken.validate()


if __name__ == '__main__':
    unittest.main()
