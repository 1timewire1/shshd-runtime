"""Services 7/63 terminate a scene and retire its ordinary Resume entry."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from exp_runtime.content import ContentLibrary, digest, import_game
from exp_runtime.engine import EngineAction, PanelState
from exp_runtime.loading import LoadingScreen
from exp_runtime.menu import MenuState
from exp_runtime.runtime import SaveError, Session
from exp_runtime.scene_badge import SceneBadge
from exp_runtime.trace import trace_archive
from exp_runtime.vm import VMError
from test_content import FAKE_NATIVE, archive, make_apk, metadata
from test_runtime import Resources, host_call
from test_vm import program


def exit_program(service=7, args=(), *, dynamic=False):
    call = ([(0x1a, a) for a in args] + [(0x20, len(args)), (0x1e, service)]
            if dynamic else host_call(service, *args))
    # The scheduled resource is deliberately absent. Neither it nor the
    # numeric write after the exit may execute.
    return program(*host_call(10, 29999, 1), *call, *host_call(54, 999, 12), 0x33)


class EpisodeExitTests(unittest.TestCase):
    def test_aliases_ignore_all_arguments_and_never_run_the_tail_or_queue(self):
        for service in (7, 63):
            for dynamic in (False, True):
                for args in ((), (-32768, 0x7fff, 321)):
                    with self.subTest(service=service, dynamic=dynamic, args=args):
                        s = Session(Resources(exit_program(service, args, dynamic=dynamic)))
                        s.engine.numbers[12] = 456
                        s.engine.character_expressions = {0: 1, 199: 3, 200: 2}
                        s.engine.character_names[0] = 'Alex'
                        s.engine.character_art_variants[0] = [101] * 5
                        s.engine.strings['$NAME'] = 'Sam'
                        s.engine.dynamic_strings[0] = 'Retained slot'
                        s.engine.result_cells[0] = 17
                        random = s.engine.random.state, s.engine.random48.state
                        action = s.advance()
                        self.assertEqual(action.name, 'episode_exit')
                        self.assertTrue(s.episode_exited)
                        self.assertEqual(action.request.args, args)
                        self.assertIs(action.request, s.vm.pending)
                        self.assertEqual(s.scene_loads, 0)
                        self.assertEqual(s.engine.scheduled_scripts, [])
                        self.assertEqual(s.engine.numbers, {})
                        self.assertEqual(s.engine.character_expressions, {200: 2})
                        self.assertEqual(s.engine.character_names, {0: 'Alex'})
                        self.assertEqual(s.engine.character_art_variants, {0: [101] * 5})
                        self.assertEqual(s.engine.strings, {'$NAME': 'Sam'})
                        self.assertEqual(s.engine.dynamic_strings[0], 'Retained slot')
                        self.assertEqual(s.engine.result_cells[0], 17)
                        self.assertEqual((s.engine.random.state, s.engine.random48.state), random)
                        # The final VM frame is an audit record, with no callback.
                        held = s.snapshot()
                        self.assertIs(s.advance(), action)
                        self.assertIs(s.tick(10000), action)
                        with self.assertRaises(VMError):
                            s.answer()
                        self.assertEqual(s.snapshot(), held)
                        restored = Session.from_snapshot(s.resources, json.loads(json.dumps(held)))
                        self.assertEqual(restored.snapshot(), held)

    def test_scene_teardown_removes_panels_and_gates_without_completion_callbacks(self):
        s = Session(Resources(exit_program()))
        s.engine.panel = PanelState(background_id=42, character_id=1, speaker='Alex', text='Last line')
        s.engine.loading = LoadingScreen(True)
        s.engine.scene_badge = SceneBadge(41, 'Evening', False)
        s.engine.next_dialogue_notice = s.engine.notice = 'Notice'
        s.engine.notice_ms = 1000
        s.engine.last_input = 'Input'
        s.engine.scene_value = 20  # Closing a scene must not consume callback RNG.
        s.engine.music_id = 8201
        s.engine.sound_id, s.engine.sound_serial = 8010, 3
        random = s.engine.random.state, s.engine.random48.state
        s.advance()
        self.assertEqual(s.engine.panel, PanelState())
        self.assertIsNone(s.engine.loading)
        self.assertIsNone(s.engine.scene_badge)
        self.assertEqual((s.engine.notice, s.engine.next_dialogue_notice, s.engine.last_input), ('', '', ''))
        self.assertEqual((s.engine.notice_ms, s.engine.scene_value), (0, 0))
        self.assertEqual((s.engine.random.state, s.engine.random48.state), random)
        self.assertEqual((s.engine.music_id, s.engine.sound_id, s.engine.sound_serial), (8201, 8010, 3))
        self.assertIs(s.tick(4000), s.pending)  # No surviving loading gate can resume the VM.

    def test_old_unsupported_saves_upgrade_only_the_final_call(self):
        for service in (7, 63):
            s = Session(Resources(exit_program(service, (101, 103, 1))))
            while (request := s.vm.run()).yield_id != service:
                s.engine.dispatch(s.vm)
            s.pending = EngineAction('unhandled_yield', request, False)
            s.engine.numbers[44] = 51
            saved = json.loads(json.dumps(s.snapshot()))
            saved['version'] = 11
            before = copy.deepcopy(saved)
            restored = Session.from_snapshot(s.resources, saved)
            self.assertEqual(saved, before)
            self.assertTrue(restored.episode_exited)
            self.assertEqual(restored.vm.snapshot(), s.vm.snapshot())
            self.assertEqual(restored.engine.scheduled_scripts, [])
            self.assertEqual(restored.engine.numbers, {})
            self.assertEqual(Session.from_snapshot(s.resources, restored.snapshot()).snapshot(), restored.snapshot())

    def test_invalid_terminal_checkpoints_and_unrelated_services_are_rejected(self):
        s = Session(Resources(exit_program(63, (1, 2, 3))))
        s.advance()
        for key, value in (('scheduled_scripts', [(25002, False)]), ('numbers', {5: 7}),
                           ('scene_value', 20), ('last_input', 'Not cleared')):
            saved = s.snapshot()
            saved['engine'][key] = value
            with self.subTest(key=key), self.assertRaises(SaveError):
                Session.from_snapshot(s.resources, saved)
        for mutate in (lambda saved: saved.update(version=11),
                       lambda saved: saved['pending'].update(details={'result': 0}),
                       lambda saved: saved.update(remaining_ms=1000),
                       lambda saved: saved['vm']['pending'].update(args=[])):
            saved = s.snapshot()
            mutate(saved)
            with self.assertRaises(SaveError):
                Session.from_snapshot(s.resources, saved)
        unknown = Session(Resources(program(*host_call(254, 7))))
        self.assertEqual(unknown.advance().name, 'unhandled_yield')
        saved = unknown.snapshot()
        saved['pending']['name'] = 'episode_exit'
        with self.assertRaises(SaveError):
            Session.from_snapshot(unknown.resources, saved)

    def test_headless_trace_reports_episode_exit_without_loading_another_scene(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'authored.exp'
            path.write_bytes(archive({1: metadata(), 25001: exit_program(63).to_bytes()}))
            result = trace_archive(path, max_events=2)
        self.assertEqual(result['status'], 'episode_exit')
        self.assertIsNone(result['error'])
        self.assertEqual([e['name'] for e in result['events']], ['schedule_script', 'episode_exit'])
        self.assertEqual(result['state']['scheduled_scripts'], [])

    @unittest.skipUnless(Path('.shs-library/library.json').is_file(), 'player content is absent')
    def test_original_football_end_message_reaches_reported_service(self):
        with ContentLibrary(Path('.shs-library')) as library:
            s = Session(library.open_episode('Football Star'))
            # Execute the original caller and helper, starting at the branch
            # reached by service 70(10). No original script/text is bundled.
            s.vm.pc = 234
            self.assertEqual(s.advance().name, 'message_panel')
            self.assertEqual(s.pending.request.pc, 126)
            s.tick(1000)
            action = s.answer()
            self.assertEqual((action.name, action.request.pc, action.request.yield_id), ('episode_exit', 130, 7))
            self.assertEqual(action.request.args, (490, 494, 1))
            self.assertNotIn(131, s.vm.recent_pcs)
            self.assertEqual(Session.from_snapshot(s.resources, s.snapshot()).snapshot(), s.snapshot())


class EpisodeExitMenuTests(unittest.TestCase):
    ENDING = (0x32, *host_call(7, 12, 13, 1), 0x33)
    SCHEDULED = {}

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        profile = patch('exp_runtime.shs.content.NATIVE_SHA256', digest(FAKE_NATIVE))
        profile.start()
        self.addCleanup(profile.stop)
        apk = self.root / 'authored.apk'
        make_apk(apk, archive({1: metadata(), 25001: program(*self.ENDING).to_bytes(),
                                **{key: program(*code).to_bytes() for key, code in self.SCHEDULED.items()}}))
        import_game(apk, [], self.root / 'library')
        self.library = ContentLibrary(self.root / 'library')
        self.addCleanup(self.library.close)

    def test_terminal_checkpoint_masks_older_progress_preserves_manual_and_allows_new_game(self):
        state = MenuState(self.library)
        episode = state.selected
        other = self.root / 'other.exp'
        other.write_bytes(archive({1: metadata('Another story'), 25001: program(0x32, 0x33).to_bytes()}))
        self.library.add_episodes([other])
        other_session = state.session('Another story')
        other_session.advance()
        other_path = state.checkpoint(other_session)
        other_bytes = other_path.read_bytes()
        state.selected = episode
        s = state.session(state.selected)
        s.advance()
        manual = s.save()
        before = manual.read_bytes()
        state.checkpoint(s)
        self.assertIsNotNone(state.resume_path(state.selected))
        s.answer()
        state.checkpoint(s)
        os.utime(manual, ns=(1, 1))
        self.assertIsNone(state.resume_path(state.selected))
        reopened = MenuState(self.library)
        self.assertIsNone(reopened.resume_path(state.selected))
        self.assertEqual(manual.read_bytes(), before)
        self.assertEqual(other_path.read_bytes(), other_bytes)
        self.assertEqual(reopened.resume_path('Another story'), other_path)
        self.assertEqual(Session.load(s.resources, manual).pending.name, 'vm_pause')
        fresh = reopened.session(state.selected)
        self.assertIsNone(fresh.pending)
        self.assertEqual(fresh.vm.pc, 0)
        fresh.advance()
        reopened.checkpoint(fresh)
        self.assertIsNotNone(reopened.resume_path(state.selected))
        self.assertEqual(reopened.session(state.selected).snapshot(), fresh.snapshot())
        self.assertEqual(manual.read_bytes(), before)

    def test_corrupt_completion_marker_stays_visible_and_reports_load_error(self):
        state = MenuState(self.library)
        s = state.session(state.selected)
        s.advance()
        s.answer()
        path = state.checkpoint(s)
        saved = json.loads(path.read_text())
        saved['engine']['scheduled_scripts'] = [[25002, False]]
        path.write_text(json.dumps(saved))
        self.assertEqual(state.resume_path(state.selected), path)
        with self.assertRaises(SaveError):
            state.session(state.selected)

    def make_app(self):
        from exp_runtime.application import Application
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        app = Application(self.root / 'empty', audio=False, check_updates=False)
        self.addCleanup(app.close)
        # The lifecycle needs no original menu art. Use the setup renderer's
        # canvas with the authored content library and real Desktop/Session.
        app.library, app.directory = self.library, self.library.directory
        app.state = MenuState(self.library)
        app.selected = app.state.selected
        return app

    @unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
    def test_desktop_returns_to_menu_and_new_play_starts_at_the_beginning(self):
        app = self.make_app()
        app.start(resume=False)
        self.assertEqual(app.screen, 'game')
        self.assertEqual(app.game.session.pending.name, 'vm_pause')
        app.tick(16)
        self.assertEqual(app.screen, 'main')
        self.assertIsNone(app.game)
        self.assertFalse(app.can_resume())
        self.assertEqual(app.message, '')
        app.start()
        self.assertEqual(app.screen, 'game')
        self.assertEqual(app.game.session.pending.name, 'vm_pause')

    @unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
    def test_loading_old_unsupported_exit_returns_to_menu_before_rendering(self):
        app = self.make_app()
        s = app.state.session(app.selected)
        s.vm.run()
        s.vm.continue_after_pause()
        request = s.vm.run()
        s.pending = EngineAction('unhandled_yield', request, False)
        s.engine.music_id = 8201
        app.state.checkpoint(s)
        with patch('exp_runtime.desktop.Desktop._sync_music') as music:
            app.start()
            music.assert_not_called()  # Loading a terminal save must not restart its old cue.
        self.assertEqual(app.screen, 'main')
        self.assertIsNone(app.game)
        self.assertFalse(app.can_resume())
        self.assertEqual(app.message, '')

    @unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
    def test_a_save_that_cannot_be_loaded_is_set_aside_with_the_apps_message_and_the_menu_stays(self):
        app = self.make_app()
        session = app.state.session(app.selected)
        session.advance()
        path = app.state.checkpoint(session)
        saved = json.loads(path.read_text())
        saved['scene'] = 65000                                           # a save whose script is not the episode's
        path.write_text(json.dumps(saved))
        app.start()
        self.assertNotEqual(app.screen, 'game')                          # `onTick`: back at the menu, not in the game
        self.assertIsNone(app.game)
        self.assertIn('Save file was corrupt', app.message)
        self.assertFalse(path.exists())                                  # deleted in the app; kept aside here
        self.assertTrue(path.with_name(path.name + '.corrupt').exists())
        self.assertFalse(app.can_resume())

    @unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
    def test_exit_from_input_hands_off_before_drawing_and_stops_audio(self):
        app = self.make_app()
        app.start(resume=False)
        game = app.game
        game.session.answer()
        app.audio = True
        with patch.object(game, 'render') as game_draw, \
                patch.object(app.renderer, 'draw', return_value=app.renderer.canvas), \
                patch('pygame.mixer.music') as music, patch('pygame.mixer.stop') as sounds:
            app.render()
            game_draw.assert_not_called()
            music.stop.assert_called_once_with()
            sounds.assert_called_once_with()
        self.assertEqual(app.screen, 'main')
        self.assertIsNone(app.game)
        self.assertFalse(app.can_resume())

    @unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
    def test_exit_keeps_the_click_of_the_tap_that_ended_the_episode(self):
        # Owner's report: CoD's message-panel Continue click was cut off by the exit's own sound stop.
        from types import SimpleNamespace
        app = self.make_app()
        app.start(resume=False)
        game = app.game
        game.session.answer()
        app.audio = True
        click, story = object(), object()
        busy = SimpleNamespace(get_busy=lambda: True, get_sound=lambda: click)
        game.ui_sounds.channels = [busy]
        channels = [SimpleNamespace(get_sound=lambda: click, stop=Mock()),
                    SimpleNamespace(get_sound=lambda: story, stop=Mock())]
        with patch.object(game, 'render'), patch.object(app.renderer, 'draw', return_value=app.renderer.canvas), \
                patch('pygame.mixer.music'), patch('pygame.mixer.stop') as everything, \
                patch('pygame.mixer.get_num_channels', return_value=2), \
                patch('pygame.mixer.Channel', side_effect=lambda index: channels[index]):
            app.render()
            everything.assert_not_called()
        channels[0].stop.assert_not_called()
        channels[1].stop.assert_called_once_with()
        self.assertEqual(app.screen, 'main')

    @unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
    def test_failed_completion_checkpoint_keeps_terminal_session_for_retry(self):
        app = self.make_app()
        app.start(resume=False)
        game = app.game
        with patch.object(app.state, 'checkpoint', side_effect=OSError('Authored write failure')), \
                self.assertLogs(level='WARNING'):
            app.tick(16)
        self.assertEqual(app.screen, 'main')
        self.assertIs(app.game, game)
        self.assertTrue(game.session.episode_ended)
        self.assertIn('Authored write failure', app.message)
        held = game.session.snapshot()
        app.message = ''
        app.start()  # Retry checkpointing the retained exit; never rerun the VM.
        self.assertEqual(game.session.snapshot(), held)
        self.assertEqual(app.screen, 'main')
        self.assertIsNone(app.game)
        self.assertFalse(app.can_resume())


class HaltEndingMenuTests(EpisodeExitMenuTests):
    """A branch that returns to its script's top-level HALT with nothing scheduled (CoD's "Your Case: The Missing
    Child" "Try again" ending) ends the episode like service 7, rather than leaving a blank scene with music playing."""
    ENDING = (0x32, *host_call(10, 25002, 0), 0x33)
    SCHEDULED = {25002: (0x33,)}
    # Service 7's own save validation and old-save upgrade; a HALT has neither.
    test_corrupt_completion_marker_stays_visible_and_reports_load_error = None
    test_loading_old_unsupported_exit_returns_to_menu_before_rendering = None

    def test_halt_is_an_ended_episode_but_not_a_service_exit(self):
        s = MenuState(self.library).session(self.library.episodes[0]['id'])
        s.advance()
        self.assertFalse(s.episode_ended)
        self.assertEqual(s.answer().name, 'finished')
        self.assertEqual((s.scene, s.scene_loads), (25002, 1))
        self.assertTrue(s.episode_ended)
        self.assertFalse(s.episode_exited)

    def test_a_first_script_that_halts_stays_resumable(self):
        s = Session(Resources(program(0x33)))
        self.assertEqual(s.advance().name, 'finished')
        self.assertFalse(s.episode_ended)


if __name__ == '__main__':
    unittest.main()
