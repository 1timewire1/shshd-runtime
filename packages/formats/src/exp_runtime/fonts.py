"""Original bitmap-font records and the recovered SHS text-layout rules.

No glyph metrics or images are embedded here. They come from the player's APK.
This module does not depend on a window system. See docs/UI_FIDELITY.md for
native addresses, scope, and the distinction between pen advances and kerning.
"""
from dataclasses import KW_ONLY, dataclass, field, replace
import math
import re
import shlex

from .exp import ContentError


class FontError(ContentError):
    pass


def load_font(library, name):
    if getattr(library, 'kind', 'apk') == 'ipa':
        from .ios_fonts import render_font
        return render_font(library, name)[0]
    return BitmapFont.parse(library.read_ui_asset(f'fonts/{name}.fnt'))


def _integer(value: str) -> int:
    # Native sscanf("%d") consumes the decimal prefix: "6.5" becomes 6.
    match = re.match(r'[+-]?[0-9]+', value)
    if match is None:
        raise FontError(f'Invalid font integer: {value!r}')
    return int(match[0])


@dataclass(frozen=True)
class Glyph:
    code: int
    x: float
    y: float
    width: float
    height: float
    xoffset: int
    yoffset: int
    advance: int


@dataclass(frozen=True)
class BitmapFont:
    face: str
    declared_size: int
    line_height: int
    page: str
    glyphs: dict[int, Glyph]
    kernings: dict[tuple[int, int], int]
    # BMFont `common base`: the baseline's offset from the top of the line box. Keyword-only, so subclasses
    # (ios_fonts.IOSFont) can still add positional fields.
    _: KW_ONLY
    base: int = 0

    @classmethod
    def parse(cls, data: bytes):
        """Read the supported single-page descriptor profile.

        Native parsing ignores declared character counts and atlas dimensions.
        Reject missing/unsafe records rather than reproduce native uninitialized
        memory reads. Repeated glyph and kerning records replace earlier ones.
        """
        info, common, page, glyphs, kernings = {}, {}, None, {}, {}
        try:
            for line in data.decode('utf-8-sig').splitlines():
                tokens = shlex.split(line)
                if not tokens:
                    continue
                kind = tokens[0]
                if kind not in ('info', 'common', 'page', 'char', 'kerning'):
                    continue
                row = dict(token.split('=', 1) for token in tokens[1:])
                if kind == 'info':
                    info = row
                elif kind == 'common':
                    common = row
                elif kind == 'page':
                    if page is not None or _integer(row['id']) != 0:
                        raise FontError('Multiple font pages are unsupported')
                    page = row['file']
                    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', page):
                        raise FontError('Font atlas must be a filename in the fonts namespace')
                elif kind == 'char':
                    code = _integer(row['id'])
                    if not 0 <= code < 2048 or _integer(row.get('page', '0')) != 0:
                        raise FontError('Unsupported glyph ID or page')
                    rect = tuple(float(row[key]) for key in ('x', 'y', 'width', 'height'))
                    if not all(math.isfinite(v) and v >= 0 for v in rect):
                        raise FontError('Invalid glyph rectangle')
                    offsets = tuple(_integer(row[key]) for key in ('xoffset', 'yoffset', 'xadvance'))
                    glyphs[code] = Glyph(code, *rect, *offsets)
                elif kind == 'kerning':
                    first, second, amount = (_integer(row[key]) for key in ('first', 'second', 'amount'))
                    kernings[first & 0xffff, second & 0xffff] = amount
            height = _integer(common['lineHeight'])
            if page is None or not glyphs or not 0 < height <= 4096:
                raise FontError('Incomplete font descriptor or unsupported line height')
            return cls(info.get('face', ''), _integer(info.get('size', '0')),
                       height, page, glyphs, kernings, base=_integer(common.get('base', '0')))
        except (KeyError, UnicodeError, ValueError) as error:
            if isinstance(error, FontError):
                raise
            raise FontError(f'Invalid bitmap-font descriptor: {error}') from error

    def glyph(self, character: str) -> Glyph:
        code = ord(character)
        try:
            return self.glyphs[code]
        except KeyError:
            # The native font table leaves absent advances uninitialized;
            # there is no verified replacement-glyph or system-font fallback.
            if code >= 0x20:
                raise FontError(f'{self.face}: no defined glyph for U+{ord(character):04X}') from None
            # Real HD episode dialogue (confirmed, not hypothetical: three
            # separate episodes) embeds low control-range bytes exactly
            # where typographic punctuation reads naturally -- U+0019 in
            # "Ben\x19s girlfriend", U+0018 before a quoted phrase, U+0009
            # between two sentences -- none of which this font (sourced
            # only from the Android APK) has a glyph for at all; its lowest
            # defined code is the space at 32. Rendering these as an
            # invisible, space-width gap rather than raising is a
            # deliberately conservative guess at *presence* only, not at
            # which specific mark was intended -- stopping the whole
            # episode over a handful of missing glyphs is worse than a
            # slightly-off gap. See legacy/findings.md.
            space = self.glyphs.get(32)
            return Glyph(code, 0, 0, 0, 0, 0, space.yoffset if space else 0,
                        space.advance if space else 0)


