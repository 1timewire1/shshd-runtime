"""The native drawing backend's pygame features the HD and Cause of Death screens use (platforms/drawing.py): pygame's
subsurfaces, the five blends, Rect's positional attributes, the font module and interface sounds."""
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image

from exp_runtime.platforms import drawing
from exp_runtime.platforms.drawing import (BLEND_RGB_ADD, BLEND_RGB_MULT, BLEND_RGBA_MAX, BLEND_RGBA_MIN,
                                           BLEND_RGBA_MULT, SRCALPHA, Draw, FRect, Rect, Surface, raster)
from native_host_fonts import FontHost


def pixel(surface, point):
    return raster(surface.snapshot()).getpixel(point)


class SubsurfaceTests(unittest.TestCase):
    def test_a_subsurface_draws_into_its_parent_clipped_to_itself(self):
        # The HD dialogue renderer draws its 320-unit column into the frame-wide layer through one.
        wide = Surface((100, 50), SRCALPHA)
        column = wide.subsurface((20, 0, 60, 50))
        column.fill((255, 0, 0, 255), (0, 0, 10, 10))
        Draw.rect(column, (0, 255, 0, 255), (5, 20, 10, 10))
        column.blit(Surface((70, 5)), (50, 45))
        self.assertEqual(pixel(wide, (20, 0)), (255, 0, 0, 255))
        self.assertEqual(pixel(wide, (19, 0))[3], 0)
        self.assertEqual(pixel(wide, (26, 21)), (0, 255, 0, 255))
        self.assertEqual(pixel(wide, (79, 46)), (0, 0, 0, 255))
        self.assertEqual(pixel(wide, (80, 46))[3], 0)                       # clipped at the column's edge
        copy = column.copy()
        wide.fill((0, 0, 255, 255))
        self.assertEqual(pixel(copy, (0, 0)), (255, 0, 0, 255))             # a copy keeps what it read
        self.assertEqual(pixel(column, (0, 0)), (0, 0, 255, 255))           # the view follows its parent
        self.assertEqual(column.subsurface((10, 10, 5, 5)).copy().get_size(), (5, 5))


class BlendTests(unittest.TestCase):
    def setUp(self):
        self.base = Surface((4, 4), SRCALPHA)
        self.base.fill((200, 100, 50, 128))
        self.top = Surface((2, 2), SRCALPHA)
        self.top.fill((100, 200, 250, 255))

    def test_the_rgba_blends_combine_every_channel_where_the_source_lands(self):
        for flags, expected in ((BLEND_RGBA_MIN, (100, 100, 50, 128)), (BLEND_RGBA_MAX, (200, 200, 250, 255)),
                                (BLEND_RGBA_MULT, (79, 79, 49, 128))):   # SDL: (a * b + 255) >> 8
            with self.subTest(flags=flags):
                surface = self.base.copy()
                surface.blit(self.top, (1, 1), special_flags=flags)
                self.assertEqual(pixel(surface, (2, 2)), expected)
                self.assertEqual(pixel(surface, (0, 0)), (200, 100, 50, 128))

    def test_the_rgb_blends_keep_the_destinations_alpha(self):
        surface = self.base.copy()
        surface.blit(self.top, (0, 0), special_flags=BLEND_RGB_ADD)
        self.assertEqual(pixel(surface, (1, 1)), (255, 255, 255, 128))
        surface = self.base.copy()
        surface.fill((128, 128, 128), special_flags=BLEND_RGB_MULT)
        self.assertEqual(pixel(surface, (3, 3)), (100, 50, 25, 128))

    def test_an_opaque_surfaces_fades_go_to_the_host_as_blended_ops(self):
        # The HD menus darken their whole canvas every frame of a fade: the host's multiply, not Python pixels.
        canvas = Surface((4, 4))
        canvas.fill((200, 100, 50))
        canvas.fill((128, 128, 128), special_flags=BLEND_RGB_MULT)
        art = Surface((4, 4))
        art.fill((10, 20, 30))
        black = Surface((4, 4))
        black.blit(art, (0, 0), special_flags=BLEND_RGB_ADD)
        self.assertEqual([op.get('blend') for op in canvas.snapshot().ops], [None, 'multiply'])
        self.assertEqual(black.snapshot().ops[-1]['blend'], 'add')
        self.assertEqual(pixel(canvas, (0, 0)), (100, 50, 25, 255))         # the reference raster agrees
        self.assertEqual(pixel(black, (0, 0)), (10, 20, 30, 255))


