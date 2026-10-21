"""Exercise the actual desktop bridge and MCP transport with authored stories."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from importlib.util import find_spec
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from exp_runtime.creator import Project, ProjectError, load_project, save_project
from exp_runtime.creator.editing import Recovery
from exp_runtime.creator.sharing import (ProjectBusy, SharingError, guard, request,
                                         session_info, state_path)
from exp_runtime.creator.workspace import Workspace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


@unittest.skipUnless(find_spec('PySide6'), 'Install the creator extra for live editing tests')
class CreatorLiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from exp_runtime.creator.ui import Editor
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.path = self.root / 'story.expproj'
        save_project(Project(), self.path)
        self.editor = Editor(path=self.path, discover_library=False)
        self.editor.recovery = Recovery(self.root / 'recovery')
        self.editor.show()
        self.app.processEvents()
        self.workspace = Workspace(self.root)
        self.addCleanup(self.close_editor)

    def close_editor(self):
        self.editor.dirty = False
        self.editor.close()
        self.app.processEvents()

    def client(self, operation):
        # The GUI stays on its owning thread while the real socket/MCP client
        # runs independently, as it does when launched by a model client.
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(operation)
            deadline = time.monotonic() + 40
            while not pending.done() and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(.002)
            return pending.result(timeout=1)

    def test_unsaved_desktop_edits_model_transaction_undo_redo_and_save_share_one_document(self):
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QTextEdit
        original = self.path.read_bytes()
        self.editor.title.setFocus()
        self.editor.title.selectAll()
        QTest.keyClicks(self.editor.title, 'Unsaved desktop title')
        field = self.editor.inspector.findChild(QTextEdit, 'story_text')
        field.setPlainText('Unsaved human dialogue.')
        field.setFocus()
        cursor = field.textCursor(); cursor.setPosition(7); field.setTextCursor(cursor)
        before = self.client(lambda: self.workspace.describe('story.expproj'))
        self.assertTrue(before['live'])
        self.assertTrue(before['unsaved'])
        self.assertEqual(before['title'], 'Unsaved desktop title')
        self.assertEqual(before['nodes'][0]['text'], 'Unsaved human dialogue.')
        changed = self.client(lambda: self.workspace.batch('story.expproj', before['revision'], [
            dict(op='node', id='ending', changes={'kind': 'end', 'label': 'Model ending'}),
            dict(op='connect', source='start', target='ending'),
        ]))
        self.assertTrue(changed['live'])
        self.assertTrue(changed['unsaved'])
        self.assertIn('ending', self.editor.graph.cards)
        self.assertEqual(self.editor.project.node('start').text, 'Unsaved human dialogue.')
        field = self.editor.inspector.findChild(QTextEdit, 'story_text')
        self.assertIs(self.app.focusWidget(), field)
        self.assertEqual(field.textCursor().position(), 7)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(Recovery.read(self.editor.recovery.path)[0], self.editor.project)
        self.editor.undo()
        self.assertNotIn('ending', self.editor.graph.cards)
        self.assertEqual(self.editor.project.title, 'Unsaved desktop title')
        self.assertEqual(self.editor.project.node('start').text, 'Unsaved human dialogue.')
        self.assertEqual(self.client(lambda: self.workspace.read('story.expproj'))[1], before['revision'])
        self.editor.redo()
        self.assertIn('ending', self.editor.graph.cards)
        self.assertTrue(self.editor.save())
        self.assertEqual(load_project(self.path), self.editor.project)
        self.assertFalse(self.client(lambda: self.workspace.snapshot('story.expproj')).unsaved)

    def test_stale_edits_dialogs_and_invalid_batches_preserve_the_current_document(self):
        from PySide6.QtWidgets import QDialog
        before = self.client(lambda: self.workspace.read('story.expproj'))[1]
        self.editor.set_node('text', 'Typed after the model read.')
        with self.assertRaisesRegex(ProjectError, 'changed'):
            self.client(lambda: self.workspace.update('story.expproj', before, {'title': 'Stale edit'}))
        fresh = self.client(lambda: self.workspace.read('story.expproj'))[1]
        invalid = [dict(op='project', changes={'title': 'Must roll back'}),
                   dict(op='node', id='bad', changes={'kind': 'invalid'})]
        with self.assertRaises(ProjectError):
            self.client(lambda: self.workspace.batch('story.expproj', fresh, invalid))
        self.assertEqual(self.editor.project.title, 'Untitled episode')
        self.assertEqual(self.editor.project.node('start').text, 'Typed after the model read.')
        dialog = QDialog(self.editor); dialog.setModal(True); dialog.show(); self.app.processEvents()
        try:
            with self.assertRaises(ProjectBusy):
                self.client(lambda: self.workspace.read('story.expproj'))
        finally:
            dialog.reject(); self.app.processEvents()

    def test_revision_is_rechecked_when_the_desktop_accepts_an_edit(self):
        from exp_runtime.creator.model import project_record
        candidate, revision = self.client(lambda: self.workspace.read('story.expproj'))
        candidate.title = 'Outdated candidate'
        # The candidate is prepared already, like a model transaction that
        # was valid when read but races a later human edit before committing.
        self.editor.set_node('text', 'Latest human edit')
        with self.assertRaisesRegex(ProjectError, 'changed'):
            self.client(lambda: request(session_info(self.path), 'commit', revision=revision,
                                         project=project_record(candidate)))
        self.assertEqual(self.editor.project.node('start').text, 'Latest human edit')
        self.assertEqual(self.editor.project.title, 'Untitled episode')

    def test_checkpoint_restore_export_and_playtest_use_unsaved_live_state(self):
        self.editor.set_node('text', 'Unsaved text for the VM.')
        first = self.client(lambda: self.workspace.read('story.expproj'))[1]
        changed = self.client(lambda: self.workspace.update('story.expproj', first, {'title': 'Model title'}))
        debug = self.client(lambda: self.workspace.start_debug('story.expproj'))
        self.assertEqual(debug['revision'], changed['revision'])
        result = self.workspace.debugger(debug['session']).resume(step=False)
        self.assertEqual(result['details']['text'], 'Unsaved text for the VM.')
        self.workspace.close_debug(debug['session'])
        self.client(lambda: self.workspace.export('story.expproj', 'story.exp', changed['revision']))
        from exp_runtime.exp import ExpArchive
        self.assertEqual(ExpArchive((self.root / 'story.exp').read_bytes()).metadata().title, 'Model title')
        restored = self.client(lambda: self.workspace.restore('story.expproj', changed['revision'], changed['undo_checkpoint']))
        self.assertEqual(restored['revision'], first)
        self.assertEqual(self.editor.project.title, 'Untitled episode')
        self.assertEqual(self.editor.project.node('start').text, 'Unsaved text for the VM.')
        self.editor.undo()
        self.assertEqual(self.editor.project.title, 'Model title')
        # A saved authoring checkpoint may intentionally have unfinished
        # connections. Restoring it must behave like desktop Undo.
        self.editor.set_node('next', 'future')
        unfinished = self.client(lambda: self.workspace.read('story.expproj'))[1]
        complete = self.client(lambda: self.workspace.node('story.expproj', unfinished, 'future', {'kind': 'end'}))
        self.client(lambda: self.workspace.restore('story.expproj', complete['revision'], complete['undo_checkpoint']))
        self.assertEqual(self.editor.project.node('start').next, 'future')
        self.assertNotIn('future', self.editor.graph.cards)

    def test_closed_or_unavailable_sessions_never_silently_overwrite_a_live_project(self):
        from exp_runtime.creator.ui import Editor
        with self.assertRaises(ProjectBusy): Editor(path=self.path, discover_library=False)
        info = session_info(self.path)
        bad = dict(info, token='0' * 64)
        with self.assertRaisesRegex(ProjectError, 'Unknown desktop session'):
            self.client(lambda: request(bad, 'read'))
        self.close_editor()
        self.assertIsNone(session_info(self.path))
        w = self.workspace
        revision = w.read('story.expproj')[1]
        result = w.update('story.expproj', revision, {'title': 'Saved after closing'})
        self.assertFalse(result['live'])
        self.assertEqual(load_project(self.path).title, 'Saved after closing')
        original = self.path.read_bytes()
        # A process crash can leave a private discovery record. Fail closed
        # until the creator reopens the project and replaces the stale lease.
        state_path(self.path, '.json').write_text(json.dumps(info))
        with self.assertRaises(SharingError): w.update('story.expproj', result['revision'], {'title': 'Must not write'})
        self.assertEqual(self.path.read_bytes(), original)
        recovered = Editor(path=self.path, discover_library=False)
        try: self.assertNotEqual(session_info(self.path)['token'], info['token'])
        finally: recovered.close()

    def test_external_file_changes_and_busy_file_locks_preserve_desktop_work(self):
        self.editor.set_node('text', 'Keep my unsaved work')
        save_project(Project(title='Saved by another program'), self.path)
        with patch.object(self.editor, 'error') as error:
            self.assertFalse(self.editor.save())
        error.assert_called_once()
        self.assertEqual(load_project(self.path).title, 'Saved by another program')
        self.assertEqual(self.editor.project.node('start').text, 'Keep my unsaved work')
        with guard(self.path), self.assertRaises(ProjectBusy):
            self.client(lambda: self.workspace.read('story.expproj'))

    def test_save_as_and_open_transfer_the_live_document_without_changing_other_files(self):
        self.editor.set_node('text', 'A new saved copy')
        destination = self.root / 'copy.expproj'
        with patch.object(self.editor, 'save_destination', return_value=destination):
            self.assertTrue(self.editor.save_as())
        self.assertIsNone(session_info(self.path))
        self.assertIsNotNone(session_info(destination))
        self.assertEqual(self.workspace.read('story.expproj')[0].node('start').text, 'Your story begins here.')
        self.assertEqual(self.client(lambda: self.workspace.read('copy.expproj'))[0].node('start').text, 'A new saved copy')
        with patch('exp_runtime.creator.ui.QFileDialog.getOpenFileName', return_value=(str(self.path), '')):
            self.editor.open()
        self.assertIsNone(session_info(destination))
        self.assertIsNotNone(session_info(self.path))
        self.assertEqual(self.editor.project.node('start').text, 'Your story begins here.')
        self.assertEqual(self.workspace.read('copy.expproj')[0].node('start').text, 'A new saved copy')

    def test_failed_recovery_or_save_as_retains_the_original_document_and_connection(self):
        before = self.client(lambda: self.workspace.read('story.expproj'))[1]
        with patch.object(self.editor.recovery, 'write', side_effect=OSError('Cannot write recovery')):
            with self.assertRaisesRegex(ProjectError, 'Cannot write recovery'):
                self.client(lambda: self.workspace.update('story.expproj', before, {'title': 'Must not apply'}))
        self.assertEqual(self.editor.project.title, 'Untitled episode')
        self.assertEqual(self.client(lambda: self.workspace.read('story.expproj'))[1], before)
        self.editor.set_node('text', 'Keep this draft after Save as fails')
        other = self.root / 'copy.expproj'
        with patch.object(self.editor, 'save_destination', return_value=other), patch.object(self.editor, 'error'), \
                patch('exp_runtime.creator.ui.save_project', side_effect=OSError('Cannot write project')):
            self.assertFalse(self.editor.save_as())
        self.assertEqual(self.editor.path, self.path)
        self.assertIsNone(session_info(other))
        self.assertEqual(self.client(lambda: self.workspace.read('story.expproj'))[0].node('start').text,
                         'Keep this draft after Save as fails')

    @unittest.skipUnless(find_spec('mcp'), 'Install creator-mcp for the combined desktop/stdio check')
    def test_real_stdio_mcp_client_updates_the_open_editor(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        self.editor.set_node('text', 'Human draft visible through MCP.')
        async def use_mcp():
            params = StdioServerParameters(command=sys.executable,
                args=['-m', 'exp_runtime.creator.mcp_server', '--workspace', str(self.root)])
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as client:
                    await client.initialize()
                    result = await client.call_tool('project_get', dict(path='story.expproj', view='full'))
                    self.assertFalse(result.isError, result.content)
                    data = result.structuredContent
                    self.assertTrue(data['live'])
                    self.assertEqual(data['nodes'][0]['text'], 'Human draft visible through MCP.')
                    result = await client.call_tool('project_apply_edits', dict(path='story.expproj', revision=data['revision'],
                        operations=[dict(op='node', id='start', changes={'text': 'Live model dialogue.'})]))
                    self.assertFalse(result.isError, result.content)
                    self.assertTrue(result.structuredContent['unsaved'])
        self.client(lambda: asyncio.run(use_mcp()))
        self.assertEqual(self.editor.project.node('start').text, 'Live model dialogue.')
        self.assertIn('Live model dialogue.', self.editor.graph.cards['start'].caption.toPlainText())
        self.editor.undo()
        self.assertEqual(self.editor.project.node('start').text, 'Human draft visible through MCP.')
