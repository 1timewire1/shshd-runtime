# Main menu and desktop application contract

Reference: SHS Android 1.0.9, `libshs09.so`, SHA-256
`b17aa4c71bc46666d414cafae6fac92bbcd755f3dcccd73975cf05f4a119665b`.
Addresses below refer to that loaded binary. The Android interface is the
working reference for the shared interface described by the user.

SHSHD Runtime first presents an asset-free game chooser (or, on a first launch, Bulk Import). SHS and CoD each open
their own validated library and game menu; the SHS evidence below does not
establish complete CoD presentation parity. [COD.md](COD.md) records its bindings.

## 1. Native application states and commands

The main menu is outside the KiWi VM. `FUN_00090818` switches application
states; `FUN_000de258` handles its buttons. These commands are **not** script
yield IDs and must never be fed into the engine-service dispatcher.

| Native state | Meaning | Native constructor/setup |
| --- | --- | --- |
| 101 / `0x65` | Main menu, input enabled | `000861c0`, `000deac4` |
| 110 / `0x6e` | Play/Resume selection | `0007ad74` |
| 111 / `0x6f` | Options | `00076c7c` |
| 112 / `0x70` | Help/About | `0006ee04` |
| 105 / `0x69` | Episodes on demand/network listing | `00090818` |
| 107 / `0x6b` | Weekly episode/network listing | `00090818` |

| Button tag | Native action | String-bank ID | Desktop action |
| --- | --- | --- | --- |
| 10002 | Play/Resume | 125; 126 if a save exists | All installed episodes, with saved-progress indicators |
| 10004 | NowAiring | 127 | Locally imported episode list |
| 10003 | OnDemand | 91 | All local episodes |
| 10005 | MoreGames | 252 or 253, depending on ad state | Switch Game; checkpoint progress and open the other installed game, or the chooser if absent |
| 1006 | Options | Gear artwork | Music/Sound, update checks, episode title language and library controls |
| 10007 | Help/About | Info artwork | Player controls, runtime version and GitHub project link |
| 10008 | DisableAds | 300 | Omitted; no advertising or purchase system |

`0008cfe4` checks native save availability; `0008ce68` distinguishes the New
Girl save from the current expansion save. Native save formats are not read by
the compatible runtime. The native analytics names and visible English labels
differ: string 127 is "Weekly Free Episode", and 91 is "More Episodes".
Native labels are loaded from the player's APK, not embedded as copied game
data. The fourth button is the authored **Switch Game** action; it retains
the original 533 glyph font, artwork, placement and entrance/pressed states.
Help/About displays the installed SHSHD Runtime version, independently of the
imported game's version. Its GitHub button opens the configured public project
URL in the system browser only when selected, on desktop and iOS.

Native button handling rejects input during a transition and unless the
application is in the main-menu state. Selection feedback uses sound 8010.
CoD uses its own verified sound 8005; see [COD.md](COD.md). The shared menu
reads the click from the selected game's base bank and respects Sound separately
from Music. It never substitutes the other game's identically numbered asset.
Native network listings refer to server-provided episode/ad configuration.
The desktop lists the user's own EXP files instead; it neither contacts those
servers nor pretends that a local episode is the latest weekly release.

### Runtime update check

This fork asks its own repository's releases (`app_info.UPDATE_REPOSITORY`,
`1timewire1/shshd-runtime`), never upstream's, which are a different program.
A release tag must be a plain version newer than the running one, such as
`v1.0.1` or `1.0.1` (the running version is the packages' own, 1.0.0 at the
first release).

