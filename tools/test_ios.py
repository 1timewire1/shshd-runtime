"""Verify the embedded runtime in a temporary, isolated iOS simulator."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
APP_ID = 'org.shshd.runtime'          # tools/build_ios.py's PRODUCT_BUNDLE_IDENTIFIER


def simctl(*args, timeout=60, check=True):
    print(f'simctl {args[0]}', flush=True)
    try:
        return subprocess.run(['xcrun', 'simctl', *map(str, args)], text=True, capture_output=True,
                              timeout=timeout, check=check).stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        for output in (error.stdout, error.stderr):
            if output:
                print(output.decode(errors='replace') if isinstance(output, bytes) else output,
                      file=sys.stderr, flush=True)
        raise


def stop_process(process, description):
    """Bound child cleanup without replacing the verification failure."""
    try:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    except (OSError, subprocess.SubprocessError) as error:
        print(f'Could not stop {description}: {error}', file=sys.stderr, flush=True)


def run_simctl_step(args, log, *, label, timeout):
    """Run a bounded simulator step, retaining output and reporting slow progress."""
    if timeout <= 0:
        raise ValueError(f'{label} timeout must be positive')
    print(f'simctl {args[0]} {args[1]}; allowing {timeout}s for {label.lower()}', flush=True)
    started = time.monotonic()
    progress = started + 30
    with log.open('w') as output, log.open(encoding='utf-8', errors='replace') as reader:
        process = subprocess.Popen(['xcrun', 'simctl', *map(str, args)],
                                   stdout=output, stderr=subprocess.STDOUT)
        try:
            while True:
                code = process.poll()
                chunk = reader.read()
                if chunk:
                    print(chunk, end='', flush=True)
                now = time.monotonic()
                if code is not None:
                    if code != 0:
                        raise RuntimeError(f'simctl {args[0]} exited with status {code}; see {log}')
                    print(f'{label} completed in {now - started:.1f}s', flush=True)
                    return
                if now - started >= timeout:
                    raise TimeoutError(f'{label} did not finish within {timeout} seconds; see {log}')
                if now >= progress:
                    print(f'Waiting for {label.lower()} ({now - started:.0f}s elapsed, limit {timeout}s)...', flush=True)
                    progress = now + 30
                time.sleep(.2)
        finally:
            stop_process(process, f'{label.lower()} monitor')


def wait_for_boot(device, log, *, timeout=300):
    """Boot the disposable device and relay boot/migration progress with a deadline."""
    run_simctl_step(('bootstatus', device, '-b', '-d'), log, label='Simulator boot', timeout=timeout)


def install_app(device, bundle, log, *, timeout=300):
    """Wait for installation independently of boot and app startup budgets."""
    run_simctl_step(('install', device, bundle), log, label='App installation', timeout=timeout)


def wait_for_report(process, report, log, *, timeout=300):
    """Watch the app's report while simctl remains attached to its console."""
    if timeout <= 0:
        raise ValueError('Verification timeout must be positive')
    print(f'Launching self-test; allowing {timeout}s for startup and verification', flush=True)
    deadline = time.monotonic() + timeout
    progress = time.monotonic() + 30
    while time.monotonic() < deadline:
        if report.is_file():
            try:
                result = json.loads(report.read_text())
            except json.JSONDecodeError:
                pass
            else:
                if not isinstance(result, dict) or result.get('status') != 'passed' or result.get('platform') != 'ios':
                    raise RuntimeError(f'iOS runtime verification failed: {result}')
                return result
        code = process.poll()
        if code is not None:
            raise RuntimeError(f'simctl launch exited with status {code} before the app completed verification; see {log}')
        if time.monotonic() >= progress:
            print('Waiting for the iOS presentation verification report...', flush=True)
            progress = time.monotonic() + 30
        time.sleep(.2)
    raise TimeoutError(f'The app did not complete startup and presentation verification within {timeout} seconds; see {log}')


def collect_failure(device, documents, diagnostics, error):
    """Keep evidence before deleting the disposable simulator."""
    (diagnostics / 'failure.txt').write_text(str(error) + '\n')
    if documents:
        for name in ('ios-verification.json', 'ios-presentation-verification.json'):
            source = documents / name
            if source.is_file():
                shutil.copy2(source, diagnostics / name)
    commands = (
        ('devices.log', ('list', 'devices', '--json')),
        ('system.log', ('spawn', device, 'log', 'show', '--style', 'compact', '--last', '5m',
                        '--predicate', 'process == "EXP Runtime" OR process == "SpringBoard" OR process == "runningboardd" '
                        'OR process == "installd" OR process == "installcoordinationd" OR process == "lsd"')),
        ('screenshot.log', ('io', device, 'screenshot', diagnostics / 'failure.png')),
    )
    for name, args in commands:
        with (diagnostics / name).open('w') as output:
            try:
                subprocess.run(['xcrun', 'simctl', *map(str, args)], stdout=output,
                               stderr=subprocess.STDOUT, timeout=20, check=False)
            except (OSError, subprocess.SubprocessError) as failure:
                output.write(f'\nDiagnostic command failed: {failure}\n')
    print(f'Simulator failure diagnostics: {diagnostics}', file=sys.stderr, flush=True)


