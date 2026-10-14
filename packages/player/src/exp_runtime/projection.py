"""Perspective texture mapping shared by software and native drawing hosts."""
from functools import lru_cache
import math


def inverse_quad(points):
    """Map a convex screen quad to the unit texture square (TL/TR/BR/BL)."""
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = points
    dx1, dx2, dx3 = x1 - x2, x3 - x2, x0 - x1 + x2 - x3
    dy1, dy2, dy3 = y1 - y2, y3 - y2, y0 - y1 + y2 - y3
    denominator = dx1 * dy2 - dx2 * dy1
    if abs(denominator) < 1e-9:
        return None
    g = (dx3 * dy2 - dx2 * dy3) / denominator
    h = (dx1 * dy3 - dx3 * dy1) / denominator
    a, b, c = x1 - x0 + g * x1, x3 - x0 + h * x3, x0
    d, e, f = y1 - y0 + g * y1, y3 - y0 + h * y3, y0
    k = a * e - b * d
    if abs(k) < 1e-9:
        return None
    return tuple(v / k for v in (e - f*h, c*h - b, b*f - c*e,
                                 f*g - d, a - c*g, c*d - a*f, d*h - e*g, b*g - a*h))


def local_map(coefficients, x, y):
    a, b, c, d, e, f, g, h = coefficients
    k = g*x + h*y + 1
    return tuple(v / k for v in (a, b, a*x + b*y + c, d, e, d*x + e*y + f, g, h))


def warp(source, size, coefficients):
    from PIL import Image
    factors = (source.width,) * 3 + (source.height,) * 3 + (1, 1)
    return source.transform(size, Image.Transform.PERSPECTIVE,
                            tuple(v * scale for v, scale in zip(coefficients, factors)),
                            Image.Resampling.BILINEAR)


@lru_cache(maxsize=256)
def _desktop_texture(image):
    # Grid face images are immutable cached assets; only their transforms move.
    from PIL import Image
    from . import graphics
    return Image.frombytes('RGBA', image.get_size(), graphics.image.tobytes(image, 'RGBA'))


def draw_quad(target, image, points):
    from . import graphics
    coefficients = inverse_quad(points)
    if coefficients is None:
        return
    clip = target.get_clip()
    left = max(clip.left, math.floor(min(p[0] for p in points)))
    top = max(clip.top, math.floor(min(p[1] for p in points)))
    right = min(clip.right, math.ceil(max(p[0] for p in points)))
    bottom = min(clip.bottom, math.ceil(max(p[1] for p in points)))
    if right <= left or bottom <= top:
        return
    coefficients = local_map(coefficients, left, top)
    bounds = left, top, right - left, bottom - top
    native = getattr(graphics.draw, 'textured_quad', None)
    if native is not None:
        native(target, image, bounds, coefficients)
    else:
        pixels = warp(_desktop_texture(image), bounds[2:], coefficients)
        layer = graphics.image.frombytes(pixels.tobytes(), pixels.size, 'RGBA')
        layer.set_alpha(image.get_alpha())
        target.blit(layer, (left, top))
