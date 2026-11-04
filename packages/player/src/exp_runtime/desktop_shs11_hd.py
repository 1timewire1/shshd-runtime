"""shshd-runtime: SHS '11's Memory and Reflex in the iOS HD word game's look (desktop_word_hd.py), the "Use Word Grid Skin" switch
(owner, 2026-11-04). The games play exactly as they do in '11's own look (shs11_games.py); only the drawing differs.

What each part becomes, from the art in the player's own HD bundle:
- The whole frame: the word game's scene, spinning haze, cloud edges and time and score, and the player's portrait in its ring.
- '11's grid: three rows of three of the word game's 3D cubes. A hidden cell is `?`, a right one green, a wrong one red, as the
  word game colours its start and wrong-prefix cubes. A cell changing turns over, as the word game's cubes do between boards.
- Memory's cue: the word game's question, sliding in. Its word: the orange keyword, going to the bottom left as a keyword does.
- Reflex's icons: '11's own (the addon's), since the word game has none like them, in the cube letters' blue on the cube faces,
  with their green bars. Its gauge: '11's bar and marker, between two small cube faces with its wrong and right icons.
- Points: the word game's "+N" flying to the score; a finished word or gauge throws off the word game's shards. Boxes: its tutorial
  popup. Spelling Bonus and "Time's up!": its centre banner.

Nothing in '11 or the word game says how these fit together: the arrangement is this player's.
"""
import math
from types import SimpleNamespace

import pygame

from .desktop_shs11_memory import memory_spec
from .desktop_word_hd import (ATLAS, EFFECT_SLOTS, FRAME, HEADING_LINES, HEADING_SLIDE, SHARDS, TOP_FACE, EffectState, HdWordRenderer, Shard,
                              keyword_pose, turn_ms)
from .graphics import opaque
from .hd_gl import to_pil
from .shs.grid_layout import clamp, ease
from .shs11_games import (GRID_TEXT, AGE, BAD, BARS, BARS_SHOWN, BONUS_SHOWN_MS, CUE, CUE_MS, DEAL, DELAY, ENTER, ENTER_MS, FLASH_MS_WORD, GAUGE, GOAL, HIDDEN,
                          LOOK, PENALTY, PICTURE, PLAY, READY, RIGHT, RIGHT_PICTURE, SELECT, SHOWN, SHUT_MS, SHUTTING, SKULL, SKULL_PICTURE, TIME_UP, TIME_UP_MS,
                          WRONG, WRONG_PICTURE)

BOARD = SimpleNamespace(width=3, height=3)
QUESTION_STROKE, QUESTION_EDGE = 120, 60        # how little blue is all stroke, and how much more is all fill
GRID_QUESTION, QUESTION_FONT = '\uF8FF', 'big'     # a hidden cell's face in Memory in a grid's place, and the font it comes from
ICON_BASE = 0xE000                      # a tile's "letter" that is one of Reflex's icons: + 10 x its picture + its bars
BAR_FRAMES = (14, 15, 16)
ICON_TINT = (60, 120, 225, 255)         # the cube letters' blue
ICON_HEIGHT = 382.5                     # board units, as `drawTileIcon` scales a picture tile's art
QUESTION_HEIGHT = 240                   # about the cube font's capitals
TURN_MS = 300                           # a cube turning to a new face (the word game's own take 700)
GAUGE_SCALE, GAUGE_Y = 1.25, 112        # in this frame
GAUGE_TILE = 88
POPUP_TITLES = {'shs11_memory': 'Memory', 'shs11_reflex': 'Reflex'}
MEMORY_BOXES = {GOAL: 'goal', LOOK: 'look', SHOWN: 'select', BAD: 'careful', READY: 'ready'}
REFLEX_BOXES = {GOAL: 'goal', GAUGE: 'gauge', SELECT: 'select', BARS: 'bars', PENALTY: 'penalty', SKULL: 'skull', READY: 'ready'}


