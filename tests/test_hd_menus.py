from io import BytesIO
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest

import pygame

from exp_runtime.application_hd import HdShell, MISS_MENU, END_MENU
from exp_runtime.desktop_boot_hd import FLASH_TOTAL, HdBootScreen
from exp_runtime.desktop_hd_menu import BUTTON_STRIP, CARD_W, FOOTER_HEIGHT, HdMenuWindows, ROW_HEIGHT
from exp_runtime.desktop_main_hd import (BUTTONS_START_INTRO, GEAR_DELAY, HdMainMenu, INFO_FADE, LEAVE_TIME,
                                         OUT_DELAYS, READY_AFTER, SLIDE_FROM, SLIDE_OVERSHOOT, SLIDE_TIME, STAGGER,
                                         keyframes, layer_progress)
from exp_runtime.menu import MenuFont, MenuState
from exp_runtime.menu_engine import (BACK, CLEAR, ENGINE, QUEUE, MenuEngineData, MenuEngineError, MenuStack)

NO = 0xffff


def bank(*texts):
    """A string bank (the layout `MenuStrings.parse` reads)."""
    body = b''.join(t.encode('latin-1') + b'\0' for t in texts)
    start = 9 + 2 * len(texts)
    offsets, position = [], start
    for t in texts:
        offsets.append(position)
        position += len(t.encode('latin-1')) + 1
    return struct.pack('>iBhh', 1, 0, 0, len(texts)) + b''.join(struct.pack('>h', o) for o in offsets) + body


def engine_data(menus, actions):
    """Menu engine bytes: `menus` are (title, message, style, items), `actions` are (label, flags, steps)."""
    records = []
    table = 2 * len(menus)
    blob = bytearray()
    offsets = []
    for title, message, style, items in menus:
        offsets.append(table + len(blob))
        header = struct.pack('>HH', title, message) + b'\xff' * 8 + bytes([style, 0x14, 0x15, len(items)])
        blob += header + b''.join(struct.pack('>H', i) for i in items)
    action_table = table + len(blob)
    blob += b'\0' * (2 * len(actions))
    for index, (label, flags, steps) in enumerate(actions):
        struct.pack_into('>H', blob, action_table - table + 2 * index, table + len(blob))
        blob += struct.pack('>H', label) + bytes(flags) + bytes([len(steps)]) + b''.join(
            bytes([kind]) + struct.pack('>H', arg) for kind, arg in steps)
    head = b''.join(struct.pack('>H', o) for o in offsets)
    data = head + bytes(blob)
    return bytes([len(menus), len(menus) * 2]) + struct.pack('>HH', action_table, len(data)) + data


STRINGS = bank('zero', 'Title', 'A message', 'Yes', 'No', 'Back', 'Row one', 'Row two', 'OK', 'Play with sound?',
               'x' * 3)


class MenuEngineTests(unittest.TestCase):
    def setUp(self):
        menus = [(1, NO, 2, (0, 1)),                        # an alert: No / Yes
                 (1, NO, 7, (2, 3, 4)),                     # a list with a footer button
                 (1, 2, 0xff, (5,))]                        # an info page
        actions = [(4, (0xff, 0xff), [(ENGINE, 0), (ENGINE, 1)]),
                   (3, (0xff, 0xff), [(ENGINE, 2), (ENGINE, 1)]),
                   (6, (0xff, 0xff), [(QUEUE, 0)]),
                   (7, (0xff, 0xff), [(BACK, 0xffff)]),
                   (5, (1, 0xff), [(BACK, 0xffff)]),
                   (0, (0xfb, 0xff), [(BACK, 0xffff)])]
        self.data = MenuEngineData(engine_data(menus, actions))

    def test_menus_and_actions_are_read_back(self):
        self.assertEqual(len(self.data.menus), 3)
        menu = self.data.menu(1)
        self.assertEqual((menu.title, menu.message, menu.style, menu.layouts), (1, NO, 7, (0x14, 0x15)))
        self.assertEqual([a.label for a in self.data.items(1)], [6, 7, 5])
        self.assertTrue(self.data.action(4).is_footer_button)
        self.assertFalse(self.data.action(2).is_footer_button)
        self.assertEqual(self.data.action(0).steps, ((ENGINE, 0), (ENGINE, 1)))
        self.assertTrue(self.data.menu(2).is_form)
        self.assertFalse(self.data.menu(1).is_form)

    def test_bad_data_is_rejected(self):
        with self.assertRaises(MenuEngineError):
            MenuEngineData(b'\x01\x02')
        with self.assertRaises(MenuEngineError):
            MenuEngineData(bytes([9, 18]) + struct.pack('>HH', 0, 4) + b'\0' * 4)
        with self.assertRaises(MenuEngineError):
            self.data.menu(9)

    def test_stack_runs_an_items_steps_in_order(self):
        seen = []
        stack = MenuStack(self.data, seen.append)
        stack.queue(0)
        stack.press(self.data.action(1))
        self.assertEqual(seen, [2, 1])
        stack.queue(1)
        stack.press(self.data.action(2))            # queue menu 0 over menu 1
        self.assertEqual(stack.stack, [0, 1, 0])
        stack.press(self.data.action(3))            # go back
        self.assertEqual(stack.stack, [0, 1])
        stack.back_to(0)
        self.assertEqual(stack.stack, [0])
        stack.queue(1)
        stack.clear()
        self.assertIsNone(stack.current)
        with self.assertRaises(MenuEngineError):
            stack.queue(50)


