# Episode creator (unreleased)

The optional desktop creator authors **new SHS and CoD episodes** for EXP
Runtime and the original games. It exports the native CSPUD `.exp` container
with KiWi v2 bytecode. Authored scripts pass checks against the original
SHS Android, SHS iOS and CoD iOS loaders and interpreters; full playback in
the original apps remains unverified. See the compatibility details below.
This feature is newer than the published v0.5.0 release; run it from this
checkout for now:

```sh
uv run --locked --extra creator exp-creator
```

## Make an episode

1. Choose **Surviving High School** or **Cause of Death**, and enter the title,
   pack ID and episode ID. The five native title fields receive the same title
   in this first version. Pack and episode IDs are author-assigned metadata;
   they do not claim a place in the original game catalog.
2. Select a card to edit it. Add **Dialogue**, **Choice**, **Background**,
   **Set variable**, **Condition** or **End episode** nodes from the left pane.
   Drag cards to arrange them; use the zoom and fit controls for larger stories.
3. Choose each node's **Next** destination in the right pane. A choice has two
   to eight answers, each with its own destination. A condition has true and
   false destinations. **Start episode here** sets the entry node independently
   of card order. Lines show the current connections.
4. Leave the speaker empty for narration, enter a name for dialogue without
   a portrait, or select a portrait and its color for character dialogue.
   Set a choice's time limit in milliseconds, and select which answer its
   timer chooses on expiry. Zero disables the timer.
5. Use **Set variable** to remember a number, then **Condition** to compare it
   later. Names identify episode-local numeric variables; unread variables
   start at zero. Values use the native signed 16-bit range. Loops through
   dialogue and choices are supported; automatic loops that could freeze
   playback are rejected.
6. **Save** writes an editable `.expproj` document. **Validate** checks the
   story, and **Export EXP** writes an episode that the ordinary player can
   import through its existing EXP/ZIP/RAR workflow. Saving unfinished
   projects is allowed; exporting missing connections is not.

Undo/redo covers text, connections, node positions, project settings and image
changes. The editor asks about unsaved changes before opening another project
or closing the window. Project and EXP writes replace the destination only
after the complete output has been written.

## Images and imported game assets

**Add PNG / JPEG** embeds an image in the project. Embedded images are portable:
moving the project or deleting the original image does not break the export.
The creator allocates episode resource IDs from 26000, reserving five IDs for
each image so unrelated images cannot become portrait expression variants.
Use artwork sized for the original game's portrait/background presentation;
the shared renderer retains its usual scaling and masking rules.

**Use imported library** selects the game folder containing `library.json`,
created by importing your APK/IPA through the player. **Browse library images**
shows base resources and imported episode banks, with a preview of single
images. Numeric IDs are retained because original archives do not always
provide descriptive filenames. Fonts, scripts and UI atlases are not offered
as usable single images.

- Base images remain references to the selected game's resources. They are
  not copied into the exported episode. Recipients must supply the corresponding
  game assets through the usual player import, or use the matching original
  game. A base ID must exist in the version they play; the EXP does not include
  missing base assets from a different APK/IPA.
- Episode images are copied into the project and assigned local IDs. The
  source episode is no longer required. Embedded images are included in the
  exported EXP; review which assets you intend to distribute.
- SHS and CoD libraries stay separate. The project game must match the selected
  library. The format itself does not identify a game: import the export under
  the same game you selected in the creator.

No original content ships with the editor. A project can be edited and
exported without a game library, using narration and your own images.

## Preview

**Preview in player** opens the compiled episode in the existing desktop
player, with the selected game's original skin, fonts, animations and choice
handling. Supply an imported library to use this preview. It runs in a separate
process and uses a temporary save directory; it does not import into, overwrite
or save progress in your existing library. Close the preview before starting
another. Edits take effect when a new preview is launched.

## Export for an original app

The original apps select episodes through their own catalogs. They do not have
the runtime's general-purpose EXP import picker. **Original app export** creates
a replacement for an existing episode slot:

1. Choose an existing EXP from the matching original game that is already
   present in that installation's catalog.
2. Save the replacement to a separate location. The compiler keeps that EXP's
   pack and episode IDs and writes your authored story, title and images.
   It leaves the reference file and your project's assigned IDs unchanged.
3. On a compatible installation, back up its episode and save data, then place
   the replacement where that catalog expects the existing EXP, using the
   expected filename. Access to the app's episode storage is required; this
   step depends on the device, platform and installation.
