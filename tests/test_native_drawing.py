"""Authored backend contracts: geometry, masks, immutable frames and imports."""
from io import BytesIO
import json
import os
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
if importlib.util.find_spec('pygame'):
    import pygame
from PIL import Image

from exp_runtime.platforms import drawing as d


class NativeDrawingTests(unittest.TestCase):
    def test_perspective_projection_preserves_corners_clipping_alpha_and_cache(self):
        from types import SimpleNamespace
        from exp_runtime import graphics
        from exp_runtime.projection import draw_quad, inverse_quad
        previous = graphics.install(SimpleNamespace(draw=d.Draw))
        self.addCleanup(graphics.install, previous)
        points = ((2, 5), (27, 1), (30, 28), (4, 24))
        a, b, c, e, f, g, h, i = inverse_quad(points)
        for (x, y), (u, v) in zip(points, ((0, 0), (1, 0), (1, 1), (0, 1))):
            self.assertAlmostEqual((a*x + b*y + c) / (h*x + i*y + 1), u)
            self.assertAlmostEqual((e*x + f*y + g) / (h*x + i*y + 1), v)
        self.assertIsNone(inverse_quad(((0, 0), (0, 0), (1, 1), (1, 1))))
        source = d.Surface.from_pixels(Image.new('RGBA', (4, 6), (240, 10, 20, 255)))
        source.fill((10, 230, 20), (0, 0, 4, 2))
        source.fill((20, 10, 220), (2, 4, 2, 2))
        source.set_alpha(128)
        encoder = d.FrameEncoder()
        for _ in range(2):
            target = d.Surface((32, 32)); target.fill((0, 0, 0))
            target.set_clip((4, 4, 25, 25))
            draw_quad(target, source, points)
            pixels = d.raster(target.snapshot())
            self.assertEqual(pixels.getpixel((3, 6)), (0, 0, 0, 255))
            self.assertEqual(pixels.getpixel((8, 6)), (5, 115, 10, 255))
            self.assertEqual(pixels.getpixel((9, 20)), (120, 5, 10, 255))
            self.assertEqual(pixels.getpixel((25, 24)), (10, 5, 110, 255))
            packet = encoder.encode(target)
            self.assertEqual(sum('png' in node for node in packet['nodes']), int(_ == 0))

    def test_batched_projection_preserves_scanlines_clipping_alpha_and_source_cache(self):
        from types import SimpleNamespace
        from exp_runtime import graphics
        previous = graphics.install(SimpleNamespace(draw=d.Draw, transform=d.Transform))
        self.addCleanup(graphics.install, previous)
        source = d.Surface.from_pixels(Image.new('RGBA', (8, 6), (240, 10, 20, 128)))
        source.fill((20, 200, 100, 255), (0, 0, 4, 2))
        encoder = d.FrameEncoder()
        for frame in range(20):
            points = ((-2.5, 3.5), (17.5, 3.5), (23.5 + frame, 18.5), (4.5, 18.5))
            fast, reference = d.Surface((32, 32)), d.Surface((32, 32))
            for target in (fast, reference):
                target.fill((10, 20, 30))
                target.set_clip((2, 2, 25, 26))
            graphics.project_quad(fast, source, points)
            with patch.object(d.Draw, 'textured_rows', None):
                graphics.project_quad(reference, source, points)
            self.assertEqual(d.raster(fast.snapshot()).tobytes(), d.raster(reference.snapshot()).tobytes())
            packet = encoder.encode(fast)
            self.assertLessEqual(len(packet['nodes']), 2 if frame else 3)
            if frame:
                self.assertFalse(any('png' in node for node in packet['nodes']))

    def test_shared_text_preserves_one_baseline_at_half_pixel_origins(self):
        from types import SimpleNamespace
        from exp_runtime.desktop_text import BitmapTextRenderer
        from exp_runtime.fonts import BitmapFont, Glyph, TextStyle, layout_text
        font = BitmapFont('Authored', 10, 10, 'none', {
            ord('A'): Glyph(ord('A'), 0, 0, 1, 6, 0, 0, 3),
            ord('i'): Glyph(ord('i'), 0, 0, 1, 7, 0, -1, 3)}, {})
        renderer = BitmapTextRenderer.__new__(BitmapTextRenderer)
        renderer.font = lambda _: font
        renderer._glyph = lambda name, glyph, scale: (chr(glyph.glyph.code), 0, 0)
        placed = []
        surface = SimpleNamespace(blit=lambda image, point: placed.append((image, point)))
        text = layout_text(font, 'AiAi', 100, TextStyle(10))
        for origin in (-2.5, 0, 3.5, 4.5, 12.5):
            placed.clear()
            renderer.draw_layout(surface, 'Authored', text, origin, origin)
            self.assertEqual(len({y + font.glyph(char).height for char, (x, y) in placed}), 1)
            self.assertEqual([x - placed[0][1][0] for _, (x, y) in placed], [0, 3, 6, 9])

    @unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
    def test_integer_geometry_matches_desktop_hit_regions(self):
        for values in ((0, 0, 320, 480), (-12.6, 9.8, 71.1, 33.9), (1, 5, 6, 7)):
            rect, native = pygame.Rect(values), d.Rect(values)
            for method, args in (('move', (-2.9, 1.7)), ('inflate', (-7, 5)), ('clip', ((10, 9, 20, 11),)),
                                 ('unionall', ([(10, -30, 10, 20), (-2, 10, 30, 50)],)), ('copy', ())):
                with self.subTest(values=values, method=method):
                    self.assertEqual(tuple(getattr(native, method)(*args)), tuple(getattr(rect, method)(*args)))
            self.assertEqual(native.center, rect.center)
            for point in ((0, 0), (1, 5), (319, 479), (320, 480)):
                self.assertEqual(native.collidepoint(point), rect.collidepoint(point))
        for x in (-2.5, -.5, .5, 1.5, 2.5):
            pg = pygame.Surface((7, 11)).get_rect(center=(x, x))
            own = d.Surface((7, 11)).get_rect(center=(x, x))
            self.assertEqual(tuple(own), tuple(pg), x)

    def test_copies_and_blits_capture_the_image_before_subsequent_writes(self):
        source = d.Surface((2, 2), d.SRCALPHA)
        source.fill((255, 0, 0, 255))
        saved = source.copy()
        target = d.Surface((4, 2))
        target.blit(source, (0, 0))
        source.fill((0, 255, 0, 255))
        target.blit(source, (2, 0))
        image = d.raster(target.snapshot())
        self.assertEqual(image.getpixel((0, 0)), (255, 0, 0, 255))
        self.assertEqual(image.getpixel((3, 1)), (0, 255, 0, 255))
        self.assertEqual(d.raster(saved.snapshot()).getpixel((0, 0)), (255, 0, 0, 255))

    @unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
    def test_alpha_modulation_and_timer_mask_match_desktop_bytes(self):
        pixels = bytes(range(256)) * 4
        desktop = pygame.image.frombytes(pixels, (16, 16), 'RGBA')
        mobile = d.ImageAPI.frombytes(pixels, (16, 16), 'RGBA')
        for color in ((255, 255, 255, 255), (50, 128, 201, 3)):
            pg, own = desktop.copy(), mobile.copy()
            pg.fill(color, special_flags=pygame.BLEND_RGBA_MULT)
            own.fill(color, special_flags=d.BLEND_RGBA_MULT)
            self.assertEqual(d.ImageAPI.tobytes(own, 'RGBA'), pygame.image.tobytes(pg, 'RGBA'))
        mask = d.Surface((16, 16), d.SRCALPHA)
        d.Draw.polygon(mask, (255, 255, 255), ((8, 8), (8, 0), (15, 0), (15, 8)))
        mobile.blit(mask, (0, 0), special_flags=d.BLEND_RGBA_MULT)
        self.assertEqual(d.raster(mobile.snapshot()).getpixel((0, 15)), (0, 0, 0, 0))

    def test_whole_surface_fade_is_a_host_alpha_blit(self):
        """graphics.faded's multiply by white over a whole surface: the host's alpha on a blit, not a Python raster
        (every glyph and button of an HD fade, every frame), within SDL's rounding of pygame's bytes."""
        pixels = bytes(range(256)) * 4
        desktop = pygame.image.frombytes(pixels, (16, 16), 'RGBA')
        mobile = d.ImageAPI.frombytes(pixels, (16, 16), 'RGBA')
        pg, own = desktop.copy(), mobile.copy()
        pg.fill((255, 255, 255, 128), special_flags=pygame.BLEND_RGBA_MULT)
        with patch.object(d.Surface, '_blend_into', side_effect=AssertionError('rasterised in Python')):
            own.fill((255, 255, 255, 128), special_flags=d.BLEND_RGBA_MULT)
        self.assertEqual([(op['kind'], op['alpha']) for op in own.snapshot().ops], [('blit', 128)])
        self.assertEqual(d.ImageAPI.tobytes(mobile, 'RGBA'), pixels)          # the source keeps its pixels
        got, want = d.ImageAPI.tobytes(own, 'RGBA'), pygame.image.tobytes(pg, 'RGBA')
        for index in range(0, len(got), 4):
            self.assertLessEqual(abs(got[index + 3] - want[index + 3]), 1)
            if got[index + 3] and want[index + 3]:
                self.assertEqual(got[index:index + 3], want[index:index + 3])

    def test_subsurface_reads_of_an_image_reuse_one_node(self):
        """A font sheet's glyph read through a subsurface every frame is one node (one PNG for the host)."""
        sheet = d.Surface.from_pixels(Image.new('RGBA', (8, 8), (1, 2, 3, 255)))
        glyph = sheet.subsurface((2, 2, 3, 3)).snapshot()
        self.assertIs(sheet.subsurface((2, 2, 3, 3)).snapshot(), glyph)
        self.assertIsNot(sheet.subsurface((2, 2, 3, 4)).snapshot(), glyph)
        encoder, canvas = d.FrameEncoder(), d.Surface((16, 16))
        sent = []
        for _ in range(3):
            canvas.fill((0, 0, 0))
            canvas.blit(sheet.subsurface((2, 2, 3, 3)), (4, 4))
            sent.append([node for node in encoder.encode(canvas)['nodes'] if 'png' in node])
        self.assertEqual([len(nodes) for nodes in sent], [1, 0, 0])

    def test_frame_graph_releases_transients_and_reuses_cached_images(self):
        encoder = d.FrameEncoder()
        canvas = d.Surface((320, 480))
        image = d.Surface.from_pixels(Image.new('RGBA', (2, 2), (100, 120, 140, 255)))
        cached = image.snapshot().identifier
        for i in range(100):
            canvas.fill((0, 0, 0))
            canvas.blit(image, (i, 0))
            packet = json.loads(json.dumps(encoder.encode(canvas)))
            self.assertEqual(len(encoder.previous), 2)
            if i:
                self.assertEqual(len(packet['release']), 1)
                self.assertNotIn(cached, [n['id'] for n in packet['nodes']])
        canvas.blit(d.Transform.scale(image, (320, 480)), (0, 0))
        encoder.encode(canvas)
        self.assertLessEqual(len(encoder.previous), 3)

    def test_animated_sprite_scaling_sends_commands_and_reuses_source_pixels(self):
        encoder = d.FrameEncoder()
        image = d.Surface.from_pixels(Image.new('RGBA', (80, 120), (70, 130, 190, 255)))
        canvas = d.Surface((320, 480))
        for frame in range(30):
            canvas.fill((0, 0, 0))
            scaled = d.Transform.smoothscale(image, (90 + frame, 130 + frame))
            canvas.blit(scaled, (10, 10))
            packet = encoder.encode(canvas)
            pngs = [node for node in packet['nodes'] if 'png' in node]
            self.assertEqual(len(pngs), 0 if frame else 1)
            self.assertEqual(d.raster(canvas.snapshot()).getpixel((20, 20)), (70, 130, 190, 255))
            self.assertLessEqual(len(encoder.previous), 3)

    @unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
    def test_rotation_bounds_preserve_desktop_sprite_centers(self):
        for size in ((61, 60), (10, 7), (128, 128)):
            pg, own = pygame.Surface(size), d.Surface(size)
            for angle in (0, 10, 45, 90, -167):
                for scale in (.5, 1, 1.3):
                    with self.subTest(size=size, angle=angle, scale=scale):
                        self.assertEqual(d.Transform.rotozoom(own, angle, scale).get_size(),
                                         pygame.transform.rotozoom(pg, angle, scale).get_size())
                self.assertEqual(d.Transform.rotate(own, angle).get_size(), pygame.transform.rotate(pg, angle).get_size())

    def test_ios_launcher_remembers_relative_locations_after_relocation(self):
        from exp_runtime import launcher
        with tempfile.TemporaryDirectory() as temporary, patch.object(launcher.sys, 'platform', 'ios'), \
                patch.object(launcher.Path, 'home', return_value=Path(temporary)):
            root = launcher.user_data_directory()
            library = root / 'libraries/imported/authored'
            launcher.remember_library(library, 'cod')
            record = json.loads((root / 'launcher.json').read_text())
            self.assertEqual(record['libraries']['cod'], 'libraries/imported/authored')
            self.assertEqual(launcher.default_library('cod'), library)
            self.assertEqual(launcher.default_library('shs'), root / 'libraries/shs')


if __name__ == '__main__':
    unittest.main()
