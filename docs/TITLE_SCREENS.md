# Episode introductions and week cards

Service 8 draws both episode introductions and Football Star's week cards.
The original script supplies the title, subtitle and background for each call;
the runtime does not generate week counts or substitute an episode-list title.
This contract comes from Android 1.0.9 `libshs09.so`, identified in
[PROVENANCE.md](PROVENANCE.md). It describes the ordinary local title screen;
Android advertising and promotional branches remain outside the implementation.

## Service and callback

```text
service   : 8 (0x08), native UI type 0x10
arguments : title_ref:s16, subtitle_ref:s16, asset_id:s16, flag:s16
title     : "" if title_ref < 0, otherwise T(title_ref)
subtitle  : T(subtitle_ref)
stop      : presentation; VM argument frame stays pending
callback  : R = 0 after an accepted acknowledgement
```

`T` resolves the host's packed/dynamic byte strings and applies replacement
strings; see [ENGINE_ABI.md](ENGINE_ABI.md#1-shared-calling-convention-and-notation).
Every negative title reference means an empty title on this path. It must not
be read as a VM memory address. The subtitle uses the normal resolver.

`FUN_0009fa3c` selects this screen, `FUN_000a6ec0` constructs it and
`FUN_000a7758` supplies the strings and numeric fields. A negative title or the
literal first-week title selects additional Android promotional code in the
factory; it does not define a different week-card layout. The local renderer
uses the shared title implementation for every service-8 call.

Accepted input reaches `FUN_000ab8b8` / `FUN_0007efe8`. If the queued scene
transition selector is 20, the native path consumes one `lrand48` draw before
choosing a transition. The runtime preserves this draw, clears `scene_value`,
and resumes through callback `FUN_000a6448` with zero. It does not write a UI
result cell. Message service 33 and dialogue services 13/65/76 share this
completion path. Transition visuals are
drawn by `desktop_transition.py`; early taps, redraws and save restoration do not consume
that random draw or complete the call.

## Assets and coordinates

The logical canvas is 320 × 480. Positions below use a top-left origin unless
marked GL. `FUN_000a70b4` creates individual scene nodes; it does not draw every
element in layout 48 as a generic panel.

| Element | Original resources and geometry |
| --- | --- |
| Background | Exact `asset_id`, scaled independently in X/Y to 320 × 480, centered at GL `(160,240)` |
| Title | PNG 528, external glyph descriptor 529; layout 48 node 9; content width 380, left aligned, node scale 0.85 |
| Subtitle | PNG 530, external glyph descriptor 531; layout 48 node 10; content width 320, right aligned, node scale X=1 |
| Footer | Shared pack 126 frame 47 at `(0,431)`; gear frame 49 at `(0,408)` |
| Continue hint | APK string bank 13 entry 36; font registry 11 (`ArialMT14`), nominal size 14, line gap 8, white, center/center flags `0x0a`, zero content size, node origin `(180,455)` |

The title font pairs contain ordinary PNG images and external glyph metrics,
not embedded ABGR sprite packs or the dialogue's Pajama Hip font. Descriptor
529 has glyph height 33, space width 13, tracking -3 and line gap 1; descriptor
531 has height 23, space width 7, tracking -2 and line gap 1. The parser uses the
six-byte header and glyph records described in
[MINIGAMES.md](MINIGAMES.md#6-sprite-atlas-and-glyph-font-payload-schemas), including the existing byte
fallback, spacing and wrapping rules.

The nodes retain their default zero anchors. For title rectangle `r9` and
subtitle rectangle `r10`:

```text
title_origin   = (r9.x - 10, floor(r9.height / 2) - 10)
subtitle_GL_y = r10.y - floor(r10.height / 2)
if byte_length(subtitle) < 100:
    subtitle_GL_y -= 75
subtitle_origin = (0, 480 - subtitle_GL_y)
```

The available APK gives title origin `(0,90)` and subtitle origin `(0,405)`;
subtitles at least 100 bytes long instead use `(0,330)`. These are node origins,
not glyph top-left corners. Layout-node widths 305/293 do not replace the
explicit native text widths 380/320.

`FUN_00054148` / `FUN_00054490` wrap each byte string. Title uses flags `0x11`,
subtitle `0x13`. The title panel sets host flag `+0x6ac43`, causing successive
rows to decrease the local GL pen Y by `font.height + font.line_gap`. A glyph
at `(pen_x,pen_y)` has downward local top-left `(pen_x,-pen_y-font.height)`;
`FUN_0005373c` constructs the corresponding centered sprite. Right alignment
starts each subtitle row at `320 - measured_row_width`.

For subtitles of 25–99 bytes with the original 23-pixel font, `00054490`
also adjusts local Y before each drawable glyph: Y at least `height-2`
becomes 3; otherwise Y=0 becomes `height-4` (19). This raises the first row,
then later rows continue downward. At 100 bytes the fitting adjustment is
disabled and the subtitle node moves 75 pixels up. The title's 33-pixel font
does not take the separate larger-font branch in that routine.

`FUN_0007d280`, `FUN_0007cbbc` and `FUN_0007d4c8` establish the shared footer
art, centered hint font and string. The title renderer shows this footer and
the gear, without a desktop title bar or rectangular Continue button. The gear
opens the runtime pause menu; the rest of the screen acknowledges the title.

The setup also calls `FUN_0007d6a4` with the asset/flag pair to configure a
shared menu background. That helper can select adjacent background variants
or a time-dependent variant. The title's own sprite is still loaded from the
base asset by `FUN_000a6aa4`. The runtime retains the flag in the pending
request; it does not pretend that the shared menu-background lifetime and
all variant side effects have been recovered.

## Entrance and input gate

`FUN_000a70b4` installs independent animations:

| Element | First entrance |
| --- | --- |
| Background | Opacity zero for 1000 ms, then a linear fade to full opacity over 3000 ms |
| Title | Horizontal reveal from screen X=0; clip width starts at zero and increases by 5 logical pixels per update, capped at 320 |
| Subtitle | Scale Y=0.5 for 500 ms, then linear scale to 1 over 500 ms, keeping its node origin fixed |

`FUN_000a65b4` applies the title's scissor rectangle for that node only. The
subtitle and background have their own animation clocks; completing the wipe
does not finish their animations. The canvas behind a transparent background
is black. Once visible, the screen stays until accepted input.

`FUN_000a650c` tests whether the **previous** clip width exceeds 240 before
adding five. At the runtime's 30 Hz logical update cadence the gate opens on
tick 50 (1667 ms), while the wipe completes on tick 64 (2134 ms). The 60 Hz
desktop redraw loop does not change this step count. As with dialogue, this
uses the recovered application cadence rather than a timing measurement from
a recording of the original app.

`FUN_000a6800` handles an early tap by setting clip width to 320 and returning
without acknowledging. The following logical update opens the gate. A later
tap resumes the VM, even if the background fade is still running. Queued input
is bounded by the desktop's existing screen-change guard. Enter and Space use
the same acknowledgement path as a pointer tap.

The session owns these clocks. Menu pause and focus loss freeze them; rendering
and resizing never advance the VM or animation. Native panel reconstruction
(`FUN_000a7898` / `FUN_000a792c`) can rebuild a settled title without replaying
the entrance. The desktop keeps the live screen and its clocks while paused;
it does not reproduce every Android application reconstruction branch.

## Save schema, version 11

The engine adds `title_screen`, required exactly while `pending.name` is
`presentation`, and null otherwise:

```text
TitleScreen {
    elapsed_ms:   integer 0..4000,   // active entrance time, capped once settled
    reveal_width: integer 0..320,    // logical scissor width
    ready:        boolean           // acknowledgement gate
}
pending.details {
    title:    Latin-1 string,
    subtitle: Latin-1 string,
    asset_id: s16,
    flag:     s16
}
```

Let `steps = floor(elapsed_ms * 30 / 1000)`. Width must be
`min(320,steps*5)` or the fast-reveal value 320. At 50 or more steps the gate
must be open; an open gate requires at least one step and width greater than
245. Fast reveal can leave width 320 with a closed gate until the next update.
The saved strings and numeric fields must match the retained service-8 frame
and current host substitutions.

Versions 1–10 have no entrance history. A pending title migrates to
`{elapsed_ms:4000, reveal_width:320, ready:true}`, preserving its previous
readable, immediately acknowledgeable state. Other screens receive null.
Restoring version 11 retains the exact animation phase and gate without
replaying the VM, resetting timers or consuming random draws. See the full
[runtime save schema](RUNTIME.md#runtime-save-schema).

## Implementation and verification boundary

`title_screen.py` owns animation, input state and pure glyph placement.
`desktop_title.py` draws the supplied assets. `engine.py` resolves the frame;
`runtime.py` keeps it suspended, advances active time and performs completion.
The same path serves week cards and all episode title calls.

Authored tests cover both fonts, wrapped/right-aligned text, subtitle length
branches, negative title references, substitutions, clip/fade/scale geometry,
exact gate boundaries, clock partitioning, callback/result-cell behavior,
random draw timing, malformed saves and old-save migration. Optional checks
using a player's Football Star and The New Girl exercise actual assets,
mid-entrance save/restore pixels, window resize, pause and focus loss. No
original images, text fixtures, decompilations or saves are bundled.

A local audit rendered all 179 title cards reached at episode startup in the
available library at 500 ms and 4000 ms, then restored their saves, with no
failures. This included a 167-byte, multiline subtitle taking the long-text
branch. This is coverage of initial stops, not every later title in each story.

Native layout and state recovery do not establish complete pixel or timing
equivalence to a running original game. Original-device comparisons, Android
promotional overlays, device comparison of transition visuals, shared background lifetimes and
global input locks remain open. SDL texture filtering can also differ from
the native OpenGL renderer.
