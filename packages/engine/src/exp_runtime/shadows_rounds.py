"""shshd-runtime: Claire Hart: Secret in the Shadows' hidden-object round (Claire Hart plan Stage S3; reference/Other Games/
docs/CLAIRE_HART_SHADOWS_ROUNDS_PLAN.md, CLAIRE_HART_SHADOWS_ENGINE.md section 5). The rules of build 232's round: hogscene
(the pick with its close-up rule and forced story objects, the list, the end), touchdetector (misclicks and the spam lock),
combometer (x6, a tier at a time), premiumobject (the Gold Key), componentPartClicked (multi-part objects, back to back),
hotcoldpowerup (the Psychic Sensor's use, target and cooldown), hintpowerup / freezepowerup / addobjectspowerup, and gameover
(the summary's rows and its ten half-star checks), with gamebalance.json's numbers. Nothing here draws or reads pictures:
the player finds which objects lie under a tap and hands them in, topmost first (as claire_rounds.ClaireRound).

The scene is given as each object's name and kind (KINDS), so a round of Classic's scenes plays here too, the extras never
occurring (Round Style). The owner's changes (2026-11-24, ENGINE section 10): the Gold Key's 500 points for every player
(the game: Club only); the Hint, Time Warp and Clairvoyance follow the Power-Ups setting (the game sold them); a multi-part
object needs its own parts (in 5 scenes the game took any two of three, its assembled sprite counting as a part).
"""
from dataclasses import dataclass, field

# Kinds of a scene's objects (the scene model: an add-on's spec gives each object's)
ORDINARY, CLOSE_UP, PART, WHOLE, GOLD_KEY = 'o', 'p', 'c', 'w', 'k'
KINDS = (ORDINARY, CLOSE_UP, PART, WHOLE, GOLD_KEY)

# gamebalance.json: hogBalance, powerups, gameover, spamClickData, starlimits
SOL_SIZE, AOL_SIZE, ADD_OBJECTS = 12, 6, 6
ORDINARY_FIRST = 6                      # the pick reaches its seventh place before close-up objects join its pool
SPAM_LOCK_MS = 5000
SPAM_SHORT = (6, 1000)                  # the 6th misclick within 1 s
SPAM_LONG = (9, 6000)                   # ...or the 9th within 6 s (the history keeps 8)
MINUTE_CAP = 99
FIND_POINTS, MAX_MULTIPLIER = 100, 6
COMBO_LEEWAY_S = 0.1
TIER_S = {6: 3.0, 5: 3.0, 4: 5.0, 3: 7.0, 2: 9.0}      # how long each multiplier holds before dropping one (the prefab's)
TIME_WARP_SLOWDOWN = 0.5
SENSOR_COOLDOWN_MS = 60000              # hotColdCooldown, from when it ends (any find ends it)
PIP_GLOW_FINDS = 6                      # objectsTillPipHighlight
FOUND_MS = 1700                         # the find's flight and its callback (1.67 s), then the next name comes in
NAME_GAP_MS = 260
# The summary (gameover): the time bonus by whole minutes, the other rows, the half-star checks' limits
TIME_BONUS = ((1, 300), (4, 200), (6, 100), (10, 50))
SENSOR_BONUS, PERFECT_BONUS, KEY_BONUS = 500, 100, 500
SCORE_TIERS = (1300, 5700)              # find points > 1,299, >= 5,700
KEY_TIMES_S = (90, 60)
TIME_LIMITS_S = (600, 300)

# The Psychic Sensor's feel (gamebalance powerups.hotColdBehavior, by distance in the round's units: the scene 600 tall):
# (distance, pulses a second, pulse strength, glow RGB, opacity, outer circle's opacity, outer circle's extra scale)
SENSOR_POINTS = ((1, 3.0, 0.30, (0, 255, 84), 255, 255, 0.01),
                 (2, 2.0, 0.25, (10, 240, 80), 255, 240, 0.14),
                 (400, 0.8, 0.13, (0, 84, 255), 135, 160, 0.50),
                 (600, 0.5, 0.08, (127, 127, 127), 125, 15, 0.65))
SENSOR_SOUNDS = ('GS_Psychic_Sensor_1_Coldest', 'GS_Psychic_Sensor_2_Cold', 'GS_Psychic_Sensor_3_Warm',
                 'GS_Psychic_Sensor_4_Warmest')
