# EXP Runtime — engine

Headless KiWi VM, sessions, content libraries and saves. This is a component of the single
[EXP Runtime project](https://github.com/joshrmcdaniel/exp-runtime), maintained
and released together with its other wheels. Python imports use the shared
`exp_runtime` namespace.

Install `exp-runtime[tools]` for file tools, `exp-runtime[engine,shs]` or
`exp-runtime[engine,cod]` for a headless game, or `exp-runtime[player]` for
the desktop player with both games. Individual component wheels also support
selective installs. See the project's `docs/SDK.md` for APIs and examples.

No original game content is included. Users supply their own game files.
The inherited MIT license and attribution are included in LICENSE; see
[provenance](https://github.com/joshrmcdaniel/exp-runtime/blob/main/docs/PROVENANCE.md).
