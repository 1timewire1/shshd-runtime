"""Qt graph editor. The production player owns all game presentation."""
from copy import deepcopy
from html import escape
from pathlib import Path
import sys
import json
from dataclasses import asdict
import tempfile
import uuid

from PySide6.QtCore import QPointF, QProcess, Qt, Signal, QTimer, QStandardPaths
from PySide6.QtGui import QAction, QColor, QIcon, QKeySequence, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QGraphicsItem, QGraphicsPathItem, QGraphicsRectItem,
    QGraphicsScene, QGraphicsTextItem, QGraphicsView, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QMainWindow, QMessageBox, QPushButton, QScrollArea,
    QSpinBox, QSplitter, QTextEdit, QToolBar, QVBoxLayout, QWidget)

from exp_runtime.exp import ContentError
from .addons import (ADDON_FEATURES, AddonsNeeded, NODE_ADDONS, copy_addon_asset, drop_unused_addons, require_node_addon,
                     set_primary_addon, use_addon_asset)
from .cutscenes import blank_spec, cutscene_assets, read_project_spec, save_cutscene
from .assets import addon_asset_ids, image_png, import_library_image, player_library
from .compiler import compile_project, export_project, export_native_slot
from exp_runtime.cutscene_spec import read_spec
from .model import (Choice, EMOTICONS, KINDS, OPERATORS, Node, Project, ProjectError,
                    project_from_bytes, save_project, Character, is_audio, is_image, validate_structure)
from .features import NAMES, parameters
from .editing import Recovery, auto_layout, copy_nodes, paste_nodes
from .panels import CutsceneDialog, DebugDialog, ListDialog, RecordDialog, TranslationsDialog
from .live import LiveEditor
from .sharing import SharingError, digest, guard, session_info

COLORS = dict(dialogue='#6093cb', choice='#b381c7', background='#67a68b',
              set='#cc9d50', branch='#cc9d50', end='#aa7479')
COLORS = dict.fromkeys(KINDS, '#6093cb') | COLORS


class NodeItem(QGraphicsRectItem):
    def __init__(self, node, graph):
        super().__init__(0, 0, 228, 126)
        self.node, self.graph = node, graph
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setBrush(QColor('#263342'))
        self.caption = QGraphicsTextItem(self)
        self.caption.setTextWidth(212)
        self.caption.setPos(8, 5)
        self.caption.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setPos(node.x, node.y)
        self.refresh()

    def refresh(self):
        node = self.node
        marker = 'START · ' if node.id == self.graph.project.start else ''
        text = node.text or (f'{node.variable} {node.operator if node.kind == "branch" else "="} {node.value}'
                            if node.kind in ('set', 'branch') else NAMES[node.kind])
        self.setPen(QPen(QColor(COLORS[node.kind]), 2))
        self.caption.setHtml(f'<span style="color:{COLORS[node.kind]}">{marker}{NAMES[node.kind]}</span>'
                             f'<br><b style="color:#ffffff">{escape(node.label or node.id)}</b>'
                             f'<br><span style="color:#d2dce8">{escape(text[:70])}</span>')

    def mousePressEvent(self, event):
        self.original = (self.node.x, self.node.y)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        self.graph.draw_edges()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if (self.pos().x(), self.pos().y()) != self.original:
            self.graph.moved.emit(self.node.id, self.pos().x(), self.pos().y())


class Graph(QGraphicsScene):
    moved = Signal(str, float, float)

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self.cards = {}
        self.edges = []
        self.rebuild()

    def rebuild(self, selected=None):
        self.blockSignals(True)
        self.clear()
        self.edges, self.cards = [], {}
        for node in self.project.nodes:
            card = NodeItem(node, self)
            self.cards[node.id] = card
            self.addItem(card)
            card.setSelected(node.id == selected)
        self.draw_edges()
        self.blockSignals(False)

    def draw_edges(self):
        for edge in self.edges:
            self.removeItem(edge)
        self.edges = []
        for source in self.cards.values():
            for i, (label, target) in enumerate(source.node.links()):
                if target not in self.cards:
                    continue
                start = source.pos() + QPointF(228, 45 + i * 9)
                end = self.cards[target].pos() + QPointF(0, 62)
                path = QPainterPath(start)
                if source.node.id == target:
                    end = source.pos() + QPointF(114, 0)
                    path.cubicTo(start + QPointF(100, -180), end + QPointF(50, -100), end)
                else:
                    bend = max(65, abs(end.x() - start.x()) / 2)
                    path.cubicTo(start + QPointF(bend, 0), end - QPointF(bend, 0), end)
                line = QGraphicsPathItem(path)
                line.setPen(QPen(QColor('#8798aa'), 2))
                line.setZValue(-1)
                line.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                self.addItem(line)
                caption = self.addText(label[:22] + ' →')
                caption.setDefaultTextColor(QColor('#d2dce8'))
                caption.setPos(path.pointAtPercent(0.45))
                caption.setZValue(-1)
                caption.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                self.edges.extend((line, caption))
        self.setSceneRect(self.itemsBoundingRect().adjusted(-150, -150, 150, 150))


class LibraryBrowser(QDialog):
    def __init__(self, library, parent=None):
        super().__init__(parent)
        self.library, self.episode, self.resource = library, None, None
        self.setWindowTitle('Images from your imported library')
        self.resize(740, 520)
        layout = QVBoxLayout(self)
        self.bank = QComboBox()
        self.bank.addItem('Original game assets (reference only)', None)
        for addon in library.addons:
            self.bank.addItem(f'Add-on: {addon["title"]}', 'addon:' + addon['addon'])
        for episode in library.episodes:
            self.bank.addItem(episode['titles'][0] or episode['name'], episode['id'])
        layout.addWidget(self.bank)
        search = QLineEdit()
        search.setPlaceholderText('Filter by resource ID')
        layout.addWidget(search)
        row = QHBoxLayout()
        self.items = QListWidget()
        row.addWidget(self.items, 1)
        self.preview = QLabel('Select an image resource to preview it.')
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumWidth(380)
        self.preview.setWordWrap(True)
        row.addWidget(self.preview, 2)
        layout.addLayout(row, 1)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Add image to project')
        # An add-on's picture or sound: by reference, which needs the add-on, or copied in, which doesn't (the Ok above).
        self.reference = False
        self.use_addon = self.buttons.addButton('Use from add-on', QDialogButtonBox.ButtonRole.AcceptRole)
        self.use_addon.clicked.connect(self.choose_reference)
        self.use_addon.hide()
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.bank.currentIndexChanged.connect(self.populate)
        self.items.currentTextChanged.connect(self.show_image)
        search.textChanged.connect(lambda text: [self.items.item(i).setHidden(text not in self.items.item(i).text())
                                                for i in range(self.items.count())])
        self.populate()

    def populate(self):
        selector = self.bank.currentData()
        self.items.clear()
        self.episode, self.resource, self.addon = None, None, None
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        from_addon = bool(selector) and selector.startswith('addon:')
        self.use_addon.setVisible(from_addon)
        self.use_addon.setEnabled(False)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Copy into project' if from_addon else 'Add image to project')
        try:
            if selector and selector.startswith('addon:'):
                self.addon = selector[len('addon:'):]
                self.items.addItems([str(i) for i in addon_asset_ids(self.library, self.addon)])
                return
            self.episode = self.library.open_episode(selector) if selector else None
            ids = (self.episode.archive.entries if self.episode else self.library.base_members)
            self.items.addItems([str(i) for i in sorted(ids) if 26000 <= i <= 32767] if self.episode
                                else [str(i) for i in sorted(ids) if i < 25000])
        except (ContentError, OSError) as error:
            self.preview.setText(str(error))

    def choose_reference(self):
        self.reference = True
        self.accept()

    def show_image(self, text):
        self.resource = None
        if self.addon:
            self.show_addon_asset(text)
            return
        try:
            resource = int(text)
            png = image_png((self.episode or self.library).read_asset(resource))
            pixmap = QPixmap()
            if not pixmap.loadFromData(png):
                raise ProjectError('Image could not be decoded')
            self.preview.setPixmap(pixmap.scaled(380, 360, Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.SmoothTransformation))
            self.resource = resource
        except (ValueError, OSError, ContentError) as error:
            self.preview.setText(str(error) if text else 'Select an image resource.')
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(self.resource is not None)


    def show_addon_asset(self, text):
        """An add-on's resource: a picture is shown, and a sound or cutscene is named. Copying only takes pictures and sounds."""
        ok = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        try:
            resource = int(text)
            data = self.library.addon(self.addon)[1].read(resource)
            copyable = True
            if is_image(data):
                pixmap = QPixmap()
                if not pixmap.loadFromData(image_png(data)):
                    raise ProjectError('Image could not be decoded')
                self.preview.setPixmap(pixmap.scaled(380, 360, Qt.AspectRatioMode.KeepAspectRatio,
                                                    Qt.TransformationMode.SmoothTransformation))
            elif is_audio(data):
                self.preview.setText(f'A sound, {len(data) // 1024} KB.')
            else:
                copyable = False
                read_spec(data)
                self.preview.setText('A storyboard cutscene.')
            self.resource = resource
            ok.setEnabled(copyable)
            self.use_addon.setEnabled(True)
        except (ValueError, OSError, ContentError) as error:
            self.preview.setText(str(error) if text else 'Select a resource.')
            ok.setEnabled(False)
            self.use_addon.setEnabled(False)


