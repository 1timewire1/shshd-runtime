"""shshd-runtime: Secret in the Shadows' reader (tools/translate/claire_hart_shadows.py, sequel Stage S1): the case list's
dialect and decision K's parts, the chapters and rounds `main` plays, the looks, the stage tracker's faces, the crop rule
and the story-object names, on a small mirror made here; and pack 31900's add-on settings."""
import csv
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools' / 'translate'))
HAS_PIL = importlib.util.find_spec('PIL') is not None and importlib.util.find_spec('numpy') is not None
CH = 'references/characters/'
CLAIRE = {'default': CH + 'Avatar_ClaireHart/sd/avatar_clairehart_normal',
          'Happy': CH + 'Avatar_ClaireHart/sd/avatar_clairehart_happy'}
TROY = {'default': CH + 'Avatar_TroyHarris/sd/avator_toryharris_normal',
        'Sad': CH + 'Avatar_TroyHarris/sd/avator_toryharris_sad'}


def line(body, header='', **fields):
    return dict(type='dialogText', body=body, header=header, **fields)


def chapter_refs(**extra):
    refs = {'characters': {'Claire': {'expressions': CLAIRE}, 'Troy': {'expressions': TROY}}, 'backgrounds': {},
            'music': {}, 'dialogStoryObjects': {}}
    refs.update(extra)
    return refs


def episode(scheme='SCENE 1_', chapters=None, refs=None):
    """(epconfig, sequences) of six chapters and five rounds between them."""
    ids = [f'{scheme}{n}' for n in range(1, 7)]
    main = []
    for n, chapter in enumerate(ids, 1):
        main.append(dict(type='playSequence', sequenceId=chapter))
        if n < 6:
            main.append(dict(type='playHOG', hogId=f'HIDDEN OBJECT GAME {n}'))
    sequences = {'main': {'nodes': main}}
    for chapter in ids:
        sequences[chapter] = {'nodes': (chapters or {}).get(chapter, [line('A line.')])}
    config = {'sceneRefs': {chapter: (refs or {}).get(chapter, chapter_refs()) for chapter in ids}, 'hogConfig': {}}
    return config, sequences


def mirror_at(root, cases, portraits=(), storyobjs=(), names=None, sizes=None):
    """A mirror folder: `cases` [(case record, [(epconfig, sequences)])], `portraits` and `storyobjs` as bundle rows with
    pictures (`sizes` {path: (w, h, colour)}), and round scenes' `names` {scene: [entries]}."""
    from PIL import Image
    root = Path(root)
    rows = []
    for kind, paths in (('portrait', portraits), ('storyobj', storyobjs)):
        for number, path in enumerate(paths):
            local = f'raw/{kind}{number}.png'
            rows.append(dict(real_path=path, part='native', kind=kind, local_path=local))
            (root / 'raw').mkdir(parents=True, exist_ok=True)
            width, height, colour = (sizes or {}).get(path, (4, 4, (number, 0, 0, 255)))
            Image.new('RGBA', (width, height), colour).save(root / local)
    with open(root / 'bundle_names.csv', 'w', encoding='utf-8', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=['real_path', 'part', 'kind', 'local_path'])
        writer.writeheader()
        writer.writerows(rows)
    folder = root / 'unpacked/resources_json/cases'
    folder.mkdir(parents=True)
    listed = []
    for number, (record, episodes) in enumerate(cases, 1):
        listed.append(record)
        for e, (config, sequences) in enumerate(episodes, 1):
            (folder / f'case{number}' / f'ep{e}').mkdir(parents=True)
            (folder / f'case{number}' / f'ep{e}' / 'epconfig.json').write_text(json.dumps(config))
            (folder / f'case{number}' / f'ep{e}' / 'sequences.json').write_text(json.dumps({'sequences': sequences}))
    (folder / 'caselist.json').write_text(json.dumps({'metadata': {}, 'case_list': listed}))
    for scene, entries in (names or {}).items():
        (root / 'unpacked/resources_json/references/backgrounds' / scene).mkdir(parents=True)
        (root / 'unpacked/resources_json/references/backgrounds' / scene / 'names.json').write_text(
            json.dumps({'names': entries}))
    return root


def case(title, *names, number=None):
    record = {'title': title, 'episodes': [{'name': name, 'id': f'ch2_epid.{number or 1}case{k}ep'}
                                           for k, name in enumerate(names, 1)]}
    if number is not None:
        record['case'] = number
    return record


