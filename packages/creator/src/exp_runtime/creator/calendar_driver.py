"""shshd-runtime: the calendar's driver script and its nodes' code (calendar.py has the model and the emitter;
CREATOR_CALENDAR_DESIGN.md "How it plays")."""
from .calendar import (BADGE_UP, CAL, CANCELLED, CLOCK_ICON, CHECK, CLOCK, COUNT, CUMULATIVE, DAY, DAY_END, DAY_START, DONE, FIRST_F, LAST_DAY,
                       MASK, MINUTE_F, MONTHS, NEST, PENDING, SHOWN_DAY, SHOWN_WEEK, SLOT, START, START_DOY, STATE_F,
                       TEMPLATE_F, TIMED, WAITING, WAITING_LEFT, WEEKDAY0, WEEKDAYS, day_of_year, emitter, last_index,
                       occurrences, templates)
from .model import ProjectError

KINDS = ('start_calendar', 'calendar_back', 'schedule_event', 'cancel_event', 'set_clock', 'skip_ahead', 'run_due', 'call_scene',
         'return_scene')
ENDS = ('start_calendar', 'calendar_back', 'return_scene')      # nodes after which the scene goes nowhere
RUNTIME_ONLY = ('run_due', 'call_scene')                         # service 223: other apps stop at it


class Context:
    """What the compiler hands the calendar code: the project, its templates, where each node is, and (per script) how to
    evaluate an expression."""

    def __init__(self, project, parameters, ordinals, script_of, driver_script, translated):
        self.project, self.parameters, self.ordinals, self.script_of = project, parameters, ordinals, script_of
        self.driver_script, self.translated = driver_script, translated
        self.templates, self.indexes, self.by_name, self.own = templates(project, parameters)
        self.expression = None          # expression(asm, text): code pushing its value, set by the compiler per script

    def durations(self):
        return [0] + [t.duration for t in self.templates]

    def condition(self, e, template, skip):
        """Jump to `skip` when the condition of the occurrence's template (`template` pushes its number) is false."""
        for t in self.templates:
            if t.condition.strip():
                other = e.label()
                template(); e.push(t.number); e.op(0x0a); e.jump_unless(other)
                self.expression(e.asm, t.condition); e.jump_unless(skip)
                e.mark(other)

    def enter(self, e, template):
        """Set the template's node as its scene's entry, and push the scene's script (for a queue or a nested run)."""
        ordinals = [0] + [self.ordinals.get(t.node, 0) for t in self.templates]
        scripts = [0] + [self.script_of(t.node) for t in self.templates]
        e.set(-1, lambda: e.read_table('ordinals', ordinals, template))
        e.read_table('scripts', scripts, template)