class Editor(QMainWindow):
    def __init__(self, project=None, path=None, *, discover_library=True):
        super().__init__()
        self.setWindowIcon(QIcon(str(Path(__file__).with_name('kiwi-hammer.svg'))))
        self.project, self.path = project or Project(), Path(path) if path else None
        self.live_editor = LiveEditor(self)
        self.saved_path = self.disk_revision = None
        if self.path is not None:
            try:
                self.live_editor.attach(self.path)
                with guard(self.path):
                    data = self.path.read_bytes()
                    if project is None: self.project = project_from_bytes(data, self.path)
                    self.disk_revision = digest(data)
                self.saved_path = self.path.resolve()
            except BaseException:
                self.live_editor.close()
                raise
        self.discover_library = discover_library
        self.use_player_library()
        self.dirty = False
        self.undo_history, self.redo_history = [], []
        self.selected = self.project.start
        self.preview_process = None
        self.preview_directory = None
        self.recovery = Recovery(Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)) / 'recovery')
        self.autosave_timer = QTimer(self)
        self.autosave_timer.timeout.connect(self.autosave)
        self.autosave_timer.start(15000)
        self.live_timer = QTimer(self)
        self.live_timer.setSingleShot(True)
        self.live_timer.timeout.connect(self.restart_preview)
        self.resize(1320, 820)
        self.setMinimumSize(1000, 650)
        toolbar = QToolBar('Episode')
        self.addToolBar(toolbar)
        for label, callback, shortcut in (
            ('New', self.new, QKeySequence.StandardKey.New),
            ('Open…', self.open, QKeySequence.StandardKey.Open),
            ('Save', self.save, QKeySequence.StandardKey.Save),
            ('Save as…', self.save_as, QKeySequence.StandardKey.SaveAs),
            ('Undo', self.undo, QKeySequence.StandardKey.Undo),
            ('Redo', self.redo, QKeySequence.StandardKey.Redo),
            ('Validate', self.validate, None), ('Export EXP…', self.export, None),
            ('Original app export…', self.export_original, None),
            ('Preview in player', self.preview, None),
            ('Import EXP…', self.import_exp, None), ('Debug…', self.debug, None),
        ):
            action = QAction(label, self)
            action.triggered.connect(callback)
            if shortcut:
                action.setShortcut(shortcut)
            toolbar.addAction(action)
        root = QWidget()
        column = QVBoxLayout(root)
        project_row = QHBoxLayout()
        self.title = QLineEdit(self.project.title)
        self.title.setPlaceholderText('Episode title')
        self.title.setObjectName('project_title')
        self.title.textEdited.connect(lambda value: self.set_project('title', value))
        project_row.addWidget(QLabel('Title'))
        project_row.addWidget(self.title, 1)
        self.game = QComboBox()
        self.game.addItem('Surviving High School', 'shs')
        self.game.addItem('Cause of Death', 'cod')
        self.game.currentIndexChanged.connect(self.change_game)
        project_row.addWidget(self.game)
        self.pack, self.episode_id = QSpinBox(), QSpinBox()
        for widget, key, label in ((self.pack, 'pack_id', 'Pack'), (self.episode_id, 'episode_id', 'Episode')):
            widget.setRange(1 if key == 'episode_id' else 0, 32767)
            widget.valueChanged.connect(lambda value, key=key: self.set_project(key, value))
            project_row.addWidget(QLabel(label))
            project_row.addWidget(widget)
        # shshd-runtime: the episode's version (episode_version.py); 0 shows as None, an export without one.
        self.episode_version = QSpinBox()
        self.episode_version.setRange(0, 65535)
        self.episode_version.setSpecialValueText('None')
        self.episode_version.setToolTip('A newer version replaces an older copy of this episode when it is imported')
        self.episode_version.valueChanged.connect(lambda value: self.set_project('episode_version', value or None))
        project_row.addWidget(QLabel('Version'))
        project_row.addWidget(self.episode_version)
        column.addLayout(project_row)
        splitter = QSplitter()
        left = QWidget()
        toolbox = QVBoxLayout(left)
        toolbox.addWidget(QLabel('ADD A STORY NODE'))
        self.node_kind = QComboBox()
        for kind in KINDS:
            if kind != 'native': self.node_kind.addItem(NAMES[kind], kind)
        toolbox.addWidget(self.node_kind)
        button = QPushButton('Add node')
        button.clicked.connect(lambda: self.add_node(self.node_kind.currentData()))
        toolbox.addWidget(button)
        for label, callback in (('Characters…', self.characters), ('Translations…', self.translations),
                                ('Emoticon images…', self.emoticon_images),
                                ('Add-ons and settings…', self.addon_settings),
                                ('Auto arrange', self.arrange), ('Copy nodes', self.copy),
                                ('Paste nodes', self.paste), ('Duplicate nodes', self.duplicate)):
            button = QPushButton(label); button.clicked.connect(callback); toolbox.addWidget(button)
        search = QLineEdit(); search.setPlaceholderText('Find label, dialogue or speaker')
        search.returnPressed.connect(lambda: self.search(search.text())); toolbox.addWidget(search)
        self.live = QCheckBox('Restart preview after edits'); toolbox.addWidget(self.live)
        self.preview_selected = QCheckBox('Preview from selected node'); toolbox.addWidget(self.preview_selected)
        toolbox.addWidget(QLabel('PROJECT IMAGES AND AUDIO'))
        self.assets = QListWidget()
        toolbox.addWidget(self.assets, 1)
        for label, callback in (('Add PNG / JPEG…', self.add_image), ('Add MP3 / WAV…', self.add_audio),
                                ('Use imported library…', self.choose_library),
                                ('Browse library images…', self.browse_library), ('Remove image', self.remove_image)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            toolbox.addWidget(button)
        self.library_label = QLabel()
        self.library_label.setWordWrap(True)
        toolbox.addWidget(self.library_label)
        splitter.addWidget(left)
        self.graph = Graph(self.project)
        self.graph.moved.connect(self.move_node)
        self.graph.selectionChanged.connect(self.select_node)
        self.view = QGraphicsView(self.graph)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setBackgroundBrush(QColor('#19232f'))
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        for label, callback in (('Zoom in', lambda: self.view.scale(1.2, 1.2)),
                                ('Zoom out', lambda: self.view.scale(1 / 1.2, 1 / 1.2)),
                                ('Fit story', lambda: self.view.fitInView(self.graph.itemsBoundingRect().adjusted(
                                    -30, -30, 30, 30), Qt.AspectRatioMode.KeepAspectRatio))):
            action = QAction(label, self)
            action.triggered.connect(callback)
            toolbar.addAction(action)
        splitter.addWidget(self.view)
        self.inspector = QScrollArea()
        self.inspector.setWidgetResizable(True)
        splitter.addWidget(self.inspector)
        splitter.setSizes([220, 730, 330])
        column.addWidget(splitter, 1)
        self.setCentralWidget(root)
        self.sharing_label = QLabel()
        self.statusBar().addPermanentWidget(self.sharing_label)
        self.refresh()
        self.statusBar().showMessage('Connect nodes with the destination fields. Drag cards to arrange your story.')

    def error(self, error):
        QMessageBox.warning(self, 'Episode creator', str(error))

    def remember(self):
        self.undo_history.append(deepcopy(self.project))
        del self.undo_history[:-100]
        self.redo_history.clear()
        self.dirty = True

    def changed(self):
        self.setWindowTitle(f'{self.project.title}{" *" if self.dirty else ""} — SHSHD Runtime Creator')
        self.sharing_label.setText('MCP: live editing ready' if self.live_editor.lease else 'MCP: save project to connect')
        for card in self.graph.cards.values():
            card.refresh()
        self.graph.draw_edges()
        if self.dirty and self.preview_process is not None and self.live.isChecked():
            self.live_timer.start(800)

    def refresh(self, *, preserve_focus=False):
        focus = QApplication.focusWidget() if preserve_focus else None
        focused_name = focus.objectName() if focus is not None else ''
        cursor = focus.textCursor() if isinstance(focus, QTextEdit) else None
        position = focus.cursorPosition() if isinstance(focus, QLineEdit) else None
        scroll = self.inspector.verticalScrollBar().value()
        for widget, value in ((self.title, self.project.title), (self.game, self.project.game),
                              (self.pack, self.project.pack_id), (self.episode_id, self.project.episode_id),
                              (self.episode_version, self.project.episode_version or 0)):
            widget.blockSignals(True)
            if isinstance(widget, QComboBox):
                widget.setCurrentIndex(widget.findData(value))
            elif isinstance(widget, QSpinBox):
                widget.setValue(value)
            else:
                widget.setText(value)
            widget.blockSignals(False)
        self.assets.clear()
        self.assets.addItems([f'{a.id} · {a.name}{" (add-on)" if a.addon else " (base)" if a.data is None else ""}'
                              for a in self.project.assets])
        self.library_label.setText('Game library: ' + (Path(self.project.library).name if self.project.library else 'none'))
        self.library_label.setToolTip(self.project.library)
        self.preview_selected.setEnabled(not self.project.native)
        if self.project.native: self.preview_selected.setChecked(False)
        self.graph.project = self.project
        self.graph.rebuild(self.selected)
        self.show_properties()
        if focused_name:
            restored = self.title if focus is self.title else self.inspector.widget().findChild(type(focus), focused_name)
            if restored is not None:
                restored.setFocus()
                if isinstance(restored, QTextEdit) and cursor is not None:
                    current = restored.textCursor()
                    end = restored.document().characterCount() - 1
                    current.setPosition(min(cursor.anchor(), end))
                    current.setPosition(min(cursor.position(), end), current.MoveMode.KeepAnchor)
                    restored.setTextCursor(current)
                elif isinstance(restored, QLineEdit) and position is not None:
                    restored.setCursorPosition(min(position, len(restored.text())))
        if preserve_focus: self.inspector.verticalScrollBar().setValue(scroll)
        self.changed()

    def set_project(self, key, value):
        if getattr(self.project, key) != value:
            self.remember()
            setattr(self.project, key, value)
            self.changed()

    def change_game(self):
        game = self.game.currentData()
        if game != self.project.game:
            if (self.project.native or any(a.data is None for a in self.project.assets)
                    or any(n.kind in ('music', 'sound') for n in self.project.nodes)):
                self.error('Start a new project to change games after using base assets or native scripts. '
                           'Game libraries and base resource IDs must stay together.')
                self.refresh()
            else:
                self.remember()
                self.project.game, self.project.library = game, ''
                self.use_player_library()
                self.refresh()

    def use_player_library(self):
        if self.discover_library and not self.project.library:
            self.project.library = player_library(self.project.game)

    def set_node(self, key, value):
        node = self.project.node(self.selected)
        if getattr(node, key) != value:
            self.remember()
            setattr(node, key, value)
            self.changed()
            if key in ('portrait', 'character'):
                self.show_properties()

    def select_node(self):
        selected = [item for item in self.graph.selectedItems() if isinstance(item, NodeItem)]
        if selected:
            self.selected = selected[0].node.id
            self.show_properties()

    def move_node(self, node_id, x, y):
        self.remember()
        node = self.project.node(node_id)
        node.x, node.y = x, y
        self.changed()

    def add_node(self, kind):
        if self.project.native:
            self.error('Native blocks keep their original instruction addresses. Create a new story for high-level nodes.'); return
        self.remember()
        position = self.view.mapToScene(self.view.viewport().rect().center())
        node = Node(uuid.uuid4().hex[:10], kind, NAMES[kind], position.x(), position.y())
        if kind == 'choice':
            node.options = [Choice('First choice'), Choice('Second choice')]
        self.project.nodes.append(node)
        if kind in NODE_ADDONS:
            # Its game plays from an add-on's art: the episode declares it, an extra unless it's the primary (owner, 2026-11-09).
            try:
                with self.open_library() as library:
                    require_node_addon(self.project, library, kind)
            except (ProjectError, ContentError, OSError) as error:
                self.statusBar().showMessage(f'{error} The episode needs it before it can be exported.')
        self.selected = node.id
        self.refresh()

    def delete_node(self):
        if self.project.native:
            self.error('Native blocks cannot be removed without invalidating existing PCs.'); return
        if len(self.project.nodes) == 1:
            return
        self.remember()
        self.project.nodes = [n for n in self.project.nodes if n.id != self.selected]
        self.selected = self.project.nodes[0].id
        self.refresh()

    def combo(self, values, current, callback):
        widget = QComboBox()
        for label, value in values:
            widget.addItem(label, value)
        index = widget.findData(current)
        if index < 0:
            widget.addItem(f'Missing: {current}', current)
            index = widget.count() - 1
        widget.setCurrentIndex(index)
        widget.currentIndexChanged.connect(lambda: callback(widget.currentData()))
        return widget

    def destination(self, current, callback):
        return self.combo([('Choose a node…', '')] + [(n.label or n.id, n.id) for n in self.project.nodes],
                          current, callback)

    def show_properties(self):
        panel = QWidget()
        form = QFormLayout(panel)
        node = next((n for n in self.project.nodes if n.id == self.selected), None)
        if node is None:
            form.addRow(QLabel('Select a story node.'))
        else:
            heading = QLabel(NAMES[node.kind])
            heading.setStyleSheet('font-size: 18px; font-weight: bold')
            form.addRow(heading)
            label = QLineEdit(node.label)
            label.setObjectName('node_label')
            label.textEdited.connect(lambda value: self.set_node('label', value))
            form.addRow('Label', label)
            if node.kind in ('dialogue', 'choice', 'input'):
                speaker = QLineEdit(node.speaker)
                speaker.setPlaceholderText('Empty for narration')
                speaker.setObjectName('speaker')
                speaker.textEdited.connect(lambda value: self.set_node('speaker', value))
                speaker.setEnabled(node.kind != 'dialogue' or not node.character)
                form.addRow('Speaker / title', speaker)
            if node.kind in ('dialogue', 'choice', 'title', 'message', 'notice', 'scene_label', 'word_game',
                             'set_text', 'text_default', 'character_name', 'picker', 'faceplace', 'faceplace_post',
                             'faceplace_link', 'tree_node', 'tree_result', 'append_text'):
                text = QTextEdit()
                text.setPlainText(node.text)
                text.setAcceptRichText(False)
                text.setObjectName('story_text')
                text.setMinimumHeight(120)
                text.textChanged.connect(lambda: self.set_node('text', text.toPlainText()))
                form.addRow('Text', text)
            if (node.kind in ('background', 'character_art', 'faceplace_link')
                    or node.kind == 'dialogue' and not node.character):
                key = 'portrait' if node.kind == 'dialogue' else 'asset'
                images = [('None', None)] + [(f'{a.id} · {a.name}', a.id) for a in self.project.assets
                                             if a.data is None or is_image(a.data)]
                form.addRow({'background': 'Background', 'faceplace_link': 'Photo'}.get(node.kind, 'Portrait'), self.combo(
                    images, getattr(node, key), lambda value: self.set_node(key, value)))
            if node.kind in ('dialogue', 'choice'):
                color = self.combo([('Gray', 0), ('Pink', 1), ('Blue', 2), ('Gold', 3)],
                                   node.theme, lambda value: self.set_node('theme', value))
                color.setEnabled(not node.character and (node.kind == 'choice' or node.portrait is not None))
                color.setToolTip('Portrait and choice color. Narration and dialogue without a portrait use the game\'s fixed style.')
                form.addRow('Color', color)
            if node.kind == 'choice':
                for i, option in enumerate(node.options):
                    field = QLineEdit(option.text)
                    field.setObjectName(f'answer_{i}')
                    field.textEdited.connect(lambda text, i=i: self.set_option(i, 'text', text))
                    form.addRow(f'Answer {i + 1}', field)
                    condition = QLineEdit(option.condition)
                    condition.setObjectName(f'condition_{i}')
                    condition.setPlaceholderText('Optional: points >= 3')
                    condition.textEdited.connect(lambda value, i=i: self.set_option(i, 'condition', value))
                    form.addRow('Enabled when', condition)
                    form.addRow('Go to', self.destination(option.target, lambda target, i=i: self.set_option(i, 'target', target)))
                buttons = QHBoxLayout()
                for label, delta in (('Add answer', 1), ('Remove last', -1)):
                    button = QPushButton(label)
                    button.clicked.connect(lambda checked=False, delta=delta: self.resize_options(delta))
                    buttons.addWidget(button)
                form.addRow(buttons)
                timer = QSpinBox()
                timer.setRange(0, 32767)
                timer.setSuffix(' ms')
                timer.setSpecialValueText('No timer')
                timer.setValue(node.timeout_ms)
                timer.valueChanged.connect(lambda value: self.set_node('timeout_ms', value))
                form.addRow('Time limit', timer)
                form.addRow('On expiry', self.combo([(f'Answer {i + 1}', i) for i in range(len(node.options))],
                            node.timeout_option, lambda value: self.set_node('timeout_option', value)))
            if node.kind in ('set', 'branch'):
                variable = QLineEdit(node.variable)
                variable.setObjectName('variable')
                variable.setPlaceholderText('e.g. helped_friend')
                variable.textEdited.connect(lambda value: self.set_node('variable', value))
                form.addRow('Variable', variable)
                value = QSpinBox()
                value.setRange(-32768, 32767)
                value.setValue(node.value)
                value.valueChanged.connect(lambda value: self.set_node('value', value))
                if node.kind == 'branch':
                    form.addRow('Comparison', self.combo([(op, op) for op in OPERATORS], node.operator,
                                lambda value: self.set_node('operator', value)))
                form.addRow('Value', value)
            if node.kind not in ('choice', 'end', 'native'):
                form.addRow('If true' if node.kind in ('branch', 'text_branch') else 'Next',
                            self.destination(node.next, lambda target: self.set_node('next', target)))
            if node.kind in ('branch', 'text_branch'):
                form.addRow('If false', self.destination(node.otherwise, lambda target: self.set_node('otherwise', target)))
            if not self.project.native:
                scene = QSpinBox(); scene.setRange(25001, 25999); scene.setValue(node.scene)
                scene.valueChanged.connect(lambda value: self.set_node('scene', value)); form.addRow('Scene group', scene)
                if node.kind in ('dialogue', 'choice', 'relationship', 'word_game', 'flag', 'expression_default',
                                 'character_art', 'character_name', 'picker', 'faceplace_post'):
                    form.addRow('Character', self.combo([('Narrator / inline speaker', '')] +
                        [(c.name, c.id) for c in self.project.characters], node.character,
                        lambda value: self.set_node('character', value)))
                if node.kind in ('dialogue', 'expression_default', 'faceplace_post'):
                    form.addRow('Expression', self.combo([('Character default', -1)] * (node.kind == 'dialogue')
                        + [(str(i), i) for i in range(5)], node.expression,
                        lambda value: self.set_node('expression', value)))
                if node.kind == 'dialogue' and self.project.game == 'shs':
                    self.presentation_rows(form, node)
                if node.kind == 'cutscene':
                    choices = [('None', 0)] + [(f'{a.id} · {a.name}', a.id) for a in cutscene_assets(self.project)]
                    form.addRow('Cutscene', self.combo(choices, parameters(node)['spec'],
                                                       lambda value: self.set_param('spec', value)))
                    timeline = QPushButton('New or edit timeline…')
                    timeline.clicked.connect(self.edit_cutscene)
                    form.addRow(timeline)
                if node.kind == 'music' and self.project.game == 'shs':
                    loops = [('None', -1)] + [(f'{a.id} · {a.name}', a.id) for a in self.project.assets
                                              if a.addon or a.data is not None and is_audio(a.data)]
                    then_loop = self.combo(loops, parameters(node)['then_loop'],
                                           lambda value: self.set_param('then_loop', value))
                    then_loop.setToolTip('An embedded track this one runs into without a gap after playing once '
                                         '(SHSHD Runtime). Other apps play this track alone.')
                    form.addRow('Then loop', then_loop)
            if parameters(node) and node.kind != 'dialogue':
                settings = QPushButton('Edit ' + ('native instructions…' if node.kind == 'native' else 'settings…'))
                settings.clicked.connect(self.node_settings); form.addRow(settings)
            if node.kind == 'native':
                data = QPushButton('Edit script data words…'); data.clicked.connect(self.native_data); form.addRow(data)
                strings = QPushButton('Edit packed text…'); strings.clicked.connect(self.native_text); form.addRow(strings)
            if node.kind in ('music', 'sound'):
                audio = QPushButton('Listen to selected resource'); audio.clicked.connect(self.listen); form.addRow(audio)
                stop = QPushButton('Stop listening'); stop.clicked.connect(self.stop_listening); form.addRow(stop)
            start = QPushButton('Start episode here')
            start.setEnabled(not self.project.native)
            start.clicked.connect(lambda: self.set_project('start', self.selected))
            form.addRow(start)
            delete = QPushButton('Delete node')
            delete.clicked.connect(self.delete_node)
            form.addRow(delete)
        old = self.inspector.takeWidget()
        if old is not None:
            old.deleteLater()
        self.inspector.setWidget(panel)

    def presentation_rows(self, form, node):
        """A dialogue line's SHSHD Runtime presentation (SHS): a second speaker, a named line's bubble colour and an
        emoticon over the speaker. Other apps show the line as SHS does."""
        p = parameters(node)
        portrait = bool(node.character) or node.portrait is not None
        note = ' SHSHD Runtime; other apps show the line as SHS does.'
        partner = self.combo([('None', '')] + [(c.name, c.id) for c in self.project.characters if c.id != node.character],
                             p['partner'], lambda value: self.set_param('partner', value))
        partner.setEnabled(portrait)
        partner.setToolTip('A second character saying the line, their portrait on the other side.' + note)
        form.addRow('Second speaker', partner)
        expression = self.combo([(str(i), i) for i in range(5)], p['partner_expression'],
                                lambda value: self.set_param('partner_expression', value))
        expression.setEnabled(portrait and bool(p['partner']))
        form.addRow('Their expression', expression)
        bubble = self.combo([('Game default', 0), ('Blue', 1), ('Pink', 2), ('Gray', 3)], p['bubble'],
                            lambda value: self.set_param('bubble', value))
        bubble.setEnabled(not portrait)
        bubble.setToolTip('The bubble of a named line without a portrait (a speaker name only).' + note)
        form.addRow('Bubble color', bubble)
        emoticon = self.combo([('None', 0)] + [(name if image is not None else f'{name} (no image yet)', i)
                                               for i, (name, image) in enumerate(zip(EMOTICONS, self.project.emoticons), 1)],
                              p['emoticon'], lambda value: self.set_param('emoticon', value))
        emoticon.setEnabled(portrait)
        emoticon.setToolTip('Shown over the speaker\'s portrait; choose the images with Emoticon images….' + note)
        form.addRow('Emoticon', emoticon)

    def set_param(self, key, value):
        node = self.project.node(self.selected)
        if parameters(node)[key] != value:
            self.set_node('params', dict(node.params, **{key: value}))
            self.show_properties()

    def emoticon_images(self):
        if self.project.native:
            self.error('Native projects keep their original presentation.'); return
        dialog = QDialog(self)
        dialog.setWindowTitle('Emoticon images')
        form = QFormLayout(dialog)
        intro = QLabel('The image each emoticon shows over a speaker\'s portrait, from this project\'s images '
                       '(SHS; SHSHD Runtime). A dialogue line picks one with its Emoticon setting.')
        intro.setWordWrap(True)
        form.addRow(intro)
        images = [('None', None)] + [(f'{a.id} · {a.name}', a.id) for a in self.project.assets
                                     if a.data is None or is_image(a.data)]
        boxes = []
        for name, current in zip(EMOTICONS, self.project.emoticons):
            boxes.append(self.combo(images, current, lambda value: None))
            form.addRow(name, boxes[-1])
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.set_project('emoticons', [box.currentData() for box in boxes])
            self.show_properties()

    def open_library(self):
        """The project's library (a context manager), or a stand-in with no add-ons when none is chosen."""
        from contextlib import nullcontext
        from types import SimpleNamespace
        if not self.project.library:
            return nullcontext(SimpleNamespace(addons=[], addon=lambda addon_id: None))
        from exp_runtime.content import ContentLibrary
        return ContentLibrary(Path(self.project.library))

    def addon_settings(self):
        """The primary add-on (its settings come with it, and the episode needs it), BREW's edition, what each declared add-on
        brings, and the translated games' settings that need no add-on (owner, 2026-11-09)."""
        from .model import ADDON_EDITIONS, FREE_SETTINGS, primary_addon
        if self.project.native:
            self.error('Native projects keep their original presentation.'); return
        if self.project.game != 'shs':
            self.error('Add-ons and their settings are for Surviving High School episodes.'); return
        try:
            with self.open_library() as library:
                available = [(addon['title'], addon['addon']) for addon in library.addons]
        except (ContentError, OSError) as error:
            self.error(error); return
        declared = {entry['id'] for entry in self.project.addons}
        available += [(entry['id'], entry['id']) for entry in self.project.addons
                      if entry['id'] not in {addon_id for _, addon_id in available}]
        primary = primary_addon(self.project)
        dialog = QDialog(self)
        dialog.setWindowTitle('Add-ons and settings')
        form = QFormLayout(dialog)
        intro = QLabel('The primary add-on gives the episode its look: its frame, relationship icons, answer music and switches. '
                       'Its pictures win where add-ons share a number. Other add-ons are extras, for their pictures, sounds '
                       'and mini-games. Players need every add-on the episode uses.'
                       + ('' if self.project.library else ' Choose an imported library to pick from its add-ons.'))
        intro.setWordWrap(True)
        form.addRow(intro)
        primary_box = self.combo([('None', None)] + available, primary['id'] if primary else None, lambda value: None)
        form.addRow('Primary add-on', primary_box)
        edition_box = QComboBox()
        form.addRow('Edition', edition_box)
        brings = QLabel()
        brings.setWordWrap(True)
        form.addRow(brings)

        titles = {addon_id: title for title, addon_id in available}

        def describe():
            """What the primary brings (its chosen edition's switch only) and what each extra adds, by the add-ons' names."""
            addon_id, edition = primary_box.currentData(), edition_box.currentData()
            lines = []
            for _, other in available:
                if other not in declared and other != addon_id:
                    continue
                own, extra = ADDON_FEATURES.get(other, ((), ()))
                name = escape(titles.get(other, other))
                if other == addon_id:
                    own = tuple(line for line in own if not line.startswith("'0") or line.startswith(f"'{edition} only: "))
                    shown = [line.split(' only: ', 1)[-1] for line in own + extra]
                    lines.append(f'<b>{name}</b> (primary): ' + (escape('; '.join(shown)) or 'its pictures and sounds'))
                else:
                    lines.append(f'<b>{name}</b> (extra): ' + (escape('; '.join(extra)) or 'its pictures and sounds'))
            brings.setText('<br>'.join(lines) or 'No add-on: the episode looks as the smartphone game does.')

        def update():
            addon_id = primary_box.currentData()
            editions = ADDON_EDITIONS.get(addon_id, ())
            edition_box.blockSignals(True)
            edition_box.clear()
            for edition in editions:
                edition_box.addItem(f"'{edition}", edition)
            if primary and primary['id'] == addon_id and primary.get('edition') in editions:
                edition_box.setCurrentIndex(editions.index(primary['edition']))
            edition_box.setEnabled(bool(editions))
            edition_box.blockSignals(False)
            describe()
        primary_box.currentIndexChanged.connect(update)
        edition_box.currentIndexChanged.connect(describe)
        update()
        form.addRow(QLabel('<b>Settings that need no add-on</b>'))
        boxes = {}
        for name, label in FREE_SETTINGS.items():
            boxes[name] = QCheckBox(label)
            boxes[name].setChecked(bool(self.project.options.get(name)))
            form.addRow(boxes[name])
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        candidate = deepcopy(self.project)
        try:
            with self.open_library() as library:
                set_primary_addon(candidate, library, primary_box.currentData(), edition_box.currentData() or '')
            candidate.options = {name: True for name, box in boxes.items() if box.isChecked()}
            drop_unused_addons(candidate)
        except (ProjectError, ContentError, OSError) as error:
            self.error(error); return
        self.remember()
        self.project = candidate
        self.refresh()

    def edit_cutscene(self):
        """The selected cutscene node's timeline: its own if it has one in the project, else a new one. An add-on's can't be edited
        here, as the project doesn't hold it."""
        node = self.project.node(self.selected)
        current = next((a for a in self.project.assets if a.id == parameters(node)['spec']), None)
        if current is not None and current.addon:
            self.error(ProjectError('That cutscene belongs to an add-on, so it can\'t be edited here.'))
            return
        spec = read_project_spec(current) if current is not None else None
        pictures = [(f'{a.id} · {a.name}', a.id) for a in self.project.assets
                    if a.addon or a.data is not None and is_image(a.data)]
        sounds = [(f'{a.id} · {a.name}', a.id) for a in self.project.assets if a.addon or a.data is not None and is_audio(a.data)]
        dialog = CutsceneDialog(spec or blank_spec(), current.name if spec else 'Cutscene', pictures, sounds, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        candidate = deepcopy(self.project)
        try:
            asset = save_cutscene(candidate, dialog.name.text().strip() or 'Cutscene', dialog.spec, current.id if spec else None)
        except ProjectError as error:
            self.error(error)
            return
        self.remember()
        self.project = candidate
        self.project.node(self.selected).params['spec'] = asset.id
        self.changed()
        self.refresh()

    def set_option(self, index, key, value):
        option = self.project.node(self.selected).options[index]
        if getattr(option, key) != value:
            self.remember()
            setattr(option, key, value)
            self.changed()

    def resize_options(self, delta):
        node = self.project.node(self.selected)
        if 2 <= len(node.options) + delta <= 8:
            self.remember()
            if delta > 0:
                node.options.append(Choice())
            else:
                node.options.pop()
                node.timeout_option = min(node.timeout_option, len(node.options) - 1)
            self.refresh()

    def undo(self):
        if self.undo_history:
            self.redo_history.append(deepcopy(self.project))
            self.project = self.undo_history.pop()
            self.dirty = True
            self.refresh()

    def redo(self):
        if self.redo_history:
            self.undo_history.append(deepcopy(self.project))
            self.project = self.redo_history.pop()
            self.dirty = True
            self.refresh()

    def add_image(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Add an image', '', 'Images (*.png *.jpg *.jpeg)')
        if path:
            try:
                png = image_png(Path(path).read_bytes())
                candidate = deepcopy(self.project)
                candidate.add_image(Path(path).name, png)
                self.remember()
                self.project = candidate
                self.refresh()
            except (ValueError, OSError) as error:
                self.error(error)

    def add_audio(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Add music or a sound effect', '', 'Audio (*.mp3 *.wav)')
        if path:
            try:
                candidate = deepcopy(self.project)
                candidate.add_audio(Path(path).name, Path(path).read_bytes())
                self.remember()
                self.project = candidate
                self.refresh()
            except (ValueError, OSError) as error:
                self.error(error)

    def remove_image(self):
        row = self.assets.currentRow()
        if row >= 0:
            self.remember()
            self.project.assets.pop(row)
            drop_unused_addons(self.project)
            self.refresh()

    def choose_library(self):
        path = QFileDialog.getExistingDirectory(self, 'Choose the game folder containing library.json', self.project.library)
        if not path:
            return
        try:
            from exp_runtime.content import ContentLibrary
            with ContentLibrary(Path(path)) as library:
                if library.game_id != self.project.game:
                    raise ProjectError('Choose a library for the selected game, or start a project for the other game')
            self.set_project('library', str(Path(path).resolve()))
            self.refresh()
        except (ContentError, OSError) as error:
            self.error(error)

    def browse_library(self):
        if not self.project.library:
            self.choose_library()
        if not self.project.library:
            return
        try:
            from exp_runtime.content import ContentLibrary
            with ContentLibrary(Path(self.project.library)) as library:
                browser = LibraryBrowser(library, self)
                if browser.exec() == QDialog.DialogCode.Accepted:
                    candidate = deepcopy(self.project)
                    if browser.addon:
                        (use_addon_asset if browser.reference else copy_addon_asset)(candidate, library, browser.addon, browser.resource)
                    else:
                        import_library_image(candidate, library, browser.resource, browser.episode)
                    self.remember()
                    self.project = candidate
                    self.refresh()
        except (ContentError, OSError) as error:
            self.error(error)

    def confirm_saved(self):
        if not self.dirty:
            return True
        result = QMessageBox.question(self, 'Unsaved episode', 'Save your project before closing it?',
                    QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        return self.save() if result == QMessageBox.StandardButton.Save else result == QMessageBox.StandardButton.Discard

    def replace_project(self, project, path=None):
        path = Path(path) if path else None
        previous = self.live_editor.lease.path if self.live_editor.lease else None
        self.live_editor.attach(path)
        try:
            if path:
                with guard(path): revision = digest(path.read_bytes()) if path.exists() else None
            else: revision = None
        except (ContentError, OSError):
            self.live_editor.attach(previous)
            raise
        self.recovery.remove()
        self.project, self.path = project, path
        self.saved_path = path.resolve() if path else None
        self.disk_revision = revision
        self.use_player_library()
        self.selected = project.start
        self.undo_history, self.redo_history = [], []
        self.dirty = False
        self.refresh()

    def new(self):
        if self.confirm_saved():
            self.replace_project(Project())

    def open(self):
        if not self.confirm_saved():
            return
        path, _ = QFileDialog.getOpenFileName(self, 'Open an episode project', '', 'Episode projects (*.expproj)')
        if path:
            try:
                # Claim the live document before reading; MCP writes now go
                # through this window rather than racing the file load.
                previous = self.live_editor.lease.path if self.live_editor.lease else None
                self.live_editor.attach(path)
                try:
                    with guard(path): data = Path(path).read_bytes()
                    self.replace_project(project_from_bytes(data, path), path)
                    self.disk_revision = digest(data)
                except (ContentError, OSError):
                    self.live_editor.attach(previous)
                    raise
            except (ContentError, OSError) as error:
                self.error(error)

    def save(self):
        if self.path is None:
            return self.save_as()
        previous = self.live_editor.lease.path if self.live_editor.lease else None
        try:
            self.live_editor.attach(self.path)
            with guard(self.path):
                info = session_info(self.path)
                if info is None or info['token'] != self.live_editor.lease.record['token']:
                    raise SharingError('Desktop ownership changed; reopen the project before saving')
                actual = digest(self.path.read_bytes()) if self.path.exists() else None
                if self.saved_path == self.path.resolve() and actual != self.disk_revision:
                    raise ProjectError('Project changed on disk; use Save as to keep your edits, or reopen the changed file.')
                save_project(self.project, self.path)
                self.disk_revision = digest(self.path.read_bytes())
                self.saved_path = self.path.resolve()
            self.dirty = False
            self.recovery.remove()
            self.changed()
            self.statusBar().showMessage(f'Saved {self.path.name}')
            return True
        except (ContentError, OSError) as error:
            self.live_editor.attach(previous)
            self.error(error)
            return False

    def save_as(self):
        path = self.save_destination('Save editable episode project',
                                    self.path or Path('episode.expproj'), '.expproj', 'Episode projects')
        if not path:
            return False
        previous = self.path
        self.path = path
        if self.save():
            return True
        self.path = previous
        return False

    def save_destination(self, title, initial, suffix, label):
        path, _ = QFileDialog.getSaveFileName(self, title, str(initial), f'{label} (*{suffix})')
        if not path:
            return None
        destination = Path(path if Path(path).suffix.lower() == suffix else path + suffix)
        # The native dialog only confirmed the name it returned. If we add an
        # extension, confirm any existing file at that final destination too.
        if destination != Path(path) and destination.exists():
            if QMessageBox.question(self, title, f'{destination.name} already exists. Replace it?',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                return None
        return destination

    def validate(self):
        try:
            data = compile_project(self.project)
            self.statusBar().showMessage(f'Ready to export: {len(self.project.nodes)} nodes, {len(data):,} bytes')
            return True
        except ContentError as error:
            self.error(error)
            return False

    def export(self):
        if not self.validate():
            return
        destination = self.save_destination('Export native EXP episode', 'episode.exp', '.exp', 'EXP episodes')
        if destination:
            try:
                export_project(self.project, destination)
                self.statusBar().showMessage(f'Exported {destination.name} for {self.project.game.upper()} in SHSHD Runtime')
            except (ContentError, OSError) as error:
                self.error(error)

    def preview(self):
        if self.preview_process is not None:
            self.statusBar().showMessage('Close the existing preview window to start a new preview.')
            return
        if not self.project.library:
            self.choose_library()
        if not self.project.library or not self.validate():
            return
        try:
            self.preview_directory = tempfile.TemporaryDirectory(prefix='exp-creator-')
            path = Path(self.preview_directory.name) / 'preview.exp'
            export_project(self.project, path) if not self.preview_selected.isChecked() else path.write_bytes(
                compile_project(self.project, start=self.selected))
            process = QProcess(self)
            self.preview_process = process
            process.setProgram(sys.executable)
            process.setArguments(([] if getattr(sys, 'frozen', False) else ['-m', 'exp_runtime.creator']) + ['--preview', str(path),
                                  '--library', self.project.library, '--game', self.project.game])
            process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
            self.preview_output = ''
            process.readyReadStandardOutput.connect(self.read_preview_output)
            process.finished.connect(self.preview_finished)
            process.errorOccurred.connect(self.preview_error)
            process.start()
        except (ContentError, OSError) as error:
            self.cleanup_preview()
            self.error(error)

    def export_original(self):
        if not self.validate():
            return
        reference, _ = QFileDialog.getOpenFileName(self,
            'Choose an installed EXP from the matching original game to use its catalog identity', '', 'EXP episodes (*.exp)')
        if not reference:
            return
        destination = self.save_destination('Save a separate replacement EXP',
                                            Path(reference).name, '.exp', 'EXP episodes')
        if destination:
            try:
                metadata = self.export_slot(Path(reference), destination)
                if metadata is None:
                    return
                QMessageBox.information(self, 'Original app export',
                    f'Exported pack {metadata.pack_id}, episode {metadata.episode_id}.\n\n'
                    f'Install the replacement under the original catalog filename: {Path(reference).name}\n'
                    'Use a copy of your original game data and start a new playthrough. '
                    'The original apps do not have an EXP file picker. See docs/CREATOR.md for installation and verification limits.')
            except (ContentError, OSError) as error:
                self.error(error)

    def export_slot(self, reference, destination):
        """The slot's export. One that takes add-on assets is blocked, with the offer to pack them in; None if it's declined."""
        try:
            return export_native_slot(self.project, reference, destination)
        except AddonsNeeded as needed:
            answer = QMessageBox.question(self, 'Original app export', f'{needed}\n\nPack them into this export? Your project stays as '
                                          'it is, and the file gets larger.')
            if answer != QMessageBox.StandardButton.Yes:
                return None
            if not self.project.library:
                self.choose_library()
            if not self.project.library:
                return None
            from exp_runtime.content import ContentLibrary
            with ContentLibrary(Path(self.project.library)) as library:
                return export_native_slot(self.project, reference, destination, pack_from=library)

    def read_preview_output(self):
        if self.preview_process is not None:
            self.preview_output = (self.preview_output + bytes(self.preview_process.readAllStandardOutput()).decode(
                'utf-8', errors='replace'))[-12000:]

    def preview_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            message = self.preview_process.errorString()
            self.cleanup_preview()
            self.error(message)

    def preview_finished(self, code, status):
        self.read_preview_output()
        output = self.preview_output
        self.cleanup_preview()
        if code:
            self.error(output or 'The preview player could not start')

    def cleanup_preview(self):
        if self.preview_process is not None:
            self.preview_process.deleteLater()
            self.preview_process = None
        if self.preview_directory is not None:
            self.preview_directory.cleanup()
            self.preview_directory = None

    def autosave(self):
        if self.dirty:
            try: self.recovery.write(self.project, self.path)
            except (ContentError, OSError) as error: self.statusBar().showMessage(f'Autosave failed: {error}')

    def focus_node(self, key):
        if key in self.graph.cards:
            self.graph.clearSelection(); self.graph.cards[key].setSelected(True)
            self.view.centerOn(self.graph.cards[key])

    def search(self, query):
        matches = [n.id for n in self.project.nodes if query.casefold() in
                   (n.id + ' ' + n.label + ' ' + n.speaker + ' ' + n.text).casefold()]
        if matches:
            index = (matches.index(self.selected) + 1) % len(matches) if self.selected in matches else 0
            self.focus_node(matches[index])
        else: self.statusBar().showMessage('No matching nodes')

    def arrange(self):
        try:
            candidate = deepcopy(self.project); auto_layout(candidate)
            self.remember(); self.project = candidate; self.refresh()
        except ProjectError as error: self.error(error)

    def copy(self):
        try:
            ids = {item.node.id for item in self.graph.selectedItems() if isinstance(item, NodeItem)} or {self.selected}
            QApplication.clipboard().setText(copy_nodes(self.project, ids))
        except ProjectError as error: self.error(error)

    def paste(self):
        try:
            candidate = deepcopy(self.project)
            ids = paste_nodes(candidate, QApplication.clipboard().text())
            self.remember(); self.project = candidate; self.selected = ids[0]; self.refresh()
        except ProjectError as error: self.error(error)

    def duplicate(self):
        if not self.project.native: self.copy(); self.paste()

    def characters(self):
        if self.project.native:
            self.error('Original character definitions remain in their native instructions.'); return
        dialog = ListDialog([asdict(c) for c in self.project.characters], self, 'Characters',
                            template=asdict(Character(uuid.uuid4().hex[:10])))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                candidate = deepcopy(self.project); candidate.characters = [Character(**r) for r in dialog.value]
                validate_structure(candidate)
                self.remember(); self.project = candidate; self.refresh()
            except (ValueError, TypeError) as error: self.error(error)

    def translations(self):
        dialog = TranslationsDialog(self.project, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.remember(); self.project.locales = dialog.locales
            self.project.language = dialog.current; self.refresh()

    def node_settings(self):
        node = self.project.node(self.selected)
        dialog = RecordDialog(parameters(node), self, NAMES[node.kind] + ' settings')
        if dialog.exec() == QDialog.DialogCode.Accepted: self.set_node('params', dialog.value)

    def native_text(self):
        from .native import packed_strings, edit_packed_text
        from PySide6.QtWidgets import QInputDialog
        script = self.project.node(self.selected).params['script']
        candidates = packed_strings(self.project, script)
        labels = [f'{item["address"]}: {item["text"][:100]}' for item in candidates]
        if not labels:
            self.error('No printable packed strings found in this main data bank.'); return
        label, accepted = QInputDialog.getItem(self, 'Packed text candidates',
            'Confirm the word address used by the instruction before editing.', labels, editable=False)
        if not accepted: return
        selected = candidates[labels.index(label)]
        text, accepted = QInputDialog.getMultiLineText(self, 'Replace packed text',
            'The replacement must fit the original allocation; native addresses stay fixed.', selected['text'])
        if accepted:
            try:
                candidate = deepcopy(self.project)
                edit_packed_text(candidate, script, selected['address'], text)
                self.remember(); self.project = candidate; self.refresh()
            except ValueError as error: self.error(error)

    def native_data(self):
        from .native import _resources, set_data_words
        from exp_runtime.decode.bytecode import decode_program
        script = self.project.node(self.selected).params['script']
        program = decode_program(_resources(self.project)[script])
        dialog = RecordDialog({'main': list(program.main_words), 'extra': list(program.extra_words)}, self, 'Native data words')
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                candidate = deepcopy(self.project)
                set_data_words(candidate, script, dialog.value['main'])
                set_data_words(candidate, script, dialog.value['extra'], extra=True)
                self.remember(); self.project = candidate; self.refresh()
            except ValueError as error: self.error(error)

    def import_exp(self):
        if not self.confirm_saved(): return
        path, _ = QFileDialog.getOpenFileName(self, 'Import an EXP as an editable project', '', 'EXP episodes (*.exp)')
        if path:
            from .native import import_exp
            try:
                project = import_exp(Path(path).read_bytes(), game=self.project.game)
                self.replace_project(project); self.dirty = True; self.changed()
                self.statusBar().showMessage('Imported native blocks. Instruction addresses are fixed.' if project.native
                                            else 'Restored the editable story graph from EXP.')
            except (ContentError, OSError) as error: self.error(error)

    def debug(self):
        try:
            dialog = DebugDialog(self.project, self, self.focus_node,
                                 self.selected if self.preview_selected.isChecked() else None)
            dialog.exec()
        except (ValueError, OSError) as error: self.error(error)

    def restart_preview(self):
        if not self.live.isChecked() or self.preview_process is None: return
        self.preview_process.blockSignals(True); self.preview_process.terminate()
        if not self.preview_process.waitForFinished(1500):
            self.preview_process.kill(); self.preview_process.waitForFinished(1500)
        self.cleanup_preview(); self.preview()

    def listen(self):
        from io import BytesIO
        from exp_runtime.content import ContentLibrary
        from exp_runtime.audio import music_cue
        import pygame
        node = self.project.node(self.selected); resource = parameters(node)['resource']
        cue = music_cue(resource, game=self.project.game)
        embedded = next((a.data for a in self.project.assets if a.id == resource and a.data is not None), None)
        if embedded is None and not self.project.library: self.choose_library()
        if embedded is None and not self.project.library: return
        addon = next((a.addon for a in self.project.assets if a.id == resource and a.addon), '')
        if addon:
            from exp_runtime.content import ContentLibrary
            try:
                with ContentLibrary(Path(self.project.library)) as library:
                    held = library.addon(addon)
                    if held is None:
                        raise ProjectError(f'The library has no {addon} add-on')
                    embedded = held[1].read(resource)
            except (ContentError, OSError) as error:
                self.error(error)
                return
        try:
            if embedded is not None:
                data = embedded
            else:
                with ContentLibrary(Path(self.project.library)) as library:
                    data = library.read_asset(cue.asset_id if node.kind == 'music' else resource)
            pygame.mixer.init()
            if node.kind == 'music':
                pygame.mixer.music.load(BytesIO(data)); pygame.mixer.music.play(start=cue.start_ms / 1000)
            else: pygame.mixer.Sound(BytesIO(data)).play()
        except (ContentError, OSError, pygame.error) as error: self.error(error)

    def stop_listening(self):
        if 'pygame' in sys.modules:
            import pygame
            if pygame.mixer.get_init(): pygame.mixer.stop(); pygame.mixer.music.stop()

    def closeEvent(self, event):
        if not self.confirm_saved():
            event.ignore()
            return
        if self.preview_process is not None:
            self.preview_process.blockSignals(True)
            self.preview_process.terminate()
            if not self.preview_process.waitForFinished(2000):
                self.preview_process.kill()
                self.preview_process.waitForFinished(2000)
            self.cleanup_preview()
        self.recovery.remove()
        self.stop_listening()
        self.live_editor.close()
        # QGraphicsScene emits selectionChanged while destroying selected
        # items. The scene's C++ object may already be gone at that point.
        self.graph.blockSignals(True)
        event.accept()


def launch(path=None):
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName('SHSHD Runtime Creator')
    window = Editor(path=path)
    app.setWindowIcon(window.windowIcon())
    window.show()
    for path in sorted(window.recovery.path.parent.glob('*.recovery.json')):
        try:
            project, source = Recovery.read(path)
            if QMessageBox.question(window, 'Recover unsaved work', f'Recover "{project.title}"?') == QMessageBox.StandardButton.Yes:
                window.replace_project(project, source); window.dirty = True
                window.recovery.path = path; window.changed(); break
        except (ContentError, OSError) as error: window.statusBar().showMessage(str(error))
    app.exec()
