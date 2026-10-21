"""Authored depth/colour contracts shared by SDL and the iOS command stream."""
import importlib.util
import unittest

from PIL import Image

from exp_runtime import graphics
from exp_runtime.desktop_pause import SEPIA
from exp_runtime.platforms import drawing
from exp_runtime.projection import draw_depth_quads


class PresentationPixelTests(unittest.TestCase):
    def test_intersecting_faces_use_pixel_depth_and_keep_the_background_clip(self):
        original = graphics.install(drawing.Backend(None, None))
        self.addCleanup(graphics.install, original)
        # Two intersecting planes have the same average distance. Sorting
        # whole faces cannot make red win on the left and blue on the right.
        red = graphics.Surface((4, 4), graphics.SRCALPHA); red.fill((255, 0, 0))
        blue = graphics.Surface((4, 4), graphics.SRCALPHA); blue.fill((0, 0, 255))
        front = ((2, 2, -2), (30, 2, -4), (30, 30, -4), (2, 30, -2))
        back = ((2, 2, -4), (30, 2, -2), (30, 30, -2), (2, 30, -4))
        faces = [(red, front), (blue, back)]
        outputs = []
        for ordered in (faces, list(reversed(faces))):
            target = graphics.Surface((32, 32)); target.fill((40, 50, 60))
            target.set_clip((4, 4, 24, 24))
            draw_depth_quads(target, ordered)
            pixels = drawing.raster(target.snapshot())
            self.assertEqual(pixels.getpixel((6, 16)), (255, 0, 0, 255))
            self.assertEqual(pixels.getpixel((25, 16)), (0, 0, 255, 255))
            self.assertEqual(pixels.getpixel((3, 16)), (40, 50, 60, 255))
            outputs.append(pixels.tobytes())
        self.assertEqual(*outputs)
        if importlib.util.find_spec('pygame'):
            import pygame
            graphics.install(None)
            desktop = pygame.Surface((32, 32)); desktop.fill((40, 50, 60))
            desktop.set_clip((4, 4, 24, 24))
            faces = [(pygame.image.frombytes(drawing.ImageAPI.tobytes(image, 'RGBA'), (4, 4), 'RGBA'), points)
                     for image, points in faces]
            draw_depth_quads(desktop, faces)
            self.assertEqual(pygame.image.tobytes(desktop, 'RGBA'), outputs[0])

    def test_depth_equal_passes_and_transparent_texels_write_depth(self):
        original = graphics.install(drawing.Backend(None, None))
        self.addCleanup(graphics.install, original)
        clear = graphics.Surface((2, 2), graphics.SRCALPHA)
        red = graphics.Surface((2, 2)); red.fill((255, 0, 0))
        plane = ((0, 0, -2), (8, 0, -2), (8, 8, -2), (0, 8, -2))
        far = tuple((x, y, -4) for x, y, _ in plane)
        target = graphics.Surface((8, 8)); target.fill((10, 20, 30))
        draw_depth_quads(target, [(clear, plane), (red, far)])
        self.assertEqual(drawing.raster(target.snapshot()).getpixel((4, 4)), (10, 20, 30, 255))
        draw_depth_quads(target, [(clear, plane), (red, plane)])
        self.assertEqual(drawing.raster(target.snapshot()).getpixel((4, 4)), (255, 0, 0, 255))

    def test_native_pause_sepia_truncates_clamps_and_retains_a_snapshot(self):
        original = graphics.install(drawing.Backend(None, None))
        self.addCleanup(graphics.install, original)
        rgb = bytes((255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 255, 17, 38, 79))
        source = drawing.Surface.from_pixels(Image.frombytes('RGB', (5, 1), rgb).convert('RGBA'))
        transformed = graphics.color_matrix(source, SEPIA)
        expected = bytes((100, 88, 69, 196, 174, 136, 48, 42, 33, 255, 255, 238, 50, 45, 35))
        self.assertEqual(drawing.ImageAPI.tobytes(transformed, 'RGB'), expected)
        source.fill((0, 0, 0))
        self.assertEqual(drawing.ImageAPI.tobytes(transformed, 'RGB'), expected)
        if importlib.util.find_spec('pygame'):
            import pygame
            graphics.install(None)
            source = pygame.image.frombytes(rgb, (5, 1), 'RGB')
            self.assertEqual(pygame.image.tobytes(graphics.color_matrix(source, SEPIA), 'RGB'), expected)
