# Android app (experimental)

This port packages the existing Python engine and pygame-ce renderer in an
SDL2 Android activity. It targets ARM64 devices running Android 7.0/API 24
or newer. The first development APK built successfully in
[GitHub Actions run 39041119010](https://github.com/andymenard/shshd-runtime/actions/runs/39041119010)
from commit `741e156`. Its APK v2 signature and 114 ARM64 native libraries and
extensions were verified. Physical-device gameplay verification is still pending;
desktop gameplay tests do not establish Android compatibility.

## Build with GitHub Actions

The **Android APK** workflow uses a standard Ubuntu x86-64 runner. Standard
runners are free for public repositories. No game files, signing credentials,
or other secrets are required. A debug APK is signed with the runner's
development key; it is intended for sideloading, not Play Store publication.

1. Push the changes to a repository you control. The workflow runs on pushes
   to `codex/android-port`. Forks may need Actions enabled first.
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

Use x86-64 Linux (or Windows with an x86-64 WSL2 Linux environment), Python
3.12 and Java 17. Install the native build tools listed in the workflow,
Android command-line tools, platform/build-tools 35 and NDK 28c
(`28.2.13676358`). Google's Linux NDK host tools cannot run natively on this
workspace's ARM64 Linux host. An Apple Silicon Mac can trigger the cloud
workflow from its browser; no local SDK installation is needed for that.

```sh
python3 -m venv .android-env
. .android-env/bin/activate
python -m pip install -r android/build-requirements.txt
export ANDROID_HOME=/path/to/android-sdk
export ANDROID_NDK_HOME="$ANDROID_HOME/ndk/28.2.13676358"
python tools/build_android.py --build
```

Run `python tools/build_android.py` without `--build` to inspect the staged
source tree and its SHA-256 manifest without installing the Android SDK.
The builder includes only component Python sources, the authored icon and
licenses. It does not package the checkout, local game libraries or saves.

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
the time spent asleep. System fonts substitute for unavailable original faces,
so IPA/HD typography needs visual comparison on a device.

## CoD colors

Ported the notice-palette correction from upstream exp-runtime
[`v0.6.1`](https://github.com/joshrmcdaniel/exp-runtime/releases/tag/v0.6.1),
commit `10e9839bd3419d9acaaa2cc52f1e4a40e230ba45`: normal notices use
`(240, 81, 60)`, rose notices `(180, 78, 78)`, and default/gray notices
neutral black lettering. The fork already had black narration with gold
backtick emphasis, which is retained. HD notice fonts now cache per theme.
SHS's palette is unchanged. The complete upstream release was not merged.

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
