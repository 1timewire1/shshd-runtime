"""Choice-panel geometry in the original 320 by 480 coordinate system.

The supplied iPhone screenshots define the visual target. Fonts, skins and
insets come from the APK; the 44-pixel rows also occur in FUN_000d9038.
See docs/UI_FIDELITY.md for differences from the Android Cocos drawing path.

This fork adds the vector-font (IPA / HD) measurements taken from the HD light-mode photos -- the line pitch, the
centred survey description, the portrait header block, the lighter option colour and the timed-box offsets -- and
lets an HD frontend drop the timer's lower panel (`timer_panel=False`). SHS HD's own choice panel is
`hd_choice.HdChoicePage`.
"""
from dataclasses import dataclass, replace
from functools import lru_cache
import math

from .fonts import FontError, load_font, TextLayout, TextStyle, layout_text
from .speaker_names import DEFAULT_FONT, NameFontState
from .ui_assets import LayoutBank, Rect, read_ui


BODY_FONT = 'ArialRoundedMTBold16'
FOOTER_FONT = 'ArialMT11'
TITLE_FONTS = {1: 'PajamaHip26', 2: 'PajamaHip266', 3: 'PajamaHipG26'}
PANEL_TOP = 32
PANEL_BOTTOM = 421
# HD draws option labels in a lighter shade of the theme color (see vector_text.HD_COLORS); the keys are
# the theme colors nudged by one level, which the bitmap fonts render as the ordinary color.
OPTION_COLORS = {(1, 76, 215): (2, 76, 215), (166, 45, 45): (167, 45, 45), (108, 108, 108): (109, 108, 108),
                 (223, 163, 52): (224, 163, 52)}


@dataclass(frozen=True)
class ChoiceRow:
    index: int
    rect: Rect
    text: TextLayout
    origin: tuple[float, float]
    enabled: bool


@dataclass(frozen=True)
class ChoicePage:
    box: Rect  # Outer border, unlike DialoguePage's center-fill rectangle.
    title_font: str
    title: TextLayout
    title_origin: tuple[float, float]
    description: TextLayout
    description_origin: tuple[float, float]
    portrait: Rect | None
    rows: tuple[ChoiceRow, ...]
    theme: int
    timer_panel: Rect | None = None
    text_scale: float = 1.0

    @property
    def max_scroll(self):
        # Retained for callers of the layout API. Choices never scroll.
        return 0


