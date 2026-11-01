"""shshd-runtime: the cancelled Xbox 360 game's jewel puzzle, as translated stories call it (service X360_PUZZLE behind
service 70 selector X360_MINIGAMES_QUERY; other players go on without it).

MS4's data/scripts/minigames/puzzlegame (game, grid and piece; MS3's is an earlier game that clears nothing), line for line
where a line decides anything. An 8 x 8 board of five jewels. The cursor steps a cell at a time; with the button held it
drags its row or column along, wrapping round. Four or more joined are selected and go after 3 s, or 1 s during a chain,
unless a move breaks the group first. The jewels above fall in, new ones come in from the top, and that starts a chain for
2 s. +1 a jewel, +3 during a chain; 60 s.

Changes from MS4 (owner, 2026-11-01), which leaves the game unfinished:
- It waits behind a press to start, where MS4 waits 3 s.
- At the end it says Time's Up! and shows the score, then goes on. MS4 just stops taking input.
- Sounds, which MS4's scripts never play: a drag plays fx/move.wav and a clearing fx/move3.wav, both unused in MS4.
- A mouse or finger can grab any jewel and drag (grab, drag, let_go), and a hovering mouse can point the cursor.
"""
from dataclasses import dataclass, field

from .x360_games import CLOSING, OPENING, OPENING_MS, READY, RUNNING, TIME_UP

X360_PUZZLE = 216
SIZE = 8
KINDS = 5
GROUP = 4                               # Grid:SelectPieces (its comment says 3)
SECONDS_TO_DIE = 3
SECONDS_TO_DIE_IN_CHAIN = 1
CHAIN_SECONDS = 2                       # TIMER_INCHAIN
SECONDS = 60                            # totalTime
MOVE_MS = 70                            # MOVEMENT_VEL: a step's pause, and a dragged jewel's slide
FALL_WAIT_MS = 200                      # Grid:Step's Wait(0.2)
FALL_MS = 140                           # movementVel * 2
SCORE, SCORE_IN_CHAIN = 1, 3
BAR_MAX = 100                           # minigame/puzzle/*bar's Range
UP, DOWN, LEFT, RIGHT = 'up', 'down', 'left', 'right'
SHOWING_SCORE = 'score'
TIME_UP_MS = 2500
CLOSING_MS = 300
CLEARED_MS = 700                        # how long a clearing's effect is kept for the renderer
# The sounds, in the X360 addon (tools/translate/x360_arena_art.py PUZZLE_SOUNDS).
SOUND_DRAG, SOUND_CLEAR = 26441, 26442
NORMAL, SELECTED, DESTROYED = 0, 1, 2   # Piece.State


def _jewel():
    return dict(index=-1, state=NORMAL, prev=0, own=0, i=0, j=0, off_i=0, off_j=0, anim=0, anim_total=1)