class FakeLibrary:
    hd_ipa = None

    def hd_raw_resource(self, resource_id):
        return STRINGS if resource_id == 15 else None


class WindowLayoutTests(unittest.TestCase):
    def setUp(self):
        pygame.display.init()
        pygame.display.set_mode((1, 1))
        menus = ([(9, NO, 2, (0, 1)), (1, 2, 7, (2, 3, 4)), (1, 2, 0xff, (5,)), (1, NO, 6, (2, 3, 4))]
                 + [(1, NO, 6, (2,))] * 3 + [(1, 2, 0xff, (5,))])
        actions = [(4, (0xff, 0xff), []), (3, (0xff, 0xff), []), (6, (0xff, 0xff), []), (7, (0xff, 0xff), []),
                   (3, (1, 0xff), [(BACK, 0xffff)]), (3, (0xfb, 0xff), [(BACK, 0xffff)])]
        self.windows = HdMenuWindows(FakeLibrary(), MenuEngineData(engine_data(menus, actions)), None)

    def test_an_alert_is_a_title_and_a_button_strip_centered_on_the_frame(self):
        g = self.windows.layout(0)
        self.assertEqual(g['kind'], 'alert')
        self.assertEqual(g['rows'], [])
        self.assertAlmostEqual(g['total'], g['header'] + BUTTON_STRIP)
        self.assertAlmostEqual(g['top'] * 2 + g['total'], 1024)
        self.assertAlmostEqual(g['header'], 58 + 53.7)                  # a one-line title: 111.7

    def test_a_list_has_88_point_rows_a_footer_button_and_a_message_in_the_header(self):
        g = self.windows.layout(1)
        self.assertEqual(g['kind'], 'list')
        self.assertEqual([r.height for r in g['rows']], [ROW_HEIGHT, ROW_HEIGHT])          # the footer item is not a row
        self.assertEqual(g['footer'].label, 3)
        self.assertEqual(len(g['message']), 1)
        self.assertGreater(g['header'], 58 + 53.7)
        self.assertAlmostEqual(g['total'], g['header'] + 2 * ROW_HEIGHT + FOOTER_HEIGHT)
        self.assertEqual(g['rows'][1].top, g['rows'][0].top + ROW_HEIGHT)

    def test_info_pages_and_notices(self):
        self.assertEqual(self.windows.layout(2)['kind'], 'form')              # menus 0-6 with no style are info pages
        self.assertEqual(self.windows.layout(7)['kind'], 'notice')            # later ones are alerts with one OK button
        self.assertEqual(self.windows.kind_of(self.windows.data.menu(3)), 'list')

    def test_switch_game_rows_carry_the_other_games_title(self):
        switch = SimpleNamespace(label=3, steps=((ENGINE, 23),))
        other = SimpleNamespace(label=1, steps=((ENGINE, 21),))
        self.assertEqual(self.windows.item_label(switch, None), '')                 # native until a title is set
        self.windows.switch_title = 'Cause of Death'
        self.assertEqual(self.windows.item_label(switch, None), 'Cause of Death')
        self.assertEqual(self.windows.item_label(other, None), 'Title')

    def test_text_substitution(self):
        self.assertEqual(self.windows.text_for(1), 'Title')
        self.assertEqual(self.windows.text_for(NO), '')
        self.assertEqual(self.windows.item_label(self.windows.data.action(4), None), '')          # string 3 is not empty here
        self.assertEqual(CARD_W, 604)


