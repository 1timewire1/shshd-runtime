"""HD's two unfinished layout toggles, as an exploration build: the tree zoom tab (`SHSDTZButton`,
`-[SHSViewController toggleDTZ]`, with a temporary marker where the tab is) and the portrait zoom button
(`SHSPZButton`, `togglePZ`).

In SHS HD 1.4.38 (decompiled 2026-10-29 and 2026-11-04, reference/ghidra_scripts/dtview_zoom_dtzbutton_report.txt,
dtview_deceleration_orientation_report.txt and reference/Other Games/docs/SMARTPHONE_HIDDEN_FEATURES.md) neither button
is ever created: no code names either class, nothing assigns `g_engineDTZButton` or `g_enginePZButton`, and neither is
in a nib. So the shipped app shows no tab and the owner's taps in its corner did nothing. Their code is otherwise whole.

The tree zoom tab is a 50 x 60-point view, switched with the tree panels (`newGame:` / `resumeGame:` `setEnable:`). Its
`drawRect:` sets up a transform and draws nothing. Tapped, `toggleDTZ` flips `_dt_zoomed` and lays the screen out again
inside a 0.5 s UIView animation (UIKit's ease in and out):

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

The portrait zoom button only has a place in portrait: a 64 x 64 view filled with olive (`drawRect:`), centre (736, 992),
or (480, 992) zoomed; landscape puts it off the screen. Tapped, `togglePZ` flips `_portrait_zoomed` and, in the same kind
of 0.5 s animation, shrinks the full-size game to 0.75, moved by (`_portrait_alignx`, -`_portrait_aligny`). No sound, no
pause: the story carries on in the smaller game, whose touches are mapped back by the view's transform, and whatever it
uncovers keeps its own. Those two offsets start at 0 and nothing writes them in 1.4.38, so the game shrinks around the
screen's centre. With the tree zoom in, the button is 256 lower, off the screen, and the game is at full size again.

ENABLED switches the exploration on, off by default. Tree zoom on its own (owner, 2026-10-29): tried on desktop, too rough
as it stands (the portrait strip shows about one scene); to be revisited for phones, where landscape makes the game small,
once the Android and iOS ports are ready for outside testing. MARKER is the temporary tab art: HD has none.

PORTRAIT_ALIGN is not HD's data apart from its (0, 0): SHSHD_PORTRAIT_ALIGN="x,y" tries other offsets, in HD's own terms.
"""
import math
import os

from . import graphics as pygame

ENABLED = os.environ.get('SHSHD_TREE_ZOOM') == '1'
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

# `SHSPZButton`: its size and centre on the portrait screen, shut and zoomed; how much lower the tree zoom puts it; its
# fill. `setupLocalInterfaceOrientation:`: the game's scale when zoomed.
PORTRAIT_ZOOM_TAB = ((64, 64), (736, 992), (480, 992))
PORTRAIT_ZOOM_TAB_DROP = 256
PORTRAIT_ZOOM_FILL = (0x7F, 0x7F, 0)    # `setColor: 0x7f7f00`
PORTRAIT_ZOOM_SCALE = 0.75


def portrait_align(text=None):
    """(`_portrait_alignx`, `_portrait_aligny`): 0 in HD, or an "x,y" to try."""
    text = os.environ.get('SHSHD_PORTRAIT_ALIGN', '') if text is None else text
    try:
        x, y = (float(part) for part in text.split(','))
    except ValueError:
        return (0.0, 0.0)
    return (x, y)


PORTRAIT_ALIGN = portrait_align()


def ease(t):
    """UIViewAnimationCurveEaseInOut, near enough: slow, faster, slow."""
    return 0.5 - 0.5 * math.cos(math.pi * max(0.0, min(1.0, t)))


