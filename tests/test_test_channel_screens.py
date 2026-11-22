"""shshd-runtime: the test channel sees and drives every screen a player can reach (owner, 2026-11-21): the windows over a
story and over the app, Help's pages, the episode picker, the side panels and Decision Tree, the Faceplace wall, the
chooser's lists and the screens outside the HD menus."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

HAS_PYGAME = importlib.util.find_spec('pygame') is not None


def finish(job):
    """A command's reply: a job (a generator) run to its end, as the channel runs it a frame at a time."""
    if not hasattr(job, '__next__'):
        return job
    try:
        while True:
            next(job)
    except StopIteration as stop:
        return stop.value


def settled(seconds=0.5):
    yield
    return dict(ok=True)


@unittest.skipUnless(HAS_PYGAME, 'the desktop extra is unavailable')
class ChannelScreenTests(unittest.TestCase):
    def setUp(self):
        from exp_runtime import test_channel
        self.module = test_channel

    def channel(self, **app):
        values = dict(screen='main', shell=None, message='', busy=False, game=None, library=None, picker=None)
        values.update(app)
        channel = self.module.Commands(None, SimpleNamespace(**values))
        for name in ('_settled', '_idle'):
            setattr(channel, name, settled)
        return channel

    # -- windows -------------------------------------------------------------------------------------------------------
    def test_the_apps_message_and_update_prompt_are_windows(self):
        sent = []
        channel = self.channel(message='Added 3 episodes.', game_title='Surviving High School', command=sent.append)
        window = channel._window_words(channel._window())
        self.assertEqual((window['source'], window['text'], window['buttons']), ('message', 'Added 3 episodes.', ['OK']))
        self.assertTrue(finish(channel.do_window('ok'))['ok'])
        channel.app.message = ''
        channel.app.update_prompt, channel.app.can_quit = SimpleNamespace(version='9.9.9'), True
        self.assertEqual(channel._window().buttons, ['No', 'Yes'])
        finish(channel.do_window('yes'))
        finish(channel.do_window('no'))
        self.assertEqual(sent, [('dismiss',), ('update_yes',), ('update_no',)])
        channel.app.busy = True                             # (the busy card is over everything: no window to press)
        self.assertIsNone(channel._window())

    def test_a_storys_own_notice_is_a_window(self):
        """The wall's "Exit Game?" and the tree's "Locked" (Desktop.notice_stack) were invisible to `state`."""
        no, yes = SimpleNamespace(label=25), SimpleNamespace(label=24)
        pressed = []
        words = {5: 'Exit Game?', 6: 'Proceed?', 25: 'No', 24: 'Yes'}
        windows = SimpleNamespace(text_for=lambda key, variables=None: words[key],
                                  item_label=lambda action, variables: words[action.label], items=lambda menu: [no, yes])
        stack = SimpleNamespace(stack=[17], current=17, press=pressed.append)
        game = SimpleNamespace(notice_stack=stack, notice_windows=windows,
                               notice_data=SimpleNamespace(menu=lambda key: SimpleNamespace(title=5, message=6)))
        channel = self.channel(screen='game', game=game)
        self.assertEqual(channel._window_words(channel._window()),
                         dict(source='story', title='Exit Game?', text='Proceed?', buttons=['No', 'Yes'], ids=['25', '24']))
        finish(channel.do_window('no'))
        self.assertEqual(pressed, [no])

    def test_the_choosers_question_and_the_pickers_alert_are_windows(self):
        done = []
        options = SimpleNamespace(ask=('Reset Settings?', 'Every option...', ('No', 'Reset'), (None, lambda: done.append(1))),
                                  menu=None)
        channel = self.channel(screen='options', app_options_open=lambda: True,
                               app_screens=SimpleNamespace(options=options))
        self.assertEqual(channel._window().buttons, ['No', 'Reset'])
        finish(channel.do_window('reset'))
        self.assertEqual((done, options.ask), ([1], None))
        commands = []
        from exp_runtime.episode_picker import EpisodeInfo
        picker = SimpleNamespace(alert=EpisodeInfo('Football Star', 'Go long.', 'Airdate: 2010', None))
        channel = self.channel(screen='picker', picker=picker, picker_command=commands.append)
        self.assertEqual(channel._window().title, 'Football Star')
        finish(channel.do_window('ok'))
        self.assertEqual(commands, [('dismiss',)])

    # -- pages and lists -------------------------------------------------------------------------------------------------
    def test_help_lists_its_pages_and_a_text_page_reads_with_its_links(self):
        from exp_runtime.desktop_pause_hd import HELP_ORDER, HdPauseMenu
        strings = {i: f's{i}' for i in range(400)}
        pause = SimpleNamespace(state=SimpleNamespace(screen='help'), row_pages={}, main_menu=False, PAGES=HdPauseMenu.PAGES,
                                strings=lambda: strings, text_pages={},
                                text_lines=lambda page: ('About', 'By [someone](https://example.com/a).\nPlain.'))
        game = SimpleNamespace(menu_open=True, pause_hd=pause, command=None, _pause_settings=lambda: {})
        channel = self.channel(screen='game', game=game)
        self.assertEqual([r['key'] for r in channel.do_rows('')['rows']], list(HELP_ORDER))
        pause.state.screen = 'about'
        reply = channel.do_rows('')
        self.assertEqual((reply['title'], reply['rows']),
                         ('About', [dict(label='someone', kind='link', key='https://example.com/a')]))

    def test_the_choosers_tick_list_is_picked_and_acted_on(self):
        from exp_runtime.desktop_episode_list_hd import EpisodeChoice
        choosing = EpisodeChoice('Delete Episodes', 'Delete', {'aaaaaaaa1'})
        acted = []
        chooser = SimpleNamespace(picker=SimpleNamespace(choosing=choosing),
                                  library=SimpleNamespace(episodes=[dict(id='aaaaaaaa1', titles=['Easter Egg Hunt'])]))
        channel = self.channel(screen='choice', app_screens=SimpleNamespace(choice=chooser, choice_act=lambda: acted.append(1)))
        self.assertEqual(channel.do_ticks('')['episodes'], [dict(id='aaaaaaaa1', title='Easter Egg Hunt', ticked=False)])
        self.assertTrue(channel.do_pick('easter')['ticked'])
        self.assertTrue(finish(channel.do_act(''))['ok'])
        self.assertEqual(acted, [1])

    def test_the_episode_picker_taps_its_tiles_and_popup(self):
        record = dict(id='445a21be098c0000', titles=['Football Star'])
        row = SimpleNamespace(title='Mega Packs', episodes=(record,))
        model = SimpleNamespace(rows=[row], label=lambda r: r['titles'][0], has_info=lambda r: False)
        picker = SimpleNamespace(model=model, popup=None, alert=None, selected=None)
        commands = []
        channel = self.channel(screen='picker', picker=picker, picker_style='tile', saved={record['id']}, finished=set(),
                               picker_command=commands.append)
        listing = finish(channel.do_picker(''))
        self.assertEqual(listing['rows'][0]['episodes'][0],
                         dict(id='445a21be098c', title='Football Star', saved=True, finished=False, info=False))
        self.assertIn('no New Game', finish(channel.do_picker('continue'))['error'])
        finish(channel.do_picker('tile football'))
        picker.popup = record
        finish(channel.do_picker('continue'))
        picker.popup = None
        self.assertIn('has no info card', finish(channel.do_picker('info football'))['error'])
        self.assertEqual(commands, [('tile', record['id']), ('continue', record['id'])])

    def test_buttons_read_a_screen_outside_the_hd_menus(self):
        sent = []
        library = SimpleNamespace(episodes=[dict(id='4637c71a16ec', titles=['Football Star'])])
        channel = self.channel(screen='episodes', library=library, command=sent.append,
                               buttons=[(None, ('back',)), (None, ('episode', '4637c71a16ec')), (None, ('browse', 'episodes'))])
        self.assertEqual(channel.do_buttons('')['buttons'], ['back', 'episode Football Star [4637c71a]', 'browse episodes'])
        finish(channel.do_button('episode football'))
        self.assertIn('no button', finish(channel.do_button('nothing'))['error'])
        channel.app.screen, channel.app.files = 'browser', [Path('far/below.exp')]
        channel.app.folder, channel.app.browser_kind, channel.app.buttons = Path('far'), 'episodes', []
        finish(channel.do_button('file below.exp'))       # (scrolled out of view: still a file of the folder)
        self.assertEqual(sent, [('episode', '4637c71a16ec'), ('file', Path('far/below.exp'))])

    # -- the story's panels -----------------------------------------------------------------------------------------------
    def test_the_tree_warps_only_where_a_player_could_tap(self):
        from exp_runtime.dtview_faceplace import DTNode
        week, beth = DTNode(1203, 'Week 1', 0, serial=1), DTNode(1206, 'Meet Beth', 0, serial=2)
        week.active = beth.active = True
        week.children[0] = beth
        view = SimpleNamespace(nodes=lambda: [week, beth], current=beth, real_parent=lambda node: week,
                               real_child=lambda node: None)
        tapped = []
        session = SimpleNamespace(engine=SimpleNamespace(dt_view=view), has_tree_state=lambda node: True,
                                  transitioning=False)
        game = SimpleNamespace(session=session, panels_used=lambda: (True, False), _panels_ready=lambda: False,
                               notice_stack=None, warp_unlocked=True, _tree_target=tapped.append, fade=None, error=None)
        channel = self.channel(screen='game', game=game)
        listing = channel.do_tree('')
        self.assertEqual([(n['label'], n['current'], n['warp']) for n in listing['nodes']],
                         [('Week 1', False, True), ('Meet Beth', True, False)])
        self.assertEqual((listing['rewind'], listing['forward']), (1, None))
        with self.assertRaises(ValueError):
            channel.do_tree('rewind')                    # (the panels are closed: nothing to tap)
        game._panels_ready = lambda: True

        def act(do, check=None):
            do()
            yield
            return dict(ok=True)
        with mock.patch.object(channel, '_act', act):
            for words in ('warp week 1', 'warp 2', 'rewind'):
                self.assertTrue(finish(channel.do_tree(words))['ok'])
        self.assertEqual(tapped, [('node', week), ('node', beth), ('rewind',)])
        self.assertIn('no scene', channel.do_tree('warp Nowhere')['error'])


if __name__ == '__main__':
    unittest.main()