class MainMenuTimingTests(unittest.TestCase):
    def setUp(self):
        pygame.display.init()
        pygame.display.set_mode((1, 1))
        self.menu = HdMainMenu(FakeLibrary())

    def test_the_switch_button_shortens_a_title_too_wide_for_it(self):
        widths = {'Cause of Death': 297, 'Surviving High School': 455}       # the green label font, in points
        self.menu.label = lambda text, variant: pygame.Surface((widths[text] * 2, 2))
        self.menu.switch_title = 'Cause of Death'
        self.assertEqual(self.menu.switch_text(), 'Cause of Death')          # 297 of the 298 points free
        self.menu.switch_title = 'Surviving High School'
        self.assertEqual(self.menu.switch_text(), 'Surviving HS')

    def test_keyframes_interpolate_and_hold_the_ends(self):
        self.assertEqual(keyframes((0, .5, 1), (0., 10., 0.), -1), 0.)
        self.assertAlmostEqual(keyframes((0, .5, 1), (0., 10., 0.), .25), 5.)
        self.assertAlmostEqual(keyframes((0, .5, 1), (0., 10., 0.), .75), 5.)
        self.assertEqual(keyframes((0, .5, 1), (0., 10., 0.), 2), 0.)

    def test_the_intro_delays_the_buttons_and_input_opens_after_the_last_slide(self):
        self.assertEqual(BUTTONS_START_INTRO, 1.5)                # animateMainMenuButtonsIn(1.5), both games
        self.menu.start(intro=True)
        self.assertEqual(self.menu.buttons_start, BUTTONS_START_INTRO)
        self.assertFalse(self.menu.ready)
        self.menu.tick(BUTTONS_START_INTRO + READY_AFTER - .01)
        self.assertFalse(self.menu.ready)
        self.menu.tick(.02)
        self.assertTrue(self.menu.ready)
        self.menu.start(intro=False)
        self.assertEqual(self.menu.buttons_start, 0)
        self.menu.tick(READY_AFTER + .01)
        self.assertTrue(self.menu.ready)

    def test_cods_buttons_start_under_its_fade_from_black_on_the_first_arrival(self):
        from exp_runtime.desktop_cod_main import CodMainMenu
        menu = object.__new__(CodMainMenu)
        menu.start(intro=True)
        self.assertEqual(menu.buttons_start, 1.5)
        menu.start(intro=False)
        self.assertEqual(menu.buttons_start, 0.0)

    def test_each_layer_holds_its_delay_twice_then_moves_for_0_35_s(self):
        # createMainMenuAnimationInForLayer: begins at the delay, lasts delay + 0.35 s, holds until key time d / D.
        for delay in (0.0, .08, 1.5):
            progress, hold = layer_progress(delay, delay)
            self.assertEqual((progress, hold), (0.0, delay / (delay + SLIDE_TIME)))
            self.assertAlmostEqual(layer_progress(2 * delay, delay)[0], hold)
            self.assertEqual(layer_progress(2 * delay + SLIDE_TIME, delay)[0], 1.0)

    def test_buttons_slide_in_from_the_left_016_s_apart_with_a_small_overshoot(self):
        self.menu.start(intro=False)
        self.assertEqual([self.menu.slide(i) for i in range(5)], [SLIDE_FROM] * 5)
        self.menu.tick(2 * STAGGER + .01)                         # the wedge and Play/Resume are moving, not Now Airing
        offsets = [self.menu.slide(i) for i in range(5)]
        self.assertGreater(offsets[0], offsets[1])
        self.assertGreater(offsets[1], SLIDE_FROM)
        self.assertEqual(offsets[2:], [SLIDE_FROM] * 3)
        self.menu.tick(.96 * SLIDE_TIME - 2 * STAGGER - .01)
        self.assertAlmostEqual(self.menu.slide(0), SLIDE_OVERSHOOT, places=3)
        self.menu.tick(1)
        self.assertEqual([self.menu.slide(i) for i in range(5)], [0.0] * 5)
        self.assertEqual((self.menu.pop(), self.menu.info_alpha()), (1.0, 1.0))

    def test_the_gear_pops_in_past_full_size_and_the_info_button_fades_in(self):
        # The gear grows and the info button fades, as on the iPad (owner, 2026-10-20).
        self.menu.start(intro=False)
        self.assertEqual((self.menu.pop(), self.menu.info_alpha()), (0.01, 0.0))
        self.menu.tick(.32 + INFO_FADE / 2)
        self.assertAlmostEqual(self.menu.info_alpha(), .5)
        self.menu.tick(GEAR_DELAY + .96 * (GEAR_DELAY + SLIDE_TIME) - .32 - INFO_FADE / 2)   # key time .96 of d + .35
        self.assertAlmostEqual(self.menu.pop(), 1.2, places=2)

    def test_taking_an_option_slides_the_buttons_out_in_reverse_and_closes_input(self):
        self.menu.start(intro=False)
        self.menu.tick(READY_AFTER + .01)
        self.assertTrue(self.menu.ready)
        self.menu.leave()
        self.assertFalse(self.menu.ready)
        self.assertEqual([self.menu.slide(i) for i in range(5)], [0.0] * 5)
        self.menu.tick(2 * OUT_DELAYS[4] + .02)                   # More EA Games (last in) goes first: a nudge right
        self.assertGreater(self.menu.slide(4), 0.0)
        self.assertEqual(self.menu.slide(0), 0.0)
        self.assertLess(self.menu.pop(), 1.0)
        self.menu.tick(LEAVE_TIME)
        self.assertTrue(self.menu.left)
        self.assertEqual(([self.menu.slide(i) for i in range(5)], self.menu.pop(), self.menu.info_alpha()),
                         ([SLIDE_FROM] * 5, 0.0, 0.0))
        self.menu.start(intro=False)                              # back on the main menu: in again
        self.assertIsNone(self.menu.leaving)


class PickerOverMenuTests(unittest.TestCase):
    def test_a_picker_draws_over_the_live_menu_until_the_buttons_have_gone(self):
        from exp_runtime.application import Application
        from exp_runtime.desktop_main_hd import LEAVE_TIME
        from exp_runtime.desktop_pause import PAUSE_OPEN_MS
        app = Application.__new__(Application)
        main = HdMainMenu.__new__(HdMainMenu)
        main.start(intro=False)
        main.leave()
        app.shell, app.screen, app.picker_zoom = SimpleNamespace(main=main), 'picker', 0
        self.assertTrue(app.picker_over_menu())
        app.picker_zoom = PAUSE_OPEN_MS
        self.assertTrue(app.picker_over_menu())                 # zoomed in, the buttons still sliding out
        main.tick(LEAVE_TIME)
        self.assertFalse(app.picker_over_menu())
        app.shell = None
        self.assertFalse(app.picker_over_menu())

    def test_without_its_backdrop_a_picker_starts_from_a_see_through_dim(self):
        import pygame
        from exp_runtime.desktop_episode_picker import BACKDROP_DIM_ALPHA, HdEpisodePicker
        if pygame.display.get_surface() is None:
            pygame.display.init()
            pygame.display.set_mode((1, 1))
        picker = HdEpisodePicker.__new__(HdEpisodePicker)
        picker.canvas = pygame.Surface((40, 30)).convert()
        layer = picker.begin_layer(False)
        self.assertEqual(layer.get_at((5, 5)), (0, 0, 0, BACKDROP_DIM_ALPHA))
        self.assertIsNot(layer, picker.canvas)


