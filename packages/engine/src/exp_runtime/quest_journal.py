"""shshd-runtime: a translated story's quest journal, which the pause menu shows (owner, 2026-11-14).

Surviving Hollywood keeps a quest journal its player opens with key 1 or from the pause menu ("you can access the quest
journal via the pause menu at any time"). Its translation (tools/translate/shw_full.py) rebuilds the demo's quest table
whenever the journal changes and keeps it in the session: a global number holding how many quests there are, and each
quest's title and lines as stored texts under keys made from a `%d` form (the game profile's TRANSLATED_JOURNALS, by pack).
A journal can also name stats, global numbers it shows first as they stand (Money, Looks, Body, Stress; owner, 2026-11-14).
This reads them back, so the pause menu can list them; a story without one, or with no quest yet, has none.
"""
from .content import presentation_feature

STATS_TITLE = 'Stats'


def _spec(session):
    if session is None:
        return None
    return presentation_feature(session.resources, 'journal')


def quests(session):
    """[(title, lines)] of the open story's journal, its stored texts with their tokens (`$USR`) filled in; [] without one."""
    spec = _spec(session)
    if spec is None:
        return []
    count_key, title_form, lines_form = spec[:3]
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


def stats(session):
    """The journal's stats as a page's text, `Money: $55` a line each (16-bit, as the story keeps them), or None without."""
    spec = _spec(session)
    if spec is None or len(spec) < 4 or not spec[3]:
        return None
    engine = session.engine
    lines = []
    for label, key, prefix in spec[3]:
        value = engine.numbers.get(engine.number_key(0, key), 0) & 0xffff
        value = value - 0x10000 if value & 0x8000 else value
        lines.append(f'{label}: {"-" if value < 0 and prefix else ""}{prefix}{abs(value) if prefix else value}')
    return '\n'.join(lines)
