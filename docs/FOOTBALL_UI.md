# Football presentation contract

Reference: Android 1.0.9 `libshs09.so`, Ghidra image base `0x10000`.
This supplements service 94's arguments, play tables, scoring and callback in
[MINIGAMES.md](MINIGAMES.md#4-service-94-football). The implementation is shared
by all episodes and all six half/possession plans. Everything is drawn in the
original 320 × 480 coordinate space before viewport scaling. All images,
font descriptors and localized strings come from the player's APK or IPA.
The score strip additionally uses the supplied SHS iOS executable as a native
reference; its atlas parts and bitmap font match the APK.

## Resources and text

| Resource | Purpose |
| --- | --- |
| 290 | ABGR sprite atlas: field, help panel, coaches, play symbols, digits, countdown, feedback strip and rings |
| 524 / 525 | Sprite-atlas glyph sheet / CS metrics for the score strip; 15 pixels high in APK and IPA |
| 540 / 541 | PNG glyph sheet / CS font metrics for result messages; height 52, gap 0 in the reference APK |
| 701–704 | Image-pack down labels, selected by down 0–3; down 4 retains the fourth label |
| 720–723 | Image-pack animated target shadow frames, 110 ms per frame |
| 13 | Localized interface strings |
| `fonts/ArialMT14.fnt` | Native registry font 11 for the football BM labels |
| 126, frames 47 / 49 | Shared footer and gear |

The feedback PNG is **not** a sprite-atlas payload. Its metrics have the
[CS glyph schema](MINIGAMES.md#6-sprite-atlas-and-glyph-font-payload-schemas).
The help title and paragraph use nominal height 14 and gap 4; other football
BM labels use height 14 and gap 8. Text remains white unless a help paragraph
uses backticks for RGB `(24,92,219)` or semicolons for `(255,51,0)`.
Native font setup: `000b6f9c`; registry: `000e09d4`. Paragraph glyph spacing,
wrapping and native ink overhang come from `fonts.py`, not a system font.

BM labels draw downward from local zero. A center-aligned label's downward
origin is its screen-space node center plus half its measured text height;
this differs from centering a raster image. Each centered line has its own
horizontal offset. Help labels follow the panel's position but do not inherit
its scale or opacity: native code switches them off when panel opacity is zero.

Team selectors 1–9 map to string IDs 167–175. Other low-byte selectors produce
an empty name. Header IDs are 176/177 for first/second-half offense, 178/179
for first/second-half defense, and 71/72 for overtime. These are independent
of the script-supplied instruction paragraphs. Evidence: `000b6d4c`, `000b1b4c`.

## Field, header and help

`000b8410` tiles atlas frame 86 with 45 pixels per yard. The field scrolls
using `camera_position`, independently of the already committed game position.
Chalk uses the signed composites for the numbered ten-yard lines, composite
-80 at intervening five-yard lines, and authored end-zone composites. Their
child offsets must be retained. Frame 75 is a four-times-scaled haze overlay,
with opacity approximately 0.147, moving at -0.02/+0.05 pixels per millisecond.

For an active tick `dt = min(elapsed_ms, 250)`:

```text
camera += (position - camera) * 0.5 * min(dt / 100, 1)
if abs(position - camera) < 0.02: camera = position

delta = position - hud_position
step = delta * 0.5 * (dt / 300)
hud_position += step
if delta * (position - hud_position) < 0 or abs(step) < 0.5:
    hud_position = position
```

Both start at the configured starting position. Phase 4 and touchdown phases
9/10 wait for the camera to reach the logical position **and** for feedback to
finish. Field-goal phase 13 only waits for feedback. Evidence: `000b1c10`,
`000c0310`. Rendering never advances either interpolation.

The header uses frame 30 at `(10,13)` and offensive/defensive frame 152/153
at `(19,4)`. The down-label center is `(99,33)`. Native numeric routines
`000b68b4` and `000b9e90` place distance and clock near `(186,37)` and
`(165,37)`, including their distinct measurement, baseline and digit-spacing
rules. The clock rounds remaining positive milliseconds upward to seconds.
SHS iOS `drawHUD` **00088a60** selects score-strip composites -40/-39/-38
from the measured team-name widths plus 82: below 92, below 114, or larger.
It draws at `(253,50)`. The name/score font is `loadImageFont(523,522)` at
**00088094**, semantic roles 525/524. Let `c = 253 + min(child.x) + offset`,
where the three strip offsets are 51/62/73. All lettering starts at **Y 42**:
home name ends at `c-28`, home score is centered in `[c-24,c-7)`, the dash in
`[c-3,c+3)`, away score in `[c+7,c+24)`, and away name starts at `c+28`.
`CSMasterImage::getCenterX` **00015320** supplies the negative minimum child
offset. The same font and composite geometry are present in both supplied
asset profiles. This replaces the previously stretched strip, BM labels and
separate low dash; no scene-specific positioning is used.

`000be110` constructs help with frame 64, size 306 × 197, settled at `(7,126)`.
The title plaque is at `(13,117)`, with title string 76 or 77. The paragraph
origin is `(32,152)` in a 256-pixel column; its native node is four nominal
lines high. The renderer preserves the supplied paragraph and color markers.
The legend reads the current play table in its supplied order, including
zero-weight rows, excluding codes -6, -5, 5, 6 and 7. It spaces the remaining
icons across 217 pixels, starting from local X 45. Its labels are strings
166 (worst) and 165 (best) at panel-relative Y 183. The runtime safely handles
an authored one-icon legend without the native division by zero.

The selected coach is atlas frame 0 or 1, right-aligned at X 320, bottom 457.
The panel enters over 800 ms from `(320,440)`, with the native 1.1 overshoot
curve. The coach slides in over 700 ms and settles by five pixels over the
last 100 ms. On exit the coach slides right while the panel fades and hides
at 60% progress. When another extra-help page follows, the coach stays put.
The first reading gate remains strictly greater than 3500 ms; later gates
remain strictly greater than 900 ms. The footer displays localized string 75
only after the gate, otherwise strings 73/74 during gameplay. Its BM node is
centered at screen `(180,455)`, giving line origin Y 462.

## Countdown and play targets

`000b4050` divides the 2400 ms countdown into **four 600 ms slots**: frames
4, 3, 2, then 5 (Go). The numeric sprites expand/fade into place. Go has a
separate entrance, spinning exit, scale divisor 1.3 and opacity divisor 1.8.
All rotate and scale around the native center near `(159.5,240)`.

Touch regions remain inclusive X ±35, Y -53..+17 around the nine configured
centers `(60,160,260) × (220,300,380)`, regardless of visible sprite scale.
Only target phases 2–7 accept a play; appearance never changes the outcome.

`000c12a8` places the play sprite's native top-left at:

```text
x = target_x - 35
y = int(target_y - int(scale * 18)) + bob - 35
bob = sin(elapsed_ms / hold_ms * 3.1415926) * 3.5  # phases 3 and 6 only
```

Grow/shrink scale also controls opacity. The one-literal play composites have
negative serialized origins, but helper `0009936c` repositions the returned
sprite at `(x+width/2, y+height/2)`. Applying the serialized offset again is
incorrect. Field chalk uses a different direct composite path.

Target yardage uses `000b3a60`'s slanted digit baselines, width table, signed
color selection and matching `yds` suffix. Bonus icons display their base
yardage: the extra five yards are represented by their art and subsequent
message. Turnovers have their own overlay; field-goal targets omit yardage.
The runtime extends the two-digit native display safely for authored larger
values, without changing those play values.

Entry uses yellow frame-127 rings; the common-worst exit uses red frame-126
rings. The four-frame shadow uses the position and opacity recovered from
`000c0ac0`; its native GL Y is `target_y - 120`, with scales 1.3/1.2 and
opacity `(sin(visual_ms/1000*4)*0.3+0.7)/1.5`.

A touch snapshots visible targets before committing the play. The selected
sprite changes to its authored effect variant, expands and flattens for
500 ms, then rotates and fades over 1000 ms. Other visible sprites shrink and
fade over 1300 ms. Their clocks and initial scales are saved. Evidence:
`000bc2ec`, `000b2584`, `000b2494`, `000b4bd0`. These effects consume no random
numbers and cannot commit a second play.

## Result sequence

`000b78c8`, `000b618c` and `000b66d8` configure one to three distinct messages.
They are displayed sequentially, not flattened into one English string.

| Event | Native string sequence |
| --- | --- |
| Ordinary gain | 58(value), then next-down 50/51/52 or possession-change 55 |
| Loss / defensive zero gain | 54(abs(value)), then next down / possession change |
| Special defensive block | 61(0), then next down / possession change |
| Bonus pass / run | 63(base yards) / 62(base yards), then next down / possession change |
| Turnover | 60, then 55 |
| Offensive / opponent touchdown | 48 / 53, then both scores when time remains and outside sudden death |
| Made / missed field goal | 46 / 47, then both scores under the same condition |
| First-half end | 42, then both scores |
| Second-half end | 57, both scores, then 43 (overtime), 44 (win), or 45 (loss) |
| Overtime end | Both scores, then 44 or 45 |

Internal IDs -100/-101 mean home/away score; -102 joins both team/score lines
with a newline. Value 1000 is the native no-substitution sentinel; other values
replace `%d` in the localized message. The native fourth-down branch at the
first-half time boundary returns before configuring another yardage banner.

The shared stage machine (`000b4db4`) is:

```text
0: entry 800 -> 1: shine 300 -> 2: hold H
if another message: 3: hide 100 -> 4: show 100 -> 6: shine 300 -> 5: hold H
if a third message: 7: hide 100 -> 8: show 100 -> 10: shine 300 -> 9: hold H
11: exit 800 -> -1: finished
```

`H=0` for ordinary yards/turnovers and `H=800` for touchdowns, kicks and half
results. Timed boundaries discard overshoot. The zero hold is still a stage,
not an instruction to skip subsequent stages in the same tick. The half-result
win/loss sound is requested as its second message enters the shine stage.
The 1000 ms turnover delay runs concurrently with feedback; a fourth-down
possession delay is 2000 ms after yardage feedback.

`000bba50` slides frame 66 into settled position `(-24,240)` and sweeps frame
65 across it during shine stages. The entry text scales 0→1 and rotates 180→0;
the exit reverses that motion. Inter-message visibility factors are **gates**,
not additional opacity or font-size changes. Feedback uses CS font 540/541,
a 300-pixel wrapping column, per-line centering and the native baseline
adjustment for a single line. No generic final-result panel is added.

## Saved presentation and verification

Home touchdowns now create the star celebration recovered from Android
**000b618c** / **000b4858** and iOS `TouchdownEffect::init` **0008d150**.
There are **50** stars; each consumes nine engine random draws, **450** total.
Opponent touchdowns do not create stars. Initial values are:

```text
delay = random(1000) + 300 ms
x = 145 + random(30); y = 235
vx = signed_random(120) / 1000; vy = (-50-random(190)) / 1000
angle = random(360); spin = signed_random(720) / 1000
alpha = 1; fade = (-100-random(1500)) / 1000000
```

Each signed draw consumes a magnitude and sign draw. iOS `TouchdownStar::tick`
**0008f460** decrements the delay, then uses the whole first active tick for
Euler movement, rotation and opacity. Gravity adds `dt*.0001` to vertical
velocity, with a double intermediate and float32 store. Stars die at opacity
zero or Y 480. `draw` **0008f51c** uses frame **90**, pivot `(15,15)`. Stars
are above field/play effects and below the HUD and feedback.

Save version **22** adds up to 50 `touchdown_stars` records, each containing
`x`, `y`, `vx`, `vy`, `angle`, `spin`, `delay_ms`, `alpha` and `fade`.
Positions/velocities/opacity must be finite and clocks/ranges are validated.
Older saves start with no stars and retain their recorded RNG state; historical
missing draws are not invented. Future play selection after a touchdown can
differ from older runtime versions because the missing draws now occur.

Save version **8** extends each active football game with:

| Field | Type / contract |
| --- | --- |
| `visual_ms` | Nonnegative integer; active decorative time |
| `camera_position`, `hud_position` | Finite floats in 0..100; field and HUD interpolation |
| `message_ids`, `message_values` | Parallel integer arrays; 1–3 native messages, or empty for a migrated old banner |
| `message_hold_ms` | 0 or 800 |
| `effects` | At most nine `{frame:int, x:int, y:int, scale:float, selected:bool, remaining_ms:int}` records |

`message_lines`, `message_phase`, `message_ms`, phase timers, logical field
position, scores and pending VM arguments remain part of the existing game
state. Effect frames, positions, scales and lifetimes are validated on load.
Versions 1–7 remain readable. An older active football save starts both display
positions at its recorded logical position, with no outgoing effects. Its
recorded text and remaining timers are retained until the next native message
sequence; unavailable historical messages are not guessed or replayed.
Menu/focus pause freezes all these clocks. Repeated rendering is read-only.

Authored tests cover all half/possession header mappings, plan-driven legends,
help gates, all four countdown slots, message selection/stages, camera easing,
selected-play save/replay, migration and invalid-state rejection. A generated
sprite verifies that composite offsets are not applied twice. The optional
player-library test renders original fonts/art, checks animated frames and
pixel-identical save/resume, then verifies pause/focus and resized mouse input.
Original Football Star was also advanced through its script into service 94
for local visual inspection. A local match completed both halves through normal
target input and resumed dialogue with scores 14–7; 128 distinct presentation
states rendered, including both possession modes and both touchdown branches.
None of that content is a distributed fixture.

An isolated ARM comparison checks Android's actual star initializer with four
deterministic random streams and the iOS star tick through expiration; all
fields match. Random helper returns are supplied by that harness, and no native
graphics or operating-system code runs. This complements save/RNG tests.

These are native-code and implementation checks, not a pixel/frame comparison
with a running original. Internal performance-score flight reachability still
needs verification: iOS `addToScore` **0008ded4** is a no-op despite the presence
of `drawScoreEffect` **00089770** and `tickScore` **0008dba0**. The phase-6 final
message now plays 8101 for a win or 8105 otherwise, without replaying the cue
on an intermediate message. Android target shadows retain their four 110 ms
frames across deals, with their own unclamped animation clocks. Save version
22 retains those clocks; the existing iOS shadow rotation remains unchanged.
The iOS final overlay eases to black over 800 ms, then releases the callback
at 960 ms. Gameplay and particles freeze during that exit phase.

Cross-panel native widget lifetimes, the complete audio timeline, float32
boundary rounding outside the verified star/fragment routines, unusual native
node placements and exact GPU sampling still need recording-level verification.
The renderer must not invent random particle calls or script-visible results to
hide those gaps. Other unsupported host services remain explicit stops.
