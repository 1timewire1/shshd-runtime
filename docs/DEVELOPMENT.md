# Development

See [MAINTAINERS.md](../MAINTAINERS.md) for contributor setup, reporting issues,
compatibility requirements and pull request guidance.

The project is a single uv workspace with component source under
`packages/{formats,engine,player,shs,cod,creator}/src/exp_runtime`. It does not import
modules from the old decoder checkout or require any extracted game files
to install, test its synthetic fixtures, or build an executable.

The `exp_runtime` namespace and existing module imports are preserved. See
[SDK.md](SDK.md) for wheel ownership, optional pip installs and custom UI APIs.
The default development environment includes both games and the player;
minimal installs are verified independently with `tools/test_packages.py`.

## Environment and commands

Use Python 3.10 or newer. From the project directory:

```sh
uv sync --locked --extra desktop
uv run --locked --extra desktop python -m unittest discover -s tests
uv run --locked --extra desktop exp-runtime
uv run --locked --extra build python tools/build_desktop.py
uv run --locked --extra build python tools/package_desktop.py --label local --smoke-test
```

For creator and MCP development, including the live editing tests:

```sh
uv sync --locked --extra build --extra creator --extra creator-mcp
uv run --locked --extra build --extra creator --extra creator-mcp python -m unittest discover -s tests
uv run --locked --extra creator exp-creator
uv run --locked --extra creator-mcp exp-creator-mcp --workspace /path/to/stories
```

`exp-tool` provides `import`, `list`, `play` and `trace`. It can also be invoked
with `python -m exp_runtime`. The desktop entry point is `exp-runtime`, or
`python -m exp_runtime.application`.

```sh
uv run --locked exp-tool import --apk /path/to/game.apk --episodes /path/to/Episodes --library /path/to/library
uv run --locked exp-tool list --library /path/to/library
uv run --locked --extra desktop exp-tool play --library /path/to/library --episode "The New Girl"
uv run --locked exp-tool trace /path/to/episode.exp
```

The desktop menu supports adding further episodes to an existing library.
CLI `import` creates a new library and refuses to overwrite an existing one.
`trace` starts an empty engine state and stops at a pending action; it is a
bounded diagnostic, not an automated episode playthrough.

## Architecture

| Layer | Modules |
| --- | --- |
| Content and local import | `content`, `shs.content`, `shs.builtin_episode`, `cod.content`, `episode_catalog` |
| RAR episode decoding | `rar` (OS libarchive on Apple, bundled decoder in Windows/Linux builds) |
| KiWi decoding and execution | `decode.bytecode`, `vm`, `trace` |
| Host services and saved sessions | `engine`, `runtime`, `shs.services`, `cod.services` |
| Dialogue, choices and panel clocks | `dialogue`, `choice`, `dialogue_animation`, `relationships`, `loading` |
| Optional choice previews | `choice_hints` (bounded copies; no live state, save or host side effects) |
| Mini games and random streams | `minigames`, `randomness`, `shs.word_grid`, `shs.football` |
| Native formats and geometry | `fonts`, `ui_assets`, `atlas`, `menu` |
| Desktop application | `launcher`, `application`, `desktop`, `desktop_*`, `shs.desktop_*` |
| Game bindings | `games`, `shs.profile`, `shs.ios_assets`, `cod.profile`, `cod.assets`, each game's `audio` |

The engine/session state owns script-visible behavior. Rendering must not
silently answer callbacks or change game results. Preserve pending frames,
timer clocks and random streams across save/load, pause and scene changes.
Unknown services remain explicit diagnostic stops.

## Tests and private content

See [Running unit tests](../MAINTAINERS.md#running-unit-tests) for full-suite,
single-file and individual-test commands, filtering options and expected skips.

The default test command works without any game files. For optional checks,
follow [Testing with your own game files](../MAINTAINERS.md#testing-with-your-own-game-files):
place your APK at `surviving-high-school-1-0-9.apk` in the repository root and
import it into `.shs-library`. That guide also lists episode-specific inputs
and the optional `extract/assets/Assets/The_New_Girl.exp` fixture. The tests do
not search the desktop app's application-data directory. These local paths
are ignored by Git and never packaged. Do not commit originals as fixtures.

Corpus tools accept user-supplied paths:

```sh
uv run --locked python tools/audit_format.py /path/to/Episodes
uv run --locked python tools/audit_vm.py /path/to/Episodes
uv run --locked python tools/audit_runtime.py --library /path/to/library
uv run --locked python tools/audit_ui_assets.py /path/to/game.apk
```

Treat generated JSON as local evidence; traces can include original dialogue
and player data. The specifications distinguish native contracts, historical
corpus observations and unverified behavior. A passing synthetic test suite
does not establish complete episode playback or pixel/timing equivalence.

## Migration from the research project

| Research project | Standalone project |
| --- | --- |
| `src/exp_file` Python package | `exp_runtime` namespace across `packages/*/src` |
| `exp-file` command | `exp-tool` |
| `shs` desktop launcher | `exp-runtime` (`shs` alias retained) |
| Heuristic AST/Ren'Py conversion | Retained only in the old research project |
| Legacy extraction used by `trace` | Strict `content.ExpArchive` reader |

Save JSON and library schemas do not contain Python module paths; their
resource IDs and content hashes remain unchanged by the rename. New imports
use the game-aware `exp-content-library` v1 schema; legacy SHS v1–3 manifests
remain readable. Save version 15 accepts both the `shs-runtime-save` and
`exp-runtime-save` format markers. Existing SHS save filenames are retained.
Older IPA dialogue checkpoints reflow at their saved read offset for the
shared v0.1.3 dialogue layout, without executing the pending VM call.
The `EXP Runtime` launcher reads old `SHS Runtime` library locations, then
remembers each game's location separately. See [MAIN_MENU.md](MAIN_MENU.md).

Keep game-specific assets, imports and behavior in `exp_runtime/shs/` or
`exp_runtime/cod/`. Shared code must resolve a resource only in the selected
library, never search all games for a matching numeric ID. Both games use
v0.1.3's SHS dialogue layout and renderer; adapt resource/font loading rather
than selecting a separate layout by package type. Optional CoD
integration tests read `decomp/cod/Cause+of+Death+(World)+1.3.4.ipa` into a
temporary library; no proprietary fixtures are checked in.
There is no need to move or reimport that content.

### Migration verification, 2026-09-13

The standalone project was installed into a fresh environment with its locked
dependencies on macOS arm64, using Python 3.14.7. The suite reported 142 tests:
114 passed and 28 optional original-content checks skipped. Additional checks
opened the existing 272-episode research library, loaded and round-tripped its
seven saved sessions, and rendered its menu, 28 episode groups and a saved
episode using the renamed package. Original manifest, preferences and save
hashes were unchanged.

The macOS app built from the standalone source. SDL dummy-driver smoke checks
covered both empty-library setup and an existing-library menu from an unrelated
working directory. Source and wheel archives were inspected for the intended
package, required docs/tools/tests, and exclusion of original game files and
legacy conversion code. These migration checks do not add Windows/Linux or
full original-game visual-equivalence coverage.
