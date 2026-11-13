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
        self.assertEqual((replies[0]['ok'], replies[0]['screen']), (True, 'main'))
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

    def test_the_hidden_settings_key_switches_it_on_and_is_kept(self):
        """iOS gets no environment from a launch: settings.json's hidden `test_channel` names the port instead, and the
        app's own writes keep it."""
        port = free_port()
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('SHSHD_TEST_CHANNEL', None)
            channel = self.module.from_environment(self.temporary.name, port)
        self.addCleanup(channel.server.close)
        self.assertEqual(channel.server.getsockname()[1], port)
        from exp_runtime.settings import AppSettings
        path = Path(self.temporary.name) / 'settings.json'
        path.write_text(json.dumps(dict(version=1, check_for_updates=False, test_channel=port)), encoding='utf-8')
        settings = AppSettings(path)
        self.assertEqual(settings.test_channel, port)
        settings.set_start_in('shs')
        self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['test_channel'], port)
        path.write_text(json.dumps(dict(version=1, check_for_updates=False, test_channel='47920')), encoding='utf-8')
        self.assertIsNone(AppSettings(path).test_channel)            # (a port, as a number)

    def test_files_log_and_dev_modules(self):
        """`put`/`get`/`files` stay in the app's data folder; `log` keeps the app's lines; with the key set,
        dev-modules goes first on the module path (launcher.install_dev_modules)."""
        import base64
        import logging
        import sys
        from exp_runtime import launcher
        port = free_port()
        channel = self.module.TestChannel(port, Path(self.temporary.name) / 'test-shots')
        self.addCleanup(channel.server.close)
        data = Path(self.temporary.name)
        with mock.patch.object(launcher, 'user_data_directory', lambda: data):
            commands = self.module.Commands(channel, SimpleNamespace(screen='games'))
            put = commands.do_put('dev-modules/exp_runtime/probe_mod.py ' + base64.b64encode(b'X = 1' + bytes([10])).decode())
            self.assertTrue(put['ok'])
            self.assertEqual(base64.b64decode(commands.do_get('dev-modules/exp_runtime/probe_mod.py')['data']), b'X = 1' + bytes([10]))
            self.assertIn('dev-modules', [entry['name'] for entry in commands.do_files('')['entries']])
            with self.assertRaises(ValueError):
                commands.do_get('../outside.txt')
            self.assertFalse(launcher.install_dev_modules())         # (no settings key: nothing)
            (data / 'settings.json').write_text(json.dumps(dict(version=1, check_for_updates=False, test_channel=port)),
                                                encoding='utf-8')
            before = list(sys.path)
            self.addCleanup(lambda: sys.path.__setitem__(slice(None), before))
            self.assertTrue(launcher.install_dev_modules())
            self.assertEqual(sys.path[0], str(data / 'dev-modules'))
        logging.getLogger('probe').warning('a line for the log')
        self.assertIn('WARNING probe: a line for the log', commands.do_log('5')['lines'])

    def test_it_listens_on_this_machine_only(self):
        port = free_port()
        channel = self.module.TestChannel(port, Path(self.temporary.name))
        self.addCleanup(channel.server.close)
        self.assertEqual(channel.server.getsockname()[0], '127.0.0.1')


if __name__ == '__main__':
    unittest.main()
