"""Bounded, reproducible player-input workflows over the production debugger."""
from .model import ProjectError

ENDS = {'episode_exit', 'finished'}
INPUTS = {'choice', 'text_input', 'word_game', 'word_grid', 'football', 'character_picker'}
ACKNOWLEDGE = {'dialogue', 'presentation', 'message_panel', 'survey_confirmation'}


class Playtest:
    def __init__(self, debugger):
        self.debugger = debugger
        self.transcript = []
        self.last_event = None
        self.sequence = 0
        self.error = None

    def capture(self):
        raw = self.debugger.state()
        details = raw['details']
        token = (raw['scene'], raw['pc'], self.debugger.session.vm.steps_executed,
                 raw['action'], details.get('page_start'))
        if raw['action'] and token != self.last_event:
            self.last_event = token
            self.sequence += 1
            self.transcript.append(dict(sequence=self.sequence, node_id=raw['node'], action=raw['action'],
                speaker=details.get('speaker', details.get('title', '')), text=details.get('text', details.get('prompt', '')),
                options=self.choices(raw), page_start=details.get('page_start')))
            del self.transcript[:-200]
        return raw

    def choices(self, raw):
        if raw['action'] != 'choice': return []
        details = raw['details']
        return [dict(id=f'{raw["node"]}:{value}', text=text, enabled=enabled, visible_index=index)
                for index, (text, value, enabled) in enumerate(zip(details['options'], details['values'], details['enabled']))]

    def state(self, *, verbose=False):
        raw = self.capture()
        action = raw['action']
        choices = self.choices(raw)
        actions = []
        if action in ACKNOWLEDGE or action == 'vm_pause': actions.append('continue')
        if action == 'choice': actions.append('choose')
        if action == 'text_input': actions.append('answer_text')
        if action in ('word_game', 'football', 'character_picker'): actions.append('answer')
        if action == 'word_grid': actions.append('grid_pointer')
        if action not in ENDS and action is not None: actions.append('tick')
        if action is None: actions.extend(('run', 'step'))
        result = dict(node_id=raw['node'], scene=raw['scene'], pc=raw['pc'], action=action,
            paused=self.debugger.paused, variables=raw['variables'], text_variables=raw['text_variables'],
            text=raw['details'].get('text', raw['details'].get('prompt', '')),
            speaker=raw['details'].get('speaker', raw['details'].get('title', '')), choices=choices,
            remaining_ms=self.debugger.session.remaining_ms, next_actions=actions,
            visited_count=len(self.debugger.visited), seed=self.debugger.seed,
            manual_overrides=list(self.debugger.overrides), error=self.error)
        if action not in INPUTS | ACKNOWLEDGE | ENDS | {'loading', None}:
            result.update(pending_arguments=raw['pending_arguments'], details=raw['details'])
        if verbose: result['vm'] = raw
        return result

    def perform(self, operation):
        before = self.debugger.state()['variables']
        sequence = self.sequence
        self.error = None
        try:
            reason = operation()
        except (ValueError, KeyError, IndexError) as error:
            # A real VM/service failure is visible and stays suspended. Do not
            # supply a guessed callback result or roll gameplay forward.
            self.error = str(error)
            reason = 'error'
        result = self.state()
        result.update(stop_reason=reason, variable_changes={key: dict(before=before.get(key), after=value)
            for key, value in result['variables'].items() if before.get(key) != value},
            transcript=[row for row in self.transcript if row['sequence'] > sequence],
            transcript_truncated=self.sequence - sequence > 200)
        return result

    def run(self, *, until='input', node_id=None, max_operations=500, max_ms=60000):
        if until not in ('input', 'choice', 'end', 'node'): raise ProjectError('Use until input, choice, end or node')
        if until == 'node' and node_id not in {n.id for n in self.debugger.project.nodes}:
            raise ProjectError('Select an existing node as the stopping point')
        if type(max_operations) is not int or not 1 <= max_operations <= 2000:
            raise ProjectError('Operation budget must be 1–2000')
        if type(max_ms) is not int or not 0 <= max_ms <= 60000:
            raise ProjectError('Clock budget must be 0–60000 ms')
        def execute():
            elapsed = 0
            original = set(self.debugger.breakpoints)
            if until == 'node': self.debugger.breakpoints.add(node_id)
            try:
                for _ in range(max_operations):
                    raw = self.capture(); action = raw['action']
                    if action in ENDS: return 'end'
                    if self.debugger.paused and (raw['node'] == node_id or raw['node'] in original): return 'breakpoint'
                    if action in INPUTS: return 'choice' if action == 'choice' else 'input'
                    if until == 'input' and action in ACKNOWLEDGE: return 'input'
                    if action in ACKNOWLEDGE:
                        session = self.debugger.session
                        ready = (session.engine.dialogue_animation.complete if action == 'dialogue' else
                                 session.engine.title_screen.ready if action == 'presentation' else
                                 session.engine.message_panel.ready)
                        if ready:
                            self.debugger.resume(provide_answer=True)
                        else:
                            if elapsed >= max_ms: return 'clock_budget'
                            step = min(100, max_ms - elapsed)
                            self.debugger.resume(milliseconds=step); elapsed += step
                    elif action == 'loading':
                        if elapsed >= max_ms: return 'clock_budget'
                        step = min(100, max_ms - elapsed)
                        self.debugger.resume(milliseconds=step); elapsed += step
                    elif action is None:
                        self.debugger.resume()
                    else:
                        return 'unsupported'  # Includes explicit VM pauses; only manual input may resume those.
                return 'operation_budget'
            finally:
                self.debugger.breakpoints = original
        return self.perform(execute)

    def choose(self, option_id):
        raw = self.debugger.state()
        option = next((o for o in self.choices(raw) if o['id'] == option_id), None)
        if option is None or not option['enabled']: raise ProjectError('Choose an enabled option ID from the current state')
        def execute():
            session = self.debugger.session
            pending = session.pending
            if not session.choice_ready:
                self.debugger.resume(milliseconds=250 - session.engine.choice_ms)
            # A very short timed choice can expire during its entrance. Never
            # send the old option to the next panel or bypass the real clock.
            if session.pending is pending:
                self.debugger.resume(answer=option['visible_index'], provide_answer=True)
            return 'input'
        return self.perform(execute)

    def input(self, action, *, value=None, milliseconds=0, phase=None, cell=None):
        if action not in ('continue', 'answer_text', 'answer', 'tick', 'step', 'grid_pointer'):
            raise ProjectError('Unknown playtest input')
        if type(milliseconds) is not int or not 0 <= milliseconds <= 60000:
            raise ProjectError('Clock step must be 0–60000 ms')
        def execute():
            if action == 'tick':
                if milliseconds: self.debugger.resume(milliseconds=milliseconds)
            elif action == 'step': self.debugger.resume(step=True)
            elif action == 'grid_pointer':
                from .debugger import _Paused
                if phase not in ('down', 'move', 'up', 'cancel'): raise ProjectError('Invalid pointer phase')
                try: self.debugger.session.grid_pointer(phase, cell)
                except _Paused: pass
            else:
                self.debugger.resume(answer=None if action == 'continue' else value, provide_answer=True)
            return 'input'
        return self.perform(execute)


