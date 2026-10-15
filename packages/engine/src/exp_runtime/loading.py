"""Service 91's application overlay and host execution gate.

FUN_0008e7d0 accumulates active milliseconds; FUN_0009ea70 clears the
overlay only once the counter is strictly greater than 3000.
"""
from dataclasses import dataclass

from .vm import KiwiVM, VMError, VMStop


def loading_waits(vm: KiwiVM, request: VMStop) -> bool:
    """Read the dispatcher's first frame slot, even for a zero-word call.

    FUN_0009fe3c (and HD's SHSScript::syscall, 0003d9b8) reads stack[SP - argc]
    without checking argc. With no arguments this is retained backing at SP,
    not an implicit zero.

    shshd-runtime: a slot this session never wrote reads as 0 (no wait) instead
    of stopping. HD allocates the script stack once, at launch, with
    `new short[0x400]` (CSKiwiEngine::init, 0000f788; no fill), so natively the
    slot holds whatever that allocation held: most plausibly zero for memory
    claimed at startup and never written, but not verified. The value only
    chooses whether the overlay holds the script for its 3 s; the story
    continues either way. 4_The_Great_Float_Caper's first script reaches this
    call before ever writing the slot, and used to stop there.
    """
    return bool(request.args[0] if request.args else retained_word(vm))


def retained_word(vm: KiwiVM) -> int:
    """The stack backing at SP, as a zero-word service 91 reads it; never written this session reads as 0 (above)."""
    if 0 <= vm.sp < len(vm._stack) and vm._stack[vm.sp] is None:
        return 0
    return vm.read_word(vm.stack_base + vm.sp)


@dataclass
class LoadingScreen:
    blocking: bool
    elapsed_ms: int = 0

    def tick(self, elapsed_ms: int) -> bool:
        self.elapsed_ms = min(3001, self.elapsed_ms + elapsed_ms)
        return self.elapsed_ms > 3000

    @property
    def frame(self):
        # FUN_0008952c: five common-pack frames, 500 ms each, repeated.
        return 23 + (self.elapsed_ms // 500) % 5

    def validate(self):
        if type(self.blocking) is not bool or type(self.elapsed_ms) is not int or not 0 <= self.elapsed_ms <= 3000:
            raise VMError('Invalid loading-screen state')
