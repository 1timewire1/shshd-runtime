"""LAN sync (Data Management, owner 2026-10-30): one device sends a game's progress, names, options and episodes to
another on the same network. This module only finds the other device and moves files; the app decides what is sent
and what a receiver does with it.

**Finding each other.** The receiver listens on TCP PORT (or any free port, if that one is taken) and announces itself
with a small UDP beacon to the network's broadcast addresses every BEACON_S. The sender listens for beacons on
DISCOVERY_PORT (an Android host holds a multicast lock meanwhile), or is given the receiver's address by hand.

**A connection** carries frames: a 4-byte big-endian length, a JSON header of that length, then `size` bytes of
payload when the header names one. The conversation:

    sender   -> hello   {protocol, app, name, game, categories, backup, nonce}
    receiver -> hello   {protocol, app, name, nonce, error?}   an error ends it (this device cannot take that game)
    both     -> confirm {ok}                                   each person checks the other's name and the code
    sender   -> offer   {episodes}  receiver -> want {episodes}  (only when episodes are sent)
    sender   -> item    {kind, name, index, count, size} + payload, for each item; then end {}
    receiver -> result  {ok, message}

`code` (four digits from both nonces) is shown on both screens, so each person can see they paired the right devices.
"""
from dataclasses import dataclass, field
import hashlib
import json
import logging
from pathlib import Path
import secrets
import select
import socket
import struct
import threading
import time

PROTOCOL = 1
APP = 'shshd-sync'
PORT = 47914                    # the receiver's TCP port, when it is free (the address typed by hand needs no port)
DISCOVERY_PORT = 47915          # the sender's UDP port, for receivers' beacons
BEACON_S = 1.0
DEVICE_TTL_S = 4.0              # a device not heard from for this long has gone
CONNECT_S = 5.0
IDLE_S = 30.0                   # a peer silent this long (outside the confirmations) is gone
CONFIRM_S = 300.0               # how long a person has to answer the confirmation
MAX_HEADER = 1 << 20
MAX_ITEM = 1 << 31
CHUNK = 1 << 16
CATEGORIES = ('progress', 'names', 'options', 'episodes')

# The short reasons a failed sync gives (owner: "a short error explaining why").
LOST = 'The connection to the other device was lost.'
DECLINED = 'The other device said no.'
CANCELLED = 'Sync was cancelled.'
CANCELLED_THERE = 'Sync was cancelled on the other device.'
VERSION = 'The other device has a different version of SHSHD Runtime; update both to the same version.'


class SyncError(Exception):
    """A sync that cannot go on; its message is the short reason both screens show."""


def local_address():
    """This device's address on the local network (the route a packet would take; nothing is sent), or 127.0.0.1."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(('10.255.255.255', 1))
        return probe.getsockname()[0]
    except OSError:
        return '127.0.0.1'
    finally:
        probe.close()


def broadcast_addresses():
    """Where a beacon goes: the limited broadcast, and this network's own (assumed a /24, the home-router norm)."""
    address = local_address()
    found = ['255.255.255.255']
    if not address.startswith('127.'):
        found.append(address.rsplit('.', 1)[0] + '.255')
    return found


def pairing_code(sender_nonce, receiver_nonce):
    digest = hashlib.sha256(f'{sender_nonce}:{receiver_nonce}'.encode()).hexdigest()
    return f'{int(digest, 16) % 10000:04d}'


# -- frames ---------------------------------------------------------------------------------------------------------

