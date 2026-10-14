"""Public runtime identity, independent of the imported game's version."""
from importlib.metadata import PackageNotFoundError, version


PROJECT_REPOSITORY = 'joshrmcdaniel/exp-runtime'
PROJECT_URL = f'https://github.com/{PROJECT_REPOSITORY}'


def runtime_version():
    # A custom install may use the player component without the umbrella.
    for distribution in ('exp-runtime', 'exp-runtime-player'):
        try:
            return version(distribution)
        except PackageNotFoundError:
            pass
    return 'development'
