"""Marker for saved dataclasses owned by an installed game adapter.

The selected profile supplies concrete types for these fields. Saves never
choose a Python class or module, and unsupported fields accept only None.
"""


class GameState:
    pass
