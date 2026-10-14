# Contributing to EXP Runtime

EXP Runtime is an experimental compatible engine for Surviving High School
and Cause of Death.
It executes original KiWi bytecode and imports resources from each player's
SHS APK/IPA or CoD IPA and EXP episodes. The goal is to reproduce the original
gameplay and interface. It is not an ARM recompilation or a Ren'Py conversion.

Code, tests, documentation, compatibility reports and platform verification
are useful contributions. You can install, test and build the project without
owning any game files.

## Getting started

Fork the repository, clone your fork and create a branch for your change.
Install uv and run these commands from the repository root:

```sh
uv sync --locked --extra desktop
uv run --locked --extra desktop python -m unittest discover -s tests
uv run --locked --extra desktop exp-runtime
```

The project supports Python 3.10 or newer; CI uses Python 3.14. The launcher
opens a game chooser; each game has its own content setup. Playing an episode requires
your own game files, imported locally through the app.

Read [DEVELOPMENT.md](docs/DEVELOPMENT.md) for the module map, diagnostic tools
and optional content checks. [RUNTIME.md](docs/RUNTIME.md) and
[ENGINE_ABI.md](docs/ENGINE_ABI.md) describe current support and known gaps.
For a larger change, an issue describing the problem and proposed behavior
helps coordinate the work before implementation.

## Running unit tests

Tests use Python's built-in `unittest` runner. Run the commands below from the
repository root. uv manages the virtual environment; manual activation is not
needed. Install the desktop extra so the pygame tests can run too.

Install dependencies and run the full suite with individual test results:

```sh
uv sync --locked --extra desktop
uv run --locked --extra desktop python -m unittest discover -s tests -v
```

Run one test file, for example the VM tests:

```sh
uv run --locked --extra desktop python -m unittest discover -s tests -p "test_vm.py" -v
```

Run one test method within that file:

```sh
uv run --locked --extra desktop python -m unittest discover -s tests -p "test_vm.py" -k test_pause_and_budget_are_resumable -v
```

Replace the filename and method name to select other tests. `-k` matches a
substring of the test name, so use a unique name when selecting a single test.
Keep `discover -s tests` in these commands so imports of shared test helpers
resolve correctly. Add `-f` to stop at the first failure; omit `-v` for compact
output.

No APK or EXP files are required for the authored tests. Optional checks
against local game content skip when those files are absent, and some tests
skip on unsupported platforms. Verbose output includes each skip reason.
A successful run ends with `OK` or `OK (skipped=...)`; `FAIL` and `ERROR` need
investigation. If a filtered run reports zero tests, check the filename,
method name and working directory.

CI runs the same suite with the `build` extra, which also includes the desktop
dependencies. Report the command, failures and relevant skips when sharing
test results. Keep original game content out of test fixtures and reports.

### Testing with your own game files

The optional original-content tests currently look at fixed paths in the
repository. Importing through the app's normal setup may create a library in
your application-data directory instead; the tests do not discover it there.
Run the following steps from the repository root.

Copy your **SHS Android 1.0.9 APK** into the repository root and name that copy
**`surviving-high-school-1-0-9.apk`**. Keep it as an APK file. The font and UI
asset tests read this exact filename directly; they do not use the APK in an
imported library. The filename requirement belongs to these tests, not the
app's file picker.

If you have additional episodes, put the EXP files in a local **`Episodes/`**
directory, retaining their original filenames. Include `shs_options.sav` there
if you have the original episode catalog. Additional episodes are optional;
the APK contains bundled stories used by many of the checks.

Create the local test library with this command:

```sh
uv run --locked exp-tool import --apk surviving-high-school-1-0-9.apk --library .shs-library
```

To include `Episodes/` during this initial import, append **`--episodes Episodes`**
to that command. The importer creates `.shs-library/` and its `content/` files;
do not create an empty library directory beforehand. It preserves the source
files and refuses to overwrite an existing library.

If `.shs-library/` already contains a compatible library, reuse it. To add
episodes later, open that specific library and use **Options → Add Episodes**:

```sh
uv run --locked --extra desktop shs --library .shs-library
```

Check the imported episode list, then run the tests:

```sh
uv run --locked exp-tool list --library .shs-library
uv run --locked --extra desktop python -m unittest discover -s tests -v
```

These are the inputs expected by the optional checks. All paths are relative
to the repository root:

| Local input | Checks it enables |
| --- | --- |
| `surviving-high-school-1-0-9.apk` | Original font descriptors, layouts, skins and portrait masks. |
| `.shs-library/library.json` and its `content/` directory | Bundled-story execution, rendering, menu, save/load and mini-game checks. Created by the import command above. |
| `Episodes/Big_Man_On_Campus.exp` plus the local library | The additional football-script check. |
| Homecoming Queen imported into the local library | The character-selection story checks; these skip if that episode is absent. |
| `Episodes/shs_options.sav` plus the local library | Catalog coverage and the season boundary check. This requires the matching episodes with pack/episode IDs `(301, 57)` and `(301, 58)` to be imported too. |
| `extract/assets/Assets/The_New_Girl.exp` | One legacy initialization/trace check that reads a standalone EXP. |

To enable that last check, extract only its member from your APK:

```sh
uv run --locked python -c "from zipfile import ZipFile; apk = ZipFile('surviving-high-school-1-0-9.apk'); apk.extract('assets/Assets/The_New_Girl.exp', 'extract'); apk.close()"
```

Supplying the APK alone does not enable every check. Missing optional inputs
leave their checks skipped. The catalog test currently guards only the catalog
and library paths; it will fail if the required season-boundary episodes are
missing from a partial collection. Use verbose output to identify each check
and its requirements.

