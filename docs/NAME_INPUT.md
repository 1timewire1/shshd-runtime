# Name entry: services 17 and 40

Reference: Android 1.0.9 `libshs09.so`. The user reports an identical
iOS/Android game interface. The renderer reads the player's APK; no original
artwork, font metrics, screenshots, or native code are distributed.

The Android contract below remains unchanged. IPA playback uses the inspected
iOS layout-46 panel and Pajama Hip 24 for entered text/cursor, with installed-font
fallback when necessary. Its UIKit alert uses the desktop message skin. See
[IPA.md](IPA.md#platform-specific-ui) for evidence and compatibility limits.

## VM and editing contract

Both services select UI factory type 15. `000d4440` stores the substituted
title, prompt, and default at panel `+0x84`, `+0x90`, and `+0x9c`. The call
remains suspended, with all arguments intact, until confirmation.

`000d3cb0` processes one typed byte:

1. Accept ASCII `A–Z`, `a–z`, or `0–9` only.
2. Require the current length to be less than 16.
3. Require the **existing name's measured width plus the cursor's measured
   width** to be strictly less than 240 logical pixels, before appending.
4. Lowercase a newly typed uppercase letter when the current name is nonempty.
   The first character's case and the supplied default remain unchanged.

The width fields are `state+0x518e8` (name label `+0x130`) and
`state+0x53030` (cursor label `+0x130`). They are unkerned advances, not an
inset or the proposed new string's ink bounds. Consequently a final accepted
character can cross the threshold. `00085b54` selects font registry entry 8
for the name, confirmed in ARM instructions where the decompiler loses that
argument. The cursor is registry entry 12. These details supersede the
initial approximations in `CONTINUING.md`; the caller's constant 20 is not
the interactive length limit.

Backspace removes the final byte. Return with nonempty text sets the submit
flag (`000d3de0`); the update handler `000d3ae8` invokes the callback.
Empty Return hides the virtual keyboard without resuming. Callback
`000d3f5c` copies the name to dynamic string slot 0 and host last-input,
then resumes with handle `0x7ff5`. It does not write a numeric result cell.

`text_input.py` supplies the pure character helper and confirmation validator.
`Session.answer()` rejects empty, non-ASCII, unsupported-character, overlength,
and overwidth values before changing any host or VM state. A programmatic answer
is a complete value, so it retains its supplied case; only interactive typing
performs case conversion. Both paths use the same APK font advances. Authored
headless fixtures without an asset loader exercise the byte/length contract
without a width measurement.

### CoD input policy

The supplied CoD 1.3.4 `SHSUITextEntry::tick` (`0003b5f4`, character filter at
`0003b682`–`0003b6b4`) accepts only ASCII letters/digits and handles Return
separately. The capitalization path at `0003b872`–`0003b89e` uppercases an
initial lowercase ASCII character and preserves subsequent case. Shared
desktop/iOS typing follows that CoD rule; programmatic answers retain their
exact supplied case, and SHS retains the Android rule above.

CoD additionally accepts ASCII spaces as a deliberate owner-requested
convenience. This is not required to solve the inspected puzzles: the cited
Volume One names trigger a wrong-guess branch, while Volume Four accepts
single-word alternatives. Spaces count toward existing length and width limits;
space-only answers, tabs, Unicode whitespace and punctuation remain rejected.
No trimming or rewriting changes the submitted string. `name_input_metrics()`
shares the space policy with typing, player confirmation and `Session.answer()`,
so the desktop and iOS paths agree with headless callers. Saved drafts preserve
their contents and remain subject to validation on confirmation.

## Screen composition

`000d4658` constructs the normal screen. `000d42f0` places its background
at GL `(160,300)`, or top-origin center `(160,180)`. All coordinates below
are logical 320 by 480 pixels, before Desktop's window scaling.

| Element | APK source | Native placement / resulting bounds |
| --- | --- | --- |
| Header | Resource 14, layout 15; image slots 0=126, 2=204 | Texture width = layout 46 design width + 22, height 50; GL center `(160,415)`; supplied bounds `(9,40,302,50)` |
| Footer strip | Resource 14, layout 43; slot 3=16 | Design-size texture; GL center `(160,267)`; supplied bounds `(9,191,302,44)` |
| Main white box | Resource 14, layout 46; slots 0=126, 2=204 | Width = design width + 22, height 156; GL center `(160,340)`; supplied bounds `(9,62,302,156)` |
| Entry shadow/slot | Numeric resource 706 | Native 260 by 40 image at GL center `(160,283)`; top-origin `(30,177)` |
| Title | `ArialRoundedMTBold30`, registry 9 | GL `(160,415)`, anchor `(1/2,1)`; blue; downscale only when measured width exceeds layout 46 node 18's width |
| Prompt | `ArialRoundedMTBold16`, registry 5 | GL `(30,360)`; nominal height 16, initial gap -16; blue |
| Name | `ArialRoundedMTBold28`, registry 8 | GL `(35,290)`; nominal height 26, gap -26; blue |
| Cursor | `PajamaHip26`, registry 12, glyph `\|` | Update position GL `(name width + 33,266)`; blue |

Blue is RGB `(41,104,221)`. Setup overrides the name's initially white color.
The header, footer, and main-box sprites have increasing z order. Layout 46
reference roots 1 and 10 are explicitly hidden, including their descendants.
Layout 43's button subtree is hidden by its default visibility bits. Geometry
queries still include hidden nodes.

Changing the title's anchor through `00165c14` rebuilds its glyph children
with the ordinary BMFont algorithm: cumulative kerning, descriptor line
height, and a centered width. Other labels use the game's `0004dc20` layout.
The cursor's glyph was created by `000858cc` **before** its nominal height
was set to 26. It is never assigned text again by this panel. Its glyph
therefore retains the initial zero-height line origin; applying the later
nominal height to that existing glyph would move it below the input slot.

The values 22000, 23000, 24000, and 25000 in this path are scene-node tags
for labels, not image resource IDs. The normal screen does not use resource
707. It also does not attach the portrait picker's frame-41 checkmark or the
common lower-left gear. The keyboard's Return is the verified confirmation
path; input-panel touch methods `000d3278/000d327c` are empty.

## Rejected-input alert

`000d339c` hides the input widgets and keyboard and unregisters keyboard
listeners. It leaves the draft and suspended VM call untouched. It shows:

| Element | Source / placement |
| --- | --- |
| Clickable panel | Resource 707, 280 by 160, centered at `(160,240)` |
| Heading | Resource 13 string 258, `Alert`; Arial Rounded 20, nominal 16, white, origin `(130,169)` |
| Message | Resource 13 string 260; Arial Rounded 16, nominal 16, gap 2, center/top wrapping (`0x16`), content size `(280,160)`, label origin `(20,185)` |
| Confirmation caption | Resource 13 string 164, `OK`; Arial Rounded 20, nominal 16, black, origin `(140,275)` |

The error text is:

> The name entry screen only supports the following alphanumeric characters: A-Z and 0-9.

The same alert is used for invalid characters, the length limit, and the width
gate. `000d3f94` restores the widgets and keyboard after dismissal. Desktop
stops processing a paste at the first rejected character and ignores further
text while the alert is open. Clicking its panel or pressing Return dismisses
the alert without submitting the name. Backspace removes one character and
clears the alert so editing can continue.

## Desktop, saves, and verification limits

`desktop_input.py` draws a 320 by 480 canvas. Desktop converts logical hit
rectangles using the same window transform as the other native screens.
Clicking the entry slot reactivates SDL text input after empty Return. Escape
opens the desktop pause/save/load menu. Input stops while paused, unfocused,
or displaying the alert. The cursor blinks on the desktop clock and the
screen redraws each frame; neither affects the VM or saved clocks.

Save version 12 is retained. An optional `pending.details.draft` must be a
string on load. Old prototype drafts remain editable, but confirmation must
pass the new rules. Drafts do not update `last_input` or dynamic strings until
submission. Alert, keyboard visibility, and cursor phase are transient desktop
state, reset on restoring a save or changing the pending action.

Authored tests cover both service IDs, callback/frame preservation, ASCII and
case rules, both limits (including the pre-append width boundary), empty
Return, backspace, modal rejection, focus/pause, save/load, scaled alert hit
testing, and cursor redraw. An optional local-content test loads the player's
actual layouts, image packs, fonts, and menu strings. Local rendering checks
are not a pixel comparison against a running original build.

The mobile system keyboard is supplied through native host interfaces and
is not reproduced as a drawn desktop keyboard. Cross-label global kerning,
native panel transitions, inherited mutable layout/font state from other UI
paths, and exact cursor animation timing still require a live reference
comparison. No unsupported native service is acknowledged to reach this UI.
