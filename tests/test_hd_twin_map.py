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
        for standard, (hd, width, height) in shipped.TWINS.items():
            self.assertRegex(standard, r'^[0-9a-f]{20}$')
            self.assertRegex(hd, r'^[0-9a-f]{20}$')
            self.assertTrue(isinstance(width, int) and isinstance(height, int))
        for record_id, ids in shipped.COVERAGE.items():
            self.assertRegex(record_id, r'^[0-9a-f]{64}$')
            self.assertTrue(all(isinstance(i, int) for i in ids))


if __name__ == '__main__':
    unittest.main()
