"""shshd-runtime: Claire Hart Classic's reader (tools/translate/claire_hart.py, plan Stage 1): looks folded into CoD's 5 slots,
the id table, scene slices at CoD's cut or centred, and the story-object lists, on a small mirror made here."""
import csv
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools' / 'translate'))
HAS_PIL = importlib.util.find_spec('PIL') is not None
CH = 'references/characters/'


def mirror_at(root, portraits=(), scenes=(), cuts=None, cases=None, storyobjs=(), tracks=()):
    """A mirror folder with bundle rows for `portraits`, `storyobjs` and `tracks`, scene folders `scenes` {folder: (w, h,
    names)}, CoD's cut index `cuts` and the case files `cases` {case key: (record, [(epconfig, sequences)])}."""
    from PIL import Image
    root = Path(root)
    rows = []
    for kind, paths in (('portrait', portraits), ('storyobj', storyobjs), ('music', tracks)):
        for number, path in enumerate(paths):
            local = f'raw/{kind}{number}.png'
            rows.append(dict(real_path=path, part='native', kind=kind, local_path=local))
            (root / 'raw').mkdir(parents=True, exist_ok=True)
            Image.new('RGBA', (4, 4), (number, 0, 0, 255)).save(root / local)
    with open(root / 'bundle_names.csv', 'w', encoding='utf-8', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=['real_path', 'part', 'kind', 'local_path'])
        writer.writeheader()
        writer.writerows(rows)
    base = root / 'raw/157/res/raw-assets/references/backgrounds'
    for folder, (width, height, names) in dict(scenes).items():
        (base / folder / 'hd').mkdir(parents=True)
        Image.new('P', (width, height)).save(base / folder / 'hd' / 'template.png')
        (base / folder / 'names.json').write_text(json.dumps({'names': names}))
    (root / 'index').mkdir()
    (root / 'index/bg_vs_template.json').write_text(json.dumps(cuts or {}))
    folder = root / 'unpacked/resources_json/cases'
    folder.mkdir(parents=True)
    caselist = {}
    for key, (record, parts) in (cases or {}).items():
        caselist[key] = dict(record, episodes=[{'name': config.get('title', '').strip()} for config, _ in parts])
        for number, (config, sequences) in enumerate(parts, 1):
            episode = folder / record['case'].replace('CASE ', 'case').replace(' ', '') / f'ep{number}'
            episode.mkdir(parents=True)
            (episode / 'epconfig.json').write_text(json.dumps(config))
            (episode / 'sequences.json').write_text(json.dumps({'sequences': sequences}))
    (folder / 'caselist.json').write_text(json.dumps(caselist))
    return root


