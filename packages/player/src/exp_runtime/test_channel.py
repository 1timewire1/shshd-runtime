"""A test channel (shshd-runtime; owner, 2026-11-06): drive the running app from a script, by state rather than by screen taps.

Off unless the environment variable SHSHD_TEST_CHANNEL names a port, or the hidden `test_channel` key of the app's
settings.json does (AppSettings.test_channel). On Android the variable comes from the app's `p4a_env_vars.txt`, which
only `run-as` can write, and `run-as` works only on a debuggable build. On iOS an app gets no environment from its
launch, so the settings key switches it on: the file is in the app's Documents, which a computer writes over the cable
(File Sharing). It listens on 127.0.0.1 only; from a PC, `adb forward tcp:PORT tcp:PORT` (Android) or usbmux's
forwarding (iOS: pymobiledevice3) reaches it over the cable (tools/test_channel.py is the client, `--adb` / `--ios`).
With the channel switched on, the app also loads modules from its data folder's `dev-modules` first
(launcher.install_dev_modules): a changed module tried without a new build.

One command a line, one JSON reply a line. Commands run on the app's own thread, between frames, as input would, so
nothing here races the game. A command that takes time (`run-until`, `wait`) is stepped once a frame and replies when
it's done, so real clocks (fades, timers) run as in play.

    ping                        the app is up
    state                       what's showing: screen, pending story screen and its text/options, prompt, switches
    continue                    a tap on a line or panel (Enter)
    answer N                    pick choice or prompt row N (0 first)
    type TEXT                   type into name entry, then confirm it
    key NAME                    a key press: return, escape, up, down, left, right, space, n, u, ... (the menus' keys)
    pinch FACTOR [MS] [MOVES]   two fingers on the open story tree part to FACTOR times as far apart over MS
                                (default 800) and lift, MOVES moves a frame (default 3); replies with the tree's size
                                before and after
    back                        Android's Back (Escape)
    skip / undo                 Skip Ahead / Undo
    pause / resume              the pause menu
    set KEY on|off              a switch, as Options does (undo, skip_ahead, java_look, arena_minigames, ...)
    aspect 3:4|2:3|9:16|fit|default   General's Aspect Ratio (default: the device's own)
    game shs|cod                pick a game, as the game picker does (`open` needs one picked)
    import PATH                 Add Episodes with that file (Android: one in the app's files folder); waits for it
    window yes|no|ok|LABEL|N    press a button of the menu's open window (`state` shows it as `window`), or the Nth
    reopen TITLE                as `open`, continuing the story from its autosave
    open TITLE                  start the episode whose title contains TITLE (or whose id starts with TITLE), from the
                                beginning; of several copies, the newest import
    run-until KIND [SECONDS]    advance lines until KIND shows (choice, brew_catch, word_game, text_input, prompt,
                                stop = anything Skip Ahead stops at), or SECONDS (default 60) pass
    wait SECONDS                let the app run
    timing on|off               frame times since `on`: fps, median, p90, worst, and the slowest (100 ms+) with
                                the command running and what showed after each
    profile on|off              profile the app's thread (cProfile) between the two; `off` replies with the costliest
                                calls by their own time and by their total (`profile off WORD`: only those whose
                                file or function name contains WORD)
    shot NAME [inline]          save the window as NAME.png in the app's data folder; replies with its path, and with
                                `inline` its PNG too (base64 `png`), for a device whose files a computer can't read
    log [N]                     the app's last N log lines (default 50), kept since the channel opened
    tap X Y                     a tap at window pixel X, Y (as a shot shows it): press and release a frame apart
    drag X1 Y1 X2 Y2 [MS]       press at X1, Y1, move to X2, Y2 over MS (default 300), release
    files [PATH]                what's in the app's data folder (or a folder in it): name, size, whether a folder
    get PATH                    a file in the app's data folder (base64 `data`)
    put PATH BASE64             write a file in the app's data folder (dev-modules/exp_runtime/NAME.py: a module the
                                app loads first, from its next start)
    quit                        close the app, as its window's close does
"""
import base64
import collections
import io
import json
import logging
import os
from pathlib import Path
import queue
import socket
import statistics
import threading
import time

