# EXP Runtime Creator

Optional visual desktop editor for new SHS and CoD episodes. Author dialogue,
choices, branches, characters, audio, minigames and translations, save portable projects and export native CSPUD/KiWi EXP
files for EXP Runtime and the original games. Original-slot export preserves
an existing episode's catalog IDs. Native KiWi loader/VM checks pass for SHS
Android, SHS iOS and CoD iOS; full original-app playback remains unverified.

Install the desktop editor with pip, then launch it:

```sh
python -m pip install 'exp-runtime-creator[desktop]>=0.6.0'
exp-creator
```

Standalone Creator downloads are also included in the v0.6.0 GitHub release
for Windows, Linux and macOS (Apple Silicon and Intel).

The Python authoring API needs only `exp-runtime-formats`. The `desktop` extra
adds Qt, the shared player and both game adapters. No game assets are included.
Preview uses an imported game library and temporary saves. The independent
`mcp` extra adds a stdio server, production playtesting and isolated player
rendering/audio previews. It includes pygame but does not install Qt.
Run `exp-creator-mcp --workspace /path/to/stories`.

Install both extras with `python -m pip install 'exp-runtime-creator[desktop,mcp]>=0.6.0'`
to use the editor and MCP server together.

Open a saved workspace project in the desktop creator to share live edits with
an MCP client. Models see unsaved work, their edits appear immediately, and
desktop undo/redo covers both. Save in the editor to write the shared project.

See the project README and `docs/CREATOR.md` in the source repository.
