"""LAN sync's pages and the app's side of it (Data Management's Sync Devices, owner 2026-10-30).

lan_sync.py finds the other device and moves the files; this decides what is sent and what a receiver does with it:

- **Sender** (Send to Another Device): a page of switches for what goes (SYNC_CATEGORIES, and Back Up Receiver First),
  then Find Receiver, a page of the receivers heard on the network. Choosing one connects. In a game, that game is
  sent; from the game chooser's Options, both games (or the one chosen on the page's Games row).
- **Receiver** (Receive from Another Device): a page saying it waits, with this device's name and address. It takes
  each sent game it has a library of, whether that game is open or not (or no game is: the chooser).
- Both: once connected, each asks its person "Send to X? / Receive from X?" with the same four-digit code; then the
  busy card shows the transfer, and a notice how it went (or the short reason it failed).

What goes is a progress bundle per game (progress_bundle.py: the saved games and trees when Saved Games & Trees is on,
the names when Names is, the shared options but those that stay per device when Options is) and the episodes the
receiver lacks. The receiver merges each bundle: each episode it holds replaces that episode's saves and tree there,
every other episode's stay. With Back Up Receiver First, what would be replaced (and the options, the names) goes
first into the receiver's backups folder, as a "before sync" backup Restore Progress can bring back.

A sent game the receiver has no library of (owner, 2026-10-30) is named after the sync, and both people are asked
again: yes sends the sender's whole library of it (LIBRARY_PARTS), installed where that game's library belongs.

**Legacy Mode** (Sync Devices' switch, on by default for now; owner, 2026-10-30) syncs as the Android build does
(lan_sync protocol 1): one game, from inside it, with no whole library. The chooser's Send and Receive explain it must
be off there (LEGACY_NOTICE).
"""
from contextlib import contextmanager, nullcontext
import logging
import os
from pathlib import Path
import shutil
import socket
import tempfile
import time

from . import lan_sync
from .games import GAMES
from .menu import SHARED_PREFERENCES

SYNC_CATEGORIES = (('progress', 'Saved Games & Trees'), ('names', 'Names'), ('options', 'Options'),
                   ('episodes', 'Episodes'))
BACKUP_LABEL = 'Back Up Receiver First'
GAMES_LABEL = 'Games'
# Options that stay per device (owner, 2026-10-30): the vibration switches and the controller's own settings. (Start
# In and the chosen folders are app settings, never in a bundle.)
DEVICE_OPTIONS = ('vibration', 'device_vibration', 'controller_confirm', 'grid_controls')
SEND_PAGE, FIND_PAGE, RECEIVE_PAGE, SYNC_PAGE = 'data:send', 'data:find', 'data:receive', 'data:sync'
QUESTIONS = ('confirm', 'confirm_full')         # a session's statuses while its people are asked
LEGACY_NOTICE = ('Legacy Mode Is On', 'Legacy Mode syncs one game at a time, from inside that game. To sync both games '
                 'at once from here, turn Legacy Mode off on both devices (Sync Devices). Without it, sync works only '
                 'from computer to computer for now.')


def device_name():
    """This device's name, as the other device shows it (SHSHD_DEVICE_NAME names it instead: two copies on one
    computer, play-sync-test.ps1)."""
    from . import graphics
    name = os.environ.get('SHSHD_DEVICE_NAME')
    if not name:
        name = getattr(graphics, 'device_name', None)
        name = name() if callable(name) else None
    return (name or socket.gethostname() or 'This device')[:40]


def hold_multicast(held):
    """While the sender listens for beacons, a phone must keep its Wi-Fi taking broadcasts (Android drops them to save
    power without a multicast lock): the host's `graphics.hold_multicast`, where it has one."""
    from . import graphics
    hold = getattr(graphics, 'hold_multicast', None)
    if callable(hold):
        try:
            hold(held)
        except Exception as error:              # a phone without it still finds receivers it is told of
            logging.warning('Sync: multicast lock: %s', error)


def titles(games):
    """Games as a sentence names them ("Surviving High School and Cause of Death")."""
    return ' and '.join(GAMES[game].TITLE for game in games)


def open_library(app, game):
    """A game's library and its menu state: the open one's own, else opened for the job (closed after)."""
    if app.library is not None and app.library.game_id == game:
        return nullcontext((app.library, app.state))
    return app.opened_library(game)


