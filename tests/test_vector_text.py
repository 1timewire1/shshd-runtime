"""Vector text uses pygame's bundled font, so no system or player fonts are needed."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from exp_runtime.fonts import BitmapFont, Glyph, TextStyle, layout_text


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class VectorTextTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        pygame.font.init()
        self.addCleanup(pygame.quit)
        from exp_runtime import vector_text
        self.vt = vector_text
        # pygame ships its default face, so the test needs no system font.
        path = os.path.join(os.path.dirname(pygame.__file__), pygame.font.get_default_font())
        self.source = vector_text.FaceSource(path=path)
        # A stand-in for an Android bitmap font: only its line box matters.
        glyphs = {c: Glyph(c, 0, 0, 5, 9, 0, 3, 6) for c in range(32, 127)}
        self.base = BitmapFont('Authored', 14, 19, 'unused.png', glyphs, {(65, 86): -2}, base=15)

    def font(self, **kwargs):
        return self.vt.vector_font(self.base, self.source, 16, **kwargs)

    def test_glyphs_get_real_advances_and_no_kerning(self):
        font = self.font()
        self.assertEqual(font.kernings, {})
        self.assertEqual(font.line_height, self.base.line_height)
        # The baseline is the bitmap font's capital bottom less its padding row
        # (H: yoffset 3 + height 9 - 1); the descriptor's own `base` (15) is
        # not trusted -- most real ones say 26 whatever the line height.
        self.assertEqual(font.base, 11)
        self.assertEqual(self.vt.vector_font(self.base, self.source, 16, use_common_base=True).base, 15)
        # Advances are proportional, unlike the authored fixed-width base font.
        self.assertNotEqual(font.glyph('i').advance, font.glyph('W').advance)
        self.assertEqual(font.glyph(' ').width, 0)
        # Sized in logical units: doubling the logical size doubles advances.
        double = self.vt.vector_font(self.base, self.source, 32)
        self.assertAlmostEqual(double.glyph('W').advance, font.glyph('W').advance * 2, delta=.05)
        # Ink sits on the base font's baseline: a capital ends at it.
        capital = font.glyph('H')
        self.assertAlmostEqual(capital.yoffset + capital.height, 11, delta=.3)

    def test_layout_wraps_by_the_vector_advances(self):
        font = self.font()
        wide = layout_text(font, 'iiii WWWW', 1000, TextStyle(16)).width
        self.assertAlmostEqual(wide, sum(font.glyph(c).advance for c in 'iiii WWWW'), delta=.01)
        narrow = layout_text(font, 'iiii WWWW', wide - 1, TextStyle(16))
        self.assertEqual(len(narrow.lines), 2)

    def test_rendering_places_ink_on_the_layout_baseline(self):
        import pygame
        from exp_runtime.desktop_text import BitmapTextRenderer
        library = SimpleNamespace()
        renderer = BitmapTextRenderer(library)
        font = self.font()
        renderer.fonts['Authored'] = font, None
        layout = layout_text(font, 'H', 100, TextStyle(16))
        for scale in (1, 2):
            surface = pygame.Surface((120 * scale, 40 * scale), pygame.SRCALPHA)
            renderer.draw_layout(surface, 'Authored', layout, 10 * scale, 5 * scale, scale=scale)
            ink = surface.get_bounding_rect()
            self.assertGreater(ink.width, 0)
            # The capital's bottom edge lands on the baseline (top + base).
            baseline = (5 + 16 - font.line_height + font.base) * scale  # font.base is 11
            self.assertAlmostEqual(ink.bottom, baseline, delta=1.5 * scale)

    def test_stroked_fonts_grow_an_outline_under_the_fill(self):
        import pygame
        plain = self.font(fill=(41, 104, 221))
        stroked = self.font(fill=(41, 104, 221), stroke=8 / 52)
        image, dx, dy = plain.render_glyph(ord('O'), (255, 255, 255), 2)
        outlined, odx, ody = stroked.render_glyph(ord('O'), (255, 255, 255), 2)
        self.assertGreater(outlined.get_width(), image.get_width())
        self.assertLess(odx, dx)
        self.assertLess(ody, dy)
        colors = {tuple(outlined.get_at((x, y)))[:3] for x in range(outlined.get_width())
                  for y in range(outlined.get_height()) if outlined.get_at((x, y)).a == 255}
        self.assertIn((255, 255, 255), colors)   # the stroke
        self.assertIn((41, 104, 221), colors)    # the fill on top

    def test_android_theme_colors_map_to_hd_colors(self):
        image, _, _ = self.font().render_glyph(ord('H'), (1, 76, 215), 2)
        colors = {tuple(image.get_at((x, y)))[:3] for x in range(image.get_width())
                  for y in range(image.get_height()) if image.get_at((x, y)).a == 255}
        self.assertIn((41, 104, 221), colors)

    def test_the_notice_font_is_a_red_outlined_italic_only_with_an_hd_bundle(self):
        vt = self.vt
        no_bundle = SimpleNamespace(hd_raw_resource=lambda resource_id: None)
        self.assertIs(vt.hd_font(no_bundle, vt.NOTICE_FONT_NAME, self.base), self.base)
        os.environ['SHS_TREBUCHET_ITALIC_FONT'] = self.source.path
        self.addCleanup(os.environ.pop, 'SHS_TREBUCHET_ITALIC_FONT', None)
        bundle = SimpleNamespace(hd_raw_resource=lambda resource_id: b'x')
        font = vt.hd_font(bundle, vt.NOTICE_FONT_NAME, self.base)
        self.assertEqual((font.logical_size, font.fill), (20, vt.NOTICE_FILL))
        self.assertGreater(font.stroke, font.embolden)
        self.assertGreater(font.embolden, 0)
        image, dx, dy = font.render_glyph(ord('S'), (255, 255, 255), 2)
        colors = {tuple(image.get_at((x, y)))[:3] for x in range(image.get_width())
                  for y in range(image.get_height()) if image.get_at((x, y)).a == 255}
        self.assertIn((255, 255, 255), colors)     # the outline
        self.assertIn(vt.NOTICE_FILL, colors)      # the fill survives on top of it

    def test_cod_switch_fonts_are_edged_but_the_narration_body_is_not(self):
        # The narration body (dialogue.NARRATOR_FONT) shares the switch fonts' name prefix.
        vt = self.vt
        os.environ['SHS_TREBUCHET_ITALIC_FONT'] = self.source.path
        self.addCleanup(os.environ.pop, 'SHS_TREBUCHET_ITALIC_FONT', None)
        library = SimpleNamespace(kind='ipa', game_id='cod')
        with mock.patch('exp_runtime.fonts.load_font', return_value=self.base):
            self.assertIs(vt.load_font(library, 'TrebuchetMS_Italic16'), self.base)
            self.assertAlmostEqual(vt.load_font(library, 'TrebuchetMS_Italic16NarrationEmphasis').embolden, .6 / 16)
            self.assertAlmostEqual(vt.load_font(library, 'TrebuchetMS_Italic16Emphasis').embolden, .5 / 16)

    def test_names_map_to_sizes_and_are_ignored_without_an_hd_bundle(self):
        vt = self.vt
        self.assertEqual(vt.parse_name('ArialRoundedMTBold16'), ('ArialRoundedMTBold', 16))
        self.assertEqual(vt.parse_name('TrebuchetMS_Italic16'), ('TrebuchetMS_Italic', 16))
        self.assertIsNone(vt.parse_name('mainmenu'))
        self.assertEqual(vt._pajama_split('PajamaHip26'), ('', 26))
        self.assertEqual(vt._pajama_split('PajamaHip266'), ('6', 26))
        self.assertEqual(vt._pajama_split('PajamaHipG26'), ('G', 26))
        self.assertIs(vt.hd_font(SimpleNamespace(), 'ArialRoundedMTBold16', self.base), self.base)
        no_bundle = SimpleNamespace(hd_raw_resource=lambda resource_id: None)
        self.assertIs(vt.hd_font(no_bundle, 'ArialRoundedMTBold16', self.base), self.base)
        self.assertIs(vt.hd_font(no_bundle, 'PajamaHip26', self.base), self.base)
        os.environ['SHS_VECTOR_TEXT'] = '0'
        self.addCleanup(os.environ.pop, 'SHS_VECTOR_TEXT', None)
        bundle = SimpleNamespace(hd_raw_resource=lambda resource_id: b'x')
        self.assertIs(vt.hd_font(bundle, 'ArialRoundedMTBold16', self.base), self.base)


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class LibraryFontTests(unittest.TestCase):
    """A player who owns the real font but hasn't installed it system-wide can drop it into their own
    library's `fonts/` folder instead (see `vector_text.py`'s own module docstring)."""

    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        pygame.font.init()
        self.addCleanup(pygame.quit)
        from exp_runtime import vector_text
        self.vt = vector_text
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.library = SimpleNamespace(directory=self.root)

    def _drop(self, filename, content=b'not a real font, the path alone is what matters here'):
        fonts_dir = self.root / 'fonts'
        fonts_dir.mkdir(exist_ok=True)
        path = fonts_dir / filename
        path.write_bytes(content)
        return path

    def test_a_supplied_font_wins_over_the_os_search(self):
        path = self._drop('arialroundedmtbold.ttf')
        with mock.patch.object(self.vt.pygame.font, 'match_font', return_value='/os/some-other-font.ttf'):
            self.assertEqual(self.vt.system_font_path('arial-rounded', self.library), str(path))

    def test_filename_matching_is_case_insensitive(self):
        path = self._drop('ArialRoundedMTBold.TTF')
        self.assertEqual(self.vt.system_font_path('arial-rounded', self.library), str(path))

    def test_an_env_override_still_wins_over_a_supplied_font(self):
        self._drop('arialroundedmtbold.ttf')
        override = self.root / 'override.ttf'
        override.write_bytes(b'x')
        os.environ['SHS_ARIAL_ROUNDED_FONT'] = str(override)
        self.addCleanup(os.environ.pop, 'SHS_ARIAL_ROUNDED_FONT', None)
        self.assertEqual(self.vt.system_font_path('arial-rounded', self.library), str(override))

    def test_no_library_or_no_match_falls_back_to_the_os_search(self):
        with mock.patch.object(self.vt.pygame.font, 'match_font', return_value='/os/fallback.ttf'):
            self.assertEqual(self.vt.system_font_path('arial-rounded'), '/os/fallback.ttf')
            self.assertEqual(self.vt.system_font_path('arial-rounded', self.library), '/os/fallback.ttf')
            self._drop('somethingelse.ttf')
            self.assertEqual(self.vt.system_font_path('arial-rounded', self.library), '/os/fallback.ttf')

    def test_a_real_font_file_loads_and_measures_as_arial_rounded(self):
        """Verified with the owner's own real Arial Rounded MT Bold file when present in the project's own
        `reference/` folder (one level above this checkout, never committed); skipped otherwise, the same way
        other tests here skip when optional local content is absent."""
        import pygame
        real = Path(__file__).resolve().parents[2] / 'reference' / 'arialroundedmtbold.ttf'
        if not real.is_file():
            self.skipTest('no real Arial Rounded MT Bold file to test with')
        self._drop('arialroundedmtbold.ttf', real.read_bytes())
        path = self.vt.system_font_path('arial-rounded', self.library)
        self.assertIn('round', path.lower())
        font = pygame.font.Font(path, 32)
        self.assertGreater(font.size('Surviving High School')[0], 0)


if __name__ == '__main__':
    unittest.main()
