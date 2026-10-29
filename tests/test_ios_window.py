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

    def host(self):
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
        host = Host(self.root, backend=backend, library_root=self.root / 'libraries', check_updates=False)
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
        self.assertIn('frames (picker, 306,', logged.output[0])
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
