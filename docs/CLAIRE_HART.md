# Claire Hart Classic

*Claire Hart Classic* is Pogo's HTML5 hidden-object game (build 157): Claire Hart, who senses the memories objects hold, solves
cases with the things she finds. Its art overlaps Cause of Death's: 209 of CoD's 460 backgrounds are slices of its scenes,
and the two share characters (Mal and Natara visit; some of CoD's cast appear under other names). This fork translates its
cases into Cause of Death episodes on CoD's presentation. With the optional rounds add-on, Classic's own hidden-object rounds
are played for real. (`claire-hart` branch.)

None of the game's code runs here, and no file of it ships with the runtime: `tools/translate` reads the player's own copy of
the game.

**In the library:** 107 cases, pack 31500, entry *case × 10* (10–1070), tagged CH in their own category, Claire Hart. Each needs
the [`chc` add-on](ADDONS.md#chc-claire-hart-classic-claire-hart-branch) (455 MB); the
[`chcrounds` add-on](ADDONS.md#chcrounds-claire-hart-classic-rounds-claire-hart-branch) (1.1 GB) is optional. The tester zips
carry them: the cases with `chc` inside, and the rounds add-on on its own. Large add-ons stream to disk as they import.

| | |
| --- | --- |
| Cases | 107: Classic's 266 episodes, one entry per case, a title card naming each part (the case's title over the episode's). Numbered cases are "Case n", as Classic titled them; the 27 specials keep their titles |
| Shape | No branching, as in Classic: each episode is 6 chapters, a hidden-object round after each of the first 5 |
| Lines | 11,539, Classic's text as it is |
| Portraits | 835 heads in 185 looks (Normal, Angry, Happy, Sad, Surprised), drawn as CoD draws a look (look banks) |
| Scenes | 787, each Classic's 1024 × 768 picture without its hidden objects, darkened as Classic drew it |
| Story objects | 645 pictures, shown in a framed row along the dialogue box as Claire finds them (service 225) |
| Music | 33 tracks |
| Rounds | 1,330 over the 787 scenes (with `chcrounds`) |

## How a case plays

- **CoD's dialogue, in Claire Hart's dress** with **Claire Hart UI** on Auto (the default): Claire Hart's speech
  bubbles, Romic Bold in its dark red, the name on the bubble's tab, CoD's portrait ring, Continue as Classic's Play Now
  button. Its choices, prompts, windows, pause menu, text entry and portrait picker take Classic's panel and rows. The
  sequel's cases take Secret in the Shadows' own look on Auto. Choosing **Claire Hart Classic** or **Secret in the
  Shadows** puts that look on every CoD episode and the main menu's screens. Off is CoD's own look.
- **Narration** shows Claire's portrait (or the chapter's narrator's) beside a narrator box, as Classic does.
- **Scenes** are cut to a 3:4 slice that fills CoD's frame, panning with the speaker as CoD's scenes do. The slice of each scene
  is set in `chc`'s spec, and an episode may move it in its own resource 7 (`backdrop_slices.py`). Beside the frame on wide
  screens: Claire Hart's green.
- **Claire Hart 4:3:** where the window is at least 4:3 (a phone or iPad in landscape, a maximized or full-screen window), a
  case shows in a 4:3 frame instead. Each scene is whole, as Classic framed it, the dialogue is drawn 1.35x larger, and a round
  is Classic's own 800 × 600 layout. It switches as the window turns or resizes; a save's picture is still 3:4
  (`Desktop.wide_frame`, `frame_shape.has_wide_room`).
- **Rounds** (service 226, `claire_rounds.py`, `desktop_claire_round.py`): 12 objects from the scene's ~50, shown 6 at a time;
  the round's story objects (what the next chapter has Claire hold) are always among them. A find scores 100 × the combo (up to
  ×5). Then come the time and skill bonuses, half-stars per 600 points and the Level Summary. A misclick costs 100, and six in
  six seconds lock clicking for five. Zoom 1–2× and drag; at 3:4 and taller the scene fits the frame's height, with arrows at
  either edge. The hint is free. The four power-ups (Focus, Psychic Locator, Clairvoyance, Time Warp) follow **Power-Ups**:
  once each a round, unlimited (Clairvoyance still once), or off. The HUD is Classic's, its text in Classic's Romic at
  Classic's sizes; on tall phones its bars grow and its top bar keeps below the status bar. A save mid-round resumes it exactly.
  Without `chcrounds`, or with **Use Translated Mini-Games** off, a round is a narrated line: "Claire searches the Driveway and
  finds the Bracelet."
- **Ask to Skip Mini-Games** offers each round with its prompt in Claire Hart's dress.

## Settings

All carry the CH tag; on the main menu they're on Add-Ons › Per-Game Settings, in a case on the pause menu's Add-Ons.

| Setting | Does | Default |
| --- | --- | --- |
| Claire Hart UI | Auto, Off, Claire Hart Classic, Secret in the Shadows (above) | Auto |
| Power-Ups | Once Each Round, Unlimited, Off | Once Each Round |
| Round Style | Each Game's Own, Claire Hart Classic, Secret in the Shadows: which game's rules and round screen both games' rounds play under (shown with both rounds add-ons) | Each Game's Own |
| Dim Backdrops | The scenes darkened to 110/255, as Classic drew them | On |
| Claire Hart 4:3 | A 4:3 frame where the window has room (above) | On |
| HD Portraits in CoD | Claire Hart's sharper originals of CoD's own portraits | On |
| Backdrop | Beside CoD's frame: Off (SHS HD's collage or the dark fill), Claire Hart Classic's green, or Secret in the Shadows' violet (its episode select's, `ch2` 26999); each offered with its add-on. A saved On is Classic's (owner, 2026-11-25) | Claire Hart Classic |
| Use Translated Mini-Games | The real rounds (with `chcrounds`), else the narrated line | On |

Title Screen Music and Look (Add-Ons) offer each game's: Claire Hart Classic's 13-second main jingle, played once, and its
Play Now screen behind CoD's buttons; Secret in the Shadows' (`ch2` revision 3) the same jingle (the sequel ships the same
file, so it plays with the sequel alone too) and its episode select's violet backdrop under its loading picture's cast and
logo. Auto takes the game of the case last played.

## In the Creator

A Cause of Death project can take `chc` as its **primary add-on** (**Add-ons and settings…**). It then looks as a case does:
Claire Hart UI on Auto, the narrator's portrait, dimmed scenes, the green backdrop, the scenes' slices and
Claire Hart 4:3, and the title look and tune on Auto. **Browse library images** names `chc`'s pictures: each portrait by its
character and face, each scene, track and story object by name, and lists its 185 looks ("look Claire"), which a character
takes as its portrait by reference: the player reads its five faces from `chc` as a case's are. The **Hidden-object round (Claire Hart)** node plays one of
Classic's rounds from `chcrounds`, behind **Real minigames?**. See
[CREATOR.md](CREATOR.md#example-a-claire-hart-scene-in-a-cod-project) for a worked example.

## Building

`tools/translate/claire_hart.py` writes the cases (`build`) and `chc` (`addon`) from the game's files, and `rounds` writes
`chcrounds` (`claire_rounds_addon.py`); `claire_rounds_check.py` redraws every scene from the rounds add-on against Classic's
own. `ch_dialogue_skin.py` cuts Claire Hart UI's pieces into `chc`, and `title_looks.py` its title look. The commands and each
add-on's resources are in [ADDONS.md](ADDONS.md#chc-claire-hart-classic-claire-hart-branch).

The plans and the engine study (`CLAIRE_HART_PLAN.md`, `CLAIRE_HART_ENGINE.md`, `CLAIRE_HART_ROUNDS_PLAN.md`,
`CLAIRE_HART_SKIN_PLAN.md`, `CLAIRE_HART_43_PLAN.md`) are in `reference/Other Games/docs` beside the repository.

Sync Devices carries both add-ons (g54 to PC, 2026-11-24: about 3 minutes over Wi-Fi). A transfer cut short starts over
next time; the receiving library is unchanged until all of it has arrived.

**Checked 2026-11-24:**
- **Long lines:** every case was walked to its end, headless, at 3:4 and with a tall phone's extra rows, each line paged as
  the player pages it. The 255 distinct lines over 300 characters each run unbroken over 2–8 boxes; Case 76's 642
  characters take 8 at 3:4. No box is empty, and no text runs past its box.
- **Romic is Classic's font:** the game ships `Romic.ttf` and `Romic-Bold.ttf`. Its story and round screens' labels use
  `Romic.ttf`, and its dialogue box prefab draws with bitmap fonts made from Romic (`romicorange`, `romicwhite`, tinted by
  the box). The skin's dialogue is Romic Bold, since regular Romic lacks "&", "/" and most accented letters.

## Secret in the Shadows

*Claire Hart: Secret in the Shadows* is the sequel (Pogo HTML5, build 232), translated the same way into Cause of Death episodes
by `tools/translate/claire_hart_shadows.py`.

**In the library:** 51 cases, pack 31900, tagged CH2 in their own category, Claire Hart: Secret in the Shadows. Each needs the
[`ch2` add-on](ADDONS.md#ch2-claire-hart-secret-in-the-shadows-claire-hart-branch) (653 MB); the
[`ch2rounds` add-on](ADDONS.md#ch2rounds-claire-hart-secret-in-the-shadows-rounds-claire-hart-branch) (574 MB) is optional.
Neither needs Classic's. The tester zips carry them: the cases with `ch2` inside, and the rounds add-on on its own.

| | |
| --- | --- |
| Cases | 51 in 58 entries: 171 parts, entry *case × 10*. Seven cases are too long for one episode's script (its text limit), so they come in two halves, "(Part 1)" and "(Part 2)", the second entry numbered *case × 10* + its first part; the second half opens with the first's journal pages. They are 18 Lateral Libel, 21 Merry in Maui, 23 Overbaked, 28 End of Asbolus, 30 Best Intentions, 44 Silverhill Thriller and 50 The Art of Death (ROADMAP 3.35: rejoin them if the limit is raised). Case 31's three unlisted parts are included with their released titles, and case 45 takes its released title, *Lost Soul* |
| Lines | 13,500, each with its speaker's face on the game's stage |
| Portraits | 418 in 84 looks, cropped so the heads match Classic's |
| Scenes | 512, at full brightness, dimmed to 102/255 under Dim Backdrops |
| Story objects | 253 photos, one at a time for one line, framed as the game's, above the dialogue box at its right |
| Music | 37 tracks |
| Rounds | 855 over 512 scenes (with `ch2rounds`) |

**How a case plays:**
- **Secret in the Shadows UI** on Auto: the sequel's teal-framed dialogue box with the name in capitals on its tab, Roboto
  Condensed text, its purple CONTINUE, and its glass panels on the other screens.
- **The Case Journal** (pause menu): one page a part, its notes so far. A new entry shows its notice in a narration box with the
  game's cue.
- **Rounds** (`shadows_rounds.py`, `desktop_shadows_round.py`), on the sequel's own round screen: 12 objects, 6 listed at a
  time. Its extras over Classic:
  - **close-ups:** a hotspot opens a picture-in-picture with more objects (171 scenes);
  - **multi-part objects:** found piece by piece, when they're the story object;
  - **the Gold Key:** 500 points and its time recorded;
  - **the Psychic Sensor:** free, with a 60 s cooldown;
  - **spotlight rounds** (4);
  - **the combo** up to ×6, draining a tier at a time;
  - **"Not So Fast!"** for six taps in a second or nine in six.

  The summary counts the time, sensor, perfect and Gold Key bonuses and ten half-star checks, and ends with "Scene Cleared!".
  The Hint, Time Warp and Clairvoyance follow **Power-Ups**. How To Play is on the pause menu.
- **Round Style** (with both rounds add-ons) plays either game's rounds under the other's rules and screen. Under Classic's,
  a sequel scene offers only its ordinary objects (no close-ups, parts or key); under the sequel's, a Classic scene simply
  has none of the extras.

**Building:**

```sh
python tools/translate/claire_hart_shadows.py addon --mirror CH2_DIR --out OUT_DIR                                # ch2
python tools/translate/claire_hart_shadows.py build --mirror CH2_DIR --out OUT_DIR                                # the cases
python tools/translate/claire_hart_shadows.py rounds --mirror CH2_DIR --out OUT_DIR --story OUT_DIR/CH_Shadows.exp  # ch2rounds
```

The plans and the engine study (`CLAIRE_HART_SHADOWS_ENGINE.md`, `CLAIRE_HART_SHADOWS_ROUNDS_PLAN.md`, and
`CLAIRE_HART_PLAN.md`'s sequel stages) are in `reference/Other Games/docs` beside the repository.

**Checked 2026-11-25:**
- **Every case:** each of the 58 was played in a headless session and compared with an independent walk of the game's data
  (title cards, speakers, text, backdrops, music, photos, round lines). Each was also played with rounds off and on (all 855
  won), saved and loaded mid-part and mid-round, and skipped ahead to the end.
- **Every round of both games, under both round styles** (`tools/claire_round_audit/` beside the repository), at 3:4, 4:3
  and 9:20: every object can be seen and tapped clear of the HUD, every close-up opens, and every round plays to its summary.
- **The g54:** the sequel's round screen holds 57–60 fps idle, panning, in a close-up, under the spotlight and at the end.
- **Sync Devices** (g54 to a PC library, 2026-11-25): the whole Cause of Death library, both sequel add-ons with it, in
  about 5½ minutes over Wi-Fi. Every add-on's SHA-256 matched, all 58 entries arrived, the rounds spec and sprite packs
  read back, and nothing was left in the staging area.

## Not verified yet

- **The iPad:** cases, rounds, the skin and Claire Hart 4:3 are checked on the PC and the g54, not yet on iOS (ROADMAP 5.13).
  The same goes for the sequel's cases and rounds.
- **The sequel's rounds by hand:** its phone touch rule (while the sensor or a spotlight is on, a tap counts only near the
  ring or the light: `shadows_rounds.touch_counts`) and its sounds are checked in tests and headless runs, not yet by a
  player's finger and ear.
