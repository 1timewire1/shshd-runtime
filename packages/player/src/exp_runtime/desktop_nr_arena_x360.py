"""shshd-runtime: New Rules' minigame arena in the cancelled X360 prototype's look (owner, 2026-10-31), drawn from the
X360 addon's skin (tools/translate/x360_arena_art.py; reference/Other Games/docs/NR_ARENA_X360_SKIN.md).

Only the drawing differs from desktop_nr_arena.py. The panel model, the library's rules and the result are the same,
and so is every position the New Rules renderer works out (slots, anchors, the keypad, click targets): this renderer
is that one with its drawing replaced, and with the ring following the X360 record's ellipse so the items ride it.
The X360 art is 512-pixel textures and Xenia renders, not pixel art, so it draws smoothly at the frame's size in the
window rather than at New Rules' 480 x 650 scaled up by a whole number. Coordinates are the arena's native pixels
(NATIVE) until they are drawn, times `self.k`.
"""
import io
import json
import math

import pygame

from .desktop_nr_arena import ENTRANCE_MS, FRAME, NATIVE, NRArenaRenderer, OX, SCREEN_HEIGHT, SCREEN_WIDTH

ADDON = 'shsx360'                       # tools/translate/x360.py ADDON_ID
SPEC = 26300                            # x360_arena_art.SPEC
NR_TRACK_BASE = 26980                   # New Rules' tracks in its addon (tools/translate/newrules.py MUSIC_BASE)
FORMAT, VERSION = 'shshd-arena-skin-x360', 1
# Where the X360 pieces go in the arena's native frame (489 x 652; the gear's bar covers below about 560).
DECK_WIDTH = 469                        # the deck centred, 10 pixels in from each edge
RECORD_Y = 380                          # the record's centre: the New Rules ring's height, a little lower
SCORE_BOX = (250, 104, 229)             # the score's six digits: left, top, width (top right, as in Diss Practice)
METER_BOX = pygame.Rect(14, 112, 190, 30)
LABEL_TOP = pygame.Rect(14, 150, 230, 52)       # HUD box 0's label (New Rules' top band), under the meter
LABEL_BOTTOM = pygame.Rect(30, 500, 429, 56)    # HUD box 2's label (the bottom band: "cool rhymes with...")
STAMPS = {'correct!': 'stamp_yeah', 'wrong!': 'stamp_ooops'}     # the library's flash labels (decision 7)
EMPHASIS = (255, 214, 64)               # backticked text, as SHS's emphasis
COMBO_RED = (220, 24, 16)               # Diss Practice's "x13" on the record's label
TUTORIAL_CARDS = {20: 'tutorial_1', 17: 'tutorial_1', 19: 'tutorial_1', 18: 'tutorial_2', 28: 'tutorial_3'}
COUNTDOWN = ((3, 500), (2, 750), (1, 1000))     # Diss Practice's 3-2-1 (ms each, scaling up and back; silent)
START_PROMPT = 'press ok to start'
SCORE_PROMPT = 'your score'             # the end's "your score: n" bubble, where the X360 music stops (Desktop)
MUSIC_FADE_MS = 1000
BUBBLE_TEXT_WIDTH = 430                 # a bubble's or the info box's lines at most, native pixels (balanced: wrapped)
EDGE_SCALE = 0.6                        # native pixels a pixel of a nine-sliced picture's edge
SWING = ((47, 1300), (35, 2100), (62, 1700), (41, 2700), (55, 1100), (30, 2300), (38, 1900), (66, 2500))


def addon_skin(resources):
    """The X360 skin's spec and an archive to read it from, from the library the episode came from, or None: the
    addon isn't required by New Rules' episodes, so it is read straight from the library (ContentLibrary.addon)."""
    library = getattr(resources, 'library', None)
    if library is None or not hasattr(library, 'addon'):
        return None
    try:
        found = library.addon(ADDON)
        if found is None or SPEC not in found[1].entries:
            return None
        spec = json.loads(found[1].read(SPEC))
    except Exception:                                   # a damaged addon: New Rules' look (NR_ARENA_X360_SKIN §1)
        return None
    if spec.get('format') != FORMAT or spec.get('version') != VERSION:
        return None
    return spec, found[1]


def library_has_skin(library):
    """Whether `library` holds the X360 addon with its arena skin (for the "X360 Arena Look" switch)."""
    if library is None or not hasattr(library, 'addon'):
        return False
    try:
        found = library.addon(ADDON)
        if found is None or SPEC not in found[1].entries:
            return False
        spec = json.loads(found[1].read(SPEC))
    except Exception:
        return False
    return spec.get('format') == FORMAT and spec.get('version') == VERSION and 'booth' in spec


