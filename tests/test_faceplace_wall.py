"""The faceplace wall's input (scrolling, tapping a link) and the alert's sound, on a desktop with authored content."""
import importlib.util
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from exp_runtime.desktop_hd_menu import HdMenuWindows
from exp_runtime.dtview_faceplace import FaceplaceMessage, FaceplaceToast
from exp_runtime.menu_engine import BACK, ENGINE, MenuEngineData, MenuStack
from exp_runtime.runtime import Session
from test_hd_menus import NO, FakeLibrary, engine_data
from test_tree_warp import dialogue_story


def _build_wall_ui(testcase):
    """A `Desktop` on authored test content with the wall open and a known link target -- shared by
    `WallInputTests` (no HD resources: a tap opens directly) and `WallConfirmTests` (HD's "Exit Game?"
    confirmation wired in by hand)."""
    os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
    import pygame
    testcase.pygame = pygame
    testcase.addCleanup(pygame.quit)
    testcase.temporary = tempfile.TemporaryDirectory()
    testcase.addCleanup(testcase.temporary.cleanup)
    from exp_runtime.desktop import Desktop
    session = Session(dialogue_story(testcase.temporary.name))
    session.advance()
    testcase.ui = Desktop(session, audio=False)
    testcase.ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB))
    testcase.ui.tick(1000)
    panels = testcase.ui.side_panels
    # Where the drawn wall would be, and the link it would leave (the art comes from the imported app).
    panels.wall_rect, panels.wall_scale, panels.wall_scroll = pygame.Rect(1000, 0, 448, 1536), 2.0, 100.0
    panels.wall_targets = [(pygame.Rect(1100, 400, 300, 40), 'http://example.invalid/pogo')]


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class WallInputTests(unittest.TestCase):
    def setUp(self):
        _build_wall_ui(self)

    def event(self, kind, **fields):
        return self.pygame.event.Event(kind, **fields)

    def test_the_wheel_over_the_wall_scrolls_it_and_only_there(self):
        panels, pygame = self.ui.side_panels, self.pygame
        with patch.object(pygame.mouse, 'get_pos', return_value=(1200, 300)):
            self.assertTrue(self.ui.handle_event(self.event(pygame.MOUSEWHEEL, x=0, y=-1)))
        self.assertEqual(panels.wall_scroll, 120.0)                     # 40 pixels a notch, 2 pixels a point: 20 points
        with patch.object(pygame.mouse, 'get_pos', return_value=(300, 300)):
            self.ui.handle_event(self.event(pygame.MOUSEWHEEL, x=0, y=-1))
        self.assertEqual(panels.wall_scroll, 120.0)

    def test_dragging_scrolls_and_a_tap_on_a_link_opens_it(self):
        panels, pygame = self.ui.side_panels, self.pygame
        with patch('exp_runtime.desktop.webbrowser.open', return_value=True) as opened:
            self.ui.handle_event(self.event(pygame.MOUSEBUTTONDOWN, pos=(1200, 420), button=1))
            self.ui.handle_event(self.event(pygame.MOUSEMOTION, pos=(1200, 480), rel=(0, 60), buttons=(1, 0, 0)))
            self.ui.handle_event(self.event(pygame.MOUSEBUTTONUP, pos=(1200, 480), button=1))
            self.assertEqual(panels.wall_scroll, 70.0)                  # 60 pixels at 2 pixels a point, dragged down
            opened.assert_not_called()                                  # a touch that moved is not a tap
            self.ui.handle_event(self.event(pygame.MOUSEBUTTONDOWN, pos=(1200, 420), button=1))
            self.ui.handle_event(self.event(pygame.MOUSEBUTTONUP, pos=(1200, 420), button=1))
            opened.assert_called_once_with('http://example.invalid/pogo')
            opened.reset_mock()
            self.ui.handle_event(self.event(pygame.MOUSEBUTTONDOWN, pos=(1200, 900), button=1))
            self.ui.handle_event(self.event(pygame.MOUSEBUTTONUP, pos=(1200, 900), button=1))
            opened.assert_not_called()                                  # a tap beside the link

    def test_a_link_that_cannot_be_opened_is_logged_not_fatal(self):
        pygame = self.pygame
        with patch('exp_runtime.desktop.webbrowser.open', return_value=False), self.assertLogs(level='WARNING') as logged:
            self.ui.handle_event(self.event(pygame.MOUSEBUTTONDOWN, pos=(1200, 420), button=1))
            self.ui.handle_event(self.event(pygame.MOUSEBUTTONUP, pos=(1200, 420), button=1))
        self.assertIn('failed to open URL', logged.output[0])


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class WallConfirmTests(unittest.TestCase):
    """With an HD bundle's resource 17 available, a wall link tap goes through the app's own "Exit Game?"
    confirmation first (`Desktop._wall_perform`/`_notice_pointer`), the same window number
    (`LEAVE_MENU = 17` in `application_hd.py`) the main menu's own EULA/Privacy/Terms rows already use --
    synthesized here with `test_hd_menus.py`'s own `engine_data()` helper rather than a real HD ipa import,
    since only the dispatch logic is under test, not `HdMenuWindows`/`MenuEngineData` themselves (covered in
    `test_hd_menus.py`)."""

    def setUp(self):
        _build_wall_ui(self)
        # bg_viewport is normally set by render(); this fixture's minimal content can't actually render a
        # dialogue frame (no imported APK fonts/layout), and render() failing would set self.error, disabling
        # all input -- so it's set directly here instead, purely for _pause_point's coordinate math below.
        self.ui.bg_viewport = self.pygame.Rect(0, 0, 768, 1024)
        # Menu 17 mirrors the real "Exit Game?" alert's shape: title 93, message 94, two items (No, Yes).
        menus = [(1, NO, 2, ())] * 17 + [(93, 94, 2, (0, 1))]
        actions = [(25, (0xff, 0xff), [(BACK, 0xffff)]), (24, (0xff, 0xff), [(ENGINE, 18)])]
        data = MenuEngineData(engine_data(menus, actions))
        self.ui.notice_data = data
        self.ui.notice_windows = HdMenuWindows(FakeLibrary(), data, None)
        self.ui.notice_stack = MenuStack(data, self.ui._wall_perform)
        # Known frame-point rects for the two buttons, as if draw() had just populated them.
        self.no_rect, self.yes_rect = self.pygame.Rect(100, 900, 200, 60), self.pygame.Rect(450, 900, 200, 60)
        self.ui.notice_windows.hits = [(self.no_rect, ('item', 0)), (self.yes_rect, ('item', 1))]

    def event(self, kind, **fields):
        return self.pygame.event.Event(kind, **fields)

    def _frame_pos(self, point):
        """A window pixel position that maps back to `point` (frame points) through `Desktop._pause_point`."""
        frame = self.ui.bg_viewport
        return (point[0] * frame.width / 768 + frame.x, point[1] * frame.height / 1024 + frame.y)

    def _tap(self, rect):
        pos = self._frame_pos(rect.center)
        self.ui.handle_event(self.event(self.pygame.MOUSEBUTTONDOWN, pos=pos, button=1))
        self.ui.handle_event(self.event(self.pygame.MOUSEBUTTONUP, pos=pos, button=1))

    def test_a_wall_link_tap_opens_the_confirmation_before_the_browser(self):
        with patch('exp_runtime.desktop.webbrowser.open', return_value=True) as opened:
            self.ui.handle_event(self.event(self.pygame.MOUSEBUTTONDOWN, pos=(1200, 420), button=1))
            self.ui.handle_event(self.event(self.pygame.MOUSEBUTTONUP, pos=(1200, 420), button=1))
            opened.assert_not_called()
        self.assertEqual(self.ui.notice_stack.stack, [self.ui.exit_menu])
        self.assertEqual(self.ui.wall_link, 'http://example.invalid/pogo')

    def test_a_help_page_link_in_the_pause_menu_asks_first(self):
        # An About page's link, tapped in a story's pause menu, goes through the same "Exit Game?" prompt.
        with patch('exp_runtime.desktop.webbrowser.open', return_value=True) as opened:
            self.ui.command(('pause_link', 'https://example.invalid/about'))
            opened.assert_not_called()
        self.assertEqual(self.ui.notice_stack.stack, [self.ui.exit_menu])
        self.assertEqual(self.ui.wall_link, 'https://example.invalid/about')

    def test_yes_opens_the_link_and_closes_the_dialog(self):
        self.ui.handle_event(self.event(self.pygame.MOUSEBUTTONDOWN, pos=(1200, 420), button=1))
        self.ui.handle_event(self.event(self.pygame.MOUSEBUTTONUP, pos=(1200, 420), button=1))
        with patch('exp_runtime.desktop.webbrowser.open', return_value=True) as opened:
            self._tap(self.yes_rect)
            opened.assert_called_once_with('http://example.invalid/pogo')
        self.assertEqual(self.ui.notice_stack.stack, [])

    def test_no_closes_without_opening(self):
        self.ui.handle_event(self.event(self.pygame.MOUSEBUTTONDOWN, pos=(1200, 420), button=1))
        self.ui.handle_event(self.event(self.pygame.MOUSEBUTTONUP, pos=(1200, 420), button=1))
        with patch('exp_runtime.desktop.webbrowser.open', return_value=True) as opened:
            self._tap(self.no_rect)
            opened.assert_not_called()
        self.assertEqual(self.ui.notice_stack.stack, [])

    def test_escape_closes_without_opening(self):
        self.ui.handle_event(self.event(self.pygame.MOUSEBUTTONDOWN, pos=(1200, 420), button=1))
        self.ui.handle_event(self.event(self.pygame.MOUSEBUTTONUP, pos=(1200, 420), button=1))
        with patch('exp_runtime.desktop.webbrowser.open', return_value=True) as opened:
            self.ui.handle_event(self.event(self.pygame.KEYDOWN, key=self.pygame.K_ESCAPE))
            opened.assert_not_called()
        self.assertEqual(self.ui.notice_stack.stack, [])


