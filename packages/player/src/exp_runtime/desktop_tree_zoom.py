"""HD's tree zoom tab (`SHSDTZButton`, `-[SHSViewController toggleDTZ]`): an exploration build, with a temporary
marker where the tab is.

In SHS HD 1.4.38 (decompiled 2026-10-29, reference/ghidra_scripts/dtview_zoom_dtzbutton_report.txt and
dtview_deceleration_orientation_report.txt) the tab is a 50 x 60-point view switched on with the tree panels
(`newGame:` / `resumeGame:` `setEnable:`). Its `drawRect:` sets up a transform and draws nothing, and it sits under
the game view: the shipped app shows no tab and the owner's taps in its corner did nothing. Tapped, `toggleDTZ` flips
`_dt_zoomed` and lays the screen out again inside a 0.5 s UIView animation (UIKit's ease in and out):

- Portrait (orientation 1), the 768 x 1024 screen: the game (`setupLocalInterfaceOrientation:`) moves down by 1024,
  off the screen; the tree (`SHSDTView`, 768 x 224) moves from behind the game's top (centre y 128) to the middle
  (512); the wall (`SHSFSView`, 224 x 768, centre (672, 400)) does not move and is left uncovered. The tab's centre
  goes from (25, 30) to (25, 994).
- Landscape (orientation 3), the 1024 x 768 screen as the views' rotation shows it: the game (always at 0.75) and the
  wall (centre x 912 -> 1424) slide right by 1024 and 512, off the screen; the tree (214 x 696, centre x 106) moves to
  the middle (512). The tab (60 x 50 on screen) goes from (196, 25) to (994, 25).

Zooming in during the story also brings up the pause menu (`invokePauseMenu`, with the pause sound 8011, here as
`open_pause`), and every toggle plays 8017. The pause menu is drawn on the game, which is off the screen, so it shows
once the tree is put back. A warp closes the zoom (`closeDTZ`, from `warpToNode:`).

ENABLED switches the exploration on (owner, 2026-10-29: to judge it, perhaps for phones, where landscape makes the
game small). MARKER is the temporary tab art: HD has none.
"""
import math

from . import graphics as pygame

ENABLED = True
DURATION_MS = 500                       # `setAnimationDuration: 0.5`
MARKER = (255, 0, 200, 150)             # temporary: HD draws nothing
MARKER_EDGE = (255, 255, 255)

PORTRAIT_SCREEN, LANDSCAPE_SCREEN = (768, 1024), (1024, 768)
# The tab's size and centre on the screen (points), shut and zoomed.
PORTRAIT_TAB = ((50, 60), (25, 30), (25, 994))
LANDSCAPE_TAB = ((60, 50), (196, 25), (994, 25))
PORTRAIT_TREE = (768, 224)              # the tree view's size in portrait; its centre y goes 128 -> 512
PORTRAIT_TREE_Y = (128, 512)
PORTRAIT_WALL = (560, 16, 224, 768)     # left, top, width, height (centre (672, 400))
GAME_SHIFT = 1024                       # the game's move, down (portrait) or right (landscape)
LANDSCAPE_WALL_SHIFT = 512              # 912 -> 1424


def ease(t):
    """UIViewAnimationCurveEaseInOut, near enough: slow, faster, slow."""
    return 0.5 - 0.5 * math.cos(math.pi * max(0.0, min(1.0, t)))


class TreeZoom:
    def __init__(self):
        self.zoomed = False             # `_dt_zoomed`
        self.t = 0.0                    # 0 shut .. 1 zoomed, in time
        self.tab = None                 # the tab's window rectangle as last drawn, or None when it is not there
        self.pressed = False

    @property
    def amount(self):
        return ease(self.t)

    @property
    def showing(self):
        """The layout is not the ordinary one (zoomed, or on the way in or out)."""
        return self.t > 0

    @property
    def settled(self):
        return self.t in (0.0, 1.0) and (self.t == 1.0) == self.zoomed

    def toggle(self):
        self.zoomed = not self.zoomed

    def close(self, *, instantly=False):
        self.zoomed = False
        if instantly:
            self.t = 0.0

    def advance(self, elapsed_ms):
        step = elapsed_ms / DURATION_MS
        self.t = min(1.0, self.t + step) if self.zoomed else max(0.0, self.t - step)

    @staticmethod
    def mode(window_size, panels_wide):
        """'landscape' beside the side panels, 'portrait' in an upright window without them, else None."""
        width, height = window_size
        if panels_wide:
            return 'landscape'
        return 'portrait' if height > width else None

    @staticmethod
    def screen(mode, frame):
        """HD's screen for `frame` (the game's window rectangle): (scale, left, top) of its points in the window."""
        if mode == 'portrait':
            s = frame.height / PORTRAIT_SCREEN[1]
            return s, frame.centerx - PORTRAIT_SCREEN[0] * s / 2, frame.y
        s = frame.height / LANDSCAPE_SCREEN[1]
        return s, frame.centerx - LANDSCAPE_SCREEN[0] * s / 2, frame.y

    def tab_rect(self, mode, frame):
        (w, h), shut, zoomed = PORTRAIT_TAB if mode == 'portrait' else LANDSCAPE_TAB
        s, left, top = self.screen(mode, frame)
        a = self.amount
        cx = shut[0] + (zoomed[0] - shut[0]) * a
        cy = shut[1] + (zoomed[1] - shut[1]) * a
        rect = pygame.Rect(0, 0, max(1, round(w * s)), max(1, round(h * s)))
        rect.center = round(left + cx * s), round(top + cy * s)
        return rect

    def draw_tab(self, window, rect):
        self.tab = rect
        marker = pygame.Surface(rect.size, pygame.SRCALPHA)
        marker.fill(MARKER)
        window.blit(marker, rect.topleft)
        pygame.draw.rect(window, MARKER_EDGE, rect, 2)

    def pointer(self, event, *, down, up):
        """A press and release on the tab toggles: 'toggled' then, 'taken' for the press (the game under the tab
        never sees it), else None."""
        if self.tab is None or not hasattr(event, 'pos') or getattr(event, 'button', 1) != 1:
            return None
        inside = self.tab.collidepoint(event.pos)
        if event.type == down and inside:
            self.pressed = True
            return 'taken'
        if event.type == up and self.pressed:
            self.pressed = False
            if inside:
                self.toggle()
                return 'toggled'
            return 'taken'
        return None
