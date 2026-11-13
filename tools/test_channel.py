"""Talk to a running SHSHD Runtime's test channel (packages/player/src/exp_runtime/test_channel.py).

    python tools/test_channel.py [--port 47920] [--adb SERIAL | --ios] COMMAND [COMMAND ...]
    python tools/test_channel.py --adb ZY22KJTN3J --enable        (Android: switch the channel on, then restart the app)
    python tools/test_channel.py --ios --enable                   (iOS: switch it on; then start the app on the device)
    python tools/test_channel.py [--adb SERIAL | --ios] --shot NAME OUT   (the window as OUT, a PNG)
    python tools/test_channel.py [--adb SERIAL | --ios] --put LOCAL REMOTE (a file into the app's data folder)
    python tools/test_channel.py [--adb SERIAL | --ios] --get REMOTE OUT   (a file out of it)

Each COMMAND is one line sent to the app (quote it: "answer 1", "run-until choice 90"); each reply is printed as JSON.

- Android (--adb): the port is forwarded over USB first (`adb forward`). --enable writes SHSHD_TEST_CHANNEL into the
  app's p4a_env_vars.txt with `run-as`, which only a debuggable build allows (an app update resets that file: enable
  again).
- iOS (--ios): the port is forwarded over USB with pymobiledevice3's `usbmux forward` (PMD3 names its command; the
  default is the SHSHD folder's .venvs/pmd3). --enable sets the hidden `test_channel` key in the app's settings.json, in
  its Documents (File Sharing, over the cable), for the next start; --bundle names the app (as it was signed).
- The desktop: set SHSHD_TEST_CHANNEL=47920 before starting the app, or the same settings key.

`--put` into `dev-modules/exp_runtime/NAME.py` gives the app a changed module from its next start
(launcher.install_dev_modules): a change tried on a device without a new build.
"""
import argparse
import base64
import contextlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

PACKAGE = 'org.shshd.runtime'
IOS_BUNDLE = 'org.shshd.runtime.DVU8UW52Q3'         # as the owner's sideloaded build is signed
IOS_SETTINGS = '/Documents/SHSHD Runtime/settings.json'
ADB = os.environ.get('ADB', r'C:\platform-tools\adb.exe' if os.name == 'nt' else 'adb')
PMD3 = os.environ.get('PMD3') or str(Path(__file__).resolve().parents[2] / '.venvs' / 'pmd3' /
                                     ('Scripts/pymobiledevice3.exe' if os.name == 'nt' else 'bin/pymobiledevice3'))


def adb(serial, *args, **kwargs):
    return subprocess.run([ADB, '-s', serial, *args], check=True, capture_output=True, **kwargs)


def enable(serial, port):
    env = 'files/app/p4a_env_vars.txt'
    script = (f"grep -v SHSHD_TEST_CHANNEL {env} > files/.env && cat files/.env > {env} && rm files/.env && "
              f"echo SHSHD_TEST_CHANNEL={port} >> {env}")
    adb(serial, 'shell', f"run-as {PACKAGE} sh -c '{script}'")
    adb(serial, 'shell', 'am', 'force-stop', PACKAGE)
    adb(serial, 'shell', 'monkey', '-p', PACKAGE, '-c', 'android.intent.category.LAUNCHER', '1')


def pmd3(*args):
    return subprocess.run([PMD3, *args], check=True, capture_output=True, text=True)


def ios_enable(bundle, port):
    """The hidden `test_channel` key in the app's settings.json, through its Documents (pymobiledevice3's house_arrest):
    read, set, written back. The app reads it as it starts."""
    with tempfile.TemporaryDirectory() as folder:
        local = Path(folder) / 'settings.json'
        try:
            pmd3('apps', 'pull', bundle, IOS_SETTINGS, str(local))
            settings = json.loads(local.read_text(encoding='utf-8'))
        except (subprocess.CalledProcessError, OSError, ValueError):
            settings = dict(version=1, check_for_updates=True)      # (no settings yet: a fresh install)
        settings['test_channel'] = port
        local.write_text(json.dumps(settings) + '\n', encoding='utf-8')
        pmd3('apps', 'push', bundle, str(local), IOS_SETTINGS)


@contextlib.contextmanager
def ios_forward(port):
    """usbmux's forwarding of `port` to the device's, for as long as the commands run."""
    process = subprocess.Popen([PMD3, 'usbmux', 'forward', str(port), str(port)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):                             # (up once it accepts a connection)
            with contextlib.suppress(OSError), socket.create_connection(('127.0.0.1', port), timeout=0.2):
                break
            time.sleep(0.1)
        yield
    finally:
        process.terminate()


def send(port, commands):
    with socket.create_connection(('127.0.0.1', port), timeout=330) as connection, \
            connection.makefile('rw', encoding='utf-8', newline='\n') as stream:
        for command in commands:
            stream.write(command + '\n')
            stream.flush()
            line = stream.readline()
            if not line:
                raise ConnectionError('the app closed the channel (is it on? Android: the first launch after an update '
                                      'rewrites p4a_env_vars.txt, run --enable again; iOS: --enable, then start the app)')
            yield command, json.loads(line)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--port', type=int, default=47920)
    parser.add_argument('--adb', metavar='SERIAL', help='an Android device or emulator, reached over adb forward')
    parser.add_argument('--ios', action='store_true', help='the iOS device on the cable, reached over usbmux')
    parser.add_argument('--bundle', default=IOS_BUNDLE, help='iOS: the app as it was signed')
    parser.add_argument('--enable', action='store_true', help='switch the channel on (Android: and restart the app)')
    parser.add_argument('--shot', nargs=2, metavar=('NAME', 'OUT'), help='the window, saved as OUT')
    parser.add_argument('--put', nargs=2, metavar=('LOCAL', 'REMOTE'), help="a file into the app's data folder")
    parser.add_argument('--get', nargs=2, metavar=('REMOTE', 'OUT'), help="a file out of the app's data folder")
    parser.add_argument('commands', nargs='*')
    args = parser.parse_args(argv)
    if args.adb:
        if args.enable:
            enable(args.adb, args.port)
        adb(args.adb, 'forward', f'tcp:{args.port}', f'tcp:{args.port}')
    elif args.ios and args.enable:
        ios_enable(args.bundle, args.port)
        print(json.dumps(dict(ok=True, enabled=args.port, note='start (or restart) the app on the device')))
    commands = list(args.commands)
    if args.shot:
        commands.append(f'shot {args.shot[0]} inline')
    if args.put:
        commands.append(f'put {args.put[1]} ' + base64.b64encode(Path(args.put[0]).read_bytes()).decode('ascii'))
    if args.get:
        commands.append(f'get {args.get[0]}')
    if not commands:
        return 0
    with ios_forward(args.port) if args.ios else contextlib.nullcontext():
        for command, reply in send(args.port, commands):
            if 'png' in reply and args.shot:
                Path(args.shot[1]).write_bytes(base64.b64decode(reply.pop('png')))
                reply['saved'] = args.shot[1]
            if 'data' in reply and args.get:
                Path(args.get[1]).write_bytes(base64.b64decode(reply.pop('data')))
                reply['saved'] = args.get[1]
            shown = command if len(command) < 200 else command[:60] + ' ...'
            print(json.dumps(dict(command=shown, **reply), ensure_ascii=False))
            if not reply.get('ok', True):
                return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
