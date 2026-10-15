# Episode release dates

External research, not decompilation: none of this is embedded in the APK/IPA or recoverable from the binary, so
it carries a different kind of evidence than the rest of `docs/`. Compiled to drive a chronological "Now Airing"
list (grouped by year, earliest first) as a cross-check on the library's own completeness, separate from the
episode picker's native category grouping (`EPISODE_CATALOG.md`).

## 9 episodes have no separate picker entry -- but their content is already in the library

Checking the assembled dates against [centerscorefan.netlify.app](https://centerscorefan.netlify.app/)'s own
canonical episode order (see below) turned up nine consecutive Troublemakers Season 3 (and one Season 2) titles
with no matching library title at all: in canonical order, between `Getaway` and `1: The Kimi Dates`, `Christmas
Stories`, `The Date`, `Pyramid Scheme`, `The Secret Life of Owen Harris`, `Exposed`, `Spencer Betrayed`, `The
Winter Dance`, `Heart to Hart`, `Hart Attack`. Dates for all nine, mostly from @SHSTeam's own tweets:

| Date | Episode | Source |
|---|---|---|
| 2014-01-18 | Christmas Stories | @SHSTeam (X) -- "Christmas Stories is now our Weekly Free Episode! ..." |
| 2014-01-29 | The Date | @SHSTeam (X) -- "the first episode of Season 3, The Date is out!" |
| 2014-02-07 | Pyramid Scheme | @SHSTeam (X) -- "...our newest episode Pyramid Scheme is now available..." |
| 2014-02-21 | The Secret Life of Owen Harris | @SHSTeam (X) -- "Now Airing as our Weekly Free Episode is The Secret Life of Owen Harris! ..." |
| 2014-02-27 | Exposed | @SHSTeam (X) -- "This week's Now Airing episode is Exposed! ..." |
| 2014-03-06 | Spencer Betrayed | @SHSTeam (X) -- "This week's On Demand episode is Spencer Betrayed! ..." |
| 2014-03-14 | The Winter Dance | @SHSTeam (X) -- "The new episode this week is The Winter Dance! ..." |
| 2014-03-20 | Heart to Hart | Wikia era page -- Troublemakers (no @SHSTeam tweet found; see the gap noted below) |
| 2014-03-27 | Hart Attack | Wikia era page -- Troublemakers (no @SHSTeam tweet found; see the gap noted below) |

@SHSTeam's own account confirms the first seven directly. The last two have no tweet in the owner's export at
all -- @SHSTeam's own timeline goes quiet between March 24 and April 10, 2014 (visible as a real gap in the
main-tweets export, not a search miss: the surrounding weeks are otherwise tweeted weekly without exception),
so `Heart to Hart` and `Hart Attack` keep their Wikia-sourced dates, unconfirmed by the primary source.

**Not actually a missing-content gap.** Three independent community-collected episode archives ("2nd Set",
"3rd Set") were checked for a standalone EXP matching any of these nine titles; none exists in any of them. But
the library already has `Troublemakers_Season_2.exp` (13 scripts, covers `Christmas Stories`) and
`Troublemakers_Season_3.exp` (17 scripts, covers the other eight) -- confirmed byte-for-byte identical to the
copies in both newer archives, so there was nothing new to import. These two files are consolidated season
bundles, the same shape as `Season 1: A New Start` (which likewise bundles five same-launch sub-episodes under
one title): the real app evidently rolled these eight-ish weeks out individually (matching @SHSTeam's weekly
"Now Airing"/"On Demand" language above), but what survives as a standalone file today is the later, consolidated
season pack, not the original per-week releases. The owner's call: leave the bundle as one dated entry, consistent
with how every other season bundle in this library already works, rather than trying to split it into individually
dated sub-episodes. These nine titles will not appear as their own rows in the "Now Airing" chronological list;
their content is already playable, just under the season's own single title and date.

## Sources, in priority order

1. **[@SHSTeam on X](https://x.com/SHSTeam)** -- the developers' own account, the only primary source. The
   owner exported their own archive (`reference/X csvs/main tweets.csv`, 527 tweets, every regular tweet the
   account sent; a second `replies (incomplete).csv` export was checked too but added nothing not already in
   the main export) rather than this being bulk-scraped live. Matched the same way as the other sources (each
   library title searched for as a normalized substring across every tweet), but only trusted as an override of
   an existing Wikia/GameFAQs date when the two are within 30 days of each other -- a tweet mentioning an
   episode isn't necessarily a release announcement (retrospective polls, "Limited Time" re-releases of old
   content, and "throwback" call-outs all turned up in the search and would have silently corrupted well-established
   dates otherwise; see "Known exceptions" below for what this caught). Applied to 79 episodes this way; also
   the source for 7 of the 9 missing episodes above, found by searching the full tweet text rather than the
   narrower pattern used for the automated pass, since their names were short/generic enough to risk false
   positives in the bulk search. X's own posting was inconsistent -- per the owner's own contact, the developers
   only ever posted *consistently* on a Facebook page, now deleted; X got whatever they cross-posted there, which
   explains why confirmed tweets cover barely over a quarter of the library (79 of 285) rather than acting as a
   real primary source throughout.
