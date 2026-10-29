"""Release metadata, opt-out, launch lifecycle and both host handoffs."""
from concurrent.futures import Future
import json
import importlib.util
import os
from pathlib import Path
import tempfile
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from exp_runtime.app_info import PROJECT_URL
from exp_runtime.settings import AppSettings
from exp_runtime.updates import (MAX_RESPONSE, RELEASE_API, UpdateCheck, update_message,
                                  fetch_release, newer_release)


def release(tag='v0.5.0', **fields):
    return json.dumps(dict(tag_name=tag, draft=False, prerelease=False, **fields))


class UpdateTests(unittest.TestCase):
    def test_versions_are_numeric_and_only_new_stable_releases_are_offered(self):
        for current, latest, expected in (('0.4.1', 'v0.4.2', True), ('0.9.0', 'v0.10.0', True),
                ('0.10.0', 'v0.9.0', False), ('0.5.0', 'v0.5.0', False), ('1.0.0', 'v0.99.0', False),
                ('0.5.0rc1', 'v0.5.0', True), ('0.5.0.dev2', 'v0.5.0', True),
                ('0.5.0+local', 'v0.5.0', False), ('0.5.0.post1', 'v0.5.0', False),
                ('0.4.1', '0.5.0', True), ('development', 'v0.5.0', False),
                ('0.4.1', 'nightly', False), ('0.4.1', 'v0.5.0rc1', False)):
            with self.subTest(current=current, latest=latest):
                self.assertEqual(newer_release(release(latest), current) is not None, expected)
        for field in ('draft', 'prerelease'):
            data = json.loads(release())
            data[field] = True
            self.assertIsNone(newer_release(json.dumps(data), '0.4.1'))
            data[field] = 0
            self.assertIsNone(newer_release(json.dumps(data), '0.4.1'))

    def test_untrusted_metadata_cannot_change_the_download_destination(self):
        update = newer_release(release(html_url='file:///tmp/evil', body='Untrusted message'), '0.4.1')
        self.assertEqual(update.url, PROJECT_URL + '/releases/tag/v0.5.0')
        for payload in (None, 'null', '[]', '{}', '<html>offline</html>', b'\xff', ' ' * (MAX_RESPONSE + 1),
                        release('../../elsewhere'), release('v01.2.3'), release('v1.2.3/elsewhere')):
            self.assertIsNone(newer_release(payload, '0.4.1'))

    def test_check_runs_once_and_cancellation_ignores_late_results(self):
        future = Future()
        fetcher = Mock(return_value=future)
        check = UpdateCheck(fetcher, current='0.4.1')
        check.start(); check.start()
        fetcher.assert_called_once_with()
        self.assertIsNone(check.poll())
        future.set_result(release())
        self.assertEqual(check.poll().version, '0.5.0')
        check.dismiss(); check.start()
        self.assertIsNone(check.poll())
        fetcher.assert_called_once_with()
        late = Future(); late.set_running_or_notify_cancel()
        check = UpdateCheck(lambda: late, current='0.4.1')
        check.start(); check.cancel()
        late.set_result(release())
        self.assertIsNone(check.poll())
        skipped = Mock()
        UpdateCheck(skipped, current='development').start()
        skipped.assert_not_called()

    def test_transport_is_bounded_and_network_errors_stay_silent(self):
        response = Mock(status=200)
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = release().encode()
        with patch('exp_runtime.updates._ssl_context', return_value='verified context'), \
                patch('exp_runtime.updates.urlopen', return_value=response) as request:
            self.assertEqual(fetch_release().result(timeout=2), release().encode())
            self.assertEqual(request.call_args.args[0].full_url, RELEASE_API)
            self.assertEqual(request.call_args.args[0].get_method(), 'GET')
            self.assertEqual(request.call_args.kwargs['context'], 'verified context')
            self.assertEqual(request.call_args.kwargs['timeout'], 8)
            response.read.assert_called_once_with(MAX_RESPONSE + 1)
            response.read.return_value = b'x' * (MAX_RESPONSE + 1)
            self.assertIsNone(fetch_release().result(timeout=2))
        for error in (URLError('offline'), TimeoutError(), HTTPError(RELEASE_API, 403, 'rate limited', {}, None),
                      HTTPError(RELEASE_API, 404, 'no releases', {}, None)):
            with patch('exp_runtime.updates._ssl_context', return_value=None), \
                    patch('exp_runtime.updates.urlopen', side_effect=error):
                self.assertIsNone(fetch_release().result(timeout=2))

    def test_cancelling_a_blocked_transport_does_not_wait_for_network(self):
        entered, finish, stopped = Event(), Event(), Event()
        def offline(*args, **kwargs):
            entered.set()
            finish.wait(5)
            stopped.set()
            raise URLError('offline')
        with patch('exp_runtime.updates._ssl_context', return_value=None), \
                patch('exp_runtime.updates.urlopen', side_effect=offline):
            future = fetch_release()
            try:
                self.assertTrue(entered.wait(2))
                self.assertTrue(future.cancel())
                self.assertFalse(stopped.is_set())
            finally:
                finish.set()
                self.assertTrue(stopped.wait(2))

    def test_preferences_default_on_persist_globally_and_do_not_reenable_when_damaged(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'preferences/settings.json'
            settings = AppSettings(path)
            self.assertTrue(settings.check_for_updates)
            self.assertFalse(path.exists())
            settings.set_update_check(False)
            self.assertFalse(AppSettings(path).check_for_updates)
            before = path.read_bytes()
            with patch.object(Path, 'replace', side_effect=OSError('read-only disk')):
                with self.assertRaises(OSError):
                    settings.set_update_check(True)
            self.assertFalse(settings.check_for_updates)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual([p.name for p in path.parent.iterdir()], ['settings.json'])
            path.write_text('{"version":1,"check_for_updates":"yes"}')
            with self.assertLogs(level='WARNING'):
                self.assertFalse(AppSettings(path).check_for_updates)


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class ApplicationUpdateTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        version = patch('exp_runtime.updates.runtime_version', return_value='0.4.1')
        version.start(); self.addCleanup(version.stop)
        self.future = Future()
        self.fetcher = Mock(return_value=self.future)

    def app(self):
        from exp_runtime.application import Application
        app = Application(audio=False, library_root=self.root / 'libraries',
                          settings_path=self.root / 'settings.json', update_fetcher=self.fetcher)
        self.addCleanup(app.close)
        return app

    def test_launch_is_nonblocking_and_no_dismisses_once_without_opening_a_browser(self):
        app = self.app()
        self.assertFalse(app.busy)
        app.tick(50); app.render()
        self.assertIsNone(app.update_prompt)
        opener = app.url_opener = Mock()
        self.future.set_result(release())
        app.tick(0)
        with patch.object(app.renderer, 'label', wraps=app.renderer.label) as label:
            app.render()
            self.assertIn(update_message('0.5.0'), [call.args[0] for call in label.call_args_list])
        self.assertEqual([c for _, c in app.buttons], [('update_no',), ('update_yes',)])
        app.command(('choose_game', 'shs'))
        self.assertEqual(app.screen, 'games')  # Covered controls are inert.
        app.command(('update_no',))
        app.choose_game('shs'); app.tick(4000)
        app.show_game_chooser(); app.tick(4000)
        self.assertIsNone(app.update_prompt)
        opener.assert_not_called()
        self.fetcher.assert_called_once_with()

    def test_a_message_over_the_hd_menus_has_an_ok_that_a_tap_dismisses(self):
        """The owner's g54 was left on "Added 53 episodes." over the HD main menu: the busy card had no button, and a
        phone or an iPad has no Escape or Enter. The message is the prompt's card with an OK; a tap on it dismisses."""
        import pygame
        app = self.app()
        app.window = pygame.display.set_mode((768, 1024))
        drawn = []

        def draw_prompt(canvas, title, text, labels):
            drawn.append((title, text, labels))
            return [pygame.Rect(306, 588, 156, 58)]
        canvas = pygame.Surface((768, 1024))
        app.shell = SimpleNamespace(render=lambda: canvas, windows=SimpleNamespace(draw_prompt=draw_prompt))
        app.screen, app.message = 'main', 'Added 53 episodes.'
        self.assertFalse(app.busy)
        with patch.object(app, 'present_frame'):
            app.render_shell()
        self.assertEqual(drawn, [(app.game_title, 'Added 53 episodes.', ('OK',))])
        app.viewport = pygame.Rect(0, 0, 768, 1024)
        with patch.object(app, 'picker_point', side_effect=lambda pos: pos):
            for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
                app.handle_event(pygame.event.Event(kind, pos=(100, 100), button=1))
            self.assertEqual(app.message, 'Added 53 episodes.')                 # beside the button: nothing
            for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
                app.handle_event(pygame.event.Event(kind, pos=(380, 610), button=1))
        self.assertEqual(app.message, '')

    def test_yes_opens_only_the_release_page_then_closes_the_game(self):
        app = self.app()
        opener = app.url_opener = Mock()
        self.future.set_result(release())
        app.tick(0); app.render()
        opener.assert_not_called()
        self.assertFalse(app.quit_requested)
        app.command(('update_yes',))
        opener.assert_called_once_with(PROJECT_URL + '/releases/tag/v0.5.0')
        self.assertTrue(app.quit_requested)          # run() ends after this event; close() checkpoints as usual
        self.assertIn('close the game and open your browser', update_message('0.5.0'))
        app.quit_requested = False
        app.active = False; app.tick(20)
        app.active = True; app.tick(20)
        self.assertIsNone(app.update_prompt)
        self.assertEqual(app.screen, 'games')

    def test_native_confirmation_uses_two_separate_button_regions_not_the_footer_art(self):
        from exp_runtime.ui_assets import Layout, LayoutBank, LayoutNode
        renderer = self.app().renderer
        # Authored footer: two art nodes followed by two hit regions. Native
        # node IDs are one-based; selecting the separator would stretch a
        # button across the whole footer and hide the other label.
        nodes = tuple(LayoutNode(bounds, (0, 0, 0, 0), kind, payload)
                      for bounds, kind, payload in (
                          ((0, 0, 302, 43), 1, (3, 0)),
                          ((0, 0, 302, 1), 1, (3, 1)),
                          ((15, 7, 93, 36), 6, ()),
                          ((209, 7, 287, 36), 6, ())))
        renderer.library = object()
        renderer.bank = LayoutBank(0, 0, 0, (), (Layout(1, 1, ()),) * 39 + (Layout(302, 43, nodes),))
        renderer.strings = {25: 'Yes', 26: 'No'}
        with patch.object(renderer, 'layout'), patch.object(renderer, 'label') as label:
            renderer.confirmation(update_message('0.5.0'))
        no, yes = renderer.buttons
        self.assertEqual(no[1], ('update_no',))
        self.assertEqual(yes[1], ('update_yes',))
        self.assertEqual(tuple(no[0]), (24, 288, 78, 29))
        self.assertEqual(tuple(yes[0]), (218, 288, 78, 29))
        self.assertFalse(no[0].colliderect(yes[0]))
        self.assertEqual([call.args[0] for call in label.call_args_list][-2:], ['No', 'Yes'])

    @patch('exp_runtime.desktop_menu.UPDATE_REPOSITORY', 'owner/repository')   # shown only with a release source
    def test_opt_out_survives_game_switch_and_restart_and_disabling_ignores_inflight_result(self):
        app = self.app()
        self.future.set_running_or_notify_cancel()
        app.command(('options',)); app.tick(200); app.render()
        self.assertIn(('toggle_updates',), [command for _, command in app.buttons])
        app.command(('toggle_updates',))
        self.future.set_result(release())
        app.command(('back',)); app.tick(200)
        self.assertIsNone(app.update_prompt)
        for game in ('shs', 'cod'):
            app.choose_game(game)
            self.assertFalse(app.settings.check_for_updates)
        app.close()
        self.fetcher.reset_mock()
        restarted = self.app()
        restarted.tick(0)
        self.fetcher.assert_not_called()
        self.assertFalse(restarted.settings.check_for_updates)

    def test_reenable_starts_only_one_check_if_launch_was_disabled(self):
        AppSettings(self.root / 'settings.json').set_update_check(False)
        app = self.app()
        self.fetcher.assert_not_called()
        app.command(('toggle_updates',))
        self.fetcher.assert_called_once_with()
        app.command(('toggle_updates',)); app.command(('toggle_updates',))
        self.fetcher.assert_called_once_with()

    def test_alerts_imports_and_active_story_defer_the_prompt(self):
        app = self.app()
        app.message = 'An import warning'
        self.future.set_result(release())
        app.tick(0)
        self.assertIsNone(app.update_prompt)
        app.message = ''
        job = Future(); app.job = job
        app.tick(0)
        self.assertIsNone(app.update_prompt)
        app.job = None
        app.screen = 'game'
        app.game = SimpleNamespace(tick=Mock(), session=SimpleNamespace(episode_exited=False, episode_ended=False))
        app.tick(50)
        app.game.tick.assert_called_once_with(50)
        self.assertIsNone(app.update_prompt)
        app.game = None; app.screen = 'games'; app.tick(0)
        self.assertIsNotNone(app.update_prompt)

    def test_modal_cancels_old_gestures_and_enter_defaults_to_no(self):
        import pygame
        app = self.app()
        app.render()
        old = app.buttons[0][0].center
        position = tuple(round(n * app.viewport.width / 320) for n in old)
        app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=position))
        self.assertIsNotNone(app.pressed)
        self.future.set_result(release()); app.tick(0); app.render()
        self.assertIsNone(app.pressed)
        yes = next(r for r, command in app.buttons if command == ('update_yes',)).center
        position = tuple(round(n * app.viewport.width / 320) for n in yes)
        app.url_opener = Mock()
        app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=position))
        app.url_opener.assert_not_called()
        app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        self.assertIsNone(app.update_prompt)
        app.url_opener.assert_not_called()


