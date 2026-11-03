"""Build p4a's included Android helpers with its prepared Cython environment.

The pinned toolchain's helper has setup.py but no pyproject build requirements;
an isolated PEP 517 environment therefore omits Cython, which setup.py imports.
Keep its source/configuration intact and use its explicit host prerequisites.
"""
from pathlib import Path
from pythonforandroid.recipes import android as upstream


class AndroidRecipe(upstream.AndroidRecipe):
    name = 'android'
    extra_build_args = ['--no-isolation']

    def get_recipe_dir(self):
        return str(Path(upstream.__file__).parent)


recipe = AndroidRecipe()
