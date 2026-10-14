"""Native decoder discovery in component checkouts and installed applications."""
import ctypes.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from exp_runtime import rar
from tools import build_rar


class RarLibraryTests(unittest.TestCase):
    def setUp(self):
        rar.library.cache_clear()
        self.addCleanup(rar.library.cache_clear)

    def test_component_checkout_finds_the_build_helpers_output(self):
        # The runtime and build helper must agree even after source files move
        # into component packages. No system decoder may mask a wrong path.
        for platform, relative in (('win32', 'bin/archive.dll'),
                                   ('linux', 'lib/libarchive.so.13')):
            with self.subTest(platform=platform):
                rar.library.cache_clear()
                expected = build_rar.ROOT / 'build/rar/install' / relative
                decoder = Mock()

                def load(path):
                    if Path(path) == expected:
                        return decoder
                    raise OSError(f'No decoder at {path}')

                with patch.object(rar.sys, 'platform', platform), \
                        patch('ctypes.util.find_library', return_value=None), \
                        patch.object(rar.c, 'CDLL', side_effect=load) as cdll:
                    self.assertIs(rar.library(), decoder)
                    self.assertIn(str(expected), [call.args[0] for call in cdll.call_args_list])

    def test_frozen_app_prefers_its_bundled_decoder(self):
        for platform, name in (('win32', 'archive.dll'), ('linux', 'libarchive.so.13')):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as temporary:
                rar.library.cache_clear()
                bundle = Path(temporary)
                decoder = Mock()
                with patch.object(rar.sys, 'platform', platform), \
                        patch.object(rar.sys, '_MEIPASS', str(bundle), create=True), \
                        patch('ctypes.util.find_library', return_value='system-archive'), \
                        patch.object(rar.c, 'CDLL', return_value=decoder) as cdll:
                    self.assertIs(rar.library(), decoder)
                    cdll.assert_called_once_with(str(bundle / name))

    def test_installed_engine_can_use_a_system_decoder_without_build_tools(self):
        with tempfile.TemporaryDirectory() as temporary:
            module = Path(temporary) / 'site-packages/exp_runtime/rar.py'
            decoder = Mock()

            def load(path):
                if path == 'system-archive':
                    return decoder
                raise OSError('Not an installed library')

            with patch.object(rar, '__file__', str(module)), \
                    patch.object(rar.sys, 'platform', 'linux'), \
                    patch('ctypes.util.find_library', return_value='system-archive'), \
                    patch.object(rar.c, 'CDLL', side_effect=load):
                self.assertIs(rar.library(), decoder)

    def test_missing_rar5_support_tries_the_next_decoder(self):
        incomplete, decoder = Mock(spec=['archive_read_new', 'archive_read_support_format_rar']), Mock()
        with patch.object(rar.sys, 'platform', 'win32'), \
                patch.object(rar.sys, '_MEIPASS', '/authored-bundle', create=True), \
                patch('ctypes.util.find_library', return_value='system-archive'), \
                patch.object(rar.c, 'CDLL', side_effect=[incomplete, decoder]) as cdll:
            self.assertIs(rar.library(), decoder)
            self.assertEqual(cdll.call_args.args, ('system-archive',))

    def test_no_usable_decoder_keeps_the_actionable_error(self):
        with patch.object(rar.sys, 'platform', 'win32'), \
                patch('ctypes.util.find_library', return_value=None), \
                patch.object(rar.c, 'CDLL', side_effect=OSError('Missing library')):
            with self.assertRaisesRegex(rar.RarError, 'RAR support needs libarchive with RAR5 support'):
                rar.library()
