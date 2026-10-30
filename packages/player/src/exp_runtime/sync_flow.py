"""LAN sync's pages and the app's side of it (Data Management's Sync Devices, owner 2026-10-30).

lan_sync.py finds the other device and moves the files; this decides what is sent and what a receiver does with it:

- **Sender** (Send to Another Device): a page of switches for what goes (SYNC_CATEGORIES, and Back Up Receiver First),
  then Find Receiver, a page of the receivers heard on the network for this game. Choosing one connects.
- **Receiver** (Receive from Another Device): a page saying it waits, with this device's name and address.
- Both: once connected, each asks its person "Send to X? / Receive from X?" with the same four-digit code; then the
  busy card shows the transfer, and a notice how it went (or the short reason it failed).

What goes is one progress bundle (progress_bundle.py: the saved games and trees when Saved Games & Trees is on, the
names when Names is, the shared options but those that stay per device when Options is) and the episodes the
receiver lacks. The receiver merges the bundle: each episode it holds replaces that episode's saves and tree there,
every other episode's stay. With Back Up Receiver First, what would be replaced (and the options, the names) goes
first into the receiver's backups folder, as a "before sync" backup Restore Progress can bring back.
"""
import logging
import os
from pathlib import Path
import shutil
import socket
import tempfile
import time

from . import lan_sync
from .menu import SHARED_PREFERENCES

SYNC_CATEGORIES = (('progress', 'Saved Games & Trees'), ('names', 'Names'), ('options', 'Options'),
                   ('episodes', 'Episodes'))
BACKUP_LABEL = 'Back Up Receiver First'
# Options that stay per device (owner, 2026-10-30): the vibration switches and the controller's own settings. (Start
# In and the chosen folders are app settings, never in a bundle.)
DEVICE_OPTIONS = ('vibration', 'device_vibration', 'controller_confirm', 'grid_controls')
SEND_PAGE, FIND_PAGE, RECEIVE_PAGE, SYNC_PAGE = 'data:send', 'data:find', 'data:receive', 'data:sync'


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


# SHSHD_SYNC_LOOPBACK=1 keeps sync to this computer's loopback: two copies of the app syncing with each other, with no
# firewall question (play-sync-test.ps1).
LOOPBACK = os.environ.get('SHSHD_SYNC_LOOPBACK') == '1'


