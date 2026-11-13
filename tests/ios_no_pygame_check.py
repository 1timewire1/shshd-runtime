"""Start the iOS host on the native backend in a process where pygame can't be imported (as on the device), run frames,
and import every module the app ships there (tests/test_ios_no_pygame.py runs this in its own process: modules other
tests loaded with pygame would hide a failure). usage: ios_no_pygame_check.py DATA_DIR"""
import importlib
import pkgutil
import sys
import tempfile
from pathlib import Path


class NoPygame:
    def find_spec(self, name, path=None, target=None):
        if name == 'pygame' or name.startswith('pygame.'):
            raise ImportError('pygame is not on iOS')
        return None


sys.meta_path.insert(0, NoPygame())
from PIL import Image
from exp_runtime.platforms.drawing import Backend
from exp_runtime import graphics
sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_host_fonts import FontHost
from exp_runtime.platforms.ios import Host

root = Path(sys.argv[1])
root.mkdir(parents=True, exist_ok=True)
icon = root / 'icon.png'
Image.new('RGBA', (2, 2), 'green').save(icon)
backend = Backend(FontHost(), icon)
graphics.install(backend)
host = Host(root, backend=backend, library_root=root / 'libraries', check_updates=False, view_size=(1536, 2048))
for _ in range(30):
    host.request(dict(operation='frame', elapsed=16, size=[1536, 2048], events=[]))
print('host frames ok, screen', host.app.screen)
import exp_runtime
skip = {'exp_runtime.platforms.android', 'exp_runtime.platforms.sdl_audio', 'exp_runtime.creator'}
failed = []
for module in pkgutil.walk_packages(exp_runtime.__path__, 'exp_runtime.'):
    name = module.name
    if any(name == s or name.startswith(s + '.') for s in skip) or '.creator' in name or name.endswith('__main__') or name == 'exp_runtime.cli':
        continue
    try:
        importlib.import_module(name)
    except Exception as error:      # noqa: BLE001
        failed.append((name, f'{type(error).__name__}: {error}'))
print('modules that fail to import without pygame:', len(failed))
for name, error in failed:
    print(' ', name, error[:150])