2. **[Wikia's List of Episodes](https://shs.fandom.com/wiki/List_of_Episodes)**, plus five era-specific pages with
   deeper season-by-season detail than the combined list: [The Classics](https://shs.fandom.com/wiki/List_of_Episodes:_The_Classics),
   [The New Girl](https://shs.fandom.com/wiki/List_of_Episodes:_The_New_Girl),
   [A New Start](https://shs.fandom.com/wiki/List_of_Episodes:_A_New_Start),
   [Magic School](https://shs.fandom.com/wiki/List_of_Episodes:_Magic_School),
   [Troublemakers](https://shs.fandom.com/wiki/List_of_Episodes:_Troublemakers),
   [Battle of the Schools](https://shs.fandom.com/wiki/List_of_Episodes:_Battle_Of_The_Schools). Originally ranked
   below GameFAQs here, flagged only as "sources from a since-dead Facebook page, explicitly contested" -- the
   same dead Facebook page X turned out to be a thin cross-post of. The owner's own contact (connected to the
   original community) has since confirmed that page as the developers' real, consistently-updated announcement
   channel, with Wikia's numbers compiled directly from it at the time, which promotes it above GameFAQs below.
   The contact separately flagged that some Wikia dates land about a week off depending on whether an editor
   recorded an episode's earlier "On Demand" (paid) availability or its later "Now Airing" (free) one -- both are
   real native release stages for the same episode (@SHSTeam's own tweets use both terms, see above), not a
   dating error, and reprocessing GameFAQs-sourced entries against Wikia bore this out directly: 150 of 165
   plain GameFAQs dates had a matching Wikia date, the overwhelming majority 1-8 days apart and almost all within
   two weeks -- consistent with a systematic release-stage offset, not a source disagreeing by chance.
3. **[GameFAQs walkthrough by dmikester](https://gamefaqs.gamespot.com/iphone/979746-surviving-high-school/faqs/58319)**
   (version 16.6, updated through July 2014) -- its own version-history changelog reads as a de facto release
   log ("Walkthrough for X" entries added roughly weekly, matching the game's own release cadence). Originally
   ranked above Wikia and used as the primary bulk source for everything X didn't confirm; demoted below Wikia
   once the Facebook-sourcing finding above came in, and 150 of its 165 plain entries were superseded by a
   matching Wikia date as a result (see "Reprocessed..." below) -- it remains the only source for an episode
   Wikia never dated at all (31 titles, mostly ones GameFAQs' own changelog never gives Wikia anything to match:
   season-bundle packs borrowing a date by inference, the vote packages, and the five Holiday Tales sub-stories).

[centerscorefan.netlify.app](https://centerscorefan.netlify.app/) supplies a canonical episode *order* with no
dates (273 entries for this game). Used two ways: as the source of the library-completeness finding above, and
as a systematic consistency check on every assigned date (walking the order and flagging any date that jumps
backward by more than 45 days against the running maximum) -- this caught three real matching bugs during
compilation, described below, that a spot check would have missed, and was re-run clean (zero flagged) after
the GameFAQs/Wikia reprocessing below.

## Methodology

- Matched against the library's own English episode titles (`record['titles'][0]`) by normalizing both sides
  (strip numeric/era prefixes, a leading `Special:`, leading articles, punctuation, spelled-out "Part One" ->
  "Part 1") and searching for known titles as substrings of each changelog/table/tweet entry.
- On a conflict between the two written sources (Wikia, GameFAQs), the higher-priority one wins silently
  (Wikia over GameFAQs), per the owner's call -- no per-conflict log is kept, except where noted below as an
  explicit exception. X's own dates are reconciled differently (a 30-day tolerance check against whichever of
  the two already has a date), for the reason given above.
- An episode with no date from any of these sources is left out of the table entirely; the "Now Airing" feature's
  own handling of that case (year-only grouping when a year can be inferred, otherwise omitted) is a UI decision
  made separately from this research.
- 12 library titles are vote-pack / non-episode content (`Sam`/`Sara`/`Taylor`/`Zoe` x `Large`/`Medium`/`Small`
  `Vote Package`, and `Specials`) and were excluded rather than treated as missing episodes: `Sam Large Vote
  Package`, `Sam Medium Vote Package`, `Sam Small Vote Package`, `Sara Large Vote Package`, `Sara Medium Vote
  Package`, `Sara Small Vote Package`, `Taylor Large Vote Package`, `Taylor Small Vote Package`, `Zoe Large Vote
  Package`, `Zoe Medium Vote Package`, `Zoe Small Vote Package`, `Specials`.
- A season-bundle record (a whole season sold/imported as one pack, e.g. `A New Start 2: Howard's Return`) takes
  its season's own start date from the relevant Wikia era page, since neither source dates a bundle as its own
  release.
- Season 1 of "A New Start" (`Season 1: A New Start`) is one library record for five same-day sub-episodes
  (`The First Day`, `High Spirits`, `Making A Name`, `The Dinner and the Party`, `The Big Game`); dated to that
  shared day.

### Three real matching bugs the order-consistency check caught

A short, reused title can legitimately name two different episodes released years apart (the library carries no
pack/season metadata this research draws on, only titles), and simple substring matching can silently pick the
wrong one:

- **`17: Halloween`** (a Classics-era episode, March 2010) was initially dated October 16, 2010 -- the date of
  the unrelated spin-off `Football: Halloween` -- because an over-eager normalization step stripped `Football:`
  as if it were a generic prefix, making the two titles collide. Fixed by only ever stripping a leading
  `Special:` this way (checked safe: this library's own `Special: X` / bare `X` pairs, e.g. `Special: Getting
  Over Howard` / `Getting Over Howard`, are confirmed to be the same episode under two title variants, unlike
  `Football:`, `Troublemakers:`, etc., which mark a genuinely different spin-off).
- **`Best Party Ever`** (the bare title, the Megapack bundle) and **`4: Prom`** (the Troublemakers series finale)
  each collided with an earlier, differently-numbered episode that happens to share the same bare name once
  numeric prefixes are stripped (`12: Best Party Ever`, a 2010 Classics episode; an unrelated 5/29/2011 GameFAQs
  mention of "Prom"). Both fixed with the correct source identified from context (Wikia's own Premium Content
  table for the Megapack; GameFAQs' own later 4/30/2014 changelog entry for the Troublemakers finale).

These three were caught only because the consistency check exists; any other short/reused title colliding the
same way would look identical to a correct entry without it.

### Reprocessed: Wikia promoted over GameFAQs

Done after the Facebook-sourcing finding above came in (see "Sources, in priority order"), reusing the exact
title-matching code the original merge used, nothing about the matching itself changed: every title whose date
came from plain GameFAQs (165 of them) was checked again for a Wikia date, and 150 had one. Nine titles were
excluded automatically rather than by rule -- they have no Wikia counterpart to match against at all (the twelve
vote packages and five Holiday Tales sub-stories, each dated by inference rather than a direct title mention; a
handful of season-bundle packs borrowing their season's own start date the same way) -- so they simply kept their
existing GameFAQs date, nothing to supersede it. One title, `4: Prom`, was excluded by hand: its GameFAQs date
exists specifically to resolve a collision *within* GameFAQs' own data (an unrelated 2011 "Prom" mention, see
above), not a GameFAQs-vs-Wikia disagreement, and Wikia's own date for it already agrees (April 30, 2014) --
nothing to supersede there either.

Of the 150 actual swaps, the gaps were overwhelmingly small and one-directional: Wikia's date almost always lands
*later* than GameFAQs' by roughly a week, matching the On Demand/Now Airing release-stage distinction above almost
exactly (a handful ran longer, up to two weeks, still consistent with the same explanation rather than a
mismatch). Three swapped dates crossed a calendar year boundary and moved to a different year's table section
below (`07: Surviving Europe`, `08: From Europe With Love`: 2009 -> 2010; `60: New Year's Date`: 2010 -> 2011).
Re-ran the centerscorefan order-consistency check against the reprocessed dataset afterward: still zero flagged
entries, so the swap introduced no new ordering problems.

### Other known exceptions to the priority rule, and remaining caveats

- **`Football Star`** uses Wikia's iOS release date (November 9, 2009) rather than GameFAQs' changelog date
  (November 22, 2009): the GameFAQs date is when the guide was *written*, and the guide's very first update
  (0.5) retroactively covered four already-released episodes at once, so it doesn't mean much for this one
  specifically -- Wikia gives an actual asserted release date instead. (X was also checked for this one and
  rejected: the only tweet mentioning it is a generic 2012 "game day" greeting, not a release announcement --
  exactly the retrospective-mention risk the 30-day tolerance exists to catch.)
- **`Summer Fling`** and **`As Time Goes By`** are marked "approximate" rather than given the same confidence as
  the rest of the table: they're two of those same four episodes from GameFAQs' first bundled update, and Wikia
  explicitly lists their release date as unknown ("N/A") rather than offering a conflicting one. The GameFAQs
  write-up date is kept as the best available guess, not presented as a confirmed date.
- **`Battle of the Schools: Girl`**: Wikia's own two pages disagree with each other (combined list says June 11,
  2014, same day as `Guy`; the era-specific page says June 20). The era-specific page was preferred as more
  likely carefully maintained, but this is a real inconsistency in the source, not a resolution backed by a
  higher-priority source.
- **`Special Novel Chapter`** and **`Peter's Story`** matched by content, not by title substring: the library's
  own names for these don't share words with Wikia's (`Novel Bonus Chapter: The San Francisco Date Debacle`;
  `Peter's Challenge`), so they needed manual identification rather than the usual automated match.
- **The Mistletoe Match**, **New Year's Connection**, **A Tom Prince New Year's Eve**, **Officer Monte's New
  Year's Bash**, and **Christmas in Helzeroth** don't appear as their own dated entries anywhere: GameFAQs'
  walkthrough body text (not the changelog) identifies them as five sub-stories bundled into the single
  "Holiday Tales" release, so all five share that release's date (January 12, 2012).
- 18 titles had an X mention that the 30-day tolerance rejected as too far from the existing date to trust --
  all of them, on inspection, genuinely are "Limited Time" re-releases, anniversary polls, or classic-content
  throwbacks rather than the original release, confirming the tolerance check is catching what it was built to
  catch rather than discarding real corrections. Full list kept in the compiled research, not reproduced here.

## @SHSTeam's own tweets reveal a real season-renumbering: Wikia's later-season numbers run one higher than the developers' own

Found while dating the five season-bundle packs below: @SHSTeam's tweets consistently call the arc starting with
`300's A Crowd` "Season 10" (`"Now Airing for iPhone/iPad/iPod touch players! Season 10, Episode 1: 300's A
Crowd"`, February 17, 2012, and seven more weekly tweets through Season 10 Episode 8), the arc starting with
`Photo Op` "Season 11", and the arc containing `Date Auction`/`The New Head Cheerleader` "Season 12" -- all
primary-source, from the developers themselves. Wikia's own `List of Episodes: The New Girl` page calls those
same three arcs "Season 11: The Spartan Games", "Season 12: The Election", and "Season 13: Howard's Goodbye"
respectively -- one higher across the board. This isn't a typo on Wikia's part; its own trivia note says seasons
were relabeled at least once historically ("Seasons 2-3 of The New Girl were originally considered to be the
third season of The Classics... This was later changed after the release of Season 6: Prom"), so the page most
likely reflects a later community renumbering that never propagated back to what the game itself called these
seasons at the time. This also independently confirms the library's own existing HD catalog data is right where
it disagreed with three community-collected Standard catalogs (see "Howard's Goodbye" below) -- it already used
this same, real, developer-numbering scheme.

## Five newly-imported season bundles, and the vote packages, dated

Five season-bundle packs the owner separately imported into the library (see `legacy/findings.md`, "Three
community episode archives...") dated the same way the other bundles above are -- matching the date already
established for that season's own first individual episode:

| Bundle | Date | Matches |
|---|---|---|
| `Set 9: Colt, Reformed` | 2011-12-16 | `1: Christmas Break` |
| `Set 10: The Spartan Games` | 2012-02-17 | `1: 300's A Crowd` (@SHSTeam confirms "Season 10, Episode 1" directly) |
| `Set 11: The Election` | 2012-04-20 | `1: Photo Op` (@SHSTeam confirms "Season 11, Episode 1" directly) |
| `Set 12: Howard's Goodbye` | 2012-06-07 | `1: The New Head Cheerleader` |
| `A New Start 5: Spring Break Romeo` | 2013-02-28 | `1: The Play` |

**`Howard's Goodbye`'s own categorization**, flagged separately in conversation: the library's HD-side picker
already files it under "Season 12" (matching the siblings above), disagreeing with three independent
community-collected Standard-release catalogs, which all say "The New Girl" (too generic to be useful, though
not exactly wrong). The @SHSTeam tweets above settle this in the HD catalog's favor -- "Season 12" is the real,
developer-confirmed label, not a coincidence or an HD-side quirk. Still no code change made; whether to adjust
`episode_category()`'s own cross-release priority to prefer this kind of match generally, versus leaving this one
record as-is, remains the owner's call from the earlier conversation.

**The twelve character vote packages** (`Sam`/`Sara`/`Taylor`/`Zoe` x `Small`/`Medium`/`Large`) all take the same
inferred date, `Homecoming Princesses`' own (September 2, 2011) -- not independently confirmed anywhere, but
GameFAQs' walkthrough text ties them directly to that specific episode ("I refuse to spend fifteen dollars on a
Large Vote Pack just to have access to short stories", written about `Homecoming Princesses`), and that episode's
own plot -- four girls (Taylor, Zoe, Sam, Sara) each get a named short story inside the free episode -- matches
the four vote-package characters exactly. No dedicated Wikia page or @SHSTeam tweet exists for the vote packages
themselves; this is the best available evidence, not a confirmed date. Kept separate from `Story Vote Ticket`
(already dated above), which is a real, separately-confirmed and unrelated voting mechanic (choosing Magic
School's genre, per that story's own Wikia page).

Twelfth: the library's own `Specials` title is one of these, not a twelfth kind of content. It's the literal
internal title of `Homecoming_Taylor_2.exp` (pack 1000, episode 2) -- the exact same file-numbering slot as
`Homecoming_Sam_2.exp`, `Homecoming_Sara_2.exp`, and `Homecoming_Zoe_2.exp`, all three titled "X Medium Vote
Package". Taylor's own Medium tier shipped with a generic placeholder title baked into the EXP itself rather than
"Taylor Medium Vote Package" -- a real authoring artifact in the source file, not a picker bug. Dated the same as
its eleven siblings above.

**Every one of the library's 285 distinct English episode titles now has a date** by this research (checked by
diffing the full current title list against the compiled dataset after the additions above) -- nothing left
unaccounted for as of this pass.

## Dates, earliest first

### 2009

| Date | Episode | Source |
|---|---|---|
| 2009-11-09 | Football Star | Wikia -- combined list; iOS release date, more specific than the GameFAQs write-up date this would otherwise use |
| 2009-11-16 | 01: Making Some Dough | Wikia combined list |
| 2009-11-22 | 01: Summer Fling | GameFAQs (approximate; see note below) |
| 2009-11-22 | 02: As Time Goes By | GameFAQs (approximate; see note below) |
| 2009-11-23 | 02: A Float Is Born | Wikia combined list |
| 2009-11-30 | 03: Assembling the Team | Wikia combined list |
| 2009-12-07 | 04: The Great Float Caper | Wikia combined list |
| 2009-12-14 | 05: Break A Leg | Wikia combined list |
| 2009-12-21 | 06: The Outcast | Wikia combined list |

### 2010

| Date | Episode | Source |
|---|---|---|
| 2010-01-04 | 07: Surviving Europe | Wikia combined list |
| 2010-01-11 | 08: From Europe With Love | Wikia combined list |
| 2010-01-19 | 09: Skate Video | Wikia combined list |
| 2010-01-19 | 10: The Wrong Side of Town | Wikia combined list |
| 2010-01-25 | 11: The Concert | Wikia combined list |
| 2010-02-02 | 12: Best Party Ever | Wikia combined list |
| 2010-02-08 | 13: Local Ghosts | Wikia combined list |
| 2010-02-15 | 14: Spud the Stud | Wikia combined list |
| 2010-02-23 | 15: Lost Recipe | Wikia combined list |
| 2010-03-01 | 16: Secret Ingredient | Wikia combined list |
| 2010-03-08 | 17: Halloween | Wikia combined list |
| 2010-03-08 | Homecoming Queen | Wikia combined list |
| 2010-03-15 | 18: Writer's Block | Wikia combined list |
| 2010-03-22 | 19: Flex Games | Wikia combined list |
| 2010-03-29 | 20: Party Fowl | Wikia combined list |
| 2010-04-05 | 21: Road Rules | Wikia combined list |
| 2010-04-12 | 22: Winter Queen | Wikia combined list |
| 2010-04-19 | 23: Quest Rewards | Wikia combined list |
| 2010-04-26 | 24: The Holiday Party | Wikia combined list |
| 2010-05-03 | 25: Tom Prince's Carol | Wikia combined list |
| 2010-05-03 | Football: Big Man On Campus | Wikia combined list |
| 2010-05-11 | 26: New Year's Kiss | @SHSTeam (X) -- tweet: 'For this week, iPhone/iPod touch users can play 2 new episodes to play' |
| 2010-05-11 | Hector's Guide To Girls | @SHSTeam (X) -- tweet: 'For this week, iPhone/iPod touch users can play 2 new episodes to play' |
| 2010-05-17 | 27: Prank Wars | Wikia combined list |
| 2010-05-17 | 28: Boot Camp Breakout | GameFAQs changelog |
| 2010-05-18 | Love Potion Fun Pack | Wikia combined list |
| 2010-06-01 | 29: Guys Versus Wild | Wikia combined list |
| 2010-06-07 | 30: Proof | Wikia combined list |
| 2010-06-14 | 31: The Crosstown Races, Part One | Wikia combined list |
| 2010-06-21 | 32: The Crosstown Races, Part Two | Wikia combined list |
| 2010-06-28 | 33: The Break Up | Wikia combined list |
| 2010-07-06 | 34: Andy Cannelloni, P.I. | Wikia combined list |
| 2010-07-12 | 35: Fair Catch | Wikia combined list |
| 2010-07-19 | 36: The Cheer-Lationship | Wikia combined list |
| 2010-07-26 | 37: The Prince Plot, Part One | Wikia combined list |
| 2010-08-02 | 38: The Prince Plot Part Two | Wikia combined list |
| 2010-08-09 | 39: Prom Night | Wikia combined list |
| 2010-08-16 | 40: The Graduation List | Wikia combined list |
| 2010-08-20 | The New Girl | @SHSTeam (X) -- tweet: "New SHS Mega Pack! Get 'The New Girl' now and help Zoe become a cheerl" |
| 2010-08-23 | 41: When Howard Met... | Wikia combined list |
| 2010-08-27 | 42: Spirit Week | Wikia combined list |
| 2010-09-03 | 43: Love and War | Wikia combined list |
| 2010-09-10 | 44: Green With Kenji | Wikia combined list |
| 2010-09-17 | 45: Foreign Exchange | @SHSTeam (X) -- tweet: "Kay: Dad wouldn't make us French toast... Kel: So we signed us up for " |
| 2010-09-19 | 46: Dance Dance Revelation | GameFAQs changelog |
| 2010-10-01 | 47: Party Crashers | Wikia combined list |
| 2010-10-08 | 48: Sam's Formation, Part One | Wikia combined list |
| 2010-10-15 | 49: Sam's Formation, Part Two | Wikia combined list |
| 2010-10-16 | Football: Halloween | @SHSTeam (X) -- tweet: 'Trick or treat! iPhone players can get the Football: Halloween episode' |
| 2010-10-22 | 50: Surviving Pet Society | Wikia combined list |
| 2010-10-29 | 51: Halloween: In Colt Blood | Wikia combined list |
| 2010-11-05 | 52: Quiz-aster | Wikia combined list |
| 2010-11-12 | 53: Twinstigators | Wikia combined list |
| 2010-11-15 | Pranksgiving | Wikia combined list |
| 2010-11-19 | 54: Long Distance Relation-Trip | Wikia combined list |
| 2010-11-24 | 55: Denni and Raven's Thanksgiving | Wikia combined list |
| 2010-12-03 | 56: The Truth About Colt, Part One | Wikia combined list |
| 2010-12-07 | Holiday Cheer | Wikia combined list |
| 2010-12-10 | 57: The Truth About Colt, Part Two | Wikia combined list |
| 2010-12-17 | 58: A Very Tom Prince Holiday | Wikia combined list |
| 2010-12-25 | 59: Bringing Home Christmas | Wikia combined list |

### 2011

| Date | Episode | Source |
|---|---|---|
| 2011-01-02 | 60: New Year's Date | Wikia combined list |
| 2011-01-07 | 61: School Ski Trip | Wikia combined list |
| 2011-01-14 | 62: The Reluctant Matchmaker | Wikia combined list |
| 2011-01-27 | 63: How to Fight Nerdy | Wikia combined list |
| 2011-01-28 | 65: Valentine's Dates | GameFAQs changelog |
| 2011-02-03 | 64: The Kim-Provised First Date | Wikia combined list |
| 2011-02-04 | Football: Valentine's Carnival | Wikia combined list |
| 2011-02-11 | 66: Queen of Hearts | Wikia combined list |
| 2011-02-18 | 67: Basketball Woes | Wikia combined list |
| 2011-02-25 | 68: Spring Break Up | Wikia combined list |
| 2011-02-28 | Football: King of Spring Break | Wikia combined list |
| 2011-03-04 | 69: Wilson High's Demise | Wikia combined list |
| 2011-03-11 | 70: The New Regime | Wikia combined list |
| 2011-03-18 | 71: Officer Monte's Ridealong | Wikia combined list |
| 2011-03-25 | 72: Trapped in the Classroom | Wikia combined list |
| 2011-04-01 | 73: School Rebellion | Wikia combined list |
| 2011-04-08 | 74: Good Chemistry | Wikia combined list |
| 2011-04-15 | 75: Anger Management | Wikia combined list |
| 2011-04-22 | 76: Sink or Swim | Wikia combined list |
| 2011-04-29 | 77: Tough Guy on Campus | Wikia combined list |
| 2011-05-06 | 78: Justin for President | Wikia combined list |
| 2011-05-13 | 79: Return of the Astrid | Wikia combined list |
| 2011-05-20 | 80: Erik's Date | Wikia combined list |
| 2011-05-21 | 81: Breaking News | GameFAQs changelog |
| 2011-05-24 | Best Party Ever | Wikia era page -- The New Girl (Premium Content table; Megapack bundle, iOS/Android date -- the GameFAQs entry it collided with is the earlier, differently-numbered Classics episode) |
| 2011-06-03 | 82: Broken Prom-ises, Part 1 | Wikia combined list |
| 2011-06-10 | 83: Broken Prom-ises, Part Two | Wikia combined list |
| 2011-06-17 | 84: Spike Must Graduate | Wikia combined list |
| 2011-06-24 | 85: Howard's Summer Bummer | Wikia combined list |
| 2011-07-01 | Fourth of July Flashback | Wikia combined list |
| 2011-07-08 | 1: Freedom Festival | Wikia combined list |
| 2011-07-15 | 2: Girls Night In | Wikia combined list |
| 2011-07-26 | 3: Camping Trip Visions | @SHSTeam (X) -- tweet: 'Hey SHS Fans,  Right now, Episode 3: Camping Trip Visions should be th' |
| 2011-07-26 | 5: French Kiss, Paris Part 2 | @SHSTeam (X) -- tweet: 'French Kiss, Paris Part 2:  Who is Zoe talking about?! Find out in the' |
| 2011-07-29 | 4: French Connection, Paris Part 1 | Wikia combined list |
| 2011-08-02 | 6: French Finale, Paris Part 3 | @SHSTeam (X) -- tweet: 'French Finale, Paris Part 3:  Looks like Zoe is more than surprised to' |
| 2011-08-16 | 7: A College Date | @SHSTeam (X) -- tweet: "A College Date:  What's Brendan talking about? Why is college life so " |
| 2011-08-17 | Gossip Files | @SHSTeam (X) -- tweet: "Hey SHS Fans!!!  Check out Taylor's Gossip Files to learn juicy secret" |
| 2011-08-20 | 8: Hector Versus Hector | GameFAQs changelog |
| 2011-09-02 | 1: Back to School | Wikia combined list |
| 2011-09-02 | Sam Large Vote Package | GameFAQs, inferred -- same release as Homecoming Princesses; GameFAQs' own walkthrough text ties a 'Large Vote Pack' purchase directly to that episode's bonus short stories, not independently dated |
| 2011-09-02 | Sam Medium Vote Package | GameFAQs, inferred -- same release as Homecoming Princesses; GameFAQs' own walkthrough text ties a 'Large Vote Pack' purchase directly to that episode's bonus short stories, not independently dated |
| 2011-09-02 | Sam Small Vote Package | GameFAQs, inferred -- same release as Homecoming Princesses; GameFAQs' own walkthrough text ties a 'Large Vote Pack' purchase directly to that episode's bonus short stories, not independently dated |
| 2011-09-02 | Sara Large Vote Package | GameFAQs, inferred -- same release as Homecoming Princesses; GameFAQs' own walkthrough text ties a 'Large Vote Pack' purchase directly to that episode's bonus short stories, not independently dated |
| 2011-09-02 | Sara Medium Vote Package | GameFAQs, inferred -- same release as Homecoming Princesses; GameFAQs' own walkthrough text ties a 'Large Vote Pack' purchase directly to that episode's bonus short stories, not independently dated |
| 2011-09-02 | Sara Small Vote Package | GameFAQs, inferred -- same release as Homecoming Princesses; GameFAQs' own walkthrough text ties a 'Large Vote Pack' purchase directly to that episode's bonus short stories, not independently dated |
| 2011-09-02 | Specials | GameFAQs, inferred -- same release as Homecoming Princesses; this record is Homecoming_Taylor_2.exp, the same file-numbering slot as the other three characters' own Medium vote packages, so almost certainly Taylor's Medium tier shipped under a generic internal title |
| 2011-09-02 | Taylor Large Vote Package | GameFAQs, inferred -- same release as Homecoming Princesses; GameFAQs' own walkthrough text ties a 'Large Vote Pack' purchase directly to that episode's bonus short stories, not independently dated |
| 2011-09-02 | Taylor Small Vote Package | GameFAQs, inferred -- same release as Homecoming Princesses; GameFAQs' own walkthrough text ties a 'Large Vote Pack' purchase directly to that episode's bonus short stories, not independently dated |
| 2011-09-02 | Zoe Large Vote Package | GameFAQs, inferred -- same release as Homecoming Princesses; GameFAQs' own walkthrough text ties a 'Large Vote Pack' purchase directly to that episode's bonus short stories, not independently dated |
| 2011-09-02 | Zoe Medium Vote Package | GameFAQs, inferred -- same release as Homecoming Princesses; GameFAQs' own walkthrough text ties a 'Large Vote Pack' purchase directly to that episode's bonus short stories, not independently dated |
| 2011-09-02 | Zoe Small Vote Package | GameFAQs, inferred -- same release as Homecoming Princesses; GameFAQs' own walkthrough text ties a 'Large Vote Pack' purchase directly to that episode's bonus short stories, not independently dated |
| 2011-09-09 | 2: Homecoming Princesses | Wikia combined list |
| 2011-09-16 | 3: Ben's Blowup | Wikia combined list |
| 2011-09-23 | 4: Big Shoes to Phil | Wikia combined list |
| 2011-09-30 | 5: Homecoming, The Game | Wikia combined list |
| 2011-10-07 | 6: Homecoming, The Dance | Wikia combined list |
| 2011-10-14 | 7: Nerd No More | @SHSTeam (X) -- tweet: 'Now Airing for iPhone/iPad/iPod touch players! Season 7: Episode 7: Ne' |
| 2011-10-21 | 8: Halloween: The Second Kiss, Part One | Wikia combined list |
| 2011-10-21 | What Happened To Colt, Part 1 | Wikia combined list |
| 2011-10-28 | 1: Halloween: The Second Kiss, Part Two | @SHSTeam (X) -- tweet: 'Now Airing for iPhone/iPad/iPod touch players! Season 8: Episode 1: Ha' |
| 2011-11-04 | 2: Cheerevolution, Part One | @SHSTeam (X) -- tweet: 'Now Airing for iPhone/iPad/iPod touch players! Season 8: Episode 2: Ch' |
| 2011-11-11 | 3: Cheerevolution, Part Two | @SHSTeam (X) -- tweet: 'Now Airing for iPhone/iPad/iPod touch players! Season 8: Episode 2: Ch' |
| 2011-11-18 | 4: Double Date | Wikia combined list |
| 2011-11-25 | 5: Thanksgiving Surprise | @SHSTeam (X) -- tweet: 'Now Airing for iPhone/iPad/iPod touch players! Season 8: Episode 5: Th' |
| 2011-12-02 | 6: Taylor the Nerd | @SHSTeam (X) -- tweet: 'Now Airing for iPhone/iPad/iPod touch players! Season 8: Episode 6: Ta' |
| 2011-12-09 | 7: Secret Santa, Part One | @SHSTeam (X) -- tweet: 'Now Airing for iPhone/iPad/iPod touch players! Season 8: Episode 7: Se' |
| 2011-12-16 | 8: Secret Santa, Part Two | @SHSTeam (X) -- tweet: 'Now Airing for iPhone/iPad/iPod touch players! Season 8: Episode 8: Se' |
| 2011-12-16 | Set 9: Colt, Reformed | GameFAQs -- season bundle; matches its season's own first episode, 1: Christmas Break |
| 2011-12-16 | The Super New Girl | @SHSTeam (X) -- tweet: 'Hey SHS Fans,  Are you ready for the biggest SHS event ever?! Next Wed' |
| 2011-12-21 | 1: Christmas Break | Wikia combined list |
| 2011-12-21 | 2: Christmas Exchange | @SHSTeam (X) -- tweet: 'Hey SHS Fans,  Now available in the store...  Episode 2, Christmas Exc' |

### 2012

| Date | Episode | Source |
|---|---|---|
| 2012-01-06 | 3: New Year's Parties | @SHSTeam (X) -- tweet: 'Now Airing for iPhone/iPad/iPod touch players! Season 9, Episode 3: Ne' |
| 2012-01-09 | Holiday Short Stories | @SHSTeam (X) -- tweet: 'Hey SHS Fans,  Let us know what you think of SHS!   Have you played Th' |
| 2012-01-12 | A Tom Prince New Year's Eve | GameFAQs -- Holiday Tales bundle, sub-story 3 of 5 |
| 2012-01-12 | Christmas in Helzeroth | GameFAQs -- Holiday Tales bundle, sub-story 5 of 5 |
| 2012-01-12 | New Year's Connection | GameFAQs -- Holiday Tales bundle, sub-story 2 of 5 |
| 2012-01-12 | Officer Monte's New Year's Bash | GameFAQs -- Holiday Tales bundle, sub-story 4 of 5 |
| 2012-01-12 | The Mistletoe Match | GameFAQs -- Holiday Tales bundle, sub-story 1 of 5 |
| 2012-01-13 | 4: This is Spartan | @SHSTeam (X) -- tweet: 'Now Airing for iPhone/iPad/iPod touch players! Season 9, Episode 4: Th' |
| 2012-01-19 | 5: Clash of the Immortals | Wikia combined list |
| 2012-01-27 | 6: Valentine's Dilemma | @SHSTeam (X) -- tweet: 'Now Airing for iPhone/iPad/iPod touch players! Season 9, Episode 6: Va' |
| 2012-02-03 | 7: A Spartan Love Story, Part 1 | @SHSTeam (X) -- tweet: 'Now Airing for iPhone/iPad/iPod touch players! Season 9, Episode 7: A ' |
| 2012-02-10 | 8: A Spartan Love Story, Part 2 | @SHSTeam (X) -- tweet: 'Now Airing for iPhone/iPad/iPod touch players! Season 9, Episode 8: A ' |
| 2012-02-13 | Amanda's Valentine's Day | @SHSTeam (X) -- tweet: "Hey SHS Fans,  Check out our latest premium content, Amanda's Valentin" |
| 2012-02-17 | 1: 300's A Crowd | @SHSTeam (X) -- tweet: 'Now Airing for iPhone/iPad/iPod touch players! Season 10, Episode 1: 3' |
| 2012-02-17 | Set 10: The Spartan Games | @SHSTeam (X) -- season bundle; @SHSTeam "Season 10, Episode 1: 300's A Crowd" |
| 2012-02-24 | 2: The Contestants | @SHSTeam (X) -- tweet: 'Now Airing for iPhone/iPad/iPod touch players! Season 10, Episode 2: T' |
| 2012-03-02 | 3: The Spartan Games, Part One | @SHSTeam (X) -- tweet: 'Now Airing for iPhone/iPad/iPod touch players! Season 10, Episode 3: T' |
| 2012-03-02 | The Floating Isle | Wikia combined list |
| 2012-03-02 | The Super New Girl 2 | Wikia combined list |
| 2012-03-08 | Story Vote Ticket | Wikia era page -- Magic School |
| 2012-03-09 | 4: The Spartan Games, Part 2 | @SHSTeam (X) -- tweet: 'Now Airing for iPhone/iPad/iPod touch players! Season 10, Episode 4: T' |
| 2012-03-15 | 5: The Spartan Games, Part 3 | Wikia combined list |
| 2012-03-23 | 6: Eyes on the Prize | @SHSTeam (X) -- tweet: 'Now Airing for iPhone/iPad/iPod touch players! Season 10, Episode 6: E' |
| 2012-03-30 | 7: Faceplace Zero | @SHSTeam (X) -- tweet: 'Now Airing! – Season 10: Episode 10.7 - Faceplace Zero  Now Airing for' |
| 2012-03-30 | 8: Real Life Hero | @SHSTeam (X) -- tweet: 'On Demand/New Episode – Season 10: Episode 8: Real Life Hero  Let us k' |
| 2012-04-09 | Special: April Fools | @SHSTeam (X) -- tweet: 'Hey SHS Fans,  Have you checked out the Easter story at the beginning ' |
| 2012-04-19 | The Super New Girl 3: The Sinking Schools | Wikia combined list |
| 2012-04-20 | 1: Photo Op | @SHSTeam (X) -- tweet: 'Now Airing for this week is Season 11, Episode 1: Photo Op: Can you he' |
| 2012-04-20 | Set 11: The Election | @SHSTeam (X) -- season bundle; @SHSTeam "Season 11, Episode 1: Photo Op" |
| 2012-04-23 | 2: The Candidates | @SHSTeam (X) -- tweet: 'Of the three things we released on Friday (Photo Op, Candidates, and S' |
| 2012-05-03 | 3: The Endorsement | Wikia combined list |
| 2012-05-08 | 5: The Campaign Trail | @SHSTeam (X) -- tweet: 'Episode 5, The Campaign Trail comes out at the end of this week... Who' |
| 2012-05-10 | 4: The Last Straw | Wikia combined list |
| 2012-05-24 | 6: Sara The TV Star | Wikia combined list |
| 2012-05-31 | 7: Ballot Breakup | Wikia combined list |
| 2012-06-07 | 8: Nice Girl Unleashed | Wikia combined list |
| 2012-06-07 | Set 12: Howard's Goodbye | GameFAQs -- season bundle; matches its season's own first episode, 1: The New Head Cheerleader |
| 2012-06-14 | Special: Father's Day | Wikia combined list |
| 2012-06-14 | The Super New Girl 4: Reign of Dyre | Wikia combined list |
| 2012-06-21 | 1: The New Head Cheerleader | Wikia combined list |
| 2012-06-29 | 2: Date Auction | @SHSTeam (X) -- tweet: 'Now Airing: Season 12, Ep. 2: Date Auction: Ever since he broke up wit' |
| 2012-06-29 | 3: Howard's Last Day | @SHSTeam (X) -- tweet: "Now available in Episodes on Demand: Howard's Last Day: It's Howard's " |
| 2012-07-12 | 4: Wilson Strikes Back | Wikia combined list |
| 2012-07-19 | 5: Swim Team Trip | Wikia combined list |
| 2012-07-26 | 6: The Island Party | Wikia combined list |
| 2012-08-02 | 7: Howard's College Tour | Wikia combined list |
| 2012-08-09 | 8: A Kingston King | Wikia combined list |
| 2012-08-16 | Special: The Storm, Part 1 | Wikia combined list |
| 2012-08-23 | Special: The Storm, Part 2 | Wikia combined list |
| 2012-08-23 | Special: The Storm, Part Two | Wikia combined list |
| 2012-08-30 | Surviving High School: The Novel | Wikia combined list |
| 2012-09-05 | Season 1: A New Start | Wikia era page -- A New Start (season bundle; season start) |
| 2012-09-05 | Special Novel Chapter | Wikia era page -- A New Start (as Novel Bonus Chapter: The San Francisco Date Debacle) |
| 2012-09-07 | 1: Howard's Return | Wikia combined list |
| 2012-09-07 | A New Start 2: Howard's Return | Wikia era page -- A New Start (season bundle; season start) |
| 2012-09-11 | Getting Over Howard | @SHSTeam (X) -- tweet: 'Releasing Novel Prelude Bundle soon! Four episodes: The Storm 1 and 2 ' |
| 2012-09-11 | Special: Getting Over Howard | @SHSTeam (X) -- tweet: 'Releasing Novel Prelude Bundle soon! Four episodes: The Storm 1 and 2 ' |
| 2012-09-13 | 2: Swim Team Retreat, Part 1 | GameFAQs changelog |
| 2012-09-20 | 3: Swim Team Retreat, Part 2 | GameFAQs changelog |
| 2012-09-28 | 4: Howard's Secret | @SHSTeam (X) -- tweet: "Season 2, Episode 4 Howard's Secret is in More Episodes now! Share you" |
| 2012-10-05 | 5: Psych Project, Subject: Owen | @SHSTeam (X) -- tweet: 'SHS episode is up! Season 2, Episode 5, Psych Project: Subject Owen! C' |
| 2012-10-12 | 6: Psych Project, Subject: Paige | @SHSTeam (X) -- tweet: 'New SHS episode is up! Season 2, Episode 6, Psych Project, Subject: Pa' |
| 2012-10-19 | 7: The Halloween Dance, Part 1 | @SHSTeam (X) -- tweet: 'New SHS episode is up! Season 2, Episode 7, Halloween Dance, Part 1! C' |
| 2012-10-26 | 8: The Halloween Dance, Part 2 | Wikia combined list |
| 2012-11-02 | 1: Basketball Tryouts | Wikia combined list |
| 2012-11-09 | 2: The Dance_Dilemma, Part 1 | @SHSTeam (X) -- tweet: 'New SHS episode is up! Season 3, Episode 2, The Dance Dilemma, Part 1!' |
| 2012-11-09 | A New Start 3: The Dance Dilemma | Wikia era page -- A New Start (season bundle; season start) |
| 2012-11-16 | 3: The Dance Dilemma, Part 2 | Wikia combined list |
| 2012-11-23 | 4: Paige's Thanksgiving Party | Wikia combined list |
| 2012-11-29 | Magic School: Book 1 | Wikia combined list |
| 2012-12-07 | 5: The Snow Ball, Part 1 | @SHSTeam (X) -- tweet: 'New SHS Episode is up! Season 3, Episode 5, The Snow Ball, Part 1! Wil' |
| 2012-12-14 | 6: The Snow Ball, Part 2 | @SHSTeam (X) -- tweet: 'Season 3, Episode 6, The Snow Ball, Part 2 is up! Will they kiss?' |
| 2012-12-21 | 7: A Fallon Family Christmas | @SHSTeam (X) -- tweet: 'Season 3, Episode 7, A Fallon Family Christmas is up! Yes, Mal and Nat' |
| 2012-12-22 | Magic School: Book 2 | @SHSTeam (X) -- tweet: "It's here! Magic School: Book 2 is up!  Learn new spells, train your f" |
| 2012-12-28 | 8: Holiday Special | Wikia combined list |

### 2013

| Date | Episode | Source |
|---|---|---|
| 2013-01-03 | 1: Full Court Pressure | Wikia combined list |
| 2013-01-03 | A New Start 4: Love and Basketball | Wikia era page -- A New Start (season bundle; season start) |
| 2013-01-11 | 2: Showcase Sabotage, Part 1 | @SHSTeam (X) -- tweet: 'Hey SHS Fans! Showcase Sabotage, Part 1 is up in the store! Can Zoe fi' |
| 2013-01-17 | 3: Showcase Sabotage, Part 2 | Wikia combined list |
| 2013-01-17 | 7: The Art Showcase | @SHSTeam (X) -- tweet: 'Season 4, Episode 3, Showcase Showdown, Part Two is up! Can Zoe and Au' |
| 2013-01-25 | 4: Girl Trouble | @SHSTeam (X) -- tweet: 'Season 4, Episode 4, Girl Trouble is up in the SHS Store! Can Ben help' |
| 2013-02-01 | 5: Paige and Owen's Valentine's Outing | @SHSTeam (X) -- tweet: "Season 4, Episode 5, Paige and Owen's Valentine's Outing is up in the " |
| 2013-02-07 | 6: Anti-Valentine's Day | Wikia combined list |
| 2013-02-22 | 8: Sectionals | @SHSTeam (X) -- tweet: 'Season 4, Episode 8, Sectionals is up! Can Ben lead the team to victor' |
| 2013-02-28 | A New Start 5: Spring Break Romeo | GameFAQs -- season bundle; matches its season's own first episode, 1: The Play |
| 2013-03-01 | 1: The Play | Wikia combined list |
| 2013-03-08 | 2: Casting Call | @SHSTeam (X) -- tweet: 'Season 5, Episode 2, Casting Call is up in More Episodes now! Will Sam' |
| 2013-03-14 | O.M.G.! It's St. Patrick's Day! | GameFAQs changelog |
| 2013-03-15 | 3: Paige Against The Machine | @SHSTeam (X) -- tweet: 'Season 5, Episode 3, Paige Against the Machine, is up in More Episodes' |
| 2013-03-22 | 4: The Show Must Go On | @SHSTeam (X) -- tweet: 'Season 5, Episode 4 The Show Must Go On is up in More Episodes now! Ca' |
| 2013-03-29 | 5: Owen's Eleven | @SHSTeam (X) -- tweet: "Season 5, Episode 5 Owen's Eleven is up in More Episodes now! Can Owen" |
| 2013-03-31 | Easter Egg Hunt | Wikia combined list |
| 2013-04-05 | 6: Perfect Paige | @SHSTeam (X) -- tweet: 'Season 5, Episode 6 Perfect Paige is up in More Episodes now! Will Pai' |
| 2013-04-11 | Romeo and Juliet | Wikia combined list |
| 2013-04-12 | 7: Debutante Dance, Part 1 | @SHSTeam (X) -- tweet: 'Season 5, Episode 7, Debutante Dance, Part 1 is now available in More ' |
| 2013-04-18 | 8: Debutante Dance, Part 2 | Wikia combined list |
| 2013-04-25 | 1: Ready, S.E.T., Go | Wikia combined list |
| 2013-05-02 | 2: Cheer Off | Wikia combined list |
| 2013-05-11 | 3: How to Date a Nerd | @SHSTeam (X) -- tweet: 'Season 6, Episode 3, How to Date a Nerd is up in More Episodes! Can Ki' |
| 2013-05-17 | 4: This Friday Night | @SHSTeam (X) -- tweet: 'Season 6, Episode 4, This Friday Night is available in More Episodes! ' |
| 2013-05-24 | 5: The Newest Cheerleader | @SHSTeam (X) -- tweet: 'Season 6, Episode 5, The Newest Cheerleader is now available in More E' |
| 2013-05-31 | 6: Talent Search | @SHSTeam (X) -- tweet: 'Season 6, Episode 6, Talent Search is up in More Episodes! Twin Branch' |
| 2013-06-10 | 7: Talent Show | @SHSTeam (X) -- tweet: "Season 6, Episode 7, Talent Show is up in More Episodes! It's showtime" |
| 2013-06-13 | 8: Graduation Stories | Wikia combined list |
| 2013-06-20 | 1: Summer Beginnings | Wikia combined list |
| 2013-06-27 | 2: Admit Weekend | Wikia combined list |
| 2013-07-04 | 3: Sorority Showdown | Wikia combined list |
| 2013-07-18 | 5: Wedding Smashers | Wikia combined list |
| 2013-07-19 | 4: Rehearsal Dinner | @SHSTeam (X) -- tweet: 'The Weekly Free Episode for this week is Season 7, Episode 4: Rehearsa' |
| 2013-07-26 | 6: College Stories | @SHSTeam (X) -- tweet: "This week's new episode, College Stories, is now available under 'More" |
| 2013-08-09 | The Conned Artist, Part 1 | @SHSTeam (X) -- tweet: 'The Weekly Free Episode for this week is The Conned Artist, Part 1! Au' |
| 2013-08-15 | 7: Game Of Cones, Part 1 | GameFAQs changelog |
| 2013-08-15 | The Conned Artist, Part 2 | Wikia combined list |
| 2013-08-22 | 8: A Clash of Queens | Wikia combined list |
| 2013-08-29 | Magic School: Book 3 | @SHSTeam (X) -- tweet: "It's here! Magic School Book 3 is now available in More Episodes! Get " |
| 2013-09-05 | 1: Troublemakers | Wikia combined list |
| 2013-09-13 | 2: Dog Days | @SHSTeam (X) -- tweet: "Now in More Episodes, Episode 2: Dog Days! Will Owen's past come back " |
| 2013-09-20 | 3: The Fashionista | Wikia combined list |
| 2013-09-27 | 4: Spencer's Story | Wikia combined list |
| 2013-10-11 | 6: The Pumpkin Farmer's Daughter | Wikia combined list |
| 2013-10-14 | 5: The Breakup | @SHSTeam (X) -- tweet: 'Hey SHS Fans! What did you think of The Breakup? Did you swoon? Cry? T' |
| 2013-10-18 | 7: The Float | Wikia combined list |
| 2013-10-25 | 8: The Unusual Suspects | Wikia combined list |
| 2013-11-15 | College Scavenger Hunt | @SHSTeam (X) -- tweet: 'Hoping to make up for the issues with College Scavenger Hunt. Stay tun' |
| 2013-11-15 | Troublemakers 2: Holiday Hearts | Wikia era page -- Troublemakers (season bundle; season start) |
| 2013-11-23 | 1: The Tutors | @SHSTeam (X) -- tweet: '2.2 Homecoming Kiss is up in the store! 2.1 The Tutors is the Weekly F' |
| 2013-11-23 | 2: Homecoming Kiss | @SHSTeam (X) -- tweet: '2.2 Homecoming Kiss is up in the store! 2.1 The Tutors is the Weekly F' |
| 2013-11-27 | 3: A Troublemaker's Thanksgiving | Wikia combined list |
| 2013-12-17 | 4: Nate's Revenge | @SHSTeam (X) -- tweet: "What'd you all think about 4: Nate's Revenge?!" |
| 2013-12-20 | 5: Getaway | Wikia combined list |

### 2014

| Date | Episode | Source |
|---|---|---|
| 2014-01-23 | Troublemakers 3: Secrets Exposed | Wikia era page -- Troublemakers (season bundle; season start) |
| 2014-04-11 | 1: The Kimi Dates | @SHSTeam (X) -- tweet: "This week's new episode is The Kimi Dates! Can Kimi find romance?" |
| 2014-04-18 | 2: Just the Four of Us | Wikia combined list |
| 2014-04-25 | 3: Kimi Strikes Back | @SHSTeam (X) -- tweet: "This week's new episode is Kimi Strikes Back! Can Kimi get revenge on " |
| 2014-04-30 | 4: Prom | GameFAQs -- later changelog entry, 16.4 4/30/14 -- collided with an earlier, unrelated 5/29/11 Prom mention sharing the same bare title |
| 2014-06-11 | Battle of the Schools: Guy | Wikia combined list |
| 2014-06-20 | Battle of the Schools: Girl | Wikia era page -- Battle of the Schools (era page gives a later, more specific date than the combined list, which shows the same day as Guy) |
| 2014-07-04 | Series Finale | Wikia combined list |
| 2014-07-11 | Sierra's Challenge | Wikia combined list |
| 2014-07-18 | Lauren's Story | Wikia combined list |
| 2014-08-09 | Peter's Story | Wikia era page -- Battle of the Schools (as Peter's Challenge) |
| 2014-08-16 | Matteo's Date | Wikia combined list |
| 2014-08-22 | Magic School: Book 4 | Wikia combined list |