# SHSHD_SYNC_LOOPBACK=1 keeps sync to this computer's loopback: two copies of the app syncing with each other, with no
# firewall question (play-sync-test.ps1).
LOOPBACK = os.environ.get('SHSHD_SYNC_LOOPBACK') == '1'


class ShellPages:
    """Sync's pages and windows in a game's menus: the HD shell's pause menu."""

    def __init__(self, app):
        self.app = app

    @property
    def menu(self):
        return self.app.shell.pause

    def screen(self):
        shell = self.app.shell
        return shell.pause.state.screen if shell is not None and shell.pause_open else None

    def notify(self, title, text):
        self.app.shell.notify(title, text)

    def confirm(self, title, text, verb, action):
        self.app.shell.confirm(title, text, verb, action)

    def asking(self):
        shell = self.app.shell
        return shell is not None and bool(shell.stack.stack) and shell.stack.current == shell.CONFIRM_MENU

    def close(self):
        if self.asking():
            self.app.shell.close_window()


class ChooserPages:
    """Sync's pages and windows in the game chooser's Options (desktop_app_hd.AppOptions): no library is open there."""

    def __init__(self, app):
        self.app = app
        self.window = None              # the question this flow put up

    @property
    def options(self):
        return self.app.app_screens.options

    @property
    def menu(self):
        return self.options.menu

    def screen(self):
        return self.menu.state.screen if self.app.screen == 'options' else None

    def notify(self, title, text):
        self.options.notice(title, text)

    def confirm(self, title, text, verb, action):
        self.window = self.options.ask = (title, text, ('No', verb), (None, action))

    def asking(self):
        return self.window is not None and self.options.ask is self.window

    def close(self):
        if self.asking():
            self.options.ask = None


