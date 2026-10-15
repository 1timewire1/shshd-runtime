# Cause of Death support

EXP Runtime opens SHS and CoD as separate games. Choose **Cause of Death** in
the launcher and supply its IPA, then add CoD EXP files to that library. A CoD
APK profile has not been established. No original files, screenshots, fonts
or decompilations ship with the engine.

```sh
uv run --locked exp-tool import --game cod --ipa /path/to/CoD.ipa --episodes /path/to/CoD-Episodes --library /path/to/cod-library
uv run --locked --extra desktop exp-runtime --game cod --library /path/to/cod-library
uv run --locked exp-tool trace /path/to/episode.exp --game cod
```

## Identification and isolation

Import recognizes `com.ea.causeofdeath` and `com.ea.causeofdeathfree`, with
optional dot-separated suffixes, and validates the required `res_generated`
payloads. Version numbers and the
native executable are informational; native code is never executed. The
locally inspected package is 1.3.4 (`com.ea.causeofdeath.bv`), with 348 numeric assets.

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
is a fade duration (`stopMusic`, `00042d70`), not a track selector. The current
desktop stops immediately, as in the existing SHS audio approximation.

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
Music. Native `SHSUIMenu::handleMenuSelection` (`000395ac`) also uses 8005 for
ordinary modes 1/3; scored-choice mode 2 selects distinct feedback. This menu
binding does not establish those story-choice or relationship sound rules.

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

Complete episode routes, all CoD service variants, exact iOS animation/font
parity and CoD story-choice/relationship feedback sounds still require verification.
Unknown services stop explicitly; no score, choice, random result or next scene
is invented to continue an unsupported episode.

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
