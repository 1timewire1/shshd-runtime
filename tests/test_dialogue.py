import copy
import json
from pathlib import Path
import unittest

from exp_runtime.content import ContentLibrary
from exp_runtime.engine import EngineState
from exp_runtime.runtime import SaveError, Session
from exp_runtime.vm import KiwiVM
from test_runtime import Resources, answer_screen, host_call, text_words
from test_vm import program


class DialogueTests(unittest.TestCase):
    def test_ios_bubble_keyframes_are_shared_and_keep_text_and_layout_independent(self):
        from exp_runtime.ui_assets import Rect
        for game in ('shs', 'cod'):
            session = self.session()
            session.resources.library.game_id = game
            motion = session.engine.dialogue_animation
            box, portrait = Rect(20, 290, 280, 100), Rect(-4, 230, 128, 128)
            vm = session.vm.snapshot()
            self.assertEqual(motion.box_rect(box, portrait), Rect(60, 289, 1, 1))
            for elapsed, expected in ((550, Rect(60, 289, 1, 1)),
                                      (610, Rect(40, 290, 140, 10)),
                                      (670, Rect(20, 290, 280, 20)),
                                      (770, Rect(20, 290, 280, 60)),
                                      (870, box)):
                session.tick(elapsed - motion.elapsed_ms)
                self.assertEqual(motion.box_rect(box, portrait), expected)
                self.assertEqual(session.vm.snapshot(), vm)
            self.assertEqual(motion.name_delay_ms, 670)
            self.assertEqual(motion.text_delay_ms, 670)
            # Opposite-side and same-side transitions use their existing
            # portrait exit/entry sequencing, then the same 320ms grow.
            for expected_delay in (550, 850):
                answer_screen(session)
                motion = session.engine.dialogue_animation
                session.tick(expected_delay + 120)
                self.assertEqual(motion.box_rect(box, portrait), Rect(20, 290, 280, 20))
            answer_screen(session)  # Same speaker keeps the full frame.
            self.assertFalse(session.engine.dialogue_animation.box_grow)
            self.assertEqual(session.engine.dialogue_animation.box_rect(box, portrait), box)

    def test_bubble_clock_pauses_and_restores_without_replaying_the_vm(self):
        from exp_runtime.ui_assets import Rect
        session = self.session()
        session.tick(720)
        saved = json.loads(json.dumps(session.snapshot()))
        restored = Session.from_snapshot(session.resources, saved)
        box, portrait = Rect(20, 290, 280, 100), Rect(-4, 230, 128, 128)
        for ms in (0, 50, 100, 200):
            session.tick(ms)
            restored.tick(ms)
            self.assertEqual(restored.snapshot(), session.snapshot())
            self.assertEqual(restored.engine.dialogue_animation.box_rect(box, portrait),
                             session.engine.dialogue_animation.box_rect(box, portrait))
        # Advancing active time is the sole animation driver; drawing does
        # not advance it, including repeated draws while paused.
        before = restored.snapshot()
        for _ in range(5):
            restored.engine.dialogue_animation.box_rect(box, portrait)
        self.assertEqual(restored.snapshot(), before)
        restored.engine.dialogue_animation.next_page(10)
        self.assertEqual(restored.engine.dialogue_animation.box_rect(box, portrait), box)

    def test_older_saves_keep_full_box_and_new_grow_state_is_validated(self):
        from exp_runtime.ui_assets import Rect
        session = self.session()
        session.tick(610)
        old = session.snapshot()
        old['version'] = 19
        del old['engine']['dialogue_animation']['box_grow']
        before = copy.deepcopy(old)
        restored = Session.from_snapshot(session.resources, old)
        box, portrait = Rect(20, 290, 280, 100), Rect(-4, 230, 128, 128)
        self.assertEqual(restored.engine.dialogue_animation.box_rect(box, portrait), box)
        self.assertEqual(restored.vm.snapshot(), session.vm.snapshot())
        self.assertEqual(restored.engine.dialogue_animation.revealed, session.engine.dialogue_animation.revealed)
        self.assertEqual(old, before)
        for value in (1, 'true', None):
            bad = session.snapshot()
            bad['engine']['dialogue_animation']['box_grow'] = value
            with self.assertRaises(SaveError):
                Session.from_snapshot(session.resources, bad)

    def test_continue_expands_after_reveal_and_survives_save_and_page_turn(self):
        for finish in (False, True):
            with self.subTest(finish=finish):
                session = self.session()
                motion = session.engine.dialogue_animation
                if finish:
                    session.answer()
                self.assertEqual(motion.continue_scale, 0)
                while not motion.complete:
                    session.tick(1)
                self.assertEqual(motion.continue_scale, 0)
                finished = motion.elapsed_ms
                vm = session.vm.snapshot()
                session.tick(125)
                self.assertEqual(motion.continue_scale, .5)
                restored = Session.from_snapshot(session.resources, session.snapshot())
                self.assertEqual(restored.engine.dialogue_animation.continue_scale, .5)
                restored.tick(125)
                self.assertEqual(restored.engine.dialogue_animation.continue_scale, 1)
                self.assertEqual(restored.vm.snapshot(), vm)
                # A large scheduler step reaches the same presentation state.
                other = self.session()
                if finish:
                    other.answer()
                other.tick(finished + 125)
                self.assertEqual(other.engine.dialogue_animation.continue_scale, .5)
                motion.next_page(10)
                self.assertEqual(motion.continue_scale, 0)

    def test_older_continue_state_migrates_without_replaying_story(self):
        session = self.session()
        session.tick(5000)
        old = session.snapshot()
        old['version'] = 16
        del old['engine']['dialogue_animation']['continue_ms']
        original = copy.deepcopy(old)
        restored = Session.from_snapshot(session.resources, old)
        self.assertEqual(old, original)
        self.assertEqual(restored.vm.snapshot(), session.vm.snapshot())
        self.assertEqual(restored.engine.dialogue_animation.continue_scale, 1)
        for value in (-1, 251, True):
            bad = restored.snapshot()
            bad['engine']['dialogue_animation']['continue_ms'] = value
            with self.assertRaises(SaveError):
                Session.from_snapshot(session.resources, bad)

    def engine(self):
        engine = EngineState()
        from exp_runtime.shs.scene_transition import SceneTransition
        engine.scene_transition = SceneTransition()
        engine.ui_defaults = {74: 0, 75: 7}
        engine.character_names = {0: 'Player', 7: 'A narrator', 32: 'Event'}
        engine.character_art_variants = {0: [100] * 5, 32: [200] * 5, 7: [-1] * 5}
        engine.numbers[engine.number_key(0, 651)] = 2
        # These text/portrait tests start with the native no-change sentinel;
        # relationship changes and their added timing have separate tests.
        for character in (32, 33):
            engine.numbers[engine.number_key(character, 3001)] = -1
        return engine

    def session(self):
        words, refs = text_words('The first line has enough letters to watch it appear.',
                                'The second speaker replies.', 'The third speaker answers.',
                                'And continues speaking.', 'A little later.')
        calls = [word for ref, character in zip(refs, (0, 32, 33, 33, 7))
                 for word in host_call(13, ref, character)]
        session = Session(Resources(program(*calls, 0x33, words=words)))
        session.engine = self.engine()
        session.engine.character_art_variants[33] = [300] * 5
        session.engine.character_names[33] = 'Third'
        session.advance()
        return session

    def test_reveal_tap_finishes_current_line_before_acknowledging_vm(self):
        session = self.session()
        before = session.vm.snapshot()
        action = session.pending
        motion = session.engine.dialogue_animation
        self.assertEqual((motion.portrait_delay_ms, motion.name_delay_ms, motion.text_delay_ms), (250, 670, 670))
        self.assertEqual((motion.revealed, motion.portrait_scale, motion.name_alpha), (0, 0, 0))
        self.assertIs(session.answer(), action)
        self.assertIs(session.answer(), action)  # Queued taps cannot skip unread text.
        session.tick(699)
        self.assertEqual(motion.revealed, 0)  # Finish respects the entrance delay.
        session.tick(1)
        self.assertEqual(motion.revealed, 1)
        self.assertFalse(motion.complete)
        session.tick(34)
        self.assertEqual(motion.revealed, len(action.details['text']))
        self.assertTrue(motion.complete)
        self.assertEqual(session.vm.snapshot(), before)
        session.answer()
        self.assertEqual(session.pending.details['text'], 'The second speaker replies.')
        self.assertNotEqual(session.vm.snapshot(), before)
        self.assertEqual(session.engine.dialogue_animation.revealed, 0)

    def test_speaker_tweens_same_side_swap_and_repeated_speaker(self):
        session = self.session()
        motion = session.engine.dialogue_animation
        session.tick(400)
        self.assertEqual(motion.portrait_scale, .5)
        self.assertEqual(motion.name_alpha, 0)
        session.tick(420)
        self.assertEqual(motion.name_alpha, 127)
        self.assertTrue(0 < motion.revealed < motion.text_length)
        answer_screen(session)
        motion = session.engine.dialogue_animation
        self.assertEqual((motion.previous.mode, motion.portrait.mode), (1, 2))
        self.assertEqual(motion.portrait_delay_ms, 250)
        session.tick(150)
        self.assertEqual(motion.previous_scale, .5)
        self.assertEqual(motion.portrait_scale, 0)
        answer_screen(session)
        motion = session.engine.dialogue_animation
        self.assertEqual((motion.previous.mode, motion.portrait.mode), (2, 2))
        self.assertEqual((motion.portrait_delay_ms, motion.text_delay_ms), (550, 970))
        answer_screen(session)
        motion = session.engine.dialogue_animation
        self.assertFalse(motion.changed)
        self.assertIsNone(motion.previous)
        self.assertEqual((motion.portrait_scale, motion.name_alpha, motion.text_delay_ms), (1, 255, 250))
        answer_screen(session)
        motion = session.engine.dialogue_animation
        self.assertIsNone(motion.portrait)
        self.assertEqual((motion.previous.character_id, motion.text_delay_ms), (33, 370))

    def test_clocks_are_independent_of_render_rate_and_mid_transition_saves(self):
        session = self.session()
        answer_screen(session)
        session.tick(137)  # Old portrait is shrinking, incoming one is delayed.
        session.answer()
        saved = json.loads(json.dumps(session.snapshot()))
        restored = Session.from_snapshot(session.resources, saved)
        self.assertEqual(json.loads(json.dumps(restored.snapshot())), saved)
        session.tick(1800)
        for elapsed in [7, 9] * 112 + [8]:
            restored.tick(elapsed)
        self.assertEqual(restored.snapshot(), session.snapshot())
        self.assertTrue(restored.engine.dialogue_animation.complete)

        # Natural reveal also uses elapsed time, including skipped render frames.
        session = self.session()
        restored = Session.from_snapshot(session.resources, session.snapshot())
        session.tick(1700)
        for _ in range(1700):
            restored.tick(1)
        self.assertEqual(restored.snapshot(), session.snapshot())
        self.assertFalse(restored.engine.dialogue_animation.complete)
        self.assertEqual(restored.engine.dialogue_animation.revealed, 31)

    def test_corrupt_motion_and_old_saves_are_validated(self):
        session = self.session()
        session.tick(800)
        original = session.snapshot()
        for key, value in (('elapsed_ms', -1), ('revealed', 9999), ('complete', 1),
                           ('text_length', 1), ('finish_step', 3)):
            with self.subTest(key=key):
                bad = copy.deepcopy(original)
                bad['engine']['dialogue_animation'][key] = value
                with self.assertRaises(SaveError):
                    Session.from_snapshot(session.resources, bad)
        bad = copy.deepcopy(original)
        bad['engine']['dialogue_animation'] = None
        with self.assertRaises(SaveError):
            Session.from_snapshot(session.resources, bad)
        for version in (2, 3):
            old = copy.deepcopy(original)
            old['version'] = version
            del old['engine']['dialogue_animation']
            untouched = copy.deepcopy(old)
            restored = Session.from_snapshot(session.resources, old)
            self.assertEqual(old, untouched)
            self.assertEqual(restored.vm.snapshot(), session.vm.snapshot())
            self.assertEqual(restored.pending.details, session.pending.details)
            self.assertTrue(restored.engine.dialogue_animation.complete)
            restored.answer()
            self.assertEqual(restored.pending.details['text'], 'The second speaker replies.')

    def test_narrator_is_selected_by_id_and_preserves_script_metadata(self):
        engine = self.engine()
        words, (ref,) = text_words('A little later.')
        vm = KiwiVM(program(*host_call(13, ref, 32), *host_call(65, 7, ref, -1), 0x33, words=words))
        vm.run()
        first = engine.dispatch(vm)
        self.assertEqual((first.details['speaker'], first.details['presentation_mode']), ('Event', 2))
        vm.resume(0); vm.run()
        second = engine.dispatch(vm)
        self.assertEqual((second.details['speaker'], second.details['visible_character_id'],
                          second.details['presentation_mode']), ('', -1, 4))
        self.assertEqual(second.details['text'], 'A little later.')
        self.assertEqual(engine.character_names[7], 'A narrator')

    def test_text_prefixes_do_not_select_the_narrator_panel(self):
        engine = self.engine()
        engine.strings = {'$WHO': 'Sam'}
        words, (ref,) = text_words('Hello $WHO!')
        for prefix, expected in [(-2, '(Hello Sam!)'), (-3, '`Hello Sam!`'), (-9, 'Hello Sam!')]:
            vm = KiwiVM(program(*host_call(13, prefix, ref, 0, 255), words=words))
            vm.run()
            details = engine.dispatch(vm).details
            self.assertEqual((details['text'], details['raw_text']), (expected, 'Hello $WHO!'))
            self.assertEqual((details['presentation_mode'], details['expression']), (1, 0))

    def test_missing_art_and_palette_inheritance(self):
        engine = self.engine()
        first = engine.present_dialogue(0, 0, 'Hello', 0)
        self.assertEqual(first['emphasis_theme'], 2)
        second = engine.present_dialogue(32, 0, 'Another line', 0)
        self.assertEqual((second['theme'], second['emphasis_theme']), (0, 2))
        third = engine.present_dialogue(100, 0, 'A voice', 0)
        self.assertEqual((third['presentation_mode'], third['speaker'], third['theme']), (3, 'Event', -1))

    def test_version_one_dialogue_save_migrates_without_replaying_vm(self):
        words, (ref,) = text_words('Later...')
        resources = Resources(program(*host_call(65, 7, ref, -1), 0x33, words=words))
        original = Session(resources)
        original.engine = self.engine()
        original.advance()
        legacy = original.snapshot()
        legacy['version'] = 1
        for field in ('presentation_mode', 'theme', 'emphasis_theme'):
            legacy['engine']['panel'].pop(field)
        legacy['engine']['panel']['character_id'] = 7
        legacy['engine']['panel']['speaker'] = 'A narrator'
        legacy['pending']['details'] = {key: value for key, value in legacy['pending']['details'].items()
                                        if key in ('text', 'raw_text', 'speaker', 'character_id', 'expression', 'mode')}
        legacy['pending']['details']['speaker'] = 'A narrator'
        unchanged = copy.deepcopy(legacy)
        restored = Session.from_snapshot(resources, legacy)
        self.assertEqual(legacy, unchanged)
        self.assertEqual(restored.vm.snapshot(), original.vm.snapshot())
        self.assertEqual(restored.pending.details['speaker'], '')
        self.assertEqual(restored.pending.details['presentation_mode'], 4)
        self.assertEqual(restored.snapshot()['version'], 26)
        self.assertEqual(restored.answer().name, 'finished')