SENSOR_STEP_S = 1 / 30                  # hotcoldpowerup.updateIndicator measures every other frame of 60
SENSOR_SMOOTHING = 0.7                  # the distance kept from the last measure (0.3 of the new)
# Touch while the sensor or a spotlight is on (owner, 2026-11-24, S1: the game's phone rule, on touch only): a tap counts
# only within TOUCH_REACH units of the ring's (or the light's) last place and dragged under TOUCH_DRAG; else it's ignored.
TOUCH_REACH, TOUCH_DRAG = 100, 10

ONCE_EACH, UNLIMITED, OFF = 'once', 'unlimited', 'off'
POWERUP_MODES = (ONCE_EACH, UNLIMITED, OFF)
HINT, TIME_WARP, CLAIRVOYANCE = 'hint', 'time_warp', 'clairvoyance'
POWERUPS = (HINT, TIME_WARP, CLAIRVOYANCE)
NO_OBJECT = -1


@dataclass
class ShadowsRound:
    """One round. Objects are the scene's, by their place in its list; `kinds` says what each is (KINDS); `parts` gives a
    multi-part object's parts ({whole: [part, ...]}, as str keys when saved). `picked` is hogscene's selected list: a
    forced multi-part object first, then the story objects, then the shuffle, 12 + Clairvoyance's 6 in all."""
    scene: str
    names: list[str]
    kinds: list[str]
    picked: list[int]
    parts: dict = field(default_factory=dict)
    story: list[int] = field(default_factory=list)
    powerups: str = ONCE_EACH
    sol_size: int = SOL_SIZE
    original_sol: int = SOL_SIZE
    next_index: int = 0
    slots: list[int] = field(default_factory=list)
    extra: list[bool] = field(default_factory=list)          # a slot's name in Clairvoyance's teal
    found: list[int] = field(default_factory=list)
    leaving: list[list[int]] = field(default_factory=list)  # [object, ms until its name leaves the list]
    elapsed_ms: int = 0
    find_points: int = 0
    multiplier: int = 1
    tier_left_s: float = 0.0            # how long the multiplier still holds before dropping one
    leeway_s: float = 0.0
    combo_running: bool = False
    x6_finds: int = 0
    misclicks: int = 0
    clicks: list[int] = field(default_factory=list)          # recent misclick times, for the spam check (8 kept)
    lock_ms: int = 0                    # "Not So Fast": taps do nothing (but count) until this is 0
    key_found_ms: int = -1              # the Gold Key's round time when found
    pip_open: bool = False
    pip_seen: bool = False              # (opened once: its hotspot's glow stops)
    collecting: list[int] = field(default_factory=list)      # a multi-part object's parts found back to back so far
    sensor_on: bool = False
    sensor_target: int = NO_OBJECT
    sensor_uses: int = 0
    sensor_cooldown_ms: int = 0
    markers: list[int] = field(default_factory=list)        # objects the Hint has marked (until found)
    used: dict[str, int] = field(default_factory=dict)
    time_warp: bool = False
    time_warp_can_end: bool = False
    spotlight: bool = False
    over: bool = False
    finished: bool = False
    title: str = ''
    started: bool = False

    # --- opening ----------------------------------------------------------------------------------------------------------
    @classmethod
    def opened(cls, scene, names, kinds, parts, story, random, powerups=ONCE_EACH, title='', spotlight=False):
        """A round of the scene whose objects are `names` of `kinds`, its multi-part objects' `parts` ({whole: [parts]}), the
        story objects `story` (their places; a multi-part object listed first) forced in: hogscene.selectObjectList, its
        shuffle drawn from the session's `random` so a reload picks the same."""
        ordinary = [i for i, k in enumerate(kinds) if k == ORDINARY]
        close_ups = [i for i, k in enumerate(kinds) if k == CLOSE_UP]
        total = min(SOL_SIZE + ADD_OBJECTS, len(ordinary) + len(close_ups))
        pool = list(ordinary)
        for i in range(total):
            if i == ORDINARY_FIRST:
                pool += close_ups               # (the first six listed are always ordinary objects)
            j = i + random.below(len(pool) - i)
            pool[i], pool[j] = pool[j], pool[i]
        picked = pool[:total]
        forced = [i for i in story if 0 <= i < len(kinds) and kinds[i] in (ORDINARY, CLOSE_UP, WHOLE)]
        wholes = [i for i in forced if kinds[i] == WHOLE and parts.get(i)]
        rest = [i for i in forced if kinds[i] != WHOLE]
        for index in reversed(rest):                    # (each moved to the front, in the list's order)
            if index in picked:
                picked.remove(index)
            picked.insert(0, index)
        picked = picked[:total]
        for index in reversed(wholes):                  # (a multi-part object takes the first slot)
            picked.insert(0, index)
        picked = picked[:max(total, len(wholes))]
        sol = min(SOL_SIZE, len(picked))
        game = cls(scene, list(names), list(kinds), picked, {int(w): list(p) for w, p in parts.items()},
                   [i for i in wholes + rest if i in picked], powerups if powerups in POWERUP_MODES else ONCE_EACH,
                   sol, sol, slots=[NO_OBJECT] * min(AOL_SIZE, len(picked)), extra=[False] * min(AOL_SIZE, len(picked)),
                   title=title or scene, spotlight=bool(spotlight))
        for _ in range(len(game.slots)):
            game._list_next()
        return game

    @property
    def key(self):
        """The scene's Gold Key (premiumobject), or NO_OBJECT (2 of 512 scenes have none)."""
        return next((i for i, k in enumerate(self.kinds) if k == GOLD_KEY), NO_OBJECT)

    def _list_next(self):
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
        return [o for o in self.slots if o != NO_OBJECT]

    @property
    def found_count(self):
        """"ITEMS FOUND n/12"'s n: the listed objects found (the Gold Key isn't one)."""
        return sum(1 for o in self.found if self.kinds[o] != GOLD_KEY)

    @property
    def to_find(self):
        return self.sol_size

    @property
    def seconds(self):
        return min(MINUTE_CAP * 60 + 59, (self.elapsed_ms + 500) // 1000)

    @property
    def pip_glow(self):
        """The close-up's hotspot pulses after PIP_GLOW_FINDS finds, until it is opened (no 30 s glow: the game has none)."""
        return CLOSE_UP in self.kinds and self.found_count >= PIP_GLOW_FINDS and not self.pip_seen

    # --- time -------------------------------------------------------------------------------------------------------------
    def tick(self, elapsed_ms):
        if self.finished:
            return
        if elapsed_ms > 0:
            self.started = True
        if not self.over:
            self.elapsed_ms += elapsed_ms
        self.lock_ms = max(0, self.lock_ms - elapsed_ms)
        if not self.sensor_on:
            self.sensor_cooldown_ms = max(0, self.sensor_cooldown_ms - elapsed_ms)
        self._drain(elapsed_ms / 1000)
        for item in self.leaving:
            item[1] -= elapsed_ms
        while self.leaving and self.leaving[0][1] <= 0:
            obj, _ = self.leaving.pop(0)
            self._remove(obj)

    def _drain(self, seconds):
        """combometer: after a find's leeway, the multiplier holds its tier's time, then drops one, down to x1."""
        if not self.combo_running or self.over:
            return
        past = seconds if self.leeway_s >= COMBO_LEEWAY_S else max(0.0, self.leeway_s + seconds - COMBO_LEEWAY_S)
        self.leeway_s += seconds
        self.tier_left_s -= past * (TIME_WARP_SLOWDOWN if self.time_warp else 1)
        while self.tier_left_s <= 0 and self.multiplier > 1:
            self.multiplier -= 1
            if self.multiplier == 1:
                self.tier_left_s, self.combo_running = 0.0, False
                if self.time_warp and self.time_warp_can_end:            # Time Warp ends with the combo
                    self.time_warp = self.time_warp_can_end = False
                break
            self.tier_left_s += TIER_S[self.multiplier]

    @property
    def combo(self):
        """The meter's fill within its tier, 1 to 0 (for the player's bar)."""
        if not self.combo_running or self.multiplier < 2:
            return 0.0
        return max(0.0, min(1.0, self.tier_left_s / TIER_S[self.multiplier]))

    def _remove(self, obj):
        if obj in self.slots:
            self.slots[self.slots.index(obj)] = NO_OBJECT
        if self.next_index < self.sol_size:
            self._list_next()
        elif not self.listed and not self.leaving:
            self.over = True
            self.combo_running, self.tier_left_s = False, 0.0
            self.sensor_on, self.sensor_target = False, NO_OBJECT

    # --- taps -------------------------------------------------------------------------------------------------------------
    def tap(self, under):
        """A tap on the scene (or the open close-up): `under` the objects its point hits, topmost first. Returns the object
        found (a listed one, a multi-part object completed, or the Gold Key), PART for a part collected, or None (a
        misclick: counted, even during the lock, and spam-checked)."""
        if self.over:
            return None
        if not self.lock_ms:
            for obj in under:
                outcome = self._try(obj)
                if outcome is not None:
                    return outcome
        self._misclick()
        return None

    def backing_tap(self):
        """A tap on the open close-up's empty backing: it feeds the spam check but is no misclick (its callback swallows it)."""
        if not self.over:
            self._spam(count=False)

    def _try(self, obj):
        kind = self.kinds[obj] if 0 <= obj < len(self.kinds) else None
        if kind == GOLD_KEY:
            if self.key_found_ms >= 0:
                return None
            self.key_found_ms = self.elapsed_ms
            self._score()
            self._break_collecting()
            self._end_sensor()
            return obj
        if kind == PART:
            whole = next((w for w, ps in self.parts.items() if obj in ps), None)
            if whole is None or whole not in self.slots or whole in self.found:
                return None                     # (a loose part, its object not listed: a misclick)
            if obj in self.collecting:
                return None
            self.collecting.append(obj)
            if set(self.collecting) >= set(self.parts[whole]):
                self.collecting = []
                self._find(whole)
                return whole
            if self.sensor_on and self.sensor_target == obj:
                self.sensor_target = self._part_target(whole)        # changeTargetToNextComponent
            return PART
        if kind in (ORDINARY, CLOSE_UP) and obj in self.slots and obj not in self.found:
            if kind == CLOSE_UP and not self.pip_open:
                return None
            self._break_collecting()
            self._find(obj)
            return obj
        return None

    def _score(self):
        """combometer.increment: 100 x the multiplier, which then rises to x6; the tier's time restarts."""
        self.find_points += FIND_POINTS * self.multiplier
        if self.multiplier == MAX_MULTIPLIER:
            self.x6_finds += 1
        self.multiplier = min(MAX_MULTIPLIER, self.multiplier + 1)
        self.tier_left_s, self.leeway_s, self.combo_running = TIER_S[self.multiplier], 0.0, True
        if self.time_warp:
            self.time_warp_can_end = True

    def _find(self, obj):
        self.found.append(obj)
        self._score()
        if obj in self.markers:
            self.markers.remove(obj)
        self._end_sensor()
        self.leaving.append([obj, FOUND_MS + NAME_GAP_MS])

    def _break_collecting(self):
        """clearComponentObjectUI: parts found back to back go back into the scene at anything else."""
        self.collecting = []

    def _misclick(self):
        self.misclicks += 1
        self._break_collecting()
        self._spam(count=True)

    def _spam(self, count):
        """touchdetector.detectSpamClick: the 6th click within 1 s or the 9th within 6 s locks taps for 5 s."""
        now = self.elapsed_ms
        self.clicks.append(now)
        for many, span in (SPAM_SHORT, SPAM_LONG):
            if len(self.clicks) >= many and now - self.clicks[-many] < span:
                self.clicks = []
                self.lock_ms = SPAM_LOCK_MS
                return
        self.clicks = self.clicks[-8:]

    # --- the close-up -----------------------------------------------------------------------------------------------------
    def open_pip(self):
        if CLOSE_UP in self.kinds and not self.pip_open and not self.over:
            self.pip_open = self.pip_seen = True
            self._break_collecting()

    def close_pip(self):
        if self.pip_open:
            self.pip_open = False
            self._break_collecting()

    # --- the Psychic Sensor -----------------------------------------------------------------------------------------------
    def _targets(self, exclude=()):
        """The list's priority (hintpowerup / hotcoldpowerup): ordinary listed objects, then story objects, close-up objects
        (first while the close-up is open), multi-part objects; not found, not in `exclude`."""
        open_ = [o for o in self.listed if o not in self.found and o not in exclude]

        def rank(o):
            kind = self.kinds[o]
            if self.pip_open:
                return 0 if kind == CLOSE_UP else 1 if o not in self.story else 2
            return {ORDINARY: 0 if o not in self.story else 1, CLOSE_UP: 2, WHOLE: 3}.get(kind, 4)
        return sorted(open_, key=lambda o: (rank(o), self.listed.index(o)))

    @property
    def sensor_ready(self):
        return not self.over and not self.sensor_on and not self.sensor_cooldown_ms and bool(self._targets())

    def use_sensor(self):
        """The crystal ball: its target the first by the list's priority; the close-up opened or closed to suit. Returns the
        target (a multi-part object: its first part not yet collected), or None."""
        if not self.sensor_ready:
            return None
        target = self._targets()[0]
        self._suit_pip(target)
        self.sensor_on, self.sensor_uses = True, self.sensor_uses + 1
        self.sensor_target = self._part_target(target)
        return self.sensor_target

    def _part_target(self, obj):
        if self.kinds[obj] == WHOLE:
            return next((p for p in self.parts.get(obj, ()) if p not in self.collecting), obj)
        return obj

    def _suit_pip(self, target):
        if self.kinds[target] == CLOSE_UP:
            self.open_pip()
        else:
            self.close_pip()

    def _end_sensor(self):
        """Any find ends the sensor; its 60 s cooldown starts."""
        if self.sensor_on:
            self.sensor_on, self.sensor_target = False, NO_OBJECT
            self.sensor_cooldown_ms = SENSOR_COOLDOWN_MS

    # --- the Hint, Time Warp, Clairvoyance (the Power-Ups setting) --------------------------------------------------------
    def uses_left(self, powerup):
        if self.powerups == OFF:
            return 0
        if powerup == CLAIRVOYANCE or self.powerups == ONCE_EACH:
            return max(0, 1 - self.used.get(powerup, 0))
        return None

    def can_use(self, powerup):
        if self.over or self.uses_left(powerup) == 0:
            return False
        if powerup == HINT:
            return bool(self._targets(self.markers))
        if powerup == CLAIRVOYANCE:
            return len(self.picked) > self.sol_size
        return not self.time_warp

    def _use(self, powerup):
        self.used[powerup] = self.used.get(powerup, 0) + 1

    def hint(self):
        """The magnifier: a marker on the first unmarked listed object by the list's priority (every part of a multi-part
        one), the close-up opened or closed to suit. Returns the objects marked, or []."""
        if not self.can_use(HINT):
            return []
        target = self._targets(self.markers)[0]
        self._use(HINT)
        self._suit_pip(target)
        self.markers.append(target)
        return list(self.parts.get(target, [target])) if self.kinds[target] == WHOLE else [target]

    def warp_time(self):
        """The stopwatch: the combo drains at half speed until it falls back to x1."""
        if not self.can_use(TIME_WARP):
            return False
        self._use(TIME_WARP)
        self.time_warp = True
        self.time_warp_can_end = self.combo > 0.02
        return True

    def clairvoyance(self):
        """The eye: six more objects to find, their names in teal; "n/12" becomes "n/18"."""
        if not self.can_use(CLAIRVOYANCE):
            return False
        self._use(CLAIRVOYANCE)
        self.sol_size = min(len(self.picked), self.sol_size + ADD_OBJECTS)
        while len(self.listed) < len(self.slots) and self.next_index < self.sol_size and self._list_next():
            pass
        return True

    # --- the end ----------------------------------------------------------------------------------------------------------
    def summary(self):
        """gameover: the rows, the total and the ten half-star checks."""
        minutes = self.seconds // 60
        time_bonus = next((points for limit, points in TIME_BONUS if minutes < limit), 0)
        key_s = self.key_found_ms // 1000 if self.key_found_ms >= 0 else None
        rows = {'found': self.find_points, 'time_bonus': time_bonus,
                'sensor_bonus': SENSOR_BONUS if self.sensor_uses == 0 else 0,
                'key_bonus': KEY_BONUS if key_s is not None else 0,
                'perfect_bonus': PERFECT_BONUS if self.misclicks == 0 else 0}
        checks = [self.sensor_uses <= 2, self.sensor_uses == 0, self.misclicks <= 4, self.misclicks <= 1,
                  self.find_points >= SCORE_TIERS[0], self.find_points >= SCORE_TIERS[1],
                  key_s is not None and key_s <= KEY_TIMES_S[0], key_s is not None and key_s <= KEY_TIMES_S[1],
                  self.seconds < TIME_LIMITS_S[0], self.seconds < TIME_LIMITS_S[1]]
        return dict(rows, total=sum(rows.values()), half_stars=sum(checks), checks=checks, seconds=self.seconds,
                    found_count=self.found_count, misclicks=self.misclicks, sensor_uses=self.sensor_uses, key_s=key_s,
                    x6_finds=self.x6_finds)

    def finish(self):
        if self.over:
            self.finished = True

    @property
    def result(self):
        return self.summary()['total'] if self.over else 0

    def validate(self):
        count = len(self.names)
        objects = set(range(count))
        parts = {int(w): p for w, p in self.parts.items()}
        if (not self.scene or len(self.kinds) != count or any(k not in KINDS for k in self.kinds)
                or not 0 < len(self.picked) <= count or len(set(self.picked)) != len(self.picked)
                or not set(self.picked) <= objects or not set(self.story) <= set(self.picked)
                or any(self.kinds[o] not in (ORDINARY, CLOSE_UP, WHOLE) for o in self.picked)
                or any(w not in objects or not set(p) <= objects for w, p in parts.items())
                or self.powerups not in POWERUP_MODES or len(self.slots) != len(self.extra) or len(self.slots) > AOL_SIZE
                or any(o != NO_OBJECT and o not in self.picked for o in self.slots)
                or not set(self.found) <= objects or len(set(self.found)) != len(self.found)
                or not 0 <= self.next_index <= len(self.picked) or not 0 < self.sol_size <= len(self.picked)
                or not 1 <= self.multiplier <= MAX_MULTIPLIER or self.tier_left_s < 0
                or self.elapsed_ms < 0 or self.find_points < 0 or self.misclicks < 0 or self.lock_ms < 0
                or self.sensor_uses < 0 or self.sensor_cooldown_ms < 0
                or any(len(item) != 2 or item[0] not in self.found for item in self.leaving)
                or any(n < 0 or p not in POWERUPS for p, n in self.used.items())
                or not set(self.markers) <= set(self.picked) or not set(self.collecting) <= objects):
            raise ValueError('Invalid Secret in the Shadows round state')
        self.parts = parts


# --- the Psychic Sensor's ring (the player draws it; its feel is the game's, worked out here) -----------------------------
def sensor_distance(box, offset, point):
    """hotcoldpowerup.updateIndicator: from `point` (the ring) to the target's box (centre x, y, width, height), shifted by
    its hint `offset`: 0 inside it."""
    cx, cy, width, height = box
    dx = max(0.0, abs(cx + offset[0] - point[0]) - width / 2)
    dy = max(0.0, abs(cy + offset[1] - point[1]) - height / 2)
    return (dx * dx + dy * dy) ** 0.5


def sensor_feel(distance):
    """(pulses a second, strength, glow RGB, opacity, outer opacity, outer extra scale, sound 0-3, particles) at a smoothed
    `distance`: SENSOR_POINTS interpolated. The game's sound index between its first two points fell through to the
    coldest (`2 == i ? 2 : 3 == i ? 1 : 0`); here it is the warmest, as the owner's other fixes (2026-11-24)."""
    points = SENSOR_POINTS
    if distance <= points[0][0]:
        p = points[0]
        return p[1], p[2], p[3], p[4], p[5], p[6], 3, True
    if distance >= points[-1][0]:
        p = points[-1]
        return p[1], p[2], p[3], p[4], p[5], p[6], 0, False
    for i in range(1, len(points)):
        if distance < points[i][0]:
            a, b = points[i - 1], points[i]
            t = (distance - a[0]) / (b[0] - a[0])
            mix = lambda x, y: x * (1 - t) + y * t                      # noqa: E731
            sound = {1: 3, 2: 2, 3: 1}.get(i, 0)
            return (mix(a[1], b[1]), mix(a[2], b[2]), tuple(round(mix(x, y)) for x, y in zip(a[3], b[3])),
                    mix(a[4], b[4]), mix(a[5], b[5]), mix(a[6], b[6]), sound, False)


@dataclass
class SensorRing:
    """The ring's state between frames (not saved: a reload starts it afresh): the smoothed distance, its pulse (the goal
    scale falling by strength x rate a second, a pulse and its heartbeat when it drops below 1), the outer circle's extra
    scale (eased 0.2 a measure), and what the last measure set."""
    distance: float = 600.0
    goal: float = 1.0
    outer: float = 0.65
    carry: float = 0.0
    feel: tuple = field(default_factory=lambda: sensor_feel(600.0))

    def step(self, seconds, raw_distance):
        """`seconds` of play with the ring `raw_distance` from its target: returns the heartbeats to play (sound indexes)."""
        self.carry += seconds
        while self.carry >= SENSOR_STEP_S:
            self.carry -= SENSOR_STEP_S
            self.distance = SENSOR_SMOOTHING * self.distance + (1 - SENSOR_SMOOTHING) * raw_distance
            self.feel = sensor_feel(self.distance)
            self.outer = 0.2 * self.feel[5] + 0.8 * self.outer
        pulses, strength = self.feel[0], self.feel[1]
        self.goal -= strength * pulses * seconds
        beats = []
        while self.goal < 1.0:
            self.goal += strength if strength > 0 else 1.0
            beats.append(self.feel[6])
        return beats


def touch_counts(point, indicator, drag):
    """The game's phone rule while the sensor or a spotlight is on (S1): a tap at `point`, dragged `drag` units, counts
    only near the ring's (or the light's) last place `indicator`."""
    return drag < TOUCH_DRAG and ((point[0] - indicator[0]) ** 2 + (point[1] - indicator[1]) ** 2) ** 0.5 <= TOUCH_REACH


# --- spotlight rounds (4 rounds: playHOG mode "spotlight"; the player draws the overlay) ---------------------------------
SPOTLIGHT_SIZE = (2048, 1536)           # its overlay (spotlight2alpha), centred on the light, in the round's units
SPOTLIGHT_SPRING = {'mouse': (0.12, 0.32), 'touch': (0.2, 0.5)}     # (pull, damping) a frame, desktop and phone
SPOTLIGHT_FRAME_S = 1 / 60


@dataclass
class Spotlight:
    """spotlight.globalUpdate, a 60th of a second at a time: the light follows the pointer on a spring, clamped to a quarter
    of its overlay from the scene's middle, with a random jitter that also breathes its scale (not saved: presentation)."""
    x: float = 0.0
    y: float = 0.0
    speed: list = field(default_factory=lambda: [0.0, 0.0])
    jitter: list = field(default_factory=lambda: [0.0, 0.0])
    wander: list = field(default_factory=lambda: [0.0, 0.0])
    scale: float = 1.0
    carry: float = 0.0

    def step(self, seconds, pointer, random, touch=False):
        """`seconds` of play with the pointer at `pointer` (the round's units, from the scene's middle); `random()` gives
        0-1 (the game's Math.random)."""
        pull, damping = SPOTLIGHT_SPRING['touch' if touch else 'mouse']
        qx, qy = SPOTLIGHT_SIZE[0] / 4, SPOTLIGHT_SIZE[1] / 4
        self.carry += seconds
        while self.carry >= SPOTLIGHT_FRAME_S:
            self.carry -= SPOTLIGHT_FRAME_S
            dx, dy = pointer[0] - self.x, pointer[1] - self.y
            if abs(dx) > 5 or abs(dy) > 5 or abs(self.speed[0]) > 0.1 or abs(self.speed[1]) > 0.1:
                self.speed[0] += pull * dx - damping * self.speed[0]
                self.speed[1] += pull * dy - damping * self.speed[1]
                self.x = max(-qx, min(qx, self.x + self.speed[0]))
                self.y = max(-qy, min(qy, self.y + self.speed[1]))
            for k in (0, 1):
                self.wander[k] = 0.9 * self.wander[k] + 0.025 * (random() - 0.5)
                self.jitter[k] = 0.9985 * self.jitter[k] + self.wander[k]
                self.speed[k] += self.jitter[k]
            self.scale = 1 + abs(0.05 * self.jitter[0])
