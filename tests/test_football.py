import copy
import json
from pathlib import Path
import unittest

from exp_runtime.content import ContentLibrary, EpisodeResources, ExpArchive, digest
from exp_runtime.shs.football import FootballTarget, Play
from exp_runtime.randomness import NativeRandom
from exp_runtime.runtime import SaveError, Session
from test_runtime import Resources, host_call, text_words
from test_vm import program


def resources(first=1, second=0, *, home=5, away=3):
    words, refs = text_words('Attack', 'Defend')
    texts = len(words); words += refs * 3
    table = len(words); words += [3, 0, 0, 100, 0x7ffe]
    args = [first, second, *([table] * 6), texts, 1, 1, 2, 60, 40, home, away,
            0, 0, 0, 1, -1, -1]
    return Resources(program(*host_call(94, *args), 0x21,
                             *host_call(95, 1), 0x21, *host_call(95, 0), 0x21,
                             (0x1f, 0xfe03), words=words))


def wait_for(session, predicate, limit=300):
    for _ in range(limit):
        if predicate():
            return
        session.tick(250)
    raise AssertionError('Football did not reach the expected state')


def start_play(session):
    g = session.engine.football
    wait_for(session, lambda: g.phase_elapsed_ms > (3500 if g.first_help else 900))
    session.answer()
    wait_for(session, lambda: g.phase == 3)


