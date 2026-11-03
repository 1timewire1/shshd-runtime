"""shshd-runtime addons (addons.py, SCHEMA.md "Addon extension"): shared resource packs that episodes declare."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from exp_runtime.addons import addon_record, normalize, provides_bytes, requires_bytes
from exp_runtime.content import ContentError, ContentLibrary, ExpArchive, digest, import_game
from test_content import FAKE_NATIVE, archive, make_apk, metadata
from test_vm import program


def addon(revision=1, art=b'addon art', addon_id='shsnr'):
    return archive({1: metadata('A test addon'), 4: provides_bytes(addon_id, 'A test addon', revision),
                    26000: b'addon background', 26001: art, 26999: b'addon backdrop'})


def episode(title='An episode with an addon', requires=(('shsnr', 1),), own=None):
    records = {1: metadata(title), 25001: program(0x33).to_bytes(), 26000: b'episode background'}
    if requires:
        records[4] = requires_bytes(requires)
    records.update(own or {})
    return archive(records)


class AddonRecordTests(unittest.TestCase):
    def test_an_addon_names_itself_and_an_episode_lists_what_it_needs(self):
        self.assertEqual(addon_record(ExpArchive(addon(3))),
                         ('provides', dict(id='shsnr', title='A test addon', revision=3)))
        self.assertEqual(addon_record(ExpArchive(episode(requires=(('shsnr', 2), ('x360', 1))))),
                         ('requires', (('shsnr', 2), ('x360', 1))))
        self.assertIsNone(addon_record(ExpArchive(episode(requires=()))))

    def test_malformed_records_are_refused(self):
        base = dict(format='shshd-addons', version=1)
        for bad in (dict(base, version=2), dict(base), dict(base, provides={}, requires=[]),
                    dict(base, provides=dict(id='Bad Id', title='x', revision=1)),
                    dict(base, provides=dict(id='ok', title='', revision=1)),
                    dict(base, provides=dict(id='ok', title='x', revision=0)),
                    dict(base, requires=[]), dict(base, requires=[dict(id='ok', revision=1)] * 2),
                    dict(base, requires=[dict(id='ok')])):
            with self.subTest(record=bad), self.assertRaises(ValueError):
                normalize(bad)
        broken = archive({1: metadata(), 4: b'SHSHD-ADDONS\0{not json'})
        with self.assertRaisesRegex(ContentError, 'Invalid addon record'):
            addon_record(ExpArchive(broken))


class AddonLibraryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        profile = patch('exp_runtime.shs.content.NATIVE_SHA256', digest(FAKE_NATIVE))
        profile.start()
        self.addCleanup(profile.stop)
        self.apk = self.root / 'user.apk'
        make_apk(self.apk, archive({1: metadata(), 25001: program(0x33).to_bytes()}))
        self.target = self.root / 'library'
        import_game(self.apk, [], self.target)

    def write(self, name, data):
        path = self.root / name
        path.write_bytes(data)
        return path

    def test_an_addon_is_kept_apart_and_its_episodes_read_through_it(self):
        with ContentLibrary(self.target) as library:
            count = library.add_episodes([self.write('pack.exp', addon()), self.write('story.exp', episode())])
            self.assertEqual(count, 2)
            self.assertEqual([a['addon'] for a in library.addons], ['shsnr'])
            self.assertNotIn('pack.exp', [e['name'] for e in library.episodes])     # no picker lists it
            resources = library.open_episode('story.exp')
            self.assertEqual(resources.missing_addons(), [])
            resources.check_addons()
            self.assertEqual(resources.read_asset(26000), b'episode background')     # the episode's own copy wins
            self.assertEqual(resources.read_asset(26001), b'addon art')
            self.assertEqual(resources.raw_asset(26999), b'addon backdrop')
            self.assertTrue(resources.exists(26001))
            self.assertFalse(resources.exists(26002))
        with ContentLibrary(self.target) as reopened:                               # the manifest keeps it
            self.assertEqual(reopened.open_episode('story.exp').read_asset(26001), b'addon art')

    def test_an_episode_without_its_addon_says_so_before_playing(self):
        with ContentLibrary(self.target) as library:
            library.add_episodes([self.write('story.exp', episode(requires=(('shsnr', 2),)))])
            resources = library.open_episode('story.exp')                 # indexing and previews still open it
            self.assertEqual(resources.missing_addons(), [('shsnr', 2)])
            self.assertFalse(resources.exists(26001))
            with self.assertRaisesRegex(ContentError, '"shsnr" \\(revision 2 or later\\) addon'):
                resources.check_addons()
            library.add_episodes([self.write('old.exp', addon(1))])        # too old a revision
            self.assertEqual(library.open_episode('story.exp').missing_addons(), [('shsnr', 2)])
            library.add_episodes([self.write('new.exp', addon(2))])
            self.assertEqual(library.open_episode('story.exp').missing_addons(), [])

    def test_a_newer_revision_replaces_the_older_and_an_older_one_is_ignored(self):
        with ContentLibrary(self.target) as library:
            library.add_episodes([self.write('v1.exp', addon(1))])
            old = self.target / library.addons[0]['file']
            library.add_episodes([self.write('v2.exp', addon(2, art=b'redrawn'))])
            self.assertEqual([(a['addon'], a['revision']) for a in library.addons], [('shsnr', 2)])
            self.assertFalse(old.exists())                                  # the older file goes with its entry
            self.assertEqual(library.add_episodes([self.write('v1-again.exp', addon(1))]), 0)
            rebuilt = library.add_episodes([self.write('v2-rebuilt.exp', addon(2, art=b'rebuilt'))])
            self.assertEqual(rebuilt, 1)                                    # same revision, new build: replaces
            library.add_episodes([self.write('story.exp', episode())])
            self.assertEqual(library.open_episode('story.exp').read_asset(26001), b'rebuilt')

    def test_an_invalid_addon_entry_in_the_manifest_is_refused(self):
        with ContentLibrary(self.target) as library:
            library.add_episodes([self.write('pack.exp', addon())])
        manifest = json.loads((self.target / 'library.json').read_text(encoding='utf-8'))
        manifest['addons'][0]['revision'] = 0
        (self.target / 'library.json').write_text(json.dumps(manifest), encoding='utf-8')
        with self.assertRaisesRegex(ContentError, 'Invalid addon entry'):
            ContentLibrary(self.target)


if __name__ == '__main__':
    unittest.main()
