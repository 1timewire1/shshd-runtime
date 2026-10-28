"""One transaction vocabulary shared by workspace edits and MCP schemas."""
from dataclasses import fields

from .model import Character, Choice, Node, ProjectError
from . import graph


def patch_record(record, changes, allowed):
    if not isinstance(changes, dict) or set(changes) - set(allowed):
        raise ProjectError('Unsupported fields: ' + ', '.join(sorted(set(changes) - set(allowed)))
                           if isinstance(changes, dict) else 'Changes must be an object')
    for key, value in changes.items():
        if key == 'options':
            if not isinstance(value, list): raise ProjectError('Options must be a list')
            try: value = [Choice(**option) for option in value]
            except TypeError as error: raise ProjectError(f'Invalid choice: {error}') from error
        setattr(record, key, value)


def apply(workspace, project, operation):
    """Apply to a disposable candidate. The workspace validates and commits once."""
    if not isinstance(operation, dict): raise ProjectError('An edit operation must be an object')
    op = operation.get('op')
    allowed = {
        'project': {'changes'}, 'node': {'id', 'changes', 'remove'},
        'character': {'id', 'changes', 'remove'}, 'rename_node': {'id', 'new_id'},
        'connect': {'source', 'target', 'field'}, 'image': {'source'}, 'audio': {'source'},
        'library_image': {'library', 'resource', 'episode'}, 'asset_label': {'id', 'label'}, 'layout': set(),
    }
    if op not in allowed or set(operation) - {'op'} - allowed[op]:
        raise ProjectError('Unknown edit operation or operation fields')
    if op == 'project':
        changes = dict(operation['changes'])
        if 'game' in changes and changes['game'] != project.game and (project.assets or project.native or project.library):
            raise ProjectError('Create a new project to change the game after importing resources')
        if changes.get('library'): changes['library'] = str(workspace.path(changes['library']))
        patch_record(project, changes, {'title', 'game', 'pack_id', 'episode_id', 'start', 'language', 'locales', 'library',
                                        'emoticons'})
    elif op in ('node', 'character'):
        key = operation['id']
        if not isinstance(key, str) or not key: raise ProjectError('An edit needs a nonempty ID')
        collection = project.nodes if op == 'node' else project.characters
        record = next((r for r in collection if r.id == key), None)
        if project.native and (op == 'character' or record is None or operation.get('remove')):
            raise ProjectError('Native projects retain their original blocks and character definitions')
        if operation.get('remove'):
            if record is None: raise ProjectError(f'Unknown {op}: {key}')
            collection.remove(record)
        else:
            if record is None:
                record = Node(key) if op == 'node' else Character(key)
                collection.append(record)
            patch_record(record, operation.get('changes', {}), {f.name for f in fields(record)} - {'id'})
    elif op == 'rename_node': graph.rename_node(project, operation['id'], operation['new_id'])
    elif op == 'connect': graph.connect(project, operation['source'], operation['target'], operation.get('field', 'next'))
    elif op == 'image':
        from .model import MAX_ASSET_BYTES
        path = workspace.path(operation['source'])
        if path.stat().st_size > MAX_ASSET_BYTES: raise ProjectError('Image is too large')
        project.add_image(path.name, path.read_bytes())
    elif op == 'audio':
        from .model import MAX_ASSET_BYTES
        path = workspace.path(operation['source'])
        if path.stat().st_size > MAX_ASSET_BYTES: raise ProjectError('Audio is too large')
        project.add_audio(path.name, path.read_bytes())
    elif op == 'library_image':
        from exp_runtime.content import ContentLibrary
        from .assets import import_library_image
        with ContentLibrary(workspace.path(operation['library'])) as content:
            episode = operation.get('episode')
            import_library_image(project, content, operation['resource'], content.open_episode(episode) if episode else None)
    elif op == 'asset_label':
        asset = next((a for a in project.assets if a.id == operation['id']), None)
        if asset is None: raise ProjectError('Import the asset into the project before labeling it')
        asset.name = operation['label']
    elif op == 'layout':
        from .editing import auto_layout
        auto_layout(project)


def check_removals(before, after):
    removed = {n.id for n in before.nodes} - {n.id for n in after.nodes}
    references = [e for e in graph.edges(after) if e['target'] in removed]
    if after.start in removed or references:
        raise ProjectError('Removed node is still referenced; reconnect its incoming edges and project start in the same batch')
    removed_characters = {c.id for c in before.characters} - {c.id for c in after.characters}
    def referenced(node):
        keys = [node.character, *(node.params.get(key) for key in ('left_character', 'right_character', 'player', 'narrator',
                                                                    'partner'))]
        looks = node.params.get('characters')
        keys += looks if isinstance(looks, list) else []
        return {key for key in keys if isinstance(key, str) and key}
    if any(referenced(n) & removed_characters for n in after.nodes):
        raise ProjectError('Removed character is still referenced by a node')