@unittest.skipUnless(HAS_PIL, 'the reader measures scenes with Pillow')
class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)

    def mirror(self, **parts):
        import claire_hart
        return claire_hart.Mirror(mirror_at(self.temporary.name, **parts))

    def test_faces_fold_into_looks_of_cods_five_slots(self):
        import claire_hart
        faces = [f'{CH}Ann/Avatar_Ann_{face}' for face in ('Normal', 'Angry', 'Happy', 'Sad', 'Surprised', 'Scream')]
        young = [f'{CH}Ann/Avatar_Ann_Young{face}' for face in ('Normal', 'Sad')]
        mirror = self.mirror(portraits=[*faces, *young, f'{CH}Ann/Avatar_Ann_Masked', f'{CH}Bo/Avatar_Bo_Angry',
                                        f'{CH}Bo/Avatar_Bo_Sad', f'{CH}Cy/Avatar_Cy_Normal 2'])
        banks, names, slots = mirror.look_banks()
        ids = mirror.picture_ids()
        looks = dict(zip(names, banks))
        self.assertEqual(looks['Ann'], [ids[path] for path in faces[:5]])
        self.assertEqual(looks['Ann Scream'], [ids[faces[5]]] * 5)              # a sixth face: a look of its own
        # Young is its own look; a face it lacks shows its Normal, as Classic's driver falls back to `default`
        self.assertEqual(looks['Ann Young'], [ids[young[0]]] * 3 + [ids[young[1]], ids[young[0]]])
        self.assertEqual(looks['Ann Masked'], [ids[f'{CH}Ann/Avatar_Ann_Masked']] * 5)
        # no Normal: its first face stands in
        angry, sad = ids[f'{CH}Bo/Avatar_Bo_Angry'], ids[f'{CH}Bo/Avatar_Bo_Sad']
        self.assertEqual(looks['Bo'], [angry, angry, angry, sad, angry])
        self.assertEqual(looks['Cy Normal 2'], [ids[f'{CH}Cy/Avatar_Cy_Normal 2']] * 5)
        self.assertEqual(slots[faces[3]], (names.index('Ann'), 3))
        self.assertEqual(len(slots), len(ids))                                  # every picture is some look's own face
        self.assertEqual(claire_hart.SLOTS, ('Normal', 'Angry', 'Happy', 'Sad', 'Surprised'))

    def test_a_lone_extra_face_takes_the_fifth_slot(self):
        faces = [f'{CH}Lu/Avatar_Lu_{face}' for face in ('Normal', 'Angry', 'Happy', 'Sad', 'Scream')]
        mirror = self.mirror(portraits=faces)
        banks, names, _ = mirror.look_banks()
        self.assertEqual(names, ['Lu'])
        self.assertEqual(banks[0][4], mirror.picture_ids()[faces[4]])

    def test_a_scene_slices_at_cods_cut_else_centred(self):
        cuts = {'0101': {'cands': [{'scene': 'Office', 'agree': 0.9, 'crop': [600, 0, 400, 768]}]},
                '0102': {'cands': [{'scene': 'Office', 'agree': 0.9, 'crop': [0, 0, 400, 768]}]},
                '0103': {'cands': [{'scene': 'Park', 'agree': 0.2, 'crop': [0, 0, 400, 768]}]},
                '0104': {'note': 'flat image'}}
        mirror = self.mirror(scenes={'Office': (1024, 768, []), 'Park': (1024, 768, [])}, cuts=cuts)
        scenes = mirror.scenes()
        # CoD's first cut of it (0101, centred at 800): its 576-wide slice reaches the right edge
        self.assertEqual(scenes['Office'], (26000, 448, 'cod'))
        self.assertEqual(scenes['Park'], (26001, 224, 'centre'))                # an unsure match places nothing

    def test_the_id_table_and_case_titles(self):
        config = dict(epid='E001', title=' Haunted ', sceneRefs={}, hogConfig={})
        cases = {'case1': ({'case': 'CASE 1', 'index': 1, 'title': ''}, [(config, {}), (dict(config, epid='E002'), {})]),
                 'casechristmas': ({'case': 'CASE Christmas', 'index': 4, 'title': 'Christmas Special'},
                                   [(dict(config, epid='E009'), {})])}
        rows = self.mirror(cases=cases).ids()
        self.assertEqual([(r['epid'], r['case_title'], r['part'], r['parts'], r['episode']) for r in rows],
                         [('E001', 'Case 1', 1, 2, 10), ('E002', 'Case 1', 2, 2, 10), ('E009', 'Christmas Special', 1, 1, 40)])
        self.assertEqual(rows[0]['title'], 'Haunted')
        self.assertEqual(rows[0]['pack'], 31500)

    def test_story_object_lists_resolve_to_the_scenes_items(self):
        names = [{'normal': 'ho_obj_x_broom', 'name': 'Broom'}, {'normal': 'ho_obj_x_keys2', 'name': 'Car Keys'}]
        refs = {'backgrounds': {'Shed': {'type': 'hogScene', 'scene': 'The Shed',
                                         'storyobject': ['Broom (by the door)', 'keys', 'Nothing', 'Lamp']}}}
        config = dict(epid='E001', title='x', sceneRefs={'SCENE 1_1': refs}, hogConfig={})
        mirror = self.mirror(scenes={'TheShed': (1024, 768, names)},
                             cases={'case1': ({'case': 'CASE 1', 'index': 1, 'title': ''}, [(config, {})])})
        found = {entry: item and item['name'] for _, _, entry, item in mirror.story_objects()}
        self.assertEqual(found, {'Broom (by the door)': 'Broom', 'keys': 'Car Keys', 'Lamp': None})

    def test_the_spec_names_every_picture_and_the_tracks_and_story_objects(self):
        import claire_hart
        mirror = self.mirror(portraits=[f'{CH}Ann/Avatar_Ann_Normal'], storyobjs=['references/storyobjs/b', 'references/storyobjs/a'],
                             tracks=['references/music/ogg/Park', 'references/music/ogg/Beach'],
                             scenes={'Office': (1024, 768, [])})
        spec = mirror.spec()
        self.assertEqual(spec['version'], claire_hart.SPEC_VERSION)
        self.assertEqual(spec['pictures'], {f'{CH}Ann/Avatar_Ann_Normal': [0, 0, 28010]})
        self.assertEqual(spec['story_objects'], {'references/storyobjs/a': 27000, 'references/storyobjs/b': 27001})
        self.assertEqual(spec['music'], {'Beach': 26900, 'Park': 26901})
        self.assertEqual(spec['scenes'], {'Office': [26000, 224]})
        self.assertEqual(json.loads(json.dumps(spec)), spec)


