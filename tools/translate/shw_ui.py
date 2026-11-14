"""The Surviving Hollywood demo's interface resources, read and drawn as the jar's own code does them (the same readers as Tardy-
Slip's `data/shw-ui.js` and `web/shw/ui.js`, ported from the decompiled classes): the UI strings (14), the bitmap fonts (8, 10, 11)
and the layout set (15), drawn with the sprite set (16, shw_sprites.py) onto a 240 x 320 picture.

- **Strings** (GameMidlet.y(int)): string n starts at the u16 offset at byte 9 + 2n, NUL-terminated; the count is the u16 at 7.
- **Fonts** (j.a(InputStream)): s8 space, s8 gap, s8 tracking, s16 glyph count, s8 height, the characters, then a glyph strip
  (shw_sprites). A letter with no glyph takes the other case's.
- **Layouts** (k.a(...)): u8 sprite sets, u8 image slots, u8 colour count and s32 colours, s16 layout count, then per layout s16
  w, h, n and n children: x1 y1 x2 y2, four Q12 anchors (how far each edge moves as the layout is sized), a type byte (its low
  three bits the kind: 0 an image slot tiled, 1 a sprite frame tiled, 2-4 a fill, 5 an outline, 7 a layout inside; 32 shown,
  64 a tiled sub-layout) and the kind's arguments. A child's place, counted from 1 through the sub-layouts, is its index (rect).
"""
import struct

from PIL import Image, ImageDraw

import shw_sprites

W, H = 240, 320


def strings(data):
    count = struct.unpack_from('>H', data, 7)[0]
    out = []
    for n in range(count):
        start = struct.unpack_from('>H', data, 9 + 2 * n)[0]
        end = data.index(b'\0', start) if b'\0' in data[start:] else len(data)
        out.append(data[start:end].decode('latin-1'))
    return out


class Font:
    def __init__(self, data):
        self.space, self.gap, self.tracking = struct.unpack_from('bbb', data, 0)
        count = struct.unpack_from('>h', data, 3)[0]
        self.height = struct.unpack_from('b', data, 5)[0]
        chars = data[6:6 + count]
        images, _ = shw_sprites.glyph_strip(data, 6 + count)
        self.glyphs = {c: images[k] for k, c in enumerate(chars)}
        for c in range(65, 256):
            if c not in self.glyphs:
                other = ord(chr(c).swapcase()) if len(chr(c).swapcase()) == 1 else c
                if other in self.glyphs:
                    self.glyphs[c] = self.glyphs[other]

    def glyph(self, ch):
        return self.glyphs.get(ord(ch)) if ord(ch) < 256 else None

    def char_width(self, ch):
        glyph = self.glyph(ch)
        return glyph.width if glyph is not None else self.space

    def width(self, text):
        return sum(self.char_width(ch) + self.tracking for ch in text) - self.tracking if text else 0

    def image(self, text):
        """One line of text on a clear picture as wide as `width` and the font's height (j.a, one line, left aligned)."""
        out = Image.new('RGBA', (max(1, self.width(text)), max(1, self.height)), (0, 0, 0, 0))
        x = 0
        for ch in text:
            glyph = self.glyph(ch)
            if ch != ' ' and glyph is not None:
                out.alpha_composite(glyph, (x, 0))
            x += self.char_width(ch) + self.tracking
        return out


