"""Service 78's five-position portrait selector (native UI type 5)."""
from dataclasses import dataclass
import math


# DAT_0025b830, converted from GL to top-left 320 x 480 coordinates.
POSITIONS = ((160, 275), (52, 241), (115, 170), (206, 170), (269, 241))
SWAP_MS = 50


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

    @classmethod
    def start(cls, characters):
        if not 1 <= len(characters) <= 5:
            raise ValueError('Character selection requires 1 to 5 character IDs')
        portraits = []
        for slot in range(len(characters)):
            x, y = POSITIONS[slot]
            pose = (float(x), float(y), 1.0 if slot == 0 else 0.6)
            portraits.append(PortraitMotion(pose, pose, opacity=255 if slot == 0 else 91))
        return cls(list(characters), list(range(len(characters))), portraits)

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
            outgoing.start, outgoing.end = second, (first[0], first[1], 0.6)
            incoming.elapsed_ms = outgoing.elapsed_ms = 0
            for position, original in enumerate(self.order):
                self.portraits[original].opacity = 255 if position == 0 else 91
        return True

    def tick(self, elapsed_ms):
        for portrait in self.portraits:
            portrait.elapsed_ms = min(SWAP_MS, portrait.elapsed_ms + elapsed_ms)

    def hit(self, point):
        """Native fixed circular hit regions, independent of animated widgets."""
        x, y = point
        for slot, original in enumerate(self.order):
            cx, cy = POSITIONS[slot]
            radius = 61 * (1 if slot == 0 else 0.6)
            if (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2:
                return original
        return None

    def validate(self):
        count = len(self.characters)
        if (not 1 <= count <= 5 or sorted(self.order) != list(range(count))
                or len(self.portraits) != count
                or any(not -32768 <= c <= 32767 for c in self.characters)):
            raise ValueError('Invalid character selection state')
        for portrait in self.portraits:
            if not 0 <= portrait.elapsed_ms <= SWAP_MS or portrait.opacity not in (91, 255):
                raise ValueError('Invalid portrait animation')
            for x, y, scale in (portrait.start, portrait.end):
                if (not all(math.isfinite(v) for v in (x, y, scale))
                        or not 52 <= x <= 269 or not 170 <= y <= 275 or not 0.6 <= scale <= 1):
                    raise ValueError('Invalid portrait position or scale')
