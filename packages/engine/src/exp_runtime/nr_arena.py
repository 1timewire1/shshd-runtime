"""shshd-runtime: New Rules' minigame arena panel (its panel type 27), driven by New Rules' own minigame library.

The panel is passive (docs/NEW_RULES.md): it keeps the ring, the timer, the score and meter, the
HUD, popups and a key queue, turns and counts them down each frame, and answers the library's property reads and writes
(New Rules services 50-57, here shshd-runtime's 200-207). Every rule of every game lives in the library's bytecode,
which runs beside the story as a linked segment (vm.linked_layout). Pure and headless; the player draws it
(desktop_nr_arena.py). Property and field meanings follow the Java panel (`h`, renamed `class_13`), cited by ID.
"""
from dataclasses import asdict, dataclass, field

SLOTS = 20                              # the panel's slot arrays (h[], 20 x 9 ints)
POPUPS = 20                             # its popups (i[], 20 x 9 ints)
KEYS = 20                               # its key queue
LABELS = 6                              # 690-695: three HUD text areas, then their 3 s flash labels
FLASH_MS = 3000
PRESS_MS = 250                          # an on-screen button's highlight after a press
BLINK_FREE_MS = 100000                  # 713/761's blink clock wraps here (field_558)
DEFAULT_PERIOD_MS = 4000                # 719 when the panel opens
# New Rules' entrance (class_13.method_383, transition -3 from the story's screen: field_611[2]): the bands slide in and
# the table settles. Meanwhile the panel neither draws nor runs, takes no keys, and the script waits. Leaving (718) runs
# transition -4 (field_611[3]) backwards, as long: the same tracks out again, before the story goes on.
ENTRANCE_MS = EXIT_MS = 2000
MOTIONS = (-1, 0, 1, 2)                 # 740's modes; -1, 0 and 1 are also the ring's direction (_set_motion)
SHAKE = 790                             # shshd-runtime's own property: shake the ring for v1 ms (New Rules' end at 772)
# The sound as "Time's up!" appears (owner, 2026-10-31): the New Rules addon's track #02 (translator MUSIC_BASE + 2),
# before the score's own jingle (#05, the library's).
TIME_UP_SOUND = 26982
TIME_UP_MS = 2000                     # how long "Time's up!" shows before the panel presses its OK (time_up)

# Nokia key codes (the Vivaz/J2ME canvas) as the panel queues them (class_22.method_546), and how 707 and 772 read
# them. The player passes these codes: OK / fire, soft keys, the arrows, and the number keys 0-9.
KEY_BITS = {-1: 1, -2: 2, -3: 4, -4: 8, -5: 16, -6: 32, -7: 64, -8: 524288, 42: 131072, 35: 262144,
            **{48 + n: 128 << n for n in range(10)}}
GAME_KEYS = {16: 1, 32: 1, 64: 2, 524288: 2, 1: 3, 2: 4, 4: 5, 8: 6}         # 707
NUMBER_KEYS = {256 << n: 8 + n for n in range(6)}                             # 772: keys 1-6
OK_KEYS, LEFT_KEY, RIGHT_KEY = (-5, -6), -3, -4

# Item kinds (723) and popup kinds.
PORTRAIT, PICTURE, TEXT = 1, 2, 3
POPUP_TEXT, POPUP_ITEM, POPUP_PICTURE = 1, 2, 3


@dataclass
class Popup:
    kind: int                           # POPUP_TEXT / POPUP_ITEM / POPUP_PICTURE
    value: int                          # a text index (strings), an item or a picture ID
    source: int                         # where it starts: a slot (>= 0) or a layout anchor (< 0), -32768 none
    target: int                         # where it goes: a slot or an anchor
    tint: int = -1                      # RGB, or -1
    elapsed_ms: int = 0
    duration_ms: int = 0                # 0: it stays until removed (748/749 with no duration)
    index: int = -1                     # 749: its place in a row of `count`
    count: int = 0


