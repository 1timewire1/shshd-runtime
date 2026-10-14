"""Native location alignment, independent of image decoding and drawing.

Android 0007b790/00136364 move node 1000 linearly over 250 ms. SHS and
CoD iOS use the same left/center/right targets. Store the fraction of the
image's horizontal overflow so saves and headless execution need no pixels.
"""
from dataclasses import dataclass


PAN_MS = 250


@dataclass
class BackgroundPan:
    automatic: bool = True
    alignment: int = 0  # Only consulted after service 97 supplies a value.
    start: float = 0.5
    target: float = 0.5
    elapsed_ms: int = PAN_MS

    @property
    def position(self):
        return self.start + (self.target - self.start) * (self.elapsed_ms / PAN_MS)

    def center(self):
        """A replacement background node starts at (160,180)."""
        self.start = self.target = 0.5
        self.elapsed_ms = PAN_MS

    def align(self, alignment):
        if not self.automatic:
            alignment = self.alignment
        self.start = self.position
        # Native switch defaults to the node's current position.
        self.target = {1: 0.0, 2: 0.5, 3: 1.0}.get(alignment, self.start)
        self.elapsed_ms = 0

    def dialogue(self, presentation):
        if presentation in (1, 2):
            self.align(1 if presentation == 1 else 3)

    def configure(self, automatic, alignment):
        """Service 97 also immediately requests its supplied alignment."""
        self.automatic, self.alignment = automatic, alignment
        self.align(alignment)

    def tick(self, elapsed_ms):
        self.elapsed_ms = min(PAN_MS, self.elapsed_ms + elapsed_ms)

    def origin(self, width, height):
        # Do not scale or clamp small images: native targets use their width.
        return int((320 - width) * self.position), 180 - height // 2

    def validate(self):
        if (not -32768 <= self.alignment <= 32767
                or not 0.0 <= self.start <= 1.0 or not 0.0 <= self.target <= 1.0
                or not 0 <= self.elapsed_ms <= PAN_MS):
            raise ValueError('Invalid background pan state')
