"""shshd-runtime: the X360 minigames' service numbers, and the service 70 selector that says they are available
(docs/X360.md). Here since the creator compiles calls to them without the engine.
"""
X360_MINIGAMES_QUERY = 201
X360_SLOT = 214
X360_LEASH = 215
X360_PUZZLE = 216
X360_DISS = 217
X360_BATTLE = 222       # the Monday Planner's real Diss Battle (x360_battle.py; owner, 2026-11-16)
X360_BATTLE_QUERY = 205         # service 70: whether it plays here (the minigames switch, on a player that has it)
