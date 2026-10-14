"""Serial JSON bridge between UIKit and the shared application/presentation.

Swift owns device services only. Imports, menus, hit testing, clocks, game
sessions, layout and saves all run through the desktop application's code.
"""
import json
from concurrent.futures import Future
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace

from .drawing import Backend, FrameEncoder

_host = None
_verifying = False


class Host:
    def __init__(self, directory, *, backend=None, library_root=None, check_updates=True):
        from .. import graphics
        if backend is None:
            import exp_platform
            def font(request):
                return json.loads(exp_platform.font(json.dumps(request)))
            backend = Backend(font, Path(__file__).resolve().parents[3] / 'kiwi.png')
        self.backend = backend
        graphics.install(backend)
        # Import after installing the backend: pygame is not bundled on iOS.
        from ..application import Application
        self.directory = Path(directory)
        self.update_future = None
        self.update_request = None
        settings = (Path(library_root).parent if library_root is not None else self.directory / 'EXP Runtime') / 'settings.json'
        self.app = Application(file_picker=self.pick, library_root=library_root, url_opener=self.open_url,
                               settings_path=settings, update_fetcher=self.fetch_release, check_updates=check_updates)
        self.encoder = FrameEncoder()
        self.picker = None
        self.url = None
        self.staging = []
        self.last_active = True
        self.app.render()
        self.input_stamp = self._input_stamp()
        self.generation = 0

    def _input_stamp(self):
        game = self.app.game if self.app.screen == 'game' else None
        action = game.session.pending if game else None
        session = game.session if game else None
        return (self.app.input_token(), id(game.session) if game else None, game.menu_open if game else False,
                id(action), action.details.get('page_start') if action else None,
                (session.scene, session.vm.steps_executed) if session else None)

    def handle_events(self, events):
        screen = self.app.screen
        token = self.app.input_token()
        entry = self.app.game.session.pending if screen == 'game' else None
        for event in events:
            if event.get('generation', self.generation) != self.generation:
                continue  # A touch begun on an expired timed choice cannot answer its successor.
            self._event(event)
            if self.app.input_token() != token:
                break
            if screen == 'game' and self.app.game.screen_token != self.app.game._screen_token():
                # Keep all queued characters for this same text field. The
                # one-input gate still applies when it submits or raises an alert.
                editing = (entry is not None and entry.name == 'text_input'
                           and self.app.game.session.pending is entry and not self.app.game.input_error
                           and (event['kind'] == 'text' or event.get('key') == 'backspace'))
                if not editing:
                    break

    def pick(self, kind):
        self.picker = kind

    def open_url(self, url):
        self.url = url

    def fetch_release(self):
        # The host handles HTTPS with URLSession/system certificate trust.
        # Shared Python still owns versions, settings and the Yes/No prompt.
        from ..updates import RELEASE_API, REQUEST_HEADERS, TIMEOUT, MAX_RESPONSE
        self.update_future = Future()
        self.update_request = dict(url=RELEASE_API, headers=REQUEST_HEADERS,
                                   timeout=TIMEOUT, max_bytes=MAX_RESPONSE)
        return self.update_future

    def _event(self, event):
        b = self.backend
        kind = event['kind']
        if kind in ('down', 'up', 'move'):
            position = tuple(event['point'])
            b.pointer = position if kind != 'up' else (-1, -1)
            event = SimpleNamespace(type={'down': b.MOUSEBUTTONDOWN, 'up': b.MOUSEBUTTONUP,
                                          'move': b.MOUSEMOTION}[kind], pos=position, button=1)
        elif kind == 'scroll':
            event = SimpleNamespace(type=b.MOUSEWHEEL, y=event['delta'])
        elif kind == 'text':
            event = SimpleNamespace(type=b.TEXTINPUT, text=event['text'])
        elif kind == 'key':
            event = SimpleNamespace(type=b.KEYDOWN, key={'return': b.K_RETURN, 'backspace': b.K_BACKSPACE,
                                                        'escape': b.K_ESCAPE}[event['key']])
        elif kind == 'cancel':
            b.pointer = (-1, -1)
            self.app.cancel_pointer()
            return
        else:
            raise ValueError(f'Unsupported iOS input: {kind}')
        self.app.handle_event(event)

    def active(self, value):
        if value == self.last_active:
            return
        self.last_active = value
        b = self.backend
        self.app.handle_event(SimpleNamespace(type=b.WINDOWFOCUSGAINED if value else b.WINDOWFOCUSLOST))
        if not value:
            b.mixer.stop()
            if self.app.game:
                self.app._attempt(lambda: self.app.state.checkpoint(self.app.game.session))

    def request(self, message):
        operation = message.get('operation', 'frame')
        verification = {}
        if operation in ('verify_start', 'verify_next'):
            import exp_ios_probe
            if operation == 'verify_start':
                self.test_steps = exp_ios_probe.presentation_steps(self)
                verification['drawing_test'] = exp_ios_probe.drawing_fixture()
                verification['audio_test'] = exp_ios_probe.audio_fixture()
            try:
                verification['verification_check'] = next(self.test_steps)
            except StopIteration:
                verification['verification_done'] = True
            message = dict(message, elapsed=50)
        elif operation == 'import':
            kind = message['kind']
            paths = [Path(path) for path in message['paths']]
            if kind == 'library':
                if len(paths) != 1 or not paths[0].is_dir():
                    raise ValueError('Choose one EXP Runtime library folder')
                self.app._attempt(lambda: self.app.open_library(paths[0], remember=True))
            else:
                self.app._attempt(lambda: self.app.import_paths(paths))
                self.staging.extend(paths)
        elif operation == 'message':
            self.app.message = message['text']
        elif operation == 'update_result':
            if self.update_future is not None and not self.update_future.done():
                self.update_future.set_result(message.get('payload'))
            self.update_future = None
        elif operation == 'active':
            self.active(bool(message['active']))
        elif operation == 'close':
            self.app.close()
            return {'status': 'closed'}
        elif operation != 'frame':
            raise ValueError(f'Unsupported iOS operation: {operation}')
        elapsed = max(0, int(message.get('elapsed', 0))) if self.last_active else 0
        self.backend.ticks += elapsed
        self.handle_events(message.get('events', ()))
        self.app.tick(elapsed)
        if not self.app.busy and self.staging:
            # Swift copied imports into a disposable, app-owned directory.
            # Never remove a selected original or a library being played.
            imports = (self.directory / 'Imports').resolve()
            for path in self.staging:
                if path.resolve().is_relative_to(imports):
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink(missing_ok=True)
                    parent = path.parent.resolve()
                    while parent != imports and parent.is_relative_to(imports):
                        try:
                            parent.rmdir()
                        except OSError:
                            break
                        parent = parent.parent
            self.staging.clear()
        self.app.render()
        stamp = self._input_stamp()
        if stamp != self.input_stamp:
            self.input_stamp = stamp
            self.generation += 1
        frame = self.encoder.encode(self.backend.window)
        audio, self.backend.mixer.commands = self.backend.mixer.commands, []
        picker, self.picker = self.picker, None
        url, self.url = self.url, None
        update_request, self.update_request = self.update_request, None
        if self.update_future is None or self.update_future.cancelled():
            update_request = None
        game = self.app.game if self.app.screen == 'game' else None
        pending = game.session.pending if game else None
        if (operation.startswith('verify_') and verification.get('verification_check')
                and self.app.screen == 'main' and self.app.menu_music_loaded):
            verification['verify_menu_audio'] = True
        if (operation.startswith('verify_')
                and str(verification.get('verification_check', '')).endswith('menu click')):
            verification['verify_click_audio'] = True
        return dict(verification, status='ok', frame=frame, audio=audio, keyboard=self.backend.keyboard, picker=picker, open_url=url,
                    update_request=update_request,
                    generation=self.generation,
                    scrollable=self.app.screen in ('episodes', 'browser') or bool(game and game.max_scroll),
                    busy=self.app.busy, screen=self.app.screen, game=self.app.selected_game,
                    pending=pending.name if pending else None, scene=game.session.scene if game else None,
                    error=game.error if game else self.app.message or None)


def request(payload, directory):
    global _host, _verifying
    message = json.loads(payload)
    if message.get('operation') == 'verify':
        _verifying = True
        import exp_ios_probe
        return exp_ios_probe.request(payload, directory)
    if _host is None:
        # Launch-argument diagnostics never open or change a player's library.
        root = None
        if _verifying:
            parent = Path(directory) / 'Verification'
            parent.mkdir(parents=True, exist_ok=True)
            root = Path(tempfile.mkdtemp(prefix='libraries-', dir=parent))
        _host = Host(directory, library_root=root, check_updates=not _verifying)
    return json.dumps(_host.request(message), separators=(',', ':'))
