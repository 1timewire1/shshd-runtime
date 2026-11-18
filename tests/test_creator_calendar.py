"""The Creator's calendars (CREATOR_CALENDAR_DESIGN.md; owner, 2026-11-17): compiled to KiWi and played in the engine through the
playtest, as a player would see them: date and week cards, time badges, the order events run in, conditions, scheduling and
cancelling while playing, the clock, events inside events, several calendars and a save in the middle."""
import unittest

from exp_runtime.creator.calendar import blank_calendar, blank_event, preview
from exp_runtime.creator.compiler import compile_project
from exp_runtime.creator.debugger import DebugSession
from exp_runtime.creator.model import Node, Project, ProjectError
from exp_runtime.creator.playtest import ENDS, Playtest


def event(name, node, **fields):
    found = blank_event(node)
    found.update(name=name, **fields)
    return found


def term(**fields):
    calendar = blank_calendar('term')
    calendar.update(first=[9, 13, 1], last=[9, 17], after='after')
    calendar['events'] = [
        event('Class', 'class', when='school_days', date=[9, 13], until=[9, 17], minute=540, duration=60),
        event('Lunch', 'lunch', date=[9, 13], minute=720, timed=False),
        event('Practice', 'practice', date=[9, 15], minute=540, duration=30, first=True),
        event('Secret', 'secret', date=[9, 13], minute=900, condition='met == 1'),
    ]
    calendar.update(fields)
    return calendar


def story(*extra, met=0, calendars=None, class_nodes=None, lunch_nodes=None):
    nodes = [
        Node('start', 'set', variable='met', value=met, next='intro'),
        Node('intro', text='The term begins.', next='go'),
        Node('go', 'start_calendar', params={'calendar': 'term'}),
        *(class_nodes or [Node('class', text='Class on day {day()}.', next='b1')]),
        Node('b1', 'calendar_back'),
        *(lunch_nodes or [Node('lunch', text='Lunch.', next='b2')]),
        Node('b2', 'calendar_back'),
        Node('practice', text='Practice!', next='b3'),
        Node('b3', 'calendar_back'),
        Node('secret', text='Secret!', next='b4'),
        Node('b4', 'calendar_back'),
        Node('after', text='Done.', next='end'),
        Node('end', 'end'),
        *extra,
    ]
    return Project(title='Calendar', game='shs', start='start', nodes=nodes, calendars=calendars or [term()])


def play(project, steps=80, seed=1, debugger=None):
    """What the player sees, a line each: `card: title / subtitle`, `Line text [badge]`, and `END` at the episode's end."""
    debugger = debugger or DebugSession(project, seed=seed)
    test, seen = Playtest(debugger), []
    try:
        for _ in range(steps):
            state = test.run(until='input', max_operations=2000)
            if state['error']:
                raise AssertionError(state['error'])
            action = state['action']
            if action in ENDS:
                seen.append('END')
                break
            if action == 'presentation':
                details = debugger.session.pending.details
                seen.append(f'card: {details.get("title", "")} / {details.get("subtitle", "")}')
            elif action == 'dialogue':
                badge = debugger.session.engine.scene_badge
                seen.append(state['text'] + (f' [{badge.text}]' if badge else ''))
            else:
                seen.append(f'? {action}')
                break
            test.input('tick', milliseconds=3000)
            test.input('continue')
        return seen
    finally:
        if debugger is not None:
            debugger.close()


class Plays(unittest.TestCase):
    def test_a_term_runs_its_events_by_bremws_rules(self):
        self.assertEqual(play(story()), [
            'The term begins.',
            'card: Monday, September 13 / ',
            'Class on day 0. [9:00 AM - Class]',
            'Lunch. [12:00 PM - Lunch]',                 # untimed, in its half hour
            'card: Wednesday, September 15 / ',          # Monday, Wednesday and Friday
            'Practice! [9:00 AM - Practice]',            # First wins the half hour; Class's minute has passed
            'card: Friday, September 17 / ',
            'Class on day 4. [9:00 AM - Class]',
            'Done.',                                     # the After node, its badge gone
            'END'])

    def test_a_badge_stays_for_one_line(self):
        nodes = [Node('class', text='Class on day {day()}.', next='c2'), Node('c2', text='Still in class.', next='b1')]
        seen = play(story(class_nodes=nodes))
        start = seen.index('Class on day 0. [9:00 AM - Class]')
        self.assertEqual(seen[start + 1], 'Still in class.')

    def test_a_condition_true_when_its_turn_comes_lets_it_run(self):
        seen = play(story(met=1))
        self.assertIn('Secret! [3:00 PM - Secret]', seen)

    def test_week_cards_and_a_card_title(self):
        seen = play(story(calendars=[term(week_cards=True, card_title='Fall Term')]))
        self.assertEqual(seen[1:3], ['card: Week 1 of 1 / September 13-17', 'card: Monday, September 13 / Fall Term'])

    def test_any_school_days_and_no_after_node_ends_the_episode(self):
        seen = play(story(calendars=[term(weekdays=[1, 2], after='')]))
        self.assertEqual([line for line in seen if line.startswith('card')],
                         ['card: Monday, September 13 / ', 'card: Tuesday, September 14 / '])
        self.assertEqual(seen[-1], 'END')
        self.assertNotIn('Done.', seen)