class SyncFlow:
    # The network the sessions use (a test on one machine keeps them to its loopback).
    BIND, BEACON_ADDRESSES = ('127.0.0.1', ['127.0.0.1']) if LOOPBACK else ('0.0.0.0', None)
    DISCOVERY_PORT, PORT = lan_sync.DISCOVERY_PORT, lan_sync.PORT

    def __init__(self, app):
        self.app = app
        self.choices = {key: True for key, _ in SYNC_CATEGORIES}
        self.choices['backup'] = True
        self.finder = self.receiver = self.session = None
        self.devices = []
        self.asked = False              # the confirmation window is (or was) up for this session
        self.stage = None               # the receiver's folder for what arrives
        self.provider = None            # the sender's SendProvider (its folder holds the bundle it packed)
        self.pending = None             # (names data, options) for the UI thread to apply, from the receiver

    # -- pages --------------------------------------------------------------------------------------------------

    @property
    def shell(self):
        return self.app.shell

    def switches(self):
        """The send page's switch values, for the pause menu's settings."""
        return {f'sync_{key}': value for key, value in self.choices.items()}

    def toggle(self, key):
        key = key[len('sync_'):]
        self.choices[key] = not self.choices[key]
        self.show_send_page(reopen=False)

    def show_send_page(self, reopen=True):
        rows = [(f'sync_{key}', label, 'switch') for key, label in SYNC_CATEGORIES]
        rows += [('sync_backup', BACKUP_LABEL, 'switch'), ('sync_find', 'Find Receiver')]
        if reopen:
            self.shell.pause.show_rows(SEND_PAGE, 'Send', rows, SYNC_PAGE)
        else:
            self.shell.pause.row_pages = dict(self.shell.pause.row_pages, **{SEND_PAGE: ('Send', tuple(rows), SYNC_PAGE)})

    def find(self):
        """Find Receiver: listen for receivers' beacons, and list them on a page as they are heard."""
        if not any(self.choices[key] for key, _ in SYNC_CATEGORIES):
            self.shell.notify('Nothing to Send', 'Turn on at least one of the things to send.')
            return
        self.stop()
        hold_multicast(True)
        try:
            self.finder = lan_sync.Finder(port=self.DISCOVERY_PORT, bind=self.BIND)
        except OSError as error:
            hold_multicast(False)
            logging.warning('Sync: cannot listen for receivers: %s', error)
            self.shell.notify('Cannot Search', 'This device cannot listen on the network right now. Close any other '
                              'copy of SHSHD Runtime and try again.')
            return
        self.devices = []
        self.shell.pause.show_rows(FIND_PAGE, 'Choose Receiver', self.device_rows(), SEND_PAGE)

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
        self.asked = False
        self.provider = SendProvider(self.app, categories)
        self.session = lan_sync.SendSession(
            device.address, device.port, name=device_name(), app_version=self.app_version(),
            game=self.app.library.game_id, categories=categories, backup=self.choices['backup'],
            provider=self.provider).start()

    def receive(self):
        """Receive from Another Device: wait for a sender, on a page saying how to be found."""
        self.stop()
        library = self.app.library
        self.stage = Path(tempfile.mkdtemp(prefix='.sync-', dir=library.directory))
        try:
            self.receiver = lan_sync.Receiver(
                self.stage, name=device_name(), app_version=self.app_version(), game=library.game_id,
                host=ReceiveHost(self), port=self.PORT, bind=self.BIND, beacon_addresses=self.BEACON_ADDRESSES,
                discovery_port=self.DISCOVERY_PORT)
        except OSError as error:
            logging.warning('Sync: cannot wait for a sender: %s', error)
            self.stop()
            self.shell.notify('Cannot Receive', 'This device cannot listen on the network right now.')
            return
        body = (f'This device is waiting for a sender.\n\nOn the other device, choose Send to Another Device, then '
                f'Find Receiver, and pick "{device_name()}" ({self.receiver.address}).\n\nOn a computer, allow SHSHD '
                f'Runtime on private networks if Windows asks.')
        self.shell.pause.show_text(RECEIVE_PAGE, 'Receive', body, SYNC_PAGE)

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
        if not self.active:
            return
        pause = self.shell.pause
        screen = pause.state.screen if self.shell.pause_open else None
        session = self.current()
        if self.finder is not None:
            if screen != FIND_PAGE:
                self.stop()                     # the page was left
                return
            devices = self.finder.devices(self.app.library.game_id)
            if [d.key for d in devices] != [d.key for d in self.devices]:
                self.devices = devices
                pause.row_pages = dict(pause.row_pages, **{FIND_PAGE: ('Choose Receiver', tuple(self.device_rows()),
                                                                       SEND_PAGE)})
        if self.receiver is not None and session is None and screen != RECEIVE_PAGE:
            self.stop()
            return
        if session is None or self.app.busy:
            return
        if session.status == 'confirm':
            current = self.shell.stack.current if self.shell.stack.stack else None
            if not self.asked:
                self.asked = True
                sending = isinstance(session, lan_sync.SendSession)
                title = f'{"Send to" if sending else "Receive from"} {session.peer}?'
                message = (f'Check that {session.peer} shows the code {session.code}, then press '
                           f'{"Send" if sending else "Receive"}.')
                self.shell.confirm(title, message, 'Send' if sending else 'Receive', lambda: session.confirm(True))
            elif current != self.shell.CONFIRM_MENU and session._answer is None:
                session.confirm(False)          # No, or the window closed
            elif session._answer:
                self.start_job(session)         # this person said yes: wait for the other under the busy card
        elif session.status == 'transfer':
            self.start_job(session)
        elif session.finished:
            self.finished(session)

    def start_job(self, session):
        title = 'Sending' if isinstance(session, lan_sync.SendSession) else 'Receiving'
        self.app.start_data_job(title, lambda library: self.wait(session), self.finished)

    def current(self):
        if self.session is not None:
            return self.session
        return self.receiver.session if self.receiver is not None else None

    def wait(self, session):
        """The busy card's job: the session's own progress until it ends."""
        while not session.finished:
            self.app.progress_text = (session.progress if session.status == 'transfer' else '') or \
                f'Waiting for {session.peer or "the other device"}...'
            time.sleep(0.1)
        return session

    def finished(self, session):
        """How it went: the receiver applies the names and options on this thread, then both show a notice."""
        stack = self.shell.stack
        if stack.stack and stack.current == self.shell.CONFIRM_MENU:
            self.shell.close_window()           # the other person said no first
        pending, self.pending = self.pending, None
        received = isinstance(session, lan_sync.ReceiveSession)
        self.stop()
        if session.status == 'done':
            if pending is not None:
                self.apply(*pending)
            self.app.refresh_saves()
            self.app.picker = None
            self.shell.notify('Sync Complete', session.message or 'Done.')
            if received:
                self.app.prepare_previews()     # the episodes that came (the picker's previews)
        else:
            self.shell.notify('Sync Failed', session.message or lan_sync.LOST)

    def apply(self, player, options):
        """A received bundle's names (merged: the sender's win, the receiver's others stay), warp lock and options
        (those this app knows, outside DEVICE_OPTIONS)."""
        state = self.app.state
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
            self.app.apply_options({key: value for key, value in options.items() if key not in DEVICE_OPTIONS})
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
        self.devices, self.asked = [], False
        for folder in (self.stage, getattr(self.provider, 'folder', None)):
            if folder is not None:
                shutil.rmtree(folder, ignore_errors=True)
        self.stage = self.provider = None


