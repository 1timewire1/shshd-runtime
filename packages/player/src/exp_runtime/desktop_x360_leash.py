"""shshd-runtime: the X360 translations' leash game drawn over the story's scene (x360_games.LeashGame), with the art of
the X360 addon's skin (spec `leash`; tools/translate/x360_arena_art.py).

The places come from the prototype's own group (hud/minigame/power_bar/main) as MS3 draws it at 1280 x 720, a little
larger and moved to fit the 3:4 frame: the power bar upright at the right, filling from its red end at the bottom, and
the icon of the wanted shake at the bottom, its joystick flipbook over the arrows. Nothing here decides anything in the
game. The inputs the player reads for it are here too, as far as they are geometry: where a stick and a drag point.

Behind them, Zack, the doberman and the collar-and-lead (B1, 2026-11-18): frames rendered offline at the pound background's
own camera (reference tools x360_leashbooth.py), an atlas per animation in the animations add-on (`shsx360anim`, spec
`leash_cast`; the X360 add-on's own `leash.cast` up to its revision 21), by build: MS4's, or MS3's for the MS3 Characters
switch. The spec places them on the background (`places`, by background: their size
against the shot's and where their feet go, in the 960 x 1440 picture's pixels), and the player says where the picture is
this frame (`scene_placement`), so they follow its pan and its size in a taller frame. The game says which animation and
how far in (LeashGame.cast_anim, cast_ms), and what it blends from over 0.3 s. Without them the game plays as before."""
from . import graphics as pygame
from .desktop_nr_arena_x360 import animation_source
from .desktop_x360_slot import FRAME, X360SlotRenderer
from .x360_games import (BLEND_MS, CAST_ANIMS, CAST_IDLE, CLOSING, CLOSING_LEASH_MS, DOWN, LEFT, LEVEL_FULL, OPENING,
                         OPENING_MS, READY, RIGHT, RUNNING, UP)

