# Changelog

## 1.0.1 (shshd-runtime)

### Fixed

- **HD art for standard episodes now works in imported libraries.** In 1.0.0
  only a library prepared by the developer's tools had an HD twin store, so
  every imported library showed **SD** on episodes that play fully in HD and
  drew their pictures at 2x instead of HD.
  - The app now ships SHS's twin map. It holds fingerprints only, no art.
  - From it, the app builds the store from the player's own HD episodes
    during first-time preparation, in about 45 seconds. A 1.0.0 library gets
    it on its next open, with no re-import.
  - Built from a zip import, it matches the reference library: 1,795 twins
    and the same SD marks.
- Two tests that passed only on Windows: one depended on folder-listing order,
  the other gave a test app no screenshot cache.

## 1.0.0 (shshd-runtime)

The first release of this fork. Earlier sections are upstream exp-runtime's history.

### Changed

- **Merged upstream exp-runtime v0.5.0 (4ed86d0): the component layout.**
  The source now lives under `packages/{formats,engine,player,shs,cod}/src`
  as upstream's does, so later merges line up file for file.
  - **Names.** The distributions are `shshd-runtime` and
    `shshd-runtime-<component>`, all version 1.0.0, never upstream's names.
  - **Placement.** Every module keeps its import name. Ours are placed by
    role: drawing code in `player`, headless state and layout in `engine`,
    `cod/hd_art.py` in `cod`.
  - **Checks.** A headless session runs with no pygame loaded, and each game
    package works on its own.
  - **Taken from upstream:**
    - `exp_runtime.formats` and `exp.py`, with `ExpArchive`, `Metadata` and
      `ContentError` moved there unchanged;
    - `exp-tool inspect` / `extract`;
    - adapter-owned saved state (`STATE_TYPES`);
    - lazy SHS imports in the engine;
    - RAR decoder discovery for the new layout;
    - upstream's component and RAR tests.
  - **Kept from this fork:**
    - the HD style-1 menu font, now in `menu_assets.py`;
    - the decision-tree save relinking, the `ephemeral` sessions and SHS
      HD's own named-dialogue words;
    - `add-hd-art`;
    - the "SHS Runtime" desktop build, without the kiwi icon.

  The merged tree passes 955 tests. `uv.lock` still names upstream's packages:
  this fork does not use uv. See AGENTS.md for the fork's packaging rules.
- **Truncated curly quotes show as apostrophes, in both games.** The authoring
  tool stored U+2019 as the byte 0x19 and U+2018 as 0x18:
  - Cause of Death: 3 lines, in Volumes 6, 7 and 8.
  - SHS: 23 strings with 0x19 and 6 with 0x18, for example 11_3 The
    Endorsement's cupcakes that say 'BEN'.

  The device draws a missing-glyph box (owner photos IMG_0512/0513), and SHS
  drew a space-width gap. By the owner's choice, the runtime shows a straight
  quote, through each profile's `DISPLAY_CHARACTERS`, applied in
  `EngineState.substitute`. Scripts still see the raw bytes, and saves made on
  those lines load either way.
- **A second free Cause of Death build imports.** Upstream PR
  joshrmcdaniel/exp-runtime#1 describes a free build with no language banks.
  It keeps the duplicate Volume One at 13 and moves 1.3.4's 13-297 up by one.
  `cod.assets.logical_members` now recognises that layout from its members, as
  it does the reference .bv build (language banks at 15-18, the rest +5).
- **Cause of Death choices use CoD's own panel.** CoD's iPhone `SHSWidgetMenu`
  is SHS HD's at half scale. With the SHS HD art source, choices are laid out
  by SHS HD's port with CoD's constants, layout bank, packs and fonts
  (`hd_choice.COD_GEOMETRY`, `hd_layout.BankLayouts`). This brings in black
  descriptions and options, the per-theme rows, the housing and the circle
  timer. They match the 1x photos to within half a point (docs/COD.md, "The
  choice panel").
- **Options layout.**
  - The switches sit against the card's right side, as the Episode Titles button
    does.
  - That button is smaller: 104 x 34, a little bigger than a switch.
  - Data Management adds Open Another Library. A library opened from there
    arrives as a game switch does, with no loading screen or sound question.
- **Options gains Episode Titles and Data Management (main menu).**
  - **Episode Titles** is a button at the end of General that steps through the
    title languages. It appears only where an episode has a translated title,
    so not in Cause of Death. The HD picker and lists now caption episodes in
    the chosen language too; before, they always used English.
  - **Data Management** holds Add Episodes. It opens the file browser, and an
    import now returns to the HD main menu instead of the SD episode list.
- **Options has categories, in both games.** Options lists General and Sound,
  laid out like Help & About, and each opens a page of its own switches:
  - General: Side Panels (in a story), Choice Hints, Ask to Skip Mini-Games, Skip
    Ad Intros and SHS HD Backdrop;
  - Sound: Game Music and Sound FX with their sliders.

  Cause of Death leaves out the SHS-only switches (Side Panels, Ask to Skip
  Mini-Games, Skip Ad Intros). SHS HD Backdrop now works in SHS too (main menu,
  picker and episodes). A Data Management category is planned.
- **Fixed: SHS HD's intro ran about three times too slowly** on a full-screen
  window. The cap that stops a library opening from skipping a fade had
  slowed every slow frame; it now applies only to frames over 0.25 s.
- **Fixed: opening Cause of Death directly (not by switching) crashed** on its
  first frame. The CoD shell lacked the new fade state.
- **This fork is a distinct app: "SHSHD Runtime".** Its data folder
  (`%LOCALAPPDATA%\SHSHD Runtime`, `~/Library/Application Support/SHSHD
  Runtime`, `$XDG_DATA_HOME/SHSHD Runtime`, iOS Documents), window title, game
  chooser, desktop build (`SHSHD Runtime.exe` / `.app`) and iOS identity
  (display name, bundle identifier `org.shshd.runtime`) no longer share the
  original's names. It no longer adopts the original's `SHS Runtime` launcher
  file or library either. So an install of upstream EXP Runtime and this app
  never open, write or remember each other's libraries, saves or settings.
  The iOS project's product file is still `EXP Runtime.app`, which is only a
  build-output name. Libraries made under an earlier name can be opened with
  Open Library.
- **Fixes from the owner's first full Cause of Death test.**
  - **Chapter cards** are drawn on the whole HD frame, so the opening black covers
    the picture. Their text uses SHS HD's 2x glyphs on CoD's layout, so it is no
    longer pixelated.
  - **Help & About's Push Notifications** shows CoD's own page (strings 235 /
    237) instead of the iOS permission prompt.
  - **CoD's window cards** (Pause, Options, Help & About, Exit Game and the
    other menu-engine windows) are drawn as vectors at HD's size, as SHS HD's
    are. Before, they were CoD's 1x pieces stretched, and their corners were
    soft and off the grey edge. The grey edge now runs beside a window's body,
    as on the device.
  - **CoD's main menu plays its own music** (0x2011, from
    `doSoundManagerTransition`). The app had always asked for SHS's.
  - **SHS HD's faded collage beside the frame in CoD**, on the menus and in
    episodes, with a new "SHS HD Backdrop" switch in Options (off: the dark
    fill). The stretched title painting is gone.
  - **Fades.** Switching games fades the frame (not the backdrop beside it) to
    black. CoD then fades its menu in; SHS plays SHS HD's flash, with its jingle,
    over black. CoD's launch also fades to black between its EA screen and its
    menu. The shell's animations advance at most 1/20 s a frame, so the half
    second a library takes to open no longer skips a fade.
- **"More EA Games" is Switch Game in both HD front ends.** The main menu's
  fourth button and the end menus' row run upstream's Switch Game: the other
  game's library opens, or the game chooser does when it isn't set up. Each
  is labelled with the other game's name: "Cause of Death" in SHS HD, and
  "Surviving HS" in CoD, because the full title is too wide for the button.
  A switch goes straight to the main menu's entrance, with no loading screen
  or sound question. New option `--game-library GAME PATH` says where a
  game's library is without remembering it. `play-hd-art-test.ps1` uses it
  to pair `test-library` with `cod-library`.
- **Cause of Death's episode screens are SHS HD's, in CoD's style**
  (`desktop_cod_episodes.py`, `cod/episodes.py`).
  - **Screens.** Play/Resume opens the tile grid with a title-card preview per
    episode. Episodes On Demand opens the category list, and Now Airing the
    list by year of first release.
  - **Categories** are CoD's catalogue's own. Volume One is "Volume One: The
    Maskmaker". The two names a volume can carry share one row. The Now Airing
    Special ("Just Another Day") leads Side Stories, and A Fallon Family
    Christmas sits in Premium Content (owner's placements).
  - **Order.** The volumes come first, then Side Stories and Premium Content.
    Episodes within a category go by first release.
  - **Dates** are docs/COD_RELEASE_DATES.md's first releases. A Volume set takes
    its Chapter One's date. The first Secret Files, never announced, takes its
    store date, now added to the doc.
  - **Styling.** The parts styled as CoD are the backdrop (its title painting),
    the blue buttons, the popup's recoloured border, and the list's bands,
    rows, icons and text from CoD's pack 16, checked against IMG_0467.
    `HdEpisodePicker` and `HdEpisodeList` expose their colours, string ids,
    masks and popup card for this.
  - **Previews** are generated for 72 of the 74 episodes. The Restore alert and
    a picker message use the game's own strings and title.
  - **Without the SHS HD art source** the buttons open the plain episode
    browser.
- **Cause of Death has its own title screen and launch flow**
  (`application_cod.CodShell`, `desktop_cod_main.py`). It is SHS HD's front end
  on CoD's menu engine, in SHS HD's layout with CoD's art:
  - the six buttons in SHS HD's places, with CoD's labels;
  - CoD's title painting, filling the 3:4 frame with its logo kept just above
    Play/Resume as on the device (IMG_0464); only the buttons slide in;
  - "Play with sound?" over CoD's EA launch image (IMG_0473), then straight to
    the main menu;
  - Help & About, Options, the Privacy Policy / EULA / Terms list (its usage
    sharing rows follow their item conditions), Delete Saved Game?, the end
    menus and the Connection Error notice, all from CoD's menu engine.

  CoD's menu and action numbers are translated onto SHS HD's (docs/COD.md,
  "The title screen and launch"). Every CoD menu-engine window is now SHS HD's
  `HdMenuWindows` in CoD's style, the in-game "Exit Game?" too, so it no
  longer uses CoD's iPhone geometry. Until CoD's own picker is built, the
  episode buttons open the episode browser. "More EA Games" keeps the
  Connection Error for now.
- **Cause of Death's Help & About pages.** Now Airing and Episodes On Demand
  are SHS's rewrites adapted to CoD:
  - CoD's two release stages, listed by first release;
  - why most dates are exact (the Facebook page announced each release) and
    how the rest are approximated;
  - the planned tile grid selector;
  - no SD tag.

  About is the owner's (CoD's and this project's credits, the fan-project
  disclaimer and the Discord link). The other pages keep CoD's text, and
  CoD's version token `~259~` is substituted. A link in a help page now
  opens behind the "Exit Game?" prompt during a story too, in both games;
  before, it only worked from SHS's main menu.
- **Cause of Death has its own Pause, Options and Help & About menus**
  (`desktop_cod_pause.py`). They are CoD's menu-engine windows (Pause is menu
  24, Options menu 20, Help & About menu 13). By the owner's choice, every CoD
  menu keeps SHS HD's scaling and layout: `HdPauseMenu`'s card, rows, centring,
  UIKit switches and sliders, and text pages. Only the styling is CoD's:
  - its pack-16 card art, Arial Rounded text and row tints;
  - CoD's back button and speakers, at HD's sizes.

  `HdPauseMenu` exposes its colours, `font`, `control_font`, `art` and `panel`
  for this. Options keeps every setting shared with SHS. By the owner's choice
  the sliders are drawn although CoD's photos show none, and "Play My Music"
  and Side Panels are left out.
- **Cause of Death's quiz uses CoD's own panel, with SHS HD's art mirrored.**
  The word quiz (service 71) is CoD's `SHSUIMenu::initActionMenu`, which is
  SHS HD's at half size: the panel, the score layers 41x19 / 18x15, and the
  running man at (161, footer + 31). The "+1 / -1" effect still rises 30
  points, because `doScoreEffectAnimation` is the same in both builds.
  - With the SHS HD art source, the timer pie, score capsule and running man
    are SHS HD's 2x frames in CoD's colours.
  - The quiz now shows "Touch choice before time runs out" in both games,
    since `initActionMenu` calls `setTimed`.

  Checked against the owner's Accelerant photos IMG_0516 / IMG_0520
  (docs/COD.md, "The quiz").
- **Cause of Death's script links go through its own "Exit Game?" prompt.**
  A service-100 link is offered behind CoD's own menu-engine alert (menu 16:
  No, or Yes for engine action 24, `exitAndShowURL`), in SHS HD's window
  layout and CoD's purple-blue style (`desktop_cod_menu.py`). The buttons have
  SHS HD's sharper outline filled with CoD's own colours. It dims and holds the
  game like the SHS notices.
- **The bottom hint runs at Arial Rounded's advances on iOS.** Both iOS
  builds lay ArialMT out with Arial Rounded MT Bold's advance table, an
  original bug (CoD `initFonts` case 4; SHS HD 0002b04a, as on the faceplace
  wall). "Touch the screen to continue" is now 154 units wide, as in SHS HD's
  IMG_0132 and CoD's IMG_0496; it was 141. Android's bitmap hint is
  unchanged.
- **Cause of Death's portrait picker and name entry use CoD's own screens.**
  Both are SHS HD's at iPhone size, with CoD's layout bank, packs and fonts:
  - **Portrait picker** (`desktop_picker.CodCharacterPickerRenderer`). The
    box is at (0, 120, 320 x 240) and the portrait positions are SHS HD's
    halved. Ring and art take the portrait's opacity separately.
  - **Name entry** (`InputRenderer._draw_cod`). Layout 46 is placed at
    151 - promptHeight. The title, prompt and typed text are black, and the
    cursor is a dark-red bar. A two-line title centres on the one-line slot,
    as CoD's does. With the SHS HD art source, the widgets' white fill and
    the field's outline come from SHS HD's 2x frames in CoD's look
    (`cod.hd_art.COMMON_FRAMES`).

  Checked against Fallon Family Christmas, Volume 8 and Your Case photos,
  within half a point (docs/COD.md, "The portrait picker" and "Name entry").
- **Cause of Death backgrounds fill the frame without stretching.** Scenes now
  pan with the speaker the way SHS's SD backgrounds do in the HD frame (owner's
  choice), so the window always stays inside the art. They used to be
  stretched about 26% wide. A window that does run past an art's edge keeps the
  art's scale.
- **Cause of Death's speaker names wrap like the iPhone's.** CoD's
  `SHSUIDialog` title code is SHS HD's over its own layout 17, so long names
  now wrap onto two lines in the tall header ("Natara / Williams"). They used
  to shrink onto one line by Android's rule. The short-title threshold and
  shift stay 135 and 15 in CoD's own points. Matches IMG_0392, IMG_0415 and
  IMG_0310.
