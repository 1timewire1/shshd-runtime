"""Android host contracts tested without a device or Java runtime."""
import importlib.util
from pathlib import Path
from queue import Queue
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from exp_runtime.platforms.android import Host


class ImportTests(unittest.TestCase):
    def host(self):
        host = Host.__new__(Host)
        host.pending = True
        host.closed = False
        host.results = Queue()
        host.imported = []
        host.app = SimpleNamespace(busy=False, message='', import_paths=Mock(), job=None, job_kind=None)
        host.app._attempt = lambda operation: operation()
        return host

    def test_picker_cancellation_does_not_import_or_replace_progress(self):
        host = self.host()
        host.on_result(Host.REQUEST, 0, None)
        host.poll()
        self.assertFalse(host.pending)
        host.app.import_paths.assert_not_called()

    def test_the_busy_screen_shows_while_picked_files_copy(self):
        """A 1 GB zip takes a while to copy into the app: the busy screen shows from the pick until the copy's result,
        which then starts the import."""
        host = self.host()
        host.results.put(('copying', None))
        host.poll()
        self.assertEqual(host.app.job_kind, 'copying')
        host.app.busy = True                                # Application.busy: a job is set
        host.results.put(('paths', [Path('picked.zip')]))
        host.poll()
        self.assertEqual((host.app.job, host.app.job_kind), (None, None))
        host.app.import_paths.assert_called_once_with([Path('picked.zip')])

    def test_unrelated_activity_result_is_ignored(self):
        host = self.host()
        host.on_result(99, -1, Mock())
        self.assertTrue(host.results.empty())

    def test_sources_survive_until_async_import_finishes(self):
        host = self.host()
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / 'selected'
            directory.mkdir()
            source = directory / 'episode.exp'
            source.write_bytes(b'authored test data')
            host.results.put(('paths', [source]))
            host.poll()
            host.app.import_paths.assert_called_once_with([source])
            host.app.busy = True
            host.poll()
            self.assertTrue(source.exists())
            host.app.busy = False
            host.poll()
            self.assertFalse(directory.exists())

    def test_provider_error_is_visible_and_picker_can_be_retried(self):
        host = self.host()
        host.results.put(('error', 'document unavailable'))
        host.poll()
        self.assertIn('document unavailable', host.app.message)
        self.assertFalse(host.pending)


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra required')
class FontTests(unittest.TestCase):
    def test_supplied_faces_are_found_by_style_then_roboto(self):
        """Android has none of the HD faces: the player's files (Windows names here) are found by face and style, so
        Trebuchet's bold and italic are told apart; anything missing falls back to Roboto."""
        from exp_runtime.platforms import android
        with tempfile.TemporaryDirectory() as root:
            fonts, system = Path(root) / 'fonts', Path(root) / 'system'
            fonts.mkdir()
            system.mkdir()
            for name in ('arial.ttf', 'ARIALBD.TTF', 'arialroundedmtbold.ttf', 'trebucbd.ttf', 'trebucit.ttf'):
                (fonts / name).write_bytes(b'authored stand-in')
            (system / 'Roboto-Regular.ttf').write_bytes(b'authored stand-in')
            match = android.font_finder(lambda: [Path(root) / 'missing', fonts])
            with patch.object(android, 'SYSTEM_FONTS', system):
                self.assertEqual(Path(match('arial')).name, 'arial.ttf')
                self.assertEqual(Path(match('arial', bold=True)).name, 'ARIALBD.TTF')
                self.assertEqual(Path(match('Arial Rounded MT Bold,Arial Rounded', bold=True)).name,
                                 'arialroundedmtbold.ttf')
                self.assertEqual(Path(match('trebuchetms', bold=True)).name, 'trebucbd.ttf')
                self.assertEqual(Path(match('trebuchetms', italic=True)).name, 'trebucit.ttf')
                self.assertEqual(Path(match('arial', italic=True)).name, 'Roboto-Regular.ttf')
                self.assertEqual(Path(match('liberationsans')).name, 'Roboto-Regular.ttf')
            with patch.object(android, 'SYSTEM_FONTS', Path(root) / 'none'):
                self.assertIsNone(match('verdana'))


