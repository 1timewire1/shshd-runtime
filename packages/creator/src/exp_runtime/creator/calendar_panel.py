"""shshd-runtime: the Calendar panel (CREATOR_CALENDAR_DESIGN.md; owner, 2026-11-17): the project's calendars, each with its dates,
school days, day, cards, After node and its table of events, and what the table puts on each day."""
from copy import deepcopy
import uuid

from PySide6.QtCore import QTime
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QPlainTextEdit, QPushButton, QSpinBox, QSplitter, QTableWidget, QTimeEdit,
                               QVBoxLayout, QWidget)

from .calendar import MONTH_DAYS, SHS_BADGE_ICONS, WEEKDAYS, WHEN, blank_calendar, blank_event, preview, validate_calendars
from .model import Choice, Node, ProjectError

COLUMNS = ('Name', 'Starts at', 'When', 'Date', 'Until', 'Weekdays', 'Time', 'Timed', 'Length', 'First', 'Icon', 'Condition',
           'Badge')
SHORT_DAYS = ('Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat')


def minutes_time(minutes):
    return QTime(min(minutes, 1439) // 60, min(minutes, 1439) % 60)


def time_minutes(time):
    return time.hour() * 60 + time.minute()


def date_text(value):
    return f'{value[0]}/{value[1]}'


def parse_date(text):
    """`9/13` -> [9, 13]; raises ProjectError."""
    try:
        month, day = (int(part) for part in text.replace('-', '/').split('/'))
    except ValueError:
        raise ProjectError(f'Write a date as month/day, not {text!r}') from None
    if not 1 <= month <= 12 or not 1 <= day <= MONTH_DAYS[month - 1]:
        raise ProjectError(f'{text} is not a date')
    return [month, day]


def parse_weekdays(text):
    """`Mon, Wed, Fri` -> [1, 3, 5]."""
    found = []
    for part in text.replace(';', ',').split(','):
        key = part.strip()[:3].title()
        if key:
            if key not in SHORT_DAYS:
                raise ProjectError(f'{part.strip()} is not a weekday')
            found.append(SHORT_DAYS.index(key))
    return found


class CalendarDialog(QDialog):
    """The calendars of a project, edited on a copy: `value` holds them, and `nodes` any nodes the Free time preset added."""

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Calendars')
        self.resize(1180, 760)
        self.project = project
        self.value = deepcopy(project.calendars)
        self.nodes = []
        self.current = None
        self.loading = False
        layout = QVBoxLayout(self)
        intro = QLabel('A calendar runs your events over school days, as the BREW games do: a date card each new day, a time '
                       'badge for each event. A Start calendar node starts one; each event ends with Back to the calendar. '
                       'SHS only.')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        splitter = QSplitter()
        left = QWidget(); column = QVBoxLayout(left)
        self.list = QListWidget(); self.list.setObjectName('calendars')
        self.list.currentRowChanged.connect(self.select)
        column.addWidget(self.list)
        for label, callback in (('Add calendar', self.add_calendar), ('Remove calendar', self.remove_calendar)):
            button = QPushButton(label); button.clicked.connect(callback); column.addWidget(button)
        splitter.addWidget(left)
        right = QWidget(); body = QVBoxLayout(right)
        form = QFormLayout()
        self.name = QLineEdit(); self.ident = QLineEdit()
        self.first_month, self.first_day = QSpinBox(), QSpinBox()
        self.first_month.setRange(1, 12); self.first_day.setRange(1, 31)
        self.first_weekday = QComboBox(); self.first_weekday.addItems(WEEKDAYS)
        self.last_month, self.last_day = QSpinBox(), QSpinBox()
        self.last_month.setRange(1, 12); self.last_day.setRange(1, 31)
        self.school = [QCheckBox(day) for day in SHORT_DAYS]
        self.day_start, self.day_end = QTimeEdit(), QTimeEdit()
        self.day_end.setToolTip('00:00 is midnight, the end of the day')
        self.date_cards, self.week_cards = QCheckBox('A date card each new day'), QCheckBox('Week cards')
        self.card_title = QLineEdit(); self.card_title.setPlaceholderText('Under the date: optional')
        self.after = QComboBox()
        form.addRow('Name', self.name)
        form.addRow('ID', self.ident)
        first = QHBoxLayout()
        for widget in (QLabel('month'), self.first_month, QLabel('day'), self.first_day, QLabel('a'), self.first_weekday):
            first.addWidget(widget)
        form.addRow('First date', first)
        last = QHBoxLayout()
        for widget in (QLabel('month'), self.last_month, QLabel('day'), self.last_day):
            last.addWidget(widget)
        form.addRow('Last date', last)
        days = QHBoxLayout()
        for box in self.school:
            days.addWidget(box)
        form.addRow('School days', days)
        hours = QHBoxLayout()
        for widget in (self.day_start, QLabel('to'), self.day_end):
            hours.addWidget(widget)
        form.addRow('The day', hours)
        cards = QHBoxLayout(); cards.addWidget(self.date_cards); cards.addWidget(self.week_cards)
        form.addRow('Cards', cards)
        form.addRow('Card title', self.card_title)
        form.addRow('After the calendar', self.after)
        body.addLayout(form)
        self.table = QTableWidget(0, len(COLUMNS)); self.table.setObjectName('events')
        self.table.setHorizontalHeaderLabels(COLUMNS)
        body.addWidget(self.table, 1)
        buttons = QHBoxLayout()
        for label, callback in (('Add event', self.add_event), ('Remove event', self.remove_event),
                                ('Free time preset', self.free_time), ('Preview days', self.show_preview)):
            button = QPushButton(label); button.clicked.connect(callback); buttons.addWidget(button)
        body.addLayout(buttons)
        self.preview = QPlainTextEdit(); self.preview.setReadOnly(True); self.preview.setMaximumHeight(160)
        body.addWidget(self.preview)
        splitter.addWidget(right)
        splitter.setSizes([200, 980])
        layout.addWidget(splitter, 1)
        self.error = QLabel(); self.error.setStyleSheet('color: #d33'); self.error.setWordWrap(True)
        layout.addWidget(self.error)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.accept); box.rejected.connect(self.reject)
        layout.addWidget(box)
        self.refresh_list()

    # -- the list -----------------------------------------------------------------------------------------------------------------
    def refresh_list(self, row=0):
        self.loading = True
        self.list.clear()
        for calendar in self.value:
            self.list.addItem(f'{calendar["name"]} ({calendar["id"]})')
        self.loading = False
        self.current = None
        if self.value:
            self.list.setCurrentRow(min(row, len(self.value) - 1))
            self.select(self.list.currentRow())
        else:
            self.show_calendar(None)

    def add_calendar(self):
        if not self.save_current():
            return
        identifier = 'term' if not any(c['id'] == 'term' for c in self.value) else f'calendar{uuid.uuid4().hex[:4]}'
        self.value.append(blank_calendar(identifier))
        self.refresh_list(len(self.value) - 1)

    def remove_calendar(self):
        if self.current is not None:
            del self.value[self.current]
            self.current = None
            self.refresh_list()

    def select(self, row):
        if self.loading:
            return
        if self.current is not None and self.current != row and not self.save_current():
            self.loading = True
            self.list.setCurrentRow(self.current)
            self.loading = False
            return
        self.current = row if 0 <= row < len(self.value) else None
        self.show_calendar(self.value[self.current] if self.current is not None else None)

    # -- one calendar --------------------------------------------------------------------------------------------------------------
    def node_choices(self):
        return [(f'{n.label or n.id} ({n.id})', n.id) for n in list(self.project.nodes) + self.nodes if n.kind != 'native']

    def show_calendar(self, calendar):
        self.error.setText('')
        enabled = calendar is not None
        for widget in (self.name, self.ident, self.table, self.after):
            widget.setEnabled(enabled)
        if calendar is None:
            self.table.setRowCount(0)
            return
        self.name.setText(calendar['name']); self.ident.setText(calendar['id'])
        self.first_month.setValue(calendar['first'][0]); self.first_day.setValue(calendar['first'][1])
        self.first_weekday.setCurrentIndex(calendar['first'][2])
        self.last_month.setValue(calendar['last'][0]); self.last_day.setValue(calendar['last'][1])
        for k, box in enumerate(self.school):
            box.setChecked(k in calendar['weekdays'])
        self.day_start.setTime(minutes_time(calendar['day_start']))
        self.day_end.setTime(QTime(0, 0) if calendar['day_end'] >= 1440 else minutes_time(calendar['day_end']))
        self.date_cards.setChecked(calendar['date_cards']); self.week_cards.setChecked(calendar['week_cards'])
        self.card_title.setText(calendar['card_title'])
        self.after.clear()
        self.after.addItem('The episode ends', '')
        for label, value in self.node_choices():
            self.after.addItem(label, value)
        self.after.setCurrentIndex(max(0, self.after.findData(calendar['after'])))
        self.table.setRowCount(0)
        for event in calendar['events']:
            self.add_row(event)

    def add_row(self, event):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setCellWidget(row, 0, QLineEdit(event['name']))
        node = QComboBox()
        for label, value in self.node_choices():
            node.addItem(label, value)
        node.setCurrentIndex(max(0, node.findData(event['node'])))
        self.table.setCellWidget(row, 1, node)
        when = QComboBox()
        for value, label in zip(WHEN, ('Once', 'Weekly', 'Every school day')):
            when.addItem(label, value)
        when.setCurrentIndex(WHEN.index(event['when']))
        self.table.setCellWidget(row, 2, when)
        self.table.setCellWidget(row, 3, QLineEdit(date_text(event['date'])))
        self.table.setCellWidget(row, 4, QLineEdit(date_text(event['until'])))
        self.table.setCellWidget(row, 5, QLineEdit(', '.join(SHORT_DAYS[d] for d in event['weekdays'])))
        time = QTimeEdit(); time.setTime(minutes_time(event['minute']))
        self.table.setCellWidget(row, 6, time)
        timed = QCheckBox(); timed.setChecked(event['timed']); timed.setToolTip('Unticked: any time in its half hour')
        self.table.setCellWidget(row, 7, timed)
        length = QSpinBox(); length.setRange(0, 1440); length.setSuffix(' min'); length.setValue(event['duration'])
        self.table.setCellWidget(row, 8, length)
        first = QCheckBox(); first.setChecked(event['first']); first.setToolTip('Wins its half hour over other timed events')
        self.table.setCellWidget(row, 9, first)
        icon = QComboBox()
        icon.addItem('Clock (default)', -1)
        for number, name in SHS_BADGE_ICONS.items():
            icon.addItem(f'{name} ({number})', number)
        for asset in self.project.assets:
            icon.addItem(f'{asset.id} · {asset.name}', asset.id)
        if icon.findData(event['icon']) < 0:
            icon.addItem(str(event['icon']), event['icon'])
        icon.setCurrentIndex(icon.findData(event['icon']))
        self.table.setCellWidget(row, 10, icon)
        condition = QLineEdit(event['condition']); condition.setPlaceholderText('Optional: met == 1')
        self.table.setCellWidget(row, 11, condition)
        badge = QCheckBox(); badge.setChecked(event['badge'])
        self.table.setCellWidget(row, 12, badge)

    def read_rows(self):
        events = []
        for row in range(self.table.rowCount()):
            cell = lambda column: self.table.cellWidget(row, column)
            events.append(dict(name=cell(0).text().strip(), node=cell(1).currentData() or '', when=cell(2).currentData(),
                               date=parse_date(cell(3).text()), until=parse_date(cell(4).text()),
                               weekdays=parse_weekdays(cell(5).text()), minute=time_minutes(cell(6).time()),
                               timed=cell(7).isChecked(), duration=cell(8).value(), first=cell(9).isChecked(),
                               icon=cell(10).currentData(), condition=cell(11).text().strip(), badge=cell(12).isChecked()))
        return events

    def read_calendar(self):
        """The calendar as the form has it; raises ProjectError for a form that doesn't make one."""
        end = time_minutes(self.day_end.time())
        return dict(id=self.ident.text().strip(), name=self.name.text().strip(),
                    first=[self.first_month.value(), self.first_day.value(), self.first_weekday.currentIndex()],
                    last=[self.last_month.value(), self.last_day.value()],
                    weekdays=[k for k, box in enumerate(self.school) if box.isChecked()],
                    day_start=time_minutes(self.day_start.time()), day_end=1440 if end == 0 else end,
                    date_cards=self.date_cards.isChecked(), week_cards=self.week_cards.isChecked(),
                    card_title=self.card_title.text().strip(), after=self.after.currentData() or '', events=self.read_rows())

    def save_current(self):
        """The form back into its calendar, checked; False (and the reason shown) when it doesn't make one."""
        if self.current is None:
            return True
        try:
            calendar = self.read_calendar()
            candidate = list(self.value)
            candidate[self.current] = calendar
            validate_calendars(candidate)
        except ProjectError as error:
            self.error.setText(str(error))
            return False
        self.value = candidate
        self.error.setText('')
        return True

    def add_event(self):
        nodes = self.node_choices()
        self.add_row(blank_event(nodes[0][1] if nodes else ''))

    def remove_event(self):
        row = self.table.currentRow()
        if row < 0:
            row = self.table.rowCount() - 1
        if row >= 0:
            self.table.removeRow(row)

    def free_time(self):
        """Free time, as BREW's and Guy's: an event on every school day at 3:00 PM, any time in its half hour, whose node is a
        choice of two activities, each ending with Back to the calendar. Rename and add activities in the story."""
        if self.current is None:
            self.error.setText('Add a calendar first.')
            return
        stem = uuid.uuid4().hex[:6]
        ask, one, two, back = (f'free_{stem}', f'free_{stem}_a', f'free_{stem}_b', f'free_{stem}_back')
        self.nodes += [
            Node(ask, 'choice', 'Free time', text='What do I want to do?', speaker='',
                 options=[Choice('Hang out', one), Choice('Homework', two)]),
            Node(one, text='You hang out with friends.', next=back, label='Hang out'),
            Node(two, text='You get some homework done.', next=back, label='Homework'),
            Node(back, 'calendar_back', 'Back to the calendar'),
        ]
        event = blank_event(ask)
        calendar = self.value[self.current]
        event.update(name='Free time', when='school_days', date=calendar['first'][:2], until=calendar['last'],
                     minute=900, timed=False, duration=0, icon=3110)
        self.add_row(event)

    def show_preview(self):
        if not self.save_current():
            return
        calendar = self.value[self.current]
        lines = []
        for day in preview(calendar):
            events = ', '.join(f'{e["minute"] // 60}:{e["minute"] % 60:02} {e["name"]}' for e in day['events']) or '(nothing)'
            lines.append(f'Day {day["day"]}, {day["date"]}: {events}')
        self.preview.setPlainText('\n'.join(lines))

    def accept(self):
        if self.save_current():
            super().accept()