class RectTests(unittest.TestCase):
    def test_positional_attributes_read_and_move(self):
        rect = Rect(10, 20, 30, 40)
        rect.midbottom = (100, 200)
        self.assertEqual(tuple(rect), (85, 160, 30, 40))
        rect.topright = (50, 0)
        self.assertEqual((rect.left, rect.top, rect.bottomleft), (20, 0, (20, 40)))
        rect.size = (6, 8)
        self.assertEqual((rect.w, rect.h, rect.center), (6, 8, (23, 4)))
        self.assertEqual(tuple(rect.move((1, 2))), (21, 2, 6, 8))
        self.assertTrue(Rect(0, 0, 10, 10).contains((2, 2, 3, 3)))
        rect = FRect(0, 0, 3, 3)
        rect.center = (1.5, 1.5)
        self.assertEqual(rect.topleft, (0.0, 0.0))


class FontTests(unittest.TestCase):
    def test_system_faces_by_family_and_supplied_fonts_registered_once(self):
        host = FontHost()
        fonts = drawing.Fonts(host)
        self.assertTrue(fonts.get_init())
        self.assertEqual(fonts.match_font('arialroundedmtbold', bold=True), 'ArialRoundedMTBold')
        self.assertEqual(fonts.match_font('trebuchetms', italic=True), 'TrebuchetMS-Italic')
        self.assertIsNone(fonts.match_font('liberationsans'))
        data = b'authored font bytes'
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'Authored.ttf'
            path.write_bytes(data)
            first, second = fonts.Font(BytesIO(data), 20), fonts.Font(str(path), 30)
        self.assertEqual((first.face, second.face, host.registered), ('Registered1', 'Registered1', [data]))
        self.assertEqual(fonts.Font('ArialMT', 12).face, 'ArialMT')

    def test_the_pygame_font_calls_the_hd_text_uses(self):
        font = drawing.Fonts(FontHost()).Font('ArialMT', 40)
        minx, maxx, miny, maxy, advance = font.metrics('H')[0]
        self.assertTrue(maxx > minx and maxy > 0 and advance > 0)
        self.assertGreater(font.get_ascent(), 0)
        self.assertEqual(font.get_height(), font.get_ascent() - font.get_descent())
        image = font.render('H', True, (0, 0, 0))
        self.assertEqual(image.get_height(), font.get_height())


class DrawingTests(unittest.TestCase):
    def test_polylines_and_ellipses(self):
        # The side panels' Decision Tree branches and Faceplace badges.
        surface = Surface((20, 20), SRCALPHA)
        Draw.lines(surface, (255, 0, 0), False, [(0, 0), (10, 0), (10, 10)], 1)
        Draw.aalines(surface, (0, 255, 0), True, [(15, 15), (19, 15), (19, 19)])
        Draw.ellipse(surface, (0, 0, 255), (2, 12, 6, 6))
        self.assertEqual(pixel(surface, (5, 0)), (255, 0, 0, 255))
        self.assertEqual(pixel(surface, (10, 5)), (255, 0, 0, 255))
        self.assertEqual(pixel(surface, (17, 17)), (0, 255, 0, 255))     # closed: the last point joins the first
        self.assertEqual(pixel(surface, (5, 15)), (0, 0, 255, 255))
        self.assertEqual(surface.snapshot().ops[-1]['kind'], 'ellipse')

    def test_image_save_writes_the_named_format(self):
        surface = Surface((3, 2))
        surface.fill((10, 200, 30))
        api = drawing.ImageAPI(None)
        with tempfile.TemporaryDirectory() as folder:
            jpeg, png = Path(folder) / 'shot.tmp', Path(folder) / 'tile.png'
            api.save(surface, str(jpeg), 'jpg')
            api.save(surface, str(png))
            with Image.open(jpeg) as image:
                self.assertEqual(image.format, 'JPEG')
            with Image.open(png) as image:
                self.assertEqual(image.getpixel((2, 1)), (10, 200, 30, 255))

    def test_system_faces_report_their_cap_height_and_descender(self):
        # vector_text reads these for a face it has no file for (iOS's system fonts).
        font = drawing.Fonts(FontHost()).Font('ArialMT', 100)
        self.assertGreater(font.cap_height(), 0)
        self.assertGreater(font.descender(), 0)


class SoundTests(unittest.TestCase):
    def test_interface_sounds_play_on_effect_channels_at_their_volume(self):
        mixer = drawing.Mixer()
        sound = mixer.Sound(file=BytesIO(b'authored wave'))
        sound.set_volume(.5)
        channel = sound.play()
        self.assertIs(channel.get_sound(), sound)
        self.assertEqual((sound.get_num_channels(), mixer.get_num_channels()), (1, 1))
        self.assertIs(mixer.Channel(0), channel)
        kinds = [(command['kind'], command.get('volume')) for command in mixer.commands]
        self.assertEqual(kinds, [('music_load', None), ('music_volume', .5), ('music_play', None)])
        sound.stop()
        self.assertEqual((sound.get_num_channels(), mixer.get_num_channels()), (0, 0))


if __name__ == '__main__':
    unittest.main()
