"""Read SDL_mixer's current decoder position, including loops and cue offsets."""
import ctypes
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def decoder():
    import pygame.mixer
    module = Path(pygame.mixer.__file__)
    # POSIX resolves the extension's linked exports. Windows exposes these
    # on its bundled SDL_mixer DLL instead. Never load an unrelated system DLL.
    for path in (module, *sorted(module.parent.glob('*mixer*.dll'))):
        try:
            library = ctypes.CDLL(str(path))
            function = library.Mix_GetMusicPosition
            function.argtypes, function.restype = [ctypes.c_void_p], ctypes.c_double
            return library
        except (OSError, AttributeError):
            continue
    return None


def position_ms():
    library = decoder()
    if library is not None:
        position = library.Mix_GetMusicPosition(None)
        if position >= 0:
            return int(position * 1000)
    return None


class Sound:
    """A seekable decoded effect; SDL channels expose no decoder playhead."""
    def __init__(self, stream, start_ms=0):
        import pygame
        self.pygame = pygame
        self.sound = pygame.mixer.Sound(file=stream)
        frequency, bits, channels = pygame.mixer.get_init()
        self.start_ms = start_ms
        self.duration_ms = round(self.sound.get_length() * 1000)
        if start_ms:
            frame = frequency * start_ms // 1000
            data = self.sound.get_raw()[frame * (abs(bits) // 8) * channels:]
            self.sound = pygame.mixer.Sound(buffer=data) if data else None
        self.channel = self.sound.play() if self.sound is not None else None
        if self.channel is not None:
            self.channel.set_volume(1)
        self.started_ms = pygame.time.get_ticks()
        self.paused_ms = None

    def get_busy(self):
        return bool(self.channel is not None and self.channel.get_sound() is self.sound and self.channel.get_busy())

    def position_ms(self):
        now = self.pygame.time.get_ticks() if self.paused_ms is None else self.paused_ms
        return min(self.duration_ms, self.start_ms + max(0, now - self.started_ms))

    def set_volume(self, volume):
        if self.get_busy():
            self.channel.set_volume(volume)

    def stop(self):
        if self.get_busy():
            self.channel.stop()

    def pause(self):
        if self.get_busy() and self.paused_ms is None:
            self.paused_ms = self.pygame.time.get_ticks()
            self.channel.pause()

    def unpause(self):
        if self.get_busy() and self.paused_ms is not None:
            self.started_ms += self.pygame.time.get_ticks() - self.paused_ms
            self.paused_ms = None
            self.channel.unpause()
