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

    def test_storage_counts_each_part_of_the_folder(self):
        app = self.app()
        directory = app.library.directory
        (directory / 'content').mkdir()
        (directory / 'content' / 'e.exp').write_bytes(b'x' * 3000)
        (directory / 'content' / 'g.apk').write_bytes(b'x' * 2_500_000)
        (directory / 'thumbs').mkdir()
        (directory / 'thumbs' / 'a.jpg').write_bytes(b'x' * 1500)
        lines = app.storage_text(app.library).split('\n')
        self.assertIn('Episodes: 3.0 KB', lines)
        self.assertIn('Game apps: 2.5 MB', lines)
        self.assertIn('Previews: 1.5 KB', lines)
        self.assertTrue(any(line.startswith('Total: 2.5 MB') for line in lines))
        self.assertTrue(any(line.startswith('Free on this drive: ') for line in lines))

    def test_verify_removes_a_damaged_episode_and_names_what_is_wrong(self):
        import hashlib
        app = self.app()
        directory = app.library.directory
        (directory / 'content').mkdir()
        good, bad = b'good episode', b'damaged episode'
        (directory / 'content' / 'good.exp').write_bytes(good)
        (directory / 'content' / 'bad.exp').write_bytes(bad)
        sha = lambda data: hashlib.sha256(data).hexdigest()
        app.library.manifest = {'apk': dict(file='content/game.apk', sha256=sha(b'app'))}   # missing
        app.library.episodes = [dict(id='g', titles=['Good'], file='content/good.exp', sha256=sha(good)),
                                dict(id='b', titles=['Bad'], file='content/bad.exp', sha256=sha(b'what it was'))]
        app.library.restore_builtin_episodes = lambda: 0
        checked, missing, damaged, restored = app.verify_library(app.library)
        self.assertEqual((checked, missing, damaged, restored), (3, ['The Android app'], ['Bad'], 0))
        self.assertFalse((directory / 'content' / 'bad.exp').exists())      # adding it again restores it
        self.assertTrue((directory / 'content' / 'good.exp').exists())
        app.shell = SimpleNamespace(pause=Mock(), notify=Mock())
        app.verify_report((checked, missing, damaged, restored))
        screen, title, body, parent = app.shell.pause.show_text.call_args.args
        self.assertEqual((screen, title, parent), ('data:verify', 'Verify Library', 'data:library'))
        self.assertIn('Damaged: Bad', body)
        self.assertIn('importing the game again', body)
        app.verify_report((3, [], [], 1))
        title, message = app.shell.notify.call_args.args
        self.assertEqual(title, 'Library Verified')
        self.assertIn('1 built-in episode was restored', message)

    def test_rebuild_previews_draws_every_preview_again(self):
        from unittest.mock import patch
        app = self.app()
        thumbs = app.library.directory / 'thumbs'
        thumbs.mkdir()
        (thumbs / 'a.jpg').write_bytes(b'old')
        (thumbs / 'b.none').write_bytes(b'4')
        with patch('exp_runtime.application.PickerModel', lambda library: SimpleNamespace(records=['a', 'b'])), \
                patch('exp_runtime.episode_thumbnails.ensure', lambda library, records, progress: len(records)):
            self.assertEqual(app.rebuild_previews(app.library), 2)
        self.assertFalse(thumbs.exists())

    def episode_app(self):
        """self.app() with three episode records: one imported, one built in, one inside the game's package."""
        app = self.app()
        app.library.episodes = [dict(id='a', sha256='a', titles=['A'], name='A.exp', file='content/a.exp'),
                                dict(id='f', sha256='f', titles=['Football Star'], name='Football_Star.exp',
                                     file='content/f.exp', builtin='football-star'),
                                dict(id='p', sha256='p', titles=['P'], name='P.exp', apk_member='assets/P.exp')]
        app.library.select = lambda key: next(r for r in app.library.episodes if r['id'] == key)
        return app

    def test_each_episode_list_offers_the_episodes_it_can_act_on(self):
        app = self.episode_app()
        directory = app.library.directory
        self.assertEqual(app.choice_allowed('delete_episodes'), {'a'})         # not built in, not in the package
        self.assertEqual(app.choice_allowed('export_episodes'), {'a', 'f', 'p'})
        self.assertEqual(app.choice_allowed('reset_trees'), {'f'})             # dtview_tree.json + dtsaves/1.json.gz
        (directory / 'dtview' / 'a.json').write_text('{}')
        self.assertEqual(app.choice_allowed('reset_trees'), {'a', 'f'})
        app.game = SimpleNamespace(session=SimpleNamespace(resources=SimpleNamespace(record={'id': 'a'})))
        self.assertEqual(app.choice_allowed('delete_episodes'), set())         # the one being played stays

    def test_reset_trees_clears_football_stars_tree_but_not_the_others_folders(self):
        app = self.episode_app()
        directory = app.library.directory
        title, message = app.reset_trees(app.library, {'f'})
        self.assertEqual(title, 'Trees Reset')
        self.assertFalse((directory / 'dtview_tree.json').exists())
        self.assertFalse((directory / 'dtsaves' / '1.json.gz').exists())
        self.assertTrue((directory / 'dtsaves' / 'k').is_dir())               # another episode's scenes
        (directory / 'dtsaves' / 'a').mkdir()
        (directory / 'dtview' / 'a.json').write_text('{}')
        app.reset_trees(app.library, {'a'})
        self.assertFalse((directory / 'dtsaves' / 'a').exists())
        self.assertFalse((directory / 'dtview' / 'a.json').exists())
        self.assertTrue((directory / 'dtsaves' / 'k').is_dir())

    def test_delete_episodes_takes_their_saves_previews_and_trees(self):
        app = self.episode_app()
        directory = app.library.directory
        (directory / 'thumbs').mkdir()
        (directory / 'thumbs' / 'a.jpg').write_bytes(b'')
        (directory / 'saves' / 'a.shs-save.json').write_text('{}')
        (directory / 'dtview' / 'a.json').write_text('{}')
        removed = []
        app.library.remove_episodes = lambda ids: removed.extend(ids) or len(ids)
        title, message = app.delete_episodes(app.library, {'a'})
        self.assertEqual((title, removed), ('Episodes Deleted', ['a']))
        self.assertEqual(sorted(p.name for p in (directory / 'saves').iterdir()), ['b.shs-auto.json', 'b.shs-save.json'])
        self.assertFalse((directory / 'thumbs' / 'a.jpg').exists())
        self.assertFalse((directory / 'dtview' / 'a.json').exists())
        self.assertTrue((directory / 'dtview_tree.json').exists())             # Football Star's tree stays

    def test_export_copies_each_file_under_its_own_name_without_overwriting_another(self):
        app = self.episode_app()
        folder = self.root / 'exports'
        app.export_folder = lambda library=None: folder
        app.library.episode_bytes = lambda record: record['id'].encode()
        folder.mkdir()
        (folder / 'A.exp').write_bytes(b'someone else')
        title, message = app.export_episodes(app.library, {'a', 'p'})
        self.assertEqual(title, 'Episodes Exported')
        self.assertEqual({p.name: p.read_bytes() for p in folder.iterdir()},
                         {'A.exp': b'someone else', 'A (2).exp': b'a', 'P.exp': b'p'})
        app.export_episodes(app.library, {'a'})                                # the same file again: no third copy
        self.assertEqual(len(list(folder.iterdir())), 3)

    def test_back_up_then_restore_brings_back_the_saves_and_names_and_keeps_the_newer_progress(self):
        app = self.episode_app()
        app.library.game_id = 'shs'
        app.backup_folder = lambda: self.root / 'backups'
        app.shell = SimpleNamespace(notify=Mock(), pause=Mock())
        directory = app.library.directory
        app.state.names['$USR'] = 'Zoe'
        path, manifest = app.back_up_progress(app.library, app.player_data())
        self.assertEqual([entry['id'] for entry in manifest['saved']], ['a', 'b'])
        app.backed_up((path, manifest))
        self.assertIn('2 saved games', app.shell.notify.call_args.args[1])
        # Newer progress: a save deleted, a name changed.
        app.delete_save('a')
        app.state.names['$USR'] = 'Max'
        app.show_backups()
        screen, title, rows, parent = app.shell.pause.show_rows.call_args.args
        self.assertEqual((screen, title, parent, len(rows)), ('data:restore', 'Restore Progress', 'data:progress', 1))
        self.assertTrue(rows[0][1].endswith(': 2 saves'))
        result = app._restore(app.library, app.backup_choices[rows[0][0]], app.player_data())
        app.progress_restored(result)
        self.assertTrue((directory / 'saves' / 'a.shs-auto.json').exists())
        self.assertEqual(app.state.names['$USR'], 'Zoe')
        self.assertEqual(json.loads((directory / 'player.json').read_text())['names'], {'$USR': 'Zoe'})
        self.assertEqual(app.saved, {'a'})                                   # of this library's episodes
        self.assertIn('1 more wait', app.shell.notify.call_args.args[1])     # 'b' is no episode of this library
        labels = [app.backup_label(m) for _, m in app.backups()]
        self.assertEqual(len(labels), 2)
        self.assertTrue(labels[0].endswith('(before restore)'))              # the newer progress, kept

    def test_a_chosen_folder_takes_backups_and_exports_and_restore_still_finds_the_default_ones(self):
        from exp_runtime.settings import AppSettings
        app = self.episode_app()
        app.library.game_id = 'shs'
        app.settings = AppSettings(self.root / 'settings.json')
        default = self.root / 'downloads'
        app.user_folder = lambda name: default / f'SHSHD Runtime {name}'
        self.assertEqual(app.backup_folder(), default / 'SHSHD Runtime Backups')
        self.assertEqual(app.export_folder(), default / 'SHSHD Runtime Episodes' / 'Surviving High School')
        old, _ = app.back_up_progress(app.library, app.player_data())
        chosen = self.root / 'My Backups'
        chosen.mkdir()
        app.browser_kind = 'backups'
        app.shell = SimpleNamespace(notify=Mock(), activate=Mock(), pause=Mock())
        app.show = Mock()
        app.use_folder(chosen)
        self.assertEqual(AppSettings(self.root / 'settings.json').backup_folder, str(chosen))    # kept
        app.shell.pause.open.assert_called_once_with('data:progress')
        self.assertIn('My Backups', app.shell.notify.call_args.args[1])
        new, _ = app.back_up_progress(app.library, app.player_data())
        self.assertEqual(new.parent, chosen)
        self.assertEqual({path for path, _ in app.backups()}, {old, new})
        self.assertEqual(app.folder_label('backup_folder'), 'My Backups')
        app.settings.set_folder('export_folder', self.root / 'Exports')
        self.assertEqual(app.export_folder(), self.root / 'Exports')
        app.browser_kind = 'exports'
        app.use_folder(None)                                                  # the browser's Default button
        self.assertIsNone(app.settings.export_folder)
        self.assertIn('SHSHD Runtime Episodes', app.shell.notify.call_args.args[1])
        app.settings.set_folder('export_folder', self.root / 'Exports')
        app.state.shared = app.settings
        app.apply_hires_portraits = app.sync_controller = app.menu_music_changed = lambda *a, **k: None
        app.set_update_check = app.settings.set_update_check
        app.reset_settings()
        self.assertEqual((app.settings.backup_folder, app.settings.export_folder), (None, None))
        self.assertEqual(app.backup_folder(), default / 'SHSHD Runtime Backups')

    def test_deleting_a_library_takes_only_its_own_parts(self):
        from exp_runtime.application import remove_library
        app = self.app()
        directory = app.library.directory
        for name in ('content', 'thumbs', 'hd_twins', 'fonts', '.sync-abc'):
            (directory / name).mkdir()
            (directory / name / 'x').write_bytes(b'x')
        (directory / 'library.json').write_text('{}')
        self.assertEqual(remove_library(directory), 0)
        self.assertFalse(directory.exists())                                   # nothing else was there
        app = self.app()
        directory = app.library.directory
        (directory / 'library.json').write_text('{}')
        (directory / 'my notes.txt').write_text('mine')                       # the player's own file
        remove_library(directory)
        self.assertEqual([p.name for p in directory.iterdir()], ['my notes.txt'])

    def test_actions_on_another_library_leave_the_open_ones_menus_alone(self):
        from exp_runtime.menu import MenuState
        app = self.app()
        picker = app.picker
        other_dir = self.root / 'cod'
        (other_dir / 'saves').mkdir(parents=True)
        (other_dir / 'saves' / 'x.shs-auto.json').write_text('{}')
        (other_dir / 'player.json').write_text(json.dumps(dict(version=1, names={'$USR': 'Ana'})))
        other = SimpleNamespace(directory=other_dir, episodes=[{'id': 'x'}], game_id='cod',
                                select=lambda key: {'id': key})
        state = MenuState(other)
        title, message = app.delete_all_saves(other, state)
        self.assertEqual(title, 'Saves Deleted')
        self.assertIn('1 saved game of Cause of Death', message)
        self.assertFalse((other_dir / 'saves').exists())
        self.assertTrue((app.library.directory / 'saves').exists())          # the open library's saves stay
        self.assertIs(app.picker, picker)
        self.assertEqual(app.reset_names(state), ('Names Reset', 'Cause of Death will ask for the names again.'))
        self.assertEqual(json.loads((other_dir / 'player.json').read_text())['names'], {})
        self.assertEqual(app.state.names, {'$USR': 'Zoe'})                  # the open library's names stay

    def test_library_info_breaks_the_folder_where_a_page_can_wrap_it(self):
        from exp_runtime.application import folder_lines
        lines = folder_lines(Path('C:/Users/someone/AppData/Local/SHSHD Runtime/libraries/shs'), width=20)
        self.assertTrue(all(len(line) <= 24 for line in lines))
        self.assertEqual(''.join(lines).replace('\\', '/'), 'C:/Users/someone/AppData/Local/SHSHD Runtime/libraries/shs')


if __name__ == '__main__':
    unittest.main()
