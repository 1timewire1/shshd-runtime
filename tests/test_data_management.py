"""Data Management (owner, 2026-10-29): its pages, this player's own confirmation windows, and the actions behind them."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


class CustomWindowTests(unittest.TestCase):
    def test_a_window_of_this_players_own_carries_its_text_and_its_buttons_steps(self):
        from exp_runtime.menu_engine import (BACK, CUSTOM_MENUS, ENGINE, MenuEngineData, MenuEngineError,
                                             MenuStack, STYLE_ALERT)
        data = MenuEngineData.__new__(MenuEngineData)
        data.menus, data._actions, data.custom = (), {}, {}
        data.add_window(CUSTOM_MENUS, 'Delete All Saves?', 'Every saved game...', (('No', ((BACK, 0),)),
                                                                                  ('Delete', ((ENGINE, 1000),))))
        menu = data.menu(CUSTOM_MENUS)
        self.assertEqual((menu.title, menu.message, menu.style), ('Delete All Saves?', 'Every saved game...', STYLE_ALERT))
        no, delete = data.items(CUSTOM_MENUS)
        self.assertEqual((no.label, delete.label, delete.steps), ('No', 'Delete', ((ENGINE, 1000),)))
        with self.assertRaises(MenuEngineError):
            data.add_window(5, 'x', 'y', ())                               # a game's own ids are not this player's
        performed = []
        stack = MenuStack(data, performed.append)
        stack.queue(CUSTOM_MENUS)
        stack.press(no)
        self.assertEqual(stack.stack, [])                                  # No steps back
        stack.queue(CUSTOM_MENUS)
        stack.press(delete)
        self.assertEqual(performed, [1000])                                # the verb's action goes to the host
        from exp_runtime.desktop_hd_menu import HdMenuWindows
        windows = HdMenuWindows.__new__(HdMenuWindows)
        self.assertEqual(windows.text_for('Reset Names?'), 'Reset Names?')  # text, not a string id

    def test_a_confirmations_yes_runs_its_action_then_shows_what_it_did(self):
        from exp_runtime.application_hd import HdShell
        shell = HdShell.__new__(HdShell)
        shell.data = Mock()
        shell.stack = Mock(stack=[])
        shell.app = SimpleNamespace(_attempt=lambda operation: operation(), state=None)
        notices = []
        shell.notify = lambda title, message: notices.append((title, message))
        shell.confirm('Delete All Saves?', 'Every saved game...', 'Delete', lambda: shell.notify('Saves Deleted', '3'))
        shell.stack.queue.assert_called_once_with(HdShell.CONFIRM_MENU)
        shell.perform(HdShell.CONFIRM_ACTION)
        self.assertEqual(notices, [('Saves Deleted', '3')])
        self.assertIsNone(shell.confirmed)


class LibraryActionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def app(self):
        from exp_runtime.application import Application
        from exp_runtime.menu import MenuState
        directory = self.root / 'shs'
        (directory / 'saves').mkdir(parents=True)
        for name in ('a.shs-auto.json', 'a.shs-shot.jpg', 'b.shs-save.json', 'b.shs-auto.json'):
            (directory / 'saves' / name).write_text('{}')
        (directory / 'dtsaves' / 'k').mkdir(parents=True)
        (directory / 'dtsaves' / '1.json.gz').write_bytes(b'')
        (directory / 'dtview').mkdir()
        (directory / 'dtview' / 'k.json').write_text('{}')
        (directory / 'dtview_tree.json').write_text('{}')
        library = SimpleNamespace(directory=directory, episodes=[{'id': 'a'}, {'id': 'b'}],
                                  select=lambda key: {'id': key})
        (directory / 'player.json').write_text(json.dumps(dict(version=1, music=True, sound=True, selected='a',
                                                               names={'$USR': 'Zoe'})))
        app = Application.__new__(Application)
        app.library, app.game, app.shot_cache, app.selected_game = library, None, {'a': object()}, 'shs'
        app.state = MenuState(library)
        app.state.resume_path = lambda episode: (directory / 'saves' / f'{episode}.shs-auto.json'
                                                 if (directory / 'saves' / f'{episode}.shs-auto.json').exists() else None)
        app.picker = object()
        return app

    def test_delete_save_takes_one_episodes_saves_and_picture_and_leaves_its_tree(self):
        app = self.app()
        app.delete_save('a')
        folder = app.library.directory / 'saves'
        self.assertEqual(sorted(path.name for path in folder.iterdir()), ['b.shs-auto.json', 'b.shs-save.json'])
        self.assertEqual(app.saved, {'b'})
        self.assertNotIn('a', app.shot_cache)
        self.assertTrue((app.library.directory / 'dtview_tree.json').exists())

    def test_delete_all_saves_takes_every_save_and_every_tree(self):
        app = self.app()
        title, message = app.delete_all_saves()
        directory = app.library.directory
        self.assertEqual(title, 'Saves Deleted')
        self.assertIn('2 saved games', message)
        for name in ('saves', 'dtsaves', 'dtview', 'dtview_tree.json'):
            self.assertFalse((directory / name).exists(), name)
        self.assertEqual((app.saved, app.picker, app.shot_cache), (set(), None, {}))
        self.assertEqual(json.loads((directory / 'player.json').read_text())['names'], {'$USR': 'Zoe'})

    def test_reset_names_empties_the_tables(self):
        app = self.app()
        app.state.name_sets['nr'] = {'$Emily': 'Em'}
        app.reset_names()
        data = json.loads((app.library.directory / 'player.json').read_text())
        self.assertEqual((data['names'], data['name_sets']), ({}, {}))

    def test_reset_settings_puts_every_shared_option_back_and_keeps_the_games_own_data(self):
        from exp_runtime.menu import preference_defaults
        from exp_runtime.settings import AppSettings
        app = self.app()
        app.settings = AppSettings(self.root / 'settings.json')
        app.state.shared = app.settings
        app.settings.set_start_in('cod')
        app.settings.set_update_check(False)
        app.state.autoplay, app.state.music_volume, app.state.warp_unlocked = True, 10, True
        app.apply_hires_portraits = app.sync_controller = app.menu_music_changed = lambda *a, **k: None
        app.set_update_check = app.settings.set_update_check
        app.reset_settings()
        self.assertEqual({key: getattr(app.state, key) for key in preference_defaults()}, preference_defaults())
        self.assertTrue(app.state.warp_unlocked)                           # a game's own progress stays
        self.assertEqual((app.settings.start_in, app.settings.check_for_updates), ('auto', True))
        self.assertEqual(app.settings.preferences['music_volume'], 50)

    def test_library_info_breaks_the_folder_where_a_page_can_wrap_it(self):
        from exp_runtime.application import folder_lines
        lines = folder_lines(Path('C:/Users/someone/AppData/Local/SHSHD Runtime/libraries/shs'), width=20)
        self.assertTrue(all(len(line) <= 24 for line in lines))
        self.assertEqual(''.join(lines).replace('\\', '/'), 'C:/Users/someone/AppData/Local/SHSHD Runtime/libraries/shs')


if __name__ == '__main__':
    unittest.main()
