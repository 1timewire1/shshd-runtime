"""Retained drawing commands for native hosts, using the shared renderer API.

Only the primitives used by our presentation code are implemented. This is not
an SDL emulator. Immutable snapshots keep cached layers and fades independent
of later writes. Native hosts rasterize commands; Pillow decodes source images
and performs the small, byte-exact asset operations used by masks and atlases.
"""
import base64
from dataclasses import dataclass, field
from functools import lru_cache
from io import BytesIO
from itertools import count
import math
import struct
from types import SimpleNamespace

from PIL import Image, ImageDraw


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

    @property
    def size(self):
        return self.width, self.height

    @property
    def topleft(self):
        return self.x, self.y

    @property
    def top(self):
        return self.y

    @property
    def bottom(self):
        return self.y + self.height

    @property
    def left(self):
        return self.x

    @property
    def right(self):
        return self.x + self.width

    @property
    def centerx(self):
        return self.x + (self.width // 2 if self.cast is int else self.width / 2)

    @centerx.setter
    def centerx(self, value):
        self.x = self.cast(value) - (self.width // 2 if self.cast is int else self.width / 2)

    @property
    def centery(self):
        return self.y + (self.height // 2 if self.cast is int else self.height / 2)

    @centery.setter
    def centery(self, value):
        self.y = self.cast(value) - (self.height // 2 if self.cast is int else self.height / 2)

    @property
    def center(self):
        return self.centerx, self.centery

    @center.setter
    def center(self, point):
        self.centerx, self.centery = point

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

    def move(self, x, y):
        return type(self)(self.x + self.cast(x), self.y + self.cast(y), self.width, self.height)

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


def rgba(color):
    return tuple(color) if len(color) == 4 else (*color, 255)


@dataclass(eq=False)
class Node:
    size: tuple
    ops: tuple = ()
    pixels: Image.Image | None = None
    identifier: int = field(default_factory=lambda: next(_ids))
    encoded: str | None = None

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
            if special_flags != BLEND_RGBA_MULT:
                raise DrawingError('Unsupported fill blend')
            pixels = raster(self.snapshot())
            box = (region.x, region.y, region.right, region.bottom)
            patch = pixels.crop(box)
            # SDL's multiply is (a*b + 255) >> 8, including alpha.
            patch = Image.merge('RGBA', [channel.point(lambda a, b=b: (a * b + 255) >> 8)
                                        for channel, b in zip(patch.split(), rgba(color))])
            pixels.paste(patch, box)
            self._ops, self._node = [], Node(self._size, pixels=pixels)
            self.opaque = pixels.getextrema()[3] == (255, 255)
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
            if special_flags != BLEND_RGBA_MULT or at != (0, 0) or source.get_size() != self._size:
                raise DrawingError('Unsupported image blend')
            a, b = raster(self.snapshot()), raster(source.snapshot())
            # The timer mask has binary channels. General multiply uses the
            # same rounded multiplication as the atlas modulation above.
            pixels = Image.frombytes('RGBA', self._size,
                                     bytes((x * y + 255) >> 8 for x, y in zip(a.tobytes(), b.tobytes())))
            self._ops, self._node = [], Node(self._size, pixels=pixels)
            self.opaque = pixels.getextrema()[3] == (255, 255)
        elif bounds.width > 0 and bounds.height > 0:
            node = source.snapshot()
            if source.opaque and source._alpha == 255 and bounds == self.get_rect():
                self._ops, self._node = [], None
                self.opaque = True
            self._append(dict(kind='blit', source=node, at=at, alpha=source._alpha))
        return bounds

    def subsurface(self, rect):
        rect = Rect(rect)
        if rect.x < 0 or rect.y < 0 or rect.right > self.get_width() or rect.bottom > self.get_height():
            raise DrawingError('Subsurface lies outside its source')
        node = self.snapshot()
        if node.pixels is not None:
            return self.from_pixels(node.pixels.crop((rect.x, rect.y, rect.right, rect.bottom)))
        result = Surface(rect.size, SRCALPHA)
        result.blit(self, (-rect.x, -rect.y))
        return result


class Draw:
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


class Transform:
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
    for op in node.ops:
        kind = op['kind']
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
        if kind == 'blit':
            source = raster(op['source'])
            if op['alpha'] != 255:
                source.putalpha(source.getchannel('A').point(lambda a: a * op['alpha'] // 255))
            layer.alpha_composite(source, op['at'])
        elif kind == 'textured_quad':
            from ..projection import warp
            x, y, w, h = op['bounds']
            source = warp(raster(op['source']), (w, h), op['coefficients'])
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
    def __init__(self, bridge, face, size):
        self.bridge, self.face, self.points = bridge, face, max(1, round(size * .75)) if face is None else size

    @lru_cache(maxsize=512)
    def metrics(self, text):
        return self.bridge(dict(operation='text', face=self.face, size=self.points, text=text, measure=True))

    def size(self, text):
        result = self.metrics(text)
        return result['width'], result['height']

    def get_linesize(self):
        return self.metrics('Mg')['height']

    @lru_cache(maxsize=128)
    def render(self, text, antialias, color):
        result = self.bridge(dict(operation='text', face=self.face, size=self.points, text=text, color=rgba(color)))
        return ImageAPI.load(BytesIO(base64.b64decode(result['png'])))


class Music:
    def __init__(self, owner, channel='music'):
        self.owner, self.channel = owner, channel

    def command(self, action, **details):
        self.owner.commands.append(dict(kind=f'{self.channel}_{action}', **details))

    def load(self, stream):
        self.command('load', data=base64.b64encode(stream.read()).decode('ascii'))

    def play(self, loops=0, *, start=0):
        self.command('play', loops=loops, start=start)

    def stop(self):
        self.command('stop')

    def pause(self):
        self.command('pause')

    def unpause(self):
        self.command('resume')


class Mixer:
    def __init__(self):
        self.commands = []
        self.music = Music(self)
        self.menu_music = Music(self, 'menu')

    def init(self):
        pass  # AVAudioSession is owned by the native host.

    def stop(self):
        self.commands.append(dict(kind='sounds_stop'))

    def Sound(self, *, file):
        data = base64.b64encode(file.read()).decode('ascii')
        return SimpleNamespace(play=lambda: self.commands.append(dict(kind='sound', data=data)))


class Backend:
    error, Rect, FRect, Surface = DrawingError, Rect, FRect, Surface
    SRCALPHA, BLEND_RGBA_MULT, RESIZABLE = SRCALPHA, BLEND_RGBA_MULT, RESIZABLE
    # Event values are private to this host. Keyboard digit ordering is used by
    # the shared accessibility/shortcut path, so keep ASCII digits contiguous.
    QUIT, WINDOWFOCUSLOST, WINDOWFOCUSGAINED, DROPBEGIN, DROPFILE, DROPCOMPLETE = range(1, 7)
    KEYDOWN, TEXTINPUT, MOUSEBUTTONDOWN, MOUSEBUTTONUP, MOUSEMOTION, MOUSEWHEEL = range(7, 13)
    K_1, K_5, K_9 = 49, 53, 57
    K_BACKSPACE, K_RETURN, K_ESCAPE, K_SPACE, K_TAB = 8, 13, 27, 32, 9
    K_UP, K_DOWN, K_PAGEUP, K_PAGEDOWN, K_F5, K_F9 = range(256, 262)

    def __init__(self, bridge, icon_path):
        self.bridge = bridge
        self.ticks = 0
        self.keyboard = False
        self.pointer = (-1, -1)
        self.window = None
        self.image = ImageAPI(icon_path)
        self.draw, self.transform = Draw(), Transform()
        self.mixer = Mixer()
        self.font = SimpleNamespace(init=lambda: None, match_font=lambda *a, **k: 'ArialRoundedMTBold',
                                    Font=lambda face, size: PlatformFont(bridge, face, size))
        self.time = SimpleNamespace(get_ticks=lambda: self.ticks)
        self.mouse = SimpleNamespace(get_pos=lambda: self.pointer)
        self.key = SimpleNamespace(start_text_input=lambda: self._keyboard(True),
                                   stop_text_input=lambda: self._keyboard(False), set_text_input_rect=lambda rect: None)
        self.display = SimpleNamespace(init=lambda: None, set_mode=self._window, flip=lambda: None,
                                       set_icon=lambda icon: None, set_caption=lambda caption: None)

    def _keyboard(self, enabled):
        self.keyboard = enabled

    def _window(self, size, flags=0):
        self.window = Surface(size)
        return self.window

    def quit(self):
        self.mixer.music.stop()
        self.mixer.menu_music.stop()
        self.mixer.stop()
        self.keyboard = False
