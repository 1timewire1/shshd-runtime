"""Vector text for the iOS HD build's fonts, sharing the bitmap layout code.

The Android APK ships bitmap fonts named after Arial Rounded / Pajama Hip /
Trebuchet, but the Arial Rounded ones were generated from Java's generic
"Dialog.bold" (see their `info face=` line), so their advances are not the
real font's. The HD build has no atlases at all: `SHSEngine::initFonts`
creates a CGFont per face and `CSFont::init` gives each instance a point size
that is exactly twice the number in the Android font's name (ArialRounded 16
-> 32, PajamaHip 26 -> 52, Trebuchet 14 -> 28), with the theme colors listed
in `PAJAMA_COLORS`. `CSFont::getCharAdvance` is the CGFont glyph advance times
size over unitsPerEm and there is no kerning, so a `VectorFont` is a
`BitmapFont` whose glyphs carry real advances and ink boxes at the logical
size (the Android name's number) and whose kerning table is empty; the layout
code (wrapping, indents, ink bounds) then runs unchanged. Vertical placement
keeps the Android font's own line height and baseline, which the panel
calibrations were taken against.

Fonts are looked up on the player's machine, never bundled: Pajama Hip and the
digit font are TrueType resources inside the imported HD app bundle; Arial
Rounded MT Bold is used when installed (macOS ships it, Office installs it
on Windows) and otherwise the nearest Arial-metric system face, which keeps
line breaks close to HD's. A player who owns the real font but can't (or would
rather not) install it system-wide can instead drop the file into their own
library's `fonts/` folder, named after one of `SYSTEM_FONTS`' own family
candidates below (`ArialRoundedMTBold.ttf` for the main one; case doesn't
matter) -- checked ahead of the OS's installed fonts, same "a file in the
player's own library" convention as the HD twin store (`hd_twins.py`). Set
SHS_ARIAL_ROUNDED_FONT (or the other SHS_*_FONT variables below) to a font
file to override either of those, or SHS_VECTOR_TEXT=0 to keep the Android
bitmap fonts.
"""
from dataclasses import dataclass, field, replace
from io import BytesIO
import math
import os
from pathlib import Path
import re

import pygame

from .content import ContentError
from .fonts import BitmapFont, FontError, Glyph

# Advances and ink boxes are measured once at this pixel size and scaled;
# integer rounding at 1024 px is far below anything visible.
REFERENCE_PX = 1024

# HD fill colors (ARGB in initFonts) by Pajama Hip variant.
PAJAMA_COLORS = {'': (41, 104, 221), '6': (180, 78, 78), 'G': (137, 137, 137), 'Y': (180, 109, 26)}
# CSFont::setStroke(width 8 at size 52): the outline is centered on the glyph
# edge, so it extends half of it outside. The stroked instance is drawn under
# the plain fill instance. Stroke color is not visible in the decompile and
# is read as white from HD screenshots.
PAJAMA_STROKE_WIDTH = 8 / 52
STROKE_COLOR = (255, 255, 255)

# The text styles inherited from the Android layout code carry Android's
# theme colors; HD's CSFont instances use these (initFonts ARGB colors) for
# the same themes and for the emphasis marker.
HD_COLORS = {
    (1, 76, 215): (41, 104, 221),      # blue
    (166, 45, 45): (180, 78, 78),      # pink/red
    (108, 108, 108): (137, 137, 137),  # gray
    (223, 163, 52): (180, 109, 26),    # gold
    (254, 53, 0): (254, 53, 53),       # red emphasis
    # Choice-option labels are the theme color 16% toward white (measured: blue (41, 104, 221) reads
    # (75, 127, 225) on the light-mode choice photos, the same as the pause menu's row labels). Their keys
    # are the theme colors one level off, so option text can be told apart from description text.
    (2, 76, 215): (75, 127, 225),
    (167, 45, 45): (192, 106, 106),
    (109, 108, 108): (162, 162, 162),
    (224, 163, 52): (194, 136, 79),
}

