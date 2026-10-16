"""Music routing uses native cues without aliasing the resource namespaces."""
import importlib.util
from io import BytesIO
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import wave

from exp_runtime.audio import MusicCue, music_cue
from exp_runtime.content import ContentError
from exp_runtime.runtime import SaveError, Session
from test_runtime import Resources, host_call
from test_vm import program


class MusicCueTests(unittest.TestCase):
    def test_stat_notices_use_explicit_script_sounds_and_do_not_invent_a_cue(self):
        from test_runtime import text_words
        for game, cue in (('shs', 8007), ('cod', 8002)):
            for explicit in (False, True):
                with self.subTest(game=game, explicit=explicit):
                    words, refs = text_words('Stat Up', 'Well done.')
                    calls = host_call(79, cue) if explicit else []
                    resources = Resources(program(*calls, *host_call(44, 3017, 1),
                                                  *host_call(88, refs[0]), *host_call(13, refs[1], 0),
                                                  0x33, words=words))
                    resources.library.game_id = game
                    session = Session(resources)
                    self.assertEqual(session.advance().name, 'dialogue')
                    self.assertEqual(session.engine.notice, 'Stat Up')
                    self.assertEqual(session.engine.numbers[3017], 1)
                    self.assertEqual(session.engine.sound_ids, [cue] if explicit else [])
                    self.assertEqual(session.engine.sound_serial, int(explicit))
                    restored = Session.from_snapshot(resources, session.snapshot())
                    restored.tick(500)
                    self.assertEqual(restored.engine.sound_serial, int(explicit))

    def test_choice_click_precedes_all_script_cues_and_timeout_is_silent(self):
        from test_runtime import text_words
        for game, click in (('shs', 8010), ('cod', 8005)):
            with self.subTest(game=game):
                words, refs = text_words('Choose', 'One|Two', 'Prompt', 'Continue')
                resources = Resources(program(*host_call(1, *refs[:3], 1000, 0, -1, -1, 1),
                                              *host_call(79, 28001), *host_call(79, 28002),
                                              *host_call(13, refs[3], 0), 0x33, words=words))
                resources.library.game_id = game
                session = Session(resources); session.advance()
                saved = session.snapshot()
                with self.assertRaises(ValueError):
                    session.answer(2)
                self.assertEqual(session.snapshot(), saved)
                session.tick(250)
                self.assertEqual(session.answer(0).name, 'dialogue')
                self.assertEqual(session.engine.sound_ids, [click, 28001, 28002])
                self.assertEqual(session.engine.sound_serial, 3)
                session.tick(10)
                self.assertEqual(session.engine.sound_ids, [click, 28001, 28002])
                restored = Session.from_snapshot(resources, saved)
                restored.tick(1001)
                self.assertEqual(restored.engine.sound_ids, [28001, 28002])
                self.assertEqual(restored.engine.sound_serial, 2)

    def test_word_choices_use_each_games_native_cues_and_ignore_early_taps(self):
        from test_minigames import word_resources
        for game, positive, negative in (('shs', 8001, 8002), ('cod', 8003, 8004)):
            with self.subTest(game=game):
                resources = word_resources(); resources.library.game_id = game
                session = Session(resources); session.advance()
                session.answer(0)
                self.assertEqual(session.engine.sound_serial, 0)
                session.tick(400)
                for weight, cue in ((1, positive), (-1, negative)):
                    session.answer(session.engine.word_game.weights.index(weight))
                    self.assertEqual(session.engine.sound_ids, [cue])
                saved = session.snapshot()
                restored = Session.from_snapshot(resources, saved)
                restored.tick(1)
                self.assertEqual(restored.engine.sound_serial, 2)

    def test_native_stop_duration_request_serial_and_save_validation(self):
        for game in ('shs', 'cod'):
            for duration in (-5, -1, 0, 600, 32767):
                with self.subTest(game=game, duration=duration):
                    r = Resources(program(*host_call(80, 8201, 1), *host_call(80, 8201, 1),
                                          *host_call(81, duration), 0x33))
                    r.library.game_id = game
                    session = Session(r); session.advance()
                    engine = session.engine
                    expected = max(0, 1000 if duration == -1 else duration) if game == 'cod' else 0
                    self.assertEqual((engine.music_id, engine.music_serial, engine.music_stop_ms), (-1, 3, expected))
                    self.assertEqual(Session.from_snapshot(r, session.snapshot()).snapshot(), session.snapshot())
                    for field, value in (('music_serial', -1), ('music_stop_ms', -1), ('music_stop_ms', 32768)):
                        state = session.snapshot()
                        state['engine'][field] = value
                        with self.assertRaises(SaveError):
                            Session.from_snapshot(r, state)

    def test_shared_track_cues_and_unmapped_resources(self):
        self.assertEqual(music_cue(8213), MusicCue(8212, 4000))
        self.assertEqual(music_cue(8214), MusicCue(8212, 39200))
        for resource_id in (16, 8002, 8201, 8203, 8222, 8232, 26002, 28202):
            with self.subTest(resource_id=resource_id):
                self.assertEqual(music_cue(resource_id), MusicCue(resource_id, 0))


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class MusicPlaybackTests(unittest.TestCase):
    def test_loading_saved_effects_waits_for_menu_without_overwriting_the_save(self):
        from exp_runtime.platforms.drawing import Mixer
        from exp_runtime.music_state import MusicPlayback, SoundPlayback
        ui, resources = self.make_ui(music=8201, repeat=1, game='cod')
        resources.library.kind = 'ipa'
        ui.session.engine.music_playback = MusicPlayback(8201, True, 14987)
        ui.session.engine.sound_playback = [SoundPlayback(28001, 1723)]
        ui.session = Session.from_snapshot(resources, ui.session.snapshot())
        before = ui.session.snapshot()
        mixer = Mixer()
        with patch('pygame.mixer.music', mixer.music), patch('exp_runtime.graphics.play_sound', mixer.play_sound):
            ui.audio_wait = True
            ui._sync_audio(); ui.capture_audio(); ui.tick(999)
            self.assertEqual(ui.session.snapshot(), before)
            self.assertFalse(any(c['kind'] == 'music_play' for c in mixer.commands))
            ui.audio_wait = False
            ui._sync_audio()
            self.assertIn(dict(kind='music_play', start=14.987, loops=-1), mixer.commands)
            self.assertIn(dict(kind='music_play', track='effect:1', start=1.723, loops=0), mixer.commands)

    def test_ipa_pause_fades_and_restores_music_and_effects_from_saved_playheads(self):
        from exp_runtime.platforms.drawing import Mixer
        from exp_runtime.music_state import SoundPlayback
        for game in ('shs', 'cod'):
            with self.subTest(game=game):
                ui, resources = self.make_ui(music=8201, repeat=1, game=game)
                resources.library.kind = 'ipa'
                mixer = Mixer()
                with patch('pygame.mixer.music', mixer.music), patch('exp_runtime.graphics.play_sound', mixer.play_sound):
                    ui._sync_audio()
                    ui.session.engine.sound_ids = [8001, 28001]
                    ui.session.engine.sound_serial += 1
                    ui._sync_audio()
                    mixer.positions.update(music=4321, **{'effect:1': 71, 'effect:2': 132})
                    ui.menu_open = True
                    ui._sync_audio()
                    saved = ui.session.snapshot()
                    self.assertEqual(saved['engine']['music_playback']['position_ms'], 4000)
                    self.assertEqual(ui.session.engine.sound_playback, [SoundPlayback(8001, 0), SoundPlayback(28001, 0)])
                    self.assertEqual(Session.from_snapshot(resources, saved).snapshot(), saved)
                    ui.tick(50)
                    self.assertIn(dict(kind='music_volume', volume=.95), mixer.commands)
                    self.assertIn(dict(kind='music_volume', track='effect:1', volume=.5), mixer.commands)
                    ui.tick(50)
                    self.assertFalse(mixer.playing.get('effect:1'))
                    self.assertTrue(mixer.playing['music'])
                    ui.active = False
                    ui._sync_audio(); ui.tick(5000)
                    self.assertEqual(ui.music_fade_ms, 900)
                    ui.active = True
                    ui._sync_audio(); ui.tick(900)
                    self.assertFalse(mixer.playing.get('music'))
                    ui.capture_audio()
                    self.assertEqual(ui.session.snapshot(), saved)  # Do not save the outgoing fade instead.
                    ui.menu_open = False
                    mixer.commands.clear()
                    ui._sync_audio()
                    self.assertIn(dict(kind='music_play', start=4., loops=-1), mixer.commands)
                    self.assertIn(dict(kind='music_play', track='effect:3', start=0., loops=0), mixer.commands)
                    self.assertIn(dict(kind='music_play', track='effect:4', start=0., loops=0), mixer.commands)
                    self.assertFalse(ui.audio_stored)
                    self.assertEqual(ui.session.snapshot(), saved)
                    invalid = ui.session.snapshot()
                    invalid['engine']['sound_playback'][0]['position_ms'] = -1
                    with self.assertRaises(SaveError):
                        Session.from_snapshot(resources, invalid)

    def test_ipa_main_menu_waits_for_story_and_menu_fades_before_restoring(self):
        from exp_runtime.application import Application
        from exp_runtime.platforms.drawing import Mixer
        for game in ('shs', 'cod'):
            with self.subTest(game=game):
                ui, resources = self.make_ui(music=8201, repeat=1, game=game)
                resources.library.kind = 'ipa'
                resources.record['id'] = 'authored-episode'
                app = Application(audio=False, game_key=game, directory=Path('/no-authored-library'), check_updates=False)
                self.addCleanup(app.close)
                app.library, app.selected, app.game = resources.library, resources.record['id'], ui
                resources.library.read_asset = resources.read_asset
                resources.library.close = Mock()
                app.state = Mock(music=True, sound=True)
                app.state.title.return_value = 'Authored'
                app.screen = 'game'
                app.audio = True
                app.refresh_saves = Mock()
                app.show = Mock(side_effect=lambda screen, **_: setattr(app, 'screen', screen))
                mixer = Mixer()
                app.menu_music = mixer.menu_music
                with patch('pygame.mixer.music', mixer.music), patch('pygame.mixer.stop'), \
                        patch('exp_runtime.graphics.play_sound', mixer.play_sound):
                    ui._sync_audio()
                    mixer.positions['music'] = 4321
                    app.return_to_menu()
                    app._sync_menu_music()
                    self.assertFalse(app.menu_music_loaded)
                    app._tick_menu_audio(999)
                    self.assertFalse(app.menu_music_loaded)
                    app._tick_menu_audio(1)
                    self.assertTrue(app.menu_music_loaded)
                    app.start()
                    self.assertEqual(app.menu_music_fade_ms, 1000)
                    self.assertTrue(ui.audio_stored)
                    mixer.commands.clear()
                    app._tick_menu_audio(999); ui._sync_audio()
                    self.assertFalse(any(c['kind'] == 'music_play' for c in mixer.commands))
                    app._tick_menu_audio(1); ui._sync_audio()
                    self.assertIn(dict(kind='music_play', start=4., loops=-1), mixer.commands)
                    self.assertFalse(app.menu_music_loaded)
                    self.assertFalse(ui.audio_stored)
                app.audio = False
                app.game = app.state = app.library = None

    def test_decoded_effect_seek_preserves_sample_boundaries_and_paused_clock(self):
        import pygame
        from exp_runtime.platforms.sdl_audio import Sound
        self.make_ui()
        pygame.mixer.init(frequency=8000, size=-16, channels=1, buffer=128)
        sample = BytesIO()
        pcm = b'\x10\x00' * 800 + b'\x20\x00' * 8000
        with wave.open(sample, 'wb') as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(8000)
            stream.writeframes(pcm)
        player = Sound(BytesIO(sample.getvalue()), 100)
        self.assertTrue(player.get_busy())
        self.assertEqual(player.sound.get_raw(), pcm[1600:])
        player.pause()
        position = player.position_ms()
        pygame.time.wait(30)
        self.assertEqual(player.position_ms(), position)
        player.unpause()
        player.stop()
        self.assertFalse(player.get_busy())
        self.assertFalse(Sound(BytesIO(sample.getvalue()), 2000).get_busy())

    def test_ios_background_checkpoint_captures_playhead_without_advancing_story(self):
        from types import SimpleNamespace
        import pygame
        from exp_runtime.platforms.ios import Host
        ui, _ = self.make_ui(music=8201, repeat=1, game='cod')
        host = Host.__new__(Host)
        host.last_active = True
        host.backend = SimpleNamespace(WINDOWFOCUSGAINED=pygame.WINDOWFOCUSGAINED,
                                       WINDOWFOCUSLOST=pygame.WINDOWFOCUSLOST, mixer=Mock())
        checkpoints = []
        host.app = SimpleNamespace(game=ui, handle_event=ui.handle_event,
                                   _attempt=lambda operation: operation(),
                                   state=SimpleNamespace(checkpoint=lambda session: checkpoints.append(session.snapshot())))
        with patch('pygame.mixer.music') as music, patch('exp_runtime.graphics.music_position', return_value=4321):
            music.get_busy.return_value = True
            ui._sync_audio()
            before = ui.session.snapshot()
            host.active(False)
            host.active(False)  # Duplicate lifecycle notifications must not overwrite it.
            self.assertEqual(len(checkpoints), 1)
            playback = checkpoints[0]['engine']['music_playback']
            self.assertEqual(playback['position_ms'], 4321)
            self.assertTrue(playback['repeat'])
            self.assertFalse(playback['finished'])
            before['engine']['music_playback'] = playback
            self.assertEqual(checkpoints[0], before)
            music.pause.assert_called_once()
            host.active(True)
            music.unpause.assert_called_once()
            self.assertEqual(len(checkpoints), 1)

    def test_save_restores_actual_outgoing_playhead_fade_and_queued_cue(self):
        from exp_runtime.music_state import MusicPlayback
        ui, resources = self.make_ui(music=8201, repeat=1, game='cod')
        with patch('pygame.mixer.music') as music, patch('exp_runtime.graphics.music_position', return_value=4237):
            music.get_busy.return_value = True
            ui._sync_audio()
            ui.session.engine.music_id = 8202
            ui._sync_audio(); ui._tick_music(350)
            ui.capture_audio()
            self.assertEqual(ui.session.engine.music_playback, MusicPlayback(8201, 1, 4237, 650, 1000, False))
            saved = ui.session.snapshot()
            ui.session = Session.from_snapshot(resources, saved)
            ui.music_restore_pending = True
            ui._sync_audio()
            music.play.assert_called_with(loops=-1, start=4.237)
            music.set_volume.assert_called_with(.65)
            ui._tick_music(649)
            self.assertEqual(ui.music_playing, (8201, 1))
            ui._tick_music(1)
            self.assertEqual(ui.music_playing, (8202, 1))
            music.play.assert_called_with(loops=-1, start=0)
            self.assertEqual(resources.read_asset.call_args.args, (8202,))
            for field, value in (('position_ms', -1), ('fade_ms', 1001), ('finished', 1)):
                state = ui.session.snapshot()
                state['engine']['music_playback'][field] = value
                with self.subTest(field=field), self.assertRaises(SaveError):
                    Session.from_snapshot(resources, state)

    def test_finished_save_does_not_restart_and_native_repeat_changes_in_place(self):
        from exp_runtime.platforms.drawing import Mixer
        ui, resources = self.make_ui(music=8201, game='cod')
        mixer = Mixer()
        with patch('pygame.mixer.music', mixer.music):
            ui._sync_audio()
            mixer.commands.clear()
            ui.session.engine.music_flag = True
            ui._sync_audio()
            self.assertEqual(mixer.commands, [dict(kind='music_loops', loops=-1)])
            mixer.playing['music'] = False
            with patch('exp_runtime.graphics.music_position', return_value=10500):
                ui.capture_audio()
            saved = ui.session.snapshot()
            self.assertTrue(saved['engine']['music_playback']['finished'])
            ui.session = Session.from_snapshot(resources, saved)
            ui.music_restore_pending = True
            mixer.commands.clear()
            ui._sync_audio(); ui._sync_audio()
            self.assertEqual(mixer.commands, [dict(kind='music_stop')])

    def test_menu_click_uses_selected_library_and_sound_preference(self):
        from exp_runtime.application import Application
        for game, resource in (('shs', 8010), ('cod', 8005)):
            with self.subTest(game=game):
                app = Application.__new__(Application)
                app.selected_game, app.audio = game, True
                app.library = Mock(read_asset=Mock(return_value=b'authored click'))
                app.state = Mock(sound=False, music=True)
                with patch('pygame.mixer.Sound') as sound:
                    app._click_sound()
                    sound.assert_not_called()
                    app.state.sound, app.state.music = True, False
                    app._click_sound()
                    app._click_sound()
                    app.library.read_asset.assert_called_once_with(resource)
                    self.assertEqual(sound.call_args.kwargs['file'].getvalue(), b'authored click')
                    self.assertEqual(sound.return_value.play.call_count, 2)
                    app.state.sound = False
                    app._click_sound()
                    self.assertEqual(sound.return_value.play.call_count, 2)

    def make_ui(self, service=80, music=8202, repeat=0, game='shs'):
        from exp_runtime.desktop import Desktop
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        self.addCleanup(pygame.quit)
        r = Resources(program(*host_call(service, *([music] if service == 79 else [music, repeat])), 0x33))
        r.library.game_id = game
        r.read_asset = Mock(return_value=b'authored music bytes')
        ui = Desktop(Session(r), audio=False)
        ui.audio = True
        return ui, r

    def test_script_repeat_flag_keeps_real_music_playing_past_the_end(self):
        import pygame
        sample = BytesIO()
        with wave.open(sample, 'wb') as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(8000)
            stream.writeframes(b'\0\0' * 960)  # 120ms, wholly authored.
        for game in ('shs', 'cod'):
            for service, flag in ((79, 0), (80, 0), (80, 1), (80, -3)):
                with self.subTest(game=game, service=service, flag=flag):
                    ui, resources = self.make_ui(service, 8201, flag, game)
                    resources.read_asset.return_value = sample.getvalue()
                    saved = ui.session.snapshot()
                    ui.session = Session.from_snapshot(resources, saved)
                    pygame.mixer.init(frequency=8000, size=-16, channels=1, buffer=128)
                    ui._sync_audio()
                    pygame.time.wait(400)
                    self.assertEqual(pygame.mixer.music.get_busy(), bool(flag))
                    ui.menu_open = True
                    ui._sync_audio()
                    self.assertFalse(pygame.mixer.music.get_busy())
                    ui.menu_open = False
                    ui._sync_audio()
                    self.assertEqual(pygame.mixer.music.get_busy(), bool(flag))
                    self.assertEqual(ui.session.snapshot(), saved)
                    ui.session.engine.music_id = -1
                    ui._sync_audio()
                    self.assertFalse(pygame.mixer.music.get_busy())
                    pygame.mixer.quit()

    def test_script_repeat_flag_reaches_native_music_commands(self):
        from exp_runtime.platforms.drawing import Mixer
        for flag in (0, 1):
            ui, _ = self.make_ui(music=26001, repeat=flag, game='cod')
            mixer = Mixer()
            with patch('pygame.mixer.music', mixer.music):
                ui._sync_audio()
                ui._sync_audio()
                ui.menu_open = True
                ui._sync_audio()
                ui.menu_open = False
                ui._sync_audio()
            self.assertEqual([c['kind'] for c in mixer.commands],
                             ['music_stop', 'music_load', 'music_volume', 'music_play', 'music_pause', 'music_resume'])
            self.assertEqual(mixer.commands[3], dict(kind='music_play', start=0., loops=-1 if flag else 0))

    def test_cod_music_fades_before_starting_the_latest_queued_track(self):
        ui, resources = self.make_ui(music=8201, game='cod')
        with patch('pygame.mixer.music') as music:
            music.get_busy.return_value = True
            ui._sync_audio()
            ui.session.engine.music_id = 8202
            ui._sync_audio()
            ui._tick_music(250)
            music.set_volume.assert_called_with(.75)
            music.play.assert_called_once()
            # A new cue replaces the queue without extending the old fade.
            ui.session.engine.music_id = 8203
            ui._sync_audio()
            ui._tick_music(749)
            music.play.assert_called_once()
            ui._tick_music(1)
            self.assertEqual([c.args for c in resources.read_asset.call_args_list], [(8201,), (8203,)])
            self.assertEqual(music.play.call_count, 2)
            music.set_volume.assert_called_with(1)

    def test_cod_stop_duration_pause_cancel_and_finished_track(self):
        ui, resources = self.make_ui(music=8201, game='cod')
        with patch('pygame.mixer.music') as music:
            music.get_busy.return_value = True
            ui._sync_audio()
            ui.session.engine.music_id, ui.session.engine.music_stop_ms = -1, 600
            ui._sync_audio()
            ui._tick_music(200)
            music.set_volume.assert_called_with(2/3)
            ui.menu_open = True
            ui._sync_audio()
            ui.tick(1000)
            self.assertEqual(ui.music_fade_ms, 400)
            ui.menu_open = False
            ui._sync_audio()
            ui._tick_music(399)
            self.assertEqual(music.stop.call_count, 1)
            ui._tick_music(1)
            self.assertEqual(music.stop.call_count, 2)
            self.assertFalse(ui.music_loaded)
            ui.session.engine.music_id = 8201
            ui._sync_audio()
            ui.session.engine.music_id = 8202
            ui._sync_audio()
            ui._tick_music(250)
            ui.session.engine.music_id = 8201
            ui._sync_audio()
            self.assertEqual(ui.music_fade_ms, 0)
            self.assertEqual(music.play.call_count, 2)  # Existing cue survives.
            music.set_volume.assert_called_with(1)
            # A naturally finished one-shot has nothing left to fade.
            music.get_busy.return_value = False
            ui.session.engine.music_id = 8203
            ui._sync_audio()
            self.assertEqual(music.play.call_count, 3)
            self.assertEqual(ui.music_fade_ms, 0)

    def test_repeated_native_music_requests_do_not_restart_a_live_cue(self):
        ui, _ = self.make_ui(music=8201, game='cod')
        with patch('pygame.mixer.music') as music:
            music.get_busy.return_value = True
            ui._sync_audio()
            ui.session.engine.music_serial += 1
            ui._sync_audio()
            music.play.assert_called_once()
            music.get_busy.return_value = False
            ui.session.engine.music_serial += 1
            ui._sync_audio()
            self.assertEqual(music.play.call_count, 2)

    def test_both_music_services_load_and_seek_without_changing_vm_or_save_ids(self):
        # Expected destinations and offsets recovered from the Java player,
        # including redirects beyond the five IDs in the original report.
        cues = [(8202, 8201, 2.8), (8204, 8203, .72), (8206, 8205, 28.28),
                (8208, 8207, 3.27), (8211, 8210, 6.), (8213, 8212, 4.),
                (8214, 8212, 39.2), (8216, 8215, 1.32), (8218, 8217, 1.92),
                (8220, 8219, 10.6), (8225, 8224, 29.2), (8221, 8221, 0.),
                (26002, 26002, 0.)]
        for service in (79, 80):
            for requested, source, seconds in cues:
                if service == 79 and requested >= 26000:
                    continue  # Service 79 treats episode resources as SFX.
                with self.subTest(service=service, requested=requested):
                    ui, r = self.make_ui(service, requested)
                    saved = ui.session.snapshot()
                    with patch('pygame.mixer.music') as music:
                        ui._sync_audio()
                        music.stop.assert_called_once_with()
                        music.load.assert_called_once()
                        self.assertEqual(music.load.call_args.args[0].getvalue(), b'authored music bytes')
                        music.play.assert_called_once_with(loops=0, start=seconds)
                        r.read_asset.assert_called_once_with(source)
                        self.assertEqual(ui.session.snapshot(), saved)
                        self.assertEqual(ui.session.engine.music_id, requested)
                        ui._sync_audio()  # Rendering another frame must not restart it.
                        music.play.assert_called_once()

    def test_two_cues_in_one_track_restart_and_muting_preserves_the_request(self):
        ui, r = self.make_ui(music=8213)
        with patch('pygame.mixer.music') as music:
            ui._sync_audio()
            ui.session.engine.music_id = 8214
            ui._sync_audio()
            self.assertEqual([call.kwargs['start'] for call in music.play.call_args_list], [4., 39.2])
            self.assertEqual([call.args for call in r.read_asset.call_args_list], [(8212,), (8212,)])
            saved = ui.session.snapshot()
            ui.music_enabled = False
            ui._sync_audio()
            self.assertEqual(music.play.call_count, 2)
            self.assertEqual(music.stop.call_count, 3)
            ui.music_enabled = True
            ui._sync_audio()
            self.assertEqual(music.play.call_args.kwargs, {'loops': 0, 'start': 39.2})
            self.assertEqual(ui.session.snapshot(), saved)

    def test_pause_menu_resumes_the_same_stream_without_reloading_or_replaying_vm(self):
        import pygame
        for controls in ('buttons', 'escape'):
            with self.subTest(controls=controls):
                ui, resources = self.make_ui()
                saved = ui.session.snapshot()
                with patch('pygame.mixer.music') as music:
                    ui._sync_audio()
                    if controls == 'buttons':
                        ui.command(('menu',))
                    else:
                        ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
                    ui._sync_audio()
                    ui.tick(5000)
                    music.pause.assert_called_once_with()
                    music.unpause.assert_not_called()
                    if controls == 'buttons':
                        ui.command(('resume',))
                    else:
                        ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
                    ui._sync_audio()
                    ui._sync_audio()
                    music.unpause.assert_called_once_with()
                    music.load.assert_called_once()
                    music.play.assert_called_once_with(loops=0, start=2.8)
                    resources.read_asset.assert_called_once_with(8201)
                    self.assertEqual(ui.session.snapshot(), saved)

    def test_focus_and_menu_holds_must_both_clear_before_music_resumes(self):
        import pygame
        ui, _ = self.make_ui()
        with patch('pygame.mixer.music') as music:
            ui._sync_audio()
            ui.command(('menu',))
            ui.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST))
            ui.handle_event(pygame.event.Event(pygame.WINDOWFOCUSGAINED))
            ui._sync_audio()
            music.pause.assert_called_once_with()
            music.unpause.assert_not_called()
            ui.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST))
            ui.command(('resume',))
            ui._sync_audio()
            music.unpause.assert_not_called()
            ui.handle_event(pygame.event.Event(pygame.WINDOWFOCUSGAINED))
            ui._sync_audio()
            music.unpause.assert_called_once_with()
            music.play.assert_called_once()

    def test_muting_stopping_and_switching_cues_while_paused_do_not_resume_stale_music(self):
        for change in ('mute', 'stop', 'cue'):
            with self.subTest(change=change):
                ui, _ = self.make_ui(music=8213)
                with patch('pygame.mixer.music') as music:
                    ui._sync_audio()
                    ui.command(('menu',))
                    ui._sync_audio()
                    if change == 'mute':
                        ui.music_enabled = False
                    else:
                        ui.session.engine.music_id = -1 if change == 'stop' else 8214
                    ui._sync_audio()
                    ui.command(('resume',))
                    ui._sync_audio()
                    if change == 'cue':
                        self.assertEqual([call.kwargs['start'] for call in music.play.call_args_list],
                                         [4., 39.2])
                        self.assertEqual(music.pause.call_count, 2)
                        music.unpause.assert_called_once_with()
                    else:
                        music.play.assert_called_once_with(loops=0, start=4.)
                        music.unpause.assert_not_called()

    def test_live_main_menu_resume_keeps_the_stream_and_restart_loads_a_new_one(self):
        from exp_runtime.application import Application
        ui, resources = self.make_ui()
        resources.record['id'] = 'authored-episode'
        # Exercise application lifecycle without original menu art or writes.
        app = Application.__new__(Application)
        app.selected_game = 'shs'
        app.game, app.selected, app.audio, app.active = ui, resources.record['id'], True, True
        app.window = ui.window
        app.library = resources
        app.menu_music = Mock()
        app.menu_music_token = None
        app.menu_music_loaded = app.menu_music_paused = False
        app.menu_music_fade_ms = 0
        app.game_entry = None
        app.state = Mock(music=True, sound=True)
        app.state.title.return_value = resources.record['titles'][0]
        app.show = Mock(side_effect=lambda screen, **_: setattr(app, 'screen', screen))
        app.refresh_saves = Mock()
        saved = ui.session.snapshot()
        with patch('pygame.mixer.music') as music, patch('pygame.mixer.stop'), \
                patch('exp_runtime.graphics.music_position', return_value=2871):
            ui._sync_audio()
            app.return_to_menu()
            app._sync_menu_music()
            app.menu_music.play.assert_called_once_with()
            music.pause.assert_called_once_with()
            app.start()
            ui._sync_audio()
            self.assertIs(app.game, ui)
            music.unpause.assert_called_once_with()
            music.load.assert_called_once()
            music.play.assert_called_once_with(loops=0, start=2.8)
            playback = ui.session.snapshot()['engine']['music_playback']
            self.assertEqual((playback['asset'], playback['repeat']), (8202, False))
            saved['engine']['music_playback'] = playback
            self.assertEqual(ui.session.snapshot(), saved)
            app.return_to_menu()
            app.state.session.return_value = Session(resources)
            app.start(resume=False)
            app.game._sync_audio()
            self.assertIsNot(app.game, ui)
            self.assertEqual(music.load.call_count, 2)
            self.assertEqual(music.play.call_count, 2)

    def test_menu_uses_each_games_theme_and_obeys_mute_focus_and_game_changes(self):
        from exp_runtime.application import Application
        for game, resource in (('shs', 8215), ('cod', 8209)):
            with self.subTest(game=game):
                app = Application(audio=False, game_key=game, directory=Path('/no-authored-library'), check_updates=False)
                self.addCleanup(app.close)
                import pygame
                pygame.mixer.init()
                app.audio = True
                app.library = Mock(read_asset=Mock(return_value=b'authored theme'))
                app.state = Mock(music=True)
                app.menu_music = Mock()
                app.screen = 'main'
                app._sync_menu_music()
                app._sync_menu_music()
                app.library.read_asset.assert_called_once_with(resource)
                app.menu_music.play.assert_called_once_with()
                self.assertEqual(app.menu_music.load.call_args.args[0].getvalue(), b'authored theme')
                app.active = False
                app._sync_menu_music()
                app.menu_music.pause.assert_called_once_with()
                app.active = True
                app._sync_menu_music()
                app.menu_music.unpause.assert_called_once_with()
                app.state.music = False
                app._sync_menu_music()
                self.assertFalse(app.menu_music_loaded)
                app.state.music = True
                app._sync_menu_music()
                self.assertEqual(app.menu_music.play.call_count, 2)
                app.screen = 'game'
                app._sync_menu_music()
                self.assertFalse(app.menu_music_loaded)
                app.screen = 'main'
                app._sync_menu_music()
                self.assertEqual(app.menu_music.play.call_count, 3)
                app.release_library()
                self.assertFalse(app.menu_music_loaded)
                app.audio = False

    def test_real_menu_channel_leaves_paused_story_stream_intact(self):
        from exp_runtime.graphics import create_menu_music
        import pygame
        ui, resources = self.make_ui(music=8201)
        sample = BytesIO()
        with wave.open(sample, 'wb') as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(8000)
            stream.writeframes(b'\0\0' * 16000)
        resources.read_asset.return_value = sample.getvalue()
        pygame.mixer.init(frequency=8000, size=-16, channels=1, buffer=128)
        ui._sync_audio()
        ui.command(('menu',))
        position = pygame.mixer.music.get_pos()
        menu = create_menu_music()
        menu.load(BytesIO(sample.getvalue()))
        menu.play()
        self.assertTrue(menu.channel.get_busy())
        self.assertFalse(pygame.mixer.music.get_busy())
        pygame.time.wait(50)
        self.assertEqual(pygame.mixer.music.get_pos(), position)
        menu.pause()
        menu.unpause()
        menu.stop()
        ui.command(('resume',))
        self.assertTrue(pygame.mixer.music.get_busy())
        resources.read_asset.assert_called_once_with(8201)

    def test_real_mixer_freezes_and_resumes_authored_music_position(self):
        import pygame
        ui, resources = self.make_ui(music=8201)
        sample = BytesIO()
        with wave.open(sample, 'wb') as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(8000)
            stream.writeframes(b'\0\0' * 16000)
        resources.read_asset.return_value = sample.getvalue()
        pygame.mixer.init(frequency=8000, size=-16, channels=1, buffer=128)
        ui._sync_audio()
        self.assertTrue(pygame.mixer.music.get_busy())
        pygame.time.wait(50)
        ui.command(('menu',))
        ui._sync_audio()
        self.assertFalse(pygame.mixer.music.get_busy())
        position = pygame.mixer.music.get_pos()
        pygame.time.wait(80)
        self.assertEqual(pygame.mixer.music.get_pos(), position)
        ui.command(('resume',))
        ui._sync_audio()
        self.assertTrue(pygame.mixer.music.get_busy())
        pygame.time.wait(50)
        self.assertGreater(pygame.mixer.music.get_pos(), position)
        resources.read_asset.assert_called_once_with(8201)
        pygame.mixer.music.stop()  # A finished/stopped stream must not be restarted by Resume.
        ui.command(('menu',))
        ui.command(('resume',))
        ui._sync_audio()
        self.assertFalse(pygame.mixer.music.get_busy())

    def test_unknown_missing_music_warns_and_sound_effect_ids_stay_exact(self):
        ui, r = self.make_ui(music=8222)
        r.read_asset.side_effect = ContentError('APK resource 8222 is missing')
        with patch('pygame.mixer.music') as music, self.assertLogs(level='WARNING') as logs:
            ui._sync_audio()
            ui._sync_audio()
            ui.command(('menu',))
            ui.command(('resume',))
            music.play.assert_not_called()
            music.unpause.assert_not_called()
            r.read_asset.assert_called_once_with(8222)
        self.assertEqual(len(logs.output), 1)
        self.assertIn('Music 8222 cannot be played', logs.output[0])
        r.read_asset.reset_mock(); r.read_asset.side_effect = None
        # The episode SFX bank must never acquire music-cue redirects.
        ui.session.engine.sound_id = 28202
        ui.session.engine.sound_ids = [28202]
        ui.session.engine.sound_serial += 1
        with patch('exp_runtime.graphics.play_sound') as sound:
            ui._sync_audio()
            r.read_asset.assert_called_once_with(28202)
            sound.assert_called_once()
            self.assertEqual(sound.call_args.args[1], 0)

    @unittest.skipUnless(Path('.shs-library/library.json').is_file(), 'user library is not present')
    def test_original_apk_contains_and_plays_every_redirected_track(self):
        import pygame
        from exp_runtime.content import ContentLibrary
        ui, _ = self.make_ui()
        pygame.mixer.init()
        with ContentLibrary(Path('.shs-library')) as lib:
            ui.session.resources = lib.open_episode('Football Star')
            for requested in (8202, 8204, 8206, 8208, 8211, 8213, 8214, 8216, 8218, 8220, 8225):
                with self.subTest(requested=requested), self.assertNoLogs(level='WARNING'):
                    cue = music_cue(requested)
                    # The APK has no standalone alias file. Keep generic
                    # resource reads exact even after implementing playback.
                    with self.assertRaises(ContentError):
                        lib.read_asset(requested)
                    self.assertIn(cue.asset_id, lib.base_members)
                    ui.session.engine.music_id = requested
                    ui._sync_audio()
                    self.assertTrue(pygame.mixer.music.get_busy())
            pygame.mixer.music.stop()
