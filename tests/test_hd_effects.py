"""HD pictures recreated to match a standard picture (hd_effects): authored pictures only."""
from io import BytesIO
import unittest

from PIL import Image, ImageEnhance

from exp_runtime.hd_effects import apply, motion, recreate


def scene(size):
    """A colourful picture with structure."""
    width, height = size
    image = Image.new('RGB', size)
    image.putdata([((x * 7) % 256, (y * 5) % 256, ((x + y) * 3) % 256) for y in range(height) for x in range(width)])
    return image


def mean_difference(a, b):
    a, b = a.convert('RGB'), b.convert('RGB').resize(a.size)
    total = sum(abs(p - q) for pa, pb in zip(a.getdata(), b.getdata()) for p, q in zip(pa, pb))
    return total / (a.width * a.height * 3)


class EffectTests(unittest.TestCase):
    def setUp(self):
        self.hd = scene((96, 144))
        self.small = self.hd.resize((48, 72), Image.LANCZOS)

    def test_E_gives_a_grey_picture_close_to_the_greyscale_standard_one(self):
        standard = ImageEnhance.Color(self.small).enhance(0)
        out = recreate(standard, self.hd, ('E',))
        self.assertEqual(out.size, self.hd.size)
        self.assertTrue(all(max(pixel) - min(pixel) <= 2 for pixel in out.getdata()))
        self.assertLess(mean_difference(standard, out), 12)

    def test_the_colour_form_follows_a_tinted_standard_picture(self):
        r, g, b = self.small.split()
        blue = Image.merge('RGB', (r.point(lambda v: v // 4), g.point(lambda v: v // 3), b))
        out = recreate(blue, self.hd, ('Ecolour',))
        self.assertLess(mean_difference(blue, out), 14)
        red, green, blue_channel = (sum(band.getdata()) for band in out.split())
        self.assertGreater(blue_channel, red)

    def test_F_colours_a_grey_picture_by_the_standard_pictures_tint(self):
        grey = ImageEnhance.Color(self.small).enhance(0).convert('L')
        green = Image.merge('RGB', (grey.point(lambda v: v // 3), grey, grey.point(lambda v: v // 3)))
        out = recreate(green, self.hd, ('F',))
        red, green_channel, blue = (sum(band.getdata()) for band in out.split())
        self.assertGreater(green_channel, 2 * red)
        self.assertLess(mean_difference(green, out), 14)

    def test_a_motion_blur_is_horizontal_and_centred(self):
        line = Image.new('RGB', (32, 4))
        line.putpixel((16, 1), (255, 255, 255))
        blurred = motion(line, 8)
        lit = [x for x in range(32) if blurred.getpixel((x, 1))[0] > 0]
        self.assertEqual(len(lit), 8)
        self.assertLessEqual(abs(sum(lit) / len(lit) - 16), 1)
        self.assertEqual(blurred.getpixel((16, 0)), (0, 0, 0))

    def test_mirror_keeps_a_portraits_transparency(self):
        portrait = Image.new('RGBA', (8, 8), (0, 0, 0, 0))
        portrait.putpixel((1, 2), (200, 10, 10, 255))
        stream = BytesIO()
        portrait.save(stream, 'PNG')
        out = Image.open(BytesIO(apply(stream.getvalue(), stream.getvalue(), ('MIRROR',))))
        self.assertEqual(out.mode, 'RGBA')
        self.assertEqual(out.getpixel((6, 2)), (200, 10, 10, 255))
        self.assertEqual(out.getpixel((1, 2))[3], 0)

    def test_no_effect_keeps_the_hd_bytes_and_an_unknown_one_is_refused(self):
        self.assertIs(apply(b'sd', b'hd', None), b'hd')
        with self.assertRaises(ValueError):
            recreate(self.small, self.hd, ('sepia',))


if __name__ == '__main__':
    unittest.main()
