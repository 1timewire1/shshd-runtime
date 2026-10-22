"""The iOS HD message panel (script service 33, "Instructions", "The End", ...).

Decompiled (`SHSUIForm::initForm`, `internalTransitionOn`, `tick`, `getTimerText`, `GameModel::expandContinue`) and
checked against the owner's photos (`dialouge/IMG_0240`-`0242`). Everything is in frame points (768 x 1024).

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
from functools import lru_cache

from . import graphics as pygame

from .hd_layout import HdLayouts, STRINGS_ID
from .menu import MenuStrings
from .vector_text import system_font_path

S = 2
FRAME = (768, 1024)
BLUE = (41, 104, 221)
WIDTH = 560
LEFT = (FRAME[0] - WIDTH) // 2
BODY = (36, 30, 488, 196)                   # node 0x18 in the widget
MIN_HEIGHT = 256
SHORT_HEADER, TALL_HEADER = 94, 156
SHORT_TITLE, TALL_TITLE = (20, -72, 520, 50), (20, -132, 520, 108)   # nodes 0x17 and 0xe
FOOTER_OVERHANG = 33
TITLE_POINTS, BODY_POINTS, LABEL_POINTS = 40, 28, 28
# Where HD's CSFont puts a line's top relative to pygame's, measured on the photos (points).
TITLE_NUDGE, BODY_NUDGE = 2, -5
# Arial Bold (the fallback when Arial Rounded MT Bold is not installed) sets the same text about 1% narrower
# than HD (480 vs 485 points for "Then tune-in each week! Go to 'Now"), enough to change line breaks.
FALLBACK_WIDTH = 1.0104
# 1-based walk numbers of the two header subtrees in layout 24 (short = node 0xf, tall = node 6).
TALL_HEADER_NODE, SHORT_HEADER_NODE = 6, 15
PILL_FRAME = 10                             # pack 155, the blue continue pill
LAYOUT = 24


class HdMessageRenderer:
    hd_layer = True
    edge_bar = 'bar'

    def __init__(self, resources, art):
        self.resources, self.art = resources, art
        self.layouts = HdLayouts(resources.library)
        self.canvas = pygame.Surface((FRAME[0] * S, FRAME[1] * S), pygame.SRCALPHA).convert_alpha()
        self.pending_background = None
        self.pending_background_origin = (160, 180)
        self.footer_text = ''

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
        return pygame.font.Font(system_font_path(role, self.resources.library), points * S)

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
                if current and font.size(trial)[0] / S * factor > width:
                    lines.append(current)
                    current = word
                else:
                    current = trial
            lines.append(current)
        return lines

    def pitch(self, points):
        return self.font(points).get_linesize() / S

    def geometry(self, title, text):
        """(header, height, total, body top, bubble center y) in points."""
        body_height = len(self.wrap(text, BODY_POINTS, BODY[2])) * self.pitch(BODY_POINTS) + 1
        body_height = int(body_height) + int(body_height) % 2
        height = max(MIN_HEIGHT, MIN_HEIGHT - BODY[3] + body_height)
        title_height = len(self.wrap(title, TITLE_POINTS, SHORT_TITLE[2])) * self.pitch(TITLE_POINTS)
        header = TALL_HEADER if title_height + 1 > SHORT_TITLE[3] else SHORT_HEADER
        total = height + header + FOOTER_OVERHANG
        total += total % 2
        top = header + (FRAME[1] - total) // 2
        center = top + height // 2 + (66 - header) // 2
        return header, height, total, top, center

    def image(self, slot, index, theme=1):
        pack = self.layouts.pack_for(slot, theme)
        return None if pack is None else self.layouts.frame(pack, index)

    def draw_bubble(self, layer, total, center):
        """`g_layerBubble`: the blue dialogue box (setBubbleSex(1)), inner 520 x (total - 40), borders outside."""
        from .ui_assets import Rect
        inner_w, inner_h = WIDTH - 40, total - 40
        # DialogueRenderer.box works in layout units (half points); this layer has 2 * S px per unit.
        self.art.box(layer, Rect((FRAME[0] - inner_w) / 4, (center - inner_h / 2) / 2, inner_w / 2, inner_h / 2),
                     1, alpha=self.art.box_alpha(), scale=2 * S)

    def draw_widget(self, layer, header, height, top):
        # The form's own layer only spans the body rows (and 6 points in from each side), so the widget's
        # header and footer art is clipped away; the bubble underneath shows there.
        layer.set_clip(pygame.Rect((LEFT + 6) * S, top * S, (WIDTH - 12) * S, height * S))
        tall = header == TALL_HEADER
        hidden = (SHORT_HEADER_NODE,) if tall else (TALL_HEADER_NODE,)
        shown = (TALL_HEADER_NODE,) if tall else (SHORT_HEADER_NODE,)
        for _, node, visible, (x, y, w, h) in self.layouts.nodes(LAYOUT, size=(WIDTH / 2, height / 2),
                                                                 hidden=hidden, shown=shown):
            if not visible or node.kind != 1 or w <= 0 or h <= 0:
                continue
            image = self.image(*node.payload)
            if image is None:
                continue
            # Units are half points: node rectangles come back in units, the layer is 2 px per point.
            size = (max(1, round(w * 2 * S)), max(1, round(h * 2 * S)))
            layer.blit(pygame.transform.smoothscale(image, size),
                       (round((LEFT + x * 2) * S), round((top + y * 2) * S)))
        layer.set_clip(None)

    def text_block(self, layer, lines, points, x, y, width, *, center=False, middle_height=None):
        font, pitch = self.font(points), self.pitch(points)
        if middle_height is not None:
            y += (middle_height - pitch * len(lines)) / 2
        for index, line in enumerate(lines):
            if not line:
                continue
            surface = font.render(line, True, BLUE)
            left = x + (width - surface.get_width() / S) / 2 if center else x
            layer.blit(surface, (round(left * S), round((y + index * pitch) * S)))

    def draw_pill(self, layer, label, center, grow):
        native = self.art.frame_native(155, PILL_FRAME)      # 198 x 34, one pixel per point
        size = native.get_width() * S, native.get_height() * S
        piece = pygame.Surface(size, pygame.SRCALPHA).convert_alpha()
        piece.blit(pygame.transform.smoothscale(native, size), (0, 0))
        # g_layerContinueLabel: TrebuchetMS-Bold 28 pt, white, centered both ways (flags 10).
        font = self.font(LABEL_POINTS, 'trebuchet-bold')
        text = font.render(label, True, (255, 255, 255))
        # Vertically it centers the line box (ascent + descent), not the ink.
        piece.blit(text, ((piece.get_width() - text.get_width()) // 2, (piece.get_height() - text.get_height()) // 2))
        if grow < 1:
            piece = pygame.transform.smoothscale(piece, (piece.get_width(), max(1, round(piece.get_height() * grow))))
        layer.blit(piece, piece.get_rect(center=(round(center[0] * S), round(center[1] * S))))

    def draw(self, target, session):
        panel = session.engine.message_panel
        layer = self.canvas
        layer.fill((0, 0, 0, 0))
        self.pending_background = self.art.image(session.engine.panel.background_id)
        header, height, total, top, center = self.geometry(panel.title, panel.text)
        self.draw_bubble(layer, total, center)
        self.draw_widget(layer, header, height, top)
        tx, ty, tw, th = TALL_TITLE if header == TALL_HEADER else SHORT_TITLE
        self.text_block(layer, self.wrap(panel.title, TITLE_POINTS, tw), TITLE_POINTS,
                        LEFT + tx, top + ty + 4 + TITLE_NUDGE, tw, center=True, middle_height=th)
        self.text_block(layer, self.wrap(panel.text, BODY_POINTS, BODY[2]), BODY_POINTS,
                        LEFT + BODY[0], top + BODY[1] + BODY_NUDGE, BODY[2])
        strings = self.strings()
        label = strings[26] if panel.ready else f'{strings[27]} ({panel.countdown})'
        inner = total - 40
        grow = min(1., panel.elapsed_ms / 250)
        if grow > 0:
            self.draw_pill(layer, label, (FRAME[0] / 2 - (WIDTH - 40) / 2 + (WIDTH - 40) - 99,
                                          center + inner / 2 + 17), grow)
        self.footer_text = strings[33 if panel.ready else 36]
        return [(pygame.Rect(-32, 422, 92, 58), ('menu',)), (pygame.Rect(0, 0, 320, 480), ('continue',))]
