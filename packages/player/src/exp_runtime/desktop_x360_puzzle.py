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
BARS = ('fill_blue', 'fill_red', 'fill_yellow', 'fill_green', 'fill_purple')    # top to bottom, as the prototype's HUD
BAR_INDEX = {'fill_red': 0, 'fill_green': 1, 'fill_blue': 2, 'fill_yellow': 3, 'fill_purple': 4}
BAR_X, BAR_Y, BAR_W, BAR_H, BAR_STEP = 34, 738, 330, 40, 27
SCORE_RIGHT, TIME_RIGHT, DIGIT_Y, DIGIT_H = 590, 740, 744, 84
COLOURS = ((255, 40, 30), (40, 230, 50), (50, 90, 255), (240, 220, 40), (220, 50, 220))  # the emitters' BirthColorEnd
GLOW_SIZE = 1.7                         # selection_00N's billboards against a cell
GLOW_PULSE_MS = 900
FADE_MS = 300
SHEEN_MS = 2400                         # the metal board's reflection crossing it
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
        """Scale some of the shine's frames while it waits to start, so play doesn't have to."""
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
        self._board(surface, spec, game)
        self._jewels(surface, spec, game)
        self._cleared(surface, game)
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
        box = spec['placed']['board']
        image = self._placed(spec['board_metal' if game.in_chain else 'board'], box)
        x, y = GRID_LEFT + round(box[0] * CELL), GRID_TOP + round(box[1] * CELL)
        surface.blit(image, (x, y))
        if game.in_chain:
            self._board_sheen(surface, image.get_rect(topleft=(x, y)), game)

    def _board_sheen(self, surface, rect, game):
        """minigame/metal's reflection, which crosses the board in the prototype."""
        if self._sheen is None or self._sheen.get_height() != rect.height:
            self._sheen = pygame.Surface((rect.width // 2, rect.height))
            width = self._sheen.get_width()
            for x in range(width):
                level = round(120 * (1 - abs(2 * x / width - 1)) ** 2)
                pygame.draw.line(self._sheen, (level, level, level), (x, 0), (x, rect.height))
        into = game.now_ms % SHEEN_MS / SHEEN_MS
        x = rect.x - self._sheen.get_width() + round(into * (rect.width + self._sheen.get_width()))
        clip = surface.get_clip()
        surface.set_clip(rect)
        surface.blit(self._sheen, (x, rect.y), special_flags=pygame.BLEND_RGB_ADD)
        surface.set_clip(clip)

    def _jewels(self, surface, spec, game):
        clip = surface.get_clip()
        surface.set_clip(pygame.Rect(GRID_LEFT, GRID_TOP, SIZE * CELL, SIZE * CELL))
        pulse = .75 + .25 * math.sin(2 * math.pi * game.now_ms / GLOW_PULSE_MS)
        for row, pieces in enumerate(game.board, 1):
            for column, piece in enumerate(pieces, 1):
                if piece['state'] == DESTROYED or piece['index'] == -1:
                    continue
                x, y = self._cell_centre(row, column)
                if piece['anim'] > 0:
                    left = piece['anim'] / max(1, piece['anim_total'])
                    x += piece['off_j'] * CELL * left
                    y += piece['off_i'] * CELL * left
                kind = str(piece['index'])
                frames = spec['jewels'][kind]
                box = spec['placed']['jewels'][kind]
                image = self._placed(frames[game.now_ms * len(frames) // spec['shine_ms'] % len(frames)], box)
                surface.blit(image, (round(x + box[0] * CELL), round(y + box[1] * CELL)))
                if piece['state'] == SELECTED:
                    glow = self._glow(piece['index'])
                    if pulse < 1:
                        glow = glow.copy()
                        level = round(255 * pulse)
                        glow.fill((level, level, level), special_flags=pygame.BLEND_RGB_MULT)
                    surface.blit(glow, glow.get_rect(center=(round(x), round(y))), special_flags=pygame.BLEND_RGB_ADD)
        surface.set_clip(clip)

    def _cleared(self, surface, game):
        """destroy_piece_00N: five sparks in the jewel's colour, thrown out and fading in half a second."""
        for i, j, kind, at in game.cleared:
            age = game.now_ms - at
            if not 0 <= age < min(PARTICLE_MS, CLEARED_MS):
                continue
            x, y = self._cell_centre(i, j)
            rng = random.Random(at * 31 + i * 7 + j)
            left = 1 - age / PARTICLE_MS
            colour = tuple(round(c * left) for c in COLOURS[kind - 1])
            for _ in range(PARTICLES):
                angle, speed = rng.uniform(0, 2 * math.pi), rng.uniform(.5, 2.2) * CELL / (PARTICLE_MS / 1000)
                seconds = age / 1000
                px = x + math.cos(angle) * speed * seconds
                py = y + math.sin(angle) * speed * seconds + 6 * CELL * seconds * seconds
                spark = pygame.Surface((26, 26))
                pygame.draw.circle(spark, colour, (13, 13), max(1, round(12 * left)))
                surface.blit(spark, (round(px) - 13, round(py) - 13), special_flags=pygame.BLEND_RGB_ADD)

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