class WhilePlaying(unittest.TestCase):
    def test_schedule_an_event_of_the_table_and_a_scene_of_its_own(self):
        lunch = [Node('lunch', text='Lunch.', next='s1'),
                 Node('s1', 'schedule_event', params={'calendar': 'term', 'target': 'date', 'name': 'Date',
                                                      'day': 'day() + 2', 'minute': '1140', 'icon': 3114}, next='s2'),
                 Node('s2', 'schedule_event', params={'calendar': 'term', 'event': 'Practice', 'day': 'next_weekday(5)',
                                                      'minute': '600'}, next='b2')]
        seen = play(story(Node('date', text='A date!', next='b5'), Node('b5', 'calendar_back'), lunch_nodes=lunch))
        wednesday = seen.index('card: Wednesday, September 15 / ')
        self.assertEqual(seen[wednesday + 1:wednesday + 3], ['Practice! [9:00 AM - Practice]', 'A date! [7:00 PM - Date]'])
        friday = seen.index('card: Friday, September 17 / ')
        self.assertEqual(seen[friday + 1:friday + 3], ['Class on day 4. [9:00 AM - Class]', 'Practice! [10:00 AM - Practice]'])

    def test_cancel_every_class(self):
        lunch = [Node('lunch', text='Lunch.', next='c1'),
                 Node('c1', 'cancel_event', params={'calendar': 'term', 'event': 'Class'}, next='b2')]
        seen = play(story(lunch_nodes=lunch))
        self.assertEqual([line for line in seen if line.startswith('Class')], ['Class on day 0. [9:00 AM - Class]'])

    def test_skip_to_the_end_of_the_day_misses_the_rest(self):
        nodes = [Node('class', text='Class on day {day()}.', next='k1'),
                 Node('k1', 'skip_ahead', params={'to': 'end_of_day'}, next='b1')]
        seen = play(story(class_nodes=nodes))
        self.assertNotIn('Lunch. [12:00 PM - Lunch]', seen)

    def test_run_due_events_runs_lunch_inside_class(self):
        nodes = [Node('class', text='Class on day {day()}.', next='k1'),
                 Node('k1', 'set_clock', params={'minute': '760'}, next='k2'),
                 Node('k2', 'run_due', next='k3'),
                 Node('k3', text='Back in class at {minute()}.', next='b1')]
        seen = play(story(class_nodes=nodes))
        start = seen.index('Class on day 0. [9:00 AM - Class]')
        self.assertEqual(seen[start + 1:start + 3], ['Lunch.', 'Back in class at 760.'])     # Class's badge went with its line
        self.assertEqual(seen.count('Lunch.') + seen.count('Lunch. [12:00 PM - Lunch]'), 1)

    def test_run_a_scene_and_come_back(self):
        nodes = [Node('class', text='Class.', next='k1'),
                 Node('k1', 'call_scene', params={'target': 'aside'}, next='k2'),
                 Node('k2', text='After the aside.', next='b1')]
        extra = [Node('aside', text='An aside.', next='r', scene=25002), Node('r', 'return_scene', scene=25002)]
        seen = play(story(*extra, class_nodes=nodes))
        start = seen.index('Class. [9:00 AM - Class]')
        self.assertEqual(seen[start + 1:start + 3], ['An aside.', 'After the aside.'])


