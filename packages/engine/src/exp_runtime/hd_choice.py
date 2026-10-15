"""The HD build's own choice panel (iPad 1.4.38), ported from `SHSWidgetMenu` and `SHSMenu`.

All native geometry is in iPad points in the 768x1024 frame; pages report layout units in the 320-unit column
like every other renderer (units = points / 2, less hd_layout.FRAME_TO_COLUMN). See legacy/findings.md, "HD choice
panel, decompiled".

`SHSUIMenu::initMenu` builds an in-game choice with `generateNewMenu(-1, 1, 4, 1)` and
`setPortrait(character, portrait_mode == 1)`; `setTimed(timeout > 0)`. Then:

- `CSWidgetMenu::setMetrics(0x68, 0, 0x230, 200)`: the panel is 560 points wide at x 104.
- `solveMetrics` (0004fbac): the header widget is 8 (no character), 7 (portrait on the left) or 16 (right). Its
  normal title region is node 18; a title taller than that region uses the tall node 9 instead, and the header
  then shows node 1 rather than node 10. Header height = max(region's delta height + title height, the widget's
  own). The description widget is 65 (node 4): text height + its 20-point delta, plus 20 points when there is no
  character; with a portrait the text is measured with 1, 2 then 3 of ARR_LINE_OFFSETS_MENU_LEFT/RIGHT until it
  fits that many lines. Rows are 88 points each, dropped from the computation while the panel exceeds 964 points.
  The footer is widget 3, or 22 when timed (its score capsule, node 13, hidden). The panel is centred,
  top = (1024 - total) / 2, and only then is a portrait's description raised to 136 points.
- `drawSelf` (000504e4): header, description widget, a separator at the description's bottom ((179,179,179), 6
  points in), title in its region raised by the title font's descent (flags 0x1a centred, 0x19 with a portrait and
  ARR_TITLE_LINE_OFFSETS), description in node 4 (0x1a / 0x19 with the chosen line offsets), the footer, and 6-point
  side strips (box pack frame 3) beside the description and rows.
- `SHSMenu`: a UITableView at (x + 6, rows top, width - 12, rows height), 88-point rows of enabled options only, each
  an SHSLabel inset 24 x 12 points (flags 0x19), separators (166,166,166), even/odd/pressed colors from setPortrait.
- `SHSUIMenu::addPortraitToMenu`: the portrait housing's top is the panel's top, its centre x 104 + 74 (mode 1) or
  694 - 104 (mode 2); `clipPortraitHousing` keeps the ring out of (x + 6, box line + 6, width - 12, 244).
- `SHSUIMenu::updateTimerLayers`: the circle timer (100 points square) is centred at (385, footer top + 61).
"""
from dataclasses import dataclass, replace

from .fonts import TextLayout, TextStyle, layout_text
from .ui_assets import Rect

PANEL_X, PANEL_WIDTH = 104, 560
ROW_HEIGHT = 88
PANEL_LIMIT = 964
TABLE_INSET = 6
LABEL_PADDING = (24, 12)
HEADER_NO_PORTRAIT, HEADER_LEFT, HEADER_RIGHT = 8, 7, 16
TITLE_NORMAL_NODE, TITLE_TALL_NODE = 18, 9
HEADER_TALL_ROOT, HEADER_NORMAL_ROOT = 1, 10
DESCRIPTION_WIDGET, DESCRIPTION_NODE = 65, 4
FOOTER, TIMED_FOOTER, SCORE_CAPSULE = 3, 22, 13
PORTRAIT_DESCRIPTION_MINIMUM = 136
NO_PORTRAIT_EXTRA = 20
MENU_LINE_OFFSETS = ((190,), (190, 170), (190, 170, 130))     # ARR_LINE_OFFSETS_MENU_LEFT, points
TITLE_LINE_OFFSETS = {True: (0, 40), False: (0, 10)}           # SHSUIDialog::ARR_TITLE_LINE_OFFSETS_LEFT / _RIGHT
SEPARATOR, ROW_SEPARATOR = (179, 179, 179), (166, 166, 166)
TIMER_CENTER = (385, 61)                                         # x, and y below the footer's top
TIMER_SIZE = 100
# setPortrait's (even row, odd row, pressed row) ARGB per theme; the binary's gray triple is opaque placeholder
# green / red / blue.
ROW_COLORS = {1: (0xf3ffffff, 0xf3eff9fa, 0xf3aae1f9), 2: (0xf3ffffff, 0xf3faefee, 0xf3fad6d3),
              3: (0xff00ff00, 0xffff0000, 0xff0000ff), 0: (0xf3ffffff, 0xf3eddac5, 0xf3eebc82)}
