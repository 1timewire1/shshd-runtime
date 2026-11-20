"""shshd-runtime: Claire Hart Classic's hidden-object round (Claire Hart plan Stage 3; reference/Other Games/docs/
CLAIRE_HART_ROUNDS_PLAN.md). The rules of build 157's decompiled round: hogscene (picking, the list, the end), activeobjectlist
(its six names), touchdetector (the hit test, misclicks and the spam lock), combometer and score (finds and the combo), timer,
levelsummary (bonuses and stars), and the hint and power-ups (hintpowerup, zonehintpowerup, clickshintpowerup,
addobjectspowerup, addtimepowerup), with gamebalance.json's numbers. Nothing here draws (desktop_claire_round.py, Stage 3 step
3) or reads pictures: the player finds which objects lie under a tap (pixel_hit, against the add-on's sprites) and hands them
in, topmost first.

Three changes from Classic, the owner's (2026-11-20): the round's story objects are forced in (G2: Classic's lookup read the
wrong refs, so it never was); the hint may point at them (R5); and the power-ups, which Classic sold for gems, follow the
Power-Ups setting (R2: once each a round, unlimited, or off).
"""
from dataclasses import dataclass, field

# gamebalance.json: hogBalance, powerups, gameover, spamClickData
SOL_SIZE, AOL_SIZE = 12, 6              # objects to find, names listed at a time
ADD_OBJECTS = 6                         # Clairvoyance's extra objects, picked with the rest from the start
SPAM_LOCK_MS = 5000
SPAM_LONG_MS, SPAM_SHORT_MS, SPAM_SHORT_CLICKS = 6000, 1000, 6
MIN_BONUS_S, MAX_BONUS_S = 180, 360
FULL_TIME_BONUS, FULL_SKILL_BONUS = 1000, 1000
MAX_MISCLICKS, HALF_STAR_POINTS, MAX_HALF_STARS = 10, 600, 10
MINUTE_CAP = 99                         # timer.js stops at 99:59
# combometer.js: a find scores 100 x the multiplier, which then rises to 5; the bar drains in 10 s after a 0.1 s grace
FIND_POINTS, MAX_MULTIPLIER = 100, 5
COMBO_LEEWAY_S, COMBO_DRAIN_S = 0.1, 10
TIME_WARP_SLOWDOWN = 0.5                # addtimepowerup.js: the drain at half speed until the combo next empties
# A find's flight (FoundObjectPrefab's clip, objectClicked: 0.83 s), then its name fading out (aolhide: 0.25 s): the next
# name comes in after both (hogscene.objectRemoved).
FOUND_MS, NAME_HIDE_MS = 833, 250
HINT_REFILL_MS = 1170                   # hintpowerup's orb: hint_empty (0.17 s) then hint_full_fill (1 s), once its object is found
HIT_WINDOW = 9                          # touchdetector's 9 x 9 pixel window

# The Power-Ups setting (owner, 2026-11-20)
ONCE_EACH, UNLIMITED, OFF = 'once', 'unlimited', 'off'
POWERUP_MODES = (ONCE_EACH, UNLIMITED, OFF)
FOCUS, LOCATOR, CLAIRVOYANCE, TIME_WARP = 'focus', 'locator', 'clairvoyance', 'time_warp'
POWERUPS = (FOCUS, LOCATOR, CLAIRVOYANCE, TIME_WARP)

NO_OBJECT = -1

# A scene's sprites in `chcrounds` (one resource a scene: the add-on's IDs are 16 bits, its sprites 78,577): their original
# PNG files one after another, after an index. b'CHSP', a u32 count, then each sprite's u32 offset and length (big-endian).
SPRITE_PACK_MAGIC = b'CHSP'


def encode_sprite_pack(files):
    import struct
    head = len(SPRITE_PACK_MAGIC) + 4 + 8 * len(files)
    index, offset = bytearray(), head
    for data in files:
        index += struct.pack('>II', offset, len(data))
        offset += len(data)
    return SPRITE_PACK_MAGIC + struct.pack('>I', len(files)) + bytes(index) + b''.join(files)


