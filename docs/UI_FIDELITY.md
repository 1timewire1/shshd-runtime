# Original UI reconstruction evidence

Revision: 2026-09-13. The user reports identical iOS and Android interfaces.
The working reference is the supplied SHS Android 1.0.9 APK and its loaded
`libshs09.so`. The target is the shared original interface; the prototype's
current appearance is temporary. See [RUNTIME.md](RUNTIME.md) for implementation
order and [ENGINE_ABI.md](ENGINE_ABI.md) for game/UI behavior contracts.

IPA playback now reads the supplied iOS asset bank. [IPA.md](IPA.md) records
its native timer, name-entry and football differences, installed-font lookup
and user-requested system-default fallback. The Android bitmap-font evidence
below does not establish identical iOS font metrics or rasterization.

As of 2026-10-05, the owner selected **v0.1.3's SHS dialogue display** as the
best available presentation reference for both SHS and CoD. Their APK/IPA
adapters supply artwork and fonts to the same dialogue layout and renderer.
The renderer remains shared. Later original screenshots and Ghidra verification
established native outline-font title/body rules within that skin; see
[IPA dialogue](IPA.md#dialogue-text-placement). The Android font evidence below
is retained for bitmap playback, not imposed on the IPA's CSFont metrics.

## Confirmed clues in the supplied APK

`assets/Assets/fonts/` contains **18 bitmap-font sets**. Every set has a text
`.fnt` descriptor and an atlas available under both `.dat` and `.png` filenames.
For all 18 sets, those two atlas files are byte-identical PNGs. These are actual
shipped glyph images; no system-font installation or substitute font is needed
to obtain their appearance.

The descriptors contain **1,711 glyph records** and **1,443 kerning records**
across the sets. They supply glyph rectangles, offsets, advance widths, line
heights, and kerning information. Counts include records repeated in colored
font variants. There are 1,442 distinct per-font kerning pairs: Trebuchet bold
repeats the pair `(118,46)` with the same amount, -2. This is data needed for
faithful text layout, not just font family names.

Some representative descriptors:

| Asset filename | Descriptor face / size | Line height | Actual atlas |
| --- | --- | --- | --- |
| `ArialRoundedMTBold16.fnt` | `Dialog.bold`, 14 | 19 | 512 × 64 |
| `TrebuchetMS_Italic16.fnt` | `Trebuchet MS Italic`, 16 | 20 | 512 × 64 |
| `PajamaHip26.fnt` | `Pajama Hip`, 26 | 38 | 512 × 256 |
| `mainmenu.fnt` | `Comic Sans MS Bold`, 14 | 21 | 256 × 64 |

The filenames do not reliably specify the glyphs' actual face or size. Choosing
a similarly named desktop font would therefore introduce differences even
before platform-specific font rasterization and hinting are considered.

`assets/Assets/images/` contains **19 named PNG assets**, including scrollbar,
slider, sound controls, boxes, icons, and other UI graphics. Numeric assets also
contain logos, decorative artwork, textures, and additional font resources.
The dialogue layout bank and ARGB/alpha image packs are now decoded from their
native readers; see [UI_ASSETS.md](UI_ASSETS.md). Existing experimental
conversions are not authoritative evidence for unverified formats.

`assets/GameApplication.ini` declares `fps=30`. This is a configuration clue;
it does not by itself prove that every animation, timer, or minigame advances
in fixed 1/30-second steps. Native elapsed-time behavior remains authoritative.

## Native paths that use these assets

Research output is saved in `native-ui-fidelity-helpers.c`
and `native-font-field-parsers.c`. These are
decompiler evidence, excluded from distributable engine packages.

| Address | Evidence |
| --- | --- |
| `FUN_000e09d4` | Constructs an ordered registry of 17 of the named `.fnt` descriptors; the separate `mainmenu` set is not in this registry |
| `FUN_000a59bc` | Constructs a scrolling UI widget using `Assets/fonts/ArialRoundedMTBold16.fnt` and `Assets/images/text_scrollBarSmall.png`; derives child placement from measured sizes/positions |
| `FUN_0017874c` | Reads font descriptor lines and dispatches info, common, page, glyph, and kerning records |
| `FUN_00175f90` | Reads common font metadata; stores `lineHeight` |
| `FUN_00176abc` | Parses glyph ID, rectangle, offsets, and advance into the native glyph record |
| `FUN_0017633c` | Parses signed decimal `first`, `second`, and `amount`; inserts a kerning record keyed by `(first << 16) \| (second & 0xffff)` |

The font registry order is Trebuchet bold/italic; Arial Rounded 11, 14, 15, 16,
20, 22, 28, 30; Arial 11/14; and the five Pajama Hip variants. These are registry
entries, not EXP/global numeric resource IDs. `FUN_000e0c50` indexes this table
and constructs the `Assets/fonts/` path. Dialogue roles are now traced below;
other screens still require caller tracing.

Native layout evidence also exists in the already saved
`native-playback-helpers.c`:

- `FUN_000d2238` initializes a panel rectangle at `(0,120)` with dimensions
  `(320,240)` and computes related UI placement using `480 - y`.
- `FUN_000a92f4` places a background at the vector `(160,300)`.
- `FUN_000ab048` updates character/panel state and writes numeric decoration
  cache keys 3000 and 3001. Reproducing only the visible portrait omits those
  native state changes.

These are concrete layout/state clues. The complete root viewport transform,
asset scaling, anchoring, clipping, draw order, and input-coordinate conversion
still need to be established before declaring a screen pixel-equivalent.
The dimensions of a background image alone do not define that transform.

## Font-loader compatibility details

The supplied descriptors contain quirks that a strict generic loader could
reject or interpret differently:

1. Every descriptor declares one fewer character than the number of `char`
   records it actually contains. `FUN_0017874c` skips the `chars count` record
   and continues to parse the individual glyph lines; it does not use the
   declared count to truncate the glyph set.
2. `ArialMT14.fnt` declares a 512 × 512 atlas, while its actual PNG is 512 × 32.
   In `FUN_00175f90`, `scaleW`, `scaleH`, and `pages` tokens are copied into
   temporary strings and discarded; only `lineHeight` is stored. The complete
   texture-coordinate path still needs tracing. Do not resize/pad the atlas
   solely to force it to agree with the descriptor.
3. The `+` glyph (ID 43) in `ArialRoundedMTBold16.fnt` contains `yoffset=6.5`.
   `FUN_00176abc` reads offsets with `%d`, so this field becomes **6** in that
   native parser. Preserving a floating-point 6.5 offset would differ.

The inspected native glyph record has this field sequence:

| Offset | Conversion / meaning |
| --- | --- |
| `+0x00` | `id=%u`, glyph ID |
| `+0x04` | `x=%f`, atlas x |
| `+0x08` | `y=%f`, atlas y |
| `+0x0c` | `width=%f` |
| `+0x10` | `height=%f` |
| `+0x14` | `xoffset=%d` |
| `+0x18` | `yoffset=%d` |
| `+0x1c` | `xadvance=%d` |

The top-level reader copies this 32-byte record into its glyph table.
`FUN_0017900c` allocates 2,048 such entries. Its initialization clears rectangle
fields but does not initialize every absent glyph's advance. There is no
verified native fallback glyph. The compatible loader therefore reports a
missing glyph explicitly instead of substituting a system font or reproducing
an uninitialized memory read. It accepts the supplied single-page descriptors.
The pygame backend currently requires integral atlas rectangles; all supplied
rectangles satisfy that restriction.

## Dialogue typography and layout contract

The evidence is in `native-dialogue-text.c` and
`native-font-advance.asm`. `FUN_0007cbbc` constructs the
dialogue font objects, `FUN_000a8544` displays speaker names, and
`FUN_000aa0a0` displays body text. Font selection is verified through the
registry accessor, independently of the scrolling widget described above.

| Role / native object | Registry index / asset | Nominal height | Extra line gap |
| --- | --- | --- | --- |
| Ordinary dialogue, `DAT_002ae914` | 5 / `ArialRoundedMTBold16.fnt` | 14 | 7 |
| Panel mode 4 narration, `DAT_002ae918` | 1 / `TrebuchetMS_Italic16.fnt` | 10 | 7 |
| Narration measurement, state `+0xd180` | 5 / `ArialRoundedMTBold16.fnt` | 16 | 9 |
| Default speaker, `DAT_002ae908` | 12 / `PajamaHip26.fnt` | 16 | Initially -16 |
| Theme -1 speaker, `DAT_002ae90c` | 16 / `PajamaHipY26.fnt` | 16 | Initially -16 |
| Theme 2 speaker, `DAT_002ae920` | 13 / `PajamaHip266.fnt` | 16 | Initially -16 |
| Theme 3 speaker, `DAT_002ae928` | 15 / `PajamaHipG26.fnt` | 16 | Initially -16 |

The font object has separate nominal height, extra gap, descriptor line height,
and sprite transform. `FUN_0004c7b8` initially sets the gap to negative nominal
height; dialogue setup then overrides it with 7. Setting nominal height does
not resample the glyph atlas or proportionally scale advances. The name path
normally applies an additional 0.9 sprite scale, with numerous string-length,
panel-mode, and named-character exceptions. `speaker_names.py` implements the
branches of `FUN_000a7fa8` / `FUN_000a8544`, including their persistent inputs.

### Speaker labels and persistent font state

These rules depend on the font object's history, not just the current name.
`FUN_0007cbbc` initializes each of the four name labels with `SHS`, a zero
content size, nominal height 16, gap -16 and one measured line. The mode-2
large-name branch changes the selected object's gap to 8. Later short names
do **not** reset it. Each colored font has its own content size, line count
and indent array. `FUN_000a79a8` removes labels from their parent without
resetting these objects; dialogue panel close therefore retains the state.

`FUN_000a7fa8` selects layout-17 rectangles as follows:

| Presentation mode | Small rectangle | Large rectangle | Large-name test |
| --- | --- | --- | --- |
| 1, portrait on left | `0x2e` | `0x25` | Measured wrapped height exceeds small rectangle height |
| 2, portrait on right | `0x4c` | `0x43` | Unwrapped advance width exceeds small rectangle width |
| 3, no portrait | `0x6a` | `0x61` | Measured wrapped height exceeds small rectangle height |

The large branch sets panel `extra=40`, otherwise 8. Modes 1/2 subtract 40
from the large rectangle's Y. Mode 1 adds 1 to X; mode 2 adds 1 for eight-byte
names, otherwise 5. Measurement uses the theme-2/3 font when selected and the
default font otherwise: theme -1 measures with the default but draws yellow.
Height measurement updates that measuring object's line count. Mode 2's width
measurement does not; its later line-count tests observe the previous name.

Below, `w,h` are the selected rectangle dimensions, `n` is the original name's
Latin-1 byte length and `c` is the selected drawing object's line count at the
branch. Branches are ordered. Scale starts at 0.9 on each call.

| Mode / branch | Label content size | Scale / alignment |
| --- | --- | --- |
| 1, `Brendizzle` | Retain the previous size | 0.9 |
| 1, `c < 2` | `(w+20, h+30)` | 0.9 |
| 1, otherwise | `(w+80, h+30)` if `n < 14`, else `(w+40, h+30)` | 0.8 |
| 2, `Howard's Mom` | `(235, h+32)` | 0.9, `0x3d` |
| 2, `Howard's Dad` | `(223, h+32)` | 0.9, `0x3d` |
| 2, `French Teacher` | `(225, h+50)` | 0.8, `0x3d` |
| 2, `Neighbor's Wife` | `(w+80, h+60)` | 0.8, `0x3d` |
| 2, `n == 8` | `(w, h+34)` | 0.9 |
| 2, `n == 11`, including Mr. Russell | `(w, h+82)` | 0.9, `0x3d` |
| 2, `c < 2` | `(w+20, h+32)` | 0.9, `0x19` |
| 2, `n < 19` | `(w+80, h+30)` | 0.8, or 0.7 for `Spud The Stud` |
| 2, otherwise | `(300, h+32)` | 0.7 |
| 3, `n == 8` | `(w+20, h+34)` | 0.9, `0x1a` |
| 3, `n < 16` | `(w+20, h+20)` | 0.9, `0x1a` |
| 3, otherwise | `(580, h+30)` | 0.6, `0x1a` |

Mode 1 uses flags `0x1b` for the small branch, `0x19` for large, and indents
`[0,20]`. Mode 2 starts with `0x1a` for small, `0x19` for large, and sets
indents `[0,5]`. Only mode 3's middle branch clears the previous indents;
its eight-byte and long branches retain them. Small mode-1 labels subtract
23 from node X when truncated unwrapped width is below 127; mode 2 adds 23
under the same width condition.

The native routine also rewrites spacing within the panel's retained string:

| Branch | Original → displayed string |
| --- | --- |
| Mode 2, eight bytes | `The Boss` → `Th e Boss ` (including trailing space) |
| Mode 2, `c < 2` | `The Mayor` → `Th e Mayor`; `Judge Tigh` → `Judge Ti gh`; `Animal Thief` → `Animal Th ief` |
| Mode 2, `c >= 2` and `n < 19` | `Spud The Stud` → `Spud Th e Stud` |
| Mode 3, eight bytes | `The team` → `Th e team` |
| Mode 3, middle branch | `The Whole Room` → `Th e Whole Room`; `The Crowd` → `Th e Crowd` |

These are verified literal comparisons in the binary, not new episode-specific
overrides. Character metadata and pending source text remain intact. Mode 3
can retain the preceding panel string, including its spacing rewrite.

`fonts.layout_label` implements the relevant `FUN_0004dc20` flags: low bits
1/2/3 mean left/center/right; `0x08` means vertical center, `0x0c` bottom;
`0x10` wraps, and `0x20` limits drawn lines to the content height. Alignment
uses nominal line boxes and accounts for the absolute per-line indent.
Bottom alignment sets local GL text Y to `H - measured_height - 4` and adds
four to the clipping height. With node anchor `(0.5,0.5)` and scale `s`, its
downward screen origin before per-glyph offsets is
`480 - node_y + s * (measured_height + 4 - H/2)`.
Vertical center instead gives `480 - node_y + s * measured_height/2`.
The previous implementation applied center alignment to bottom-aligned names,
placing a fresh Mr. Russell label 47.25 logical pixels too low.

`Session` advances name-font state once per dialogue. Rendering and page turns
use a copy of the state before that dialogue, so their frequency cannot change
future placement. Save version 10 retains both banks and validates the current
layout against them; see [RUNTIME.md](RUNTIME.md#runtime-save-schema-version-13).

**Compatibility correction, not verified native behavior:** applying these
native rules with the current imported-font renderer still permits overlaps.
Nominal name height is 16 although visible glyph rectangles can exceed 30;
retained spacing can also lower a later short name into the dialogue. After
native layout, `fit_speaker_ink` separates overlapping rows, shrinks ink only
when it exceeds the selected header's width or height. Bitmap-label ink is
attached to the bottom of the available header; outline-font titles retain
their native position unless they exceed the bounds. The selected normal/tall
node in layout 17 supplies the vertical region (31/63 high in the supplied
skins), shortened only where body glyphs intrude. Width is bounded by the
skin's left/right border frames, the viewport and the portrait.
Glyphs and outlines are scaled together, including multiline names and larger
fallback faces. The body boundary accounts for glyphs anywhere in the dialogue,
keeping the name fixed across page turns.

The later CoD promo shows "Det. Mal Fallon" over two lines straddling the top
border. The intermediate 31-pixel-only guard prevented that presentation and
was an overcorrection. The shared renderer now wraps outline-font titles at
their native width, selects the normal/tall region, and keeps the body text in
its own region; see [the native verification](IPA.md#dialogue-text-placement).
This applies to every name in both iOS games. No promo/scene exception exists.

The earlier fitter constrained only viewport width and the first body ink.
It had no top/height limit and did not attach names to the actual box. CoD's
Volume One poker sequence exposed both gaps: long names could exceed the
box edge, and the subsequent name could float above it after a large-name
transition. Comparing that renderer against itself with another asset adapter
could not detect these problems. The general correction uses the same bounds
for all games and fonts, without new character-name exceptions.
The ink guard changes drawing only. The separate outline-font measurement
correction can change header selection and body pagination; save version 16
reflows old IPA pages without altering VM arguments, results or random state.

Authored tests cover all presentation modes and font themes, long and multiline
names, preceding font-state changes, saved pages, invalid state and migration.
An optional local-content check covers Football Star's portrait-bearing roster
and a parents-then-teachers sequence using the player's original fonts.
Rendered parent/teacher checkpoints and save restoration were checked locally.
The optional CoD opening check includes the poker cast, the later Captain and
actual rendered name-layer bounds. The owner's original CoD screenshots show
titles attached to the box's top border and corroborate its separate palette;
see [COD.md](COD.md#native-ui-and-audio-bindings). Tests now require bounded title height
and box attachment in addition to non-overlap. These checks establish bounded
drawing in this renderer; exact native pixel
equivalence still requires comparison with a running original game. Shared
kerning and measurements performed by other UI paths, such as `FUN_000d9038`,
are not yet included in the dialogue font-history model.

### Name-entry screen

Services 17/40 now use the APK's layout bank (15/43/46), image packs
126/204/16, and entry shadow 706. Resource **707 belongs to the rejection
alert**, rather than the normal name screen. The title uses Arial Rounded
30, the prompt 16, and the entered name 28; the cursor is Pajama Hip 26.
Setup colors all four blue. The ordinary header, body, and footer are
centered at GL `(160,415)`, `(160,340)`, and `(160,267)` respectively.

Return on the keyboard is the verified submission path. This panel does not
attach the portrait-selector checkmark or common gear. The desktop host menu
is accessible through Escape. Full coordinates, title/cursor font-origin
details, the error alert, input limits, and remaining uncertainties are in
[NAME_INPUT.md](NAME_INPUT.md). This supersedes the provisional screen
identification in `CONTINUING.md`.

### Story text and wrapping

`FUN_0004d3f8` consumes NUL-terminated bytes. The current text core accepts
Latin-1 strings, matching the KiWi host text representation. The implemented
ordinary path is:

1. Skip ASCII spaces at each new line's start. Preserve spaces inside a line;
   do not collapse all whitespace. LF ends a line; a trailing LF does not add
   another empty line. A leading LF does produce an empty line.
2. Measure with glyph `xadvance`. Registered color delimiters have zero advance
   with the dialogue object's zero character-spacing field. **Kerning is not
   included in line fitting.**
3. Accept a glyph that exactly fits. On overflow, scan backward to an ASCII
   space and wrap there. If the word has no earlier space, split at the
   overflow glyph. Native layout aborts when a single glyph exceeds the
   available width; the compatible core reports this condition explicitly.
4. Store source start/end byte offsets for each line. The native object retains
   up to 32 pairs; the Python layout retains all computed pairs. No truncation
   or pagination policy is inferred from that native bookkeeping capacity.
5. For nominal height `h`, gap `g`, and line index `i`, the downward line-box Y
   is `i * (h + g)`. Measured height is `n * (h + g) - g` when the product is
   nonzero, otherwise zero. Ink can extend beyond that measured line box.

`FUN_0004c9e8` configures per-line indents. Positive entries move the left edge
inward; negative entries shorten the right edge. Available width decreases by
the absolute value. Ordinary dialogue panel modes 1 and 2 use respectively
`[85,75,0,0]` and `[-85,-75,0,0]` at `0x0025b344` / `0x0025b354`.
These let the first two lines fit around the character area. The desktop now
applies them with the recovered portrait and box geometry.

### Glyph placement, kerning, and color controls

`FUN_0004cae8` returns unscaled `xadvance` (or negative character spacing for a
registered delimiter). `FUN_0004cb90` draws a glyph using the atlas rectangle,
offsets, and `FUN_0013f09c` kerning lookup. In downward coordinates relative to
the nominal line-box origin:

```text
glyph_left = pen_x + xoffset + kerning(previous_drawn_glyph, current_glyph)
glyph_top  = line_y + nominal_height - descriptor_lineHeight + yoffset
next_pen_x = pen_x + xadvance
```

The kerning amount moves **only that glyph**, not the pen. Spaces and color
delimiters do not update the previous drawn glyph. Native `__data_start` at
`0x002a8010` holds that previous byte, starts at -1, and has no other code
writers in the inspected program. It therefore persists across lines and
separate text objects. The next lookup uses `LDRSB`, sign-extending that byte
before packing its low 16 bits into the high half of the pair key. Thus byte
233 uses first-key half 65513, not 233. The pure layout accepts/returns the previous glyph;
the current frontend initializes each text block to -1. Exact object-update
ordering and its cross-object kerning state are still missing.

`FUN_0004c90c` registers color delimiters. Ordinary dialogue registers backtick
and semicolon. They share **one toggle**, so a different registered delimiter
can close the active color span. A matched delimiter is invisible and does not
change the font. Color persists across wrapped lines. This corrects the earlier
assumption that backticks implied an italic font. **Narration** selects the
italic font through panel mode 4. A service-13 thought prefix of -2 instead
adds parentheses and retains the ordinary speaker panel and body font.

For ordinary visible characters, `FUN_000ab048` derives theme `DAT_002af014`
from character-owned numeric key 651. `FUN_000a81d8` applies these RGB values:

| Theme | Body RGB | Backtick RGB | Name font |
| --- | --- | --- | --- |
| 1 | (41,104,221) | (254,53,0) | Pajama Hip 26 |
| 2 | (180,78,78) | (41,104,221) | Pajama Hip 266 |
| 3 | (108,108,108) | Inherits the prior setting | Pajama Hip G26 |
| Other | (223,163,52) | Inherits the prior setting | Pajama Hip 26, or Y26 for -1 |

The initial ordinary backtick color is (254,53,0); the semicolon color is
(1,76,215). Narration body/backtick colors are (223,163,52) / (125,67,0).
Color modulates the original atlas RGB while preserving its alpha and colored
variants. The engine now retains the last theme-1/2 backtick selection through
other themes and serializes it. Other font-object lifetime effects, including
cross-object kerning and interactions with other UI widgets, remain incomplete.
Dialogue name gaps, line counts, sizes and indents are retained as specified
above.

## Dialogue panel composition

The native geometry and artwork schemas are in [UI_ASSETS.md](UI_ASSETS.md).
The game scene uses **320 × 480 logical coordinates**. The desktop renders
that scene and scales/letterboxes it to the window; UI placement no longer
comes from the former dark, full-width desktop dialogue overlay.

This 320×480/480×720 reference is the Android phone screen this whole
pipeline was calibrated against. An iOS HD build ships some backgrounds at
real higher pixel density (960×1440 confirmed on real content); compositing
those into this fixed-size canvas at native density and only then scaling
the whole canvas to the window discards that extra detail before it ever
reaches the screen. `Desktop._present()` composites the background as a
separate layer, directly at window resolution, underneath this canvas
instead -- the UI layer's own 320×480 math here is unaffected and unchanged.

Every screen with a real per-episode background (dialogue, choice, word
grid, loading, message panel, character picker, and the title/week-card
screen) tracks its own `pending_background`/`pending_background_origin` the
same way and lets `Desktop` composite it; each renderer's own 320×480 canvas
stays transparent where the background belongs (`pygame.SRCALPHA`) instead
of drawing it in directly. The title screen additionally tracks
`pending_background_alpha` for its background fade-in/out, applied to the
window-resolution copy after scaling rather than to the canvas-resolution
one. Football has no per-episode background (its field art is fixed game
chrome, not `panel.background_id`), and the main menu only ever reads from
the Android APK bank, so neither needed this treatment.

The default window is 3:4 (`DEFAULT_WINDOW_SIZE`), not 2:3 like the UI
canvas (`SIZE`). HD's own main game view is a fixed 768×1024 in every
orientation -- landscape is a rotation of that same rectangle, not a
resize, confirmed from `SHSViewController::setupLocalInterfaceOrientation:`
(see `legacy/findings.md`'s DTView/Faceplace layout section) -- so a 3:4
window gives the separately-composited background layer real room to show
more of the actual scene, while the Android-authored 2:3 chrome keeps its
own proven-correct proportions and position, centered and unchanged inside
that wider window. `_draw_background_layer`'s crop widens from 320 to 360
game units (480 × 3/4) around the same horizontal focal point for this
reason; the UI canvas's own crop/scale math is untouched.

`FUN_000ab048` and `FUN_000ab344` select these presentation modes:

| Mode | Trigger | Visible character/name |
| --- | --- | --- |
| 1 | Character with art matches service 74's ID | Portrait on left, name to right |
| 2 | Other character with art | Portrait on right, name to left |
| 3 | Character lacks art, or service 76 supplies an explicit speaker | No portrait; service 76 replaces the name, otherwise retains the previous native name object |
| 4 | Character matches service 75's ID | No portrait or visible name |

The New Girl configures service 74 to ID 0 and service 75 to ID 32. Character
32 is named **Event** in script metadata; it is not a name to display. The
engine uses the configured ID, not a string comparison. An ordinary character
literally named Event would still display its name when assigned a different
ID. Hiding narration must not erase or rename the script character.

Service 13's negative prefixes are a separate field from presentation mode:
`-2` wraps raw text with `(` and `)`, and `-3` wraps it with backticks. These
decorations precede substitution. Neither prefix selects presentation mode 4.
Explicit expression overrides pass through a signed low-byte conversion and
negative clamp before art selection. The delayed expression and separate
last-expression cache follow the recovered iOS lifecycle described below;
relationship indicators and their cache writes have their own section.

Service 76 supplies a speaker string and dialogue directly, selecting mode 3
and theme -1. It shares the name layout, no-portrait body, reveal and paging
rules below; it does not assign an NPC name or switch to narration. Its
[service contract](STORY_SERVICES.md#named-dialogue-without-a-portrait-service-76)
also describes the transition callback and saved-stop recovery.

### Box, portrait and text placement

The following geometry is the **v0.1.3 bitmap-font dialogue reference**, using
Android native evidence. IPA outline fonts use the same frame construction
with their verified cap-height metrics and separate body region; see
[IPA.md](IPA.md#dialogue-text-placement) for the implemented differences.

`FUN_000aa0a0` measures ordinary dialogue at layout-17 node 8, currently
`(37,304,246,98)`. With nominal body height `h=14`, gap `g=7`, and measured
line count `n`, it computes:

```text
capacity = trunc((rect.h + g) / (h + g))
n = min(capacity, max(3, n))
body_height = even_ceiling(n * (h + g) - g + 7)  // 8 if capacity is zero
extra = 8 normally, 40 for the native large-name branch
box_center_fill = (rect.x - 7, rect.y - extra, rect.w + 14, body_height + extra)
text_origin = (rect.x - 7, rect.y - trunc(extra/2))
```

The nine-slice border pieces extend **outside** that center-fill rectangle.
`FUN_0007f91c` / `FUN_0007fabc` select skin 204, 220, 252, or 236 by theme.
`FUN_00082144` / `FUN_00081920` use common-pack frame 0 as the fill, with skin
frames `(6,7,8; 4,fill,5; 0,1,2)` around it. Corners retain their original
dimensions; edges stretch along one axis. Measurement uses width 246, while
the resulting text object has width **260**; keep that native distinction.

`FUN_000aaa40` uses portrait node 48 or 78 and sets the whole widget center to
`(rect.x + rect.w/2, 485 - rect.y - rect.h/2)` in GL coordinates. In the
normal downward viewport, the resulting centers are `(57,284)` and `(263,284)`.
`FUN_0009dd8c` gives the widget a 128 × 128 content size and puts its scaled
portrait group at local `(0,0)`. The artwork and circle are children of that
group; the layout rectangle is not a separate anchor for the character image.
`FUN_0009bd40` supplies common frame 37 behind the portrait and frame 38, 39,
or 40 as the theme-colored circle. `FUN_0009c034` positions the character's
center at screen Y
`bubble_center_y + floor(common_frame_39.height/2) - floor(cropped_art.height/2)`.
Both heights are halved separately; using a strict bottom-edge anchor instead
placed odd-height artwork one pixel too high in pygame. The shared
`portrait_rect()` now applies the native center calculation to dialogue,
choices and the picker. Mode 2 flips the character except for theme 3.
The original 128 × 150 portrait mask is applied
before drawing; the portraits are no longer resized to an arbitrary 160 × 180
desktop rectangle.

That 128 × 150 mask is Android-reference-sized: it always comes from APK
resource 268 (below the 26000 threshold that routes per-episode content to
the `.exp` archive instead), so it never grows for an HD build. HD's own
per-episode portrait art (also read as resource IDs ≥ 26000, same as HD
backgrounds) runs well past it -- observed 220×240 up to 256×256 in real
episodes -- which used to raise `UIAssetError` and stop playback outright.
`DialogueRenderer.portrait()` now detects that case and calls
`_scaled_mask()`, which smooth-scales the mask's geometry (not the portrait)
up to cover it before clipping. The mask is a plain rounded cutout shape, not
detailed art, so this loses nothing a native HD-resolution mask would have
shown -- confirmed against real 220×240 through 256×256 portraits. This
sidesteps needing the iOS HD build's own low-id chrome container format,
which uses an undeciphered, Android-incompatible layout (see
`legacy/findings.md`, "HD retargeting feasibility") for most chrome -- the
portrait mask specifically turned out not to need that workaround at all
(see below).

The clipped result is always scaled back down to `ANDROID_MASK_SIZE`
(128×150, a fixed constant in `desktop_dialogue.py`) divided by the same
factor the mask needed scaling up by -- never to whatever size the mask
object actually in hand happens to be. Every ring, border and panel around
a portrait is still Android-sized, so leaving an HD portrait at its own
native pixel count made it render comically oversized relative to
everything else -- confirmed and fixed against a real HD choice screen,
where the earlier, unscaled version was clearly wrong side by side with the
correctly-sized chrome around it. Anchoring to a fixed constant rather than
re-deriving it from `self.pack(268)` each time matters because that mask
can itself now be the real HD-native one (below) -- if the reference size
tracked whatever mask happened to be loaded, importing an HD ipa would
silently change what "oversized" means and break this same scaling.

**A real HD-native mask exists after all, and is preferred when
available.** `content.py`'s `HD_ASSET_MAP` records that HD's own resource
311 is the identical rounded-cutout shape as Android's 268, just at a clean
native 256×300 (2x) -- confirmed by rendering both and comparing pixels,
not assumed from the size match. This is a real ImagePack-format resource,
decoded by the same unmodified parser Android resources use: the
"undeciphered format" conclusion above only ever held for one tested
resource type (`MenuStrings`, a font/text bank), not for image packs
generally (see `legacy/findings.md`, "HD chrome assets may be directly
usable after all"). The substitution happens transparently at the content
layer -- `ContentLibrary.read_asset()` hands back the HD ipa's bytes for id
268 whenever one was imported (see `RUNTIME.md`) -- so `portrait()`'s own
`self.pack(268)` call doesn't need to know or care which source it got;
it falls through to `_scaled_mask()`'s algorithmic upscale exactly as
before whenever the mask in hand (HD-native or Android) still isn't big
enough. Real source detail beats interpolation, though the difference is
subtle at this size; the win is using verified native data instead of an
approximation where one is actually available. The same transparent
substitution now also covers every background/portrait asset from id 1000
up to (not including) 25000 -- not just this one mask -- since those ship
at the same numeric id on both platforms; see `RUNTIME.md`'s content
library contract for the full id-range rationale.

Upstream's Android-side handling of the same imported art (New Girl's 256 × 256
and 226 × 256 variants) halves it before masking. This build reaches the same
apparent size without pre-halving: art inside an episode file that exceeds the
mask but fits within twice its size is treated as 2x Android art
(`DialogueRenderer._episode_portrait_size`), and its clipping mask is exactly
twice the 128 × 150 mask (`_scaled_mask`) -- what a real HD mask (resource 311)
is -- so the cutout matches native halved-then-masked geometry while keeping
the extra pixels for density. Previously such art fell back to the fixed mask
size and any 1x consumer drew 226 × 256 portraits at 128 × 145 instead of
113 × 128. The upstream paragraph follows.

The imported New Girl's 256 × 256 and 226 × 256 portrait variants use a
documented compatibility conversion to half size before masking and horizontal
flipping. This preserves their aspect ratio, transparency and bottom alignment;
the shared dialogue, choice and appearance-picker renderer uses the same path.
Native-size portraits and the full-resolution source cache remain unchanged.
The available Android implementation does not establish the original scaling
or filter for these larger variants, so this conversion remains an inference.
See [UI_ASSETS.md](UI_ASSETS.md#portrait-mask) for its precise bounds. Authored
tests cover alpha-aware reduction, mask order and both orientations; an optional
local-content check renders the imported episode through its opening and verifies
save restoration.

Masked portrait surfaces must be converted to the display's alpha-aware pixel
format before blitting. On the macOS Cocoa driver, an opaque canvas can retain
an alpha bitmask whose stored alpha bytes are zero. Blitting an unconverted RGBA
portrait onto that BGRA canvas exposed transparent white pixels and black mask
corners as an opaque rectangle. `desktop_dialogue.py` now uses `convert_alpha()`
after masking, as the other artwork loaders already do. This was reproduced
with the Cocoa driver and covered by a headless regression using the same
destination pixel format, including both portrait orientations, partial alpha,
and actual black artwork that must remain visible.

Choice-panel testing subsequently exposed the same destination-format problem
when a surface also has whole-surface opacity (the translucent box border).
All three composition canvases now explicitly use `convert(32)` to remove the
unused destination alpha mask; plain `convert()` retains it on Cocoa. The
display surface itself is unchanged. A regression compares the complete choice
image with RGB and simulated Cocoa default canvases, and a real Cocoa render
checks the translucent panel and its corners.

The native image loader also subtracts 12 from the decoded portrait height
after masking and before texture upload; `FUN_00139d70` confirms that the first
image field is height. The shared portrait loader now applies that crop once
for dialogue, choices and the appearance picker. The cropped texture's bottom
is aligned to the circle; retaining the discarded rows previously placed the
visible dialogue artwork 12 logical pixels too high. The circle's position and
entrance animation are unchanged. Authored regressions check the lower edge in
both orientations and all themes, mask-before-crop order, and absence of a
second crop in the picker. The imported New Girl check also covers normalization
before cropping and save restoration.

The native mask can still leave a narrow strip of the circle's fill beneath
the character. Local checks of New Girl's Zoe and Sam find a 1–2 logical-pixel
strip near the bottom center, enlarged along with the window. `00059eb4` ARM
instructions at `00059fb4`–`00059fc8` confirm that mask division occurs before
pixel multiplication, so partially masked pixels are fully cleared. Do not
silently trim that alpha margin or shift the art to cover it. The node centers
and mask arithmetic are verified from code; a pixel comparison with the running
original's final OpenGL sampling remains unverified.

Names use the layout's mode-specific name rectangles and the sizing, offsets,
alignment and default 0.9 scale recovered from `FUN_000a7fa8` / `FUN_000a8544`.
All branches of these two routines are represented, including literal-name
exceptions and persistent font state. The shared ink-bounds correction and
remaining fidelity limits are documented under
[speaker labels](#speaker-labels-and-persistent-font-state). Earlier research
output is preserved privately in `native-dialogue-placement.c`.

`FUN_00179a6c` gives each font node an anchor of `(0.5,0.5)`.
The desktop draws glyph ink relative to the derived origin, including negative
ink overhang, without normalizing it into a different rectangle.
### Background panning

Backgrounds start at the native unscaled center, GL `(160,300)` or downward
`(160,180)`. Shared desktop/iOS presentation now implements the recovered
speaker-side pan for both games. The special resource-1013 width adjustment
and scene transitions still need reproduction.

Direct Ghidra inspection confirms the horizontal movement during SHS dialogue.
Android `000aaa40` calls `000a7dcc` during
dialogue presentation; mode 1 requests alignment 1 (player side), while mode 2
requests alignment 3 (other character). `0007b790` moves the background node
over **250 ms** using the action created by `00157b04`; update `00136364`
interpolates linearly from the starting position. Its center targets are
`(width/2,300)` for alignment 1, `(160,300)` for alignment 2, and
`(320-width/2,300)` for alignment 3. These expose the left edge, center or right
edge of a wide background in the 320-pixel viewport. Repeated dialogue on the
same side need not move it; a viewport-width image has identical horizontal
targets. This is speaker-side alignment, not a continuous horizontal loop.

The supplied SHS iOS binary confirms the same targets at downward Y=180 in
`GameModel::alignLocation` (`00023a9c`), called by
`SHSUIDialog::animateLocationLayer` (`0007cc18`) for modes 1/2. Both binaries
also support disabling automatic alignment and selecting a fixed alignment:
Android `0007b8d4`, iOS `GameModel::setLocationPan` (`00023a80`). Service 97
passes `bool(a1), a2`, stores automatic/fixed policy, and immediately requests
alignment `a2`. With automatic panning disabled, subsequent dialogue uses the
stored alignment. Values outside 1/2/3 hold the current position. Additional
frame words are ignored; the call returns zero without a UI callback or score,
result-cell or random mutation. Android dispatch `000a257c` and CoD dispatch
`00034abc` confirm the contract. Exact iOS animation transaction timing remains
unverified; shared presentation uses the selected Android 250 ms reference.

CoD independently confirms the same dialogue mode/alignment mapping and center
targets in `animateLocationLayer` (`0003671c`) and `alignLocation` (`0000eff8`),
with automatic/fixed control in `setLocationPan` (`0000f0c0`). [CoD evidence](COD.md)
records the read-only disassembly
check needed where Ghidra truncates the helper at an Objective-C call.

`engine.background_pan` retains the starting/target fractions of image overflow,
the 0–250 ms clock and the script policy. It advances only during active session
time; rendering does not change it. Dialogue uses the existing 250 ms entrance
delay without adding another delay. Narration, named/no-art dialogue and page
turns do not request another alignment. Ordinary choices, name entry, portrait
selection and loading retain the scene background's position; the message and
word-game panels keep their separate centered backgrounds.

`000a92f4` replaces a nonnegative background at center even when its resource ID
is unchanged, then requests the current speaker's alignment. Base -2 retains
the node; -1 hides it. A changed target starts from the current interpolated
position. Closing dialogue retires its visual state but keeps script policy;
episode reset re-enables automatic panning (`0007e59c`, CoD `00012128`).

Save version 19 preserves a pan in progress. Older versions load with their
previous centered view until the next alignment request. Retained service-97
stops resume their original call. Authored tests cover both games, interrupted
movement, fixed/automatic policy, replacement/retention, pause, migration and
matching desktop/native pixels. The iOS probe also checks saved pan clocks and
CoreGraphics crops at the start, middle and end of opposite pans.

### Narration and page turns

Mode 4 uses the normal constructor's narrator anchor `(30,360)` in GL space.
`FUN_000858cc` configures its **measuring** font as registry 5 at height 16,
gap 9, with no registered color markers. `FUN_000aa0a0` measures at width 220,
caps measured height at 200, rounds width-plus-one upward to an even number,
adds 4 to height and rounds it to even, and enforces a minimum inner width 120.
The box fill is then `(25,115,inner_w+10,inner_h+10)` in downward coordinates;
the displayed italic font starts at `(30,120)`. Because measurement and display
fonts differ, even a short narration can wrap when drawn. The alternate native
constructor branch that shifts the narrator anchor by 15 remains unimplemented.

The native input handler at `0x000a9868` first completes an unfinished reveal.
When reveal is finished, it either acknowledges the final page or starts the
remaining substring at the consumed source-byte offset. The compatible session
now holds the VM's pending argument frame during page turns and resumes it
with 0 only after the final page. Pages keep the original box dimensions.
Page offsets and the reveal/portrait/name clocks are serialized. The first tap
requests completion of an unfinished reveal; only a later tap after completion
turns the page or acknowledges the dialogue.

### Dialogue transitions and reveal scheduler

The following is recovered from Android 1.0.9 `libshs09.so`; it describes the
ordinary dialogue path without relationship-decoration or scene-transition
overrides. `dialogue_animation.py` models this timing in session state.

| Native function | Contract |
| --- | --- |
| `FUN_000aaa40` | Sequences outgoing/incoming portraits, name fade and text reveal using previous character and presentation mode |
| `FUN_000a7dcc` | Supplies a 250 ms setup interval |
| `FUN_0009d64c` | New character: scale portrait group from zero to one in 300 ms; outgoing character: scale from one to zero in 300 ms |
| `FUN_000db334` | Delay followed by a scale action, repeated once in this path; no easing curve is applied |
| `FUN_0009bd40`, `FUN_0009c034` | Circle backing, colored ring and masked character art are children of that scaled group; scaling pivots at the circle center |
| `FUN_000a8544`, `FUN_000db3b8` | When the character changes, fade the name from opacity 0 to 255 in 300 ms, starting 120 ms after the portrait sequence |
| `FUN_000aa0a0` | Lays out the full text and box; schedules reveal with the sequence delay, plus 120 ms when the character changes |
| `FUN_000a5e98` | Installs the text, hides glyph children by source index, clears reveal state, and schedules a selector with interval `0x3b449ba6` (0.003 seconds) |
| `FUN_000a5fa4` | After the initial delay, visits one source index per eligible scheduler update; completion unhides the full label and stops the selector |
| `FUN_000a5e20`, `FUN_000a5e2c` | Request fast completion and query completion, respectively |
| `FUN_000a9868` | Unfinished reveal: request completion. Finished reveal: advance the substring with a 350 ms delay, or acknowledge the final page |

Portrait delay depends on the previous visible character. An outgoing portrait
starts shrinking immediately. If the next character occupies the same side,
its entrance waits for that 300 ms exit as well as the 250 ms setup interval.
Opposite-side portraits do not add that exit interval to the incoming delay.
Unchanged characters retain their portrait and name while their next text
starts after 250 ms. Page turns retain the portrait, name and box dimensions.

Ordinary timing examples, relative to the new dialogue's presentation:

| Transition | Outgoing portrait | Incoming portrait | Name fade | Text start |
| --- | --- | --- | --- | --- |
| First visible character | None | 250–550 ms | 670–970 ms | 670 ms |
| Different character on opposite side | 0–300 ms | 250–550 ms | 670–970 ms | 670 ms |
| Different character on same side | 0–300 ms | 550–850 ms | 970–1270 ms | 970 ms |
| Same character | Retained | Retained | Retained | 250 ms |
| Switch from a character to narration | 0–300 ms | None | Hidden | 370 ms |
| Next page of the same dialogue | Retained | Retained | Retained | 350 ms |

Android positions/sizes the box immediately in `FUN_000aa0a0`; its ordinary
path does not supply a box fade or scale action. The shared runtime originally
followed this behavior. The owner has now selected the original **iOS box
entrance for both games**; the common final layout remains unchanged.
The footer stays stationary while the background follows its independent
250 ms alignment move.

**Letter cadence policy.** The native selector's 3 ms interval is not a promise
of 333 letters/second: its body visits only one source index per update and
resets its elapsed accumulator instead of catching up. The bundled application
configuration declares 30 fps. The compatible session models this as one source
index per 1/30-second step, independent of rendering, and displays the portrait
and name tweens at 60 fps. This reproduces the configured nominal cadence;
the exact cadence of a running original device, including dropped frames and
the scheduler's initial tick, has not been compared against a recording.

The first step at or after the initial delay reveals index zero. Spaces,
newlines and color controls consume source indices even though some have no
visible glyph. Full layout precedes reveal, so line breaks, indents, colors
and box size never change as letters appear. The native cursor scans the
whole remaining substring, including source indices beyond the visible page.
After its last index, another callback marks completion. A finish request
respects the entrance delay: the next callback visits one index and moves the
cursor to the end, and the following callback unhides the whole label. It
does not resume the VM. Repeated input before that completion cannot acknowledge
the page. The desktop also stops processing queued game input when a tap
changes the reveal state, requiring the resulting frame to be displayed first.

**Saved state.** `engine.dialogue_animation` contains `text_length` (length of
the remaining substring), `portrait` and `previous` (nullable objects containing
`character_id`, resolved `asset_id`, `mode`, `theme`), `changed`, `page_turn`,
`elapsed_ms`, `revealed`, `complete`, `finish_requested`, and `finish_step`.
Clocks and counters are nonnegative integers; flags are booleans. A portrait
mode must be 1 or 2. `revealed` cannot exceed `text_length`, and a completed
reveal must have reached that length. `finish_step` is 0 or 1 and returns to
0 at completion. Delays, scales and opacities are derived from these fields;
no surfaces, fonts or wall-clock timestamps enter saves. Animation state also
survives intervening panels and VM pauses. Covered dialogue does not tick;
explicit panel removal, a new scene or episode teardown disposes it. Loading
validates its correspondence with the pending dialogue's substring and current
portrait. Application inactivity and the pause menu stop its clock. Version 21
adds the lifecycle fields and hidden-layer history specified below.

Relationship-decoration delays are implemented through the recovered
`FUN_0009ce2c` path; see the NPC relationship section. The flag previously
described here as a scene transition is specifically service 89's next-dialogue
shake. Its additional 400 ms delay is now modeled. It is distinct from service
16's whole-screen transition selector.

### iOS dialogue-box entrance

Read-only Ghidra inspection confirmed the same three `BubbleFrame` records
in SHS `setupAnimationsForTextLayer` **0007df70** and CoD **00035898**.
CoD `animateLayers` **00037a60** passes the 250 ms setup interval plus the
portrait/status sequence duration into `animateTextLayer` **000373e0**.
A changed speaker without the shake flag calls the bubble helper; a retained
speaker, page turn or shake path does not.

Relative to that sequence's completion, the keyframes are:

| Time | Box frame |
| --- | --- |
| 0 ms | 1×1 at the portrait layer's position |
| 120 ms | Final x/y and width, height 20 |
| 320 ms | Final x/y, width and height |

CoD `SHSBubbleLayer::createAnimation:::::` **00015704** lays out the box at
each frame, collects each child's position/bounds and applies matching
keyframe animations. **00015468** selects `kCAAnimationLinear` and
`kCAFillModeBoth`; the original Mach-O indirect-symbol table confirms those
constants. Corners retain their dimensions; straight edges and the center
resize. This is not a scaled screenshot of the whole box. Ghidra's CoD ARM
decoding and Objective-C noreturn annotations truncate some decompilations;
the original armv6 instruction bytes and selector references were also read.

The shared renderer implements these keyframes for all changed speakers. First
and opposite-side entrances grow at 550–870 ms; same-side replacements grow
at 850–1170 ms, before any additional relationship delay. Text/name timings
remain as above. Page turns keep the full frame. Save version 20 adds
`box_grow:bool`; existing `elapsed_ms` drives the animation, so drawing does
not advance it. Older saves set `box_grow=false` for their current dialogue,
retaining the already full-size box and all text/VM clocks.

SHS `animatePortraitLayer` **0007e798** and CoD **000367b4** retain the current
portrait layer's position when hiding it for narration or a speaker without
art. Only the outgoing and cached layers swap; the current layer remains in
place. A portrait-less entrance therefore starts at the last visible side's
logical position, or `(0,0)` before any portrait was positioned. Its travel
runs at 250–370 ms and height expansion at 370–570 ms, before relationship
delays. `engine.dialogue_history.anchor_mode` records 0 (initial), 1 (left) or
2 (right), using the same common layout origin as visible portraits. Closing
the dialogue panel or loading another scene retains this global position.

### Portrait housing at box completion

SHS `GameModel::clipAgainstBubble` **0002367c**, `clipHousing` **000238c8** and
`SHSPortrait::drawInContext:` **00069e9c** recover the cutout. Relative to the
final box `(x,y,w,h)`, it is `(x-7,y-7,w+14,h+34)`, with 10-pixel bevels at
the two top corners, converted into portrait-local coordinates. The inverse
path clips only outer housing frame **37**. Colored frames **38/39/40** and
the character's separate image layers remain intact.

SHS `animationDidStop:finished:` **0002a7fc** and CoD **00014ca4** apply the
cutout after successful completion of the `dialog-bubble-grow` animation.
For a retained speaker it is immediate. New grow/shake tracks clear it first;
cancelled tracks do not receive a successful completion and do not clip later.
The shared renderer stores this as `housing_clipped` and preserves it on page
turns. Authored pixel checks exercise the bevel, untouched ring and character
on SDL, the native drawing backend and actual CoreGraphics.

### Shake and reveal input

SHS `GameModel::shakeDialog` **000259a8**, CoD **0000f774**, and their dialogue
`animateLayers`/`animateTextLayer` paths implement service 89 as follows:

- Hold box opacity at zero for **100 ms**, plus **600 ms** for a changed
  speaker; then show it at full opacity.
- From that point, scale **0.5 to 1 over 125 ms** and rotate over **250 ms**.
  The right speaker uses **-0.25, +0.125, 0 radians** at normalized key times
  **0, 0.75, 1**; the other side reverses the signs. Interpolation is linear.
- Suppress ordinary box growth and add **400 ms** to the non-grow text delay.
  Clip housing when the rotation finishes. Very short/no-art dialogue still
  allows the entire box animation to finish after its text clock completes.

The legacy `wobble_direction` values remain side markers; version-20 and older
checkpoints retain their existing Android 70/2-or-5/70 ms rotation while that
dialogue is active. New dialogue uses the shared iOS behavior.

SHS `touchesBegan` **0007befc** and CoD **0003719c** cancel the title and bubble
tracks when requesting an unfinished text reveal. They do **not** cancel the
portrait entrance or delayed expression. The shared `visuals_finished` flag
settles the box and name on that tap, while the existing common reveal gate
holds the VM and requires a later acknowledgement. Cancelling a grow does not
fabricate its successful clipping callback.

**Correction to the previous input-lock note:** the bubble completion delegate
does not impose a tap lock. SHS's early checks at game-model `+0x3b4` and
`+0x1c44` refer to the script loading gate and global fade respectively.
`SHSScript::executeWithSyscalls` **0006d728** clears the former after the loading
timer; the shared loading screen already gates that interval. No invented
blanket portrait/box lock was added. Whole-screen fade transitions and their
associated input gate remain outside this dialogue implementation.

### Delayed expressions and panel reuse

SHS `setCurrentSpeaker` **0007c790** / CoD **00038008** enter a new speaker with
expression **0**. An unchanged speaker starts with its separate last-expression
byte. This cache is distinct from service 5's script-selected expression.
SHS `tick` **0007c1d8** / CoD **00037e64** request the target expression at
**1000 ms** of active dialogue time and update that cache. Page turns do not
restart this clock; leaving the line early does not force the target into it.

SHS `SHSPortrait::changeExpression:` **0006ad38** / CoD **00044dc8** use two
independent fill-both opacity tracks after that request:

| Layer | Delay after request | Fade |
| --- | --- | --- |
| New expression | 400 ms | 0 to 1 over 200 ms |
| Old expression | 600 ms | 1 to 0 over 800 ms |

Thus new art appears at dialogue time 1400–1600 ms; the old art finishes
fading at 2400 ms. The cache changes at the request, before the visual fade.
Outgoing portraits use the cached identity, as the native cached layer does.

SHS `addUIElement` **000210a0** covers the previous panel;
`removeUIElement` **00021fb4** exposes it again. Choices and other temporary
panels retain dialogue speaker/expression state rather than creating a fresh
speaker entrance on return. `clearUI` **00021c2c** and `runScript09` **00022a28**
dispose the old scene. Both games' `loadScript09NoGUI` (SHS **00020ab0**, CoD
**00011f2c**) clear the 200 script expression bytes and 200 last-expression
bytes. Names, art bindings and the hidden global portrait position survive.

**Verification boundary:** these recovered dialogue paths are shared by both
games and both rendering backends. There is no separate IPA layout or Swift
game-animation implementation. Special portrait decorations for expressions
6–9, service-16 whole-screen transitions and original-device recordings of
the nominal letter cadence remain outside the verified parity claim.

## Implemented text foundation and remaining UI work

### Dialogue Continue tab

Both iOS runtimes contain `GameModel::expandContinue`: SHS **00023020**
(default-label overload **00022f28**) and CoD **000103cc** / **000107cc**.
SHS `setBubbleSex` **00023db4** selects common-atlas frames **5 / 3 / 6 / 4**
for themes **1 / 2 / 3 / other**. These supplied frames are **99×17**, also
present in the APK common atlas. SHS IPA's UI adapter maps role 126 to 125;
CoD and APK keep 126. There is no generated replacement artwork.

`expandContinue` positions the tab center at
`(bubble.width - 49.5, bubble.height + 8.5)`. Its label uses SHS string **29**
or CoD **26**, centered in the tab. SHS `GameModel::init` **00024e48** binds
engine font `+0xb23c`; `initFonts` **0003c440** identifies white
**TrebuchetMS-Bold, 14**. The common renderer uses that role and each game's
own font resolution. The original CoD screenshots corroborate the tab beneath
the right edge of the box.

SHS call sites **0007dc60 / 0007dcdc** schedule its appearance from the text
layer's `m_endTypingTime`. `expandContinue` uses a **0.25 second** vertical
scale from nearly zero to one; it keeps its horizontal size. The shared
implementation starts this expansion at the existing typing-completion gate,
including early reveal and page turns. Save version 17 retains its visual
clock without changing the VM or tap-to-reveal/advance rules. Read-only native
memory and LLVM assembly supplement Ghidra's truncated Objective-C calls.

The separate bottom instruction uses SHS string 36 / CoD string 33, semantic
role 36, in footer layout 18's rectangle `(63,459,252,18)`: local Y 28 plus
footer origin 431. It uses centered ArialMT 11, white at alpha 176, above the
common footer art. It does not replace the animated Continue tab or change
its input gate.

Shared text rasterization uses translation-invariant half-up rounding for
glyph positions. Python's half-to-even `round` could move two glyphs with
different integer bearings in opposite directions at a half-pixel origin,
raising individual letters such as Continue's “i”. Layout metrics, advances,
pagination and saved font history are unchanged.

### Other shared presentation

Service 8's episode introductions and week cards now use the original PNG
font pairs 528/529 and 530/531, layout 48, full-screen background, shared footer
and native entrance/input behavior. [TITLE_SCREENS.md](TITLE_SCREENS.md)
records glyph placement, subtitle length branches, wipe/fade/scale clocks,
early-tap handling, save state and remaining promotional/transition limits.

Service 33's standalone Instructions/message panel now uses native layouts
24/15/25, blue skin, APK bitmap fonts, continuation label and footer. Its
one-second reading gate, raw-text contract and remaining presentation limits
are documented in [STORY_SERVICES.md](STORY_SERVICES.md#message-panel-service-33).

Offline surveys reuse this message panel for the local thank-you receipt.
That presentation is an explicit compatibility choice; Android 1.0.9's survey
upload path is disabled. The original questions and remaining story still
execute normally. See the [survey contract](STORY_SERVICES.md#offline-surveys-service-9).

`fonts.py` implements the supported descriptor schema, native integer parsing,
line fitting, source offsets, nominal line metrics, per-line indents, glyph
placement, and shared color toggles without a display dependency.
`desktop_text.py` draws actual APK atlas pixels with bounded glyph/layout caches.
`ContentLibrary.read_ui_asset()` reads exact `fonts/` and `images/` names from
the imported APK without extracting paths or entering the numeric resource bank.

`ui_assets.py` decodes the original layout and image packs. `dialogue.py`
computes native dialogue geometry and page breaks without pygame;
`desktop_dialogue.py` composes the original borders, masked portraits and text.
The scene is scaled 1.5 times for the default 480 × 720 window. Ordinary choices
now use the screenshot-based reconstruction described below. Title screens
and the full original menus remain provisional. The extra dialogue checkmark
has been removed: layout 18 contains the footer (common frame 47), gear (49),
and two hit/layout rectangles, but no confirmation image. Native common frame
41 is constructed for portrait selection by `000d2238`/`000d2dcc`; it remains
on that screen. Dialogue continues by touching the screen, consistent with APK
help string 145. Footer/gear artwork alone does not reproduce every original
menu callback.
Save version 4 retains presentation mode, palette selection, page position,
mini-game/random state, and dialogue animation state. Version-1/2/3 saves
migrate without replaying the current dialogue's entrance. Font/atlas caches
are not serialized.

Authored tests cover parsing quirks, advance-versus-kerning behavior, exact-fit
wrapping, byte boundaries, indents, negative initial gap, mixed color markers,
alpha/color modulation, image transforms/masking, layout references, narrator
selection, old-save migration and VM suspension during pagination.
Optional local tests parse all 18 fonts
and render all 35 opening presentation/dialogue screens, then both continuations
of the first saved choice. These pass, but are not screenshot/frame comparisons
against a running original game and do not establish full UI equivalence.

## Ordinary choice panels

The visual reference supplied for this screen is
`original-screenshots/surviving-high-school-iphone_1.jpg` (320 × 480): one
translucent, colored-border panel, an overlapping circular portrait at the
upper left, a two-line "Make your choice!" heading, a description, divided
option rows, and a gear above the dark footer. The two other supplied images
show dialogue, not choices. Additional period screenshots are collected in
[this 2011 episode walkthrough](https://kandyriot.wordpress.com/2011/06/28/surviving-highschool-howards-summer-bummer/);
screenshots from the Java/DSi editions are not interchangeable with this target.

`choice.py` computes the panel and hit rectangles independently of pygame.
`desktop_choice.py` draws them using the player's APK assets. The first real
New Girl choice now uses this path; it has no desktop episode-title strip,
numbered labels, separate dark buttons, or dialogue continue checkmark.
The heading and description still come from the pending KiWi service.

### Recovered inputs and artwork

Research evidence is in `native-choice-layout.c` (excluded from packages):

| Evidence | Contract used by the renderer |
| --- | --- |
| `FUN_000b07e8`, `FUN_000ae740`, `FUN_000d6800` | Ordinary/incremental choices share a panel; character property 651 selects its theme |
| `FUN_000aed50`, `FUN_000ae5d4`, `FUN_0009e5d8` | Reuses the character widget, requests expression **zero**, and passes portrait mode separately |
| `FUN_0009c034`, `FUN_0005afbc` | Mask before horizontal flip; mode 2 flips except theme 3; discard the final 12 masked rows before texture upload |
| `FUN_000d9038` | Header layouts 7/8/16, description layout 65, 44-pixel row allocation, and progressively tested description insets |
| `FUN_000858cc`, `FUN_000d6afc`, `FUN_0006bd5c` | Pajama Hip title atlas, Arial Rounded body/option atlas, and different title/description/option line metrics |
| `FUN_000d6800` | Translucent white panel color with alpha 243 and theme-dependent selection colors |
| Layout 18, common frames 47 and 49 | Original footer and gear artwork |
| `FUN_000d5878`, `FUN_000d9038`, `FUN_000d6afc` | Positive choice durations enable lower layout 22; ordinary choices hide its score-capsule root 13 and descendants |
| `FUN_000ad6b4`, `FUN_00082744` | Shared timed-choice widget: resource 708 under a radial sweep of 709, advancing from elapsed/total to 100 percent over the remaining time |

The title uses `PajamaHip26` for blue, `PajamaHip266` for pink, and the gray/gold
variants for other themes. Its nominal height/gap is 26/8; portrait headings
have second-line inset 20 for mode 1 or 5 otherwise (`0x002a8014/1c`). The
description uses `ArialRoundedMTBold16`, nominal height/gap 10/10; options use
the same atlas with 12/1. Nominal height changes the line origin, not glyph
bitmap size. Theme 1 text is RGB `(1,76,215)`, theme 2 `(166,45,45)`.

Description measurement uses width 246, nominal height/gap 16/10, and tests
one, two, then three insets from `(105,95,85)` for a visible portrait. The
negative native inset tables for the alternate header branch also exist at
`0x0025b858`; the current screenshot-based layout keeps the portrait at the
left and does not claim full equivalence for that alternate branch.

### Screenshot-based placement and remaining differences

The reference's panel starts at x=20 and is 280 pixels wide. The title field
comes from layout 7 node 9 (width 194), or layout 8 without a portrait. The
implemented placement, in downward coordinates, is:

```text
description_y = max(26, measured_title_height + 2)
header_height = ceil(max(portrait ? 112 : 38,
                         description_y + description_height + 6))
row_height[i] = max(44, ceil(option_ink_height[i] + 16))
footer_height = timed ? layout22.height : 20
H = header_height + sum(row_height) + footer_height
panel = (20, max(32, floor((480-H)/2) + 11), 280, H)
title_origin = (panel.x + header_node.x, panel.y - 9)
description_origin = (panel.x + 7, panel.y + description_y)
portrait_rect = (panel.x - 27, panel.y - 24, 128, 128)
```

These offsets are a reconstruction from the supplied screenshot, **not** a
claim that the complete native placement algorithm has been reproduced.
The Android binary contains both the 44-pixel allocation in `FUN_000d9038`
and a later Cocos renderer (`FUN_000d6afc`) with a **37-pixel** row pitch and
count-specific positions. This frontend follows the supplied screenshot's
44-pixel spacing. The APK's glyph metrics can also produce different line
breaks from the iPhone screenshot. Preserve that distinction when refining
platform/release fidelity; do not use a successful render as proof of equality.

Long options expand instead of truncating text; tall panels scroll above the
footer. This is a desktop accommodation, not a recovered original scrolling
contract. Hit rectangles follow that scroll, exclude the gear/footer, and
retain each original option index and enabled state. Hover tint, scroll offset
and the host menu are frontend state and are not included in game saves.

The gear opens a host Resume/Save/Load menu; the original settings/menu flow
remains unimplemented. Opening it suspends desktop timer ticks, and keyboard
choice shortcuts do not bypass it. Dialogue, choices and the appearance picker
share the recovered 12-row portrait crop and bottom alignment.

Timed choices now use the APK's circular timer and a separate lower panel from
layout 22, with its ordinary score capsule hidden. Node 10 supplies the clock
background rectangle; resources 708 and 709 are each 61 by 60 pixels. The
progress texture covers the base clockwise from twelve o'clock as elapsed time
increases (`001441b4`, `00138ac8`, `001388a8`). The static base is present before
the first active tick. The footer retains its ordinary instruction without the
prototype numeric countdown suffix. Nonpositive choice durations have neither
the timer nor its extra panel space. Word choices share the same sweep helper
and retain their separate score display.

The lower panel occupies the supplied layout's 60-pixel height below the last
row. This placement follows this frontend's existing 44-pixel rows and expanded
text; it is not the Android renderer's complete count-specific placement
algorithm. For tall lists, the timer remains pinned above y=421 while the choice
rows scroll in a reduced viewport. Option hit rectangles stop above it, so the
timer cannot select an obscured row. These scrolling rules remain desktop
accommodations. The native 0.2-second ordinary-choice entrance is still unmodeled.

The sweep derives entirely from the session's saved remaining milliseconds.
Rendering does not consume time, resume the VM or draw randomness. Both service
1 and incremental services 2–4 wait at exactly zero; the next positive active
tick applies the configured timeout selection, including any custom return
mapping. Pausing or losing window focus freezes both the clock and its display.

Verification covers the original New Girl choice and both VM continuations,
blue/pink themes, portrait-free panels, multiline/tall option lists, disabled
options, custom return values, scaled mouse coordinates, menu timer suspension,
save/load while a choice is pending, authored radial-sweep pixels, absence of
timers on untimed choices, scrolling around the timer and the exact expiry
boundary for both choice formats. The user images remain local references
and are excluded from wheel/source distributions.

## Mini-game presentation

Services 71, 94 and 96 now have session-owned game state and playable renderers.
[MINIGAMES.md](MINIGAMES.md) specifies their frames, rules, clocks, callbacks,
random streams and ABGR sprite/glyph payloads. Saves preserve the current game
and generated state; menu/focus pause does not consume game time.

Timed word choices reuse the theme's original panel, masked portrait and
37-pixel minimum rows. They include the native timer/score art and a 200 ms
label transition. Word/picture grids use atlas 446's colored tiles/arrows,
522/523's blue glyphs, episode-supplied symbols/backgrounds and the recovered
tilted-board projection. Their native white/orange CS fonts, measured tutorial
panels, portraits, time/score HUD, cloud borders, prompts and banner movement
are specified in [GRID_UI.md](GRID_UI.md). Football uses atlas 290's nested
field markings, turf, changing play symbols, coach art and fixed nine-target
input bounds. Its recovered help/legend, Arial and CS fonts, team/score HUD,
camera easing, countdown and result/selection animations are specified in
[FOOTBALL_UI.md](FOOTBALL_UI.md).
No artwork is embedded in the implementation.

These paths still need visual comparison with original recordings. Football
touchdown particles, internal score flights, parts of audio staging and the
final exit overlay remain incomplete. Grid tile
side faces, highlights, particles, ring pulses, flying score deltas, outgoing-board
generation timing and some overlay boundaries remain approximate. Fast grid pointer
motion does not interpolate skipped cells. Service 88 notices now use the
original font, portrait-relative placement, rising letters, fade and input
lifecycle, specified in [STORY_SERVICES.md](STORY_SERVICES.md#dialogue-notifications-service-88). See the
mini-game spec's verification boundary before treating a successful render or
unit test as proof of complete original behavior.

## Main menu

The desktop now starts at the main menu (or content setup on first launch).
Resources 6–9, 272, 532/533 and layouts 74/75/77/79 reconstruct its background,
logo/photo, staggered gold buttons, original lettering and lower-right controls.
Live button geometry is derived from `000df488` and `00147df8`; the 205px
placeholder rows in layout 74 are not the actual 184px buttons. The app uses
the ad-free arrangement and local episode selection in place of network/store
flows. Its setup/file picker, search and library management are desktop additions.

[MAIN_MENU.md](MAIN_MENU.md) records the native application states, original
command/string IDs, additional resource schemas, transition evidence, checkpoint
contract, executable startup and the remaining animation/list/options differences.
The presentation retains the shared 320×480 logical coordinate system and the
60 Hz desktop redraw loop. Menu transitions do not advance the suspended VM.

## What to implement early

Reconstruct one original dialogue/choice screen using the actual asset/font
paths and native layout rules, then use that foundation for additional UI and
minigames. Input timing, panel lifecycle, text pagination, and transition
completion belong in the modeled engine state. Record pending input and timing
state in saves as those native contracts are recovered.

Final adjustments to colors, borders, and small visual details can happen
incrementally. It would be costly to implement all minigames using provisional
layout/input rules and then discover that their original UI requires a different
state machine. The existing EXP decoder and VM can remain beneath the more
faithful frontend.

The UI assets and fonts must continue to come from each player's imported APK.
Do not embed their images, glyph tables, or converted asset packs in the runtime
distribution as a shortcut.

## Reproduce the asset inventory

From the research checkout:

```sh
uv run --locked python tools/audit_ui_assets.py surviving-high-school-1-0-9.apk > docs/ui-assets-audit.json
```

`ui-assets-audit.json` records descriptor/atlas hashes,
font metadata, named-image dimensions, and the metadata discrepancies. The
audit does not extract or publish the original graphics. Native addresses above
refer to SHA-256
`b17aa4c71bc46666d414cafae6fac92bbcd755f3dcccd73975cf05f4a119665b`.

## Character appearance selector (service 78)

The native layout, circular hit regions, original index mapping, 50 ms swaps,
masked/cropped portraits, selected versus faded appearance, prompt font and
checkmark are implemented. See [STORY_SERVICES.md](STORY_SERVICES.md#portrait-selection-service-78)
for geometry, asset IDs, native addresses and save fields. Tests cover all five
Homecoming Queen appearances and release input in a resized window. Selection
uses common frames 43/44 (the fifth portrait argument is 1), not the dialogue
ring pair. The pressed-checkmark tint remains a visual refinement.

## NPC relationship indicators

The original game does display relationship emotes around NPC portraits. This
is shared engine behavior, with per-character suppression rather than a
Football-Star-only UI path. The desktop now renders the original icons and
gain/loss effects during dialogue, with their state and timing saved.

`FUN_000ab048` prepares the indicators for a visible character ID greater than
zero; `FUN_000a90f0` selects the asset from numeric state:

| Condition | Result |
| --- | --- |
| NPC-owned key 629 equals 1 | Hide indicators |
| NPC-owned key 407 (`0x197`) is negative | Skull, resource 3011 |
| NPC matches global key 601 and relationship is nonnegative | Heart, resource 3010 |
| Otherwise | Smiley face, resource 3012 |

`FUN_000ab048` maps relationship key 407 (`0x197`) to indicator count: -3→3, -2→2,
-1→1, 0→1, 1→2, 2→3; other values use 4. Tables at 0x0025b31c/324 map the
base icons to loss-ring/effect resources 3013–3018. Inspection of the actual
APK confirms a heart, skull, smiley, pink/green/yellow rings, broken heart,
red-eyed skull and surprised face. No semantic labels have been inferred from
filenames.

Both native functions read key `0x197`; the earlier documentation and runtime
lookup of key 403 were incorrect. Football Star supplies a regression case:
Adam (character 10) has key 407 set to -1 at scene 25006's dialogue PCs 445 and
453, then -4 at PC 462. His indicators therefore change from one skull to four.
The scripts write this property through service 52; the VM already preserved
the correct values, including in saves. Existing saves keep their current
dialogue animation, and the next NPC dialogue refreshes its indicators from
key 407 without a save migration.

`FUN_000ab048` reads the previous icon/count from NPC-owned numeric keys
3000/3001. A previous count of -1 suppresses change animation; otherwise any
icon/count difference requests the effect. Missing keys read as zero, so an
NPC's first appearance can animate its initial icons. It then writes the new
icon/count back to those keys **before** the dialogue callback. The runtime
does this in `EngineState.present_dialogue`, once; drawing and save restoration
do not replay the writes or the sound. Invisible portraits, player ID 0 and
narration do not update these caches. Choice portraits explicitly clear their
decorations (`FUN_000ae5d4` → `FUN_0009d60c(...,0,0)`).

The recovered geometry from `FUN_0009bacc` and `FUN_0009ce2c` is:

| Slot | Child position (GL) | Child rotation | Parent resting rotation |
| --- | --- | --- | --- |
| 0 | (61,16) | -190° | 195° |
| 1 | (62,17) | -210° | 215° |
| 2 | (62,18) | -230° | 235° |
| 3 | (64,19) | -250° | 255° |

The rotating parent is at the portrait origin. Cocos angles are clockwise in
GL coordinates; the child is anchored at its center. These transforms place
the resting icons around the upper-left edge of an NPC portrait, with a net
5° tilt. Indicator parents are siblings of the head's scaled node, so they
do not inherit its entrance scale or its horizontal portrait-image flip.
Ordinary NPC portraits use the right-side layout-17 center (263,284) after the
dialogue's 485-y conversion. No image, mask or sprite data is embedded in code.

For a changed speaker, initial visibility waits until its portrait entrance
ends: 550 ms normally, or 850 ms if the outgoing portrait occupies the same
side. Repeated speakers have zero indicator visibility delay. In the rules
below, D is that delay and t is active time since the dialogue began:

- **Unchanged/sentinel:** show the current icons at t=D without an effect.
- **Gain:** for the same icon, animate slots starting at the previous count;
  for a changed icon type, animate all slots starting at zero. Let N be the
  number of animated icons and T=300+200×(N-1) ms. Their starts are
  D+200×j ms. Each parent rotates from zero to its resting angle over T,
  using the **shortest arc** (the `RotateTo` start code at 0x00146a88 wraps
  differences outside ±180°). This is not a long clockwise revolution.
- **Gain flash:** attach the matching ring (3013/3015/3017) at the icon center,
  initially scale 0.5 and alpha 200. At D+200×j+300 ms it scales to 2 and
  fades to zero over 500 ms (`FUN_0009caf4`, `FUN_00136450/001364c4`).
- **Loss of count, same icon:** retain lost slots using effect resources
  3014/3016/3018. At t=1000 ms their parents begin moving to GL (0,-500)
  over 1000 ms, independently of D. The remaining icons keep their positions.
- **Character 45:** the native path suppresses gain animation; a hidden-icon
  request clears its decorations explicitly.

`FUN_0009ce2c` returns an additional dialogue delay: T for a gain, 600 ms for a
loss, otherwise zero. `FUN_000aaa40` adds it to the name/text start sequence.
The last icon can still be moving after text starts, because its stagger and
T are separate. The relationship clock continues independently of text reveal
and survives a page turn; pagination does not replay the effects.

`FUN_000a916c` chooses these sound resources:

| Transition | Sound |
| --- | --- |
| Same icon, count decreases | 8008 |
| Same skull, count increases; or any recognized icon becomes skull | 8006 |
| Same smiley/heart, count increases; skull becomes smiley | 8009 |
| Smiley/skull becomes heart | 8015 |
| Heart becomes smiley | 8016 |
| No change, sentinel -1, suppressed icon or unrecognized previous icon | None |

Save version 6 stores a `RelationshipChange` with the following fields, plus
a `RelationshipAnimation` clock in `engine.dialogue_animation.relationship`:

| Field | Contract |
| --- | --- |
| `character_id` | Positive signed 16-bit visible NPC ID |
| `asset_id` | -1, 3010, 3011 or 3012 |
| `count` | Integer 1–4 |
| `previous_asset` | Signed 16-bit cache value; zero is a valid absent-cache value |
| `previous_count` | Integer -1–4; -1 is the native animation sentinel |
| Animation `change` | The above immutable descriptor, also in pending `details.relationship` |
| Animation `delay_ms` | Integer 0–850 |
| Animation `elapsed_ms` | Integer 0–derived duration, independent of page/reveal time |

The descriptor must match the current portrait and its saved cache entries.
Effect poses, sound choice and extra dialogue delay are derived, not serialized
as image frames. Older dialogue saves initialize settled icons and caches
without changing their saved text progress or replaying sounds.

Tests cover smileys, hearts, skulls, suppression, the count mapping, cache reads
by actual VM services, frame-rate-independent gain/loss timing, shortest-arc
rotation, sound transitions, save validation and exact restored pixels using
the user's original artwork. Native reused-widget edge cases remain partial:
the low-level asset=-1 call can retain stale children except for character 45;
the runtime clears suppressed indicators instead of preserving stale emotes.

Local initialization confirms Football Star leaves the suppression flag clear
for its NPCs; Homecoming Queen sets key 629 to 1 for many NPCs. The New Girl
also leaves it clear for the sampled characters. This verifies the user's
memory while keeping the distinction between engine capability and individual
episode configuration explicit.


## HD vector text

The HD binary has no bitmap fonts. `SHSEngine::initFonts` (`0002af38`) builds a
CGFont per face -- `ArialRoundedMTBold`, `ArialMT`, `TrebuchetMS-Bold`,
`TrebuchetMS-Italic` from the system, and Pajama Hip and a digit font
(`MonoNumerals`) from TrueType resources 568 and 567 in the app bundle -- and
`CSFont::init` gives each instance a size and an ARGB color. Every size is
exactly twice the number in the matching Android font name (Arial Rounded
11/14/15/16/20/22/28/30 -> 22/28/30/32/40/44/56/60, Pajama Hip 26 -> 52,
Trebuchet 14 -> 28), i.e. the layout unit count. Theme colors: blue
`0x2968dd`, pink `0xb44e4e`, gray `0x898989`, gold `0xb46d1a`; the Android
theme colors carried by the shared text styles are mapped onto them. Pajama Hip
comes as a fill instance and a `CSFont::setStroke` instance (width 8 at size
52, drawn under the fill, so 2 layout units of outline outside the glyph; the
stroke color is not legible in the decompile and is read as white from HD
screenshots). `CSFont::getCharAdvance` is the glyph advance times size over
unitsPerEm, drawing is per-glyph `CGContextShowGlyphsAtPoint`, and there is no
kerning.

`vector_text.VectorFont` is a `BitmapFont` with those advances and ink boxes,
so `layout_text` (wrapping, indents, ink bounds) runs unchanged and vertical
placement keeps the Android font's own line height and baseline, which the
panel calibrations were taken against. It is used only when an HD app bundle is
imported; otherwise the Android bitmap fonts are kept. The Android `Arial
Rounded` atlases carry `info face="Dialog.bold"`: they were generated from a
generic Java font, so their advances differ from HD's. With real advances, the
"parking ticket" choice wraps exactly as the HD screenshot does, which it did
not with the atlases.

Font files come from the player's machine, in this order: an override
(`SHS_ARIAL_ROUNDED_FONT`, `SHS_ARIAL_FONT`, `SHS_TREBUCHET_BOLD_FONT`,
`SHS_TREBUCHET_ITALIC_FONT`), then Arial Rounded MT Bold (macOS ships it,
Office installs it on Windows), then the nearest Arial-metric face (Arial Bold
on Windows/macOS, Liberation Sans / Arimo Bold on Linux). Those fallbacks are
about 4-6% wider than Arial Rounded and have square terminals. Set
`SHS_VECTOR_TEXT=0` to keep the bitmap fonts.

Wrap widths, checked against HD screenshots with real advances: option text in
the choice panel wraps at Android's 264 (the "parking ticket" choice breaks
exactly as `IMG_0085` does), and the dialogue body wraps at the 246 it is
*measured* at rather than the 260 box width (the "Um... You're... I / mean...
Um... Let's do / that kissing thing?" line in `IMG_0069`). Android's bitmap
fonts keep their own 260. Portrait art in HD is drawn at its own 2x size (226 x
256 = 113 x 128 units), which with the 12-row crop spans exactly the outer
ring's top to the inner ring's bottom in that screenshot.

Text placement: the Android font descriptors' `common base` is not a baseline
(it says 26 for nearly every font), so a vector font's baseline is the bitmap's
own capital-H bottom less its padding row; Pajama Hip keeps its descriptor base
(26), which matched HD. Against `IMG_0069` and `IMG_0070` the dialogue body
origin moves (+6, +6) for vector text (lines then sit 24, 46 and 67 below the
box's top line, the first starting 17 from its left edge), the portrait ring's
center sits 5 units below the top line (`_HD_PORTRAIT_VERTICAL_OFFSET`), and the
ring frames are drawn under the body text. The bottom bar's hint is bank-13
string 36 (dialogue), 38 (choice) or 40 (timed choice), all seen in HD.

Not converted, on purpose: Pajama Hip `S26` (the Strength Up notice, red
`244,65,31` with a baked white outline) and `mainmenu` (Android: Comic Sans MS
Bold Italic). HD's `initFonts` has no Comic Sans and no red Pajama Hip; its
only red text face is Trebuchet Italic 40 (`0xf0513c`, strokes 3 and 9), which
may be the notice's real face but has no HD screenshot to confirm. They stay
bitmap until there is evidence. Not verified: HD's line pitch beyond these
samples and any dialogue with fewer than three lines.
