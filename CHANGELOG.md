# Changelog

## v0.5.0

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

## v0.4.2

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

- Implemented Android's randomized choice order. Choices preserve
  their script return values and saved random state. Existing saves stopped
  there now resume without replaying earlier progress or reimporting content.

## v0.1.2

### Fixed

- Corrected dialogue portraits sitting too high inside their circular frames.
  The native 12-row crop and center placement now apply consistently in
  dialogue, choices and the appearance picker, including odd-height artwork.
- Fixed the imported New Girl episode's portrait-mask error. Larger portrait
  variants now render at half size before masking, preserving aspect ratio,
  transparency and orientation. Existing libraries need no content reimport.
- Timed choices now show the original circular countdown and timer panel.
  The timer stays visible when long lists scroll, freezes while paused or
  unfocused, and restores from saved time. Corrected expiry to occur just after
  zero, preserving the script's timeout selection and custom return values.
- Fixed the APK-bundled New Girl episode stopping at `yield 91 at pc 60:
  expected 1 arguments, got 0`. Loading now accepts both bundled and imported
  episode calls, preserving their native timer and VM frames through save/load.
  Existing libraries need no content reimport.
- Restored the name-entry screen's original panels, bitmap fonts, layout,
  cursor and invalid-input alert. Typing now follows the native capitalization,
  alphanumeric, 16-character and width rules, with Return to confirm. Drafts
  survive save/load, and rejected input leaves the pending script unchanged.

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
