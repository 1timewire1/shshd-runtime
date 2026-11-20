"""Claire Hart plan Stage 2, decision M: a translated pack's 4:3 scenes as a 3:4 slice that fills CoD's frame (the episode's
own record, resource 7, first; then its add-on's spec), and the player cutting the picture to it."""
import importlib.util
import io
import json
import os
from types import SimpleNamespace
import unittest

from exp_runtime.backdrop_slices import RESOURCE, decode, encode, slice_box
from exp_runtime.exp import ContentError
from test_look_banks import resources


def with_scenes(pack=31500, own=None, scenes=None):
    episode = resources(pack=pack, own=own)
    chc = episode.library.addon('chc')[1]
    spec = json.loads(chc.contents[26998])
    spec['scenes'] = scenes if scenes is not None else {'Office': [26160, 326], 'Driveway': [26100, 224]}
    chc.contents[26998] = json.dumps(spec).encode()
    return episode


class RecordTests(unittest.TestCase):
    def test_the_record_round_trips_and_refuses_what_it_isnt(self):
        self.assertEqual(RESOURCE, 7)
        self.assertEqual(decode(encode({26160: 300, 26100: 0})), {26160: 300, 26100: 0})
        for bad in (b'nope', json.dumps({'format': 'other', 'version': 1, 'slices': {}}).encode(),
                    json.dumps({'format': 'shshd-backdrop-slices', 'version': 1, 'slices': {'x': 1}}).encode(),
                    json.dumps({'format': 'shshd-backdrop-slices', 'version': 1, 'slices': {'1': -4}}).encode()):
            with self.assertRaises(ContentError):
                decode(bad)
        with self.assertRaises(ContentError):
            encode({26160: -1})

    def test_the_slice_is_three_by_four_and_stays_inside_the_picture(self):
        self.assertEqual(slice_box((1024, 768), 326), (326, 0, 576, 768))
        self.assertEqual(slice_box((1024, 768), 900), (448, 0, 576, 768))
        self.assertEqual(slice_box((1026, 770), 224), (224, 0, 578, 770))
        self.assertEqual(slice_box((400, 768), 50), (0, 0, 400, 768))           # narrower than a slice: whole


class LookupTests(unittest.TestCase):
    def test_the_episodes_own_slice_wins_then_the_addons(self):
        episode = with_scenes(own={25001: b'script', RESOURCE: encode({26160: 100})})
        self.assertEqual(episode.backdrop_slice(26160), 100)
        self.assertEqual(episode.backdrop_slice(26100), 224)
        self.assertIsNone(episode.backdrop_slice(26500))                       # not a scene: drawn as any picture

    def test_only_the_packs_the_profile_names(self):
        self.assertIsNone(with_scenes(pack=31400).backdrop_slice(26160))
        self.assertEqual(with_scenes().backdrop_slice(26160), 326)

    def test_a_bad_record_falls_back_to_the_addon(self):
        with self.assertLogs(level='WARNING'):
            episode = with_scenes(own={25001: b'script', RESOURCE: b'garbage'})
            self.assertEqual(episode.backdrop_slice(26160), 326)


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class PlayerTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        import pygame
        pygame.init()
        pygame.display.set_mode((1, 1))
        self.addCleanup(pygame.quit)

    def test_the_picture_is_cut_to_its_slice_and_marked_to_fill_the_frame(self):
        import pygame
        from exp_runtime.desktop import Desktop, SLICED_BACKDROPS
        picture = pygame.Surface((1024, 768))
        picture.fill((10, 10, 10))
        picture.fill((200, 0, 0), (326, 0, 576, 768))
        fake = SimpleNamespace(images={26160: picture, 26999: picture.copy()},
                               session=SimpleNamespace(resources=with_scenes()))
        Desktop._slice_backdrop(fake, 26160)
        Desktop._slice_backdrop(fake, 26999)                                  # no slice: untouched
        sliced = fake.images[26160]
        self.assertEqual(sliced.get_size(), (576, 768))
        self.assertEqual(sliced.get_at((0, 0))[:3], (200, 0, 0))
        self.assertEqual(sliced.get_at((575, 767))[:3], (200, 0, 0))
        self.assertIn(sliced, SLICED_BACKDROPS)
        self.assertEqual(fake.images[26999].get_size(), (1024, 768))
        self.assertNotIn(fake.images[26999], SLICED_BACKDROPS)
        out = io.BytesIO()                                                    # (still a picture the player can save)
        pygame.image.save(sliced, out, 'x.png')


if __name__ == '__main__':
    unittest.main()
