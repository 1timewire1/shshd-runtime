"""The High School Story ad some later episodes open with (7_7_Gameofcones1, The_Conned_Artist_1/2_Promotion).

Autumn introduces the other game, then a choice offers to go to its App Store page, to see a sneak peek, or to "Play
the Surviving High School episode!" -- which shows a narrator's "And now..." and then the episode: its title card
(The Conned Artist) or a "Previously, on..." recap before it (Game of Cones). The player's `skip_ad_intros` preference
plays the ad headlessly when a new game starts: the dialogue is acknowledged and the play option chosen, exactly as a
player would, through that "And now...", stopping at whatever the episode shows next. Anything unexpected leaves the
episode untouched.
"""
import re

from .runtime import Session

PLAY_EPISODE = re.compile(r'play the surviving high school episode', re.I)
AND_NOW = re.compile(r'\s*and now\.*\s*$', re.I)       # the ad's last screen, after the play option
STEPS = 80                      # screens the ad takes at most (it takes about 6)


def play_option(action):
    """The index of the ad choice's "Play the Surviving High School episode!" option, or None for any other screen."""
    if action is None or action.name != 'choice':
        return None
    details = action.details
    return next((i for i, (text, enabled) in enumerate(zip(details.get('options', ()), details.get('enabled', ())))
                 if enabled and PLAY_EPISODE.search(text)), None)


def has_ad(resources):
    """Whether any of the episode's scripts carries the ad's play option (packed text in the data words)."""
    for program in getattr(resources, 'programs', {}).values():
        data = b''.join(word.to_bytes(2, 'big') for word in program.main_words + program.extra_words)
        if PLAY_EPISODE.search(data.decode('latin-1')):
            return True
    return False


def has_links(resources):
    """Whether any of the episode's scripts holds a link (service 100's App Store and book pages): only these choices
    can open one."""
    for program in getattr(resources, 'programs', {}).values():
        data = b''.join(word.to_bytes(2, 'big') for word in program.main_words + program.extra_words)
        if b'://' in data:
            return True
    return False


def skip_ad_intro(session):
    """`session` (a game just started) with its ad intro played through to the episode's first screen, or the same
    session unchanged when the episode does not open with the ad."""
    if not has_ad(session.resources):
        return session
    if session.pending is None:
        session.advance()
    state = session.snapshot()
    chosen = ended = False
    for _ in range(STEPS):
        action = session.pending
        if action is None:
            break
        if session.transitioning:
            session.tick(100)
            continue
        if chosen and (ended or action.name != 'dialogue' or not AND_NOW.match(action.details.get('text', ''))):
            return session                           # the episode's first screen (its title card or recap)
        if action.name == 'presentation':
            break
        if action.name == 'dialogue':
            ended = chosen                           # the ad's "And now..."
            if not session.engine.dialogue_animation.complete:
                session.answer()                     # the first tap finishes the reveal
                session.tick(2000)
            session.answer()
        elif action.name == 'choice' and not chosen and play_option(action) is not None:
            if not session.choice_ready:
                session.tick(250 - session.engine.choice_ms)   # the menu ignores taps for its first 250 ms
            session.answer(play_option(action))
            chosen = True
        elif action.name == 'loading':
            session.tick(3001)
        else:
            break
    return Session.from_snapshot(session.resources, state)