class EpisodeListCardTests(unittest.TestCase):
    def test_with_a_menu_card_the_list_scrolls_inside_a_tall_card_like_a_text_page(self):
        from exp_runtime.desktop_episode_list_hd import HdEpisodeList
        from exp_runtime.desktop_pause_hd import BORDER, FOOT, HEADER, PANEL_W, PANEL_X, TALL
        picker = HdEpisodeList.__new__(HdEpisodeList)
        picker.model = SimpleNamespace(chronological=True)
        picker.strings = lambda: {83: 'Episodes On Demand', 119: 'Now Airing'}
        picker.card = SimpleNamespace(title_lines=lambda text: text.split(' ', 2)[:2] if len(text) > 12 else [text])
        area = picker.list_area()
        self.assertEqual((area.x, area.width), (PANEL_X + BORDER, PANEL_W - 2 * BORDER))
        self.assertEqual((area.top, area.bottom), (TALL[0] + HEADER + 1, TALL[1] - FOOT))
        picker.model.chronological = False                      # "Episodes On Demand" wraps: a taller header
        self.assertEqual(picker.list_area().top, TALL[0] + HEADER + 40 + 1)
        self.assertEqual(picker.list_height(), picker.list_area().height)

    def test_the_lists_layer_is_undimmed_and_see_through_when_zooming(self):
        import pygame
        from exp_runtime.desktop_episode_picker import HdEpisodePicker
        if pygame.display.get_surface() is None:
            pygame.display.init()
            pygame.display.set_mode((1, 1))
        picker = HdEpisodePicker.__new__(HdEpisodePicker)
        picker.canvas = pygame.Surface((40, 30)).convert()
        self.assertEqual(picker.begin_layer(False, dim=False).get_at((5, 5)), (0, 0, 0, 0))


class BootTests(unittest.TestCase):
    def test_the_flash_lasts_its_delay_plus_its_fade(self):
        self.assertAlmostEqual(FLASH_TOTAL, 0.6)
        self.assertFalse(HdBootScreen.flash_done(.5))
        self.assertTrue(HdBootScreen.flash_done(.61))


class StubApp:
    def __init__(self, state):
        self.state, self.played, self.urls, self.left, self.opened = state, [], [], [], []
        self.commands = []

    def command(self, command):
        self.commands.append(command)

    def play_asset(self, asset_id):
        self.played.append(asset_id)

    def menu_music_changed(self, *, switched=False):
        self.music_changes = getattr(self, 'music_changes', 0) + 1
        self.music_switched = switched

    def open_url(self, url):
        self.urls.append(url)

    def leave_end_menu(self, **options):
        self.left.append(options)

    def open_picker(self, **options):
        self.opened.append(options)


