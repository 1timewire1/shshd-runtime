"""Interface sounds: SHS HD's and CoD 1.4.7's playSound cues for choices, menu rows, switches and sliders."""
import importlib.util
import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from test_choice_hints import choice_session

# game: (click, Sound switched on, Sound FX slider, Music slider)
CUES = {'shs': (8010, 8004, 8007, 8009), 'cod': (8005, 8005, 8005, 8005)}


class FakeMixer:
    """pygame.mixer.Sound stand-in recording (asset, volume) per play; `busy` keeps the channels playing."""

    def __init__(self):
        self.played, self.busy, self.stopped = [], False, 0

    def sound(self, file):
        asset, sound = int(file.getvalue()), Mock()

        def play():
            self.played.append((asset, sound.set_volume.call_args.args[0]))
            channel = Mock(get_busy=lambda: self.busy)
            channel.stop.side_effect = lambda: setattr(self, 'stopped', self.stopped + 1)
            return channel
        sound.play.side_effect = play
        return sound

    def assets(self):
        return [asset for asset, _ in self.played]


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class DesktopUiSoundTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        from exp_runtime.desktop import Desktop
        self.Desktop = Desktop
        self.addCleanup(pygame.quit)

    def ui(self, game):
        session = choice_session(lambda refs: [])
        ui = self.Desktop(session, audio=False)
        ui.audio, ui._sync_music = True, Mock()
        session.resources.library.game_id = game
        session.resources.library.read_asset = Mock(side_effect=lambda asset: str(asset).encode())
        session.resources.read_asset = Mock(side_effect=AssertionError('Episode bank used for an interface sound'))
        mixer = FakeMixer()
        for patcher in (patch('pygame.mixer.Sound', side_effect=mixer.sound), patch('pygame.mixer.music')):
            patcher.start()
            self.addCleanup(patcher.stop)
        return ui, mixer

    def test_picking_a_story_choice_clicks_at_the_sound_volume(self):
        for game, (click, *_) in CUES.items():
            with self.subTest(game=game):
                ui, mixer = self.ui(game)
                ui.sound_volume = .4
                self.assertEqual(ui.session.pending.name, 'choice')
                ui.command(('choose', 0))
                self.assertEqual(mixer.played, [(click, .4)])

    def test_choice_click_respects_the_sound_switch(self):
        ui, mixer = self.ui('shs')
        ui.sound_enabled = False
        ui.command(('choose', 1))
        self.assertEqual(mixer.played, [])
        self.assertNotEqual(ui.session.pending and ui.session.pending.name, 'choice')

    def test_pause_rows_and_back_click_but_switches_do_not(self):
        for game, (click, sound_on, *_) in CUES.items():
            with self.subTest(game=game):
                ui, mixer = self.ui(game)
                ui.menu_open = True
                ui.command(('pause_open', 'options'))
                ui.command(('pause_back',))
                self.assertEqual(mixer.assets(), [click, click])
                for key in ('choice_hints', 'music', 'music', 'sound'):
                    ui.command(('pause_toggle', key))           # Sound switched off: silent
                self.assertEqual(mixer.assets(), [click, click])
                ui.command(('pause_toggle', 'sound'))
                self.assertEqual(mixer.assets(), [click, click, sound_on])
                self.assertEqual(mixer.stopped, 2)              # the switch's sound stops the others first

    def test_volume_sliders_preview_their_sounds(self):
        for game, (_, _, fx, music) in CUES.items():
            with self.subTest(game=game):
                ui, mixer = self.ui(game)
                ui._set_volume('sound', .5)
                ui._set_volume('sound', .5)                     # unchanged: nothing new
                self.assertEqual(mixer.played, [(fx, .5)])
                ui.sound_enabled = False
                ui._set_volume('sound', .7)                     # at the Sound FX volume, so Sound must be on
                ui._set_volume('music', .3)                     # at its own volume, Sound on or off
                ui._set_volume('music', 0.)
                self.assertEqual(mixer.played, [(fx, .5), (music, .3)])
                ui.music_enabled = False
                ui._set_volume('music', .6)
                self.assertEqual(len(mixer.played), 2)

    def test_a_preview_never_restarts_while_one_plays(self):
        ui, mixer = self.ui('shs')
        mixer.busy = True
        ui._set_volume('sound', .2)
        ui._set_volume('sound', .3)
        self.assertEqual(mixer.played, [(8007, .2)])
        ui.command(('resume',))                               # a click is not a preview: it always plays
        self.assertEqual(mixer.assets(), [8007, 8010])
        mixer.busy = False
        ui._set_volume('sound', .4)
        self.assertEqual(mixer.assets(), [8007, 8010, 8007])


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class MainMenuUiSoundTests(unittest.TestCase):
    def test_options_switches_and_sliders_in_the_main_menu(self):
        from exp_runtime.application_hd import HdShell
        for game, (_, sound_on, fx, music) in CUES.items():
            with self.subTest(game=game):
                state = SimpleNamespace(sound=False, music=True, sound_volume=100, music_volume=100,
                                        choice_hints=True, persist=Mock())
                shell = SimpleNamespace(app=Mock(state=state))
                HdShell.toggle(shell, 'choice_hints')
                HdShell.toggle(shell, 'sound')
                shell.app.ui_sound.assert_called_once_with('SOUND_ON_SOUND', stop_others=True)
                shell.app.ui_sound.reset_mock()
                HdShell.set_volume(shell, 'sound', .5)
                HdShell.set_volume(shell, 'music', .25)
                HdShell.set_volume(shell, 'music', .25)
                self.assertEqual(shell.app.ui_sound.call_args_list,
                                 [unittest.mock.call('SOUND_SLIDER_SOUND', when_idle=True),
                                  unittest.mock.call('MUSIC_SLIDER_SOUND', volume=.25, when_idle=True)])
                self.assertEqual((state.sound_volume, state.music_volume), (50, 25))

    def test_main_menu_switches_do_not_click(self):
        from exp_runtime.application import Application
        import pygame
        app = Application.__new__(Application)
        app._click_sound = Mock()
        for pressed, clicks in ((('pause_toggle', 'music'), 0), (('pause_open', 'sound'), 1)):
            app.shell = Mock(pressed=pressed)
            app.picker_point = lambda pos: pos
            app.shell_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(1, 1)))
            self.assertEqual(app._click_sound.call_count, clicks)

    def test_app_sounds_use_the_selected_game_and_sound_volume(self):
        from exp_runtime.application import Application
        for game, (click, _, _, music) in CUES.items():
            with self.subTest(game=game):
                app = Application.__new__(Application)
                app.selected_game, app.audio = game, True
                app.library = Mock(read_asset=Mock(side_effect=lambda asset: str(asset).encode()))
                app.state = SimpleNamespace(sound=True, sound_volume=30)
                mixer = FakeMixer()
                with patch('pygame.mixer.Sound', side_effect=mixer.sound):
                    app._click_sound()
                    app.state.sound = False
                    app._click_sound()
                    app.ui_sound('MUSIC_SLIDER_SOUND', volume=.8, when_idle=True)
                self.assertEqual(mixer.played, [(click, .3), (music, .8)])


if __name__ == '__main__':
    unittest.main()