- **Cause of Death's "Detective Score Up!" banner.** CoD's score notice is SHS
  HD's letter effect, with CoD's raise, limit and housing and its red Trebuchet
  Italic letters in a white outline. It used Android's typed notice, which the
  CoD library drew with SHS HD's iPad geometry and the speaker-name face, so it
  never appeared on screen. Matches IMG_0322 within a point.
- **Cause of Death's chapter card.** CoD's `SHSUIChapterScreen` is SHS HD's in
  a 320x480 screen. The new `CodTitleRenderer` draws it with CoD's layout 48
  regions (the title 30 lower with the free edition's banner), its image fonts,
  and the HD card's black fade and title wipe. Title and subtitle match
  IMG_0479 and IMG_0474. Its picture is scaled evenly to cover the frame.
- **Native notices dim the scene sepia.** The "Locked" notice and the faceplace
  link's "Exit Game?" confirmation now tint the frame the way the pause menu
  does, matching an HD photo of the "Locked" notice. The tint goes when the
  button closes the notice. Like the pause menu, the notice also holds the game
  behind it: typing and clocks wait until it closes.
- **Hand-confirmed art pairs override automatic ones**
  (`tools/extend_hd_twins.py --confirmed`, `TwinStore.add(replace=, remove=)`).
  A `= none` line removes a wrong pair. First use: the owner's catalogue check
  moved MTX_Pranksgiving's school exterior (Lizards sign) to its own HD
  picture; the correlation had picked the Squirrels version.
- **HD episodes with narrower portraits are no longer marked SD.** Release
  detection (`episode_index.image_variant`) now reads picture heights as well
  as widths. HD portraits narrower than 256 are still 256 tall. 29 HD episodes
  had no 256-wide art, among them the Sara and Taylor Small/Medium vote
  packages, so they were left undecided and then tagged SD. Existing libraries
  re-read undecided records once (record `index` 2).
- **Pictures already HD inside standard files** (Set_12's pool is 12_5's
  own HD picture) are no longer doubled by the fill mode, and the coverage
  measure counts them as covered.
- Merged upstream exp-runtime v0.4.2 (`4bae56b`; see its section below).
  - **Dialogue lifecycle.** Both games, with or without an HD bundle, now use
    upstream's recovered iOS lifecycle, which replaces this fork's own versions:
    - A new speaker's box grows out of the portrait through a strip, in
      120 + 200 ms.
    - Service 89's shake holds the box hidden, then scales it from 0.5 and
      rotates it. Our left-hand keyframe was at 50%; it is at 75% for both
      sides in SHS HD and CoD alike (`initAnimations`).
    - The portrait housing is clipped when the entrance finishes; for a
      shake, that is when its rotation ends, not when its growth ends.
    - New speakers enter neutral, and old and new art crossfade on two
      tracks.
    - Hidden dialogue survives temporary panels.
  - **Music.** The script's music repeat flag is honoured.
  - **Saves** are version 25 (upstream's 20 and 21); older saves keep their
    full-size box.
  - **Update checks.** Upstream's release check is included but switched off:
    this fork has no release repository (`app_info.UPDATE_REPOSITORY`), and
    upstream's releases are a different program.
- Merged upstream exp-runtime v0.4.1 (joshrmcdaniel/exp-runtime `6fb7191`; the
  project formerly named shs-runtime). The package is now `exp_runtime`, with
  SHS-only modules under `exp_runtime/shs/`; this fork's HD modules stay at the
  top level for now. The distribution is `shshd-runtime`; the app still opens
  directly into SHS (`--game cod` is reachable but Cause of Death is untested
  here), and the desktop executable keeps its "SHS Runtime" name.
- Saves stay `shs-runtime-save`, now version 23. Both projects numbered saves
  independently after the shared version 12. Version 23 adds upstream's
  background pan, Continue-tab expansion and word-grid tile effects. Earlier
  saves from this fork migrate; upstream `exp-runtime-save` files are not
  accepted (docs/RUNTIME.md).

### Added (from upstream, without an HD bundle unless noted)

- Speaker-side background panning (service 97 / `BackgroundPan`). With the HD
  app bundle, HD's own location pan still drives the frame.
- The supplied skin's Continue tab, the original pause menu artwork with its
  held-gear release-to-open and click/pause sounds (sounds also play over the
  HD pause menu), the looping menu theme (not over HD's main menu), Choice
  hints, episode-title languages, adding a music APK, ZIP/RAR episode archives
  (RAR needs libarchive; see tools/build_rar.py), and local survey receipts.
- iPhone SHS IPA libraries, now also from the free edition's IPA
  (`com.ea.shslite.row`, 1.4.2 build 1.4.3.53). Its assets pass the same
  checks as `com.ea.shs.row`. An SHS HD (iPad) IPA chosen together with the
  APK is recognized and imported as the APK's HD supplement, as before.
- RAR import works in source runs once `tools/build_rar.py` has built the
  pinned libarchive (3.8.9) into `build/rar/install`. Desktop builds bundle it
  when present and otherwise import EXP/ZIP only.

### Added (shshd-runtime)

- **Update check, against this fork's releases** (`1timewire1/shshd-runtime`).
  - In the HD menus the offer is an "Update Available" card with the game's
    own No / Yes buttons. It appears at the end of the launch's loading
    screen, before "Play with sound?" (the launch waits up to 2.5 s for the
    check), or later on the idle main menu if the answer comes late.
  - The offer reads "SHSHD Runtime x.y.z is available. Would you like to
    update? (Clicking Yes will close the game and open your browser)". Yes
    opens the release page and closes the game.
  - On iOS, which cannot update or quit itself, the offer only says an update
    is out and how to install it, with an OK that carries on.
- **Release downloads are named `shshd-runtime-<tag>-…`** (desktop archives and
  the unsigned iOS IPA), no longer upstream's `exp-runtime-<tag>-…`.
- **CI and packaging for this fork.**
  - `uv.lock` is regenerated for the shshd-runtime names; CI's
    `uv sync --locked` would have failed.
  - The wheel audit and install tests use the fork's names.
  - The iOS app's metadata, its simulator test's bundle id and the macOS bundle
    id are the fork's own.
  - The release workflow names the fork's downloads and never publishes to
    PyPI. Releases carry the desktop downloads and wheels. The iOS job runs
    but no longer gates or joins a release.

### Known issues

- **The iOS app does not work in this fork.** The tests pass and the simulator
  app builds, but it stops on launch with "No module named 'pygame'". The HD
  and CoD screens import pygame directly, while the iOS app draws through
  `exp_runtime.graphics` and embeds no pygame. Its backend also lacks several
  features those screens use: file fonts, blend-mode masks, `PixelArray`, some
  draw calls and `image.save`. Set aside after v1.0.0; see docs/IOS_APP.md.
  - `RELEASE.md` has v1.0.0 notes.
- **Commands and documentation name the fork.**
  - The app is `shshd-runtime` and the file tools `shshd-tool`. Upstream's
    `exp-runtime` / `exp-tool` and `shs` / `shs-tool` remain aliases.
  - README, AGENTS, MAINTAINERS and the docs describe SHSHD Runtime as a
    separate app, a fork of exp-runtime. They now name its own data folder,
    releases and wheels (GitHub releases, not PyPI).
  - They no longer claim the launcher reads the old SHS Runtime folders.
- **A Cause of Death-only install works.** SHS HD's football and word-grid
  screens are loaded only when SHS's package is installed.
  - General gains a **Check for Updates** switch on the main menu.
  - The About pages link **shshd-runtime** and **exp-runtime** to their
    repositories. Help pages may now hold any number of links, written
    `[label](url)` or as bare URLs.
  - SHS's About credit names exp-runtime, not the old shs-runtime.
  - The special thanks link each game's Discord server (the bare links at the
    bottom stay). A link of several words underlines as one.
- **Usage Sharing is hidden** in both games' Privacy Policy / EULA / Terms
  window. The runtime sends no usage data, so the switch only confused.
- **README** documents the SHS HD IPA's role, the import folder, Bulk Import
  and the store listing.
- **Episode info for Cause of Death.**
  - An "i" button on each episode opens a card with its title, airdate,
    original price and store description. On the tile grid it sits where
    SHS's SD mark goes; in the lists it sits beside the play / pause icon.
  - The data comes from 1.4.7's store listing (`mtxprods`, from a device
    backup), imported like the episode catalogue. It goes in `cod_episodes`,
    beside the IPAs, in a bulk archive, or through Add Episodes.
  - The library keeps every store product, including the chapters inside
    the Volume sets, for splitting those later. The file's own user record
    (device and account identifiers) is never kept.
  - The On Demand copy's text is preferred over the Now Airing one. A Volume
    set shows its set's text.
  - Volume One, never sold, shows the App Store listing's description, free.
  - Without a store listing, nothing changes.
  - On the tile grid the button takes the SD mark's style: its dark plate,
    with an "i" in a ring.
  - The format is documented in docs/COD_STORE.md.
- **The Now Airing Special follows the store.** It is now "Now Airing
  Special", in a category of its own after Premium Content, as 1.4.7's store
  listing files it. Before, it was first in Side Stories as "Now Airing
  Special: Just Another Day".
- **Bulk Import: both games from one .zip or .rar.**
  - The archive holds the `import` folder's layout, at its root or inside
    one folder.
  - **First boot** with nothing to import opens a Bulk Import page. Drag the
    archive onto it, or press Choose File. Back leads to the game chooser,
    which now has a Bulk Import button too.
  - **The import folder** may instead hold just the archive; it is imported
    at first boot as loose files are.
  - Only the game files are extracted, into a temporary folder beside the
    libraries that is removed afterwards. Before extracting a ZIP, the app
    checks there is room for it and its libraries.
  - A game that already has a library is left as it is, and a message says
    so.
  - With a library open, a dropped archive still adds episodes as before.
  - A first boot whose only library is Cause of Death's opens it, rather
    than SHS's setup screen.
- **The `import` folder sets up both games at first boot.**
  - Beside the SHS APK, HD IPA and fonts it now takes the Cause of Death IPA
    and a `cod_episodes` folder (EXPs and `cod_options.sav`; a device's whole
    Library/Caches folder works, since everything else there is skipped).
  - The IPAs are told apart by what they hold, not by file name.
  - The fonts go into each new library, and the CoD library gets the SHS HD
    IPA as its art source, as `add-hd-art` does.
  - Either game can be staged alone. If one game's import fails, the other is
    still kept, and the error is shown.
  - The desktop build's empty `import` folder gains `cod_episodes`.
- Names carry from episode to episode, as the original app's
  (`shs_options.sav` keeps one name table for the whole install).
  - A name you type or pick, or one a script stores, is saved with the
    library's `player.json` (`names`). Examples are the player (`$USR`), a
    series lead (`$ZOE`, `$Scott`, `$Travis`…), a familiar or `$DATE`.
  - Every later episode reads it there instead of falling back to its
    default. 231 episode files in the test library read these names.
  - Loading an older save keeps the shared names; any name only that save
    has joins them.
  - Service 113 now stores its name while no player name exists. That is
    Football Star's "John" before you type yours.
  - The look you pick in a portrait picker is not carried over: the
    original starts every picker on the first portrait.

- A Side Panels switch in the in-game Options screen, under the Sound FX
  slider and above the player's extras, does what Tab does. The panels are a
  native feature the device shows on rotation, so there is no native string;
  the label is this project's. Opening the panels widens the window to 4:3
  only when it is narrower than that. A window already 4:3 or wider has room
  for both 224-point panels beside the game at full height and keeps its size.
  Closing them no longer narrows the window back to 3:4.

- Cause of Death can link the SHS HD (iPad) IPA as an optional HD art source
  (`exp-tool add-hd-art`). Its dialogue then gets crisp vector text in CoD's
  own fonts and colours (black Trebuchet italic narration, Arial Rounded body,
  dark-red names) and HD box skins derived from SHS HD's, recoloured and
  verified against CoD's own art. The portrait ring, its disc, the choice
  timer's wedges, the Continue tab, the gear and bottom bar and the portrait
  picker's rings are HD too, and the bottom bar runs edge to edge across the
  3:4 frame with the gear flush left, as in SHS HD. Without the link CoD's art
  is as before.
  SHS HD's screens, strings and scripts never apply to CoD (docs/COD.md).
- `docs/COD_RELEASE_DATES.md`: Cause of Death's release dates, from the
  developers' own Facebook page (all 556 posts), cross-checked against the CoD
  wiki. Every chapter, side story, special and volume set has its On Demand and
  Now Airing dates (each chapter shipped in both stages), along with the
  release-schedule history and the gaps the page never announced.
- Cause of Death 1.4.7 (the free edition, `com.ea.causeofdeathfree`) imports
  alongside 1.3.4. Its resources are renumbered: string banks for five
  languages at 14–18, and 1.3.4's 14–999 five higher. The library reads them
  under the 1.3.4 ids, English only, so the existing CoD contracts apply
  unchanged (docs/COD.md).
- A **Choice Hints** On/Off switch in the HD Options screen, under the sound
  volume slider, in both the in-game pause menu and the main menu. It is saved
  with the other options. It shows exp-runtime's Choice hints on the HD choice
  panel for HD and standard episodes alike (a 153-episode HD/SD comparison
  agreed on 99.8% of choices). Time spent computing a preview is kept off the
  story clock, so it never shortens a timed choice's countdown.

### Fixed

- The screens shown before any game is imported (the game chooser and each
  game's setup) no longer cut off their text. Every label there was drawn at
  one large size; each now keeps its own. The setup screen's HD (iPad) IPA
  note is shown for SHS only.
- A fresh desktop build no longer reports "files staged but no base game"
  at first boot. The build's own empty `import` subfolders counted as a
  drop; now only game files do.
- Opening the side panels no longer freezes the app when the story path loops.
  Football Star's practice hub replays scenes: a later join repeats the hub's
  ids, so the recorded path continues from the hub again. With the current
  scene off that loop (a save from earlier in the story), Rewind's parent
  search walked the loop forever. `DTView.real_parent` and `real_child` now
  visit each node once, as `sweep_forward` already did. The tree file was
  fine.
- Cause of Death's dialogue text follows its own `SHSUIDialog`: narration is
  measured in its own font and wrapped at 220. It now breaks lines as the
  device does ("…You struggle to / open your eyes."), in a box at CoD's place,
  15 units lower in the free edition, which leaves room for its ad banner.
  Typed lines sit 4 units up and left of the text layer, step by whole points,
  and drop 2.4 units (photo-measured). With vector text it had used SHS HD's
  photo-fitted placement: text about 4 units right of the device's, and the
  narration box about 30 units left.
  The bottom bar's hints read "Touch the screen to continue", "Touch the best
  choice" and "Touch choice before time runs out", from CoD's own string
  indices (docs/COD.md).
- Cause of Death's portraits sit as its iPhone `SHSPortraitLayer` places them:
  flush on the ring's bottom edge, with no gap under the chin. The ring is
  clipped against the bubble with CoD's 10-point corners, in dialogue and in
  choices. They used to follow Android SHS's anchoring (docs/COD.md).
- Cause of Death's timed word quiz (service 71) runs on the iOS action menu
  its own code builds, the same pacing as SHS HD's (fly-off 0.5 s, fly-on
  0.7 s, a 0.1 s selection). It plays CoD's own answer sounds, 8003 and 8004,
  instead of SHS's 8001 and 8002. CoD's portrait selector (service 78) plays
  CoD's click, 8005, for both a swap and the confirm, instead of SHS sounds
  that CoD doesn't have (docs/COD.md).
- Cause of Death no longer stops when a timed action choice runs out. Most
  Volume bundles and Side Stories 18 have choices whose timeout picks no
  option (-1). CoD's menu then returns the never-written slot before its
  result table, which the runtime models as 0, so the script's "no answer"
  branch plays. It used to raise "Incremental choice timeout index is out of
  range" (docs/COD.md). Volume 2's number puzzle, whose timeout points past
  its options, returns that selection unmapped. It matches no answer, so the
  wrong-answer branch plays (an adaptation, to be checked on device).
- The episode explorer (`tree_explorer.py`) also lets timed choices run out.
  Side Stories 12's lone "Shoot!" can only be passed by holding fire, and an
  explorer that always answered never reached the rest of the story. It also
  plays the iOS quiz (SHS HD, CoD) frame by frame, tapping only while input
  is open; its one large tick used to leave that quiz unfinished.
- HD dialogue speaker names follow the iPad build's own title layout, decompiled
  from `SHSUIDialog::updateTitleBounds` / `animateTitleLayer`, `SHSTextLayer` and
  `CSFont`. That replaces Android's label history, per-name cases and the ink fit:
  - **Regions:** layout 17's normal or tall title region comes from the HD layout
    bank, with the tall one used when the name wraps beyond the normal height.
    Speaker type 1 nudges right 1 unit and type 2 left 2.
  - **Flags and offsets:** 0x1b/0x19/0x1a, with title line offsets {40, 10}
    points.
  - **Short names:** a name under 135 points shifts 15 points, which is half
    what the iPhone port's units imply.
  - **Vertical placement:** the line block is centered with cap-height lines
    16 points apart, each baseline one cap height below its line's top.
  Matched to the pixel against the iPad photos IMG_0070 (Adam) and IMG_0075
  (You).
- HD dialogue body text starts at the text node's x with HD's line offsets
  (80/70 units, ARR_TEXT_LINE_OFFSETS) instead of Android's bitmap 85/75 and a
  photo-fitted shift. It now matches IMG_0075's three lines.
- HD dialogue and choice portraits are composed as `SHSPortraitLayer` does
  (`drawLayer:inContext:`, decompiled): each sits in a 256x320-point layer whose
  bottom is the housing's, at its own size, centered with its bottom 2 points
  above the housing's edge. It is clipped by the 256x300 mask (resource 311,
  soft-edged as CoreGraphics clips) from 20 points down, and mirrored after the
  clip, so the mask is not mirrored. The Android 12-row crop and inner-disc
  anchor no longer apply in HD. Standard-episode portraits with no HD twin (1x
  art, e.g. As Time Goes By's Mr. Hotpants) are drawn at 2x like HD art. Before,
  HD's 256x300 mask was applied to the 1x art before enlarging it, so the clip
  was twice too large and the art ended above the disc. IMG_0070 and IMG_0075
  still match within a pixel.
- HD relationship icons share the portrait ring's center (they are
  sublayers of the same layer, `setStatusIconAnimated`); they sat 5 units high,
  visible against IMG_0070's skull.
