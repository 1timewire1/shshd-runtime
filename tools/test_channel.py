"""Talk to a running SHSHD Runtime's test channel (packages/player/src/exp_runtime/test_channel.py).

    python tools/test_channel.py [--port 47920] [--adb SERIAL] COMMAND [COMMAND ...]
    python tools/test_channel.py --adb ZY22KJTN3J --enable        (Android: switch the channel on, then restart the app)
    python tools/test_channel.py --adb ZY22KJTN3J --pull NAME OUT  (Android: fetch a `shot NAME` picture)

Each COMMAND is one line sent to the app (quote it: "answer 1", "run-until choice 90"); each reply is printed as JSON.
With --adb, the port is forwarded over USB first (`adb forward`), and --enable writes SHSHD_TEST_CHANNEL into the app's
p4a_env_vars.txt with `run-as`, which only a debuggable build allows (an app update resets that file: enable again).
On the desktop, set SHSHD_TEST_CHANNEL=47920 before starting the app.
"""
import argparse
import json
import os
import socket
import subprocess
import sys

PACKAGE = 'org.shshd.runtime'
ADB = os.environ.get('ADB', r'C:\platform-tools\adb.exe' if os.name == 'nt' else 'adb')


def adb(serial, *args, **kwargs):
    return subprocess.run([ADB, '-s', serial, *args], check=True, capture_output=True, **kwargs)


def enable(serial, port):
    env = 'files/app/p4a_env_vars.txt'
    script = (f"grep -v SHSHD_TEST_CHANNEL {env} > files/.env && cat files/.env > {env} && rm files/.env && "
              f"echo SHSHD_TEST_CHANNEL={port} >> {env}")
    adb(serial, 'shell', f"run-as {PACKAGE} sh -c '{script}'")
    adb(serial, 'shell', 'am', 'force-stop', PACKAGE)
    adb(serial, 'shell', 'monkey', '-p', PACKAGE, '-c', 'android.intent.category.LAUNCHER', '1')


def pull(serial, name, out):
    data = adb(serial, 'exec-out', f"run-as {PACKAGE} cat 'files/SHSHD Runtime/test-shots/{name}.png'").stdout
    with open(out, 'wb') as stream:
        stream.write(data)
    return len(data)


def send(port, commands):
    with socket.create_connection(('127.0.0.1', port), timeout=330) as connection, \
            connection.makefile('rw', encoding='utf-8', newline='\n') as stream:
        for command in commands:
            stream.write(command + '\n')
            stream.flush()
            line = stream.readline()
            if not line:
                raise ConnectionError('the app closed the channel (on Android, is it on? The first launch after an '
                                      'update rewrites p4a_env_vars.txt: run --enable again)')
            yield command, json.loads(line)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--port', type=int, default=47920)
    parser.add_argument('--adb', metavar='SERIAL', help='a device or emulator, reached over adb forward')
    parser.add_argument('--enable', action='store_true', help='Android: switch the channel on and restart the app')
    parser.add_argument('--pull', nargs=2, metavar=('NAME', 'OUT'), help='Android: fetch a shot')
    parser.add_argument('commands', nargs='*')
    args = parser.parse_args(argv)
    if args.adb:
        if args.enable:
            enable(args.adb, args.port)
        adb(args.adb, 'forward', f'tcp:{args.port}', f'tcp:{args.port}')
        if args.pull:
            print(json.dumps(dict(ok=True, bytes=pull(args.adb, *args.pull))))
    if args.commands:
        for command, reply in send(args.port, args.commands):
            print(json.dumps(dict(command=command, **reply), ensure_ascii=False))
            if not reply.get('ok', True):
                return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
