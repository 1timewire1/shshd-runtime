"""Shared desktop/file authoring operations restricted to one workspace."""
from copy import deepcopy
from dataclasses import asdict, fields, is_dataclass
import hashlib
import json
import re
from pathlib import Path
import threading
import uuid

from .compiler import compile_details
from .model import (Project, ProjectError, atomic_write, project_from_record,
                    project_bytes, project_from_bytes, project_record, save_project, validate_structure)
from .sharing import guard, session_info, snapshot, request, digest


class Workspace:
    def __init__(self, root):
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir(): raise ProjectError('Workspace must be an existing directory')
        self.lock = threading.RLock()
        self.debuggers = {}
        self.playtests = {}
        self.responses = {}

    def path(self, name, suffix=None):
        path = (self.root / name).resolve()
        if not path.is_relative_to(self.root) or path == self.root:
            raise ProjectError('Paths must remain inside the configured workspace')
        if suffix and path.suffix.lower() != suffix:
            raise ProjectError(f'Expected a {suffix} file')
        return path

    def revision(self, path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def read(self, name):
        state = self.snapshot(name)
        return state.project, state.revision

    def snapshot(self, name):
        return snapshot(self.path(name, '.expproj'))

    def describe(self, name, offset=0, limit=100):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 200:
            raise ProjectError('Use a nonnegative offset and limit from 1 to 200')
        state = self.snapshot(name)
        project = state.project
        return {'revision': state.revision, 'live': state.live, 'unsaved': state.unsaved,
                'title': project.title, 'game': project.game,
                'pack_id': project.pack_id, 'episode_id': project.episode_id, 'start': project.start,
                'language': project.language, 'locales': project.locales, 'library': project.library,
                'native': bool(project.native), 'node_count': len(project.nodes),
                'nodes': [asdict(n) for n in project.nodes[offset:offset + limit]],
                'characters': [asdict(c) for c in project.characters],
                'assets': [{'id': a.id, 'name': a.name, 'embedded': a.data is not None,
                            'bytes': len(a.data) if a.data else 0} for a in project.assets]}

    def create(self, name, title='Untitled episode', game='shs', pack_id=30000, episode_id=1):
        with self.lock:
            path = self.path(name, '.expproj')
            with guard(path):
                if path.exists() or session_info(path): raise ProjectError('Project already exists')
                project = Project(title=title, game=game, pack_id=pack_id, episode_id=episode_id)
                save_project(project, path)
            return self.describe(name)

    def edit(self, name, revision, operation):
        with self.lock:
            project, actual = self.read(name)
            if not revision or revision != actual:
                raise ProjectError('Project changed; read its current revision before editing')
            before = deepcopy(project)
            operation(project)
            validate_structure(project)
            from .operations import check_removals
            check_removals(before, project)
            result = self.commit(name, revision, project_bytes(project, self.path(name)))
            return dict(**result, changed=self.changes(before, project), library=project.library)

    def commit(self, name, revision, data):
        path = self.path(name, '.expproj')
        project = project_from_bytes(data, path)
        with guard(path):
            info = session_info(path)
            if info is None:
                previous = path.read_bytes()
                if digest(previous) != revision:
                    raise ProjectError('Project changed; read its current revision before editing')
                checkpoint = self._checkpoint(name, previous, 'Before edit')
                atomic_write(path, data)
                return dict(revision=digest(data), undo_checkpoint=checkpoint['checkpoint'], live=False, unsaved=False)
        # Do not hold a filesystem lock while the GUI processes a request. The
        # GUI checks the revision again, including edits made after this read.
        checkpoint = self.checkpoint(name, revision, 'Before edit')
        result = request(info, 'commit', revision=revision, project=project_record(project))
        return dict(**result, undo_checkpoint=checkpoint['checkpoint'])

    @staticmethod
    def changes(before, after):
        def brief(value):
            if is_dataclass(value): return brief(asdict(value))
            if isinstance(value, bytes): return dict(bytes=len(value), sha256=hashlib.sha256(value).hexdigest())
            if isinstance(value, str) and len(value) > 1000:
                return dict(preview=value[:1000], characters=len(value), truncated=True)
            if isinstance(value, list): return [brief(v) for v in value[:20]] + ([dict(truncated=True, total=len(value))] if len(value) > 20 else [])
            if isinstance(value, dict):
                keys = list(value)[:20]
                result = {k: brief(value[k]) for k in keys}
                if len(keys) < len(value): result['_truncated'] = dict(total=len(value))
                return result
            return value
        result = {}
        for field in fields(Project):
            a, b = getattr(before, field.name), getattr(after, field.name)
            if a == b: continue
            if field.name in ('nodes', 'characters', 'assets'):
                old, new = {r.id: r for r in a}, {r.id: r for r in b}
                updated = sorted(key for key in new.keys() & old.keys() if new[key] != old[key])
                result[field.name] = dict(added=sorted(new.keys() - old.keys()), removed=sorted(old.keys() - new.keys()),
                    updated=updated, details={key: {f.name: dict(before=brief(getattr(old[key], f.name)),
                        after=brief(getattr(new[key], f.name))) for f in fields(new[key])
                        if getattr(old[key], f.name) != getattr(new[key], f.name)} for key in updated[:20]})
                if len(updated) > 20: result[field.name]['details_truncated'] = True
            else:
                result[field.name] = dict(before=brief(a), after=brief(b))
        return result

    def batch(self, name, revision, operations, *, preview=False):
        from .operations import apply, check_removals
        if not isinstance(operations, list) or not 1 <= len(operations) <= 200:
            raise ProjectError('A transaction needs 1–200 operations')
        def run(project):
            for index, operation in enumerate(operations):
                try: apply(self, project, operation)
                except (KeyError, TypeError, ValueError) as error:
                    raise ProjectError(f'Operation {index}: {error}') from error
        if not preview: return self.edit(name, revision, run)
        with self.lock:
            before, actual = self.read(name)
            if revision != actual: raise ProjectError('Project changed; read its current revision before editing')
            candidate = deepcopy(before); run(candidate)
            validate_structure(candidate); check_removals(before, candidate)
            from .diagnostics import diagnose
            return dict(revision=actual, changed=self.changes(before, candidate), validation=diagnose(candidate), applied=False)

    def _history(self, name):
        identity = str(self.path(name, '.expproj').relative_to(self.root))
        return self.path('.creator-history/' + hashlib.sha256(identity.encode()).hexdigest() + '/index.json')

    def checkpoints(self, name):
        with guard(self.path(name, '.expproj')):
            return self._checkpoints(name)

    def _checkpoints(self, name):
        index = self._history(name)
        if not index.exists(): return []
        records = json.loads(index.read_text(encoding='utf-8'))
        if (not isinstance(records, list) or len(records) > 40 or any(
                not isinstance(r, dict) or set(r) != {'checkpoint', 'revision', 'label'} or
                not isinstance(r['checkpoint'], str) or not re.fullmatch('[0-9a-f]{32}', r['checkpoint']) or
                not isinstance(r['revision'], str) or not re.fullmatch('[0-9a-f]{64}', r['revision']) or
                not isinstance(r['label'], str) for r in records)):
            raise ProjectError('Invalid checkpoint index')
        return records

    def checkpoint(self, name, revision, label='Checkpoint'):
        with self.lock:
            state = self.snapshot(name)
            if revision != state.revision: raise ProjectError('Project changed; reread before checkpointing')
            with guard(self.path(name, '.expproj')):
                return self._checkpoint(name, state.data, label)

    def _checkpoint(self, name, data, label):
        if not isinstance(label, str) or len(label) > 200: raise ProjectError('Checkpoint label must fit 200 characters')
        index = self._history(name)
        index.parent.mkdir(parents=True, exist_ok=True)
        records = self._checkpoints(name)
        key = uuid.uuid4().hex
        target = self.path(index.parent / (key + '.expproj'))
        atomic_write(target, data)
        record = dict(checkpoint=key, revision=digest(data), label=label)
        records.append(record)
        atomic_write(index, json.dumps(records[-40:]).encode())
        for old in records[:-40]:
            self.path(index.parent / (old['checkpoint'] + '.expproj')).unlink(missing_ok=True)
        return record

    def restore(self, name, revision, checkpoint):
        with self.lock:
            target = self.path(name, '.expproj')
            record = next((r for r in self.checkpoints(name) if r['checkpoint'] == checkpoint), None)
            if record is None: raise ProjectError('Unknown checkpoint for this project')
            source = self.path(self._history(name).parent / (checkpoint + '.expproj'))
            if self.revision(source) != record['revision']: raise ProjectError('Checkpoint checksum does not match')
            # Raw bytes retain library paths relative to the original project location.
            data = source.read_bytes()
            project_from_record(json.loads(data))
            result = self.commit(name, revision, data)
            return dict(**result, restored=checkpoint)

    def update(self, name, revision, changes):
        return self.batch(name, revision, [dict(op='project', changes=changes)])

    def node(self, name, revision, node_id, changes=None, remove=False):
        return self.batch(name, revision, [dict(op='node', id=node_id, changes=changes or {}, remove=remove)])

    def character(self, name, revision, character_id, changes=None, remove=False):
        return self.batch(name, revision, [dict(op='character', id=character_id, changes=changes or {}, remove=remove)])

    def import_image(self, name, revision, source):
        from .model import MAX_ASSET_BYTES
        path = self.path(source)
        if path.stat().st_size > MAX_ASSET_BYTES: raise ProjectError('Image is too large')
        return self.edit(name, revision, lambda project: project.add_image(path.name, path.read_bytes()))

    def import_audio(self, name, revision, source):
        return self.batch(name, revision, [dict(op='audio', source=source)])

    def library_image(self, name, revision, library, resource, episode=None):
        from exp_runtime.content import ContentLibrary
        from .assets import import_library_image
        path = self.path(library)
        def apply(project):
            with ContentLibrary(path) as content:
                import_library_image(project, content, resource, content.open_episode(episode) if episode else None)
        return self.edit(name, revision, apply)

    def import_episode(self, source, destination, game='shs'):
        from .native import import_exp
        from .model import MAX_PROJECT_BYTES
        with self.lock:
            source, output = self.path(source, '.exp'), self.path(destination, '.expproj')
            if source.stat().st_size > MAX_PROJECT_BYTES: raise ProjectError('EXP exceeds the editable project size limit')
            with guard(output):
                if output.exists() or session_info(output): raise ProjectError('Project destination already exists')
                save_project(import_exp(source.read_bytes(), game=game), output)
            return self.describe(destination)

    def export(self, name, destination, revision, language=None, replace_revision=None):
        with self.lock:
            project, actual = self.read(name)
            if actual != revision: raise ProjectError('Project changed; read its current revision before exporting')
            output = self.path(destination, '.exp')
            if output.exists() and self.revision(output) != replace_revision:
                raise ProjectError('Export exists; provide its SHA-256 as replace_revision to replace it')
            result = compile_details(project, language=language)
            atomic_write(output, result.data)
            return {'path': str(output.relative_to(self.root)), 'sha256': self.revision(output),
                    'bytes': len(result.data), 'scripts': sorted(result.locations)}

    def start_debug(self, name, start=None, *, seed=None, library=None, language=None):
        from .debugger import DebugSession
        if len(self.debuggers) >= 8: raise ProjectError('Close a debug session before starting another (limit 8)')
        project, revision = self.read(name)
        if library is not None: project.library = str(self.path(library)) if library else ''
        if project.library: project.library = str(self.path(project.library))
        debugger = DebugSession(project, start=start, seed=seed, library=project.library or None, language=language)
        key = uuid.uuid4().hex
        debugger.path, debugger.revision = name, revision
        self.debuggers[key] = debugger
        from .playtest import Playtest
        self.playtests[key] = Playtest(debugger)
        return {'session': key, 'revision': revision, **debugger.state()}

    def debugger(self, key):
        if key not in self.debuggers: raise ProjectError('Unknown or closed playtest session')
        return self.debuggers[key]

    def close_debug(self, key):
        debugger = self.debuggers.pop(key, None)
        if debugger is not None: debugger.close()
        self.playtests.pop(key, None)
        return dict(closed=True)
