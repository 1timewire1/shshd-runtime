"""Bounded story queries and reference-aware edits, independent of MCP and Qt."""
from collections import Counter, deque
from dataclasses import asdict

from .model import ProjectError


def page(offset, limit):
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 200:
        raise ProjectError('Use a nonnegative offset and limit from 1 to 200')


def edges(project):
    result = []
    for node in project.nodes:
        for index, (label, target) in enumerate(node.links()):
            field = (f'options.{index}.target' if node.kind == 'choice' else
                     'otherwise' if node.kind in ('branch', 'text_branch') and index else 'next')
            if node.kind == 'native': field = 'params.instructions'
            result.append(dict(source=node.id, target=target, label=label, field=field))
    return result


def overview(project):
    return dict(title=project.title, game=project.game, start=project.start, native=bool(project.native),
                node_count=len(project.nodes), kinds=dict(Counter(n.kind for n in project.nodes)),
                scenes=dict(Counter(n.scene for n in project.nodes)),
                characters=[dict(id=c.id, name=c.name) for c in project.characters],
                asset_count=len(project.assets), language=project.language,
                languages=sorted({project.language, *project.locales}),
                endings=[n.id for n in project.nodes if n.kind == 'end'])


def search(project, *, text='', character=None, kind=None, scene=None, offset=0, limit=50):
    page(offset, limit)
    found = []
    needle = text.casefold()
    for node in project.nodes:
        if character is not None and character not in (node.character, node.params.get('left_character'),
                                                       node.params.get('right_character')): continue
        if kind is not None and node.kind != kind: continue
        if scene is not None and node.scene != scene: continue
        if needle and needle not in str(asdict(node)).casefold(): continue
        found.append(node)
    return dict(total=len(found), nodes=[asdict(n) for n in found[offset:offset + limit]],
                next_offset=offset + limit if offset + limit < len(found) else None)


def subgraph(project, node_id, *, depth=1, direction='both', limit=100):
    page(0, limit)
    if type(depth) is not int or not 0 <= depth <= 20 or direction not in ('both', 'incoming', 'outgoing'):
        raise ProjectError('Use depth 0–20 and direction incoming, outgoing or both')
    nodes = {n.id: n for n in project.nodes}
    if node_id not in nodes: raise ProjectError('Unknown node')
    links = edges(project)
    adjacent = {key: [] for key in nodes}
    for edge in links:
        a, b = edge['source'], edge['target']
        if b not in nodes: continue
        if direction != 'incoming': adjacent[a].append(b)
        if direction != 'outgoing': adjacent[b].append(a)
    queue, visited, selected = deque([(node_id, 0)]), {node_id}, []
    while queue and len(selected) < limit:
        key, level = queue.popleft(); selected.append(key)
        if level < depth:
            for target in adjacent[key]:
                if target not in visited:
                    visited.add(target); queue.append((target, level + 1))
    included = set(selected)
    return dict(nodes=[asdict(nodes[key]) for key in selected], truncated=bool(queue),
                edges=[e for e in links if e['source'] in included and e['target'] in included],
                boundary=[e for e in links if (e['source'] in included) != (e['target'] in included)])


def paths(project, target, *, source=None, limit=20, max_depth=100, budget=10000):
    """Enumerate bounded simple structural paths, not claims of runtime reachability."""
    page(0, limit)
    if type(max_depth) is not int or not 1 <= max_depth <= 500:
        raise ProjectError('Path depth must be 1–500')
    nodes = {n.id: n for n in project.nodes}
    source = source or project.start
    if source not in nodes or target not in nodes: raise ProjectError('Unknown source or target node')
    stack, found, examined, truncated = [(source,)], [], 0, False
    while stack and len(found) < limit and examined < budget:
        route = stack.pop(); examined += 1
        if route[-1] == target:
            found.append(list(route)); continue
        if len(route) >= max_depth:
            truncated |= any(t in nodes and t not in route for _, t in nodes[route[-1]].links())
            continue
        for _, next_id in reversed(nodes[route[-1]].links()):
            if next_id in nodes and next_id not in route: stack.append((*route, next_id))
    return dict(paths=found, truncated=bool(stack) or truncated, examined=examined,
                semantics='Simple structural paths. Conditions, timers and native indirect jumps require playtesting.')


def rename_node(project, old, new):
    if project.native: raise ProjectError('Native blocks retain fixed addresses and identities')
    if not new or any(n.id == new for n in project.nodes): raise ProjectError('Choose a new, nonempty node ID')
    node = next((n for n in project.nodes if n.id == old), None)
    if node is None: raise ProjectError('Unknown node')
    node.id = new
    if project.start == old: project.start = new
    for n in project.nodes:
        if n.next == old: n.next = new
        if n.otherwise == old: n.otherwise = new
        for option in n.options:
            if option.target == old: option.target = new
    prefix = f'node.{old}.'
    for language, translations in project.locales.items():
        project.locales[language] = {(f'node.{new}.' + key[len(prefix):] if key.startswith(prefix) else key): value
                                    for key, value in translations.items()}


def connect(project, source, target, field='next'):
    if project.native: raise ProjectError('Edit native control flow through its instructions')
    node = next((n for n in project.nodes if n.id == source), None)
    if node is None: raise ProjectError('Unknown source node')
    if field not in {e['field'] for e in edges(project) if e['source'] == source}:
        raise ProjectError('Choose an existing edge field: next, otherwise or options.N.target')
    if field.startswith('options.'):
        node.options[int(field.split('.')[1])].target = target
    else:
        setattr(node, field, target)
