"""Packed RGBA sprite atlases used by the native minigame renderer.

This is the CS sprite-atlas path (000507b8 / 000503dc), separate from
ImagePack's literal-image path. All dimensions and extents are bounded.
"""
from dataclasses import dataclass

from .exp import MAX_PAYLOAD
from .ui_assets import Raster, UIAssetError, _Reader


@dataclass(frozen=True)
class AtlasFrame:
    x: int
    y: int
    width: int
    height: int
    stored_width: int
    stored_height: int


@dataclass(frozen=True)
class SpriteAtlas:
    flags: int
    sequences: tuple[tuple[int, ...], ...]
    parts: tuple[tuple[tuple[int, int, int], ...], ...]
    transforms: tuple[tuple[int, int], ...]
    frames: tuple[AtlasFrame, ...]
    image: Raster

    @classmethod
    def parse(cls, data):
        r = _Reader(data)
        flags, capacity, count = r.integer('B'), r.count(), r.count('b')
        if flags & ~0x3f:
            raise UIAssetError('Unsupported sprite-atlas flags')
        sequences = []
        if count:
            base, total = r.integer(), r.count()
            for _ in range(count):
                sequences.append(tuple(base + r.integer('h' if flags & 4 else 'b')
                                       for __ in range(r.count('b'))))
            if sum(map(len, sequences)) != total:
                raise UIAssetError('Inconsistent atlas sequences')
        count, total = r.count(), r.count()
        parts = []
        for _ in range(count):
            parts.append(tuple((r.integer('h' if flags & 1 else 'b'),
                                r.integer('h' if flags & 2 else 'b'),
                                r.integer('h' if flags & 2 else 'b'))
                               for __ in range(r.count('b'))))
        if sum(map(len, parts)) != total:
            raise UIAssetError('Inconsistent atlas parts')
        transforms = tuple(r.unpack('hb') for _ in range(r.count()))
        scale, size, count = r.integer(), r.count(), r.count()
        if scale <= 0 or size <= 0 or size * size * 4 > MAX_PAYLOAD or count != capacity:
            raise UIAssetError('Invalid sprite-atlas dimensions')
        frames = []
        for _ in range(count):
            x, y, w, h, sw, sh = r.unpack('hhhhhh')
            x, y = x * scale, y * scale
            if (min(x, y, w, h, sw, sh) < 0 or w * h * 4 > MAX_PAYLOAD
                    or x + sw > size or y + sh > size):
                raise UIAssetError('Sprite frame is outside its atlas')
            frames.append(AtlasFrame(x, y, w, h, sw, sh))
        data = r.take(size * size * 4)
        r.finish()
        # 000503dc reverses each stored A,B,G,R quadruple before upload.
        rgba = bytearray(len(data))
        rgba[0::4], rgba[1::4], rgba[2::4], rgba[3::4] = data[3::4], data[2::4], data[1::4], data[0::4]
        for frame, transform in transforms:
            if not 0 <= frame < count or not 0 <= transform <= 7:
                raise UIAssetError('Invalid atlas transform')
        for group in parts:
            for index, _, __ in group:
                if not (-len(parts) <= index < count):
                    raise UIAssetError('Invalid atlas part reference')
        if any(not -len(parts) <= index < count for sequence in sequences for index in sequence):
            raise UIAssetError('Invalid atlas sequence reference')
        return cls(flags, tuple(sequences), tuple(parts), transforms, tuple(frames),
                   Raster(size, size, bytes(rgba)))

    def raster(self, index):
        """Decode a positive literal frame; composites retain signed references."""
        if not 0 <= index < len(self.frames):
            raise UIAssetError('Absent atlas frame')
        f = self.frames[index]
        # CSGLMasterImage draws a quad at the stored dimensions. The logical
        # dimensions are used for metrics and mirrored placement, not scaling
        # (Android 00050ecc, iOS SHS 0000a95c / 0000d96c).
        row_size = f.stored_width * 4
        pixels = b''.join(self.image.pixels[(y * self.image.width + f.x) * 4:
                                          (y * self.image.width + f.x) * 4 + row_size]
                          for y in range(f.y, f.y + f.stored_height))
        result = Raster(f.stored_width, f.stored_height, pixels)
        # Atlas transforms are vertex permutations, distinct from ImagePack's
        # eight generated-image transforms. Native cases 1, 4 and 7 are no-ops.
        transform = (0, 0, 2, 3, 0, 4, 7, 0)[self.transform(index)]
        return result.transformed(transform) if transform else result

    def transform(self, index):
        # The native parser assigns a per-frame byte; later records overwrite
        # earlier ones rather than applying a sequence of transformations.
        return next((value for frame, value in reversed(self.transforms) if frame == index), 0)

    def origin(self, index):
        """Offset of stored pixels from the literal's logical drawing origin."""
        if not 0 <= index < len(self.frames):
            raise UIAssetError('Absent atlas frame')
        frame = self.frames[index]
        return (frame.width - frame.stored_width if self.transform(index) == 2 else 0), 0

    def literals(self, index):
        """Flatten signed composite references, preserving painter order/origin."""
        result = []

        def visit(ref, x, y, ancestors):
            if ref >= 0:
                if ref >= len(self.frames) or len(result) >= 4096:
                    raise UIAssetError('Invalid or oversized atlas composite')
                dx, dy = self.origin(ref)
                result.append((ref, x + dx, y + dy))
                return
            if ref in ancestors or len(ancestors) >= 64 or ~ref >= len(self.parts):
                raise UIAssetError('Invalid or cyclic atlas composite')
            for child, dx, dy in self.parts[~ref]:
                visit(child, x + dx, y + dy, ancestors + (ref,))

        visit(index, 0, 0, ())
        return tuple(result)


