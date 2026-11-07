"""shshd-runtime: the BREW games' catch game drawn over the story's scene (brew_catch.CatchGame), with its art from the addon (spec
`catch`; tools/translate/brew.py catch_pictures). BREW's 240 x 320 screen at 3 times, centred across the frame and from its top: at
that size it clears the player's bottom bar, and each art pixel stays whole. The places are native (FUN_00005b94). Nothing here
decides anything in the game.

With the "Java '08 Look" switch (library.java_look) and an addon that has it (spec `catch.java`, brew.java_look), the Java '08
demo's skin instead (l.java d(Graphics)): its cream-bordered screen with a blue header, `SCORE: n` in its outlined letters, a bar of
the items still to come, a cream guide line, its own pictures centred on BREW's (the game's sizes and places stay BREW's), and
`Minigame finished!` on its panel at the end."""
import io
import json

from . import graphics as pygame
from .brew_catch import ANGLED, FIELD_HEIGHT, FIELD_WIDTH, HEIGHT, PICTURE, SIDEWAYS, WIDTH

ADDON, SPEC = 'shsbrew', 26998
FRAME = (768, 1024)
SCALE, LEFT = 3, 24
FIELD_X, FIELD_Y = 6, 34
GAUGE_X, RING_Y = 36, 0                 # the ring; the bar's fill runs from 24 on and 3 down its 28
FILL_X, FILL_Y, FILL_HEIGHT, FILL_WIDTH = 60, 9, 21, 141
DIGIT_Y = 10
RING_WIDTH = 28
FILL_COLOUR, LINE_COLOUR = (255, 255, 0), (255, 255, 255)
# The Java skin, in BREW's pixels (its 176 x 220 places at 240 / 176): SCORE and the items bar in the header, cream line, colours.
JAVA_LABEL = (12, 10)
JAVA_BAR = (112, 9, 112, 12)
JAVA_LINE, JAVA_BAR_BACK, JAVA_BAR_FILL, JAVA_BAR_END = (255, 235, 211), (255, 255, 255), (248, 200, 0), (232, 120, 16)


def catch_spec(resources):
    """(The addon's catch spec, an archive to read it from), or None, from the library the episode came from."""
    library = getattr(resources, 'library', None)
    if library is None or not hasattr(library, 'addon'):
        return None
    found = library.addon(ADDON)
    if found is None or SPEC not in found[1].entries:
        return None
    spec = json.loads(found[1].read(SPEC)).get('catch')
    return None if spec is None else (spec, found[1])


def library_has_java_look(library):
    """Whether `library` holds a BREW addon built with the Java '08 demo's look (for the "Java '08 Look" switch)."""
    holder = type('Resources', (), {'library': library})()
    try:
        found = catch_spec(holder)
    except Exception:
        return False
    return found is not None and 'java' in found[0]