def driver(asm, ctx):
    """The calendar's own script: a Start calendar request, then each step."""
    e = emitter(asm)
    project = ctx.project
    step, loop, run, over, halt = (e.label() for _ in range(5))
    durations = ctx.durations()
    duration = lambda o: e.read_table('durations', durations, lambda: e.occ(o, TEMPLATE_F))
    B = lambda: e.load('B')

    # -- a calendar to start --
    e.num(START); e.jump_unless(step)
    for index, calendar in enumerate(project.calendars, 1):
        other = e.label()
        e.num(START); e.push(index); e.op(0x0a); e.jump_unless(other)
        start_calendar(e, ctx, index, calendar)
        e.jump(step)
        e.mark(other)
    e.set(START, 0)
    e.jump(halt)

    e.mark(step)
    e.num(CAL); e.jump_unless(halt)
    # -- the timed event that ran: untimed ones inside its span are due; the clock moves past its end --
    timed_done = e.label()
    e.num(TIMED); e.jump_unless(timed_done)
    e.store('T', lambda: e.num(TIMED))
    T = lambda: e.load('T')
    e.store('span_end', lambda: (e.occ(T, MINUTE_F), e.larger(lambda: duration(T), lambda: e.push(0)), e.op(0x50),
                                 e.push(1), e.op(0x51)))

    def inside(o):
        skip = e.label()
        e.occ(o, STATE_F); e.push(WAITING); e.op(0x0b); e.jump_if(skip)
        duration(o); e.push(0); e.op(0x0d); e.jump_if(skip)
        e.occ(o, MINUTE_F); e.occ(T, MINUTE_F); e.op(0x0e); e.jump_if(skip)
        e.occ(o, MINUTE_F); e.load('span_end'); e.op(0x0c); e.jump_if(skip)
        e.set_occ(o, STATE_F, PENDING)
        e.mark(skip)
    e.for_today('inside', inside)
    e.set(CLOCK, lambda: e.larger(lambda: e.num(CLOCK), lambda: e.larger(
        lambda: (e.load('span_end'), e.push(1), e.op(0x50)), lambda: (e.occ(T, MINUTE_F), e.push(1), e.op(0x50)))))
    e.set(TIMED, 0)
    e.mark(timed_done)

    e.mark(loop)
    e.num(DAY); e.push(0); e.op(0x0e); e.jump_if(over)

    # -- an event already due runs first, in the order of the day's list --
    def pending(o):
        skip = e.label()
        e.occ(o, STATE_F); e.push(PENDING); e.op(0x0b); e.jump_if(skip)
        e.store('B', o); e.jump(run)
        e.mark(skip)
    e.for_today('pending', pending)
    # -- past the day's end: the next school day, or the end --
    today = e.label()
    e.num(CLOCK); e.num(DAY_END); e.op(0x0f); e.jump_if(today)
    next_school_day(e, lambda: (e.num(DAY), e.push(1), e.op(0x50)))
    e.jump(loop)
    e.mark(today)
    # -- the earliest waiting event today from now; none: the day is over (or the calendar, with nothing left at all) --
    e.store('earliest', 32767)

    def earliest(o):
        skip = e.label()
        e.occ(o, STATE_F); e.push(WAITING); e.op(0x0b); e.jump_if(skip)
        e.occ(o, MINUTE_F); e.num(CLOCK); e.op(0x0e); e.jump_if(skip)
        e.occ(o, MINUTE_F); e.load('earliest'); e.op(0x0d); e.jump_if(skip)
        e.store('earliest', lambda: e.occ(o, MINUTE_F))
        e.mark(skip)
    e.for_today('earliest', earliest)
    some = e.label()
    e.load('earliest'); e.push(32767); e.op(0x0b); e.jump_if(some)
    e.num(WAITING_LEFT); e.push(0); e.op(0x0f); e.jump_if(over)
    e.set(CLOCK, lambda: (e.num(DAY_END), e.push(1), e.op(0x50)))
    e.jump(loop)
    e.mark(some)
    # -- its half hour: the timed events in it, a First one first; with none, the untimed ones are due --
    e.set(CLOCK, lambda: e.larger(lambda: e.num(CLOCK),
                                  lambda: (e.load('earliest'), e.push(SLOT), e.op(0x53), e.push(SLOT), e.op(0x52))))
    e.store('slot_end', lambda: (e.num(CLOCK), e.push(SLOT), e.op(0x53), e.push(SLOT), e.op(0x52), e.push(SLOT - 1),
                                 e.op(0x50)))

    def in_slot(o, skip):
        e.occ(o, STATE_F); e.push(WAITING); e.op(0x0b); e.jump_if(skip)
        e.occ(o, MINUTE_F); e.num(CLOCK); e.op(0x0e); e.jump_if(skip)
        e.occ(o, MINUTE_F); e.load('slot_end'); e.op(0x0c); e.jump_if(skip)

    e.store('B', 0)

    def timed(o):
        skip, take = e.label(), e.label()
        in_slot(o, skip)
        duration(o); e.push(0); e.op(0x0e); e.jump_if(skip)
        B(); e.jump_unless(take)
        e.occ(o, FIRST_F); e.jump_unless(skip)
        e.occ(B, FIRST_F); e.jump_if(skip)
        e.mark(take)
        e.store('B', o)
        e.mark(skip)
    e.for_today('timed', timed)
    untimed = e.label()
    B(); e.jump_unless(untimed)
    e.set(CLOCK, lambda: e.larger(lambda: e.num(CLOCK), lambda: e.occ(B, MINUTE_F)))
    e.set(TIMED, B)
    e.jump(run)
    e.mark(untimed)

    def due(o):
        skip = e.label()
        in_slot(o, skip)
        e.set_occ(o, STATE_F, PENDING)
        e.mark(skip)
    e.for_today('due', due)
    e.set(CLOCK, lambda: (e.load('slot_end'), e.push(1), e.op(0x50)))
    e.jump(loop)

    # -- run B: its condition (false: skipped), a new day's cards, its badge, then its node --
    e.mark(run)
    e.set_occ(B, STATE_F, DONE)
    e.set(WAITING_LEFT, lambda: (e.num(WAITING_LEFT), e.push(1), e.op(0x51)))
    skipped, shown = e.label(), e.label()
    ctx.condition(e, lambda: e.occ(B, TEMPLATE_F), skipped)
    e.num(DAY); e.num(SHOWN_DAY); e.op(0x0a); e.jump_if(shown)
    e.set(SHOWN_DAY, lambda: e.num(DAY))
    asm.call(90, -1, -1)                                        # (yesterday's badge off before the new day's cards)
    e.set(BADGE_UP, 0)
    cards(e, ctx)
    e.mark(shown)
    badge(e, ctx, B)
    ctx.enter(e, lambda: e.occ(B, TEMPLATE_F))
    e.push(0); asm.emit(0x1f, 10 << 8 | 2)
    e.jump(halt)
    e.mark(skipped)
    not_timed = e.label()
    e.num(TIMED); B(); e.op(0x0a); e.jump_unless(not_timed)
    e.set(TIMED, 0)
    e.mark(not_timed)
    e.jump(loop)

    # -- the end: the calendar's After node, or the episode's end --
    e.mark(over)
    e.store('ended', lambda: e.num(CAL))
    e.set(CAL, 0)
    asm.call(90, -1, -1)                                        # the last event's badge goes with the calendar
    e.set(BADGE_UP, 0)
    for index, calendar in enumerate(project.calendars, 1):
        if not calendar['after']:
            continue
        other = e.label()
        e.load('ended'); e.push(index); e.op(0x0a); e.jump_unless(other)
        e.set(-1, ctx.ordinals[calendar['after']])
        asm.call(10, ctx.script_of(calendar['after']), 0)
        e.jump(halt)
        e.mark(other)
    asm.call(7)
    e.mark(halt)
    asm.emit(0x33)