# CSFont sizes and gaps from SHSEngine::initFonts, in points: title Pajama Hip 52 / 16, description Arial Rounded
# 32 / 20, options Arial Rounded 30 / 12.
TITLE_GAP, DESCRIPTION_GAP, OPTION_GAP = 16, 20, 12

COLUMN = (64, 53)          # the 320x480 column's origin in frame points (-2 * hd_layout.FRAME_TO_COLUMN)


def argb(value):
    return (value >> 16) & 255, (value >> 8) & 255, value & 255, value >> 24


@dataclass(frozen=True)
class PanelGeometry:
    """One build's SHSWidgetMenu constants, in its own points. `density` is points per layout unit (the iPad's 2, an
    iPhone's 1) and `column` the 320x480 column's origin in those points. Cause of Death 1.4.7's iPhone menu
    (solveMetrics 0004422c, drawSelf 00044b60, generateNewMenu 000453d8, SHSMenu 000337b0.., addPortraitToMenu
    0003d3f0, updateTimerLayers 0003c878) is SHS HD's code with every constant halved, in a 480-point screen."""
    density: int
    column: tuple
    screen_height: int
    panel_x: int
    panel_width: int
    row_height: int
    panel_limit: int
    table_inset: int
    label_padding: tuple
    description_minimum: int
    no_portrait_extra: int
    menu_line_offsets: tuple
    title_line_offsets: dict
    box_line: tuple             # the clip's line above the header's bottom: (normal, tall)
    portrait_left: int          # housing centre x: panel x + this (portrait on the left) ...
    portrait_right: int         # ... or this - panel x
    housing: int                # the portrait layer's square, points
    corner: int                 # clipPortraitHousing's corner cut, points
    timer_center: tuple         # x, and y below the footer's top
    timer_size: int
    label_fly: int              # SHSMenu's first label flies in from this x offset (the second from the table's width)
    # The rapid-fire quiz (setScored, drawScore, drawScoreEffect, updateTimerLayers), in points: the score and score
    # effect layers relative to the footer (widget 22 nodes 17 / 18), the effect's rise, the running man's frames in
    # the build's common pack (first, count, seconds each) and its centre's drop below the circle timer's. The defaults
    # are SHS HD's: resource 155 frames 28-32 at 0.07 s each (GameModel::initAnimations), centred at (385, footer top +
    # 62).
    score_box: tuple = (373, 42, 82, 38)
    effect_box: tuple = (493, 24, 36, 30)
    effect_rise: int = 30
    running_man: tuple = (28, 5, .07)
    running_drop: int = 1

    def units(self, x, y):
        """Points to column units."""
        return (x - self.column[0]) / self.density, (y - self.column[1]) / self.density


HD_GEOMETRY = PanelGeometry(2, COLUMN, 1024, PANEL_X, PANEL_WIDTH, ROW_HEIGHT, PANEL_LIMIT, TABLE_INSET, LABEL_PADDING,
                            PORTRAIT_DESCRIPTION_MINIMUM, NO_PORTRAIT_EXTRA, MENU_LINE_OFFSETS, TITLE_LINE_OFFSETS,
                            (36, 100), 74, 694, 256, 10, TIMER_CENTER, TIMER_SIZE, -600)
