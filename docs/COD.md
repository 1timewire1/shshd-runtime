# Cause of Death support

SHSHD Runtime opens SHS and CoD as separate games. Choose **Cause of Death** in
the launcher and supply its IPA, then add CoD EXP files to that library. A CoD
APK profile has not been established. No original files, screenshots, fonts
or decompilations ship with the engine.

```sh
uv run --locked exp-tool import --game cod --ipa /path/to/CoD.ipa --episodes /path/to/CoD-Episodes --library /path/to/cod-library
uv run --locked --extra desktop shshd-runtime --game cod --library /path/to/cod-library
uv run --locked exp-tool trace /path/to/episode.exp --game cod
```

## Identification and isolation

Import recognizes `com.ea.causeofdeath` and the free edition's
`com.ea.causeofdeathfree`, with optional dot-separated suffixes, and validates
the required `res_generated` payloads. Version numbers and the native
executable are informational; native code is never executed. The inspected
packages are 1.3.4 (`com.ea.causeofdeath.bv`, 348 numeric assets) and 1.4.7
(`com.ea.causeofdeathfree.bv`, 353).

1.4.7 renumbers the low bank. Its revised Volume One stays at 12 and the old
one is kept at 13. The English string bank is 14, followed by French,
Italian, German and Spanish banks (15–18). 1.3.4's resources 14–999 sit five
higher (layout bank 19, skins 209/225/241/257, mask 273, fonts 295–302). Ids
1–12 and 1000 and up keep their numbers. Everything except the string bank's
credits year and resource 15 (→ 20) is byte-identical; backgrounds 1000–1050
are re-encoded at the same size. `cod/assets.py` (`logical_members`) exposes
such an IPA under the 1.3.4 ids, so every contract below applies unchanged.
The layout is recognized by its contents (1.3.4 has nothing between 17 and
125), not by its version string. Only the English bank is exposed.

The bundle ID identifies the game, not its resource layout. Import and reopen
try the supported mappings and require exactly one complete, valid asset bank:

| Layout | Profile | English strings | Layouts / common images | Mask | Fonts |
| --- | --- | --- | --- | --- | --- |
| Paid reference | `cod-ios-assets-v1` | 13 | 14 / 16 | 268 | 291–297 |
| Compact free | `cod-ios-free-assets-v1` | 14 | 15 / 17 | 269 | 292–298 |
| Multilingual free | `cod-ios-free-localized-assets-v1` | 14 | 19 / 21 | 273 | 296–302 |

Free layouts repeat Volume One at 13; only 12 is canonical. Reference UI
members 14–297 move by one in the compact free layout and five in the
multilingual layout. The latter has extra language string banks at 15–18.
The base member view normalizes UI IDs and omits the duplicate/language banks;
characters, backgrounds, relationship art, sounds, music and episode assets
keep their IDs. This does not add localized story or UI selection.

Import records the detected profile (exp-runtime v0.6.0). This fork's `logical_members` gives the same
mapping from the members themselves, so a library imported by shshd-runtime 1.0.x, which recorded every CoD
IPA as `cod-ios-assets-v1`, still opens: `ContentLibrary` accepts the IPA's own free layout under that
record and leaves `library.json` unchanged.

