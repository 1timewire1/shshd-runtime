"""Service 96: native word and picture grids, tutorials, and score callback.

The model uses row-major cells; native storage is column-major with a fixed
five-row stride. Random calls and searches retain the native traversal order.
Evidence, record schemas, and presentation limits: docs/MINIGAMES.md.
"""
from ..game_state import GameState
from dataclasses import dataclass, field
from collections import Counter
import math

from .grid_motion import project
from .grid_animation import GridTile
from .physics import float32

NEIGHBORS = ((0, 1), (0, -1), (1, 1), (1, 0), (1, -1),
             (-1, 1), (-1, 0), (-1, -1))
WORD_TRIM = ''.join(chr(c) for c in range(0x21))


def grid_words(text):
    """000cccd0/0005f838: trim byte values <= 32 and omit empty fields."""
    words, start = [], 0
    while True:
        end = text.find('|', start)
        if end == -1:
            end = len(text)
        word = text[start:end].strip(WORD_TRIM)
        if word:
            words.append(word)
        start = end + 1
        # The native splitter stops after a delimiter when at most one byte
        # remains. A one-byte word without a preceding delimiter is retained.
        if start >= len(text) - 1:
            return words


@dataclass
class GridProblem:
    width: int
    height: int
    heading: str
    prompt: str
    words: list[str]
    alphabet: str
    highlight: bool
    advance_after_one: bool
    minimum_starts: int
    identifier: int
    fixed_board: str | None = None
    show_hints: bool = False
    animate_board: bool = True
    timed_tutorial: bool = False
    success_next: int = -1
    failure_next: int = -1
    tutorial_title: str = ''
    tutorial_text: str = ''
    tutorial_position: int = 0
    tap_to_advance: bool = False
    hide_board: bool = False

    def validate(self):
        if (not 1 <= self.width <= 5 or not 1 <= self.height <= 5
                or len(self.words) > 256
                or any(not w or len(w) > self.width * self.height for w in self.words)
                or not 1 <= self.minimum_starts <= self.width * self.height):
            raise ValueError('Invalid grid dimensions, words, or minimum start count')
        if not self.words and not (self.fixed_board is not None and self.tap_to_advance
                                   and not self.timed_tutorial):
            raise ValueError('Playable grids require at least one target word')
        if self.fixed_board is None:
            if self.width * self.height < 2 or not self.alphabet:
                raise ValueError('Generated grid needs an alphabet and at least two cells')
            if any(c not in self.alphabet for word in self.words for c in word):
                raise ValueError('Grid alphabet cannot form its target words')
        elif len(self.fixed_board) < self.height * (self.width + 1) - 1:
            raise ValueError('Truncated tutorial grid')


@dataclass
class GridBanner:
    kind: str
    enter_ms: int
    hold_ms: int
    age_ms: int = 0


@dataclass
class GridTransition:
    problem: GridProblem
    board: list[str]
    starts: list[int]
    tutorial: bool
    mode: str = 'replace'
    highlight_offsets: dict[int, int] | None = None
    round_ms: int = 0
    deferred: bool = False


@dataclass
class GridFragment:
    x: float
    y: float
    scale: float
    vx: float
    vy: float
    spin: float
    angle: float
    age_ms: int


@dataclass
class GridScoreEffect:
    value: int
    x: float
    y: float
    remaining_ms: int = 400


