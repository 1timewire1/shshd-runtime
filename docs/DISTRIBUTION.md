# Source distribution and local builds

EXP Runtime provides the compatible engine, KiWi interpreter, local asset
importer, authored specifications, tests and build tools. Each player supplies
an SHS Android 1.0.9 APK, compatible SHS IPA, or CoD IPA, plus additional EXP files. The original
ARM executable is inspected only to identify the supported APK profile; it is
not executed by the runtime. IPA import identifies the game by bundle identifier
and validates its required assets, independently of the version number.
System-font fallback and current limits are in [IPA.md](IPA.md) and [COD.md](COD.md).

## Downloads built by GitHub Actions

[Builds](../.github/workflows/desktop-builds.yml) runs on branch pushes,
pull requests, version tags beginning with `v`, and manual **Run workflow**
requests. It installs locked dependencies with uv and Python 3.14, runs the
tests without game content, builds the app, audits its bundle and tests the
extracted desktop download. It also calls the reusable
[iOS workflow](../.github/workflows/ios-builds.yml), which verifies the shared
engine and native presentation in a simulator before packaging the unsigned
device app. Third-party actions are pinned to verified commit hashes.

The Python packaging job builds all component wheels and source archives,
then checks isolated pip installs on Python 3.10 and 3.14. Its
`python-packages` Actions artifact contains the component distributions and their
checksums. Version-tag runs also publish these tested wheels and source
archives to PyPI after all checks pass. See [PyPI publishing](#pypi-publishing)
for the required one-time setup and [SDK.md](SDK.md) for component installs.

| Download target | GitHub runner | Archive |
| --- | --- | --- |
| `windows-x64` | `windows-2022` | ZIP containing the full executable directory |
| `linux-x64` | `ubuntu-22.04` | tar.gz preserving executable modes and links |
| `macos-arm64` | `macos-14` | ZIP containing the Apple Silicon app |
| `macos-x64` | `macos-15-intel` | ZIP containing the Intel app |
| `ios-arm64-unsigned` | `macos-26` | Unsigned IPA for users to sign and install |

After a successful run, development downloads are under **Actions → Builds
→ the run → Artifacts**, with one artifact per platform. Each contains
an app archive and its `.sha256` checksum; extract the outer artifact ZIP and
then the app archive (or sign the IPA). The simulator report is a separate
`ios-simulator-verification` artifact and is not a release download.
These artifacts expire after 30 days. GitHub requires
sign-in and repository read access for [Actions artifact downloads](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts).

The owner can publish a version by pushing a tag such as `v0.5.0`. The tag
must be exactly `v` followed by the version shared by all component `pyproject.toml`
files; a mismatch fails before building Python distributions. Once all
four desktop builds, the iOS build/verification and the Python packaging checks
pass, the release job
requires all five downloads and their checksum files, verifies the checksums,
and publishes the desktop archives plus the unsigned IPA and their checksums
on **Releases**. Ordinary pushes and pull requests
never create releases. Their jobs have read-only repository permissions; only
the version-tag release job has `contents: write`, using GitHub's built-in
token. No personal token or signing secrets are required.

The release body comes from [RELEASE.md](../RELEASE.md) at the repository root.
Update it before tagging a version. [CHANGELOG.md](../CHANGELOG.md) records
release history, with upcoming changes under **Unreleased**.

The prepared release notes describe the **unreleased episode creator**. Its
seventh distribution, `exp-runtime-creator`, is optional: existing player
downloads and the unsigned IPA do not include Qt or the editor. Register its
PyPI publisher before the next release. The owner has released v0.5.0 and has
not assigned a new version yet; bump all versions before publishing these changes.

Rerunning a version-tag workflow updates matching assets on an existing
release using `gh release upload --clobber`, then publishes any draft left by
an interrupted upload. If GitHub release immutability is enabled, publish a
new version tag instead. The workflow does not commit,
push code or create a tag; the release command requires the tag to exist.

Workflow changes take effect for tags containing the updated files. Local
validation does not replace a successful GitHub run on all five targets.

### PyPI publishing

The `publish-pypi` job runs only for pushed `v*` tags, after both Python
packaging jobs, all desktop builds and iOS verification succeed. It downloads
the same run's `python-packages` artifact, verifies every SHA-256 checksum and
stages only the component wheels and source archives. The publishing job does
not check out, build or install the project. Metadata validation and PyPI
attestations remain enabled in the pinned PyPA publishing action.

Before the first tag using this workflow, configure
[PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/adding-a-publisher/)
for **each** project: `exp-runtime`, `exp-runtime-formats`,
`exp-runtime-engine`, `exp-runtime-player`, `exp-runtime-shs`,
`exp-runtime-cod` and `exp-runtime-creator`. The creator is new since v0.5.0 and
needs its own publisher registration. Each registration uses the same values:

| Publisher field | Value |
| --- | --- |
| Owner | `joshrmcdaniel` |
| Repository | `exp-runtime` |
| Workflow filename | `desktop-builds.yml` |
| Environment | `pypi` |

For an existing project you own, add this publisher in its PyPI **Publishing**
settings. For a new project, register a pending publisher through your
[account's Publishing page](https://pypi.org/manage/account/publishing/);
[PyPI creates the project on its first successful upload](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).
A pending publisher does not reserve a name. Configure every component before
releasing, since every component is pinned to the common version.

In GitHub **Settings → Environments**, create `pypi` and restrict its deployment
tags to `v*`. The PyPI environment field must match this name exactly. No
PyPI API token or repository secret is needed: only the publishing job has
`id-token: write`, allowing the action to obtain short-lived PyPI credentials.
Branch pushes, pull requests and manual runs build artifacts without uploading
to PyPI.

PyPI files cannot be replaced. The workflow intentionally fails on an existing
filename rather than silently skipping it. After a successful upload, rerun
only failed jobs if an unrelated release job needs another attempt. If an
upload fails after publishing some files, inspect that PyPI release before
retrying; a full retry will reject those existing files. Use a new common
version and tag for changed distributions. The GitHub app release and PyPI
upload are separate jobs, so check both when releasing.

### Adding an IPA to an existing release

For a tag released before iOS was connected to the release job, download its
successful **iOS builds → ios-arm64-unsigned** artifact. Extract the outer
artifact ZIP and find the `.ipa` and `.ipa.sha256` files; older artifacts put
them under `dist/downloads/`. Use the run for that tag/commit so the files match
the published version. In **Releases → Edit**, attach both files and save.

Rerunning the old tag's workflow uses its original commit and workflow files;
it does not load this fix from the default branch. See
[GitHub's rerun behavior](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs).

## Player workflow

After cloning the project, run from its root directory:

```sh
uv sync --locked --extra build
uv run --locked --extra build python tools/build_desktop.py
```

Open `dist/desktop/EXP Runtime.app` on macOS. Windows and Linux executables
are inside `dist/desktop/EXP Runtime/`; keep that complete directory together.
Build on the target operating system. CI adds startup checks for all four
download targets; complete gameplay still needs validation on each platform.

Windows/Linux builds also need CMake and a C compiler. `tools/build_rar.py`
downloads the SHA-256-pinned libarchive 3.8.9 source and builds the decoder,
without external codec dependencies or CLI tools. CI runs this before tests;
the desktop builder includes its library and license notices. Source users
can run the same helper, or use a system libarchive on Linux. macOS and iOS
use their OS library, so Apple builds need no additional dependency download.
Source checkouts locate the helper's `build/rar/install` output at the workspace
root, including when launched from another directory. Frozen downloads load
their bundled decoder first; installed Python wheels use the system library.
The builder also disables unused POSIX regex support explicitly: libarchive
3.8.9's automatic provider search otherwise requires libgcc on MSVC even with
PCRE disabled.
Windows builds explicitly enable CNG so CMake links the system BCrypt library,
which libarchive's random-number and temporary-file helpers require even when
reading unencrypted archives. This adds no third-party runtime dependency.

The build bundles Python and the runtime dependencies. No APK, IPA, EXPs, Ghidra,
Ren'Py SDK, extracted resources or old checkout are required to build it.
On first launch, choose SHS or CoD, supply its APK/IPA, and add its episode files.
Extraction happens locally; the application has no game download service.

To run from source instead:

```sh
uv run --locked --extra desktop exp-runtime
```

Libraries and saves stay in the user's application-data directory or another
folder they choose. Existing libraries from the research project can be opened
through **Open Library**. Building or updating the engine does not require
copying game content into this source directory. See [MAIN_MENU.md](MAIN_MENU.md)
for library locations and [RUNTIME.md](RUNTIME.md) for current compatibility.

## Public project contents

This standalone directory was assembled from authored source and documents.
It includes no Git history from the research project. Git initialization,
remotes, commits and publication are left to the project owner.

Keep APKs, IPAs, extracted images/audio/fonts/scripts, original screenshots,
native decompilations, generated games, runtime libraries and player saves
outside the public tree. Optional original-content tests read local inputs
and skip when those inputs are absent; ordinary tests use synthetic fixtures.

- `.gitignore` excludes known local game/research paths and generated output
  from normal Git staging. It does not exclude already tracked files.
- `MANIFEST.in` explicitly selects authored source, tests, tools, docs and the
  kiwi SVG logo for source packages. Each component has its own restrictive
  manifest and package discovery under `packages/<component>/src/exp_runtime`.
  Only the player wheel includes `assets/kiwi.svg` as package data. The root
  `exp-runtime` wheel contains dependency metadata; its source archive includes
  the authored workspace. See [SDK.md](SDK.md) for local wheel builds, pip
  installs and isolation checks. These tools do not publish to a package index.
- `tools/build_desktop.py` bundles the runtime and its dependencies. Licenses,
  runtime metadata and the authored kiwi SVG are explicitly collected
  as executable data. The build renders the SVG into a macOS ICNS or Windows
  ICO using the existing pygame/Pillow dependencies; no game files are needed.
  The SVG also supplies the launcher logo and window icon on all platforms.
- `tools/package_desktop.py` archives only the expected app bundle/directory,
  rejecting known game inputs, research files and external links. The workflow
  uploads only `dist/downloads`, never the workspace or content library.

The macOS archiver uses `ditto` to preserve framework links, executable bits
and the app's ad-hoc signature. The archive is extracted again and checked
with `codesign --verify --deep --strict` before the setup-screen smoke test.
Linux downloads use tar.gz because ordinary Actions ZIP uploads do not retain
[file permissions](https://github.com/actions/upload-artifact#permission-loss).
Windows ZIP downloads include the complete PyInstaller output directory.

Apple Developer ID signing/notarization and Windows Authenticode signing are
not configured. macOS may block the initial launch pending approval in Privacy
& Security; Windows may show an unknown-publisher prompt. These are local
builds of an experimental engine, with no original game content included.

Research commands can produce traces containing game text and local paths.
Their JSON outputs belong in ignored local directories, not in the published
source. The format and VM specifications retain evidence addresses and
historical verification summaries. See [PROVENANCE.md](PROVENANCE.md) for how
to interpret references to private evidence snapshots.
