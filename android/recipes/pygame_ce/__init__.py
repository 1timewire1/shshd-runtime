"""Use pygame-ce with p4a's SDL2 compiler recipe, retaining its pygame import."""
from pathlib import Path
import re
from pythonforandroid.recipes.pygame import Pygame2Recipe


class PygameCERecipe(Pygame2Recipe):
    name = 'pygame_ce'
    version = '2.5.8'
    url = 'https://github.com/pygame-community/pygame-ce/archive/refs/tags/{version}.tar.gz'
    site_packages_name = 'pygame'
    hostpython_prerequisites = ['setuptools<81', 'Cython>=3.1,<4']

    def prebuild_arch(self, arch):
        super().prebuild_arch(arch)
        setup = Path(self.get_build_dir(arch.arch)) / 'setup.py'
        text = setup.read_text()
        # New setuptools no longer re-exports spawn from ccompiler. Delegate
        # through the original method which pygame saves before its wrapper.
        text = text.replace('distutils.ccompiler.spawn(cmd, dry_run=self.dry_run, **kwargs)',
                            'distutils.ccompiler.CCompiler.__spawn(self, cmd, **kwargs)')
        # The build host is x86-64, but these files are compiled for Android.
        # Never add host AVX2 compiler flags to ARM compilation commands.
        text = text.replace('machine_name = platform.machine()', f'machine_name = {arch.arch!r}')
        setup.write_text(text)
        # p4a precompiles through setup.py. pygame-ce's default Meson backend
        # would start a second native build when pip installs the package.
        project = setup.with_name('pyproject.toml')
        text = project.read_text()
        text, replaced = re.subn(r'(?ms)^\[build-system\]\n.*?(?=^\[|\Z)',
                                '[build-system]\n'
                                'requires = ["setuptools<81", "wheel", "Cython>=3.1,<4"]\n'
                                'build-backend = "setuptools.build_meta"\n\n', text)
        if replaced != 1:
            raise ValueError('pygame-ce build-system declaration has changed')
        project.write_text(text)


recipe = PygameCERecipe()
