from types import SimpleNamespace
import struct
import unittest

from exp_runtime.episode_catalog import CatalogEntry, EpisodeCatalog
from exp_runtime import episode_index as ei


def words(text):
    data = text.encode('ascii')
    data += b'\0' * (len(data) % 2)
    return tuple(int.from_bytes(data[i:i + 2], 'big') for i in range(0, len(data), 2))


def programs(*lines):
    return {index: SimpleNamespace(main_words=words(line)) for index, line in enumerate(lines)}


def png(width, height=10):
    return b'\x89PNG\r\n\x1a\n' + struct.pack('>I', 13) + b'IHDR' + struct.pack('>II', width, height)


class FakeArchive:
    def __init__(self, *sizes):
        self.entries = {index: None for index in range(len(sizes))}
        self.data = {index: png(*size) if isinstance(size, tuple) else png(size) for index, size in enumerate(sizes)}

    def read(self, resource_id):
        return self.data[resource_id]


def record(identity, pack, episode, title, *, variant=None, signature='', name=None):
    return dict(id=f'{identity:064x}', pack_id=pack, episode_id=episode, titles=[title] * 5, variant=variant,
                signature=signature, name=name or f'{identity}.exp')


def entry(pack, episode, title, category, source, filename=''):
    return CatalogEntry(pack, episode, title, category, filename, source)


STORY = tuple(f'a line of dialogue number {n} in the story' for n in range(40))


class SignatureTests(unittest.TestCase):
    def test_identical_text_overlaps_fully_and_unrelated_text_not_at_all(self):
        a = ei.script_signature(programs(*STORY))
        b = ei.script_signature(programs(*STORY))
        c = ei.script_signature(programs(*(f'a completely different sentence {n} here' for n in range(40))))
        self.assertEqual(ei.signature_overlap(a, b), 1.0)
        self.assertEqual(ei.signature_overlap(a, c), 0.0)
        self.assertEqual(ei.signature_overlap(a, ''), 0.0)

    def test_small_edits_keep_a_high_overlap(self):
        edited = STORY[:-1] + ('one line was rewritten in the second release',)
        a = ei.script_signature(programs(*STORY))
        b = ei.script_signature(programs(*edited))
        self.assertGreaterEqual(ei.signature_overlap(a, b), 0.9)

    def test_short_fragments_and_whitespace_do_not_count(self):
        self.assertEqual(ei.script_signature(programs('ab', 'short')), '')
        self.assertEqual(ei.script_signature(programs('same   words  here!')), ei.script_signature(programs('SAME words here!')))


class VariantTests(unittest.TestCase):
    def test_portrait_widths_tell_the_releases_apart(self):
        self.assertEqual(ei.image_variant(FakeArchive(256, 256, 128)), ei.HD)
        self.assertEqual(ei.image_variant(FakeArchive(128, 128, 480)), ei.STANDARD)
        self.assertEqual(ei.image_variant(FakeArchive(400)), ei.STANDARD)
        self.assertIsNone(ei.image_variant(FakeArchive()))
        self.assertIsNone(ei.image_variant(FakeArchive(300)))

    def test_narrower_portraits_are_told_apart_by_their_height(self):
        # Homecoming_Sara_1: fifteen 226 x 256 HD portraits and nothing 256 wide.
        self.assertEqual(ei.image_variant(FakeArchive(*[(226, 256)] * 15)), ei.HD)
        self.assertEqual(ei.image_variant(FakeArchive((113, 128), (113, 128), (96, 128))), ei.STANDARD)

    def test_art_less_episodes_take_the_other_release_of_a_twin_or_the_hd_catalog(self):
        hd_art = record(1, 101, 5, 'Break a Leg', variant='hd')
        bare_twin = record(2, 101, 5, 'Break a Leg')
        listed_hd = record(3, 201, 30, 'Only in the HD list')
        listed_both = record(4, 201, 31, 'In both lists')
        unlisted = record(5, 201, 32, 'Nowhere')
        catalog = EpisodeCatalog([entry(201, 30, 'Only in the HD list', 'Season 2', 'hd'),
                                  entry(201, 31, 'In both lists', 'Season 2', 'hd'),
                                  entry(201, 31, 'In both lists', 'SEASON 2', 'standard')])
        variants = ei.resolve_variants([hd_art, bare_twin, listed_hd, listed_both, unlisted], catalog)
        # Twin of an HD episode with art: the twin is the other release.
        self.assertEqual(variants[bare_twin['id']], ei.STANDARD)
        self.assertEqual(variants[hd_art['id']], ei.HD)
        self.assertEqual(variants[listed_hd['id']], ei.HD)
        self.assertEqual(variants[unlisted['id']], ei.STANDARD)
        std_art = record(6, 101, 6, 'The Outcast', variant='standard')
        bare = record(7, 101, 6, 'The Outcast')
        self.assertEqual(ei.resolve_variants([std_art, bare], EpisodeCatalog())[bare['id']], ei.HD)


