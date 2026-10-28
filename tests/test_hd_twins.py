"""Higher-density art for standard episodes (`exp_runtime.hd_twins`), on authored pictures."""
import io
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from exp_runtime import hd_twins
from exp_runtime.content import EpisodeResources
from exp_runtime.hd_twins import (ArtMatch, TwinStore, best_by_source_count, fingerprint, image_size,
                                  is_flat_capture, is_twin, is_upgraded, names_compatible, pair_art,
                                  pair_art_detailed, upscale)


def picture(size, color=(200, 30, 30, 255), kind='PNG'):
    out = io.BytesIO()
    Image.new('RGBA' if kind == 'PNG' else 'RGB', size, color if kind == 'PNG' else color[:3]).save(out, kind)
    return out.getvalue()


def photo(size, tint=(0, 0, 0)):
    """Four colored quadrants upscaled to `size`, tinted -- real spatial content (unlike `picture`'s flat fill), so
    two same-pattern pictures correlate the way a real background and its resampled HD twin would."""
    quadrants = [(40, 40, 200), (200, 40, 40), (40, 200, 40), (200, 200, 40)]
    base = Image.new('RGB', (2, 2))
    for index, color in enumerate(quadrants):
        base.putpixel((index % 2, index // 2), tuple(min(255, c + t) for c, t in zip(color, tint)))
    out = io.BytesIO()
    base.resize(size, Image.NEAREST).convert('RGBA').save(out, 'PNG')
    return out.getvalue()


def similar_photo(size):
    """Two of `photo`'s own quadrants, paired with two unrelated colors -- a different picture that still
    correlates moderately with `photo`'s (real content: two establishing shots of the same set), unlike an
    unrelated photo's near-zero correlation."""
    quadrants = [(40, 40, 200), (200, 40, 40), (10, 90, 150), (150, 90, 10)]
    base = Image.new('RGB', (2, 2))
    for index, color in enumerate(quadrants):
        base.putpixel((index % 2, index // 2), color)
    out = io.BytesIO()
    base.resize(size, Image.NEAREST).convert('RGBA').save(out, 'PNG')
    return out.getvalue()


class PictureTests(unittest.TestCase):
    def test_sizes_are_read_from_png_and_jpeg_headers(self):
        self.assertEqual(image_size(picture((110, 125))), (110, 125))
        self.assertEqual(image_size(picture((64, 48), kind='JPEG')), (64, 48))
        self.assertIsNone(image_size(b'kiwi program bytes'))

    def test_a_flat_capture_is_told_apart_from_a_real_resampled_photo(self):
        # A corrupt or truncated extraction that decodes to a solid wash must not pass as a background's HD twin,
        # even though it is exactly the right size (see 12_3_Howards_Last_Day's black id 26116 in legacy/findings.md).
        standard = photo((480, 720), (3, 3, 3))
        self.assertFalse(is_flat_capture(standard, photo((960, 1440), (9, 3, 3))))    # a real (tinted) resample
        self.assertTrue(is_flat_capture(standard, picture((960, 1440), (0, 0, 0, 255))))  # solid black: corrupt
        self.assertTrue(is_flat_capture(standard, picture((960, 1440), (250, 10, 10, 255))))  # unrelated content
        # Both sides genuinely flat and the same color (a fade-to-black/white transition frame, seen in
        # 10_1_300s_A_Crowd's and 1_1_Magic_School's own #26055/#26001) is a real match, not a corrupt capture --
        # a flat picture has no variance for Pearson correlation to compare, so this needs its own rule.
        flat_black = picture((480, 720), (0, 0, 0, 255))
        self.assertFalse(is_flat_capture(flat_black, picture((960, 1440), (0, 0, 0, 255))))
        self.assertTrue(is_flat_capture(flat_black, picture((960, 1440), (255, 255, 255, 255))))

    def test_names_compatible_allows_a_shorter_title_of_the_same_fuller_name(self):
        # Real content: 75_Anger_Management's own "Coach"/"Coach Kessler" and 19_flex_games' own "Judge"/"Judge
        # Tigh" are the same character at the same id, one release just using a fuller name than the other.
        self.assertTrue(names_compatible('Coach', 'Coach Kessler'))
        self.assertTrue(names_compatible('Judge Tigh', 'Judge'))          # order-independent
        self.assertTrue(names_compatible('Amanda', 'Amanda'))
        self.assertFalse(names_compatible('Colt', 'Coltrane'))            # a shared prefix, not a shared title
        self.assertFalse(names_compatible('Colt', 'Jeeves'))

    def test_a_twin_is_about_twice_the_picture_each_way(self):
        standard = picture((113, 128))
        self.assertTrue(is_twin(standard, picture((226, 256))))
        self.assertTrue(is_twin(standard, picture((199, 256))))         # HD sprites are padded differently
        self.assertFalse(is_twin(standard, picture((113, 128))))         # the same size is no upgrade
        self.assertFalse(is_twin(standard, picture((480, 720))))         # another picture under the same id
        self.assertFalse(is_twin(standard, b'not an image'))

    def test_an_upgrade_need_not_keep_the_standard_pictures_aspect_ratio(self):
        # A portrait's identity is confirmed some other way (a name) before this check runs, so it can afford to
        # accept an HD redraw that grew unevenly (real content: 68_spring_Break's own "Angie", 128x128 -> 168x256,
        # where only the height comes close to doubling -- `is_twin`'s proportional band rejects it outright).
        standard = picture((128, 128))
        self.assertTrue(is_upgraded(standard, picture((168, 256))))
        self.assertTrue(is_upgraded(standard, picture((226, 256))))       # a proportional twin still passes
        self.assertFalse(is_upgraded(standard, picture((128, 128))))      # the same size is still no upgrade
        self.assertFalse(is_upgraded(standard, picture((140, 140))))      # barely bigger is noise, not a redraw
        self.assertFalse(is_upgraded(standard, picture((600, 600))))      # implausibly large: not the same picture

    def test_scaling_doubles_a_picture_and_leaves_what_it_cannot_read(self):
        self.assertEqual(image_size(upscale(picture((30, 40)))), (60, 80))
        self.assertEqual(upscale(b'kiwi'), b'kiwi')


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.standard, self.hd = picture((100, 120)), picture((200, 240), (10, 200, 10, 255))
        self.store = TwinStore(Path(self.temporary.name))
        self.store.write({fingerprint(self.standard): (self.standard, self.hd)})

    def test_a_picture_with_a_twin_is_served_as_the_twin_in_twins_and_fill_modes(self):
        self.assertEqual(self.store.art(self.standard, 'twins'), self.hd)
        self.assertEqual(self.store.art(self.standard, 'fill'), self.hd)
        self.assertEqual(self.store.art(self.standard, 'off'), self.standard)
        self.assertEqual(len(TwinStore(Path(self.temporary.name))), 1)   # and it is on disk for the next run

    def test_a_picture_without_one_is_scaled_only_in_fill_mode(self):
        other = picture((50, 60), (1, 2, 3, 255))
        self.assertEqual(self.store.art(other, 'twins'), other)
        self.assertEqual(image_size(self.store.art(other, 'fill')), (100, 120))
        self.assertEqual(self.store.art(b'kiwi program', 'fill'), b'kiwi program')     # scripts and other data untouched

    def test_a_picture_already_hd_in_a_standard_file_is_not_doubled_again(self):
        pool, portrait = picture((960, 1440), (1, 2, 3, 255)), picture((226, 256), (1, 2, 3, 255))
        self.assertEqual(self.store.art(pool, 'fill'), pool)                 # Set_12's pool: 12_5's own HD picture
        self.assertEqual(self.store.art(portrait, 'fill'), portrait)
        self.assertEqual(image_size(self.store.art(picture((480, 720)), 'fill')), (960, 1440))   # standard ones still are

    def test_adding_keeps_what_the_store_holds_and_skips_pictures_it_has(self):
        other, other_hd = picture((60, 80), (1, 2, 3, 255)), picture((120, 160), (4, 5, 6, 255))
        added = self.store.add({fingerprint(other): (other, other_hd),
                                fingerprint(self.standard): (self.standard, other_hd)})     # already held: not replaced
        self.assertEqual(added, 1)
        reopened = TwinStore(Path(self.temporary.name))
        self.assertEqual((len(reopened), reopened.twin(other), reopened.twin(self.standard)), (2, other_hd, self.hd))

    def test_a_confirmed_correction_replaces_or_removes_a_held_pair(self):
        other, other_hd = picture((60, 80), (1, 2, 3, 255)), picture((120, 160), (4, 5, 6, 255))
        self.store.add({fingerprint(other): (other, other_hd)})
        better = picture((200, 240), (7, 8, 9, 255))
        key = fingerprint(self.standard)
        changed = self.store.add({key: (self.standard, better)}, replace={key}, remove={fingerprint(other)})
        self.assertEqual(changed, 2)
        reopened = TwinStore(Path(self.temporary.name))
        self.assertEqual((len(reopened), reopened.twin(self.standard), reopened.twin(other)), (1, better, None))
        self.assertEqual(reopened.add({key: (self.standard, better)}, replace={key}), 0)   # already that picture

    def test_a_missing_store_is_empty(self):
        self.assertEqual(len(TwinStore(Path(self.temporary.name) / 'nowhere')), 0)

    def test_coverage_round_trips_and_is_absent_for_an_unmeasured_episode(self):
        self.store.write_coverage({'abc': {'total': 5, 'matched': 3}})
        self.assertEqual(self.store.coverage('abc'), (5, 3))
        self.assertIsNone(self.store.coverage('never measured'))
        self.assertEqual(TwinStore(Path(self.temporary.name)).coverage('abc'), (5, 3))   # and it is on disk


class Archive:
    def __init__(self, assets):
        self.assets = assets

    @property
    def entries(self):
        return self.assets

    def programs(self):
        return {}

    def read(self, resource_id):
        return self.assets[resource_id]


class ResourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.standard, self.hd = picture((100, 120)), picture((200, 240), (10, 200, 10, 255))
        store = TwinStore(Path(self.temporary.name))
        store.write({fingerprint(self.standard): (self.standard, self.hd)})
        self.library = SimpleNamespace(hd_art_mode='fill', twin_store=lambda: store, read_asset=lambda rid: b'base %d' % rid,
                                       hd_asset=lambda rid: None, android_asset=lambda rid: b'base %d' % rid)

    def resources(self, variant, mode='fill'):
        self.library.hd_art_mode = mode
        return EpisodeResources(self.library, dict(variant=variant), Archive({26000: self.standard, 26001: picture((20, 20))}))

    def test_only_a_standard_episodes_own_art_is_substituted(self):
        self.assertEqual(self.resources('standard').read_asset(26000), self.hd)
        self.assertEqual(self.resources('hd').read_asset(26000), self.standard)             # an HD episode is left alone
        self.assertEqual(self.resources('standard', 'off').read_asset(26000), self.standard)
        self.assertEqual(self.resources('standard').read_asset(1234), b'base 1234')          # not a picture: untouched
        self.assertEqual(image_size(self.resources('standard').read_asset(26001)), (40, 40))

    def test_the_raw_bytes_are_always_available(self):
        self.assertEqual(self.resources('standard').raw_asset(26000), self.standard)

    def test_raw_bytes_for_a_shared_bank_id_skip_any_hd_native_upgrade(self):
        # raw_asset promises the episode's own, never-substituted bytes -- it must not pick up
        # ContentLibrary's own separate hd_asset upgrade for a shared-bank id either.
        self.library.hd_asset = lambda rid: b'should never be seen'
        self.library.android_asset = lambda rid: b'base %d' % rid
        self.assertEqual(self.resources('standard').raw_asset(1234), b'base 1234')

    def test_a_shared_bank_picture_with_a_twin_is_substituted_too(self):
        # A picture below the episode's own 26000 range (the app's shared content bank) can still have a real
        # cross-episode HD twin recorded by content, not just a local one; the substitution must not be limited
        # to ids >= 26000.
        self.library.android_asset = lambda rid: self.standard
        self.assertEqual(self.resources('standard').read_asset(1234), self.hd)

    def test_a_verified_hd_native_upgrade_always_wins_over_the_twin_store(self):
        # ContentLibrary.hd_asset is a separate, already-HD substitution; running its result back through the
        # twin store (especially 'fill') would upscale an already-HD picture a second time.
        upgraded = picture((300, 360), (5, 5, 5, 255))
        self.library.hd_asset = lambda rid: upgraded
        self.assertEqual(self.resources('standard').read_asset(1234), upgraded)


class HiresPortraitTests(unittest.TestCase):
    """A translated New Rules episode (pack 31300) carries the X1i's portraits 1000 above the WinMo ones
    (shs profile TRANSLATED_PORTRAIT_ART); the "Hi-Res Portraits" switch picks between them."""
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.winmo, self.x1i = picture((100, 120)), picture((150, 180), (10, 200, 10, 255))
        store = TwinStore(Path(self.temporary.name))
        store.write({fingerprint(self.winmo): (self.winmo, picture((200, 240)))})
        self.library = SimpleNamespace(game_id='shs', hires_portraits=True, hd_art_mode='fill', twin_store=lambda: store,
                                       hd_asset=lambda rid: None, android_asset=lambda rid: b'base %d' % rid)

    def resources(self, pack=31300, assets=None):
        assets = {26200: self.winmo, 27200: self.x1i, 26999: self.winmo} if assets is None else assets
        return EpisodeResources(self.library, dict(variant='standard', pack_id=pack), Archive(assets))

    def test_the_hires_portrait_is_shown_as_it_is_without_the_twin_store(self):
        self.assertEqual(self.resources().read_asset(26200), self.x1i)

    def test_the_hires_portrait_names_the_portrait_it_stands_in_for(self):
        self.assertEqual(self.resources().standard_portrait(26200), self.winmo)       # the player sizes it to this
        self.assertIsNone(self.resources().standard_portrait(26999))
        self.library.hires_portraits = False
        self.assertIsNone(self.resources().standard_portrait(26200))

    def test_with_the_switch_off_the_episodes_own_portrait_goes_through_the_twin_store(self):
        self.library.hires_portraits = False
        self.assertEqual(image_size(self.resources().read_asset(26200)), (200, 240))

    def test_a_save_loads_with_whichever_portrait_set_is_current(self):
        # A save names the portrait the story set (26200), never the hi-res copy (+1000) the switch reads, and the
        # switch is not part of the save's content identity: a save made with either set opens under the other, and
        # its portrait comes from the set chosen now.
        import json
        from exp_runtime.dialogue_animation import DialoguePortrait
        from exp_runtime.runtime import Session
        from test_runtime import Resources, host_call, text_words
        from test_vm import program
        words, (line,) = text_words('Hello there.')
        story = Resources(program(*host_call(72, 3, 26200), *host_call(13, line, 3, 2), 0x33, words=words))
        session = Session(story)
        session.advance()
        saved = json.dumps(session.snapshot())
        self.assertIn('26200', saved)
        self.assertNotIn('27200', saved)
        restored = Session.from_snapshot(story, json.loads(saved))
        portrait = DialoguePortrait.from_details(restored.pending.details, restored.engine.character_art_variants)
        self.assertEqual(portrait.asset_id, 26200)
        self.library.profile, self.library.kind, self.library.manifest = 'test', 'apk', {'apk': {'sha256': 'a' * 64}}
        episode = self.resources()
        episode.record['sha256'] = 'b' * 64
        for enabled, expected in ((True, (150, 180)), (False, (200, 240)), (True, (150, 180))):
            self.library.hires_portraits = enabled
            self.assertEqual(episode.identity, dict(profile='test', episode_sha256='b' * 64, apk_sha256='a' * 64))
            self.assertEqual(image_size(episode.read_asset(portrait.asset_id)), expected)

    def test_only_the_portrait_range_of_a_translated_pack_is_moved(self):
        self.assertEqual(image_size(self.resources().read_asset(26999)), (200, 240))         # its backdrop
        self.assertEqual(image_size(self.resources(pack=1).read_asset(26200)), (200, 240))   # another pack
        self.assertEqual(image_size(self.resources(assets={26200: self.winmo}).read_asset(26200)), (200, 240))


class PairingTests(unittest.TestCase):
    def test_the_art_two_releases_register_identically_is_paired_and_the_rest_is_not(self):
        std_bytes = {26000: picture((113, 128), (1, 1, 1, 255)), 26001: picture((113, 128), (2, 2, 2, 255)),
                     26010: photo((480, 720), (3, 3, 3)), 26020: picture((60, 60), (4, 4, 4, 255)), 500: b'base'}
        hd_bytes = {26000: picture((226, 256), (9, 1, 1, 255)), 26001: picture((113, 128), (9, 2, 2, 255)),
                    26010: photo((960, 1440), (9, 3, 3)), 26020: picture((500, 500), (9, 4, 4, 255)), 500: b'base'}

        def resources(assets):
            return SimpleNamespace(raw_asset=lambda rid: assets[rid])
        seen = {}

        def collect(res, *_):
            return seen[id(res)]
        standard, hd = resources(std_bytes), resources(hd_bytes)
        seen[id(standard)] = ({7: [500, 26000, 26001], 8: [26020]}, {26010, 500}, {})
        seen[id(hd)] = ({7: [500, 26000, 26001], 8: [26020]}, {26010, 500}, {})
        with patch.object(hd_twins, 'collect_art', collect):
            found = pair_art(standard, hd)
        self.assertEqual(sorted(found), sorted(fingerprint(std_bytes[i]) for i in (26000, 26010)))   # 26001: same size; 26020: not a twin; 500: shared bank
        self.assertEqual(found[fingerprint(std_bytes[26010])][1], hd_bytes[26010])

    def test_a_character_registered_with_a_different_number_of_expressions_is_not_paired(self):
        assets = {26000: picture((10, 10)), 26001: picture((20, 20))}
        res = SimpleNamespace(raw_asset=lambda rid: assets[rid])
        answers = iter([({1: [26000]}, set(), {}), ({1: [26001, 26001]}, set(), {})])
        with patch.object(hd_twins, 'collect_art', lambda *_: next(answers)):
            self.assertEqual(pair_art(res, res), {})

    def test_a_shared_id_naming_two_different_people_is_recovered_by_name_instead(self):
        # Real content (9_4_This_is_Spartan): the standard release has three ids all named "Colt" (3, 4, 5); the
        # HD release folds one away, so its own id 5 is "Jeeves" instead and everything past it is off by one.
        # Matching id 5 to id 5 anyway (as a numeric-only pairing would) hands Colt's picture a stranger's HD art;
        # the fix must refuse that pairing and instead find HD's *own* Jeeves (id 5) by name for the standard
        # release's *own* Jeeves (id 6), leaving Colt's spare third id honestly unpaired.
        colt_a, colt_b, colt_c, jeeves = (picture((113, 128), (n, n, n, 255)) for n in (1, 2, 3, 4))
        hd_colt_a, hd_colt_b, hd_jeeves = (picture((226, 256), (n, n, n, 255)) for n in (9, 8, 7))
        std_assets = {26000: colt_a, 26001: colt_b, 26002: colt_c, 26003: jeeves}
        hd_assets = {26010: hd_colt_a, 26011: hd_colt_b, 26012: hd_jeeves}

        def resources(assets):
            return SimpleNamespace(raw_asset=lambda rid: assets[rid])
        standard, hd = resources(std_assets), resources(hd_assets)
        std_result = ({3: [26000], 4: [26001], 5: [26002], 6: [26003]}, set(),
                     {3: 'Colt', 4: 'Colt', 5: 'Colt', 6: 'Jeeves'})
        hd_result = ({3: [26010], 4: [26011], 5: [26012]}, set(), {3: 'Colt', 4: 'Colt', 5: 'Jeeves'})
        answers = iter([std_result, hd_result])
        with patch.object(hd_twins, 'collect_art', lambda *_: next(answers)):
            matches, unpaired_std, unpaired_hd = pair_art_detailed(standard, hd)

        paired = {m.std_id: m.hd_id for m in matches}
        self.assertEqual(paired, {26000: 26010, 26001: 26011, 26003: 26012})   # not 26002 -> 26012 by raw id
        self.assertEqual([m.hd_name for m in matches if m.std_id == 26003], ['Jeeves'])
        self.assertEqual([(u.id, u.name) for u in unpaired_std], [(26002, 'Colt')])
        self.assertEqual(unpaired_hd, [])

    def test_a_background_renumbered_between_releases_is_recovered_by_content_not_a_similar_looking_one(self):
        # Real content (4_8_Sectionals, 5_3_Paigeagainstthemachine): a background can be renumbered between
        # releases with no overlapping id at all, so it must be recovered by content. But two different
        # establishing shots of the same set can still correlate moderately (a leftover background the standard
        # release never upgraded, `std_b`/`hd_b`, sized like a real twin next to `std_a` purely by coincidence) --
        # too low a floor would make that a second "candidate" and leave `std_a`'s real match unrecovered too.
        std_a, hd_a = photo((480, 720), (1, 0, 0)), photo((960, 1440), (9, 1, 0))    # a real twin, renumbered
        std_b = hd_b = similar_photo((960, 1440))       # already HD-sized on the standard side: no real upgrade
        std_assets = {26010: std_a, 26011: std_b}
        hd_assets = {26099: hd_a, 26100: hd_b}

        def resources(assets):
            return SimpleNamespace(raw_asset=lambda rid: assets[rid])
        standard, hd = resources(std_assets), resources(hd_assets)
        answers = iter([({}, {26010, 26011}, {}), ({}, {26099, 26100}, {})])
        with patch.object(hd_twins, 'collect_art', lambda *_: next(answers)):
            matches, unpaired_std, unpaired_hd = pair_art_detailed(standard, hd)

        self.assertEqual([(m.std_id, m.hd_id) for m in matches], [(26010, 26099)])   # not 26100, despite correlating
        self.assertEqual([u.id for u in unpaired_std], [26011])
        self.assertEqual([u.id for u in unpaired_hd], [26100])

    def test_the_most_agreed_on_hd_twin_wins_not_whichever_story_built_first(self):
        # Real content (11_0_April_Fools): its own "Monkey" costume happens to share its SD bytes with several
        # other episodes' "Amanda" (a bunny costume) -- one SD picture, two different, correctly redrawn HD
        # identities depending on the story. `pair_art`'s own per-pair contract (first found wins) would let
        # whichever story is built first -- an accident of processing order, confirmed to land on "Monkey" in the
        # real library, alphabetically before every "Amanda" episode -- paint every other story's Amanda too.
        std_bytes, monkey_bytes = picture((113, 128), (1, 1, 1, 255)), picture((226, 256), (9, 1, 1, 255))
        amanda_bytes = picture((226, 256), (9, 2, 2, 255))
        monkey = ArtMatch(26006, 30006, std_bytes, monkey_bytes, 'portrait', 43, 'Monkey', 'Monkey')
        amandas = [ArtMatch(26077, 40077, std_bytes, amanda_bytes, 'portrait', 12, 'Amanda', 'Amanda')
                  for _ in range(3)]
        found = best_by_source_count([monkey, *amandas])
        self.assertEqual(found, {fingerprint(std_bytes): (std_bytes, amanda_bytes)})

    def test_a_fuller_hd_name_at_the_same_id_still_lines_up_directly(self):
        # Real content (75_Anger_Management, 19_flex_games): the same character at the same id can be "Coach" on
        # the standard side and "Coach Kessler" on the HD side -- not the Colt/Jeeves case of two different
        # people, so this must still line up directly rather than fall back to (fruitless) name recovery.
        std_bytes, hd_bytes = picture((113, 128), (1, 1, 1, 255)), picture((226, 256), (9, 1, 1, 255))
        std_assets, hd_assets = {26000: std_bytes}, {26000: hd_bytes}

        def resources(assets):
            return SimpleNamespace(raw_asset=lambda rid: assets[rid])
        standard, hd = resources(std_assets), resources(hd_assets)
        answers = iter([({4: [26000]}, set(), {4: 'Coach'}), ({4: [26000]}, set(), {4: 'Coach Kessler'})])
        with patch.object(hd_twins, 'collect_art', lambda *_: next(answers)):
            matches, unpaired_std, unpaired_hd = pair_art_detailed(standard, hd)

        self.assertEqual([(m.std_id, m.hd_id, m.std_name, m.hd_name) for m in matches],
                         [(26000, 26000, 'Coach', 'Coach Kessler')])
        self.assertEqual(unpaired_std, [])
        self.assertEqual(unpaired_hd, [])


if __name__ == '__main__':
    unittest.main()
