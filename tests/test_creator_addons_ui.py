"""The creator's windows for addons and cutscenes: the library browser, the pack-or-block prompt and the timeline editor."""
import importlib.util
import os
import unittest
from unittest.mock import patch

from exp_runtime.creator import Asset, Node
from exp_runtime.creator.cutscenes import blank_spec, read_project_spec
from exp_runtime.exp import ExpArchive
from exp_runtime.addons import addon_record
from test_content import archive, metadata
from test_creator_addons import Library, PNG, WAV
from test_creator_features import sequence
from test_vm import program

HAS_QT = importlib.util.find_spec('PySide6') is not None
PICTURES = [('26000 · Art', 26000), ('26005 · Other', 26005)]
SOUNDS = [('26010 · Whip', 26010)]


def timeline():
    spec = blank_spec()
    spec.update(hold=2000, skip=1500, music=26010,
                shots=[{'image': 26000, 'start': 0, 'end': 1500, 'from': [0, 0, 768, 1024], 'to': [100, 50, 768, 1024], 'ease': 'out'},
                       {'image': 26005, 'start': 1500, 'end': 1500, 'from': [0, 0, 768, 1024], 'to': [0, 0, 768, 1024]}],
                overlays=[{'image': 26005, 'start': 1500, 'end': 1700, 'from': [300, 600, 900, 500], 'to': [300, 600, 450, 250]}],
                sounds=[dict(at=1500, sound=26010)])
    return spec


@unittest.skipUnless(HAS_QT, 'the creator extra (PySide6) is required')
class Windows(Library):
    @classmethod
    def setUpClass(cls):
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])


    def close(self, editor):
        """Without its "save changes?" prompt, which would wait forever here."""
        editor.dirty = False
        editor.close()


class TimelineTests(Windows):
    def dialog(self, spec=None, name='Opening'):
        from exp_runtime.creator.panels import CutsceneDialog
        return CutsceneDialog(spec or timeline(), name, PICTURES, SOUNDS)

    def test_a_timeline_comes_back_out_as_it_went_in(self):
        dialog = self.dialog()
        self.assertEqual(dialog.current_spec(), timeline())
        self.assertEqual(dialog.name.text(), 'Opening')

    def test_rows_can_be_added_and_a_new_shot_starts_where_the_last_ended(self):
        dialog = self.dialog()
        dialog.add_shot()
        self.assertEqual(dialog.shots.cellWidget(2, 1).value(), 1500)
        dialog.add_sound()
        dialog.add_overlay()
        spec = dialog.current_spec()
        self.assertEqual((len(spec['shots']), len(spec['sounds']), len(spec['overlays'])), (3, 2, 2))

    def test_shots_and_sounds_are_put_in_time_order_as_the_format_wants(self):
        dialog = self.dialog()
        dialog.add_sound(dict(at=100, sound=26010))
        dialog.add_shot({'image': 26000, 'start': 500, 'end': 900, 'from': [0, 0, 768, 1024], 'to': [0, 0, 768, 1024]})
        spec = dialog.current_spec()
        self.assertEqual([shot['start'] for shot in spec['shots']], [0, 500, 1500])
        self.assertEqual([sound['at'] for sound in spec['sounds']], [100, 1500])

    def test_ok_refuses_a_bad_timeline_and_says_why(self):
        dialog = self.dialog(blank_spec())
        with patch('exp_runtime.creator.panels.QMessageBox.warning') as warning:
            dialog.accept()
        warning.assert_called_once()
        self.assertIsNone(dialog.spec)
        dialog = self.dialog()
        dialog.accept()
        self.assertEqual(dialog.spec, timeline())

    def editor(self, project):
        from exp_runtime.creator.ui import Editor
        editor = Editor(project, discover_library=False)
        self.addCleanup(self.close, editor)
        return editor

    def node_project(self):
        project = sequence(Node('c', 'cutscene', params={'spec': 0}))
        project.assets += [Asset(26000, 'Art', PNG), Asset(26005, 'Other', PNG), Asset(26010, 'Whip', WAV)]
        return project

    def test_editing_from_the_node_embeds_it_and_points_the_node_at_it(self):
        editor = self.editor(self.node_project())
        editor.selected = 'c'
        editor.show_properties()
        with patch('exp_runtime.creator.ui.CutsceneDialog') as dialog:
            dialog.return_value.exec.return_value = 1
            dialog.return_value.spec = timeline()
            dialog.return_value.name.text.return_value = 'Opening'
            editor.edit_cutscene()
        resource = editor.project.node('c').params['spec']
        asset = next(a for a in editor.project.assets if a.id == resource)
        self.assertEqual((asset.name, read_project_spec(asset)['hold']), ('Opening', 2000))
        # Editing again replaces that one, and the dialog is given what the node has.
        with patch('exp_runtime.creator.ui.CutsceneDialog') as dialog:
            dialog.return_value.exec.return_value = 0
            editor.edit_cutscene()
        self.assertEqual(dialog.call_args.args[0]['hold'], 2000)
        self.assertEqual(dialog.call_args.args[1], 'Opening')

    def test_an_addons_cutscene_cant_be_edited(self):
        project = self.node_project()
        project.addons = [dict(id='packs', revision=1)]
        project.assets.append(Asset(26012, 'From the pack', None, 'packs'))
        project.node('c').params['spec'] = 26012
        editor = self.editor(project)
        editor.selected = 'c'
        with patch.object(editor, 'error') as error, patch('exp_runtime.creator.ui.CutsceneDialog') as dialog:
            editor.edit_cutscene()
        dialog.assert_not_called()
        self.assertIn('belongs to an add-on', str(error.call_args.args[0]))