def verify(bundle, content=(), *, timeout=300, boot_timeout=300, install_timeout=300):
    if timeout <= 0:
        raise ValueError('Verification timeout must be positive')
    if boot_timeout <= 0:
        raise ValueError('Boot timeout must be positive')
    if install_timeout <= 0:
        raise ValueError('Installation timeout must be positive')
    output = ROOT / 'build/ios/verification-simulator.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    runtimes = json.loads(simctl('list', 'runtimes', '--json'))['runtimes']
    diagnostics_root = output.parent / 'simulator-diagnostics'
    diagnostics_root.mkdir(parents=True, exist_ok=True)
    (diagnostics_root / 'runtimes.json').write_text(json.dumps(runtimes, indent=2) + '\n')
    candidates = [r for r in runtimes if r.get('isAvailable') and r['identifier'].startswith('com.apple.CoreSimulator.SimRuntime.iOS-')]
    if not candidates:
        raise ValueError('Install an iOS simulator runtime through Xcode before verification')
    runtime = max(candidates, key=lambda r: tuple(map(int, r['version'].split('.'))))
    device_type = next((t for t in runtime['supportedDeviceTypes'] if t['name'].startswith('iPhone')), None)
    if device_type is None:
        raise ValueError(f'No supported iPhone device type for {runtime["name"]}')
    print(f'Selected available runtime {runtime["name"]} ({runtime["identifier"]}); '
          f'device {device_type["name"]} ({device_type["identifier"]})', flush=True)
    device = simctl('create', 'EXP Runtime Verification', device_type['identifier'], runtime['identifier'])
    diagnostics = diagnostics_root / device
    documents = None
    process = None
    try:
        diagnostics.mkdir(parents=True, exist_ok=True)
        (diagnostics / 'device.json').write_text(json.dumps(
            dict(device=device, runtime=runtime, device_type=device_type), indent=2) + '\n')
        wait_for_boot(device, diagnostics / 'boot.log', timeout=boot_timeout)
        install_app(device, bundle, diagnostics / 'install.log', timeout=install_timeout)
        container = Path(simctl('get_app_container', device, APP_ID, 'data'))
        documents = container / 'Documents'
        documents.mkdir(exist_ok=True)
        inputs = []
        for index, (game, path) in enumerate(content):
            destination = documents / 'Verification/inputs' / str(index) / Path(path).name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            inputs.append(dict(game=game, path=str(destination)))
        if inputs:
            (documents / 'ios-playback-input.json').write_text(json.dumps(inputs))
        log = diagnostics / 'launch.log'
        with log.open('w') as console:
            process = subprocess.Popen(['xcrun', 'simctl', 'launch', '--console', device, APP_ID, '--self-test'],
                                       stdout=console, stderr=subprocess.STDOUT)
            result = wait_for_report(process, documents / 'ios-presentation-verification.json', log, timeout=timeout)
        image = documents / 'ios-chooser.png'
        if image.is_file():
            shutil.copy2(image, output.with_suffix('.png'))
        if content:
            private = ROOT / 'build/ios/content-verification'
            private.mkdir(exist_ok=True)
            for screenshot in documents.glob('ios-content-*.png'):
                shutil.copy2(screenshot, private / screenshot.name)
        simctl('io', device, 'screenshot', output.with_name('verification-window.png'))
        output.write_text(json.dumps(dict(simulator=runtime['name'], **result), indent=2) + '\n')
        print(output.read_text())
        return result
    except Exception as error:
        try:
            collect_failure(device, documents, diagnostics, error)
        except Exception as failure:
            print(f'Could not collect simulator diagnostics: {failure}', file=sys.stderr, flush=True)
        raise
    finally:
        # --console stays attached until the app exits. Stop only this
        # launch process after collecting screenshots/reports/diagnostics.
        if process is not None:
            stop_process(process, 'simulator console')
        for args in (('terminate', device, APP_ID), ('shutdown', device), ('delete', device)):
            try:
                simctl(*args, timeout=20, check=False)
            except (OSError, subprocess.SubprocessError) as error:
                print(f'Simulator cleanup {args[0]} failed: {error}', file=sys.stderr, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, default=ROOT / 'dist/ios/iphonesimulator/EXP Runtime.app')
    parser.add_argument('--content', nargs=2, action='append', metavar=('GAME', 'ARCHIVE'), default=[],
                        help='Optionally test a locally supplied game archive in the temporary simulator only')
    parser.add_argument('--timeout', type=int, default=300, help='Maximum seconds for app startup and verification')
    parser.add_argument('--boot-timeout', type=int, default=300, help='Maximum seconds for simulator boot, before app verification')
    parser.add_argument('--install-timeout', type=int, default=300, help='Maximum seconds for app installation, after boot and before launch')
    args = parser.parse_args()
    verify(args.bundle.resolve(), args.content, timeout=args.timeout, boot_timeout=args.boot_timeout,
           install_timeout=args.install_timeout)
