"""Android host contracts tested without a device or Java runtime."""
import importlib.util
from pathlib import Path
from queue import Queue
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from exp_runtime.platforms.android import Host


class ImportTests(unittest.TestCase):
    def host(self):
        host = Host.__new__(Host)
        host.pending = True
        host.closed = False
        host.results = Queue()
        host.imported = []
        host.app = SimpleNamespace(busy=False, message='', import_paths=Mock())
        host.app._attempt = lambda operation: operation()
        return host

    def test_picker_cancellation_does_not_import_or_replace_progress(self):
        host = self.host()
        host.on_result(Host.REQUEST, 0, None)
        host.poll()
        self.assertFalse(host.pending)
        host.app.import_paths.assert_not_called()

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
