"""Finished episodes (owner, 2026-11-19): an episode played to its end once shows its list row's play icon in green.
The library keeps them in player.json; a newer copy takes its older copies' mark; Back Up / Restore and Sync carry them;
Delete All Saves clears them."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from test_shared_settings import library


class FinishedEpisodesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_the_library_keeps_them_in_player_json(self):
        from exp_runtime.menu import MenuState
        from exp_runtime.settings import AppSettings
        settings = AppSettings(self.root / 'settings.json')
        shelf = library(self.root, 'shs', music_volume=50)
        state = MenuState(shelf, shared=settings)
        self.assertEqual(state.finished, set())
        state.finished.update({'b', 'a'})
        state.persist()
        self.assertEqual(json.loads((shelf.directory / 'player.json').read_text(encoding='utf-8'))['finished'], ['a', 'b'])
        self.assertEqual(MenuState(shelf, shared=settings).finished, {'a', 'b'})

    def app(self):
        from exp_runtime import application
        app = SimpleNamespace(state=SimpleNamespace(finished=set(), persist=Mock()), _attempt=lambda work: work())
        app.library = SimpleNamespace(episodes=[{'id': 'old'}, {'id': 'new', 'carries': ['older']}, {'id': 'other'}])
        app.finished_ids = lambda library=None, state=None: application.Application.finished_ids(app, library, state)
        return app, application.Application

    def test_a_storys_end_marks_it_and_a_newer_copy_keeps_the_mark(self):
        app, Application = self.app()
        session = SimpleNamespace(episode_ended=False, resources=SimpleNamespace(record={'id': 'old'}))
        app.game = SimpleNamespace(session=session)
        Application.mark_finished(app)
        self.assertEqual(app.state.finished, set())                 # still playing
        session.episode_ended = True
        Application.mark_finished(app)
        self.assertEqual(app.state.finished, {'old'})
        app.state.persist.assert_called_once()
        app.state.finished.add('older')                             # finished before a newer copy replaced it
        self.assertEqual(app.finished_ids(), {'old', 'new'})

    def test_a_save_left_at_a_storys_end_fills_in_a_finish_from_before(self):
        # Before the marks were kept, a story's end still left its last save at the end (State.resume_path reads it to
        # hide Resume): refresh_saves takes those as finished, and keeps them.
        app, Application = self.app()
        def resume_path(episode):
            if episode == 'other':
                app.state.finished.add('other')         # (what resume_path does for a save at a story's end)
            return None
        app.state.resume_path = resume_path
        app.game = None
        Application.refresh_saves(app)
        self.assertEqual(app.finished, {'other'})
        app.state.persist.assert_called_once()
        Application.refresh_saves(app)
        app.state.persist.assert_called_once()                    # nothing new: not written again

    def test_back_up_restore_and_sync_carry_them(self):
        from exp_runtime.progress_bundle import PLAYER_KEYS, restore_bundle, write_bundle
        from exp_runtime.sync_flow import SyncFlow
        self.assertIn('finished', PLAYER_KEYS)
        directory = self.root / 'lib'
        (directory / 'saves').mkdir(parents=True)
        target = self.root / 'backup.zip'
        write_bundle(directory, 'shs', dict(names={}, finished=['a', 'b']), {}, target)
        (self.root / 'back').mkdir()
        self.assertEqual(restore_bundle(self.root / 'back', target, 'shs')[1]['finished'], ['a', 'b'])
        from exp_runtime.application import Application
        state = SimpleNamespace(names={}, name_sets={}, warp_unlocked=False, finished={'z'}, persist=Mock())
        Application.restore_player(state, {'finished': ['a', 'b']})
        self.assertEqual(state.finished, {'a', 'b'})                # a restore puts back the backup's
        state.finished = {'z'}
        SyncFlow(SimpleNamespace(state=state)).apply({'finished': ['a']}, None, state)
        self.assertEqual(state.finished, {'a', 'z'})                # a sync adds the sender's to the receiver's

    def test_the_rows_icon_goes_green(self):
        import pygame
        from exp_runtime.desktop_episode_list_hd import HdEpisodeList
        from exp_runtime.hd_scale import S
        pygame.init()
        self.addCleanup(pygame.quit)
        pygame.display.set_mode((8, 8))
        picker = HdEpisodeList.__new__(HdEpisodeList)
        colours = []
        for saved in (False, True):
            for finished in (False, True):
                layer = pygame.Surface((64 * S, 64 * S), pygame.SRCALPHA)
                picker.draw_icon(layer, 32, 32, saved, finished)
                ring = layer.get_at((32 * S, (32 - 15) * S))[:3]       # on the ring, above the white disc
                colours.append((saved, finished, ring))
        for saved, finished, (r, g, b) in colours:
            self.assertEqual(g > b, finished, (saved, finished, (r, g, b)))


if __name__ == '__main__':
    unittest.main()
