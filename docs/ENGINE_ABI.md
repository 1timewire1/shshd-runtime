# SHS engine service ABI and dispatcher inventory

Revision: 2026-11-17. Companion to [VM_SPEC.md](VM_SPEC.md) and [SCHEMA.md](SCHEMA.md). The core VM is specified separately because a numeric yield is a call into a game engine, not a display opcode.

This document inventories **every explicit service ID 0–100** in Android 1.0.9 `FUN_0009fe3c`. It includes verified state contracts and unresolved helper calls. Rows marked unresolved are research boundaries, not implemented semantics. Android default cases must not automatically be assumed to have the same meaning in an iOS build.

The launcher selects the game's host profile from its validated
library. SHS-specific handlers live in `exp_runtime/shs/services.py`;
[COD.md](COD.md) records CoD's separate handlers and native evidence. Both games
support service 15's named dialogue; Android-profile SHS also implements its
verified optional negative prefix, while SHS HD's own case 0xf reads its first two
words as CoD does. Their native service-100 paths differ; here both complete with 0
and keep a URL argument for the host (section 2).

## 1. Shared calling convention and notation

See [VM yield ABI](VM_SPEC.md#7-yield--host-call-abi) for the complete transition rules. The argument frame is `S[SP-count:SP]`; `a1` is its first word. Arguments are signed 16-bit unless the handler explicitly narrows or interprets their bits differently. Completion removes the entire frame and puts a word in R; the script uses opcode `0x21` to push it. Pending input retains the frame and the already-advanced PC.

- `t(n)` means raw string reference resolution through `FUN_0009f420`.
- `T(n)` means string resolution **plus substitutions** through `FUN_0009f9fc`.
- `bool(a)` is `a != 0`; a byte argument may instead truncate a word.
- “Arguments read” describes accesses visible in the inspected implementation. It is not an assertion that the native reader checks exact arity or accepts every larger frame.
- **C**: current Python host completes this operation, with any stated limitation.
- **P**: Python exposes a recognized pending event; the desktop/session implements the supported input callback or terminal application handoff.
- **X**: Python leaves the service as `unhandled_yield`, even when a native effect is partly known.

A return of 0 from the C dispatcher does not by itself mean successful completion: pending operations also return 0 to their caller. The pending flags and VM status distinguish those cases. The internal sentinel `0x80000000` is not a script return value.

Services 7/63 terminate the scene and reset its VMs. Their zero dispatcher
result has no surviving script caller. The runtime retains their final frame
for terminal-checkpoint validation; it never resumes or consumes that frame
as an ordinary input callback.

## 2. Complete dispatcher inventory

All rows derive from `native-yield-dispatcher.c`. Additional evidence is in `native-ui-factory.c`, `native-runtime-helpers.c`, `native-engine-spec-helpers.c`, and `native-playback-helpers.c`. Native addresses are for the binary identified in the EXP spec. C/P describe the implemented subset, not exact reproduction of every native panel or application side effect; see the limits in [RUNTIME.md](RUNTIME.md).

| ID decimal (hex) | Arguments read | Native behavior / evidence | Completion | Python |
| --- | --- | --- | --- | --- |
| 0 (`00`) | a1 format, or negative selector a1 followed by format a2; values… | Formats raw `%c/%d/%s` through scratch slot 10, then stores slot 0 or `1-a1`. See [story services](STORY_SERVICES.md). | dynamic handle | C |
| 1 (`01`) | a1..a8; T(1), T(2), optional T(3) | Pipe-delimited choices; title, description, millisecond timer, timeout selection, character and portrait mode. See section 4.6. | zero-based selection | P |
| 2 (`02`) | T(1), T(2), a3..a6 | Begins incremental choice: title, description, timer, timeout selection, character, portrait mode; `FUN_000ae740`. | 0 | C |
| 3 (`03`) | T(1), a2, bool(a3) | Adds an option, mapped return value (-999 selects its index), and enabled flag; `FUN_000ae6c8`. | 0 | C |
| 4 (`04`) | bool(a1) | Attaches incremental choices, clears the builder pointer, and waits. Nonzero a1 shuffles labels and return mappings using the shared native LCG; see section 4.6. | mapped selection | P |
| 5 (`05`) | a1, low byte of a2 | Writes a byte at game-state offset a1 via `FUN_00095d48`; service 13 reads these bytes as character expression defaults. | 0 | C (expression byte) |
| 6 (`06`) | a1, a2 destination | Gets the named character string via `FUN_00096c64`; writes to VM address a2 or, for negative a2, dynamic slot `~a2`. | address / handle | C (SHS: entity name; CoD stops) |
| 7 (`07`) | none read; all supplied words ignored | Ends the episode through `0007e614`: dispose panels, reset hosts/numeric state, cancel scheduled scripts and retire native resume progress. [Contract](STORY_SERVICES.md#episode-exit-services-7-and-63). | terminal scene exit | P (terminal) |
| 8 (`08`) | a1 title ref, T(2), a3, a4 | Episode/week title card, UI type 16; negative a1 means empty title, a3 is the background asset, a4 a retained flag. Original fonts, layout, entrance and input gate; Android promotional branches remain unmodeled. See [TITLE_SCREENS.md](TITLE_SCREENS.md). | 0 on acknowledgement | P |
| 9 (`09`) | poll ID, upload type (0 text, 1 number, 2 array), upload value or array address, upload count, results type, results buffer address, results count (HD `getPollURL` 0003c984 appends words 0-4 and 6 to the URL as pollID, upType, upValue(s), upSize, resultsType, resultsSize; `finishPollDownload` writes the results through word 5) | Android: `0009f0cc` builds then discards the poll parameters, returns `EMPTY`; sender `0007b448` is empty in Android 1.0.9. HD: poll download (`getPollURL`, `pollID=&upType=&upValue(s)=`), the "Loading / Please wait..." bar, waits for the request; on failure `finishPollDownload(false)` returns 0. Type 2 with a verified script continuation completes offline with a local receipt ([contract](STORY_SERVICES.md#offline-surveys-service-9), `survey_confirmation`); any other call shows the bar for `POLL_WAIT_MS` (1 s) and returns 0 (`download_poll`). | native waits; offline R=0 | P (offline) |
| 10 (`0a`) | a1, bool(a2) | Schedules script resource a1 and its flag through `FUN_0007b44c`; LIFO consumption after HALT. | 0 | C |
| 11 (`0b`) | a1, a2 | Sets panel background base a2, variant a1 through `FUN_000a92f4`, then requests speaker-side alignment. | 0 | C (background and pan) |
| 12 (`0c`) | none required by case | Explicit native default/no-op path; ordinary completion still removes the supplied argument frame. | 0 | C (SHS: native default; CoD stops) |
| 13 (`0d`) | optional negative mode, text, character, optional override | Dialogue path; raw text reference is subsequently substituted by the panel. Section 4 describes argument positions. | pending | P |
| 14 (`0e`) | none required by case; supplied words ignored | Explicit native default path, verified in Android and SHS iOS; ordinary completion removes the supplied frame without changing panel/game state. | 0 | C |
| 15 (`0f`) | optional negative prefix, then T(speaker), T(body); extra words ignored | Named dialogue in panel mode 3; prefix is skipped without applying service-13 text styling. Shares presentation and callback with 76. [Contract](STORY_SERVICES.md#shs-service-15). | 0 on acknowledgement | P |
| 16 (`10`) | a1 | Queues a screen-transition selector at scene `+0x1c1c`. Title, message and dialogue panels (8/13/33/65/76) consume it on final acknowledgement; selector 20 draws a libc random bit for transition 1/2. Other panel paths remain partial. | 0 | C (queue; callbacks partial) |
| 17 (`11`) | T(1), T(2), T(3) | Text input: title, prompt, initial value; UI factory type 15, same as 40. | string handle 0x7ff5 | P |
| 18 (`12`) | none required by case | Explicit native default/no-op path; ordinary completion still removes the supplied argument frame. | 0 | C (zero args) |
| 19 (`13`) | none required by case | Explicit native default/no-op path; ordinary completion still removes the supplied argument frame. | 0 | C (SHS: native default; CoD stops) |
| 20 (`14`) | none required by case | Explicit native default/no-op path; ordinary completion still removes the supplied argument frame. | 0 | C (SHS: native default; CoD stops) |
| 21 (`15`) | none required by case; supplied words ignored | Same verified Android/SHS iOS default completion as 14; no panel, score or random effect. | 0 | C |
| 22 (`16`) | destination a1, format t(2), values... | Formats `%d` / `%s` into packed VM memory via `FUN_0009f838`; destination capacity is caller-managed. | 0 | C (SHS: `my_sprintf`; CoD stops) |
| 23 (`17`) | none required by case | Explicit native default/no-op path; ordinary completion still removes the supplied argument frame. | 0 | C (SHS: native default; CoD stops) |
| 24 (`18`) | t(1), t(2) | String equality through `FUN_0009f56c` / `FUN_0005edd8`. | 0 / 1 | C |
| 25 (`19`) | t(1), t(2) | Copies both strings, concatenates and writes packed words back to a1; dynamic-slot destinations are invalid. `FUN_0009f4d8`. | 0 | C |
| 26 (`1a`) | t(1) | Calls `atoi` helper `FUN_0009f498`; dispatcher pseudocode discards its result and takes void completion. Do not assume the parsed integer is returned. | 0 shown; inspect before port | C (SHS: no-op; CoD stops) |
| 27 (`1b`) | a1 bound | Positive bound: absolute remainder from the shared native LCG stream. Otherwise 0 without consuming randomness. `FUN_0009ea28`. | integer | C |
| 28 (`1c`) | destination a1 | Copies last input into packed VM memory, high byte first, including NUL and zero padding. `FUN_00056b78`. | 0 | C |
| 29 (`1d`) | a1 index | Reads signed word at host `+0x60 + 2*a1`; choice callbacks write cell 0. Other cell meanings remain unresolved. | word | C (initialized cells only) |
| 30 (`1e`) | a1 | Calls application virtual slot `+0x1e8`; effect unresolved. | 0 | C (SHS: sound effect; CoD stops) |
| 31 (`1f`) | none required by case | Explicit native default/no-op path; ordinary completion still removes the supplied argument frame. | 0 | C (SHS: native default; CoD stops) |
| 32 (`20`) | none required by case | Explicit native default/no-op path; ordinary completion still removes the supplied argument frame. | 0 | C (SHS: `addMaster`; CoD stops) |
| 33 (`21`) | t(1) title, t(2) body, a3 retained | Raw-text message panel, UI type 2. Requires 1000 ms active reading time, then acknowledgement; a3 does not set the initial delay. See [STORY_SERVICES.md](STORY_SERVICES.md#message-panel-service-33). | 0 on acknowledgement | P |
| 34 (`22`) | a1, a2 | If panel type 3 is absent, creates it and sets background `(a2,a1)`; otherwise default completion. | 0 | C (background/pan; lifecycle partial) |
| 35 (`23`) | a1..a4 | If panel 3 exists, character/expression update `(a1,a4)` via `FUN_000ab048`, then background `(a3,a2)`. | 0 | C (background/pan; other side effects partial) |
| 36 (`24`) | t(1) | Sets a panel text field through `FUN_000aa028`. | 0 | C (SHS: dialogue title; CoD stops) |
| 37 (`25`) | t(1) | Sets dialogue text through `FUN_000a9f84`, starts display, and waits. | pending | P (SHS: dialogue text, waits; CoD stops) |
| 38 (`26`) | a1, a2 | Panel operation `FUN_000a927c(panel3,a1,a2,0,-1,-1,-1,-1)`; semantics partial. | 0 | C (SHS: status icons; CoD stops) |
| 39 (`27`) | none read; supplied arguments ignored | Closes dialogue panel 3 through `FUN_000a7cd0`, setting its removal flag at +0x0c. Completes without a UI callback. See [STORY_SERVICES.md](STORY_SERVICES.md#dialogue-panel-close-service-39). | 0 | C |
| 40 (`28`) | T(1), T(2), T(3) | Text input, same as 17. | string handle 0x7ff5 | P |
| 41 (`29`) | none required by case | Explicit native default/no-op path; ordinary completion still removes the supplied argument frame. | 0 | C (SHS: native default; CoD stops) |
| 42 (`2a`) | none required by case | Explicit native default/no-op path; ordinary completion still removes the supplied argument frame. | 0 | C (SHS: native default; CoD stops) |
| 43 (`2b`) | t(1) | Stores a replacement string under the fixed key at `0x0025b268`; the key is `$USR` (HD `setNameReplacement`). | 0 | C (SHS: sets `$USR`; CoD stops) |
| 44 (`2c`) | key, value | Global numeric write; alias of 54. | 0 | C |
| 45 (`2d`) | key | Global numeric read, missing value 0; alias of 55. | word | C |
| 46 (`2e`) | t(key), t(value) | Stores a raw text substitution through `FUN_00097644`. | 0 | C |
| 47 (`2f`) | t(key), t(default), negative slot selector | Reads stored string or initializes default, copies into dynamic slot, returns its handle. Native also invokes a persistence helper on default initialization. | handle | C |
| 48 (`30`) | none required by case | Explicit native default/no-op path; ordinary completion still removes the supplied argument frame. | 0 | C (SHS: native default; CoD stops) |
| 49 (`31`) | character, t(name), case flag | Assigns character name; optional native byte-case conversion. See section 3. | 0 | C |
| 50 (`32`) | owner a1, key a2, bit a3, value a4 | Set a bit only when a4==1; otherwise clear it. Uses the shared 32-bit numeric map. `FUN_000965bc`. | 0 | C |
| 51 (`33`) | owner a1, key a2, bit a3 | Returns a bit from the shared 32-bit numeric map; missing entries read zero. `FUN_00095ca0`. | 0 / 1 | C |
| 52 (`34`) | owner, key, value | Numeric write through `FUN_00096474`. | 0 | C |
| 53 (`35`) | owner, key | Numeric read through `FUN_00095bdc`, missing value 0. | word | C |
| 54 (`36`) | key, value | Global numeric write, owner 0; alias of 44. | 0 | C |
| 55 (`37`) | key | Global numeric read, owner 0; alias of 45. | word | C |
| 56 (`38`) | a1..a3 | Calls `FUN_0009783c`; state collection meaning unresolved. | 0 | C (SHS: per-entity int array; CoD stops) |
| 57 (`39`) | a1..a3 | Calls `FUN_00096fd0`; narrows result to signed word. | word | C (SHS: per-entity int array; CoD stops) |
| 58 (`3a`) | a1, a2 | Calls `FUN_00096fbc`; state query unresolved. | word | C (SHS: per-entity int array; CoD stops) |
| 59 (`3b`) | a1..a3 | Calls `FUN_00096f9c`; state mutation unresolved. | 0 | C (SHS: per-entity int array; CoD stops) |
| 60 (`3c`) | t(1) | Name/string lookup through `FUN_000966bc`; domain and missing-value behavior unresolved. | word | C (SHS: index of a registered name, or -1; CoD stops) |
| 61 (`3d`) | character a1, destination a2 | Copies character name from `FUN_00096c64` to packed VM word memory. | 0 | C (SHS: entity name; CoD stops) |
| 62 (`3e`) | none required by case | Explicit native default/no-op path; ordinary completion still removes the supplied argument frame. | 0 | C (SHS: native default; CoD stops) |
| 63 (`3f`) | none read; all supplied words ignored | Same episode-exit path as 7, including scene teardown and resume retirement. | terminal scene exit | P (terminal) |
| 64 (`40`) | character, t(name) | Assigns raw character name via `FUN_00096144`, without service 49 case conversion. | 0 | C |
| 65 (`41`) | character a1, t(2), override a3 | Updates panel character/expression and dialogue, then waits. Has Android promotional-text special cases and an early-return path. | pending / special early return | P (ordinary dialogue path) |
| 66 (`42`) | all arguments as weights | Weighted random selection: sum weights, PRNG remainder, return first index whose cumulative sum exceeds the remainder; invalid weights not specified. | zero-based index | C (SHS; a total of 0 or less returns the last index; CoD stops) |
| 67 (`43`) | none required by case | Explicit native default/no-op path; ordinary completion still removes the supplied argument frame. | 0 | C (SHS: native default; CoD stops) |
| 68 (`44`) | none required by case | Explicit native default/no-op path; ordinary completion still removes the supplied argument frame. | 0 | C (SHS: native default; CoD stops) |
| 69 (`45`) | none required by case | Explicit native default/no-op path; ordinary completion still removes the supplied argument frame. | 0 | C (SHS: native default; CoD stops) |
| 70 (`46`) | a1 selector; extra words ignored | Android build query: 2→2, 3→6, 6→0x7ff5, 9→1; remaining selectors return 0 except 11, which compares native current/weekly-episode objects and stays unsupported on Android-profile SHS. HD answers 10→2 and 11→0 (6 its app version), CoD 10→1 and 11→0; shshd-runtime's selectors 200–205 are in section 5. [Contract](STORY_SERVICES.md#build-and-application-query-service-70). | word | C (fixed selectors; HD, CoD 11); X (Android 11) |
| 71 (`47`) | 8 words: title, description, good/bad lists, duration ms, character, portrait mode, refresh ms | Timed word choices; raw text, libc random deals, ±1 scoring clamped at zero. See [mini-game schema](MINIGAMES.md#3-service-71-timed-word-choices). | score in R and UI cell 0 | P |
| 72 (`48`) | character, art base ID | Initializes five character-art slots, probes IDs base+1..base+4 and falls back to base when absent. | 0 | C (resource probes in Session) |
| 73 (`49`) | a1 character | Returns first art word at game state `+0xb1c + 10*a1` via `FUN_00095c48`. | word | C |
| 74 (`4a`) | a1 | Stores numeric UI default `DAT_002af012` via `FUN_000a7d14`; not a fade opcode. | 0 | C |
| 75 (`4b`) | a1 | Stores numeric UI default `DAT_002af010` via `FUN_000a7cf8`; not a fade opcode. | 0 | C |
| 76 (`4c`) | T(1) speaker, T(2) dialogue; extra words ignored | Named dialogue in panel mode 3, no portrait, theme -1. Uses ordinary name layout, text reveal, paging and final callback. See [STORY_SERVICES.md](STORY_SERVICES.md#named-dialogue-without-a-portrait-service-76). | 0 on final acknowledgement | P |
| 77 (`4d`) | none required by case | Explicit native default/no-op path; ordinary completion still removes the supplied argument frame. | 0 | C (SHS: native default; CoD stops) |
| 78 (`4e`) | T(1), count a2, word-address a3 | Portrait selector copies 1–5 IDs (a translated pack's layout up to 10); separate confirmation returns the chosen original array index. See section 4.3. | index in R and UI cell 0 | P |
| 79 (`4f`) | a1 resource | Selects music request for 8201–8232, otherwise SFX path; native playback through `FUN_000a3bc8`. | 0 | C (basic audio) |
| 80 (`50`) | a1 resource, bool(a2) | Stores music resource and flag through `FUN_0007b550`; repeat/fade flag meaning unresolved. | 0 | C (basic audio; flag retained) |
| 81 (`51`) | a1 | Calls audio stop helper `FUN_000a3260(audio,a1,1)`; Python stops requested music, with simplified channel handling. | 0 | C |
| 82 (`52`) | none | Optional 1000 ms Android vibration via `FUN_000a3040`; iPhone uses the iOS system vibration alert. Here General's Vibration drives the device's vibrator (Android, iPhone, a desktop controller's rumble), and Sound's Simulated Vibration Sound plays a synthesized buzz on any host (both opt-in; unsaved `vibration_serial`). Music/SFX unchanged. [Device contract](STORY_SERVICES.md#optional-device-request-and-native-stub-services-82-99). | 0 | C (device vibrator; optional simulated buzz) |
| 83 (`53`) | none read here | Audio helper `FUN_000a3208`; detailed effect unresolved. | 0 | C (SHS: pause music; CoD stops) |
| 84 (`54`) | none read here | Audio helper `FUN_000a31bc`; detailed effect unresolved. | 0 | C (SHS: resume music; CoD stops) |
| 85 (`55`) | none read here | Scene helper `FUN_0007b494`; effect unresolved. | 0 | C (SHS: no-op; CoD stops) |
| 86 (`56`) | a1, a2, a3 flag | If a3==0, invokes `FUN_0007b488`, then background helper `FUN_000a92f4(panel,a1,a2)`. | 0 | C (background/pan; flag effect unresolved) |
| 87 (`57`) | none read here | Reads scene field `+0x264` and narrows to a word; meaning unresolved. | word | C (SHS: 0; CoD stops) |
| 88 (`58`) | T(1) | Queues substituted notification in panel-3 `+0xf0`; next dialogue consumes it. Original notice font, portrait-relative letter motion, length-based fade and tap dismissal; see [notification contract](STORY_SERVICES.md#dialogue-notifications-service-88). | 0 | C |
| 89 (`59`) | none | Sets a one-shot flag for the next dialogue. Shared presentation uses the recovered iOS hold/scale/rotation and +400 ms reveal delay; older saves retain the Android rotation. [Timing](UI_FIDELITY.md#shake-and-reveal-input). | 0 | C |
| 90 (`5a`) | icon a1, optional T(2) when a2!=-1 | Nonblocking scene badge: -1 removes it; otherwise icon/text, layout 67 and 200 ms entrance. `FUN_0007b97c`. | 0 | C |
| 91 (`5b`) | bool(stack[SP-argc]), even when argc=0 | Loading overlay gates VM execution until active time >3000 ms. A zero wait value completes the supplied frame immediately; nonzero retains it until `FUN_0009ea70` clears the overlay. Zero-argument calls read retained backing at SP. [Contract](STORY_SERVICES.md#loading-overlay-service-91). | R=0; UI cells unchanged | P |
| 92 (`5c`) | none required by case | Explicit native default/no-op path; ordinary completion still removes the supplied argument frame. | 0 | C (SHS: native default; CoD stops) |
| 93 (`5d`) | none required by case | Explicit native default/no-op path; ordinary completion still removes the supplied argument frame. | 0 | C (SHS: native default; CoD stops) |
| 94 (`5e`) | 22 words; six weighted play tables and six instruction references | Football: nine changing targets, drives, halves and sudden death. [Frame and rules](MINIGAMES.md#4-service-94-football); [presentation](FOOTBALL_UI.md). | home minus away; saves both scores | P |
| 95 (`5f`) | a1 selector | Last football home score if a1==1, otherwise away score; scene `+0x1c0c/+0x1c10`. Python rejects uninitialized score reads. | word | C |
| 96 (`60`) | 20 words; ten-word problems, seventeen-word tutorials, two-word symbols | Word/picture grids, timers, tutorial branches, path scoring. [Frame and rules](MINIGAMES.md#5-service-96-word-and-picture-grids). | score >= target as 0/1; UI cells unchanged | P |
| 97 (`61`) | bool(a1), a2; extra words ignored | `FUN_0007b8d4` stores automatic/fixed background-pan policy and immediately requests alignment a2 (1=left, 2=center, 3=right; other values hold position). [Contract](UI_FIDELITY.md#background-panning). | 0 | C |
| 98 (`62`) | none read here | `FUN_000843c8` clears the application loading overlay, resets its timer and restores input. HD dismisses a non-blocking loading screen. | 0 | C (SHS: `hideLoadingBar`; CoD stops) |
| 99 (`63`) | bool(a1) | `FUN_00082adc` is exactly `mov r0,#0; bx lr` in this release; ordinary completion, no host +0x118 flag. | 0 | C |
| 100 (`64`) | t(1), bool(a2) | Optionally sets scene `+0x1b`, invokes application helper, then passes text to `FUN_000db5e0`; SHS HD and CoD 1.4.7 save and open the URL. Here it completes with 0 and a `://` link is kept for the host to offer behind Exit Game. | 0 | C (SHS and CoD: 0, link kept) |

shshd-runtime completes the rows marked "SHS" with the HD build's `SHSScript::syscall` behaviour (`engine.SHS_HD_YIELDS`), for both SHS editions; Cause of Death still stops at them.

IDs beyond 100 take the inspected Android dispatcher's default path. The HD build's 101-120 are in section 6 and shshd-runtime's own 200-225 in sections 5.1-5.6b; any other unknown ID stays an explicit stop. The Python host intentionally does not treat unknown IDs as successful no-ops.

### Imported SHS corpus follow-up

The supplied 271 external SHS EXPs contain 974 scripts and 55 distinct service
numbers. The previously unhandled numbers found in these scripts were 14, 15,
21 and 100. Service 15 has 396 calls across 62 episodes; 14 has 14 calls in the
two Prince Plot episodes; 21 has four calls in four episodes. The runtime now
implements those three contracts. This inventory is a static call-site scan,
not proof of every branch, argument variant or minigame mode being supported.

Ghidra MCP confirms Android jump entries `0009fedc` (14) and `0009fef8` (21)
both target `000a00f8`, then the return-zero/frame-pop tail at `000a0058`.
SHS iOS entries `0006de74` and `0006de90` both hold relative offset `0x3c80`
from table base `0006de3c`, targeting `00071abc`; `00071ad4` narrows its default
sentinel to R=0 and removes the frame. Neither default implements the dialogue
or diagnostic operation that its caller's arguments might suggest. Only these
explicitly verified SHS IDs were enabled; unknown IDs still retain their frames.

SHS service 100 has 23 calls across 15 supplied episodes. shshd-runtime now
completes it with 0 for SHS and CoD alike; a URL argument is kept for the host to
offer behind Exit Game (`engine.store_link`). The save, the scene flag `+0x1f` and
leaving the app are not modelled. The native evidence follows.
It is not CoD 1.3.4's default path: SHS reads a URL and flag, sets a scene flag
when requested, and saves state before platform handoff. SHS iOS names the
helpers `saveGame` and `exitAndShowURL`; Android calls `0008b618` and `000db5e0`.
Its external-application lifecycle and resume flag are not modelled.
The follow-up trace confirms iOS **000061ac** uses `UIApplication.openURL:`
and returns. Scene flag `+0x1f` is tested by **00022440/00022a28** when ticking
and deciding whether queued scripts can continue. This is more than a URL
string or a return-zero stub. The bounded choice-tree audit encounters it in
Game of Cones and Conned Artist promotional branches; it completes there without
opening a URL or changing the live save.

## 3. Verified state-service contracts

These contracts define the subset implemented in [engine.py](../packages/engine/src/exp_runtime/engine.py). The implementation checks exact argument counts for these fixed forms. Persistence, rendering, and other noted native side effects are separate from its in-memory state model.

### 3.1 Numeric variables

```text
set_global(key, value)       : services 44, 54; 2 arguments; returns 0
get_global(key)              : services 45, 55; 1 argument; returns stored word or 0
set_owned(owner, key, value) : service 52; 3 arguments; returns 0
get_owned(owner, key)        : service 53; 2 arguments; returns stored word or 0

map_key = (s16(owner) * 65536 + s16(key)) & 0xffffffff
```

Global operations use owner 0. This is signed arithmetic followed by 32-bit wrapping, **not** concatenating two unsigned halves. For owner 1, key -1, the map key is 65535, not 131071. Ordinary setters sign-extend their 16-bit argument into the native 32-bit map. Services 50/51 also access its high bits; ordinary VM getters narrow to 16 bits. Evidence: `FUN_00096474` and `FUN_00095bdc`.

### 3.2 Stored strings and dynamic slots

```text
service 46: (key_ref, value_ref) -> 0
    strings[t(key_ref)] = t(value_ref)

service 47: (key_ref, default_ref, selector) -> handle
    key = t(key_ref)
    value = strings.get(key, "")
    if value is empty:
        value = t(default_ref)
        strings[key] = value
    slot = ~s16(selector)                 # -1 -> 0, ..., -11 -> 10
    dynamic_strings[slot] = value
    return 0x7ff5 + slot
```

These are raw references; substitution is not implicitly applied to key/value arguments. An existing empty value invokes the default just like a missing value. Native default initialization also calls `FUN_0008b2a8`; the Python host doesn't call it, but keeps the shared names table across episodes in `player.json` (section 6, `Session.share_names`).

Runtime handles are mutable references to slots, not immutable strings or inverted indices into a static string list. Services can overwrite the slot before a later use. The slot selector in this contract must not be generalized to service 0's distinct formatting convention.

### 3.3 Characters

Service 64 `(character_id, name_ref)` stores `t(name_ref)`. Service 49 adds a third case-conversion flag. With that flag set, its native byte conversion preserves names beginning with `$`; otherwise it changes case at literal spaces using ASCII and specific extended-byte ranges. The current `_format_name()` models those ranges. This is not Unicode title-casing.

Service 72 `(character_id, base_id)` records five art slots natively. For positive bases it stores the base in slot 0 and probes base+1 through base+4; each missing variant falls back to the base. Nonpositive bases are copied across the five slots. Variant numbers are not yet assigned verified expression names. Session supplies resource-bank probes; standalone tracing without a resource bank records base fallbacks. Service 73 returns the stored first art word, or 0 for a character never given art (the native table is zero-filled).

Service 5 stores a signed low byte at the game-state offset given by a1. Service 13 reads that character byte as its default expression. Native helper `FUN_00095c60` selects art slot `expression % 5`. Panel helper `FUN_000ab048` also uses separate bytes at character+200, prior panel state, and relationship properties. NPC relationship icons, cache writes to owned keys 3000/3001, gain/loss sounds, and their animation delays are implemented; see [UI_FIDELITY.md](UI_FIDELITY.md#npc-relationship-indicators). Other expression and panel-lifecycle exceptions remain partial.

The separate last-expression bytes now live in `engine.dialogue_history`.
New speakers enter neutral; retained speakers use that cache. At one second
the native iOS tick requests the target expression and updates the cached
signed byte, independently of service 5's table. Two delayed opacity tracks
then crossfade the art. Choices retain this speaker state. Loading a scheduled
scene clears both 200-byte expression tables, as SHS `loadScript09NoGUI`
**00020ab0** and CoD **00011f2c** do; ordinary name/art bindings remain intact.
See [the lifecycle contract](UI_FIDELITY.md#delayed-expressions-and-panel-reuse).

### 3.4 Scheduling, defaults, and audio

Service 10 `(script_id, flag)` appends a schedule record; records are consumed in LIFO order after the running VM halts. It returns 0 immediately. The flag's native panel effect is not rendered.

Services 74 and 75 each accept one word and store separate numeric UI defaults. Native consumers can use -2 as a sentinel selecting a stored default; for example the panel setup in service 1 reads `DAT_002af012`. These services are not fade-in/fade-out actions.

Service 79 selects a music request for IDs 8201–8232 in SHS (8201–8209 in CoD)
and otherwise a sound-effect request. It requests one music playthrough.
Service 80 stores a music ID and `bool(a2)` repeat flag. Both native iOS games'
`SHSSound::setLoop:` translate this flag to AVAudioPlayer loop counts -1 / 0
(CoD `00041e88`, SHS `00073fa8`). Desktop and native iOS playback now use the
same convention, with the existing flag retained in saves. Service 81 accepts
one word and calls the native stop/fade path, `stopMusic(word, true)`, in both
iOS games (SHS HD case 0x51, CoD `00042d70`). The runtime fades over that word
(see [COD.md](COD.md) and "Music" below). Changing a live track's repeat flag
without restarting it, all channel semantics and intermediate same-frame
requests remain partial.

#### Android music cues

Native `FUN_000a3778` constructs `Assets/audio/music/<id>.mp3` for IDs
8201–8232. JNI bridge `FUN_000dc938` then calls
`com.eamobile.shs_na_wf.SHS09SoundEngine.playMusic(String)` in `classes.dex`.
That Java method redirects **eleven** filenames and seeks to a millisecond
offset before starting playback. These IDs are alternate cues within existing
tracks, not missing standalone audio or approximate nearest-ID fallbacks.

| Requested music ID | APK MP3 ID | Start offset, milliseconds |
| --- | --- | --- |
| 8202 | 8201 | 2800 |
| 8204 | 8203 | 720 |
| 8206 | 8205 | 28280 |
| 8208 | 8207 | 3270 |
| 8211 | 8210 | 6000 |
| 8213 | 8212 | 4000 |
| 8214 | 8212 | 39200 |
| 8216 | 8215 | 1320 |
| 8218 | 8217 | 1920 |
| 8220 | 8219 | 10600 |
| 8225 | 8224 | 29200 |

The Java path stops/releases the previous player, applies the first matching
filename rule, prepares a new player, calls `seekTo(offset)` for nonzero
offsets, sets music volume, then starts it. It does not set looping in this
method; the shared player's repeat behavior follows the recovered iOS
contract. All other filenames start at zero. ID 8222 has neither a file nor a
redirect in the inspected APK; its missing-resource diagnostic remains valid.
No replacement is inferred for it.

`audio.music_cue()` reproduces this mapping at playback only. Engine state,
saved `music_id`, and exact content lookup keep the original requested ID;
the renderer reads the mapped source and passes seconds to SDL_mixer's
`music.play(start=...)`. Different cues sharing a source still restart at
their distinct offsets. SFX and episode resource IDs are not remapped.
Existing libraries work without reimport because the complete source APK was
retained. Saves keep the requested cue and repeat flag; the playback fields
(this fork's save version 27, upstream's 22) stay empty in this player (see
Music below), so a loaded save starts its requested cue.
Android's exact codec seek precision remains unverified.

#### Music

The story's music follows `SHSSoundManager` as both iOS games build it
(`music_stream.py`; SHS HD addresses, CoD 1.4.7's the same code):

- **Requests.** `playMusic` (`00053830`) ignores a request while Music is
  off; it is not queued. Asking again for the playing cue cancels its fade.
  Another cue fades the playing one over 1000 ms (`stopMusic(-1)`), then
  starts once the fade has ended (`tick`, `000536d8`).
- **Stops.** `stopMusic(fade, true)` (`00053424`): 0 stops at once, `0xffff`
  is 1000 ms, any other value is that many ms, and the queued cue is dropped.
  A cue already fading keeps its fade. Fades are linear (`getFadeLevel`).
- **Music switch.** Off is `stopMusic(-1, true)`, a 1000 ms fade. On plays
  nothing in an episode until the script asks for music again.
- **Pause menu.** Opening it saves the playing cue and its position
  (`storeGameAudio` `0001e6e0`, `-[SHSSound save:]` keeps `currentTime`), then
  fades it over 1000 ms. A cue already fading finishes first and is not saved.
  - Resume waits for that fade, then plays the saved cue again from the saved
    position at full volume (`restoreGameAudio` `0001e688`, `restartFromLoad`).
    If Music is off by then, the cue is dropped.
  - A looping cue's position wraps at its file's length (`audio.mp3_length_ms`).
- **Desktop holds.** Window inactivity and service 83 (`pauseMusic`) pause the
  stream at once; both holds must clear before playback resumes.
- **Main menu.** Returning to it from the pause menu leaves the episode's cue
  held, and resuming the same live session restores it. New sessions and
  explicit save loads start their requested cue.
- **Music switched on in the pause menu** sets `SHSEngine` +0xb22c, which
  `doSoundManagerTransition` turns into the menu's song (`MENU_MUSIC`, once)
  as soon as the episode's music is held (confirmed on the iPad).
  - Switching Music off again fades it over 1000 ms.
  - Resume fades it over 1000 ms, and the episode's song is restored only
    after it has stopped (`restoreGameAudio` waits for silence).
  - **Adaptation (owner's choice):** natively, the Main Menu row then fades it
    out and leaves the main menu silent. Here the main menu keeps it playing
    (`Desktop.take_pause_song`).
- **Not applied:** the pause menu's effects fade (0.1 s) and their restore on
  Resume.

The engine keeps the request count and the stop's fade time as exp-runtime's
saved `music_serial` and `music_stop_ms` (save version 27); the player reads
them as requests and keeps the playing stream itself.

exp-runtime v0.6.0 has its own desktop audio (CoD fades, a store/restore handoff and saved
playheads in `music_playback` / `sound_playback`, save version 27 here). Those fields are kept in
saves, but this player does not fill them: its music is the model above.

Evidence: `SHS09SoundEngine.java` debug lines 145–253, inspected as Dalvik
instructions in the player-supplied APK. The DEX hash is recorded in
[PROVENANCE.md](PROVENANCE.md). Authored tests check both music services,
source bytes and seek offsets, request preservation, switching between cues,
mute/re-enable, unmapped missing resources, pause/focus combinations and live
menu resume. An authored WAV checks that the real mixer holds its position
while paused and continues without reloading. Optional player-content tests
decode and start all eleven cues with the desktop mixer.

`FUN_000a92f4(panel, base, variant)` leaves the background node unchanged for base -2, hides it for -1, and otherwise uses base+variant for variants 1/2 when that asset exists, falling back to base. Services 11/34 pass `(a2,a1)`, 35 passes `(a3,a2)`, and 86 passes `(a1,a2)`. A replacement node starts centered; the helper then requests speaker-side alignment, as does dialogue presentation. Service 97 supplies automatic/fixed policy. The shared renderer implements the 250 ms move and saves its clock; see [background panning](UI_FIDELITY.md#background-panning). Native panel existence checks, transitions, and flag-dependent side effects are only partially modeled.

## 4. Presentation and remaining structured arguments

### 4.1 Service 8: title presentation

The frame is `(title_ref, subtitle_ref, asset_id, flag)`. UI factory
`FUN_0009fa3c` type `0x10` calls `FUN_000a7758` with substituted title/subtitle
and the two numeric fields, attaches the panel, and waits. Every negative
title reference produces an empty title without reading VM memory.

Episode introductions and Football Star's week cards use this same screen.
`FUN_000a70b4` loads PNG/glyph-font pairs 528/529 and 530/531, uses layout 48,
and animates the background, title wipe and subtitle. An early tap finishes
the wipe; a later accepted tap returns zero without writing a result cell.
The shared transition completion can consume one `lrand48` draw when service
16 has queued selector 20. The model, input gates, callback and version-11
save schema are in [TITLE_SCREENS.md](TITLE_SCREENS.md).

Negative title references and the first-week title also trigger Android
promotional branches. Those overlays, shared menu-background variant effects
and transition visuals are not reproduced by the local title screen.

For the bundled `The_New_Girl.exp`, the verified first presentation in scene 25002 is:

```text
issuing PC: 164       encoded byte offset: 9719
next VM PC: 165       SP: 12       FP: 7
arguments: (42, 49, 1057, 0)
title: The New Girl
subtitle: So it begins...
```

This follows 2,561 executed instructions and one LIFO scene load, not a backward scan of nearby pushes. See `new-girl-start-trace.json`.

### 4.2 Services 13 and 65: dialogue

Service 76 uses the same dialogue panel with an explicit speaker string,
mode 3 and no portrait. It bypasses NPC name/art lookup while retaining the
ordinary reveal, pagination and callback. See its
[frame and state contract](STORY_SERVICES.md#named-dialogue-without-a-portrait-service-76).

Service 13's normal argument prefix is `(text_ref, character_id)`. If its first word is negative, the prefix becomes `(mode, text_ref, character_id)`; recognized special modes are -2 and -3, and other negative mode values are normalized in the native path. An optional following word overrides the character's stored expression when it is not -1. The native code resolves raw text, applies mode-specific decorations, looks up character state, sets the panel, and waits.

The -2 prefix surrounds raw text with parentheses; -3 surrounds it with
backticks. `FUN_000a9f84` then applies substitutions at the panel boundary.
The optional expression override is narrowed to a signed byte and clamped at
zero. The event exposes raw and displayed text, visible speaker, requested and
visible character IDs, expression, script prefix, presentation mode and theme.
Service 65 uses `(character_id, text_ref, override)`; its ordinary dialogue path
is exposed, while Android promotional checks and an early return are not
reproduced. The ordinary callback at `0x000b10d8` resumes from panel field +0xb0,
initialized to 0 by display setup. Text reveal and page turns hold the VM's
argument frame. The first tap during a reveal requests its completion; a later
tap turns the page or resumes with 0 after the last page. The session owns
the reveal counter, fast-completion request and portrait/name animation clocks;
rendering never acknowledges this callback.

Dialogue typography is now traced through `FUN_0007cbbc`, `FUN_000a8544`, and
`FUN_000aa0a0`. Ordinary body text uses registry font 5; narrator panel mode 4
uses font 1, and speaker names use Pajama Hip variants. Mode 4 is selected by
service 75's configured character ID, not by the thought prefix or the literal
name "Event". Its name and portrait are hidden. Characters with art use mode 1
when matching service 74, or mode 2 otherwise. Missing art selects mode 3,
clears the visible character/theme and retains the old name object.
Character-owned key 651 selects the ordinary theme. Backticks and semicolons are registered
color controls, with a shared toggle. Kerning affects glyph drawing but not
wrap measurements. The desktop uses native layout-17 rectangles, original box
skins, masked portraits and session-owned pagination. Persistent font-object
sizes, gaps, line counts and indents, plus the native name exceptions, are
implemented for the dialogue path and saved in version 10. Drawing applies
a general glyph-bounds correction to prevent remaining name/body/portrait
overlaps; this correction is not a verified native rule. Cross-object kerning,
other widgets' shared font effects, special expression decorations and
global transition locks remain partial. The recovered name branches and
compatibility boundary are specified in
[UI_FIDELITY.md](UI_FIDELITY.md#speaker-labels-and-persistent-font-state).
Ordinary dialogue now has a source-index
reveal, 300 ms portrait scales/name fades, and a 350 ms page-turn reveal delay.
The scheduler policy and remaining timing paths are specified in
[UI_FIDELITY.md](UI_FIDELITY.md#dialogue-transitions-and-reveal-scheduler).
See [UI_FIDELITY.md](UI_FIDELITY.md#dialogue-typography-and-layout-contract)
for the text schema, algorithms, colors, and evidence addresses.

shshd-runtime adds no service for its two-speaker lines, named-line colours,
emoticons or intro-into-loop music. An episode declares the global numbers it
sets around such a line (service 54) in resource 3, and the runtime reads them
while the line is up; see
[SCHEMA.md](SCHEMA.md#presentation-extension-shshd-runtime).

### 4.3 Services 17/40 and 78: UI-owned data

Services 17 and 40 select UI type 15 and pass substituted title, prompt, and initial text to `FUN_000d4440`, with an additional constant 20 at the caller. Callback `FUN_000d3f5c` copies the entered string (panel +0x9c) to dynamic slot 0, resumes with handle `0x7ff5`, and copies it into host last-input storage +0x54. Typing actually permits at most **16 ASCII alphanumeric characters**, with uppercase characters after the first converted to lowercase. Before each append, the existing name width plus cursor width must be below 240 logical pixels. Empty Return does not submit. Native layouts, fonts, error alert, validation, and the callback are implemented; the desktop uses SDL keyboard input. See the [name-entry contract](NAME_INPUT.md) for evidence, geometry, save handling, and remaining fidelity limits.

Service 78 selects UI type 5. Its factory copies `(text_ref, count, array_word_address)` into a portrait selector. `FUN_000d2238` initializes panel +0x70 to indices 0 through count-1; `FUN_000d1d78` swaps indices and portrait pointers. `FUN_000d2008` handles touch release and a separate confirmation checkmark. `FUN_000d1b48` returns the selected **original index**, not the character ID, and writes UI result cell 0. The first portrait is selected initially. The full frame, input, animation and save contracts are in [STORY_SERVICES.md](STORY_SERVICES.md#portrait-selection-service-78).

### 4.4 Service 0: formatting selector exception

`FUN_0009f5cc(..., 0)` uses argument 1 as a raw format reference when nonnegative and returns slot 0. Otherwise argument 2 is the format and the destination is `1-a1`: -1 selects slot 2, and -9 selects slot 10. The runtime supports the native `%c`, `%d`, `%s` scanner and its aliasing scratch slot 10. See [STORY_SERVICES.md](STORY_SERVICES.md#formatting-and-packed-strings-services-0-24-25-28) for bounds, literal percent handling and memory writes. Service 22 (`my_sprintf`) is separate: only `%s` and `%d` are formats, another `%x` keeps x without the percent sign, and the result is written to VM memory at a1.

### 4.5 Complex UI/minigame frames

Services 71, 94 and 96 now have implemented game models and a separate
[mini-game specification](MINIGAMES.md). It defines all frame fields, nested
record layouts, random streams, clock/input transitions and distinct callbacks.
The models preserve pending frames until actual play completes. Presentation
and some native lifecycle boundaries remain incomplete and are listed there;
implementation tests alone do not establish frame-for-frame equivalence.

### 4.6 Services 1–4: ordinary choices

```text
service 1(title_ref, options_ref, description_ref, timeout_ms,
          timeout_selection, character_id, unused_here, portrait_mode)
    title = T(title_ref)
    options = T(options_ref).split('|')
    description = T(description_ref) if description_ref >= 0 else ""
    character_id = UI default 74 when character_id == -2
    pause until a selection or timeout
    R = s16(selected_zero_based_index)
    result_cells[0] = R

service 2(title_ref, description_ref, timeout_ms,
          timeout_selection, character_id, portrait_mode) -> 0
    begin an incremental choice builder
service 3(option_ref, return_value, enabled) -> 0
    append T(option_ref)
    mapping[index] = index if return_value == -999 else return_value
service 4(shuffle) -> pending
    if shuffle != 0: apply native full-list swaps to labels and mapping
    attach the built panel; clear the builder pointer
    R = mapping[selected_zero_based_index]
    result_cells[0] = R
```

Evidence: `FUN_000b07e8`/`000b04b8` construct the delimited choices and register
zero-based indices; `FUN_000ae740`/`000ae6c8` build custom mappings;
`FUN_000afee8` stores the selected index at panel +0x44; `FUN_000add90` applies
the optional mapping, resumes the VM, and writes host +0x60. The final
pipe-delimited field is empty if its content is whitespace; other fields are
not trimmed by the inspected helper. Disabling an incremental option prevents
player selection.

For a nonzero shuffle flag, `FUN_000aeee4` visits rows `i = 0..N-1`, draws
`j = native_random.next() % N`, and swaps labels and return mappings at `i/j`.
Every draw uses the **full** list size, including self-swaps; this is not
Fisher-Yates. The native helper also swaps the widget's index table at +0x9e;
the ordinary choice callback uses the displayed row and panel mapping at +0xae.
Per-row enabled flags stay in their existing slots. Empty lists draw nothing,
single-option lists still draw once, and a zero flag consumes no randomness.
`0004c1bc` calls `00122554` on the same application LCG used by service 27 and
football/grid games, separate from the libc stream used by service 71. See
[MINIGAMES.md](MINIGAMES.md#22-footballgrid-engine-stream) for the generator.

shshd-runtime: an option built with service 3 may carry a **detail line** after the byte 0x1F (`engine.OPTION_DETAIL`):
the label alone is the option (its text everywhere: hints, the test channel, saves' `options`), and the detail goes in
the choice's `details` list, one string per option, moving with its label when the list is shuffled. The HD menu
(`hd_choice.py`) draws it under the label in the option face at 11 points, lighter, as the settings show an option's value
under its name; a row counts its lines. Surviving Hollywood's Where to? puts each place's opening hours there (owner,
2026-11-14). Without one, a choice has no `details` and is as native; other menus show the label only.
From saved state 1, four options end in original-index order `[2,1,3,0]`, with
stored random state `0xc46b9b3d`; the next service-27 call with bound 100 gives 43.

The pending choice stores the resulting labels and mapping. Rendering, repeated
`advance()`, and reloading that choice do not reshuffle or consume random draws.
Old unsupported service-4 saves retain the builder and pre-shuffle random state;
loading validates both and dispatches only that held call once. Shuffling needs
no new save fields; existing version-12 choices remain valid. Clicks and timeouts
use the shuffled return mapping.

The panel stores initial/remaining time at +0x4c/+0x48. `FUN_000ae4f4` subtracts
elapsed time and uses the configured timeout selection; `FUN_000ad6b4` divides
the time by 1000 for its display widget, establishing milliseconds. Nonpositive
durations disable the timer. Expiry is strictly below zero on an active frame
update, matching the native comparison. At exactly zero the frame remains
pending and can still be selected or saved; a zero-length tick does not expire it. An incremental
choice's timeout selection passes through the same mapping as a clicked option.
An invalid mapped timeout is an explicit runtime error, rather than a native
out-of-bounds read. The one exception is Cause of Death, whose action choices
time out to selection -1 ("no option"). Its `SHSUIMenu::setReturnValue`
(`0003e994`) then returns the short just before the mapping table. Only a save
load writes that slot, so it holds the new allocation's zero, and the runtime
returns 0. See [COD.md](COD.md#timed-choices-with-no-timeout-option). `portrait_mode` is not an expression: `FUN_000ae5d4` passes
expression zero to `FUN_0009e810`/`FUN_0009e5d8`, with the mode separately.
The art loader flips mode 2 except for theme 3; character property 651 selects
the choice palette. The choice renderer does not reuse the previous dialogue's
expression. See [UI_FIDELITY.md](UI_FIDELITY.md#ordinary-choice-panels) for
the recovered assets, screenshot-based placement and remaining differences.

Rendering, hover, scrolling and opening the host menu leave the pending VM
frame intact. The desktop suspends timer ticks while that menu is open; a
selection still uses the original zero-based index/custom mapping, and saves
retain the existing pending choice and remaining milliseconds. Timed panels
display the original circular timer (assets 708/709 and layout 22); its elapsed
sweep is derived from that saved clock, without a separate animation timer.

Relevant decompiler excerpt from `FUN_000ad6b4` (panel +0x4c is the initial
duration, +0x48 the remaining time):

```c
FUN_00082744(DAT_002ae938,
    (*(float *)(param_1 + 0x4c) - *(float *)(param_1 + 0x48)) / 1000.0,
    *(float *)(param_1 + 0x4c) / 1000.0);
```

The supplied New Girl script reaches service 1 at scene 25002 PC 316 with
arguments `(0,949,937,-1,-1,-2,-1,1)`. Choices 0/1 lead to different dialogue
instructions at PCs 336/352. Its later randomized choice in scene 25005 uses
service 4 at PC 1465 (bundled) or 1478 (imported), with argument `(1,)`.
Both variants recover an old unsupported checkpoint and continue through the
original option callbacks. See [RUNTIME.md](RUNTIME.md) for playback and save
verification.

## 5. Remaining work and verification boundary

The main menu is a native application state machine outside this yield ABI.
Its button tags (for example 10002 = Play/Resume) are not VM services.
[MAIN_MENU.md](MAIN_MENU.md) documents states 101/110/111/112, menu commands,
asset bindings and the compatible runtime's local-content lifecycle.

The earlier saved fresh-state corpus trace stopped at recognized service 8 presentations in 37 archives and at unimplemented services 99 (156 archives), 35 (30), 73 (28), 65 (20), or 80 (3) in the other 237. It predates the playback handlers above. No VM error or budget exhaustion occurred before those stops. The new import/session audit covers 271 deduplicated episodes and 974 script records, stopping at 58 presentations, 53 ordinary dialogue screens, 159 service-99 calls, and one service-89 call, with no exception; see `runtime-import-audit.json`. Both audits describe initialization, not exhaustive gameplay coverage.

Ordinary choices and service-71 scores execute distinct actual New Girl branches.
Football and word/picture grids have recovered models, desktop input and saved
random replay. LIFO loading and JSON save migration are tested. Service 99 is a
verified native stub; service 91 now gates execution through the native loading
timer and continues into Football Star's first match. Remaining blockers include
other state/panel services, native save/resource extensions, audio and outstanding
mini-game presentation. The corpus's presence of a service does not prove the
Android helper matches its original iOS semantics.

## 5.1 New Rules' minigame arena (shshd-runtime services 200–213)

These are not native SHS services. Episodes translated from SHS: New Rules
(`tools/translate`) call them, as does New Rules' own minigame library, which
runs beside the story as a linked segment (VM_SPEC.md §2.3). Each stands in for
one New Rules service and answers as New Rules' engine does. The panel, its
properties and its clock are decoded in
[NEW_RULES.md](NEW_RULES.md#the-arena) and modelled in `nr_arena.py`.

| Service | New Rules | Arguments | Result |
| --- | --- | --- | --- |
| 200 | 50 | margins, show score | Opens the arena panel |
| 201 | 51 | label id (690–695), text | Sets a label |
| 202 | 52 | property, value | Sets a property on the selected slot |
| 203 | 53 | property | The property's value |
| 204 | 54 | slot | The slot's item |
| 205 | 55 | slot, item or text | Puts an item in a slot |
| 206 | 56 | slot, property, v1[, v2[, v3]] | Sets a property; 718 closes the panel |
| 207 | 57 | slot, property, v | Sets a property |
| 208 | 29 | — | Waits for the next frame (the session completes it on its next tick) |
| 209 | 5 | [−k], format, values… | Formats into string slot k−1 (slot 0 without a selector); the slot's handle |
| 210 | 9 | title, `a\|b…`, selection | A menu over the panel; waits; the chosen index |
| 211 | 10 | text | An info box over the panel; waits for OK; 0 |
| 212 | 32 | selector | New Rules' build query as the Java (arena) build answers it |

Service **70 selector 200** answers 1 when the arena plays here: New Rules'
library is attached and the player's arena switch is on (`Session.nr_arena`).
Native players and upstream exp-runtime answer 0 to an unknown selector, so a
translated story takes the word game or timed choices it also carries.

Service **213** (no arguments) goes before each arena game. It answers −1 to play
the game. With Ask to Skip Mini-Games on, it waits for the player's choice and
answers the result the game would have left instead
([NEW_RULES.md](NEW_RULES.md#skipping)).

## 5.2 The X360 minigames (shshd-runtime services 214–217 and 222)

These are not native SHS services either. Episodes translated from the cancelled
Xbox 360 game call them after **70 selector 201** answers 1, which it does only
with the player's minigames switch on. Otherwise a story takes the fallback it
also carries ([X360.md](X360.md#minigames)).

| Service | Game | Arguments | Result, after waiting for the game |
| --- | --- | --- | --- |
| 214 | Slot machine | — | Bulbs taken, 0–5 |
| 215 | Leash game | — | 1 won, 0 lost |
| 216 | Jewel puzzle | — | The score |
| 217 | Diss Practice | show the tutorial first | The score, at most 32767 |
| 222 | Diss Battle (the Monday Planner's; ours: `x360_battle.py`) | show the tutorial first, a bonus added to the grade, the round count, a table of 5 text references a round (target, the rhyme, three wrong words) | The grade, 0–10 (a skip: 10 or 0) |

The Diss Battle has its own question, **70 selector 205** (`X360_BATTLE_QUERY`;
`minigames_available` with `for: x360_battle` in the creator), answered by the same
switch. An older shshd-runtime that answers 201 but lacks 222 answers 205 with 0, so
the story falls back to the speed diss it also carries.

Saves from version 40 keep a Diss Battle in play.

## 5.3 Storyboard cutscenes (shshd-runtime service 218)

Service **218** (`spec`) plays the storyboard whose JSON spec is resource `spec`, and
completes with 0 after its last press. A story asks **70 selector 202** first, which
answers 1 only on a player that draws them (`Session.cutscenes`). Native players and
upstream exp-runtime answer 0 to an unknown selector, so a story goes straight on.

The spec is described in `cutscene.py`. A service 16 before it runs when its last press
ends it, with the last picture up under the closing blinds.

## 5.4 SHS '11's minigames (shshd-runtime services 219 and 220)

Episodes translated from SHS '11 call these (`seconds`, `target`, `rounds`, `table`, `character`, the player) after
**70 selector 203** answers 1, which it does only with the player's minigames switch on.
Otherwise a story takes what it also carries, the smartphone's game at that spot.

| Service | Game | A record of `table` |
| --- | --- | --- |
| 219 | Memory | 6 words: cue text, word text, bonus, points a letter, letter time in ms, the round's limit in ms |
| 220 | Reflex | 13 words: right icons at least, the gauge's size, bonus, points a bar, right, wrong and skull pictures, odds of 1, 2 and 3 bars and of a skull, flash ms, hold ms |

Each waits for the game (`shs11_games.py`, with its tutorial the first time in a story) and
completes with **2** at 98% of the target or more, **1** above 75%, else **0**. [SHS11.md](SHS11.md) has the rules.

Service **96**, a word grid, can also open Memory, with the player's "Use '11's Memory for Word Grid" switch on and a grid that fits (`shs11_games.grid_memory`). It then completes with the grid's own result: **1** at 98% of the target or more, else **0**.

## 5.5 The BREW games' catch game (shshd-runtime service 221)

Episodes translated from the BREW games call it after **70 selector 204** answers 1, which it does only with the player's
minigames switch on. Otherwise a story plays a word game (71) in its place. Its 11 arguments: the kind (1 angled, 2 sideways,
3 orbit, as BREW's services 20, 21 and 19), the target, ms between items, speed, spread, the odds (of coming at the angle, or
from the left), the angle, the player's picture, a list of items (its length, then value, picture and count each), a table of
sizes (picture, width, height each) and how many sizes it holds. A 12th, optional: a table of the scores at which the story after it can go another way (a count, then
the scores; -1 for none), read by the translator from the story's own comparisons. Only the skip prompt reads it
(`choice_hints.brew_catch_outcomes`: one preview per stretch of scores instead of trying them in turn). It waits for the game (`brew_catch.py`) and completes with
the score, from 0 to the target. The scripts test it themselves. [BREW.md](BREW.md) has more.

## 5.6 Running a script and coming back (shshd-runtime service 223)

Service **223** (`script`) runs scene script `script` to its end and then returns to the instruction after the call, as a
call into another scene would if SHS had one. The caller's frames wait on a stack that saves keep (save version 39). Fall '06's
nest runner uses it for the events BREW runs inside another (service 37), one after another, as the decompiled '08 engine
does (`FUN_0000af08`). It takes exactly one argument and nests at most 16 deep (`NESTED_SCRIPT_DEPTH`); the inner script's end
(a halt) resumes the caller with 0. Native players and upstream exp-runtime
stop at it as an unknown service. [BREW.md](BREW.md) has the season driver around it. The Creator's **Run due events** and **Run a scene and come back** nodes use it too ([CREATOR.md](CREATOR.md#calendars)).

## 5.6a The word grid's part score (shshd-runtime service 224)

Service **224** takes no arguments and returns the last word grid's (96) **part score**: the most letters of one of its
words traced in their places, counted on every cell added to a trace (`word_grid.part_score`; the engine keeps it as
`grid_part_score` when the grid closes, and saves keep both, save version 41). A script reads it right after service 96, as
it reads football's score with 95 after 94. Surviving Hollywood's translated rehearsals return it for a missed word, as the
demo scores the letters typed right when time runs out (Tardy-Slip `web/shw/screens.js` `Spelling.check`), so Glamlet's
soliloquy can give its middle reaction (owner, 2026-11-17). Native players and upstream exp-runtime stop at it as an
unknown service.

## 5.6b Story-object pictures (shshd-runtime service 225)

Service **225** (`picture`) puts an episode-bank picture (the episode's own, or a required add-on's: Claire Hart Classic's are
chc's 27000 on) in the dialogue box, as Claire Hart's `showStoryObject` does (CLAIRE_HART_ENGINE.md §4.7; plan decision P). It
completes at once with 0. The picture waits for the next dialogue line and shows with it, in a framed square along the box's
bottom, right-aligned (`dialogue.story_object_slots`; the box grows a row for them, upward for a speaker so its bottom stays,
downward for a narrator). More pictures before a line join the row, up to 8 (`STORY_OBJECT_ROW`). The row goes at the next
change of speaker (character, name and presentation), as Classic's go when the next box comes in; `picture` −1
(`STORY_OBJECT_CLEAR`) empties it at once, as a box coming in for the same speaker does there; Skip Ahead empties it too, as
Classic's Skip does. Saves keep the row, what waits for the next line and whose lines it is shown with (save version 43).

A story asks **70 selector 206** (`STORY_OBJECT_QUERY`) first. Cause of Death's dispatcher answers 1; native players, upstream
exp-runtime and this player's SHS answer 0, and the story shows a message naming the item instead (the Creator's **Story object
picture** node compiles both ways).

## 5.6c Claire Hart's hidden-object rounds (shshd-runtime service 226)

Service **226** (`key`) plays Claire Hart Classic's hidden-object round `key`: its original episode's number × 10 + the round
(`claire_round_services.round_key`: E018's third is 183), from the optional `chcrounds` add-on, whose spec at 26000 names the
round's scene, its objects and its story objects (the session's `claire_round_source`; reference/Other Games/docs/
CLAIRE_HART_ROUNDS_PLAN.md). Its rules are build 157's (`claire_rounds.ClaireRound`: 12 objects to find, 6 listed at a time, the
round's story objects among them and listed first, the combo, misclicks and the spam lock, the timer, the bonuses and stars, the
free hint and the four power-ups under the **Power-Ups** setting). The player draws it over the whole frame
(`desktop_claire_round.py`) and hands in what a tap hits; the round ends on its Level Summary, whose Continue completes the call
with the round's total score (`Session.claire_continue`). The story reads no result: Ask to Skip's Skip completes it with 0. Saves
keep the round whole, so a save mid-round resumes it exactly (save version 44). A key the add-on hasn't stops as an unhandled
yield.

A key from **20000** is Secret in the Shadows' round (`shadows_key`: 20000 + case × 100 + part × 10 + the round, so case 31
part 4's fifth is 23145; a signed word, as every Creator node's number is), from the optional `ch2rounds` add-on, under build
232's rules (`shadows_rounds.ShadowsRound`: close-ups, multi-part objects, the Gold Key, the Psychic Sensor with its cooldown,
the combo to ×6 a tier at a time, spotlight rounds, the Hint, Time Warp and Clairvoyance under Power-Ups) on the sequel's
screen (`desktop_shadows_round.py`). **Round Style** (`claire_round_style.py`) plays either game's round under the other's
rules and screen: a sequel scene under Classic's offers only its ordinary objects; a Classic scene under the sequel's has no
extras. A style whose screen's add-on is gone falls back to each game's own. Saves keep either round whole, with the add-on
its scene is from (save version 48; an older save's round is Classic's).

A story asks **70 selector 207** (`CLAIRE_ROUNDS_QUERY`) first. Cause of Death's dispatcher answers 1 where `chcrounds` is in the
library and Use Translated Mini-Games is on; native players, upstream exp-runtime and this player's SHS answer 0, and the story
takes its other path (the translated cases' stand-in line naming the place searched and what was found). A sequel round asks
**70 selector 208** (`CLAIRE2_ROUNDS_QUERY`), answered 1 where `ch2rounds` is in the library and Use Translated Mini-Games is
on.

## 5.7 The BREW packs' text and menus

In the BREW translations (profile `TRANSLATED_ARTICLE_PACKS`, `TRANSLATED_BREW_MENU_PACKS`, `TRANSLATED_THREE_WORD_PACKS`), and
in an episode made in the Creator that declares the same setting (SCHEMA.md "Presentation extension"), some native services
answer as BREW's engine did:

- **22 and 0** (formatting): `a(n)` before a word becomes `a` or `an` by that word, and `word(s)` or `word(es)` after a number
  the singular for 1 and the plural otherwise (`engine.choose_articles`, `choose_plurals`). Service 0 only for a Creator episode
  that asks.
- **1** (a menu): a blank last option, from a list ending in `|`, is dropped, as BREW's menu builder does (`FUN_0000d6a0`);
  SHS keeps it.
- **71** (a word game) may have three words, one or two of them good; natively it stops without two of each.

## 6. iOS HD-build-only services (Faceplace / DT view)

Reference: the HD iPad build's own `Surviving_HS` binary (`com.ea.shs.ipad.inc`,
`CFBundleShortVersionString` 1.4.38, 32-bit Mach-O armv7), extracted from the
player-supplied `.ipa` and imported into a separate Ghidra program from the
Android `.so`. SHA-256 `327cf59ddb8efd704795099d5b5e9a04ceec51f6c084bf7d0962e78e3ae7e875`.
Unlike the stripped Android `.so`, this binary retains its full C++ symbol
table, so its dispatcher is named directly: `SHSScript::syscall(int)`, a
dense Thumb-2 `TBH` jump table over ids `0`–`0x78`. Its low ids (at least
through the low 70s) decompile identically in shape to Android's
`FUN_0009fe3c` handlers; ids above the documented Android range diverge and
are new to this build. As with the Android table above, presence in this
build's dispatcher is not evidence the same id means anything on Android or
in an original iOS build without its own dispatcher.

**The entire DTView/Faceplace cluster (services 101–120, native cases
`0x65`–`0x78`) is now decompiled and implemented.** Ghidra's decompiler is
not trustworthy for this specific function at the argument level (several
cases visibly fetch real strings off the VM stack and then appear to
discard them, passing empty placeholders to the actual `objc_msgSend`
instead, which cannot be real behavior; the function also triggers 300+
"unreachable block" warnings during decompilation). Every case below was
instead verified from raw Thumb disassembly: the jump table's targets were
computed by hand from the table base (the same dense Thumb-2 `TBH` table
`SHSScript::syscall` uses for ids `0`–`0x78`) and disassembled directly with
capstone, bypassing the decompiler entirely.

That raw-disassembly pass resolved the one fact that mattered for safety:
**every case in this cluster discards its `objc_msgSend` return value** --
confirmed directly in the instructions (the call result is never stored in
a register or branched on; execution falls straight through to argument-
buffer cleanup and `break`), the same shape already proven safe for
`scriptEnable`. That is what made the whole cluster safe to implement as
no-ops first, without yet resolving which of the script's own arguments
maps to which named parameter -- keeping the VM running doesn't depend on
content fidelity for rendering a decision-tree diagram or Faceplace
message. That harder question (which turned out not to be a separate
"resource-table" scheme at all -- see 6.2) was resolved in a later session,
and every case below is now backed by a real, verified data model.

| ID decimal (hex) | Native selector / behavior | Python |
| --- | --- | --- |
| 101 (`65`) | `objc_msgSend(g_engineDTView, @selector(scriptEnable))`. Bare. | C (`dt_view.enabled`) |
| 102 (`66`) | `addNode:innerLabel:upperLabel:lowerLabel:exw:` on `g_engineDTView`. | Modeled: `DTView.add_node(args[0], read_text(args[1]), exw=0)` -- see 6.2 |
| 103 (`67`) | `addNode:innerLabel:upperLabel:lowerLabel:exw:` on `g_engineDTView`, different argument shape. | Modeled: `DTView.add_node(args[0], read_text(args[1]), exw=args[2])` -- see 6.2 |
| 104 (`68`), 105 (`69`) | `addNode` with three labels (type, inner, upper, lower); exw not passed. | Modeled: `DTView.add_node(args[0], read_text(args[3]), exw=0)` |
| 106 (`6a`) | `addResult:exitLabel:` on `g_engineDTView`, dynamic exit-label string. | Modeled: `DTView.add_result(args[0], read_text(args[1]))` -- see 6.2 |
| 107 (`6b`) | `addResult:exitLabel:` on `g_engineDTView`, sprintf-formatted exit-label. | Modeled: `DTView.add_result(args[0], str(args[0]))` -- see 6.2 |
| 108 (`6c`) | `objc_msgSend(g_engineDTView, @selector(clearGlobalAccumulator), <value>)`. | C (`setIntProperty(entity id, 0x197, 0)` for an id below 600, else `setIntProperty(0, id, 0)`, and the id joins `DTView.accumulators` -- see `dt_state.py`) |
| 109 (`6d`), 110 (`6e`) | The tree's update and save. | C (`dt_update`, `dt_save`) |
| 111 (`6f`) | `addBranchNode:condition:innerLabel:upperLabel:lowerLabel:exw:` = addNode, then the node's branch condition. | Modeled: `DTView.add_node(args[0], read_text(args[4]), exw=0)`, `condition = args[1]` |
| 112 (`70`) | `addNode(0x4c8, "", "", "")`: a join node. | Modeled: `DTView.add_node(0x4c8, '', exw=0)`, joining the node that owns the repeated ids |
| 113 (`71`) | t(key), t(value): stores key = value only while `$USR` is empty, then `setNeedsDisplay` on `g_engineFSView`. | C |
| 114 (`72`) | `objc_msgSend(g_engineFSView, @selector(scriptEnable))`. Bare. | C (`faceplace.enabled`) |
| 115 (`73`) | `incomingMessage:from:expression:` on `g_engineFSView`. | Modeled: `FaceplaceWall.incoming_message(resolve_text(args[0]), args[1], args[2])` -- see 6.2 |
| 116 (`74`) | `incomingContinuationMessageText:url:` on `g_engineFSView`. | Modeled: `FaceplaceWall.incoming_continuation_text(resolve_text(args[0]), read_text(args[1]))` -- see 6.2 |
| 117 (`75`) | `incomingContinuationMessageImage:url:` on `g_engineFSView`, **and** `incomingContinuationMessageText:url:` on the same call -- see 6.2. | Modeled: `FaceplaceWall.incoming_continuation_image(args[0], resolve_text(args[1]), read_text(args[2]))` -- see 6.2 |
| 118 (`76`) | `objc_msgSend(g_engineFSView, @selector(clearWall))`. Bare. | Modeled: `FaceplaceWall.clear()` |
| 119 (`77`) | `objc_msgSend(g_engineFSView, @selector(nameChosen:))`. Observed with zero pushed arguments despite the colon. | C (no-op) |
| 120 (`78`) | `objc_msgSend(g_engineFSView, @selector(faceChosen:))`. Same as 119. | C (no-op) |

Yield 113 (HD `SHSScript::syscall` case 0x71) reads its key, then its value,
as yield 46 does, and stores them only while `getNameReplacement("$USR")`
is empty. Football Star 25008 is the one caller: ("$USR", "John"), the name
a fresh install's `shs_options.sav` holds before any is typed.

Yields 43, 46, 47 and 113 share one name-replacement table
(`SHSEntityTable` renames). The app saves it in `shs_options.sav`, loads it
at start and never clears it, so it spans every episode and new game.
`SHSDTView warpToNode:` keeps `$USR` across a warp. This runtime keeps the
table in the library's `player.json` (`names`): every session the desktop
plays shares it (`Session.share_names`), and keys only an older save holds
join it. See [RUNTIME.md](RUNTIME.md#names-shared-across-episodes).

**Yield 120 (`faceChosen:`) is confirmed live to be the same mechanism as
an earlier, separately-documented avatar/name-picker gap from the original
KiWi-bytecode-only research** (a `derefPointer`-fed portrait picker whose
real ids were never recovered there). Running the HD build's own native
Football Star through this engine, with the full cluster above implemented,
reached the real `character_picker` action with
`characters=[88, 89, 90, 91, 92]` -- the actual 5 portrait ids -- and its
already-correctly-implemented completion path (built independently, not
new this session) resumes straight into yield 120, exactly as this cluster
predicts.

With the full cluster implemented, HD's own native Football Star runs
cleanly from scene 25001 through the entire "New Girl" story opening: 278
unique dialogue lines, zero further unhandled services or VM errors, all
the way into the real football minigame and a word-grid puzzle (both
pre-existing, unrelated systems). The run only stops because a driver
without interactive input can't *play* those minigames, not from any
remaining engine gap.

A gap found then is now closed: service 73 for a character never given art
returns 0, as the native table is zero-filled (`engine.py`), so HD's Football
Star runs on from there. The original finding, kept for its history, was
`VMError("Art requested for uninitialized character 0")`. Root-caused (not just observed): diffing every yield
instruction in HD's `25001` against Android's copy of the same script shows
both are byte-identical through instruction 182, after which HD inserts a
new block (the `scriptEnable` calls, then character-art queries for ids
0/13/14) that queries those ids' art *before* this scene ever sets it --
those ids are properly `set_character_art_base`'d moments later in the same
block, so the query almost certainly expects app-wide state established
outside Football Star entirely (name/avatar creation), which a standalone
test of one episode never runs. This blocks launching Football Star (HD)
directly and cold in the real desktop app, confirmed by attempting exactly
that; it does not block the regular story-episode path, which reaches the
same character-picker moment without it (verified live in the desktop app
with the real APK and the built-in "The New Girl" episode).

**Correction, recorded for anyone reading the history:** an earlier pass of
this investigation suspected yields 74/75 (called shortly after the
character-art block) might collide with this table's Faceplace cluster.
That was wrong -- decimal 74/75 are native cases `0x4a`/`0x4b`
(`SHSUIDialog::setPrimarySpeaker`/`setEventSpeaker`), a different case value
that looks similar in hex. `engine.py`'s existing `y in (74, 75)` handler
already correctly implements this; there was no bug. Caught before being
recorded as fact, not after.

### 6.1 DTView/Faceplace real argument semantics (from Objective-C method decompiles)

The table above names each yield's native selector but treats several
argument shapes as opaque ("different argument shape", "drained, not
rendered"). Decompiling the actual `-[SHSDTView ...]`/`-[SHSFSView ...]`
Objective-C method implementations (not just their call sites in
`SHSScript::syscall`) resolves the real parameter meanings:

**DTView** (`addNode:innerLabel:upperLabel:lowerLabel:exw:`, `addBranchNode:
condition:innerLabel:upperLabel:lowerLabel:exw:`, `addResult:exitLabel:`):
confirmed to build a real, persistent decision-tree data structure (`DTNode`,
with a `DTNode::root`), not a one-shot visual effect:

- `addNode`'s five arguments are, in order: a node-type/id (`int`), then
  `innerLabel`/`upperLabel`/`lowerLabel` (each a `CSString`, converted via
  `CSString::toCharArray` straight into a `DT2LineText`, i.e. real on-node
  label text), then `exw` (`int`, a KiWi fixed-point value divided down after
  `FixedToFP`, stored as the node's width scale). Each call appends a child
  to `_cur_node` if one exists, else starts a new root; either way it
  auto-saves a `tree_<serial>.sav` file via `SHSEngine::saveGameFile` --
  DTView state is meant to persist across sessions, independent of the
  episode's own save.
- `addBranchNode` is `addNode` plus one extra `condition` (`int`) argument,
  stored on the new node at a fixed offset -- a conditional branch point in
  the tree, not a separate visual element.
- `addResult:exitLabel:` records which branch/child index the current node
  resolved to (`param_3`) and its exit label text, guarded by an
  `_awaiting_result` flag that `addNode` sets and `addResult` clears --
  `puts()`-based assertions fire (visible in a console, not the UI) if a
  script calls `addNode` twice without an intervening `addResult`, or
  `addResult` twice without an intervening `addNode`. This confirms the
  script's calls to this cluster are meant to be paired, not independent.

**Faceplace** (`incomingMessage:from:expression:`, `incomingContinuation
MessageText:url:`, `incomingContinuationMessageImage:url:`): a real,
ordered, timestamped message wall, not a placeholder:

- `incomingMessage:from:expression:` takes the message text (`CSString`),
  a `from` id and an `expression` id (both `int` -- the same shape as a
  dialogue portrait's character id + expression code). It resolves a slot
  via `getMessageIndex:from:expression:`, then pushes onto four parallel
  arrays: `mCurMessages` (the slot's encoded key string), `mCurTimeStamps`
  (a real `CFAbsoluteTimeGetCurrent()` capture), `mCurMessageStates` (state
  code `5`, "new"), and two pre-measured heights (`mCurMessageHeightP`/`L`,
  against wrap widths `204.0`/`224.0` -- the wall's portrait/landscape
  column widths).
- Each message's identity is packed into one `std::string` "key" as
  `"%d %d "` (two ints), read back with `sscanf` elsewhere
  (`getImageResIDWithMessageIndex:`, `isFaceMessageWithIndex:`,
  `isContinuationMessageWithIndex:`): the first int is the `from` id, or
  `-1` for a system/attachment message; when it's `-1`, the second int's
  sign/parity distinguishes a face-expression message
  (`(-second & 1) == 0`) from a continuation message (`second < -10`), and
  an image message's actual resource id is appended as extra text after the
  two ints and recovered with `atoi` past the second space. This encoding
  was reconstructed from the accessor methods, not guessed -- it has not
  been round-tripped against a real captured message yet.
- `incomingContinuationMessageText:url:`/`incomingContinuationMessageImage:
url:` insert a message associated with an *existing* one (shifting the
  parallel arrays to keep it adjacent) rather than always appending, using
  `sscanf`-parsed existing keys to find the right slot -- the shape a
  threaded reply or a caption-after-photo needs.

Services 102/103/106/107 (DTView) and 115/116/117/118 (Faceplace) are now
implemented, modeling this real content -- see section 6.2. Reference:
`reference/ghidra_scripts/dtview_faceplace_decompile_report.txt` (raw
decompiles) and `legacy/findings.md`'s DTView/Faceplace layout section (the
layout half of this same investigation). Both are the owner's private notes,
kept outside this repository.

### 6.2 DTView/Faceplace real per-argument mapping (from raw Thumb disassembly)

Section 6.1 recovered the ObjC methods' own parameter meanings from their
decompiled bodies. It did not resolve which of *this engine's* `args[i]`
(the yield's own VM-stack words, 0-indexed in push order -- see `vm.py`'s
`arguments = tuple(stack_word(i) for i in range(sp-count, sp))`) maps to
which parameter at the actual `SHSScript::syscall` call site, because
Ghidra's decompile of that specific function is demonstrably wrong at the
argument level for these cases: for native case `0x66` it shows a real
string fetched via `getStringFromStackNoTranslation` and then destroyed
(`decUsage`) without ever reaching `objc_msgSend`, and the visible call
only has 2 of the selector's 5 real arguments. This is a known decompiler
failure mode for `objc_msgSend`, not a real behavior.

Resolved instead by pulling the HD ipa's own `Surviving_HS` binary
(`com.ea.shs.ipad.inc`, SHA-256 `327cf59d...e875`, armv7 Mach-O, matching
the executable this project's `content.py` already validates against),
locating `SHSScript::syscall`'s dense Thumb-2 `TBH` jump table by hand
(base `0x3da5c`, `pc_base = 0x3da60`, target `= pc_base + 2 * table[case]`),
and disassembling each case block directly with capstone (Thumb mode),
tracing literal-pool loads (`movw`/`movt`/`add reg,pc`/`ldr`) to their real
selector strings and register arguments -- bypassing the decompiler
entirely, the same rigor already used for yields 101/114/119/120. Full
per-case traces live in this investigation's working notes
(`legacy/findings.md`, "DTView/Faceplace: real per-argument mapping from
raw disassembly"; the owner's private notes, outside this repository).

**The key structural finding:** `getStringFromStackNoTranslation(dest, this,
index)` -- called at every DTView/Faceplace string argument -- reads
`argBuffer[index - 1 + (arg32 - arg74)]`, where `arg32`/`arg74` are the same
`this+0x32`/`this+0x74` fields every other already-implemented yield in
this engine already reads its own arguments through. That is: native
1-based `index` **is** this engine's `args[index - 1]`, not a separate
resource-table addressing scheme requiring its own model. The "resource-
table-relative" language in section 6's original writeup was this
uncertainty before it was resolved; it turned out to be the same mechanism
`args`/`need()` already implement everywhere else in `engine.py`.

**Per-case real argument mapping**, each cross-checked against the yield's
already-empirically-verified argument count (`need()`, established live
against HD's own Football Star before this session):

- Case `0x66` (yield 102, `need(2)`): `addNode(nodeType=args[0],
  innerLabel="", upperLabel="", lowerLabel=read_text(args[1]), exw=0)`.
  `innerLabel`/`upperLabel`/`exw` are hardcoded (empty-string literals and
  a literal `0`), not read from the script at all at this call site.
- Case `0x67` (yield 103, `need(3)`): same selector, `exw=args[2]` instead
  of the hardcoded `0`; `innerLabel`/`upperLabel` are still hardcoded empty.
- Case `0x6a` (yield 106, `need(2)`): `addResult(index=args[0],
  exitLabel=read_text(args[1]))`.
- Case `0x6b` (yield 107, `need(1)`): `addResult(index=args[0],
  exitLabel=str(args[0]))` -- the exit label is `sprintf("%d", args[0])`
  of the *same* value, not a second script argument.
- Case `0x73` (yield 115, `need(3)`): `incomingMessage(
  message=read_text(args[0]), from=args[1], expression=args[2])` -- `from`/
  `expression` are raw shorts read directly off the argument buffer, not
  resolved through `getStringFromStackNoTranslation`.
- Case `0x74` (yield 116, `need(2)`): `incomingContinuationMessageText(
  text=read_text(args[0]), url=read_text(args[1]))`.
- Case `0x75` (yield 117): **not** the same shape as `0x74` despite the
  similar selector name -- reads 3 words, not 2 (the previous `need(2)`
  shared with 116 was an unverified guess; 117 had never been reached live
  before this session). Fires two `objc_msgSend` calls back to back:
  `incomingContinuationMessageImage(imageId=args[0],
  url=read_text(args[2]))` immediately followed by
  `incomingContinuationMessageText(text=read_text(args[1]),
  url=read_text(args[2]))` -- the same `url` both times. Modeled as one
  logical wall entry carrying both the image and its caption. **`need(2)`
  changed to `need(3)` this session** to match.
- Case `0x76` (yield 118, `need(0)`): bare `clearWall`.

The engine now reads the message (115), the continuation text (116) and the
caption (117) with `resolve_text`, which substitutes `$USR` (a real-device
correction); the URLs and the tree's labels stay raw `read_text`.

**Verified against real content, not just in theory:** running HD's own
Football Star (`tools/audit_hd_football.py`) with this mapping wired into
`engine.py` produces a `DTView` tree whose node labels read as a real,
coherent progression outline -- `"Week 1"` -> `"Meet Beth"` -> `"What are
you into?"` -> `"Flirt with Beth"` -> `"Meet Adam"` -> `"Speak to Adam"` ->
`"Fight!"` -> `"Meet Raven"` -> ... -- matching the actual story beats this
project already confirmed live (Beth, the Adam fight, Raven, Howard). The
`FaceplaceWall` fills with real, in-voice social-wall posts (`"Potential
fight in the main hallway! Twenty bucks says the new kid loses a tooth!"`)
including one genuine cross-promotion ad with a real `itunes.apple.com` URL
via the continuation-text path. Coherent, in-character text at every
resolved `args[i]` position -- not garbage, not empty, not a type error --
is strong independent confirmation the index mapping above is correct, on
top of the register-level disassembly it was derived from.

**Since implemented:** the tree's per-node saves (`tree_<serial>`, numbered in
`dtview_faceplace.py`; `native_tree.py`) and the warp to a node
(`Session.warp`), the tree's layout ported from the app's `DTNode` classes
(`dt_layout.py`), and the drawing of the tree (`desktop_panels.py`,
`desktop_tree_zoom.py`) and of the Faceplace wall (`drawMessage`/`drawFace`,
`desktop_faceplace_alert.py`).