class SidePanelTests(unittest.TestCase):
    def test_side_panels_turn_the_app_to_landscape_and_go_off_in_portrait(self):
        """The owner's rule: panels turned on in portrait ask once for landscape, without locking rotation; turned back
        to portrait (or never turned), they switch off and rotation is the user's again."""
        from exp_runtime.desktop import Desktop
        from exp_runtime.platforms.android import PANELS_PORTRAIT_MS, PANELS_ROTATE_MS
        Desktop._widen_for_panels(SimpleNamespace(fixed_window=True))      # the window is the screen's
        host = Host.__new__(Host)
        host.activity, host.panels_view = 'activity', None
        host.orientation = Mock()
        game = SimpleNamespace(panels_open=True)
        game.toggle_panels = lambda: setattr(game, 'panels_open', not game.panels_open)
        size = [1080, 2400]
        host.app = SimpleNamespace(game=game, screen='game',
                                   window=SimpleNamespace(get_size=lambda: tuple(size)))
        host.panels_orientation(16)
        host.panels_orientation(16)
        host.orientation.requestLandscape.assert_called_once_with('activity')
        size[:] = [2400, 1080]
        host.panels_orientation(16)
        self.assertTrue(game.panels_open)
        size[:] = [1080, 2400]
        host.panels_orientation(16)
        self.assertTrue(game.panels_open)                                    # a moment's flip: still on
        size[:] = [2400, 1080]
        host.panels_orientation(16)
        size[:] = [1080, 2400]
        host.panels_orientation(16)
        host.panels_orientation(PANELS_PORTRAIT_MS)
        self.assertFalse(game.panels_open)                                   # turned back: off
        host.orientation.release.assert_called_once_with('activity')
        game.panels_open = True
        host.panels_orientation(16)
        host.panels_orientation(PANELS_ROTATE_MS)
        self.assertFalse(game.panels_open)                                   # never turned: off
        game.panels_open, size[:] = True, [2400, 1080]
        host.panels_orientation(16)
        game.panels_open = False                                             # switched off in Options
        host.panels_orientation(16)
        self.assertEqual(host.orientation.release.call_count, 3)
        # A near-square screen (a foldable's inner one) is no portrait screen: no turn asked, the panels stay.
        game.panels_open, size[:] = True, [1800, 2000]
        host.panels_orientation(16)
        host.panels_orientation(PANELS_ROTATE_MS)
        self.assertTrue(game.panels_open)
        self.assertEqual(host.orientation.requestLandscape.call_count, 2)


