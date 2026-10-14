"""Service-96 screen geometry recovered from Android 1.0.9.

Coordinates use the original 320 x 480 screen. These functions are pure:
rendering and hit testing cannot advance the game or its random stream.
"""
from dataclasses import dataclass


def clamp(value):
    return min(1., max(0., value))


def ease(value, low=0., high=1., bounce=None):
    """000c29a8: smoothstep, or the native triangular overshoot curve."""
    if value < low:
        return 0.
    if value > high:
        return 1.
    value = (value - low) / (high - low)
    if bounce is None:
        return value * value * (3 - 2 * value)
    if value - bounce > (1 - bounce) / 2:
        return (bounce + 1 - value) / bounce
    return value / bounce


@dataclass(frozen=True)
class TutorialBox:
    x: float
    top: float
    body_y: float
    body_height: float
    scale: float

    @property
    def bottom(self):
        return self.body_y + (self.body_height + 15) * self.scale


def tutorial_box(text_height, position, scale=1.):
    """000c5da0: 306px cap/body/foot, 286px text column, 10px padding."""
    body = text_height + 20
    center = body / 2 + 30 if position == 0 else 480 - (body / 2 + 30) if position == 2 else 240
    top = center - (body + 23 + 15) * scale / 2
    return TutorialBox(160 - 153 * scale, top, top + 23 * scale - 1, body, scale)


def heading_lines(game, problem=None):
    """000c39c0/000cda28: staggered, sliding lines next to the left NPC."""
    if game.phase in (-2, -1, 6):
        return ()
    alpha = max(0., game.phase_ms / 800 - .2) if game.phase == 4 else 1.
    lines = (problem or game.problem).heading.split('\n')[:3]
    positions = ((110, 60), (104, 80), (95, 100))
    result = []
    for index, (line, (x, y)) in enumerate(zip(lines, positions)):
        if game.phase in (0, 2):
            progress = 1 - game.phase_ms / (2800 if game.phase == 0 else 1800)
            limit, delay = (.4, .05) if game.phase == 0 else (.9, .1)
            x += int((1 - ease(progress + (2 - index) * delay, 0, limit, .85)) * 352)
        result.append((line, x, y, alpha))
    return tuple(result)


def prompt_position(progress, index, width, line_count, font_height=52):
    """000c5400/000c8598/000c8790: center reveal, then bottom-left list."""
    x = int(15 + index * 23 + width * .65 / 2)
    y = (480 - line_count * font_height) / 2 + index * font_height
    bottom = 377 + index * 25
    if .2 <= progress <= .5:
        t = ease(progress, .2, .5, .9)
        return 260 - t * 100, 420 + (y - 420) * t, max(.1, t)
    if .5 <= progress <= .74:
        return 160., y, 1.
    if .74 <= progress <= .89:
        t = ease(progress, .74, .89, .9)
        return 160 + (x - 160) * t, y + (bottom - y) * t, 1 - .65 * t
    return x, bottom, .65
