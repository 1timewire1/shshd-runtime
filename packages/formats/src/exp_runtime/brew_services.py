"""shshd-runtime: the BREW games' catch game's service number, and the service 70 selector that says it's available
(docs/ENGINE_ABI.md). Here since the translator and the engine both need them, without each other.
"""
BREW_MINIGAMES_QUERY = 204
BREW_CATCH = 221
ANGLED, SIDEWAYS, ORBIT = 1, 2, 3       # the game's three kinds, as the native object's +0x18: BREW's services 20, 21 and 19
