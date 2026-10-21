# Word and picture grid presentation

Service 96 uses a separate renderer from the dialogue panel and the service-71
timed word choices. This document describes the recovered Android 1.0.9 layout
in a **320 x 480**, top-left-origin viewport. Positions scale together when the
desktop window changes size. Rules and script records are in
[MINIGAMES.md](MINIGAMES.md#5-service-96-word-and-picture-grids).

Evidence is the locally inspected `libshs09.so` and SHS iOS `Surviving_HS`;
addresses below identify iOS explicitly where applicable. No native code or original art
is included in this repository. All artwork, fonts, labels, episode text and
portraits are read from the player's imported content.

The shared renderer projects solid tile faces, culls back faces and sorts
visible polygons by camera depth. Desktop uses a Pillow perspective map;
iOS receives the same inverse map and cached source texture for native bilinear
sampling. Neither camera nor game geometry is duplicated in Swift. Tile art
is cached by face, letter, picture and shine frame. Flat arrows retain the
batched scanline path. Authored tests cover texture orientation, perspective,
clipping, alpha, cache reuse and cube faces at successive flip angles.

## Resource and font contracts

`000c6944` loads these paired CS fonts and atlases:

| Resources | Use | Native metrics |
| --- | --- | --- |
| 510 / 511 | Orange-outlined word prompts and central banners | Height 52, tracking -6, line gap 0 |
| 512 / 513 | White italic headings, tutorial titles, time, score and score changes | Height 27, tracking -3, line gap 1 |
| 516 / 517 | White tutorial body | Height 16, tracking 1, line gap 0 |
| 522 / 523 | Blue tile letters | Height 85, tracking 0, line gap 1 |
| 446 | Tiles, arrows, cloud edges, haze and tutorial frame | Literal frames described below |
| 499 | Portrait ring | 148 x 152 |
| 502 | Cloud behind each portrait | 167 x 148 |
| 496 | Loaded portrait-related texture | 133 x 150; no active drawing reference established |

These are atlas glyphs, rather than substitutes from the dialogue's named
BMFonts or the operating system. The second byte of the metrics header,
previously named `style` by the parser, is a **signed line gap**: `000538ac` stores it at
font offset `+0x139`, and `00054490` adds it to each line's height. Horizontal
tracking is header byte 2. Width measurement omits the final tracking interval.

Wrapping uses glyph widths, backs up to a space when a word will not fit, and
splits an overlong word at the last fitting glyph. Leading spaces are discarded
on each line. Explicit newlines, including empty paragraph lines, count toward
height. An ending newline does not add a further empty line. Missing glyphs
use the original opposite-case lookup, then space advance. Evidence:
`00052f88`, `000534a8`, `000535fc`, `00053130`, `00054490`.

Time and score use the width of glyph `3` for all digits (`00053718`). Time is
rounded up to seconds and padded to three digits; score is padded to five.
Labels come from resource 13, entries 32 and 33. The target score appears in
the opening and result banners; there is no extra score/target row or round
progress bar beneath the board in the recovered renderer.

## Stable layout

| Element | Placement / behavior |
| --- | --- |
| Background | Service argument, centered at (160, 240) |
| Rotating haze | Atlas 446 frame 3, centered at (160, 240), scale 1.8 |
| Cloud edges | Atlas 446: bottom 0 at y=429, top 4 at y=0, left 1 at x=0, right 2 at x=273; repeated and scrolled |
| Left NPC | For art size `(w,h)`, center `(w//2+10, h//2+17)` |
| Right character | Center `(310-w//2, 487-h//2)`; flip horizontally unless NPC property 651 is 3 |
| Portrait ring | Center 12px above the character center |
| Portrait cloud | Center 0.5px right and 2px above the character center |
| Time label | Right edge 196, top 2 |
| Time digits | Right edge 206, top 22 |
| Score label | Right edge 278, top 2 |
| Score digits | Right edge 310, top 22 |
| Heading lines | (110,60), (104,80), (95,100), at most three explicit lines |
| Settled word prompts | Scale .65, centers at y=377, 402, 427; left origins approximately x=15, 38, 61, subject to integer rounding |

Portraits retain their original size and transparency. The word game does not
use the dialogue's circular crop or place two enlarged characters along the
bottom. The native portrait circles can extend beyond the viewport; that
clipping is intentional. Evidence: `000c98c0`, `000cbb5c`, `000c6220`,
`000c1ca8`, `000c6ebc`, `000c39c0`, `000c5400`, `000c8790`.

The desktop pause gear remains available at the lower left. The provisional
full-width dialogue footer and duplicate instruction line are removed, so
they do not obscure the right portrait and bottom word list. That pause control
is a desktop accommodation; its placement is not evidence for a native grid
footer contract.

## Tutorial panel schema

For a tutorial record's `tutorial_text`, `tutorial_title` and
`tutorial_position`, `000c5da0` computes:

```text
column_width = 286
body_height = wrapped_text_height + 20
center_y = body_height / 2 + 30           when position == 0 (top)
         = 480 - (body_height / 2 + 30)   when position == 2 (bottom)
         = 240                          otherwise (center)

x = 160 - 153 * scale
top = center_y - (body_height + 23 + 15) * scale / 2
body_y = top + 23 * scale - 1
```

Draw atlas 446 frame 47 (306 x 23) at `(x,top)`, frame 45 (306 x 1)
stretched to the body height at `(x,body_y)`, and frame 46 (306 x 15) at
`(x,body_y+body_height*scale)`. The body text starts at
`(x+10*scale,body_y+10*scale)`; the title starts at
`(x+22*scale,top-6*scale)`. All pieces share the same scale and opacity.

This measures the entire paragraph rather than shrinking it to a fixed box.
For example, a 128px body text height produces a top panel from y=11 through
y=196, or a centered panel from y=147 through y=332. The panel is translucent
and draws over the other game elements, as in the native draw order.

The initial tutorial waits 3200ms, then grows/fades in over 500ms. Subsequent
pages enter over 500ms after the board transition. A completed page shrinks
over 500ms. `hide_board` and `tap_to_advance` remain script-supplied flags.
Timed exercise pages can show a top instruction while the grid remains usable.
Evidence: `000cea80`, `000d02c4`, `000d1124`, `000cda28`.

## Movement and banners

Headings slide from the right, with three staggered lines and the native
overshoot curve (`000c29a8`). Orange word prompts initially grow near the
center, pause, then move to the bottom-left list (`000c8598`). The list and
heading fade while the outgoing board leaves.

Tile changes retain the previous board for presentation. Equal-size animated
boards turn from the old letters to the incoming letters; a dimension change
shrinks the old board before the new board grows. Tile staggering follows
`80 * (height - 1 + column - row)` milliseconds. Flips turn about the Y axis
with a 700ms clock; tile pops use the 600ms overshoot curve with parameter .8.
The individual countdowns also advance while their delay remains positive;
only the frame crossing below zero uses its overshoot. The pose stays at its
starting value until the delay expires. This can make a late tile jump forward
and must not be replaced by an elapsed-time-minus-delay approximation.
Growth and shine expire strictly below zero; flipping expires at zero.
Shine's crossing frame reads the retained growth delay in both binaries.
Evidence: Android **000c1d88**, iOS **00096e14**. Isolated execution of both
functions matches saved clock fields across five delays and five frame sizes.

Only phases 1–6 tick the cubes; initial tutorial phase 0 holds their clocks.
The shine wait also uses those active board ticks. Frame selection retains
Android's float32-then-double truncation at the exact 100ms boundaries.

Immediate replacements and equal-size flips generate the incoming board at
phase-4 entry. Shrinks retain the outgoing board and random state for 800ms,
then generate the incoming board on advance. Native **000d0ff8** / iOS
**00097a48** uses `(retained_index+1)%table_count` in that deferred path,
including tutorial transitions; the immediate path instead uses the explicit
peeked destination. The model preserves this distinction. Native execution of
iOS **000983a8** and **00097a48**, with lookup/generation stubs, confirms the
different index and call boundary. No board generation runs during rendering.

SHS iOS `draw3DCube` **00095f34** defines a 450×450×100 solid, at
`(column*522+225, row*522+225, -50)`, with normal faces 15/16, selected
43/44, highlighted 41/42 and bad-prefix 33/34 in atlas 446. Both front and
back carry upright letters; the back retains the outgoing board during a
flip. The fifth row's bottom cap extends ten units. `setup3DTransform`
**00095338** uses the shared 30-degree camera; depth is -3800 for five rows,
-3400 for 5×3, 4×4 and 5×4, otherwise -3000. Native `draw3D` **000942cc**
uses a depth buffer; the shared software path instead sorts nonintersecting
cube faces. It does not claim identical GL edge rasterization.

Shine frames 35–40 play over 600ms with the same stagger, triggered 4000ms
after committing round visuals (`setGlintEffect` **00096f58**, commit
**00098894**). Successful words scatter eight fragments per selected tile,
using frames 17–32 at twelve frames per second, then pop the tile back in.
There are at most twenty live bursts. Evidence: Android **000c3cb0**,
**000d072c**, and iOS `CubeExplosion::init` **0009542c**, draw **000946ac**,
tick **00097c0c**, selection **0009a2fc**.

Highlighted start tiles dim as the round countdown expires. Commit shuffles
the offsets `int(3000*i/start_count)` with one full-range random swap per
start, then assigns them in column-major order. A highlight's opacity is
`clamp((round_ms-offset)/3500, .1, 1)`; valid selected tiles use the first
selected cell's offset and `clamp((round_ms-offset)/7000, .7, 1)`. Bad-prefix
tiles remain fully bright. This is a countdown, not time since selection.
The native draw first puts a black normal cube behind a dimmed colored cube;
letters and shine remain opaque. Evidence: Android **000c43ec**/**000c94f8**,
iOS **00099424**/**00095858**/**00095f34**. Isolated Android ARM execution
matches all 0–25 start counts with four seeds, plus selection/highlight
opacity and black-underlay calls at countdown boundaries.

Each fragment consumes twelve native engine random draws: signed offsets below
50 for X/Y, signed X velocity below 250, signed Y velocity below 350 minus
250, signed spin below 360, absolute angle below 360 and sprite age below
5000ms. Each signed draw uses two RNG advances. Scale is
`1+(tile_screen_y-150)*.0024242424`; gravity is 1600 pixels/second².
Fragments retire at Y≥480. These are model side effects, so subsequent board
generation sees the native draws; a render or restore consumes none.

Blue hint arrows and orange player-trace arrows use atlas 446. Orange arrows
have eight separately drawn frames, rather than rotating the rightward art:
right/up-right/up/up-left/left/down-left/down/down-right use
6/12/13/7/8/9/10/11. The hint uses frame 5, rotated. Each arrow is projected onto
the board between adjacent cells. A player's trace covers its matching hint.
Evidence: `000ca9b4`, `000c6db8`, `000c6a48` and tables `0025b7ac`, `002a80cc`.

Banners use font 510, centered as one multiline block at (160,240), with no
dialogue box. Their scale and opacity grow during the entrance. Opacity begins
falling after 60% of the hold period, following `000ccb68`.

| Banner | Text source | Entrance / hold, ms |
| --- | --- | --- |
| Ready | Resource 13 entry 80 | 700 / 800 |
| Target | Entry 59, formatted with the target | 700 / 1300 |
| Success / failure | Service-96 arguments | 1300 / 700 |
| Time expired | Entry 57 | 1600 / 1000 |
| Result | Entry 81, score and target | 2600 / 2000 |

Successful tutorial pages suppress the ordinary success banner. Banners have
their own lifetime and may continue across a board phase change. Evidence:
`000cba10`, `000c488c`, `000d02c4`, `000d1124`, `000ccb68`, `000c8408`.

## Saved presentation and verification

Save version **7** adds these fields to `engine.word_grid`:

| Field | Schema |
| --- | --- |
| `visual_ms` | Nonnegative active time, capped to the exactly representable integer range; drives decorative movement |
| `board_entry_ms` | 0–2000ms entrance progress; continues across the target banner into phase 2 without restarting the tiles |
| `banner` | Null or `{kind, enter_ms, hold_ms, age_ms}`; kind and timing pairs validated against the table above |
| `transition` | Null or `{problem: GridProblem, board: [byte-character], starts: [cell-index], tutorial: bool, mode: "replace" / "flip" / "shrink"}` |

Version **18** adds `pop_ms` (cell-index to 0–601ms remaining pop/delay),
`glint_ms` (-4000 through 100,000,000ms visual clock), and `explosions`
(up to twenty lists of one to eight fragments). Each fragment stores finite
`x`, `y`, `scale`, `vx`, `vy`, `spin`, `angle` and integer `age_ms`.
Bounds, timers, cell indices and fragment counts are validated on load.
Versions 1–17 start the new effects inactive, retaining their original RNG
state; omitted historical particle draws cannot be reconstructed.

The existing `tutorial_entry_ms`, `phase_ms`, score and game clocks are also
used for drawing. Rendering and pointer geometry do not advance clocks or draw
random numbers. The desktop freezes these fields while paused or unfocused.
Saving during motion restores the same pixels and retained VM frame.

Version 1–6 saves remain readable. Old grid saves retain their exact board,
selection, score, random state and pending VM call. Missing decorative time
starts at zero and missing banner/outgoing-board state starts null. Their
historical animation frame cannot be recovered from those older saves. Their
tile entrance starts settled (`board_entry_ms=2000`).

Version **22** adds native score flights. Android **000cd2c0** starts each
successful word's points at the projected center of its first selected cell.
**000c7b9c** moves the text to `(260,42)` over **400 ms**, with smoothstep
interpolation and font 512. The unit-scale drawTextEx anchor does not change
that text origin. **000c2a98** collects arriving flights, transfers points at
**800/s**, then holds the final delta for **300 ms**. The HUD counter eases
toward that transferred total, independently of the immediately committed
game score. The Android draw path **000c7cdc** uses `(280-width,width+62)`
during transfer and `(310-width,42)` during the hold; the iOS implementation
uses the latter position for both. The common renderer retains Android.

`score_effects` stores `{value:int, x:float, y:float, remaining_ms:int[1..400]}`;
`score_pending`, `score_phase`, `score_target`, `display_score` and the existing
`delta_ms` retain the counter stages. Validation checks finite positions,
positive flight values and conservation against the committed score. Versions
1–21 start with their saved score already displayed and no fabricated flights.

Version 22 also retains `highlight_offsets` (cell index to 0–2999 ms) and
the departing transition's `highlight_offsets` and `round_ms`. Committing
round visuals consumes the native highlight shuffle, even for fixed tutorial
boards. Rendering and restoring do not shuffle. An older save uses null for
unknown offsets and retains full brightness until the next commit.

`tiles` contains each cell's flip/growth/shine active flags, remaining clocks
and delays, plus the shrinking flag. It uses the existing row-major board
order. Transition `deferred` records whether the next board still needs to be
generated. Old saves use null tile state and `deferred=false`, preserving
their prior board, random state and elapsed-time motion until a new setup.
The legacy `pop_ms` field stays empty for new cube state. Rendering does not
advance these timers; snapshots during either half of a board change resume
the same native clocks and random stream.

The portrait ring also follows Android **000c98c0**: three staggered writes
to the same retained ring during entrance, then the absolute sine pulse at
`.8 * pi` radians per second, shrinking at most .15. Its last active entrance
write wins. The iOS immediate-mode path **0009ab88** draws three rings instead;
that difference does not introduce a separate IPA minigame layout.

Verification includes authored font/layout and save tests, plus optional
player-content rendering and resized-pointer tests. Football Star's sixteen
tutorial records and subsequent 4 x 4 boards have been rendered and visually
inspected locally. These checks do not establish pixel equivalence with an
original device recording. Fragment initialization/ticks now round at native
float32 operation boundaries. Isolated ARM checks match Android **000c3cb0**
initialization (96 draws for eight fragments) and Android **000c1fcc** / iOS
**00097c0c** updates through expiration. Rendering now uses per-pixel reciprocal
depth, including transparent depth writes and equal-depth replacement, in both
shared backends. Original GL edge sampling and depth-buffer quantization still
need device comparison.

The iOS ending overlay eases to black over 800 ms and holds until the 960 ms
callback. Board/gameplay clocks stop on entering that exit phase, including
its final callback tick. No visual effect substitutes a result or resumes the
VM without play.