def a_case():
    """One part: chapter 1 (music, a backdrop, narration, a speaker's faces, a story object, a change of outfit), its
    round in the Shed, and chapter 2 (its track from chapter 1's map, Troy narrating)."""
    ann = {'default': f'{CH}Ann/Avatar_Ann_Normal', 'Avatar_Ann_Happy': f'{CH}Ann/Avatar_Ann_Happy',
           'Avatar_Ann_Purple_Normal': f'{CH}Ann/Avatar_Ann_Purple_Normal'}
    chapter1 = {'backgrounds': {'Office': {'type': 'texture', 'resource': 'references/backgrounds/Office/hd/template'},
                                'HIDDEN OBJECT GAME 1': {'type': 'hogScene', 'scene': 'Shed',
                                                         'storyobject': ['Broom (by the door)', 'Nothing']}},
                'characters': {'Ann': {'expressions': ann}}, 'music': {'Office': 'Theme.mp3'},
                'dialog objects': {'Push_Broom_SO': 'references/storyobjs/broomso'}, 'textColors': {}, 'sounds': {}}
    chapter2 = {'backgrounds': {'Office': chapter1['backgrounds']['Office']}, 'characters': {}, 'music': {},
                'dialog objects': {}, 'textColors': {}, 'sounds': {}}

    def line(header, body, expression=''):
        return {'type': 'dialogText', 'header': header, 'body': body, 'expression': expression}
    sequences = {
        'main': {'nodes': [{'type': 'playSequence', 'sequenceId': 'SCENE 1_1'},
                           {'type': 'playHOG', 'hogId': 'HIDDEN OBJECT GAME 1'},
                           {'type': 'playSequence', 'sequenceId': 'SCENE 1_2'}]},
        'SCENE 1_1': {'nodes': [{'type': 'event', 'eventtype': 'playMusic', 'id': 'Office'},
                                {'type': 'stageBlockIntro', 'ref': 'Office'}, {'type': 'dialogIntro'},
                                line('', 'Hello  there , friend… '), line('Ann', 'Hi!', 'Avatar_Ann_Happy'),
                                line('Ann', 'Still me.'), line('Ann', 'Typo.', 'Avatar_Ann_Hapy'),
                                {'type': 'event', 'eventtype': 'showStoryObject', 'id': 'Push_Broom_SO'},
                                line('Ann', 'New dress.', 'Avatar_Ann_Purple_Normal')]},
        'SCENE 1_2': {'nodes': [{'type': 'event', 'eventtype': 'playMusic', 'id': 'Office'},
                                {'type': 'stageBlockIntro', 'ref': 'Office'},
                                line('', 'Troy here.', 'Avatar_Troy_Event')]}}
    config = dict(epid='E001', title='Haunted', hogConfig={'HIDDEN OBJECT GAME 1': {'scene': 'Shed'}},
                  sceneRefs={'SCENE 1_1': chapter1, 'SCENE 1_2': chapter2})
    return {'case1': ({'case': 'CASE 1', 'index': 1, 'title': ''}, [(config, sequences)])}


