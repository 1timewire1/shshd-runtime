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
