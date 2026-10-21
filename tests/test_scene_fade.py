import unittest

from exp_runtime.scene_fade import blind_rects, coverage, in_ms, out_ms


class SceneFadeTests(unittest.TestCase):
    def test_out_closes_in_1_2_seconds_and_holds(self):
        self.assertEqual(coverage(2, 'out', 0), 0)
        self.assertAlmostEqual(coverage(2, 'out', 600), .5)
        self.assertEqual(coverage(2, 'out', 1500), 1)
        self.assertEqual(out_ms(2), 1500)

    def test_blinds_wait_before_opening_but_the_fade_holds_black_first(self):
        self.assertEqual(coverage(1, 'in', 299), 1)
        self.assertAlmostEqual(coverage(1, 'in', 900), .5)
        self.assertEqual(coverage(1, 'in', 1800), 0)
        self.assertEqual(in_ms(1), 1800)
        self.assertEqual(coverage(6, 'in', 1199), 1)
        self.assertAlmostEqual(coverage(6, 'in', 1350), .5)
        self.assertEqual(in_ms(6), 1500)

    def test_sixteen_strips(self):
        rects = blind_rects(2, .5, (768, 1024))
        self.assertEqual(len(rects), 16)
        self.assertEqual(rects[1], (48, 0, 24, 1024))
        self.assertEqual(blind_rects(1, 1, (768, 1024))[1], (0, 64, 768, 64))
        self.assertEqual(blind_rects(2, 0, (768, 1024)), [])

    def test_the_session_model_shares_the_timing(self):
        # fade_transition.FadeTransition (the queued transition) and this module (the player's own fades) agree.
        from exp_runtime.fade_transition import FadeTransition
        for kind in (1, 2, 6):
            for phase, name in ((4, 'out'), (3, 'in')):
                for ms in (0, 600, 1199, 1200, 1350, 1499):
                    with self.subTest(kind=kind, phase=name, ms=ms):
                        track = FadeTransition(selector=kind, phase=phase, elapsed_ms=ms)
                        self.assertAlmostEqual(track.coverage, coverage(kind, name, ms))


class HdTransitionTests(unittest.TestCase):
    """SHS HD's queued transition is the session's FadeTransition, as CoD's is (fade_transition.py)."""

    def session(self, selector, *, hd=True, title=False):
        from exp_runtime.runtime import Session
        from test_runtime import Resources, host_call, text_words
        from test_vm import program
        words, (first, second, card) = text_words('Before.', 'After.', 'Week 2')
        nxt = host_call(8, card, second, 1000, 0) if title else host_call(13, second, 0)
        resources = Resources(program(*host_call(16, selector), *host_call(13, first, 0), *nxt, 0x33, words=words))
        if hd:
            resources.library.hd_app_version = lambda: '1.4.38'
        session = Session(resources)
        session.advance()
        session.tick(4000)
        return session

    def test_the_hd_bundle_selects_the_visual_model_and_android_keeps_its_own(self):
        from exp_runtime.fade_transition import FadeTransition
        from exp_runtime.shs.scene_transition import SceneTransition
        self.assertIsInstance(self.session(6).engine.scene_transition, FadeTransition)
        self.assertIsInstance(self.session(6, hd=False).engine.scene_transition, SceneTransition)

    def test_selector_20_draws_libc_rand_not_lrand48(self):
        # setupQueuedFade (SHS HD 000125f8) calls `_rand`; the KiWi / mini-game stream is untouched.
        session = self.session(20)
        before = session.engine.random48.state
        session.answer()
        transition = session.engine.scene_transition
        self.assertEqual(session.engine.random48.state, before)
        self.assertEqual((transition.selector, transition.random_state), (2, 16807))   # 16807 is odd: selector 2

    def test_the_script_waits_for_the_closed_blinds_and_a_title_card_skips_the_fade_in(self):
        session = self.session(1, title=True)
        old = session.pending
        session.answer()
        session.tick(1499)
        self.assertIs(session.pending, old)
        session.tick(1)                                          # GameModel::tick: a title card, no fade-in
        self.assertEqual(session.pending.name, 'presentation')
        self.assertFalse(session.transitioning)

    def test_the_next_dialogue_is_revealed_settled_and_holds_its_text(self):
        session = self.session(6)
        session.answer()
        session.tick(1500)
        self.assertEqual((session.pending.name, session.engine.scene_transition.phase), ('dialogue', 3))
        motion = session.engine.dialogue_animation
        revealed = motion.revealed
        session.tick(1000)                                       # the black layer is still up: no typing yet
        self.assertEqual(motion.revealed, revealed)
        self.assertEqual(session.engine.scene_transition.coverage, 1.0)
        session.tick(500)
        self.assertFalse(session.transitioning)


if __name__ == '__main__':
    unittest.main()
