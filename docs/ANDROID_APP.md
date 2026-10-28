# Android app (experimental)

This port packages the existing Python engine and pygame-ce renderer in an
SDL2 Android activity (python-for-android): the desktop drawing path runs as it
is, with an Android host (`platforms/android.py`) for files, fonts, links,
lifecycle and orientation. It targets Android 7.0/API 24 or newer, as one APK
for ARM64 devices and the x86-64 emulator.

It began in [@andymenard's fork](https://github.com/andymenard/shshd-runtime),
whose Android commits were cherry-picked onto this repository's `android-port`
branch with their authorship (their first APK built in
[GitHub Actions run 39041119010](https://github.com/andymenard/shshd-runtime/actions/runs/39041119010)).
Since then it imports, opens both games' HD menus and pickers and plays
episodes on an Android 15 emulator; physical-device checks are pending.

## Build with GitHub Actions

The **Android APK** workflow uses a standard Ubuntu x86-64 runner. Standard
runners are free for public repositories. No game files, signing credentials,
or other secrets are required. A debug APK is signed with the runner's
development key; it is intended for sideloading, not Play Store publication.

1. Push the changes to a repository you control. The workflow runs on pushes
   to `android-port`. Forks may need Actions enabled first.
2. Open **Actions → Android APK** and select the latest run. Once the workflow
   exists on the repository's default branch it can also be run manually.
3. Download **shshd-runtime-android-arm64-debug** from the completed run's
   artifacts. Extract it to find the APK and SHA-256 checksum.
4. Transfer the APK to an ARM64 Android device and open it. Allow installation
   from that file manager/browser when Android asks.

New cloud runs may use a different debug signing key. If Android refuses an
update due to a signature mismatch, do not uninstall without backing up any
progress you want to keep. A persistent signing key is needed before regular
update distribution; this initial workflow deliberately uses no private keys.

The initial native build can take tens of minutes. The workflow has a
90-minute timeout and keeps the downloadable APK for seven days. It grants
read-only repository permissions and does not publish releases.

## Local build

Use x86-64 Linux, or Windows with WSL2 (Ubuntu 24.04: Python 3.12 and, from
apt, Java 17 and the native build tools the workflow installs). Install the
Android command-line tools, platform and build-tools 35 and NDK 28c
(`28.2.13676358`) in the Linux home folder: the Windows SDK's tools do not run
there. Build from a copy of the checkout in the Linux file system, not
`/mnt/c` (much slower). Google's Linux NDK host tools cannot run on an ARM64
Linux host; an Apple Silicon Mac can use the cloud workflow instead.

```sh
python3 -m venv .android-env
. .android-env/bin/activate
python -m pip install -r android/build-requirements.txt
export ANDROID_HOME=/path/to/android-sdk
export ANDROID_NDK_HOME="$ANDROID_HOME/ndk/28.2.13676358"
python tools/build_android.py --build                 # arm64-v8a and x86_64
python tools/build_android.py --build --arch x86_64   # the emulator only
```

The first build compiles Python, SDL, Pillow and pygame-ce for each ABI (about
15 minutes for one on an x86-64 desktop); later builds reuse them. Run
`python tools/build_android.py` without `--build` to inspect the staged
source tree and its SHA-256 manifest without installing the Android SDK.
The builder includes only component Python sources, the authored icon (rendered
into the launcher icon and loading splash) and licenses. It does not package
the checkout, local game libraries or saves.

## Import and controls

Use **Bulk Import** to choose a ZIP of game files, or choose a game and import
its APK/IPA files. Android's document picker supports multiple selection, so
SHS users can select both the APK and optional HD IPA together. Files are
copied to private staging on a worker, validated by the shared importer and
removed after the import job finishes. Source files stay untouched.

Use ZIP or individual EXP files for this first build. The desktop RAR decoder
is not yet bundled for Android. External library-folder selection is also not
implemented; the app explains how to import the original game files instead.

Libraries, settings and saves stay in private app storage. Do not clear app
data or uninstall if you want to retain them; export/backup UI is not part of
this proof of concept. No broad storage permission is requested. Internet
access supports the existing optional update check.

Touch uses SDL's primary-finger mouse mapping, including drags and scrolling.
Android Back follows the existing Escape/menu behavior. Backgrounding pauses
the story and audio and checkpoints progress; the first resumed frame excludes
the time spent asleep.

## Fonts

Android ships none of the faces the HD and Cause of Death screens draw with:
Arial, Arial Bold, Arial Rounded MT Bold, Trebuchet MS Bold and Trebuchet MS
Italic. Put your own copies in the bulk import's ZIP beside the game files
(a Windows PC has them as `arial.ttf`, `arialbd.ttf`, `trebucbd.ttf`,
`trebucit.ttf` and Office's `ARLRDBD.TTF`); the import copies them into each
library's `fonts/` folder, where the Android host finds them by face and style.
A face that is missing is drawn in Android's Roboto instead.

## Side panels

The story tree and Faceplace panels need the screen's width, so turning them on
in portrait turns the app to landscape (`OrientationBridge`), without locking
it: once the phone is held sideways, rotation is the user's again, and turning
back to portrait switches the panels off (as on iPad). The app otherwise
follows the phone's rotation.

## CoD colors

The fork also ported upstream exp-runtime
[`v0.6.1`](https://github.com/joshrmcdaniel/exp-runtime/releases/tag/v0.6.1)'s
notice palette. This repository had already merged v0.6.1, so those hunks were
not taken; the HD letter effect keeps theme 1's red (docs/COD.md).

## Acceptance checks on Android

- Cold launch reaches Bulk Import without a missing Python/native module.
- Cancel the picker, then import authored fixtures and player-supplied files.
- Play a scene in each installed game; verify audio and CoD notice themes.
- Enter a name with the onscreen keyboard and scroll long episode lists.
- Exercise HD dialogue, choices, portrait effects and both mini-games.
- Background during a timed choice; return without consuming paused time.
- Close/relaunch and verify restored progress and settings.
- Check tall/notched displays, Back navigation and sound after resume.

Device checks need to be recorded after an APK is installed. No original game
content is bundled with the runtime or committed as test fixtures.
