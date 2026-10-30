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
    return SimpleNamespace(state=state, library=library, apply_options=Mock(), shell=None)


class SyncFlowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

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

    def test_a_sender_offers_imported_episodes_and_sends_only_the_options_and_names_switched_on(self):
        app = app_with(self.root, autoplay=True, music=True, vibration=True, device_vibration=False,
                       controller_confirm='south', grid_controls='hold', **{key: False for key in (
                           'sound', 'logging_disabled', 'choice_hints', 'skip_minigames', 'skip_ad_intros',
                           'skip_upsell_intros', 'disable_choice_timer', 'hd_backdrop', 'hires_portraits',
                           'skip_sound_prompt')}, music_volume=50, sound_volume=50, order='episode', title_language='en')
        provider = SendProvider(app, ['options', 'episodes'])
        self.assertEqual(provider.offer(), ['a'])
        self.assertEqual(provider.player, {})                     # Names off, Saved Games off
        self.assertNotIn('vibration', provider.options)
        self.assertTrue(provider.options['autoplay'])
        self.assertIsNone(SendProvider(app, ['names']).options)
        self.assertEqual(SendProvider(app, ['names']).player['names']['$USR'], 'Zoe')

    def test_a_receiver_on_the_other_game_says_which_and_wants_only_what_it_lacks(self):
        app = app_with(self.root)
        host = ReceiveHost(SyncFlow(app))
        self.assertIsNone(host.check({'game': 'shs'}))
        self.assertIn('not Cause of Death', host.check({'game': 'cod'}))
        self.assertEqual(host.want(['a', 'b', 'c']), ['b', 'c'])

    def test_the_result_reads_the_same_on_both_devices(self):
        app = app_with(self.root)
        app.library.add_episodes = lambda paths: 1
        host = ReceiveHost(SyncFlow(app))
        stage = self.root / 'stage'
        (stage / 'episodes' / '0').mkdir(parents=True)
        (stage / 'episodes' / '0' / 'B.exp').write_bytes(b'')
        self.assertEqual(host.apply({'categories': ['episodes']}, stage), '1 episode was synced.')
        app.library.add_episodes = lambda paths: 3
        self.assertEqual(host.apply({'categories': ['episodes']}, stage), '3 episodes were synced.')
        (stage / 'episodes' / '0' / 'B.exp').unlink()
        self.assertEqual(host.apply({'categories': []}, stage), 'Nothing needed to change.')


if __name__ == '__main__':
    unittest.main()
