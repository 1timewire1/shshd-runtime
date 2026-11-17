"""shshd-runtime: the Creator's calendars (CREATOR_CALENDAR_DESIGN.md; owner, 2026-11-17).

A calendar runs a story's events over school days, the BREW games' way (tools/translate/brew.py's Classic driver,
`calendar_step` and `run_event`, which matched Tardy-Slip on all 144 runs of the multi-date Classic stories): a clock in half-hour
slots from the day's start to its end, timed events one at a time (a "First" one before the others, then in the order they were
scheduled), untimed ones after them in order, a date card each new day, a time badge for each event, and the next school day when
the day ends. An event whose condition is false when its turn comes is skipped (decision 1).

The compiler writes it as KiWi: one script of its own, the driver, and code in the scenes for the nodes that start a calendar,
schedule or cancel an event, move the clock or run the due events. Everything it keeps is in the numbers multi-scene stories already
use (owner -30000, negative keys), so saves, Skip Ahead, Undo and sync need nothing new, and it uses only native services, apart
from Run due events (223).
"""
from .model import ProjectError

OWNER = -30000                  # compiler.VARIABLE_OWNER: the Creator's own numbers
MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)    # BREW's: no leap years
CUMULATIVE = tuple(sum(MONTH_DAYS[:m]) for m in range(13))
WEEKDAYS = ('Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday')
MONTHS = ('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November',
          'December')
SLOT = 30                       # BREW's half hours
MOST_DAYS, MOST_EVENTS, MOST_OCCURRENCES, MOST_A_DAY, MOST_TEMPLATES = 120, 64, 512, 32, 600
UNTIMED = -1                    # an occurrence's duration when it runs any time in its half hour

# The state (owner -30000).
CAL, START, DAY, CLOCK, TIMED, SHOWN_DAY, SHOWN_WEEK, COUNT, WAITING_LEFT, CHECK, NEST = range(-2, -13, -1)
WEEKDAY0, START_DOY, LAST_DAY, DAY_START, DAY_END, MASK = range(-13, -19, -1)
FIRST_OF = -100                 # - template: the First setting it was last scheduled with
OCCURRENCE, FIELDS = -1000, 5   # occurrence n (from 1): OCCURRENCE - FIELDS * n - field
TEMPLATE_F, DAY_F, MINUTE_F, STATE_F, FIRST_F = range(5)
DAY_COUNT = -4000               # - day: how many occurrences that day holds
DAY_LIST = -5000                # - MOST_A_DAY * day - i: the day's i-th occurrence
WAITING, PENDING, DONE, CANCELLED = 1, 2, 3, 4
NO_DATE = -1
# SHS's own scene-badge icons (its episodes use 3100-3127 with service 90), by what they show, for the Calendar panel. An event with
# no icon of its own (-1) wears the clock.
SHS_BADGE_ICONS = {3100: 'Art', 3101: 'Science', 3102: 'Books', 3103: 'Burger', 3104: 'Calendar', 3105: 'Car', 3106: 'Clock',
                   3107: 'Gem', 3108: 'Open book', 3109: 'Sunglasses', 3110: 'Smiley', 3111: 'Restaurant', 3112: 'Football',
                   3113: 'French flag', 3114: 'Heart', 3115: 'Ruins', 3116: 'Rose', 3117: 'Creature', 3118: 'Lunch bag',
                   3119: 'Maths', 3120: 'Money', 3121: 'Sun', 3122: 'Tickets', 3123: 'Music', 3124: 'Moon', 3125: 'Party cups',
                   3126: 'Question', 3127: 'Skull'}
CLOCK_ICON = 3106


# -- the calendar's dates ----------------------------------------------------------------------------------------------------------
def day_of_year(month, day):
    return CUMULATIVE[month - 1] + day - 1


def day_index(calendar, month, day):
    """The calendar's day number of a date (0 its first day), a month before the first one counted in the next year, as BREW."""
    return (day_of_year(month, day) - day_of_year(*calendar['first'][:2])) % 365


def weekday_of(calendar, index):
    return (calendar['first'][2] + index) % 7


def date_of(calendar, index):
    """(month, day) of a day number."""
    doy = (day_of_year(*calendar['first'][:2]) + index) % 365
    month = max(m for m in range(1, 13) if CUMULATIVE[m - 1] <= doy)
    return month, doy - CUMULATIVE[month - 1] + 1


def date_text(calendar, index):
    month, day = date_of(calendar, index)
    return f'{WEEKDAYS[weekday_of(calendar, index)]}, {MONTHS[month - 1]} {day}'


def last_index(calendar):
    return day_index(calendar, *calendar['last'])


