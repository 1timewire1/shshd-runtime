# v0.6.1

## Added

- Add Options → Cheats → Minigame skips. Before each football, word-grid or
  word-selection minigame, offer Skip with success, Skip with failure, or Play
  minigame while holding its timer. Keep skips available in the pause menu;
  save the Play decision for that game. Ordinary timed story choices are excluded.
  The prompt uses the Answer hints green/red rows for success/failure and a
  neutral Play row, including feedback while pressed.
- Show faint answers in empty CoD puzzle-entry fields when Cheats → Answer
  hints is enabled. Discover accepted spellings from isolated script previews;
  preserve defaults, typed text and explicit submission, and leave uncertain
  answers and ordinary name fields unhinted.

## Fixed

- Correct CoD's narration and score-notification colors: black narration and
  neutral/gray notices, with the original red/rose notice variants selected
  by dialogue theme. Preserve SHS's palette.
- Restore native IPA dialogue typography in both games: fixed-size character
  names in their original headers, italic emphasis with its own spacing and
  fine outline, and the original text colors. Keep substitute-font fitting and
  reflow older IPA checkpoints without replaying story commands.
- Restore the loading runner's original 70 ms frame timing for IPA imports;
  keep APK timing, the loading wait and saved progress intact.
- Keep every choice on screen without scrolling. Reposition tall quiz panels
  above the footer before reducing text; reflow oversized choices while
  preserving all answers, disabled states and timer space in both games.
- Preserve portrait-expression fades across consecutive lines and settle active
  layers when pausing IPA playback. Correct both iOS games' full-opacity flash
  and SHS IPA's pulse/fade timing; keep overlapping decorations independent.
- Deliver script vibration requests on iPhone using the original iOS system
  alert, with a persistent Vibration switch independent of Music and Sound.
  Drop inactive requests and never replay vibration from saves or choice hints.
- Recognize CoD's correct/wrong choice cues in optional hints, including
  Volume Two's death/restart branch. Preview across native pause/loading
  boundaries and local survey receipts without changing the live session.
- Restore ordinary choices' 250 ms input gate and IPA fade, including saved
  entrance progress and creator playtests that honor short timer expiries.
- Share native footer strings, font roles and anchors across story panels;
  restore Android's choice-heading spacing repairs without changing scripts.
- Decode sprite-atlas frames with distinct logical/stored sizes and their
  native transforms, separate from ImagePack's transform convention.
- Restore native portrait decorations for expressions 6–9, including each
  game's flash timing and layer order, without changing dialogue geometry.
- Fade CoD music changes and stops using the native durations; repeated
  requests cancel an outgoing fade or restart a finished cue. Host checkpoints
  retain the actual playhead and outgoing fade; iOS repeat changes keep the
  same playing audio object.
- Restore IPA pause/menu audio handoffs for both games: save story music and
  effects before their 1000/100 ms fades, wait for menu audio to stop, then
  resume the saved playheads. Background checkpoints retain active effects.
- Restore story-choice clicks and CoD's timed-word answer sounds. Preserve
  ordered sound requests when a choice immediately dispatches script cues.
- Restore CoD's scene blinds and black fades, including delayed callbacks,
  input locks, title-screen exceptions, menu-to-story entry and a separate
  saved random stream. Preserve SHS's nonvisual callback tick boundary.
- Keep random streams and speaker-font banks across episodes in the same
  application process, with explicit save loads restoring saved state.
- Preserve Android bitmap kerning history across story labels, including
  choices, word-game scores, messages, loading, name entry and the appearance
  picker. Follow native text-assignment order without changing state on redraw;
  choice-title measurements now affect subsequent speaker-font layout.
- Preserve suppressed Android relationship icons at their last visible poses,
  including interrupted effects and dialogue/scene handoffs. Keep the iOS
  games' explicit clearing behavior and Android's character-45 exception.
- Apply SHS background 1013's native 1% width correction around its pan center.
- Restore main-menu info/gear entrances and departures; add the recovered
  Android pause tint, iOS sepia capture, closing animation and submenu transitions.
  APK submenus zoom/slide over the departing main rows instead of waiting
  for them; the underlying strip completes its native departure afterward.
- Use alternate choice headers and signed text insets for right-side portraits;
  correct IPA name-entry cursor placement and appearance-picker pressed art.
- Animate SHS grid points flying from the selected tile into the score
  counter, and restore the Android reference's portrait-ring pulse.
- Dim grid highlights and selected tiles with the native round countdown;
  retain the shuffled start offsets and their gameplay random draws.
- Preserve native per-tile flip/pop/shine clocks, including delay-boundary
  behavior, and defer board generation until a shrinking board has left.
- Match fragment float32 arithmetic and depth-test intersecting grid faces.
- Restore football's home-touchdown stars and their 450 native random draws,
  retained target shadows and final-score sound staging. Restore iOS grid and
  football exit overlays while freezing completed minigame clocks.
  Save version 26 retains the new effects, bitmap/widget history, choice entrance and expression layers; older
  saves preserve their story and random state without inventing missing history.
- Keep CoD relationship effects usable when only the CoD component is installed.
