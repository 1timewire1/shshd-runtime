"""CoD SHSSoundManager::playMusic (0004313c): each ID is its own source."""
from ..audio import MusicCue


def music_cue(resource_id):
    return MusicCue(resource_id)
