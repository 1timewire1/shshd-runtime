"""Native speaker label state and layout (000a7fa8 / 000a8544).

The four font objects survive dialogue changes. Their previous line counts,
content sizes and line spacing are inputs to the next layout, not caches that
can be recomputed from the next speaker's name. See docs/UI_FIDELITY.md.
"""
from copy import deepcopy
from dataclasses import dataclass, field, replace

from .fonts import BitmapFont, TextLayout, TextStyle, layout_label, layout_text
from .ui_assets import LayoutBank, Rect


NAME_FONTS = {-1: 'PajamaHipY26', 2: 'PajamaHip266', 3: 'PajamaHipG26'}
DEFAULT_FONT = 'PajamaHip26'


@dataclass
class NameFontState:
    width: int = 0
    height: int = 0
    gap: int = -16
    # 0007cbbc initializes each label with "SHS", then sets nominal height 16.
    lines: int = 1
    indents: list[int] = field(default_factory=list)

    @property
    def style(self):
        return TextStyle(16, self.gap, indents=tuple(self.indents))

    def validate(self):
        if (not 0 <= self.width <= 65535 or not 0 <= self.height <= 65535
                or self.gap not in (-16, 8) or not 0 <= self.lines <= 65535
                or self.indents not in ([], [0, 5], [0, 20])):
            raise ValueError('Invalid speaker font state')


@dataclass
class SpeakerNames:
    fonts: dict[str, NameFontState] = field(default_factory=dict)
    # State before the current dialogue: redraws and page turns replay only
    # this layout, without advancing the live font objects a second time.
    basis: dict[str, NameFontState] | None = None

    def validate(self):
        for bank in (self.fonts, self.basis):
            if bank is not None:
                if set(bank) - {DEFAULT_FONT, *NAME_FONTS.values()}:
                    raise ValueError('Invalid speaker font bank')
                for state in bank.values():
                    state.validate()


@dataclass(frozen=True)
class SpeakerLabel:
    text: str
    font: str
    layout: TextLayout
    origin: tuple[float, float]
    scale: float
    extra: int
    content_size: tuple[int, int]
    flags: int
    # Outline fonts use CSFont's top-left title region, rather than a Cocos
    # label with retained content size. Keep that distinction at the font
    # adapter boundary, within the common dialogue renderer.
    header: Rect | None = None


