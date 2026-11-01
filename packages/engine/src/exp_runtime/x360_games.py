"""shshd-runtime: the cancelled Xbox 360 game's minigames, as translated stories call them (service X360_SLOT behind
service 70 selector X360_MINIGAMES_QUERY, which only this player answers; other players take the story's timed choice).

The slot machine is MS3's `gameSHS.RunSlotMachineMinigame` and `SelectInSlotMachineMinigame` (data/scripts/
common_functions.lua; MS4 deleted them), with Dating Beth's arguments (event3: a 0.5 s first period, 15 s, a speed factor
of 1.4). Five slots fill in turn. The one in focus cycles bulb, cross, question, each slot faster than the last. A press
takes what shows: a bulb scores +1 and moves on, a cross -1 and moves on, a question scores nothing and stays. After a
press nothing is in focus for 0.8 s and presses do nothing.

Its Lua's order is kept, oddities included: a press sets the option back to the first while the period's `Wait` is still
running, and when that ends the option steps on, so the next slot opens on the cross.
"""
from dataclasses import dataclass, field

X360_MINIGAMES_QUERY = 201
X360_SLOT = 214

BULB, CROSS, QUESTION = 0, 1, 2
OFF = -1                                # a slot not reached: menus/icons/bulb_off
OPTIONS = 3
SLOTS = 5
POINTS = {BULB: 1, CROSS: -1, QUESTION: 0}
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
OPENING, RUNNING, CLOSING, TIME_UP = 'opening', 'running', 'closing', 'time_up'


def period_ms(slot):
    """How long slot `slot` (1-5) shows each option: speed / speedFactor ^ (slot - 1)."""
    return round(FIRST_PERIOD_MS / SPEED_FACTOR ** (slot - 1))


@dataclass
class SlotMachine:
    phase: str = OPENING
    phase_ms: int = OPENING_MS          # what's left of the opening, the closing wait or the time-up
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
        """What the story's `gameStats.choice` holds: the points, below zero if the crosses have it."""
        return self.points

    def press(self):
        """SelectInSlotMachineMinigame."""
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

    def tick(self, elapsed_ms):
        """One frame; True when the machine has finished and the story goes on."""
        self.flash_ms = max(0, self.flash_ms - elapsed_ms)
        if self.phase == OPENING:
            self.phase_ms -= elapsed_ms
            if self.phase_ms <= 0:
                self.phase = RUNNING
                self.sounds.append(SOUND_TIMER)
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
        if (self.phase not in (OPENING, RUNNING, CLOSING, TIME_UP) or not 0 <= self.clock_ms <= DURATION_MS
                or not 1 <= self.slot <= SLOTS + 1 or not 0 <= self.option < OPTIONS or len(self.shown) != SLOTS
                or any(picture not in (OFF, BULB, CROSS, QUESTION) for picture in self.shown)):
            raise ValueError('Invalid slot machine state')
