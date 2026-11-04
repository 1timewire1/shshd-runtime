"""shshd-runtime: SHS '11's minigames, as translated stories call them (service SHS11_MEMORY behind service 70 selector
SHS11_MINIGAMES_QUERY, which only this player answers; other players take what the smartphone has at that spot).

Memory is N73 1.40.63's `bg` over `cv`, with `am` (its grid, clock, score ring and dealer) and `x` (a round). A round's cue
line shows for 3 s. Then its word's letters are dealt one by one into shuffled cells of nine, each starting half a letter
time after the last and taking a letter time to land. The cells turn to question marks and the rest hide bad boxes. A letter
that's next in the word scores and keeps the Spelling Bonus; any other letter scores too and loses it, and moves on what
counts as next. A bad box takes 5 s off the clock and loses it. Finding them all pays the bonus if it's kept. The round
ends after its limit too, and the next starts 2 s later. Points arrive 1 s after they're won.

The 60 s clock starts at the first round's first pick and runs through everything, so a slow cue costs nothing but a slow
hand does. After the last round they repeat at random (`bg`'s `u` past `t`) until the clock runs out, so the game always
lasts the whole minute. At the end, "Time's up!" holds for 3 s. The result is 2 at 98% of the target or more, 1 above 75%,
else 0 (`cv`, state 7).

Its oddity is kept: a bad box is an `X`, and the check for the next letter comes first, so in RELAX a bad box counts as the
X when that's next, and the real X scores as an out-of-order letter afterwards.

Two changes. '11 keeps one "tutorials seen" flag for the whole game; this keeps it per story (EngineState), as a story has
no way to reach another's. And '11 takes a key's release; this takes the press, as a pointer has no key to hold.
"""
from dataclasses import dataclass, field

from .shs11_services import SHS11_MEMORY, SHS11_MINIGAMES_QUERY, SHS11_REFLEX  # noqa: F401

# Phases. `goal`, `shown`, `bad` and `ready` are the tutorial's boxes, each waiting for a press; `look` is its box over a
# dealt grid. CUE and DEAL run in both.
GOAL, CUE, DEAL, LOOK, SHOWN, BAD, READY, PLAY, NEXT, TIME_UP = ('goal', 'cue', 'deal', 'look', 'shown', 'bad', 'ready',
                                                                 'play', 'next', 'time_up')
PHASES = (GOAL, CUE, DEAL, LOOK, SHOWN, BAD, READY, PLAY, NEXT, TIME_UP)
BLANK, HIDDEN, WRONG, RIGHT = 0, 1, 2, 3     # what a cell shows: its own number, `?`, a red X, a green letter
CELLS = 9
BAD_BOX = 'X'
CUE_MS = 3000                           # `bg`.d: `i` to 3000
NEXT_MS = 2000                          # `bg`.f: `l` to 2000
TIME_UP_MS = 3000                       # `cv`.p
POINTS_DELAY_MS = 1000                  # `bg`.a: b.a(1000, B)
BONUS_SHOWN_MS = 1000                   # `bg`.a(short): the ct's a
PENALTY_MS = 5000
WIN_PERCENT, MIDDLE_PERCENT = 98, 75
TUTORIAL_CELLS = (8, 6, 5, 4, 3, 2, 1, 7, 0)    # co.a(bg): its fixed deal, not shuffled
# The sounds, in the addon: its tracks (the full builds' calls and slots, SHS_11_PLAN.md). A bad pick is a drum, a finished
# word without its bonus a short rising pad, one with it, or a full gauge, a longer one, and the time up a whistle.
SOUND_BASE = 26980
SOUND_WRONG, SOUND_MISSED_BONUS, SOUND_DONE, SOUND_TIME_UP = SOUND_BASE + 7, SOUND_BASE + 8, SOUND_BASE + 9, SOUND_BASE + 10
GAME_SOUNDS = (SOUND_WRONG, SOUND_MISSED_BONUS, SOUND_DONE, SOUND_TIME_UP)
# Standing in for a word grid, or with '11's own games in the Word Grid skin (Reflex: the wrong pick, the full gauge as a finished word,
# the time up), it has the HD minigames' own sounds in place of '11's, chosen by ear (owner, 2026-11-04): a wrong pick is
# the grid's wrong trace, a word without its bonus the quiz's right answer, one with it the grid's found word, and the time up the grid's.
# Any finished word also has the tiles breaking (8111, which the grid plays with its found word), as they break either way.
# Reflex's right picks are silent in '11, which feels empty in the skin: there they have the quiz's right answer (SOUND_RIGHT_PICK is no
# sound of its own: in '11's look it's dropped).
SOUND_RIGHT_PICK = -1
GRID_SOUNDS = {SOUND_WRONG: (8109,), SOUND_MISSED_BONUS: (8001, 8111), SOUND_DONE: (8110, 8111), SOUND_TIME_UP: (8113,),
               SOUND_RIGHT_PICK: (8001,)}
