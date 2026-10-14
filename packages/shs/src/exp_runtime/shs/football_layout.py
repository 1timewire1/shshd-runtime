"""Service-94 presentation in the original 320 x 480 coordinates.

Pure layout: these helpers never advance gameplay or consume randomness.
Native routines and the remaining fidelity boundaries: docs/FOOTBALL_UI.md.
"""
from dataclasses import dataclass
import math

from ..fonts import TextStyle


FONT = 'ArialMT14'
LABEL_STYLE = TextStyle(14, 8)
HELP_STYLE = TextStyle(14, 4, markers=(('`', (24, 92, 219)), (';', (255, 51, 0))))
TITLE_STYLE = TextStyle(14, 4)


def clamp(value):
    return min(1., max(0., value))


def heading_id(game):
    return (72 if game.defense else 71) if game.half == 3 else 176 + game.half - 1 + 2 * game.defense


def team_name(strings, selector):
    return strings[166 + selector] if 1 <= selector <= 9 else ''


def score_strip(home_width, away_width):
    """SHS iOS 00088a60: select the authored strip from measured team names."""
    width = home_width + away_width + 82
    return (-40, 51) if width < 92 else (-39, 62) if width < 114 else (-38, 73)


def feedback_text(game, strings, index):
    if not game.message_ids:
        # Pre-v8 saves retain the text they actually recorded for this play.
        return game.message
    message, value = game.message_ids[index], game.message_values[index]
    home = f'{team_name(strings, game.teams[0])}: {game.home}'
    away = f'{team_name(strings, game.teams[1])}: {game.away}'
    if message < 0:
        return {-100: home, -101: away, -102: home + '\n' + away}[message]
    return strings[message].replace('%d', str(value)) if value != 1000 else strings[message]


def legend_codes(game):
    # 000be110 scans the supplied plan in order, including zero-weight rows.
    return tuple(p.code for p in game.plans[game.plan_index] if p.code not in (-6, -5, 5, 6, 7))


def footer_id(game):
    if game.phase in (20, 21, 22, 23, 25):
        return 75 if game.phase_elapsed_ms > (3500 if game.first_help else 900) else None
    return 74 if game.defense else 73


@dataclass(frozen=True)
class HelpMotion:
    x: float
    y: float
    scale: float
    alpha: float
    coach_x: float
    coach_alpha: float


def help_motion(game, coach_width):
    """000be110: 800ms panel entry/exit and the coach's 700+100ms slide."""
    coach_x = 320 - coach_width
    if game.phase == 25:
        remaining = clamp(game.phase_ms / 800)
        keep_coach = game.half == 1 and not game.extra_help and bool(game.extra_instructions[int(game.defense)])
        return HelpMotion(7., 126., 1., remaining if remaining > .4 else 0.,
                          coach_x if keep_coach else coach_x + coach_width * (1 - remaining),
                          1. if keep_coach else .5 + .5 * remaining)
    if game.phase_elapsed_ms >= 800:
        return HelpMotion(7., 126., 1., 1., float(coach_x), 1.)
    elapsed = game.phase_elapsed_ms
    scale = elapsed / 800 * 1.1
    if scale > 1.05:
        scale = 1.1 - (scale - 1.05)
    if not game.extra_help:
        coach_x += -5 + (coach_width * (1 - elapsed / 700) if elapsed < 700 else (elapsed - 700) / 20)
    return HelpMotion(7 + (1 - scale) * 313, 126 + (1 - scale) * 314,
                      scale, clamp(scale), float(coach_x),
                      1. if game.extra_help else .5 + .5 * elapsed / 800)


@dataclass(frozen=True)
class CountdownMotion:
    frame: int
    scale: float
    alpha: float
    angle: float = 0.


def countdown_motion(remaining_ms):
    """000b4050: 3, 2, 1, Go; four 600ms slots, pivot at screen center."""
    slot = min(3, max(0, remaining_ms // 600))
    r = clamp((remaining_ms - slot * 600) / 600)
    if slot:
        t = max(0., 2 * (r - .5))
        return CountdownMotion(slot + 1, 1 + t, 1 - t)
    scale, alpha, angle = 1., 1., 0.
    if r >= .7:
        t = (r - .7) / .3
        scale, alpha = (1 - t) * 1.1, 1 - t
    elif r < .4:
        scale = alpha = r / .4
        angle = (1 - scale) * 180
    return CountdownMotion(5, scale / 1.3, alpha / 1.8, angle)


@dataclass(frozen=True)
class FeedbackMotion:
    index: int
    x: float = -24.
    scale: float = 1.
    angle: float = 0.
    visible: bool = True
    shine_x: float | None = None


def feedback_motion(game):
    """000bba50: swipe backdrop, spinning text, shine, and message gates."""
    phase = game.message_phase
    if phase == -1:
        return None
    if phase in (0, 11):
        r = clamp(game.message_ms / 800)
        return (FeedbackMotion(0, -24 - 399 * r, 1 - r, r * 180, r < 1)
                if phase == 0 else
                FeedbackMotion(game.message_lines - 1, -24 + 359 * (1 - r), r, (1 - r) * 180, r > 0))
    index = 0 if phase in (1, 2, 3) else 1 if phase in (4, 5, 6, 7) else 2
    visible = game.message_ms > 0 if phase in (3, 7) else game.message_ms < 100 if phase in (4, 8) else True
    shine = -30 + 380 * (1 - clamp(game.message_ms / 300)) if phase in (1, 6, 10) else None
    return FeedbackMotion(index, visible=visible, shine_x=shine)


def target_position(target, center):
    """000c12a8: native node top-left; bitmap dimensions supply its pivot."""
    x, y = center
    bob = math.sin(target.elapsed_ms / target.hold_ms * 3.1415926) * 3.5 if target.phase in (3, 6) else 0.
    return x - 35, int(y - int(target.scale * 18)) + bob - 35


def yard_glyphs(yards, x, baseline):
    """000b3a60: slanted two-digit yardage and the matching 'yds' suffix."""
    widths = (14, 13, 15, 14, 14, 14, 14, 14, 14, 14)
    heights = (19, 19, 20, 19, 19, 19, 19, 20, 19, 20)
    # Authored extensions can exceed the native two-digit table. Draw all
    # digits safely with the same metrics, without altering the play's value.
    digits = [int(c) for c in str(abs(yards))]
    x -= (sum(widths[d] for d in digits) + 24) / 2
    base = -22 if yards >= 0 else -6
    result = []
    for digit in digits:
        result.append((base - digit, x, baseline - heights[digit]))
        x += widths[digit]
        baseline += widths[digit] * .1
    result.append((-33 if yards >= 0 else -17, x, baseline - 12))
    return tuple(result)
