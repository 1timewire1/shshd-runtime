# Episode splitter

**Status: survey only (owner, 2026-10-30).** Nothing is split yet. This file will describe the episode splitter once it
is built. For now it records the packs found in both games: EXPs that hold several episodes behind a menu, so the
splitter can turn each into separate entries in the episode list. The next step is a test split of one pack, before a
full system is planned.

## How the packs were found

- **SHS:** every episode of the test library (337) was run headlessly from its start, answering screens the way the
  tree explorer does (`tree_explorer.Explorer`), in ephemeral sessions that write nothing. An episode was flagged when
  a choice came **before its first title card** (service 8), or right after it when the choice reads like a menu
  ("How would you like to play?", "Which chapter / story...", "Where would you like to start?"). The second case
  catches packs that show their own card first (CoD's Volume 13 and 15).
- **Each flagged menu was walked:** every option was replayed from the start and followed to the next title card,
  through nested menus ("Select a chapter" > "Select from chapters 1-4" > the chapter), up to three levels deep. The
  card each option reaches names the episode behind it.
- **CoD:** the same run over its 74 episodes, then checked against the store listing (`mtxprods`, COD_STORE.md).
  Every chapter inside a Volume set was also sold on its own, so the listing gives each one's file name, pack and
  episode ids, title and description.

**Limits:**
- Episodes that open on the character picker (below) were stopped there, so a menu after the picker was not seen.
- A pack that plays its episodes in a row with no menu is not caught this way. A second pass counted the title cards
  of whole playthroughs for those (see Sequential packs). It covered SHS only, since CoD's store listing names its
  sets.
- Option-to-card pairs come from one replay each. A shuffled menu (Holiday Short Stories) is listed by its cards,
  not its first replay's pairs.

## SHS

### Chapter-select sets

Each opens on "How would you like to play?" (Start from the beginning / Select a chapter), or straight on "Which
chapter would you like?", then splits the chapters into two menus of four (Troublemakers 2: three). The chapters'
own title cards:

| Pack (file, pack/episode) | Episodes inside |
|---|---|
| A New Start 2: Howard's Return (`A_New_Start_Season_2.exp`, 1401/14000) | 1 Howard's Return · 2 Swim Team Retreat, Part 1 · 3 Swim Team Retreat, Part 2 · 4 Howard's Secret · 5 Psych Project, Subject: Owen · 6 Psych Project, Subject: Paige · 7 The Halloween Dance, Part 1 · 8 The Halloween Dance, Part 2 |
| A New Start 3: The Dance Dilemma (`A_New_Start_Season_3.exp`, 1501/15000) | 1 Basketball Tryouts · 2 The Dance Dilemma, Part 1 · 3 The Dance Dilemma, Part 2 · 4 Paige's Thanksgiving Party · 5 The Snow Ball, Part 1 · 6 The Snow Ball, Part 2 · 7 A Fallon Family Christmas · 8 Holiday Special! |
| A New Start 4: Love and Basketball (`A_New_Start_Season_4.exp`, 1601/16000) | 1 Full Court Pressure · 2 Showcase Sabotage, Part 1 · 3 Showcase Sabotage, Part 2 · 4 Girl Trouble · 5 Paige and Owen's Valentine's Outing · 6 Anti-Valentine's Day · 7 The Art Showcase · 8 Sectionals |
| A New Start 5: Spring Break Romeo (`A_New_Start_Set_5.exp`, 1701/17000) | 1 The Play · 2 Casting Call · 3 Paige Against The Machine · 4 The Show Must Go On · 5 Owen's Eleven · 6 Perfect Paige · 7 The Debutante Dance, Part 1 · 8 The Debutante Dance, Part 2 |
| Troublemakers 2: Holiday Hearts (`Troublemakers_Season_2.exp`, 2001/22000) | 1 The Tutors · 2 Homecoming Kiss · 3 A Troublemakers Thanksgiving · 4 Nate's Revenge · 5 Getaway · 6 Christmas Stories |
| Troublemakers 3: Secrets Exposed (`Troublemakers_Season_3.exp`, 2001/24000) | 1 The Date · 2 Pyramid Scheme · 3 The Secret Life of Owen Harris · 4 Exposed · 5 Spencer Betrayed · 6 The Winter Dance · 7 Heart to Hart · 8 Hart Attack |
| Set 9: Colt, Reformed (`Set_9.exp`, 9000/1) | 1 Christmas Break · 2 Christmas Exchange · 3 New Year's Parties · 4 This is Spartan! · 5 Clash of The Immortals · 6 Valentine's Dilemma · 7 A Spartan Love Story, Part 1 · 8 A Spartan Love Story, Part 2 |
| Set 10: The Spartan Games (`Set_10.exp`, 10000/1) | 1 300's a Crowd · 2 The Contestants · 3 The Spartan Games, Part One · 4 The Spartan Games, Part Two · 5 The Spartan Games, Part Three · 6 Eyes on the Prize · 7 Faceplace Zero · 8 Real Life Hero |
| Set 11: The Election (`Set_11.exp`, 11000/1) | 1 Photo Op · 2 The Candidates · 3 The Endorsement · 4 The Last Straw (first asks: play the short story **Mother's Day**, or continue) · 5 The Campaign Trail · 6 Sara the TV Star · 7 Ballot Breakup · 8 Nice Girl Unleashed |
| Set 12: Howard's Goodbye (`Set_12.exp`, 12000/1) | 1 The New Head Cheerleader · 2 Date Auction · 3 Howard's Last Day · 4 Wilson Strikes Back · 5 Swim Team Trip · 6 The Island Party · 7 Howard's College Tour · 8 A Kingston King |

### Story collections

A menu of separate stories:

| Pack (file, pack/episode) | Asks | Stories inside (title card) |
|---|---|---|
| College Scavenger Hunt (`1_9_College_Scavenger_Hunt.exp`, 1901/90) | What would you like to play? | College Scavenger Hunt · Homecoming (A Magic School Short Story) |
| 7: A Fallon Family Christmas (`3_7_A_Fallon_Family_Christmas.exp`, 1501/70) | Which story do you want to play? | A Fallon Family Christmas · The Christmas Curse |
| 8: Holiday Special (`3_8_Howards_Holidays.exp`, 1501/80) | its own card, then What would you like to play? | Howard's Holidays · Paige's Nightmare After Christmas |
| 4: The Last Straw (`11_4_The_Last_Straw.exp`, 1101/4) | What would you like to do? | Mother's Day (short story) · The Last Straw |
| Amanda's Valentine's Day (`amanda_valentines.exp`, 7/2004) | Which story would you like to see? | Amanda's Valentine's Day · Soul Searching: A Claire Hart Story |
| Holiday Short Stories (`MTX_Holiday_Short_Stories.exp`, 7/2001) | its own card, then Which story do you want to see? | The Chronicles of Amanda · Kay and Kel's Christmas Crisis · Riches to Rags (A Monarch Prep Story). The menu is shuffled each time (service 78's shuffle), and a story runs on into the next one's card. |
| Surviving High School 11 Demos (`NR_48_...`, 31300/48) | Which demo would you like to play first? | Best Party Ever · The New Girl. This is our own New Rules translation, so splitting it is our choice. |

A New Start 3's chapters 7 and 8 are the standalone "7: A Fallon Family Christmas" and "8: Holiday Special" packs
(the set offers only their main stories). Set 11's chapter 4 is the standalone "4: The Last Straw".

### Start-point menus

| Pack | Asks | Starts |
|---|---|---|
| Romeo and Juliet (`MTX_ROMEO_AND_JULIET.exp`, 7/3000) | Where would you like to start? | At the beginning (Romeo and Juliet) · Act Two · Act Three · Act Four · Act Five |

One story with jumps to its acts, not separate episodes. Whether it splits is the owner's call.

### Menus that are not packs

| Episode | What the opening menu is |
|---|---|
| 7: Game Of Cones, Part 1; The Conned Artist, Parts 1 and 2 | High School Story promotion: open the app (ends the episode), a sneak peek (an untitled card), or play the episode |
| Story Vote Ticket | A genre vote (the survey confirmation) |
| Special: April Fools | A joke "rate this pack" menu before the episode's card (its three parodies follow in a row: see Sequential packs) |
| Love Potion Fun Pack | Activities after its card (trivia, a quiz, matching couples) |
| Day of Diss, Dating Beth (Xbox 360 translations) | Ordinary story choices before any card |

### Not reached

These open on the character picker, where the survey stops: Battle of the Schools (Girl and Guy), Lauren's Story,
Matteo's Date, Peter's Story, Sierra's Challenge, Dancing Queen, King of Diss. Puzzle Test ends with no card.

### Sequential packs

These hold several episodes or stories **in a row, with no menu**. They were found by playing every SHS episode
through once (the tree explorer's choices, seed 0) and listing its title cards, then checking the opening of each
that showed more than one story. Most episodes with several cards are a single story with day or part cards
("Monday", "Week 2 of 8", "Part 1", "Sophomore year"); those are left out.

| Pack (file) | Its cards, in order |
|---|---|
| Season 1: A New Start (`SHS_Season_1.exp`, two copies) | Episode One: The First Day · Episode Two: High Spirits · Episode Three: Making a Name · Episode Four: The Dinner and the Party · Episode Five: The Big Game |
| Magic School: Book 1 (`1_1_Magic_School.exp`) | Chapter 1: Unexpected Detours · 2: First Days · 3: Campus Tour · Four: Creatures of the Wilde · Five: Friends and Companions · Epilogue: Schemes |
| Magic School: Book 2 (`1_2_Magic_School.exp`) | Chapter 1: Pleasingly Familiar · 2: Party Crashers · 3: Accusations And Admissions · Four: The Morning After · Five: The Hecate |
| Magic School: Book 3 (`1_3_Magic_School.exp`) | Prelude: Trust · Chapter 1: Obstacles · 2: Beastly Beginnings · 3: Poor Study · 4: The Heist · 5: Phall'anx |
| Magic School: Book 4 (`1_4_Magic_School.exp`) | Chapter 1: Of Dungeons · 2: Escape (the playthrough did not finish, so more may follow) |
| Special: Father's Day (`MTX_Fathers_Day.exp`) | its card, then Erik and Sam · Colt and Denni · Howard and Zoe |
| Special: April Fools (`11_0_April_Fools.exp`) | the joke menu and its card, then Cause of Centerscore: The Prom Case · Animal High: A Horse of a Different Color · A Different Twin Branches: Couple Swap |
| 8: Graduation Stories (`6_8_GraduationStories.exp`) | its card, then Colt and Denni, Part 1 · Sam and Zoe, Part 1 · Hector and Amanda, Parts 1 and 2 · Sam and Zoe, Part 2 · Colt and Denni, Part 2. The pairs are interleaved, so this is one finale more than separate stories. |
| 6: College Stories (`7_6_College_Stories.exp`) | its card, then Football: Admit Weekend (other segments may depend on choices) |

**Vote packages** (Homecoming): the Small and Medium packages are a card and one story (Sam's: The Social Butterfly;
Sara's: Winning; Taylor's: Birth of a Mean Girl). The Large packages (`Sam3.exp`, `Sara3.exp`, `Taylor3.exp`,
`Zoe3.exp`) ask "Whose story do you want to see?" after their card: Taylor (Birth of a Mean Girl), Sam (The Social
Butterfly), Sara (Winning), and Zoe, whose option reached no card in the replay.

**Bonus stories inside an episode:** 6: Perfect Paige opens with "One Too Many Boyfriends" before its own card. Set 12's
episodes 3, 4 and 5 (Howard's Last Day, Wilson Strikes Back, Swim Team Trip) each lead to "Super New Girl: The Complete
Saga".

**Not packs:** Gossip Files is a reader that loops over its files (the playthrough was stopped after 17,221 cards).
The New Rules translations' chapter cards (King of Diss Lite: Chapter 1, 1.1...) are one story each.

**Limits of this pass:** 43 episodes stopped at a survey screen the explorer cannot answer (the vote and feedback
screens near their end), so their later cards were not seen.

## Cause of Death

### Volume sets

The owner's library has the set EXPs of Volumes 2-13 and 15, and Volumes 14 and 16 as separate chapters. Every set
opens on "How would you like to play?" (13 and 15 after their own card), then "Select a chapter". Its chapters are
the store's own chapter products: the table gives each one's store file and ids, for the split episodes to take.

| Set (file) | Chapters (store file, pack/episode) | Interludes on the set's menu |
|---|---|---|
| Volume 2 (`Volume_2.exp`) | 1 Tough Love `2_1_Tough_Love` 101/1 · 2 Head Case `2_2_Head_Case` 101/2 · 3 Sins of the Fathers `2_3_Sins_of_the_Fathers` 101/17 · 4 Catching Fire `2_4_Catching_Fire` 101/4 · 5 Missing Persons, Pt. 1 `2_5_Missing_Persons_Pt_1` 101/5 · 6 Missing Persons, Part 2 `2_6_Missing_Persons_2` 101/6 · 7 Old Wounds `2_7_Old_Wounds` 101/7 · 8 Revelations `2_8_Revelations` 101/8 | |
| Volume 3 (`Volume_3.exp`) | 1 Prey · 2 Broken Hearted, Part 1 · 3 Broken Hearted, Part 2 · 4 Hunter, Hunted · 5 Lights, Camera, Murder, Part 1 · 6 Part 2 · 7 Savage · 8 The Wild Hunt (`3_N_...`, 201/1-8) | |
| Volume 4 (`Volume_4.exp`) | 1 Zero Hour · 2 Blood Relations, Part 1 · 3 Part 2 · 4 Coded Messages · 5 Games We Play, Part 1 · 6 Part 2 · 7 Zero Sum Game · 8 Zero Consequences (`4_N_...`, 301/1-8) | |
| Volume 5 (`Volume_5.exp`) | 1 Dread Silence · 2 The Perilous Fight · 3 The Shore Dimly Seen · 4 The Gloom of the Grave · 5 The Root of All Evil, Part 1 · 6 Part 2 · 7 Trafficked · 8 Mallory (`5_N_...`, 401/1-8) | |
| Volume 6 (`Volume_6.exp`) | 1 Opening Moves · 2 Under My Skin, Part 1 · 3 Part 2 · 4 Gambit · 5 Breaking Point, Part 1 · 6 Part 2 · 7 Zugzwang · 8 Endgame (`6_N_...`, 501/1-8) | |
| Volume 7 (`Volume_7.exp`) | 1 Bad Romance · 2 In Vino Veritas, Part 1 · 3 Part 2 · 4 Split · 5 Domestic Disturbance, Part 1 · 6 Part 2 · 7 Killer Alibi · 8 Final Flight (`7_N_...`, 601/1-8) | |
| Volume 8 (`Volume_8.exp`) | 1 Tendrils · 2 Crimes of Passion, Part 1 · 3 Part 2 · 4 Rising Tides, Part 1 · 5 Part 2 · 6 A Day in the Life · 7 In Roaring He Shall Rise · 8 And On The Surface Die (`8_N_...`, 701/1-8) | |
| Volume 9 (`Volume_9.exp`) | 1 Walk the Wire · 2 Fire and Brimstone, Part 1 · 3 Part 2 · 4 Sparks · 5 Kings of Las Vegas, Part 1 · 6 Part 2 · 7 Shock and Awe, Part 1 · 8 Part 2 (`9_N_...`, 801/1-5, 60, 70, 80) | Wild Things · Best Intentions (store: `9_Interlude`, 801/45) |
| Volume 10 (`Volume_102.exp`) | 1 Fear and Loathing · 2 Truth or Dare, Part 1 · 3 Part 2 · 4 Nightmare · 5 In Fidelity, Part 1 · 6 Part 2 · 7 Love and Madness · 8 Death Do Us Part (`10_N_...`, 901/10-80) | Something New · Going Stag (store: `10_Interlude`, 901/45) |
| Volume 11 (`Volume_11.exp`) | 1 Best Served Cold · 2 Black Magic, Part 1 · 3 Part 2 · 4 Putting the Pieces Together · 5 Tangled Webs · 6 Wolf at the Gates · 7 Love and War, Part 1 · 8 Part 2 (`11_N_...`, 1001/10-80) | The Fall of Fallon (store: `11_Interlude`, 1001/45) |
| Volume 12 (`Volume_12.exp`) | 1 Monsters Among Us · 2 Bloodlines, Part 1 · 3 Part 2 · 4 Special Friend · 5 The Old College Try, Part 1 · 6 Part 2 · 7 Nothing To Fear · 8 Out Of The Shadows (`12_N_...`, 1101/10-80) | |
| Volume 13 (`Volume_13.exp`) | 1 The Creeping Darkness · 2 Blood and Water · 3 The Boys in Blue · 4 Predator Unseen · 5 Safety in Numbers · 6 Ghosts of the Past · 7 Spider to the Fly · 8 Brood (`13_N_...`, 1201/10-80) | Perfect Getaway (store: `13_Interlude`, 1201/45) · April Fools: The Break-Up · March of Madness: A Good Day · Volume 14 Prologue (no store product for the last three) |
| Volume 15 (`Volume_15.exp`) | 1 Across the Pond · 2 The Harrowing Truth · 3 Mixed Messages · 4 Pretenders · 5 Hanging by a Thread · 6 The End of the Rope · 7 High Crimes · 8 Capital Punishment (`15_N_...`, 1401/10-80) | The Days We Remember (store: `15_Interlude`, 1401/35) · Ho-Ho-Homicide · It's a Wonderful Kai (the Holiday Stories pack's) |

The store also sells Volumes 14 and 16 as sets (`Volume_14.exp`, `Volume_16.exp`, not in the owner's library) and
two-chapter combos for Volumes 2-5 and 11. The owner has 14 and 16 as chapters already.

### Story collections

| Pack (file, pack/episode) | Asks | Stories inside (title card) |
|---|---|---|
| First Date, First Kiss, First Kill (`First_Date.exp`, 7/10) | Which story would you like to see? | First Date · First Kiss · First Kill. First Kiss's own card also reads "First Date" (no subtitle), and First Date runs on into it. |
| Love and Bullets (`MTX_Love_And_Bullets.exp`, 7/4) | Which story would you like to see? | The Veritox Incident · All Alone, Under the Stars · Mysterious Ways · Just Another Day |
| Buried Secrets, Buried Lives (`MTX_Buried_Secrets_Buried_Lives.exp`, 7/11) | Which story would you like to see? | Hostile Takeover · Four Hours · From Oahu With Kai |
| Life Lessons, Deadly Desires (`MTX_Life_Lessons_Deadly_Desires.exp`, 7/12) | Which story would you like to see? | Alma Maltara · Follow the L.E.A.D.E.R · A Slip of the Mask |
| A Cause of Death Christmas (`MTX_Christmas_Stories.exp`, 7/8) | Which story would you like to see? | A Mansingh Family Christmas · Claus of Death |
| Valentine Short Stories (`Valentine_Stories.exp`, 7/9) | Which story would you like to see? | An Unconventional Crime · Love-Locked · Volume 8 Preview |
| Holiday Interlude: A Fallon Family Christmas (`12_Fallon_Family_Christmas.exp`, 7/14) | Which story do you want to play? | A Fallon Family Christmas · The Christmas Curse (SHS's crossover pair) |
| Holiday Stories: Past and Presents (`MTX_Holiday_Stories_Past_and_Presents.exp`, 7/16) | its own card, then Which story would you like to play? | Ho-Ho-Homicide · It's a Wonderful Kai! |

### Menus that are not packs

| Episode | What the opening menu is |
|---|---|
| Secret Files, Secret Files 02 | Character dossiers browsed by category (untitled cards, Back rows): a reader, not episodes |
| Halloween Special: Dead Man Walking, Part 1 | "Play the short story?", with Ghost Harvest cross-sell rows, then the episode |
| What Happened To Colt, Part 2 | "Check out Surviving High School?", then the episode either way |
| Chapter Four: Sunrise; Chapter Seven: Sunset | Ordinary story choices before the card |

## Next: a test split

One pack is split by hand first, to answer:
- **Starting a chapter:** how the split entry enters the pack at its chapter (replaying the menu's answers, or
  starting at the chapter's own script), and what the pack does when that chapter ends (on to the next chapter, or
  back to its menu).
- **What stays shared:** the pack's resources and file are one, so the split entries point into it rather than copy
  it.
- **Saves and the Decision Tree:** both key off the episode record today.
- **The list:** each split entry's title, category and order, and for CoD the chapter product's description and
  price on the info card.
