# Portrait selection and built-in story services

Reference: SHS Android 1.0.9, `libshs09.so`, SHA-256
`b17aa4c71bc46666d414cafae6fac92bbcd755f3dcccd73975cf05f4a119665b`.
These are host-service contracts; VM opcodes and EXP resource IDs are separate
namespaces. All assets, text and bytecode come from the player's content.

## Episode exit (services 7 and 63)

```text
arguments : none read; every supplied word is ignored
aliases   : 7 and 63 enter the same native scene-exit helper
scene     : dispose panels, cancel script queue, clear numeric state
input     : none; terminal application handoff
callback  : none; no next instruction or scheduled script executes
result    : native dispatcher writes 0, but there is no surviving caller
resume    : retire the current episode's ordinary resume progress
```

`0009fe3c` cases `0x07` and `0x3f` enter `0007e614`. It calls `0007e59c`,
sets scene byte `+0x1b` to 1, then calls `0008a770` on the application.
The three words used by Football Star are not title/message arguments to
this service; that display has already happened through service 33.

| Helper | Verified effect |
| --- | --- |
| `0007e4c4` | Disposes the scene's panel collection, clears the scene badge ID and queued transition selector |
| `000805d0(scene+0x1bc4)` | Disposes an auxiliary collection of scene-owned objects |
| `0009ee48`, `0009f200` | Reset the script hosts and VM execution pointers; clear their pending/loading gates, current script IDs, choice builder and last-input text |
| `0007e59c` | Also zeros scheduled-script count `+0x3bc`, clears scene gates and calls the game-state reset |
| `0009623c` | Frees the numeric key/value arrays and zeros the first 200 state bytes (expression defaults); character names/art and replacement strings are outside these cleared ranges |
| `0007f5f4` | Does not load queued scripts when the scene-exit flag is set |
| `0008a770` → `0008a6cc` → `000885f4` | Removes the active episode's native resume file and clears application byte `+0x6ac0c` |

`0008a60c` chooses the native resume file by packed episode ID: 0 uses
`shs_football.sav`, `0x50009` uses `shs_newgirl.sav`, `0xe99` uses
`shs_season1.sav`, and other IDs use `shs_expansion.sav`. `0008b618` refuses
to write another scene save while the exit flag is set. `0008b048` likewise
stops treating the Football Star live scene as resumable after that flag;
it instead tests the save file. There is no score calculation, reward,
random draw or episode-unlock assignment in this path.

The runtime exposes terminal `EngineAction('episode_exit')`. Its `completed`
flag is false because the enclosing application must handle the handoff;
there is no VM callback to answer. `Session.advance()` and `tick()` retain
that terminal action, and `answer()` rejects it. The cleared scene contains
no queued scripts, numeric entries, expression overrides in IDs 0–199,
panels, active games, loading/choice gates, scene badge, notices, transition
selector or last-input text. Other mapped state, including RNG streams and
UI result cells, is not assigned a new value by this exit operation.

The supplied iOS games confirm the same handoff: SHS `SHSScript::syscall`
(`0006dd6c`) and CoD `SHSScript::syscall` (`0003354c`) dispatch 7/63 to
`GameModel::endGame` (SHS `00021ad4`, CoD `00012454`). These reset the scene,
set its exit flag and retire resume progress; they read no destination pack or
episode ID. `runScript09` (SHS `00022a28`, CoD `00012494`) also ends exhausted
script queues through `endGame09` (SHS `00022b44`, CoD `00012470`), which calls
the application's `invokeEndOfGameMenu` (SHS `0003b928`, CoD `00018bc4`).
Episode catalog selection belongs to that application/menu layer, outside the
KiWi instruction stream. Creator End nodes reuse service 7 and the existing
player menu rather than supplying a separate episode-link mechanism.

The menu application checkpoints the termination and returns to its main
menu, stopping episode audio and releasing the live session. This uses the
desktop menu's existing entrance; exact native exit-frame scheduling and
menu transition animation have not been recovered. A standalone diagnostic
`Desktop` without a menu displays its terminal episode screen instead.

### Save schema, version 12

Version 12 adds the pending action `{name:"episode_exit", details:{}}`.
The original final `vm.pending` yield and its entire frame are retained only
as an audit record, validated against the original program/stack as usual.
They do not represent the native VM object's post-reset memory and can never
receive a callback through `Session`. The teardown must already have been
applied to `engine`; live panels, queued work, uncleared numeric state or a
choice timer invalidate a terminal checkpoint. No new engine fields are added.

An earlier `unhandled_yield` checkpoint at 7/63 dispatches only its retained,
validated call. Loading does not execute another instruction, replay earlier
choices or rewrite the player's save file. The application subsequently writes
a terminal automatic checkpoint as part of its menu handoff.

The desktop preserves its explicit manual F5 slot. A fully validated terminal
checkpoint, when newer than other checkpoints for that episode, suppresses
ordinary Resume instead of falling back to an older manual save. Starting
the episode then creates a fresh session; an explicit Load can still restore
the manual slot. New progress replaces the automatic checkpoint normally.
Invalid terminal files remain visible to Resume so their load error is reported.
Other episodes' saves are unaffected. If checkpoint writing fails, the menu
keeps the terminal live session and reports the error so the operation can
be retried without continuing the VM.

Authored tests cover both call encodings and aliases, ignored arguments,
scene teardown, canceled script queues, terminal immutability, saved-frame
validation, old-stop recovery, trace output, menu/audio handoff, checkpoint
failures, manual-save preservation and new-game startup. An optional test
executes Football Star scene 25001's original caller at PC 234 through its
service-33 message at PC 126 and service-7 exit at PC 130 (byte offset 3283,
arguments `(490,494,1)`). It does not replay the entire episode.

## Named dialogue without a portrait (service 76)

```text
arguments : speaker_ref:s16, text_ref:s16; extra words ignored
texts     : packed strings or dynamic slots, with substitutions on BOTH
panel     : existing dialogue panel 3, presentation mode 3, theme -1
speaker   : explicit substituted string; not an NPC ID or narrator selection
portrait  : none; visible character -1, expression 0, no relationship change
input     : ordinary progressive reveal, then paging and final acknowledgement
result    : 0 on final acknowledgement; no UI result-cell write
```

Dispatcher `0009fe3c`, case `0x4c`, finds panel type 3 and calls
`000ab344(panel,3)`. That selects the layout's mode-3 name area and invokes
`000ab048(panel,-1,0)`, clearing the visible character and selecting theme -1.
The dispatcher resolves both strings with `0009f9fc`; `000aa028` writes the
speaker at panel `+0x3c`, `000a9f84` writes dialogue at `+0x30`, and `000aaf84`
starts the ordinary display. The host wait flag at `+0x84` retains the whole
VM frame until the final callback. SHS service 15 shares this native display
tail, with the additional argument-prefix rule documented below.

This is the shared group-speaker path used by Football Star at scene 25011,
PC 4303 (byte offset 58996), with arguments `(20059,20064)`: speaker “The team”.
The later call at PC 4311 uses the same service. No scene number, PC, group
name, result, branch or dialogue text is hard-coded into the host handler.
The first argument is always a text reference; service 13's negative mode
prefix does not apply here. Reference -1 resolves to an empty string, including
an empty speaker, without turning this screen into narrator mode 4.

