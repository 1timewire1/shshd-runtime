"""The interface's own sounds: `SHSSoundManager::playSound` for menu cues, from the selected game's base bank.

SHS HD `playSound` (`000538c8`) and CoD 1.4.7's (`00046eb4`) take a sound, a stop-others flag and a volume. A volume of
-1 means the Sound FX volume and obeys the Sound switch; a positive one (the music slider's preview) plays at that
volume even with Sound off. With the flag set, the other effects stop first. The preview of a volume slider
(`playFXVolumeFeedbackEffect`, SHS HD `0001c1e4`, CoD `0001a8a8`) only plays while the manager's list of playing
effects is empty, so dragging never stacks it. Ours checks only the effects this player started; the story's own
effects are not counted. See docs/MAIN_MENU.md, "Interface sounds".
"""
from io import BytesIO
import logging

from . import graphics as pygame
from .content import ContentError


class UiSounds:
    """One loaded Sound per base-bank asset, and the channels they play on."""

    def __init__(self):
        self.cache = {}
        self.channels = []

    def playing(self):
        self.channels = [channel for channel in self.channels if channel.get_busy()]
        return bool(self.channels)

    def play(self, library, asset, volume, *, stop_others=False, when_idle=False):
        """Play `asset` from `library` at `volume` (0..1). Returns whether it started."""
        if when_idle and self.playing():
            return False
        try:
            if asset not in self.cache:
                self.cache[asset] = pygame.mixer.Sound(file=BytesIO(library.read_asset(asset)))
            if stop_others:
                for channel in self.channels:
                    channel.stop()
                self.channels = []
            sound = self.cache[asset]
            sound.set_volume(volume)
            channel = sound.play()
        except (ContentError, pygame.error) as error:
            logging.debug('Interface sound %s unavailable: %s', asset, error)
            return False
        if channel is not None:
            self.channels.append(channel)
        return True

    def clear(self):
        self.cache.clear()
        self.channels = []
