"""shshd-runtime: what a project takes from addons (docs/ADDONS.md), and what happens to that when it goes to an original app.

An asset can name an addon instead of holding its bytes: it keeps the addon's resource ID, and the export declares the addon (resource 4).
The original apps can't read addons, so for them (owner, 2026-11-02): a project that only takes pictures and sounds can have those packed
into its `.exp`, and one using this runtime's own mechanics can't go at all.
"""
from copy import deepcopy

from .model import Asset, ProjectError, is_audio, is_image

# The add-on whose mini-game a node plays: the episode needs it, as the primary or an extra (owner, 2026-11-09).
NODE_ADDONS = {'shs11_memory': 'shs11', 'shs11_reflex': 'shs11', 'x360_slot': 'shsx360', 'x360_leash': 'shsx360',
               'x360_puzzle': 'shsx360', 'x360_diss': 'shsx360', 'brew_catch': 'shsbrew'}
# What a primary add-on brings (its settings that need its pictures and sounds; the runtime's ADDON_FEATURE_PACKS) and what any
# declared add-on adds: id -> (brought as the primary, played as an extra too). For the Add-Ons panel.
ADDON_FEATURES = {
    'shsbrew': (("BREW's frame around the scene, pink behind a pink box", "BREW's relationship icons",
                 "BREW's right/wrong music for answer hints", "'08: the Java '08 Look switch; '07: the '08 Backgrounds switch"),
                ('The catch game',)),
    'shs11': (("SHS '11's relationship icons and their sounds", "SHS '11's one sound channel",
               "SHS '11's right/wrong music for answer hints"), ("SHS '11's Memory", "SHS '11's Reflex")),
    'shsnr': (("New Rules' frame around the scene", 'The Hi-Res Portraits switch', "New Rules' right/wrong music for answer hints"),
              ()),
    'shsx360': (("The X360 frame around the scene", 'The MS3 Characters switch'),
                ('The slot machine', 'The leash game', 'The jewel puzzle', 'Diss Practice')),
}
# Node kinds only this runtime answers, and how to name them to a person.
MECHANIC_NODES = {'minigames_available': 'the translated mini-games', 'x360_slot': 'the X360 slot machine',
                  'brew_catch': "the BREW games' catch game",
                  'shs11_memory': "SHS '11's Memory", 'shs11_reflex': "SHS '11's Reflex",
                  'x360_leash': 'the X360 leash game', 'x360_puzzle': 'the X360 jewel puzzle',
                  'x360_diss': 'X360 Diss Practice', 'cutscene_available': 'storyboard cutscenes',
                  'cutscene': 'storyboard cutscenes'}
# In an imported episode's scripts: New Rules' arena and the X360 games (ENGINE_ABI.md 5.1, 5.2), cutscenes (5.3) and
# SHS '11's games (5.4).
MECHANIC_SERVICES = ((range(200, 214), "New Rules' minigame arena"), (range(214, 218), 'the X360 mini-games'),
                     (range(218, 219), 'storyboard cutscenes'), (range(219, 221), "SHS '11's mini-games"),
                     (range(221, 222), "the BREW games' catch game"))


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
    """No asset takes from it any more, it isn't the primary and no node plays its mini-game: the project doesn't need it. An
    imported episode's list stays as its scripts need it."""
    if not project.native:
        used = ({asset.addon for asset in project.assets if asset.addon}
                | {NODE_ADDONS[node.kind] for node in project.nodes if node.kind in NODE_ADDONS})
        project.addons = [entry for entry in project.addons if entry['id'] in used or entry.get('primary')]


def set_primary_addon(project, library, addon_id, edition=''):
    """Make an add-on the project's primary (declaring it at the library's revision if it isn't yet), with its edition (BREW: '08
    or '07); any other primary becomes an extra. None for `addon_id` leaves the project with no primary. The primary is listed
    first: where add-ons share a number, an episode reads the first's."""
    from .model import ADDON_EDITIONS
    found = None
    if addon_id is not None:                    # (checked first: a refused change leaves the project as it was)
        editions = ADDON_EDITIONS.get(addon_id, ('',))
        if edition not in editions:
            raise ProjectError(f'Choose the {addon_id} add-on\'s edition: {" or ".join(e for e in editions)}')
        found = library.addon(addon_id) if library is not None else None
        if found is None and not any(entry['id'] == addon_id for entry in project.addons):
            raise ProjectError(f'The library has no {addon_id} add-on.')
    for entry in project.addons:
        entry.pop('primary', None)
        entry.pop('edition', None)
    if addon_id is None:
        return
    if found is not None:
        require_addon(project, addon_id, found[0]['revision'])
    entry = next(entry for entry in project.addons if entry['id'] == addon_id)
    entry['primary'], entry['edition'] = True, edition
    project.addons.remove(entry)
    project.addons.insert(0, entry)


def require_node_addon(project, library, kind):
    """A node playing an add-on's mini-game was added: the project declares that add-on (an extra unless it's the primary)."""
    addon_id = NODE_ADDONS.get(kind)
    if addon_id is None or any(entry['id'] == addon_id for entry in project.addons):
        return
    found = library.addon(addon_id) if library is not None else None
    if found is None:
        raise ProjectError(f'This needs the {addon_id} add-on: import it into the library first.')
    require_addon(project, addon_id, found[0]['revision'])


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
            holder = f'from the {existing.addon} add-on' if existing.addon else 'of its own'
            raise ProjectError(f'The project already takes resource {resource} {holder}. Copy this one in instead.')
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
