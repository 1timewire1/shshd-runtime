# Project provenance and evidence

SHS Runtime was separated from the `exp-decoder-python` research project on
2026-09-13. It retains the compatible engine, original-format readers, authored
tests, build tools and specifications developed there. The inherited MIT
license and Josh Mcdaniel's copyright notice remain in [LICENSE](../LICENSE).

The project is now EXP Runtime, with package `exp_runtime` and `exp-runtime` /
`exp-tool` entry points. `shs` and `shs-tool` remain compatibility aliases.
The original checkout retains the older heuristic AST parser, Ren'Py
exporter, conversion attempts, local assets and raw native research output.
This project has no dependency on that directory or its Python environment.

This is a compatible engine with a KiWi bytecode interpreter. It does not
recompile or execute the original ARM game executable. The fidelity target is
the reported identical original iOS/Android interface; Android 1.0.9 provides
the available native code and asset reference. Unknown platform differences
remain explicit rather than being assumed equivalent.

Cause of Death uses its own supplied iOS executable as the reference for
game-specific contracts; see [COD.md](COD.md). Its native decompilations and
original assets also remain private research inputs.

The [kiwi fruit app logo](../packages/player/src/exp_runtime/assets/kiwi.svg) was drawn for
EXP Runtime and is covered by this project's MIT license. It is independent
of the original games' artwork. Native app icons are generated from this SVG.

RAR import calls [libarchive](https://github.com/libarchive/libarchive), a
separate BSD-licensed archive decoder. Apple platforms use the OS library.
Windows/Linux desktop builds use the pinned upstream **3.8.9** release from
`tools/build_rar.py`; build output includes its COPYING text and individual
source copyright/license headers. Decoder sources/binaries remain in ignored
build output and are not copied into the authored source package. Tests
construct their own stored RAR4/RAR5 bytes; no original game archive is bundled.

## Evidence notes

Native function addresses in the specifications refer to `libshs09.so` with
SHA-256:

```text
b17aa4c71bc46666d414cafae6fac92bbcd755f3dcccd73975cf05f4a119665b
```

The Android music-cue rules additionally come from
`com.eamobile.shs_na_wf.SHS09SoundEngine.playMusic` in the supplied APK's
`classes.dex`, SHA-256:

```text
8e5bdc26784153301f473db9103d00b5f950943743252d99a779852fc5be66a9
```

Only the recovered ID/offset contract and compatible implementation are
included; Java/Dalvik disassembly stays in private research files.

The speaker-label rules were checked against `FUN_000a7fa8`, `FUN_000a8544`,
`FUN_0004dc20` and font initialization/lifetime code in the same native binary.
[UI_FIDELITY.md](UI_FIDELITY.md#speaker-labels-and-persistent-font-state)
separates those recovered rules from the runtime's additional glyph-bounds
correction. Non-overlap checks are not evidence of exact original rendering.

Episode/week title screens were recovered from `FUN_000a70b4`, `FUN_000a650c`,
`FUN_000a65b4`, `FUN_000a6800` and the external glyph-font routines in the same
binary. [TITLE_SCREENS.md](TITLE_SCREENS.md) records the original resources,
coordinates, animation/input gates, callback and remaining comparison limits.

Names such as `native-kiwi-vm.c`, `native-exp-loader.c` and
`new-girl-start-trace.json` identify private evidence snapshots in the original
research checkout. The raw decompilations and generated traces are deliberately
not copied into this project. References to them are descriptive, not links
to required source files. The specifications preserve the native addresses,
schemas, observations, known ambiguities and implementation limits needed to
continue the work using a user-supplied binary.

Historical corpus counts describe the inputs and coverage of particular
research runs. They are not release guarantees or evidence that all episodes
finish successfully. The audit tools can generate new reports from a player's
own inputs. Keep those reports local because they may contain original game
text and machine-specific paths.

The project contains no original APK, episode archive, native executable,
image/font/audio asset, original screenshot, imported library or player save.
Users supply those inputs separately as described in [DISTRIBUTION.md](DISTRIBUTION.md).