class ChoiceLayout:
    def __init__(self, resources):
        self.resources = resources
        self.bank = LayoutBank.parse(read_ui(resources, 14))

    @lru_cache(maxsize=8)
    def font(self, name):
        try:
            from .vector_text import load_font as vector_load_font  # needs pygame, the desktop extra
        except ImportError:
            return load_font(self.resources.library, name)
        return vector_load_font(self.resources.library, name)

    def display_title(self, text, theme):
        # 000d6afc repairs the bitmap title's spacing after solveMetrics has
        # measured the original string. This changes only the display label.
        if getattr(getattr(getattr(self, 'resources', None), 'library', None), 'kind', 'apk') == 'apk':
            if text == 'Fight!' and theme == 1:
                return 'Fi ght!'
            return {'Think fast!': 'Th ink fast', 'The answer is...?': 'Th e answer is...?'}.get(text, text)
        return text

    def prepare(self, details, names, history, *, theme=1, has_portrait=False):
        """Commit 000d9038's measurement and 000d6afc's label update order."""
        header = (7 if details.get('portrait_mode', 1) == 1 else 16) if has_portrait else 8
        state = names.fonts.setdefault(DEFAULT_FONT, NameFontState())
        measured = layout_text(self.font(DEFAULT_FONT), details['title'],
                               self.bank.rectangle(header, 18).width, state.style)
        state.lines = len(measured.lines)
        page = self.page(details, theme=theme, has_portrait=has_portrait)
        font = self.font(BODY_FONT)
        for row, text in zip(page.rows, details['options']):
            # Button construction assigns its text before setting dimensions,
            # then assigns it again after configuring the label (0006bd5c).
            history.update(f'choice_{row.index}', font, text,
                           layout_text(font, text, 2**31, TextStyle(12, 1)))
            history.update(f'choice_{row.index}', font, text, row.text)
        history.update('choice_body', font, details['text'], page.description)
        history.update('choice_title', self.font(page.title_font), self.display_title(details['title'], theme), page.title)

    def page(self, details, *, theme=1, has_portrait=False, text_history=None, timer_panel=True):
        """`timer_panel`: whether a timed choice gets Android's lower panel
        (layout 22). The HD build has none -- its wheel straddles the box's
        own bottom border -- so an HD-capable frontend passes False and the
        box keeps a 33-unit footer."""
        options = dict(theme=theme, has_portrait=has_portrait, text_history=text_history, timer_panel=timer_panel)
        page = self._page(details, **options)
        if page.box.height <= PANEL_BOTTOM - PANEL_TOP:
            return page
        # Preserve native-size labels whenever repositioning alone fits. For
        # unusually long authored options or substitute fonts, reflow smaller
        # text within the same skin width so every answer remains reachable.
        # This overflow fit is an adaptation, not a native animation/layout.
        low, high, fitted = 0., 1., None
        for _ in range(12):
            scale = (low + high) / 2
            candidate = self._page(details, scale=scale, **options)
            if candidate.box.height <= PANEL_BOTTOM - PANEL_TOP:
                low, fitted = scale, candidate
            else:
                high = scale
        if fitted is None:
            raise FontError('Choice text cannot fit in the available panel')
        return fitted

    def _page(self, details, *, theme, has_portrait, text_history, timer_panel=True, scale=1.):
        minigame = details.get('minigame', False)
        timed = not minigame and timer_panel and details.get('timeout_ms', 0) > 0
        # HD's timed choice (no lower panel; the wheel straddles the bottom
        # border) leaves ~33 units under the last row, against the ordinary 20.
        hd_timed = not minigame and not timer_panel and details.get('timeout_ms', 0) > 0
        width = self.bank.layouts[65].width
        left_portrait = details.get('portrait_mode', 1) == 1
        header = self.bank.rectangle((7 if left_portrait else 16) if has_portrait else 8, 9)
        title_font = TITLE_FONTS.get(theme, 'PajamaHipY26')
        title_indent = 20 if left_portrait else 5
        title_style = TextStyle(26, 8, indents=(0, title_indent / scale) if has_portrait else ())
        previous = text_history.initial if text_history is not None else lambda key: -1
        title = layout_text(self.font(title_font), self.display_title(details['title'], theme), header.width / scale,
                            title_style, previous_glyph=previous('choice_title'))
        if not has_portrait:
            # A character-free heading occupies the full top of the panel.
            glyphs = tuple(replace(g, x=g.x + (header.width / scale - line.width) / 2)
                           for line in title.lines for g in title.glyphs
                           if line.start <= g.index < line.end)
            title = replace(title, glyphs=glyphs)

        color = {1: (1, 76, 215), 2: (166, 45, 45), 3: (108, 108, 108)}.get(theme, (223, 163, 52))
        body_font = self.font(BODY_FONT)
        body_rect = self.bank.rectangle(65, 4)
        # FUN_000d9038 measures progressively around the portrait; the actual
        # text uses the smaller nominal height configured by FUN_000d6afc.
        indents = ()
        if has_portrait:
            # Native solveMetrics chooses the opposite header and signed
            # offsets for a right-side portrait. Android's third left offset
            # really is 103; iOS uses the smaller 95/85/65 table.
            ios = getattr(getattr(getattr(self, 'resources', None), 'library', None), 'kind', 'apk') == 'ipa'
            offsets = (95, 85, 65) if ios else (105, 95, 103 if left_portrait else 85)
            if not left_portrait:
                offsets = tuple(-value for value in offsets)
            for count in (1, 2, 3):
                indents = tuple(value / scale for value in offsets[:count])
                measured = layout_text(body_font, details['text'], body_rect.width / scale,
                                       TextStyle(16, 10, color, indents=indents))
                if len(measured.lines) <= count:
                    break
        vector = getattr(body_font, 'source', None) is not None
        # HD's real font advances come with its real line pitch: the description's lines are ~21.5 units apart
        # (Android 20) and, with a portrait, the block sits centered ~82 units below the box top in a header
        # that stays ~116 tall whether it has one line or two (light-mode photos, one and two lines).
        description = layout_text(body_font, details['text'], body_rect.width / scale,
                                  TextStyle(10, 11.5 if vector else 10, color, indents=indents),
                                  previous_glyph=previous('choice_body'))
        description_y = max(26, title.height + 2) * scale
        minimum_header = 112 if has_portrait else 38 * scale
        trailing = 6
        if vector and not has_portrait:
            # A heading with no character (the survey): the description is centered under the title and
            # sits 3.5 units lower than Android's (light-mode photo).
            description_y += 3.5 * scale
            width_used = (width - 14) / scale
            glyphs = tuple(replace(g, x=g.x + (width_used - line.width) / 2)
                           for line in description.lines for g in description.glyphs
                           if line.start <= g.index < line.end)
            description = replace(description, glyphs=glyphs)
        if vector and has_portrait:
            description_y = (82 - 10 * (len(description.lines) - 1)) * scale
            minimum_header, trailing = 116, 1
        header_height = math.ceil(max(minimum_header, description_y + description.height * scale + trailing))
        laid_out = []
        # HD's real font advances come with its real line pitch: two-line option
        # rows in the HD photo have their lines ~17.5 units apart (Android's
        # bitmap rows use 13) inside the same 44-unit row.
        for index, (label, enabled) in enumerate(zip(details['options'], details['enabled'])):
            label_color = OPTION_COLORS.get(color, color) if vector else color
            text = layout_text(body_font, label, ((width - 16) if vector else (width - 28)) / scale,
                               TextStyle(12, 5 if vector else 1, label_color if enabled else (150, 150, 150)),
                               previous_glyph=previous(f'choice_{index}'))
            _, top, _, bottom = text.ink_bounds
            laid_out.append((text, math.ceil(max(37 if minigame else 44, bottom - top + (12 if vector else 16)) * scale),
                             enabled))

        footer_height = self.bank.layouts[22].height if timed else 33 if hd_timed else (80 if minigame else 20)
        height = header_height + sum(h for _, h, _ in laid_out) + footer_height
        # Keep the whole panel above the footer, including the timer. A tall
        # quiz needs to move up before considering any smaller text.
        # Measured on the HD light-mode photos: an untimed choice sits 24 units below the centered position
        # and a timed one (whose wheel hangs off the bottom) 1 unit above it; Android's 11 stays for its own art.
        top_offset = 0 if minigame else (-1 if hd_timed else (24 if has_portrait else 12) if vector else 11)
        top = max(PANEL_TOP, min((480 - height) // 2 + top_offset, PANEL_BOTTOM - height))
        box = Rect((320 - width) // 2, top, width, height)
        rows, y = [], box.y + header_height
        for index, (text, height, enabled) in enumerate(laid_out):
            _, top, _, bottom = text.ink_bounds
            rect = Rect(box.x + 3, y, width - 6, height)
            origin = (box.x + 14, y + (height - (bottom - top) * scale) / 2 - top * scale + 2 * scale)
            rows.append(ChoiceRow(index, rect, text, origin, enabled))
            y += height
        portrait = Rect(box.x - 27, box.y - 24, 128, 128) if has_portrait else None
        if portrait is not None and not left_portrait:
            portrait = replace(portrait, x=320 - portrait.x - portrait.width)
        timer = None
        if timed:
            timer = Rect(box.x, y, width, footer_height)
        return ChoicePage(box, title_font, title, (box.x + header.x, box.y - 9),
                          description, (box.x + 7, box.y + description_y), portrait,
                          tuple(rows), theme, timer, scale)