class FootballTests(unittest.TestCase):
    def test_final_score_cue_waits_for_the_second_message_entrance(self):
        for home, away, cue in ((7, 0, 8101), (0, 7, 8105), (7, 7, 8105)):
            s = Session(resources(home=home, away=away)); s.advance()
            game = s.engine.football
            game.phase, game.message_phase, game.message_ms = 11, 4, 100
            serial = game.sound_serial
            game.tick_message(99)
            self.assertEqual(game.sound_serial, serial)
            game.tick_message(1)
            self.assertEqual((game.message_phase, game.sound_ids, game.sound_serial), (6, [cue], serial + 1))
            game.tick_message(1)
            self.assertEqual(game.sound_serial, serial + 1)

    def test_exit_freezes_the_field_until_the_native_960ms_callback(self):
        s = Session(resources()); s.advance()
        g = s.engine.football
        g.enter(26, 960)
        before = copy.deepcopy(g)
        held, random = s.vm.snapshot(), copy.deepcopy(s.engine.random)
        s.tick(800)
        self.assertEqual(g.phase_ms, 160)
        before.phase_ms = 160
        self.assertEqual(g, before)
        self.assertEqual(s.vm.snapshot(), held)
        restored = Session.from_snapshot(s.resources, s.snapshot())
        s.tick(159); restored.tick(159)
        self.assertEqual(s.snapshot(), restored.snapshot())
        self.assertIsNotNone(s.engine.football)
        s.tick(1)
        self.assertIsNone(s.engine.football)
        self.assertEqual(s.engine.random, random)

    def test_shadow_action_survives_target_phases_redeal_and_save(self):
        s = Session(resources(100, 100)); s.advance(); start_play(s)
        g = s.engine.football
        wait_for(s, lambda: any(age >= 0 for age in g.shadow_ms))
        clocks = g.shadow_ms[:]
        s.tick(17)
        for old, new in zip(clocks, g.shadow_ms):
            if old >= 0:
                self.assertEqual(new, (old + 17) % 440)
        g.deal(s.engine.random)
        self.assertTrue(any(age >= 0 for age in g.shadow_ms))
        restored = Session.from_snapshot(s.resources, s.snapshot())
        s.tick(111); restored.tick(111)
        self.assertEqual(s.snapshot(), restored.snapshot())
        bad = s.snapshot(); bad['engine']['football']['shadow_ms'][0] = 440
        with self.assertRaises(SaveError):
            Session.from_snapshot(s.resources, bad)

    def test_home_touchdown_stars_consume_native_draws_and_survive_save(self):
        s = Session(resources(100, 100, home=0, away=0)); s.advance()
        g = s.engine.football
        s.engine.random = NativeRandom(1)
        expected = NativeRandom(1)
        for _ in range(450):
            expected.next()
        g.position = 4
        g.apply_play(1, 4, s.engine.random)
        self.assertEqual((g.home, g.away, g.score), (7, 0, 78))
        self.assertEqual(len(g.touchdown_stars), 50)
        self.assertEqual(s.engine.random, expected)
        self.assertTrue(all(300 <= star.delay_ms < 1300 and star.alpha == 1 and star.y == 235
                            and 145 <= star.x < 175 for star in g.touchdown_stars))
        s.tick(250); s.tick(250)
        self.assertTrue(any(star.delay_ms <= 0 and star.y < 235 for star in g.touchdown_stars))
        held = s.vm.snapshot()
        saved = s.snapshot()
        restored = Session.from_snapshot(s.resources, saved)
        for _ in range(30):
            s.tick(100); restored.tick(100)
            self.assertEqual(s.snapshot(), restored.snapshot())
        self.assertEqual(s.vm.snapshot(), held)
        self.assertEqual(s.engine.random, expected)
        for key, value in (('alpha', float('nan')), ('delay_ms', 2000), ('spin', 2.)):
            bad = copy.deepcopy(saved)
            bad['engine']['football']['touchdown_stars'][0][key] = value
            with self.subTest(key=key), self.assertRaises(SaveError):
                Session.from_snapshot(s.resources, bad)
        old = copy.deepcopy(saved); old['version'] = 21
        del old['engine']['football']['touchdown_stars']
        migrated = Session.from_snapshot(s.resources, old)
        self.assertFalse(migrated.engine.football.touchdown_stars)
        self.assertEqual(migrated.engine.random.state, saved['engine']['random']['state'])
        g.touchdown_stars.clear()
        g.position, g.defense = 96, True
        g.apply_play(-1, -4, s.engine.random)
        self.assertFalse(g.touchdown_stars)  # No celebration for the opponent.
        self.assertEqual(s.engine.random, expected)

    def test_help_gate_held_frame_and_unattended_match_result(self):
        s = Session(resources()); a = s.advance(); g = s.engine.football
        held = s.vm.snapshot()
        for _ in range(14): s.tick(250)
        s.answer()
        self.assertEqual(g.phase, 20)  # Strictly greater than 3.5 seconds.
        s.tick(1); s.answer(); self.assertEqual(g.phase, 25)
        wait_for(s, lambda: g.phase == 3)
        self.assertEqual(s.vm.snapshot(), held)
        self.assertEqual(len(g.targets), 9)
        self.assertIs(s.pending, a)
        s.engine.result_cells[0] = 123
        # No tap: all targets decay, then the worst play is applied.
        wait_for(s, lambda: s.pending.name != 'football')
        self.assertEqual(s.pending.request.args, (2, 5, 3))
        self.assertEqual(s.engine.football_scores, [5, 3])
        self.assertEqual(s.engine.result_cells[0], 123)
        self.assertIsNone(s.engine.football)

    def test_target_lifecycle_and_remapping_weighted_plans(self):
        t = FootballTarget(1, 20, 200, 800)
        t.tick(199, (3, 0)); self.assertFalse(t.visible)
        t.tick(1, (3, 0)); self.assertEqual((t.phase, t.scale), (2, 0))
        t.tick(500, (3, 0)); self.assertEqual(t.phase, 3)
        t.tick(800, (3, 0)); self.assertEqual(t.phase, 4)
        t.tick(500, (3, 0)); self.assertEqual((t.phase, t.code, t.yards), (5, 3, 0))
        t.tick(500, (3, 0)); self.assertEqual(t.phase, 6)
        t = FootballTarget(3, 0, 0, 800, phase=3)
        t.tick(800, (3, 0)); self.assertEqual((t.phase, t.elapsed_ms), (6, 800))
        s = Session(resources()); s.advance(); g = s.engine.football
        g.plans[0] = [Play(6, 90, 0, 1), Play(2, 10, 0, 0)]
        g.deal(NativeRandom(1))
        self.assertEqual({(t.code, t.yards) for t in g.targets}, {(2, 10)})
        self.assertEqual(g.worst, (2, 10))
        g.allow_pass_bonus = True; g.deal(NativeRandom(1))
        self.assertEqual({(t.code, t.yards) for t in g.targets}, {(6, 90)})
        self.assertFalse(g.eligible(Play(-4, 0, 0, 1)))
        g.down = 2; self.assertTrue(g.eligible(Play(-4, 0, 0, 1)))
        self.assertFalse(g.eligible(Play(5, 0, 0, 1)))
        g.down = 3; self.assertTrue(g.eligible(Play(5, 0, 0, 1)))
        for position, eligible in [(65, False), (66, True), (94, True), (95, False)]:
            g.position = position
            self.assertEqual(g.eligible(Play(-5, 0, 0, 1)), eligible)

    def test_touchdowns_turnovers_and_sudden_death(self):
        s = Session(resources(30, 30, home=0, away=0)); s.advance(); g = s.engine.football
        g.position = 10; g.apply_play(6, 5, s.engine.random)
        self.assertEqual((g.position, g.home, g.away, g.score, g.phase), (0, 7, 0, 90, 9))
        wait_for(s, lambda: g.phase == 21)
        self.assertTrue(g.defense); self.assertEqual(g.position, 40)
        g.position = 90; g.apply_play(-1, -10, s.engine.random)
        self.assertEqual((g.position, g.home, g.away, g.score), (100, 7, 7, 0))
        wait_for(s, lambda: g.phase == 20)
        g.apply_play(4, 111, s.engine.random)
        self.assertEqual(g.score, -50)
        wait_for(s, lambda: g.phase == 21)
        self.assertEqual(g.down, 0)
        g.half = 2; g.remaining_ms = 0; g.end_half()
        wait_for(s, lambda: g.phase == 23)
        self.assertEqual((g.half, g.remaining_ms, g.defense, g.sudden_death), (3, -1, False, True))
        g.position = 5; g.apply_play(1, 5, s.engine.random)
        wait_for(s, lambda: s.pending.name != 'football')
        self.assertEqual(s.pending.request.args, (7, 14, 7))

    def test_four_downs_switch_possession_and_clock_is_paused_in_help(self):
        s = Session(resources(100)); s.advance(); g = s.engine.football
        before = g.remaining_ms
        for _ in range(30): s.tick(250)
        self.assertEqual(g.remaining_ms, before)
        for down in range(4):
            g.apply_play(3, 0, s.engine.random)
            wait_for(s, lambda: g.phase in (2, 7))
            self.assertEqual(g.down, down + 1)
        wait_for(s, lambda: g.phase == 21)
        self.assertTrue(g.defense); self.assertEqual(g.down, 0)

    def test_save_mid_target_and_future_random_stream(self):
        r = resources(100); s = Session(r); s.engine.random = NativeRandom(1); s.advance(); start_play(s)
        for _ in range(3): s.tick(250)
        saved = json.loads(json.dumps(s.snapshot())); restored = Session.from_snapshot(r, saved)
        self.assertEqual(restored.snapshot(), s.snapshot())
        for _ in range(100):
            s.tick(33); restored.tick(33)
            self.assertEqual(s.snapshot(), restored.snapshot())
        for key, value in [('targets', []), ('half', 9), ('position', -1), ('phase', 8), ('plans', [])]:
            invalid = copy.deepcopy(saved); invalid['engine']['football'][key] = value
            with self.subTest(key=key), self.assertRaises(SaveError): Session.from_snapshot(r, invalid)

    @unittest.skipUnless(Path('Episodes/Big_Man_On_Campus.exp').exists() and Path('.shs-library/library.json').exists(), 'user content absent')
    def test_actual_football_script_frame(self):
        data = Path('Episodes/Big_Man_On_Campus.exp').read_bytes(); archive = ExpArchive(data)
        with ContentLibrary(Path('.shs-library')) as library:
            r = EpisodeResources(library, dict(sha256=digest(data), titles=archive.metadata().titles), archive)
            s = Session(r); s.vm.pc = 153  # Diagnostic entry before the original frame builder.
            s.engine.random = NativeRandom(1)
            self.assertEqual(s.advance().name, 'football')
            g = s.engine.football
            self.assertEqual((g.first_ms, g.second_ms, g.position, g.defense), (35000, 35000, 60, False))
            self.assertEqual([p.code for p in g.plans[0]], [4, 3, 2, 6, 1, 7])
            self.assertEqual([p.code for p in g.plans[1]], [-1, -2, -3, -6, -4])
            start_play(s)
            self.assertEqual(len(g.targets), 9)
            self.assertEqual(Session.from_snapshot(r, s.snapshot()).snapshot(), s.snapshot())
