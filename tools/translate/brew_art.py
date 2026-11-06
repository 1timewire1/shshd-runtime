"""BREW SHS ('07, '08) art for the `shsbrew` addon: paper-doll portraits, location strips over their coded skies, relationship
icons and the planner's icons. Everything is rendered up front, pixel for pixel, so the runtime needs no BREW formats.

The rules come from Tardy-Slip's player and the native modules (SHS_BREW_ENGINE.md, sections 4.3-4.5, in the owner's reference
folder): a script's art ID is a frame or composite of a registered sheet, or a whole BMP; magenta is transparent; a palette swap
replaces exact colours across a whole BMP before it's cut; and a portrait is a 23-entry list of parts and palettes.

It reads the player's own game files and holds none of them.
"""
from dataclasses import dataclass
from functools import lru_cache
import io
from pathlib import Path
import struct
import sys

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

import nr_art  # noqa: E402

MAGENTA = (255, 0, 255)
STRIP_SIZE = (240, 80)
EXPRESSIONS = 5                         # the faces a line can ask for: a bank's five consecutive resources
DEFAULT_FACES = (3, 4, 12)              # a portrait's face entries, by BREW expression 2-4; any other is the default
FACES = {2: (9, 6, 14), 3: (10, 7, 15), 4: (8, 5, 13)}
ENTRIES = 23                            # a portrait list: 0-19 parts, 20-22 palettes
BASE_PART, BASE_PALETTE = 0, 22
RELATIONSHIP_ART = dict(heart=80, skull=81, smiley=82)
# Sky modes (screens.js drawSky; shs08.5.mod): (top, bottom) of the gradient. Mode -1 is night from minute 1080, else day.
SKIES = {0: (0x008AFF, 0xFFFFFF), 1: (0x000000, 0x42A2F7), 2: (0x34386C, 0xEF7351)}
SKY_BANDS = 10


def builtin_ranges():
    """The module's built-in art ranges: (first, count, image, descriptor). shs08.5.mod FUN_0001133c."""
    ranges = [(12, 31, 12, 45), (80, 3, 80, 85)]
    ranges += [(289 + 5 * k, 3, 289 + 5 * k, 395 + k) for k in range(21)]
    ranges += [(420 + 5 * k, 3, 420 + 5 * k, 416 + k) for k in range(4)]
    ranges += [(200, 9, 200, 284), (260, 7, 260, 286)]
    ranges += [(first, count, first, sheet) for first, count, sheet in ((461, 1, 492), (464, 2, 493), (468, 1, 494), (471, 2, 495),
                                                                        (475, 1, 496), (478, 1, 497), (481, 1, 498))]
    ranges += [(440 + 3 * k, 1, 440 + 3 * k, 485 + k) for k in range(7)]
    ranges += [(269, 5, 269, 287), (276, 5, 276, 288), (211, 47, 211, 285)]
    ranges += [(3001 + 3 * k, 1, 3001 + 3 * k, 3197 + k) for k in range(60)]
    return ranges


@dataclass(frozen=True)
class Sheet:
    frames: tuple       # (x, y, w, h, hotspot x, hotspot y), the hotspot relative to the frame's corner
    composites: tuple   # each a tuple of (frame, dx, dy); a negative frame -(i + 1) is composite i


