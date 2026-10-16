"""Service 91's application overlay and host execution gate.

FUN_0008e7d0 accumulates active milliseconds; FUN_0009ea70 clears the
overlay only once the counter is strictly greater than 3000.
"""
from dataclasses import dataclass

from .vm import KiwiVM, VMError, VMStop


def loading_waits(vm: KiwiVM, request: VMStop) -> bool:
    """Read the dispatcher's first frame slot, even for a zero-word call.

    FUN_0009fe3c reads stack[SP - argc] without checking argc. With no
    arguments this is retained backing at SP, not an implicit zero. Unknown
    backing must still stop explicitly through read_word().
    """
    return bool(request.args[0] if request.args else vm.read_word(vm.stack_base + vm.sp))


@dataclass
class LoadingScreen:
    blocking: bool
    elapsed_ms: int = 0

    def tick(self, elapsed_ms: int) -> bool:
        self.elapsed_ms = min(3001, self.elapsed_ms + elapsed_ms)
        return self.elapsed_ms > 3000

    @property
    def frame(self):
        return self.animation_frame()

    def animation_frame(self, *, ios=False):
        # Android 0008952c/00136a30: 500 ms per frame. Both iOS games'
        # initLoadingBar (SHS 0003da88, CoD 0001d4cc) use 70 ms instead.
        # This presentation clock does not change the service-91 wait.
        return 23 + (self.elapsed_ms // (70 if ios else 500)) % 5

    def validate(self):
        if type(self.blocking) is not bool or type(self.elapsed_ms) is not int or not 0 <= self.elapsed_ms <= 3000:
            raise VMError('Invalid loading-screen state')