class Shs11HdRenderer(HdWordRenderer):
    edge_bar = 'gear'

    def __init__(self, resources, art):
        super().__init__(resources, art)
        self.cursor = 4
        self.cursor_shown = False
        self.game = None
        self.turns = {}
        self._loaded = None
        self._pictures = {}

    def _spec(self):
        if self._loaded is None:
            self._loaded = memory_spec(self.resources)
        return self._loaded

    def available(self):
        """The player's HD bundle has the word game's art, and the library the addon's."""
        try:
            found = self._spec()
        except Exception:                               # a damaged addon: '11's own look says so
            return False
        return found is not None and found[0].get('reflex') is not None and super().available()

    def art_available(self):
        """The player's HD bundle has the word game's art, which is all Memory in a grid's place needs (it wants no addon)."""
        return HdWordRenderer.available(self)

    def alpha(self, game):
        return None

    def picture(self, resource):
        found = self._pictures.get(resource)
        if found is None:
            import io
            found = self._pictures[resource] = pygame.image.load(io.BytesIO(self._spec()[1].read(resource)), 's11.png').convert_alpha()
        return found

    # -- what a cell shows ----------------------------------------------
    def icon_tile(self, code):
        """A Reflex icon and its bars, in the sheet's own box, as a PIL image with its width in board units."""
        code -= ICON_BASE
        picture, bars = code // 10, code % 10
        spec = self._spec()[0]['reflex']['icons']
        key = ('tile', code)
        found = self._pictures.get(key)
        if found is None:
            sheet = self.picture(spec['picture'])
            box = pygame.Surface(spec['box'], pygame.SRCALPHA).convert_alpha()
            x, y, w, h, ox, oy = spec['frames'][picture][:6]
            part = sheet.subsurface((x, y, w, h)).copy()
            part.fill(ICON_TINT, special_flags=pygame.BLEND_RGBA_MULT)
            box.blit(part, (ox, oy))
            for frame in BAR_FRAMES[:bars]:
                x, y, w, h, ox, oy = spec['frames'][frame][:6]
                box.blit(sheet, (ox, oy), (x, y, w, h))
            found = self._pictures[key] = to_pil(box), box
        return found

    def question_mark(self):
        """Memory's `?`, which the cube font hasn't got: '11's letter font's, in the cube letters' blue."""
        found = self._pictures.get('?')
        if found is None:
            font = self._spec()[0]['fonts']['letters']
            x, y, w, h = font['glyphs'][str(ord('?'))][:4]
            part = self.picture(font['picture']).subsurface((x, y, w, h)).copy()
            part.fill(ICON_TINT[:3] + (0,), special_flags=pygame.BLEND_RGBA_MAX)
            part.fill(ICON_TINT, special_flags=pygame.BLEND_RGBA_MIN)
            found = self._pictures['?'] = to_pil(part)
        return found

    def grid_question_mark(self):
        """The same, for Memory in a grid's place: '11's with its addon (owner, 2026-11-04), so the addon is never needed for it, else
        the HD word game's big font's. Only that one's white fill, in the cube letters' blue: its orange stroke would make it far
        heavier than they are. Orange is low in blue, white isn't."""
        found = self._pictures.get(GRID_QUESTION)
        if found is None:
            try:
                has_addon = self._spec() is not None
            except Exception:                           # a damaged addon: as if it weren't there
                has_addon = False
            if has_addon:
                found = self._pictures[GRID_QUESTION] = self.question_mark()
                return found
            font = self.font(QUESTION_FONT)
            x, y, w = font.font.glyph('?')
            part = font.sheet.subsurface((x, y, w, font.height)).copy()
            for py in range(part.get_height()):
                for px in range(part.get_width()):
                    colour = part.get_at((px, py))
                    keep = clamp((min(colour.r, colour.g, colour.b) - QUESTION_STROKE) / QUESTION_EDGE)
                    part.set_at((px, py), (*ICON_TINT[:3], round(colour.a * keep)))
            found = self._pictures[GRID_QUESTION] = to_pil(part.subsurface(part.get_bounding_rect()).copy())
        return found

    def glyph_quad(self, char, vertex, depth, mirrored, symbols):
        if char == GRID_QUESTION:
            image, h = self.grid_question_mark(), QUESTION_HEIGHT
        elif char == '?':
            image, h = self.question_mark(), QUESTION_HEIGHT
        elif ord(char) >= ICON_BASE:
            image, h = self.icon_tile(ord(char))[0], ICON_HEIGHT
        else:
            return super().glyph_quad(char, vertex, depth, mirrored, symbols)
        w = h * image.width / image.height
        left, up = -w / 2, -h / 2
        xs = (left + w, left) if mirrored else (left, left + w)
        return image, [vertex(xs[0], up, depth), vertex(xs[1], up, depth), vertex(xs[1], up + h, depth), vertex(xs[0], up + h, depth)]

    @staticmethod
    def memory_cell(game, cell):
        """(the face's letter, the cube's colour)."""
        show = game.shows[cell]
        if show == RIGHT:
            return game.cells[cell], 2
        if show == WRONG:
            return 'X', 4
        if show == HIDDEN:
            return GRID_QUESTION if game.grid else '?', 0
        if game.phase in (DEAL, LOOK) and cell in game.order[:len(game.landing)]:
            return game.cells[cell], 0
        return '', 0

    @staticmethod
    def reflex_cell(game, cell):
        icon = game.cells[cell]
        mode = {RIGHT: 2, WRONG: 4}.get(game.shows[cell], 0)
        if not icon or icon[SHUTTING] >= 0 or icon[AGE] < icon[DELAY]:
            return '', mode
        return chr(ICON_BASE + icon[PICTURE] * 10 + icon[BARS_SHOWN]), mode

    def board_cells(self, game, reflex):
        """The cubes, each turning from what it showed when that changed."""
        for cell in range(9):
            face, mode = self.reflex_cell(game, cell) if reflex else self.memory_cell(game, cell)
            turn = self.turns.get(cell)
            if turn is None or turn[0] != face:
                turn = self.turns[cell] = [face, turn[0] if turn else '', game.visual_ms]
            length = ((SHUT_MS if not face else game.row[FLASH_MS_WORD]) if reflex else TURN_MS)
            angle = (1 - clamp(turn_ms(game.visual_ms - turn[2], cell) / length)) * 180
            self.cube(3, 3, cell % 3, cell // 3, mode, face, turn[1] if angle else '', angle=angle)

    def warm_icons(self, game):
        for row in game.rounds:
            for picture in (row[RIGHT_PICTURE], row[WRONG_PICTURE], row[SKULL_PICTURE]):
                for bars in range(len(BAR_FRAMES) + 1):
                    self.icon_tile(ICON_BASE + picture * 10 + bars)

    # -- the rest of the frame --------------------------------------------
    def hud(self, game):
        strings = self.strings()
        seconds = math.ceil(game.clock_ms / 1000)
        for text, edge, y, mono in ((strings[32], 412, 4, None), (f'{seconds:03}', 412, 44, '3'),
                                    (strings[33], 620, 4, None), (f'{game.score:05}', 620, 44, '3')):
            self.text('status', text, edge, y, right=True, monospace=mono)

    def heading(self, game):
        """The cue as the word game's question, and its word as the keyword."""
        if not game.word or game.phase == GOAL:
            return
        since = game.phase_ms if game.phase == CUE else CUE_MS
        font = self.font('status')
        for index, (line, (x, y)) in enumerate(zip(font.wrap(self.cue_line(game), 768 - 2 * 250)[:3], HEADING_LINES)):
            x += int((1 - ease(since / 1800 + (2 - index) * .1, 0, .9, .85)) * HEADING_SLIDE)
            self.text('status', line, x, y)
        big = self.font('big')
        pose = keyword_pose(since / CUE_MS, 0, big.width(game.word), 1, big.height)
        if pose is not None:
            self.scaled_text('big', game.word, *pose, 1.)

    @staticmethod
    def cue_line(game):
        return game.cue

    def gauge_tile(self, frame_top, picture, centre):
        key = ('gauge', frame_top, picture)
        found = self._pictures.get(key)
        if found is None:
            face = pygame.transform.smoothscale(self.atlas(ATLAS).frame(frame_top), (GAUGE_TILE, GAUGE_TILE))
            box = self.icon_tile(ICON_BASE + picture * 10)[1]
            height = round(GAUGE_TILE * .85)
            icon = pygame.transform.smoothscale(box, (round(height * box.get_width() / box.get_height()), height))
            face.blit(icon, icon.get_rect(center=face.get_rect().center))
            found = self._pictures[key] = face
        self.canvas.blit(found, found.get_rect(center=centre))

    def draw_gauge(self, game):
        spec = self._spec()[0]['reflex']
        marker, bar = spec['marker'], spec['bar']
        scale = GAUGE_SCALE
        span = (marker['travel'] + 43) * scale
        left, top = (FRAME[0] - span) / 2, GAUGE_Y
        drop = 0
        if game.phase == ENTER:
            drop = round((max(0, game.phase_ms) / ENTER_MS) ** 2 * (top + GAUGE_TILE))
        picture = self.picture(bar['picture'])
        key = ('bar', scale)
        found = self._pictures.get(key)
        if found is None:
            found = self._pictures[key] = pygame.transform.smoothscale(picture, (round(picture.get_width() * scale), round(picture.get_height() * scale)))
        bar_top = top + round((bar['place'][1] - marker['place'][1]) * scale)
        self.canvas.blit(found, (round(left + (bar['place'][0] - marker['place'][0]) * scale), bar_top))
        picture = self.picture(marker['pictures'][game.marker_look])
        key = ('marker', game.marker_look, scale)
        found = self._pictures.get(key)
        if found is None:
            found = self._pictures[key] = pygame.transform.smoothscale(picture, (round(picture.get_width() * scale), round(picture.get_height() * scale)))
        self.canvas.blit(found, (round(left + marker['travel'] * scale * game.marker_at / 1000), top))
        middle = top + round(found.get_height() * .62)
        self.gauge_tile(TOP_FACE[4], game.row[WRONG_PICTURE], (round(left - GAUGE_TILE / 2 - 6), middle - drop))
        self.gauge_tile(TOP_FACE[2], game.row[RIGHT_PICTURE], (round(left + span + GAUGE_TILE / 2 + 6), middle - drop))

    def floats(self, game):
        """The word game's "+N": it waits over its cell, then flies to the score as it arrives."""
        for ms, points, cell in game.pending:
            x, y = self.cell_center(BOARD, cell) if cell >= 0 else (384, 512)
            if ms < 400:
                f = ease(1 - ms / 400)
                x, y = x + (520 - x) * f, y + (84 - y) * f
            self.text('status', f'+{points}', x, y)

    def shards(self, game, reflex):
        state = self._effects
        if state is None or state.game is not game:
            state = self._effects = EffectState(game)
            state.done = False
        dt = min(250, game.visual_ms - state.last)
        state.last = game.visual_ms
        done = game.full if reflex else bool(game.word) and game.found >= len(game.word)
        if done and not state.done:
            cells = [game.flash[0]] if reflex else game.order
            for x, y in (self.cell_center(BOARD, cell) for cell in cells[-EFFECT_SLOTS:]):
                scale = 1 + (y - 300) * .00110497
                for _ in range(SHARDS):
                    state.shards.append(Shard(x + state.rng.randrange(50), y + state.rng.randrange(50), scale, state.rng.randrange(250),
                                              state.rng.randrange(350) - 250, state.rng.randrange(360), state.rng.randrange(360),
                                              state.rng.randrange(5000)))
        state.done = done
        state.score = state.shown = game.score
        state.tick(dt)
        self.draw_effects(state)

    def box(self, title, text):
        """The word game's tutorial popup, where its `bottom` place leaves the board and what's over it in sight."""
        surface, text_height = self.popup(title, text)
        centre = 1024 - ((text_height + 40) / 2 + 60)
        self.canvas.blit(surface, (round(384 - self.POPUP_WIDTH / 2), round(centre - surface.get_height() / 2)))

    def banner_text(self, text, age, length):
        scale = clamp(age / 200)
        alpha = scale if age < 200 else clamp(1 - (age / length - .6) / .4)
        self.scaled_text('big', text, 384, 512, scale, alpha)

    def cell_at(self, x, y):
        return self.hit((x, y), SimpleNamespace(problem=BOARD, selection=()))

    # -- frame ------------------------------------------------------------
    def draw(self, session):
        name = session.pending.name
        reflex = name == 'shs11_reflex'
        game = session.engine.shs11_reflex if reflex else session.engine.shs11_memory
        if self.game is not game:
            self.game, self.turns, self._effects = game, {}, None
            if reflex:                          # now, not in the middle of its first set
                self.warm_icons(game)
        spec = None if not reflex and game.grid else self._spec()[0]
        texts = GRID_TEXT if spec is None else spec['text']
        self.backdrop(game, session.pending.details.get('background_id', session.engine.panel.background_id))
        self.portraits(session, game)
        self.hud(game)
        if reflex and game.row and game.phase != GOAL:
            self.draw_gauge(game)
        self.board_cells(game, reflex)
        if not reflex:
            self.heading(game)                  # over the board: the keyword crosses it on its way to the corner
        if self.cursor_shown and game.phase == PLAY:
            self.cursor_outline(BOARD)
        self.shards(game, reflex)
        self.floats(game)
        if not reflex and game.bonus_ms > 0:
            self.banner_text(texts['spelling'], BONUS_SHOWN_MS - game.bonus_ms, BONUS_SHOWN_MS)
        if reflex:
            key = REFLEX_BOXES.get(game.phase) if game.tutorial and game.wait_ms <= 0 else None
            if key is not None:
                self.box(POPUP_TITLES[name], spec['reflex']['text'][key])
        else:
            key = MEMORY_BOXES.get(game.phase) if game.tutorial or game.phase == GOAL else None
            if game.tutorial and game.phase == DEAL:
                key = 'look'
            if key is not None:
                self.box(POPUP_TITLES[name], texts[key])
        if game.phase == TIME_UP:
            self.banner_text(self.strings()[57], TIME_UP_MS - game.phase_ms, TIME_UP_MS)
        opaque(self.canvas)

