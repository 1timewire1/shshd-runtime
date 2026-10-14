# iOS app

Introduced in **v0.4.0**. The v0.3.0 release supports importing
original IPA assets on desktop; it does not include this iPhone/iPad app.

The iPhone/iPad app embeds the same `exp_runtime` Python package used on
desktop. The launcher, importers, KiWi VM, menus, layouts, pagination,
animation, input gates, timers and saves are shared. Swift provides a native
CoreGraphics canvas, CoreText fonts, Files access, touch/keyboard input,
AVAudioPlayer playback and app lifecycle handling. No original assets are
included. Users provide SHS APK/IPA or CoD IPA assets and their EXP episodes.

## Build and distribution

Use an Apple Silicon Mac, full Xcode, an installed iOS simulator runtime,
and Python 3.14. The deployment target is iOS 15.0. Dependency URLs and
SHA-256 hashes are pinned in `ios/dependencies.json`: Python 3.14.7 from
Python Apple Support and Pillow 12.3.0 from PyPI. The first build downloads
these public dependencies into ignored `build/ios/dependencies`; subsequent
builds can use `--offline`. These native iOS dependencies are separate from
the desktop dependencies pinned in `uv.lock`.

```sh
uv sync --locked --extra desktop
uv run --locked --extra desktop python tools/build_ios.py --sdk iphonesimulator
uv run --locked --extra desktop python tools/test_ios.py
uv run --locked --extra desktop python tools/build_ios.py --sdk iphoneos
uv run --locked --extra desktop python tools/package_ios.py --label development
```

The device build is `dist/ios/iphoneos/EXP Runtime.app`. Packaging produces
`dist/downloads/exp-runtime-development-ios-arm64-unsigned.ipa` and its SHA-256
checksum. The archive contains `Payload/EXP Runtime.app`. Users supply their
own signing and installation method, which must sign the app and all embedded
frameworks. Producing the unsigned artifact needs no signing credentials or
provisioning profile.

The [Builds workflow](../.github/workflows/desktop-builds.yml) calls the reusable
[iOS workflow](../.github/workflows/ios-builds.yml) alongside the desktop builds.
The iOS job runs host tests, builds and verifies the simulator app, and packages
an unsigned device build on an arm64 macOS runner. Its `ios-arm64-unsigned`
artifact contains only the IPA and checksum; `ios-simulator-verification`
contains the verification report. The standalone **iOS builds** workflow can
also be run manually for development artifacts.

