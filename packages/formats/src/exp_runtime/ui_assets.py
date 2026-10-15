"""Native layout-bank and image-pack records, read from the player's APK.

The parsers are independent of pygame. All dimensions, pixels and layout
records stay in user content; only the recovered decoding rules live here.
See docs/UI_FIDELITY.md and docs/UI_ASSETS.md for the native evidence.
"""
from dataclasses import dataclass
from functools import lru_cache
import struct

from .exp import ContentError, MAX_PAYLOAD


def read_ui(resources, role):
    """Read a host UI role; authored resource fixtures may expose only IDs."""
    reader = getattr(resources, 'read_ui_resource', None) or resources.read_asset
    return reader(role)


class UIAssetError(ContentError):
    pass


class _Reader:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def take(self, size):
        if size < 0 or self.pos + size > len(self.data):
            raise UIAssetError('Truncated UI asset')
        start, self.pos = self.pos, self.pos + size
        return self.data[start:self.pos]

    def unpack(self, fmt):
        return struct.unpack('>' + fmt, self.take(struct.calcsize('>' + fmt)))

    def integer(self, fmt='h'):
        return self.unpack(fmt)[0]

    def count(self, fmt='h'):
        result = self.integer(fmt)
        if result < 0:
            raise UIAssetError('Negative UI record count')
        return result

    def finish(self):
        if self.pos != len(self.data):
            raise UIAssetError(f'Unconsumed UI asset bytes at {self.pos}')


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def center(self):
        return self.x + self.width // 2, self.y + self.height // 2


@dataclass(frozen=True)
class LayoutNode:
    base: tuple[int, int, int, int]
    relative: tuple[int, int, int, int]
    flags: int
    payload: tuple[int, ...]

    @property
    def kind(self):
        return self.flags & 15

    def rectangle(self, parent: Rect, design: tuple[int, int]):
        dx, dy = parent.width - design[0], parent.height - design[1]
        x1, y1, x2, y2 = (v + ((d * r) >> 12)
                          for v, d, r in zip(self.base, (dx, dy, dx, dy), self.relative))
        return Rect(parent.x + x1, parent.y + y1, x2 - x1, y2 - y1)


@dataclass(frozen=True)
class Layout:
    width: int
    height: int
    nodes: tuple[LayoutNode, ...]