# Cause of Death: setMetrics(20, 0, 280, ..); 44-point rows; the panel kept within 450 points and centred in 480; a
# portrait's description raised to 68; 10 more without a character; ARR_LINE_OFFSETS_MENU_LEFT {95; 95,85; 95,85,65}
# and ARR_TITLE_LINE_OFFSETS_LEFT/RIGHT {0,20} / {0,5} (read from the binary); labels inset 12 x 6; the box line 18 or
# 50 above the header's bottom; the housing (a 128-point layer, centre x panel x + 37 or 283 - panel x, y top + 64)
# clipped with 10-point corners; the circle timer at (161, footer top + 30). Not halved: the labels fly in from
# -200 (`tableView:cellForRowAtIndexPath:` 00034c38, HD -600). The quiz: setScored's 41x19 / 18x15 layers at widget 22
# nodes 17 (187, 21) and 18 (247, 12); the running man (common pack 126 frames 23-27) at (161, footer top + 1 + 6 +
# 24), one below the circle timer (updateTimerLayers 0003c878). Not halved: doScoreEffectAnimation is byte-identical,
# so the effect rises 30 points.
COD_GEOMETRY = PanelGeometry(1, (0, 0), 480, 20, 280, 44, 450, 3, (12, 6), 68, 10, ((95,), (95, 85), (95, 85, 65)),
                             {True: (0, 20), False: (0, 5)}, (18, 50), 37, 283, 128, 10, (161, 30), 50, -200,
                             score_box=(187, 21, 41, 19), effect_box=(247, 12, 18, 15), effect_rise=30,
                             running_man=(23, 5, .07), running_drop=1)


def units(x, y):
    """HD frame points to column units."""
    return HD_GEOMETRY.units(x, y)


@dataclass(frozen=True)
class FontMetrics:
    font: object
    cap: float          # units (CSFont +0x24 / +0x1814)
    gap: float          # units (CSFont +0x20, as initFonts sets it)
    descent: float = 0  # units (CSFont +0x14)


def text_height(metrics, text, width, indents=(), density=2):
    """`CSFont::getTextHeight` in points, truncated as FPToFixed does by its callers. `width` in points."""
    layout = layout_text(metrics.font, text, width / density,
                         TextStyle(metrics.cap, metrics.gap, indents=tuple(i / density for i in indents)))
    return int(layout.height * density)


def text_in_region(metrics, text, rect, flags, color, indents=(), density=2):
    """`CSFont::drawTextInRegion` (00005778) in a region given in column units: wraps at its width (0x10), aligns
    each line by flags & 3 (2 centre, 3 right) within the width its offset leaves, and places the block by flags &
    0xc (8 centre, 0xc bottom less 4). `indents` are in points. Returns (layout, origin) for
    TextRenderer.draw_layout."""
    style = TextStyle(metrics.cap, metrics.gap, indents=tuple(i / density for i in indents))
    if color is not None:
        style = replace(style, color=color)
    font = metrics.font
    layout = layout_text(font, text, rect.width if flags & 0x10 else 2 ** 31, style)
    alignment = {2: .5, 3: 1}.get(flags & 3, 0)
    lines, glyphs = [], []
    for index, line in enumerate(layout.lines):
        indent = int(style.indents[index]) if index < len(style.indents) else 0
        offset = (rect.width - abs(indent) - line.width) * alignment
        lines.append(replace(line, x=line.x + offset))
        glyphs.extend(replace(g, x=g.x + offset) for g in layout.glyphs if line.start <= g.index < line.end)
    layout = replace(layout, lines=tuple(lines), glyphs=tuple(glyphs))
    vertical = flags & 0xc
    top = rect.y + ((rect.height - layout.height) / 2 if vertical == 8 else
                    rect.height - layout.height - 4 if vertical == 0xc else 0)
    # layout_text's baseline is line.y + height - line_height + base; CSFont's is line.y + cap.
    return layout, (rect.x, top + font.line_height - font.base)


@dataclass(frozen=True)
class HdRow:
    index: int                 # the script's option index
    position: int              # the enabled row's position (even/odd colors)
    rect: Rect                 # the cell, column units, unscrolled
    text: TextLayout
    origin: tuple[float, float]
    enabled: bool = True


