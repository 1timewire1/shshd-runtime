"""shshd-runtime: New Rules' minigame arena in the cancelled X360 prototype's look (owner, 2026-10-31), drawn from the
X360 addon's skin (tools/translate/x360_arena_art.py; docs/X360.md).

Only the drawing differs from desktop_nr_arena.py. The panel model, the library's rules and the result are the same,
and so is every position the New Rules renderer works out (slots, anchors, the keypad, click targets): this renderer
is that one with its drawing replaced, and with the ring following the X360 record's ellipse so the items ride it.
The X360 art is 512-pixel textures and Xenia renders, not pixel art, so it draws smoothly at the frame's size in the
window rather than at New Rules' 480 x 650 scaled up by a whole number. Coordinates are the arena's native pixels
(NATIVE) until they are drawn, times `self.k`.
"""
import json
import math

import pygame

from .desktop_nr_arena import ENTRANCE_MS, FRAME, NATIVE, NRArenaRenderer, OX, SCREEN_HEIGHT, SCREEN_WIDTH
from .desktop_x360_deck import FX, SCORE_BOX, X360Deck

# New Rules' item pictures that are notes, as Diss Practice shoots them (booth `notes`; owner, 2026-11-02): (picture, its
# effects). Its good note at speeds 1-7, 8-9 and max are the X360's note, double note and on-fire note.
ITEM_NOTES = {20: ('note', ()), 17: ('double', ('sparks',)), 19: ('double', ('flames', 'sparks')), 18: ('bad', ('stink',)),
              28: ('swap', ())}
NOTE_ROW = .8                           # how far from the record's centre its notes ride (x360_diss.ELEMENTS)

ADDON = 'shsx360'                       # tools/translate/x360.py ADDON_ID
SPEC = 26300                            # x360_arena_art.SPEC
NR_TRACK_BASE = 26980                   # New Rules' tracks in its addon (tools/translate/newrules.py MUSIC_BASE)
FORMAT, VERSION = 'shshd-arena-skin-x360', 1
METER_BOX = pygame.Rect(14, 112, 190, 30)
LABEL_TOP = pygame.Rect(14, 150, 230, 52)       # HUD box 0's label (New Rules' top band), under the meter
LABEL_BOTTOM = pygame.Rect(30, 500, 429, 56)    # HUD box 2's label (the bottom band: "cool rhymes with...")
STAMPS = {'correct!': 'stamp_yeah', 'wrong!': 'stamp_ooops'}     # the library's flash labels (decision 7)
EMPHASIS = (255, 214, 64)               # backticked text, as SHS's emphasis
COMBO_RED = (220, 24, 16)               # Diss Practice's "x13" on the record's label
TUTORIAL_CARDS = {20: 'tutorial_1', 17: 'tutorial_1', 19: 'tutorial_1', 18: 'tutorial_2', 28: 'tutorial_3'}
COUNTDOWN = ((3, 500), (2, 750), (1, 1000))     # Diss Practice's 3-2-1 (ms each, scaling up and back; silent)
START_PROMPT = 'press ok to start'
MUSIC_FADE_MS = 1000
HIT_TRACKS = {'good': 13, 'bad': 1}     # the New Rules track each hit effect's moment plays in the game
BUBBLE_TEXT_WIDTH = 430                 # a bubble's or the info box's lines at most, native pixels (balanced: wrapped)
EDGE_SCALE = 0.6                        # native pixels a pixel of a nine-sliced picture's edge
PANEL_FLOURISH = 170                    # the slot panel's ends, kept whole: its ink flourishes at top left, bottom right
TITLE_X = 1.0                           # the 3:4 frame's place across the title's 16:9 screen (0 left, 1 right)


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
    except Exception:                                   # a damaged addon: New Rules' look (docs/X360.md)
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


