"""The app's own saving (`SHSEngine::onTick` every 60 s, `onExit` when the app is left), on a stand-in application shell."""
import importlib.util
import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class AutosaveTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        from exp_runtime import application
        self.pygame, self.module = pygame, application
        self.addCleanup(pygame.quit)
        session = SimpleNamespace(episode_exited=False, pending=SimpleNamespace(name='dialogue'))
        game = SimpleNamespace(session=session, handle_event=Mock(return_value=True), tick=Mock())
        self.app = SimpleNamespace(
            game=game, screen='game', active=True, pressed=None, busy=False, message='', job=None, autosave_age=0,
            unsaved_entry=True, state=SimpleNamespace(checkpoint=Mock(return_value='path')), save_screenshot=Mock(),
            refresh_saves=Mock(), flush_drops=Mock(), return_to_menu=Mock(), cancel_pointer=Mock(),
            _sync_menu_music=Mock(), settings=SimpleNamespace(check_for_updates=False), update_prompt=None)
        self.app.autosave = lambda **kwargs: self.module.Application.autosave(self.app, **kwargs)

    def tick(self, elapsed):
        self.module.Application.tick(self.app, elapsed)

    def test_the_game_is_saved_every_sixty_seconds_of_play(self):
        self.tick(59000)
        self.app.state.checkpoint.assert_not_called()
        self.tick(1500)
        self.app.state.checkpoint.assert_called_once_with(self.app.game.session)
        self.assertEqual(self.app.autosave_age, 0)
        self.app.save_screenshot.assert_not_called()                 # only leaving the app photographs the game
        self.tick(30000)
        self.app.state.checkpoint.assert_called_once()

    def test_leaving_the_app_saves_once_until_the_game_is_entered_again(self):
        lost = self.pygame.event.Event(self.pygame.WINDOWFOCUSLOST)
        self.module.Application.handle_event(self.app, lost)
        self.app.state.checkpoint.assert_called_once()
        self.app.save_screenshot.assert_called_once()
        self.assertFalse(self.app.unsaved_entry)
        self.module.Application.handle_event(self.app, lost)          # +0x649ce was cleared by the first
        self.app.state.checkpoint.assert_called_once()

    def test_nothing_is_saved_without_a_screen_or_after_the_episode_ends(self):
        self.app.game.session.pending = None
        self.assertIsNone(self.module.Application.autosave(self.app))
        self.app.game.session.pending = SimpleNamespace(name='dialogue')
        self.app.game.session.episode_exited = True
        self.assertIsNone(self.module.Application.autosave(self.app))
        self.app.state.checkpoint.assert_not_called()

    def test_a_failed_save_is_logged_and_the_game_carries_on(self):
        self.app.state.checkpoint.side_effect = OSError('disk full')
        with self.assertLogs(level='WARNING'):
            self.assertIsNone(self.module.Application.autosave(self.app))
        self.assertEqual(self.app.message, '')

    def test_finishing_football_season_unlocks_warping_for_good(self):
        app = self.app
        app.state.warp_unlocked = False
        app.state.persist = Mock()
        app._attempt = lambda operation: operation()
        app.game.session.resources = SimpleNamespace(record={'builtin': 'football-star'})
        unlock = lambda: self.module.Application.unlock_warp_if_football_finished(app)
        unlock()
        self.assertFalse(app.state.warp_unlocked)                     # still playing
        app.game.session.episode_exited = True
        unlock()
        self.assertTrue(app.state.warp_unlocked)
        app.state.persist.assert_called_once()
        app.state.warp_unlocked = False
        app.game.session.resources = SimpleNamespace(record={'id': 'some downloaded episode'})
        unlock()
        self.assertFalse(app.state.warp_unlocked)                     # another episode's end does not


if __name__ == '__main__':
    unittest.main()
