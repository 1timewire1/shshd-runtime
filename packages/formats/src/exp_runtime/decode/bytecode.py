"""Lossless KiWi v2 decoding, verified against libshs09.so FUN_00057068.

This is a binary representation, not a reconstruction of game actions.
Data words may contain packed text, mutable variables, or other values.
"""
from dataclasses import dataclass
import struct


# int32 table at 0x002593a8: only entries equal to 1 consume an operand.
OPERAND_OPCODES = frozenset({
    0x01, 0x19, 0x1A, 0x1B, 0x1E, 0x1F, 0x20, 0x23,
    0x28, 0x29, 0x2A, 0x2B, 0x2C, 0x2D, 0x2E, 0x40, 0x41, 0x5C,
})


class KiwiFormatError(ValueError):
    """Unsupported or truncated KiWi input, with a file byte offset."""


@dataclass(frozen=True)
class BytecodeInstruction:
    pc: int
    byte_offset: int
    opcode: int
    operand: int | None

    @property
    def yield_id(self) -> int | None:
        if self.opcode == 0x1E:
            return self.operand
        if self.opcode == 0x1F:
            return self.operand >> 8
        return None

    def branch_target(self) -> int | None:
        """Statically encoded target in logical instruction indices.

        Native PC arithmetic wraps at 16 bits. Dynamic return opcode 0x43
        is deliberately not assigned a guessed target.
        """
        if self.opcode == 0x29:
            return self.operand
        if self.opcode in {0x28, 0x2A, 0x2B, 0x2C, 0x2D, 0x2E}:
            return (self.pc + self.operand) & 0xFFFF
        if self.opcode == 0x5C:
            return (self.pc + (self.operand >> 8)) & 0xFFFF
        return None


@dataclass(frozen=True)
class KiwiProgram:
    version: int
    previous_flag: int
    previous_data_count: int | None
    previous_instruction_count: int | None
    flag: int
    main_words: tuple[int, ...]
    gap_count: int
    extra_words: tuple[int, ...]
    instructions: tuple[BytecodeInstruction, ...]

    def to_bytes(self) -> bytes:
        """Re-encode every stored field without interpreting data words."""
        header = b'kiwi' + bytes((self.version, self.previous_flag))
        if self.previous_flag:
            header += struct.pack('>HH', self.previous_data_count,
                                  self.previous_instruction_count)
        header += bytes((self.flag,))
        header += struct.pack('>4H', len(self.main_words), self.gap_count,
                              len(self.extra_words), len(self.instructions))
        words = self.main_words + self.extra_words
        body = struct.pack(f'>{len(words)}H', *words)
        code = bytearray()
        for instruction in self.instructions:
            code.append(instruction.opcode)
            if instruction.operand is not None:
                code.extend(struct.pack('>H', instruction.operand))
        return header + body + code


def decode_program(data: bytes) -> KiwiProgram:
    """Decode v2 strictly; never turn truncated input into invented operands."""
    pos = 0

    def take(size):
        nonlocal pos
        if pos + size > len(data):
            raise KiwiFormatError(f'truncated KiWi at byte 0x{pos:x}: need {size} bytes')
        result = data[pos:pos + size]
        pos += size
        return result

    def u16():
        return struct.unpack('>H', take(2))[0]

    if take(4) != b'kiwi':
        raise KiwiFormatError('invalid KiWi signature at byte 0x0')
    version = take(1)[0]
    if version != 2:
        raise KiwiFormatError(f'unsupported KiWi version {version} at byte 0x4')
    previous_flag = take(1)[0]
    previous_data = u16() if previous_flag else None
    previous_code = u16() if previous_flag else None
    flag = take(1)[0]
    main, gap, extra, count = (u16() for _ in range(4))
    main_words = tuple(u16() for _ in range(main))
    extra_words = tuple(u16() for _ in range(extra))
    instructions = []
    base_pc = previous_code or 0
    for index in range(count):
        offset = pos
        opcode = take(1)[0]
        operand = u16() if opcode in OPERAND_OPCODES else None
        instructions.append(BytecodeInstruction(base_pc + index, offset, opcode, operand))
    if pos != len(data):
        raise KiwiFormatError(f'{len(data) - pos} trailing bytes at byte 0x{pos:x}')
    return KiwiProgram(version, previous_flag, previous_data, previous_code,
                       flag, main_words, gap, extra_words, tuple(instructions))
