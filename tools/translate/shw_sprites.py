"""The Surviving Hollywood demo's sprite set (resource 16), read as the jar's own code reads it (f.a(DataInputStream); the
same reader as Tardy-Slip's `data/shw-ui.js` parseSpriteSet): its images, animations and composites.

Layout: u8 flags (1 wide frame ids, 2 wide offsets, 4 wide animation frames), s16 image count, s8 animation count (then s16
base, s16 unused, and per animation s8 n and n frame ids, base added), s16 composite count, s16 unused, per composite u8 n and n
(frame, dx, dy); then a glyph strip: s16 palette size, the palette's RGB triples, s16 image count, and per image u8 w, u8 h and
w x h palette indices, index 0 transparent. A negative frame id -(k + 1) is composite k.

    python tools/translate/shw_sprites.py JAR OUT.png      (a numbered sheet of every image, at 3 times)
"""
import struct
import sys
from pathlib import Path

from PIL import Image


class _Reader:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def u8(self):
        self.pos += 1
        return self.data[self.pos - 1]

    def s8(self):
        return struct.unpack_from('b', self.data, self._skip(1))[0]

    def s16(self):
        return struct.unpack_from('>h', self.data, self._skip(2))[0]

    def _skip(self, n):
        self.pos += n
        return self.pos - n


def parse(data):
    """(images, animations, composites): images as RGBA PIL images, animations as lists of frame ids, composites as lists of
    (frame, dx, dy)."""
    r = _Reader(data)
    flags = r.u8()
    wide_frames, wide_offsets, wide_anims = bool(flags & 1), bool(flags & 2), bool(flags & 4)
    count = r.s16()
    anims = []
    anim_count = r.s8()
    if anim_count > 0:
        base = r.s16()
        r.s16()
        for _ in range(anim_count):
            n = r.s8()
            anims.append([(r.s16() if wide_anims else r.s8()) + base for _ in range(n)])
    comps = []
    comp_count = r.s16()
    r.s16()
    for _ in range(comp_count):
        n = r.u8()
        comps.append([((r.s16() if wide_frames else r.s8()), (r.s16() if wide_offsets else r.s8()),
                       (r.s16() if wide_offsets else r.s8())) for _ in range(n)])
    images, end = glyph_strip(r.data, r.pos)
    if len(images) != count:
        raise ValueError(f'sprite set: {len(images)} images, header says {count}')
    return images, anims, comps


def glyph_strip(data, pos):
    """(images, end): a glyph strip at `pos` (GameMidlet.a(InputStream...)), its images as RGBA PIL images."""
    r = _Reader(data)
    r.pos = pos
    palette_size = r.s16()
    palette = [(r.u8(), r.u8(), r.u8()) for _ in range(palette_size)]
    images = []
    for _ in range(r.s16()):
        w, h = r.u8(), r.u8()
        pixels = r.data[r.pos:r.pos + w * h]
        r.pos += w * h
        image = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        if w * h:
            image.putdata([(0, 0, 0, 0) if k == 0 else (*palette[k], 255) for k in pixels])
        images.append(image)
    return images, r.pos


def put(canvas, image, x, y):
    """Alpha-composite `image` onto `canvas` at (x, y), any part off the canvas left out."""
    left, top = max(0, -x), max(0, -y)
    if left >= image.width or top >= image.height:
        return
    part = image.crop((left, top, image.width, image.height)) if left or top else image
    if x + left < canvas.width and y + top < canvas.height:
        canvas.alpha_composite(part, (x + left, y + top))


def sheet(images, scale=3):
    from PIL import ImageDraw
    cell = 120
    cols = 10
    out = Image.new('RGB', (cols * cell, ((len(images) + cols - 1) // cols) * (cell + 14)), (60, 62, 72))
    d = ImageDraw.Draw(out)
    for i, image in enumerate(images):
        x, y = (i % cols) * cell, (i // cols) * (cell + 14)
        if image.width and image.height:
            k = max(1, min(scale, (cell - 4) // max(image.width, 1), (cell - 4) // max(image.height, 1)))
            big = image.resize((image.width * k, image.height * k), Image.NEAREST)
            out.paste(big, (x + 2, y + 2), big)
        d.text((x + 2, y + cell), f'{i} {image.width}x{image.height}', fill=(240, 240, 240))
    return out


if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import shw
    images, anims, comps = parse(shw.jar_resources(sys.argv[1])[16])
    print(len(images), 'images', len(anims), 'animations', len(comps), 'composites')
    sheet(images).save(sys.argv[2])
