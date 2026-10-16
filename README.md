# EXP Runtime

An experimental compatible engine for **Surviving High School** and **Cause of Death**, aiming to
reproduce the original interface and gameplay. It executes the original KiWi
scripts and reads graphics, fonts, audio and episode data from files supplied
by each player.

Choose a game in the launcher, then supply its assets: an **SHS Android 1.0.9 APK**,
**SHS IPA**, or **Cause of Death IPA**, plus any additional **EXP episodes**
for that game. The importer reads those
files locally. Game content is not included in this project or downloaded by it.
IPA import checks the game's bundle identifier and required assets; its version
number is informational. See [SHS IPA support](docs/IPA.md) and
[Cause of Death support](docs/COD.md) for details.

## Download an app

Open this repository's **Releases** page and download the archive for your
system: `windows-x64`, `linux-x64`, `macos-arm64` (Apple Silicon), or
`macos-x64` (Intel). Extract it and open the app inside. Keep the complete app
or executable folder together. Python and the runtime dependencies are bundled.

To make episodes, download `exp-runtime-creator-v0.6.1-<target>.zip` (or
`.tar.gz` for Linux) and open **EXP Runtime Creator**. The Creator has separate
downloads for the same four desktop targets. See [the creator guide](docs/CREATOR.md).

For development builds, open **Actions → Builds**, choose a successful
run, and download its platform artifact. Extract the artifact ZIP, then the
app archive inside it.

Builds include a SHA-256 checksum. macOS builds use ad-hoc signing and are not
notarized; Windows builds are unsigned. See [distribution](docs/DISTRIBUTION.md)
for CI triggers, packaging and the first-launch requirements.

The [iPhone/iPad app](docs/IOS_APP.md) shares the Python engine, menus and
renderers with desktop, using native iOS drawing, audio and Files access.
Download `exp-runtime-<tag>-ios-arm64-unsigned.ipa` and its checksum from the
release files, then sign and install the IPA. Development runs provide the same
format in the `ios-arm64-unsigned` Actions artifact. The Xcode project also
supports running directly on your device.

## Build your own app

Install Git and uv, clone this project, then run from the project's directory:

```sh
uv sync --locked --extra build
uv run --locked --extra build python tools/build_desktop.py
```

No game files are needed during the build. Python 3.10 or newer is required;
uv prepares the local environment and installs the locked dependencies.

| Platform | App to open |
| --- | --- |
| macOS | `dist/desktop/EXP Runtime.app` |
| Windows | `dist/desktop/EXP Runtime/EXP Runtime.exe` |
| Linux | `dist/desktop/EXP Runtime/EXP Runtime` |

Build on the operating system where you will play. Keep the whole app or
executable directory together: it includes Python and its dependencies.
CI builds and checks all four targets. Local verification has covered macOS
on Apple Silicon; a successful CI run checks the other platforms' startup,
but full gameplay still needs testing on each system.

You can also run directly from source:

```sh
uv run --locked --extra desktop exp-runtime
```

## Add your game files

1. Launch the app, select **Surviving High School** or **Cause of Death**, then
   choose that game's APK/IPA or open its existing library.
2. Add EXP files, ZIP/RAR collections or a folder through Options, or drag them onto the
   menu. SHS's bundled stories, including Football Star, or CoD's Volume One
   are imported automatically.
3. Select an episode in Play/Resume. Imported episodes and progress persist
   when you close the app.

Use **Switch Game** to open the other installed game, or the chooser when it
has not been imported. Each game has its own
library, preferences and saves. Shared asset IDs never pull artwork from the
other game. EXP files do not reliably identify their game, so add them to the
correct selected library.