class TreeZoom:
    def __init__(self):
        self.zoomed = False             # `_dt_zoomed`
        self.t = 0.0                    # 0 shut .. 1 zoomed, in time
        self.tab = None                 # the tab's window rectangle as last drawn, or None when it is not there
        self.pressed = False
        self.portrait_zoomed = False    # `_portrait_zoomed`
        self.portrait_t = 0.0
        self.portrait_tab = None
        self.portrait_pressed = False
        self.game_down = False          # the press now down began on the shrunken game, so the game keeps it

    @property
    def amount(self):
        return ease(self.t)

    @property
    def portrait_amount(self):
        return ease(self.portrait_t)

    @property
    def showing(self):
        """The layout is not the ordinary one (zoomed, or on the way in or out)."""
        return self.t > 0 or self.portrait_t > 0

    @property
    def tree_showing(self):
        return self.t > 0

    @property
    def settled(self):
        return (self.t in (0.0, 1.0) and (self.t == 1.0) == self.zoomed
                and self.portrait_t in (0.0, 1.0) and (self.portrait_t == 1.0) == self.portrait_zoomed)

    def toggle(self):
        self.zoomed = not self.zoomed

    def toggle_portrait(self):
        self.portrait_zoomed = not self.portrait_zoomed

    def close(self, *, instantly=False):
        self.zoomed = False
        if instantly:
            self.t = 0.0
            self.portrait_zoomed, self.portrait_t, self.game_down = False, 0.0, False

    def advance(self, elapsed_ms):
        step = elapsed_ms / DURATION_MS
        self.t = min(1.0, self.t + step) if self.zoomed else max(0.0, self.t - step)
        self.portrait_t = min(1.0, self.portrait_t + step) if self.portrait_zoomed else max(0.0, self.portrait_t - step)

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

    def portrait_tab_rect(self, frame):
        """`SHSPZButton setupViewOrientation_internal:` case 1: zoomed or with the tree zoom in it is at the zoomed x;
        the tree zoom also drops it."""
        (w, h), shut, zoomed = PORTRAIT_ZOOM_TAB
        s, left, top = self.screen('portrait', frame)
        across = max(self.portrait_amount, self.amount)
        cx = shut[0] + (zoomed[0] - shut[0]) * across
        cy = shut[1] + PORTRAIT_ZOOM_TAB_DROP * self.amount
        rect = pygame.Rect(0, 0, max(1, round(w * s)), max(1, round(h * s)))
        rect.center = round(left + cx * s), round(top + cy * s)
        return rect

    def draw_portrait_tab(self, window, rect):
        self.portrait_tab = rect
        window.fill(PORTRAIT_ZOOM_FILL, rect)

    def game_rect(self, frame):
        """Where the game is in the portrait layout (`setupLocalInterfaceOrientation:` cases 1 and 2). The tree zoom's
        layout has no scale of its own, so it brings the game back to full size as it moves it off."""
        s = self.screen('portrait', frame)[0]
        a, p = self.amount, self.portrait_amount
        scale = 1 - (1 - PORTRAIT_ZOOM_SCALE) * p * (1 - a)
        rect = pygame.Rect(0, 0, max(1, round(frame.width * scale)), max(1, round(frame.height * scale)))
        rect.center = (round(frame.centerx + PORTRAIT_ALIGN[0] * s * p),
                       round(frame.centery - PORTRAIT_ALIGN[1] * s * p + GAME_SHIFT * s * a))
        return rect

    def to_game(self, frame, position):
        """A window position on the shrunken game, as the same place on the full-size game (the view's transform maps
        touches this way); outside the game, the nearest edge, for a press the game already holds."""
        rect = self.game_rect(frame)
        x = max(0, min(rect.width - 1, position[0] - rect.x))
        y = max(0, min(rect.height - 1, position[1] - rect.y))
        return (round(frame.x + x * frame.width / rect.width), round(frame.y + y * frame.height / rect.height))

    def _tap(self, tab, pressed, event, down, up):
        """(result, pressed now) for a press and release on `tab`: see pointer."""
        if tab is None or not hasattr(event, 'pos') or getattr(event, 'button', 1) != 1:
            return None, pressed
        inside = tab.collidepoint(event.pos)
        if event.type == down and inside:
            return 'taken', True
        if event.type == up and pressed:
            return ('toggled' if inside else 'taken'), False
        return None, pressed

    def pointer(self, event, *, down, up):
        """A press and release on the tab toggles: 'toggled' then, 'taken' for the press (the game under the tab
        never sees it), else None."""
        result, self.pressed = self._tap(self.tab, self.pressed, event, down, up)
        if result == 'toggled':
            self.toggle()
        return result

    def portrait_pointer(self, event, *, down, up):
        """The same for the portrait zoom button."""
        result, self.portrait_pressed = self._tap(self.portrait_tab, self.portrait_pressed, event, down, up)
        if result == 'toggled':
            self.toggle_portrait()
        return result
