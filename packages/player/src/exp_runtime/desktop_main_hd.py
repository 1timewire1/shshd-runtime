"""The iOS HD main menu (`SHSEngine::setAppMode(101)` and `animateMainMenuButtonsIn`), in HD's 768 x 1024 point frame.

Decompiled and fitted to `reference/screenshots/main menu/IMG_0124`:

* Four art layers over the frame: wood (resource 6, x1.25), the photo (9, x1, tilted in the art), the dark ribbon (8, x1.25,
  tilted 6 degrees at (384, 212)) and the title (7, x1.25 at (384, 218)); `HdUi.main_backdrop`.
* The first time in, the photo zooms in from 10x while turning up from -30 degrees, starting 0.4 s in over 1.9375 s (scale
  keyframes 10 -> 1 at 88.2%, 1.1 at 94.1%, 1 at 100% of 1.7 s); the ribbon grows from nothing (scale y over 0.6 s) and the
  title fades in over the same 0.6 s, both from 2.6 s. Coming back from another screen only the buttons slide in.
* The buttons (layout 74's nodes, pack 315) come and go with `animateMainMenuButtonsIn(p)` / `Out(p)` (SHS HD `000233ac` /
  `0002323c`, CoD 1.4.7 the same at iPhone scale). `p` is 1.5 the first time in (`setAppMode(101)`) and 0 otherwise.
  - Each layer gets `createMainMenuAnimation{In,Out}ForLayer(layer, base, d)` (`0001b9a8` / `0001bda0`), a keyframe
    animation that begins at base + d, lasts d + 0.35 s and holds its first value until key time d / (d + 0.35).
    Each layer therefore moves from 2d to 2d + 0.35 s (`layer_progress`).
  - In (base = now, d = p + 0.08 k): the wedge, then Play/Resume, Now Airing, Episodes On Demand and More EA Games
    translate -550 -> +5 (key time 0.96) -> 0. The gear (+0x1e0) scales 0.01 -> 1.2 -> 1 with d = p + 0.36. The info button
    (+0x1dc) fades 0 -> 1 over 0.6 s from 2p + 0.32 (`createFadeAnimationForLayer`). Which layer is which was settled
    against the iPad (owner, 2026-10-20), as Android's menu also does (docs/MAIN_MENU.md).
  - Out (base = now + p, d = 0.36 / 0.32 / 0.24 / 0.16 / 0.08 for the wedge .. More EA Games, 0 for the gear):
    0 -> +5 (key time d / (d + 0.35) + 0.04) -> -550, the gear 1 -> 1.2 -> 0. The info button fades 1 -> 0 over 0.6 s
    from 3p + 0.08.
  - The doubled delay was missed at first (the buttons were 0.08 s apart), and PR #9 slowed them 1.6x to make up for it.
  - Out runs whenever a main-menu option is taken (`SHSEngine::buttonPressed`; Play/Resume's episode menu through
    `setAppMode`, which also zooms that menu in: `animateView(20)`).
* Labels are the embedded glyph fonts 593 (brown) and 594 (green, "More EA Games"), 48 pixels tall at 1 px per point.

Not decompiled: the exact origin of the button group (fitted to the photo).
"""
from functools import lru_cache

import pygame

from .hd_ui import HdUi, S, FRAME
from .menu import MenuFont

INTRO_PHOTO_START, INTRO_PHOTO_ZOOM, INTRO_PHOTO_TURN = 0.4, 1.7, 1.9375
INTRO_STRIP_START, INTRO_STRIP_TIME = 2.6, 0.6
BUTTONS_START_INTRO = 1.5             # `animateMainMenuButtonsIn(1.5)` (SHS HD 00027916; CoD the same)
# Each layer's animation (see the docstring): 0.35 s of movement after its delay, held twice.
SLIDE_TIME, STAGGER, GEAR_DELAY = 0.35, 0.08, 0.36
OUT_DELAYS, GEAR_OUT_DELAY = (0.36, 0.32, 0.24, 0.16, 0.08), 0.0     # the wedge .. More EA Games, then the gear
INFO_FADE, INFO_IN_AT, INFO_OUT_AT = 0.6, 0.32, 0.08
SLIDE_FROM, SLIDE_OVERSHOOT = -550.0, 5.0
READY_AFTER = 2 * GEAR_DELAY + SLIDE_TIME           # after the last layer (the gear) has settled
LEAVE_TIME = 2 * OUT_DELAYS[0] + SLIDE_TIME         # the slide out, until the wedge has gone
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


