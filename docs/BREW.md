# The BREW games

*Surviving High School* '07 and '08 ran on Qualcomm BREW phones, built by Centerscore. They share one engine and are a calendar simulation: a story schedules events on dates and times, and a day planner runs them. This fork is translating their stories into ordinary episodes.

**State: in progress.** The translator and the `shsbrew` addon exist, and seven stories play through: Quizzes 1-3, 2.2, 2.5, 3.3 and 9.4. Scripted runs of them match Tardy-Slip's lines, speakers and menus on eight answer paths each. Most other stories still stop on a service with no handler yet (the catch game, for one), which is deliberate: a story that needs something new says so instead of being guessed at.

None of the games' code runs here, and no file of them ships with the runtime: `tools/translate` reads the player's own copies.

## Building

```sh
python tools/translate/translate.py brew --base-08 GAME_08_FOLDER --base-07 MODULE_07_FOLDER --casts BREW_CASTS_JSON --out OUT_DIR
python tools/translate/translate.py brew --story FILE --addon shsbrew.exp --out OUT_DIR
```

The first writes the addon, and the second a story that reads it. `brew_casts.json` is the BREW portrait catalogue's list of each story's looks.

## How a story is translated

BREW's machine is SHS's, in KiWi's older header, so a story keeps its scripts, with every host call rewritten for SHS's services (`HANDLERS` in `brew.py`).

- **Scripts.** A story's 25001 stays where it is, and its story script, 26000, becomes 25002, since 26000 and up are SHS's episode bank.
- **Choices.** A quiz has no player character, so it asks in the narrator's gold under `Make your choice!`, as New Rules' Train That Brain! does.
- **Word games.** BREW's timed menus come from one shared routine: several rounds of a spinning cursor over words with scores, usually two good and two bad, returning a total the story tests. They play as service 71, with BREW's own title and instructions, and its result is scaled onto the best total, so that a full score is every round's best. A single round is a question, and it's the smartphone's `Think fast!`, which takes a random option when time runs out.
- **Name entry** (29: title, default, 0) is the smartphone's own text input (17). Its answer becomes the event's text (`$BREWEVENT`), which BREW's scripts read straight after with 7 and store as `$USR`, `$CAT_NAME` or `$ANNA`.
- **The catch game.** BREW's one minigame, in three kinds (19 orbit, 20 angled, 21 sideways), plays as service 221 with "Use Translated Mini-Games" on, ported from the module's own code (`brew_catch.py`) and drawn with its art at 3 times (`desktop_brew_catch.py`). Its page shows first, as in BREW. The orbit moves once a tick, as in BREW, at the only real phone's 50 ms (its `xlarge.prf`): a lap takes 2 s. With the switch off it's a word game under the same page, less the catch game's points (`45 pts to pass.`) and with `Think fast!`, the smartphone's kind of banner, for BREW's generic title `Instructions` (`CATCH_POINTS`, `CATCH_GENERIC_TITLE`); BREW's own banners, such as `Bowl right!`, stay. Two words for each picture (`CATCH_WORDS`, named by eye), good or bad by the picture's value. That result out of the smartphone's pass mark is that share of the target: every band the 181 call sites test can be reached that way.
- **6.1 Surviving College** picks its ending from 6 points up or below 5, so exactly 5 has none and the story stops, in BREW too. Here 5 takes the lower ending (owner's choice, `STORY_FIXES`).
- **Brackets.** BREW puts narration and thoughts alike in brackets. Narration loses them, and a character's bracketed line becomes SHS's thought. Game words lose their brackets and quotes.
- **Time.** Each Campaign story runs one calendar event, so scheduling it just queues its script. The other stories' calendar isn't built yet.
- **Numbers.** BREW's numbered values work as SHS's do, except 407: BREW's runs 0 to 100 and SHS's counts icons, so BREW's value stays under its own key and 407 follows it. Below 20, 30 and 40 show 3, 2 and 1 skulls. From 40, 66 and 76 show 1, 2 and 3 smileys, or hearts for the current partner.
- **Portraits.** A look is a 23-entry list that scripts build and change. Its entries live in saved numbers with a running hash. When a character is next shown, a changed hash is looked up in the story's table of looks, and the character is pointed at that look's faces. Setups are still big, as a story can dress 27 characters: `Session.advance`'s safety limit went from 100,000 instructions to a million for it. Entry 2 picks the box's colour, as BREW's pink one does.
- **Scenes.** Scenes stack: 13 opens one and 18 closes the top one, so what's underneath comes back. The stack lives in saved numbers.
- **Names.** BREW's stories have their own names table (`TRANSLATED_NAME_SETS`), as its phones' `prefs.sav` was its own, so `$USR` starts as BREW's Jenny, not the smartphone's name.
- **Narration.** A character named Event is the narrator, as on the smartphone. The real game shows it with an `EVENT` plate and an empty photo frame.
- **Title cards.** A story's card shows the first picture the story itself does, found by playing it that far when translating, as scripts choose pictures through helpers.

## Art and music

All of it is in the addon, and stories hold only their scripts ([ADDONS.md](ADDONS.md#shsbrew-the-brew-games)).

- **Locations** are 240 × 80 strips over a sky drawn in code, so each is rendered at each of its three skies, at six times size with no smoothing.
- **Portraits** are paper dolls, rendered at 3.5 times size to 252 × 294, within twice the player's portrait mask. Anything larger is squeezed into the mask's shape by the player, out of proportion. They're made at seven times with no smoothing, then halved, so every art pixel is the same size. Each is raised 7 art pixels from the picture's bottom, which the ring hides, so the whole bust shows.
- **Relationship icons** are BREW's own, on the smartphone's places and motion (`TRANSLATED_BADGE_ART`). BREW's never break, so a broken one is the whole one parted down its middle.
- **The frame** around the strip is BREW's dialogue panel, tiled at the strip's density, with its yellow bar above and below (`TRANSLATED_FRAME_BACKDROP`). As in the real game, the panel turns pink behind a pink box and back for anyone else (`TRANSLATED_THEME_BACKDROP`).
- **Music** is rendered through Java's built-in synthesizer, as for New Rules and '11. The game plays its 15 cues all the same way; sorted by ear, 8001, 8004, 8008, 8009, 8011 and 8012 play as sound effects, so they leave any music playing, and the rest as music. 8011 and 8001 are the correct and incorrect chimes, which Answer hints read as outcomes (`shs/profile.py` `TRANSLATED_FEEDBACK_MUSIC`).

## Checking

The BREW games' behaviour comes from a local copy of the third-party Tardy-Slip player, checked against the native modules. The real game also runs under the Melange wrapper on an Android emulator, which can settle how something looks, but it's silent. A translated story should say the same lines in the same order on the same choices.