class SendProvider:
    """What the sender sends (lan_sync.SendSession's provider), from its library."""

    def __init__(self, app, categories):
        self.app, self.categories = app, set(categories)
        self.library = app.library
        self.folder = None              # where items() packs the bundle (SyncFlow.stop removes it)
        state = app.state
        # Taken now, on the UI thread.
        self.player = {}
        if 'names' in self.categories:
            self.player.update(names=dict(state.names), name_sets={k: dict(v) for k, v in state.name_sets.items()})
        if 'progress' in self.categories:
            self.player['warp_unlocked'] = state.warp_unlocked
        self.options = ({key: getattr(state, key) for key in SHARED_PREFERENCES if key not in DEVICE_OPTIONS}
                        if 'options' in self.categories else None)

    def offer(self):
        """The episodes this library can send: imported ones (not built in, not inside the game's package)."""
        return [record['id'] for record in self.library.episodes if 'file' in record and not record.get('builtin')]

    def items(self, wanted):
        from .progress_bundle import write_bundle
        library = self.library
        folder = self.folder = Path(tempfile.mkdtemp(prefix='.sync-send-', dir=library.directory))
        bundle = folder / 'progress.zip'
        titles = {record['id']: record['titles'][0] for record in library.episodes}
        progress = 'progress' in self.categories
        write_bundle(library.directory, library.game_id, self.player, titles, bundle, note='sync',
                     keep=lambda name: progress, options=self.options)
        items = [('progress', 'progress.zip', bundle)]
        records = {record['id']: record for record in library.episodes}
        for index, key in enumerate(wanted or ()):
            record = records[key]
            name = Path(record.get('name') or key + '.exp').name
            items.append(('episode', f'{index}/{name if name.lower().endswith(".exp") else name + ".exp"}',
                          library.directory / record['file']))
        return items


class ReceiveHost:
    """What the receiver does with a sync (lan_sync.ReceiveSession's host)."""

    def __init__(self, flow):
        self.flow, self.app = flow, flow.app
        self.library = self.app.library

    def check(self, hello):
        from .games import GAMES
        game = hello.get('game')
        if game != self.library.game_id:
            sent = GAMES[game].TITLE if game in GAMES else 'another game'
            return (f'The receiving device has {GAMES[self.library.game_id].TITLE} open, not {sent}. Switch games '
                    f'there and try again.')
        return None

    def want(self, offered):
        have = {record['id'] for record in self.library.episodes}
        return [key for key in offered if key not in have]

    def apply(self, hello, stage):
        from .progress_bundle import bundle_options, merge_bundle, overwritten
        library, app = self.library, self.app
        parts = []
        bundle = stage / 'progress.zip'
        if bundle.is_file():
            options = bundle_options(bundle)
            if hello.get('backup'):
                # What the merge replaces, kept first (owner: Back Up Receiver First) in this device's backups folder.
                state = app.state
                kept = {key: getattr(state, key) for key in (options or {}) if hasattr(state, key)}
                app.back_up_progress(library, app.player_data(), note='before sync', keep=overwritten(bundle),
                                     options=kept or None)
            manifest, player = merge_bundle(library.directory, bundle, library.game_id)
            self.flow.pending = (player, options)
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
        if not parts:
            return 'Nothing needed to change.'
        # Shown on both devices, so it names neither side.
        listed = ', '.join(parts[:-1]) + ' and ' + parts[-1] if len(parts) > 1 else parts[0]
        return f'{listed[0].upper()}{listed[1:]} {"were" if len(parts) > 1 or not parts[0].startswith("1 ") else "was"} synced.'
