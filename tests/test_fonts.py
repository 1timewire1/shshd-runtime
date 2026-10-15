"""Authored fixtures exercise native behavior without shipping game data."""
from io import BytesIO
import importlib.util
import os
from pathlib import Path
import unittest
from zipfile import ZipFile

from exp_runtime.fonts import BitmapFont, FontError, TextStyle, layout_text


def descriptor():
    rows = [
        'info face="Authored test font" size=14',
        'common lineHeight=12 base=9 scaleW=999 scaleH=999 pages=1',
        'page id=0 file="test.dat"',
        'chars count=1',  # A declared count must not truncate later records.
    ]
    for code, advance in ((32, 3), (43, 6), (65, 6), (86, 6), (88, 6)):
        rows.append(f'char id={code} x=0 y=0 width=2 height=3 xoffset=1 '
                    f'yoffset={"6.5" if code == 43 else "2"} xadvance={advance} page=0 chnl=0')
    rows.extend(('kernings count=1', 'kerning first=65 second=86 amount=-2'))
    return ('\r\n'.join(rows) + '\r\n').encode()


class FontTests(unittest.TestCase):
    def setUp(self):
        self.font = BitmapFont.parse(descriptor())
        self.style = TextStyle(10, 7, (10, 20, 30), (('`', (200, 30, 40)), (';', (40, 50, 200))))

    def test_descriptor_uses_all_glyphs_and_native_integer_conversion(self):
        self.assertEqual(len(self.font.glyphs), 5)
        self.assertEqual(self.font.page, 'test.dat')
        self.assertEqual(self.font.glyph('+').yoffset, 6)
        self.assertEqual(self.font.kernings[65, 86], -2)
        self.assertEqual(self.font.line_height, 12)
        replaced = BitmapFont.parse(descriptor() + b'kerning first=65 second=86 amount=-4\n')
        self.assertEqual(replaced.kernings[65, 86], -4)
        for bad in (b'../test.dat', b'/tmp/test.dat', b'images/test.dat'):
            with self.subTest(page=bad), self.assertRaises(FontError):
                BitmapFont.parse(descriptor().replace(b'test.dat', bad))
        with self.assertRaisesRegex(FontError, 'no defined glyph'):
            layout_text(self.font, 'Q', 100, self.style)

    def test_control_bytes_fall_back_only_when_the_font_has_no_glyph(self):
        self.assertIs(self.font.glyph('\t'), self.font.glyph(' '))
        with_apostrophe = BitmapFont.parse(descriptor().replace(
            b'chars count=1', b'chars count=1\r\nchar id=39 x=0 y=0 width=1 height=3 xoffset=0 yoffset=2 xadvance=2 page=0 chnl=0'))
        for char in ('\x18', '\x19'):
            with self.subTest(character=ord(char)):
                with self.assertRaisesRegex(FontError, f'U\\+{ord(char):04X}'):
                    self.font.glyph(char)
                self.assertEqual(with_apostrophe.glyph(char).code, ord("'"))
                self.assertEqual(with_apostrophe.glyph(char).advance, 2)
        for char in ('\t', '\x18', '\x19'):
            own = BitmapFont.parse(descriptor() + (
                f'char id={ord(char)} x=0 y=0 width=1 height=3 xoffset=0 yoffset=2 xadvance=9 page=0 chnl=0\n'
            ).encode())
            self.assertEqual(own.glyph(char).advance, 9)
        for char in ('\x17', '\x1a'):
            with self.assertRaisesRegex(FontError, f'U\\+{ord(char):04X}'):
                with_apostrophe.glyph(char)

    def test_kerning_moves_only_drawn_glyph_and_never_changes_wrapping(self):
        result = layout_text(self.font, 'AVX', 18, self.style)
        self.assertEqual(result.width, 18)
        self.assertEqual([p.x for p in result.glyphs], [1, 5, 13])
        self.assertEqual(result.glyphs[0].y, 0)  # 10 nominal - 12 atlas + 2 offset
        wrapped = layout_text(self.font, 'AV', 11, self.style)
        self.assertEqual([(line.start, line.end) for line in wrapped.lines], [(0, 1), (1, 2)])
        self.assertEqual([p.x for p in wrapped.glyphs], [1, -1])
        self.assertEqual(wrapped.height, 27)  # 2 * (10 + 7) - 7
        self.assertEqual([p.y for p in wrapped.glyphs], [0, 17])

    def test_spaces_newlines_and_long_words_keep_native_byte_boundaries(self):
        text = '  A  V\nX\n'
        result = layout_text(self.font, text, 40, self.style)
        self.assertEqual([text[line.start:line.end] for line in result.lines], ['A  V', 'X'])
        self.assertEqual(result.lines[0].width, 18)
        self.assertEqual([p.x for p in result.glyphs], [1, 11, 1])
        text = 'AA VVXX'
        result = layout_text(self.font, text, 18, self.style)
        self.assertEqual([text[line.start:line.end] for line in result.lines], ['AA', 'VVX', 'X'])
        self.assertEqual(len(layout_text(self.font, '\n', 10, self.style).lines), 1)
        self.assertEqual(layout_text(self.font, '   ', 10, self.style).height, 0)
        self.assertEqual(layout_text(self.font, 'A\x00Q', 10, self.style).width, 6)
        with self.assertRaisesRegex(FontError, 'single glyph'):
            layout_text(self.font, 'A', 5, self.style)

    def test_color_markers_share_toggle_across_wrapped_lines(self):
        result = layout_text(self.font, 'A`V V;X', 15, self.style)
        self.assertEqual([p.color for p in result.glyphs],
                         [self.style.color, (200, 30, 40), (200, 30, 40), self.style.color])
        self.assertEqual([line.width for line in result.lines], [12, 12])
        self.assertFalse(result.highlighted)
        self.assertEqual(result.previous_glyph, ord('X'))
        self.assertEqual(result.color, self.style.color)
        # Standalone semicolons are registered color controls, not punctuation.
        self.assertEqual(layout_text(self.font, 'A;V', 12, self.style).glyphs[1].color, (40, 50, 200))

    def test_per_line_indents_affect_available_width_and_placement(self):
        text = 'AV AV AV'
        style = TextStyle(10, 7, indents=(4, -4))
        result = layout_text(self.font, text, 16, style)
        self.assertEqual([(line.x, line.width) for line in result.lines], [(4, 12), (0, 12), (0, 12)])

    def test_native_initial_negative_gap_can_give_zero_line_step(self):
        result = layout_text(self.font, 'A\nV', 20, TextStyle(10, -10))
        self.assertEqual([line.y for line in result.lines], [0, 0])
        self.assertEqual(result.height, 0)

    def test_previous_glyph_is_a_signed_byte_in_native_kerning_key(self):
        font = BitmapFont.parse(descriptor() + (
            'char id=233 x=0 y=0 width=2 height=3 xoffset=1 yoffset=2 xadvance=6 page=0\n'
            'kerning first=233 second=65 amount=-5\n'
            'kerning first=-23 second=65 amount=-1\n').encode())
        result = layout_text(font, '\xe9A', 20, self.style)
        self.assertEqual([p.x for p in result.glyphs], [1, 6])
        self.assertEqual(layout_text(font, '\xe9', 20, self.style).previous_glyph, -23)

    @unittest.skipUnless(Path('surviving-high-school-1-0-9.apk').is_file(), 'user APK is not present')
    def test_all_supplied_font_descriptors(self):
        from PIL import Image
        fonts = []
        with ZipFile('surviving-high-school-1-0-9.apk') as apk:
            for name in apk.namelist():
                if name.startswith('assets/Assets/fonts/') and name.endswith('.fnt'):
                    font = BitmapFont.parse(apk.read(name))
                    fonts.append(font)
                    with Image.open(BytesIO(apk.read('assets/Assets/fonts/' + font.page))) as atlas:
                        for glyph in font.glyphs.values():
                            self.assertLessEqual(glyph.x + glyph.width, atlas.width)
                            self.assertLessEqual(glyph.y + glyph.height, atlas.height)
                    self.assertGreater(layout_text(font, 'AV AV', 100, TextStyle(14)).width, 0)
        self.assertEqual(len(fonts), 18)
        self.assertEqual(sum(len(font.glyphs) for font in fonts), 1711)
        self.assertEqual(sum(len(font.kernings) for font in fonts), 1442)  # One repeated pair.


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class AtlasDrawingTests(unittest.TestCase):
    def test_actual_atlas_bounds_colors_alpha_and_clipping(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        import pygame
        from exp_runtime.desktop_text import BitmapTextRenderer

        pygame.display.init()
        pygame.display.set_mode((30, 30))
        self.addCleanup(pygame.quit)
        atlas = pygame.Surface((2, 3), pygame.SRCALPHA)
        atlas.fill((255, 255, 255, 255))
        atlas.set_at((0, 0), (255, 255, 255, 0))
        data = BytesIO()
        pygame.image.save(atlas, data, 'test.png')
        files = {'fonts/test.fnt': descriptor(), 'fonts/test.dat': data.getvalue()}

        class Library:
            def read_ui_asset(self, name):
                return files[name]

        renderer = BitmapTextRenderer(Library())
        target = pygame.Surface((30, 30), pygame.SRCALPHA)
        target.set_clip((0, 0, 7, 30))
        style = TextStyle(10, 7, (10, 20, 30), (('`', (200, 30, 40)),))
        renderer.draw(target, 'test', 'A`V`X', 0, 0, 30, style)
        self.assertEqual(target.get_at((1, 0)).a, 0)
        self.assertEqual(tuple(target.get_at((1, 1))), (10, 20, 30, 255))
        self.assertEqual(tuple(target.get_at((5, 1))), (200, 30, 40, 255))
        self.assertEqual(target.get_at((13, 1)).a, 0)