class NativeUpdateTests(unittest.TestCase):
    def test_ios_fetch_is_one_shot_and_results_use_shared_modal_and_browser_handoff(self):
        from exp_runtime import graphics
        from exp_runtime.app_icon import icon_surface
        from exp_runtime.platforms.drawing import Backend
        from exp_runtime.platforms.ios import Host
        from PIL import Image
        from native_host_fonts import FontHost
        font = FontHost()
        with tempfile.TemporaryDirectory() as temporary, \
                patch('exp_runtime.updates.runtime_version', return_value='0.4.1'):
            root = Path(temporary)
            icon = root / 'authored-icon.png'; Image.new('RGBA', (2, 2), 'green').save(icon)
            backend = Backend(font, icon)
            previous = graphics.install(backend)
            self.addCleanup(graphics.install, previous)
            icon_surface.cache_clear()
            self.addCleanup(icon_surface.cache_clear)
            host = Host(root, backend=backend, library_root=root / 'libraries')
            self.addCleanup(host.app.close)
            first = host.request({'operation': 'frame'})
            self.assertEqual(first['update_request']['url'], RELEASE_API)
            self.assertIsNone(host.request({'operation': 'frame'})['update_request'])
            shown = host.request(dict(operation='update_result', payload=release()))
            self.assertIsNotNone(host.app.update_prompt)
            # iOS only informs: one OK, which dismisses; nothing opens and the app never quits (can_quit=False).
            self.assertEqual([cmd for _, cmd in host.app.buttons], [('update_no',)])
            generation = shown['generation']
            rect = host.app.buttons[0][0]
            point = [int(v * 1.5) for v in rect.center]
            stale = [dict(kind=kind, point=point, generation=generation - 1) for kind in ('down', 'up')]
            self.assertIsNone(host.request(dict(operation='frame', events=stale))['open_url'])
            self.assertIsNotNone(host.app.update_prompt)
            events = [dict(kind=kind, point=point, generation=generation) for kind in ('down', 'up')]
            accepted = host.request(dict(operation='frame', events=events))
            self.assertIsNone(accepted['open_url'])
            self.assertIsNone(host.app.update_prompt)
            self.assertFalse(host.app.quit_requested)
            host.app.command(('update_yes',))             # even a stray Yes never opens or quits there
            self.assertFalse(host.app.quit_requested)


