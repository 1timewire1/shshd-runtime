# Cause of Death release dates

External research, not decompilation, like [EPISODE_RELEASE_DATES.md](EPISODE_RELEASE_DATES.md) for SHS: none of it
is recoverable from the IPA's code. Compiled 2026-10-08 for the HD player's Now Airing / On Demand lists.

## Sources

1. **The developers' Facebook page** (facebook.com/CauseofDeathEA), the primary source. The owner exported all 556
   posts (2010-12-17 to 2014-09-08) with exact timestamps. Times are converted to US Pacific (EA Mobile's time zone);
   many posts fall in the late evening, which would otherwise land on the next day in UTC.
2. **[The CoD wiki](https://causeofdeath.fandom.com/wiki/Volume_1:_The_Maskmaker)**, per-volume chapter tables, used
   as a cross-check. Its dates are the Facebook Now Airing dates for Volumes 2-3 and the On Demand dates from Volume
   4 on (e.g. 4.2 = 2011-04-26, 4.3 = 2011-04-29), and agree exactly with the posts within each stage.
3. **The 1.4.7 store listing** (`Documents/mtxprods`, `releaseDate` per product). These are upload dates, usually
   days and sometimes weeks *before* the announced release (15.2: store 2013-09-13, On Demand 2013-10-01), so they
   are a fallback only (used twice: the Volume 8 set and the first Secret Files, neither announced).

## Two release stages

Every chapter shipped twice: **On Demand** (paid, first) and **Now Airing** (free, normally a week later; two weeks
or more in the biweekly era). Premium Content packs were On Demand only. Both dates are kept; which one the picker
shows as "Airdate" is a presentation decision.

## Schedule history (from the posts)

- **2010-12-17:** free edition launches (Volume 1 plus Volume 2, Chapter 1 in Now Airing); new chapters on Fridays.
  The early posts name the On Demand chapter only inside the Now Airing post ("Also get this week's Chapter on
  Demand: ..."), which starts with Volume 2, Chapter 5; Chapters 2-4 have no On Demand date.
- **2011-06-02:** new episodes end for the paid edition (Cause of Death PAID, `com.ea.causeofdeath`).
- **Mid-2011:** releases move to Thursdays (announced Fridays), then to **Mondays from 2011-07-18** after repeated
  On Demand failures; the free **Now Airing Special** short story (`Now_Airing_Special.exp`) aired 2011-07-14 to
  2011-07-18 as thanks.
- **2013-09-20:** weekly releases become **biweekly**.
- **2014-04-21:** releases move to **Wednesdays**, alongside Surviving High School.
- **2014-07-16:** series finale (16.7 Sunset) On Demand; Now Airing 2014-07-23.
- **2014-09-08:** the app is pulled from the App Store ("EVERYTHING 99¢" sale from 2014-09-02).

## Method and gaps

Release posts are split into stage clauses ("NOW AIRING", "ON DEMAND", "Now available ON DEMAND", "Also get this
week's Chapter on Demand", "Then download this week's On Demand episode") and matched against the store's own chapter
titles (`cod_options_episodes.sav`) plus the specials. Every match was reviewed; corrections (false matches inside
descriptions, re-releases, combo packs, delayed releases) are listed in the Notes column. The extractor, the store
table and the full post list are kept outside the repo in `reference/cod-airdates/`.

Never announced, so left blank: Now Airing for 6.5, the Volume 9 Interlude, 9.5, 9.6, 14.7, 14.8, 15.1, 15.2, 15.4,
16.1, 16.3 and City of Love 1-2; On Demand for the Volume 16 Interlude. "Inferred" in a note marks the few dates
taken from a post that says a release happened without naming it, or from the weekly cadence.

## Table

Sorted by first release.

| First release | Episode | On Demand | Now Airing | Notes |
|---|---|---|---|---|
| 2010-12-17 | Volume 2 - Chapter One: Tough Love | - | 2010-12-17 | Launch week (wiki); re-aired in Now Airing 2014-08-06 as a series promo. |
| 2010-12-17 | Volume One: The Maskmaker (base game) | - | 2010-12-17 | Base game; the free edition launched 2010-12-17 ("now available FOR FREE"). |
| 2010-12-24 | Volume 2 - Chapter Two: Head Case | - | 2010-12-24 |  |
| 2010-12-31 | Volume 2 - Chapter Three: Sins of the Fathers | - | 2010-12-31 |  |
| 2011-01-07 | Volume 2 - Chapter Four: Catching Fire | - | 2011-01-07 |  |
| 2011-01-07 | Volume 2 - Chapter Five: Missing Persons, Part 1 | 2011-01-07 | 2011-01-14 |  |
| 2011-01-14 | Volume 2 - Chapter Six: Missing Persons, Part 2 | 2011-01-14 | 2011-01-21 |  |
| 2011-01-21 | Volume 2 - Chapter Seven: Old Wounds | 2011-01-21 | 2011-01-28 |  |
| 2011-01-28 | Volume 2 - Chapter Eight: Revelations | 2011-01-28 | 2011-02-04 |  |
| 2011-02-04 | Volume 3 - Chapter One: Prey | 2011-02-04 | 2011-02-12 |  |
| 2011-02-12 | Volume 3 - Chapter Two: Broken Hearted, Part 1 | 2011-02-12 | 2011-02-18 |  |
| 2011-02-18 | Volume 3 - Chapter Three: Broken Hearted, Part 2 | 2011-02-18 | 2011-02-25 |  |
| 2011-02-25 | Volume 3 - Chapter Four: Hunter, Hunted | 2011-02-25 | 2011-03-04 |  |
| 2011-03-04 | Volume 3 - Chapter Five: Lights, Camera, Murder, Part 1 | 2011-03-04 | 2011-03-11 |  |
| 2011-03-11 | Volume 3 - Chapter Six: Lights, Camera, Murder, Part 2 | 2011-03-11 | 2011-03-18 |  |
| 2011-03-11 | Your Case: The Missing Child | 2011-03-11 | - | Premium Content 2011-03-11; re-offered On Demand at a low price 2013-08-26. |
| 2011-03-18 | Volume 3 - Chapter Seven: Savage | 2011-03-18 | 2011-03-25 |  |
| 2011-03-25 | Volume 3 - Chapter Eight: The Wild Hunt | 2011-03-25 | 2011-04-01 |  |
| 2011-04-01 | Side Stories: Detective Kalaba, Part 1 | 2011-04-01 | 2011-04-08 |  |
| 2011-04-08 | Side Stories: Detective Kalaba, Part 2 | 2011-04-08 | 2011-04-15 |  |
| 2011-04-15 | Volume 4 - Chapter One: Zero Hour | 2011-04-15 | 2011-04-22 |  |
| 2011-04-26 | Volume 4 - Chapter Two: Blood Relations, Part 1 | 2011-04-26 | 2011-04-29 |  |
| 2011-04-29 | Volume 4 - Chapter Three: Blood Relations, Part 2 | 2011-04-29 | 2011-05-06 |  |
| 2011-05-06 | Volume 4 - Chapter Four: Coded Messages | 2011-05-06 | 2011-05-13 |  |
| 2011-05-13 | Volume 4 - Chapter Five: Games We Play, Part 1 | 2011-05-13 | 2011-05-20 |  |
| 2011-05-20 | Volume 4 - Chapter Six: Games We Play, Part 2 | 2011-05-20 | 2011-05-27 |  |
| 2011-05-27 | Volume 4 - Chapter Seven: Zero Sum Game | 2011-05-27 | 2011-06-03 |  |
| 2011-06-03 | Volume 4 - Chapter Eight: Zero Consequences | 2011-06-03 | 2011-06-10 |  |
| 2011-06-10 | Side Stories: Amy's Case, Part 1 | 2011-06-10 | 2011-06-17 |  |
| 2011-06-13 | Secret Files | 2011-06-13 | - | Never announced; date from the 1.4.7 store listing (upload date). Added 2026-10-14 for the picker. |
| 2011-06-17 | Side Stories: Amy's Case, Part 2 | 2011-06-17 | 2011-06-23 |  |
| 2011-06-23 | Volume 5 - Chapter One: Dread Silence | 2011-06-23 | 2011-06-30 |  |
| 2011-06-30 | Volume 5 - Chapter Two: The Perilous Fight | 2011-06-30 | 2011-07-07 | Inferred: Thursday release (2011-07-07 post); that week only On Demand failed. |
| 2011-07-12 | Volume 5 - Chapter Three: The Shore Dimly Seen | 2011-07-12 | 2011-07-18 | 2011-07-14 post: "On Monday, we will release Chapter 3 ... for Now Airing". |
| 2011-07-14 | Now Airing Special (free short story) | - | 2011-07-14 | Free short story in Now Airing until 2011-07-18 (Now_Airing_Special.exp). |
| 2011-07-18 | Volume 5 - Chapter Four: The Gloom of the Grave | 2011-07-18 | 2011-07-25 | Now Airing inferred (weekly cadence; not announced). |
| 2011-07-25 | Volume 5 - Chapter Five: The Root Of All Evil, Part 1 | 2011-07-25 | 2011-08-01 |  |
| 2011-08-01 | Volume 5 - Chapter Six: The Root Of All Evil, Part 2 | 2011-08-01 | 2011-08-08 |  |
| 2011-08-08 | Volume 5 - Chapter Seven: Trafficked | 2011-08-08 | 2011-08-15 |  |
| 2011-08-15 | Volume 5 - Chapter Eight: Mallory | 2011-08-15 | 2011-08-22 |  |
| 2011-08-22 | Side Stories: Fallon And Yeong, Part 1 | 2011-08-22 | 2011-08-29 |  |
| 2011-08-29 | Side Stories: Fallon And Yeong, Part 2 | 2011-08-29 | 2011-09-05 | Inferred from the unannounced 2011-09-05 release. |
| 2011-09-05 | Volume 6 - Chapter One: Opening Moves | 2011-09-05 | 2011-09-12 | 2011-09-05 post: "Episodes have been released", announcement never followed. |
| 2011-09-12 | Volume 6 - Chapter Two: Under My Skin, Part 1 | 2011-09-12 | 2011-09-19 |  |
| 2011-09-19 | Volume 6 - Chapter Three: Under My Skin, Part 2 | 2011-09-19 | 2011-09-26 |  |
| 2011-09-19 | Love and Bullets (short story collection) | 2011-09-19 | - | Announced 2011-09-19 as a "Special Short Story Collection" (store: Love and Bullets). |
| 2011-09-26 | Volume 6 - Chapter Four: Gambit | 2011-09-26 | 2011-10-03 |  |
| 2011-10-03 | Volume 6 - Chapter Five: Breaking Point, Part 1 | 2011-10-03 | - |  |
| 2011-10-11 | Volume 6 - Chapter Six: Breaking Point, Part 2 | 2011-10-11 | 2011-10-17 |  |
| 2011-10-17 | Volume 6 - Chapter Seven: Zugzwang | 2011-10-17 | 2011-10-24 |  |
| 2011-10-21 | What Happened To Colt, Part 2 | 2011-10-21 | - | SHS crossover; Part 1 in Surviving High School. |
| 2011-10-24 | Volume 6 - Chapter Eight: Endgame | 2011-10-24 | 2011-10-31 |  |
| 2011-10-31 | Halloween Special: Dead Man Walking, Part 1 | 2011-10-31 | 2011-11-07 |  |
| 2011-11-07 | Halloween Special: Dead Man Walking, Part 2 | 2011-11-07 | 2011-11-14 |  |
| 2011-11-14 | Volume 7 - Chapter One: Bad Romance | 2011-11-14 | 2011-11-21 |  |
| 2011-11-21 | Volume 7 - Chapter Two: In Vino Veritas, Part 1 | 2011-11-21 | 2011-11-28 |  |
| 2011-11-28 | Volume 7 - Chapter Three: In Vino Veritas, Part 2 | 2011-11-28 | 2011-12-05 |  |
| 2011-12-05 | Volume 7 - Chapter Four: Split | 2011-12-05 | 2011-12-12 |  |
| 2011-12-12 | Volume 7 - Chapter Five: Domestic Disturbance, Part 1 | 2011-12-12 | 2011-12-19 |  |
| 2011-12-19 | Volume 7 - Chapter Six: Domestic Disturbance, Part 2 | 2011-12-19 | 2012-01-03 |  |
| 2012-01-03 | A Cause of Death Christmas | 2012-01-03 | 2012-01-09 |  |
| 2012-01-09 | Volume 7 - Chapter Seven: Killer Alibi | 2012-01-09 | 2012-01-17 |  |
| 2012-01-17 | Volume 7 - Chapter Eight: Final Flight | 2012-01-17 | 2012-01-23 |  |
| 2012-01-23 | Side Stories: Greene Zone, Part 1 | 2012-01-23 | 2012-01-30 |  |
| 2012-01-30 | Side Stories: Greene Zone, Part 2 | 2012-01-30 | 2012-02-06 |  |
| 2012-02-06 | Valentine Short Stories | 2012-02-06 | 2012-02-13 |  |
| 2012-02-13 | Volume 8 - Chapter One: Tendrils | 2012-02-13 | 2012-02-21 |  |
| 2012-02-21 | Volume 8 - Chapter Two: Crimes of Passion, Part 1 | 2012-02-21 | 2012-02-27 |  |
| 2012-02-27 | Volume 8 - Chapter Three: Crimes of Passion, Part 2 | 2012-02-27 | 2012-03-05 |  |
| 2012-03-05 | Volume 8 - Chapter Four: Rising Tides, Part 1 | 2012-03-05 | 2012-03-12 |  |
| 2012-03-05 | First Date, First Kiss, First Kill | 2012-03-05 | - |  |
| 2012-03-12 | Volume 8 - Chapter Five: Rising Tides, Part 2 | 2012-03-12 | 2012-03-19 |  |
| 2012-03-19 | Volume 8 - Chapter Six: A Day in the Life | 2012-03-19 | 2012-03-26 |  |
| 2012-03-26 | Volume 8 - Chapter Seven: In Roaring He Shall Rise | 2012-03-26 | 2012-04-02 |  |
| 2012-04-02 | Volume 8 - Chapter Eight: And On The Surface Die | 2012-04-02 | 2012-04-09 |  |
| 2012-04-09 | Side Stories: In The Cards, Part 1 | 2012-04-09 | 2012-04-16 |  |
| 2012-04-16 | Side Stories: In The Cards, Part 2 | 2012-04-16 | 2012-04-23 |  |
| 2012-04-23 | Volume 9 - Chapter One: Walk the Wire | 2012-04-23 | 2012-04-30 |  |
| 2012-04-30 | Volume 9 - Chapter Two: Fire and Brimstone, Part 1 | 2012-04-30 | 2012-05-07 |  |
| 2012-05-07 | Volume 9 - Chapter Three: Fire and Brimstone, Part 2 | 2012-05-07 | 2012-05-14 |  |
| 2012-05-14 | Volume 9 - Chapter Four: Sparks | 2012-05-14 | 2012-05-21 |  |
| 2012-05-21 | Volume 9 - Volume 9 Interlude | 2012-05-21 | - |  |
| 2012-05-29 | Volume 9 - Chapter Five: Kings of Las Vegas, Part 1 | 2012-05-29 | - |  |
| 2012-06-04 | Volume 9 - Chapter Six: Kings of Las Vegas, Part 2 | 2012-06-04 | - |  |
| 2012-06-11 | Volume 9 - Chapter Seven: Shock And Awe, Part 1 | 2012-06-11 | 2012-06-18 |  |
| 2012-06-18 | Volume 9 - Chapter Eight: Shock And Awe, Part 2 | 2012-06-18 | 2012-06-25 |  |
| 2012-06-25 | Buried Secrets, Buried Lives | 2012-06-25 | - |  |
| 2012-06-25 | Side Stories: Fourth of July Special, Part 1 | 2012-06-25 | 2012-07-02 |  |
| 2012-07-02 | Side Stories: Fourth of July Special, Part 2 | 2012-07-02 | 2012-07-09 |  |
| 2012-07-09 | Volume 10 - Chapter One: Fear and Loathing | 2012-07-09 | 2012-07-16 |  |
| 2012-07-16 | Volume 10 - Chapter Two: Truth or Dare, Part 1 | 2012-07-16 | 2012-07-23 |  |
| 2012-07-23 | Volume 10 - Chapter Three: Truth or Dare, Part 2 | 2012-07-23 | 2012-07-30 |  |
| 2012-07-30 | Volume 10 - Chapter Four: Nightmare | 2012-07-30 | 2012-08-06 |  |
| 2012-08-06 | Volume 10 - Volume 10 Interlude | 2012-08-06 | 2012-08-13 |  |
| 2012-08-13 | Volume 10 - Chapter Five: In Fidelity, Part 1 | 2012-08-13 | 2012-08-20 |  |
| 2012-08-20 | Volume 10 - Chapter Six: In Fidelity, Part 2 | 2012-08-20 | 2012-08-27 |  |
| 2012-08-20 | Life Lessons, Deadly Desires | 2012-08-20 | - |  |
| 2012-08-27 | Volume 10 - Chapter Seven: Love And Madness | 2012-08-27 | 2012-09-03 |  |
| 2012-09-03 | Volume 10 - Chapter Eight: Death Do Us Part | 2012-09-03 | 2012-09-10 |  |
| 2012-09-10 | Side Stories: Far From Home, Part 1 | 2012-09-10 | 2012-09-18 |  |
| 2012-09-17 | Side Stories: Far From Home, Part 2 | 2012-09-17 | 2012-09-24 |  |
| 2012-09-24 | Volume 11 - Chapter One: Best Served Cold | 2012-09-24 | 2012-10-08 | Now Airing failed 2012-10-01..05; aired as the Chapters 1 & 2 Combo Pack. |
| 2012-10-01 | Volume 11 - Chapter Two: Black Magic, Part 1 | 2012-10-01 | 2012-10-08 |  |
| 2012-10-08 | Volume 11 - Chapter Three: Black Magic, Part 2 | 2012-10-08 | 2012-10-15 |  |
| 2012-10-15 | Volume 11 - Chapter Four: Putting The Pieces Together | 2012-10-15 | 2012-10-22 |  |
| 2012-10-22 | Volume 11 - Chapter Eleven: Interlude | 2012-10-22 | 2012-10-29 |  |
| 2012-10-29 | Volume 11 - Chapter Five: Tangled Webs | 2012-10-29 | 2012-11-05 |  |
| 2012-10-30 | Halloween Special: Undying Love | 2012-10-30 | - |  |
| 2012-11-05 | Volume 11 - Chapter Six: Wolf At The Gates | 2012-11-05 | 2012-11-12 |  |
| 2012-11-12 | Volume 11 - Chapter Seven: Love and War, Part 1 | 2012-11-12 | 2012-11-19 |  |
| 2012-11-19 | Volume 11 - Chapter Eight: Love and War, Part 2 | 2012-11-19 | 2012-11-26 |  |
| 2012-11-26 | Side Stories: Peacemaker, Part 1 | 2012-11-26 | 2012-12-03 |  |
| 2012-12-03 | Side Stories: Peacemaker, Part 2 | 2012-12-03 | 2012-12-10 |  |
| 2012-12-10 | Magic School: Book 1 | 2012-12-10 | 2012-12-17 | Now Airing 2012-12-17 was a "Magic School: Book 1 Preview"; the full book was On Demand only. |
| 2012-12-17 | Volume 12 - Chapter One: Monsters Among Us | 2012-12-17 | 2012-12-24 |  |
| 2012-12-24 | Holiday Interlude: A Fallon Family Christmas | 2012-12-24 | 2012-12-31 |  |
| 2012-12-31 | Volume 12 - Chapter Two: Bloodlines, Part 1 | 2012-12-31 | 2013-01-07 |  |
| 2013-01-07 | Volume 12 - Chapter Three: Bloodlines, Part 2 | 2013-01-07 | 2013-01-14 |  |
| 2013-01-14 | Volume 12 - Chapter Four: Special Friend | 2013-01-14 | 2013-01-21 |  |
| 2013-01-21 | Volume 12 - Chapter Five: The Old College Try, Part 1 | 2013-01-21 | 2013-01-28 |  |
| 2013-01-28 | Volume 12 - Chapter Six: The Old College Try, Part 2 | 2013-01-28 | 2013-02-04 |  |
| 2013-02-04 | Volume 12 - Chapter Seven: Nothing To Fear | 2013-02-04 | 2013-02-11 |  |
| 2013-02-11 | Volume 12 - Chapter Eight: Out Of The Shadows | 2013-02-11 | 2013-02-18 |  |
| 2013-02-18 | Side Stories: Kai Hard, Part 1 | 2013-02-18 | 2013-02-25 |  |
| 2013-02-25 | Side Stories: Kai Hard, Part 2 | 2013-02-25 | 2013-03-04 |  |
| 2013-03-04 | Volume 13 - Chapter One: The Creeping Darkness | 2013-03-04 | 2013-03-11 |  |
| 2013-03-11 | Volume 13 - Chapter Two: Blood and Water | 2013-03-11 | 2013-03-18 |  |
| 2013-03-18 | Volume 13 - Chapter Three: The Boys in Blue | 2013-03-18 | 2013-03-25 |  |
| 2013-03-25 | Volume 13 - Chapter Four: Predator Unseen | 2013-03-25 | 2013-04-01 |  |
| 2013-04-01 | Volume 13 - Interlude: The Break-Up | 2013-04-01 | - |  |
| 2013-04-02 | Volume 13 - Interlude: Perfect Getaway | 2013-04-02 | 2013-04-08 |  |
| 2013-04-08 | Volume 13 - Chapter Five: Safety in Numbers | 2013-04-08 | 2013-04-15 |  |
| 2013-04-15 | Volume 13 - Chapter Six: Ghosts Of The Past | 2013-04-15 | 2013-04-22 |  |
| 2013-04-22 | Volume 13 - Chapter Seven: Spider To The Fly | 2013-04-22 | 2013-04-29 |  |
| 2013-04-29 | Volume 13 - Chapter Eight: Brood | 2013-04-29 | 2013-05-06 |  |
| 2013-05-06 | Side Stories: Seth, Lies, and Videotape, Part 1 | 2013-05-06 | 2013-05-13 |  |
| 2013-05-13 | Side Stories: Seth, Lies, and Videotape, Part 2 | 2013-05-13 | 2013-05-20 |  |
| 2013-05-20 | Volume 14 - Chapter One: Joint Forces | 2013-05-20 | 2013-05-28 |  |
| 2013-05-27 | Volume 14 - Chapter Two: Accelerant | 2013-05-27 | 2013-06-04 |  |
| 2013-06-03 | Volume 14 - Chapter Three: Catch and Release | 2013-06-03 | 2013-06-11 |  |
| 2013-06-10 | Volume 14 - Chapter Four: One Step Ahead | 2013-06-10 | 2013-06-18 |  |
| 2013-06-17 | Volume 14 - Interlude: Madness In Orbit | 2013-06-17 | 2013-06-25 |  |
| 2013-06-24 | Volume 14 - Chapter Five: Second Chances | 2013-06-24 | 2013-07-09 |  |
| 2013-07-08 | Volume 14 - Short Story: Retreats and Advances | 2013-07-08 | 2013-07-15 |  |
| 2013-07-15 | Volume 14 - Chapter Six: The Greater Good | 2013-07-15 | 2013-07-24 |  |
| 2013-07-22 | Volume 14 - Chapter Seven: Prodigal Son | 2013-07-22 | - |  |
| 2013-07-29 | Volume 14 - Chapter Eight: New World Order, Part 1 | 2013-07-29 | - |  |
| 2013-08-05 | Volume 14 - Chapter Nine: New World Order, Part 2 | 2013-08-05 | 2013-08-16 |  |
| 2013-08-15 | Side Stories: Forks in the Road, Part 1 | 2013-08-15 | 2013-08-26 | Now Airing as a Parts 1 & 2 bundle. |
| 2013-08-19 | Side Stories: Forks in the Road, Part 2 | 2013-08-19 | 2013-08-26 | Now Airing as a Parts 1 & 2 bundle. |
| 2013-09-03 | Secret Files 02 | 2013-09-03 | 2013-09-10 |  |
| 2013-09-10 | Volume 15 - Chapter One: Across The Pond | 2013-09-10 | - |  |
| 2013-10-01 | Volume 15 - Chapter Two: The Harrowing Truth | 2013-10-01 | - |  |
| 2013-10-14 | Volume 15 - Chapter Three: Mixed Messages | 2013-10-14 | 2013-10-29 |  |
| 2013-10-28 | Volume 15 - Interlude: The Days We Remember | 2013-10-28 | 2013-11-11 |  |
| 2013-11-11 | Volume 15 - Chapter Four: Pretenders | 2013-11-11 | - |  |
| 2013-11-25 | Volume 15 - Chapter Five: Hanging by a Thread | 2013-11-25 | 2013-12-10 |  |
| 2013-12-09 | Volume 15 - Chapter Six: The End of the Rope | 2013-12-09 | 2013-12-24 |  |
| 2013-12-23 | Holiday Stories: Past and Presents | 2013-12-23 | 2014-01-13 | 2014-01-13 post: "the Holiday Stories pack is available free on Now Airing right now". |
| 2014-01-13 | Volume 15 - Chapter Seven: High Crimes | 2014-01-13 | 2014-02-05 | On Demand delayed by a server mix-up (2014-01-13); Now Airing 2014-02-05. |
| 2014-02-06 | Volume 15 - Chapter Eight: Capital Punishment | 2014-02-06 | 2014-02-24 |  |
| 2014-02-24 | Side Stories: City of Love, Part 1 | 2014-02-24 | - |  |
| 2014-03-11 | Side Stories: City of Love, Part 2 | 2014-03-11 | - |  |
| 2014-03-24 | Volume 16 - Chapter One: Haunted | 2014-03-24 | - |  |
| 2014-04-08 | Volume 16 - Chapter Two: Metamorphosis | 2014-04-08 | 2014-04-23 |  |
| 2014-04-23 | Volume 16 - Chapter Three: Unfinished Business | 2014-04-23 | - |  |
| 2014-06-04 | Volume 16 - Interlude: Promises and Compromises | - | 2014-06-04 |  |
| 2014-06-04 | Volume 16 - Chapter Four: Sunrise | 2014-06-04 | 2014-06-20 |  |
| 2014-06-20 | Volume 16 - Chapter Five: The Red Room | 2014-06-20 | 2014-07-04 |  |
| 2014-07-04 | Volume 16 - Chapter Six: True Faces | 2014-07-04 | 2014-07-16 |  |
| 2014-07-16 | Volume 16 - Chapter Seven: Sunset | 2014-07-16 | 2014-07-23 |  |

| Released | Volume set (On Demand bundle) | Notes |
|---|---|---|
| 2011-04-01 | Volume 2 set |  |
| 2011-05-06 | Volume 3 set |  |
| 2011-06-30 | Volume 4 set |  |
| 2011-09-19 | Volume 5 set |  |
| 2011-12-19 | Volume 6 set |  |
| 2012-03-05 | Volume 7 set |  |
| 2012-04-17 | Volume 8 set | Not announced; date from the 1.4.7 store listing (upload date). |
| 2012-08-27 | Volume 9 set |  |
| 2012-10-22 | Volume 10 set |  |
| 2013-02-04 | Volume 11 set |  |
| 2013-04-03 | Volume 12 set |  |
| 2013-06-21 | Volume 13 set |  |
| 2013-10-30 | Volume 14 set |  |
| 2014-03-05 | Volume 15 set |  |
| 2014-07-24 | Volume 16 set |  |
