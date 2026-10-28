"""Retained drawing commands for native hosts, using the shared renderer API.

Only the primitives used by our presentation code are implemented. This is not
an SDL emulator. Immutable snapshots keep cached layers and fades independent
of later writes. Native hosts rasterize commands; Pillow decodes source images
and performs the small, byte-exact asset operations used by masks and atlases.
"""
import base64
from dataclasses import dataclass, field
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
from itertools import count
import math
import os
import struct
from types import SimpleNamespace

from PIL import Image, ImageChops, ImageDraw


class DrawingError(ValueError):
    pass


class Rect:
    cast = int

    def __init__(self, *values):
        if len(values) == 1:
            values = tuple(values[0])
        if len(values) == 2:
            values = (*values[0], *values[1])
        if len(values) != 4:
            raise TypeError('Rectangle requires x, y, width, height')
        self.x, self.y, self.width, self.height = map(self.cast, values)

    def __setattr__(self, key, value):
        object.__setattr__(self, key, self.cast(value) if key in ('x', 'y', 'width', 'height') else value)

    def __iter__(self):
        return iter((self.x, self.y, self.width, self.height))

    def __getitem__(self, index):
        return tuple(self)[index]

    def __eq__(self, other):
        return tuple(self) == tuple(other)

    # pygame's positional attributes, readable and settable (setting one moves the rectangle; `size` resizes it).
    def _half(self, length):
        return length // 2 if self.cast is int else length / 2

    size = property(lambda self: (self.width, self.height),
                    lambda self, value: self._set(width=value[0], height=value[1]))
    w = property(lambda self: self.width, lambda self, value: self._set(width=value))
    h = property(lambda self: self.height, lambda self, value: self._set(height=value))
    left = property(lambda self: self.x, lambda self, value: self._set(x=value))
    top = property(lambda self: self.y, lambda self, value: self._set(y=value))
    right = property(lambda self: self.x + self.width, lambda self, value: self._set(x=self.cast(value) - self.width))
    bottom = property(lambda self: self.y + self.height,
                      lambda self, value: self._set(y=self.cast(value) - self.height))
    centerx = property(lambda self: self.x + self._half(self.width),
                       lambda self, value: self._set(x=self.cast(value) - self._half(self.width)))
    centery = property(lambda self: self.y + self._half(self.height),
                       lambda self, value: self._set(y=self.cast(value) - self._half(self.height)))

    def _set(self, **values):
        for key, value in values.items():
            object.__setattr__(self, key, self.cast(value))

    def _pair(horizontal, vertical):
        return property(lambda self: (getattr(self, horizontal), getattr(self, vertical)),
                        lambda self, point: (setattr(self, horizontal, point[0]), setattr(self, vertical, point[1])))

    topleft, topright = _pair('left', 'top'), _pair('right', 'top')
    bottomleft, bottomright = _pair('left', 'bottom'), _pair('right', 'bottom')
    midtop, midbottom = _pair('centerx', 'top'), _pair('centerx', 'bottom')
    midleft, midright = _pair('left', 'centery'), _pair('right', 'centery')
    center = _pair('centerx', 'centery')
    del _pair

    def clip(self, other):
        other = type(self)(other)
        x, y = max(self.x, other.x), max(self.y, other.y)
        w, h = min(self.right, other.right) - x, min(self.bottom, other.bottom) - y
        return type(self)(x, y, w, h) if w > 0 and h > 0 else type(self)(self.x, self.y, 0, 0)

    def inflate(self, x, y):
        x, y = self.cast(x), self.cast(y)
        return type(self)(self.x - self.cast(x / 2), self.y - self.cast(y / 2), self.width + x, self.height + y)

    def inflate_ip(self, x, y):
        self.x, self.y, self.width, self.height = self.inflate(x, y)

    def move(self, x, y=None):
        if y is None:
            x, y = x
        return type(self)(self.x + self.cast(x), self.y + self.cast(y), self.width, self.height)

    def move_ip(self, x, y=None):
        self.x, self.y = self.move(x, y).topleft

    def union(self, other):
        return self.unionall([other])

    def contains(self, other):
        other = type(self)(other)
        return (self.x <= other.x and self.y <= other.y and other.right <= self.right
                and other.bottom <= self.bottom)

    def __len__(self):
        return 4

    def __repr__(self):
        return f'<{type(self).__name__}({self.x}, {self.y}, {self.width}, {self.height})>'

    def unionall(self, rectangles):
        rectangles = [self, *(type(self)(rect) for rect in rectangles)]
        x, y = min(rect.x for rect in rectangles), min(rect.y for rect in rectangles)
        right, bottom = max(rect.right for rect in rectangles), max(rect.bottom for rect in rectangles)
        return type(self)(x, y, right - x, bottom - y)

    def copy(self):
        return type(self)(self)

    def collidepoint(self, *point):
        x, y = point[0] if len(point) == 1 else point
        return self.x <= x < self.right and self.y <= y < self.bottom

    def colliderect(self, other):
        other = type(self)(other)
        return self.x < other.right and self.right > other.x and self.y < other.bottom and self.bottom > other.y


