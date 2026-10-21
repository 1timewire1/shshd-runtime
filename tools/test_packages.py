"""Verify real pip installs outside the checkout, including missing components.

Build with tools/build_packages.py first. Download the locked third-party
wheels once into ignored build output, then resolve every install offline.
--offline reuses that dependency cache without contacting a package index.
"""
import argparse
from importlib.metadata import version as installed_version
import os
from pathlib import Path
import subprocess
import tempfile
import venv

if __package__:
    from .build_packages import audit
    from .components import check_versions
else:
    from build_packages import audit
    from components import check_versions

ROOT = Path(__file__).resolve().parents[1]

# Authored fixtures only. This program runs in isolated Python processes,
# with no repository/test paths or development site-packages available.
VERIFY = r'''
from copy import deepcopy
from importlib.metadata import distributions
from importlib.util import find_spec
import json
from pathlib import Path
import struct
import subprocess
import sys
from types import SimpleNamespace

from exp_runtime.formats import ExpArchive, decode_program
from exp_runtime.cli import main

expected, games, player = json.loads(sys.argv[1])
actual = {d.metadata['Name'].lower().replace('_', '-') for d in distributions()
          if d.metadata['Name'].lower().startswith('shshd-runtime')}
assert actual == set(expected), (actual, expected)
for name in ('engine', 'shs', 'cod', 'application', 'creator'):
    installed = find_spec('exp_runtime.' + name) is not None
    wanted = (player if name == 'application' else name in games if name in ('shs', 'cod')
              else 'shshd-runtime-creator' in actual if name == 'creator' else 'shshd-runtime-engine' in actual)
    assert installed == wanted, (name, installed, wanted)
for module in ('PIL', 'pygame'):
    wanted = bool(games or player) if module == 'PIL' else player
    assert (find_spec(module) is not None) == wanted, module
creator = 'shshd-runtime-creator' in actual
assert (find_spec('PySide6') is not None) == (creator and player and find_spec('mcp') is None)

def program(*instructions, words=()):
    from exp_runtime.decode.bytecode import OPERAND_OPCODES
    code = bytearray()
    for item in instructions:
        op, arg = item if isinstance(item, tuple) else (item, None)
        code.append(op)
        if op in OPERAND_OPCODES:
            code.extend(struct.pack('>H', arg & 65535))
    return decode_program(b'kiwi\x02\x00\x00' + struct.pack('>4H', len(words), 0, 0, len(instructions))
                          + struct.pack(f'>{len(words)}H', *words) + code)

script = program((0x1a, 7), (0x1f, 0xfa01), 0x33)
data = script.to_bytes()
archive = b'CSPUD' + struct.pack('>IHI3I', 1, 25001, 15, len(data), len(data), 0) + data
Path('authored.exp').write_bytes(archive)
assert ExpArchive(archive).programs()[25001].to_bytes() == data
main(['inspect', 'authored.exp'])
main(['extract', 'authored.exp', '--output', 'extracted'])
assert Path('extracted/25001.bin').read_bytes() == data
assert not any(n.startswith(('pygame', 'PIL', 'exp_runtime.engine', 'exp_runtime.shs', 'exp_runtime.cod')) for n in sys.modules)

if 'shshd-runtime-engine' not in actual:
    result = subprocess.run([sys.executable, '-I', '-m', 'exp_runtime', 'trace', 'authored.exp'], text=True, capture_output=True)
    assert result.returncode == 2 and 'exp-runtime[engine' in result.stderr and 'Traceback' not in result.stderr
else:
    from exp_runtime.content import ExpArchive as CompatibleArchive
    from exp_runtime.games import GAMES, GameUnavailableError
    from exp_runtime.runtime import Session, SaveError
    from exp_runtime.vm import KiwiVM, StopKind
    assert CompatibleArchive is ExpArchive
    assert set(GAMES) == set(games)
    vm = KiwiVM(script)
    stop = vm.run()
    assert stop.args == (7,) and stop.yield_id == 250
    assert vm.run() is stop
    vm.resume(0)
    assert vm.run().kind == StopKind.HALT
    for missing in {'shs', 'cod'} - set(games):
        try:
            GAMES[missing]
        except GameUnavailableError as error:
            assert f'exp-runtime[{missing}]' in str(error)
        else:
            raise AssertionError('Missing adapter silently accepted')
    for game in games:
        resources = SimpleNamespace(library=SimpleNamespace(game_id=game, directory=Path('.')),
                                    identity=dict(profile='authored', episode_sha256='f'*64),
                                    program=lambda resource: script, exists=lambda resource: False)
        session = Session(resources)
        action = session.advance()
        assert action.name == 'unhandled_yield' and action.request.args == (7,)
        saved = json.loads(json.dumps(session.snapshot()))
        restored = Session.from_snapshot(resources, saved)
        assert json.loads(json.dumps(restored.snapshot())) == saved
        assert restored.vm.pending.args == (7,)
        change = session.engine.prepare_relationship(45)
        assert change is not None and change.asset_id == GAMES[game].RELATIONSHIP_ASSETS[2]
        assert change.extra_delay_ms == (300 if game == 'cod' else 0)
        assert change.sound is None
        if game == 'cod':
            bad = deepcopy(saved)
            bad['engine']['football'] = {}
            try:
                Session.from_snapshot(resources, bad)
            except SaveError:
                pass
            else:
                raise AssertionError('CoD accepted an SHS-only saved object')
    assert 'pygame' not in sys.modules
if player:
    from exp_runtime.application import Application
    from exp_runtime.app_info import runtime_version
    from exp_runtime.app_icon import icon_surface
    assert runtime_version() != 'development'
    app = Application(audio=False, library_root=Path('libraries'), settings_path=Path('settings.json'), check_updates=False)
    try:
        assert app.screen == 'games' and set(GAMES) == set(games)
        assert icon_surface(32).get_size() == (32, 32)
        for game in games:
            app.choose_game(game)
            assert app.selected_game == game
    finally:
        app.close()
if creator:
    from exp_runtime.creator import Project, compile_project, save_project, load_project
    project = Project()
    save_project(project, Path('story.expproj'))
    assert load_project(Path('story.expproj')) == project
    assert ExpArchive(compile_project(project)).metadata().title == project.title
    result = subprocess.run([sys.executable, '-I', '-m', 'exp_runtime.creator', 'story.expproj',
                             '--export', 'story.exp'], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert Path('story.exp').read_bytes() == compile_project(project)
    if find_spec('mcp'):
        from exp_runtime.creator.mcp_server import create_server
        assert create_server(Path.cwd()).name == 'EXP Runtime Creator'
    if find_spec('PySide6'):
        from PySide6.QtWidgets import QApplication
        from exp_runtime.creator.ui import Editor
        qt = QApplication([])
        editor = Editor()
        editor.show()
        qt.processEvents()
        assert not editor.grab().isNull()
        editor.close()
print('Verified pip install:', ', '.join(sorted(actual)))
'''


