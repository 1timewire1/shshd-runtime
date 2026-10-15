"""Public runtime identity, independent of the imported game's version."""
from importlib.metadata import PackageNotFoundError, version


# This fork's repository (owner, 2026-10-15): the Help page's project link and the update check's release source.
PROJECT_REPOSITORY = '1timewire1/shshd-runtime'
PROJECT_URL = f'https://github.com/{PROJECT_REPOSITORY}'
# The program this fork is based on, credited on the About pages (help_text_overrides.py).
UPSTREAM_URL = 'https://github.com/joshrmcdaniel/exp-runtime'
# Whose releases the update check (updates.py) asks about: this fork's own (never upstream's, a different program).
UPDATE_REPOSITORY = PROJECT_REPOSITORY


def runtime_version():
    # A custom install may use the player component without the umbrella. This fork's distributions are named
    # shshd-runtime(-component), never upstream's exp-runtime names, so the two never shadow each other in pip.
    for distribution in ('shshd-runtime', 'shshd-runtime-player'):
        try:
            return version(distribution)
        except PackageNotFoundError:
            pass
    return 'development'