from . import graphics as pygame

def _keys():
    """`key`'s names: the keys this platform's drawing backend knows (iOS's knows the few its host sends and the menus
    read, not every letter)."""
    wanted = {name.lower(): 'K_' + name for name in
              ('RETURN', 'ESCAPE', 'UP', 'DOWN', 'LEFT', 'RIGHT', 'SPACE', 'BACKSPACE', 'TAB')}
    wanted.update({chr(c): 'K_' + chr(c) for c in range(ord('a'), ord('z') + 1)})
    wanted.update({str(d): f'K_{d}' for d in range(10)})
    wanted.update({'enter': 'K_RETURN', 'back': 'K_ESCAPE', 'f5': 'K_F5', 'f9': 'K_F9'})
    keys = {}
    for name, constant in wanted.items():
        code = getattr(pygame, constant, None)
        if code is not None:
            keys[name] = keys[name.upper()] = code
    return keys


KEYS = _keys()
REPLY_TIMEOUT_S = 300
HANG_S = 15                     # the app's thread silent this long: its stacks are written (_watch)
SLOW_MS = 100
TEXT_KEYS = ('text', 'title', 'prompt', 'speaker', 'options')


LOG_LINES = 1000
MAX_FILE_BYTES = 256 * 1024 * 1024


def from_environment(directory, port=None):
    """The channel the environment asks for (SHSHD_TEST_CHANNEL=port), else the hidden settings key's `port`, or None.
    `directory` is where shots go."""
    value = os.environ.get('SHSHD_TEST_CHANNEL', '') or ('' if port is None else str(port))
    if not value.isdigit():
        return None
    try:
        return TestChannel(int(value), Path(directory))
    except OSError as error:
        logging.warning('Test channel could not start: %s', error)
        return None


class _LogLines(logging.Handler):
    """The app's log lines into a deque (the channel's `log`), never raising into the code that logged."""

    def __init__(self, lines):
        super().__init__()
        self.lines = lines

    def emit(self, record):
        try:
            self.lines.append(f'{record.levelname} {record.name}: {record.getMessage()}')
        except Exception:               # noqa: BLE001 -- a test aid must not break logging
            pass


def _log_host_errors():
    """iOS: a request that raises stops the runtime in Swift ("Runtime stopped"), with nothing in the app's log; with
    the channel on, its traceback is logged first (the bridge reads `request` from the module at each call)."""
    import sys
    module = sys.modules.get('exp_runtime.platforms.ios')
    request = getattr(module, 'request', None)
    if request is None or getattr(request, 'logs_errors', False):
        return

    def logged(payload, directory):
        try:
            return request(payload, directory)
        except Exception:
            logging.exception('iOS request failed')
            raise
    logged.logs_errors = True
    module.request = logged


