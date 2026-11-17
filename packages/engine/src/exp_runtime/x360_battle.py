"""shshd-runtime: a real Diss Battle for the cancelled Xbox 360 game's Monday Planner (owner, 2026-11-16; plan
`reference/Other Games/docs/DISS_BATTLE_X360_PLAN.md`). The prototype has only a `--call diss practice minigame or
something` comment where New Rules plays its Rhyme game, so this is ours: New Rules' Rhyme on Diss Practice's turntable
(x360_diss: the same deck and arm), with the Minigame Arena's catch (the word nearest the needle) and the practice's
streak tiers.

- **Rhyme (New Rules):** a target word ("`crash` rhymes with...") and four words riding the record, the rhyme and three
  wrong ones. Catching the rhyme scores and brings a new target and words; a wrong word costs 3 (never below 0), goes
  blank and leaves the target as it is.
- **Tiers (the practice's, owner's pick: they multiply points):** a right rhyme is worth 3 x the tier: x1, then x2 (the
  practice's double notes) after DOUBLE_STREAK right in a row, then x3 (on fire) after FIRE_STREAK. A wrong word resets
  the streak and the tier.
- **The record turns at one speed** (owner: steady, as New Rules' Rhyme) and has no remix arrows.
- **Grade:** 0-10, the thresholds reached (GRADE_THRESHOLDS, for SECONDS; tools/translate/x360_battle_tune.py set them so
  a player earns about the grade New Rules' own rules give, 8 x score / seconds, which the tiers would otherwise inflate),
  plus the story's first-play bonus (New Rules adds 2 the first time a game is played, as Spike's battle is), at most 10.

Phases as the practice's: it opens, shows its tutorial (held for a press), waits for a press, counts down, runs, spins
down, holds the score, and closes. The game's frames are 60 a second, whatever the player draws.
"""
from dataclasses import dataclass, field

from .x360_diss import (BLANK_FRAMES, CLOSING, CLOSING_MS, COUNTDOWN, COUNTDOWN_MS, ELEMENTS, END_WAIT_MS, ENDED,
                        INPUT_BLOCK_MS, OPENING, OPENING_MS, PUSH, PUSH_MS, READY, RUNNING,
                        SOUND_BAD, SOUND_GOOD, SPIN_DOWN, SPIN_DOWN_STEP, TUTORIAL, TUTORIAL_MS, WHEEL_START, arm_angle,
                        head)
import math

SECONDS = 40                            # New Rules' battle length
VELOCITY = 120                          # degrees a second: a word comes round every 3 s (the practice starts at 30); at
                                        # 90 even a perfect player reached only New Rules' grade 6 (x360_battle_tune.py)
SLOTS = (0, 1, 2, 3)                    # the record's four places the words ride (ELEMENTS' first four, a quarter apart)
WORDS = len(SLOTS)
POINTS, PENALTY = 3, 3                  # New Rules' Rhyme: +3 a right answer, -3 a wrong one
DOUBLE_STREAK, FIRE_STREAK = 5, 10      # right answers in a row before x2, then x3
CATCH_SPREAD = 45                       # degrees either side of the needle a word is caught (the arena's: a quarter each)
LAND_MS = max(PUSH, key=lambda point: point[1])[0]     # the arm's swing at its deepest: the needle on the words' ring
REDEAL_MS = 500                        # after a right answer, the record clears this long before the next words show
FIRST_PLAY_BONUS = 2                    # New Rules' first play of a game
NR_GRADE = (8, 1)                       # New Rules: grade = 8 x score / seconds (for the tuning's comparison)
# Score thresholds for grades 1-10 over SECONDS (x360_battle_tune.py, 12 games a skill level, 2026-11-16; see its docstring
# for how they were found). New Rules' own would be 5, 10, 15 ... 50. Grades 9 and 10 lie past what the best bot reached
# under New Rules' scoring (its 8), so they carry on at the top's ratio of the two scores.
GRADE_THRESHOLDS = (5, 10, 16, 24, 32, 41, 50, 70, 89, 99)
NO_WORD = -1


