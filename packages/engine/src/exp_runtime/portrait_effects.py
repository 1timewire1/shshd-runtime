"""Native expression decorations, behind the portrait and above its ring."""
from dataclasses import dataclass


@dataclass(frozen=True)
class PortraitEffect:
    frame: int
    alpha: int
    scale: float = 1.0
    rotation: float = 0.0


@dataclass
class ExpressionDecorations:
    """Native overlay and flash layers have separate, reusable animations."""
    expression: int = 0
    elapsed_ms: int = 2150
    flash_ms: int = 1300

    def change(self, expression, elapsed_ms):
        if expression in (6, 7, 8, 9):
            self.expression, self.elapsed_ms = expression, elapsed_ms
        if expression == 6:
            self.flash_ms = min(1300, elapsed_ms)

    def tick(self, elapsed_ms):
        self.elapsed_ms = min(2150, self.elapsed_ms + elapsed_ms)
        self.flash_ms = min(1300, self.flash_ms + elapsed_ms)

    def settle(self):
        self.elapsed_ms, self.flash_ms = 2150, 1300

    def poses(self, *, game, ios=False):
        return expression_effects(self.expression, self.elapsed_ms, game=game, ios=ios, flash_ms=self.flash_ms)

    def validate(self):
        if (self.expression not in (0, 6, 7, 8, 9) or not 0 <= self.elapsed_ms <= 2150
                or not 0 <= self.flash_ms <= 1300):
            raise ValueError('Invalid expression decorations')


def fraction(elapsed, duration):
    return min(1.0, max(0.0, elapsed / duration))


def pop_curve(fraction):
    """iOS CAMediaTimingFunction (.5,.2,.8,.35), SHS 00069588 / CoD 000465a6."""
    if fraction <= 0 or fraction >= 1:
        return fraction
    low, high = 0.0, 1.0
    for _ in range(24):
        t = (low + high) / 2
        x = 3 * (1-t)**2 * t * .5 + 3 * (1-t) * t*t * .8 + t**3
        if x < fraction:
            low = t
        else:
            high = t
    t = (low + high) / 2
    return 3 * (1-t)**2 * t * .2 + 3 * (1-t) * t*t * .35 + t**3


def expression_effects(expression, elapsed_ms, *, game, ios=False, flash_ms=None):
    """Time is relative to changeExpression, not the dialogue entrance.

    SHS Android 0009d918/0009d8ac/0009cdcc; SHS iOS 0006ad38/00068ee0;
    CoD 00044dc8/00045f78. iOS has a full-opacity, autoreversing flash.
    Frames are semantic common-atlas indices, resolved by the game adapter.
    """
    result = []
    native_ios = ios or game == 'cod'
    if expression in (6, 7, 8, 9) and elapsed_ms >= 650:
        rise = 500 if expression == 6 else 150
        fall = 1000 if expression == 6 and native_ios else 850
        age = elapsed_ms - 650
        alpha = fraction(age, rise) if age < rise else 1 - fraction(age - rise, fall)
        if alpha > 0:
            result.append(PortraitEffect(32 if expression == 6 else expression + 27, round(255 * alpha)))
    if flash_ms is None:
        flash_ms = elapsed_ms if expression == 6 else 1300
    if 700 <= flash_ms < 1300:
        pulse = fraction(flash_ms - 700, 600)
        if native_ios:
            scale_age = (flash_ms - 650) / 325
            scale = .7 + .4 * pop_curve(scale_age if scale_age < 1 else 2 - scale_age)
            alpha = 1
        else:
            scale = .4 + .4 * fraction(flash_ms - 650, 325)
            alpha = pulse
        if alpha > 0:
            result.append(PortraitEffect(33, round(255 * alpha), scale, 45 * pulse))
    return tuple(result)