def school_day(calendar, index):
    return weekday_of(calendar, index) in calendar['weekdays']


# -- checking ------------------------------------------------------------------------------------------------------------------------
def _int(value, low, high, what):
    if type(value) is not int or not low <= value <= high:
        raise ProjectError(f'{what} must be a whole number from {low} to {high}')


def _date(value, what):
    if not isinstance(value, list) or len(value) != 2:
        raise ProjectError(f'{what} is [month, day]')
    _int(value[0], 1, 12, f'{what}\'s month')
    _int(value[1], 1, MONTH_DAYS[value[0] - 1], f'{what}\'s day')


def _text(value, what, limit):
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 for c in value):
        raise ProjectError(f'{what} is one line of at most {limit} characters')


CALENDAR_KEYS = {'id', 'name', 'first', 'last', 'weekdays', 'day_start', 'day_end', 'date_cards', 'week_cards', 'card_title',
                 'after', 'events'}
EVENT_KEYS = {'name', 'node', 'when', 'date', 'until', 'weekdays', 'minute', 'timed', 'duration', 'first', 'icon', 'condition',
              'badge'}
WHEN = ('once', 'weekly', 'school_days')


def blank_calendar(identifier='calendar'):
    """A new calendar: September 13 (a Monday) to December 10, Monday, Wednesday and Friday, 7:30 AM to midnight (Fall '06's)."""
    return dict(id=identifier, name='Term', first=[9, 13, 1], last=[12, 10], weekdays=[1, 3, 5], day_start=450, day_end=1440,
                date_cards=True, week_cards=False, card_title='', after='', events=[])


def blank_event(node=''):
    return dict(name='Event', node=node, when='once', date=[9, 13], until=[9, 13], weekdays=[1, 3, 5], minute=540, timed=True,
                duration=60, first=False, icon=-1, condition='', badge=True)


def validate_calendars(calendars):
    """The calendars' structure (model.validate_structure); the compiler checks their nodes and conditions."""
    if not isinstance(calendars, list) or len(calendars) > 16:
        raise ProjectError('A project has at most 16 calendars')
    seen = set()
    for calendar in calendars:
        if not isinstance(calendar, dict) or set(calendar) != CALENDAR_KEYS:
            raise ProjectError('A calendar has exactly ' + ', '.join(sorted(CALENDAR_KEYS)))
        identifier = calendar['id']
        if not isinstance(identifier, str) or not identifier or len(identifier) > 40 or identifier in seen:
            raise ProjectError('Each calendar needs its own ID')
        seen.add(identifier)
        what = f'Calendar {identifier}'
        _text(calendar['name'], f'{what}\'s name', 60)
        _text(calendar['card_title'], f'{what}\'s card title', 60)
        first = calendar['first']
        if not isinstance(first, list) or len(first) != 3:
            raise ProjectError(f'{what}\'s first date is [month, day, weekday]')
        _date(first[:2], f'{what}\'s first date')
        _int(first[2], 0, 6, f'{what}\'s first weekday (0 Sunday)')
        _date(calendar['last'], f'{what}\'s last date')
        if last_index(calendar) >= MOST_DAYS:
            raise ProjectError(f'{what} runs at most {MOST_DAYS} days')
        weekdays = calendar['weekdays']
        if (not isinstance(weekdays, list) or not weekdays or len(set(weekdays)) != len(weekdays)
                or any(type(w) is not int or not 0 <= w <= 6 for w in weekdays)):
            raise ProjectError(f'{what} needs its school days (0 Sunday to 6 Saturday)')
        _int(calendar['day_start'], 0, 1439, f'{what}\'s day start')
        _int(calendar['day_end'], calendar['day_start'], 1440, f'{what}\'s day end')
        for flag in ('date_cards', 'week_cards'):
            if type(calendar[flag]) is not bool:
                raise ProjectError(f'{what}: {flag} is true or false')
        _text(calendar['after'], f'{what}\'s After node', 200)
        events = calendar['events']
        if not isinstance(events, list) or len(events) > MOST_EVENTS:
            raise ProjectError(f'{what} has at most {MOST_EVENTS} events')
        for n, event in enumerate(events, 1):
            label = f'{what} event {n}'
            if not isinstance(event, dict) or set(event) != EVENT_KEYS:
                raise ProjectError(f'{label} has exactly ' + ', '.join(sorted(EVENT_KEYS)))
            _text(event['name'], f'{label}\'s name', 40)
            _text(event['node'], f'{label}\'s node', 200)
            if event['when'] not in WHEN:
                raise ProjectError(f'{label}: when is once, weekly or school_days')
            _date(event['date'], f'{label}\'s date')
            _date(event['until'], f'{label}\'s last date')
            if (not isinstance(event['weekdays'], list)
                    or any(type(w) is not int or not 0 <= w <= 6 for w in event['weekdays'])):
                raise ProjectError(f'{label}\'s weekdays are 0 (Sunday) to 6')
            _int(event['minute'], 0, 1439, f'{label}\'s time (minutes after midnight)')
            _int(event['duration'], 0, 1440, f'{label}\'s length in minutes')
            _int(event['icon'], -1, 32767, f'{label}\'s icon')
            for flag in ('timed', 'first', 'badge'):
                if type(event[flag]) is not bool:
                    raise ProjectError(f'{label}: {flag} is true or false')
            if not isinstance(event['condition'], str) or len(event['condition']) > 2000:
                raise ProjectError(f'{label}\'s condition is an expression')


