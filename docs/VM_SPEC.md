# KiWi bytecode and virtual machine specification

Revision: 2026-09-13. Companion to [SCHEMA.md](SCHEMA.md), the EXP container specification. This defines the complete recovered **KiWi v2 core instruction set** in Android SHS 1.0.9 and the host-call boundary needed to execute scripts. [ENGINE_ABI.md](ENGINE_ABI.md) inventories all dispatcher IDs 0–100, including services whose gameplay semantics remain unresolved.

This is a reverse-engineered specification, not an original vendor document. A complete core VM does not imply a complete game engine. Rendering, choices, minigames, audio, persistence, and resource banks belong to host services. The Python executor currently supports standalone v2 programs and a verified subset of those services.

## 1. Evidence and conventions

The binary identity and evidence terminology are in [SCHEMA.md](SCHEMA.md#1-evidence-and-notation). Primary sources:

| Address | Role | Saved evidence |
| --- | --- | --- |
| `0x00057068` | KiWi loader | `native-kiwi-loader.c` |
| `0x002593a8` | 99-entry operand-width table, native LE int32 | `native-operand-table.json` |
| `0x00055ce0` | Core interpreter | `native-kiwi-vm.c` |
| `0x00055c08`, `0x00055c88`, `0x00056b78` | Constructor, memory reader, packed-string writer | `native-vm-spec-helpers.c` |
| `0x00055c6c`, `0x00056f1c`, `0x0009ef60` | Reset and stack allocation | `native-runtime-helpers.c` |
| `0x0009fe3c`, `0x0009e888` | Yield dispatcher and asynchronous completion | `native-yield-dispatcher.c`, `native-runtime-helpers.c` |
| `0x0009f258`, `0x0009f420` | Packed text and argument string references | `native-vm-spec-helpers.c` |

Instruction mnemonics below are descriptive names assigned here. They are not recovered symbols. Opcode numbers are hexadecimal; host service IDs are usually decimal and are explicitly distinguished.

```text
u16(x) = x & 0xffff
s16(x) = u16(x) if u16(x) < 0x8000 else u16(x) - 0x10000
s8(x)  = (x & 0xff) if (x & 0xff) < 0x80 else (x & 0xff) - 0x100
hi8(x) = (x >> 8) & 0xff
lo8(x) = x & 0xff
```

All serialized words and immediate operands are **big-endian**. This is independent of the native ARM CPU's little-endian memory layout. Data values are untyped 16-bit bit patterns; an instruction or host signature determines whether a value means a signed integer, word address, resource ID, text reference, or packed bytes.

## 2. KiWi v2 file schema

KiWi is the decoded payload of an EXP script resource. An extractor's `.kiw` extension is conventional. There is no per-script resource ID or filename inside this header.

```text
KiwiV2 :=
    magic                       : bytes[4] = "kiwi"
    version                     : u8 = 2
    previous_flag               : u8                 # zero / nonzero
    if previous_flag != 0:
        previous_data_count     : u16be
        previous_code_count     : u16be
    reserved_flag               : u8                 # consumed; meaning unknown
    main_count                  : u16be
    gap_count                   : u16be
    extra_count                 : u16be
    instruction_count           : u16be
    main_words                  : u16be[main_count]
    extra_words                 : u16be[extra_count] # no serialized gap words
    instructions                : Instruction[instruction_count]

Instruction :=
    opcode                      : u8
    if opcode in OPERAND_OPCODES:
        immediate               : u16be
```

### 2.1 Header offsets

| Field | Standalone offset | Linked offset | Bytes |
| --- | ---: | ---: | ---: |
| `magic` | 0 | 0 | 4 |
| `version` | 4 | 4 | 1 |
| `previous_flag` | 5 | 5 | 1 |
| `previous_data_count` | absent | 6 | 2 |
| `previous_code_count` | absent | 8 | 2 |
| `reserved_flag` | 6 | 10 | 1 |
| `main_count` | 7 | 11 | 2 |
| `gap_count` | 9 | 13 | 2 |
| `extra_count` | 11 | 15 | 2 |
| `instruction_count` | 13 | 17 | 2 |
| First serialized data word / code if no words | 15 | 19 | variable |

A standalone header is 15 bytes; a linked header is 19. The four counts are word/element counts, not byte lengths. With header length `H`, `M=main_count`, `E=extra_count`, `I=instruction_count`, and `K` operand-bearing instructions:

```text
code_byte_offset = H + 2*(M + E)
file_length      = H + 2*(M + E) + I + 2*K
```

`gap_count` does not contribute bytes to the file. There is no stored jump table or separate table of string starts. An operand is always present for an operand-bearing opcode, even if it is zero.

All 987 corpus scripts use version 2, `previous_flag=0`, and `reserved_flag=0`. They decode to exactly the declared count and end at EOF. The native loader consumes the magic without comparing it, reads flags as booleans, and discards the reserved flag. A lossless decoder preserves the original bytes; a validating decoder should check the magic and supported version.

The loader uses signed-short reads for counts and stores some totals in signed shorts. Treat `0x8000`–`0xffff` count encodings as unsupported for execution; do not infer a working 65,535-instruction machine from the wire widths. The lossless representation preserves the unsigned bits. Sizes must also fit the memory regions described below.

The native version branch omits `previous_flag` and its counts for legacy versions 0/1; ordinary positive versions above 1 take the extended-header path. Legacy semantics and later versions are unverified. The implementation accepts only v2; changing the version byte is not a compatibility conversion.

### 2.2 Instruction lengths and program counters

The operand table at `0x002593a8` has 99 native 32-bit entries, one for each opcode `0x00`–`0x62`. Only entries equal to 1 cause a two-byte operand read:

```text
OPERAND_OPCODES = {
    01, 19, 1a, 1b, 1e, 1f, 20, 23,
    28, 29, 2a, 2b, 2c, 2d, 2e, 40, 41, 5c
}
```

These instructions occupy three file bytes. Every other opcode in the recovered set occupies one. The native loader builds separate opcode and operand arrays; execution does not scan variable-length bytes.

The other table values are 0 and -1; neither consumes an operand. The -1 slots
are unused entries whose interpreter cases currently do nothing. Preserve the
distinction in tooling if retaining the native table; it is not another encoded
instruction width.

**PC counts decoded instructions, never file bytes or data words.** Retain both PC and encoded byte offset in disassembly. For standalone programs, instruction 0 starts at `code_byte_offset`. Relative branch offsets are added to the branch's own PC; the normal next instruction is `pc + 1`.

Bytes outside `0x00`–`0x62` are stored without an operand by the inspected loader, and the interpreter's default path advances. Their intended semantics are unknown. The lossless Python decoder preserves them as one-byte instructions, but the executor rejects them. Do not assign them a fabricated operation or operand width.

### 2.3 Linked segments

`previous_*` names reflect the existing decoder API; the native fields act as **split boundaries**. `previous_code_count` is the boundary between primary and secondary instruction arrays; `previous_data_count` is the analogous data-word boundary. The lossless decoder labels the newly read instructions starting at `previous_code_count`.

When `previous_flag` is nonzero, the native loader records these boundaries and moves the newly read arrays into secondary slots. It clears the primary pointers after moving them; earlier primary arrays have already been freed in this routine. The flag alone therefore does **not** preserve the previously loaded script. A separate loading/attachment sequence must supply the primary segment. That sequence and its entry PC have not been verified.

With both segments available, the interpreter selects primary code for signed `PC < code_boundary`; otherwise it indexes secondary code at `PC - code_boundary`. Data lookup uses the analogous boundary after checking the stack range. Constructor defaults for both boundaries are `0x8000`.

There are no linked corpus fixtures. Binary round trips have synthetic coverage; the Python executor rejects linked programs. The fields and observed array selection are specified here without claiming a complete working segment-loading lifecycle.

## 3. Machine state and memory

### 3.1 Registers and status

| Native state offset | Width | Name / meaning |
| --- | --- | --- |
| `+0x08` | 32 bits | Most recently loaded instruction count |
| `+0x0c`, `+0x10`, `+0x14` | pointers | Primary opcodes, operands, and data |
| `+0x18`, `+0x1c`, `+0x20` | pointers | Secondary opcodes, operands, and data |
| `+0x24`, `+0x28` | 32 bits | Code and data split boundaries |
| `+0x30` | 16 bits | `PC`, instruction index |
| `+0x32` | 16 bits | `SP`, next free stack cell |
| `+0x34` | 16 bits | `FP`, frame pointer measured in stack cells |
| `+0x36` | 16 bits | `R`, host argument count / return value register |
| `+0x38`, `+0x3a` | 16 bits | General registers `A`, `B` |
| `+0x3c` | 16 bits | Virtual word address of stack cell 0 |
| `+0x40` | 32 bits | Stack capacity in words |
| `+0x44` | pointer | Stack backing array |
| `+0x48` | 16 bits | Loaded segment's total data words |
| `+0x4a`, `+0x4c`, `+0x4e` | 16 bits | Main, extra, and gap counts respectively |
| `+0x50` | 16 bits | Last yield service ID |
| `+0x52` | 8 bits | Execution status |

| Status | Meaning |
| ---: | --- |
| 1 | Yielded to host |
| 2 | Running / ready to execute |
| 3 | Paused by opcode `0x32` |
| 4 | Halted by opcode `0x33` |

The native runner returns 0 on a yield and 1 on pause, halt, or an instruction-budget return. Its entry guard explicitly checks HALT; it does not itself enforce the Python API's pending-request guard. Engine code is responsible for waiting before re-entry.

### 3.2 Data segment

For a standalone program, the allocated data array is:

```text
address 0 .. M-1             = main_words
address M .. M+G-1           = gap, no initializer in inspected loader
address M+G .. M+G+E-1       = extra_words
```

`M=main_count`, `G=gap_count`, `E=extra_count`. Main and extra words use the same address space. Both can hold text, mutable values, tables, and pointers. Names such as “string table 1/2” are not a type guarantee. The gap is reserved memory, not serialized zero padding.

### 3.3 Stack and virtual word addresses

The engine allocates `0x400` = 1024 stack words through `FUN_0009ef60` / `FUN_00056f1c`. The virtual stack base is:

```text
stack_base = 0x7ff5 - capacity = 0x7bf5
```

| Word-address region | Meaning in the standalone engine profile |
| --- | --- |
| `0 .. data_length-1` | Program data, where below `stack_base` |
| Remaining addresses below `stack_base` | No valid allocated data cell unless supplied by a linked segment |
| `0x7bf5 .. 0x7ff4` | 1024 stack backing cells |
| `0x7ff5 .. 0x7fff` | Runtime string handles when interpreted by the host; **not** valid word-memory cells |
| Negative signed addresses | Invalid except documented host sentinels such as text reference -1 |

The native address dispatcher checks the stack base first, then the segment boundary. It does not verify actual allocation bounds. The Python executor rejects out-of-range accesses and data that overlaps the stack range.

Stack storage is persistent: dropping, popping, or lowering SP does not clear cells. A direct word address may still read a previously written cell above the current SP. Raising SP allocates logical slots without initializing their contents. Code and operand arrays are separate from word memory and cannot be read through these word-address operations.

### 3.4 Initialization and reset

`FUN_00055c6c` sets `PC=SP=FP=0` and status 2. Neither that reset nor the inspected constructor establishes initial A, B, or R values. The data gap and new stack allocation are not initialized by the inspected paths. Do not assume zeros. Native uninitialized reads have no reproducible value guaranteed by this specification.

The Python VM tracks unknown cells/registers and faults on their first read. Scene reload through `load_next()` replaces data and resets PC/SP/FP while preserving register values and stack backing. This models the observed reset/load operations; it is not native saved-game deserialization.

## 4. Complete core opcode table

Let `pc` be PC before an instruction; unless explicitly assigned below, the resulting PC is `u16(pc + 1)`. Let `imm` be the operand's unsigned 16-bit bit pattern, `S` the backing stack, and `M[address]` a virtual word-memory access with signed address interpretation. All stored/pushed values narrow to `s16`.

```text
push(x): S[SP] = s16(x); SP = s16(SP + 1)
pop():   SP = s16(SP - 1); return S[SP]
peek():  return S[SP - 1]                # for SP > 0
binary(f): right = pop(); left = pop(); push(f(left, right))
```

For SP=0, the native interpreter prefetches cell 0 as its peek value. That does not authorize a pop from an empty stack. The executor permits a peek of initialized cell 0 but rejects an uninitialized read. Native memory errors are outside the valid-program semantics.

`ΔSP` is the immediate instruction effect, before any later host completion. Boolean results are 0 or 1. Conditional branches fall through when their condition is false; pop branches consume their condition either way. `NOP` rows are the native default/break behavior, not missing research placeholders.

| Opcode (hex) | Immediate | ΔSP | Descriptive mnemonic | Operation |
| --- | --- | ---: | --- | --- |
| `00` | — | 0 | NOP | No operation; advance PC. |
| `01` | u16 | 0 | LOAD_A | A = s16(imm). |
| `02` | — | 0 | NOP | No operation; advance PC. |
| `03` | — | -1 | POP_A | A = pop(). |
| `04` | — | -1 | POP_B | B = pop(). |
| `05` | — | 0 | PEEK_A | A = peek(). |
| `06` | — | 0 | NOP | No operation; advance PC. |
| `07` | — | +1 | PUSH_A | push(A). |
| `08` | — | +1 | PUSH_B | push(B). |
| `09` | — | 0 | NOP | No operation; advance PC. |
| `0a` | — | -1 | EQ | binary(left == right). |
| `0b` | — | -1 | NE | binary(left != right). |
| `0c` | — | -1 | GT | binary(left > right), signed. |
| `0d` | — | -1 | GE | binary(left >= right), signed. |
| `0e` | — | -1 | LT | binary(left < right), signed. |
| `0f` | — | -1 | LE | binary(left <= right), signed. |
| `10` | — | 0 | NOP | No operation; advance PC. |
| `11` | — | -1 | BOOL_OR | binary(bool(left) or bool(right)). |
| `12` | — | -1 | BOOL_AND | binary(bool(left) and bool(right)). |
| `13` | — | 0 | BOOL_NOT | push(pop() == 0). |
| `14` | — | 0 | NOP | No operation; advance PC. |
| `15` | — | -1 | DROP_1 | SP = s16(SP - 1); backing retained. |
| `16` | — | -2 | DROP_2 | SP = s16(SP - 2). |
| `17` | — | -3 | DROP_3 | SP = s16(SP - 3). |
| `18` | — | -4 | DROP_4 | SP = s16(SP - 4). |
| `19` | u16 | variable | ADJUST_SP | SP = s16(SP - imm); negative imm allocates without initialization. |
| `1a` | u16 | +1 | PUSH_IMM | push(s16(imm)). |
| `1b` | u16 | +2 | PUSH_I8_PAIR | push(s8(lo8(imm))); push(s8(hi8(imm))), in that order. |
| `1c` | — | +1 | DUP | push(peek()). |
| `1d` | — | 0 | NOP | No operation; advance PC. |
| `1e` | u16 | 0 | YIELD | yield_id = imm; PC = u16(pc + 1); status = 1; stop. R supplies host argument count. |
| `1f` | u16 | 0 | YIELD_PACKED | yield_id = hi8(imm); R = lo8(imm); PC = u16(pc + 1); status = 1; stop. |
| `20` | u16 | 0 | LOAD_R | R = s16(imm). |
| `21` | — | +1 | PUSH_R | push(R); no automatic result push occurs at a yield. |
| `22` | — | variable | LEAVE | old = FP; SP = s16(old - 1); FP = S[old - 1]. |
| `23` | u16 | +1 | FRAME_ADDRESS | push(stack_base + FP + s16(imm)). |
| `24` | — | 0 | NEG | push(-pop()). |
| `25` | — | 0 | INC_INDIRECT_A | M[A] = s16(M[A] + 1); no stack operand. |
| `26` | — | 0 | DEC_INDIRECT_A | M[A] = s16(M[A] - 1); no stack operand. |
| `27` | — | 0 | NOP | No operation; advance PC. |
| `28` | u16 | 0 | JUMP_REL | PC = u16(pc + s16(imm)). |
| `29` | u16 | 0 | JUMP_ABS | PC = u16(imm). |
| `2a` | u16 | -1 | BRANCH_NONZERO_POP | If pop() != 0, PC = u16(pc + s16(imm)). |
| `2b` | u16 | -1 | BRANCH_ZERO_POP | If pop() == 0, PC = u16(pc + s16(imm)). |
| `2c` | u16 | 0 | BRANCH_NONZERO_PEEK | If peek() != 0, PC = u16(pc + s16(imm)). |
| `2d` | u16 | 0 | BRANCH_ZERO_PEEK | If peek() == 0, PC = u16(pc + s16(imm)). |
| `2e` | u16 | -1 | BRANCH_EQ_A_POP | If pop() == A, PC = u16(pc + s16(imm)). |
| `2f` | — | 0 | NOP | No operation; advance PC. |
| `30` | — | 0 | NOP | No operation; advance PC. |
| `31` | — | 0 | NOP | No operation; advance PC. |
| `32` | — | 0 | PAUSE | PC = u16(pc + 1); status = 3; stop. |
| `33` | — | 0 | HALT | PC = pc (unchanged); status = 4; stop. |
| `34` | — | 0 | NOP | No operation; advance PC. |
| `35` | — | 0 | NOP | No operation; advance PC. |
| `36` | — | 0 | NOP | No operation; advance PC. |
| `37` | — | 0 | NOP | No operation; advance PC. |
| `38` | — | 0 | NOP | No operation; advance PC. |
| `39` | — | 0 | NOP | No operation; advance PC. |
| `3a` | — | 0 | NOP | No operation; advance PC. |
| `3b` | — | 0 | NOP | No operation; advance PC. |
| `3c` | — | 0 | NOP | No operation; advance PC. |
| `3d` | — | 0 | NOP | No operation; advance PC. |
| `3e` | — | -1 | STORE_KEEP | value = pop(); address = pop(); M[address] = value; push(value). |
| `3f` | — | 0 | DEREFERENCE | S[SP - 1] = M[peek()]. |
| `40` | u16 | +1 | LOAD_MEMORY | push(M[s16(imm)]). |
| `41` | u16 | +1 | LOAD_FRAME | push(M[s16(stack_base + FP + s16(imm))]). |
| `42` | — | +1 | SAVE_RETURN | push(pc + 1), the index of the following instruction. |
| `43` | — | -1 | RETURN | PC = u16(pop() + 1). |
| `44` | — | 0 | NOP | No operation; advance PC. |
| `45` | — | 0 | NOP | No operation; advance PC. |
| `46` | — | variable | SET_SP_FROM_TOP | SP = s16(peek()); no separate pop or memory erase. |
| `47` | — | 0 | NOP | No operation; advance PC. |
| `48` | — | +1 | PUSH_FP | push(FP). |
| `49` | — | 0 | NOP | No operation; advance PC. |
| `4a` | — | 0 | SET_FP | FP = SP. |
| `4b` | — | 0 | NOP | No operation; advance PC. |
| `4c` | — | 0 | NOP | No operation; advance PC. |
| `4d` | — | 0 | NOP | No operation; advance PC. |
| `4e` | — | 0 | NOP | No operation; advance PC. |
| `4f` | — | 0 | NOP | No operation; advance PC. |
| `50` | — | -1 | ADD | binary(left + right). |
| `51` | — | -1 | SUB | binary(left - right). |
| `52` | — | -1 | MUL | binary(left * right). |
| `53` | — | -1 | DIV | binary(trunc_toward_zero(left / right)); see section 5. |
| `54` | — | -1 | REM | binary(left - trunc_toward_zero(left / right) * right). |
| `55` | — | 0 | NOP | No operation; advance PC. |
| `56` | — | 0 | NOP | No operation; advance PC. |
| `57` | — | 0 | NOP | No operation; advance PC. |
| `58` | — | 0 | NOP | No operation; advance PC. |
| `59` | — | 0 | NOP | No operation; advance PC. |
| `5a` | — | +1 | PUSH_ZERO | push(0). |
| `5b` | — | +1 | PUSH_ONE | push(1). |
| `5c` | u16 | 0 | BRANCH_EQ_A_I8 | If A == lo8(imm), PC = u16(pc + hi8(imm)); both bytes unsigned. |
| `5d` | — | 0 | NOP | No operation; advance PC. |
| `5e` | — | 0 | NOP | No operation; advance PC. |
| `5f` | — | +1 | FRAME_ADDRESS_0 | push(stack_base + FP + 0). |
| `60` | — | +1 | FRAME_ADDRESS_1 | push(stack_base + FP + 1). |
| `61` | — | +1 | FRAME_ADDRESS_2 | push(stack_base + FP + 2). |
| `62` | — | +1 | FRAME_ADDRESS_3 | push(stack_base + FP + 3). |

## 5. Arithmetic and control flow details

All comparisons are signed. Arithmetic narrows after computing the result: `32767 + 1` becomes -32768; `-(-32768)` is -32768. There is no float type in this core. Boolean operations test zero versus nonzero and return 0/1, rather than preserving either input word.

Division truncates toward zero. Remainder is `left - quotient*right`, so its sign follows the numerator: `-7 / 3 = -2`, `-7 % 3 = -1`, and `7 % -3 = 1`. Division by zero is not assigned a valid result; the Python VM faults instead of depending on a native helper's platform behavior. Results are narrowed to 16 bits, including quotient overflow.

Relative branch offsets have signed 16-bit semantics with 16-bit wrapping. For example, `28 ff fd` at PC 10 jumps to PC 7, not to a byte offset or PC 8. Opcode `0x5c` is different: `5c 03 ff` compares A with **255** and advances three instructions on equality; it does not compare with -1 or use a signed displacement.

No implicit halt exists at EOF. Execution beyond the loaded code is invalid. Opcode `0x33` keeps its own PC, which matters for a saved stop location. The Python instruction budget is an external execution limit; it does not insert an opcode or silently complete a yield.

## 6. Calls, frames, and local storage

There is no single CALL opcode. Typical compiled calls combine `SAVE_RETURN` with a jump. If `0x42` executes at PC `p`, it pushes `p+1`, normally the jump instruction's index. `0x43` later pops that value and resumes at **p+2**.

A typical frame, after a caller pushes arguments and a return word and the callee executes `0x48; 0x4a`, is:

```text
lower stack indices
    arguments ...
    saved return index          # FP - 2
    caller's FP                 # FP - 1
FP: local 0                     # if allocated
    local 1 ...
higher stack indices
```

Allocate locals with `0x19` and a negative immediate, then initialize before reading. `0x41` loads frame-relative values; `0x23` and `0x5f`–`0x62` push their **addresses**, not the values. `LEAVE` restores the caller FP and sets SP just above the saved return word. `RETURN` then consumes that word; the caller may discard arguments separately. Return values in A or R are compiler/host conventions, not a universal CALL rule.

Example corresponding to the frame test (no game service needed):

| PC | Instruction | Effect |
| ---: | --- | --- |
| 0 | `PUSH_IMM 40` | One argument |
| 1 | `SAVE_RETURN` | Push 2 |
| 2 | `JUMP_ABS 7` | Enter callee |
| 3 | `DROP_1` | Caller removes its argument after return |
| 4 | `PUSH_A` | Use returned value 42 |
| 5 | `HALT` | Example caller ends |
| 6 | `NOP` | Padding in this example only |
| 7 | `PUSH_FP` | Save caller FP |
| 8 | `SET_FP` | FP now 3 |
| 9 | `LOAD_FRAME -3` | Load argument 40 |
| 10 | `PUSH_IMM 2` | Addend |
| 11 | `ADD` | 42 |
| 12 | `POP_A` | Return value in A |
| 13 | `LEAVE` | Restore FP=0, SP=2 |
| 14 | `RETURN` | Pop 2; PC becomes 3 |

This is one compiler convention supported by the primitives, not a mandatory frame shape for every program.

## 7. Yield / host-call ABI

A VM opcode and a host service ID are different namespaces. For example, opcode `0x1f` with immediate `0x0d03` invokes **service 13 with three arguments**. It is not opcode 13 and does not itself render dialogue.

### 7.1 Issuing a call

1. Evaluate arguments through real control flow and push them in argument order.
2. For `0x1f`, put the service ID in the immediate's high byte and count in its low byte. For `0x1e`, first put the count in R (often using `0x20`), then encode the full service ID as its operand.
3. The VM stores the service ID, advances PC by one instruction, sets status 1, and returns. It has not consumed arguments or pushed a result.
4. Dispatcher `FUN_0009fe3c` copies R to host field `+0x74` and sets R to -1. Its argument frame begins at `S[SP - count]`. Argument 1 is the oldest of those count words; argument `count` is the topmost.

Valid counts are nonnegative and cannot exceed the available stack frame. The native dispatcher does not comprehensively check arity or bounds. Its initial prefetch can read the next-free stack cell even for a zero-argument service; that does not create an argument.

### 7.2 Completion and pending input

For ordinary completion, the native epilogue sets `SP = SP - count`, writes the narrowed result to R, sets status 2, and clears pending flags `+0x84` / `+0x85`. Void services normally return 0. Subsequent opcode `0x21` pushes R if the script needs the result.

UI services may set `+0x84=1` and return with the argument frame intact. The C dispatcher uses a 32-bit sentinel `0x80000000` to distinguish no immediate result from a real result; this is **not** a VM word or branch result. Waiting occurs when the pending flag is set and there is no immediate result. Some cases return early after marking pending.

Asynchronous helper `FUN_0009e888` removes the saved argument count, sets R to the callback result, sets status 2, and clears wait flags. String-result callbacks can populate dynamic slot 0 and return `0x7ff5`. Exact choice indices, cancellations, minigame results, and callback-specific side effects belong to the individual service contract and remain partially unresolved.

Service 33 is a recovered zero-result callback: its raw-text message panel
requires 1000 ms of active reading time and subsequent acknowledgement,
preserves the argument frame while waiting, and leaves choice-result cells
unchanged. Its queued transition can consume the shared libc random stream.
See [message-panel contract](STORY_SERVICES.md#message-panel-service-33).

The Python API represents this boundary as `VMStop(kind='yield', yield_id, args, pc, byte_offset)`. Its stop PC is the issuing instruction; `vm.pc` has already advanced. Calling `run()` again returns the pending request. `resume(result)` explicitly completes it. The Python VM sets R=-1 when creating the request, combining the core-yield and dispatcher-entry stages above.

An unknown host service must remain pending or report unsupported in a faithful new implementation. Guessing zero can select the wrong branches. The inspected Android dispatcher has explicit default cases, but an iOS game may depend on a service absent from that Android build.

## 8. Packed strings and runtime references

### 8.1 Text in word memory

`FUN_0009f258` reads 16-bit words through `FUN_00055c88`, emitting the **high byte, then the low byte**, and stops at the first zero byte. A reference is a word address, not a string ordinal or byte offset. Strings can also be stored in initialized stack backing.

```text
M[20] = 0x4142
M[21] = 0x4300
reference 20 -> bytes 41 42 43 -> "ABC"
```

An even-length string needs a terminator in another word, commonly `0x0000`; an odd-length one can end in the low byte of its last word. Do not discard padding words or rebuild a global string list by splitting all program data at zero. Program data also contains non-text values, and references may point into existing strings.

The core string representation is a byte sequence, not UTF-16. The current Python host displays those bytes as Latin-1; a universal text encoding for all KiWi content has not been established. This differs from the verified **UTF-8 length-prefixed EXP metadata**. Native `FUN_00056b78` writes C-string bytes back into word memory in the same high/low order with zero termination; it does not allocate destination capacity.

### 8.2 Host text references

The string-argument resolver first interprets its argument as signed 16-bit:

| Reference | Interpretation |
| --- | --- |
| `-1` (`0xffff`) | Empty string |
| Other values below `0x7ff5` | Packed text at that word address; other negative values are not valid empty-string aliases |
| `0x7ff5 .. 0x7fff` | Runtime string slot `reference - 0x7ff5`, 11 slots total |

Native string objects occupy 12 bytes each beginning at host state `+0x94`. They are separate from VM word memory. A slot reference is resolved dynamically and can change meaning after another service updates that slot.

Some string-producing services accept a **negative destination selector**: `slot = ~selector`, so -1 selects slot 0, -2 selects slot 1, through -11 selecting slot 10. That argument-specific convention is not the meaning of an ordinary negative text reference. Service 47 returns the corresponding positive handle `0x7ff5 + slot`.

Text substitution is also a host operation. `FUN_0009f9fc` resolves text and applies the stored replacement mapping through `FUN_00096c9c`. `FUN_0009f420` performs raw reference resolution. Which variant a service calls matters; not every string is substituted automatically. The Python host adds cycle/iteration checks to repeated substitutions; those checks are implementation safeguards, not recovered wire semantics.

## 9. Script scheduling and persistence boundary

Service 10 records `(script_resource_id, flag)` through `FUN_0007b44c`. The engine's scene runner `FUN_0007f5f4` consumes scheduled scripts in **LIFO order after HALT**. Scheduling does not immediately jump within bytecode, and `0x33` alone does not identify a next scene. The flag affects native panel handling; rendering that effect is not implemented.

Services 7 and 63 are terminal scene exits. `0007e614` resets the scene's VM
hosts, clears the scheduled-script count and sets the exit flag at `+0x1b`;
`0007f5f4` does not load more queued scripts when it is set. The following
instruction in the current program does not execute. The compatible Session
retains the final call frame as a nonresumable audit record for its terminal
checkpoint, rather than serializing the discarded native VM's reset memory.
See [episode exit](STORY_SERVICES.md#episode-exit-services-7-and-63).

Game variables, character names/art, replacement strings, audio/UI state, and the schedule live outside the core data array. They survive ordinary scene changes in the current host model. A faithful port needs both VM and host state when saving a pending choice. The reimplementation now saves that modeled state in a versioned JSON format, including complete stack backing and a pending input frame; see [runtime save schema](RUNTIME.md#runtime-save-schema-version-13). Neither that format nor `load_next()` specifies the original native save-file format. Native serialization, missing host state, and full renderer/rollback behavior remain open.

## 10. Conformance examples and validation

### 10.1 Minimal halt

```text
6b 69 77 69 02 00 00 00 00 00 00 00 00 00 01 33
```

This is a standalone v2 script with no data and one instruction. HALT leaves PC=0, SP=0, FP=0, and status 4.

### 10.2 Host-call round trip

The following synthetic fixture uses service **254**, an arbitrary test host ID, not an established SHS service:

```text
6b 69 77 69 02 00 00 00 00 00 00 00 00 00 06
1a 00 07   # PC 0: push 7
1a ff fe   # PC 1: push -2
52         # PC 2: multiply -> -14
1f fe 01   # PC 3: service 254, one argument
21         # PC 4: push host result
33         # PC 5: halt
```

At the request: issuing PC=3, encoded byte offset=22, next PC=4, SP=1, arguments=(-14). Complete with result 5: SP becomes 0 and R=5. Running again pushes 5, then halts at PC=5 with stack `(5,)`.

### 10.3 Current verification and limits

[bytecode.py](../packages/formats/src/exp_runtime/decode/bytecode.py) round-trips all 987 corpus scripts exactly: 1,566,964 instructions and 56,761 static branch instructions. [vm.py](../packages/engine/src/exp_runtime/vm.py) implements the recovered core with explicit validation, and [engine.py](../packages/engine/src/exp_runtime/engine.py) implements the verified host subset. The legacy heuristic action parser remains in the research project and is not included here.

```sh
uv run --locked python -m unittest discover -s tests
uv run --locked shs-tool trace extract/assets/Assets/The_New_Girl.exp
uv run --locked python tools/audit_vm.py > docs/vm-corpus-audit.json
```

The core decoder/VM tests cover binary truncation and round trips, result-dependent branches, signed arithmetic, frame calls/returns, loops, memory, retained requests, and the bundled initialization fixture. The fixture test is skipped when local assets are absent. The two synthetic byte sequences above can be checked directly with `decode_program()` and `KiwiVM`.

The historical bounded corpus trace executed 501,556 instructions across 274 archives without a VM error or budget exhaustion: 37 stops at recognized presentations and 237 at unimplemented services. These runs stop before unresolved operations; they do not validate complete episodes or demonstrate equivalence to a live native playthrough. See [VM_EXECUTION.md](VM_EXECUTION.md) and `vm-corpus-audit.json`.

| Area | Defined / implemented | Remaining limit |
| --- | --- | --- |
| v2 binary layout | Exact standalone decoding and round trips | Linked lifecycle and legacy versions unverified |
| Core opcodes `00`–`62` | Complete table and executor | Native undefined memory/error behavior is not emulated |
| Yield argument/result boundary | Verified and implemented | Individual callbacks and many host services unresolved |
| Strings | Packed bytes and dynamic slot addresses verified | Full multilingual KiWi text/rendering behavior unverified |
| Scenes | LIFO scheduling and reset modeled | Full native saves and resource-bank lifecycle unresolved |
| Gameplay | Desktop dialogue, choices, mini games, callbacks and saved sessions | Complete episode playback and full native presentation fidelity remain unverified |