class DuplicateTests(unittest.TestCase):
    def test_same_ids_and_title_are_one_story_and_the_playable_release_wins(self):
        hd = record(1, 101, 1, 'Making Some Dough', variant='hd')
        standard = record(2, 101, 1, 'Making Some Dough', variant='standard')
        self.assertEqual(ei.duplicates([hd, standard], ei.HD), {standard['id']})
        self.assertEqual(ei.duplicates([hd, standard], ei.STANDARD), {hd['id']})

    def test_different_ids_need_matching_text(self):
        text = ei.script_signature(programs(*STORY))
        other = ei.script_signature(programs(*(f'unrelated sentence number {n} of another story' for n in range(40))))
        a = record(1, 301, 63, 'How to Fight Nerdy', variant='standard', signature=text)
        b = record(2, 401, 63, 'How to Fight Nerdy', variant='hd', signature=text)
        c = record(3, 401, 63, 'How to Fight Nerdy', variant='hd', signature=other)
        self.assertEqual(ei.duplicates([a, b], ei.HD), {a['id']})
        self.assertEqual(ei.duplicates([a, c], ei.HD), set())

    def test_different_titles_and_vote_packs_never_merge(self):
        a = record(1, 7, 2005, 'April Fools', variant='hd')
        b = record(2, 7, 2005, "St. Patrick's Day", variant='standard')
        self.assertEqual(ei.duplicates([a, b], ei.HD), set())
        v1 = record(3, 1000, 3, 'Taylor Large Vote Package', variant='hd', signature='0' * 16)
        v2 = record(4, 3000, 3, 'Taylor Large Vote Package', variant='standard', signature='0' * 16)
        self.assertEqual(ei.duplicates([v1, v2], ei.HD), set())

    def test_a_vote_packs_own_two_releases_still_merge_by_matching_ids(self):
        # Real content: MTX_Dr_Pepper_1 through _5 and Sam3/Sara3/Taylor3/Zoe3 each import an hd and a standard
        # record sharing one (pack, episode) id -- the same specific vote candidate's two releases, not two
        # different candidates sharing a generic title (the case above, which must still never merge).
        hd = record(1, 1000, 3, 'Taylor Large Vote Package', variant='hd')
        standard = record(2, 1000, 3, 'Taylor Large Vote Package', variant='standard')
        self.assertEqual(ei.duplicates([hd, standard], ei.HD), {standard['id']})

    def test_the_same_file_still_merges_with_a_slightly_reworded_hd_title(self):
        # Real content: 13_4_Getting_Over_Howard.exp is "Special: Getting Over Howard" in HD and "Getting Over
        # Howard" standard; MTX_The_Storm_Part_2.exp is "...Part Two" versus "...Part 2" -- the same imported file
        # (matched by name) at the same (pack, episode) id, shown as two separate rows before this merged them
        # despite the differently-worded title. A coincidental (pack, episode) collision between two genuinely
        # different *files* (found in the library: pack 7, episode 2005 is both "April Fools" and, unrelated,
        # "St. Patrick's Day") must still not merge just because the ids happen to match.
        hd = record(1, 1301, 40, 'Special: Getting Over Howard', variant='hd', name='13_4_Getting_Over_Howard.exp')
        standard = record(2, 1301, 40, 'Getting Over Howard', variant='standard', name='13_4_Getting_Over_Howard.exp')
        self.assertEqual(ei.duplicates([hd, standard], ei.HD), {standard['id']})
        unrelated = record(3, 7, 2005, "St. Patrick's Day", name='OMG_St_Patricks_Day.exp')
        april_fools = record(4, 7, 2005, 'April Fools', variant='hd', name='11_0_April_Fools.exp')
        self.assertEqual(ei.duplicates([unrelated, april_fools], ei.HD), set())

    def test_art_less_twin_yields_to_one_with_art_and_bundled_wins_ties(self):
        art = record(1, 5, 9, 'Football Star', variant='hd', name='b.exp')
        bare = record(2, 5, 9, 'Football Star', name='a.exp')
        self.assertEqual(ei.duplicates([bare, art], ei.HD), {bare['id']})
        first = record(3, 5, 10, 'Same', name='b.exp')
        second = record(4, 5, 10, 'Same', name='a.exp')
        self.assertEqual(ei.duplicates([first, second], ei.HD), {first['id']})       # by name
        self.assertEqual(ei.duplicates([first, second], ei.HD, bundled=lambda r: r is first), {second['id']})


