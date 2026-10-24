"""Rewrite a KiWi program's host calls for another game's host ABI without moving a single instruction.

Every original instruction keeps its index, so branch targets, saved return addresses and code addresses stored in data
stay valid. A host call (`0x1f`, service and argument count in its operand) is either renamed in place (same arguments,
same order, another service) or replaced by one `0x29` jump to a per-site trampoline appended after the code:

    trampoline:  0x1a <site>       push the call site's index as the return address
                 0x29 <shim>       jump to the shim for this (service, argument count)

A shim reads the original arguments from below that return address, makes the new host call(s) and returns to the
instruction after the original call with the original arguments removed and the result in R, as the original host
call left them:

    0x48, 0x4a                     push FP, FP = SP            (argument i of n is LOAD_FRAME(i - n - 3), 1-based)
    ...body...                     new host calls; R holds the result the caller pushes with 0x21
    0x23 (-2-n), 0x41 (-2)         address of argument 1, the return address
    0x3e, 0x15                     store the return address over argument 1
    0x22                           LEAVE: SP = FP - 1, FP = saved FP
    0x19 n                         drop the arguments (argument 1's cell, now the return address, is the top)
    0x43                           RETURN to the return address + 1

Data the shims need (strings, scratch words, tables) is appended after the program's extra bank, so no existing data
address moves either. Nothing here knows any game's services; `newrules.py` supplies the mapping.
"""
from dataclasses import replace

from exp_runtime.decode.bytecode import BytecodeInstruction, KiwiProgram, OPERAND_OPCODES, decode_program

STACK_BASE = 0x7bf5                     # the VM's stack starts here; data must stay below it


class RewriteError(ValueError):
    pass


def word(value):
    """A signed or unsigned value as an operand word."""
    if not -0x8000 <= value <= 0xffff:
        raise RewriteError(f'{value} does not fit a KiWi word')
    return value & 0xffff


class Shim:
    """The body of one shim: helpers emit KiWi with labels; argument i (1-based) of the original call is `arg(i)`."""

    def __init__(self, rewriter, argc):
        self.rewriter, self.argc, self.code, self.labels, self._serial = rewriter, argc, [], {}, 0

    def emit(self, opcode, operand=None):
        self.code.append((opcode, operand))

    def label(self, name=None):
        """A new label name, or place `name` here."""
        if name is None:
            self._serial += 1
            return f'L{self._serial}'
        self.labels[name] = len(self.code)
        return name

    def arg(self, i):
        if not 1 <= i <= self.argc:
            raise RewriteError(f'argument {i} of {self.argc}')
        self.emit(0x41, word(i - self.argc - 3))

    def push(self, value):
        self.emit(0x1a, word(value))

    def text(self, value):
        self.push(self.rewriter.text(value))

    def call(self, service, count):
        if not 0 <= service <= 255 or not 0 <= count <= 255:
            raise RewriteError(f'service {service} with {count} arguments')
        self.emit(0x1f, service << 8 | count)

    def result(self, value):
        """R = value, for a shim whose original service returned a constant."""
        self.emit(0x20, word(value))

    def push_result(self):
        self.emit(0x21)

    def jump(self, target):
        self.emit(0x29, target)

    def jump_if_zero(self, target):
        self.emit(0x2b, target)          # pops; the relative target is resolved by `assemble`

    def jump_if_nonzero(self, target):
        self.emit(0x2a, target)

    def select(self, i, table, default=None):
        """Push table[argument i] (a dict of ints), or `default` (None: the argument itself) when it isn't listed."""
        end = self.label()
        for key, value in table.items():
            other = self.label()
            self.arg(i); self.push(key); self.emit(0x0a)
            self.jump_if_zero(other)
            self.push(value); self.jump(end)
            self.label(other)
        if default is None:
            self.arg(i)
        else:
            self.push(default)
        self.label(end)


