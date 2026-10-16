"""Android's nonvisual fade callbacks (0007efe8 / 0007f0e8 / 0007ffb0)."""
from dataclasses import dataclass

from ..game_state import GameState
from ..vm import VMError


@dataclass
class SceneTransition(GameState):
    selector: int = 0
    phase: int = 0
    result: int = 0

    @property
    def active(self):
        return self.phase != 0

    @property
    def coverage(self):
        return 0.

    @property
    def duration_ms(self):
        return 0

    def start(self, selector, result):
        self.selector, self.result, self.phase = selector, result, 4

    def wake(self):
        self.phase, self.result = 1, 0

    def reveal(self):
        self.phase = 3

    def clear(self):
        self.selector = self.phase = self.result = 0

    def tick(self, elapsed_ms):
        # This is a frame boundary, not a duration or a visible fade. Phase 1
        # waits for KiWi to provide the next UI; phase 3 releases it next tick.
        return self.phase in (3, 4)

    def validate(self):
        if (self.phase not in (0, 1, 3, 4) or not -32768 <= self.selector <= 32767
                or not -32768 <= self.result <= 32767
                or (self.active and self.selector in (0, 20))
                or (self.phase != 4 and self.result != 0)
                or (not self.active and self.selector != 0)):
            raise VMError('Invalid scene transition state')