class BMFont:
    """A BMFont (x360_arena_art.read_font) drawn in one colour: the X360's black glyphs take `colour`; a two-tone
    font (the white Casual and Badaboom) keeps its own colours."""

    def __init__(self, spec, pages, colour=None):
        self.two_tone = colour is None              # the white Casual and Badaboom: a white fill, a black edge
        self.line_height, self.base = spec['line_height'], spec['base']
        self.chars = {int(k): v for k, v in spec['chars'].items()}
        self.glyphs = {}
        for code, (x, y, w, h, *_rest, page) in self.chars.items():
            if w > 0 and h > 0 and page < len(pages):
                glyph = pages[page].subsurface(pygame.Rect(x, y, w, h)).copy()
                if colour is not None:
                    glyph.fill((*colour, 0), special_flags=pygame.BLEND_RGBA_ADD)
                self.glyphs[code] = glyph

    def _char(self, ch):
        code = ord(ch)
        if code not in self.chars and ch.upper() != ch:
            code = ord(ch.upper())
        return self.chars.get(code), code

    def width(self, text):
        return sum((self._char(ch)[0] or (0,) * 7)[6] for ch in text)

    def render(self, runs):
        """[(text, colour override or None)] on one line, as a surface line_height tall."""
        width = max(1, sum(self.width(text) for text, _ in runs) + 12)
        out = pygame.Surface((width, self.line_height + 8), pygame.SRCALPHA)
        x = 4
        for text, colour in runs:
            for ch in text:
                char, code = self._char(ch)
                if char is None:
                    continue
                glyph = self.glyphs.get(code)
                if glyph is not None:
                    if colour is not None:
                        glyph = glyph.copy()
                        if self.two_tone:               # the fill takes the colour, the black edge stays
                            glyph.fill((*colour, 255), special_flags=pygame.BLEND_RGBA_MULT)
                        else:
                            glyph.fill((0, 0, 0, 255), special_flags=pygame.BLEND_RGBA_MULT)
                            glyph.fill((*colour, 0), special_flags=pygame.BLEND_RGBA_ADD)
                    out.blit(glyph, (x + char[4], char[5] + 4))
                x += char[6]
        return out


def plain_runs(text):
    """New Rules' text as [(text, emphasised)]: its font switches (` to the score font, ~ to font 59, ; back) taken
    out, what the backtick switches to shown as emphasis."""
    runs, current, emphasis, switched = [], '', False, False
    for ch in text.replace('…', '...'):
        if ch in '`~':
            if current:
                runs.append((current, emphasis))
            current, emphasis, switched = '', ch == '`' and not emphasis, True
        elif ch == ';' and switched:
            if current:
                runs.append((current, emphasis))
            current, emphasis, switched = '', False, False
        else:
            current += ch
    if current:
        runs.append((current, emphasis))
    return runs