For an SHS IPA, you can optionally supply your Android 1.0.9 APK through **Options →
Content Library → Add APK Music** to restore music the iOS app downloaded
separately. IPA artwork and installed original fonts keep priority, and your
IPA saves remain compatible. See [IPA import](docs/IPA.md#optional-apk-music)
for command-line options and supported assets.

**Options → Episode title language** selects English, French, Italian, German
or Spanish names where the EXP includes them. Story text remains in the
language supplied by each episode; the inspected APK/IPA contain English
stories, not five dialogue translations. Existing progress stays compatible.

**Options → Cheats → Choice hints** optionally marks recognized near-term
score/relationship gains or correct quiz answers green, losses/wrong answers
or no-gain alternatives red, and mixed effects amber. Unknown or later
consequences stay unmarked. It is off by default.

EXP Runtime checks GitHub for a newer release once per launch. **Options →
Update checks** turns this off for both games; Options is also available on
the game chooser. When “Update available. Download here.” appears, **Yes**
opens the release page in your browser and **No** dismisses it for this launch.
The check runs in the background and does not interrupt a story. Downloads
and installation remain manual, including signing an iOS IPA.

ZIP and RAR collections can be imported directly, including EXPs in subfolders and
the selected game's catalog. Imported episodes remain in the app's library;
the archive is not needed afterward. RAR imports use the OS decoder on Apple
platforms and a bundled decoder in Windows/Linux downloads. Source users need
libarchive; see [archive import](docs/RUNTIME.md#episode-archives).
You can also import an extracted folder:

> Store the episodes within a folder
>
> Example:
>
> ```
> Episodes/
>     Episode1.exp
>     Episode2.exp
>     ...
> ```

If your episode folder includes the original `shs_options.sav` (SHS) or
`cod_options.sav` (CoD), its catalog supplies the original season, volume and
story groups. You can also add that file separately through **Add Episodes**
or drag-and-drop. Reimporting the folder updates these names without adding
duplicate copies of identical EXPs or resetting progress. Episodes absent from
the supplied catalog keep numeric pack names.
This works for existing libraries too, including SHS libraries imported from
either an APK or an IPA; both use the same `shs_options.sav` catalog.

Existing libraries from `exp-decoder-python` still work: choose **Open Library**
and select the existing library directory. It can stay outside this project.
Existing Android content identities and saves are preserved. IPA libraries
use a separate source profile and installed fonts, falling back to the system
default when an original face is absent. See [runtime setup](docs/RUNTIME.md)
for paths, controls, formats and command-line import.

The Python package is now `exp_runtime`; the primary commands are `exp-runtime`
and `exp-tool`. The `shs` and `shs-tool` commands remain as compatibility aliases.
The launcher discovers old SHS library locations without moving player files.

For example, import CoD into a separate library and open it directly:

```sh
uv run --locked exp-tool import --game cod --ipa /path/to/CoD.ipa --episodes /path/to/CoD-Episodes --library /path/to/cod-library
uv run --locked --extra desktop exp-runtime --game cod --library /path/to/cod-library
```

## Current state

The runtime implements the main menu, persistent episode library, grouped
episode browser, dialogue animation, portrait masks, choices, character
selection, relationship indicators, episode/week intros, loading screens, word/grid/football mini
games and save/load. F5 saves, F9 loads, and returning to the menu creates an
automatic checkpoint. Tap once to reveal dialogue, then again to advance it.

The New Girl opening and Football Star opening through its first football
game have been exercised. Complete episode playback and full 1:1 visual/timing
equivalence are still being verified. Unsupported services stop explicitly
with their scene, service and program counter. Current limits are recorded in
[RUNTIME.md](docs/RUNTIME.md) and [ENGINE_ABI.md](docs/ENGINE_ABI.md).

CoD's Volume One opening has been exercised through ordinary/timed choices,
named dialogue and save restoration. Its nine bundled music sources play
directly. This is initial support, not a claim that every CoD episode finishes;
unverified services and presentation differences are tracked in [COD.md](docs/COD.md).

Game-specific import, UI/audio bindings and services live in
`packages/shs/src/exp_runtime/shs/` and `packages/cod/src/exp_runtime/cod/`. The EXP parser, KiWi VM,
session/save system, common panels and launcher remain shared.

## Utilize the SDK

```sh
# EXP readers, bytecode decoders and the inspect/extract CLI
python -m pip install "exp-runtime[tools]>=0.6.1"

# Headless VM and engine without game adapters or a player UI
python -m pip install "exp-runtime[engine]>=0.6.1"

# Headless engine with one game, for a custom player UI
python -m pip install "exp-runtime[engine,shs]>=0.6.1"
python -m pip install "exp-runtime[engine,cod]>=0.6.1"

# Headless engine with both games
python -m pip install "exp-runtime[engine,shs,cod]>=0.6.1"

# Full desktop player with both games
python -m pip install "exp-runtime[player]>=0.6.1"

# Visual episode creator with both games and player previews
python -m pip install "exp-runtime[creator]>=0.6.1"

# Creator MCP server without Qt (combine with [creator] for live editing)
python -m pip install "exp-runtime[creator-mcp]>=0.6.1"
```

The bare `exp-runtime` install supplies file tools; `[desktop]` is an alias
for `[player]`. All components use the `exp_runtime` namespace and share one
version, including `exp_runtime.shs` and `exp_runtime.cod` when installed.
Pip installs do not require uv. The tools provide `exp-tool`; launch the full
player with `exp-runtime` after installation.

## Specifications and development

The **desktop episode creator** supports visual dialogue, choices,
branching, minigames, characters, audio, translations, debugging and native
`.exp` export with optional imported assets for EXP Runtime
and the original games. Native loader/VM checks pass; full original-app
playback remains unverified. New in v0.6.0, it is available as a standalone
desktop download or through pip. Launch a pip install with `exp-creator`,
or run it from this checkout:

```sh
uv run --locked --extra creator exp-creator
```

The creator automatically finds your player's imported library for the selected
game. See [the creator guide](docs/CREATOR.md) for saving editable projects,
using library assets and previewing through the shared player. The creator is
optional; ordinary player and iOS downloads keep their existing dependencies.
An optional [MCP server](docs/MCP.md) exposes the same authoring tools without Qt:

```sh
uv run --locked --extra creator-mcp exp-creator-mcp --workspace /path/to/stories
```

Open a saved project from that workspace in the creator to edit alongside a
model. MCP sees unsaved desktop work, and model edits appear live with shared
undo/redo. Save in the creator to write the shared project.

To contribute code, tests, documentation or compatibility reports, start with
[MAINTAINERS.md](MAINTAINERS.md).

- [EXP format](docs/SCHEMA.md): container, index, compression, metadata and payloads.
- [KiWi VM](docs/VM_SPEC.md): bytecode, all core opcodes, memory, calls and yields.
- [Engine services](docs/ENGINE_ABI.md): native service contracts and coverage.
- [UI assets](docs/UI_ASSETS.md) and [UI fidelity](docs/UI_FIDELITY.md).
- [IPA import and system fonts](docs/IPA.md).
- [Main menu](docs/MAIN_MENU.md) and [episode catalog](docs/EPISODE_CATALOG.md).
- [Episode introductions and week cards](docs/TITLE_SCREENS.md).
- [Mini games](docs/MINIGAMES.md) and [story services](docs/STORY_SERVICES.md).
- [Development and tests](docs/DEVELOPMENT.md), [distribution](docs/DISTRIBUTION.md)
  and [project provenance](docs/PROVENANCE.md).
- [Python components and custom UIs](docs/SDK.md).
- [Release notes](RELEASE.md) and [changelog](CHANGELOG.md).

Run the full test suite from the repository root with the command below.
See [Running unit tests](MAINTAINERS.md#running-unit-tests) for dependency
setup, running individual tests and interpreting optional skips.
For checks against your APK and episodes, follow
[Testing with your own game files](MAINTAINERS.md#testing-with-your-own-game-files)
to place the inputs and create the local test library.

```sh
uv run --locked --extra desktop python -m unittest discover -s tests
uv run --locked shs-tool --help
```
