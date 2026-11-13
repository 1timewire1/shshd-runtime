"""v0.6.1 palette regression checks using Pillow's freely supplied font."""
from types import SimpleNamespace
import unittest
from PIL import ImageFont

from exp_runtime.dialogue import dialogue_styles
from exp_runtime.dialogue_notice import notice_font, NOTICE_FONT
from exp_runtime.ios_fonts import render_font


class CoDColorsTests(unittest.TestCase):
    def test_narration_is_black_and_emphasis_is_gold(self):
        style = dialogue_styles(1, narrator=True, game='cod')[-1]
        self.assertEqual(style.color, (0, 0, 0))
        self.assertIn(('`', (180, 109, 26)), style.markers)

    def test_each_notice_theme_rasterizes_its_own_palette(self):
        data = ImageFont.load_default().font_bytes
        library = SimpleNamespace(game_id='cod', base_members={291}, read_asset=lambda _: data)
        for theme, expected in ((1, (240, 81, 60)), (2, (180, 78, 78)),
                                (3, (0, 0, 0)), (-1, (0, 0, 0)), (99, (0, 0, 0))):
            with self.subTest(theme=theme):
                _, atlas = render_font(library, notice_font('cod', theme))
                colors = {color for _, color in atlas.getcolors(atlas.width * atlas.height)}
                self.assertIn((*expected, 255), colors)
                self.assertIn((255, 255, 255, 255), colors)

    def test_shs_keeps_its_original_notice_and_narrator_palette(self):
        for theme in (1, 2, 3, -1):
            self.assertEqual(notice_font('shs', theme), NOTICE_FONT)
        self.assertEqual(dialogue_styles(1, narrator=True, game='shs')[-1].color, (223, 163, 52))
