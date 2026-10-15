# SHSHD Runtime Python components

SHSHD Runtime keeps upstream exp-runtime's component layout (from its v0.5.0): five component wheels
plus a small `shshd-runtime` umbrella wheel. All components use the same `exp_runtime` import namespace
as upstream; they remain one project, repository, version and uv workspace. No game behavior or
renderer is copied between packages. Do not install upstream's `exp-runtime` distributions into the
same environment: both fill that one namespace.

## Choose an install

This fork does not publish to PyPI. Each version-tag release attaches all six wheels (with SHA-256
checksums) to its GitHub release; download them into one folder (`./wheels` below) and select the parts
you need:

| pip requirement | Installed functionality |
| --- | --- |
| `shshd-runtime` or `shshd-runtime[tools]` | EXP reader, KiWi decoder, native resource parsers and file CLI; no engine, games, Pillow or Pygame |
| `shshd-runtime[engine]` | File tools plus VM, sessions, libraries and common layout; no game adapters or graphics dependencies |
| `shshd-runtime[engine,shs]` | Headless engine with SHS and font support; no CoD or shared player |
| `shshd-runtime[engine,cod]` | Headless engine with CoD and font support; no SHS or shared player |
| `shshd-runtime[engine,shs,cod]` | Headless engine with both games |
| `shshd-runtime[player]` | Desktop player with both games by default |
| `shshd-runtime[desktop]` | Compatibility alias for the full desktop player install |

For example:

```sh
python -m pip install --find-links ./wheels 'shshd-runtime[engine,cod]==1.0.0'
```

Pip uses standard wheel metadata; it does not need uv or workspace support.
`shs` and `cod` extras each pull in the engine automatically. Game assets still
come from the user, and import/save formats remain unchanged.

The umbrella's bare install supplies file tools; app users choose `[player]` or `[desktop]`.
`shshd-tool` (with the aliases `exp-tool` and `shs-tool`) belongs to the formats wheel; `shshd-runtime`
(with the aliases `exp-runtime` and `shs`) belongs to the player wheel.

The independently installable distributions are `shshd-runtime-formats`,
`shshd-runtime-engine`, `shshd-runtime-player`, `shshd-runtime-shs` and
`shshd-runtime-cod`. For a desktop player containing just CoD:

```sh
python -m pip install --find-links ./wheels 'shshd-runtime-player[desktop]==1.0.0' 'shshd-runtime-cod==1.0.0'
```

The launcher lists installed game adapters. Calling an uninstalled game's
services fails with an install hint. The engine alone can execute the generic
KiWi VM; a `Session` needs the adapter for its selected game. Installing both
games never mixes their resource banks.

Pillow is an optional `fonts` dependency of the engine, included by game
adapters and the player to preserve native font metrics. The formats wheel's
`images` extra supplies Pillow for portrait resampling; its ordinary resource
parsers remain usable without it. Pygame is only a `desktop` dependency of the
player. The shared iOS player uses the same Python modules with a native host.

## Build local wheels before publication

No package publication is performed by these tools. From this checkout:

```sh
uv run --locked --extra build python tools/build_packages.py
uv run --locked --extra build python tools/test_packages.py
```

The build writes six wheels, six source archives and SHA-256 checksums to
`dist/packages/`. It rebuilds each wheel from its source archive and audits the
file ownership, source bytes, versions and content exclusions. The test creates
fresh virtual environments and uses real pip resolution outside the checkout,
including single-game and tools-only installs. It downloads the locked Pillow
and Pygame wheels once into `build/package-test-dependencies/`; `--offline`
reuses that cache. It does not read original game content.

Test your own project against the local wheels:

```sh
python -m venv /tmp/my-exp-project
/tmp/my-exp-project/bin/python -m pip install --no-index --find-links dist/packages 'shshd-runtime[tools]'
```

For a game/player install, omit `--no-index` to obtain third-party dependencies,
or also pass `--find-links build/package-test-dependencies` after running the
test tool. On Windows use the virtual environment's `Scripts/python.exe`.
Keep all six wheels together so pip can resolve the selected components.
Components are pinned to the same release version; mixing versions is rejected
by the dependency resolver. Plain index installs never find these builds:
the fork's distributions are not on PyPI.