class SyncFlow:
    # The network the sessions use (a test on one machine keeps them to its loopback).
    BIND, BEACON_ADDRESSES = ('127.0.0.1', ['127.0.0.1']) if LOOPBACK else ('0.0.0.0', None)
    DISCOVERY_PORT, PORT = lan_sync.DISCOVERY_PORT, lan_sync.PORT

    def __init__(self, app):
        self.app = app
        self.choices = {key: True for key, _ in SYNC_CATEGORIES}
        self.choices['backup'] = True
        self.game = None                # the chooser's Games row: one game, or None for every game with a library
        self.ui = None                  # ShellPages or ChooserPages: where this flow's pages are
        self.finder = self.receiver = self.session = None
        self.devices = []
        self.asked = None               # the question (a QUESTIONS status) put to this person for this session
        self.stage = None               # the receiver's folder for what arrives
        self.provider = None            # the sender's SendProvider (its folder holds the bundles it packed)
        self.pending = {}               # game -> (names data, options) for the UI thread to apply, from the receiver

    # -- pages --------------------------------------------------------------------------------------------------

    def pages(self):
        """Where this flow's pages go: the open game's menus, or the chooser's Options."""
        self.ui = ChooserPages(self.app) if self.app.library is None else ShellPages(self.app)
        return self.ui

    def games(self):
        """What a send takes: the open game, or (the chooser) the Games row's choice of those with a library."""
        if self.app.library is not None:
            return [self.app.library.game_id]
        have = self.app.games_with_libraries()
        return [self.game] if self.game in have else have

    def switches(self):
        """The send page's switch values (and the chooser's Games value), for the menu's settings."""
        values = {f'sync_{key}': value for key, value in self.choices.items()}
        values['sync_games'] = 'Both' if self.game is None else GAMES[self.game].TITLE
        values['sync_legacy'] = self.legacy
        return values

    @property
    def legacy(self):
        return self.app.settings.sync_legacy

    def legacy_blocked(self, ui):
        """The chooser's Send / Receive with Legacy Mode on: the notice why not (protocol 1 is one game, in it)."""
        if self.legacy and self.app.library is None:
            ui.notify(*LEGACY_NOTICE)
            return True
        return False

    def toggle(self, key):
        if key == 'sync_legacy':
            self.stop()
            self.app.settings.set_sync_legacy(not self.legacy)
            return
        key = key[len('sync_'):]
        self.choices[key] = not self.choices[key]
        self.show_send_page(reopen=False)

    def cycle_games(self):
        """The chooser's Games row: both, then each game."""
        order = [None] + self.app.games_with_libraries()
        self.game = order[(order.index(self.game) + 1) % len(order)] if self.game in order else None

    def show_send_page(self, reopen=True):
        ui = self.ui if not reopen else self.pages()
        if reopen and self.legacy_blocked(ui):
            return
        rows = []
        if self.app.library is None and len(self.app.games_with_libraries()) > 1:
            rows.append(('sync_games', GAMES_LABEL, 'cycle'))
        rows += [(f'sync_{key}', label, 'switch') for key, label in SYNC_CATEGORIES]
        rows += [('sync_backup', BACKUP_LABEL, 'switch'), ('sync_find', 'Find Receiver')]
        if reopen:
            ui.menu.show_rows(SEND_PAGE, 'Send', rows, SYNC_PAGE)
        else:
            ui.menu.row_pages = dict(ui.menu.row_pages, **{SEND_PAGE: ('Send', tuple(rows), SYNC_PAGE)})

    def find(self):
        """Find Receiver: listen for receivers' beacons, and list them on a page as they are heard."""
        ui = self.ui or self.pages()
        if not any(self.choices[key] for key, _ in SYNC_CATEGORIES):
            ui.notify('Nothing to Send', 'Turn on at least one of the things to send.')
            return
        self.stop()
        hold_multicast(True)
        try:
            self.finder = lan_sync.Finder(port=self.DISCOVERY_PORT, bind=self.BIND, protocol=(
                lan_sync.LEGACY_PROTOCOL if self.legacy else lan_sync.PROTOCOL))
        except OSError as error:
            hold_multicast(False)
            logging.warning('Sync: cannot listen for receivers: %s', error)
            ui.notify('Cannot Search', 'This device cannot listen on the network right now. Close any other copy of '
                      'SHSHD Runtime and try again.')
            return
        self.devices = []
        ui.menu.show_rows(FIND_PAGE, 'Choose Receiver', self.device_rows(), SEND_PAGE)

    def device_rows(self):
        if not self.devices:
            return [('sync_none', 'Looking for receivers...')]
        return [(f'sync_device:{index}', device.name) for index, device in enumerate(self.devices)]

    def choose(self, key):
        """A receiver's row: connect, and send once both people have said yes."""
        index = int(key.split(':', 1)[1])
        if index >= len(self.devices):
            return
        device = self.devices[index]
        self.finder.stop()
        self.finder = None
        hold_multicast(False)
        categories = [key for key, _ in SYNC_CATEGORIES if self.choices[key]]
        games = self.games()
        self.asked = None
        self.provider = SendProvider(self.app, categories, games)
        self.session = lan_sync.SendSession(
            device.address, device.port, name=device_name(), app_version=self.app_version(), games=games,
            categories=categories, backup=self.choices['backup'], provider=self.provider, legacy=self.legacy).start()

    def receive(self):
        """Receive from Another Device: wait for a sender, on a page saying how to be found."""
        self.stop()
        ui, app = self.pages(), self.app
        if self.legacy_blocked(ui):
            return
        # The stage sits by the libraries (a whole library sent is moved from it into its place).
        home = app.library.directory if app.library is not None else app.library_path(next(iter(GAMES))).parent
        home.mkdir(parents=True, exist_ok=True)
        self.stage = Path(tempfile.mkdtemp(prefix='.sync-', dir=home))
        try:
            self.receiver = lan_sync.Receiver(
                self.stage, name=device_name(), app_version=self.app_version(),
                game=app.library.game_id if app.library is not None else '', host=ReceiveHost(self), port=self.PORT,
                bind=self.BIND, beacon_addresses=self.BEACON_ADDRESSES, discovery_port=self.DISCOVERY_PORT,
                legacy=self.legacy)
        except OSError as error:
            logging.warning('Sync: cannot wait for a sender: %s', error)
            self.stop()
            ui.notify('Cannot Receive', 'This device cannot listen on the network right now.')
            return
        body = (f'This device is waiting for a sender.\n\nOn the other device, choose Send to Another Device, then '
                f'Find Receiver, and pick "{device_name()}" ({self.receiver.address}).\n\nOn a computer, allow SHSHD '
                f'Runtime on private networks if Windows asks.')
        ui.menu.show_text(RECEIVE_PAGE, 'Receive', body, SYNC_PAGE)

    @staticmethod
    def app_version():
        try:
            from .app_info import runtime_version
            return runtime_version()
        except Exception:
            return ''

    # -- each frame -----------------------------------------------------------------------------------------------

    @property
    def active(self):
        return self.finder is not None or self.receiver is not None or self.session is not None

    def tick(self):
        if not self.active or self.ui is None:
            return
        ui = self.ui
        screen = ui.screen()
        session = self.current()
        if self.finder is not None:
            if screen != FIND_PAGE:
                self.stop()                     # the page was left
                return
            # Every receiver is listed: one takes any game, opened for the sync or installed whole. (Legacy Mode's
            # receivers take only the game they have open.)
            devices = self.finder.devices(self.app.library.game_id if self.legacy else None)
            if [d.key for d in devices] != [d.key for d in self.devices]:
                self.devices = devices
                ui.menu.row_pages = dict(ui.menu.row_pages, **{FIND_PAGE: ('Choose Receiver', tuple(self.device_rows()),
                                                                           SEND_PAGE)})
        if self.receiver is not None and session is None and screen != RECEIVE_PAGE:
            self.stop()
            return
        if session is None or self.app.busy:
            return
        if session.status in QUESTIONS:
            if self.asked != session.status:
                self.asked = session.status
                self.ask(session)
            elif not ui.asking() and session._answer is None:
                session.confirm(False)          # No, or the window closed
            elif session._answer:
                self.start_job(session)         # this person said yes: wait for the other under the busy card
            return
        if self.asked is not None:
            ui.close()                          # the other person said no first
        if session.status == 'transfer':
            self.start_job(session)
        elif session.finished:
            self.finished(session)

    def ask(self, session):
        sending = isinstance(session, lan_sync.SendSession)
        verb = 'Send' if sending else 'Receive'
        if session.status == 'confirm':
            title = f'{"Send to" if sending else "Receive from"} {session.peer}?'
            message = f'Check that {session.peer} shows the code {session.code}, then press {verb}.'
        else:
            from .application import size_text
            games, size = session.full
            named = titles(games)
            title = f'{verb} {named} Too?'
            lacks = (f'{session.peer} has no {named} library' if sending else f'This device has no {named} library')
            message = (f'{lacks}. {"Send" if sending else session.peer + " can send"} the whole library '
                       f'({size_text(size)}): the game, its episodes, saved games, Decision Trees and names.')
        self.ui.confirm(title, message, verb, lambda: session.confirm(True))

    def start_job(self, session):
        title = 'Sending' if isinstance(session, lan_sync.SendSession) else 'Receiving'
        self.app.start_data_job(title, lambda library: self.wait(session), self.job_done)

    def job_done(self, session):
        if session.finished:
            self.finished(session)
        # Else a question came (a whole library): tick puts it to this person.

    def current(self):
        if self.session is not None:
            return self.session
        return self.receiver.session if self.receiver is not None else None

    def wait(self, session):
        """The busy card's job: the session's own progress until it ends, or until a question this person has not
        answered comes (a whole library: the job ends, so the window can show)."""
        while not session.finished and not (session.status == 'confirm_full' and session._answer is None):
            self.app.progress_text = (session.progress if session.status == 'transfer' else '') or \
                f'Waiting for {session.peer or "the other device"}...'
            time.sleep(0.1)
        return session

    def finished(self, session):
        """How it went: the receiver applies the names and options on this thread, then both show a notice."""
        ui = self.ui
        ui.close()                              # the other person said no first
        pending, self.pending = self.pending, {}
        received = isinstance(session, lan_sync.ReceiveSession)
        self.stop()
        app = self.app
        if session.status == 'done':
            for game, (player, options) in pending.items():
                with open_library(app, game) as (library, state):
                    self.apply(player, options, state)
            if app.library is not None:
                app.refresh_saves()
                app.picker = None
            ui.notify('Sync Complete', session.message or 'Done.')
            if received and app.library is not None:
                app.prepare_previews()          # the episodes that came (the picker's previews)
        else:
            ui.notify('Sync Failed', session.message or lan_sync.LOST)

    def apply(self, player, options, state=None):
        """A received bundle's names (merged: the sender's win, the receiver's others stay), warp lock and options
        (those this app knows, outside DEVICE_OPTIONS), into `state` (the open library's by default)."""
        app = self.app
        state = state if state is not None else app.state
        names, name_sets = player.get('names'), player.get('name_sets')
        if isinstance(names, dict):
            state.names.update({str(key): str(value) for key, value in names.items()})
        if isinstance(name_sets, dict):
            for key, table in name_sets.items():
                if isinstance(table, dict):
                    state.name_sets.setdefault(str(key), {}).update({str(k): str(v) for k, v in table.items()})
        if player.get('warp_unlocked'):
            state.warp_unlocked = True
        if isinstance(options, dict):
            options = {key: value for key, value in options.items() if key not in DEVICE_OPTIONS}
            if app.state is not None:
                app.apply_options(options)      # shared: the open game's, whichever game's bundle they came in
            else:
                # The chooser: the shared copy (settings.json), as its Options sets them; the next game opened takes it.
                from .menu import shared_preference
                app.settings.set_preferences({key: value for key, value in options.items()
                                              if shared_preference(key, value)})
        state.persist()

    def stop(self):
        """Leave sync: the ear, the waiting room and any session closed, the receiver's stage removed."""
        if self.finder is not None:
            self.finder.stop()
            hold_multicast(False)
        if self.receiver is not None:
            self.receiver.stop()
        if self.session is not None and not self.session.finished:
            self.session.cancel()
        self.finder = self.receiver = self.session = None
        self.devices, self.asked = [], None
        for folder in (self.stage, getattr(self.provider, 'folder', None)):
            if folder is not None:
                shutil.rmtree(folder, ignore_errors=True)
        self.stage = self.provider = None


