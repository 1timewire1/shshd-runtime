"""HD's GL sprite atlases and bitmap image fonts (the minigames' art).

The iOS HD minigames draw through `CSGLMasterImage`: a sprite atlas (the same
container `atlas.SpriteAtlas` reads) whose negative frame ids are composites of
signed part references. Two placement rules matter (`renderCutupInternal`,
`CSMasterImage::getCenterX`):

- with the "origin" flag a composite is placed by its own origin (its part
  offsets are used as stored);
- without it the composite's bounding box is placed by its top-left corner
  (`getCenterX(ref) == -left extent` is added first).

`renderCutupEx` then translates to (x + pivot), rotates, scales and draws the
image at (-pivot), so rotation and scale turn about the pivot. Positive angles
turn clockwise on screen (the flip transform makes GL's counter-clockwise
clockwise), as `desktop_football` already applies them.
"""
from dataclasses import dataclass
from functools import lru_cache
import math

import pygame

from PIL import Image

from .graphics import faded
from .atlas import AtlasFont, SpriteAtlas
from .ui_assets import Raster


class GLAtlas:
    def __init__(self, data):
        self.atlas = SpriteAtlas.parse(data)
        self._sheet = pygame.image.frombytes(self.atlas.image.pixels,
                                             (self.atlas.image.width, self.atlas.image.height),
                                             'RGBA').convert_alpha()

    @lru_cache(maxsize=None)
    def frame(self, index):
        """A positive frame's own surface."""
        f = self.atlas.frames[index]
        surface = self._sheet.subsurface((f.x, f.y, f.stored_width, f.stored_height)).copy()
        if (f.stored_width, f.stored_height) != (f.width, f.height):
            surface = pygame.transform.smoothscale(surface, (f.width, f.height))
        return surface

    @lru_cache(maxsize=None)
    def bounds(self, ref):
        """(left, top, right, bottom) of a frame or composite, exclusive."""
        if ref >= 0:
            f = self.atlas.frames[ref]
            return 0, 0, f.width, f.height
        boxes = [(dx, dy, dx + self.atlas.frames[r].width, dy + self.atlas.frames[r].height)
                 for r, dx, dy in self.atlas.literals(ref)]
        return (min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes))

    def size(self, ref):
        left, top, right, bottom = self.bounds(ref)
        return right - left, bottom - top

    @lru_cache(maxsize=None)
    def image(self, ref):
        """The frame or composite as one surface (its bounds' top-left at 0, 0)."""
        if ref >= 0:
            return self.frame(ref)
        left, top, right, bottom = self.bounds(ref)
        surface = pygame.Surface((right - left, bottom - top), pygame.SRCALPHA).convert_alpha()
        for r, dx, dy in self.atlas.literals(ref):
            surface.blit(self.frame(r), (dx - left, dy - top))
        return surface

    @lru_cache(maxsize=32)
    def scaled(self, ref, flip, size):
        """The frame or composite at `size`: most are drawn at one size frame after frame, a spinning haze or ring for one."""
        image = self.image(ref)
        return pygame.transform.smoothscale(pygame.transform.flip(image, True, False) if flip else image, size)

    def draw(self, canvas, ref, x, y, *, origin=False, alpha=1., sx=1., sy=None, angle=0.,
             pivot=(0, 0), flip=False):
        """`renderCutupEx`: the frame's image placed at (x, y) (its top-left, or its
        composite origin when `origin`), scaled by (sx, sy) and rotated by `angle`
        degrees about `pivot` (measured from that same point)."""
        sy = sx if sy is None else sy
        if alpha <= 0 or sx == 0 or sy == 0:
            return
        image = self.image(ref)
        left, top, _, _ = self.bounds(ref)
        if origin:
            x, y = x + left, y + top
            pivot = pivot[0] - left, pivot[1] - top
        if flip:
            image = pygame.transform.flip(image, True, False)
        px, py = x + pivot[0], y + pivot[1]
        if sx != 1 or sy != 1:
            size = max(1, round(image.get_width() * abs(sx))), max(1, round(image.get_height() * abs(sy)))
            image = self.scaled(ref, flip, size)
        w, h = image.get_size()
        # The scaled image's center, relative to the pivot.
        cx, cy = -pivot[0] * abs(sx) + w / 2, -pivot[1] * abs(sy) + h / 2
        if angle:
            a = math.radians(angle)
            cx, cy = cx * math.cos(a) - cy * math.sin(a), cx * math.sin(a) + cy * math.cos(a)
            image = pygame.transform.rotate(image, -angle)
        if alpha < 1:
            image = image.copy()
            image = faded(image, round(255 * min(1., alpha)))
        if angle:
            canvas.blit(image, image.get_rect(center=(round(px + cx), round(py + cy))))
        else:
            # Placed by its top-left corner so odd sizes never drift a pixel (tiled strips).
            canvas.blit(image, (round(px + cx - w / 2), round(py + cy - h / 2)))