def next_school_day(e, first):
    """DAY = the first school day from `first` on, the clock at the day's start; -1 past the calendar's last day."""
    top, found, none = e.label(), e.label(), e.label()
    e.store('next_day', first)
    e.mark(top)
    e.load('next_day'); e.num(LAST_DAY); e.op(0x0c); e.jump_if(none)
    e.is_school_day(lambda: e.load('next_day')); e.jump_if(found)
    e.store('next_day', lambda: (e.load('next_day'), e.push(1), e.op(0x50)))
    e.jump(top)
    e.mark(none)
    e.store('next_day', -1)
    e.mark(found)
    e.set(DAY, lambda: e.load('next_day'))
    e.set(CLOCK, lambda: e.num(DAY_START))
    e.set(CHECK, lambda: e.num(DAY_START))


def start_calendar(e, ctx, index, calendar):
    """The calendar's state afresh, its table's events on their days, and its first school day."""
    e.set(CAL, index)
    e.set(START, 0)
    for key, value in ((TIMED, 0), (SHOWN_DAY, -1), (SHOWN_WEEK, 0), (COUNT, 0), (WAITING_LEFT, 0), (NEST, 0),
                       (WEEKDAY0, calendar['first'][2]), (START_DOY, day_of_year(*calendar['first'][:2])),
                       (LAST_DAY, last_index(calendar)), (DAY_START, calendar['day_start']), (DAY_END, calendar['day_end']),
                       (MASK, sum(1 << w for w in set(calendar['weekdays'])))):
        e.set(key, value)
    clear, cleared = e.label(), e.label()
    e.store('clear_day', 0)
    e.mark(clear)
    e.load('clear_day'); e.num(LAST_DAY); e.op(0x0c); e.jump_if(cleared)
    e.set(e.day_count_key(lambda: e.load('clear_day')), 0)
    e.store('clear_day', lambda: (e.load('clear_day'), e.push(1), e.op(0x50)))
    e.jump(clear)
    e.mark(cleared)
    template_of = {}
    for cal, start in zip(ctx.project.calendars, _first_templates(ctx)):
        for k, event in enumerate(cal['events']):
            template_of[id(event)] = ctx.templates[start + k]
    rows = []
    for event, day in occurrences(calendar, calendar['events']):
        template = template_of[id(event)]
        rows += [template.number, day, event['minute'], int(template.first)]
    if rows:
        table = e.table(('start', index), rows + [0])
        top, done = e.label(), e.label()
        e.store('row', table)
        e.mark(top)
        e.load('row'); e.op(0x3f); e.jump_unless(done)
        field = lambda k: (lambda: (e.load('row'), e.push(k), e.op(0x50), e.op(0x3f)))
        e.add(field(0), field(1), field(2), field(3))
        e.store('row', lambda: (e.load('row'), e.push(4), e.op(0x50)))
        e.jump(top)
        e.mark(done)
    next_school_day(e, lambda: e.push(0))


