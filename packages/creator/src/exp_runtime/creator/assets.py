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
