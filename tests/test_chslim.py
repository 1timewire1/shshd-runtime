"""shshd-runtime: the chslim addon (tools/translate/chslim.py) and how the player reads it: Claire Hart's sharper originals of Cause
of Death's portraits, found by a hash of CoD's picture, and addons a later one supersedes."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from exp_runtime.addons import normalize, provides_bytes
from exp_runtime.content import ContentLibrary, EpisodeResources, digest, import_game
from test_addons import addon, episode
from test_content import FAKE_NATIVE, archive, make_apk, metadata
from test_hd_twins import Archive
from test_vm import program

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools' / 'translate'))
HAS_PIL = importlib.util.find_spec('PIL') is not None


def key(data):
    return hashlib.sha1(data).hexdigest()[:20]


class SupersedingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        profile = patch('exp_runtime.shs.content.NATIVE_SHA256', digest(FAKE_NATIVE))
        profile.start()
        self.addCleanup(profile.stop)
        apk = Path(self.temporary.name) / 'game.apk'
        make_apk(apk, archive({1: metadata(), 25001: program(0x33).to_bytes()}))
        self.folder = Path(self.temporary.name) / 'library'
        import_game(apk, [], self.folder)
        self.library = ContentLibrary(self.folder)
        self.addCleanup(self.library.close)

    def add(self, name, data):
        path = Path(self.temporary.name) / name
        path.write_bytes(data)
        self.library.add_episodes([path])

    def full(self, revision=1, stands_in=2):
        return archive({1: metadata('The whole game'),
                        4: provides_bytes('chfull', 'The whole game', revision, [('chslim', stands_in)]), 26001: b'the same art',
                        26002: b'more art'})

    def test_a_record_names_what_it_supersedes(self):
        base = dict(format='shshd-addons', version=1)
        kind, provides = normalize(dict(base, provides=dict(id='chfull', title='All', revision=1,
                                                            supersedes=[dict(id='chslim', revision=2)])))
        self.assertEqual((kind, provides['supersedes']), ('provides', (('chslim', 2),)))
        for bad in ([], [dict(id='chfull', revision=1)], [dict(id='a', revision=1), dict(id='a', revision=1)], 'chslim'):
            with self.assertRaises(ValueError):
                normalize(dict(base, provides=dict(id='chfull', title='All', revision=1, supersedes=bad)))

    def test_importing_the_full_addon_deletes_the_slim_one_and_stands_in_for_it(self):
        self.add('slim.exp', addon(2, art=b'the same art', addon_id='chslim'))
        slim = next(a for a in self.library.addons if a['addon'] == 'chslim')
        self.add('story.exp', episode('A story', requires=(('chslim', 2),)))
        self.add('full.exp', self.full())
        self.assertEqual([a['addon'] for a in self.library.addons], ['chfull'])
        self.assertFalse((self.folder / slim['file']).exists())
        record = next(r for r in self.library.episodes if r['titles'][0].startswith('A story'))
        resources = self.library.open_episode(record['id'])
        self.assertEqual(resources.missing_addons(), [])
        resources.check_addons()
        self.assertEqual(resources.read_asset(26001), b'the same art')
        reopened = ContentLibrary(self.folder)                      # and it lasts
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.addon('chslim')[0]['addon'], 'chfull')
        self.assertEqual(reopened.addon('chslim')[0]['revision'], 2)

    def test_the_slim_addon_stays_out_once_the_full_one_is_there(self):
        self.add('full.exp', self.full())
        self.add('slim.exp', addon(2, addon_id='chslim'))
        self.assertEqual([a['addon'] for a in self.library.addons], ['chfull'])
        self.add('slim3.exp', addon(3, addon_id='chslim'))           # a newer one than it stands in for comes back
        self.assertEqual(sorted(a['addon'] for a in self.library.addons), ['chfull', 'chslim'])

    def test_a_story_needing_more_than_it_stands_in_for_says_so(self):
        self.add('full.exp', self.full(stands_in=1))
        self.add('story.exp', episode('A story', requires=(('chslim', 2),)))
        record = next(r for r in self.library.episodes if r['titles'][0].startswith('A story'))
        self.assertEqual(self.library.open_episode(record['id']).missing_addons(), [('chslim', 2)])


class AddonPortraitTests(unittest.TestCase):
    """The read path, in a library of the game whose profile names the addon."""

    def setUp(self):
        self.small, self.twin = b'\x89PNG small', b'\x89PNG a second with the same art'
        self.sharp, self.shocked = b'sharp', b'shocked'
        pack = Archive({28000: b'', 28010: self.sharp, 29001: self.shocked})
        spec = dict(portraits={key(self.small): 28010}, resources={f'{key(self.small)}:2229': 29001})
        record = dict(id='x', addon='chslim', revision=1)
        self.library = SimpleNamespace(game_id='cod', ch_portraits=True, hd_art_mode='off', addon=lambda name: (record, pack) if name == 'chslim' else None,
                                       portrait_addon_map=lambda addon: spec, android_asset=lambda rid: self.small if rid in (2228, 2229) else b'other',
                                       hd_asset=lambda rid: None)

    def resources(self):
        return EpisodeResources(self.library, dict(variant='standard', pack_id=1), Archive({26030: self.small, 26031: b'no match'}))

    def test_a_picture_is_found_by_its_bytes_whatever_its_id(self):
        resources = self.resources()
        self.assertEqual(resources.read_asset(26030), self.sharp)
        self.assertEqual(resources.read_asset(2228), self.sharp)
        self.assertEqual(resources.read_asset(26031), b'no match')
        self.assertEqual(resources.standard_portrait(26030), self.small)    # the player sizes it to this
        self.assertIsNone(resources.standard_portrait(26031))

    def test_one_picture_serving_two_expressions_can_differ_on_the_one_the_addon_has(self):
        resources = self.resources()
        self.assertEqual(resources.read_asset(2228), self.sharp)
        self.assertEqual(resources.read_asset(2229), self.shocked)

    def test_the_switch_and_the_game_decide(self):
        self.library.ch_portraits = False
        self.assertEqual(self.resources().read_asset(26030), self.small)
        self.assertIsNone(self.resources().standard_portrait(26030))
        self.library.ch_portraits, self.library.game_id = True, 'shs'
        self.library.twin_store = lambda: None
        self.assertEqual(self.resources().read_asset(26030), self.small)


@unittest.skipUnless(HAS_PIL, 'chslim.py draws with Pillow')
class BuilderTests(unittest.TestCase):
    def test_the_pairs_file_gives_the_confirmed_ones(self):
        import chslim
        pairs = chslim.read_pairs('# a comment\nportrait 0031 = none   # not a match\n'
                                  'portrait 0061 = references/characters/A/Avatar_A_Normal [crop -1,-1,459,501]\n'
                                  '#? portrait 0062 = references/characters/A/x\nbackground 0054 = references/backgrounds/B [crop 1,1,512,768]\n')
        self.assertEqual(pairs, {'0061': ('references/characters/A/Avatar_A_Normal', (-1, -1, 459, 501))})

    def test_a_portraits_id_lasts_whatever_else_the_pack_holds(self):
        import chslim
        ids = chslim.portrait_ids(['references/characters/B/x', 'references/characters/A/x', 'references/characters/C/x'])
        self.assertEqual(ids['references/characters/A/x'], chslim.PORTRAIT_BASE)
        self.assertEqual(ids['references/characters/C/x'], chslim.PORTRAIT_BASE + 2)
        self.assertLess(chslim.PORTRAIT_BASE + 835, chslim.EDITED_BASE)

    def test_a_crop_past_the_picture_takes_cods_own_for_the_strip(self):
        import chslim
        from PIL import Image
        picture = Image.new('RGBA', (458, 500), (255, 0, 0, 255))
        cod = Image.new('RGBA', (110, 120), (0, 0, 255, 255))
        out = chslim.framed(picture, (-20, 0, 478, 500), cod)
        self.assertEqual(out.size, (220, 240))
        self.assertEqual(out.getpixel((2, 120)), (0, 0, 255, 255))
        self.assertEqual(out.getpixel((200, 120)), (255, 0, 0, 255))

    def test_hashes_come_from_the_librarys_bytes_though_the_catalogues_are_re_encoded(self):
        import chslim
        from PIL import Image

        def encoded(colour, **options):
            out = io.BytesIO()
            Image.new('RGBA', (4, 4), colour).save(out, 'PNG', **options)
            return out.getvalue()
        catalogue, library, resaved, other = encoded((1, 2, 3, 255)), encoded((1, 2, 3, 255), compress_level=0), encoded((1, 2, 3, 255), compress_level=9), encoded((9, 9, 9, 255))
        found = chslim.hashes({'0001': chslim.pixels(catalogue)}, [library, resaved, other, b'not a picture'])
        self.assertEqual(found['0001'], {key(library), key(resaved)})

    def test_sophie_stays_out_of_the_map(self):
        import chslim
        self.assertEqual(chslim.NOT_MAPPED, {'1272', '1273', '1274', '1275'})


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class BackdropTests(unittest.TestCase):
    def test_the_backdrop_covers_the_window_and_steps_back_for_a_library_without_it(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        import pygame
        pygame.init()
        pygame.display.set_mode((1, 1))
        self.addCleanup(pygame.quit)
        from exp_runtime.desktop_cod_main import addon_backdrop
        image = pygame.Surface((32, 18))
        image.fill((0, 200, 180))
        out = io.BytesIO()
        pygame.image.save(image, out, 'x.png')
        pack = Archive({28001: out.getvalue()})
        library = SimpleNamespace(game_id='cod', addon=lambda name: (dict(id='x'), pack),
                                  portrait_addon_map=lambda addon: dict(backdrop=28001))
        surface = addon_backdrop(library, (100, 100))
        self.assertEqual(surface.get_size(), (100, 100))
        self.assertEqual(surface.get_at((1, 1))[:3], (0, 200, 180))
        self.assertIsNone(addon_backdrop(SimpleNamespace(game_id='cod', addon=lambda name: None), (10, 10)))
        self.assertIsNone(addon_backdrop(SimpleNamespace(game_id='shs', addon=lambda name: None), (10, 10)))


if __name__ == '__main__':
    unittest.main()
