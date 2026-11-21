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

    def test_a_window_button_is_found_by_its_label_before_its_position(self):
        # iPad, 2026-11-19: the sound prompt labels its buttons by string id ('25' No, '24' Yes); `window 24` was taken
        # as a position and found nothing.
        no, yes = SimpleNamespace(label='25'), SimpleNamespace(label='24')
        pressed = []
        shell = SimpleNamespace(stack=SimpleNamespace(stack=[1], current='prompt', press=pressed.append),
                                data=SimpleNamespace(menu=lambda key: SimpleNamespace(title='5', message='65535'),
                                                     items=lambda key: [no, yes]))
        channel = self.module.Commands(None, SimpleNamespace(shell=shell))
        with mock.patch.object(channel, '_idle', return_value=dict(ok=True)):
            for wanted in ('24', '0', 'yes', '25', '1'):
                self.assertTrue(channel.do_window(wanted)['ok'], wanted)
            self.assertFalse(channel.do_window('7')['ok'])
            self.assertFalse(channel.do_window('maybe')['ok'])
        self.assertEqual(pressed, [yes, no, yes, no, yes])

    def test_a_games_window_reads_as_its_words_and_is_answered_by_them(self):
        """Test channel wish, 2026-11-20: a game's own window gave string ids ('5', '25' / '24')."""
        no, yes = SimpleNamespace(label='25'), SimpleNamespace(label='24')
        words = {'5': 'Play with sound?', '25': 'No', '24': 'Yes'}
        pressed = []
        windows = SimpleNamespace(text_for=lambda key, variables: words.get(str(key), ''),
                                  item_label=lambda action, variables: words[action.label])
        shell = SimpleNamespace(stack=SimpleNamespace(stack=[1], current='prompt', press=pressed.append),
                                data=SimpleNamespace(menu=lambda key: SimpleNamespace(title='5', message=0xffff),
                                                     items=lambda key: [no, yes]),
                                windows=windows, variables=lambda: {})
        channel = self.module.Commands(None, SimpleNamespace(shell=shell))
        self.assertEqual(channel._window_words(channel._window()),
                         dict(title='Play with sound?', text='', buttons=['No', 'Yes'], ids=['25', '24']))
        with mock.patch.object(channel, '_idle', return_value=dict(ok=True)):
            self.assertTrue(channel.do_window('no')['ok'])
            self.assertTrue(channel.do_window('Yes')['ok'])
            self.assertIn("['No', 'Yes']", channel.do_window('maybe')['error'])
        self.assertEqual(pressed, [no, yes])

    @staticmethod
    def finish(job):
        """A command's reply: a job (a generator) run to its end, as the channel runs it a frame at a time."""
        if not hasattr(job, '__next__'):
            return job
        try:
            while True:
                next(job)
        except StopIteration as stop:
            return stop.value

    @staticmethod
    def settled(seconds=0.5):
        yield
        return dict(ok=True)

    def menu_channel(self, screen):
        """A channel over a main menu whose Options show `screen`, with a page of each kind of row."""
        activated = []
        rows = {'extras': [('switch', 'Allow Undo', 'undo'), ('choice', 'DSi Backgrounds', 'dsi_backgrounds'),
                           ('action', 'Unlock Warping', 'unlock_warp')],
                'choice:start_in': [('pick', 'Choose a Game', ('start_in', 'games'))]}
        pause = SimpleNamespace(state=SimpleNamespace(screen=screen), row_pages={}, strings=lambda: {},
                                option_rows=lambda category, settings, strings: rows.get(category, []),
                                open=lambda page: setattr(pause.state, 'screen', page))
        shell = SimpleNamespace(pause=pause, pause_open=True, activate=activated.append,
                                settings=lambda: dict(undo=True, dsi_backgrounds='Off', start_in='Choose a Game'))
        app = SimpleNamespace(shell=shell, library=object(), screen='main', show=lambda *a, **k: None)
        return self.module.Commands(None, app), activated

    def test_rows_and_press_drive_the_options_pages_by_label(self):
        """Owner, 2026-11-21: the Options pages by name and label, without a screenshot and a tap."""
        channel, activated = self.menu_channel('options:extras')
        listed = channel.do_rows('')
        self.assertEqual([(r['label'], r['kind'], r.get('value')) for r in listed['rows']],
                         [('Allow Undo', 'switch', True), ('DSi Backgrounds', 'choice', 'Off'), ('Unlock Warping', 'action', None)])
        with mock.patch.object(channel, '_settled', self.settled):
            for label in ('allow undo', 'DSi Backgrounds', 'unlock_warp'):
                self.assertEqual(self.finish(channel.do_press(label))['ok'], True)
            self.assertIn('no row', self.finish(channel.do_press('Nothing Here'))['error'])
        self.assertEqual(activated, [('pause_toggle', 'undo'), ('pause_open', 'choice:dsi_backgrounds'),
                                     ('pause_action', 'unlock_warp')])
        channel.app.shell.pause.state.screen = 'choice:start_in'
        self.assertEqual(channel.do_rows('')['rows'], [dict(label='Choose a Game', kind='pick', key=['start_in', 'games'],
                                                           value=True)])

    def test_in_a_story_rows_and_press_drive_its_pause_menu(self):
        """The story's pause menu (Desktop.pause_hd): its own rows, and its rows' commands sent through the story."""
        sent = []
        strings = {20: 'Resume', 10: 'Options', 120: 'Help & About', 9: 'Main Menu'}
        pause = SimpleNamespace(state=SimpleNamespace(screen='pause'), row_pages={}, strings=lambda: strings,
                                option_rows=lambda category, settings, strings: [])
        game = SimpleNamespace(menu_open=True, pause_hd=pause, command=sent.append,
                               _pause_settings=lambda: dict(undo_row=True, skip_ahead_row=True))
        channel = self.module.Commands(None, SimpleNamespace(screen='game', game=game, shell=None))
        self.assertEqual([r['label'] for r in channel.do_rows('')['rows']],
                         ['Resume', 'Skip Ahead', 'Undo', 'Options', 'Help & About', 'Main Menu'])
        with mock.patch.object(channel, '_settled', self.settled):
            self.assertTrue(self.finish(channel.do_press('undo'))['ok'])
        self.assertEqual(sent, [('undo',)])
        game.menu_open = False
        self.assertIn('pause menu is not open', str(self.raises(lambda: channel.do_rows(''))))

    @staticmethod
    def raises(call):
        try:
            call()
        except ValueError as error:
            return error
        return None

    def test_options_opens_a_page_by_its_short_name(self):
        channel, _ = self.menu_channel('options')
        with mock.patch.object(channel, '_settled', self.settled):
            self.assertEqual(self.finish(channel.do_options('episodes'))['page'], 'data:episodes')

    def test_pick_and_act_work_the_tick_lists(self):
        from exp_runtime.desktop_episode_list_hd import CHOICE_ACT, EpisodeChoice
        choosing = EpisodeChoice('Mark as Finished', 'Save', {'aaaaaaaa1', 'bbbbbbbb2'}, act_when_empty=True)
        commands = []
        app = SimpleNamespace(picker=SimpleNamespace(choosing=choosing), picker_command=commands.append,
                              library=SimpleNamespace(episodes=[dict(id='aaaaaaaa1', titles=['Easter Egg Hunt']),
                                                                dict(id='bbbbbbbb2', titles=['Football Star']),
                                                                dict(id='cccccccc3', titles=['Not Listed'])]))
        channel = self.module.Commands(None, app)
        self.assertEqual(channel.do_pick('easter')['ticked'], True)
        self.assertEqual(channel.do_pick('aaaaaaaa')['ticked'], False)
        self.assertFalse(channel.do_pick('not listed')['ok'])
        with mock.patch.object(channel, '_settled', lambda seconds=0.5: dict(ok=True)):
            self.assertTrue(channel.do_act('')['ok'])
        self.assertEqual(commands, [CHOICE_ACT])

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
            broken = data / 'dev-modules' / 'exp_runtime' / 'broken_mod.py'
            broken.write_text("text = '" + chr(10) + "'" + chr(10), encoding='utf-8')     # an unterminated string
            self.assertTrue(launcher.install_dev_modules())
            self.assertEqual(sys.path[0], str(data / 'dev-modules'))
            self.assertFalse(broken.exists())                       # set aside, so the app's own module loads
            self.assertTrue(broken.with_name('broken_mod.py.broken').exists())
            self.assertTrue((data / 'dev-modules' / 'exp_runtime' / 'probe_mod.py').exists())
        logging.getLogger('probe').warning('a line for the log')
        self.assertIn('WARNING probe: a line for the log', commands.do_log('5')['lines'])

    def test_a_dev_module_replaces_one_the_app_already_imported(self):
        """A copy in dev-modules of a module imported before install_dev_modules ran (games.py's profiles) is loaded again
        from the copy (2026-11-15: the iPad kept its own SHS profile)."""
        import importlib
        import sys
        from exp_runtime import launcher
        data = Path(self.temporary.name)
        app = data / 'app'
        (app / 'exp_runtime').mkdir(parents=True)
        (app / 'exp_runtime' / 'probe_early.py').write_text('X = 1' + chr(10), encoding='utf-8')
        before = list(sys.path)
        self.addCleanup(lambda: sys.path.__setitem__(slice(None), before))
        self.addCleanup(lambda: sys.modules.pop('exp_runtime.probe_early', None))
        sys.path.append(str(app))
        importlib.invalidate_caches()
        early = importlib.import_module('exp_runtime.probe_early')
        self.assertEqual(early.X, 1)
        copy = data / 'dev-modules' / 'exp_runtime' / 'probe_early.py'
        copy.parent.mkdir(parents=True)
        copy.write_text('X = 2' + chr(10), encoding='utf-8')
        (data / 'settings.json').write_text(json.dumps(dict(version=1, check_for_updates=False, test_channel=free_port())),
                                            encoding='utf-8')
        with mock.patch.object(launcher, 'user_data_directory', lambda: data):
            self.assertTrue(launcher.install_dev_modules())
        self.assertIs(sys.modules['exp_runtime.probe_early'], early)        # the same module object, as GAMES holds it
        self.assertEqual(early.X, 2)

    def test_a_silent_app_thread_has_its_stacks_written(self):
        shots = Path(self.temporary.name) / 'test-shots'
        shots.mkdir()
        with mock.patch.object(self.module, 'HANG_S', 0.3):
            channel = self.module.TestChannel(free_port(), shots)
            self.addCleanup(channel.server.close)
            channel.last -= 10                                      # no poll for a while
            for _ in range(50):
                if (shots / 'hang-stacks.txt').exists():
                    break
                time.sleep(0.05)
        text = (shots / 'hang-stacks.txt').read_text(encoding='utf-8')
        self.assertIn('--- MainThread', text)
        self.assertIn('test_a_silent_app_thread_has_its_stacks_written', text)

    def test_library_commands_name_one_record_and_delete_as_data_management(self):
        """`episodes`/`addons` list; `delete` and `delete-addon` take one id prefix (6+) or title, run Data Management's
        own work, and refuse a story on screen (roadmap 3.22, 2026-11-18)."""
        channel = self.module.TestChannel(free_port(), Path(self.temporary.name))
        self.addCleanup(channel.server.close)
        records = [dict(id='aaaaaa111111', titles=['Dating Beth'], file='x.exp', pack_id=31400),
                   dict(id='bbbbbb222222', titles=['Dating Beth Again'], file='y.exp'),
                   dict(id='cccccc333333', titles=['Football Star'], builtin=True)]
        addons = [dict(id='dddddd444444', addon='shs11', title="Surviving High School '11", revision=3)]
        removed = []
        library = SimpleNamespace(episodes=records, addons=addons,
                                  remove_addons=lambda ids: removed.extend(ids) or len(ids))
        playing = SimpleNamespace(session=SimpleNamespace(resources=SimpleNamespace(record=records[1])))
        app = SimpleNamespace(screen='game', library=library, busy=False, saved={'bbbbbb222222'}, game=playing, picker=1,
                              refresh_saves=lambda: None, addon_deleted=lambda: removed.append('deleted'))

        def data_job(title, work, done):
            app.job_done = lambda: done(work(library))
        app.start_data_job = data_job
        app.delete_episodes = lambda lib, ids: removed.extend(ids) or ('Episodes Deleted', 'done')
        commands = self.module.Commands(channel, app)

        def finish(job):
            if not hasattr(job, '__next__'):
                return job
            try:
                next(job)
                app.job_done()                              # (the work's result back on the app's thread)
                while True:
                    next(job)
            except StopIteration as stop:
                return stop.value
        listed = commands.do_episodes('beth')
        self.assertEqual([row['saved'] for row in listed['episodes']], [False, True])
        self.assertEqual(commands.do_addons('')['addons'][0]['name'], 'shs11')
        with self.assertRaises(ValueError):
            finish(commands.do_delete('Beth'))              # (two match: an exact title or an id is needed)
        self.assertFalse(finish(commands.do_delete('Football Star'))['ok'])           # built in
        self.assertIn('open', finish(commands.do_delete('Dating Beth Again'))['error'])  # on screen
        app.screen = 'main'                                  # held for Resume behind the menu: let go, then deleted
        reply = finish(commands.do_delete('bbbbbb'))
        self.assertEqual((reply['ok'], reply['deleted'], app.game, app.picker), (True, 'bbbbbb222222', None, None))
        reply = finish(commands.do_delete('Dating Beth'))  # (an exact title wins over one containing it)
        self.assertEqual(reply['deleted'], 'aaaaaa111111')
        reply = finish(commands.do_delete_addon('shs11'))
        self.assertTrue(reply['ok'])
        self.assertEqual(removed, ['bbbbbb222222', 'aaaaaa111111', 'dddddd444444', 'deleted'])

    def test_timing_groups_and_memory(self):
        channel = self.module.TestChannel(free_port(), Path(self.temporary.name))
        self.addCleanup(channel.server.close)
        engine = SimpleNamespace(sound_serial=0)
        game = SimpleNamespace(session=SimpleNamespace(engine=engine, pending=SimpleNamespace(name='dialogue')),
                               menu_open=False, host_prompt=None)
        app = SimpleNamespace(screen='game', game=game)
        commands = self.module.Commands(channel, app)
        commands.do_timing('on')
        for frame in range(6):
            if frame == 3:
                engine.sound_serial += 1                    # a sound starts in this frame
            channel.poll(app)
        reply = commands.do_timing('off groups')
        groups = {(group['showed'], group['sound']): group['frames'] for group in reply['groups']}
        self.assertEqual(groups, {('dialogue', False): 5, ('dialogue', True): 1})
        memory = commands.do_memory('')
        self.assertTrue(memory['ok'])
        if os.name == 'nt' or Path('/proc/self/status').exists():
            self.assertGreater(memory['resident_mb'], 1)

    def test_it_listens_on_this_machine_only(self):
        port = free_port()
        channel = self.module.TestChannel(port, Path(self.temporary.name))
        self.addCleanup(channel.server.close)
        self.assertEqual(channel.server.getsockname()[0], '127.0.0.1')


if __name__ == '__main__':
    unittest.main()