@unittest.skipUnless(Path('.shs-library/library.json').is_file(), 'user library is not present')
class LocalDialogueTests(unittest.TestCase):
    def test_pages_hold_the_vm_save_their_offset_and_keep_the_box(self):
        words, (ref,) = text_words('The long dialogue continues. ' * 30)
        with ContentLibrary(Path('.shs-library')) as library:
            resources = library.open_episode('The_New_Girl.exp')
            resources.programs[65000] = program(*host_call(13, ref, 0), 0x33, words=words)
            session = Session(resources, start_script=65000)
            session.advance()
            box = session.dialogue_page().box
            before = session.vm.snapshot()
            first_end = session.pending.details['page_end']
            self.assertLess(first_end, len(session.pending.details['text']))
            session.answer()
            self.assertEqual(session.pending.details['page_start'], 0)
            self.assertEqual(session.vm.snapshot(), before)
            session.tick(1000)
            session.answer()
            self.assertEqual(session.pending.details['page_start'], first_end)
            self.assertEqual(session.vm.snapshot(), before)
            self.assertEqual(session.engine.dialogue_animation.revealed, 0)
            self.assertEqual(session.engine.dialogue_animation.text_delay_ms, 350)
            restored = Session.from_snapshot(resources, session.snapshot())
            self.assertEqual(restored.snapshot(), session.snapshot())
            corrupted = restored.snapshot()
            corrupted['pending']['details']['page_end'] -= 1
            with self.assertRaises(SaveError):
                Session.from_snapshot(resources, corrupted)
            turns = 1
            while restored.pending.name == 'dialogue' and turns < 100:
                self.assertEqual(restored.dialogue_page().box, box)
                answer_screen(restored)
                turns += 1
            self.assertGreater(turns, 2)
            self.assertEqual(restored.pending.name, 'finished')
