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

from . import graphics as pygame

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
            image = pygame.transform.smoothscale(image, size)
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


def _solve(matrix, values):
    """Gauss-Jordan on a small dense system."""
    n = len(values)
    rows = [row[:] + [value] for row, value in zip(matrix, values)]
    for column in range(n):
        pivot = max(range(column, n), key=lambda r: abs(rows[r][column]))
        if abs(rows[pivot][column]) < 1e-12:
            return None
        rows[column], rows[pivot] = rows[pivot], rows[column]
        scale = rows[column][column]
        rows[column] = [v / scale for v in rows[column]]
        for r in range(n):
            if r != column and rows[r][column]:
                factor = rows[r][column]
                rows[r] = [a - factor * b for a, b in zip(rows[r], rows[column])]
    return [row[n] for row in rows]


def perspective_coefficients(quad, size):
    """PIL PERSPECTIVE coefficients mapping each output pixel to the source pixel
    of a `size` image whose corners (TL, TR, BR, BL) land on `quad`."""
    width, height = size
    matrix, values = [], []
    for (x, y), (u, v) in zip(quad, ((0, 0), (width, 0), (width, height), (0, height))):
        matrix.append([x, y, 1, 0, 0, 0, -x * u, -y * u])
        values.append(u)
        matrix.append([0, 0, 0, x, y, 1, -x * v, -y * v])
        values.append(v)
    return _solve(matrix, values)


def to_pil(surface):
    return Image.frombytes('RGBA', surface.get_size(), pygame.image.tobytes(surface, 'RGBA'))


def draw_quad(canvas, source, quad, alpha=1.):
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
    warped = source.transform((width, height), Image.Transform.PERSPECTIVE, coefficients,
                              Image.Resampling.BILINEAR)
    surface = pygame.image.frombytes(warped.tobytes(), (width, height), 'RGBA').convert_alpha()
    if alpha < 1:
        surface = faded(surface, round(255 * max(0., alpha)))
    canvas.blit(surface, (left, top))