class BrowserTests(Windows):
    def browser(self):
        from exp_runtime.creator.ui import LibraryBrowser
        browser = LibraryBrowser(self.library)
        browser.bank.setCurrentIndex(browser.bank.findData('addon:packs'))
        return browser

    def test_addons_are_in_the_list_and_only_they_offer_use_from_addon(self):
        from exp_runtime.creator.ui import LibraryBrowser
        browser = LibraryBrowser(self.library)
        self.assertFalse(browser.use_addon.isVisibleTo(browser))
        browser = self.browser()
        self.assertTrue(browser.use_addon.isVisibleTo(browser))
        self.assertEqual([browser.items.item(i).text() for i in range(browser.items.count())], ['26010', '26011', '26012', '26013'])

    def buttons(self, browser):
        from PySide6.QtWidgets import QDialogButtonBox
        return browser.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled(), browser.use_addon.isEnabled()

    def test_a_sound_can_be_used_or_copied_and_a_cutscene_only_used(self):
        browser = self.browser()
        browser.show_image('26011')
        self.assertEqual(self.buttons(browser), (True, True))
        self.assertIn('sound', browser.preview.text())
        browser.show_image('26012')
        self.assertEqual(self.buttons(browser), (False, True))
        self.assertIn('cutscene', browser.preview.text())

    def test_anything_else_cant_be_taken(self):
        browser = self.browser()
        browser.show_image('26013')
        self.assertEqual(self.buttons(browser), (False, False))

    def test_use_from_addon_says_so(self):
        browser = self.browser()
        self.assertFalse(browser.reference)
        browser.choose_reference()
        self.assertTrue(browser.reference)

    def test_the_project_list_marks_what_comes_from_an_addon(self):
        from exp_runtime.creator.addons import use_addon_asset
        from exp_runtime.creator.ui import Editor
        project = sequence(Node('line', text='Hello.'))
        use_addon_asset(project, self.library, 'packs', 26011)
        editor = Editor(project, discover_library=False)
        self.addCleanup(self.close, editor)
        editor.refresh()
        self.assertIn('(add-on)', editor.assets.item(0).text())


class OriginalAppExportTests(Windows):
    def setUp(self):
        super().setUp()
        from exp_runtime.creator.addons import use_addon_asset
        from exp_runtime.creator.ui import Editor
        project = sequence(Node('line', text='Hello.'))
        use_addon_asset(project, self.library, 'packs', 26011)
        project.library = str(self.folder)
        self.editor = Editor(project, discover_library=False)
        self.addCleanup(self.close, self.editor)
        self.reference = self.root / 'original.exp'
        self.reference.write_bytes(archive({1: metadata('The Original'), 25001: program(0x33).to_bytes()}))
        self.destination = self.root / 'out.exp'

    def test_declining_the_offer_exports_nothing(self):
        from PySide6.QtWidgets import QMessageBox
        with patch('exp_runtime.creator.ui.QMessageBox.question', return_value=QMessageBox.StandardButton.No) as question:
            self.assertIsNone(self.editor.export_slot(self.reference, self.destination))
        self.assertIn('packed', question.call_args.args[2])
        self.assertFalse(self.destination.exists())

    def test_accepting_it_packs_them_in_and_leaves_the_project_as_it_was(self):
        from PySide6.QtWidgets import QMessageBox
        with patch('exp_runtime.creator.ui.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes):
            self.assertIsNotNone(self.editor.export_slot(self.reference, self.destination))
        built = ExpArchive(self.destination.read_bytes())
        self.assertEqual(built.read(26011), WAV)
        self.assertIsNone(addon_record(built))
        self.assertEqual(self.editor.project.addons, [dict(id='packs', revision=2)])

    def test_our_mechanics_get_no_offer_at_all(self):
        from exp_runtime.creator import ProjectError
        project = self.editor.project
        project.nodes.insert(0, Node('m', 'x360_slot', params={'result': 'r'}, next=project.nodes[0].id))
        project.start = 'm'
        with patch('exp_runtime.creator.ui.QMessageBox.question') as question, self.assertRaises(ProjectError) as caught:
            self.editor.export_slot(self.reference, self.destination)
        question.assert_not_called()
        self.assertIn('slot machine', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