class RowTests(unittest.TestCase):
    def rows(self, records, catalog, **options):
        variants = ei.resolve_variants(records, catalog)
        return ei.build_rows(records, variants, catalog, **options)

    def test_categories_title_case_and_are_ordered_by_season(self):
        records = [record(1, 201, 21, 'B', variant='hd'), record(2, 101, 1, 'A', variant='hd'),
                   record(3, 101, 2, 'C', variant='hd')]
        catalog = EpisodeCatalog([entry(201, 21, 'B', 'SEASON 2', 'hd'), entry(101, 1, 'A', 'SEASON 1', 'hd'),
                                  entry(101, 2, 'C', 'SEASON 1', 'hd')])
        rows = self.rows(records, catalog)
        self.assertEqual([r.title for r in rows], ['Season 1', 'Season 2'])
        self.assertEqual([len(r.episodes) for r in rows], [2, 1])

    def test_a_wrong_hd_season_label_falls_back_to_the_standard_catalog(self):
        records = [record(1, 301, 43, 'Sam', variant='hd')]
        catalog = EpisodeCatalog([entry(301, 43, 'Sam', 'Season 1', 'hd'), entry(301, 43, 'Sam', 'SEASON 3', 'standard')])
        self.assertEqual([r.title for r in self.rows(records, catalog)], ['Season 3'])
        # With no other label the pack's own season is used.
        only_hd = EpisodeCatalog([entry(301, 43, 'Sam', 'Season 1', 'hd')])
        self.assertEqual([r.title for r in self.rows(records, only_hd)], ['Season 3'])

    def test_uncatalogued_episodes_use_their_pack_season_and_vote_packs_premium(self):
        records = [record(1, 701, 3, 'Seventh', variant='hd'), record(2, 1000, 1, 'Ballot', variant='hd')]
        titles = [r.title for r in self.rows(records, EpisodeCatalog())]
        self.assertEqual(titles, ['Season 7', 'Premium Content'])

    def test_a_translation_from_another_game_keeps_its_own_category_and_is_never_its_twin(self):
        # shshd-runtime: content.legacy_fields tags "Making Some Dough (SHSNR)" on import and files it under its
        # game's category; it shows beside the smartphone "Making Some Dough" rather than being hidden as a copy.
        text = ei.script_signature(programs(*STORY))
        twin = record(1, 101, 1, 'Making Some Dough', variant='standard', signature=text)
        translated = dict(record(2, 31300, 2, 'Making Some Dough', variant='standard', signature=text),
                          legacy='SHSNR', category='New Rules')
        self.assertFalse(ei.same_story(twin, translated))
        self.assertEqual(ei.duplicates([twin, translated], ei.HD), set())
        catalog = EpisodeCatalog([entry(101, 1, 'Making Some Dough', 'SEASON 1', 'standard')])
        rows = self.rows([twin, translated], catalog)
        self.assertEqual({r.title: len(r.episodes) for r in rows}, {'Season 1': 1, 'New Rules': 1})
        # `order` places an episode by another position than its id: Dancing Queen (101) after King of Diss (1).
        built_in = [dict(record(n, 31300, episode, title), legacy='SHSNR', category='New Rules', **extra)
                    for n, episode, title, extra in ((3, 1, 'King of Diss', {}), (4, 2, 'Making Some Dough', {}),
                                                     (5, 100, 'King of Diss Lite', {}),
                                                     (6, 101, 'Dancing Queen', {'order': 1.5}))]
        row, = self.rows(built_in, EpisodeCatalog())
        self.assertEqual([r['titles'][0] for r in row.episodes],
                         ['King of Diss', 'Dancing Queen', 'Making Some Dough', 'King of Diss Lite'])

    def test_bundled_episodes_are_mega_packs_and_first(self):
        records = [record(1, 101, 1, 'A', variant='hd'), record(2, 5, 9, 'Football', variant='hd')]
        rows = self.rows(records, EpisodeCatalog(), bundled=lambda r: r['pack_id'] == 5)
        self.assertEqual(rows[0].title, 'Mega Packs')

    def test_a_reused_category_splits_by_the_packs_named_seasons(self):
        records = [record(1, 1401, 10, 'One', variant='hd'), record(2, 1501, 10, 'Two', variant='hd'),
                   record(3, 1401, 14000, 'Opener', variant='hd')]
        catalog = EpisodeCatalog([entry(1401, 10, 'One', 'A New Start', 'hd'), entry(1501, 10, 'Two', 'A New Start', 'hd'),
                                  entry(1401, 14000, 'Opener', 'A New Start: Season 2', 'hd'),
                                  entry(1501, 15000, 'Later', 'A New Start: Season 3', 'hd')])
        rows = self.rows(records, catalog)
        self.assertEqual([r.title for r in rows], ['A New Start: Season 2', 'A New Start: Season 3'])
        self.assertEqual([len(r.episodes) for r in rows], [2, 1])

    def test_generic_categories_stay_one_row_and_acronyms_survive(self):
        records = [record(1, 7, 2000, 'One', variant='hd'), record(2, 1201, 6, 'Two', variant='hd'),
                   record(3, 7, 2001, 'Three', variant='hd')]
        catalog = EpisodeCatalog([entry(7, 2000, 'One', 'MTX', 'hd'), entry(1201, 6, 'Two', 'PREMIUM CONTENT', 'hd'),
                                  entry(7, 2001, 'Three', 'PREMIUM CONTENT', 'hd')])
        rows = self.rows(records, catalog)
        self.assertEqual({r.title: len(r.episodes) for r in rows}, {'MTX': 1, 'Premium Content': 2})

    def test_the_premium_alias_joins_premium_content(self):
        records = [record(1, 100, 101, 'Premium thing', variant='standard'), record(2, 1301, 30, 'Other', variant='standard')]
        catalog = EpisodeCatalog([entry(100, 101, 'Premium thing', 'PREMIUM', 'standard'),
                                  entry(1301, 30, 'Other', 'PREMIUM CONTENT', 'standard')])
        self.assertEqual([r.title for r in self.rows(records, catalog)], ['Premium Content'])


