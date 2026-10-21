"""Discover player libraries without copying assets or modifying player state."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from exp_runtime.content import ContentLibrary, import_game
from exp_runtime.creator import Asset, Node, Project, compile_project, load_project, save_project
from exp_runtime.launcher import remember_library
from test_creator import image_bytes
from test_games import make_cod_ipa
from test_ipa import make_ipa

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'Install the creator extra to test library discovery')
class CreatorLibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.data = self.root / 'preferences'
        for setting in (patch('exp_runtime.launcher.user_data_directory', return_value=self.data),
                        patch.object(sys, 'frozen', True, create=True)):
            setting.start()
            self.addCleanup(setting.stop)

    def library(self, game, path=None):
        path = path or self.data / 'libraries' / game
        source = self.root / (game + '.ipa')
        project = Project(game=game, assets=[Asset(26000, 'Authored image', image_bytes())])
        (make_ipa if game == 'shs' else make_cod_ipa)(source, compile_project(project))
        import_game(source, [], path, game=game)
        source.unlink()
        return path

    def editor(self, project=None):
        from exp_runtime.creator.ui import Editor
        editor = Editor(project)
        def close():
            editor.dirty = False
            editor.close()
            self.app.processEvents()
        self.addCleanup(close)
        return editor

    def test_default_libraries_make_base_and_episode_images_available_without_writes(self):
        from exp_runtime.creator.ui import LibraryBrowser
        for game in ('shs', 'cod'):
            with self.subTest(game=game):
                path = self.library(game)
                (path / 'saves').mkdir()
                (path / 'saves' / 'existing.json').write_text('Keep this save.')
                before = {p.relative_to(path): p.read_bytes() for p in path.rglob('*') if p.is_file()}
                editor = self.editor(Project(game=game))
                self.assertEqual(editor.project.library, str(path))
                self.assertFalse(editor.dirty)
                self.assertEqual(editor.project.assets, [])
                self.assertEqual(editor.library_label.toolTip(), str(path))
                with ContentLibrary(Path(editor.project.library)) as library:
                    browser = LibraryBrowser(library, editor)
                    self.assertGreater(browser.items.count(), 0)
                    self.assertEqual(browser.bank.count(), len(library.episodes) + 1)
                    browser.bank.setCurrentIndex(1)
                    self.assertIn('26000', [browser.items.item(i).text() for i in range(browser.items.count())])
                    browser.show_image('26000')
                    self.assertEqual(browser.resource, 26000)
                    browser.reject()
                self.assertEqual({p.relative_to(path): p.read_bytes() for p in path.rglob('*') if p.is_file()}, before)
                self.assertFalse((self.data / 'launcher.json').exists())

    def test_remembered_paths_take_precedence_and_game_switch_undo_keeps_the_right_bank(self):
        self.library('shs')
        shs = self.library('shs', self.root / 'my-shs')
        cod = self.library('cod', self.root / 'my-cod')
        remember_library(shs, 'shs')
        remember_library(cod, 'cod')
        before = (self.data / 'launcher.json').read_bytes()
        editor = self.editor()
        self.assertEqual(editor.project.library, str(shs))
        editor.game.setCurrentIndex(editor.game.findData('cod'))
        self.assertEqual((editor.project.game, editor.project.library), ('cod', str(cod)))
        editor.undo()
        self.assertEqual((editor.project.game, editor.project.library), ('shs', str(shs)))
        editor.redo()
        self.assertEqual((editor.project.game, editor.project.library), ('cod', str(cod)))
        self.assertEqual((self.data / 'launcher.json').read_bytes(), before)
        path = self.root / 'story.expproj'
        save_project(editor.project, path)
        editor.replace_project(load_project(path), path)
        self.assertEqual(editor.project.library, str(cod))
        editor.replace_project(Project(library=str(self.root / 'explicit-missing-library')))
        self.assertEqual(editor.project.library, str(self.root / 'explicit-missing-library'))
        editor.new()
        self.assertEqual(editor.project.library, str(shs))
        editor.replace_project(Project(game='cod'))
        self.assertEqual(editor.project.library, str(cod))

    def test_missing_broken_or_other_game_library_does_not_block_editing(self):
        editor = self.editor()
        self.assertEqual(editor.project.library, '')
        broken = self.root / 'broken'
        broken.mkdir()
        (broken / 'library.json').write_text('not valid JSON')
        wrong = self.library('cod')
        for path in (self.root / 'missing', broken, wrong):
            with self.subTest(path=path):
                remember_library(path, 'shs')
                editor.new()
                self.assertEqual(editor.project.library, '')
                self.assertTrue(compile_project(editor.project))
        editor.replace_project(Project(game='cod'))
        self.assertEqual(editor.project.library, str(wrong))
        editor.game.setCurrentIndex(editor.game.findData('shs'))
        self.assertEqual(editor.project.library, '')

    def test_game_switch_cannot_rebind_base_resources_or_native_scripts(self):
        path = self.library('shs')
        editor = self.editor()
        for project in (Project(assets=[Asset(6, 'Base image')]),
                        Project(native={'resources': {}}),
                        Project(nodes=[Node('start', 'music')]),
                        Project(nodes=[Node('start', 'sound')])):
            with self.subTest(project=project):
                editor.replace_project(project)
                with patch.object(editor, 'error') as error:
                    editor.game.setCurrentIndex(editor.game.findData('cod'))
                error.assert_called_once()
                self.assertEqual((editor.project.game, editor.project.library), ('shs', str(path)))
                self.assertEqual(editor.game.currentData(), 'shs')
                self.assertFalse(editor.dirty)
