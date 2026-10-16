"""Optional host playback checkpoint, separate from requested script cues."""
from dataclasses import dataclass


@dataclass
class SoundPlayback:
    asset: int
    position_ms: int

    def validate(self):
        if not 0 <= self.asset <= 32767 or self.position_ms < 0:
            raise ValueError('Invalid sound playback checkpoint')


@dataclass
class MusicPlayback:
    asset: int
    repeat: bool
    position_ms: int
    fade_ms: int = 0
    fade_total: int = 0
    finished: bool = False

    def validate(self):
        if (not 0 <= self.asset <= 32767 or self.position_ms < 0
                or not 0 <= self.fade_ms <= self.fade_total <= 32767
                or (self.fade_ms == 0 and self.fade_total != 0)):
            raise ValueError('Invalid music playback checkpoint')
