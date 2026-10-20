"""Music playback routing, separate from exact script resource lookups."""
from dataclasses import dataclass


@dataclass(frozen=True)
class MusicCue:
    asset_id: int
    start_ms: int = 0


def music_cue(resource_id: int, *, game: str = 'shs') -> MusicCue:
    from .games import GAMES
    return GAMES[game].MUSIC_CUE(resource_id)


# MPEG audio frame tables (ISO 11172-3 / 13818-3), layer III: kbit/s per bitrate index and Hz per sample-rate index.
_BITRATES = {1: (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320),
             2: (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160)}
_RATES = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000), 0: (11025, 12000, 8000)}


def mp3_length_ms(data: bytes) -> int | None:
    """The playing time of an MP3 (layer III) in ms, from its frame headers, or None if it is not one. A looping cue
    starts again from the file's beginning, so this is where a stored music position wraps (music_stream.py)."""
    i, samples, rate = 0, 0, None
    if data[:3] == b'ID3' and len(data) >= 10:
        i = 10 + ((data[6] & 0x7f) << 21 | (data[7] & 0x7f) << 14 | (data[8] & 0x7f) << 7 | data[9] & 0x7f)
    while i + 4 <= len(data):
        b1, b2 = data[i + 1], data[i + 2]
        version, layer = b1 >> 3 & 3, b1 >> 1 & 3
        if data[i] != 0xff or b1 & 0xe0 != 0xe0 or version == 1 or layer != 1 or b2 >> 4 in (0, 15) or b2 >> 2 & 3 == 3:
            i += 1                       # not a layer III frame header: resynchronise
            continue
        rate = _RATES[version][b2 >> 2 & 3]
        mpeg1 = version == 3
        bitrate = _BITRATES[1 if mpeg1 else 2][b2 >> 4] * 1000
        size = (144 if mpeg1 else 72) * bitrate // rate + (b2 >> 1 & 1)
        samples += 1152 if mpeg1 else 576
        i += max(size, 1)
    return None if rate is None else samples * 1000 // rate