class ShellActionTests(unittest.TestCase):
    """`HdShell.perform`: the engine actions the menus run, on authored menu data."""
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        state = SimpleNamespace(music=True, sound=True, logging_disabled=False, persisted=0)
        state.persist = lambda: setattr(state, 'persisted', state.persisted + 1)
        menus = [(1, NO, 2, ()), (1, NO, 2, ())] + [(1, NO, 2, ())] * 30
        self.shell = object.__new__(HdShell)
        self.shell.app = StubApp(state)
        self.shell.data = MenuEngineData(engine_data(menus, [(1, (0, 0), [])]))
        self.shell.stack = MenuStack(self.shell.data, self.shell.perform)
        self.shell.windows = SimpleNamespace(strings=lambda: {203: 'terms', 204: 'eula', 205: 'privacy'})
        self.shell.stage, self.shell.flash_age, self.shell.link = 'sound', 5.0, ''
        self.shell.pending_yes = None
        self.shell.pending_title = ''

    def test_no_and_yes_set_the_options_then_start_the_flash(self):
        shell, state = self.shell, self.shell.app.state
        shell.stack.queue(0)
        shell.perform(0)
        self.assertEqual((state.music, state.sound), (False, False))
        shell.perform(1)
        self.assertEqual((shell.stage, shell.flash_age, shell.stack.stack), ('flash', 0.0, []))
        self.assertEqual(shell.app.played, [8005])
        shell.perform(2)
        self.assertEqual((state.music, state.sound), (True, True))
        shell.perform(4)                                    # keep another app's music
        self.assertEqual((state.music, state.sound), (False, True))
        self.assertGreaterEqual(state.persisted, 3)

    def test_the_in_game_pause_box_zooms_out_over_the_first_entrance_without_the_flash(self):
        # On the device the Main Menu row skips the EA flash and its jingle: the entrance runs from the photo on.
        import pygame
        from exp_runtime.desktop_pause import pause_scale
        shell, entered = self.shell, []
        shell.stage, shell.pause_open, shell.age = 'main', False, 0.0
        shell.boot = HdBootScreen.__new__(HdBootScreen)
        shell.pause = SimpleNamespace(advance=lambda ms: None, reset=lambda: None)
        shell.main = SimpleNamespace(tick=lambda seconds: None, start=lambda intro: entered.append(intro),
                                     hits=[('rect', ('play',))], ready=True)
        box = pygame.Surface((320, 480), pygame.SRCALPHA)
        shell.zoom_out(box)
        self.assertEqual(shell.leaving[0].get_size(), (1536, 2048))
        self.assertEqual((shell.stage, shell.app.played, entered), ('main', [], [True]))
        self.assertEqual(shell.hits(), [])                           # nothing takes input until it has gone
        shell.tick(.25)
        self.assertLess(pause_scale(400 - shell.leaving[1]), 1)
        shell.tick(.2)
        self.assertIsNone(shell.leaving)
        self.assertEqual(shell.hits(), [('rect', ('play',))])

    def test_links_are_remembered_then_opened_on_confirmation(self):
        shell = self.shell
        for number, link in ((14, 'eula'), (15, 'privacy'), (16, 'terms')):
            shell.perform(number)
            self.assertEqual(shell.link, link)
        shell.stack.queue(17)
        shell.perform(18)
        self.assertEqual((shell.app.urls, shell.stack.stack), (['terms'], []))

    def test_usage_sharing_switch_and_its_confirmations(self):
        shell, state = self.shell, self.shell.app.state
        shell.perform(17)
        self.assertEqual(shell.stack.stack, [19])                   # "Disable Usage Sharing" first
        shell.perform(19)
        self.assertTrue(state.logging_disabled)
        shell.stack.clear()
        shell.perform(17)
        self.assertEqual(shell.stack.stack, [20])
        shell.perform(20)
        self.assertFalse(state.logging_disabled)

    def test_end_menu_actions_leave_it_for_the_picker_the_main_menu_or_a_replay(self):
        shell = self.shell
        shell.perform(21)                                            # Now Airing -> the chronological list
        shell.perform(22)                                            # Episodes On Demand -> the category list
        shell.perform(24)
        shell.perform(25)
        self.assertEqual(shell.app.left, [dict(picker=True, style='airing'), dict(picker=True, style='list'),
                                          {}, dict(replay=True)])

    def test_a_pause_link_reuses_the_same_exit_game_confirmation_as_the_legal_rows(self):
        shell = self.shell
        shell.activate(('pause_link', 'https://discord.gg/example'))
        self.assertEqual((shell.link, shell.stack.stack), ('https://discord.gg/example', [17]))
        shell.perform(18)
        self.assertEqual((shell.app.urls, shell.stack.stack), (['https://discord.gg/example'], []))

    def test_leave_fades_to_black_then_calls_back_and_takes_no_input_meanwhile(self):
        from exp_runtime.application_hd import FADE_TIME, HITCH, MAX_STEP
        shell, calls = self.shell, []
        shell.fade, shell.pause_open, shell.pressed, shell.drag, shell.age = None, False, None, None, 0.0
        shell.main = SimpleNamespace(tick=lambda seconds: None, ready=True, hits=[('rect', ('play',))])
        shell.stage = 'main'
        shell.leave(lambda: calls.append('black'))
        self.assertEqual((shell.hits(), shell.fade_level()), ([], 0.0))
        shell.tick(HITCH + .2)                              # one long frame (a library opening) moves it one step
        self.assertEqual(shell.fade_level(), MAX_STEP / FADE_TIME)
        shell.tick(.15)                                     # an ordinary slow frame counts in full
        self.assertAlmostEqual(shell.fade_level(), (MAX_STEP + .15) / FADE_TIME)
        while shell.fade is not None:
            shell.tick(MAX_STEP)
        self.assertEqual(calls, ['black'])

    def test_the_sound_question_zooms_in_like_the_pause_menu_and_takes_input_once_open(self):
        from exp_runtime.application_hd import LOADING_TIME, SOUND_DELAY
        from exp_runtime.desktop_pause import PAUSE_OPEN_MS
        shell, drawn = self.shell, []
        shell.app.update_holds_launch = lambda seconds: False
        shell.app.external_music = lambda: False

        def draw(layer, menu_id, **_):
            drawn.append(layer)
            pygame.draw.rect(layer, (255, 0, 0), (40, 40, 20, 20))
            shell.windows.hits = [('rect', ('item', 0))]
        shell.windows.draw, shell.windows.hits = draw, []
        shell.fade, shell.pause_open, shell.pressed, shell.body_scroll = None, False, None, 0
        shell.variables, shell.stage, shell.age = (lambda: {}), 'loading', LOADING_TIME + SOUND_DELAY
        canvas = pygame.Surface((100, 100))
        shell.tick(0)                                       # the launch asks "Play with sound?"
        self.assertEqual(shell.stack.stack, [7])
        shell.draw_overlay(canvas)
        self.assertIsNot(drawn[-1], canvas)                 # drawn apart, then scaled from nothing
        self.assertEqual(canvas.get_at((50, 50))[:3], (0, 0, 0))
        self.assertEqual(shell.hits(), [])
        shell.tick(PAUSE_OPEN_MS / 2000)
        shell.draw_overlay(canvas)
        self.assertEqual(shell.hits(), [])
        shell.tick(PAUSE_OPEN_MS / 2000)
        shell.draw_overlay(canvas)
        self.assertIs(drawn[-1], canvas)                    # full size: drawn straight onto the frame
        self.assertEqual(shell.hits(), [('rect', ('item', 0))])
        shell.stack.queue(17)                               # any other window appears at once
        shell.draw_overlay(canvas)
        self.assertIs(drawn[-1], canvas)

    def test_the_fade_darkens_a_canvas_whose_pixels_carry_alpha_zero(self):
        canvas = pygame.Surface((4, 4), 0, 32, (0xff0000, 0xff00, 0xff, 0xff000000))
        canvas.fill((200, 100, 50, 0))
        self.shell.fade = ('in', .5, None, 1.0)
        self.shell.draw_fade(canvas)
        self.assertEqual(tuple(canvas.get_at((0, 0)))[:3], (100, 50, 25))

    def test_arriving_from_another_game_flashes_from_black_with_the_jingle(self):
        from exp_runtime.desktop_boot_hd import JINGLE
        shell = self.shell
        shell.fade, shell.pause_open, shell.flash_over_black = None, False, False
        shell.arrive()
        self.assertEqual((shell.stage, shell.flash_over_black, shell.app.played), ('flash', True, [JINGLE]))
        self.assertEqual(shell.fade_level(), 0.0)                        # the frame only: the backdrop never fades

    def test_episode_titles_step_through_the_languages_and_add_episodes_browses(self):
        shell, state = self.shell, self.shell.app.state
        state.title_language = 'es'
        shell.app.picker = 'stale'
        shell.activate(('pause_cycle', 'title_language'))
        self.assertEqual((state.title_language, shell.app.picker), ('en', None))      # wraps; captions rebuild
        self.assertGreaterEqual(state.persisted, 1)
        shell.activate(('pause_action', 'add_episodes'))
        self.assertEqual(shell.app.commands[-1], ('browse', 'episodes'))

    def test_more_ea_games_switches_games_from_the_main_menu_and_the_end_menus(self):
        shell = self.shell
        shell.activate(('more',))
        shell.stack.queue(23)
        shell.perform(23)
        self.assertEqual((shell.app.commands, shell.stack.stack), ([('switch_games',), ('switch_games',)], []))

    def test_main_menu_buttons_open_the_picker_in_the_right_style(self):
        shell = self.shell
        shell.activate(('play',))
        shell.activate(('airing',))
        shell.activate(('demand',))
        self.assertEqual(shell.app.opened, [dict(restore=True, style='tile'), dict(restore=False, style='airing'),
                                            dict(restore=False, style='list')])

    def test_new_game_over_a_save_waits_for_yes(self):
        shell, calls = self.shell, []
        shell.confirm_new_game('Some Episode', lambda: calls.append('started'))
        self.assertEqual((shell.stack.stack, shell.pending_title), ([12], 'Some Episode'))
        shell.perform(10)
        self.assertEqual((calls, shell.stack.stack), (['started'], []))
        shell.perform(10)                                           # nothing pending: nothing happens
        self.assertEqual(calls, ['started'])