class Layouts:
    def __init__(self, data, sprites, comps, slots):
        p = 0
        self.sprite_sets, self.images, colours = data[0], data[1], data[2]
        p = 3
        self.colours = list(struct.unpack_from('>' + 'i' * colours, data, p))
        p += 4 * colours
        count = struct.unpack_from('>h', data, p)[0]
        p += 2
        self.layouts = []
        for _ in range(count):
            w, h, n = struct.unpack_from('>hhh', data, p)
            p += 6
            children = []
            for _ in range(n):
                values = struct.unpack_from('>8h', data, p)
                p += 16
                kind_byte = data[p]
                p += 1
                kind = kind_byte & 7
                a = b = 0
                if kind == 0:
                    a = struct.unpack_from('>h', data, p)[0]; p += 2
                elif kind == 1:
                    a, b = struct.unpack_from('>hh', data, p); p += 4
                elif 2 <= kind <= 5 or kind == 7:
                    a = data[p]; p += 1
                children.append(dict(zip(('x1', 'y1', 'x2', 'y2', 'ax1', 'ay1', 'ax2', 'ay2'), values), type=kind_byte, a=a, b=b))
            self.layouts.append(dict(w=w, h=h, children=children))
        if p != len(data):
            raise ValueError(f'layout set: read {p} of {len(data)} bytes')
        self.sprites, self.comps, self.slots = sprites, comps, slots

    # -- sprites (f): frames and composites -------------------------------------------------------------------------------
    def _box(self, frame):
        parts = self.comps[-frame - 1] if -frame - 1 < len(self.comps) else []
        if not parts:
            return 0, 0, 0, 0
        xs = [dx for _, dx, _ in parts] + [dx + self._size(f)[0] - 1 for f, dx, _ in parts]
        ys = [dy for _, _, dy in parts] + [dy + self._size(f)[1] - 1 for f, _, dy in parts]
        return min(xs), min(ys), max(xs), max(ys)

    def _size(self, frame):
        if frame >= 0:
            image = self.sprites[frame] if frame < len(self.sprites) else None
            return (image.width, image.height) if image is not None else (0, 0)
        x0, y0, x1, y1 = self._box(frame)
        return x1 - x0 + 1, y1 - y0 + 1

    def draw_frame(self, canvas, frame, x, y):
        if frame >= 0:
            if frame < len(self.sprites) and self.sprites[frame].width:
                shw_sprites.put(canvas, self.sprites[frame], x, y)
            return
        for part, dx, dy in self.comps[-frame - 1]:
            self.draw_frame(canvas, part, x + dx, y + dy)

    def _tile(self, canvas, draw, size, x, y, w, h, box=(0, 0)):
        tw, th = size
        if tw <= 0 or th <= 0 or w <= 0 or h <= 0:
            return
        layer = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        for ty in range(y, y + h, th):
            for tx in range(x, x + w, tw):
                draw(layer, tx - box[0], ty - box[1])
        clip = Image.new('L', canvas.size, 0)
        ImageDraw.Draw(clip).rectangle((x, y, x + w - 1, y + h - 1), fill=255)
        layer.putalpha(Image.composite(layer.getchannel('A'), Image.new('L', canvas.size, 0), clip))
        canvas.alpha_composite(layer)

    # -- layouts (k) ------------------------------------------------------------------------------------------------------
    def count(self, index):
        return 1 + sum(self.count(c['a']) if c['type'] & 7 == 7 else 1 for c in self.layouts[index]['children'])

    def hidden(self, index, start=1, out=None):
        out = set() if out is None else out
        for c in self.layouts[index]['children']:
            if c['type'] & 32 == 0:
                out.add(start)
            if c['type'] & 7 == 7:
                self.hidden(c['a'], start + 1, out)
            start += self.count(c['a']) if c['type'] & 7 == 7 else 1
        return out

    def rect(self, layout, index, x=0, y=0, w=W, h=H):
        """(x, y, w, h) of child `index` (0 the layout itself) placed at (x, y, w, h)."""
        out = []
        self._find(layout, index, x, y, w, h, out)
        return tuple(out)

    def _find(self, layout, index, x, y, w, h, out):
        if index == 0:
            out[:] = [x, y, w, h]
            return -1
        start = index
        index -= 1
        l = self.layouts[layout]
        dw, dh = w - l['w'], h - l['h']
        for c in l['children']:
            sub = c['type'] & 7 == 7
            if index != 0 and not sub:
                index -= 1
                continue
            x1, y1 = x + c['x1'] + ((c['ax1'] * dw) >> 12), y + c['y1'] + ((c['ay1'] * dh) >> 12)
            x2, y2 = x + c['x2'] + ((c['ax2'] * dw) >> 12), y + c['y2'] + ((c['ay2'] * dh) >> 12)
            if not sub:
                out[:] = [x1, y1, x2 - x1, y2 - y1]
                return -1
            r = self._find(c['a'], index, x1, y1, x2 - x1, y2 - y1, out)
            if r == -1:
                return -1
            index -= r
        return start - index

    def paint(self, canvas, layout, x=0, y=0, w=W, h=H, hidden=None, index=1):
        hidden = self.hidden(layout) if hidden is None else hidden
        l = self.layouts[layout]
        dw, dh = w - l['w'], h - l['h']
        draw = ImageDraw.Draw(canvas)
        for c in l['children']:
            me = index
            kind = c['type'] & 7
            index += self.count(c['a']) if kind == 7 else 1
            if me in hidden:
                continue
            x1, y1 = x + c['x1'] + ((c['ax1'] * dw) >> 12), y + c['y1'] + ((c['ay1'] * dh) >> 12)
            x2, y2 = x + c['x2'] + ((c['ax2'] * dw) >> 12), y + c['y2'] + ((c['ay2'] * dh) >> 12)
            rw, rh = x2 - x1, y2 - y1
            if kind == 0:
                slot = self.slots.get(c['a'])
                if slot is not None:
                    self._tile(canvas, lambda layer, tx, ty, s=slot: shw_sprites.put(layer, s, tx, ty), slot.size, x1, y1, rw, rh)
            elif kind == 1:
                frame = c['b']
                box = self._box(frame)[:2] if frame < 0 else (0, 0)
                self._tile(canvas, lambda layer, tx, ty, f=frame: self.draw_frame(layer, f, tx, ty), self._size(frame), x1, y1,
                           rw, rh, box)
            elif kind in (2, 3, 4):
                if rw > 0 and rh > 0:
                    draw.rectangle((x1, y1, x2 - 1, y2 - 1), fill=self.rgb(c['a']))
            elif kind == 5:
                if rw > 0 and rh > 0:
                    draw.rectangle((x1, y1, x2 - 1, y2 - 1), outline=self.rgb(c['a']))
            elif kind == 7:
                sub = self.layouts[c['a']]
                if c['type'] & 64:
                    for ix in range(0, rw, max(1, sub['w'])):
                        for iy in range(0, rh, max(1, sub['h'])):
                            self.paint(canvas, c['a'], x1 + ix, y1 + iy, sub['w'], sub['h'], hidden, me + 1)
                else:
                    self.paint(canvas, c['a'], x1, y1, rw, rh, hidden, me + 1)

    def rgb(self, index):
        value = self.colours[index] if 0 <= index < len(self.colours) else 0
        return (value >> 16) & 255, (value >> 8) & 255, value & 255, 255
