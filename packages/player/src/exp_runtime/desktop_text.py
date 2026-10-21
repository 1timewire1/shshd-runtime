"""Shared atlas drawing for the presentation-independent text layout."""
from collections import OrderedDict
from functools import lru_cache
from io import BytesIO
from math import floor

from .graphics import faded
from . import graphics as pygame

from .fonts import BitmapFont, FontError, TextStyle, layout_label, layout_text
from .menu_assets import MenuStrings
from .vector_text import VectorFont, load_font


class BitmapTextRenderer:
    def __init__(self, library):
        self.library = library
        self.fonts = {}
        self.glyph_images = OrderedDict()

    def font(self, name):
        if name not in self.fonts:
            font = load_font(self.library, name)
            if isinstance(font, VectorFont):
                # HD's vector fonts have no atlas; glyphs are drawn from the
                # TrueType face (see vector_text.py).
                self.fonts[name] = font, None
                return font
            try:
                if getattr(self.library, 'kind', 'apk') == 'ipa':
                    from .ios_fonts import render_font
                    image = render_font(self.library, name)[1]
                    atlas = pygame.image.frombytes(image.tobytes(), image.size, 'RGBA')
                else:
                    atlas = pygame.image.load(BytesIO(self.library.read_ui_asset('fonts/' + font.page)))
            except pygame.error as error:
                raise FontError(f'Cannot decode font atlas {font.page}: {error}') from error
            width, height = atlas.get_size()
            for glyph in font.glyphs.values():
                rect = (glyph.x, glyph.y, glyph.width, glyph.height)
                if any(v != int(v) for v in rect):
                    raise FontError('Fractional font atlas rectangles are not supported yet')
                if glyph.x + glyph.width > width or glyph.y + glyph.height > height:
                    raise FontError(f'Glyph {glyph.code} exceeds actual atlas {font.page}')
            self.fonts[name] = font, atlas.convert_alpha()
        return self.fonts[name][0]

    def register(self, name, font):
        """Make a vector font that no Android descriptor names (e.g. HD's 30-point option font) drawable by `name`."""
        if name not in self.fonts:
            self.fonts[name] = font, None
        return self.fonts[name][0]

    @lru_cache(maxsize=128)
    def layout(self, name, text, width, style, *, previous_glyph=-1):
        return layout_text(self.font(name), text, width, style, previous_glyph=previous_glyph)

    @lru_cache(maxsize=64)
    def footer(self, index, previous_glyph=-1):
        text = MenuStrings.load(self.library)[index]
        if getattr(self.library, 'kind', 'apk') == 'ipa':
            # GameModel::init: the outline tooltip uses layout 18's 252x18
            # region at (63,459), centered Arial 11, white alpha 176.
            name = 'ArialMT11'
            label = self.layout(name, text, 252, TextStyle(11), previous_glyph=previous_glyph)
            left, top, right, bottom = label.ink_bounds
            origin = (63 + (252 - (right - left)) / 2 - left,
                      459 + (18 - (bottom - top)) / 2 - top)
            return name, label, origin, 176
        # Android 0007cbbc / 0007d4c8 share this label across story panels:
        # font registry 11, zero content size, center/center at GL (180,25).
        name = 'ArialMT14'
        label = layout_label(self.font(name), text, 0, 0, TextStyle(14, 8), 0x0a,
                             previous_glyph=previous_glyph)
        return name, label, (180, 455), 255

    def draw_footer(self, surface, index, previous_glyph=-1):
        name, label, origin, alpha = self.footer(index, previous_glyph)
        self.draw_layout(surface, name, label, *origin, alpha=alpha)

    def _glyph(self, name, placed, scale):
        """(image, dx, dy): the glyph's surface and its offset, in device
        pixels, from (placed.x, placed.y) * scale. A glyph in a switch font (exp-runtime's iOS emphasis face) names
        its own font."""
        name = getattr(placed, 'font', None) or name
        self.font(name)
        glyph = placed.glyph
        key = name, glyph.code, placed.color, scale
        if key not in self.glyph_images:
            font, atlas = self.fonts[name]
            if atlas is None:
                # Vector glyphs come out positioned by pen and baseline; the
                # layout places them by ink box, so convert once here.
                image, dx, dy = font.render_glyph(glyph.code, placed.color, scale)
                entry = image, dx - glyph.xoffset * scale, dy + (font.base - glyph.yoffset) * scale
            else:
                image = atlas.subsurface(pygame.Rect(glyph.x, glyph.y, glyph.width, glyph.height)).copy()
                # Modulate original RGB, retaining colored atlas variants and alpha.
                image.fill((*placed.color, 255), special_flags=pygame.BLEND_RGBA_MULT)
                size = max(1, round(glyph.width * scale)), max(1, round(glyph.height * scale))
                if image.get_size() != size:
                    image = pygame.transform.smoothscale(image, size)
                entry = image, 0, 0
            self.glyph_images[key] = entry
            if len(self.glyph_images) > 512:
                self.glyph_images.popitem(last=False)
        self.glyph_images.move_to_end(key)
        return self.glyph_images[key]

    def _glyph_image(self, name, placed, scale):
        return self._glyph(name, placed, scale)[0]

    def _blit(self, surface, name, placed, scale, x, y, alpha=255):
        # Half-to-even rounding snaps adjacent glyph bearings in opposite
        # directions at a half-pixel line origin (notably Continue's i).
        # Use one translation-invariant pixel rule for the whole line.
        image, dx, dy = self._glyph(name, placed, scale)
        if alpha != 255:
            image = image.copy()
            image = faded(image, alpha)
        surface.blit(image, (floor(x + placed.x * scale + dx + .5), floor(y + placed.y * scale + dy + .5)))

    def draw(self, surface, name, text, x, y, width, style, *, scale=1):
        """Draw using the current canvas placement; return the next free Y.

        Normalize only the block's top ink overhang for the provisional desktop
        panel. Native line positions, offsets, advances and colors stay in the
        pure layout. Complete native panel anchoring is still being recovered.
        """
        if scale <= 0:
            raise FontError('Font display scale must be positive')
        layout = self.layout(name, text, width / scale, style)
        _, top, _, bottom = layout.ink_bounds
        top = min(0, top)
        for placed in layout.glyphs:
            self._blit(surface, name, placed, scale, x, y - top * scale)
        return y + (max(layout.height, bottom) - top) * scale

    def draw_layout(self, surface, name, layout, x, y, *, scale=1, source_end=None, inline=None, alpha=255):
        """Draw a native layout origin without moving its ink overhang. `inline` maps glyph codes to images drawn in
        place of the glyph (`CSFont::addCharImage`), one layout unit per image pixel. `alpha` fades the glyphs (the
        cursor's blink, Choice hints' faint answers)."""
        self.font(name)
        for placed in layout.glyphs:
            if source_end is not None and placed.index >= source_end:
                continue
            image = inline.get(placed.glyph.code) if inline else None
            if image is None:
                self._blit(surface, name, placed, scale, x, y, alpha)
                continue
            if scale != 1:
                image = self._scaled(image, scale)
            surface.blit(image, (floor(x + placed.x * scale + .5), floor(y + placed.y * scale + .5)))

    @lru_cache(maxsize=64)
    def _scaled(self, image, scale):
        return pygame.transform.smoothscale(image, (max(1, round(image.get_width() * scale)),
                                                    max(1, round(image.get_height() * scale))))
