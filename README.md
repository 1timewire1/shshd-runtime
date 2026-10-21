# SHSHD Runtime

An experimental compatible engine for **Surviving High School** (including its
iPad **HD** release) and **Cause of Death**, aiming to reproduce the original
interface and gameplay. It executes the original KiWi scripts and reads
graphics, fonts, audio and episode data from files supplied by each player.

SHSHD Runtime is a fork of Josh Mcdaniel's
[exp-runtime](https://github.com/joshrmcdaniel/exp-runtime). It adds SHS HD's
own screens, ported from the iPad app, and plays Cause of Death in the same
presentation. It is a separate app: its own name, data folder
(`SHSHD Runtime` in your application data), window, app identifiers and
release downloads. It never opens, changes or shares an exp-runtime
installation's libraries, saves or settings, so both can be installed side by
side. Its update check asks this repository's releases only.

Supply your own game files: the **SHS Android 1.0.9 APK** (optionally with the
**SHS HD 1.4.38 IPA**), an **SHS IPA**, or a **Cause of Death IPA**, plus any
additional **EXP episodes** for that game. The importer reads those files
locally. Game content is not included in this project or downloaded by it.
IPA import checks the game's bundle identifier and required assets; its version
number is informational. See [SHS IPA support](docs/IPA.md) and
[Cause of Death support](docs/COD.md) for details.

## Download an app

Open this repository's **Releases** page and download the archive for your
system: `shshd-runtime-<version>-windows-x64.zip`, `-linux-x64.tar.gz`,
`-macos-arm64.zip` (Apple Silicon) or `-macos-x64.zip` (Intel). Extract it and
open **SHSHD Runtime** inside. Keep the complete app or executable folder
together. Python and the runtime dependencies are bundled.

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
**The iOS app does not work in this fork yet.** This fork's SHS HD and Cause
of Death screens draw with pygame directly, which the iOS app does not
include. They still need porting to its native drawing layer, which also lacks
several features they use. The iOS job builds the simulator app but fails on
launch, so releases carry the desktop downloads only. See
[the iOS status](docs/IOS_APP.md) for details; the port is planned after
v1.0.0.

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
| macOS | `dist/desktop/SHSHD Runtime.app` |
| Windows | `dist/desktop/SHSHD Runtime/SHSHD Runtime.exe` |
| Linux | `dist/desktop/SHSHD Runtime/SHSHD Runtime` |

Build on the operating system where you will play. Keep the whole app or
executable directory together: it includes Python and its dependencies.
CI builds and checks all four targets; a successful run checks each platform's
startup, but full gameplay still needs testing on each system.

You can also run directly from source:

```sh
uv run --locked --extra desktop shshd-runtime
```

## Add your game files

### Both games at once: Bulk Import

On first launch the app opens **Bulk Import**. Choose (or drag in) one ZIP or
RAR laid out like this, or put the same files in the `import` folder beside
the desktop app's executable before starting it:

```text
<SHS 1.0.9>.apk        SHS's base game
<SHS HD>.ipa           optional: SHS HD's art and screens (and CoD's HD look)
<CoD 1.4.7>.ipa        Cause of Death's base game
<font>.ttf             optional, e.g. arialroundedmtbold.ttf, copied into each library
shs_episodes/          standard SHS EXPs (and shs_options.sav)
shshd_episodes/        SHS HD EXPs (and their shs_options.sav)
cod_episodes/          CoD EXPs, cod_options.sav and, optionally, 1.4.7's mtxprods
```

The IPAs are told apart by their contents, not their names, and either game
may be left out. A wrapping folder inside the archive is fine. A game that
already has a library is left as it is.

### One game at a time

From Bulk Import, **Back** leads to the game chooser. Select **Surviving High
School** or **Cause of Death**, then choose that game's APK/IPA or open its
existing library. Add EXP files, ZIP/RAR collections or a folder later
through Options (**Data Management → Add Episodes** in the HD menus), or drag
them onto the menu. SHS's bundled stories, including Football Star, and CoD's
Volume One are imported automatically.

- **SHS HD.** The SHS HD IPA *supplements* the Android 1.0.9 APK: it is
  accepted only together with that APK, when the SHS library is created. The HD
  IPA alone is refused, and an existing APK library cannot gain it later yet.
  With it, SHS uses the iPad app's own launch flow, menus, episode grid and
  lists, dialogue, choices, mini-games, side panels, Decision Tree and
  Faceplace. See [RUNTIME.md](docs/RUNTIME.md).
- **Cause of Death** plays in the same presentation with its own styling,
  categories and airdates. Its HD look needs the SHS HD IPA as an art source
  (Bulk Import links it, or `shshd-tool add-hd-art`). Its store listing
  (`mtxprods`, from a 1.4.7 device backup) adds an info button to each episode
  with its store description and price; see [COD_STORE.md](docs/COD_STORE.md).
- **Switch Game** (the main menu's fourth button, labelled with the other
  game) moves between the installed games. Each game has its own library,
  preferences and saves. Shared asset IDs never pull artwork from the other
  game. EXP files do not reliably identify their game, so add them to the
  correct selected library.

Select an episode in Play/Resume. Imported episodes and progress persist when
you close the app.

### Options

With the SHS HD IPA (and for Cause of Death), Options lists **General**,
**Sound**, **Extras** and, on the main menu, **Data Management**. Extras holds
the play aids: Disable Choice Timer, Choice Hints and Ask to Skip Mini-Games.
Without it, SHS uses the original Android menus, where the same switches sit
under **Options** and **Options → Cheats**.

- **Choice hints** optionally marks recognized near-term score/relationship
  gains or correct quiz answers green, losses/wrong answers or no-gain
  alternatives red, and mixed effects amber. Unknown or later consequences stay
  unmarked. It is off by default.
- **Ask to skip mini-games** shows a choice before each football game, word
  grid and word quiz: Win, Lose or Play. Win and Lose finish the game at once
  with that result: football ends at least a touchdown up or down, a quiz with
  the most or the least a quiz can score. It is off by default.
- **Autoplay Dialogue** (Options → General) advances dialogue by itself 0.75 s
  after its text is out (title cards after 1.5 s); choices, name
  entry and mini-games still wait for you. Off by default.
- **Disable Choice Timer** (Options → Extras) stops timed choices' clocks and
  adds a last row, Let the Timer Run Out, for scenes that need no answer. Off by
  default.
- **Skip ad intros** starts the episodes that open with a High School Story ad
  (Game of Cones, Part 1; The Conned Artist, Parts 1 and 2) at their title
  card. The ad's own "Play the Surviving High School episode!" choice also
  offers to turn it on. It is off by default, and listed in the main menu's
  Options only, since it acts as an episode starts.
- **Episode Titles** (main menu) selects English, French, Italian, German or
  Spanish names where the EXP includes them. Story text remains in the language
  supplied by each episode.
- **SHS HD Backdrop** fills the space around the game with SHS HD's collage.
- **Check for Updates** asks this repository's latest release at launch. When a
  newer one exists, **Yes** opens its page in your browser and closes the game;
  nothing is downloaded or installed by the app.

For an SHS IPA library, the original Android menus can add your Android 1.0.9
APK through **Options → Content Library → Add APK Music** to restore music the
iOS app downloaded separately. See [IPA import](docs/IPA.md#optional-apk-music).

### Archives, folders and catalogs

ZIP and RAR collections can be imported directly, including EXPs in subfolders
and the selected game's catalog. Imported episodes remain in the app's library;
the archive is not needed afterward. RAR imports use the OS decoder on Apple
platforms and a bundled decoder in Windows/Linux downloads. Source users need
libarchive; see [archive import](docs/RUNTIME.md#episode-archives).

If your episode folder includes the original `shs_options.sav` (SHS) or
`cod_options.sav` (CoD), its catalog supplies the original season, volume and
story groups. You can also add that file separately through **Add Episodes**
or drag-and-drop. Reimporting the folder updates these names without adding
duplicate copies of identical EXPs or resetting progress. Episodes absent from
the supplied catalog keep numeric pack names.

Existing libraries from `exp-decoder-python` still work: choose **Open
Library** (or **Data Management → Open Another Library**) and select the
existing library directory. It can stay outside this project. See
[runtime setup](docs/RUNTIME.md) for paths, controls, formats and command-line
import.

## Commands

The app is `shshd-runtime`; the file tools are `shshd-tool`. Upstream's names
`exp-runtime` / `exp-tool` and the older `shs` / `shs-tool` remain as aliases.
The Python package namespace is `exp_runtime`, shared with upstream so merges
line up. Do not install upstream's `exp-runtime` into the same Python
environment, since both fill that namespace.

For example, import CoD into a separate library and open it directly:

```sh
uv run --locked shshd-tool import --game cod --ipa /path/to/CoD.ipa --episodes /path/to/CoD-Episodes --library /path/to/cod-library
uv run --locked --extra desktop shshd-runtime --game cod --library /path/to/cod-library
```

## Current state

SHS plays with the HD app's presentation when its HD IPA is supplied, and with
the Android 1.0.9 presentation otherwise: dialogue animation, portrait masks,
choices, character selection, relationship indicators, episode/week intros,
loading screens, the football, word grid and word quiz mini-games, Faceplace,
the Decision Tree (with warping), autosave and resume. Tap once to reveal
dialogue, then again to advance it.

Every episode in Cause of Death's 74-episode 1.4.7 library has been played
headlessly without errors, reaching every scene except some late chapters
inside the Volume sets, and its screens were checked against photos of the
original app. Complete 1:1 visual and timing equivalence is still being
verified. Unsupported services stop explicitly with their scene, service and
program counter. Current limits are recorded in [RUNTIME.md](docs/RUNTIME.md),
[ENGINE_ABI.md](docs/ENGINE_ABI.md) and [COD.md](docs/COD.md).

Game-specific import, UI/audio bindings and services live in
`packages/shs/src/exp_runtime/shs/` and `packages/cod/src/exp_runtime/cod/`.
The EXP parser, KiWi VM, session/save system, common panels and launcher
remain shared.

## Python components

The project builds six wheels (`shshd-runtime` and `shshd-runtime-formats`,
`-engine`, `-player`, `-shs`, `-cod`), attached to each GitHub release. This
fork does not publish to PyPI. Install from a release's downloaded wheels:

```sh
# EXP readers, bytecode decoders and the inspect/extract CLI
python -m pip install --find-links ./wheels "shshd-runtime[tools]==1.0.2"

# Headless engine with one or both games, for a custom player UI
python -m pip install --find-links ./wheels "shshd-runtime[engine,shs]==1.0.2"
python -m pip install --find-links ./wheels "shshd-runtime[engine,shs,cod]==1.0.2"

# Full desktop player with both games
python -m pip install --find-links ./wheels "shshd-runtime[player]==1.0.2"

# Visual episode creator (exp-runtime v0.6.0's), with both games and player previews
python -m pip install --find-links ./wheels "shshd-runtime[creator]==1.0.2"

# Creator MCP server without Qt (combine with [creator] for live editing)
python -m pip install --find-links ./wheels "shshd-runtime[creator-mcp]==1.0.2"
```

The bare `shshd-runtime` install supplies file tools; `[desktop]` is an alias
for `[player]`. See [SDK.md](docs/SDK.md) for the components and custom UIs.

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
- [Cause of Death](docs/COD.md), its [release dates](docs/COD_RELEASE_DATES.md)
  and [store listing](docs/COD_STORE.md).
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
uv run --locked shshd-tool --help
```
