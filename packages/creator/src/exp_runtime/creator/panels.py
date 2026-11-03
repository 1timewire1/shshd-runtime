"""Structured authoring dialogs shared by character and minigame inspectors."""
from copy import deepcopy
import json

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton, QScrollArea,
    QSpinBox, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget)

from .model import ProjectError


LIST_TEMPLATES = {
    'symbols': ['A', 26000],
    'expressions': None,
    'tutorials': dict(title='Practice', body='Connect the word.', position=0, tap_to_advance=False,
                      hide_board=False, width=3, height=3, heading='Practice', prompt='Find CAT',
                      words=['CAT'], highlight=True, fixed_board='CAT\nAAA\nAAA', show_hints=True,
                      animate=True, timed=False, failure_next=-1, success_next=-2),
}

def value_field(value, parent=None, key=None):
    """Return a widget and a typed getter; containers have their own row editor."""
    if isinstance(value, (dict, list)):
        current = deepcopy(value)
        button = QPushButton(f'Edit {len(value)} ' + ('fields…' if isinstance(value, dict) else 'items…'), parent)
        def edit():
            dialog = (RecordDialog(current, parent) if isinstance(current, dict) else
                      ListDialog([None] * 5 if key == 'expressions' and not current else current,
                                 parent, template=LIST_TEMPLATES.get(key)))
            if dialog.exec() == QDialog.DialogCode.Accepted:
                current.clear(); current.update(dialog.value) if isinstance(current, dict) else current.extend(dialog.value)
                button.setText(f'Edit {len(current)} items…')
        button.clicked.connect(edit)
        return button, lambda: deepcopy(current)
    if type(value) is bool:
        widget = QCheckBox(parent); widget.setChecked(value)
        return widget, widget.isChecked
    if type(value) is int:
        widget = QSpinBox(parent); widget.setRange(-32768, 65535); widget.setValue(value)
        return widget, widget.value
    widget = QLineEdit('null' if value is None else str(value), parent)
    return widget, (lambda: json.loads(widget.text())) if value is None else widget.text


class RecordDialog(QDialog):
    def __init__(self, record, parent=None, title='Edit fields'):
        super().__init__(parent)
        self.setWindowTitle(title); self.resize(560, 650)
        layout = QVBoxLayout(self)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        panel = QWidget(); form = QFormLayout(panel); self.getters = {}
        for key, value in record.items():
            field, getter = value_field(value, self, key)
            field.setObjectName(key); self.getters[key] = getter
            form.addRow(key.replace('_', ' ').capitalize(), field)
        scroll.setWidget(panel); layout.addWidget(scroll)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def accept(self):
        try:
            self.value = {key: getter() for key, getter in self.getters.items()}
        except (ValueError, TypeError) as error:
            QMessageBox.warning(self, 'Invalid value', str(error)); return
        super().accept()


