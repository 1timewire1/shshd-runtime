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

    def test_the_setting_is_kept_and_defaults_to_off(self):
        from exp_runtime.menu import SHARED_PREFERENCES
        import exp_runtime.menu as menu
        source = Path(menu.__file__).read_text(encoding='utf-8')
        self.assertIn("self.sd_portraits = 'off'", source)
        self.assertIn("sd_portraits=self.sd_portraits", source)
        self.assertIn('sd_portraits', SHARED_PREFERENCES)


if __name__ == '__main__':
    unittest.main()
