# EXP Runtime Creator

Optional visual desktop editor for new SHS and CoD episodes. Author dialogue,
choices and branches, save portable projects and export native CSPUD/KiWi EXP
files for EXP Runtime and the original games. Original-slot export preserves
an existing episode's catalog IDs. Native KiWi loader/VM checks pass for SHS
Android, SHS iOS and CoD iOS; full original-app playback remains unverified.

The Python authoring API needs only `exp-runtime-formats`. The `desktop` extra
adds Qt, the shared player and both game adapters. No game assets are included.
Preview uses an imported game library and temporary saves.

See the project README and `docs/CREATOR.md` in the source repository.
