"""CoD's queued SHSFadeLayer tracks and delayed UI callback.

GameModel 0000f998/0000ee5c and SHSFadeLayer 00058188..00058e84.
The libc rand stream is independent of SHS's lrand48 and KiWi randomness.

This fork keeps the model in the engine (fade_transition.py), shared with SHS HD, whose GameModel and SHSFadeLayer
are the same code.
"""
from ..fade_transition import FadeTransition as SceneTransition

__all__ = ['SceneTransition']
