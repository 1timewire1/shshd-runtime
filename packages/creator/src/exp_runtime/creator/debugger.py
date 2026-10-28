"""Source-node stepping and breakpoints using the production VM and services."""
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

from exp_runtime.exp import ExpArchive
from .compiler import VARIABLE_OWNER, compile_details
from .model import ProjectError


class _Paused(Exception):
    pass


class DebugSession:
    def __init__(self, project, *, start=None, seed=None, library=None, language=None):
        from exp_runtime.runtime import Session
        from exp_runtime.content import digest
        from exp_runtime.vm import StopKind
        self.project = project
        self.context = None
        self.compilation = compile_details(project, start=start, language=language)
        self.archive = ExpArchive(self.compilation.data)
        programs = self.archive.programs()
        self.resources = SimpleNamespace(library=SimpleNamespace(game_id=project.game, directory=Path('.')),
            identity={'profile': 'creator-debug', 'episode_sha256': digest(self.compilation.data)},
            program=programs.__getitem__, exists=lambda key: key in self.archive.entries or
            any(a.id == key for a in project.assets))
        if library:
            from .preview import preview_resources
            self.context = preview_resources(self.compilation.data, library, project.game)
            self.resources = self.context.__enter__()
        try: self.session = Session(self.resources, ephemeral=True)  # A debug run never writes story-tree files.
        except Exception:
            self.close()
            raise
        if seed is not None:
            if type(seed) is not int or not 0 <= seed <= 0xffffffff:
                self.close()
                raise ProjectError('Seed must be an unsigned 32-bit integer')
            self.session.engine.random.state = seed
            self.session.engine.random48.state = (seed << 16) | 0x330e
        self.seed = seed
        self.locations = {script: {pc: node for node, pc in entries.items()}
                          for script, entries in self.compilation.locations.items()}
        self.breakpoints = set()
        self.trace = []
        self.visited = set()
        self.overrides = []
        self.paused = False
        self._skip = None
        self._step = True
        original_run = self.session.vm.run
        def run(budget=100000):
            for _ in range(budget):
                position = (self.session.scene, self.session.vm.pc)
                node = self.locations.get(position[0], {}).get(position[1])
                if node and position != self._skip and (self._step or node in self.breakpoints):
                    self._skip = position
                    self.paused = True
                    raise _Paused()
                self._skip = None
                result = original_run(1)
                if node:
                    self.visited.add(node)
                    self.trace.append(node)
                    del self.trace[:-500]
                if result.kind != StopKind.BUDGET: return result
            return result
        self.session.vm.run = run
        try: self.resume(step=True)
        except Exception:
            self.close()
            raise

    def resume(self, *, step=False, answer=None, provide_answer=False, milliseconds=0):
        self.paused = False
        self._step = step
        try:
            if milliseconds:
                self.session.tick(milliseconds)
            elif provide_answer:
                self.session.answer(answer)
            else:
                self.session.advance()
        except _Paused:
            pass
        return self.state()

    def state(self):
        session = self.session
        pc = session.pending.request.pc if session.pending else session.vm.pc
        entries = self.locations.get(session.scene, {})
        before = [location for location in entries if location <= pc]
        node = entries[max(before)] if before else None
        values = {}
        for name, address in self.compilation.variables.items():
            values[name] = (session.engine.numbers.get(session.engine.number_key(VARIABLE_OWNER, address), 0)
                           if self.compilation.shared_variables else session.vm.data[address])
        pending = session.pending
        return {'node': node, 'scene': session.scene, 'pc': pc, 'variables': values,
                'text_variables': dict(session.engine.strings),
                'action': pending.name if pending else None,
                'details': pending.details if pending else {}, 'trace': list(self.trace),
                'minigames': {name: asdict(value) for name in ('word_game', 'football', 'word_grid')
                              if (value := getattr(session.engine, name)) is not None},
                'stack': list(session.vm.stack), 'result': session.vm.result,
                'pending_arguments': list(session.vm.pending.args) if session.vm.pending else []}

    def set_variable(self, name, value):
        if name not in self.compilation.variables or type(value) is not int or not -32768 <= value <= 32767:
            raise ProjectError('Choose an existing numeric variable and signed 16-bit value')
        address = self.compilation.variables[name]
        if self.compilation.shared_variables:
            self.session.engine.numbers[self.session.engine.number_key(VARIABLE_OWNER, address)] = value
        else:
            self.session.vm.write_word(address, value)
        self.overrides.append(dict(variable=name, value=value))

    def close(self):
        if self.context is not None:
            self.context.__exit__(None, None, None)
            self.context = None
