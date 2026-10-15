from pathlib import Path
import struct
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from exp_runtime.ui_assets import ImagePack, LayoutBank, Raster, Rect, UIAssetError


def image_pack(marker=-1, transforms=(), count=1, pixels=b'\x03\x02' + b'\xff\x01\x02\x03' * 6):
    return (struct.pack('>Bhbhhh', 16, count, 0, 0, 0, len(transforms))
            + b''.join(struct.pack('>hhb', *t) for t in transforms)
            + struct.pack('>hh', marker, count) + pixels)


def node(base, relative=(0, 0, 0, 0), kind=6, payload=b''):
    return struct.pack('>8hB', *base, *relative, kind) + payload


class UIAssetTests(unittest.TestCase):
    def test_argb_channel_order_and_all_generated_orientations(self):
        pixels = b'\x03\x02' + b''.join(bytes((100 + i, i, 20, 30)) for i in range(1, 7)) + b'\0' * 7
        pack = ImagePack.parse(image_pack(transforms=[(0, i, i) for i in range(1, 8)], count=8, pixels=pixels))
        expected = [(3, 2, '123456'), (3, 2, '456123'), (3, 2, '321654'), (3, 2, '654321'),
                    (2, 3, '142536'), (2, 3, '415263'), (2, 3, '362514'), (2, 3, '635241')]
        for image, (width, height, order) in zip(pack.images, expected):
            self.assertEqual((image.width, image.height), (width, height))
            self.assertEqual(list(image.pixels[0::4]), list(map(int, order)))
        self.assertEqual(pack.images[0].pixels[:4], bytes((1, 20, 30, 101)))

    def test_alpha_mask_is_bottom_aligned_and_binary(self):
        pack = ImagePack.parse(image_pack(marker=-2, pixels=b'\x04\x03' + b'\0' * 10 + b'\x80\xff'))
        image = Raster(2, 1, bytes((1, 2, 3, 200, 4, 5, 6, 210)))
        masked = image.portrait_mask(pack.images[0])
        self.assertEqual(masked.pixels, bytes((1, 2, 3, 200, 0, 0, 0, 0)))

    def test_double_size_portraits_preserve_alpha_and_mask_after_resampling(self):
        # Two authored 2x2 source blocks. Transparent white must not pollute
        # the first block's opaque red when converted to one logical pixel.
        red = bytes((240, 0, 0, 255))
        hidden = bytes((255, 255, 255, 0))
        blue = bytes((0, 0, 240, 255))
        image = Raster(4, 2, red + hidden + blue * 2 + hidden * 2 + blue * 2)
        mask = Raster(2, 3, b'\xff' * 4 + b'\0\x01', 'A')
        normalized = image.normalize_portrait(mask)
        self.assertEqual((normalized.width, normalized.height), (2, 1))
        self.assertEqual(normalized.pixels, bytes((239, 0, 0, 64, 0, 0, 240, 255)))
        self.assertEqual(normalized.portrait_mask(mask).pixels,
                         bytes((239, 0, 0, 64, 0, 0, 0, 0)))
        self.assertEqual(image.width, 4)
        self.assertEqual(image.pixels, red + hidden + blue * 2 + hidden * 2 + blue * 2)

    def test_native_portraits_are_unchanged_and_unknown_sizes_still_fail(self):
        mask = Raster(4, 5, b'\0' * 20, 'A')
        native = Raster(4, 4, bytes((5, 10, 15, 128)) * 16)
        self.assertIs(native.normalize_portrait(mask), native)
        self.assertEqual(native.portrait_mask(mask), native)
        for width, height in ((8, 8), (6, 8)):
            image = Raster(width, height, bytes((5, 10, 15, 255)) * (width * height))
            normalized = image.normalize_portrait(mask)
            self.assertEqual((normalized.width, normalized.height), (width // 2, height // 2))
            self.assertEqual(normalized.portrait_mask(mask), normalized)
        for width, height, mode in ((7, 8, 'RGBA'), (10, 12, 'RGBA'), (8, 8, 'A')):
            image = Raster(width, height, b'\0' * (width * height * (4 if mode == 'RGBA' else 1)), mode)
            with self.subTest(width=width, height=height, mode=mode), self.assertRaisesRegex(UIAssetError, 'for mask 4x5 A'):
                image.normalize_portrait(mask).portrait_mask(mask)

    def test_image_extents_encoding_and_references_are_checked(self):
        good = image_pack()
        for data in (good[:-1], good + b'x', image_pack(marker=-3),
                     image_pack(transforms=[(8, 0, 0)]),
                     image_pack(count=2, pixels=b'\0\0')):
            with self.subTest(data=data[:20]), self.assertRaises(UIAssetError):
                ImagePack.parse(data)

    def test_nested_layout_ids_and_fixed_point_coordinates(self):
        data = (struct.pack('>bbbbh', 1, 0, 0, 0, 2)
                + struct.pack('>hhh', 100, 100, 2)
                + node((10, 20, 40, 40), (2048, 0, 2048, 0), 0x17, b'\x01')
                + node((-5, -5, 5, 5))
                + struct.pack('>hhh', 30, 20, 1) + node((1, 2, 29, 18)))
        bank = LayoutBank.parse(data)
        resized = Rect(5, 10, 200, 100)
        self.assertEqual(bank.rectangle(0, 0, resized), resized)
        self.assertEqual(bank.rectangle(0, 1, resized), Rect(65, 30, 30, 20))
        self.assertEqual(bank.rectangle(0, 2, resized), Rect(66, 32, 28, 16))
        self.assertEqual(bank.rectangle(0, 3, resized), Rect(0, 5, 10, 10))
        self.assertEqual(bank.rectangle(0, 1, Rect(0, 0, 99, 100)).x, 9)
        with self.assertRaises(UIAssetError):
            LayoutBank.parse(data[:-1])
        with self.assertRaises(UIAssetError):
            bank.rectangle(0, 4)

    def test_rectangle_is_cached_not_rewalked_on_repeated_lookups(self):
        # Every caller across the whole UI (dialogue, choice, menu, message, title, input) asks `rectangle()`
        # for the same handful of node ids repeatedly, often several times a frame for the same answer -- a
        # real dialogue screen's relationship-icon placement alone cost ~13 full tree walks every single
        # frame before this cache existed, none of which could ever come back different for an immutable bank.
        # An extra, otherwise-unused empty layout at the end (count 3, not 2) only to keep this bank's own bytes
        # -- and so its value, which is what the lru_cache keys on -- distinct from the identical fixture the
        # test above builds, so a hit here can only come from this test's own calls, not a cross-test collision.
        data = (struct.pack('>bbbbh', 1, 0, 0, 0, 3)
                + struct.pack('>hhh', 100, 100, 2)
                + node((10, 20, 40, 40), (2048, 0, 2048, 0), 0x17, b'\x01')
                + node((-5, -5, 5, 5))
                + struct.pack('>hhh', 30, 20, 1) + node((1, 2, 29, 18))
                + struct.pack('>hhh', 1, 1, 0))
        bank = LayoutBank.parse(data)
        resized = Rect(5, 10, 200, 100)
        with patch.object(LayoutBank, 'walk', wraps=bank.walk, autospec=False) as walk:
            for _ in range(5):
                self.assertEqual(bank.rectangle(0, 1, resized), Rect(65, 30, 30, 20))
            for _ in range(5):
                self.assertEqual(bank.rectangle(0, 2, resized), Rect(66, 32, 28, 16))
            self.assertEqual(walk.call_count, 2)                       # one real walk per distinct (id, rect)

    def test_recursive_layout_fails_explicitly(self):
        data = struct.pack('>bbbbhhhh', 0, 0, 0, 0, 1, 10, 10, 1) + node((0, 0, 10, 10), kind=7, payload=b'\0')
        with self.assertRaises(UIAssetError):
            list(LayoutBank.parse(data).walk(0))

    @unittest.skipUnless(Path('surviving-high-school-1-0-9.apk').is_file(), 'user APK is not present')
    def test_original_layouts_skins_and_mask_decode_completely(self):
        with ZipFile('surviving-high-school-1-0-9.apk') as apk:
            bank = LayoutBank.parse(apk.read('assets/Assets/14'))
            self.assertEqual(len(bank.layouts), 82)
            self.assertEqual(bank.rectangle(17, 8), Rect(37, 304, 246, 98))
            self.assertEqual(bank.rectangle(17, 0x30), Rect(-7, 225, 128, 128))
            self.assertEqual(bank.rectangle(17, 0x4e), Rect(199, 225, 128, 128))
            for index in range(82):
                list(bank.walk(index))
            for resource, count in [('126', 60), ('16.mp3', 108), ('204', 14), ('220', 14), ('236', 14), ('252', 14), ('268', 1)]:
                pack = ImagePack.parse(apk.read('assets/Assets/' + resource))
                self.assertEqual(len(pack.images), count)
            self.assertEqual((pack.images[0].mode, pack.images[0].width, pack.images[0].height), ('A', 128, 150))
