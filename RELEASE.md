# Unreleased

## Added

- Add an optional desktop episode creator with a visual story graph, dialogue,
  timed choices, variables and conditional branches, undo/redo, editable
  projects and native EXP export for EXP Runtime and the original games.
- Export a separate replacement for an existing original-game episode slot,
  preserving its catalog IDs. Validate compiled scripts against the original
  SHS Android, SHS iOS and CoD iOS KiWi loaders/interpreters; full original-app
  playback remains unverified.
- Browse images from imported SHS/CoD libraries or embed custom PNG/JPEG
  images. Keep base-game references separate from portable episode assets.
  Preview with the shared player and temporary saves.
- Add the `exp-runtime-creator` component and `[creator]` extra, plus a
  headless authoring API and deterministic native EXP/metadata writers.
  Keep the editor and its optional Qt dependency out of player/iOS bundles.
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

Run from source with `uv run --locked --extra creator exp-creator`.
See [the creator guide](docs/CREATOR.md) for original-app installation and
verification limits. No game assets are included.
