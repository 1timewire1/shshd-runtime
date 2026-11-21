"""shshd-runtime: the add-on games' picker icons (tools/translate/addon_icons.py; owner, 2026-11-21): the records it adds
and the patch that puts them into a built add-on, raising its revision and keeping every other record as it was.
Authored pictures only: the real icons come from the owner's reference files."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from exp_runtime.addons import RESOURCE as ADDON_RECORD, addon_record, provides_bytes
from exp_runtime.exp import LazyExpArchive, encode_exp

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools' / 'translate'))
HAS_PIL = importlib.util.find_spec('PIL') is not None


@unittest.skipUnless(HAS_PIL, 'Pillow is unavailable')
class AddonIconTests(unittest.TestCase):
    def setUp(self):
        import addon_icons
        from PIL import Image
        self.icons = addon_icons
        square = lambda colour: (lambda reference: Image.new('RGBA', (40, 40), colour))
        self.fake = {'shsbrew': [('brew07', "SHS '07", square('red'), True, '07'), ('brew08', "SHS '08", square('blue'), False, '08')],
                     'shs11': [('shs11', "SHS '11", square('green'), True, None)]}

    def test_records_spec_and_pictures(self):
        with patch.dict(self.icons.ICONS, self.fake, clear=True):
            records = self.icons.icon_resources('shsbrew', Path('unused'))
            self.assertEqual(self.icons.icon_resources('shsdsi', Path('unused')), {})
        games = self.icons.read_spec(records[self.icons.SPEC_ID])
        self.assertEqual([(g['key'], g['icon'], g['smooth'], g.get('edition')) for g in games],
                         [('brew07', 26951, True, '07'), ('brew08', 26952, False, '08')])
        self.assertTrue(all(records[g['icon']].startswith(b'\x89PNG') for g in games))
        with self.assertRaises(ValueError):
            self.icons.read_spec(json.dumps({'version': 1, 'games': []}).encode())

    def test_patch_raises_the_revision_and_keeps_every_record(self):
        original = {ADDON_RECORD: provides_bytes('shs11', "Surviving High School '11", 3), 1: b'metadata', 26960: b'look',
                    27000: bytes(range(256)) * 4}
        with tempfile.TemporaryDirectory() as directory, patch.dict(self.icons.ICONS, self.fake, clear=True):
            source, target = Path(directory) / 'in.exp', Path(directory) / 'out.exp'
            source.write_bytes(encode_exp(original))
            self.assertEqual(self.icons.patch(source, target, Path('unused')), ('shs11', 3, 4))
            patched = LazyExpArchive(target)
            self.assertEqual(addon_record(patched), ('provides', {'id': 'shs11', 'title': "Surviving High School '11", 'revision': 4}))
            for resource in (1, 26960, 27000):
                self.assertEqual(patched.read(resource), original[resource])
            self.assertEqual(set(patched.entries) - set(original), {26950, 26951})
            with self.assertRaises(ValueError):             # an episode, not an add-on
                episode = Path(directory) / 'episode.exp'
                episode.write_bytes(encode_exp({1: b'metadata'}))
                self.icons.patch(episode, Path(directory) / 'x.exp', Path('unused'))

    def test_a_build_without_the_reference_files_warns_and_goes_on(self):
        resources = {1: b'metadata'}
        with patch.dict(self.icons.ICONS, {'shs11': [('shs11', "SHS '11", lambda r: (r / 'missing.png').read_bytes(), True, None)]}):
            with patch('sys.stderr'):
                self.icons.add_icons(resources, 'shs11', Path('nowhere'))
        self.assertEqual(resources, {1: b'metadata'})


if __name__ == '__main__':
    unittest.main()
