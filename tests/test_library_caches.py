"""shshd-runtime: what a library works out once (owner, 2026-11-21, the g54's round entry): an add-on's JSON parsed once and
shared (Claire Hart's 2.4 MB rounds spec, parsed by the engine and the renderer at a case's first round), and Cause of
Death's HD skins derived from SHS HD's kept in the library's `derived` folder (made in pure Python: 1.9 s at every start's
first choice), never written by a library opened without writing (the Creator's)."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from exp_runtime.content import ContentLibrary


def bare(directory, *, remember_checks=True, addons=()):
    library = ContentLibrary.__new__(ContentLibrary)
    library.directory, library.remember_checks, library.addons = Path(directory), remember_checks, list(addons)
    return library


class LibraryCacheTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_an_addons_json_is_parsed_once_and_shared(self):
        library = bare(self.root, addons=[dict(addon='chcrounds', id='abc')])
        reads = []

        def read(addon, resource):
            reads.append((addon, resource))
            return json.dumps({'scenes': {'Office': {}}}).encode()
        with mock.patch.object(ContentLibrary, 'addon_resource', lambda self, addon, resource: read(addon, resource)):
            first = library.addon_json('chcrounds', 26000)
            self.assertIs(library.addon_json('chcrounds', 26000), first)
            self.assertIsNone(library.addon_json('missing', 26000))
        self.assertEqual(reads, [('chcrounds', 26000)])

    def test_derived_art_is_made_once_and_kept_on_disk(self):
        made = []

        def compute():
            made.append(1)
            return b'derived pixels'
        self.assertEqual(bare(self.root)._derived('skin204', (b'cod', b'hd'), compute), b'derived pixels')
        kept = list((self.root / 'derived').glob('skin204-*.bin'))
        self.assertEqual(len(kept), 1)
        self.assertEqual(list((self.root / 'derived').glob('*.part')), [])
        # The next start reads it back; other inputs (another bundle) make their own.
        self.assertEqual(bare(self.root)._derived('skin204', (b'cod', b'hd'), compute), b'derived pixels')
        self.assertEqual(made, [1])
        bare(self.root)._derived('skin204', (b'cod', b'other hd'), compute)
        self.assertEqual(made, [1, 1])

    def test_a_library_opened_without_writing_keeps_derived_art_in_memory_only(self):
        library = bare(self.root, remember_checks=False)
        self.assertEqual(library._derived('common', (b'cod', b'hd'), lambda: b'x'), b'x')
        self.assertEqual(library._derived('common', (b'cod', b'hd'), lambda: b'not again'), b'x')
        self.assertFalse((self.root / 'derived').exists())


if __name__ == '__main__':
    unittest.main()
