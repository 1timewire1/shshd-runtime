"""Scrolling that coasts on after a drag (UIScrollView's deceleration), for touch screens.

HD's scroll views (the episode picker's rows and columns, the Faceplace wall, the story tree) glide on when the
finger lifts and slow to a stop. A `Fling` follows a drag's scroll positions, takes the speed of the last moments
when the finger lifts, and then hands out the positions to show frame by frame. It stops at an edge (the owner's
clamp moved the value), when another drag catches it, or when it has slowed to nothing.

Off by default: a mouse drag on desktop stops where it ends; touch hosts turn it on (platforms/android.py).
"""
import math

import pygame

ENABLED = False
RATE = 0.998            # UIScrollViewDecelerationRateNormal: the speed kept each millisecond
WINDOW_MS = 120         # the drag samples this recent set the speed at release
RESTED_MS = 80          # a finger held still this long before lifting releases without coasting
REST_SPEED = 0.01       # points a millisecond: below this it has stopped
TOP_SPEED = 8.0         # points a millisecond: a jittery last sample never throws a list away


def _now():
    return pygame.time.get_ticks()


class Fling:
    def __init__(self):
        self.samples = []           # [(ms, values)] while dragging
        self.velocity = None        # points a millisecond for each value while coasting
        self.left = None            # the values the last step set, to notice a clamp or another hand moving them
        self.time = None

    @property
    def moving(self):
        return self.velocity is not None

    def stop(self):
        """Catch it (a new touch) or drop it; True if it was coasting."""
        was = self.velocity is not None
        self.samples, self.velocity, self.left = [], None, None
        return was

    def track(self, *values, now=None):
        now = _now() if now is None else now
        self.velocity = None
        self.samples.append((now, values))
        while len(self.samples) > 2 and now - self.samples[1][0] > WINDOW_MS:
            del self.samples[0]

    def release(self, now=None):
        """The finger lifted: coast at the drag's latest speed (if enabled and it was still moving)."""
        now = _now() if now is None else now
        samples, self.samples = self.samples, []
        recent = [sample for sample in samples if now - sample[0] <= WINDOW_MS]
        if not ENABLED or len(recent) < 2 or now - recent[-1][0] > RESTED_MS:
            return
        (start, first), (end, last) = recent[0], recent[-1]
        if end - start < 8:
            return
        velocity = tuple(max(-TOP_SPEED, min(TOP_SPEED, (b - a) / (end - start))) for a, b in zip(first, last))
        if max(abs(v) for v in velocity) >= REST_SPEED:
            self.velocity, self.left, self.time = velocity, last, now

    def step(self, *values, now=None):
        """The values to show now, or None when not coasting. `values` are the current ones: if something else
        changed them since the last step (the scroll reached an edge and was clamped, or the view moved itself),
        the glide ends there."""
        if self.velocity is None:
            return None
        if any(abs(a - b) > 1e-6 for a, b in zip(values, self.left)):
            self.stop()
            return None
        now = _now() if now is None else now
        elapsed, self.time = max(0, now - self.time), now
        decay = RATE ** elapsed
        travelled = (decay - 1) / math.log(RATE)            # the integral of RATE ** t over the elapsed time
        self.left = tuple(value + v * travelled for value, v in zip(values, self.velocity))
        self.velocity = tuple(v * decay for v in self.velocity)
        if max(abs(v) for v in self.velocity) < REST_SPEED:
            self.velocity = None
        return self.left

    def settled(self, *values):
        """After the owner clamps the values a step set: remember them, so a step that hit an edge stops next time."""
        if self.velocity is not None:
            if any(abs(a - b) > 1e-6 for a, b in zip(values, self.left)):
                self.stop()