class CodWallConfirmTests(WallConfirmTests):
    """The same flow on Cause of Death's own menu engine: its "Exit Game?" is menu 16, whose Yes runs engine action
    24 (`doMenuEngineAction` case 0x18 -> `exitAndShowURL`)."""

    def setUp(self):
        super().setUp()
        menus = [(1, NO, 2, ())] * 16 + [(93, 94, 2, (0, 1))]
        actions = [(25, (0xff, 0xff), [(BACK, 0xffff)]), (24, (0xff, 0xff), [(ENGINE, 24)])]
        data = MenuEngineData(engine_data(menus, actions))
        self.ui.notice_data = data
        self.ui.notice_stack = MenuStack(data, self.ui._wall_perform)
        self.ui.exit_menu, self.ui.exit_action = 16, 24

    def test_without_hd_resources_a_tap_opens_directly_as_before(self):
        self.ui.notice_data = self.ui.notice_windows = self.ui.notice_stack = None
        with patch('exp_runtime.desktop.webbrowser.open', return_value=True) as opened:
            self.ui.handle_event(self.event(self.pygame.MOUSEBUTTONDOWN, pos=(1200, 420), button=1))
            self.ui.handle_event(self.event(self.pygame.MOUSEBUTTONUP, pos=(1200, 420), button=1))
            opened.assert_called_once_with('http://example.invalid/pogo')


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class AlertSoundTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        self.pygame = pygame
        self.addCleanup(pygame.quit)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        from exp_runtime.desktop import Desktop
        session = Session(dialogue_story(self.temporary.name))
        session.advance()
        session.resources.read_asset = Mock(return_value=b'authored sound bytes')
        self.ui = Desktop(session, audio=False)
        self.ui.audio = True

    def alert(self):
        toast = FaceplaceToast(FaceplaceMessage('message', text='hello', from_id=-1, expression=0))
        self.ui.session.engine.faceplace_toast = toast
        return toast

    def test_the_alert_plays_sound_0x1f52_once_when_it_has_slid_on(self):
        toast = self.alert()
        with patch.object(self.pygame.mixer, 'Sound') as sound:
            self.ui._sync_audio()
            sound.assert_not_called()                                   # still sliding
            toast.tick(200)
            self.ui._sync_audio()
            self.ui._sync_audio()
            self.ui.session.resources.read_asset.assert_called_with(0x1f52)
            self.assertEqual(sound.return_value.play.call_count, 1)
            self.alert().tick(200)                                      # the next alert sounds again
            self.ui._sync_audio()
            self.assertEqual(sound.return_value.play.call_count, 2)

    def test_there_is_no_alert_sound_with_the_panels_open(self):
        toast = self.alert()
        toast.tick(200)
        self.ui.panels_open = True
        with patch.object(self.pygame.mixer, 'Sound') as sound:
            self.ui._sync_audio()
            sound.assert_not_called()


if __name__ == '__main__':
    unittest.main()
