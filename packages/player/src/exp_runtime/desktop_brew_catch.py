"""shshd-runtime: the BREW games' catch game drawn over the story's scene (brew_catch.CatchGame), with its art from the addon (spec
`catch`; tools/translate/brew.py catch_pictures). BREW's 240 x 320 screen at 3 times, centred across the frame and from its top: at
that size it clears the player's bottom bar, and each art pixel stays whole. The places are native (FUN_00005b94). Nothing here
decides anything in the game.

With the "Java '08 Look" switch (library.java_look) and an addon that has it (spec `catch.java`, brew.java_look), the Java '08
demo's skin instead (l.java d(Graphics)): its cream-bordered screen with a blue header, `SCORE: n` in its outlined letters, a bar of
the items still to come, a cream guide line, its own pictures centred on BREW's (the game's sizes and places stay BREW's), and
`Minigame finished!` on its panel at the end.

Where the episode maps BREW's board to an optional add-on's (presentation `optional_art`, with its switch on: the Surviving
Hollywood Preview with `shshw` and "Hollywood Art"; owner, 2026-11-13), that add-on's skin instead (its spec `catch`; tools/translate
shw.py catch_art): the Surviving Hollywood demo's board (its header and lavender field), `Score: n` centred in the header's left box
in its letters, the bar of items still to come in the right, its pictures for the ones the episode maps (centred on BREW's places,
as the Java skin's are), and its closing line (`Time is up!`, `Max Points!`).

A translated pack whose catch game is another add-on's own (the profile's TRANSLATED_CATCH_ADDON: Surviving Hollywood's lite
Chapter 1, 31700, with `shshw`; owner, 2026-11-14: nothing from the BREW add-on) reads that add-on's spec in place of the BREW one's
and always wears its skin, the pictures its catch list names being the skin's own by number."""
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
# The Surviving Hollywood skin's bar (screens.js bar(): white, filled yellow, a darker mark at the fill's end, its corners black)
# and guide line.
HW_BAR_BACK, HW_BAR_FILL, HW_BAR_END, HW_CORNER, HW_LINE = (255, 255, 255), (248, 200, 0), (216, 112, 64), (0, 0, 0), (255, 255, 255)
HW_SPEC = 26998


def catch_addon(resources):
    """The add-on whose catch game the episode plays: its pack's own (TRANSLATED_CATCH_ADDON), else None (the BREW add-on)."""
    if getattr(resources, 'record', None) is None:
        return None
    from .content import pack_setting
    return pack_setting(resources, 'TRANSLATED_CATCH_ADDON')


def catch_spec(resources):
    """(The addon's catch spec, an archive to read it from), or None, from the library the episode came from."""
    library = getattr(resources, 'library', None)
    if library is None or not hasattr(library, 'addon'):
        return None
    found = library.addon(catch_addon(resources) or ADDON)
    if found is None or SPEC not in found[1].entries:
        return None
    spec = json.loads(found[1].read(SPEC)).get('catch')
    return None if spec is None else (spec, found[1])


def library_has_java_look(library):
    """Whether `library` holds a BREW addon built with the Java '08 demo's look (for the "Java '08 Look" switch)."""
    if hasattr(library, 'addon_resource'):
        # The spec alone: `addon` reads and hashes the whole addon first (Options asks; g54, 2026-11-09).
        try:
            data = library.addon_resource(ADDON, SPEC)
            return data is not None and 'java' in (json.loads(data).get('catch') or {})
        except (ValueError, UnicodeError):
            return False
    holder = type('Resources', (), {'library': library})()
    try:
        found = catch_spec(holder)
    except Exception:
        return False
    return found is not None and 'java' in found[0]


