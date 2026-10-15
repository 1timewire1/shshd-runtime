"""The scene transition between story elements: blinds or a fade to black.

Decompiled (`SHSFadeLayer`, `GameModel::restartFade` / `tickFade` / `setupQueuedFade`, `SHSUIElement::finishUI`):
script service 16 queues a transition type; when the element on screen finishes (a tap on a dialogue), the fade-out
runs over the frame, the script then advances behind it, and the fade-in reveals the next element. Input is off
throughout. Type 1 is 16 horizontal blinds, 2 is 16 vertical blinds, 6 a fade to black, 20 a random 1 or 2.
Every animation is a linear three-key `CAKeyframeAnimation` with keyTimes (0, .8, 1) over 1.5 s:
* out: blind width (or black opacity) runs 0 -> full by 1.2 s and holds;
* in: full -> 0 over the first 1.2 s and holds at 0; blinds wait 0.3 s before starting, the fade to black
  holds opaque for 1.2 s and fades over the last 0.3 s.
Photo `dialouge/IMG_0188` catches vertical blinds mid-way. The layer's own 7 s watchdog is not modelled.
"""

DURATION_MS = 1500
KEY_MS = 1200
BLIND_DELAY_MS = 300
BLINDS = 16
KINDS = (1, 2, 6)


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


def resolve(scene_value, draw):
    """The transition a queued `scene_value` runs: 20 picks a blind by one random draw; unknown types run none."""
    if scene_value == 20:
        return 1 + (draw & 1)
    return scene_value if scene_value in KINDS else 0