@dataclass
class JewelPuzzle:
    board: list = field(default_factory=list)       # Grid.Matrix, [i - 1][j - 1] (row 1 at the top): the jewels
    pieces: list = field(default_factory=list)      # Grid.Pieces, [index - 1]: each kind's [i, j], in Lua's order
    phase: str = OPENING
    phase_ms: int = OPENING_MS
    started: bool = False
    now_ms: int = 0                                 # GetGameTotalTime
    cursor_i: int = 8                               # currentCursorPosI
    cursor_j: int = 1                               # currentCursorPosJ
    button: bool = False                            # ButtonPressed
    moving_ms: int = 0                              # movingPiece: what's left of the step's Wait
    falling: list = field(default_factory=lambda: [0] * SIZE)   # Grid.fallingPieces: by column, the lowest row cleared
    check_falling: bool = False                     # checkFallingPieces
    fall_wait_ms: int = 0
    in_chain: bool = False                          # isInChain
    chain_time: int = 0
    prev_chain_ms: int = 0
    total_time: int = SECONDS
    prev_total_ms: int = 0
    score: int = 0
    bars: list = field(default_factory=lambda: [0] * KINDS)     # the progress bars, by index; nothing reads them
    target: list | None = None                      # where a held mouse or finger is, as [i, j]
    lock: str = ''                                  # 'row' or 'col': the way that drag first went
    cleared: list = field(default_factory=list)     # [i, j, index, now_ms] of the latest clearings, for the renderer
    sounds: list = field(default_factory=list)      # waiting for the session to play

    @classmethod
    def dealt(cls, random):
        """Grid:Init."""
        game = cls(pieces=[[] for _ in range(KINDS)])
        game.board = [[_jewel() for _ in range(SIZE)] for _ in range(SIZE)]
        for i in range(1, SIZE + 1):
            for j in range(1, SIZE + 1):
                game._init_piece(game._at(i, j), i, j, random)
        return game

    @property
    def result(self):
        return self.score

    def _at(self, i, j):
        return self.board[i - 1][j - 1]

    # -- the board ---------------------------------------------------------------------------------------------------
    def _init_piece(self, piece, i, j, random):
        """Piece:Init."""
        kind = 1 + random.below(KINDS)
        while not self._could_use(kind, i, j):
            kind += 1
            if kind > KINDS:
                kind = 1
        piece.update(index=kind, i=i, j=j, state=NORMAL)

    def _could_use(self, number, i, j):
        """Grid:CouldUseThis."""
        kind = self.pieces[number - 1]
        if kind and not self._check_chain(number, i, j, 2):
            return False
        kind.append([i, j])
        return True

    def _check_chain(self, number, i, j, top, level=1):
        """Grid:CheckChain: whether a jewel here would stay within two joined."""
        result, found = True, False
        for e in self.pieces[number - 1]:
            if e[0] == i - 1 and e[1] == j:
                if level == top:
                    return False
                found = True
                result = self._check_chain(number, i - 1, j, top, level + 1)
            for near_i, near_j in ((i + 1, j), (i, j - 1), (i, j + 1)):
                if e[0] == near_i and e[1] == near_j:
                    if level == top or found:
                        return False
                    found = True
                    result = self._check_chain(number, near_i, near_j, top, level + 1)
        return result

    def _relocate(self, number, old_i, old_j, new_i, new_j):
        """Grid:ChangePiecePosition."""
        if number == -1:
            return
        for p in self.pieces[number - 1]:
            if p[0] == old_i and p[1] == old_j:
                piece = self._at(old_i, old_j)
                piece['i'], piece['j'] = new_i, new_j
                p[0], p[1] = new_i, new_j
                return

    def check_pieces(self):
        """Grid:CheckPieces, LookForNeighbors and LookIntoArray: each kind's groups, as their loops build them. (The first
        of a group the scan meets reaches all the rest, so its "joins every list" branch never runs; kept as written.)"""
        for piece in self.pieces:
            groups, real = [], 0
            for n, cell in enumerate(piece):
                found = False
                for g, group in enumerate(groups):
                    for e in group:
                        if e[0] == cell[0] and e[1] == cell[1]:     # already in a list
                            found, real = True, g
                            break
                if not found:
                    for g, group in enumerate(groups):              # a neighbour's list: every one that has a neighbour
                        for e in group:
                            if abs(e[0] - cell[0]) + abs(e[1] - cell[1]) == 1:
                                real, found = g, True
                                group.append(cell)
                                break
                if not found:
                    real = len(groups)
                    groups.append([cell])
                self._look_for_neighbours(n, piece, cell, groups, real)
            self._select(groups)

    def _look_for_neighbours(self, n, cells, cell, groups, real):
        for other in cells[n + 1:]:
            if (other[1] == cell[1] and abs(other[0] - cell[0]) == 1) or (other[0] == cell[0] and abs(other[1] - cell[1]) == 1):
                if not any(e[0] == other[0] and e[1] == other[1] for group in groups for e in group):
                    groups[real].append(other)
                    self._look_for_neighbours(n, cells, other, groups, real)

    def _select(self, groups):
        """Grid:SelectPieces, the oldest time shared as its loop shares it."""
        for group in groups:
            if len(group) >= GROUP:
                best_time, best_own = -1, -1
                for i, j in group:
                    piece = self._at(i, j)
                    if piece['state'] == NORMAL:
                        piece['state'], piece['prev'] = SELECTED, self.now_ms      # Piece:Select
                    if piece['own'] >= best_own and piece['prev'] >= best_time:
                        best_time, best_own = piece['prev'], piece['own']
                    else:
                        piece['prev'], piece['own'] = best_time, best_own
            else:
                for i, j in group:
                    piece = self._at(i, j)
                    if piece['state'] == SELECTED:
                        piece['state'], piece['own'] = NORMAL, 0                    # Piece:UnSelect

    def _step_piece(self, piece):
        """Piece:Step. True if it went."""
        if piece['state'] != SELECTED:
            return False
        if self.now_ms - piece['prev'] >= 1000:
            piece['own'] += 1
            piece['prev'] = self.now_ms
        if piece['own'] < (SECONDS_TO_DIE_IN_CHAIN if self.in_chain else SECONDS_TO_DIE):
            return False
        self.score += SCORE_IN_CHAIN if self.in_chain else SCORE
        kind = piece['index']
        self.bars[kind - 1] = min(BAR_MAX, self.bars[kind - 1] + 1)
        piece['state'], piece['own'] = DESTROYED, 0
        cells = self.pieces[kind - 1]
        for n, p in enumerate(cells):
            if p[0] == piece['i'] and p[1] == piece['j']:
                del cells[n]
                break
        self.cleared.append([piece['i'], piece['j'], kind, self.now_ms])
        piece['index'] = -1
        column = piece['j'] - 1                     # Grid:SetFallingPiece
        self.falling[column] = max(self.falling[column], piece['i'])
        self.check_falling = True
        return True

    def _slide(self, piece, from_i, from_j, to_i, to_j, ms):
        piece.update(off_i=from_i - to_i, off_j=from_j - to_j, anim=ms, anim_total=ms)

    def _fall(self, random):
        """Grid:FallingPiece."""
        for column, lowest in enumerate(self.falling):
            if not lowest:
                continue
            k = column + 1
            new_i, spent, index = lowest, {1: self._at(lowest, k)}, 2
            for i in range(lowest - 1, 0, -1):
                piece = self._at(i, k)
                if piece['index'] != -1:
                    self._relocate(piece['index'], i, k, new_i, k)
                    self._slide(piece, i, k, new_i, k, FALL_MS)
                    self.board[new_i - 1][k - 1] = piece
                    new_i -= 1
                else:
                    spent[index] = piece
                    index += 1
            while new_i > 0:
                piece = self.board[new_i - 1][k - 1] = spent[new_i]
                self._init_piece(piece, new_i, k, random)
                self._slide(piece, -1, k, new_i, k, FALL_MS)    # from above the board, as its orgPos has it
                new_i -= 1
        self.falling = [0] * SIZE
        self.check_falling = False

    def _shift(self, cells):
        """PuzzleGame:MovePieces*: `cells` from the end that wraps to the end it wraps to. Each moves a place along, and
        the first goes straight to the last place."""
        first = self._at(*cells[0])
        self._relocate(first['index'], *cells[0], *cells[-1])
        for n in range(1, SIZE):
            piece = self._at(*cells[n])
            self._relocate(piece['index'], *cells[n], *cells[n - 1])
            self._slide(piece, *cells[n], *cells[n - 1], MOVE_MS)
            self.board[cells[n - 1][0] - 1][cells[n - 1][1] - 1] = piece
        self.board[cells[-1][0] - 1][cells[-1][1] - 1] = first
        first['anim'] = 0

    # -- the player --------------------------------------------------------------------------------------------------
    def press(self):
        """OK: the go-ahead while it waits for one; in play, PuzzleGame:PressButton; past its score, on with the story."""
        if self.phase == READY:
            return self.start()
        if self.phase == RUNNING:
            self.button = True
            return True
        if self.phase == SHOWING_SCORE:
            self.phase, self.phase_ms = CLOSING, CLOSING_MS
            return True
        return False

    def release(self):
        """PuzzleGame:ReleaseButton."""
        self.button = False

    def start(self):
        """The go-ahead: from the player's press, or from the skip prompt's Play."""
        if self.started:
            return False
        self.started = True
        if self.phase == READY:
            self._run()
        return True

    def _run(self):
        self.phase = RUNNING
        self.prev_total_ms = self.now_ms

    def move(self, direction):
        """PuzzleGame:Move*: a step of the cursor, the row or column coming along with the button held. True if it stepped."""
        if self.phase != RUNNING or self.moving_ms > 0 or self.check_falling:
            return False
        i, j = self.cursor_i, self.cursor_j
        if direction == UP and i > 1:
            self.cursor_i = i - 1
            cells = [(n, j) for n in range(1, SIZE + 1)]
        elif direction == DOWN and i < SIZE:
            self.cursor_i = i + 1
            cells = [(n, j) for n in range(SIZE, 0, -1)]
        elif direction == LEFT and j > 1:
            self.cursor_j = j - 1
            cells = [(i, n) for n in range(1, SIZE + 1)]
        elif direction == RIGHT and j < SIZE:
            self.cursor_j = j + 1
            cells = [(i, n) for n in range(SIZE, 0, -1)]
        else:
            return False
        self.moving_ms = MOVE_MS
        if self.button:
            self._shift(cells)
            self.sounds.append(SOUND_DRAG)
            self.check_pieces()
        return True

    def point(self, i, j):
        """A mouse over a jewel, the button up: the cursor goes there."""
        if self.phase == RUNNING and not self.button and 1 <= i <= SIZE and 1 <= j <= SIZE:
            self.cursor_i, self.cursor_j = i, j

    def grab(self, i, j):
        """A mouse or finger pressed on a jewel: the cursor goes there and the button is held."""
        if self.phase == RUNNING and 1 <= i <= SIZE and 1 <= j <= SIZE:
            self.cursor_i, self.cursor_j = i, j
            self.button, self.target, self.lock = True, [i, j], ''

    def drag(self, i, j):
        """It has moved to over this cell (kept on the board): tick steps the cursor after it."""
        if self.target is not None:
            self.target = [max(1, min(SIZE, i)), max(1, min(SIZE, j))]

    def let_go(self):
        self.button, self.target, self.lock = False, None, ''

    def _follow(self):
        if self.target is None or self.moving_ms > 0 or self.check_falling:
            return
        down, across = self.target[0] - self.cursor_i, self.target[1] - self.cursor_j
        if not self.lock:
            if not down and not across:
                return
            self.lock = 'row' if abs(across) >= abs(down) else 'col'
        if self.lock == 'row' and across:
            self.move(RIGHT if across > 0 else LEFT)
        elif self.lock == 'col' and down:
            self.move(DOWN if down > 0 else UP)

    def tick(self, elapsed_ms, random):
        """One frame; True when the game has finished and the story goes on."""
        self.now_ms += elapsed_ms
        for row in self.board:
            for piece in row:
                if piece['anim'] > 0:
                    piece['anim'] = max(0, piece['anim'] - elapsed_ms)
        self.cleared = [c for c in self.cleared if self.now_ms - c[3] < CLEARED_MS]
        if self.phase == OPENING:
            self.phase_ms -= elapsed_ms
            if self.phase_ms <= 0:
                if self.started:
                    self._run()
                else:
                    self.phase = READY
            return False
        if self.phase in (READY, SHOWING_SCORE):
            return False
        if self.phase == TIME_UP:
            self.phase_ms -= elapsed_ms
            if self.phase_ms <= 0:
                self.phase = SHOWING_SCORE
            return False
        if self.phase == CLOSING:
            self.phase_ms -= elapsed_ms
            return self.phase_ms <= 0
        self.moving_ms = max(0, self.moving_ms - elapsed_ms)
        self._follow()
        if self.fall_wait_ms > 0:                   # Grid:Step's Wait: nothing below runs under it
            self.fall_wait_ms -= elapsed_ms
            if self.fall_wait_ms > 0:
                return False
            self._fall(random)
            self.check_pieces()
        else:
            went = [self._step_piece(piece) for row in self.board for piece in row]
            if any(went):
                self.sounds.append(SOUND_CLEAR)
            if self.check_falling:
                self.in_chain, self.chain_time, self.prev_chain_ms = True, 0, self.now_ms   # PuzzleGame:SetChainState
                self.fall_wait_ms = FALL_WAIT_MS
                return False
        if self.in_chain:
            if self.now_ms - self.prev_chain_ms >= 1000:
                self.chain_time += 1
                self.prev_chain_ms = self.now_ms
            if self.chain_time == CHAIN_SECONDS:
                self.in_chain = False
        if self.now_ms - self.prev_total_ms >= 1000:
            self.total_time -= 1
            self.prev_total_ms = self.now_ms
        if self.total_time < 1:
            self.phase, self.phase_ms = TIME_UP, TIME_UP_MS
            self.button, self.target, self.lock = False, None, ''
        return False

    def validate(self):
        kinds_ok = len(self.board) == SIZE and all(len(row) == SIZE for row in self.board) and len(self.pieces) == KINDS
        if (not kinds_ok or self.phase not in (OPENING, READY, RUNNING, TIME_UP, SHOWING_SCORE, CLOSING)
                or not 1 <= self.cursor_i <= SIZE or not 1 <= self.cursor_j <= SIZE
                or not 0 <= self.total_time <= SECONDS or self.score < 0 or len(self.falling) != SIZE
                or len(self.bars) != KINDS
                or any(p['index'] != -1 and not 1 <= p['index'] <= KINDS for row in self.board for p in row)
                or any(not (1 <= c[0] <= SIZE and 1 <= c[1] <= SIZE) for kind in self.pieces for c in kind)):
            raise ValueError('Invalid jewel puzzle state')
