"""Local font faces used by the iOS app; no font data is distributed.

The IPA bundles Pajama Hip (505) and MonoNumerals (504). Its other fonts are
system faces, looked up by SHSEngine::initFonts at 0003c440. Desktop glyph
rasterization uses FreeType/Pillow, not the original CoreGraphics renderer.
See docs/IPA.md for the resulting fidelity limits.
"""
from dataclasses import dataclass
import base64
from io import BytesIO
import json
import os
import logging
from pathlib import Path
import re
import struct
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

from .fonts import BitmapFont, FontError, Glyph


@dataclass(frozen=True)
class IOSFont(BitmapFont):
    cap_height: float
    descent: float


def _design_metrics(font, source, index):
    """Read SFNT units, as CSFont uses CGFont metrics before rasterization.

    Older supplied/system faces have no OS/2 cap-height field. CoreGraphics
    averages the H/O tops for these faces; measure at the font's design size
    without point-size rounding (verified against local CGFont metrics).
    Pillow still owns font decoding, including glyph selection and advances.
    """
    data = source.getvalue() if isinstance(source, BytesIO) else Path(source).read_bytes()
    try:
        offset = struct.unpack_from('>I', data, 12 + index * 4)[0] if data[:4] == b'ttcf' else 0
        count = struct.unpack_from('>H', data, offset + 4)[0]
        tables = {}
        for n in range(count):
            tag, _, start, length = struct.unpack_from('>4sIII', data, offset + 12 + n * 16)
            if start + length > len(data):
                raise ValueError('Truncated font table')
            tables[tag] = data[start:start + length]
        units = struct.unpack_from('>H', tables[b'head'], 18)[0]
        if not 16 <= units <= 16384:
            raise ValueError('Invalid font units per em')
        design = font.font_variant(size=units)
        cap = 0
        os2 = tables.get(b'OS/2', b'')
        if len(os2) >= 90 and struct.unpack_from('>H', os2)[0] >= 2:
            cap = struct.unpack_from('>h', os2, 88)[0]
        if cap <= 0:
            cap = sum(-design.getbbox(c, anchor='ls')[1] for c in 'HO') // 2
        descent = -struct.unpack_from('>h', tables[b'hhea'], 6)[0]
        return design, units, cap, descent
    except (KeyError, struct.error, ValueError) as error:
        raise FontError(f'Cannot read IPA font metrics: {error}') from error


@dataclass(frozen=True)
class FontFace:
    family: str
    style: str
    filenames: tuple[str, ...]


FACES = {
    'PajamaHip': FontFace('Pajama Hip', 'Regular', ('PajamaHip.ttf', 'Pajama Hip.ttf')),
    'ArialRoundedMTBold': FontFace('Arial Rounded MT Bold', 'Regular',
                                  ('Arial Rounded Bold.ttf', 'ARLRDBD.TTF')),
    'ArialMT': FontFace('Arial', 'Regular', ('Arial.ttf', 'arial.ttf')),
    'TrebuchetMS_Bold': FontFace('Trebuchet MS', 'Bold', ('Trebuchet MS Bold.ttf', 'trebucbd.ttf')),
    'TrebuchetMS_Italic': FontFace('Trebuchet MS', 'Italic', ('Trebuchet MS Italic.ttf', 'trebucit.ttf')),
    'VerdanaBoldItalic': FontFace('Verdana', 'Bold Italic', ('Verdana Bold Italic.ttf', 'verdanaz.ttf')),
}


def _font_directories():
    paths = [Path('/System/Library/Fonts/Supplemental'), Path('/System/Library/Fonts'),
             Path('/Library/Fonts'), Path.home() / 'Library/Fonts',
             Path('/usr/share/fonts/truetype/msttcorefonts'),
             Path('/usr/share/fonts/truetype/msttcorefonts-installer'),
             Path.home() / '.fonts', Path.home() / '.local/share/fonts']
    if os.environ.get('WINDIR'):
        paths.append(Path(os.environ['WINDIR']) / 'Fonts')
    if os.environ.get('LOCALAPPDATA'):
        paths.append(Path(os.environ['LOCALAPPDATA']) / 'Microsoft/Windows/Fonts')
    return paths


def _candidates(face):
    wanted = {name.casefold() for name in face.filenames}
    for directory in _font_directories():
        try:
            for path in sorted(directory.iterdir()):
                if path.name.casefold() in wanted and path.is_file():
                    yield path, 0
        except OSError:
            continue
    # Fontconfig supports arbitrary Linux/user font locations. Its result can
    # be a substitute, so resolve_face verifies the actual face before use.
    try:
        result = subprocess.run(['fc-match', '-f', '%{file}\n%{index}\n',
                                 f'{face.family}:style={face.style}'],
                                capture_output=True, text=True, timeout=5, check=True)
        lines = result.stdout.splitlines()
        if len(lines) == 2 and lines[1].isdigit():
            yield Path(lines[0]), int(lines[1])
    except (OSError, subprocess.SubprocessError, UnicodeError):
        pass


