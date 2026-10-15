"""Services 17/40's APK layouts, bitmap labels, cursor and input alert.

Drawn at story density (`scale` canvas pixels per 320x480 logical unit) on a
transparent canvas; Desktop composites its background and this layer at
window resolution, like dialogue and choices.
"""
from dataclasses import replace
from functools import lru_cache

from . import graphics as pygame

from .content import ContentError
from .fonts import TextStyle, layout_label
from .hd_layout import FRAME_TO_COLUMN, HdLayouts
from .menu import MenuStrings
from .text_input import CURSOR_FONT, NAME_FONT
from .ui_assets import Rect, read_ui


BLUE = (41, 104, 221)
INPUT_RECT = (30, 177, 260, 40)
ALERT_RECT = (20, 160, 280, 160)

# HD's name entry (SHSUITextEntry, layout 46): the box is centered horizontally
# in the 384-unit frame and vertically by (0x13a - prompt text height) / 2, the
# height being the native 2x prompt's ink height (cap height 0.716 of 32 px).
HD_BOX_WIDTH = 280
HD_FRAME_WIDTH = 384
HD_CENTER_Y = 314
HD_CAP_HEIGHT = 0.716
HD_TITLE_FONT = 'ArialRoundedMTBold30'
HD_PROMPT_FONT = 'ArialRoundedMTBold16'
HD_NAME_FONT = 'PajamaHip24'
# Layout 46 nodes: title label 18, prompt label 23, typed-name label 44, and the
# field's box 34. Roots 1 (two-line title) and 10 (one-line) are toggled by the
# title's height; one line is shown here.
HD_HIDDEN_ROOTS = (1,)
# The name-entry photo (IMG_0091) shows the art shifted 96 units left of the
# other panels' placement, i.e. right-aligned in the frame.
HD_BACKGROUND_ORIGIN = (64, 180)
# Text anchors inside layout 46 (units from the label's top-left; baselines from
# its top), measured against IMG_0091 -- first estimates, refined below.
HD_TITLE_BASELINE = 23.5
HD_PROMPT_X = 0.6
HD_PROMPT_BASELINE = 12.3
HD_NAME_X = 0
HD_NAME_BASELINE = 25.6
# The cursor measures as a plain bar (IMG_0091: 8 x 82 px at 3.9 px/unit, its
# top 6.95 units below the label's top, its left 75.66 from the label's left
# with "John" in the field); it is placed by the text's end.
HD_CURSOR_SIZE = (2.05, 21.0)
HD_CURSOR_TOP = 6.7
HD_CURSOR_GAP = 3.85

# Cause of Death 1.4.7's SHSUITextEntry is SHS HD's at iPhone size (initTextEntry 0003f620: the same widget 0x2e,
# sub-elements 0x12/0x17/0x2c, m30/m20 for HD's m60/m40), laid out from CoD's own layout 46 in 320x480 points. Its
# fonts are engine +0x4a768 (Arial Rounded 30), +0x4bf88 (Arial Rounded 16) and +0x4d7a8 (the bundled name face
# 24), all 0xff000000 (initFonts). Placement and anchors measured on IMG_0457/0493/0502/0505/0507 (1x, 2 px/pt):
# the widget at x = (320 - 280) / 2, y = 151 - promptHeight (the base IPA's 000a0238 rule), promptHeight being the
# prompt's cap height; title, prompt and cursor within 0.5 pt.
COD_BOX_WIDTH = 280
COD_TOP = 151
COD_COLOR = (0, 0, 0)
COD_TITLE_BASELINE = 23.5      # the first line's, below node 18's top, for a one-line title
COD_PROMPT_X = 0.6
COD_PROMPT_BASELINE = 12.3
COD_NAME_BASELINE = 18.7
# The cursor is a solid bar in the name font's dark red (IMG_0493/0505: 6 x 48 px, (139, 0, 0)), its top 2.5 below
# the name label's top and 3.5 past the typed text's ink.
COD_CURSOR = (139, 0, 0)
COD_CURSOR_SIZE = (3, 24)
COD_CURSOR_TOP = 2.5
COD_CURSOR_GAP = 3.5


