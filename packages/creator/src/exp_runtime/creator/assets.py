"""Read-only access to a user's already imported game library."""
from io import BytesIO

from .model import Asset, ProjectError


def player_library(game):
    """Find a usable library through the player's remembered/default location."""
    from exp_runtime.content import ContentError, ContentLibrary
    from exp_runtime.launcher import default_library
    try:
        path = default_library(game)
        with ContentLibrary(path) as library:
            if library.game_id == game:
                return str(path.resolve())
    except (ContentError, OSError):
        pass
    return ''


def image_png(data: bytes) -> bytes:
    """Decode a single original image for the browser or an embedded copy."""
    from PIL import Image
    from exp_runtime.ui_assets import ImagePack
    if data.startswith((b'\x89PNG', b'\xff\xd8')):
        with Image.open(BytesIO(data)) as image:
            image.load()
            image = image.convert('RGBA')
    else:
        pack = ImagePack.parse(data)
        if len(pack.images) != 1 or pack.images[0].mode != 'RGBA':
            raise ProjectError('Select a single portrait or background, not a UI atlas')
        frame = pack.images[0]
        image = Image.frombytes('RGBA', (frame.width, frame.height), frame.pixels)
    output = BytesIO()
    image.save(output, format='PNG')
    return output.getvalue()


def addon_asset_ids(library, addon_id):
    """The episode-bank resources an addon holds, for browsing."""
    return sorted(key for key in library.addon(addon_id)[1].entries if 26000 <= key <= 32767)


SKIES = ('day', 'night', 'sunset')   # its backgrounds' three skies, BREW's sky modes (tools/translate shw.SKY_STRIPS)
ADDON_ART_SPEC = 26998       # where Surviving Hollywood's add-on keeps what its pictures are (tools/translate shw.SPEC)


def addon_asset_labels(library, addon_id):
    """{resource: what it is} for an add-on whose spec says (Surviving Hollywood's: its portraits by the demo's number, the
    same facing left, its eight silhouettes and its backgrounds; owner, 2026-11-17), {} for any other. The numbers alone say
    nothing, so the character art picker and MCP name them from it."""
    import json
    found = library.addon(addon_id) if library is not None and hasattr(library, 'addon') else None
    if found is None or ADDON_ART_SPEC not in found[1].entries:
        return {}
    try:
        spec = json.loads(found[1].read(ADDON_ART_SPEC))
    except (ValueError, OSError, KeyError):
        return {}
    if isinstance(spec, dict) and isinstance(spec.get('looks'), list) and isinstance(spec.get('scenes'), dict):
        return claire_hart_labels(spec)
    if not isinstance(spec, dict) or not isinstance(spec.get('portraits'), dict):
        return {}
    labels = {}
    for number, resource in spec.get('portraits', {}).items():
        labels[resource] = f'portrait {number}'
    for number, resource in spec.get('flipped', {}).items():
        labels[resource] = f'portrait {number}, facing left'
    for k, resource in enumerate(spec.get('silhouettes', []), 1):
        labels[resource] = f'silhouette {k}'
    for number, resources in spec.get('backgrounds', {}).items():
        for sky, resource in enumerate(resources if isinstance(resources, list) else [resources]):
            labels[resource] = f'background {number}' + (f', {SKIES[sky]}' if isinstance(resources, list) and sky < len(SKIES) else '')
    return {resource: label for resource, label in labels.items() if type(resource) is int}


EXPRESSIONS = ('Normal', 'Angry', 'Happy', 'Sad', 'Surprised')     # a Claire Hart look's five faces, in chc's slot order


def _words(name):
    """A Claire Hart folder or file name spaced at its capitals and digits: 'ClairesOffice' -> 'Claires Office'."""
    import re
    return re.sub(r'(?<=[a-z])(?=[A-Z0-9])|(?<=[0-9])(?=[A-Z])', ' ', name)


def claire_hart_labels(spec):
    """{resource: what it is} from Claire Hart Classic's spec (`chc` 26998; Claire Hart plan Stage 6, owner 2026-11-24): each
    portrait as its look and face ('Aaron Mitchels, Angry'), each scene by its folder, each track and story object by name."""
    labels = {}
    names = spec.get('look_names') if isinstance(spec.get('look_names'), list) else []
    for entry in (spec.get('pictures') or {}).values():
        if isinstance(entry, list) and len(entry) == 3 and all(type(v) is int for v in entry):
            look, slot, resource = entry
            who = names[look] if 0 <= look < len(names) and isinstance(names[look], str) else f'look {look}'
            labels[resource] = f'{who}, {EXPRESSIONS[slot]}' if 0 <= slot < len(EXPRESSIONS) else who
    for folder, entry in (spec.get('scenes') or {}).items():
        if isinstance(entry, list) and entry and type(entry[0]) is int:
            labels[entry[0]] = f'scene {_words(folder)}'
    for track, resource in (spec.get('music') or {}).items():
        if type(resource) is int:
            labels[resource] = f'track {track.replace("_", " ")}'
    for path, resource in (spec.get('story_objects') or {}).items():
        if type(resource) is int:
            stem = path.rsplit('/', 1)[-1]
            labels[resource] = f'story object {stem[:-2] if stem.endswith("so") and len(stem) > 2 else stem}'
    return labels


def import_library_image(project, library, resource, episode=None):
    if library.game_id != project.game:
        raise ProjectError('The library must match the project game')
    if resource < 25000:
        image_png(library.read_asset(resource))  # Reject scripts, fonts and atlases.
        existing = next((asset for asset in project.assets if asset.id == resource), None)
        if existing:
            return existing
        asset = Asset(resource, f'Base image {resource}')
        project.assets.append(asset)
        return asset
    if resource < 26000 or episode is None:
        raise ProjectError('Select an episode image with an ID of 26000 or higher')
    # Copy to a reserved local slot: no dependency on the source episode,
    # and no accidental expression variants from neighboring original IDs.
    png = image_png(episode.read_asset(resource))
    return project.add_image(f'Episode image {resource}', png)
