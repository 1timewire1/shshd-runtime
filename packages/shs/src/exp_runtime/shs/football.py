"""Service 94: timed football targets, drives, halves, and sudden death.

This game offers nine changing play outcomes; it does not simulate player
physics. The script supplies weighted play tables for each half/possession.
Native evidence and presentation limits are recorded in docs/MINIGAMES.md.
"""
from ..game_state import GameState
from dataclasses import dataclass, field
import math
import struct

from ..vm import signed16


# DAT_002a8024 maps a play code to a signed composite frame in atlas 290.
PLAY_FRAMES = {-2: -57, -1: -51, -3: -41, -4: -59, -5: -45, -6: -42,
               1: -47, 2: -53, 3: -41, 4: -59, 5: -45, 6: -54, 7: -48}
TARGET_CENTERS = tuple((x, y) for y in (220, 300, 380) for x in (60, 160, 260))
SELECTED_FRAMES = {-59: -60, -57: -58, -54: -55, -53: -56, -51: -52,
                   -48: -49, -47: -50, -45: -46, -42: -44, -41: -43}


@dataclass
class Play:
    code: int
    yards: int
    variation: int
    weight: int


@dataclass
class FootballEffect:
    frame: int
    x: int
    y: int
    scale: float
    selected: bool
    remaining_ms: int


@dataclass
class FootballTarget:
    code: int
    yards: int
    delay_ms: int
    hold_ms: int
    phase: int = 1
    elapsed_ms: int = 0

    @property
    def visible(self):
        return 2 <= self.phase <= 7

    @property
    def scale(self):
        if self.phase in (2, 5):
            return min(1., self.elapsed_ms / 500)
        if self.phase in (4, 7):
            return max(0., 1 - self.elapsed_ms / 500)
        return 1. if self.phase in (3, 6) else 0.

    def tick(self, dt, worst):
        # 000b1f6c discards overshoot at each state boundary.
        self.elapsed_ms += dt
        limits = {1: self.delay_ms, 2: 500, 3: self.hold_ms, 4: 500, 5: 500, 7: 600}
        if self.phase in limits and self.elapsed_ms >= limits[self.phase]:
            if self.phase == 3 and (self.code, self.yards) == worst:
                # The native direct-to-worst branch retains its elapsed time.
                self.phase = 6
            else:
                self.elapsed_ms = 0
                self.phase += 1
            if self.phase == 5:
                self.code, self.yards = worst


