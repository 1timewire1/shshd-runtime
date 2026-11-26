"""SD Portraits (Extras; owner 2026-11-25): portraits in their standard originals, from authored pictures only."""
from io import BytesIO
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from exp_runtime.content import EpisodeResources
from exp_runtime.hd_twins import SD_ADDON, SdPortraits, TwinStore, build_from_map, fingerprint, sd_portraits_due


def png(size, colour):
    stream = BytesIO()
    Image.new('RGBA', size, colour).save(stream, 'PNG')
    return stream.getvalue()


class Library:
    """What build_from_map and EpisodeResources' SD Portraits read."""

    def __init__(self, root, episodes, addon=None, revision=1):
        self.directory = root
        self.game_id = 'shs'
        self.hd_art_mode = 'fill'
        self.sd_portraits = 'off'
        self.store = TwinStore(root)
        self.sd_store = SdPortraits(root)
        self.episodes = [dict(id=key, name=key, variant=variant) for key, (variant, _) in episodes.items()]
        self._assets = {key: assets for key, (_, assets) in episodes.items()}
        self._addon = None if addon is None else (dict(addon=SD_ADDON, revision=revision), self._archive(addon))

    @staticmethod
    def _archive(assets):
        return SimpleNamespace(entries=sorted(assets), read=assets.__getitem__)

    def twin_store(self):
        return self.store

    def sd_portraits_store(self):
        return self.sd_store

    def addon(self, addon_id):
        return self._addon if addon_id == SD_ADDON else None

    def hd_asset(self, resource_id):
        return None

    def open_episode(self, key):
        assets = self._assets[key]
        return SimpleNamespace(archive=self._archive(assets), exists=assets.__contains__, raw_asset=assets.__getitem__)


def resources(library, record_id, variant, assets):
    episode = EpisodeResources.__new__(EpisodeResources)
    episode.library, episode.record = library, dict(id=record_id, variant=variant)
    episode.archive = SimpleNamespace(entries=sorted(assets), read=assets.__getitem__)
    return episode


class SdPortraitsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.sd_viv, self.hd_viv = png((64, 64), 'red'), png((128, 128), 'red')
        self.sd_patchouli = png((64, 64), 'orange')              # another story's original of the same HD picture
        self.sd_kevin, self.hd_kevin = png((64, 64), 'lime'), png((128, 128), 'darkorange')
        self.map = SimpleNamespace(
            VERSION='v1', COVERAGE={},
            TWINS={fingerprint(self.sd_viv): (fingerprint(self.hd_viv), 64, 64),
                   fingerprint(self.sd_kevin): (fingerprint(self.hd_kevin), 64, 64)},
            SD_OF={fingerprint(self.hd_viv): (fingerprint(self.sd_patchouli),),
                   fingerprint(self.hd_kevin): (fingerprint(self.sd_kevin),)},
            SD_OF_EPISODE={'hd_12_7': {fingerprint(self.hd_viv): (fingerprint(self.sd_viv), True)}},
            REDESIGNED=frozenset({fingerprint(self.sd_viv), fingerprint(self.sd_kevin)}),
            BANK_PORTRAITS=frozenset())

    def library(self, addon=None, revision=1):
        return Library(self.root, {
            'hd_12_7': ('hd', {26000: self.hd_viv, 26001: self.hd_kevin}),
            'hd_party_fowl': ('hd', {26000: self.hd_viv}),
            'standard_12_7': ('standard', {26000: self.sd_viv, 26001: self.sd_kevin}),
            'standard_party_fowl': ('standard', {26000: self.sd_patchouli}),
        }, addon=addon, revision=revision)

    def test_an_hd_episode_shows_its_own_storys_original_and_another_story_its_own(self):
        library = self.library()
        build_from_map(library, self.map)
        store = library.sd_portraits_store()
        self.assertEqual(store.original('hd_12_7', fingerprint(self.hd_viv)), (self.sd_viv, True))
        self.assertEqual(store.original('hd_party_fowl', fingerprint(self.hd_viv)), (self.sd_patchouli, False))

    def test_everywhere_redesigns_only_and_off_in_an_hd_episode(self):
        library = self.library()
        build_from_map(library, self.map)
        episode = resources(library, 'hd_party_fowl', 'hd', {26000: self.hd_viv})
        self.assertIsNone(episode._sd_original(self.hd_viv))                  # Off
        library.sd_portraits = 'all'
        shown = Image.open(BytesIO(episode._sd_original(self.hd_viv)))
        self.assertEqual(shown.size, (128, 128))                              # the original at twice its size
        self.assertEqual(shown.convert('RGB').getpixel((5, 5)), (255, 165, 0))
        library.sd_portraits = 'redesigns'
        self.assertIsNone(episode._sd_original(self.hd_viv))                  # Patchouli's pair is a redraw
        own = resources(library, 'hd_12_7', 'hd', {26000: self.hd_viv})
        self.assertIsNotNone(own._sd_original(self.hd_viv))                   # Viv's is a redesign

    def test_a_standard_episode_keeps_its_own_portrait_instead_of_the_twin(self):
        library = self.library()
        build_from_map(library, self.map)
        episode = resources(library, 'standard_12_7', 'standard', {})
        self.assertFalse(episode._keeps_standard_portrait(self.sd_kevin))
        library.sd_portraits = 'redesigns'
        self.assertTrue(episode._keeps_standard_portrait(self.sd_kevin))
        self.assertFalse(episode._keeps_standard_portrait(png((480, 720), 'blue')))    # a background stays HD

    def test_an_original_only_the_add_on_holds_is_found_and_the_add_on_triggers_a_rebuild(self):
        library = self.library()
        library._assets['standard_party_fowl'] = {}                          # the player lacks that standard episode
        build_from_map(library, self.map)
        self.assertEqual(library.sd_portraits_store().original('hd_party_fowl', fingerprint(self.hd_viv)), None)
        self.assertFalse(sd_portraits_due(library, self.map))
        with_addon = self.library(addon={26000: self.sd_patchouli})
        with_addon._assets['standard_party_fowl'] = {}
        self.assertTrue(sd_portraits_due(with_addon, self.map))             # the add-on arrived: rebuild the originals
        self.assertTrue(build_from_map(with_addon, self.map))
        found = with_addon.sd_portraits_store().original('hd_party_fowl', fingerprint(self.hd_viv))
        self.assertEqual(found, (self.sd_patchouli, False))
        self.assertIsNotNone(with_addon.twin_store().twin(self.sd_viv))     # the twins were not rebuilt for it

    def test_an_episode_imported_after_the_build_adds_its_art_without_a_rebuild(self):
        # Owner, 2026-11-25: a standard episode imported after the update gets its originals (and twins) at once.
        from exp_runtime.hd_twins import new_episodes
        library = self.library()
        later = library.episodes.pop(next(i for i, r in enumerate(library.episodes) if r['id'] == 'standard_party_fowl'))
        build_from_map(library, self.map)
        self.assertIsNone(library.sd_portraits_store().original('hd_party_fowl', fingerprint(self.hd_viv)))
        twins = len(library.twin_store())
        library.episodes.append(later)                                       # imported now
        self.assertEqual([r['id'] for r in new_episodes(library, self.map)], ['standard_party_fowl'])
        self.assertTrue(build_from_map(library, self.map))
        self.assertEqual(library.sd_portraits_store().original('hd_party_fowl', fingerprint(self.hd_viv)),
                         (self.sd_patchouli, False))
        self.assertEqual(len(library.twin_store()), twins)                   # nothing cleared or rebuilt
        self.assertEqual(new_episodes(library, self.map), [])
        self.assertFalse(build_from_map(library, self.map))

    def test_an_effect_picture_is_made_when_its_standard_episode_arrives_later(self):
        from exp_runtime.hd_twins import image_size
        noir_sd = png((48, 72), 'gray')
        stream = BytesIO()
        Image.new('RGB', (96, 144), (200, 60, 30)).save(stream, 'PNG')
        noir_hd = stream.getvalue()
        self.map.TWINS[fingerprint(noir_sd)] = (fingerprint(noir_hd), 48, 72, ('E',))
        library = self.library()
        library._assets['hd_12_7'][26002] = noir_hd                          # the HD half, in an episode already held
        build_from_map(library, self.map)
        self.assertIsNone(library.twin_store().twin(noir_sd))                 # its standard episode isn't here yet
        library._assets['standard_noir'] = {26000: noir_sd}
        library.episodes.append(dict(id='standard_noir', name='standard_noir', variant='standard'))
        self.assertTrue(build_from_map(library, self.map))
        made = library.twin_store().twin(noir_sd)
        self.assertIsNotNone(made)
        self.assertEqual(image_size(made), (96, 144))
        r, g, b = Image.open(BytesIO(made)).convert('RGB').getpixel((40, 70))
        self.assertLess(max(r, g, b) - min(r, g, b), 12)                      # greyscale, as the standard picture

    def test_adding_the_add_on_reads_only_the_add_on_and_removing_it_gathers_again(self):
        library = self.library()
        library._assets['standard_party_fowl'] = {}
        build_from_map(library, self.map)
        held = len(library.sd_portraits_store().pictures.index)
        with_addon = self.library(addon={26000: self.sd_patchouli})
        with_addon._assets['standard_party_fowl'] = {}
        opened = []
        real_open = with_addon.open_episode
        with_addon.open_episode = lambda key: opened.append(key) or real_open(key)
        self.assertTrue(build_from_map(with_addon, self.map))
        self.assertEqual(opened, [])                                         # the add-on alone was read
        self.assertEqual(len(with_addon.sd_portraits_store().pictures.index), held + 1)
        without = self.library()                                             # removed: gathered again from everything
        without._assets['standard_party_fowl'] = {}
        self.assertTrue(sd_portraits_due(without, self.map))
        build_from_map(without, self.map)
        self.assertIsNone(without.sd_portraits_store().original('hd_party_fowl', fingerprint(self.hd_viv)))

    def test_a_redesign_tagged_on_its_hd_picture_leaves_a_shared_original_plain_elsewhere(self):
        # 10_2's costume Ben (hd/0404) and plain HD Ben (hd/0425) both go back to sd/0512: only the costume is a
        # redesign, so the tag is on its HD picture (owner, 2026-11-25).
        costume, plain = png((128, 128), 'purple'), png((128, 128), 'navy')
        ben = png((64, 64), 'teal')
        self.map.SD_OF[fingerprint(costume)] = (fingerprint(ben),)
        self.map.SD_OF[fingerprint(plain)] = (fingerprint(ben),)
        self.map.REDESIGNED = frozenset(self.map.REDESIGNED | {fingerprint(costume)})
        library = self.library()
        library._assets['standard_12_7'][26002] = ben
        build_from_map(library, self.map)
        library.sd_portraits = 'redesigns'
        episode = resources(library, 'hd_party_fowl', 'hd', {})
        self.assertIsNotNone(episode._sd_original(costume))                 # the costume goes back to SD Ben
        self.assertIsNone(episode._sd_original(plain))                      # plain Ben stays HD
        standard = resources(library, 'standard_12_7', 'standard', {})
        self.assertFalse(standard._keeps_standard_portrait(ben))           # a standard episode shows plain Ben's twin

    def tinted_map(self):
        """The noir pair: a greyscale standard scene and its colour HD picture, which one HD episode (its own story's)
        lists as tinted and another story shows as it is."""
        noir_sd = png((48, 72), 'gray')
        stream = BytesIO()
        Image.new('RGB', (96, 144), (200, 60, 30)).save(stream, 'PNG')
        noir_hd = stream.getvalue()
        self.map.TWINS[fingerprint(noir_sd)] = (fingerprint(noir_hd), 48, 72, ('E',))
        self.map.TINTS_OF_EPISODE = {'hd_12_7': {26002: fingerprint(noir_sd)}}
        return noir_sd, noir_hd

    def test_sd_background_tints_show_the_tinted_scene_only_where_its_story_had_it(self):
        noir_sd, noir_hd = self.tinted_map()
        library = self.library(addon={26000: self.sd_patchouli, 26001: noir_sd})   # the add-on carries the standard
        library._assets['hd_12_7'][26002] = noir_hd
        library._assets['hd_party_fowl'][26002] = noir_hd                          # another story's same picture
        build_from_map(library, self.map)
        own = resources(library, 'hd_12_7', 'hd', {26002: noir_hd})
        other = resources(library, 'hd_party_fowl', 'hd', {26002: noir_hd})
        self.assertIsNone(own._sd_tint(26002))                                     # the switch is off
        library.sd_tints = True
        tinted = own._sd_tint(26002)
        self.assertIsNotNone(tinted)
        r, g, b = Image.open(BytesIO(tinted)).convert('RGB').getpixel((40, 70))
        self.assertLess(max(r, g, b) - min(r, g, b), 12)                           # greyscale, as the standard scene
        self.assertIsNone(other._sd_tint(26002))                                   # not that story's scene
        self.assertIsNone(own._sd_tint(26003))                                     # nor another scene

    def test_adding_the_add_on_makes_the_tinted_pictures_it_carries_the_standard_for(self):
        noir_sd, noir_hd = self.tinted_map()
        library = self.library()
        library._assets['hd_12_7'][26002] = noir_hd
        build_from_map(library, self.map)
        self.assertIsNone(library.twin_store().twin(noir_sd))                      # no standard picture yet
        with_addon = self.library(addon={26000: noir_sd})
        with_addon._assets['hd_12_7'][26002] = noir_hd
        self.assertTrue(build_from_map(with_addon, self.map))
        self.assertIsNotNone(with_addon.twin_store().twin(noir_sd))

    def test_a_store_built_before_the_searched_list_takes_the_library_as_searched(self):
        from exp_runtime.hd_twins import new_episodes
        library = self.library()
        build_from_map(library, self.map)
        library.twin_store().mark_source(self.map.VERSION)                    # as tools/export_hd_twin_map.py marks it
        self.assertEqual(new_episodes(library, self.map), [])
        self.assertEqual(len(library.twin_store().source()['episodes']), 4)    # written once, for the next import

    def test_a_strict_episode_original_never_falls_back_to_another_look(self):
        library = self.library()
        library._assets['standard_12_7'] = {26001: self.sd_kevin}           # Viv's own original is missing
        build_from_map(library, self.map)
        self.assertIsNone(library.sd_portraits_store().original('hd_12_7', fingerprint(self.hd_viv)))


