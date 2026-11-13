# Surviving High School '11

*Surviving High School '11* is EA Mobile Montréal's J2ME game from 2010. It tells five of the smartphone stories again in flat-colour vector art, with its own two minigames. This fork translates those stories into `.exp` episodes on the SHS presentation, with the minigames ported.

None of the game's code runs here, and no file of it ships with the runtime: `tools/translate` reads the player's own jars.

**In the library:** five stories, pack 31600, tagged SHS11, in their own category, all needing the [`shs11` addon](ADDONS.md#shs11-surviving-high-school-11).

| Story | Reached lines | Lines the smartphone twin doesn't have |
| --- | --- | --- |
| Best Party Ever | 991 | 66 |
| The New Girl | 434 | 31 |
| Foreign Exchange | 309 | 24 |
| Lost Recipe | 441 | 17 |
| Secret Ingredient | 361 | 18 |

Those counts are floors, from a harness that took a few random paths rather than every one. Episode numbers follow '11's order, with Best Party Ever first.

## Building

```sh
python tools/translate/translate.py shs11 --art IT_480X800_JAR --english N73_JAR --sounds KG800_JAR --out OUT_DIR
python tools/translate/translate.py shs11 --english N73_JAR --story "The New Girl" --twin THE_NEW_GIRL_EXP --out OUT_DIR
```

The first writes the addon (`shs11.py`). All the big builds hold the same art at different sizes and the images hold no text, so the sharpest build serves every language, here the Italian 480 × 800 one. Its English text comes from the N73 build and its sounds from the KG800 build. The second writes a story (`shs11_story.py`), and needs the smartphone twin for the fallbacks below.

## How a story is translated

'11's machine, script queue and scene tables match SHS's, so each story keeps its scripts, with every host call rewritten for SHS's services (`HANDLERS` in `shs11_story.py`). A few things differ underneath:

- **Numbers.** An unset '11 number reads -1 and an SHS one 0, and the scripts test for -1, so a number is stored plus one.
- **Relationships.** '11's values 0-3 show 4-1 skulls and 4-7 show 1-4 smileys, or hearts for one chosen character. SHS's key 407 shows the same icons from negative numbers up.
- **Minigames.** Each game plays [Memory or Reflex](#minigames) with Use Translated Mini-Games on. Otherwise it plays what the smartphone has at that spot, or a letter grid of '11's words.
- **Sound.** Effects stay '11's own, along with its one sound channel and its relationship sounds and icons. With **Smartphone Music** on, the smartphone's music plays too, placed by the lines it comes before. '11's own music is almost nothing: one real tune and ten short cues.

## Minigames

[ENGINE_ABI.md](ENGINE_ABI.md#54-shs-11s-minigames-shshd-runtime-services-219-and-220) has the calls, and `shs11_games.py` the rules, from the jars' code. Both games run on a 3 × 3 grid with a clock ring, a score ring and usually 60 seconds. The result is **2** at 98% of the target or more, **1** above 75%, else **0**. Each shows its tutorial once per app launch, as '11's flags do, and a skipped game doesn't count as having shown it.

**Memory.** A word's cue line and banner appear, then its letters flash one at a time into random cells. The rest are bad boxes. Every cell turns to `?`, and the player picks the letters' cells from memory. Each letter scores 10, picking them in spelling order adds a Spelling Bonus of 20, and a bad box costs 5 seconds and the bonus.

**Reflex.** Nine icons deal into the grid over and over. Each is the scene's right icon, its wrong icon or a skull, with 1 to 3 bars. Picking moves a gauge by that many bars, and a skull resets it.

### Use Word Grid Skin

This Add-Ons switch, off by default, draws both games in the HD word game's look (`desktop_shs11_hd.py`) instead of '11's. It needs HD's art.

With the skin, sounds are HD's word game sounds, chosen by ear by the owner (`GRID_SOUNDS`):

| In the game | Plays |
| --- | --- |
| A wrong pick | 8109 |
| A word without its bonus | 8001, 8111 |
| A finished word | 8110, 8111 |
| Time up | 8113 |
| A right pick, in Reflex | 8001 |

### Memory in place of letter grids

**Options → Extras → Use '11's Memory for Word Grid**, off by default, plays Memory wherever an SHS episode has a letter grid (service 96). It's our own idea: '11 only swapped a grid for Memory once. It needs only HD's art or the addon, and these games always have the skin when HD's art is there. It carries its own instructions, reworded for touch screens.

`grid_memory` leaves a grid alone if it has pictures, a word that won't fit the 9 tiles, no score to reach, or a very short time. A round takes '11's usual points and its middle speed. The target is 75% of what a steady pace would score through the grid's own time. The story still gets the grid's own result: reached or not.

## Not done

- **Italian.** '11's Italian text isn't used, although the addon's art comes from an Italian build.
- **Lost downloads.** President's Day and Fitting In don't survive.
- **Hidden code mode.** '11 has one (hold 0 for 3 seconds). This fork's [Skip Ahead](MAIN_MENU.md) is an all-games version of its code 4687. Its others aren't ported.
