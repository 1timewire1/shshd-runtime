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
