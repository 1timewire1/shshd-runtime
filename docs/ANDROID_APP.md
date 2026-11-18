# Android app

This port packages the existing Python engine and pygame-ce renderer in an
SDL2 Android activity (python-for-android): the desktop drawing path runs as it
is, with an Android host (`platforms/android.py`) for files, fonts, links,
lifecycle and orientation. It targets Android 7.0/API 24 or newer, as one APK
for ARM64 devices and the x86-64 emulator.

It began in [@andymenard's fork](https://github.com/andymenard/shshd-runtime),
whose Android commits were cherry-picked onto this repository's `android-port`
branch with their authorship (their first APK built in
[GitHub Actions run 39041119010](https://github.com/andymenard/shshd-runtime/actions/runs/39041119010)).
Since then it has been checked on Android 15 emulators (phone and tablet) and
on a Moto g54 5G (Android 15), the test phone since 2026-10-28: upgrades over
earlier builds, imports, real Wi-Fi Sync, resume after a restart, rotation and
the side panels, and the translated games' minigames.

## Build with GitHub Actions

The **Android APK** workflow uses a standard Ubuntu x86-64 runner. Standard
runners are free for public repositories. No game files are used. The APK is
a release build signed with the project's release key, kept in four repository
secrets: `ANDROID_KEYSTORE_BASE64` (the keystore, base64), `ANDROID_KEY_ALIAS`,
`ANDROID_STORE_PASSWORD` and `ANDROID_KEY_PASSWORD`. Without them (a fork), the
workflow builds a debug APK signed with the runner's own development key. It is
intended for sideloading, not Play Store publication.

1. Push the changes to a repository you control. The workflow runs on pushes
   to `master` that touch the app. Forks may need Actions enabled first.
2. Open **Actions → Android APK** and select the latest run. Once the workflow
   exists on the repository's default branch it can also be run manually.
3. Download **shshd-runtime-android** from the completed run's artifacts.
   Extract it to find the APK (`dist/android/shshd-release-<version>.apk`, one
   for devices and the emulator) and its SHA-256 checksum.
4. Transfer the APK to an Android device and open it. Allow installation
   from that file manager/browser when Android asks.

Every build signed with the release key installs over the last, keeping the
player's libraries and saves. An APK signed with another key (a fork's debug
build, or one built before the release key) cannot: Android refuses it with a
signature mismatch, and only uninstalling (which deletes the app's data) lets
it in. Back up any progress you want to keep first.

The initial native build can take tens of minutes. The workflow has a
90-minute timeout and keeps the downloadable APK for seven days. It grants
read-only repository permissions and does not publish releases itself.

From v1.1.0, a version tag's **Builds** run also calls this workflow, and the
release attaches its APK as `shshd-runtime-<version>-android.apk` with a
SHA-256 checksum ([distribution](DISTRIBUTION.md)). Releases are built with the
release key, so they install over tester builds and the reverse.

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
python tools/build_android.py --build --release --signing signing.properties
```

`--signing` names a properties file beside the release keystore
(`keystore=`, the keystore's path relative to the file, `alias=`,
`store_password=` and `key_password=`); keep both outside the checkout and
never commit them. With `--release` the APK is a release build signed with that
key; without it, a debug build re-signed with it (`apksigner`), which installs
over the testers' release builds. A debug build without `--signing` carries the
machine's own debug key.

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

ZIP, RAR4/RAR5 and individual EXP files all import: the APK carries its own
libarchive build (`android/recipes/libarchive`). External library-folder
selection is not implemented; the app explains how to import the original game
files instead.

Libraries, settings and saves stay in private app storage. Do not clear app
data or uninstall if you want to retain them. Options → Data Management backs up
progress and exports episodes into the app's external files folder
(`Android/data/<package>/files`), which a computer can reach over USB, and Sync
Devices sends them to another device. No broad storage permission is requested. Internet
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
it: once the phone is held sideways the app follows the phone (even with
auto-rotate off), and turning it back to portrait for 0.7 s switches the panels
off and gives rotation back to the user's setting (as on iPad). Only a screen
more than 1.2 times taller than wide counts as portrait here, so a near-square
one (a foldable's inner screen) keeps its panels however it is held. The app
otherwise follows the phone's rotation.

SDL asks for its own orientation whenever the window is remade (on every
rotation), so the host has it ask for landscape while the panels hold it and
the bridge asks again for its own afterwards. pygame's own resize handling is
off: it re-made the window surface on Android's UI thread, which crashed SDL on
rotation; the host re-makes it on SDL's thread.

## Frame rate

A phone's clocks hold 60 fps only if frames fit the budget, so one slow effect costs more than its own time. On Android (`platforms/android.py`):

- `desktop_word_hd.QUICK_DRAWING` rounds the word game's cube poses to fewer steps, leaves moving pieces unsmoothed, and limits its haze by time, not by frames. Limiting it by frames made it visibly choppy.
- `desktop_dialogue.REUSE_AT_REST` reuses a settled dialogue line's pieces (`dialogue_animation.at_rest`).

Measured on a Moto g54 in the owner's play, 2026-11-04: dialogue about 56 fps, Memory's skin 52, Reflex's skin 53, a real word grid 55 at rest (37 before `graphics.faded` stopped blending opaque frames), and the story tree's pinch 51-57 fps (2026-11-12). The 60-second autosave waits until a minigame ends; on story screens it still costs one 60-100 ms frame a minute.

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

A full pass ran on the emulators on 2026-11-02/03 and on the g54 on 2026-11-03,
and the g54 has run every tester build since. No original game content is
bundled with the runtime or committed as test fixtures.
