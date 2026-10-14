"""Native random streams and pipe-delimited option parsing.

Evidence and argument schemas: docs/MINIGAMES.md. Random permutations are
part of saved gameplay state, never recomputed by a renderer.
"""
from dataclasses import dataclass, field
from time import process_time_ns


RAND48_INITIAL = 0x1234ABCD330E
RAND48_MASK = (1 << 48) - 1


@dataclass
class Random48:
    """The libc lrand48 stream for word choices, separate from services 4/27."""
    state: int = RAND48_INITIAL

    def next(self):
        self.state = (self.state * 0x5DEECE66D + 0xB) & RAND48_MASK
        return self.state >> 17

    def below(self, bound):
        if bound <= 0:
            raise ValueError('Random selection needs a positive bound')
        return self.next() % bound


@dataclass
class NativeRandom:
    """0004c248 / 00126fa8 / 00122554: CPU-clock seed and 32-bit LCG.

    The returned word includes bits from the full multiplication, before
    truncating the stored state. This is not the usual ANSI rand() result.
    """
    state: int = field(default_factory=lambda: (process_time_ns() // 1000) & 0xffffffff)

    def next(self):
        product = self.state * 0x41c64e6d + 0x3039
        self.state = product & 0xffffffff
        value = (product >> 16) & 0xffffffff
        return abs(value if value < 0x80000000 else value - 0x100000000)

    def below(self, bound):
        if bound <= 0:
            raise ValueError('Random selection needs a positive bound')
        return self.next() % bound

    def signed_below(self, bound):
        value, negative = self.below(bound), self.next() & 1
        return -value if negative else value


def pipe_list(text):
    result = text.split('|')
    # The native parser preserves a blank final field, including whitespace.
    if not result[-1].strip():
        result[-1] = ''
    return result


