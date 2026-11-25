"""LAN sync's app side (sync_flow.py, owner 2026-10-30): what a receiver keeps and how it words the result."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from exp_runtime.sync_flow import DEVICE_OPTIONS, ReceiveHost, SendProvider, SyncFlow


def app_with(directory, **state):
    state = SimpleNamespace(names={'$USR': 'Zoe', '$ZOE': 'Max'}, name_sets={'nr': {'$Emily': 'Em'}},
                            warp_unlocked=False, persist=Mock(), **state)
    library = SimpleNamespace(directory=Path(directory), game_id='shs', episodes=[
        dict(id='a', titles=['A'], name='A.exp', file='content/a.exp'),
        dict(id='f', titles=['Football Star'], file='content/f.exp', builtin='football-star'),
        dict(id='p', titles=['P'], apk_member='assets/P.exp')])
    return SimpleNamespace(state=state, library=library, apply_options=Mock(), shell=None,
                           games_with_libraries=lambda: ['shs'], library_path=lambda game: Path(directory) / game)


class SyncFlowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_a_new_sync_clears_the_stages_a_killed_one_left(self):
        """A receiver killed mid-transfer left its stage in the library (348 MB, 2026-11-24): the next sync clears it."""
        from exp_runtime.sync_flow import clear_stale_stages
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            for name in ('.sync-abc', '.sync-send-def'):
                (home / name / 'cod').mkdir(parents=True)
                (home / name / 'cod' / 'part.exp').write_bytes(b'half')
            (home / 'content').mkdir()
            (home / '.restore-xyz').mkdir()
            (home / 'library.json').write_text('{}')
            clear_stale_stages(home)
            self.assertEqual(sorted(p.name for p in home.iterdir()), ['.restore-xyz', 'content', 'library.json'])
            clear_stale_stages(home / 'missing')                         # (no folder yet: nothing to do)

    def test_received_names_win_and_the_receivers_others_stay_and_device_options_stay(self):
        app = app_with(self.root)
        flow = SyncFlow(app)
        flow.apply({'names': {'$USR': 'Sam'}, 'name_sets': {'nr': {'$Hector': 'H'}, 'x360': {'$Pat': 'P'}},
                    'warp_unlocked': True},
                   {'autoplay': True, 'vibration': True, 'controller_confirm': 'east', 'music_volume': 20})
        self.assertEqual(app.state.names, {'$USR': 'Sam', '$ZOE': 'Max'})
        self.assertEqual(app.state.name_sets, {'nr': {'$Emily': 'Em', '$Hector': 'H'}, 'x360': {'$Pat': 'P'}})
        self.assertTrue(app.state.warp_unlocked)
        (options,), _ = app.apply_options.call_args
        self.assertEqual(options, {'autoplay': True, 'music_volume': 20})
        self.assertFalse(set(options) & set(DEVICE_OPTIONS))
        app.state.persist.assert_called()

    def test_options_received_on_the_chooser_are_kept_after_the_library_is_saved(self):
        # The g54 to a computer's chooser (2026-11-19): the opened library's save put its old options back.
        from exp_runtime.menu import MenuState
        from exp_runtime.settings import AppSettings
        from test_shared_settings import library
        settings = AppSettings(self.root / 'settings.json')
        settings.set_preferences({'music_volume': 50, 'skip_ad_intros': False})
        state = MenuState(library(self.root, 'shs', music_volume=50), shared=settings)
        app = SimpleNamespace(state=None, settings=settings)
        SyncFlow(app).apply({'names': {'$USR': 'Sam'}}, {'music_volume': 20, 'skip_ad_intros': True}, state)
        again = AppSettings(self.root / 'settings.json')
        self.assertEqual((again.preferences['music_volume'], again.preferences['skip_ad_intros']), (20, True))
        self.assertEqual(MenuState(library(self.root / 'next', 'cod'), shared=again).music_volume, 20)
        self.assertEqual(state.names['$USR'], 'Sam')

    def test_a_finished_sync_leaves_the_search_or_waiting_page_it_ended(self):
        # The g54 and the PC (2026-11-19): after a sync the Choose Receiver row did nothing and Receive still said
        # "waiting", since the finder and the receiver close with the session.
        from exp_runtime.sync_flow import FIND_PAGE, RECEIVE_PAGE, SYNC_PAGE
        for page, backed in ((FIND_PAGE, True), (RECEIVE_PAGE, True), (SYNC_PAGE, False)):
            app = app_with(self.root)
            flow = SyncFlow(app)
            flow.ui = Mock()
            flow.ui.screen.return_value = page
            flow.finished(SimpleNamespace(status='failed', message='The other device said no.'))
            self.assertEqual(flow.ui.menu.back.called, backed, page)
            flow.ui.notify.assert_called_with('Sync Failed', 'The other device said no.')

    def test_a_sender_offers_imported_episodes_and_sends_only_the_options_and_names_switched_on(self):
        app = app_with(self.root, autoplay=True, music=True, vibration=True, device_vibration=False,
                       controller_confirm='south', grid_controls='hold', **{key: False for key in (
                           'sound', 'logging_disabled', 'side_panels', 'choice_hints', 'skip_minigames', 'skip_ad_intros',
                           'skip_upsell_intros', 'skip_ahead', 'undo', 'disable_choice_timer', 'hd_backdrop', 'hires_portraits', 'ms3_characters', 'java_look', 'brew_08_backgrounds', 'hollywood_art', 'smartphone_music', 'word_grid_skin', 'grids_as_memory', 'ch_portraits', 'ch_backdrop', 'dim_backdrops',
                           'arena_minigames', 'arena_skin', 'skip_sound_prompt', 'dsi_backgrounds')}, dsi_pixels='sharp', preferred_language='fr', music_volume=50, sound_volume=50, order='episode', title_language='en',
                           title_music='default', last_title_game='default', title_look='default', last_title_look='default', ch_dialogue='cases', claire_powerups='once', claire_round_style='own')
        provider = SendProvider(app, ['options', 'episodes'], ['shs'])
        self.assertEqual(provider.offer(['shs']), {'shs': ['a']})
        self.assertEqual(provider.player, {})                     # Names off, Saved Games off
        self.assertNotIn('vibration', provider.options)
        self.assertTrue(provider.options['autoplay'])
        # Preferred Language, and the four it replaced for a device from before it (2026-11-18)
        self.assertEqual({key: provider.options[key] for key in ('preferred_language', 'title_language', 'dsi_language',
                                                                 'shs11_language', 'story_language')},
                         dict(preferred_language='fr', title_language='fr', dsi_language='fr', shs11_language='off',
                              story_language='fr'))
        self.assertIsNone(SendProvider(app, ['names']).options)
        self.assertEqual(SendProvider(app, ['names']).player['names']['$USR'], 'Zoe')

    def test_a_receiver_takes_the_games_it_has_names_those_it_lacks_and_wants_only_what_it_lacks(self):
        app = app_with(self.root)
        host = ReceiveHost(SyncFlow(app))
        self.assertIsNone(host.check({'games': ['shs', 'cod']}))
        self.assertIsNotNone(host.check({'games': ['nr']}))
        self.assertEqual(host.games({'games': ['shs', 'cod', 'nr']}), (['shs'], ['cod']))
        self.assertEqual(host.want('shs', ['a', 'b', 'c']), ['b', 'c'])

    def test_the_result_reads_the_same_on_both_devices(self):
        app = app_with(self.root)
        app.library.add_episodes = lambda paths, **options: 1
        host = ReceiveHost(SyncFlow(app))
        stage = self.root / 'stage'
        (stage / 'shs' / 'episodes' / '0').mkdir(parents=True)
        (stage / 'shs' / 'episodes' / '0' / 'B.exp').write_bytes(b'')
        self.assertEqual(host.apply({'categories': ['episodes']}, stage, ['shs']), '1 episode was synced.')
        app.library.add_episodes = lambda paths, **options: 3
        self.assertEqual(host.apply({'categories': ['episodes']}, stage, ['shs']), '3 episodes were synced.')
        (stage / 'shs' / 'episodes' / '0' / 'B.exp').unlink()
        self.assertEqual(host.apply({'categories': []}, stage, ['shs']), 'Nothing needed to change.')

    def test_a_whole_library_is_moved_into_place_and_never_over_one_there(self):
        app = app_with(self.root)
        host = ReceiveHost(SyncFlow(app))
        sent = self.root / 'stage' / 'library' / 'cod'
        (sent / 'content').mkdir(parents=True)
        (sent / 'content' / 'v1.exp').write_bytes(b'one')
        (sent / 'library.json').write_text('{"game": "cod"}')
        (sent / 'stray.txt').write_text('not a library part')
        (self.root / 'cod' / 'thumbs').mkdir(parents=True)           # a deleted library's leftovers
        self.assertEqual(host.install('cod', sent), 'The whole Cause of Death library was copied.')
        self.assertEqual((self.root / 'cod' / 'content' / 'v1.exp').read_bytes(), b'one')
        self.assertTrue((self.root / 'cod' / 'library.json').is_file())
        self.assertFalse((self.root / 'cod' / 'thumbs').exists())
        self.assertFalse((self.root / 'cod' / 'stray.txt').exists())
        with self.assertRaises(OSError):
            host.install('cod', sent)

    def test_a_whole_library_sent_is_only_its_own_parts(self):
        from exp_runtime.sync_flow import library_files
        library = self.root / 'shs'
        (library / 'saves').mkdir(parents=True)
        (library / 'saves' / 'a.sav').write_bytes(b'1')
        (library / 'library.json').write_text('{}')
        (library / '.sync-x').mkdir()
        (library / '.sync-x' / 'part').write_bytes(b'2')
        (library / 'library.json.before-x360').write_text('{}')
        self.assertEqual([name for name, _ in library_files(library)], ['library.json', 'saves/a.sav'])


if __name__ == '__main__':
    unittest.main()