4. Start that episode from the beginning. An existing save's script positions
   belong to the old story and cannot be reused with the replacement.

This flow does not create native catalog entries, install files on a device,
or repackage/sign an APK or IPA. The original catalog may still display the
old episode name. Bundled episodes can have special app-bundle lookup paths;
putting a replacement in the downloaded-episode folder is not sufficient for
those slots. Prefer a downloaded episode when testing.

The equivalent headless export is:

```sh
uv run --locked python -m exp_runtime.creator story.expproj \
  --native-slot /path/to/original/Existing_Episode.exp \
  --export /path/to/replacements/Existing_Episode.exp
```

### Native compatibility evidence

The compiler uses the native entry script ID `25001`, literal CSPUD records,
KiWi v2 instruction encoding and recovered host-service argument contracts.
Ghidra inspection covers the resource loaders and game host calls. A separate
ARM emulation check runs authored exports through the actual KiWi loader and
interpreter from each supplied reference binary:

| Profile | KiWi loader | Interpreter | CSPUD loader |
| --- | --- | --- | --- |
| SHS Android 1.0.9 (`libshs09.so`) | `00057068` | `00055ce0` | `0005e4c0` |
| SHS iOS (`Surviving_HS`) | `00010e9c` | `00011410` | `00017334` |
| CoD iOS (`CoD`, ARMv6 slice) | `0000d53c` | `0000cb8c` | `00007250` |

`tools/test_creator_native.py` pins the SHA-256 identities of those binaries.
It checks 24 programs per profile, covering every comparison operator and
choice branch, signed variable writes, initialized memory, narration, named
dialogue and episode exit. Native yield arguments and script memory must match
the production Python VM. The harness supplies stream I/O, allocation and
host callback results. It does **not** run the original UI, timers, image
decoder, catalog installation or OS integration. CSPUD compatibility is based
on the inspected native loaders and the format's round-trip tests, not an
emulated app launch.

With a matching locally supplied binary, developers can repeat the optional
check without adding Unicorn to the player dependencies:

```sh
uv run --locked --with 'unicorn>=2,<3' python tools/test_creator_native.py \
  --profile cod-ios --binary /path/to/CoD
```

Use `shs-ios` or `shs-android` with the corresponding binary for the other
profiles. No original code or assets are included in the tool. Original-app
playback is still a required verification step before claiming complete native
compatibility; a compatible installation is not currently available for it.

## Python API and package boundaries

`exp-runtime-creator` contains the headless document model and compiler and
depends only on `exp-runtime-formats`. Its `[desktop]` extra adds Qt for Python
(`PySide6-Essentials`), the existing desktop player and both game adapters. The
umbrella's `[creator]` extra selects that complete editor. Ordinary player
installs and desktop/iOS player bundles exclude the creator and Qt.

Once this feature is released, `python -m pip install 'exp-runtime[creator]'`
will install the visual editor. Until then, use the source command above or
locally built wheels. No new release version has been assigned yet.

```python
from pathlib import Path
from exp_runtime.creator import Project, load_project, save_project, export_project

project = Project(title="My episode", game="cod")
project.node("start").text = "A new story begins."
save_project(project, Path("story.expproj"))
export_project(load_project(Path("story.expproj")), Path("story.exp"))
```

Headless export does not load Qt or the game library:

```sh
uv run --locked python -m exp_runtime.creator story.expproj --export story.exp
```

The general `exp_runtime.formats.encode_exp({resource_id: payload_bytes})`
writer and `Metadata.to_bytes()` also work independently of the creator. The
writer emits deterministic literal records; it does not preserve an existing
archive's compression, aliases or physical layout.

## Initial limits

This is an editor for new stories, not a decompiler that converts arbitrary
original EXP scripts into a graph. Music cues, minigame authoring, expression
animation editing, localization editing and live preview updates are not yet
exposed. The compiler emits one script at resource 25001 and checks the native
signed instruction-count limit (32,767), keeps data below `0x7000` words and
allows at most 199 portrait speakers plus the narrator. Variables live in
initialized script memory, separate from the games' global properties. Story
text uses native Latin-1 encoding; unsupported
characters are reported instead of silently replaced. Use straight quotes and
dashes when pasting text from a word processor. Metadata titles use UTF-8.

An editable project is versioned JSON containing node positions, connections,
settings and base64-encoded custom image bytes. The optional library location
is stored relative to the project where possible. Projects and generated EXPs
are ignored by Git and excluded from package archives.
