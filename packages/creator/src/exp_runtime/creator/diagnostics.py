"""Recoverable authoring diagnostics using the same checks as EXP compilation."""
from collections import deque

from .compiler import compile_details, validate_node
from .features import text_fields, parameters
from .graph import edges
from .model import ProjectError, validate_structure


def diagnose(project):
    issues = []
    def issue(code, message, *, node=None, field=None, severity='error', suggestion=''):
        issues.append(dict(code=code, severity=severity, node_id=node, field=field,
                           message=str(message), suggestion=suggestion))
    try: validate_structure(project)
    except ProjectError as error:
        issue('invalid_structure', error, suggestion='Correct the document types and limits before checking execution.')
        return dict(valid=False, issues=issues)
    nodes = {n.id: n for n in project.nodes}
    assets = {a.id: a for a in project.assets}
    characters = {c.id: c for c in project.characters}
    if not project.native:
        if project.start not in nodes:
            issue('missing_start', 'Starting node does not exist', field='start', suggestion='Select an existing node ID.')
        for edge in edges(project):
            if edge['target'] not in nodes:
                issue('missing_target', f'Destination {edge["target"]!r} does not exist', node=edge['source'],
                      field=edge['field'], suggestion='Connect this edge to an existing node.')
        for character in project.characters:
            for field, resource in [('portrait', character.portrait), *[(f'expressions.{i}', v) for i, v in enumerate(character.expressions)]]:
                if resource is not None and resource not in assets:
                    issue('missing_asset', f'Character {character.id} references image {resource}',
                          field=f'characters.{character.id}.{field}', suggestion='Import that image or clear the reference.')
        for node in project.nodes:
            try: validate_node(project, node, nodes, assets, characters)
            except (ProjectError, TypeError, ValueError, KeyError) as error:
                if not any(i['node_id'] == node.id and i['code'] == 'missing_target' for i in issues):
                    field = ('text' if node.kind in ('dialogue', 'choice') and not node.text.strip() else
                             'character' if node.character and node.character not in characters else 'params')
                    issue('invalid_node', error, node=node.id, field=field,
                          suggestion=f'Consult schema_get for the {node.kind} node requirements.')
            from .expressions import parse
            expressions = [(f'options.{i}.condition', o.condition) for i, o in enumerate(node.options)]
            if node.kind in ('set', 'branch'): expressions.append(('params.expression', parameters(node)['expression']))
            for field, expression in expressions:
                if expression:
                    try: parse(expression)
                    except (ProjectError, TypeError, ValueError) as error:
                        issue('invalid_expression', error, node=node.id, field=field,
                              suggestion='Use integers, variable names, arithmetic, comparisons and and/or/not.')
            if node.kind == 'choice' and node.options and all(o.condition for o in node.options):
                issue('conditional_choices', 'Every answer has a condition; some states may offer no enabled answer.',
                      node=node.id, field='options', severity='warning', suggestion='Add an unconditional answer or test all relevant states.')
        try:
            texts = text_fields(project)
            for key, original in texts.items():
                value = project.locales.get(project.language, {}).get(key, original)
                try: value.encode('latin-1')
                except (AttributeError, UnicodeError):
                    node_id = next((n.id for n in project.nodes if key.startswith(f'node.{n.id}.')), None)
                    issue('text_encoding', 'Text cannot be encoded in native Latin-1', node=node_id, field=key,
                          suggestion='Use Latin-1 characters in the selected export language.')
            for language, translations in project.locales.items():
                for key in translations.keys() - texts.keys():
                    issue('unused_translation', f'{language}: unknown translation key', field=key, severity='warning',
                          suggestion='Remove or rename this translation to match a current field key.')
        except (KeyError, TypeError, ValueError):
            pass  # Invalid structured tables already have a node diagnostic.
    reached, queue = set(), deque([project.start])
    while queue:
        key = queue.popleft()
        if key not in nodes or key in reached: continue
        reached.add(key); queue.extend(target for _, target in nodes[key].links())
    if not project.native:
        for key in nodes.keys() - reached:
            issue('unreachable_node', 'No graph path from the starting node', node=key, severity='warning',
                  suggestion='Connect this node or remove it if it is no longer needed.')
    compilation = None
    try: compilation = compile_details(project)
    except (ProjectError, TypeError, ValueError, KeyError) as error:
        if not any(i['severity'] == 'error' for i in issues):
            issue('compile_error', error, suggestion='Correct the compiler error before export; no output was written.')
    result = dict(valid=not any(i['severity'] == 'error' for i in issues), issues=issues,
                  coverage=dict(reachable=len(reached), total=len(nodes), analysis='structural'))
    if compilation: result.update(bytes=len(compilation.data), scripts=sorted(compilation.locations))
    return result
