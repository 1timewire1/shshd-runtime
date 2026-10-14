"""KiWi v2 execution core, derived from libshs09.so FUN_00055ce0.

The engine services yields separately. No game actions or query results
are guessed here. Uninitialized/out-of-range memory and unknown opcodes
raise VMError instead of imitating native undefined memory accesses.
"""
from collections import Counter, deque
from dataclasses import dataclass
from enum import Enum

from .decode.bytecode import KiwiProgram


def signed16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


class VMError(ValueError):
    pass


class StopKind(str, Enum):
    YIELD = 'yield'
    PAUSE = 'pause'
    HALT = 'halt'
    BUDGET = 'budget'


@dataclass(frozen=True)
class VMStop:
    kind: StopKind
    pc: int
    byte_offset: int
    yield_id: int | None = None
    args: tuple[int, ...] = ()


# Explicit break-only cases in the native switch, including opcode 0.
NATIVE_NOPS = frozenset({
    0, 2, 6, 9, 0x10, 0x14, 0x1D, 0x27, 0x2F, 0x30, 0x31,
    *range(0x34, 0x3E), 0x44, 0x45, 0x47, 0x49,
    *range(0x4B, 0x50), *range(0x55, 0x5A), 0x5D, 0x5E,
})


class KiwiVM:
    """One standalone script with persistent stack backing and mutable data.

    PC, SP, and FP start at zero (FUN_00055c6c). A, B, the result/count
    register, the data gap, and unused stack cells start unknown: native
    allocation/reset does not establish their contents. Stores initialize
    them. Stack capacity 0x400 comes from FUN_0009ef60/00056f1c.
    """

    def __init__(self, program: KiwiProgram, *, stack_capacity: int = 0x400):
        if program.previous_flag:
            raise VMError('linked KiWi segments are not yet executable')
        if not 0 < stack_capacity < 0x7FF5:
            raise VMError('invalid stack capacity')
        self.program = program
        self.stack_base = 0x7FF5 - stack_capacity
        self.data: list[int | None] = (
            [signed16(w) for w in program.main_words]
            + [None] * program.gap_count
            + [signed16(w) for w in program.extra_words]
        )
        if len(self.data) > self.stack_base:
            raise VMError('data overlaps the VM stack address range')
        self._stack: list[int | None] = [None] * stack_capacity
        self.pc = self.sp = self.fp = 0
        self.a: int | None = None
        self.b: int | None = None
        self.result: int | None = None  # native +0x36: argument count or result
        self.pending: VMStop | None = None
        self.steps_executed = 0
        self.opcode_counts: Counter[int] = Counter()
        self.recent_pcs: deque[int] = deque(maxlen=32)

    def _error(self, message: str) -> VMError:
        return VMError(f'pc={self.pc} sp={self.sp} fp={self.fp}: {message}')

    def _known(self, value: int | None, description: str) -> int:
        if value is None:
            raise self._error(f'uninitialized {description}')
        return value

    def _stack_word(self, index: int) -> int:
        if not 0 <= index < len(self._stack):
            raise self._error(f'stack address {index} out of range')
        return self._known(self._stack[index], f'stack word {index}')

    @property
    def stack(self) -> tuple[int | None, ...]:
        return tuple(self._stack[:self.sp])

    def read_word(self, address: int) -> int:
        address = signed16(address)
        if address >= self.stack_base:
            return self._stack_word(address - self.stack_base)
        if not 0 <= address < len(self.data):
            raise self._error(f'data address {address} out of range')
        return self._known(self.data[address], f'data word {address}')

    def write_word(self, address: int, value: int) -> None:
        address = signed16(address)
        if self.stack_base <= address < self.stack_base + len(self._stack):
            self._stack[address - self.stack_base] = signed16(value)
        elif 0 <= address < len(self.data):
            self.data[address] = signed16(value)
        else:
            raise self._error(f'write address {address} out of range')

    def _set_sp(self, value: int) -> None:
        value = signed16(value)
        if not 0 <= value <= len(self._stack):
            raise self._error(f'stack pointer {value} out of range')
        self.sp = value

    def _push(self, value: int) -> None:
        if self.sp == len(self._stack):
            raise self._error('stack overflow')
        self._stack[self.sp] = signed16(value)
        self.sp += 1

    def _pop(self) -> int:
        if not self.sp:
            raise self._error('stack underflow')
        value = self._stack_word(self.sp - 1)
        self.sp -= 1
        return value

    def _top(self) -> int:
        # The native interpreter peeks cell zero when SP is zero.
        return self._stack_word(max(0, self.sp - 1))

    def resume(self, result: int) -> None:
        """Complete a yield: discard its frame and set the result register.

        An explicit result is required even for void actions (normally 0).
        Merely calling run() again retains the same pending request.
        """
        if self.pending is None or self.pending.kind != StopKind.YIELD:
            raise self._error('no pending yield to resume')
        self._set_sp(self.sp - len(self.pending.args))
        self.result = signed16(result)
        self.pending = None

    def continue_after_pause(self) -> None:
        if self.pending is None or self.pending.kind != StopKind.PAUSE:
            raise self._error('no pending VM pause')
        self.pending = None

    def load_next(self, program: KiwiProgram) -> None:
        """Load a scheduled script after HALT, matching reset + loader.

        Native reset clears PC/SP/FP, but keeps registers and stack backing.
        Game state lives outside this machine and survives scene changes.
        """
        if self.pending is None or self.pending.kind != StopKind.HALT:
            raise self._error('next script requires a halted VM')
        validated = KiwiVM(program, stack_capacity=len(self._stack))
        self.program, self.data = validated.program, validated.data
        self.pc = self.sp = self.fp = 0
        self.pending = None
        self.recent_pcs.clear()

    def snapshot(self) -> dict:
        """Portable state, including popped cells still addressable by scripts."""
        from dataclasses import asdict
        return dict(pc=self.pc, sp=self.sp, fp=self.fp, a=self.a, b=self.b,
                    result=self.result, data=list(self.data), stack=list(self._stack),
                    pending=asdict(self.pending) if self.pending else None,
                    steps_executed=self.steps_executed,
                    opcode_counts={str(k): v for k, v in self.opcode_counts.items()},
                    recent_pcs=list(self.recent_pcs))

    @classmethod
    def from_snapshot(cls, program: KiwiProgram, state: dict):
        """Restore state against the original program; reject incompatible saves."""
        def integer(value, low, high):
            if type(value) is not int or not low <= value <= high:
                raise VMError('Invalid integer in VM snapshot')
            return value

        def word(value):
            return None if value is None else integer(value, -32768, 32767)

        try:
            stack = state['stack']
            if not isinstance(stack, list):
                raise VMError('Invalid stack in VM snapshot')
            vm = cls(program, stack_capacity=len(stack))
            if (set(state) != set(vm.snapshot()) or not isinstance(state['data'], list)
                    or len(state['data']) != len(vm.data)):
                raise VMError('VM snapshot shape does not match the loaded script')
            vm._stack = [word(v) for v in stack]
            vm.data = [word(v) for v in state['data']]
            vm.pc = integer(state['pc'], 0, len(program.instructions))
            vm.sp = integer(state['sp'], 0, len(stack))
            vm.fp = integer(state['fp'], 0, len(stack))
            vm.a, vm.b, vm.result = (word(state[k]) for k in ('a', 'b', 'result'))
            vm.steps_executed = integer(state['steps_executed'], 0, 2**63 - 1)
            vm.opcode_counts = Counter({integer(int(k), 0, 255): integer(v, 0, vm.steps_executed)
                                       for k, v in state['opcode_counts'].items()})
            if sum(vm.opcode_counts.values()) != vm.steps_executed:
                raise VMError('VM instruction counters disagree')
            recent = state['recent_pcs']
            if not isinstance(recent, list) or len(recent) > 32:
                raise VMError('Invalid VM instruction history')
            vm.recent_pcs = deque((integer(v, 0, len(program.instructions) - 1)
                                   for v in recent), maxlen=32)
            saved = state['pending']
            if saved is not None:
                kind = StopKind(saved['kind'])
                pc = integer(saved['pc'], 0, len(program.instructions) - 1)
                instruction = program.instructions[pc]
                args = tuple(integer(v, -32768, 32767) for v in saved['args'])
                vm.pending = VMStop(kind, pc, saved['byte_offset'], saved['yield_id'], args)
                if set(saved) != {'kind', 'pc', 'byte_offset', 'yield_id', 'args'}:
                    raise VMError('Invalid suspended request shape')
                expected_pc = pc if kind == StopKind.HALT else (pc + 1) & 0xffff
                if vm.pc != expected_pc or saved['byte_offset'] != instruction.byte_offset:
                    raise VMError('Suspended request does not match the saved PC')
                if kind == StopKind.YIELD:
                    op, arg = instruction.opcode, instruction.operand
                    if op not in (0x1e, 0x1f) or saved['yield_id'] != (arg if op == 0x1e else arg >> 8):
                        raise VMError('Suspended service does not match the script')
                    if (len(args) > vm.sp or tuple(stack[vm.sp - len(args):vm.sp]) != args
                            or (op == 0x1f and len(args) != (arg & 255))):
                        raise VMError('Suspended service frame does not match the saved stack')
                elif kind not in (StopKind.PAUSE, StopKind.HALT) or args or saved['yield_id'] is not None:
                    raise VMError('Invalid suspended VM stop')
                elif instruction.opcode != (0x32 if kind == StopKind.PAUSE else 0x33):
                    raise VMError('Suspended stop does not match the script')
            return vm
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            if isinstance(error, VMError):
                raise
            raise VMError(f'Invalid VM snapshot: {error}') from error

    def run(self, max_steps: int = 100_000) -> VMStop:
        """Execute until a yield, pause, halt, or instruction budget boundary."""
        if max_steps < 1:
            raise ValueError('max_steps must be positive')
        if self.pending is not None:
            return self.pending
        for _ in range(max_steps):
            if not 0 <= signed16(self.pc) < len(self.program.instructions):
                raise self._error('instruction address out of range')
            instruction = self.program.instructions[self.pc]
            op = instruction.opcode
            arg = instruction.operand
            next_pc = self.pc + 1
            self.recent_pcs.append(self.pc)
            self.opcode_counts[op] += 1
            self.steps_executed += 1
            if op in NATIVE_NOPS:
                pass
            elif op == 0x01:
                self.a = signed16(arg)
            elif op == 0x03:
                self.a = self._pop()
            elif op == 0x04:
                self.b = self._pop()
            elif op == 0x05:
                self.a = self._top()
            elif op in (0x07, 0x08):
                self._push(self._known(self.a if op == 7 else self.b, 'register A/B'))
            elif op in (0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x11, 0x12,
                        0x50, 0x51, 0x52, 0x53, 0x54):
                right, left = self._pop(), self._pop()
                if op == 0x0A:
                    value = left == right
                elif op == 0x0B:
                    value = left != right
                elif op == 0x0C:
                    value = left > right
                elif op == 0x0D:
                    value = left >= right
                elif op == 0x0E:
                    value = left < right
                elif op == 0x0F:
                    value = left <= right
                elif op == 0x11:
                    value = bool(left or right)
                elif op == 0x12:
                    value = bool(left and right)
                elif op == 0x50:
                    value = left + right
                elif op == 0x51:
                    value = left - right
                elif op == 0x52:
                    value = left * right
                else:
                    if right == 0:
                        raise self._error('division by zero')
                    quotient = abs(left) // abs(right)
                    if (left < 0) != (right < 0):
                        quotient = -quotient
                    value = quotient if op == 0x53 else left - quotient * right
                self._push(int(value))
            elif op == 0x13:
                self._push(int(not self._pop()))
            elif 0x15 <= op <= 0x19:
                self._set_sp(self.sp - (arg if op == 0x19 else op - 0x14))
            elif op == 0x1A:
                self._push(arg)
            elif op == 0x1B:
                for byte in (arg & 0xFF, arg >> 8):
                    self._push(byte - 0x100 if byte > 0x7F else byte)
            elif op == 0x1C:
                self._push(self._top())
            elif op in (0x1E, 0x1F):
                count = (arg & 0xFF) if op == 0x1F else self._known(self.result, 'argument count')
                if not 0 <= count <= self.sp:
                    raise self._error(f'invalid yield argument count {count}')
                arguments = tuple(self._stack_word(i) for i in range(self.sp - count, self.sp))
                self.pending = VMStop(StopKind.YIELD, self.pc, instruction.byte_offset,
                                      arg >> 8 if op == 0x1F else arg, arguments)
                self.result = -1  # dispatcher moves the count to its frame metadata
            elif op == 0x20:
                self.result = signed16(arg)
            elif op == 0x21:
                self._push(self._known(self.result, 'result register'))
            elif op == 0x22:
                old_fp = self._stack_word(self.fp - 1)
                self._set_sp(self.fp - 1)
                self.fp = old_fp
            elif op == 0x23:
                self._push(self.stack_base + self.fp + arg)
            elif op == 0x24:
                self._push(-self._pop())
            elif op in (0x25, 0x26):
                address = self._known(self.a, 'register A')
                self.write_word(address, self.read_word(address) + (1 if op == 0x25 else -1))
            elif op == 0x28:
                next_pc = self.pc + arg
            elif op == 0x29:
                next_pc = arg
            elif 0x2A <= op <= 0x2E:
                value = self._top() if op in (0x2C, 0x2D) else self._pop()
                if op == 0x2E:
                    take_branch = value == self._known(self.a, 'register A')
                else:
                    take_branch = (value != 0) if op in (0x2A, 0x2C) else (value == 0)
                if take_branch:
                    next_pc = self.pc + arg
            elif op == 0x32:
                self.pending = VMStop(StopKind.PAUSE, self.pc, instruction.byte_offset)
            elif op == 0x33:
                next_pc = self.pc
                self.pending = VMStop(StopKind.HALT, self.pc, instruction.byte_offset)
            elif op == 0x3E:
                value, address = self._pop(), self._pop()
                self.write_word(address, value)
                self._push(value)
            elif op == 0x3F:
                if not self.sp:
                    raise self._error('stack underflow')
                self._stack[self.sp - 1] = self.read_word(self._top())
            elif op == 0x40:
                self._push(self.read_word(arg))
            elif op == 0x41:
                self._push(self.read_word(self.stack_base + self.fp + arg))
            elif op == 0x42:
                self._push(self.pc + 1)
            elif op == 0x43:
                next_pc = self._pop() + 1
            elif op == 0x46:
                if not self.sp:
                    raise self._error('stack underflow')
                self._set_sp(self._top())
            elif op == 0x48:
                self._push(self.fp)
            elif op == 0x4A:
                self.fp = self.sp
            elif op in (0x5A, 0x5B):
                self._push(op - 0x5A)
            elif op == 0x5C:
                if self._known(self.a, 'register A') == (arg & 0xFF):
                    next_pc = self.pc + (arg >> 8)
            elif 0x5F <= op <= 0x62:
                self._push(self.stack_base + self.fp + op - 0x5F)
            else:
                raise self._error(f'unsupported opcode 0x{op:02x}')
            self.pc = next_pc & 0xFFFF
            if self.pending is not None:
                return self.pending
        instruction = self.program.instructions[self.recent_pcs[-1]]
        return VMStop(StopKind.BUDGET, instruction.pc, instruction.byte_offset)
