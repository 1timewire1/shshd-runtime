"""Shared, UI-independent graph edits and crash-recovery documents."""
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import uuid

from .model import (Choice, Node, ProjectError, atomic_write, project_from_record,
                    project_record, validate_structure)


def copy_nodes(project, selected):
    if project.native:
        raise ProjectError('Native blocks retain fixed PCs and cannot be duplicated')
    return json.dumps({'format': 'exp-creator-nodes', 'nodes': [asdict(n) for n in project.nodes if n.id in selected]})


def paste_nodes(project, text):
    try:
        data = json.loads(text)
        if data['format'] != 'exp-creator-nodes' or not 1 <= len(data['nodes']) <= 2000 or project.native:
            raise ValueError('unsupported clipboard')
        candidate = deepcopy(project)
        ids = {record['id']: uuid.uuid4().hex[:12] for record in data['nodes']}
        if len(ids) != len(data['nodes']): raise ValueError('duplicate source IDs')
        for record in data['nodes']:
            node = Node(**dict(record, options=[Choice(**o) for o in record['options']]))
            node.id = ids[node.id]
            node.x += 40; node.y += 40
            node.next, node.otherwise = ids.get(node.next, node.next), ids.get(node.otherwise, node.otherwise)
            for option in node.options: option.target = ids.get(option.target, option.target)
            candidate.nodes.append(node)
        validate_structure(candidate)
        project.nodes = candidate.nodes
        return list(ids.values())
    except (KeyError, TypeError, ValueError, RecursionError) as error:
        raise ProjectError(f'Cannot paste nodes: {error}') from error


def auto_layout(project):
    if len(project.nodes) > 20000: raise ProjectError('A graph can contain at most 20000 nodes')
    remaining = {node.id: node for node in project.nodes}
    frontier, level = [project.start], 0
    rows = [0] * 40
    while remaining:
        current = list(dict.fromkeys(key for key in frontier if key in remaining))
        if not current: current = [next(iter(remaining))]
        frontier = []
        for row, key in enumerate(current):
            node = remaining.pop(key)
            column = level % 40
            while rows[column] >= 500: column = (column + 1) % 40
            node.x, node.y = 40 + column * 310, 60 + rows[column] * 180
            rows[column] += 1
            frontier.extend(target for _, target in node.links() if target in remaining)
        level += 1


class Recovery:
    def __init__(self, directory, identity=None):
        self.path = Path(directory) / ((identity or uuid.uuid4().hex) + '.recovery.json')

    def write(self, project, source=None):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record = {'source': str(Path(source).resolve()) if source else None, 'project': project_record(project)}
        atomic_write(self.path, json.dumps(record, ensure_ascii=True).encode())

    def remove(self):
        self.path.unlink(missing_ok=True)

    @staticmethod
    def read(path):
        from .model import MAX_PROJECT_BYTES
        path = Path(path)
        if path.stat().st_size > MAX_PROJECT_BYTES: raise ProjectError('Recovery file exceeds the project limit')
        try:
            record = json.loads(path.read_text(encoding='utf-8'))
            return project_from_record(record['project']), record.get('source')
        except (KeyError, ValueError, TypeError) as error:
            raise ProjectError(f'Invalid recovery document: {error}') from error
