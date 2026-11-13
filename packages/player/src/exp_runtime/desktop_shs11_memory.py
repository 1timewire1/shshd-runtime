"""shshd-runtime: SHS '11's Memory drawn over the story's scene (shs11_games.MemoryGame), with its own art and fonts from
the addon (spec `memory`; tools/translate/shs11.py memory_ui).

The frame is N73's layout at 3.2 times (its 240 wide to this player's 768), since its 240 x 304 screen has this player's
shape; the 480 x 800 build's art is that layout at twice the size, with its grid's own offsets, so it draws at 1.6. N73's
places: the clock ring (7, 10), the score ring (176, 10), boxes and the banner from (7, 69) and 226 wide, the grid at y = 111
(`bg`.j, `am`, gamelib entries 9, 11 and 16). The boxes here are drawn to the shape of its sliced ones, not from their
slices. Where a dealt letter starts its flight isn't known: here it's the middle of the banner's place. Nothing here decides
anything in the game."""
import io
import json

from . import graphics as pygame
from .shs11_games import GRID_TEXT, BAD, BLANK, CELLS, CUE, DEAL, GOAL, HIDDEN, LOOK, NEXT, PLAY, READY, RIGHT, SHOWN, TIME_UP, WRONG

ADDON, SPEC, FORMAT, VERSION = 'shs11', 26199, 'shshd-shs11', 1
FRAME = (768, 1024)
ART = 1.6                               # the 480 x 800 build's pixels on this frame
CLOCK_PLACE, SCORE_PLACE = (22, 32), (563, 32)
GRID_Y = 355
BOX_X, BOX_Y, BOX_WIDTH = 22, 221, 724
BANNER_HEIGHT = 112
TEXT_LINE, TEXT_PAD = 58, 34
CUE_LETTER_MS = 30                      # how fast a cue types, here; '11 has its own Text Speed option
FLOAT_RISE, FLOAT_RISE_MS = 115, 400    # `am` case 4: 36 of N73's over 400 ms
LETTER_SCALE, BANNER_SCALE = ART, 1.1
TIME_UP_Y = 620
PRESS_MS = 120                          # how long a pick shows the tile's pressed colours, here
BOX_WHITE, BOX_BLUE, BOX_LIGHT, BOX_DARK = (255, 251, 245), (64, 120, 205), (118, 170, 240), (40, 90, 170)
TEXT_COLOUR, CLOCK_COLOUR, SHADOW = (40, 40, 50), (120, 110, 100), (214, 208, 200)
TILE_PRESSED, TILE_WRONG, TILE_RIGHT = 1, 2, 3


def memory_spec(resources):
    """(The addon's spec, an archive to read it from), or None, from the library the episode came from."""
    library = getattr(resources, 'library', None)
    if library is None or not hasattr(library, 'addon'):
        return None
    found = library.addon(ADDON)
    if found is None or SPEC not in found[1].entries:
        return None
    spec = json.loads(found[1].read(SPEC))
    if spec.get('format') != FORMAT or spec.get('version') != VERSION or 'memory' not in spec:
        return None
    return dict(spec['memory'], reflex=spec.get('reflex')), found[1]


