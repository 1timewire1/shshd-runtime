"""shshd-runtime: New Rules' minigame arena (nr_arena.py, reference/Other Games/docs/NR_ARENA.md) on authored scripts.
New Rules' own minigame library isn't a fixture; these drive the panel through the same services it calls."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from exp_runtime.nr_arena import NRArena, POPUP_TEXT
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
        self.assertEqual(snapshot['version'], 30)
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
