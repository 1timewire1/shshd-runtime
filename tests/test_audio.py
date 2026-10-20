"""Music routing uses native cues without aliasing the resource namespaces."""
import importlib.util
from io import BytesIO
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import wave

from exp_runtime.audio import MusicCue, music_cue
from exp_runtime.content import ContentError
from exp_runtime.runtime import Session
from test_runtime import Resources, host_call
from test_vm import program


class MusicCueTests(unittest.TestCase):
    def test_shared_track_cues_and_unmapped_resources(self):
        self.assertEqual(music_cue(8213), MusicCue(8212, 4000))
        self.assertEqual(music_cue(8214), MusicCue(8212, 39200))
        for resource_id in (16, 8002, 8201, 8203, 8222, 8232, 26002, 28202):
            with self.subTest(resource_id=resource_id):
                self.assertEqual(music_cue(resource_id), MusicCue(resource_id, 0))


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class MusicPlaybackTests(unittest.TestCase):
    def test_menu_click_uses_selected_library_and_sound_preference(self):
        from exp_runtime.application import Application
        for game, resource in (('shs', 8010), ('cod', 8005)):
            with self.subTest(game=game):
                app = Application.__new__(Application)
                app.selected_game, app.audio = game, True
                app.library = Mock(read_asset=Mock(return_value=b'authored click'))
                app.state = Mock(sound=False, music=True, sound_volume=100)
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
                with self.subTest(game=game, service=service, flag=flag), \
                        patch('pygame.time.get_ticks') as clock:
                    clock.return_value = 10000
                    ui, resources = self.make_ui(service, 8201, flag, game)
                    resources.read_asset.return_value = sample.getvalue()
                    saved = ui.session.snapshot()
                    ui.session = Session.from_snapshot(resources, saved)
                    pygame.mixer.init(frequency=8000, size=-16, channels=1, buffer=128)
                    ui._sync_audio()
                    pygame.time.wait(400)
                    clock.return_value = 10400
                    ui._sync_audio()
                    self.assertEqual(pygame.mixer.music.get_busy(), bool(flag))
                    ui.menu_open = True                     # storeGameAudio: a 1000 ms fade, then held
                    ui._sync_audio()
                    self.assertEqual(pygame.mixer.music.get_busy(), bool(flag))
                    clock.return_value = 11500
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
            with patch('pygame.mixer.music', mixer.music), patch('pygame.time.get_ticks') as clock:
                clock.return_value = 10000
                ui._sync_audio()
                ui._sync_audio()
                clock.return_value = 10250
                ui.menu_open = True
                ui._sync_audio()
                clock.return_value = 11300                  # the pause menu's fade is over: held
                ui._sync_audio()
                ui.menu_open = False
                ui._sync_audio()                            # restartFromLoad: the held cue from where it was
            self.assertEqual([c['kind'] for c in mixer.commands],
                             ['music_stop', 'music_load', 'music_play', 'music_pause', 'music_play'])
            self.assertEqual(mixer.commands[2], dict(kind='music_play', start=0., loops=-1 if flag else 0))
            self.assertEqual(mixer.commands[4], dict(kind='music_play', start=.25, loops=-1 if flag else 0))

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

    def test_two_cues_in_one_track_and_the_music_switch(self):
        ui, r = self.make_ui(music=8213)
        with patch('pygame.mixer.music') as music, patch('pygame.time.get_ticks') as clock:
            clock.return_value = 10000
            ui._sync_audio()
            ui.session.engine.music_id = 8214
            ui._sync_audio()
            # The playing cue fades out over 1000 ms before the new one starts (SHSSoundManager::playMusic).
            self.assertEqual(music.play.call_count, 1)
            clock.return_value = 10500
            ui._sync_audio()
            self.assertAlmostEqual(music.set_volume.call_args.args[0], .5 * ui.music_volume)
            self.assertEqual(music.play.call_count, 1)
            clock.return_value = 11000
            ui._sync_audio()
            self.assertEqual([call.kwargs['start'] for call in music.play.call_args_list], [4., 39.2])
            self.assertEqual([call.args for call in r.read_asset.call_args_list], [(8212,), (8212,)])
            saved = ui.session.snapshot()
            # Music off: setMusicEnabled(false) -> stopMusic(-1, true), a 1000 ms fade.
            ui.music_enabled = False
            ui._sync_audio()
            self.assertEqual(music.stop.call_count, 2)
            clock.return_value = 11500
            ui._sync_audio()
            self.assertAlmostEqual(music.set_volume.call_args.args[0], .5 * ui.music_volume)
            clock.return_value = 12000
            ui._sync_audio()
            self.assertEqual(music.stop.call_count, 3)
            # Requests while off are ignored, and turning Music on plays nothing until the script asks again.
            ui.session.engine.music_id = 8213
            ui._sync_audio()
            ui.music_enabled = True
            ui._sync_audio()
            self.assertEqual(music.play.call_count, 2)
            from test_background import dispatch
            dispatch(ui.session.engine, 80, 8213, 0)
            ui._sync_audio()
            self.assertEqual(music.play.call_args.kwargs, {'loops': 0, 'start': 4.})
            self.assertEqual(ui.session.snapshot()['engine'].keys(), saved['engine'].keys())

    def test_stop_fades_out_over_its_argument_and_holds_the_next_cue(self):
        # Service 81 is stopMusic(arg, true) in both iOS games (SHS HD case 0x51, CoD 1.4.7 00042d70).
        from test_background import dispatch
        for game, fade, expected in (('cod', 2000, 2000), ('cod', 0xffff, 1000), ('cod', -1, 1000),
                                     ('cod', 0, 0), ('shs', 2000, 2000), ('shs', 0, 0)):
            with self.subTest(game=game, fade=fade):
                ui, r = self.make_ui(music=8201, repeat=1, game=game)
                with patch('pygame.mixer.music') as music, patch('pygame.time.get_ticks') as clock:
                    clock.return_value = 10000
                    ui._sync_audio()
                    dispatch(ui.session.engine, 81, fade)
                    saved = ui.session.snapshot()
                    ui._sync_audio()
                    if not expected:
                        self.assertEqual(music.stop.call_count, 2)
                        continue
                    music.stop.assert_called_once_with()
                    ui.session.engine.music_id = 8203
                    clock.return_value = 10000 + expected // 2
                    ui._sync_audio()
                    self.assertAlmostEqual(music.set_volume.call_args.args[0], .5 * ui.music_volume)
                    music.play.assert_called_once()
                    clock.return_value = 10000 + expected
                    ui._sync_audio()
                    self.assertEqual(music.stop.call_count, 2)
                    self.assertEqual([call.args for call in r.read_asset.call_args_list], [(8201,), (8203,)])
                    self.assertEqual(saved['engine'].keys(), ui.session.snapshot()['engine'].keys())

    def test_cod_replaying_the_fading_cue_keeps_it_at_full_volume(self):
        from test_background import dispatch
        ui, _ = self.make_ui(music=8201, repeat=1, game='cod')
        with patch('pygame.mixer.music') as music, patch('pygame.time.get_ticks') as clock:
            clock.return_value = 10000
            ui._sync_audio()
            dispatch(ui.session.engine, 81, 1000)
            clock.return_value = 10500
            ui._sync_audio()
            dispatch(ui.session.engine, 80, 8201, 1)
            ui._sync_audio()
            self.assertEqual(music.set_volume.call_args.args[0], ui.music_volume)
            clock.return_value = 12000
            ui._sync_audio()
            music.stop.assert_called_once_with()
            music.play.assert_called_once()

    def test_pause_menu_fades_out_then_resumes_from_where_it_paused_without_replaying_vm(self):
        # storeGameAudio saves the cue (its currentTime) and fades it over 1000 ms; restoreGameAudio plays it again from
        # there at full volume.
        import pygame
        for controls in ('buttons', 'escape'):
            with self.subTest(controls=controls):
                ui, resources = self.make_ui()
                saved = ui.session.snapshot()
                with patch('pygame.mixer.music') as music, patch('pygame.time.get_ticks') as clock:
                    clock.return_value = 10000
                    ui._sync_audio()
                    clock.return_value = 10500
                    if controls == 'buttons':
                        ui.command(('menu',))
                    else:
                        ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
                    clock.return_value = 11000
                    ui._sync_audio()
                    self.assertAlmostEqual(music.set_volume.call_args.args[0], .5 * ui.music_volume)
                    music.pause.assert_not_called()
                    clock.return_value = 11600
                    ui._sync_audio()
                    ui.tick(5000)
                    music.pause.assert_called_once_with()
                    clock.return_value = 15000
                    if controls == 'buttons':
                        ui.command(('resume',))
                    else:
                        ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
                    ui._sync_audio()
                    ui._sync_audio()
                    music.unpause.assert_not_called()
                    music.load.assert_called_once()
                    self.assertEqual([call.kwargs for call in music.play.call_args_list],
                                     [dict(loops=0, start=2.8), dict(loops=0, start=3.3)])
                    self.assertEqual(music.set_volume.call_args.args[0], ui.music_volume)
                    resources.read_asset.assert_called_once_with(8201)
                    self.assertEqual(ui.session.snapshot(), saved)

    def test_focus_and_menu_holds_must_both_clear_before_music_resumes(self):
        import pygame
        ui, _ = self.make_ui()
        with patch('pygame.mixer.music') as music, patch('pygame.time.get_ticks') as clock:
            clock.return_value = 10000
            ui._sync_audio()
            ui.command(('menu',))
            ui.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST))
            ui._sync_audio()
            music.pause.assert_called_once_with()
            clock.return_value = 11100                      # the pause menu's fade ends while the window is away
            ui._sync_audio()
            ui.handle_event(pygame.event.Event(pygame.WINDOWFOCUSGAINED))
            ui._sync_audio()
            music.unpause.assert_not_called()               # held by the pause menu
            ui.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST))
            ui.command(('resume',))
            ui._sync_audio()
            calls = [c[0] for c in music.method_calls if c[0] in ('play', 'pause', 'unpause')]
            self.assertEqual(calls[-1], 'pause')            # restored, but held until the window is back
            ui.handle_event(pygame.event.Event(pygame.WINDOWFOCUSGAINED))
            ui._sync_audio()
            calls = [c[0] for c in music.method_calls if c[0] in ('play', 'pause', 'unpause')]
            self.assertEqual(calls[-1], 'unpause')
            self.assertEqual(music.play.call_count, 2)

    def test_muting_stopping_and_switching_cues_while_paused_do_not_resume_stale_music(self):
        for change in ('mute', 'stop', 'cue'):
            with self.subTest(change=change):
                ui, _ = self.make_ui(music=8213)
                with patch('pygame.mixer.music') as music, patch('pygame.time.get_ticks') as clock:
                    clock.return_value = 10000
                    ui._sync_audio()
                    ui.command(('menu',))
                    clock.return_value = 11100                  # held
                    ui._sync_audio()
                    if change == 'mute':
                        ui.music_enabled = False                # restartFromLoad drops it: Music is off
                    else:
                        ui.session.engine.music_id = -1 if change == 'stop' else 8214
                    ui._sync_audio()
                    clock.return_value = 12300
                    ui._sync_audio()
                    ui.command(('resume',))
                    ui._sync_audio()
                    starts = [call.kwargs['start'] for call in music.play.call_args_list]
                    if change == 'cue':                         # the new cue, held and resumed in its place
                        self.assertEqual(starts[:2], [4., 39.2])
                        self.assertEqual(starts[-1], 39.2)
                    else:
                        self.assertEqual(starts, [4.])
                    music.unpause.assert_not_called()

    def test_live_main_menu_resume_keeps_the_stream_and_restart_loads_a_new_one(self):
        from exp_runtime.application import Application
        ui, resources = self.make_ui()
        resources.record['id'] = 'authored-episode'
        # Exercise application lifecycle without original menu art or writes.
        app = Application.__new__(Application)
        app.selected_game = 'shs'
        app.shot_cache = {}             # __init__ is skipped here; save_screenshot drops the episode's cached shot
        app.game, app.selected, app.audio, app.active = ui, resources.record['id'], True, True
        app.window = ui.window
        app.library = resources
        app.menu_music = Mock()
        app.menu_music_token = None
        app.menu_music_loaded = app.menu_music_paused = False
        app.state = Mock(music=True, sound=True, music_volume=100, sound_volume=100)
        app.state.title.return_value = resources.record['titles'][0]
        app.show = Mock(side_effect=lambda screen, **_: setattr(app, 'screen', screen))
        app.refresh_saves = Mock()
        saved = ui.session.snapshot()
        with patch('pygame.mixer.music') as music, patch('pygame.mixer.stop'):
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
            self.assertEqual(ui.session.snapshot(), saved)
            app.return_to_menu()
            app.state.session.return_value = Session(resources)
            app.start(resume=False)
            app.game._sync_audio()
            self.assertIsNot(app.game, ui)
            self.assertEqual(music.load.call_count, 2)
            self.assertEqual(music.play.call_count, 2)

    def test_main_menu_music_switch_fades_out_and_restarts_or_cancels_the_fade(self):
        # setMusicEnabled(false): a 1000 ms fade. Back on: doSoundManagerTransition plays the menu's cue from the start,
        # or, still fading, playMusic of the same cue cancels the fade. The volume slider never restarts it.
        from exp_runtime.application import Application
        app = Application.__new__(Application)
        app.audio, app.screen, app.shell = True, 'main', object()
        app.library = Mock(game_id='shs', read_asset=Mock(return_value=b'authored theme'))
        app.state = SimpleNamespace(music=True, music_volume=80)
        with patch('pygame.mixer.Sound') as sound, patch('pygame.time.get_ticks') as clock:
            clock.return_value = 10000
            app.play_menu_music()
            song = app.menu_sound
            app.state.music = False
            app.menu_music_changed(switched=True)
            clock.return_value = 10500
            app._fade_menu_music()
            self.assertAlmostEqual(song.set_volume.call_args.args[0], .4)
            app.state.music = True                          # back on mid-fade: it plays on at full volume
            app.menu_music_changed(switched=True)
            self.assertEqual((app.menu_sound, song.set_volume.call_args.args[0]), (song, .8))
            self.assertEqual(sound.call_count, 1)
            app.state.music = False
            app.menu_music_changed(switched=True)
            clock.return_value = 11600
            app._fade_menu_music()
            self.assertIsNone(app.menu_sound)
            song.stop.assert_called_once_with()
            app.state.music = True                          # after the fade: from the start again
            app.menu_music_changed(switched=True)
            self.assertEqual(sound.call_count, 2)
            app.menu_sound.play.assert_called_with()
            app.state.music_volume = 50
            app.menu_music_changed()                        # the slider only sets the volume
            self.assertEqual(sound.call_count, 2)
            self.assertEqual(app.menu_sound.set_volume.call_args.args[0], .5)

    def test_music_switched_on_in_the_pause_menu_plays_the_menus_song_until_resume(self):
        # SHSEngine +0xb22c: the menu's song plays once the episode's music is held; Resume fades it over 1000 ms and
        # only then restores the episode's song from where it was paused (restoreGameAudio waits for silence).
        for game, menu_song in (('shs', 8215), ('cod', 8209)):
            with self.subTest(game=game):
                ui, resources = self.make_ui(music=8201, repeat=1, game=game)
                resources.library.read_asset = Mock(side_effect=lambda asset: f'base {asset}'.encode())
                with patch('pygame.mixer.music') as music, patch('pygame.time.get_ticks') as clock,                         patch('pygame.mixer.Sound') as sound:
                    song = sound.return_value
                    song.get_num_channels.return_value = 1
                    clock.return_value = 10000
                    ui._sync_audio()
                    clock.return_value = 10200
                    ui.command(('menu',))
                    ui.command(('pause_toggle', 'music'))       # off
                    ui.command(('pause_toggle', 'music'))       # on, while the episode's song still fades
                    played = lambda: [c.kwargs['file'].getvalue() for c in sound.call_args_list]
                    self.assertNotIn(f'base {menu_song}'.encode(), played())
                    clock.return_value = 11300                  # held: now the menu's song
                    ui._sync_audio()
                    self.assertIn(f'base {menu_song}'.encode(), played())
                    ui.command(('resume',))
                    clock.return_value = 11800
                    ui._sync_audio()
                    self.assertAlmostEqual(song.set_volume.call_args.args[0], .5 * ui.music_volume)
                    self.assertEqual(music.play.call_count, 1)  # the episode waits
                    clock.return_value = 12400
                    ui._sync_audio()
                    song.stop.assert_called_once_with()
                    ui._sync_audio()
                    self.assertEqual(music.play.call_args.kwargs, dict(loops=-1, start=.2))

    def test_the_pause_menus_song_carries_on_into_the_main_menu(self):
        ui, resources = self.make_ui(music=8201, repeat=1)
        resources.library.read_asset = Mock(return_value=b'menu song')
        with patch('pygame.mixer.music'), patch('pygame.time.get_ticks') as clock,                 patch('pygame.mixer.Sound') as sound:
            sound.return_value.get_num_channels.return_value = 1
            clock.return_value = 10000
            ui._sync_audio()
            ui.command(('menu',))
            clock.return_value = 11100
            ui.music_enabled = False
            ui.command(('pause_toggle', 'music'))
            ui._sync_audio()
            self.assertIs(ui.take_pause_song(), sound.return_value)
            self.assertIsNone(ui.take_pause_song())             # handed over once
            ui.command(('pause_toggle', 'music'))               # off again: nothing playing to fade

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
        with patch('pygame.time.get_ticks') as clock:
            clock.return_value = 10000
            ui._sync_audio()
            ui.command(('menu',))
            clock.return_value = 11100                      # the pause menu's fade is over: held
            ui._sync_audio()
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

    def test_real_mixer_holds_and_resumes_authored_music_position(self):
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
        with patch('pygame.time.get_ticks') as clock:
            clock.return_value = 10000
            ui._sync_audio()
            self.assertTrue(pygame.mixer.music.get_busy())
            clock.return_value = 10050
            ui.command(('menu',))
            ui._sync_audio()
            self.assertTrue(pygame.mixer.music.get_busy())  # fading
            clock.return_value = 11100
            ui._sync_audio()
            self.assertFalse(pygame.mixer.music.get_busy())
            held = ui.music_stream.stored
            self.assertAlmostEqual(held, .05)
            ui.command(('resume',))
            ui._sync_audio()
            self.assertTrue(pygame.mixer.music.get_busy())
            clock.return_value = 11200
            ui._sync_audio()
            self.assertGreater(ui.music_stream.position(), held)
            resources.read_asset.assert_called_once_with(8201)
            pygame.mixer.music.stop()  # A finished/stopped stream must not be restarted by Resume.
            ui._sync_audio()
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
        with patch('pygame.mixer.Sound') as sound:
            ui._sync_audio()
            r.read_asset.assert_called_once_with(28202)
            sound.return_value.play.assert_called_once_with()

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