class FRect(Rect):
    cast = float


_ids = count(1)
SRCALPHA, BLEND_RGBA_MULT, RESIZABLE = 1, 2, 4
# The other blends the HD and CoD screens use (values private to this backend, as pygame's are to it).
BLEND_RGBA_MIN, BLEND_RGBA_MAX, BLEND_RGB_ADD, BLEND_RGB_MULT = 8, 16, 32, 64
BLENDS = (BLEND_RGBA_MULT, BLEND_RGBA_MIN, BLEND_RGBA_MAX, BLEND_RGB_ADD, BLEND_RGB_MULT)


def rgba(color):
    return tuple(color) if len(color) == 4 else (*color, 255)


def _multiply(a, b):
    # SDL's multiply is (a*b + 255) >> 8.
    return Image.frombytes(a.mode, a.size, bytes((x * y + 255) >> 8 for x, y in zip(a.tobytes(), b.tobytes())))


def blend(destination, source, flags):
    """SDL's `special_flags` blend of two same-sized RGBA images: the RGBA ones on every channel, the RGB ones on
    colour only (the destination keeps its alpha)."""
    if flags == BLEND_RGBA_MULT:
        return _multiply(destination, source)
    if flags == BLEND_RGBA_MIN:
        return ImageChops.darker(destination, source)
    if flags == BLEND_RGBA_MAX:
        return ImageChops.lighter(destination, source)
    rgb = (_multiply(destination.convert('RGB'), source.convert('RGB')) if flags == BLEND_RGB_MULT
           else ImageChops.add(destination.convert('RGB'), source.convert('RGB')))
    rgb.putalpha(destination.getchannel('A'))
    return rgb


@dataclass(eq=False)
class Node:
    size: tuple
    ops: tuple = ()
    pixels: Image.Image | None = None
    identifier: int = field(default_factory=lambda: next(_ids))
    encoded: str | None = None
    # Pieces of these pixels read through a subsurface, by box: one node (one PNG for the host) each, however often
    # it is read (a font sheet's glyphs, every frame of a title card).
    crops: dict = field(default_factory=dict, repr=False)

    def record(self):
        record = dict(id=self.identifier, size=self.size)
        if self.pixels is not None:
            if self.encoded is None:
                stream = BytesIO()
                self.pixels.save(stream, 'PNG')
                self.encoded = base64.b64encode(stream.getvalue()).decode('ascii')
            record['png'] = self.encoded
        else:
            record['ops'] = [dict(op, source=op['source'].identifier) if 'source' in op else op for op in self.ops]
        return record


