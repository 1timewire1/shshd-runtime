from pathlib import Path
import struct
import unittest
from dataclasses import replace

from exp_runtime.atlas import AtlasFont, AtlasFrame, SpriteAtlas
from exp_runtime.content import ContentLibrary
from exp_runtime.ui_assets import Raster, UIAssetError


class AtlasTests(unittest.TestCase):
    def test_stored_quad_dimensions_vertex_transforms_and_mirrored_origin(self):
        # Six authored pixels in a non-square frame distinguish every vertex
        # permutation. Logical dimensions deliberately differ from the crop.
        image = Raster(3, 2, b''.join(bytes((i, 0, 0, 255)) for i in range(1, 7)))
        atlas = SpriteAtlas(16, (), (((0, 7, -2),),), (),
                            (AtlasFrame(0, 0, 8, 9, 3, 2),), image)
        cases = ((0, (3, 2), [1, 2, 3, 4, 5, 6]),
                 (1, (3, 2), [1, 2, 3, 4, 5, 6]),
                 (2, (3, 2), [3, 2, 1, 6, 5, 4]),
                 (3, (3, 2), [6, 5, 4, 3, 2, 1]),
                 (4, (3, 2), [1, 2, 3, 4, 5, 6]),
                 (5, (2, 3), [1, 4, 2, 5, 3, 6]),
                 (6, (2, 3), [6, 3, 5, 2, 4, 1]),
                 (7, (3, 2), [1, 2, 3, 4, 5, 6]))
        for transform, size, pixels in cases:
            with self.subTest(transform=transform):
                value = replace(atlas, transforms=((0, 3), (0, transform)))
                raster = value.raster(0)
                self.assertEqual((raster.width, raster.height), size)
                self.assertEqual(list(raster.pixels[::4]), pixels)
                self.assertEqual(value.literals(-1), ((0, 12 if transform == 2 else 7, -2),))

    def test_distinct_abgr_pixels_frames_and_bounds(self):
        data = (struct.pack('>Bhbhhhhh', 16, 1, 0, 0, 0, 0, 1, 2)
                + struct.pack('>h6h',1,1,0,1,2,1,2)
                + bytes([255,30,20,10,128,60,50,40,0,90,80,70,255,120,110,100]))
        atlas=SpriteAtlas.parse(data)
        self.assertEqual(atlas.raster(0),Raster(1,2,bytes([40,50,60,128,100,110,120,255])))
        for bad in (data[:-1],data+b'\0',data[:10]):
            with self.assertRaises(UIAssetError):SpriteAtlas.parse(bad)
        with self.assertRaises(UIAssetError):atlas.raster(-1)
        composite = replace(atlas, parts=(((0, -2, 3),), ((-1, 10, -5), (0, 1, 2))))
        self.assertEqual(composite.literals(-2), ((0, 8, -2), (0, 1, 2)))
        with self.assertRaises(UIAssetError): replace(atlas, parts=(((-1, 0, 0),),)).literals(-1)

    def test_binary_font_case_fallback_and_extents(self):
        atlas=Raster(8,10,b'\0'*(8*10*4))
        data=struct.pack('>BBbhbBhhb',5,1,-1,1,10,65,0,0,8)
        font=AtlasFont.parse(data,atlas)
        self.assertEqual(font.glyph('a'),(0,0,8))
        self.assertIsNone(font.glyph('?'))
        with self.assertRaises(UIAssetError):AtlasFont.parse(data[:-1]+b'\x09',atlas)

    def test_native_font_wrapping_tracking_and_paragraph_height(self):
        # Authored glyph metrics: negative tracking, a line gap, and an
        # intentionally narrower I. No platform fonts or original assets.
        font = AtlasFont(4, 2, -1, 10, {ord(c): (0, 0, 8 if c != 'I' else 3)
                                      for c in 'ABCDEFGHI'})
        self.assertEqual(font.width('   AB'), 15)
        self.assertEqual(font.width('A I'), 13)
        self.assertEqual(font.width('II', 'A'), 15)
        lines = font.wrap('  AB CD\n\nEFGHI\n', 22)
        self.assertEqual(lines, ('AB', 'CD', '', 'EFG', 'HI'))
        self.assertEqual(font.text_height(lines), 58)
        self.assertEqual(font.wrap('', 22), ())
        self.assertEqual(font.text_height(()), 0)
        self.assertEqual(font.wrap('AB  CD', 15), ('AB', 'CD'))
        self.assertEqual(replace(font, style=255).text_height(('A', 'B')), 19)
        with self.assertRaises(UIAssetError): font.wrap('A', 7)

    @unittest.skipUnless(Path('.shs-library/library.json').exists(), 'user library absent')
    def test_original_grid_and_football_atlases(self):
        with ContentLibrary(Path('.shs-library')) as lib:
            r=lib.open_episode('The_New_Girl.exp')
            for asset,count in [(290,154),(446,48),(496,1),(499,1),(502,1),(522,1)]:
                atlas=SpriteAtlas.parse(r.read_asset(asset))
                self.assertEqual(len(atlas.frames),count)
                for i in range(count):atlas.raster(i)
                for i in range(len(atlas.parts)):atlas.literals(~i)
            atlas=SpriteAtlas.parse(r.read_asset(522))
            font=AtlasFont.parse(r.read_asset(523),atlas.image)
            self.assertEqual((font.height,len(font.glyphs)),(85,60))