def run_scenario(debugger, scenario):
    """Replay a declarative scenario. No eval, arbitrary code or fabricated results."""
    steps = scenario.get('steps', [])
    assertions = scenario.get('assertions', [])
    if (not isinstance(steps, list) or len(steps) > 200 or not isinstance(assertions, list) or
            len(assertions) > 200 or set(scenario) - {'seed', 'start', 'language', 'steps', 'assertions'}):
        raise ProjectError('A scenario allows seed/start/language, up to 200 steps and 200 assertions')
    test, results, failures = Playtest(debugger), [], []
    for index, step in enumerate(steps):
        try:
            args = dict(step); action = args.pop('action')
            if action == 'run': result = test.run(**args)
            elif action == 'choose': result = test.choose(**args)
            else: result = test.input(action, **args)
            results.append(dict(step=index, action=result['action'], node_id=result['node_id'],
                                stop_reason=result['stop_reason'], variable_changes=result['variable_changes']))
            if result['stop_reason'] in ('error', 'unsupported', 'operation_budget', 'clock_budget'):
                failures.append(dict(step=index, message=result['error'] or result['stop_reason'])); break
        except (TypeError, ValueError, KeyError) as error:
            failures.append(dict(step=index, message=str(error))); break
    state = test.state()
    for index, assertion in enumerate(assertions):
        kind = assertion.get('kind') if isinstance(assertion, dict) else None
        if kind in ('variable', 'text_variable'):
            values = state['variables' if kind == 'variable' else 'text_variables']
            if assertion.get('name') not in values or 'equals' not in assertion:
                failures.append(dict(assertion=index, message='Name must identify an existing variable and equals is required')); continue
            actual, expected = values[assertion['name']], assertion['equals']
        elif kind == 'node': actual, expected = state['node_id'], assertion.get('equals')
        elif kind == 'action': actual, expected = state['action'], assertion.get('equals')
        elif kind == 'visited': actual, expected = assertion.get('node_id') in debugger.visited, True
        elif kind == 'ended': actual, expected = state['action'] in ENDS, True
        else:
            failures.append(dict(assertion=index, message='Unknown assertion kind')); continue
        if actual != expected:
            failures.append(dict(assertion=index, message='Assertion failed', actual=actual, expected=expected))
    return dict(passed=not failures, failures=failures, steps=results, state=state, transcript=test.transcript,
                coverage=dict(visited=sorted(debugger.visited), total=len(debugger.project.nodes)))