@dataclass
class ImageFont:
    """A `CSImageFont`: an atlas sheet with CS glyph metrics."""
    font: AtlasFont
    sheet: pygame.Surface

    @classmethod
    def load(cls, sheet_data, metrics_data):
        atlas = SpriteAtlas.parse(sheet_data)
        raster = atlas.image
        f = atlas.frames[0]
        sheet = pygame.image.frombytes(raster.pixels, (raster.width, raster.height), 'RGBA').convert_alpha()
        sheet = sheet.subsurface((f.x, f.y, f.stored_width, f.stored_height)).copy()
        return cls(AtlasFont.parse(metrics_data, Raster(sheet.get_width(), sheet.get_height(),
                                                        pygame.image.tobytes(sheet, 'RGBA'))), sheet)

    @property
    def height(self):
        return self.font.height

    def width(self, text, monospace=None):
        return self.font.width(text, monospace)

    def wrap(self, text, width):
        return self.font.wrap(text, width)

    def text_height(self, lines):
        return self.font.text_height(lines)

    def draw_line(self, canvas, text, x, y, alpha=1., monospace=None):
        """One line; `monospace` is a character whose advance every glyph shares
        (`CSFont::setMonospace`), each glyph drawn from the left of its cell."""
        for char in text:
            glyph = self.font.glyph(char)
            if glyph is not None and char != ' ':
                gx, gy, gw = glyph
                piece = self.sheet.subsurface((gx, gy, gw, self.font.height))
                if alpha < 1:
                    piece = piece.copy()
                    piece = faded(piece, round(255 * alpha))
                canvas.blit(piece, (round(x), round(y)))
            x += self.font.char_width(char, monospace) + self.font.tracking


def perspective_coefficients(quad, size):
    """PIL PERSPECTIVE coefficients mapping each output pixel to the source pixel of a `size` image whose corners (TL, TR, BR, BL)
    land on `quad`, or None for a quad with no area. In closed form (Heckbert's square-to-quad, inverted): every cube face asks for
    these, and solving the eight equations in Python was a quarter of its cost."""
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = quad
    dx1, dx2, sx = x1 - x2, x3 - x2, x0 - x1 + x2 - x3
    dy1, dy2, sy = y1 - y2, y3 - y2, y0 - y1 + y2 - y3
    den = dx1 * dy2 - dx2 * dy1
    if abs(den) < 1e-12:
        return None
    g, h = (sx * dy2 - dx2 * sy) / den, (dx1 * sy - sx * dy1) / den
    a, b, d, e = x1 - x0 + g * x1, x3 - x0 + h * x3, y1 - y0 + g * y1, y3 - y0 + h * y3
    last = a * e - b * d
    if abs(last) < 1e-12:
        return None
    width, height = size[0] / last, size[1] / last
    return ((e - y0 * h) * width, (x0 * h - b) * width, (b * y0 - x0 * e) * width,
            (y0 * g - d) * height, (a - x0 * g) * height, (x0 * d - a * y0) * height,
            (d * h - e * g) / last, (b * g - a * h) / last)


def to_pil(surface):
    return Image.frombytes('RGBA', surface.get_size(), pygame.image.tobytes(surface, 'RGBA'))


def draw_quad(canvas, source, quad, alpha=1., resample=Image.Resampling.BILINEAR):
    """`source` (a PIL RGBA image) projected onto the screen quad (TL, TR, BR, BL),
    perspective-correct, as the GL cube faces are."""
    xs, ys = [p[0] for p in quad], [p[1] for p in quad]
    left, top = math.floor(min(xs)), math.floor(min(ys))
    right, bottom = math.ceil(max(xs)), math.ceil(max(ys))
    width, height = right - left, bottom - top
    if width <= 0 or height <= 0 or width > 4000 or height > 4000:
        return
    local = [(x - left, y - top) for x, y in quad]
    coefficients = perspective_coefficients(local, source.size)
    if coefficients is None:
        return
    warped = source.transform((width, height), Image.Transform.PERSPECTIVE, coefficients, resample)
    surface = pygame.image.frombytes(warped.tobytes(), (width, height), 'RGBA').convert_alpha()
    if alpha < 1:
        surface = faded(surface, round(255 * max(0., alpha)))
    canvas.blit(surface, (left, top))