@dataclass
class NRArena:
    """The panel's state, as `h.a(boolean, boolean)` (open) leaves it and the properties change it."""
    open: bool = False
    margins: bool = False               # 50's first argument (field_592): the field keeps 10 px inside the frame
    score_display: int = 0              # 713 (field_435): 0 hidden, 1 shown, 2 blinking; 50's second argument sets 1
    labels: list = field(default_factory=lambda: [None] * LABELS)       # 690-695 (text or None)
    flash_ms: list = field(default_factory=lambda: [0] * 3)             # 693-695's remaining time
    hud: list = field(default_factory=lambda: [[-1, 0, 0, 0, 0, 0] for _ in range(3)])   # 696-701, per box
    strings: list = field(default_factory=list)                         # the text items' strings (field_563)
    item_kind: int = TEXT               # 723
    slots: list = field(default_factory=lambda: [-1] * 4)               # each slot's item (-1 empty); count = 729
    blink: list = field(default_factory=lambda: [0] * 4)                # 761
    tint: list = field(default_factory=lambda: [-1] * 4)                # 751
    moves: list = field(default_factory=lambda: [None] * 4)             # 747 to a slot: [from slot, angle, ms, total]
    period_ms: int = DEFAULT_PERIOD_MS  # 719: one full turn
    ring_size: int = 100                # 722, %
    angle: int = 0                      # ae: the ring's turn, degrees
    turn_carry_ms: int = 0              # field_587: time not yet worth a whole degree
    direction: int = 0                  # field_575: 1, -1 or 0
    motion: int = 0                     # 740: 0 stepped, 1 turning, -1 turning the other way, 2 still
    target_slot: int = 0                # field_576 (mode 0's left/right)
    target_angle: int = 0               # field_577 (af)
    selected: int = 0                   # 725
    under: int = 0                      # field_571: the slot nearest the selector
    window: int = 360                   # 727: the hit window, degrees
    plates: bool = True                 # 705
    wide: bool = False                  # 770
    timer_ms: int = -1                  # 710 (U); -1 no timer
    timer_total_ms: int = -1            # V
    timer_shown: bool = False           # field_554
    timer_paused: bool = False          # 712
    score: int = 0                      # 714
    meter: int = -1                     # 715 - 1
    target_marker: int = -1             # 716 - 1
    second_marker: int = -1             # 717 - 1
    max_ms: int = 0                     # field_549: the meter's "max" animation at 9 or more
    blink_clock_ms: int = BLINK_FREE_MS     # field_558
    buttons: int = 3                    # field_438: bit 0 the OK style, bits 1-4 the four buttons, 8/16 the arrows,
                                        # 32 << i a button's press highlight, 512 hides the right soft key
    button_ms: list = field(default_factory=lambda: [-1] * 4)          # field_436
    feedback: int = 0                   # 708: 1 green, 2 red
    no_highlight: bool = False          # 730
    ok_shown: bool = True               # 769
    keypad: bool = False                # 765
    keypad_flash: int = -1              # 766
    keypad_flash_ms: int = 0
    soft_key: bool = False              # 771
    unknown_768: int = 1                # 768 (field_591), not drawn
    popups: list[Popup] = field(default_factory=list)                   # at most POPUPS
    bubbles: list = field(default_factory=lambda: [None, None])         # 762/763: [text, slot, flags]
    keys: list = field(default_factory=list)                            # queued key bits, at most KEYS
    elapsed_ms: int = 0                 # 721, read and cleared
    entrance_ms: int = ENTRANCE_MS      # how far the entrance has run (ENTRANCE_MS: done)
    exit_ms: int = -1                   # how far the exit has run, once 718 has closed the panel (-1: open)
    pictures: list = field(default_factory=list)                        # 767's list (preload hints)
    # shshd-runtime (owner, 2026-10-31): from the "Time's up!" bubble to "your score" the panel takes no presses, so a
    # last tap can't skip them; it presses the first bubble's OK itself after TIME_UP_MS. 0 until then (a new timer
    # resets it), 1 holding, 2 after "your score".
    time_up: int = 0
    time_up_ms: int = -1
    sounds: list = field(default_factory=list)          # sound effects the panel asks for, which the engine takes
    # shshd-runtime (owner, 2026-10-31): SHAKE shakes the ring as Rhythm's frame loop does, for the games whose loop
    # has no shake of its own (the translator adds it to Rhyme's wrong answers).
    shake_ms: int = 0
    shake_base: int = 100               # 722 as the library set it; the ring's size between shakes
    shake_seed: int = 1

    # -- opening and the clock ---------------------------------------------------------------------------------------
    @classmethod
    def opened(cls, margins: bool, score: bool) -> 'NRArena':
        """Service 50: a fresh panel (`h.a(boolean, boolean)`)."""
        arena = cls(open=True, margins=margins, score_display=1 if score else 0, entrance_ms=0)
        arena._set_motion(0)
        return arena

    @property
    def entering(self) -> bool:
        return self.entrance_ms < ENTRANCE_MS

    def enter(self, elapsed_ms: int) -> bool:
        """The entrance's clock (class_13.method_377); True once it has run its course."""
        self.entrance_ms = min(ENTRANCE_MS, self.entrance_ms + max(0, elapsed_ms))
        return not self.entering

    @property
    def leaving(self) -> bool:
        return self.exit_ms >= 0

    def leave(self, elapsed_ms: int) -> bool:
        """The exit's clock; True once it has run its course."""
        self.exit_ms = min(EXIT_MS, max(0, self.exit_ms) + max(0, elapsed_ms))
        return self.exit_ms >= EXIT_MS

    def tick(self, elapsed_ms: int) -> None:
        """One frame (h's update, case 25 state 11)."""
        dt = elapsed_ms
        self.blink_clock_ms -= dt
        if self.blink_clock_ms < 0:
            self.blink_clock_ms += BLINK_FREE_MS
        for popup in list(self.popups):
            if popup.duration_ms > 0:
                popup.elapsed_ms += dt
                if popup.elapsed_ms >= popup.duration_ms:
                    self.popups.remove(popup)
        degrees = (self.turn_carry_ms + dt) * 360 // self.period_ms if self.period_ms > 0 else 0
        self.turn_carry_ms = self.turn_carry_ms + dt if degrees == 0 else 0
        self.angle = (self.angle + degrees * self.direction) % 360
        if self.motion == 0 and self.direction:
            ahead = (self.target_angle - self.angle) % 360
            if (self.direction == 1 and ahead > 180) or (self.direction == -1 and 0 < ahead < 180):
                self.direction, self.angle = 0, self.target_angle
        self.under = self.slot_under()
        for i in range(3):
            if self.flash_ms[i] > 0:
                self.flash_ms[i] -= dt
                if self.flash_ms[i] <= 0:
                    self.flash_ms[i] = 0
                    self.labels[i + 3] = None
        if self.timer_ms > 0 and not self.timer_paused:
            self.timer_ms = max(0, self.timer_ms - dt)
        for i, move in enumerate(self.moves):
            if move is not None:
                move[2] += dt
                if move[2] >= move[3]:
                    self.moves[i] = None
        if not self.no_highlight:
            for i in range(4):
                if self.button_ms[i] >= 0:
                    if self.button_ms[i] == 0:
                        self.button_ms[i] = PRESS_MS
                    else:
                        self.button_ms[i] -= dt
                        if self.button_ms[i] <= 0:
                            self.button_ms[i] = -1
                            if i == 0:
                                self.feedback = 0
                            self.buttons &= ~(32 << i)
        if self.meter >= 9:
            self.max_ms += dt
        if self.keypad_flash_ms > 0:
            self.keypad_flash_ms = max(0, self.keypad_flash_ms - dt)
        if self.shake_ms > 0:
            self.shake_ms = max(0, self.shake_ms - dt)
            if self.shake_ms == 0:
                self.ring_size = self.shake_base
            else:
                # Rhythm's own shake (its frame loop): 722 = 100 - (random(30) - 15) each frame, here round the
                # ring's size and from the panel's own generator (it only moves the picture).
                self.shake_seed = (self.shake_seed * 1103515245 + 12345) & 0x7FFFFFFF
                self.ring_size = max(3, self.shake_base - ((self.shake_seed >> 16) % 30 - 15))
        if self.time_up_ms >= 0:
            self.time_up_ms += dt
            if self.time_up_ms >= TIME_UP_MS:
                self.time_up_ms = -1
                self.keys.append(KEY_BITS[OK_KEYS[0]])        # the bubble's OK, until "your score" ends the hold
        self.elapsed_ms = min(0x7FFF, self.elapsed_ms + dt)

    def slot_under(self) -> int:
        count = len(self.slots)
        if count == 0:
            return 0
        under = (360 - self.angle + 360 // count // 2) * count // 360
        return 0 if under == count else under

    def slot_angle(self, slot: int) -> int:
        """Where a slot sits on the ring, degrees (90 is the front, the selector's place)."""
        return (self.angle + 90 + slot * (360 // len(self.slots))) % 360

    # -- input -------------------------------------------------------------------------------------------------------
    def press(self, key_code: int) -> None:
        """A key press (a Nokia key code, KEY_BITS), as the panel takes it (`method_373` case 25)."""
        bits = KEY_BITS.get(key_code)
        if bits is None or self.time_up == 1:
            return
        button = -1
        if bits in (16, 32):
            button, self.feedback = 0, 0
        elif bits in (4, 8):
            if self.motion == 0 and not self.buttons & 1:
                step = -1 if bits == 8 else 1
                if self.direction == 0:
                    self.target_slot = self.under + step
                elif self.direction == step:
                    self.target_slot += step
                self.direction = -step
                self.target_slot %= len(self.slots) or 1
                self.target_angle = 360 - self.target_slot * 360 // max(1, len(self.slots))
            button = 3 if bits == 8 else 2
        if not self.no_highlight and button != -1:
            self.button_ms[button] = 0
            self.buttons |= 32 << button
            if button == 0:
                self.button_ms[1] = 0
                self.buttons |= 64
        if len(self.keys) < KEYS - 1:
            self.keys.append(bits)

    def _next_key(self, numbers: bool) -> int:
        if not self.keys:
            return -1
        bits = self.keys.pop(0)
        return (NUMBER_KEYS if numbers else GAME_KEYS).get(bits, 0)

    # -- properties --------------------------------------------------------------------------------------------------
    def get(self, prop: int) -> int:
        """Service 53 (`method_453`)."""
        if prop in (707, 772):
            return self._next_key(prop == 772)
        if prop == 710:
            return (self.timer_ms + 999) // 1000
        if prop == 714:
            return self.score
        if prop == 719:
            return self.period_ms
        if prop == 721:
            elapsed, self.elapsed_ms = self.elapsed_ms, 0
            return elapsed
        if prop == 722:
            return self.shake_base if self.shake_ms > 0 else self.ring_size
        if prop == 723:
            return self.item_kind
        if prop == 724:
            return self.slots[self.selected] if 0 <= self.selected < len(self.slots) else -1
        if prop == 725:
            return self.selected
        if prop == 726:
            count = len(self.slots)
            if count and (self.angle + self.window // 2) % (360 // count) <= self.window:
                return self.under
            return -1
        if prop == 727:
            count = len(self.slots)
            return (self.angle + self.window // 2) % (360 // count) if count else 0
        if prop == 729:
            return len(self.slots)
        if prop == 740:
            return self.motion
        return 0

    def item(self, slot: int) -> int:
        """Service 54."""
        return self.slots[slot] if 0 <= slot < len(self.slots) else 0

    def set_item(self, slot: int, value: int) -> None:
        """Service 55 with a number (`method_455`)."""
        if 0 <= slot < len(self.slots):
            self.slots[slot] = value

    def set_text_item(self, slot: int, text: str) -> None:
        """Service 55 with text, on a text ring (`method_456`)."""
        self.set_item(slot, self.text_index(text))

    def text_index(self, text):
        if text is None:
            return -1
        if text not in self.strings:
            self.strings.append(text)
        return self.strings.index(text)

    def set_label(self, label_id: int, text) -> None:
        """Service 51 (`method_452`): 690-692 the HUD's text areas, 693-695 their 3 s flash labels."""
        index = label_id - 690
        if not 0 <= index < LABELS:
            return
        if index >= 3:
            self.flash_ms[index - 3] = FLASH_MS if text is not None else 0
        self.labels[index] = text

    def set(self, slot: int, prop: int, v1: int, v2: int = -1, v3: int = -1, *, text=None) -> bool:
        """Services 52, 56 and 57 (`method_459`). `text`: the string a text-taking property names (747, 762, 763),
        resolved by the caller. Returns True when the panel closes (718)."""
        if slot == -10:
            slot = self.selected
        if 696 <= prop <= 700:
            if 0 <= slot < 3:
                self.hud[slot][prop - 696] = v1
        elif prop == 701:
            if 0 <= slot < 3:
                self.hud[slot][5] = (self.hud[slot][5] & ~1) | (1 if v1 else 0)
        elif prop == 705:
            self.plates = v1 != 0
        elif prop == 706:
            self.buttons ^= v1 if self.no_highlight else v1 & 30
        elif prop == 708:
            self.feedback = v1
        elif prop == 710:
            if v1 > 0:
                self.timer_ms = self.timer_total_ms = v1 * 1000
                self.timer_shown = True
                self.time_up = 0
            else:
                self.timer_ms, self.timer_shown = -1, False
        elif prop == 712:
            self.timer_paused = v1 != 0
        elif prop == 713:
            self.score_display, self.blink_clock_ms = v1, BLINK_FREE_MS
        elif prop == 714:
            self.score = v1
        elif prop == 715:
            if self.meter < 9 and v1 == 10:
                self.max_ms = 0
            self.meter = v1 - 1
        elif prop == 716:
            self.target_marker = v1 - 1
        elif prop == 717:
            self.second_marker = v1 - 1
        elif prop == 718:
            self.open = False
            return True
        elif prop == 719:
            self.period_ms = v1
        elif prop == 720:
            self.buttons &= ~(512 | 1)
            if v1 <= 0:
                self.buttons |= 1 | (512 if v1 < 0 else 0)
        elif prop == 722:
            self.ring_size = max(3, v1)
            if self.shake_ms > 0:
                self.shake_base = self.ring_size
        elif prop == SHAKE:
            if self.shake_ms <= 0:
                self.shake_base = self.ring_size
            self.shake_ms = max(0, v1)
        elif prop == 723:
            self.item_kind = v1
        elif prop == 724:
            self.set_item(slot, v1)
        elif prop == 725:
            self.selected = v1
        elif prop == 726:
            count = len(self.slots)
            self.under = v1
            if count:
                self.angle = (360 - v1 * 360 // count) % 360
            if self.motion in (0, 2):
                self.direction = 0
        elif prop == 727:
            self.window = v1
        elif prop == 729:
            self._resize(slot, v1)
        elif prop == 730:
            self.no_highlight = v1 != 0
        elif prop == 740:
            self._set_motion(v1)
        elif prop == 747:
            self._move(slot, v1, v2, text)
        elif prop == 748:
            self._popup(Popup(POPUP_PICTURE, v1, slot, slot, duration_ms=max(0, v2)))
        elif prop == 749:
            self._popup(Popup(POPUP_PICTURE, v1, slot, slot, index=v2, count=v3))
        elif prop == 750:
            self.popups = [p for p in self.popups if not (v1 == -1 or p.kind == v1)]     # by kind (i[n * 9])
        elif prop == 751:
            if 0 <= slot < len(self.slots):
                self.tint[slot] = ((v1 & 255) << 16 | (v2 & 255) << 8 | v3 & 255) if min(v1, v2, v3) >= 0 else -1
        elif prop == 761:
            if 0 <= slot < len(self.slots):
                self.blink[slot] = v1
                self.blink_clock_ms = BLINK_FREE_MS
        elif prop in (762, 763):
            self.bubbles[prop - 762] = [text, v2, v3] if text else None
            if text:
                self._bubble_shown()
        elif prop == 764:
            pass                                    # a picture preload hint
        elif prop == 765:
            self.keypad = v1 != 0
        elif prop == 766:
            self.keypad_flash, self.keypad_flash_ms = v1, 500
        elif prop == 767:
            if v1 not in self.pictures and len(self.pictures) < 20:
                self.pictures.append(v1)
        elif prop == 768:
            self.unknown_768 = v1
        elif prop == 769:
            self.ok_shown = v1 != 0
            self.buttons = self.buttons | 2 if v1 else self.buttons & ~2
        elif prop == 770:
            self.wide = v1 != 0
        elif prop == 771:
            self.soft_key = v1 != 0
        return False

    def _bubble_shown(self) -> None:
        """A bubble has appeared. The first once the timer has run out ("Time's up!") holds the input (TIME_UP_MS);
        the next ("your score: ...") ends the hold. Both drop the presses queued before them."""
        if self.timer_ms != 0 or self.timer_total_ms <= 0:
            return
        if self.time_up == 0:
            self.time_up, self.time_up_ms = 1, 0
            self.keys.clear()
            self.sounds.append(TIME_UP_SOUND)
        elif self.time_up == 1:
            self.time_up, self.time_up_ms = 2, -1
            self.keys.clear()

    def _set_motion(self, mode: int) -> None:
        """740 (`method_434`): the arrows show in the stepped mode only."""
        self.motion = mode
        if mode == 2:
            self.direction = 0
        else:
            self.direction = mode
            self.buttons = self.buttons | 8 | 16 if mode == 0 else self.buttons & ~(8 | 16)

    def _resize(self, slot: int, value: int) -> None:
        """729: (slot, 1) inserts an empty slot there, (slot, 0) removes it, (_, n > 1) sets n empty slots."""
        lists = (self.slots, self.blink, self.tint, self.moves)
        if value == 1:
            if len(self.slots) < SLOTS:
                for values, empty in zip(lists, (-1, 0, -1, None)):
                    values.insert(max(0, min(slot, len(values))), empty)
        elif value != 0:
            count = max(1, min(SLOTS, value))
            self.slots, self.blink, self.tint, self.moves = [-1] * count, [0] * count, [-1] * count, [None] * count
        elif len(self.slots) > 1 and 0 <= slot < len(self.slots):
            for values in lists:
                del values[slot]
        self.under = self.slot_under()

    def _move(self, slot: int, target: int, duration_ms: int, text) -> None:
        """747: an item glides from `slot` to slot `target`, or a popup flies from `slot` to a layout anchor: its text
        if there is one, else a copy of the slot's item."""
        if target >= 0:
            if 0 <= target < len(self.slots):
                self.moves[target] = [slot, self.angle, 0, max(1, duration_ms)]
            return
        if text:
            self._popup(Popup(POPUP_TEXT, self.text_index(text), -32768 if slot < 0 else slot, target,
                              duration_ms=max(0, duration_ms)))
        elif 0 <= slot < len(self.slots):
            self._popup(Popup(POPUP_ITEM, self.slots[slot], slot, target, tint=self.tint[slot],
                              duration_ms=max(0, duration_ms)))

    def _popup(self, popup: Popup) -> None:
        if len(self.popups) < POPUPS:
            self.popups.append(popup)

    # -- saves -------------------------------------------------------------------------------------------------------
    def to_data(self) -> dict:
        return asdict(self)

    @classmethod
    def from_data(cls, data: dict) -> 'NRArena':
        data = dict(data)
        data['popups'] = [Popup(**popup) for popup in data.get('popups', [])]
        arena = cls(**data)
        arena.validate()
        return arena

    def validate(self) -> None:
        count = len(self.slots)
        if (not 1 <= count <= SLOTS or len(self.blink) != count or len(self.tint) != count
                or len(self.moves) != count or len(self.labels) != LABELS or len(self.flash_ms) != 3
                or len(self.hud) != 3 or any(len(box) != 6 for box in self.hud)
                or len(self.popups) > POPUPS or len(self.keys) > KEYS or len(self.bubbles) != 2 or len(self.sounds) > 4
                or not 0 <= self.angle < 360 or self.direction not in (-1, 0, 1) or self.motion not in MOTIONS
                or self.item_kind not in (PORTRAIT, PICTURE, TEXT) or self.time_up not in (0, 1, 2)
                or self.time_up_ms < -1 or self.shake_ms < 0 or self.shake_base < 3):
            raise ValueError('Invalid New Rules arena state')
