"""shshd-runtime: what a project takes from addons (docs/ADDONS.md), and what happens to that when it goes to an original app.

An asset can name an addon instead of holding its bytes: it keeps the addon's resource ID, and the export declares the addon (resource 4).
The original apps can't read addons, so for them (owner, 2026-11-02): a project that only takes pictures and sounds can have those packed
into its `.exp`, and one using this runtime's own mechanics can't go at all.
"""
from copy import deepcopy

from .model import Asset, ProjectError, is_audio, is_image

# Node kinds only this runtime answers, and how to name them to a person.
MECHANIC_NODES = {'minigames_available': 'the translated mini-games', 'x360_slot': 'the X360 slot machine',
                  'x360_leash': 'the X360 leash game', 'x360_puzzle': 'the X360 jewel puzzle',
                  'x360_diss': 'X360 Diss Practice', 'cutscene_available': 'storyboard cutscenes',
                  'cutscene': 'storyboard cutscenes'}
# In an imported episode's scripts: New Rules' arena and the X360 games (ENGINE_ABI.md 5.1, 5.2) and cutscenes (5.3).
MECHANIC_SERVICES = ((range(200, 214), "New Rules' minigame arena"), (range(214, 218), 'the X360 mini-games'),
                     (range(218, 219), 'storyboard cutscenes'))


class AddonsNeeded(ProjectError):
    """Going to an original app with addon assets that can be packed in: `names` says which addons. Blocked, with the offer."""

    def __init__(self, names):
        self.names = names
        listed = ' and '.join(names)
        super().__init__(f'This episode takes pictures or sounds from {listed}. The original apps can\'t read add-ons, so it can\'t '
                         'go as it is, but they can be packed into the .exp.')


def mechanics(project):
    """What the project uses that only this runtime has, as a sorted list of names; empty if nothing."""
    found = {MECHANIC_NODES[node.kind] for node in project.nodes if node.kind in MECHANIC_NODES}
    for node in project.nodes:
        if node.kind == 'native':
            for opcode, operand in node.params.get('instructions', ()):
                if opcode == 0x1f:
                    found.update(name for services, name in MECHANIC_SERVICES if operand >> 8 in services)
    return sorted(found)


def check_native_export(project):
    """Raises ProjectError if the project can't go to an original app at all, with why; AddonsNeeded if it can once packed."""
    used = mechanics(project)
    if used:
        raise ProjectError(f'This episode can\'t be exported for an original app, because it uses {" and ".join(used)}. Only SHSHD '
                           'Runtime has that: the original apps would stop or skip it, and packing can\'t bring it along.')
    if project.addons and project.native:
        raise ProjectError('This imported episode needs add-ons, and which of their resources its scripts read can\'t be told, so '
                           'they can\'t be packed in. It can\'t be exported for an original app.')
    if project.addons:
        raise AddonsNeeded([entry['id'] for entry in project.addons])


def pack_addons(project, library):
    """A copy of the project holding its addon assets itself, and needing no addon. Only pictures and sounds translate back."""
    packed = deepcopy(project)
    for asset in packed.assets:
        if not asset.addon:
            continue
        found = library.addon(asset.addon)
        if found is None:
            raise ProjectError(f'Packing needs the {asset.addon} add-on: import it into the library first.')
        record, archive = found
        wanted = next((entry['revision'] for entry in project.addons if entry['id'] == asset.addon), 1)
        if record['revision'] < wanted:
            raise ProjectError(f'Packing needs revision {wanted} of the {asset.addon} add-on; the library has {record["revision"]}.')
        if asset.id not in archive.entries:
            raise ProjectError(f'The {asset.addon} add-on has no resource {asset.id}.')
        data = archive.read(asset.id)
        if not is_image(data) and not is_audio(data):
            raise ProjectError(f'{asset.name} from {asset.addon} is neither a picture nor a sound, so it can\'t be packed in.')
        asset.data, asset.addon = data, ''
    packed.addons = []
    return packed


def require_addon(project, addon_id, revision):
    """The project declares the addon, at least at this revision."""
    for entry in project.addons:
        if entry['id'] == addon_id:
            entry['revision'] = max(entry['revision'], revision)
            return
    project.addons.append(dict(id=addon_id, revision=revision))


def drop_unused_addons(project):
    """No asset takes from it any more: the project doesn't need it. An imported episode's list stays as its scripts need it."""
    if not project.native:
        used = {asset.addon for asset in project.assets if asset.addon}
        project.addons = [entry for entry in project.addons if entry['id'] in used]


def use_addon_asset(project, library, addon_id, resource):
    """Take a picture, sound or cutscene spec from an addon by reference: it keeps its ID, and the project declares the addon at the
    library's revision. Returns the asset."""
    from exp_runtime.cutscene_spec import read_spec
    found = library.addon(addon_id)
    if found is None:
        raise ProjectError(f'The library has no {addon_id} add-on.')
    record, archive = found
    if library.game_id != project.game:
        raise ProjectError('The library must match the project game')
    if not 26000 <= resource <= 32767 or resource not in archive.entries:
        raise ProjectError(f'The {addon_id} add-on has no episode resource {resource}.')
    data = archive.read(resource)
    if not is_image(data) and not is_audio(data):
        try:
            read_spec(data)
        except ValueError:
            raise ProjectError(f'Resource {resource} is neither a picture, a sound nor a cutscene.') from None
    existing = next((asset for asset in project.assets if asset.id == resource), None)
    if existing is not None:
        if existing.addon != addon_id:
            raise ProjectError(f'The project already holds its own resource {resource}. Copy this one in instead.')
        return existing
    asset = Asset(resource, f'{record["title"]} {resource}', None, addon_id)
    project.assets.append(asset)
    require_addon(project, addon_id, record['revision'])
    return asset


def copy_addon_asset(project, library, addon_id, resource):
    """Embed a picture or sound from an addon at a free ID of the project's own, so that it needs no addon."""
    found = library.addon(addon_id)
    if found is None:
        raise ProjectError(f'The library has no {addon_id} add-on.')
    record, archive = found
    if resource not in archive.entries:
        raise ProjectError(f'The {addon_id} add-on has no resource {resource}.')
    data = archive.read(resource)
    name = f'{record["title"]} {resource}'
    if is_audio(data):
        return project.add_audio(name, data)
    if is_image(data):
        return project.add_image(name, data)
    raise ProjectError(f'Resource {resource} is neither a picture nor a sound, so it can\'t be copied in.')
