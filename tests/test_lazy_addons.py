"""Claire Hart plan Stage 0, O: an addon is read a record at a time (LazyExpArchive), its file hashed once and then known by
its size and time, so a large one (the rounds, about 480 MB) is never held in memory or read whole at each open."""
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from exp_runtime.content import ContentError, ContentLibrary, ExpArchive
from exp_runtime.exp import LazyExpArchive
import test_addons
from test_addons import addon, episode
from test_content import archive, metadata


class LazyArchiveTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def write(self, data):
        path = self.root / 'pack.exp'
        path.write_bytes(data)
        return path

    def test_it_reads_what_the_whole_archive_reads(self):
        data = archive({1: metadata('Lazy'), 26000: b'plain record', 26001: b'packed record ' * 40}, compressed={26001})
        lazy, whole = LazyExpArchive(self.write(data)), ExpArchive(data)
        self.assertEqual(lazy.entries, whole.entries)
        for resource in whole.entries:
            self.assertEqual(lazy.read(resource), whole.read(resource))
        self.assertEqual(lazy.metadata(), whole.metadata())
        with self.assertRaises(ContentError):
            lazy.read(26002)

    def test_a_broken_index_or_record_is_refused(self):
        good = archive({1: metadata('Lazy'), 26000: b'record'})
        with self.assertRaises(ContentError):
            LazyExpArchive(self.write(b'NOTEXP' + good[6:]))
        past = bytearray(good)
        struct.pack_into('>I', past, 9 + 2, len(good) + 100)          # the first record's offset past the end
        with self.assertRaises(ContentError):
            LazyExpArchive(self.write(bytes(past)))
        lazy = LazyExpArchive(self.write(good[:-3]))                    # the last record cut short
        with self.assertRaises(ContentError):
            lazy.read(26000)


class LazyAddonTests(unittest.TestCase):
    setUp = test_addons.AddonLibraryTests.setUp         # a library made from a test APK (test_addons)
    write = test_addons.AddonLibraryTests.write

    def test_an_addon_opens_lazily_and_is_hashed_once(self):
        from exp_runtime import content
        with ContentLibrary(self.target) as library:
            library.add_episodes([self.write('pack.exp', addon()), self.write('story.exp', episode())])
        with patch('exp_runtime.content.file_digest', wraps=content.file_digest) as hashed:
            with ContentLibrary(self.target) as library:
                record, held = library.addon('shsnr')
                self.assertIsInstance(held, LazyExpArchive)
                self.assertEqual(held.read(26001), b'addon art')
                self.assertEqual(library.open_episode('story.exp').read_asset(26001), b'addon art')
            addons_hashed = lambda: sum(1 for call in hashed.call_args_list if call.args[0].suffix == '.exp'
                                        and call.args[0].name == Path(record['file']).name)
            self.assertEqual(addons_hashed(), 1)
            with ContentLibrary(self.target) as library:
                library.addon('shsnr')
            self.assertEqual(addons_hashed(), 1)                    # known by its size and time: not hashed again
        checks = json.loads((self.target / ContentLibrary.ADDON_CHECKS).read_text(encoding='utf-8'))
        self.assertEqual(list(checks), [Path(record['file']).name])
        # A file changed since is hashed again, and refused.
        path = self.target / record['file']
        data = bytearray(path.read_bytes())
        data[-1] ^= 0xff
        path.write_bytes(bytes(data))
        os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 1_000_000_000))
        with ContentLibrary(self.target) as library:
            with self.assertRaises(ContentError):
                library.addon('shsnr')


if __name__ == '__main__':
    unittest.main()