@dataclass(frozen=True)
class HdChoicePage:
    theme: int
    top: int                   # all of these in frame points
    header_widget: int
    header_height: int
    tall_title: bool
    description_height: int
    rows_top: int
    rows_height: int
    footer_widget: int
    footer_top: int
    footer_height: int
    title_font: str
    title: TextLayout
    title_origin: tuple[float, float]
    description: TextLayout
    description_origin: tuple[float, float]
    description_font: str
    rows: tuple[HdRow, ...]
    portrait: Rect | None      # the housing, column units
    portrait_clip: tuple | None  # polygon the ring is not drawn in, column units
    max_scroll: float          # units the rows can scroll
    table: Rect                # the table view, column units
    timer_center: tuple[float, float] | None
    row_colors: tuple
    scored: bool = False        # setScored: the timed footer's score capsule (the rapid-fire quiz)
    timer_panel: None = None
    geometry: PanelGeometry = HD_GEOMETRY

    @property
    def box(self):
        """The panel's outer rectangle in column units (for code shared with the Android page)."""
        g = self.geometry
        x, y = g.units(g.panel_x, self.top)
        return Rect(x, y, g.panel_width / g.density,
                    (self.header_height + self.description_height + self.rows_height + self.footer_height) / g.density)


def hd_choice_page(layouts, details, *, theme, has_portrait, title: FontMetrics, title_font,
                   description: FontMetrics, description_font, option: FontMetrics, color, option_color,
                   scored=False, geometry=HD_GEOMETRY):
    """`layouts` holds the build's layout bank (hd_layout.HdLayouts for HD's, hd_layout.BankLayouts for an iPhone
    build's own); `details` the pending choice's; `geometry` the build's constants (HD_GEOMETRY, COD_GEOMETRY)."""
    g, d = geometry, geometry.density
    mode = details.get('portrait_mode', 1)
    left = mode == 1                      # setPortrait's flag: portrait_mode == 1
    header = HEADER_NO_PORTRAIT if not has_portrait else HEADER_LEFT if left else HEADER_RIGHT
    bank = layouts.bank()
    base_height = bank.layouts[header].height

    def region(layout_id, node, x, y, width, height):
        rx, ry, rw, rh = layouts.rectangle(layout_id, node, size=(width / d, height / d))
        return round(x + rx * d), round(y + ry * d), round(rw * d), round(rh * d)

    title_indents = g.title_line_offsets[left] if has_portrait else ()
    _, _, width, height = region(header, TITLE_NORMAL_NODE, 0, 0, g.panel_width, base_height)
    title_height = text_height(title, details['title'], width, title_indents, d)
    tall = base_height - height + title_height > base_height
    node = TITLE_TALL_NODE if tall else TITLE_NORMAL_NODE
    if tall:
        _, _, width, height = region(header, node, 0, 0, g.panel_width, base_height)
        title_height = text_height(title, details['title'], width, title_indents, d)
    header_height = max(base_height - height + title_height, base_height)

    text = details['text']
    description_base = bank.layouts[DESCRIPTION_WIDGET].height
    _, _, width, height = region(DESCRIPTION_WIDGET, DESCRIPTION_NODE, 0, 0, g.panel_width, description_base)
    delta = description_base - height
    offsets = ()
    if text:
        if has_portrait:
            for count in (1, 2, 3):
                offsets = tuple(o if left else -o for o in g.menu_line_offsets[count - 1])
                measured = text_height(description, text, width, offsets, d)
                if count * (description.cap + description.gap) * d >= measured:
                    break
            description_height = int(measured + delta)
        else:
            description_height = int(text_height(description, text, width, (), d) + delta + g.no_portrait_extra)
    else:
        description_height = 0

    timed = details.get('timeout_ms', 0) > 0
    footer = TIMED_FOOTER if timed else FOOTER
    footer_height = bank.layouts[footer].height
    options = [(index, label) for index, (label, enabled) in enumerate(zip(details['options'], details['enabled']))
               if enabled]
    rows_height = len(options) * g.row_height
    while rows_height and header_height + rows_height + footer_height + description_height > g.panel_limit:
        rows_height -= g.row_height
    total = header_height + rows_height + footer_height + description_height
    top = int((g.screen_height - total) / 2)
    if has_portrait and description_height < g.description_minimum:
        description_height = g.description_minimum
    body_top = top + header_height
    rows_top = body_top + description_height
    footer_top = rows_top + rows_height

    # Title, raised by the font's descent (drawSelf: -(int)titleFont.+0x14; CoD's CSFont has it at +0x18).
    rx, ry, rw, rh = region(header, node, g.panel_x, top, g.panel_width, header_height)
    ry -= int(title.descent * d)
    x, y = g.units(rx, ry)
    title_layout, title_origin = text_in_region(title, details['title'], Rect(x, y, rw / d, rh / d),
                                                0x19 if has_portrait else 0x1a, None, title_indents, d)
    rx, ry, rw, rh = region(DESCRIPTION_WIDGET, DESCRIPTION_NODE, g.panel_x, body_top, g.panel_width,
                            description_height)
    x, y = g.units(rx, ry)
    description_layout, description_origin = text_in_region(
        description, text, Rect(x, y, rw / d, rh / d), 0x19 if has_portrait else 0x1a, color, offsets, d)

    rows = []
    table_x, _ = g.units(g.panel_x + g.table_inset, 0)
    table_width = (g.panel_width - 2 * g.table_inset) / d
    for position, (index, label) in enumerate(options):
        cell_top = rows_top + position * g.row_height
        _, cell_y = g.units(0, cell_top)
        hx, vy = g.label_padding
        region_rect = Rect(table_x + hx / d, cell_y + vy / d, table_width - 2 * hx / d, (g.row_height - 2 * vy) / d)
        layout, origin = text_in_region(option, label, region_rect, 0x19, option_color, (), d)
        rows.append(HdRow(index, position, Rect(table_x, cell_y, table_width, g.row_height / d), layout, origin))
    _, table_y = g.units(0, rows_top)
    table = Rect(table_x, table_y, table_width, rows_height / d)

    portrait = clip = None
    if has_portrait:
        half = g.housing / 2
        cx = g.panel_x + g.portrait_left if left else g.portrait_right - g.panel_x
        hx, hy = g.units(cx - half, top)
        portrait = Rect(hx, hy, g.housing / d, g.housing / d)
        # addPortraitToMenu: clipPortraitHousing(layer, (x, +0x145c, width, housing)); +0x145c is the box line, and
        # the clip keeps the table's inset all round.
        line = top + header_height - (g.box_line[1] if tall else g.box_line[0])
        inset, corner = g.table_inset, g.corner / d
        x0, y0 = g.units(g.panel_x + inset, line + inset)
        x1, y1 = g.units(g.panel_x + g.panel_width - inset, line + g.housing - inset)
        clip = ((x0, y1), (x0, y0 + corner), (x0 + corner, y0), (x1 - corner, y0), (x1, y0 + corner), (x1, y1))
    timer = g.units(g.timer_center[0], footer_top + g.timer_center[1]) if timed else None
    return HdChoicePage(theme, top, header, header_height, tall, description_height, rows_top, rows_height,
                        footer, footer_top, footer_height, title_font, title_layout, title_origin,
                        description_layout, description_origin, description_font, tuple(rows), portrait, clip,
                        max(0, (len(options) * g.row_height - rows_height) / d), table, timer,
                        tuple(argb(c) for c in ROW_COLORS.get(theme, ROW_COLORS[0])), scored, geometry=g)