def _first_templates(ctx):
    """Each calendar's first template's place in ctx.templates (the calendars' events come first, in order)."""
    starts, k = [], 0
    for calendar in ctx.project.calendars:
        starts.append(k)
        k += len(calendar['events'])
    return starts


def date_parts(e):
    """Scratch `month` (0-11) and `date` (1-31) of today."""
    ends = CUMULATIVE[:12] + (365,)
    e.store('doy', lambda: (e.num(START_DOY), e.num(DAY), e.op(0x50), e.push(365), e.op(0x54)))
    top, done = e.label(), e.label()
    e.store('month', 0)
    e.mark(top)
    e.load('month'); e.push(11); e.op(0x0d); e.jump_if(done)
    e.load('doy'); e.read_table('cumulative13', ends, lambda: (e.load('month'), e.push(1), e.op(0x50)))
    e.op(0x0e); e.jump_if(done)
    e.store('month', lambda: (e.load('month'), e.push(1), e.op(0x50)))
    e.jump(top)
    e.mark(done)
    e.store('date', lambda: (e.load('doy'), e.read_table('cumulative13', ends, lambda: e.load('month')), e.op(0x51),
                             e.push(1), e.op(0x50)))


def cards(e, ctx):
    """A new day's cards, as the running calendar has them: its week's card when the week changes (week cards on), then the date
    card (date cards on), `Friday, November 9` under the calendar's card title."""
    weekdays = e.table('weekday_names', [e.text(n) for n in WEEKDAYS])
    months = e.table('month_names', [e.text(n) for n in MONTHS])
    for index, calendar in enumerate(ctx.project.calendars, 1):
        if not (calendar['date_cards'] or calendar['week_cards']):
            continue
        other = e.label()
        e.num(CAL); e.push(index); e.op(0x0a); e.jump_unless(other)
        title = ctx.translated(f'calendar.{calendar["id"]}.card_title', calendar['card_title'])
        if calendar['week_cards']:
            week_card(e, months)
        if calendar['date_cards']:
            date_parts(e)
            buffer = e.buffer('date', 40)
            e.push(buffer); e.push(e.text('%s, %s %d'))
            e.push(weekdays); e.weekday(lambda: e.num(DAY)); e.op(0x50); e.op(0x3f)
            e.push(months); e.load('month'); e.op(0x50); e.op(0x3f)
            e.load('date')
            e.asm.emit(0x1f, 22 << 8 | 5)
            e.asm.call(8, buffer, e.text(title), -1, 0)
        e.mark(other)


