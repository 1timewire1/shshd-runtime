"""shshd-runtime: New Rules' minigame arena (nr_arena.py) drawn from the New Rules addon's skin.

The skin (tools/translate/nr_arena_art.py, resources SKIN in the addon) is the X1i build's own art: its static screen
(layout 31 and the top band), the scrolling background tile, and an atlas of every sprite the panel draws, with the
node rectangles, the two variable-size layouts (25, the text item's box; 70, the bubble), the bitmap fonts and the
colours. This module is a port of the Java panel's paint (`class_13.method_356` case 25, X1i names) onto that skin:
it draws at the X1i's 480 x 650 game area, then scales that up by a whole number with nearest-neighbour pixels, as
the translator scales New Rules' backgrounds and portraits, so the player's last smoothing step down to the window
keeps the pixel art sharp. Its layer is the whole 3:4 frame, like the football HD layer.
Coordinates in comments and code are X1i pixels. Unverified or approximate parts are listed in docs/NEW_RULES.md.
"""
import json
import math

import pygame

from . import hd_scale
from .content import ContentError

SKIN = {'skin.json': 26174, 'static.png': 26175, 'tile.png': 26176, 'atlas.png': 26177}
FRAME_PICTURE = 26178                   # the dialogue screens' frame without its bars (addon revision 3), if present
FRAME = (768, 1024)
NATIVE = (489, 652)                     # the X1i's 480 x 650 game area, widened to exactly the frame's 3:4
OX = 4                                  # where the game area sits in it
SCREEN_WIDTH, SCREEN_HEIGHT = 480, 650     # the game area (class_6.field_325 / field_326)
# class_13.field_618: sin(0..90 degrees) x 65536, truncated, with the table's own three roundings.
SINE = tuple({30: 32768, 47: 47930, 90: 65535}.get(d, int(math.sin(math.radians(d)) * 65536)) for d in range(91))
KEYPAD = '541236'                       # field_617: the number keys around the ring (765), slot order
ITEM_FONT = 56                          # field_450 as the arena keeps it (field_229)
# class_6's boot: font 56 swaps to 59 at '~' and to the score font 61 at '`'; 61 back to 56 at ';' and to 59 at '~';
# 59 back at ';' and to 61 at '`'.
FONT_SWITCHES = ((56, '~', 59), (56, '`', 61), (61, ';', 56), (61, '~', 59), (59, ';', 56), (59, '`', 61))
ENTRANCE_MS = 2000                      # nr_arena.ENTRANCE_MS
PICTURES, PICTURE_BASE = 29, 8018       # class_6.field_161: picture IDs 0-28 are resources 8018-8046 (the icons)
HUD_BOXES = ((('hud0_label', 'hud0_label_alt', 'hud0_text'), ('hud0_item', 'hud0_item_alt')),
             (('hud1_label', 'hud1_label_alt', 'hud1_text'), ('hud1_item', 'hud1_item_alt')),
             (('hud2_label', 'hud2_label_alt', 'hud2_text'), ('hud2_item', 'hud2_item_alt')))
BUTTON_NODES = ('ok', 'second', 'left', 'right')
BUTTON_KEYS = {'ok': -5, 'second': -5, 'left': -3, 'right': -4}
ANCHORS = {-15: 'meter_frame', -7: 'second', -6: 'ok', -5: 'meter', -4: 'timer'}   # method_461
TEXT_TINT = 0x75FC84                    # the text box colour 751's tint replaces (o.a(v, ..., int)'s field_555)
UNICODE = str.maketrans({'‘': "'", '’': "'", '“': '"', '”': '"', '…': '...',
                         '–': '-', '—': '-'})


# class_6.field_154: cos(0, 2, ... 90 degrees) x 1000, for its easing curves' sine (method_179).
EASING_COS = (1000, 999, 997, 994, 990, 984, 978, 970, 961, 951, 939, 927, 913, 898, 882, 866, 848, 829, 809, 788, 766,
              743, 719, 694, 669, 642, 615, 587, 559, 529, 500, 469, 438, 406, 374, 342, 309, 275, 241, 207, 173, 139,
              104, 69, 34, 0)


