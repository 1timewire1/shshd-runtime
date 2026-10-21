"""The authored app logo, independent of player-supplied game artwork, and the window icon."""
from functools import lru_cache
from importlib.resources import files
from io import BytesIO

from . import graphics as pygame


@lru_cache(maxsize=8)
def icon_surface(size=128):
    # Python 3.10 namespace readers resolve only one child per joinpath call.
    data = files('exp_runtime').joinpath('assets').joinpath('kiwi.svg').read_bytes()
    return pygame.image.load_sized_svg(BytesIO(data), (size, size))


def game_icon_surface(library):
    reader = getattr(library, 'app_icon', None)    # authored fixtures may stand in for a ContentLibrary
    image = reader() if reader is not None else None
    if image is None:
        return None
    stream = BytesIO()
    image.convert('RGBA').save(stream, format='PNG')
    stream.seek(0)
    return pygame.image.load(stream)


def set_window_icon(library=None):
    icon = None
    if library is not None:
        try:
            icon = game_icon_surface(library)
        except (OSError, ValueError, pygame.error):
            icon = None
    pygame.display.set_icon(icon if icon is not None else icon_surface())
