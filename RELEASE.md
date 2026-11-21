# SHSHD Runtime v1.1.0

**This release brings SHSHD Runtime to Android and back to iOS, fits any screen shape, and plays episodes
translated from the other Surviving High School games, with their own art, music and real minigames.** Your
libraries and saves from v1.0.x carry over: no re-import needed.

## What's new

### On every screen

- **Android app** (thanks @andymenard, whose fork started the port): the same app on phones and tablets, with
  touch, pinch-to-zoom on the story tree, the side panels in landscape, RAR import and the device's vibrator.
  Tuned on a Moto g54 to hold 50-60 fps in stories, menus and minigames.
- **iOS app caught up:** everything this fork draws now runs on iPhone and iPad, composited on the GPU, edge
  to edge with the safe area.
- **Any screen shape** (Options → General → Aspect Ratio): **Fit Screen** (the default on phones), 3:4, 2:3 or
  9:16. The story fills a taller frame without squeezing dialogue, backgrounds keep their scale and show more of
  the scene, and every menu, card and minigame is laid out for it. On a computer, picking a shape resizes the
  window.
- **Side panels on any shape:** the Faceplace wall and story tree open over the story on narrow screens, and turn
  a phone or tablet to landscape.
- **Controller support** (thanks @zazatree): buttons by position, football and the word grid included, with a
  confirm-button setting and a Hold mode for the grid.

### Playing

- **Skip Ahead** (Options → Extras): straight to the next choice, minigame or title card.
- **Undo** (Options → Extras → Allow Undo, off by default): back to your last choice, or the one before; a
  minigame under way starts over.
- **Choice Hints** no longer freeze the screen: they're worked out alongside the frames.
- **Episode versions:** importing a newer copy of an episode replaces the older one, asking first if it has a
  game in progress.

### Menus and data

- **Finished episodes show green:** once you've played an episode to its end, its play button in Now Airing and Episodes
  On Demand turns green (both games). An episode you finished before this version counts too while its last save is
  still the one at the end. The marks travel with Sync and backups, and Delete All Saves clears them.