class PinchTests(unittest.TestCase):
    def test_two_fingers_zoom_the_story_tree_about_their_middle(self):
        """The owner's request: pinch zooms the tree panel as desktop's wheel does (zoom_tree), about the point between
        the fingers, and that point carries the tree along (UIScrollView's pinch); the first finger's mouse events
        stop meanwhile, so a pinch is never a tap or a drag."""
        import math
        import pygame
        host = Host.__new__(Host)
        zooms, scrolls = [], []
        panels = SimpleNamespace(ZOOM_STEP=1.15, tree_rect=pygame.Rect(0, 0, 400, 1000), tree_scale=0.5,
                                 zoom_tree=lambda notches, point: zooms.append((notches, point)),
                                 scroll_tree=lambda down, across: scrolls.append((down, across)))
        fling = Mock()
        game = SimpleNamespace(side_panels=panels, tree_drag=['down'], tree_fling=fling)
        handled = []
        host.app = SimpleNamespace(screen='game', game=game, window=SimpleNamespace(get_size=lambda: (1000, 1000)),
                                   handle_event=handled.append, active=True)

        def touch(kind, finger, x, y):
            return pygame.event.Event(kind, finger_id=finger, x=x, y=y, dx=0, dy=0, touch_id=0)

        host.event(touch(pygame.FINGERDOWN, 1, .1, .5))
        host.event(touch(pygame.FINGERDOWN, 2, .3, .5))
        self.assertIsNone(game.tree_drag)
        fling.stop.assert_called_once_with()                            # a gliding tree stops under the fingers
        host.event(pygame.event.Event(pygame.MOUSEMOTION, pos=(100, 500), rel=(0, 0), buttons=(1, 0, 0)))
        self.assertEqual(handled, [])                                   # swallowed while pinching
        host.event(touch(pygame.FINGERMOTION, 2, .35, .5))              # 200 -> 250 px apart
        notches, point = zooms[0]
        self.assertAlmostEqual(notches, math.log(250 / 200) / math.log(1.15))
        self.assertEqual(point, (225.0, 500.0))
        self.assertEqual(scrolls, [(-0.0, -50.0)])                      # the middle moved 25 px right at scale 0.5
        host.event(touch(pygame.FINGERUP, 1, .1, .5))
        host.event(touch(pygame.FINGERUP, 2, .35, .5))
        host.event(pygame.event.Event(pygame.MOUSEMOTION, pos=(100, 500), rel=(0, 0), buttons=(0, 0, 0)))
        self.assertEqual(len(handled), 1)                               # back to ordinary input

    def test_a_lost_finger_up_never_counts_as_touching(self):
        """A FINGERUP the one-input-per-frame rule used to drop left a finger behind, and the next two-finger pinch
        counted three: SDL's own list of fingers down wins."""
        import pygame
        from unittest.mock import patch
        from pygame._sdl2 import touch
        host = Host.__new__(Host)
        host.app = SimpleNamespace(screen='menu', game=None, window=SimpleNamespace(get_size=lambda: (100, 100)))
        host.fingers = {7: (5, 5)}                                      # lifted long ago
        with patch.object(touch, 'get_num_fingers', return_value=2),                 patch.object(touch, 'get_finger', side_effect=lambda device, i: {'id': (1, 2)[i]}):
            host.event(pygame.event.Event(pygame.FINGERDOWN, finger_id=1, x=.1, y=.1, dx=0, dy=0, touch_id=0))
            host.event(pygame.event.Event(pygame.FINGERDOWN, finger_id=2, x=.2, y=.1, dx=0, dy=0, touch_id=0))
        self.assertEqual(set(host.fingers), {1, 2})
        self.assertTrue(host.pinching)


class LinkTests(unittest.TestCase):
    def test_a_storys_link_goes_to_the_host(self):
        """A script link (a novel's "Yes, please!") and the Faceplace wall's open through the app's opener (the
        Android host's ACTION_VIEW intent): Python's webbrowser has no Android browser."""
        from exp_runtime.desktop import Desktop
        opened = []
        Desktop._open_link(SimpleNamespace(url_opener=opened.append), 'https://example.com/story')
        self.assertEqual(opened, ['https://example.com/story'])


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        import pygame
        self.pg = pygame
        self.host = Host.__new__(Host)
        self.host.app = SimpleNamespace(active=True, game=SimpleNamespace(session=object()),
                                        state=SimpleNamespace(checkpoint=Mock()))
        def handle(event):
            if event.type in (pygame.WINDOWFOCUSGAINED, pygame.WINDOWFOCUSLOST):
                self.host.app.active = event.type == pygame.WINDOWFOCUSGAINED
            return True
        self.host.app.handle_event = Mock(side_effect=handle)
        self.host.app._attempt = lambda operation: operation()

    def test_background_checkpoints_once_and_foreground_reactivates(self):
        for kind in (self.pg.APP_WILLENTERBACKGROUND, self.pg.APP_DIDENTERBACKGROUND):
            self.assertTrue(self.host.event(self.pg.event.Event(kind)))
        self.host.app.state.checkpoint.assert_called_once_with(self.host.app.game.session)
        self.assertFalse(self.host.app.active)
        self.host.event(self.pg.event.Event(self.pg.APP_WILLENTERFOREGROUND))
        self.assertFalse(self.host.app.active)
        self.host.event(self.pg.event.Event(self.pg.APP_DIDENTERFOREGROUND))
        self.assertTrue(self.host.app.active)

    def test_android_back_uses_existing_escape_navigation(self):
        event = self.pg.event.Event(self.pg.KEYDOWN, key=self.pg.K_AC_BACK, unicode='', mod=0)
        self.host.event(event)
        translated = self.host.app.handle_event.call_args.args[0]
        self.assertEqual(translated.key, self.pg.K_ESCAPE)
        self.assertEqual(translated.mod, 0)

    def test_focus_loss_before_background_does_not_skip_checkpoint(self):
        self.host.app.active = False
        self.host.event(self.pg.event.Event(self.pg.APP_WILLENTERBACKGROUND))
        self.host.event(self.pg.event.Event(self.pg.APP_DIDENTERBACKGROUND))
        self.host.app.state.checkpoint.assert_called_once_with(self.host.app.game.session)


