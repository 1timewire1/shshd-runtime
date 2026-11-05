# The BREW games

*Surviving High School* '07 and '08 ran on Qualcomm BREW phones, built by Centerscore. They share one engine and are a calendar simulation: a story schedules events on dates and times, and a day planner runs them. This fork is translating their stories into ordinary episodes.

**State: in progress.** The translator and the `shsbrew` addon exist, and Quiz 1 plays through. Most stories still stop on a service with no handler yet (the catch game, for one), which is deliberate: a story that needs something new says so instead of being guessed at.

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
- **Time.** Each Campaign story runs one calendar event, so scheduling it just queues its script. The other stories' calendar isn't built yet.
- **Numbers.** BREW's numbered values work as SHS's do, except 407: BREW's runs 0 to 100 and SHS's counts icons, so BREW's value stays under its own key and 407 follows it. Below 20, 30 and 40 show 3, 2 and 1 skulls. From 40, 66 and 76 show 1, 2 and 3 smileys, or hearts for the current partner.
- **Portraits.** A look is a 23-entry list that scripts build and change. Its entries live in saved numbers with a running hash, and each change looks the hash up in the story's table of looks, then points the character at that look's faces. Entry 2 picks the box's colour, as BREW's pink one does.
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
- **Music** is rendered through Java's built-in synthesizer, as for New Rules and '11.

## Checking

The BREW games' behaviour comes from a local copy of the third-party Tardy-Slip player, checked against the native modules. The real game also runs under the Melange wrapper on an Android emulator, which can settle how something looks, but it's silent. A translated story should say the same lines in the same order on the same choices.
