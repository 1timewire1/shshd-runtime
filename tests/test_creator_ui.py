"""Exercise the optional GUI using authored text and images, without a display."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HAS_QT = importlib.util.find_spec('PySide6') is not None


@unittest.skipUnless(HAS_QT, 'Install the creator extra to test the optional Qt editor')
class CreatorUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_edit_connect_undo_save_export_and_reopen_without_changing_literal_text(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QLineEdit, QTextEdit
        from exp_runtime.creator import compile_project, load_project
        from exp_runtime.creator.ui import Editor
        from exp_runtime.exp import ExpArchive
        editor = Editor(discover_library=False)
        editor.show()
        try:
            self.app.processEvents()
            field = editor.inspector.findChild(QTextEdit, 'story_text')
            field.setPlainText('<b>This is literal episode text.</b>')
            self.assertEqual(editor.project.node('start').text, '<b>This is literal episode text.</b>')
            editor.show_properties()
            self.assertEqual(editor.inspector.findChild(QTextEdit, 'story_text').toPlainText(),
                             '<b>This is literal episode text.</b>')
            editor.add_node('choice')
            choice = editor.selected
            editor.set_node('text', 'Choose your route.')
            editor.set_option(0, 'target', 'start')
            editor.set_option(1, 'target', 'end')
            editor.set_project('start', choice)
            self.assertEqual(editor.project.start, choice)
            self.assertTrue(compile_project(editor.project))
            editor.undo()
            self.assertEqual(editor.project.start, 'start')
            editor.redo()
            self.assertEqual(editor.project.start, choice)
            # User interaction reaches the same model used by the compiler.
            label = editor.inspector.findChild(QLineEdit, 'node_label')
            label.selectAll()
            QTest.keyClicks(label, 'Fork in the road')
            self.assertEqual(editor.project.node(choice).label, 'Fork in the road')
            temporary = tempfile.TemporaryDirectory()
            # Close the editor before deleting its owned project directory;
            # Windows keeps the session's lock file open until close.
            self.addCleanup(temporary.cleanup)
            path = Path(temporary.name) / 'episode.expproj'
            editor.path = path
            self.assertTrue(editor.save())
            self.assertFalse(editor.dirty)
            project = load_project(path)
            self.assertEqual(project, editor.project)
            export = Path(temporary.name) / 'episode.exp'
            with patch('exp_runtime.creator.ui.QFileDialog.getSaveFileName', return_value=(str(export), '')):
                editor.export()
            self.assertEqual(export.read_bytes(), compile_project(project))
            self.assertEqual(ExpArchive(export.read_bytes()).metadata().title, project.title)
            self.assertFalse(editor.grab().isNull())
        finally:
            editor.dirty = False
            editor.close()
            self.app.processEvents()

    def test_unsaved_cancel_keeps_the_editor_and_project_open(self):
        from PySide6.QtWidgets import QMessageBox
        from exp_runtime.creator.ui import Editor
        editor = Editor(discover_library=False)
        editor.show()
        editor.set_node('text', 'Unsaved work')
        with patch('exp_runtime.creator.ui.QMessageBox.question', return_value=QMessageBox.StandardButton.Cancel):
            editor.close()
        self.assertTrue(editor.isVisible())
        self.assertEqual(editor.project.node('start').text, 'Unsaved work')
        editor.dirty = False
        editor.close()

    def test_failed_preview_removes_temporary_export_and_reports_error(self):
        from PySide6.QtTest import QTest
        from exp_runtime.creator import export_project
        from exp_runtime.creator.ui import Editor
        editor = Editor(discover_library=False)
        try:
            with tempfile.TemporaryDirectory() as temporary:
                editor.project.library = temporary
                missing = str(Path(temporary) / 'missing-python')
                with patch('exp_runtime.creator.ui.sys.executable', missing), patch.object(editor, 'error') as error, \
                        patch('exp_runtime.creator.ui.export_project', wraps=export_project) as export:
                    editor.preview()
                    export.assert_called_once()
                    # FailedToStart may clean up synchronously on Windows.
                    staging = Path(export.call_args.args[1]).parent
                    for _ in range(100):
                        if editor.preview_process is None:
                            break
                        QTest.qWait(20)
                    self.assertIsNone(editor.preview_process)
                    self.assertIsNone(editor.preview_directory)
                    self.assertFalse(staging.exists())
                    error.assert_called_once()
        finally:
            editor.close()

    def test_export_does_not_overwrite_after_adding_an_extension_without_confirmation(self):
        from PySide6.QtWidgets import QMessageBox
        from exp_runtime.creator.ui import Editor
        editor = Editor(discover_library=False)
        try:
            with tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / 'existing.exp'
                path.write_bytes(b'keep previous export')
                with patch('exp_runtime.creator.ui.QFileDialog.getSaveFileName',
                           return_value=(str(path.with_suffix('')), '')), patch(
                        'exp_runtime.creator.ui.QMessageBox.question', return_value=QMessageBox.StandardButton.No):
                    editor.export()
                self.assertEqual(path.read_bytes(), b'keep previous export')
        finally:
            editor.close()


@unittest.skipUnless(HAS_QT, 'Install the creator extra to test the optional Qt editor')
class CreatorInspectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_every_node_kind_opens_in_the_inspector_with_its_fields(self):
        from PySide6.QtWidgets import QTextEdit
        from exp_runtime.creator.model import KINDS
        from exp_runtime.creator.ui import Editor
        editor = Editor(discover_library=False)
        editor.show()
        try:
            for kind in KINDS:
                if kind == 'native':
                    continue
                with self.subTest(kind=kind):
                    editor.add_node(kind)
                    self.app.processEvents()
                    self.assertEqual(editor.project.node(editor.selected).kind, kind)
                    text = editor.inspector.findChild(QTextEdit, 'story_text')
                    wanted = kind in ('dialogue', 'choice', 'title', 'message', 'notice', 'scene_label', 'word_game',
                                      'set_text', 'text_default', 'character_name', 'picker', 'faceplace',
                                      'faceplace_post', 'faceplace_link', 'tree_node', 'tree_result', 'append_text')
                    self.assertEqual(text is not None, wanted)
        finally:
            editor.dirty = False
            editor.close()


if __name__ == '__main__':
    unittest.main()

@unittest.skipUnless(HAS_QT, 'Install the creator extra to test the optional Qt editor')
class CreatorExpandedUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_all_node_inspectors_and_structured_settings_render(self):
        from exp_runtime.creator.ui import Editor
        from exp_runtime.creator.features import DEFAULTS
        from exp_runtime.creator.panels import RecordDialog, TranslationsDialog
        editor = Editor(discover_library=False)
        try:
            for kind, defaults in DEFAULTS.items():
                if kind == 'native': continue
                editor.add_node(kind)
                self.app.processEvents()
                self.assertIsNotNone(editor.inspector.widget())
                dialog = RecordDialog(defaults, editor)
                dialog.accept()
                self.assertEqual(dialog.value, defaults)
            translation = TranslationsDialog(editor.project, editor)
            self.assertGreater(translation.table.rowCount(), 10)
            translation.reject()
        finally:
            editor.dirty = False; editor.close()

    def test_autosave_copy_paste_layout_and_search_preserve_work(self):
        from exp_runtime.creator.ui import Editor
        from exp_runtime.creator.editing import Recovery
        editor = Editor(discover_library=False)
        with tempfile.TemporaryDirectory() as directory:
            editor.recovery = Recovery(Path(directory) / 'nested')
            try:
                editor.set_node('text', 'Find this dialogue')
                editor.autosave()
                self.assertEqual(Recovery.read(editor.recovery.path)[0], editor.project)
                editor.copy(); editor.paste()
                self.assertEqual(len(editor.project.nodes), 3)
                editor.arrange(); editor.search('Find this')
                self.assertEqual(editor.project.node(editor.selected).text, 'Find this dialogue')
            finally:
                editor.dirty = False; editor.close()
            self.assertFalse(editor.recovery.path.exists())
