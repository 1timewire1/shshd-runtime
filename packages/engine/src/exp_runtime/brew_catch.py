"""shshd-runtime: the BREW games' catch game (BREW services 19, 20 and 21; here service 221). Evidence is shs08.5.mod's own code
(setup FUN_0000bcb4 and FUN_0000356c, update FUN_00016f98, spawn FUN_0001598c, catch FUN_000120a0, end test FUN_0000d9bc, key
FUN_0000b070, draw FUN_00005b94), which Tardy-Slip's brew-catch.js also follows. Positions are in 256ths of BREW's pixels on its
228 x 280 field. Nothing here draws (desktop_brew_catch.py), and the native game has no sounds of its own.

The update counts time as it comes, but moves the orbit once per tick, so its rate comes from the module's tick_delay (`xlarge.prf`
on the only real phone's install: 50 ms) and circle_points (not set there, so 2000 / tick_delay): a lap takes 2 s whatever the tick.
"""
from dataclasses import dataclass, field
import math

from .brew_services import ANGLED, BREW_CATCH, BREW_MINIGAMES_QUERY, ORBIT, SIDEWAYS  # noqa: F401

FIELD_WIDTH, FIELD_HEIGHT = 228, 280
TICK_MS, CIRCLE_POINTS = 50, 40
STEP_MS = 10                            # objects move in steps of this
END_MS = 1000                           # the caption's time on screen
COLLISION_INSET, COLLISION_SHRINK = 2, 4
ITEM_WORDS = 3                          # value, picture, count, after the list's length
MAX_ITEMS = 20
VALUE, PICTURE, COUNT, WIDTH, HEIGHT = range(5)     # a template
X, Y, VX, VY, TEMPLATE = range(5)                   # an object


def _divide(a, b):
    """C's integer division, which goes towards 0."""
    quotient = abs(a) // abs(b)
    return quotient if (a < 0) == (b < 0) else -quotient


def _sin16(degrees):
    """The native table's sine at 65535 for 1 (FUN_0000f94c)."""
    return round(65535 * math.sin(math.radians(degrees)))


def _sin8(degrees):
    return _sin16(degrees) >> 8


def _cos8(degrees):
    return _sin16(degrees + 90) >> 8