Color = tuple[int, int, int]


@dataclass(frozen=True)
class TextStyle:
    height: float
    gap: float = 0
    color: Color = (255, 255, 255)
    markers: tuple[tuple[str, Color], ...] = ()
    # FUN_0004d3f8: positive entries inset the left; negative ones inset right.
    indents: tuple[float, ...] = ()


@dataclass(frozen=True)
class TextLine:
    start: int
    end: int
    x: float
    y: float
    width: float


@dataclass(frozen=True)
class PlacedGlyph:
    index: int
    glyph: Glyph
    x: float
    y: float
    color: Color
    font: str | None = None


@dataclass(frozen=True)
class TextLayout:
    lines: tuple[TextLine, ...]
    glyphs: tuple[PlacedGlyph, ...]
    width: float
    height: float
    previous_glyph: int
    color: Color
    alternate_color: Color
    highlighted: bool

    @property
    def ink_bounds(self):
        if not self.glyphs:
            return (0, 0, 0, 0)
        return (min(g.x for g in self.glyphs), min(g.y for g in self.glyphs),
                max(g.x + g.glyph.width for g in self.glyphs),
                max(g.y + g.glyph.height for g in self.glyphs))


def layout_text(font: BitmapFont, text: str, width: float, style: TextStyle,
                *, previous_glyph: int = -1,
                switch_fonts: dict[str, tuple[str, BitmapFont]] | None = None) -> TextLayout:
    """Lay out a complete byte string with native unkerned wrapping.

    Coordinates use a downward Y axis and the native nominal line-box origin.
    Kerning displaces only the drawn glyph, never the pen or wrap boundary.
    Spaces and color markers do not update the previous *drawn* glyph. Return
    that state explicitly. Label updates use TextHistory to carry it between
    font objects; measurement and rendering must not advance that history.
    Outline dialogue can associate a marker with another face/atlas role.
    Its glyphs use that face's advances on the base face's common baseline;
    the caller supplies the maximum cap height as the nominal line height.
    """
    if (not all(math.isfinite(v) for v in (width, style.height, style.gap, *style.indents))
            or width <= 0 or style.height <= 0 or style.height + style.gap < 0):
        raise FontError('Invalid text dimensions or line step')
    text = text.split('\x00', 1)[0]
    try:
        text.encode('latin-1')
    except UnicodeError:
        raise FontError('Native story text must be Latin-1') from None
    markers = dict(style.markers)
    faces, advances, selected = [], [], None
    for character in text:
        if character in markers and switch_fonts:
            selected = switch_fonts.get(character) if selected is None else None
        role, face = selected if selected is not None else (None, font)
        faces.append((role, face))
        advances.append(0 if character in markers or character == '\n' else face.glyph(character).advance)
    lines, index = [], 0
    while index < len(text):
        while index < len(text) and text[index] == ' ':
            index += 1
        if index == len(text):
            break
        start = index
        indent = int(style.indents[len(lines)]) if len(lines) < len(style.indents) else 0
        available = width - abs(indent)
        pen = 0
        while index < len(text) and text[index] != '\n':
            advance = advances[index]
            if advance > available:
                # Native aborts this layout; avoid an endless wrap retry.
                raise FontError('The text rectangle cannot fit a single glyph')
            if pen + advance > available:
                end = text.rfind(' ', start, index + 1)
                if end <= start:
                    end = index  # Split a word only when it cannot fit a line.
                index = end
                break
            pen += advance
            index += 1
        else:
            end = index
            if index < len(text):  # Consume an explicit newline.
                index += 1
        lines.append(TextLine(start, end, max(0, indent),
                              len(lines) * (style.height + style.gap),
                              max(0, sum(advances[start:end]))))
    placements = []
    color, alternate, highlighted = style.color, style.color, False
    baseline = getattr(font, 'cap_height', style.height) if switch_fonts else style.height
    for line in lines:
        pen = line.x
        for index in range(line.start, line.end):
            character = text[index]
            if character in markers:
                # All registered delimiters share one toggle, even when mixed.
                if highlighted:
                    color, alternate = alternate, color
                else:
                    color, alternate = markers[character], color
                highlighted = not highlighted
                continue
            role, face = faces[index]
            glyph = face.glyph(character)
            if character != ' ':
                kerning = face.kernings.get((previous_glyph & 0xffff, glyph.code), 0)
                if glyph.width and glyph.height:
                    # CSFont switches faces on the same baseline. Its line
                    # step uses the tallest registered face's cap height.
                    placements.append(PlacedGlyph(index, glyph, pen + glyph.xoffset + kerning,
                        line.y + baseline - face.line_height + glyph.yoffset, color, role))
                # FUN_0004cb90 stores a byte, then LDRSB sign-extends it on
                # the next lookup (before packing it into the high half).
                previous_glyph = glyph.code if glyph.code < 128 else glyph.code - 256
            pen += glyph.advance
    height = len(lines) * (style.height + style.gap)
    if height:
        height -= style.gap
    return TextLayout(tuple(lines), tuple(placements),
                      max((line.width for line in lines), default=0), height,
                      previous_glyph, color, alternate, highlighted)


