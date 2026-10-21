"""CoD's queued SHSFadeLayer tracks and delayed UI callback.

GameModel 0000f998/0000ee5c and SHSFadeLayer 00058188..00058e84.
The libc rand stream is independent of SHS's lrand48 and KiWi randomness.
"""
from dataclasses import dataclass

from ..game_state import GameState
from ..vm import VMError


@dataclass
class SceneTransition(GameState):
    selector: int = 0
    phase: int = 0
    elapsed_ms: int = 0
    result: int = 0
    random_state: int = 1

    @property
    def active(self):
        return self.phase != 0

    def start(self, selector, result):
        if selector == 20:
            # Darwin's Park-Miller rand(), initially seeded with 1. No game
            # seeding call exists; the other caller belongs to ZIP encryption.
            self.random_state = (16807 * (self.random_state or 123459876)) % 2147483647
            selector = 1 + (self.random_state & 1)
        self.selector, self.result = selector, result
        self.phase, self.elapsed_ms = 4, 0

    def reveal(self):
        self.phase, self.elapsed_ms, self.result = 3, 0, 0

    def wake(self):
        self.phase, self.elapsed_ms, self.result = 1, 0, 0

    def clear(self):
        self.selector = self.phase = self.elapsed_ms = self.result = 0

    @property
    def delay_ms(self):
        return 300 if self.phase == 3 and self.selector in (1, 2) else 0

    @property
    def duration_ms(self):
        # An unrecognized selector starts no layers. isFinished's native
        # watchdog releases it only after strictly more than seven seconds.
        return 1500 + self.delay_ms if self.selector in (1, 2, 6) else 7001

    def tick(self, elapsed_ms):
        if self.phase == 1:
            return False
        self.elapsed_ms = min(self.duration_ms, self.elapsed_ms + elapsed_ms)
        return self.elapsed_ms == self.duration_ms

    @property
    def coverage(self):
        if not self.active or self.selector not in (1, 2, 6):
            return 0.0
        if self.phase == 1:
            return 1.0
        progress = min(1., max(0., (self.elapsed_ms - self.delay_ms) / 1200))
        return progress if self.phase == 4 else 1 - progress

    def validate(self):
        if (not 0 <= self.random_state < 2147483647 or self.phase not in (0, 1, 3, 4)
                or not -32768 <= self.selector <= 32767
                or not -32768 <= self.result <= 32767
                or not 0 <= self.elapsed_ms < self.duration_ms
                or (self.active and self.selector in (0, 20))
                or (self.phase != 4 and self.result != 0)
                or (self.phase == 1 and self.elapsed_ms != 0)
                or (not self.active and (self.selector or self.elapsed_ms))):
            raise VMError('Invalid scene transition state')