@dataclass
class CatchGame:
    mode: int
    target: int
    interval_ms: int
    speed: int
    spread: int
    chance: int                         # of an item coming at the angle, or from the left
    angle: int
    sprite: int                         # the player's picture
    width: int
    height: int
    templates: list[list[int]]
    total: int
    remaining: int
    x: int = 0
    y: int = 0
    direction: int = 1
    orbit_at: int = 0
    orbit_x: int = 0
    orbit_y: int = 0
    objects: list[list[int]] = field(default_factory=list)
    score: int = 0
    step_ms: int = 0
    spawn_ms: int = 0
    tick_ms: int = 0
    end_ms: int = 0
    started: bool = False

    @classmethod
    def opened(cls, mode, target, interval_ms, speed, spread, chance, angle, sprite, items, sizes, random):
        """`items` as (value, picture, count), `sizes` {picture: (width, height)}: a picture it has no size for is an error."""
        width, height = sizes[sprite]
        templates = [[value, picture, max(0, count), *sizes[picture]] for value, picture, count in items]
        total = sum(t[COUNT] for t in templates)
        game = cls(mode, target, interval_ms, speed, spread, chance, angle, sprite, width, height, templates, total, total)
        if mode == ANGLED:
            game.x, game.y = _divide(FIELD_WIDTH - width, 2) << 8, (FIELD_HEIGHT - height - 4) << 8
        elif mode == SIDEWAYS:
            game.x, game.y = _divide(FIELD_WIDTH - width, 2) << 8, (FIELD_HEIGHT - height) << 8
        game.orbit_x, game.orbit_y = FIELD_WIDTH // 2 - width // 2, FIELD_HEIGHT // 2 - height // 2
        game.orbit_at = 3 * CIRCLE_POINTS // 4
        game.direction = -1 if random.next() & 1 else 1
        if mode == ORBIT:
            game._place_on_orbit()
        return game

    @property
    def over(self):
        return self.score >= self.target or (self.remaining == 0 and not self.objects)

    @property
    def out_of_items(self):
        """Which caption shows: "Time is up!" when nothing's left, even with the most points, else "Max Points!"."""
        return self.remaining == 0 and not self.objects

    @property
    def result(self):
        return max(0, min(self.target, self.score))

    @property
    def digit(self):
        """The count in the ring: 9 down to 1, then 0 only once it's over."""
        n = self.remaining * 9 // self.total if self.total else 0
        return 1 if n == 0 and not self.over else n

    def press(self):
        """OK: turn back."""
        self.started = True
        self.direction = -self.direction

    def _on_orbit(self, index, width, height):
        degrees = _divide(index * 360, CIRCLE_POINTS)
        return ((FIELD_WIDTH // 2 << 8) + self.orbit_x * _cos8(degrees) - (width // 2 << 8),
                (FIELD_HEIGHT // 2 << 8) + self.orbit_y * (_sin16(degrees) >> 8) - (height // 2 << 8))

    def _place_on_orbit(self):
        self.x, self.y = self._on_orbit(self.orbit_at, self.width, self.height)

    def tick(self, elapsed_ms, random):
        """One frame; True when the game has finished and the story goes on."""
        self.started = True
        if self.over:
            self.end_ms += elapsed_ms
            return self.end_ms > END_MS
        self.spawn_ms += elapsed_ms
        if self.spawn_ms >= self.interval_ms:
            self._spawn(random)
            self.spawn_ms = 0
        if self.mode == ORBIT:
            self.tick_ms += elapsed_ms
            while self.tick_ms >= TICK_MS:
                self.tick_ms -= TICK_MS
                self.orbit_at = (self.orbit_at + self.direction + CIRCLE_POINTS) % CIRCLE_POINTS
            self._place_on_orbit()
        self.step_ms += elapsed_ms
        while self.step_ms > STEP_MS:
            self._step()
            self.step_ms -= STEP_MS
        self.score = max(0, min(self.target, self.score))
        return False

    def _move_player(self):
        """A straight run, turning at the field's ends: along the bottom when angled, up and down when sideways."""
        length, along, size = ((FIELD_WIDTH, self.x, self.width) if self.mode == ANGLED else (FIELD_HEIGHT, self.y, self.height))
        at = along + _divide(length * self.direction * 128, 100)
        if (at >> 8) + size >= length:
            self.direction = -self.direction
            at = (length - size - 1) << 8
        elif at >> 8 <= 0:
            self.direction = -self.direction
            at = 1 << 8
        if self.mode == ANGLED:
            self.x = at
        else:
            self.y = at

    def _step(self):
        if self.mode in (ANGLED, SIDEWAYS):
            self._move_player()
        px, py = self.x >> 8, self.y >> 8
        kept = []
        for item in self.objects:
            template = self.templates[item[TEMPLATE]]
            width, height = template[WIDTH], template[HEIGHT]
            ox, oy = item[X] >> 8, item[Y] >> 8
            if ox + width < 0 or ox > FIELD_WIDTH or oy + height < 0 or oy > FIELD_HEIGHT:
                continue
            if self.mode == ANGLED:
                if ox + width >= FIELD_WIDTH:
                    item[VX] = -item[VX]
                    item[X] = (FIELD_WIDTH - width - 1) << 8
                elif ox <= 0:
                    item[VX] = -item[VX]
                    item[X] = 1 << 8
            cx, cy = (item[X] >> 8) + COLLISION_INSET, (item[Y] >> 8) + COLLISION_INSET
            if (px <= cx + width - COLLISION_SHRINK and cx <= px + self.width
                    and py <= cy + height - COLLISION_SHRINK and cy <= py + self.height):
                self.score += template[VALUE]
                continue
            item[X] += _divide(self.speed * item[VX], 256)
            item[Y] += _divide(self.speed * item[VY], 256)
            kept.append(item)
        self.objects = kept

    def _spawn(self, random):
        if self.remaining <= 0:
            return
        pick, running = random.below(self.remaining), 0
        for index, template in enumerate(self.templates):
            running += template[COUNT]
            if pick < running:
                break
        else:
            return
        template[COUNT] -= 1
        self.remaining -= 1
        width, height = template[WIDTH], template[HEIGHT]
        if self.mode == ANGLED:
            x, y = random.below(FIELD_WIDTH - width) << 8, (1 - height) << 8
            angle = self.angle if random.below(100) < self.chance else 0
            sine = _sin8(angle) or 1
            vx = _divide(self.speed * (((random.below(2 * sine) - sine) * 128) >> 8), 256)
            vy = _divide(self.speed * ((_cos8(angle) * 128) >> 8), 256)
        elif self.mode == SIDEWAYS:
            speed = _divide(self.speed * 128, 256)
            if random.below(100) < self.chance:
                x, vx = (1 - width) << 8, speed
            else:
                x, vx = (FIELD_WIDTH - 1) << 8, -speed
            y, vy = random.below(FIELD_HEIGHT - height) << 8, 0
        else:
            point = random.below(CIRCLE_POINTS)
            speed = random.below(2 * self.spread) + self.speed - self.spread
            x, y = (FIELD_WIDTH // 2 - width // 2) << 8, (FIELD_HEIGHT // 2 - height // 2) << 8
            to_x, to_y = self._on_orbit(point, width, height)
            divisor = _divide(6553600, max(1, _divide(speed, 2)))
            vx, vy = _divide((to_x - x) * 256, divisor), _divide((to_y - y) * 256, divisor)
        self.objects.append([x, y, vx, vy, index])

    def validate(self):
        if (self.mode not in (ANGLED, SIDEWAYS, ORBIT) or self.target <= 0 or self.interval_ms <= 0
                or not 0 <= self.remaining <= self.total or not 0 <= self.orbit_at < CIRCLE_POINTS
                or self.direction not in (-1, 1) or not 0 <= self.score <= self.target
                or any(len(t) != 5 for t in self.templates) or any(len(o) != 5 or not 0 <= o[TEMPLATE] < len(self.templates) for o in self.objects)):
            raise ValueError('Invalid catch game state')