# -- the templates: what an occurrence can be ---------------------------------------------------------------------------------------
class Template:
    """An event the calendar can run: a calendar's event, or a Schedule event node's own scene."""

    def __init__(self, number, calendar, name, node, minute, duration, first, icon, condition, badge, key=''):
        self.number, self.calendar, self.name, self.node, self.key = number, calendar, name, node, key
        self.minute, self.duration, self.first, self.icon, self.condition, self.badge = (minute, duration, first, icon,
                                                                                         condition, badge)


def templates(project, parameters):
    """(the templates, {calendar ID: index from 1}, {(calendar ID, event name): [templates]}, {schedule node ID: template})."""
    found, indexes, by_name, own = [], {}, {}, {}
    for index, calendar in enumerate(project.calendars, 1):
        indexes[calendar['id']] = index
        for k, event in enumerate(calendar['events']):
            template = Template(len(found) + 1, index, event['name'], event['node'], event['minute'],
                                event['duration'] if event['timed'] else UNTIMED, event['first'], event['icon'],
                                event['condition'], event['badge'], key=f'calendar.{calendar["id"]}.event.{k}.name')
            found.append(template)
            by_name.setdefault((calendar['id'], event['name']), []).append(template)
    for node in project.nodes:
        if node.kind == 'schedule_event':
            p = parameters(node)
            if p['event'] or p['calendar'] not in indexes:
                continue
            template = Template(len(found) + 1, indexes[p['calendar']], p['name'], p['target'], 0,
                                p['duration'] if p['duration'] >= 0 else UNTIMED, p['first'], p['icon'], '', bool(p['name']),
                                key=f'node.{node.id}.param.name')
            found.append(template)
            own[node.id] = template
            by_name.setdefault((p['calendar'], p['name']), []).append(template)
    if len(found) > MOST_TEMPLATES:
        raise ProjectError(f'At most {MOST_TEMPLATES} events and Schedule event nodes')
    return found, indexes, by_name, own


def occurrences(calendar, events):
    """[(event, day)] a calendar's table puts on it when it starts, checked against its limits."""
    last = last_index(calendar)
    out, per_day = [], {}
    for event in events:
        start = day_index(calendar, *event['date'])
        if start > last:
            raise ProjectError(f'Calendar {calendar["id"]}: {event["name"]} is after its last date')
        if event['when'] == 'once':
            days = [start]
        else:
            end = min(day_index(calendar, *event['until']), last)
            wanted = event['weekdays'] if event['when'] == 'weekly' else calendar['weekdays']
            days = [d for d in range(start, end + 1) if weekday_of(calendar, d) in wanted]
        for day in days:
            out.append((event, day))
            per_day[day] = per_day.get(day, 0) + 1
            if per_day[day] > MOST_A_DAY:
                raise ProjectError(f'Calendar {calendar["id"]}: more than {MOST_A_DAY} events on {date_text(calendar, day)}')
    if len(out) > MOST_OCCURRENCES:
        raise ProjectError(f'Calendar {calendar["id"]}: more than {MOST_OCCURRENCES} events in all')
    return out


def preview(calendar):
    """What a calendar's table puts on each day, for the panel and MCP: [{day, date, weekday, school, events: [...]}]."""
    by_day = {}
    for event, day in occurrences(calendar, calendar['events']):
        by_day.setdefault(day, []).append(dict(name=event['name'], minute=event['minute'], node=event['node']))
    return [dict(day=d, date=date_text(calendar, d), school=school_day(calendar, d),
                 events=sorted(by_day.get(d, []), key=lambda e: e['minute']))
            for d in range(last_index(calendar) + 1) if d in by_day or school_day(calendar, d)]