class InputRenderer:
    def __init__(self, resources, text_renderer, artwork, scale=1):
        self.resources, self.text, self.art = resources, text_renderer, artwork
        self.scale = scale
        self.canvas = pygame.Surface((320 * scale, 480 * scale), pygame.SRCALPHA).convert_alpha()
        self.pending_background = None
        self.pending_background_origin = (160, 180)
        self.edge_bar = None
        self.hd = HdLayouts(resources.library)

    def hd_available(self):
        return self.hd.bank() is not None and self.hd.frame(155, 4) is not None and self.hd.frame(247, 0) is not None

    @lru_cache(maxsize=1)
    def strings(self):
        return MenuStrings.load(self.resources.library)

    @lru_cache(maxsize=3)
    def layout_image(self, index, width, height):
        k = self.scale
        layer = pygame.Surface((width * k, height * k), pygame.SRCALPHA).convert_alpha()
        bank = self.resources.dialogue_layout().bank
        hidden_until = 0
        for number, (node, rect) in enumerate(bank.walk(index, Rect(0, 0, width, height)), 1):
            if number <= hidden_until:
                continue
            visible = node.flags & 16 and not (index == 46 and number in (1, 10))
            # Visibility belongs to reference roots as well as images. The
            # native layout-43 footer has a hidden button subtree, and
            # 000d4658 explicitly hides layout-46 roots 1 and 10.
            if node.kind == 7 and not visible:
                hidden_until = number + sum(1 for _ in bank.walk(node.payload[0]))
                continue
            if node.kind == 1 and visible and rect.width > 0 and rect.height > 0:
                slot, frame = node.payload
                image = self.art.frame_scaled({0: 126, 2: 204, 3: 16}[slot], frame, k)
                layer.blit(pygame.transform.scale(image, (round(rect.width * k), round(rect.height * k))),
                           (round(rect.x * k), round(rect.y * k)))
        return layer

    @lru_cache(maxsize=32)
    def title(self, text):
        name = 'ArialRoundedMTBold30'
        font = self.text.font(name)
        # 00165c14 rebuilds this label with BMFont's cumulative kerning when
        # 000d4658 changes its anchor to (1/2,1). Other labels use 0004dc20.
        layout = self.text.layout(name, text, 2**31, TextStyle(font.line_height, 0, BLUE))
        glyphs, widths = [], []
        placed = {g.index: g for g in layout.glyphs}
        for line in layout.lines:
            previous, width = -1, 0
            for i in range(line.start, line.end):
                code = ord(text[i])
                adjustment = font.kernings.get((previous & 0xffff, code), 0)
                if i in placed:
                    g = placed[i]
                    glyphs.append(replace(g, x=width + adjustment + g.glyph.xoffset))
                width += font.glyph(text[i]).advance + adjustment
                previous = code if code < 128 else code - 256
            widths.append(width)
        max_width = self.resources.dialogue_layout().bank.rectangle(46, 18).width
        scale = min(1., max_width / layout.width) if layout.width else 1.
        return replace(layout, glyphs=tuple(glyphs)), max(widths, default=0), scale

    def _image(self, asset):
        if getattr(self.resources.library, 'kind', 'apk') == 'ipa':
            # A base-game IPA's own name-entry roles (ios_assets.py), drawn at this canvas's density.
            image = self.art.ui_image(asset)
            if image is not None and self.scale != 1:
                image = pygame.transform.smoothscale(image, (round(image.get_width() * self.scale),
                                                             round(image.get_height() * self.scale)))
        else:
            # Android-only chrome, normalized to its logical size times density.
            image = self.art.chrome_image(asset, self.scale)
        if image is None:
            raise ContentError(f'Name-entry artwork {asset} is missing')
        return image

    def alert(self):
        k = self.scale
        # 707 is the alert's clickable panel, not the ordinary input screen.
        ios = getattr(self.resources.library, 'kind', 'apk') == 'ipa'
        if ios:
            # The IPA uses UIKit's UIAlertView, with no exported panel image.
            # Use the runtime's existing message skin for the desktop modal.
            self.art.box(self.canvas, Rect(30, 170, 260, 140), 1, scale=k)
        else:
            self.canvas.blit(self._image(707), (ALERT_RECT[0] * k, ALERT_RECT[1] * k))
        strings = self.strings()
        for caption, origin, color in ((strings[258], (130, 169), (255, 255, 255)),
                                        (strings[164], (140, 275), (0, 0, 0))):
            label = self.text.layout('ArialRoundedMTBold20', caption, 2**31, TextStyle(16, -16, BLUE if ios else color))
            self.text.draw_layout(self.canvas, 'ArialRoundedMTBold20', label, origin[0] * k, origin[1] * k, scale=k)
        label = layout_label(self.text.font('ArialRoundedMTBold16'), strings[260],
                             280, 160, TextStyle(16, 2, BLUE if ios else (255, 255, 255)), 0x16)
        # GL node (160,375), size (280,160), anchor (1/2,1/2).
        self.text.draw_layout(self.canvas, 'ArialRoundedMTBold16', label, 20 * k, 185 * k, scale=k)
        return [(pygame.Rect(ALERT_RECT), ('input_dismiss',))]

    def draw_ipa_entry(self, details, cursor_visible):
        """000a0238/000a0880: layout 46 supplies the entire entry panel."""
        bank = self.resources.dialogue_layout().bank
        prompt_rect = bank.rectangle(46, 23)
        prompt = self.text.layout('ArialRoundedMTBold16', details['prompt'], prompt_rect.width,
                                  TextStyle(16, 10, BLUE))
        height = max(1, round(prompt.height))
        bounds = Rect((320 - bank.layouts[46].width) // 2, 151 - height,
                      bank.layouts[46].width, bank.layouts[46].height + height - prompt_rect.height)
        title_rect = bank.rectangle(46, 18, bounds)
        title = self.text.layout('ArialRoundedMTBold30', details['title'], title_rect.width,
                                 TextStyle(30, 0, BLUE))
        active_header = 1 if title.height > title_rect.height else 10
        hidden_until = 0
        for number, (node, rect) in enumerate(bank.walk(46, bounds), 1):
            if number <= hidden_until:
                continue
            visible = node.flags & 16 and (number not in (1, 10) or number == active_header)
            if node.kind == 7 and not visible:
                hidden_until = number + sum(1 for _ in bank.walk(node.payload[0]))
                continue
            if node.kind == 1 and visible and rect.width > 0 and rect.height > 0:
                slot, frame = node.payload
                image = self.art.frame({0: 126, 2: 204, 3: 16}[slot], frame)
                self.canvas.blit(pygame.transform.scale(image, (rect.width, rect.height)), (rect.x, rect.y))
        title_y = bank.rectangle(46, 9 if active_header == 1 else 18, bounds).y
        self.text.draw_layout(self.canvas, 'ArialRoundedMTBold30', title,
                              title_rect.x + (title_rect.width - title.width) / 2, title_y)
        prompt_rect = bank.rectangle(46, 23, bounds)
        self.text.draw_layout(self.canvas, 'ArialRoundedMTBold16', prompt, prompt_rect.x, prompt_rect.y)
        entry = bank.rectangle(46, 44, bounds)
        draft = details.get('draft', details['default'])
        entered = self.text.layout('PajamaHip24', draft, 2**31, TextStyle(24))
        self.text.draw_layout(self.canvas, 'PajamaHip24', entered, entry.x, entry.y)
        if cursor_visible:
            cursor = self.text.layout('PajamaHip24', '|', 2**31, TextStyle(24))
            self.text.draw_layout(self.canvas, 'PajamaHip24', cursor, entry.x + entered.width, entry.y)
        return [(pygame.Rect(entry.x, entry.y, entry.width, entry.height), ('input_focus',))]

    def draw(self, target, session, *, error=None, cursor_visible=True):
        k = self.scale
        self.canvas.fill((0, 0, 0, 0))
        self.edge_bar = None
        self.pending_background = self.art.image(session.engine.panel.background_id)
        self.pending_background_origin = self.art.background_origin(self.pending_background, session.engine)
        if error:
            buttons = self.alert()
        elif self.cod_available():
            return self._draw_cod(target, session, cursor_visible)
        elif getattr(self.resources.library, 'kind', 'apk') == 'ipa':
            # draw_ipa_entry works in the 320x480 layout units of the original; this canvas is `k` times denser.
            flat, self.canvas = self.canvas, pygame.Surface((320, 480), pygame.SRCALPHA).convert_alpha()
            try:
                buttons = self.draw_ipa_entry(session.pending.details, cursor_visible)
            finally:
                flat, self.canvas = self.canvas, flat
            self.canvas.blit(pygame.transform.smoothscale(flat, self.canvas.get_size()), (0, 0))
        else:
            if self.hd_available():
                return self._draw_hd(target, session, cursor_visible)
            bank = self.resources.dialogue_layout().bank
            width = bank.layouts[46].width + 22
            footer = bank.layouts[43]
            # GL centers (160,415), (160,267), (160,340), in z order.
            self.canvas.blit(self.layout_image(15, width, 50), ((160 - width // 2) * k, 40 * k))
            self.canvas.blit(self.layout_image(43, footer.width, footer.height),
                             ((160 - footer.width // 2) * k, (213 - footer.height // 2) * k))
            self.canvas.blit(self.layout_image(46, width, 156), ((160 - width // 2) * k, 62 * k))
            details = session.pending.details
            title, title_width, scale = self.title(details['title'])
            self.text.draw_layout(self.canvas, 'ArialRoundedMTBold30', title,
                                  (160 - title_width * scale / 2) * k, 65 * k, scale=scale * k)
            prompt = self.text.layout('ArialRoundedMTBold16', details['prompt'], 2**31,
                                      TextStyle(16, -16, BLUE))
            self.text.draw_layout(self.canvas, 'ArialRoundedMTBold16', prompt, 30 * k, 120 * k, scale=k)
            shadow = self._image(706)
            self.canvas.blit(shadow, shadow.get_rect(center=(160 * k, 197 * k)))
            draft = details.get('draft', details['default'])
            entered = self.text.layout(NAME_FONT, draft, 2**31, TextStyle(26, -26, BLUE))
            self.text.draw_layout(self.canvas, NAME_FONT, entered, 35 * k, 190 * k, scale=k)
            if cursor_visible:
                cursor = self.text.layout(CURSOR_FONT, '|', 2**31, TextStyle(26, -26, BLUE))
                # 000858cc creates '|' before setting nominal height 26.
                # Unlike the name, the cursor is never assigned text again;
                # its glyph keeps the initial zero-height line origin.
                self.text.draw_layout(self.canvas, CURSOR_FONT, cursor, (entered.width + 33) * k, (214 - 26) * k,
                                      scale=k)
            # Native confirmation is keyboard Return. No portrait-picker
            # checkmark or common gear is attached by this panel's setup.
            buttons = [(pygame.Rect(INPUT_RECT), ('input_focus',))]
        if target is not None:
            target.blit(pygame.transform.smoothscale(self.canvas, target.get_size()), (0, 0))
        return buttons

    def cod_available(self):
        try:
            return self.art.game_id() == 'cod' and self.art.cod_hd_common() is not None
        except AttributeError:
            return False

    def _draw_cod(self, target, session, cursor_visible):
        """Cause of Death's panel (COD_* above): layout 46 from CoD's bank, its nodes tiled from the common pack 126
        (slot 0) and the theme-1 box pack (slot 2) as `CSLightWeightWidget::draw` does, the text in black."""
        from .hd_layout import BankLayouts
        k = self.scale
        details = session.pending.details
        bank = self.resources.dialogue_layout().bank
        layouts = BankLayouts(bank)
        style = lambda name, color=COD_COLOR: TextStyle(self.text.font(name).line_height, 0, color)
        prompt_rect = bank.rectangle(46, 23)
        prompt = self.text.layout(HD_PROMPT_FONT, details['prompt'], prompt_rect.width, style(HD_PROMPT_FONT))
        prompt_font = self.text.font(HD_PROMPT_FONT)
        height = HD_CAP_HEIGHT * 16 + (max(1, len(prompt.lines)) - 1) * prompt_font.line_height
        ox, oy = (320 - COD_BOX_WIDTH) / 2, COD_TOP - height
        title_rect = bank.rectangle(46, 18)
        title = self.text.layout(HD_TITLE_FONT, details['title'], title_rect.width, style(HD_TITLE_FONT))
        tall = len(title.lines) > 1
        for _, node, visible, (x, y, w, h) in layouts.nodes(46, (ox, oy), hidden=(10,) if tall else (1,),
                                                            shown=(1,) if tall else (10,)):
            if node.kind != 1 or not visible or w <= 0 or h <= 0:
                continue
            slot, frame = node.payload
            pack = {0: 126, 2: 204}.get(slot)
            try:
                image = None if pack is None else self.art.frame_scaled(pack, frame, k)
            except (ContentError, IndexError, ValueError):
                image = None
            if image is not None:
                self._tile(image, pygame.Rect(round(x * k), round(y * k), round(w * k), round(h * k)))
        # drawTextCentered on node 18's rectangle, read before the tall header is shown and never re-read: each line
        # centred across it, the block centred on it, so a second line runs down toward the prompt (IMG_0493).
        node = layouts.rectangle(46, 18, (ox, oy))
        title_font = self.text.font(HD_TITLE_FONT)
        baseline = COD_TITLE_BASELINE - (len(title.lines) - 1) * title_font.line_height / 2
        shifts = {}
        for line in title.lines:
            for i in range(line.start, line.end):
                shifts[i] = (node[2] - line.width) / 2
        title = replace(title, glyphs=tuple(replace(g, x=g.x + shifts.get(g.index, 0)) for g in title.glyphs))
        self.text.draw_layout(self.canvas, HD_TITLE_FONT, title, node[0] * k,
                              (node[1] + baseline - title_font.base) * k, scale=k)
        node = layouts.rectangle(46, 23, (ox, oy))
        self.text.draw_layout(self.canvas, HD_PROMPT_FONT, prompt, (node[0] + COD_PROMPT_X) * k,
                              (node[1] + COD_PROMPT_BASELINE - prompt_font.base) * k, scale=k)
        name_rect = layouts.rectangle(46, 44, (ox, oy))
        draft = details.get('draft', details['default'])
        entered = self.text.layout(HD_NAME_FONT, draft, 2**31, style(HD_NAME_FONT, (255, 255, 255)))
        name_font = self.text.font(HD_NAME_FONT)
        nx, ny = name_rect[0], name_rect[1] + COD_NAME_BASELINE - name_font.base
        self.text.draw_layout(self.canvas, HD_NAME_FONT, entered, nx * k, ny * k, scale=k)
        if cursor_visible:
            end = entered.ink_bounds[2] if entered.glyphs else 0
            bar = pygame.Rect(round((nx + end + COD_CURSOR_GAP) * k), round((name_rect[1] + COD_CURSOR_TOP) * k),
                              round(COD_CURSOR_SIZE[0] * k), round(COD_CURSOR_SIZE[1] * k))
            pygame.draw.rect(self.canvas, COD_CURSOR, bar)
        self.edge_bar = 'bar'
        field = layouts.rectangle(46, 34, (ox, oy))
        if target is not None:
            target.blit(pygame.transform.smoothscale(self.canvas, target.get_size()), (0, 0))
        return [(pygame.Rect(*(round(v) for v in field)), ('input_focus',))]

    def _tile(self, image, rect):
        """`CSMasterImage::drawTiledNoCP`: the image repeated from the rectangle's top-left, clipped to it."""
        clip = self.canvas.get_clip()
        self.canvas.set_clip(rect.clip(clip))
        w, h = image.get_size()
        for y in range(rect.y, rect.bottom, h):
            for x in range(rect.x, rect.right, w):
                self.canvas.blit(image, (x, y))
        self.canvas.set_clip(clip)

    def _hd_glyphs(self, font, text, width, color=BLUE):
        # Pajama Hip carries its own fill color (vector_text.PAJAMA_COLORS).
        color = (255, 255, 255) if font.startswith('PajamaHip') else color
        return self.text.layout(font, text, width, TextStyle(self.text.font(font).line_height, 0, color))

    def _draw_hd(self, target, session, cursor_visible):
        """The HD panel: layout 46 from the HD bank, drawn with HD's own frames
        (`legacy/findings.md`, "HD name entry")."""
        k = self.scale
        details = session.pending.details
        prompt = self._hd_glyphs(HD_PROMPT_FONT, details['prompt'], 246)
        prompt_font = self.text.font(HD_PROMPT_FONT)
        lines = max(1, len(prompt.lines))
        height = HD_CAP_HEIGHT * 32 + (lines - 1) * 2 * prompt_font.line_height
        frame_x, frame_y = (HD_FRAME_WIDTH - HD_BOX_WIDTH) / 2, (HD_CENTER_Y - height) / 2
        ox, oy = frame_x + FRAME_TO_COLUMN[0], frame_y + FRAME_TO_COLUMN[1]
        for _, node, visible, (x, y, w, h) in self.hd.nodes(46, (ox, oy), hidden=HD_HIDDEN_ROOTS, shown=(10,)):
            if node.kind != 1 or not visible or w <= 0 or h <= 0:
                continue
            slot, index = node.payload
            image = self.hd.frame(self.hd.pack_for(slot, 1), index)
            if image is not None:
                size = round(w * k), round(h * k)
                self.canvas.blit(pygame.transform.smoothscale(image, size), (round(x * k), round(y * k)))
        rect = self.hd.rectangle
        title, title_width, scale = self.title(details['title'])
        title_rect = rect(46, 18, (ox, oy))
        title_font = self.text.font(HD_TITLE_FONT)
        cx = title_rect[0] + title_rect[2] / 2 - title_width * scale / 2
        self.text.draw_layout(self.canvas, HD_TITLE_FONT, title, cx * k, (title_rect[1] + HD_TITLE_BASELINE - title_font.base * scale) * k,
                              scale=scale * k)
        prompt_rect = rect(46, 23, (ox, oy))
        self.text.draw_layout(self.canvas, HD_PROMPT_FONT, prompt, (prompt_rect[0] + HD_PROMPT_X) * k,
                              (prompt_rect[1] + HD_PROMPT_BASELINE - prompt_font.base) * k, scale=k)
        name_rect = rect(46, 44, (ox, oy))
        draft = details.get('draft', details['default'])
        entered = self._hd_glyphs(HD_NAME_FONT, draft, 2**31)
        name_font = self.text.font(HD_NAME_FONT)
        nx, ny = name_rect[0] + HD_NAME_X, name_rect[1] + HD_NAME_BASELINE - name_font.base
        self.text.draw_layout(self.canvas, HD_NAME_FONT, entered, nx * k, ny * k, scale=k)
        if cursor_visible:
            bar = pygame.Rect(round((nx + entered.width + HD_CURSOR_GAP) * k), round((name_rect[1] + HD_CURSOR_TOP) * k),
                              max(1, round(HD_CURSOR_SIZE[0] * k)), round(HD_CURSOR_SIZE[1] * k))
            pygame.draw.rect(self.canvas, BLUE, bar)
        self.pending_background_origin = HD_BACKGROUND_ORIGIN
        self.edge_bar = 'bar'
        field = rect(46, 34, (ox, oy))
        if target is not None:
            target.blit(pygame.transform.smoothscale(self.canvas, target.get_size()), (0, 0))
        return [(pygame.Rect(*(round(v) for v in field)), ('input_focus',))]
