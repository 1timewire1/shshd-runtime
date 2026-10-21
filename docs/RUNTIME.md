# Compatible runtime and user content

Revision: 2026-10-05. This is an experimental implementation of the shared SHS/CoD EXP engine.
CoD-specific support and limits are in [COD.md](COD.md); the fidelity notes
below describe the SHS reference.
It executes original KiWi instructions and reuses original assets. It currently
plays the opening of **The New Girl**, including real branching choices and its
first mini game, and implements timed words, word/picture grids and football; it
does not yet play complete episodes.

## Fidelity target and implementation order

The required destination is a **1:1 game experience**, including behavior and
presentation. The existing desktop UI is a temporary playback/debugging frontend.
Its remaining prototype layouts, simplified music playback, and convenient desktop
controls do not define the final design. Dialogue now uses the original APK
layout, fonts, borders and masked portrait frames, with native left/right
placement, progressive text, animated portrait/name transitions and session-owned
pagination. Ordinary choices use a reconstruction
of the supplied original screenshots: one translucent bordered panel, a circular
portrait, the original fonts, divided rows and the gear/footer. Remaining
placement/timing differences are listed in [UI_FIDELITY.md](UI_FIDELITY.md#ordinary-choice-panels).
Mini games reuse the original APK art with recovered input/scoring contracts;
their remaining presentation differences are in [MINIGAMES.md](MINIGAMES.md).
Episode introductions and week cards now use their original background,
external glyph fonts, placement, entrance and acknowledgement gate; see
[TITLE_SCREENS.md](TITLE_SCREENS.md). Name entry uses recovered native layouts;
see [NAME_INPUT.md](NAME_INPUT.md).

The user reports that the iOS and Android interfaces were identical. The
available **Android 1.0.9 executable and APK assets** are therefore the working
reference for reconstructing the shared original interface. Native layout
calculations and shipped glyph/art data take priority over estimates from the
prototype. Newly discovered platform differences must remain explicit; shared
appearance does not establish identical engine internals or platform services.
The current concrete asset/code evidence is in [UI_FIDELITY.md](UI_FIDELITY.md).
IPA asset import and the inspected iOS differences are documented in
[IPA.md](IPA.md), including system-font fallback and its fidelity limits.

Implement fidelity in this order:

| Work | When / reason |
| --- | --- |
| Original coordinate system, asset scale, font metrics, text layout and pagination | Establish early; these determine screen geometry, option placement, and input regions |
| Panel creation/destruction, script-visible panel side effects, input acceptance, animation completion and timers | Model with each engine feature; these affect execution and cannot be recovered by changing colors or textures |
| Minigame rules, timing, random state, input/result mapping | Recover together with the minigame's UI; a visually similar screen can otherwise produce different outcomes |
| Persistent panel/timing state and ordered audio requests | Preserve in the engine/session model as understood; saving only the current visible asset IDs is insufficient for full fidelity |
| Final artwork composition, borders, colors, and small spacing adjustments | Refine after the relevant behavior and layout contracts are stable |

The VM, resource layer, and frontend are already separate. Visual changes should
reuse the EXP decoder and VM, but the current host/presentation state is still
incomplete. Adding native panel, animation, audio, and random state can require
new save fields and explicit save-version migrations. The present save schema
must not prevent those corrections.

Use an original dialogue/choice sequence as an early reference before expanding
the UI. Compare the same inputs against the selected release: VM requests and
game state for behavior, screenshots for stable layouts, and recordings or
frame traces for transitions, sound, and timing. Extend those comparisons to
each recovered minigame. Automated tests of the reimplementation establish its
own consistency; they do not alone establish equivalence to the original.

This permits incremental progress on the missing services while avoiding a
large final rewrite of behavior that was initially treated as styling. All
known approximations remain explicit until their native contract is recovered
and the corresponding comparison passes.

## Distribution model

Each player supplies their own **SHS Android 1.0.9 APK** or **compatible SHS IPA**, or **CoD IPA**,
and any additional **episode EXP files**. The package provides the base resource
bank, available audio, and bundled stories. Additional episode files remain necessary for their
respective stories. There are no game downloads or dependencies on this
repository's extracted assets, Ren'Py projects, Ghidra installation, or original
directory layout.

The reusable program ships separately from that content. This is the same
user-supplied-content model discussed for game recompilation projects; this
implementation is a **compatible engine with a KiWi interpreter**, rather
than a static recompilation of the ARM executable. APK native code is used
only to identify the supported Android profile. IPA import uses the game bundle
identifier and required assets, with informational version/build metadata.
Neither package's native code is executed.

`MANIFEST.in` explicitly selects runtime source and authored documentation for
the source distribution. Setuptools package discovery is restricted to
`packages/*/src/exp_runtime`. Original APKs/IPAs/EXPs, extracted art/audio, decompiled native C,
generated Ren'Py games, and saved progress are excluded from Python packages
and executable builds. Players can clone the engine's source and build their
own executable before supplying any game content. See
[DISTRIBUTION.md](DISTRIBUTION.md) for that workflow and the separate Git
publishing boundary. The standalone project contains authored files and no
Git history or native decompilations from the research checkout. Libraries
created under custom directory names must likewise remain local.

## Install and play

From a source checkout:

```sh
uv run --locked --extra desktop shshd-runtime
```

`shshd-runtime` (or `shshd-tool play` without `--library` / `--game`) opens the
game chooser. Choose SHS or Cause of Death, then import its assets or open its
existing library. Options accepts additional episodes for the selected game;
drag-and-drop also works. **Options → Switch Game** checkpoints the current
story and opens the other installed game, or the chooser if it is absent.
No assets or saved progress cross game
libraries. The `shs` and `shs-tool` commands remain compatibility aliases.
See [MAIN_MENU.md](MAIN_MENU.md) for launcher migration and native menu evidence.

Command-line imports and direct episode launch remain supported:

```sh
uv run --locked exp-tool import --apk /path/to/game.apk --episodes /path/to/Episodes --library /path/to/my-shs-library
uv run --locked exp-tool list --library /path/to/my-shs-library
uv run --locked --extra desktop exp-tool play --library /path/to/my-shs-library --episode "The_New_Girl.exp"
```

For an SHS IPA, replace `--apk /path/to/game.apk` with `--ipa /path/to/game.ipa`.
Optionally add `--music-apk /path/to/game.apk` to supply its missing original
music. For an existing IPA library, use **Options → Content Library → Add APK
Music** or `exp-tool add-music --apk /path/to/game.apk --library /path/to/library`.
The IPA remains the base package; its assets and installed original fonts take
precedence. See [optional APK music](IPA.md#optional-apk-music) for the exact scope.

Without uv, install with `python -m pip install -e '.[desktop]'`, then use
`exp-tool` from that environment. Decoder/headless tools do not require pygame.

`--episodes` accepts multiple files or directories and recursively finds EXP
files, including uppercase `.EXP`. It is optional when using only the episodes
inside the supplied APK or IPA. Import creates a **new** library directory; it refuses
to overwrite an existing library. Add more episodes through the app's Options
screen; the batch is validated before updating the manifest. Saves can be copied
between libraries with identical content hashes. IPA dialogue checkpoints also
require matching font metrics; see [IPA fonts](IPA.md#fonts). Imports preserve supplied files.

CLI import requires an explicit `--library` destination. `list` retains the
legacy `.shs-library` default; supply `--library` for another game or location.
The launcher remembers a separate path for each game and otherwise uses
`SHSHD Runtime/libraries/shs` or `SHSHD Runtime/libraries/cod` in application data.
It discovers a source checkout's `.shs-library` without moving it. It never reads
upstream's `EXP Runtime` or older `SHS Runtime` folders (this fork is a separate app). An explicit `--library` opens that library directly;
`--game shs|cod` opens a game directly and checks that supplied assets match.
`--episode` accepts an exact title from any of the five metadata slots, filename, or unique hash prefix printed by
`list`. Starting with `play --episode` begins a fresh session. To resume the
newer automatic/manual checkpoint:

```sh
uv run --locked exp-tool play --library /path/to/my-shs-library --episode "The_New_Girl.exp" --resume
```

`--load /path/to/progress.shs-save.json` loads a specific save instead.
`--no-audio` disables playback. These are runtime JSON saves; original game
saves are not supported.

**Options → Episode title language** selects English, French, Italian, German
or Spanish titles where supplied, with English/filename fallback for empty
slots. `exp-tool list` follows the saved preference; `--title-language en|fr|it|de|es`
overrides it without writing preferences. Search accepts all supplied titles.
The inspected game files contain English story text; selecting a title slot
does not translate dialogue or menus. Saves and live progress stay compatible.
See [the localization evidence](MAIN_MENU.md#episode-title-languages).

| Input | Action |
| --- | --- |
| Checkmark, tap dialogue, Enter, or Space | Finish an unfinished text reveal; once complete, show the next page or acknowledge the VM after the last page |
| Tap a title screen / Enter / Space | Complete an unfinished title wipe; once its input gate opens, acknowledge the presentation |
| Click an option or press 1–9 | Submit that choice to the VM |
| Click a word or press 1–4 in timed words | Score the selected word and deal new options |
| Hold and drag across grid cells | Trace a word or picture sequence, including diagonal steps; no repeated cell |
| Click a football target or press 1–9 | Commit that play; targets change over time |
| Tap football help / Enter / Space | Continue after its native reading delay |
| Gear on title, dialogue, choice or mini-game screens | Open the pause menu (Resume, Options, Help & About, Main Menu); active game time and music pause |
| Type, Backspace, Enter | Edit a name (up to 16 ASCII letters/digits, subject to native font width); Enter submits a nonempty name or dismisses its alert |
| F5 (also Pause → Options → Save without the HD app, and the fallback screen's Save button) | Replace the current episode's manual save slot |
| F9 (also Pause → Options → Load, and its Load button) | Restore that slot |
| Arrow keys, Enter or Space | Select and pick a choice, or a pause or main menu item. Left/Right adjust a volume slider |
| Arrow keys, Enter or Space (episode pickers) | Move between episodes; in the New Game / Continue popup, between its two cards and back (Continue first) |
| I (episode pickers) | Open the highlighted episode's info card, where it has one (CoD with its store listing) |
| Left / Right (portrait picker) | Bring the previous / next portrait to the front; Enter confirms |
| Wheel, arrow keys, Page Up/Down | Scroll long option lists and other non-dialogue screens |
| Escape | Open/close the pause menu during play; go back within application menus |
| Main Menu / Close window | Save a separate automatic checkpoint and return to the menu / exit |
| (nothing to press) | The automatic checkpoint is also written every 60 s of play and once when the window loses focus, as the app's `SHSEngine::onTick` / `onExit` do |

## Content library contract

### Episode archives

Episode selection, folder imports, drag-and-drop and CLI `--episodes` accept
loose EXPs and ZIP/RAR collections. Subfolders are scanned for EXPs and the
selected game's catalog. macOS metadata and unrelated files are ignored.
Imported episodes/catalogs persist independently of the source archive.
The existing batch validation, content deduplication and save preservation
apply to every input form; a failed batch does not partially publish episodes.

Archive paths are never used as output paths. Selected members reject parent
traversal, absolute/drive paths, links, duplicate normalized names, encryption
and oversized data. Limits are 10,000 entries, 64 MiB per EXP and 2 GiB total
unpacked data; catalogs retain their own smaller limit. RAR streams stage
selected members to numbered temporary files, cleaned on success or failure.
RAR's total includes ignored members because a solid decoder may unpack them.

RAR4/RAR5 decoding uses libarchive via ctypes, without external commands or a
network request at import time. macOS/iOS use `/usr/lib/libarchive.2.dylib`;
Windows/Linux downloads bundle the pinned decoder built by `tools/build_rar.py`.
Source users on Windows can run that helper with CMake and a C compiler;
Linux can use its system libarchive. Unsupported variants (including RAR4
solid archives in Apple's decoder), encrypted or incomplete multipart inputs
report decoder errors; extract those to EXP/ZIP first. Archive checksum
enforcement follows the platform decoder: Apple's tested system library did
not reject a stored-member CRC mismatch. Every imported EXP still receives
the same full structural/script validation as a loose EXP. Do not interpret
content hashes as proof that a source archive was undamaged.

### Layout

```text
library/
  library.json
  content/<package SHA-256>.apk  # or .ipa
  content/<EXP SHA-256>.exp       # external episodes and extracted Football Star
  saves/<EXP SHA-256>.shs-save.json
```

Android manifests have `format: "shs-content-library"`, `version: 1`, and
`profile: "shs-android-1.0.9"`. `apk` contains `file`, `sha256`, and
`native_sha256`. IPA manifests use `version: 2`, `profile: "shs-ios-assets-v1"`,
and `ipa` containing `file`, `sha256`, and informational `app` plist metadata.
They do not contain an `apk` record or require a native executable hash.
With optional APK music, an IPA library uses version 3 and a separate
`music_apk` record (`file`, `sha256`, `native_sha256`). Only the ten verified
iOS download IDs absent from the IPA can resolve through this supplemental
archive. All required tracks are validated before publishing the new manifest.
Each `episodes` entry contains:

| Field | Type / meaning |
| --- | --- |
| `id`, `sha256` | Identical lowercase 64-digit SHA-256 of the complete EXP bytes |
| `name` | Original basename, for display/selection |
| `pack_id`, `episode_id` | Unsigned metadata words |
| `titles` | Five UTF-8 localized metadata strings, in archive order |
| `scripts` | Sorted exact resource IDs containing KiWi programs |
| Exactly one of `file`, `apk_member`, `ipa_member` | Copied EXP path or member inside the matching base package |

Duplicate EXP bytes produce one entry, even when supplied under different
names or also present inside the package. Metadata IDs alone are not unique content
identities. All filesystem paths in the manifest are relative, content-derived
paths, so the entire library can be moved to another directory or computer.

The optional manifest field `episode_catalog` retains original English category
metadata imported from a user's `shs_options.sav` or CoD's `cod_options.sav`.
It supplies season, volume and story group headers without changing EXP
identities or saves. Folder/EXP imports
discover this optional sidecar; users can also add it through the episode
picker. The native envelope, normalized metadata schema, matching and fallback
rules are in [EPISODE_CATALOG.md](EPISODE_CATALOG.md).

The optional manifest field `store` (CoD libraries only; this fork) points at
`content/<sha256>.json`, the products of Cause of Death 1.4.7's store listing
(`Documents/mtxprods`) imported the same way. The device's user record in that
file is never kept. The format and the kept schema are in
[COD_STORE.md](COD_STORE.md).

Import validates a private copy of the APK or IPA, decodes all imported EXP payloads,
and parses their KiWi programs before publishing the library by directory
rename. A failed import leaves no partially initialized destination. Archive
paths are never used as output paths. Import checks duplicate member names. Android import
rejects an unknown native profile; its supported member is `lib/armeabi/libshs09.so`, with
SHA-256:

```text
b17aa4c71bc46666d414cafae6fac92bbcd755f3dcccd73975cf05f4a119665b
```

IPA import instead checks its bundle identifier, app root, and the required UI
asset contract described in [IPA.md](IPA.md#identification-and-compatibility).
It accepts compatible assets independently of the package's version number.

The complete APK/IPA hash is checked when opening the library; the selected EXP hash
is checked when opening its episode. The native-library hash identifies the
Android engine profile, whereas the **profile and complete package/EXP hashes**
identify save content compatibility. A differently repacked package may import
but has a different save identity. IPA saves use `ipa_sha256` in place of
`apk_sha256`; the JSON save version does not change.
The optional music APK is hash-checked on open but excluded from save identity:
adding audio does not alter the story, layout or fonts, and old IPA saves remain
compatible. Its addition does not rewrite any manual or automatic save files.

`import_game`/`shs-tool import --hd-ipa` optionally accepts the iOS HD
(iPad) build's own `.ipa` alongside the required Android APK. It is never
required. When present, the manifest gains an `hd_ipa` field shaped like
`apk` (`file`, `sha256`, `executable_sha256`), validated the same way on
every open. The supported executable is
`Payload/Surviving_HS.app/Surviving_HS` from the SHS HD (iPad) 1.4.38
build, with SHA-256:

```text
327cf59ddb8efd704795099d5b5e9a04ceec51f6c084bf7d0962e78e3ae7e875
```

`ContentLibrary.hd_asset(resource_id)`/`EpisodeResources.hd_asset(...)`
return the HD ipa's raw bytes for a resource id, or `None` if no HD ipa was
imported or the id isn't eligible -- every caller must keep working from
the Android original alone. Two disjoint id ranges are eligible, per
`content.HD_ASSET_MAP`/`HD_SHARED_CONTENT_RANGE`:

- **`HD_SHARED_CONTENT_RANGE` (1000 <= id < 25000):** per-scene content
  (backgrounds/portraits) ships at the *same* numeric id on both
  platforms. Trusted directly by id, without a per-asset check: sampling
  667 ids that exist in both banks found 606 genuine HD upgrades of the
  identical asset (confirmed by rendering and comparing, not just size),
  every mismatch found was a low chrome/icon id well outside this range,
  and every Android base id inside it decodes as an image (KiWi bytecode
  programs start at 25000, confirmed by their `kiwi` header -- never
  substituted, or a script load would run the wrong dialect entirely).
- **`HD_ASSET_MAP` (below 1000):** a small, individually-verified table
  for the handful of chrome ids HD numbers or formats differently --
  currently just the dialogue/choice/character-picker portrait mask
  (Android id 268 -> HD id 311, confirmed identical shape at a clean
  native 2x resolution). Never extended by id alone; low ids can
  coincidentally collide with unrelated HD content (id 10 is a menu
  button on Android, an unrelated loading-screen collage on HD).

`ContentLibrary.read_asset`/`EpisodeResources.read_asset` (used by every
`<26000` asset load, not a separate opt-in call) transparently prefer
`hd_asset()`'s result when it returns something, so this upgrade reaches
every background/portrait/mask consumer without per-call-site changes. See
`legacy/findings.md`, "HD chrome assets may be directly usable after all"
and "53% ... questioned and checked properly" for how this was verified.
Audited live across the real 195-episode HD library: HD background
coverage went from 53% to 100% of episodes with an HD ipa imported (1315
vs 202 unique HD backgrounds found, 5956 vs 2926 unique HD portraits),
zero decode errors either way.

The runtime's strict EXP reader follows [SCHEMA.md](SCHEMA.md): BE outer
fields, the LE LZMA wrapper, aliases, and five UTF-8 titles. It rejects partial
overlap, duplicate IDs, unknown flag bits, inconsistent sizes, unsupported
compression properties, and oversized records/members (64 MiB). These checks
are a supported-input policy; the native reader is less defensive and, for
example, ignores compression flag bits other than bit 0. Native grouped
fallback and EXPD variants remain unsupported.

### HD art for standard episodes (this fork)

A standard (non-HD) SHS episode can draw HD pictures where another
episode's HD release has the same picture: the library's **twin store**
(`hd_twins/` in the library: `index.json` and `pack.bin`) maps a standard
picture's fingerprint to its HD twin's bytes. `hd_art` in `player.json`
(or `SHS_HD_ART`) picks the mode: `off`; `twins` (twinned pictures only);
or `fill`, the default (twins, and every other standard picture drawn at 2x
so the episode keeps HD's density). `hd_twins/coverage.json` records how much
of each standard episode has a twin. An episode whose counted pictures are
all HD loses the picker's **SD** mark.

The store holds extracted art, so it is never shipped. It is built on the
player's machine from **SHS's shipped twin map**
(`packages/shs/src/exp_runtime/shs/hd_twin_map.py`), which contains no art:
- each standard picture's fingerprint and size, with its HD twin's
  fingerprint;
- per standard episode, the resource ids its coverage counts.

**The build** (`hd_twins.build_from_map`):
- **When:** during the picker's first-time preparation ("HD art: n of m
  episodes"), for any SHS library with HD episodes whose store did not come
  from the shipped map's `VERSION`. A library imported by an earlier version
  gets it on its next open; nothing is re-imported.
- **How:** it searches the library's own episodes for each HD fingerprint
  (HD episodes first), copies what it finds, and counts coverage from what
  was actually built. A picture the player's files cannot supply stays
  standard, and the episode keeps its SD mark.
- **Time:** on the owner's 284-episode library it found all 1,795 twins in
  about 45 seconds.

**Making the map.** The map comes from a library that holds both the standard
and HD copies of the stories:
1. `tools/build_hd_twins.py` pairs them story by story.
2. `tools/extend_hd_twins.py` adds season bundles, reused backgrounds and the
   hand-confirmed pairs (`--confirmed`).
3. `tools/build_hd_coverage.py` measures coverage.
4. `tools/export_hd_twin_map.py --library LIBRARY` writes the map.

Rerun the export after improving that library's store; the new `VERSION`
makes every library rebuild once.

## Resource and execution boundaries

| Layer | Responsibility |
| --- | --- |
| `content.py` | Import, profile/content identity, EXP reader, resource banks |
| `decode/bytecode.py` | Lossless KiWi schema decoder |
| `vm.py` | Signed-word execution, memory, calls, branches, suspension |
| `engine.py` | Native host services and persistent game/panel state |
| `runtime.py` | Input callbacks, scene scheduling, timers, save/load |
| `fonts.py` | Original descriptor records, native text metrics, wrapping, color controls |
| `ios_assets.py`, `ios_fonts.py` | Validated IPA UI roles and installed-font rendering/fallback |
| `ui_assets.py` | Native layout records, ARGB/alpha image packs, transforms and masks |
| `atlas.py` | ABGR sprite atlases, signed composites and binary glyph-font records |
| `minigames.py`, `word_grid.py`, `football.py` | Game rules, random streams, input phases, scoring and clocks |
| `dialogue.py` | Native dialogue geometry, name placement and page layout |
| `title_screen.py`, `desktop_title.py` | Episode/week title fonts, layout, entrance animation and input gate |
| `desktop_text.py` | Original atlas drawing for dialogue; font/layout/glyph caches |
| `desktop_dialogue.py` | Original dialogue artwork and portrait composition |
| `desktop.py` | pygame input, presentation, images, and basic audio |
| `audio.py` | Verified Android/iOS music-cue redirects and millisecond start offsets; separate from exact resource lookup |
| `menu.py`, `desktop_menu.py` | Native menu geometry, string/glyph resources, menu UI, local preferences/checkpoints |
| `application.py` | Setup/import, menu navigation, session lifecycle, worker/event loop and exit |

The original script chooses the next instruction. A button submits an option
index; the runtime performs the recovered callback, and the VM executes the
resulting branch. A renderer does not select scene links or interpret nearby
numbers as dialogue.

Native image-bank selection (`FUN_00082bc0`, iOS `0003dd60`) uses the base bank for
resource IDs below 26000 and the selected EXP bank for IDs at least 26000. APK numeric files
live directly under `assets/Assets/`; six native IDs have a `.mp3` suffix,
including image pack 16. The audio subdirectories have explicit
numeric filenames. Font/image/animation atlas filenames in other subdirectories
are separate namespaces, so `images/1.png` never replaces global resource 1.
An absent episode resource does not silently fall back to an unrelated APK ID.
Named Android UI resources are read explicitly with `ContentLibrary.read_ui_asset()`.
IPA numeric files live in `Payload/<app>.app/res_generated/` without suffixes.
Host UI roles use `read_ui_resource()` to select the matching platform assets;
this never remaps script-visible `read_asset()` calls.
Music playback separately applies eleven verified Java sound-engine redirects:
for example, cue 8202 plays APK track 8201 starting at 2800 ms. The requested
ID remains in engine/save state, and generic resource reads stay exact. These
cues use the APK already in the library; no additional download or import is
needed. See [Android music cues](ENGINE_ABI.md#android-music-cues).
Font atlases are read directly from the imported APK, including `.dat` files
that contain PNG data. Neither original font tables nor images ship with the
runtime; no system-font installation is needed for Android dialogue. IPA text
uses its bundled or installed original faces, then the system default if absent.
Its font rendering and missing audio limits are in [IPA.md](IPA.md).

Script loading follows a different path: the selected episode's exact script
IDs take priority, including its scripts in the 25000 range. Playback starts at
25001. Service 10 appends a scheduled script; after HALT the runtime loads the
last scheduled script. Registers and complete stack backing survive that load,
while data and PC/SP/FP reset according to the core VM contract.

<a id="runtime-save-schema-version-13"></a>
<a id="runtime-save-schema-version-14"></a>
<a id="runtime-save-schema-version-15"></a>
<a id="runtime-save-schema-version-17"></a>
<a id="runtime-save-schema-version-18"></a>
<a id="runtime-save-schema-version-23"></a>

<a id="runtime-save-schema-version-24"></a>
<a id="runtime-save-schema-version-25"></a>
<a id="runtime-save-schema-version-26"></a>

## Runtime save schema, version 27

This is a new format for the reimplementation. No pickle, object deserialization,
or original executable code is used.

This HD fork and upstream exp-runtime number their saves independently after
the shared version 12. This fork's versions 13–22 add the Decision Tree,
Faceplace, location pan, portrait expression changes, status icons and
tree-free saves; version 23 adds exp-runtime v0.4.1's background pan, Continue
tab expansion and word-grid tile effects (upstream's own versions 17–19), and
its survey receipt; version 24 adds the HD word game's pacing (`WordGame.hd` and
its selection, fly-off, fly-on and score-effect clocks; older saves load with
`hd` false); version 25 adds exp-runtime v0.4.2's dialogue lifecycle (upstream's
own versions 20 and 21, described below in their terms) and drops this fork's
own expression memory it replaces (`engine.last_speaker`/`last_expressions`,
the animation's `expression_committed`, the portraits' `from_asset_id`); the
animation keeps this fork's uncapped `age_ms` for HD's emotion effects. An HD build's saved notice clock may also run past Android's
lifetime, to the HD letters' start plus their own lifetime. Version 26 adds
`engine.notice_mode`, the portrait side (1 or 2) those letters started on, which they keep on later lines; older
saves load with 0, following the current portrait. Version 27 adds exp-runtime v0.6.x's fields (upstream's own versions 22-26, described below in their terms): music and effect playheads (`music_serial`, `music_stop_ms`, `music_playback`, `sound_playback`), the scene-transition state and its random stream, bitmap/widget text history, the choice entrance clock, expression layers and the minigame effects; older saves take their defaults without inventing missing history, and an IPA library's older save reflows its typography. This fork's player does not fill the audio playheads yet (its music is `music_stream.py`'s) and leaves the scene transition unset (`scene_fade.py` draws its fades). The fork keeps the `shs-runtime-save` marker; upstream's
`exp-runtime-save` saves are not accepted, because the same version numbers
describe different fields there. Version-number references below that concern
IPA libraries and survey receipts are upstream's numbering. JSON fields are:

| Field | Contract |
| --- | --- |
| `format`, `version` | `"shs-runtime-save"`, `27` |
| `content` | `profile`, `apk_sha256`, `episode_sha256`; must exactly match loaded content |
| `scene` | Unsigned current script resource ID |
| `script_sha256` | Hash of the losslessly encoded current program |
| `vm` | Full mutable machine state, defined below |
| `engine` | All current `EngineState` dataclass fields, including panel, speaker font history, dialogue/title animation, choice builder, random streams and any active mini game |
| `pending` | Null, or `{name, details}` for the suspended screen/service or terminal episode exit |
| `remaining_ms` | Null for no timer; otherwise the remaining active choice time in milliseconds. Zero is still pending; the next positive active tick expires it. The visible circular timer derives from this value. |
| `scene_loads` | Nonnegative number of scheduled script loads |

The selected game and native `app_version` are derived from the validated
library, not serialized engine fields. CoD service 70 selector 6 reads
`CFBundleVersion` from the retained IPA's `Info.plist` and writes dynamic string
slot 0; that mutable slot is saved normally. Missing native version metadata
keeps the query pending. Older CoD stops at services 70, 94, 96 and 100 resume their
original call and continuation without replaying previous choices or random
draws. Their outgoing portrait is recovered from the saved panel when needed.
These handlers were introduced without changing the version-16 save schema.

SHS stops at 14, 15 and 21 also resume their retained calls. Services 14/21
complete with the verified native zero result. Service 15 presents named
dialogue and retains its complete frame through paging and acknowledgement;
save validation honors its optional negative prefix. Loading an older stop
recovers the outgoing portrait before continuing without replaying earlier
bytecode or random draws. These additions originally retained save version 16.

Version 17 adds `dialogue_animation.continue_ms`, the 0–250 ms visual clock
for the native Continue tab. It stays zero until typing completes, advances
only with active story time and resets on each page. Versions 1–16 remain
readable: an already completed page gets a settled tab; an unfinished page
gets a hidden one. VM state, reading position and input gates are unchanged.

Version 18 adds the grid's selected-tile pop clocks, glint clock and active
fragment bursts. These preserve in-flight effects without drawing new random
values on load. Versions 1–17 retain their board, selection, scores, random
state and VM frame; absent effects start inactive. Native fragment creation
now consumes its recovered random draws, so future generated boards may differ
from older runtime builds after a successful word. Historical omitted draws
are not reconstructed. See [GRID_UI.md](GRID_UI.md#saved-presentation-and-verification).

Version 19 adds `engine.background_pan`: `automatic:bool`, signed-word
`alignment:int`, `start:float[0..1]`, `target:float[0..1]` and
`elapsed_ms:int[0..250]`. The fractions represent horizontal image overflow;
no image pixels or device dimensions are needed to restore the movement.
The native 250 ms linear pan shares the active session clock and freezes with
pause/focus loss. Versions 1–18 start with their previous centered view and
automatic alignment enabled, without replaying dialogue or altering VM state.
Old SHS/CoD stops at service 97 resume only that retained call and continuation.
See [background panning](UI_FIDELITY.md#background-panning). Older runtime builds
cannot read version-19 saves.

Upstream's version 20 (this fork's 25) adds `dialogue_animation.box_grow:bool`. The existing elapsed
clock also drives the native iOS bubble entrance now shared by both games.
Versions 1–19 retain a full-size box for the saved dialogue without changing
its revealed text, portrait/name clocks, pending call or VM. The next new
portrait-speaker entrance uses the recovered 120+200 ms animation.

Upstream's version 21 (also this fork's 25) adds `engine.dialogue_history`, containing the hidden portrait's
`anchor_mode` (0/1/2) and a character-ID map of signed last-expression bytes.
Dialogue details also retain `initial_expression`. The animation adds
`native_lifecycle:bool`, `anchor_mode:int`, nullable `initial_portrait`, integer
`initial_expression`/`expression`, `presentation_ms:int[0..2400]`, and booleans
`visuals_finished`/`housing_clipped`. The presentation clock is independent of
page-local text timing. It controls the one-second expression update and both
art fades; the existing elapsed clock drives bubble and shake completion.

Covered dialogue remains saved while a choice or other temporary panel is
active, without ticking. Explicit panel removal and scene teardown clear the
animation. A new scene clears both expression tables for IDs 0–199 while
retaining the global portrait anchor. Loading validates typed fields, portrait
identity, expression cache, text and progress without executing VM callbacks.
This fork's versions 1–24 remain readable: their current expression stays
visible, their old shake/box timing continues, and no new fade or clipping is
replayed. The next dialogue uses the new lifecycle. Older runtimes cannot read
version 25 or 26.

Version 22 adds:

- `engine.music_serial:int >= 0` and `music_stop_ms:int[0..32767]` for repeated
  music requests and CoD's requested stop duration. Optional `music_playback`
  records the host's actual `asset`, boolean `repeat`, `position_ms >= 0`,
  `fade_ms`, `fade_total` and boolean `finished`. The fade has
  `0 <= fade_ms <= fade_total <= 32767`; a zero remaining fade has zero total.
  Host save/checkpoint operations capture it; a new script cue invalidates
  stale captured playback. Headless and older saves leave it null.
- `engine.sound_playback` lists active effects as `{asset, position_ms}` with
  `asset:int[0..32767]` and nonnegative integer position. Host checkpoints
  capture their playheads; headless and older saves use an empty list. IPA
  pause/menu handoffs retain the snapshot taken before the outgoing fade,
  including effects, with the native whole-second truncation, until audio is
  restored. Backend handles and menu clicks
  never enter the save. Restoring effects does not repeat VM calls.
- `dialogue_animation.expression_effects:bool` and an extended
  `presentation_ms:int[0..3150]` clock for expression 6–9 decorations. Poses
  are derived from the existing portrait identity and expression request.
- Grid `score_effects` (value, first-tile X/Y, 1–400 ms remaining),
  `score_pending`, `score_phase` (0/1/2), `score_target` and `display_score`.
  Score flights, pending points and target sum to the committed game score;
  the script callback does not wait for the displayed counter to catch up.
- Grid `highlight_offsets` maps cell indices to shuffled 0–2999 ms countdown
  offsets. A departing board retains its offsets and round clock. Null means
  an old save has no offset history; it stays fully bright until the next
  board is committed, without inventing historical random draws.
- Grid `tiles` retains each cube's flip, growth/shrink and shine countdowns,
  delays and active flags. Null retains legacy elapsed-time rendering until
  the next board setup. `transition.deferred` distinguishes a pending native
  board generation from an older save that already generated its next board.
- Both adapters' `scene_transition` retain `selector`, `phase` (0 idle, 4 out,
  1 waiting for the next UI, 3 in) and the deferred signed-word `result`.
  CoD also stores `elapsed_ms` and its separate libc `random_state`; SHS's
  nonvisual boundary uses successive ticks. Restoring checks the phase and retained
  result against the pending VM/UI; [CoD](COD.md#scene-transitions) describes
  durations, callback order and remaining limits.
- Football `touchdown_stars`, up to 50 finite position/velocity, angle/spin,
  delay and opacity/fade records. Creation consumes 450 engine RNG draws;
  ticking and drawing consume none.
- Football `shadow_ms` holds nine retained 440 ms animation clocks, using -1
  before a slot's shadow is first created. Null preserves the older saved
  presentation until its next setup; later deals retain already created clocks.

Versions 1–21 keep their existing VM, random state and committed scores.
Missing effects start empty, an older grid counter starts at its recorded
score, and the current dialogue suppresses decorations whose history was not
saved. No historical random draws or sound cues are replayed. New dialogues
and subsequent minigame actions use the recovered effects. Older runtime
versions cannot read version-22 saves.

Version 23 adds:

- `engine.text_history`: signed-byte `previous_glyph:int[-128..127]`, a
  `labels` map of label names to their incoming signed bytes, and the last
  assigned `footer:string`. Android bitmap text assignments advance the
  global byte; measurement, redraw, glyph reveal and save restoration do not.
  The saved label inputs reproduce first-glyph kerning independently of draw
  order. The footer skips identical assignments, matching native code.
  `RuntimeProcess` carries this history across episodes of the same game;
  explicit restores use the saved history. IPA outline fonts do not use it.
- `engine.dialogue_history.indicators`: up to four retained icon poses with
  `asset_id`, finite `x/y/rotation`, `flash_asset`, finite `flash_scale` and
  `flash_alpha`. These represent the active Android portrait's children,
  including their frozen state after dialogue removal or narration.
- `dialogue_animation.relationship.retained`: null for an ordinary derived
  effect, or the frozen pose list for a suppressed Android SHS indicator.
  Native reattachment cancels child actions before the negative asset request
  leaves those children unchanged. Character 45 and the player clear them;
  SHS/CoD IPA requests clear their own children instead. Restoring validates
  asset IDs, finite bounded poses, count, platform and suppression state.

Versions 1–22 start bitmap history at -1 and hidden indicator history empty:
those saves contain no evidence for the missing earlier updates. Their active
relationship effect continues using its existing descriptor. Migration does
not replay a panel assignment, random draw, sound or VM callback. Older
runtimes cannot read version-23 saves. See the [font/widget follow-up](
UI_FIDELITY.md#bitmap-history-and-reused-portrait-follow-up) for coverage and
the remaining original-app comparison limits.

Version 24 adds `engine.choice_ms`, an integer in `[0,250]`. Ordinary
choice attachment resets it to zero; active ticks advance it independently
of the script's timeout. The menu rejects early answers without a callback
or click sound. IPA drawing fades the panel over this clock; Android draws
it immediately. Pausing freezes both clocks. Versions 1–23 migrate to 250
(an already attached choice), preserving the saved remaining timeout rather
than replaying an entrance. Rendering and restoration never advance time.
Creator playtest `choose` waits out this real gate and checks whether a short
timer has already moved the story on before applying the requested answer.

Version 25 separates expression layers from the dialogue's one-second request
clock. `dialogue_animation.expression_transition` is null before a request,
or contains `previous` and `portrait` descriptors, the requested `expression`,
and `elapsed_ms:int[0..2150]`. Consecutive same-speaker lines retain this state
until their next request; a speaker/side change clears it. Removing the layer
animations settles the track without advancing `presentation_ms` or the VM.
`expression_decorations` stores the overlay `expression` (0 or 6–9), its
`elapsed_ms:int[0..2150]`, and independent `flash_ms:int[0..1300]`. New ordinary
expressions leave these tracks running, and pausing IPA playback settles them.
Versions 1–24 derive only the fade/effect progress already present in their
saved line, preserving VM, random state and last-expression bytes. They do
not reconstruct unknown earlier transitions. Older runtimes cannot read
version-25 saves. See [expression lifecycle](UI_FIDELITY.md#delayed-expressions-and-panel-reuse).

Version 26 reflows older IPA dialogue pages with the original italic emphasis
font's advances and semicolon punctuation. It retains `page_start`, validates
the saved speaker-font banks, and recomputes only `page_end`; VM state, random
state and reveal/expression clocks do not advance. Versions before 15 retain
their existing missing-name-history migration. Current IPA pages and APK
version-10+ pages still require an exact saved end. The schema adds no fields;
the version distinguishes pagination computed with the corrected metrics.
Older runtimes cannot read version-26 saves. See [IPA dialogue](IPA.md#dialogue-text-placement).

The `vm` object contains `pc`, `sp`, `fp`, `a`, `b`, `result`, `data`, `stack`,
`pending`, `steps_executed`, `opcode_counts`, and `recent_pcs`.

- Memory/register words are signed 16-bit integers or JSON null for
  uninitialized storage. Null must not be changed to zero on load.
- `stack` contains **all allocated cells**, including cells above SP. Popped
  values remain addressable by native scripts. `data` includes the mutable
  initialized words and gap cells, not just changes to the original script.
- `vm.pending` is null or `{kind, pc, byte_offset, yield_id, args}`. Its PC is the
  issuing instruction; `vm.pc` is already advanced for a yield or pause and
  remains on the HALT instruction for a halt. Pending argument words remain
  in the stack until the callback completes. Service 91 with a zero wait value
  is an application gate after an already completed call: its loading screen
  has `vm.pending=null`. Empty service-91 frames read their wait flag from
  retained backing at SP; they do not default to zero. Completed compact calls
  recover argc from bytecode; register-count calls with argc other than 1
  preserve it in the pending loading screen's `details.argument_count`.
  Services 7/63 instead retain their final yield as a terminal audit record;
  no callback or subsequent instruction is permitted.
- `opcode_counts` and numeric engine map keys use decimal strings as JSON
  object keys. They are restored to integer keys in memory.
- `engine` includes numeric/string variables, names and art variants, expression
  bytes, all 11 dynamic string slots, 10 optional result words, UI defaults,
  scheduled `(script_id, flag)` records, panel presentation, audio requests,
  last input, and any choice under construction. A text-input draft is retained
  in its pending screen details when saving from the desktop and validated as
  a string on load. It becomes script-visible only after valid confirmation;
  input alerts, keyboard visibility, and cursor phase are not serialized.

The panel additionally stores `presentation_mode` (native modes 1–4, or 0
before setup), `theme`, and `emphasis_theme` (last ordinary theme-1/2 backtick
palette). `mode` is still the separate script text-decoration prefix.
A pending dialogue includes the requested `character_id`, `visible_character_id`,
visible `speaker`, `expression`, raw/displayed text, those mode/palette fields,
and `page_start` / `page_end`, as Latin-1 source-byte offsets. The VM stays
suspended while these offsets advance. Page layout is derived from the same
user-supplied library and selected fonts; current-version saved page extents
are checked on load.
The pending `speaker` precedes the native display-spacing rewrites; the panel's
retained `speaker` includes them. Neither changes the character's stored name.

Version-1 saves are migrated without executing the pending VM instruction or
replaying choices. Pending dialogue is reconstructed from its raw text and
configured character IDs, fixing old visible narrator names and thought text.
It starts on page zero because version 1 stored no page position. Historical
font state absent from version 1 starts with the initial palette, then applies
the current dialogue theme. Unknown save versions are rejected.

Version 3 adds `random48`, `random`, `word_game`, `football`, `football_scores`,
`word_grid`, `grid_tutorials_seen`, `sound_ids`, and queued/active dialogue notice
state. Game fields include generated choices/boards/targets, score, consumed
starts, pointer selection, phases, timers and sound requests. Both random
generator states are integers. Games are restored without consuming randomness;
their typed fields and correspondence to the pending VM request are validated.
See [MINIGAMES.md](MINIGAMES.md#7-saves-verification-and-remaining-fidelity-work).
Version 1/2 saves receive defaults for these fields. If their retained stop is
service 71, 94 or 96, the game is initialized from that original frame; missing
historical random state cannot be reconstructed.

The optional `pending.details.minigame_started` boolean records choosing Play
at an enabled minigame-skip prompt; older saves infer entry from their existing
game clocks/phases. It applies to that pending call only. `Session.start_minigame()`
records this choice, `tick(..., pause_minigame=True)` holds a minigame while its
entry prompt is visible, and `skip_minigame(success: bool)` uses the implemented
game's completion callback. Ordinary choices and unsupported services are never
skippable. See [the explicit cheat policy](MINIGAMES.md#optional-minigame-skips)
for script-visible outcomes. The frontend preference is separate from the save.

Service-88 notices derive their letter motion from the existing remaining
`notice_ms` countdown, independently of the dialogue reveal clock. Its native
upper bound is `165*(len(notice)+1)+300` for nonempty text, zero otherwise.
Older notice saves retain their remaining time and VM state. No fields were
added for this rendering correction. See the
[notification contract](STORY_SERVICES.md#dialogue-notifications-service-88).

Version 4 adds `dialogue_animation`: the current and outgoing portrait identities,
speaker/page transition flags, active elapsed time, source-index reveal counter,
completion flag and pending fast-completion state. The field is required on a
pending dialogue, can survive a VM pause, and is null on other presented screen
types. See the field schema and native timing evidence in
[UI_FIDELITY.md](UI_FIDELITY.md#dialogue-transitions-and-reveal-scheduler).
Version-1/2/3 dialogue saves migrate with the current page fully revealed and
its entrance settled, preserving their previous immediately visible behavior.
They retain the saved VM frame and, for version 2/3, the page offset.

Version 5 adds `character_picker`, `scene_badge`, `next_dialogue_wobble`, and dialogue animation `wobble_direction`. These hold copied character IDs, their index permutation, per-portrait 50 ms motions, the 200 ms scene-label entrance, and the next dialogue rotation. The complete typed field schema is in [STORY_SERVICES.md](STORY_SERVICES.md#save-schema-additions-version-5). Older saves receive null/false/zero defaults; a retained unsupported service-78 frame upgrades to a working selector without replaying earlier choices. Existing dialogue checkpoints retain their progress.

For portrait selection, click and release a portrait, then click the checkmark. Keys 1–5 select the original portrait index, Left / Right the previous / next one; Enter/Space confirms. `Session.answer(index)` selects without completing, and `Session.answer()` confirms. Animation freezes while paused or unfocused.

Version 6 adds the service-91 loading gate and relationship indicator animation
state. A loading screen continues automatically only when active time exceeds
3000 ms; a click cannot dismiss it. NPC icon/count changes write the original
cache keys, play the native sound, and add their original dialogue delay.
Older unsupported service-91 saves enter the recovered screen; old dialogue
checkpoints acquire settled icons without losing reveal/page progress. See
[STORY_SERVICES.md](STORY_SERVICES.md#save-schema-additions-version-6) for the
fields, validation and migration rules.

Version 7 adds `visual_ms`, `board_entry_ms`, `banner` and `transition` to the word-grid state.
They preserve active decorative time, the banner's entrance/hold clock, and
outgoing letters during board transitions. The renderer uses the original
atlas fonts and instruction panel geometry without mutating the VM or game.
Earlier grid saves keep their exact board, score, selection and random state;
missing decorative history starts at zero/null. See
[GRID_UI.md](GRID_UI.md#saved-presentation-and-verification) for the typed schema.

Version 8 adds football's `visual_ms`, `camera_position`, `hud_position`,
`message_ids`, `message_values`, `message_hold_ms` and `effects`. These retain
the moving field, localized message sequence and selected-play animation.
Older football saves preserve recorded text, timers, scores, VM and random
state; missing camera history starts at the saved field position and outgoing
effects start empty. See [FOOTBALL_UI.md](FOOTBALL_UI.md#saved-presentation-and-verification).

Version 9 adds `message_panel`, holding service 33's raw title/body, retained
third argument and active reading time. Older saves gain a null field; saves
paused at unsupported service 33 enter its recovered Instructions/message
screen without replaying earlier inputs. Panel text and arguments are checked
against the pending VM call, and restored clocks do not restart. See
[STORY_SERVICES.md](STORY_SERVICES.md#saves-and-verification-version-9).

Version 10 adds `engine.speaker_names`. Native name labels retain layout inputs
between dialogues, so treating this state as a disposable renderer cache could
change the next name's placement or large-name branch after restoring a save.

| Field | Type / contract |
| --- | --- |
| `fonts` | Map from font name to the state after the current name layout |
| `basis` | Null before layout, otherwise the font-state map immediately before the current dialogue |
| Map keys | Only `PajamaHip26`, `PajamaHipY26`, `PajamaHip266`, `PajamaHipG26`; absent keys use initial state |
| Per-font `width`, `height` | Integer content dimensions, 0–65535; initially 0 |
| Per-font `gap` | Integer -16 initially, or 8 after the native large-name branch |
| Per-font `lines` | Integer previous line count, 0–65535; initially 1 |
| Per-font `indents` | Integer list `[]`, `[0,5]` or `[0,20]`; initially empty |

Layout advances `fonts` once when presenting a dialogue. Redraws and page
turns work from a copy of `basis`; they never advance that history. A version-10
pending dialogue with asset layout requires a non-null basis. Loading replays
only the pure name layout on that copy and checks its resulting bank against
`fonts`, along with the page extent. This does not execute any VM instructions.
Both banks survive panel close; they are fresh for a new episode session.

Versions 1–9 have no saved name-font history. Migration initializes it and
applies the current name once. Versions 2–9 retain their saved `page_start`
and reflow the remaining page; version 1 still starts at zero as described
above. Saved VM frames, previous choices, random streams and reveal clocks
are not replayed or restarted. No APK/episode reimport is needed. The generic
ink-bounds correction is derived drawing data, never serialized back into the
native font state. Bounding speaker ink to the selected normal/tall header
therefore does not itself change font history or page extents. Game-specific
text colors likewise affect only drawing. Version 16 additionally corrects
outline-font measurement and body regions, which can change IPA page ends.
See the recovered rules and explicit compatibility limit in
[UI_FIDELITY.md](UI_FIDELITY.md#speaker-labels-and-persistent-font-state).

Version 11 adds `engine.title_screen`, holding service 8's active `elapsed_ms`
(0–4000), horizontal `reveal_width` (0–320) and boolean `ready` input gate.
It is non-null exactly while a title presentation is pending. Width, gate,
resolved strings and asset/flag fields are validated against the clock and
retained VM frame. Older title saves migrate to a fully revealed, settled
screen without replaying the VM or consuming randomness. Current saves retain
the exact entrance phase. See [TITLE_SCREENS.md](TITLE_SCREENS.md#save-schema-version-11)
for the field constraints, early-tap state and shared completion side effects.

Version 12 adds the terminal `episode_exit` action for services 7/63, with
empty details, a validated final VM yield frame and cleared scene state.
Older unsupported stops recover by dispatching only that retained call.
The application returns to its main menu and writes a terminal automatic
checkpoint that masks older Resume entries while preserving the manual slot.
A subsequent play starts fresh; explicit manual Load remains available.
Terminal scene checks, persistence behavior and the native/reset-memory
boundary are specified in [STORY_SERVICES.md](STORY_SERVICES.md#save-schema-version-12).

Version 13 adds `survey_confirmation` for supported service-9 submissions.
The pending details contain only the verified `response_pc`; the original
submission frame remains suspended. The existing `engine.message_panel`
stores the local thank-you receipt and its active reading time (0–1000 ms).
Loading validates the upload type, exact receipt, response PC and original
script's not-uploaded branch without changing live VM state. Older unsupported
service-9 saves enter this confirmation without replaying questions or sending
answers. Acknowledgement executes the verified branch and its dialogue callback
once, then continues the remaining story. It does not mark the episode ended;
only the script's original services 7/63 do that. See the
[offline survey contract](STORY_SERVICES.md#offline-surveys-service-9).

Version 14 introduced a separate IPA dialogue layout, since superseded by the
owner's shared v0.1.3 presentation reference. It added no fields; its IPA
checkpoints stored empty `fonts` and `basis` maps and reflowed older IPA pages.

Version 15 restores the shared dialogue layout and speaker-font history for
both games and package types. No fields are added. Older IPA dialogue saves
preserve `page_start`, VM state and reveal clocks, then derive `page_end`
once using the shared layout. The current speaker is prepared from the saved
`basis` for pre-v14 checkpoints, preventing the name from advancing twice.
Version-14 IPA saves have no earlier speaker history to recover, so migration
initializes it and prepares the current name once. It never executes the
pending VM call. Current-version pages and font history remain strictly
validated; APK saves from version 10 onward retain their strict checks too.
Version 16 uses verified CSFont title wrapping and ordinary body metrics
within the shared renderer. The title's 8/40-pixel extension is no longer
counted as IPA body capacity. No JSON fields are added. Version-15 IPA saves
keep both name-history banks and validate them normally; only `page_end` is
recomputed from the retained `page_start`. Pre-v15 IPA saves also use the
earlier history migration above. VM memory, pending arguments, random state,
panel state and animation clocks remain unchanged. Version-16 page ends are
strictly validated; APK version-10+ validation is unchanged.
Upstream accepts versions 1–15 and the legacy `shs-runtime-save` marker; this fork accepts `shs-runtime-save` 1–23.
See [IPA dialogue](IPA.md#dialogue-text-placement) for geometry and font limits.

Saves stopped at unsupported service 4 now validate the retained choice builder
and shuffle argument, then perform the native shuffle once using the saved
game random stream. No preceding script input or random draws are replayed.
An already displayed choice keeps its saved order, return mapping and timer
without reshuffling. No fields or save version change; see the
[choice contract](ENGINE_ABI.md#46-services-14-ordinary-choices).

A save retained at unsupported service 39 now completes the recovered panel
close through its validated VM frame and follows the saved script queue to
the next stop. This also applies to version-6 saves; no schema fields change.
Earlier choices and random draws are not replayed. See
[STORY_SERVICES.md](STORY_SERVICES.md#dialogue-panel-close-service-39).

Saves stopped at unsupported service 76 now enter the recovered named-dialogue
screen from their validated pending frame. The retained previous panel supplies
its outgoing portrait identity; no earlier choices, VM instructions or random
draws are replayed. Service-76 saves use the existing dialogue animation/name
fields and keep reveal/page progress. No save version changes; see the
[named-dialogue contract](STORY_SERVICES.md#named-dialogue-without-a-portrait-service-76).

Saves stopped at service 70 now complete its verified fixed queries, including
Football Star's selector 10, and execute the following bytecode without
replaying earlier progress. Selector 11 still requires unmodeled native
application identity and retains its pending frame. No save fields change;
see the [query contract](STORY_SERVICES.md#build-and-application-query-service-70).

Loading checks content identity, program identity, machine extents, field
types, and correspondence between the pending request, saved instruction, and
argument frame. It restores the suspended screen directly. It does not replay
prior script input or reapply choice side effects. Saving uses a temporary file
and atomic replacement, with one slot per episode by default.

Timers count active foreground time. Saving preserves the remaining interval;
time spent with the application closed or unfocused does not consume it. Music
pauses while the pause menu is open, the window is unfocused, or the live
episode is in the main menu. Resuming that live episode keeps the stream's
position; both focus and menu holds must clear before it resumes. Version-22
host checkpoints capture playback position and fades; older/headless saves
without that state start the requested cue at its native offset.
Implemented dialogue/title/mini-game animation clocks and modeled random streams
are serialized. Other native animation and panel-lifecycle state remains partial;
newly modeled fields will require explicit save migrations.

Version 21 leaves the story tree out of a save: `engine.dt_view` keeps `enabled`, `pending_result_index`, `awaiting_result` and `last_was_result`, `root` and `current` are null, and the current scene is `engine.dt_view.current_serial` (0 for none). `SHSDTView saveGame:` does the same (the tree is `tree_nodes.txt`, kept whatever the game); loading finds that serial in the library's own tree (`dtview_tree.json`). Older saves that embed a tree still load: the library's tree is used when it has the scene (same type and ids), the embedded one when it does not.

## Names shared across episodes

The app keeps one name-replacement table for the whole install: `SHSEntityTable`'s
renames, the `$KEY` → text pairs that every shown `$KEY` is replaced with. It
is saved in `shs_options.sav` after the catalog (`saveRenames`: a count, the
pairs, then 200 persisted-expression bytes), loaded at start, and never
cleared by a new game, an episode or a loaded save.

The scripts write it:
- Service 46 stores a key, a fixed text or one the player typed or picked.
- Service 47 reads a key, storing the script's default when it is empty (and
  saving the file at once).
- Service 113 stores a key only while `$USR` is empty.

Episodes use it to carry names forward. A series' first episode stores the
lead's typed name (`$ZOE`, `$Scott`, `$Travis`, `$CADY`…); the later ones read
it through service 47, falling back to the default only when it was never
set. Football Star stores `$USR` and `$DATE`. The portrait a player picks is
not kept: `SHSUIPortraitSelect` always starts at the first one.

This runtime keeps the table in the library's `player.json` as `names`. The
desktop shares it with every session it plays (`Session.share_names`):
- Services 46, 47 and 113 write into it, and it is saved with `player.json`
  (each checkpoint, save, episode change and exit).
- A session's own save still records the table as it stood. When a save
  loads, the shared table keeps its values and only adds keys it lacks, such
  as names typed before the table was shared.
- A warp keeps the table as it is, as the app keeps `$USR`.
- Choice previews, the episode explorer and other copied sessions never
  change it.

## Verified playback and remaining work

With the supplied local APK, the runtime executes 25001 initialization, loads
25002, and reaches service 8's opening presentation after 2,561 instructions.
After acknowledging 35 title/dialogue screens it reaches service 1 at PC 316.
Submitting options 0 and 1 reaches different original dialogue instructions at
PCs 336 and 352. Save/load at that choice preserves both possible continuations.
Continuing reaches **service 71 at PC 92**, still in scene 25002. This timed
word game is now playable, and scores 0 and 10 produce different actual script
branches. Service 88's post-game notification now continues into dialogue.
An all-first-choice route with ten positive word selections reaches service 91
at PC 60 in scene 25004. This APK-bundled call has zero arguments and reads a
retained wait value of 407. The imported `SHS_The_New_Girl.exp` passes 1 at PC 61.
Both loading gates preserve the original frame and timer across saves and
continue into the word-grid game. A route choosing Algebra when available and
spending free time alone later reaches the shuffled service-4 choice in scene
25005: PC 1465 in the bundled episode and 1478 in the imported episode.
Both recover old unsupported saves without replaying the earlier route;
each displayed option then reaches its original dialogue and mapped result.
Separate local tests
exercise the original driving-grid frame in script 25003 and the football
frame in **Big Man On Campus** without adding production script skips.

The full local import audit consumed 274 archive paths (271 external paths and
three APK members), deduplicated them to **271 distinct episodes**, and parsed
**974 distinct-episode script records**, with no import or startup exception.
Initial stops were 58 title presentations, 53 dialogue screens, 159 unsupported
service-99 calls, and one unsupported service-89 call. See
`runtime-import-audit.json`. These counts describe
initialization only, not complete episode support.
The startup audit was repeated after adding dialogue layout and pagination:
`runtime-panel-audit.json` has the same counts and
zero failures across all 271 episodes and 974 script records.

Reproduce the audit from the source checkout (the temporary imported copy is
removed afterward):

```sh
uv run --locked python tools/audit_runtime.py --apk surviving-high-school-1-0-9.apk --episodes Episodes > docs/runtime-import-audit.json
```

Use `--library /path/to/library` instead to audit an existing import.

The authored unit tests cover hostile/truncated archives, compressed aliases,
relocatable imports, wrong profiles/content, actual branch execution, scene
loads, complete saved stack/data, timers, custom choice values, text callbacks,
unsupported-service suspension, and desktop keyboard/mouse/save/load behavior.
Text tests cover the native descriptor quirks, wrapping independently of
kerning, color controls, original atlas dimensions, glyph alpha, and clipping.
Optional tests exercise the local New Girl content without packaging it as a
fixture. New checks cover image-pack transforms, mask alignment, signed layout
coordinates, configured narrator IDs, version-1 migration and saved page turns.
Choice checks cover native font/skin composition, neutral portraits, disabled
rows, long-list hit testing, resized selection, custom result mappings and menu
timer suspension. Rendering never answers a pending choice.
Dialogue checks cover delayed/progressive reveal, fast-completion taps without
VM acknowledgement, speaker swaps on either side, repeated speakers, page
delays, clock partitioning, old-save migration and mid-transition save/load.
Local rendering checks confirm intermediate portrait frames and freeze clocks
on menu pause/focus loss. A macOS Cocoa smoke check rendered 401 dialogue frames
and restored a partially revealed frame with identical pixels.
Mini-game checks cover native random vectors, word scoring, grid tutorials and
path rules, football drives and overtime, callbacks, saved random replay,
malformed state and original sprites. Desktop tests exercise each game using
resized pointer coordinates, menu pause and focus loss. These checks do not
establish full equivalence to a running original game.
Run `uv run --locked python -m unittest discover -s tests`.

Remaining compatibility work includes other scene/state services, remaining
mini-game presentation and global random-state
lifetimes, linked KiWi, native
saves, grouped resources, remaining texture/composite animation formats, and
iOS/Android differences. Dialogue uses the original fonts, layout bank, box
artwork, masked portrait placement and paging. Narration hides the configured
character's name and portrait; thought prefixes add parentheses. Ordinary
choices use the supplied screenshot layout and APK artwork. Episode/week title
screens now use their original glyph fonts, layout and entrance animations.
Name-entry screens use native APK layouts, bitmap fonts, and error artwork,
with SDL keyboard input. Dialogue portraits scale in/out and
names fade while text reveals; backgrounds pan to the native speaker-side
alignment over 250 ms, with script-controlled fixed alignment and saved motion.
Basic music/SFX playback is supported. NPC relationship icons use original assets, cache writes, sounds,
gains/losses and dialogue delays. Name layout includes the native exceptions
and persistent font inputs, with a documented glyph-bounds correction for
remaining overlaps. Cross-object kerning, other widgets' shared font effects
and uncommon widget-reuse paths remain incomplete; see
[UI_FIDELITY.md](UI_FIDELITY.md). Dialogue now retains hidden portrait position,
speaker reuse, box-completion clipping and delayed expression fades across
temporary panels. Scene fades, SHS's nonvisual callback boundary and CoD music
fades are modeled. Other panel-lifecycle exceptions, Android promotional
branches and the full menu/story audio handoff are not fully reproduced.
Name entry accepts up to 16 ASCII alphanumeric characters, with the recovered
pre-append bitmap-width gate and interactive case conversion. See
[NAME_INPUT.md](NAME_INPUT.md) for keyboard controls and remaining fidelity
limits, including the mobile system keyboard and inherited UI state.

The exploratory Ren'Py exporter remains in the original research checkout
and is not included in this standalone runtime.

## Built-in Football Star extraction

The importer extracts the 22 loose APK scripts into a deterministic local EXP with native IDs 25001–25021 and 25023. Its five titles come from string-bank 13, entries 193–197; pack/episode IDs are 0/0. IPA extraction uses its 21 scripts at 25001–25021 and string-bank 12. Shared art/audio remain in the base package bank. Startup upgrades existing libraries atomically and preserves their episodes, preferences and saves. See [MAIN_MENU.md](MAIN_MENU.md#built-in-story-extraction) and [IPA.md](IPA.md).

The opening has been exercised through character creation, the first classes,
service 91 in scene 25006 at PC 1245, and the following football mini game at
PC 1270. Both halves complete through ordinary tap/tick input and the original
script returns to Howard's dialogue. This required services 0, 24, 25, 27, 28,
50, 51, 78, 82, 89, 90, 91 and 99 alongside the existing game handlers.
Extraction includes the whole story; this check does not establish full-story
playback. Earlier 271-episode audit counts above are historical and predate
these newly supported services.
