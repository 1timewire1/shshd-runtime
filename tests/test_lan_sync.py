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

    def offer(self):
        return list(self.episodes)

    def items(self, wanted):
        self.wanted = wanted
        episode = self.root / 'b.exp'
        episode.write_bytes(b'episode b' * 10000)            # a file streamed in blocks
        items = [('progress', 'progress.zip', b'bundle bytes'), ('options', 'options.json', b'{"autoplay": true}')]
        return items + [('episode', f'{key}.exp', episode) for key in wanted or ()]


class Host:
    def __init__(self, *, error=None, have=(), fail=None):
        self.error, self.have, self.fail = error, set(have), fail
        self.applied = None

    def check(self, hello):
        return self.error

    def want(self, offered):
        return [key for key in offered if key not in self.have]

    def apply(self, hello, stage):
        if self.fail:
            raise OSError(self.fail)
        self.applied = (hello, {path.relative_to(stage).as_posix(): path.read_bytes()
                                for path in stage.rglob('*') if path.is_file()})
        return 'Received 1 episode.'


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

    def sender(self, receiver, provider, categories=('progress', 'options', 'episodes')):
        session = SendSession('127.0.0.1', receiver.port, name='PC', app_version='1.0.2', game='shs',
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
        self.assertEqual(provider.wanted, ['b'])                       # the receiver had 'a'
        hello, files = host.applied
        self.assertEqual((hello['backup'], hello['game']), (True, 'shs'))
        self.assertEqual(files, {'progress.zip': b'bundle bytes', 'options.json': b'{"autoplay": true}',
                                 'episodes/b.exp': b'episode b' * 10000})

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