class TestChannel:
    def __init__(self, port, directory):
        self.directory = directory
        self.requests = queue.Queue()
        self.job = None                 # (generator, reply queue) of a command still running
        self.frames = None              # frame times (ms) since `timing on`, or None
        self.slow = []                  # frames of SLOW_MS or more since `timing on`: (ms, command, what showed after)
        self.command = None             # the latest command, for `slow`
        self.profiler = None            # a cProfile.Profile while `profile on`
        self.last = time.perf_counter()
        self.log = collections.deque(maxlen=LOG_LINES)     # the app's log lines since the channel opened (`log`)
        logging.getLogger().addHandler(_LogLines(self.log))
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(('127.0.0.1', port))
        self.server.listen(2)
        threading.Thread(target=self._serve, daemon=True, name='test-channel').start()
        threading.Thread(target=self._watch, daemon=True, name='test-channel-watchdog').start()
        _log_host_errors()
        logging.info('Test channel listening on 127.0.0.1:%s', port)

    def _watch(self):
        """A hang's Python stacks: when the app's thread stops polling for HANG_S, every thread's stack goes to the log
        and to hang-stacks.txt in the channel's folder, once a stall (the iPad's arena entrance stopped the app, its
        window black, with nothing in the log, 2026-11-12)."""
        import sys
        import traceback
        dumped = None
        while True:
            time.sleep(HANG_S / 3)
            last = self.last
            if time.perf_counter() - last < HANG_S or dumped == last:
                continue
            dumped = last
            names = {thread.ident: thread.name for thread in threading.enumerate()}
            text = '\n'.join(f'--- {names.get(ident, ident)}\n' + ''.join(traceback.format_stack(frame))
                             for ident, frame in sys._current_frames().items())
            try:
                Path(self.directory, 'hang-stacks.txt').write_text(text, encoding='utf-8')
            except OSError:
                pass
            logging.warning('App thread silent for %.0f s; stacks:\n%s', time.perf_counter() - last, text)

    # -- the network side (its own thread): lines in, replies out ------------------------------------------------------

    def _serve(self):
        while True:
            try:
                connection, _ = self.server.accept()
            except OSError:
                return
            threading.Thread(target=self._talk, args=(connection,), daemon=True).start()

    def _talk(self, connection):
        with connection, connection.makefile('rw', encoding='utf-8', newline='\n') as stream:
            for line in stream:
                line = line.strip()
                if not line:
                    continue
                reply = queue.Queue()
                self.requests.put((line, reply))
                try:
                    answer = reply.get(timeout=REPLY_TIMEOUT_S)
                except queue.Empty:
                    answer = dict(ok=False, error='timed out')
                stream.write(json.dumps(answer, ensure_ascii=False, default=str) + '\n')
                stream.flush()

    # -- the app's side (its own thread, once a frame) ----------------------------------------------------------------

    def poll(self, app):
        now = time.perf_counter()
        if self.frames is not None:
            ms = (now - self.last) * 1000
            self.frames.append(ms)
            if ms >= SLOW_MS:                           # (what the slow frame ended on, to find what made it slow)
                self.slow.append((ms, self.command, _label(app)))
        self.last = now
        if self.job is not None:
            generator, reply = self.job
            try:
                next(generator)
            except StopIteration as done:
                self.job = None
                reply.put(done.value)
            except Exception as error:                  # a test command must never take the app down
                self.job = None
                reply.put(dict(ok=False, error=f'{type(error).__name__}: {error}'))
            return
        try:
            line, reply = self.requests.get_nowait()
        except queue.Empty:
            return
        self.command = line
        try:
            result = Commands(self, app).run(line)
        except Exception as error:
            reply.put(dict(ok=False, error=f'{type(error).__name__}: {error}'))
            return
        if hasattr(result, '__next__'):
            self.job = (result, reply)
        else:
            reply.put(result)


def _label(app):
    """A few words on what's showing, for a slow frame."""
    game = app.game if app.screen == 'game' else None
    if game is None:
        return app.screen
    action = game.session.pending
    words = [f'scene {game.session.scene}', action.name if action is not None else 'running']
    if game.host_prompt is not None:
        words.append('prompt')
    if game.fade:
        words.append('fade')
    return ', '.join(str(word) for word in words)


