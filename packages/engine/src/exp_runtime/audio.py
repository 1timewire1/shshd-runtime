"""Music playback routing, separate from exact script resource lookups."""
from dataclasses import dataclass


@dataclass(frozen=True)
class MusicCue:
    asset_id: int
    start_ms: int = 0


def music_cue(resource_id: int, *, game: str = 'shs') -> MusicCue:
    from .games import GAMES
    return GAMES[game].MUSIC_CUE(resource_id)