class ChronologicalRowTests(unittest.TestCase):
    def test_years_come_first_earliest_first_then_vote_packages_then_bundles(self):
        records = [record(1, 101, 1, 'Later', variant='hd'), record(2, 101, 2, 'Earlier', variant='hd'),
                   record(3, 1000, 1, 'A Vote Pack', variant='hd'), record(4, 1401, 1, 'A Bundle', variant='hd')]
        dates = {'Later': '2013-06-01', 'Earlier': '2010-01-01', 'A Vote Pack': '2011-09-02', 'A Bundle': '2012-09-07'}
        rows = ei.build_chronological_rows(records, dates, redundant_bundles={'A Bundle'}, vote_packages={'A Vote Pack'})
        self.assertEqual([r.title for r in rows], ['2010', '2013', 'Vote Packages', 'Season Bundles'])

    def test_translated_episodes_list_after_the_bundles_whatever_their_twins_aired(self):
        # shshd-runtime: "Making Some Dough" translated from New Rules shares its smartphone twin's title, not its
        # airdate; it lists under Legacy Game Episodes, after Season Bundles and before Date Unknown.
        twin = record(1, 101, 1, 'Making Some Dough', variant='hd')
        translated = [dict(record(n, 31300, episode, title), legacy='SHSNR', category='New Rules', **extra)
                      for n, episode, title, extra in ((2, 2, 'Making Some Dough', {}), (3, 1, 'King of Diss', {}),
                                                       (4, 101, 'Dancing Queen', {'order': 1.5}))]
        undated = record(5, 31400, 1, 'Day of Diss')
        bundle = record(6, 1401, 1, 'A Bundle', variant='hd')
        dates = {'Making Some Dough': '2010-01-01', 'A Bundle': '2012-09-07'}
        rows = ei.build_chronological_rows([twin, *translated, undated, bundle], dates, redundant_bundles={'A Bundle'})
        self.assertEqual([(r.title, [e['titles'][0] for e in r.episodes]) for r in rows],
                         [('2010', ['Making Some Dough']), ('Season Bundles', ['A Bundle']),
                          ('Legacy Game Episodes', ['King of Diss', 'Dancing Queen', 'Making Some Dough']),
                          ('Date Unknown', ['Day of Diss'])])

    def test_a_year_sorts_its_own_episodes_by_date_not_by_pack_id(self):
        records = [record(1, 201, 1, 'Second', variant='hd'), record(2, 101, 1, 'First', variant='hd')]
        dates = {'Second': '2010-02-01', 'First': '2010-01-01'}
        rows = ei.build_chronological_rows(records, dates)
        self.assertEqual([r.title for r in rows], ['2010'])
        self.assertEqual([r['titles'][0] for r in rows[0].episodes], ['First', 'Second'])

    def test_a_sole_source_bundle_stays_in_its_own_year_unless_named_otherwise(self):
        records = [record(1, 1201, 6, 'Season 1: A New Start', variant='standard')]
        dates = {'Season 1: A New Start': '2012-09-05'}
        rows = ei.build_chronological_rows(records, dates, redundant_bundles={'A New Start 2: Howard\'s Return'})
        self.assertEqual([r.title for r in rows], ['2012'])

    def test_an_undated_title_lands_in_its_own_trailing_row_rather_than_vanishing(self):
        records = [record(1, 101, 1, 'Dated', variant='hd'), record(2, 999, 1, 'Undated', variant='hd')]
        rows = ei.build_chronological_rows(records, {'Dated': '2010-01-01'})
        self.assertEqual([r.title for r in rows], ['2010', 'Date Unknown'])
        self.assertEqual(rows[1].episodes[0]['titles'][0], 'Undated')

    def test_empty_trailing_groups_are_left_out_entirely(self):
        records = [record(1, 101, 1, 'Only', variant='hd')]
        rows = ei.build_chronological_rows(records, {'Only': '2010-01-01'}, redundant_bundles={'Nothing here'},
                                           vote_packages={'Nothing here either'})
        self.assertEqual([r.title for r in rows], ['2010'])


