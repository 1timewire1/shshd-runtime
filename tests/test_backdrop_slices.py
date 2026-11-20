"""Claire Hart plan Stage 2, decision M: a translated pack's 4:3 scenes as a 3:4 slice that fills CoD's frame (the episode's
own record, resource 7, first; then its add-on's spec), and the player cutting the picture to it."""
import importlib.util
import io
import json
import os
from types import SimpleNamespace
import unittest

from exp_runtime.backdrop_slices import PAN, RESOURCE, decode, encode, pan_box, slice_box
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

    def test_it_pans_across_a_quarter_more_about_the_slice(self):
        self.assertEqual(PAN, 1.25)                                             # CoD's own: 480-unit art, a 384-unit frame
        self.assertEqual(pan_box((1024, 768), 326), (254, 0, 720, 768))
        self.assertEqual(pan_box((1024, 768), 0), (0, 0, 720, 768))             # at an edge: all the extra on one side
        self.assertEqual(pan_box((1024, 768), 448), (304, 0, 720, 768))
        self.assertEqual(pan_box((600, 768), 0), (0, 0, 600, 768))              # no wider than the picture


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

    def test_the_picture_is_cut_to_its_pan_window_and_marked(self):
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
        self.assertEqual(sliced.get_size(), (720, 768))                       # 254-974: the slice, 72 px more either side
        self.assertEqual(sliced.get_at((0, 0))[:3], (10, 10, 10))
        self.assertEqual(sliced.get_at((72, 0))[:3], (200, 0, 0))
        self.assertEqual(sliced.get_at((647, 767))[:3], (200, 0, 0))
        self.assertEqual(sliced.get_at((648, 0))[:3], (10, 10, 10))
        self.assertIn(sliced, SLICED_BACKDROPS)
        self.assertEqual(fake.images[26999].get_size(), (1024, 768))
        self.assertNotIn(fake.images[26999], SLICED_BACKDROPS)
        out = io.BytesIO()                                                    # (still a picture the player can save)
        pygame.image.save(sliced, out, 'x.png')

    def test_it_fills_the_frames_height_and_pans_with_the_speaker(self):
        import pygame
        from exp_runtime.desktop import Desktop
        from exp_runtime.location_pan import LocationPan
        panel = SimpleNamespace(location_align=1)
        fake = SimpleNamespace(location_pan=LocationPan(), session=SimpleNamespace(engine=SimpleNamespace(panel=panel)))
        picture = pygame.Surface((720, 768))
        self.assertEqual(Desktop._slice_placement(fake, picture, (384, 512)), (0, 0, 480, 512))   # flush left
        panel.location_align = 3
        x, _, w, _ = Desktop._slice_placement(fake, picture, (384, 512))      # moving right over 0.25 s
        fake.location_pan.since -= 1000
        self.assertEqual(Desktop._slice_placement(fake, picture, (384, 512)), (-96, 0, 480, 512))  # flush right
        x, y, w, h = Desktop._slice_placement(fake, picture, (320, 569))      # a 9:16 frame: as tall, wider
        self.assertEqual((round(w), round(h)), (533, 569))       # 720 x 569 / 768


if __name__ == '__main__':
    unittest.main()
