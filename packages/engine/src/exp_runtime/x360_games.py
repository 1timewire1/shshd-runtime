"""shshd-runtime: the cancelled Xbox 360 game's minigames, as translated stories call them (service X360_SLOT behind
service 70 selector X360_MINIGAMES_QUERY, which only this player answers; other players take the story's timed choice).

The slot machine is MS3's `gameSHS.RunSlotMachineMinigame` and `SelectInSlotMachineMinigame` (data/scripts/
common_functions.lua; MS4 deleted them), with Dating Beth's arguments (event3: a 0.5 s first period, 15 s, a speed factor
of 1.4). Five slots fill in turn. The one in focus cycles bulb, cross, question, each slot faster than the last. A press
takes what shows: a bulb scores +1 and moves on, a cross scores nothing and moves on, a question scores nothing and
stays. After a press nothing is in focus for 0.8 s and presses do nothing.

Two changes from MS3 (owner, 2026-11-01). A cross costs nothing, where MS3 takes a point: five slots at +1 and -1 can only
total an odd number, so its middle result of 2 could not be reached by finishing. And the clock waits for a press once
the machine has opened, unless the skip prompt's Play has already said so; MS3 starts it at once.

Its Lua's order is kept, oddities included: a press sets the option back to the first while the period's `Wait` is still
running, and when that ends the option steps on, so the next slot opens on the cross.

The leash is MS3's and MS4's `gameSHS.RunSmashButtonMinigame` with Dating Beth's arguments (event4), the same in both, and
their native `IsButtonSmashPressed` with the shake check at the end of the game manager's update. The level starts at 50
and the game ends at 100 (won) or 0 (lost). A frame with a shake adds 7; any other loses 12 a second. The wanted shake
starts left and right and swaps with up and down every 2 to 5 seconds, picked once for the game. A shake is a new
direction on the same axis as the last, reached within 0.1 s of that last one; any new direction restarts the 0.1 s.

Changes from the prototype (owner, 2026-11-01): the clock waits for a press as the slot machine's does. A controller's stick
keeps the 0.1 s; a D-pad, keys and a drag have SHAKE_WINDOW_MS, since the player has no stick to flick there. The
animations that the level's turns play on the 3D Zack, doberman and collar are not here.
"""
from dataclasses import dataclass, field

from .x360_services import X360_LEASH, X360_MINIGAMES_QUERY, X360_SLOT  # noqa: F401


BULB, CROSS, QUESTION = 0, 1, 2
OFF = -1                                # a slot not reached: menus/icons/bulb_off
OPTIONS = 3
SLOTS = 5
POINTS = {BULB: 1, CROSS: 0, QUESTION: 0}
ADVANCE = {BULB: 1, CROSS: 1, QUESTION: 0}
FIRST_PERIOD_MS, SPEED_FACTOR = 500, 1.4
DURATION_MS = 15000
OPENING_MS = 500                        # `Wait(0.5)`, the machine showing before its clock starts
DELAY_MS = 800                          # gameSHS._vars.DelayOnSlotMachine
TIME_UP_MS = 3000                       # slotmachine/timeup's Wait(3)
FLASH_MS = 150                          # the slot's GroupCommand.2: three 0.05 s blinks as it is taken
TIMER_LOOP_MS = 926                     # gui/timer.wav, looping while the clock shows
# The sounds, in the X360 addon (tools/translate/x360_arena_art.py SLOT_SOUNDS).
SOUND_SUCCESS, SOUND_MISS, SOUND_TIMER = 26427, 26428, 26429
OPENING, READY, RUNNING, CLOSING, TIME_UP = 'opening', 'ready', 'running', 'closing', 'time_up'

