"""The creator and addons: projects that declare them, what compiles, Preview, importing, and going to an original app."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from exp_runtime.addons import addon_record, provides_bytes
from exp_runtime.content import ContentLibrary, digest, import_game
from exp_runtime.creator import Asset, Node, ProjectError, compile_project
from exp_runtime.creator.addons import (AddonsNeeded, check_native_export, copy_addon_asset, drop_unused_addons, mechanics, pack_addons,
                                        use_addon_asset)
from exp_runtime.creator.compiler import export_native_slot
from exp_runtime.creator.model import VERSION, project_from_record, project_record
from exp_runtime.creator.native import import_exp
from exp_runtime.creator.preview import preview_resources
from exp_runtime.exp import ExpArchive
from test_content import FAKE_NATIVE, archive, make_apk, metadata
from test_creator_features import sequence
from test_vm import program

PNG = b'\x89PNG\r\n\x1a\n' + b'picture'
WAV = b'RIFF\x24\0\0\0WAVEfmt ' + b'sound'
SPEC = b'{"format": "shshd-cutscene", "version": 1, "size": [20, 40], "hold": 100, "skip": 0, "shots": [{"image": 26010, "start": 0, "end": 0, "from": [0, 0, 20, 40], "to": [0, 0, 20, 40]}]}'


def pack(revision=2):
    return archive({1: metadata('The Pack (addon)'), 4: provides_bytes('packs', 'The Pack', revision), 26010: PNG, 26011: WAV,
                    26012: SPEC, 26013: b'something else'})


class Library(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        profile = patch('exp_runtime.shs.content.NATIVE_SHA256', digest(FAKE_NATIVE))
        profile.start()
        self.addCleanup(profile.stop)
        apk = self.root / 'game.apk'
        make_apk(apk, archive({1: metadata(), 25001: program(0x33).to_bytes()}))
        self.folder = self.root / 'library'
        import_game(apk, [], self.folder)
        self.library = ContentLibrary(self.folder)
        self.addCleanup(self.library.close)
        path = self.root / 'pack.exp'
        path.write_bytes(pack())
        self.library.add_episodes([path])

    def story(self, *resources):
        project = sequence(Node('line', text='Hello.'))
        for resource in resources:
            use_addon_asset(project, self.library, 'packs', resource)
        return project


class ProjectTests(Library):
    def test_the_format_stays_at_3_and_older_projects_have_none(self):
        self.assertEqual(VERSION, 3)
        record = project_record(sequence(Node('line', text='Hello.')))
        del record['addons']
        self.assertEqual(project_from_record(record).addons, [])

    def test_using_an_asset_declares_the_addon_and_keeps_its_id_with_no_data(self):
        project = self.story(26010)
        asset = next(a for a in project.assets if a.id == 26010)
        self.assertEqual((asset.data, asset.addon), (None, 'packs'))
        self.assertEqual(project.addons, [dict(id='packs', revision=2)])

    def test_a_sound_and_a_cutscene_can_be_used_but_nothing_else(self):
        self.assertEqual({a.id for a in self.story(26011, 26012).assets}, {26011, 26012})
        with self.assertRaises(ProjectError):
            self.story(26013)
        with self.assertRaises(ProjectError):
            self.story(26999)

    def test_it_wont_use_an_id_the_project_holds_itself(self):
        project = sequence(Node('line', text='Hello.'))
        project.assets.append(Asset(26010, 'Mine', PNG))
        with self.assertRaisesRegex(ProjectError, 'Copy this one in'):
            use_addon_asset(project, self.library, 'packs', 26010)

    def test_copying_embeds_it_at_a_free_id_and_needs_no_addon(self):
        project = sequence(Node('line', text='Hello.'))
        picture = copy_addon_asset(project, self.library, 'packs', 26010)
        sound = copy_addon_asset(project, self.library, 'packs', 26011)
        self.assertEqual((picture.data, sound.data, project.addons), (PNG, WAV, []))
        with self.assertRaises(ProjectError):
            copy_addon_asset(project, self.library, 'packs', 26012)

    def test_an_undeclared_addon_is_refused_and_a_save_keeps_them(self):
        project = self.story(26010)
        again = project_from_record(project_record(project))
        self.assertEqual((again.addons, again.assets[0].addon), (project.addons, 'packs'))
        project.addons = []
        with self.assertRaisesRegex(ProjectError, "doesn't declare"):
            project_record(project)

    def test_removing_the_last_asset_drops_the_addon(self):
        project = self.story(26010)
        project.assets = []
        drop_unused_addons(project)
        self.assertEqual(project.addons, [])

    def test_export_declares_it_and_holds_none_of_its_data(self):
        archive_ = ExpArchive(compile_project(self.story(26010)))
        self.assertEqual(addon_record(archive_), ('requires', (('packs', 2),)))
        self.assertNotIn(26010, archive_.entries)
        self.assertIsNone(addon_record(ExpArchive(compile_project(sequence(Node('line', text='Hello.'))))))

    def test_music_a_sound_and_a_loop_can_come_from_an_addon(self):
        project = self.story(26011, 26010)
        for node in (Node('m', 'music', params={'resource': 26011, 'loop': True, 'then_loop': 26010}),
                     Node('s', 'sound', params={'resource': 26011})):
            node.next = project.nodes[0].id
            project.nodes.insert(0, node)
            project.start = node.id
        compile_project(project)

    def test_music_from_nowhere_is_still_refused(self):
        with self.assertRaisesRegex(ProjectError, 'native music ID'):
            compile_project(sequence(Node('m', 'music', params={'resource': 26011, 'loop': True})))

    def test_preview_finds_addons_though_its_saves_are_elsewhere(self):
        data = compile_project(self.story(26010))
        with preview_resources(data, self.folder, 'shs') as resources:
            self.assertEqual(resources.missing_addons(), [])
            self.assertEqual(resources.read_asset(26010), PNG)

    def test_importing_an_authored_export_brings_them_back(self):
        again = import_exp(compile_project(self.story(26010)))
        self.assertEqual(again.addons, [dict(id='packs', revision=2)])
        self.assertEqual(next(a for a in again.assets if a.id == 26010).addon, 'packs')

    def test_a_translations_older_export_that_lost_its_addons_assets_still_imports(self):
        # A build whose authoring record lists an embedded asset that strip_addon then left out.
        from exp_runtime.addons import requires_bytes
        from exp_runtime.exp import encode_exp
        project = sequence(Node('line', text='Hello.'))
        project.assets.append(Asset(26500, 'Shared', PNG))
        built = ExpArchive(compile_project(project))
        resources = {key: built.read(key) for key in built.entries if key != 26500}
        resources[4] = requires_bytes([('packs', 2)])
        again = import_exp(encode_exp(resources))
        self.assertEqual((again.assets[0].data, again.assets[0].addon), (None, 'packs'))
        self.assertEqual(again.addons, [dict(id='packs', revision=2)])

    def test_a_cutscene_needs_its_spec_in_the_project_and_an_embedded_one_needs_its_pictures(self):
        node = Node('c', 'cutscene', params={'spec': 26020})
        project = sequence(node)
        with self.assertRaisesRegex(ProjectError, 'choose a cutscene'):
            compile_project(project)
        project.assets.append(Asset(26020, 'Spec', SPEC))
        with self.assertRaisesRegex(ProjectError, 'resource 26010'):
            compile_project(project)
        project.assets.append(Asset(26010, 'Art', PNG))
        compile_project(project)
        project.assets[0].data = b'not a spec'
        with self.assertRaises(ProjectError):
            compile_project(project)

    def test_a_spec_from_an_addon_is_taken_on_trust_there(self):
        project = self.story(26012)
        node = Node('c', 'cutscene', params={'spec': 26012}, next=project.nodes[0].id)
        project.nodes.insert(0, node)
        project.start = 'c'
        self.assertEqual(addon_record(ExpArchive(compile_project(project))), ('requires', (('packs', 2),)))


class NativeExportTests(Library):
    def reference(self):
        path = self.root / 'original.exp'
        path.write_bytes(archive({1: metadata('The Original'), 25001: program(0x33).to_bytes()}))
        return path

    def test_a_plain_project_goes_as_it_always_did(self):
        destination = self.root / 'out.exp'
        export_native_slot(sequence(Node('line', text='Hello.')), self.reference(), destination)
        self.assertTrue(destination.is_file())

    def test_addon_assets_block_it_with_the_offer(self):
        destination = self.root / 'out.exp'
        with self.assertRaises(AddonsNeeded) as caught:
            export_native_slot(self.story(26010, 26011), self.reference(), destination)
        self.assertEqual(caught.exception.names, ['packs'])
        self.assertIn('packed', str(caught.exception))
        self.assertFalse(destination.exists())

    def test_packing_puts_them_in_needs_no_addon_and_leaves_the_project_alone(self):
        project = self.story(26010, 26011)
        destination = self.root / 'out.exp'
        export_native_slot(project, self.reference(), destination, pack_from=self.library)
        built = ExpArchive(destination.read_bytes())
        self.assertEqual((built.read(26010), built.read(26011)), (PNG, WAV))
        self.assertIsNone(addon_record(built))
        self.assertEqual(project.addons, [dict(id='packs', revision=2)])
        self.assertIsNone(project.assets[0].data)

    def test_packing_needs_the_addon_at_its_revision(self):
        project = self.story(26010)
        project.addons[0]['revision'] = 9
        with self.assertRaisesRegex(ProjectError, 'revision 9'):
            pack_addons(project, self.library)
        project.addons = [dict(id='gone', revision=1)]
        project.assets[0].addon = 'gone'
        with self.assertRaisesRegex(ProjectError, 'gone'):
            pack_addons(project, self.library)

    def test_a_spec_can_never_be_packed_in(self):
        with self.assertRaisesRegex(ProjectError, 'neither a picture nor a sound'):
            pack_addons(self.story(26012), self.library)

    def test_our_mechanics_block_it_outright_even_with_a_library_to_pack_from(self):
        for kind, params, named in (('cutscene', {'spec': 26012}, 'storyboard cutscenes'), ('x360_slot', {'result': 'r'}, 'slot machine'),
                                    ('x360_diss', {'result': 'r', 'tutorial': 0}, 'Diss Practice'),
                                    ('minigames_available', {'result': 'r'}, 'translated mini-games')):
            with self.subTest(kind=kind):
                project = self.story(26012)
                project.nodes.insert(0, Node('m', kind, params=params, next=project.nodes[0].id))
                project.start = 'm'
                destination = self.root / f'{kind}.exp'
                with self.assertRaises(ProjectError) as caught:
                    export_native_slot(project, self.reference(), destination, pack_from=self.library)
                self.assertNotIsInstance(caught.exception, AddonsNeeded)
                self.assertIn(named, str(caught.exception))
                self.assertIn('Only SHSHD Runtime', str(caught.exception))
                self.assertFalse(destination.exists())

    def test_an_imported_episodes_scripts_are_read_for_our_services(self):
        for service, named in ((205, 'minigame arena'), (216, 'X360 mini-games'), (218, 'storyboard cutscenes')):
            project = sequence(Node('line', text='Hello.'))
            project.nodes.append(Node('n', 'native', params={'instructions': [[0x1a, 1], [0x1f, service << 8 | 1]]}))
            self.assertTrue(any(named in name for name in mechanics(project)), service)
        project = sequence(Node('line', text='Hello.'))
        project.nodes.append(Node('n', 'native', params={'instructions': [[0x1f, 72 << 8]]}))
        self.assertEqual(mechanics(project), [])

    def test_an_imported_episode_that_needs_an_addon_cant_be_packed(self):
        project = sequence(Node('line', text='Hello.'))
        project.addons, project.native = [dict(id='packs', revision=1)], {'resources': {}}
        with self.assertRaises(ProjectError) as caught:
            check_native_export(project)
        self.assertNotIsInstance(caught.exception, AddonsNeeded)


class GameTests(unittest.TestCase):
    def test_this_runtimes_mechanics_are_refused_in_a_cod_project(self):
        for kind, params in (('cutscene', {'spec': 26000}), ('cutscene_available', {'result': 'r'}), ('minigames_available', {'result': 'r'}),
                             ('x360_slot', {'result': 'r'}), ('x360_leash', {'result': 'r'}), ('x360_puzzle', {'result': 'r'}),
                             ('x360_diss', {'result': 'r', 'tutorial': 0})):
            with self.subTest(kind=kind):
                project = sequence(Node('m', kind, params=params), game='cod')
                project.assets.append(Asset(26000, 'Spec', SPEC))
                with self.assertRaises(ProjectError):
                    compile_project(project)

    def test_a_cod_project_can_still_take_pictures_from_an_addon(self):
        project = sequence(Node('line', text='Hello.'), game='cod')
        project.addons = [dict(id='chslim', revision=1)]
        project.assets.append(Asset(28010, 'Portrait', None, 'chslim'))
        self.assertEqual(addon_record(ExpArchive(compile_project(project))), ('requires', (('chslim', 1),)))


class CutsceneAuthoringTests(unittest.TestCase):
    def project(self):
        project = sequence(Node('c', 'cutscene', params={'spec': 0}))
        project.assets += [Asset(26000, 'Art', PNG), Asset(26005, 'Whip', WAV)]
        return project

    def spec(self, **more):
        from exp_runtime.creator.cutscenes import blank_shot, blank_spec
        spec = blank_spec()
        shot = blank_shot()
        shot.update(image=26000, end=1000)
        spec.update(shots=[shot], hold=1000, sounds=[dict(at=500, sound=26005)], **more)
        return spec

    def test_a_saved_cutscene_plays_from_its_node(self):
        from exp_runtime.creator.cutscenes import cutscene_assets, read_project_spec, save_cutscene
        project = self.project()
        asset = save_cutscene(project, 'Opening', self.spec())
        self.assertEqual([a.id for a in cutscene_assets(project)], [asset.id])
        self.assertEqual(read_project_spec(asset)['hold'], 1000)
        project.nodes[0].params['spec'] = asset.id
        built = ExpArchive(compile_project(project))
        self.assertEqual(built.read(asset.id), asset.data)

    def test_replacing_keeps_its_id_and_a_missing_picture_is_named(self):
        from exp_runtime.creator.cutscenes import read_project_spec, save_cutscene
        project = self.project()
        asset = save_cutscene(project, 'Opening', self.spec())
        again = save_cutscene(project, 'Renamed', self.spec(skip=500), asset.id)
        self.assertEqual((again.id, again.name, read_project_spec(again)['skip']), (asset.id, 'Renamed', 500))
        spec = self.spec()
        spec['shots'][0]['image'] = 26999
        with self.assertRaisesRegex(ProjectError, '26999'):
            save_cutscene(project, 'Broken', spec)
        with self.assertRaises(ProjectError):
            save_cutscene(project, 'Not one', self.spec(), 26000)

    def test_a_bad_timeline_is_refused(self):
        from exp_runtime.creator.cutscenes import blank_spec, save_cutscene
        with self.assertRaises(ProjectError):
            save_cutscene(self.project(), 'No shots', blank_spec())
        with self.assertRaises(ProjectError):
            save_cutscene(self.project(), 'Skips past its hold', self.spec(skip=5000))

    def test_an_addons_asset_can_be_chosen_as_only_the_library_knows_what_it_is(self):
        from exp_runtime.creator.cutscenes import cutscene_assets
        project = self.project()
        project.addons = [dict(id='packs', revision=1)]
        project.assets.append(Asset(26012, 'From the pack', None, 'packs'))
        self.assertEqual([a.id for a in cutscene_assets(project)], [26012])


class TranslatorTests(unittest.TestCase):
    def test_a_translated_project_says_what_it_takes_from_the_addon(self):
        import x360
        project = sequence(Node('line', text='Hello.'))
        project.assets += [Asset(26100, 'Shared', PNG), Asset(26101, 'Its own', PNG)]
        x360.use_addon(project, [26100], 7)
        self.assertEqual(project.addons, [dict(id=x360.ADDON_ID, revision=7)])
        self.assertEqual((project.assets[0].data, project.assets[0].addon), (None, x360.ADDON_ID))
        self.assertEqual(project.assets[1].data, PNG)
        built = ExpArchive(compile_project(project))
        self.assertEqual(addon_record(built), ('requires', ((x360.ADDON_ID, 7),)))
        self.assertNotIn(26100, built.entries)
        self.assertIn(26101, built.entries)

    def test_stripping_replaces_a_declaration_the_story_already_had(self):
        import x360
        project = sequence(Node('line', text='Hello.'))
        project.addons = [dict(id=x360.ADDON_ID, revision=3)]
        project.assets += [Asset(26100, 'Spec', None, x360.ADDON_ID)]
        data, left_out = x360.strip_addon(compile_project(project), ExpArchive(archive({1: metadata('A'), 26100: b'x'})), 14)
        self.assertEqual(left_out, [])
        self.assertEqual(addon_record(ExpArchive(data)), ('requires', ((x360.ADDON_ID, 14),)))


if __name__ == '__main__':
    unittest.main()
