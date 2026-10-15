"""Run an exported episode with the production player and isolated saves."""
from contextlib import contextmanager
from copy import copy
from pathlib import Path
import tempfile

from exp_runtime.content import ContentLibrary, EpisodeResources, digest
from exp_runtime.exp import ExpArchive
from .model import ProjectError


@contextmanager
def preview_resources(data, library_path, game):
    archive = ExpArchive(data)
    meta = archive.metadata()
    with ContentLibrary(Path(library_path)) as library:
        if library.game_id != game:
            raise ProjectError('Preview library does not match the project game')
        with tempfile.TemporaryDirectory(prefix='exp-creator-preview-') as temporary:
            isolated = copy(library)
            isolated.directory = Path(temporary)
            record = dict(id=digest(data), sha256=digest(data), name=meta.title + '.exp',
                          titles=list(meta.titles), pack_id=meta.pack_id, episode_id=meta.episode_id)
            yield EpisodeResources(isolated, record, archive)


def play_preview(path, library_path, game):
    from exp_runtime.desktop import play
    with preview_resources(Path(path).read_bytes(), library_path, game) as resources:
        play(resources)
