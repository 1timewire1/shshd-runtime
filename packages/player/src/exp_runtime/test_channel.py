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
    state                       what's showing: screen, pending story screen and its text/options, prompt, switches;
                                `minigame` for an open mini-game (minigame_report: its score, time, what it waits for;
                                a Claire Hart round's listed names, hint, power-ups and view); `window` for the window
                                on top (its source: story, message, update, picker, options or menu); `panels` where
                                an episode has a Decision Tree or Faceplace wall; `picker` (the look picker's portraits),
                                `input_error`, `page` (an Options page, in a story too), `games` (the chooser's), `job`
    continue                    a tap on a line or panel (Enter)
    answer N                    pick choice or prompt row N (0 first); on the look picker, bring portrait N to the front
    type TEXT                   type into name entry (or a screen's field: a search, the browser's path), then Enter
    key NAME [MS]               a key press: return, escape, up, down, left, right, space, n, u, ... (the menus' keys);
                                held MS milliseconds if given
    panels open|close           the side panels, as Tab (beside the game where there's room, else over the screen)
    tree                        the Decision Tree's scenes: serial, label, current, which a warp reaches, Rewind and
                                Fast Forward's scenes; `tree warp SERIAL|LABEL`, `tree rewind`, `tree forward` tap them
                                (the panels open first; locked, its "Locked" window)
    wall                        the Faceplace wall's posts (sender, text, links); `wall link N` taps post N's link
                                (its "Exit Game?" window: `window no`)
    picker                      the episode picker's rows and tiles (id, title, saved, finished, info) and its popup;
                                `picker tile TITLE|ID`, `picker new|continue|delete|close` (the popup), `picker info
                                TITLE|ID`, `picker restore`, `picker back`
    ticks                       the open episode tick list (Data Management's, or the chooser's): each episode, ticked
    buttons / button WORDS      a screen outside a story and the HD menus (the chooser, Setup, Bulk Import, the file
                                browser, a game's menus without HD art): its buttons by their command's words, and a
                                tap on one (`button file NAME`, `button up`, `button folder`, `button episode TITLE`)
    pinch FACTOR [MS] [MOVES]   two fingers on the open story tree (or a Claire Hart round) part to FACTOR times as far
                                apart over MS (default 800) and lift, MOVES moves a frame (default 3); replies with the
                                tree's size (the round's zoom) before and after
    play press [N]              the open mini-game's go-ahead or button; a cell 0-8 in SHS '11's games; a key code on
                                New Rules' arena (-5 OK, -1 to -4 the joystick, 48-57 numbers), a row on its menu;
                                football's tap, or a play 0-8; the word game's option N
    play cells A B C...         the word grid: a drag through those cells (0 first, row by row); `play press` a tap off
                                the board
    play find NAME|SLOT         a Claire Hart round: a real tap on that listed object, where nothing listed covers it
                                (the view centred on it first if it's off screen); `play miss` taps an empty spot
    play hint | pick SLOT | continue | powerup NAME   a round's hint orb, a name for the Psychic Locator, the Level
                                Summary's Continue, or focus / locator / clairvoyance / time_warp
    back                        Android's Back (Escape)
    skip / undo                 Skip Ahead / Undo
    pause / resume              the pause menu
    menu                        the pause menu's Main Menu: the story saved and kept for Resume, the main menu shown
    main BUTTON                 a main menu button: play (the tiles), airing, demand, options, help, more; `back` returns
    set KEY on|off              a switch, as Options does (undo, skip_ahead, java_look, arena_minigames, ...);
                                `set dsi_pixels sharp|smooth` (Extras' DSi Backgrounds is these two: `set dsi_backgrounds
                                on` with the pixels), `set preferred_language en|fr|it|de|es` (the titles,
                                and the DSi's, '11's and the Creator's stories where they have it), any choice
                                option (title_look, title_music...), `set start_in auto|games|shs|cod`,
                                `set music_volume|sound_volume 0-100`
    options [PAGE]              Options at PAGE: general, sound, extras, addons, per_game, controller, data, library,
                                episodes, progress, sync, or a screen name (choice:start_in...): the main menu's, the
                                game chooser's (no game open), or in a story the pause menu's (opened first)
    rows                        the open menu page's rows: label, kind, key, value (the pause menu itself too: Resume,
                                Skip Ahead, Undo, Options, Help, Main Menu; Help & About's pages); a text page (a Help
                                page, Library Info, a Quest Journal entry) gives its title and text, its links as rows
    press LABEL                 a row of the open Options page, as a tap (its label or key): pages open, switches flip,
                                choices open their page, picks choose, actions run (their question shows as `window`)
    do ACTION                   a Data Management action by its key, as its row (verify_library, back_up, mark_read...)
    pick TITLE|ID               tick or untick an episode in Data Management's tick list (Mark as Finished, Delete...)
    act                         the tick list's verb button (Save, Delete, Export, Reset)
    aspect 3:4|2:3|9:16|fit|default   General's Aspect Ratio (default: the device's own)
    resize W H                  a computer's window resized to W x H pixels, as a drag would (with `aspect fit`, any
                                shape: 9:20 is `resize 540 1200`); not on a phone, whose window is its screen
    game shs|cod|chooser        pick a game, as the game picker does (`open` needs one picked); a story held for
                                Resume is saved and let go, as the main menu's switch button does; `chooser` shows the
                                game chooser, as Switch Game does where the other game has no library
    import PATH                 Add Content with that file (Android: one in the app's files folder); waits for it
    window yes|no|ok|LABEL|N    press a button of the window on top (`state` shows it: a story's own "Exit Game?" or
                                "Locked", the app's message card or Update Available, the picker's info card, the
                                chooser's question, the menus' windows) by its words, its id, or the Nth
    reopen TITLE                as `open`, continuing the story from its autosave
    open TITLE                  start the episode whose title contains TITLE (or whose id starts with TITLE), from the
                                beginning; of several copies, the newest import
    run-until KIND [SECONDS]    advance lines until KIND shows (choice, brew_catch, word_game, text_input, prompt,
                                stop = anything Skip Ahead stops at), or SECONDS (default 60) pass
    wait SECONDS                let the app run
    timing on|off               frame times since `on`: fps, median, p90, worst, and the slowest (100 ms+) with
                                the command running and what showed after each; `timing off groups` adds them by
                                what each frame showed (its screen) and whether a sound started in it, and on iOS
                                Python's and the host's drawing time per frame
    episodes [TEXT]             the library's episodes (title containing TEXT, or id starting with it): id, title,
                                pack, episode, version, whether a saved game holds it
    addons                      the library's add-ons: name, revision, id
    delete ID|TITLE             Delete Episodes for one episode, as Data Management does (its saves, screenshots,
                                previews and Decision Tree too); an id prefix (6+) or a title only one matches
    delete-addon NAME|ID        Delete for one add-on, as Data Management's Add-Ons page does
    memory                      the app process's memory in MB: resident now and its peak (iOS: Jetsam's footprint)
    profile on|off              profile the app's thread (cProfile) between the two; `off` replies with the costliest
                                calls by their own time and by their total (`profile off WORD`: only those whose
                                file or function name contains WORD; `profile off callers NAME`: the callers
                                of the functions named NAME, e.g. fill or blit, by their time in it)
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
    sync receive                Data Management's Sync Devices, Receive (the open game's menus, or the chooser's
                                Options), as the rows do
    sync send [shs|cod|both] [nobackup]   Send with every switch on (Back Up Receiver First too, unless nobackup; the
                                chooser's Games row as named), then Find Receiver
    sync devices [SECONDS]      the receivers found so far (waits up to SECONDS for one)
    sync choose NAME|N          connect to that receiver (the name as listed, or its position)
    sync answer yes|no          this device's answer to the open question (the code, or a whole library)
    sync wait [SECONDS]         until the sync ends or asks this device something; replies with `sync status`
    sync status                 the page, the session (status, peer, code, progress), the open question, the last result
    sync ok / sync stop         close the result's notice / leave Sync (its search or waiting closed)
"""
import base64
import collections
import json
import logging
import math
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
    wanted.update({'enter': 'K_RETURN', 'back': 'K_ESCAPE', 'f5': 'K_F5', 'f9': 'K_F9',
                   'pageup': 'K_PAGEUP', 'pagedown': 'K_PAGEDOWN',      # (a scrolling page's own keys)
                   'f11': 'K_F11'})                                     # (the desktop's full screen)
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
        self.tags = []                  # each frame since `timing on`: (ms, what showed, a sound started, python, render)
        self.sounds = None              # the sound counters at the frame before (_frame_tag)
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
            try:
                self.tags.append(_frame_tag(self, app, ms))
            except Exception:                           # (a tag is for `timing off groups` only: never the frame)
                self.tags.append((ms, '?', False, None, None))
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


def _sound_counters(app):
    """The counters a started sound moves: the open story's engine's, and the drawing backend's mixer's (iOS)."""
    game = app.game if app.screen == 'game' else None
    engine = game.session.engine if game is not None else None
    mixer = getattr(pygame, 'mixer', None)
    return getattr(engine, 'sound_serial', None), getattr(mixer, 'sound_serial', None)


def _host_times():
    """iOS: Python's time on the frame before and the host's CoreGraphics drawing of the one before that (ms), from
    the frame stats the iOS module keeps (platforms.ios.FrameStats); (None, None) elsewhere."""
    import sys
    module = sys.modules.get('exp_runtime.platforms.ios')
    rows = getattr(getattr(getattr(module, '_host', None), 'frame_stats', None), 'rows', None)
    if not rows:
        return None, None
    return rows[-1][1], rows[-1][3]


def _frame_tag(channel, app, ms):
    """One frame for `timing off groups`: (ms, what showed, whether a sound started, python ms, render ms)."""
    counters = _sound_counters(app)
    sound = channel.sounds is not None and any(now is not None and before is not None and now != before
                                               for now, before in zip(counters, channel.sounds))
    channel.sounds = counters
    game = app.game if app.screen == 'game' else None
    if game is None:
        what = app.screen
    elif game.menu_open:
        what = 'pause'
    elif game.host_prompt is not None:
        what = 'prompt'
    else:
        action = game.session.pending
        what = action.name if action is not None else 'running'
    return (ms, what, sound) + _host_times()


def _group_frames(tags):
    """`timing off groups`: the frames by what showed and whether a sound started, each with its count, median, p90,
    worst and how many took over 20 ms (iOS: Python's and the host's median and worst too), most frames first."""
    groups = collections.defaultdict(list)
    for tag in tags:
        groups[(tag[1], tag[2])].append(tag)
    out = []
    for (what, sound), rows in sorted(groups.items(), key=lambda item: -len(item[1])):
        times = sorted(row[0] for row in rows)
        entry = dict(showed=what, sound=sound, frames=len(times), median_ms=round(statistics.median(times), 1),
                     p90_ms=round(times[math.ceil(.9 * len(times)) - 1], 1), worst_ms=round(times[-1], 1),
                     over_20ms=sum(1 for t in times if t > 20))
        for index, name in ((3, 'python'), (4, 'render')):
            values = [row[index] for row in rows if row[index] is not None]
            if values:
                entry[name + '_median_ms'] = round(statistics.median(values), 1)
                entry[name + '_worst_ms'] = round(max(values), 1)
        out.append(entry)
    return out


def _memory():
    """The process's memory in MB: resident now and its peak, by the platform's own count."""
    import sys
    out = {}
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD),
                        ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
                        ('QuotaPeakPagedPoolUsage', ctypes.c_size_t), ('QuotaPagedPoolUsage', ctypes.c_size_t),
                        ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t), ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                        ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t)]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.windll.kernel32
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        kernel.K32GetProcessMemoryInfo.argtypes = (wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD)
        if kernel.K32GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            out.update(resident_mb=counters.WorkingSetSize / 2**20, peak_mb=counters.PeakWorkingSetSize / 2**20,
                       committed_mb=counters.PagefileUsage / 2**20)
    elif Path('/proc/self/status').exists():           # Linux, Android
        keys = {'VmRSS': 'resident_mb', 'VmHWM': 'peak_mb', 'VmSwap': 'swapped_mb'}
        for line in Path('/proc/self/status').read_text().splitlines():
            key, _, value = line.partition(':')
            if key in keys and value.strip().endswith('kB'):
                out[keys[key]] = int(value.split()[0]) / 1024
    else:                                               # iOS, macOS
        try:
            import resource
            out['peak_mb'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20     # (bytes on Darwin)
        except (ImportError, OSError):
            pass
        try:
            out.update(_mach_footprint())
        except Exception as error:                      # (a best effort: the peak above still answers)
            out['footprint_error'] = f'{type(error).__name__}: {error}'
    return {key: round(value, 1) if isinstance(value, float) else value for key, value in out.items()}


def _mach_footprint():
    """Darwin's task_info(TASK_VM_INFO): resident, its peak and phys_footprint, the figure Jetsam ends an app by (MB)."""
    import ctypes
    import ctypes.util
    system = ctypes.CDLL(ctypes.util.find_library('System') or '/usr/lib/libSystem.B.dylib')
    task = ctypes.c_uint.in_dll(system, 'mach_task_self_')
    info = (ctypes.c_uint64 * 40)()
    count = ctypes.c_uint(38)                           # TASK_VM_INFO_REV0_COUNT: through phys_footprint
    if system.task_info(task, 22, ctypes.byref(info), ctypes.byref(count)) != 0:     # 22: TASK_VM_INFO
        raise OSError('task_info failed')
    return dict(resident_mb=info[2] / 2**20, resident_peak_mb=info[3] / 2**20, footprint_mb=info[18] / 2**20)


class Commands:
    def __init__(self, channel, app):
        self.channel, self.app = channel, app

    @property
    def game(self):
        return self.app.game if getattr(self.app, 'screen', None) == 'game' else None

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
                   progress=getattr(app, 'progress_text', '') or None, game=getattr(app, 'selected_game', None))
        if app.busy and getattr(app, 'job_kind', None) == 'data':
            out['job'] = app.job_title                          # a Data Management job's busy card
        if app.shell is not None and getattr(app.shell, 'pause_open', False):
            out['page'] = app.shell.pause.state.screen          # the Options page showing over the main menu
        opened = getattr(app, 'app_options_open', None)
        if opened is not None and opened():
            out['page'] = app.app_screens.options.menu.state.screen     # the chooser's Options
        if app.screen == 'games' and hasattr(app, 'games_with_libraries'):
            out['games'] = list(app.games_with_libraries())     # the chooser's games that have a library
        picker = getattr(app, 'picker', None)
        if app.screen == 'picker' and picker is not None:
            out['picker'] = dict(style=getattr(app, 'picker_style', None), selected=picker.selected,
                                 popup=picker.popup['id'][:12] if picker.popup else None,
                                 ticks=getattr(picker, 'choosing', None) is not None)
        window = self._window()
        if window is not None:
            out['window'] = self._window_words(window)
        if game is None:
            return out
        session = game.session
        record = getattr(session.resources, 'record', None) or {}
        # The story's toast ("Progress saved") while it shows: it goes after 3.5 s (Desktop.message_until).
        toast = game.message if game.message and pygame.time.get_ticks() < getattr(game, 'message_until', 0) else None
        out.update(episode=(record.get('titles') or [''])[0], scene=session.scene, paused=game.menu_open,
                   fading=bool(game.fade), notice=toast, error=game.error, ended=session.episode_ended)
        if game.menu_open:
            out['page'] = game.pause_hd.state.screen            # the pause menu's page (`rows` reads it)
        action = session.pending
        if action is not None:
            out['pending'] = action.name
            out.update({key: action.details[key] for key in TEXT_KEYS if key in action.details})
            if action.name == 'text_input' and getattr(game, 'input_error', None):
                out['input_error'] = str(game.input_error)      # a name the game turned down, as its alert says
            motion = getattr(session.engine, 'dialogue_animation', None)
            if action.name == 'dialogue' and motion is not None:
                # The page's Text Animation and how far it is out (dialogue_animation.TEXT_ANIMATIONS).
                out['reveal'] = dict(mode=getattr(motion, 'text_mode', 'letters'), complete=motion.complete,
                                     revealed=motion.revealed, length=motion.text_length)
            picker = getattr(session.engine, 'character_picker', None)
            if action.name == 'character_picker' and picker is not None:
                # The portraits by their original place (`answer N` brings one to the front, `continue` confirms).
                out['picker'] = dict(characters=list(picker.characters), selected=picker.selected,
                                     moving=bool(picker.moving))
        if game.host_prompt is not None and game.host_prompt.get('loading'):
            out['prompt'] = dict(loading=True)             # its outcomes still being worked out (the loading band)
        elif game.host_prompt is not None:
            out['prompt'] = dict(title=game.host_prompt['session'].pending.details['title'],
                                 text=game.host_prompt['session'].pending.details['text'],
                                 options=list(game.host_prompt['options']))
        out['switches'] = {key: getattr(game, key) for key in ('undo', 'skip_ahead', 'java_look', 'hollywood_art', 'dsi_backgrounds', 'dsi_pixels', 'preferred_language', 'dsi_language', 'shs11_language', 'story_language', 'skip_minigames',
                                                                'choice_hints', 'autoplay') if hasattr(game, key)}
        panels = self._panels_state(game)
        if panels is not None:
            out['panels'] = panels
        chain = game._undo_for(session)
        out['undo_saves'] = chain.numbers() if chain is not None else None
        out['can_undo'] = game._undo_ready()
        badge = getattr(session.engine, 'scene_badge', None)
        if badge is not None:
            out['badge'] = dict(text=badge.text, asset=badge.asset_id)     # the scene's location/time badge (service 90)
        catch = getattr(session.engine, 'brew_catch', None)
        if catch is not None:
            out['catch'] = dict(score=catch.score, target=catch.target, remaining=catch.remaining, over=catch.over)
        from .minigame_report import describe
        minigame = describe(session, skippable=game.host_prompt is not None)
        if minigame is not None:
            out['minigame'] = minigame
            view = getattr(getattr(game, 'claire_round_renderer', None), 'view', None)
            if minigame['kind'] == 'claire_round' and view is not None:
                minigame['view'] = dict(zoom=round(view.zoom, 3), centre=[round(view.cx), round(view.cy)])
        return out

    @staticmethod
    def _panels_state(game):
        """The side panels where an episode uses them (the Decision Tree, the Faceplace wall): beside the game or over
        the screen, the corner button, the Faceplace alert, the warp lock; None in an episode with neither."""
        try:
            tree, wall = game.panels_used()
        except AttributeError:
            return None
        if not (tree or wall):
            return None
        engine = game.session.engine
        toast = getattr(engine, 'faceplace_toast', None)
        return dict(tree=tree, wall=wall, enabled=game.side_panels_enabled, beside=bool(game.panels_open),
                    over=bool(game.panels_overlay), ready=game._panels_ready(), button=game._panels_button_shown(),
                    alert=toast.message.text if toast is not None else None,
                    warp_unlocked=bool(getattr(game, 'warp_unlocked', False)),
                    posts=len(engine.faceplace.messages) if wall else 0)

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
        """Typing, then Enter: a story's name entry, or a screen's own field (the file browser's path, a list's
        search)."""
        for character in rest:
            pygame.event.post(pygame.event.Event(pygame.TEXTINPUT, text=character))
        return self._then_key('return')

    def do_key(self, rest):
        """`key NAME [MS]`: a key pressed and released, or held MS milliseconds (the X360 puzzle's and leash's held
        arrows)."""
        parts = rest.split()
        if len(parts) > 1:
            return self._held_key(parts[0], float(parts[1]))
        return self._then_key(rest.strip())

    def _held_key(self, name, ms):
        code = KEYS.get(name)
        if code is None:
            return dict(ok=False, error=f'unknown key {name!r}')
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=code, mod=0, unicode=''))
        end = time.perf_counter() + ms / 1000
        while time.perf_counter() < end:
            yield
        pygame.event.post(pygame.event.Event(pygame.KEYUP, key=code, mod=0, unicode=''))
        result = yield from self._settled(0.2)
        return result

    def do_pinch(self, rest):
        """`pinch FACTOR [MS] [MOVES]`: two fingers on the open story tree, a quarter of its width apart about its middle,
        part to FACTOR times that over MS (default 800) and lift, moving MOVES times a frame (default 3: a touch screen
        reports more often than a phone draws). They go through Android's own pinch (Host.finger); on a desktop, which
        has no pinch of its own, through a stand-in of it."""
        parts = rest.split()
        factor = float(parts[0]) if parts else 2.0
        ms = float(parts[1]) if len(parts) > 1 else 800.0
        moves = max(1, int(parts[2])) if len(parts) > 2 else 3
        finger = getattr(self.app, 'finger_input', None)
        if finger is None:
            from .platforms.android import Host
            host = Host.__new__(Host)
            host.app = self.app
            finger = host.finger
        game = self.game
        if game is not None and game._claire_ready():
            # A Claire Hart round (owner, 2026-11-21): the fingers about the frame's middle, zooming the scene (1x to 2x).
            frame = game.bg_viewport
            view = game.claire_round_renderer.view
            return self._pinch(finger, frame.center, frame.width, lambda: view.zoom, factor, ms, moves, 'zoom')
        panels = getattr(game, 'side_panels', None)
        if panels is None or panels.tree_rect is None:
            return dict(ok=False, error='the story tree is not showing (key tab opens the panels), nor a Claire Hart round')
        return self._pinch(finger, panels.tree_rect.center, panels.tree_rect.width, panels._zoom_size, factor, ms, moves,
                           'tree_size')

    def _pinch(self, finger, centre, span, size, factor, ms, moves, reported):
        from types import SimpleNamespace
        width, height = self.app.window.get_size()
        cx, cy = centre
        half = span / 8

        def touch(kind, finger_id, x):
            finger(SimpleNamespace(type=kind, finger_id=finger_id, x=x / width, y=cy / height, dx=0, dy=0, touch_id=0),
                   check_sdl=False)
        touch(pygame.FINGERDOWN, 9001, cx - half)
        touch(pygame.FINGERDOWN, 9002, cx + half)
        before, began, last, done = size(), time.perf_counter(), half, False
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
        return dict(result, **{reported: [round(before, 2), round(size(), 2)]})

    def do_panels(self, rest):
        """`panels open|close`: the side panels, as Tab (or the corner button, or a tap on the Faceplace alert) opens
        them: beside the game where there's room, else over the screen; `close` as Tab, the close strip or Escape."""
        game = self._need_game()
        wanted = rest.strip().lower()
        if wanted not in ('open', 'close'):
            return dict(ok=False, error='panels open|close')
        if not any(game.panels_used()):
            return dict(ok=False, error='this episode has no Decision Tree or Faceplace wall')
        if not game.side_panels_enabled:
            return dict(ok=False, error='Side Panels is off (`set side_panels on`)')
        room = game.panels_room()
        is_open = game.panels_open if room else game.panels_overlay
        if (wanted == 'open') != bool(is_open):
            if room:
                game.toggle_panels()
            elif wanted == 'open':
                game.open_panels_overlay()
            else:
                game.close_panels_overlay()
        return self._settled(0.5)

    def _tree_ready(self):
        game = self._need_game()
        if not game.panels_used()[0]:
            raise ValueError('this episode has no Decision Tree')
        if not game._panels_ready():
            raise ValueError('the Decision Tree is not showing (`panels open`)')
        if game.notice_stack is not None and game.notice_stack.stack:
            raise ValueError('a window is open over it (`window`)')
        return game

    def _tree_listing(self, game):
        """The Decision Tree's scenes as `tree` lists them."""
        from .dtview_faceplace import NOT_WARPABLE
        session = game.session
        view = session.engine.dt_view
        nodes = []
        for node in view.nodes():
            reachable = (node.active and node.node_type not in NOT_WARPABLE and session.has_tree_state(node)
                         and node is not view.current)
            nodes.append(dict(serial=node.serial, label=node.lower_label or node.exit_label, type=node.node_type,
                              current=node is view.current, active=bool(node.active), warp=bool(reachable)))
        back = view.real_parent(view.current) if view.current is not None else None
        ahead = view.real_child(view.current) if view.current is not None else None
        return dict(nodes=nodes, rewind=back.serial if back is not None and session.has_tree_state(back) else None,
                    forward=ahead.serial if ahead is not None and session.has_tree_state(ahead) else None,
                    current=view.current.serial if view.current is not None else None,
                    unlocked=bool(game.warp_unlocked))

    def do_tree(self, rest):
        """`tree`: the Decision Tree's scenes (serial, label, the current one, those a warp reaches); `tree warp
        SERIAL|LABEL`, `tree rewind`, `tree forward`: a tap on that scene, Rewind or Fast Forward, as the tree takes it
        (locked: its "Locked" notice, which `state` shows as `window`)."""
        game = self._need_game()
        if not game.panels_used()[0]:
            return dict(ok=False, error='this episode has no Decision Tree')
        view = game.session.engine.dt_view
        words = rest.split(None, 1)
        verb = words[0].lower() if words else ''
        if not verb:
            return dict(ok=True, **self._tree_listing(game))
        self._tree_ready()
        if verb in ('rewind', 'forward'):
            target = (verb,)
        elif verb == 'warp' and len(words) > 1:
            wanted = words[1].strip()
            nodes = list(view.nodes())
            node = (next((n for n in nodes if str(n.serial) == wanted), None) if wanted.isdigit()
                    else next((n for n in nodes if (n.lower_label or '').lower() == wanted.lower()), None))
            if node is None:
                return dict(ok=False, error=f'no scene {wanted!r} on the tree (`tree` lists them)')
            target = ('node', node)
        else:
            return dict(ok=False, error='tree, tree warp SERIAL|LABEL, tree rewind, tree forward')
        return self._tree_tap(game, target)

    def _tree_tap(self, game, target):
        view = game.session.engine.dt_view
        before = view.current
        result = yield from self._act(lambda: game._tree_target(target))
        return dict(result, warped=view.current is not before, tree=self._tree_listing(game))

    def do_wall(self, rest):
        """`wall`: the Faceplace wall's posts, oldest first (sender, text, links); `wall link N`: a tap on post N's link
        (the "Exit Game?" window first where the game has it: `window no` declines)."""
        game = self._need_game()
        if not game.panels_used()[1]:
            return dict(ok=False, error='this episode has no Faceplace wall')
        posts = []
        for index, message in enumerate(game.session.engine.faceplace.messages):
            parts = [message] + list(message.continuations)
            posts.append(dict(index=index, sender=message.from_id, text='\n'.join(p.text for p in parts if p.text),
                              links=[p.url for p in parts if p.url]))
        words = rest.split()
        if not words:
            return dict(ok=True, posts=posts)
        if words[0] != 'link' or len(words) < 2 or not words[1].isdigit() or int(words[1]) >= len(posts):
            return dict(ok=False, error=f'wall link N (0 to {len(posts) - 1}, a post with a link)')
        if not game._panels_ready():
            return dict(ok=False, error='the wall is not showing (`panels open`)')
        links = posts[int(words[1])]['links']
        if not links:
            return dict(ok=False, error=f'post {words[1]} has no link')
        game._wall_link(links[0])
        return self._settled(0.6)

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

    def do_menu(self, _):
        """The pause menu's Main Menu row: the story saved and kept for Resume, the main menu showing."""
        self._need_game().command(('main_menu',))
        return self._settled(1.0)

    MAIN_BUTTONS = ('play', 'airing', 'demand', 'more', 'options', 'help')

    def do_main(self, rest):
        """`main play|airing|demand|options|help|more`: a button of the HD main menu, as a tap on it (the picker's tiles,
        Now Airing, Episodes On Demand, Options...); `back` returns."""
        button = rest.strip().lower()
        shell = self.app.shell
        if button not in self.MAIN_BUTTONS:
            return dict(ok=False, error=f'main is one of {", ".join(self.MAIN_BUTTONS)}')
        if shell is None or self.app.screen != 'main' or getattr(shell, 'stage', None) != 'main':
            return dict(ok=False, error='the main menu is not showing')
        shell.activate((button,))
        return self._settled(1.2)

    # -- the main menu's Options and Data Management, by name (owner, 2026-11-21: no screenshot-and-tap) -----------------
    PAGE_NAMES = {'general': 'options:general', 'sound': 'options:sound', 'extras': 'options:extras',
                  'addons': 'options:addons', 'add-ons': 'options:addons', 'per_game': 'options:per_game',
                  'per-game': 'options:per_game', 'controller': 'options:controller', 'data': 'options:data',
                  'library': 'data:library', 'episodes': 'data:episodes', 'progress': 'data:progress',
                  'sync': 'data:sync'}

    def _main_options(self):
        app = self.app
        if app.shell is None or app.library is None:
            raise ValueError('no game is open (`game shs` or `game cod` first)')
        if app.screen == 'game':
            raise ValueError('a story is open: leave it first (`menu`)')
        if app.screen != 'main':
            app.show('main', remember=False)
        if not app.shell.pause_open:
            app.shell.activate(('options',))
        return app.shell

    def _menu(self):
        """The menu `rows` and `press` drive: (its HdPauseMenu, its settings, how a row's command is sent). In a story,
        the story's pause menu (Desktop.pause_hd, sent through Desktop.command); else the main menu's Options."""
        game = self.game
        if game is not None:
            if not game.menu_open:
                raise ValueError('the pause menu is not open (`pause` or `options` first)')
            return game.pause_hd, game._pause_settings(), game.command
        opened = getattr(self.app, 'app_options_open', None)
        if opened is not None and opened():
            # The chooser's Options (no game open): the shared Options and Data Management for both games.
            options = self.app.app_screens.options
            return options.menu, options.settings(), options.activate
        shell = self.app.shell
        if shell is None or not getattr(shell, 'pause_open', False):
            raise ValueError('no Options page is open (`options` first)')
        return shell.pause, shell.settings(), shell.activate

    def do_options(self, rest):
        """`options [PAGE]`: Options at PAGE: general, sound, extras, addons, per_game, controller, data, library,
        episodes, progress, sync, or a screen name (options:extras, data:episodes, choice:start_in). On the main menu,
        its Options; in a story, the pause menu's (it opens first; Data Management is the main menu's only)."""
        page = rest.strip().lower()
        game = self.game
        if game is not None:
            if not game.menu_open:
                game.command(('menu',))
                yield from self._settled(0.6)
            pause = game.pause_hd
        elif self.app.library is None:
            # The game chooser's Options (no game open), as its Options button opens them.
            app = self.app
            if not app.app_options_open():
                app.history = ['games']
                app.show('options', remember=False)
                yield from self._settled(0.3)       # (its first frame sets it up: AppOptions.enter)
            pause = app.app_screens.options.menu
        else:
            pause = self._main_options().pause
        pause.open(self.PAGE_NAMES.get(page, page) if page and page != 'options' else 'options')
        result = yield from self._settled(0.5)
        return dict(result, page=pause.state.screen)

    def _menu_rows(self):
        """The open menu page's rows as a player reads them: [dict(label, kind, key, value, command)]: the commands
        its rows send when tapped (desktop_pause_hd.screen_layout)."""
        from .desktop_pause_hd import DATA_TITLES, JOURNAL_LABEL, OPTION_CATEGORIES, SKIP_AHEAD_LABEL, UNDO_LABEL
        pause, settings, _ = self._menu()
        strings, screen = pause.strings(), pause.state.screen
        rows = []
        if screen == 'pause':
            # A story's pause menu itself: Resume, (Skip Ahead, Undo, Quest Journal,) Options, Help, Main Menu.
            entries = [(strings[20], ('resume',)), (strings[10], ('pause_open', 'options')),
                       (strings[120], ('pause_open', 'help')), (strings[9], ('main_menu',))]
            for flag, label, command in (('journal_row', JOURNAL_LABEL, ('journal',)), ('undo_row', UNDO_LABEL, ('undo',)),
                                         ('skip_ahead_row', SKIP_AHEAD_LABEL, ('skip_ahead',))):
                if settings.get(flag):
                    entries.insert(1, (label, command))
            return [dict(label=str(label), kind='action', key=command[-1], command=command) for label, command in entries]
        if screen == 'help':
            # Help & About's list (the main menu's has Push Notifications and the legal page too).
            from .desktop_pause_hd import HELP_ORDER, MAIN_HELP_ORDER
            for page in (MAIN_HELP_ORDER if pause.main_menu else HELP_ORDER):
                label = strings[170 if page == 'privacy' else pause.PAGES[page][0]]
                rows.append(dict(label=str(label), kind='page', key=page, command=('pause_open', page)))
            return rows
        text = self._page_text(pause, screen)
        if text is not None:
            # A text page (a Help page, Library Info, a Quest Journal entry): its links are its rows.
            return [dict(label=label, kind='link', key=url, command=('pause_link', url)) for label, url in text[2]]
        if screen == 'options':
            for category, label in OPTION_CATEGORIES:
                if pause.option_rows(category, settings, strings):
                    rows.append(dict(label=label, kind='page', key='options:' + category,
                                     command=('pause_open', 'options:' + category)))
            return rows
        category = (screen if screen in DATA_TITLES or screen in pause.row_pages or screen.startswith('choice:')
                    else screen.split(':', 1)[1])
        for kind, label, key in pause.option_rows(category, settings, strings):
            row = dict(label=str(label), kind=kind, key=key if isinstance(key, str) else list(key))
            if kind == 'slider':
                row.update(value=settings.get(key + '_volume'), command=None)       # (`set music_volume N`)
            elif kind == 'pick':
                option, value = key
                row.update(value=label == settings.get(option), command=('pause_cycle', option, value))
            elif kind == 'folder':
                row.update(value=settings.get(key), command=('pause_cycle', key))
            elif kind == 'choice':
                row.update(value=settings.get(key), command=('pause_open', 'choice:' + key))
            elif kind == 'switch':
                row.update(value=bool(settings.get(key, False)), command=('pause_toggle', key))
            elif kind == 'cycle':
                row.update(value=settings.get(key), command=('pause_cycle', key))
            else:
                row.update(command=('pause_open' if kind == 'page' else 'pause_action', key))
            rows.append(row)
        return rows

    @staticmethod
    def _page_text(pause, screen):
        """A text page's (title, body, [(link words, url)]), or None for a page of rows."""
        from .desktop_pause_hd import DATA_TITLES, link_words
        if (screen in ('pause', 'options', 'help') or screen.startswith(('options:', 'choice:')) or screen in DATA_TITLES
                or screen in pause.row_pages):
            return None
        try:
            title, body = pause.text_lines(screen)
        except (KeyError, IndexError):
            return None
        links = []
        for paragraph in body.split('\n'):
            current = None
            for word in link_words(paragraph):
                for piece, url in word:
                    if url is None:
                        current = None
                    elif current is not None and current[1] == url:
                        current[0].append(piece)
                    else:
                        current = ([piece], url)
                        links.append(current)
        return str(title), str(body), [(' '.join(words), url) for words, url in links]

    def do_rows(self, _):
        """The open Options page's rows: label, kind (switch, choice, pick, page, action, folder, cycle, slider, link),
        key, value (a switch's on/off, a choice's current value, a pick's tick); a text page (a Help page, Library Info,
        a Quest Journal entry) also gives its title and text, its links as rows."""
        rows = self._menu_rows()
        pause = self._menu()[0]
        out = dict(ok=True, page=pause.state.screen,
                   rows=[{k: v for k, v in row.items() if k != 'command'} for row in rows])
        if getattr(pause, 'scroll_area', None) is not None:
            # A page that scrolls (a text page; rows too many for the frame): where it is, in points.
            out['scroll'] = dict(at=round(pause.state.scroll, 1), most=round(pause.state.max_scroll, 1))
        text = self._page_text(pause, pause.state.screen)
        if text is not None:
            out.update(title=text[0], text=text[1])
        return out

    def do_press(self, rest):
        """`press LABEL`: a row of the open Options page, as a tap on it (its label, without case, or its key): a page
        opens, a switch flips, a choice's page opens, a pick is chosen, an action runs (its question shows as `window`)."""
        wanted = rest.strip().lower()
        rows = self._menu_rows()
        row = next((r for r in rows if r['label'].lower() == wanted), None)
        row = row or next((r for r in rows if str(r['key']).lower() == wanted), None)
        if row is None or row['command'] is None:
            return dict(ok=False, error=f'no row {rest!r}: {[r["label"] for r in rows]}')
        self._menu()[2](row['command'])
        result = yield from self._settled(0.6)
        return dict(result, pressed=row['label'])

    def do_do(self, rest):
        """`do ACTION`: a Data Management action by its key, as its row does (verify_library, rebuild_previews,
        back_up, mark_read, delete_episodes, add_episodes...): `rows` on a data page lists the keys."""
        key = rest.strip()
        shell = self._main_options()
        from .desktop_pause_hd import DATA_ACTIONS, DATA_PAGES
        if key not in {k for k, _ in DATA_ACTIONS}:
            return dict(ok=False, error=f'do is one of {", ".join(k for k, _ in DATA_ACTIONS)}')
        page = next((screen for screen, _, rows in DATA_PAGES if any(k == key for k, _ in rows)), 'options:data')
        shell.pause.open(page)
        yield from self._settled(0.4)
        shell.activate(('pause_action', key))
        result = yield from self._settled(0.8)
        return result

    def _choosing(self):
        """The open episode tick list: (its picker, its EpisodeChoice, its library, its verb button's act): a game's
        Data Management list, or the chooser's (its Episodes page, a library opened for it)."""
        app = self.app
        chooser = getattr(app.app_screens, 'choice', None) if getattr(app, 'app_screens', None) is not None else None
        if app.screen == 'choice' and chooser is not None:
            return chooser.picker, chooser.picker.choosing, chooser.library, app.app_screens.choice_act
        picker = app.picker
        choosing = getattr(picker, 'choosing', None)
        if choosing is None or app.screen != 'picker':
            raise ValueError('no episode tick list is open (`press Mark as Finished`, `press Delete Episodes`...)')
        from .desktop_episode_list_hd import CHOICE_ACT
        return picker, choosing, app.library, lambda: app.picker_command(CHOICE_ACT)

    def do_ticks(self, _):
        """The open tick list: its title and verb, each episode offered (id, title, ticked)."""
        picker, choosing, library, _ = self._choosing()
        episodes = [dict(id=r['id'][:12], title=(r.get('titles') or [''])[0], ticked=r['id'] in choosing.chosen)
                    for r in library.episodes if r['id'] in choosing.allowed]
        return dict(ok=True, title=getattr(choosing, 'title', None), verb=getattr(choosing, 'verb', None),
                    chosen=len(choosing.chosen), episodes=episodes)

    def do_pick(self, rest):
        """`pick TITLE|ID`: tick or untick an episode in Data Management's tick list (Mark as Finished, Delete, Export,
        Reset Decision Tree): its title contains TITLE, or its id starts with ID."""
        picker, choosing, library, _ = self._choosing()
        wanted = rest.strip().lower()
        records = [r for r in library.episodes if r['id'] in choosing.allowed]
        found = [r for r in records if r['id'].startswith(wanted) and len(wanted) >= 6] or \
                [r for r in records if any(wanted in (t or '').lower() for t in r.get('titles', ()))]
        if not found:
            return dict(ok=False, error=f'no episode {rest!r} in this list')
        choosing.toggle(found[-1]['id'])
        return dict(ok=True, episode=(found[-1].get('titles') or [''])[0], ticked=found[-1]['id'] in choosing.chosen,
                    chosen=len(choosing.chosen))

    def do_act(self, _):
        """The tick list's verb button (Save, Delete, Export, Reset): its question shows as `window`."""
        picker, choosing, _, act = self._choosing()
        if not choosing.can_act():
            return dict(ok=False, error='nothing is ticked')
        act()
        return self._settled(0.8)

    def do_set(self, rest):
        key, _, value = rest.partition(' ')
        wanted = value.strip() in ('on', 'true', '1')
        state = self.app.state
        from .menu import SHARED_PREFERENCES
        choices = {k: v for k, v in SHARED_PREFERENCES.items() if isinstance(v, tuple)}
        if state is not None and key in choices:
            # An option that is one of a few values (DSi Pixels, DSi Language, Title Screen Look...): as its choice page sets it
            if value.strip() not in choices[key]:
                return dict(ok=False, error=f'{key} is one of {", ".join(choices[key])}')
            setattr(state, key, value.strip())
            state.persist()
            if key.startswith('dsi_') or key == 'preferred_language':
                self.app.apply_dsi()
            elif self.app.game is not None and hasattr(self.app.game, key):
                setattr(self.app.game, key, value.strip())     # (the open story's too, as its pause menu's page sets it)
            if key == 'ch_dialogue':
                self.app.apply_ch_dialogue()
            if key == 'claire_powerups':
                self.app.apply_claire_powerups()
            return dict(ok=True, key=key, value=getattr(state, key))
        if key == 'start_in':
            # General's Start In (settings.json, the app's own): auto, games, shs or cod.
            from .settings import START_IN
            if value.strip() not in START_IN:
                return dict(ok=False, error=f'start_in is one of {", ".join(START_IN)}')
            self.app.settings.set_start_in(value.strip())
            return dict(ok=True, key=key, value=self.app.settings.start_in)
        if state is not None and key in ('music_volume', 'sound_volume'):
            # Sound's sliders: 0-100, as the slider sets them.
            if not value.strip().isdigit() or not 0 <= int(value) <= 100:
                return dict(ok=False, error=f'{key} is 0 to 100')
            if self.app.shell is not None:
                self.app.shell.set_volume(key.split('_')[0], int(value) / 100)     # as the slider does
            else:
                setattr(state, key, int(value))
                state.persist()
            return dict(ok=True, key=key, value=getattr(state, key))
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

    def do_resize(self, rest):
        """A computer's window at W x H, as a user's drag leaves it: the app and the open story draw into it from the next
        frame (they read its size each frame). For shapes past the Aspect Ratio choices (2026-11-18: 9:20)."""
        try:
            width, height = (int(value) for value in rest.split())
        except ValueError:
            return dict(ok=False, error='resize W H')
        if getattr(self.app, 'fixed_window', False) or not (100 <= width <= 8192 and 100 <= height <= 8192):
            return dict(ok=False, error="a phone's window is its screen" if getattr(self.app, 'fixed_window', False)
                        else 'W and H are 100 to 8192')
        self.app.window = pygame.display.set_mode((width, height), pygame.RESIZABLE)
        if self.app.game is not None:
            self.app.game.window = self.app.window
        return dict(ok=True, window=list(self.app.window.get_size()))

    def _screen_buttons(self):
        """The buttons of a screen outside a story and the HD menus (the chooser, Setup, Bulk Import, the file browser,
        the menus of a game without HD art): [(words, command)], as the screen drew them."""
        app = self.app
        if app.screen == 'game' or (app.screen == 'main' and app.shell is not None) or app.screen == 'picker':
            return []

        titles = {}
        if app.library is not None:
            titles = {r['id']: (r.get('titles') or [''])[0] for r in app.library.episodes}

        def words(command):
            if len(command) == 2 and command[1] in titles:        # an episode's row: its title, then its id's start
                return f'{command[0]} {titles[command[1]]} [{command[1][:8]}]'
            return ' '.join(part.name if isinstance(part, Path) else str(part) for part in command)
        return [(words(command), command) for _, command in getattr(app, 'buttons', ()) or ()]

    def do_buttons(self, _):
        """The buttons on a screen outside a story and the HD menus, by their command's words (`button` presses one); in
        the file browser, its folder and kind too."""
        app = self.app
        out = dict(ok=True, screen=app.screen, buttons=[label for label, _ in self._screen_buttons()])
        if app.screen == 'browser':
            out.update(folder=str(getattr(app, 'folder', '')), kind=getattr(app, 'browser_kind', None),
                       files=[p.name + ('/' if p.is_dir() else '') for p in getattr(app, 'files', ())])
        return out

    def do_button(self, rest):
        """`button WORDS`: a button of that screen, as a tap on it (`buttons` lists them: `file NAME` opens a folder or
        imports a file in the browser, `up`, `folder` (Use This Folder, Open Library), `browse library`...)."""
        wanted = rest.strip().lower()
        buttons = self._screen_buttons()
        if self.app.screen == 'browser' and wanted.startswith('file '):
            # Any file of the folder, not only those scrolled into view (a player scrolls to it).
            name = wanted[5:].strip().rstrip('/')
            buttons = buttons + [('file ' + p.name, ('file', p)) for p in getattr(self.app, 'files', ())
                                 if p.name.lower() == name]
        found = (next((command for label, command in buttons if label.lower() == wanted), None)
                 or next((command for label, command in buttons if label.lower().startswith(wanted)), None))
        if not wanted or found is None:
            return dict(ok=False, error=f'no button {rest!r}: {[label for label, _ in buttons][:60]}')
        if self._window() is not None:
            return dict(ok=False, error='a window is open (`window`)')
        self.app.command(found)
        return self._idle(600) if found[0] in ('file', 'folder') else self._settled(0.6)

    PICKER_VERBS = ('tile', 'new', 'continue', 'delete', 'close', 'info', 'restore', 'back')

    def do_picker(self, rest):
        """`picker`: the episode picker on screen (the tiles, Now Airing or On Demand): its rows, each episode's id,
        title, whether a saved game holds it and whether it's finished, and the open popup. `picker tile TITLE|ID` taps
        an episode (a new one starts; one with a save opens its New Game / Continue popup), `picker new|continue|
        delete|close` presses the popup's New Game, Continue, Delete Save or back, `picker info TITLE|ID` its info
        button, `picker restore` the Restore button, `picker back` Back."""
        app = self.app
        picker = getattr(app, 'picker', None)
        if app.screen != 'picker' or picker is None:
            return dict(ok=False, error='the episode picker is not showing (`main play`, `main airing`, `main demand`)')
        model = picker.model
        words = rest.split(None, 1)
        verb = words[0].lower() if words else ''
        if not verb:
            rows = [dict(title=row.title, episodes=[
                dict(id=r['id'][:12], title=model.label(r), saved=r['id'] in app.saved,
                     finished=r['id'] in getattr(app, 'finished', ()), info=bool(model.has_info(r))) for r in row.episodes])
                    for row in model.rows]
            return dict(ok=True, style=app.picker_style, rows=rows, selected=picker.selected,
                        popup=picker.popup['id'][:12] if picker.popup else None)
        if verb not in self.PICKER_VERBS:
            return dict(ok=False, error=f'picker is one of {", ".join(self.PICKER_VERBS)}')
        if self._window() is not None:
            return dict(ok=False, error='a window is open (`window`)')
        if verb in ('new', 'continue', 'delete', 'close'):
            if not picker.popup:
                return dict(ok=False, error='no New Game / Continue popup is open (`picker tile` on a saved episode)')
            record_id = picker.popup['id']
            command = {'close': ('close',), 'delete': ('delete_save', record_id)}.get(verb, (verb, record_id))
        elif verb in ('restore', 'back'):
            command = (verb,)
        else:
            if picker.popup:
                return dict(ok=False, error='the popup is open (`picker close`)')
            wanted = (words[1] if len(words) > 1 else '').strip().lower()
            shown = [r for row in model.rows for r in row.episodes]
            found = ([r for r in shown if len(wanted) >= 6 and r['id'].startswith(wanted)]
                     or [r for r in shown if wanted and wanted in model.label(r).lower()])
            if not found:
                return dict(ok=False, error=f'no episode {wanted!r} in the picker')
            if verb == 'info' and not model.has_info(found[0]):
                return dict(ok=False, error=f'{model.label(found[0])} has no info card')
            command = (verb, found[0]['id'])
        app.picker_command(command)
        result = yield from self._settled(0.8)
        return dict(result, pressed=list(command[:1]))

    def do_game(self, rest):
        key = rest.strip().lower()
        if self.app.game is not None and self.app.screen == 'game':
            return dict(ok=False, error='a story is open: leave it first')
        # (A story held for Resume behind the main menu is let go with its library, saved first, as the main menu's
        # switch button does: test channel wish, 2026-11-20.)
        if key in ('chooser', 'games'):
            # The game chooser, as Switch Game shows it where the other game has no library (and Start In's Choose a
            # Game at launch): this game's library let go.
            self.app.show_game_chooser()
            return self._settled(0.5)
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
        before = self.app.game
        self.app.state.selected = self.app.selected = record_id
        self.app.enter_episode(resume=resume)

        def shown():
            # The requested story's first screen: not the one open before (whose screen would answer at once,
            # 2026-11-18: `open` from Dating Beth replied with Dating Beth), unless it is that story resumed.
            game = self.game
            return (game is not None and game.session.pending is not None
                    and game.session.resources.record['id'] == record_id and (game is not before or resume))
        result = yield from self._until(shown, 60)
        return result

    def _window(self):
        """The window on top, as a player meets it: a story's own notice ("Exit Game?", the Decision Tree's "Locked",
        Connection Error), the app's Update Available or its message card ("Added 3 episodes."), the episode picker's
        alert (an info card, Restore's answer), the chooser's Options' question, or the menus' confirmation or notice.
        A SimpleNamespace(source, title, text, buttons, ids, press(index)), or None (owner, 2026-11-21: `state` saw only
        the menus' windows)."""
        from types import SimpleNamespace
        app, game = self.app, self.game

        def window(source, title, text, buttons, press, ids=None):
            buttons = [str(b) for b in buttons]
            return SimpleNamespace(source=source, title=str(title or ''), text=str(text or '')[:400], buttons=buttons,
                                   ids=ids or list(buttons), press=press)
        if game is not None:
            stack = game.notice_stack
            if stack is not None and stack.stack:
                items = self._shown_items(game.notice_windows, game.notice_data, stack.current)
                return self._menu_window('story', game.notice_data.menu(stack.current), items, game.notice_windows,
                                         None, lambda i: stack.press(items[i]), window)
            return None
        if getattr(app, 'busy', False):
            return None
        if getattr(app, 'message', None):
            return window('message', app.game_title, app.message, ['OK'], lambda i: app.command(('dismiss',)))
        if getattr(app, 'update_prompt', None) is not None:
            from .updates import UPDATE_TITLE, update_message
            commands = (('update_no',), ('update_yes',)) if app.can_quit else (('update_no',),)
            return window('update', UPDATE_TITLE, update_message(app.update_prompt.version, can_quit=app.can_quit),
                          ['No', 'Yes'] if app.can_quit else ['OK'], lambda i: app.command(commands[i]))
        picker = getattr(app, 'picker', None)
        if getattr(app, 'screen', None) == 'picker' and picker is not None and picker.alert:
            alert = picker.alert
            title, text = ((alert.title, ' '.join(t for t in (alert.airdate, alert.price, alert.description) if t))
                           if hasattr(alert, 'description') else alert)
            return window('picker', title, text, ['OK'], lambda i: app.picker_command(('dismiss',)))
        opened = getattr(app, 'app_options_open', None)
        if opened is not None and opened() and app.app_screens.options.ask is not None:
            options = app.app_screens.options
            title, text, labels, actions = options.ask

            def press(i):
                options.ask = None
                if actions[i] is not None:
                    actions[i]()
            return window('options', title, text, labels, press)
        shell = app.shell
        stack = getattr(shell, 'stack', None)
        if stack is None or not stack.stack or getattr(shell, 'data', None) is None:
            return None
        try:
            variables = shell.variables()
        except Exception:                               # (a shell without a game's variables: the ids' own words)
            variables = None
        items = self._shown_items(getattr(shell, 'windows', None), shell.data, stack.current)
        return self._menu_window('menu', shell.data.menu(stack.current), items, getattr(shell, 'windows', None),
                                 variables, lambda i: stack.press(items[i]), window)

    @staticmethod
    def _shown_items(windows, data, menu_id):
        """A window's buttons as drawn: its renderer leaves out the ones a game's conditions rule out."""
        items = getattr(windows, 'items', None)
        return list(items(menu_id)) if callable(items) else list(data.items(menu_id))

    @staticmethod
    def _menu_window(source, menu, items, windows, variables, press, window):
        """A menu engine's window as a player reads it: a game's own window carries string ids (its title '5', buttons
        '25' / '24'), shown as the words they draw (test channel wish, 2026-11-20)."""
        def words(string_id):
            try:
                return windows.text_for(string_id, variables) if windows is not None else str(string_id)
            except (KeyError, IndexError, TypeError, AttributeError):
                return str(string_id)

        def notice():
            try:
                return windows.kind_of(menu) == 'notice'
            except (AttributeError, TypeError):
                return False

        def label(action):
            try:
                if windows is not None and notice():
                    # A notice draws its one button as OK, whatever its item says (the "Locked" notice's item is
                    # string 0, the credits: v1.1.1 check, 2026-11-22).
                    return str(windows.strings()[154])
                return windows.item_label(action, variables) if windows is not None else str(action.label)
            except (KeyError, IndexError, TypeError, AttributeError):
                return str(action.label)
        return window(source, words(menu.title), words(menu.message), [label(b) for b in items], press,
                      ids=[str(b.label) for b in items])

    @staticmethod
    def _window_words(window):
        return dict(source=window.source, title=window.title, text=window.text, buttons=window.buttons, ids=window.ids)

    def do_window(self, rest):
        """Press a button of the open window: its words (`no`, `ok`, `play with sound`), its id, its position (0
        first), or `yes` (its verb, the last)."""
        window = self._window()
        if window is None:
            return dict(ok=False, error='no window is open')
        wanted = rest.strip().lower()
        # Its words first ("no", "play with sound": a game's own window draws them from string ids), then a label as an
        # id ('25', '24'), which a position never reached (iPad, 2026-11-19: `window 24` found no button '24').
        index = next((i for i, word in enumerate(window.buttons) if word.lower() == wanted), None)
        if index is None:
            index = next((i for i, key in enumerate(window.ids) if key.lower() == wanted), None)
        if index is None and wanted.isdigit() and int(wanted) < len(window.buttons):
            index = int(wanted)
        if index is None and wanted in ('yes', 'ok') and window.buttons:
            index = len(window.buttons) - 1
        if index is None:
            return dict(ok=False, error=f'no button {rest!r}: {window.buttons}')
        window.press(index)
        if window.source == 'story':
            return self._settled(0.6)
        return self._idle(60)

    # -- Sync Devices (owner, 2026-11-19: the device passes drove it by taps, shots and coordinates) ---------------
    def _sync_pages(self, page):
        """Show Data Management's Sync Devices `page` where a player reaches it: the open game's Options over its main
        menu, or the chooser's Options."""
        app = self.app
        if app.library is None:
            app.history = ['games']
            app.app_screens.options.next_screen = page
            app.show('options', remember=False)
        else:
            if app.game is not None and app.screen == 'game':
                raise ValueError('a story is open: leave it first')
            app.show('main', remember=False)
            if not app.shell.pause_open:
                app.shell.activate(('options',))
            app.shell.pause.open(page)
        # (A frame first: the chooser's Options take their opening page as they are first drawn, and a page opened
        # before that was replaced, closing Receive's waiting at once.)
        yield from self._settled(0.3)
        return app.sync_flow()

    def do_sync(self, rest):
        from .sync_flow import ChooserPages, SYNC_PAGE
        words = rest.split()
        verb, args = (words[0] if words else 'status'), words[1:]
        app = self.app
        if verb == 'receive':
            flow = yield from self._sync_pages(SYNC_PAGE)
            flow.result = None
            flow.receive()
            result = yield from self._settled(1.0)
            return dict(result, sync=self._sync_status())
        if verb == 'send':
            flow = yield from self._sync_pages(SYNC_PAGE)
            flow.result = None
            for key in flow.choices:
                flow.choices[key] = True
            flow.choices['backup'] = 'nobackup' not in args
            named = next((word for word in args if word in ('shs', 'cod', 'both')), None)
            if app.library is None and named is not None:
                flow.game = None if named == 'both' else named
            flow.show_send_page()
            flow.find()
            result = yield from self._settled(1.0)
            return dict(result, sync=self._sync_status())
        flow = getattr(app, 'sync', None)
        if flow is None:
            return dict(ok=False, error='Sync has not been used')
        if verb == 'devices':
            seconds = float(args[0]) if args else 0.
            yield from self._until(lambda: bool(flow.devices), seconds, quiet=True)
            return dict(ok=True, devices=[device.name for device in flow.devices])
        if verb == 'choose':
            wanted = ' '.join(args)
            names = [device.name for device in flow.devices]
            index = (int(wanted) if wanted.isdigit() and int(wanted) < len(names)
                     else names.index(wanted) if wanted in names else None)
            if index is None:
                return dict(ok=False, error=f'no receiver {wanted!r}: {names}')
            flow.choose(f'sync_device:{index}')
            yield from self._until(lambda: flow.ui is not None and flow.ui.asking(), 15)
            return dict(ok=True, sync=self._sync_status())
        if verb == 'answer':
            ui = flow.ui
            yes = (args[:1] or ['yes'])[0].lower() in ('yes', 'y', 'send', 'receive')
            if ui is None or not ui.asking():
                return dict(ok=False, error='no Sync question is open', sync=self._sync_status())
            if isinstance(ui, ChooserPages):
                window, ui.options.ask = ui.window, None
                if yes:
                    window[3][-1]()
            else:
                window = self._window()
                window.press(len(window.buttons) - 1 if yes else 0)
            yield from self._settled(0.5)
            return dict(ok=True, sync=self._sync_status())
        if verb == 'wait':
            seconds = float(args[0]) if args else 120.

            def waiting():
                session = flow.current()
                return flow.result is not None or (session is not None and session.status in ('confirm', 'confirm_full')
                                                   and flow.ui is not None and flow.ui.asking())
            result = yield from self._until(waiting, seconds)
            return dict(ok=True, reached=result.get('reached'), sync=self._sync_status())
        if verb == 'ok':
            ui = flow.ui
            if isinstance(ui, ChooserPages):
                if ui.options.ask is None:
                    return dict(ok=False, error='no notice is open')
                ui.options.ask = None
            else:
                window = self._window()
                if window is None:
                    return dict(ok=False, error='no notice is open')
                window.press(len(window.buttons) - 1)
            yield from self._settled(0.5)
            return dict(ok=True, sync=self._sync_status())
        if verb == 'stop':
            flow.stop()
            return dict(ok=True, sync=self._sync_status())
        if verb == 'status':
            return dict(ok=True, sync=self._sync_status())
        return dict(ok=False, error='sync is one of receive, send, devices, choose, answer, wait, status, ok, stop')

    def _sync_status(self):
        flow = getattr(self.app, 'sync', None)
        if flow is None:
            return dict(active=False)
        session, ui = flow.current(), flow.ui
        out = dict(active=flow.active, page=ui.screen() if ui is not None else None,
                   devices=[device.name for device in flow.devices], asking=bool(ui is not None and ui.asking()),
                   result=list(flow.result) if flow.result else None)
        if session is not None:
            out.update(status=session.status, peer=session.peer, code=getattr(session, 'code', None),
                       progress=getattr(session, 'progress', None))
        return out

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
                # The story ended (its end card shows over the main menu) or was left: nothing more to run (test channel
                # wish, 2026-11-20: run-until choice in Easter Egg Hunt waited out its time after the end).
                return self.app.screen != 'game'
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
        if self.game is None:
            return dict(result, reached=False, ended=True)
        action = self.game.session.pending if self.game is not None else None
        result['reached'] = bool(result.get('reached')) and (kind in ('stop', 'any') or (action is not None and action.name == kind)
                                                               or (kind == 'prompt' and self.game.host_prompt is not None
                                                                   and not self.game.host_prompt.get('loading')))
        return result

    def do_timing(self, rest):
        channel = self.channel
        words = rest.split()
        if words[:1] == ['on']:
            channel.frames, channel.slow, channel.tags, channel.sounds = [], [], [], None
            return dict(ok=True)
        frames, tags = channel.frames or [], channel.tags
        if words[:1] == ['off']:
            channel.frames = None
        if not frames:
            return dict(ok=True, frames=0)
        ordered = sorted(frames)
        out = dict(ok=True, frames=len(frames), fps=round(1000 * len(frames) / sum(frames), 1),
                   median_ms=round(statistics.median(frames), 1), p90_ms=round(ordered[int(.9 * (len(ordered) - 1))], 1),
                   worst_ms=round(ordered[-1], 1),
                   slow=[dict(ms=round(ms, 1), command=command, after=label)
                         for ms, command, label in sorted(channel.slow, reverse=True)[:8]])
        if 'groups' in words[1:]:
            out['groups'] = _group_frames(tags)
        return out

    def do_memory(self, _):
        return dict(ok=True, **_memory())

    # -- the library --------------------------------------------------------------------------------------------------

    def _library(self):
        if self.app.library is None:
            raise ValueError('no library is open (`game shs` opens one)')
        return self.app.library

    def do_episodes(self, rest):
        library, wanted = self._library(), rest.strip().lower()
        saved = getattr(self.app, 'saved', None) or set()
        rows = []
        for record in library.episodes:
            titles = record.get('titles') or ['']
            if wanted and not record['id'].startswith(wanted) and not any(wanted in (t or '').lower() for t in titles):
                continue
            rows.append(dict(id=record['id'][:12], title=titles[0], pack=record.get('pack_id'),
                             episode=record.get('episode_id'), revision=record.get('revision'),
                             category=record.get('category'), builtin=bool(record.get('builtin')) or 'file' not in record,
                             saved=record['id'] in saved))
        return dict(ok=True, count=len(rows), episodes=rows)

    def do_addons(self, _):
        library = self._library()
        return dict(ok=True, addons=[dict(name=addon.get('addon'), title=addon.get('title'), revision=addon.get('revision'),
                                          id=addon['id'][:12]) for addon in getattr(library, 'addons', ())])

    @staticmethod
    def _one(records, rest, what):
        """The one record an id prefix (6+) or a title names (exactly, else containing it); a ValueError naming the
        matches otherwise."""
        wanted = rest.strip().lower()
        if not wanted:
            raise ValueError(f'which {what}?')

        def names(record):
            return [(name or '').lower() for name in (record.get('titles') or [record.get('title')]) + [record.get('addon')]]
        found = [r for r in records if len(wanted) >= 6 and r['id'].startswith(wanted)]
        found = found or [r for r in records if wanted in names(r)]
        found = found or [r for r in records if any(wanted in name for name in names(r))]
        if len(found) != 1:
            listed = [f"{r['id'][:12]} {(r.get('titles') or [r.get('title')])[0]}" for r in found[:10]]
            raise ValueError(f'{len(found)} {what}s match {rest!r}' + (f': {listed} (use an id)' if found else ''))
        return found[0]

    def _data_job(self, title, work, done):
        """A job: Data Management's background work (app.start_data_job), until its result is back on the app's thread
        and `done(result)` has made the reply."""
        end = time.perf_counter() + 600
        while self.app.busy and time.perf_counter() < end:
            yield
        box = []
        self.app.start_data_job(title, work, lambda result: box.append(done(result)))
        end = time.perf_counter() + 600
        while not box and time.perf_counter() < end:
            yield
        return box[0] if box else dict(ok=False, error=f'{title}: not done in 600 s')

    def do_delete(self, rest):
        """Delete Episodes for one episode (its saves, screenshots, previews, Decision Tree), as Data Management's list
        does. Not one being played: a story on screen is refused; one kept for Resume behind the menu is let go first."""
        library = self._library()
        record = self._one(library.episodes, rest, 'episode')
        if record.get('builtin') or 'file' not in record:
            return dict(ok=False, error='a built-in episode is extracted again: not deleted')
        held = self.app.game
        if held is not None and held.session.resources.record['id'] == record['id']:
            if self.app.screen == 'game':
                return dict(ok=False, error='that episode is open: leave it first (`menu`)')
            self.app.game = None                            # (held for Resume: its saves go with it)

        def done(result):
            self.app.refresh_saves()
            self.app.picker = None
            return dict(ok=True, deleted=record['id'][:12], title=(record.get('titles') or [''])[0], notice=list(result))
        result = yield from self._data_job('Deleting episodes',
                                           lambda lib: self.app.delete_episodes(lib, [record['id']]), done)
        return result

    def do_delete_addon(self, rest):
        """Delete for one add-on, as Data Management's Add-Ons page does (the episodes that need it say so until it's
        imported again)."""
        library = self._library()
        addon = self._one(getattr(library, 'addons', []), rest, 'add-on')

        def done(count):
            self.app.addon_deleted()
            return dict(ok=bool(count), deleted=addon['id'][:12], name=addon.get('addon'), title=addon.get('title'))
        result = yield from self._data_job('Deleting add-on', lambda lib: lib.remove_addons([addon['id']]), done)
        return result

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
        if only.startswith('callers '):
            # `profile off callers NAME`: who calls the functions named NAME (e.g. fill, blit), costliest first
            name = only.split()[1]
            out = []
            for func, row in stats.stats.items():
                if func[2] == name or func[2].endswith(f"'{name}' of 'pygame.surface.Surface' objects>") \
                        or func[2].endswith(f' {name}>'):
                    for caller, (_, calls, own, _total) in sorted(row[4].items(), key=lambda c: -c[1][2])[:20]:
                        out.append(dict(callee=func[2][:60], call=f'{Path(caller[0]).name}:{caller[1]} {caller[2]}',
                                        calls=calls, own_ms=round(own * 1000, 1)))
            return dict(ok=True, callers=out)

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

    # -- the mini-games (owner, 2026-11-21) ---------------------------------------------------------------------------
    # `state`'s `minigame` says what's open and what it waits for (minigame_report.describe); `play` gives it a player's
    # input. The translated mini-games take the calls the desktop's own handlers make for a tap or key; Claire Hart's rounds
    # take real taps, at the place the round draws what's tapped, so its hit-testing, panning and buttons are exercised.

    def do_play(self, rest):
        """`play press [N]` (the go-ahead or the game's button; a cell 0-8 for SHS '11's games; a key code on New Rules'
        arena, a row on its menu; football's tap, or a play 0-8; the word game's option N); `play cells A B C` (the word
        grid: a drag through those cells; `play press` a tap off its board); Claire Hart's rounds: `play find NAME|SLOT`, `play miss`, `play hint`,
        `play powerup focus|locator|clairvoyance|time_warp`, `play pick SLOT` (the Psychic Locator), `play continue`."""
        game = self._need_game()
        words = rest.split(None, 1)
        if not words:
            return dict(ok=False, error='play what? (press, find, miss, hint, powerup, pick, continue)')
        verb, arg = words[0], words[1].strip() if len(words) > 1 else ''
        session = game.session
        action = session.pending
        name = action.name if action is not None else None
        if game.host_prompt is not None:
            return dict(ok=False, error='a skip prompt is up: answer it first (`answer N`, Play to play)')
        if name == 'claire_round':
            return self._claire_play(verb, arg)
        if name == 'word_grid' and verb in ('press', 'cells'):
            # (v1.1.1 check, 2026-11-22) The word grid: a drag through cells (`play cells 0 1 2`, down on the first,
            # through the rest, up on the last), or `play press`, a tap off the board (its rules pages, its results).
            cells = [int(c) for c in arg.split()] if verb == 'cells' else []
            if verb == 'cells' and not cells:
                return dict(ok=False, error='play cells A B C... (the board\'s cells, 0 first, row by row)')
            def drag():
                if not cells:
                    session.grid_pointer('down', None)
                    session.grid_pointer('up', None)
                    return
                session.grid_pointer('down', cells[0])
                for cell in cells[1:]:
                    session.grid_pointer('move', cell)
                session.grid_pointer('up', cells[-1])
            return self._act(lambda: game._attempt(drag))
        if verb != 'press':
            return dict(ok=False, error=f'{verb} is for Claire Hart rounds; this is {name}')
        from .minigame_report import CELL_GAMES, PRESS_GAMES
        value = int(arg) if arg.lstrip('-').isdigit() else None
        if name == 'arena_frame':
            if value is None:
                return dict(ok=False, error='the arena takes a key code (-5 OK, -1 to -4 the joystick, 48-57 the number keys)')
            return self._act(lambda: game.command(('arena_key', value)))
        if name in ('arena_menu', 'arena_info'):
            return self._act(lambda: game.command(('arena_answer', value if value is not None else 0)))
        if name in CELL_GAMES:
            if value is not None and not 0 <= value < 9:
                return dict(ok=False, error='a cell is 0-8 (none for an OK)')
            return self._act(lambda: game._attempt(lambda: session.answer(value)))
        if name in PRESS_GAMES:
            return self._act(lambda: game._attempt(lambda: session.answer(None)))
        if name == 'football':
            # (v1.1.1 check, 2026-11-22) A tap goes on from a rules page; a play is one of the nine targets (0-8), as a
            # tap on it or keys 1-9.
            if value is not None and not 0 <= value < 9:
                return dict(ok=False, error='a play is 0-8 (none for a tap)')
            return self._act(lambda: game._attempt(lambda: session.answer(value)))
        if name == 'word_game':
            # The word game's options by number (0 first), as a tap on a row or keys 1-9.
            options = session.engine.word_game.options if session.engine.word_game is not None else []
            if value is None or not 0 <= value < len(options):
                return dict(ok=False, error=f'the word game takes an option, 0 to {len(options) - 1}')
            return self._act(lambda: game.command(('choose', value)))
        return dict(ok=False, error=f'no mini-game is open ({name})')

    def _claire_window(self, x, y):
        """A point on the round's canvas, in window pixels (desktop._claire_point's inverse)."""
        game = self.game
        frame = game.bg_viewport
        width, height = game.claire_round_renderer.canvas.get_size()
        return frame.x + x * frame.width / width, frame.y + y * frame.height / height

    def _claire_tap(self, x, y):
        """A real tap at canvas (x, y): press and release a frame apart, then the state."""
        point = self._claire_window(x, y)
        self._pointer(pygame.MOUSEBUTTONDOWN, point, button=1)
        yield
        self._pointer(pygame.MOUSEBUTTONUP, point, button=1)
        result = yield from self._settled(0.3)
        return dict(result, tapped=[round(point[0]), round(point[1])])

    def _claire_spot(self, renderer, game, obj):
        """Canvas (x, y) of an opaque pixel of `obj` where it is the first listed, unfound object a tap hits (the round's
        own rule), nearest its middle; the view centred on it first when that pixel is off the play area. None if no
        such pixel."""
        from .claire_rounds import pixel_hit
        _, normal, _, _ = renderer.spec()['scenes'][game.scene]['objects'][obj]
        number, w, h, left, top = normal
        sprite = renderer.sprite(game.scene, number)
        step = max(1, min(w, h) // 12)
        points = sorted(((px, py) for py in range(0, h, step) for px in range(0, w, step)
                         if pixel_hit(lambda ax, ay: sprite.get_at((ax, ay))[3], w, h, px, py)),
                        key=lambda p: (p[0] - w / 2) ** 2 + (p[1] - h / 2) ** 2)
        wanted = [o for o in game.listed if o not in game.found]
        top_bar, bar_top = renderer.top_bar_bottom(), renderer.bar_top()
        for recentred in (False, True):
            if recentred:
                renderer.view.centre_on(left + w / 2, top + h / 2)    # (as the hint's marker brings an object into view)
            for px, py in points:
                x, y = renderer.view.to_canvas(left + px, top + py)
                if not (0 <= x < renderer.canvas.get_width() and top_bar + 4 <= y < bar_top - 24):
                    continue
                if renderer.hit(game, x, y) != ('scene', renderer.objects_at(game, x, y)):
                    continue
                hits = [o for o in renderer.objects_at(game, x, y) if o in wanted]
                if hits and hits[0] == obj:
                    return x, y
        return None

    def _claire_play(self, verb, arg):
        game = self.game
        if not game._claire_ready():
            return dict(ok=False, error='the round is not ready to play (opening, paused or a window over it)')
        renderer, round_ = game.claire_round_renderer, game.session.engine.claire_round
        if verb == 'continue':
            if not round_.over:
                return dict(ok=False, error='the round is still being played')
            button = renderer.summary_rects()[2]
            return self._claire_tap(*button.center)
        if round_.over:
            return dict(ok=False, error='the round is over: `play continue`')
        if verb == 'find':
            listed = [(slot, o) for slot, o in enumerate(round_.slots) if o >= 0 and o not in round_.found]
            if arg.isdigit():
                match = [o for slot, o in listed if slot == int(arg)]
            else:
                match = [o for _, o in listed if round_.names[o].lower() == arg.lower()]
            if not match:
                names = [round_.names[o] for _, o in listed]
                return dict(ok=False, error=f'{arg!r} is not listed to find; listed: {names}')
            spot = self._claire_spot(renderer, round_, match[0])
            if spot is None:
                return dict(ok=False, error=f'no spot on {round_.names[match[0]]} a tap reaches first')
            return self._claire_tap(*spot)
        if verb == 'miss':
            # The emptiest point of the play area: where no object's sprite is under the tap.
            width = renderer.canvas.get_width()
            for y in range(round(renderer.top_bar_bottom() + 10), round(renderer.bar_top() - 10), 23):
                for x in range(10, width - 10, 37):
                    if renderer.hit(round_, x, y) == ('scene', []):
                        return self._claire_tap(x, y)
            return dict(ok=False, error='no empty spot in view')
        if verb == 'hint':
            return self._claire_tap(*renderer.orb_rect().center)
        if verb == 'powerup':
            rects = renderer.segment_rects()
            if arg not in rects:
                return dict(ok=False, error=f'a power-up is one of {sorted(rects)}')
            return self._claire_tap(*rects[arg].center)
        if verb == 'pick':
            if not arg.isdigit() or not 0 <= int(arg) < len(round_.slots):
                return dict(ok=False, error=f'a slot is 0-{len(round_.slots) - 1}')
            return self._claire_tap(*renderer.label_rect(int(arg)).center)
        return dict(ok=False, error=f'a round takes find, miss, hint, powerup, pick or continue, not {verb!r}')

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