class ListDialog(QDialog):
    def __init__(self, values, parent=None, title='Edit items', template=None):
        super().__init__(parent)
        self.value = deepcopy(values); self.template = template
        self.setWindowTitle(title); self.resize(650, 480)
        layout = QVBoxLayout(self); self.items = QListWidget(); layout.addWidget(self.items)
        buttons = QHBoxLayout()
        for label, callback in (('Edit', self.edit), ('Add', self.add), ('Duplicate', self.duplicate),
                                ('Remove', self.remove), ('Move up', lambda: self.move(-1)),
                                ('Move down', lambda: self.move(1))):
            button = QPushButton(label); button.clicked.connect(callback); buttons.addWidget(button)
        layout.addLayout(buttons)
        self.items.itemDoubleClicked.connect(self.edit)
        done = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        done.accepted.connect(self.accept); done.rejected.connect(self.reject); layout.addWidget(done)
        self.refresh()

    def refresh(self, row=0):
        self.items.clear()
        for index, value in enumerate(self.value):
            self.items.addItem(f'{index + 1}. ' + (value.get('name', value.get('heading', str(value)))
                                               if isinstance(value, dict) else str(value)))
        self.items.setCurrentRow(row)

    def edit(self, *unused):
        row = self.items.currentRow()
        if row < 0: return
        value = self.value[row]
        if isinstance(value, list):
            dialog = ListDialog(value, self)
        else:
            dialog = RecordDialog(value if isinstance(value, dict) else {'value': value}, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.value[row] = dialog.value if isinstance(value, (list, dict)) else dialog.value['value']
            self.refresh(row)

    def add(self):
        self.value.append(deepcopy(self.template if self.template is not None else self.value[-1] if self.value else ''))
        if isinstance(self.value[-1], dict) and 'id' in self.value[-1] and isinstance(self.value[-1]['id'], str):
            import uuid
            self.value[-1]['id'] = uuid.uuid4().hex[:10]
        self.refresh(len(self.value) - 1); self.edit()

    def duplicate(self):
        row = self.items.currentRow()
        if row >= 0:
            self.value.insert(row + 1, deepcopy(self.value[row]))
            if isinstance(self.value[row + 1], dict) and isinstance(self.value[row + 1].get('id'), str):
                import uuid
                self.value[row + 1]['id'] = uuid.uuid4().hex[:10]
            self.refresh(row + 1)

    def remove(self):
        row = self.items.currentRow()
        if row >= 0:
            self.value.pop(row); self.refresh(max(0, row - 1))

    def move(self, delta):
        row = self.items.currentRow(); other = row + delta
        if 0 <= row < len(self.value) and 0 <= other < len(self.value):
            self.value[row], self.value[other] = self.value[other], self.value[row]; self.refresh(other)


class CutsceneDialog(QDialog):
    """shshd-runtime: a storyboard cutscene's timeline: tables of shots, overlays and sounds (cutscenes.py). Times are milliseconds. A
    shot's window is the part of its picture that fills the frame, and one the frame's size is the sharpest and cheapest to draw. Preview
    from the node plays it."""
    SHOT_COLUMNS = ('Picture', 'Start', 'End', 'From X', 'From Y', 'From W', 'From H', 'To X', 'To Y', 'To W', 'To H', 'Ease out')
    OVERLAY_COLUMNS = ('Picture', 'Start', 'End', 'From center X', 'From center Y', 'From W', 'From H',
                       'To center X', 'To center Y', 'To W', 'To H')
    SOUND_COLUMNS = ('At', 'Sound')

    def __init__(self, spec, name, pictures, sounds, parent=None):
        """`pictures`, `sounds`: [(label, resource)] of what the project holds."""
        super().__init__(parent)
        self.setWindowTitle('Storyboard cutscene'); self.resize(1120, 720)
        self.pictures, self.sounds, self.spec = pictures, sounds, None
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(name, self)
        form.addRow('Name', self.name)
        self.width_field, self.height_field = self.number(spec['size'][0], 1, 8192), self.number(spec['size'][1], 1, 8192)
        size = QHBoxLayout(); size.addWidget(self.width_field); size.addWidget(self.height_field)
        form.addRow('Frame size', size)
        self.hold = self.number(spec['hold'], 0, 3600000)
        self.hold.setToolTip('Where it stays until a press or Autoplay: its title card, if it has one.')
        form.addRow('Holds at', self.hold)
        self.skip = self.number(spec['skip'], 0, 3600000)
        self.skip.setToolTip('Where a press before it jumps to.')
        form.addRow('A press jumps to', self.skip)
        self.music = QComboBox(self)
        self.music.addItem('None: its own clock', -1)
        for label, resource in sounds:
            self.music.addItem(label, resource)
        at = self.music.findData(spec.get('music', -1))
        self.music.setCurrentIndex(max(0, at))
        self.music.setToolTip('The track the clock follows, so sounds land on its beats. Start it just before this node.')
        form.addRow('Follows the music', self.music)
        layout.addLayout(form)
        self.shots = self.table(self.SHOT_COLUMNS, layout, 'Shots', self.add_shot)
        for shot in spec['shots']:
            self.add_shot(shot)
        self.overlays = self.table(self.OVERLAY_COLUMNS, layout, 'Overlays', self.add_overlay)
        for overlay in spec.get('overlays', ()):
            self.add_overlay(overlay)
        self.sound_rows = self.table(self.SOUND_COLUMNS, layout, 'Sounds', self.add_sound)
        for sound in spec.get('sounds', ()):
            self.add_sound(sound)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def number(self, value, low=-100000, high=100000):
        field = QSpinBox(self); field.setRange(low, high); field.setValue(int(round(value)))
        return field

    def table(self, columns, layout, title, add):
        row = QHBoxLayout()
        row.addWidget(QLabel(title, self)); row.addStretch()
        adding, removing = QPushButton('Add', self), QPushButton('Remove', self)
        adding.clicked.connect(lambda: add()); row.addWidget(adding); row.addWidget(removing)
        layout.addLayout(row)
        table = QTableWidget(0, len(columns), self)
        table.setHorizontalHeaderLabels(list(columns))
        removing.clicked.connect(lambda: table.removeRow(table.currentRow()) if table.currentRow() >= 0 else None)
        layout.addWidget(table, 1)
        return table

    def picker(self, choices, current):
        box = QComboBox(self)
        for label, resource in choices:
            box.addItem(label, resource)
        box.setCurrentIndex(max(0, box.findData(current)))
        return box

    def add_shot(self, shot=None):
        from .cutscenes import blank_shot
        shot = shot or blank_shot(self.next_start(self.shots))
        row = self.shots.rowCount(); self.shots.insertRow(row)
        self.shots.setCellWidget(row, 0, self.picker(self.pictures, shot['image']))
        for column, value in enumerate((shot['start'], shot['end'], *shot['from'], *shot['to']), 1):
            self.shots.setCellWidget(row, column, self.number(value, -100000, 3600000))
        ease = QCheckBox(self); ease.setChecked(shot.get('ease') == 'out')
        self.shots.setCellWidget(row, 11, ease)

    def add_overlay(self, overlay=None):
        from .cutscenes import blank_overlay
        overlay = overlay or blank_overlay()
        row = self.overlays.rowCount(); self.overlays.insertRow(row)
        self.overlays.setCellWidget(row, 0, self.picker(self.pictures, overlay['image']))
        for column, value in enumerate((overlay['start'], overlay['end'], *overlay['from'], *overlay['to']), 1):
            self.overlays.setCellWidget(row, column, self.number(value, -100000, 3600000))

    def add_sound(self, sound=None):
        sound = sound or dict(at=0, sound=0)
        row = self.sound_rows.rowCount(); self.sound_rows.insertRow(row)
        self.sound_rows.setCellWidget(row, 0, self.number(sound['at'], 0, 3600000))
        self.sound_rows.setCellWidget(row, 1, self.picker(self.sounds, sound['sound']))

    def next_start(self, table):
        rows = table.rowCount()
        return table.cellWidget(rows - 1, 2).value() if rows else 0

    def read_row(self, table, row, count):
        return [table.cellWidget(row, column).value() for column in range(1, count)]

    def current_spec(self):
        """The tables as a spec, its shots and sounds in time order, as the format wants."""
        from .cutscenes import blank_spec
        spec = blank_spec()
        spec.update(size=[self.width_field.value(), self.height_field.value()], hold=self.hold.value(), skip=self.skip.value())
        if self.music.currentData() != -1:
            spec['music'] = self.music.currentData()
        for row in range(self.shots.rowCount()):
            start, end, *numbers = self.read_row(self.shots, row, 11)
            shot = {'image': self.shots.cellWidget(row, 0).currentData(), 'start': start, 'end': end, 'from': numbers[:4], 'to': numbers[4:]}
            if self.shots.cellWidget(row, 11).isChecked():
                shot['ease'] = 'out'
            spec['shots'].append(shot)
        for row in range(self.overlays.rowCount()):
            start, end, *numbers = self.read_row(self.overlays, row, 11)
            spec['overlays'].append({'image': self.overlays.cellWidget(row, 0).currentData(), 'start': start, 'end': end,
                                     'from': numbers[:4], 'to': numbers[4:]})
        for row in range(self.sound_rows.rowCount()):
            spec['sounds'].append(dict(at=self.sound_rows.cellWidget(row, 0).value(), sound=self.sound_rows.cellWidget(row, 1).currentData()))
        spec['shots'].sort(key=lambda shot: shot['start'])
        spec['sounds'].sort(key=lambda sound: sound['at'])
        return spec

    def accept(self):
        from .cutscenes import spec_bytes
        spec = self.current_spec()
        try:
            spec_bytes(spec)
        except ProjectError as error:
            QMessageBox.warning(self, 'Storyboard cutscene', str(error))
            return
        self.spec = spec
        super().accept()


class TranslationsDialog(QDialog):
    def __init__(self, project, parent=None):
        from .features import text_fields
        super().__init__(parent)
        self.setWindowTitle('Translations'); self.resize(1000, 600)
        self.locales = deepcopy(project.locales); self.fields = text_fields(project)
        layout = QVBoxLayout(self); self.language = QComboBox()
        for name, code in (('English', 'en'), ('French', 'fr'), ('Italian', 'it'), ('German', 'de'), ('Spanish', 'es')):
            self.language.addItem(name, code)
        self.language.setCurrentIndex(self.language.findData(project.language))
        layout.addWidget(self.language)
        layout.addWidget(QLabel('Empty translations use the original text. Story text uses native Latin-1 encoding.'))
        self.table = QTableWidget(0, 3); self.table.setHorizontalHeaderLabels(['Field', 'Original', 'Translation'])
        layout.addWidget(self.table); self.current = self.language.currentData(); self.populate()
        self.language.currentIndexChanged.connect(self.change)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def populate(self):
        from PySide6.QtCore import Qt
        self.table.setRowCount(len(self.fields))
        for row, (key, value) in enumerate(self.fields.items()):
            for column, text in enumerate((key, value, self.locales.get(self.current, {}).get(key, ''))):
                item = QTableWidgetItem(text)
                if column < 2: item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()

    def store(self):
        self.locales[self.current] = {key: self.table.item(row, 2).text() for row, key in enumerate(self.fields)
                                     if self.table.item(row, 2).text()}

    def change(self):
        self.store(); self.current = self.language.currentData(); self.populate()

    def accept(self):
        self.store(); super().accept()


class DebugDialog(QDialog):
    def __init__(self, project, parent=None, select=None, start=None):
        from .debugger import DebugSession
        super().__init__(parent)
        self.debug = DebugSession(project, start=start); self.select = select
        self.setWindowTitle('Story debugger'); self.resize(800, 650)
        layout = QVBoxLayout(self); row = QHBoxLayout()
        for label, callback in (('Step node', lambda: self.execute(step=True)), ('Run', self.execute)):
            button = QPushButton(label); button.clicked.connect(callback); row.addWidget(button)
        layout.addLayout(row)
        self.breakpoints = QLineEdit(); self.breakpoints.setPlaceholderText('Breakpoint node IDs, separated by commas')
        self.breakpoints.editingFinished.connect(lambda: setattr(self.debug, 'breakpoints',
            set(value.strip() for value in self.breakpoints.text().split(',') if value.strip())))
        layout.addWidget(self.breakpoints)
        self.output = QTextEdit(); self.output.setReadOnly(True); layout.addWidget(self.output)
        row = QHBoxLayout(); self.answer = QLineEdit(); self.answer.setPlaceholderText('Text, or zero-based choice/word/play index')
        row.addWidget(self.answer)
        button = QPushButton('Submit / continue'); button.clicked.connect(self.submit); row.addWidget(button)
        button = QPushButton('Advance clock 1s'); button.clicked.connect(lambda: self.execute(milliseconds=1000)); row.addWidget(button)
        layout.addLayout(row)
        row = QHBoxLayout(); self.variable = QLineEdit(); self.variable.setPlaceholderText('Numeric variable name')
        self.value = QSpinBox(); self.value.setRange(-32768, 32767)
        row.addWidget(self.variable); row.addWidget(self.value)
        button = QPushButton('Set value'); button.clicked.connect(self.set_variable); row.addWidget(button)
        layout.addLayout(row); self.refresh()

    def refresh(self):
        state = self.debug.state()
        self.output.setPlainText(json.dumps(state, indent=2, ensure_ascii=False))
        if self.select and state['node']: self.select(state['node'])

    def execute(self, checked=False, **kwargs):
        try:
            self.debug.resume(**kwargs); self.refresh()
        except ValueError as error:
            QMessageBox.warning(self, 'Execution stopped', str(error)); self.refresh()

    def submit(self):
        action = self.debug.state()['action']
        value = self.answer.text()
        if action == 'character_picker' and not value.strip():
            value = None  # Confirms the selected look.
        elif action in ('choice', 'word_game', 'football', 'character_picker'):
            try: value = int(value)
            except ValueError:
                QMessageBox.warning(self, 'Choose an answer', 'Enter a zero-based answer index.'); return
        elif action != 'text_input': value = None
        self.execute(answer=value, provide_answer=True)

    def set_variable(self):
        try:
            self.debug.set_variable(self.variable.text(), self.value.value()); self.refresh()
        except ProjectError as error:
            QMessageBox.warning(self, 'Variable', str(error))
