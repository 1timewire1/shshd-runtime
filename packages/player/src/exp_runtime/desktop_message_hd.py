"""The iOS message panel (script service 33, "Instructions", "The End", Cause of Death's "Thanks for playing!").

Decompiled (`SHSUIForm::initForm`, `internalTransitionOn`, `tick`, `getTimerText`, `GameModel::expandContinue`) and
checked against the owner's photos (`dialouge/IMG_0240`-`0242`). SHS HD's numbers below are in frame points (768 x
1024); Cause of Death runs the same code (CoD 1.4.7 0004f054...) on its own layout bank, which is HD's at half size,
so `CodMessageRenderer` keeps every rule in CoD points and draws them at 2x from the CoD column's origin.

The form is HD layout 24 (widget 0x18), 560 points wide, centered on x 384. Its body text region (node 0x18,
at (36, 30), 488 wide) is resized to the text's height (ArialRoundedMTBold 28 pt, (41, 104, 221), left aligned
from the top, wrapped) plus one, rounded up to even, and the widget grows with it; it never shrinks below its
authored 256. Above it sits a header: layout 25 (94 points, title region node 0x17, 520 x 50) or, when the title
(ArialRoundedMTBold 40 pt, centered both ways, wrapped) is taller than 50, layout 27 (156 points, node 0xe).
The footer (layout 3) hangs 66 points below. With `total = header + height + 33` (rounded up to even) the body's
top is `header + (1024 - total) / 2`. The title is drawn 4 points below its region's top.

The continue pill is the shared `g_layerContinue` (the dialogue's): centered at the bubble's inner width - 99 and
17 points below its inner bottom, where the bubble (the dialogue box, 560 wide, `total` tall) is centered on
`body top + height / 2 + 33 - header / 2`. Its label reads "Wait (n)" until the reading gate opens and then
"Continue" (HD strings 27 / 26); the footer hint is string 36 then 33. The pill grows in over 0.25 s.
Drawn 2x supersampled, so layer pixels are the HD art's native pixels.
"""
import math
from functools import lru_cache

from . import graphics as pygame

from .content import ContentError
from .hd_layout import BankLayouts, HdLayouts, STRINGS_ID
from .location_pan import default_ease
from .menu import MenuStrings
from .ui_assets import UIAssetError
from .vector_text import system_font_path

from .hd_scale import S
FRAME = (768, 1024)
BLUE = (41, 104, 221)
# Arial Bold (the fallback when Arial Rounded MT Bold is not installed) sets the same text about 1% narrower
# than HD (480 vs 485 points for "Then tune-in each week! Go to 'Now"), enough to change line breaks.
FALLBACK_WIDTH = 1.0104
# 1-based walk numbers of the two header subtrees in layout 24 (short = node 0xf, tall = node 6).
TALL_HEADER_NODE, SHORT_HEADER_NODE = 6, 15
LAYOUT = 24