class Surface:
    def __init__(self, size, flags=0):
        self._size = tuple(map(int, size))
        if len(self._size) != 2 or min(self._size) < 0:
            raise DrawingError('Invalid surface dimensions')
        self._alpha = 255
        self._clip = Rect(0, 0, *self._size)
        self._ops = []
        self._node = None
        self.opaque = not bool(flags & SRCALPHA)
        self.fill((0, 0, 0, 255 if self.opaque else 0))

    @classmethod
    def from_pixels(cls, pixels):
        result = cls(pixels.size, SRCALPHA)
        result._ops = []
        result._node = Node(pixels.size, pixels=pixels.convert('RGBA'))
        result.opaque = result._node.pixels.getextrema()[3] == (255, 255)
        return result

    @classmethod
    def from_node(cls, node):
        result = cls(node.size, SRCALPHA)
        result._ops, result._node = [], node
        return result

    def snapshot(self):
        if self._node is None:
            self._node = Node(self._size, tuple(self._ops))
        return self._node

    def _append(self, op):
        if not self._ops and self._node is not None:
            self._ops = [dict(kind='blit', source=self._node, at=(0, 0), alpha=255,
                              clip=(0, 0, *self._size))]
        self._node = None
        self._ops.append(dict(op, clip=tuple(self._clip)))

    def get_size(self):
        return self._size

    def get_width(self):
        return self._size[0]

    def get_height(self):
        return self._size[1]

    def get_rect(self, **keywords):
        rect = Rect(0, 0, *self._size)
        for key, value in keywords.items():
            setattr(rect, key, value)
        return rect

    def copy(self):
        result = self.from_node(self.snapshot())
        result._alpha, result.opaque = self._alpha, self.opaque
        result._clip = Rect(self._clip)
        return result

    def convert(self, depth=32):
        return self

    def convert_alpha(self):
        return self

    def set_alpha(self, alpha):
        self._alpha = 255 if alpha is None else max(0, min(255, int(alpha)))

    def set_clip(self, rect=None):
        self._clip = self.get_rect() if rect is None else self.get_rect().clip(rect)

    def get_clip(self):
        return Rect(self._clip)

    def fill(self, color, rect=None, special_flags=0):
        region = self._clip if rect is None else self._clip.clip(rect)
        if region.width <= 0 or region.height <= 0:
            return region
        if special_flags:
            if special_flags == BLEND_RGB_MULT and self.opaque:
                # An opaque surface's darkening (the HD menus' fades, every frame over the whole canvas): drawn by the
                # host with its multiply blend, as SDL's RGB multiply leaves opaque pixels opaque.
                self._append(dict(kind='fill', color=rgba(color)[:3] + (255,), rect=tuple(region), blend='multiply'))
                return region
            if special_flags == BLEND_RGBA_MULT and rgba(color)[:3] == (255, 255, 255) and region == self.get_rect():
                # graphics.faded's whole-surface fade (the HD screens' text and buttons, each frame of a fade): SDL's
                # multiply by white keeps the colour and scales the alpha, so the host's own alpha on a blit of what
                # is there draws it, not a Python multiply.
                node, alpha = self.snapshot(), rgba(color)[3]
                self._ops, self._node = [], None
                self._append(dict(kind='blit', source=node, at=(0, 0), alpha=alpha))
                self.opaque = self.opaque and alpha == 255
                return region
            solid = Image.new('RGBA', region.size, rgba(color))
            self._blend_into(solid, region.topleft, special_flags, 'fill')
        else:
            if region == self.get_rect():
                self._ops, self._node = [], None
                self.opaque = rgba(color)[3] == 255
            self._append(dict(kind='fill', color=rgba(color), rect=tuple(region)))
        return region

    def blit(self, source, destination, area=None, special_flags=0):
        if area is not None:
            source = source.subsurface(area)
        x, y = tuple(destination)[:2]
        at = int(x), int(y)
        bounds = Rect(*at, *source.get_size()).clip(self._clip)
        if special_flags:
            if special_flags == BLEND_RGB_ADD and self.opaque and source.opaque:
                # Opaque over opaque (the episode loading screen's art fading in over black, every frame): drawn by the
                # host with its additive blend.
                if bounds.width > 0 and bounds.height > 0:
                    self._append(dict(kind='blit', source=source.snapshot(), at=at, alpha=source._alpha, blend='add'))
                return bounds
            self._blend_into(raster(source.snapshot()), at, special_flags, 'image')
        elif bounds.width > 0 and bounds.height > 0:
            node = source.snapshot()
            if source.opaque and source._alpha == 255 and bounds == self.get_rect():
                self._ops, self._node = [], None
                self.opaque = True
            self._append(dict(kind='blit', source=node, at=at, alpha=source._alpha))
        return bounds

    def _blend_into(self, source, at, flags, what):
        """SDL's blend of the PIL image `source` placed at `at` into this surface, computed exactly here (masks and
        small pieces: the timer and picker masks, the choice shadows, the switches' pill), within the clip."""
        region = Rect(*at, *source.size).clip(self._clip)
        if region.width <= 0 or region.height <= 0:
            return
        if flags not in BLENDS:
            raise DrawingError(f'Unsupported {what} blend')
        pixels = raster(self.snapshot())
        box = (region.x, region.y, region.right, region.bottom)
        piece = source.crop((region.x - at[0], region.y - at[1], region.right - at[0], region.bottom - at[1]))
        pixels.paste(blend(pixels.crop(box), piece, flags), box)
        self._ops, self._node = [], Node(self._size, pixels=pixels)
        self.opaque = pixels.getextrema()[3] == (255, 255)

    def get_bounding_rect(self, min_alpha=1):
        """pygame's: the smallest rectangle holding every pixel whose alpha is at least `min_alpha` (the HD screens
        place text by its ink)."""
        alpha = raster(self.snapshot()).getchannel('A').point(lambda a: 255 if a >= min_alpha else 0)
        box = alpha.getbbox()
        return Rect(0, 0, 0, 0) if box is None else Rect(box[0], box[1], box[2] - box[0], box[3] - box[1])

    def subsurface(self, rect):
        rect = Rect(rect)
        if rect.x < 0 or rect.y < 0 or rect.right > self.get_width() or rect.bottom > self.get_height():
            raise DrawingError('Subsurface lies outside its source')
        return SurfaceView(self, rect)


def _translated(op, dx, dy):
    """`op` (a drawing command) moved by (dx, dy)."""
    op = dict(op)
    if op['kind'] in ('textured_quad', 'depth_quad', 'textured_rows') and (dx or dy):
        raise DrawingError(f"Unsupported operation on a subsurface: {op['kind']}")
    if 'rect' in op:
        op['rect'] = tuple(Rect(op['rect']).move(dx, dy))
    if 'at' in op:
        op['at'] = (op['at'][0] + dx, op['at'][1] + dy)
    if 'points' in op:
        op['points'] = tuple((x + dx, y + dy) for x, y in op['points'])
    if 'center' in op:
        op['center'] = (op['center'][0] + dx, op['center'][1] + dy)
    return op


