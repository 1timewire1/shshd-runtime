# SHS mini-game contracts and asset schemas

Revision: 2026-09-13. Reference: Android SHS 1.0.9, `lib/armeabi/libshs09.so`,
SHA-256 `b17aa4c71bc46666d414cafae6fac92bbcd755f3dcccd73975cf05f4a119665b`.
Addresses below are Ghidra virtual addresses with image base `0x10000`.
The three mini-game families in this dispatcher are services **71, 94, 96**.
Their rules run independently of pygame and return results to the original
KiWi instruction stream. This is an implemented subset of the original engine,
not a claim of complete episode support or verified pixel/frame equivalence.

## 1. Common conventions

Arguments and table members are signed 16-bit KiWi words. Table addresses are
**word addresses**, not byte offsets or resource IDs. Packed KiWi strings are
Latin-1 bytes, high byte then low byte per word, terminated by NUL; dynamic
references `0x7ff5..0x7fff` address the engine's eleven string slots. See
[VM_SPEC.md](VM_SPEC.md) for addressing, stack frames and yield suspension.
`raw(ref)` resolves text only; `text(ref)` additionally applies substitutions.
List strings use literal `|` separators; a trailing whitespace-only field becomes
an empty last entry. Word matching is case-sensitive byte matching.

Each game owns its generated state, scores, active timers, input phase and audio
requests. Rendering must not consume random numbers or choose outcomes. The
pending VM frame remains intact until the terminal callback. Time is in integer
milliseconds in this engine; native panels use floating-point milliseconds.
Football and grid updates cap each supplied frame interval at 250 ms. Service
71 does not have that cap. Desktop focus loss and the gear menu suspend active
time. Ordinary input does not invent a result to dismiss an unfinished game;
the optional skip cheat below is an explicit user-selected override.

| Service | Return in VM R | Other callback effects |
| --- | --- | --- |
| 71 | Score, narrowed to signed 16-bit | Writes UI result cell 0 to the same word |
| 94 | Home score minus away score, narrowed to signed 16-bit | Stores both final scores for service 95; UI result cells unchanged |
| 95 | Home score if selector is 1, otherwise away score | Immediate query; the runtime rejects a query before scores have been established |
| 96 | 1 if score meets/exceeds the target, otherwise 0 | UI result cells unchanged |

Evidence: `000add90`, `000b10d8`, grid virtual result method `000c1bc4`, football
completion `000c0310`, dispatcher cases 94–96. Native football writes
application offsets `+0x6aaec/+0x6aaf0`, which correspond to scene offsets
`+0x1c0c/+0x1c10` with the scene at application `+0x68ee0`.

### Optional minigame skips

**Options → Cheats → Minigame skips** is an authored feature, disabled by
default and saved separately from Answer hints. Before **each** service-71,
94 or 96 minigame, the shared desktop/iOS player uses the native system-menu
skin to offer **Skip with success**, **Skip with failure**, and **Play minigame**.
Timers, introductory animation and game input wait for this decision. A native
scene reveal may finish first. Choosing Play releases the original entry gate
and saves that decision for the current call; resuming it does not prompt
again. The next minigame gets a new prompt, even in the same scene. Existing
saves already in play are not interrupted. Both skips remain available from
the pause menu while that minigame is active and the preference is enabled.

This covers SHS football and word grids, plus the four-option word-selection
game shared with CoD. The inspected CoD collection contains service-71 calls;
its services 94/96 are not SHS minigames. Ordinary choices, including timed
services 1/4, character selection and unknown services never receive this
prompt and cannot be completed by `Session.skip_minigame()`.

Skip outcomes deliberately override normal play, then use its existing VM
callback: word selection returns **32767** for success and **0** for failure,
including result cell 0 and any queued native scene transition. Service 71
supplies no success target; these are a maximum positive signed-word score
and a zero score, and the episode still decides how to interpret them.
Football preserves starting scores where possible, puts the requested winner
at least a touchdown ahead within 0–32767, and updates both service-95 scores.
Grid skipping returns **1/0** directly, including a requested failure of a
zero-target tutorial. Football/grid callbacks leave UI result cells unchanged.

