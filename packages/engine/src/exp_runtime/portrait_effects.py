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


# ----------------------------------------------------------------------------------------------------
# This fork's SHS HD expression effects (desktop_dialogue.DialogueRenderer's HD portrait path):
#
# HD's portrait expression change and its emotion effects.
#
# Decompiled (`SHSUIDialog::tick`, `SHSUIDialog::setCurrentSpeaker`, `SHSPortraitLayer::changeExpression:`,
# `SHSPortraitLayer::init`): a portrait first appears in the expression its character last showed (neutral, 0, for
# a speaker who was not speaking on the previous line) and, when the line's own expression differs, changes to
# it 1.0 s after the dialogue appeared. That crossfade is exp-runtime's shared model (`DialogueAnimation.expression_alphas`,
# since v0.4.2: the new art in over 0.2 s from +0.4 s, the old out over 0.8 s from +0.6 s). This module keeps HD's
# emotion effects: expressions 6 to 9 add one 0.65 s after the change, drawn between the housing (ring and disc) and
# the art:
#
# * 6 (angry): a red starburst (pack 155 frame 42, 318 x 316 px, one pixel per point) that shows for 0.6 s from 0.05 s
#   after the effect starts, rotating 0 -> 45 degrees linearly and scaling 0.7 -> 1.1 -> 0.7 (0.325 s each way, timing
#   bezier (.5, .2, .8, .35)), plus a red ball (frame 41, 105 px drawn at 2x = the disc's size) fading in over 0.5 s
#   and out over 1.0 s;
# * 7 / 8 / 9: only the ball, yellow / blue / white (frames 43 / 44 / 45), fading in over 0.15 s and out over 0.85 s.
#
# The direction of the starburst's rotation is assumed clockwise (the layer's coordinate flip is not decoded).

EXPRESSION_CHANGE_MS = 1000        # SHSUIDialog::tick's counter
EFFECT_DELAY_MS = 650
BALL_FRAMES = {6: 41, 7: 43, 8: 44, 9: 45}
STARBURST_FRAME = 42
BALL_UNITS = 105                   # 105 px drawn at 2x, in layout units (2 px each)
ROTATION_DEGREES = 45


def _bezier(t, x1, y1, x2, y2):
    def component(u, a, b):
        return 3 * (1 - u) ** 2 * u * a + 3 * (1 - u) * u ** 2 * b + u ** 3
    lo, hi = 0., 1.
    for _ in range(30):
        mid = (lo + hi) / 2
        if component(mid, x1, x2) < t:
            lo = mid
        else:
            hi = mid
    return component((lo + hi) / 2, y1, y2)


def starburst(age_ms):
    """(scale, degrees) of the angry starburst, or None while it is not showing."""
    t = age_ms - EXPRESSION_CHANGE_MS - EFFECT_DELAY_MS
    if not 50 <= t < 650:
        return None
    phase = t / 325
    unit = phase if phase < 1 else 2 - phase
    return .7 + .4 * _bezier(min(1., max(0., unit)), .5, .2, .8, .35), ROTATION_DEGREES * (t - 50) / 600


def ball_alpha(expression, age_ms):
    """Opacity of the emotion ball for `expression` (0 when it has none or is not showing)."""
    if expression not in BALL_FRAMES:
        return 0.
    t = age_ms - EXPRESSION_CHANGE_MS - EFFECT_DELAY_MS
    fade_in, fade_out = (500, 1000) if expression == 6 else (150, 850)
    if t < 0 or t >= fade_in + fade_out:
        return 0.
    return t / fade_in if t < fade_in else 1 - (t - fade_in) / fade_out