LEFT, RIGHT, UP, DOWN = 'left', 'right', 'up', 'down'
LEFT_RIGHT, UP_DOWN = 0, 1
AXIS = {LEFT: LEFT_RIGHT, RIGHT: LEFT_RIGHT, UP: UP_DOWN, DOWN: UP_DOWN}
LEVEL_FULL = 100000                     # the level in thousandths: 0 to 100
LEVEL_START = 50000
LEVEL_GAIN = 7000                       # increaseValue
LEVEL_DRAIN_PER_MS = 12                 # decreaseRate, 12 a second
SHAKE_WINDOW_STICK_MS = 100             # the native check's 0.1 s
SHAKE_WINDOW_MS = 250
CLOSING_LEASH_MS = 300                  # (the prototype closes at once: the full or empty bar shows, then fades)


def period_ms(slot):
    """How long slot `slot` (1-5) shows each option: speed / speedFactor ^ (slot - 1)."""
    return round(FIRST_PERIOD_MS / SPEED_FACTOR ** (slot - 1))


@dataclass
class SlotMachine:
    phase: str = OPENING
    phase_ms: int = OPENING_MS          # what's left of the opening, the closing wait or the time-up
    started: bool = False               # the player has said go: the clock runs once the opening is over
    clock_ms: int = 0                   # how far the 15 s have gone
    slot: int = 1                       # gameSHS._vars.SMCurrentSlot
    option: int = BULB                  # SMCurrentOption
    focus: int = -1                     # SMCurrentFocusSlot: presses only count while it is `slot`
    wait_ms: int = 0                    # the period's Wait still running
    delay_ms: int = 0                   # what's left of DELAY_MS since a press
    points: int = 0                     # gameStats.choice
    shown: list[int] = field(default_factory=lambda: [OFF] * SLOTS)     # each slot's picture
    flash_slot: int = -1                # the slot just taken, blinking
    flash_ms: int = 0
    timer_ms: int = 0
    sounds: list[int] = field(default_factory=list)     # waiting for the session to play

    @property
    def result(self):
        """The bulbs taken, 0 to SLOTS. The story maps them onto its `gameStats.choice` (x360.SLOT_MACHINE_LEVELS)."""
        return self.points

    def press(self):
        """SelectInSlotMachineMinigame, or the go-ahead while it waits for one. Presses do nothing during the opening,
        so one left over from the dialogue before can't start it unseen."""
        if self.phase == READY:
            return self.start()
        if self.phase != RUNNING or self.focus != self.slot:
            return False
        option = self.option
        self.points += POINTS[option]
        if option != QUESTION:
            self.sounds.append(SOUND_SUCCESS if option == BULB else SOUND_MISS)
        self.flash_slot, self.flash_ms = self.slot - 1, FLASH_MS
        self.slot += ADVANCE[option]
        self.focus, self.option = -1, BULB
        self.delay_ms = DELAY_MS
        return True

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
        self.sounds.append(SOUND_TIMER)

    def tick(self, elapsed_ms):
        """One frame; True when the machine has finished and the story goes on."""
        self.flash_ms = max(0, self.flash_ms - elapsed_ms)
        if self.phase == OPENING:
            self.phase_ms -= elapsed_ms
            if self.phase_ms <= 0:
                if self.started:
                    self._run()
                else:
                    self.phase = READY
            return False
        if self.phase == READY:
            return False
        if self.phase in (CLOSING, TIME_UP):
            self.phase_ms -= elapsed_ms
            return self.phase_ms <= 0
        self.clock_ms = min(DURATION_MS, self.clock_ms + elapsed_ms)
        self.delay_ms = max(0, self.delay_ms - elapsed_ms)      # (the Lua's SMDelay is a time: it runs through a Wait)
        self.timer_ms += elapsed_ms
        if self.timer_ms >= TIMER_LOOP_MS:
            self.timer_ms -= TIMER_LOOP_MS
            self.sounds.append(SOUND_TIMER)
        if self.wait_ms > 0:                    # the period's Wait, then the option steps on
            self.wait_ms -= elapsed_ms
            if self.wait_ms > 0:
                return False
            self.option = (self.option + 1) % OPTIONS
        if self.clock_ms >= DURATION_MS:
            self.phase, self.phase_ms, self.focus = TIME_UP, TIME_UP_MS, -1             # slotmachine/timeup
        elif self.slot > SLOTS:
            self.phase, self.phase_ms, self.focus = CLOSING, DELAY_MS, -1               # Wait(DelayOnSlotMachine)
        elif self.delay_ms == 0:
            self.focus = self.slot
            self.shown[self.slot - 1] = self.option
            self.wait_ms = period_ms(self.slot)
        return False

    def validate(self):
        if (self.phase not in (OPENING, READY, RUNNING, CLOSING, TIME_UP) or not 0 <= self.clock_ms <= DURATION_MS
                or not 1 <= self.slot <= SLOTS + 1 or not 0 <= self.option < OPTIONS or len(self.shown) != SLOTS
                or any(picture not in (OFF, BULB, CROSS, QUESTION) for picture in self.shown)):
            raise ValueError('Invalid slot machine state')


