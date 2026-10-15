# Unreleased

## Added

- Support compact and multilingual free CoD IPA asset layouts, detected by
  validating their resources. Existing compact-free libraries remain readable.

## Changed

- Allow spaces in CoD text entry on desktop and iOS as an intentional
  convenience beyond the original keyboard's filter.

## Fixed

- Substitute undefined `0x09`, `0x18` and `0x19` dialogue glyphs with readable
  spaces/apostrophes while preserving explicitly defined font glyphs.
- Handle CoD's observed `-1` and `1000` timed-choice defaults with a documented
  compatibility fallback. SHS and unrecognized invalid defaults still stop.
- Preserve CoD text-entry case after capitalizing an initial lowercase letter,
  matching the inspected native input path.

# v0.5.0

## Added

- Split EXP Runtime into formats, engine, player, SHS and CoD component wheels
  within one project and shared `exp_runtime` namespace. Pip extras select
  only the required source and dependencies; the player/desktop extras
  include both games by default. Existing source development commands and
  import paths remain supported.

## Changed

- A bare Python package install now provides file tools. Use `[engine,shs]`
  or `[engine,cod]` for headless playback and `[player]` or `[desktop]` for
  the app. Game discovery, minigame state restoration and app builders support
  the component layout without changing library or save formats.