@unittest.skipUnless(HAS_PIL, 'the reader measures scenes with Pillow')
class ConverterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)

    def test_text_and_round_lines(self):
        import claire_hart
        self.assertEqual(claire_hart.story_text('Hello  there , friend’s ‘dog’… '),
                         "Hello there, friend's 'dog'...")
        self.assertEqual(claire_hart.story_text('Wait ... now'), 'Wait ... now')      # only a lone mark joins
        self.assertEqual(claire_hart.place('Driveway'), 'the Driveway')
        self.assertEqual(claire_hart.place("Claire's Office"), "Claire's Office")
        self.assertEqual(claire_hart.place('The Aquatic Center'), 'The Aquatic Center')
        self.assertEqual(claire_hart.round_line('Troy', 'Driveway', ['Broom', 'Car Keys', 'Map']),
                         'Troy searches the Driveway and finds the Broom, the Car Keys and the Map.')
        self.assertEqual(claire_hart.round_line('Claire', 'Driveway', []), 'Claire searches the Driveway.')
        self.assertEqual(claire_hart.item_title('Push_Broom_SO'), 'Push Broom')
        self.assertEqual(claire_hart.item_title('CarKeysSO'), 'Car Keys')

    def test_episode_end_sign_offs_go(self):
        import claire_hart
        trim = claire_hart.trim_outro
        self.assertEqual(trim('A new case begins in the next episode of Claire Hart Classic!'), '')
        self.assertEqual(trim("We had the ring, we had the girl... but just what was Ethan's message? Find out in "
                              'Episode 3! And remember, Club POGO members get a discount on the next episode!'),
                         'We had the ring, we had the girl...')
        self.assertEqual(trim('Is it too late to help the spirit of Mrs. Gray? Find out in the next episode of Claire '
                              'Hart Classic.'), '')                              # "Mrs." doesn't end a sentence
        line = 'Troy smiled. Looks like Claire did it! Happy Holidays! Come back for the next episode.'
        self.assertEqual(trim(line, narration=True), 'Troy smiled.')             # the game's own voice goes too
        self.assertEqual(trim('Troy smiled at me.'), 'Troy smiled at me.')       # no sign-off: as it is

    def test_a_round_the_next_chapter_tells_keeps_no_stand_in(self):
        import claire_hart
        told = claire_hart.round_told
        self.assertEqual(told(['I found a set of keys by the pool.', 'Thanks.'], ['Car Keys']), 'names the Car Keys')
        self.assertEqual(told(['I searched the car.'], []), 'tells the search ("searched")')
        self.assertIsNone(told(['We drove back during the storm.', 'Hi.'], ['Ring']))   # "during" isn't a ring
        self.assertIsNone(told(['Troy waved.'], ['Broom']))

    def test_a_case_becomes_one_cod_episode(self):
        import claire_hart
        from exp_runtime.backdrop_slices import RESOURCE, decode
        from exp_runtime.exp import ExpArchive
        portraits = [f'{CH}Ann/Avatar_Ann_Normal', f'{CH}Ann/Avatar_Ann_Happy', f'{CH}Ann/Avatar_Ann_Purple_Normal',
                     f'{CH}ClaireHart/Avatar_Claire_Normal', f'{CH}TroyHarris/Avatar_Troy_Normal']
        root = mirror_at(self.temporary.name, portraits=portraits, cases=a_case(),
                         scenes={'Office': (1024, 768, []), 'Shed': (1024, 768, [{'normal': 'ho_obj_shed_broom',
                                                                                    'name': 'Broom'}])},
                         storyobjs=['references/storyobjs/broomso'], tracks=['references/music/ogg/Theme'])
        cache = Path(self.temporary.name) / 'store.json'
        cache.write_text(json.dumps({'E001': 'Office'}))
        mirror = claire_hart.Mirror(root)
        art = claire_hart.converter_art(mirror, cache)
        (_, case, parts), = mirror.cases()
        project, slices, report = claire_hart.convert(mirror, art, case, parts)
        self.assertEqual((project.title, project.game, project.pack_id, project.episode_id),
                         ('Case 1 (CHC)', 'cod', 31500, 10))
        self.assertEqual(project.addons, [dict(id='chc', revision=1)])
        seen = [(n.kind, n.text, n.character, n.expression) for n in project.nodes]
        names = {c.id: c.name for c in project.characters}
        looks = dict(zip(art['look_names'], range(len(art['look_names']))))
        title = project.nodes[0]
        self.assertEqual((title.kind, title.text, title.params['subtitle'], title.params['background']),
                         ('title', 'Haunted', 'Case 1', 26000))           # the episode's title over the case's
        lines = [(names.get(c, c), t, e) for k, t, c, e in seen if k == 'dialogue']
        self.assertEqual(lines, [('', 'Hello there, friend...', 0), ('Ann', 'Hi!', 2), ('Ann', 'Still me.', 0),
                                 ('Ann', 'Typo.', 0),
                                 ('Ann', 'New dress.', 0), ('', 'Claire searches the Shed and finds the Broom.', 0),
                                 ('', 'Troy here.', 0)])
        kinds = [k for k, *_ in seen]
        # the track restarts in chapter 2 from chapter 1's map; Ann's outfit is a look change; no relationship badge
        self.assertEqual(kinds.count('music'), 2)
        self.assertEqual(kinds.count('character_art'), 1)
        art_node = next(n for n in project.nodes if n.kind == 'character_art')
        self.assertEqual(art_node.asset, 30000 + 5 * looks['Ann Purple'])
        badge = next(n for n in project.nodes if n.kind == 'relationship')
        self.assertTrue(badge.params['hide'])
        narrators = [n.params['narrator'] for n in project.nodes if n.kind == 'speakers']
        self.assertEqual([names[n] for n in narrators], ['Claire', 'Troy'])
        # Ann isn't the narrator's person (Claire's folder narrates most), so no speaker is the player
        self.assertEqual({n.params['player'] for n in project.nodes if n.kind == 'speakers'}, {''})
        so = next(n for n in project.nodes if n.kind == 'story_object')
        self.assertEqual((so.text, so.asset), ('Push Broom', 27000))
        self.assertEqual(report['faces kept (a key the speaker lacks)'], 1)     # none asked shows default
        self.assertEqual(report['music ids from an earlier chapter or case'], 1)
        self.assertEqual(art['music_before'], {1: {}})          # the first case starts with no maps loaded
        art['music_before'] = {1: {'Lobby': 'Theme.mp3'}}       # a later case: an id only an earlier case maps
        parts[0][2]['SCENE 1_1']['nodes'].insert(0, {'type': 'event', 'eventtype': 'playMusic', 'id': 'Lobby'})
        project, _, report = claire_hart.convert(mirror, art, case, parts)
        self.assertEqual([n.params['resource'] for n in project.nodes if n.kind == 'music'], [26900] * 3)
        self.assertEqual(report['music ids from an earlier chapter or case'], 2)
        self.assertEqual(slices, {26000: 224, 26001: 224})
        archive = ExpArchive(claire_hart.compiled(project, slices))
        self.assertEqual(decode(archive.read(RESOURCE)), slices)


if __name__ == '__main__':
    unittest.main()
