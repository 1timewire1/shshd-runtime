"""Serial JSON bridge between UIKit and the shared application/presentation.

Swift owns device services only. Imports, menus, hit testing, clocks, game
sessions, layout and saves all run through the desktop application's code.
"""
import json
import logging
from concurrent.futures import Future
from pathlib import Path
import shutil
import tempfile
import time
from types import SimpleNamespace

from ..launcher import APP_NAME
from .drawing import Backend, FrameEncoder

_host = None
_verifying = False
LOG_NAME = 'shshd-runtime.log'
LOG_LIMIT = 2 * 1024 * 1024
# How long side panels turned on in portrait wait for the iPad to turn to landscape before they switch off.
PANELS_ROTATE_MS = 3000


def install_log(directory):
    """The runtime's log in the app's Documents (UIFileSharingEnabled: the Files app shows it under On My iPad), so a
    tester can send what went wrong. One file, started afresh once it passes LOG_LIMIT; warnings and errors only."""
    import logging

    class LogFile(logging.Handler):
        """Appends each record and closes the file again: warnings are rare, and nothing stays open."""
        def __init__(self, path):
            super().__init__(logging.WARNING)
            self.path = path
            self.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))

        def emit(self, record):
            try:
                with open(self.path, 'a', encoding='utf-8') as stream:
                    stream.write(self.format(record) + '\n')
            except OSError:
                pass

    path = Path(directory) / LOG_NAME
    try:
        if path.is_file() and path.stat().st_size > LOG_LIMIT:
            path.replace(path.with_suffix('.log.old'))
    except OSError:
        pass
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, 'ios_runtime_log', False):          # one log at a time: the newest host's
            root.removeHandler(handler)
    handler = LogFile(path)
    handler.ios_runtime_log = True
    root.addHandler(handler)
    if root.level > logging.WARNING or root.level == logging.NOTSET:
        root.setLevel(logging.WARNING)
    return path


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
        from .. import desktop_choice, momentum
        desktop_choice.BACKGROUND_HINTS = True      # the choice shows at once, its hints when worked out (as Android)
        momentum.ENABLED = True                     # flicked lists, the wall and the tree glide on (as Android)
        self.directory = Path(directory)
        install_log(self.directory)
        self.update_future = None
        self.update_request = None
        settings = (Path(library_root).parent if library_root is not None else self.directory / APP_NAME) / 'settings.json'
        # can_quit=False: an iOS app cannot quit or update itself, so the update offer only informs (an OK).
        self.app = Application(file_picker=self.pick, library_root=library_root, url_opener=self.open_url,
                               can_quit=False, settings_path=settings, update_fetcher=self.fetch_release,
                               check_updates=check_updates)
        self.encoder = FrameEncoder()
        self.picker = None
        self.url = None
        self.staging = []
        self.last_active = True
        self.view_size = None           # the view's pixel size, as Swift last sent it
        self.panels_view = None         # [game, 'asked' | 'landscape', ms asked] while a game's side panels are open
        self.app.fixed_window = True    # the window is the view: the side panels never widen it (landscape holds them)
        self.app.render()
        self.input_stamp = self._input_stamp()
        self.generation = 0
        self.frame_stats = FrameStats()      # slow frames, summarised in the runtime log (request)

    def _input_stamp(self):
        game = self.app.game if self.app.screen == 'game' else None
        action = game.session.pending if game else None
        session = game.session if game else None
        return (self.app.input_token(), id(game.session) if game else None, game.menu_open if game else False,
                id(action), action.details.get('page_start') if action else None,
                (session.scene, session.vm.steps_executed) if session else None,
                game.host_prompt is not None if game else False)

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

    def resize(self, size):
        """The app's window at the view's pixel size (Swift sends it with each frame), as a desktop window resized
        by the player: the shared app fits its frames to whatever window it has, so the iPad gets the HD frame at
        its own resolution. The running game shares the window."""
        width, height = (max(320, min(4096, int(value))) for value in size)
        self.view_size = width, height
        if self.app.window is not None and self.app.window.get_size() == (width, height):
            return
        window = self.backend.display.set_mode((width, height))
        self.app.window = window
        if self.app.game is not None:
            self.app.game.window = window

    def panels_orientation(self, elapsed):
        """The side panels want landscape (the iPad's 4:3 holds them beside the game): turning them on in portrait
        asks Swift to turn the app ('landscape'), which holds landscape until the iPad itself is turned, then follows
        the device again. Turned back to portrait afterwards, or not turned within PANELS_ROTATE_MS, the panels switch
        off, and 'release' hands rotation back (a hold the iPad was never turned for ends there too)."""
        game = self.app.game if self.app.screen == 'game' else None
        if game is None or not game.panels_open or self.view_size is None:
            released, self.panels_view = self.panels_view is not None, None
            return 'release' if released else None
        width, height = self.view_size
        state = self.panels_view if self.panels_view is not None and self.panels_view[0] is game else None
        if width > height:
            self.panels_view = [game, 'landscape', 0]
            return None
        if state is None:
            self.panels_view = [game, 'asked', 0]
            return 'landscape'
        state[2] += elapsed
        if state[1] == 'landscape' or state[2] >= PANELS_ROTATE_MS:
            game.toggle_panels()
            self.panels_view = None
            return 'release'
        return None

    def _end_copying(self):
        """The copy of picked files is over (import_copying): the app is free again for the import itself."""
        if self.app.job_kind == 'copying':
            self.app.job = self.app.job_kind = None
            self.app.progress_text = ''

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
            # pygame's mouse events also carry `buttons` (held during a drag: the HD picker's rows scroll by it).
            event = SimpleNamespace(type={'down': b.MOUSEBUTTONDOWN, 'up': b.MOUSEBUTTONUP,
                                          'move': b.MOUSEMOTION}[kind], pos=position, button=1,
                                    buttons=(0, 0, 0) if kind == 'up' else (1, 0, 0))
        elif kind == 'scroll':
            event = SimpleNamespace(type=b.MOUSEWHEEL, x=0, y=event['delta'])
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
                def checkpoint():
                    self.app.game.capture_audio()
                    return self.app.state.checkpoint(self.app.game.session)
                self.app._attempt(checkpoint)

    def request(self, message):
        operation = message.get('operation', 'frame')
        if message.get('size'):
            self.resize(message['size'])
        if 'vibration_available' in message:
            self.backend.vibration_available = message['vibration_available'] is True
        if 'audio_playing' in message:
            self.backend.mixer.playing = dict(message['audio_playing'])
        if 'audio_positions' in message:
            self.backend.mixer.positions = dict(message['audio_positions'])
        verification = {}
        if operation in ('verify_start', 'verify_next'):
            import exp_ios_probe
            if operation == 'verify_start':
                self.test_steps = exp_ios_probe.presentation_steps(self)
                verification['drawing_test'] = exp_ios_probe.drawing_fixture()
                verification['audio_test'] = exp_ios_probe.audio_fixture()
                verification['vibration_test'] = True
            try:
                verification['verification_check'] = next(self.test_steps)
            except StopIteration:
                verification['verification_done'] = True
            except Exception as error:
                # AssertionError can have an empty message. Keep the failed
                # authored check's location in the simulator report.
                import traceback
                raise RuntimeError(''.join(traceback.format_exception(error))) from error
            message = dict(message, elapsed=50)
        elif operation == 'import_copying':
            # Swift is copying the picked files into the app (a 1 GB zip takes a while): the busy screen says so,
            # and nothing else can start meanwhile. 'import' or 'message' ends it.
            names = [str(name) for name in message.get('names', ())]
            self.app.job, self.app.job_kind = Future(), 'copying'
            self.app.progress_text = f'Copying {names[0]} into the app...' if len(names) == 1 else (
                f'Copying {len(names)} files into the app...')
        elif operation == 'import':
            self._end_copying()
            kind = message['kind']
            paths = [Path(path) for path in message['paths']]
            if kind == 'library':
                if len(paths) != 1 or not paths[0].is_dir():
                    raise ValueError(f'Choose one {APP_NAME} library folder')
                self.app._attempt(lambda: self.app.open_library(paths[0], remember=True))
            else:
                self.app._attempt(lambda: self.app.import_paths(paths))
                self.staging.extend(paths)
        elif operation == 'message':
            self._end_copying()
            import logging
            logging.warning('iOS host: %s', message['text'])
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
        orientation = self.panels_orientation(elapsed)
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
        vibrations, self.backend.vibrations = self.backend.vibrations, 0
        if not self.last_active or not self.backend.vibration_available:
            vibrations = 0
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
        if (operation.startswith('verify_') and game
                and str(verification.get('verification_check', '')).endswith('stat-increase sound')):
            verification['verify_effect_audio'] = game.sound_players[-1][1].channel
        return dict(verification, status='ok', frame=frame, audio=audio, keyboard=self.backend.keyboard, picker=picker, open_url=url,
                    orientation=orientation,
                    vibrations=vibrations,
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
    started = time.perf_counter()
    result = _host.request(message)
    if message.get('operation', 'frame') == 'frame':
        _host.frame_stats.add(message, result, (time.perf_counter() - started) * 1000, _host.app.screen,
                              _host.app.window.get_size() if _host.app.window is not None else None)
    return json.dumps(result, separators=(',', ':'))


class FrameStats:
    """Where a slow device's frames go, in the runtime log (the owner's iPad is the only place they show): each
    STATS_MS of play with a frame slower than SLOW_MS writes one line. The interval is Swift's time between frames;
    python is this module's handling of one; engine is Swift's whole call (JSON both ways, Python, the lock) and
    render is CoreGraphics drawing the frame's graph, both for the frame before; png/op are the new picture and
    drawn nodes sent (KB, megapixels)."""
    STATS_MS = 5000
    SLOW_MS = 50

    def __init__(self):
        self.rows = []
        self.span = 0

    def add(self, message, result, python_ms, screen, size=None):
        nodes = (result.get('frame') or {}).get('nodes', ())
        timing = message.get('timing') or {}
        elapsed = max(0, int(message.get('elapsed', 0)))
        self.rows.append((elapsed, python_ms, float(timing.get('engine_ms', 0)), float(timing.get('render_ms', 0)),
                          sum(len(node['png']) for node in nodes if 'png' in node) * 3 / 4 / 1024,
                          sum(node['size'][0] * node['size'][1] for node in nodes if 'ops' in node) / 1e6))
        self.span += elapsed
        if self.span < self.STATS_MS:
            return
        rows, self.rows, self.span = self.rows, [], 0
        if max(row[0] for row in rows) < self.SLOW_MS:
            return
        names = ('interval', 'python', 'engine', 'render', 'png_kb', 'op_mpx')
        columns = list(zip(*rows))
        summary = ' '.join(f'{name} {sum(column) / len(column):.1f}/{max(column):.1f}'
                           for name, column in zip(names, columns))
        logging.warning('frames (%s, %s, %d, mean/max ms): %s', screen, 'x'.join(map(str, size or ())), len(rows), summary)
