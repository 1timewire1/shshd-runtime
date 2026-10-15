# v0.6.0

## Added

- Add an optional desktop episode creator with a visual story graph, dialogue,
  timed choices, variables and conditional branches, undo/redo, editable
  projects and native EXP export for EXP Runtime and the original games.
- Add creator music/SFX controls, reusable characters and expressions,
  relationships/properties, arithmetic and conditional answers, text puzzles,
  title/presentation nodes, native minigame authoring and multiple scenes.
- Add translations, reversible authored EXP import, lossless original EXP block
  editing, autosave/recovery, graph editing/search/layout and a production-VM
  debugger. Preview can restart automatically after edits.
- Use native episode exits and the existing game menu/episode picker for
  creator endings. Preserve closing messages when opening earlier unreleased
  next-episode nodes.
- Build separate creator downloads for Windows, Linux, Apple Silicon and Intel
  macOS, include them in the release files, and expose an optional stdio MCP
  server for project editing, asset import, native export and debugging.
- Share open creator projects with MCP: models read unsaved desktop work and
  apply live transactions through the editor's undo/redo history. Recheck
  revisions to preserve concurrent edits, retain recovery copies, and guard
  saves against external file changes.
- Add atomic MCP edit batches, checkpoint undo, focused graph queries,
  per-node schemas, structured diagnostics and repeatable playtest scenarios.
  Browse image/audio metadata and previews, and capture screenshots through
  the shared player. Use consistent tool names and bounded, recoverable results.
- Export a separate replacement for an existing original-game episode slot,
  preserving its catalog IDs. Validate compiled scripts against the original
  SHS Android, SHS iOS and CoD iOS KiWi loaders/interpreters; full original-app
  playback remains unverified.
- Browse images from imported SHS/CoD libraries or embed custom PNG/JPEG
  images. Keep base-game references separate from portable episode assets.
  Automatically use the player's matching library in the desktop creator,
  preserving saved project selections. Preview with the shared player and
  temporary saves.
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

Download `exp-runtime-creator-v0.6.0-<target>.zip` (`.tar.gz` for Linux) and open
**EXP Runtime Creator**, or install `exp-runtime[creator]>=0.6.0` with pip and
run `exp-creator`. The release also includes the desktop player, unsigned iOS
IPA, all seven Python wheels and their SHA-256 checksums.

For MCP, install `exp-runtime[creator-mcp]>=0.6.0` and run
`exp-creator-mcp --workspace /path/to/stories`. Both extras can be installed
together for live desktop/model editing.

Run the editor from source with `uv run --locked --extra creator exp-creator`.
See [the creator guide](docs/CREATOR.md) for original-app installation and
verification limits. No game assets are included.