class BrewCatchRenderer:
    # shshd-runtime (General's Aspect Ratio): the game's own screen, the canvas's top this many pixels; in a taller frame the
    # player centres it (Desktop.render: story_lift), the bottom bar and gear staying at the frame's bottom.
    SCREEN_HEIGHT = 320 * SCALE

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
                raise ValueError(f"The {catch_addon(self.resources) or ADDON} add-on has no catch game art: import its latest build")
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
        from .content import pack_setting
        return pack_setting(self.resources, 'JAVA_LOOK_ART') is not None

    def drop_images(self):
        """Forget the pictures loaded so far (the "Java '08 Look" or "Hollywood Art" switch changed)."""
        self._images.clear()
        self._bases.clear()
        self.canvas = self._drawn = None
        self._skin = False
        self.__dict__.pop('_skin_pictures', None)

    _skin = False                           # (the optional skin found for this episode, or None; False not yet asked)

    def skin(self, spec):
        """(the optional add-on's archive, its catch spec) when the episode maps BREW's board to it (optional_art_source), else
        None."""
        if self._skin is False:
            self._skin, self._own_skin = None, False
            if catch_addon(self.resources) is not None:
                self._skin, self._own_skin = (self._spec()[1], spec), True
                return self._skin
            source = getattr(self.resources, 'optional_art_source', None)
            found = source(spec['frame']) if source is not None else None
            if found is not None and HW_SPEC in found[0].entries:
                catch = json.loads(found[0].read(HW_SPEC)).get('catch')
                if catch is not None and catch.get('board') == found[1]:
                    self._skin = (found[0], catch)
        return self._skin

    def skin_image(self, archive, resource):
        key = ('skin', resource)
        found = self._images.get(key)
        if found is None:
            found = self._images[key] = pygame.image.load(io.BytesIO(archive.read(resource)), 'catch.png').convert_alpha()
        return found

    def draw(self, session):
        game = session.engine.brew_catch
        spec = self._spec()[0]
        skin = self.skin(spec)
        if skin is not None:
            return self.draw_skin(game, spec, *skin)
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

    def _start_skin(self, archive, board, field_top):
        """The canvas with the skin's board on it, as _start: the header put back from the board each frame, the field filled."""
        key = ('skin', board)
        base = self._bases.get(key)
        if base is None:
            picture = pygame.Surface(FRAME, pygame.SRCALPHA)
            picture.fill((0, 0, 0, 0))
            picture.blit(self.skin_image(archive, board), (LEFT, 0))
            field = pygame.Rect(LEFT, field_top * SCALE, FIELD_WIDTH * SCALE + 2 * FIELD_X * SCALE, self.SCREEN_HEIGHT - field_top * SCALE)
            base = self._bases[key] = (picture, picture.get_at(field.center), field)
        picture, colour, field = base
        if self.canvas is None or self._drawn != key:
            self.canvas, self._drawn = picture.copy(), key
        header = pygame.Rect(0, 0, FRAME[0], field.y)
        self.canvas.fill((0, 0, 0, 0), header)
        self.canvas.blit(picture, header, header)
        self.canvas.fill(colour, field)
        return self.canvas, field

    def draw_skin(self, game, spec, archive, catch):
        """The optional add-on's skin over the same game: BREW's places and sizes, its pictures centred on them."""
        surface, shown = self._start_skin(archive, catch['board'], catch['field_top'])
        field = pygame.Rect(LEFT + FIELD_X * SCALE, FIELD_Y * SCALE, FIELD_WIDTH * SCALE, FIELD_HEIGHT * SCALE)
        if game.mode == ANGLED:
            surface.fill(HW_LINE, pygame.Rect(shown.x, field.y + ((game.y >> 8) + game.height // 2 - 1) * SCALE, shown.width, 2 * SCALE))
        elif game.mode == SIDEWAYS:
            surface.fill(HW_LINE, pygame.Rect(field.x + (FIELD_WIDTH // 2 - 1) * SCALE, shown.y, 2 * SCALE, shown.height))
        surface.set_clip(shown)
        mapped = self.__dict__.setdefault('_skin_pictures', {})

        own = getattr(self, '_own_skin', False)

        def picture(number, x, y, width, height):
            ours = spec['pictures'][str(number)][0]
            if own:
                mapped.setdefault(ours, (archive, ours))
            if ours not in mapped:
                mapped[ours] = self.resources.optional_art_source(ours)
            source = mapped[ours]
            if source is None:                              # a picture the episode doesn't map stays BREW's
                surface.blit(self.image(ours), (field.x + x * SCALE, field.y + y * SCALE))
                return
            image = self.skin_image(*source)
            surface.blit(image, (field.x + x * SCALE + (width * SCALE - image.get_width()) // 2,
                                 field.y + y * SCALE + (height * SCALE - image.get_height()) // 2))
        picture(game.sprite, game.x >> 8, game.y >> 8, game.width, game.height)
        for item in game.objects:
            template = game.templates[item[4]]
            picture(template[PICTURE], item[0] >> 8, item[1] >> 8, template[WIDTH], template[HEIGHT])
        surface.set_clip(None)
        lx, ly, lw, lh = catch['label']
        digits = [int(c) for c in str(max(0, game.score))]
        total = catch['prefix_width'] + sum(catch['digit_widths'][d] + catch['tracking'] for d in digits) - catch['tracking']
        x, y = lx + (lw - total) // 2, ly + (lh - catch['height']) // 2
        surface.blit(self.skin_image(archive, catch['prefix']), (LEFT + x * SCALE, y * SCALE))
        x += catch['prefix_width']
        for d in digits:
            surface.blit(self.skin_image(archive, catch['digits'][d]), (LEFT + x * SCALE, y * SCALE))
            x += catch['digit_widths'][d] + catch['tracking']
        bx, by, bw, bh = catch['bar']
        rect = lambda x0, y0, w, h: pygame.Rect(LEFT + x0 * SCALE, y0 * SCALE, w * SCALE, h * SCALE)
        surface.fill(HW_BAR_BACK, rect(bx, by, bw, bh))
        left = (game.remaining + len(game.objects)) * bw // max(1, game.total)
        if left > 0:
            surface.fill(HW_BAR_FILL, rect(bx, by, min(left, bw), bh))
            if left < bw:
                surface.fill(HW_BAR_END, rect(bx + left, by, 1, bh))
        for cx, cy in ((bx, by), (bx + bw - 1, by), (bx, by + bh - 1), (bx + bw - 1, by + bh - 1)):
            surface.fill(HW_CORNER, rect(cx, cy, 1, 1))
        if game.over:
            caption = self.skin_image(archive, catch['captions'][0 if game.out_of_items else 1])
            surface.blit(caption, caption.get_rect(center=(LEFT + 120 * SCALE, 320 * SCALE // 2)))

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
