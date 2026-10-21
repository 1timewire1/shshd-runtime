"""The story's music as `SHSSoundManager` plays it in SHS HD and Cause of Death 1.4.7 (docs/ENGINE_ABI.md, "Music").

- **`playMusic`** (SHS HD `00053830`): ignored while Music is off. The playing cue asked again cancels its fade.
  Another cue fades the playing one out over 1000 ms (`stopMusic(-1)`) and waits as the pending cue.
- **`stopMusic(fade, clear)`** (`00053424`): 0 stops at once. Otherwise the music fades over `fade` ms (0xffff:
  1000), unless it is already fading. Service 81 passes the script's fade; the Music switch passes 1000.
- **`tick`** (`000536d8`): a finished fade unloads the cue. With nothing loaded, the pending cue starts while Music is
  on and is otherwise dropped.
- **The pause menu** (`SHSEngine::storeGameAudio` `0001e6e0` / `restoreGameAudio` `0001e688`). Switching Music on there
  plays the menu's song (desktop.Desktop's pause song); Resume fades it out before the restore.
  - On opening, playing music that is not fading has its state saved (`-[SHSSound save:]` keeps `currentTime`). It
    then fades out over 1000 ms and the pending cue is dropped. Music that is already fading finishes first.
  - Resume waits for that fade, then plays the saved cue from the saved position at full volume while Music is on,
    and drops it otherwise (`restartFromLoad` `000535e8`).

Fades are linear in time (`-[SHSSound getFadeLevel]`). The mixer is pygame's music stream. Whatever a host's mixer lacks
(the iOS host has no volume or busy state) is skipped.
"""
from io import BytesIO
import logging

from . import graphics as pygame
from .audio import mp3_length_ms
from .content import ContentError

FADE_MS = 1000


def stop_fade_ms(argument):
    """`stopMusic`'s fade for a script argument: 0 is at once, 0xffff (-1) is 1000 ms."""
    argument &= 0xffff
    return FADE_MS if argument == 0xffff else argument