class ForkUpdateSourceTests(unittest.TestCase):
    def test_the_check_asks_this_forks_releases_never_upstreams(self):
        from exp_runtime import app_info, updates
        self.assertEqual(app_info.UPDATE_REPOSITORY, '1timewire1/shshd-runtime')
        self.assertEqual(updates.RELEASE_API, 'https://api.github.com/repos/1timewire1/shshd-runtime/releases/latest')
        self.assertTrue(app_info.PROJECT_URL.endswith('/1timewire1/shshd-runtime'))
        self.assertNotIn('joshrmcdaniel', updates.RELEASE_API)

    def test_no_release_source_means_no_network_check(self):
        from exp_runtime import updates
        with patch.object(updates, 'UPDATE_REPOSITORY', None), patch.object(updates, 'fetch_release') as fetch:
            check = updates.UpdateCheck(current='1.0.0')
            check.fetcher = updates.fetch_release        # the default, as Application builds it
            check.start()
            fetch.assert_not_called()
            self.assertIsNone(check.future)



class LaunchOfferTests(unittest.TestCase):
    """The HD launch holds before "Play with sound?" for the update check (Application.update_holds_launch)."""

    def test_the_launch_waits_briefly_for_an_answer_and_for_an_offer_to_be_answered(self):
        from types import SimpleNamespace
        from exp_runtime.application import UPDATE_WAIT, Application
        app = lambda prompt=None, future=None, available=None: SimpleNamespace(
            update_prompt=prompt, updates=SimpleNamespace(future=future, available=available))
        holds = Application.update_holds_launch
        self.assertFalse(holds(app(), 0))                               # no check out: straight on
        self.assertTrue(holds(app(future=object()), 0))                 # the check is still out
        self.assertFalse(holds(app(future=object()), UPDATE_WAIT))      # ... but only for UPDATE_WAIT
        self.assertTrue(holds(app(available=object()), 0))             # an answer about to be shown
        self.assertTrue(holds(app(prompt=object()), UPDATE_WAIT * 10))  # an offer on screen holds until answered