@dataclass(frozen=True)
class LayoutBank:
    image_slots: int
    font_slots: int
    other_slots: int
    colors: tuple[int, ...]
    layouts: tuple[Layout, ...]

    @classmethod
    def parse(cls, data: bytes):
        reader = _Reader(data)
        images, fonts, other, color_count = (reader.count('b') for _ in range(4))
        colors = tuple(reader.integer('i') for _ in range(color_count))
        layouts = []
        for _ in range(reader.count()):
            width, height, count = (reader.count() for _ in range(3))
            nodes = []
            for _ in range(count):
                base, relative = reader.unpack('hhhh'), reader.unpack('hhhh')
                flags = reader.integer('B')
                fmt = {0: 'h', 1: 'hh', 2: 'b', 3: 'b', 4: 'b', 5: 'b', 6: '', 7: 'b'}.get(flags & 15)
                if fmt is None:
                    raise UIAssetError(f'Unsupported layout node kind {flags & 15}')
                nodes.append(LayoutNode(base, relative, flags, reader.unpack(fmt)))
            layouts.append(Layout(width, height, tuple(nodes)))
        reader.finish()
        for layout in layouts:
            for node in layout.nodes:
                if node.kind == 7 and not 0 <= node.payload[0] < len(layouts):
                    raise UIAssetError('Layout references an absent layout')
        return cls(images, fonts, other, colors, tuple(layouts))

    def walk(self, layout_id: int, rect: Rect | None = None):
        """Flatten native one-based node IDs, including each reference root.

        Node zero is the caller's rectangle. A reference contributes itself,
        then every node of the referenced layout (FUN_00057400).
        """
        remaining = 100000
        def visit(index, bounds, ancestors):
            nonlocal remaining
            if index in ancestors or len(ancestors) >= 64:
                raise UIAssetError('Recursive UI layout reference')
            try:
                layout = self.layouts[index]
            except IndexError:
                raise UIAssetError('Absent UI layout') from None
            for node in layout.nodes:
                remaining -= 1
                if remaining < 0:
                    raise UIAssetError('UI layout expansion exceeds supported size')
                child = node.rectangle(bounds, (layout.width, layout.height))
                yield node, child
                if node.kind == 7:
                    yield from visit(node.payload[0], child, ancestors + (index,))
        if not 0 <= layout_id < len(self.layouts):
            raise UIAssetError('Absent UI layout')
        layout = self.layouts[layout_id]
        yield from visit(layout_id, rect or Rect(0, 0, layout.width, layout.height), ())

    @lru_cache(maxsize=512)
    def rectangle(self, layout_id: int, node_id: int, rect: Rect | None = None):
        # A node's rectangle is a pure function of the bank's own static data plus these three arguments --
        # every caller across the whole UI (dialogue, choice, menu, message, title, input) asks for the same
        # handful of node ids over and over, often several times a frame for the same answer (profiled live:
        # one dialogue screen's relationship-icon placement alone cost ~13 full tree walks every frame). `self`
        # is part of the cache key and the bank is immutable once parsed, so this is safe for the bank's own
        # lifetime; `walk()` itself stays uncached since its generator form doesn't fit lru_cache, but its
        # handful of direct callers each run once per screen, not once per frame.
        if node_id == 0 and 0 <= layout_id < len(self.layouts):
            layout = self.layouts[layout_id]
            return rect or Rect(0, 0, layout.width, layout.height)
        for index, (_, bounds) in enumerate(self.walk(layout_id, rect), 1):
            if index == node_id:
                return bounds
        raise UIAssetError(f'Absent layout node {layout_id}:{node_id}')


@dataclass(frozen=True)
class Raster:
    width: int
    height: int
    pixels: bytes
    mode: str = 'RGBA'

    def normalize_portrait(self, mask):
        """Convert supported 2x episode portraits to the mask's logical scale.

        Imported New Girl art includes 256x256 and 226x256 PNGs. This is a
        compatibility rule for those larger variants, not an operation found
        in Android's native mask routine. Native-size images stay untouched;
        other oversized dimensions remain explicit errors in portrait_mask().
        """
        if (self.mode == 'RGBA' and mask.mode == 'A'
                and (self.width > mask.width or self.height > mask.height)
                and self.width % 2 == self.height % 2 == 0
                and 0 < self.width <= mask.width * 2 and 0 < self.height <= mask.height * 2):
            from PIL import Image
            size = self.width // 2, self.height // 2
            # Pillow resamples RGBA through premultiplied alpha, so invisible
            # RGB does not add a fringe around the smaller portrait.
            image = Image.frombytes(self.mode, (self.width, self.height), self.pixels)
            image = image.resize(size, Image.Resampling.BOX)
            return Raster(*size, image.tobytes())
        return self

    def portrait_mask(self, mask):
        """FUN_00059eb4: bottom-align to 128x150 and clear nonzero mask pixels.

        The native integer expression is (255-mask)//255, not a continuous
        alpha blend. This preserves the supplied mask's hard clipping rule.
        """
        if (self.mode != 'RGBA' or mask.mode != 'A'
                or self.width > mask.width or self.height > mask.height):
            raise UIAssetError(f'Unsupported portrait {self.width}x{self.height} {self.mode} '
                               f'for mask {mask.width}x{mask.height} {mask.mode}')
        left, top = (mask.width - self.width) // 2, mask.height - self.height
        out = bytearray(self.pixels)
        for y in range(self.height):
            for x in range(self.width):
                if mask.pixels[(top + y) * mask.width + left + x]:
                    pos = (y * self.width + x) * 4
                    out[pos:pos + 4] = b'\0\0\0\0'
        return Raster(self.width, self.height, bytes(out))

    def transformed(self, transform: int):
        if self.mode != 'RGBA' or not 0 <= transform <= 7:
            raise UIAssetError('Unsupported image-pack transform')
        width, height = (self.width, self.height) if transform < 4 else (self.height, self.width)
        out = bytearray(width * height * 4)
        for y in range(self.height):
            for x in range(self.width):
                dx, dy = ((x, y), (x, height - 1 - y), (width - 1 - x, y),
                          (width - 1 - x, height - 1 - y), (y, x),
                          (width - 1 - y, x), (y, height - 1 - x),
                          (width - 1 - y, height - 1 - x))[transform]
                source, target = (y * self.width + x) * 4, (dy * width + dx) * 4
                out[target:target + 4] = self.pixels[source:source + 4]
        return Raster(width, height, bytes(out))