class SettingTests(unittest.TestCase):
    def test_extras_lists_sd_portraits_as_a_choice(self):
        from exp_runtime.desktop_pause_hd import CHOICE_PARENTS, SD_PORTRAITS_LABEL, SD_PORTRAITS_NAMES
        self.assertEqual(SD_PORTRAITS_NAMES, {'off': 'Off', 'all': 'Everywhere', 'redesigns': 'Redesigns Only'})
        self.assertEqual(CHOICE_PARENTS['sd_portraits'], 'options:extras')
        self.assertEqual(SD_PORTRAITS_LABEL, 'SD Portraits')

    def test_extras_has_sd_background_tints_as_a_switch_kept_and_off_by_default(self):
        from exp_runtime.desktop_pause_hd import EXTRAS_KEYS, SD_TINTS_LABEL
        from exp_runtime.menu import SHARED_PREFERENCES, MenuState
        self.assertIn('sd_tints', EXTRAS_KEYS)
        self.assertEqual(SD_TINTS_LABEL, 'SD Background Tints')
        self.assertIs(SHARED_PREFERENCES['sd_tints'], bool)
        self.assertFalse(MenuState.__new__(MenuState).__dict__.get('sd_tints', False))

    def test_the_setting_is_kept_and_defaults_to_off(self):
        from exp_runtime.menu import SHARED_PREFERENCES
        import exp_runtime.menu as menu
        source = Path(menu.__file__).read_text(encoding='utf-8')
        self.assertIn("self.sd_portraits = 'off'", source)
        self.assertIn("sd_portraits=self.sd_portraits", source)
        self.assertIn('sd_portraits', SHARED_PREFERENCES)


if __name__ == '__main__':
    unittest.main()
