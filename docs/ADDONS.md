# Addons

An addon is a pack of resources kept apart from the episodes that use them. It's an ordinary EXP archive, so it imports the
same way an episode does, but no picker lists it. Addons are this fork's own feature: native players and upstream exp-runtime
never read them.

The record format is in [SCHEMA.md](SCHEMA.md#addon-extension-shshd-runtime). This page covers how they behave, what the
current addons hold and how to build them.

No addon ships with the runtime, and no game art belongs in the repository. Each is built from the player's own game files by
`tools/translate`.

## Why they exist

Of the 299 MB of resources in the 50 New Rules translations, 263 MB is also in other episodes. With those in one addon, the whole
set takes about 90 MB, and the episodes' scripts don't change. An addon also gives a home to what belongs to no single episode, such
as a minigame library, a renderer's skin or an optional art pack.

## Required and optional addons

| Kind | Who asks for it | Without it | Examples |
| --- | --- | --- | --- |
| **Required** | The episode, in its `requires` record | The episode opens for indexing and previews, but starting it shows a message naming the addon | `shsnr` and `shsx360` for their own stories |
| **Optional** | The player, through `ContentLibrary.addon(id)` | Everything works, and the addon's switches aren't offered | `shsx360` as New Rules' arena skin; `chslim` in Cause of Death; `shshw` in the Surviving Hollywood Preview; `shsx360anim` in the X360 stories (Josh's dance, the leash game's cast) |

An addon can be both: New Rules' stories never declare `shsx360`, but the X360 Arena Skin reads it when it's there, and the X360
stories require it.

## In the library

The manifest keeps addons in an `addons` list, apart from `episodes`, one per id:

- a higher revision replaces a lower one, and the old file is deleted;
- a rebuild at the same revision replaces it too;
- a lower revision is ignored.

An import can hold addons and the episodes that need them together, in any order.

**Staged and bulk imports** take addons as they take episodes: put them under `shs_episodes` or `cod_episodes`, in any subfolder
([staged_import.py](../packages/engine/src/exp_runtime/staged_import.py)). The library they go to is the one that folder fills, so
`chslim` goes under `cod_episodes`.

**Sync Devices** sends them with the episodes ([below](#sync-devices)). The iOS and Android builds take them the same way.

### Lookup

For a required addon, an episode-bank resource (26000 and up) resolves from the episode first, then from each addon in the order
the episode lists them (`EpisodeResources._bank_archive`). Lower IDs keep coming from the game package.

The addons reuse numbers (the frame backdrop 26999 and the relationship icons 26991-26997 are in several), so in an episode that
lists more than one, the first wins. An episode made in the Creator lists its primary add-on first, and names each picture or sound
it takes from another (an extra) in an alias table (SCHEMA.md "Presentation extension", `aliases`), which is read before that
lookup. Mini-games read their art from their own addon directly, whatever else the episode lists.

An optional addon is never part of that lookup. Whatever uses it asks the library for it and reads its archive directly. This means
its IDs can't collide with an episode's own.

### Superseding

An addon can declare that it replaces others, in its `provides` record:

```json
{"id": "chfull", "title": "Claire Hart", "revision": 1, "supersedes": [{"id": "chslim", "revision": 1}]}
```

It promises to hold everything those addons hold under the same IDs, at those revisions. Then:

- importing it deletes them;
- `ContentLibrary.addon('chslim')` returns it, with the revision it stands in at;
- episodes requiring `chslim` read it, and a story that needs a higher revision than it stands in for still reports `chslim` as
  missing;
- importing `chslim` afterwards is ignored, unless it's newer than the revision the other stands in at.

## Revisions and rebuilding

A revision numbers an addon's resource layout. An episode's requirement is a minimum, so a newer addon serves every older story.

Keep every resource's ID once it has shipped. Add new ones at the end of a range. A story only needs rebuilding when it uses
something new, so stories can ask for less than the newest revision (`Story.addon_revision` in the X360 translator), and keep their
saves.

Replacing an episode adds a new record beside the old one, as an episode's id is its hash. Remove the stale record with
`ContentLibrary.remove_episodes`. Saves are kept.

## Picker icons

Each translated game's add-on holds the game's icon for a game chooser that lists the add-on games beside SHS and CoD
(owner, 2026-11-21; ROADMAP 3.31): packed now, so that feature needs no add-on update. The player doesn't read them yet.

| Resource | What |
| --- | --- |
| 26950 | The spec, JSON: `{"version": 1, "games": [{"key", "title", "icon", "smooth"[, "edition"]}, ...]}`, one entry per game: its tag (`nr`, `brew07`, `brew08`, `shs11`, `shw`, `x360`), its name for the chooser, the resource of its picture, `smooth` false for pixel art (scaled nearest), and `edition` where one add-on holds two games (`shsbrew`: '07 and '08, as the Title Screen Looks tell them apart) |
| 26951 on | The pictures: square PNGs at their source size, which the chooser scales to its icon |

The owner's picks (2026-11-21), from the player's own files and the Web Archive's store art in the owner's reference
folder (never shipped with the project):

| Add-on | Game | Picture |
| --- | --- | --- |
| `shsnr` (revision 6) | New Rules | EA's store thumbnail (`product-thumbnail_shsnr`, 150 px) |
| `shsbrew` (14) | '07 | Centerscore's box art (`92046_front`, its top 150 px) |
| | '08 | EA's store thumbnail (`product-thumbnail_SHS`, 150 px) |
| `shs11` (4) | '11 | Its own app icon (the 480x800 jar's `icon.png`, 102 px) |
| `shshw` (9) | Surviving Hollywood | Vivendi's banner: the logo and gold reel (`bannerhollywood`, 178 px) |
| `shsx360` (23) | X360 prototype | It had none: its title logo and the logo's black splat on its rayed sky (MS4's `gui` art, 256 px) |

`tools/translate/addon_icons.py` makes them: each builder adds them as it builds (`add_icons`, which warns and goes on
without the reference files), and `addon_icons.py patch IN OUT` adds them to an add-on already built, raising its
revision by one and keeping every other record byte for byte (how the 2026-11-21 revisions were made). The DSi and
Claire Hart add-ons have none yet.

## The addons

### `shsnr`: New Rules

Required by every [New Rules](NEW_RULES.md) translation. Revision 6, about 45 MB; the stories ask for revision 3, since 4
adds only the main menu's art, 6 only its [picker icon](#picker-icons) and 5 only the arena's own info box (layout 23 and its hourglass in the skin;
[NEW_RULES.md](NEW_RULES.md)), which an older revision draws as a bubble.

| Resources | What |
| --- | --- |
| 25200 | New Rules' minigame library, run as a linked segment beside the story ([VM_SPEC.md](VM_SPEC.md)) |
| 26000–26173 | Backgrounds: 29 locations × 6 times of day |
| 26174–26178 | The arena's skin and frame |
| 26960–26963 | The [Title Screen Look](#settings) (revision 4): its spec, the X1i menu backdrop, Paula, Spike and Raven as a photo (EA Mobile's store header), and the WinMo logo |
| 26980–26994 | The 15 music tracks |
| 26999 | The frame backdrop |

Portraits stay in each episode, since each story numbers its looks in the order it meets them.

```sh
python tools/translate/translate.py newrules addon --pud RES_LARGE_PUD --x1i X1I_JAR --store-art STORE_ART_FOLDER --out OUT_DIR
```

`STORE_ART_FOLDER` holds EA Mobile's store art from the Wayback Machine (`header_mob_shsnr.jpg`); without it, or without
`--x1i`, the addon has no Title Screen Look.

### `shsx360`: the cancelled Xbox 360 game

Required by the four [X360](X360.md) stories, and read optionally for New Rules' X360 Arena Skin. Revision 23, about 48 MB (23 adds only its [picker icon](#picker-icons)).
Revision 22 moves Josh's dance and the leash game's cast into their own add-on, [`shsx360anim`](#shsx360anim-the-x360-animations)
(owner, 2026-11-18), so this one is about half the size; no story needs them. Revision 21 added the leash game's cast (89 MB
with it), revision 20 the dance under each room's own lights ([X360.md](X360.md#joshs-dance)).
Revision 17 adds the main menu's [Title Screen Look](#settings), which needs the MS3 prototype's data.pak too (`--ms3`); no story asks for it.
Revision 15 adds the prototype's main menu tune for [Title Screen Music](#settings). Revision 16 rebuilds Day of Diss's opening for taller frames (storyboard spec version 2; [X360.md](X360.md#day-of-disss-opening)), which Day of Diss now asks for. Revision 18 adds the Diss Battle's tune, which Monday Planner asks for; revision 19 adds Spike's
taunts, which no story needs. The other stories ask for what they did.

| Resources | What |
| --- | --- |
| 26100–26120 | Scene backgrounds (`x360.SCENES`) |
| 26200–26239, 26750–26784 | Portrait renders, 113 × 128 (`x360.RENDERS`) |
| 27200–27239, 27750–27784 | The same, 226 × 256 |
| 28200–28784 | The MS3 Characters set (`x360.MS3_LOOKS`) |
| 26300 | The skin's spec: what the renderers read to find everything below (from revision 19 also Spike's Diss Battle taunts, `battle.taunts`) |
| 26301–26391 | Pictures, font pages, sounds and music for the arena skin |
| 26400–26418 | The deck, digits and title-screen backdrop, shot in an emulator |
| 26420–26435 | The slot machine and leash game |
| 26436–26749 | The jewel puzzle |
| 26790–26793 | Diss Practice's notes (Josh's dance, 26794–26795, is `shsx360anim`'s from revision 22) |
| 26796–26805 | Day of Diss's opening: its timeline, stills, card and whip |
| 26900–26914 | Music, each track mixed with its ambience |
| 26960–26963 | The Title Screen Look (revision 17): its spec, MS4's sky with its clouds, the roof scene (MS4's splash, two schools, the city, and five on the roof: MS3's girl and boy, MS4's Kim, Josh and Ryan), kept above the buttons, and the logo with its splat and tapes, which in taller frames moves down to stay centred in the sky |
| 26982–26995 | Sound effects and emoticons |
| 26996 | The main menu's tune (`music/main_menu`, mixed as the tracks are; `x360.MENU_MUSIC`) |
| 26997 | The Diss Battle's tune (revision 18): `music/dissdown`, which the prototype never plays (`x360.BATTLE_MUSIC`) |
| 26999 | The frame backdrop |

```sh
python tools/translate/translate.py x360 DATA_PAK --story addon --pud RES_LARGE_PUD --x1i X1I_JAR --looks NR_LOOKS_JSON \
    --portraits PORTRAIT_CATALOG --backgrounds BACKGROUNDS --dbp DECK_SHOTS --puzzle PUZZLE_SHOTS --opening OPENING_STILLS \
    --ms3 MS3_DATA_PAK --out OUT_DIR
```


### `shsx360anim`: the X360 animations

Read optionally by the [X360](X360.md) stories: Josh's dance behind Diss Practice's deck and Zack, the doberman and the
collar behind the leash game's bar. No story requires it; without it the games play as they did before the animations.
Split out of `shsx360` at its revision 22 (owner, 2026-11-18). Revision 2, about 47 MB: revision 1 with the cast's
shadow kept to the pound's floor, off its desk and crate (the dance byte for byte).

| Resources | What |
| --- | --- |
| 26300 | Its spec: `dance`, `dance_ms3` and `leash_cast` (format `shshd-x360-animations` 1) |
| 26794–26795 | Josh's dance on the steps, MS4's then MS3's (the MS3 Characters switch) |
| 26806–26809 | The dance under the hallway's and his room's own lights, MS4's then MS3's (`dance.rooms`) |
| 26810–26819 | The leash game's cast at 15 fps: an atlas per animation, MS4's five then MS3's (`leash_cast`) |

`translate.py x360 --story addon` writes it beside `shsx360` when given `--dbp` or `--leash` (the cast's frames, from
reference tools `x360_leashbooth.py` at `--size 960 540 --fps 15 --floor-mask pound_floor.json`, LOSE with `--pad 48`).
The mask (in the cast's folder) is the pound picture's floor in its pixels, less the crate, with the place it was cut
for; it must match `LEASH_CAST_PLACES`.

### `shs11`: Surviving High School '11

Required by the five [SHS '11](SHS11.md) stories, and read optionally for its Memory in place of letter grids. Revision 4, about 9 MB;
the stories ask for revision 2, since 3 adds only the main menu's art and 4 its [picker icon](#picker-icons). Its pack is 31600.

| Resources | What |
| --- | --- |
| 26000–26049 | Backgrounds, two for each of the 25 locations: 26000 + 2 × location + variant |
| 26100–26198 | Interface pictures, in gamelib's order |
| 26199 | The addon's spec, JSON |
| 26200–26624 | Portraits, 26200 + 5 × look + expression |
| 26800– | Parts no look draws |
| 26960–26962 | The [Title Screen Look](#settings) (revision 3): its spec, the photo cut out of gamelib picture 1's wood (its left border carried past the picture's edge), which drops in on the smartphone's own wood, and the logo, picture 21 |
| 26980–26991 | Music and sound, the last a copy for the story's selector 2 |
| 26992– | Relationship badges: heart, skull and smiley, whole and then broken |

```sh
python tools/translate/translate.py shs11 --art IT_480X800_JAR --english N73_JAR --sounds KG800_JAR --out OUT_DIR
```

### `shsbrew`: the BREW games

Required by every translated [BREW](BREW.md) story (126: the '08 Campaign, the Classic stories, the M.A.S.H. packs and Fall
'06), under either game's badge. It holds all their art and music, and the stories hold only their scripts. Revision 14,
about 19.3 MB; the stories ask for revision 7 (Theme Park's card 11), since the later ones only redraw pictures or add the
main menu's art and (14) the [picker icons](#picker-icons), '07's and '08's.

| Resources | What |
| --- | --- |
| 26000-26206 | Locations, three skies each: '08's, then '07's, then a sky alone (`brew.BACKGROUND_BASE`) |
| 26300-26364 | The catch game: frame, ring, digits, captions, then each item and player picture (`brew.CATCH_BASE`) |
| 26400 + picture | Time badge icons, BREW's small pictures 101-166 at the smartphone's size, 92 pixels (`EVENT_ICON_BASE`), and from revision 13 its heart (80), badger (276) and lizard (279) |
| 26600 | A story's own icon: CS Idol's yawning face (`OWN_ICON_BASE`) |
| 26900-26914 | Music, tracks 8000-8014 |
| 26960-26962 | '07's [Title Screen Look](#settings) (revision 12): its spec, the lilac tile, and picture 47 without CENTERSCORE, its band carried to the edges (it doesn't drop in) |
| 26970-26972 | '08's Title Screen Look (revision 12, with `--java-08` and `--store-art`): its spec, Java '08's blue SHS tile, and EA's store thumbnail as a photo |
| 26991 | The frame backdrop behind a pink box |
| 26992-26997 | Relationship icons: heart, skull and smiley, whole and then broken |
| 26998 | The spec: each story's looks, the Classic stories' own backgrounds, the catch game |
| 26999 | The frame backdrop |
| 27000- | Portraits, five faces each, 381 looks |
| 29000- | The Classic stories' own backgrounds, three skies each; '08's redraws of eleven of them 500 above |
| 36000- | The Java '08 Look: the demo's copy of a picture, 10000 above BREW's (frame, relationship icons, badge icons, catch game) |

Revisions: 2 the event icons; 3 the Java '08 Look; 4 the Classic stories' own backgrounds; 5 '08's redraws of them; 6 the
yawning face the catch games show; 7 that face as an event icon, and King of the Road's Michael centred; 8 the TV turned to face
the middle; 9 the Kid lowered onto the ring; 10 the badge icons at the smartphone's size; 11 Theme Park's card picture; 12
the Title Screen Looks; 13 the heart, badger and lizard as badge icons, which *Sadie Hawkins Day* and Fall '06 ask for.

```sh
python tools/translate/translate.py brew --base-08 GAME_08_FOLDER --base-07 MODULE_07_FOLDER --casts BREW_CASTS_JSON --java-08 JAVA_08_JAR --store-art STORE_ART_FOLDER --shs-hd-episodes SHS_HD_EPISODES_FOLDER --out OUT_DIR
```

### `shshw`: Surviving Hollywood

Optional for the BREW Classic *Surviving Hollywood Preview* (31100, 73), and required by Surviving Hollywood's own chapters
(pack 31700, [HOLLYWOOD.md](HOLLYWOOD.md): the Lite revision 4, *The Bright Lights* revision 8). Revision 9, about 4.2 MB (9 adds only its [picker icon](#picker-icons)).
Built from the Surviving Hollywood demo's 240 × 320 jar (1.0.2): its painted portraits, its backgrounds, its dialogue panel as
the frame, its music, its catch game's look, its status bar's moon and sun (revision 5: the full chapter's daytime badges) and
its soft key's phone (revision 8: the journal's badge); and from the low-end 1.0.4 (88K) demo's jar, its eight silhouettes
(revision 6: the full chapter's people with no portrait; revision 8 adds them turned). Its numbers stay as they are. Revision
1 had the portraits at 4 times and no frame, music or turned faces; revision 2 had no catch skin or moon; revision 3 had no
numbered star or star badge; revision 4 no sun; revision 5 no silhouettes; revision 6 no Title Screen Look; revision 7 no
turned silhouettes or phone.

| Resources | What |
| --- | --- |
| 26600 | The catch game's board: the demo's layouts 4 and 44 (its header with two boxes, copper rims) drawn as its code does (`tools/translate/shw_ui.py`), the field filled with its 0x9198FE from y 39, at 3 times |
| 26601, 26610-26619, 26620-26621 | `Score: ` and the digits in its main font, and its closing lines `Time is up!` and `Max Points!` (strings 47, 48), at 3 times |
| 26630 | The star the demo's player steers (sprite 59), at 3 times |
| 26631 | Its status bar's moon (sprite 43) as a time badge icon, BREW's icons' size |
| 26633 | Its status bar's sun (sprite 67), the same way: the full chapter's daytime badges |
| 27200-27207 | The 1.0.4 demo's eight silhouettes (its sprite sheet 3000: a waving boy, a small girl, a man in a cap, a broad man, a heavy man, a rocker with a guitar, a posing woman, a woman in a dress) as portraits: their pedestal shadow left off, at 6 times, the head where the whole figure at 4.5 times would put it, the rest running down past the ring. Built only when that jar is given (`--lite-demo-jar`) |
| 27208-27215 | The same silhouettes turned the other way (revision 8), worn for the sprites the full chapter shows turned (`shw_full.TURNED_SILHOUETTES`) |
| 26632 | The star (sprite 59) as a badge icon, the same way: the lite chapter's place badges |
| 26634 | The soft key's phone (sprite 57) as a badge icon, the same way (revision 8): the full chapter's *Quest journal updated* badge |
| 26701-26745 | Its 45 icons (2501-2545) as catch pictures, at 3 times |
| 26012-26110 | Backgrounds 1504-1536, at 26000 + 3 × (picture − 1500) + BREW's sky mode (day, night, sunset), each over the demo's own sky strip, 6 times their pixels. A picture with no sky window is the same under all three |
| 26960-26964 | The [Title Screen Look](#settings) (revision 7): its spec; the main menu's layout 9 (the spotlight panel, rims, film strip and round logo, which stays under the photo) as a top, a two-row middle and a bottom, built at the frame's height; and the city map (1100, its sky filled; its middle doubled exactly, a little smaller in the 3:4 frame so the logo shows) as a photo |
| 26901-26914 | Music, the demo's cues 3001-3014 (city noise, club, comic, exciting, failure, fail tone, main menu, map day, map night, ringtone, sentimental, stressed, success, success tone), at 26900 + (cue − 3000), rendered through Java's synthesizer as BREW's are |
| 26990 | The frame backdrop: the demo's orange panel (sprites 4 and 5 of its resource 16, `tools/translate/shw_sprites.py`) with its copper rim along each edge of the strip, in the shape of BREW's (26999) |
| 26998 | The spec, JSON. Its catch pictures also list the star under 2499, a number no demo resource has, so an episode's catch list can name it |
| 27001-27052 | Portraits 2001-2052, at 27000 + (picture − 2000): 3.5 times their pixels, as BREW's portraits are, on a 256 × 300 picture, standing 7 art pixels above its foot |
| 27101-27152 | The same portraits turned the other way. The player mirrors a right-hand portrait, so a face the demo drew turned to its left looks away from the middle there |

**The Preview names them itself.** Its presentation record maps the BREW add-on's pictures and music to these (`optional_art`),
and the runtime serves them while `shshw` is imported and the **Use SHW Art in Preview** switch is on (`EpisodeResources._optional_art`).
The mapping is the translator's (`shw.PREVIEW_FACES`, `shw.PREVIEW_SCENES`, `shw.PREVIEW_MUSIC`; owner's picks):
- **Faces:** four of the Preview's speakers (Chelsea, The Jeff, Milan, Donny) take the turned copy, decided one by one with the
  owner; the rest face front or toward the middle as drawn.
- **The dream:** the welcome and red-carpet dream showed '07's dance floor, as the club does, so those two scene changes name a
  location of their own (30002-30004), an alias of the dance floor (`aliases`), which the map draws as the red carpet.
- **Music by role:** each of the Preview's 18 music calls plays one of nine numbers of its own (30010-30018), an alias of the
  BREW cue it had, which the map draws as a demo cue: the welcome is the main menu's tune, the club `club`, the chase `exciting`,
  though all three were BREW's `action`.
- **The frame** takes the place of BREW's (26999) and of its pink copy (26991): the demo's panel never turns pink.
- **The time badge** (`7:30 PM - Pheno what?`) shows the demo's moon for BREW's (event icon 139).
- **The catch game** ("Be cool!"): the Preview maps BREW's board (26300) to the demo's, which tells the catch renderer to
  draw the demo's skin (`desktop_brew_catch.draw_skin`, with `EpisodeResources.optional_art_source`): the board, `Score: n`
  centred in its left box, the bar of items still to come in its right box, its closing line. Its pictures by BREW number
  (owner, 2026-11-13): the player's face (151) is the star, the smile (152) 2522, the laughing face (128) 2525, the lightning
  (130) 2534's "pow", each centred on BREW's place. The game itself is BREW's: the demo's catch game is the same one.

The Preview was version 4 from this change and is 5 now, with badges for one line only (3 had no catch skin or moon; 2 only
the portraits and backgrounds).

**Switch:** "Use SHW Art in Preview" (its SHW in the Surviving Hollywood tag's gold, as the Arena Skin's X360; called "Hollywood
Art" until 2026-11-19), with the '07 tag, on by default: on the Add-Ons page in the Preview, and on Per-Game Settings when the
library holds `shshw`.

```sh
python tools/translate/shw.py --demo-jar SURVIVING_HOLLYWOOD_DEMO_JAR --out OUT_DIR
```

**Surviving Hollywood's chapters** (pack 31700, badge SHW in the logo's gold, filed under Surviving Hollywood; owner,
2026-11-14; [HOLLYWOOD.md](HOLLYWOOD.md) has the whole story). Phase 2 is *The Bright Lights (Lite)*, the 1.0.4 demo's retelling of Chapter 1
(`tools/translate/shw_lite.py`). It requires `shshw` only, never the BREW add-on, and takes from it, through the profile's
pack tables: the frame (26990), the catch game's skin with its pictures by number (`TRANSLATED_CATCH_ADDON`, so
`desktop_brew_catch` reads this spec instead of BREW's), the demo's main-menu tune for Title Screen Music (`shw`, 26907),
and Use Translated Mini-Games. Its names (`$USR`) are a table of their own (`shw`), apart from every other game's. The
catch game's Instructions line becomes the page it opens with (as BREW's catch pages), and the fight's four action-menu
rounds become SHS's timed word game (71), as BREW's spinning-menu routine does. 1.0.4 keeps no clock, so its place badges
carry no time. It is episode 2; Phase 3, *The Bright Lights* (`tools/translate/shw_full.py`, the 1.0.2 demo's full
month), is episode 1 and takes the same from `shshw`, plus the sun and moon as its time badges' icons and the
silhouettes for its 21 people with no portrait (`shw_full.SILHOUETTES`). Its quest journal shows in the pause menu (`TRANSLATED_JOURNALS`) and its named lines without a portrait take
colours (`TRANSLATED_NARRATION_THEMES`). Its `--library`
option lists, beside the episode, the words its casing left lowercase that no SHS episode writes.

```sh
python tools/translate/shw_lite.py --jar LITE_DEMO_JAR --addon shshw.exp --out OUT_DIR
python tools/translate/shw.py --demo-jar DEMO_JAR --lite-demo-jar LITE_DEMO_JAR --out OUT_DIR
python tools/translate/shw_full.py --jar DEMO_JAR --addon shshw.exp --out OUT_DIR [--library SHS_LIBRARY]
```

### `shsdsi`: SHS DSiWare

Optional, for SHS's own episodes. Revision 2, about 5.9 MB. Built from the player's own image of *Surviving High School*
for DSiWare (2010, A2M; the EUR `.nds` or its CDN content file, the same bytes; all text is taken from EUR, decision 12) and
an SHS library holding the eight stories the DSi ported, as the owner decided on 2026-11-15
(`reference/Other Games/docs/DSI_ADDON_SCOPE.md`). It brings two things: the DSi's redrawn backgrounds (revision 1), and its
French, Italian, German and Spanish translations of those eight stories (revision 2).

| Resources | What |
| --- | --- |
| 26000 | The spec, JSON: `bank` (a smartphone picture: [DSi picture, same time of day]), `screens` (a DSi picture: [left, right]), `stories`, `text` (26900) |
| 26001– | The screens, 192 × 256 PNGs upright: 26001 + 2 × the picture's place in `dsi.PICTURES`, its right screen after |
| 26900 | The translations, JSON: `lines`, `context`, `menu`, `words` (below) |

#### The backgrounds

The DSi redrew the smartphone bank's locations as 2D pictures, each two screens, a left and a right, where the smartphone
pans one wide picture.

**The map** (`tools/translate/dsi.py`). A DSi scene changes background with `table[location + time]`, a table of name hashes
filled at start-up, in groups of three (day, night, sunset; the DSi repeats a time it didn't draw: `INDEX_GROUPS`). The
smartphone's bank is laid out the same way, a location at 1000 + 3k and its night and sunset after it. Aligning the eight
shared stories' background changes by the first line each shows paired the two (`BANK_GROUPS`); the rest were matched by
eye. 1003 (the arcade's pool table), 1024 (bus stop), 1075 (music room), 1099 and 1102 (washrooms) have no DSi drawing, and
the DSi drew the auto shop from outside where the bank's three pictures are inside (its own pairing, kept).

**Which episodes** (`exp_runtime/dsi.py`): SHS's own (not a translation from another game, nor an episode on an add-on)
whose every background, read from its scripts' constant arguments (services 11, 34, 35, 86 and title cards), has a DSi
picture:
every episode takes whatever the DSi showed for a picture, its stand-in times included (a night den is its day den).
At first only the eight stories the DSi ported (Football Star and Classics 1, 2, 5, 7, 8, 10 and 12) did, and any other
episode needed the same location at the same time; since 2026-11-18 every episode does (owner), which took test-library
from 28 qualifying copies to 87.

A picture of the episode's own that is plain black (a fade or flashback screen) needs no counterpart and shows as it is
(owner, 2026-11-15): seven episodes were held back by nothing else.

**In the episode list** (list view only, owner 2026-11-15): while DSi Backgrounds is on, an episode that shows them has a
DSi tag beside its play button, left of an SD or translated game's tag. Finding that out means opening the episode
(about 0.1 s on a PC), so a background thread does it the first time a row is drawn and the library keeps the answers in
`dsi_backgrounds.json`, for the add-on file it holds and the rule (`dsi.RULE`) it was measured under (`dsi.known`,
`dsi.measure`); the tag appears when it's known.

A background a script picks at run time is looked up the same way when it appears; one with no DSi picture shows as before.

**In play** (`Desktop._dsi_screen`): the left screen while the location is aligned left (a speaker on the left), the right one
while it's aligned right, the last one for narration; a change crossfades over the location layer's 0.25 s in either
presentation. A screen is the frame's own 3:4: it fills HD's frame and covers a taller one centred, its sides cut.

A minigame that draws its own frame (the word grid) keeps its own background.

#### The translations

**Reading them** (`tools/translate/dsi_text.py`). The DSi compiled each scene to C++ once per language: Football Season is
overlays 0–4, one language each; each Classic overlay holds all five, one after another. The copies are the same machine code
but for their literal pools, so a French line is the one the French copy's same instruction loads:
- the copies are split into functions (at each `push {…, lr}`; they have the same functions in the same order), and within
  a function the k-th string load in English is the k-th in French;
- where one language loads fewer strings (English shows a quiz question twice, as narration in quotes and as the prompt;
  French loads one and copies its register), the two are walked in step, following the copied registers;
- pointer tables no load reads (questions picked by index) pair in order, and a record a scene copies (a word grid's
  rounds: title, prompt, words, letters) pairs word by word.

About 99.7% of English lines pair in all four languages. A pairing is dropped when its name tokens, number formats, menu bars
or line breaks differ from the English, or its length is far off (a neighbouring line slipped in).

**Matching them** to the smartphone's text: a DSi line is kept when its English is one of the story's lines (in any copy in
the library, by letters, digits and tokens), or when it sits alone between two kept lines whose smartphone lines are as far
apart: a line the DSi rewrote (Weebox 360 as "the game thing"), which shows the DSi's wording (decision 10). A line with
different translations in different scenes takes the most common, and the others by the line shown before it (`context`).
The menu text (`GameText`) adds speaker names and episode titles (`menu`). Text is written in Latin-1, `œ` as `oe` and `…` as
`...` (decision 9). A word grid's words and letters (`words`, matched by the English exactly) are the DSi's own lists, which
it rebuilt per language (decision 11), lowercase and without accents for the grid's letter font. About 10,600 lines in all;
the lines the DSi cut (surveys, Faceplace, promos) stay English.

**In play** (`exp_runtime/dsi.py`, `Engine.substitute`): with General's "Preferred Language" on French, Italian, German or
Spanish, the eight stories (SHS's own copies, not a translation from another game) show it in the HD presentation only (decision 8: SD's bitmap fonts have no accents), from the
next line; the HD faces now draw Latin-1's accented letters (`vector_text.LATIN1_EXTRA`). Name tokens are kept, and a token
holding a name the DSi translates shows that name (German renames many characters, decision 16), never the player's own
(`$USR`). A quiz's title, prompt and word lists follow it, and choices show the DSi's "Make your choice!". The episode list
shows the stories' DSi titles: SHS's own copies only, as for the lines (a translated game's story of the same name, New Rules'
Making Some Dough, keeps its title; owner, 2026-11-18). A save keeps the line as shown, and loads in any language (`Engine.shown_forms`).

**Option:** "DSi Backgrounds" (DSi tag) on Extras, the main menu's and the pause menu's: Off (the default), Sharp (nearest
neighbour) or Smooth, when the library holds `shsdsi` (in play: when the episode qualifies). Until 2026-11-19 it was a switch and a
"DSi Pixels" choice on Add-Ons; they stay two settings underneath (`dsi_backgrounds`, `dsi_pixels`), so Sharp or Smooth is kept
while it's Off (owner, 2026-11-19). Its language is General's Preferred Language (owner, 2026-11-18; until then a "DSi Language" of its own), with the
HD bundle: English is the stories' own.

```sh
python tools/translate/dsi.py --nds DSI_IMAGE --library SHS_LIBRARY --out OUT_DIR
```

### `chslim`: Claire Hart (Slim)

Optional, for Cause of Death. Revision 2, about 17 MB (revision 1, about 21 MB, also held Claire Hart's own extras: see `chc`).

CoD's portraits are 110 × 120, downscaled about 4.17 times from Claire Hart Classic's 458 × 500 originals, so this pack carries the
sharper art. CoD's episodes can't name an addon and a portrait's ID differs between episodes, so the player finds it by a hash of the
picture's bytes in the map at resource 28000 (`EpisodeResources._addon_portrait`, the profile's `PORTRAIT_ADDON`). The original's
size in play doesn't change, as `standard_portrait` keeps it at the size CoD's picture fills.

| Resources | What |
| --- | --- |
| 28000 | The map and contents, JSON |
| 28001 | The backdrop beside the frame |
| 28010 on | Portraits, each at 28010 + its place in the sorted list of all 835 (CoD's matched ones only) |
| 29000, 29001 | Pictures made for CoD: Natara's shocked portrait with her tie, Kai's shocked portrait from SHS HD |

- **Map keys:** a hash for any resource with that picture, or `hash:resource` for one expression where CoD uses one picture for
  two. Kai's sad and shocked share a picture, so his shocked has its own entry.
- **Left out of the map:** Sophie. Claire Hart's version has pink hair, and her red hair is plot-relevant.
- **Revision 2 (owner, 2026-11-19):** only what CoD shows. Revision 1 also held the rest of Troy Harris, Paul Clayton and Claire,
  the speech bubbles (28002, 28003) and the Romic fonts (28004, 28005), for playing Claire Hart's own episodes from it; checked
  against every Classic episode, that covers 4 of 107 cases, story only (Other Games/docs/CLAIRE_HART_PLAN.md, "chslim for
  translation"), so those moved to `chc`.
- **Stable IDs:** so that `chc` supersedes it. Both hold each portrait under the same ID.

**Switches:** "HD Portraits in CoD" and "Backdrop" on the Add-Ons page, with the CH tag, shown when the addon is imported and on by default.
The backdrop takes the place of the SHS HD Backdrop in play and on CoD's menus.

```sh
python tools/translate/chslim.py --mirror CLAIRE_HART_DIR --pairs PAIRS.txt --catalog COD_CATALOG_PORTRAITS \
    --cod-library COD_LIBRARY --extras EXTRAS_DIR --out OUT_DIR [--chc]
```

### `chc`: Claire Hart Classic (in progress on the `claire-hart` branch)

The add-on of the translated Claire Hart Classic cases (Other Games/docs/CLAIRE_HART_PLAN.md), pack 31500. Revision 1 began
(2026-11-19) as chslim revision 1 exactly, under the same IDs and the same map at 28000, so CoD's portrait swap works the same
from either. Since Stage 1 (2026-11-19) `tools/translate/claire_hart.py addon` writes it (454 MB): chslim revision 1's
resources (`chslim.contents(chc=True)`) and everything else of Classic's, used by a case or not, under its own record (`chc`,
superseding chslim at revision 2). It keeps revision 1 until it goes to testers.

```sh
python tools/translate/claire_hart.py addon --mirror CLAIRE_HART_DIR --pairs PAIRS.txt --catalog COD_CATALOG_PORTRAITS \
    --cod-library COD_LIBRARY --extras EXTRAS_DIR --out OUT_DIR      # FFmpeg on PATH, for the tracks
python tools/translate/claire_hart.py report --mirror CLAIRE_HART_DIR
python tools/translate/claire_hart.py ids --mirror CLAIRE_HART_DIR --out claire_hart_ids.tsv
```

| Resources | What |
| --- | --- |
| 26000–26786 | The 787 scenes' backdrops (`template`), in the scene folders' sorted order: Classic's own PNGs (paletted; full brightness, dimmed at draw time) |
| 26900–26932 | The 33 tracks, MP3 128 kb/s |
| 26960–26962, 26990 | The Title Screen Look (its spec, Classic's Play Now forest, its logo) and Title Screen Music (the main jingle) |
| 26998 | The spec, JSON (version 1): `looks` (each look's 5 picture IDs: Normal, Angry, Happy, Sad, Surprised), `look_names`, `pictures` (portrait path → look, slot, ID), `scenes` (folder → backdrop ID, the 3:4 slice's left edge in the scene's pixels), `music` (track → ID), `story_objects` (picture path → ID) |
| 27000–27644 | The 645 story-object pictures, Classic's own PNGs |
| 28000–28005, 29000–29001 | chslim revision 1's, kept (the map, the backdrop, the speech bubbles, the Romic fonts, CoD's two edits) |
| 28010–28844 | All 835 portraits, each at 28010 + its place in the sorted list (chslim's rule): CoD's matches framed as chslim's, the rest whole at the same scale |
| 29100 | Claire Hart Dialogue's spec, JSON (`tools/translate/ch_dialogue_skin.py`): its density, text and emphasis colours, fonts, and where each picture is cut |
| 29101–29108 | Its art: the speaker body (the tail side mirrored away), the name tab, the narrator box, the new portrait ring and disc, the Play Now button (Continue, at rest and pressed) and the story-object square |

Importing it removes chslim, and an episode or switch asking for chslim gets `chc` (it stands in for chslim's revision 2).

**Pack 31500's episodes** (tagged `(CHC)`: the Claire Hart category, CH badge) require it. They draw its green backdrop (28001)
under their scenes (the cod profile's `TRANSLATED_FRAME_BACKDROP`), and name their looks through **look banks**
(`LOOK_BANKS`): CoD draws a look as 5 consecutive IDs, but chc holds each picture once, so ID 30000 + 5 × look + expression is
the picture its spec at 26998 (`looks`: 185 looks, a face a look lacks given as its Normal) names there
(`EpisodeResources._look_bank`). An episode's own resource at such an ID wins.

**Claire Hart Dialogue** (Add-Ons, CH tag; owner, 2026-11-19): CoD's dialogue in Claire Hart's speech bubbles with CoD's
attached portrait ring, for **Off**, **Claire Hart Cases** (the default: pack 31500) or **All Episodes**. The text and names are
Romic Bold (28005; Romic, 28004, lacks `/`, `&` and most accented letters) in Claire Hart's dark red, emphasis in its gold;
narration is Romic Bold slanted by the player (Classic ships no italic, and Romic is a commercial ITC face);
the name sits in the bubble's tab beside the ring; no tail; Continue is the Play Now button. Narration takes the narrator box,
with the ring when the narrator has a portrait. The CoD profile's `DIALOGUE_SKIN`; `content.EpisodeResources.dialogue_skin`.
Choices, message panels and title cards keep CoD's look for now (ROADMAP 4.1a).

Its backdrops stay at full brightness, as the rounds need them. The player darkens them as it draws a case's story, to 110/255 as
Classic did (its backdrop node's colour; the cod profile's `TRANSLATED_BACKDROP_DIM`), while the shared **Dim Backdrops** switch is
on (CH tag, on by default, offered once the library has a case).

The tool reads the real hashes from the CoD library, since a catalogue's copies are re-encoded, and stops with an error if a mapped
picture isn't found.

**Unverified:**

- Nothing draws the bubbles or fonts yet, so they haven't been seen in use. Romic is inferred from Claire Hart's asset list and a
  screenshot.
- The backdrop on CoD's menus was tested through its function, not captured on a menu screen.

## Settings

Switches that only concern translated games and addons live on **Options › Add-Ons** (`ADDON_KEYS` in `desktop_pause_hd.py`), which
hides itself when none of them is offered. Each carries its game's tag (`SWITCH_BADGES`, from `LEGACY_GAMES` in the game's profile).
On the menus a switch shows when the library has what it concerns. In play, it shows when it concerns that episode. The skin's
tag is New Rules', since it changes New Rules' episodes, and its label names X360 in that game's colour (`LABEL_TINTS`).

| Switch | Tag | Shown when |
| --- | --- | --- |
| Use Translated Mini-Games | | Translated episodes with minigames |
| '08 Backgrounds | '07 | '07 BREW episodes |
| Java '08 Look | '08 | '08 BREW episodes, with an addon built with the Java demo |
| Hi-Res Portraits | NR | New Rules episodes |
| MS3 Characters | X360 | X360 episodes |
| Smartphone Music | SHS11 | SHS '11 episodes |
| Use Word Grid Skin | SHS11 | SHS '11 episodes, with HD's word game art |
| HD Portraits in CoD, Backdrop | CH | CoD with `chslim` imported |
| Dim Backdrops | CH | Claire Hart's translated cases (pack 31500); on by default |
| Use SHW Art in Preview | '07 | The Surviving Hollywood Preview, with `shshw` imported |
| Use X360 Arena Skin | NR | New Rules episodes with `shsx360` imported; in play, also Use Translated Mini-Games on |

They're listed in the episode list's order of their games ('07, '08, New Rules, X360, '11, then CoD's), and last the two that need
two add-ons, Use SHW Art in Preview and the X360 Arena Skin (owner, 2026-11-19; `desktop_pause_hd.ADDON_KEYS`). DSi Backgrounds is an Extras option (above).

On the main menus (owner, 2026-11-09), Add-Ons keeps only Use Translated Mini-Games, and the other switches are one page in,
**Per-Game Settings**; the pause menu lists them all on Add-Ons. Episodes made in the Creator count for a switch through their
primary add-on.

**Title Screen Music** (the main menus, under Add-Ons) chooses the tune the main menu plays, once, as its own: Default (the
game's own), Auto (that of the game last played, by its pack or a Creator episode's primary add-on), or a translated game's
title tune from its addon, offered when the library holds that addon (`TITLE_MUSIC` in the game's profile):

| Choice | Addon | Resource | The game's |
| --- | --- | --- | --- |
| '07 / '08 | `shsbrew` | 26906 | Track 8006, the MIDI both games share |
| New Rules | `shsnr` | 26988 | Track 8 |
| X360 | `shsx360` (revision 15) | 26996 | `music/main_menu` |
| '11 | `shs11` | 26981 | Track 1, the main menu's one full tune; started 0.9 s in, past its silence (`audio.mp3_from`) |
| Surviving Hollywood | `shshw` | 26907 | Cue 3007, the main menu's tune |
| Claire Hart (CoD; `claire-hart` branch) | `chc` | 26990 | `Claire_Hart_Main_Jingle` (13 s), which Classic's episode select plays once after Play Now (`playsoundonload.js`), as an MP3 |

**Title Screen Look** (the HD main menus, under Add-Ons; owner, 2026-11-16) chooses its art the same way: Default, Auto,
or a translated game's own title art from its addon, offered when the addon carries it (`TITLE_LOOKS` in the SHS profile). The
gold buttons, their backdrop, the gear and the info button stay; the wood, photo, ribbon and title give way to the game's
(`title_look.py`), and the episode picker's backdrop follows. The first launch still drops the photo in and fades the title in
where the look has them. BREW's editions are two looks: Auto takes '08's after a Campaign story (31000) and '07's after a
Classic story or Fall '06 (31100, 31200). The looks are built by `tools/translate/title_looks.py`; which addon revisions carry
them is listed with each addon above as they land. The plan: `reference/TITLE_SCREENS_PLAN.md` beside the repository.

Cause of Death has one look so far, **Claire Hart** (`claire-hart` branch, Stage 0; the CoD profile's `TITLE_LOOKS` and
`TITLE_LOOK_PACKS`): Classic's Play Now screen, its misty forest and Claire and Paul over the gem banner, from `chc`'s spec at
26960. Chosen, it replaces CoD's painting behind the same buttons, laid out as SHS HD's menu lays a look out (the logo is the
look's title, fading in), and the episode lists' backdrop follows; Auto takes it after a Claire Hart case.

## Data Management

**Options › Data Management › Add-Ons** lists a library's addons, and hides itself when there are none. From the chooser it's always there, and picks the game first when both have a library. Each addon has:

- **Details:** its ID, revision and size, and the episodes that need it. Reading those takes a moment the first time, as the manifest doesn't record them (`ContentLibrary.episode_requires`).
- **Export:** its file, under its own name, into the Exports folder.
- **Delete:** after a warning that counts the episodes needing it. Those show the "needs the addon" message until it's imported again, and their saves stay. It also lets go of a game left for the main menu, which could be drawing from it.

Elsewhere:

- **Add Content** (Data Management's first row; Add Episodes before 2026-11-21) takes addons and fonts too, and says how
  many of each came. Episodes have versions of their own (resource 5, [SCHEMA.md](SCHEMA.md#episode-version-extension-shshd-runtime)): a newer one replaces an older copy, and the notice says how many were replaced, kept or left out.
- **Library Info** lists them, and **Storage** counts them apart from episodes.
- **Verify Library** checks them. A damaged file is removed, and importing the addon again restores it, as it does an episode's.
- **Export Episodes** exports only what you chose. When those episodes need addons, it says so afterwards and offers to export those too.

## Sync Devices

The send page's **Episodes & Add-Ons** switch sends every addon the other device lacks or holds at a lower revision, whether or not an episode being sent needs it, as optional addons aren't declared by anything. A same-revision rebuild stays where it is, since neither device can tell which is newer. An addon standing in for another counts as holding it, and receiving a full pack deletes the slim one it supersedes.

They travel in the offer step of [`lan_sync.py`](../packages/engine/src/exp_runtime/lan_sync.py), as `addons` beside `episodes`. A whole library sent to a device without one carries them already.

## In the Creator

See [CREATOR.md](CREATOR.md#add-ons). A project can take pictures, sounds and cutscenes from an addon by reference, or copy pictures and sounds in. One addon can be its **primary**: the episode then takes that addon's settings (frame, relationship icons, answer music, switches) as its translated stories have them. Others are extras, for their pictures, sounds and mini-games. It can't make an addon yet: that's what the steps below are for.

## Writing your own

1. Pick an id and put your resources at 26000 or above; for an optional addon, pick IDs episodes won't use.
2. Write resource 4 with `addons.provides_bytes(id, title, revision)`, and resource 1 with a `Metadata` of your pack and episode 0.
3. Save it with `exp.encode_exp`.
4. For a required addon, write `addons.requires_bytes([(id, revision)])` into each episode's resource 4.

`x360.build_addon` and `chslim.build` are short worked examples.