# -- KiWi ------------------------------------------------------------------------------------------------------------------------------
class Emitter:
    """Structured code over a compiler._Assembler: the Creator's numbers, data-word scratch and labels."""

    def __init__(self, asm, prefix):
        self.asm, self.prefix, self.serial = asm, prefix, 0
        scratch = getattr(asm, 'calendar_scratch', None)
        if scratch is None:
            scratch = asm.calendar_scratch = {}
        self.scratch = scratch

    def label(self):
        self.serial += 1
        return (self.prefix, self.serial)

    def mark(self, label):
        self.asm.labels[label] = len(self.asm.code)

    def push(self, value):
        self.asm.emit(0x1a, value)

    def op(self, code):
        self.asm.emit(code)

    def jump(self, label):
        self.asm.jump(label)

    def jump_if(self, label):               # pops; jumps when nonzero
        self.asm.jump_if(label)

    def jump_unless(self, label):           # pops; jumps when zero
        self.asm.emit(0x13)
        self.asm.jump_if(label)

    def num(self, key):
        """Push number `key` (an int or a callable pushing the key)."""
        self.push(OWNER)
        key() if callable(key) else self.push(key)
        self.asm.emit(0x1f, 53 << 8 | 2)
        self.asm.emit(0x21)

    def set(self, key, value):
        """Number `key` = `value` (ints or callables that push)."""
        self.push(OWNER)
        key() if callable(key) else self.push(key)
        value() if callable(value) else self.push(value)
        self.asm.emit(0x1f, 52 << 8 | 3)

    def word(self, name):
        """A scratch data word of this script, by name."""
        if name not in self.scratch:
            self.scratch[name] = self.asm.table([0])
        return self.scratch[name]

    def buffer(self, name, words):
        key = ('buffer', name)
        if key not in self.scratch:
            self.scratch[key] = self.asm.table([0] * words)
        return self.scratch[key]

    def table(self, name, values):
        key = ('table', name)
        if key not in self.scratch:
            self.scratch[key] = self.asm.table(list(values))
        return self.scratch[key]

    def load(self, name):
        self.asm.emit(0x40, self.word(name))

    def store(self, name, value):
        value() if callable(value) else self.push(value)
        self.asm.emit(0x03); self.push(self.word(name)); self.asm.emit(0x07); self.asm.emit(0x3e); self.asm.emit(0x15)

    def read_table(self, name, values, index):
        """Push values[index] (index a callable pushing it)."""
        self.push(self.table(name, values)); index(); self.op(0x50); self.op(0x3f)

    def text(self, value):
        return self.asm.text(value)

    # -- the calendar's keys --------------------------------------------------------------------------------------------------------
    def occ_key(self, n, field):
        return lambda: (self.push(OCCURRENCE - field), n(), self.push(FIELDS), self.op(0x52), self.op(0x51))

    def occ(self, n, field):
        self.num(self.occ_key(n, field))

    def set_occ(self, n, field, value):
        self.set(self.occ_key(n, field), value)

    def day_count_key(self, day):
        return lambda: (self.push(DAY_COUNT), day(), self.op(0x51))

    def day_list_key(self, day, i):
        return lambda: (self.push(DAY_LIST), day(), self.push(MOST_A_DAY), self.op(0x52), self.op(0x51), i(), self.op(0x51))

    def larger(self, a, b):
        first, end = self.label(), self.label()
        a(); b(); self.op(0x0d); self.jump_if(first)
        b(); self.jump(end)
        self.mark(first)
        a()
        self.mark(end)

    def for_today(self, name, body):
        """for i in today's list: body(occurrence) (a callable pushing it). `name` keeps its scratch apart."""
        i, top, done = f'{name}_i', self.label(), self.label()
        self.store(i, 0)
        self.mark(top)
        self.load(i); self.num(self.day_count_key(lambda: self.num(DAY))); self.op(0x0e); self.jump_unless(done)
        body(lambda: self.num(self.day_list_key(lambda: self.num(DAY), lambda: self.load(i))))
        self.store(i, lambda: (self.load(i), self.push(1), self.op(0x50)))
        self.jump(top)
        self.mark(done)

    def weekday(self, day):
        """Push day `day`'s weekday (0 Sunday)."""
        self.num(WEEKDAY0); day(); self.op(0x50); self.push(7); self.op(0x54)

    def is_school_day(self, day):
        """Push whether the weekday mask has day `day`'s weekday."""
        self.num(MASK)
        self.read_table('pow2', [1 << k for k in range(7)], lambda: self.weekday(day))
        self.op(0x53); self.push(2); self.op(0x54)

    # -- adding an occurrence (the calendar's start, Schedule event) -----------------------------------------------------------------
    def add(self, template, day, minute, first):
        """A waiting occurrence of `template` on day `day` at `minute`, First or not (ints or callables that push), unless the day is
        outside the calendar or full, or the calendar's list is."""
        push = lambda value: value() if callable(value) else self.push(value)
        skip = self.label()
        self.store('add_day', day)
        self.load('add_day'); self.push(0); self.op(0x0e); self.jump_if(skip)
        self.load('add_day'); self.num(LAST_DAY); self.op(0x0c); self.jump_if(skip)
        self.num(COUNT); self.push(MOST_OCCURRENCES); self.op(0x0d); self.jump_if(skip)
        count = self.day_count_key(lambda: self.load('add_day'))
        self.num(count); self.push(MOST_A_DAY); self.op(0x0d); self.jump_if(skip)
        self.set(COUNT, lambda: (self.num(COUNT), self.push(1), self.op(0x50)))
        n = lambda: self.num(COUNT)
        self.set_occ(n, TEMPLATE_F, template)
        self.set_occ(n, DAY_F, lambda: self.load('add_day'))
        self.set_occ(n, MINUTE_F, minute)
        self.set_occ(n, STATE_F, WAITING)
        self.set_occ(n, FIRST_F, first)
        self.set(lambda: (self.push(FIRST_OF), push(template), self.op(0x51)), first)
        self.set(self.day_list_key(lambda: self.load('add_day'), lambda: self.num(count)), n)
        self.set(count, lambda: (self.num(count), self.push(1), self.op(0x50)))
        self.set(WAITING_LEFT, lambda: (self.num(WAITING_LEFT), self.push(1), self.op(0x50)))
        self.mark(skip)