def week_card(e, months):
    """`Week 2 of 13` over the week's dates, Monday (or the first day) to Friday (or the last), as the Fall '06 translation's week
    cards (tools/translate/brew.py week_card)."""
    def monday(day):
        day(); e.weekday(day); e.push(6); e.op(0x50); e.push(7); e.op(0x54); e.op(0x51)

    def week(day):
        monday(day); monday(lambda: e.push(0)); e.op(0x51); e.push(7); e.op(0x53); e.push(1); e.op(0x50)
    shown = e.label()
    e.store('week', lambda: week(lambda: e.num(DAY)))
    e.load('week'); e.num(SHOWN_WEEK); e.op(0x0a); e.jump_if(shown)
    e.set(SHOWN_WEEK, lambda: e.load('week'))
    e.store('first', lambda: e.larger(lambda: monday(lambda: e.num(DAY)), lambda: e.push(0)))
    e.store('last', lambda: (e.load('first'), e.push(4), e.op(0x50)))
    within = e.label()
    e.load('last'); e.num(LAST_DAY); e.op(0x0f); e.jump_if(within)
    e.store('last', lambda: e.num(LAST_DAY))
    e.mark(within)
    # The first and last days' months and dates, through date_parts with DAY standing at each for the moment.
    e.store('today', lambda: e.num(DAY))
    for which in ('first', 'last'):
        e.set(DAY, lambda which=which: e.load(which))
        date_parts(e)
        e.store(f'{which}_month', lambda: e.load('month'))
        e.store(f'{which}_date', lambda: e.load('date'))
    e.set(DAY, lambda: e.load('today'))

    def month(which):
        e.push(months); e.load(f'{which}_month'); e.op(0x50); e.op(0x3f)
    span, buffer = e.buffer('week_span', 40), e.buffer('week_title', 20)
    one_month, one_day, written = e.label(), e.label(), e.label()
    e.load('first_month'); e.load('last_month'); e.op(0x0a); e.jump_if(one_month)
    e.push(span); e.push(e.text('%s %d - %s %d')); month('first'); e.load('first_date'); month('last'); e.load('last_date')
    e.asm.emit(0x1f, 22 << 8 | 6); e.jump(written)
    e.mark(one_month)
    e.load('first_date'); e.load('last_date'); e.op(0x0a); e.jump_if(one_day)
    e.push(span); e.push(e.text('%s %d-%d')); month('first'); e.load('first_date'); e.load('last_date')
    e.asm.emit(0x1f, 22 << 8 | 5); e.jump(written)
    e.mark(one_day)
    e.push(span); e.push(e.text('%s %d')); month('first'); e.load('first_date')
    e.asm.emit(0x1f, 22 << 8 | 4)
    e.mark(written)
    e.push(buffer); e.push(e.text('Week %d of %d')); e.load('week'); week(lambda: e.num(LAST_DAY))
    e.asm.emit(0x1f, 22 << 8 | 4)
    e.asm.call(8, buffer, span, -1, 0)
    e.mark(shown)


def badge(e, ctx, B):
    """The event's badge, `3:00 PM - Practice` (its half hour, then its name; the time alone without one), with its icon."""
    names = [0] + [e.text(ctx.translated(t.key, t.name)) if t.name else 0 for t in ctx.templates]
    shows = [0] + [int(t.badge) for t in ctx.templates]
    icons = [0] + [CLOCK_ICON if t.icon == -1 else t.icon for t in ctx.templates]      # (-1 would take the badge away)
    template = lambda: e.occ(B, TEMPLATE_F)
    done, named, shown = e.label(), e.label(), e.label()
    e.read_table('badges', shows, template); e.jump_unless(done)
    e.store('slot', lambda: (e.occ(B, MINUTE_F), e.push(SLOT), e.op(0x53), e.push(SLOT), e.op(0x52)))
    slot = lambda: e.load('slot')
    buffer = e.buffer('badge', 40)

    def time():
        slot(); e.push(60); e.op(0x53); e.push(11); e.op(0x50); e.push(12); e.op(0x54); e.push(1); e.op(0x50)
        slot(); e.push(60); e.op(0x54); e.push(10); e.op(0x53)
        slot(); e.push(10); e.op(0x54)
        pm, end = e.label(), e.label()
        slot(); e.push(720); e.op(0x0e); e.jump_unless(pm)
        e.push(e.text('AM')); e.jump(end)
        e.mark(pm)
        e.push(e.text('PM'))
        e.mark(end)
    e.read_table('names', names, template); e.jump_if(named)
    e.push(buffer); e.push(e.text('%d:%d%d %s')); time(); e.asm.emit(0x1f, 22 << 8 | 6)
    e.jump(shown)
    e.mark(named)
    e.push(buffer); e.push(e.text('%d:%d%d %s - %s')); time(); e.read_table('names', names, template)
    e.asm.emit(0x1f, 22 << 8 | 7)
    e.mark(shown)
    e.read_table('icons', icons, template); e.push(buffer); e.asm.emit(0x1f, 90 << 8 | 2)
    e.set(BADGE_UP, 1)
    e.mark(done)


def badge_off(asm):
    """An event's badge stays for one line only and never shows on a title card (the owner's rule for the translated calendars,
    2026-11-17): the compiler emits this after a line, a choice's answer, a message or an entry, and before a title, in a project
    with a calendar. A badge the story sets itself (Scene label, Journal updated) is the story's to take away."""
    e = emitter(asm)
    done = e.label()
    e.num(BADGE_UP); e.jump_unless(done)
    asm.call(90, -1, -1)
    e.set(BADGE_UP, 0)
    e.mark(done)



def badge_owned(asm):
    """A badge the story set itself replaced the event's: it stays until the story takes it away."""
    emitter(asm).set(BADGE_UP, 0)