Initial setup uses the usual random draws; skipping does not simulate rounds
or consume their future random draws. Subsequent script execution and native
scene transitions keep their own effects. The optional `minigame_started`
pending-action flag is validated as a boolean and needs no save-version bump.

## 2. Random streams

There are **two independent streams**. Both are saved with the session.

### 2.1 Choice-panel libc stream

```text
state:u48 initially 0x1234abcd330e
state = (state * 0x5deece66d + 0xb) & ((1 << 48) - 1)
next() = state >> 17
below(n) = next() % n              # n > 0
```

The service-71 mini-game choice panel uses `lrand48`, including its shuffles. This matches
the Bionic/POSIX default state and the recovered native calls. First outputs:
`851401618, 1804928587, 758783491, 959030623`. The runtime starts this stream at
the default for each new session; it does not emulate a single libc stream
shared with other episodes and all application panels.

### 2.2 Football/grid engine stream

```text
state:u32 initially CPU process clock in microseconds, low 32 bits
product = state * 0x41c64e6d + 0x3039  # retain full product
state = product & 0xffffffff
value = signed32((product >> 16) & 0xffffffff)
next() = abs(value)
below(n) = next() % n
signed_below(n) = below(n) with sign chosen by a SECOND next() & 1
```

Evidence: seed constructor `0004c248`, initializer `00126fa8`, generator
`00122554`, wrappers `0004c1bc/000b1394/000b13f8`. This is **not** ANSI rand's
15-bit result. Seed 1 produces `16838` then `1507104382`; stored states are
`1103527590` and `2524885223`. Native explicit seed 0 maps to `0xaaaaaaaa`;
the native default constructor passes -1 to select `clock()`. Python's explicit
`NativeRandom(state)` accepts an already initialized state for saved replay.
Native signed `abs(INT_MIN)` overflow is not emulated. Service 27 and ordinary
choice shuffling (service 4, `000aeee4`) share this stream; the latter consumes
one draw per option. See [ENGINE_ABI.md](ENGINE_ABI.md#46-services-14-ordinary-choices).
Other engine random services and their application-wide lifetime remain outside
this implementation.

## 3. Service 71: timed word choices

```text
word_game(
  a1:raw_text_ref,          # supplied title; this helper replaces it with empty title
  a2:raw_text_ref,          # instructions/description
  a3:raw_text_ref,          # positive choices, pipe-separated
  a4:raw_text_ref,          # negative choices, pipe-separated
  a5:s16,                  # total duration, milliseconds
  a6:s16,                  # character ID
  a7:s16,                  # portrait mode
  a8:s16                   # refresh counter, milliseconds
)
```

The supported configuration requires at least two positive entries, three
negative entries and positive duration. Native rejection loops assume those
list lengths; malformed configurations remain explicit stops here.

A deal samples one positive index and two distinct negative indices. A random
bit selects the fourth entry's category; rejection sampling avoids reusing an
index from that category. Then **twenty pairs of random indices in `[0,4)`**
are swapped. Entry identity is by list index, so equal text in different list
positions is not deduplicated. The four weights remain attached to their text.

Input is ignored during the first 400 ms. A selected positive/negative item adds
`+1/-1`, clamps score to zero, requests sound `8001/8002` in SHS or `8003/8004`
in CoD, deals again and starts the 200 ms label transition. Its value is not a
story choice index. Expiry uses
`remaining_ms < 0`, strictly: at exactly zero the frame remains pending. The
refresh counter is decremented and saved, but the inspected Android tick does
not redeal when it expires. Do not add an automatic reshuffle based on that
counter. Evidence: `000af010`, `000afee8`, `000af32c`, `000ae4f4`, `000b06bc`.

Presentation reuses choice skins and portrait masks, with 37-pixel minimum rows,
original timer art `708/709` and skin timer/score pieces. The ordinary choice
screen's layout is described in [UI_FIDELITY.md](UI_FIDELITY.md).

## 4. Service 94: football

### 4.1 Frame and tables

| Argument | Meaning |
| --- | --- |
| a1, a2 | First/second half duration in seconds. If a1 ≤ 0 start in half 2; if a2 ≤ 0 after a positive first half finish after half 1 |
| a3, a4 | First-half offense/defense play-table word addresses |
| a5, a6 | Second-half offense/defense tables |
| a7, a8 | Overtime offense/defense tables |
| a9 | Address of six raw text references, in the same interleaved order as the six supplied tables |
| a10 | Boolean: first possession is offense when true, defense when false. Second half reverses that initial possession |
| a11, a12 | Team selectors, low byte; localized team labels use selectors 1–9 |
| a13, a14 | Starting field positions for home/away possession |
| a15, a16 | Initial home/away scores |
| a17 | Enable special defensive block code -6 |
| a18, a19 | Enable bonus pass/run codes 6/7 |
| a20 | Boolean selecting coach art: frame `!bool(a20)` in atlas 290 |
| a21, a22 | Optional raw additional offense/defense instructions; -1 means absent |

```text
play_table := play_row* + 0x7ffe
play_row  := code:s16, base_yards:s16, variation:s16, weight:s16
```

Native storage reserves ten seven-word expanded records plus a terminator per
table; only four input words per row come from KiWi. The runtime bounds tables
to ten rows, checks codes and nonnegative weights, and requires an eligible
positive-weight ordinary outcome. Native internally groups offense tables
before defense tables; the Python model retains the frame's interleaved order.
Evidence: dispatcher 94, `000bc144`, `000c0050`, `000bdf7c`.

| Code | Outcome | Atlas 290 signed frame |
| --- | --- | --- |
| 1 / 2 | Run / pass | -47 / -53 |
| 3 / -3 | Block/ordinary defensive yardage | -41 |
| 4 / -4 | Turnover | -59 |
| 5 / -5 | Field goal attempt | -45 |
| 6 / 7 | Bonus pass / run | -54 / -48 |
| -1 / -2 | Opponent run / pass | -51 / -57 |
| -6 | Special block, zero yards | -42 |

### 4.2 Selection and timers

Nine targets use centers `(60,160,260) × (220,300,380)`, in row order, with
top-down 320×480 coordinates. Inclusive input bounds are `x ± 35`,
`y - 53 .. y + 17`, independent of the sprite's scale. Invisible waiting and
finished targets reject input. Initial help accepts a touch strictly after
3500 ms; subsequent help uses 900 ms. Acknowledgement has an 800 ms exit;
play starts after a 2400 ms countdown. Additional supplied help is shown when
applicable. Help, feedback, possession changes and result panels pause play time.

For each target, draw a weighted eligible code, derive yardage, then draw hold
time `800 + below(2)*500` and initial delay `below(1200)`. Code -4 is eligible
only on zero-based down 2 or 3; code 5 only on down 3; code -5 only on down 3
with `65 < position < 95`. Disabled 6/7/-6 map to 2/1/-3 **after** weighted
selection. Yardage looks up the first row for the mapped code, falling back to
the first table row. Variation is `sign(variation)*below(abs(variation))` and
is exclusive of the bound. ±4, ±5 and -6 have zero yardage without that draw.

```text
1 wait(delay) -> 2 grow(500) -> 3 hold(800 or 1300)
3 -> 4 shrink(500) -> 5 grow-worst(500) -> 6 worst
3 -> 6 directly if already the worst code AND yards; retain elapsed time
all targets in 6 and each elapsed >= 500 -> 7 shrink -> 8 finished at 600
all targets finished -> apply worst automatically
```

Overshoot is discarded on the timed transitions except the direct 3→6 branch.
The common worst is the first minimum-ranked generated target: turnover 4
ranks -200, turnover -4 ranks +200, special block -6 ranks 0, bonus 6/7 ranks
yards+5, and other plays rank by yards. Choosing a visible target commits its
current outcome immediately. Evidence: `000bce84`, `000bccdc`, `000b467c`,
`000b45d8`, `000bf300`, `000bf450`, `000b1f6c`, `000bfae8`, `000bc2ec`.

### 4.3 Drives and completion

Positive yards move position toward 0; negative yards toward 100, clamped to
that range. Bonus offense codes add five yards. Touchdowns occur at position 0
on offense or 100 on defense and award seven points. Four plays without a
touchdown cause a possession change; this mini game has no simulated
ten-yard first-down rule. Turnovers switch possession immediately after feedback.
Touchdowns and successful kicks restart at the receiving side's supplied
starting position. Scores wrap as signed 16-bit values.

For field goal distance `d` (position on offense, 100-position on defense), the
native threshold is `min(.99, 1 - log(d)/3.9120230674743652)` for `0<d<50`,
otherwise `.99`, stored as float32. With `r=below(10000)/10000`, the kick succeeds
when `r >= threshold`, awarding three points. Otherwise native failure variants
split at `r/threshold > .9`. This unusual formula is retained as recovered.

A separate internal performance score adds twice the yards, ±70 for a
touchdown, +10 for a defensive turnover or -50 for an offensive turnover. It
is saved but is **not** the service-94 return. A half ending mid-play resolves
that play and its feedback. A tied second half starts sudden-death overtime,
with no play clock, initially on offense. The first scoring result ends overtime.
After result presentation and exit the callback stores the match scores and
resumes KiWi. Evidence: `000b78c8`, `000b618c`, `000c0310`.

Feedback uses an 800 ms entrance, 300 ms shine and a hold of 0 ms for ordinary
yards/turnovers or 800 ms for touchdowns, kicks and half results. Additional
messages add 100/100/300/hold stages, followed by an 800 ms exit (`000b4db4`).
The messages, localized team/score labels, camera interpolation, play animations,
fonts, help panels and four-step countdown are implemented and specified in
[FOOTBALL_UI.md](FOOTBALL_UI.md). The final 960 ms exit timer is modeled;
its original overlay and the other remaining differences are listed below.

## 5. Service 96: word and picture grids

### 5.1 Frame

| Argument | Meaning |
| --- | --- |
| a1 | Overall play duration, seconds |
| a2 | Target score |
| a3, a4 | Per-board deadline and correct-answer time bonus, milliseconds |
| a5, a6 | Background variant and base resource ID |
| a7..a10 | Left character/expression, right character/expression |
| a11 | Shuffle problem order if exactly 1 |
| a12, a13 | Problem count and ten-word problem table address |
| a14 | Show between-round feedback if exactly 1 |
| a15, a16 | Success/failure substituted text references, read when feedback enabled |
| a17, a18 | Picture-symbol count and two-word symbol table address |
| a19, a20 | Tutorial count and seventeen-word tutorial table address |

```text
problem[10] = width, height, heading_ref, prompt_ref, valid_words_ref,
              alphabet_ref, highlight_starts, advance_after_one, minimum_starts, id
symbol[2]   = byte_character, asset_id
tutorial[17]= title_ref, body_ref, text_position, tap_to_advance, hide_board,
              width, height, heading_ref, prompt_ref, valid_words_ref,
              highlight_starts, fixed_board_ref, show_hints, animate_board,
              timed_tutorial, failure_next, success_next
```

Problem and tutorial text is substituted, except fixed-board bytes are raw.
Target-word lists use `000cccd0`, which trims bytes 0x00–0x20 at each field's
ends through `0005f838` and omits empty fields. This differs from the choice
list parser. An empty reference produces zero target words, not one empty
word. The native delimiter loop also stops when at most one byte remains after
`|`: `cat|x` yields only `cat`, while `cat|x ` keeps both words after trimming.
Duplicates and the order of retained words are preserved.

An ID of -1 uses 1001; the inspected native loop does not increment that default.
The problem loop ends after adding a record whose alphabet is exactly
`"inspirem"` (`00098344`/`0005edd8`: equality, not substring search).
Tutorial title/body references can be negative; absent body disables its text
position, tap and hide flags. Fixed boards have `width` bytes per row separated
by one byte, normally newline or `|`. Untimed, tap-to-advance instruction pages
may have zero target words and zero valid starting cells; they display the
fixed board and advance on a tap without awarding points. Playable puzzles
still require valid target words.

Tutorial branches are table indices, or -2 to finish tutorials. Shipped untimed
instruction pages also use -1 for their unused failure branch. The runtime
accepts that value only when the tutorial timer is disabled; it does not treat
-1 as a transition or an instruction to skip a page. The selected link is still
checked by `next_problem`, matching `000d01a4`'s direct branch selection.
Finishing tutorials clears their score before the real game.
The application suppresses already-seen tutorials; the current runtime stores
that flag per session and preserves it across the session's script changes.

Football Star scene 25011, service 96 at PC 4578, supplies three generated
problems and sixteen tutorial records. Records 3, 10 and 13 have empty target
lists; the instruction pages use unused failure links of -1. The parser and
validation support these records, including timeout → explanation → hinted
retry paths, without changing the VM arguments, scores or random stream.

### 5.2 Boards, paths, scoring

Dimensions are 1..5 with at most 25 cells. Native storage is column-major with
a five-row stride; the Python API/save uses row-major `row*width+column`.
Eight neighboring cells may be joined, including diagonals, without reusing a
cell. Search order is down, up, down-right, right, up-right, down-left, left,
up-left. Valid starting cells are enumerated column first, then row.

Generation makes up to fifteen attempts. Each attempt clears the board,
chooses target words and tries random neighbor walks, committing only complete
words; each next step draws independent signed offsets in [-1,1]. Out-of-bounds
steps retry without consuming the sixteen-collision allowance. Empty cells
are filled from the alphabet in row order. If too few valid starts exist,
fallback fills cyclically from the alphabet and repeatedly shuffles cells,
traversing columns first. Problem-order shuffling avoids immediately repeating
the previous problem at the start of a new cycle. The runtime bounds placement,
fallback and DFS work to reject pathological input rather than hang.

Mouse down starts a trace; moves extend to adjacent cells. A complete target
word submits immediately, without waiting for release. Previously consumed
starting cells cannot score again on that board. Each success scores
`100 * (number of starts already consumed + 1)`; subsequent words from distinct
starts therefore award 100, 200, 300, etc. Normally it consumes that start and
adds the supplied time bonus, capped by the per-board deadline. An ordinary
`advance_after_one` problem ends immediately instead; fixed tutorials consume
starts and use the time bonus. Invalid release clears the trace and requests
8109, throttled for 250 ms; success requests both 8110 and 8111. Letters remain
in place after a success. Picture grids use the same byte/path rules, replacing
glyphs via the supplied resource map.

### 5.3 Lifecycle

| Phase | Meaning / transition |
| --- | --- |
| -2 | Initial wait, 1000 ms |
| -1 | Ready, 1500 ms |
| 0 | Initial tutorial board entry, 2800 ms |
| 6 | Target-score announcement, 1600 ms |
| 2 | Board entry, 1800 ms; native permits input in this phase |
| 1 | Active board; overall clock runs only outside tutorials; round clock runs outside tutorials or for a timed tutorial |
| 3 | Optional round feedback, 1100 ms |
| 4 | Board change, 800 ms, then phase 2 (or 6 on tutorial completion) |
| 5 | Time-up/results sequence; main 4200 ms counter with 2600 and 4600 ms overlays |
| 7 | Final exit, 960 ms, then boolean callback |

Tutorial dialogue has a separate entry timer. A `tap_to_advance` tutorial accepts
acknowledgement instead of tracing. Between-board phases suspend both clocks.
Overall expiry clears active dragging. The renderer uses the native projected
cell geometry: 450-unit squares, 72-unit gaps, 30-degree tilt, camera depth
-3000/-3400/-3800 depending on dimensions. Initial pointer hits use a full cell;
continuation uses a 65% inset. Fast motion does not interpolate skipped cells
in the current frontend. Exact native interpolation behavior remains to compare.

Evidence: dispatcher 96; record builders `000cd014/000cce44/000ccf0c`;
generation `000cb570/000c536c/000c512c/000c4318`; input `000d08fc/000cf228/000cf35c`;
scoring `000c3874`; transitions `000d01a4/000cfb30`; tick `000d1124`;
camera `000cc398/000c7ef8/000c7f98/0004e114`.

## 6. Sprite-atlas and glyph-font payload schemas

These are **separate** from the ARGB image packs in [UI_ASSETS.md](UI_ASSETS.md).
Read numeric resources directly from the user's APK/episode bank; do not use
PNG-conversion filenames as resource identifiers. Multi-byte fields below are
**big-endian**. `s8/s16` are signed, and counts must be nonnegative.

```text
SpriteAtlas {
  flags:u8
  frame_capacity:s16
  sequence_count:s8
  if sequence_count > 0 {
    sequence_base:s16
    total_sequence_entries:s16
    sequences[sequence_count] {
      count:s8
      delta[count]: (flags & 4 ? s16 : s8)
      # actual frame reference = sequence_base + delta
    }
  }
  composite_count:s16
  total_parts:s16
  composites[composite_count] {
    count:s8
    parts[count] {
      reference:(flags & 1 ? s16 : s8)
      x:(flags & 2 ? s16 : s8)
      y:(flags & 2 ? s16 : s8)
    }
  }
  transform_count:s16
  transforms[transform_count] { frame:s16, transform:s8 }
  coordinate_scale:s16
  atlas_side:s16
  frame_count:s16
  frames[frame_count] {
    atlas_x:s16, atlas_y:s16,
    logical_width:s16, logical_height:s16,
    stored_width:s16, stored_height:s16
  }
  pixels:byte[atlas_side * atlas_side * 4]  # A,B,G,R per pixel
}
```

Multiply atlas x/y by coordinate_scale. Nonnegative references name literal
frames; negative references name composite `~reference`. Parts retain signed
offsets and painter order and may reference other composites. The decoder
checks totals/extents and bounded acyclic composite expansion. Pixel upload
reverses ABGR to RGBA. Current rasterization requires logical and stored sizes
to match; scaled-storage variants reject explicitly. Transform codes 0..7 use
the same flip/rotation convention documented for image packs. Other native
flags and playback of atlas sequences are not fully implemented.

```text
AtlasFont {
  space_width:s8
  style:u8
  tracking:s8
  glyph_count:s16
  glyph_height:s8
  glyphs[glyph_count] { byte:u8, atlas_x:s16, atlas_y:s16, width:s8 }
}
```

Glyph images come from a paired SpriteAtlas. Missing ASCII/Latin-1 letter case
falls back to the opposite case. The grid's blue letter image/metrics are
resources `522/523`; tile/arrow sprites are atlas `446`. Football uses atlas
`290`, including nested field markings, play symbols, coach art and number
glyphs. Evidence: atlas `000507b8/000503dc`, font `000538ac`.

The service-96 renderer now uses its own paired fonts `510/511`, `512/513`,
`516/517` and `522/523`, rather than generic dialogue labels. Tutorial panels
use atlas 446 frames 45–47, measured paragraphs and the record's top/center/bottom
position. Portraits, cloud borders, headings, the time/score HUD, bottom word
list and banners follow the recovered native layout. See [GRID_UI.md](GRID_UI.md)
for coordinates, font metrics, animation contracts and the validation boundary.

## 7. Saves, verification and remaining fidelity work

Save version **3** embeds the complete typed game dataclasses under
`engine.word_game`, `engine.football`, or `engine.word_grid`, exactly one matching
the pending service. It also records both random states, football scores,
tutorial history and queued/active dialogue notices. Generated options, boards,
consumed starts, selection path, targets, animation phases and clocks are saved;
loading never redraws them randomly. Version 1/2 saves acquire new defaults;
an old stopped 71/94/96 frame is initialized using its retained original args.
Historical random draws absent from an old save cannot be reconstructed.

Version **7** additionally preserves grid decorative time, active banner state
and outgoing board faces. Version 1–6 grid saves migrate with zero decorative
time and no reconstructed banner/outgoing faces, retaining the generated board,
selection, score, random generator and VM state. Full field schemas and native
evidence are in [GRID_UI.md](GRID_UI.md#saved-presentation-and-verification).

Version **8** adds football's camera/HUD positions, decorative time, distinct
localized message IDs/values and outgoing play effects. Older football saves
retain their recorded feedback and game state; absent camera history starts at
the saved field position. See [FOOTBALL_UI.md](FOOTBALL_UI.md#saved-presentation-and-verification).

Version **18** preserves grid tile pop/glint clocks and fragment bursts. Eight
fragments per selected tile consume twelve native engine RNG draws each, up to
twenty active bursts. Rendering does not draw randomness. Older saves retain
their existing gameplay/RNG state and start the missing effects inactive.

Version **22** preserves grid score flights/pending and displayed counters,
and football touchdown stars. Home touchdowns now consume 450 engine RNG
draws to create 50 stars. Rendering consumes none. Old saves start these
missing effects inactive without reconstructing historical random draws.

Service 88 queues a substituted notification for the next dialogue, with the
original Pajama Hip S font, rising letters and length-dependent fade
(`0009c814/0009c750`). This shared path handles post-game notifications and stat
changes without changing their scripted results. The lifetime is
`165*(source_length+1)+300` ms; dialogue input dismisses it even on a reveal/page
tap. See the [notification specification](STORY_SERVICES.md#dialogue-notifications-service-88).

Tests cover libc and native random vectors, choices and score clamps, held VM
frames, callback/result-cell differences, diagonal paths and cell reuse, generated
solvable grids, tutorial transitions, football target decay and no-input outcomes,
weighted-code remapping, downs, turnovers, touchdowns, sudden death, save/replay,
malformed saves, actual user-supplied script frames, original atlas decoding,
resized mouse coordinates and pause/focus gating. These are implementation and
native-derived rule checks; no running-original frame trace has been compared.

Remaining differences include football internal score-flight reachability,
the full audio timeline (see [FOOTBALL_UI.md](FOOTBALL_UI.md)), native GL
depth precision/edge sampling and uncommon overlay-reuse boundaries. Native
minigame exit fades, football shadows/final-score sound, float32 grid fragments,
per-pixel depth, selection opacity, highlight shuffles, per-cell clocks and
the deferred outgoing-board generation path are now modeled;
see [GRID_UI.md](GRID_UI.md) for isolated native checks and save migration.
Integer clocks may differ from fractional native frame deltas at floating-point
boundaries. Fonts outside the recovered glyph path use existing APK bitmap fonts,
but not every native font-object parameter. Random generators and speaker fonts
now persist across episodes in the same application process; other native
widget lifetimes remain partial. Full visual fidelity remains a requirement.

Unimplemented surrounding engine services remain explicit stops. Service 91's
loading timer and service 99's native stub have since been recovered; Football
Star now enters its first match through the loading screen and returns to
dialogue after both halves. See [STORY_SERVICES.md](STORY_SERVICES.md).
Assets, local previews, original episodes,
native decompilations and saved games are excluded from distributable packages.