@unittest.skipUnless(HAS_PIL, 'Pillow and NumPy are needed')
class ReaderTests(unittest.TestCase):
    def setUp(self):
        import claire_hart_shadows
        self.S = claire_hart_shadows
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)

    def mirror(self, cases, **kwargs):
        return self.S.Mirror(mirror_at(self.folder.name, cases, **kwargs))

    def test_the_case_list_dialect_and_decision_ks_parts(self):
        S = self.S
        cases = [(case('Bitter Revenge', 'One', 'Two'), [episode(), episode('SCENE ')])]
        cases += [(case(f'Case {n}', 'Only', number=n), [episode()]) for n in range(2, 46)]
        cases[30] = (case('Esplanade', 'BoomBoxx', number=31), [episode()] * 4)      # (three parts unlisted)
        cases[44] = (case('Title for Case 45', 'Title for case 45, episode 1', number=45), [episode()])
        mirror = self.mirror(cases)
        read = {number: (title, parts) for number, title, parts in mirror.cases()}
        self.assertEqual(read[1][0], 'Bitter Revenge')                  # (cases 1 and 2 carry no number)
        self.assertEqual([p.title for p in read[31][1]], ['BoomBoxx', "Eric's Past", 'Accident Averted', "Claire's heart"])
        self.assertEqual([p.listed for p in read[31][1]], [True, False, False, False])
        self.assertEqual(read[31][1][3].epid, 'ch2_epid.31case4ep')
        self.assertEqual((read[45][0], read[45][1][0].title), ('Lost Soul', 'Lost Soul'))
        rows = mirror.ids()
        self.assertEqual({(r['case'], r['part'], r['episode'], r['pack']) for r in rows if r['case'] == 31},
                         {(31, n, 310, S.PACK_ID) for n in range(1, 5)})
        # Both chapter-id schemes, each chapter with the round after it.
        self.assertEqual(S.chapters_of(read[1][1][1].sequences)[:2],
                         [('SCENE 1', 'HIDDEN OBJECT GAME 1'), ('SCENE 2', 'HIDDEN OBJECT GAME 2')])
        self.assertEqual(S.chapters_of(read[1][1][0].sequences)[-1], ('SCENE 1_6', None))

    def test_refs_keep_a_lower_case_copy_of_each_character(self):
        refs = self.S.refs_for({'characters': {'Claire': {'expressions': CLAIRE}}, 'music': {'Office': 'x.mp3'},
                                'backgrounds': {'Office': {'type': 'texture', 'resource': 'r'}}})
        self.assertIs(refs['claire'], refs['Claire'])
        self.assertEqual(refs['music'], {'Office': 'x.mp3'})
        self.assertEqual(refs['Office']['resource'], 'r')

    def test_looks_fold_faces_into_cods_five_slots(self):
        S = self.S
        faces = ['Avatar_ClaireHart/sd/avatar_clairehart_' + f for f in ('normal', 'angry', 'happy', 'sad', 'surprised')]
        faces += ['Avatar_Harper/sd/avatar_harperanderson_neutral', 'Avatar_Harper/sd/avatar_harperanderson_normal',
                  'Avatar_SimonWells/hd/avatar_simonwells_neutral', 'Avatar_SimonWells/sd/avatar_simonwells_neutral',
                  'Avator_PaigeMills/sd/avatar_paigemills_halloween', 'Avatar_HarrisonMyers/sd/avatar_harrisonmyers_happy_copy',
                  'Avatar_PatrickGates/sd/template']
        paths = [CH + f for f in faces]
        same = (4, 4, (9, 9, 9, 255))
        mirror = self.mirror([(case('A', 'One'), [episode()])], portraits=paths,
                             sizes={CH + 'Avatar_SimonWells/hd/avatar_simonwells_neutral': same,
                                    CH + 'Avatar_SimonWells/sd/avatar_simonwells_neutral': same})
        ids = mirror.picture_ids()
        self.assertNotIn(CH + 'Avatar_PatrickGates/sd/template', ids)        # (never shown)
        self.assertEqual(ids[CH + 'Avatar_SimonWells/sd/avatar_simonwells_neutral'],
                         ids[CH + 'Avatar_SimonWells/hd/avatar_simonwells_neutral'])     # (the same pixels: one picture)
        banks, names, slots = mirror.look_banks(ids)
        claire = names.index('Claire Hart')
        self.assertEqual(banks[claire], [ids[CH + f] for f in faces[:5]])
        self.assertEqual(slots[CH + faces[1]], (claire, 1))                   # Angry
        self.assertEqual(slots[CH + 'Avatar_HarrisonMyers/sd/avatar_harrisonmyers_happy_copy'][1], 2)
        self.assertIn('Harper Normal', names)                                 # (a second picture for a face: its own look)
        self.assertIn('Paige Mills Halloween', names)
        harper = names.index('Harper')
        self.assertEqual(banks[harper], [ids[CH + 'Avatar_Harper/sd/avatar_harperanderson_neutral']] * 5)
        self.assertEqual(S.look_name('Avatar_AlessandravanderWalt'), 'Alessandra van der Walt')
        self.assertEqual(S.look_name('Avator_James Lieft'), 'James Lieft')

    def test_the_crop_puts_the_head_where_classics_is(self):
        from PIL import Image
        S = self.S
        picture = Image.new('RGBA', (600, 566))
        picture.paste((200, 50, 50, 255), (380, 40, 480, 160))               # a head right of centre
        picture.paste((50, 50, 200, 255), (300, 160, 560, 566))              # a body to the foot
        out = S.portrait_crop(picture)
        self.assertEqual(out.size, S.PORTRAIT_SIZE)
        from PIL import ImageChops
        opaque = out.getchannel('A').point(lambda v: 255 if v > 128 else 0)
        head = ImageChops.multiply(out.getchannel('R').point(lambda v: 255 if v > 150 else 0), opaque).getbbox()
        k = S.PORTRAIT_SIZE[1] / S.CROP_HEIGHT
        self.assertAlmostEqual((head[0] + head[2]) / 2, S.PORTRAIT_SIZE[0] / 2, delta=3)     # centred on the head
        self.assertAlmostEqual(head[1], S.CROP_MARGIN * k, delta=2)                        # its top just below the frame's
        self.assertAlmostEqual(head[2] - head[0], 100 * k, delta=2)                        # at the rule's scale
        wide = S.portrait_crop(picture, 540)                                               # (the Browdy brothers' window)
        self.assertEqual(wide.size, S.PORTRAIT_SIZE)

    def test_the_stage_gives_every_line_its_face(self):
        from collections import Counter
        S = self.S
        log = Counter()
        refs = S.refs_for(chapter_refs())
        stage = S.Stage(refs, log)
        for node in (dict(type='stageBlockIntro', ref='CLAIRE', id='CLAIRE'),
                     dict(type='stageBlockExpressionChange', ref='Claire', id='CLAIRE', expression='Happy')):
            stage.step(node)
        self.assertEqual(stage.face(line('Hi.', 'Claire')), ('Claire', CLAIRE['Happy']))          # the tracker
        self.assertEqual(stage.face(line('Hi.', 'Claire', expression='')), ('Claire', CLAIRE['default']))  # its field
        self.assertEqual(stage.face(line('So.', narrator='Claire')), ('Claire', CLAIRE['Happy']))  # narration: the stage
        self.assertEqual(stage.face(line('So.', narrator='Happy')), ('Claire', CLAIRE['Happy']))   # (junk: Claire)
        self.assertEqual(stage.face(line('Hey.', 'Troy')), ('Troy', TROY['default']))             # off stage: default
        stage.step(dict(type='stageBlockExpressionChange', ref='Troy', id='TROY', expression='Sad'))     # (ignored)
        stage.step(dict(type='stageBlockExpressionChange', ref='Claire', id='CLAIRE', expression='Angry'))   # (lacks it)
        self.assertEqual(stage.face(line('Hi.', 'Claire'))[1], CLAIRE['Happy'])
        stage.step(dict(type='event', eventtype='clearStage'))
        self.assertEqual(stage.face(line('Hi.', 'Claire'))[1], CLAIRE['default'])
        empty = S.Stage(S.refs_for(chapter_refs(characters={})), log)
        self.assertEqual(empty.face(line('The end.')), ('Claire', S.CLAIRE))         # (a chapter without her: her Normal)
        self.assertEqual(log['face changes for someone off stage (ignored)'], 1)
        self.assertEqual(log['face changes to a face they lack (face kept)'], 1)

    def test_photos_are_named_from_the_round_before(self):
        S = self.S
        found = 'references/backgrounds/Den_HO/hd/1_den_knife_found'
        photo = 'references/storyobjs/case1ep1scene1_2_0'
        refs = {f'SCENE 1_{n}': chapter_refs() for n in range(1, 7)}
        refs['SCENE 1_1']['backgrounds'] = {'HIDDEN OBJECT GAME 1': {'type': 'hogScene', 'scene': 'Den_HO',
                                                                     'storyobject': ['Vase']}}
        refs['SCENE 1_2']['backgrounds'] = {'HIDDEN OBJECT GAME 2': {'type': 'hogScene', 'scene': 'Den_HO',
                                                                     'storyobject': ['Nothing']}}
        refs['SCENE 1_2']['dialogStoryObjects'] = {'SCENE 1_2_0': photo}
        refs['SCENE 1_3']['dialogStoryObjects'] = {'SCENE 1_3_0': found}
        show = lambda key: dict(type='event', eventtype='showStoryObject', id=key)   # noqa: E731
        chapters = {'SCENE 1_2': [show('SCENE 1_2_0'), line('A vase.')], 'SCENE 1_3': [show('SCENE 1_3_0'), line('.')]}
        mirror = self.mirror([(case('A', 'One'), [episode(chapters=chapters, refs=refs)])], storyobjs=[photo],
                             names={'Den_HO': [{'name': 'broken vase', 'normal': 'den_vase_normal', 'found': 'den_vase_found'},
                                               {'name': 'Knife', 'normal': 'den_knife_normal', 'found': 'den_knife_found'}]})
        rows = S.story_object_names(mirror)
        self.assertEqual([(row[4], row[5]) for row in rows],
                         [('Broken vase', 'round list entry 1'), ('Knife', 'its round sprite')])
        self.assertEqual(mirror.story_object_ids(), {photo: 27000, found: 27001})   # (the round sprite after the pictures)