class Shs11MemoryRenderer:
    # shshd-runtime (General's Aspect Ratio, owner 2026-11-12): in a frame of another shape the canvas is 768 points
    # across and the frame's shape, see-through over the scene; N73's screen (rings, box, grid) is drawn whole in its
    # middle, `dy` points down. The scene shows round it (its desk under the grid runs on to the frame's bottom, where
    # the gear stays). HD's 768 x 1024 at 3:4, where nothing moves.
    frame_units = (384, 512)
    dy = 0

    @property
    def fills_frame(self):
        return self.frame_units != (384, 512)

    def canvas_size(self):
        wide, tall = self.frame_units
        if (wide, tall) == (384, 512):
            return FRAME
        return FRAME[0], max(FRAME[1], round(FRAME[0] * tall / wide))

    hd_layer = True
    grid_y = GRID_Y

    def __init__(self, resources):
        self.resources = resources
        self.canvas = None
        self.cursor = 4                 # a keyboard's or controller's cell: the middle
        self.cursor_shown = False       # only once keys have moved it
        self._loaded = None
        self._images = {}
        self._glyphs = {}

    def _spec(self):
        if self._loaded is None:
            self._loaded = memory_spec(self.resources)
            if self._loaded is None:
                raise ValueError("SHS '11's addon has no Memory art: import its latest build")
        return self._loaded

    def image(self, resource):
        found = self._images.get(resource)
        if found is None:
            found = self._images[resource] = pygame.image.load(io.BytesIO(self._spec()[1].read(resource)),
                                                               's11.png').convert_alpha()
        return found

    def prime_steps(self, background_id=None):
        """shshd-runtime: the pictures and pieces the game's first frame would load, a step at a time, for the player to
        take while a line sits still (Desktop._prime_games)."""
        spec = self._spec()[0]
        pictures = [spec[part]['picture'] for part in ('clock', 'score', 'grid', 'numbers')]
        pictures += list(spec['tiles']['pictures']) + list(spec['floats'])
        pictures += [font['picture'] for font in spec['fonts'].values()]
        for picture in dict.fromkeys(pictures):
            yield lambda picture=picture: self.image(picture)
        for part in ('clock', 'score', 'numbers'):
            for frame in spec[part]['frames']:
                yield lambda part=part, frame=frame: self.piece(spec[part]['picture'], frame)
        for picture in spec['tiles']['pictures']:
            for frame in spec['tiles']['frames']:
                yield lambda picture=picture, frame=frame: self.piece(picture, frame)

    def piece(self, resource, frame, scale=ART):
        """A frame of a sprite, scaled: frame = source x, y, w, h, and its place in its box."""
        key = (resource, tuple(frame[:4]), scale)
        found = self._images.get(key)
        if found is None:
            x, y, w, h = frame[:4]
            part = self.image(resource).subsurface(pygame.Rect(x, y, w, h))
            found = self._images[key] = pygame.transform.smoothscale(part, (max(1, round(w * scale)), max(1, round(h * scale))))
        return found

    def glyph(self, font, char, scale, colour=None):
        """A character's picture and its (offset x, offset y, advance), scaled, or None."""
        key = (font, char, scale, colour)
        if key in self._glyphs:
            return self._glyphs[key]
        spec = self._spec()[0]['fonts'][font]
        entry = spec['glyphs'].get(str(ord(char)))
        found = None
        if entry is not None:
            x, y, w, h, ox, oy, advance = entry
            picture = None
            if w > 0 and h > 0:
                part = self.image(spec['picture']).subsurface(pygame.Rect(x, y, w, h)).copy()
                if colour is not None:
                    part.fill((*colour, 255), special_flags=pygame.BLEND_RGBA_MIN)
                    part.fill((*colour, 0), special_flags=pygame.BLEND_RGBA_MAX)
                picture = pygame.transform.smoothscale(part, (max(1, round(w * scale)), max(1, round(h * scale))))
            found = (picture, round(ox * scale), round(oy * scale), advance * scale)
        self._glyphs[key] = found
        return found

    def width(self, font, text, scale):
        return sum(found[3] for found in (self.glyph(font, c, scale) for c in text) if found)

    def write(self, surface, font, text, x, y, scale, colour=None):
        """A line, with its top at y."""
        for char in text:
            found = self.glyph(font, char, scale, colour)
            if found is None:
                continue
            picture, ox, oy, advance = found
            if picture is not None:
                surface.blit(picture, (round(x) + ox, y + oy))
            x += advance

    def centred(self, surface, font, text, centre, scale, colour=None):
        line = round(self._spec()[0]['fonts'][font]['line'] * scale)
        self.write(surface, font, text, centre[0] - self.width(font, text, scale) / 2, centre[1] - line // 2, scale, colour)

    def wrapped(self, text, width):
        lines, line = [], ''
        for word in text.split(' '):
            longer = f'{line} {word}' if line else word
            if line and self.width('text', longer, ART) > width:
                lines.append(line)
                line = word
            else:
                line = longer
        return [*lines, line]

    def box(self, surface, y, height, *, x=BOX_X, width=BOX_WIDTH):
        """'11's box, flat and slanted: white over a thick blue edge, its lower right cut away."""
        cut = min(46, height // 3)
        outer = [(x + 22, y), (x + width - 40, y + 6), (x + width, y + cut), (x + width, y + height - cut),
                 (x + width - 34, y + height), (x, y + height), (x, y + 30)]
        inner = [(x + 34, y + 16), (x + width - 50, y + 20), (x + width - 16, y + cut + 6), (x + width - 16, y + height - cut - 10),
                 (x + width - 46, y + height - 16), (x + 16, y + height - 16), (x + 16, y + 36)]
        pygame.draw.polygon(surface, BOX_BLUE, outer)
        pygame.draw.polygon(surface, BOX_LIGHT, outer[:3] + [(x + width - 16, y + cut + 6), (x + width - 50, y + 20), (x + 34, y + 16), (x + 16, y + 36), (x, y + 30)])
        pygame.draw.polygon(surface, BOX_WHITE, inner)

    def text_box(self, surface, text, typed=None, top=BOX_Y):
        lines = self.wrapped(text, BOX_WIDTH - 2 * TEXT_PAD)
        height = max(BANNER_HEIGHT, TEXT_LINE * len(lines) + 2 * TEXT_PAD - 8)
        self.box(surface, top, height)
        left = len(text) if typed is None else typed
        y = top + TEXT_PAD - 6
        for line in lines:
            self.write(surface, 'text', line[:max(0, left)], BOX_X + TEXT_PAD, y, ART, TEXT_COLOUR)
            left -= len(line) + 1
            y += TEXT_LINE

    def banner(self, surface, word):
        self.box(surface, BOX_Y, BANNER_HEIGHT)
        self.centred(surface, 'letters', '-'.join(word), (FRAME[0] // 2, BOX_Y + BANNER_HEIGHT // 2), BANNER_SCALE, None)

    def cell_rect(self, cell):
        x, y, w, h = self._spec()[0]['tiles']['cells'][cell]
        return pygame.Rect(round(x * ART), self.grid_y + round(y * ART), round(w * ART), round(h * ART))

    def cell_at(self, x, y):
        """The cell at a frame position, or None."""
        for cell in range(CELLS):
            if self.cell_rect(cell).collidepoint(x, y):
                return cell
        return None

    def tile_centre(self, cell):
        frame = self._spec()[0]['tiles']['frames'][cell]
        x, y = self._spec()[0]['tiles']['cells'][cell][:2]
        return (round((x + frame[4] + frame[2] / 2) * ART), self.grid_y + round((y + frame[5] + frame[3] / 2) * ART))

    def draw_grid(self, surface, game):
        spec = self._spec()[0]
        grid = spec['grid']
        for frame, (x, width) in zip(grid['frames'], grid['places']):
            piece = self.piece(grid['picture'], frame)
            if frame[2] != width:
                piece = pygame.transform.smoothscale(piece, (round(width * ART), piece.get_height()))
            surface.blit(piece, (round(x * ART), self.grid_y))
        tiles = spec['tiles']
        numbers = spec['numbers']
        for cell in range(CELLS):
            state = 0
            if game.shows[cell] == RIGHT:
                state = TILE_RIGHT
            elif game.shows[cell] == WRONG:
                state = TILE_WRONG
            elif (self.cursor_shown and cell == self.cursor and game.phase == PLAY) or (game.flash[0] == cell and game.flash[1] < PRESS_MS):
                state = TILE_PRESSED
            frame = tiles['frames'][cell]
            x, y = tiles['cells'][cell][:2]
            surface.blit(self.piece(tiles['pictures'][state], frame),
                         (round((x + frame[4]) * ART), self.grid_y + round((y + frame[5]) * ART)))
            if game.shows[cell] in (BLANK, HIDDEN):
                number = numbers['frames'][cell]
                px, py = numbers['places'][cell]
                surface.blit(self.piece(numbers['picture'], number),
                             (round((px + number[4]) * ART), self.grid_y + round((py + number[5]) * ART)))
            self.draw_cell(surface, game, cell)

    def draw_cell(self, surface, game, cell):
        shown = {HIDDEN: '?', WRONG: 'X', RIGHT: game.cells[cell]}.get(game.shows[cell])
        if shown:
            self.centred(surface, 'letters', shown, self.tile_centre(cell), LETTER_SCALE)

    def draw_dealt(self, surface, game):
        """The letters in the air or landed: `bg`.d's path, half the way in a quarter of the time, three quarters in half."""
        for index, ms in enumerate(game.landing):
            cell = game.order[index]
            target = self.tile_centre(cell)
            start = (FRAME[0] // 2, BOX_Y + BANNER_HEIGHT // 2)
            into = min(1.0, ms / max(1, game.letter_ms))
            share = into * 2 if into <= 0.25 else 0.5 + (into - 0.25) if into <= 0.5 else 0.75 + (into - 0.5) / 2
            place = (round(start[0] + (target[0] - start[0]) * share), round(start[1] + (target[1] - start[1]) * share))
            self.centred(surface, 'letters', game.word[index], place, LETTER_SCALE)

    def draw_clock(self, surface, game):
        spec = self._spec()[0]['clock']
        frames = spec['frames']
        x, y = CLOCK_PLACE
        ring = frames[0]
        surface.blit(self.piece(spec['picture'], ring), (x + round(ring[4] * ART), y + round(ring[5] * ART)))
        step = game.total_ms // 8
        gone = min(8, (game.total_ms - game.clock_ms) // step)
        blink = game.clock_ms < step and game.running and (game.clock_ms // 125) % 2 == 0
        for segment in range(1, gone + 1):
            if blink and segment >= 7:
                continue
            frame = frames[segment]
            surface.blit(self.piece(spec['picture'], frame), (x + round(frame[4] * ART), y + round(frame[5] * ART)))
        seconds = (game.clock_ms + 999) // 1000 if game.running else 0  # 0:00 until the first pick starts it, and at the end
        self.centred(surface, 'text', f'{seconds // 60}:{seconds % 60:02d}', (x + 91, y + 90), ART, CLOCK_COLOUR)

    def draw_score(self, surface, game):
        spec = self._spec()[0]['score']
        frames = spec['frames']
        x, y = SCORE_PLACE
        ring = frames[0]
        surface.blit(self.piece(spec['picture'], ring), (x + round(ring[4] * ART), y + round(ring[5] * ART)))
        quarter = game.target / 4
        for index, frame in enumerate(frames[1:5]):
            if game.score >= quarter * (index + 0.5):
                surface.blit(self.piece(spec['picture'], frame), (x + round(frame[4] * ART), y + round(frame[5] * ART)))
        if game.running or game.phase == TIME_UP:               # (blank until the clock starts, as '11's)
            self.centred(surface, 'text', str(game.score), (x + 91, y + 90), ART, CLOCK_COLOUR)

    def draw_floats(self, surface, game):
        spec = self._spec()[0]
        for ms, points, cell in game.pending:
            into = 1000 - ms
            rise = round(FLOAT_RISE * min(1.0, into / FLOAT_RISE_MS))
            picture = self.image(spec['floats'][1 if points >= 100 else 0])
            size = (round(picture.get_width() * ART), round(picture.get_height() * ART))
            key = ('float', size)
            big = self._images.get(key)
            if big is None:
                big = self._images[key] = pygame.transform.smoothscale(picture, size)
            centre = self.tile_centre(cell) if cell >= 0 else (FRAME[0] // 2, BOX_Y + BANNER_HEIGHT // 2)
            into = max(0, into)
            x = max(size[0] // 2, min(FRAME[0] - size[0] // 2, centre[0]))
            y = centre[1] - rise
            surface.blit(big, big.get_rect(center=(x, y)))
            self.centred(surface, 'text', str(points), (x, y), ART, TEXT_COLOUR)

    def alpha(self, game):
        return None

    def draw(self, session):
        """The game on the canvas: HD's frame at 3:4, else the frame's shape with the game in its middle (frame_units)."""
        size = self.canvas_size()
        if self.canvas is None or self.canvas.get_size() != size:
            self.canvas = pygame.Surface(size, pygame.SRCALPHA)
        if size == FRAME:
            self.dy = 0
            self.draw_game(session, self.canvas)
            return
        self.dy = (size[1] - FRAME[1]) // 2
        self.canvas.fill((0, 0, 0, 0))
        self.draw_game(session, self.canvas.subsurface((0, self.dy, *FRAME)))

    def draw_game(self, session, surface):
        game = session.engine.shs11_memory
        text = GRID_TEXT if game.grid else self._spec()[0]['text']
        surface.fill((0, 0, 0, 0))
        self.draw_clock(surface, game)
        self.draw_score(surface, game)
        self.draw_grid(surface, game)
        if game.phase in (DEAL, LOOK):
            self.draw_dealt(surface, game)
        if game.phase == GOAL:
            self.text_box(surface, text['goal'])
        elif game.phase == CUE:
            self.text_box(surface, self.cue_line(game), game.phase_ms // CUE_LETTER_MS)
        elif game.phase == DEAL and game.tutorial:
            self.text_box(surface, text['look'])
        elif game.phase == LOOK:
            self.text_box(surface, text['look'])
        elif game.phase == SHOWN:
            self.text_box(surface, text['select'])
        elif game.phase == BAD:
            self.text_box(surface, text['careful'])
        elif game.phase == READY:
            self.text_box(surface, text['ready'])
        elif game.phase in (PLAY, NEXT) and game.word:
            self.banner(surface, game.word)
        if game.bonus_ms > 0:
            self.box(surface, BOX_Y, BANNER_HEIGHT)
            self.centred(surface, 'text', text['spelling'], (FRAME[0] // 2, BOX_Y + BANNER_HEIGHT // 2), ART, TEXT_COLOUR)
        self.draw_floats(surface, game)
        if game.phase == TIME_UP:
            self.box(surface, TIME_UP_Y, 190, x=60, width=648)
            self.centred(surface, 'letters', text['time_up'].upper(), (FRAME[0] // 2, TIME_UP_Y + 95), BANNER_SCALE)

    @staticmethod
    def cue_line(game):
        """`x`: a round's word stands out in its cue, in capitals."""
        at = game.cue.lower().find(game.word.lower())
        if at < 0:
            return game.cue
        return game.cue[:at] + game.word + game.cue[at + len(game.word):]

