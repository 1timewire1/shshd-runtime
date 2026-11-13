"""shshd-runtime: the X360 translations' leash game drawn over the story's scene (x360_games.LeashGame), with the art of
the X360 addon's skin (spec `leash`; tools/translate/x360_arena_art.py).

The places come from the prototype's own group (hud/minigame/power_bar/main) as MS3 draws it at 1280 x 720, a little
larger and moved to fit the 3:4 frame: the power bar upright at the right, filling from its red end at the bottom, and
the icon of the wanted shake at the bottom, its joystick flipbook over the arrows. Nothing here decides anything in the
game. The inputs the player reads for it are here too, as far as they are geometry: where a stick and a drag point."""
from . import graphics as pygame
from .desktop_x360_slot import FRAME, X360SlotRenderer
from .x360_games import CLOSING, CLOSING_LEASH_MS, DOWN, LEFT, LEVEL_FULL, OPENING, OPENING_MS, READY, RIGHT, UP

BAR_SIZE = (130, 680)                   # the bar's whole picture, turned upright (hud/power_bar, 1.15 times MS3's)
BAR_CENTRE = (690, 460)
ICON_CENTRE, ICON, STICK = (384, 790), 250, 188     # control_icon: the arrows at 2.0, the joystick over them at 1.5
FLIP_MS = 125                           # the joystick's four cells (MultilayerUVFlipTime 0.5)
FADE_MS = 300                           # the machine's fade in and out
HINT_TEXT, HINT_Y, HINT_HEIGHT = 'Shake the way the arrows point!', 400, 40
START_TEXT, START_Y, START_HEIGHT = 'Press OK to start', 480, 52
STICK_PAST = .75                        # the native check: past this much of the stick's travel
DRAG_UNITS = 70                         # a drag this far across the 768-wide frame is a shake's direction


def stick_direction(x, y):
    """Where a stick at (x, y), each -1..1, points for the leash, or None: left and right before up and down, as the
    native check has its axes."""
    if abs(x) > STICK_PAST:
        return RIGHT if x > 0 else LEFT
    if abs(y) > STICK_PAST:
        return DOWN if y > 0 else UP
    return None


def drag_direction(anchor, x, y):
    """Where a drag from `anchor` to (x, y), in frame units, has gone for the leash, or None if not far enough yet."""
    dx, dy = x - anchor[0], y - anchor[1]
    if max(abs(dx), abs(dy)) < DRAG_UNITS:
        return None
    if abs(dx) >= abs(dy):
        return RIGHT if dx > 0 else LEFT
    return DOWN if dy > 0 else UP


class X360LeashRenderer(X360SlotRenderer):
    def __init__(self, resources):
        super().__init__(resources)
        self._cells = {}

    def alpha(self, game):
        """The game's fade as it opens and closes (None: whole)."""
        if game.phase == OPENING:
            return min(1.0, max(0.0, 1 - game.phase_ms / min(FADE_MS, OPENING_MS)))
        if game.phase == CLOSING and game.phase_ms < FADE_MS:
            return max(0.0, game.phase_ms / min(FADE_MS, CLOSING_LEASH_MS))
        return None

    def cell(self, resource, frame):
        """Frame `frame` of a joystick flipbook: two by two, read across."""
        key = (resource, frame)
        found = self._cells.get(key)
        if found is None:
            image = self.image(resource)
            w, h = image.get_width() // 2, image.get_height() // 2
            found = self._cells[key] = pygame.transform.smoothscale(
                image.subsurface(pygame.Rect(frame % 2 * w, frame // 2 * h, w, h)), (STICK, STICK))
        return found

    def draw(self, session):
        game = session.engine.x360_leash
        specs = self._spec()[0]
        spec, words = specs['leash'], specs['slot']
        surface = self.fresh_canvas()
        surface.fill((0, 0, 0, 0))
        self._bar(surface, specs, spec, game)
        name = 'updown' if game.wanted else 'leftright'
        arrows = self.scaled(spec['arrows'][name], (ICON, ICON))
        surface.blit(arrows, arrows.get_rect(center=ICON_CENTRE))
        stick = self.cell(spec['stick'][name], game.anim_ms // FLIP_MS % 4)
        surface.blit(stick, stick.get_rect(center=ICON_CENTRE))
        if game.phase == READY:
            for text, y, height in ((HINT_TEXT, HINT_Y, HINT_HEIGHT), (START_TEXT, START_Y, START_HEIGHT)):
                line = self.text(words, text, height)
                surface.blit(line, line.get_rect(center=(FRAME[0] // 2, y)))

    def _upright(self, resource):
        """A bar picture turned as the prototype's -90 degrees has it, its left end at the bottom, at BAR_SIZE."""
        key = ('upright', resource)
        found = self._scaled.get(key)
        if found is None:
            found = self._scaled[key] = pygame.transform.smoothscale(
                pygame.transform.rotate(self.image(resource), 90), BAR_SIZE)
        return found

    def _bar(self, surface, specs, spec, game):
        w, h = BAR_SIZE
        x, y = BAR_CENTRE[0] - w // 2, BAR_CENTRE[1] - h // 2
        surface.blit(self._upright(specs['pictures']['power_bar']), (x, y))
        shown = round(h * game.level / LEVEL_FULL)
        if shown > 0:
            fill = self._upright(spec['fill'])
            surface.blit(fill, (x, y + h - shown), pygame.Rect(0, h - shown, w, shown))