class HdMessageRenderer:
    hd_layer = True
    edge_bar = 'bar'

    # The form's own points (SHS HD: frame points), and where they sit in the frame.
    K = 1                                       # frame points per form point
    ORIGIN = (0, 0)
    SCREEN = FRAME
    WIDTH = 560
    BODY = (36, 30, 488, 196)                   # node 0x18 in the widget
    MIN_HEIGHT = 256
    SHORT_HEADER, TALL_HEADER = 94, 156
    SHORT_TITLE, TALL_TITLE = (20, -72, 520, 50), (20, -132, 520, 108)   # nodes 0x17 and 0xe
    FOOTER = 66                                 # layout 3; the bubble reaches half of it past the widget
    BODY_INSET = 6                              # the form's layer starts this far in from each side
    BUBBLE_EDGE = 20                            # the bubble's border, outside its inner rectangle
    PILL_INSET, PILL_DROP = 99, 17              # GameModel::expandContinue
    TITLE_DROP = 4
    TITLE_POINTS, BODY_POINTS, LABEL_POINTS = 40, 28, 28
    # Where HD's CSFont puts a line's top relative to pygame's, measured on the photos (points).
    TITLE_NUDGE, BODY_NUDGE = 2, -5
    NODE_POINTS = 2                             # form points per unit HdLayouts reports (its half points)
    INK = BLUE
    PILL_FRAME = 10                             # pack 155, the blue continue pill
    LABELS = (26, 27, 33, 36)                   # Continue, Wait, the ready and the waiting hints
    BUBBLE_THEME = 1                            # setBubbleSex(1)
    TITLE_FADE = False

    def __init__(self, resources, art):
        self.resources, self.art = resources, art
        self.canvas = pygame.Surface((FRAME[0] * S, FRAME[1] * S), pygame.SRCALPHA).convert_alpha()
        self.pending_background = None
        self.pending_background_origin = (160, 180)
        self.footer_text = ''

    def form_layouts(self):
        return HdLayouts(self.resources.library)

    _layouts = None

    @property
    def layouts(self):
        """The form's layout bank reader, made on first use (a Desktop builds every renderer up front)."""
        if self._layouts is None:
            self._layouts = self.form_layouts()
        return self._layouts

    _rounded = ''

    def rounded_path(self):
        """The Arial Rounded face's file, or None; looked up once (the search scans the library's fonts folder)."""
        if self._rounded == '':
            self._rounded = system_font_path('arial-rounded', self.resources.library)
        return self._rounded

    def available(self):
        try:
            return (self.art.hd_chrome() and self.layouts.bank() is not None and self.rounded_path() is not None)
        except (AttributeError, ValueError):
            return False

    @lru_cache(maxsize=4)
    def font(self, points, role='arial-rounded'):
        """A face at `points` form points, sized for the layer (S pixels per frame point)."""
        return pygame.font.Font(system_font_path(role, self.resources.library), round(points * self.K * S))

    @lru_cache(maxsize=1)
    def strings(self):
        return MenuStrings.parse(self.resources.library.hd_raw_resource(STRINGS_ID))

    def wrap(self, text, points, width):
        """Lines of `text` wrapped at `width` points; explicit newlines break (an empty line keeps its height)."""
        font, lines = self.font(points), []
        factor = 1. if 'round' in (self.rounded_path() or '').lower() else FALLBACK_WIDTH
        for paragraph in text.split('\n'):
            current = ''
            for word in paragraph.split(' '):
                trial = f'{current} {word}' if current else word
                if current and font.size(trial)[0] / (S * self.K) * factor > width:
                    lines.append(current)
                    current = word
                else:
                    current = trial
            lines.append(current)
        return lines

    def pitch(self, points):
        return self.font(points).get_linesize() / (S * self.K)

    @staticmethod
    def even(value):
        """Up to the next even number of points."""
        return math.ceil(value / 2) * 2

    def geometry(self, title, text):
        """(header, height, total, body top, bubble center y) in form points."""
        lines = len(self.wrap(text, self.BODY_POINTS, self.BODY[2]))
        body_height = self.even(int(lines * self.pitch(self.BODY_POINTS) + 1))
        height = max(self.MIN_HEIGHT, self.MIN_HEIGHT - self.BODY[3] + body_height)
        title_height = len(self.wrap(title, self.TITLE_POINTS, self.SHORT_TITLE[2])) * self.pitch(self.TITLE_POINTS)
        header = self.TALL_HEADER if title_height + 1 > self.SHORT_TITLE[3] else self.SHORT_HEADER
        total = self.even(height + header + self.FOOTER / 2)
        top = header + (self.SCREEN[1] - total) // 2
        center = top + height // 2 + (self.FOOTER - header) // 2
        return header, height, total, top, center

    def frame_point(self, x, y):
        """A form point's place on the layer's frame, in frame points."""
        return self.ORIGIN[0] + x * self.K, self.ORIGIN[1] + y * self.K

    @property
    def left(self):
        return (self.SCREEN[0] - self.WIDTH) / 2

    def image(self, slot, index, theme=1):
        pack = self.layouts.pack_for(slot, theme)
        return None if pack is None else self.layouts.frame(pack, index)

    def draw_bubble(self, layer, total, center):
        """`g_layerBubble`: the dialogue box (setBubbleSex(1)), inner WIDTH - 2 edges x (total - 2 edges), borders
        outside."""
        from .ui_assets import Rect
        inner_w, inner_h = self.WIDTH - 2 * self.BUBBLE_EDGE, total - 2 * self.BUBBLE_EDGE
        x, y = self.frame_point((self.SCREEN[0] - inner_w) / 2, center - inner_h / 2)
        # DialogueRenderer.box works in its own units (an HD half point, a CoD point: two frame points either way);
        # this layer has 2 * S px per unit.
        self.art.box(layer, Rect(x / 2, y / 2, inner_w * self.K / 2, inner_h * self.K / 2),
                     self.BUBBLE_THEME, alpha=self.art.box_alpha(), scale=2 * S)

    def draw_widget(self, layer, header, height, top):
        # The form's own layer only spans the body rows (and BODY_INSET in from each side), so the widget's
        # header and footer art is clipped away; the bubble underneath shows there.
        k = self.K * S
        x, y = self.frame_point(self.left + self.BODY_INSET, top)
        layer.set_clip(pygame.Rect(round(x * S), round(y * S), round((self.WIDTH - 2 * self.BODY_INSET) * k),
                                   round(height * k)))
        tall = header == self.TALL_HEADER
        hidden = (SHORT_HEADER_NODE,) if tall else (TALL_HEADER_NODE,)
        shown = (TALL_HEADER_NODE,) if tall else (SHORT_HEADER_NODE,)
        n = self.NODE_POINTS
        for _, node, visible, (nx, ny, w, h) in self.layouts.nodes(LAYOUT, size=(self.WIDTH / n, height / n),
                                                                   hidden=hidden, shown=shown):
            if not visible or node.kind != 1 or w <= 0 or h <= 0:
                continue
            image = self.image(*node.payload)
            if image is None:
                continue
            size = (max(1, round(w * n * k)), max(1, round(h * n * k)))
            px, py = self.frame_point(self.left + nx * n, top + ny * n)
            layer.blit(pygame.transform.smoothscale(image, size), (round(px * S), round(py * S)))
        layer.set_clip(None)

    def text_block(self, layer, lines, points, x, y, width, *, center=False, middle_height=None, alpha=1.):
        """Lines at form point (x, y), `width` form points wide."""
        font, pitch = self.font(points), self.pitch(points)
        if middle_height is not None:
            y += (middle_height - pitch * len(lines)) / 2
        for index, line in enumerate(lines):
            if not line:
                continue
            surface = font.render(line, True, self.INK)
            if alpha < 1:
                surface.set_alpha(round(255 * alpha))
            left = x + (width - surface.get_width() / (S * self.K)) / 2 if center else x
            fx, fy = self.frame_point(left, y + index * pitch)
            layer.blit(surface, (round(fx * S), round(fy * S)))

    def pill_image(self):
        """The continue pill at layer density: HD's pack 155 frame is one pixel per point."""
        native = self.art.frame_native(155, self.PILL_FRAME)
        return pygame.transform.smoothscale(native, (native.get_width() * S, native.get_height() * S))

    def draw_pill(self, layer, label, center, grow):
        image = self.pill_image()
        piece = pygame.Surface(image.get_size(), pygame.SRCALPHA).convert_alpha()
        piece.blit(image, (0, 0))
        # g_layerContinueLabel: TrebuchetMS-Bold, white, centered both ways (flags 10).
        font = self.font(self.LABEL_POINTS, 'trebuchet-bold')
        text = font.render(label, True, (255, 255, 255))
        # Vertically it centers the line box (ascent + descent), not the ink.
        piece.blit(text, ((piece.get_width() - text.get_width()) // 2, (piece.get_height() - text.get_height()) // 2))
        if grow < 1:
            piece = pygame.transform.smoothscale(piece, (piece.get_width(), max(1, round(piece.get_height() * grow))))
        fx, fy = self.frame_point(*center)
        layer.blit(piece, piece.get_rect(center=(round(fx * S), round(fy * S))))

    def background(self, session):
        return self.art.image(session.engine.panel.background_id)

    def draw(self, target, session):
        panel = session.engine.message_panel
        layer = self.canvas
        layer.fill((0, 0, 0, 0))
        self.pending_background = self.background(session)
        header, height, total, top, center = self.geometry(panel.title, panel.text)
        self.draw_bubble(layer, total, center)
        self.draw_widget(layer, header, height, top)
        tx, ty, tw, th = self.TALL_TITLE if header == self.TALL_HEADER else self.SHORT_TITLE
        title_alpha = default_ease(min(1., panel.elapsed_ms / 250)) if self.TITLE_FADE else 1.
        if title_alpha > 0:
            self.text_block(layer, self.wrap(panel.title, self.TITLE_POINTS, tw), self.TITLE_POINTS,
                            self.left + tx, top + ty + self.TITLE_DROP + self.TITLE_NUDGE, tw, center=True,
                            middle_height=th, alpha=title_alpha)
        self.text_block(layer, self.wrap(panel.text, self.BODY_POINTS, self.BODY[2]), self.BODY_POINTS,
                        self.left + self.BODY[0], top + self.BODY[1] + self.BODY_NUDGE, self.BODY[2])
        strings = self.strings()
        ready, wait, hint_ready, hint_wait = self.LABELS
        label = strings[ready] if panel.ready else f'{strings[wait]} ({panel.countdown})'
        inner_w, inner_h = self.WIDTH - 2 * self.BUBBLE_EDGE, total - 2 * self.BUBBLE_EDGE
        grow = min(1., panel.elapsed_ms / 250)
        if grow > 0:
            self.draw_pill(layer, label, (self.SCREEN[0] / 2 + inner_w / 2 - self.PILL_INSET,
                                          center + inner_h / 2 + self.PILL_DROP), grow)
        self.footer_text = strings[hint_ready if panel.ready else hint_wait]
        return [(pygame.Rect(-32, 422, 92, 58), ('menu',)), (pygame.Rect(0, 0, 320, 480), ('continue',))]


class CodMessageRenderer(HdMessageRenderer):
    """Cause of Death's message panel ("Thanks for playing!"): the same `SHSUIForm` on CoD's own layout bank
    (resource 14), whose layouts 24 / 25 / 27 / 3 are HD's at exactly half size, so every HD rule holds in CoD
    points (`expandContinue`'s offsets are halved too: 10 / -1.5 for HD's 20 / -3). Drawn on the HD frame at 2 points
    per CoD point from the CoD column's origin, like the chapter card (`desktop_title.CodTitleRenderer`).

    Checked against the owner's photo of the panel and zazatree's lighttouch recording of an episode's end:
    - Its art is CoD's: the gray dialogue box, pack 126's form rows and its gray pill (frame 5); title and text
      black. Labels are the game's strings 29 / 30, hints 36 / 39.
    - It stands on black: the recording shows the scene picture fading out as the panel opens (Desktop's
      `_location_change`), with the last dialogue fading out over it (`_panel_handover`).
    - The pill grows in over 0.25 s (the recording; `expandContinue` is HD's).
    - The title fades in over 0.25 s. The recording shows it gliding from the last speaker's name plate as it does
      (the dialogue's `g_layerTitle` moved and given new text with implicit actions on); the glide is not modelled.
    """
    K = 2
    ORIGIN = (64, 53)                           # the CoD column in the HD frame (desktop_title.CodTitleRenderer)
    SCREEN = (320, 480)
    WIDTH = 280
    BODY = (18, 15, 244, 98)
    MIN_HEIGHT = 128
    SHORT_HEADER, TALL_HEADER = 47, 78
    SHORT_TITLE, TALL_TITLE = (10, -36, 260, 25), (10, -66, 260, 54)
    FOOTER = 33
    BODY_INSET = 3
    BUBBLE_EDGE = 10
    PILL_INSET, PILL_DROP = 49.5, 8.5
    TITLE_DROP = 2
    TITLE_POINTS, BODY_POINTS, LABEL_POINTS = 20, 14, 14
    TITLE_NUDGE, BODY_NUDGE = 1, -2.5
    NODE_POINTS = 1                             # BankLayouts reports CoD points
    INK = (0, 0, 0)
    PILL_FRAME = 5                              # pack 126, layout 24 node 32
    LABELS = (29, 30, 36, 39)
    TITLE_FADE = True
    # CoD's box packs by theme (desktop_choice.hd_piece).
    BOX_PACKS = {1: 204, 2: 220, 3: 252}

    def form_layouts(self):
        return BankLayouts(self.resources.dialogue_layout().bank)

    def available(self):
        try:
            return (self.art.game_id() == 'cod' and self.rounded_path() is not None
                    and self.layouts.bank() is not None)
        except (AttributeError, ValueError, ContentError, UIAssetError):
            return False

    @lru_cache(maxsize=1)
    def strings(self):
        return MenuStrings.load(self.resources.library)

    def image(self, slot, index, theme=1):
        pack = 126 if slot == 0 else self.BOX_PACKS.get(theme, 236) if slot == 2 else None
        if pack is None:
            return None
        try:
            return self.art.frame_native(pack, index)
        except (IndexError, ValueError):
            return None

    def pill_image(self):
        return self.art.frame_scaled(126, self.PILL_FRAME, self.K * S)

    def background(self, session):
        return None