@dataclass(frozen=True)
class ImagePack:
    flags: int
    frame_count: int
    sequences: tuple[tuple[int, ...], ...]
    parts: tuple[tuple[tuple[int, int, int], ...], ...]
    images: tuple[Raster, ...]
    # Byte offset of each literal image's stored pixels (None for a generated one), so a derived pack can be written
    # back into a copy of the original bytes (cod/hd_art.py).
    pixel_offsets: tuple = ()

    @classmethod
    def parse(cls, data: bytes):
        reader = _Reader(data)
        flags, frames, groups = reader.integer('B'), reader.count(), reader.count('b')
        if flags & ~0x3f:
            raise UIAssetError(f'Unsupported image-pack flags 0x{flags:x}')
        sequences = []
        if groups:
            base, total = reader.integer(), reader.count()
            for _ in range(groups):
                sequences.append(tuple(base + reader.integer('h' if flags & 4 else 'b')
                                       for _ in range(reader.count('b'))))
            if sum(map(len, sequences)) != total:
                raise UIAssetError('Inconsistent image sequence count')
        groups, total = reader.count(), reader.count()
        parts = []
        for _ in range(groups):
            parts.append(tuple((reader.integer('h' if flags & 1 else 'b'),
                                reader.integer('h' if flags & 2 else 'b'),
                                reader.integer('h' if flags & 2 else 'b'))
                               for _ in range(reader.count('b'))))
        if sum(map(len, parts)) != total:
            raise UIAssetError('Inconsistent image part count')
        transforms = tuple(reader.unpack('hhb') for _ in range(reader.count()))
        marker = 0 if flags & 8 else reader.integer()
        if marker not in (-1, -2):
            raise UIAssetError(f'Unsupported image-pack pixel encoding {marker}')
        images, offsets, total_bytes = [], [], 0
        for _ in range(reader.count()):
            width = reader.integer('h' if flags & 32 else 'B')
            if width == 0:
                images.append(None)  # Generated from an earlier literal image.
                offsets.append(None)
                continue
            height = reader.integer('h' if flags & 32 else 'B')
            size = width * height * (4 if marker == -1 else 1)
            total_bytes += size
            if width < 0 or height <= 0 or total_bytes > MAX_PAYLOAD:
                raise UIAssetError('Invalid or excessive image-pack dimensions')
            offsets.append(reader.pos)
            pixels = reader.take(size)
            if marker == -1:
                rgba = bytearray(size)
                rgba[0::4], rgba[1::4], rgba[2::4], rgba[3::4] = (pixels[1::4], pixels[2::4],
                                                               pixels[3::4], pixels[0::4])
                pixels = bytes(rgba)
            images.append(Raster(width, height, pixels, 'RGBA' if marker == -1 else 'A'))
        reader.finish()
        literal_indices = {index for index, image in enumerate(images) if image is not None}
        for source, target, transform in transforms:
            if (source not in literal_indices or not 0 <= target < len(images)
                    or images[target] is not None):
                raise UIAssetError('Invalid image-pack transform reference')
            total_bytes += len(images[source].pixels)
            if total_bytes > MAX_PAYLOAD:
                raise UIAssetError('Excessive generated image data')
            images[target] = images[source].transformed(transform)
        if any(image is None for image in images):
            raise UIAssetError('Unresolved image-pack placeholder')
        return cls(flags, frames, tuple(sequences), tuple(parts), tuple(images), tuple(offsets))
