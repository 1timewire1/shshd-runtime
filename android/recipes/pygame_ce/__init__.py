"""Use pygame-ce with p4a's SDL2 compiler recipe, retaining its pygame import."""
from pythonforandroid.recipes.pygame import Pygame2Recipe


class PygameCERecipe(Pygame2Recipe):
    name = 'pygame_ce'
    version = '2.5.8'
    url = 'https://github.com/pygame-community/pygame-ce/archive/refs/tags/{version}.tar.gz'
    site_packages_name = 'pygame'
    hostpython_prerequisites = ['setuptools<81', 'Cython>=3.1,<4']


recipe = PygameCERecipe()
