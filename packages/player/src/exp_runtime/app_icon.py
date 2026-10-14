"""The authored app logo, independent of player-supplied game artwork."""
from functools import lru_cache
from importlib.resources import files
from io import BytesIO

from . import graphics as pygame


@lru_cache(maxsize=8)
def icon_surface(size=128):
    data = files('exp_runtime').joinpath('assets/kiwi.svg').read_bytes()
    return pygame.image.load_sized_svg(BytesIO(data), (size, size))
