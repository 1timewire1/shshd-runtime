"""Tune the X360 Diss Battle's grade thresholds (exp_runtime.x360_battle.GRADE_THRESHOLDS) by simulation.

The battle's tiers multiply points, so New Rules' own grade (8 x score / seconds) would rise with them. The owner's rule
(2026-11-16): beating Spike's 7 should take the same skill as in New Rules. So a bot plays the battle at a ladder of skill
levels twice, once with New Rules' scoring (tiers off) and once with ours, and each grade's threshold is our mean score at
the skill whose mean New Rules score just earns that grade.

The bot plays the real model at 60 frames a second. It knows where a press catches a word (the catch window, measured
once from the model itself), and at its skill level:
- reads a new round's words for READ_MS before it can find the rhyme;
- takes a pass of the rhyme under the arm with probability HIT (else lets it go round again);
- presses on a wrong word as it passes with probability ERR (a misread), at most once a pass.

    python tools/translate/x360_battle_tune.py [GAMES_PER_LEVEL]        (prints the thresholds and a table)
"""
import math
import sys
from pathlib import Path

for part in ('formats', 'engine'):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'packages' / part / 'src'))
from exp_runtime import x360_battle as xb     # noqa: E402
from exp_runtime.randomness import Random48  # noqa: E402

ROUNDS = [['rude', 'lewd', 'crook', 'socks', 'store'], ['crash', 'trash', 'chatter', 'ride', 'rat'],
          ['cradle', 'ladle', 'crime', 'tool', 'door'], ['ran', 'tan', 'fun', 'sing', 'lend'],
          ['lily', 'chilly', 'membrane', 'store', 'guy'], ['guy', 'thigh', 'shorty', 'door', 'ran']]
FRAME_MS = 50 / 3


def running(tiers):
    game = xb.DissBattle.opened(ROUNDS, tutorial=False)
    game.tiers = tiers
    random = Random48()
    game.start()
    game.tick(xb.OPENING_MS + xb.COUNTDOWN_MS + 40, random)
    game.block_ms = 0
    return game, random


def catch_windows():
    """For each place, the record angles (whole degrees) at which a press, the record turning at its speed, catches the
    word there: measured from the model itself."""
    windows = []
    for place in range(xb.WORDS):
        caught = set()
        for start in range(360):
            game, random = running(True)
            for slot in game.slots:
                slot.update(word=xb.NO_WORD, shown=xb.NO_WORD)
            game.slots[place].update(word=1, shown=1)
            game.angle = start
            game.press()
            for _ in range(30):
                game.tick(FRAME_MS, random)
                if game.wrong:
                    caught.add(start)
                    break
        windows.append(caught)
    return windows


def middle(window):
    """The middle angle of a window of whole degrees, which may wrap past 0."""
    ordered = sorted(window)
    start = next(a for a in ordered if (a - 1) % 360 not in window)
    return (start + len(window) // 2) % 360


def play(skill, tiers, seed, windows):
    """One game by a bot of `skill` (0-1); its score and right/wrong counts."""
    import random as py_random
    rng = py_random.Random(seed)
    read_ms = 2600 - 2000 * skill
    hit, err = 0.35 + 0.65 * skill, 0.25 * (1 - skill)
    game, random = running(tiers)
    random.state ^= seed
    dealt_at, decided = game.now_ms, set()
    last_round = game.round
    centres = [middle(window) for window in windows]
    while game.phase == xb.RUNNING:
        if game.round != last_round or game.redeal_ms > 0:
            dealt_at, decided, last_round = game.now_ms, set(), game.round
        aim = round(game.angle) % 360
        for k, slot in enumerate(game.slots):
            if slot['word'] == xb.NO_WORD or game.arm_ms >= 0 or game.redeal_ms > 0:
                continue
            here = (aim - centres[k] + 180) % 360 - 180 in range(-2, 3)     # near the middle of the catch window
            key = (k, int(game.now_ms // (360 / game.velocity * 1000)))
            if not here or key in decided:
                continue
            decided.add(key)
            ready = game.now_ms - dealt_at >= read_ms
            if slot['word'] == 0 and ready and rng.random() < hit:
                game.press()
            elif slot['word'] != 0 and rng.random() < err:
                game.press()
        game.tick(FRAME_MS, random)
    return game.score, game.right, game.wrong


def main(games=40):
    windows = catch_windows()
    print('catch windows (degrees)', [(min(w), max(w), len(w)) if w else None for w in windows])
    ladder = [i / 20 for i in range(21)]
    rows = []
    for skill in ladder:
        nr = [play(skill, False, s, windows) for s in range(games)]
        ours = [play(skill, True, s, windows) for s in range(games)]
        nr_mean = sum(r[0] for r in nr) / games
        our_mean = sum(r[0] for r in ours) / games
        rights = sum(r[1] for r in nr) / games
        rows.append((skill, nr_mean, our_mean, rights))
        print(f'skill {skill:.2f}: NR score {nr_mean:5.1f} (grade {xb.nr_grade(round(nr_mean))}, {rights:4.1f} right), '
              f'ours {our_mean:6.1f}')
    thresholds = []
    for g in range(1, 11):
        need = g * xb.SECONDS * xb.NR_GRADE[1] / xb.NR_GRADE[0]     # the New Rules score that earns grade g
        for (s0, n0, o0, _), (s1, n1, o1, _) in zip(rows, rows[1:]):
            if n0 <= need <= n1 and n1 > n0:
                t = (need - n0) / (n1 - n0)
                thresholds.append(math.ceil(o0 + t * (o1 - o0)))
                break
        else:
            # beyond the ladder: carry on at the top's ratio of our score to New Rules'
            top = rows[-1]
            thresholds.append(math.ceil(need * top[2] / max(1, top[1])))
    for i in range(1, len(thresholds)):        # strictly rising
        thresholds[i] = max(thresholds[i], thresholds[i - 1] + 1)
    print('GRADE_THRESHOLDS =', tuple(thresholds))
    return tuple(thresholds)


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 40)
