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

Open this repository's **Releases** page and download the file for your device:

| Device | Download |
| --- | --- |
| Windows | `shshd-runtime-<version>-windows-x64.zip` |
| macOS, Apple Silicon | `shshd-runtime-<version>-macos-arm64.zip` |
| macOS, Intel | `shshd-runtime-<version>-macos-x64.zip` |
| Linux | `shshd-runtime-<version>-linux-x64.tar.gz` |
| Android 7.0 or newer | `shshd-runtime-<version>-android.apk` (from v1.1.0) |
| iPhone and iPad | `shshd-runtime-<version>-ios-arm64-unsigned.ipa` (from v1.1.0) |
| Episode Creator (Windows, macOS, Linux) | `shshd-runtime-creator-<version>-<platform>` (from v1.1.0, where it built) |

On a computer, extract the archive and open **SHSHD Runtime** inside. Keep the
complete app or executable folder together. Python and the runtime
dependencies are bundled.

On Android, open the APK and allow installation from that app when Android
asks; it isn't on the Play Store. Each release installs over the last and keeps
your libraries and saves. See [the Android app](docs/ANDROID_APP.md).

The iPhone/iPad app is unsigned: sign it with your own Apple ID or a signing
tool before installing it. See [the iOS app](docs/IOS_APP.md).

To make episodes, download **SHSHD Runtime Creator** for your computer from the
same release (its first launch is the same as the player's), or install it from
the release's Python wheels (see [Python components](#python-components)) and
run `shshd-creator`. It finds the player's library by itself, and can also run as
an MCP server (`--mcp --workspace FOLDER`). See [the creator guide](docs/CREATOR.md).

For development builds, open **Actions → Builds** (or **Actions → Android
APK** for Android), choose a successful run, and download its platform
artifact. Extract the artifact ZIP, then the app archive inside it.

Builds include a SHA-256 checksum. macOS builds use ad-hoc signing and are not
notarized; Windows builds are unsigned, so the first launch needs one extra
step: on macOS, right-click the app and choose **Open** (or run
`xattr -dr com.apple.quarantine "SHSHD Runtime.app"`); on Windows, choose **More
info → Run anyway**. See [distribution](docs/DISTRIBUTION.md#first-launch)
for CI triggers and packaging. Each app comes with `THIRD_PARTY_NOTICES.txt`,
the open-source components it bundles and their licences.

The Android app runs the desktop engine and renderer as they are. The
iPhone/iPad app shares the Python engine and menus, drawing through native iOS
graphics, audio and Files access.

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
through Options (**Data Management → Add Content** in the HD menus, which also takes add-ons and fonts), or drag
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
**Sound**, **Controller** (with a controller), **Extras**, **Add-Ons** (when a
translated game or add-on needs it) and, on the main menu, **Data Management**.
Extras holds the play aids: Disable Choice Timer, Choice Hints, Ask to Skip
Mini-Games, Allow Skip Ahead, Allow Undo and Use '11's Memory for Word Grid.
Without it, SHS uses the original Android menus: **Options → Cheats** has
Answer hints, Skip mini-games, Skip ad intros and Skip upsell intros only.

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
- **Skip Upsell Intros** skips the store plugs some episodes open with. Off by
  default.
- **Preferred Language** (Options › General) selects English, French, Italian,
  German or Spanish: episode names where the EXP includes them and, in the HD
  presentation, the stories of add-ons that carry translations (the DSi's, SHS
  '11's Italian, the Creator's). Other story text remains in the language
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
story groups. You can also add that file separately through **Add Content**
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

The project builds seven wheels (`shshd-runtime` and `shshd-runtime-formats`,
`-engine`, `-player`, `-shs`, `-cod`, `-creator`), attached to each GitHub release. This
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
desktop download or through pip. Launch a pip install with `shshd-creator`,
or run it from this checkout:

```sh
uv run --locked --extra creator shshd-creator
```

The creator automatically finds your player's imported library for the selected
game. See [the creator guide](docs/CREATOR.md) for saving editable projects,
using library assets and previewing through the shared player. The creator is
optional; ordinary player and iOS downloads keep their existing dependencies.
An optional [MCP server](docs/MCP.md) exposes the same authoring tools without Qt:

```sh
uv run --locked --extra creator-mcp shshd-creator-mcp --workspace /path/to/stories
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
- [Addons](docs/ADDONS.md), and the translated games:
  [New Rules](docs/NEW_RULES.md), the [cancelled Xbox 360 game](docs/X360.md),
  [SHS '11](docs/SHS11.md), the [BREW games, SHS '07 and '08](docs/BREW.md) and
  [Surviving Hollywood](docs/HOLLYWOOD.md).
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