class Rewriter:
    def __init__(self, program: KiwiProgram, zero_gap=False):
        """`zero_gap`: the source engine allocates data as one zeroed array (New Rules' Java `new short[main + gap +
        extra]`, r.java), so its scripts may read gap words they never wrote; the output stores them as zeros."""
        if program.previous_flag:
            raise RewriteError('linked KiWi segments are not supported')
        self.program, self.zero_gap = program, zero_gap
        self.code = [(i.opcode, i.operand) for i in program.instructions]
        self.original = len(self.code)
        self.extra = list(program.extra_words)
        self.data_end = len(program.main_words) + program.gap_count + len(self.extra)
        self.strings, self.shims, self.sites, self.start = {}, {}, {}, None

    # -- data ------------------------------------------------------------------------------------------------------
    def words(self, values):
        """Append words after the extra bank; returns the first one's address."""
        address = len(self.program.main_words) + self.program.gap_count + len(self.extra)
        self.extra.extend(word(v) for v in values)
        if address + len(values) >= STACK_BASE:
            raise RewriteError('appended data reaches the VM stack')
        return address

    def text(self, value):
        """The address of a NUL-terminated Latin-1 string (packed two bytes a word, high byte first)."""
        if value not in self.strings:
            data = value.encode('latin-1') + b'\0'
            if len(data) % 2:
                data += b'\0'
            self.strings[value] = self.words([data[i] << 8 | data[i + 1] for i in range(0, len(data), 2)])
        return self.strings[value]

    # -- call sites ------------------------------------------------------------------------------------------------
    def calls(self):
        """(pc, service, argument count) of every original packed host call."""
        result = []
        for pc, (opcode, operand) in enumerate(self.code[:self.original]):
            if opcode == 0x1e:
                raise RewriteError(f'register-count host call at {pc} is not supported')
            if opcode == 0x1f:
                result.append((pc, operand >> 8, operand & 255))
        return result

    def rename(self, pc, service):
        opcode, operand = self.code[pc]
        assert opcode == 0x1f and pc < self.original
        self.code[pc] = (0x1f, service << 8 | operand & 255)
        self.sites[pc] = ('rename', service)

    def redirect(self, pc, key, build):
        """Send the call at `pc` through the shim `key`, built once by `build(shim)` for this argument count."""
        opcode, operand = self.code[pc]
        assert opcode == 0x1f and pc < self.original
        argc = operand & 255
        shim_key = (key, argc)
        if shim_key not in self.shims:
            shim = Shim(self, argc)
            build(shim)
            self.shims[shim_key] = shim
        self.sites[pc] = ('shim', shim_key)

    def replace_function(self, pc, key, build):
        """Run the shim `key` instead of the function starting at `pc` (its PUSH_FP). The shim has no arguments; it
        returns to the function's caller (whose SAVE_RETURN is still on the stack) and sets what the caller reads."""
        opcode, _ = self.code[pc]
        if opcode != 0x48 or pc >= self.original:
            raise RewriteError(f'no function starts at {pc}')
        shim_key = (key, 'function')
        if shim_key not in self.shims:
            shim = Shim(self, 0)
            build(shim)
            self.shims[shim_key] = shim
        self.sites[pc] = ('function', shim_key)

    def replace_call(self, pc, key, argc, build):
        """Run the shim `key` instead of the function the jump at `pc` enters (a SAVE_RETURN + JUMP call into code this
        program doesn't hold, such as New Rules' minigame library). The shim reads the caller's `argc` arguments with
        `arg(i)` and returns to the caller, which drops them itself, as it did for the original function."""
        opcode, _ = self.code[pc]
        if opcode != 0x29 or pc >= self.original:
            raise RewriteError(f'no jump at {pc}')
        shim_key = (key, 'call', argc)
        if shim_key not in self.shims:
            shim = Shim(self, argc)
            shim.function = True
            build(shim)
            self.shims[shim_key] = shim
        self.sites[pc] = ('function', shim_key)

    def prologue(self, build):
        """Code that runs once before the program's first instruction (built like a shim body, without arguments)."""
        self.start = Shim(self, 0)
        build(self.start)

    # -- output ----------------------------------------------------------------------------------------------------
    def finish(self) -> KiwiProgram:
        code = list(self.code)
        starts = {}
        for key, shim in self.shims.items():
            starts[key] = len(code)
            code.extend(_assemble(shim, len(code)))
        for pc, site in sorted(self.sites.items()):
            if site[0] == 'shim':
                trampoline = len(code)
                code.extend([(0x1a, pc), (0x29, starts[site[1]])])
                code[pc] = (0x29, trampoline)
            elif site[0] == 'function':
                code[pc] = (0x29, starts[site[1]])
        if self.start is not None:
            # Instruction 0 moves to the end of the prologue block and becomes a jump to it. A relative jump there
            # becomes an absolute one; other relative branches at 0 are not supported.
            first, operand = code[0]
            if first == 0x28:
                first, operand = 0x29, operand & 0xffff
            elif first in (0x2a, 0x2b, 0x2c, 0x2d, 0x2e, 0x5c):
                raise RewriteError('a conditional branch at instruction 0 cannot take a prologue')
            block = len(code)
            code.extend(_assemble(self.start, block, frame=False))
            code.extend([(first, operand), (0x29, 1)])
            code[0] = (0x29, block)
        if len(code) > 0x7fff:
            raise RewriteError(f'{len(code)} instructions exceed the KiWi limit')
        instructions = tuple(BytecodeInstruction(pc, 0, opcode, operand) for pc, (opcode, operand) in enumerate(code))
        program = replace(self.program, extra_words=tuple(self.extra), instructions=instructions)
        if self.zero_gap:
            program = replace(program, main_words=program.main_words + (0,) * program.gap_count, gap_count=0)
        return decode_program(program.to_bytes())          # recomputes byte offsets, checks the encoding


def _assemble(shim, start, frame=True):
    n = 0 if getattr(shim, 'function', False) else shim.argc       # a function's caller drops its own arguments
    body = ([(0x48, None), (0x4a, None)] if frame else []) + shim.code
    offset = 2 if frame else 0                              # labels are indices into shim.code
    epilogue = []
    if frame:
        if n:
            epilogue += [(0x23, word(-2 - n)), (0x41, word(-2)), (0x3e, None), (0x15, None)]
        epilogue += [(0x22, None)] + ([(0x19, n)] if n else []) + [(0x43, None)]
    end = len(body)
    labels = {name: index + offset for name, index in shim.labels.items()}
    out = []
    for index, (opcode, operand) in enumerate(body + epilogue):
        if isinstance(operand, str):
            target = labels[operand] if operand in labels else None
            if target is None:
                raise RewriteError(f'unplaced label {operand}')
            operand = target + start if opcode == 0x29 else word(target - index)
        if opcode not in OPERAND_OPCODES and operand is not None:
            raise RewriteError(f'opcode 0x{opcode:02x} takes no operand')
        out.append((opcode, operand))
    assert len(out) == end + len(epilogue)
    return out