def library_files(directory):
    """A library's own files (application.LIBRARY_PARTS: not a job's stage, nor anything else of the player's in its
    folder), as [(path in the library, file)]: what a whole library sent carries."""
    from .application import LIBRARY_PARTS
    directory, files = Path(directory), []
    for name in LIBRARY_PARTS:
        path = directory / name
        if path.is_file():
            files.append((name, path))
        elif path.is_dir():
            files += [(file.relative_to(directory).as_posix(), file) for file in sorted(path.rglob('*')) if file.is_file()]
    return files


class SendProvider:
    """What the sender sends (lan_sync.SendSession's provider), from each game's library."""

    def __init__(self, app, categories, games=None):
        self.app, self.categories = app, set(categories)
        self.games = list(games) if games is not None else [app.library.game_id]
        self.folder = None              # where items() packs the bundles (SyncFlow.stop removes it)
        # The open library's state is read now, on the UI thread; another game's when its library is opened.
        self.player = self.player_data(app.state) if app.state is not None else {}
        self.options = self.shared_options() if 'options' in self.categories else None

    def player_data(self, state):
        player = {}
        if 'names' in self.categories:
            player.update(names=dict(state.names), name_sets={k: dict(v) for k, v in state.name_sets.items()})
        if 'progress' in self.categories:
            player['warp_unlocked'] = state.warp_unlocked
        return player

    def shared_options(self):
        """The shared options but those that stay per device: the open game's, else the shared copy the chooser's
        Options shows (settings.json, over the defaults)."""
        app = self.app
        if app.state is not None:
            return {key: getattr(app.state, key) for key in SHARED_PREFERENCES if key not in DEVICE_OPTIONS}
        from .menu import preference_defaults, shared_preference
        values = dict(preference_defaults(), **{key: value for key, value in app.settings.preferences.items()
                                                if shared_preference(key, value)})
        return {key: value for key, value in values.items() if key in SHARED_PREFERENCES and key not in DEVICE_OPTIONS}

    @contextmanager
    def library(self, game):
        with open_library(self.app, game) as (library, state):
            yield library, (self.player if state is self.app.state else self.player_data(state))

    def offer(self, games):
        """Each game's episodes it can send: imported ones (not built in, not inside the game's package)."""
        offer = {}
        for game in games:
            with self.library(game) as (library, _):
                offer[game] = [record['id'] for record in library.episodes
                               if 'file' in record and not record.get('builtin')]
        return offer

    def items(self, games, wanted):
        from .progress_bundle import write_bundle
        folder = self.folder = Path(tempfile.mkdtemp(prefix='.sync-send-', dir=self.app.library_path(games[0])))
        progress = 'progress' in self.categories
        items = []
        for game in games:
            with self.library(game) as (library, player):
                bundle = folder / f'{game}.zip'
                titles = {record['id']: record['titles'][0] for record in library.episodes}
                write_bundle(library.directory, game, player, titles, bundle, note='sync',
                             keep=lambda name: progress, options=self.options)
                items.append(('progress', f'{game}/progress.zip', bundle))
                records = {record['id']: record for record in library.episodes}
                for index, key in enumerate(wanted.get(game) or ()):
                    record = records[key]
                    name = Path(record.get('name') or key + '.exp').name
                    items.append(('episode', f'{game}/{index}/{name if name.lower().endswith(".exp") else name + ".exp"}',
                                  library.directory / record['file']))
        return items

    def library_items(self, game):
        return library_files(self.app.library_path(game))

    def library_size(self, game):
        return sum(file.stat().st_size for _, file in self.library_items(game))


