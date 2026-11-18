"""shshd-runtime: the X360 translations' jewel puzzle drawn over the story's scene (x360_puzzle.JewelPuzzle), with the art
of the X360 addon's skin (spec `puzzle`; tools/translate/x360_arena_art.py).

Straight down on the board (owner, 2026-11-01), where the prototype looks across it. The jewels, cursor and board are the
prototype's, shot from above in Xenia; the board fills the top of the 3:4 frame, with the bars, score and clock under it.
The selected and clearing effects, particles in the prototype, are drawn here in their colours and times. Nothing here
decides anything in the game."""
import math
import random

from . import graphics as pygame
from .desktop_x360_slot import FRAME, X360SlotRenderer
from .x360_games import CLOSING, OPENING, OPENING_MS, READY, TIME_UP
from .x360_puzzle import CLOSING_MS, CLEARED_MS, DESTROYED, SELECTED, SHOWING_SCORE, SIZE

CELL = 84                               # a cell on the frame
GRID_LEFT, GRID_TOP = (FRAME[0] - SIZE * CELL) // 2, 44
GRID = pygame.Rect(GRID_LEFT, GRID_TOP, SIZE * CELL, SIZE * CELL)
BARS = ('fill_blue', 'fill_red', 'fill_yellow', 'fill_green', 'fill_purple')    # top to bottom, as the prototype's HUD
BAR_INDEX = {'fill_red': 0, 'fill_green': 1, 'fill_blue': 2, 'fill_yellow': 3, 'fill_purple': 4}
BAR_X, BAR_Y, BAR_W, BAR_H, BAR_STEP = 34, 738, 330, 40, 27
SCORE_RIGHT, TIME_RIGHT, DIGIT_Y, DIGIT_H = 590, 740, 744, 84
COLOURS = ((255, 40, 30), (40, 230, 50), (50, 90, 255), (240, 220, 40), (220, 50, 220))  # the emitters' BirthColorEnd
GLOW_SIZE = 1.7                         # selection_00N's billboards against a cell
GLOW_PULSE_MS = 900
GLOW_STEP = 4                           # the pulse's brightness steps, each glow made once (_glow_at)
SPARK_STEP_MS = 10                      # a spark's fading steps, each drawn once (_spark): under a frame
FADE_MS = 300
SHEEN_MS = 2400                         # the metal board's reflection crossing it
SHEEN_RIM_STEP = 8                      # its steps on the board's rim, each drawn once (_sheen_rim): ~7 px a frame anyway
HINT_TEXT, START_TEXT = 'Slide the rows to join 4 or more!', 'Press OK to start'
TIME_UP_TEXT, CONTINUE_TEXT = "Time's Up!", 'Press OK to continue'
PARTICLES = 5                           # destroy_piece_00N
PARTICLE_MS = 500
WARM_FRAMES = 12                        # shine frames scaled each frame while it waits to start


def cell_at(x, y):
    """The cell (i, j) under (x, y) in frame units, which may be off the board: a drag keeps its nearest."""
    return math.floor((y - GRID_TOP) / CELL) + 1, math.floor((x - GRID_LEFT) / CELL) + 1


def on_board(x, y):
    return GRID_LEFT <= x < GRID_LEFT + SIZE * CELL and GRID_TOP <= y < GRID_TOP + SIZE * CELL