@dataclass
class LeashGame:
    swap_ms: int                        # math.random(2,5), picked once: how long each wanted shake lasts
    phase: str = OPENING
    phase_ms: int = OPENING_MS          # what's left of the opening or the closing fade
    started: bool = False               # the player has said go: it runs once the opening is over
    level: int = LEVEL_START
    wanted: int = LEFT_RIGHT            # currentOption
    swap_left_ms: int = 0               # until the wanted shake swaps; set as it starts running
    last: str | None = None             # the last direction reached
    since_ms: int = 0                   # how long since the last direction was reached
    shook: bool = False                 # a shake this frame: it doesn't drain
    anim_ms: int = 0                    # the joystick icon's flipbook

    @property
    def result(self):
        """The story's `gameStats.choice`: dog_control/win's 1, dog_control/lose's 0."""
        return int(self.level >= LEVEL_FULL)

    def press(self):
        """OK: the go-ahead while it waits for one, and nothing else. As the slot machine's, it does nothing during the
        opening, so one left over from the dialogue before can't start it unseen."""
        return self.phase == READY and self.start()

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
        self.swap_left_ms = self.swap_ms

    def shake(self, direction, window_ms=SHAKE_WINDOW_MS):
        """The input has reached `direction`. True if that scored: the native check, with the input's own window."""
        if self.phase != RUNNING or direction == self.last:
            return False
        last, self.last = self.last, direction
        within, self.since_ms = self.since_ms < window_ms, 0
        if not within or last is None or AXIS[last] != AXIS[direction] or AXIS[direction] != self.wanted:
            return False
        self.level = min(LEVEL_FULL, self.level + LEVEL_GAIN)
        self.shook = True
        self._ended()
        return True

    def _ended(self):
        if not 0 < self.level < LEVEL_FULL:
            self.phase, self.phase_ms = CLOSING, CLOSING_LEASH_MS

    def tick(self, elapsed_ms):
        """One frame; True when the game has finished and the story goes on."""
        self.anim_ms = (self.anim_ms + elapsed_ms) % 60000
        if self.phase == OPENING:
            self.phase_ms -= elapsed_ms
            if self.phase_ms <= 0:
                if self.started:
                    self._run()
                else:
                    self.phase = READY
            return False
        if self.phase == READY:
            return False
        if self.phase == CLOSING:
            self.phase_ms -= elapsed_ms
            return self.phase_ms <= 0
        self.since_ms = min(60000, self.since_ms + elapsed_ms)
        if self.shook:
            self.shook = False
        else:
            self.level = max(0, self.level - LEVEL_DRAIN_PER_MS * elapsed_ms)
            self._ended()
        self.swap_left_ms -= elapsed_ms
        if self.swap_left_ms <= 0:
            self.wanted = 1 - self.wanted
            self.swap_left_ms = self.swap_ms
        return False

    def validate(self):
        if (self.phase not in (OPENING, READY, RUNNING, CLOSING) or not 0 <= self.level <= LEVEL_FULL
                or self.wanted not in (LEFT_RIGHT, UP_DOWN) or self.last not in (None, *AXIS) or self.swap_ms <= 0
                or self.since_ms < 0):
            raise ValueError('Invalid leash game state')
