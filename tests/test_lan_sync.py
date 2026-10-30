"""LAN sync's discovery, pairing and transfer (owner's design, 2026-10-30), over this machine's loopback."""
import json
from pathlib import Path
import socket
import tempfile
import time
import unittest

from exp_runtime import lan_sync
from exp_runtime.lan_sync import Beacon, Finder, Receiver, SendSession


def wait(test, condition, seconds=10):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


def free_port(kind=socket.SOCK_DGRAM):
    with socket.socket(socket.AF_INET, kind) as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


class Provider:
    def __init__(self, root, episodes):
        self.root, self.episodes = Path(root), episodes
        self.wanted = None
        library = self.root / 'sender-cod'
        (library / 'content').mkdir(parents=True, exist_ok=True)
        (library / 'library.json').write_text('{"game": "cod"}')
        (library / 'content' / 'v1.exp').write_bytes(b'volume one')

    def offer(self, games):
        return {game: list(self.episodes) for game in games}

    def items(self, games, wanted):
        self.wanted = wanted
        episode = self.root / 'b.exp'
        episode.write_bytes(b'episode b' * 10000)            # a file streamed in blocks
        items = [('progress', f'{game}/progress.zip', b'bundle bytes') for game in games]
        return items + [('episode', f'{game}/{index}/{key}.exp', episode)
                        for game in games for index, key in enumerate(wanted.get(game, ()))]

    def library_items(self, game):
        folder = self.root / 'sender-cod'
        return [(path.relative_to(folder).as_posix(), path) for path in sorted(folder.rglob('*')) if path.is_file()]

    def library_size(self, game):
        return sum(path.stat().st_size for _, path in self.library_items(game))


class Host:
    def __init__(self, *, error=None, have=(), fail=None, games=('shs',)):
        self.error, self.have, self.fail, self.has = error, set(have), fail, set(games)
        self.applied = self.installed = None

    def check(self, hello):
        return self.error

    def games(self, hello):
        offered = hello.get('games', ())
        return [game for game in offered if game in self.has], [game for game in offered if game not in self.has]

    def want(self, game, offered):
        return [key for key in offered if key not in self.have]

    def apply(self, hello, stage, games):
        if self.fail:
            raise OSError(self.fail)
        self.applied = (hello, games, {path.relative_to(stage).as_posix(): path.read_bytes()
                                       for path in stage.rglob('*') if path.is_file()})
        return 'Received 1 episode.'

    def install(self, game, folder):
        self.installed = (game, {path.relative_to(folder).as_posix(): path.read_bytes()
                                 for path in folder.rglob('*') if path.is_file()})
        return f'The {game} library was installed.'


class SyncTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def receiver(self, host):
        receiver = Receiver(self.root / 'stage', name='Phone', app_version='1.0.2', game='shs', host=host,
                            port=0, bind='127.0.0.1', beacon_addresses=['127.0.0.1'], discovery_port=free_port())
        self.addCleanup(receiver.stop)
        return receiver

    def sender(self, receiver, provider, categories=('progress', 'options', 'episodes'), games=('shs',)):
        session = SendSession('127.0.0.1', receiver.port, name='PC', app_version='1.0.2', games=games,
                              categories=categories, backup=True, provider=provider).start()
        self.addCleanup(session.cancel)
        return session

    def test_both_confirm_then_the_items_arrive_and_both_hear_how_it_went(self):
        host, provider = Host(have={'a'}), Provider(self.root, ['a', 'b'])
        receiver = self.receiver(host)
        sender = self.sender(receiver, provider)
        self.assertTrue(wait(self, lambda: sender.status == 'confirm' and receiver.session is not None
                             and receiver.session.status == 'confirm'))
        incoming = receiver.session
        self.assertEqual((sender.peer, incoming.peer), ('Phone', 'PC'))
        self.assertRegex(sender.code, r'^\d{4}$')
        self.assertEqual(sender.code, incoming.code)                   # the same four digits on both screens
        sender.confirm(True)
        time.sleep(0.2)
        self.assertEqual(sender.status, 'confirm')                     # still waiting on the other person
        incoming.confirm(True)
        self.assertTrue(wait(self, lambda: sender.finished and incoming.finished))
        self.assertEqual((sender.status, sender.message), ('done', 'Received 1 episode.'))
        self.assertEqual(incoming.status, 'done')
        self.assertEqual(provider.wanted, {'shs': ['b']})              # the receiver had 'a'
        hello, games, files = host.applied
        self.assertEqual((hello['backup'], hello['games'], games), (True, ['shs'], ['shs']))
        self.assertEqual(files, {'shs/progress.zip': b'bundle bytes', 'shs/episodes/0/b.exp': b'episode b' * 10000})

    def test_a_no_on_either_side_ends_it_for_both_at_once(self):
        for refuser in ('sender', 'receiver'):
            with self.subTest(refuser=refuser):
                host = Host()
                receiver = self.receiver(host)
                sender = self.sender(receiver, Provider(self.root, []))
                self.assertTrue(wait(self, lambda: receiver.session is not None and receiver.session.status == 'confirm'
                                     and sender.status == 'confirm'))
                incoming = receiver.session
                (sender if refuser == 'sender' else incoming).confirm(False)
                other = incoming if refuser == 'sender' else sender
                self.assertTrue(wait(self, lambda: other.finished))     # without its person answering
                self.assertEqual((other.status, other.message), ('failed', lan_sync.DECLINED))
                self.assertIsNone(host.applied)

    def test_a_receiver_without_that_game_says_why(self):
        reason = 'This device has no Cause of Death library.'
        receiver = self.receiver(Host(error=reason))
        sender = self.sender(receiver, Provider(self.root, []))
        self.assertTrue(wait(self, lambda: sender.finished))
        self.assertEqual((sender.status, sender.message), ('failed', reason))

    def test_a_failure_applying_reaches_the_sender(self):
        receiver = self.receiver(Host(fail='Not enough space on this device.'))
        sender = self.sender(receiver, Provider(self.root, []), categories=('progress',))
        self.assertTrue(wait(self, lambda: receiver.session is not None and receiver.session.status == 'confirm'))
        sender.confirm(True)
        receiver.session.confirm(True)
        self.assertTrue(wait(self, lambda: sender.finished))
        self.assertEqual((sender.status, sender.message), ('failed', 'Not enough space on this device.'))

    def test_cancelling_while_waiting_ends_the_other_side(self):
        receiver = self.receiver(Host())
        sender = self.sender(receiver, Provider(self.root, []))
        self.assertTrue(wait(self, lambda: receiver.session is not None and receiver.session.status == 'confirm'))
        sender.cancel()
        self.assertTrue(wait(self, lambda: receiver.session.finished))
        self.assertEqual(receiver.session.message, lan_sync.CANCELLED_THERE)
        self.assertTrue(wait(self, lambda: sender.finished))
        self.assertEqual(sender.message, lan_sync.CANCELLED)

    def confirm_both(self, sender, receiver, status='confirm'):
        self.assertTrue(wait(self, lambda: sender.status == status and receiver.session is not None
                             and receiver.session.status == status))
        self.assertEqual(sender.code, receiver.session.code)
        sender.confirm(True)
        receiver.session.confirm(True)

    def test_both_games_sync_what_the_receiver_has_then_offer_the_missing_library_whole(self):
        host, provider = Host(games=('shs',)), Provider(self.root, ['b'])
        receiver = self.receiver(host)
        sender = self.sender(receiver, provider, games=('shs', 'cod'))
        self.confirm_both(sender, receiver)
        self.confirm_both(sender, receiver, 'confirm_full')               # CoD: no library there
        self.assertEqual(sender.full[0], ['cod'])
        self.assertEqual(sender.full[1], len(b'{"game": "cod"}') + len(b'volume one'))
        self.assertTrue(wait(self, lambda: sender.finished and receiver.session.finished))
        self.assertEqual(sender.status, 'done')
        self.assertEqual(sender.message, 'Received 1 episode. The cod library was installed.')
        self.assertEqual(host.applied[1], ['shs'])                         # only SHS synced as progress
        self.assertEqual(host.installed, ('cod', {'library.json': b'{"game": "cod"}', 'content/v1.exp': b'volume one'}))

    def test_a_no_to_the_whole_library_keeps_the_sync_that_was_made(self):
        for refuser in ('sender', 'receiver'):
            with self.subTest(refuser=refuser):
                host = Host(games=('shs',))
                receiver = self.receiver(host)
                sender = self.sender(receiver, Provider(self.root, []), categories=('progress',), games=('shs', 'cod'))
                self.confirm_both(sender, receiver)
                self.assertTrue(wait(self, lambda: sender.status == 'confirm_full'
                                     and receiver.session.status == 'confirm_full'))
                (sender if refuser == 'sender' else receiver.session).confirm(False)
                other = receiver.session if refuser == 'sender' else sender
                self.assertTrue(wait(self, lambda: sender.finished and receiver.session.finished))
                self.assertEqual((sender.status, receiver.session.status), ('done', 'done'))
                self.assertEqual(sender.message, 'Received 1 episode.')
                self.assertIsNone(host.installed)
                self.assertIsNot(other, None)

    def test_a_receiver_without_any_of_the_games_can_still_take_them_whole(self):
        host = Host(games=())
        receiver = self.receiver(host)
        sender = self.sender(receiver, Provider(self.root, []), games=('cod',))
        self.confirm_both(sender, receiver)
        self.confirm_both(sender, receiver, 'confirm_full')
        self.assertTrue(wait(self, lambda: sender.finished))
        self.assertEqual((sender.status, sender.message), ('done', 'The cod library was installed.'))
        self.assertIsNone(host.applied)

    def test_an_item_outside_its_game_or_its_folder_ends_the_sync(self):
        from exp_runtime.lan_sync import ReceiveSession, SyncError
        session = ReceiveSession(None, self.root / 'stage', name='Phone', app_version='', host=Host())
        for header in (dict(kind='library', name='cod/../../x'), dict(kind='progress', name='other/progress.zip'),
                       dict(kind='episode', name='shs/a/b.exp'), dict(kind='library', name='shs/C:/x')):
            with self.subTest(header=header), self.assertRaises(SyncError):
                session._target(header, ['shs', 'cod'])
        self.assertEqual(session._target(dict(kind='library', name='cod/content/v.exp'), ['cod']),
                         self.root / 'stage' / 'library' / 'cod' / 'content' / 'v.exp')

    def test_a_beacon_is_heard_and_forgotten_once_it_stops(self):
        port = free_port()
        finder = Finder(port=port, bind='127.0.0.1')
        self.addCleanup(finder.stop)
        beacon = Beacon('Phone', 'cod', 50000, addresses=['127.0.0.1'], discovery_port=port)
        self.assertTrue(wait(self, lambda: finder.devices()))
        (device,) = finder.devices()
        self.assertEqual((device.name, device.game, device.address, device.port), ('Phone', 'cod', '127.0.0.1', 50000))
        self.assertEqual(finder.devices('shs'), [])                    # another game's receiver is not offered
        beacon.stop()
        stale = time.monotonic() + lan_sync.DEVICE_TTL_S + 1
        for device in finder.found.values():
            device.seen -= stale                                       # as if long unheard
        self.assertEqual(finder.devices(), [])
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as other:   # strangers' packets are ignored
            other.sendto(json.dumps({'app': 'else'}).encode(), ('127.0.0.1', port))
        time.sleep(0.2)
        self.assertEqual(finder.devices(), [])


if __name__ == '__main__':
    unittest.main()