def speaker_label(text: str, mode: int, theme: int, bank: LayoutBank, font_loader,
                  states: dict[str, NameFontState]) -> SpeakerLabel:
    """Execute one native name layout, updating only the supplied font bank."""
    font_name = NAME_FONTS.get(theme, DEFAULT_FONT)
    font: BitmapFont = font_loader(font_name)
    if mode == 4:
        return SpeakerLabel('', font_name, layout_text(font, '', 1, TextStyle(16, -16)),
                            (0, 0), .9, 8, (0, 0), 0x19)
    state = states.setdefault(font_name, NameFontState())
    # 000a7fa8 measures theme -1 with the default font, although 000a8544
    # draws it with the separate yellow font object.
    measure_name = NAME_FONTS.get(theme, DEFAULT_FONT) if theme in (2, 3) else DEFAULT_FONT
    measure_state = states.setdefault(measure_name, NameFontState())
    measure_font = font_loader(measure_name)
    rect = bank.rectangle(17, {1: 0x2e, 2: 0x4c, 3: 0x6a}[mode])
    if mode == 2:
        large = layout_text(measure_font, text, 2**31, measure_state.style).width > rect.width
    else:
        measured = layout_text(measure_font, text, rect.width, measure_state.style)
        measure_state.lines = len(measured.lines)
        large = measured.height > rect.height
    extra = 40 if large else 8
    if large:
        rect = bank.rectangle(17, {1: 0x25, 2: 0x43, 3: 0x61}[mode])
        if mode in (1, 2):
            rect = replace(rect, y=rect.y - 40)
    if mode == 1:
        rect = replace(rect, x=rect.x + 1)
    elif mode == 2:
        rect = replace(rect, x=rect.x + (1 if len(text) == 8 else 5))

    unwrapped = layout_text(font, text, 2**31, state.style).width
    w, h = rect.width, rect.height
    scale, offset, flags = .9, 0, 0x1a
    if mode == 1:
        flags = 0x19 if large else 0x1b
        offset = -23 if not large and int(unwrapped) < 127 else 0
        if text != 'Brendizzle':  # Native branch deliberately retains the previous size.
            state.height = h + 30
            if state.lines < 2:
                state.width = w + 20
            else:
                state.width = w + (80 if len(text) < 14 else 40)
                scale = .8
        state.indents = [0, 20]
    elif mode == 2:
        if large:
            state.gap = 8
            flags = 0x19
        if text in ("Howard's Mom", "Howard's Dad", 'French Teacher', "Neighbor's Wife"):
            state.width, state.height, scale = {
                "Howard's Mom": (235, h + 32, .9),
                "Howard's Dad": (223, h + 32, .9),
                'French Teacher': (225, h + 50, .8),
                "Neighbor's Wife": (w + 80, h + 60, .8),
            }[text]
            flags = 0x3d
        elif len(text) == 8:
            if text == 'The Boss':
                text = 'Th e Boss '
            state.width, state.height = w, h + 34
        elif len(text) == 11:
            state.width, state.height, flags = w, h + 82, 0x3d
        elif state.lines < 2:
            text = {'The Mayor': 'Th e Mayor', 'Judge Tigh': 'Judge Ti gh',
                    'Animal Thief': 'Animal Th ief'}.get(text, text)
            state.width, state.height, flags = w + 20, h + 32, 0x19
        elif len(text) < 19:
            state.width, state.height, scale = w + 80, h + 30, .8
            if text == 'Spud The Stud':
                text, scale = 'Spud Th e Stud', .7
        else:
            state.width, state.height, scale = 300, h + 32, .7
        state.indents = [0, 5]
        offset = 23 if int(unwrapped) < 127 else 0
    else:
        if len(text) == 8:
            if text == 'The team':
                text = 'Th e team'
            state.width, state.height = w + 20, h + 34
        elif len(text) < 16:
            text = {'The Whole Room': 'Th e Whole Room', 'The Crowd': 'Th e Crowd'}.get(text, text)
            state.indents = []
            state.width, state.height = w + 20, h + 20
        else:
            state.width, state.height, scale = 580, h + 30, .6

    laid_out = layout_label(font, text, state.width, state.height, state.style, flags)
    state.lines = len(laid_out.lines)
    # 000a8544 sets the node position before setString. Glyph coordinates from
    # layout_label are local to its bottom-left corner, with downward Y.
    px = rect.x + offset - 10 + (w + 20) // 2
    py = 480 - state.height + 19 - rect.y + (h + 20) // 2
    origin = (px - scale * state.width / 2, 480 - py + scale * state.height / 2)
    return SpeakerLabel(text, font_name, laid_out, origin, scale, extra,
                        (state.width, state.height), flags)


def preview_speaker(details, bank, font_loader, names: SpeakerNames | None = None):
    font_name = NAME_FONTS.get(details['theme'], DEFAULT_FONT)
    font = font_loader(font_name)
    if getattr(font, 'cap_height', None) is not None:
        return outline_speaker_label(details['speaker'], details['presentation_mode'],
                                     font_name, bank, font)
    basis = deepcopy(names.basis) if names is not None and names.basis is not None else {}
    return speaker_label(details['speaker'], details['presentation_mode'], details['theme'],
                         bank, font_loader, basis)