@unittest.skipUnless(HAS_PIL, 'Pillow and NumPy are needed')
class ConverterTests(unittest.TestCase):
    def setUp(self):
        import claire_hart_shadows
        self.S = claire_hart_shadows
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)

    def test_a_later_parts_introduction_and_self_description_go(self):
        trim = self.S.trim_intro
        self.assertEqual(trim("I'm Harper. I'm a grad student in the Bay Area. I also have an unusual ability. Eric was hurt."),
                         'Eric was hurt.')
        self.assertEqual(trim("I'm Claire Hart. I'm a writer and I have a unique ability."), '')
        self.assertEqual(trim('Eric was hurt. I am sad.'), 'Eric was hurt. I am sad.')      # (no introduction: as it is)

    def test_round_places_are_said_plainly(self):
        names = ['Harper', 'Eric Ito', 'Claire Hart']
        self.assertEqual([self.S.place_name(n, names) for n in ('HarpersLivingRoom', 'EricsStudio', 'DeliteDiner',
                                                                 "Claire's Living Room", 'ItoGuest')],
                         ["Harper's Living Room", "Eric's Studio", 'Delite Diner', "Claire's Living Room", 'Ito Guest Room'])

    def test_journal_text_keeps_paragraphs_by_the_text_rules(self):
        self.assertEqual(self.S.journal_text('My ‘husband’, Troy.\n\nWill  helps… '),
                         "My 'husband', Troy.\nWill helps...")

    def test_a_case_with_its_journal_and_notice(self):
        S = self.S
        den = {'type': 'texture', 'resource': 'references/backgrounds/Den_HO/hd/template'}
        refs = {f'SCENE 1_{n}': chapter_refs(backgrounds={'Den': den}) for n in range(1, 7)}
        refs['SCENE 1_1']['journal'] = [{'header': 'Journal 1:1', 'body': 'Troy was arrested.\nI must help.'}]
        refs['SCENE 1_2']['journal'] = [{'header': 'Journal 1:1', 'body': 'Troy was arrested.\nI must help.',
                                         'pastEntry': True},
                                        {'header': 'Journal 1:2', 'body': 'Will helps.'}]      # (no unlock: at its end)
        chapters = {'SCENE 1_1': [dict(type='stageBlockIntro', ref='Den', id='Den', intro='enterFromBottom'),
                                  dict(type='stageBlockIntro', ref='CLAIRE', id='CLAIRE'),
                                  line('Hello.', 'Claire'), dict(type='event', eventtype='animateJournalIcon'),
                                  line('I wondered.', narrator='Claire')]}
        config, sequences = episode(chapters=chapters, refs=refs)
        config['hogConfig'] = {f'HIDDEN OBJECT GAME {n}': {'scene': 'Den_HO'} for n in range(1, 6)}
        mirror = S.Mirror(mirror_at(self.folder.name, [(case('Bitter Revenge', 'Cloud of Suspicion'), [(config, sequences)])],
                                    portraits=[CLAIRE['default'], CLAIRE['Happy']]))
        art = dict(looks=[[28000, 28000, 28001, 28000, 28000]], look_names=['Claire Hart'],
                   faces={CLAIRE['default']: (0, 0), CLAIRE['Happy']: (0, 2)}, scenes={'Den_HO': (26000, 224)},
                   own_scenes=set(), music={}, story_objects={}, store={'case1/ep1': 'Den_HO'}, names={})
        number, title, parts = mirror.cases()[0]
        project, _, report = S.convert(mirror, art, number, title, parts)
        kinds = [node.kind for node in project.nodes]
        self.assertEqual((project.pack_id, project.episode_id, project.title), (31900, 10, 'Bitter Revenge (CH2)'))
        quests = [node for node in project.nodes if node.kind == 'quest']
        self.assertEqual([(q.params['number'], q.params['title'], q.text) for q in quests],
                         [(0, 'Cloud of Suspicion', 'Troy was arrested.\nI must help.'),
                          (0, 'Cloud of Suspicion', 'Troy was arrested.\nI must help.\n\nWill helps.')])
        notice = kinds.index('quest') + 1
        self.assertEqual(kinds[notice:notice + 3], ['speakers', 'sound', 'dialogue'])
        self.assertEqual(project.nodes[notice].params['narrator'], '')                       # (no portrait)
        self.assertEqual(project.nodes[notice + 1].params['resource'], S.JOURNAL_SOUND)
        self.assertEqual(project.nodes[notice + 2].text, S.JOURNAL_NOTICE)
        self.assertEqual(report['journal notices'], 2)
        self.assertEqual(project.addons, [dict(id='ch2', revision=1)])
        from claire_hart import compiled
        self.assertTrue(compiled(project, {}))                 # (it compiles)


