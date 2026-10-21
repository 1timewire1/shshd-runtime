"""Drawing the iOS games' scene transitions: SHSFadeLayer's 16 blinds and its black layer.

The queued transition itself (service 16 -> finishUI -> fade-out, callback, reveal) is the session's
(fade_transition.FadeTransition). This module keeps the timing the player also uses for its own fade from black (a
Decision Tree warp, `fadeToGame`): every animation is a linear three-key `CAKeyframeAnimation` with keyTimes
(0, .8, 1) over 1.5 s:
* out: blind width (or black opacity) runs 0 -> full by 1.2 s and holds;
* in: full -> 0 over the first 1.2 s and holds at 0; blinds wait 0.3 s before starting, the fade to black
  holds opaque for 1.2 s and fades over the last 0.3 s.
Photo `dialouge/IMG_0188` catches vertical blinds mid-way.
"""

DURATION_MS = 1500
KEY_MS = 1200
BLIND_DELAY_MS = 300
BLINDS = 16


def out_ms(kind):
    return DURATION_MS


def in_ms(kind):
    return DURATION_MS + (BLIND_DELAY_MS if kind in (1, 2) else 0)


def coverage(kind, phase, ms):
    """How much of the frame is black, 0..1 (a blind's closed fraction, or the black layer's opacity)."""
    if phase == 'out':
        return min(1., max(0., ms / KEY_MS))
    if kind in (1, 2):
        return 1. - min(1., max(0., (ms - BLIND_DELAY_MS) / KEY_MS))
    return 1. - min(1., max(0., (ms - KEY_MS) / (DURATION_MS - KEY_MS)))


def blind_rects(kind, fraction, size):
    """Black rectangles (x, y, w, h) inside a frame of `size` for a blind transition `fraction` closed."""
    width, height = size
    rects = []
    for index in range(BLINDS):
        if kind == 2:                                   # vertical blinds: strips side by side
            strip = width / BLINDS
            rects.append((round(index * strip), 0, max(0, round(strip * fraction)), height))
        else:
            strip = height / BLINDS
            rects.append((0, round(index * strip), width, max(0, round(strip * fraction))))
    return [rect for rect in rects if rect[2] > 0 and rect[3] > 0]