class Channel:
    """Frames over a connected socket (see the module docstring)."""

    def __init__(self, sock):
        self.sock = sock

    def send(self, header, payload=None, *, progress=None):
        """Send `header`; with `payload` (bytes, or a Path streamed from disk) its `size` is set and the payload follows.
        `progress(sent)` is told the payload bytes sent so far."""
        header = dict(header)
        if payload is not None:
            header['size'] = payload.stat().st_size if isinstance(payload, Path) else len(payload)
        data = json.dumps(header).encode()
        self.sock.sendall(struct.pack('>I', len(data)) + data)
        if payload is None:
            return
        if isinstance(payload, Path):
            sent = 0
            with payload.open('rb') as stream:
                for block in iter(lambda: stream.read(CHUNK), b''):
                    self.sock.sendall(block)
                    sent += len(block)
                    if progress:
                        progress(sent)
        else:
            self.sock.sendall(payload)
            if progress:
                progress(len(payload))

    def _exactly(self, count):
        data = bytearray()
        while len(data) < count:
            block = self.sock.recv(min(CHUNK, count - len(data)))
            if not block:
                raise SyncError(LOST)
            data += block
        return bytes(data)

    def header(self):
        (length,) = struct.unpack('>I', self._exactly(4))
        if length > MAX_HEADER:
            raise SyncError(LOST)
        try:
            header = json.loads(self._exactly(length))
        except ValueError as error:
            raise SyncError(LOST) from error
        if not isinstance(header, dict) or not isinstance(header.get('type'), str):
            raise SyncError(LOST)
        return header

    def payload(self, header, target=None):
        """The payload a header announced: as bytes, or written to `target` (a Path) when one is given."""
        size = header.get('size', 0)
        if not isinstance(size, int) or not 0 <= size <= MAX_ITEM:
            raise SyncError(LOST)
        if target is None:
            return self._exactly(size)
        with target.open('wb') as stream:
            left = size
            while left:
                block = self.sock.recv(min(CHUNK, left))
                if not block:
                    raise SyncError(LOST)
                stream.write(block)
                left -= len(block)
        return target

    def expect(self, kind):
        header = self.header()
        if header['type'] == 'cancel':
            raise SyncError(header.get('message') or CANCELLED)
        if header['type'] != kind:
            raise SyncError(LOST)
        return header


# -- discovery ------------------------------------------------------------------------------------------------------

@dataclass
class Device:
    name: str
    game: str
    address: str
    port: int
    seen: float = field(default_factory=time.monotonic)

    @property
    def key(self):
        return self.address, self.port


class Beacon:
    """The receiver's announcement, sent every BEACON_S until stopped."""

    def __init__(self, name, game, port, *, addresses=None, discovery_port=DISCOVERY_PORT):
        self.message = json.dumps(dict(app=APP, protocol=PROTOCOL, name=name, game=game, port=port)).encode()
        self.addresses = addresses
        self.discovery_port = discovery_port
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._run, name='sync-beacon', daemon=True)
        self.thread.start()

    def _run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            while not self.stopped.is_set():
                for address in self.addresses or broadcast_addresses():
                    try:
                        sock.sendto(self.message, (address, self.discovery_port))
                    except OSError:
                        pass                    # a network without that broadcast address; the other one may work
                self.stopped.wait(BEACON_S)
        finally:
            sock.close()

    def stop(self):
        self.stopped.set()


class Finder:
    """The sender's ear for beacons: `devices()` are the receivers heard in the last DEVICE_TTL_S."""

    def __init__(self, *, port=DISCOVERY_PORT, bind='0.0.0.0'):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((bind, port))
        self.sock.settimeout(0.5)
        self.found = {}
        self.lock = threading.Lock()
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._run, name='sync-finder', daemon=True)
        self.thread.start()

    def _run(self):
        try:
            while not self.stopped.is_set():
                try:
                    data, (address, _) = self.sock.recvfrom(4096)
                except socket.timeout:
                    continue
                except OSError:
                    return
                try:
                    beacon = json.loads(data)
                except ValueError:
                    continue
                if (not isinstance(beacon, dict) or beacon.get('app') != APP or beacon.get('protocol') != PROTOCOL
                        or not isinstance(beacon.get('port'), int) or not isinstance(beacon.get('name'), str)):
                    continue
                device = Device(beacon['name'][:40], str(beacon.get('game', '')), address, beacon['port'])
                with self.lock:
                    self.found[device.key] = device
        finally:
            self.sock.close()

    def devices(self, game=None):
        now = time.monotonic()
        with self.lock:
            return [device for device in self.found.values() if now - device.seen < DEVICE_TTL_S
                    and (game is None or device.game in ('', game))]

    def stop(self):
        self.stopped.set()


# -- sessions -------------------------------------------------------------------------------------------------------

