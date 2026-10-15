# EXP Runtime

This is an experimental compatible engine for Surviving High School and Cause
of Death. Users supply SHS Android 1.0.9 APK / SHS IPA or CoD IPA assets and
additional EXP episodes. `exp_runtime` executes
original KiWi bytecode and renders user-supplied resources. It is not a static
ARM recompilation or a Ren'Py conversion.

## Build and verify

```sh
uv sync --locked --extra desktop
uv run --locked --extra desktop python -m unittest discover -s tests
uv run --locked --extra desktop exp-runtime
uv run --locked --extra build python tools/build_desktop.py
```

Tests use authored fixtures. Optional original-content checks skip when a
player's local content is absent. Do not add original assets as test fixtures.

## Architecture and contracts

One uv workspace produces the `exp-runtime` umbrella and six component wheels.
Source lives under `packages/{formats,engine,player,shs,cod,creator}/src/exp_runtime`.
Keep the shared `exp_runtime` namespace free of a root `__init__.py`, and give
each source file one wheel owner. `tools/build_packages.py` audits the wheels;
`tools/test_packages.py` checks isolated pip installs. See docs/SDK.md.

- `shs/`, `cod/`: game-specific import, asset/audio bindings and host services.
- `content.py`: validated EXP/APK/IPA import, exact resource IDs, relocatable
  per-game libraries and separation of base versus episode resource banks.
- `decode/bytecode.py`, `vm.py`: lossless KiWi representation and real VM
  execution, including pending argument frames and callbacks.
- `engine.py`, `runtime.py`: host services, panel state, clocks, choices,
  mini games and versioned JSON saves.
- `application.py`, `desktop*.py`: shared launcher, menu, rendering and input.
- `graphics.py`, `platforms/`, `ios/`: pygame/native drawing primitives and the
  Swift iOS host; keep game layout and behavior in the shared Python code.
- `fonts.py`, `ui_assets.py`, `atlas.py`: native asset and layout contracts.
- `creator/`: optional desktop story graph, portable authoring documents and
  native EXP compiler; preview reuses the player with temporary saves. Keep
  creator/Qt out of ordinary player and iOS bundles.

Follow SCHEMA.md, VM_SPEC.md and docs/ENGINE_ABI.md. Unknown services must
remain explicit stops with their pending arguments intact. Never invent a
score, result, scene link or random value to bypass them. The heuristic AST
parser and Ren'Py experiments belong to the original research project.

Preserve the 1:1 target: original positions, font metrics, portrait masking,
pagination, panel lifecycle, input gates, timers, randomness and script-visible
side effects. Recover behavior and presentation together. Use Android 1.0.9
as the available reference for the reported identical iOS/Android interface.
The owner selected v0.1.3's SHS skin as the common presentation reference,
then supplied original screenshots and requested native verification of the
general title fix. Keep a common dialogue renderer; adapters supply each
game’s assets and native font metrics. Do not introduce a separate IPA layout.
The owner subsequently selected the verified iOS dialogue-box opening
animation for both games/platforms (120 ms travel, then 200 ms expansion).
This overrides Android's immediate box display; retain the common final
geometry. See docs/UI_FIDELITY.md for recovered paths and remaining limits.
Ghidra confirms that both iOS games wrap names at the native region width,
select a normal/tall header, and keep ordinary body text in its own region.
Honor those outline-font rules and Android's distinct bitmap-label rules.
Long titles may straddle the box border: do not force every name wholly above
it into the normal-height header. Bound fallback ink against the selected
header, skin, body and portrait; keep the drawing fit separate from saved
font history. Resolve text colors per game. See docs/IPA.md for evidence.
For other CoD-specific differences use its
supplied iOS native reference and docs/COD.md.
Keep unverified details explicit in the specifications.

Do not bundle APKs, EXPs, extracted art/audio/fonts/scripts, native
decompilations, screenshots, generated games, player libraries or saves.
Keep MANIFEST.in and package discovery restrictive. Preserve the inherited
MIT license and attribution in docs/PROVENANCE.md.

The owner handles Git initialization, commits, remotes and pushes. Creating
this directory does not authorize publishing it.
