"""HD's portrait expression change and its emotion effects.

Decompiled (`SHSUIDialog::tick`, `SHSUIDialog::setCurrentSpeaker`, `SHSPortraitLayer::changeExpression:`,
`SHSPortraitLayer::init`): a portrait first appears in the expression its character last showed (neutral, 0, for
a speaker who was not speaking on the previous line) and, when the line's own expression differs, changes to
it 1.0 s after the dialogue appeared. That crossfade is exp-runtime's shared model (`DialogueAnimation.expression_alphas`,
since v0.4.2: the new art in over 0.2 s from +0.4 s, the old out over 0.8 s from +0.6 s). This module keeps HD's
emotion effects: expressions 6 to 9 add one 0.65 s after the change, drawn between the housing (ring and disc) and
the art:

* 6 (angry): a red starburst (pack 155 frame 42, 318 x 316 px, one pixel per point) that shows for 0.6 s from 0.05 s
  after the effect starts, rotating 0 -> 45 degrees linearly and scaling 0.7 -> 1.1 -> 0.7 (0.325 s each way, timing
  bezier (.5, .2, .8, .35)), plus a red ball (frame 41, 105 px drawn at 2x = the disc's size) fading in over 0.5 s
  and out over 1.0 s;
* 7 / 8 / 9: only the ball, yellow / blue / white (frames 43 / 44 / 45), fading in over 0.15 s and out over 0.85 s.

The direction of the starburst's rotation is assumed clockwise (the layer's coordinate flip is not decoded).
"""

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