The compact layout comes from the PR contributor's inspected free IPA. The
multilingual layout comes from the
[1.4.7 `.bv` review report](https://github.com/joshrmcdaniel/exp-runtime/pull/1#issuecomment-6193379821).
Both have authored import/reopen fixtures, including identical bundle IDs and
versions, relocation, missing assets and conflicting manifests. Full original
1.4.7 playback has not been independently verified here. Required payloads must
parse correctly; sentinel filenames, version strings or bundle suffixes alone
cannot make an incompatible archive pass.

Its base resource **12** is a complete EXP containing **Volume One** (metadata
pack 101 / episode 1 and scripts 25001–25008). Import retains that EXP as a
hash-named private episode automatically. It does not synthesize a story or
borrow SHS's Football Star scripts.

The native `SHSEngine::getData` at `00019cf4` selects the base resource bank
below **26000**, and the current episode bank at or above **26000**. That matches
the shared resource reader. Script loading separately permits episode scripts
in the 25000 range. Exact lookup never falls through to another game or library.
An EXP's metadata has no reliable game discriminator: the player selects the
destination game when importing additional episodes.

New libraries use `format: exp-content-library`, `version: 1`, `game: cod` and
the matching profile above. A contradictory game/profile/package is rejected.
The complete source and EXP hashes bind saves, so the same EXP used in both
games cannot share progress accidentally. SHS APK music supplementation is
restricted to SHS IPA libraries.

## Explicit compatibility adaptations

The following adaptations are intentionally distinguished from native parity:

- Undefined bitmap glyphs `0x09`, `0x18` and `0x19` fall back to space,
  apostrophe and apostrophe respectively in both games. These bytes occur in
  supplied dialogue, including `0x18` in SHS's The Endorsement. Their positions
  suggest truncated Unicode punctuation; the authoring conversion itself has
  not been verified. A reviewer reports that original CoD 1.4.7 displays a
  missing-glyph box for `0x19`. Existing font glyphs always win, and other
  missing characters still fail explicitly.
- CoD incremental timed choices (services 2–4) pass through only the observed
  out-of-range defaults `-1` and `1000`. This prevents a stop on known content
  without copying undefined memory. In-range defaults still use the return
  mapping, and completion updates the VM and result cell once. Other invalid
  indices, including those in SHS, remain explicit stops.
- ASCII spaces in CoD text entry are an owner-requested convenience. The native
  filter rejects spaces, and the cited puzzles have space-free solutions.
  Typing, final validation and saved drafts share this allowance; other
  rejected characters and the existing length/width limits remain unchanged.
  [NAME_INPUT.md](NAME_INPUT.md) distinguishes the native capitalization rule.

For the timeout adaptation, local CoD 1.3.4 `SHSUIMenu::tick` (`00039c8c`)
copies the configured default. `setReturnValue` (`00039570`) then reads a
signed short from `this + 0x9a + 2*selection` when mapping is enabled by
`initTextMenuWait` (`0003a30c`). At `-1` it reads the field at `+0x98`; it
does not return the default itself. Executing that callback with authored menu
memory confirms that changing the neighboring field changes the callback.
Fresh allocation does not guarantee zero, so neither zero nor passthrough is
claimed as an exact native result. A local static scan found 124 literal `-1`
timed defaults and one `1000` default across 23 of 81 distinct CoD EXPs; it
does not establish every dynamically computed default or reachable branch.
The reviewer's reported equivalent-play comparisons support this narrow
compatibility policy, rather than a general rule for arbitrary invalid values.

## Episode catalog and duplicate imports

Folder imports and individual EXP imports discover a sibling `cod_options.sav`.
The episode picker and drag-and-drop also accept that file by itself. Reimport
the original folder or add its catalog to name existing entries without resetting
progress. SHS's catalog is ignored when discovering CoD content, and explicitly
selecting the other game's catalog is rejected.

CoD keeps the `SHS_OPTIONS` signature, but its version-17 file has a 33-byte
prefix and no flags after the runtime string table. Native `loadOptions`
(`00019098`), `saveOptions` (`000195b4`), and `SHSEpisode::createFromStream:`
(`00050b10`) establish the envelope and common episode-record format. The
shared reader selects this layout through `cod/profile.py`, validates through
EOF, and imports only catalog metadata. See [EPISODE_CATALOG.md](EPISODE_CATALOG.md).

Initial and subsequent imports already deduplicate identical EXP bytes by
SHA-256 in both games. Alternate filenames are now retained as lookup aliases
so renamed copies can match a catalog's original filename. Different EXP hashes
remain distinct editions, even when their numeric IDs and titles are identical.
They never replace an edition with existing progress.

The supplied 103 external CoD files contain 80 unique EXP hashes. The supplied
catalog has 80 distinct records and names 79 of those 80 external episodes.
`12_Fallon_Family_Christmas.exp` is absent from that catalog and retains its
numeric pack header; its category is not inferred from neighboring stories.
These are observations of the supplied files, not limits on other collections.

## Native UI and audio bindings

Addresses here refer to the user-supplied **CoD** iOS executable, inspected
through Ghidra MCP. Read-only LLVM disassembly was used where Objective-C
decompiler output ended prematurely. No analysis repair or server access was
required.

| CoD resource | Contract |
| --- | --- |
| 13 | 257-entry UI string bank; host labels use CoD's semantic indices |
| 14 | Layout bank, byte-identical to the inspected SHS Android bank |
| 6–9, 16, 126, 204/220/236/252, 268, 272 | Menu art, shared panel skins and portrait mask |
| 291 | Bundled Verdana Bold Italic name/title face |
| 292/293, 294/295 | Title/secondary PNG glyph atlases and font records |
| 296/297 | Embedded menu glyph fonts |
| 3000–3008 | Relationship icons and their burst/drop variants |
| 8201–8209 | Nine independent music sources |

`SHSEngine::initFonts` (`000230b8`, notably `000231f2` and `00023220`) binds
292/294 and embedded faces 291/290. The name-font host roles use bundled 291.
Common system faces retain the existing original-installed-face, then
system-default fallback. FreeType rendering remains an approximation of iOS
CoreGraphics; saving on one font configuration and loading on another can
trigger the existing layout validation.

CoD's palette is also game-specific. `initFonts` initializes the normal
speaker fonts at `000234da` / `000234fe` with ARGB **0xff8b0000** (dark red),
and the ordinary body at `0002353c` with **0xff000000** (black). The literal
pool at `00023838` identifies the name objects at engine offsets `0x11294`
and `0x12ab4`; `updateFonts` (`000355e4`) binds those objects and the body at
`0x142d4` to dialogue. Theme 2 keeps its rose color; gray/default themes use
the same dark-red names and black body as the normal theme. These bindings
live in `cod/profile.py`; font size and glyph advances are unchanged.

Narration has its own font object: `initFonts` at `00023476` initializes
engine `+0xe254` with black (`0xff000000`); its backtick switch font at
`+0xfa74` uses gold (`0xffb46d1a`, `000234a0`). The shared narrator now uses
this CoD palette rather than SHS's amber/brown pair.

Score notices are theme-dependent in the supplied 1.3.4 native code.
`updateFonts` (`000355e4`) selects the main letter font at dialog `+0xd4`:
theme 1 uses engine `+0x17314`, red `(240,81,60)`; theme 2 uses `+0x21bf4`,
rose `(180,78,78)`; theme 3/default use `+0x2acb4`/`+0x33d74`, black.
`SHSTextLayer::drawLayerText:` (`00046dec`) draws the outline font first,
then this main font. The color selection applies to every service-88 notice,
without matching the text "Detective Score Up!". This verifies black notices
for neutral/gray themes, not a universal black color for every theme.
The shared notice face, outline and motion still follow the compatibility
renderer; see [service 88's remaining iOS differences](STORY_SERVICES.md#dialogue-notifications-service-88).

The owner supplied `decomp/cod/cod-native-1.jpg` and `cod-native-2.jpeg` on
2026-10-05. Their Man/Sophie scenes corroborate the normal palette and titles
attached to the top border. They remain private references, not test fixtures
or bundled content. They do not establish full native parity for long names,
animation, body wrapping or the footer. Their Continue tab is corroborated
by the native layer/artwork evidence below.

The subsequently supplied `decomp/cod/cod-original-promo-ss.jpeg` adds a
long-name reference: **Det. Mal / Fallon** appears on two lines straddling
the box's top border, above "I'll catch this guy, Captain." The intermediate
compact-header correction put this name on one line wholly above the box.
The general correction now reproduces the two-line title using verified native
font metrics and header selection, with the body in its own text region.
The reference does not establish exact pixels from the resized promotional
image, validate earlier detached name positions, or prove SHS-specific font
metrics. It corroborates the corrected CoD palette.
The promo remains private reference content, never a fixture or bundled asset.

CoD has the same native Continue layer as SHS. `expandContinue`
(`000103cc`, default-label overload `000107cc`) positions a 99×17 common-atlas
tab below the dialogue box and expands it vertically over 250 ms. The default
label is CoD string 26 (shared string role 29). `setBubbleSex` selects the
skin's common frames 3–6. The shared renderer now draws this control for both
games; [UI fidelity](UI_FIDELITY.md#dialogue-continue-tab) records the common
geometry, font and save behavior. Read-only LLVM Thumb disassembly of the
supplied armv6 slice supplements Ghidra where its ARM decoding is incorrect.

CoD also has SHS's speaker-side background alignment, now implemented in
the shared desktop/iOS renderer. `SHSUIDialog::animateLocationLayer` (`0003671c`) selects
alignment 1 for dialogue mode 1 and alignment 3 for mode 2.
`GameModel::alignLocation` (`0000eff8`) sets the background center to
`(width/2,180)`, `(160,180)` or `(320-width/2,180)` for alignment 1/2/3.
`setLocationPan` (`0000f0c0`) controls automatic versus fixed alignment through
fields `+0x3f8/+0x3fc`. Ghidra incorrectly stops the dialogue helper at its first
Objective-C call; its memory bytes and the original armv6 disassembly confirm
the continued mode branches/calls at `00036742`–`0003675e` and the 0.25-second
return value. Service 97 calls `setLocationPan` at `00034abc`, with the same
automatic flag and alignment arguments as SHS. Exact iOS animation transaction
timing remains unverified; the shared renderer uses Android's verified linear
250 ms move. See [UI fidelity](UI_FIDELITY.md#background-panning) for timing,
background replacement, fixed alignment and save migration.

Dialogue uses the [shared SHS skin and renderer](IPA.md#dialogue-text-placement),
with both games' outline fonts following the same recovered CSFont rules.
Read-only Ghidra verification confirms wrapped-height selection of normal/tall
title regions in CoD `updateTitleBounds` **00036adc** and SHS **0007ce08**.
Title alignment, line indents and cap-height spacing come from their native
title/font routines. Ordinary body text stays at node 8 independently of the
title extension; that extension does not increase page capacity. The generic
ink guard permits native border overlap and only bounds excessive ink against
the selected header, skin, portrait and body. There are no character or scene
overrides and no separate IPA layout class. Android bitmap rules, saved font
history, shared narration and animation remain. Save version **16** reflows
older IPA pages at their saved source offset without replaying VM instructions;
current pages and retained history are validated. Details and Ghidra addresses
for both games, including decompiler limitations, are recorded in IPA.md.

`SHSUIDialog::getStatusIconID` (`00037e08`) reads properties 629, 601 and 407.
`setCurrentSpeaker` (`00038008`) selects the native 3000/3001/3002 icon, derives
its count and writes the actual icon/count into properties 3000/3001. These
script-visible values are never replaced with SHS's 3010-series IDs. The shared
animation uses each game's own burst/drop assets. SHS feedback sound IDs and
its character-45 animation exception are not applied to CoD.

Service 79 classifies 8201–8209 as music; service 80 explicitly queues music.
`SHSSoundManager::playMusic` (`0004313c`) accepts that range and episode audio
at or above 26000. CoD cues use their exact source with zero seek offset;
SHS's 8202→8201 and other segment aliases do not apply. Service 81's argument
is a fade duration, not a track selector. The syscall calls
`stopMusic((short)a1, true)` (`00042d70`): 0 stops at once, `0xffff` means
1000 ms, and any other value is milliseconds (`-[SHSSound setFadeTime:]`
divides it by 1000.0; `getFadeLevel` falls linearly to 0). `true` drops any
queued cue. A sound that is already fading keeps its fade. `tick` (`00042ffc`)
starts a cue queued by `playMusic` only once the faded sound has stopped, and
`playMusic` of the fading cue itself removes the fade. The desktop follows
these rules for both games (SHS HD's case 0x51 makes the same call; see
ENGINE_ABI.md, "Music"; the fade time is playback state and is not saved). Negative shorts other than -1 would make the native fade never finish.
The runtime stops at once for these instead (unverified in scripts). The iOS
host's mixer has no volume control, so there the cue plays at full volume for
the fade time and then stops.

exp-runtime v0.6.0 models CoD's scene blinds and black fades in the session (selectors 1, 2, 6 and 20,
`setupQueuedFade` `0000f998`, `tickFade` `0000ee5c`). This fork runs that model for CoD and for SHS HD, whose
GameModel and SHSFadeLayer are the same code (`fade_transition.FadeTransition`; comparison 2026-10-21 in
legacy/findings.md). One change: the black layer's fade-in is (1, 1, 0) at keyTimes (0, .8, 1), holding black for
1.2 s and clearing over the last 0.3 s (1.4.7 `0005cbce`), where exp-runtime clears it linearly over 1.2 s. Its
menu-to-story `fadeToGame` (`0000f9d8`) and desktop audio handoff with saved playheads are not used here: the main
menu's entry is application.py's and the music `music_stream.py`'s.

Service 80's second argument is the **repeat flag**, not a fade control.
The dispatcher (`0003354c`) passes `bool(a2)` to `queueMusic` (`0000ebe2`),
then `handleQueuedAudio` (`00011c0c`) forwards it to `playMusic` (`0004313c`).
The sound manager's `tick` (`00042ffc`) applies `setLoop:` before playback;
`SHSSound::setLoop:` (`00041e88`) sets AVAudioPlayer's loop count to -1 or 0.
Both runtime audio backends now honor this flag. Service 79 queues music
with `false`. Menu track 8209 is also explicitly one-shot in
`splashScreenFlewIn:` (`00014c0c`) and `doSoundManagerTransition`
(`00022b04`); it is not evidence that story tracks should stop after one pass.
SHS iOS `SHSSound::setLoop:` (`00073fa8`) uses the same repeat convention.

The shared dialogue renderer now adopts the iOS bubble-opening animation
for portrait-speaker entrances in both games, at the owner's request.
See [animation evidence and limits](UI_FIDELITY.md#ios-dialogue-box-entrance).

CoD menu clicks use **8005** (`0x1f45`), recovered through read-only Ghidra
inspection of `SHSEngine::buttonPressed` (`000249d0`) and
`SHSWidgetMenu::buttonPressed` (`0003fd60`). These pass `false, -1` to
`SHSSoundManager::playSound` (`000431cc`). The shared application now plays
that source from the CoD base library when Sound is enabled, independently of
Music. Native `SHSUIMenu::handleMenuSelection` (1.4.7 `0003cbc0`) also plays
8005 when a story choice is picked (modes 1/3), and the runtime now plays it
there too. Scored-choice mode 2 plays 8003 / 8004 instead. CoD's Options
switch and sliders also sound 8005. See
[MAIN_MENU.md, "Interface sounds"](MAIN_MENU.md#interface-sounds) for the full
table.

## Services and current coverage

The CoD dispatcher is `SHSScript::syscall` at `0003354c`.

- **15:** named dialogue on panel 3. Resolve/substitute the first two string
  arguments as speaker and body, set speaker mode 3, and animate the panel.
  Extra words in the four-argument EXP form are ignored. The original frame
  stays pending through pagination and the shared acknowledgement callback.
  `setSpeakerType` (`00037f14`) confirms this mode removes the portrait.
  SHS also supports named dialogue, including its separately verified
  negative-prefix form; see [the SHS contract](STORY_SERVICES.md#shs-service-15).
- **99:** the original invokes `showFullPageAd`; the offline desktop follows
  its no-ad completion path and resumes with zero. It never contacts an ad
  service. This is a deliberate desktop adaptation, not a native no-op claim.
- **7/63:** native `GameModel::endGame` is a terminal scene handoff. The
  desktop returns to the selected game's menu.
- **70:** CoD's build/platform query, including its version-string write.
  The desktop takes the native store-unavailable branch for selector 10.
  Selector 6 requires `CFBundleVersion` from the retained IPA; bare EXP
  tracing or an IPA without that field leaves this query explicitly pending.
- **94/96:** native default completions, returning zero and removing the
  supplied frame without starting a minigame or modifying scores/randomness.
- **97:** shared location-pan control: `bool(a1)` enables automatic alignment;
  `a2` chooses left (1), center (2) or right (3). It also requests that alignment
  immediately, ignores extra words and completes with zero. Other alignments
  retain the current position. The policy and active movement are saved.
- **100:** the supplied 1.3.4 runtime takes the same default completion through
  its out-of-range branch, without reading its arguments. The desktop follows
  that verified behavior for the observed promotional-link calls; no external
  browser or app is launched. See the service-100 audit below.
- **9, 91, 95:** remain unsupported CoD stops, with their original arguments
  intact. Their native behavior was audited separately below; SHS's survey,
  loading and score handlers must not be enabled wholesale for CoD.

Older saves stopped at 70, 94, 96, 97 or 100 resume their retained call and its actual
continuation without replaying earlier instructions or random draws. The
outgoing portrait is recovered from the retained panel for the next dialogue.
Service 97's presentation state uses save version 19; older saves migrate.
These handlers do not require library reimport.

The shared KiWi decoder accepted the 420 scripts in the 103 supplied external
EXPs. Removing byte-identical EXP copies leaves 80 archives and 368 scripts,
using 39 distinct service numbers. After adding the native service-100 default,
each observed number has a handler. This does not establish support for every
argument variant, conditional minigame mode, branch or complete story route.
Optional original-content tests import Volume One, render its opening through
ordinary/timed choices and service-15 dialogue, restore its pending saves, and
play all nine base music sources through SDL dummy audio. Authored tests cover
colliding IDs, game/profile mismatch rejection, unavailable assets, legacy SHS
saves, launcher migration and switching/checkpoint failures.

`SHSUIMenu::handleMenuSelection` **000395ac** plays **8005** for an accepted
ordinary or incremental story choice. Timed word selections play **8003** for
a positive score delta and **8004** for a negative one; zero is silent.
SHS's corresponding **000afee8** (Android) / **00084600** (iOS) uses
**8010**, **8001** and **8002**. The shared session now preserves each input's
ordered sound requests, including script cues immediately after a choice.
Timeout callbacks and rejected input do not synthesize a click.

CoD `setCurrentSpeaker` **00038008** and the full
`setStatusIconAnimated` **00043fc0–00044d84** path do not request relationship
sounds. SHS's relationship sound table is therefore not applied to CoD.
Complete episode routes, all CoD service variants and exact iOS animation/font
parity still require verification.
Unknown services stop explicitly; no score, choice, random result or next scene
is invented to continue an unsupported episode.

## HD presentation through the SHS HD bundle (optional)

CoD has no iPad edition. A CoD library may link the owner's SHS HD (iPad)
IPA as a presentation-only art source (`exp-tool add-hd-art --ipa ...
--library ...`, `ContentLibrary.add_shs_hd_art`; manifest `shs_hd_art`,
validated by the same executable hash as SHS's HD supplement). Without it,
CoD plays exactly as before. The link never becomes `hd_ipa`, so none of SHS
HD's screens, strings, scripts or fonts apply; `hd_asset` serves only CoD's own
verified map. With it:

- **Skins.** CoD's skin packs 204/220/236/252 share SHS's geometry. 252 and
  the portrait mask 268 are byte-identical to SHS Android's; 204 and 236 are
  grey recolours of the blue and gold; every box frame caps the opaque interior
  at alpha 242. `cod/hd_art.py` turns SHS HD's 2x packs (247/263/279/295) into
  CoD's look. Each literal frame keeps or recolours its RGB (a table on
  min(R,G,B)) and alpha, whichever scales back closest to CoD's 1x frame. The
  remaining differences equal SHS HD's own redraw differences: 252, identical
  at 1x, shows the same. 268 uses SHS HD's 311 as it stands.
- **Text.** `vector_text.cod_vector_font` draws CoD's own CSFonts as vector
  text at their iPhone point sizes. The faces come from `SHSEngine::initFonts`
  (1.3.4 armv7 `00025e68`):

  | Slot | Face |
  | --- | --- |
  | +0x1e4 | TimesNewRomanPS-ItalicMT |
  | +0x1e8 | TrebuchetMS-Bold |
  | +0x1ec | TrebuchetMS-Italic |
  | +0x1f4 | ArialRoundedMTBold |
  | +0x1f0 | ArialMT, measured with Arial Rounded's advances |
  | +0x1e0 / +0x1f8 | the two faces bundled in `res_generated` |

  Narration is +0xe254, TrebuchetMS-Italic 16 in black (SHS's narrator gold
  does not apply). Its `` ` `` switches to +0xfa74 (0xffb46d1a). Body text
  switches only on `` ` `` (`CSFont::handleSwitchChar` `00004b54` toggles the
  base font's own characters, so `;` is plain text): theme 1 goes to red
  0xfffe3535 TrebuchetMS-Italic with stroke 0.5, theme 2 to blue. Names use the
  bundled face, dark red, with `setStroke(4.0)` at 26. The player's own
  `fonts/` folder supplies Arial Rounded when it is not installed; the IPA atlas
  path checks it too.

- **Common frames.** CoD's pack 126 is SHS's with recolours. Its frames get
  SHS HD's pack-155 drawings, derived the same way (`cod/hd_art.COMMON_FRAMES`):
  Continue tabs 3-6 (155 #8-11), timer wedges 7-22 (#12-27), ring 37 (#46,
  unchanged), picker rings 43/44 (#47/48) and gear 49/50 (#58/59). Bar 47 is
  composed from cap #55 and strip #56. On the bottom edge CoD then takes SHS
  HD's layout (`DialogueRenderer.hd_bar`): the bar runs across the whole
  384-unit frame and the gear sits flush left, where it is also tapped. Its
  iPhone layout puts both in the 320-unit column, which left gaps at the 3:4
  frame's sides. They are served through
  `ContentLibrary.cod_hd_common`, never as `hd_asset(155)`, so none of SHS HD's
  own chrome behaviour switches on. Each stand-in is drawn at its own 2x size:
  the wedges are 19x50 for Android's 10x25, and only tile at their own size.
  Alpha follows CoD's change proportionally (the median ratio on opaque pixels:
  a 242 cap, or a 242 strip raised to 254), never per value. The discs 38-40
  are flat greys (207, 207, 149), so they become SHS HD's vector circle, 105
  units, in the frame's own colour.

Since ported from CoD's own code (sections below): the choice geometry,
choice-panel colours and title placement, the chapter card and the score
banner. Still open: the highlight's face change (colour only so far).

## Dialogue geometry

CoD has its own `SHSUIDialog`, and its text uses CoD's iPhone rules
(`dialogue.DialogueLayout.page`). It does so with or without the art
source; SHS HD's photo-fitted placements never apply.

- **Narration** (`animateTextLayer`, 1.3.4 armv7 `0003c4e4`, speaker
  type 4).
  - The narration font measures and draws. `+0xcc` is set in `init`
    (`0003d8d8`) to engine `+0xe254`; Android measures with the body font
    instead.
  - The block is wrapped at 220. Its width is the widest line + 1, rounded
    up to even and at least 120. Its height is the text height + 4, rounded
    up to even.
  - The bubble is that block plus 10. The text layer sits at the
    constructor's (30, 120).
  - 1.4.7 anchors at (30, 135) when `SHSEngine::g_bEnableInGameBanner` is
    set (constructor `0003c27c`). The flag sits in zero-filled memory and is
    set at run time by the ad code. The owner's 1.4.7 device shows the
    shifted layout (IMG_0309), so a free-edition library keeps it
    (`cod.profile.in_game_banner`).
  - The flag also moves the schedule caption from y 10 to 55
    (`GameModel::init` `00012964`, `+0x1c20`, read by
    `displayScheduleCaption`) and is read by
    `SHSUIChapterScreen::initChapterScreen`. The chapter card's use is ported
    (`desktop_title.CodTitleRenderer.BANNER`). The scene caption's never
    shows: no CoD script raises a caption. Service 90 appears once, in
    Volume One, as a dismissal (`90(-1, -1)`). Its frame is
    (-171, `+0x1c20`, 171 x 60) CoD points (1.4.7 `00011024`).
- **Typed lines** (`-[SHSTextLayer setupTypingLayers]` `0004db50`).
  - Each line is its own layer inside a container placed at
    (x − 4, line top − 4). The line layer sits at (−4, −4) in it
    (`positionLayer:boundsPadding:` `0004e7e4`), with its text at (4, 4).
    Every line therefore sits 4 units up and left of the text layer's origin.
  - Lines step by `FPToFixed(gap + cap)`: 20 for narration, 21 for body.
  - The device's baseline is a further 2.4 units lower in both faces
    (IMG_0309, IMG_0310). This is photo-measured and not found in the
    decompile (`COD_BASELINE_DROP`).
- **Footer hints** come from CoD's own bank. It lacks three of SHS's strings,
  so roles 36/38/40 are CoD's 33/35/37 (`cod.assets.STRING_IDS`).

Measured against IMG_0309 and IMG_0310 at 1.4 px per unit, every edge and
line is within about half a unit: line breaks, box edges, text x and line
tops and bottoms.

## The portrait housing

CoD's iPhone `SHSPortraitLayer` (1.3.4 armv7) has SHS HD's layer at one point
per unit. This applies with or without the art source:

- `init` (`0004c680`) builds 128x160 character layers, anchored bottom-centre
  on the 128-point housing.
- `drawLayer:inContext:` (`0004c3f0`) applies mask frame 0 at (0, 10, 128,
  150), the immediates at `0004c502`-`0004c518`. It translates to
  ((128 - w) / 2, 160 - h). Portraits therefore sit flush on the housing's
  bottom edge; SHS HD uses 318 of 320 points.
- A right-hand speaker is flipped unless theme 3.
- `drawInContext:` (`0004bfcc`) draws ring 37 even-odd clipped against the
  bubble outline, then the disc unclipped (38/39/40 by theme; 43/44 in the
  portrait picker).
- `GameModel::clipPortraitHousingAgainstBubble` (`00010850`) and
  `clipPortraitHousing` (`00010768`) give SHS HD's outline: the box plus 7.
  Its top corners are cut 10 points, which is 10 units here (SHS HD: 5).
- `SHSUIMenu::addPortraitToMenu` (`0003f2b4`) calls the same clip, so choices
  share this housing.

## The choice panel

CoD 1.4.7's iPhone `SHSWidgetMenu` is SHS HD's code with every constant
halved, laid out in a 480-point screen (`hd_choice.COD_GEOMETRY`). The
runtime draws it with SHS HD's port (`hd_choice_page`, `ChoiceRenderer.draw_hd`)
from CoD's own layout bank (resource 14; `hd_layout.BankLayouts`) and CoD's
packs: slot 0 is common pack 126, slot 2 the theme's box pack. It needs vector
fonts, so it applies with the SHS HD art source; a plain IPA library keeps the
Android page.

| | SHS HD (iPad points) | CoD (iPhone points) |
| --- | --- | --- |
| `setMetrics` (`generateNewMenu` `000453d8`) | x 104, width 560 | x 20, width 280 |
| Rows; panel limit; screen | 88; 964; 1024 | 44; 450; 480 |
| Portrait description minimum; extra without a character | 136; 20 | 68; 10 |
| `ARR_LINE_OFFSETS_MENU_LEFT` | 190, 170, 130 | 95, 85, 65 |
| `ARR_TITLE_LINE_OFFSETS_LEFT` / `_RIGHT` | (0, 40) / (0, 10) | (0, 20) / (0, 5) |
| Table and separator inset; side strips; label padding | 6; 6; 24 x 12 | 3; 3; 12 x 6 |
| Box line above the header's bottom (normal, tall) | 36, 100 | 18, 50 |
| Housing centre x (left / right) | x + 74 / 694 - x | x + 37 / 283 - x |
| Housing; `clipPortraitHousing` inset | 256; 6 | 128; 3 |
| Circle timer (`updateTimerLayers` `0003c878`) | (385, footer + 61), 100 | (161, footer + 30), 50 |
| Label fly-in offset (`cellForRowAtIndexPath:`) | -600 | -200 |

- The table is from `solveMetrics` (`0004422c`), `drawSelf` (`00044b60`), `SHSMenu` (`000337b0`...) and
  `addPortraitToMenu` (`0003d3f0`). The line-offset arrays were read from the binary's data.
- The label fly-in offset is the one constant that is not halved.
- `setPortrait` (`00043aa0`) sets SHS HD's row colours per theme.
- Fonts come from `initFonts` (`00026234`):
  - Title: the bundled name face, 26 points, dark red (theme 2 rose), with a 4.0 stroke twin and gap 8.
  - Description: Arial Rounded 16, black (theme 2 rose), gap 10. A backtick switches it to Trebuchet italic.
  - Options: Arial Rounded 15, black (theme 2 rose), gap 8.
- `drawSelf` raises the title by the field at CSFont +0x18 (SHS HD reads +0x14). This is read as the same
  descent in CoD's older CSFont layout, not separately confirmed.
- **Checked against the 1x photos (2 px per point).**
  - IMG_0483 (no character): every rule (210, 254, 298, 342), both panel edges and all text within half a
    point.
  - IMG_0406 (portrait, two-line description) and IMG_0482 (timed): same layout. Side-by-side images are in
    `reference/screenshots/verify/cod_choice_*`.
- **Not yet ported:** the rapid-fire quiz (service 71) still uses the Android page.

## Speaker names

CoD 1.4.7's `SHSUIDialog::updateTitleBounds` (0003a030) and `animateTitleLayer` (0003a174) are SHS HD's. Names are
laid out by `speaker_names.hd_speaker_label` over CoD's own layout 17 (resource 14, column units):
- **Normal title regions:** nodes 0x2e / 0x4c / 0x6a. A name taller than its region takes the tall node 0x25 /
  0x43 / 0x61, with the header extra 40 instead of 8.
- **x nudge:** +1 for speaker type 1, -2 for type 2.
- **Flags:** 0x19 / 0x1b / 0x1a. Title lines are indented (0, 20) / (0, 5), with gap 8.

Two constants are not halved: a title is short under 135 of CoD's points and then shifts 15. SHS HD's 135 and 15
are iPad points, so 67.5 and 7.5 units (`points_per_unit=1, shift=15`). The names used to take Android's
shrink-to-one-line fit.

Checked against IMG_0392 (Natara Williams, two lines), IMG_0415 (Realtor, right) and IMG_0310 (Sophie, left). The
side-by-side images are in `reference/screenshots/verify/cod_name_*`.

## The score notice ("Detective Score Up!")

Service 88's notice is SHS HD's letter effect, not Android's typed notice (`cod.profile.LETTER_NOTICE`).
- **Same code.** CoD 1.4.7's `SHSUIDialog::startLetterEffectAnimation` (00038d84) has SHS HD's code and timings:
  letters 0.05 s apart, a 0.2 s rise, 1.2 s, spacing 3, and an empty letter 5. It starts 0.25 s after the portrait
  animation, with spacing 3.0, as `setup` calls it.
- **CoD's own constants.** The raise is 30 (SHS HD 60) and the right limit 300 (748), over the 128-point portrait
  layer. The padding is not in that function; 10 is fitted to the photos (`dialogue_notice.COD_NOTICE`).
- **Fonts** (`updateFonts` 00038b18). Every CoD speaker seen is theme 1: TrebuchetMS-Italic 20 in 0xf0513c with a
  1.5 stroke (+0x17328), over a black twin with a 6 stroke (+0x18b48). IMG_0322 / IMG_0412 show red letters edged in
  black inside a white outline, drawn as a white 6-point outline, the red fill and a black 1.5-point edge
  (`DialogueRenderer.cod_notice_font`).
  - Themes 0 and 3 use TrebuchetMS-Bold 20, black; theme 2 uses rose. Neither is drawn yet.
- **Checked against IMG_0322.** The outline's left and right edges are within half a point; the height is within
  about a point.

## The background window

**Native.** CoD's iPhone screen shows a scene's 480x720 art at 1 px per point. In IMG_0483 the screen starts at the
art's (0, 180), exactly `background_origin`'s focal point. Its chapter card (`SHSUIChapterScreen::animate`: bounds
320 x 480 at (160, 240)) shows the whole picture fitted to the screen (IMG_0479: the art at 2/3, error 2.0 of 255).

**In the 3:4 frame (owner's choice, 2026-10-14).** Backgrounds behave as SHS's SD backgrounds do, filling the frame:
- **Scenes** pan with the speaker (`location_pan`, the art's width given as 960 HD points) with `HD_BG_SHIFT`'s
  vertical offset, so the window always stays inside the art.
- **The chapter card** scales the picture evenly until it covers the frame, centred on the column's centre (`'cover'`).
  SHS HD's own card stretches its picture to the frame, which would distort CoD's 2:3 art.
  - The card itself is drawn on the whole 768 x 1024 frame, as SHS HD's is, so its black opening layer covers the
    picture. Drawn in the CoD column it left the picture showing around a black column (owner's test, 2026-10-14).
  - **Text.** Wrapping, alignment and each glyph's place stay CoD's (fonts 528 / 530, in CoD points mapped at 2x from
    the column's origin). With the SHS HD art source each glyph is SHS HD's 2x one (589 / 590, 591 / 592): the same
    faces at exactly twice the height (66 / 46 against 33 / 23), centred on CoD's cell, since SHS HD's cells are a
    little wider (2.05-2.14x). Without the art source, CoD's own glyphs are drawn at 2x.

Plain iPhone placement reached past the art's left edge and left dead space. A window that does run past an art's
edge keeps the art's scale rather than stretching it: the old stretch made CoD's art about 26% wider. SHS's
backgrounds never ran past the art in a 20-episode sample (0 of 2,974 frames).

## The portrait picker

Service 78 draws CoD's `SHSUIPortraitSelect`: SHS HD's at iPhone size, without the frame offset
(`desktop_picker.CodCharacterPickerRenderer`).
- **Box.** Widget 47 sits at (0, 120, 320 x 240).
- **Portraits.** `ARR_PORTRAIT_POSITIONS` are (160, 275), (52, 241), (115, 170), (206, 170) and (269, 241), which is
  SHS HD's halved. The scales are the same as SHS HD's.
- **Each portrait** is the picker ring (frame 43 or 44 of pack 126) and the art in its housing, at opacity
  scale x scale (`selectPortrait` 0004fc5c).
  - The opacity is applied to the ring and the art separately: iOS of CoD's era has no group opacity.
  - Where ring and art overlap, the side portraits therefore read stronger than one flattened layer would.
- **Title.** The title is drawn in the speaker theme's name face (26), its ink centred at (160, 112).
- **Check button.** It is frame 41 at (205, 347).
- **Hint.** The hint goes on the shared bottom bar.

Checked against Fallon Family Christmas (IMG_0458) and Volume 8 (IMG_0499). The side-by-side images are
`reference/screenshots/verify/cod_picker_*`.

## Name entry

Services 17/40 draw CoD's `SHSUITextEntry` (`desktop_input.InputRenderer._draw_cod`).

**Same code as SHS HD at iPhone size.** CoD 1.4.7's `initTextEntry` (0003f620) is SHS HD's with m30/m20 for m60/m40:
- It uses the same widget 0x2e and sub-elements 0x12/0x17/0x2c.
- It picks the same one-line or two-line header (root 10 or 1) by comparing the title's height with node 18's.
- Its `tick` (the alphanumeric filter) is unchanged.

**Layout.** The panel is CoD's own layout 46 in screen points:
- **Position.** x = (320 - 280) / 2, and y = 151 - promptHeight. That is the base IPA's rule (000a0238). The height
  is the prompt's cap height (0.716 x 16), plus one line per extra prompt line.
- **Art.** The nodes are tiled from pack 126 (slot 0) and the theme-1 box pack 204 (slot 2), which gives the grey
  border.
  - With the SHS HD art source, both come at 2x. The border is SHS HD's 247 recoloured (`cod/hd_art.py`).
  - The white fill and the field's nine-piece outline are SHS HD's 155 frames 4 and 60-68, in CoD's look
    (`COMMON_FRAMES` 0 and 51-59). Each is an exact 2x of CoD's frame. The fill is unchanged; the outline corners fit
    at about 9 mean error.

**Fonts** (`initFonts`). All three are 0xff000000, black:
- engine +0x4a768, Arial Rounded 30 (title);
- +0x4bf88, Arial Rounded 16 (prompt);
- +0x4d7a8, the bundled name face 24 (typed text).

`cod.profile.NAME_COLORS['PajamaHip24']` had been SHS's blue; it is now black.

**Text placement.**
- **Title.** `drawTextCentered` uses node 18's rectangle. That rectangle is read before the tall header is shown and
  never read again. So a two-line title is centred on the one-line slot and runs down toward the prompt, as in
  IMG_0493 ("What do you / type?").
- **Prompt.** It sits 0.6 right of node 23, with its baseline 12.3 below the node's top (SHS HD's anchors).
- **Typed text.** Its baseline is 18.7 below node 44's top (measured).
- **Cursor.** It is a solid bar in the name font's dark red (139, 0, 0), 3 x 24 points. Its top is 2.5 below node 44,
  and it sits 3.5 past the text's ink (measured on IMG_0493/0505).

**Checked** against Fallon (IMG_0457), Volume 8 Chapter Eight (IMG_0493) and Your Case's first name, last name and
hometown (IMG_0502/0505/0507):
- The title, prompt and typed text are within half a point.
- Volume 8's two-line title is within a point.

The images are `reference/screenshots/verify/cod_name_entry_*`.

**Background.** In these photos the screen shows the art from (80, 180), CoD's plain centred placement. In the frame,
the art keeps following the last speaker's pan, so it always covers the frame (owner's choice, above).

## The quiz

Service 71's timed word quiz is drawn on CoD's own panel (`ChoiceRenderer.cod_page(scored=True)`), with SHS HD's pacing
(`WordGame.hd`).

**Same code at iPhone size.** CoD 1.4.7's `setScored`, `drawScore` and `drawScoreEffect` are SHS HD's with every
size halved (m41/m18/m19/m15 for m82/m36/m38/m30).
- **Score layer.** 41 x 19 at the timed footer's node 17, (187, 21). The text is TrebuchetMS-Bold 25, white, with a
  0.3 stroke (+0x3e668): SHS HD's 50 / 0.6 at half size.
- **Score effect.** 18 x 15 at node 18, (247, 12). "+N" is TrebuchetMS-Bold 16 green (+0x3fe88); "-N" is red
  (+0x416a8).
- **Effect rise.** `doScoreEffectAnimation` is byte-identical to SHS HD's: the label still rises 30 points, which is
  twice as far in column units.
- **Running man.** `updateTimerLayers` (0003c878) puts it at (161, footer top + 1 + 6 + 24), one point below the
  circle timer. It is common pack 126 frames 23-27, 0.07 s each.

All of these sit in `hd_choice.COD_GEOMETRY`; SHS HD's are the `PanelGeometry` defaults.

**HD mirroring (SHS HD art source).**
- The timer pie was already mirrored.
- The running man is now SHS HD's 155 frames 28-32, recoloured from SHS HD's blue to CoD's grey
  (`cod/hd_art.COMMON_FRAMES`). These are the same five poses, though not exact doubles, so they keep their own size.
- The score capsule and timer notch are slot-2 frames 9-12 of the theme box pack, already SHS HD's recoloured skins.
- CoD's style is kept: black description and options, its own row colours, and the bundled name face for the title.

**Hint.** `initActionMenu` calls `setTimed`, so the quiz shows "Touch choice before time runs out", as the photos do.
This applies in SHS HD too.

**Checked** against 14_2 Accelerant's "Identify the IP address!" (IMG_0516, and IMG_0519-0521 / 0517-0518 during
play): the panel, rows, capsule, digit, runner and "+1" sit where the photos have them.
- `reference/screenshots/verify/cod_quiz_IMG0516_vs.png`
- `reference/screenshots/verify/cod_quiz_score_effect_IMG0520_vs.png`

The quiz is in 18 calls over 15 episodes. Single-chapter ones include Accelerant, Unfinished Business, New World
Order 1 and 2, True Faces, Sunset and City of Love Part 2.

## The Exit Game? prompt

**Native.** CoD 1.4.7's service 100 saves, then calls `CSEngine::exitAndShowURL`, which is `UIApplication openURL`
with no prompt. Its menu engine does have the prompt:
- **Menu 16** (logical resource 15; strings in resource 13) is "Exit Game?", with the message "If you follow this
  link you will exit Cause of Death and open your browser. Proceed?".
- **No** is a back step. **Yes** is engine action 24 (`doMenuEngineAction` case 0x18: `goBack`, then
  `exitAndShowURL` with the stored link).

**Ours.** As with SHS's script and wall links, the runtime offers a script's link behind that alert
(`Desktop._offer_link`, `exit_menu` / `exit_action`). That is this player's addition, so a desktop browser never opens
unasked. Like the SHS notices, it dims the scene sepia and holds the game.

Only two CoD episodes call service 100. Both go to an App Store page:
- Halloween Special Dead Man Walking 1, for Ghost Harvest;
- What Happened To Colt Part 2, for SHS's free edition.

**The window** (`desktop_cod_menu.CodMenuWindows`). Since 2026-10-14 it is SHS HD's window
(`desktop_hd_menu.HdMenuWindows`: the 604-point card centred in the 768 x 1024 frame, its title, message, button strip
and 156 x 58 buttons) in CoD's dress, by the owner's rule for every CoD menu. The same class draws CoD's other
menu-engine windows (see "The title screen and launch").
- **Card.** CoD's window drawn as vectors at HD's size (`draw_cod_card`, measured on pack 16 frames 78-80 and pack
  204 frame 3): the (85, 95, 176) border around the top 112 points and the footer's 86, the grey edge (89, 90, 90)
  beside the body between them (IMG_0514), a white face at alpha 242.
- **Text.** Arial Rounded; titles and messages black, rows (60, 60, 62) on lavender / pink; rules (166, 166, 166).
- **Buttons.** CoD's blue button (frames 90-92, pressed 93-95) at HD's size with a white label, or the back arrow
  (frame 89). CoD has no orange alert buttons, so its notices' OK is blue too.
- **HD mirroring.** With the SHS HD art source, the buttons take SHS HD's pack 32 frames 13-18 (exact doubles) as
  their outline, filled with CoD's colours sampled by position (`cod/hd_art.positional_menu_buttons`).
  - The colour-keyed recolour that the skins use banded these. SHS HD's button has an inner bevel and a lighter
    gradient, so shades from different places shared a key and painted CoD's dark rim across the middle.
  - The card has no SHS HD counterpart, since SHS HD's windows use its dialogue skin, so it stays CoD's.

**Superseded.** The first version drew the window at CoD's own iPhone geometry (layout 39's slots, a 302-wide card,
TrebuchetMS labels) and matched IMG_0514 within half a point. The owner's rule replaced that with HD's layout.

## The bottom hint

Both iOS builds draw the hint in an ArialMT 11 CSFont (CoD +0xca48, white at alpha 0xb0). Both `initFonts` build the
ArialMT advance table from the Arial Rounded MT Bold face:
- CoD case 4: `CSFontInfo::init(+0x7010, *(+0x208))`.
- SHS HD 0002b04a: the faceplace text's bug.

So the hint is Arial's letters at Arial Rounded's advances (`DialogueRenderer.footer_font`). "Touch the screen to
continue" now measures:

| Source | Width |
| --- | --- |
| SHS HD photos IMG_0132 / IMG_0133 | 154.0 units |
| Arial Rounded advances (predicted) | 154.4 units |
| Plain Arial (ours before) | 141.2 units |
| CoD photo IMG_0496 | 152 points |
| Ours now (CoD) | 154 points |

Android's bitmap hint is unchanged.

## The pause menu and Options

CoD's gear opens its menu engine's windows (logical resource 15, strings in bank 13; `desktop_cod_pause.CodPauseMenu`):

| Window | Menu | Items |
| --- | --- | --- |
| Pause | 24 | Resume (engine 33), Options (queue 20), Help & About (queue 13), Main Menu (engine 34), and an "Alert" item with condition flag 16 |
| Options | 20 | Vibration (condition 8, hidden on the photographed iPad; this player shows it for its stand-in buzz), Game Music, Music Volume, Sound FX, Sound FX Volume, Play My Music, back |
| Help & About | 13 | Introduction, Controls, Now Airing, Episodes On Demand, Network, About, back. The pages are menus 0-5. |

**Same structure as SHS HD.** The string ids are SHS HD's (8, 9, 10, 20, 120, 12-15; the pages 133-140, 16 / 0),
and as in SHS HD the rows are a UIKit table with a UISwitch and a UISlider.

**SHS HD's layout in CoD's style (owner's choice, 2026-10-14; it applies to every CoD menu).** `CodPauseMenu` is
`desktop_pause_hd.HdPauseMenu` with only its style overridden. From SHS HD it keeps:
- the 604-point card in the 768 x 1024 frame, with 112-point headers, 88-point rows (130 for a slider row) and an
  86-point footer;
- the centring;
- the UIKit switch and slider sizes;
- the taller text pages;
- the hit areas.

CoD's own card is the same width, but its iPhone controls are twice HD's size in frame points; those are not used.
CoD's styling, measured on IMG_0460 (Pause), IMG_0461 (Options; IMG_0342 at 2x agrees) and IMG_0462 / 0463 (Help &
About):

| Part | CoD style |
| --- | --- |
| Card | CoD's window as vectors at HD's size, as SHS HD draws its own (`desktop_cod_menu.draw_cod_card`): a 6-point (85, 95, 176) border with 20-point corners around a white face, both at alpha 242 (pack 16 frames 78-80), the grey edge (89, 90, 90) beside the body (pack 204 frame 3) and the footer's rule (166, 166, 166) (frame 74). Stretching the 1x pieces 2x left their corners soft and off the grey strips. |
| Text | Arial Rounded. Titles are black, row labels (60, 60, 62), and a help page's text black on white (255, 255, 254). |
| Rows and rules | Rows alternate lavender (240, 240, 248) and pink (255, 243, 253) from the first. Rules are (166, 166, 166). |
| Art | The back button, its arrow and the slider row's speakers are CoD's (pack 16 frames 89-92; common pack 126 frames 45 / 46) at SHS HD's sizes. |
| Controls | The switches keep UIKit's own bold ON / OFF label. |

**HD mirroring.** With the SHS HD art source, the back button, arrow and speakers are SHS HD's doubles filled with
CoD's colours (`cod/hd_art.positional_frames`).

**Owner's choices (2026-10-14).**
- **Sliders.** CoD's photos show no slider between the speakers: CoD ships no slider art, and its stock UISlider did
  not draw on the device. One is drawn as SHS HD's is.
- **Options categories (2026-10-14, both games).** Options lists categories, laid out like Help & About's list, and
  each opens a page of its own rows (`desktop_pause_hd.OPTION_CATEGORIES`):
  - **General:** Side Panels (in a story, SHS only), Autoplay Dialogue, Skip Ad Intros (SHS only, main menu only:
    it acts as an episode starts), SHS HD Backdrop (both games, where a collage exists) and Check for Updates (main
    menu).
  - **Sound:** Game Music and Sound FX, with their sliders.
  - **Extras** (owner, 2026-10-21): the play aids, Disable Choice Timer, Choice Hints (CoD: Choice & Answer Hints)
    and Ask to Skip Mini-Games (CoD's word quizzes too).
  - **On the main menu only:**
    - **Episode Titles** ends General. It is a button (SHS HD's orange footer button; CoD's blue) that steps
      through the title languages. It is offered where some episode has a translated title, so not in CoD (none of
      its 74 has one).
    - **Data Management:** Add Episodes, Open Another Library.
  - **Controls** sit against the card's right side, 26 points in (owner's choice; SHS HD's switches sat 168 in): the
    79 x 27 switch, and the Episode Titles button at 104 x 34 with an 18-point label.

  Every switch is stored in each game's own `player.json`, not shared between games (yet).
- **Left out.** Play My Music: it opens the device's music library, which a desktop doesn't have.

**Help & About.** The pages use SHS HD's page layout (a long title, such as "Episodes On Demand", takes two lines,
as in SHS HD).
- **Now Airing and Episodes On Demand** describe this player's library rather than EA's paid store. They are SHS's
  rewrites adapted to CoD (`help_text_overrides.COD_HELP_TEXT_OVERRIDES`):
  - the two release stages (On Demand, then Now Airing), with episodes listed by their first release;
  - why most dates are exact: the Cause of Death Facebook page announced each release. The few it never announced are
    approximated from the weekly schedule, the wiki or the App Store listing (docs/COD_RELEASE_DATES.md);
  - the tile grid selector behind Play/Resume, which is planned for CoD;
  - no SD tag, which is SHS-only.
- **Introduction, Controls and Network** keep CoD's own text.
- **About** is the owner's: CoD's credits plus this project's credits, the fan-preservation disclaimer SHS's page has,
  and the Cause of Death Discord link. Its editing copy is `SHSHD/cod_about_page.txt`.
- **Version token.** CoD's is `~259~` (SHS HD's `~276~`); both are replaced with this player's version.
- **Push Notifications** (main menu only) is CoD's menu 6: "Push Notifications" (235) and "Do you want to be notified
  when new episodes are released?..." (237), as on IMG_0522. SHS HD's ids (238 / 240) are, in CoD's bank, the iOS
  permission prompt ('"Cause of Death" Would Like to Send You Push Notifications').
- **Links.** A URL in a page's text becomes a link. In a story it now goes through the game's own "Exit Game?" prompt
  (`Desktop.command('pause_link')`), for SHS too, as the main menu's copy of the page already did.
- SHS's own overrides are not applied to CoD.

## The title screen and launch

CoD's front end is SHS HD's (`application_hd.HdShell`) on CoD's menu engine (`application_cod.CodShell`), in SHS HD's
layout with CoD's art (owner's choice, 2026-10-14).

**Same as SHS HD.**
- **Main menu layouts.** CoD's layouts 74 / 75 / 77 / 79 are exactly half of SHS HD's. CoD's layout units are points,
  SHS HD's are half points, so the numbers agree.
- **Button art.** CoD's pack 272 is SHS HD's 315 at 1x, except frames 14 / 15 (the info button's two states), which
  are swapped.
- **Label fonts.** CoD's 532 / 533 are SHS HD's 593 / 594 at 1x.
- **Buttons.** Play/Resume, Now Airing, Episodes On Demand, More EA Games, the gear and the info button, in the same
  places. The labels are CoD's strings 118 / 119 / 83 / 227.

**Different.**
- **The picture.** CoD's title is one 320 x 480 painting (resource 6), not SHS HD's four animated layers; resources 7-9
  are empty. It fills the 3:4 frame's width (2.4x, against the buttons' 2x). It is placed so that the device's
  Play/Resume top (CoD point 346 on IMG_0464) falls on ours (frame point 753). The logo then sits just above the wedge,
  as on the device, and the taller picture loses 77 points of sky and 51 of the brick floor.
- **The entrance.** Only the buttons slide in, since there is one layer (owner's choice). On the first arrival they
  come with `animateMainMenuButtonsIn(1.5)`, as in SHS HD, so the wedge moves from 3.0 s (each layer holds its
  delay twice: `desktop_main_hd.py`); otherwise at once.
- **The launch screen.** CoD's own `Default@2x.png` (the EA logo on a flat grey of 105, 640 x 960) is fitted to the
  frame's height on the same grey, under "Play with sound?" (menu 7; IMG_0473). After the answer the screen goes to
  black and the main menu slowly fades in from it: CoD has no EA flash, but runs SHS HD's flash code without the flare
  (1.4.7, read-only):
  - `setAppMode(102)` (`00022cd4`) adds a full-frame black layer that fades in (opacity 0 -> 1) over 1.0 s, beginning
    1.0 s later. The EA screen stays meanwhile.
  - When that animation ("flash-all-white") stops, `SHSAnimationDelegate animationDidStop:finished:` (`00017388`)
    sets up the main menu (`setAppMode(101)`) and fades the black out (1 -> 0) over 1.0 s, beginning 0.2 s later.
  - `application_cod.py` (`BLACK_HOLD`, `BLACK_FADE`, `REVEAL_DELAY`) keeps these times.
- **Menu music.** `doSoundManagerTransition` (00025c60) plays 0x2011 (8209) once, unlooped, where SHS HD plays 0x2017
  (8215). The menu was silent because the app always asked for SHS's asset; it now takes the game profile's
  `MENU_MUSIC`.
- **Beside the frame.** With the SHS HD art source, the window around the frame shows SHS HD's faded collage
  (resource 10), on the menus and in episodes, as SHS HD's do. Options has a "SHS HD Backdrop" switch (player.json
  `hd_backdrop`, on by default; this player's own) that leaves the dark fill instead. The title painting stretched to
  the window is gone (owner's choice).

**Menu numbers.** CoD's menu engine has SHS HD's windows under other numbers; `CodShell` translates them.

| Window | SHS HD | CoD |
| --- | --- | --- |
| Play with sound? / Continue playing your music? | 7 / 8 | 7 / 8 |
| Privacy Policy / EULA / Terms | 16 | 15 |
| Exit Game? | 17 | 16 |
| Disable / Enable Usage Sharing | 19 / 20 | 18 / 19 |
| Delete Saved Game? (`~260~`; SHS HD's `~277~`) | 12 | 52 |
| Connection Error | 41 | 38 |
| Want More Content? / Miss An Episode? | 23 / 24 | 22 / 23 |

**Engine actions.** CoD's numbers and the SHS HD actions they map to:

| Action | CoD | SHS HD |
| --- | --- | --- |
| The sound answers | 0-4 | 0-4 |
| EULA / privacy / terms links (strings 201 / 202 / 200) | 21 / 22 / 23 | 14 / 15 / 16 |
| Exit Game's Yes | 24 | 18 |
| Close the window | 25 | 9 |
| Disable / enable usage sharing | 26 / 27 | 19 / 20 |
| End menus: More EA Games / Main Menu / Replay | 30 / 31 / 32 | 23 / 24 / 25 |
| Delete Saved Game's Yes | 36 | 10 |

Outside the end menus, Main Menu (31) only closes the window.

**Privacy list.** Its usage-sharing rows are two items with conditions (`checkItemConditions`), not SHS HD's `~275~`
label:
- flag 2, "Enable Usage Sharing", shows only while sharing is disabled;
- flag 4, "Disable Usage Sharing", shows only while it is on.

`CodMenuWindows.items` hides the one that fails, and also Vibration (8) and the pause "Alert" row (16).

This fork hides both usage-sharing rows in either state, as it does SHS HD's (owner, 2026-10-15): the runtime sends
no usage data, so the switch would only confuse. A row is hidden by the window it opens (CoD's 18 / 19, SHS HD's
19 / 20) or the engine action it runs (SHS HD's 17; `HdMenuWindows.HIDDEN_ACTIONS` / `HIDDEN_MENUS`).

**Episode buttons.** Play/Resume, Now Airing and Episodes On Demand (the main menu's and the end menus') open SHS
HD's pickers in CoD's dress (see "The episode screens"). Without the SHS HD art source they open the plain episode
browser.

**Switch Game.** "More EA Games" switches to the other game in both HD front ends (owner's choice, 2026-10-14):
- **Where.** The main menu's fourth button and the end menus' row (SHS HD action 23, CoD's 30).
- **What it runs.** Upstream's Switch Game (`Application.switch_games`). With the other game's library set up, that
  game opens; otherwise the game chooser does. A switch is not a launch, so there is no loading screen or "Play with
  sound?" again.
- **Fades (owner's choice).** The frame fades to black (0.5 s); the backdrop beside it stays. Then the other game
  arrives:
  - Cause of Death: its menu fades in from black as after its EA screen (0.2 s of black, then 1.0 s).
  - SHS: SHS HD's flash (the flare and the white, with the EA jingle) over black, then the main menu's entrance.

  Opening a library makes one frame last about half a second. The shell's animations advance at most 1/20 s a frame
  (`MAX_STEP`), so that frame no longer skips the fade-in (it used to cut straight to CoD's menu).
- **Labels.** Each carries the other game's name: "Cause of Death" in SHS HD, and in CoD "Surviving HS". The full
  "Surviving High School" (455 points in the green label font) is too wide for the 310-point button; "Cause of Death"
  (297) fits, about as snugly as "More EA Games" (283). The end menus' rows take the full title.
- **Libraries.** A test setup can say where each game's library is with `--game-library GAME PATH` (repeatable; this
  fork's option). Those paths are used for the switch and never written to the launcher's remembered locations.
  `play-hd-art-test.ps1` passes `test-library` and `cod-library`.

## The episode screens

By the owner's choice (2026-10-14) CoD uses SHS HD's three episode screens, not its own iPhone "Play My Episodes"
list (IMG_0467):
- **Play/Resume** is the tile grid (`desktop_episode_picker.HdEpisodePicker`), with a title-card preview per episode.
- **Episodes On Demand** is the list grouped by category (`desktop_episode_list_hd.HdEpisodeList`).
- **Now Airing** is the same list grouped by year of first release.

`desktop_cod_episodes.py` gives them CoD's style. The grouping and dates are CoD's own (`cod/episodes.py`). The
screens need the SHS HD art source, for the tile masks (resources 13 / 14), the popup card and the row divider.

**Categories.** SHS's rules misfile CoD: the bundled base game becomes "Mega Packs", and uncatalogued episodes take a
season from SHS's pack numbering. So CoD uses its catalogue's own categories:

| Category | Contents | Source |
| --- | --- | --- |
| Volume One | the base game, captioned "Volume One: The Maskmaker" | the catalogue's synthetic entry (pack 0, episode 0); bank 13 strings 79 / 182 |
| Volume Two - Volume Six, Season 7 - Season 15 | the Volume sets | both device catalogues name the sets this way |
| Volume 13 | shares Season 13's row: Interlude: Perfect Getaway | 1.4.7's episode catalogue, (1201, 45) |
| Volume 14, Volume 16 | their chapters | catalogue |
| Side Stories | the Side Stories and the Halloween special | catalogue |
| Premium Content | with A Fallon Family Christmas | catalogue; owner's placement (1.3.4 filed its byte copy `1_1_Magic_School.exp` under "Interlude") |
| Now Airing Special | the free Now Airing promo, captioned "Now Airing Special" | no catalogue lists it; 1.4.7's store listing gives it this category and name (product 840878). Owner, 2026-10-15: follow the store (it was first in Side Stories as "Now Airing Special: Just Another Day") |

Anything else uncatalogued goes to Premium Content, SHS's fallback.

**Order.**
- **Categories:** the volumes by number first, then Side Stories, then Premium Content, as SHS HD's rule puts its
  seasons before the generic categories, then any other category (Now Airing Special). CoD's own list and 1.4.7's
  catalogue put Premium Content and Side Stories right after Volume One instead.
- **Episodes in a category** go by first release, which is the order the owner listed Premium Content in.

**Now Airing.** Episodes are grouped by the year of their first release (docs/COD_RELEASE_DATES.md); a Volume set takes
its Chapter One's date, as SHS's season bundles do. Nothing is set apart:
- CoD has no vote packs and no redundant bundles.
- Its one overlap, Perfect Getaway's Now Airing file, repeats an interlude inside the Volume 13 set, which is the only
  copy of that volume's other chapters. Both stay, each at its own date (both 2013).

**Previews** are generated title cards, as for SHS's non-bundled episodes: about 29 seconds for all 74, cached in the
library's `thumbs/`. Volume One's "Prologue" card is black with the title, as on the device (IMG_0474). A Volume set
shows its Chapter One card.

Two episodes have no preview and keep the picker's flat card, because the capture can't reach a title card:
- Volume 16's Chapter Seven: Sunset reaches a quiz before its card, and the capture doesn't answer quizzes.
- Fourth of July Special, Part 2's opening fight loops on the first choice.

**Styling.** The structure is SHS HD's; only these parts are CoD's:

| Part | CoD style | Source |
| --- | --- | --- |
| Backdrop | the title painting, placed as on the main menu and dimmed as SHS HD dims its own | `desktop_cod_main.title_layer` |
| Buttons | blue back arrow and a blue Restore (CoD has no orange button) | `desktop_cod_menu.CodButtons` |
| Popup | SHS HD's `popupBackground.png` with its (117, 137, 255) border recoloured to CoD's (85, 95, 176); black labels and alert text | `recolor_border` |
| Category bands | (85, 95, 176) | pack 16 frames 73 / 76 |
| Rows | (239, 243, 247) and white, starting with the tinted one as IMG_0467 does; selected (181, 195, 236) | frames 82 / 83 / 84 |
| Separators | (222, 222, 222) | measured on IMG_0467 |
| Icons | ring (102, 120, 213) at alpha 128; play (60, 85, 205) at 102; pause (50, 70, 161) at 128 | frames 101 / 96, their own alphas |
| Text and card | black text; card border (85, 95, 176) | frame 81 |

**Strings** come from bank 13:
- New Game 19 and Continue 26;
- Restore 194, and "Restore Not Necessary" 188 / 189 (SHS HD's 197 and 191 / 192);
- the list titles, Episodes On Demand 83 and Now Airing 119.

A message over the picker is titled with the game's name, no longer always "Surviving High School".

**Checked** against IMG_0467 side by side (`verify/cod_picker_on_demand_IMG0467_vs.png`): bands, rows, icons, text,
card border and buttons agree. CoD's list has a "MY SAVED GAMES" section that SHS HD's list doesn't; saved episodes
show a pause icon in their own rows instead, as in SHS HD.

### Episode info (this fork, 2026-10-15)

With 1.4.7's store listing imported, every episode gets an info button:
- **On the grid** it sits at the tile's bottom-right corner, where SHS's SD mark goes, in the SD mark's style: its dark
  plate, with an "i" in a ring in the mark's text colour (owner, 2026-10-15).
- **In the lists** it sits left of the play / pause icon: that icon's ring with an "i", in CoD's icon colours.

It opens a card on the alert's card, showing:
- the picker's own title;
- the airdate from docs/COD_RELEASE_DATES.md (as in the lists, not the store's upload date);
- the original price;
- the store description, at the largest size from 20 down to 15 points that fits above OK.

There is no native screen to follow.

**The store listing** is `Documents/mtxprods` from a 1.4.7 device backup (`cod/store.py`). Its format, what the
library keeps of it, and its coverage are in [COD_STORE.md](COD_STORE.md).
- **Importing it:** it goes in `cod_episodes/` or beside the IPAs in the import folder or a bulk archive, or comes
  through Add Episodes or a drop.
- **What the library keeps** (`store` in library.json, `content/<sha>.json`): every product field except `granted`,
  each product's `binPack` byte for byte, and its parsed contents. So the chapters inside the Volume sets keep their
  own entries, for splitting the sets later. The file's user record (device and account identifiers, push token,
  analytics) is never kept.
- **Which product an episode takes:** the single-file product named after its file. The store's `_NA` / `_OD` /
  `_airing` / `_NOW_AIRING_ONLY` suffixes fold. When there are two, the On Demand (paid) copy wins. The Now Airing
  Special was only ever free, so it takes its free copy.
- **Bundles:** a Volume set takes its own set product. Products naming several files (bundles, combos) describe a set
  and are skipped.
- **Price:** "Free" or the store's amount, e.g. "$0.99".
- **Volume One** was never sold. Its card uses the App Store listing's description, supplied by the owner, priced
  Free, and is shown only when a store listing is imported.

The owner's listing gives all 74 of their episodes a card.

## Audit: services 71 and 78, and 1.4.7's dispatcher (2026-10-08)

Addresses in this section are from the **armv7** slices (the older audits
below cite armv6). In 1.3.4 the dispatcher is `SHSScript::syscall`
`0003831c`; in 1.4.7 it is in the same function. Both versions were analysed
with Ghidra headless, and constants were read with Capstone.

**Service 71, the timed word quiz (18 calls in 15 episodes).** Dispatcher
case 0x47 builds an `SHSUIMenu` with `initActionMenu`, the same iOS action
menu that SHS HD uses (`WordGame.hd`). Android's `FUN_000af010` pacing does
not apply.

| Item | Value | Where |
| --- | --- | --- |
| Arguments | title, description, good list, bad list, duration ms, character, portrait mode, refresh ms | case 0x47 |
| Fly durations | 0.3 s on, 0.5 s off | `setFlyDurations`, `0004003e` |
| Fly-on finish | 0.7 s timer | `flyOnNewChoices` `0003fed8`, literal `0003ff40` |
| Skip input / tick | 400.0 / 0.2 s | `00040ab8` / `00040aac` |
| Deal | arc4random, one good, two bad, a fourth of either, 20 swaps | `resetActionMenu` `0003fb60` |
| Sounds | **8003** for a positive weight, **8004** for a negative one, none for zero | `handleMenuSelection` `0003ea4e` |

The runtime gives CoD the `WordGame.hd` pacing (`IOS_ACTION_MENU`) and these
sounds (`WORD_GAME_SOUNDS`). SHS keeps 8001/8002, and Android pacing unless
the HD bundle is present.

**Service 78, the portrait selector (2 calls).** "Choose your look!" appears
in Fallon Family Christmas ("A Christmas Curse", script 25003) and in
Volume 8's script 25017. Case 0x4e calls `createUIElement(5)`, an
`SHSUIPortraitSelect` (`createUIElement` `00037e5c`). It reads the same text,
count and character-array arguments. `selectPortrait` (`0004fc5c`) swaps the
tapped portrait with the front one, and `setReturnValue` (`0004f840`) returns
the front portrait's original index, matching `CharacterPicker`.
`touchesEnded` (`0004fe00`) plays **8005**, CoD's click, for a swap and for
the confirm button; tapping the front portrait is silent. The runtime uses
these sounds (`PICKER_SOUNDS`); SHS's 8013/8010 do not exist in CoD's bank.
Its presentation is ported ("The portrait picker" above). `createUIElement`
type 16 is `SHSUIChapterScreen`, the chapter title card.

**1.4.7 compared with 1.3.4.** The functions were compared case by case and
function by function, with the decompiler's renaming normalised.

- **Service 70:** same selectors, plus selector 11, which now returns 1 when
  two engine fields match (`+0x62bdc` and `+0x6483c`) instead of 0. No
  supplied CoD script calls service 70.
- **Service 99:** calls `SHSEngine::getInterstitialType` before
  `showFullPageAd`. The offline no-ad completion is unchanged.
- **Service 100:** now has its own case and no longer reaches the default
  branch. If the second argument is nonzero, it sets GameModel +0x1f, the
  `endGame` flag that `runScript09` checks to end the game when the current
  script finishes instead of returning to a caller. It then calls
  `SHSEngine::saveGame` and `CSEngine::exitAndShowURL`, and the script
  continues. All four supplied calls pass -1 from the top-level script 25001,
  whose end already ends the episode, so the visible difference is the link
  opening. The runtime keeps 1.3.4's local continuation and offers the link
  behind CoD's own "Exit Game?" alert ("The Exit Game? prompt" above).
- **Unchanged:** the quiz, choice and timeout code (`setReturnValue`
  `0003cb88`; +0x98 is still written only by `loadElement`), the quiz sounds
  and fly durations, and `SHSUIPortraitSelect`'s logic. Services 9, 91 and 95
  have the same calls.

## Timed choices with no timeout option

Many CoD action scenes build a timed incremental choice (services 2–4) whose
timeout selection is -1. Volume 7's "Let go." / "Hang on." is one example, and
it appears in most Volume bundles and Side Stories 18. CoD 1.3.4 handles the
timeout in three steps, checked read-only with Capstone:

- **`SHSUIMenu::tick` (`0003f12c`):** with no selection pending, it copies the
  timeout selection (+0x3c) into the selection (+0x30).
- **`setReturnValue` (`0003e994`):** for an incremental menu (mode 3, mapping
  flag +0x10d, always set by `initTextMenuWait` at `0003f934`), it returns
  `mapping[selection]` from the table at +0x9a. For -1, that is the short at
  +0x98.
- **The +0x98 slot:** only `loadElement` (`0003ed88`) writes it, and
  `saveElement` reads it. Each service-2 call allocates a new menu with
  operator new, so the slot keeps the allocation's initial memory.

The runtime returns **0** for this case (`cod/profile.py`,
`TIMEOUT_NO_OPTION_RESULT`). That is the value of fresh heap memory, and a
reused menu-sized block leaves the slot untouched too. It is not guaranteed
natively. The scripts examined compare the result with their options' values,
so any value that matches no option takes the same branch. Volume 7 tests
`== 1` ("Hang on.") and sends everything else to the "Let go." path.

One choice in the supplied library has a timeout selection past its options:
the number puzzle in Volume 2's script 25011 ("Pick the right number!",
6 s). It times out to 1000, with values 0–3. Natively that reads
`mapping[1000]`, far past the 0x114-byte menu, which is undefined memory. As
an adaptation the owner chose (`TIMEOUT_PAST_OPTIONS_UNMAPPED`), the runtime
returns the selection unmapped. It matches no option, so the script's
wrong-answer branch plays, which is what players would almost always have
seen. The owner will compare this on device. Other negative selections, and
SHS, keep the explicit error.

## Native audit: service 100

The supplied episodes contain four calls, all two-word calls in scene 25001.
Each passes a promotional URL string reference followed by `-1`; none reads
the return value. The surrounding choices identify external app promotions:

| Episode | PC | Target kind |
| --- | --- | --- |
| What Happened to Colt, Part 2 | 5375 | SHS App Store listing |
| Dead Man Walking, Part 1 | 135, 734 | Ghost Harvest custom URL scheme |
| Dead Man Walking, Part 1 | 725 | Ghost Harvest App Store listing |

Those arguments suggest a link-opening service in another release. They do
not establish a later implementation or the second argument's meaning.
Ghidra MCP confirms the supplied CoD 1.3.4 behavior: the unsigned comparison
at `000335cc` branches past its 0–99 table via `000335d0` to `00033778`.
This occurs before the first argument read at `000335d6`. The default sets
`r4 = 0x80000000`; the completion tail at `00034b74` / `00034b8a` stores its
low 16 bits as **R=0**, subtracts the original argument count from SP, clears
the wait flags and resumes the actual continuation. There is no URL access,
score update, result-cell write or random draw. The relevant disassembly and
bytes were checked read-only through MCP, including `000335b8` and `00034b8a`.

The CoD adapter implements this observed default specifically for service 100,
including empty frames and ignored extra words. It does not generalize default
completion to all unknown service numbers or apply it to SHS. Old stopped saves
retry only their retained service frame without replaying earlier choices.

Optional checks with the user's private episodes reach all four calls through
ordinary story choices and restore saves made with the old unsupported handler.
The Colt call continues to a title presentation; the first Ghost Harvest link
finishes its script, and the two later links continue dialogue. These outcomes
come from the episode continuations, not a hardcoded return-to-menu action.
Authored tests separately check frame removal, both call encodings, result zero,
state/randomness preservation, following dialogue or episode exit, and retained
stops for other unknown services. No original files are bundled as fixtures.

## Native audit: services 9, 70, 91 and 94–96

Audited on 2026-10-05 against the supplied CoD 1.3.4 executable through Ghidra
MCP. These numbers identify host services invoked by KiWi yield instructions.
The native dispatcher is `0003354c`, with a 100-entry relative jump table at
`000335e8`. The table, selector table and shared completion tail were checked
directly: decompilation alone omits some cases and misidentifies branches
inside the dispatcher as separate functions. Objective-C continuations were
read in LLVM assembly and their relevant bytes checked against Ghidra memory.
The runtime now implements the recovered 70/94/96 contracts, with the explicit
offline store adaptation described below. Services 9/91/95 remain guarded.

| Service | Verified CoD behavior | Difference from the SHS Android handler |
| --- | --- | --- |
| 9 | Poll upload/download, with an asynchronous success/failure callback | A real native sender exists; Android's sender is a stub |
| 70 | Platform/build/store query, selected by the first frame word | Selector 6 writes the version string; selector 10 checks store availability; selector 11 returns zero |
| 91 | Loading overlay and execution gate, starting a 1500 ms counter | Android uses a strictly-greater-than-3000 ms gate; CoD also has different frame handling for a zero flag |
| 94 | Default dispatcher completion, returning zero | Does not start SHS football |
| 95 | Reads one of two native model fields and returns its low signed 16 bits | The read resembles SHS's score getter, but CoD score initialization/producers are not established |
| 96 | Default dispatcher completion, returning zero | Does not start SHS's word grid |

A static scan found **zero calls to any of these six services** in all **420
scripts from 103 supplied external CoD EXPs**, and zero in the **eight bundled
Volume One scripts** in base resource 12. All numeric base resources were also
checked for standalone KiWi programs. This covers the supplied corpus, not
unknown releases, complete routes or every shared service's CoD semantics.
The four service-100 calls were audited separately above.

### 9: poll submission and results

The case at `000343dc` calls `SHSScript::getPollURL` (`0003261c`), hides the
dialogue layers, starts `GameModel::setDownloading` (`00011e00`), and retains
the argument frame while waiting. URL construction reads the poll ID from
argument 0 and the upload type from argument 1. Type 0 reads argument 2 as a
string; type 1 reads it as a signed number; type 2 reads an array through that
pointer, using argument 3 as its count. It also reads request words 4 and 6.
Argument positions here are zero-based; the native stack-string helper uses
one-based positions internally.

`finishPollDownload` (`00011dac`) returns **0 on failure**, without writing the
result buffer. On success it calls `parseGamePollResults` (`00011c60`), writes
returned shorts through **argument 5**, and returns **1**. The write uses
`writeArrayToStack` (`0003249a`) with one-based argument index 6. Completion
goes through `returnFromSyscall` (`0003247c`), which pops the original frame
and clears the wait flags; the loading overlay is then hidden.

The owner's offline survey requirement still applies: a local thank-you must
continue the actual remaining story without fabricating aggregate results.
No CoD survey caller was present to establish its response branches. The SHS
adapter's specific connection-error replacement is therefore not evidence for
an arbitrary CoD caller. The native failure path establishes a zero status,
but returning success or suppressing a later story screen would require
additional evidence.

### 70: selectors and script-visible string state

The selector branch starts at `000341a2`; its nine-entry relative table is at
`000341bc`. It compares the unsigned 16-bit value of `selector - 2` with 8.

| Selector | Native result and side effect |
| --- | --- |
| 2 | Return 2 |
| 3 | Return 6 |
| 6 | Copy `SHSEngine::getAppVersionString()` into script dynamic string slot 0, then return its reference `0x7ff5` |
| 9 | Return 1 |
| 10 | Return 2 when `MTX_IsStoreAvailable()` is true, otherwise 1 |
| All others, including 11 | Return 0 |

The version branch at `000341fe` writes the string at script offset `0x94`.
`getAppVersionString` (`0001b138`) reads **CFBundleVersion** from the native
main bundle; it is not the desktop runtime version or a preexisting string.
Selector 10 calls `MTX_IsStoreAvailable` (`000679e0`). The desktop has no MTX
store, so it returns **1**, the native unavailable result. This is an explicit
offline adaptation, not a claim that iOS always returned a constant. Neither
selector's side effects are supplied by SHS's Android query handler.

The runtime binds the version to the retained IPA's validated `Info.plist`,
including after save restoration. Editable manifest metadata, the desktop
package version and `CFBundleShortVersionString` do not substitute for it.
Missing `CFBundleVersion` preserves a pending selector-6 frame and the previous
dynamic string; an explicitly empty version string is supported. Version
numbers still do not restrict asset import. The derived `app_version` context
is excluded from saves; the script's mutable dynamic strings are saved normally.

Both compact and register-count calls consume exactly their original frame.
Extra words are ignored. A zero-argument call reads its selector from retained
stack backing at SP; unknown backing stops explicitly instead of defaulting
the selector. Authored tests cover these forms, native defaults, the offline
store result, mutable string handles, source metadata and saved continuations.

### 91: loading time and frame lifetime

The case at `00034ac2` shows strings 28 and 32, sets the host gate at script
offset `0x118`, and tests the first frame word. The dispatcher reads that word
at `stack[SP - argc]` even when argc is zero: retained stack backing matters,
as it does in SHS. It does not enforce a one-argument signature.

`showLoadingBar` (`0002162c`, timer write at `000219cc`) assigns **1500** to the
engine counter at `0x64910`. `onTick` (`00024f30`, counter update at `0002500e`)
subtracts at most **200** units of the supplied millisecond delta per tick,
converting the remainder back to an integer. `isLoadingBarTimerDone`
(`000170c0`) tests whether the counter is **less than 1**. It is not Android's
strict `elapsed > 3000` test.

With a nonzero first word, the native wait flag retains the frame until
`executeWithSyscalls` (`00034fbc`) sees the timer expire, hides the overlay,
returns zero and pops the frame. The zero-word-value branch instead reaches
the common completion tail immediately, while leaving the host gate set.
The later gate-completion code still subtracts the saved argument count.
Consequently, the listing exposes a second subtraction for a zero flag with
a nonempty frame. A zero-argument call subtracts zero both times. There are
no supplied CoD callers to establish a supported use of that unusual path;
the Android implementation must not silently replace it. Overlay rendering,
clock behavior and these frame cases need CoD-specific implementation and
validation before enabling service 91.

### 94–96: default cases and retained score read

Jump-table entries **94 and 96 both target `00033778`**, the default branch.
That branch puts internal sentinel `0x80000000` in the result register and
reaches the common tail at `00034b74`. With no outstanding host wait, the tail
stores the low 16 bits (**zero**) in VM R, pops the saved argument count and
marks the VM runnable. It does not instantiate a minigame, consume random
values or write score/result cells. This is a recovered native default, not
permission to ignore other unknown services or later native versions.
The CoD runtime implements these two completions for empty and nonempty frames;
the SHS handlers still enforce their own minigame argument contracts.

Service **95** has its own case at `00034b3c`. First argument **1** selects the
32-bit field at `GameModel + 0x1c14`; every other value selects `+0x1c18`.
The common tail narrows the value to the VM's signed 16-bit result. The CoD
constructors and reset path inspected here do not establish initialized
values for these fields, and service 94 does not populate them. Treating
them as zero, borrowing SHS scores, or asserting that 95 is also a no-op would
invent a result. Its producer/lifetime remains unresolved.