class NamingTests(unittest.TestCase):
    def test_labels_follow_the_title_language(self):
        translated = dict(record(1, 101, 10, '10: The Wrong Side of Town'),
                          titles=['10: The Wrong Side of Town', '10 - En territoire hostile', '10: Il quartiere sbagliato',
                                  '10. Falsches Ende der Stadt', ''])
        self.assertEqual([ei.episode_label(translated, language) for language in ('en', 'fr', 'it', 'de', 'es')],
                         ['The Wrong Side of Town', 'En territoire hostile', 'Il quartiere sbagliato',
                          'Falsches Ende der Stadt', 'The Wrong Side of Town'])      # no Spanish title: English

    def test_labels_and_preview_names(self):
        self.assertEqual(ei.episode_label(record(1, 1, 1, '01: Making Some Dough')), 'Making Some Dough')
        self.assertEqual(ei.episode_label(record(1, 1, 1, 'Special: April Fools')), 'Special: April Fools')
        self.assertEqual(ei.episode_label(record(1, 1501, 20, '2: The Dance_Dilemma, Part 1')),
                         'The Dance Dilemma, Part 1')
        # Homecoming_Taylor_2.exp ships titled just "Specials" -- confusing on its own, especially in a list
        # view -- when its three siblings correctly title themselves "<Name> Medium Vote Package".
        self.assertEqual(ei.episode_label(record(1, 1000, 2, 'Specials')), 'Taylor Medium Vote Package')
        # The override keys on (pack_id, episode_id), not the text, since "Specials" isn't a safe text match;
        # a different record that happens to also ship titled "Specials" must not be corrected.
        self.assertEqual(ei.episode_label(record(1, 2000, 2, 'Specials')), 'Specials')
        self.assertEqual(ei.preview_names(record(1, 401, 24, 'x'))[0], 'preview_401_64.jpg')
        self.assertEqual(ei.preview_names(record(1, 5, 9, 'x')), ['preview_1_1.jpg'])
        # Seasons 1-5 number their episodes globally, so a pack that disagrees still finds the preview.
        names = ei.preview_names(record(1, 301, 63, 'x'))
        self.assertIn('preview_401_63.jpg', names)
        self.assertEqual(names[0], 'preview_301_63.jpg')
        self.assertEqual(ei.preview_names(record(1, 1201, 3, 'x')), ['preview_1201_3.jpg'])
        self.assertEqual(ei.preview_names(record(1, 601, 2, 'x')), ['preview_601_2.jpg'])

    def test_format_airdate_as_month_day_year(self):
        self.assertEqual(ei.format_airdate('2009-11-22'), '11/22/2009')

    def test_category_labels_matches_what_build_rows_would_group_each_record_under(self):
        records = [record(1, 101, 1, 'A', variant='hd'), record(2, 201, 1, 'B', variant='hd')]
        catalog = EpisodeCatalog([entry(101, 1, 'A', 'SEASON 1', 'hd'), entry(201, 1, 'B', 'SEASON 2', 'hd')])
        variants = ei.resolve_variants(records, catalog)
        labels = ei.category_labels(records, variants, catalog)
        self.assertEqual(labels, {records[0]['id']: 'Season 1', records[1]['id']: 'Season 2'})

    def test_title_case(self):
        self.assertEqual(ei.title_case('SEASON 2'), 'Season 2')
        self.assertEqual(ei.title_case('MTX'), 'MTX')
        self.assertEqual(ei.title_case("Sara's Classic Set"), "Sara's Classic Set")
        self.assertEqual(ei.title_case('SPECIAL: THE CONNED ARTIST'), 'Special: The Conned Artist')

    def test_catalog_helpers(self):
        catalog = EpisodeCatalog([entry(1401, 14000, 'Season pack', 'A New Start: Season 2', 'hd'),
                                  entry(1401, 10, 'Episode', 'A New Start', 'standard', 'e.exp')])
        self.assertEqual(catalog.pack_title(1401), 'A New Start: Season 2')
        self.assertIsNone(catalog.pack_title(5))
        record_ = record(1, 1401, 10, 'Episode', name='E.exp')
        self.assertEqual(catalog.sources(record_), {'standard'})
        self.assertEqual(catalog.category(record_, source='standard'), 'A New Start')
        self.assertIsNone(catalog.category(record_, source='hd'))
        self.assertEqual(catalog.category(record_), 'A New Start')


if __name__ == '__main__':
    unittest.main()