- The HD Word Game draws a standard episode's 1x portrait at 2x, as the dialogue
  does. It used to be half size, mostly off the bottom edge.
- HD choice panels are laid out and drawn as `SHSWidgetMenu` / `SHSMenu` do
  (`hd_choice.py`, decompiled) instead of from photo fits:
  - **Header:** layout bank widgets 7/16/8 (portrait left/right/none), with the
    tall title region when the title wraps.
  - **Description:** widget 65, with ARR_LINE_OFFSETS_MENU around a portrait;
    a portrait's description is at least 136 points.
  - **Rows:** fixed 88-point table cells of enabled options with 24x12 label
    insets, (166,166,166) separators and setPortrait's row colors; only the 6-point
    side strips sit behind them.
  - **Footer:** widget 3, or 22 when timed.
  - **Placement:** the panel is centered at (1024 - total) / 2 with rows dropped
    past 964 points, and only the row table scrolls. A tall panel (As Time Goes
    By's "What quality is most important...") therefore fits as on the device.
  - **Portrait:** the housing's top is the panel's top, which fixes the 3-unit
    offset against IMG_0085. The ring is clipped by `clipPortraitHousing`.
  The light-mode photos IMG_0226, IMG_0227 and IMG_0222 match within a point,
  including every row separator.
- The HD choice timer is the native `SHSCircleTimerLayer`: resource 155's 16
  wedge frames over the timed footer's notch (box frame 9), centered at
  (385, footer top + 61). Each wedge holds full opacity until its sixteenth of
  the timeout, then drops to 0.8 and fades out, clockwise from twelve o'clock.
  This replaces the drawn 12-slice wheel.
- Pajama Hip's cap height (CSFont's line height) is its ascent, as CoreGraphics
  returns for that version-1 OS/2 table. Two-line choice titles were 10 points
  too tight, and one-line dialogue names 5 points high (IMG_0226/0227,
  IMG_0070/0075).
- With an HD bundle, the rapid-fire quiz (word game) is HD's own action menu:
  - **Panel:** the same SHSWidgetMenu panel as a choice. Its timed footer shows the
    score capsule.
  - **Footer:** the running man (resource 155 frames 28-32, 0.07 s each) runs over
    the circle timer. The score is drawn in white TrebuchetMS-Bold 50, and a
    "+1"/"-1" (green/red TrebuchetMS-Bold 32) fades in and out while rising
    30 points over 1 s.
  - **Pacing (engine):** a tap highlights its row for 0.1 s, then scores. The
    labels then fly off over 0.5 s, the new ones deal and fly on, and input
    returns 0.7 s later. The game ends once its time is out with no selection
    pending. Save format 24.
- HD choice rows draw the option text as SHSMenu's two half-alpha labels. They
  fly on when a choice appears (0.35 s per row, staggered; 0.15 s in the quiz)
  and, in the quiz, fly off after an answer. The settled color is the native
  theme color at 75% (IMG_0226 measures (92,140,227); ours (94,140,229)). The
  photo-fitted lightened option colors are no longer used there.
- HD flair notices ("Strength Up") follow `startLetterEffectAnimation`:
  - **Spacing:** each letter is placed separately, 3 points apart.
  - **Position:** the text is centered over the portrait housing and clamped to
    the screen, with its top at housing.y - 60 - cap/2 + 20.
  - **Timing:** the letters start when the portrait animation ends plus 0.25 s,
    0.12 s before the name, not when the line starts.
  The white outline was 2 points instead of 3 at the normal window size
  (half-stroke widths were rounded half-to-even). Matches IMG_0088 to a point
  vertically; the word is ~4% wider, from the Windows Trebuchet MS Italic file.
- HD stroked text (flair notices, Pajama Hip names, the quiz score) is drawn as
  CoreGraphics fill-and-stroke (`glyph_outline.py`):
  - **Outlines:** glyph outlines are read from the face's `glyf` table.
  - **Stroke:** each is filled and stroked at the font's width with mitered
    joins (limit 10), instead of a round dilation of the rendered glyph.
  - **Effect:** corners are sharp ("th"), counters stay open ("e", "g"), and
    outlines meet in flat edges (under "n").
  - **Stroke colors:** a font's own stroke can now differ from its fill, so the
    quiz score's 0.6-point stroke is gray (0xffb4b4b4) over the white rather
    than thickening it. Its stem now matches IMG_0293.
  - **Flair spacing:** a flair notice's space is 5 points wide (the letter loop
    gives zero-width letters 5), and the centering width counts its advance.
    Every letter of "Strength Up" now lands within half a point of IMG_0088.
- The HD faceplace wall is laid out from the decompiled `drawMessage` /
  `measureMessage*` instead of photo-fitted spacing (legacy/findings.md, "The
  wall's rows"):
  - **Rows:** each post and each continuation is a row of its own. A face post's
    group is made up to 56 points (by its heights, so a continuation's 3-point
    padding comes on top), and a "Tap here" link has no padding above it.
  - **Separators:** start at x 11, 2 points above the next row.
  - **Face:** centered at (43.5, row + 27.5); the portrait is clipped to its row.
  - **Picture frames:** drawn around a 2-point margin.
  - **Order:** a post's newest continuation sits directly under it.
  - **Check:** every separator in IMG_0299 and IMG_0245 lands on the photo's
    point.
- Faceplace body text keeps an original bug: the app sizes its Arial letters
  with Arial Rounded Bold's advances (`initFonts` builds the ArialMT advance
  table from the wrong CGFont). The wall and alert now draw Arial 14 at those
  advances instead of the earlier fitted "Arial 15.1", so lines wrap where the
  device's do ("Raven When you end" fits, "Wilson! We're coming" does not).
  Emoticons use `addCharImage`'s offset (-1, 6), bottom-left anchored, with a
  16-point advance.
- HD art for standard episodes reaches season bundles and backgrounds reused
  across stories (`tools/extend_hd_twins.py`, added to the existing twin
  store):
  - **Season bundles:** a season shipped as one HD file (A New Start Seasons 2
    and 3) pairs with each standalone episode found inside it by its script
    text. Portraits pair by name with the bundle intro's cast, including the
    shared-bank characters the HD app has no art for (Ben, Cameron).
  - **Costumes:** characters with more than one look in a season are left for
    a short hand review (`--review`, `--confirmed`). A confirmed line may name
    the HD episode that holds the look
    (`<episode> <base> = [<HD episode>] <base>`), and pairing stops at the
    first unused expression slot. The owner's review paired seven looks
    (35 pictures): every A New Start S2/S3 episode except 3_7 A Fallon
    Family Christmas (114/119) is now fully HD.
  - **Backgrounds:** a background correlating 0.98 or more with any HD one is
    taken as the same picture.
- `tools/build_hd_coverage.py` counted the app's shared-bank pictures and the
  unused expression slots against coverage. Shared-bank pictures the HD bundle
  or the twin store replaces now count as HD, and unused slots aren't counted.
  `--only` merges into the cache instead of replacing it.
- The HD picker's thumbnail pass now gets past the High School Story ad (it
  takes the "Play the Surviving High School episode!" option), so Game of
  Cones, Part 1 and The Conned Artist, Parts 1 and 2 show their title cards.
  Episodes once marked as having no title card are tried again once.
- The High School Story ad that opens Game of Cones, Part 1 and The Conned
  Artist, Parts 1 and 2 no longer leaves the episode stuck after "Go to the
  High School Story app!":
  - **Cause:** the script asks service 100 to open the App Store link (a no-op
    in the HD app, as in ours) and then ends.
  - **Now:** the choice comes back, and the app's "Exit Game?" confirmation
    offers the link's web page.
- Picking "Play the Surviving High School episode!" in that ad asks whether to
  skip these intros from now on. Yes sets **Skip ad intros**, also under
  Options → Cheats and in the HD Options page. With it on, a new game of those
  episodes starts at its title card: the ad's dialogue and choice are played
  through headlessly (`ad_intro.py`).
- An **Ask to skip mini-games** option (Options → Cheats, and the HD Options
  page), off by default:
  - **The prompt:** before each football game or word grid, a narrator-styled
    choice offers Win, Lose or Play. It shows football's half, side and
    starting score, or the grid's target, time and words.
  - **Win or Lose:** finishes the game with that result, as the Decision Tree
    explorer decides it.
  - **Play:** starts the game as usual.
- With the HD app bundle, the main menu's faded collage now fills the whole
  window around the game: beside the frame, above and below it in a tall
  window (the main menu included), and beyond the side panels. The empty dark
  blue margins are gone.
- `tools/export_art_catalog.py LIBRARY OUT` catalogues a library's character
  portraits and backgrounds as Markdown documents with full-resolution
  exports, all written outside the project:
  - **HD documents:** every HD picture, and whether a standard picture
    already resolves to it.
  - **Standard documents:** every standard picture with no HD counterpart.
  - **Leads for unmatched standard pictures:** portraits list HD portraits
    with the same name. Backgrounds list the same resource id in the same
    story's HD release, and the closest-looking unlinked HD background.
  - **Portrait names:** each portrait gets its character names from every
    episode's scripts.
  - **Expression slots:** a slot is listed only when it really holds a
    portrait. The app fills a character's unused slots with whatever follows
    its art in the file.
- HD choice panels now appear and close as the app's do (`SHSUIMenu`
  transitions, decompiled):
  - **Appearing:** the panel and its portrait fade in over 0.25 s while the
    labels fly on. The circle timer does not fade.
  - **Picking:** the picked row shows its pressed color for 0.1 s, the timer
    disappears, and the panel fades out over 0.25 s before the story moves on.
  - **Timing out:** the panel fades out the same way. So does the rapid-fire
    quiz when its time runs out, before the game ends.
  - Ordinary choices have no label fly-off natively (only the quiz does), so
    none was added.
