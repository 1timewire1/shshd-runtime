"""The iOS HD main menu (`SHSEngine::setAppMode(101)` and `animateMainMenuButtonsIn`), in HD's 768 x 1024 point frame.

Decompiled and fitted to `reference/screenshots/main menu/IMG_0124`:

* Four art layers over the frame: wood (resource 6, x1.25), the photo (9, x1, tilted in the art), the dark ribbon (8, x1.25,
  tilted 6 degrees at (384, 212)) and the title (7, x1.25 at (384, 218)); `HdUi.main_backdrop`.
* The first time in, the photo zooms in from 10x while turning up from -30 degrees, starting 0.4 s in over 1.9375 s (scale
  keyframes 10 -> 1 at 88.2%, 1.1 at 94.1%, 1 at 100% of 1.7 s); the ribbon grows from nothing (scale y over 0.6 s) and the
  title fades in over the same 0.6 s, both from 2.6 s; the buttons start 3.2 s in. Coming back from another screen only the
  buttons slide in.
* The buttons (layout 74's nodes, pack 315) slide in from 550 points to the left over 0.35 s (with a 5 point overshoot at
  96%): the wedge first, then Play/Resume, Now Airing, Episodes On Demand and More EA Games 0.08 s apart, the gear then
  the info button popping in (scale 0.01 -> 1.2 -> 1) 0.36 s after the wedge. Input opens 0.35 + 0.36 s after the start.
* Labels are the embedded glyph fonts 593 (brown) and 594 (green, "More EA Games"), 48 pixels tall at 1 px per point.

Not decompiled: the exact origin of the button group (fitted to the photo) and the gear's fade-in timing.
"""
from functools import lru_cache

import pygame

from .hd_ui import HdUi, S, FRAME
from .menu import MenuFont

INTRO_PHOTO_START, INTRO_PHOTO_ZOOM, INTRO_PHOTO_TURN = 0.4, 1.7, 1.9375
INTRO_STRIP_START, INTRO_STRIP_TIME = 2.6, 0.6
BUTTONS_START_INTRO = 3.2
SLIDE_TIME, STAGGER, INFO_DELAY = 0.35, 0.08, 0.36
SLIDE_FROM, SLIDE_OVERSHOOT = -550.0, 5.0
READY_AFTER = INFO_DELAY + SLIDE_TIME
# Layout 74 (the widget the buttons come from) is 275 x 135 units; its origin on the frame, fitted to the photo.
GROUP_ORIGIN = (0.0, 744.0)
BUTTON_NODES = ((13, 2.5, 205, 28), (37.5, 36.5, 205, 28), (27.5, 70, 205, 28), (7, 104, 155, 28))   # units
GEAR_NODE = (174, 104, 39, 28)
INFO_CENTER = (726, 983)
STRING_PLAY, STRING_AIRING, STRING_DEMAND, STRING_MORE = 118, 119, 83, 230
COMMANDS = (('play',), ('airing',), ('demand',), ('more',), ('options',), ('help',))
# The fourth button switches games (upstream's Switch Game) and is labelled with the other game's name; one too wide
# for the button takes its short form (owner's choice, 2026-10-14).
SHORT_TITLES = {'Surviving High School': 'Surviving HS'}
SWITCH_MARGIN = 6                       # points kept clear at each end of the 155-unit (310-point) button


def keyframes(times, values, t):
    """Linear interpolation over keyframes (`times` ascending in 0..1), holding the ends."""
    if t <= times[0]:
        return values[0]
    for (t0, v0), (t1, v1) in zip(zip(times, values), zip(times[1:], values[1:])):
        if t <= t1:
            return v0 + (v1 - v0) * ((t - t0) / (t1 - t0) if t1 > t0 else 1)
    return values[-1]