def outline_speaker_label(text, mode, font_name, bank, font):
    """SHS/CoD CSFont title layout, independent of Android label history.

    updateTitleBounds (CoD 00036adc / SHS 0007ce08) measures at the normal
    region's width and selects the tall region if wrapped height exceeds it.
    animateTitleLayer sets the offsets/flags below, then drawTextInRegion
    centers the line boxes vertically. CSFont uses cap height and gap 8;
    Cocos's width expansion, nominal height 16 and 0.9 scale do not apply.
    """
    style = TextStyle(font.cap_height, 8)
    rect = bank.rectangle(17, {1: 0x2e, 2: 0x4c, 3: 0x6a}[mode])
    measured = layout_text(font, text, rect.width, style)
    large = measured.height > rect.height
    if large:
        rect = bank.rectangle(17, {1: 0x25, 2: 0x43, 3: 0x61}[mode])
    unwrapped = layout_text(font, text, 2**31, style).width
    flags, offset = 0x1a, 0
    if mode == 1:
        flags = 0x19 if large else 0x1b
        offset = -15 if not large and int(unwrapped) < 135 else 0
        rect = replace(rect, x=rect.x + 1)
        style = replace(style, indents=(0, 20))
    elif mode == 2:
        flags = 0x19
        offset = 15 if int(unwrapped) < 135 else 0
        rect = replace(rect, x=rect.x - 2)
        style = replace(style, indents=(0, 5))
    layout = layout_text(font, text, rect.width, style)
    alignment = {2: .5, 3: 1}.get(flags & 3, 0)
    lines, glyphs = [], []
    for index, line in enumerate(layout.lines):
        indent = style.indents[index] if index < len(style.indents) else 0
        shift = (rect.width - abs(indent) - line.width) * alignment
        lines.append(replace(line, x=line.x + shift))
        glyphs.extend(replace(g, x=g.x + shift) for g in layout.glyphs
                      if line.start <= g.index < line.end)
    layout = replace(layout, lines=tuple(lines), glyphs=tuple(glyphs))
    origin = (rect.x + offset, rect.y + (rect.height - layout.height) / 2)
    return SpeakerLabel(text, font_name, layout, origin, 1, 40 if large else 8,
                        (rect.width, rect.height), flags, rect)


def fit_speaker_ink(label: SpeakerLabel, bounds: Rect):
    """Fit complete visible ink to the header attached to the current box.

    The native routine sizes line boxes using height 16, although the imported
    name glyphs can be taller than 30. Its retained gap can also put a later
    single-line name far above or below the header. Separate overlapping rows,
    then fit both dimensions to the selected normal/tall header. Outline
    fonts retain their native position unless ink exceeds that region or the
    body/portrait boundary. This drawing correction never changes font history.
    """
    layout = label.layout
    if not layout.glyphs:
        return layout, label.origin, label.scale
    lines, glyphs, previous_bottom, shift = [], [], None, 0
    for line in layout.lines:
        row = [g for g in layout.glyphs if line.start <= g.index < line.end]
        if row:
            top = min(g.y for g in row) + shift
            if previous_bottom is not None and top < previous_bottom:
                shift += previous_bottom - top
            previous_bottom = max(g.y + g.glyph.height for g in row) + shift
        lines.append(replace(line, y=line.y + shift))
        glyphs.extend(replace(g, y=g.y + shift) for g in row)
    layout = replace(layout, lines=tuple(lines), glyphs=tuple(glyphs))
    ink_left, ink_top, ink_right, ink_bottom = layout.ink_bounds
    scale = min(label.scale, bounds.width / (ink_right - ink_left),
                bounds.height / (ink_bottom - ink_top))
    if label.header is not None:
        x = min(max(label.origin[0], bounds.x - ink_left * scale),
                bounds.x + bounds.width - ink_right * scale)
        y = min(max(label.origin[1], bounds.y - ink_top * scale),
                bounds.y + bounds.height - ink_bottom * scale)
        return layout, (x, y), scale
    alignment = {2: .5, 3: 1}.get(label.flags & 3, 0)
    spare = bounds.width - (ink_right - ink_left) * scale
    x = bounds.x + spare * alignment - ink_left * scale
    y = bounds.y + bounds.height - ink_bottom * scale
    return layout, (x, y), scale
