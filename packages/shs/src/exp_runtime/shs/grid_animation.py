"""Saved word-cube clocks from Android 000c1d88 / SHS iOS 00096e14."""
from dataclasses import dataclass
import math
import struct

from .grid_layout import ease


@dataclass
class GridTile:
    flipping: bool = False
    flip_ms: int = 0
    flip_delay: int = 0
    growing: bool = False
    shrinking: bool = False
    grow_ms: int = 0
    grow_delay: int = 0
    glinting: bool = False
    glint_ms: int = 0
    glint_delay: int = 0

    def flip(self, delay):
        self.flipping, self.flip_ms, self.flip_delay = True, 700, max(1, delay)

    def grow(self, delay, *, shrinking=False):
        self.growing, self.shrinking = True, shrinking
        self.grow_ms, self.grow_delay = 600, max(1, delay) if shrinking else delay

    def shine(self, delay):
        self.glinting, self.glint_ms, self.glint_delay = True, 600, delay

    def tick(self, dt):
        # The native clocks spend the full frame while a delay remains
        # positive, but only its overshoot when crossing zero. Drawing stays
        # at the starting pose until the delay expires; this is not equivalent
        # to subtracting the delay from total elapsed time.
        if self.flipping:
            step = dt
            if self.flip_delay > 0:
                self.flip_delay -= dt
                if self.flip_delay < 0:
                    step = -self.flip_delay
            self.flip_ms -= step
            if self.flip_ms <= 0:
                self.flipping = False
        if self.growing:
            step = dt
            if self.grow_delay > 0:
                self.grow_delay -= dt
                if self.grow_delay < 0:
                    step = -self.grow_delay
            self.grow_ms -= step
            if self.grow_ms < 0 and not self.shrinking:
                self.growing = False
        if self.glinting:
            step = dt
            if self.glint_delay > 0:
                self.glint_delay -= dt
                if self.glint_delay < 0:
                    # Both supplied binaries read the growth delay here.
                    step = -self.grow_delay
            if step > 0:
                self.glint_ms -= step
                if self.glint_ms < 0:
                    self.glinting = False

    @property
    def angle(self):
        return (math.pi if self.flip_delay > 0 else self.flip_ms / 700 * math.pi) if self.flipping else 0.

    @property
    def scale(self):
        if not self.growing:
            return 1.
        if self.grow_delay > 0:
            return 1. if self.shrinking else 0.
        return ease(self.grow_ms / 600 if self.shrinking else 1 - self.grow_ms / 600, bounce=.8)

    @property
    def glint(self):
        if not self.glinting or self.glint_delay > 0:
            return -1
        fraction, = struct.unpack('<f', struct.pack('<f', self.glint_ms / -600))
        return min(5, int(fraction * 6 + 6))

    def validate(self):
        if (not -250 <= self.flip_ms <= 700 or not -250 <= self.flip_delay <= 640
                or not -1000 <= self.grow_ms <= 600 or not -250 <= self.grow_delay <= 640
                or not -250 <= self.glint_ms <= 600 or not -250 <= self.glint_delay <= 640
                or self.flipping and self.flip_ms <= 0
                or self.growing and not self.shrinking and self.grow_ms < 0
                or self.glinting and self.glint_ms < 0):
            raise ValueError('Invalid grid cube clock')
