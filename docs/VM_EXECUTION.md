# VM execution and diagnostics

The consolidated contracts are in [VM_SPEC.md](VM_SPEC.md) and
[ENGINE_ABI.md](ENGINE_ABI.md); the archive format is in
[SCHEMA.md](SCHEMA.md). [RUNTIME.md](RUNTIME.md) covers the desktop player,
callbacks, clocks, local libraries and saved sessions.

The runtime executes actual KiWi control flow and host services. It does not
use the research project's heuristic action parser or Ren'Py exporter.

## Reproduce

```sh
uv run --locked --extra desktop python -m unittest discover -s tests
uv run --locked shs-tool trace /path/to/episode.exp
uv run --locked python tools/audit_vm.py /path/to/Episodes
```

`trace` reads the archive with the same strict `content.ExpArchive` reader
used by the runtime. It uses a fresh, empty engine state and stops at the first
pending presentation or unsupported service. Instruction and event budgets
bound execution. It does not answer an unknown handler or invent a result.
Trace JSON includes the archive hash, pending arguments, engine state and
recent program counters. Keep generated traces local: they may contain game
text and player data.

## Verified state model

| Native state offset | Python state | Evidence |
| --- | --- | --- |
| +0x30 | instruction-index PC | FUN_00055ce0 |
| +0x32 | stack pointer | FUN_00055ce0 |
| +0x34 | frame pointer | FUN_00055ce0 |
| +0x36 | argument count / result register | FUN_0009fe3c, FUN_0009e888 |
| +0x38, +0x3a | registers A, B | FUN_00055ce0 |
| +0x3c | stack virtual-address base | FUN_00056f1c |
| +0x40 | stack capacity | FUN_00056f1c |
| +0x44 | stack backing array | FUN_00055ce0 |
| +0x74 | pending argument count | FUN_0009fe3c |

`FUN_0009ef60` allocates 0x400 stack words through `FUN_00056f1c`, which
sets the stack address base to `0x7ff5 - capacity = 0x7bf5`. The base is
not the script data length. Stack words remain addressable after pops.

The implementation covers the observed interpreter's arithmetic, signed
comparisons, 16-bit overflow, register operations, direct/indirect memory
access, branches, frames, calls/returns, yields, pauses, and halt. Division
truncates toward zero; remainder has the numerator's sign. Return opcode
0x43 jumps to the popped value plus one: 0x42 saves the following jump
instruction's index, not the eventual continuation's index.

Reset `FUN_00055c6c` clears PC/SP/FP. It does not initialize registers A/B,
the result register, data gaps, or stack memory. Python marks those cells
unknown until written and raises on an uninitialized read. Bounds faults,
division by zero, and opcodes above the verified range also raise, instead
of reproducing native undefined behavior. Break-only opcodes in the native
switch are explicitly represented as no-ops.

Linked segments run beside a script (`KiwiVM(linked=...)`, `vm.linked_layout`);
New Rules' minigame library is the one in use ([VM_SPEC.md](VM_SPEC.md#23-linked-segments)).
None of the 987 audited SHS scripts sets that flag.

## Pending actions

`KiwiVM.run()` returns a `VMStop` at a yield, retaining its argument frame.
Calling it again returns that same request without executing more code.
`resume(result)` removes exactly that frame and sets the result register.
The script must execute opcode 0x21 to push the result. This matches both
the dispatcher epilogue and UI completion helper `FUN_0009e888`.

Opcode 0x32 produces an explicit pause, continued with
`continue_after_pause()`. Opcode 0x33 halts without incrementing PC.
Instruction-budget exhaustion leaves the machine resumable.

`load_next(program)` requires a halted VM, reloads data, resets PC/SP/FP,
and preserves the registers and stack backing. The external engine state
survives scene changes. This follows reset + loader behavior; it is not
an implementation of native saved-game deserialization.

## Host services and scheduling

[ENGINE_ABI.md](ENGINE_ABI.md) records the current service inventory and known
callback contracts. [RUNTIME.md](RUNTIME.md) describes rendering, asset banks,
saved state and the implemented dialogue/mini-game lifecycle. The headless
trace does not render panels, advance timed UI or play through callbacks.

The native numeric property key is `owner * 65536 + property`, with signed
short arguments, wrapped to 32 bits. Scheduled scenes use LIFO order:
`FUN_0007f5f4` decrements its count and loads the last scheduled script after a
VM halt. The scheduling flag is preserved even in a headless trace.

## Historical corpus evidence

The initial research trace of the APK-bundled New Girl executed 2,561
instructions and retained a four-argument service-8 frame at scene 25002,
next PC 165. It initialized 33 character records through actual calls and
loops, with one LIFO scene load. The original-content regression test can
repeat that check when the player's local fixture is available.

An earlier bounded fresh-state audit ran 501,556 instructions across 274
archives with no VM error or budget exhaustion: 37 presentations and 237
stops at then-unimplemented services. Those counts predate subsequent host
handlers and do not establish complete episode playback. Native addresses and
private snapshot names are explained in [PROVENANCE.md](PROVENANCE.md).