BAR_SIZE = (130, 680)                   # the bar's whole picture, turned upright (hud/power_bar, 1.15 times MS3's)
BAR_CENTRE = (690, 460)
ICON_CENTRE, ICON, STICK = (384, 790), 250, 188     # control_icon: the arrows at 2.0, the joystick over them at 1.5
FLIP_MS = 125                           # the joystick's four cells (MultilayerUVFlipTime 0.5)
FADE_MS = 300                           # the machine's fade in and out
HINT_TEXT, HINT_Y, HINT_HEIGHT = 'Shake the way the arrows point!', 400, 40
START_TEXT, START_Y, START_HEIGHT = 'Press OK to start', 480, 52
STICK_PAST = .75                        # the native check: past this much of the stick's travel
DRAG_UNITS = 70                         # a drag this far across the 768-wide frame is a shake's direction
PICTURE = (960, 1440)                   # the pound's background, as the spec's places count it


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
    # Set by the player each frame before `draw`: the background's id and where its whole picture lies, (x, y, width,
    # height) in this canvas's pixels (Desktop._leash_scene). None: no cast.
    background_id = None
    scene_placement = None

    def __init__(self, resources):
        super().__init__(resources)
        self._cells = {}
        self._hud = None
        self._cast_frames = {}          # (atlas, rect, size): a frame at the size it's drawn, the last two kept
        self._cast_look = None          # the build drawn last

    def alpha(self, game):
        """The game's fade as it opens and closes (None: whole). With the cast drawn, the close is the cast's: the bar
        and icon fade within the canvas (draw), and the cast at the end."""
        if game.phase == OPENING:
            return min(1.0, max(0.0, 1 - game.phase_ms / min(FADE_MS, OPENING_MS)))
        if game.phase == CLOSING and not game.cast and game.phase_ms < FADE_MS:
            return max(0.0, game.phase_ms / min(FADE_MS, CLOSING_LEASH_MS))
        return None

    # -- the cast ----------------------------------------------------------------------------------------------
    def _animations(self):
        """({dance, dance_ms3, leash_cast}, archive): the animations add-on (owner, 2026-11-18), or the X360 add-on itself up
        to its revision 21 (animation_source); None without either."""
        anim = getattr(self, '_anim', None)
        if anim is None or anim[0] is not self.resources:
            anim = self._anim = (self.resources, animation_source(self.resources, self._spec()))
        return anim[1]

    def _anim_image(self, resource):
        """One of the cast's atlases, from the archive it comes from (kept with the skin's pictures)."""
        found = self._images.get(resource)
        if found is None:
            import io
            found = self._images[resource] = pygame.image.load(io.BytesIO(self._animations()[1].read(resource)),
                                                               'x360.png').convert_alpha()
        return found

    def cast_build(self):
        """(the cast's spec, `leash_cast`, and this look's build of it), or None without them."""
        found = self._animations()
        cast = found[0].get('leash_cast') if found is not None else None
        if not cast:
            return None
        ms3 = getattr(getattr(self.resources, 'library', None), 'ms3_characters', False)
        build = cast.get('ms3' if ms3 else 'ms4') or cast.get('ms4')
        return (cast, build) if build else None

    def _cast_atlases(self, build=None):
        """The atlases of the cast's builds (or of `build`) that are loaded."""
        found = self.cast_build() if self._skin is not None else None
        if found is None:
            return []
        builds = [build] if build is not None else [b for b in (found[0].get('ms4'), found[0].get('ms3')) if b]
        return [a['atlas'] for b in builds for a in b['animations'].values() if a['atlas'] in self._images]

    def drop_cast(self, keep=None):
        """Forget the cast's atlases (about 114 MB decoded a look at 15 fps) but `keep`'s: once the game has gone (Desktop), or the
        other look's after the MS3 Characters switch."""
        kept = set(self._cast_atlases(keep)) if keep is not None else set()
        for atlas in self._cast_atlases():
            if atlas not in kept:
                self._images.pop(atlas, None)
        self._cast_frames.clear()

    @property
    def holds_cast(self):
        return bool(self._cast_atlases())

    def cast_place(self):
        """The cast's place on this frame's background, or None (no cast, no place for that background, no picture)."""
        found = self.cast_build()
        if found is None or self.scene_placement is None:
            return None
        place = found[0].get('places', {}).get(str(self.background_id))
        return None if place is None else (found[0], found[1], place)

    def _preload_step(self, build):
        """One atlas not yet loaded, MG1_IDLE2's first, so the cast's first frames don't wait on all five (about 114 MB
        decoded): a step a frame as the game opens, rather than a stall."""
        for name in (CAST_IDLE, *CAST_ANIMS):
            atlas = build['animations'].get(name, {}).get('atlas')
            if atlas is not None and atlas not in self._images:
                self._anim_image(atlas)
                return

    def _cast_cell(self, build, name, ms):
        """(atlas, cell) for animation `name` at `ms`: a loop wraps, the others hold their last frame."""
        anim = build['animations'].get(name) or build['animations'][CAST_IDLE]
        frames = anim['frames']
        index = ms * build['fps'] // 1000
        index = index % len(frames) if anim.get('loop') else min(index, len(frames) - 1)
        return anim['atlas'], frames[int(index)]

    def _cast_frame(self, atlas, cell, size):
        key = atlas, tuple(cell['rect']), size
        found = self._cast_frames.get(key)
        if found is None:
            image = self._anim_image(atlas).subsurface(pygame.Rect(cell['rect']))
            found = image if image.get_size() == size else pygame.transform.smoothscale(image, size)
            if len(self._cast_frames) >= 2:             # (the blend's two: one scaled frame each)
                self._cast_frames.pop(next(iter(self._cast_frames)))
            self._cast_frames[key] = found
        return found

    def _cast_blit(self, surface, cast, build, place, name, ms, alpha):
        """One of the cast's frames, through the place onto the picture and the picture's placement onto the canvas."""
        atlas, cell = self._cast_cell(build, name, ms)
        left, top, right, bottom = cell['box']
        ax, ay = build['anchor']
        k = cast['shot'][0] / build['size'][0] * place['scale']           # picture pixels per frame pixel
        fx, fy = place['feet']
        px, py, pw, ph = self.scene_placement
        sx, sy = pw / PICTURE[0], ph / PICTURE[1]                          # canvas pixels per picture pixel
        x = px + (fx + (left - ax) * k) * sx
        y = py + (fy + (top - ay) * k) * sy
        size = (max(1, round((right - left) * k * sx)), max(1, round((bottom - top) * k * sy)))
        image = self._cast_frame(atlas, cell, size)
        if alpha < 1:
            image = pygame.faded(image, round(255 * alpha))
        surface.blit(image, (round(x), round(y)))

    def _cast(self, surface, game):
        """Zack, the doberman and the collar under the bar; True if drawn. A blend draws what it comes from under it, the
        new one growing in over BLEND_MS (each at up to twice its share, so the pair never shows through); the held close
        fades them over its last BLEND_MS."""
        found = self.cast_place()
        if found is None:
            return False
        cast, build, place = found
        if self._cast_look is not build:                # (the MS3 Characters switch: the other look's go)
            if self._cast_look is not None:
                self.drop_cast(keep=build)
            self._cast_look = build
        if game.phase in (OPENING, READY, RUNNING):
            game.cast = True                            # the close will hold them (x360_games.LeashGame.closing_total_ms)
        alpha = 1.0
        if game.phase == CLOSING and game.cast:
            alpha = min(1.0, max(0, game.phase_ms) / BLEND_MS)
        share = min(1.0, game.cast_ms / BLEND_MS) if game.cast_from is not None else 1.0
        if share < 1:
            self._cast_blit(surface, cast, build, place, game.cast_from, game.cast_from_ms + game.cast_ms,
                            alpha * min(1.0, 2 * (1 - share)))
        self._cast_blit(surface, cast, build, place, game.cast_anim, game.cast_ms, alpha * min(1.0, 2 * share))
        self._preload_step(build)
        return True

    def hud_alpha(self, game):
        """The bar's and icon's own fade while the close holds the cast: out over its first FADE_MS (None: whole)."""
        if game.phase != CLOSING or not game.cast:
            return None
        return max(0.0, 1 - (game.closing_total_ms - game.phase_ms) / FADE_MS)

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
        canvas = surface = self.fresh_canvas()
        canvas.fill((0, 0, 0, 0))
        self._cast(canvas, game)
        hud = self.hud_alpha(game)
        if hud is not None:
            if hud <= 0:
                return
            if self._hud is None or self._hud.get_size() != canvas.get_size():
                self._hud = pygame.Surface(canvas.get_size(), pygame.SRCALPHA)
            surface = self._hud
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
        if surface is not canvas:
            canvas.blit(pygame.faded(surface, round(255 * hud)), (0, 0))

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