def run(command, *, cwd, env):
    result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, timeout=180)
    if result.returncode:
        raise RuntimeError(f'Failed: {command}\n{result.stdout}\n{result.stderr}')
    return result.stdout


def python_in(directory):
    return directory / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def verify(directory, *, offline=False):
    audit(directory)
    version = check_versions(ROOT)
    cache = ROOT / 'build/package-test-dependencies'
    cache.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONNOUSERSITE='1', PIP_DISABLE_PIP_VERSION_CHECK='1',
               SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', PYGAME_HIDE_SUPPORT_PROMPT='1',
               QT_QPA_PLATFORM='offscreen')
    env.pop('PYTHONPATH', None)
    with tempfile.TemporaryDirectory(prefix='exp-pip-tests-') as temporary:
        root = Path(temporary)
        if not offline:
            bootstrap = root / 'bootstrap'
            venv.EnvBuilder(with_pip=True).create(bootstrap)
            run([str(python_in(bootstrap)), '-m', 'pip', 'download', '--only-binary=:all:',
                 '--no-deps', '--dest', str(cache), f'Pillow=={installed_version("Pillow")}',
                 f'pygame-ce=={installed_version("pygame-ce")}',
                 f'PySide6-Essentials=={installed_version("PySide6-Essentials")}',
                 f'shiboken6=={installed_version("shiboken6")}'], cwd=root, env=env)
            run([str(python_in(bootstrap)), '-m', 'pip', 'download', '--only-binary=:all:',
                 '--dest', str(cache), 'mcp>=1.28,<2'], cwd=root, env=env)
        cases = (
            ('tools', ('shshd-runtime[tools]',), (), False, True),
            ('engine', ('shshd-runtime[engine]',), (), False, True),
            ('shs', ('shshd-runtime[engine,shs]',), ('shs',), False, True),
            ('cod', ('shshd-runtime[engine,cod]',), ('cod',), False, True),
            ('both', ('shshd-runtime[engine,shs,cod]',), ('shs', 'cod'), False, True),
            ('player', ('shshd-runtime[player]',), ('shs', 'cod'), True, True),
            ('desktop', ('shshd-runtime[desktop]',), ('shs', 'cod'), True, True),
            ('creator-mcp', ('shshd-runtime[creator-mcp]',), ('shs', 'cod'), True, True),
            ('creator-core', ('shshd-runtime-creator',), (), False, False),
            ('creator', ('shshd-runtime[creator]',), ('shs', 'cod'), True, True),
            ('cod-player', ('shshd-runtime-player[desktop]', 'shshd-runtime-cod'), ('cod',), True, False),
        )
        import json
        for label, requirements, games, player, umbrella in cases:
            case = root / label
            venv.EnvBuilder(with_pip=True).create(case / 'venv')
            python = str(python_in(case / 'venv'))
            pip = [python, '-m', 'pip']
            run([*pip, 'install', '--no-index', '--find-links', str(directory), '--find-links', str(cache),
                 *(f'{req}=={version}' for req in requirements)], cwd=case, env=env)
            run([*pip, 'check'], cwd=case, env=env)
            expected = ['shshd-runtime-formats'] + (['shshd-runtime'] if umbrella else [])
            if label not in ('tools', 'creator-core'):
                expected.append('shshd-runtime-engine')
            if label in ('creator', 'creator-core', 'creator-mcp'):
                expected.append('shshd-runtime-creator')
            if player:
                expected.append('shshd-runtime-player')
            expected.extend(f'shshd-runtime-{game}' for game in games)
            output = run([python, '-I', '-c', VERIFY, json.dumps((expected, games, player))], cwd=case, env=env)
            print(output.splitlines()[-1], flush=True)
        # Removing one namespace component must not delete another's files.
        run([*pip, 'uninstall', '-y', 'shshd-runtime-player'], cwd=case, env=env)
        run([*pip, 'check'], cwd=case, env=env)
        expected.remove('shshd-runtime-player')
        # Pip intentionally retains dependencies; remove pygame for the
        # assertion that this resulting headless environment has no SDL.
        run([*pip, 'uninstall', '-y', 'pygame-ce'], cwd=case, env=env)
        (case / 'extracted').rename(case / 'previous-extraction')
        output = run([python, '-I', '-c', VERIFY, json.dumps((expected, games, False))], cwd=case, env=env)
        print('Uninstall isolation:', output.splitlines()[-1], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheels', type=Path, default=ROOT / 'dist/packages')
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    verify(args.wheels.resolve(), offline=args.offline)
