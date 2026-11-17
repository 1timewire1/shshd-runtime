"""Bounded, reproducible player-input workflows over the production debugger."""
from .model import ProjectError

ENDS = {'episode_exit', 'finished'}
STORY_INPUTS = {'choice', 'text_input', 'word_game', 'word_grid', 'football', 'character_picker'}
# The translated mini-games, as the player plays them: a press (the go-ahead, then the game's own button), or a cell for SHS '11's;
# New Rules' arena takes key codes on its frames (nr_arena.KEY_BITS), a pick from its menu and an OK on its info box.
PRESS_GAMES = {'x360_slot', 'x360_leash', 'x360_puzzle', 'x360_diss', 'x360_battle', 'brew_catch', 'cutscene'}
CELL_GAMES = {'shs11_memory', 'shs11_reflex'}
ARENA = {'arena_frame', 'arena_menu', 'arena_info', 'arena_skip'}
INPUTS = STORY_INPUTS | PRESS_GAMES | CELL_GAMES | ARENA
ACKNOWLEDGE = {'dialogue', 'presentation', 'message_panel', 'survey_confirmation'}
TIMED = {'loading', 'arena_entrance', 'arena_exit'}      # screens that go on by themselves as time passes
FRAMED = PRESS_GAMES | CELL_GAMES | {'word_grid', 'football', 'arena_frame', 'arena_entrance', 'arena_exit'}
FRAME_MS = 16                   # a mini-game's time passes in frames, as a player's does (each caps a long one)
SKIP_ALWAYS = {'word_game', 'word_grid', 'football'}     # the prompt the player shows the first time these are seen
OK_PHASES = {'ready', 'tutorial', 'score', 'ended', 'goal', 'look', 'shown', 'bad'}  # a mini-game's screens a press goes on from


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
        if raw['action'] and raw['action'] != 'arena_frame' and token != self.last_event:
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
        if action in ('word_game', 'football', 'character_picker', 'arena_menu'): actions.append('answer')
        if action == 'arena_info': actions.append('continue')
        if action == 'word_grid': actions.append('grid_pointer')
        if action in PRESS_GAMES | CELL_GAMES or action == 'arena_frame': actions.append('press')
        if self.skippable(): actions.append('skip')
        if action not in ENDS and action is not None: actions.append('tick')
        if action is None: actions.extend(('run', 'step'))
        result = dict(node_id=raw['node'], scene=raw['scene'], pc=raw['pc'], action=action,
            paused=self.debugger.paused, variables=raw['variables'], text_variables=raw['text_variables'],
            text=raw['details'].get('text', raw['details'].get('prompt', '')),
            speaker=raw['details'].get('speaker', raw['details'].get('title', '')), choices=choices,
            remaining_ms=self.debugger.session.remaining_ms, next_actions=actions,
            visited_count=len(self.debugger.visited), seed=self.debugger.seed,
            manual_overrides=list(self.debugger.overrides), error=self.error)
        if action not in STORY_INPUTS | ACKNOWLEDGE | ENDS | {'loading', None}:
            result.update(pending_arguments=raw['pending_arguments'], details=raw['details'])
        minigame = self.minigame(raw)
        if minigame is not None: result['minigame'] = minigame
        if verbose: result['vm'] = raw
        return result

    def minigame(self, raw):
        """The open mini-game or cutscene as a player would read it: its score, time left, round and what it waits for."""
        session = self.debugger.session
        name = raw['action']
        game = raw['minigames'].get(name)
        if game is None: return None
        live = getattr(session.engine, name)
        summary = dict(kind=name, started=not session.minigame_unstarted if name != 'cutscene' else live.elapsed_ms > 0)
        for key in ('phase', 'score', 'points', 'round', 'target', 'level', 'right', 'wrong', 'found', 'remaining'):
            if key in game: summary[key] = game[key]
        result = getattr(live, 'result', None)
        if isinstance(result, int) and not isinstance(result, bool): summary['result'] = result
        if name == 'x360_slot':
            from exp_runtime.x360_games import DURATION_MS
            summary['time_left_ms'] = DURATION_MS - live.clock_ms
        elif name in CELL_GAMES: summary['time_left_ms'] = live.clock_ms
        elif name in ('x360_puzzle', 'x360_diss', 'x360_battle'): summary['time_left_ms'] = live.total_time * 1000
        elif name == 'cutscene':
            summary.update(elapsed_ms=live.elapsed_ms, skip_ms=live.skip_ms, hold_ms=live.hold_ms, held=live.held)
        phase = getattr(live, 'phase', None)
        if name == 'cutscene':
            summary['waits_for'] = 'press' if live.held else 'time or press'
        elif self.skippable():
            summary['waits_for'] = 'skip prompt or go-ahead'
        elif name in CELL_GAMES:
            # '11's tutorial screens take an OK (a press with no cell); its rounds take cells.
            summary['waits_for'] = ('cell' if phase == 'play' else 'press' if live.tutorial or phase in OK_PHASES
                                    else 'time')
        elif phase in OK_PHASES or name == 'brew_catch' and not live.started:
            summary['waits_for'] = 'press'      # a go-ahead, a tutorial page or the score screen's OK
        elif phase in ('running', None):
            summary['waits_for'] = 'press'
        else:
            summary['waits_for'] = 'time'       # an opening, countdown, time-up or closing
        return summary

    def skippable(self):
        """Whether the player's skip prompt (Ask to Skip Mini-Games) is over the pending screen, or it's a cutscene (always
        skippable)."""
        from exp_runtime.minigames import MINIGAMES
        session = self.debugger.session
        name = session.pending.name if session.pending else None
        return (name in ('cutscene', 'arena_skip') or name in SKIP_ALWAYS
                or (name in MINIGAMES and session.minigame_unstarted)) and not session.transitioning

    def skip_options(self):
        """The skip prompt's options, as the player lists them (its outcomes worked out on copies, as the player does): [{index,
        label, outcome}], Play last with outcome None. A cutscene's one option skips it."""
        session = self.debugger.session
        if session.pending and session.pending.name == 'cutscene': return [dict(index=0, label='Skip', outcome=None)]
        if not self.skippable(): raise ProjectError('No skip prompt here: run to a mini-game first')
        from exp_runtime.choice_hints import skip_prompt
        with self.debugger.plain():
            options = skip_prompt(session) or ()
        return [dict(index=index, label=label, outcome=outcome) for index, (label, outcome) in enumerate(options)]

    def frames(self, milliseconds):
        """Let `milliseconds` pass in player frames while the same screen (or New Rules' arena) stays up."""
        session = self.debugger.session
        action = session.pending
        left = milliseconds
        while left > 0 and not self.debugger.paused:
            step = min(FRAME_MS, left)
            self.debugger.resume(milliseconds=step); left -= step
            now = session.pending
            if now is not action and not (now and action and now.name in ARENA | TIMED and action.name in ARENA | TIMED): break
            action = now

    def call(self, operation):
        """A direct Session call (as the player's own prompt makes), run as resume runs its calls."""
        from .debugger import _Paused
        self.debugger.paused, self.debugger._step = False, False
        try: operation()
        except _Paused: pass

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
                    if action == 'cutscene' and until != 'input':
                        if self.debugger.session.engine.cutscene.held:
                            self.debugger.resume(provide_answer=True)      # watched to its end: the press that closes it
                        else:
                            if elapsed >= max_ms: return 'clock_budget'
                            step = min(100, max_ms - elapsed)
                            self.debugger.resume(milliseconds=step); elapsed += step
                        continue
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
                    elif action in TIMED:
                        if elapsed >= max_ms: return 'clock_budget'
                        step = min(100 if action == 'loading' else FRAME_MS, max_ms - elapsed)
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
        if action not in ('continue', 'answer_text', 'answer', 'tick', 'step', 'grid_pointer', 'press', 'skip'):
            raise ProjectError('Unknown playtest input')
        if type(milliseconds) is not int or not 0 <= milliseconds <= 60000:
            raise ProjectError('Clock step must be 0–60000 ms')
        def execute():
            session = self.debugger.session
            name = session.pending.name if session.pending else None
            if action == 'tick':
                if milliseconds and name in FRAMED: self.frames(milliseconds)
                elif milliseconds: self.debugger.resume(milliseconds=milliseconds)
            elif action == 'press':
                if name == 'arena_frame':
                    if type(value) is not int: raise ProjectError('A press on the arena takes a key code')
                    session.arena_press(value)
                elif name in CELL_GAMES:
                    if value is not None and (type(value) is not int or not 0 <= value < 9):
                        raise ProjectError('Press a cell 0-8, or nothing for the go-ahead')
                    self.debugger.resume(answer=value, provide_answer=True)
                elif name in PRESS_GAMES:
                    if value is not None: raise ProjectError(f'{name} takes a press with no value')
                    self.debugger.resume(provide_answer=True)
                else:
                    raise ProjectError('Nothing here takes a press')
                if milliseconds: self.frames(milliseconds)
            elif action == 'skip':
                self.skip(value)
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

    def skip(self, option):
        """Answer the skip prompt with an option by its label or index, as the player's tap does; a cutscene is pressed to its
        end (its skip, then its close)."""
        session = self.debugger.session
        if session.pending and session.pending.name == 'cutscene':
            if option not in (None, 0, 'Skip'): raise ProjectError('A cutscene has one skip option')
            cutscene = session.pending
            for _ in range(3):
                if session.pending is not cutscene or self.debugger.paused: break
                self.debugger.resume(provide_answer=True)
            return
        options = self.skip_options()
        if isinstance(option, str):
            found = [entry for entry in options if entry['label'].casefold() == option.casefold()]
        elif type(option) is int:
            found = [entry for entry in options if entry['index'] == option]
        else:
            found = []
        if not found:
            raise ProjectError('Choose a skip option by its label or index: ' + ', '.join(entry['label'] for entry in options))
        from exp_runtime.choice_hints import answer_skip_prompt
        self.call(lambda: answer_skip_prompt(session, found[0]['outcome']))


def run_scenario(debugger, scenario):
    """Replay a declarative scenario. No eval, arbitrary code or fabricated results."""
    steps = scenario.get('steps', [])
    assertions = scenario.get('assertions', [])
    if (not isinstance(steps, list) or len(steps) > 200 or not isinstance(assertions, list) or
            len(assertions) > 200 or set(scenario) - {'seed', 'start', 'language', 'minigames', 'cutscenes', 'skip_arena',
                                                      'steps', 'assertions'}):
        raise ProjectError('A scenario allows seed/start/language/minigames/cutscenes/skip_arena, up to 200 steps and 200 '
                           'assertions')
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