class Commands:
    def __init__(self, channel, app):
        self.channel, self.app = channel, app

    @property
    def game(self):
        return self.app.game if self.app.screen == 'game' else None

    def run(self, line):
        name, _, rest = line.partition(' ')
        method = getattr(self, 'do_' + name.replace('-', '_'), None)
        if method is None:
            return dict(ok=False, error=f'unknown command {name!r}')
        return method(rest.strip())

    # -- reading ------------------------------------------------------------------------------------------------------

    def do_ping(self, _):
        import sys
        from .launcher import DEV_MODULES
        dev = next((path for path in sys.path if Path(path).name == DEV_MODULES), None)
        return dict(ok=True, screen=self.app.screen, dev_modules=dev)

    def do_state(self, _=''):
        app, game = self.app, self.game
        out = dict(ok=True, screen=app.screen, stage=getattr(app.shell, 'stage', None) if app.shell else None,
                   message=getattr(app, 'message', None), busy=bool(app.busy),
                   progress=getattr(app, 'progress_text', '') or None)
        prompt = getattr(app.shell, 'prompt', None) if app.shell else None
        if prompt is not None:
            out['menu_prompt'] = str(prompt)[:200]
        window = self._window()
        if window is not None:
            menu = window[0]
            out['window'] = dict(title=str(menu.title), text=str(menu.message)[:400], buttons=[str(item.label) for item in window[1]])
        if game is None:
            return out
        session = game.session
        record = getattr(session.resources, 'record', None) or {}
        out.update(episode=(record.get('titles') or [''])[0], scene=session.scene, paused=game.menu_open,
                   fading=bool(game.fade), notice=game.message if game.message else None, error=game.error,
                   ended=session.episode_ended)
        action = session.pending
        if action is not None:
            out['pending'] = action.name
            out.update({key: action.details[key] for key in TEXT_KEYS if key in action.details})
        if game.host_prompt is not None and game.host_prompt.get('loading'):
            out['prompt'] = dict(loading=True)             # its outcomes still being worked out (the loading band)
        elif game.host_prompt is not None:
            out['prompt'] = dict(title=game.host_prompt['session'].pending.details['title'],
                                 text=game.host_prompt['session'].pending.details['text'],
                                 options=list(game.host_prompt['options']))
        out['switches'] = {key: getattr(game, key) for key in ('undo', 'skip_ahead', 'java_look', 'skip_minigames',
                                                                'choice_hints', 'autoplay') if hasattr(game, key)}
        chain = game._undo_for(session)
        out['undo_saves'] = chain.numbers() if chain is not None else None
        out['can_undo'] = game._undo_ready()
        catch = getattr(session.engine, 'brew_catch', None)
        if catch is not None:
            out['catch'] = dict(score=catch.score, target=catch.target, remaining=catch.remaining, over=catch.over)
        return out

    # -- acting -------------------------------------------------------------------------------------------------------

    def _need_game(self):
        if self.game is None:
            raise ValueError('no story is open')
        return self.game

    def _calm(self):
        game = self.game
        return game is not None and not game.fade and not game.session.transitioning

    def _act(self, act, check=None):
        """A job: wait (3 s at most) for a fade or transition to end, as a player would before tapping; then `act()`
        (or reply with `check()`'s refusal); then wait for what it starts to settle."""
        self._need_game()
        end = time.perf_counter() + 3
        while not self._calm() and time.perf_counter() < end:
            yield
        refusal = check() if check is not None else None
        if refusal is not None:
            return dict(ok=False, error=refusal, state=self.do_state())
        error_before = self.game.error
        act()
        end = time.perf_counter() + 0.4
        while time.perf_counter() < end:
            yield
        end = time.perf_counter() + 3
        while not self._calm() and time.perf_counter() < end:
            yield
        state = self.do_state()
        if self.game is not None and self.game.error and self.game.error != error_before:
            state['ok'] = False                             # (what it did ended in the game's error: say so)
        return dict(state, reached=True)

    def do_continue(self, _):
        return self._act(lambda: self.game.command(('continue',)))

    def do_answer(self, rest):
        index = int(rest)

        def act():
            game = self.game
            action = game.session.pending
            if game.host_prompt is None and action is not None and action.name == 'choice' and not game.session.choice_ready:
                game.session.tick(250)                      # (the choice's entrance: a tap waits for it too)
            game.command(('choose', index))

        def check():
            """A row a player couldn't tap is refused here, not handed to the game (where it would be an error)."""
            game = self.game
            if game.host_prompt is not None:
                count, enabled = len(game.host_prompt['options']), None
            else:
                action = game.session.pending
                if action is None or action.name != 'choice':
                    return None                                 # (other screens' rows: the game decides)
                count, enabled = len(action.details['values']), action.details['enabled']
            if not 0 <= index < count or (enabled is not None and not enabled[index]):
                return f'no option {index} to pick (0 to {count - 1}, enabled ones only)'
            return None
        return self._act(act, check)

    def do_type(self, rest):
        self._need_game()
        for character in rest:
            pygame.event.post(pygame.event.Event(pygame.TEXTINPUT, text=character))
        return self._then_key('return')

    def do_key(self, rest):
        return self._then_key(rest.strip())

    def do_pinch(self, rest):
        """`pinch FACTOR [MS] [MOVES]`: two fingers on the open story tree, a quarter of its width apart about its middle,
        part to FACTOR times that over MS (default 800) and lift, moving MOVES times a frame (default 3: a touch screen
        reports more often than a phone draws). They go through Android's own pinch (Host.finger); on a desktop, which
        has no pinch of its own, through a stand-in of it."""
        parts = rest.split()
        factor = float(parts[0]) if parts else 2.0
        ms = float(parts[1]) if len(parts) > 1 else 800.0
        moves = max(1, int(parts[2])) if len(parts) > 2 else 3
        panels = getattr(self.game, 'side_panels', None)
        if panels is None or panels.tree_rect is None:
            return dict(ok=False, error='the story tree is not showing (key tab opens the panels)')
        finger = getattr(self.app, 'finger_input', None)
        if finger is None:
            from .platforms.android import Host
            host = Host.__new__(Host)
            host.app = self.app
            finger = host.finger
        return self._pinch(finger, panels, factor, ms, moves)

    def _pinch(self, finger, panels, factor, ms, moves):
        from types import SimpleNamespace
        width, height = self.app.window.get_size()
        cx, cy = panels.tree_rect.center
        half = panels.tree_rect.width / 8

        def touch(kind, finger_id, x):
            finger(SimpleNamespace(type=kind, finger_id=finger_id, x=x / width, y=cy / height, dx=0, dy=0, touch_id=0),
                   check_sdl=False)
        touch(pygame.FINGERDOWN, 9001, cx - half)
        touch(pygame.FINGERDOWN, 9002, cx + half)
        before, began, last, done = panels._zoom_size(), time.perf_counter(), half, False
        while not done:
            yield
            progress = min(1.0, (time.perf_counter() - began) * 1000 / ms)
            done = progress >= 1.0
            target = half * (1 + (factor - 1) * progress)
            for step in range(1, moves + 1):
                at = last + (target - last) * step / moves
                touch(pygame.FINGERMOTION, 9001, cx - at)
                touch(pygame.FINGERMOTION, 9002, cx + at)
            last = target
        yield
        touch(pygame.FINGERUP, 9001, cx - last)
        touch(pygame.FINGERUP, 9002, cx + last)
        result = yield from self._settled(0.3)
        return dict(result, tree_size=[round(before, 2), round(panels._zoom_size(), 2)])

    def do_back(self, _):
        return self._then_key('escape')

    def _then_key(self, name):
        code = KEYS.get(name)
        if code is None:
            return dict(ok=False, error=f'unknown key {name!r}')
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=code, mod=0, unicode=''))
        pygame.event.post(pygame.event.Event(pygame.KEYUP, key=code, mod=0, unicode=''))
        return self._settled(0.3)

    def do_skip(self, _):
        return self._act(lambda: self.game.command(('skip_ahead',)),
                         lambda: None if self.game.skip_ahead else 'Allow Skip Ahead is off')

    def do_undo(self, _):
        return self._act(lambda: self.game.command(('undo',)),
                         lambda: None if self.game._undo_ready() else 'nothing to undo')

    def do_pause(self, _):
        self._need_game().command(('menu',))
        return self._settled(0.6)

    def do_resume(self, _):
        self._need_game().command(('resume',))
        return self._settled(0.6)

    def do_set(self, rest):
        key, _, value = rest.partition(' ')
        wanted = value.strip() in ('on', 'true', '1')
        state = self.app.state
        if state is None or type(getattr(state, key, None)) is not bool:
            return dict(ok=False, error=f'unknown switch {key!r}')
        setattr(state, key, wanted)                                 # as Options' toggle does: kept, then passed on
        state.persist()
        apply = getattr(self.app, 'apply_' + key, None)
        if apply is not None:
            apply()
        elif self.app.game is not None and hasattr(self.app.game, key):
            setattr(self.app.game, key, wanted)
        return dict(ok=True, key=key, value=getattr(state, key))

    def do_aspect(self, rest):
        """General's Aspect Ratio (frame_shape.CHOICES, or `default`), as its choice page sets it."""
        from .frame_shape import CHOICES
        choice = rest.strip().lower()
        if choice not in (*CHOICES, 'default'):
            return dict(ok=False, error=f'aspect is one of {", ".join(CHOICES)} or default')
        self.app.set_aspect_ratio(None if choice == 'default' else choice)
        return dict(ok=True, aspect=self.app.settings.aspect(self.app.fixed_window))

    def do_game(self, rest):
        key = rest.strip().lower()
        if self.app.game is not None:
            return dict(ok=False, error='a story is open: leave it first')
        if getattr(self.app, 'selected_game', None) != key or self.app.library is None:
            self.app.choose_game(key)
        return self._settled(0.5)

    def do_reopen(self, rest):
        """`open`, but continuing the story from its autosave, as the menu's Continue does."""
        result = yield from self.do_open(rest, resume=True)
        return result

    def do_open(self, rest, resume=False):
        library, state = self.app.library, self.app.state
        if library is None or state is None:
            return dict(ok=False, error='no library is open')
        wanted = rest.lower()
        found = [record for record in library.episodes if record['id'].startswith(wanted) and len(wanted) >= 6]
        found = found or [record for record in library.episodes
                          if any(wanted in (title or '').lower() for title in record.get('titles', ()))]
        if not found:
            return dict(ok=False, error=f'no episode titled {rest!r}')
        # Several copies (an episode imported again after a rebuild keeps both): the newest import, the library's
        # last; an id prefix picks another. The reply says which, and how many matched.
        record = found[-1]
        result = yield from self._open(record['id'], resume)
        return dict(result, opened=record['id'][:12], copies=len(found))

    def _open(self, record_id, resume=False):
        """A job: wait for the app to be free (first boot builds previews), start the episode, wait for its first screen."""
        end = time.perf_counter() + 600
        while self.app.busy and time.perf_counter() < end:
            yield
        self.app.state.selected = self.app.selected = record_id
        self.app.enter_episode(resume=resume)
        result = yield from self._until(lambda: self.game is not None and self.game.session.pending is not None, 60)
        return result

    def _window(self):
        """The menu window that's open on top (a confirmation, a notice, the launch's questions): (menu, its buttons), or
        None. A game's own window gives string ids for its text, this player's own gives text."""
        shell = self.app.shell
        stack = getattr(shell, 'stack', None)
        if stack is None or not stack.stack or getattr(shell, 'data', None) is None:
            return None
        return shell.data.menu(stack.current), shell.data.items(stack.current)

    def do_window(self, rest):
        """Press a button of the open window: `yes` (its verb, the last), `no`, `ok`, a label, or its position (0 first)."""
        window = self._window()
        if window is None:
            return dict(ok=False, error='no window is open')
        buttons, wanted = window[1], rest.strip().lower()
        if wanted.isdigit():
            found = buttons[int(wanted)] if int(wanted) < len(buttons) else None
        else:
            found = buttons[-1] if wanted == 'yes' else next((b for b in buttons if str(b.label).lower() == wanted), None)
        if found is None:
            return dict(ok=False, error=f'no button {rest!r}: {[str(b.label) for b in buttons]}')
        self.app.shell.stack.press(found)
        return self._idle(60)

    def do_import(self, rest):
        """Add Episodes with a file the app can read (on Android, one in its own files folder): replies once the import
        is done, with its message, or with a window if it asks something."""
        path = Path(rest.strip())
        if not path.exists():
            return dict(ok=False, error=f'no file {rest!r}')
        self.app.import_paths([path])
        return self._idle(600)

    def _idle(self, seconds):
        """A job: until the app is free (no import or other work) or a window asks something; then the state."""
        return self._until(lambda: not self.app.busy and getattr(self.app, 'job', None) is None, seconds, quiet=True)

    def do_wait(self, rest):
        return self._settled(float(rest or 1))

    def do_run_until(self, rest):
        parts = rest.split()
        kind, seconds = (parts[0] if parts else 'stop'), float(parts[1]) if len(parts) > 1 else 60.0
        from .skip_ahead import PASSES
        from .undo import is_stop

        def reached():
            game = self.game
            if game is None:
                return False
            action = game.session.pending
            if game.host_prompt is not None:                # a mini-game's skip prompt: that game (or a stop it can't pass)
                return not game.host_prompt.get('loading')  # (once its outcomes are worked out)
            if action is None or game.session.episode_ended:
                return True
            if kind == 'stop':
                return is_stop(action)
            if action.name == kind:
                return True
            # Another stop it can't pass (a choice on the way to a game): reply now, with it, rather than wait it out.
            return self._calm() and is_stop(action) and not (action.name == 'presentation' and kind != 'presentation')

        def step():
            game = self.game
            if game is None or game.fade or game.menu_open or game.session.transitioning:
                return
            action = game.session.pending
            if action is not None and action.name in PASSES and game.host_prompt is None:
                game.command(('continue',))
            elif action is not None and action.name == 'presentation' and kind != 'presentation':
                game.command(('continue',))
        result = yield from self._until(reached, seconds, step, every=0.12)
        action = self.game.session.pending if self.game is not None else None
        result['reached'] = bool(result.get('reached')) and (kind in ('stop', 'any') or (action is not None and action.name == kind)
                                                               or (kind == 'prompt' and self.game.host_prompt is not None
                                                                   and not self.game.host_prompt.get('loading')))
        return result

    def do_timing(self, rest):
        channel = self.channel
        if rest == 'on':
            channel.frames, channel.slow = [], []
            return dict(ok=True)
        frames, channel.frames = channel.frames or [], None if rest == 'off' else channel.frames
        if not frames:
            return dict(ok=True, frames=0)
        ordered = sorted(frames)
        return dict(ok=True, frames=len(frames), fps=round(1000 * len(frames) / sum(frames), 1),
                    median_ms=round(statistics.median(frames), 1), p90_ms=round(ordered[int(.9 * (len(ordered) - 1))], 1),
                    worst_ms=round(ordered[-1], 1),
                    slow=[dict(ms=round(ms, 1), command=command, after=label)
                          for ms, command, label in sorted(channel.slow, reverse=True)[:8]])

    def do_profile(self, rest):
        import cProfile
        import pstats
        channel = self.channel
        if rest == 'on':
            if channel.profiler is None:
                channel.profiler = cProfile.Profile()
                channel.profiler.enable()                   # (this is the app's thread: poll runs on it)
            return dict(ok=True)
        if channel.profiler is None:
            return dict(ok=False, error='profile is off')
        only = rest.partition(' ')[2].strip()              # `profile off WORD`: only calls whose file or name has WORD
        channel.profiler.disable()
        stats, channel.profiler = pstats.Stats(channel.profiler), None

        def top(key, count=15):
            rows = [item for item in stats.stats.items() if not only or any(only in str(part) for part in item[0])]
            rows = sorted(rows, key=lambda item: item[1][key], reverse=True)[:count]
            return [dict(call=f'{Path(name[0]).name}:{name[1]} {name[2]}', calls=row[1], own_ms=round(row[2] * 1000, 1),
                         total_ms=round(row[3] * 1000, 1)) for name, row in rows]
        return dict(ok=True, own=top(2), total=top(3))

    def do_shot(self, rest):
        words = rest.split()
        inline = 'inline' in words[1:]
        name = ''.join(c for c in (words[0] if words else 'shot') if c.isalnum() or c in '-_') or 'shot'
        path = self.channel.directory / f'{name}.png'
        path.parent.mkdir(parents=True, exist_ok=True)
        window = self._window_picture()
        pygame.image.save(window, str(path))
        out = dict(ok=True, path=str(path), size=list(window.get_size()))
        if inline:
            out['png'] = base64.b64encode(path.read_bytes()).decode('ascii')
        return out

    def _window_picture(self):
        """The window as a surface: the host's own picture of it where it draws natively (iOS: `snapshot`), else the
        display surface."""
        snapshot = getattr(self.app, 'host_snapshot', None)
        picture = snapshot() if snapshot is not None else None
        return picture if picture is not None else pygame.display.get_surface()

    def do_log(self, rest):
        count = int(rest) if rest.strip().isdigit() else 50
        return dict(ok=True, lines=list(self.channel.log)[-count:])

    # -- pointer ------------------------------------------------------------------------------------------------------

    def _pointer(self, kind, pos, **extra):
        self.app.handle_event(pygame.event.Event(kind, pos=(round(pos[0]), round(pos[1])), **extra))

    def do_tap(self, rest):
        x, y = (float(v) for v in rest.split()[:2])
        self._pointer(pygame.MOUSEBUTTONDOWN, (x, y), button=1)
        yield
        self._pointer(pygame.MOUSEBUTTONUP, (x, y), button=1)
        result = yield from self._settled(0.3)
        return result

    def do_drag(self, rest):
        values = [float(v) for v in rest.split()]
        (x1, y1, x2, y2), ms = values[:4], (values[4] if len(values) > 4 else 300.)
        self._pointer(pygame.MOUSEBUTTONDOWN, (x1, y1), button=1)
        began = time.perf_counter()
        last = (x1, y1)
        while True:
            yield
            k = min(1., (time.perf_counter() - began) * 1000 / max(1., ms))
            here = (x1 + (x2 - x1) * k, y1 + (y2 - y1) * k)
            self._pointer(pygame.MOUSEMOTION, here, rel=(round(here[0] - last[0]), round(here[1] - last[1])),
                          buttons=(1, 0, 0))
            last = here
            if k >= 1:
                break
        self._pointer(pygame.MOUSEBUTTONUP, (x2, y2), button=1)
        result = yield from self._settled(0.3)
        return result

    # -- the app's data folder ----------------------------------------------------------------------------------------

    def _data_path(self, rest):
        """A path within the app's data folder (no way out of it)."""
        from .launcher import user_data_directory
        base = user_data_directory().resolve()
        path = (base / rest.strip().lstrip('/\\')).resolve() if rest.strip() else base
        if path != base and base not in path.parents:
            raise ValueError('outside the app\'s data folder')
        return path

    def do_files(self, rest):
        path = self._data_path(rest)
        if not path.is_dir():
            return dict(ok=False, error=f'not a folder: {rest}')
        entries = [dict(name=entry.name, folder=entry.is_dir(), size=None if entry.is_dir() else entry.stat().st_size)
                   for entry in sorted(path.iterdir(), key=lambda entry: entry.name.lower())]
        return dict(ok=True, path=str(path), entries=entries)

    def do_get(self, rest):
        path = self._data_path(rest)
        if not path.is_file():
            return dict(ok=False, error=f'no file: {rest}')
        if path.stat().st_size > MAX_FILE_BYTES:
            return dict(ok=False, error='too large')
        return dict(ok=True, path=str(path), data=base64.b64encode(path.read_bytes()).decode('ascii'))

    def do_put(self, rest):
        name, _, data = rest.partition(' ')
        path = self._data_path(name)
        payload = base64.b64decode(data.strip(), validate=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_name(path.name + '.part')
        part.write_bytes(payload)
        part.replace(path)
        return dict(ok=True, path=str(path), size=len(payload))

    def do_quit(self, _):
        self.app.quit_requested = True
        return dict(ok=True)

    # -- helpers ------------------------------------------------------------------------------------------------------

    def _settled(self, seconds=0.5):
        """Let the app run `seconds` (a fade, a transition), then reply with the state."""
        return self._until(lambda: False, seconds, quiet=True)

    def _until(self, done, seconds, step=None, every=0.0, quiet=False):
        """A job: a frame at a time until `done()` or `seconds` pass (calling `step()` at most every `every` s), then the
        state."""
        end, last_step = time.perf_counter() + seconds, 0.0
        while True:
            if done():
                return dict(self.do_state(), reached=True)
            now = time.perf_counter()
            if now >= end:
                return dict(self.do_state(), reached=quiet)
            if step is not None and now - last_step >= every:
                last_step = now
                step()
            yield
