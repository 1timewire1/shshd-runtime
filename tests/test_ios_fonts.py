"""Authored SFNT fixtures for the IPA font adapter."""
from io import BytesIO
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import ImageFont

from exp_runtime.dialogue_notice import notice_font
from exp_runtime.fonts import layout_text, TextStyle
from exp_runtime.ios_fonts import _design_metrics, render_font


class IOSFontMetricsTests(unittest.TestCase):
    def test_each_game_supplies_its_own_name_and_notice_colors_with_the_same_metrics(self):
        data = ImageFont.load_default().font_bytes
        fonts = {}
        for game, asset, expected in (('shs', 505, (41, 104, 221, 255)),
                                       ('cod', 291, (139, 0, 0, 255))):
            library = SimpleNamespace(game_id=game, base_members={asset}, read_asset=lambda _: data)
            names = ('PajamaHip26', 'PajamaHipG26', 'PajamaHipY26') if game == 'cod' else ('PajamaHip26',)
            palette = [(name, expected) for name in names]
            for theme in (1, 2, 3, -1):
                color = {1: (240, 81, 60), 2: (180, 78, 78)}.get(theme, (0, 0, 0))
                palette.append((notice_font(game, theme), (*color, 255) if game == 'cod' else (254, 53, 0, 255)))
            for name, expected in palette:
                font, atlas = render_font(library, name)
                self.assertTrue(font.native_face)
                colors = {color for _, color in atlas.getcolors(atlas.width * atlas.height)}
                self.assertIn(expected, colors)
                self.assertIn((255, 255, 255, 255), colors)  # Supplied-face outline stays white.
            fonts[game] = font
        self.assertEqual(fonts['shs'].glyphs, fonts['cod'].glyphs)

    def font_file(self, cap=None):
        head, hhea, os2 = bytearray(54), bytearray(36), bytearray(90 if cap else 86)
        struct.pack_into('>H', head, 18, 1000)
        struct.pack_into('>h', hhea, 6, -225)
        struct.pack_into('>H', os2, 0, 2 if cap else 1)
        if cap:
            struct.pack_into('>h', os2, 88, cap)
        tables = [(b'head', head), (b'hhea', hhea), (b'OS/2', os2)]
        data = bytearray(struct.pack('>I4H', 0x10000, len(tables), 0, 0, 0))
        offset = 12 + len(tables) * 16
        for tag, table in tables:
            data += struct.pack('>4sIII', tag, 0, offset, len(table))
            offset += len(table)
        return BytesIO(data + b''.join(table for _, table in tables))

    def test_cap_height_and_descent_use_font_design_units(self):
        design = SimpleNamespace(getbbox=lambda c, **_: (0, -701 if c == 'H' else -722, 500, 0),
                                 getlength=lambda c: 333)
        font = SimpleNamespace(font_variant=lambda **kwargs: design)
        for supplied, expected in ((725, 725), (None, 711)):
            actual, units, cap, descent = _design_metrics(font, self.font_file(supplied), 0)
            self.assertIs(actual, design)
            self.assertEqual((units, cap, descent), (1000, expected, 225))

    def test_collection_metrics_use_the_selected_face(self):
        faces = [bytearray(self.font_file(cap).getvalue()) for cap in (725, 800)]
        offsets = [20, 20 + len(faces[0])]
        for data, offset in zip(faces, offsets):
            for i in range(3):
                pos = 12 + i * 16 + 8
                struct.pack_into('>I', data, pos, struct.unpack_from('>I', data, pos)[0] + offset)
        collection = BytesIO(struct.pack('>4s4I', b'ttcf', 0x10000, 2, *offsets) + b''.join(faces))
        font = SimpleNamespace(font_variant=lambda **_: None)
        self.assertEqual(_design_metrics(font, collection, 1)[1:], (1000, 800, 225))

    def test_rendered_atlas_retains_fractional_advances_for_wrapping(self):
        # Pillow's own freely supplied font is already used by the authored
        # CoD importer fixtures; no proprietary face is included in the test.
        data = ImageFont.load_default().font_bytes
        library = SimpleNamespace(game_id='cod', base_members={291}, read_asset=lambda _: data)
        font, atlas = render_font(library, 'PajamaHip26')
        rounded = ImageFont.truetype(BytesIO(data), 26, layout_engine=ImageFont.Layout.BASIC)
        glyph = next(g for g in font.glyphs.values() if chr(g.code).isalpha()
                     and 32 < g.code < 127 and g.advance < rounded.getlength(chr(g.code)))
        text = chr(glyph.code) * 10
        width = glyph.advance * 10 + .01
        self.assertLess(width, rounded.getlength(chr(glyph.code)) * 10)
        self.assertEqual(len(layout_text(font, text, width, TextStyle(font.cap_height)).lines), 1)
        self.assertTrue(atlas.getbbox())

    def test_emphasis_atlas_has_a_fine_outline_without_changing_pen_advances(self):
        with TemporaryDirectory() as directory:
            path = Path(directory, 'authored.ttf')
            path.write_bytes(ImageFont.load_default().font_bytes)
            library = SimpleNamespace(game_id='shs', base_members=set())
            with patch('exp_runtime.ios_fonts.resolve_face', return_value=(path, 0)):
                normal, normal_atlas = render_font(library, 'TrebuchetMS_Italic16')
                emphasized, atlas = render_font(library, 'TrebuchetMS_Italic16Emphasis')
                substitute, _ = render_font(library, 'PajamaHip26')
            self.assertFalse(normal.native_face)
            self.assertFalse(substitute.native_face)
            self.assertEqual((normal.cap_height, normal.descent), (emphasized.cap_height, emphasized.descent))
            self.assertEqual([g.advance for g in normal.glyphs.values()],
                             [g.advance for g in emphasized.glyphs.values()])
            self.assertGreater(atlas.getchannel('A').getbbox()[2], 0)
            glyph, outlined = normal.glyph('A'), emphasized.glyph('A')
            self.assertEqual((outlined.width, outlined.height), (glyph.width + 2, glyph.height + 2))
            ink = atlas.crop((outlined.x, outlined.y, outlined.x + outlined.width, outlined.y + outlined.height))
            original = normal_atlas.crop((glyph.x, glyph.y, glyph.x + glyph.width, glyph.y + glyph.height))
            # Fractional strokes are supersampled, rather than rounded away
            # or expanded to the same two-point radius as character names.
            self.assertGreater(sum(ink.getchannel('A').tobytes()), sum(original.getchannel('A').tobytes()))
