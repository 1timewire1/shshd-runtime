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


def depth_plane(points):
    """Reciprocal camera distance is affine in projected screen coordinates."""
    (x, y, z), (x1, y1, z1), (x2, y2, z2) = points[:3]
    dx1, dy1, dx2, dy2 = x1 - x, y1 - y, x2 - x, y2 - y
    divisor = dx1 * dy2 - dx2 * dy1
    if abs(divisor) < 1e-9:
        return None
    a = ((-1 / z1 + 1 / z) * dy2 - (-1 / z2 + 1 / z) * dy1) / divisor
    b = (dx1 * (-1 / z2 + 1 / z) - dx2 * (-1 / z1 + 1 / z)) / divisor
    return a, b, -1 / z - a * x - b * y


def depth_mask(image, coefficients, plane, bounds, depth, viewport):
    """GL_LEQUAL on a shared depth buffer; transparent texels still write depth."""
    left, top, width, height = bounds
    a, b, c = plane
    values = bytearray(image.tobytes())
    u0, u1, u2, v0, v1, v2, d0, d1 = coefficients
    for y in range(height):
        fy = y + .5
        for x in range(width):
            fx = x + .5
            divisor = d0 * fx + d1 * fy + 1
            if abs(divisor) < 1e-12:
                values[(y * width + x) * 4:(y * width + x + 1) * 4] = bytes(4)
                continue
            u, v = (u0 * fx + u1 * fy + u2) / divisor, (v0 * fx + v1 * fy + v2) / divisor
            index = (top + y) * viewport[0] + left + x
            distance = a * (left + fx) + b * (top + fy) + c
            if 0 <= u < 1 and 0 <= v < 1 and distance >= depth[index]:
                depth[index] = distance
            else:
                offset = (y * width + x) * 4
                values[offset:offset + 4] = bytes(4)
    from PIL import Image
    return Image.frombytes('RGBA', image.size, bytes(values))


def draw_depth_quads(target, faces):
    """One native depth-tested batch; camera/face construction stays shared."""
    from . import graphics
    layer = graphics.Surface(target.get_size(), graphics.SRCALPHA)
    layer.set_clip(target.get_clip())
    depth = [0.] * (target.get_width() * target.get_height())
    for image, points in faces:
        plane = depth_plane(points)
        if plane is not None:
            draw_quad(layer, image, tuple(p[:2] for p in points), depth=depth, plane=plane)
    target.blit(layer, (0, 0))


@lru_cache(maxsize=256)
def _desktop_texture(image):
    # Grid face images are immutable cached assets; only their transforms move.
    from PIL import Image
    from . import graphics
    return Image.frombytes('RGBA', image.get_size(), graphics.image.tobytes(image, 'RGBA'))


def draw_quad(target, image, points, *, depth=None, plane=None):
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
        if plane is None:
            native(target, image, bounds, coefficients)
        else:
            graphics.draw.depth_quad(target, image, bounds, coefficients, plane)
    else:
        pixels = warp(_desktop_texture(image), bounds[2:], coefficients)
        if plane is not None:
            pixels = depth_mask(pixels, coefficients, plane, bounds, depth, target.get_size())
        layer = graphics.image.frombytes(pixels.tobytes(), pixels.size, 'RGBA')
        layer = graphics.faded(layer, image.get_alpha())
        target.blit(layer, (left, top))