class X360ArenaRenderer(X360Deck, NRArenaRenderer):
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
        self._wrapped = {}
        self.countdown = None               # (start ms) once "press ok to start" closes
        self._prompt_seen = False
        self._sizes = []                    # (ms, the ring's size) over the last 0.8 s
        self.effects = []                   # hit effects playing: (kind, x, y, start ms, particles)
        self.hits = []                      # the latest ones' kinds, for Desktop: a tutorial's practice has no sounds
        self._fx_pressed, self._fx_held, self._fx_flash_ms = False, -1, 0
        self._stickers = {}
        self._title = None                  # the title backdrop's layers at the frame's size (_title_layers)
        self._title_surface = None
        self._seams = {}                    # the record's seams by turn and size (_record_seams)
        self._arm_held, self._arm_start, self._now = -1, None, 0     # the tone arm's swing (_arm_press, _arm_frame)
        self._arm_clear, self._arm_waiting, self._arm_taken = False, False, False

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

    @staticmethod
    def _opaque(source):
        """Opaque by laying it over itself (plain pygame: the player has no numpy): a half-alpha body reaches full alpha
        in three layers, its colours unchanged. The X360 lays these at half alpha over its 3D scene; here items would
        show through the text."""
        image = source.copy()
        for _ in range(3):
            image.blit(source, (0, 0))
        return image

    def panel_art(self):
        """The slot machine's panel for a bubble (owner, 2026-11-01): (picture, (left, top, right, bottom) edges for
        _nine, where its box starts below the top in native pixels, native pixels below the text, the narrowest it
        goes). The edges take in its flourishes, so a wider or taller panel doesn't stretch them. None with an addon
        from before the slot machine (revision 1), whose bubbles stay speech bubbles."""
        found = self._images.get('panel art')
        if found is None:
            spec = self.x360()[0].get('slot')
            if spec is None:
                return None
            source = self.image(spec['panel'])
            image = self._opaque(source.subsurface(source.get_bounding_rect(min_alpha=8)).copy())
            w, h = image.get_size()
            column = [image.get_at((w // 2, y))[3] for y in range(h)]   # (the flourishes stop short of the middle)
            top = next((y for y, a in enumerate(column) if a > 128), 0)
            bottom = h - next((y for y, a in enumerate(reversed(column)) if a > 128), 0)
            flourish = min(PANEL_FLOURISH, (w - 2) // 2)
            found = self._images['panel art'] = (image, (flourish, top + 10, flourish, h - bottom + 10), top * EDGE_SCALE,
                                                 (h - bottom) * EDGE_SCALE + 16, 2 * flourish * EDGE_SCALE + 10)
        return found

    def bubble_art(self):
        """The X360's speech bubble for a bubble, as panel_art has it. The picture is cut to what shows and its body made
        opaque. The top edge takes in the tail, which rises above the box at the right, so a taller bubble doesn't
        stretch it into the text."""
        found = self._images.get('bubble art')
        if found is None:
            image = self._opaque(self.trimmed('bubble'))
            w, h = image.get_size()
            column = [image.get_at((w // 4, y))[3] for y in range(h)]
            row = [image.get_at((x, h // 2))[3] for x in range(w)]
            top = next((y for y, a in enumerate(column) if a > 128), 0)
            bottom = h - 1 - next((y for y, a in enumerate(reversed(column)) if a > 128), 0)
            left = next((x for x, a in enumerate(row) if a > 128), 0)
            right = w - 1 - next((x for x, a in enumerate(reversed(row)) if a > 128), 0)
            edges = (left + 10, top + 10, w - right + 10, h - bottom + 10)
            found = self._images['bubble art'] = (image, edges, top * EDGE_SCALE, 20, 0)
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
        the narrowest width that still takes as few lines, so no word is left alone on the last. Worked out once and
        kept: a bubble on screen asks every frame."""
        key = (font, colour, emphasis, text, height, width, self.k)
        found = self._wrapped.get(key)
        if found is not None:
            return found
        if len(self._wrapped) > 200:
            self._wrapped.clear()
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
        found = self._wrapped[key] = [self.text_surface(font, line, height, colour, emphasis) for line in lines]
        return found

    # -- geometry ---------------------------------------------------------------------------------------------------
    def _field(self, arena):
        """The ring's rectangle: the record's top face, so the items ride its rim (the selector, at 90 degrees, is the
        needle at its front)."""
        _, cx, cy, rx, ry, _, _ = self._deck()
        self.item_height = self._item_size(arena)[1]
        return pygame.Rect(round(cx - rx), round(cy - ry), round(2 * rx), round(2 * ry))

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
        self._backdrop(surface, min(1, ms / 600) if moving else 1, now)
        drop = 0 if ms >= 800 else (1 - ms / 800) ** 2          # the HUD drops in over the first 800 ms
        rise = 0 if ms >= 1600 else 1 if ms <= 400 else (1 - (ms - 400) / 1200) ** 2   # the deck rises 400-1600 ms
        self._paint_x360(surface, arena, session, now, drop * -200, rise * 420, moving)
        if action is not None and action.name in ('arena_menu', 'arena_info') and overlay:
            self.targets = []
            self._overlay_x360(surface, action, now)
        return []

    def _backdrop(self, surface, alpha, now=0):
        """The title screen's background behind the deck, whatever the episode's place (owner, 2026-11-01): its sky,
        the clouds drifting at the title's own speed, a sweep of ray glints every 3 s, the city and the school, cut
        from its 16:9 screen to the 3:4 frame at TITLE_X. A skin without it has Diss Practice's own place."""
        title = self.x360()[0].get('title')
        if title is None:
            self._place_backdrop(surface, alpha)
            return
        width, height = size = surface.get_size()
        layers = self._title_layers(title, size)
        if alpha < 1:
            if self._title_surface is None or self._title_surface.get_size() != size:
                self._title_surface = pygame.Surface(size).convert()
            target = self._title_surface
        else:
            target = surface
        target.blit(layers['sky'], (0, 0))
        clouds, title_w, left = layers['clouds'], layers['width'], layers['left']
        # The shader's UV shift: the texture slides left, wrapping, `speed` of its width a second.
        x = -left - round(now / 1000 * title['clouds']['speed'] * title_w) % title_w
        while x < width:
            target.blit(clouds, (x, 0))
            x += title_w
        rays = title['rays']
        k = (now % rays['every']) // rays['ms']
        if k < len(rays['frames']):
            target.blit(self._title_ray(title, size, k), (0, 0))
        target.blit(layers['front'], (0, 0))
        if target is not surface:
            target.set_alpha(round(255 * alpha))
            surface.blit(target, (0, 0))
            target.set_alpha(None)

    def _title_layers(self, title, size):
        """The title's layers at the frame's height: the sky and the front cut to the frame, the clouds whole (they
        wrap) at their opacity."""
        found = self._title
        if found is None or found['size'] != size:
            width, height = size
            title_w = round(height * 16 / 9)
            left = round((title_w - width) * TITLE_X)

            def cut(image):
                return pygame.transform.smoothscale(image, (title_w, height)).subsurface(
                    (left, 0, width, height)).copy()
            clouds = pygame.transform.smoothscale(self.image(title['clouds']['id']), (title_w, height))
            clouds.fill((255, 255, 255, round(255 * title['clouds']['opacity'])), special_flags=pygame.BLEND_RGBA_MULT)
            found = self._title = dict(size=size, width=title_w, left=left, sky=cut(self.image(title['sky'])).convert(),
                                       clouds=clouds, front=cut(self.image(title['front'])), rays={})
        return found

    def _title_ray(self, title, size, k):
        """Ray glint `k` cut to the frame (made the first time it shows)."""
        layers = self._title_layers(title, size)
        found = layers['rays'].get(k)
        if found is None:
            frame = title['rays']['frames'][k]
            atlas = self.image(title['rays']['atlas'])
            x0, y0, x1, y1 = frame['box']
            title_w, height = layers['width'], size[1]
            glint = pygame.transform.smoothscale(atlas.subsurface(frame['rect']),
                                                 (max(1, round((x1 - x0) * title_w)), max(1, round((y1 - y0) * height))))
            found = pygame.Surface(size, pygame.SRCALPHA)
            found.blit(glint, (round(x0 * title_w) - layers['left'], round(y0 * height)))
            layers['rays'][k] = found
        return found

    def _place_backdrop(self, surface, alpha):
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
        self._now = now
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
        if 'parts' in booth:
            self._deck_parts(surface, arena, booth['parts'], size, deck_dy, now)
        else:
            self._deck_piece(surface, self.image(booth['pieces']['deck']['id']), booth['pieces']['deck']['box'], size,
                             deck_dy)
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
        self._hit_effects(surface, arena, ring, now)
        self._hud_x360(surface, arena, session, now, 0)
        self._popups_x360(surface, arena, ring)
        prompt = False
        for bubble in arena.bubbles:
            if bubble is not None and bubble[0]:
                # The 3-2-1 is before the game itself: "press ok to start", not "...start practice." (tutorial)
                prompt = prompt or bubble[0].strip().casefold().rstrip('.!') == START_PROMPT
                self._bubble_x360(surface, arena, ring, bubble[0], bubble[2], bubble[1], now)
        self._countdown(surface, arena, ring, now, prompt)

    def _arm_press(self, arena, now):
        """Starts the tone arm's PUSH on a press of OK that plays (it restarts on one during it, as the X360's does), not
        one that closes a prompt (owner, 2026-11-01). Decided by the frame before the press, since closing a bubble takes
        it away before the next is drawn: nothing showing, time left, not the number keys' game and the ring turning,
        which takes in a tutorial's practice with the turntable. Then the library must take the key: between a tutorial's
        bubbles it leaves it queued. OK's feedback (right or wrong) is play in any case."""
        held = arena.button_ms[0]
        if held > 0 and held > self._arm_held:              # 0 is the press itself, before the panel's next tick
            self._arm_waiting, self._arm_taken = self._arm_clear, False
        self._arm_held = held
        if held == -1:
            self._arm_waiting = False
        elif not self._arm_taken and (arena.feedback in (1, 2) or (self._arm_waiting and not arena.keys)):
            self._arm_start, self._arm_taken, self._arm_waiting = now, True, False
        self._arm_clear = (not any(arena.bubbles) and arena.time_up == 0 and arena.timer_ms != 0 and not arena.keypad
                           and arena.motion in (-1, 1))

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
        note = self._note_of(item)
        if note is not None:
            resource = self.x360()[0]['booth']['notes']['kinds'][note[0]]['id']
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
            drawn = self._item_x360(surface, arena, arena.slots[slot], arena.item_kind, x, y, arena.tint[slot], index=slot)
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

    def _note_of(self, item):
        """The booth's (picture, effects) for New Rules' item picture `item` (ITEM_NOTES), or None."""
        name = self._picture_name(item)
        note = ITEM_NOTES.get(int(name.split('/')[1])) if name else None
        return note if note and 'notes' in self.x360()[0]['booth'] else None

    def _item_x360(self, surface, arena, item, kind, x, y, tint, alpha=255, index=0):
        """An item standing at (x, y): the rect drawn, in canvas pixels, or None. A note is the booth's, as large as Diss
        Practice's camera has it that far round the record. A popup's fades (`alpha`) keep the flat picture."""
        if item == -1:
            return None
        if kind == 2:
            note = self._note_of(item)
            if note is not None and alpha == 255:
                ring = self._field(arena)
                across = max(-1, min(1, (y - ring.centery) / max(1, ring.height / 2)))
                depth = self._project(0, -NOTE_ROW * across)[2]
                return self._stand_note(surface, note[0], note[1], x, y, depth, 1, self._now, index)
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
        """OK's feedback at the needle (the selector): a glow while it's pressed, green for right, red for wrong (708).
        The needle follows the tone arm where the deck has one, whose swing is itself the press; a deck in one piece
        shows a white glow for a press with no feedback."""
        if arena.button_ms[0] == -1:
            return
        parts = self.x360()[0]['booth'].get('parts')
        colour = {1: (60, 255, 80), 2: (255, 60, 50)}.get(arena.feedback, None if parts else (255, 255, 230))
        if colour is None:
            return
        k = self.k
        radius = round(16 * k)
        glow = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        for r in range(radius, 0, -max(1, radius // 8)):
            pygame.draw.circle(glow, (*colour, round(150 * (1 - r / radius)) + 20), (radius, radius), r)
        x, y = ring.centerx, ring.bottom
        if parts:
            frame = self._arm_frame(parts['arm'], self._now)
            x, y, _, _ = self._to_native(frame['tip'] * 2)
        surface.blit(glow, (round(x * k) - radius, round(y * k) - radius))

    def _hit_effects(self, surface, arena, ring, now):
        """Diss Practice's hit effects (FX), where the X360 shows them on a note it eats: on OK's feedback (708: 1
        right, 2 wrong) at the item under the selector, or, in a game played by number keys (Sequences), at the item
        whose key flashes (766). Drawn only: nothing the game sees changes."""
        # A new press: OK's 250 ms highlight starts (or restarts, under presses faster than it lasts).
        held = arena.button_ms[0]
        if held == -1 or held > self._fx_held:
            self._fx_pressed = False
        self._fx_held = held
        if held != -1 and not self._fx_pressed and arena.feedback in (1, 2):
            self._fx_pressed = True
            slot = arena.slot_under() if len(arena.slots) else -1
            if 0 <= slot < len(arena.slots) and arena.slots[slot] != -1:
                x, y = self._slot_point(arena, ring, slot, vertical=0)
            else:
                x, y = ring.centerx, ring.bottom
            self._spawn('good' if arena.feedback == 1 else 'bad', x, y, now)
        if arena.keypad and arena.keypad_flash_ms > self._fx_flash_ms and 0 <= arena.keypad_flash < len(arena.slots):
            # Sequences gives no OK feedback; its "+n" / "-n" popup, thrown as the key is taken, says which.
            x, y = self._slot_point(arena, ring, arena.keypad_flash, vertical=0)
            sign = self._fresh_popup_sign(arena)
            self._spawn('bad' if sign == '-' or (sign is None and arena.feedback == 2) else 'good', x, y, now)
        self._fx_flash_ms = arena.keypad_flash_ms
        self.effects = [e for e in self.effects if 0 <= now - e[3] < FX[e[0]]['life']]
        for effect in self.effects:
            self._draw_effect(surface, effect, now)

    @staticmethod
    def _fresh_popup_sign(arena):
        """'+' or '-' from a text popup (747) only just thrown, or None."""
        for popup in arena.popups:
            if popup.kind == 1 and popup.elapsed_ms < 150 and 0 <= popup.value < len(arena.strings):
                text = (arena.strings[popup.value] or '').strip().lstrip('`~')
                if text[:1] in '+-' and text[:1]:
                    return text[0]
        return None

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
        """A bubble on the slot machine's panel, where New Rules puts it (method_449's placing); in Rhythm's tutorial
        the Diss Practice card for the item it points at (decision 4)."""
        images = self.wrapped('casual', text, 24, BUBBLE_TEXT_WIDTH, (20, 20, 30), (190, 20, 20))
        k = self.k
        art, edges, box_top, below, narrowest = self.panel_art() or self.bubble_art()
        inner_w = max((im.get_width() for im in images), default=0) / k
        inner_h = sum(im.get_height() / k - 8 for im in images)
        w = min(SCREEN_WIDTH - 8, max(narrowest, inner_w + 36))
        h = box_top + inner_h + below                       # the flourish or tail above the box, then text
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
        h = sum(im.get_height() / k - 8 for im in images) + 46 + len(options) * 30      # (dark text vanishes on its ink)
        x, y = OX + (SCREEN_WIDTH - w) / 2, (SCREEN_HEIGHT - h) / 2
        self._nine(surface, self.trimmed("info_box"), x, y, w, h, 18)
        top = y + 14
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