class HdMainMenu(HdUi):
    hd_layer = True
    LABELS = (STRING_PLAY, STRING_AIRING, STRING_DEMAND, STRING_MORE)      # the four buttons' string ids

    def __init__(self, library):
        super().__init__(library)
        self.canvas = pygame.Surface((FRAME[0] * S, FRAME[1] * S)).convert()
        self.age = 0.0
        self.intro = False
        self.hits = []
        self.pressed = None
        self.fonts = None
        self.switch_title = None        # the other game's title; None keeps the native "More EA Games"

    @staticmethod
    def available(library):
        try:
            return library is not None and library.hd_ipa is not None and all(
                library.hd_raw_resource(i) is not None for i in (6, 7, 8, 9, 15, 17, 315, 593, 594))
        except Exception:
            return False

    def start(self, *, intro):
        """Enter the screen: `intro` runs the first-launch entrance, otherwise only the buttons slide in."""
        self.age, self.intro, self.pressed = 0.0, intro, None

    def tick(self, seconds):
        self.age += seconds

    @property
    def buttons_start(self):
        return BUTTONS_START_INTRO if self.intro else 0.0

    @property
    def ready(self):
        return self.age >= self.buttons_start + READY_AFTER

    # ------------------------------------------------------------ art

    def glyph_fonts(self):
        if self.fonts is None:
            self.fonts = [MenuFont.parse(self.library.hd_raw_resource(i)) for i in (593, 594)]
        return self.fonts

    def switch_text(self):
        """The fourth button's label: the other game's title, or its short form when that is too wide."""
        room = BUTTON_NODES[3][2] * 2 - 2 * SWITCH_MARGIN
        if self.label(self.switch_title, 1).get_width() / S <= room:
            return self.switch_title
        return SHORT_TITLES.get(self.switch_title, self.switch_title)

    @lru_cache(maxsize=16)
    def label(self, text, variant):
        font = self.glyph_fonts()[variant]
        widths = [font.space if c == ' ' else (font.glyph(c).width + font.tracking if font.glyph(c) else font.space) for c in text]
        surface = pygame.Surface((max(1, sum(widths) - font.tracking), font.height), pygame.SRCALPHA).convert_alpha()
        x = 0
        for c, width in zip(text, widths):
            glyph = font.glyph(c)
            if c != ' ' and glyph:
                surface.blit(pygame.image.frombytes(glyph.pixels, (glyph.width, glyph.height), 'RGBA').convert_alpha(), (x, 0))
            x += width
        return pygame.transform.smoothscale(surface, (surface.get_width() * S, surface.get_height() * S))

    def piece(self, size_units, pressed=False):
        """A three-piece button drawn from layout 75 / 77 at a width of `size_units` (units, half points)."""
        pieces = []
        for _, node, visible, (x, y, w, h) in self.layouts.nodes(77 if pressed else 75, size=size_units):
            if node.kind != 1 or w <= 0 or h <= 0:
                continue
            image = self.layouts.frame(self.layouts.pack_for(*node.payload), node.payload[1])
            if image is not None:
                pieces.append((image, (x * 2, y * 2, w * 2, h * 2)))
        return pieces

    def draw_piece(self, layer, pieces, x, y):
        for image, (px, py, pw, ph) in pieces:
            layer.blit(pygame.transform.smoothscale(image, (max(1, round(pw * S)), max(1, round(ph * S)))),
                       (round((x + px) * S), round((y + py) * S)))

    # ------------------------------------------------------------ animation

    def slide(self, index):
        """The x offset (points) of the `index`th sliding layer (0 wedge, 1-4 buttons)."""
        t = self.age - self.buttons_start - (0 if index == 0 else STAGGER * index)
        if t <= 0:
            return SLIDE_FROM
        progress = min(1.0, t / SLIDE_TIME)
        return keyframes((0, .96, 1), (SLIDE_FROM, SLIDE_OVERSHOOT, 0.0), progress)

    def pop(self, delay):
        t = self.age - self.buttons_start - delay
        if t <= 0:
            return 0.01
        return keyframes((0, .96, 1), (0.01, 1.2, 1.0), min(1.0, t / SLIDE_TIME))

    def draw_photo(self, layer):
        photo = self.main_layers()[1][0]
        t = self.age - INTRO_PHOTO_START
        if not self.intro or t >= INTRO_PHOTO_ZOOM and t >= INTRO_PHOTO_TURN:
            layer.blit(photo, photo.get_rect(center=(384 * S, 512 * S)))
            return
        zoom = keyframes((0, .882, .941, 1), (10.0, 1.0, 1.1, 1.0), max(0.0, t) / INTRO_PHOTO_ZOOM)
        turn = -30.0 * (1 - min(1.0, max(0.0, t) / INTRO_PHOTO_TURN))
        # Only the part of the photo that can land inside the frame needs scaling.
        span = (FRAME[0] + FRAME[1]) * S / zoom / S            # the frame's diagonal in photo pixels (x S)
        crop = pygame.Rect(0, 0, min(photo.get_width(), round(span * S)), min(photo.get_height(), round(span * S)))
        crop.center = photo.get_rect().center
        piece = photo.subsurface(crop)
        image = pygame.transform.rotozoom(piece, turn, zoom)
        layer.blit(image, image.get_rect(center=(384 * S, 512 * S)))

    def draw_ribbon_title(self, layer):
        layers = self.main_layers()
        (ribbon, ribbon_center), (title, title_center) = layers[2], layers[3]
        t = self.age - INTRO_STRIP_START
        progress = 1.0 if not self.intro else max(0.0, min(1.0, t / INTRO_STRIP_TIME))
        if progress > 0:
            image = ribbon if progress >= 1 else pygame.transform.smoothscale(
                ribbon, (ribbon.get_width(), max(1, round(ribbon.get_height() * progress))))
            layer.blit(image, image.get_rect(center=(round(ribbon_center[0] * S), round(ribbon_center[1] * S))))
            fade = title if progress >= 1 else title.copy()
            if progress < 1:
                fade.set_alpha(round(255 * progress))
            layer.blit(fade, fade.get_rect(center=(round(title_center[0] * S), round(title_center[1] * S))))

    # ------------------------------------------------------------ drawing

    def draw(self, *, buttons=True):
        """Render into the 2x canvas; `self.hits` lists the buttons (points, command) once input is open. With
        `buttons` off (a window is open over the menu) only the backdrop is drawn."""
        layer = self.canvas
        wood = self.main_layers()[0][0]
        layer.blit(wood, wood.get_rect(center=(384 * S, 512 * S)))
        self.draw_photo(layer)
        self.draw_ribbon_title(layer)
        self.hits = []
        if not buttons:
            return layer
        ox, oy = GROUP_ORIGIN
        # The wedge: layout 74's two backdrop pieces (pack 315 frames 0 and 1, from layout 79), 13 units down.
        wedge_x = ox + self.slide(0)
        for _, node, visible, (x, y, w, h) in self.layouts.nodes(74):
            if node.kind == 1 and w > 0 and h > 0:
                image = self.layouts.frame(self.layouts.pack_for(*node.payload), node.payload[1])
                layer.blit(pygame.transform.smoothscale(image, (round(w * 2 * S), round(h * 2 * S))),
                           (round((wedge_x + x * 2) * S), round((oy + y * 2) * S)))
        strings = self.strings()
        labels = tuple(strings[i] for i in self.LABELS)
        if self.switch_title:
            labels = labels[:3] + (self.switch_text(),)
        for index, ((nx, ny, nw, nh), text) in enumerate(zip(BUTTON_NODES, labels)):
            x, y = ox + nx * 2 + self.slide(index + 1), oy + ny * 2
            command = COMMANDS[index]
            pieces = self.piece((nw, nh), self.pressed == command)
            self.draw_piece(layer, pieces, x, y)
            image = self.label(text, 1 if index == 3 else 0)
            layer.blit(image, image.get_rect(center=(round((x + nw) * S), round((y + nh) * S))))
            if self.ready:
                self.hits.append((pygame.Rect(round(ox + nx * 2), round(y), nw * 2, nh * 2), command))
        self.draw_gear_info(layer, ox, oy)
        return layer

    def draw_gear_info(self, layer, ox, oy):
        nx, ny, nw, nh = GEAR_NODE
        scale = self.pop(INFO_DELAY)
        x, y = ox + nx * 2, oy + ny * 2
        gear_pieces = self.piece((nw, nh), self.pressed == ('options',))
        gear = self.layouts.frame(315, 13)
        surface = pygame.Surface((nw * 2 * S, nh * 2 * S), pygame.SRCALPHA)
        for image, (px, py, pw, ph) in gear_pieces:
            surface.blit(pygame.transform.smoothscale(image, (max(1, round(pw * S)), max(1, round(ph * S)))), (round(px * S), round(py * S)))
        surface.blit(pygame.transform.smoothscale(gear, (gear.get_width() * S, gear.get_height() * S)),
                     (surface.get_width() // 2 - gear.get_width() * S // 2, surface.get_height() // 2 - gear.get_height() * S // 2))
        if scale != 1.0:
            surface = pygame.transform.smoothscale(surface, (max(1, round(surface.get_width() * scale)), max(1, round(surface.get_height() * scale))))
        center = (round((x + nw) * S), round((y + nh) * S))
        layer.blit(surface, surface.get_rect(center=center))
        info = self.layouts.frame(315, 15 if self.pressed == ('help',) else 14)
        info = pygame.transform.smoothscale(info, (max(1, round(info.get_width() * S * scale)), max(1, round(info.get_height() * S * scale))))
        layer.blit(info, info.get_rect(center=(INFO_CENTER[0] * S, INFO_CENTER[1] * S)))
        if self.ready:
            self.hits.append((pygame.Rect(round(x), round(y), nw * 2, nh * 2), ('options',)))
            self.hits.append((pygame.Rect(INFO_CENTER[0] - 42, INFO_CENTER[1] - 42, 84, 84), ('help',)))
