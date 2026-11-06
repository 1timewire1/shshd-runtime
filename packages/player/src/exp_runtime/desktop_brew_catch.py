"""shshd-runtime: the BREW games' catch game drawn over the story's scene (brew_catch.CatchGame), with its art from the addon (spec
`catch`; tools/translate/brew.py catch_pictures). BREW's 240 x 320 screen at 3 times, centred across the frame and from its top: at
that size it clears the player's bottom bar, and each art pixel stays whole. The places are native (FUN_00005b94). Nothing here
decides anything in the game."""
import io
import json

from . import graphics as pygame
from .brew_catch import ANGLED, FIELD_HEIGHT, FIELD_WIDTH, SIDEWAYS

ADDON, SPEC = 'shsbrew', 26998
FRAME = (768, 1024)
SCALE, LEFT = 3, 24
FIELD_X, FIELD_Y = 6, 34
GAUGE_X, RING_Y = 36, 0                 # the ring; the bar's fill runs from 24 on and 3 down its 28
FILL_X, FILL_Y, FILL_HEIGHT, FILL_WIDTH = 60, 9, 21, 141
DIGIT_Y = 10
RING_WIDTH = 28
FILL_COLOUR, LINE_COLOUR = (255, 255, 0), (255, 255, 255)


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


class BrewCatchRenderer:
    def __init__(self, resources):
        self.resources = resources
        self.canvas = None
        self._images = {}

    def _spec(self):
        found = catch_spec(self.resources)
        if found is None:
            raise ValueError("The BREW games' addon has no catch game art: import its latest build")
        return found

    def image(self, resource):
        found = self._images.get(resource)
        if found is None:
            found = self._images[resource] = pygame.image.load(io.BytesIO(self._spec()[1].read(resource)), 'catch.png').convert_alpha()
        return found

    def alpha(self, game):
        return None

    def draw(self, session):
        game = session.engine.brew_catch
        spec = self._spec()[0]
        if self.canvas is None:
            self.canvas = pygame.Surface(FRAME, pygame.SRCALPHA)
        surface = self.canvas
        surface.fill((0, 0, 0, 0))
        surface.blit(self.image(spec['frame']), (LEFT, 0))
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