These local paths are ignored by Git and excluded from packages. Keep the
originals and imported content local; do not force-add them to a commit or
upload them with test reports. GitHub CI uses authored fixtures and skips
checks requiring original game files.

## Reporting problems

Include enough information for someone with their own game files to reproduce
the problem:

- The runtime version or commit, operating system and CPU architecture.
- The episode name or ID, steps taken, and expected versus actual behavior.
- For an unsupported service, the scene ID, service code and program counter
  shown by the runtime.
- Whether the problem occurs from a new session, after loading a save, or
  both, and any relevant checks you have already tried.

Review diagnostics before posting. Remove game dialogue, personal paths and
player data. Describe a visual mismatch in words; keep original screenshots,
game files, libraries and saves out of public issues and pull requests.

## Compatibility and evidence

Use the authored specifications as the starting point:

- [SCHEMA.md](docs/SCHEMA.md) covers EXP containers and resource formats.
- [VM_SPEC.md](docs/VM_SPEC.md) covers KiWi bytecode and execution.
- [ENGINE_ABI.md](docs/ENGINE_ABI.md) covers host services and callbacks.
- [UI_ASSETS.md](docs/UI_ASSETS.md) and [UI_FIDELITY.md](docs/UI_FIDELITY.md)
  cover native assets, layout and presentation.

Android 1.0.9 is the available reference for the reported identical iOS and
Android interfaces. Record the binary identity and native function addresses
when documenting newly recovered behavior. Explain the observed contract in
your own words, distinguish observations from inferences, and leave remaining
uncertainties explicit. [PROVENANCE.md](docs/PROVENANCE.md) explains the existing
evidence references; private research files are not dependencies of this repo.

Preserve these contracts when changing the implementation:

- Unknown services remain explicit stops with their pending arguments intact.
  Do not invent results, scores, scene links or random values to advance them.
- The VM and session state own script-visible behavior. Preserve argument
  frames, callbacks, input gates, clocks and random streams across pauses,
  scene changes and save/load. Rendering must not silently complete actions.
- Recover presentation with behavior: original positions, font metrics,
  portrait masking, pagination, panel lifecycle and animation timing matter.
- Preserve exact resource IDs, the separation of APK and episode resource
  banks, relocatable libraries and versioned saves. Document any schema change
  and how existing data is handled.

Update the relevant specification alongside a behavior change. A synthetic
test or a working opening scene establishes only the behavior exercised;
describe full-episode or visual equivalence as unverified until checked.

## Game content and licensing

Keep original APKs, EXPs, extracted art, audio, fonts and scripts, native
decompilations, screenshots, generated games, player libraries and saves out
of contributions and distributed packages. Generated traces and audit reports
can contain original dialogue and player data; keep them local too.

Use authored, synthetic fixtures for regression tests. Optional checks against
your own content may skip when that content is absent. Do not make ordinary
tests or builds depend on the old research checkout, Ghidra or game downloads.

Keep [MANIFEST.in](MANIFEST.in) and Python package discovery restrictive when
adding files or dependencies. Preserve the inherited [MIT license](LICENSE)
and attribution documented in [PROVENANCE.md](docs/PROVENANCE.md).

## Verification and pull requests

Keep a pull request focused on a concrete problem. For behavior fixes, add a
meaningful regression test using authored inputs where practical, and run the
full suite described in [Running unit tests](#running-unit-tests).
Optional original-content skips are expected in a clean
checkout; mention any local content checks separately.

For changes to packaging, dependencies or application startup, also build and
test the extracted download on your platform:

```sh
uv run --locked --extra build python tools/build_desktop.py
uv run --locked --extra build python tools/package_desktop.py --label local --smoke-test
```

CI runs the tests and extracted-app startup checks on Windows x64, Linux x64,
macOS Apple Silicon and Intel. Passing those checks does not verify full
gameplay on each platform. See [DISTRIBUTION.md](docs/DISTRIBUTION.md) for
download packaging and release behavior.

In the pull request description, explain the problem, resulting behavior,
evidence used, verification performed and remaining uncertainties. Update
[CHANGELOG.md](CHANGELOG.md) under **Unreleased** for user-visible changes.
If dependencies change, update `pyproject.toml` and `uv.lock` together and
explain why the dependency is needed. Do not include generated build output.

## Release maintenance

The repository owner handles merges, version tags and publication. Before a
release, update the root [RELEASE.md](RELEASE.md), which supplies the GitHub
release body, and move the relevant changelog entries into a versioned section
with the release date. Keep the root and all five component `pyproject.toml`
versions and exact component dependency pins, `uv.lock`, both Xcode
`MARKETING_VERSION` settings in `ios/EXPRuntime.xcodeproj/project.pbxproj`, and
the intended release tag consistent. The macOS bundle and command-line iOS
build read the package version; direct Xcode builds use the project settings.
The workflow publishes app downloads to GitHub Releases and all six Python
distributions to PyPI after all four desktop builds, iOS verification and
isolated Python package checks pass for a pushed version tag. The tag must
equal `v` plus the common package version. Ordinary pushes, pull requests
and manual runs produce development artifacts without publishing.

Build and audit the Python distributions with `tools/build_packages.py`, then
run `tools/test_packages.py` through the locked build environment. These check
real pip installs of tools, engine, single-game and full-player combinations.
All six distributions are one release; the scripts never publish them.
See [SDK.md](docs/SDK.md) for local wheel installation and component boundaries.
Before the first PyPI release, register all six projects with the
[`desktop-builds.yml` Trusted Publisher and `pypi` environment](docs/DISTRIBUTION.md#pypi-publishing).
The publish job uses short-lived OIDC credentials, not a stored API token.
PyPI rejects existing filenames; rerun only failed jobs after a successful
upload and use a new version for changed packages.