class SurfaceView(Surface):
    """pygame's subsurface: a window onto `parent` that draws into it, clipped to itself (the HD dialogue and choice
    renderers draw their 320-unit column into the frame-wide layer through one). Reading it (a blit from it, `copy`)
    takes the parent's pixels as they are then."""
    def __init__(self, parent, rect):
        self._parent, self._offset, self._size = parent, (rect.x, rect.y), rect.size
        self._alpha = 255
        self._clip = Rect(0, 0, *self._size)
        self.opaque = False

    def _on_parent(self, call):
        parent, saved = self._parent, self._parent._clip
        parent._clip = self._clip.move(*self._offset)
        try:
            return call(parent)
        finally:
            parent._clip = saved

    def _append(self, op):
        self._on_parent(lambda parent: parent._append(_translated(op, *self._offset)))

    def fill(self, color, rect=None, special_flags=0):
        rect = self.get_rect() if rect is None else Rect(rect)
        region = self._on_parent(lambda parent: parent.fill(color, rect.move(*self._offset), special_flags))
        return region.move(-self._offset[0], -self._offset[1])

    def blit(self, source, destination, area=None, special_flags=0):
        x, y = tuple(destination)[:2]
        at = (x + self._offset[0], y + self._offset[1])
        bounds = self._on_parent(lambda parent: parent.blit(source, at, area, special_flags))
        return bounds.move(-self._offset[0], -self._offset[1])

    def snapshot(self):
        node = self._parent.snapshot()
        (x, y), (w, h) = self._offset, self._size
        if node.pixels is not None:
            box = (x, y, x + w, y + h)
            if box not in node.crops:
                node.crops[box] = Node(self._size, pixels=node.pixels.crop(box))
            return node.crops[box]
        return Node(self._size, (dict(kind='blit', source=node, at=(-x, -y), alpha=255, clip=(0, 0, w, h)),))

    def copy(self):
        result = Surface.from_node(self.snapshot())
        result._alpha = self._alpha
        return result

    def subsurface(self, rect):
        rect = Rect(rect)
        if rect.x < 0 or rect.y < 0 or rect.right > self.get_width() or rect.bottom > self.get_height():
            raise DrawingError('Subsurface lies outside its source')
        return SurfaceView(self._parent, rect.move(*self._offset))


class Draw:
    @staticmethod
    def depth_quad(surface, image, bounds, coefficients, plane):
        surface._append(dict(kind='depth_quad', source=image.snapshot(), alpha=image._alpha,
                             bounds=bounds, coefficients=coefficients, depth_plane=plane))

    @staticmethod
    def textured_quad(surface, image, bounds, coefficients):
        surface._append(dict(kind='textured_quad', source=image.snapshot(), alpha=image._alpha,
                             bounds=bounds, coefficients=coefficients))

    @staticmethod
    def textured_rows(surface, image, top, rows):
        surface._append(dict(kind='textured_rows', source=image.snapshot(),
                             alpha=image._alpha, top=top, rows=tuple(rows)))

    @staticmethod
    def rect(surface, color, rect, width=0, border_radius=0):
        surface._append(dict(kind='rect', color=rgba(color), rect=tuple(Rect(rect)),
                             width=width, radius=border_radius))

    @staticmethod
    def line(surface, color, start, end, width=1):
        surface._append(dict(kind='line', color=rgba(color), points=(start, end), width=width))

    @staticmethod
    def polygon(surface, color, points, width=0):
        surface._append(dict(kind='polygon', color=rgba(color), points=tuple(points), width=width))

    @staticmethod
    def circle(surface, color, center, radius, width=0):
        surface._append(dict(kind='circle', color=rgba(color), center=center, radius=radius, width=width))

    @staticmethod
    def lines(surface, color, closed, points, width=1):
        """A polyline (the Decision Tree panel's branches), on the host's `line` path."""
        points = tuple(tuple(point) for point in points)
        if closed and points:
            points += (points[0],)
        surface._append(dict(kind='line', color=rgba(color), points=points, width=width))

    @classmethod
    def aalines(cls, surface, color, closed, points):
        cls.lines(surface, color, closed, points, 1)

    @staticmethod
    def ellipse(surface, color, rect, width=0):
        surface._append(dict(kind='ellipse', color=rgba(color), rect=tuple(Rect(rect)), width=width))