def emit_function(e, name, args, walk, all_templates, by_name):
    """A calendar expression function (expressions.CALENDAR_FUNCTIONS), as code pushing its value."""
    if name == 'day':
        e.num(DAY)
    elif name == 'minute':
        e.num(CLOCK)
    elif name == 'weekday':
        e.weekday(lambda: e.num(DAY))
    elif name == 'date':
        month, day = args
        # (day of year - the first's + 365) % 365
        e.read_table('cumulative', CUMULATIVE[:12], lambda: (walk(month), e.push(1), e.op(0x51)))
        walk(day); e.op(0x50); e.push(1); e.op(0x51); e.num(START_DOY); e.op(0x51); e.push(365); e.op(0x50); e.push(365); e.op(0x54)
    elif name == 'days_between':
        emit_function(e, 'date', args[2:], walk, all_templates, by_name)
        emit_function(e, 'date', args[:2], walk, all_templates, by_name)
        e.op(0x51)
    elif name == 'next_weekday':
        # The next day after today on that weekday: today + (w - weekday() + 13) % 7 + 1.
        e.num(DAY); walk(args[0]); e.weekday(lambda: e.num(DAY)); e.op(0x51); e.push(13); e.op(0x50); e.push(7); e.op(0x54)
        e.op(0x50); e.push(1); e.op(0x50)
    elif name == 'event_first':
        found = [t for t in all_templates if t.name == args[0]]
        if not found:
            raise ProjectError(f'event_first: no event is named {args[0]!r}')
        for k, template in enumerate(found):
            e.num(FIRST_OF - template.number)
            if k:
                e.op(0x11)
    elif name == 'events_between':
        # How many of today's events overlap [from, to]: one starts before `to` ends and ends after `from` starts.
        low, high = args
        walk(low); e.store('window_from', lambda: None)
        walk(high); e.store('window_to', lambda: None)
        e.store('window_count', 0)
        durations = [0] + [max(t.duration, 0) for t in all_templates]

        def body(o):
            skip = e.label()
            e.occ(o, STATE_F); e.push(CANCELLED); e.op(0x0a); e.jump_if(skip)
            e.occ(o, MINUTE_F); e.load('window_to'); e.op(0x0c); e.jump_if(skip)
            e.occ(o, MINUTE_F); e.read_table('durations', durations, lambda: e.occ(o, TEMPLATE_F)); e.op(0x50)
            e.load('window_from'); e.op(0x0e); e.jump_if(skip)
            e.store('window_count', lambda: (e.load('window_count'), e.push(1), e.op(0x50)))
            e.mark(skip)
        e.for_today('window', body)
        e.load('window_count')
    else:
        raise ProjectError(f'Unknown calendar function {name}')


def emitter(asm):
    """The one Emitter of a script, so its labels and scratch never meet another's."""
    found = getattr(asm, 'calendar_emitter', None)
    if found is None:
        found = asm.calendar_emitter = Emitter(asm, 'calendar')
    return found
