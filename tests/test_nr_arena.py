"""shshd-runtime: New Rules' minigame arena (nr_arena.py, docs/NEW_RULES.md) on authored scripts.
New Rules' own minigame library isn't a fixture; these drive the panel through the same services it calls."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from exp_runtime.nr_arena import NRArena, NUMBER_KEYS_AHEAD, NUMBER_KEYS_PROPERTY, POPUP_TEXT, opens_number_keys
from exp_runtime.runtime import Session
from test_runtime import host_call, text_words
from test_vm import program
from test_vm_linked import linked


def resources(story, library=None):
    return SimpleNamespace(library=SimpleNamespace(game_id='shs', directory=Path('.')), record={'titles': ['']},
                           identity=dict(profile='arena-test', episode_sha256='0' * 64),
                           program=lambda rid: story, exists=lambda rid: False, linked_program=lambda: library)


class ArenaModelTests(unittest.TestCase):
    def test_the_ring_turns_by_its_period_and_the_selector_finds_the_nearest_slot(self):
        arena = NRArena.opened(False, True)
        arena.set(0, 729, 6)                                # six empty slots
        arena.set(0, 740, 1)                                # turning
        arena.set(0, 719, 6000)                             # a turn in 6 s: 60 degrees a second
        for _ in range(10):
            arena.tick(100)
        self.assertEqual(arena.angle, 60)
        self.assertEqual(arena.under, 5)                    # slot 5 has come round to the front
        self.assertEqual(arena.get(726), 5)                 # the default 360-degree window: always a slot
        arena.set(0, 727, 10)                               # a 10-degree window: between two slots, none
        arena.tick(250)
        self.assertEqual(arena.get(726), -1)

    def test_keys_queue_for_the_library_and_stepped_rings_follow_the_arrows(self):
        arena = NRArena.opened(False, False)
        arena.set(0, 729, 4)
        for key in (-5, -6, -7, -1, 51):                    # fire, left soft, right soft, up, the 3 key
            arena.press(key)
        self.assertEqual([arena.get(707) for _ in range(4)], [1, 1, 2, 3])
        self.assertEqual(arena.get(772), 10)                # number keys 1-6 read as 8-13
        self.assertEqual(arena.get(707), -1)
        arena.press(-4)
        self.assertEqual(arena.direction, 0)                # the arrows step only once 720 enables them
        arena.set(0, 720, 1)
        arena.press(-4)                                     # right: step the target slot
        self.assertEqual((arena.direction, arena.target_slot), (1, 3))
        for _ in range(20):
            arena.tick(250)
        self.assertEqual((arena.direction, arena.angle, arena.under), (0, 90, 3))

    def test_labels_flash_popups_expire_and_the_panel_closes(self):
        arena = NRArena.opened(False, True)
        arena.set_label(690, 'speed: 1')
        arena.set_label(693, 'speed: max')
        arena.set(0, 747, -5, 400, text='+3')               # a "+3" flying from slot 0 to the meter
        self.assertEqual(arena.popups[0].kind, POPUP_TEXT)
        arena.tick(500)
        self.assertEqual(arena.popups, [])
        arena.tick(2600)
        self.assertEqual(arena.labels[:4], ['speed: 1', None, None, None])
        arena.set(0, 729, 1)                                # insert a slot
        self.assertEqual(len(arena.slots), 5)
        self.assertTrue(arena.set(0, 718, 0))               # 718 closes it

    def test_the_code_after_the_panel_opens_says_whether_the_game_shows_the_number_keys(self):
        def vm(*operands):
            code = [SimpleNamespace(opcode=0x1a, operand=operand) for operand in operands]
            return SimpleNamespace(pc=0, instruction_at=code.__getitem__)
        self.assertTrue(opens_number_keys(vm(712, NUMBER_KEYS_PROPERTY)))
        self.assertFalse(opens_number_keys(vm(712, 714)))           # the code's end isn't an error
        self.assertFalse(opens_number_keys(vm(*[712] * NUMBER_KEYS_AHEAD, NUMBER_KEYS_PROPERTY)))   # a later game's
        self.assertFalse(opens_number_keys(None))
        # Only as a constant pushed, not as a number used otherwise.
        other = SimpleNamespace(pc=0, instruction_at=[SimpleNamespace(opcode=0x29, operand=NUMBER_KEYS_PROPERTY)].__getitem__)
        self.assertFalse(opens_number_keys(other))

    def test_750_removes_popups_by_kind(self):
        # Sequences shows each sequence as a strip of pictures (749) and clears it with 750(3) before the next.
        arena = NRArena.opened(False, True)
        for index, picture in enumerate((17, 15, 15)):
            arena.set(-14, 749, picture, index, 3)
        arena.set(0, 747, -5, 400, text='+6')
        arena.set(0, 750, 3)
        self.assertEqual([p.kind for p in arena.popups], [POPUP_TEXT])
        arena.set(0, 750, -1)
        self.assertEqual(arena.popups, [])

    def test_times_up_takes_no_presses_until_the_score_shows(self):
        # Every game ends on two bubbles once its timer has run out, "Time's up!" and "your score: n", each waiting
        # for OK. A last tap used to skip them; now the panel drops presses until the score shows, and presses the
        # first one's OK itself after TIME_UP_MS.
        from exp_runtime.nr_arena import TIME_UP_MS, TIME_UP_SOUND
        arena = NRArena.opened(False, True)
        arena.set(0, 762, 0, -1, 0, text='press ok to start')     # before the timer: presses as usual
        arena.press(-5)
        self.assertEqual(arena.keys, [16])
        arena.set(0, 762, 0, -1, 0, text=None)
        arena.set(0, 710, 2)
        arena.tick(2000)
        arena.press(-5)                                     # a tap in flight as time runs out
        arena.set(0, 762, 0, -1, 0, text="Time's up!")
        self.assertEqual(arena.keys, [])
        self.assertEqual(arena.sounds, [TIME_UP_SOUND])     # the panel's own sound as time runs out
        arena.sounds.clear()
        arena.press(-5)
        arena.tick(TIME_UP_MS - 33)
        self.assertEqual(arena.keys, [])
        arena.tick(33)
        self.assertEqual(arena.keys, [16])                  # its own OK
        arena.keys.clear()
        arena.set(0, 762, 0, -1, 0, text=None)
        arena.press(-5)                                     # while the score is tallied
        arena.set(0, 762, 0, -1, 0, text='your score: 3')
        self.assertEqual((arena.keys, arena.sounds), ([], []))       # the score: no second sound
        arena.press(-5)
        self.assertEqual(arena.keys, [16])                  # the score takes presses again
        self.assertEqual(NRArena.from_data(arena.to_data()).time_up, 2)

    def test_the_shake_jitters_the_rings_size_and_puts_it_back(self):
        # SHAKE (shshd-runtime's, for Rhyme's wrong answers) shakes the ring as Rhythm's loop does: its size within
        # 15% of the library's own each frame, the library's own read back meanwhile, and put back after.
        from exp_runtime.nr_arena import SHAKE
        arena = NRArena.opened(False, True)
        arena.set(0, 722, 80)
        arena.set(0, SHAKE, 500)
        sizes = set()
        for _ in range(14):
            arena.tick(33)
            sizes.add(arena.ring_size)
            self.assertEqual(arena.get(722), 80)
        self.assertTrue(len(sizes) > 3 and all(65 <= size <= 95 for size in sizes))
        arena.tick(100)
        self.assertEqual((arena.ring_size, arena.shake_ms), (80, 0))

    def test_a_ring_turning_backwards_survives_a_save(self):
        # Every library and download game turns its ring with 740 = -1 (backwards) at some point; saves made then
        # were refused as corrupt (owner, 2026-10-31).
        arena = NRArena.opened(False, True)
        arena.set(0, 729, 6)
        arena.set(0, 740, -1)
        arena.set(0, 719, 6000)
        arena.tick(1000)
        restored = NRArena.from_data(arena.to_data())
        self.assertEqual((restored.motion, restored.direction, restored.angle), (-1, -1, 300))
        with self.assertRaises(ValueError):
            NRArena.from_data(dict(arena.to_data(), motion=3))


class ArenaServiceTests(unittest.TestCase):
    def test_a_game_loop_runs_frame_by_frame_and_the_score_comes_back(self):
        # Open the arena, ask "tutorial? yes|no", show an info box, then each frame read a key and add it to the score
        # until OK, close and halt with the score.
        words, (title, options, info) = text_words('tutorial?', 'yes|no', 'press ok!')
        story = program(*host_call(200, 0, 1), *host_call(210, title, options, 0), *host_call(211, info),
                        *host_call(208),                                    # 9: the frame wait
                        *host_call(203, 707), 0x21, (0x1A, 1), 0x0A,        # 10-14: the next key == OK?
                        (0x2B, 8),                                          # 15: no: on to 23
                        *host_call(206, 0, 718, 0, 0, 0), 0x33,             # 16-22: close, halt
                        (0x28, -14), words=words)                           # 23: back to 9
        session = Session(resources(story))
        self.assertEqual(session.advance().name, 'arena_entrance')      # New Rules' entrance: the script waits 2 s
        session.arena_press(-5)                                         # and keys are not taken meanwhile
        self.assertEqual(session.engine.nr_arena.keys, [])
        for _ in range(7):
            self.assertEqual(session.tick(250).name, 'arena_entrance')
        action = session.tick(250)
        self.assertEqual((action.name, action.details['options']), ('arena_menu', ['yes', 'no']))
        self.assertEqual(session.answer(1).name, 'arena_info')
        self.assertEqual(session.answer().name, 'arena_frame')
        self.assertIsNotNone(session.engine.nr_arena)
        snapshot = json.loads(json.dumps(session.snapshot()))
        self.assertEqual(snapshot['version'], 38)
        restored = Session.from_snapshot(resources(story), snapshot)
        for machine in (session, restored):
            self.assertEqual(machine.tick(33).name, 'arena_frame')      # no key: another frame
            machine.arena_press(-5)
            self.assertEqual(machine.tick(33).name, 'arena_exit')       # OK: closed; New Rules' exit plays
            self.assertTrue(machine.engine.nr_arena.leaving)
            for _ in range(7):
                self.assertEqual(machine.tick(250).name, 'arena_exit')
            machine.tick(250)
            self.assertIsNone(machine.engine.nr_arena)                  # then the script goes on
            self.assertTrue(machine.vm.pending.kind.name == 'HALT')

    def test_ask_to_skip_waits_before_an_arena_game_and_hands_the_story_its_answer(self):
        # 213 (the translator puts it before each arena game): -1 plays the game. Without Ask to Skip Mini-Games it
        # answers that at once; with it the story waits on 'arena_skip' (saved like the arena's other screens) for
        # the result to read instead.
        words, _ = text_words('x')
        store = [(0x1A, 9), 0x21, (0x1F, 54 << 8 | 2)]                      # global 9 = the answer
        story = program(*host_call(213), *store, 0x33, words=words)

        def answer(session):
            return session.engine.numbers.get(session.engine.number_key(0, 9), 0)
        session = Session(resources(story))
        session.advance()
        self.assertEqual(answer(session), -1)
        session = Session(resources(story))
        session.skip_arena = True
        self.assertEqual(session.advance().name, 'arena_skip')
        restored = Session.from_snapshot(resources(story), json.loads(json.dumps(session.snapshot())))
        self.assertEqual(restored.pending.name, 'arena_skip')
        with self.assertRaises(ValueError):
            restored.answer(-2)
        restored.answer(5)
        self.assertEqual(answer(restored), 5)

    def test_the_arena_query_needs_the_library_and_the_switch(self):
        words, _ = text_words('x')
        store = [(0x1A, 9), 0x21, (0x1F, 54 << 8 | 2)]                      # global 9 = the answer
        story = program(*host_call(70, 200), *store, 0x33, words=words)
        library = linked(0x43, data_boundary=200, code_boundary=100)
        for attached, switch, expected in ((None, True, 0), (library, False, 0), (library, True, 1)):
            session = Session(resources(story, attached))
            session.nr_arena = switch
            session.advance()
            self.assertEqual(session.engine.numbers.get(session.engine.number_key(0, 9), 0), expected)

    def test_new_rules_formats_into_its_own_slots(self):
        words, (pattern,) = text_words('speed: %d')
        story = program(*host_call(209, -2, pattern, 7), (0x1A, 9), 0x21, (0x1F, 54 << 8 | 2), 0x33, words=words)
        session = Session(resources(story))
        session.advance()
        self.assertEqual(session.engine.dynamic_strings[1], 'speed: 7')     # New Rules' -2 is slot 1
        self.assertEqual(session.engine.numbers[session.engine.number_key(0, 9)], 0x7FF5 + 1)


if __name__ == '__main__':
    unittest.main()