@dataclass
class WordGrid(GameState):
    duration_ms: int
    target: int
    round_limit_ms: int
    bonus_ms: int
    shuffle: bool
    feedback: bool
    success_text: str
    failure_text: str
    problems: list[GridProblem]
    tutorials: list[GridProblem]
    symbols: dict[int, int]
    remaining_ms: int
    round_ms: int
    order: list[int] = field(default_factory=list)
    tutorial: bool = False
    problem_index: int = 0
    board: list[str] = field(default_factory=list)
    starts: list[int] = field(default_factory=list)
    initial_starts: int = 0
    highlight_offsets: dict[int, int] | None = field(default_factory=dict)
    tiles: list[GridTile] | None = None
    selection: list[int] = field(default_factory=list)
    bad_prefix: list[int] = field(default_factory=list)
    dragging: bool = False
    score: int = 0
    round: int = 0
    phase: int = -2
    phase_ms: int = 1000
    overlay_ms: int = 0
    result_shown: bool = False
    round_success: bool = False
    switching_to_game: bool = False
    tutorial_entry_ms: int = 3700
    sound_ids: list[int] = field(default_factory=list)
    sound_serial: int = 0
    error_sound_ms: int = 0
    last_delta: int = 0
    delta_ms: int = 0
    score_effects: list[GridScoreEffect] = field(default_factory=list)
    score_pending: int = 0
    score_phase: int = 0
    score_target: int = 0
    display_score: int = 0
    visual_ms: int = 0
    board_entry_ms: int = 0
    banner: GridBanner | None = None
    transition: GridTransition | None = None
    pop_ms: dict[int, int] = field(default_factory=dict)
    explosions: list[list[GridFragment]] = field(default_factory=list)
    glint_ms: int = -4000

    @property
    def problem(self):
        if self.transition and self.transition.deferred and self.phase == 4:
            return self.transition.problem
        return (self.tutorials[self.problem_index] if self.tutorial else
                self.problems[self.order[self.problem_index]])

    @property
    def input_enabled(self):
        return self.phase in (1, 2)

    @property
    def selected_text(self):
        return ''.join(self.board[i] for i in self.selection)

    @property
    def result(self):
        # Virtual slot +0x90, 000c1bc4: comparison, not the raw score.
        return int(self.score >= self.target)

    def initialize(self, random):
        self.validate_config()
        self.order = list(range(len(self.problems)))
        if self.shuffle:
            self.shuffle_order(random)
        self.tutorial = bool(self.tutorials)
        self.load_board(random)
        self.commit_highlights(random)
        self.animate_tiles('grow')

    def animate_tiles(self, action):
        if self.tiles is None:
            self.tiles = [GridTile() for _ in self.board]
        p = self.problem
        for i, tile in enumerate(self.tiles):
            delay = 80 * (p.height - 1 + i % p.width - i // p.width)
            if action == 'flip':
                tile.flip(delay)
            elif action == 'shine':
                tile.shine(delay)
            else:
                tile.grow(delay, shrinking=action == 'shrink')

    def commit_highlights(self, random):
        """000c43ec: shuffle one countdown offset per valid starting cell."""
        if not self.problem.highlight:
            return
        count = len(self.starts)
        # For the native maximum of 25 cells, integer division produces the
        # same truncated values as the original float32 calculation.
        offsets = [3000 * i // count for i in range(count)]
        for i in range(count):
            j = random.below(count)
            offsets[i], offsets[j] = offsets[j], offsets[i]
        self.highlight_offsets = dict(zip(self.starts, offsets))

    def shuffle_order(self, random, previous=-1):
        if len(self.order) < 2:
            return
        for i in range(len(self.order)):
            j = random.below(len(self.order))
            while i == 0 and self.order[j] == previous:
                j = random.below(len(self.order))
            self.order[i], self.order[j] = self.order[j], self.order[i]

    def find_path(self, start, word):
        """000c512c: eight-neighbor DFS, exact byte characters, no reuse."""
        w, h = self.problem.width, self.problem.height
        if not word or not 0 <= start < w * h or Counter(word) - Counter(self.board):
            return None
        visited = 0

        def visit(i, offset, path):
            nonlocal visited
            visited += 1
            if visited > 100_000:
                raise ValueError('Grid path search exceeded the work limit')
            if i in path or self.board[i] != word[offset]:
                return None
            path = path + [i]
            if offset + 1 == len(word):
                return path
            x, y = i % w, i // w
            for dx, dy in NEIGHBORS:
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h:
                    result = visit(ny * w + nx, offset + 1, path)
                    if result is not None:
                        return result
            return None

        return visit(start, 0, [])

    def scan_starts(self):
        w, h = self.problem.width, self.problem.height
        self.starts = [y * w + x for x in range(w) for y in range(h)
                       if any(self.find_path(y * w + x, word) for word in self.problem.words)]
        self.initial_starts = len(self.starts)

    def place_word(self, word, random):
        """000cb570: walk from a random cell, committing only a complete path."""
        w, h = self.problem.width, self.problem.height
        x, y = random.below(w), random.below(h)
        placed = {}
        for char in word:
            collisions = 0
            # Native retries out-of-bounds moves without counting collisions.
            # Bound malformed/adversarial input rather than hang the UI.
            for _ in range(4096):
                nx, ny = x + random.signed_below(2), y + random.signed_below(2)
                if (nx == x and ny == y) or not (0 <= nx < w and 0 <= ny < h):
                    continue
                index = ny * w + nx
                if index not in placed and self.board[index] in ('', char):
                    placed[index] = char
                    x, y = nx, ny
                    break
                collisions += 1
                if collisions == 16:
                    return False
            else:
                raise ValueError('Grid placement exceeded the work limit')
        for index, char in placed.items():
            self.board[index] = char
        return True

    def shuffle_board(self, random):
        w, h = self.problem.width, self.problem.height
        for x in range(w):
            for y in range(h):
                nx, ny = random.below(w), random.below(h)
                a, b = y * w + x, ny * w + nx
                self.board[a], self.board[b] = self.board[b], self.board[a]

    def load_board(self, random):
        p = self.problem
        self.round_ms = self.round_limit_ms
        self.selection, self.bad_prefix, self.dragging = [], [], False
        self.highlight_offsets = {}
        self.tiles = [GridTile() for _ in range(p.width * p.height)]
        self.pop_ms = {}
        self.round += 1
        if p.fixed_board is not None:
            self.board = [p.fixed_board[y * (p.width + 1) + x]
                          for y in range(p.height) for x in range(p.width)]
            self.scan_starts()
            return
        for _ in range(15):
            self.board = [''] * (p.width * p.height)
            if not all(self.place_word(p.words[random.below(len(p.words))], random)
                       for __ in range(p.minimum_starts)):
                continue
            for i in range(len(self.board)):
                if not self.board[i]:
                    self.board[i] = p.alphabet[random.below(len(p.alphabet))]
            self.scan_starts()
            if len(self.starts) >= p.minimum_starts:
                return
        self.board = [p.alphabet[i % len(p.alphabet)] for i in range(p.width * p.height)]
        for _ in range(4096):
            self.shuffle_board(random)
            self.scan_starts()
            if len(self.starts) >= p.minimum_starts:
                return
        raise ValueError('Grid cannot satisfy its required number of starting cells')

    def sound(self, *assets):
        self.sound_ids, self.sound_serial = list(assets), self.sound_serial + 1

    def select(self, index, random):
        if type(index) is not int or not 0 <= index < len(self.board):
            raise ValueError('Grid cell index is out of range')
        if not self.input_enabled or index in self.selection:
            return False
        if self.selection:
            w = self.problem.width
            last = self.selection[-1]
            if max(abs(index % w - last % w), abs(index // w - last // w)) > 1:
                return False
        self.selection.append(index)
        if ((self.problem.highlight and self.selection[0] not in self.starts)
                or not any(word.startswith(self.selected_text) for word in self.problem.words)):
            self.bad_prefix.append(index)
        # Native move handler submits immediately when the full word matches.
        if self.selection[0] in self.starts and self.selected_text in self.problem.words:
            self.break_tiles(random)
            self.last_delta = (self.initial_starts - len(self.starts) + 1) * 100
            self.score += self.last_delta
            index, p = self.selection[0], self.problem
            x, y, _ = project(p.width, p.height, index % p.width * 522 + 225,
                               index // p.width * 522 + 225)
            self.score_effects.append(GridScoreEffect(self.last_delta, x, y))
            if self.problem.advance_after_one and self.problem.fixed_board is None:
                self.complete_round(True, random)
            else:
                self.starts.remove(self.selection[0])
                self.round_ms = min(self.round_limit_ms, self.round_ms + self.bonus_ms)
                if not self.starts:
                    self.complete_round(True, random)
            self.selection, self.bad_prefix = [], []
            self.sound(8110, 8111)  # 000c3874 requests both sounds, no random draw.
            return True
        return False

    def break_tiles(self, random):
        # Android 000c3cb0/000d072c; iOS CubeExplosion::init 0009542c.
        # Twenty concurrent bursts, eight fragments each, twelve native random
        # draws per fragment. These belong to gameplay state, never rendering.
        p = self.problem
        for index in self.selection:
            if len(self.explosions) < 20:
                x, y, _ = project(p.width, p.height, index % p.width * 522 + 225,
                                   index // p.width * 522 + 225)
                x, y = float32(x), float32(y)
                scale = float32(float32(float32(y - 150) * float32(.0024242424)) + 1)
                burst = []
                for _ in range(8):
                    burst.append(GridFragment(float32(x + random.signed_below(50)),
                                               float32(y + random.signed_below(50)),
                                               scale, float(random.signed_below(250)),
                                               float(random.signed_below(350) - 250),
                                               float(random.signed_below(360)), float(random.below(360)),
                                               random.below(5000)))
                self.explosions.append(burst)
            if self.tiles is None:
                self.pop_ms[index] = 601  # Legacy saves retain their existing clock.
            else:
                self.tiles[index].grow(1)

    def tick_fragments(self, dt):
        self.pop_ms = {index: remaining - dt for index, remaining in self.pop_ms.items() if remaining >= dt}
        if self.tiles is None:
            self.glint_ms = min(100_000_000, self.glint_ms + dt)
        seconds = float32(dt / 1000)
        for burst in self.explosions:
            for fragment in burst:
                fragment.age_ms += dt
                fragment.x = float32(fragment.x + float32(fragment.vx * seconds))
                fragment.y = float32(fragment.y + float32(fragment.vy * seconds))
                fragment.angle = float32(fragment.angle + float32(fragment.spin * seconds))
                if fragment.y < 480:
                    fragment.vy = float32(fragment.vy + float32(seconds * 1600))
            burst[:] = [fragment for fragment in burst if fragment.y < 480]
        self.explosions[:] = [burst for burst in self.explosions if burst]

    def tick_tiles(self, dt):
        if self.tiles is None or self.phase not in (1, 2, 3, 4, 5, 6):
            return
        for tile in self.tiles:
            tile.tick(dt)
        previous = self.glint_ms
        self.glint_ms = min(100_000_000, previous + dt)
        if previous <= 0 < self.glint_ms:
            self.animate_tiles('shine')

    def tick_score(self, dt):
        """000c2a98/000cd2c0: fly, accumulate, transfer at 800 points/s.

        The HUD has its own eased counter (SHS iOS 00085698); none of these
        delayed display values replaces the score used by the script callback.
        """
        difference = self.score_target - self.display_score
        step = int(difference * .5 * (dt / 100))
        if step == 0 or (difference - step) * difference < 0:
            self.display_score = self.score_target
        else:
            self.display_score += step
        if self.score_phase == 2:
            step = min(self.score_pending, int(dt / 1000 * 800))
            self.score_pending -= step
            self.score_target += step
            if not self.score_pending:
                self.score_phase, self.delta_ms = 1, 300
        elif self.score_phase == 1:
            self.delta_ms = max(0, self.delta_ms - dt)
            if not self.delta_ms:
                self.score_phase = 0
        for effect in self.score_effects:
            effect.remaining_ms -= dt
            if effect.remaining_ms <= 0:
                self.score_pending += effect.value
                self.score_phase = 2
        self.score_effects[:] = [effect for effect in self.score_effects if effect.remaining_ms > 0]

    def pointer(self, phase, index, random):
        if phase not in ('down', 'move', 'up', 'cancel'):
            raise ValueError('Unknown grid pointer phase')
        if index is not None and (type(index) is not int or not 0 <= index < len(self.board)):
            raise ValueError('Grid cell index is out of range')
        if phase == 'cancel':
            self.dragging, self.selection, self.bad_prefix = False, [], []
            return
        if not self.input_enabled:
            return
        if phase == 'down':
            self.dragging = False
            if self.tutorial and self.problem.tap_to_advance:
                self.complete_round(True, random)
                return
            self.dragging = True
        if self.dragging and index is not None:
            self.select(index, random)
        if phase == 'up':
            if self.selection and not self.error_sound_ms:
                self.sound(8109)
                self.error_sound_ms = 250
            self.selection, self.bad_prefix, self.dragging = [], [], False

    def complete_round(self, success, random):
        self.transition = None
        self.round_success = success
        self.dragging = False
        if self.feedback:
            self.phase, self.phase_ms = 3, 1100
            # 000d02c4 suppresses the success banner during instruction pages.
            self.banner = (None if self.tutorial and success else
                           GridBanner('success' if success else 'failure', 1300, 700))
        else:
            self.next_problem(random)

    def next_problem(self, random):
        previous_index = self.problem_index
        self.transition = GridTransition(self.problem, self.board.copy(), self.starts.copy(), self.tutorial,
                                         highlight_offsets=self.highlight_offsets, round_ms=self.round_ms)
        if self.tutorial:
            index = self.problem.success_next if self.round_success else self.problem.failure_next
            if index == -2:
                self.tutorial = False
                self.switching_to_game = True
                self.score = 0
                self.score_effects.clear()
                self.score_pending = self.score_phase = self.score_target = self.display_score = self.delta_ms = 0
                if self.shuffle:
                    self.shuffle_order(random)
                index = 0
            if index < 0 or index >= (len(self.tutorials) if self.tutorial else len(self.problems)):
                raise ValueError('Tutorial transition points outside its record table')
        else:
            index = self.problem_index + 1
            if index == len(self.problems):
                if self.shuffle:
                    self.shuffle_order(random, self.order[self.problem_index])
                index = 0
        incoming = self.tutorials[index] if self.tutorial else self.problems[self.order[index]]
        old = self.transition.problem
        if incoming.animate_board:
            self.transition.mode = ('flip' if (old.width, old.height) == (incoming.width, incoming.height)
                                    and not old.hide_board and not self.switching_to_game else 'shrink')
        self.transition.deferred = self.transition.mode == 'shrink'
        self.phase, self.phase_ms = 4, 800
        if self.transition.deferred:
            # 000d0ff8 advances the retained index at the end of a shrink.
            # Unlike the immediate/flip path, it does not use the peeked
            # tutorial destination. Keep that native distinction explicit.
            count = len(self.tutorials) if self.tutorial else len(self.problems)
            self.problem_index = (previous_index + 1) % count
            self.animate_tiles('shrink')
        else:
            self.problem_index = index
            self.load_board(random)
            if self.transition.mode == 'flip':
                self.animate_tiles('flip')

    def tick(self, elapsed_ms, random):
        if self.phase == 7:
            self.phase_ms = max(0, self.phase_ms - elapsed_ms)
            return self.phase_ms == 0
        # Each native grid update caps dt at 250 ms, including after a stall.
        dt = min(elapsed_ms, 250)
        self.tick_score(dt)
        self.tick_fragments(dt)
        self.tick_tiles(dt)
        self.visual_ms += dt
        if self.phase in (2, 6):
            self.board_entry_ms = min(2000, self.board_entry_ms + dt)
        if self.banner is not None:
            self.banner.age_ms += dt
            if self.banner.age_ms > self.banner.enter_ms + self.banner.hold_ms:
                self.banner = None
        self.error_sound_ms = max(0, self.error_sound_ms - dt)
        self.tutorial_entry_ms = max(0, self.tutorial_entry_ms - dt)
        if self.phase == 1:
            if not self.tutorial:
                self.remaining_ms = max(0, self.remaining_ms - dt)
            if not self.tutorial or self.problem.timed_tutorial:
                self.round_ms -= dt
                if self.round_ms <= 0:
                    self.complete_round(False, random)
            if self.remaining_ms <= 0:
                self.phase, self.phase_ms = 5, 4200
                self.overlay_ms = 2600
                self.banner = GridBanner('time_up', 1600, 1000)
                self.sound(8113)
                self.dragging, self.selection, self.bad_prefix = False, [], []
        else:
            self.phase_ms -= dt
            if self.phase == 5:
                if not self.result_shown and self.phase_ms <= 2600 and not self.overlay_ms:
                    self.result_shown, self.overlay_ms = True, 4600
                    self.banner = GridBanner('result', 2600, 2000)
                elif self.phase_ms <= 0 and not self.overlay_ms:
                    self.phase, self.phase_ms = 7, 960
            elif self.phase_ms <= 0:
                if self.phase == -2:
                    self.phase, self.phase_ms = -1, 1500
                    self.banner = GridBanner('ready', 700, 800)
                elif self.phase == -1:
                    if self.tiles is None:
                        self.glint_ms = -4000
                    self.phase, self.phase_ms = (0, 2800) if self.tutorial else (6, 1600)
                    if not self.tutorial:
                        self.banner = GridBanner('target', 700, 1300)
                elif self.phase in (0, 2):
                    self.phase, self.phase_ms = 1, 0
                    self.transition = None
                elif self.phase == 3:
                    self.next_problem(random)
                elif self.phase == 4:
                    self.glint_ms = -4000
                    self.phase, self.phase_ms = (6, 1600) if self.switching_to_game else (2, 1800)
                    if self.transition and self.transition.deferred:
                        self.load_board(random)
                        self.animate_tiles('grow')
                    self.commit_highlights(random)
                    self.board_entry_ms = 0
                    self.tutorial_entry_ms = 500
                    if self.switching_to_game:
                        self.banner = GridBanner('target', 700, 1300)
                    self.switching_to_game = False
                elif self.phase == 6:
                    self.phase, self.phase_ms = 2, 1800
        # Native expires an overlay strictly after its full display interval.
        if self.overlay_ms:
            self.overlay_ms = max(0, self.overlay_ms - dt)
        return False

    def validate_config(self):
        if (not 0 < self.duration_ms <= 32767000 or not 0 <= self.target <= 32767
                or not 0 < self.round_limit_ms <= 32767 or not 0 <= self.bonus_ms <= 32767
                or not 1 <= len(self.problems) <= 256 or len(self.tutorials) > 256
                or len(self.symbols) > 256):
            raise ValueError('Invalid grid configuration')
        for p in self.problems + self.tutorials:
            p.validate()
        for p in self.tutorials:
            valid = lambda n: n == -2 or 0 <= n < len(self.tutorials)
            if (not valid(p.success_next) or not (valid(p.failure_next)
                    or p.failure_next == -1 and not p.timed_tutorial)):
                raise ValueError('Invalid tutorial transition')
        if any(not 0 <= c <= 255 or not 0 <= asset <= 65535 for c, asset in self.symbols.items()):
            raise ValueError('Invalid grid symbol map')

    def validate(self):
        self.validate_config()
        self.validate_highlights(self.highlight_offsets, len(self.board))
        if self.tiles is not None:
            if len(self.tiles) != len(self.board):
                raise ValueError('Invalid grid cube count')
            for tile in self.tiles:
                tile.validate()
        if (not -4000 <= self.glint_ms <= 100_000_000 or len(self.pop_ms) > len(self.board)
                or any(not 0 <= index < len(self.board) or not 0 <= ms <= 601 for index, ms in self.pop_ms.items())
                or len(self.explosions) > 20 or any(not 1 <= len(burst) <= 8 for burst in self.explosions)):
            raise ValueError('Invalid grid tile animation')
        for burst in self.explosions:
            for f in burst:
                if (not all(math.isfinite(v) for v in (f.x, f.y, f.scale, f.vx, f.vy, f.spin, f.angle))
                        or not -2000 < f.x < 2000 or not -2000 < f.y < 480
                        or not 0 < f.scale < 3 or not -250 < f.vx < 250
                        or not -600 < f.vy < 10000 or not -360 < f.spin < 360
                        or not -10000 < f.angle < 10000 or not 0 <= f.age_ms < 20000):
                    raise ValueError('Invalid grid fragment')
        if (sorted(self.order) != list(range(len(self.problems)))
                or not 0 <= self.problem_index < (len(self.tutorials) if self.tutorial else len(self.problems))):
            raise ValueError('Invalid grid problem order')
        if (not 0 <= self.visual_ms <= 2**53 or not 0 <= self.tutorial_entry_ms <= 3700
                or not 0 <= self.board_entry_ms <= 2000
                or not 0 <= self.delta_ms <= 600):
            raise ValueError('Invalid grid presentation clock')
        if (not 0 <= self.display_score <= self.score or not 0 <= self.score_target <= self.score
                or not 0 <= self.score_pending <= self.score or self.score_phase not in (0, 1, 2)
                or len(self.score_effects) > 1000
                or any(not 0 < effect.value <= self.score or not 0 < effect.remaining_ms <= 400
                       or not math.isfinite(effect.x) or not math.isfinite(effect.y)
                       or not -1000 <= effect.x <= 1000 or not -1000 <= effect.y <= 1000
                       for effect in self.score_effects)
                or self.score_target + self.score_pending + sum(e.value for e in self.score_effects) != self.score):
            raise ValueError('Invalid grid score animation')
        if self.banner is not None:
            b = self.banner
            timings = dict(ready=(700, 800), target=(700, 1300), success=(1300, 700),
                           failure=(1300, 700), time_up=(1600, 1000), result=(2600, 2000))
            if (timings.get(b.kind) != (b.enter_ms, b.hold_ms)
                    or not 0 <= b.age_ms <= b.enter_ms + b.hold_ms):
                raise ValueError('Invalid grid banner')
        if self.transition is not None:
            t = self.transition
            t.problem.validate()
            self.validate_highlights(t.highlight_offsets, len(t.board))
            if (self.phase not in (2, 4, 6) or t.mode not in ('replace', 'flip', 'shrink')
                    or t.deferred and t.mode != 'shrink'
                    or len(t.board) != t.problem.width * t.problem.height
                    or any(len(c) != 1 for c in t.board)
                    or len(t.starts) != len(set(t.starts))
                    or any(not 0 <= i < len(t.board) for i in t.starts)
                    or not -250 <= t.round_ms <= self.round_limit_ms
                    or t.mode == 'flip' and (t.problem.width, t.problem.height) !=
                    (self.problem.width, self.problem.height)):
                raise ValueError('Invalid departing grid')
        p = self.problem
        if (len(self.board) != p.width * p.height or any(len(c) != 1 for c in self.board)
                or len(self.starts) != len(set(self.starts))
                or not len(self.starts) <= self.initial_starts <= len(self.board)
                or len(self.selection) != len(set(self.selection))
                or any(not 0 <= i < len(self.board) for i in self.starts + self.selection)
                or any(i not in self.selection for i in self.bad_prefix)
                or not 0 <= self.remaining_ms <= self.duration_ms
                or not -250 <= self.round_ms <= self.round_limit_ms or self.score < 0
                or self.phase not in range(-2, 8) or not -10000 <= self.phase_ms <= 4600
                or not 0 <= self.overlay_ms <= 4600 or self.round < 1):
            raise ValueError('Invalid saved grid state')
        for a, b in zip(self.selection, self.selection[1:]):
            if max(abs(a % p.width - b % p.width), abs(a // p.width - b // p.width)) > 1:
                raise ValueError('Saved grid selection is not adjacent')
        if any(not any(self.find_path(i, word) for word in p.words) for i in self.starts):
            raise ValueError('Saved grid has an impossible starting cell')

    @staticmethod
    def validate_highlights(offsets, cell_count):
        if offsets is not None and (len(offsets) > cell_count or any(
                not 0 <= index < cell_count or not 0 <= ms < 3000 for index, ms in offsets.items())):
            raise ValueError('Invalid grid highlight offsets')


def read_grid(vm, args, read_text, resolve_text, *, tutorials_seen=False):
    """Decode the service's 20-word frame and word-addressed record tables."""
    if len(args) != 20:
        raise ValueError('Grid service requires twenty arguments')

    def rows(count, address, stride):
        if not 0 <= count <= 256:
            raise ValueError('Grid record count is out of range')
        return [[vm.read_word(address + i * stride + k) for k in range(stride)]
                for i in range(count)]

    problems = []
    for a in rows(args[11], args[12], 10):
        # Native 9f378 is substituted text; fixed board bytes use 9f258.
        problems.append(GridProblem(a[0], a[1], resolve_text(a[2]), resolve_text(a[3]),
                                    grid_words(resolve_text(a[4])), resolve_text(a[5]),
                                    a[6] == 1, a[7] == 1, a[8], 1001 if a[9] == -1 else a[9]))
        # The shipped dispatcher ends the problem loop at this alphabet.
        if problems[-1].alphabet == 'inspirem':
            break
    tutorials = []
    if not tutorials_seen:
        for a in rows(args[18], args[19], 17):
            title, text = (resolve_text(i) if i >= 0 else '' for i in a[:2])
            tutorials.append(GridProblem(
                a[5], a[6], resolve_text(a[7]), resolve_text(a[8]),
                grid_words(resolve_text(a[9])), '', a[10] == 1, False, 1, 1000,
                read_text(a[11]), a[12] == 1, a[13] == 1, a[14] == 1, a[16], a[15],
                title if text else '', text, a[2] if text else 0,
                bool(text) and a[3] == 1, bool(text) and a[4] == 1))
    symbols = dict(rows(args[16], args[17], 2))
    return WordGrid(args[0] * 1000, args[1], args[2], args[3], args[10] == 1, args[13] == 1,
                    resolve_text(args[14]) if args[13] == 1 else '',
                    resolve_text(args[15]) if args[13] == 1 else '', problems, tutorials, symbols,
                    args[0] * 1000, args[2])
