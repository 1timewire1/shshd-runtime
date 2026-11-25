"""shshd-runtime: Claire Hart Classic's hidden-object round's service number and the service 70 selector that says it can be
played (docs/ENGINE_ABI.md 5.6c; Claire Hart plan Stage 3). Here since the Creator's compiler, the engine and the CoD services
all need them, without each other.
"""
CLAIRE_ROUNDS_QUERY = 207       # service 70: 1 when a round can be played for real (chcrounds, Use Translated Mini-Games)
CLAIRE2_ROUNDS_QUERY = 208      # ...and Secret in the Shadows' (ch2rounds; Claire Hart plan S3)
CLAIRE_ROUND = 226              # play round `key`: its original episode's number x 10 + the round (E018's third: 183)
# A sequel round's key: 20000 + case x 100 + part x 10 + round (to 30,799; Classic's are under 3,000): a signed word, as
# every Creator node's number is.
SHADOWS_KEY_BASE = 20000


def round_key(epid, number):
    """'E018', 3 -> 183."""
    return int(epid.lstrip('Ee')) * 10 + int(number)


def round_of(key):
    """183 -> ('E018', 3)."""
    return f'E{key // 10:03d}', key % 10


def is_shadows_key(key):
    """Whether round `key` is Secret in the Shadows' (ch2rounds) rather than Classic's (chcrounds)."""
    return key >= SHADOWS_KEY_BASE


def shadows_key(case, part, number):
    """31, 4, 5 -> 23145."""
    return SHADOWS_KEY_BASE + case * 100 + part * 10 + number