# SHSMenu's label flights. Each cell holds two SHSLabels of the same text at alpha 0.5 (`getCellContentView`), which
# land on top of each other (the photos' option text is the theme color at 75%: IMG_0226 (92,140,227) over
# (248,248,247)). `flySubLabel` eases (UIViewAnimationCurveEaseInOut) a label's frame x between 0 and an offset:
# the first label -600 points, the second its own width (the table's, 548).
LABEL_FLY_OFFSET = -600
FLY_ON_SECONDS = .7             # SHSMenu init; the quiz sets 0.3 / 0.5 (`setFlyDurations`)
QUIZ_FLY_ON_SECONDS, QUIZ_FLY_OFF_SECONDS = .3, .5
# `SHSUIMenu::internalTransitionOn` / `internalTransitionOff`: the menu's view (panel, rows and portrait) animates its
# alpha 0 -> 1 / 1 -> 0 over 0.25 s, curve 0 (ease in/out); the circle timer and the running man are layers of the
# engine view, shown at once and hidden at once. A tap shows the row's pressed colour and `selectionTimer` fires
# `itemSelected` 0.1 s later (`tableView:didSelectRowAtIndexPath:`); an ordinary choice then goes straight to
# `finishUI` -> `transitionOff` (no fly-off: only the quiz calls `flyOffCurrentChoices`).
TRANSITION_MS = 250
SELECT_MS = 100