class X360ArenaRenderer(NRArenaRenderer):
    """The arena in the X360 look. `available()` is False without the X360 addon's skin, and Desktop then keeps
    New Rules' look."""

    def __init__(self, resources):
        super().__init__(resources)
        self.k = FRAME[1] / NATIVE[1]
        self._x360 = None
        self._images = {}
        self._scaled = {}
        self._fonts = {}
        self._texts = {}
        self.countdown = None               # (start ms) once "press ok to start" closes
        self._prompt_seen = False
        self._sizes = []                    # (ms, the ring's size) over the last 0.8 s
        self._stickers = {}

    # -- the skin ---------------------------------------------------------------------------------------------------
    def x360(self):
        if self._x360 is None:
            found = addon_skin(self.resources)
            if found is None:
                raise ValueError('The X360 addon\'s arena skin is missing')
            self._x360 = found
        return self._x360

    def available(self):
        if not super().available():
            return False                    # New Rules' own skin still gives the geometry
        try:
            spec = self.x360()[0]
        except ValueError:
            return False
        return 'booth' in spec

    def image(self, resource):
        found = self._images.get(resource)
        if found is None:
            spec, archive = self.x360()
            found = pygame.image.load(io.BytesIO(archive.read(resource)), 'x360.png').convert_alpha()
            self._images[resource] = found
        return found

    def picture(self, name):
        return self.image(self.x360()[0]['pictures'][name])

    def bubble_art(self):
        """The X360's speech bubble for a bubble: (picture, (left, top, right, bottom) edges for _nine, where its box
        starts below the top in native pixels). The picture is cut to what shows and its body made opaque (the X360
        lays it at half alpha over its 3D scene; here items would show through the text). The top edge takes in the
        tail, which rises above the box at the right, so a taller bubble doesn't stretch it into the text."""
        found = self._images.get('bubble art')
        if found is None:
            image = self.trimmed('bubble').copy()
            w, h = image.get_size()
            alpha = pygame.surfarray.pixels_alpha(image)
            alpha[alpha >= 96] = 255
            del alpha
            column = [image.get_at((w // 4, y))[3] for y in range(h)]
            row = [image.get_at((x, h // 2))[3] for x in range(w)]
            top = next((y for y, a in enumerate(column) if a > 128), 0)
            bottom = h - 1 - next((y for y, a in enumerate(reversed(column)) if a > 128), 0)
            left = next((x for x, a in enumerate(row) if a > 128), 0)
            right = w - 1 - next((x for x, a in enumerate(reversed(row)) if a > 128), 0)
            edges = (left + 10, top + 10, w - right + 10, h - bottom + 10)
            found = self._images['bubble art'] = (image, edges, top * EDGE_SCALE)
        return found

    def trimmed(self, name):
        """A picture cut to what shows (the X360's bubble has a wide clear margin round it)."""
        key = ('trim', name)
        found = self._images.get(key)
        if found is None:
            image = self.picture(name)
            box = image.get_bounding_rect(min_alpha=8)
            found = self._images[key] = image.subsurface(box).copy()
        return found

    def scaled(self, image, size):
        """`image` (a surface, or a skin resource ID) smoothly scaled to `size` pixels, kept for the next frames."""
        if isinstance(image, int):
            image = self.image(image)
        key = (id(image), size)
        found = self._scaled.get(key)
        if found is None or found[0] is not image:          # an id reused by another surface since
            if len(self._scaled) > 400:
                self._scaled.clear()
            found = (image, pygame.transform.smoothscale(image, (max(1, size[0]), max(1, size[1]))))
            self._scaled[key] = found
        return found[1]

    def bmfont(self, name, colour=None):
        key = (name, colour)
        found = self._fonts.get(key)
        if found is None:
            spec = self.x360()[0]['fonts'][name]
            found = BMFont(spec, [self.image(page) for page in spec['pages']], colour)
            self._fonts[key] = found
        return found

    def text_surface(self, font, text, height, colour=None, emphasis=None):
        """A line of text `height` native pixels tall (its line height), drawn once and kept."""
        key = (font, colour, emphasis, text, round(height * self.k))
        found = self._texts.get(key)
        if found is None:
            if len(self._texts) > 200:
                self._texts.clear()
            face = self.bmfont(font, colour)
            runs = [(part.upper(), emphasis if strong and emphasis else None) for part, strong in plain_runs(text)]
            line = face.render(runs)
            scale = height * self.k / face.line_height
            found = pygame.transform.smoothscale(line, (max(1, round(line.get_width() * scale)),
                                                        max(1, round(line.get_height() * scale))))
            self._texts[key] = found
        return found

    def wrapped(self, font, text, height, width, colour=None, emphasis=None):
        """`text` in lines no wider than `width` native pixels, broken at spaces (and at its own line breaks), as
        text_surface images: New Rules' tutorials run to two long sentences. Each paragraph's lines are balanced:
        the narrowest width that still takes as few lines, so no word is left alone on the last."""
        face = self.bmfont(font, colour)
        scale = height / face.line_height

        def broken(paragraph, limit):
            out, line = [], ''
            for word in paragraph.split(' '):
                candidate = f'{line} {word}' if line else word
                plain = ''.join(part for part, _ in plain_runs(candidate)).upper()
                if line and face.width(plain) * scale > limit:
                    out.append(line)
                    line = word
                else:
                    line = candidate
            return out + [line] if line.strip() else out
        lines = []
        for paragraph in text.replace('\r', '').split('\n'):
            best, limit = broken(paragraph, width), width
            while len(best) > 1 and limit > 60:
                trial = broken(paragraph, limit - 10)
                if len(trial) != len(best):
                    break
                best, limit = trial, limit - 10
            lines += best
        return [self.text_surface(font, line, height, colour, emphasis) for line in lines]

    # -- geometry ---------------------------------------------------------------------------------------------------
    def _deck(self):
        """(scale, record centre x, y, record half-width, half-height) in native pixels: the booth's camera frame onto
        the arena's, the deck centred DECK_WIDTH wide, the record's centre at RECORD_Y."""
        booth = self.x360()[0]['booth']
        deck, record = booth['pieces']['deck']['box'], booth['pieces']['record']['box']
        u = DECK_WIDTH / (deck[2] - deck[0])
        record_cx, record_cy = (record[0] + record[2]) / 2, (record[1] + record[3] - 12) / 2   # its top face
        cx = OX + SCREEN_WIDTH / 2 - ((deck[0] + deck[2]) / 2 - record_cx) * u
        return u, cx, RECORD_Y, (record[2] - record[0]) * u / 2, (record[3] - record[1] - 12) * u / 2, record_cx, \
            record_cy

    def _field(self, arena):
        """The ring's rectangle: the record's top face, so the items ride its rim (the selector, at 90 degrees, is the
        needle at its front)."""
        _, cx, cy, rx, ry, _, _ = self._deck()
        self.item_height = self._item_size(arena)[1]
        return pygame.Rect(round(cx - rx), round(cy - ry), round(2 * rx), round(2 * ry))

    def _to_native(self, box):
        """A booth box (camera-frame pixels) placed by the deck's transform, as a native-pixel rect (floats)."""
        u, cx, cy, _, _, record_cx, record_cy = self._deck()
        return (cx + (box[0] - record_cx) * u, cy + (box[1] - record_cy) * u, (box[2] - box[0]) * u,
                (box[3] - box[1]) * u)

    def _time_rect(self):
        slots = self.x360()[0]['booth']['digits']['slots']
        boxes = [self._to_native(slots[i][0]['box']) for i in (6, 7)]
        left, top = min(b[0] for b in boxes), min(b[1] for b in boxes)
        return pygame.Rect(round(left), round(top), round(max(b[0] + b[2] for b in boxes) - left),
                           round(max(b[1] + b[3] for b in boxes) - top))

    def _score_rect(self):
        """Where the score's six digits are, native pixels."""
        digits = self.x360()[0]['booth']['digits']
        u, left, top = self._score_transform()
        bottom = max(digits['slots'][i][0]['box'][3] for i in digits['score'])
        return pygame.Rect(SCORE_BOX[0], SCORE_BOX[1], SCORE_BOX[2], round((bottom - top) * u))

    def _score_transform(self):
        """The score's six digits as a group: their booth boxes scaled to SCORE_BOX's width, at its corner."""
        digits = self.x360()[0]['booth']['digits']
        boxes = [digits['slots'][i][0]['box'] for i in digits['score']]
        left, top = min(b[0] for b in boxes), min(b[1] for b in boxes)
        right = max(b[2] for b in boxes)
        u = SCORE_BOX[2] / (right - left)
        return u, left, top

    def _anchor(self, arena, anchor):
        """New Rules' anchors moved to where the X360 look shows those things."""
        if anchor == -4:
            return self._time_rect()
        if anchor == -5:                    # New Rules' score dial: here the score's digits (where "+3" flies)
            return self._score_rect()
        if anchor == -15:                   # the dial's frame, with the meter round it: here the power bar
            return pygame.Rect(METER_BOX)
        if anchor in (-6, -7):
            ring = self._field(arena)
            return pygame.Rect(ring.centerx - 20, ring.bottom - 10, 40, 20)
        if anchor == -1:
            return pygame.Rect(LABEL_TOP)
        if anchor == -3:
            return pygame.Rect(LABEL_BOTTOM)
        if anchor == -2:
            ring = self._field(arena)
            return pygame.Rect(ring.centerx - 60, ring.centery - 24, 120, 48)
        return super()._anchor(arena, anchor)

    # -- drawing ----------------------------------------------------------------------------------------------------
    def blit(self, surface, image, x, y, w=None, h=None, alpha=255, anchor='topleft'):
        """An image at native (x, y), `w` x `h` native pixels (its own size scaled with the frame by default)."""
        k = self.k
        if w is None:
            w, h = image.get_width() / k, image.get_height() / k
        size = (max(1, round(w * k)), max(1, round(h * k)))
        scaled = self.scaled(image, size) if image.get_size() != size else image
        rect = scaled.get_rect(**{anchor: (round(x * k), round(y * k))})
        if alpha < 255:
            scaled = scaled.copy()
            scaled.set_alpha(alpha)
        surface.blit(scaled, rect)
        return rect

    def draw(self, target, session, now_ms=None, overlay=True):
        arena = session.engine.nr_arena
        action = session.pending
        now = pygame.time.get_ticks() if now_ms is None else now_ms
        # Exactly 3:4 (a height a multiple of 4), as the player places a layer over the whole frame only then: a
        # pixel off and it took the canvas for the story's 320 x 480 column (owner, 2026-10-31).
        height = max(4, round(max(FRAME[1], self.target_height) / 4) * 4)
        size = (height * 3 // 4, height)
        self.k = height / NATIVE[1]
        if self.canvas.get_size() != size:
            self.canvas = pygame.Surface(size).convert()
        surface = self.canvas
        self.targets = []
        skin = self.skin()
        if skin.frame is not None:
            if self._frame_scaled is None or self._frame_scaled[0] != size:
                self._frame_scaled = (size, pygame.transform.smoothscale(skin.frame, size))
            surface.blit(self._frame_scaled[1], (0, 0))
        else:
            surface.fill((0, 0, 0))
        moving = arena is not None and (arena.entering or arena.leaving)
        if arena is None:
            return []                       # the panel closed: the bare frame, which fades out over the next screen
        ms = (ENTRANCE_MS - arena.exit_ms) if arena.leaving else arena.entrance_ms if arena.entering else ENTRANCE_MS
        self._backdrop(surface, min(1, ms / 600) if moving else 1)
        drop = 0 if ms >= 800 else (1 - ms / 800) ** 2          # the HUD drops in over the first 800 ms
        rise = 0 if ms >= 1600 else 1 if ms <= 400 else (1 - (ms - 400) / 1200) ** 2   # the deck rises 400-1600 ms
        self._paint_x360(surface, arena, session, now, drop * -200, rise * 420, moving)
        if action is not None and action.name in ('arena_menu', 'arena_info') and overlay:
            self.targets = []
            self._overlay_x360(surface, action, now)
        return []

    def _backdrop(self, surface, alpha):
        """Diss Practice's own place behind the deck: the school front's steps (decision 1), cut to the 3:4 frame
        round the deck as the game's camera saw it."""
        booth = self.x360()[0]['booth']
        image = self.image(booth['places']['school_front_diss_002'])
        u, cx, cy, _, _, record_cx, record_cy = self._deck()
        frame_w, frame_h = booth['frame']
        scale = max(NATIVE[1] / frame_h, u)                      # at least the deck's scale, filling the height
        w, h = frame_w * scale, frame_h * scale
        x = cx - record_cx * scale
        y = cy - record_cy * scale
        x = min(0, max(NATIVE[0] - w, x))
        y = min(0, max(NATIVE[1] - h, y))
        self.blit(surface, image, x, y, w, h, alpha=round(255 * alpha))

    def _paint_x360(self, surface, arena, session, now, hud_dy, deck_dy, moving):
        u, cx, cy, rx, ry, record_cx, record_cy = self._deck()
        booth = self.x360()[0]['booth']
        # The deck keeps its size when a game sets another ring size (Fever, Sequences, a tutorial) and follows only the
        # shake: its scale is the ring's size against where it rests, the median of the last 0.8 s (a shake swings
        # round it; a size held takes over within half that), within the shake's 15 %.
        self._sizes = [(t, s) for t, s in self._sizes if now - t < 800 and t <= now] + [(now, arena.ring_size)]
        rest = max(1, sorted(s for _, s in self._sizes)[len(self._sizes) // 2])
        # A shake swings back and forth; the library's easing a ring in or out moves one way: only the first (two
        # turns within 0.6 s) moves the deck.
        steps = [b - a for (_, a), (t, b) in zip(self._sizes, self._sizes[1:]) if a != b and now - t < 600]
        turns = sum(1 for d, e in zip(steps, steps[1:]) if (d > 0) != (e > 0))
        size = min(1.15, max(0.85, arena.ring_size / rest)) if turns >= 2 else 1
        deck = booth['pieces']['deck']
        x, y, w, h = self._to_native(deck['box'])
        self.blit(surface, self.image(deck['id']), cx + (x - cx) * size, cy + (y - cy) * size + deck_dy, w * size,
                  h * size)
        if moving:
            self._hud_x360(surface, arena, session, now, hud_dy, deck_dy)
            return
        ring = self._field(arena)
        self._buttons_x360(arena, ring)
        self._needle(surface, arena, ring)
        if arena.keypad:
            self._keypad_x360(surface, arena, ring)
        count = len(arena.slots)
        self._ring_x360(surface, arena, ring, 0, count // 2)
        self._label_x360(surface, arena, session, 1, now)
        self._ring_x360(surface, arena, ring, count // 2, count)
        self._hud_x360(surface, arena, session, now, 0)
        self._popups_x360(surface, arena, ring)
        prompt = False
        for bubble in arena.bubbles:
            if bubble is not None and bubble[0]:
                # The 3-2-1 is before the game itself: "press ok to start", not "...start practice." (tutorial)
                prompt = prompt or bubble[0].strip().casefold().rstrip('.!') == START_PROMPT
                self._bubble_x360(surface, arena, ring, bubble[0], bubble[2], bubble[1], now)
        self._countdown(surface, arena, ring, now, prompt)

    # The HUD: score, time, meter, the labels and the HUD boxes' pictures.
    def _hud_x360(self, surface, arena, session, now, dy, deck_dy=0):
        if arena.score_display == 1 or (arena.score_display == 2 and arena.blink_clock_ms // 500 % 2 == 1):
            self._score_x360(surface, arena, now, dy)
        if arena.timer_shown:
            self._time_x360(surface, arena, now, deck_dy)            # on the deck: it moves with it
        if arena.score_display or arena.meter >= 0:
            self._meter_x360(surface, arena, dy)
        for box in (0, 2):
            self._label_x360(surface, arena, session, box, now, dy if box == 0 else 0)

    def _digit(self, surface, slot, n, rect, now):
        """Slot `slot`'s digit `n` from the atlas into `rect` (native x, y, w, h), swinging as Diss Practice's do:
        30-70 degrees about the digit's upright axis and back, drawn as its width narrowing."""
        digits = self.x360()[0]['booth']['digits']
        ax, ay, aw, ah = digits['slots'][slot][n]['rect']
        atlas = self.image(digits['atlas'])
        cell = self._scaled.get(('cell', slot, n))
        if cell is None:
            cell = atlas.subsurface(pygame.Rect(ax, ay, aw, ah)).copy()
            self._scaled[('cell', slot, n)] = cell
        amplitude, period = SWING[slot % len(SWING)]
        phase = (now % (2 * period)) / period                   # 0-2: there and back
        angle = amplitude * (1 - abs(1 - phase)) - amplitude / 2
        x, y, w, h = rect
        narrow = max(0.55, math.cos(math.radians(angle)))
        self.blit(surface, cell, x + w * (1 - narrow) / 2, y, w * narrow, h)

    def _score_x360(self, surface, arena, now, dy):
        digits = self.x360()[0]['booth']['digits']
        u, left, top = self._score_transform()
        text = f'{max(0, min(arena.score, 999999)):06d}'
        for slot, ch in zip(digits['score'], text):
            box = digits['slots'][slot][int(ch)]['box']
            self._digit(surface, slot, int(ch), (SCORE_BOX[0] + (box[0] - left) * u,
                                                  SCORE_BOX[1] + (box[1] - top) * u + dy,
                                                  (box[2] - box[0]) * u, (box[3] - box[1]) * u), now)

    def _time_x360(self, surface, arena, now, dy=0):
        digits = self.x360()[0]['booth']['digits']
        seconds = max(0, min(99, -(-max(0, arena.timer_ms) // 1000)))
        for slot, ch in zip(digits['time'], f'{seconds:02d}'):
            x, y, w, h = self._to_native(digits['slots'][slot][int(ch)]['box'])
            self._digit(surface, slot, int(ch), (x, y + dy, w, h), now)

    def _meter_x360(self, surface, arena, dy):
        """The 0-10 meter as the X360's power bar: green once the target is met (or at max), blue past the second
        marker, yellow below both, as New Rules' three meter kinds; the markers as ticks; a pulse at max."""
        rect = METER_BOX.move(0, dy)
        self.blit(surface, self.picture('power_bar'), rect.x, rect.y, rect.width, rect.height)
        meter, target, second = arena.meter, arena.target_marker, arena.second_marker
        inner = rect.inflate(-rect.width * 0.08, -rect.height * 0.36)
        if meter >= 0:
            if meter >= 9 or meter >= target:
                fill = 'power_fill_green'
            elif meter >= second and second != -2:
                fill = 'power_fill_blue'
            else:
                fill = 'power_fill_yellow'
            share = min(10, meter + 1) / 10
            alpha = 255 if meter < 9 else 190 + round(65 * abs(math.sin(arena.max_ms / 2000 * math.pi * 2)))
            self.blit(surface, self.picture(fill), inner.x, inner.y, inner.width * share, inner.height, alpha=alpha)
        k = self.k
        for marker, colour in ((second, (80, 140, 255)), (target, (255, 255, 255))):
            if 0 <= marker <= 9 and marker != -2:
                mx = inner.x + inner.width * (marker + 1) / 10
                points = [(mx * k, (rect.bottom + 1) * k), ((mx - 5) * k, (rect.bottom + 9) * k),
                          ((mx + 5) * k, (rect.bottom + 9) * k)]
                pygame.draw.polygon(surface, colour, points)
                pygame.draw.polygon(surface, (0, 0, 0), points, max(1, round(k)))

    def _label_x360(self, surface, arena, session, box, now, dy=0):
        """A HUD box's picture and its label or flashing message: box 1's on the record's label in Diss Practice's
        red combo style; box 0's under the meter and box 2's along the bottom in white with a black edge. "correct!"
        and "wrong!" flash as the YEAH! and OOOPS! stamps (decision 7)."""
        item_id, kind, variant = arena.hud[box][0], arena.hud[box][1], arena.hud[box][2]
        if variant in (1, 2) and item_id != -1 and kind == 2 and not (arena.hud[box][5] & 1 and now // 350 % 2 == 0):
            area = self._anchor(arena, -1 - box)
            self._item_picture(surface, item_id, area.centerx, area.bottom + dy, 52)
        text = arena.labels[box]
        flash = arena.labels[box + 3]
        flashing = flash is not None and arena.flash_ms[box] > 0
        if flashing:
            stamp = STAMPS.get(flash.strip().casefold().strip('`'))
            if stamp is not None:                       # over the record, whichever label flashes it
                ring = self._field(arena)
                grow = 1 + 0.15 * max(0, (arena.flash_ms[box] - 2700) / 300)
                image = self.picture(stamp)
                w = 230 * grow
                self.blit(surface, image, ring.centerx, ring.y - 40 + dy, w, w * image.get_height() / image.get_width(),
                          anchor='center')
                return
            text = flash if arena.flash_ms[box] // 350 % 2 else None
        if not text:
            return
        for line_no, line in enumerate(text.replace('\r', '').split('\n')[:2]):
            if box == 1:
                image = self.text_surface('badaboom', line, 26, COMBO_RED, EMPHASIS)
                ring = self._field(arena)
                x, y = ring.centerx, ring.centery - 4 + line_no * 22
            elif box == 0:                                  # under the meter, from its left
                image = self.text_surface('casual_white', line, 24, None, EMPHASIS)
                x = LABEL_TOP.x + image.get_width() / self.k / 2
                y = LABEL_TOP.y + 4 + line_no * 24 + dy
            else:                                           # along the bottom, centred
                image = self.text_surface('badaboom_white', line, 34, None, EMPHASIS)
                x, y = LABEL_BOTTOM.centerx, LABEL_BOTTOM.y + 4 + line_no * 32
            w, h = image.get_width() / self.k, image.get_height() / self.k
            if w > SCREEN_WIDTH - 20:
                ratio = (SCREEN_WIDTH - 20) / w
                w, h = w * ratio, h * ratio
            if box != 1:                                    # a soft dark plate: white text over the light steps
                self._plate(surface, x - w / 2 - 6, y + h * 0.12, w + 12, h * 0.72)
            self.blit(surface, image, x, y, w, h, anchor='midtop')

    def _plate(self, surface, x, y, w, h):
        k = self.k
        rect = pygame.Rect(round(x * k), round(y * k), max(1, round(w * k)), max(1, round(h * k)))
        key = ('plate', rect.size)
        plate = self._scaled.get(key)
        if plate is None:
            plate = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(plate, (12, 14, 24, 150), plate.get_rect(), border_radius=max(2, round(8 * k)))
            self._scaled[key] = plate
        surface.blit(plate, rect)

    def _item_picture(self, surface, item, x, bottom, height, alpha=255):
        """New Rules' item picture `item` in the X360 look (its counterpart, or New Rules' own outlined), standing at
        (x, bottom), `height` native pixels tall at most."""
        items = self.x360()[0]['items']
        name = self._picture_name(item)
        index = name and name.split('/')[1]
        resource = items.get(index) if index is not None else None
        if resource is None:
            return None
        image = self.image(resource)
        nr_w, nr_h = self.skin().size(name) if name in self.skin().sprites else (40, 40)
        h = min(height, max(30, nr_h * 1.15))
        w = h * image.get_width() / image.get_height()
        if w > max(nr_w * 1.4, 54):
            w = max(nr_w * 1.4, 54)
            h = w * image.get_height() / image.get_width()
        return self.blit(surface, image, x, bottom, w, h, alpha=alpha, anchor='midbottom')

    def _ring_x360(self, surface, arena, ring, start, stop):
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
            x, y = self._ring_x(ring, a, arena.ring_size), self._ring_y(ring, a, arena.ring_size)
            move = arena.moves[slot]
            if move is not None and move[3] > 0:
                source, angle, elapsed, total = move
                fx, fy = self._slot_point(arena, ring, source, angle=angle) if 0 <= source < count else (x, y)
                fy -= self.item_height // 2
                x = fx + (x - fx) * elapsed / total
                y = fy + (y - fy) * elapsed / total
            y = self._row_y(arena, ring, y, slot) - (6 if arena.plates else 0)
            drawn = self._item_x360(surface, arena, arena.slots[slot], arena.item_kind, x, y, arena.tint[slot])
            if arena.keypad and slot < 6 and arena.slots[slot] != -1:
                # The item's whole picture as drawn takes the click (Sequences: its slot's number key), a little
                # beyond it; New Rules' item size is smaller than the X360 pictures (owner, 2026-11-01).
                from .desktop_nr_arena import KEYPAD
                width, height = self._item_size(arena)
                area = pygame.Rect(round(x - width / 2), round(y - height), width, height)
                if drawn is not None:
                    area.union_ip(pygame.Rect(drawn.x / self.k, drawn.y / self.k, drawn.width / self.k,
                                              drawn.height / self.k))
                self.targets.append((area.inflate(10, 10), ('arena_key', 48 + int(KEYPAD[slot]))))

    def _item_x360(self, surface, arena, item, kind, x, y, tint, alpha=255):
        """An item standing at (x, y): the rect drawn, in canvas pixels, or None."""
        if item == -1:
            return None
        if kind == 2:
            return self._item_picture(surface, item, x, y, 58, alpha)
        elif kind == 3 and 0 <= item < len(arena.strings):
            # A tinted box (751: the library's colour for the words, GOOD and BAD) takes the tint, its text white
            # with a black edge; an untinted one stays the X360's beige sticker with dark text.
            if tint != -1:
                image = self.text_surface('casual_white', arena.strings[item], 26, None, EMPHASIS)
            else:
                image = self.text_surface('casual', arena.strings[item], 26, (24, 16, 16), (190, 20, 20))
            w, h = image.get_width() / self.k + 10, image.get_height() / self.k - 2
            sticker = self._stickers.get(tint)
            if sticker is None:
                sticker = self.picture('sticker')
                if tint != -1:
                    sticker = sticker.copy()
                    sticker.fill(((tint >> 16 & 255), (tint >> 8 & 255), (tint & 255), 255),
                                 special_flags=pygame.BLEND_RGBA_MULT)
                self._stickers[tint] = sticker
            self._nine(surface, sticker, x - w / 2, y - h, w, h, 10, alpha)
            self.blit(surface, image, x, y - h / 2, anchor='center')
            return pygame.Rect(round((x - w / 2) * self.k), round((y - h) * self.k), round(w * self.k),
                               round(h * self.k))
        return None

    def _nine(self, surface, image, x, y, w, h, border, alpha=255):
        """`image` stretched over (x, y, w, h) native pixels with its edges kept (nine slices): `border` pixels of
        the picture on every side, or (left, top, right, bottom). An edge is drawn at EDGE_SCALE native pixels a
        picture pixel."""
        iw, ih = image.get_size()
        edges = (border,) * 4 if isinstance(border, int) else tuple(border)
        bl, bt, br, bb = (max(1, min(e, (iw if i % 2 == 0 else ih) // 3 if isinstance(border, int)
                                     else (iw if i % 2 == 0 else ih) - 2)) for i, e in enumerate(edges))
        k = self.k
        dl, dt, dr, db = (max(1, round(e * k * EDGE_SCALE)) for e in (bl, bt, br, bb))
        X, Y = round(x * k), round(y * k)
        W, H = max(dl + dr + 1, round(w * k)), max(dt + db + 1, round(h * k))
        key = ('nine', id(image), W, H, dl, dt, dr, db)
        found = self._scaled.get(key)
        if found is None:
            found = pygame.Surface((W, H), pygame.SRCALPHA)
            cols = ((0, bl, 0, dl), (bl, iw - bl - br, dl, W - dl - dr), (iw - br, br, W - dr, dr))
            rows = ((0, bt, 0, dt), (bt, ih - bt - bb, dt, H - dt - db), (ih - bb, bb, H - db, db))
            for sx, sw, dx, dw in cols:
                for sy, sh, dy, dh in rows:
                    if sw > 0 and sh > 0 and dw > 0 and dh > 0:
                        part = image.subsurface(pygame.Rect(sx, sy, sw, sh))
                        found.blit(pygame.transform.smoothscale(part, (dw, dh)), (dx, dy))
            self._scaled[key] = found
        if alpha < 255:
            found = found.copy()
            found.set_alpha(alpha)
        surface.blit(found, (X, Y))

    def _buttons_x360(self, arena, ring):
        """The on-screen buttons aren't drawn (the needle is the OK button, and a tap anywhere is OK), but they still
        take clicks where New Rules' are."""
        from .desktop_nr_arena import BUTTON_KEYS, BUTTON_NODES
        for i, name in enumerate(BUTTON_NODES):
            if arena.buttons & (2 << i):
                self.targets.append((pygame.Rect(self.skin().nodes[name]), ('arena_key', BUTTON_KEYS[name])))

    def _needle(self, surface, arena, ring):
        """OK's feedback at the needle (the selector): a glow while it's pressed, green for right, red for wrong
        (708), white otherwise (in place of the tone arm's PUSH, which the booth didn't catch)."""
        if arena.button_ms[0] == -1:
            return
        colour = {1: (60, 255, 80), 2: (255, 60, 50)}.get(arena.feedback, (255, 255, 230))
        k = self.k
        radius = round(16 * k)
        glow = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        for r in range(radius, 0, -max(1, radius // 8)):
            pygame.draw.circle(glow, (*colour, round(150 * (1 - r / radius)) + 20), (radius, radius), r)
        surface.blit(glow, (round(ring.centerx * k) - radius, round(ring.bottom * k) - radius))

    def _keypad_x360(self, surface, arena, ring):
        from .desktop_nr_arena import KEYPAD
        count = len(arena.slots) or 1
        for i, ch in enumerate(KEYPAD):
            a = (arena.angle + 90 + i * (360 // count)) % 360
            x = self._ring_x(ring, a, 100)
            y = self._row_y(arena, ring, self._ring_y(ring, a, 100), i, 100)
            if 2 <= i <= 4:
                y -= self.item_height + 22
            flashing = arena.keypad_flash_ms > 0 and arena.keypad_flash == i
            image = self.text_surface('badaboom_white' if not flashing else 'badaboom', ch, 24,
                                      None if not flashing else (255, 200, 40))
            self.blit(surface, image, x - 14, y + 2, anchor='midtop')
            self.targets.append((pygame.Rect(x - 24, y - 12, 48, 48), ('arena_key', 48 + int(ch))))

    def _popups_x360(self, surface, arena, ring):
        count = len(arena.slots)
        for popup in arena.popups:
            if popup.kind == 3 and popup.count > 0:
                rect = self._anchor(arena, popup.source)
                step = rect.width / popup.count
                x, y = rect.x + step * popup.index + step / 2, rect.y + rect.height / 2
            elif popup.kind == 3:
                if not 0 <= popup.source < count:
                    continue
                x, y = self._slot_point(arena, ring, popup.source, vertical=0)
            else:
                sx, sy = self._point(arena, ring, popup.source) if popup.source != -32768 else (0, 0)
                sy -= self.item_height // 2
                tx, ty = self._point(arena, ring, popup.target, x_from=sx, y_from=sy)
                ty -= self.item_height // 2
                progress = popup.elapsed_ms / popup.duration_ms if popup.duration_ms > 0 else 0
                x, y = sx + (tx - sx) * progress, sy + (ty - sy) * progress
            if popup.kind == 1:
                if 0 <= popup.value < len(arena.strings):
                    image = self.text_surface('badaboom', arena.strings[popup.value], 30, COMBO_RED, EMPHASIS)
                    self.blit(surface, image, x, y, anchor='midbottom')
            elif popup.kind == 3:
                self._item_picture(surface, popup.value, x, y + 20, 44)
            else:
                self._item_x360(surface, arena, popup.value, arena.item_kind, x, y, popup.tint)

    def _bubble_x360(self, surface, arena, ring, text, slot, flags, now):
        """A bubble in the X360's speech bubble, where New Rules puts it (method_449's placing); in Rhythm's tutorial
        the Diss Practice card for the item it points at (decision 4)."""
        images = self.wrapped('casual', text, 24, BUBBLE_TEXT_WIDTH, (20, 20, 30), (190, 20, 20))
        k = self.k
        art, edges, box_top = self.bubble_art()
        inner_w = max((im.get_width() for im in images), default=0) / k
        inner_h = sum(im.get_height() / k - 8 for im in images)
        w, h = min(SCREEN_WIDTH - 8, inner_w + 36), box_top + inner_h + 20     # the tail above the box, then text
        x, y = OX + (SCREEN_WIDTH - w) / 2, (SCREEN_HEIGHT - h) / 2
        above = bool(flags & 2)
        card = None
        if flags & 1 and (slot < 0 or slot < len(arena.slots)):
            sx, sy = self._point(arena, ring, slot, vertical=2 if above else 1)
            y = sy - h - 12 if above else sy + 12
            x = min(max(8, sx - w / 2), NATIVE[0] - 8 - w)
            if 0 <= slot < len(arena.slots) and arena.item_kind == 2:
                name = self._picture_name(arena.slots[slot])
                card = TUTORIAL_CARDS.get(int(name.split('/')[1])) if name else None
        # Clear of the bottom label (box 2's: "bling rhymes with...") when it shows, else of the gear's bar.
        bottom = LABEL_BOTTOM.y - 4 if arena.labels[2] else NATIVE[1] - 70
        y = min(max(4, y), bottom - h)
        self._nine(surface, art, x, y, w, h, edges)
        top = y + box_top + 6
        for image in images:
            self.blit(surface, image, x + w / 2, top, anchor='midtop')
            top += image.get_height() / k - 8
        if card is not None:
            image = self.picture(card)
            cw = 190
            ch = cw * image.get_height() / image.get_width()
            cy = y - ch - 4 if y - ch - 4 > 60 else y + h + 4
            self.blit(surface, image, x + w / 2, cy, cw, ch, anchor='midtop')

    def _countdown(self, surface, arena, ring, now, prompt):
        """Diss Practice's 3-2-1 once "press ok to start" closes, as decoration (decision 5): the game is already
        running under it, so it is translucent and held clear of the record's centre."""
        if prompt:
            self._prompt_seen, self.countdown = True, None
            return
        if self._prompt_seen and arena.timer_shown and arena.timer_ms > 0:
            self._prompt_seen, self.countdown = False, now
        if self.countdown is None:
            return
        elapsed = now - self.countdown
        digits = self.x360()[0]['booth']['digits']
        for n, length in COUNTDOWN:
            if elapsed < length:
                grow = 1 + math.sin(math.pi * elapsed / length)       # 1 -> 2 -> 1, as B2Scale2ToAndBackLoop
                ax, ay, aw, ah = digits['slots'][7][n]['rect']
                cell = self.image(digits['atlas']).subsurface(pygame.Rect(ax, ay, aw, ah))
                h = 70 * grow
                self.blit(surface, cell, ring.centerx, ring.y - 30, h * aw / ah, h, alpha=170, anchor='midbottom')
                return
            elapsed -= length
        self.countdown = None

    def _overlay_x360(self, surface, action, now):
        """The info box (10) in the X360's narrator box; New Rules' menu (9), where the player doesn't show it as SHS's
        choice, as a list in it. A tap anywhere is the info box's OK."""
        details = action.details
        is_menu = action.name == 'arena_menu'
        title = (details.get('title') if is_menu else details.get('text')) or ''
        options = details.get('options', []) if is_menu else []
        images = self.wrapped('casual', title, 24, BUBBLE_TEXT_WIDTH, (20, 20, 30), (190, 20, 20))
        k = self.k
        w = min(SCREEN_WIDTH - 12, max((im.get_width() / k for im in images), default=200) + 50)
        h = sum(im.get_height() / k - 8 for im in images) + 40 + len(options) * 30
        x, y = OX + (SCREEN_WIDTH - w) / 2, (SCREEN_HEIGHT - h) / 2
        self._nine(surface, self.trimmed("info_box"), x, y, w, h, 18)
        top = y + 18
        for image in images:
            self.blit(surface, image, x + w / 2, top, anchor='midtop')
            top += image.get_height() / k - 8
        focus = self.focus(action)
        for i, option in enumerate(options):
            colour = (190, 20, 20) if i == focus else (20, 20, 30)
            image = self.text_surface('casual', option, 22, colour)
            self.blit(surface, image, x + w / 2, top + 6 + i * 30, anchor='midtop')
            self.targets.append((pygame.Rect(round(x), round(top + 6 + i * 30), round(w), 28), ('arena_answer', i)))
        if not options:
            self.targets.append((pygame.Rect((0, 0), NATIVE), ('arena_answer', 0)))