On each application launch, the shared application checks the project's
[latest public release](https://docs.github.com/en/rest/releases/releases#get-the-latest-release)
on GitHub. This is a runtime feature, separate from the original games'
episode servers. It fetches release metadata without authentication or any
game files, saves or player identifiers in the request. Numeric version
comparison ignores older, equal, draft, prerelease and malformed releases.
Unknown development versions skip the check. Network failures and rate limits
do not show an error or delay startup/shutdown.

**In the HD menus** (both games) the switch is **Options → General → Check for
Updates**, on the main menu only. The offer is an HD card, "Update Available",
with No and Yes, drawn with the game's own footer buttons, over the launch's
loading screen, before "Play with sound?" (owner, 2026-10-15). The launch waits
up to `UPDATE_WAIT` (2.5 s) past the loading screen for the check, which
usually answers during it. An answer arriving later, or a launch that skipped
the loading screen (a game switch), waits for the main menu with no window,
Options card or fade over it. Escape, Enter and Space mean No; only a click on
Yes acts.

**The offer's text and Yes** (owner, 2026-10-15; `updates.update_message`):
- **Desktop:** "SHSHD Runtime x.y.z is available. Would you like to update?
  (Clicking Yes will close the game and open your browser)". Yes opens the
  release page in the system browser, then closes the game the way its window's
  close button does (`Application.quit_requested`; `close()` checkpoints as
  usual). Nothing is downloaded, installed or restarted.
- **iOS** (`platforms/ios.Host` passes `can_quit=False`): an app cannot update
  or quit itself there, and a new build is signed and installed from a
  computer. So the offer only informs ("... To update, download the new IPA
  from the release page on a computer, then sign and install it.") with one
  **OK**, which carries on.

**Options → Update checks** defaults to On. It is accessible from the game
chooser even before importing assets and persists in the app's `settings.json`,
outside either game's library. Turning it off prevents checks on later launches
and ignores an already pending response. Re-enabling it starts a check if none
has run during this launch; switching games or returning from the background
does not repeat it. Automated verification and smoke tests disable live checks.

A newer release shows **Update available. Download here.** at the chooser,
import setup or main menu. A result arriving during play, an import, a transition
or another alert waits until a menu is ready. **No** dismisses the offer for this
launch; **Yes** opens that release's page on the configured project in the system
browser. Nothing is downloaded or installed by the runtime. Keyboard Escape and
the initial Enter selection mean No. Pointer presses cannot pass through the
modal or carry over from a covered button.

With game assets loaded, the prompt uses the original two-button menu skin:
header 33, footer 39 and orange normal/held button layouts 72/73. SHS iOS
`SHSWidgetMenu::generateNewMenu` (`000a2f80`) and `finalizeMenu` (`000a4b84`)
confirm those widgets; the footer's flattened nodes 3/4 place the left/right
buttons (nodes 1/2 draw its background and separator). Yes/No labels come
from each game's string bank (SHS 25/26, CoD 24/25). This new message's title,
height and placement are a runtime adaptation, not a reconstructed original
update service. Before loading game assets, the launcher's authored fallback
provides the same Yes/No actions.

Desktop HTTPS runs in a daemon worker with verified system certificate trust;
iOS uses an ephemeral `URLSession` and sends the result to shared Python. The
version check, preference, message, rendering and input rules remain shared.
Requests use an eight-second timeout and responses over 1 MiB are ignored.
The browser destination is constructed from the project and validated release
tag, rather than an arbitrary URL or message in downloaded metadata.

## 2. Artwork and layout

All menu resources are read directly from the **APK bank**, before any episode
is opened. This avoids requiring an arbitrary episode to render application UI.

| Resource | Use |
| --- | --- |
| 6 | 320 × 480 wooden background |
| 7 | 303 × 104 title logo |
| 8 | 336 × 69 dark ribbon |
| 9 | 477 × 398 character photograph |
| 13 | Byte-string bank |
| 14 | Layout bank |
| 16 (`16.mp3`) | Episode rows, navigation icons, blue/orange buttons |
| 126 | Common UI art |
| 204 | Blue window border |
| 272 | Gold menu-button pack, background wedge, gear and info icons |
| 532 / 533 | Embedded menu glyph fonts; 532 used for main labels |

`000dfde8` loads 272 and binds it to layout image slot 5. Layout 74 describes
the 275 × 135 menu group. Layout 79 supplies its 109px-high backdrop;
75/77 are normal/pressed three-piece gold buttons. `000e0988` independently
constructs the four live buttons from 75/77. The default width is **184px**;
it is not the 205px placeholder width found by flattening layout 74.

`000df488` sets the staggered horizontal destinations. `00147df8` centers
four 28px-high buttons vertically with 5px gaps. With the ad-free fourth
button width 155, the reconstructed top-left rectangles, rounded to pixels,
are `(14,344,184,28)`, `(40,378,184,28)`, `(26,410,184,28)` and
`(13,444,155,28)`. `menu.main_button_rects()` derives them from the APK's
layout dimensions and these native placement operations. Half-pixel origins
are rounded at rasterization. The gear and info controls occupy the lower
right corner. The desktop uses the ad-free arrangement.

`000df868` centers the background/photo at logical `(160,240)`;
`000dfa48` centers the title/ribbon at GL `(160,384)`, or top-origin y=96.
The title ribbon rotates -5 degrees in the native clockwise convention.
Logical rendering is 320 × 480, scaled uniformly into a resizable desktop
window with letterboxing; pointer coordinates use the inverse transform.

Native list assets recovered through `0006ca44`/`0006cf00` and layouts
62/63 supply 296 × 42 alternating episode rows, with status icons 96 (pause),
97 (replay), and 101 (play) from pack 16. Layouts 70/71 provide the blue
normal/pressed footer buttons. The desktop uses those resources with local
metadata, scrolling, and a searchable list. The native category strings retained
in the user's `shs_options.sav` or CoD's `cod_options.sav` organize the list
into collapsible sections; saved games also appear as shortcuts at the top
of Play/Resume. Headers use
original frame 76 and font registry 2. Search includes category names and
temporarily expands results. By Number / By Title sorts within sections and
remembers the choice. Default ordering uses `(pack_id, episode_id, title)`,
with bundled versions first for matching IDs and titles. Unknown categories
use numeric pack headers. Matching titles distinguish bundled and imported
versions rather than merging different EXP hashes. The complete catalog schema,
native evidence, import behavior and desktop adaptations are documented in
[EPISODE_CATALOG.md](EPISODE_CATALOG.md).

### Episode title languages

Options exposes the five EXP metadata slots in their observed order: English,
French, Italian, German and Spanish (`en`, `fr`, `it`, `de`, `es`). The language
names are read from original menu strings 118–122. The preference changes list
rows, episode detail titles, desktop captions and By Title ordering. Search
and exact episode selectors accept all five supplied titles; ambiguous matches
still require an ID. Empty/whitespace translations fall back to the English
title, then the filename if English is empty too. Repeated English titles are
displayed as supplied. Catalog grouping and content identity retain their
original keys.

This is a desktop metadata preference, not a recovered dialogue-language
switch. Inspection of the supplied Android 1.0.9 APK and iOS 1.4.2 IPA found
one 303-entry UI string bank in each (13 and 12, respectively), and no alternate
translated scene scripts. iOS `SHSEngine::getLanguageIndex` (`0003dd48`)
returns 0; `getLanguageCode` (`0003dd50`) returns English. `loadLanguageCSL`
(`0003a074`) loads resource 12, and `CSLocalizer::loadCSL` (`00013350`) reads
a single offset/string table. The language labels and some multilingual art
do not establish that a complete translation is present. Service 70 and script
resource IDs retain their verified contracts.

The extracted APK's 2,840-byte `resources.arsc` has no locale-specific resource
configurations; its string values are English launcher/connection labels.
The IPA root `Localizable.strings` is a binary plist with seven
`default_ticket_string_*` entries: EA Mobile promotional text in English,
French, Italian, German, Spanish, Korean and Chinese. It supplies no story or
game-menu translations. These observations apply to the inspected files, not
every historical regional build.

Android's supplied bitmap fonts have no accented glyphs. Menu labels which
need them use the installed Arial Rounded MT Bold face, then pygame's default
font when absent. Other menu labels retain their original bitmap metrics;
IPA's existing original-font lookup remains first. This fallback is confined
to desktop menu text. Story font/layout validation is independent of the
title-language setting. Choosing a title language preserves live sessions and existing
manual/automatic checkpoints.

## 3. Additional resource schemas

### String bank (resource 13)

All integer fields are big endian. The supported asset has this structure:

```text
version        : s32 = 1
flags          : u8  = 0
bank           : s16 = 0
string_count   : s16 = 303
offsets        : s16[string_count]  # Absolute byte offsets from file start
strings        : NUL-terminated byte strings
```

`00058de4` reads the three header fields, count, and offsets. It subtracts 9
when copying offsets into its own headerless in-memory buffer. `00058d4c`
indexes those offsets by `2 * string_id`. These strings use byte characters,
unlike EXP metadata's UTF-8 titles. Dynamic `~number~` substitutions are handled
by `00058bc4` through the application's string callback; the main-menu labels
used here are static. The parser validates all offsets and terminators. It does
not implement substitutions for unrelated strings in this bank.

### Embedded menu glyph font (532 / 533)

```text
space_width    : s8  = 5
style          : u8  = 0
tracking       : s8  = -2
glyph_count    : s16 = 88
height         : s8  = 24
character      : u8[glyph_count]
pixel_marker   : s16 = -1
image_count    : s16 = glyph_count
for each glyph:
    width      : u8
    height     : u8
    pixels     : (A,R,G,B)[width * height]
```

The character lookup and every pixel come from the asset. Lowercase labels
fall back to their uppercase glyphs; spacing uses the stored tracking. This
is a different representation from the external-atlas fonts 529/531/541 and
the named `.fnt` descriptors. `000e0988` explicitly selects 532 for the first
three labels and 533 for the fourth; the renderer follows that selection.

## 4. Lifecycle and persistence

```text
No library -> Setup -> Choose/drop APK or IPA -> Validate/copy -> Main menu
Main menu -> Play or episode list -> Episode -> Play/Resume -> Session
Session -> Pause -> Main menu -> Automatic checkpoint -> Main menu
Session -> Service 7/63 -> Terminal checkpoint -> Main menu (no Resume)
Main menu -> Options -> Add EXP files/folder -> Validate/copy -> Episode list
IPA library -> Options -> Content Library -> Add APK Music -> Validate/copy -> Library
```

The file picker is implemented inside the application, so a packaged app does
not need a terminal, Python installation, Tk, or an external file-dialog
utility. Files and whole episode folders can also be dropped onto the menu.
A multi-file SDL drop is collected into one import transaction. Parsing and
copying run on a worker; the render/event loop continues at 60 Hz.

An initial drop containing one IPA and one APK uses the IPA as the base game
and the APK only for its verified missing music. An existing IPA library also
accepts a single dropped APK or the **Add APK Music** file picker, which filters
for `.apk` files. The library panel shows the missing track count and offers
the action only while tracks are absent. Music import preserves the live story,
checkpoints and loaded audio; Resume retries a cue whose earlier load failed.
See [IPA.md](IPA.md#optional-apk-music) for asset precedence and manifest version 3.

Initial imports stage a new library and publish by directory rename.
`ContentLibrary.add_episodes()` stages and validates the entire batch before
atomically replacing `library.json`. SHA-256 deduplication preserves existing
content identities, the original inputs, and saved progress in both games.
An identical EXP imported under another filename adds a lookup alias, allowing
catalogs to name that existing entry; it does not add another episode. Only
the selected game's catalog is discovered and shown in the file picker.
A failed validation changes neither the manifest nor the content files.
A crash during the final file moves
can leave unreferenced content files, but cannot publish a half-written manifest.
Use one writer per library; a manifest change detected since opening aborts the
import. This is not a multi-process database locking protocol.

The application holds one live session. Menus and unfocused windows do not
tick its dialogue, choice or mini-game clocks. Returning through Main Menu
checkpoints it; resuming that episode reuses the live session exactly. Starting
a different episode constructs fresh renderers and image caches, preventing
episode-specific IDs from reusing the old episode's images. Unsupported VM
services remain suspended and visible to the player.

Services 7/63 end the episode, cancel its queued scripts and retire ordinary
Resume progress. The application stores a terminal automatic checkpoint,
stops audio and releases that live session. A validated terminal checkpoint
masks older saves for Resume; the manual F5 slot remains available to explicit
Load. Starting the episode again creates a fresh session. Other episodes'
progress is unchanged. A failed checkpoint retains the terminal live session
and reports the write error. See the [exit contract](STORY_SERVICES.md#episode-exit-services-7-and-63).

| File, relative to the library | Schema / behavior |
| --- | --- |
| `player.json` | `{version:1, selected:SHA256, music:bool, sound:bool, order:"episode"\|"title", title_language:"en"\|"fr"\|"it"\|"de"\|"es"}`; old files default to episode order and English titles. `names` (object of `$KEY` to string, at most 4096) is the name table every episode shares ([RUNTIME.md](RUNTIME.md#names-shared-across-episodes)) |
| `saves/<episode-sha>.shs-save.json` | Existing manual F5/F9 slot, [runtime save schema](RUNTIME.md#runtime-save-schema-version-13) |
| `saves/<episode-sha>.shs-auto.json` | Automatic checkpoint on menu return and application exit, same schema |

Preferences and saves use temporary files plus atomic replacement. Resume after
restart chooses the newer automatic/manual file, then validates its full
profile/APK/episode identity through `Session.load`. A valid terminal checkpoint
suppresses Resume rather than falling back to older progress. A bad save is reported;
it is not silently replaced by a fresh game. New Game has an in-app restart
confirmation when progress exists. Subsequent checkpoints replace the automatic
slot; the manual slot is preserved. Existing libraries without preferences use
their most recent save, or the New Girl metadata ID `(5,9)` when no save exists.

Music/Sound preferences gate playback separately from VM-visible audio state.
Leaving a live episode pauses its music stream; resuming that same session
continues from its current position. Starting another episode, restarting, or
loading a saved session instead loads its requested cue. Playback position is
not saved to disk.

The shared menu now requests the selected game's original theme: **8215**
for SHS and **8209** for CoD. Ghidra identifies these in iOS
`splashScreenFlewIn:` (SHS `0002adb0`, CoD `00014c0c`) and
`doSoundManagerTransition` (SHS `0003b44c`, CoD `00022b04`). Both supplied
IPAs contain their menu track. Playback uses a separate SDL channel on desktop
and a separate AVAudioPlayer on iOS, retaining the live story stream and
playhead while navigating the main menu. Music mute and focus/background
holds apply to the menu too. Switching games releases the old theme.
Native looping/fades and exact splash-to-theme scheduling remain unverified;
the theme currently plays once on entering the menu.

## 5. Executable and content boundary

`shshd-runtime`, `python -m exp_runtime.application`, and `shshd-tool play` launch
the game chooser. `exp-runtime` / `exp-tool` and `shs` / `shs-tool` remain command aliases. `--game shs|cod`
opens one game directly; `--library` opens a specified relocatable library.
New libraries default to per-user application data, replacing `<game>` with
`shs` or `cod`:

- macOS: `~/Library/Application Support/SHSHD Runtime/libraries/<game>`
- Windows: `%LOCALAPPDATA%/SHSHD Runtime/libraries/<game>`
- Linux: `$XDG_DATA_HOME/SHSHD Runtime/libraries/<game>`, defaulting to `~/.local/share`

This fork keeps its data under its own name, `SHSHD Runtime` (`launcher.APP_NAME`), so it is a distinct app from
upstream's EXP Runtime: neither reads, writes or remembers the other's libraries, saves or settings.

A frozen executable uses application data independently of its working directory
or extraction location. **Open Library remembers the chosen folder** in
`SHSHD Runtime/launcher.json`. Its schema is
`{version:2, libraries:{shs:absolute_path, cod:absolute_path}}`; either game
may be absent. Publication is atomic and preserves the other game's location.
Selecting a game uses its remembered library across working directories.
Upstream's folders (`EXP Runtime`, and its older `SHS Runtime` with a v1
launcher and default `library` folder) are not discovered in this fork; a
library there can be opened with Open Library. Source checkouts additionally
discover `.shs-library`. No original player files are moved or rewritten by discovery.
An explicit `--library` is a launch override and does not change the remembered
default. Imported episodes appear in Play/Resume even before they have saves.

**Options → Switch Game** checkpoints a live session before closing its library,
stops audio and discards per-game rendering caches. If the checkpoint fails,
the session stays open. The other game loads its own preferences and saves.
When the other game has no imported library, switching opens the chooser.
Setup's Back action always returns to the chooser.
Setup rejects packages/libraries belonging to the other selected game.
EXPs themselves have no reliable game marker and must be added to the correct
selected library. SHS APK supplementation is unavailable for CoD libraries.

### Pause menu and choice hints

Read-only native verification of SHS iOS `invokePauseMenu` **0003b53c** and
CoD **00024888**, plus their supplied layout banks, confirms four ordinary
rows: Resume, Options, Help & About, Main Menu. The shared renderer uses pack
16, header layout 33, alternating row colors and footer layout 36
(frames 74/79, without the list's navigation icons). Width is 302 at X 9;
height is `56 + 4*44 + 43`, vertically centered. SHS `generateNewMenu`
**000a2f80**, `solveMetrics` **000a3dc0** (assembly), iOS table row height
**0005ceb0**, and `initFonts` **0003c440** provide geometry and the rounded
28/14-point title/body fonts. Standalone desktop sessions retain their Save/Load shortcuts;
the application exposes manual slots in paused Options and via F5/F9.
Options/Help/Cheats retain the paused story, timers, RNG and audio state.

SHS `initPermanents` at **0003e8d8–0003ea28** assigns common atlas frame 49
to the gear's normal state and frame 50 to highlighted/selected states, with
touch-up-inside dispatch. The alternate frame supplies the orange glow.
The shared gear now tracks down/move/up across dialogue, choices, pickers,
title/message panels and minigames. Moving outside removes the highlight;
moving back restores it, while releasing outside or losing the panel cancels.

The supplied menu banks select entry transition **20** for Pause (SHS menu
22, CoD menu 21). `notifyNewMenu` **00045318 / 00020a0c**, including SHS
assembly **00045620–00045720**, scales the menu from **0.001** to **1** about
its center over **400 ms**, with UIKit ease-in/out (curve 0). The frontend
uses that curve and duration, with story clocks frozen and pointer input gated
until entry finishes. Dimming opacity and exit/subpage transitions retain their
previous behavior; those details are not claimed as native-equivalent.

### Menu entrances (PR #9, checked against SHS HD)

The menu data's header bytes 13 and 14 (`menu_engine.Menu.layouts`) are each
menu's entrance and exit transitions. SHS HD's `SHSEngine::notifyNewMenu`
(`00027bd0`) reads the entrance:
- **Entrance 20: zoom.** The window scales from 0.001 to 1 about its centre
  in a 0.4 s UIKit ease-in/out. These are "Play with sound?" (menu 7), the main
  menu's Help & About (15) and Options (22), and the pause menu (25). CoD's are
  the same windows (7, 14, 21 and 24).
- **Any other entrance: slide** (`00027f1a`). Examples are 16, the Options and
  Help & About pages opened from the pause menu. The new window starts one
  width to the right and moves in while the old one moves a width to the left,
  0.4 s ease-in/out, with no delay. Both kinds wait 0.4 s while a loading
  screen shows.
- **Back.** Going back runs the same slide the other way. The page categories
  this player adds (General / Sound / Data Management) slide like native pages.
  Native exits (`notifyMenuRemoved` -> `animateView` with the exit byte) are not
  decompiled, so the reverse slide is ours.
- **Music switch.** In the main menu, off fades the menu's song over 1000 ms
  (`setMusicEnabled(false)` -> `stopMusic(-1, true)`). On plays it again from
  the start (`doSoundManagerTransition`), or cancels the fade if it is still
  fading. The volume slider only sets the volume.
- **Main Menu row.** The pause card zooms back out over the main menu (ours, for
  its exit byte 21; unverified). The main menu replays its first-launch entrance from the photo
  animation on, without the EA flash or its jingle (the owner, on the device).
  CoD shows only its buttons' entrance (unverified).
- **Main menu buttons** (`desktop_main_hd.py`, decompiled in full: `animateMainMenuButtons{In,Out}`).
  - Each layer's keyframe animation begins after its delay, lasts delay + 0.35 s, and holds until key time
    delay / (delay + 0.35). So each layer moves from twice its delay, and the buttons start 0.16 s apart, not 0.08 s.
  - PR #9's 1.6x slowdown made up for that misreading. It has been replaced by the native timing.
  - The first entrance passes 1.5 s in both games (the 3.2 s used before belonged to `showUnlockedInter`).
  - Taking any main-menu option slides them out in reverse (`animateMainMenuButtonsOut(0)`): the gear shrinks, the
    info button fades, More EA Games leaves first and the wedge last. Coming in, the gear grows and the info button
    fades in (checked on the iPad).
  - An episode picker (`SHSMTXMenu`) zooms in over the menu meanwhile (`setAppMode` -> `animateView(20)`), as do
    Options and Help & About.

SHS `buttonPressed` **00050fe8** (pause branch **00051188**) plays resource
**8011**; CoD **000249d0** (branch **00024d86**) plays **8006**. Pause row
dispatch in `SHSWidgetMenu::buttonPressed` **000a5c64 / 0003fd60** plays
**8010 / 8005** after the selected action. Both sounds use the game's base
bank and Sound preference independently of Music. They do not dispatch a
story sound service or alter the saved VM/audio state. Objective-C decompilation
stops prematurely at some UIKit calls; these paths were followed in assembly
and checked against Ghidra memory without changing its analysis.

### Interface sounds

The table lists every direct `SHSSoundManager::playSound` call in SHS HD
(`000538c8`) and CoD 1.4.7 (`00046eb4`) that belongs to the interface. They
were found by a Capstone scan of both binaries for calls to it, and each
caller was read. The sounds come from the game's base bank (`ui_sound.py`).
SHS HD's own bundle holds byte-identical copies of 8004, 8007, 8009, 8010 and
8011.

| Control | SHS HD | CoD 1.4.7 | Native path |
| --- | --- | --- | --- |
| Main menu button | 8010 | 8005 | `SHSEngine::buttonPressed` |
| Pause button | 8011 | 8006 | `SHSEngine::buttonPressed`, pause branch |
| Story choice picked (ordinary, mode 1; incremental, mode 3) | 8010 | 8005 | `SHSUIMenu::handleMenuSelection` `00046138` / `0003cbc0` |
| Choice timing out | none | none | `SHSUIMenu::tick` `00046814` / `0003d298` calls `finishUI` directly |
| Menu row (pause and Options rows, Resume, Main Menu) | 8010 | 8005 | `SHSWidgetMenu::itemSelected` `0004f028` / `000436e8` |
| Menu button (back, tags 1-4) | 8010 | 8005 | `SHSWidgetMenu::buttonPressed` `0004f288` / `00043944` |
| Switches (tags 10-12) | none | none | `buttonPressed` |
| Sound switched on | 8004 | 8005 | `SHSEngine::setSoundEnabled(true, true)` `00022280` / `0001f4e4` |
| Sound FX slider | 8007 | 8005 | `sliderChanged` `0004f1cc` / `00043888`, `getToggleSoundID` |
| Music slider, while Music is on | 8009 | 8005 | `sliderChanged` |
| Portrait swap / confirm | 8013 / 8010 | 8005 / 8005 | `SHSUIPortraitSelect::touchesEnded` (`PICKER_SOUNDS`) |

How the sounds play:
- **Volume.** A volume of -1 plays at the Sound FX volume and only with Sound
  on, which covers every click.
- **Music slider.** It passes its own value instead, so its sound plays even
  with Sound off. A value of 0 plays nothing.
- **Sound switch.** Its sound stops the other effects first.
- **Slider previews** (`playFXVolumeFeedbackEffect` `0001c1e4` / `0001a8a8`)
  play only while no effect is playing, so dragging never stacks them. Ours
  counts only the interface's own effects, not the story's.
- **Scored action menu** (mode 2, the quiz) plays its answer sounds instead
  (`WORD_GAME_SOUNDS`).

Not applied:
- The Decision Tree zoom toggle (`-[SHSViewController toggleDTZ]`, 8011 and
  8017). Ours zooms with the wheel and has no such button.
- The store pages' clicks (`SHSMTXMenu`). Their stand-ins, the episode pickers,
  click as rows.

Rows and switches this player adds follow the same rule: a row clicks
(Options categories, Data Management actions, Title Language), a switch does
not.

Rows fill only the 296-pixel interior; the three-pixel sides come from frame
74. Stretching the row art across all 302 pixels covered those borders.
`SHSMenuCell::setSelected:animated:` **0005d018**, palette setup **000a2f80**,
and `tableView:didSelectRowAtIndexPath:` **0005bc24** confirm held selection
followed by release dispatch. Normal alternating RGBA colors are
`(239,239,249,239)` and `(255,242,255,239)`; selected is `(170,225,249,243)`.
Shared menu buttons use their supplied pressed artwork. Dragging off, scrolling,
losing focus, replacing a panel or redealing a timed quiz cancels the old press.

**Options → Cheats → Choice hints**, added in v0.4.0, is an
authored, opt-in per-game preference, off by default. Green marks recognized
gains/correct answers, red recognized losses/wrong answers or a
no-gain alternative when another option has a known gain, amber mixed effects.
Unresolved choices retain their original styling. It applies to ordinary
choices, including their actual randomized/custom return values. Service 71
word quizzes use the current deal's explicit good/bad weights, including bad
answers at score zero and duplicate words with different weights.

**Options → Cheats → Ask to skip mini-games** (HD Options: "Ask to Skip
Mini-Games") is another authored, opt-in preference, off by default:
- **When:** a football game or word grid waits on a narrator-styled choice
  (no portrait, the HD choice panel and its fades). Its clocks don't start
  until the choice is made.
- **The prompt:** it states the game's half, side and starting score, or the
  grid's target, time and words.
- **Win and Lose** finish the game through `Session.skip_minigame`, giving the
  script the result a real game would. Football ends 7 points over the higher
  starting score for the winning side and records that as the scores. The grid
  passes or fails.
- **Play** starts the game, and the same game is not asked again.
- **Not included:** the rapid-fire word quiz (service 71).

The preview executes isolated copies of the current session, bounded to
6,000 VM steps/48 panels per path, 16 options per decision, four decisions
including the current one, and 192 branch copies across the whole preview.
It observes relationship property 407, actually dispatched service-88
“Score Up!”/“Detective Score Up!” notices and SHS's explicit service-79 answer
feedback sounds (8007 correct / 8003 wrong). It does not infer score from
arbitrary counters or words in dialogue. When feedback is deferred, it compares
every matching sequence of later answers across the initial options. Later
questions must match by scene, instruction and enabled return values. An
option is marked better only when it is never worse on those continuations
and strictly improves at least one; equal outcomes and conflicting tradeoffs
remain unmarked. This handles multi-question thresholds such as Football
Star's Beth conversation without any episode, character or counter overrides.
Immediate recognized feedback retains the existing gain/loss/mixed colors.
Missing resources, unmatched decisions, unknown services and exhausted
budgets stay unknown. Previewing never saves, emits audio/host requests or
changes live VM state, clocks or random state. The real choice still runs the
original branch, including the ordinary Score Up animation.

Football Star's classroom questions use ordinary **service 1**, not the
service-71 timed-word minigame. Its shared quiz routine (scene25004, PC300)
shuffles the answer data and branches on the selected answer: correct plays
8007, displays confirmation and increments a local count; wrong or timeout
plays 8003. Weekly quizzes and finals call that routine. It never emits a
Score Up notice for each answer, which is why the original preview missed it.
The per-game sound bindings now establish feedback for any choice using
those cues; no scene, question, answer text or grade-counter ID is special-cased.
CoD has separate assets and does not inherit these SHS bindings. Ghidra's
Android `000a3bc8` and SHS iOS `playSound` **0004a714** confirm the resource
handoff; the original EXP establishes the correct/wrong meaning. Authored tests
cover shuffled values, muted/stale audio independence, mixed feedback, unknown
services and saves; optional replays check original APK/IPA classroom questions.

The original gray choice skin (property 651 = 3, resource 252) does contain
red/green button art, but those are native selection colors rather than an
outcome oracle. No gray-skin override is exposed.

Build on the target operating system:

```sh
uv sync --locked --extra build
uv run --locked --extra build python tools/build_desktop.py
```

The build creates `dist/desktop/SHSHD Runtime.app` on macOS and a
`dist/desktop/SHSHD Runtime` executable directory on other systems. Distribute the
whole app/directory. The build entry point is a temporary authored launcher;
LICENSE and the authored kiwi SVG logo are the only repository files explicitly
collected as data. The game chooser and window use this logo; macOS and Windows
app icons are generated from the same SVG during the build. Runtime modules,
Python, pygame/SDL, dependencies and their support files ship; **no
APK, EXP, extracted game assets, original native executable, screenshots,
decompilation, library manifest or save files ship**. Users import their data
on first launch. The same build works from a source checkout without any game
files; see [DISTRIBUTION.md](DISTRIBUTION.md). Build and inspect each platform
independently; creating the macOS app does not validate a Windows or Linux
executable. See the official
[PyInstaller build options](https://pyinstaller.org/en/stable/usage.html).

## 6. Verification boundary

The main artwork, glyphs, original button commands and static geometry are
grounded in native code/assets. Full screenshot/recording equivalence is not
yet established. Known adaptations and gaps:

- Local episode lists, search, setup, file picker, help content and library
  controls replace server/purchase/platform flows.
- Options implements audio, episode title language and content management, not all original native
  settings. Original episode preview/download details are not reconstructed.
- Entrance models the one-second photo scale, title at 1.1s, menu backdrop at
  1.6s, and staggered 250/500/750/1000ms buttons starting at 2s. Native
  `000dede4`/`000df168` subsequently fade the info button and grow the gear;
  these appear immediately at 3s here. Returning main menu uses a 500ms slide;
  submenus use a 200ms crossfade rather than the full native panel movement.
- Save formats and automatic checkpoints are compatible-runtime features,
  not emulation of the original binary `.sav` files.

Tests cover authored string/font records, failed-batch atomicity, deduplication,
manual/automatic save separation, corrupt resume behavior, first launch without
content, multi-file drops, menu input gates, resized hit testing, long-list
search/scrolling, pause timing and exact live resume. Optional visual tests use
the player's local library; they do not package it as a fixture.

## Built-in story extraction

Football Star is not an APK `.exp` member. Its scripts are loose numeric assets:
25001–25021 and 25023. The importer copies all 22, byte for byte and under the
same IDs, into a deterministic local CSPUD archive with literal records.
Metadata resource 1 has pack/episode IDs 0/0; `FUN_0008b048` identifies the
Football save by native key zero, and `FUN_0009794c` composes that key from the
pack and episode shorts. The five title strings are read from APK resource 13,
entries 193–197. The catalog filename is `Football_Star.exp`.

The resulting record has an ordinary hash-derived `file` location plus
`builtin: "football-star"` and text search aliases, including Football Season.
These optional manifest fields do not change library schema version 1. Art,
fonts and audio keep their original APK namespace. No proprietary EXP or
metadata blob is embedded in the executable; every extraction requires a
validated user APK, which the library retains.

Fresh imports include this story automatically. Application startup and CLI
listing call `ensure_builtin_episodes()` to upgrade earlier libraries from the
retained APK. Publication uses the same staged, validated, atomic manifest
update as added episodes, checking for concurrent edits. Existing episode
identities, player preferences, and manual/automatic saves are preserved.
Repeated upgrades do not duplicate the entry. Numeric order puts it at 0/0;
it is classified as bundled even though its generated EXP is a local file.
The local library now contains 272 episodes and 996 script records. A startup
audit reached 179 title screens and 93 dialogue screens with no failures;
these counts establish initialization, not full-story compatibility.

Football Star's opening, appearance selection, name entry, dialogue choices
and first classes have been tested using original bytecode. Service 91 at
scene 25006, PC 1245 now completes into the first football mini game. The tested
route plays both halves and returns to dialogue. Relationship indicators now
render with native icon/count selection, cache writes, sound and animation;
see [UI_FIDELITY.md](UI_FIDELITY.md#npc-relationship-indicators).
