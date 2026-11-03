"""shshd-runtime: the cancelled Xbox 360 game's Diss Practice, as translated stories call it (service X360_DISS behind
service 70 selector X360_MINIGAMES_QUERY; other players take the story's word game).

MS4's data/scripts/minigames/dissbattlepractice (game, element and wheel), line for line where a line decides anything,
as its HUD runs it (SetGameSystem(1)). Eight notes ride a record past a tone arm. Good ones score 10 x the streak x the
tier, speed the record up and build the streak; broken ones reset all three; remix arrows swap the two and turn the record
back the other way. A note goes blank when caught and comes back about 2 s later. 60 s.

The arm decides what's caught, as the X360's does: its head carries the trigger's box, a press swings it in over the rim
for about 55 ms of PUSH's 242, and a note is caught as its own box enters. The geometry is the map's and the deck model's
(docs/X360.md). The game's frames are 60 a second, whatever the player draws.

Bugs in the Lua, kept on purpose so the game plays as the X360's does (owner, 2026-11-02, after playing it); they aren't ours
to fix:
- The good-note cap never counts: `goodNotesTypeCount` only goes up in a swap.
- A swap makes the speed negative, so `Velocity >= 130` can't bring double notes until the next swap; on-fire notes still
  come at a streak of 20. A negative speed also ends the spin-down at once.
- SECONDS_TO_REBORN is 3, but a caught note's first second counts at once, on a clock left from before.

Changes (owner): it waits behind a press to start, where MS4 waits behind nothing but its countdown; MS4's tutorial is
held for a press as MS4 holds it, and is its go-ahead. The sounds are the ones MS4's effects play.
"""
from dataclasses import dataclass, field
import math

from .x360_games import CLOSING, OPENING, OPENING_MS, READY, RUNNING
from .x360_services import X360_DISS  # noqa: F401

TUTORIAL, COUNTDOWN, SPIN_DOWN, ENDED = 'tutorial', 'countdown', 'spin_down', 'ended'
PASS_SCORE = 5000                       # DBP:EndGame: over this, the level goes up
SECONDS = 60                            # totalTime
SCORE_VALUE = 10                        # ScoreValue
DEFAULT_VELOCITY, MAX_VELOCITY, VELOCITY_STEP = 30, 300, 10     # wheel.lua; degrees a second (the map's AngVel)
DOUBLE_VELOCITY, FIRE_STREAK = 130, 20
SPIN_DOWN_STEP = 2                      # Wheel:ReduceVelocityToStop, a frame
REBORN_SECONDS = 3                      # SECONDS_TO_REBORN
BLANK_FRAMES = 3                        # CheckTouch's WaitFrames(3)
MAX_BAD, MAX_REMIX, MAX_GOOD = 6, 3, 6
NOTE, BAD, REMIX, DOUBLE, FIRE, BLANK = 0, 1, 2, 3, 4, 5        # ElementType
GOOD_KINDS = (NOTE, DOUBLE, FIRE)
COUNTDOWN_STEPS_MS = (500, 750, 1000)   # the HUD's Waits for 3, 2, 1
COUNTDOWN_MS = sum(COUNTDOWN_STEPS_MS)
INPUT_BLOCK_MS = 3000                   # gui.BlockInputTimed(3), from when the countdown starts
TUTORIAL_MS = 5000                      # hud/tutorial's Waits, before `finished`
END_WAIT_MS = 3000                      # DBP:EndGame's Wait(3)
CLOSING_MS = 300
EFFECT_MS = 1200                        # how long a hit's effect is kept for the renderer
# The map, relative to the record's centre: (x, z), x to the right and z away from the camera. The elements' AttachPos.
WHEEL_START = 28.6765                   # minigame/wheel's Ang
ELEMENTS = ((0, .8), (-.8, 0), (.8, 0), (0, -.8), (-.6, -.6), (.6, .6), (.6, -.6), (-.6, .6))
ELEMENT_HEIGHT = .25                    # their AttachPos y, over the record
# The deck: Bone02's pivot, the head's distance along the arm (ResourcesPos) and the arm's direction from the pivot at rest.
PIVOT = (1.116, -.727)
ARM_LENGTH = 1.1
ARM_REST = 26.45
# The trigger's box on the head (CLP3 at 0.15 x 0.1 x 0.4, stood upright by ResourcesAng), along and across the arm, and a
# note's (0.15 each way, its upright side reaching the head): how near they overlap.
REACH_ALONG = .075 + .075
REACH_ACROSS = .05 + .075
# wheel_push.caf: (ms, degrees in over the record), at the trigger's AnimSpeed of 4.
PUSH = tuple((ms / 4, angle) for ms, angle in (
    (0, 0), (33, -4.13), (67, -8.26), (100, -7.29), (133, -4.69), (167, -.93), (200, 3.53), (233, 8.22), (267, 12.67),
    (300, 16.43), (333, 19.03), (367, 20), (400, 19.82), (433, 19.31), (467, 18.52), (500, 17.48), (533, 16.24),
    (567, 14.81), (600, 13.29), (633, 11.66), (667, 10.01), (700, 8.34), (733, 6.73), (767, 5.19), (800, 3.78),
    (833, 2.52), (867, 1.49), (900, .69), (933, .18), (967, 0)))
