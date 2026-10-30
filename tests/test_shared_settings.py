"""Preferences both games share, General's Start In and Extras' Unlock Warping (owner, 2026-10-29)."""
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from exp_runtime.menu import SHARED_PREFERENCES, MenuState, shared_preference
from exp_runtime.settings import AppSettings


def library(root, name, **player):
    """A stand-in library with one episode and, when `player` is given, a player.json holding those values."""
    directory = Path(root) / name
    directory.mkdir(parents=True)
    if player:
        (directory / 'player.json').write_text(json.dumps(dict(version=1, music=True, sound=True, selected='e1',
                                                               **player)), encoding='utf-8')
    return SimpleNamespace(directory=directory, episodes=[{'id': 'e1'}], select=lambda key: {'id': key},
                           game_id='shs')


class SharedSettingsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_an_older_settings_file_still_reads_and_the_new_values_are_kept(self):
        path = self.root / 'settings.json'
        path.write_text(json.dumps(dict(version=1, check_for_updates=False)), encoding='utf-8')
        settings = AppSettings(path)
        self.assertEqual((settings.check_for_updates, settings.preferences, settings.start_in, settings.last_game),
                         (False, {}, 'auto', None))
        settings.set_start_in('games')
        settings.set_last_game('cod')
        settings.set_preferences(dict(autoplay=True))
        again = AppSettings(path)
        self.assertEqual((again.check_for_updates, again.preferences, again.start_in, again.last_game),
                         (False, {'autoplay': True}, 'games', 'cod'))
        with self.assertRaises(ValueError):
            again.set_start_in('elsewhere')
        before = path.stat().st_mtime_ns
        os.utime(path, ns=(10**9, 10**9))
        again.set_preferences(dict(autoplay=True))                         # unchanged: not written again
        self.assertEqual(path.stat().st_mtime_ns, 10**9)
        self.assertNotEqual(before, 10**9)

    def test_start_in_opens_a_game_that_has_a_library_else_the_chooser(self):
        settings = AppSettings(self.root / 'settings.json')
        everything, nothing = (lambda game: True), (lambda game: False)
        self.assertIsNone(settings.boot_game(everything))                  # Last Played, the default: none yet
        settings.set_last_game('cod')
        self.assertEqual(settings.boot_game(everything), 'cod')
        settings.set_start_in('games')
        self.assertIsNone(settings.boot_game(everything))                  # Choose a Game
        settings.set_start_in('cod')
        self.assertEqual(settings.boot_game(everything), 'cod')
        self.assertIsNone(settings.boot_game(nothing))                     # no library yet: the chooser
        settings.set_start_in('auto')
        settings.set_last_game('shs')
        self.assertEqual(settings.boot_game(everything), 'shs')

    def test_both_games_share_options_but_keep_their_own_progress_and_names(self):
        settings = AppSettings(self.root / 'settings.json')
        shs = MenuState(library(self.root, 'shs', autoplay=False, music_volume=20, warp_unlocked=True,
                                names={'$USR': 'Zoe'}), shared=settings)
        shs.autoplay, shs.music_volume, shs.title_language = True, 80, 'es'
        shs.persist()
        self.assertEqual((settings.preferences['autoplay'], settings.preferences['music_volume']), (True, 80))
        self.assertEqual(set(settings.preferences), set(SHARED_PREFERENCES))
        cod = MenuState(library(self.root, 'cod', autoplay=False, music_volume=50), shared=settings)
        self.assertEqual((cod.autoplay, cod.music_volume, cod.title_language), (True, 80, 'es'))
        self.assertEqual((cod.warp_unlocked, cod.names), (False, {}))       # the other game's progress and names
        self.assertEqual(json.loads((shs.library.directory / 'player.json').read_text())['autoplay'], True)

    def test_a_damaged_shared_value_is_ignored(self):
        settings = AppSettings(self.root / 'settings.json')
        settings.preferences = dict(music_volume=400, autoplay='yes', order='random', sound=False)
        state = MenuState(library(self.root, 'shs', music_volume=30), shared=settings)
        self.assertEqual((state.music_volume, state.autoplay, state.order, state.sound), (30, False, 'episode', False))
        self.assertFalse(shared_preference('selected', 'e1'))               # never shared

    def test_the_shared_values_start_from_the_game_played_last(self):
        from exp_runtime.application import Application
        older = library(self.root, 'shs', autoplay=False, choice_hints=True)
        newer = library(self.root, 'cod', autoplay=True, choice_hints=False)
        os.utime(older.directory / 'player.json', ns=(1, 1))
        app = SimpleNamespace(settings=AppSettings(self.root / 'settings.json'),
                              library_path=lambda key: self.root / key)
        Application.seed_shared_preferences(app)
        self.assertEqual((app.settings.preferences['autoplay'], app.settings.preferences['choice_hints']),
                         (True, False))
        app.settings.set_preferences(dict(autoplay=False))
        Application.seed_shared_preferences(app)                           # seeded once
        self.assertFalse(app.settings.preferences['autoplay'])


class UnlockWarpingTests(unittest.TestCase):
    def app(self, unlocked=False, football=True):
        from exp_runtime.application import Application
        state = SimpleNamespace(warp_unlocked=unlocked, persist=Mock())
        records = [{'id': 'f', 'builtin': 'football-star'}] if football else [{'id': 'e'}]
        app = Application.__new__(Application)
        app.state, app.library, app.game, app.message = state, SimpleNamespace(episodes=records), None, ''
        return app

    def test_extras_offers_it_only_while_shs_warping_is_locked(self):
        self.assertTrue(self.app().warp_lock_offered())
        self.assertFalse(self.app(unlocked=True).warp_lock_offered())
        self.assertFalse(self.app(football=False).warp_lock_offered())     # Cause of Death has no Football Season
        app = self.app()
        self.assertTrue(app.unlock_warp())
        self.assertTrue(app.state.warp_unlocked)
        app.state.persist.assert_called_once_with()
        self.assertFalse(app.unlock_warp())                                # gone with the lock

    def test_football_seasons_unlock_shows_its_notice_on_the_main_menu(self):
        from exp_runtime.application_hd import WARP_UNLOCKED_MENU
        app = self.app()
        app.game = SimpleNamespace(session=SimpleNamespace(episode_exited=True,
                                                           resources=SimpleNamespace(record={'builtin': 'football-star'})))
        app.unlock_warp_if_football_finished()
        self.assertTrue(app.warp_notice_due)
        queued = []
        app.shell = SimpleNamespace(stage='end', overlay_active=False, pause_open=False, fading=False,
                                    open_window=queued.append)
        app.screen = 'main'
        app.show_warp_notice()
        self.assertEqual(queued, [])                                       # the end menu is still up
        app.shell.stage = 'main'
        app.show_warp_notice()
        app.show_warp_notice()
        self.assertEqual(queued, [WARP_UNLOCKED_MENU])                     # once

    def test_a_storys_extras_does_not_offer_it(self):
        from exp_runtime.desktop import Desktop
        self.assertNotIn('unlock_warp', Desktop._pause_settings(SimpleNamespace(
            vibration_enabled=False, music_enabled=True, sound_enabled=True, music_volume=1, sound_volume=1,
            panels_open=False, choice_hints=False, skip_minigames=False, autoplay=False, disable_choice_timer=False,
            backdrop_switch=lambda: False, hires_switch=lambda: False)))

if __name__ == '__main__':
    unittest.main()
