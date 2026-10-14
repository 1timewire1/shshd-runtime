"""Shared service-88 notification motion, in native dialogue coordinates."""
from dataclasses import dataclass

from .fonts import TextStyle


NOTICE_FONT = 'PajamaHipS26'
NOTICE_STYLE = TextStyle(16, 5)


def notice_lifetime(text: str) -> int:
    # 0009c814 starts at .03 seconds and increments after every source byte,
    # including spaces. The exit callback then runs a 300 ms fade and move.
    return (len(text) + 1) * 165 + 300 if text else 0


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
