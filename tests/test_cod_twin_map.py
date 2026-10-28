"""Cause of Death's HD backgrounds: the shipped map, the recreated edits and the store built from the player's own SHS
HD files (cod/hd_twins.py). Authored pictures only."""
from io import BytesIO
import json
import random
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageChops, ImageFilter, ImageStat

from exp_runtime.content import EpisodeResources
from exp_runtime.cod import hd_twin_map, hd_twins
from exp_runtime.hd_twins import TwinStore, fingerprint, image_size


def textured(size, seed=1):
    """A picture with detail at every scale: noise over a gradient."""
    rng = random.Random(seed)
    image = Image.new('RGB', size)
    image.putdata([(min(255, x * 200 // size[0] + rng.randrange(40)), min(255, y * 200 // size[1] + rng.randrange(40)),
                    rng.randrange(60, 200)) for y in range(size[1]) for x in range(size[0])])
    return image


def encode(image, kind='PNG'):
    stream = BytesIO()
    image.save(stream, kind)
    return stream.getvalue()


def difference(a, b):
    return sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 3


class ShippedMapTests(unittest.TestCase):
    def test_the_map_names_pictures_by_fingerprint_only(self):
        self.assertRegex(hd_twin_map.VERSION, r'^[0-9a-f]{12}$')
        self.assertGreater(len(hd_twin_map.TWINS), 60)
        effects = set()
        for key, (hd, width, height, effect, hint) in hd_twin_map.TWINS.items():
            self.assertRegex(key, r'^[0-9a-f]{20}$')
            self.assertRegex(hd, r'^[0-9a-f]{20}$')
            self.assertTrue(width > 0 and height > 0)
            self.assertTrue(effect in (None, 'levels') or effect[0] in ('blur', 'local'), effect)
            self.assertIn(hint[0], ('episode', 'bank'))
            if hint[0] == 'episode':
                self.assertTrue(hint[1].endswith('.exp') and hint[2] >= 26000, hint)
            effects.add(effect if effect in (None, 'levels') else effect[0])
        self.assertEqual(effects, {None, 'levels', 'blur', 'local'})

    def test_the_profile_loads_it(self):
        from exp_runtime.cod import profile
        self.assertIs(profile.background_twin_map(), hd_twin_map)


class EffectTests(unittest.TestCase):
    def setUp(self):
        self.hd = textured((96, 144))
        self.small = self.hd.resize((48, 72), Image.LANCZOS)

    def test_no_effect_keeps_the_hd_bytes(self):
        data = encode(self.hd, 'JPEG')
        self.assertIs(hd_twins.apply_effect(encode(self.small), data, None), data)

    def test_levels_recover_a_brightness_change(self):
        cod = self.small.point(lambda v: min(255, round(v * .8 + 30)))
        out = hd_twins.recreate(cod, self.hd, 'levels')
        self.assertEqual(out.size, self.hd.size)
        self.assertLess(difference(out.resize(cod.size, Image.LANCZOS), cod), 3)
        self.assertGreater(difference(self.small, cod), 6)

    def test_blur_is_recreated_at_the_hd_size(self):
        cod = self.small.filter(ImageFilter.GaussianBlur(3))
        out = hd_twins.recreate(cod, self.hd, ('blur', 3.0))
        self.assertLess(difference(out.resize(cod.size, Image.LANCZOS), cod), 3)

    def test_a_local_veil_carries_over_and_the_hd_detail_stays(self):
        haze = Image.linear_gradient('L').resize(self.small.size)            # strongest at the bottom
        cod = Image.composite(Image.new('RGB', self.small.size, (235, 230, 220)), self.small,
                              haze.point(lambda v: v * 3 // 4))
        out = hd_twins.recreate(cod, self.hd, ('local', None))
        self.assertLess(difference(out.resize(cod.size, Image.LANCZOS), cod), difference(self.small, cod) / 3)
        # At HD size the top (barely hazed) keeps the HD picture's own detail, not an upscaled CoD picture.
        box = (0, 0, 96, 30)
        upscaled = cod.resize(self.hd.size, Image.BICUBIC)
        self.assertLess(difference(out.crop(box), self.hd.crop(box)), difference(upscaled.crop(box), self.hd.crop(box)))

    def test_saturation_then_the_local_transfer(self):
        cod = self.small.convert('L').convert('RGB')
        out = hd_twins.recreate(cod, self.hd, ('local', 0.0))
        r, g, b = out.split()
        self.assertLess(max(difference(r.convert('RGB'), g.convert('RGB')), difference(g.convert('RGB'), b.convert('RGB'))), 2)

    def test_an_unknown_effect_is_refused(self):
        with self.assertRaises(ValueError):
            hd_twins.recreate(self.small, self.hd, ('sepia', 1))


class Archive(SimpleNamespace):
    def read(self, resource_id):
        return self.assets[resource_id]


class CodLibrary:
    game_id = 'cod'
    hd_art_mode = 'fill'
    hires_portraits = False

    def __init__(self, root, bundle, episodes, shs_hd_bank=None):
        self.store = TwinStore(root)
        self.base_members = dict.fromkeys(bundle)
        self._bundle = bundle
        self.episodes = [dict(id=name, name=name) for name in episodes]
        self._episodes = episodes
        self._bank = shs_hd_bank or {}

    def twin_store(self):
        return self.store

    def android_asset(self, resource_id):
        return self._bundle[resource_id]

    def hd_asset(self, resource_id):
        return None

    def shs_hd_resource(self, resource_id):
        return self._bank.get(resource_id)

    def open_episode(self, key):
        assets = self._episodes[key]
        return SimpleNamespace(archive=Archive(entries=sorted(assets), assets=assets))


class ShsLibrary:
    def __init__(self, episodes):
        self.episodes = [dict(id=name, name=name, variant='hd') for name in episodes]
        self._episodes = episodes

    def open_episode(self, key):
        assets = self._episodes[key]
        return SimpleNamespace(archive=Archive(entries=sorted(assets), assets=assets))

    def hd_raw_resource(self, resource_id):
        return None


class BuildTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        pictures = [textured((96, 144), seed) for seed in range(4)]
        self.hd = [encode(p, 'JPEG') for p in pictures]
        self.cod = [encode(p.resize((48, 72), Image.LANCZOS), 'JPEG') for p in pictures]
        self.cod_levels = encode(pictures[1].resize((48, 72)).point(lambda v: min(255, v + 25)), 'JPEG')
        self.map = SimpleNamespace(VERSION='v1', TWINS={
            fingerprint(self.cod[0]): (fingerprint(self.hd[0]), 48, 72, None, ('bank', 1050)),
            fingerprint(self.cod_levels): (fingerprint(self.hd[1]), 48, 72, 'levels', ('episode', 'a.exp', 26001)),
            fingerprint(self.cod[2]): (fingerprint(self.hd[2]), 48, 72, None, ('episode', 'gone.exp', 26009)),
            fingerprint(self.cod[3]): (fingerprint(self.hd[3]), 48, 72, None, ('episode', 'a.exp', 26003)),
        })

    def libraries(self, *, with_last=True):
        cod = CodLibrary(self.root, {1050: self.cod[0]},
                         {'one.exp': {26000: self.cod_levels, 26001: self.cod[2], 26002: self.cod[3]}},
                         shs_hd_bank={1050: self.hd[0]})
        shs_assets = {'a.exp': {26001: self.hd[1], **({26003: self.hd[3]} if with_last else {})},
                      'b.exp': {26007: self.hd[2]}}                # the hinted 'gone.exp' is not this player's
        return cod, ShsLibrary(shs_assets)

    def test_the_store_holds_each_cod_picture_as_its_hd_picture(self):
        cod, shs = self.libraries()
        self.assertEqual(hd_twins.build(cod, shs, self.map), 4)
        store = cod.twin_store()
        self.assertEqual(store.twin(self.cod[0]), self.hd[0])                 # the bundle's, via the SHS HD art
        self.assertEqual(store.twin(self.cod[2]), self.hd[2])                 # found by scanning the rest
        self.assertEqual(store.twin(self.cod[3]), self.hd[3])
        levelled = store.twin(self.cod_levels)
        self.assertEqual(image_size(levelled), (96, 144))                     # recreated: a new JPEG at HD size
        self.assertNotEqual(levelled, self.hd[1])
        self.assertEqual(store.source(), {'map': 'v1', 'missing': 0, 'shs_hd_episodes': 2})
        self.assertFalse(hd_twins.due(cod, 2, self.map))
        self.assertTrue(hd_twins.due(cod, 2, SimpleNamespace(VERSION='v2', TWINS={})))

    def test_a_missing_picture_is_left_out_and_a_changed_shs_library_retries(self):
        cod, shs = self.libraries(with_last=False)
        hd_twins.build(cod, shs, self.map)
        self.assertIsNone(cod.twin_store().twin(self.cod[3]))
        self.assertEqual(cod.twin_store().source()['missing'], 1)
        self.assertFalse(hd_twins.due(cod, 2, self.map))                      # nothing new to look in
        self.assertTrue(hd_twins.due(cod, 3, self.map))                       # another SHS HD episode arrived
        cod_again, shs_again = self.libraries()
        cod_again.store = cod.store
        hd_twins.build(cod_again, shs_again, self.map)
        self.assertEqual(cod.twin_store().twin(self.cod[3]), self.hd[3])

    def test_without_an_shs_library_only_the_bundles_pictures_are_built(self):
        cod, _ = self.libraries()
        hd_twins.build(cod, None, self.map)
        self.assertEqual(len(cod.twin_store()), 1)
        self.assertEqual(cod.twin_store().source()['shs_hd_episodes'], 0)

    def test_the_shs_librarys_hd_episodes_are_counted_from_its_manifest(self):
        directory = self.root / 'shs'
        directory.mkdir()
        (directory / 'library.json').write_text(json.dumps({'episodes': [
            {'variant': 'hd'}, {'variant': 'standard'}, {'variant': 'hd'}]}), encoding='utf-8')
        self.assertEqual(hd_twins.shs_hd_episodes_listed(directory), 2)
        self.assertEqual(hd_twins.shs_hd_episodes_listed(self.root / 'none'), 0)


class ReadPathTests(unittest.TestCase):
    def test_cod_episodes_show_the_twin_and_never_a_fill(self):
        with tempfile.TemporaryDirectory() as temporary:
            library = CodLibrary(Path(temporary), {}, {})
            cod, hd = encode(textured((48, 72))), encode(textured((96, 144)))
            other = encode(textured((48, 72), seed=9))
            library.store.add_pictures({fingerprint(cod): ((48, 72), hd)})
            archive = SimpleNamespace(programs=lambda: {}, read={26000: cod, 26001: other}.__getitem__)
            resources = EpisodeResources(library, {'id': 'x', 'name': 'x.exp'}, archive)
            self.assertEqual(resources.read_asset(26000), hd)
            self.assertEqual(resources.read_asset(26001), other)              # no twin: CoD's own, not doubled
            library.hd_art_mode = 'off'
            self.assertEqual(resources.read_asset(26000), cod)


if __name__ == '__main__':
    unittest.main()