class CodShellActionTests(unittest.TestCase):
    """`CodShell.perform`: CoD's engine action numbers translated onto HdShell's (application_cod.py)."""
    def setUp(self):
        from exp_runtime.application_cod import CodShell
        state = SimpleNamespace(music=True, sound=True, logging_disabled=False, persisted=0)
        state.persist = lambda: setattr(state, 'persisted', state.persisted + 1)
        app = StubApp(state)
        app.commands = []
        app.command = app.commands.append
        app.picker_available = lambda: self.pickers
        self.pickers = False
        self.shell = object.__new__(CodShell)
        self.shell.app = app
        self.shell.data = MenuEngineData(engine_data([(1, NO, 2, ())] * 60, [(1, (0, 0), [])]))
        self.shell.stack = MenuStack(self.shell.data, self.shell.perform)
        self.shell.windows = SimpleNamespace(strings=lambda: {200: 'terms', 201: 'eula', 202: 'privacy'})
        self.shell.stage, self.shell.flash_age, self.shell.link = 'sound', 5.0, ''
        self.shell.pending_yes, self.shell.pending_title = None, ''
        self.entered = []
        self.shell.enter_main = lambda **options: self.entered.append(options)
        self.shell.fade, self.shell.pause_open, self.shell.pressed, self.shell.drag = None, False, None, None

    def test_the_pause_box_zooms_out_over_cods_menu_without_a_flash(self):
        import pygame
        shell = self.shell
        shell.stage = 'main'
        shell.zoom_out(pygame.Surface((320, 480), pygame.SRCALPHA))
        self.assertEqual((shell.stage, shell.app.played), ('main', []))
        self.assertIsNotNone(shell.leaving)

    def test_the_sound_answer_goes_straight_to_the_main_menu(self):
        shell, state = self.shell, self.shell.app.state
        shell.stack.queue(7)
        shell.perform(0)
        shell.perform(1)
        self.assertEqual((state.music, state.sound), (False, False))
        self.assertEqual((self.entered, shell.stack.stack, shell.app.played, shell.fade[0]), ([], [], [], 'out'))
        shell.fade[2]()                                     # once black: the menu, fading in (no EA flash, no jingle)
        self.assertEqual((self.entered, shell.fade[0]), ([dict(intro=True)], 'in'))

    def test_the_ea_screen_holds_then_goes_black_and_the_menu_slowly_fades_in(self):
        shell, step, clock, seen = self.shell, .01, 0.0, {}
        shell.age, shell.stage = 0.0, 'menu'               # no launch stage to advance in this test
        shell.main = SimpleNamespace(tick=lambda seconds: None)
        shell.perform(1)
        while clock < 3.3:
            seen[round(clock, 2)] = (shell.fade_level(), len(self.entered))
            shell.tick(step)
            clock += step
        self.assertEqual(seen[.9], (0.0, 0))               # the EA screen stays
        self.assertAlmostEqual(seen[1.5][0], .5, places=1)
        self.assertEqual(seen[2.05], (1.0, 1))              # black, with the menu set up under it
        self.assertAlmostEqual(seen[2.7][0], .5, places=1)
        self.assertEqual(seen[3.25][0], 0.0)
        self.assertIsNone(shell.fade)

    def test_legal_links_use_cods_strings_and_exit_game_window(self):
        shell = self.shell
        for number, link in ((21, 'eula'), (22, 'privacy'), (23, 'terms')):
            shell.perform(number)
            self.assertEqual(shell.link, link)
        shell.activate(('pause_link', 'https://discord.gg/example'))
        self.assertEqual(shell.stack.stack, [16])
        shell.perform(24)
        self.assertEqual((shell.app.urls, shell.stack.stack), (['https://discord.gg/example'], []))

    def test_usage_sharing_delete_save_and_more(self):
        shell, state, calls = self.shell, self.shell.app.state, []
        shell.perform(26)
        self.assertTrue(state.logging_disabled)
        shell.perform(27)
        self.assertFalse(state.logging_disabled)
        shell.confirm_new_game('Some Case', lambda: calls.append('started'))
        self.assertEqual((shell.stack.stack, shell.variables()), ([52], {'260': 'Some Case'}))
        shell.perform(36)
        self.assertEqual((calls, shell.stack.stack), (['started'], []))
        shell.activate(('more',))                          # More EA Games is Switch Game
        self.assertEqual((shell.stack.stack, shell.app.commands[-1]), ([], ('switch_games',)))
        shell.stack.queue(38)
        shell.perform(25)
        self.assertEqual(shell.stack.stack, [])
        shell.stack.queue(22)
        shell.stage = 'end'
        shell.perform(30)                                   # the end menu's row too
        self.assertEqual((shell.stack.stack, shell.app.commands[-1]), ([], ('switch_games',)))

    def test_with_the_art_source_the_buttons_open_shs_hds_pickers(self):
        shell, self.pickers = self.shell, True
        for kind in ('play', 'airing', 'demand'):
            shell.activate((kind,))
        self.assertEqual(shell.app.opened, [dict(restore=True, style='tile'), dict(restore=False, style='airing'),
                                            dict(restore=False, style='list')])
        shell.stage = 'end'
        shell.perform(28)
        shell.perform(29)
        self.assertEqual(shell.app.left, [dict(picker=True, style='airing'), dict(picker=True, style='list')])
        self.assertEqual(shell.app.commands, [])

    def test_main_and_end_menu_buttons(self):
        shell = self.shell                                  # no SHS HD art source: the plain episode browser
        for kind in ('play', 'airing', 'demand'):
            shell.activate((kind,))
        self.assertEqual(shell.app.commands, [('episodes', 'play'), ('episodes', 'weekly'), ('episodes', 'all')])
        shell.stack.queue(22)
        shell.perform(31)                                   # Main Menu outside the end menu only closes
        self.assertEqual((shell.stack.stack, shell.app.left), ([], []))
        shell.stage = 'end'
        shell.perform(31)
        shell.perform(32)
        shell.perform(29)
        self.assertEqual(shell.app.left, [{}, dict(replay=True), {}])
        self.assertEqual(shell.app.commands[-1], ('episodes', 'all'))

    def test_a_shell_built_by_its_own_constructor_starts_without_a_fade(self):
        # CodShell does not run HdShell.__init__; launching straight into CoD must not trip over the fade state.
        from exp_runtime.application_cod import CodShell
        shell = object.__new__(CodShell)
        self.assertEqual((shell.fade, shell.flash_over_black, shell.fade_level()), (None, False, 0.0))

    def test_only_a_complete_cod_library_gets_the_shell(self):
        from exp_runtime.application_cod import CodShell
        self.assertFalse(CodShell.available(SimpleNamespace(game_id='shs')))
        self.assertFalse(CodShell.available(SimpleNamespace(game_id='cod', android_asset=lambda rid: b'')))