def ease_in_out(t):
    """kCAMediaTimingFunctionEaseInEaseOut, cubic Bezier (0.42, 0) (0.58, 1)."""
    t = min(1., max(0., t))
    low, high = 0., 1.
    for _ in range(40):
        s = (low + high) / 2
        x = 3 * (1 - s) ** 2 * s * .42 + 3 * (1 - s) * s * s * .58 + s ** 3
        low, high = (s, high) if x < t else (low, s)
    s = (low + high) / 2
    return 3 * (1 - s) * s * s + s ** 3


def panel_alpha(shown_ms, closing_ms=None):
    """The menu view's alpha `shown_ms` after it appeared, or `closing_ms` after a row was tapped. The fade-out is a
    new UIView animation from the model value 1 (no `setAnimationBeginsFromCurrentState`), so a tap during the fade-in
    first shows the panel whole."""
    if closing_ms is None:
        return ease_in_out(shown_ms / TRANSITION_MS)
    return 1 - ease_in_out((closing_ms - SELECT_MS) / TRANSITION_MS)


def fly_on(position, seconds, duration=FLY_ON_SECONDS):
    """Fraction of the way home (0 at the offsets, 1 in place) for the row at `position`: `tableView:cellForRowAt
    IndexPath:` flies both labels on after position * 0.25 * duration / 2, over duration / 2."""
    delay, length = position * .25 * duration / 2, duration / 2
    return ease_in_out((seconds - delay) / length)


def fly_off(position, selected, seconds, count=4, duration=QUIZ_FLY_OFF_SECONDS):
    """Fraction of the way out for `flyAwayLabels:`: the chosen row leaves after half the duration over the other
    half; the rest after (count - distance) / count of a quarter, over a quarter."""
    half, quarter = duration / 2, duration / 4
    if position == selected:
        delay, length = half, duration - half
    else:
        delay, length = (count - abs(selected - position)) / count * quarter, half - quarter
    return ease_in_out((seconds - delay) / length)


def label_offsets(home, geometry=None):
    """(first label, second label) x offsets in points at `home` (0 out, 1 in place)."""
    g = geometry or HD_GEOMETRY
    return g.label_fly * (1 - home), (g.panel_width - 2 * g.table_inset) * (1 - home)


def wedge_opacity(index, elapsed, total):
    """SHSCircleTimerLayer: wedge `index` (of 16) keeps its layer's opacity 1 until its own animation begins at
    index / 16 of the timeout, then keyframes 0.8, 0.8, 0 at 0, 0.4, 1 of 1/16 of the timeout (linear, fill
    forwards; `startTimer:totalTime:` offsets the begin times by the time already elapsed)."""
    if total <= 0:
        return 1.
    duration = total * .0625
    progress = (elapsed - index * duration) / duration
    if progress < 0:
        return 1.
    if progress < .4:
        return .8
    return max(0., .8 * (1 - progress) / .6)


def wedge_position(index, width, height, centre=50):
    """`initWithImages:` places the 16 wedges clockwise from twelve o'clock, four per quadrant, around the layer's
    centre (50, 50; CoD's 50-point layer, 25): top-right, bottom-right, bottom-left, top-left. Returns the image's
    top-left in points."""
    quadrant = index // 4
    x = centre if quadrant < 2 else centre - width
    y = centre - height if quadrant in (0, 3) else centre
    return x, y
