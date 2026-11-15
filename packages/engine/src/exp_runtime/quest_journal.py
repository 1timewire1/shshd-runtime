"""shshd-runtime: a translated story's quest journal, which the pause menu shows (owner, 2026-11-14).

Surviving Hollywood keeps a quest journal its player opens with key 1 or from the pause menu ("you can access the quest
journal via the pause menu at any time"). Its translation (tools/translate/shw_full.py) rebuilds the demo's quest table
whenever the journal changes and keeps it in the session: a global number holding how many quests there are, and each
quest's title and lines as stored texts under keys made from a `%d` form (the game profile's TRANSLATED_JOURNALS, by pack).
This reads them back, so the pause menu can list them; a story without one, or with no quest yet, has none.
"""
from .content import presentation_feature


def quests(session):
    """[(title, lines)] of the open story's journal, its stored texts with their tokens (`$USR`) filled in; [] without one."""
    if session is None:
        return []
    spec = presentation_feature(session.resources, 'journal')
    if spec is None:
        return []
    count_key, title_form, lines_form = spec
    engine = session.engine
    count = engine.numbers.get(engine.number_key(0, count_key), 0)
    out = []
    for n in range(max(0, min(int(count), 64))):
        title = engine.strings.get(title_form % n, '')
        if not title:
            continue
        lines = engine.strings.get(lines_form % n, '')
        out.append((engine.substitute(title), engine.substitute(lines)))
    return out
