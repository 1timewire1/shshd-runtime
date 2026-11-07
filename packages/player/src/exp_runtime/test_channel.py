"""A test channel (shshd-runtime; owner, 2026-11-06): drive the running app from a script, by state rather than by screen taps.

Off unless the environment variable SHSHD_TEST_CHANNEL names a port. On Android that variable comes from the app's
`p4a_env_vars.txt`, which only `run-as` can write, and `run-as` works only on a debuggable build: a release build can
never open it. It listens on 127.0.0.1 only; from a PC, `adb forward tcp:PORT tcp:PORT` reaches it over the cable
(tools/test_channel.py is the client).

One command a line, one JSON reply a line. Commands run on the app's own thread, between frames, as input would, so
nothing here races the game. A command that takes time (`run-until`, `wait`) is stepped once a frame and replies when
it's done, so real clocks (fades, timers) run as in play.

    ping                        the app is up
    state                       what's showing: screen, pending story screen and its text/options, prompt, switches
    continue                    a tap on a line or panel (Enter)
    answer N                    pick choice or prompt row N (0 first)
    type TEXT                   type into name entry, then confirm it
    key NAME                    a key press: return, escape, up, down, left, right, space, n, u, ... (the menus' keys)
    back                        Android's Back (Escape)
    skip / undo                 Skip Ahead / Undo
    pause / resume              the pause menu
    set KEY on|off              a switch, as Options does (undo, skip_ahead, java_look, arena_minigames, ...)
    game shs|cod                pick a game, as the game picker does (`open` needs one picked)
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
    shot NAME                   save the window as NAME.png in the app's data folder; replies with its path
"""
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

KEYS = {name: getattr(pygame, 'K_' + name) for name in
        ('RETURN', 'ESCAPE', 'UP', 'DOWN', 'LEFT', 'RIGHT', 'SPACE', 'BACKSPACE', 'TAB')}
KEYS.update({name.lower(): code for name, code in KEYS.items()})
KEYS.update({chr(c): getattr(pygame, 'K_' + chr(c)) for c in range(ord('a'), ord('z') + 1)})
KEYS.update({str(d): getattr(pygame, f'K_{d}') for d in range(10)})
KEYS.update({'enter': pygame.K_RETURN, 'back': pygame.K_ESCAPE, 'f5': pygame.K_F5, 'f9': pygame.K_F9})
REPLY_TIMEOUT_S = 300
SLOW_MS = 100
TEXT_KEYS = ('text', 'title', 'prompt', 'speaker', 'options')


def from_environment(directory):
    """The channel the environment asks for (SHSHD_TEST_CHANNEL=port), or None. `directory` is where shots go."""
    value = os.environ.get('SHSHD_TEST_CHANNEL', '')
    if not value.isdigit():
        return None
    try:
        return TestChannel(int(value), Path(directory))
    except OSError as error:
        logging.warning('Test channel could not start: %s', error)
        return None


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
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(('127.0.0.1', port))
        self.server.listen(2)
        threading.Thread(target=self._serve, daemon=True, name='test-channel').start()
        logging.info('Test channel listening on 127.0.0.1:%s', port)

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
        return dict(ok=True, screen=self.app.screen)

    def do_state(self, _=''):
        app, game = self.app, self.game
        out = dict(ok=True, screen=app.screen, stage=getattr(app.shell, 'stage', None) if app.shell else None,
                   message=getattr(app, 'message', None), busy=bool(app.busy),
                   progress=getattr(app, 'progress_text', '') or None)
        prompt = getattr(app.shell, 'prompt', None) if app.shell else None
        if prompt is not None:
            out['menu_prompt'] = str(prompt)[:200]
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
        if game.host_prompt is not None:
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

    def do_game(self, rest):
        key = rest.strip().lower()
        if self.app.game is not None:
            return dict(ok=False, error='a story is open: leave it first')
        if getattr(self.app, 'selected_game', None) != key or self.app.library is None:
            self.app.choose_game(key)
        return self._settled(0.5)

    def do_open(self, rest):
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
        result = yield from self._open(record['id'])
        return dict(result, opened=record['id'][:12], copies=len(found))

    def _open(self, record_id):
        """A job: wait for the app to be free (first boot builds previews), start the episode, wait for its first screen."""
        end = time.perf_counter() + 600
        while self.app.busy and time.perf_counter() < end:
            yield
        self.app.state.selected = self.app.selected = record_id
        self.app.enter_episode(resume=False)
        result = yield from self._until(lambda: self.game is not None and self.game.session.pending is not None, 60)
        return result

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
                return True
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
                                                               or (kind == 'prompt' and self.game.host_prompt is not None))
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
        name = ''.join(c for c in (rest or 'shot') if c.isalnum() or c in '-_') or 'shot'
        path = self.channel.directory / f'{name}.png'
        path.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(pygame.display.get_surface(), str(path))
        return dict(ok=True, path=str(path))

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
