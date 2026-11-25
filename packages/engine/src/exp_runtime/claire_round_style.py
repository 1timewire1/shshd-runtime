"""shshd-runtime: which rules a Claire Hart round plays under (Round Style; reference/Other Games/docs/
CLAIRE_HART_SHADOWS_ROUNDS_PLAN.md, owner's idea 2026-11-24). Service 226 names a round by its key; the round source
(runtime.claire_round_source) gives its scene from the add-on the key belongs to (Classic's `chcrounds`, the sequel's
`ch2rounds`), and the Round Style setting picks the rules and so the screen: Each Game's Own (the scene's own game), Claire
Hart Classic (claire_rounds.ClaireRound) or Secret in the Shadows (shadows_rounds.ShadowsRound).

Under Classic's rules a sequel scene offers only its ordinary objects (Classic's screen can't show close-ups, multi-part
objects or the Gold Key); under the sequel's a Classic scene's objects are all ordinary, so the sequel's extras never occur.
"""
from dataclasses import dataclass, field

from .claire_rounds import ClaireRound
from .shadows_rounds import ORDINARY, ShadowsRound

OWN, CLASSIC, SHADOWS = 'own', 'classic', 'shadows'
ROUND_STYLES = (OWN, CLASSIC, SHADOWS)


@dataclass
class RoundData:
    """A round as its add-on describes it: the scene, its objects' names and kinds (shadows_rounds.KINDS), a multi-part
    object's parts, the story objects forced in, the scene's name for Classic's plate, and whether it's a spotlight round."""
    addon: str
    scene: str
    names: list
    story: list
    title: str = ''
    kinds: list = None
    parts: dict = field(default_factory=dict)
    spotlight: bool = False

    def __post_init__(self):
        if self.kinds is None:
            self.kinds = [ORDINARY] * len(self.names)


def round_data(found):
    """The round source's answer as RoundData: a Classic source may answer (scene, names, story, title)."""
    if isinstance(found, RoundData):
        return found
    scene, names, story, title = found
    return RoundData('chcrounds', scene, list(names), list(story), title)


def sequel_rules(data, style):
    return style == SHADOWS or (style != CLASSIC and data.addon == 'ch2rounds')


def open_round(found, random, powerups, style=OWN):
    """The round for service 226 under Round Style `style`."""
    data = round_data(found)
    if sequel_rules(data, style):
        return ShadowsRound.opened(data.scene, data.names, data.kinds, data.parts, data.story, random, powerups,
                                   data.title, data.spotlight, source=data.addon)
    pool = None if all(k == ORDINARY for k in data.kinds) else [i for i, k in enumerate(data.kinds) if k == ORDINARY]
    game = ClaireRound.opened(data.scene, data.names, data.story, random, powerups, data.title, pool=pool)
    game.source = data.addon
    return game
