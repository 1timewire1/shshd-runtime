"""Shared service-88 notification motion, in native dialogue coordinates."""
from dataclasses import dataclass

from .fonts import TextStyle


NOTICE_FONT = 'PajamaHipS26'
NOTICE_STYLE = TextStyle(16, 5)


def notice_lifetime(text: str) -> int:
    # 0009c814 starts at .03 seconds and increments after every source byte,
    # including spaces. The exit callback then runs a 300 ms fade and move.
    return (len(text) + 1) * 165 + 300 if text else 0


# HD's per-letter effect, from `SHSUIDialog::startLetterEffectAnimation`
# (000421 18) with its float constants read from the binary: letter i begins
# i * 0.05 s after the first and lasts (n - 1 - i) * 0.05 + 1.55 s, so all
# letters end together at (n - 1) * 0.05 + 1.55 s. Each animates y and opacity
# as linear keyframes: for 0.2 s it rises from 3 cap heights below its place
# while fading in, holds, then for the last 0.15 s rises 3 cap heights above
# it while fading out.
HD_STEP_MS, HD_RISE_MS, HD_EXIT_MS, HD_TAIL_MS = 50, 200, 150, 1550
HD_TRAVEL_CAPS = 3


def hd_notice_lifetime(text: str) -> int:
    return (len(text) - 1) * HD_STEP_MS + HD_TAIL_MS if text else 0


# SHSUIDialog::setup (dialog_report: the startLetterEffectAnimation call) begins the letters at the time
# animatePortraitLayer returns plus 0.25 s, 0.12 s before animateTitleLayer begins: DialogueAnimation.name_delay_ms
# less 120. The engine's notice clock is restarted to cover that delay plus the effect (Session, HD builds).
HD_TITLE_LEAD_MS = 120


def hd_letter_start_ms(animation) -> int:
    return max(0, animation.name_delay_ms - HD_TITLE_LEAD_MS)


def notice_limit(text: str, animation=None) -> int:
    """The largest valid saved notice clock: Android's lifetime, or, for an HD build's dialogue `animation`, the
    letters' start plus their HD lifetime."""
    limit = notice_lifetime(text)
    if text and animation is not None:
        limit = max(limit, hd_letter_start_ms(animation) + hd_notice_lifetime(text))
    return limit


# Where `startLetterEffectAnimation` (00042118) puts the letters, in iPad points. The text is measured with the
# fill font's getDisplayLength plus 3 points between letters (the caller's spacing argument), centred over the
# portrait layer's frame (frame.x + (256 - width) / 2, kept within 0..748 - width), on a line whose top is
# frame.y - 60 - cap / 2. Each letter is its own SHSTextLayer placed by `positionLayer:boundsPadding:` at that
# origin with 20 points of padding, so its glyph box starts 20 points right of and below it (flags 7: left of
# a box as wide as the letter, top-aligned; baseline one cap height down). Photo IMG_0088 ("Strength Up", mode 1):
# predicted fill baseline 477.3 and left edge 76.5; measured 478 and 75.5.
HD_NOTICE_SPACING = 3
HD_EMPTY_LETTER = 5             # the width the letter loop gives a letter whose display length is 0 (a space)
HD_NOTICE_RAISE = 60
HD_NOTICE_PADDING = 20
HD_NOTICE_LIMITS = (0, 748)


# Cause of Death 1.4.7's `SHSUIDialog::startLetterEffectAnimation` has the same code and timings (0.05, 0.15, 0.2,
# 1.2, spacing 3, an empty letter 5) with a 30-point raise and a 300-point limit in its 320-point screen, over its
# 128-point portrait layer. Its padding is not in that function (`positionLayer:boundsPadding:`'s argument):
# COD_NOTICE_PADDING is fitted to IMG_0412.
COD_NOTICE = dict(housing=128, raise_=30, padding=10, limits=(0, 300))
HD_NOTICE = dict(housing=256, raise_=HD_NOTICE_RAISE, padding=HD_NOTICE_PADDING, limits=HD_NOTICE_LIMITS)


def hd_letter_origins(advances, frame_x, frame_y, cap, total=None, *, housing=256, raise_=HD_NOTICE_RAISE,
                      padding=HD_NOTICE_PADDING, limits=HD_NOTICE_LIMITS):
    """Top-left (points) of each letter's glyph box. `advances` are each letter's own getDisplayLength (points),
    which skips leading spaces, so a space measures 0 and adds only the spacing; `total` is the whole string's
    (spaces inside it count), which centres the text. It defaults to the sum of `advances`. The keywords are the
    build's constants (HD_NOTICE, COD_NOTICE)."""
    total = sum(advances) if total is None else total
    width = total + (len(advances) - 1) * HD_NOTICE_SPACING
    x = frame_x + (housing - width) / 2
    if x < limits[0]:
        x = limits[0]
    elif x + width > limits[1]:
        x = limits[1] - width
    top = frame_y - raise_ - cap / 2 + padding
    origins = []
    for advance in advances:
        origins.append((x + padding, top))
        x += advance + HD_NOTICE_SPACING
    return origins


def hd_letter_state(text: str, elapsed_ms: float, index: int):
    """(alpha 0..1, offset in cap heights, positive = below its place) for
    the character at `index`, or None while it is not visible."""
    local = elapsed_ms - index * HD_STEP_MS
    duration = (len(text) - 1 - index) * HD_STEP_MS + HD_TAIL_MS
    if local < 0 or local >= duration:
        return None
    if local < HD_RISE_MS:
        progress = local / HD_RISE_MS
        return progress, HD_TRAVEL_CAPS * (1 - progress)
    exit_start = duration - HD_EXIT_MS
    if local < exit_start:
        return 1.0, 0.0
    progress = (local - exit_start) / HD_EXIT_MS
    return 1 - progress, -HD_TRAVEL_CAPS * progress


@dataclass(frozen=True)
class NoticeMotion:
    text: str
    remaining_ms: int

    @property
    def elapsed_ms(self):
        return max(0, notice_lifetime(self.text) - self.remaining_ms)

    @property
    def scale(self):
        return 1.0 if len(self.text) < 19 else .88

    @property
    def exit_progress(self):
        return min(1.0, max(0.0, 1 - self.remaining_ms / 300))

    @property
    def alpha(self):
        return int(255 * (1 - self.exit_progress)) if self.remaining_ms > 0 else 0

    def glyph_rise(self, index: int):
        # Child tags count drawn letters, excluding spaces and newlines. All
        # MoveBy actions start together, with progressively longer durations.
        entry = min(1.0, self.elapsed_ms / (30 * (index + 1)))
        # The letter moves inside the scaled label; the exiting label moves
        # inside the unscaled portrait parent (0009c750).
        return 40 * self.scale * entry + 50 * self.exit_progress

    @staticmethod
    def origin(portrait_rect, mode: int):
        cx, cy = portrait_rect.center
        # 000aaa40 places the portrait at 485-y in GL coordinates. 0009c814
        # attaches the label at (-60,50) on the left, (-260,50) on the right.
        return cx + (-60 if mode == 1 else -260), cy - 5 - 50
