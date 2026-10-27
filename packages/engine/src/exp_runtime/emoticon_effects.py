"""shshd-runtime: emoticons over a translated speaker's portrait (the cancelled Xbox 360 prototype's line effects).

The X360 scripts put an "emoticon" over a character's head before some lines (`scene.kim.CreateFx("hud/emoticon/
love")`): a particle burst drawing one cell of its 4x4 sheet `art/hud/emoticons.png`. Its translations
(tools/translate x360.py) carry the six cells as episode images and set a global number around such a line; the game
profile's TRANSLATED_PORTRAIT_EFFECTS names that number and the images (Session.portrait_effect). This module is the
animation, pure and headless: `sprites(effect, t)` places the effect's pieces at t ms after it starts, in layout units
from its anchor at the portrait ring's upper corner (the side facing the box). The original's particles aren't
reproduced; each effect has its own entrance and then a quiet loop for as long as the line is up.
"""
from dataclasses import dataclass
from math import cos, exp, pi, sin

# Effect numbers (the global number's values) and the sheet cell each draws, in sheet order.
LIGHTNING, SWEAT, ANGER, HEART, EXCLAMATION, QUESTION = range(1, 7)
EFFECTS = {LIGHTNING: 'lightning', SWEAT: 'sweat', ANGER: 'anger', HEART: 'heart', EXCLAMATION: 'exclamation',
           QUESTION: 'question'}
# The X360 effect names (fx.wxr hud/emoticon/*) -> effect number; "dust" (a smoke puff on arrival) has none.
X360_EFFECTS = {'angry': LIGHTNING, 'angry_female': LIGHTNING, 'sweat': SWEAT, 'stress': ANGER,
                'stress_female': ANGER, 'love': HEART, 'exclamation': EXCLAMATION,
                'exclamation_female': EXCLAMATION, 'questionmark': QUESTION, 'questionmark_female': QUESTION}
SIZE = 40                       # an icon's side in layout units (the 320 x 480 column) at scale 1


@dataclass(frozen=True)
class Sprite:
    effect: int                 # which cell
    x: float                    # offset from the anchor, layout units (x toward the box, y down)
    y: float
    scale: float = 1.0          # of SIZE
    rotation: float = 0.0       # degrees, clockwise
    alpha: float = 1.0


def _pop(t, duration=240, overshoot=1.25):
    """0 -> overshoot -> 1 over `duration` ms (a quick ease-out past 1, then settling)."""
    if t <= 0:
        return 0.0
    if t >= duration:
        return 1.0
    u = t / duration
    if u < .6:
        return overshoot * sin(u / .6 * pi / 2)
    return overshoot + (1 - overshoot) * sin((u - .6) / .4 * pi / 2)


def _spring(t, duration=520):
    """A damped spring from 0 to 1: one overshoot, a small rebound, settled by `duration`."""
    if t <= 0:
        return 0.0
    if t >= duration:
        return 1.0
    u = t / duration
    return 1 - exp(-6 * u) * cos(3 * pi * u)


def _lightning(t):
    # Two bolts pop in 90 ms apart, jitter hard for ~0.8 s, then flicker.
    out = []
    for i, (x, y) in enumerate(((0, 0), (11, 7))):
        local = t - 90 * i
        if local <= 0:
            continue
        scale = _pop(local, 220, 1.3) * (0.85 if i else 1.0)
        shake = max(0.0, 1 - local / 800)
        jx = 2.2 * shake * sin(local / 23 + i)
        jy = 1.6 * shake * cos(local / 31 + 2 * i)
        rot = -12 + 9 * shake * sin(local / 41 + i) + (8 if i else 0)
        alpha = 1.0 if local < 900 else 0.8 + 0.2 * (0.5 + 0.5 * cos((local - 900) / 140))
        out.append(Sprite(LIGHTNING, x + jx, y + jy, scale, rot, alpha))
    return out


def _sweat(t):
    # Pops in at the brow, slides down a little, then bobs.
    scale = _pop(t, 200, 1.15)
    slide = 10 * min(1.0, max(0.0, (t - 200) / 700)) ** .6
    bob = 1.0 * sin((t - 900) / 255) if t > 900 else 0.0
    return [Sprite(SWEAT, 2, -4 + slide + bob, 0.8 * scale, 8)] if t > 0 else []


def _anger(t):
    # Pops in, then pulses like a throbbing vein.
    scale = _pop(t, 220, 1.3)
    if t > 220:
        scale *= 1 + 0.12 * (0.5 - 0.5 * cos((t - 220) / 700 * 2 * pi))
    return [Sprite(ANGER, 0, 0, scale, 0)] if t > 0 else []


HEART_LIFE = 1600
HEART_BURST = (0, 300, 600, 900)        # the first four, then one every HEART_EVERY ms
HEART_EVERY = 900


def _heart(start, local, i):
    u = local / HEART_LIFE
    rise = 34 * (1 - (1 - u) ** 2)
    sway = 4 * sin(local / 260 + i * 1.7)
    side = (-7, 6, -2, 9)[i % 4]
    alpha = 1.0 if u < .6 else max(0.0, 1 - (u - .6) / .4)
    return Sprite(HEART, side + sway, 6 - rise, 0.45 + 0.25 * min(1.0, u * 3), sway * 2, alpha)


def _hearts(t):
    starts = [s for s in HEART_BURST]
    n = int(max(0, t - HEART_BURST[-1]) // HEART_EVERY)
    starts += [HEART_BURST[-1] + HEART_EVERY * k for k in range(1, n + 2)]
    return [_heart(s, t - s, i) for i, s in enumerate(starts) if 0 < t - s < HEART_LIFE]


def _exclamation(t):
    # Springs up from below with a bounce, wobbles, then bobs.
    lift = _spring(t)
    scale = 0.6 + 0.4 * min(1.0, t / 160)
    wobble = 7 * exp(-t / 380) * sin(t / 45)
    bob = 1.0 * sin((t - 600) / 220) if t > 600 else 0.0
    return [Sprite(EXCLAMATION, 0, 9 * (1 - lift) + bob, scale, wobble)] if t > 0 else []


def _question(t):
    # Pops in, then rocks slowly side to side.
    scale = _pop(t, 240, 1.15)
    rock = 11 * sin((t - 240) / 1600 * 2 * pi) if t > 240 else 0.0
    return [Sprite(QUESTION, 0, 0, scale, rock)] if t > 0 else []


ANIMATIONS = {LIGHTNING: _lightning, SWEAT: _sweat, ANGER: _anger, HEART: _hearts, EXCLAMATION: _exclamation,
              QUESTION: _question}


def sprites(effect, t):
    """The effect's pieces t ms after it started (none before); an unknown effect draws nothing."""
    animate = ANIMATIONS.get(effect)
    return animate(t) if animate is not None and t > 0 else []


def start_ms(motion):
    """When the effect starts on a line, in DialogueAnimation.age_ms: once a new speaker's portrait has come in (as
    the relationship icons wait for it), at once for the same speaker."""
    if motion.changed and motion.portrait is not None:
        from .dialogue_animation import PORTRAIT_MS
        return motion.portrait_delay_ms + PORTRAIT_MS
    return 0