class MusicStream:
    def __init__(self):
        self.current = None      # the loaded cue: dict(id, flag, start (s), length (s or None), played (ms))
        self.fade = None         # dict(since, ms, store): a running fade-out; `store` is the pause menu's
        self.pending = None      # (id, flag, opener) waiting for the playing cue's fade to end
        self.stored = None       # the saved position (s) of the cue the pause menu holds
        self.volume = 1.0
        self.paused = False      # the stream is paused (the window lost focus, service 83, or a stored cue)
        self.clock = None        # ticks when the played time was last counted

    @property
    def loaded(self):
        return self.current is not None

    @property
    def silent(self):
        """Nothing of the story's music sounds: none loaded, or held/paused."""
        return self.current is None or self.paused

    # ------------------------------------------------------------------ native operations

    def play(self, music_id, flag, opener, now, *, held=False):
        """`playMusic` with Music on. `opener(music_id)` returns (MP3 bytes, start in s). `held`: the pause menu is
        open and nothing is playing (a saved game resumed under it, as `SHSEngine::onTick` opens it after a load), so
        the cue waits for Resume instead of starting and fading out."""
        current = self.current
        if held and current is None:
            self.pending = (music_id, flag, opener)
            return
        if self.stored is not None and current is not None and current['id'] != music_id:
            self._drop_stored()             # (scripts do not run under the pause menu; a load or test can ask)
            current = None
        if current is not None and current['id'] == music_id:
            if self.fade is not None and not self.fade['store']:
                self.fade = None
                self._set_volume(self.volume)
            return
        if current is not None:
            if self.fade is None:
                self.fade = dict(since=now, ms=FADE_MS, store=False)
            self.pending = (music_id, flag, opener)
            return
        self._start(music_id, flag, opener, now)

    def stop(self, fade_ms, now):
        """`stopMusic(fade, true)`."""
        self.pending = None
        if self.stored is not None:
            self._drop_stored()             # stopped under the pause menu: nothing to resume
            return
        if self.current is None:
            return
        if fade_ms == 0:
            self._unload()
        elif self.fade is None:
            self.fade = dict(since=now, ms=fade_ms, store=False)

    def update(self, now, *, enabled, menu_open, paused, held_back=False):
        """One frame: the fade, a cue that played out, the pending cue, the pause menu's store/restore and the
        immediate pause (`paused`: focus or service 83). `held_back`: something else is still sounding (the menu's
        song the pause menu played), so the restore waits for silence, as `restoreGameAudio` does."""
        self._count(now)
        if self.fade is not None:
            level = 1 - (now - self.fade['since']) / self.fade['ms'] if self.fade['ms'] > 0 else 0
            if level > 0:
                self._set_volume(self.volume * level)
            elif self.fade['store']:
                self.fade = None
                self._pause_stream(True)
            else:
                self._unload(stop=not (self.pending is not None and enabled))     # starting the next cue stops it
        if self.current is not None and self.stored is None and not self.paused and self._finished():
            self._unload()
        if self.current is None and self.pending is not None and not menu_open:
            music_id, flag, opener = self.pending
            self.pending = None
            if enabled:
                self._start(music_id, flag, opener, now)
        if menu_open:
            if self.current is not None and self.stored is None and self.fade is None:
                self.stored = self.position()
                self.pending = None
                if not self.paused:
                    self.fade = dict(since=now, ms=FADE_MS, store=True)
                # A paused stream (an episode left for the main menu and resumed under its pause menu) is silent
                # already: it stays held, rather than playing for its fade.
        elif self.stored is not None and (self.fade is None or not self.fade['store']) and not held_back:
            position, self.stored = self.stored, None
            if enabled:
                self._replay(position, now)
            else:
                self._unload()
        holding = paused or (self.stored is not None and (self.fade is None or not self.fade['store']))
        if self.current is not None and holding != self.paused:
            self._pause_stream(holding)

    def disable(self, now):
        """The Music switch turned off: `setMusicEnabled(false)` -> `stopMusic(-1, true)`. A cue the pause menu holds
        stays held; Resume drops it while Music is still off (`restartFromLoad`)."""
        self.pending = None
        if self.stored is None and self.current is not None and self.fade is None:
            self.fade = dict(since=now, ms=FADE_MS, store=False)

    def set_volume(self, volume):
        self.volume = volume
        if self.fade is None and self.current is not None:
            self._set_volume(volume)

    def reset(self):
        """Forget everything (a new session); the stream is stopped."""
        self._unload()
        self.pending = self.stored = None

    # ------------------------------------------------------------------ position

    def position(self):
        """Where the loaded cue is in its file (s): it starts at `start` and a looping cue restarts at 0."""
        current = self.current
        at = current['start'] + current['played'] / 1000
        length = current['length']
        if current['flag'] and length and at >= length:
            at = (at - length) % length
        return at

    def _count(self, now):
        if self.current is not None and self.clock is not None and not self.paused:
            self.current['played'] += max(0, now - self.clock)
        self.clock = now

    # ------------------------------------------------------------------ mixer

    def _start(self, music_id, flag, opener, now):
        try:
            data, start = opener(music_id)
            music = pygame.mixer.music
            music.stop()
            music.load(BytesIO(data))
            self._set_volume(self.volume)
            music.play(loops=-1 if flag else 0, start=start)
        except (ContentError, pygame.error, OSError, ValueError) as error:     # the cue is skipped
            logging.warning('Music %s cannot be played: %s', music_id, error)
            self.current = None
            return
        length = mp3_length_ms(data)
        self.current = dict(id=music_id, flag=flag, start=start, played=0,
                            length=None if length is None else length / 1000)
        self.fade, self.paused, self.clock = None, False, now

    def _replay(self, position, now):
        current = self.current
        try:
            music = pygame.mixer.music
            self._set_volume(self.volume)
            music.play(loops=-1 if current['flag'] else 0, start=position)
        except (pygame.error, OSError, ValueError) as error:
            logging.warning('Music %s cannot resume: %s', current['id'], error)
            self._unload()
            return
        current.update(start=position, played=0)
        self.paused, self.clock = False, now

    def _drop_stored(self):
        self.stored = None
        self._unload()

    def _unload(self, *, stop=True):
        if self.current is not None and stop:
            try:
                pygame.mixer.music.stop()
            except pygame.error as error:
                logging.warning('Music cannot stop: %s', error)
        self.current = self.fade = None
        self.paused = False

    def _pause_stream(self, pause):
        self.paused = pause
        try:
            (pygame.mixer.music.pause if pause else pygame.mixer.music.unpause)()
        except pygame.error as error:
            logging.warning('Music cannot change pause state: %s', error)

    def _set_volume(self, volume):
        set_volume = getattr(pygame.mixer.music, 'set_volume', None)
        if set_volume is not None:
            try:
                set_volume(volume)
            except pygame.error as error:
                logging.warning('Music volume failed: %s', error)

    def _finished(self):
        get_busy = getattr(pygame.mixer.music, 'get_busy', None)
        if get_busy is None or self.current['flag']:
            return False
        try:
            return not get_busy()
        except pygame.error:
            return False
