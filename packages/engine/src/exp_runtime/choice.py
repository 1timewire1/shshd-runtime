"""Choice-panel geometry in the original 320 by 480 coordinate system.

The supplied iPhone screenshots define the visual target. Fonts, skins and
insets come from the APK; the 44-pixel rows also occur in FUN_000d9038.
See docs/UI_FIDELITY.md for differences from the Android Cocos drawing path.
"""
from dataclasses import dataclass, replace
from functools import lru_cache
import math

from .fonts import load_font, TextLayout, TextStyle, layout_text
from .ui_assets import LayoutBank, Rect, read_ui


BODY_FONT = 'ArialRoundedMTBold16'
FOOTER_FONT = 'ArialMT11'
TITLE_FONTS = {1: 'PajamaHip26', 2: 'PajamaHip266', 3: 'PajamaHipG26'}
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
    max_scroll: int
    timer_panel: Rect | None = None


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

    def page(self, details, *, theme=1, has_portrait=False, timer_panel=True):
        """`timer_panel`: whether a timed choice gets Android's lower panel
        (layout 22). The HD build has none -- its wheel straddles the box's
        own bottom border -- so an HD-capable frontend passes False and the
        box keeps the ordinary 20px footer."""
        minigame = details.get('minigame', False)
        timed = not minigame and timer_panel and details.get('timeout_ms', 0) > 0
        # HD's timed choice (no lower panel; the wheel straddles the bottom
        # border) leaves ~33 units under the last row, against the ordinary 20.
        hd_timed = not minigame and not timer_panel and details.get('timeout_ms', 0) > 0
        width = self.bank.layouts[65].width
        header = self.bank.rectangle(7 if has_portrait else 8, 9)
        title_font = TITLE_FONTS.get(theme, 'PajamaHipY26')
        title_indent = 20 if details.get('portrait_mode', 1) == 1 else 5
        title_style = TextStyle(26, 8, indents=(0, title_indent) if has_portrait else ())
        title = layout_text(self.font(title_font), details['title'], header.width, title_style)
        if not has_portrait:
            # A character-free heading occupies the full top of the panel.
            glyphs = tuple(replace(g, x=g.x + (header.width - line.width) / 2)
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
            for count in (1, 2, 3):
                indents = (105, 95, 85)[:count]
                measured = layout_text(body_font, details['text'], body_rect.width,
                                       TextStyle(16, 10, color, indents=indents))
                if len(measured.lines) <= count:
                    break
        vector = getattr(body_font, 'source', None) is not None
        # HD's real font advances come with its real line pitch: the description's lines are ~21.5 units apart
        # (Android 20) and, with a portrait, the block sits centered ~82 units below the box top in a header
        # that stays ~116 tall whether it has one line or two (light-mode photos, one and two lines).
        description = layout_text(body_font, details['text'], body_rect.width,
                                  TextStyle(10, 11.5 if vector else 10, color, indents=indents))
        description_y = max(26, title.height + 2)
        minimum_header = 112 if has_portrait else 38
        trailing = 6
        if vector and not has_portrait:
            # A heading with no character (the survey): the description is centered under the title and
            # sits 3.5 units lower than Android's (light-mode photo).
            description_y += 3.5
            width_used = width - 14
            glyphs = tuple(replace(g, x=g.x + (width_used - line.width) / 2)
                           for line in description.lines for g in description.glyphs
                           if line.start <= g.index < line.end)
            description = replace(description, glyphs=glyphs)
        if vector and has_portrait:
            description_y = 82 - 10 * (len(description.lines) - 1)
            minimum_header, trailing = 116, 1
        header_height = math.ceil(max(minimum_header, description_y + description.height + trailing))
        laid_out = []
        # HD's real font advances come with its real line pitch: two-line option
        # rows in the HD photo have their lines ~17.5 units apart (Android's
        # bitmap rows use 13) inside the same 44-unit row.
        for label, enabled in zip(details['options'], details['enabled']):
            label_color = OPTION_COLORS.get(color, color) if vector else color
            text = layout_text(body_font, label, width - 16,
                               TextStyle(12, 5 if vector else 1, label_color if enabled else (150, 150, 150)))
            _, top, _, bottom = text.ink_bounds
            laid_out.append((text, max(37 if minigame else 44, math.ceil(bottom - top + (12 if vector else 16))),
                             enabled))

        footer_height = (self.bank.layouts[22].height if timed else 33 if hd_timed else (80 if minigame else 20))
        height = header_height + sum(h for _, h, _ in laid_out) + footer_height
        # The reference's panel is centered below its overlapping heading.
        # Taller lists can scroll without changing the script's option order.
        # The HD timed box keeps its bottom edge where the ordinary one has it
        # (measured, `IMG_0085`), so its extra footer height grows it upward.
        # Measured on the HD light-mode photos: an untimed choice sits 24 units below the centered position
        # and a timed one (whose wheel hangs off the bottom) 1 unit above it; Android's 11 stays for its own art.
        top_offset = 0 if minigame else (-1 if hd_timed else (24 if has_portrait else 12) if vector else 11)
        top = max(32, (480 - height) // 2 + top_offset)
        if vector and not minigame and top + height > 421:
            # HD keeps a tall panel whole above the bottom bar: it moves up rather than becoming a scrolling list
            # (owner-observed on the HD app; As Time Goes By's four-line "What quality is most important..." with
            # four options sat 5 units too low after the portrait offset). Only a panel taller than the space
            # between the top margin and the bar still scrolls.
            top = max(32, 421 - height)
        box = Rect((320 - width) // 2, top, width, height)
        rows, y = [], box.y + header_height
        for index, (text, height, enabled) in enumerate(laid_out):
            _, top, _, bottom = text.ink_bounds
            rect = Rect(box.x + 3, y, width - 6, height)
            origin = (box.x + 14, y + (height - (bottom - top)) / 2 - top + 2)
            rows.append(ChoiceRow(index, rect, text, origin, enabled))
            y += height
        portrait = Rect(box.x - 27, box.y - 24, 128, 128) if has_portrait else None
        timer_rect = None
        max_scroll = max(0, box.y + box.height - 421)
        if timed:
            # Layout 22 supplies the timer's lower panel. Keep it visible when
            # the desktop's expanded rows need scrolling above the footer.
            timer_rect = Rect(box.x, min(y, 421 - footer_height), width, footer_height)
            max_scroll = max(0, y - timer_rect.y)
        return ChoicePage(box, title_font, title, (box.x + header.x, box.y - 9),
                          description, (box.x + 7, box.y + description_y), portrait,
                          tuple(rows), theme, max_scroll, timer_rect)
