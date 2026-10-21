"""HD pause menu layout, navigation and hit rectangles (no bundled art)."""
import importlib.util
import os
import unittest
from unittest.mock import patch


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class HdPauseTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        pygame.init()
        pygame.font.init()
        pygame.display.set_mode((16, 16))
        self.addCleanup(pygame.quit)
        from exp_runtime import desktop_pause_hd as module
        self.module = module
        self.menu = module.HdPauseMenu.__new__(module.HdPauseMenu)
        self.menu.state = module.PauseState()
        strings = [''] * 273
        for index, text in {8: 'Pause', 9: 'Main Menu', 10: 'Options', 11: 'Vibration', 12: 'Game Music', 13: 'Music Volume',
                            14: 'Sound FX', 15: 'Sound FX Volume', 16: 'About', 20: 'Resume', 83: 'Episodes On Demand',
                            119: 'Now Airing', 120: 'Help & About', 133: 'Introduction', 134: 'Controls',
                            135: 'Network', 136: 'Welcome. ' * 40, 137: 'Controls text.\n' * 80,
                            0: 'Version: ~276~'}.items():
            strings[index] = text
        art = pygame.Surface((10, 10), pygame.SRCALPHA)
        self.patches = [patch.object(module.HdPauseMenu, 'strings', lambda _self: strings),
                        patch.object(module.HdPauseMenu, 'art', lambda _self, *_: pygame.transform.scale(
                            art, (10 * module.S, 10 * module.S)))]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.settings = dict(music=True, sound=False, music_volume=.5, sound_volume=.25, choice_hints=False,
                             skip_minigames=False, skip_ad_intros=False)

    def commands(self, **kw):
        _, buttons = self.menu.layout(self.settings, **kw)
        return buttons

    def test_pause_rows_are_88_high_and_the_card_is_centered(self):
        buttons = self.commands()
        self.assertEqual([c for _, c in buttons], [('resume',), ('pause_open', 'options'),
                                                    ('pause_open', 'help'), ('main_menu',)])
        self.assertEqual([r.height for r, _ in buttons], [88] * 4)
        self.assertEqual(buttons[0][0].y, 349)
        # 112 header + 4 rows + 86 footer, centered on y 512.
        self.assertEqual(buttons[-1][0].bottom + 86, 512 + (112 + 4 * 88 + 86) // 2)

    def test_host_rows_follow_the_real_ones(self):
        buttons = self.commands(host_rows=[('Save', ('save',))])
        self.assertEqual([c for _, c in buttons][-2:], [("main_menu",), ("save",)])

    def test_options_lists_categories_then_each_categorys_switches(self):
        state = self.menu.state
        state.screen = 'options'
        self.assertEqual([c for _, c in self.commands()],
                         [('pause_open', 'options:general'), ('pause_open', 'options:sound'), ('pause_back',)])
        state.screen = 'options:sound'
        commands = [c for _, c in self.commands()]
        self.assertEqual([c[:2] for c in commands], [('pause_toggle', 'music'), ('pause_slider', 'music'),
                                                     ('pause_toggle', 'sound'), ('pause_slider', 'sound'),
                                                     ('pause_back',)])
        track = self.commands()[1][0]
        self.assertEqual((track.left + 10, track.width - 20), (143, 460))
        state.screen = 'options:general'
        rows = self.commands()
        self.assertEqual([c[:2] for _, c in rows], [('pause_toggle', key) for key in
                                                    ('choice_hints', 'skip_minigames', 'skip_ad_intros')]
                         + [('pause_back',)])
        self.assertGreaterEqual(rows[1][0].top, rows[0][0].bottom)          # Ask to Skip Mini-Games under Choice Hints
        # Offered settings add their rows: the side panels in a story, the backdrop switch where there is a collage.
        self.settings.update(side_panels=False, hd_backdrop=True)
        self.assertEqual([c[1] for _, c in self.commands() if c[0] == 'pause_toggle'],
                         ['side_panels', 'choice_hints', 'skip_minigames', 'skip_ad_intros', 'hd_backdrop'])
        # Back: the category list, then the pause panel.
        self.assertFalse(self.menu.back())
        self.assertEqual(state.screen, 'options')
        self.assertFalse(self.menu.back())
        self.assertEqual(state.screen, 'pause')

    def test_vibration_leads_the_sound_page_when_offered(self):
        self.menu.state.screen = 'options:sound'
        self.settings['vibration'] = False
        buttons = self.commands()
        self.assertEqual([c[:2] for _, c in buttons][:2], [('pause_toggle', 'vibration'), ('pause_toggle', 'music')])
        self.assertEqual(self.menu.option_rows('sound', self.settings, self.menu.strings())[0][1], 'Vibration')

    def test_title_language_button_and_data_management_on_the_main_menu_only(self):
        state = self.menu.state
        state.screen = 'options'
        self.assertNotIn(('pause_open', 'options:data'), [c for _, c in self.commands()])   # in a story: none
        self.settings.update(title_language='English', add_episodes=True, open_library=True)
        self.assertIn(('pause_open', 'options:data'), [c for _, c in self.commands()])
        state.screen = 'options:general'
        rows = self.commands()
        self.assertEqual(rows[-2][1], ('pause_cycle', 'title_language'))                 # last row: its button
        from exp_runtime.desktop_pause_hd import CONTROL_RIGHT, PANEL_W, PANEL_X
        self.assertEqual((rows[-2][0].width, rows[-2][0].height), (104, 34))          # a little bigger than a switch
        self.assertEqual(rows[-2][0].right, PANEL_X + PANEL_W - CONTROL_RIGHT)          # against the card's right
        state.screen = 'options:data'
        self.assertEqual([c for _, c in self.commands()], [('pause_action', 'add_episodes'),
                                                           ('pause_action', 'open_library'), ('pause_back',)])

    def test_back_steps_out_one_screen_at_a_time(self):
        state = self.menu.state
        state.screen = 'controls'
        self.assertFalse(self.menu.back())
        self.assertEqual(state.screen, 'help')
        self.assertFalse(self.menu.back())
        self.assertEqual(state.screen, 'pause')
        self.assertTrue(self.menu.back())

    def test_a_page_pushes_in_from_the_right_and_back_slides_it_out_again(self):
        import pygame
        from exp_runtime.desktop_pause import ease_in_out
        menu, module = self.menu, self.module
        width = module.FRAME[0] * module.S
        layers = {}

        def screen_layout(settings, host_rows=(), *, message=''):
            layer = pygame.Surface((width, 8), pygame.SRCALPHA)
            layer.fill({'pause': (255, 0, 0, 255), 'options': (0, 0, 255, 255)}[menu.state.screen], (0, 0, 4, 8))
            layers[menu.state.screen] = layer
            return layer, [('rect', ('row',))]
        menu.screen_layout = screen_layout
        self.assertEqual(self.commands(), [('rect', ('row',))])       # at rest: no slide
        menu.open('options')
        menu.advance(module.SLIDE_MS / 2)
        layer, buttons = menu.layout(self.settings)
        self.assertEqual(buttons, [])                                 # no input until it settles
        shift = round(ease_in_out(.5) * width)
        self.assertEqual(layer.get_at((width - shift, 0))[:3], (0, 0, 255))   # the new card enters from the right
        self.assertEqual(layer.get_at((0, 0)).a, 0)                   # the old one has left by the left edge
        menu.advance(module.SLIDE_MS / 2)
        layer, buttons = menu.layout(self.settings)
        self.assertIs(layer, layers['options'])
        self.assertEqual(buttons, [('rect', ('row',))])
        self.assertFalse(menu.back())                                 # back: the reverse
        menu.advance(module.SLIDE_MS / 4)
        layer, _ = menu.layout(self.settings)
        shift = round(ease_in_out(.25) * width)
        self.assertEqual(layer.get_at((shift, 0))[:3], (0, 0, 255))   # the page leaves to the right
        self.assertEqual(layer.get_at((shift - width, 0) if shift > width else (0, 0)).a, 0)
        menu.reset()
        self.assertIsNone(menu.slide)

    def test_text_pages_scroll_within_their_limits_and_show_the_version(self):
        state = self.menu.state
        state.screen, state.scroll = 'controls', 10_000.
        self.commands()
        self.assertGreater(state.max_scroll, 0)
        self.assertEqual(state.scroll, state.max_scroll)
        with patch.object(self.module, 'HELP_TEXT_OVERRIDES', {}):
            self.assertEqual(self.menu.text_lines('about')[1], f'Version: {self.module.VERSION}')

    def test_long_titles_take_two_lines(self):
        self.assertEqual(self.menu.title_lines('Pause'), ['Pause'])
        self.assertEqual(self.menu.title_lines('Episodes On Demand'), ['Episodes On', 'Demand'])

    def test_an_override_replaces_a_pages_text_a_page_with_none_still_reads_the_original(self):
        overrides = {'airing': ('Now Airing', 'Custom copy, version ~276~.')}
        with patch.object(self.module, 'HELP_TEXT_OVERRIDES', overrides):
            self.assertEqual(self.menu.text_lines('airing'),
                             ('Now Airing', f'Custom copy, version {self.module.VERSION}.'))
            self.assertEqual(self.menu.text_lines('demand'), ('Episodes On Demand', ''))

    def test_a_url_in_override_text_becomes_a_tappable_pause_link(self):
        overrides = {'controls': ('Controls', 'Join us: https://discord.gg/example and have fun.')}
        with patch.object(self.module, 'HELP_TEXT_OVERRIDES', overrides):
            self.menu.state.screen = 'controls'
            buttons = self.commands()
        links = [(rect, command) for rect, command in buttons if command[0] == 'pause_link']
        self.assertEqual(len(links), 1)
        rect, command = links[0]
        self.assertEqual(command, ('pause_link', 'https://discord.gg/example'))
        self.assertGreater(rect.width, 0)
        self.assertGreater(rect.x, self.module.PANEL_X)

    def test_text_with_no_url_gets_no_pause_link(self):
        self.menu.state.screen = 'controls'          # the fixture's own 'Controls text.' body has no URL
        buttons = self.commands()
        self.assertFalse([c for _, c in buttons if c[0] == 'pause_link'])

    def test_arrow_keys_highlight_rows_and_the_back_button_and_enter_taps_them(self):
        import pygame
        menu, state = self.menu, self.menu.state
        plain, _ = menu.layout(self.settings)
        self.assertIsNone(menu.key(pygame.K_UP))
        self.assertEqual(state.focus, ('main_menu',))                       # the first Up takes the last row
        lit, _ = menu.layout(self.settings)
        self.assertNotEqual(pygame.image.tobytes(lit, 'RGBA'), pygame.image.tobytes(plain, 'RGBA'))
        menu.key(pygame.K_UP)
        menu.key(pygame.K_UP)
        self.assertEqual(menu.key(pygame.K_RETURN), ('pause_open', 'options'))
        state.screen = 'options:sound'
        self.commands()
        self.assertIsNone(menu.key(pygame.K_RETURN))                        # nothing here is highlighted yet
        menu.key(pygame.K_DOWN)
        self.assertEqual(menu.key(pygame.K_SPACE), ('pause_toggle', 'music'))
        menu.key(pygame.K_DOWN)
        self.assertEqual(state.focus[:2], ('pause_slider', 'music'))
        self.assertEqual(menu.key(pygame.K_RIGHT), ('pause_volume', 'music', self.module.VOLUME_STEP))
        self.assertEqual(menu.key(pygame.K_LEFT), ('pause_volume', 'music', -self.module.VOLUME_STEP))
        self.assertIsNone(menu.key(pygame.K_RETURN))                        # a slider is not tapped
        for _ in range(5):
            menu.key(pygame.K_DOWN)
        self.assertEqual(state.focus, ('pause_back',))                      # the back button, and no further
        self.assertEqual(menu.key(pygame.K_KP_ENTER), ('pause_back',))

    def test_arrow_keys_scroll_a_text_page(self):
        import pygame
        state = self.menu.state
        state.screen = 'controls'
        self.commands()
        self.menu.key(pygame.K_DOWN)
        self.menu.key(pygame.K_PAGEDOWN)
        self.assertEqual((state.scroll, state.focus), (440., None))
        self.menu.key(pygame.K_UP)
        self.assertEqual(state.scroll, 400.)


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class CodPauseTests(unittest.TestCase):
    """Cause of Death's Pause / Options / Help & About (desktop_cod_pause.py): SHS HD's layout in CoD's dress, from
    authored strings and art."""

    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        from types import SimpleNamespace
        pygame.init()
        pygame.font.init()
        pygame.display.set_mode((16, 16))
        self.addCleanup(pygame.quit)
        from exp_runtime.desktop_cod_pause import CodPauseMenu
        strings = [''] * 257
        for index, text in {8: 'Pause', 9: 'Main Menu', 10: 'Options', 11: 'Vibration', 12: 'Game Music', 13: 'Music Volume',
                            14: 'Sound FX', 15: 'Sound FX Volume', 16: 'About', 20: 'Resume', 83: 'Episodes On Demand',
                            119: 'Now Airing', 120: 'Help & About', 133: 'Introduction', 134: 'Controls',
                            135: 'Network', 136: 'Welcome.'}.items():
            strings[index] = text
        art = SimpleNamespace(game_id=lambda: 'cod',
                              frame_scaled=lambda pack, index, k: pygame.Surface((4 * k, 4 * k), pygame.SRCALPHA))
        library = SimpleNamespace(shs_hd_resource=lambda rid: None)
        self.menu = CodPauseMenu(SimpleNamespace(library=library), art)
        for name, value in (('strings', lambda _self: strings),
                            ('font_path', lambda _self: pygame.font.match_font('arial', bold=True))):
            patcher = patch.object(CodPauseMenu, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.settings = dict(music=True, sound=False, music_volume=.5, sound_volume=.25, side_panels=True,
                             choice_hints=False, skip_minigames=True, skip_ad_intros=False)

    def buttons(self):
        return self.menu.layout(self.settings)[1]

    def test_pause_is_cod_menu_24_in_shs_hds_layout(self):
        import pygame
        from exp_runtime import desktop_pause_hd as hd
        self.assertTrue(self.menu.available())
        self.assertIsNone(self.menu.raw(17))
        buttons = self.buttons()
        self.assertEqual([c for _, c in buttons],
                         [('resume',), ('pause_open', 'options'), ('pause_open', 'help'), ('main_menu',)])
        # SHS HD's card: 112 + 4 x 88 + 86 points, centred in the 1024-point frame.
        top = (1024 - (hd.HEADER + 4 * hd.ROW + hd.FOOT)) / 2
        self.assertEqual(buttons[0][0], pygame.Rect(hd.PANEL_X, top + hd.HEADER, hd.PANEL_W, hd.ROW))

    def test_options_keeps_choice_hints_but_not_shs_only_switches_or_play_my_music(self):
        # CoD has no side panels, mini-games or ad intros; Play My Music is not listed (owner's choices).
        self.menu.state.screen = 'options:sound'
        self.assertEqual([c[:2] for _, c in self.buttons()],
                         [('pause_toggle', 'music'), ('pause_slider', 'music'), ('pause_toggle', 'sound'),
                          ('pause_slider', 'sound'), ('pause_back',)])
        self.menu.state.screen = 'options:general'
        self.assertEqual([c[:2] for _, c in self.buttons()], [('pause_toggle', 'choice_hints'), ('pause_back',)])

    def test_cods_sound_page_offers_vibration_too(self):
        self.menu.state.screen = 'options:sound'
        self.settings['vibration'] = True
        self.assertEqual([c[:2] for _, c in self.buttons()][0], ('pause_toggle', 'vibration'))

    def test_cods_style_over_hds_controls(self):
        # CoD's colours and art; the UIKit controls and the slider's track stay SHS HD's.
        from exp_runtime.desktop_pause_hd import HdPauseMenu
        self.assertEqual((self.menu.TITLE_COLOR, self.menu.LABEL_COLOR), ((0, 0, 0), (60, 60, 62)))
        self.assertEqual(self.menu.slider_value(143), 0)
        self.assertEqual(self.menu.slider_value(603), 1)
        self.assertEqual(self.menu.art(32, 13).get_size(), (4 * 2 * 2, 4 * 2 * 2))   # a 4-pixel 1x frame, 2 points a pixel, 2 layer pixels a point
        self.assertIs(type(self.menu).switch, HdPauseMenu.switch)

    def test_help_lists_cods_pages_and_back_steps_out(self):
        self.menu.state.screen = 'help'
        self.assertEqual([c for _, c in self.buttons()][:6],
                         [('pause_open', page) for page in ('intro', 'controls', 'airing', 'demand', 'network', 'about')])
        self.menu.state.screen = 'intro'
        self.assertIn(('pause_back',), [c for _, c in self.buttons()])
        self.assertEqual(self.menu.text_lines('intro'), ('Introduction', 'Welcome.'))
        self.assertFalse(self.menu.back())
        self.assertEqual(self.menu.state.screen, 'help')

    def test_push_notifications_is_cods_menu_6(self):
        # CoD's own page (IMG_0522): "Push Notifications" (235) and its text (237), not SHS HD's 238 / 240, which in
        # CoD's bank are the iOS permission prompt.
        self.assertEqual(self.menu.PAGES['push'], (235, 237))
        from exp_runtime.desktop_pause_hd import HdPauseMenu
        self.assertEqual(HdPauseMenu.PAGES['push'], (238, 240))

    def test_options_lists_the_hd_backdrop_switch_when_offered(self):
        self.menu.state.screen = 'options:general'
        self.settings['hd_backdrop'] = True
        self.assertIn(('pause_toggle', 'hd_backdrop'), [c[:2] for _, c in self.buttons()])

    def test_cods_own_overrides_and_version_token(self):
        from exp_runtime import desktop_cod_pause, help_text_overrides
        # Now Airing / On Demand describe this player's library, adapted to CoD; About keeps CoD's text, whose version
        # token is ~259~ (SHS HD's ~276~).
        title, body = self.menu.text_lines('airing')
        self.assertEqual(title, 'Now Airing')
        self.assertIn('Cause of Death Facebook page', body)
        self.assertNotIn('SD', self.menu.text_lines('demand')[1].split())
        # The owner's About keeps the disclaimer, credits and a link; without it, CoD's own page is shown.
        about = self.menu.text_lines('about')[1]
        self.assertIn('unofficial fan preservation project', about)
        self.assertIn(f'Version: {desktop_cod_pause.VERSION}', about)
        self.menu.strings()[0] = 'Version: ~259~'
        overrides = {k: v for k, v in help_text_overrides.COD_HELP_TEXT_OVERRIDES.items() if k != 'about'}
        with patch.dict(help_text_overrides.COD_HELP_TEXT_OVERRIDES, overrides, clear=True):
            self.assertEqual(self.menu.text_lines('about'), ('About', f'Version: {desktop_cod_pause.VERSION}'))
        with patch.dict(help_text_overrides.COD_HELP_TEXT_OVERRIDES, about=('About', 'Credits ~259~ https://x.test')):
            self.assertEqual(self.menu.text_lines('about')[1], f'Credits {desktop_cod_pause.VERSION} https://x.test')
            self.menu.state.screen = 'about'
            self.assertIn(('pause_link', 'https://x.test'), [c for _, c in self.buttons()])

if __name__ == '__main__':
    unittest.main()


class HelpLinkTests(unittest.TestCase):
    """[label](url) and bare URLs in Help & About override text (desktop_pause_hd.link_words)."""

    def test_labelled_and_bare_links_and_double_spaces(self):
        from exp_runtime.desktop_pause_hd import link_words
        words = link_words('Based on the original [exp-runtime](https://example.com/a) by Josh')
        self.assertEqual(words[4], [('exp-runtime', 'https://example.com/a')])
        self.assertEqual(words[5], [('by', None)])
        self.assertEqual(link_words('Join: https://discord.gg/x')[1], [('https://discord.gg/x', 'https://discord.gg/x')])
        self.assertEqual(link_words('Written by  Paul'), [[('Written', None)], [('by', None)], [], [('Paul', None)]])
        self.assertEqual(link_words('[two words](https://e.com/b).')[1], [('words', 'https://e.com/b'), ('.', None)])

    def test_both_about_pages_link_both_projects(self):
        from exp_runtime.help_text_overrides import COD_HELP_TEXT_OVERRIDES, HELP_TEXT_OVERRIDES
        for overrides in (HELP_TEXT_OVERRIDES, COD_HELP_TEXT_OVERRIDES):
            body = overrides['about'][1]
            self.assertIn('[shshd-runtime](https://github.com/1timewire1/shshd-runtime)', body)
            self.assertIn('[exp-runtime](https://github.com/joshrmcdaniel/exp-runtime)', body)
            self.assertNotIn('shs-runtime by', body)
        self.assertIn('[Surviving High School Community Discord](https://discord.gg/reJT83aAeD)',
                      HELP_TEXT_OVERRIDES['about'][1])
        self.assertIn('[Cause of Death Discord](https://discord.gg/NdCru4Vz3q)', COD_HELP_TEXT_OVERRIDES['about'][1])
