"""The game chooser's Options > Sound (reported on iOS, 2026-11-22: "AppCard.slider() got an unexpected keyword argument
'key'" stopped the app on every platform), and the iOS host's UIKit switches and sliders on that page reaching the
chooser's Options."""
import os
from types import SimpleNamespace
import unittest
from unittest import mock

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
import pygame


SETTINGS = dict(music=True, sound=False, music_volume=.6, sound_volume=.3)


class ChooserSoundPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    def sound_page(self):
        from exp_runtime.desktop_app_hd import AppOptionsMenu
        menu = AppOptionsMenu()
        menu.state.screen = 'options:sound'
        return menu, menu.layout(SETTINGS)[1]

    def test_the_sound_page_draws_its_sliders(self):
        _, buttons = self.sound_page()
        sliders = [command for _, command in buttons if command[0] == 'pause_slider']
        self.assertEqual([command[1] for command in sliders], ['music', 'sound'])

    def test_with_the_hosts_own_sliders_the_track_is_placed_for_them(self):
        from exp_runtime import graphics
        with mock.patch.object(graphics, 'native_controls', []):
            menu, _ = self.sound_page()
        placed = [(c['kind'], c['key'], c.get('value')) for c in menu.screen_controls if c['kind'] == 'slider']
        self.assertEqual(placed, [('slider', 'music', .6), ('slider', 'sound', .3)])


class ChooserNativeControlTests(unittest.TestCase):
    def host(self, options):
        from exp_runtime.platforms.ios import Host
        host = Host.__new__(Host)
        host.app = SimpleNamespace(screen='options', library=None, game=None, shell=None,
                                   app_screens=SimpleNamespace(options=options))
        host.controls_shown = [dict(kind='switch', key='music', on=True)]
        return host

    def test_a_uiswitch_and_a_uislider_on_the_choosers_options_reach_it(self):
        options = SimpleNamespace(ask=None, activate=mock.Mock(), set_volume=mock.Mock())
        host = self.host(options)
        host.flip_switch('music', False)
        options.activate.assert_called_once_with(('pause_toggle', 'music'))
        host.slide_volume('sound', .25)
        options.set_volume.assert_called_once_with('sound', .25)

    def test_not_while_a_question_is_over_the_page(self):
        options = SimpleNamespace(ask=('Reset?', '', ('No', 'Yes'), None), activate=mock.Mock(), set_volume=mock.Mock())
        host = self.host(options)
        host.flip_switch('music', False)
        host.slide_volume('music', .5)
        options.activate.assert_not_called()
        options.set_volume.assert_not_called()


if __name__ == '__main__':
    unittest.main()