class StagingTests(unittest.TestCase):
    def test_build_contains_only_owned_sources_and_licenses(self):
        spec = importlib.util.spec_from_file_location('build_android', Path(__file__).resolve().parents[1]
                                                       / 'tools/build_android.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        (module.ROOT / 'build/android').mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=module.ROOT / 'build/android') as root:
            destination = module.stage(Path(root) / 'source')
            self.assertTrue((destination / 'exp_runtime/platforms/android.py').is_file())
            self.assertTrue((destination / 'exp_runtime/cod/profile.py').is_file())
            self.assertFalse((destination / 'exp_runtime/__init__.py').exists())
            self.assertTrue((destination / 'source-manifest.json').is_file())
            forbidden = {'.apk', '.ipa', '.exp', '.sav', '.ttf', '.zip', '.rar'}
            self.assertFalse(any(p.suffix.lower() in forbidden for p in destination.rglob('*')))

    def test_staging_refuses_to_clear_a_path_outside_owned_build_directory(self):
        spec = importlib.util.spec_from_file_location('build_android', Path(__file__).resolve().parents[1]
                                                       / 'tools/build_android.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / 'keep.txt'
            source.write_text('keep')
            with self.assertRaises(ValueError):
                module.stage(Path(root))
            self.assertEqual(source.read_text(), 'keep')


class RecipeCacheTests(unittest.TestCase):
    def test_recipe_edits_preserve_other_compiled_dependencies(self):
        spec = importlib.util.spec_from_file_location('build_android', Path(__file__).resolve().parents[1]
                                                       / 'tools/build_android.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            for name in ('android', 'pygame_ce'):
                path = root / 'android/recipes' / name / '__init__.py'
                path.parent.mkdir(parents=True)
                path.write_text('initial recipe')
            storage = root / 'cache'
            with patch.object(module, 'ROOT', root):
                module.prepare_recipe_cache(storage)
                files = {}
                for name in ('android-sdl2', 'pygame_ce', 'png', 'android_support'):
                    path = storage / 'build/other_builds' / name / 'compiled'
                    path.parent.mkdir(parents=True)
                    path.write_text('compiled')
                    files[name] = path
                installed = storage / 'build/python-installs/shshd/arm64-v8a/pygame'
                installed.mkdir(parents=True)
                (installed / 'surface.so').write_bytes(b'compiled fixture')
                module.prepare_recipe_cache(storage)
                self.assertTrue(all(p.exists() for p in files.values()))
                (root / 'android/recipes/pygame_ce/__init__.py').write_text('edited recipe')
                module.prepare_recipe_cache(storage)
                self.assertFalse(files['pygame_ce'].exists())
                self.assertFalse(installed.exists())
                for name in ('android-sdl2', 'png', 'android_support'):
                    self.assertTrue(files[name].exists())
