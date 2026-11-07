"""Service 78's five-position portrait selector (native UI type 5)."""
from dataclasses import dataclass, field
import math


# DAT_0025b830, converted from GL to top-left 320 x 480 coordinates.
POSITIONS = ((160, 275), (52, 241), (115, 170), (206, 170), (269, 241))
SWAP_MS = 50
NATIVE_MOST = 5                 # the native selector's slots
SMALL = 0.6                     # an unselected portrait's scale (ARR_PORTRAIT_SCALE)
# shshd-runtime: a translated pack's own layout (shs/profile.py TRANSLATED_PICKER_LAYOUTS) may hold more portraits (the BREW
# M.A.S.H. packs offer ten photos; owner, 2026-11-07), each slot (x, y) or (x, y, its unselected scale), within the column.
MOST = 10
SMALLEST = 0.3


def slot_scale(position):
    """An unselected portrait's scale in a slot: its own third number, or the native 0.6."""
    return float(position[2]) if len(position) > 2 else SMALL


@dataclass
class PortraitMotion:
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    elapsed_ms: int = SWAP_MS
    opacity: int = 255

    @property
    def pose(self):
        t = self.elapsed_ms / SWAP_MS
        return tuple(a + (b - a) * t for a, b in zip(self.start, self.end))


@dataclass
class CharacterPicker:
    characters: list[int]
    order: list[int]
    portraits: list[PortraitMotion]
    # Where each slot is: the native table, or a translated pack's own (shs/profile.py TRANSLATED_PICKER_LAYOUTS).
    positions: list[tuple[int, int] | tuple[int, int, float]] = field(default_factory=lambda: list(POSITIONS))

    @classmethod
    def start(cls, characters, positions=POSITIONS):
        most = NATIVE_MOST if positions is POSITIONS else MOST
        if not 1 <= len(characters) <= most:
            raise ValueError(f'Character selection requires 1 to {most} character IDs')
        if len(positions) < len(characters):
            raise ValueError('A picker layout needs a position for every character')
        portraits = []
        for slot in range(len(characters)):
            x, y = positions[slot][:2]
            pose = (float(x), float(y), 1.0 if slot == 0 else slot_scale(positions[slot]))
            portraits.append(PortraitMotion(pose, pose, opacity=255 if slot == 0 else 91))
        return cls(list(characters), list(range(len(characters))), portraits, [tuple(p) for p in positions])

    @property
    def selected(self):
        return self.order[0]

    def select(self, index):
        """Select an original array index, without completing the VM call."""
        if type(index) is not int or not 0 <= index < len(self.characters):
            raise ValueError('Select a portrait by its original zero-based index')
        slot = self.order.index(index)
        if slot == 0:
            return False
        previous = self.order[0]
        self.order[0], self.order[slot] = index, previous
        incoming, outgoing = self.portraits[index], self.portraits[previous]
        # FUN_000d1d78 swaps indices even during motion. It starts new actions
        # when at least one of the two widgets has no running action.
        if incoming.elapsed_ms == SWAP_MS or outgoing.elapsed_ms == SWAP_MS:
            first, second = incoming.pose, outgoing.pose
            incoming.start, incoming.end = first, (second[0], second[1], 1.0)
            outgoing.start, outgoing.end = second, (first[0], first[1], slot_scale(self.positions[slot]))
            incoming.elapsed_ms = outgoing.elapsed_ms = 0
            for position, original in enumerate(self.order):
                self.portraits[original].opacity = 255 if position == 0 else 91
        return True

    @property
    def moving(self):
        """Whether a swap is still running. A selection meanwhile reorders the portraits without restarting their motion
        (as FUN_000d1d78 does), which leaves the drawn positions out of step; keyboard selection waits for this."""
        return any(portrait.elapsed_ms < SWAP_MS for portrait in self.portraits)

    def tick(self, elapsed_ms):
        for portrait in self.portraits:
            portrait.elapsed_ms = min(SWAP_MS, portrait.elapsed_ms + elapsed_ms)

    def hit(self, point):
        """Native fixed circular hit regions, independent of animated widgets."""
        x, y = point
        for slot, original in enumerate(self.order):
            cx, cy = self.positions[slot][:2]
            radius = 61 * (1 if slot == 0 else slot_scale(self.positions[slot]))
            if (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2:
                return original
        return None

    def validate(self):
        count = len(self.characters)
        native = all(len(p) == 2 for p in self.positions) and count <= NATIVE_MOST
        if native:
            inside = lambda x, y: 52 <= x <= 269 and 170 <= y <= 275
            smallest = SMALL
        else:
            inside = lambda x, y: 0 <= x <= 320 and 100 <= y <= 400
            smallest = min([SMALL] + [slot_scale(p) for p in self.positions])
        if (not 1 <= count <= MOST or sorted(self.order) != list(range(count))
                or len(self.portraits) != count
                or any(not -32768 <= c <= 32767 for c in self.characters)
                or len(self.positions) < count
                or any(len(p) not in (2, 3) for p in self.positions)
                or any(not inside(*p[:2]) for p in self.positions)
                or any(not SMALLEST <= slot_scale(p) <= 1 for p in self.positions)):
            raise ValueError('Invalid character selection state')
        for portrait in self.portraits:
            if not 0 <= portrait.elapsed_ms <= SWAP_MS or portrait.opacity not in (91, 255):
                raise ValueError('Invalid portrait animation')
            for x, y, scale in (portrait.start, portrait.end):
                if (not all(math.isfinite(v) for v in (x, y, scale))
                        or not inside(x, y) or not smallest <= scale <= 1):
                    raise ValueError('Invalid portrait position or scale')