# (environment override, family names to try in order, bold, italic)
SYSTEM_FONTS = {
    'arial-rounded': ('SHS_ARIAL_ROUNDED_FONT',
                      ('arialroundedmtbold', 'arialrounded', 'arialbold', 'arial', 'liberationsans', 'arimo',
                       'helveticaneue', 'helvetica', 'dejavusans'), True, False),
    'arial': ('SHS_ARIAL_FONT', ('arial', 'liberationsans', 'arimo', 'helvetica', 'dejavusans'), False, False),
    'trebuchet-bold': ('SHS_TREBUCHET_BOLD_FONT',
                       ('trebuchetms', 'trebuchet', 'verdana', 'liberationsans', 'dejavusans'), True, False),
    # HD's `TrebuchetMS-Italic` is the regular italic (the bold one is separate).
    'trebuchet-italic': ('SHS_TREBUCHET_ITALIC_FONT',
                         ('trebuchetms', 'trebuchet', 'verdana', 'liberationsans', 'dejavusans'), False, True),
}


def enabled() -> bool:
    return os.environ.get('SHS_VECTOR_TEXT', '1') != '0'


FONTS_DIRECTORY = 'fonts'
FONT_EXTENSIONS = ('.ttf', '.otf', '.ttc')


def _library_font_path(library, families):
    """The first of `families` found as a same-named file in the player's own library (see the module
    docstring); None without a library, without a `fonts/` folder, or without a match."""
    directory = getattr(library, 'directory', None)
    if directory is None:
        return None
    fonts_dir = Path(directory) / FONTS_DIRECTORY
    try:
        by_stem = {}
        for entry in fonts_dir.iterdir():
            if entry.is_file() and entry.suffix.lower() in FONT_EXTENSIONS:
                by_stem.setdefault(entry.stem.lower(), entry)
    except OSError:
        return None
    for family in families:
        found = by_stem.get(family.lower())
        if found is not None:
            return str(found)
    return None


def system_font_path(role: str, library=None):
    """A font file for `role`: an explicit SHS_*_FONT override, else a file the player supplied in their own
    library's `fonts/` folder (when `library` is given), else one installed on this machine, else None."""
    variable, families, bold, italic = SYSTEM_FONTS[role]
    override = os.environ.get(variable)
    if override:
        return override if os.path.isfile(override) else None
    supplied = _library_font_path(library, families)
    if supplied:
        return supplied
    if not pygame.font.get_init():
        pygame.font.init()
    for family in families:
        try:
            path = pygame.font.match_font(family, bold=bold, italic=italic)
        except (OSError, pygame.error):
            path = None
        if path:
            return path
    return None


@dataclass(frozen=True)
class FaceSource:
    """Font bytes or a file, opened at any pixel size on demand."""
    path: str | None = None
    data: bytes | None = None
    label: str = ''
    _fonts: dict = field(default_factory=dict, compare=False, hash=False, repr=False)

    def font(self, px):
        # Per instance: a Font is invalid once the font module is re-initialized.
        if px not in self._fonts:
            self._fonts[px] = pygame.font.Font(self.path if self.path else BytesIO(self.data), px)
        return self._fonts[px]

    def reference(self):
        return self.font(REFERENCE_PX)


