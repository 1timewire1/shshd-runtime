# SHSHD Runtime Creator

Optional visual desktop editor for new SHS and CoD episodes, from exp-runtime v0.6.0 (Josh Mcdaniel's EXP Runtime
Creator), packaged under this fork's names. Author dialogue, choices, branches, characters, audio, minigames and
translations, save portable projects and export native CSPUD/KiWi EXP files for SHSHD Runtime and the original
games. Original-slot export preserves an existing episode's catalog IDs. Native KiWi loader/VM checks pass for SHS
Android, SHS iOS and CoD iOS; full original-app playback remains unverified.

Install the desktop editor from a source checkout, then launch it:

```sh
python -m pip install './packages/creator[desktop]'
shshd-creator
```

This fork's releases do not include standalone Creator downloads.

The Python authoring API needs only `shshd-runtime-formats`. The `desktop` extra
adds Qt, the shared player and both game adapters. No game assets are included.
Preview uses an imported game library and temporary saves. The independent
`mcp` extra adds a stdio server, production playtesting and isolated player
rendering/audio previews. It includes pygame but does not install Qt.
Run `shshd-creator-mcp --workspace /path/to/stories`.

Install both extras with `python -m pip install './packages/creator[desktop,mcp]'`
to use the editor and MCP server together.

Open a saved workspace project in the desktop creator to share live edits with
an MCP client. Models see unsaved work, their edits appear immediately, and
desktop undo/redo covers both. Save in the editor to write the shared project.

See the project README and `docs/CREATOR.md` in the source repository.