class X360PuzzleRenderer(X360SlotRenderer):
    def __init__(self, resources):
        super().__init__(resources)
        self._glows = {}
        self._sheen = None
        self._layer = None                              # the grid's opaque layer (_grid_layer)
        self._kept = set()                              # the board pictures read once (_board)
        self._rim_board, self._rim_cache = None, {}     # the sheen's rim strips, by (strip, step) (_sheen_rim)
        self._rim_todo = None                           # the strips _warm_rim has yet to draw
        self._glow_levels = {}                          # (kind, level): the glow at a pulse's step (_glow_at)
        self._sparks = {}                               # (kind, age step): a spark (_spark)
        self._veil = None
        self._digits = {}

    def alpha(self, game):
        """The game's fade as it opens and closes (None: whole)."""
        if game.phase == OPENING:
            return min(1.0, max(0.0, 1 - game.phase_ms / min(FADE_MS, OPENING_MS)))
        if game.phase == CLOSING:
            return max(0.0, game.phase_ms / CLOSING_MS)
        return None

    def _placed(self, resource, box):
        """A picture at the frame's scale for `box`, in cell units around its place."""
        key = ('puzzle', resource)
        found = self._scaled.get(key)
        if found is None:
            import io
            size = (max(1, round((box[2] - box[0]) * CELL)), max(1, round((box[3] - box[1]) * CELL)))
            # (Only the scaled copy is kept: there are 300 frames of shine.)
            source = pygame.image.load(io.BytesIO(self._spec()[1].read(resource)), 'x360.png').convert_alpha()
            found = self._scaled[key] = pygame.transform.smoothscale(source, size)
        return found

    def _warm(self, spec):
        """Scale some of the shine's frames while it waits to start, so play doesn't have to; first the chain's metal
        board, drawn in a phone's Python once (its first chain had a 234 ms frame on the iPad, 2026-11-18)."""
        for name in ('board', 'board_metal'):
            if spec[name] not in self._kept:
                self._kept_board(spec[name], spec['placed']['board'])
                return
        placed = spec['placed']['jewels']
        left = WARM_FRAMES
        for kind, frames in spec['jewels'].items():
            for resource in frames:
                if ('puzzle', resource) not in self._scaled:
                    self._placed(resource, placed[kind])
                    left -= 1
                    if not left:
                        return

    def _glow(self, kind):
        """The selected jewel's soft light, in its colour: premultiplied on black, for adding."""
        found = self._glows.get(kind)
        if found is None:
            size = round(CELL * GLOW_SIZE)
            found = pygame.Surface((size, size))
            colour = COLOURS[kind - 1]
            for step in range(size // 2, 0, -1):
                strength = (1 - step / (size / 2)) ** 1.5
                pygame.draw.circle(found, tuple(round(c * strength) for c in colour), (size // 2, size // 2), step)
            self._glows[kind] = found
        return found

    def draw(self, session):
        game = session.engine.x360_puzzle
        specs = self._spec()[0]
        spec = specs['puzzle']
        surface = self.fresh_canvas()
        surface.fill((0, 0, 0, 0))
        if game.phase in (OPENING, READY):
            self._warm(spec)
        elif not game.in_chain and pygame.native() and game.phase not in (TIME_UP, SHOWING_SCORE, CLOSING):
            self._warm_rim(spec)
        # The board's grid is drawn on a layer of its own, opaque as the board is there, so the effects added into it
        # (the clearing jewels' glow, their sparks, the metal board's sheen) are the host's own additive blend on a
        # phone. Added into the see-through canvas they were each worked out in Python and sent as a new picture every
        # frame: a chain took 2.8 s a frame through the iOS backend on a PC (owner, 2026-11-18: "really bad" on the
        # iPad). The board's rim around the grid, partly see-through, still takes the effects on the canvas.
        image, rect = self._board(surface, spec, game)
        layer = self._grid_layer(image, rect)
        sheen = self._board_sheen(rect, game) if game.in_chain else None
        if sheen is not None:
            self._add(layer, *sheen, rect)
        self._jewels(layer, spec, game)
        sparks = self._cleared(game)                    # (picture, where on the frame): added in the layer and the rim
        for picture, at in sparks:
            self._add(layer, picture, at, rect)
        surface.blit(layer, GRID.topleft)
        if sheen is not None and pygame.native():
            self._sheen_rim(surface, image, rect, *sheen)
        elif sheen is not None:                         # (SDL's add, in C: as cheap on the rim as anywhere)
            self._add_rim(surface, *sheen, rect)
        for picture, at in sparks:
            self._add_rim(surface, picture, at, rect)
        if game.phase != TIME_UP and game.phase != SHOWING_SCORE and game.phase != OPENING:
            box = spec['placed']['cursor']
            x, y = self._cell_centre(game.cursor_i, game.cursor_j)
            surface.blit(self._placed(spec['cursor'], box), (round(x + box[0] * CELL), round(y + box[1] * CELL)))
        self._bars(surface, specs, spec, game)
        self._numbers(surface, specs, game)
        words = specs['slot']
        if game.phase == READY:
            self._lines(surface, words, ((HINT_TEXT, 330, 40), (START_TEXT, 410, 56)))
        elif game.phase == TIME_UP:
            self._lines(surface, words, ((TIME_UP_TEXT, 380, 80),), veil=False)     # (the board is still clearing)
        elif game.phase == SHOWING_SCORE or game.phase == CLOSING:
            self._lines(surface, words, ((f'Your score: {game.score}', 340, 64), (CONTINUE_TEXT, 430, 44)))

    @staticmethod
    def _cell_centre(i, j):
        return GRID_LEFT + (j - .5) * CELL, GRID_TOP + (i - .5) * CELL

    def _board(self, surface, spec, game):
        """The board's picture on the canvas: (the picture, its rect on the frame)."""
        box = spec['placed']['board']
        image = self._kept_board(spec['board_metal' if game.in_chain else 'board'], box)
        x, y = GRID_LEFT + round(box[0] * CELL), GRID_TOP + round(box[1] * CELL)
        surface.blit(image, (x, y))
        return image, image.get_rect(topleft=(x, y))

    def _kept_board(self, resource, box):
        """A board's picture, kept drawn. A phone's backend draws the rim's effects in Python over the board, which drew
        its scaled picture again each time (689 x 687, past what it keeps): a pixel read keeps it (drawing.get_at)."""
        image = self._placed(resource, box)
        if resource not in self._kept:
            image.get_at((0, 0))
            self._kept.add(resource)
        return image

    def _grid_layer(self, image, rect):
        """The grid's square of the board on an opaque layer, kept between frames. The board's art is opaque over the
        grid (desktop pygame's smoothscale leaves it 251-253 there, a rounding of the shrink: 255 here, as the art)."""
        if self._layer is None:
            self._layer = pygame.Surface(GRID.size)
        self._layer.fill((0, 0, 0))
        self._layer.blit(image, (rect.x - GRID.x, rect.y - GRID.y))
        return self._layer

    @staticmethod
    def _add(layer, picture, at, board):
        """An effect added into the grid's layer (the board covers it all, so the layer's own edges are the clip)."""
        layer.blit(picture, (at[0] - GRID.x, at[1] - GRID.y), special_flags=pygame.BLEND_RGB_ADD)

    @staticmethod
    def _rim(board):
        """The board's rim around the grid, as four strips: top, bottom, left, right."""
        return (pygame.Rect(board.x, board.y, board.width, GRID.y - board.y),
                pygame.Rect(board.x, GRID.bottom, board.width, board.bottom - GRID.bottom),
                pygame.Rect(board.x, GRID.y, GRID.x - board.x, GRID.height),
                pygame.Rect(GRID.right, GRID.y, board.right - GRID.right, GRID.height))

    def _add_rim(self, surface, picture, at, board):
        """An effect's part on the board's rim around the grid, added into the canvas as before (only the board takes
        it: SDL's add leaves the canvas's clear pixels clear). Most sparks don't reach it."""
        reach = pygame.Rect(at, picture.get_size()).clip(board)
        if not reach.width or not reach.height or GRID.contains(reach):
            return
        clip = surface.get_clip()
        for strip in self._rim(board):
            part = strip.clip(reach)
            if part.width and part.height:
                surface.set_clip(part)
                surface.blit(picture, at, special_flags=pygame.BLEND_RGB_ADD)
        surface.set_clip(clip)

    def _sheen_picture(self, rect):
        if self._sheen is None or self._sheen.get_height() != rect.height:
            self._sheen = pygame.Surface((rect.width // 2, rect.height))
            width = self._sheen.get_width()
            for x in range(width):
                level = round(120 * (1 - abs(2 * x / width - 1)) ** 2)
                pygame.draw.line(self._sheen, (level, level, level), (x, 0), (x, rect.height))
        return self._sheen

    def _board_sheen(self, rect, game):
        """minigame/metal's reflection, which crosses the board in the prototype: (its picture, where)."""
        self._sheen_picture(rect)
        into = game.now_ms % SHEEN_MS / SHEEN_MS
        x = rect.x - self._sheen.get_width() + round(into * (rect.width + self._sheen.get_width()))
        return self._sheen, (x, rect.y)

    def _sheen_rim(self, surface, image, board, sheen, at):
        """iOS's backend: the sheen on the board's rim. Each strip it reaches is the rim's own pixels with the sheen
        added, worked out once for each SHEEN_RIM_STEP of its way across and put in the strip's place (over cleared
        pixels that backend's blit is a copy; SDL's would darken the rim's see-through edge, so pygame adds directly).
        The rim is partly see-through, so the backend's add is Python's: done every frame, it was most of a chain's
        frame on the iPad (2026-11-18). The sheen is the same all the way down: a strip depends on how far across."""
        step = board.x + round((at[0] - board.x) / SHEEN_RIM_STEP) * SHEEN_RIM_STEP
        for index, strip in self._sheen_strips(board, sheen, step):
            surface.fill((0, 0, 0, 0), strip)
            surface.blit(self._sheen_piece(image, board, sheen, index, strip, step), strip.topleft)

    def _sheen_strips(self, board, sheen, step):
        """(index, strip) of the rim's strips the sheen reaches at `step` (the others keep the board's own rim)."""
        reach = pygame.Rect(step, board.y, sheen.get_width(), board.height).clip(board)
        return [(index, strip) for index, strip in enumerate(self._rim(board)) if strip.colliderect(reach)]

    def _sheen_piece(self, image, board, sheen, index, strip, step):
        if self._rim_board is not image:                # (the strips are this picture's)
            self._rim_board, self._rim_cache, self._rim_todo = image, {}, None
        key = index, step
        piece = self._rim_cache.get(key)
        if piece is None:
            piece = pygame.Surface(strip.size, pygame.SRCALPHA)
            piece.fill((0, 0, 0, 0))
            piece.blit(image, (board.x - strip.x, board.y - strip.y))
            piece.blit(sheen, (step - strip.x, board.y - strip.y), special_flags=pygame.BLEND_RGB_ADD)
            self._rim_cache[key] = piece
        return piece

    def _warm_rim(self, spec):
        """iOS's backend: one more of the sheen's rim strips a frame while the board isn't in a chain, so that its
        first sweep needn't work them out as it goes (about 4 s of play for them all)."""
        box = spec['placed']['board']
        image = self._kept_board(spec['board_metal'], box)
        board = image.get_rect(topleft=(GRID_LEFT + round(box[0] * CELL), GRID_TOP + round(box[1] * CELL)))
        sheen = self._sheen_picture(board)
        if self._rim_board is not image:
            self._rim_board, self._rim_cache, self._rim_todo = image, {}, None
        if self._rim_todo is None:
            # (every step the sheen's left edge takes, from a sheen's width before the board to its far side)
            self._rim_todo = [(index, strip, board.x + k * SHEEN_RIM_STEP)
                              for k in range(-(sheen.get_width() // SHEEN_RIM_STEP) - 2, board.width // SHEEN_RIM_STEP + 2)
                              for index, strip in self._sheen_strips(board, sheen, board.x + k * SHEEN_RIM_STEP)]
        while self._rim_todo:
            index, strip, step = self._rim_todo.pop()
            if (index, step) not in self._rim_cache:
                self._sheen_piece(image, board, sheen, index, strip, step)
                return

    def _jewels(self, layer, spec, game):
        """The jewels and the clearing ones' glow, on the grid's layer (which is the grid's clip)."""
        pulse = .75 + .25 * math.sin(2 * math.pi * game.now_ms / GLOW_PULSE_MS)
        for row, pieces in enumerate(game.board, 1):
            for column, piece in enumerate(pieces, 1):
                if piece['state'] == DESTROYED or piece['index'] == -1:
                    continue
                x, y = self._cell_centre(row, column)
                x, y = x - GRID.x, y - GRID.y
                if piece['anim'] > 0:
                    left = piece['anim'] / max(1, piece['anim_total'])
                    x += piece['off_j'] * CELL * left
                    y += piece['off_i'] * CELL * left
                kind = str(piece['index'])
                frames = spec['jewels'][kind]
                box = spec['placed']['jewels'][kind]
                image = self._placed(frames[game.now_ms * len(frames) // spec['shine_ms'] % len(frames)], box)
                layer.blit(image, (round(x + box[0] * CELL), round(y + box[1] * CELL)))
                if piece['state'] == SELECTED:
                    glow = self._glow_at(piece['index'], pulse)
                    layer.blit(glow, glow.get_rect(center=(round(x), round(y))), special_flags=pygame.BLEND_RGB_ADD)

    def _glow_at(self, kind, pulse):
        """The glow at its pulse's brightness, in steps of GLOW_STEP, each made once: a copy darkened every frame for
        each clearing jewel was a new picture a frame for a phone's host to draw (2026-11-18)."""
        level = min(255, GLOW_STEP * round(255 * pulse / GLOW_STEP))
        if level >= 255:
            return self._glow(kind)
        key = kind, level
        found = self._glow_levels.get(key)
        if found is None:
            found = self._glow(kind).copy()
            found.fill((level, level, level), special_flags=pygame.BLEND_RGB_MULT)
            self._glow_levels[key] = found
        return found

    def _spark(self, kind, age):
        """A spark of `kind` `age` ms after its jewel cleared, in steps of SPARK_STEP_MS, each drawn once (as the glow)."""
        age -= age % SPARK_STEP_MS
        key = kind, age
        found = self._sparks.get(key)
        if found is None:
            left = 1 - age / PARTICLE_MS
            found = pygame.Surface((26, 26))
            pygame.draw.circle(found, tuple(round(c * left) for c in COLOURS[kind - 1]), (13, 13), max(1, round(12 * left)))
            self._sparks[key] = found
        return found

    def _cleared(self, game):
        """destroy_piece_00N: five sparks in the jewel's colour, thrown out and fading in half a second, as
        [(picture, where on the frame)]."""
        sparks = []
        for i, j, kind, at in game.cleared:
            age = game.now_ms - at
            if not 0 <= age < min(PARTICLE_MS, CLEARED_MS):
                continue
            x, y = self._cell_centre(i, j)
            rng = random.Random(at * 31 + i * 7 + j)
            spark = self._spark(kind, age)
            for _ in range(PARTICLES):
                angle, speed = rng.uniform(0, 2 * math.pi), rng.uniform(.5, 2.2) * CELL / (PARTICLE_MS / 1000)
                seconds = age / 1000
                px = x + math.cos(angle) * speed * seconds
                py = y + math.sin(angle) * speed * seconds + 6 * CELL * seconds * seconds
                sparks.append((spark, (round(px) - 13, round(py) - 13)))
        return sparks

    def _bars(self, surface, specs, spec, game):
        pictures = specs['pictures']
        frame = self.scaled(pictures['power_bar'], (BAR_W, BAR_H))
        for row, name in enumerate(BARS):
            y = BAR_Y + row * BAR_STEP
            surface.blit(frame, (BAR_X, y))
            value = game.bars[BAR_INDEX[name]]
            if value:
                resource = spec.get(name) or pictures[f'power_{name}']
                fill = self.scaled(resource, (BAR_W, BAR_H))
                surface.blit(fill, (BAR_X, y), pygame.Rect(0, 0, round(BAR_W * value / 100), BAR_H))

    def _digit(self, specs, slot, n):
        key = (slot, n)
        found = self._digits.get(key)
        if found is None:
            digits = specs['booth']['digits']
            ax, ay, aw, ah = digits['slots'][slot][n]['rect']
            cell = self.image(digits['atlas']).subsurface(pygame.Rect(ax, ay, aw, ah))
            found = self._digits[key] = pygame.transform.smoothscale(cell, (max(1, round(aw * DIGIT_H / ah)), DIGIT_H))
        return found

    def _numbers(self, surface, specs, game):
        """The score's six digits and the clock's two, the prototype's own models (its map never shows them)."""
        digits = specs['booth']['digits']
        for right, slots, text in ((SCORE_RIGHT, digits['score'], f'{min(game.score, 999999):06d}'),
                                   (TIME_RIGHT, digits['time'], f'{max(0, game.total_time):02d}')):
            images = [self._digit(specs, slot, int(ch)) for slot, ch in zip(slots, text)]
            step = min((right - (BAR_X + BAR_W + 8 if right == SCORE_RIGHT else SCORE_RIGHT + 14)) / len(images),
                       max(image.get_width() for image in images))
            x = right - step * len(images)
            for image in images:
                surface.blit(image, (round(x + (step - image.get_width()) / 2), DIGIT_Y))
                x += step

    def _lines(self, surface, words, lines, veil=True):
        if self._veil is None:
            self._veil = pygame.Surface((SIZE * CELL, SIZE * CELL), pygame.SRCALPHA)
            self._veil.fill((0, 0, 0, 150))
        if veil:
            surface.blit(self._veil, (GRID_LEFT, GRID_TOP))
        for text, y, height in lines:
            line = self.text(words, text, height)
            surface.blit(line, line.get_rect(center=(FRAME[0] // 2, y)))
