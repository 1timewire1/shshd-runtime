"""The iOS HD launch screens: the loading screen, the sound question over it, and the EA flash into the main menu.

Decompiled (`SHSInitLoadingRenderer::render`, `SHSEngine::onStart`, `setAppMode(100 / 102)`, `queueStartSoundMenu`) and
checked against `reference/screenshots/main menu/IMG_0235`. Frame points (768 x 1024).

* Mode 100 fills the window with gray 0x696969, draws the EA disc (resource 1) centered at (384, 341.33), the gray outlined
  title (resource 2) centered at (384, 768) and over it the colored title (resource 3) revealed from both outer edges
  inward: `setLoadingPhase(i, n)` sets phase = i / n and the clip is x < phase * 384 and x > 768 - phase * 384.
  Nothing takes input.
* The sound question is menu 7 ("Play with sound?", No / Yes; menu 8 "Continue playing your music?" when music from
  another app is playing) of the menu engine, centered over this screen.
* Mode 102 (after the answer) plays sound 8005 (the EA jingle) and flashes: the flare (resource 5, 622 x 600) sits at
  (393, 341.33) and grows 1 -> 4 over 0.4 s from 0.2 s in, while a white layer fades in over the same 0.4 s; when it is
  fully white the main menu starts.

Not decompiled: how long real loading takes (a desktop has nothing to load, so the reveal is a timed animation here).
"""
from functools import lru_cache

from . import graphics as pygame

from .graphics import faded
from .hd_ui import HdUi, S, FRAME

DISC_CENTER, TITLE_CENTER = (384, 341.33), (384, 768)
GRAY = (105, 105, 105)
FLARE_CENTER = (393, 341.33)
FLASH_DELAY, FLASH_TIME = 0.2, 0.4
LOADING_TIME = 1.2                      # seconds the reveal takes here
FLASH_TOTAL = FLASH_DELAY + FLASH_TIME
JINGLE = 8005


class HdBootScreen(HdUi):
    hd_layer = True

    def __init__(self, library):
        super().__init__(library)
        self.canvas = pygame.Surface((FRAME[0] * S, FRAME[1] * S)).convert()

    @staticmethod
    def available(library):
        try:
            return library is not None and library.hd_ipa is not None and all(
                library.hd_raw_resource(i) is not None for i in (1, 2, 3, 5, 15, 17))
        except Exception:
            return False

    @lru_cache(maxsize=4)
    def art(self, resource_id):
        return self.scaled(self.resource(resource_id), S)

    def blit_centered(self, image, center, clip=None):
        rect = image.get_rect(center=(round(center[0] * S), round(center[1] * S)))
        if clip is not None:
            self.canvas.set_clip(pygame.Rect(clip[0] * S, clip[1] * S, clip[2] * S, clip[3] * S))
        self.canvas.blit(image, rect)
        self.canvas.set_clip(None)

    def draw_loading(self, phase):
        """The loading screen at `phase` (0..1)."""
        self.canvas.fill(GRAY)
        self.blit_centered(self.art(1), DISC_CENTER)
        self.blit_centered(self.art(2), TITLE_CENTER)
        color = self.art(3)
        reach = max(0.0, min(1.0, phase)) * 384
        self.blit_centered(color, TITLE_CENTER, (0, 0, reach, FRAME[1]))
        self.blit_centered(color, TITLE_CENTER, (FRAME[0] - reach, 0, reach, FRAME[1]))
        return self.canvas

    def draw_flash(self, seconds, *, over_black=False):
        """The EA flash `seconds` after the answer; `done` once fully white. `over_black`: after a game switch, over
        the black the old game faded to instead of the loading screen."""
        if over_black:
            self.canvas.fill((0, 0, 0))
        else:
            self.draw_loading(1.0)
        t = max(0.0, min(1.0, (seconds - FLASH_DELAY) / FLASH_TIME))
        white = pygame.Surface(self.canvas.get_size())
        white.fill((255, 255, 255))
        white = faded(white, round(255 * t))
        self.canvas.blit(white, (0, 0))
        flare = self.resource(5)
        # 4x at 2x would be a 5000 pixel image; a soft glow loses nothing at half that.
        scale = min((1 + 3 * t) * S, 2400 / max(flare.get_size()))
        self.blit_centered(self.scaled(flare, scale), FLARE_CENTER)
        return self.canvas

    @staticmethod
    def flash_done(seconds):
        return seconds >= FLASH_TOTAL