@dataclass(frozen=True)
class AtlasFont:
    """000538ac: six-byte header, then (byte, s16 x, s16 y, s8 width)."""
    space_width: int
    style: int
    tracking: int
    height: int
    glyphs: dict[int, tuple[int, int, int]]

    @classmethod
    def parse(cls, data, atlas):
        r = _Reader(data)
        space, style, tracking = r.integer('b'), r.integer('B'), r.integer('b')
        count, height = r.count(), r.integer('b')
        if height <= 0 or space < 0 or count > 256:
            raise UIAssetError('Invalid atlas font header')
        glyphs = {}
        for _ in range(count):
            code, x, y, width = r.unpack('Bhhb')
            if min(x, y, width) < 0 or x + width > atlas.width or y + height > atlas.height:
                raise UIAssetError('Font glyph is outside its atlas')
            glyphs[code] = x, y, width
        r.finish()
        return cls(space, style, tracking, height, glyphs)

    def glyph(self, char):
        code = ord(char)
        code = {0x91: 39, 0x92: 39, 0x93: 34, 0x94: 34, 0x96: 45}.get(code, code)
        if code not in self.glyphs:
            if 97 <= code <= 122 or 224 <= code <= 252:
                code -= 32
            elif 65 <= code <= 90 or 192 <= code <= 220:
                code += 32
        return self.glyphs.get(code)

    @property
    def line_gap(self):
        # 000538ac stores header byte 1 at +0x139; 00054490 adds it to
        # each line's height. The older parser called this byte "style".
        return self.style if self.style < 128 else self.style - 256

    def char_width(self, char, monospace=None):
        if monospace is not None:
            return self.char_width(monospace)
        glyph = self.glyph(char)
        return glyph[2] if glyph is not None else self.space_width

    def width(self, text, monospace=None):
        """000535fc: trim leading spaces, omit the last tracking interval."""
        return max((max(0, sum(self.char_width(c, monospace) + self.tracking for c in line)
                        - self.tracking) if line else 0
                    for line in text.lstrip(' ').split('\n')), default=0)

    def wrap(self, text, width):
        """00054490: byte glyph advances, space wrapping and explicit newlines."""
        if width <= 0:
            raise UIAssetError('Atlas text width must be positive')
        lines = []
        while text:
            text = text.lstrip(' ')
            if not text:
                break
            end, advance = 0, 0
            while end < len(text) and text[end] != '\n':
                glyph_width = self.char_width(text[end])
                if glyph_width > width:
                    raise UIAssetError('Atlas text column cannot fit a glyph')
                if advance + glyph_width > width:
                    break
                advance += glyph_width + self.tracking
                end += 1
            if end == len(text):
                lines.append(text)
                break
            if text[end] == '\n':
                lines.append(text[:end])
                text = text[end + 1:]
            else:
                space = text.rfind(' ', 0, end + 1)
                if space > 0:
                    end = space
                lines.append(text[:end])
                text = text[end:]
        return tuple(lines)

    def text_height(self, lines):
        return len(lines) * (self.height + self.line_gap) - self.line_gap if lines else 0