@dataclass
class Football(GameState):
    first_ms: int
    second_ms: int
    plans: list[list[Play]]  # first offense/defense, second pair, overtime pair
    instructions: list[str]
    second_starts_defense: bool
    teams: list[int]
    start_positions: list[int]
    home: int
    away: int
    allow_block: bool
    allow_pass_bonus: bool
    allow_run_bonus: bool
    field_variant: int
    extra_instructions: list[str]
    half: int
    defense: bool
    position: int
    remaining_ms: int
    phase: int = 20
    phase_ms: int = 800
    phase_elapsed_ms: int = 0
    first_help: bool = True
    extra_help: bool = False
    down: int = 0
    targets: list[FootballTarget] = field(default_factory=list)
    worst: tuple[int, int] = (3, 0)
    round: int = 0
    score: int = 0
    end_pending: bool = False
    sudden_death: bool = False
    change_possession: bool = False
    message: str = ''
    message_phase: int = -1
    message_ms: int = 0
    message_lines: int = 2
    kick_result: int = 0
    sound_ids: list[int] = field(default_factory=list)
    sound_serial: int = 0
    visual_ms: int = 0
    camera_position: float | None = None
    hud_position: float | None = None
    message_ids: list[int] = field(default_factory=list)
    message_values: list[int] = field(default_factory=list)
    message_hold_ms: int = 800
    effects: list[FootballEffect] = field(default_factory=list)

    def __post_init__(self):
        if self.camera_position is None:
            self.camera_position = float(self.position)
        if self.hud_position is None:
            self.hud_position = float(self.position)

    @property
    def result(self):
        return self.home - self.away

    @property
    def plan_index(self):
        return (self.half - 1) * 2 + int(self.defense)

    @property
    def instruction(self):
        return (self.extra_instructions[int(self.defense)] if self.extra_help else
                self.instructions[self.plan_index])

    def enter(self, phase, duration=0):
        self.phase, self.phase_ms, self.phase_elapsed_ms = phase, duration, 0

    def sound(self, *assets):
        self.sound_ids, self.sound_serial = list(assets), self.sound_serial + 1

    def announce(self, text, phase, *, lines=2, messages=(), hold=800):
        self.message = text
        self.message_ids = [item[0] for item in messages]
        self.message_values = [item[1] for item in messages]
        self.message_hold_ms = hold
        if messages:
            lines = len(messages)
        self.message_lines, self.message_phase, self.message_ms = lines, 0, 800
        self.enter(phase, 1000 if phase in (5, 6) else 0)

    def tick_message(self, dt):
        # 000b4db4: three possible messages, each with explicit in/out stages.
        if self.message_phase == -1:
            return
        self.message_ms -= dt
        if self.message_ms > 0:
            return
        phase = self.message_phase
        transitions = {0: (1, 300), 1: (2, self.message_hold_ms), 3: (4, 100), 4: (6, 300),
                       6: (5, self.message_hold_ms), 7: (8, 100), 8: (10, 300),
                       10: (9, self.message_hold_ms), 11: (-1, 0)}
        if phase == 2:
            next_phase = (3, 100) if self.message_lines > 1 else (11, 800)
        elif phase == 5:
            next_phase = (7, 100) if self.message_lines == 3 else (11, 800)
        elif phase == 9:
            next_phase = 11, 800
        else:
            next_phase = transitions[phase]
        self.message_phase, self.message_ms = next_phase
        if self.phase == 11 and next_phase == 6:
            self.sound(8101 if self.home > self.away else 8105)

    def eligible(self, play):
        if play.code == -4:
            return self.down in (2, 3)
        if play.code == 5:
            return self.down == 3
        if play.code == -5:
            return self.down == 3 and 65 < self.position < 95
        return True

    def deal(self, random):
        """000bce84 / 000b467c / 000b45d8 / 000bf450."""
        plan = self.plans[self.plan_index]
        eligible = [p for p in plan if self.eligible(p)]
        total = sum(p.weight for p in eligible)
        if total <= 0:
            raise ValueError('Football play table has no eligible weighted outcomes')
        targets = []
        for _ in range(9):
            pick = random.below(total)
            for p in eligible:
                pick -= p.weight
                if pick < 0:
                    code = p.code
                    break
            if code == 6 and not self.allow_pass_bonus:
                code = 2
            elif code == 7 and not self.allow_run_bonus:
                code = 1
            elif code == -6 and not self.allow_block:
                code = -3
            # Native looks up the remapped code, with the first row as fallback.
            p = next((p for p in plan if p.code == code), plan[0])
            yards = 0 if abs(code) in (4, 5) or code == -6 else p.yards
            if abs(code) not in (4, 5) and code != -6 and p.variation:
                yards += random.below(abs(p.variation)) * (1 if p.variation > 0 else -1)
            hold, delay = random.below(2) * 500 + 800, random.below(1200)
            targets.append(FootballTarget(code, yards, delay, hold))
        self.targets = targets

        def rank(t):
            return {4: -200, -4: 200, -6: 0}.get(t.code, t.yards + (5 if t.code in (6, 7) else 0))

        worst = min(targets, key=rank)
        self.worst = worst.code, worst.yards
        self.round += 1
        self.enter(3)

    def help(self, *, switch=False):
        if switch:
            self.defense = not self.defense
            self.down = 0
        self.change_possession = False
        self.enter(21 if self.defense else 20, 800)

    def tap(self, index, random):
        if index is not None and (type(index) is not int or not 0 <= index < 9):
            raise ValueError('Football target index must be between zero and eight')
        if 20 <= self.phase <= 23:
            if self.phase_elapsed_ms > (3500 if self.first_help else 900):
                self.first_help = False
                self.enter(25, 800)
            return
        if self.phase != 3 or index is None or not self.targets[index].visible:
            return
        target = self.targets[index]
        # 000bc2ec/000b2584: capture the current art before committing the
        # play. These effects never choose an outcome or draw random values.
        effects = []
        for i, (item, (x, y)) in enumerate(zip(self.targets, TARGET_CENTERS)):
            if item.visible:
                frame = PLAY_FRAMES[item.code]
                selected = i == index
                if selected:
                    frame = SELECTED_FRAMES[frame]
                    y -= int(item.scale * 18)
                effects.append(FootballEffect(frame, x, y, float(item.scale), selected,
                                               1500 if selected else 1300))
        self.apply_play(target.code, target.yards, random)
        self.effects = effects

    def apply_play(self, code, yards, random):
        """000b78c8: field movement, seven-point touchdowns, kicks, downs."""
        self.targets = []
        self.change_possession = False
        if abs(code) == 4:
            self.score += 10 if self.defense else -50
            self.change_possession = True
            self.sound(8107, 8100 if self.defense else 8105)
            self.announce('Turnover!', 5 if self.defense else 6,
                          messages=((60, 1000), (55, 1000)), hold=0)
            return
        if abs(code) == 5:
            distance = 100 - self.position if self.defense else self.position
            failure = min(.9900000095367432,
                          1 - math.log(distance) / 3.9120230674743652) if 0 < distance < 50 else .9900000095367432
            failure = struct.unpack('<f', struct.pack('<f', failure))[0]
            r = random.below(10000) / 10000
            self.kick_result = 1 if r >= failure else 3 if r / failure > .9 else 2
            if self.kick_result == 1:
                if self.defense:
                    self.away = signed16(self.away + 3)
                else:
                    self.home = signed16(self.home + 3)
                self.sound(8102, 8101)
            else:
                self.sound(8104, 8105)
            self.change_possession = True
            messages = [(46 if self.kick_result == 1 else 47, 1000)]
            if self.remaining_ms > 0 and not self.sudden_death:
                messages.append((-102, 1000))
            self.announce('Field goal!' if self.kick_result == 1 else 'Kick missed!', 13,
                          messages=messages)
            return
        if code == -6:
            yards = 0
        if not self.defense and code in (6, 7):
            yards += 5
        self.position = max(0, min(100, self.position - yards))
        self.score += yards * 2
        touchdown = self.position >= 100 if self.defense else self.position <= 0
        if touchdown:
            if self.defense:
                self.away = signed16(self.away + 7)
                self.score -= 70
            else:
                self.home = signed16(self.home + 7)
                self.score += 70
            self.sound(8102, 8108 if self.defense else 8101)
            self.change_possession = True
            messages = [(53 if self.defense else 48, 1000)]
            if self.remaining_ms > 0 and not self.sudden_death:
                messages.append((-102, 1000))
            self.announce('Touchdown!', 10 if self.defense else 9,
                          messages=messages)
            return
        self.down += 1
        if code == 3 or code == -3:
            self.sound(8103)
        else:
            self.sound(8102 if yards > 0 else 8104)
        # 000b78c8: yardage, then the NEXT down (or possession change).
        # Block is the localized zero-yard opponent message, not a new label.
        if code == -6:
            message, value = 61, 0
        elif code in (6, 7) and not self.defense:
            message, value = (63 if code == 6 else 62), yards - 5
        else:
            message = 54 if yards < 0 or (yards == 0 and self.defense) else 58
            value = abs(yards)
        messages = ((message, value), (55 if self.down == 4 else 49 + self.down, 1000))
        if self.down == 4 and self.end_pending and self.half == 1:
            # Native returns before configuring another banner at this boundary.
            self.enter(4)
        else:
            self.announce(f'{abs(yards)} yards ' + ('gained' if yards > 0 else 'lost'),
                          4, messages=messages, hold=0)

    def end_half(self):
        if self.half == 2 and self.home == self.away:
            self.sudden_death = True
        self.sound(8106)
        result = 43 if self.home == self.away else 44 if self.home > self.away else 45
        messages = (((42, 1000), (-102, 1000)) if self.half == 1 else
                    ((57, 1000), (-102, 1000), (result, 1000)) if self.half == 2 else
                    ((-102, 1000), (result, 1000)))
        self.announce('Halftime' if self.half == 1 else 'Sudden death' if self.home == self.away else 'Full time',
                      11, messages=messages)

    def tick_presentation(self, dt):
        """000b1c10 / 000c0310: independent field and scoreboard easing."""
        self.visual_ms += dt
        for effect in self.effects:
            effect.remaining_ms = max(0, effect.remaining_ms - dt)
        self.effects = [effect for effect in self.effects if effect.remaining_ms > 0]
        self.camera_position += (self.position - self.camera_position) * .5 * min(dt / 100, 1.)
        if abs(self.position - self.camera_position) < .02:
            self.camera_position = float(self.position)
        delta = self.position - self.hud_position
        step = delta * .5 * (dt / 300)
        self.hud_position += step
        if delta * (self.position - self.hud_position) < 0 or abs(step) < .5:
            self.hud_position = float(self.position)

    def tick(self, elapsed_ms, random):
        dt = min(250, elapsed_ms)
        self.phase_elapsed_ms += dt
        self.tick_presentation(dt)
        self.tick_message(dt)
        active = self.phase in (2, 3)
        if self.phase == 2:
            self.phase_ms -= dt
            if self.phase_ms < 0:
                self.deal(random)
        elif self.phase == 3:
            for target in self.targets:
                target.tick(dt, self.worst)
            if all(t.phase == 8 for t in self.targets):
                self.apply_play(*self.worst, random)
            elif all(t.phase == 6 and t.elapsed_ms >= 500 for t in self.targets):
                for t in self.targets:
                    t.phase, t.elapsed_ms = 7, 0
        elif self.phase == 25:
            self.phase_ms -= dt
            if self.phase_ms <= 0:
                if self.half == 1 and self.extra_instructions[int(self.defense)] and not self.extra_help:
                    self.extra_help = True
                    self.help()
                else:
                    self.extra_help = False
                    self.enter(0, 2400)
        elif self.phase == 0:
            self.phase_ms -= dt
            if self.phase_ms <= 0:
                self.enter(2)
        elif (self.phase == 4 and self.message_phase == -1
              and self.camera_position == self.position):
            if self.end_pending:
                self.end_half()
            elif self.down == 4:
                self.change_possession = True
                self.enter(7, 2000)
            else:
                self.enter(2)
        elif self.phase in (5, 6, 7):
            self.phase_ms = max(0, self.phase_ms - dt)
            if self.phase_ms <= 0 and self.message_phase == -1:
                self.help(switch=self.change_possession)
        elif (self.phase in (9, 10, 13) and self.message_phase == -1
              and (self.phase == 13 or self.camera_position == self.position)):
            if self.sudden_death:
                self.end_half()
            else:
                if self.phase != 13 or self.kick_result == 1:
                    self.position = self.start_positions[0 if self.defense else 1]
                self.help(switch=True)
        elif self.phase == 11 and self.message_phase == -1:
            self.end_pending = False
            if self.half == 1 and self.second_ms > 0:
                self.half, self.remaining_ms = 2, self.second_ms
                self.defense = self.second_starts_defense
                self.position, self.down = self.start_positions[int(self.defense)], 0
                self.enter(22, 800)
            elif self.half != 1 and self.home == self.away:
                self.half, self.remaining_ms, self.defense = 3, -1, False
                self.position, self.down = self.start_positions[0], 0
                self.enter(23, 800)
            else:
                self.enter(1, 3000)
        elif self.phase == 1:
            self.phase_ms -= dt
            if self.phase_ms <= 0:
                self.enter(26, 960)
        elif self.phase == 26:
            self.phase_ms -= dt
            if self.phase_ms <= 0:
                return True
        if active and not self.end_pending:
            if self.half == 3:
                self.end_pending = self.home != self.away
            else:
                self.remaining_ms = max(0, self.remaining_ms - dt)
                self.end_pending = self.remaining_ms == 0
        if self.end_pending and self.phase not in (1, 3, 4, 5, 6, 9, 10, 11, 13, 26):
            self.end_half()
        return False

    def validate_config(self):
        if (not 0 <= self.first_ms <= 32767000 or not 0 <= self.second_ms <= 32767000
                or not self.first_ms + self.second_ms or len(self.plans) != 6
                or len(self.instructions) != 6 or len(self.extra_instructions) != 2
                or len(self.teams) != 2 or len(self.start_positions) != 2
                or any(not 0 <= p <= 100 for p in self.start_positions)
                or self.field_variant not in (0, 1)):
            raise ValueError('Invalid football configuration')
        for plan in self.plans:
            if (not 1 <= len(plan) <= 10
                    or any(p.code not in PLAY_FRAMES or p.weight < 0 for p in plan)
                    or not any(p.weight > 0 and p.code not in (-4, -5, 5) for p in plan)):
                raise ValueError('Invalid football play table')

    def validate(self):
        self.validate_config()
        if (self.half not in (1, 2, 3) or not 0 <= self.position <= 100 or not 0 <= self.down <= 4
                or self.phase not in (0, 1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 13, 20, 21, 22, 23, 25, 26)
                or not -250 <= self.phase_ms <= 3000 or self.phase_elapsed_ms < 0
                or self.message_phase not in range(-1, 12) or self.message_lines not in (1, 2, 3)
                or not -250 <= self.message_ms <= 800 or self.round < 0
                or len(self.targets) not in (0, 9) or (self.phase == 3 and len(self.targets) != 9)
                or self.worst[0] not in PLAY_FRAMES or not -32768 <= self.home <= 32767
                or not -32768 <= self.away <= 32767 or self.remaining_ms < -1
                or self.remaining_ms > max(self.first_ms, self.second_ms)):
            raise ValueError('Invalid saved football game')
        if (self.visual_ms < 0 or self.camera_position is None or self.hud_position is None
                or not 0 <= self.camera_position <= 100 or not 0 <= self.hud_position <= 100
                or self.message_hold_ms not in (0, 800)
                or len(self.message_ids) not in (0, self.message_lines)
                or len(self.message_ids) != len(self.message_values)
                or any(i not in (*range(42, 64), -100, -101, -102) for i in self.message_ids)):
            raise ValueError('Invalid saved football presentation')
        if len(self.effects) > 9:
            raise ValueError('Too many football effects')
        for effect in self.effects:
            if (effect.frame not in (SELECTED_FRAMES.values() if effect.selected else PLAY_FRAMES.values())
                    or effect.x not in (60, 160, 260) or not 202 <= effect.y <= 380
                    or not 0 <= effect.scale <= 1
                    or not 0 < effect.remaining_ms <= (1500 if effect.selected else 1300)):
                raise ValueError('Invalid saved football effect')
        for t in self.targets:
            if (t.code not in PLAY_FRAMES or not 0 <= t.delay_ms < 1200
                    or t.hold_ms not in (800, 1300) or not 1 <= t.phase <= 8 or t.elapsed_ms < 0):
                raise ValueError('Invalid saved football target')


def read_football(vm, args, read_text):
    if len(args) != 22:
        raise ValueError('Football service requires twenty-two arguments')
    plans = []
    for address in args[2:8]:
        plan = []
        for i in range(11):
            if vm.read_word(address + i * 4) == 0x7ffe:
                break
            if i == 10:
                raise ValueError('Unterminated or oversized football play table')
            plan.append(Play(*(vm.read_word(address + i * 4 + k) for k in range(4))))
        plans.append(plan)
    text = [read_text(vm.read_word(args[8] + i)) for i in range(6)]
    half = 1 if args[0] > 0 else 2
    defense = not bool(args[9])
    return Football(max(0, args[0]) * 1000, max(0, args[1]) * 1000, plans, text,
                    bool(args[9]), [args[10] & 255, args[11] & 255], list(args[12:14]),
                    args[14], args[15], bool(args[16]), bool(args[17]), bool(args[18]),
                    int(not args[19]), [read_text(i) if i != -1 else '' for i in args[20:22]],
                    half, defense, args[13] if defense else args[12],
                    (args[0] if half == 1 else args[1]) * 1000)