class Session:
    """One side of a sync, run on its own thread. The app polls `status` ('connecting', 'confirm', 'transfer', 'done',
    'failed'), `peer`, `code`, `progress` (a short line) and `message`, and answers with `confirm(ok)` / `cancel()`."""

    def __init__(self, name, app_version):
        self.name, self.app_version = name, app_version
        self.status, self.peer, self.code, self.progress, self.message = 'connecting', '', '', '', ''
        self.nonce = secrets.token_hex(8)
        self._answer = None
        self._answered = threading.Event()
        self._cancelled = threading.Event()
        self.channel = None
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self._guarded, name=f'sync-{type(self).__name__}', daemon=True)
        self.thread.start()
        return self

    def confirm(self, ok):
        self._answer = bool(ok)
        self._answered.set()

    def cancel(self):
        """End it from this side: the other side is told why first, then this session's thread lets go (were it let go
        first, it could close the connection before the message went, and the other side would read a lost one)."""
        self._cancelled.set()
        channel = self.channel
        if channel is not None:
            try:
                channel.send(dict(type='cancel', message=CANCELLED_THERE))
            except OSError:
                pass
            try:
                channel.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        self._answered.set()

    @property
    def finished(self):
        return self.status in ('done', 'failed')

    def _guarded(self):
        try:
            self.message = self._run() or ''
            self.status = 'done'
        except SyncError as error:
            self.message, self.status = (CANCELLED if self._cancelled.is_set() else str(error)), 'failed'
        except (OSError, socket.timeout) as error:
            logging.warning('Sync: %s', error)
            self.message, self.status = (CANCELLED if self._cancelled.is_set() else LOST), 'failed'
        except Exception as error:              # the app's own step failed: its message is the reason
            logging.exception('Sync failed')
            self.message, self.status = str(error) or LOST, 'failed'
        finally:
            if self.channel is not None:
                try:
                    self.channel.sock.close()
                except OSError:
                    pass

    def _confirm(self, channel):
        """Both people answer; a no on either side ends it. While this person thinks, the other side's answer (or its
        cancel) is read as soon as it comes, so a no there closes this side's question at once."""
        self.status = 'confirm'
        channel.sock.settimeout(CONFIRM_S)
        deadline, peer = time.monotonic() + CONFIRM_S, None
        while not self._answered.wait(0.2):
            if time.monotonic() > deadline:
                raise SyncError(CANCELLED)
            if peer is None and select.select([channel.sock], [], [], 0)[0]:
                peer = channel.expect('confirm')
                if not peer.get('ok'):
                    raise SyncError(DECLINED)
        if self._cancelled.is_set():
            raise SyncError(CANCELLED)
        channel.send(dict(type='confirm', ok=self._answer))
        if not self._answer:
            raise SyncError(CANCELLED)
        if peer is None and not channel.expect('confirm').get('ok'):
            raise SyncError(DECLINED)
        channel.sock.settimeout(IDLE_S)
        self.status = 'transfer'

    def _hello(self, header):
        if header.get('protocol') != PROTOCOL:
            raise SyncError(VERSION)
        self.peer = str(header.get('name', ''))[:40] or 'Another device'


class SendSession(Session):
    """The sender. `provider` supplies what goes:
    - `offer()`: the episode ids it could send (None without the episodes category);
    - `items(wanted)`: after both confirmed, [(kind, name, payload bytes or Path)], given the episodes the receiver
      wants. Called on this session's thread."""

    def __init__(self, address, port, *, name, app_version, game, categories, backup, provider):
        super().__init__(name, app_version)
        self.address, self.port = address, port
        self.game, self.categories, self.backup = game, list(categories), bool(backup)
        self.provider = provider

    def _run(self):
        sock = socket.create_connection((self.address, self.port), timeout=CONNECT_S)
        sock.settimeout(IDLE_S)
        channel = self.channel = Channel(sock)
        channel.send(dict(type='hello', protocol=PROTOCOL, app=self.app_version, name=self.name, game=self.game,
                          categories=self.categories, backup=self.backup, nonce=self.nonce))
        reply = channel.expect('hello')
        self._hello(reply)
        if reply.get('error'):
            raise SyncError(str(reply['error']))
        self.code = pairing_code(self.nonce, reply.get('nonce', ''))
        self._confirm(channel)
        wanted = None
        offer = self.provider.offer() if 'episodes' in self.categories else None
        if offer is not None:
            channel.send(dict(type='offer', episodes=list(offer)))
            wanted = [key for key in channel.expect('want').get('episodes', []) if key in set(offer)]
        self.progress = 'Packing...'
        items = self.provider.items(wanted)
        for index, (kind, name, payload) in enumerate(items):
            label = f'Sending {index + 1} of {len(items)}'
            self.progress = label
            channel.send(dict(type='item', kind=kind, name=name, index=index, count=len(items)), payload)
        channel.send(dict(type='end'))
        self.progress = 'Waiting for the other device...'
        channel.sock.settimeout(None)               # the receiver applies everything before it answers
        result = channel.expect('result')
        if not result.get('ok'):
            raise SyncError(str(result.get('message') or LOST))
        return str(result.get('message', ''))