- HD vector text draws letters whose ink starts left of the pen (Arial
  Rounded's "j" and "f") where CoreGraphics does. SDL_ttf starts the bitmap at
  the leftmost ink, which put them up to 1.5 points too far right: the "j" of
  "just" crowded the "u". Every HD text font is affected.
- The Decision Tree's Rewind and Fast Forward bars show their labels while
  warping is still locked (Football Season unfinished), even with nowhere to
  go, as the device does; a tap brings up the "Locked" notice. Both bars now
  have the native 1-point black line along the tree's side.
- HD body text no longer drops 4 units when the speaker's name wraps to the tall
  title (animateTextLayer ignores the title; IMG_0298, "Mrs. / Sworelin").
- Choice hints also read "Score Way Up!" as a gain and "Detective Score Down!"
  as a loss.
- 4_The_Great_Float_Caper no longer stops at its first loading screen
  ("uninitialized stack word 18"). A zero-argument service 91 reads the stack
  slot above the top. HD allocates that stack once with an unfilled
  `new short[0x400]` (CSKiwiEngine::init), so a slot never written this session
  now reads as 0 (the overlay shows without holding the script). The native
  value is unverified, but the story continues either way.
- Best_Party_Ever no longer stops at its "Creep Stealthily!" word grid, whose
  alphabet has no "e". Target words are kept even when they use letters their
  alphabet lacks: the native walk places a word's own letters, and the
  alphabet only fills empty cells (docs/MINIGAMES.md 5.2). This also restores
  the words this fork used to drop in 46_Dance_Dance_Revelation ("dinah") and
  67_Basketball_Woes ("clydes"). Such puzzles keep retrying normal placement
  instead of the alphabet-only fallback, which could never form them.

- Choice-hint previews are ephemeral: a previewed branch can no longer write
  Decision Tree saves (`tree_<serial>`, the shared tree file) to the library.

### Kept from this fork where the two disagree

- Service 9 non-survey uploads wait on HD's poll download (`download_poll`).
- Service 15 with an HD bundle reads HD's own title/text words. Services
  12/19/100 take HD's default case, and 101-120 are the Decision Tree and
  Faceplace (SHS only).
- Any negative background base keeps the scene background, and closing the
  panel keeps the background and its pan position.
## v0.5.0 (upstream exp-runtime; merged into shshd-runtime, see above)

### Added

- Split EXP Runtime into formats, engine, player, SHS and CoD component wheels
  within one project and shared `exp_runtime` namespace. Pip extras select
  only the required source and dependencies; the player/desktop extras
  include both games by default. Existing source development commands and
  import paths remain supported.
- Add the public `exp_runtime.formats` API and `exp-tool inspect` / `extract`
  commands, usable without installing the engine, games or graphics packages.
- Document custom UI and EXP-tool integration, and add source/wheel audits
  and isolated pip installation checks for minimal and full installations.
- Publish all six Python distributions to PyPI from version-tag CI after
  package, desktop and iOS checks pass, using Trusted Publishing and verified
  build artifacts. Reject tags that differ from the common package version.

### Changed

- A bare Python package install now provides file tools. Use `[engine,shs]`
  or `[engine,cod]` for headless playback and `[player]` or `[desktop]` for
  the app. Game discovery, minigame state restoration and app builders support
  the component layout without changing library or save formats.

## v0.4.2 (upstream exp-runtime; merged into shshd-runtime, see above)

### Added

- Check for newer public releases once per launch on desktop and iOS, with a
  persistent **Options → Update checks** switch shared by both games. A newer
  release shows “Update available. Download here.” using the game's Yes/No
  menu skin; Yes opens its GitHub release page and No dismisses it for this
  launch. Checks run in the background, fail quietly offline, and wait for a
  menu before showing the prompt during play.

### Fixed

- Honor the script's music repeat flag on desktop and iOS. Repeating CoD
  story tracks keep playing; one-shot cues and the native CoD menu theme
  still finish normally. Pause/resume preserves the repeat setting.
- Restore the original iOS dialogue-box entrance for portrait speakers in
  both games: 120 ms from the portrait to a narrow strip, then 200 ms to full
  height. Keep the common layout and fixed-size border pieces. Save/load
  preserves an entrance in progress; older saves retain their full-size box.
- Complete the recovered dialogue lifecycle for SHS and CoD: grow narration
  from the retained portrait position, clip only the outer portrait frame at
  box completion, and use the native shake hold, scale and rotation timing.
  Early reveal taps settle the box/name while portrait animation continues.
- Restore neutral speaker entrances and delayed expression crossfades. Reuse
  speaker state across choices, and clear expression caches at native scene
  boundaries. Save version 21 preserves these states; older saves remain
  readable without replaying their current dialogue.
- Give iOS simulator installation its own five-minute timeout in CI, with
  progress output and diagnostics, so slow installs can finish after boot
  without consuming the app's verification time.
- Report the release version in macOS app metadata and direct Xcode builds,
  matching the runtime's Help/About version.

## v0.4.1

### Fixed

- Restore speaker-side background panning in SHS and CoD on desktop and iOS,
  using the native 250 ms movement and script-controlled automatic/fixed
  alignment (service 97). Preserve the current pan through pause and save/load;
  older saves remain readable without replaying dialogue.
- Include the unsigned iOS IPA and SHA-256 checksum in tagged GitHub Release
  downloads. Wait for all desktop builds and iOS verification before publishing;
  keep simulator reports in separate Actions artifacts.

## v0.4.0

### Fixed

- Fix Windows RAR decoder builds failing on unused POSIX regex detection or
  missing linkage to the system BCrypt library.
- Write portable iOS library paths and explicit IPA executable permissions,
  fixing their Windows-hosted packaging and launcher checks.
- Show the selected iOS simulator runtime and live boot progress, with up to
  ten minutes for CI cold boots and a separate app-verification deadline.
  Preserve console output, reports and simulator diagnostics on failure,
  and attempt cleanup even when simulator commands time out.
- Recognize classroom-quiz answer feedback in Choice hints, including Football
  Star's shuffled questions and finals. Correct answers turn green and wrong
  answers red without changing grades, timers, audio or saved state.
- Keep scene captions such as Football Star's “Before School” inside the
  badge, using the native 14-point Arial region for IPA fonts in both games.
  Substitute fonts fit the same region; Android bitmap labels retain their
  original layout rules.
- Restore the orange held gear, release-to-open behavior, 400 ms pause-menu
  expansion and original pause/menu click sounds in both games. Dragging off
  cancels the press; the entrance freezes story clocks and gates menu input.
- Highlight held menu rows and choices until release, canceling when dragged
  away or when the question changes. Preserve the Pause menu's side borders
  instead of stretching row backgrounds over them, in both games.
- Apply Choice hints to timed word quizzes and deferred rewards across short
  choice sequences, including Football Star's Beth conversation. Compare
  matching later answers without changing the live story or guessing scores.
- Restore solid word-grid tiles, rotating side/back faces, shine frames and
  shattering fragments followed by tile pops. Native fragment RNG draws and
  active effects survive save/load; older saves migrate without replaying play.
- Speed up iOS football by reusing sprite images and scaling them in the native
  renderer. Restore SHS's original You–Opp score strip and bitmap lettering.
  Game timing, scoring and target input remain unchanged.
- Batch word-grid tile projection in the iOS renderer and cache tile artwork,
  avoiding hundreds of image-strip commands per frame. Timed word choices
  also benefit from the shared scaling and text-baseline fixes.
- Keep glyph baselines aligned at half-pixel origins, fixing raised letters
  such as the “i” in Continue across dialogue and choices in both games.
- Restore the bottom “Touch the screen to continue” instruction in dialogue.
- Use the original Pause menu's artwork and Resume, Options, Help & About and
  Main Menu entries. Manual Save/Load is available in paused Options; timers
  remain paused while browsing those pages.
- Make iOS safe areas and letterboxing black, including the top and bottom
  margins around the game.
- Restore CoD's original menu click sound, respecting the Sound setting
  independently of Music.
- Play the original SHS and CoD main-menu themes on desktop and iOS. Menu
  music respects Music/focus settings and preserves the paused story stream.
- Restore the original dialogue Continue tab in both games, with supplied
  theme artwork and its 250 ms expansion after text finishes. Older saves
  migrate without replaying the story.
- Allow opaque files in the iOS Files picker so IPA/EXP/ZIP selection does
  not depend on a provider identifying their type before the first opening.
  The shared importer continues to validate the selected content.

### Added

- Optional **Options → Cheats → Choice hints** colors recognized near-term
  score/relationship gains green, losses or alternatives without a recognized
  gain red, and mixed effects amber. Unknown effects retain the normal style.
  The preview leaves the live story, timers, random state and saves untouched.
- Import RAR4/RAR5 episode collections on desktop and iOS, with nested EXPs,
  catalogs, duplicate detection and atomic publication. Password-protected and
  unsupported archive variants report an error.
- Show the runtime version and a clickable GitHub project link in Help/About,
  opened with the main menu's info icon.
- Import ZIP collections of EXP episodes on desktop and iOS, including nested
  folders and SHS/CoD catalogs. Episodes persist in the library without the
  source ZIP; repeated imports preserve existing episodes and saved progress.
- An iPhone/iPad app sharing the Python engine, importers, menus and game
  renderers with desktop. Native iOS drawing, fonts, audio, touch, keyboard
  and Files access support SHS/CoD libraries and existing save formats.
  Backgrounding pauses playback and checkpoints progress. The Xcode project
  supports device signing; CI produces an unsigned IPA and checksum for
  users to sign and install. See [iOS setup](docs/IOS_APP.md).

### Changed

- Replace More EA Games with **Switch Game**, preserving the original menu
  artwork, lettering and animation. Switching checkpoints the current story
  and opens the other installed game, or the chooser if it is not installed.

## v0.3.0

**Renamed from shs-runtime to exp-runtime**

### Fixed

- Implement SHS service 15's named dialogue, including its optional negative
  prefix and ignored extra arguments, using the shared dialogue renderer.
  Native defaults 14/21 now complete with zero. Existing saves stopped at
  these services resume without restarting the episode. Verified with both
  APK and IPA assets and original imported callers.
- CoD service 100 now follows the supplied native runtime's return-zero path,
  allowing promotional-link choices in What Happened to Colt, Part 2 and
  Dead Man Walking, Part 1 to continue. Existing saves stopped at these calls
  resume the actual remaining script; no browser or other app is opened.
- Read CoD's native `cod_options.sav` catalog so imported episodes use their
  original volume and category names. Folder imports, individual EXP imports
  and the episode picker now discover the selected game's catalog. The shared
  matching and update behavior also applies to SHS's `shs_options.sav` in
  existing and newly imported APK/IPA libraries.
- Preserve alternate filenames when identical EXPs are imported again in
  either game, allowing catalogs to match renamed copies. Existing content
  deduplication keeps one entry per EXP hash and preserves saved progress;
  different editions with the same title remain separate.
- Correct dialogue names and text placement with IPA fonts in both games,
  using their verified native wrapping, font metrics and normal/tall headers.
  Long names retain their original size and may straddle the box border.
  Body text stays in its own region; expanding the header no longer crowds
  the first line or adds body capacity. The shared renderer fits fallback
  glyphs/outlines to the selected header without character or scene overrides.
  Existing IPA saves retain progress and reflow the current page once.
- Correct CoD's normal dialogue to black text with dark-red speaker names,
  using its own native palette instead of SHS's blue. Theme colors remain
  separate from the shared layout.
- Share v0.1.3's SHS dialogue skin between SHS and CoD, across APK and IPA
  libraries, with each game's own artwork and native font rules. Android
  bitmap-font geometry/history and common narration/animation remain supported.
  Older IPA checkpoints reflow at their saved reading position without
  replaying the story; libraries do not need to be reimported.

### Added

- A kiwi fruit app logo, drawn as an SVG and shown in the game chooser and
  window icon. Desktop builds generate macOS and Windows app icons from it.
- Implement CoD's build/platform queries (service 70), including the supplied
  IPA's version string and the native store-unavailable result on desktop.
  Services 94/96 now follow CoD's native return-zero paths. Existing saves
  stopped at these calls resume without replaying previous story actions.
- Choose Surviving High School or Cause of Death in the launcher. Each game
  requires its own supplied assets and keeps a separate library and progress.
  **Options → Switch Game** checkpoints the current story before switching.
- Import a compatible CoD IPA, including its bundled Volume One EXP. CoD uses
  its own UI strings, fonts, relationship assets and nine music sources.
  Service 15 supports named dialogue; service 99 follows the offline no-ad
  continuation. Unverified services still stop explicitly; see [CoD support](docs/COD.md).

### Changed

- Rename the project/package to `exp-runtime` / `exp_runtime`, with
  `exp-runtime` and `exp-tool` commands. `shs` and `shs-tool` remain aliases.
- Organize game-specific code under `exp_runtime/shs/` and `exp_runtime/cod/`.
  The EXP reader, KiWi VM, common panels, saves and launcher remain shared.
- New libraries identify the game explicitly. Existing SHS APK/IPA libraries,
  launcher locations and saves remain supported without moving player files.
  Matching numeric resource IDs never resolve against the other game's assets.

## v0.2.0

### Added

- Choose English, French, Italian, German or Spanish episode titles in Options.
  The preference applies to episode lists, title sorting and desktop captions;
  search and episode selectors accept all supplied titles. Missing translations
  fall back to English. Story text keeps the supplied episode's language, and
  existing saves remain compatible. CLI lists accept `--title-language`.
- Import an SHS IPA through setup, drag-and-drop, or `shs-tool import --ipa`
  as an alternative to the Android APK, including its bundled episodes and
  Football Star. Import identifies SHS by its bundle identifier and validates
  required assets; version and build numbers are informational.
- IPA playback uses its original UI assets, including its timer wedges,
  name-entry panel and football graphics. System fonts use the installed
  original face when available, then the system default. Font rendering and
  missing-content limits are documented in [IPA support](docs/IPA.md). The
  inspected IPA omits ten music tracks the original app downloaded separately;
  scenes requesting these tracks remain silent with the IPA alone.
- Optionally supply an Android 1.0.9 APK to restore missing IPA music during
  import or later through **Add APK Music** / `shs-tool add-music`. IPA assets
  and original installed fonts keep priority. Existing IPA saves and live
  story progress are preserved; no server download is required.

## v0.1.3

### Added

- Episode surveys now show “Thanks for taking the survey!” locally and continue
  any remaining story, without sending responses to a server. Saves stopped at
  survey submission recover without repeating the questions.

### Fixed

- The HD "Continue" pill under a narrator dialogue box no longer spills past the box's own left edge and overlaps its corner for a very
  short line ("Except...", "SMASH!" in 7_5_WeddingSmashers.exp): a narrator box sizes tightly around its own text (`dialogue.py`'s
  `DialoguePage.page()`), so a one- or two-word line can be narrower than the pill itself. The pill now stays clamped to the box's own
  left edge in that case (still not confirmed against a real device photo of this specific short-line case, unlike the rest of the
  pill's measured position) -- and, since a narrator box's fixed x is already slightly negative by design, is now drawn on the same
  wider layer the box's own background uses instead of the narrower one it was on, which had been silently re-clipping it at its own
  edge even after the first fix.
- Script service 108 (`clearGlobalAccumulator`) now empties the counter it names (a character's relationship value or a global counter such as
  3100); it used to do nothing, so those values carried over. Football Star calls it nine times.
- Episodes that wait on the poll download (service 9, at the end of most episodes) show the app's "Loading / Please wait..." bar for a fixed
  second and then carry on, as the app does when the poll server does not answer; it used to skip past instantly. Mini-game and other loading
  screens are untouched.
- A save that cannot be loaded is set aside (as `.corrupt`) and the app's "Save file was corrupt ..." message shown at the menu, as the app does
  (which deletes it).
- Loading a game (Resume, F9 or a restored save) links the Decision Tree to the scene you were at again: Rewind shows its words and the
  scene is highlighted. Saves used to carry their own copy of the tree, so the scene they named was not in the tree on screen (and loading an
  old save replaced the tree you had built with the smaller one it held). Saves now keep only the scene's serial, as the app's do.
- Episodes that never turn the Decision Tree or faceplace panel on (every downloaded episode) show "not supported in this episode"
  again. The saved tree is library-wide, and the panel had treated any saved tree (or wall message) as enabling it, so the Football
  Star tree appeared beside other episodes; only the script's own enable call (`script_enable`, per episode) does now.
- A speaker name that wraps to two lines no longer lets the last line of dialogue duck under the portrait (seen in Magic School:
  Book 3's Beastmaster Kimuko); the body text was nudged up by an undocumented approximation that only made sense for a one-line name.
- A relationship badge on a left-housed speaker's own portrait (seen in Battle of the Schools: Girl, on the player's own first
  line) no longer clips off the screen's left edge; it was using the right-housing's slot positions regardless of which side the
  speaking portrait was actually on.
- HD art substitution for standard episodes (`hd_twins`) no longer risks pairing a standard picture with a different HD character
  who happens to share its numeric id (found in This is Spartan: the HD release folds one of three "Colt" ids away, shifting
  every id after it by one, so the old id-only matching would have shown "Jeeves"'s HD art on "Colt"'s line). Matching now also
  checks the two releases' own character names, and falls back to finding the same name elsewhere when the numbered id
  disagrees or is missing; rebuild an existing twin store with `tools/build_hd_twins.py` to pick this up.
- HD art substitution recognizes more genuine twins than before: a background reused under a different, unrelated id between
  releases (found in MTX: The Storm) no longer blocks a real match found elsewhere by content; two flat-colored transition
  frames (a fade to black or white) no longer register as a failed correlation check and go unpaired; and a portrait or
  background that grew unevenly rather than uniformly 2x (several found across the library) is no longer rejected once its
  identity is otherwise confirmed. A background recovered by content also required too little correlation, so an episode
  with more than one similar-looking shot (found in 4_8_Sectionals and 5_3_Paigeagainstthemachine) could leave a real
  match unrecovered as a false ambiguity; the floor is now well clear of a merely similar photo. Rebuild an existing twin
  store with `tools/build_hd_twins.py` to pick these up.
- Fixed a real bug in the built HD twin store, not just the review tool: an SD picture reused under a different identity
  by more than one story (found in 11_0_April_Fools, whose own "Monkey" costume shares its SD bytes with several other
  episodes' "Amanda") used to take whichever story's HD picture happened to build first (an accident of alphabetical
  episode order -- confirmed the store was serving Monkey's portrait for every standard episode's Amanda). The builder
  now ranks every story's match across the whole library and keeps the HD picture the most of them agree on. Rebuild an
  existing twin store with `tools/build_hd_twins.py` to pick this up.
- HD art substitution recognizes a character across releases even when one names them more fully than the other (found in
  Anger Management's own "Coach"/"Coach Kessler" and flex games' own "Judge"/"Judge Tigh"); this used to be treated as a
  disagreeing name (the same guard that catches a real identity swap like This is Spartan's Colt/Jeeves) and left unpaired.
  Also recognizes more real backgrounds than before: the sample walk that finds an episode's own art now runs longer,
  reaching a background (confirmed real content in This Friday Night) the previous, shorter walk never showed at all.
  Rebuild an existing twin store with `tools/build_hd_twins.py` to pick these up.
- The episode picker no longer shows some episodes twice. A vote pack's own HD and standard releases (MTX_Dr_Pepper_1
  through _5, Sam3, Sara3, Taylor3, Zoe3) were treated the same as two different candidates sharing a vote pack's generic
  title, which must never merge; and a same-episode retitling between releases (Getting Over Howard's own "Special:"
  prefix, The Storm Part 2's "Two" vs "2", The Floating Isle's fuller HD title) meant the two releases were never even
  compared, since the picker only ever compares episodes that already share an exact title. Both also mean HD art
  substitution now recognizes these episodes' own real HD releases instead of only ever giving them art borrowed from
  elsewhere in the library; rebuild an existing twin store with `tools/build_hd_twins.py` to pick this up.
- The HD end-of-episode card ("Want More Content?" / "Miss An Episode?") no longer shows a flat, undecorated background
  behind it where the real app shows the last scene's photo under a sepia tone. Three separate bugs combined to hide it:
  `Desktop.snapshot()` (also used to build the card's sepia backdrop) forced a real frame present (`pygame.display.flip()`)
  as a side effect of its own render, briefly flashing a live, un-sepia'd frame to the screen first; the episode's own
  teardown resets `panel.background_id` to -1 once it exits (confirmed in `test_episode_exit.py`), which left nothing for
  the generic background lookup to draw at all; and, once the background itself was showing again, `finished`/`episode_exit`
  still fell to this player's own placeholder UI for states with no native rendering (a dark title bar with the episode
  name, an "Episode complete" heading, Save/Load buttons) -- a real device never shows this, and this player only ever
  drew it here because the end card's snapshot is the sole caller that ever renders this state at all (live gameplay
  calls `return_to_menu()` the instant `episode_exited` is set, never `Desktop.render()`). `Desktop` now remembers the
  last real scene background it rendered and falls back to it once the panel's own id goes empty, the same as pausing
  mid-scene (whose `panel.background_id` is still valid) already could; and `finished`/`episode_exit` (when not a real
  error) now return a clean frame, the same early-return shape dialogue and choice screens already use, instead of
  reaching that placeholder bar.
- The HD end-of-episode "Episodes On Demand" button opened the tile-grid picker instead of the scrollable list view the
  main menu's own "Episodes On Demand" button opens; `leave_end_menu()` now takes the picker style the caller wants, and
  the end menu's window dispatch passes `'list'` for Episodes On Demand and `'tile'` for Now Airing, matching the main
  menu's own split.
- The Android-native episode list (`desktop_menu.py`) drew every category header orange; the owner's own iPad SD
  screenshots (the full list, not just one screen) confirm only "Mega Packs" is orange and every other category is blue.
  A prior pass already sampled both strips straight from the APK's own art (pack 16 frame 73 blue, frame 76 orange) and
  flagged this as a known gap without fixing it; the header now picks between them by comparing the section's title
  against the Mega Packs string, the same way the HD list view's own header already does.
- The HD Episodes On Demand list (`desktop_episode_list_hd.py`) drew every header blue, including its own Mega Packs
  row, despite already having the same orange/blue rule the fix above copied from it: `episode_index.build_rows()`
  title-cases every row's own label before storing it, but `PickerModel.mega_label` keeps the raw string it was
  built with, so the header's exact `==` between the two never matched. Now compares case-insensitively, the way
  `build_rows()`'s own sort key already has to.

### Changed

- The Decision Tree's automatic branches now follow the game state the way the app's do: each scene records what changed since the one before
  it (the gates of the app's `tree_nodes.txt`), the followed story rebuilds the state from those, and a branch takes the result its condition
  gives. Checked against the iPad's completed save: all 25 branches it could decide agree. A tree made before this has no state; rebuild it
  with `tools/explore_tree.py --reset`.
- Warping installs the scene's game state as the app does, and only scenes on the followed story (colored, not grayed) can be warped to.
- Warping starts locked, as on the iPad, until Football Season has been completed once (an existing `player.json` keeps its setting).
- The pause menus no longer list Save and Load (the app's has no such rows); F5 and F9 still quick-save and load.

### Added

- HD art for standard episodes (`tools/build_hd_twins.py --library DIR` gathers the HD release's version of the portraits and backgrounds
  a standard episode shares with a story that has both releases) is now on by default (`fill`): a picture with a twin is served as the
  twin, and every other picture of a standard episode is scaled 2x so a portrait that would otherwise show tiny inside an HD-sized
  circle fills it instead, softer than a real HD asset but no longer undersized. `off`/`twins` stay reachable only through `SHS_HD_ART`
  or a hand-edited `player.json`; there is no in-game toggle. On a story that has both releases, the standard episode with twins renders
  pixel-identically to the HD one. See `legacy/findings.md`.
- Fixed: HD art substitution only ever applied to an episode's own local pictures (resource ids 26000 and up); a picture from the app's
  shared asset bank (below 26000, e.g. a stock character reused across many episodes) never got its own twin or the 2x fill scale even
  when one existed, because the whole check was gated on the id range rather than on whether the picture was actually eligible. A
  verified same-app HD-native upgrade for a low id (a separate, older mechanism, `ContentLibrary.hd_asset`) still wins outright and is
  never run through the twin store on top of that, which would have scaled an already-HD picture a second time.
- `tools/build_hd_coverage.py --library DIR` measures how much of each standard episode's own art has an HD twin. With `hd_art` on, the
  HD picker's SD marker is now dropped for a standard episode whose coverage cache says every one of its pictures already has an HD
  twin (nothing about it still looks lower-resolution); an episode still missing some, or never measured, keeps the marker.
- The HD picker now dims the main-menu backdrop behind its rows, and captions each row with its catalog category in the otherwise-empty
  gutter above its tiles. Neither is measured against a reference photo (this player's own addition, like the SD marker itself).
- The main menu's Episodes On Demand button now opens a scrollable text list of episodes (`HdEpisodeList`) instead of the tile grid --
  a blue-bordered white card with a blue or orange category strip per group (orange only for Mega Packs, sampled from the base APK's
  own pack 16 frames 73/76) and alternating rows in blue text with a pale blue play/pause icon, colors sampled straight from the
  standard-edition app's own list screen (`desktop_menu.py`) and reproduced as flat vectors so nothing is soft at HD's size. Tap a
  header to fold or unfold its group (every group starts expanded); a tap elsewhere is a normal episode selection, reusing the tile
  grid's resume popup unchanged. Play/Resume still opens the tile grid (Now Airing now opens the chronological list described
  below instead). The card itself is one 248/255 translucent layer, same as `MenuRenderer`'s own `art.box(..., alpha=248)` for
  this exact screen, so the bare title area shows a faint bleed of what is behind it, same as the real thing; a row or header
  bar's own opaque fill on top of that reads solid, also matching. (`render_picker()` and `picker_event()` both called
  `ensure_picker()` with no style -- once per frame and once per input event respectively -- silently rebuilding
  the list back into the tile grid the moment either next ran; both now pass `self.picker_style` so the chosen
  view actually stays open.)
- The main menu's Now Airing button (and the end-of-episode card's own "Now Airing" entry) opens the same scrollable list as
  Episodes On Demand, but grouped by release year (earliest first) instead of by category -- a cross-check on the library's
  own completeness as much as a new way to browse it. The dates themselves are external research with no native source
  (GameFAQs' walkthrough changelog, Wikia, @SHSTeam's own tweets, cross-checked against a fan-made canonical episode order);
  see `docs/EPISODE_RELEASE_DATES.md` for the full sourcing and `src/shs_runtime/episode_dates.py` for the data itself. An
  episode whose own content already has a separately-dated individual release elsewhere (a season sold again later as one
  bundle, e.g. `A New Start 2: Howard's Return`) is left out of the year it would otherwise duplicate and shown in its own
  "Season Bundles" group instead; a bundle with no individual counterpart at all (`Season 1: A New Start`, `Troublemakers 3:
  Secrets Exposed`, `Battle of the Schools: Guy`/`Girl`) stays in its real year, since nothing else represents that content.
  The twelve character-specific "Vote Package" purchases get their own trailing group the same way, ahead of the bundles.
  An episode with no researched date at all (none currently) would fall into a trailing "Date Unknown" group rather than
  vanish from the list.
- Fixed two bad captions on the tile grid and both list views, which all three share one caption function
  (`episode_index.episode_label()`): `Homecoming_Taylor_2.exp` shipped titled just "Specials" -- its own file
  slot for what its three siblings correctly title "`<Name>` Medium Vote Package" -- read confusingly out of
  context in a flat list, and is now corrected to "Taylor Medium Vote Package" to match them; and `2: The
  Dance_Dilemma, Part 1`'s stray underscore now renders as the space it was clearly meant to be.
- Fixed the last row in both list views (Episodes On Demand and Now Airing) being cut off when scrolled all
  the way down: `HdEpisodeList.list_height()`, which the scroll-clamping math treats as the visible area,
  overstated it by 24px against the rect `draw()` actually clips rows to (the 2px gap under the title divider
  and the panel's own rounded-corner inset, both accounted for in the clip rect but not in `list_height()`).
  `draw()` now builds that clip rect's height from `list_height()` itself so the two can't drift apart again.
- Both list views now show a second, smaller and dulled-down line under each title (`PickerModel.subtitle()`,
  no native screen to sample): Now Airing shows the episode's own category and its researched airdate
  ("MEGA PACKS - Airdate: 11/09/2009"), since its own rows are grouped by year, not category; Episodes On
  Demand shows just the airdate ("Airdate: 11/09/2009"), leaving the category out since its own header above
  already names it. Rows grew from 58 to 72 points tall to fit the extra line.
- The HD pause menu's Help & About pages (`desktop_pause_hd.py`) can now have their text replaced per page
  (`help_text_overrides.py`'s `HELP_TEXT_OVERRIDES`), for a page whose native copy describes a service this
  runtime doesn't offer (paid weekly episodes, EA's own purchase/restore flow). Empty by default, so every page
  still shows the app's own original string-bank text until one is filled in; this player's own addition, with
  no native equivalent to preserve 1:1 against. Populated the Now Airing and About pages with the owner's own
  rewritten copy.
- A `https://` URL in a Help & About page's own body text (so far, only possible in override text -- a native
  page's body never carries a literal link) is now underlined and tappable, reusing the app's own native "Exit
  Game?" confirmation (menu 17) exactly the way the EULA/Privacy/Terms rows already do: tapping it stores the
  link and asks before leaving to open it in the browser. Used for the About page's new Discord invite link.
- Episode release dates (`episode_dates.py`) now prefer Wikia over GameFAQs on a conflict, the reverse of before:
  a direct contact from the original community confirmed the developers' only consistently-updated channel was
  a Facebook page (since deleted) that Wikia's own numbers were compiled from, and explained the small, mostly
  one-week gaps between the two sources as a real release-stage distinction (On Demand vs. Now Airing), not an
  error. 150 of 165 GameFAQs-sourced dates had a matching Wikia date and were superseded; the rest had no Wikia
  entry to match at all and are unchanged. See `docs/EPISODE_RELEASE_DATES.md` for the full reprocessing writeup.
  Populated the Episodes On Demand help page with the owner's own text, which also explains the SD badge and the
  automatic HD-art substitution shared with Play/Resume's tile grid. The About page now also states up front that
  this is an unofficial fan preservation project, not affiliated with or endorsed by Electronic Arts or
  Centerscore Inc.
- Tapping a faceplace wall link now goes through the same "Exit Game?" confirmation (menu 17) as the About page's
  Discord link and the main menu's own EULA/Privacy/Terms rows, instead of opening the browser immediately --
  this player's own addition, since the wall's native link-opening (`SHSFSMessageContentView touchesEnded:`) has
  no confirmation at all. Falls back to opening directly when no HD bundle is imported (no resource 17 to read),
  matching the base app's own behavior in that case.
- A player who owns Arial Rounded MT Bold but hasn't (or can't) install it system-wide can now drop the font
  file into their own library's `fonts/` folder instead (`vector_text.py`'s `system_font_path`), named after one
  of its own family candidates (e.g. `ArialRoundedMTBold.ttf`; case doesn't matter). Checked ahead of the OS's
  installed fonts and behind an explicit `SHS_*_FONT` environment override, the same "a file in the player's own
  library" convention the HD twin store already uses.

### Added

- A pre-configured "drop your files here before first boot" folder, alongside the app's own existing manual
  browse/drag-and-drop import rather than replacing it: an `import` folder shipped as a sibling of `_internal`
  in the distributed build (or `SHS_IMPORT_DIR`, for a source checkout) can hold the base APK, the HD ipa, any
  number of font files for the player's own `fonts/` folder (`vector_text.py`), and two episode folders
  (`shs_episodes`, `shshd_episodes`) -- each accepting files directly inside them or organized into further
  subfolders, flattened into one set at import time the same way a folder already dropped onto the app's own
  browse screen does. Checked once on startup when no library exists yet; an absent or empty folder is not an
  error (most players never touch it), but files staged with no `.apk` among them is, so an incomplete drop
  doesn't fail silently. See `staged_import.py`. `tools/build_desktop.py` now also creates the `import` folder
  itself, empty, with its `shs_episodes`/`shshd_episodes` subfolders already in place in the distributed
  Windows/Linux build, so a player has an obvious spot to drag files into rather than needing to create it by
  hand (macOS's `.app` bundle has no matching sibling-of-`_internal` location, so it's skipped there).
- The About page's "Version: ~276~" line now reports shshd-runtime's own release (`desktop_pause_hd.py`'s
  `VERSION`) instead of the native app's own build number (1.4.38) that token originally stood for -- the only
  place it appears at all (checked against a real HD string bank) is the About page, and only this project's own
  override of it is ever shown, so there's no other native text this could affect. One constant to edit on a
  release, not the whole About body; `pyproject.toml`'s own version now starts matching it too. First release:
  **1.0.0** -- substantial, broad functionality (real HD rendering, the Decision Tree, faceplace wall, a staged
  import pipeline, extensive performance work) well past the 0.1.x the upstream project this forked from is
  still at, even without the formal API-stability guarantees a 1.0 traditionally implies for a library.

### Fixed

- The setup and "Importing content" screens (anything shown before a library exists yet, `desktop_menu.py`)
  rendered visibly blurrier text than the rest of the app: a fallback to pygame's own crude built-in font
  instead of a real installed face. Now uses the same OS-font search (`vector_text.py`'s `system_font_path`)
  every other screen already relies on, and renders each line at 3x size before downscaling it to the exact
  footprint the normal size would have produced, so the antialiasing survives this screen's own ~1.6x upscale
  to the window far better. See `legacy/findings.md` for why this screen is softer than the rest of the app to
  begin with, and what a full fix would take.
- Trying to warp the Decision Tree before Football Season unlocks it (`touchesEnded:` behavior) printed the
  native "Locked" message (string 271) as a bottom-bar toast instead of the real modal window the app uses for
  it (menu 28 -- title 127, an orange OK button, pausing input behind it until dismissed), the same native
  menu-engine mechanism the faceplace wall's own "Exit Game?" confirmation already draws. `Desktop`'s wall-only
  `wall_menu_data`/`wall_windows`/`wall_stack`/`wall_pressed` are now the shared `notice_data`/`notice_windows`/
  `notice_stack`/`notice_pressed` both features queue onto, so the lock opens the real window instead; the toast
  remains only as a fallback with no HD bundle imported (no resource 17 to read menu 28 from, same as the wall).
- The HD football minigame's coach portrait, sliding in over the "Offensive/Defensive Plays" instructions panel,
  rested far short of the frame's own right edge instead of flush against it: `football_layout.py`'s
  `help_motion()` computes everything in its own native 320-wide SD coordinates (its own module docstring says
  so), including the coach's resting position (`320 - coach_width`), but the HD renderer's frame is 768 wide --
  a different, independently-measured image, not an SD one scaled up -- and was using that SD-space x directly
  as an HD pixel position. `help_motion()` now takes the resting edge as a `frame_width` parameter (default 320,
  unchanged for the standard renderer); the HD renderer passes its own frame's width.
- The timed rapid-fire quiz (`session.engine.word_game`, e.g. "Get Snacks," "Concentrate!," "Bonfire!") never
  showed its own category banner ("Snacks!" in the decorative title font above the box) -- `engine.py` always
  supplied an empty title for it, on the strength of an earlier, unverified comment claiming the native app
  deliberately discards this argument. Statically decoding real `host_call(71, ...)` sites in an imported
  episode's own compiled bytecode (Football_Star.exp has a dozen; "Get Snacks" is one of them) showed the
  discarded argument is a real, populated string every time -- `'Snacks!'`, `'Concentrate!'`, `'Bonfire!'`,
  one per quiz topic -- not blank at all. No new rendering code was needed: `ChoiceLayout.page()` already lays
  a title out at the portrait-adjacent banner position in the right decorative font for every choice type,
  title included, and `desktop_choice.py` already draws it unconditionally; a word_game choice just never had
  one to draw. See `legacy/findings.md`.
- A long two-word speaker name not already hand-measured into `speaker_names.py`'s own named branches (unlike
  `"Howard's Mom"`, `'French Teacher'`, ...) could render on one line in a dialogue box sized for two, floating
  above the box instead of attached to it, with the box left empty where the (unwrapped) name should have
  wrapped into it ("Mrs. Sworelin," a teacher who isn't one of the specifically-measured names). The generic
  fallback branches for this case (`elif state.lines < 2:`, `elif len(text) < 19:`) compute a box width sized
  for padding, not for actually constraining the word-wrap, and for some names that padded width ends up wider
  than the name's own natural (unwrapped) width -- so it never wraps. Both branches now clamp the wrap width to
  strictly less than the natural width whenever the name was already measured as not fitting one line (`large`),
  guaranteeing `layout_label`'s own word-wrap actually breaks it, without touching the already-correct
  hand-measured named branches or the fixed-width "very long name" fallback. See `legacy/findings.md`.

### Performance

- Fixed the football and word-grid minigames (and, to a lesser extent, every other HD screen) spending most of
  each frame re-reading and re-`zlib`-decompressing HD app bundle resources from the imported ipa's own zip
  archive: `ContentLibrary.hd_raw_resource()`/`hd_asset()` had no cache at all, so an `available()` gate
  re-evaluated every rendered frame (`HdFootballRenderer.available()`, `HdWordRenderer.available()`, ...) paid a
  fresh zip read for every resource it checked, every single frame, even though the ipa's own content never
  changes mid-session. Profiled live against a real HD bundle: football gameplay dropped from 4.22s to 0.78s
  over the same 90 frames (~47ms/frame to ~9ms/frame, roughly 5.4x).
- Fixed `Desktop.render()`'s renderer selection building one dict literal out of every action type's own value
  (word grid, football, character picker, loading, message panel, presentation, text input) and then indexing
  into it by the actual action's name -- Python evaluates every value in a dict literal up front, so selecting
  one action's renderer still ran every *other* action's own `available()` check first, multiplying the cost
  above by roughly the number of branches. Rewritten as a dict of callables, evaluated only for the selected key.
- Fixed `LayoutBank.rectangle()` (`ui_assets.py`) -- the single function every native UI layout computation goes
  through (dialogue, choice, menu, message, title, input) -- re-walking its node tree from scratch on every call,
  even for a node id it had already answered the frame before. Now cached per `(bank, layout_id, node_id, rect)`,
  since a parsed layout bank is immutable and the same question always has the same answer. Measured live in
  ordinary dialogue (holding one line, portrait steady, no transition): ~13.8ms to ~6.9ms per frame, roughly 2x,
  with the relationship-icon placement that originally surfaced this (~13 full tree walks every single frame)
  no longer showing up in a profile at all. `android_asset()` got the same read-caching fix as `hd_raw_resource()`
  above, for the same reason.
- The game saves itself the way the app does: every 60 seconds of play, and once when the window loses focus (as well as on Main Menu and
  when closing), so a crash costs at most a minute.
- The faceplace wall scrolls: the mouse wheel or a drag moves it, it stops at both ends (no bounce), a new post scrolls it back to the
  newest, and a scroll indicator shows for a moment. Tapping a linked post ("Tap here to get ...") opens its link in the browser.
- Braces and `>` in posts are the app's emoticons (a frown, a heart, a smile) on the wall and the alert; a continuation with a picture
  draws it framed; the alert plays its sound (`0x1f52`) once it has slid on.
- Warping keeps the side panels open (the tree scrolls to the scene you warped to).
- The Decision Tree is drawn the way the iOS app draws it, from its decompiled node classes: rows, branch offsets and stubs where each
  node's shape puts them, forks spaced by how wide each branch is and rejoining below, exit labels with their white boxes, outlines
  and the yellow path / black story / gray off-path colors. The scene you are at is outlined in yellow, icons off the story you followed
  are grayed, and Rewind / Fast Forward show their words only when there is a scene to go to (blank and inert at the first or last scene).
  Fixed a story tree that stacked scenes at one spot after replays that met a repeated join.
- The Decision Tree zooms with the mouse wheel (about the pointer; Shift+wheel or a drag scrolls, the middle button fits the tree
  to the panel again).
- `tools/stage_tree_save.py` copies an iOS save folder and replaces the copy's `tree_nodes.txt` (the app's own text form of the
  tree, now readable and writable in `shs_runtime.native_tree`) with a simulated tree, after checking it against what the app's
  loader accepts (a file it rejects makes the app delete the game's main save).
- The Decision Tree labels each branch you have taken with its exit label ("Sports", "Girls", "TV") beside a yellow stub, keeps the
  labels of earlier playthroughs on the gray stubs of the other results, and no longer stacks a fork's branches on one lane.
  Long trees scroll (mouse wheel, or drag) and centre on the current scene when the panel opens; they zoom out only to a readable size.
- `tools/explore_tree.py --library <dir>` plays the built-in Football Star (or `--episode`) through again and again, taking every
  choice and football / word-game / grid-game outcome across the runs, so the tree and every scene's warp save fill in. Add `--reset`
  to start from an empty tree.
- The Decision Tree's warp feature works: open the side panels (Tab), tap any scene on the tree to jump back to it, or use
  Rewind / Fast Forward to step to the scene before or after the current one. Every scene's starting point is saved when the
  story first reaches it (`dtsaves/` in the library), your names, `$USR` and the tree itself are kept, the message wall is
  emptied and the game fades in from black. The feature starts unlocked (`warp_unlocked` in `player.json`; locked, a tap shows
  "Please complete Football Season episode to unlock this feature."). Trees recorded before this version only become warpable
  as their scenes are played again, and a scene that follows a plain node now continues in slot 0 as the app does.
- Relationship-icon rings now disappear after their 0.5 s pop-in (only the icons stay), the portrait ring is complete until the
  dialogue box has finished growing, and it is clipped against the box 3 units closer, so it crosses the box's colored border line like
  the iOS app. Football Star uses the iOS HD bundle's scripts (Faceplace and Decision Tree support) when an HD bundle is imported, and
  the main menu plays its music (once, as the app does) when you arrive and when you return from an episode.
- The launch and main menu are now the iOS HD ones when an HD bundle is imported: the EA loading screen, "Play with sound?", the
  EA flash, and the main menu with its photo / ribbon / title entrance and sliding buttons (positions and timings decompiled and fitted
  to your photos). Help & About (with Push Notifications and the legal page), Options (light-mode switches and sliders, the same as
  the in-game ones; volumes now persist and start at 50), the legal / usage-sharing windows and "Delete Saved Game?" come from the
  app's own menu data. Finishing an episode shows "Want More Content?" (Football Season) or "Miss An Episode?" over the sepia last frame.
  Wider windows show the faded collage beside the frame. More EA Games reports a connection error, as the app does offline.
- The episode picker is now the iOS HD one when an HD bundle is imported: rows of preview tiles (one row per catalog category,
  HD's `shs_options.sav` first, Android's optional) over the main-menu photo, sideways and vertical scrolling, and a resume
  popup with the preview and your saved game's screenshot. Episodes that exist in both releases show once, as HD; standard-
  only episodes carry a small "SD" tag. Missing previews are rendered from each episode's title card while a library is set
  up (or first opened), and saved games get a screenshot when you leave the episode.
- HD message panels ("Instructions", "The End") drawn like the iOS app, checked against photos; the continue pill's label
  is TrebuchetMS Bold as in the app. With an HD bundle, build queries use HD's answers, so Football Star's ending shows the
  app's "tune-in each week" text. Relationship icons keep their ring for the whole line and sit above the portrait art; lost
  icons circle before falling. Story-tree joins merge by script position. Service 38's icons show on the next text change.
- Music crossfades: a different cue fades the playing one out over 1 s before starting. The story-tree panel now merges join
  nodes, keeps one branch under choice / game nodes like the app, and only waits for results on the node types that do.
  Save format is now version 19.
- Scene transitions between story elements (blinds or fade to black, queued by script service 16) now run like the iOS app,
  with input off while they play.
- HD relationship icons fly in on arcs with the ring effect and fall when lost; HD dialogue shakes (service 89) use the
  decoded keyframes; the scene label slides back out when dismissed; music honors its loop flag.
- Every script service the HD binary implements now has a handler (about 25 that no shipped episode calls: string formatting,
  entity name copies, int arrays, weighted random, music pause, hide loading bar, more story-tree calls). Save format is now
  version 18.
- HD portraits change expression like the iOS app: a portrait starts in the expression the character last showed (neutral
  for a new speaker) and fades to the line's own a second in, with the angry starburst and the yellow / blue / white
  emotion balls for expressions 6-9. Save format is now version 17.
- The gear's touch area matches the icon (its left part in the side margin and its top rim did nothing before).
- Script services: yields 111 / 112 (story-tree branch and join nodes), 15 (titled dialogue), 9 (download poll) and the
  ids the native dispatcher ignores (14, 21, 100, ...) no longer stop an episode; Football Star now plays through to
  its exit in a scripted run.
- HD story scenes pan the background with the speaker like the iOS app (left-hand speaker: image flush
  left, right-hand: flush right, narration keeps the last side; 0.25 s move), and script yield 97
  (`setLocationPan`) pins the side. Save format is now version 16.
- Merged upstream `shs-runtime` v0.1.2 (commits `2cf78b8f`..`01b73c30`, on top
  of the `d01bf1a7` this fork started from):
  - Android's randomized choice order (service 4 with a shuffle argument):
    choices keep their script return values and saved random state, and saves
    stopped there resume without replaying earlier progress.
  - The name-entry screen (services 17/40): native APK layouts, bitmap fonts,
    cursor and rejection alert, keyboard rules, and drafts that survive
    save/load ([NAME_INPUT.md](docs/NAME_INPUT.md)). Drawn at story density
    through the same window-resolution layer as dialogue and choices.
  - The Android timed-choice panel (layout 22, assets 708/709), used when no
    HD app bundle is imported (an episode that never shipped on HD); with one,
    the HD wheel below is kept and the box keeps its ordinary footer.
  - Service 91 with zero arguments (the APK-bundled New Girl episode) and
    exact-zero choice expiry, which now happens strictly below zero.
- HD scene label, title / week cards and character selector, rebuilt from the decompiled native code: the label is
  ArialMT at HD density with the native slide (0.5 s delay, 0.6 s bounce) and wraps in its region; the title card is
  full-frame with the native wipe / fade timing and HD's image fonts; the selector is a full-width panel with HD-sharp
  portraits and the button where HD puts it.
- Fixes from the first live HD run: translucent dialogue bubbles, HD's narrator box size and position, the pressed
  state of odd choice rows, faceplace promo continuations (one post and alert instead of two), an HD loading screen
  and scene label, the trademark sign on the About page, and a large frame-time cut (a cached bundle lookup).
  Saves are version 15; older saves still load.
- The story-tree and faceplace panels now honor the script's own enable calls (services 101 and 114), so HD's
  bundled Football Star shows its (initially empty) faceplace wall instead of "not supported in this episode".
  Saves are version 14; older saves still load.
- HD choice panels follow the light-mode photos: lighter option labels, tinted alternate rows (blue and gold
  themes photographed), corrected header/row spacing and box position, and HD's timer wheel. The pause menu's
  rows now alternate lavender-gray and pink as photographed.
- HD pause menu. The in-game gear menu now matches the HD app: the scene dimmed sepia with the Pause card
  (Resume, Options, Help & About, Main Menu), the real Options (music and sound switches, volume sliders that
  work) and Help & About text pages (Introduction, Controls, Now Airing, Episodes On Demand, Network, About).
  Save (F5) and Load (F9) rows are kept as host extras; Escape steps back one screen.
- HD word game. With the HD app bundle imported, the word game is drawn in the full 768 x 1024 frame with
  HD's own art: real 3D letter cubes (selection, hint pulses, flips, pop-in), the scene background with haze and
  clouds, the portraits in their rings, the question and keyword text, tutorial popups, banners, the flying "+N"
  score with the counting digits, and the shard bursts, checked against photos of the real game. Input uses the
  projected cells. Game rules are unchanged; a found word now also records its cells for the effects.
- HD football. With the HD app bundle imported, the football minigame is drawn with HD's own art in the
  768 x 1024 frame: the scrolling turf and yard lines, scoreboard, the 3 x 3 play grid with yardage numbers,
  help panel and coach, countdown, down/time banners (including the spinning ones) and the touchdown stars,
  checked against photos of the real game. Game rules are unchanged.
- HD side panels. The Tab panels now use HD's own art: the story tree with the
  real node icons (colored on the current lineage, gray elsewhere), yellow path
  lines, the "Rewind" / "Fast Forward" bars and dark dividers, and the faceplace
  wall with faces, the sender's name and a rule under each message. An episode
  with no story tree or wall (or the main menu's own landscape view) gets HD's
  "not supported in this episode" state: the faded school collage with the
  original message, matched to the real screen. The collage is read from the
  imported app bundle (resource 10, an Apple-format PNG that `cgbi.py` decodes).
- HD name-entry screen. With an HD app bundle imported the panel is HD's own
  layout 46 (its translucent frames, Pajama Hip typed name and bar cursor,
  centered by the prompt's height), matched to a photo of the real screen to
  about a pixel, with the HD bottom bar and gear under it.
- HD faceplace alert. The card that slides in at the top right when a
  faceplace message arrives is now drawn from HD's own frames (header with
  "faceplace alert", rounded body, the sender's face in its ring and disc) at
  native pixels, cut by the screen's edge as on the device; it slides in over
  0.2 s.
- HD vector text. With an HD app bundle imported, story text is drawn from real
  vector fonts instead of the Android bitmap atlases, the way the HD build does
  (`SHSEngine::initFonts`): every font's size is exactly twice the number in
  its Android name, glyph advances come from the font with no kerning, and
  Pajama Hip titles are the TrueType face inside the bundle, filled per theme
  with a white outline. Layout code is unchanged, so wrapping, indents and
  vertical placement stay native while glyph shapes and widths match HD (the
  Android "Arial Rounded" atlases were generated from a generic Java font, so
  their widths never matched). Fonts are found on the player's machine, never
  bundled: Arial Rounded MT Bold when installed (macOS, Office), otherwise
  Arial Bold / Liberation Sans Bold, with `SHS_ARIAL_ROUNDED_FONT` and
  `SHS_VECTOR_TEXT=0` overrides. See [UI_FIDELITY.md](docs/UI_FIDELITY.md#hd-vector-text).
- HD's real frame geometry. HD lays its UI out in a 384x512-unit frame (an iPad's
  768x1024 points at half size): the 320x480 column sits in it 32 units from each
  side, 5.5 units above the bottom, at ~3.9 px per unit at 1500x2000 (this build
  fitted the column to the window height at 4.17, which is why HD's boxes measured
  ~6% narrower), the background fills the whole frame (offset 48 units right and
  20.5 up from its Android focal point, matched against two HD photos), and the
  bottom bar and gear run to the frame's edges. With it, the HD dialogue and
  choice screenshots line up with ours to within a few pixels at 1500x2000.
- The bottom bar and settings gear are HD's own 2x art (resource 155 frames 55/56
  for the bar, 58 for the gear at 0.915 of its nominal size, 59 pressed), drawn
  edge to edge and flush in the bottom-left corner on every screen that has them
  (dialogue, choices, the word grid, football, the character picker, message
  panels and title screens); Android's frames 47/49 are the fallback. The menu
  button's hit area follows the gear out of the column.
- The Strength Up notice follows HD's letter effect (read from
  `SHSUIDialog::startLetterEffectAnimation`): letters start 50 ms apart, rise from
  3 cap heights below while fading in over 200 ms, hold, then leave upward while
  fading out over the last 150 ms, all ending together at (n-1)*50+1550 ms. It is
  drawn in red Trebuchet Italic (size 20 units, `0xf0513c`) with a same-color
  thickening stroke and a 9/40 white outline, as in HD.
- The Continue pill expands: its height scales from ~0 to full over 250 ms once
  the text has settled (`GameModel::expandContinue`).
- Timed choices in HD have a 33-unit footer under the last row and option lines
  17.5 units apart (rows stay 44), and the wheel is ~22% of the box width.
- HD's real dialogue portrait housing, decoded from the binary
  (`SHSPortraitLayer.drawInContext`): the outer ring is HD frame 46 (a crisp 256 px
  ring-and-fill, not the stretched Android frame), clipped against the dialogue
  bubble so it never draws inside the box; the inner disc is a vector-filled circle
  in the theme's exact colors (pale blue / pink / gray) instead of Android's frames.
  It reaches into the frame's side margins, so dialogue and choices now draw on a
  canvas as wide as the whole 384-unit frame. The character picker uses HD's
  selection rings (frames 46/47/48). The HD layout bank turned out to be resource
  16 (and the strings 15), not the "undeciphered" 13/14; see
  [findings](../legacy/findings.md).
- The iOS HD build's own name-entry rules, read from its `SHSUITextEntry`
  (see [NAME_INPUT.md](docs/NAME_INPUT.md#ios-hd-build)): the first letter is
  capitalized, later letters keep their case, and there is no 16-character
  cap. Applied whenever an HD app bundle is imported.

- Read the iOS HD build's version-19 `shs_options.sav` episode catalog. That
  envelope differs from Android versions 16-18 (u16 entry count, no separate
  current-episode slot, one extra per-entry alias string, fixed trailer); see
  [Version 19](docs/EPISODE_CATALOG.md#version-19-ios-hd-build). Verified
  end-to-end against one real HD file (195 entries, 25 categories).
- Implemented the iOS HD build's DTView/Faceplace syscall cluster (services
  101-120, native cases `0x65`-`0x78`), verified from raw disassembly of the
  HD binary's own dispatcher rather than its unreliable decompiler output;
  see [iOS HD-build-only services](docs/ENGINE_ABI.md#6-ios-hd-build-only-services-faceplace--dt-view).
  Unblocks the HD build's native Football Star, which now runs cleanly
  through its entire story opening (278 dialogue lines) with no unhandled
  services. Confirmed this cluster is also the real mechanism behind a
  long-standing avatar-picker gap from earlier KiWi-bytecode-only research,
  recovering its actual 5 portrait ids live.
- DTView (a persistent decision-tree/progression outline) and Faceplace (an
  ordered, timestamped social-wall message feed) now capture real content
  instead of safely discarding it: `DTView`/`FaceplaceWall` in the new
  `dtview_faceplace` module. The real per-argument mapping (which yield
  argument is the node type vs. label vs. exit label vs. message/from/
  expression/url) was recovered by hand-disassembling the raw Thumb-2
  `SHSScript::syscall` call sites -- Ghidra's decompiler is confirmed wrong
  at the argument level for these specific calls -- and verified against
  real content: running HD's own Football Star now builds a `DTView` tree
  whose labels read as a real story-progression outline ("Week 1" -> "Meet
  Beth" -> "What are you into?" -> ...) and a `FaceplaceWall` full of real,
  in-voice social posts. See
  [DTView/Faceplace real per-argument mapping](docs/ENGINE_ABI.md#62-dtviewfaceplace-real-per-argument-mapping-from-raw-thumb-disassembly).
  In the process, found and fixed a real argument-count bug: yield 117
  (`incomingContinuationMessageImage:url:`) was draining only 2 words
  (assumed to share yield 116's shape, never confirmed live); it actually
  needs 3. The on-screen diagram/wall drawing routines themselves are now
  implemented too -- see the DTView/Faceplace side panels entry below.
- A "faceplace alert" corner toast: when a new Faceplace post arrives, a
  card (header, poster portrait, name, message text) appears in the
  top-right corner and fades out after a few seconds, independent of the
  still-unbuilt full side panel. Confirmed against a real HD gameplay
  screenshot rather than decompiled -- an exhaustive symbol-table search of
  `SHSFSView`/`SHSViewController` found no matching alert/toast/badge
  method (`SHSEngine::handleBadges`/`decrementBadgeNumber` turned out to be
  the iOS home-screen app icon badge, unrelated), so the trigger condition
  and timing are a best-effort match to that screenshot, not a recovered
  native constant. Save format bumped to version 13 for the new DTView/
  Faceplace/toast fields (added earlier this session without a version
  bump); older saves migrate in an empty tree/wall and no pending toast.
- DTView and Faceplace now render as real, toggleable side panels
  (`desktop_panels.py`) instead of just capturing data. Recovered the real
  layout algorithm from raw disassembly of `-[SHSDTView
  layoutNodeInSubview:withParent:]`: a Reingold-Tilford-style recursive
  tree layout, confirmed to be the *same* drawing code across all 23 real
  DTNode subclasses (read every one of their vtables directly rather than
  assuming from a sample). Built with a simpler direct layout algorithm
  that produces the same real tree shape rather than replicating the
  native accumulator/tile-recycling implementation node-for-node -- see
  [DTView/Faceplace side panels](legacy/findings.md) for exactly what was
  and wasn't reconstructed. In the real app both panels slide on/off
  screen on a portrait<->landscape device rotation; this desktop app has
  no such gesture, so it's bound to the Tab key instead (user's choice).
  Panel arrangement (DTView left, Faceplace right, flanking the game view)
  matches a real landscape-orientation reference screenshot rather than
  simulating the portrait-mode top-ribbon/sidebar shapes and a rotation
  transform on top of them.
- Three corrections to the panels above, from comparing against a real
  device and a copy of its own save data (`tree_<serial>.sav` files and
  debug text dumps confirming the exact persistence model): panels now pop
  the window open (3:4 -> 4:3, the center game view keeping its original
  size) instead of overlaying it, and render at real window resolution
  instead of the blurrier fixed canvas budget; the DTView tree now
  persists across separate playthroughs in a library-wide
  `dtview_tree.json` (outside any one save, matching the real app's own
  tree files) and correctly reuses/updates existing branches instead of
  always starting fresh, with previously-explored-but-inactive branches
  shown desaturated alongside the current path; the corner alert no longer
  fires while its own panel is already open. See
  [DTView/Faceplace side panels](legacy/findings.md).
- `shs-tool import --hd-ipa` (and dropping an `.ipa` alongside the APK in
  the desktop app) optionally imports the iOS HD build's own app bundle.
  Never required. Every background/portrait asset id from 1000 up to
  (not including) 25000 ships at the identical numeric id on both
  platforms -- confirmed by sampling 667 overlapping ids, 606 genuine HD
  upgrades of the exact same asset, verified by rendering and comparing,
  not just matching sizes -- so importing an HD ipa transparently upgrades
  every one of those to its real HD-native art. A small, separately
  verified table (`content.HD_ASSET_MAP`) covers the handful of lower-id
  chrome assets that are numbered differently on HD, currently the
  dialogue/choice/character-picker portrait mask (Android id 268 -> HD id
  311). Ids at or above 25000 (KiWi bytecode programs) are never touched.
  Audited across the real 195-episode HD library: HD background coverage
  went from 53% to 100% of episodes once an HD ipa was imported, with the
  same driver and zero decode errors either way. See
  [Content library contract](docs/RUNTIME.md#content-library-contract-version-1).
- DTView side-panel nodes now record a label for every result slot they
  offer, not just the one actually taken (`DTNode.choice_labels`), sourced
  from the game's separate choice-presentation syscalls rather than
  addNode's own (confirmed-empty) label arguments. Confirmed against a real
  device's live `tree_nodes.txt` debug dump captured over USB (iPad3,1, iOS
  8.4.1): a branching node there lists a label for every slot regardless of
  which one was explored. Slots with a label but no explored branch now
  render as an outline-only placeholder in the tree instead of being
  omitted, matching the real "see all the choices map out" tree behavior.
- DTView side-panel nodes now draw a small icon badge matching their real
  node type (`NODE_TYPE_IMAGE_ID`/`ICON_COLORS`/`_draw_node_icon` in
  `desktop_panels.py`) instead of a plain colored box -- diamonds with
  paired dots for choices, a heart for dates, a laced oval for the
  football minigame, a diamond with "?" for quiz/final nodes, and a
  triangle for branch/join connectors. The per-node-type mapping is real,
  recovered from raw-disassembling each of the 23 `DTNode_*` subclasses'
  own `get_image_id()` getters; the glyph art itself is this renderer's
  own design cross-checked against real device screenshots of the
  unlocked, populated tree, not recovered native sprite assets. Ghost
  placeholders (offered-but-unexplored choices) intentionally draw no
  icon, since their node type is never actually known.
- The dialogue box border pack now upgrades to real HD art when an HD ipa
  is imported. HD renumbers each of the four per-theme packs (204/220/236/
  252 on Android become 247/263/279/295 on HD) but keeps the identical
  14-frame layout, confirmed by parsing both -- a direct id substitution
  via `content.HD_ASSET_MAP`, activated automatically through the existing
  `read_asset()`/`hd_asset()` path with no renderer changes needed.
- Dialogue now shows a real "Continue" button once the text finishes
  revealing, when an HD ipa is imported: HD-only content
  (`content.HD_ASSET_MAP[155]`), positioned and styled per real-device
  reference photos of settled dialogue lines, replacing this build's
  implicit tap-anywhere affordance. See `DialogueRenderer.draw_continue()`.
  Its vertical position accounts for `box()`'s own border art having
  ~16.5px of padding before its colored line actually starts -- found by
  sampling this renderer's own canvas pixels directly, not assumed; an
  earlier pass measured the button correctly against real photos but
  anchored that measurement to the wrong (unrendered) reference line.
- Timed choices now show a filling circular wheel straddling the choice
  box's own bottom border instead of "Xs" appended to the footer hint
  text, matching real HD behavior -- position, size, 12-segment coloring
  and fill direction all measured directly against real-device screenshots
  of an active timed choice (including the exact same "parking ticket"
  choice this session's own driver reaches, at three different elapsed
  points). Depletes from a full wheel as time runs out rather than filling
  from empty (real device behavior isn't fully confirmed either way from
  static screenshots alone -- implemented per explicit direction). The
  exact native 16-frame composite (also HD-only content at the same
  resource as the Continue button) isn't reproduced pixel-for-pixel --
  `ChoiceRenderer.draw_timer_wheel()` draws the same real-device-measured
  appearance with plain pygame drawing instead of compositing the real
  frames at a guessed, geometrically-inconsistent position. See
  `legacy/findings.md` for what would be needed to make this pixel-exact.
- The choice panel's own portrait no longer renders too small with a
  large gap of empty ring backdrop above the hair. Unlike the main
  dialogue panel's portrait (genuinely bottom-anchored, confirmed against
  real photos), this panel's real device behavior turned out to be
  top-anchored -- pixel-traced directly against a real screenshot of the
  exact same choice: the portrait fills the ring almost edge to edge, not
  anchored to one edge with the other left wherever the art's height
  happens to land. `ChoiceRenderer.draw()` now positions it accordingly.
  (An earlier attempt in this same area only fixed which ring frame the
  anchor read its size from, not the anchor model itself, and made this
  visibly worse.) Its size was also wrong: `portrait()`'s own HD-vs-
  Android scale (a "contain" fit, correct for the dialogue panel) left
  this specific asset short on height since its HD source and Android
  original don't share an aspect ratio -- confirmed with a zoomed,
  matched-scale comparison against real HD showing the portrait's own
  bottom curve falling short of the ring's. `ChoiceRenderer.draw()` now
  rescales to the real measured target (94% of the ring's own diameter)
  instead of trusting that contain-fit result as final, and anchors it
  slightly above the ring's own top so the shoulders stay inside the
  ring's bottom edge (confirmed against a matched-scale zoomed comparison
  with real HD).

- The dialogue panel now draws at 2x density (`STORY_SCALE`) and is
  composited once at window resolution, so HD portraits, emoticons, the
  Continue pill and box borders keep their real pixels instead of being
  shrunk to 1x and stretched back. Android-only art (rings, footer, gear)
  and all text (Android bitmap fonts) are still upscaled and soft.

- The choice panel (including the timed wheel and word-game variant) draws
  at the same 2x density and composites through the same window-resolution
  layer, so its HD portrait and box border are crisp too.

### Fixed

- The HD gear is drawn at its layout size (74 x 72 units) at the position measured from
  a photo of the real screen, instead of 8% smaller and flush in the corner.
- The dialogue and choice portraits of HD art are drawn at their own 2x size
  (226x256 is 113x128 layout units) instead of being fitted into the Android
  original's size. Beth's near-2x pair hid the difference; the player avatar's
  smaller 94x123 original made it ~20% too small (confirmed against a real HD
  photo). With vector text the dialogue body also wraps at its measured 246
  width, which reproduces HD's line breaks.
- HD dialogue text no longer runs under the portrait ring. Against two real HD
  photos (a portrait on each side) the body text sits 6 units lower and 6 further
  from the box's left edge, and the ring's center is 5 units below the box's top
  line (it had been calibrated at 29 against the old, too-thick borders). The
  ring frames are now drawn beneath the body text, as in HD, and the portrait
  art above the relationship icon.
- Small vector text no longer sits ~16 layout units too low. The Android font
  descriptors' `common base` is meaningless (26 whatever the line height), so
  the baseline now comes from each bitmap font's capital H; the bottom bar's
  hint had been pushed off the screen.
- The bottom bar shows its hint again on choices ("Touch the best choice", or
  "Touch choice before time runs out" for a timed one, as in HD) and, new,
  "Touch the screen to continue" in dialogue, all from string bank 13.
- Downloadable HD episodes ship their portraits at 2x inside the episode file
  (226x256, 256x256, ...). With no Android copy to compare against they were
  treated as mask-sized, so any 1x consumer (character picker, panels) drew
  them 13% too big (128x145 instead of 113x128). They are now recognized as
  2x art, clipped with exactly twice the portrait mask, and drawn at half
  size in logical units.
- The native 12-row portrait crop now lives in `DialogueRenderer.portrait(...,
  crop=True)` with a shared `portrait_rect()`, used by dialogue, choices and
  the appearance picker. Dialogue's anchor is unchanged on screen: cropped art
  aligned to the inner ring ends where the previous uncropped art aligned to
  the outer ring did (independently confirmed by decompile and by the HD photo).

- HD-substituted box border packs are no longer drawn at native 2x pixel
  size in 1x layout units: borders were twice as thick and boxes ~10 units
  wider per side on every screen that uses `box()`. `DialogueRenderer.frame()`
  now returns chrome at its logical (Android) size.
- `get_character_art_base` (yield 73) no longer raises for a character
  that never received a matching `set_character_art_base` (yield 72); it
  now reads 0, matching native's zero-initialized entity table. Found by
  driving the real HD build's own Football Star bytecode (loose `kiwi`
  files in the HD ipa, not the Android APK's `.exp`-wrapped version, which
  predates this syscall cluster and never exercises it): HD's compiled
  script calls yield 73 directly at a point where Android's script instead
  calls a subroutine that guarantees initialization first, byte-identical
  up to the exact instruction where the two diverge. This previously made
  every real HD episode unplayable through this runtime immediately after
  character creation.
- Faceplace wall posts referencing `$USR` (e.g. "Say what you will about
  $USR, but...") now correctly substitute the player's chosen name instead
  of showing the literal token. `incomingMessage:from:expression:`/
  `incomingContinuationMessage{Text,Image}:url:` (yields 115/116/117) now
  resolve message/caption text with substitution applied, matching this
  engine's own established dialogue pattern; found and confirmed by
  actually playing a real HD episode interactively.
- The story background no longer goes blank/black immediately after the
  football minigame (or more generally, immediately after any dialogue
  panel closes). Two layered causes, both fixed: `set_dialog_location`/
  `ensure_dialog`/`speaker_and_location`/`set_location_wipe_option`
  (yields 11/34/35/86) only treated a `-2` base as "keep the current
  background," so the real script's `-1` (sent right before football)
  fell through and got written literally, which renders as no background
  at all; and `close_dialogue_panel` (yield 39) reset the entire panel
  state to its defaults, including `background_id`, even though the
  scene background is conceptually separate from the closing text-box
  widget. The sibling KiWi engine's own native disassembly
  (`reference/codkiwi-main`) independently confirms any negative base is
  a KEEP sentinel, not just `-2`. Found and confirmed against real HD
  Football Star content played interactively.
- Word-grid portraits no longer render comically oversized. They were
  loaded with a raw, uncompensated image call instead of the same
  HD-vs-Android scale compensation `DialogueRenderer`'s own portraits
  already had; `GridRenderer` now applies the same ratio to its own
  (unmasked, frame-decorated) portrait art.
- The DTView/Faceplace side panels no longer cover part of the background
  on each side. `Desktop._present()` deliberately draws the background
  wider than the actual game viewport (showing more of HD's true 3:4 view
  beyond the narrower Android-authored UI canvas), but the panel margins
  were computed from the narrower viewport's own edge, so a panel started
  inside the region the wider background already occupied. Margins now
  start at the wider background's own edge instead.
- The Faceplace corner toast no longer auto-fades after a few seconds.
  Real-device testing overturned that earlier assumption: the toast has no
  timer of its own, popping in alongside the next dialogue beat and staying
  on screen until the player explicitly dismisses it by advancing dialogue,
  opening the settings menu, or opening the side panels. `FaceplaceToast`
  dropped its hold/exit timing; dismissal is now wired into
  `Session.answer()`'s dialogue branch and `Desktop`'s menu-open/panels-open
  handling.
- The dialogue relationship indicator (the small "emoticon" next to a
  speaker's portrait) no longer renders on top of the portrait.
  `DialogueRenderer.draw()` now draws it before both portraits instead of
  after, matching real-device screenshots where the icon sits behind the
  character art.
- The dialogue portrait no longer floats with a visible gap above the
  dialogue box. Measured directly against two real HD device photos of
  named dialogue: the box's top edge should sit at ~37% of the portrait
  ring's own diameter down from the ring's top (~63% overlap), not the
  ~59%/41% split the Android-sourced layout bank rect alone produced.
  `DialogueRenderer._portrait_rect()` applies this correction once, shared
  by the portrait, the relationship emoticon and the Faceplace-style notice
  label so all three move together.
- The dialogue portrait's own artwork no longer overflows above its ring
  (hair visibly poking out past the border) with a matching gap of
  backdrop showing below the chin. `portrait_group()` anchored the art's
  bottom edge to the smaller inner themed ring's height instead of the
  fixed outer ring every theme shares, sitting the art 12px too high.
  Verified against a real-device screenshot of the exact dialogue line
  being tested (`reference/football_star_beth_greeting_hd.webp`).
- The dialogue portrait no longer renders visibly larger than the real HD
  build's own. `portrait()` scaled every HD portrait down against a fixed
  `(128, 150)` constant (resource 268's own mask canvas size) instead of
  that specific portrait's own Android-native size -- most portraits
  aren't actually 128x150 on Android (Beth's is 113x122), so this
  under-scaled the HD source. Now reads the real per-portrait Android size
  the same way `chrome_image()` already did for small UI icons.
- The dialogue relationship indicator (emoticon) no longer renders behind
  the speaker name and body text -- confirmed on real device, it should sit
  on top of everything except the portrait itself. Also stopped applying
  the portrait's own ring/box vertical correction to the emoticon, which
  had pulled it down onto the name text; it uses its own, unshifted
  position again.
- Small UI chrome (relationship "likon" icons, the scene-badge sun icon)
  no longer renders oversized with an HD ipa attached. The generalized
  HD-asset fallback correctly upgrades backgrounds/portraits, which have
  their own scale compensation, but nothing was scaling these back down --
  confirmed live, relationship icons (3010-3012) came back at 44x48
  instead of their real 22x24 apparent size. `Desktop._chrome_image` /
  `DialogueRenderer.chrome_image` now normalize these back to the Android
  apparent size using the new `ContentLibrary.android_asset`.
- Dialogue, choice, word grid, loading, message, character-picker, title and
  the generic/text-input background now render HD content at its real pixel
  density instead of the Android-reference resolution the whole pipeline is
  otherwise calibrated to. The background is composited as a separate layer
  directly at window resolution in `Desktop._present()`, underneath the
  existing, unchanged UI canvas, rather than being baked into that canvas's
  fixed 480x720 pixel budget first. Verified against a real 960x1440 HD
  background: legible signage and visibly more scene detail versus the
  previous single-canvas compositing, confirmed live end-to-end on a real
  choice screen (background, panel and HD portrait composited together).
  The title screen's background fade-in keeps working, now applied to the
  separately-composited layer instead of the baked-in one. Football has no
  per-episode background content to begin with (its field art is fixed
  game chrome), so it needed no change; the main menu is APK-only and out
  of scope for the same reason.
- HD dialogue portraits (per-episode art at real HD density, well past the
  Android-reference 113x123 the mask was cut for) no longer stop playback
  with "Unsupported portrait mask dimensions." `DialogueRenderer` now scales
  the mask's geometry up to cover the portrait before clipping, rather than
  requiring a native-resolution mask that only the iOS HD build's own
  undeciphered low-id chrome format would provide. Verified against real
  220x240 through 256x256 portraits from a genuine HD episode.
- HD portraits no longer render comically oversized next to their (still
  Android-sized) ring and panel: the previous fix left the masked cutout at
  its own native pixel count, with nothing scaling it back down. The result
  is now always normalized to the size an Android portrait would have
  occupied, whichever mask (real HD-native or algorithmically scaled) did
  the clipping. When an HD ipa is imported, the real native HD portrait
  mask (id 311) is used directly instead of the algorithmic approximation.
  Verified live: a real HD choice screen's portrait now matches its ring
  instead of overflowing past it.
- The default window is now 3:4 instead of 2:3, and the background layer
  (see above) fills that wider shape while the Android-authored UI chrome
  stays exactly where it was. HD's own main game view is a fixed 768x1024
  (3:4) in every orientation -- confirmed from
  `SHSViewController::setupLocalInterfaceOrientation:`, which only ever
  rotates that rectangle for landscape, never resizes it -- so this shows
  real extra background content at the edges without touching any
  already-correct chrome position. Verified live against a real HD choice
  screen: more of the school building and street are visible around an
  unchanged dialogue panel and portrait.
- Word-grid puzzles no longer refuse to start when one target word needs a
  letter its own alphabet doesn't have. Confirmed against two real HD
  episodes (a one-character content typo each, not a decoding bug -- every
  other row in the same episodes checks out fine) that this is real
  shipped puzzle data, not a shs-runtime bug. The unspellable word is now
  dropped before the puzzle starts instead of refusing the whole grid,
  keeping its other, well-formed words playable.
- Dialogue text embedding a handful of low control-range bytes (confirmed
  in three real HD episodes, sitting exactly where an apostrophe, a quoted
  phrase, and a sentence break belong) no longer stops the episode with
  "no defined glyph." The Android font resource genuinely has no glyph
  data below the space character, so these now render as an invisible,
  space-width gap instead -- keeping affected dialogue readable rather
  than halting playback. Printable characters with no glyph still raise.

## 0.1.1

### Fixed

- Implemented services 7/63 for episode exit, fixing Football Star scene
  25001, PC 130. Endings now cancel queued scripts and return to the main menu.
  Save version 12 recovers older stops there and retires ordinary Resume
  progress while preserving manual saves and other episodes' checkpoints.
- Implemented service 70's verified Android query constants, fixing Football
  Star scene 25001, PC 222 (selector 10). Existing saves stopped at fixed
  queries now continue normally. Selector 11 remains explicit until native
  weekly-episode identity is modeled.
- Implemented service 76's named dialogue without a portrait, fixing Football
  Star scene 25011, PC 4303 and other group-speaker lines. Existing saves
  stopped there resume through the original dialogue reveal and input gates.
  Dialogue completion now also consumes the queued transition selector and
  its native random draw, shared with title/message panels.
- Restored the shared episode-intro and week-card screen, including Football
  Star's week titles: original fonts, background scaling, text placement,
  title wipe, background fade, subtitle animation and tap behavior. Save
  version 11 preserves intro animation state and migrates existing saves.
- Music now pauses with gameplay and resumes from the same position after
  closing the pause menu, regaining window focus, or returning to a live
  episode from the main menu.
- Restored native speaker-name widths, alignment and persistent spacing,
  including Howard's parents and quiz teachers. A shared glyph-bounds
  correction keeps names clear of dialogue and portraits across page turns.
  Save version 10 retains font history and migrates existing saves.
- Fixed top-left location/time labels so their text aligns inside the badge,
  including wrapped labels. No content reimport is needed.
- Restored eleven Android music cues that reuse another APK track at a
  specific start offset. This fixes missing-music warnings for 8202, 8208,
  8211, 8220, 8225 and the other verified redirects, using existing libraries.
- Implemented service 33's Instructions/message panel, fixing Football Star
  scene 25011, PC 629. Restored its original panel assets, reading delay and
  acknowledgement callback, including the shared random-stream side effect.
  Save version 9 preserves reading time and recovers older saves paused there.
- Relationship indicators now read the correct NPC property, so script changes
  update the icons and count, including Adam's four skulls in Football Star.
- Implemented service 39's dialogue panel cleanup, fixing the Football Star
  stop at scene 25013, PC 13. Saves paused there resume from their existing state.
- Fixed Football Star's word-grid tutorial initialization by matching the
  native word-list parser and accepting instruction pages with no targets and
  unused failure links. Playable-grid validation remains enforced.
- Restored the word-grid UI's original bitmap fonts, tutorial panels, portrait
  placement, time/score display, cloud borders and word prompts. Added native
  banner and panel motion, outgoing tile faces, and corrected hint/trace art.
  Save version 7 retains these animations and reads earlier saves.
- Restored Strength Up and other service-88 notifications with the original
  lettering, portrait-relative placement, rising letters and fade. Corrected
  their lifetime and dismissal on dialogue taps. The fix applies across
  episodes, and existing saves retain their remaining notice time.
- Restored football's original help panels, play legend, fonts, team/score HUD,
  four-step countdown, target motion and selection effects. Added smooth field
  movement and native localized result sequences with corrected feedback timing.
  Save version 8 preserves football animation state and reads earlier saves.

## v0.1.0

### Added

- Compatible KiWi engine that executes original scripts and imports resources
  locally from a player-supplied Android 1.0.9 APK and EXP episodes.
- Desktop launcher and main menu with persistent episode libraries, catalog
  grouping, manual saves and automatic checkpoints.
- Dialogue animation, portrait masks, choices, character selection,
  relationship indicators, and word, grid and football mini games.
- EXP, VM, engine-service and UI specifications documenting recovered behavior
  and remaining uncertainties.

### Known limitations

- Complete episode playback and full original-game fidelity remain in
  progress. Unsupported services stop explicitly with their pending arguments
  preserved.
- macOS builds use ad-hoc signing and are not notarized; Windows builds are
  unsigned.