# A round in a story's table, in words: cue, word, bonus, points a letter, letter time, its limit.
ROUND_WORDS = 6
LETTER_STEP, BAR_STEP = 10, 5           # what every score in '11's games is a multiple of (its tables)


# Memory in place of a word grid (the "Use '11's Memory for Word Grid" switch; owner, 2026-11-04): our own idea, as '11 only swapped a
# grid for Memory once. A round takes '11's usual points and its middle speed. The target is what a player keeps up with: it
# walks the words at a steady pace through the grid's own time and takes 75% of what that scores. Over '11's own 60 s and five-letter
# words that comes to the 300-400 its stories ask for (Best Party Ever: 350), and a grid's usual 45 s and 4-6 words fit about once.
# Its words, here so it needs no addon: '11's, but for how the first says to pick a box (owner, 2026-11-04: on a touch screen too).
GRID_TEXT = dict(
    spelling='Spelling Bonus',
    goal='Your goal in this game is to select boxes in order to find the letters that spell a word.',
    look='Look closely where the letters of the target word go on the grid and memorize their locations.',
    select="You can select the boxes in any order, but if you spell the word in the right order, you'll get a Spelling Bonus!",
    careful='Be careful: selecting a wrong box will result in a time penalty!',
    ready='Ready to try the real thing? Good luck!',
    time_up="Time's up!")
GRID_BONUS, GRID_LETTER_POINTS = 20, 10
GRID_LETTER_MS, GRID_LIMIT_MS, GRID_LIMIT_LETTER_MS = 570, 4250, 700
GRID_PICK_MS = 500                      # the pace a target assumes: a pick this often
GRID_TARGET_PERCENT = 75
GRID_LEAST_SECONDS = 30                 # shorter ones are scenes of their own (a grid of 8 s), not games to swap


