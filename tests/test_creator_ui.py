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
        editor = Editor()
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
            with tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / 'episode.expproj'
                editor.path = path
                self.assertTrue(editor.save())
                self.assertFalse(editor.dirty)
                project = load_project(path)
                self.assertEqual(project, editor.project)
                export = Path(temporary) / 'episode.exp'
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
        editor = Editor()
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
        from exp_runtime.creator.ui import Editor
        editor = Editor()
        try:
            with tempfile.TemporaryDirectory() as temporary:
                editor.project.library = temporary
                missing = str(Path(temporary) / 'missing-python')
                with patch('exp_runtime.creator.ui.sys.executable', missing), patch.object(editor, 'error') as error:
                    editor.preview()
                    staging = Path(editor.preview_directory.name)
                    self.assertTrue((staging / 'preview.exp').exists())
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
        editor = Editor()
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


if __name__ == '__main__':
    unittest.main()