def emit_node(asm, ctx, node, p, expression):
    """A calendar node's code; `expression(text)` pushes an expression's value in this script."""
    e = emitter(asm)
    kind = node.kind
    if kind == 'start_calendar':
        e.set(START, ctx.indexes[p['calendar']])
        asm.call(10, ctx.driver_script, 0); asm.emit(0x33)
    elif kind == 'calendar_back':
        nested = e.label()
        e.num(NEST); e.push(0); e.op(0x0c); e.jump_if(nested)      # inside Run due events: back to the event that ran it
        asm.call(10, ctx.driver_script, 0)
        e.mark(nested)
        asm.emit(0x33)
    elif kind == 'schedule_event':
        template = ctx.by_name[(p['calendar'], p['event'])][0] if p['event'] else ctx.own[node.id]
        skip = e.label()
        e.num(CAL); e.push(template.calendar); e.op(0x0b); e.jump_if(skip)       # only into the calendar that's running
        minute = (lambda: expression(p['minute'])) if p['minute'].strip() else template.minute
        e.add(template.number, lambda: expression(p['day'] or 'day()'), minute, int(template.first or p['first']))
        e.mark(skip)
    elif kind == 'cancel_event':
        found = ctx.by_name.get((p['calendar'], p['event']), [])
        top, done = e.label(), e.label()
        e.store('cancel_n', 0)
        e.mark(top)
        e.store('cancel_n', lambda: (e.load('cancel_n'), e.push(1), e.op(0x50)))
        e.load('cancel_n'); e.num(COUNT); e.op(0x0c); e.jump_if(done)
        n = lambda: e.load('cancel_n')
        e.occ(n, STATE_F); e.push(DONE); e.op(0x0e); e.jump_unless(top)      # waiting or due
        if not found:
            e.jump(done)
        for k, template in enumerate(found):
            e.occ(n, TEMPLATE_F); e.push(template.number); e.op(0x0a)
            if k:
                e.op(0x11)
        e.jump_unless(top)
        e.set_occ(n, STATE_F, CANCELLED)
        e.set(WAITING_LEFT, lambda: (e.num(WAITING_LEFT), e.push(1), e.op(0x51)))
        if p['all']:
            e.jump(top)
        e.mark(done)
    elif kind == 'set_clock':
        e.set(CLOCK, lambda: e.larger(lambda: e.push(0), lambda: expression(p['minute'])))
    elif kind == 'skip_ahead':
        if p['to'] == 'end_of_day':
            e.set(CLOCK, lambda: (e.num(DAY_END), e.push(1), e.op(0x50)))
        else:
            e.set(CLOCK, lambda: e.larger(lambda: e.num(CLOCK), lambda: expression(p['minute'])))
    elif kind == 'run_due':
        durations = ctx.durations()

        def due(o):
            skip = e.label()
            e.occ(o, STATE_F); e.push(WAITING); e.op(0x0b); e.jump_if(skip)
            e.read_table('durations', durations, lambda: e.occ(o, TEMPLATE_F)); e.push(0); e.op(0x0d); e.jump_if(skip)
            e.occ(o, MINUTE_F); e.num(CHECK); e.op(0x0e); e.jump_if(skip)
            e.occ(o, MINUTE_F); e.num(CLOCK); e.op(0x0c); e.jump_if(skip)
            e.set_occ(o, STATE_F, DONE)
            e.set(WAITING_LEFT, lambda: (e.num(WAITING_LEFT), e.push(1), e.op(0x51)))
            e.store('due_o', o)
            due_template = lambda: e.occ(lambda: e.load('due_o'), TEMPLATE_F)
            ctx.condition(e, due_template, skip)
            e.set(NEST, lambda: (e.num(NEST), e.push(1), e.op(0x50)))
            ctx.enter(e, due_template)
            asm.emit(0x1f, 223 << 8 | 1)                                 # each to its end, inside this scene
            e.set(NEST, lambda: (e.num(NEST), e.push(1), e.op(0x51)))
            e.mark(skip)
        e.for_today('due', due)
        e.set(CHECK, lambda: (e.num(CLOCK), e.push(1), e.op(0x50)))
    elif kind == 'call_scene':
        e.set(-1, ctx.ordinals[p['target']])
        asm.call(223, ctx.script_of(p['target']))
    elif kind == 'return_scene':
        asm.emit(0x33)
    else:
        raise ProjectError(f'Unknown calendar node {kind}')