class PreferenceTests(unittest.TestCase):
    def test_volumes_and_usage_sharing_persist_and_bad_values_are_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            record = dict(id='a' * 64, pack_id=5, episode_id=9, titles=['t'] * 5, name='x.exp')
            library = SimpleNamespace(directory=Path(directory), episodes=[record], select=lambda selector: record,
                                      open_episode=None)
            state = MenuState(library)
            self.assertEqual((state.music_volume, state.sound_volume, state.logging_disabled), (50, 50, False))
            state.music_volume, state.sound_volume, state.logging_disabled = 20, 80, True
            state.persist()
            again = MenuState(library)
            self.assertEqual((again.music_volume, again.sound_volume, again.logging_disabled), (20, 80, True))
            path = Path(directory) / 'player.json'
            data = json.loads(path.read_text(encoding='utf-8'))
            data.update(music_volume=250, sound_volume='loud', logging_disabled='yes')
            path.write_text(json.dumps(data), encoding='utf-8')
            broken = MenuState(library)
            self.assertEqual((broken.music_volume, broken.sound_volume, broken.logging_disabled), (50, 50, False))

    def test_the_hd_menu_fonts_are_style_one_glyph_sets(self):
        glyph = struct.pack('BB', 2, 2) + bytes(16)
        data = struct.pack('>bBbhb', 10, 1, -2, 2, 2) + b'AB' + struct.pack('>hh', -1, 2)[:2] + struct.pack('>h', 2) + glyph * 2
        font = MenuFont.parse(data)
        self.assertEqual((font.space, font.height, sorted(font.glyphs)), (10, 2, ['A', 'B']))
        with self.assertRaises(Exception):
            MenuFont.parse(struct.pack('>bBbhb', 10, 2, -2, 2, 2) + b'AB' + struct.pack('>h', -1) + struct.pack('>h', 2) + glyph * 2)


class EndMenuTests(unittest.TestCase):
    def test_end_menu_choice_follows_the_episode(self):
        self.assertEqual((END_MENU, MISS_MENU), (23, 24))


