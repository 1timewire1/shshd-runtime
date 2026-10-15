"""HD's location layer pans sideways with the speaker.

Decompiled (`GameModel::alignLocation`, `SHSUIDialog::animateLocationLayer`, `GameModel::setLocationPan`,
`GameModel::loadScript09NoGUI`): a location image is wider than the 768 point frame (Football Star's are
960 x 1440, one pixel per point) and sits in a layer whose position x is `w/2` (align 1: left edge flush),
384 (align 2: centered) or `768 - w/2` (align 3: right edge flush), y always 384. Each dialogue with a
portrait on the left (speaker type 1) aligns the layer left, one on the right (type 2) aligns it right;
narration leaves it where it was. Photos of the same field with a right-hand and a left-hand speaker differ by
exactly 192 points, 960 - 768. The move is a Core Animation implicit position change; its curve and duration
(0.25 s, the default timing function) are assumed, not decompiled.
"""

FRAME_WIDTH = 768
DURATION_S = .25


def center_x(align, width):
    """The layer's x position, in points, for an alignment and the image's width in points."""
    if align == 3:
        return FRAME_WIDTH - width / 2
    if align == 2:
        return FRAME_WIDTH / 2
    return width / 2


def default_ease(t):
    """kCAMediaTimingFunctionDefault, the bezier (.25, .1, .25, 1), by bisection."""
    def bez(u, a, b):
        return 3 * (1 - u) ** 2 * u * a + 3 * (1 - u) * u ** 2 * b + u ** 3
    lo, hi = 0., 1.
    for _ in range(30):
        mid = (lo + hi) / 2
        if bez(mid, .25, .25) < t:
            lo = mid
        else:
            hi = mid
    return bez((lo + hi) / 2, .1, 1.)


class LocationPan:
    """Animates the layer between alignments; `x(align, width, now_ms)` is the current center x."""

    def __init__(self):
        self.target = self.start = None
        self.origin = self.since = 0.

    def x(self, align, width, now_ms):
        goal = center_x(align, width)
        if self.target is None:
            self.target = self.start = goal
        elif goal != self.target:
            self.origin, self.since, self.target = self.current(now_ms), now_ms, goal
            self.start = self.origin
        return self.current(now_ms)

    def current(self, now_ms):
        if self.target is None:
            return 0.
        t = (now_ms - self.since) / 1000 / DURATION_S
        if t >= 1 or self.start == self.target:
            return self.target
        return self.start + (self.target - self.start) * default_ease(max(0., t))