class ReceiveSession(Session):
    """The receiver's side of one connection. `host` decides:
    - `check(hello)`: None, or the reason this device cannot take the sync (no library of that game);
    - `want(ids)`: which of the offered episodes it lacks;
    - `apply(hello, stage)`: everything has arrived in `stage` (items by kind: progress.zip, options.json,
      episodes/<name>); returns the success message. Called on this session's thread."""

    def __init__(self, sock, stage, *, name, app_version, host):
        super().__init__(name, app_version)
        self.sock, self.stage, self.host = sock, Path(stage), host
        self.hello = None

    def _run(self):
        self.sock.settimeout(IDLE_S)
        channel = self.channel = Channel(self.sock)
        hello = self.hello = channel.expect('hello')
        if hello.get('protocol') != PROTOCOL:
            channel.send(dict(type='hello', protocol=PROTOCOL, app=self.app_version, name=self.name,
                              nonce=self.nonce, error=VERSION))
            raise SyncError(VERSION)
        self._hello(hello)
        error = self.host.check(hello)
        channel.send(dict(type='hello', protocol=PROTOCOL, app=self.app_version, name=self.name, nonce=self.nonce,
                          **(dict(error=error) if error else {})))
        if error:
            raise SyncError(error)
        self.code = pairing_code(hello.get('nonce', ''), self.nonce)
        self._confirm(channel)
        if 'episodes' in hello.get('categories', ()):
            offered = [key for key in channel.expect('offer').get('episodes', []) if isinstance(key, str)]
            channel.send(dict(type='want', episodes=list(self.host.want(offered))))
        (self.stage / 'episodes').mkdir(parents=True, exist_ok=True)
        while True:
            header = channel.header()
            if header['type'] == 'end':
                break
            if header['type'] == 'cancel':
                raise SyncError(header.get('message') or CANCELLED)
            if header['type'] != 'item':
                raise SyncError(LOST)
            self.progress = f'Receiving {header.get("index", 0) + 1} of {header.get("count", 0)}'
            channel.payload(header, self._target(header))
        self.progress = 'Applying...'
        try:
            message = self.host.apply(hello, self.stage)
        except Exception as error:
            logging.exception('Sync: applying failed')
            channel.send(dict(type='result', ok=False, message=str(error) or LOST))
            raise SyncError(str(error) or LOST) from error
        channel.send(dict(type='result', ok=True, message=message))
        return message

    def _target(self, header):
        """Where an item lands in the stage. An episode is named `<n>/<file>.exp`: a folder each, since two episodes
        may share a file name (an HD and a standard "The_New_Girl.exp")."""
        kind, name = header.get('kind'), str(header.get('name', ''))
        if kind == 'episode':
            folder, _, file = name.rpartition('/')
            file = Path(file).name
            if folder.isdigit() and file.lower().endswith('.exp') and file not in ('.exp',):
                (self.stage / 'episodes' / folder).mkdir(parents=True, exist_ok=True)
                return self.stage / 'episodes' / folder / file
            raise SyncError(LOST)
        name = Path(name).name
        if kind in ('progress', 'options'):
            return self.stage / {'progress': 'progress.zip', 'options': 'options.json'}[kind]
        raise SyncError(LOST)


class Receiver:
    """The receiver's waiting room: a listening port, its beacon, and the session of the one sender that connects
    (`session`, None until then). Later senders are turned away while a session runs."""

    def __init__(self, stage, *, name, app_version, game, host, port=PORT, bind='0.0.0.0', beacon_addresses=None,
                 discovery_port=DISCOVERY_PORT):
        self.stage, self.name, self.app_version, self.host = Path(stage), name, app_version, host
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.server.bind((bind, port))
        except OSError:
            self.server.bind((bind, 0))         # the usual port is taken: any free one (the beacon carries it)
        self.server.listen(2)
        self.server.settimeout(0.5)
        self.port = self.server.getsockname()[1]
        self.address = local_address()
        self.session = None
        self.stopped = threading.Event()
        self.beacon = Beacon(name, game, self.port, addresses=beacon_addresses, discovery_port=discovery_port)
        self.thread = threading.Thread(target=self._run, name='sync-receiver', daemon=True)
        self.thread.start()

    def _run(self):
        try:
            while not self.stopped.is_set():
                try:
                    sock, _ = self.server.accept()
                except socket.timeout:
                    continue
                except OSError:
                    return
                if self.session is not None and not self.session.finished:
                    sock.close()
                    continue
                self.beacon.stop()
                self.session = ReceiveSession(sock, self.stage, name=self.name, app_version=self.app_version,
                                              host=self.host).start()
        finally:
            self.server.close()

    def stop(self):
        self.stopped.set()
        self.beacon.stop()
        if self.session is not None and not self.session.finished:
            self.session.cancel()