def resolve_face(face):
    """Prefer the original face, then use the platform's default UI font."""
    for path, index in _candidates(face):
        try:
            font = ImageFont.truetype(str(path), 16, index=index, layout_engine=ImageFont.Layout.BASIC)
            if tuple(part.casefold() for part in font.getname()) == (face.family.casefold(), face.style.casefold()):
                return path, index
        except (OSError, ValueError):
            continue
    for path, index in _system_default(face):
        try:
            font = ImageFont.truetype(str(path), 16, index=index, layout_engine=ImageFont.Layout.BASIC)
        except (OSError, ValueError):
            continue
        logging.warning('IPA font %s (%s) is unavailable; using system font %s (%s)',
                        face.family, face.style, *font.getname())
        return path, index
    raise FontError(f'No usable system font is installed for {face.family} ({face.style}). '
                    'Install a system UI font, then reopen the library. '
                    'IPA asset import does not require fonts.')


def _system_default(face):
    if sys.platform == 'darwin':
        for filename in (('SFNSItalic.ttf', 'SFNS.ttf') if face.style == 'Italic' else
                         ('SFNS.ttf', 'SFNSDisplay.ttf')):
            yield Path('/System/Library/Fonts') / filename, 0
    elif sys.platform == 'win32':
        directory = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
        filename = {'Bold': 'segoeuib.ttf', 'Italic': 'segoeuii.ttf'}.get(face.style, 'segoeui.ttf')
        yield directory / filename, 0
        yield directory / 'segoeui.ttf', 0
    else:
        # Ask fontconfig for its configured generic sans family. Here a
        # substitution is intentional: this is the user's requested fallback.
        generic = FontFace('sans-serif', face.style, ())
        yield from _candidates(generic)


def render_font(library, name):
    """Return a text-layout font and RGBA atlas, cached only in this library."""
    cache = getattr(library, '_ios_fonts', None)
    if cache is None:
        library._ios_fonts = cache = {}
    if name in cache:
        return cache[name]
    color, stroke, source, index = (255, 255, 255, 255), 0, None, 0
    if name in ('PajamaHip24', 'PajamaHip26', 'PajamaHip266', 'PajamaHipG26', 'PajamaHipY26', 'PajamaHipS26'):
        from .games import GAMES, game_id
        size = 24 if name == 'PajamaHip24' else 26
        face, bundled = GAMES[game_id(library)].NAME_FONT
        if bundled in library.base_members:
            source = BytesIO(library.read_asset(bundled))
        color = (*GAMES[game_id(library)].NAME_COLORS[name], 255)
        stroke = 0 if size == 24 else 2
    else:
        match = re.fullmatch(r'(ArialRoundedMTBold|ArialMT|TrebuchetMS_Bold|TrebuchetMS_Italic)(11|14|15|16|20|22|28|30)', name)
        if match is None:
            raise FontError(f'Unsupported IPA font role: {name}')
        face, size = match[1], int(match[2])
    if sys.platform == 'ios':
        # The host looks up the original system face, then the system default.
        # Layout roles, colors and glyph history stay in this shared module.
        import exp_platform
        request = dict(operation='atlas', face=face, size=size, color=color, stroke=stroke)
        if source is not None:
            request['data'] = base64.b64encode(source.getvalue()).decode('ascii')
        native = json.loads(exp_platform.font(json.dumps(request)))
        glyphs = {values[0]: Glyph(*values) for values in native['glyphs']}
        glyphs[202] = Glyph(202, 0, 0, 0, 0, 0, 0, glyphs[32].advance)
        atlas = Image.open(BytesIO(base64.b64decode(native['png']))).convert('RGBA')
        result = IOSFont(name, size, size, name + '.png', glyphs, {}, native['cap'], native['descent']), atlas
        cache[name] = result
        return result
    if source is None:
        sources = getattr(library, '_ios_font_sources', None)
        if sources is None:
            library._ios_font_sources = sources = {}
        if face not in sources:
            sources[face] = resolve_face(FACES[face])
        path, index = sources[face]
        source = str(path)
    try:
        # BASIC disables shaping across byte glyphs, matching KiWi's
        # individual-character path.
        font = ImageFont.truetype(source, size, index=index, layout_engine=ImageFont.Layout.BASIC)
    except (OSError, ValueError) as error:
        raise FontError(f'Cannot open IPA font {name}: {error}') from error
    design, units, cap, descent = _design_metrics(font, source, index)
    glyphs = {}
    cell = (size + stroke * 2) * 3
    atlas = Image.new('RGBA', (cell * 16, cell * 16))
    draw = ImageDraw.Draw(atlas)
    for code in range(32, 256):
        if 127 <= code < 160:
            continue
        char = chr(code)
        left, top, right, bottom = font.getbbox(char, anchor='ls', stroke_width=stroke)
        x, y = code % 16 * cell, code // 16 * cell
        if right - left > cell or bottom - top > cell:
            raise FontError(f'IPA glyph exceeds its atlas cell: {name} U+{code:04X}')
        draw.text((x - left, y - top), char, font=font, anchor='ls', fill=color,
                  stroke_width=stroke, stroke_fill=(255, 255, 255, 255))
        glyphs[code] = Glyph(code, x, y, right - left, bottom - top,
                             left, size + top, design.getlength(char) * size / units)
    # SHS text is byte-oriented. 0xCA is a nonbreaking space in CSFontInfo.
    glyphs[202] = Glyph(202, 0, 0, 0, 0, 0, 0, glyphs[32].advance)
    result = IOSFont(name, size, size, name + '.png', glyphs, {},
                     cap * size / units, descent * size / units), atlas
    cache[name] = result
    return result