For version tags, the release job waits for all desktop builds and iOS
verification, checks all five downloads and their checksums, and attaches the
IPA and checksum directly to the GitHub Release alongside desktop downloads.
Simulator reports remain Actions artifacts. Users handle signing and installation.
For a release made before this workflow change, see
[adding the missing IPA](DISTRIBUTION.md#adding-an-ipa-to-an-existing-release).

## Install from Xcode

1. Run `uv sync --locked --extra desktop`, then prepare the device dependencies:
   `uv run --locked --extra desktop python tools/build_ios.py --sdk iphoneos --prepare`.
2. Copy `ios/Signing.local.xcconfig.example` to `ios/Signing.local.xcconfig`
   if the local file does not exist. Uncomment `DEVELOPMENT_TEAM` and replace
   the example with your Apple Team ID. Uncomment and set
   `PRODUCT_BUNDLE_IDENTIFIER` if your team needs a unique bundle identifier.
3. Open `ios/EXPRuntime.xcodeproj` and select the **EXPRuntime** target.
   Both Debug and Release read the local configuration; automatic signing is enabled.
4. Select your connected iPhone or iPad as the destination and run the app.
   Enable Developer Mode on the device if Xcode requests it.

Keep personal settings in `Signing.local.xcconfig`, which is ignored by Git
and excluded from source distributions. Changing the Team or Bundle Identifier
directly in Xcode can write an override into the shared `project.pbxproj`;
edit the local file instead. Xcode user state, exported signing keys/profiles,
DerivedData and archives are also ignored.

The build phase signs the embedded Python/Pillow frameworks with Xcode's
selected identity during a signed build. The command-line artifact build
explicitly disables signing, clears the team and uses `org.expruntime.player`,
so local team and bundle settings do not enter unsigned artifacts.
The build phase uses `.venv/bin/python` by default;
`EXP_BUILD_PYTHON` can select another Python 3.14 host with the desktop extra.

For a simulator destination, prepare its dependencies with
`--sdk iphonesimulator --prepare` first. The two Pillow wheels are different;
one cannot substitute for the other.

## Use the app

Choose a game, then **Choose Game** to import that game's APK or IPA through
Files. Multiple selection lets SHS users choose an IPA and its optional APK
asset supplement together. IPA assets take precedence. Each game keeps a
separate content library and progress.

**Options → Update checks** controls the automatic GitHub release check at
launch. It defaults to On and is shared by both games, including the chooser's
Options screen. A newer release shows “Update available. Download here.” with
Yes/No controls. Yes opens its release page in the browser; signing and
installation remain manual. The check runs asynchronously through iOS
`URLSession`; shared Python handles versions, settings and the prompt. Offline
launches continue normally, and prompts wait until a menu if a story is active.

File selection accepts the broad `UTType.item` type, including opaque files
whose provider has not yet identified an IPA/EXP/ZIP/RAR. The shared importer
validates extensions and archive contents after selection. Open Library still
filters for folders. This addresses first-open graying reported with the CoD
IPA; cold picker behavior across physical-device providers remains a manual
check.

**Options → Add Episodes** accepts EXP files, ZIP/RAR collections, episode folders
and the selected game's catalog file. Choose an archive directly in Files; its
subfolders are scanned for EXPs and the selected game's catalog. Imported
episodes persist in the app's library after closing or relaunching, and the
source archive is not needed afterward. Existing episodes and saved progress are
preserved when the same collection is imported again. RAR4/RAR5 use the iOS
system libarchive, without a separate app or command-line extractor. See
[archive limits](RUNTIME.md#episode-archives) for unsupported variants.

The catalog reader, duplicate detection, title languages and sorting are
shared with desktop. **Open Library** copies a selected library folder into
the app before opening it; the source remains
intact. Imports use a worker and the shared atomic publication rules.

Tap to continue or choose an option. Swipe to scroll episode lists and long
choices. Name entry uses the iOS keyboard and the same native validation as
desktop. The lower-left game control opens the original pause menu with Resume,
Options, Help & About and Main Menu. Manual Save/Load is in paused Options.
**Options → Cheats → Choice hints** optionally marks recognized score and
relationship effects, classroom and timed word answers, and short sequences
with deferred rewards. Uncertain consequences remain unmarked. Pause rows and
choice options highlight under a held finger; releasing on the same row
activates it and dragging away cancels. Pause rows preserve the skin's side borders.
Leaving the app pauses story clocks/audio and checkpoints
progress. Returning resumes the existing session; Play/Resume also restores
saved progress after a later launch.

Both games play their supplied main-menu theme. Menu and story music have
independent native players, so returning to the menu preserves the paused
story stream. Music settings and background pauses apply to both. Native
prepare/start/resume failures are reported instead of silently ignored.
Story music honors service 80's repeat flag; one-shot cues remain one-shot,
including CoD's native main-menu theme. Both audio backends use this policy.
Portrait-speaker dialogue boxes use the original iOS 120+200 ms entrance
in shared Python, with fixed-size borders and saved active-time progress.
See [animation parity limits](UI_FIDELITY.md#ios-dialogue-box-entrance).
Dialogue shows each game's original Continue tab after text finishes; the
shared 250 ms visual clock pauses and saves with the story. The bottom footer
also shows the original continuation instruction. Glyph rounding keeps one
consistent baseline when a centered line starts at a half pixel.

Animated sprite scales are native CoreGraphics commands referencing cached
source images. Football no longer resizes and PNG-encodes those images for
every frame in Python. SHS's score strip uses its supplied 15-pixel bitmap
font and original composite geometry; the play clocks/rules are unchanged.
Word-grid tiles use shared solid cube geometry and cached face artwork.
Each visible face sends one perspective-texture operation; Swift samples the
texture with the supplied inverse map. Camera, animation, depth ordering and
hit geometry remain in Python. Flat arrows retain the batched scanline path.
Successful words scatter the supplied fragments and pop the tiles back in;
these effects pause and save with the game. Timed word
choices use the same cached sprite scales and glyph rounding as ordinary choices.

The game's surrounding safe areas and letterboxing are black. CoD menu clicks
use its original sound, controlled by Sound separately from Music. The main
menu's fourth button is **Switch Game**, in the original lettering and style;
it checkpoints progress and opens the other imported game, or the chooser if
that game is absent. Tap the info
icon for Help/About, including the EXP Runtime version and a GitHub project
button that opens the system browser.

Libraries and saves live under **On My iPhone → EXP Runtime → EXP Runtime**
in Files. Library locations are relative to this directory so an app-container
UUID change does not invalidate them. Serialized iOS paths use forward slashes
on every host, including Windows tests. IPA font lookup uses the original bundled
font when present, then the named iOS system face, then the system default.
Android bitmap fonts retain their existing layout path.
The global update preference lives in `settings.json` alongside the libraries
and survives ordinary app relaunches and game switches.

## Verification

`tools/test_ios.py` creates its own temporary simulator, installs the app,
launches `--self-test`, and reads the result from its app container. It shuts
down and deletes only that simulator afterward. The report records the actual
iOS/Python/Pillow versions in `build/ios/verification-simulator.json`.
`build/ios/verification-window.png` captures the full phone screen, including
safe areas and letterboxing, for visual inspection.

Simulator boot defaults to a five-minute limit, configurable with
`--boot-timeout SECONDS`; CI allows ten minutes for a cold boot. The runner
prints the selected available runtime/device, relays `bootstatus` boot and
data-migration output, and prints elapsed time every 30 seconds while waiting.
It must finish booting successfully before the app is installed. Installation
has its own five-minute limit, configurable with `--install-timeout SECONDS`,
and streams any installer output with progress every 30 seconds. CI explicitly
allows five minutes for installation. A failed or timed-out install prevents
launch; it is never accepted as a successful verification. App startup
and self-tests then have their own five-minute limit, configurable with
`--timeout SECONDS`. The runner attaches to the app's console while watching
for its final report and prints progress during the wait. An early exit, failed
report or expired deadline still fails verification. Cleanup attempts termination,
shutdown and deletion without replacing the original failure if another
simulator command hangs.

Boot, installation and app console output stay in `boot.log`, `install.log`
and `launch.log` under
`build/ios/simulator-diagnostics/<device-id>/`, alongside selected-device
metadata. The parent directory also retains the installed runtime inventory.
On failure, the runner also saves available app reports, simulator logs
(including installation services) and a screenshot before cleanup. The iOS
workflow uploads this directory as the
`ios-simulator-diagnostics` artifact when verification fails. Optional original
content checks remain local; CI diagnostic uploads use only authored fixtures.

The authored checks require no original content and cover:

- Pillow image decoding and the embedded native extensions.
- LZMA EXP parsing and real KiWi execution under both game profiles.
- Compressed episode ZIPs, subfolders and macOS metadata filtering.
- Authored RAR4/RAR5 collections decoded by the iOS system library.
- Timed choices, exact expiry boundaries, atomic saves and identical restores.
- Unknown services retaining their actual pending arguments across saves.
- The shared game chooser, touch hit regions and native Files-picker requests.
- Native system-font lookup/fallback, font metrics and glyph atlas rendering.
- Native pixels for image orientation, clipping, scaling, rotation, alpha and
  perspective-texture sampling.
- Real AVAudioPlayer playback with authored silent PCM, independent menu/story
  players, pause and resume. Optional original imports also assert that the
  supplied main-menu MP3, pause-opening sound and menu clicks are playing.
- Embedded runtime version metadata and the Help/About project-link handoff.
- Offline update fixtures, saved opt-out and Yes/No prompt actions. Verification
  never makes a live release request or opens the release page.

Optional local checks import supplied originals into that disposable simulator,
play the opening story through the shared renderer, and exercise pauses,
choice-hint settings and checkpoint/manual saves. SHS additionally renders an
authored football scenario with the supplied artwork and scoreboard.
Both timed word choices and a 5×5 word grid are also rendered using authored
scripts and the supplied SHS assets, checking that their pending VM remains held.
These checks cover the held gear highlight, pause expansion/input gate, pause
sounds and held/canceled rows in both games, quiz hint colors, choice release,
solid tile flips, fragments and in-flight grid restoration. Football Star's
opening scene also verifies the badge text inside its native region; its
original classroom quiz checks answer colors without advancing the live quiz.
Both games also render the update prompt using their original menu skin, verify
the held Yes button, and check the browser handoff without opening Safari.

```sh
uv run --locked --extra desktop python tools/test_ios.py \
  --content shs /path/to/SHS.ipa --content cod /path/to/CoD.ipa
```

Repeat `--content` to test an SHS APK too. These archives stay in simulator
Documents; they are never added to the app or distribution. Optional screenshots
stay in ignored `build/ios/content-verification`. Reports contain check names,
not script text. Diagnostic libraries are isolated from the player's libraries.

To run the same authored checks on a phone, add `--self-test` to the Xcode
scheme's launch arguments. Reports appear in the app's Documents as
`ios-verification.json` and `ios-presentation-verification.json`. Remove the
argument for normal play. Physical-device testing and external IPA signing
remain separate from simulator verification.

The engine remains experimental: unsupported game services stop explicitly,
as on desktop. Shared layout and clocks do not imply identical rasterization;
CoreGraphics interpolation/antialiasing can differ from SDL, and CoreText can
differ from desktop FreeType. Device keyboard, document providers, audio routes
and performance still need physical-device testing.

## Implementation boundary

`graphics.py` selects drawing/platform primitives before the shared application
loads. Desktop delegates to pygame. `platforms/drawing.py` records immutable
image layers and draw commands, retaining only the reachable frame graph in
Swift. Pillow handles asset decoding and the shared mask/tint operations; whole
frames are drawn natively. The existing `desktop*.py` renderers remain the single
source for game layout and hit testing. There is no separate iOS dialogue skin.

`platforms/ios.py` processes events and advances `Application` on one serial
engine queue. A small Objective-C bridge acquires the GIL for each operation
and releases it while idle. Native font callbacks supply glyphs and metrics;
font roles and colors stay in Python. User-selected files are data and cannot
supply Python modules or native extensions. JIT is not enabled.

The build merges the authored `exp_runtime` namespace from the five component
source directories, checking that no files overlap. It uses the same Python
code as pip installs and desktop builds. Native Python extensions become
individual frameworks using CPython's `.fwork` loader. Packaging audits every
binary's arm64 iPhone platform, absence of signatures/provisioning material,
loader references and the same original-content exclusions as desktop.
IPA entries use explicit Unix modes: 0755 for the audited app/framework
executables and 0644 for resources, independently of host filesystem modes.

References: [CPython on iOS](https://docs.python.org/3/using/ios.html),
[Python Apple Support](https://github.com/beeware/Python-Apple-support),
[Core Text](https://developer.apple.com/documentation/CoreText).
