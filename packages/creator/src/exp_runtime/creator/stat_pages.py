"""shshd-runtime: the Message node's "Stat changes" preset, as Surviving Hollywood's translation shows a change in its stats
(tools/translate/shw_full.py stat_page): a page titled `Stat changes`, a line each, `Looks: +3` with a + before a rise
(owner, 2026-11-17; CREATOR_CATCHUP_PLAN.md Stage 2)."""

TITLE = 'Stat changes'


def stat_changes_page(lines, signed=True):
    """(title, text) of the page for [(label, owner-0 property key)]: each line formats the property as it stands when the
    page shows, `{+prop(0, key)}` signing a rise."""
    sign = '+' if signed else ''
    return TITLE, '\n'.join(f'{label}: {{{sign}prop(0, {key})}}' for label, key in lines)
