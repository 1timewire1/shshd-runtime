"""Service 90's nonblocking scene label (FUN_0007b97c)."""
from dataclasses import dataclass

from .fonts import TextStyle, layout_text


@dataclass
class SceneBadge:
    asset_id: int
    text: str
    blue: bool
    elapsed_ms: int = 0

    def tick(self, elapsed_ms):
        self.elapsed_ms = min(200, self.elapsed_ms + elapsed_ms)

    def validate(self):
        if not 0 <= self.asset_id <= 32767 or not 0 <= self.elapsed_ms <= 200:
            raise ValueError('Invalid scene label')

    @property
    def text_position(self):
        # Native label node centers in a 171x60 sprite (GL local coordinates).
        n = len(self.text)
        if 15 <= n <= 17:
            return 123, 55, 1.0
        if n < 13:
            x = {'Before Class': 120, 'Mascot Theft': 122, 'Driving Home': 120}.get(self.text, 125)
            return x, 45, 1.0
        if n < 19:
            x, y = {'Before School': (117, 45), "Chuck's Party": (120, 45),
                    'Football Game': (120, 45), 'After Practice': (120, 45),
                    "Counselor's Office": (123, 53), 'Unsupervised Study': (120, 53),
                    'Saturday Night': (119, 45)}.get(self.text, (117, 53))
            return x, y, .9 if self.text == 'Before School' else 1.0
        return 121, 55, 1.0

    @property
    def text_origin(self):
        # FUN_0007b97c: a 110x20 label with (.5,.5) anchor and flags 0x11
        # (wrapped, left/top aligned). Text draws downward from local zero;
        # converting the anchor to screen Y therefore adds half its height.
        x, y, scale = self.text_position
        return x - 55 * scale, 60 - y + 10 * scale, scale


def outline_badge_text(text, font, region, color):
    """CSFont's wrapped, left/center-aligned layout-67 text (flags 0x19).

    Both iOS games use Arial 14, cap-height line boxes and no added gap.
    Bound substitute-font ink to the same region without changing the label
    or any saved state. Android's separate bitmap-label rules remain above.
    """
    # A substitute font may have a glyph wider than the entire native region.
    # Let that glyph wrap alone, then fit its ink with the rest of the label.
    width = max(region.width, max((font.glyph(c).advance
                for c in text.split('\x00', 1)[0] if c != '\n'), default=0))
    layout = layout_text(font, text, width, TextStyle(font.cap_height, 0, color))
    left, top, right, bottom = layout.ink_bounds
    scale = min(1, region.width / max(1, right - left),
                region.height / max(1, bottom - top))
    x, y = region.x, region.y + (region.height - layout.height * scale) / 2
    x = max(region.x - left * scale, min(x, region.x + region.width - right * scale))
    y = max(region.y - top * scale, min(y, region.y + region.height - bottom * scale))
    return layout, (x, y), scale