class Transform:
    @staticmethod
    def color_matrix(surface, matrix):
        return Surface.from_node(Node(surface.get_size(),
            (dict(kind='color_matrix', source=surface.snapshot(), matrix=matrix),)))

    @staticmethod
    def _scale(surface, size, smooth):
        size = tuple(map(int, size))
        node = surface.snapshot()
        if min(surface.get_size()) == 0:
            return Surface(size, SRCALPHA)
        # Keep source pixels stable. Realizing resized sprites here encoded
        # dozens of fresh PNGs per football frame (including four large haze
        # tiles). The native canvas already implements both resampling modes.
        result = Surface.from_node(Node(size, (dict(kind='scale', source=node, smooth=smooth),)))
        result._alpha, result.opaque = surface._alpha, surface.opaque
        return result

    @classmethod
    def scale(cls, surface, size):
        return cls._scale(surface, size, False)

    @classmethod
    def smoothscale(cls, surface, size):
        return cls._scale(surface, size, True)

    @staticmethod
    def flip(surface, horizontal, vertical):
        node = surface.snapshot()
        if node.pixels is not None:
            pixels = node.pixels
            if horizontal:
                pixels = pixels.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            if vertical:
                pixels = pixels.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            result = Surface.from_pixels(pixels)
        else:
            result = Surface.from_node(Node(surface.get_size(), (dict(kind='flip', source=node,
                                                                      horizontal=horizontal, vertical=vertical),)))
        result._alpha, result.opaque = surface._alpha, surface.opaque
        return result

    @staticmethod
    def _rotate(surface, angle, scale, smooth):
        w, h = surface.get_size()
        if smooth:
            # pygame's rotozoom binding accepts C floats before calculating
            # the output bounds. Preserve that rounding at integer edges.
            angle, scale = struct.unpack('ff', struct.pack('ff', angle, scale))
        cosine, sine = abs(math.cos(math.radians(angle))), abs(math.sin(math.radians(angle)))
        if smooth and angle % 360:
            size = (max(1, math.ceil((w // 2 * cosine + h // 2 * sine) * scale)) * 2,
                    max(1, math.ceil((w // 2 * sine + h // 2 * cosine) * scale)) * 2)
        else:
            size = (max(1, int((w * cosine + h * sine) * scale + 1e-9)),
                    max(1, int((w * sine + h * cosine) * scale + 1e-9)))
        result = Surface.from_node(Node(size, (dict(kind='rotate', source=surface.snapshot(),
                                                    angle=angle, scale=scale, smooth=smooth),)))
        result._alpha = surface._alpha
        return result

    @classmethod
    def rotate(cls, surface, angle):
        return cls._rotate(surface, angle, 1, False)

    @classmethod
    def rotozoom(cls, surface, angle, scale):
        return cls._rotate(surface, angle, scale, True)


def raster(node):
    """Realize a small asset mask for the shared portrait/tint algorithms.

    Whole frames are drawn by the native host, not encoded as Python bitmaps.
    This also provides a reference image for protocol tests.
    """
    if node.pixels is not None:
        return node.pixels.copy()
    image = Image.new('RGBA', node.size)
    depth = None
    for op in node.ops:
        kind = op['kind']
        if kind == 'color_matrix':
            from ..color_transform import transform_rgb
            source = raster(op['source']).convert('RGB')
            image = Image.frombytes('RGB', node.size,
                                    transform_rgb(source.tobytes(), op['matrix'])).convert('RGBA')
            continue
        if kind in ('scale', 'rotate', 'flip'):
            source = raster(op['source'])
            if kind == 'scale':
                image = source.resize(node.size, Image.Resampling.BILINEAR if op['smooth'] else Image.Resampling.NEAREST)
            elif kind == 'flip':
                image = source
                if op['horizontal']:
                    image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                if op['vertical']:
                    image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            else:
                scale = op['scale']
                if scale != 1:
                    source = source.resize((max(1, round(source.width * scale)), max(1, round(source.height * scale))))
                rotated = source.rotate(op['angle'], Image.Resampling.BICUBIC if op['smooth'] else Image.Resampling.NEAREST, expand=True)
                image.paste(rotated, ((image.width - rotated.width) // 2, (image.height - rotated.height) // 2))
            continue
        layer = image.copy()
        if op.get('blend'):
            # The host's multiply / additive blends over opaque pixels (Surface.fill / blit), here as SDL's.
            if kind == 'fill':
                x, y, w, h = op['rect']
                piece, at, flags = Image.new('RGBA', (w, h), tuple(op['color'])), (x, y), BLEND_RGB_MULT
            else:
                piece, at, flags = raster(op['source']), tuple(op['at']), BLEND_RGB_ADD
            box = (*at, at[0] + piece.width, at[1] + piece.height)
            layer.paste(blend(layer.crop(box), piece, flags), box)
        elif kind == 'blit':
            source = raster(op['source'])
            if op['alpha'] != 255:
                source.putalpha(source.getchannel('A').point(lambda a: a * op['alpha'] // 255))
            layer.alpha_composite(source, op['at'])
        elif kind in ('textured_quad', 'depth_quad'):
            from ..projection import warp, depth_mask
            x, y, w, h = op['bounds']
            source = warp(raster(op['source']), (w, h), op['coefficients'])
            if kind == 'depth_quad':
                if depth is None:
                    depth = [0.] * (node.size[0] * node.size[1])
                source = depth_mask(source, op['coefficients'], op['depth_plane'], op['bounds'], depth, node.size)
            if op['alpha'] != 255:
                source.putalpha(source.getchannel('A').point(lambda a: a * op['alpha'] // 255))
            layer.alpha_composite(source, (x, y))
        elif kind == 'textured_rows':
            source = raster(op['source'])
            source = source.resize((source.width, len(op['rows'])), Image.Resampling.BILINEAR)
            for y, (left, width) in enumerate(op['rows']):
                row = source.crop((0, y, source.width, y + 1)).resize((width, 1), Image.Resampling.BILINEAR)
                if op['alpha'] != 255:
                    row.putalpha(row.getchannel('A').point(lambda a: a * op['alpha'] // 255))
                layer.alpha_composite(row, (left, op['top'] + y))
        else:
            draw = ImageDraw.Draw(layer)
            color, width = op['color'], op.get('width', 0)
            if kind in ('fill', 'rect'):
                x, y, w, h = op['rect']
                if w > 0 and h > 0:
                    draw.rounded_rectangle((x, y, x + w - 1, y + h - 1), radius=op.get('radius', 0),
                                           fill=None if width else color, outline=color, width=width)
            elif kind == 'line':
                draw.line(op['points'], fill=color, width=width)
            elif kind == 'polygon':
                draw.polygon(op['points'], fill=None if width else color, outline=color, width=width or 1)
            elif kind == 'circle':
                x, y = op['center']
                r = op['radius']
                draw.ellipse((x - r, y - r, x + r - 1, y + r - 1), fill=None if width else color, outline=color, width=width or 1)
            elif kind == 'ellipse':
                x, y, w, h = op['rect']
                if w > 0 and h > 0:
                    draw.ellipse((x, y, x + w - 1, y + h - 1), fill=None if width else color, outline=color,
                                 width=width or 1)
            else:
                raise DrawingError(f'Unsupported drawing operation: {kind}')
        x, y, w, h = op['clip']
        box = x, y, x + w, y + h
        image.paste(layer.crop(box), box)
    return image


class ImageAPI:
    def __init__(self, icon_path):
        self.icon_path = icon_path

    @staticmethod
    def frombytes(data, size, mode):
        return Surface.from_pixels(Image.frombytes(mode, size, data))

    @staticmethod
    def load(source):
        try:
            with Image.open(source) as image:
                return Surface.from_pixels(image.convert('RGBA'))
        except (OSError, ValueError) as error:
            raise DrawingError(str(error)) from error

    @staticmethod
    def tobytes(surface, mode):
        return raster(surface.snapshot()).convert(mode).tobytes()

    @staticmethod
    def save(surface, file, namehint=''):
        """pygame's: the surface written to `file` (a path or a stream) in the format its name or `namehint` gives
        (the episode screenshots and picker thumbnails are JPEG files)."""
        name = (namehint or str(getattr(file, 'name', file))).rsplit('.', 1)[-1].lower()
        image = raster(surface.snapshot())
        if name in ('jpg', 'jpeg'):
            image.convert('RGB').save(file, 'JPEG')
        else:
            image.save(file, 'PNG' if name not in ('bmp', 'tga') else name.upper())

    def load_sized_svg(self, source, size):
        # The build renders the project's authored SVG; no game image is bundled.
        return Transform.smoothscale(self.load(self.icon_path), size)


class FrameEncoder:
    def __init__(self):
        self.previous = set()

    def encode(self, surface):
        nodes, visited = [], set()
        def visit(node):
            if node.identifier in visited:
                return
            visited.add(node.identifier)
            for op in node.ops:
                if 'source' in op:
                    visit(op['source'])
            if node.identifier not in self.previous:
                nodes.append(node.record())
        root = surface.snapshot()
        visit(root)
        released = sorted(self.previous - visited)
        self.previous = visited
        return dict(root=root.identifier, nodes=nodes, release=released)


class PlatformFont:
    """pygame's Font on CoreText: `face` is a PostScript name (a system face, or one `Fonts` registered from a file's
    bytes), None for the system face."""
    def __init__(self, bridge, face, size):
        self.bridge, self.face, self.points = bridge, face, max(1, round(size * .75)) if face is None else size

    @lru_cache(maxsize=512)
    def _measure(self, text):
        return self.bridge(dict(operation='text', face=self.face, size=self.points, text=text, measure=True))

    def size(self, text):
        result = self._measure(text)
        return result['width'], result['height']

    def get_linesize(self):
        return self._measure('Mg')['height']

    get_height = get_linesize

    def get_ascent(self):
        return self._measure('Mg')['ascent']

    def get_descent(self):
        return -self._measure('Mg')['descent']

    def cap_height(self):
        """CoreText's cap height in pixels, unrounded (not pygame's: vector_text reads it for a system face)."""
        return self._measure('Mg')['cap']

    def descender(self):
        """CoreText's descent in pixels, unrounded (as `cap_height`)."""
        return self._measure('Mg')['descender']

    @lru_cache(maxsize=512)
    def _glyphs(self, text):
        return tuple(tuple(values) for values in
                     self.bridge(dict(operation='glyphs', face=self.face, size=self.points, text=text))['glyphs'])

    def metrics(self, text):
        """pygame's: (min x, max x, min y, max y, advance) per character, y up from the baseline."""
        return list(self._glyphs(text))

    @lru_cache(maxsize=128)
    def render(self, text, antialias, color):
        # SDL_ttf starts the image at the first character's leftmost ink; CoreText draws at the pen, so a negative left
        # bearing moves the pen in by as much (vector_text steps back by that bearing, as on desktop).
        left = -min(0, self._glyphs(text[:1])[0][0]) if text else 0
        result = self.bridge(dict(operation='text', face=self.face, size=self.points, text=text, color=rgba(color),
                                  left=left))
        return ImageAPI.load(BytesIO(base64.b64decode(result['png'])))


class Fonts:
    """pygame's font module for the HD screens: system faces by family name (`match_font` returns the iOS PostScript
    name), and fonts from a file or bytes (the HD app's Pajama Hip, a library's `fonts/` folder) registered with
    CoreText once and then used by name."""
    # Family -> (regular, bold, italic, bold italic) of the faces iOS ships.
    FACES = {'arialroundedmtbold': ('ArialRoundedMTBold',) * 4, 'arialrounded': ('ArialRoundedMTBold',) * 4,
             'arial': ('ArialMT', 'Arial-BoldMT', 'Arial-ItalicMT', 'Arial-BoldItalicMT'),
             'arialbold': ('Arial-BoldMT', 'Arial-BoldMT', 'Arial-BoldItalicMT', 'Arial-BoldItalicMT'),
             'trebuchetms': ('TrebuchetMS', 'TrebuchetMS-Bold', 'TrebuchetMS-Italic', 'Trebuchet-BoldItalic'),
             'trebuchet': ('TrebuchetMS', 'TrebuchetMS-Bold', 'TrebuchetMS-Italic', 'Trebuchet-BoldItalic'),
             'verdana': ('Verdana', 'Verdana-Bold', 'Verdana-Italic', 'Verdana-BoldItalic'),
             'helveticaneue': ('HelveticaNeue', 'HelveticaNeue-Bold', 'HelveticaNeue-Italic',
                               'HelveticaNeue-BoldItalic'),
             'helvetica': ('Helvetica', 'Helvetica-Bold', 'Helvetica-Oblique', 'Helvetica-BoldOblique')}

    def __init__(self, bridge):
        self.bridge = bridge
        self.registered = {}            # sha256 of the bytes -> the PostScript name the host gave them

    @staticmethod
    def init():
        pass

    @staticmethod
    def get_init():
        return True

    def match_font(self, family, bold=False, italic=False):
        faces = self.FACES.get(family.replace(' ', '').lower())
        return None if faces is None else faces[bool(bold) + 2 * bool(italic)]

    def Font(self, source, size):
        if hasattr(source, 'read'):
            source = self.register(source.read())
        elif isinstance(source, str) and os.path.isfile(source):
            with open(source, 'rb') as stream:
                source = self.register(stream.read())
        return PlatformFont(self.bridge, source, size)

    FALLBACK_FACE = 'Helvetica'

    def register(self, data):
        """The PostScript name the host registered a font file's bytes under. A file the host cannot take is logged
        and drawn in a system face instead (FALLBACK_FACE): a supplied font must never stop the runtime."""
        key = sha256(data).hexdigest()
        if key not in self.registered:
            try:
                result = self.bridge(dict(operation='register', data=base64.b64encode(data).decode('ascii')))
                self.registered[key] = result['face'] or self.FALLBACK_FACE
            except Exception as error:
                import logging
                logging.warning('A supplied font could not be registered (%s); drawing it in %s',
                                error, self.FALLBACK_FACE)
                self.registered[key] = self.FALLBACK_FACE
        return self.registered[key]


class Music:
    def __init__(self, owner, channel='music'):
        self.owner, self.channel = owner, channel
        self.paused = False
        self.sound = None               # the EffectSound an effect channel plays (pygame's Channel.get_sound)

    def get_sound(self):
        return self.sound

    def command(self, action, **details):
        if self.channel.startswith('effect:'):
            self.owner.commands.append(dict(kind=f'music_{action}', track=self.channel, **details))
        else:
            self.owner.commands.append(dict(kind=f'{self.channel}_{action}', **details))

    def load(self, stream):
        self.command('load', data=base64.b64encode(stream.read()).decode('ascii'))

    def play(self, loops=0, *, start=0):
        self.command('play', loops=loops, start=start)
        self.paused = False
        self.owner.playing[self.channel] = True
        self.owner.positions[self.channel] = int(start * 1000)

    def queue(self, stream, loops=0):
        """pygame's queue: `stream` plays, repeating `loops` times, when the playing music ends (a translated pack's
        intro running into its loop, MusicStream); the host swaps it in."""
        self.command('queue', data=base64.b64encode(stream.read()).decode('ascii'), loops=loops)

    def set_loops(self, loops):
        self.command('loops', loops=loops)

    def position_ms(self):
        return self.owner.positions.get(self.channel, 0)

    def stop(self):
        self.command('stop')
        self.paused = False
        self.owner.playing.pop(self.channel, None)
        self.owner.positions.pop(self.channel, None)

    def set_volume(self, volume):
        self.command('volume', volume=volume)

    def get_busy(self):
        return self.owner.playing.get(self.channel, False) or (self.paused and self.channel.startswith('effect:'))

    def pause(self):
        if not self.paused and self.get_busy():
            self.command('pause')
            self.paused = True

    def unpause(self):
        if self.paused:
            self.command('resume')
            self.paused = False
            self.owner.playing[self.channel] = True


class EffectSound:
    """pygame's Sound for the HD screens (interface clicks, the pause menu's song, script sounds): each play is one of
    the host's effect channels, at this sound's volume."""
    def __init__(self, mixer, data):
        self.mixer, self.data = mixer, data
        self.volume = 1.0
        self.channels = []

    def set_volume(self, volume):
        self.volume = volume
        for channel in self.channels:
            if channel.get_busy():
                channel.set_volume(volume)

    def get_volume(self):
        return self.volume

    def play(self):
        channel = self.mixer.effect(self)
        self.channels = [playing for playing in self.channels if playing.get_busy()] + [channel]
        return channel

    def stop(self):
        for channel in self.channels:
            channel.stop()
        self.channels = []

    def get_num_channels(self):
        return sum(1 for channel in self.channels if channel.get_busy())


class Mixer:
    def __init__(self):
        self.commands = []
        self.playing = {}
        self.positions = {}
        self.music = Music(self)
        self.menu_music = Music(self, 'menu')
        self.sound_serial = 0
        self.effects = []               # the effect channels EffectSound.play started, oldest first

    def init(self):
        pass  # AVAudioSession is owned by the native host.

    def get_init(self):
        return True

    def stop(self):
        self.commands.append(dict(kind='sounds_stop'))
        for channel in self.effects:
            channel.stop()
        self.effects = []

    def Sound(self, *, file):
        return EffectSound(self, base64.b64encode(file.read()).decode('ascii'))

    def effect(self, sound):
        self.sound_serial += 1
        channel = Music(self, f'effect:{self.sound_serial}')
        channel.sound = sound
        channel.command('load', data=sound.data)
        channel.set_volume(sound.volume)
        channel.play()
        self.effects = [playing for playing in self.effects if playing.get_busy()] + [channel]
        return channel

    def get_num_channels(self):
        self.effects = [playing for playing in self.effects if playing.get_busy()]
        return len(self.effects)

    def Channel(self, index):
        return self.effects[index]

    def play_sound(self, stream, start_ms=0):
        self.sound_serial += 1
        sound = Music(self, f'effect:{self.sound_serial}')
        sound.load(stream)
        sound.play(start=start_ms / 1000)
        return sound


class Backend:
    error, Rect, FRect, Surface = DrawingError, Rect, FRect, Surface
    SRCALPHA, BLEND_RGBA_MULT, RESIZABLE = SRCALPHA, BLEND_RGBA_MULT, RESIZABLE
    BLEND_RGBA_MIN, BLEND_RGBA_MAX, BLEND_RGB_ADD, BLEND_RGB_MULT = BLEND_RGBA_MIN, BLEND_RGBA_MAX, BLEND_RGB_ADD, BLEND_RGB_MULT
    # Event values are private to this host. Keyboard digit ordering is used by
    # the shared accessibility/shortcut path, so keep ASCII digits contiguous.
    QUIT, WINDOWFOCUSLOST, WINDOWFOCUSGAINED, DROPBEGIN, DROPFILE, DROPCOMPLETE = range(1, 7)
    KEYDOWN, TEXTINPUT, MOUSEBUTTONDOWN, MOUSEBUTTONUP, MOUSEMOTION, MOUSEWHEEL = range(7, 13)
    K_1, K_5, K_9 = 49, 53, 57
    K_BACKSPACE, K_RETURN, K_ESCAPE, K_SPACE, K_TAB = 8, 13, 27, 32, 9
    K_UP, K_DOWN, K_PAGEUP, K_PAGEDOWN, K_F5, K_F9 = range(256, 262)
    # Keys the HD menus also read; the host sends only Return, Backspace and Escape (ios.Host._event).
    K_LEFT, K_RIGHT, K_KP_ENTER = range(262, 265)
    K_i = 105
    KMOD_SHIFT = 3

    def __init__(self, bridge, icon_path):
        self.bridge = bridge
        self.ticks = 0
        self.keyboard = False
        self.vibration_available = False
        self.vibrations = 0
        self.pointer = (-1, -1)
        self.window = None
        self.image = ImageAPI(icon_path)
        self.draw, self.transform = Draw(), Transform()
        self.mixer = Mixer()
        self.font = Fonts(bridge)
        self.time = SimpleNamespace(get_ticks=lambda: self.ticks)
        self.mouse = SimpleNamespace(get_pos=lambda: self.pointer)
        self.key = SimpleNamespace(start_text_input=lambda: self._keyboard(True),
                                   stop_text_input=lambda: self._keyboard(False), set_text_input_rect=lambda rect: None,
                                   get_mods=lambda: 0)
        self.display = SimpleNamespace(init=lambda: None, set_mode=self._window, flip=lambda: None,
                                       set_icon=lambda icon: None, set_caption=lambda caption: None)

    def _keyboard(self, enabled):
        self.keyboard = enabled

    def vibrate(self):
        self.vibrations += 1

    def _window(self, size, flags=0):
        self.window = Surface(size)
        return self.window

    def quit(self):
        for channel in tuple(self.mixer.playing):
            if channel.startswith('effect:'):
                Music(self.mixer, channel).stop()
        self.mixer.music.stop()
        self.mixer.menu_music.stop()
        self.mixer.stop()
        self.keyboard = False
