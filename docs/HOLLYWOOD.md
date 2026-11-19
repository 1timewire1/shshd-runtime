# Surviving Hollywood

*Surviving Hollywood* (2007, Vivendi Games Mobile) is the J2ME spin-off of Surviving High School, developed by Centerscore,
the BREW games' studio, on their engine. You play a young actress newly arrived in a parody Hollywood with a month to find an
agent. Only demos survive: the 240 × 320 1.0.2 build (the owner's Nokia 5610's) holds the whole of Chapter 1 behind a timer,
and the low-end 1.0.4 build (88K) retells it in silhouettes. The studies are `reference/Other Games/docs/SURVIVING_HOLLYWOOD.md`
and `SURVIVING_HOLLYWOOD_ENGINE.md`. This fork translates both into `.exp` episodes on the SHS presentation, with the demo's own art,
frame, music and minigames.

**State: final** (owner, 2026-11-17). *The Bright Lights* is at version 2, and *The Bright Lights (Lite)* at version 1.

None of the demo's code runs here, and no file of it ships with the runtime: `tools/translate` reads the player's own jars.

**In the library:** pack 31700, badge **SHW** in the logo's gold, filed under Surviving Hollywood, with its own names table
(`shw`), apart from every other game's.

| Episode | What | Needs |
| --- | --- | --- |
| 1: *The Bright Lights* | The 1.0.2 demo's month-long Chapter 1 (21 scripts, 2,901 lines) | [`shshw`](ADDONS.md#shshw-surviving-hollywood) revision 8 |
| 2: *The Bright Lights (Lite)* | The 1.0.4 demo's short retelling of it | `shshw` revision 4 |

The add-on also gives the BREW games' *Surviving Hollywood Preview* the demo's look: see [Use SHW Art in Preview](#use-shw-art-in-preview).

## Building

```sh
python tools/translate/shw.py --demo-jar DEMO_JAR --lite-demo-jar LITE_DEMO_JAR --out OUT_DIR
python tools/translate/shw_full.py --jar DEMO_JAR --addon shshw.exp --out OUT_DIR [--library SHS_LIBRARY]
python tools/translate/shw_lite.py --jar LITE_DEMO_JAR --addon shshw.exp --out OUT_DIR
```

The first writes the add-on, from the 1.0.2 jar (`560_ver1.0_b2_hs92_english.jar`) and, for the silhouettes, the 1.0.4 jar. The
second writes *The Bright Lights*: `--library` names an SHS library whose episodes show which words are capitalised, and the
build writes beside the episode the words its casing left lowercase that no SHS episode writes. The third writes the Lite.

## The Bright Lights

The demo's 21 scripts are KiWi v1 on the demo engine's own host ABI, with the game loop around them in Java. Here each script
stays as it is, an SHS script of its own (10002-10017 become 25002-25017, 11000-11007 become 25100-25107), with every host call
sent to SHS's services (`shw_full.py`). The loop is KiWi too: a driver script, the episode's first, holds the month's schedule as
data and its state in saved numbers.

- **The month.** 29 days of eight slots (8 AM to 3 AM, then bedtime). Each morning opens on a date card, `Monday, February 2`.
  At bedtime the player goes home and sleeps into the next day.
- **Cards.** The title card and every date card show SHS's city skyline at sunset (shared bank 1137, catalogue 0112, in its HD
  copy with SHS HD), as the other translations' cards show SHS pictures (owner, 2026-11-19; `CARD_PICTURE`; version 3). They were
  the demo's city from the hills and its living room, which have no HD equal.
- **Where to?** On the map the driver runs a pending script, else the slot's forced event, else asks **Where to?**: SHS's
  choice of the places open now, each `District: Place` with its opening hours under it in smaller letters, then **Quest
  Journal** and **Stats** (money, looks, body, stress). A place runs its story event if one is due, else its kind's script,
  after a time badge, `3:00 PM - Home`, with the status bar's sun by day and its moon by night.
- **Badges** show for the one screen they come with (a line, a menu, a page, a name entry or a minigame), and never over a
  title or date card.