def easing_sine(degrees):
    """class_6.method_179: sin(degrees) x 1000 in 2-degree steps."""
    v = (90 - degrees) % 360
    if v < 90:
        return EASING_COS[v // 2]
    if v < 180:
        return -EASING_COS[(90 - (v - 90)) // 2]
    if v < 270:
        return -EASING_COS[(v - 180) // 2]
    return EASING_COS[(90 - (v - 270)) // 2]


def eased(curve, elapsed, duration):
    """class_6.method_191's progress (0-100, some curves pass 100) `elapsed` ms into a track of `duration`."""
    if curve == 1:
        return easing_sine(elapsed * 90 // duration) // 10
    if curve == 3:
        return 100 - easing_sine(90 - elapsed * 90 // duration) // 10
    if curve == 5:                                      # past the end by 5%, then back
        t = elapsed * 100 // duration
        return t * 1166 // 1000 if t < 90 else t * -500 // 1000 + 150
    if curve == 6:                                      # straight there by 90%, then a dip and back
        t = elapsed * 100 // duration
        return t * 100 // 90 if t < 90 else 100 - easing_sine((t - 90) * 10 * 180 // 100) * 10 // 1000
    return elapsed * 100 // duration


def sine(degrees):
    """class_13.method_430."""
    degrees %= 360
    negative = degrees >= 180
    if negative:
        degrees -= 180
    if degrees > 90:
        degrees = 180 - degrees
    return -SINE[degrees] if negative else SINE[degrees]


def rgb(colour):
    return colour >> 16 & 255, colour >> 8 & 255, colour & 255


def jdiv(a, b):
    """Java's integer division (towards zero)."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


class NRFont:
    """New Rules' bitmap font (`t`, class_3): glyph advance = width + extra, `track` pixels between characters, a
    character the font lacks borrows its other case, and one it still lacks takes no room. `switches` (method_87):
    characters that swap to another font for what follows and, from it, back (` for the score font, ~ for 59)."""

    def __init__(self, spec, glyphs):
        self.space, self.gap, self.track, self.height = spec['space'], spec['gap'], spec['track'], spec['height']
        self.extra = spec['extra']
        self.glyphs = glyphs
        self.switches = {}

    def switch(self, ch, font):
        self.switches[ch] = font
        self.height = max(self.height, font.height)

    def glyph(self, ch):
        code = ord(ch)
        image = self.glyphs.get(code)
        if image is None and 65 <= code < 256 and len(ch.swapcase()) == 1:
            image = self.glyphs.get(ord(ch.swapcase()))
        return image

    def advance(self, ch):
        if ch == ' ':
            return self.space
        image = self.glyph(ch)
        return image.get_width() + self.extra if image is not None else -self.track

    def cells(self, text):
        """The text as (character, font) pairs: the switches taken (they take no room and are not drawn)."""
        current, cells = self, []
        for ch in text.translate(UNICODE):
            if ch in self.switches:
                current = self.switches[ch] if current is self else self
            else:
                cells.append((ch, current))
        return cells

    @staticmethod
    def line_width(cells):
        if not cells:
            return 0
        return max(0, sum(font.advance(ch) + font.track for ch, font in cells) - cells[-1][1].track)

    def width(self, text):
        """method_90: the widest line."""
        return max((self.line_width(line) for line in self.lines(text)), default=0)

    def lines(self, text, width=1 << 30):
        """method_98's breaking, as lists of cells: leading spaces dropped, a line broken at its last space before
        it would pass `width` (at that character when it has none), and at '\n'."""
        cells = self.cells(text) if isinstance(text, str) else text
        result, i, n = [], 0, len(cells)
        while i < n:
            while i < n and cells[i][0] == ' ':
                i += 1
            if i >= n:
                break
            start, x, end = i, 0, n
            while i < n:
                ch, font = cells[i]
                if ch == '\n':
                    end, i = i, i + 1
                    break
                advance = font.advance(ch)
                if x + advance > width:
                    j = i
                    while j > start and cells[j][0] != ' ':
                        j -= 1
                    end = j if j > start else max(i, start + 1)
                    i = end
                    break
                x += advance + font.track
                i += 1
            result.append(cells[start:end])
        return result

    def block_height(self, count):
        return count * (self.height + self.gap) - self.gap if count else 0

    def draw_line(self, target, line, x, y):
        for ch, font in (self.cells(line) if isinstance(line, str) else line):
            image = font.glyph(ch) if ch != ' ' else None
            if image is not None:
                target.blit(image, (x, y))
            x += font.advance(ch) + font.track

    def draw(self, target, text, x, y, width=1 << 30, align=1):
        """method_97: lines within [x, x + width], 1 left, 2 right, 3 centred. Returns the height drawn."""
        lines = self.lines(text, width)
        for line in lines:
            line_width = self.line_width(line)
            left = x + width - line_width if align == 2 else (2 * x + width - line_width) // 2 if align == 3 else x
            self.draw_line(target, line, left, y)
            y += self.height + self.gap
        return self.block_height(len(lines))

    def draw_box(self, target, text, rect, flags):
        """method_96: `flags` & 3 the horizontal alignment (2 centred, 3 right), & 12 the vertical (8 centred, 12
        bottom), & 16 wraps at the box's width."""
        x, y, w, h = rect
        if flags & 16:
            height = self.block_height(len(self.lines(text, w)))
            width = w
        else:
            height = self.block_height(len(self.lines(text)))
            width = self.width(text)
        align = 1
        if flags & 3 == 2:
            align, x = 3, x + (w + 1 - width) // 2
        elif flags & 3 == 3:
            align, x = 2, x + w - width
        if flags & 12 == 8:
            y += (h + 1 - height) // 2
        elif flags & 12 == 12:
            y += h - height
        self.draw(target, text, x, y, width, align)


class Skin:
    def __init__(self, files):
        self.spec = json.loads(files['skin.json'])
        if self.spec.get('format') != 'shshd-nr-arena-skin' or self.spec.get('version') != 1:
            raise ValueError('Unsupported New Rules arena skin')
        self.static = self._image(files['static.png'])
        self.tile = self._image(files['tile.png'])
        # The whole frame's picture, which the arena stands on in place of its scrolling tile and stripe (the static
        # screen then leaves its stripe out), so the stripe and pattern match the dialogue screens'.
        self.frame = self._image(files['frame.png']) if files.get('frame.png') else None
        atlas = self._image(files['atlas.png'])
        self.sprites = {name: (atlas.subsurface(pygame.Rect(sprite['rect'])), tuple(sprite['offset']))
                        for name, sprite in self.spec['sprites'].items()}
        self.nodes = {name: pygame.Rect(rect).move(OX, 0) for name, rect in self.spec['nodes'].items()}
        self.layouts = {int(k): v for k, v in self.spec['layouts'].items()}
        self.colors = self.spec['colors']
        self.fonts = {}
        for resource, spec in self.spec['fonts'].items():
            prefix = f'font/{resource}/'
            glyphs = {int(name[len(prefix):]): image for name, (image, _) in self.sprites.items()
                      if name.startswith(prefix)}
            self.fonts[int(resource)] = NRFont(spec, glyphs)
        for resource, ch, other in FONT_SWITCHES:
            if resource in self.fonts and other in self.fonts:
                self.fonts[resource].switch(ch, self.fonts[other])

    @staticmethod
    def _image(data):
        from io import BytesIO
        return pygame.image.load(BytesIO(data), 'skin.png').convert_alpha()

    def blit(self, target, name, x, y, origin=True):
        """A frame or composite: at its origin (`method_109(..., true)`), or with its top left at (x, y)."""
        found = self.sprites.get(name)
        if found is None:
            return None
        image, (dx, dy) = found
        target.blit(image, (x + dx, y + dy) if origin else (x, y))
        return image

    def size(self, name):
        found = self.sprites.get(name)
        return found[0].get_size() if found else (0, 0)

    def layout(self, target, layout_id, rect, replace=None):
        """A layout drawn into `rect` (class_0.method_14): visible nodes (flag 16), images tiled (from the right with
        flag 64, the bottom with 128), colour fills, outlines and nested layouts."""
        layout = self.layouts[layout_id]
        design_w, design_h = layout['size']
        x0, y0, w, h = rect
        dx, dy = w - design_w, h - design_h
        for node in layout['nodes']:
            if not node['flags'] & 16:
                continue
            base, rel = node['base'], node['relative']
            x1, y1 = x0 + base[0] + (dx * rel[0] >> 12), y0 + base[1] + (dy * rel[1] >> 12)
            x2, y2 = x0 + base[2] + (dx * rel[2] >> 12), y0 + base[3] + (dy * rel[3] >> 12)
            child = pygame.Rect(x1, y1, x2 - x1, y2 - y1)
            if child.width <= 0 or child.height <= 0:
                continue
            kind, payload = node['kind'], node['payload']
            if kind == 1:
                found = self.sprites.get(f'slot/{payload[0]}/{payload[1]}')
                if found is not None:
                    self.tile_rect(target, found[0], child, bool(node['flags'] & 64), bool(node['flags'] & 128))
            elif kind in (2, 3, 4, 5):
                colour = self.colors[payload[0]]
                if replace is not None and colour == replace[0]:
                    colour = replace[1]
                if kind == 5:
                    pygame.draw.rect(target, rgb(colour), child, 1)
                else:
                    target.fill(rgb(colour), child)
            elif kind == 7:
                self.layout(target, payload[0], child, replace)

    @staticmethod
    def tile_rect(target, image, rect, from_right=False, from_bottom=False):
        """class_4.method_106: an image repeated over a rectangle, clipped to it."""
        iw, ih = image.get_size()
        if iw <= 0 or ih <= 0:
            return
        clip = target.get_clip()
        target.set_clip(rect.clip(clip) if clip else rect)
        xs = range(rect.right - iw, rect.x - iw, -iw) if from_right else range(rect.x, rect.right, iw)
        ys = range(rect.bottom - ih, rect.y - ih, -ih) if from_bottom else range(rect.y, rect.bottom, ih)
        for y in ys:
            for x in xs:
                target.blit(image, (x, y))
        target.set_clip(clip)


class NRArenaRenderer:
    frame_units = (384, 512)            # the frame's shape in layout units (Desktop sets it)

    def __init__(self, resources):
        self.resources = resources
        self.native = pygame.Surface(NATIVE).convert()
        self.layer = pygame.Surface(NATIVE, pygame.SRCALPHA)     # the arena over the frame's picture
        self._frame_scaled = None                               # (size, the frame's picture at that size)
        self._layer_scaled = None                               # the arena's layer at the canvas's size, kept
        self.target_height = FRAME[1]       # the frame's height in the window (Desktop sets it): the scale to reach
        self.canvas = pygame.Surface((NATIVE[0] * 2, NATIVE[1] * 2)).convert()
        self.hd_layer = True
        self.edge_bar = 'bar'               # the gear on its bar, as on the story's screens (owner, 2026-10-31)
        self.menu_focus = None            # (the action, the focused option) on New Rules' menu
        self._skin = None
        self.targets = []                 # (native rect, command) for clicks, from the last frame

    def band_picture(self):
        """What a taller frame shows above the arena (Desktop._draw_picture_band, owner 2026-11-11): the frame's
        picture it stands on (New Rules' backdrop without the bars), lengthened; None without one (an older addon)."""
        try:
            return self.skin().frame
        except (ContentError, KeyError, ValueError, pygame.error):
            return None

    # -- assets -----------------------------------------------------------------------------------------------------
    def skin(self):
        if self._skin is None:
            files = {name: self.resources.raw_asset(resource) for name, resource in SKIN.items()}
            if self.resources.exists(FRAME_PICTURE):
                files['frame.png'] = self.resources.raw_asset(FRAME_PICTURE)
            self._skin = Skin(files)
        return self._skin

    def available(self):
        try:
            return all(self.resources.exists(resource) for resource in SKIN.values())
        except (AttributeError, KeyError):
            return False

    # -- geometry (class_13) ----------------------------------------------------------------------------------------
    def _field(self, arena):
        """field_557: the ring's rectangle, the field node narrowed by an item's width (field_598)."""
        skin = self.skin()
        field = pygame.Rect(skin.nodes['wide' if arena.wide else 'field'])
        if arena.margins:                               # method_431 with field_597
            left = max(field.x - OX, 15)
            field.width = min(field.width, SCREEN_WIDTH - 30)
            field.x = left + OX
        item_width, self.item_height = self._item_size(arena)
        ring = pygame.Rect(field.x + (item_width >> 1), field.y, field.width - item_width, field.height)
        if arena.wide:
            meter = skin.nodes['meter']
            ring.width = field.width - 2 * meter.width
            ring.x = OX + (SCREEN_WIDTH - ring.width) // 2
        return ring

    def _item_size(self, arena):
        """method_456's field_598 / field_599 for the ring's item kind."""
        if arena.item_kind == 1:
            return 62, 70
        if arena.item_kind == 2:
            return 61, 31
        font = self.font(ITEM_FONT)
        widest = max((font.width(arena.strings[item]) for item in arena.slots
                      if 0 <= item < len(arena.strings)), default=0)
        return widest + 8, font.height + 5

    def _ring_x(self, ring, angle, size):
        w = size * size * ring.width // 10000                     # method_439 (field_570 x the size given)
        return ring.x + (ring.width - w >> 1) + (((w // 2) << 8) + (sine(angle + 90) >> 8) * (w // 2) >> 8)

    def _ring_y(self, ring, angle, size):
        h = size * size * ring.height // 10000                    # method_440
        return ring.y + (ring.height - h >> 1) + self._depth(angle, h)

    @staticmethod
    def _depth(angle, h):
        return ((h // 2) << 8) + (sine(angle) >> 8) * (h // 2) >> 8          # method_437

    def _row_y(self, arena, ring, y, slot, size=None):
        """method_441: the wide layout puts slots 2-4 on a back row and the rest on a front one."""
        if arena.wide:
            return self._ring_y(ring, 240 if 2 <= slot <= 4 else 60, arena.ring_size if size is None else size)
        return y

    def _slot_point(self, arena, ring, slot, angle=None, vertical=1):
        """method_462 for a slot: its x, and its y moved up by the item's height (vertical 0: half, 2: whole)."""
        count = len(arena.slots)
        turn = arena.angle if angle is None else angle
        a = (turn + 90 + slot * (360 // count)) % 360
        x = self._ring_x(ring, a, arena.ring_size)
        y = self._row_y(arena, ring, self._ring_y(ring, a, arena.ring_size), slot)
        if arena.plates:
            y -= 6
        height = self.item_height
        if arena.item_kind == 2 and 0 <= slot < count:
            size = self._picture(arena.slots[slot])
            height = size[1] if size else 31
        if vertical == 0:
            y -= height >> 1
        elif vertical == 2:
            y -= height
        return x, y

    def _anchor(self, arena, anchor):
        """method_461: a layout rectangle a popup flies to or sits on."""
        skin = self.skin()
        if anchor in ANCHORS:
            return skin.nodes[ANCHORS[anchor]]
        if -3 <= anchor <= -1:
            box = -1 - anchor
            labels, items = HUD_BOXES[box]
            variant = arena.hud[box][2]
            if variant in (1, 2):
                return skin.nodes[items[variant - 1]]
            return skin.nodes[labels[min(variant, 2)]]
        return pygame.Rect(OX, 0, SCREEN_WIDTH, SCREEN_HEIGHT)

    def _point(self, arena, ring, place, vertical=1, x_from=0, y_from=0):
        """method_462: a slot's point, or an anchor's (its centre, its bottom with vertical 1)."""
        if place >= 0:
            return self._slot_point(arena, ring, place, vertical=vertical)
        if place == -13:
            return x_from, y_from - 36
        if place == -12:
            return x_from, 0
        if place == -11:
            return x_from, SCREEN_HEIGHT - 22
        rect = self._anchor(arena, place)
        y = rect.y + (rect.height if vertical == 1 else rect.height // 2 if vertical == 0 else 0)
        return rect.x + rect.width // 2, y

    # -- drawing ----------------------------------------------------------------------------------------------------
    def font(self, resource):
        return self.skin().fonts[resource]

    def _picture(self, picture):
        """A picture ID's icon size (class_6.method_183: 0-28 are 8018-8046), or None."""
        name = self._picture_name(picture)
        return self.skin().size(name) if name in self.skin().sprites else None

    @staticmethod
    def _picture_name(picture):
        if 0 <= picture < PICTURES:
            return f'icon/{picture}'
        if PICTURE_BASE <= picture < PICTURE_BASE + PICTURES:
            return f'icon/{picture - PICTURE_BASE}'
        return None

    def draw(self, target, session, now_ms=None, overlay=True):
        """The arena into `canvas`; with `overlay` False, without New Rules' menu over it (the player shows SHS's
        choice there instead)."""
        arena = session.engine.nr_arena
        action = session.pending
        now = pygame.time.get_ticks() if now_ms is None else now_ms
        skin = self.skin()
        self.targets = []
        moving = arena is not None and (arena.entering or arena.leaving)
        if skin.frame is not None:
            surface = self.layer
            surface.fill((0, 0, 0, 0))
        else:
            # method_358: the background tile, scrolling a pixel each 100 ms over its 128.
            surface = self.native
            step = now // 100 % 128
            Skin.tile_rect(surface, skin.tile, pygame.Rect(-(128 - step), -step, NATIVE[0] + 256, NATIVE[1] + 256))
        # The table and the bands run on past New Rules' 480 x 650 screen to the frame's edges (its few columns either
        # side, and the base's added row: nr_arena_art._extend_base), rather than stopping short of them.
        if moving and arena.leaving:
            # Leaving is transition -4 run backwards: the entrance's tracks from their end, the table on curve 1.
            self._entrance(surface, ENTRANCE_MS - arena.exit_ms, table_curve=1)
        elif moving:
            self._entrance(surface, arena.entrance_ms)
        elif arena is not None:
            # With the panel closed (the library waits a frame or two after its exit) only the frame shows: the
            # exit took the rest away, and that picture fades out over the next screen (owner, 2026-10-31).
            origin = skin.spec.get('static_origin', (0, 0))
            surface.blit(skin.static, (OX + origin[0], origin[1]))
        if arena is not None and not moving:
            self._paint(surface, arena, session, now)
        if action is not None and action.name in ('arena_menu', 'arena_info') and overlay:
            self.targets = []                           # the menu or box takes the clicks, not the arena under it
            self._overlay(surface, action, now)
        k = max(1, -(-self.target_height // NATIVE[1]))          # the smallest whole scale that reaches the window
        size = (NATIVE[0] * k, NATIVE[1] * k)
        direct = hd_scale.S == 1
        if direct:
            # A phone can't afford a second pass over every pixel each frame, on clocks that drop once a frame misses
            # its budget (a g54 held 20 fps): one pass straight to the frame's size, a touch softer, at 60.
            height = max(4, round(max(FRAME[1], self.target_height) / 4) * 4)
            size = (height * 3 // 4, height)
        if self.canvas.get_size() != size:
            self.canvas = pygame.Surface(size).convert()
        if skin.frame is None:
            if direct:
                pygame.transform.smoothscale(surface, size, self.canvas)
            else:
                pygame.transform.scale(surface, size, self.canvas)
            return []
        # The frame's picture is drawn over the whole 3:4 frame as the dialogue screens draw it; the arena's pixel art
        # goes over it, scaled whole as above. In a taller frame the picture runs on above the arena (the player's
        # band): the arena takes the bottom of the same lengthened picture (backdrop_fit.extend), so the picture's
        # shaded top shows once, at the frame's top, not again over the arena's bar (owner, 2026-11-11).
        if self._frame_scaled is None or self._frame_scaled[0] != (size, self.frame_units):
            picture = skin.frame
            wide, tall = self.frame_units
            if (wide, tall) != (384, 512):
                from .backdrop_fit import extend
                long = extend(picture, round(picture.get_height() * tall / (wide * 4 / 3)))
                picture = long.subsurface((0, long.get_height() - picture.get_height(), *picture.get_size()))
            self._frame_scaled = ((size, self.frame_units), pygame.transform.smoothscale(picture, size))
        self.canvas.blit(self._frame_scaled[1], (0, 0))
        if self._layer_scaled is None or self._layer_scaled.get_size() != size:
            self._layer_scaled = pygame.Surface(size, pygame.SRCALPHA, surface)
        if direct:
            # Premultiplied, or the faint edges of sprites come out at full colour (the notes' sparks went pink).
            pygame.transform.smoothscale(surface.premul_alpha(), size, self._layer_scaled)
            self.canvas.blit(self._layer_scaled, (0, 0), special_flags=pygame.BLEND_PREMULTIPLIED)
        else:
            pygame.transform.scale(surface, size, self._layer_scaled)
            self.canvas.blit(self._layer_scaled, (0, 0))
        return []

    def _entrance(self, surface, ms, table_curve=6):
        """New Rules' entrance (class_13.method_383, transition -3; class_6.method_191 draws its tracks) over the frame:
        the bottom band, with the stand, rises from below the screen and the top band drops from above it (0-800 ms,
        settling past 100%); the table, three times as wide and reaching the screen's bottom, comes down to its own
        size (400-1600 ms). Each is its layout redrawn in the moving box, so the pictures tile rather than stretch.
        The exit (transition -4) draws the same tracks with `ms` running back from the end."""
        skin = self.skin()
        nodes = {name: pygame.Rect(skin.nodes[name]) for name in ('bottom_band', 'band', 'table')}
        duration = ENTRANCE_MS * 2 // 5
        for layout_id, name, offset in (
                (67, 'bottom_band', (nodes['bottom_band'].bottom * 100 // nodes['bottom_band'].height)),
                (66, 'band', jdiv(-(nodes['band'].bottom * 100 // nodes['band'].height) * 11, 10))):
            box = nodes[name]
            if ms >= duration:
                progress = 100
            else:
                progress = eased(5, ms, duration)
            box.y += jdiv((100 - progress) * box.height * offset, 10000)
            skin.layout(surface, layout_id, box)
        start, end = ENTRANCE_MS // 5, ENTRANCE_MS * 4 // 5
        if ms >= start:
            box = nodes['table']
            progress = 100 if ms >= end else eased(table_curve, ms - start, end - start)
            tall = (SCREEN_HEIGHT - box.y + box.height // 2) * 100 // box.height
            width = box.width * (300 + jdiv((100 - 300) * progress, 100)) // 100
            height = box.height * (tall + jdiv((100 - tall) * progress, 100)) // 100
            box.x += (box.width - width) // 2
            box.width, box.height = width, height
            skin.layout(surface, 11, box)

    def _paint(self, surface, arena, session, now):
        self._hud(surface, arena, session, 0, now)
        if arena.score_display:
            self._score(surface, arena)
        if arena.timer_shown:
            self._timer(surface, arena)
        ring = self._field(arena)
        self._buttons(surface, arena)
        if arena.keypad:
            self._keypad(surface, arena, ring)
        count = len(arena.slots)
        self._ring(surface, arena, ring, 0, count // 2)
        self._hud(surface, arena, session, 1, now)
        self._ring(surface, arena, ring, count // 2, count)
        self._hud(surface, arena, session, 2, now)
        self._popups(surface, arena, ring)
        for bubble in arena.bubbles:
            if bubble is not None and bubble[0]:
                self._bubble(surface, arena, ring, bubble[0], bubble[2], bubble[1], now)

    def _hud(self, surface, arena, session, box, now):
        """method_447: a HUD box's item (portrait, picture or text) and its label or flashing message."""
        skin = self.skin()
        item_id, kind, variant = arena.hud[box][0], arena.hud[box][1], arena.hud[box][2]
        labels, items = HUD_BOXES[box]
        if variant in (1, 2):
            hidden = arena.hud[box][5] & 1 and now // 350 % 2 == 0
            rect = pygame.Rect(skin.nodes[items[variant - 1]])
            if not hidden and item_id != -1:
                if kind == 2:
                    rect.y, rect.height = rect.bottom - 74, 74
                    name = self._picture_name(item_id)
                    if name is not None:
                        w, h = skin.size(name)
                        skin.blit(surface, name, rect.x + (rect.width - w) // 2, rect.y + (rect.height - h) // 2,
                                  origin=False)
                elif kind == 3:
                    text = self._text(session, item_id)
                    if text:
                        self.font(self.skin().spec['score_font']).draw_box(surface, text, rect, 26)
                # kind 1, a portrait: New Rules' paper dolls come with the addon's portraits (not yet).
        rect = pygame.Rect(skin.nodes[labels[min(variant, 2)]])
        if box == 2:
            rect.x, rect.width = OX, SCREEN_WIDTH
        text = arena.labels[box]
        flash = arena.labels[box + 3]
        if flash is not None and arena.flash_ms[box] > 0:
            text = flash if arena.flash_ms[box] // 350 % 2 else None
        if text:
            rect.height = min(rect.height, SCREEN_HEIGHT - rect.y)
            clip = surface.get_clip()
            surface.set_clip(rect)
            self.font(ITEM_FONT).draw_box(surface, text, rect, 26)
            surface.set_clip(clip)

    @staticmethod
    def _text(session, string_id):
        try:
            return session.engine.resolve_text(session.vm, string_id)
        except Exception:                               # a string the library has since dropped
            return None

    def _score(self, surface, arena):
        """The score dial (layout 34 at the band's node 20): the meter's fill, the markers and the score."""
        skin = self.skin()
        rect = skin.nodes['meter_frame']
        x, y = rect.topleft
        skin.layout(surface, 34, rect)
        face = self._layout_node(34, rect, 2)
        w, h = skin.size('dial/0')
        skin.blit(surface, 'dial/0', face.x + (face.width - w) // 2, face.y + (face.height - h) // 2, origin=False)
        meter, target, second = arena.meter, arena.target_marker, arena.second_marker
        if meter >= 0:
            step = meter
            if meter >= 9:
                kind, step = 1, 9
            elif meter >= target:
                kind = 1
            elif meter >= second and second != -2:
                kind = 4
            else:
                kind = 2
            skin.blit(surface, f'meter/{kind}/{step}', x, y)
        markers_x, markers_y = skin.spec['markers']
        if 0 <= second < len(markers_x) and meter < second:
            skin.blit(surface, 'group/4/4', x + markers_x[second], y + markers_y[second])
        if 0 <= target < len(markers_x) and meter < target:
            skin.blit(surface, 'group/4/3', x + markers_x[target], y + markers_y[target])
        if meter >= 9:
            skin.blit(surface, f'meter/3/{arena.max_ms % 2000 * 10 // 2000}', x, y)
        if arena.score_display == 1 or (arena.score_display == 2 and arena.blink_clock_ms // 500 % 2 == 1):
            self.font(skin.spec['score_font']).draw_box(surface, str(arena.score), rect, 10)

    def _timer(self, surface, arena):
        """The timer dial (layout 33 at the band's node 16) and its 17-step pie (method_364)."""
        skin = self.skin()
        rect = skin.nodes['timer']
        face = self._layout_node(33, rect, 2)
        w, h = skin.size('dial/1')
        skin.blit(surface, 'dial/1', face.x + (face.width - w) // 2, face.y + (face.height - h) // 2, origin=False)
        total = arena.timer_total_ms
        if total > 0:
            step = min(max(0, ((total - max(0, arena.timer_ms)) << 4) // total), 16)
            skin.blit(surface, f'timer/{step}', rect.x, rect.y)

    def _layout_node(self, layout_id, rect, index):
        layout = self.skin().layouts[layout_id]
        node = layout['nodes'][index - 1]
        dx, dy = rect.width - layout['size'][0], rect.height - layout['size'][1]
        base, rel = node['base'], node['relative']
        x1, y1 = rect.x + base[0] + (dx * rel[0] >> 12), rect.y + base[1] + (dy * rel[1] >> 12)
        x2, y2 = rect.x + base[2] + (dx * rel[2] >> 12), rect.y + base[3] + (dy * rel[3] >> 12)
        return pygame.Rect(x1, y1, x2 - x1, y2 - y1)

    def _buttons(self, surface, arena):
        """The four on-screen buttons (OK, the second, left, right): the state's colour under each picture, then
        the alternate style's hint while one is pressed."""
        skin = self.skin()
        colours = skin.spec['buttons']
        hint = False
        for i, name in enumerate(BUTTON_NODES):
            if not arena.buttons & (2 << i):
                continue
            state = -1
            if arena.button_ms[i] != -1:
                state = arena.feedback if i in (0, 1) else 0
            if state == 1:
                colour = colours['right']
            elif state == 2:
                colour = colours['wrong']
            elif arena.buttons & 1:
                colour = colours['alternate']
            else:
                colour = colours['pressed' if state == 0 else 'idle']
            rect = skin.nodes[name]
            surface.fill(rgb(colour), rect)
            skin.blit(surface, f'button/{name}', rect.x, rect.y, origin=False)
            self.targets.append((pygame.Rect(rect), ('arena_key', BUTTON_KEYS[name])))
            if arena.buttons & 1 and state == 0 and not any(arena.bubbles):
                hint = True
        if hint:
            rect = skin.nodes['hint']
            skin.blit(surface, 'frame/4/22', rect.x, rect.y, origin=False)

    def _keypad(self, surface, arena, ring):
        """765: the number keys 1-6 around the ring (their slots' places at full size), 766's key flashing."""
        count = len(arena.slots) or 1
        score_font = self.font(self.skin().spec['score_font'])
        for i, ch in enumerate(KEYPAD):
            a = (arena.angle + 90 + i * (360 // count)) % 360
            x = self._ring_x(ring, a, 100)
            y = self._row_y(arena, ring, self._ring_y(ring, a, 100), i, 100)
            if 2 <= i <= 4:
                y -= self.item_height + score_font.height
            font = score_font if arena.keypad_flash_ms > 0 and arena.keypad_flash == i else self.font(ITEM_FONT)
            font.draw_line(surface, ch, x - font.advance(ch), y)
            self.targets.append((pygame.Rect(x - 24, y - 12, 48, 48), ('arena_key', 48 + int(ch))))

    def _ring(self, surface, arena, ring, start, stop):
        """method_450: the ring's items from the back (opposite the selector) towards the front."""
        count = len(arena.slots)
        if not count:
            return
        back = (arena.under + count // 2) % count
        for k in range(start, stop):
            offset = (k + 1) >> 1
            slot = (back + (-offset if k & 1 == 0 else offset)) % count
            if arena.blink[slot] == 1 and arena.blink_clock_ms // 500 % 2 == 1:
                continue
            a = (arena.angle + 90 + slot * (360 // count)) % 360
            plate = -1
            move = arena.moves[slot]
            x, y = self._ring_x(ring, a, arena.ring_size), self._ring_y(ring, a, arena.ring_size)
            if move is not None and move[3] > 0:
                source, angle, elapsed, total = move
                fx, fy = self._slot_point(arena, ring, source, angle=angle) if 0 <= source < count else (x, y)
                fy -= self.item_height // 2
                x = fx + jdiv((x - fx) * elapsed, total)
                y = fy + jdiv((y - fy) * elapsed, total)
            elif arena.plates:
                h = arena.ring_size * ring.height // 100
                if h > 0:
                    plate = 1 - 2 * self._depth(a, h) // h
            y = self._row_y(arena, ring, y, slot)
            self._item(surface, arena, arena.slots[slot], arena.item_kind, x, y, plate, arena.tint[slot])
            if arena.keypad and slot < len(KEYPAD) and arena.slots[slot] != -1:
                # shshd-runtime (owner, 2026-10-31): with the number keys around the ring (Sequences), a click on an
                # item presses its slot's key, so the items are picked by touch rather than by their numbers.
                width, height = self._item_size(arena)
                name = self._picture_name(arena.slots[slot]) if arena.item_kind == 2 else None
                if name is not None:
                    width, height = map(max, (width, height), self.skin().size(name))     # the whole picture
                self.targets.append((pygame.Rect(x - width // 2, y - height, width, height),
                                     ('arena_key', 48 + int(KEYPAD[slot]))))

    def _item(self, surface, arena, item, kind, x, y, plate, tint):
        """method_444: an item standing at (x, y): its plate (0 or 1, the meter pack's first sequence), then a
        picture's bottom centre or a text item's box."""
        if item == -1:
            return
        skin = self.skin()
        if kind == 2:
            if plate >= 0:
                skin.blit(surface, f'meter/0/{plate}', x, y)
                y -= 6
            name = self._picture_name(item)
            if name is not None:
                w, h = skin.size(name)
                skin.blit(surface, name, x - w // 2, y - h, origin=False)
        elif kind == 3:
            if not 0 <= item < len(arena.strings):
                return
            text = arena.strings[item]
            font = self.font(ITEM_FONT)
            width = font.width(text)
            box_width = max(0, width)
            top = y - 2 - font.height
            box_top = top - 2
            if plate >= 0:
                skin.blit(surface, f'meter/0/{plate}', x, y)
                box_top -= 6
                top -= 6
            skin.layout(surface, 25, pygame.Rect(x - box_width // 2 - 4, box_top, box_width + 8, font.height + 5),
                        replace=(TEXT_TINT, tint) if tint != -1 else None)
            font.draw(surface, text, x - width // 2, top)
        # kind 1, portraits: with the addon's portraits (not yet).

    def _popups(self, surface, arena, ring):
        """The popups (field_569): text and item copies flying from a slot to an anchor, pictures on a slot or in
        an anchor's row. Their ends are worked out each frame from where the slot is now."""
        count = len(arena.slots)
        for popup in arena.popups:
            if popup.kind == 3 and popup.count > 0:
                rect = self._anchor(arena, popup.source)
                step = rect.width // popup.count
                x, y = rect.x + step * popup.index + step // 2, rect.y + rect.height // 2
            elif popup.kind == 3:
                if not 0 <= popup.source < count:
                    continue
                x, y = self._slot_point(arena, ring, popup.source, vertical=0)
            else:
                sx, sy = self._point(arena, ring, popup.source) if popup.source != -32768 else (0, 0)
                sy -= self.item_height // 2
                tx, ty = self._point(arena, ring, popup.target, x_from=sx, y_from=sy)
                ty -= self.item_height // 2
                progress = 100 * popup.elapsed_ms // popup.duration_ms if popup.duration_ms > 0 else 0
                x, y = sx + (tx - sx) * progress // 100, sy + (ty - sy) * progress // 100
            if popup.kind == 1:
                if 0 <= popup.value < len(arena.strings):
                    font = self.font(ITEM_FONT)
                    text = arena.strings[popup.value]
                    font.draw(surface, text, x, y - font.height, font.width(text), 3)
            elif popup.kind == 3:
                name = self._picture_name(popup.value)
                if name is not None:
                    w, h = self.skin().size(name)
                    self.skin().blit(surface, name, x - w // 2, y - h // 2, origin=False)
            else:
                self._item(surface, arena, popup.value, arena.item_kind, x, y, -1, popup.tint)

    def _bubble(self, surface, arena, ring, text, slot, flags, now):
        """method_449: a bubble (layout 70) centred, or by a slot or a layout anchor (flags 1: method_462, as for a
        popup's ends) below it, above it with 2, and with 4 a pointer at it."""
        font = self.font(ITEM_FONT)
        width = min(SCREEN_WIDTH - 36 - 30, 340)
        lines = font.lines(text, width)
        height = font.block_height(len(lines)) + 33
        box_width = max((font.line_width(line) for line in lines), default=0) + 30
        x = OX + (SCREEN_WIDTH - box_width) // 2
        y = (SCREEN_HEIGHT - height) // 2
        pointer, above = bool(flags & 4), bool(flags & 2)
        slot_x = 0
        if flags & 1 and (slot < 0 or slot < len(arena.slots)):
            gap = 6 + (34 - (4 if above else 0) if pointer else 0)
            slot_x, slot_y = self._point(arena, ring, slot, vertical=2 if above else 1)
            y = slot_y - height - gap if above else slot_y + gap
            if pointer:
                if slot_x - 18 < x + 24:
                    x = slot_x - 18 - 24
                elif slot_x + 18 > x + box_width - 24:
                    x = slot_x + 18 + 24 - box_width
        self.skin().layout(surface, 70, pygame.Rect(x, y, box_width, height))
        font.draw(surface, text, x + 15, y + 17, box_width - 30)
        if pointer and flags & 1:
            self.skin().blit(surface, f'pointer/{0 if above else 1}/{now // 250 % 4}', slot_x - 39,
                             y + height - 4 if above else y)

    def _overlay(self, surface, action, now):
        """New Rules' menu (9) and info box (10) over the arena. Approximate (docs/NEW_RULES.md): the bubble's box and
        the item font, as the emulator shows them; the Java draws them with its own dialog layouts."""
        font = self.font(ITEM_FONT)
        width = 340
        details = action.details
        title = details.get('title') if action.name == 'arena_menu' else details.get('text')
        lines = font.lines(title or '', width)
        options = details.get('options', []) if action.name == 'arena_menu' else []
        row = font.height + font.gap                       # method_88
        height = font.block_height(len(lines)) + 33 + (len(options) * row + 8 if options else 0)
        box_width = width + 30
        x, y = OX + (SCREEN_WIDTH - box_width) // 2, (SCREEN_HEIGHT - height) // 2
        self.skin().layout(surface, 70, pygame.Rect(x, y, box_width, height))
        font.draw(surface, title or '', x + 15, y + 17, width, 3)
        top = y + 17 + font.block_height(len(lines)) + 8
        focus = self.focus(action)
        panel = self.skin().colors[3]
        if options:
            surface.fill(rgb(panel), (x + 15, top, width, len(options) * row))
        for i, option in enumerate(options):
            # class_6.method_239's rows: the square and the option centred together, the highlighted one on layout
            # 27 in the item font with the pack's arrow sweeping in (200 ms a step), the others in font 59.
            rect = pygame.Rect(x + 15, top + i * row, width, row)
            start = rect.x + (width - font.width(option) - 17) // 2
            if i == focus:
                self.skin().layout(surface, 27, pygame.Rect(rect.x - 4, rect.y - 2, width + 8, font.height + 4))
                self.skin().blit(surface, f'menu/arrow/{now // 200 % 6}', start + 17 - 6, rect.y)
                font.draw(surface, option, start + 17, rect.y, width)
            else:
                self.skin().blit(surface, 'menu/bullet', start, rect.y + (font.height - 9) // 2)
                self.font(59).draw(surface, option, start + 17, rect.y, width)
            self.targets.append((rect, ('arena_answer', i)))
        if not options:
            self.targets.append((pygame.Rect((0, 0), NATIVE), ('arena_answer', 0)))     # a tap anywhere is its OK

    # -- input ------------------------------------------------------------------------------------------------------
    def focus(self, action):
        if action is None or action.name != 'arena_menu':
            return None
        if self.menu_focus is None or self.menu_focus[0] is not action:
            self.menu_focus = (action, action.details.get('selected', 0))
        return self.menu_focus[1]

    def move_focus(self, action, step):
        count = len(action.details.get('options', []))
        if count:
            self.menu_focus = (action, (self.focus(action) + step) % count)

    def hit(self, position):
        """The command under a point in frame pixels (768 x 1024), from the last frame drawn."""
        x = position[0] * NATIVE[0] / FRAME[0]
        y = position[1] * NATIVE[1] / FRAME[1]
        for rect, command in reversed(self.targets):
            if rect.collidepoint(x, y):
                return command
        return None