class BrewCatchRenderer:
    def __init__(self, resources):
        self.resources = resources
        self.canvas = None
        self._images = {}
        self._found = None              # (spec, archive): the addon's spec is large (every look), so it's read once
        self._bases = {}                # frame picture -> (the frame drawn on a canvas, its field's colour, the field)
        self._drawn = None              # the frame picture the canvas holds

    def _spec(self):
        if self._found is None:
            found = catch_spec(self.resources)
            if found is None:
                raise ValueError("The BREW games' addon has no catch game art: import its latest build")
            self._found = found
        return self._found

    def _start(self, frame):
        """The canvas for this frame, the screen's frame already on it. Only the header (score, ring, bar) and the field change,
        so the canvas is kept, and each frame those two are put back as the frame has them: the header from the frame
        picture, the field filled with its colour. Redrawing the whole frame (a 720 x 960 blend) cost the g54 milliseconds a
        frame."""
        base = self._bases.get(frame)
        if base is None:
            picture = pygame.Surface(FRAME, pygame.SRCALPHA)
            picture.fill((0, 0, 0, 0))
            picture.blit(self.image(frame), (LEFT, 0))
            field = pygame.Rect(LEFT + FIELD_X * SCALE, FIELD_Y * SCALE, FIELD_WIDTH * SCALE, FIELD_HEIGHT * SCALE)
            base = self._bases[frame] = (picture, picture.get_at(field.center), field)
        picture, colour, field = base
        if self.canvas is None or self._drawn != frame:
            self.canvas, self._drawn = picture.copy(), frame
        header = pygame.Rect(0, 0, FRAME[0], field.y)
        self.canvas.fill((0, 0, 0, 0), header)
        self.canvas.blit(picture, header, header)
        self.canvas.fill(colour, field)
        return self.canvas

    def image(self, resource):
        found = self._images.get(resource)
        if found is None:
            found = self._images[resource] = pygame.image.load(io.BytesIO(self._spec()[1].read(resource)), 'catch.png').convert_alpha()
        return found

    def alpha(self, game):
        return None

    def java_look(self):
        """Whether this episode wears the Java '08 Look: the switch is on and it's one of the packs the look is for (JAVA_LOOK_ART:
        '08's, not '07's, owner, 2026-11-06)."""
        library = getattr(self.resources, 'library', None)
        if not getattr(library, 'java_look', False):
            return False
        from .games import GAMES
        record = getattr(self.resources, 'record', None) or {}
        return record.get('pack_id') in getattr(GAMES.get(getattr(library, 'game_id', None)), 'JAVA_LOOK_ART', ())

    def drop_images(self):
        """Forget the pictures loaded so far (the "Java '08 Look" switch changed)."""
        self._images.clear()
        self._bases.clear()
        self.canvas = self._drawn = None

    def draw(self, session):
        game = session.engine.brew_catch
        spec = self._spec()[0]
        if self.java_look() and 'java' in spec:
            return self.draw_java(game, spec)
        surface = self._start(spec['frame'])
        field = pygame.Rect(LEFT + FIELD_X * SCALE, FIELD_Y * SCALE, FIELD_WIDTH * SCALE, FIELD_HEIGHT * SCALE)
        if game.mode == ANGLED:
            surface.fill(LINE_COLOUR, pygame.Rect(field.x, field.y + ((game.y >> 8) + game.height // 2 - 1) * SCALE, field.width, 2 * SCALE))
        elif game.mode == SIDEWAYS:
            surface.fill(LINE_COLOUR, pygame.Rect(field.x + (FIELD_WIDTH // 2 - 1) * SCALE, field.y, 2 * SCALE, field.height))
        surface.set_clip(field)
        pictures = spec['pictures']
        surface.blit(self.image(pictures[str(game.sprite)][0]), (field.x + (game.x >> 8) * SCALE, field.y + (game.y >> 8) * SCALE))
        for item in game.objects:
            picture = pictures[str(game.templates[item[4]][1])][0]
            surface.blit(self.image(picture), (field.x + (item[0] >> 8) * SCALE, field.y + (item[1] >> 8) * SCALE))
        surface.set_clip(None)
        if game.score > 0:
            width = max(1, game.score * FILL_WIDTH // max(1, game.target))
            surface.fill(FILL_COLOUR, pygame.Rect(LEFT + FILL_X * SCALE, FILL_Y * SCALE, width * SCALE, FILL_HEIGHT * SCALE))
        surface.blit(self.image(spec['ring']), (LEFT + GAUGE_X * SCALE, RING_Y * SCALE))
        digit = self.image(spec['digits'][game.digit])
        surface.blit(digit, (LEFT + GAUGE_X * SCALE + (RING_WIDTH * SCALE - digit.get_width()) // 2, DIGIT_Y * SCALE))
        if game.over:
            caption = self.image(spec['captions'][0 if game.out_of_items else 1])
            surface.blit(caption, caption.get_rect(center=(FRAME[0] // 2, 320 * SCALE // 2)))

    def draw_java(self, game, spec):
        """The Java '08 demo's skin over the same game: BREW's places and sizes, Java's pictures centred on them."""
        java = spec['java']
        surface = self._start(java['frame'])
        field = pygame.Rect(LEFT + FIELD_X * SCALE, FIELD_Y * SCALE, FIELD_WIDTH * SCALE, FIELD_HEIGHT * SCALE)
        if game.mode == ANGLED:
            surface.fill(JAVA_LINE, pygame.Rect(field.x, field.y + ((game.y >> 8) + game.height // 2 - 1) * SCALE, field.width, 2 * SCALE))
        elif game.mode == SIDEWAYS:
            surface.fill(JAVA_LINE, pygame.Rect(field.x + (FIELD_WIDTH // 2 - 1) * SCALE, field.y, 2 * SCALE, field.height))
        surface.set_clip(field)

        def picture(number, x, y, width, height):
            found = java['pictures'].get(str(number))
            if found is None:                               # (BREW's house has no Java copy)
                surface.blit(self.image(spec['pictures'][str(number)][0]), (field.x + x * SCALE, field.y + y * SCALE))
                return
            surface.blit(self.image(found[0]), (field.x + (x + (width - found[1]) // 2) * SCALE,
                                                field.y + (y + (height - found[2]) // 2) * SCALE))
        picture(game.sprite, game.x >> 8, game.y >> 8, game.width, game.height)
        for item in game.objects:
            template = game.templates[item[4]]
            picture(template[PICTURE], item[0] >> 8, item[1] >> 8, template[WIDTH], template[HEIGHT])
        surface.set_clip(None)
        x, y = LEFT + JAVA_LABEL[0] * SCALE, JAVA_LABEL[1] * SCALE
        label = self.image(java['label'])
        surface.blit(label, (x, y))
        x += label.get_width()
        for character in str(game.score):
            digit = self.image(java['digits'][int(character)])
            surface.blit(digit, (x, y))
            x += digit.get_width() - 2 * SCALE              # (its letters overlap by two: brew_java.font)
        bx, by, bw, bh = JAVA_BAR
        surface.fill(JAVA_BAR_BACK, pygame.Rect(LEFT + bx * SCALE, by * SCALE, bw * SCALE, bh * SCALE))
        left = (bw - 2) * game.remaining // max(1, game.total)
        if left > 0:
            surface.fill(JAVA_BAR_FILL, pygame.Rect(LEFT + (bx + 1) * SCALE, (by + 1) * SCALE, left * SCALE, (bh - 2) * SCALE))
            surface.fill(JAVA_BAR_END, pygame.Rect(LEFT + (bx + left) * SCALE, (by + 1) * SCALE, SCALE, (bh - 2) * SCALE))
        if game.over:
            panel = self.image(java['finished'])
            surface.blit(panel, panel.get_rect(center=(FRAME[0] // 2, 320 * SCALE // 2)))