def layout_label(font: BitmapFont, text: str, width: float, height: float,
                 style: TextStyle, flags: int, *, previous_glyph: int = -1) -> TextLayout:
    """FUN_0004dc20: wrapped/aligned text in a native node's content rectangle.

    Coordinates start at the node's bottom-left corner and increase downward,
    as in layout_text. Apply the node's anchor/scale/position separately.
    Bits 0..1 select left/center/right, bits 2..3 top/center/bottom, bit 4
    enables wrapping, and bit 5 limits the number of drawn lines to the height.
    """
    if not all(math.isfinite(v) and v >= 0 for v in (width, height)):
        raise FontError('Invalid label dimensions')
    wrapping = bool(flags & 0x10)
    if wrapping and width == 0:
        # Native aborts when the zero-sized initial label cannot fit a glyph.
        return replace(layout_text(font, '', 1, style), previous_glyph=previous_glyph)
    text_width = width if wrapping else layout_text(font, text, 2**31, style).width + .1
    measured = layout_text(font, text, text_width, style)
    horizontal = {2: .5, 3: 1}.get(flags & 3, 0)
    block_x = (width - text_width) * horizontal
    vertical = flags & 0xc
    block_y = ((height - measured.height) / 2 if vertical == 8 else
               height - measured.height - 4 if vertical == 12 else 0)
    limit = (height if flags & 0x20 else 4096) + (4 if vertical == 12 else 0)
    step = style.height + style.gap
    capacity = (max(1, int((limit - style.height) // step) + 1) if step else
                1 if style.height > limit else len(measured.lines))
    lines, glyphs = [], []
    for index, line in enumerate(measured.lines[:capacity]):
        indent = int(style.indents[index]) if index < len(style.indents) else 0
        shift_x = block_x + (text_width - abs(indent) - line.width) * horizontal
        lines.append(replace(line, x=line.x + shift_x, y=line.y - block_y))
        glyphs.extend(replace(g, x=g.x + shift_x, y=g.y - block_y)
                      for g in measured.glyphs if line.start <= g.index < line.end)
    result = replace(measured, lines=tuple(lines), glyphs=tuple(glyphs))
    return kern_layout(font, text, result, previous_glyph, markers=style.markers)


def kern_layout(font, text, layout, previous_glyph, *, markers=()):
    """Apply a label's incoming byte without changing its line measurements.

    Only drawn lines visit FUN_0004cb90. Spaces and registered color markers
    leave the global byte alone; zero-ink glyphs still update it. Layouts passed
    here start with the ordinary -1 sentinel, so only their first glyph can
    need a displacement. This also handles height-clipped labels correctly.
    """
    ignored = {' ', '\n', *(key for key, _ in markers)}
    first = True
    glyphs = layout.glyphs
    for line in layout.lines:
        for index in range(line.start, line.end):
            if text[index] in ignored:
                continue
            code = font.glyph(text[index]).code
            if first:
                shift = (font.kernings.get((previous_glyph & 0xffff, code), 0)
                         - font.kernings.get((0xffff, code), 0))
                if shift:
                    glyphs = tuple(replace(g, x=g.x + shift) if g.index == index else g for g in glyphs)
                first = False
            previous_glyph = code if code < 128 else code - 256
    return replace(layout, glyphs=glyphs, previous_glyph=previous_glyph)


@dataclass
class TextHistory:
    """Android's process-wide last drawn byte and each live label's input.

    Update explicitly when native setString creates/repositions glyph nodes,
    including repeated assignments of the same string. Cached layout, drawing,
    letter visibility and measurement are pure reads. No font/asset bytes are
    stored in a save.
    """
    previous_glyph: int = -1
    labels: dict[str, int] = field(default_factory=dict)
    footer: str = ''

    def initial(self, label):
        return self.labels.get(label, -1)

    def update(self, label, font, text, layout, *, markers=()):
        result = kern_layout(font, text, layout, self.previous_glyph, markers=markers)
        self.labels[label] = self.previous_glyph
        self.previous_glyph = result.previous_glyph
        return result

    def validate(self):
        if (not -128 <= self.previous_glyph <= 127 or len(self.labels) > 65536
                or '\0' in self.footer
                or any(not key or len(key) > 80 or not -128 <= value <= 127
                       for key, value in self.labels.items())):
            raise FontError('Invalid bitmap label history')