class ReceiveHost:
    """What the receiver does with a sync (lan_sync.ReceiveSession's host)."""

    def __init__(self, flow):
        self.flow, self.app = flow, flow.app

    def check(self, hello):
        if not any(game in GAMES for game in hello.get('games', ())):
            return 'The sending device sent no game this app knows.'
        return None

    def games(self, hello):
        """The sent games this device has a library of (taken), and those it lacks (offered whole after)."""
        have = self.app.games_with_libraries()
        sent = [game for game in hello.get('games', ()) if game in GAMES]
        return [game for game in sent if game in have], [game for game in sent if game not in have]

    def want(self, game, offered):
        with open_library(self.app, game) as (library, _):
            have = {record['id'] for record in library.episodes}
        return [key for key in offered if key not in have]

    def apply(self, hello, stage, games):
        messages = []
        for game in games:
            with open_library(self.app, game) as (library, state):
                parts = self.apply_game(hello, stage / game, library, state)
            if not parts:
                listed = 'nothing needed to change.'
            else:
                # Shown on both devices, so it names neither side.
                listed = ', '.join(parts[:-1]) + ' and ' + parts[-1] if len(parts) > 1 else parts[0]
                listed += f' {"were" if len(parts) > 1 or not parts[0].startswith("1 ") else "was"} synced.'
            messages.append(f'{GAMES[game].TITLE}: {listed}' if len(games) > 1 else listed[0].upper() + listed[1:])
        return ' '.join(messages)

    def apply_game(self, hello, stage, library, state):
        """One game's bundle and episodes, from `stage`; what was synced, as phrases."""
        from .progress_bundle import bundle_options, merge_bundle, overwritten
        app = self.app
        parts = []
        bundle = stage / 'progress.zip'
        if bundle.is_file():
            options = bundle_options(bundle)
            if hello.get('backup'):
                # What the merge replaces, kept first (owner: Back Up Receiver First) in this device's backups folder.
                kept = {key: getattr(state, key) for key in (options or {}) if hasattr(state, key)}
                app.back_up_progress(library, app.player_data(state), note='before sync', keep=overwritten(bundle),
                                     options=kept or None)
            manifest, player = merge_bundle(library.directory, bundle, library.game_id)
            self.flow.pending[library.game_id] = (player, options)
            if 'progress' in hello.get('categories', ()):
                count = len(manifest.get('saved', ()))
                parts.append(f'{count} saved game{"s" if count != 1 else ""}')
            if 'names' in hello.get('categories', ()):
                parts.append('the names')
            if options:
                parts.append('the options')
        episodes = stage / 'episodes'
        if episodes.is_dir() and any(episodes.rglob('*.exp')):
            added = library.add_episodes([episodes])
            parts.append(f'{added} episode{"s" if added != 1 else ""}')
        return parts

    def install(self, game, folder):
        """A whole library sent: its parts moved where this game's library belongs (library.json last, so one cut
        short is never a library the app would open)."""
        from .application import LIBRARY_PARTS
        target = self.app.library_path(game)
        if (target / 'library.json').is_file():
            raise OSError(f'This device has a {GAMES[game].TITLE} library already.')
        if not (folder / 'library.json').is_file():
            raise OSError(f'The {GAMES[game].TITLE} library sent has no library.json.')
        target.mkdir(parents=True, exist_ok=True)
        for name in sorted(LIBRARY_PARTS, key=lambda name: name == 'library.json'):
            source, place = folder / name, target / name
            if place.is_dir():
                shutil.rmtree(place)            # a deleted library's leftovers (its previews would be another's)
            elif place.exists():
                place.unlink()
            if source.exists():
                shutil.move(str(source), str(place))
        return f'The whole {GAMES[game].TITLE} library was copied.'
