import unittest

from exp_runtime.dialogue_animation import DialogueAnimation, DialoguePortrait, ExpressionTransition
from exp_runtime.portrait_effects import EXPRESSION_CHANGE_MS, ball_alpha, starburst


class TimelineTests(unittest.TestCase):
    def test_the_old_and_new_art_fade_on_their_own_tracks(self):
        # exp-runtime's shared model (since v0.6.0 its ExpressionTransition track, DialogueAnimation.expression_alphas):
        # from the change at 1 s, the new art in over 0.2 s after 0.4 s, the old out over 0.8 s after 0.6 s.
        for at, alphas in ((EXPRESSION_CHANGE_MS + 399, (255, 0)), (EXPRESSION_CHANGE_MS + 500, (255, 128)),
                           (EXPRESSION_CHANGE_MS + 1000, (128, 255)), (EXPRESSION_CHANGE_MS + 1400, (0, 255))):
            track = ExpressionTransition(DialoguePortrait(10, 2000, 2, 1, 0), DialoguePortrait(10, 2006, 2, 1, 6), 6,
                                         at - EXPRESSION_CHANGE_MS)
            self.assertEqual(track.alphas, alphas)

    def test_angry_starburst_runs_for_six_tenths_of_a_second_after_its_delay(self):
        start = EXPRESSION_CHANGE_MS + 650
        self.assertIsNone(starburst(start + 49))
        scale, degrees = starburst(start + 50)
        self.assertAlmostEqual(scale, .7, delta=.05)
        self.assertEqual(degrees, 0)
        scale, degrees = starburst(start + 325)
        self.assertAlmostEqual(scale, 1.1, delta=.01)
        self.assertAlmostEqual(degrees, 45 * 275 / 600)
        self.assertIsNone(starburst(start + 650))

    def test_ball_fades_in_then_out_per_expression(self):
        start = EXPRESSION_CHANGE_MS + 650
        self.assertEqual(ball_alpha(6, start - 1), 0)
        self.assertAlmostEqual(ball_alpha(6, start + 500), 1)
        self.assertAlmostEqual(ball_alpha(6, start + 1000), .5)
        self.assertEqual(ball_alpha(6, start + 1500), 0)
        self.assertAlmostEqual(ball_alpha(8, start + 150), 1)
        self.assertEqual(ball_alpha(8, start + 1000), 0)
        self.assertEqual(ball_alpha(3, start + 100), 0)


if __name__ == '__main__':
    unittest.main()