- **Stat changes** come as a page of their own that waits, as the demo's panel does. Relationships stay hidden and the status
  bar is dropped. Options the demo greys out are left off the menu. The demo's numbers are kept.
- **Quest Journal.** The demo's journal (its quest script, 10005, on key 1) is the pause menu's **Quest Journal**: its quests,
  each opening its lines, rebuilt on each map turn and mid-scene, then a Stats page. Its reminder says `pause to view it.` Its badge, *Quest journal updated*, shows the demo's phone,
  which its tutorial says flashes when a quest is added.
- **Minigames** are SHS's, behind **Use Translated Mini-Games** and **Ask to Skip Mini-Games** as the other translated games'
  are. The action menus' routine and word association play as the timed word game (71). The catch games play as the BREW
  games' catch (221) in the demo's own skin: its board, `Score: n`, the bar of items still to come, the star you steer.
  The rehearsals' spelling plays as a one-word word grid (96), where a missed word scores the letters traced in their places
  (224), as the demo scores the letters typed right, so Glamlet's soliloquy can give its middle reaction.
- **Faces.** The cast wear the demo's painted portraits, some turned so that they face the middle of the box. The 21 people
  the demo gives no portrait (Mom, Dad, the cop, the kid, Myra, the telemarketer...) wear one of the 1.0.4 demo's eight
  silhouettes, chosen by the owner, also facing the middle; the street kid who says *You're bootyful!* is the girl's. The
  voices with no one behind them (Phone, Advice Column, Reel Times, Instructions) speak in SHS's named box, in the Lite's
  colours. Pages under the plate *You* (the map scripts' `I'm beat. Time to go home...`) are the player's own
  lines, with the portrait she picked; a page wholly in brackets is her thought.
- **Text.** Every full build of the demo stores its text in lowercase. The capitals come back by
  rule: sentence starts, a word list, names of several words, quoted titles, the districts, a joining word after `...` kept
  lowercase. Then every line was read in context (twice, the second time by three readers apart), and the lines the rules
  can't get right are written out whole in `tools/translate/shw_casing_fixes.json` (only their case may differ, which a test
  checks). The owner's calls are in `reference/Other Games/docs/SURVIVING_HOLLYWOOD_CASING.md`.

**Checked** against Tardy-Slip's engine (`engine/shw.js`, which follows the demo's Java) on 16 random months: the same lines,
the same scripts and the same numbers to the end.

## The Bright Lights (Lite)

The 1.0.4 demo's Chapter 1 (`shw_lite.py`), in the same art, frame, sounds and catch game, with place badges (the demo's star:
1.0.4 keeps no clock, so they carry no time), a title card (the same sunset city as the full chapter's; version 2) and the
same names table. Its catch game (the peanut-butter dodge)
plays behind Use Translated Mini-Games, else as a word game; its instructions open it as a page, as the BREW games' catch pages
do. The fight's four action-menu rounds are a timed word game (71). It matches the untranslated script line for
line on all 112 of its answer paths.

## Use SHW Art in Preview

The BREW games' *Surviving Hollywood Preview* (31100, 73) was a trailer for this game. With `shshw` imported and the **Use SHW Art
in Preview** switch on (the '07 tag, on by default; "Hollywood Art" until 2026-11-19), it shows the demo's painted portraits and backgrounds, its panel as the frame, its
music by scene, its catch game's look, its moon on the time badge and its red carpet for the welcome dream.
The Preview names those pictures and sounds itself (`optional_art`); [ADDONS.md](ADDONS.md#shshw-surviving-hollywood) has the
mapping.

## Settings

- **Title Screen Music** and **Title Screen Look** offer the demo's main-menu tune and its spotlight panel over the city map.
- **Use Translated Mini-Games** and **Ask to Skip Mini-Games**, as for the other translated games.
- **Use SHW Art in Preview**, for the Preview.

## Not done

- **The rest of the game.** Only Chapter 1 survives, in the demos.
- **Relationships and the status bar** aren't shown, by the owner's choice: the stats live in Where to?'s Stats page.