class Functions(unittest.TestCase):
    def test_date_maths_and_queries(self):
        nodes = [Node('class', text=('{date(9, 15)} {days_between(9, 13, 9, 17)} {next_weekday(3)} {weekday()} '
                                     '{events_between(540, 600)} {events_between(0, 539)} {event_first("Practice")} '
                                     '{event_first("Class")}'), next='b1')]
        seen = play(story(class_nodes=nodes))
        self.assertEqual(seen[2], '2 4 2 1 1 0 1 0 [9:00 AM - Class]')

    def test_they_need_a_calendar(self):
        project = Project(title='No calendar', game='shs', start='a',
                          nodes=[Node('a', text='Day {day()}.', next='end'), Node('end', 'end')])
        with self.assertRaisesRegex(ProjectError, 'calendar'):
            compile_project(project)


    def test_a_scene_labels_icon_from_the_story(self):
        nodes = [Node('class', 'scene_label', params={'icon_expression': '3100 + weekday()'}, text='Day {day()}', next='c2'),
                 Node('c2', text='Class.', next='b1')]
        debugger = DebugSession(story(class_nodes=nodes), seed=1)
        try:
            test = Playtest(debugger)
            while test.run(until='input')['text'] != 'Class.':
                test.input('tick', milliseconds=3000); test.input('continue')
            badge = debugger.session.engine.scene_badge
            self.assertEqual((badge.asset_id, badge.text), (3101, 'Day 0'))
        finally:
            debugger.close()


class SeveralAndSaved(unittest.TestCase):
    def test_one_calendar_runs_into_the_next(self):
        summer = blank_calendar('summer')
        summer.update(name='Summer', first=[6, 1, 1], last=[6, 3], weekdays=[1, 2, 3, 4, 5], after='after',
                      events=[event('Beach', 'lunch', date=[6, 2], minute=600, timed=False)])
        first = term(after='to_summer')
        seen = play(story(Node('to_summer', 'start_calendar', params={'calendar': 'summer'}), calendars=[first, summer]))
        self.assertEqual(seen[-4:], ['card: Tuesday, June 2 / ', 'Lunch. [10:00 AM - Beach]', 'Done.', 'END'])

    def test_a_save_in_the_middle_plays_on_the_same(self):
        from exp_runtime.runtime import Session
        whole = play(story())
        debugger = DebugSession(story(), seed=1)
        test = Playtest(debugger)
        for _ in range(4):                  # to Lunch
            test.run(until='input'); test.input('tick', milliseconds=3000); test.input('continue')
        state = debugger.session.snapshot()
        debugger.session = Session.from_snapshot(debugger.session.resources, state)
        debugger.session.vm.run = debugger.session.vm.run      # (the restored session runs unwrapped: no node stepping)
        rest = play(None, debugger=debugger)
        self.assertEqual(rest, whole[-len(rest):])


class Checks(unittest.TestCase):
    def test_the_table_previews_by_day(self):
        days = preview(term())
        self.assertEqual([d['date'] for d in days], ['Monday, September 13', 'Wednesday, September 15', 'Friday, September 17'])
        self.assertEqual([e['name'] for e in days[0]['events']], ['Class', 'Lunch', 'Secret'])

    def test_bad_calendars_are_refused(self):
        for change, message in ((dict(after='nowhere'), 'After node'), (dict(weekdays=[]), 'school days'),
                                (dict(last=[1, 30]), 'at most 120 days'), (dict(day_end=100), 'day end')):
            with self.subTest(change=change):
                with self.assertRaisesRegex(ProjectError, message):
                    compile_project(story(calendars=[term(**change)]))
        crowded = term()
        crowded['events'] = [event(f'E{k}', 'lunch', date=[9, 13], minute=600) for k in range(33)]
        with self.assertRaisesRegex(ProjectError, 'more than 32 events'):
            compile_project(story(calendars=[crowded]))
        missing = story()
        missing.nodes[2].params['calendar'] = 'winter'
        with self.assertRaisesRegex(ProjectError, 'calendars'):
            compile_project(missing)

    def test_only_nested_runs_are_this_runtimes(self):
        from exp_runtime.creator.addons import mechanics
        self.assertEqual(mechanics(story()), [])
        nested = story(class_nodes=[Node('class', text='Class.', next='k'), Node('k', 'run_due', next='b1')])
        self.assertEqual(mechanics(nested), ['running a scene and coming back'])

    def test_cod_has_no_calendars(self):
        project = story()
        project.game = 'cod'
        with self.assertRaises(ProjectError):
            compile_project(project)


if __name__ == '__main__':
    unittest.main()