class HdRelationshipFlourishTests(unittest.TestCase):
    SLOTS = [(-60, -5), (-55, -24), (-44, -42), (-28, -55)]

    def animation(self, previous_count, count, asset=3011, previous_asset=3011):
        from exp_runtime.relationships import RelationshipAnimation, RelationshipChange
        return RelationshipAnimation(RelationshipChange(10, asset, count, previous_asset, previous_count), 500)

    def test_new_icon_rides_an_arc_then_rests_in_its_slot_under_a_growing_ring(self):
        motion = self.animation(1, 2)
        motion.elapsed_ms = 500 + 150
        (rest, moving) = motion.hd_poses(self.SLOTS)
        self.assertEqual((rest.x, rest.y), self.SLOTS[0])
        self.assertAlmostEqual((moving.x ** 2 + moving.y ** 2) ** .5, (55 ** 2 + 24 ** 2) ** .5)
        self.assertLess(moving.y, 0)                       # halfway round the top
        motion.elapsed_ms = 500 + 300 + 250
        moving = motion.hd_poses(self.SLOTS)[1]
        self.assertEqual((moving.x, moving.y), self.SLOTS[1])
        self.assertEqual((moving.flash_asset, moving.flash_alpha), (3015, 255))
        self.assertAlmostEqual(moving.flash_scale, .75)
        motion.elapsed_ms = 500 + 300 + 499
        self.assertAlmostEqual(motion.hd_poses(self.SLOTS)[1].flash_scale, .998, places=2)
        motion.elapsed_ms = 500 + 300 + 500                      # full size, and the ring is gone (owner's photos)
        pose = motion.hd_poses(self.SLOTS)[1]
        self.assertEqual((pose.flash_asset, pose.flash_alpha, (pose.x, pose.y)), (-1, 0, self.SLOTS[1]))

    def test_a_left_portraits_flourish_is_the_same_path_mirrored_onto_its_own_slots(self):
        # Issue #7: the player's (mode 1) icons rest on the ring's right; they arc there over the top from the left,
        # not to the left and then snap across.
        right_slots = [(-x, y) for x, y in self.SLOTS]
        for elapsed in (500 + 1, 500 + 150, 500 + 299, 500 + 300 + 250):
            motion = self.animation(1, 2)
            motion.elapsed_ms = elapsed
            plain, mirrored = motion.hd_poses(self.SLOTS), motion.hd_poses(right_slots, mirror=True)
            for a, b in zip(plain, mirrored):
                self.assertAlmostEqual(b.x, -a.x)
                self.assertAlmostEqual(b.y, a.y)
        motion.elapsed_ms = 500 + 300 + 500
        self.assertEqual([(p.x, p.y) for p in motion.hd_poses(right_slots, mirror=True)], right_slots[:2])

    def test_lost_icon_rides_the_circle_then_falls(self):
        motion = self.animation(2, 1)
        motion.elapsed_ms = 500
        start = motion.hd_poses(self.SLOTS)[1]
        self.assertEqual(start.asset_id, 3016)
        self.assertAlmostEqual(start.x, self.SLOTS[1][0])
        self.assertAlmostEqual(start.y, self.SLOTS[1][1])
        motion.elapsed_ms = 500 + 100                              # still on the circle
        early = motion.hd_poses(self.SLOTS)[1]
        self.assertAlmostEqual((early.x ** 2 + early.y ** 2) ** .5, (55 ** 2 + 24 ** 2) ** .5)
        motion.elapsed_ms = 500 + 790                              # nearly at the bottom of its fall
        self.assertGreater(motion.hd_poses(self.SLOTS)[1].y, 400)
        motion.elapsed_ms = 500 + 800
        self.assertEqual(len(motion.hd_poses(self.SLOTS)), 1)


class ShakeTests(unittest.TestCase):
    """Service 89's shake (GameModel::shakeDialog / initAnimations, the same in SHS HD and CoD): one keyTimes array,
    0 / 0.75 / 1, for both sides. This fork's own version had the left side's middle key at 0.5 (a misreading)."""
    def motion(self, direction, changed):
        return DialogueAnimation(10, wobble_direction=direction, changed=changed)

    def test_box_is_hidden_then_grows_and_settles(self):
        motion = self.motion(20, True)
        motion.elapsed_ms = 699
        self.assertEqual(motion.box_alpha, 0)
        motion.elapsed_ms = 700
        self.assertEqual((motion.box_alpha, round(motion.box_rotation, 1), motion.box_scale), (255, -14.3, .5))
        motion.elapsed_ms = 700 + 187.5
        self.assertAlmostEqual(motion.box_rotation, 7.2, delta=.1)          # the 75% key, 0.125 rad
        motion.elapsed_ms = 700 + 250
        self.assertEqual((motion.box_rotation, motion.box_scale), (0.0, 1.0))

    def test_left_speaker_shakes_the_other_way_and_starts_sooner_without_a_speaker_change(self):
        motion = self.motion(-20, False)
        motion.elapsed_ms = 100
        self.assertEqual(round(motion.box_rotation, 1), 14.3)
        motion.elapsed_ms = 100 + 187.5
        self.assertAlmostEqual(motion.box_rotation, -7.2, delta=.1)         # also at 75%
        motion.elapsed_ms = 225
        self.assertEqual(motion.box_scale, 1.0)
