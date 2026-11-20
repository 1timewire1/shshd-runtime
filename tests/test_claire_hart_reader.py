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
        caselist[key] = dict(record, episodes=[{} for _ in parts])
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


if __name__ == '__main__':
    unittest.main()