class Pack31900Tests(unittest.TestCase):
    def test_ch2_brings_the_sequels_settings(self):
        from exp_runtime.cod import profile
        self.assertEqual(profile.ADDON_FEATURE_PACKS[('ch2', '')], 31900)
        self.assertEqual(profile.LOOK_BANKS[31900], ('ch2', 26998, 30000))
        self.assertEqual(profile.BACKDROP_SLICES[31900], ('ch2', 26998))       # (and so Claire Hart 4:3)
        self.assertEqual(profile.TRANSLATED_FRAME_BACKDROP[31900], 26999)
        from exp_runtime.creator.addons import ADDON_FEATURES
        self.assertIn('ch2', ADDON_FEATURES)


@unittest.skipUnless(HAS_PIL, 'Pillow and NumPy are needed')
class TitleLookTests(unittest.TestCase):
    def test_the_cast_and_logo_are_cut_out_with_soft_edges(self):
        """Revision 3's title (owner, 2026-11-25): the loading picture's group, faded to nothing at its edges, solid inside;
        the look's background is the episode select's backdrop ch2 already holds, the jingle at chc's number."""
        import io
        from PIL import Image
        import claire_hart_shadows as s2
        picture = Image.open(io.BytesIO(s2.title_picture(Image.new('RGB', (1066, 600), (90, 40, 120))))).convert('RGBA')
        width, height = picture.size
        self.assertEqual((width, height), (s2.TITLE_CROP[2] - s2.TITLE_CROP[0], s2.TITLE_CROP[3] - s2.TITLE_CROP[1]))
        for corner in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1), (width // 2, height - 1)):
            self.assertEqual(picture.getpixel(corner)[3], 0, corner)
        self.assertEqual(picture.getpixel((width // 2, height // 2)), (90, 40, 120, 255))
        self.assertEqual(s2.TITLE_LOOK['background']['cover']['id'], s2.FRAME_BACKDROP)
        self.assertEqual((s2.TITLE_SPEC, s2.TITLE_MUSIC, s2.ADDON_REVISION), (26960, 26990, 3))


if __name__ == '__main__':
    unittest.main()
