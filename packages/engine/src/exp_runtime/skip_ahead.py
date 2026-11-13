"""Skip Ahead (shshd-runtime; owner, 2026-11-04): go straight to the next thing that needs the player.

An all-games version of SHS '11's hidden code 4687 (reference/Other Games/docs/SHS_11_JAVA_ENGINE.md), which makes its
interpreter skip the text and the wait of its text services while the script carries on. Here the script also carries on
as ever: each screen is answered as a tap would, with its clocks run out, so portraits, backgrounds, flags, the tree and the
wall all happen as they do in play.

It stops at whatever isn't in PASSES: choices, name entry, the look picker, quizzes, mini-games, the arena, a service with
no handler (these stay explicit stops), and also the next title card, unless that's where it started. It doesn't pass the
end: when nothing is left to stop at, it holds on the story's last line, so a skip can't finish an episode by accident.
Knowing that takes a look ahead, so it first walks a throwaway copy (as choice_hints previews a branch), then walks the
session itself by as many screens.

Everything is skipped, read or not. Skipping only what the player has already seen is a possible later addition: the tree
only tracks scenes, so it would need its own record of lines.
"""
from copy import deepcopy

from .engine import POLL_WAIT_MS
from .vm import VMError

PASSES = frozenset(('dialogue', 'vm_pause', 'message_panel', 'survey_confirmation', 'cutscene', 'loading', 'download_poll'))
TITLE_CARD = 'presentation'
TEXT = ('dialogue', 'message_panel')    # where a skip may hold, at the story's end
ENDS = ('episode_exit', 'finished')
PANEL_MS = 4000                         # more than a message panel or title card takes to be ready
LETTERS_MS = 2000
MOST_SCREENS = 30000                    # a script that never waits on the player: stop rather than hang
MOST_TRIES = 64                         # one screen that doesn't go away, or one transition that doesn't end


def can_skip(session):
    """Whether what's up now is something a skip can go past."""
    action = session.pending
    if action is None or session.episode_exited:
        return False
    return action.name in PASSES or action.name == TITLE_CARD


def _settle(session):
    """Run out a scene transition, which holds everything else. False if it wouldn't end."""
    for _ in range(MOST_TRIES):
        if not session.transitioning:
            return True
        session.tick(session.engine.scene_transition.duration_ms)
    return False


def _pass_screen(session):
    """One step past the screen that's up, as a tap and the time it waits for would do."""
    action = session.pending
    kind = action.name
    if kind == 'dialogue':
        animation = session.engine.dialogue_animation
        if animation is not None and not animation.complete:
            session.answer()                    # a tap shows the rest of the letters
            if session.pending is action and not animation.complete:
                session.tick(LETTERS_MS)
        session.answer()
    elif kind == 'vm_pause':
        session.answer()
    elif kind in ('message_panel', 'survey_confirmation', TITLE_CARD):
        session.tick(PANEL_MS)
        if session.pending is action:
            session.answer()
    elif kind == 'cutscene':
        session.answer()                        # a press jumps it on; another ends it, once it's at its hold
    elif kind == 'download_poll':
        session.tick(POLL_WAIT_MS)
    elif kind == 'loading':
        session.tick(PANEL_MS)


class _Walk:
    def __init__(self):
        self.passed = 0                 # screens passed
        self.last_text = 0              # screens passed before the last line of text met
        self.stop = None                # what it stopped at

    def run(self, session, limit):
        tries, shown = 0, None
        while True:
            if not _settle(session):
                self.stop = 'transition'
                return
            action = session.pending
            kind = action.name if action is not None else None
            if self.passed >= limit or (kind not in PASSES and not (kind == TITLE_CARD and self.passed == 0)):
                self.stop = kind
                return
            marker = id(action), session.vm.steps_executed, action.details.get('page_end')
            tries = tries + 1 if marker == shown else 0
            shown = marker
            if tries >= MOST_TRIES:
                self.stop = 'stuck'
                return
            if tries == 0 and kind in TEXT:
                self.last_text = self.passed
            _pass_screen(session)
            self.passed += 1


def skip_ahead(session):
    """Go to the next stop. False if there's nowhere to go: this is the story's last line, or a stop already."""
    if not can_skip(session):
        return False
    probe = deepcopy(session, {id(session.resources): session.resources, id(session.vm.program): session.vm.program})
    probe.ephemeral, probe.durable = True, False
    ahead = _Walk()
    try:
        ahead.run(probe, MOST_SCREENS)
        hold = ahead.stop in ENDS or ahead.stop is None
    except (VMError, ValueError, OSError):     # (ContentError is a ValueError)
        hold = True                     # the story fails ahead: don't rush at it; play reports it when it gets there
    target = ahead.last_text if hold else ahead.passed
    if not target:
        return False
    durable, session.durable = session.durable, False           # the tree's saves, written as the script adds scenes
    try:
        _Walk().run(session, target)
    finally:
        session.durable = durable
    session.take_vibrations()                                   # nothing buzzes for what was skipped
    return True