- **New app screens:** a game chooser, Bulk Import and Setup in the HD style, with a file browser.
- **Add Content** (Data Management's first row, both games): add episodes, add-ons, fonts, the games' catalogs and
  Cause of Death's store listing (`mtxprods`) in one place. After adding a font, **Reopen** loads it at once.
- **Mark as Finished** (Data Management → Episodes): every episode in a tick list, the finished ones ticked; tick or
  untick and Save to change which count as finished.
- **Options shared by both games**, with pages for settings that have several values: **Start In** (Last
  Played by default), **Skip Sound Prompt**, **Unlock Warping**, and the device's vibration under General.
- **Data Management:** Storage, Verify Library, Rebuild Previews and HD Art; delete, export or reset the
  Decision Tree by episode; **Back Up and Restore Progress**; Delete Library; folders of your choice on a
  computer.
- **Sync Devices:** send progress, episodes and add-ons between your devices on the same network.
- **Preferred Language** (Options → General): one choice of English, Français, Italiano, Deutsch or Español for
  episode titles and for the stories that have that language (the DSi's, '11's in Italian, and Creator episodes).
- **Title Screen Music** and **Title Screen Look** (Options → Add-Ons): give the main menu a translated game's
  title tune and title art, or let **Auto** follow the game you played last.
- **Skip Upsell Intros**: pass the store plugs 33 SHS and 38 Cause of Death episodes open with (#8).

### Translated games and add-ons

**Add-ons** are shared resource packs that a set of episodes declares, such as a translated game's art and
music. They import like episodes and travel with them in Sync and Export. `tools/translate` builds them, and
the translated episodes, from your own copies of the games. No game files are included.

- **SHS: New Rules** (50 stories): played on New Rules' own minigame arena, its library code running beside
  the story, with Hi-Res Portraits from the X1i build.
- **The cancelled Xbox 360 prototype:** Day of Diss (with a storyboard opening), Dating Beth, Monday Planner
  and the Puzzle Test, with the prototype's own portraits and backgrounds. Their minigames are real: the slot
  machine, the leash, the jewel puzzle, **Diss Practice** on the turntable, and a new **Diss Battle** against
  Spike. MS3 Characters swaps in the April build's looks, and the X360 Arena Skin redraws New Rules' arena
  as the turntable. The optional **X360 animations** add-on adds Josh's dance and Zack wrestling the doberman
  in the leash game.
- **SHS '11** (5 stories): real **Memory** and **Reflex**, a Word Grid skin, an Extras switch to play
  Memory in place of letter grids, and '11's own **Italian** (Preferred Language → Italiano).
- **SHS '07 and '08 (BREW)** (126 stories): the '08 Campaign, the Classic stories, M.A.S.H. packs and Fall '06
  Football Season, on their calendars, with the catch game played for real and a Java '08 Look.
- **Surviving Hollywood** (the 2007 Nokia demo): **The Bright Lights**, its whole month-long Chapter 1, with a
  **Where to?** map of the places open each hour, date cards, stat pages and the **Quest Journal** in the pause
  menu; its minigames as SHS's word games, the catch game in the demo's own look and a spelling grid for the
  rehearsals. The faceless walk-ons wear the low-end demo's silhouettes. **The Bright Lights (Lite)** is the other
  demo's shorter Chapter 1, and **Use SHW Art in Preview** dresses the BREW *Surviving Hollywood Preview* in the demo's
  painted portraits, backgrounds and music.
- **SHS DSiWare:** **DSi Backgrounds** (Extras: Off, Sharp or Smooth) shows the DSi's redrawn backgrounds in
  matching episodes, and **Preferred Language** plays its eight stories in French, Italian, German or Spanish.
- **Cause of Death:** 64 of its backgrounds in HD from your own SHS HD, and the optional `chslim` pack with
  Claire Hart's sharper portraits.
- Each translated game's add-on also carries its game's icon, ready for a game chooser that lists them in a later
  version.
- **Use Translated Mini-Games** (Options → Add-Ons) turns the real minigames on; without it, or on another
  player, the stories take the word games they carry. **Ask to Skip Mini-Games** offers each outcome a game's
  story has.

### The episode creator

- A project can be built on a translated game's add-on (its frame, icons, music and minigames), use other
  add-ons as extras, and write storyboards in a timeline editor.
- It covers every service the original SHS, SHS HD and CoD episodes call, plus SHS HD's side panels.
- It's now an app of its own, **SHSHD Runtime Creator**, for Windows, macOS and Linux, and also an MCP server
  (`--mcp --workspace FOLDER`).
- Its episodes are listed under **User-Created Episodes**, after the official ones, in Now Airing too.
- A project's translations (French, Italian, German, Spanish, English) travel inside its episodes, shown in the
  player's Preferred Language.
- It caught up with this release's games: Surviving Hollywood as a base (with its quest journal, answer details and
  stat pages), optional Hollywood and DSi art, Reflex with your own icons, BREW-style calendars (school days, events,
  date cards and time badges), and New Rules' minigames in their arena. Playtests and MCP can play or skip every
  translated minigame and cutscene.
- A photo posted to the Faceplace wall from a project's own pictures now shows on the wall.
- Cause of Death projects use CoD's own name styles (standard or upright) in place of SHS's bubble colours.

## Changes and fixes

- Episodes made of a single script (Easter Egg Hunt, for one) end when their story does, instead of waiting at the end.
- A saved game's picture no longer has a black bar down one side at Fit Screen.
- iPhone and iPad: the picture no longer flickers (most of all in New Rules' arena and on its backdrop).
- The X360 Diss games no longer slow down on a wrong answer, most of all on the iPad.
- Episode previews that failed to draw (Cause of Death's whole grid, after a first setup on a phone) are tried again
  instead of staying blank; Rebuild Previews clears them too.
- Cause of Death no longer asks "Play with sound?" a second time while its launch fades out.
- About (both games) thanks @andymenard for the Android groundwork, and lists the open-source notices last.
- Libraries open faster, most of all on the iPad: the game's own app files and add-ons are no longer read whole each time.
- Faster starts: the app remembers which saved games ended their story instead of reading each one at every launch.
- iPad: the game chooser's Options no longer redraw every frame while still, and Sync's notice no longer has
  switches over it; the X360 Diss games' effects draw without slow blends.
- Back Up Progress's message says the Decision Trees went too.
- The X360 Diss games' hit effects reuse their sprites: smoother Diss Battles, most of all on the iPad.
- iPad: the episode picker's tiles load behind the scene (the placeholder shows meanwhile), so it no longer stutters.
- iPhone and iPad: backups (including a sync's Back Up Receiver First) and exported episodes go in the app's own
  folder in Files; they used to fail.
- iPhone and iPad: the app no longer freezes on its last frame after iOS pauses it and never says it's back (an audio
  interruption, for one).
- Faster on phones: the X360 games, the BREW word game, translated episodes and outlined text all draw less each
  frame (on a Moto g54 the word game went from 29 to 55 fps, the jewel puzzle from 39 to 58 and the main menu from 53 to 60).
- New Rules' arena spreads through taller screens in both looks: timer and score near the top, the table and ring
  in the middle, the gear on the frame's corner.
- New Rules' **Sequences** plays with a controller: the D-pad moves a highlight round its number keys and confirm
  presses it.
- The SHS novel's Extended chapter is listed under Special SHS Novel Content.
- Time and place badges in the BREW and Hollywood stories show for one line only, never over a title card; the '08
  Campaign's chapter 1 cards no longer carry a date.
- New Rules' arena shows New Rules' own info box, and its tutorial bubbles keep below a phone's status bar.
- New Rules' arena runs about twice as fast on phones (16 to 33–43 fps on a Moto g54, in both looks): the picture under
  it was being blended every frame.
- Sync Devices keeps the options it receives on a computer's game chooser (they were put back as they were), and
  leaves the Choose Receiver and Receive pages once a sync ends.
- Restoring a sync's "before sync" backup puts back only the episodes it holds; the others keep their progress.
- Help's and About's pages, the chooser's pages and the file browser keep clear of a phone's status and navigation bars.
- The panels' whoosh no longer comes a second after they open or close.
- Bulk Import takes an add-on found among a folder's episodes (Cause of Death's chslim stopped the whole import).
- Delete Library removes everything again: DSi Backgrounds' file was left behind, and the library with it.
- Adding the SHS HD IPA to a library made without it says how to add it (back up, make the library again with both,
  restore), and a file Add Content refuses is named.
- Android: Cause of Death's iOS fonts fall back to the phone's Roboto when they're missing, as on the PC.
- One **Funky Monkey**: '07's, with '08's typo fixes and rewordings; the Classic copy is gone.
- Named lines without a portrait in the translated games:
  - In New Rules, an off-stage character speaks with their own portrait. The loudspeaker, the newswoman and Ryan's mom
    have looks of their own.
  - Things are gray and crowds are yellow, and a voice takes its speaker's colour.
  - BREW's Phone and TV wear the pictures the other stories give them.
- '07's stories keep separate player names for a boy's story and a girl's, so one no longer overwrites the other.
- New Rules' Train That Brain! no longer stops after about 33 rounds of training.
- Surviving Hollywood is listed between '07 and '08. The add-on switches and Title Screen Music and Look follow the same order
  of games.
- Data Management's Exports and Backups Folder rows show their folder under the name, as General's choices do.
- Surviving Hollywood's title and date cards show SHS HD's sunset city skyline.
- Portrait pickers of three photos put one on each side of the chosen one, and Fall '06's six wrap round it.
- Fall '06's first day opens on the bedroom instead of an empty backdrop; its week cards all keep the school.
- iOS: sound effects and the X360 jewel puzzle's glows no longer hold up frames.
- The X360 leash game no longer stalls as it opens on a phone, and the X360 games' art is let go when you leave them.
- A freeze when music paused just as a sound effect ended (pygame's music pause could deadlock) is fixed.
- A saved game's picture in the episode tiles shows the choice again on tall screens (9:16 and taller, a phone at
  Fit Screen).
- The X360 cutscenes no longer start under the loading screen on a phone, and title cards keep off a narrow
  screen's edges.
- The X360 leash game's cast cuts cleanly between poses, and a flick in the jewel puzzle carries the row on.

- Cause of Death's end of episode is its own "Thanks for playing!" panel, and "Miss An Episode?" zooms in
  (#16, thanks @zazatree).
- Resume zooms the pause menu out (#15), the dialogue box resizes between lines and the Options switches slide
  (#14), starting an episode shows the loading screen (#13), and the picker's popups and "Delete Saved Game?"
  animate (#12), all thanks @zazatree.
- Football and the word grid fade in and out over the scene as SHS HD's do, and the minigame loading band
  animates (#18, thanks @zazatree).
- Scene pictures crossfade, and the chapter card fades in as the original does.
- Expressions change a second sooner in SHS HD and Cause of Death (#2).
- Song lines show SHS HD's music notes; long one-word names fit the name plate.
- Links in episodes are offered behind "Exit Game?" in both games.
- Fades keep their transparency on macOS; Now Airing and Episodes On Demand no longer open over black there.
- Menus no longer slow down as you finish episodes; music can no longer freeze the player; the 60 s autosave
  waits until a minigame ends instead of stalling it.
- What Happened to Colt, Part 1 no longer stops when its timed choice runs out.

---

SHSHD Runtime is a fork of
[exp-runtime](https://github.com/joshrmcdaniel/exp-runtime) that plays
Surviving High School (including its iPad HD release) and Cause of Death with
your own game files. It is a separate app: its own data folder, window and app
identifiers, so it never touches an installed copy of exp-runtime.

No game files are included. You supply your own.

## Downloads

- **Windows, macOS, Linux:** `shshd-runtime-<version>-<platform>` archives. Unzip
  and run SHSHD Runtime. Builds are unsigned (macOS: ad-hoc signed, not notarized): the first time, right-click
  the app and choose Open on macOS, or More info, Run anyway on Windows.
- **Episode Creator:** `shshd-runtime-creator-<version>-<platform>` archives, for the platforms whose build passed.
  Its first launch is the same as the player's.
- **Android:** `shshd-runtime-<version>-android.apk`, for Android 7.0 or newer. Sideload it; it isn't on the Play
  Store.
- **iOS:** `shshd-runtime-<version>-ios-arm64-unsigned.ipa`. It's unsigned: sign it with your own Apple ID
  or a signing tool before installing.

Each download has a SHA-256 checksum beside it.

See CHANGELOG.md for the full list of changes.