def nr_grade(score, seconds=SECONDS):
    """New Rules' Rhyme grade for a score, without the first-play bonus."""
    return min(10, NR_GRADE[0] * score // (NR_GRADE[1] * seconds))


def grade(score, thresholds=GRADE_THRESHOLDS):
    """This game's grade for a score, without the first-play bonus."""
    return sum(1 for threshold in thresholds if score >= threshold)


def _slot():
    return dict(word=NO_WORD, shown=NO_WORD, blank_frames=0)


@dataclass
class DissBattle:
    rounds: list = field(default_factory=list)      # [[target, rhyme, wrong, wrong, wrong], ...] the story's words
    bonus: int = 0                                  # added to the grade (FIRST_PLAY_BONUS for a first play)
    tiers: bool = True                              # False plays New Rules' own scoring (the tuning's comparison)
    phase: str = OPENING
    phase_ms: float | int = OPENING_MS               # (whole or fractional ms: the save loader checks types)
    started: bool = False
    tutorial: bool = True
    budget: int = 0                                 # time not yet played, in thirds of a ms
    now_thirds: int = 0
    prev_total_ms: int = 0
    total_time: int = SECONDS
    score: int = 0
    streak: int = 0                                 # right answers in a row
    tier: int = 1
    velocity: int = VELOCITY
    angle: float | int = WHEEL_START
    arm_ms: float | int = -1
    block_ms: float | int = 0
    order: list = field(default_factory=list)       # the rounds still to come, shuffled (a fresh shuffle when used up)
    round: int = -1                                 # the round showing (an index into rounds)
    words: list = field(default_factory=list)       # this round's words, [rhyme, wrong, wrong, wrong]
    slots: list = field(default_factory=lambda: [_slot() for _ in SLOTS])
    redeal_ms: float | int = 0
    touching: list = field(default_factory=list)    # (the practice's catch kept it; unused since the arena's, kept for saves)
    touched: int = -1
    right: int = 0                                  # for the score screen and the tuning
    wrong: int = 0
    effects: list = field(default_factory=list)     # for the renderer: [what, slot, ms]
    popup: list = field(default_factory=lambda: [0, 0])     # for the renderer: the tier shown, and since when
    sounds: list = field(default_factory=list)

    @classmethod
    def opened(cls, rounds, bonus=0, tutorial=True):
        if not rounds or any(len(r) != WORDS + 1 or len(set(r[1:])) != WORDS for r in rounds):
            raise ValueError('A Diss Battle needs rounds of a target, its rhyme and three different wrong words')
        return cls(rounds=[list(r) for r in rounds], bonus=bonus, tutorial=tutorial)

    @property
    def now_ms(self):
        return self.now_thirds // 3

    @property
    def target(self):
        return self.rounds[self.round][0] if self.round >= 0 else ''

    @property
    def result(self):
        """The grade the story reads, 0-10."""
        own = grade(self.score) if self.tiers else nr_grade(self.score)
        return min(10, own + self.bonus)

    def slot_at(self, index):
        """Slot `index`'s place (x, z) on the turning record."""
        x, z = ELEMENTS[SLOTS[index]]
        turn = math.radians(self.angle)
        return x * math.cos(turn) + z * math.sin(turn), -x * math.sin(turn) + z * math.cos(turn)

    # input, as the practice's
    def press(self):
        if self.phase == TUTORIAL:
            if self.phase_ms > 0:
                return False
            self.tutorial, self.started = False, True
            self._countdown()
            return True
        if self.phase == READY:
            return self.start()
        if self.phase == ENDED:
            self.phase, self.phase_ms = CLOSING, CLOSING_MS
            return True
        if self.phase != RUNNING or self.block_ms > 0:
            return False
        self.arm_ms = 0.0
        return True

    def start(self):
        if self.started:
            return False
        self.started = True
        if self.phase == READY:
            self._countdown()
        return True

    def _countdown(self):
        self.phase, self.phase_ms, self.block_ms = COUNTDOWN, COUNTDOWN_MS, INPUT_BLOCK_MS

    # time
    def tick(self, elapsed_ms, random):
        """Some time in the game's frames; True when it has finished and the story goes on."""
        self.budget += elapsed_ms * 3
        while self.budget >= 50:
            self.budget -= 50
            self.now_thirds += 50
            if self._frame(random):
                return True
        self.effects = [e for e in self.effects if self.now_ms - e[2] < 1200]
        return False

    def _frame(self, random):
        ms = 50 / 3
        self.phase_ms -= ms
        self.block_ms = max(0, self.block_ms - ms)
        if self.phase == OPENING:
            if self.phase_ms <= 0:
                if self.tutorial:
                    self.phase, self.phase_ms = TUTORIAL, TUTORIAL_MS
                elif self.started:
                    self._countdown()
                else:
                    self.phase = READY
            return False
        if self.phase == TUTORIAL:
            self.phase_ms = max(0, self.phase_ms)
            return False
        if self.phase == READY:
            return False
        if self.phase == COUNTDOWN:
            if self.phase_ms <= 0:
                self.prev_total_ms = self.now_ms
                self._deal(random)
                self.phase, self.phase_ms = RUNNING, 0
            return False
        if self.phase == ENDED:
            if self.phase_ms <= 0:
                self.phase, self.phase_ms = CLOSING, CLOSING_MS
            return False
        if self.phase == CLOSING:
            return self.phase_ms <= 0
        if self.arm_ms >= 0:
            self.arm_ms += ms
            if self.arm_ms >= PUSH_MS:
                self.arm_ms = -1
        if self.phase == SPIN_DOWN:
            if self.velocity > 0:
                self.velocity = max(0, self.velocity - SPIN_DOWN_STEP)
                self.angle = (self.angle + self.velocity * ms / 1000) % 360
            else:
                self.phase, self.phase_ms = ENDED, END_WAIT_MS
            return False
        self._trigger()
        self.angle = (self.angle + self.velocity * ms / 1000) % 360
        for slot in self.slots:
            if slot['blank_frames']:
                slot['blank_frames'] -= 1
                if not slot['blank_frames']:
                    slot['shown'] = NO_WORD
        if self.redeal_ms > 0:
            self.redeal_ms -= ms
            if self.redeal_ms <= 0:
                self._deal(random)
        if self.now_ms - self.prev_total_ms >= 1000:
            self.total_time -= 1
            self.prev_total_ms = self.now_ms
        if self.total_time < 1:
            self.phase, self.phase_ms = SPIN_DOWN, 0
            return False
        self._check_touch()
        return False

    def _trigger(self):
        """The Minigame Arena's catch (owner, 2026-11-16: the practice's, sized for notes, missed words the needle
        touched): as the needle lands on the record, the word nearest it, within CATCH_SPREAD degrees round the record.
        New Rules' Rhyme takes the word nearest its selector with a 360-degree window (nr_arena 727), so each of the four
        words owns a quarter of the record. A word gone blank there catches nothing."""
        if not self.arm_ms - 50 / 3 < LAND_MS <= self.arm_ms:
            return
        (hx, hz), _ = head(arm_angle(LAND_MS))
        needle = math.degrees(math.atan2(hz, hx))
        nearest, apart = -1, 180.0
        for index in range(WORDS):
            x, z = self.slot_at(index)
            gap = abs((math.degrees(math.atan2(z, x)) - needle + 180) % 360 - 180)
            if gap < apart:
                nearest, apart = index, gap
        if apart <= CATCH_SPREAD and self.slots[nearest]['word'] != NO_WORD:
            self.touched = nearest

    def _deal(self, random):
        """The next round: its four words in the four places, in a shuffled order."""
        if not self.order:
            self.order = list(range(len(self.rounds)))
            for i in range(len(self.order) - 1, 0, -1):
                j = random.below(i + 1)
                self.order[i], self.order[j] = self.order[j], self.order[i]
            if len(self.order) > 1 and self.order[-1] == self.round:     # never the same target twice running
                self.order[-1], self.order[0] = self.order[0], self.order[-1]
        self.round = self.order.pop()
        self.words = list(self.rounds[self.round][1:])
        places = list(range(WORDS))
        for i in range(WORDS - 1, 0, -1):
            j = random.below(i + 1)
            places[i], places[j] = places[j], places[i]
        for word, place in zip(range(WORDS), places):
            self.slots[place].update(word=word, shown=word, blank_frames=0)
        self.touching, self.touched = [], -1

    def _check_touch(self):
        if self.touched < 0:
            return
        index, self.touched = self.touched, -1
        slot = self.slots[index]
        word = slot['word']
        if word == NO_WORD:
            return
        if word == 0:                                   # the rhyme
            self.right += 1
            self.score += POINTS * (self.tier if self.tiers else 1)
            self.streak += 1
            self.effects.append(['good', index, self.now_ms])
            self.sounds.append(SOUND_GOOD[self.right % len(SOUND_GOOD)])
            tier = 3 if self.streak >= FIRE_STREAK else 2 if self.streak >= DOUBLE_STREAK else 1
            if self.tiers and tier != self.tier:
                self.tier = tier
                self.popup = [tier, self.now_ms]
            for other in self.slots:                    # the whole round leaves the record
                if other['word'] != NO_WORD:
                    other.update(word=NO_WORD, blank_frames=BLANK_FRAMES)
            self.redeal_ms = REDEAL_MS
        else:
            self.wrong += 1
            self.score = max(0, self.score - PENALTY)
            self.streak, self.tier = 0, 1
            self.effects.append(['bad', index, self.now_ms])
            self.sounds.append(SOUND_BAD)
            slot.update(word=NO_WORD, blank_frames=BLANK_FRAMES)

    def validate(self):
        if (self.phase not in (OPENING, TUTORIAL, READY, COUNTDOWN, RUNNING, SPIN_DOWN, ENDED, CLOSING)
                or not self.rounds or any(len(r) != WORDS + 1 for r in self.rounds)
                or len(self.slots) != WORDS or not 0 <= self.total_time <= SECONDS or self.score < 0
                or self.streak < 0 or self.tier not in (1, 2, 3) or not -1 <= self.round < len(self.rounds)
                or any(not 0 <= i < len(self.rounds) for i in self.order)
                or any(s['word'] not in range(NO_WORD, WORDS) or s['shown'] not in range(NO_WORD, WORDS)
                       for s in self.slots)
                or any(not 0 <= i < WORDS for i in self.touching) or not -1 <= self.touched < WORDS
                or not 0 <= self.bonus <= 10):
            raise ValueError('Invalid Diss Battle state')