class CodWindowTests(unittest.TestCase):
    """Cause of Death's menu-engine windows (desktop_cod_menu.py): SHS HD's layout, CoD's strings, art and item
    conditions."""

    def setUp(self):
        from exp_runtime.desktop_cod_menu import CodMenuWindows
        pygame.display.init()
        pygame.display.set_mode((1, 1))
        self.addCleanup(pygame.display.quit)
        menus = [(1, NO, 3, ())] * 16 + [(1, NO, 2, (0, 1)), (1, 2, 7, (2, 3, 4, 5, 6, 7))]   # 16: Exit Game?, 17: a list
        actions = [(4, (0xff, 0xff), [(BACK, 0xffff)]), (3, (0xff, 0xff), [(ENGINE, 24)]),
                   (6, (0xff, 0xff), []),                  # always shown
                   (7, (2, 0xff), []),                     # "Enable Usage Sharing": only while sharing is disabled
                   (6, (4, 0xff), []),                     # "Disable Usage Sharing": only while it is on
                   (7, (8, 0xff), []),                     # Vibration: never
                   (6, (16, 0xff), []),                    # the pause "Alert" row: never
                   (5, (1, 0xff), [(BACK, 0xffff)])]       # the footer button
        library = SimpleNamespace(android_asset=lambda rid: STRINGS if rid == 13 else None,
                                  shs_hd_resource=lambda rid: None, hd_raw_resource=lambda rid: None, hd_ipa=None)
        self.frames = []

        def frame_scaled(pack, index, k):
            self.frames.append((pack, index))
            return pygame.Surface((8, 8), pygame.SRCALPHA)
        self.disabled = False
        self.windows = CodMenuWindows(library, MenuEngineData(engine_data(menus, actions)),
                                      SimpleNamespace(frame_scaled=frame_scaled),
                                      logging_disabled=lambda: self.disabled)

    def test_exit_game_keeps_shs_hd_geometry(self):
        g = self.windows.layout(16)
        self.assertEqual(g['kind'], 'alert')
        self.assertAlmostEqual(g['top'] * 2 + g['total'], 1024)
        self.assertAlmostEqual(g['total'], g['header'] + BUTTON_STRIP)
        self.windows.draw(pygame.Surface((1536, 2048), pygame.SRCALPHA), 16)
        self.assertEqual([command for _, command in self.windows.hits], [('item', 0), ('item', 1)])
        self.assertTrue(all((rect.width, rect.height) == (156, 58) for rect, _ in self.windows.hits))

    def test_strings_come_from_cods_bank(self):
        self.assertEqual(self.windows.text_for(1), 'Title')

    def test_card_is_cods_window_as_vectors_and_buttons_are_pack_16_art(self):
        from exp_runtime.desktop_cod_menu import CARD_BORDER, CARD_EDGE
        from exp_runtime.desktop_hd_menu import CARD_LEFT
        layer = pygame.Surface((1536, 2048), pygame.SRCALPHA)
        g = self.windows.draw(layer, 16, pressed=('item', 1))
        self.assertFalse({(16, 80), (16, 78), (16, 79)} & set(self.frames))                # no stretched 1x pieces
        x = (CARD_LEFT + 2) * 2                                                             # inside the 6-point border
        self.assertEqual(tuple(layer.get_at((x, round((g['top'] + 60) * 2))))[:3], CARD_BORDER)
        tall = self.windows.layout(17)
        self.windows.draw(layer, 17)
        edge = tuple(layer.get_at((x, round((tall['top'] + 130) * 2))))[:3]
        self.assertTrue(all(abs(a - b) <= 2 for a, b in zip(edge, CARD_EDGE)), edge)        # beside the body
        self.assertTrue({(16, 90), (16, 91), (16, 92)} <= set(self.frames))                # No, up
        self.assertTrue({(16, 93), (16, 94), (16, 95)} <= set(self.frames))                # Yes, pressed

    def test_conditional_items_follow_usage_sharing(self):
        self.assertEqual([a.id for a in self.windows.items(17)], [2, 4, 7])
        self.disabled = True
        self.assertEqual([a.id for a in self.windows.items(17)], [2, 3, 7])
        g = self.windows.layout(17)
        self.assertEqual([row.action.id for row in g['rows']], [2, 3])
        self.assertEqual(g['footer'].id, 7)


if __name__ == '__main__':
    unittest.main()


class HiddenUsageSharingTests(unittest.TestCase):
    """The privacy window's usage-sharing rows are never shown (owner, 2026-10-15): the runtime sends nothing."""

    def test_rows_reaching_usage_sharing_are_hidden_in_both_games(self):
        from types import SimpleNamespace
        from exp_runtime.desktop_cod_menu import CodMenuWindows
        from exp_runtime.desktop_hd_menu import HdMenuWindows
        from exp_runtime.menu_engine import ENGINE, QUEUE
        row = lambda *steps: SimpleNamespace(steps=steps)
        for windows, hidden, kept in ((HdMenuWindows, row((ENGINE, 17)), row((ENGINE, 14), (QUEUE, 17))),
                                      (CodMenuWindows, row((QUEUE, 18)), row((ENGINE, 21), (QUEUE, 16)))):
            shown = windows.shown(SimpleNamespace(HIDDEN_ACTIONS=windows.HIDDEN_ACTIONS,
                                                  HIDDEN_MENUS=windows.HIDDEN_MENUS), hidden)
            self.assertFalse(shown)
            self.assertTrue(windows.shown(SimpleNamespace(HIDDEN_ACTIONS=windows.HIDDEN_ACTIONS,
                                                          HIDDEN_MENUS=windows.HIDDEN_MENUS), kept))
        self.assertFalse(CodMenuWindows.shown(SimpleNamespace(HIDDEN_ACTIONS=(26, 27), HIDDEN_MENUS=(18, 19)),
                                              row((QUEUE, 19))))