def grid_target(rounds, seconds):
    """The score to ask for of these rounds in this long."""
    score, left, index = 0, seconds * 1000, 0
    while True:
        round_ = rounds[index % len(rounds)]
        letters = len(round_[1])
        # The clock starts at the first game's first pick, so the first cue and deal are free.
        left -= letters * GRID_PICK_MS if index == 0 else (NEXT_MS + CUE_MS + letters * GRID_LETTER_MS // 2 + GRID_LETTER_MS
                                                           + letters * GRID_PICK_MS)
        if left < 0:
            break
        score += letters * GRID_LETTER_POINTS + GRID_BONUS
        index += 1
    least = max(GRID_LETTER_POINTS, score * GRID_TARGET_PERCENT // 100)
    return least - least % GRID_LETTER_POINTS


def grid_memory(grid, random, *, tutorial=False):
    """The Memory game for this word grid (shs/word_grid.WordGrid, only read), or None where it should stay a grid: pictures,
    a word that won't fit the board or the letter font, no score to reach, a very short game. The grid's result (service
    96, reached or not) is still what the story gets."""
    if (grid.symbols or grid.target <= 0 or grid.duration_ms < GRID_LEAST_SECONDS * 1000 or not grid.problems):
        return None
    order = list(range(len(grid.problems)))
    if grid.shuffle:
        for i in range(len(order) - 1, 0, -1):
            j = random.below(i + 1)
            order[i], order[j] = order[j], order[i]
    rounds = []
    for problem in (grid.problems[i] for i in order):
        cue = ' '.join(problem.heading.split())
        for word in problem.words:
            if not (1 <= len(word) <= CELLS and word.isascii() and word.isalpha()):
                return None
            rounds.append([cue, word.upper(), GRID_BONUS, GRID_LETTER_POINTS, GRID_LETTER_MS,
                           max(GRID_LIMIT_MS, len(word) * GRID_LIMIT_LETTER_MS)])
    if not rounds:
        return None
    seconds = grid.duration_ms // 1000
    game = MemoryGame.opened(rounds, seconds, grid_target(rounds, seconds), tutorial=tutorial)
    game.grid = True
    return game


def lowest_score(target, percent, step):
    """The lowest score, of those a game can reach, at this percent of its target (`cv`, state 7, rounds its percent down)."""
    least = -(-target * percent // 100)
    return -(-least // step) * step


@dataclass
class MemoryGame:
    rounds: list[list]                  # [cue, word, bonus, points a letter, letter ms, limit ms]
    target: int
    clock_ms: int                       # what's left of the minute
    total_ms: int = 60000
    tutorial: bool = False              # showing the tutorial rather than a real round
    started: bool = False               # (Session.minigame_unstarted: a skip prompt holds it before this)
    running: bool = False               # the clock has started
    phase: str = NEXT
    phase_ms: int = 0
    round: int = -1                     # `u`, the next to count on from
    word: str = ''
    cue: str = ''
    bonus: int = 0
    letter_points: int = 0
    letter_ms: int = 0
    left_ms: int = 0                    # `m`: of this round's limit
    cells: list[str] = field(default_factory=lambda: [''] * CELLS)      # each cell's letter or BAD_BOX, once dealt
    shows: list[int] = field(default_factory=lambda: [BLANK] * CELLS)
    landing: list[int] = field(default_factory=list)    # each dealt letter's ms in the air, in the word's order
    order: list[int] = field(default_factory=list)      # the word's letters' cells
    deal_ms: int = 0                    # `j`: since the last letter was dealt
    next_letter: int = 0                # `r`: of the word
    found: int = 0                      # `n`
    missed: bool = False                # `o`: the bonus is lost
    score: int = 0                      # the ring's
    pending: list[list[int]] = field(default_factory=list)      # [ms to arrive, points, cell or -1]: its floating number
    bonus_ms: int = 0                   # the Spelling Bonus box's left
    flash: list[int] = field(default_factory=lambda: [-1, 0])   # the cell just pressed, and how long ago
    sounds: list[int] = field(default_factory=list)     # waiting for the session to play
    visual_ms: int = 0                  # how long it has been up (for its look's clouds and turning cubes; nothing here reads it)
    grid: bool = False                  # standing in for a word grid (`grid_memory`): its result is 1 or 0, its sounds GRID_SOUNDS

    @classmethod
    def opened(cls, rounds, seconds, target, *, tutorial=False):
        return cls(rounds=[list(r) for r in rounds], target=target, clock_ms=seconds * 1000, total_ms=seconds * 1000, tutorial=tutorial,
                   phase=GOAL if tutorial else NEXT, phase_ms=NEXT_MS if not tutorial else 0)

    @property
    def best_result(self):
        return 1 if self.grid else 2

    @property
    def result(self):
        percent = self.score * 100 // self.target
        if self.grid:
            return int(percent >= WIN_PERCENT)
        return 2 if percent >= WIN_PERCENT else 1 if percent > MIDDLE_PERCENT else 0

    @property
    def win_score(self):
        return lowest_score(self.target, WIN_PERCENT, LETTER_STEP)

    @property
    def banner(self):
        return self.phase == PLAY or (self.phase == NEXT and bool(self.word))

    def _begin_round(self, random):
        """co.a(bg): the next round, or a random one past the last, shuffled but for the tutorial's."""
        self.round += 1
        index = self.round
        if index >= len(self.rounds):
            index = random.below(len(self.rounds))
        self.cue, self.word, self.bonus, self.letter_points, self.letter_ms, limit = self.rounds[index]
        self.left_ms = limit
        cells = list(TUTORIAL_CELLS) if self.tutorial else list(range(CELLS))
        if not self.tutorial:
            for i in range(CELLS - 1, 0, -1):
                j = random.below(i + 1)
                cells[i], cells[j] = cells[j], cells[i]
        self.order = cells[:len(self.word)]
        self.cells = [BAD_BOX] * CELLS
        for letter, cell in zip(self.word, self.order):
            self.cells[cell] = letter
        self.shows = [BLANK] * CELLS
        self.landing, self.deal_ms = [], 0
        self.next_letter = self.found = 0
        self.missed = False
        self.phase, self.phase_ms = CUE, 0

    def press(self, cell=None):
        """A press: the tutorial's OK (no cell), or a pick (`bg`.a)."""
        if self.phase in (GOAL, LOOK, SHOWN, BAD, READY):
            if cell is not None:
                return False
            self._tutorial_step()
            return True
        if self.phase != PLAY or cell is None or not 0 <= cell < CELLS or self.shows[cell] != HIDDEN:
            return False
        self.flash = [cell, 0]
        expected = self.word[self.next_letter] if self.next_letter < len(self.word) else ''
        letter = self.cells[cell]
        if letter == expected:
            self._found(cell)
        elif letter != BAD_BOX:
            self.missed = True
            self._found(cell)
        else:
            self.missed = True
            self.shows[cell] = WRONG
            self.clock_ms = max(0, self.clock_ms - PENALTY_MS)
            self.sounds.append(SOUND_WRONG)
            return True
        if self.found >= len(self.word):
            self._round_done()
        return True

    def _found(self, cell):
        self.found += 1
        self.next_letter += 1
        self.shows[cell] = RIGHT
        self.pending.append([POINTS_DELAY_MS, self.letter_points, cell])

    def _round_done(self):
        """`bg`.b's end of a round, and its a(short): the bonus, if it's kept."""
        if not self.missed:
            self.sounds.append(SOUND_DONE)
            self.pending.append([POINTS_DELAY_MS, self.bonus, -1])
            self.bonus_ms = BONUS_SHOWN_MS
        else:
            self.sounds.append(SOUND_MISSED_BONUS)
        self.phase, self.phase_ms = NEXT, NEXT_MS

    def _tutorial_step(self):
        if self.phase == GOAL:
            self._begin_tutorial_round()
        elif self.phase == LOOK:
            self.phase = SHOWN                  # the letters, green
            self.shows = [RIGHT if cell in self.order else BLANK for cell in range(CELLS)]
        elif self.phase == SHOWN:
            self.phase = BAD                    # the bad boxes, red
            self.shows = [BLANK if cell in self.order else WRONG for cell in range(CELLS)]
        elif self.phase == BAD:
            self.phase = READY
        elif self.phase == READY:
            self.tutorial = False               # (`o.c`), and the rounds start again from the first
            self.round = -1
            self.word = ''
            self.shows = [BLANK] * CELLS
            self.phase, self.phase_ms = NEXT, NEXT_MS

    def _begin_tutorial_round(self):
        class Fixed:                            # (the tutorial's deal draws no random number)
            @staticmethod
            def below(_):
                return 0
        self._begin_round(Fixed)
        self.round = -1

    def _tick_pending(self, elapsed_ms):
        for entry in self.pending:
            entry[0] -= elapsed_ms
        arrived = [entry for entry in self.pending if entry[0] <= 0]
        for entry in arrived:
            self.score += entry[1]
        if arrived:
            self.pending = [entry for entry in self.pending if entry[0] > 0]

    def tick(self, elapsed_ms, random):
        """One frame; True when the game has finished and the story goes on."""
        self.started = True
        self.visual_ms += elapsed_ms
        self._tick_pending(elapsed_ms)
        self.bonus_ms = max(0, self.bonus_ms - elapsed_ms)
        if self.flash[0] >= 0:
            self.flash[1] += elapsed_ms
        self.landing = [ms + elapsed_ms for ms in self.landing]
        if self.phase == TIME_UP:
            self.phase_ms -= elapsed_ms
            return self.phase_ms <= 0 and not self.pending
        if self.running:
            self.clock_ms = max(0, self.clock_ms - elapsed_ms)
            if self.clock_ms == 0:
                self.running = False
                self.sounds.append(SOUND_TIME_UP)
                self.phase, self.phase_ms = TIME_UP, TIME_UP_MS
                return False
        if self.phase == NEXT:
            self.phase_ms -= elapsed_ms
            if self.phase_ms <= 0:
                self._begin_round(random)
        elif self.phase == CUE:
            self.phase_ms += elapsed_ms
            if self.phase_ms >= CUE_MS:
                self.phase, self.phase_ms = DEAL, 0
        elif self.phase == DEAL:
            self.deal_ms += elapsed_ms
            if self.deal_ms >= self.letter_ms // 2 and len(self.landing) < len(self.word):
                self.landing.append(0)
                self.deal_ms = 0
            elif len(self.landing) == len(self.word) and self.deal_ms >= self.letter_ms and self.landing[-1] > self.letter_ms:
                if self.tutorial:
                    self.phase, self.phase_ms = LOOK, 0
                else:
                    self.phase, self.phase_ms = PLAY, 0
                    self.shows = [HIDDEN] * CELLS
                    self.running = True
        elif self.phase == PLAY:
            self.left_ms -= elapsed_ms
            if self.left_ms <= 0:
                self.missed = True
                self.phase, self.phase_ms = NEXT, NEXT_MS
        return False

    def validate(self):
        if (self.phase not in PHASES or self.target <= 0 or not 0 <= self.clock_ms <= self.total_ms or not self.rounds
                or len(self.cells) != CELLS or len(self.shows) != CELLS
                or any(len(r) != ROUND_WORDS for r in self.rounds)
                or any(show not in (BLANK, HIDDEN, WRONG, RIGHT) for show in self.shows)
                or any(not 0 <= cell < CELLS for cell in self.order)
                or len(self.flash) != 2 or any(len(entry) != 3 for entry in self.pending)
                or (self.word and len(self.order) != len(self.word))):
            raise ValueError('Invalid Memory game state')


# -- Reflex -----------------------------------------------------------------------------------------------------------
# N73 1.40.63's `av` over `cv`, with `am` (its gauge and its nine icons) and `bl` (a round). Nine cells deal again and again
# until the gauge fills: each icon comes in after up to 650 ms, over its round's flash time, and they all hold for its hold
# time from then. A pick shuts the others and the next deal comes 100 ms later. The round's right icon moves the gauge on by
# its bars and scores its bars x the points, the wrong one moves it back, a skull empties it. Nothing can be picked for 750 ms
# after a pick, or as a round begins. A full gauge scores the bonus and starts the next round, with worse odds, once the
# marker has got there (750 ms) and no points are in the air. After the last round they repeat at random until the clock runs
# out, as Memory's do.
GAUGE, SELECT, BARS, PENALTY, SKULL = 'gauge', 'select', 'bars', 'penalty', 'skull'     # the tutorial's other boxes
ENTER, PAUSE = 'enter', 'pause'         # `av` q = 2 (the gauge dropping in) and q = 6
REFLEX_PHASES = (GOAL, GAUGE, SELECT, BARS, PENALTY, SKULL, READY, ENTER, PLAY, PAUSE, TIME_UP)
ENTER_MS = 400                          # `b`.q: the gauge's icons drop in
MARKER_MS = 750                         # `b`.a: the marker's move
PAUSE_MS = 100                          # `av`.f
GUARD_MS = 750                          # `av`.d
LONGEST_DELAY_MS = 650                  # `av`.e: b.c(650)
RIGHT_ICON, WRONG_ICON, SKULL_ICON = 0, 1, 2     # a dealt icon's kind (`am`.r)
# A dealt icon, as a list: its kind, picture, bars, its delay, how long since it was dealt, how long it has been shutting (or
# -1).
KIND, PICTURE, BARS_SHOWN, DELAY, AGE, SHUTTING = range(6)
SHUT_MS = 100                           # `am` case 2: 50 ms on one frame, 50 on the next
# A round in a story's table, in words: right icons at least, the gauge's size, bonus, points a bar, the right, wrong and skull
# pictures, four odds out of 100 (1 bar, 2 bars, 3 bars, a skull), flash ms, hold ms.
REFLEX_ROUND_WORDS = 13
(LEAST_RIGHT, GAUGE_SIZE, ROUND_BONUS, BAR_POINTS, RIGHT_PICTURE, WRONG_PICTURE, SKULL_PICTURE, ONE_BAR, TWO_BARS, THREE_BARS,
 SKULLS, FLASH_MS_WORD, HOLD_MS_WORD) = range(REFLEX_ROUND_WORDS)


@dataclass
class ReflexGame:
    rounds: list[list[int]]
    target: int
    clock_ms: int
    total_ms: int = 60000
    tutorial: bool = False
    started: bool = False
    running: bool = False
    phase: str = ENTER
    phase_ms: int = 0
    wait_ms: int = 0                    # the tutorial's boxes wait for the marker
    round: int = -1                     # `u`
    row: list[int] = field(default_factory=list)        # the round in play
    gauge: int = 0                      # `c`
    full: bool = False                  # `h`
    marker: int = 0                     # where the marker is coming from, in thousandths of its way
    marker_to: int = 0
    marker_ms: int = 0                  # what's left of its move
    marker_look: int = 0                # 0 still, 1 going back, 2 going on (`r`)
    cells: list[list[int]] = field(default_factory=lambda: [[] for _ in range(CELLS)])
    shows: list[int] = field(default_factory=lambda: [BLANK] * CELLS)
    shown_ms: int = 0                   # `a`
    hold_ms: int = 0                    # `b`
    guard_ms: int = -1                  # `d`
    score: int = 0
    pending: list[list[int]] = field(default_factory=list)
    flash: list[int] = field(default_factory=lambda: [-1, 0])
    sounds: list[int] = field(default_factory=list)
    visual_ms: int = 0

    @classmethod
    def opened(cls, rounds, seconds, target, *, tutorial=False):
        return cls(rounds=[list(r) for r in rounds], target=target, clock_ms=seconds * 1000, total_ms=seconds * 1000,
                   tutorial=tutorial, phase=GOAL if tutorial else ENTER, row=list(rounds[0]) if tutorial else [])

    @property
    def result(self):
        percent = self.score * 100 // self.target
        return 2 if percent >= WIN_PERCENT else 1 if percent > MIDDLE_PERCENT else 0

    @property
    def win_score(self):
        return lowest_score(self.target, WIN_PERCENT, BAR_STEP)

    @property
    def close_score(self):
        return lowest_score(self.target, MIDDLE_PERCENT + 1, BAR_STEP)

    @property
    def marker_at(self):
        """Where the marker is, in thousandths of its way; a full gauge's goes all the way and then back to the start."""
        if not self.marker_ms:
            return self.marker
        return self.marker_to + (self.marker - self.marker_to) * self.marker_ms // MARKER_MS

    def _move_marker(self, to, look):
        self.marker = self.marker_at
        self.marker_to, self.marker_ms, self.marker_look = to, MARKER_MS, look

    def _change_gauge(self, by):
        """`b`.a(int, short, am)."""
        self.gauge = max(0, self.gauge + by)
        size = self.row[GAUGE_SIZE]
        look = 2 if by > 0 else 1
        if self.gauge >= size:
            self.gauge, self.full = 0, True
            self._move_marker(1000, look)
        else:
            self._move_marker(self.gauge * 1000 // size, look)

    def _begin_round(self, random):
        """co.a(av), `b`.a(ax, bl, am)."""
        self.round += 1
        index = self.round if self.round < len(self.rounds) else random.below(len(self.rounds))
        self.row = list(self.rounds[index])
        self.gauge, self.full = 0, False
        self.marker = self.marker_to = self.marker_ms = self.marker_look = 0
        self.cells = [[] for _ in range(CELLS)]
        self.shows = [BLANK] * CELLS
        self.shown_ms = self.hold_ms = 0
        self.guard_ms = -1
        self.phase, self.phase_ms = ENTER, ENTER_MS

    def _deal(self, random):
        """`av`.e, its order of draws and odds kept. A dealt icon's bars stay as the last one's when the draw is past them."""
        row = self.row
        one, two = row[ONE_BAR], row[ONE_BAR] + row[TWO_BARS]
        three = two + row[THREE_BARS]
        skull = three + row[SKULLS]
        order = list(range(CELLS))
        for i in range(CELLS - 1, 0, -1):
            j = random.below(i + 1)
            order[i], order[j] = order[j], order[i]
        rights, wanted, bars = 0, row[LEAST_RIGHT], 1
        self.cells = [[] for _ in range(CELLS)]
        for dealt in range(CELLS):
            draw = random.below(100)
            is_skull = three < draw < skull
            if CELLS - dealt <= wanted:
                kind = RIGHT_ICON
            elif rights >= row[LEAST_RIGHT]:
                kind = SKULL_ICON if is_skull else WRONG_ICON
            elif is_skull:
                kind = SKULL_ICON
            else:
                kind = RIGHT_ICON
            if kind == RIGHT_ICON:
                rights += 1
                wanted -= 1
            if draw < one:
                bars = 1
            elif draw < two:
                bars = 2
            elif draw < three:
                bars = 3
            picture = (row[RIGHT_PICTURE], row[WRONG_PICTURE], row[SKULL_PICTURE])[kind]
            self.cells[order[dealt]] = [kind, picture, bars, random.below(LONGEST_DELAY_MS), 0, -1]
        self.shows = [BLANK] * CELLS
        self.shown_ms = self.hold_ms = 0
        self.phase, self.phase_ms = PLAY, 0

    def revealed(self, cell):
        """Whether a cell's icon is all the way in, and not shutting: only then can it be picked (`av`.a's check that it's
        no longer animating)."""
        icon = self.cells[cell]
        return bool(icon) and icon[SHUTTING] < 0 and icon[AGE] >= icon[DELAY] + self.row[FLASH_MS_WORD]

    def _shut_others(self, cell=-1):
        for other, icon in enumerate(self.cells):
            if icon and other != cell and icon[SHUTTING] < 0:
                icon[SHUTTING] = 0
        self.phase, self.phase_ms = PAUSE, 0

    def press(self, cell=None):
        """A press: the tutorial's OK (no cell), or a pick (`av`.a)."""
        if self.tutorial:
            if cell is not None or self.wait_ms > 0:
                return False
            self._tutorial_step()
            return True
        if (self.phase != PLAY or cell is None or not 0 <= cell < CELLS or self.guard_ms < GUARD_MS or self.shows[cell] != BLANK
                or not self.revealed(cell)):
            return False
        self.flash = [cell, 0]
        kind, _, bars = self.cells[cell][:3]
        if kind == RIGHT_ICON:
            self.shows[cell] = RIGHT
            self.pending.append([POINTS_DELAY_MS, self.row[BAR_POINTS] * bars, cell])
            self.sounds.append(SOUND_RIGHT_PICK)
            self._change_gauge(bars)
        elif kind == WRONG_ICON:
            self.shows[cell] = WRONG
            self.sounds.append(SOUND_WRONG)
            self._change_gauge(-bars)
        else:
            self.shows[cell] = WRONG
            self.sounds.append(SOUND_WRONG)
            self._change_gauge(-self.gauge)
        self._shut_others(cell)
        self.guard_ms = 0
        return True

    def _tutorial_step(self):
        """`av`.d's boxes: each OK goes on, a pick shown between some of them while the marker moves."""
        row = self.row
        if self.phase == GOAL:
            self.phase = GAUGE
        elif self.phase == GAUGE:
            self.phase = SELECT
            self.cells[6] = [SKULL_ICON, row[SKULL_PICTURE], 2, 0, 10000, -1]
            self.cells[7] = [WRONG_ICON, row[WRONG_PICTURE], 1, 0, 10000, -1]
            self.cells[8] = [RIGHT_ICON, row[RIGHT_PICTURE], 3, 0, 10000, -1]
        elif self.phase == SELECT:
            self.phase, self.wait_ms = BARS, MARKER_MS
            self.shows[8] = RIGHT
            self._change_gauge(3)
        elif self.phase == BARS:
            self.phase = PENALTY
        elif self.phase == PENALTY:
            self.phase, self.wait_ms = SKULL, MARKER_MS
            self.shows[7] = WRONG
            self._change_gauge(-1)
        elif self.phase == SKULL:
            self.phase, self.wait_ms = READY, MARKER_MS
            self.shows[6] = WRONG
            self._change_gauge(-self.gauge)
        elif self.phase == READY:
            self.tutorial = False               # (`o.d`), and the rounds start from the first
            self.round = -1
            self.row = list(self.rounds[0])
            self.marker = self.marker_to = self.marker_ms = self.marker_look = self.gauge = 0
            self.cells = [[] for _ in range(CELLS)]
            self.shows = [BLANK] * CELLS
            self.guard_ms = -1
            self.round = 0
            self.phase, self.phase_ms = ENTER, ENTER_MS

    def _tick_pending(self, elapsed_ms):
        for entry in self.pending:
            entry[0] -= elapsed_ms
        arrived = [entry for entry in self.pending if entry[0] <= 0]
        for entry in arrived:
            self.score += entry[1]
        if arrived:
            self.pending = [entry for entry in self.pending if entry[0] > 0]

    def tick(self, elapsed_ms, random):
        """One frame; True when the game has finished and the story goes on."""
        self.started = True
        self.visual_ms += elapsed_ms
        self._tick_pending(elapsed_ms)
        if self.flash[0] >= 0:
            self.flash[1] += elapsed_ms
        if self.marker_ms:
            self.marker_ms = max(0, self.marker_ms - elapsed_ms)
            if not self.marker_ms:
                # A full gauge's marker jumps back; otherwise it stays where it got to.
                self.marker = 0 if self.marker_to >= 1000 else self.marker_to
                self.marker_look = 0
        if self.wait_ms:
            self.wait_ms = max(0, self.wait_ms - elapsed_ms)
            if not self.wait_ms:
                self.shows = [BLANK] * CELLS    # `av`.d: the pick it showed goes as the next box comes
        for icon in self.cells:
            if icon:
                icon[AGE] += elapsed_ms
                if icon[SHUTTING] >= 0:
                    icon[SHUTTING] += elapsed_ms
        self.cells = [[] if icon and icon[SHUTTING] >= SHUT_MS else icon for icon in self.cells]
        if self.phase == TIME_UP:
            self.phase_ms -= elapsed_ms
            return self.phase_ms <= 0 and not self.pending
        if self.tutorial:
            return False
        if self.running:
            self.clock_ms = max(0, self.clock_ms - elapsed_ms)
            if self.clock_ms == 0:
                self.running = False
                self.sounds.append(SOUND_TIME_UP)
                self._shut_others()
                self.phase, self.phase_ms = TIME_UP, TIME_UP_MS
                return False
        if self.phase == ENTER:
            self.phase_ms = max(0, self.phase_ms - elapsed_ms)
            if self.phase_ms == 0 and not self.pending and not self.marker_ms:
                if not self.row:
                    self._begin_round(random)
                else:
                    self._deal(random)
                    if self.round <= 0:
                        self.running = True     # `cv`.b: the clock starts with the first round's first deal
        elif self.phase == PLAY:
            if self.guard_ms < GUARD_MS:
                self.guard_ms += elapsed_ms
            flash, hold = self.row[FLASH_MS_WORD], self.row[HOLD_MS_WORD]
            if self.shown_ms < flash + LONGEST_DELAY_MS:
                self.shown_ms += elapsed_ms
            else:
                self.hold_ms += elapsed_ms
                if self.hold_ms > hold and not self.full:
                    self.hold_ms = 0
                    self._shut_others()
        elif self.phase == PAUSE:
            self.phase_ms += elapsed_ms
            if self.phase_ms > PAUSE_MS:
                if not self.full:
                    self._deal(random)
                elif not self.marker_ms:
                    self.pending.append([POINTS_DELAY_MS, self.row[ROUND_BONUS], -1])
                    self.sounds.append(SOUND_DONE)
                    self._begin_round(random)
        return False

    def validate(self):
        if (self.phase not in REFLEX_PHASES or self.target <= 0 or not 0 <= self.clock_ms <= self.total_ms or not self.rounds
                or any(len(r) != REFLEX_ROUND_WORDS for r in self.rounds) or len(self.cells) != CELLS or len(self.shows) != CELLS
                or (self.row and len(self.row) != REFLEX_ROUND_WORDS)
                or any(icon and (len(icon) != 6 or icon[KIND] not in (RIGHT_ICON, WRONG_ICON, SKULL_ICON)) for icon in self.cells)
                or any(show not in (BLANK, WRONG, RIGHT) for show in self.shows)
                or len(self.flash) != 2 or any(len(entry) != 3 for entry in self.pending)
                or not 0 <= self.marker_at <= 1000):
            raise ValueError('Invalid Reflex game state')