@dataclass(frozen=True)
class VectorFont(BitmapFont):
    source: FaceSource = None
    logical_size: float = 0
    fill: tuple | None = None
    stroke: float = 0
    # A same-color stroke on the fill instance itself (`CSFont::setStroke`
    # 3 at size 40 for the notice): it thickens the glyph by half its width.
    embolden: float = 0
    # That stroke's own colour when it is not the fill's (`CSFont::setStroke`'s second argument: the quiz score's
    # white TrebuchetMS-Bold has a 0.6-point 0xffb4b4b4 edge). Drawn over the fill (fill-then-stroke).
    embolden_color: tuple | None = None

    def render_glyph(self, code: int, color, scale: float):
        """(surface, dx, dy): the glyph at `scale` device pixels per logical
        unit, to be blitted at (pen_x + dx, baseline_y + dy) in device
        pixels. Stroked fonts are dilated first, then filled on top."""
        px = max(1, round(self.logical_size * scale))
        font = self.source.font(px)
        ascent = font.get_ascent()
        fill = (HD_COLORS.get(tuple(color), color) if self.fill is None
                else tuple(a * b // 255 for a, b in zip(self.fill, color)))
        if self.stroke > 0 or self.embolden > 0:
            stroked = self._stroked_glyph(code, fill, px)
            if stroked is not None:
                return stroked
        glyph = font.render(chr(code), True, fill)
        # SDL_ttf starts the bitmap at the leftmost ink, so a glyph whose ink begins left of the pen (a negative left
        # bearing: Arial Rounded's "j" and "f") comes out with the pen that far inside it. CoreGraphics draws at the pen
        # (`CSFont::drawChar` -> CGContextShowGlyphsAtPoint), so step back by the bearing; without it the "j" of "just" sat
        # 1.5 points right, against the "u" (the owner's comparison with HD).
        try:
            metrics = font.metrics(chr(code))[0]
        except (pygame.error, IndexError):
            metrics = None
        left = min(0, metrics[0]) if metrics else 0
        pad = 0
        if self.stroke > 0 or self.embolden > 0:
            # Half a stroke's width, rounded half up: Python's round() takes 4.5 to 4 and 1.5 to 2, which left the
            # notice's white ring (9-point outline less the fill's 3-point stroke, 4.5 - 1.5 = 3 points on the
            # device, photo IMG_0088) 2 points wide at one pixel per point.
            half = lambda width: max(1, math.floor(width * px / 2 + .5))
            pad = half(max(self.stroke, self.embolden))
            size = glyph.get_width() + 2 * pad, glyph.get_height() + 2 * pad
            layer = pygame.Surface(size, pygame.SRCALPHA)
            if self.stroke > 0:
                _grow(layer, font.render(chr(code), True, STROKE_COLOR), pad, half(self.stroke))
            if self.embolden > 0:
                # Grown on its own layer: max-blending straight onto the
                # outline would let the outline's white win every channel.
                body = pygame.Surface(size, pygame.SRCALPHA)
                _grow(body, glyph, pad, half(self.embolden))
                layer.blit(body, (0, 0))
            else:
                layer.blit(glyph, (pad, pad))
            glyph = layer
        return glyph, left - pad, -ascent - pad

    def _stroked_glyph(self, code, fill, px):
        """CoreGraphics fill-and-stroke (glyph_outline): the outline instance (white, `stroke`) under the fill
        instance (its own colour, `embolden`), each the glyph filled plus a mitered stroke of that width. None when
        the face has no TrueType outline for `code` (the dilation below is used instead)."""
        from .glyph_outline import Outlines, coverage
        outlines = _OUTLINES.get(id(self.source))
        if outlines is None:
            data = self.source.data if self.source.data is not None else Path(self.source.path).read_bytes()
            outlines = _OUTLINES[id(self.source)] = Outlines(data)
        if not outlines.available:
            return None
        layers = []
        if self.stroke > 0:
            layers.append((coverage(outlines, code, px, self.stroke * px), STROKE_COLOR))
        if self.embolden_color is None:
            layers.append((coverage(outlines, code, px, self.embolden * px), fill))
        else:
            layers.append((coverage(outlines, code, px), fill))
            layers.append((coverage(outlines, code, px, self.embolden * px, fill=False), self.embolden_color))
        if any(mask is None for mask, _ in layers):
            return None
        left = min(mask[1] for mask, _ in layers)
        top = min(mask[2] for mask, _ in layers)
        right = max(mask[1] + mask[0].width for mask, _ in layers)
        bottom = max(mask[2] + mask[0].height for mask, _ in layers)
        surface = pygame.Surface((right - left, bottom - top), pygame.SRCALPHA)
        for (mask, x, y), color in layers:
            piece = pygame.image.frombytes(bytes(b for v in mask.tobytes() for b in (*color[:3], v)), mask.size,
                                           'RGBA')
            surface.blit(piece, (x - left, y - top))
        return surface, left, top


_OUTLINES = {}


def _grow(layer, image, pad, radius):
    """Blit `image` onto `layer` (origin `pad`) dilated by `radius`: stacked
    offset copies of the antialiased glyph (max of alpha) keep the edge smooth."""
    offsets = {(0, 0)}
    for r in {radius, max(1, radius * 2 // 3), max(1, radius // 3)}:
        offsets |= {(round(r * math.cos(a * math.pi / 8)), round(r * math.sin(a * math.pi / 8)))
                    for a in range(16)}
    for dx, dy in offsets:
        layer.blit(image, (pad + dx, pad + dy), special_flags=pygame.BLEND_RGBA_MAX)


def vector_font(base: BitmapFont, source: FaceSource, logical_size: float, *, fill=None, stroke=0,
                embolden=0, embolden_color=None, use_common_base=False) -> VectorFont:
    """A `BitmapFont` twin of `base` whose glyphs have real advances and ink
    boxes, at `logical_size` layout units."""
    reference = source.reference()
    scale = logical_size / REFERENCE_PX
    baseline = base.base if use_common_base and base.base else _baseline(base)
    glyphs = {}
    for code, glyph in base.glyphs.items():
        try:
            metrics = reference.metrics(chr(code))[0] if code >= 32 else None
        except (pygame.error, IndexError):
            metrics = None
        if metrics is None:
            # Not in the face: keep the bitmap font's own advance, draw nothing.
            glyphs[code] = replace(glyph, width=0, height=0)
            continue
        minx, maxx, miny, maxy, advance = metrics
        ink = code != 32
        glyphs[code] = Glyph(code, 0, 0, (maxx - minx) * scale if ink else 0, (maxy - miny) * scale if ink else 0,
                             minx * scale, baseline - maxy * scale, advance * scale)
    return VectorFont(base.face, base.declared_size, base.line_height, base.page, glyphs, {},
                      source, logical_size, fill, stroke, embolden, embolden_color, base=baseline)


def _baseline(base: BitmapFont) -> float:
    """The baseline's offset from the top of the line box, as the bitmap font
    actually draws it: the bottom of a capital with no descender, less the
    pixel of antialiasing padding every atlas glyph carries. BMFont's own
    `common base` is not usable: most of these descriptors say 26 whatever
    their line height (14 for ArialMT11), which put small text ~16 units too
    low."""
    for code in (ord('H'), ord('E'), ord('x')):
        glyph = base.glyphs.get(code)
        if glyph and glyph.height:
            return glyph.yoffset + glyph.height - 1
    return base.line_height * 0.8


# The Strength Up notice: Android draws it in PajamaHipS26 (a red Pajama Hip with
# a baked white outline); HD has no red Pajama Hip and instead builds two
# `TrebuchetMS-Italic` size-40 instances in 0xf0513c, with strokes 9 and 3
# (`SHSUIDialog::startLetterEffectAnimation` takes a fill font and a
# pre-render/stroke font), and the HD photos show red italic letters with a
# white outline. Size 40 is 20 layout units.
NOTICE_FONT_NAME = 'PajamaHipS26'
NOTICE_FILL = (240, 81, 60)
NOTICE_STROKE_WIDTH = 9 / 40
NOTICE_FILL_STROKE = 3 / 40

_NAME = re.compile(r'^(ArialRoundedMTBold|ArialMT|TrebuchetMS_Bold|TrebuchetMS_Italic)(\d+)$')


def parse_name(name: str):
    """(family, size) for an Android bitmap-font name, or None."""
    match = _NAME.match(name)
    return (match.group(1), int(match.group(2))) if match else None


def _pajama_split(name: str):
    match = re.match(r'^PajamaHip([GYS]?)(\d+)$', name)
    if not match:
        return None
    variant, digits = match.groups()
    if variant == '' and digits.endswith('6') and digits != '26' and len(digits) == 3:
        return '6', int(digits[:2])
    return variant, int(digits)


def hd_font(library, name: str, base: BitmapFont):
    """The HD build's vector equivalent of the Android bitmap font `name`,
    or `base` itself when HD fonts are unavailable for it."""
    if not enabled():
        return base
    has_bundle = getattr(library, 'hd_raw_resource', None)
    if has_bundle is None:
        return base
    try:
        if name == NOTICE_FONT_NAME:
            if library.hd_raw_resource(568) is None:
                return base
            path = system_font_path('trebuchet-italic', library)
            if path is None:
                return base
            return vector_font(base, FaceSource(path=path, label='notice'), 20,
                               fill=NOTICE_FILL, stroke=NOTICE_STROKE_WIDTH, embolden=NOTICE_FILL_STROKE)
        if name.startswith('PajamaHip'):
            split = _pajama_split(name)
            if split is None or split[0] == 'S':
                return base
            variant, size = split
            data = library.hd_raw_resource(568)
            if data is None:
                return base
            return vector_font(base, FaceSource(data=data, label='Pajama Hip'), size,
                               fill=PAJAMA_COLORS[variant], stroke=PAJAMA_STROKE_WIDTH, use_common_base=True)
        parsed = parse_name(name)
        if parsed is None:
            return base
        family, size = parsed
        role = {'ArialRoundedMTBold': 'arial-rounded', 'ArialMT': 'arial',
                'TrebuchetMS_Bold': 'trebuchet-bold', 'TrebuchetMS_Italic': 'trebuchet-italic'}[family]
        if library.hd_raw_resource(568) is None:
            return base  # no HD bundle imported: keep the Android build's own look
        path = system_font_path(role, library)
        if path is None:
            return base
        return vector_font(base, FaceSource(path=path, label=role), size)
    except (FontError, pygame.error, OSError):
        return base


def cod_vector_font(library, name: str, base: BitmapFont):
    """Cause of Death's own CSFonts as vector text, when its library links the SHS HD bundle as an art source
    (content.ContentLibrary.add_shs_hd_art). CoD is an iPhone build: initFonts (1.3.4 armv7 00025e68) gives each
    instance the point size in its name, and the layout column is in those points, so the logical size is the
    name's number (HD's iPad build doubles it instead). The faces are CoD's own: the system faces it names, and for
    speaker names the face bundled in its IPA (profile NAME_FONT), dark red with `setStroke(4.0)` at 26 points --
    the ratio of SHS HD's Pajama Hip (8 at 52), drawn the same way (white outline under the fill). `base` is the
    IPA's atlas font, whose metrics the layout keeps; it is returned as it is when a face is missing."""
    if not enabled():
        return base
    try:
        if name.startswith('PajamaHip'):
            from .games import GAMES
            profile = GAMES['cod']
            face, bundled = profile.NAME_FONT
            if bundled not in library.base_members or name not in profile.NAME_COLORS:
                return base
            size = 24 if name == 'PajamaHip24' else 26
            return vector_font(base, FaceSource(data=library.read_asset(bundled), label=face), size,
                               fill=profile.NAME_COLORS[name], stroke=0 if size == 24 else 4 / 26,
                               use_common_base=True)
        parsed = parse_name(name)
        if parsed is None:
            return base
        family, size = parsed
        role = {'ArialRoundedMTBold': 'arial-rounded', 'ArialMT': 'arial',
                'TrebuchetMS_Bold': 'trebuchet-bold', 'TrebuchetMS_Italic': 'trebuchet-italic'}.get(family)
        path = system_font_path(role, library) if role else None
        if path is None:
            return base
        return vector_font(base, FaceSource(path=path, label=role), size)
    except (FontError, pygame.error, OSError, ContentError):
        return base


COD_EMPHASIS = 'TrebuchetMS_Italic16'
COD_EMPHASIS_RED = (254, 53, 53)        # 0xfffe3535


def cod_emphasis_font(library, name: str, base: BitmapFont):
    """Cause of Death's backtick switch fonts (cod/profile.py EMPHASIS_FONTS, initFonts 1.3.4 armv7): TrebuchetMS-Italic at
    16 points, each instance given `setStroke(0.5, colour)`. That stroke is drawn over the fill in the fill's own
    colour (+0x15af4 red, +0x1ebb4 blue), or red over a black fill for the gray and default sets (+0x27c74 at
    0002669e, +0x30d34 at 000267fc). The narration's (+0xfa74) has a 0.6-point stroke in its own colour. The fill
    colour is the layout's (BODY_MARKERS / NARRATION_COLORS). `base` is the installed-face atlas font whose metrics
    the layout keeps; it is returned as it is when the face is missing."""
    try:
        path = system_font_path('trebuchet-italic', library)
        if path is None:
            return base
        width = .6 if name.endswith('NarrationEmphasis') else .5
        edge = COD_EMPHASIS_RED if name.endswith('RedEdge') else None
        return vector_font(base, FaceSource(path=path, label='trebuchet-italic'), 16, embolden=width / 16,
                           embolden_color=edge)
    except (FontError, pygame.error, OSError, ContentError):
        return base


# HD sizes the Android build has no descriptor for, drawn from the descriptor of
# the same face (glyph set and baseline are the same; only the size differs):
# the name-entry field's typed name is Pajama Hip 48 px (24 units).
HD_ONLY_FONTS = {'PajamaHip24': 'PajamaHip26'}


def load_font(library, name: str) -> BitmapFont:
    """Parse the Android bitmap font `name` and upgrade it to HD's vector
    equivalent when one is available (see the module docstring). A base-game
    IPA library has no Android .fnt sets (and can't carry the HD iPad bundle,
    which only supplements an APK), so it keeps the shared font loader's own
    installed-face rendering (fonts.load_font / ios_fonts.py)."""
    if getattr(library, 'kind', 'apk') == 'ipa':
        from .fonts import load_font as base_load_font
        if getattr(library, 'game_id', None) == 'cod' and name.startswith(COD_EMPHASIS):
            # CoD's emphasis switch fonts: always vector, with or without the SHS HD art source, since the
            # installed-face atlas tints one colour and the gray / default ones are black with a red edge.
            cache = library.__dict__.setdefault('_text_fonts', {})
            if name not in cache:
                cache[name] = cod_emphasis_font(library, name, base_load_font(library, COD_EMPHASIS))
            return cache[name]
        base = base_load_font(library, name)
        if getattr(library, 'game_id', None) == 'cod' and getattr(library, 'shs_hd_art', None) is not None:
            cache = library.__dict__.setdefault('_text_fonts', {})
            if name not in cache:
                cache[name] = cod_vector_font(library, name, base)
            return cache[name]
        return base
    cache = library.__dict__.setdefault('_text_fonts', {}) if hasattr(library, '__dict__') else {}
    if name not in cache:
        base = BitmapFont.parse(library.read_ui_asset(f'fonts/{HD_ONLY_FONTS.get(name, name)}.fnt'))
        cache[name] = hd_font(library, name, base)
    return cache[name]


_CAP_HEIGHTS = {}


def cap_height(font) -> float | None:
    """CSFont's line height in layout units, or None for a font with no TrueType face.

    `CSFont::setFontSize` (HD 1.4.38, 00005a18) stores CGFontGetCapHeight * size / unitsPerEm as both
    field 0x24 (each line's baseline sits this far below its top) and the line height `getTextHeight` and
    `drawText` advance by, plus the gap SHSEngine::initFonts sets at +0x20.

    Pajama Hip (resource 568, the app's own file) has a version-1 OS/2 table with no sCapHeight, and on the
    device CGFontGetCapHeight returns its ascent (2182 of 2048): a two-line choice title's lines are 55.4 + 16
    points apart (IMG_0226 / IMG_0227), and the one-line names in IMG_0070 / IMG_0075 sit where that cap centres
    them. The H/O average this used before put both 10 points (two lines) or 5 (one line) too high. Arial Rounded
    is the system font on iOS; the face here is a desktop stand-in (also version 1), whose H and O tops average to
    the description pitch the photos show, so that estimate is kept for stand-ins.
    """
    source = getattr(font, 'source', None)
    if source is None:
        return None
    key = (source.path, id(source.data), source.label)
    if key not in _CAP_HEIGHTS:
        import struct
        data = source.data if source.data is not None else Path(source.path).read_bytes()
        count = struct.unpack_from('>H', data, 4)[0]
        tables = {}
        for n in range(count):
            tag, _, start, length = struct.unpack_from('>4sIII', data, 12 + n * 16)
            tables[tag] = data[start:start + length]
        units = struct.unpack_from('>H', tables[b'head'], 18)[0]
        os2 = tables.get(b'OS/2', b'')
        cap = struct.unpack_from('>h', os2, 88)[0] if len(os2) >= 90 and struct.unpack_from('>H', os2)[0] >= 2 else 0
        if cap <= 0 and source.data is not None:
            cap = struct.unpack_from('>h', tables[b'hhea'], 4)[0]      # the bundled face: CoreGraphics' ascent
        if cap <= 0:
            face = source.font(units)
            cap = sum(face.metrics(c)[0][3] for c in 'HO') / 2
        _CAP_HEIGHTS[key] = cap / units
    return _CAP_HEIGHTS[key] * font.logical_size


_DESCENTS = {}


def descent(font) -> float | None:
    """CSFont field 0x14 in layout units: -CGFontGetDescent * size / unitsPerEm (`CSFont::setFontSize`, 00005a18),
    the font's hhea descender as a positive depth; None for a font with no TrueType face."""
    source = getattr(font, 'source', None)
    if source is None:
        return None
    key = (source.path, id(source.data), source.label)
    if key not in _DESCENTS:
        import struct
        data = source.data if source.data is not None else Path(source.path).read_bytes()
        count = struct.unpack_from('>H', data, 4)[0]
        tables = {}
        for n in range(count):
            tag, _, start, length = struct.unpack_from('>4sIII', data, 12 + n * 16)
            tables[tag] = data[start:start + length]
        units = struct.unpack_from('>H', tables[b'head'], 18)[0]
        _DESCENTS[key] = -struct.unpack_from('>h', tables[b'hhea'], 6)[0] / units
    return _DESCENTS[key] * font.logical_size


def load_font_sized(library, name: str, logical_size: float):
    """The HD vector twin of the Android bitmap font `name` at a size of its own
    (in whatever unit the caller draws at), or None when HD fonts are
    unavailable. The faceplace alert's fonts are 14 device px, not a size any
    Android descriptor has."""
    if not enabled() or getattr(library, 'hd_raw_resource', None) is None:
        return None
    parsed = parse_name(name)
    if parsed is None:
        return None
    key = f'{name}@{logical_size}'
    cache = library.__dict__.setdefault('_text_fonts', {}) if hasattr(library, '__dict__') else {}
    if key not in cache:
        try:
            role = {'ArialRoundedMTBold': 'arial-rounded', 'ArialMT': 'arial',
                    'TrebuchetMS_Bold': 'trebuchet-bold', 'TrebuchetMS_Italic': 'trebuchet-italic'}[parsed[0]]
            path = system_font_path(role, library) if library.hd_raw_resource(568) is not None else None
            base = BitmapFont.parse(library.read_ui_asset(f'fonts/{name}.fnt'))
            cache[key] = None if path is None else vector_font(base, FaceSource(path=path, label=role), logical_size)
        except (ContentError, FontError, pygame.error, OSError):
            cache[key] = None
    return cache[key]
