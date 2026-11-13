"""shshd-runtime: an episode made in the Creator takes its primary add-on's settings, declares the ones that need no add-on,
reaches an extra add-on's pictures through aliases and keeps the Creator's own names table (CREATOR_ADDONS_PLAN.md; owner,
2026-11-09)."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from exp_runtime.content import EpisodeResources, declared, feature_pack, free_setting, pack_setting
from exp_runtime.games import GAMES, has_translated_minigames
from exp_runtime.menu import MenuState
from exp_runtime.presentation import normalize, presentation_bytes


def episode(pack=30000, presentation=None):
    """A stand-in episode: its record and its declared presentation (the normalized record)."""
    return SimpleNamespace(record=dict(pack_id=pack, episode_id=1), library=SimpleNamespace(game_id='shs'),
                           presentation=presentation or {})


class Archive:
    def __init__(self, contents):
        self.contents = contents
        self.entries = set(contents)

    def read(self, resource):
        return self.contents[resource]


class RecordTests(unittest.TestCase):
    def test_the_new_members_normalize_and_bad_ones_are_refused(self):
        record = dict(format='shshd-presentation', version=1, creator=True, word_forms=True, big_pickers=True,
                      addons={'primary': 'shsbrew', 'edition': '07'}, aliases={'26500': ['shs11', 26992]}, minigames=True)
        self.assertEqual(normalize(record), dict(creator=True, word_forms=True, big_pickers=True, minigames=True,
                                                 addons=('shsbrew', '07'), aliases={26500: ('shs11', 26992)}))
        self.assertTrue(presentation_bytes(dict(date_first=True, three_word_games=True)).startswith(b'SHSHD-PRESENTATION'))
        for bad in (dict(creator=1), dict(addons={'primary': 'shsbrew', 'edition': '09'}), dict(addons={'primary': ''}),
                    dict(aliases={'26500': ['shs11']}), dict(aliases=[1])):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                normalize(dict(format='shshd-presentation', version=1, **bad))


class FeatureTests(unittest.TestCase):
    def test_a_created_episode_takes_its_primary_add_ons_settings(self):
        brew08, brew07 = episode(presentation=dict(addons=('shsbrew', '08'))), episode(presentation=dict(addons=('shsbrew', '07')))
        self.assertEqual((feature_pack(brew08), feature_pack(brew07)), (31000, 31100))
        self.assertEqual(pack_setting(brew08, 'TRANSLATED_FRAME_BACKDROP'), 26999)                   # BREW's frame...
        self.assertEqual(pack_setting(brew08, 'TRANSLATED_THEME_BACKDROP'), {2: 26991})               # ...pink behind pink
        self.assertEqual(pack_setting(brew08, 'JAVA_LOOK_ART'), 10000)                               # '08's switch
        self.assertIsNone(pack_setting(brew07, 'JAVA_LOOK_ART'))
        self.assertTrue(pack_setting(brew07, 'BREW_08_BACKGROUNDS'))                                 # '07's switch
        shs11 = episode(presentation=dict(addons=('shs11', '')))
        self.assertEqual(pack_setting(shs11, 'TRANSLATED_BADGE_SOUNDS'), GAMES['shs'].TRANSLATED_BADGE_SOUNDS[31600])
        plain = episode()
        self.assertEqual((feature_pack(plain), pack_setting(plain, 'TRANSLATED_FRAME_BACKDROP')), (30000, None))
        self.assertEqual(feature_pack(episode(31000)), 31000)                                        # a translation: its own
        self.assertEqual(feature_pack(episode(presentation=dict(addons=('unknown', '')))), 30000)

    def test_settings_that_need_no_add_on_are_declared_one_by_one(self):
        self.assertTrue(free_setting(episode(31100), 'TRANSLATED_ARTICLE_PACKS', 'word_forms'))     # a BREW translation
        self.assertFalse(free_setting(episode(), 'TRANSLATED_ARTICLE_PACKS', 'word_forms'))
        self.assertTrue(free_setting(episode(presentation=dict(word_forms=True)), 'TRANSLATED_ARTICLE_PACKS', 'word_forms'))
        # The primary add-on alone brings none of them: BREW's frame, but not its "a(n)".
        self.assertFalse(free_setting(episode(presentation=dict(addons=('shsbrew', '08'))), 'TRANSLATED_ARTICLE_PACKS',
                                      'word_forms'))

    def test_the_creators_pickers_hold_four_to_ten_photos(self):
        layouts = GAMES['shs'].CREATOR_PICKER_LAYOUTS
        self.assertEqual(sorted(layouts), [4, 6, 7, 8, 9, 10])
        for count, slots in layouts.items():
            with self.subTest(count=count):
                self.assertEqual(len(slots), count)
                self.assertEqual(len({tuple(slot[:2]) for slot in slots}), count)
                self.assertEqual(tuple(slots[0][:2]), (160, 275))                                  # the chosen one in front
                self.assertTrue(all(20 <= slot[0] <= 300 for slot in slots))

    def test_the_minigames_switch_is_offered_for_a_created_episode_that_asks(self):
        profile = GAMES['shs']
        self.assertFalse(has_translated_minigames(profile, dict(pack_id=30000)))
        self.assertTrue(has_translated_minigames(profile, dict(pack_id=30000), dict(minigames=True)))
        self.assertTrue(has_translated_minigames(profile, dict(pack_id=31000)))


class NamesTests(unittest.TestCase):
    def test_created_episodes_share_the_creators_own_names_table(self):
        state = object.__new__(MenuState)
        state.library, state.names, state.name_sets = SimpleNamespace(game_id='shs'), {'$USR': 'Matt'}, {}
        created = episode(presentation=dict(creator=True))
        self.assertIs(state.names_for(created.record, created), state.name_sets['creator'])
        self.assertIs(state.names_for(episode().record, episode()), state.names)                     # the smartphone's
        self.assertIs(state.names_for(episode(31000).record, episode(31000)), state.name_sets['brew'])
        # A translation keeps its own table even if it carried the mark.
        marked = episode(31000, dict(creator=True))
        self.assertIs(state.names_for(marked.record, marked), state.name_sets['brew'])


class AliasTests(unittest.TestCase):
    def resources(self, presentation):
        primary, extra = Archive({26500: b'primary', 26999: b'frame'}), Archive({26500: b'extra', 26543: b'phone'})
        archives = {'shsx360': primary, 'shsbrew': extra}
        library = SimpleNamespace(game_id='shs', addon=lambda name: (dict(revision=10), archives[name]) if name in archives else None)
        resources = object.__new__(EpisodeResources)
        resources.library, resources.record = library, dict(pack_id=30000, name='test')
        resources.archive = Archive({27000: b'own'})
        resources._presentation, resources._required_addons = presentation, (('shsx360', 1), ('shsbrew', 1))
        resources._addon_archives = [primary, extra]
        return resources

    def test_an_alias_reaches_its_add_on_and_the_primary_wins_the_rest(self):
        resources = self.resources(dict(aliases={28000: ('shsbrew', 26500), 28001: ('shsbrew', 26543), 28002: ('shsbrew', 1)}))
        self.assertEqual(resources._bank_read(26500), b'primary')         # listed first: the primary's
        self.assertEqual(resources._bank_read(28000), b'extra')           # the same number in the extra, by its alias
        self.assertEqual(resources._bank_read(28001), b'phone')
        self.assertEqual(resources._bank_read(27000), b'own')
        self.assertTrue(resources.exists(28001))
        self.assertFalse(resources.exists(28002))                         # an alias to nothing is nothing
        self.assertFalse(resources.exists(28003))
        self.assertEqual(declared(resources, 'aliases')[28000], ('shsbrew', 26500))


if __name__ == '__main__':
    unittest.main()


class TitleMusicTests(unittest.TestCase):
    """Add-Ons' Title Screen Music (owner, 2026-11-09): the main menu's tune from a translated game's addon, or the game's own."""

    def app(self, choice, last='default', addons=('shsbrew', 'shs11')):
        from exp_runtime.application import Application
        tunes = {'shsbrew': (26906, b'brew'), 'shs11': (26981, b'eleven'), 'shsx360': (26996, b'x360'), 'shsnr': (26988, b'nr')}
        held = {name: (dict(revision=1), Archive({tunes[name][0]: tunes[name][1]})) for name in addons}
        has = lambda name, resource: name in held and resource in held[name][1].entries          # noqa: E731
        library = SimpleNamespace(game_id='shs', addon=held.get, addon_has=has,
                                  addon_resource=lambda name, resource: held[name][1].read(resource) if has(name, resource) else None)
        app = SimpleNamespace(library=library,
                              state=SimpleNamespace(title_music=choice, last_title_game=last, persist=lambda: None),
                              _attempt=lambda action: action())
        for name in ('title_music', 'title_music_offered', 'remember_title_game'):
            setattr(app, name, getattr(Application, name).__get__(app))
        return app

    def test_the_chosen_games_tune_plays_and_default_or_a_missing_addon_keeps_the_games_own(self):
        self.assertEqual(self.app('brew').title_music(), b'brew')
        self.assertEqual(self.app('shs11').title_music(), b'eleven')
        self.assertIsNone(self.app('default').title_music())
        self.assertIsNone(self.app('x360').title_music())                   # its addon isn't here
        self.assertEqual(self.app('auto', last='shs11').title_music(), b'eleven')
        self.assertIsNone(self.app('auto', last='default').title_music())
        self.assertEqual(self.app('default').title_music_offered(), ['default', 'auto', 'brew', 'shs11'])

    def test_auto_follows_the_game_last_played(self):
        app = self.app('auto')
        for presentation, pack, expected in (({}, 31100, 'brew'), ({}, 31300, 'nr'), ({}, 5, 'default'),
                                             ({'addons': ('shs11', '')}, 30000, 'shs11')):
            with self.subTest(pack=pack):
                app.remember_title_game(episode(pack, presentation))
                self.assertEqual(app.state.last_title_game, expected)


class Mp3FromTests(unittest.TestCase):
    """audio.mp3_from: an MP3 starting at the whole frame that holds a time, for '11's title tune (owner, 2026-11-09)."""

    def test_it_starts_at_the_frame_holding_the_time_and_leaves_other_data_alone(self):
        from exp_runtime.audio import mp3_from, mp3_length_ms
        frame = b'\xff\xfb\x90\x00' + bytes(413)                   # MPEG-1 layer III, 128 kbit/s, 44.1 kHz: 417 bytes, 26.1 ms
        tag = b'ID3\x04\x00\x00\x00\x00\x00\x05' + bytes(5)
        data = tag + b''.join(frame[:3] + bytes([n]) + frame[4:] for n in range(10))
        self.assertEqual(mp3_from(data, 100)[:4], frame[:3] + bytes([3]))      # 78-104 ms: the fourth frame
        self.assertEqual(len(mp3_from(data, 100)), 7 * len(frame))
        self.assertEqual(mp3_length_ms(mp3_from(data, 100)), 182)
        self.assertIs(mp3_from(data, 0), data)
        self.assertEqual(mp3_from(b'RIFF....WAVE', 500), b'RIFF....WAVE')


class FileReadTests(unittest.TestCase):
    """exp.read_file_resource / file_index: one record or the index of a file, without reading the rest (the g54's Options
    froze reading every episode whole for its presentation record; owner, 2026-11-09)."""

    def test_one_resource_and_the_index_match_the_whole_archive(self):
        from exp_runtime.exp import ExpArchive, encode_exp, file_index, read_file_resource
        data = encode_exp({1: b'meta', 3: b'SHSHD-PRESENTATION\0{}', 26000: bytes(range(256)) * 400})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'episode.exp'
            path.write_bytes(data)
            whole = ExpArchive(data)
            self.assertEqual(set(file_index(path)), set(whole.entries))
            for resource in (1, 3, 26000):
                self.assertEqual(read_file_resource(path, resource), whole.read(resource))
            self.assertIsNone(read_file_resource(path, 5))
