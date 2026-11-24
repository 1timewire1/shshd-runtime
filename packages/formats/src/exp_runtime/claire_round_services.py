"""shshd-runtime: Claire Hart Classic's hidden-object round's service number and the service 70 selector that says it can be
played (docs/ENGINE_ABI.md 5.6c; Claire Hart plan Stage 3). Here since the Creator's compiler, the engine and the CoD services
all need them, without each other.
"""
CLAIRE_ROUNDS_QUERY = 207       # service 70: 1 when a round can be played for real (chcrounds, Use Translated Mini-Games)
CLAIRE_ROUND = 226              # play round `key`: its original episode's number x 10 + the round (E018's third: 183)


def round_key(epid, number):
    """'E018', 3 -> 183."""
    return int(epid.lstrip('Ee')) * 10 + int(number)


def round_of(key):
    """183 -> ('E018', 3)."""
    return f'E{key // 10:03d}', key % 10
