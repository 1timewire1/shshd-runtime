"""python-for-android's Pillow, optimised: its arch flags carry no optimisation level, so Pillow's C was built at -O0
(the HD portraits' resampling and masks, the import's previews and HD art took several times longer on a phone)."""
from pathlib import Path
from pythonforandroid.recipes import Pillow as upstream


class OptimisedPillowRecipe(upstream.PillowRecipe):
    name = 'Pillow'

    def get_recipe_dir(self):
        return str(Path(upstream.__file__).parent)

    def get_recipe_env(self, arch, **kwargs):
        env = super().get_recipe_env(arch, **kwargs)
        env['CFLAGS'] = env.get('CFLAGS', '') + ' -O3 -DNDEBUG'
        return env


recipe = OptimisedPillowRecipe()
