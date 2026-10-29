"""The iOS host's window and touches: the app draws at the view's pixel size (an iPad mini: 1536 x 2048, where the
fixed 540 x 720 window looked blurry), and touches arrive as complete pygame-style mouse events (the HD picker's row
drag reads `buttons`, its wheel `x`: a tester's crash)."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


class IosWindowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def host(self, view_size=None):
        import logging
        from exp_runtime import graphics
        from exp_runtime.app_icon import icon_surface
        from exp_runtime.platforms.drawing import Backend
        from exp_runtime.platforms.ios import Host
        from PIL import Image
        from native_host_fonts import FontHost
        icon = self.root / 'authored-icon.png'
        Image.new('RGBA', (2, 2), 'green').save(icon)
        backend = Backend(FontHost(), icon)
        previous = graphics.install(backend)
        self.addCleanup(graphics.install, previous)
        icon_surface.cache_clear()
        self.addCleanup(icon_surface.cache_clear)
        host = Host(self.root, backend=backend, library_root=self.root / 'libraries', check_updates=False,
                    view_size=view_size)
        self.addCleanup(host.app.close)

        def drop_log():
            logger = logging.getLogger()
            for handler in list(logger.handlers):
                if getattr(handler, 'ios_runtime_log', False):
                    logger.removeHandler(handler)
        self.addCleanup(drop_log)
        return host

    def test_the_window_follows_the_views_pixel_size(self):
        host = self.host()
        default = host.app.window.get_size()
        host.request(dict(operation='frame', elapsed=16))
        self.assertEqual(host.app.window.get_size(), default)             # no size (the simulator check): unchanged
        host.request(dict(operation='frame', elapsed=16, size=[1536, 2048]))
        self.assertEqual(host.app.window.get_size(), (1536, 2048))
        window = host.app.window
        host.request(dict(operation='frame', elapsed=16, size=[1536, 2048]))
        self.assertIs(host.app.window, window)                            # the same size keeps the same window
        host.app.game = SimpleNamespace(window=window)
        host.resize([1024, 1366])
        self.assertIs(host.app.game.window, host.app.window)              # the running game draws to it too
        host.app.game = None
        host.request(dict(operation='frame', elapsed=16, size=[2048, 1536]))   # turned to landscape
        self.assertEqual(host.app.window.get_size(), (2048, 1536))

    def test_the_hd_menus_draw_at_the_screens_resolution(self):
        """The window is the view's pixel size (Swift's first frame sends it): the HD menus' layers are 2x where the
        frame is shown well over its 768 x 1024 points (a Retina iPad, either way up; a phone), 1x where it is not."""
        import os
        from unittest.mock import patch
        from exp_runtime.platforms.ios import hd_scale_for
        self.assertEqual([hd_scale_for(size) for size in ([1536, 2048], [2048, 1536], [1179, 2556], [768, 992],
                                                          [540, 720], None)], [2, 2, 2, 1, 1, 1])
        with patch.dict(os.environ):
            os.environ.pop('SHSHD_HD_SCALE', None)
            self.host(view_size=[1536, 1984])
            self.assertEqual(os.environ.get('SHSHD_HD_SCALE'), '2')

    def test_the_input_stamp_reads_this_forks_prompt(self):
        """The one-input gate's stamp follows the fork's host prompt (desktop._host_prompt), not upstream's
        `minigame_prompt`, which this Desktop lacks: every episode stopped the runtime on its first frame."""
        from exp_runtime.desktop import Desktop
        host = self.host()
        pending = SimpleNamespace(details={})
        session = SimpleNamespace(pending=pending, scene=1, vm=SimpleNamespace(steps_executed=4))
        game = SimpleNamespace(session=session, menu_open=False, host_prompt=None)
        self.assertFalse(hasattr(Desktop, 'minigame_prompt'))
        host.app.game, host.app.screen = game, 'game'
        self.addCleanup(setattr, host.app, 'game', None)
        closed = host._input_stamp()
        game.host_prompt = dict(action=pending)
        self.assertNotEqual(host._input_stamp(), closed)

    def test_touches_are_complete_mouse_events(self):
        host = self.host()
        seen = []
        host.app.handle_event = seen.append
        for kind in ('down', 'move', 'up'):
            host._event(dict(kind=kind, point=(100, 200)))
        host._event(dict(kind='scroll', delta=1.5))
        down, move, up, wheel = seen
        self.assertEqual((down.buttons, move.buttons, up.buttons), ((1, 0, 0), (1, 0, 0), (0, 0, 0)))
        self.assertEqual(move.pos, (100, 200))
        self.assertEqual((wheel.x, wheel.y), (0, 1.5))

    def test_side_panels_turn_the_ipad_to_landscape_and_go_off_in_portrait(self):
        """The owner's rule: side panels turned on in portrait ask once for landscape, without locking rotation;
        turned back to portrait (or never turned), they switch off. The window is the view's, never widened."""
        from exp_runtime.desktop import Desktop
        from exp_runtime.platforms.ios import PANELS_ROTATE_MS
        host = self.host()
        self.assertTrue(host.app.fixed_window)
        Desktop._widen_for_panels(SimpleNamespace(fixed_window=True))      # no window change at all
        game = SimpleNamespace(panels_open=True)
        game.toggle_panels = lambda: setattr(game, 'panels_open', not game.panels_open)
        host.app.game, host.app.screen = game, 'game'
        self.addCleanup(setattr, host.app, 'game', None)
        host.view_size = (1536, 2048)
        self.assertEqual(host.panels_orientation(16), 'landscape')
        self.assertIsNone(host.panels_orientation(16))                       # asked once
        host.view_size = (2048, 1536)
        self.assertIsNone(host.panels_orientation(16))
        self.assertTrue(game.panels_open)
        host.view_size = (1536, 2048)
        self.assertEqual(host.panels_orientation(16), 'release')
        self.assertFalse(game.panels_open)                                   # turned back: off
        self.assertIsNone(host.panels_orientation(16))                       # released once
        game.panels_open = True
        self.assertEqual(host.panels_orientation(16), 'landscape')
        self.assertEqual(host.panels_orientation(PANELS_ROTATE_MS), 'release')
        self.assertFalse(game.panels_open)                                   # never turned: off
        game.panels_open = True
        self.assertEqual(host.panels_orientation(16), 'landscape')
        game.panels_open = False                                             # switched off from the menu
        self.assertEqual(host.panels_orientation(16), 'release')

    def test_a_flick_read_in_one_frame_keeps_its_touches_times(self):
        """UIKit's touch times reach momentum.py on the game's clock: a slow frame can hold a whole flick, and read
        at the frame's time its moves were all at once, so it never glided (owner's report)."""
        from exp_runtime import momentum
        host = self.host()
        seen = []
        host.app.handle_event = lambda event: seen.append(momentum._now())
        host.request(dict(operation='frame', elapsed=16, size=[768, 992], now=50_000.0, events=[]))
        ticks = host.backend.ticks
        host.request(dict(operation='frame', elapsed=200, size=[768, 992], now=50_200.0, events=[
            dict(kind='down', point=[100, 500], time=50_020.0), dict(kind='move', point=[100, 400], time=50_060.0),
            dict(kind='move', point=[100, 300], time=50_100.0), dict(kind='up', point=[100, 300], time=50_110.0)]))
        self.assertEqual(seen, [ticks + 20, ticks + 60, ticks + 100, ticks + 110])
        self.assertIsNone(momentum.EVENT_TIME)                          # the frame's own clock again afterwards

    def test_a_pinch_begun_on_the_tree_zooms_it_about_the_fingers_and_carries_it(self):
        """UIKit's pinch (HD's tree is a UIScrollView): each step zooms by its factor about the midpoint, which then
        drags the tree; a pinch begun off the tree leaves it alone."""
        import math
        from types import SimpleNamespace
        from exp_runtime.platforms.drawing import Rect
        host = self.host()
        calls = []
        panels = SimpleNamespace(tree_rect=Rect(0, 0, 200, 700), tree_scale=2.0, ZOOM_STEP=1.15,
                                 zoom_tree=lambda notches, at: calls.append(('zoom', round(notches, 6), at)),
                                 scroll_tree=lambda down, across=0.0: calls.append(('scroll', down, across)))
        game = SimpleNamespace(panels_open=True, side_panels=panels, tree_drag=['held'],
                               tree_fling=SimpleNamespace(stop=lambda: calls.append(('stop',))))
        host.app.game, host.app.screen = game, 'game'
        self.addCleanup(setattr, host.app, 'game', None)
        host._event(dict(kind='pinch', phase='began', scale=1.0, point=[100, 300]))
        self.assertIsNone(game.tree_drag)
        host._event(dict(kind='pinch', phase='changed', scale=1.15, point=[110, 320]))
        host._event(dict(kind='pinch', phase='ended', scale=1.0, point=[110, 320]))
        host._event(dict(kind='pinch', phase='changed', scale=2.0, point=[110, 320]))     # over: nothing
        self.assertEqual(calls, [('stop',), ('zoom', round(math.log(1.15) / math.log(1.15), 6), (110, 320)),
                                 ('scroll', -10.0, -5.0)])
        calls.clear()
        host._event(dict(kind='pinch', phase='began', scale=1.0, point=[500, 300]))       # beside the tree
        host._event(dict(kind='pinch', phase='changed', scale=1.5, point=[500, 300]))
        self.assertEqual(calls, [])

    def test_a_drag_on_the_tree_outlives_the_story_moving_on(self):
        """A touch from before the screen changed (its generation) answers nothing, but a finger dragging the tree or
        the wall goes on, its lift ending the drag; one that never moved is let go, not a tap on the new screen."""
        from exp_runtime.platforms.drawing import Rect
        host = self.host()
        seen = []
        panels = SimpleNamespace(tree_rect=Rect(0, 0, 200, 700), tree_scroll=0.0, tree_scroll_x=0.0, tree_sz_now=1.0)
        game = SimpleNamespace(panels_open=True, side_panels=panels, tree_drag=None, wall_drag=None,
                               session=SimpleNamespace(pending=None), screen_token=None)
        game._screen_token = lambda: None
        host.app.game, host.app.screen = game, 'game'
        self.addCleanup(setattr, host.app, 'game', None)

        def handle(event):
            seen.append(event.type)
            if event.type == host.backend.MOUSEBUTTONDOWN:
                game.tree_drag = [event.pos, (0.0, 0.0), False]
            elif event.type == host.backend.MOUSEMOTION and game.tree_drag:
                game.tree_drag[2] = True
                panels.tree_scroll = 50.0
            elif event.type == host.backend.MOUSEBUTTONUP:
                game.tree_drag = None
        host.app.handle_event = handle
        cancelled = []
        host.app.cancel_pointer = lambda: cancelled.append(True)
        host.app.input_token = lambda: ('game', None, None)
        stale = host.generation - 1
        host.handle_events([dict(kind='down', point=[100, 300], generation=host.generation)])
        host.handle_events([dict(kind='move', point=[100, 250], generation=stale),
                            dict(kind='up', point=[100, 250], generation=stale)])
        b = host.backend
        self.assertEqual(seen, [b.MOUSEBUTTONDOWN, b.MOUSEMOTION, b.MOUSEBUTTONUP])
        self.assertIsNone(game.tree_drag)
        self.assertEqual(panels.tree_scroll, 50.0)
        seen.clear()
        host.handle_events([dict(kind='down', point=[100, 300], generation=host.generation)])
        host.handle_events([dict(kind='up', point=[100, 300], generation=stale)])     # a tap: let go
        self.assertEqual(seen, [b.MOUSEBUTTONDOWN])
        self.assertIsNone(game.tree_drag)
        self.assertEqual(cancelled, [True])
        host.handle_events([dict(kind='move', point=[100, 250], generation=stale)])  # no drag: dropped
        self.assertEqual(seen, [b.MOUSEBUTTONDOWN])

    def test_the_options_controls_are_uikits_and_their_changes_set_the_options(self):
        """The host turns the menus' switches and volume sliders into UIKit's (graphics.native_controls): each frame
        lists them in the window's pixels (the main menu's mapped from its frame by the viewport, none under a
        message). A flip Swift sends is the row's toggle, once, only while it differs and its page is up; a slider's
        move sets that volume."""
        from exp_runtime import graphics
        from exp_runtime.platforms.drawing import Rect
        host = self.host()
        self.assertEqual(graphics.native_controls, [])
        app = host.app
        app.viewport = Rect(0, 16, 384, 512)                    # the frame at half size, 16 down
        toggled, volumes = [], []
        app.shell = SimpleNamespace(pause_open=True, activate=toggled.append,
                                    set_volume=lambda which, value: volumes.append(('menu', which, value)))
        app.screen, app.message = 'main', ''
        graphics.native_controls.extend([
            dict(kind='switch', key='autoplay', on=False, space='frame', alpha=1.0, scale=1.0, right=660, middle=300),
            dict(kind='slider', key='music', value=.5, space='frame', alpha=1.0, scale=1.0, left=143, right=603,
                 middle=400)])
        shown = host.controls()
        self.assertEqual(shown, [dict(kind='switch', key='autoplay', on=False, right=330.0, middle=166.0, scale=.5,
                                      alpha=1.0),
                                 dict(kind='slider', key='music', value=.5, left=71.5, right=301.5, middle=216.0,
                                      scale=.5, alpha=1.0)])
        self.assertEqual(graphics.native_controls, [])
        host._event(dict(kind='switch', key='autoplay', on=True))
        host._event(dict(kind='switch', key='autoplay', on=False))         # already off: nothing
        self.assertEqual(toggled, [('pause_toggle', 'autoplay')])
        host._event(dict(kind='slider', key='music', value=1.4))
        self.assertEqual(volumes, [('menu', 'music', 1.0)])
        app.message = 'Added 3 episodes.'                                  # the message card covers the menu
        graphics.native_controls.append(dict(kind='switch', key='autoplay', on=True, space='frame', alpha=1.0,
                                             scale=1.0, right=660, middle=300))
        self.assertEqual(host.controls(), [])
        game = SimpleNamespace(menu_open=True, pause_closing=False, command=toggled.append,
                               _set_volume=lambda which, value: volumes.append(('game', which, value)))
        app.game, app.screen, app.message = game, 'game', ''
        self.addCleanup(setattr, app, 'game', None)
        graphics.native_controls.append(dict(kind='switch', key='choice_hints', on=False, space='window', alpha=1.0,
                                             scale=1.0, right=600, middle=400))
        host.controls()
        host._event(dict(kind='switch', key='choice_hints', on=True))
        host._event(dict(kind='slider', key='sound', value=.3))
        self.assertEqual(toggled[-1], ('pause_toggle', 'choice_hints'))
        self.assertEqual(volumes[-1], ('game', 'sound', .3))
        game.pause_closing = True                                          # the card is going: let it be
        host._event(dict(kind='switch', key='choice_hints', on=True))
        host._event(dict(kind='slider', key='sound', value=.9))
        self.assertEqual((len(toggled), len(volumes)), (2, 2))

    def test_the_name_entrys_alert_and_typed_name_go_to_uikit(self):
        """SHS HD's name entry showed a UIAlertView: Swift's alert's OK is the drawn alert's (input_dismiss). The
        name typed so far goes with each frame, for the keyboard's Done (grey while the name is empty)."""
        host = self.host()
        commands = []
        details = dict(default='', draft='Zo')
        game = SimpleNamespace(input_error='bad', command=commands.append,
                               session=SimpleNamespace(pending=SimpleNamespace(name='text_input', details=details)))
        host.app.game, host.app.screen = game, 'game'
        self.addCleanup(setattr, host.app, 'game', None)
        self.assertEqual(host.typed_text(), 'Zo')
        host._event(dict(kind='alert'))
        self.assertEqual(commands, [('input_dismiss',)])
        game.input_error = None
        host._event(dict(kind='alert'))                                    # already gone: nothing
        self.assertEqual(commands, [('input_dismiss',)])
        game.session.pending = SimpleNamespace(name='dialogue', details={})
        self.assertIsNone(host.typed_text())

    def test_slow_frames_are_summarised_in_the_runtime_log(self):
        """The owner's iPad is the only place its slowness shows: a span with a slow frame writes one summary line
        (Swift's timings with it); a smooth span writes nothing."""
        from exp_runtime.platforms.ios import FrameStats
        stats = FrameStats()
        frame = dict(frame=dict(nodes=[dict(png='A' * 4096), dict(ops=[], size=[1000, 1000])]))
        with self.assertNoLogs(level='WARNING'):
            for _ in range(FrameStats.STATS_MS // 16 + 1):
                stats.add(dict(elapsed=16), frame, 3.0, 'main')
        with self.assertLogs(level='WARNING') as logged:
            for elapsed in [120] + [16] * 305:
                stats.add(dict(elapsed=elapsed, timing=dict(engine_ms=9, render_ms=40)), frame, 3.0, 'picker')
        self.assertEqual(len(logged.output), 1)
        self.assertIn('frames (picker, , 306,', logged.output[0])
        self.assertIn('interval 16.3/120.0', logged.output[0])
        self.assertIn('render 40.0/40.0', logged.output[0])
        self.assertIn('png_kb 3.0/3.0 op_mpx 1.0/1.0', logged.output[0])

    def test_a_storys_link_goes_to_the_host(self):
        """A script link (a novel's "Yes, please!") and the Faceplace wall's go to the host's `open_url`, which opens
        them with UIApplication, rather than to Python's webbrowser."""
        from exp_runtime.desktop import Desktop
        host = self.host()
        game = SimpleNamespace(url_opener=host.app.url_opener)
        Desktop._open_link(game, 'https://example.com/story')
        self.assertEqual(host.url, 'https://example.com/story')


if __name__ == '__main__':
    unittest.main()
