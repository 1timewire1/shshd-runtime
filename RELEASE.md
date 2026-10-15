# SHSHD Runtime v1.0.0

The first release of SHSHD Runtime, a fork of
[exp-runtime](https://github.com/joshrmcdaniel/exp-runtime) that plays
Surviving High School (including its iPad HD release) and Cause of Death with
your own game files. It is a separate app: its own data folder, window and app
identifiers, so it never touches an installed copy of exp-runtime.

No game files are included. You supply your own.

## Highlights

- **Surviving High School HD.** With the SHS HD (iPad) IPA beside the Android
  1.0.9 APK, the app uses SHS HD's own screens, ported from the original app:
  the launch flow, main menu, episode grid and lists, dialogue, choices,
  mini-games, side panels, the Decision Tree and Faceplace.
- **HD art for standard episodes,** where a matching HD picture exists.
- **Cause of Death in SHS HD's presentation,** with CoD's own styling, categories
  and airdates. Linking the SHS HD IPA gives CoD its HD look too.
- **Switch Game** moves between the two games from the main menu.
- **Bulk Import.** On first boot, one ZIP or RAR (or an `import` folder beside
  the app) sets up both games at once. See the README for the layout.
- **Episode info for Cause of Death,** with each episode's store description and
  price, from a 1.4.7 device backup's store listing (`mtxprods`).
- **Update check** against this project's releases (Options → General).

## Downloads

- **Windows, macOS, Linux:** `shshd-runtime-<version>-<platform>` archives. Unzip
  and run SHSHD Runtime. Builds are unsigned (macOS: ad-hoc signed, not notarized).
- **iOS:** not available. This fork's HD screens draw with pygame directly,
  which the iOS app does not include, and they still need porting to its
  native drawing layer. The iOS build fails on launch in CI; see
  docs/IOS_APP.md. The port is planned after this release.

Each download has a SHA-256 checksum beside it.

See CHANGELOG.md for the full list of changes.
