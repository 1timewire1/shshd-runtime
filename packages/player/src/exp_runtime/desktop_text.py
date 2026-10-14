"""Shared atlas drawing for the presentation-independent text layout."""
from collections import OrderedDict
from functools import lru_cache
from io import BytesIO
from math import floor

from . import graphics as pygame

from .fonts import FontError, layout_text, load_font


class BitmapTextRenderer:
    def __init__(self, library):
        self.library = library
        self.fonts = {}
        self.glyph_images = OrderedDict()

    def font(self, name):
        if name not in self.fonts:
            font = load_font(self.library, name)
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

    @lru_cache(maxsize=128)
    def layout(self, name, text, width, style):
        return layout_text(self.font(name), text, width, style)

    def _glyph_image(self, name, placed, scale):
        glyph = placed.glyph
        key = name, glyph.code, placed.color, scale
        if key not in self.glyph_images:
            atlas = self.fonts[name][1]
            image = atlas.subsurface(pygame.Rect(glyph.x, glyph.y, glyph.width, glyph.height)).copy()
            # Modulate original RGB, retaining colored atlas variants and alpha.
            image.fill((*placed.color, 255), special_flags=pygame.BLEND_RGBA_MULT)
            size = max(1, round(glyph.width * scale)), max(1, round(glyph.height * scale))
            if image.get_size() != size:
                image = pygame.transform.smoothscale(image, size)
            self.glyph_images[key] = image
            if len(self.glyph_images) > 512:
                self.glyph_images.popitem(last=False)
        self.glyph_images.move_to_end(key)
        return self.glyph_images[key]

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
            surface.blit(self._glyph_image(name, placed, scale),
                         (floor(x + placed.x * scale + .5), floor(y + (placed.y - top) * scale + .5)))
        return y + (max(layout.height, bottom) - top) * scale

    def draw_layout(self, surface, name, layout, x, y, *, scale=1, source_end=None):
        """Draw a native layout origin without moving its ink overhang."""
        self.font(name)
        for placed in layout.glyphs:
            if source_end is not None and placed.index >= source_end:
                continue
            # Half-to-even rounding snaps adjacent glyph bearings in opposite
            # directions at a half-pixel line origin (notably Continue's i).
            # Use one translation-invariant pixel rule for the whole line.
            surface.blit(self._glyph_image(name, placed, scale),
                         (floor(x + placed.x * scale + .5), floor(y + placed.y * scale + .5)))
