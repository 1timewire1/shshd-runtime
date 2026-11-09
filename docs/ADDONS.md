# Addons

An addon is a pack of resources kept apart from the episodes that use them. It's an ordinary EXP archive, so it imports the
same way an episode does, but no picker lists it. Addons are this fork's own feature: native players and upstream exp-runtime
never read them.

The record format is in [SCHEMA.md](SCHEMA.md#addon-extension-shshd-runtime). This page covers how they behave, what the three
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
| **Optional** | The player, through `ContentLibrary.addon(id)` | Everything works, and the addon's switches aren't offered | `shsx360` as New Rules' arena skin; `chslim` in Cause of Death |

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

**Sync Devices** sends them with the episodes ([below](#sync-devices)). The iOS and Android builds don't support addons yet.

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

## The addons

### `shsnr`: New Rules

Required by every [New Rules](NEW_RULES.md) translation. Revision 3, about 45 MB.

| Resources | What |
| --- | --- |
| 25200 | New Rules' minigame library, run as a linked segment beside the story ([VM_SPEC.md](VM_SPEC.md)) |
| 26000–26173 | Backgrounds: 29 locations × 6 times of day |
| 26174–26178 | The arena's skin and frame |
| 26980–26994 | The 15 music tracks |
| 26999 | The frame backdrop |

Portraits stay in each episode, since each story numbers its looks in the order it meets them.

```sh
python tools/translate/translate.py newrules addon --pud RES_LARGE_PUD --x1i X1I_JAR --out OUT_DIR
```

### `shsx360`: the cancelled Xbox 360 game

Required by the four [X360](X360.md) stories, and read optionally for New Rules' X360 Arena Skin. Revision 15, about 54 MB.
Revision 15 only adds the prototype's main menu tune for [Title Screen Music](#settings); the stories still ask for 14.

| Resources | What |
| --- | --- |
| 26100–26120 | Scene backgrounds (`x360.SCENES`) |
| 26200–26239, 26750–26784 | Portrait renders, 113 × 128 (`x360.RENDERS`) |
| 27200–27239, 27750–27784 | The same, 226 × 256 |
| 28200–28784 | The MS3 Characters set (`x360.MS3_LOOKS`) |
| 26300 | The skin's spec: what the renderers read to find everything below |
| 26301–26391 | Pictures, font pages, sounds and music for the arena skin |
| 26400–26418 | The deck, digits and title-screen backdrop, shot in an emulator |
| 26420–26435 | The slot machine and leash game |
| 26436–26749 | The jewel puzzle |
| 26790–26795 | Diss Practice's notes and Josh's dance |
| 26796–26805 | Day of Diss's opening: its timeline, stills, card and whip |
| 26900–26914 | Music, each track mixed with its ambience |
| 26982–26995 | Sound effects and emoticons |
| 26996 | The main menu's tune (`music/main_menu`, mixed as the tracks are; `x360.MENU_MUSIC`) |
| 26999 | The frame backdrop |

```sh
python tools/translate/translate.py x360 DATA_PAK --story addon --pud RES_LARGE_PUD --x1i X1I_JAR --looks NR_LOOKS_JSON \
    --portraits PORTRAIT_CATALOG --backgrounds BACKGROUNDS --dbp DECK_SHOTS --puzzle PUZZLE_SHOTS --opening OPENING_STILLS --out OUT_DIR
```

### `shs11`: Surviving High School '11

Required by the five [SHS '11](SHS11.md) stories, and read optionally for its Memory in place of letter grids. Revision 2, about 9 MB. Its pack is 31600.

| Resources | What |
| --- | --- |
| 26000–26049 | Backgrounds, two for each of the 25 locations: 26000 + 2 × location + variant |
| 26100–26198 | Interface pictures, in gamelib's order |
| 26199 | The addon's spec, JSON |
| 26200–26624 | Portraits, 26200 + 5 × look + expression |
| 26800– | Parts no look draws |
| 26980–26991 | Music and sound, the last a copy for the story's selector 2 |
| 26992– | Relationship badges: heart, skull and smiley, whole and then broken |

```sh
python tools/translate/translate.py shs11 --art IT_480X800_JAR --english N73_JAR --sounds KG800_JAR --out OUT_DIR
```

### `shsbrew`: the BREW games

Required by every translated [BREW](BREW.md) story (126: the '08 Campaign, the Classic stories, the M.A.S.H. packs and Fall
'06), under either game's badge. It holds all their art and music, and the stories hold only their scripts. Revision 10,
about 18.8 MB; the stories ask for revision 7, since 8 to 10 only redraw pictures.

| Resources | What |
| --- | --- |
| 26000-26206 | Locations, three skies each: '08's, then '07's, then a sky alone (`brew.BACKGROUND_BASE`) |
| 26300-26364 | The catch game: frame, ring, digits, captions, then each item and player picture (`brew.CATCH_BASE`) |
| 26400 + picture | Time badge icons, BREW's small pictures 101-166 at the smartphone's size, 92 pixels (`EVENT_ICON_BASE`) |
| 26600 | A story's own icon: CS Idol's yawning face (`OWN_ICON_BASE`) |
| 26900-26914 | Music, tracks 8000-8014 |
| 26991 | The frame backdrop behind a pink box |
| 26992-26997 | Relationship icons: heart, skull and smiley, whole and then broken |
| 26998 | The spec: each story's looks, the Classic stories' own backgrounds, the catch game |
| 26999 | The frame backdrop |
| 27000- | Portraits, five faces each, 381 looks |
| 29000- | The Classic stories' own backgrounds, three skies each; '08's redraws of eleven of them 500 above |
| 36000- | The Java '08 Look: the demo's copy of a picture, 10000 above BREW's (frame, relationship icons, badge icons, catch game) |

Revisions: 2 the event icons; 3 the Java '08 Look; 4 the Classic stories' own backgrounds; 5 '08's redraws of them; 6 the
yawning face the catch games show; 7 that face as an event icon, and King of the Road's Michael centred; 8 the TV turned to face
the middle; 9 the Kid lowered onto the ring; 10 the badge icons at the smartphone's size.

```sh
python tools/translate/translate.py brew --base-08 GAME_08_FOLDER --base-07 MODULE_07_FOLDER --casts BREW_CASTS_JSON --out OUT_DIR
```

### `chslim`: Claire Hart (Slim)

Optional, for Cause of Death. Revision 1, about 21 MB.

CoD's portraits are 110 × 120, downscaled about 4.17 times from Claire Hart Classic's 458 × 500 originals, so this pack carries the
sharper art. CoD's episodes can't name an addon and a portrait's ID differs between episodes, so the player finds it by a hash of the
picture's bytes in the map at resource 28000 (`EpisodeResources._addon_portrait`, the profile's `PORTRAIT_ADDON`). The original's
size in play doesn't change, as `standard_portrait` keeps it at the size CoD's picture fills.

| Resources | What |
| --- | --- |
| 28000 | The map and contents, JSON |
| 28001 | The backdrop beside the frame |
| 28002, 28003 | Speech bubbles, held for Claire Hart's own episodes |
| 28004, 28005 | The Romic fonts, likewise |
| 28010 on | Portraits, each at 28010 + its place in the sorted list of all 835 |
| 29000, 29001 | Pictures made for CoD: Natara's shocked portrait with her tie, Kai's shocked portrait from SHS HD |

- **Map keys:** a hash for any resource with that picture, or `hash:resource` for one expression where CoD uses one picture for
  two. Kai's sad and shocked share a picture, so his shocked has its own entry.
- **Left out of the map:** Sophie. Claire Hart's version has pink hair, and her red hair is plot-relevant.
- **For Claire Hart's own episodes:** the pack also holds the rest of Troy Harris, Paul Clayton and Claire. With those, it covers
  every portrait in 57 of Claire Hart Classic's 266 episodes. It holds no Claire Hart backgrounds, so it isn't enough to translate
  those episodes by itself.
- **Stable IDs:** so that a complete Claire Hart addon can supersede it. Both hold each portrait under the same ID.

**Switches:** "HD Portraits in CoD" and "Backdrop" on the Add-Ons page, with the CH tag, shown when the addon is imported and on by default.
The backdrop takes the place of the SHS HD Backdrop in play and on CoD's menus.

```sh
python tools/translate/chslim.py --mirror CLAIRE_HART_DIR --pairs PAIRS.txt --catalog COD_CATALOG_PORTRAITS \
    --cod-library COD_LIBRARY --extras EXTRAS_DIR --out OUT_DIR
```

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
| MS3 Characters | X360 | X360 episodes |
| Hi-Res Portraits | NR | New Rules episodes |
| HD Portraits in CoD, Backdrop | CH | CoD with `chslim` imported |
| Use X360 Arena Skin | NR | New Rules episodes with `shsx360` imported; in play, also Use Translated Mini-Games on |
| Smartphone Music | SHS11 | SHS '11 episodes |
| Use Word Grid Skin | SHS11 | SHS '11 episodes, with HD's word game art |
| Java '08 Look | '08 | '08 BREW episodes, with an addon built with the Java demo |
| '08 Backgrounds | '07 | '07 BREW episodes |

On the main menus (owner, 2026-11-09), Add-Ons keeps only Use Translated Mini-Games, and the other switches are one page in,
**Per-Game Settings**; the pause menu lists them all on Add-Ons. Episodes made in the Creator count for a switch through their
primary add-on.

**Title Screen Music** (SHS's main menu only, under Add-Ons) chooses the tune the main menu plays, once, as its own: Default (the
game's own), Auto (that of the game last played, by its pack or a Creator episode's primary add-on), or a translated game's
title tune from its addon, offered when the library holds that addon (`TITLE_MUSIC` in the SHS profile):

| Choice | Addon | Resource | The game's |
| --- | --- | --- | --- |
| '07 / '08 | `shsbrew` | 26906 | Track 8006, the MIDI both games share |
| New Rules | `shsnr` | 26988 | Track 8 |
| X360 | `shsx360` (revision 15) | 26996 | `music/main_menu` |
| '11 | `shs11` | 26981 | Track 1, the main menu's one full tune |

## Data Management

**Options › Data Management › Add-Ons** lists a library's addons, and hides itself when there are none. From the chooser it's always there, and picks the game first when both have a library. Each addon has:

- **Details:** its ID, revision and size, and the episodes that need it. Reading those takes a moment the first time, as the manifest doesn't record them (`ContentLibrary.episode_requires`).
- **Export:** its file, under its own name, into the Exports folder.
- **Delete:** after a warning that counts the episodes needing it. Those show the "needs the addon" message until it's imported again, and their saves stay. It also lets go of a game left for the main menu, which could be drawing from it.

Elsewhere:

- **Add Episodes** takes addons, and says how many of each came. Episodes have versions of their own (resource 5, [SCHEMA.md](SCHEMA.md#episode-version-extension-shshd-runtime)): a newer one replaces an older copy, and the notice says how many were replaced, kept or left out.
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