## Read and extract an EXP

```python
from pathlib import Path
from exp_runtime.formats import ExpArchive, decode_program

archive = ExpArchive(Path('episode.exp').read_bytes())
print(archive.metadata().titles)       # Five original localized title fields.
print(sorted(archive.entries))        # Exact original resource IDs.
script = archive.read(25001)          # Decompresses and validates this record.
program = decode_program(script)
assert program.to_bytes() == script   # Lossless bytecode representation.
```

`archive.read(id)` returns original decoded bytes. The tools do not infer a
game from an EXP or substitute another resource ID. `archive.programs()`
returns all KiWi programs indexed by resource ID. Malformed content raises
`ContentError`; invalid bytecode raises `KiwiFormatError`.

```sh
shshd-tool inspect episode.exp
shshd-tool extract episode.exp --output extracted-resources
```

Extraction creates a new directory of `<resource-id>.bin` files. It refuses
to overwrite an existing output directory and leaves no partial extraction if
a record is invalid. These commands work with only the formats wheel installed.

`exp_runtime.formats` also exports `ImagePack`, `LayoutBank`, `SpriteAtlas`,
`AtlasFont`, `BitmapFont`, `MenuFont` and `MenuStrings`. Use each parser's
`parse(bytes)` method to inspect original resource structures in an editor.
Bytecode has lossless serialization; the API does **not** yet provide a general
EXP container writer or a complete visual editor. Editors must preserve the
contracts in [SCHEMA.md](SCHEMA.md) and [VM_SPEC.md](VM_SPEC.md).

## Drive the engine from your own UI

Import an APK/IPA and additional episodes through the existing CLI or
`exp_runtime.content.import_game`. Then use the selected library as the
session's resource provider:

```python
from pathlib import Path
from exp_runtime.content import ContentLibrary
from exp_runtime.runtime import Session

with ContentLibrary(Path('my-cod-library')) as library:
    resources = library.open_episode('Volume One')  # ID, unique title or filename.
    session = Session(resources)
    action = session.advance()
    print(action.name, action.details)
    # Store session and keep the library open for your UI's lifetime.
```

Your UI reads `session.pending`, `session.engine` and `session.dialogue_page()`.
Call `session.tick(elapsed_ms)` while the story is active and unpaused; submit
real input using `session.answer(value)`. Choice values are visible option
indices, and dialogue acknowledgment must follow the session's reveal gates.
The pending action after either call tells the UI what to show next. Audio
cues remain in engine state for your host to play. No Pygame window or audio
device is initialized by these APIs.

Use `session.save(path)` and `Session.load(resources, path)` for atomic,
content-bound JSON saves. `snapshot()` and `from_snapshot()` offer the same
validated state for a custom storage host. Existing saves remain readable:
serialized state contains content identities and values, not wheel paths.
Only the selected adapter can restore its game-specific dataclasses.

Keep unsupported services pending with their arguments intact. Do not resume
them with a guessed result. See [RUNTIME.md](RUNTIME.md),
[ENGINE_ABI.md](ENGINE_ABI.md) and [VM_EXECUTION.md](VM_EXECUTION.md) for input,
timer, callback and resource contracts. For a VM without game host services,
use `exp_runtime.vm.KiwiVM` with a decoded `KiwiProgram` directly.

## Source organization

Each `packages/<component>/src/exp_runtime/` directory owns only that wheel's
source. `exp_runtime` is a PEP 420 namespace: do not add a shared
`__init__.py`. Existing module paths such as `exp_runtime.runtime` and
`exp_runtime.shs` are retained. `content.ExpArchive`, `content.Metadata` and
`content.ContentError` remain aliases when the engine is installed; tools-only
clients should import them from `exp_runtime.formats`.

`uv sync --locked --extra desktop` and existing build commands continue to
work. The default development group includes all components for contributors.
Use `--no-default-groups` with selected extras for a minimal source environment;
the isolated pip checks are the authoritative check of published dependencies.
Both app builders assemble this same component set. Version checks and wheel
audits reject a mismatched release or overlapping files.