def layer_progress(age, delay):
    """How far through its keyframes a `createMainMenuAnimation*ForLayer` layer is `age` seconds after the call, for a
    delay `delay`. It begins at `delay` and lasts `delay + SLIDE_TIME`; returns (fraction 0..1, the hold's key time)."""
    duration = delay + SLIDE_TIME
    return max(0.0, min(1.0, (age - delay) / duration)), delay / duration


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
    # The info button's frames (pack 315), (at rest, pressed). SHS HD draws 14 at rest and 15 pressed; here they are
    # the other way round (owner's choice, 2026-10-20) so the button at rest does not look highlighted next to the
    # keyboard's highlight. CoD's own states already read that way (desktop_cod_main.CodMainMenu).
    INFO_FRAMES = (15, 14)

    def __init__(self, library):
        super().__init__(library)
        self.canvas = pygame.Surface((FRAME[0] * S, FRAME[1] * S)).convert()
        self.age = 0.0
        self.intro = False
        self.leaving = None             # the age the buttons started to slide out (`animateMainMenuButtonsOut`)
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
        self.age, self.intro, self.pressed, self.leaving = 0.0, intro, None, None

    def leave(self):
        """A main-menu option was taken: the buttons slide out (`animateMainMenuButtonsOut(0)`). Input closes."""
        if self.leaving is None:
            self.leaving, self.pressed = self.age, None

    @property
    def left(self):
        """Whether the buttons have slid out completely."""
        return self.leaving is not None and self.age - self.leaving >= LEAVE_TIME

    def tick(self, seconds):
        self.age += seconds

    @property
    def buttons_start(self):
        return BUTTONS_START_INTRO if self.intro else 0.0

    @property
    def ready(self):
        return self.leaving is None and self.age >= self.buttons_start + READY_AFTER

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
        if self.leaving is not None:
            progress, hold = layer_progress(self.age - self.leaving, OUT_DELAYS[index])
            return keyframes((0, hold, hold + .04, 1), (0.0, 0.0, SLIDE_OVERSHOOT, SLIDE_FROM), progress)
        progress, hold = layer_progress(self.age, self.buttons_start + STAGGER * index)
        return keyframes((0, hold, .96, 1), (SLIDE_FROM, SLIDE_FROM, SLIDE_OVERSHOOT, 0.0), progress)

    def pop(self):
        """The gear's scale: in 0.01 -> 1.2 -> 1, out 1 -> 1.2 -> 0."""
        if self.leaving is not None:
            progress, hold = layer_progress(self.age - self.leaving, GEAR_OUT_DELAY)
            return keyframes((0, hold, hold + .04, 1), (1.0, 1.0, 1.2, 0.0), progress)
        progress, hold = layer_progress(self.age, self.buttons_start + GEAR_DELAY)
        return keyframes((0, hold, .96, 1), (0.01, 0.01, 1.2, 1.0), progress)

    def info_alpha(self):
        """The info button's opacity (`createFadeAnimationForLayer`, 0.6 s): in from 2p + 0.32, out from 3p + 0.08
        (p = 0)."""
        if self.leaving is not None:
            return 1.0 - max(0.0, min(1.0, (self.age - self.leaving - INFO_OUT_AT) / INFO_FADE))
        return max(0.0, min(1.0, (self.age - 2 * self.buttons_start - INFO_IN_AT) / INFO_FADE))

    _photo_1x = None        # (the photo, its copy at 1 pixel per point) for the intro's turn

    def draw_photo(self, layer):
        photo = self.main_layers()[1][0]
        t = self.age - INTRO_PHOTO_START
        if not self.intro or t >= INTRO_PHOTO_ZOOM and t >= INTRO_PHOTO_TURN:
            layer.blit(photo, photo.get_rect(center=(384 * S, 512 * S)))
            return
        zoom = keyframes((0, .882, .941, 1), (10.0, 1.0, 1.1, 1.0), max(0.0, t) / INTRO_PHOTO_ZOOM)
        turn = -30.0 * (1 - min(1.0, max(0.0, t) / INTRO_PHOTO_TURN))
        # Turned at 1 pixel per point and then scaled up: rotozoom at S had to write the whole turned square (about
        # 13 million pixels, ~155 ms a frame); a quarter of that, and only the part inside the frame scaled up. A
        # 1080p window shows the frame at about 1 pixel per point anyway, and the settled photo is drawn at S.
        if self._photo_1x is None or self._photo_1x[0] is not photo:
            self._photo_1x = photo, pygame.transform.smoothscale(photo, (photo.get_width() // S,
                                                                        photo.get_height() // S))
        small = self._photo_1x[1]
        span = (FRAME[0] + FRAME[1]) / zoom                    # the frame's diagonal in photo pixels
        crop = pygame.Rect(0, 0, min(small.get_width(), round(span)), min(small.get_height(), round(span)))
        crop.center = small.get_rect().center
        image = pygame.transform.rotozoom(small.subsurface(crop), turn, zoom)
        placed = image.get_rect(center=(FRAME[0] // 2, FRAME[1] // 2))
        visible = placed.clip(pygame.Rect((0, 0), FRAME))
        if visible.width > 0 and visible.height > 0:
            piece = image.subsurface(visible.move(-placed.x, -placed.y))
            layer.blit(pygame.transform.smoothscale(piece, (visible.width * S, visible.height * S)),
                       (visible.x * S, visible.y * S))

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
        scale, alpha = self.pop(), self.info_alpha()
        x, y = ox + nx * 2, oy + ny * 2
        gear_pieces = self.piece((nw, nh), self.pressed == ('options',))
        gear = self.layouts.frame(315, 13)
        surface = pygame.Surface((nw * 2 * S, nh * 2 * S), pygame.SRCALPHA)
        for image, (px, py, pw, ph) in gear_pieces:
            surface.blit(pygame.transform.smoothscale(image, (max(1, round(pw * S)), max(1, round(ph * S)))), (round(px * S), round(py * S)))
        surface.blit(pygame.transform.smoothscale(gear, (gear.get_width() * S, gear.get_height() * S)),
                     (surface.get_width() // 2 - gear.get_width() * S // 2, surface.get_height() // 2 - gear.get_height() * S // 2))
        center = (round((x + nw) * S), round((y + nh) * S))
        if scale > 0.005:
            if scale != 1.0:
                surface = pygame.transform.smoothscale(surface, (max(1, round(surface.get_width() * scale)),
                                                                 max(1, round(surface.get_height() * scale))))
            layer.blit(surface, surface.get_rect(center=center))
        info = self.layouts.frame(315, self.INFO_FRAMES[1 if self.pressed == ('help',) else 0])
        if alpha > 0:
            info = pygame.transform.smoothscale(info, (max(1, round(info.get_width() * S)), max(1, round(info.get_height() * S))))
            if alpha < 1:
                info.set_alpha(round(255 * alpha))
            layer.blit(info, info.get_rect(center=(INFO_CENTER[0] * S, INFO_CENTER[1] * S)))
        if self.ready:
            self.hits.append((pygame.Rect(round(x), round(y), nw * 2, nh * 2), ('options',)))
            self.hits.append((pygame.Rect(INFO_CENTER[0] - 42, INFO_CENTER[1] - 42, 84, 84), ('help',)))
