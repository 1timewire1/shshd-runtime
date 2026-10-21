# SHSHD Runtime v1.0.2

**This release merges upstream exp-runtime v0.6.1, reworks scene transitions
from SHS HD's own code, adds new options, and fixes a batch of reported bugs.**
Your libraries and saves from v1.0.x carry over: no re-import needed.

## What's new

- **Keyboard navigation** (by zazatree) in choices, the pause menu, the main
  menu and its windows, the episode pickers and the portrait picker.
- **Menu animations** (by zazatree): menus zoom and slide with the original's
  timing, and CoD's main menu fades in from black at launch.
- **Simulated Vibration Sound** (by zazatree, Options → Sound): a short buzz
  where a story asks the iPhone to vibrate. Off by default.
- **Options → Extras**, a new category for the play aids: **Disable Choice
  Timer** (new: timed choices wait, with a "Let the Timer Run Out" row), Choice
  Hints and Ask to Skip Mini-Games (now also covering the word quizzes, in
  Cause of Death too).
- **Autoplay Dialogue** (Options → General): dialogue advances by itself
  0.75 s after its text is out. Choices and mini-games still wait for you.
- **Scene transitions** follow SHS HD's own code: the blinds close over the old
  screen, and title cards appear without a fade-in.
- **Cause of Death's emphasised words** use the game's own italic switch font.
- **Upstream exp-runtime v0.6.1**, including the optional episode creator
  (`shshd-runtime-creator`) and Cause of Death free-edition support.

## Fixes

- Music fades and interface sounds match the originals.
- The "Score Up!" letters no longer vanish when you tap through a line.
- The portrait ring no longer runs over the text after a fast tap.
- The Continue button comes when the page's text is out, not after unseen pages.
- A two-line speaker name no longer overflows the box (#11).
- The relationship badge's flourish on your own portrait sweeps to its slot
  instead of snapping (#7).
- Episodes that open on no background show black (#8).
- Cause of Death: typed answers capitalize their first letter; the pressed gear
  uses CoD's own art.
- Letter spacing of the scene caption and the Decision Tree's labels matches
  the originals.
- Previews for more episodes, including CoD's Sunset and Fourth of July
  Special, Part 2.

---

SHSHD Runtime is a fork of
[exp-runtime](https://github.com/joshrmcdaniel/exp-runtime) that plays
Surviving High School (including its iPad HD release) and Cause of Death with
your own game files. It is a separate app: its own data folder, window and app
identifiers, so it never touches an installed copy of exp-runtime.

No game files are included. You supply your own.

## Downloads

- **Windows, macOS, Linux:** `shshd-runtime-<version>-<platform>` archives. Unzip
  and run SHSHD Runtime. Builds are unsigned (macOS: ad-hoc signed, not notarized).
- **iOS:** not available. This fork's HD screens draw with pygame directly,
  which the iOS app does not include, and they still need porting to its
  native drawing layer. See docs/IOS_APP.md.

Each download has a SHA-256 checksum beside it.

See CHANGELOG.md for the full list of changes.
