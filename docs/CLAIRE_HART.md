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

- **CoD's dialogue, in Claire Hart's dress** with **Claire Hart UI** on Claire Hart Cases (the default): Claire Hart's speech
  bubbles, Romic Bold in its dark red, the name on the bubble's tab, CoD's portrait ring, Continue as Classic's Play Now
  button. Its choices, prompts, windows, pause menu, text entry and portrait picker take Classic's panel and rows. With
  **Everywhere**, every CoD episode and the main menu's screens do too. Off is CoD's own look.
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
| Claire Hart UI | Off, Claire Hart Cases, Everywhere (above) | Claire Hart Cases |
| Power-Ups | Once Each Round, Unlimited, Off | Once Each Round |
| Dim Backdrops | The scenes darkened to 110/255, as Classic drew them | On |
| Claire Hart 4:3 | A 4:3 frame where the window has room (above) | On |
| HD Portraits in CoD, Backdrop | Claire Hart's sharper originals of CoD's own portraits; its green beside CoD's frame | On |
| Use Translated Mini-Games | The real rounds (with `chcrounds`), else the narrated line | On |

Title Screen Music and Look (Add-Ons) offer Claire Hart's: its 13-second main jingle, played once, and its Play Now screen
behind CoD's buttons. Auto takes them after a case.

## In the Creator

A Cause of Death project can take `chc` as its **primary add-on** (**Add-ons and settings…**). It then looks as a case does:
Claire Hart UI with Claire Hart Cases, the narrator's portrait, dimmed scenes, the green backdrop, the scenes' slices and
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

## Not verified yet

- **The iPad:** cases, rounds, the skin and Claire Hart 4:3 are checked on the PC and the g54, not yet on iOS (ROADMAP 5.13).