def parse_sheet(data):
    """A sheet descriptor. Flag bits choose field widths; one-byte hotspots are signed (a shirt collar's 236 is 20 px below the
    face's centre), and they're stored from the sheet's corner, not the frame's."""
    position = 0

    def u8():
        nonlocal position
        position += 1
        return data[position - 1]

    def s8():
        value = u8()
        return value - 256 if value > 127 else value

    def s16():
        nonlocal position
        position += 2
        return struct.unpack_from('>h', data, position - 2)[0]
    flags = u8()
    place, size, hot, offset = (u8 if flags & 4 else s16), (u8 if flags & 2 else s16), (s8 if flags & 1 else s16), (s8 if flags & 8 else s16)
    frames = []
    for _ in range(s16()):
        x, y, w, h, hot_x, hot_y = place(), place(), size(), size(), hot(), hot()
        frames.append((x, y, w, h, hot_x - x, hot_y - y))
    for _ in range(u8()):
        position += u8()
    composites = []
    if position < len(data):
        for _ in range(u8() if flags & 8 else s16()):
            composites.append(tuple((offset(), offset(), offset()) for _ in range(u8() // 3)))
    return Sheet(tuple(frames), tuple(composites))


def swap_palette(image, palette):
    """`image` (RGB) with each of the palette's exact colours replaced: `u8 n`, then n x (from RGB, to RGB)."""
    table = {}
    for i in range(palette[0]):
        at = 1 + 6 * i
        if at + 6 > len(palette):
            break
        table[tuple(palette[at:at + 3])] = tuple(palette[at + 3:at + 6])
    if not table:
        return image
    out = image.copy()
    pixels = out.load()
    for y in range(out.height):
        for x in range(out.width):
            colour = table.get(pixels[x, y])
            if colour is not None:
                pixels[x, y] = colour
    return out


class Art:
    def __init__(self, packs, ranges=()):
        """`packs`: resources by ID, searched in order; `ranges`: a pack's own registered sheets (service 11)."""
        self.packs, self.ranges = packs, builtin_ranges() + [tuple(r) for r in ranges if r[1] > 0]
        self._images, self._sheets = {}, {}

    def resource(self, resource):
        return next((pack[resource] for pack in self.packs if resource in pack), None)

    def resolve(self, art):
        number = -(art + 1) if art < 0 else art
        for first, count, image, sheet in self.ranges:
            if first <= number < first + count:
                return ('composite' if art < 0 else 'frame'), image, sheet, number - first
        return 'image', art, None, 0

    def image(self, resource, palette=-1):
        """A BMP as RGBA, magenta clear, with a palette swap on what isn't, or None."""
        key = resource, palette
        if key not in self._images:
            data, found = self.resource(resource), None
            if data is not None and data[:2] == b'BM':
                plain = Image.open(io.BytesIO(data)).convert('RGB')
                swap = self.resource(palette) if palette >= 0 else None
                shown = swap_palette(plain, swap) if swap else plain
                found = shown.convert('RGBA')
                source, target = plain.load(), found.load()
                for y in range(found.height):
                    for x in range(found.width):
                        if source[x, y] == MAGENTA:
                            target[x, y] = (0, 0, 0, 0)
            self._images[key] = found
        return self._images[key]

    def sheet(self, descriptor):
        if descriptor not in self._sheets:
            data = self.resource(descriptor)
            self._sheets[descriptor] = parse_sheet(data) if data else None
        return self._sheets[descriptor]

    def _composite_bounds(self, sheet, index, x, y, depth=0):
        if index >= len(sheet.composites) or depth > 4:
            return None
        bounds = None
        for frame, dx, dy in sheet.composites[index]:
            if frame < 0:
                part = self._composite_bounds(sheet, -(frame + 1), x + dx, y + dy, depth + 1)
            elif frame < len(sheet.frames):
                part = x + dx, y + dy, x + dx + sheet.frames[frame][2], y + dy + sheet.frames[frame][3]
            else:
                part = None
            if part:
                bounds = part if bounds is None else (min(bounds[0], part[0]), min(bounds[1], part[1]),
                                                      max(bounds[2], part[2]), max(bounds[3], part[3]))
        return bounds

    def bounds(self, art, palette=-1):
        kind, resource, descriptor, index = self.resolve(art)
        image = self.image(resource, palette)
        if image is None:
            return None
        if kind == 'image':
            return 0, 0, image.width, image.height
        sheet = self.sheet(descriptor)
        if sheet is None:
            return None
        if kind == 'frame':
            if index >= len(sheet.frames):
                return None
            _, _, w, h, hot_x, hot_y = sheet.frames[index]
            return -hot_x, -hot_y, w - hot_x, h - hot_y
        return self._composite_bounds(sheet, index, 0, 0)

    def hotspot(self, art):
        kind, _, descriptor, index = self.resolve(art)
        sheet = self.sheet(descriptor) if kind != 'image' else None
        if sheet is None:
            return 0, 0
        if kind == 'composite':
            bounds = self._composite_bounds(sheet, index, 0, 0)
            return (bounds[0], bounds[1]) if bounds else (0, 0)
        return sheet.frames[index][4:6] if index < len(sheet.frames) else (0, 0)

    def draw(self, canvas, art, x, y, palette=-1, centre=False):
        kind, resource, descriptor, index = self.resolve(art)
        image = self.image(resource, palette)
        if image is None:
            return
        if centre:
            bounds = self.bounds(art, palette)
            if not bounds:
                return
            x -= (bounds[2] - bounds[0] >> 1) + bounds[0]
            y -= (bounds[3] - bounds[1] >> 1) + bounds[1]
        if kind == 'image':
            _paste(canvas, image, x, y)
            return
        sheet = self.sheet(descriptor)
        if sheet is None:
            return
        if kind == 'frame':
            if index < len(sheet.frames):
                fx, fy, w, h, hot_x, hot_y = sheet.frames[index]
                _paste(canvas, image.crop((fx, fy, fx + w, fy + h)), x - hot_x, y - hot_y)
            return
        self._draw_composite(canvas, image, sheet, index, x, y)

    def _draw_composite(self, canvas, image, sheet, index, x, y, depth=0):
        if index >= len(sheet.composites) or depth > 4:
            return
        for frame, dx, dy in sheet.composites[index]:
            if frame < 0:
                self._draw_composite(canvas, image, sheet, -(frame + 1), x + dx, y + dy, depth + 1)
            elif frame < len(sheet.frames):
                fx, fy, w, h, _, _ = sheet.frames[frame]
                _paste(canvas, image.crop((fx, fy, fx + w, fy + h)), x + dx, y + dy)


def _paste(canvas, image, x, y):
    layer = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
    layer.paste(image, (x, y))
    canvas.alpha_composite(layer)


def portrait_parts(expression):
    """(entry, palette entry or -1, whether it's the base) in BREW's drawing order."""
    faces = FACES.get(expression, DEFAULT_FACES)
    return ([(BASE_PART, BASE_PALETTE, True), (17, 21, False), (1, 22, False), (11, -1, False)] + [(face, -1, False) for face in faces]
            + [(16, 20, False), (18, -1, False), (19, -1, False)])


def portrait(art, entries, expression=1, size=(200, 240)):
    """A portrait on a clear canvas, its portrait point at the centre, or None for a list with no base. Uncropped, so that all of
    a look's faces stay in register."""
    entries = list(entries) + [-1] * (ENTRIES - len(entries))
    if entries[BASE_PART] == -1:
        return None
    canvas = Image.new('RGBA', size, (0, 0, 0, 0))
    x, y = size[0] // 2, size[1] // 2
    for entry, palette, base in portrait_parts(expression):
        if entries[entry] != -1:
            art.draw(canvas, entries[entry], x, y, entries[palette] if palette >= 0 else -1,
                     base and art.hotspot(entries[entry]) == (0, 0))
    return canvas


def sky(mode, size=STRIP_SIZE):
    """drawSky: ten bands from the top colour to the bottom one, over the top two thirds of the area, the rest in the last band."""
    top, bottom = SKIES[mode]
    width, height = size
    image = Image.new('RGB', size, (255, 255, 255))
    part = height * 2 // 3
    step, position = (part << 8) // SKY_BANDS, part * 256
    channel = lambda a, b, t: (a * t + b * (65536 - t)) >> 16 & 255
    for band in range(SKY_BANDS):
        t = (band << 16) // SKY_BANDS
        colour = tuple(channel(top >> shift & 255, bottom >> shift & 255, t) for shift in (16, 8, 0))
        position -= step
        image.paste(colour, (0, position >> 8, width, min(height, (position >> 8) + (step >> 8) + (1 if band else 0) + 1)))
        if band == SKY_BANDS - 2:
            step = position
    # Below the gradient: the first band drawn, the bottom colour.
    image.paste(tuple(channel(top >> shift & 255, bottom >> shift & 255, 0) for shift in (16, 8, 0)), (0, part, width, height))
    return image


def location(art, resource, mode):
    """A location's strip over its sky, opaque."""
    picture = art.image(resource)
    if picture is None:
        return None
    scene = sky(mode, picture.size).convert('RGBA')
    scene.alpha_composite(picture)
    return scene.convert('RGB')


def font_text(pack, text, sheet=2, metrics=3):
    """`text` in one of BREW's fonts: a BMP glyph sheet and its metrics (u8 space, u8 gap, s8 tracking, u16 count, u8 height, then
    (u8 character, u16 x, u16 y, u8 width) per glyph). Its characters fall back to the other case."""
    data = pack[metrics]
    space, gap, tracking = data[0], data[1], struct.unpack_from('b', data, 2)[0]
    count, height = struct.unpack_from('>H', data, 3)[0], data[5]
    glyphs = {}
    for k in range(count):
        character, x, y, width = struct.unpack_from('>BHHB', data, 6 + 6 * k)
        glyphs[chr(character)] = (x, y, width)
    art = Art([pack]).image(sheet)
    placed, x = [], 0
    for character in text:
        glyph = glyphs.get(character) or glyphs.get(character.swapcase())
        if glyph is None:
            x += space
            continue
        placed.append((glyph, x))
        x += glyph[2] + gap + tracking
    canvas = Image.new('RGBA', (max(1, x), height), (0, 0, 0, 0))
    for (left, top, width), at in placed:
        part = art.crop((left, top, left + width, top + height))
        canvas.paste(part, (at, 0), part)
    return canvas


def png(image, optimize=True):
    out = io.BytesIO()
    image.save(out, 'PNG', optimize=optimize)
    return out.getvalue()


@lru_cache(maxsize=None)
def base_pack(path):
    return nr_art.load(Path(path))
