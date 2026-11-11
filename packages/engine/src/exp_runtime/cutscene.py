"""shshd-runtime: a storyboard cutscene (service 218, asked for only where service 70 selector CUTSCENE_QUERY says it plays), first
made for Day of Diss's opening (owner, 2026-11-02; docs/X360.md). A JSON resource lays out the timeline: pictures with a window moving
across them, overlays growing or sliding in, and sounds at their moments. It runs by itself up to `hold`, where it stays until a press;
a press before `skip` jumps there, and one between goes on to `hold`. This keeps only the clock; desktop_cutscene.py draws it.

Where the spec names `music`, the player keeps this clock on that track's position (sync), so a sound lands on its beat however the
frames fall. A jump leaves the music's clock behind, as the music plays on where it is.

The spec, in milliseconds and pixels of `size`:
    {"format": "shshd-cutscene", "version": 1, "size": [w, h], "music": id (optional), "hold": ms, "skip": ms,
     "shots": [{"image": id, "start": ms, "end": ms, "from": [x, y, w, h], "to": [x, y, w, h], "ease": "out" (optional)}, ...],
     "overlays": [{"image": id, "start": ms, "end": ms, "from": [cx, cy, w, h], "to": [cx, cy, w, h]}, ...],
     "sounds": [{"at": ms, "sound": id}, ...]}
A shot's window is the part of its picture that fills the frame. A shot stays up until the next one starts; an overlay, once started,
stays to the end.

Version 2 (General's Aspect Ratio) adds "tallest": [w, h], the tallest frame the stills serve, as wide as `size`; a shot's "fit":
"crop" (default: its windows at `tallest`'s shape, cropped about their centre to the frame's) or "height" (its windows at `size`'s
shape, zoomed by height about its "anchor": [x, y]); and an overlay's "follow": a shot's index, whose picture it stays on
(cutscene_spec._check_version_2, desktop_cutscene.py). Version 1 serves 3:4 only: a taller frame shows it centred, backdrop round it.
"""
from dataclasses import dataclass, field

from .cutscene_spec import CUTSCENE, CUTSCENE_QUERY, FORMAT, VERSION, _is_int, read_spec  # noqa: F401


def moved(item, ms):
    """The item's [x, y, w, h] at `ms`."""
    span = item['end'] - item['start']
    k = 1.0 if span <= 0 else max(0.0, min(1.0, (ms - item['start']) / span))
    if item.get('ease') == 'out':
        k = 1 - (1 - k) ** 2
    return [a + (b - a) * k for a, b in zip(item['from'], item['to'])]


@dataclass
class Cutscene:
    spec: int
    hold_ms: int
    skip_ms: int
    music: int = -1                     # the track that keeps the clock, until a jump (-1: none)
    cues: list = field(default_factory=list)    # [ms, sound], in order
    elapsed_ms: int = 0
    next_cue: int = 0
    finished: bool = False
    sounds: list = field(default_factory=list)

    @classmethod
    def opened(cls, spec_id, data):
        spec = read_spec(data)
        return cls(spec_id, spec['hold'], spec['skip'], spec.get('music', -1), [[s['at'], s['sound']] for s in spec.get('sounds', [])])

    @property
    def held(self):
        """Whether it has reached `hold`, and is waiting for a press."""
        return self.elapsed_ms >= self.hold_ms

    def _to(self, ms):
        self.elapsed_ms = max(0, min(self.hold_ms, ms))
        while self.next_cue < len(self.cues) and self.cues[self.next_cue][0] <= self.elapsed_ms:
            self.sounds.append(self.cues[self.next_cue][1])
            self.next_cue += 1

    def tick(self, elapsed_ms):
        self._to(self.elapsed_ms + elapsed_ms)

    def sync(self, ms):
        """The music's position (ms): the clock follows it, either way, until the hold. A sound never plays twice."""
        if not self.held:
            self._to(ms)

    def press(self):
        self.music = -1
        if self.elapsed_ms < self.skip_ms:
            while self.next_cue < len(self.cues) and self.cues[self.next_cue][0] < self.skip_ms:
                self.next_cue += 1          # (what it jumped over stays silent)
            self._to(self.skip_ms)
        elif not self.held:
            self._to(self.hold_ms)
        else:
            self.finished = True

    def validate(self):
        if (not all(_is_int(v) for v in (self.spec, self.hold_ms, self.skip_ms, self.music, self.elapsed_ms, self.next_cue))
                or not isinstance(self.finished, bool) or not 0 <= self.skip_ms <= self.hold_ms
                or not 0 <= self.elapsed_ms <= self.hold_ms or not 0 <= self.next_cue <= len(self.cues)
                or not all(isinstance(c, list) and len(c) == 2 and all(_is_int(v) for v in c) for c in self.cues)
                or not isinstance(self.sounds, list)):
            raise ValueError('Invalid saved cutscene')
