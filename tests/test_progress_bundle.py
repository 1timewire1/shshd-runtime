"""Progress bundles (Data Management's Back Up / Restore Progress, owner 2026-10-30)."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from exp_runtime.progress_bundle import (MANIFEST, PLAYER, BundleError, read_manifest, restore_bundle, write_bundle)


def library_folder(root, saves, *, tree=True):
    directory = Path(root)
    (directory / 'saves').mkdir(parents=True)
    for name, text in saves.items():
        (directory / 'saves' / name).write_text(text)
    if tree:
        (directory / 'dtview_tree.json').write_text('{"tree": 1}')
        (directory / 'dtsaves' / 'k').mkdir(parents=True)
        (directory / 'dtsaves' / '1.json.gz').write_bytes(b'scene')
        (directory / 'dtsaves' / 'k' / '2.json.gz').write_bytes(b'other scene')
    (directory / 'content').mkdir()
    (directory / 'content' / 'a.exp').write_bytes(b'episode')          # never in a bundle
    return directory


class BundleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_a_bundle_carries_the_progress_files_and_names_and_restores_them_whole(self):
        source = library_folder(self.root / 'one', {'a.shs-auto.json': 'A', 'a.shs-shot.jpg': 'pic', 'b.shs-save.json': 'B'})
        player = dict(names={'$USR': 'Zoe'}, name_sets={'nr': {'$Emily': 'Em'}}, warp_unlocked=True, music=False)
        target = self.root / 'backups' / 'one.zip'
        manifest = write_bundle(source, 'shs', player, {'a': 'Episode A'}, target)
        self.assertEqual([entry['id'] for entry in manifest['saved']], ['a', 'b'])
        self.assertEqual((manifest['saved'][0]['title'], manifest['trees'], manifest['names']), ('Episode A', 2, 2))
        with ZipFile(target) as bundle:
            self.assertEqual(sorted(bundle.namelist()), sorted([MANIFEST, PLAYER, 'dtview_tree.json', 'dtsaves/1.json.gz',
                                                                'dtsaves/k/2.json.gz', 'saves/a.shs-auto.json',
                                                                'saves/a.shs-shot.jpg', 'saves/b.shs-save.json']))
            self.assertNotIn('music', json.loads(bundle.read(PLAYER)))      # options are not progress
        self.assertEqual(read_manifest(target)['game'], 'shs')
        other = library_folder(self.root / 'two', {'c.shs-auto.json': 'C'}, tree=False)
        (other / 'dtview').mkdir()
        (other / 'dtview' / 'x.json').write_text('{}')
        restored, names = restore_bundle(other, target, 'shs')
        self.assertEqual(names, {'names': {'$USR': 'Zoe'}, 'name_sets': {'nr': {'$Emily': 'Em'}}, 'warp_unlocked': True})
        self.assertEqual(sorted(p.name for p in (other / 'saves').iterdir()),
                         ['a.shs-auto.json', 'a.shs-shot.jpg', 'b.shs-save.json'])     # replaced, not merged
        self.assertFalse((other / 'dtview').exists())
        self.assertEqual((other / 'dtsaves' / 'k' / '2.json.gz').read_bytes(), b'other scene')
        self.assertTrue((other / 'content' / 'a.exp').exists())
        self.assertEqual([p.name for p in other.iterdir() if p.name.startswith('.')], [])   # no stage left behind

    def test_a_bundle_of_the_other_game_or_with_a_stray_file_changes_nothing(self):
        source = library_folder(self.root / 'one', {'a.shs-auto.json': 'A'})
        target = self.root / 'one.zip'
        write_bundle(source, 'shs', {}, {}, target)
        other = library_folder(self.root / 'two', {'c.shs-auto.json': 'C'}, tree=False)
        with self.assertRaises(BundleError):
            restore_bundle(other, target, 'cod')
        bad = self.root / 'bad.zip'
        with ZipFile(target) as bundle, ZipFile(bad, 'w') as copy:
            for name in bundle.namelist():
                copy.writestr(name, bundle.read(name))
            copy.writestr('saves/../content/a.exp', b'replaced')
        with self.assertRaises(BundleError):
            restore_bundle(other, bad, 'shs')
        not_a_bundle = self.root / 'x.zip'
        with ZipFile(not_a_bundle, 'w') as copy:
            copy.writestr('hello.txt', 'hi')
        with self.assertRaises(BundleError):
            read_manifest(not_a_bundle)
        self.assertEqual([p.name for p in (other / 'saves').iterdir()], ['c.shs-auto.json'])
        self.assertEqual((other / 'content' / 'a.exp').read_bytes(), b'episode')

    def test_a_swap_that_fails_puts_the_librarys_own_progress_back(self):
        source = library_folder(self.root / 'one', {'a.shs-auto.json': 'A'})
        target = self.root / 'one.zip'
        write_bundle(source, 'shs', {}, {}, target)
        other = library_folder(self.root / 'two', {'c.shs-auto.json': 'C'})
        real_replace = Path.replace
        calls = []

        def failing(self, destination):
            calls.append(self.name)
            if len(calls) == 5:                     # partway through moving the bundle's files in
                raise OSError('disk full')
            return real_replace(self, destination)
        with patch.object(Path, 'replace', failing), self.assertRaises(OSError):
            restore_bundle(other, target, 'shs')
        self.assertEqual([p.name for p in (other / 'saves').iterdir()], ['c.shs-auto.json'])
        self.assertEqual((other / 'dtview_tree.json').read_text(), '{"tree": 1}')
        self.assertTrue((other / 'dtsaves' / 'k' / '2.json.gz').exists())


if __name__ == '__main__':
    unittest.main()
