"""The HD faceplace alert card, with authored frames and fonts only."""
import importlib.util
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from exp_runtime.dtview_faceplace import FaceplaceMessage, FaceplaceToast
from exp_runtime.engine import EngineState
from exp_runtime.fonts import BitmapFont, Glyph


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class FaceplaceAlertTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        pygame.init()
        pygame.display.set_mode((16, 16))
        self.addCleanup(pygame.quit)
        from exp_runtime import desktop_faceplace_alert as module
        self.module = module
        self.calls = []

        def solid(size, color):
            surface = pygame.Surface(size, pygame.SRCALPHA)
            surface.fill(color)
            return surface

        sizes = {73: (194, 20), 38: (214, 16), 39: (214, 2), 40: (214, 16), 69: (18, 19), 70: (18, 20), 71: (18, 20)}
        colors = {73: (0, 0, 200, 255), 38: (200, 0, 0, 255), 39: (0, 200, 0, 255), 40: (200, 200, 0, 255),
                  69: (255, 200, 0, 255), 70: (255, 0, 100, 255), 71: (255, 220, 0, 255)}
        self.art = SimpleNamespace(
            scale=2, hd_chrome=lambda: True, pack=lambda _id: SimpleNamespace(images=[None] * 80),
            frame_native=lambda pack, index: solid(sizes[index], colors[index]),
            portrait_group=lambda portrait: (solid((256, 300), (255, 0, 255, 255)), (-128, -150)))
        outer = self

        class Text:
            fonts = {}

            def layout(self, name, text, width, style):
                # Ten characters to a line, whatever the width.
                lines = max(1, -(-len(text) // 10))
                return SimpleNamespace(width=min(len(text), 10) * 7, lines=[None] * lines)

            def font(self, name):
                return BitmapFont('Test', 14, 14, 'page', {32: Glyph(32, 0, 0, 0, 0, 0, 0, 4)}, {}, base=11)

            def draw_layout(self, surface, name, layout, x, y, *, scale=1, inline=None):
                outer.calls.append((name, x, y))

        self.text = Text()
        fonts = {'ArialMT14': BitmapFont('Arial', 14, 14, 'page', {97: Glyph(97, 0, 0, 5, 7, 0, 4, 5)}, {}, base=11),
                 'ArialRoundedMTBold14': BitmapFont('Rounded', 14, 14, 'page', {97: Glyph(97, 0, 0, 6, 7, 0, 4, 6)}, {},
                                                    base=11)}
        self.loaded = fonts
        patcher = patch.object(module, 'load_font_sized', lambda library, name, size: fonts[name])
        patcher.start()
        self.addCleanup(patcher.stop)
        self.renderer = module.FaceplaceAlertRenderer(SimpleNamespace(library=None), self.text, self.art)

    def engine(self):
        engine = EngineState()
        engine.character_names = {11: 'Beth'}
        engine.character_art_variants = {11: [2050, 2051]}
        engine.numbers[engine.number_key(11, 651)] = 2
        return engine

    def test_the_body_font_is_arial_at_arial_rounded_advances(self):
        # `initFonts` builds the ArialMT CSFontInfo from the Arial Rounded CGFont: Arial's glyphs, Rounded's advances.
        body_key, _ = self.renderer.fonts()
        glyph = self.text.fonts[body_key][0].glyph('a')
        self.assertEqual((glyph.width, glyph.advance), (5, 6))

    def test_braces_and_a_greater_than_sign_are_the_emoticon_frames(self):
        # `checkInit`: addCharImage makes '{', '>' and '}' the pack-155 frames 69, 70 and 71 in the body font.
        self.assertEqual(self.renderer.with_emoticons('so { and > and }'), 'so  and  and ')
        key, images = self.renderer.emoticon_font()
        font = self.text.fonts[key][0]
        # ... at offset (-1, 6) with anchor bottom | left, advancing 16: the 18-wide frames overlap their neighbours.
        self.assertEqual({code: font.glyph(chr(code)).advance for code in images}, {1: 16, 2: 16, 3: 16})
        self.assertEqual([images[code].get_size() for code in (1, 2, 3)], [(18, 19), (18, 20), (18, 20)])
        body = self.text.font(self.renderer.fonts()[0])
        for code in images:                                                     # bottom 6 below the baseline, 1 left of the pen
            glyph = font.glyph(chr(code))
            self.assertEqual((glyph.xoffset, glyph.yoffset + glyph.height), (-1, body.base + 6))
        self.assertEqual(self.renderer.emoticon_font()[0], key)                 # registered once

    def test_available_needs_the_title_frame_and_fonts(self):
        self.assertTrue(self.renderer.available())
        self.art.pack = lambda _id: SimpleNamespace(images=[None] * 10)
        self.assertFalse(self.renderer.available())

    def test_key_cuts_the_text_at_a_tilde_and_takes_the_theme_from_the_speaker(self):
        engine = self.engine()
        key = self.renderer.key(engine, FaceplaceMessage('message', text='Hi there~hidden', from_id=11, expression=3))
        self.assertEqual((key.text, key.name), ('Hi there', 'Beth'))
        # Expression 3 of the two variants, never mirrored (drawFace's hflip is 0).
        self.assertEqual((key.portrait.asset_id, key.portrait.mode, key.portrait.theme), (2051, 1, 2))
        plain = self.renderer.key(engine, FaceplaceMessage('continuation_text', text='More', url='u'))
        self.assertIsNone(plain.portrait)
        self.assertEqual(plain.name, '')

    def test_card_height_follows_the_lines_with_a_56_px_floor_for_a_face(self):
        engine = self.engine()
        module = self.module
        short = self.renderer.card(self.renderer.key(engine, FaceplaceMessage('message', text='Hi', from_id=11, expression=0)))
        # One line is under the 56 px minimum, so the floor wins.
        self.assertEqual(short.get_height(), round(module.CHROME + module.MIN_MESSAGE_HEIGHT))
        long = self.renderer.card(self.renderer.key(engine, FaceplaceMessage(
            'message', text='x' * 80, from_id=11, expression=0)))
        self.assertEqual(long.get_height(), round(module.CHROME + module.LINE_PITCH * 8 + module.TEXT_PAD))
        plain = self.renderer.card(self.renderer.key(engine, FaceplaceMessage('continuation_text', text='Hi', url='u')))
        self.assertEqual(plain.get_height(), round(module.CHROME + module.LINE_PITCH + module.TEXT_PAD))

    def test_card_is_built_from_the_top_middle_and_bottom_frames_under_the_title(self):
        engine = self.engine()
        card = self.renderer.card(self.renderer.key(engine, FaceplaceMessage('message', text='Hi', from_id=11, expression=0)))
        self.assertEqual(card.get_width(), 214)
        self.assertEqual(card.get_at((2, 1))[:3], (200, 200, 0))            # frame 40 on top
        self.assertEqual(card.get_at((2, 30))[:3], (0, 200, 0))             # frame 39 stretched
        self.assertEqual(card.get_at((2, card.get_height() - 2))[:3], (200, 0, 0))  # frame 38 below
        self.assertEqual(card.get_at((60, 8))[:3], (0, 0, 200))             # the 194 px title
        # The face at 0.2 scale: a 256x300 group -> 51x60 around (38.5, 54.8).
        self.assertEqual(card.get_at((39, 55))[:3], (255, 0, 255))
        # Name first (in the name font), then the body, on the same baseline.
        self.assertEqual([call[0] for call in self.calls], ['FaceplaceName', 'FaceplaceBodyEmoticons'])
        self.assertEqual(self.calls[0][1:], (self.module.FACE_TEXT_X, self.module.BASELINE - 11))

    def test_the_alert_slides_in_from_the_right_and_is_cut_by_the_frame(self):
        engine = self.engine()
        toast = FaceplaceToast(FaceplaceMessage('message', text='Hi', from_id=11, expression=0))
        module = self.module
        start = self.renderer.draw(engine, toast)
        self.assertEqual(start.get_size(), (768, 1024))
        self.assertEqual(start.get_at((760, module.CARD_TOP + 5)).a, 0)     # still off screen
        toast.tick(100)
        halfway = self.renderer.draw(engine, toast)
        self.assertEqual(self.renderer.slide(0.5), 0.5)                     # ease in-out
        self.assertEqual(halfway.get_at((760, module.CARD_TOP + 5)).a, 0)   # 452 px away still
        toast.tick(90)
        self.assertGreater(self.renderer.draw(engine, toast).get_at((760, module.CARD_TOP + 5)).a, 0)
        toast.tick(200)
        done = self.renderer.draw(engine, toast)
        self.assertEqual(done.get_at((module.CARD_LEFT + 2, module.CARD_TOP + 1))[:3], (200, 200, 0))
        # The strip is 224 px wide from 560 but the frame ends at 768: the card is cut.
        self.assertEqual(done.get_at((767, module.CARD_TOP + 1))[:3], (200, 200, 0))


if __name__ == '__main__':
    unittest.main()
