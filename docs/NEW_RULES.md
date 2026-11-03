# Surviving High School: New Rules

*Surviving High School: New Rules* (2009–2010) is Centerscore's game for Windows Mobile, also sold on J2ME as plain *Surviving High
School*. Internally it's `shs09`. This fork translates its stories into `.exp` episodes that play on the SHS presentation, and runs its
minigames in a rebuilt copy of its own arena.

Nothing here runs original game code except New Rules' own KiWi scripts. No New Rules file ships with the runtime: `tools/translate`
reads the player's files and writes `.exp` files.

**In the library:** 50 stories, pack 31300, tagged NR and filed under their own "New Rules" category. Save version and service details
are in [RUNTIME.md](RUNTIME.md) and [ENGINE_ABI.md](ENGINE_ABI.md#51-new-rules-minigame-arena-shshd-runtime-services-200212).

## The game

| Scripts | Story | Notes |
| --- | --- | --- |
| 25001–25007 | **King of Diss** | Josh defends his diss-battle title. Unique to this game: at most 3% of its lines are in the smartphone corpus |
| 25101–25106 | **Dancing Queen** | The smartphone's *Homecoming Queen*, 98% line match |
| 25200 (text 25250) | **Minigame library** | Arena tutorial, Sequences, Fever, Rhythm, Rhyme. A linked KiWi segment loaded beside the story |
| `2.expd`–`48.expd` | 47 downloads | Mostly smartphone seasons 1 and 2, recompiled for New Rules' ABI; *Train That Brain!* and *SHS 11 Demos* are unique |

**King of Diss Lite** (episode 100) is the condensed one-script retelling in the Lite Java builds.

The Windows Mobile and Java releases share the engine design, the KiWi host ABI (services 1–67) and the resource IDs. Java keeps text in
string tables (25051–25057, 25151–25156, 25250) rather than inline.

### Formats

- **`res_large.pud`** is the WinMo base pack, a CSPUD archive like an `.exp`. In the CAB it's `RES_LA~1.005`.
- **`.expd`** is a stored download: `u16` id, `writeUTF` title, then the CSPUD archive. Downloads hold scripts only, with no art, audio or
  metadata.
- **Java resources** are loose jar members by decimal ID, plus `CMB0` bundles: `"CMB0"`, `u8 n`, `u16 ids[n]`, `u32 offsets[n+1]`. This
  isn't BREW's `CMB0`, which has no ID table.
- **Characters are paper dolls.** There are no pre-drawn portraits: 90 character slots, each with a name and a 33-slot appearance record of
  part IDs, recoloured through palette sets. Up to 6 stand on stage.
- **Fonts** are capitals only in the main faces, which is why New Rules' script text is all lowercase. `` ` `` switches to the emphasis
  font, `~` to the alternate font, and `;` back.

## Building

```sh
python tools/translate/translate.py newrules addon --pud RES_LARGE_PUD --x1i X1I_JAR --out OUT_DIR
python tools/translate/translate.py newrules EPISODE.expd --pud RES_LARGE_PUD --x1i X1I_JAR --library LIBRARY \
    --addon OUT_DIR/NR_Addon_New_Rules.exp --arena --out OUT_DIR
```

`EPISODE` can also be `king-of-diss`, `dancing-queen` or `king-of-diss-lite` (with `--lite JAR`). `--downloads DIR` names the `.expd`
folder to learn capitals from. `--library` is an SHS library, for the same purpose. See [ADDONS.md](ADDONS.md#shsnr-new-rules) for what the
addon holds.

`tools/translate/nr_arena_test.py ARENA_DIR` writes a menu episode, *Minigame Arena Test*, that plays every library game and a round of each
game the downloads carry, then shows what each returned. It's for development and isn't one of the 50.

## How a script is translated

New Rules' scripts are compiler output, so they're translated as bytecode, not lifted into creator graphs. Control flow, arithmetic and data
stay exactly as they were.

- **A host call becomes one jump.** Each is replaced with `0x29` to a trampoline appended after the original code, so every instruction
  keeps its index and no branch needs relocating. The trampoline pushes the call site as the return address and jumps to the service's
  shared shim. A shim reorders the arguments and calls the SHS service, calls several, or does the work in KiWi, then puts the result where
  the caller expects it. One-to-one services are rewritten in place.
- **Waits are ordinary.** A shim that yields for dialogue or a choice is a script waiting at an appended PC, so saves, the Decision Tree and
  the native harness handle it unchanged.
- **The compact dialogue stream** (service 48) is static data, so each stream becomes straight-line KiWi in an appended block.
- **The service map** in brief: 40–43 → 13/76, 11–14 → 1–4, 15–18 → 54/55/46/47, 20–23 → 50–53, 32 → 70, 34 → 10, 35 → 11, 49 → 17.
- **Text** gets its capitals back from a dictionary learned from the 45 stories paired with smartphone twins (`casing.py`).
- **Art is rendered up front,** so the runtime needs no new formats:
  - **Portraits:** five expressions per look, from the paper dolls, with a second set from the X1i jar's redrawn art at +1000
    (`TRANSLATED_PORTRAIT_ART`, the Hi-Res Portraits switch).
  - **Backgrounds:** each location's strip at each time of day.
  - **Frame backdrop:** resource 26999, drawn under the strip where SHS leaves black (`TRANSLATED_FRAME_BACKDROP`).
  - **Music:** MIDI rendered to MP3 through Java's built-in synthesizer (`midi_render.py`), as the J2ME emulator plays it.

### Checks

- **Against the smartphone twins:** 96–100% of lines matched for 39 of the 46 paired stories. The lower ones were read through: dice rolls,
  New Rules' own wording, and the branch an untouched word game takes.
- **Headless playthroughs** (`playthrough.py`) reach the exit on 49 of 50. *Train That Brain!* overflows its stack only because the bot always
  answers Yes to more training.
- **Arena routes:** all 107 arena games were played at every result 0–40 to the episode's end (see [Skipping](#skipping)).

## Minigames: two forms

A translated story carries both forms and picks at each game. With **Use Translated Mini-Games** on (Options › Add-Ons, on by default), the
player answers service 70 selector 200 with 1 and the arena plays. With it off, or on any other player, the query answers 0 and the story takes
its fallback.

| Game | With the arena | Without |
| --- | --- | --- |
| Downloads' rounds | The arena copy the download carries | Its timed round, as an SHS word game (71) |
| Rhythm, beat boxing, dance steps, DJ Fever | The library's game | An SHS word game, 30 s |
| Rhyme | The library's game | A speed diss: timed choices, 10 hits to finish, 3 misses to lose |
| The face picker | SHS's portrait picker (78) | The same |

Three downloads' rounds with no guard (in *Flex Games*, *The Break Up* and *Fair Catch*) and *SHS 11 Demos* have no arena copy, so they stay
word games. *Train That Brain!* drives the arena itself.

### Word-game goals

SHS's own pace is 6 hits in 20 s, as nearly every episode in the library has it. Every download's round follows it (`WORD_GAME_PASS`).

The library's games are 30 s, as a KiWi word can't hold the arena's 40,000 ms. The stories compare their results with a target meant for the
arena's **0–10 grade**, so `newrules.library_game` compares the hits with the goal below, and leaves the story's target in B, or one short of
it. The stories' own comparisons don't change, and a skip's win and loss still work.

| Game | Hits in 30 s |
| --- | --- |
| Rhythm at target 1–3, 4, 5, 6 | 8, 10, 13, 16 |
| Rhythm at target 7 and up | 19 (the owner's cap) |
| The first Rhythm a story plays, target 6 | 10, standing in for the arena's +2 first-play handicap |
| Beat boxing, dance steps, DJ Fever | 9, SHS's own pace |

Rhythm's numbers are the straight run that scores each grade in 40 s, at n(n + 1) / 2 points, three quarters of that for 30 s. The grade
thresholds for 40 s are 15, 25, 50, 90, 150, 225, 325, 425, 550, 825. Sequences and Fever score differently and haven't been converted.

## The arena

New Rules' minigames are one scriptable panel plus rules in KiWi. The panel is **passive**: it keeps state, animates and draws. **Every rule is in
the library's bytecode**, which loops: wait a frame (29), read the elapsed time (721), the next key (707) and the item under the selector (726),
apply its rules, and write back the score, meter, items, ring speed, popups and labels.

So the runtime has a panel model (`nr_arena.py`, saved mid-game), a renderer (`desktop_nr_arena.py`), and the services. The library runs unchanged.

These were decoded from the Java panel (the U5i Vivaz 7.25.83 and X1i 7.19.20 builds). The WinMo dispatcher has the same services, but its property
code wasn't compared.

### Properties

Get with service 203 (or 204 for a slot's item); set with 202, 206 or 207. A slot argument of −10 means the selected slot.

**Ring and items.** Up to 20 slots; the library uses 4–8.

| ID | Get | Set |
| --- | --- | --- |
| 719 | ms per turn | ms per turn. Default 4,000; ≤ 0 stops the ring |
| 722 | Ring size % | Ring size %. Default 100, minimum 3 |
| 723 | Item kind | **1** portrait, **2** picture, **3** text in a box (default) |
| 724 | Selected slot's item | Puts an item in a slot |
| 725 | Selected slot | Selects a slot |
| 726 | The slot under the selector in the hit window, else −1 | Turns the ring so that slot sits under the selector |
| 727 | Phase in the current slot, degrees | The hit window, degrees. Default 360 |
| 729 | Slot count | `(slot, 1)` inserts, `(slot, 0)` removes, `(_, n > 1)` sets the count, all empty |
| 740 | Motion mode | **0** stepped, **1** turning, **−1** turning the other way (every game), **2** still |
| 705 | | Depth plate under each item |
| 747 | | A move or popup: (slot, target, ms, text). A target ≥ 0 glides to that slot; a negative one flies a popup to an anchor |
| 748 | | A picture popup at a slot: (slot, picture, ms) |
| 749 | | A picture in a row: (area, picture, index, count). Sequences' target strip |
| 750 | | Removes popups of a kind (−1: all) |
| 751 | | Tints a slot: (slot, r, g, b); any −1 clears it |
| 761 | | A slot's blink flag, 500 ms |

**Timer, score and meter.**

| ID | Get | Set |
| --- | --- | --- |
| 710 | Seconds left, rounded up | Seconds; > 0 starts the timer, else it's hidden |
| 712 | | Pauses the timer |
| 713 | | Score display: 0 hidden, 1 shown, 2 blinking |
| 714 | Score | Score |
| 715 | | The meter, 1–10. Reaching 10 restarts the "max" animation |
| 716, 717 | | First and second target markers, 1–10 |
| 721 | ms since the last read, then 0 | |

**Buttons, keys and HUD.**

| ID | Get | Set |
| --- | --- | --- |
| 707 | The next key, −1 if none | |
| 772 | The next press as a number key: 1–6 → 8–13 | |
| 706 | | Which of the 4 on-screen buttons show (bits 1–4) |
| 708 | | OK and back feedback: 1 green, 2 red, 0 normal |
| 720 | | OK style: ≤ 0 alternate colour; < 0 also hides the right soft key |
| 730 | | Stops the 250 ms press highlight |
| 690–692 | | Labels in the three HUD text areas (201) |
| 693–695 | | Those areas' flash labels, 3 s |
| 696–700 | | HUD box (0–2) contents: item, kind and, inferred, a portrait's expression and frame |
| 701 | | A HUD box blinks |
| 762, 763 | | Two bubbles: (text, slot, flags). Flags: 1 at the slot, 2 above it, 4 with a pointer. 762 also holds input |
| 765, 766 | | The keypad labels round the ring (Sequences); flash one |
| 770 | | Field layout: 0 the ring, 1 the wide row |
| 718 | | **Closes the panel**; the score returns to the script |
| 790 | | This fork's `SHAKE`: the panel sizes the ring ±15% each frame, and 722 still reads back unshaken |

764, 767 and 768 aren't fully understood: the first two appear to preload pictures, and 768 isn't drawn.

### The panel's clock

Each frame, with dt in ms:

- **Ring turn:** `(acc + dt) × 360 ÷ period` whole degrees. While that's 0, dt adds to `acc`. The angle wraps at 360. Mode 0 stops exactly at its
  target angle.
- **Slot under the selector:** `k = ((360 − angle + 180/count) × count ÷ 360) mod count`. 726 returns `k` only while
  `(angle + window/2) mod (360/count) ≤ window`.
- **Timer:** counts down unless paused, stopping at 0. It closes nothing: the library reads 710 and ends its game.
- **Moves and popups:** elapsed += dt. A popup ends at its duration; a move just stops.
- **Flash labels:** 3,000 ms. **Button highlights:** 250 ms. **Meter ≥ 9:** the "max" animation, a 2 s loop.

The library never assumes a frame length.

### Geometry

Slot i's angle is `angle + 90 + i × 360/count`, on an ellipse filling the field rectangle scaled by 722: `x = rect.x + (w − w·s)/2 + cos(a)·w·s/2`, and
likewise y. So 90° is the bottom, where the selector sits. The ring draws in two halves, back then front, with HUD box 1 between and box 2 after.

**Layout anchors** for popups and 747: −4 the timer, −5 the meter, −6 and −7 the buttons, −15 the meter frame, −1 to −3 the HUD boxes, −11 to −13 screen
edges.

### Renderer

`desktop_nr_arena.py` ports X1i `class_13.method_356` case 25 onto the addon's skin (`nr_arena_art.py`, 26174–26177). It draws at the X1i's 480 × 650 game
area, widened to 489 × 652 for exactly 3:4, then scales up by the smallest whole number that reaches the frame's height, with nearest-neighbour pixels.

- **The frame:** the arena stands on the dialogue screens' frame (26178: the backdrop without the scene's bars), so the stripe doesn't change between story
  and game. X1i's scrolling tile isn't drawn.
- **The entrance:** 2 s, from X1i's transition tracks. The bands arrive over 0–800 ms and the table narrows into place over 400–1600 ms. Meanwhile the panel's
  clock doesn't run and it takes no keys. Leaving runs the same tracks backwards.
- **Base and edges:** the table's legs are extended to the frame's bottom (`_extend_base`), and the static screen keeps 8 columns either side, since the 3:4
  frame is wider than New Rules' screen.
- **Back to the story:** the arena's last picture fades out over the next screen in 400 ms (`ARENA_HANDOVER_MS`). New Rules shows it at once.
- **The menu** ("view tutorial?") is SHS's own choice over the arena (`arena_menu_prompt`), and the info box uses the bubble's box. New Rules' own dialog layouts
  haven't been decoded.
- **Not drawn:** portrait items (no wired game uses them), and pictures other than the 29 item icons.

### Sound

The panel has none. The library's three hooks are empty in WinMo, so the addon's build fills them with what the downloads' copies play:

| Hook | Called with | Becomes |
| --- | --- | --- |
| 28189 | Preloads | Stays empty |
| 28193 | 5 time's up, 13 right, 1 wrong, 11 Fever's bonus | SHS 79 with 26980 + index |
| 28197 | | SHS 80 with track 14 |

The library's code ends at the KiWi limit (32767), so these shims overwrite two functions nothing reaches, at 29997–30041 and
27221–27242 (`LIBRARY_ROOM`).

**This fork's additions** (`ARENA_ADDITIONS`), where New Rules plays nothing, in both the library and every download's copy:

| Game | Moment | Adds |
| --- | --- | --- |
| Rhythm, DJ Fever | A good note | The right jingle (13) |
| Rhythm, DJ Fever | A swap | Fever's bonus noise (11) |
| Sequences | A wrong tap, an empty slot, a timed-out sequence | The wrong jingle (1) |
| Rhyme | A wrong answer | The ring shakes 500 ms |

Each site is found by the shape of the code round it (`arena_shape`), checked to match once per copy.

### Input

`Desktop._arena_key` and `_arena_tap`:

| Input | Is |
| --- | --- |
| Enter, Space, a controller's confirm, a tap anywhere | OK |
| Arrow keys, D-pad | The joystick |
| Backspace | The right soft key (back) |
| 0–9; with the keypad labels shown, a tap on an item | Number keys |
| Escape, a controller's Start | The pause menu, as ever |

### The end of a game

Once the timer runs out: a "Time's up!" bubble, about 2.5 s of tallying, then "your score: n". In this fork the panel holds input between them
(`NRArena.time_up`) so a last tap can't skip them, and presses the first OK itself after 2 s (`TIME_UP_MS`).

718 closes the panel and the score goes back to the script. The library's games then turn it into the grade and return that in B.

### Skipping

Service 213 goes before every arena game: −1 plays it, anything else is the result, as the game would leave it. With Ask to Skip Mini-Games on, its options
are the routes the story takes by result (`choice_hints.arena_outcomes`): each result 0–15 is played on a copy 30 panels on, and neighbours that read the same
are one route. Checked against all 107 arena games at every result: 100 have two routes, 6 three, and 1 one.

## The library's rules

**Rhythm** (entry 31473; arguments: target, −1, 2, 1, −1, seconds, intro, end).

- 6 slots. One empty slot refills every 750 ms: good, bent and swap at 3 : 3 : 1. A kind filling 5 slots spawns as a swap.
- **Good hit:** score += speed (1–10), speed +1. At max, a bonus streak adds too. The note's picture changes at speed 8 and at max (20 → 17 → 19).
- **Bad hit:** speed halves, the streak resets, the ring shakes 0.5 s.
- **Swap:** flips good and bent.
- **Decay:** speed drifts down, about a level a second at max.
- **Grade:** thresholds reached, 0–10. For 60 s or more: 15, 25, 50, 100, 175, 275, 400, 625, 900, 1,200.
- **First play** of a game gives +2 grades: the marker shows 2 lower, and 2 is added to the result.

**Rhyme** (entry 32611; arguments: target, −1, seconds, interval, word set, 0, pairs, 0, −1, intro, end).

- 4 words round the ring, under "`cat` rhymes with...". OK when the rhyme is under the selector.
- +3 right, −3 wrong, floored at 0. Two sets of 33 pairs.
- Grade = min(10, 8 × score ÷ seconds).

**Sequences** (entry 28903) picks items in a target order on keys 1–6. The stories pass the library's own tables, its picture lists at 32426 and 32427 and rows at
32423, so arena builds keep those reads (`read_builtin(linked=True)`). **DJ Fever** (entry 30244) collects good items, with a double-points fever mode.

**King of Diss** passes level + 3, capped at 10, to its practice, and targets 7 and 9 to its Rhyme battles.

## X360 Arena Skin

With the [X360 addon](ADDONS.md#shsx360-the-cancelled-xbox-360-game) imported, the switch draws the arena on the X360 game's turntable. Geometry, rules and saves are the
same. See [X360.md](X360.md#the-x360-arena-skin).

## Known limits

- The WinMo panel's property code wasn't compared with the Java's.
- The menu and info box's own layouts aren't decoded.
- HUD box words 3 and 4 are inferred.
