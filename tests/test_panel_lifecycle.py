import copy
import json
from pathlib import Path
import unittest

from exp_runtime.engine import EngineAction, EngineState, PanelState
from exp_runtime.dialogue_animation import DialogueAnimation
from exp_runtime.randomness import NativeRandom
from exp_runtime.runtime import Session
from exp_runtime.scene_badge import SceneBadge
from exp_runtime.vm import KiwiVM
from test_runtime import Resources, answer_screen, host_call, text_words
from test_vm import program


class PanelLifecycleTests(unittest.TestCase):
    def test_close_discards_its_frame_and_panel_state_but_keeps_the_background(self):
        # Real device correction: this used to assert a fully blank
        # PanelState() after close, matching an earlier bug where closing
        # the dialogue panel also discarded background_id (whose own
        # dataclass default is -1) -- confirmed live as the real cause of a
        # black background right after the football minigame, whose script
        # closes the panel via this yield just before entering it. The
        # scene background is conceptually a separate layer from the
        # closing text-box widget, not something a bare panel-close should
        # erase.
        for args in ((), (123, -4)):
            for dynamic_count in (False, True):
                with self.subTest(args=args, dynamic_count=dynamic_count):
                    call = ([(0x1a, arg) for arg in args] + [(0x20, len(args)), (0x1e, 39)]
                            if dynamic_count else host_call(39, *args))
                    vm = KiwiVM(program((0x1a, 77), *call, 0x21, (0x1f, 0xfe02)))
                    engine = EngineState(
                        panel=PanelState(background_id=1045, character_id=14, speaker='Parent', text='Hello'),
                        dialogue_animation=DialogueAnimation(5),
                        notice='Old notice', notice_ms=100, next_dialogue_notice='Queued notice',
                        numbers={407: -4}, strings={'$USR': 'Alex'}, character_names={14: 'Parent'},
                        scheduled_scripts=[(25002, False)], result_cells=[42] + [None] * 9,
                        scene_badge=SceneBadge(3121, 'Before School', False), next_dialogue_wobble=True,
                        music_id=8201, sound_ids=[8006], sound_serial=7)
                    before = copy.deepcopy(engine)
                    vm.run()
                    action = engine.dispatch(vm)
                    self.assertTrue(action.completed)
                    self.assertEqual(action.name, 'close_dialogue_panel')
                    self.assertEqual(vm.run().args, (77, 0))
                    self.assertEqual(engine.panel, PanelState(background_id=1045))
                    self.assertIsNone(engine.dialogue_animation)
                    self.assertEqual((engine.notice, engine.notice_ms, engine.next_dialogue_notice), ('', 0, ''))
                    for key in ('numbers', 'strings', 'character_names', 'scheduled_scripts', 'result_cells',
                                'scene_badge', 'next_dialogue_wobble', 'music_id', 'sound_ids', 'sound_serial',
                                'random', 'random48'):
                        self.assertEqual(getattr(engine, key), getattr(before, key), key)

    def test_reopened_panel_has_a_fresh_portrait_entrance_and_no_stale_name(self):
        words, refs = text_words('First panel.', 'New panel.')
        for character in (1, 2):
            with self.subTest(character=character):
                resources = Resources(program(
                    *host_call(34, -1, 1045), *host_call(13, refs[0], 1),
                    *host_call(39), *host_call(34, -1, 1006),
                    *host_call(13, refs[1], character), 0x33, words=words))
                session = Session(resources)
                session.engine.character_names[1] = 'Friend'
                session.engine.character_art_variants[1] = [100] * 5
                session.advance()
                action = answer_screen(session)
                self.assertEqual(action.name, 'dialogue')
                self.assertEqual(session.engine.panel.background_id, 1006)
                self.assertEqual(action.details['speaker'], 'Friend' if character == 1 else '')
                motion = session.engine.dialogue_animation
                self.assertTrue(motion.changed)
                self.assertIsNone(motion.previous)
                self.assertEqual(Session.from_snapshot(resources, session.snapshot()).snapshot(), session.snapshot())

    def test_a_negative_background_base_other_than_2_also_keeps_the_current_background(self):
        # Real device correction: only base == -2 was treated as "keep the
        # current background" -- base == -1 fell through and got written
        # literally, rendering as a blank/black background. Confirmed live:
        # the real dialogue line immediately after the football minigame
        # (whose script sets base=-1 right beforehand) rendered solid black
        # instead of the story scene already on screen. The sibling KiWi
        # engine's own native disassembly (reference/codkiwi-main's
        # KIWI_CALL_REFERENCE.txt, "Locations": "GameModel::
        # setLocationImageID returns without change for negative base")
        # confirms this is a KEEP sentinel for any negative base.
        words, (text,) = text_words('Still here.')
        resources = Resources(program(
            *host_call(34, 0, 1045), *host_call(34, 0, -1),
            *host_call(13, text, 0), 0x33, words=words))
        session = Session(resources)
        session.advance()
        self.assertEqual(session.engine.panel.background_id, 1045)

    def test_existing_unsupported_save_continues_without_replaying_prior_script(self):
        words, refs = text_words('Next scene.')
        resources = Resources(
            program(*host_call(27, 100), *host_call(10, 25002, 0), *host_call(39), 0x33),
            program(*host_call(13, refs[0], 0), 0x33, words=words))
        session = Session(resources)
        while (request := session.vm.run()).yield_id != 39:
            self.assertTrue(session.engine.dispatch(session.vm).completed)
        session.pending = EngineAction('unhandled_yield', request, False)
        session.engine.numbers[407] = -4
        old = json.loads(json.dumps(session.snapshot()))
        original = copy.deepcopy(old)
        restored = Session.from_snapshot(resources, old)
        self.assertEqual(old, original)
        self.assertEqual((restored.scene, restored.scene_loads, restored.pending.name), (25002, 1, 'dialogue'))
        self.assertEqual(restored.pending.details['text'], 'Next scene.')
        self.assertEqual(restored.engine.random.state, session.engine.random.state)
        self.assertEqual(restored.engine.numbers, session.engine.numbers)
        self.assertEqual(restored.engine.scheduled_scripts, [])
        self.assertEqual(restored.vm.steps_executed, session.vm.steps_executed + 4)
        self.assertEqual(Session.from_snapshot(resources, restored.snapshot()).snapshot(), restored.snapshot())

    @unittest.skipUnless(Path('.shs-library/library.json').is_file(), 'user content unavailable')
    def test_original_football_star_scene_25013_closes_and_halts(self):
        from exp_runtime.content import ContentLibrary
        with ContentLibrary(Path('.shs-library')) as library:
            session = Session(library.open_episode('Football Star'), start_script=25013)
            session.engine.random = NativeRandom(1)
            session.advance()
            seen = []
            for _ in range(10):
                if session.pending.name != 'dialogue':
                    break
                seen.append((session.pending.request.yield_id, session.pending.request.pc))
                answer_screen(session)
            self.assertEqual(seen[0], (65, 312))
            self.assertEqual((session.pending.name, session.pending.request.pc), ('finished', 14))
            # background_id=1045 survives the close (see the real-device
            # correction on test_close_discards_its_frame_and_panel_state_
            # but_keeps_the_background above) -- confirmed against this
            # same real scene, not just the synthetic case.
            self.assertEqual(session.engine.panel, PanelState(background_id=1045))


if __name__ == '__main__':
    unittest.main()
