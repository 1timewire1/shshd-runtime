"""Which sound SHS '11's translated episodes play, as the full builds do: its games' constants, its relationship icons and its one
channel. The tracks are the addon's order: 0 pad, 1 menu tune, 2 falling saw, 3 bell, 4 arpeggio, 5 three drum hits, 6 rising bass, 7
one drum, 8 and 9 rising pads, 10 a whistle."""
from types import SimpleNamespace
import unittest

from exp_runtime.engine import badge_sound
from exp_runtime.relationships import RelationshipChange
from exp_runtime.shs11_games import SOUND_BASE, SOUND_DONE, SOUND_MISSED_BONUS, SOUND_TIME_UP, SOUND_WRONG


def change(asset, count, previous_asset, previous_count):
    return RelationshipChange(5, asset, count, previous_asset, previous_count)


SMILE, HEART, SKULL = 3012, 3010, 3011
SOUNDS = ('for', 'against')


class GameSoundTests(unittest.TestCase):
    def test_the_games_sounds_are_the_full_builds_tracks(self):
        self.assertEqual([s - SOUND_BASE for s in (SOUND_WRONG, SOUND_MISSED_BONUS, SOUND_DONE, SOUND_TIME_UP)], [7, 8, 9, 10])

    def test_the_word_game_has_11s_right_and_wrong(self):
        from exp_runtime.shs import profile
        self.assertEqual(profile.TRANSLATED_WORD_GAME_SOUNDS[31600], (SOUND_BASE + 8, SOUND_BASE + 7))


class BadgeTests(unittest.TestCase):
    def test_more_smileys_or_hearts_are_for_and_fewer_against(self):
        self.assertEqual(badge_sound(change(SMILE, 2, SMILE, 1), SOUNDS), 'for')
        self.assertEqual(badge_sound(change(HEART, 2, HEART, 3), SOUNDS), 'against')

    def test_more_skulls_are_against_and_fewer_for(self):
        self.assertEqual(badge_sound(change(SKULL, 3, SKULL, 2), SOUNDS), 'against')
        self.assertEqual(badge_sound(change(SKULL, 1, SKULL, 2), SOUNDS), 'for')

    def test_crossing_from_skulls_to_smileys_is_for_and_back_against(self):
        self.assertEqual(badge_sound(change(SMILE, 1, SKULL, 1), SOUNDS), 'for')
        self.assertEqual(badge_sound(change(SKULL, 1, SMILE, 1), SOUNDS), 'against')

    def test_the_same_standing_or_a_first_sight_is_silent(self):
        self.assertIsNone(badge_sound(change(HEART, 2, SMILE, 2), SOUNDS))
        self.assertIsNone(badge_sound(change(SMILE, 2, -1, -1), SOUNDS))
        self.assertIsNone(badge_sound(change(SMILE, 2, SMILE, 2), SOUNDS))


class ChannelTests(unittest.TestCase):
    def player(self, record):
        from exp_runtime.desktop import Desktop
        played = []

        class Sound:
            def __init__(self, name):
                self.name = name

            def set_volume(self, volume):
                pass

            def play(self):
                played.append(('play', self.name))

            def stop(self):
                played.append(('stop', self.name))
        session = SimpleNamespace(resources=SimpleNamespace(record=record, library=SimpleNamespace(game_id='shs')))
        ui = SimpleNamespace(sound_enabled=True, sound_volume=1, session=session, _x360_swaps=lambda: None, _channel_sound=None,
                             _sound=lambda asset, read: Sound(asset))
        ui._one_channel = lambda: Desktop._one_channel(ui)
        return Desktop, ui, played

    def test_a_cue_stops_the_last_in_11s_episodes(self):
        Desktop, ui, played = self.player({'pack_id': 31600})
        Desktop._play_sounds(ui, [26982])
        Desktop._play_sounds(ui, [26987])
        self.assertEqual(played, [('play', 26982), ('stop', 26982), ('play', 26987)])

    def test_shss_own_sounds_and_other_packs_mix_as_ever(self):
        Desktop, ui, played = self.player({'pack_id': 31600})
        Desktop._play_sounds(ui, [8001])
        Desktop._play_sounds(ui, [8002])
        self.assertEqual(played, [('play', 8001), ('play', 8002)])
        Desktop, ui, played = self.player({'pack_id': 31300})
        Desktop._play_sounds(ui, [26982])
        Desktop._play_sounds(ui, [26987])
        self.assertEqual(played, [('play', 26982), ('play', 26987)])


if __name__ == '__main__':
    unittest.main()