PUSH_MS = PUSH[-1][0]
# The sounds, in the X360 addon (tools/translate/x360_arena_art.py SOUNDS): a good note, a broken note, a remix arrow.
SOUND_GOOD, SOUND_BAD, SOUND_REMIX = (26380, 26381, 26382), 26383, 26384


def _element():
    return dict(kind=BLANK, shown=BLANK, blank_frames=0, prev_ms=0, own=0, born_ms=0)


def arm_angle(ms):
    """The arm's angle `ms` into PUSH (below 0: at rest)."""
    if ms < 0:
        return 0.0
    for (t0, a0), (t1, a1) in zip(PUSH, PUSH[1:]):
        if ms < t1:
            return a0 + (a1 - a0) * (ms - t0) / (t1 - t0)
    return 0.0


def head(angle):
    """The trigger's centre (x, z) and the arm's direction, with the arm at `angle`."""
    turn = math.radians(ARM_REST - angle)
    along = (-math.cos(turn), -math.sin(turn))
    return (PIVOT[0] + ARM_LENGTH * along[0], PIVOT[1] + ARM_LENGTH * along[1]), along


@dataclass
class DissPractice:
    phase: str = OPENING
    phase_ms: int = OPENING_MS
    started: bool = False
    tutorial: bool = False                          # the first practice's screen is still to come
    budget: int = 0                                 # time not yet played, in thirds of a ms
    now_thirds: int = 0                             # GetGameTotalTime, in thirds of a ms (a frame is 50)
    prev_total_ms: int = 0                          # prevTotalTime
    total_time: int = SECONDS                       # totalTime
    score: int = 0                                  # Score
    streak: int = 1                                 # countGoodOnes
    tier: int = 1                                   # GoodNotesType
    velocity: int = DEFAULT_VELOCITY                # Wheel.Velocity
    reversed: bool = False                          # Wheel.Direction left
    angle: float = WHEEL_START                      # the wheel's Ang
    arm_ms: float = -1                              # how far into PUSH, or -1 at rest
    block_ms: int = 0                               # BlockInputTimed
    elements: list = field(default_factory=lambda: [_element() for _ in ELEMENTS])
    touching: list = field(default_factory=list)    # the elements in the trigger, as it counts them
    touched: int = -1                               # elementTouched
    bad_count: int = 0                              # badNotesTypeCount
    remix_count: int = 0                            # directionTypeCount
    good_count: int = 0                             # goodNotesTypeCount
    effects: list = field(default_factory=list)     # for the renderer: [what, x, z, ms]
    popup: list = field(default_factory=lambda: [0, 0])     # for the renderer: the "x" streak shown, and since when
    sounds: list = field(default_factory=list)      # resources to play this tick, which the session takes

    @classmethod
    def opened(cls, tutorial):
        return cls(tutorial=tutorial)

    @property
    def now_ms(self):
        return self.now_thirds // 3

    @property
    def result(self):
        """The score, as far as a word holds it (the story only asks whether it's over PASS_SCORE)."""
        return min(self.score, 32767)

    def element_at(self, index):
        """Element `index`'s place (x, z) on the turning record."""
        x, z = ELEMENTS[index]
        turn = math.radians(self.angle)
        return x * math.cos(turn) + z * math.sin(turn), -x * math.sin(turn) + z * math.cos(turn)

    # input
    def press(self):
        """A go-ahead, or DBP:HitArrow."""
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
        self.arm_ms = 0.0                           # PlayAnimation(0,"PUSH",0): from its start, even during it
        return True

    def start(self):
        """The go-ahead: from the player's press, or from the skip prompt's Play."""
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
        self.effects = [e for e in self.effects if self.now_ms - e[3] < EFFECT_MS]
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
                self._begin(random)
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
            self._spin_down(ms)
            return False
        self._trigger()
        self._main_loop(ms, random)
        return False

    def _begin(self, random):
        """DBP:Init and DBP:Start, as the countdown ends."""
        self.prev_total_ms = self.now_ms
        for element in self.elements:
            self._deal(element, random)
        self.phase, self.phase_ms = RUNNING, 0
        self.velocity = -DEFAULT_VELOCITY if self.reversed else DEFAULT_VELOCITY

    def _spin_down(self, ms):
        """Wheel:ReduceVelocityToStop."""
        if self.velocity > 0:
            self.velocity -= SPIN_DOWN_STEP
            self.angle = (self.angle + self.velocity * ms / 1000) % 360
        else:
            self.phase, self.phase_ms = ENDED, END_WAIT_MS

    def _trigger(self):
        """minigame/trigger: SetCollided as a note enters it, RemoveCollided as one leaves."""
        (hx, hz), (ux, uz) = head(arm_angle(self.arm_ms))
        for index, element in enumerate(self.elements):
            inside = False
            if element['shown'] != BLANK:
                x, z = self.element_at(index)
                dx, dz = x - hx, z - hz
                inside = abs(dx * ux + dz * uz) < REACH_ALONG and abs(dz * ux - dx * uz) < REACH_ACROSS
            if inside and index not in self.touching:
                self.touching.append(index)
                self.touched = index
            elif not inside and index in self.touching:
                self.touching.remove(index)
                self.touched = -1

    def _main_loop(self, ms, random):
        """DBP:MainLoop, State 1."""
        self.angle = (self.angle + self.velocity * ms / 1000) % 360     # Wheel:RotateWheel
        for element in self.elements:
            self._step(element, random)
        if self.now_ms - self.prev_total_ms >= 1000:
            self.total_time -= 1
            self.prev_total_ms = self.now_ms
        if self.total_time < 1:
            self.phase, self.phase_ms = SPIN_DOWN, 0            # DBP:GameOver
            return
        self._check_touch(random)

    def _step(self, element, random):
        """Element:Step, and what's left of CheckTouch's WaitFrames(3)."""
        if element['blank_frames']:
            element['blank_frames'] -= 1
            if not element['blank_frames']:
                element['shown'], element['prev_ms'] = BLANK, self.now_ms
        if element['kind'] == BLANK:
            if self.now_ms - element['prev_ms'] >= 1000:
                element['own'] += 1
                element['prev_ms'] = self.now_ms
            if element['own'] == REBORN_SECONDS:
                self._deal(element, random)
                element['own'] = 0

    def _deal(self, element, random):
        """Element:Init."""
        while True:
            kind = random.below(3)
            if kind == NOTE:
                kind = {2: DOUBLE, 3: FIRE}.get(self.tier, NOTE)
                if self.good_count > MAX_GOOD:
                    self.good_count = MAX_GOOD
                    continue
            elif kind == BAD:
                self.bad_count += 1
                if self.bad_count > MAX_BAD:
                    self.bad_count = MAX_BAD
                    continue
            else:
                self.remix_count += 1
                if self.remix_count > MAX_REMIX:
                    self.remix_count = MAX_REMIX
                    continue
            break
        element.update(kind=kind, shown=kind, born_ms=self.now_ms)

    def _check_touch(self, random):
        """DBP:CheckTouch."""
        if self.touched < 0:
            return
        element = self.elements[self.touched]
        kind = element['kind']
        where = self.element_at(self.touched)
        if kind in GOOD_KINDS:
            self.good_count -= 1
            self._add_score(where, random)
        elif kind == BAD:
            self.bad_count -= 1
            self._bad_choice(where)
        elif kind == REMIX:
            self.remix_count -= 1
            self._change_direction(where)
        if kind != BLANK:
            element['kind'], element['blank_frames'] = BLANK, BLANK_FRAMES

    def _add_score(self, where, random):
        """DBP:AddScore."""
        self.effects.append(['good', where[0], where[1], self.now_ms])
        self.sounds.append(SOUND_GOOD[random.below(len(SOUND_GOOD))])
        self.score += SCORE_VALUE * self.streak * self.tier
        if abs(self.velocity) != MAX_VELOCITY:                  # Wheel:MoveFaster
            self.velocity += -VELOCITY_STEP if self.reversed else VELOCITY_STEP
        if self.streak > 1:
            self.popup = [self.streak, self.now_ms]
        if self.velocity >= DOUBLE_VELOCITY and self.tier == 1:
            self.tier = 2
            self._change_note_type(DOUBLE)
        elif self.streak >= FIRE_STREAK:
            self.tier = 3
            self._change_note_type(FIRE)
        self.streak += 1

    def _bad_choice(self, where):
        """DBP:BadChoise."""
        self.effects.append(['bad', where[0], where[1], self.now_ms])
        self.sounds.append(SOUND_BAD)
        self.tier = 1
        self._change_note_type(NOTE)
        self.velocity = -DEFAULT_VELOCITY if self.reversed else DEFAULT_VELOCITY
        self.streak = 1

    def _change_note_type(self, kind):
        for element in self.elements:
            if element['kind'] in GOOD_KINDS:
                element.update(kind=kind, shown=kind)

    def _change_direction(self, where):
        """DBP:ChangeDirection and Wheel:ChangeDirection."""
        self.effects.append(['swap', where[0], where[1], self.now_ms])
        self.sounds.append(SOUND_REMIX)
        bad = good = 0
        for element in self.elements:
            if element['kind'] == BAD:
                kind = {1: NOTE, 2: DOUBLE, 3: FIRE}[self.tier]
                element.update(kind=kind, shown=kind)
                good += 1
            elif element['kind'] in GOOD_KINDS:
                element.update(kind=BAD, shown=BAD)
                bad += 1
        self.bad_count, self.good_count = bad, good
        self.reversed = not self.reversed
        self.velocity = -self.velocity

    def validate(self):
        if (self.phase not in (OPENING, TUTORIAL, READY, COUNTDOWN, RUNNING, SPIN_DOWN, ENDED, CLOSING)
                or len(self.elements) != len(ELEMENTS) or not 0 <= self.total_time <= SECONDS or self.score < 0
                or self.streak < 1 or self.tier not in (1, 2, 3) or abs(self.velocity) > MAX_VELOCITY + VELOCITY_STEP
                or any(e['kind'] not in range(6) or e['shown'] not in range(6) for e in self.elements)
                or any(not 0 <= i < len(ELEMENTS) for i in self.touching) or not -1 <= self.touched < len(ELEMENTS)):
            raise ValueError('Invalid Diss Practice state')
