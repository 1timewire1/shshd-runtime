# SHSHD Runtime v1.1.1

**A patch release: crash fixes for the game chooser's Sound page, Cause of Death's word quizzes and iOS after a
first import, and a new Text Animation setting.** Your libraries and saves from v1.1.0 carry over: no re-import
needed.

## What's new

- **Text Animation** (Options → General): how dialogue text comes out. **Letter by Letter** (the Android games',
  the default, as before), **Line Wipe** (the iPhone and iPad games': each line wiped in from the left, one after
  another; a tap speeds it up) or **Instant**. With Autoplay Dialogue on, a page still waits as long as Letter by
  Letter would have taken, so the pacing stays the same.
- **Options pages that don't fit now scroll.** The main menu's General page had grown too tall for a 3:4 window,
  cutting off its back button. Drag the rows (or use the wheel, Page Up / Down, or the arrow keys); pages that fit
  look as before.

## Fixes

- **The game chooser's Options → Sound closed the app** on every platform ("AppCard.slider() got an unexpected
  keyword argument 'key'"). On iOS its switches and sliders now work there too.
- **A Cause of Death word quiz closed the app** with Ask to Skip Mini-Games on (Android).
- **iOS closed the app after a first Bulk Import.** Drawing the episode previews kept about 1 GB of memory, so the
  next large job crossed iOS's limit. Building every SHS preview now stays near 220 MB.
- **After Delete Library, Bulk Import said the game "already has a library"** and imported nothing: two of the
  library's files stayed behind. Delete Library now removes them too.
- **Letters typed quickly in the name entry were lost** ("Sam" could come out "S" and the name never confirmed),
  most likely with a phone keyboard's suggestions.
- **The Decision Tree's "Locked" notice and a Faceplace link's "Exit Game?"** were hidden under the side panels on
  phones and narrow windows, so tapping seemed to do nothing until the panels closed.
- **A save from a newer build is no longer set aside as corrupt.** It stays where it is, with a message to update.
- **Backups made in the same second** list newest first.

## Upgrading

Saves made with v1.1.1 use a newer format (they remember the Text Animation of the page you were on). Saves from
v1.1.0 load as they are, but going back to v1.1.0 afterwards isn't supported: it would set the newer saves aside as
damaged. Back Up Progress first if you might.

## Downloads

- **Windows, macOS, Linux:** `shshd-runtime-<version>-<platform>` archives. Unzip
  and run SHSHD Runtime. Builds are unsigned (macOS: ad-hoc signed, not notarized): the first time, right-click
  the app and choose Open on macOS, or More info, Run anyway on Windows.
- **Episode Creator:** `shshd-runtime-creator-<version>-<platform>` archives, for the platforms whose build passed.
  Its first launch is the same as the player's.
- **Android:** `shshd-runtime-<version>-android.apk`, for Android 7.0 or newer. Sideload it; it isn't on the Play
  Store. It installs over v1.1.0 and keeps your data.
- **iOS:** `shshd-runtime-<version>-ios-arm64-unsigned.ipa`. It's unsigned: sign it with your own Apple ID
  or a signing tool before installing.

Each download has a SHA-256 checksum beside it.

See CHANGELOG.md for the full list of changes.