The panel keeps its background and uses the normal, full-width dialogue body
without a portrait indent. Theme -1 selects the yellow `PajamaHipY26` name
font, gold dialogue skin and `ArialRoundedMTBold16` body. Existing backtick
color state survives, so emphasized text follows the preceding theme's palette.
`000a8544` includes a display-only spacing rewrite for “The team”, already part
of the shared speaker layout. No character's stored name, expression, art or
relationship cache is modified. See [UI_FIDELITY.md](UI_FIDELITY.md#speaker-labels-and-persistent-font-state)
for the persistent name-font inputs and the runtime's explicit ink-fit limit.

`000aaa40` uses the same portrait exit, name fade, reveal delay and one-shot
dialogue wobble as other dialogue calls. Moving from an NPC to service 76
shrinks the outgoing portrait; two consecutive group-speaker lines both have
character ID -1, so changing only the speaker string does not create another
portrait/name entrance. An early tap finishes text reveal without resuming the
VM. Additional pages retain the call, name layout and box geometry. The final
acknowledgement returns zero through `000a9868`'s virtual completion path.

The dialogue vtable at `002975b8` places `000ab8b8` at offset `+0x44`, confirming
the shared transition wrapper used by title and message panels. A queued
service-16 selector is consumed only after the final page. Selector 20 consumes
one `lrand48` draw; other selectors consume none. The runtime clears the selector
and resumes with zero, leaving UI result cells unchanged. This correction applies
to ordinary services 13/65 as well as 76. SHS now retains the nonvisual
outgoing/wakeup/incoming tick boundaries; CoD uses its own visible fades.
The result is retained once until the covered callback, including saves and
debugger pauses. See [the transition audit](UI_FIDELITY.md#2026-10-15-presentation-audit).

### SHS service 15

Service 15 uses the same explicit speaker, no-portrait presentation, text
reveal, pagination and final callback as 76. If its first word is negative,
that word is ignored and the following two references supply speaker and body.
Otherwise the first two words are the references. Remaining words are ignored
but stay in the pending frame and are removed on final acknowledgement. Even
prefixes `-2` and `-3` do not add parentheses or backtick emphasis; those are
service-13 rules, not service-15 rules.

The Android branch at `000a1bd4` compares the first word with zero at
`000a1c10`, chooses one-based indices `(1,2)` or `(2,3)`, and joins the
service-76 display tail at `000a1460`. SHS iOS agrees: case `0006f8d8` sets
speaker type 3, compares the first word at `0006f928`, selects its first text
index at `0006f930`, and increments that index for the body at `0006f974`.
Ghidra's pseudocode omits those iOS index arguments; the MCP assembly and raw
bytes at `0006f918` confirm them. The Android bytes at `000a1c04` were checked
as well. No separate iOS presentation is introduced.

The imported SHS corpus contains 396 service-15 calls in 62 episodes, with
four to seven frame words. All first words can be recovered from immediate
pushes: 386 are nonnegative text references and ten are the `-3` prefix.
The parser also accepts the native two-reference minimal forms and rejects
incomplete or invalid text references without consuming the frame.

### Saves and verification

No new save fields or version are needed: services 15/76 use the existing panel,
speaker-font history, `dialogue_animation` and pending dialogue schema. Current
saves check both strings against the retained VM arguments and require the
mode-3, no-character/no-relationship configuration. SHS service 15 validation
selects the references using the same prefix rule as live dispatch. Partially revealed and
paginated saves keep their clock and byte offsets.

An older `unhandled_yield` save at SHS service 15 or service 76 dispatches only that validated
pending call. It does not replay preceding bytecode, choices or random draws.
Such stops discarded their dialogue animation but retained the previous panel;
its character/art identity supplies the outgoing portrait for the new entrance.
The name-font bank is advanced once for the group label. The player's save file
is not rewritten merely by loading it.

Authored tests cover fixed/dynamic argument counts, ignored extra words,
substitutions, empty/dynamic strings, portrait-to-group and group-to-NPC
transitions, repeated group speakers, pagination, exact saved-state restoration,
invalid frames/saves, and transition random draws only on final acknowledgement.
Optional player-content tests render the reported original call, pause/resume
and resize it, then reach the following Coach and team lines. A private local
checkpoint check preserves the complete VM and both random streams while
upgrading the reported stop, and reaches the subsequent service-91 loading
screen at PC 5134. These are bounded checks, not a complete episode playthrough.

Additional optional checks isolate original service-15 callers without a prefix
and with a negative prefix from the supplied Spartan Games, Part 2 and Party
Fowl episodes. Each restores an old unsupported stop with unchanged VM and
random state, renders with both APK and IPA assets, and reproduces the same
pixels after saving/loading. The original inputs remain private and are not
test fixtures. Authored tests cover both call encodings, skipped prefixes,
ignored words, invalid references, paging, save validation, outgoing portraits
and transition randomness.

## Message panel (service 33)

```text
arguments : title_ref:s16, body_ref:s16, retained_argument:s16
texts     : raw packed strings or dynamic slots; NO substitutions
gate      : 1000 ms of active time, independently of retained_argument
input     : acknowledgement after gate; earlier input is ignored, not queued
result    : 0 on acknowledgement; no choice-result cell write
```

Dispatcher case `0x21` constructs UI type 2 through `000ad208`, passes raw
strings from `0009f420` to `000ac73c`, attaches it, and retains the VM's whole
argument frame. The compatible host requires at least three words; additional
words are ignored and removed with the frame on completion. This is a generic
message service, not a minigame result or an episode-specific exception.

`000ac73c` copies both texts, stores a3 at panel `+0x54`, and writes **1000**
to the countdown at `+0x50`. `000acb18` subtracts elapsed milliseconds.
`000abb3c` ignores input while the counter is positive. Elapsed time alone
does not dismiss the screen. The normal acknowledgement path `000ab7fc`
marks both callback and removal flags; virtual callback `000a6448` calls
`0009e888(host,0)`, which removes the pending arguments and puts zero in R.
The panel hides dialogue art, preserving the underlying logical dialogue and
background state. There is no score, audio request or result-cell mutation.

On iOS the panel is `SHSUIForm` (`desktop_message_hd`): the dialogue's bubble, the form's body rows, the
dialogue's title layer and its continue pill. SHS HD draws it from HD's bank; Cause of Death runs the same code
(1.4.7 `SHSUIForm::initForm` 0004f054 matches HD's instruction for instruction) on its own bank, whose layouts
24 / 25 / 27 / 3 are HD's at exactly half size (`CodMessageRenderer`). CoD's art is its own: the gray box, pack
126's rows and gray pill (frame 5). Its title and message are black, as in the owner's photo of the "Thanks for
playing!" panel, where SHS HD's are blue.

zazatree's lighttouch recording of an episode's end shows how CoD opens it, and the player follows:
- The panel stands on black at once. The scene picture fades out under it, and the last dialogue (name, text,
  portrait) fades out over it, in about 0.25 s: the location layer's default-ease fade (`Desktop._location_change`,
  `_panel_handover`). Natively the form leaves the location layer visible (`setLocationHidden(false)`); what
  clears it is not decoded.
- The pill grows in over 0.25 s (`GameModel::expandContinue`, as in SHS HD).
- The title fades in over 0.25 s. Natively it is the dialogue's title layer, given new text and moved from the last
  speaker's name plate with implicit actions on, so it also glides there; the glide is not modelled.
- The dialogue's bubble is reused and resized natively. The player fades the last dialogue's whole box out over the
  panel instead, which shows the old box over the panel for about 0.1 s.

Tapping Continue once the wait is over plays CoD's click (8005, owner's report); the episode exit that follows
stops the story's effects but lets that click finish. Without CoD's layout bank the player falls back to the
Android panel (`desktop_message.MessageRenderer`), drawn at story density with CoD's black ink. The photo reads about
8 levels darker than the game's art throughout (fill 230 against 238); taken as the capture's.

The shared callback wrapper `000ab8b8` first consumes a queued service-16
screen-transition selector. `0007f1a4` maps selector 20 to 1/2 using exactly
one `lrand48()` call (`1 + (value & 1)`); other nonzero selectors do not draw.
`0007efe8(...,4)` clears the queue and `0007f0e8` advances to the callback on
the next active update. The runtime preserves the random draw and queue clear
before resuming. The outgoing transition's composition and frame ordering,
and consumption by other panel types, remain fidelity work. Title and ordinary
dialogue panels now use this same completion path. In particular,
this random stream is also used when the next word game deals its options.

### Presentation

`000abd0c` constructs the body from layout 24, the heading from layout 15,
and the vertically flipped bottom cap from layout 25. `0007fabc(...,1)`
selects blue skin 204, with common image pack 126. Original layout sizes and
image alpha are retained. `000ac4dc` centers the background at GL `(160,240)`.
The body sprite is centered there as well. Its height for native episode ID
zero is explicitly `layout24.width - 40` (240 pixels in Android 1.0.9).
This applies to built-in Football Star regardless of its imported filename.
Other episode IDs use the expanded layout height. The heading sits immediately
above the body with a two-pixel overlap; the bottom cap sits below with the
same overlap. The native drawing path uses these separate sprites even when
the earlier layout-measurement path selected a taller header.

| Text | APK bitmap font | Nominal height / gap | Alignment |
| --- | --- | --- | --- |
| Heading | `ArialRoundedMTBold20` | 10 / 7 | 10: center, no automatic wrap |
| Body | `ArialRoundedMTBold16` | 10 / 3 | 21: top-left, wrap at layout width minus 25 |
| Continue / Wait | `TrebuchetMS_Bold14` | 16 / 5 | 5: top-left |
| Footer hint | `ArialRoundedMTBold11` | 11 / 0 | centered in the footer |

Heading/body RGB is `(41,104,221)`. Heading scale is 1 for fewer than 31
Latin-1 bytes and 0.88 otherwise. Explicit body newlines survive. The body
label retains layout 24's original height even when its parent expands.
The built-in body's line origin is 15 pixels below the sprite's top. For
nonzero episode IDs the child-node calculation gives top-origin Y equal to
the expanded sprite height plus half the original layout height. These
unusual coordinates come from `000abd0c`, not automatic vertical centering.

`000aca28` uses localized string 29 when ready; otherwise string 30 followed
by `" (" + ((remaining_ms+900)//1000) + ")"`. The native rounding can display
zero briefly before input unlocks. `000acc28` grows the shared continuation
node from 0.001 to 1 over 250 ms at X 245, on the bottom cap's lower edge.
The child artwork is common frame 5; its text node is at local `(-6,8)` with
size `(40,0)` and anchor `(0.5,0.5)`. Footer strings are 39 during the gate
and 36 afterward. Any screen acknowledgement works; desktop Enter/Space
provide the same action. The gear and loss of focus pause the active clock.

For nonzero episode IDs, `000ac73c` measures the body with font
`ArialRoundedMTBold14`, height 14/gap 5, at layout node 24's width. It adds
one plus a legacy font-origin field at application `+0x3a474`, rounds to an
even height, then expands the root through `00058a54` without shrinking below
the layout minimum. Ghidra and an isolated ARM constructor check establish
that this field is **uninitialized**: `00092b3c` embeds the font at `+0x3a338`,
`0004d098/0004d020/0013ae04` leave its `+0x13c` untouched, and `000858cc`
never applies the height setter to that font. Other fonts' `0004c7b8` calls
do not establish a value for this one. The renderer deliberately uses zero
instead of reproducing an arbitrary heap value. Built-in Football Star's
fixed height does not depend on it.

Bitmap history follows `000abd0c`'s title/body constructor assignments,
`000acc28`'s initial Continue caption and `000acb18`'s changed-caption/footer
updates. Measurement and drawing do not advance it. Pixel-level confirmation
against an original recording and unmodeled global font updates retain the
limits in [UI_FIDELITY.md](UI_FIDELITY.md#bitmap-history-and-reused-portrait-follow-up).

### Saves and verification (version 9)

```text
engine.message_panel : null | {
    title: Latin-1 string,
    text: Latin-1 string,
    argument: s16,
    elapsed_ms: integer in [0,1000]
}
pending : {name: "message_panel", details: {}}
```

Load validates the panel's text/argument against the retained VM frame and
rejects an absent or mismatched panel, invalid time or extra state fields.
The native binary's own panel loader resets its counter to 4000; these JSON
saves use the compatible engine's format and preserve the actual remaining
reading time. Older JSON versions gain a null panel. An older unsupported
service-33 checkpoint dispatches its retained call once, without re-executing
earlier instructions or consuming randomness on load.

Football Star scene 25011, PC 629 passes `(3016,3023,4000)`: its Instructions
panel before the thinking-word game. Confirmation reaches service 71 at PC
638 through the original bytecode. Authored tests cover both yield encodings,
raw/dynamic/empty strings, extra arguments, gate boundaries, the zero callback,
unchanged result cells, transition randomness, save/load and malformed saves.
An optional player-content test covers the reported instructions and desktop
rendering, mouse input, focus/menu pause and restoration. A private checkpoint
reached through the full football match also verified this transition.

## Dialogue panel close (service 39)

```text
arguments : none read; any supplied argument words are discarded on completion
target    : current dialogue panel, native UI type 3
result    : 0, immediately; no input callback or additional timer
effect    : retire that panel's presentation state
```

Dispatcher case `0x27` looks up panel 3 through `FUN_0007dff0`, then calls
`FUN_000a7cd0`. That helper sets the byte at panel `+0x0c` to 1. The panel's
virtual slot `+0x30` points to `0x000a63e0`, which reads that byte. Scene update
`FUN_0007feac` checks it and removes the panel through `FUN_0007fd28`, calling
deactivation, cleanup and destruction. This flag is separate from the callback
flag at panel `+0x0d`; service 39 does not suspend the VM for user input.
The ordinary dispatcher completion returns zero and removes the entire pending
argument frame. It does not choose or schedule another script.

The compatible host clears the dialogue panel's background, speaker, text,
portrait and animation state, plus its active/queued notice (service 88 stores
the queued text at panel `+0xf0`). A subsequent panel starts without an outgoing
portrait or stale speaker name. Character definitions, relationship properties
and caches, other numeric/string state, result cells, randomness, audio requests
and scheduled scripts survive. The scene-owned badge and queued wobble survive
as well; services 90 and 89 store those outside the dialogue panel.

Native removal happens in the scene update or the cleanup at script HALT
(`FUN_0007e4c4`). The runtime retires the panel during dispatch, before its next
presented screen. The full native panel stack and ordering of several panel
operations within a single frame remain a fidelity boundary.

Football Star scene 25013 issues service 39 at PC 13, then HALTs at PC 14.
The existing LIFO schedule determines what runs next. Saves retained at the
previously unsupported call are validated and resumed through the handler on
load, then execute normally to the next stop. No prior choices or random draws
are replayed, and save version 6 needs no new fields.

## Portrait selection (service 78)

```text
arguments : [prompt_reference:s16, count:s16, characters_address:s16]
characters: copy of count signed VM words at characters_address
order     : [0, 1, ..., count-1]          # original array indices
result    : order[0], on confirmation only
side effect: UI result cell 0 = result
```

The factory constructs UI type 5 with `FUN_000d2cb8` and passes substituted
prompt text and copied character IDs to `FUN_000d2238`. That function initializes
the five inline index slots at panel `+0x70`. Supported count is 1–5. Unreadable
words and invalid counts fail explicitly, retaining the pending VM call.

`FUN_000d1d78` swaps `order[0]` with the touched slot and swaps its portrait
widget pointer. `FUN_000d1b48` returns the first **index**, not a character ID.
`FUN_000d2008` selects on touch release; touching the central portrait does
nothing. Confirmation is separate, and the initially selected first portrait
can be confirmed immediately. Selection does not mutate VM memory, set the
result cell, or resume execution. Confirmation can occur during a swap.

### Geometry and motion

The native logical display is 320 × 480. `DAT_0025b830` holds these GL centers,
and `DAT_0025b81c` holds scales. Top-origin values are used in the renderer.

| Slot | GL center | Top-origin center | Scale | Opacity |
| --- | --- | --- | --- | --- |
| 0, selected | (160,205) | (160,275) | 1.0 | 255 |
| 1 | (52,239) | (52,241) | 0.6 | 91 |
| 2 | (115,310) | (115,170) | 0.6 | 91 |
| 3 | (206,310) | (206,170) | 0.6 | 91 |
| 4 | (269,239) | (269,241) | 0.6 | 91 |

Hit circles are fixed to these centers, radius `61 * scale`, even while widgets
move. When either swapped widget has no running action, both move to the other's
current position in 50 ms, scaling to 1.0/0.6; opacity is assigned by current
slot as `int(scale*scale*255)`. If both are moving, indices still swap but new
motion is not started. State retains per-character motion, independently of
render frequency. Selection and confirmation request sounds 8013 and 8010.

`FUN_000d2238` reads layout 47 but overrides the root to `(0,120,320,240)`.
`FUN_000d2558` uses the first supplied character's property 651 for its skin.
Portraits each use expression zero, mode 1, common selection frame 43/44,
the original mask 268, and the native 12-row portrait crop. Nonselected portraits
are deliberately faded. There is no invented character name or option text.

The prompt uses the existing `DAT_002ae910` PajamaHip26 node at GL (180,390),
size 300 × 45, nominal height 16, initial gap -16, white modulation. The
checkmark is common frame 41 at GL (240,111). Its release hit regions combine
the native explicit rectangle and transformed sprite rectangle. Footer text
comes from string-bank 13 entry 37. Desktop keys 1–5 select original indices;
Enter/Space confirms. The gear pauses motion; focus loss cancels a pending
pointer gesture. Subpixel rasterization and the native pressed-checkmark tint
remain presentation refinements.

Homecoming Queen, scene 25003, PC 303 passes `(426,5,6262)` with character IDs
`[0,29,30,31,32]`. Tests verify all five original results: art groups 26000,
26005, 26010, 26015 and 26020 are assigned to character 0 by the original script,
then the dialogue at PC 319 runs. A save at the older unsupported stop migrates
without replaying earlier choices.

## Formatting and packed strings (services 0, 24, 25, 28)

Service 0 uses `FUN_0009f5cc(host,0)`:

```text
if a1 >= 0: destination_slot=0; format=t(a1); values=a2...
else:       destination_slot=1-a1; format=t(a2); values=a3...
scratch_slot_10 = ""
scan format left to right:
    %c -> low byte of next word
    %d -> decimal signed 16-bit next word
    %s -> raw t(next word), with no variable substitution
    other bytes -> literal, including unrecognized percent pairs
destination_slot = scratch_slot_10
return 0x7ff5 + destination_slot
```

The format is copied before clearing scratch slot 10. Scratch updates as bytes
are appended, so a `%s` referencing handle 0x7fff observes the partial output.
For example, scratch containing `A%sB` formatted with itself as the `%s` argument
produces `AAB`. There is no printf `%%` escape: unrecognized `%` bytes remain
literal and the following byte is scanned normally. Extra arguments are removed
with the original frame but ignored by formatting; missing required arguments
fail. Destinations are bounded to the eleven known slots (0–10); selector -10
and below are rejected instead of writing past native storage. Width/precision
modifiers are not invented. Service 22 has different scanning behavior and
remains unsupported.

Service 24 compares two raw texts and returns 1 for equality, otherwise 0.
Service 25 copies both raw texts, concatenates them, and writes to the first
argument as a **VM word address**. Overlapping source/destination ranges work
because both source strings are read first. A dynamic-slot handle is valid as
a source but cannot serve as the destination.

### Copy last input (service 28)

Service 28 copies the last confirmed text-input string (`host+0x54`) to a VM
word address. Services 25 and 28 share `FUN_00056b78`: high byte first, through
the first NUL, including a zero terminator. An odd total byte count is padded
with another zero; bytes after the written words remain untouched. Empty text
writes a zero word. The runtime validates the entire writable extent before
changing memory and preserves signed word representation. Destination capacity
inside a valid VM region remains caller-managed, as in the original.

## Name entry (services 17 and 40)

These services retain their argument frame while displaying the substituted
title, prompt, and default. A confirmed name goes to dynamic string slot 0
and host last-input; callback `000d3f5c` returns `0x7ff5` without changing a
numeric result cell. Typing accepts at most 16 ASCII letters/digits and
lowercases uppercase letters after the first. Before appending, the existing
name's width plus cursor width must be less than 240 logical pixels, measured
with the supplied bitmap fonts. Empty Return never completes the call.

The same limits apply to programmatic confirmation, without recasing the
complete supplied value. Rejected values leave host and VM state unchanged.
Desktop drafts survive save/load as explicitly validated strings; alerts and
cursor state are transient. See [NAME_INPUT.md](NAME_INPUT.md) for the native
layout, keyboard, alert, callback, and verification details.

## Randomness and numeric bits (services 27, 50, 51)

Service 27 returns zero without drawing when its signed bound is nonpositive.
Otherwise `FUN_0009ea28` calls `FUN_0004c1bc` and returns the absolute signed
remainder by the bound. It shares the saved native LCG stream with grids and
football, described in [MINIGAMES.md](MINIGAMES.md). This is separate from the
choice panel's libc lrand48 stream. The exact historical seed of a user's old
native installation is not recoverable.

Services 50 and 51 share the numeric map used by services 44/45/52/53/54/55.
The map value is a signed **32-bit** integer; ordinary setters sign-extend
their argument and ordinary VM getters narrow their return to 16 bits.
The key remains `(s16(owner)*65536+s16(key)) mod 2^32`.

```text
50(owner,key,bit,value):
    shift = bit & 255
    mask = shift < 32 ? (1 << shift) : 0   # ARM register LSL
    map[key] = value == 1 ? map[key] | mask : map[key] & ~mask
    return 0
51(owner,key,bit):
    return (signed32(map.get(key,0)) >> (bit & 255)) & 1
```

The getter uses arithmetic right shift, including sign fill for counts >=32.
Exactly 1 sets a bit; every other value clears it. Evidence: `FUN_000965bc`,
`FUN_00095ca0`, and the common setter `FUN_00096474`.

## Dialogue notifications (service 88)

**Presentation scope:** the implemented rising-letter animation below follows
Android 1.0.9. It is currently used for IPA imports too and is **not 1:1 with
the original iOS notices**. SHS `SHSPortraitLayer::startLetterEffectAnimation`
**0006cc48** delegates to `SHSUIDialog::startLetterEffectAnimation`
**0007eb64**; CoD has corresponding paths **00043bc4 / 00035954**. The iOS
routine builds separate letter layers and position, bounds and opacity
keyframes, including a size overshoot. Those tracks still need implementation
and original-device comparison. The Android evidence below must not be read
as verification of the iOS effect.

CoD's notice **colors** do follow its native theme selection: theme 1 red
`(240,81,60)`, theme 2 rose `(180,78,78)`, theme 3/default black. See the
[CoD font evidence](COD.md#native-ui-and-audio-bindings). These are supplied through the
game adapter, preserving SHS's red atlas. CoD still uses the compatibility
26-point name face and outline here; its native notice uses 20-point
Trebuchet Italic/Bold and separate stroke layers. Color correction does not
establish native notice typography or animation parity.

```text
arguments : text_ref:i16
result    : 0, immediately; no notification callback
queue     : one substituted Latin-1 string, panel 3 +0xf0
consumer  : next dialogue presentation (000aaa40)
```

This is the common path for stat changes, grades and upgrade messages. The
Football Star scripts use it for Strength Up, Popularity Up/Down, +1 to Grades,
and the block/running/pass upgrades. There is no stat-name lookup in the
renderer. Scripts change numeric properties and request sounds separately;
service 88 itself changes neither stats, result cells, audio nor randomness.
Repeated calls replace the queued string. Substitution happens when queued,
not when displayed. An empty string clears the queue.

The supplied Football Star's early running-choice Strength Up notice
(scene 25006, PC 206) has no accompanying service-79 request. Its word-grid
Strength Up reward (25011, PC 167) explicitly requests 8007 at PC 165.
CoD's supplied Volume One uses 8002 for positive score feedback, including
the Detective Score Up notice in scene 25008. These are ordinary PCM WAV
resources in the supplied IPAs. The iOS simulator probe verifies both cues
through the shared choice/script/notice path and checks actual AVAudioPlayer
playback, including a choice click in the same input batch. This does not
establish which specific silent moment a physical-device report refers to.

The next dialogue consumes the queue, creates the notice immediately and
starts its own active-time countdown. The additional animation-delay arguments
passed by `000aaa40` are unused by `0009c814`; the notice does not wait for the
portrait or body-text reveal. Its node is attached to the current portrait
parent at child/z-order tag 25000. It is a sibling of the scaled head, so it
does not inherit that head's entrance zoom or horizontal flip. A hidden
portrait parent (narration or missing character art) also hides the notice.

### Typography and placement

`0007cbbc` constructs the notice label `002ae924` with font-registry entry 14,
`PajamaHipS26.fnt`, nominal height 16 and extra line gap 5. The font's red
lettering and white outline come from the player's APK atlas. `0009c814`
sets RGB to white, preserving those baked colors. It sets the label scale to
1 for fewer than 19 source bytes, and 0.88 otherwise. Alignment 5 is top-left,
with explicit newlines but no automatic wrapping or emphasis markers
(`0004de48` / `0004dc20`). Existing font advances, offsets and kerning apply.

In native GL coordinates the notice starts at `(-60,50)` relative to the
mode-1 portrait parent, or `(-260,50)` for mode 2. The parent center comes from
layout 17 rectangle 0x30 or 0x4e, with `000aaa40`'s `485-y` conversion. In the
runtime's downward coordinates, for portrait rectangle center `(cx,cy)`:

```text
notice_origin = (cx + (-60 if mode == 1 else -260), cy - 55)
glyph_left    = notice_origin.x + scale * font_layout.glyph_left
glyph_top     = notice_origin.y + scale * font_layout.glyph_top - rise(i,t)
```

The label has zero content size, so its half-width/height anchor adds no
translation. These positions are evaluated on the native 320×480 dialogue
canvas before scaling to the desktop window. The notice is drawn with its
portrait, rather than over unrelated panels or the host menu.

### Letter entrance, exit and input

`0009c814` starts every letter's linear `MoveBy(0,40)` simultaneously. Drawn
child index `i` has duration `30*(i+1)` ms: the first letter finishes first,
making a rising wave. Child tags count non-space glyphs across lines
(`0004d3f8`), independently of source-byte indices. Spaces and newlines still
contribute to the overall display lifetime.

For source length `N`, the scheduling variable starts at 30 ms and is
incremented after **each** source byte. The exit therefore starts at
`165*(N+1)` ms, not `165*N`. `0009c7c8` invokes `0009c750` once; the label then
fades from 255 to 0 and moves upward another 50 units over 300 ms. The linear
action updates are verified at `00136364` and `001365f4`.

```text
exit_start_ms = 165 * (N + 1)
lifetime_ms   = exit_start_ms + 300
exit          = clamp((t - exit_start_ms) / 300, 0, 1)
rise(i,t)     = scale * 40 * clamp(t / (30 * (i+1)), 0, 1) + 50 * exit
alpha         = trunc(255 * (1-exit))
```

`000a9868` hides the notice at the beginning of dialogue input, including a
tap that only completes the reveal or advances to another page. This does not
bypass either input gate or resume a still-revealing VM call. Service 39 also
clears active and queued notices when closing the panel. Expiry alone does
not acknowledge dialogue or generate a game result.

The existing save fields are sufficient: `next_dialogue_notice:string`,
`notice:string`, and `notice_ms:int` (remaining time, including the fade).
An empty active notice requires zero time; otherwise time lies in
`[0,165*(N+1)+300]`. Elapsed motion is derived from that countdown. Rendering
does not advance it, and the desktop excludes menu/unfocused time. Older
saves retain their shorter saved remaining countdown without changing VM
state; their motion is reconstructed from the corrected deadline. No save
fields or new save version are needed.

Authored tests cover replacement/substitution, unrelated stat/result/random
state, letter geometry, the long-message scale, fade, input/page gates,
save/load during each phase, malformed timers, pixel movement with an authored
font, and paused clocks. Local verification naturally completes Football
Star's service-96 encounter and reaches its service-88 Strength Up notice at
scene 25011, then renders the supplied assets at multiple animation times.
These are native-code and asset checks, not a running-original frame capture;
cross-label kerning history and native scheduler frame boundaries retain the
limitations described in [UI_FIDELITY.md](UI_FIDELITY.md).

## Scene label and dialogue emphasis (services 89, 90)

Service 90 is nonblocking. Its second argument is substituted text, or empty
when -1. Icon ID -1 removes the badge; otherwise the icon/text are retained.
`FUN_0007b97c` creates the badge from layout 67, a 171 × 60 frame 13 from the
theme pack. Initial text `Free Time` selects blue pack 204; otherwise pack 236.
Updating an existing badge retains its original skin and entrance progress.
Text color is (69,107,176) for `Free Time`, otherwise (223,163,52).

Layout node 2 centers the icon at (38,30). Android text uses ArialRoundedMTBold16,
nominal height 14, gap 1, content size 110 × 20; the native function has string-length and
named-label positioning exceptions, represented by `SceneBadge.text_position`.
The length-15-through-17 branch sets GL node position (123,55), taking
precedence over the later named checks. Its Y constant is `0x425c0000` (55),
not 46. This branch includes `Counselor's Office`.

Alignment flags `0x11` in `FUN_0004dc20` select wrapping with left/top
alignment. With the label's `(0.5,0.5)` anchor, GL position `(x,y)`, and scale
`s`, the downward origin inside the badge is `(x - 55*s, 60 - y + 10*s)`.
Every wrapped line starts at that same X. Text draws downward from the
label's local zero, so the half-height is added when converting to screen Y;
subtracting it clips the first line into the badge's upper border. The desktop
uses this native transform rather than centering the measured text block.

The iOS outline-font adapter instead uses **ArialMT 14**, zero added line gap,
and layout 67 node 3's **(68,15,98,30)** text region. SHS/CoD
`GameModel::render` **00022ba8 / 00011a1c** passes flags **0x19** to
`CSFont::drawTextInRegion`: wrap, left-align, vertically center. The font comes
from `setBubbleSex` **00023db4 / 0001143c** and `initFonts`
**0003c440 / 000230b8**. It is not the larger rounded Android bitmap label.
Applying the bitmap font role and offsets to outline fonts wrapped “Before
School” into the lower gold stripe. The shared renderer now applies the
verified region and cap-height line boxes to every outline scene caption.
If a substitute face's ink exceeds that region, drawing scales/translates
the complete label into it without changing its text or saved state. This
fallback fit is a compatibility guard, not an observed native font substitution.
Badge color selection and the common entrance placement/timing remain the
Android behavior above; iOS-specific color/entrance parity is not claimed.

The badge moves horizontally in 200 ms from center x=-85.5 to x=100.
Ad-free top inset is 10 (`FUN_0007d280`); the original ad-enabled path uses 55.
The desktop uses the ad-free placement. Authored-font rendering tests cover
single-line, wrapped and scaled labels and verify that drawing leaves badge
state intact. These placements are checked against the binary and supplied
assets; comparison with frames from a running original remains outstanding.

Service 89 sets scene byte +0x3f8 for the **next dialogue**, then completes with
zero. In Android, `FUN_000aaa40` consumes and clears it; `FUN_0007c9e8` rotates the dialogue
box independently of its text and portrait. Mode 2 starts at +20 degrees,
rotates to -20 in 70 ms, waits 2 ms, then returns to zero over 70 ms. Other
modes invert the direction and wait 5 ms. The changed-character text path
also omits its usual additional 120 ms delay. Page turns do not replay the
one-shot wobble.

New dialogue uses the owner-selected iOS presentation for both games: a
100 ms hidden hold (700 ms for a changed speaker), then a 125 ms scale from
0.5 to 1 and a 250 ms three-keyframe rotation. Text receives an additional
400 ms delay. Housing clipping follows successful shake completion; early
reveal cancels the box track. The existing -20/20 state values select the side,
not the iOS angle. Version-20 and older checkpoints keep their active Android
rotation until the next dialogue. See the recovered paths and exact keyframes
in [UI_FIDELITY.md](UI_FIDELITY.md#shake-and-reveal-input).

## Build and application query (service 70)

```text
arguments : selector:s16; any additional words are ignored
result    : signed word in R; removes the complete pending argument frame
effects   : no UI result-cell, string-slot, timer, audio or random-state writes
```

`FUN_0009fe3c`, case `0x46`, switches on the first argument. Its fixed results
are properties of the inspected Android 1.0.9 build. They do not change with
the operating system running the app.

| Selector | Native result | Runtime behavior |
| --- | --- | --- |
| 2 | 2 | Complete with 2 |
| 3 | 6 | Complete with 6 |
| 6 | `0x7ff5` | Return the existing dynamic string-slot-0 handle |
| 9 | 1 | Complete with 1 |
| 11 | Pointer identity comparison described below | Explicit pending stop; no fabricated result |
| Every other signed-word selector, including 10 | 0 | Complete with 0 |

Selector 6 does not initialize or replace dynamic slot 0 and does not copy
`last_input` into it. The returned handle refers to that mutable slot just as
other `0x7ff5` handles do. The meanings of the fixed numeric selectors are not
assigned speculative names such as platform, locale or API version. Unknown
service IDs still stop; this zero-default rule belongs only to service 70's
verified selector switch.

Football Star scene 25001 issues selector 10 at PC 222, byte offset 3451. The
preceding instruction at PC 221 pushes 10. After completion, the original
instructions push R and 2, compare for equality, and branch on zero from
PC 226 to PC 234. Returning the native zero therefore permits the original
script to choose its path; the runtime does not replace the branch or seek
past the service.

### Native application identity boundary

Selector 11 compares the object pointers at application `+0x68ed4` and
`+0x6ab24`; it does not compare EXP titles or numeric pack/episode IDs.
`FUN_0008dcc8` installs the active episode in the first field. The second is
the separate episode slot populated by `FUN_0008e18c` in application state
108, following the native weekly-episode flow. `FUN_0008c184` restores an
expansion save by looking in the ordinary episode collection, then falling
back to that separate object if its numeric identity matches.

The compatible launcher imports local files and does not model the native
weekly-download slot or its identity/lifetime. A local episode's imported
status, bundled status, selected filename or largest episode ID cannot safely
stand in for that comparison. Selector 11 therefore retains its full VM
frame as `unhandled_yield`, with the selector and reason exposed. It requires
further application-state modeling before it can return a faithful boolean.
See the [main-menu contract](MAIN_MENU.md#1-native-application-states-and-commands).

### Saved stops and verification

No save fields or format version change. A save at an unsupported service-70
call is restored through its validated frame. A fixed selector completes
once, then the VM runs its following instructions normally. Previous choices,
state writes and random draws are not replayed. If the stopped query followed
dialogue, the retained panel supplies the previous portrait identity for the
next dialogue entrance. Selector 11 remains stopped after restoration.

Authored tests cover all fixed outcomes, zero-default cases at the signed-word
boundaries, fixed/dynamic argument counts, extra argument removal, a live
slot-0 handle, unchanged host state, saved-stop recovery, dialogue continuity,
and explicit rejection of a missing selector. An optional original-content
check executes Football Star's PC 221–226 instructions and verifies the
branch to PC 234. This is an isolated call/branch check, not a replay of the
player's route to that point; original game assets are not test fixtures.

## Optional device request and native stub (services 82, 99)

`FUN_000a3040` requests 1000 ms from the optional vibrator, gated by device and
settings availability. The desktop has no vibrator backend and completes
without altering music, sound or saved state. In its place the desktop player
sounds a shorter synthesized buzz (400 ms, `vibration.BUZZ_MS`; not an original
asset) at the Sound FX volume while Sound and the Options Vibration switch (string 11,
`MenuState.vibration`, shown in this player though the iPad hid it) are on; the engine counts requests in the
unsaved `EngineState.vibration_serial`. Android's vibrator implementation is
constructed by `FUN_00102f1c` / `FUN_00108188`, using VibratorAndroidDelegate.

The iPhone host implements the separate native iOS contract: SHS
`SHSSoundManager::vibrate` **000762e8** and CoD **0004334c** check the engine's
vibration preference and device eligibility, then call
`AudioServicesPlayAlertSound(0xfff)`. This is Apple's
[`kSystemSoundID_Vibrate`](https://developer.apple.com/documentation/audiotoolbox/ksystemsoundid_vibrate),
not a custom one-second pattern. The actual sensation is controlled by iOS
and the device. SHS **00050e40** and CoD **00018c38** also invoke the alert
when their Vibration setting is enabled.

Options exposes Vibration when the Swift host reports an iPhone. It defaults
on for existing libraries and persists independently of Music and Sound in
`player.json`. The shared player consumes each live service-82 request once;
the transient request count is excluded from saves. Isolated choice previews
cannot emit hardware feedback. Disabled, paused or inactive requests are
discarded, and Swift rechecks application activity before calling AudioToolbox
on the main thread. A response from before a background/resume cycle is also
discarded. iPad and desktop receive no alert or substitute sound.
Simulator checks exercise the bridge and native alert ID/device/activity gates;
they cannot measure physical vibration.

`FUN_00082adc`, called by service 99, contains only two ARM instructions:
`mov r0,#0` and `bx lr`. This release therefore always takes the dispatcher's
normal completion path; no wait or host +0x118 state is introduced. This is
verified native behavior, not a general policy of ignoring unknown services.

## Save schema additions (version 5)

| Field | Contract |
| --- | --- |
| `engine.character_picker` | Null, or the selector model; required exactly when pending service 78 |
| `characters` | 1–5 signed character IDs copied from the pending VM arguments |
| `order` | Permutation of original indices; first entry is selected |
| `portraits` | One motion object per original character, independent of order |
| motion `start`, `end` | Triples of finite `(x,y,scale)` floats within the native positions/scales |
| motion `elapsed_ms` | Integer 0–50 |
| motion `opacity` | 255 or 91 |
| pending picker `details.text` | Substituted prompt, checked against its retained VM frame |
| `engine.scene_badge` | Null or `{asset_id:s16>=0,text:string,blue:bool,elapsed_ms:0..200}` |
| `engine.next_dialogue_wobble` | Boolean, consumed by the next dialogue |
| pending dialogue `details.box_wobble` | Optional boolean; absent in older saves |
| `engine.dialogue_animation.wobble_direction` | -20, 0 or 20; uses existing elapsed clock |

Older versions migrate missing fields to null/false/zero, preserving choices,
random states, pending frames and page/reveal progress. Older unsupported
service-78 stops are initialized from their original arguments. Renderers do
not write VM results or advance clocks. Pausing/focus loss stops active time.

## Offline surveys (service 9)

```text
arguments : poll ID, upType, upValue(s), upSize, resultsType, results buffer, resultsSize (s16 each)
supported : upload type 2 and the verified not-uploaded response below
questions : original service-1 choices, including the option to decline
receipt   : Survey / Thanks for taking the survey!
input     : 1000 ms active reading time, then acknowledgement
result    : 0 (not uploaded); no aggregate result or UI result-cell write
resume    : execute the original remaining story; no forced episode exit
```

This is an owner-requested offline compatibility feature, not a recovered
Android upload callback. Android 1.0.9 disables this path: dispatcher
`0009fe3c`'s service-1 branch exits through `0007e614` when the description
contains the optional-survey invitation. Service 9 itself calls `0009f0cc`,
which reads only the first two frame words, constructs `pollID=...&upType=...`,
discards that temporary string and returns `EMPTY`. The dispatcher calls
panel helper `000a7cdc` and sender `0007b448`, then sets the host wait flag.
The sender is an empty function; this binary provides no submission response.
The runtime deliberately permits the script's ordinary opt-in and question
choices and completes the survey locally, as requested by the owner.

The audited local library contains 235 service-9 calls across 232 episodes.
All use seven arguments and upload type 2. Their result handling branches on
R=1: success shows “Thanks for taking the survey!” and reads an aggregate
buffer to display server poll percentages. The other branch shows service 65
with “Connection failed. Please try again later.”, then rejoins the remaining
story. Returning success without server data would fabricate a result and
read uninitialized memory. Offline completion instead uses R=0 and replaces
only that known connection-error notice with the script's thank-you wording.
The unused submission words are preserved, never dereferenced or populated.

At dispatch, `survey.script_response` copies the VM and runs at most 128 KiWi
instructions with the not-uploaded result. Its first stop must be service 65
with exactly three arguments and the exact connection-error text above.
Another host service, pause, instruction limit, VM error or unfamiliar text
leaves an explicit unsupported stop with the original frame and live state
intact. The probe does not dispatch host services or consume either random
stream. It identifies the actual response frame rather than hard-coding an
episode, scene number, PC or jump target.

While the local receipt is visible, the original submission remains pending.
The receipt reuses the service-33 blue message panel, supplied bitmap fonts,
Continue control and one-second reading gate. Its title and use of this panel
are explicit offline presentation choices, not evidence of an original survey
screen. Menu/focus pauses and save/load preserve active time. No network
request is created.

On acknowledgement, the runtime rechecks the continuation, resumes service 9
with 0, and executes the actual instructions to the verified service-65 frame.
It presents that response internally with the replacement text and completes
its ordinary dialogue callback once, since the player already acknowledged
the receipt. This retains speaker/panel state and any queued transition's
random draw without showing a second notice. Subsequent script instructions,
choices, ending messages and native episode exit execute normally. Original
bytecode and text resources are unchanged; no server percentages are supplied.

Save version 13 adds pending `survey_confirmation` with only
`details.response_pc`, using the existing `engine.message_panel` fields for
the exact receipt and reading time. Loading checks both against the retained
service-9 frame and the copied VM's verified continuation. Earlier unsupported
service-9 saves recover by dispatching only their retained call. Questions,
choice result cells and previous random draws are not replayed.

Authored tests cover both call encodings, opaque arguments, the absence of
network activity and fabricated percentages, continuation into remaining
story, one callback, reading/input gates, save recovery and invalid or unknown
continuations. Optional local tests execute the original survey callers and
choices in Green With Kenji and 300's A Crowd, including declining, saved
submission recovery, their original ending panels and subsequent service-7
exit. A desktop check covers rendering, focus/menu pauses and pixel-identical
restoration. These checks isolate the original survey routines; they do not
establish complete playback of every surveyed episode.

## Loading overlay (service 91)

```text
service 91([wait: s16, ...]) -> R = 0
```

This is a timed application overlay, not a choice, download request, or arbitrary
acknowledgement. `FUN_0009fe3c` sets application `+0x6ac36` and opens the overlay
through `FUN_0008d43c`, using string bank 13 entries 31 and 35 ("Loading" and
"Please wait..."). It always sets host `+0x118`, which gates further VM execution.

The dispatcher reads `stack[SP - argc]` without checking the argument count.
For a nonempty frame this is its first argument; for a zero-word frame it is
the retained stack cell at SP. There is no implicit zero or supplied argument
in the latter case. Uninitialized backing remains an explicit runtime error.
Other supplied words are ignored by this service, but completion removes the
entire encoded frame.

The APK's `The_New_Girl.exp` calls service 91 with **zero arguments** in scene
25004 at PC 60. On the verified route, retained backing contains 407, so the
call waits with its empty frame intact. The imported `SHS_The_New_Girl.exp`
passes 1 at PC 61 instead. Both continue to the original word-grid game after
the overlay closes, including after saving and restoring during loading.

| Wait value | At dispatch | At overlay completion |
| --- | --- | --- |
| `wait == 0` | Pop the supplied argument frame (possibly empty) and set R=0 immediately | Release the host execution gate; do not pop again |
| `wait != 0`, including negative values | Retain the VM yield and its argument frame; set host `+0x84` | Pop the frame, set R=0, clear host wait/pause flags |

Neither branch writes UI result cell 0, changes relationship values, consumes
randomness, or schedules another scene. Both prevent the next VM instruction
from running until the overlay closes. `EngineAction.completed` remains false
while this application work is pending, even if its nonwaiting VM call has
already completed.

`FUN_0008e7d0` increments the application's floating-point millisecond counter
at `+0x6ac30`. `FUN_0009ea70` checks **counter > 3000**, overlay visible, and the
service-owned flag, then clears host `+0x118` and calls `FUN_000843c8`. That helper
resets the counter/visibility, restores application input, detaches both text
nodes and the loading sprite, removes the two panels, and clears the service
flag. The host updater then completes the retained frame if `+0x84` was set.
The `1500` argument visible at the constructor call is unused by that function;
it is not the completion threshold. Disassembly at `0x0008e8c0` confirms a float
addition, despite the decompiler presenting some counter stores as integer casts.

The session uses active integer milliseconds. At 3000 ms the overlay remains;
the next positive tick completes it. Save/load and foreground pauses preserve
the timer. Overshoot is not applied to the following mini game or screen.
Player acknowledgement is rejected. The desktop retains its host pause/save
shortcuts while the original loading overlay has no confirm or cancel button
in the in-episode application state.

Presentation uses user-supplied artwork and fonts:

| Element | Native binding / top-origin placement |
| --- | --- |
| Upper panel | Layout 50, 320×150, at (0,170); original blue skin 204 |
| Lower panel | Layout 22, 350×60, at (-20,287); node 13 and its subtree hidden |
| Title | Registry font 6, ArialRoundedMTBold20, nominal height 20, RGB (41,104,221) |
| Message | Registry font 5, ArialRoundedMTBold16, nominal height 15, width 300, same color |
| Animated icon | Common pack 126 frames 23–27, centered at (155,317) |

Android `FUN_0008952c`, `FUN_00177458`, and `FUN_00136a30` establish **500 ms per
frame**, five frames and a 2500 ms repeating animation. The original iOS games
use **70 ms per frame**, repeating after 350 ms: SHS `initLoadingBar` **0003da88**
and CoD **0001d4cc** assign float `0x3d8f5c29` (0.07 seconds) to each of the same
five frames. SHS `SHSAnimationLayer::finalizeAnimation` **0002b234** sums those
times for the animation duration. The shared renderer selects this cadence for
IPA imports and retains the Android cadence for APK imports, on both hosts.
Authored tests and the iOS probe cover frame progression, repetition and saved
clock restoration. CoD's runner evidence does not implement its still-unsupported
service-91 script contract.

This animation does not determine when the VM resumes. Download/cancellation
overlays reached from other native application states are separate contracts.
The desktop currently draws these
panels over the existing scene background; retention of underlying native
dialogue/widget objects across application overlays remains a fidelity detail.

## Save schema additions (version 6)

| Field | Contract |
| --- | --- |
| `engine.loading` | Null or `{blocking:bool, elapsed_ms:int[0..3000]}` |
| Pending loading screen | `{name:"loading", details:{}}`; completed register-count calls with argc other than 1 retain `details.argument_count` |
| Loading `vm.pending` | Retained service-91 yield for a nonzero wait value, including an empty frame; null for wait value zero |
| Dialogue `details.relationship` | Null or the `RelationshipChange` fields in [UI_FIDELITY.md](UI_FIDELITY.md#npc-relationship-indicators) |
| `engine.dialogue_animation.relationship` | Null or `{change:RelationshipChange, delay_ms:int[0..850], elapsed_ms:int[0..duration]}` |

For a zero wait value, loading a save validates the completed instruction
immediately before the PC, R=0, and the zero word still present at SP in stack backing.
It reconstructs the screen's request description without creating another VM
yield. Compact bytecode provides the original argument count. A completed
register-count call preserves non-one counts in `details.argument_count`;
absent metadata retains the legacy one-argument save contract. Arguments are
recovered from backing without inventing a word for an empty frame. A waiting
zero-argument save validates its wait flag against the retained cell at SP.
Both compact and register-count yield opcodes are supported. Timers,
pending-screen identity, native arguments and relationship cache correspondence
are checked before accepting the save.

Versions 1–5 receive null new state. An older unsupported service-91 checkpoint
initializes the overlay from its retained frame without replaying earlier script
instructions. Older dialogue saves retain their reveal/page progress; relationship
icons are initialized settled and their caches populated without replaying sounds
or inventing historical gain/loss animations. Original player files are not
rewritten just by loading them.

## Verification and remaining scope

Authored tests cover packed-string padding and overlap, invalid extents,
formatting/scratch aliasing, shared random replay, high-bit updates, sprite
selection versus confirmation, original index mapping, mid-motion saves,
legacy migration, original art, resized release input, and paused clocks.
Local tests exercise all five Homecoming Queen appearances and Football Star
through character creation and its first classes with the original scripts.

Football Star's service 91 at scene 25006, PC 1245 now completes into service 94
at PC 1270. The regression route plays both football halves through public
tap/tick input and returns to Howard's original dialogue. Authored tests cover
both loading argument forms, the strict timer boundary, retained/popped frames,
older checkpoints, malformed saves, original animation frames and paused input.
Relationship tests cover icon selection, counts, native cache writes and sounds,
staggered gains, falling losses, dialogue delays and exact mid-animation restore.
Extraction of all story scripts is complete; full eight-week playback is not
yet established.

### Vibration in the iOS games (service 82)

`SHSSoundManager::vibrate` (SHS HD `00053a68`, CoD 1.4.7 `00047054`) calls
`AudioServicesPlaySystemSound(0xfff)` (the system vibrate) only when the
player's Vibration option is on (`CSEngine::isVibrationEnabled`, +0x10) and
`isVibrateAllowed` (+0x20), which the constructor sets when the device model
name contains "iPhone". So CoD vibrated on an iPhone, and SHS HD, an iPad app,
never did (its Options hide the row, condition 8). Its episodes still make the
calls: 301 in the 194 reference HD episodes; 182 of the 186 with a standard
copy match it script for script (April Fools moves its 3 calls; A Very Tom
Prince Holiday, Bringing Home Christmas and The Storm Part 1 have fewer). This
player's buzz (PR #10) works in both games: the "Simulated Vibration Sound"
switch at the end of Options -> Sound, off by default, buzzing once when
switched on (`SHSEngine::setVibrationEnabled` calls `vibrate` the same way).
Real device vibration could later use the same calls and the games' own
Vibration switch (string 11).
