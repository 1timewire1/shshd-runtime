"""shshd-runtime: authoring storyboard cutscenes (exp_runtime.cutscene_spec holds the format): the Creator's timeline editor and its MCP tool work
on a spec as a plain dict, kept as an embedded asset of the project."""
import json

from exp_runtime.cutscene_spec import FORMAT, VERSION, read_spec

from .model import ProjectError

FRAME = [768, 1024]                     # the frame the SHS player draws them on


def blank_spec():
    return dict(format=FORMAT, version=VERSION, size=list(FRAME), hold=0, skip=0, shots=[], overlays=[], sounds=[])


def blank_shot(start=0):
    return {'image': 0, 'start': start, 'end': start, 'from': [0, 0, *FRAME], 'to': [0, 0, *FRAME]}


def blank_overlay(start=0):
    return {'image': 0, 'start': start, 'end': start, 'from': [FRAME[0] // 2, FRAME[1] // 2, 100, 100],
            'to': [FRAME[0] // 2, FRAME[1] // 2, 100, 100]}


def spec_bytes(spec):
    """The spec's resource bytes, checked."""
    data = json.dumps(spec, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    try:
        read_spec(data)
    except ValueError as error:
        raise ProjectError(str(error)) from error
    return data


def read_project_spec(asset):
    """An embedded cutscene asset's spec as a dict, or None for anything else."""
    if asset.data is None:
        return None
    try:
        return read_spec(asset.data)
    except ValueError:
        return None


def cutscene_assets(project):
    """The assets a cutscene node can choose: the project's own specs, and what it takes from addons (only the library can say which
    of those are specs; the compile and the player check)."""
    return [asset for asset in project.assets if asset.addon or read_project_spec(asset) is not None]


def unknown_resources(project, spec):
    """What the spec draws or plays that isn't in the project, sorted."""
    held = {asset.id for asset in project.assets}
    used = {item['image'] for item in spec.get('shots', []) + spec.get('overlays', [])} | {item['sound'] for item in spec.get('sounds', [])}
    return sorted(used - held)


def save_cutscene(project, name, spec, resource=None):
    """Embed a spec in the project, replacing the asset `resource` if given. Returns the asset."""
    data = spec_bytes(spec)
    unknown = unknown_resources(project, spec)
    if unknown:
        raise ProjectError(f'The cutscene uses resource {unknown[0]}, which isn\'t in the project.')
    if resource is None:
        return project.add_cutscene(name, data)
    asset = next((asset for asset in project.assets if asset.id == resource), None)
    if asset is None or read_project_spec(asset) is None:
        raise ProjectError(f'Resource {resource} isn\'t one of the project\'s cutscenes.')
    asset.name, asset.data = name, data
    return asset
