"""Service 8 title cards: native wipe, input gate and external-atlas lettering."""
from dataclasses import dataclass

from .atlas import AtlasFont
from .ui_assets import LayoutBank
from .vm import VMError


@dataclass
class TitleScreen:
    elapsed_ms: int = 0
    reveal_width: int = 0
    ready: bool = False

    def tick(self, elapsed_ms):
        # 000a650c adds five pixels per update. Use the application's
        # configured 30 Hz cadence, independent of the desktop render rate.
        before = self.elapsed_ms * 30 // 1000
        self.elapsed_ms = min(4000, self.elapsed_ms + elapsed_ms)
        steps = self.elapsed_ms * 30 // 1000 - before
        if steps:
            # The native gate tests the OLD width before adding five.
            self.ready |= self.reveal_width + 5 * (steps - 1) > 240
            self.reveal_width = min(320, self.reveal_width + 5 * steps)

    def acknowledge(self):
        if not self.ready:
            # 000a6800: an early tap completes the wipe, without closing.
            # The following native update opens the acknowledgement gate.
            self.reveal_width = 320
            return False
        return True

    @property
    def background_alpha(self):
        return max(0., min(1., (self.elapsed_ms - 1000) / 3000))

    @property
    def subtitle_scale_y(self):
        return .5 + .5 * max(0., min(1., (self.elapsed_ms - 500) / 500))

    @classmethod
    def settled(cls):
        # Older saves contain no entrance history; preserve their readable,
        # immediately acknowledgeable title instead of replaying the intro.
        return cls(4000, 320, True)

    def validate(self):
        if (type(self.elapsed_ms) is not int or not 0 <= self.elapsed_ms <= 4000
                or type(self.reveal_width) is not int or not 0 <= self.reveal_width <= 320
                or type(self.ready) is not bool):
            raise VMError('Invalid title-screen animation state')
        steps = self.elapsed_ms * 30 // 1000
        if (self.reveal_width not in (min(320, steps * 5), 320)
                or (steps >= 50 and not self.ready)
                or (self.ready and (steps == 0 or self.reveal_width <= 245))):
            raise VMError('Title-screen wipe does not match its clock or input gate')


@dataclass(frozen=True)
class TitleGlyph:
    character: str
    x: int
    y: int


@dataclass(frozen=True)
class TitleLabel:
    asset_id: int
    origin: tuple[float, float]
    scale: float
    glyphs: tuple[TitleGlyph, ...]


def _glyphs(font: AtlasFont, text: str, width: int, *, right=False, subtitle=False):
    """00054148/00054490/0005373c, converted from local GL to downward Y."""
    result, pen_y = [], 0
    # Native subtitle fitting adjusts the first glyph's local Y. Subsequent
    # rows then descend because the title panel sets host flag +0x6ac43.
    adjust = subtitle and 24 < len(text) < 100 and font.height == 23
    for line in font.wrap(text, width):
        x = width - font.width(line) if right else 0
        for character in line:
            if character != ' ' and font.glyph(character) is not None:
                if adjust:
                    if pen_y >= font.height - 2:
                        pen_y = 3
                    elif pen_y == 0:
                        pen_y = font.height - 4
                result.append(TitleGlyph(character, x, -pen_y - font.height))
            x += font.char_width(character) + font.tracking
        pen_y -= font.height + font.line_gap
    return tuple(result)


def title_labels(bank: LayoutBank, title_font: AtlasFont, subtitle_font: AtlasFont,
                 title: str, subtitle: str):
    """000a70b4: zero-anchor labels with independent node positions/scales."""
    heading, subheading = bank.rectangle(48, 9), bank.rectangle(48, 10)
    title_origin = heading.x - 10, heading.height // 2 - 10
    subtitle_y = subheading.y - subheading.height // 2 - (75 if len(subtitle) < 100 else 0)
    return (TitleLabel(528, title_origin, .85, _glyphs(title_font, title, 380)),
            TitleLabel(530, (0, 480 - subtitle_y), 1.,
                       _glyphs(subtitle_font, subtitle, 320, right=True, subtitle=True)))
