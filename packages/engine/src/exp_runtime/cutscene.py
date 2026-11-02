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
"""
from dataclasses import dataclass, field
import json

CUTSCENE = 218
CUTSCENE_QUERY = 202
FORMAT, VERSION = 'shshd-cutscene', 1


def _is_int(value):
    return type(value) is int


def _box(value):
    return (isinstance(value, list) and len(value) == 4 and all(type(v) in (int, float) for v in value)
            and value[2] > 0 and value[3] > 0)


def read_spec(data):
    """The spec from its resource's bytes, checked; ValueError if it isn't one."""
    try:
        spec = json.loads(data)
    except (ValueError, UnicodeDecodeError) as error:
        raise ValueError(f'Not a cutscene: {error}') from error
    if not isinstance(spec, dict) or spec.get('format') != FORMAT or spec.get('version') != VERSION:
        raise ValueError('Not a cutscene')
    size, hold, skip = spec.get('size'), spec.get('hold'), spec.get('skip')
    shots, overlays, sounds = spec.get('shots'), spec.get('overlays', []), spec.get('sounds', [])
    if (not isinstance(size, list) or len(size) != 2 or not all(_is_int(v) and v > 0 for v in size)
            or not _is_int(hold) or not _is_int(skip) or not 0 <= skip <= hold
            or not _is_int(spec.get('music', 0))
            or not isinstance(shots, list) or not shots or not isinstance(overlays, list) or not isinstance(sounds, list)):
        raise ValueError('Invalid cutscene')
    for item in shots + overlays:
        if (not isinstance(item, dict) or not _is_int(item.get('image')) or not _is_int(item.get('start'))
                or not _is_int(item.get('end')) or item['end'] < item['start']
                or not _box(item.get('from')) or not _box(item.get('to')) or item.get('ease', 'out') != 'out'):
            raise ValueError('Invalid cutscene picture')
    if shots[0]['start'] != 0 or any(a['start'] > b['start'] for a, b in zip(shots, shots[1:])):
        raise ValueError('A cutscene\'s shots start at 0, in order')
    if (not all(isinstance(s, dict) and _is_int(s.get('at')) and _is_int(s.get('sound')) for s in sounds)
            or any(a['at'] > b['at'] for a, b in zip(sounds, sounds[1:]))):
        raise ValueError('Invalid cutscene sounds')
    return spec


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