def sprite_from_pack(pack, number):
    """Sprite `number`'s PNG bytes from a sprite pack."""
    import struct
    if pack[:4] != SPRITE_PACK_MAGIC:
        raise ValueError('Not a Claire Hart sprite pack')
    count, = struct.unpack_from('>I', pack, 4)
    if not 0 <= number < count:
        raise ValueError('No such sprite')
    offset, length = struct.unpack_from('>II', pack, 8 + 8 * number)
    if offset + length > len(pack):
        raise ValueError('A truncated sprite pack')
    return pack[offset:offset + length]


def pixel_hit(alpha, width, height, x, y):
    """touchdetector's test: whether any pixel of a `width` x `height` sprite within the 9 x 9 window centred on its pixel
    (`x`, `y`) (from its top left) is not fully transparent. `alpha(px, py)` gives a pixel's alpha. The caller has checked
    that the point lies in the sprite's box."""
    half = HIT_WINDOW // 2
    x, y = int(x), int(y)
    for py in range(max(0, y - half), min(height, y + half + 1)):
        for px in range(max(0, x - half), min(width, x + half + 1)):
            if alpha(px, py) > 0:
                return True
    return False


@dataclass
class ClaireRound:
    """One round. Objects are the scene's, by their place in the add-on's list for it; `picked` is hogscene's
    selectedIndices: the story objects first, then shuffled ones, 12 + Clairvoyance's 6 in all (fewer in a small scene)."""
    scene: str
    names: list[str]                    # every object's name, in the scene's order
    picked: list[int]
    story: list[int] = field(default_factory=list)
    powerups: str = ONCE_EACH
    sol_size: int = SOL_SIZE            # how many of `picked` are to be found (Clairvoyance adds ADD_OBJECTS)
    original_sol: int = SOL_SIZE
    next_index: int = 0                 # the next of `picked` to list
    slots: list[int] = field(default_factory=list)          # the six names: an object, or NO_OBJECT
    extra: list[bool] = field(default_factory=list)          # a slot's name in Clairvoyance's blue
    found: list[int] = field(default_factory=list)          # in the order found
    leaving: list[list[int]] = field(default_factory=list)  # [object, ms until its name leaves the list]
    chosen: list[int] = field(default_factory=list)         # objects a hint or power-up has pointed at (alreadyChosen)
    elapsed_ms: int = 0
    score: int = 0
    multiplier: int = 1
    combo: float = 0.0                  # the bar, 1 to 0
    leeway_s: float = 0.0
    combo_running: bool = False
    x5_finds: int = 0
    misclicks: int = 0
    clicks: list[int] = field(default_factory=list)         # misclick times, for the spam check
    lock_ms: int = 0                    # "Clicking Too Fast": taps do nothing until this is 0
    hint_target: int = NO_OBJECT
    hint_refill_ms: int = 0
    hints: int = 0
    focus_target: int = NO_OBJECT
    locator_target: int = NO_OBJECT
    locating: bool = False              # the Psychic Locator is waiting for a name to be picked
    used: dict[str, int] = field(default_factory=dict)
    time_warp: bool = False
    time_warp_can_end: bool = False
    over: bool = False
    finished: bool = False
    title: str = ''                     # the scene's name on its plate ("Claire's Office"), as Classic's round names it
    started: bool = False               # (the skip prompt is offered only before)

    # --- opening ----------------------------------------------------------------------------------------------------------
    @classmethod
    def opened(cls, scene, names, story, random, powerups=ONCE_EACH, title=''):
        """A round of the scene whose objects are `names`, with the story objects `story` (their places in it) forced in:
        hogscene.selectObjectList, its shuffle drawn from the session's `random` so a reload picks the same."""
        count = len(names)
        order = list(range(count))
        for i in range(count):                       # (each place swapped with a later one, as hogscene's loop)
            j = i + random.below(count - i)
            order[i], order[j] = order[j], order[i]
        total = min(max(1, SOL_SIZE + ADD_OBJECTS), count)
        picked = []
        for index in story:
            if 0 <= index < count and index not in picked:
                picked.append(index)
                order.remove(index)
        picked += order[:max(0, total - len(picked))]
        sol = min(SOL_SIZE, count)
        game = cls(scene, list(names), picked, [i for i in story if i in picked], powerups if powerups in POWERUP_MODES
                   else ONCE_EACH, sol, sol, slots=[NO_OBJECT] * min(AOL_SIZE, count), extra=[False] * min(AOL_SIZE, count))
        for _ in range(len(game.slots)):
            game._list_next()
        game.title = title or scene
        return game

    def _list_next(self):
        """addNextActiveObject: the next picked object into the first empty slot, blue past the first twelve."""
        if self.next_index >= len(self.picked) or NO_OBJECT not in self.slots:
            return False
        slot = self.slots.index(NO_OBJECT)
        self.slots[slot] = self.picked[self.next_index]
        if self.next_index + 1 > self.original_sol:
            self.extra[slot] = True
        self.next_index += 1
        return True

    # --- what's on screen -------------------------------------------------------------------------------------------------
    @property
    def listed(self):
        """The objects named in the list now (a found one stays until its name has left)."""
        return [o for o in self.slots if o != NO_OBJECT]

    @property
    def found_count(self):
        return len(self.found)

    @property
    def to_find(self):
        """"n/12 Items Found"'s 12: 18 once Clairvoyance is used."""
        return self.sol_size

    @property
    def seconds(self):
        """timer.js: whole seconds (rounded), stopping at 99:59."""
        return min(MINUTE_CAP * 60 + 59, (self.elapsed_ms + 500) // 1000)

    # --- time -------------------------------------------------------------------------------------------------------------
    def tick(self, elapsed_ms):
        """`elapsed_ms` of play (none while the game is paused)."""
        if self.finished:
            return
        if elapsed_ms > 0:
            self.started = True
        if not self.over:
            self.elapsed_ms += elapsed_ms
        self.lock_ms = max(0, self.lock_ms - elapsed_ms)
        self.hint_refill_ms = max(0, self.hint_refill_ms - elapsed_ms)
        self._drain(elapsed_ms / 1000)
        for item in self.leaving:
            item[1] -= elapsed_ms
        while self.leaving and self.leaving[0][1] <= 0:
            obj, _ = self.leaving.pop(0)
            self._remove(obj)

    def _drain(self, seconds):
        """combometer.globalUpdate / decrement."""
        if not self.combo_running or self.over:
            return
        # (Classic checks its grace once a frame; a longer tick drains only the part of it past the grace)
        past = seconds if self.leeway_s >= COMBO_LEEWAY_S else max(0.0, self.leeway_s + seconds - COMBO_LEEWAY_S)
        if past > 0:
            step = round((TIME_WARP_SLOWDOWN if self.time_warp else 1) * past * 10000) / 10000 / COMBO_DRAIN_S
            self.combo -= step
            if self.combo <= 0:
                self.combo, self.combo_running, self.multiplier = 0.0, False, 1
                if self.time_warp and self.time_warp_can_end:            # comboEmpty: Time Warp ends
                    self.time_warp = self.time_warp_can_end = False
        self.leeway_s += seconds

    def _remove(self, obj):
        """The found object's name leaves; hogscene.objectRemoved lists the next, or ends the round."""
        if obj in self.slots:
            slot = self.slots.index(obj)
            self.slots[slot] = NO_OBJECT
        if self.next_index < self.sol_size:
            self._list_next()
        elif not self.listed and not self.leaving:
            self.over = True
            self.combo, self.combo_running = 0.0, False

    # --- taps -------------------------------------------------------------------------------------------------------------
    def tap(self, under):
        """A tap on the scene: `under` are the objects whose sprites it hits (pixel_hit), topmost first. Returns the
        object found, else None (a misclick, counted, which may start the spam lock). touchdetector.onTouchEnd: only a
        picked object can be found, and only while its name is listed and it isn't found yet."""
        if self.over:
            return None
        for obj in under:
            if obj in self.picked and self._found(obj):
                return obj
        self.misclicks += 1
        self._spam_check()
        return None

    def _found(self, obj):
        """hogscene.objectClicked."""
        if self.lock_ms or obj in self.found or obj not in self.slots:
            return False
        self.found.append(obj)
        self.score += FIND_POINTS * self.multiplier                 # combometer.increment
        if self.multiplier == MAX_MULTIPLIER:
            self.x5_finds += 1
        self.multiplier = min(MAX_MULTIPLIER, self.multiplier + 1)
        self.combo, self.leeway_s, self.combo_running = 1.0, 0.0, True
        if self.time_warp:
            self.time_warp_can_end = True                           # addtimepowerup.allowPowerupDisable
        if obj == self.hint_target:
            self.hint_target = NO_OBJECT
            self.hint_refill_ms = HINT_REFILL_MS
        if obj == self.focus_target:
            self.focus_target = NO_OBJECT
        if obj == self.locator_target:
            self.locator_target = NO_OBJECT
        self.leaving.append([obj, FOUND_MS + NAME_HIDE_MS])
        return True

    def _spam_check(self):
        """touchdetector.detectSpamClick, on every misclick: 6 in 6 s (or 6 in 1 s) lock taps for 5 s."""
        now = self.elapsed_ms
        oldest = self.clicks[0] if self.clicks else 0
        self.clicks.append(now)
        if now - oldest < SPAM_LONG_MS and len(self.clicks) >= SPAM_SHORT_CLICKS:
            self.clicks = []
            self.lock_ms = SPAM_LOCK_MS
            return
        if len(self.clicks) >= SPAM_SHORT_CLICKS and now - self.clicks[-SPAM_SHORT_CLICKS] < SPAM_SHORT_MS:
            self.clicks = []
            self.lock_ms = SPAM_LOCK_MS
        if len(self.clicks) > 6:
            self.clicks = self.clicks[-1:]          # (Classic keeps only the newest here: splice(length - 1))

    # --- the hint and power-ups -------------------------------------------------------------------------------------------
    @property
    def marker_out(self):
        """The hint, Focus and the Psychic Locator lock one another while one's marker is out."""
        return self.locating or NO_OBJECT != self.hint_target or NO_OBJECT != self.focus_target \
            or NO_OBJECT != self.locator_target

    def _unchosen(self):
        """activeObjectList.getAllUnclickedObjectsOfType(..., true): listed, not found, not pointed at yet. Story objects
        too (R5; Classic left them out)."""
        return [o for o in self.listed if o not in self.found and o not in self.chosen]

    @property
    def hint_ready(self):
        return not self.over and not self.marker_out and not self.hint_refill_ms and bool(self._unchosen())

    def hint(self, random):
        """The free hint: a star onto a random listed object (at its hint offset), until it's found. Returns it, or None."""
        if not self.hint_ready:
            return None
        choices = self._unchosen()
        self.hint_target = choices[random.below(len(choices))]
        self.chosen.append(self.hint_target)
        self.hints += 1
        return self.hint_target

    def uses_left(self, powerup):
        """How many more times `powerup` can be used this round: None for any number."""
        if self.powerups == OFF:
            return 0
        if powerup == CLAIRVOYANCE or self.powerups == ONCE_EACH:
            return max(0, 1 - self.used.get(powerup, 0))
        return None

    def can_use(self, powerup):
        if self.over or self.uses_left(powerup) == 0:
            return False
        if powerup in (FOCUS, LOCATOR):
            return not self.marker_out and bool(self._unchosen() if powerup == FOCUS else self._findable())
        if powerup == CLAIRVOYANCE:
            return len(self.picked) > self.sol_size
        return not self.time_warp                           # Time Warp: not while it's on

    def _findable(self):
        return [o for o in self.listed if o not in self.found]

    def _use(self, powerup):
        self.used[powerup] = self.used.get(powerup, 0) + 1

    def focus(self, random):
        """Focus: the scene darkened but around a random listed object, its name blinking, until it's found."""
        if not self.can_use(FOCUS):
            return None
        choices = self._unchosen()
        self.focus_target = choices[random.below(len(choices))]
        self.chosen.append(self.focus_target)
        self._use(FOCUS)
        return self.focus_target

    def locate(self):
        """The Psychic Locator: every listed name glows, waiting for one to be picked (pick_located)."""
        if not self.can_use(LOCATOR):
            return False
        self.locating = True
        self._use(LOCATOR)
        return True

    def pick_located(self, slot):
        """A listed name picked for the Psychic Locator: a marker flies to its object. Returns it, or None."""
        if not self.locating or not 0 <= slot < len(self.slots):
            return None
        obj = self.slots[slot]
        if obj == NO_OBJECT or obj in self.found:
            return None
        self.locating = False
        self.locator_target = obj
        if obj not in self.chosen:
            self.chosen.append(obj)
        return obj

    def clairvoyance(self):
        """Clairvoyance: six more objects to find, named in blue (addobjectspowerup; hogscene.updateSOLSize)."""
        if not self.can_use(CLAIRVOYANCE):
            return False
        self._use(CLAIRVOYANCE)
        self.sol_size = min(len(self.picked), self.sol_size + ADD_OBJECTS)
        while len(self.listed) < len(self.slots) and self.next_index < self.sol_size and self._list_next():
            pass
        return True

    def warp_time(self):
        """Time Warp: the combo drains at half speed until it next runs out."""
        if not self.can_use(TIME_WARP):
            return False
        self._use(TIME_WARP)
        self.time_warp = True
        self.leeway_s = 0.0
        self.time_warp_can_end = self.combo > 0.02
        return True

    # --- the end ----------------------------------------------------------------------------------------------------------
    def summary(self):
        """levelsummary.js: the round's score, time bonus, skill bonus, total and half-stars."""
        seconds = self.seconds
        if seconds < MIN_BONUS_S:
            time_bonus = FULL_TIME_BONUS
        elif seconds <= MAX_BONUS_S:
            fraction = 1 - (seconds - MIN_BONUS_S) / (MAX_BONUS_S - MIN_BONUS_S)
            time_bonus = -int(-(FULL_TIME_BONUS * fraction) // 1)          # Math.ceil
        else:
            time_bonus = 0
        skill = 0 if self.misclicks > MAX_MISCLICKS else FULL_SKILL_BONUS - FULL_SKILL_BONUS // MAX_MISCLICKS * self.misclicks
        total = self.score + time_bonus + skill
        return {'score': self.score, 'time_bonus': time_bonus, 'skill_bonus': skill, 'total': total,
                'half_stars': min(MAX_HALF_STARS, total // HALF_STAR_POINTS), 'seconds': seconds,
                'found': self.found_count, 'misclicks': self.misclicks}

    def finish(self):
        """The Level Summary's Continue."""
        if self.over:
            self.finished = True

    @property
    def result(self):
        """What the story's script is given back: the total score (it has one outcome)."""
        return self.summary()['total'] if self.over else 0

    def validate(self):
        count = len(self.names)
        objects = set(range(count))
        if (not self.scene or not 0 < len(self.picked) <= count or len(set(self.picked)) != len(self.picked)
                or not set(self.picked) <= objects or not set(self.story) <= set(self.picked)
                or self.powerups not in POWERUP_MODES or len(self.slots) != len(self.extra) or len(self.slots) > AOL_SIZE
                or any(o != NO_OBJECT and o not in self.picked for o in self.slots)
                or not set(self.found) <= set(self.picked) or len(set(self.found)) != len(self.found)
                or not 0 <= self.next_index <= len(self.picked) or not 0 < self.sol_size <= len(self.picked)
                or not 1 <= self.multiplier <= MAX_MULTIPLIER or not 0 <= self.combo <= 1
                or self.elapsed_ms < 0 or self.score < 0 or self.misclicks < 0 or self.lock_ms < 0
                or any(len(item) != 2 or item[0] not in self.found for item in self.leaving)
                or any(n < 0 or p not in POWERUPS for p, n in self.used.items())
                or any(t != NO_OBJECT and t not in self.picked for t in (self.hint_target, self.focus_target,
                                                                         self.locator_target))):
            raise ValueError('Invalid Claire Hart round state')
