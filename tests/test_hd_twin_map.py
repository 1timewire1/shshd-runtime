"""The shipped HD twin map: a library's twin store and coverage built from its own HD episodes (hd_twins.build_from_map)."""
from io import BytesIO
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from exp_runtime.hd_twins import TwinStore, build_from_map, fingerprint


def png(size, colour):
    stream = BytesIO()
    Image.new('RGBA', size, colour).save(stream, 'PNG')
    return stream.getvalue()


def gradient(size, grey=False):
    """A picture with structure (a colour gradient), or its grey version."""
    width, height = size
    image = Image.new('RGB', size)
    image.putdata([(x * 255 // width, y * 255 // height, (x + y) * 255 // (width + height))
                   for y in range(height) for x in range(width)])
    return image.convert('L').convert('RGB') if grey else image


def jpeg(image):
    stream = BytesIO()
    image.save(stream, 'JPEG', quality=95)
    return stream.getvalue()


class Library:
    """Just what build_from_map reads: episodes, their archives and resources, the store and the HD bundle."""

    def __init__(self, root, episodes):
        self.store = TwinStore(root)
        self.episodes = [dict(id=key, name=key, variant=variant) for key, (variant, _) in episodes.items()]
        self._assets = {key: assets for key, (_, assets) in episodes.items()}

    def twin_store(self):
        return self.store

    def hd_asset(self, resource_id):
        return None

    def open_episode(self, key):
        assets = self._assets[key]
        archive = SimpleNamespace(entries=sorted(assets), read=assets.__getitem__)
        return SimpleNamespace(archive=archive, exists=assets.__contains__, raw_asset=assets.__getitem__)


class TwinMapTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.sd_face, self.hd_face = png((64, 64), 'red'), png((128, 128), 'red')
        self.sd_room, self.hd_room = png((48, 72), 'blue'), png((96, 144), 'blue')
        self.sd_other = png((64, 64), 'green')          # no HD twin anywhere
        self.map = SimpleNamespace(
            VERSION='v1',
            TWINS={fingerprint(self.sd_face): (fingerprint(self.hd_face), 64, 64),
                   fingerprint(self.sd_room): (fingerprint(self.hd_room), 48, 72)},
            COVERAGE={'standard': (26000, 26001), 'partial': (26000, 26002), 'absent': (26000,)})

    def library(self, *, with_room=True):
        hd_assets = {26000: self.hd_face, **({26001: self.hd_room} if with_room else {})}
        return Library(self.root, {
            'hd': ('hd', hd_assets),
            'standard': ('standard', {26000: self.sd_face, 26001: self.sd_room}),
            'partial': ('standard', {26000: self.sd_face, 26002: self.sd_other}),
        })

    def test_the_store_and_coverage_come_from_the_players_own_hd_episodes(self):
        library = self.library()
        self.assertTrue(build_from_map(library, self.map))
        store = library.twin_store()
        self.assertEqual(store.twin(self.sd_face), self.hd_face)
        self.assertEqual(store.twin(self.sd_room), self.hd_room)
        self.assertIsNone(store.twin(self.sd_other))
        self.assertEqual(store.coverage('standard'), (2, 2))           # fully HD: no SD mark
        self.assertEqual(store.coverage('partial'), (2, 1))            # one picture has no twin: keeps it
        self.assertIsNone(store.coverage('absent'))                    # not in this library: not measured
        self.assertFalse(build_from_map(library, self.map))            # already built from this map version
        self.assertTrue(build_from_map(library, SimpleNamespace(**{**vars(self.map), 'VERSION': 'v2'})))

    def test_a_new_map_version_drops_pairs_it_no_longer_has(self):
        # The 2026-11 art audit removed and moved pairs: an updated player's store must lose them too, not only gain.
        library = self.library()
        build_from_map(library, self.map)
        self.assertIsNotNone(library.twin_store().twin(self.sd_room))
        newer = SimpleNamespace(**{**vars(self.map), 'VERSION': 'v2',
                                   'TWINS': {fingerprint(self.sd_face): (fingerprint(self.hd_face), 64, 64)}})
        self.assertTrue(build_from_map(library, newer))
        store = library.twin_store()
        self.assertIsNone(store.twin(self.sd_room))
        self.assertEqual(store.twin(self.sd_face), self.hd_face)
        self.assertEqual(len(store), 1)

    def test_an_entry_with_an_effect_stores_the_hd_picture_recreated_from_the_players_standard_one(self):
        sd = jpeg(gradient((48, 72), grey=True))
        hd = jpeg(gradient((96, 144)))
        library = Library(self.root, {'hd': ('hd', {26000: hd}), 'standard': ('standard', {26000: sd})})
        twin_map = SimpleNamespace(VERSION='v1', COVERAGE={},
                                   TWINS={fingerprint(sd): (fingerprint(hd), 48, 72, ('E',))})
        build_from_map(library, twin_map)
        stored = library.twin_store().twin(sd)
        self.assertIsNotNone(stored)
        self.assertNotEqual(stored, hd)
        image = Image.open(BytesIO(stored)).convert('RGB')
        self.assertEqual(image.size, (96, 144))
        self.assertTrue(all(abs(r - g) <= 3 and abs(g - b) <= 3 for r, g, b in image.getdata()))   # grey, as the SD is

    def test_an_effect_entry_is_left_out_when_the_player_lacks_the_standard_picture(self):
        sd, hd = jpeg(gradient((48, 72), grey=True)), jpeg(gradient((96, 144)))
        library = Library(self.root, {'hd': ('hd', {26000: hd})})
        twin_map = SimpleNamespace(VERSION='v1', COVERAGE={},
                                   TWINS={fingerprint(sd): (fingerprint(hd), 48, 72, ('E',))})
        build_from_map(library, twin_map)
        self.assertEqual(len(library.twin_store()), 0)

    def test_a_picture_the_players_files_lack_is_left_out_and_coverage_says_so(self):
        library = self.library(with_room=False)
        build_from_map(library, self.map)
        self.assertIsNone(library.twin_store().twin(self.sd_room))
        self.assertEqual(library.twin_store().coverage('standard'), (2, 1))   # never claims an HD it could not build


class ShippedMapTests(unittest.TestCase):
    def test_the_shipped_map_holds_fingerprints_and_ids_only(self):
        from exp_runtime.shs.profile import twin_map
        shipped = twin_map()
        self.assertRegex(shipped.VERSION, r'^[0-9a-f]{12}$')
        self.assertGreater(len(shipped.TWINS), 0)
        from exp_runtime.hd_effects import recreate
        for standard, (hd, width, height, *effect) in shipped.TWINS.items():
            self.assertRegex(standard, r'^[0-9a-f]{20}$')
            self.assertRegex(hd, r'^[0-9a-f]{20}$')
            self.assertTrue(isinstance(width, int) and isinstance(height, int))
            if effect:                                  # a name `hd_effects.recreate` knows, never a picture
                (effect,) = effect
                self.assertIsInstance(effect, tuple)
                self.assertIn(effect[0], ('E', 'Ecolour', 'F', 'M', 'MIRROR'))
                recreate(Image.new('RGB', (8, 12)), Image.new('RGB', (16, 24)), effect)
        for record_id, ids in shipped.COVERAGE.items():
            self.assertRegex(record_id, r'^[0-9a-f]{64}$')
            self.assertTrue(all(isinstance(i, int) for i in ids))


if __name__ == '__main__':
    unittest.main()
