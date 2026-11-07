"""The test channel (test_channel.py): off unless asked for, local only, commands run between frames."""
import json
import os
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


def free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


class TestChannelTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime import test_channel
        self.module = test_channel
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)

    def test_it_is_off_unless_the_environment_names_a_port(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('SHSHD_TEST_CHANNEL', None)
            self.assertIsNone(self.module.from_environment(self.temporary.name))
        with mock.patch.dict(os.environ, {'SHSHD_TEST_CHANNEL': 'yes'}):
            self.assertIsNone(self.module.from_environment(self.temporary.name))

    def test_commands_run_on_the_apps_thread_and_reply_as_json(self):
        port = free_port()
        with mock.patch.dict(os.environ, {'SHSHD_TEST_CHANNEL': str(port)}):
            channel = self.module.from_environment(self.temporary.name)
        self.addCleanup(channel.server.close)
        app = SimpleNamespace(screen='main', shell=None, message='', busy=False, progress_text='', game=None, state=None)
        replies, stop = [], threading.Event()

        def client():
            with socket.create_connection(('127.0.0.1', port), timeout=10) as connection, \
                    connection.makefile('rw', encoding='utf-8', newline='\n') as stream:
                for line in ('ping', 'state', 'nonsense', 'answer 1', 'wait 0.05'):
                    stream.write(line + '\n')
                    stream.flush()
                    replies.append(json.loads(stream.readline()))
            stop.set()
        threading.Thread(target=client, daemon=True).start()
        end = time.time() + 10
        while not stop.is_set() and time.time() < end:
            channel.poll(app)                              # (the app's loop, a frame at a time)
            time.sleep(0.005)
        self.assertEqual(replies[0], dict(ok=True, screen='main'))
        self.assertEqual((replies[1]['screen'], replies[1]['busy']), ('main', False))
        self.assertEqual(replies[2]['ok'], False)
        self.assertIn('no story is open', replies[3]['error'])
        self.assertTrue(replies[4]['ok'])

    def test_timing_and_profile_report_on_the_frames_between(self):
        port = free_port()
        channel = self.module.TestChannel(port, Path(self.temporary.name))
        self.addCleanup(channel.server.close)
        app = SimpleNamespace(screen='main', shell=None, message='', busy=False, progress_text='', game=None, state=None)
        replies, stop = [], threading.Event()

        def client():
            with socket.create_connection(('127.0.0.1', port), timeout=10) as connection, \
                    connection.makefile('rw', encoding='utf-8', newline='\n') as stream:
                for line in ('timing on', 'profile on', 'wait 0.2', 'profile off sleep', 'timing off', 'profile off'):
                    stream.write(line + '\n')
                    stream.flush()
                    replies.append(json.loads(stream.readline()))
            stop.set()
        threading.Thread(target=client, daemon=True).start()
        end, slept = time.time() + 10, False
        while not stop.is_set() and time.time() < end:
            channel.poll(app)
            if channel.profiler is not None and not slept:
                time.sleep(0.12)                          # one slow frame, while profiled
                slept = True
            time.sleep(0.005)
        profile, timing = replies[3], replies[4]
        self.assertTrue(profile['ok'])
        self.assertTrue(profile['total'] and all('sleep' in row['call'] for row in profile['total']))
        self.assertGreater(timing['frames'], 0)
        self.assertTrue(timing['slow'] and timing['slow'][0]['ms'] >= 100)
        self.assertEqual(timing['slow'][0]['after'], 'main')
        self.assertFalse(replies[5]['ok'])                # (already off)

    def test_it_listens_on_this_machine_only(self):
        port = free_port()
        channel = self.module.TestChannel(port, Path(self.temporary.name))
        self.addCleanup(channel.server.close)
        self.assertEqual(channel.server.getsockname()[0], '127.0.0.1')


if __name__ == '__main__':
    unittest.main()
