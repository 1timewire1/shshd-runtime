"""Episode preview images for the HD picker.

The HD app ships a 216 x 290 preview for 84 episodes (`preview_<pack>_<episode>.jpg`) and downloaded the rest, so
those are gone. An episode's preview is its title card, which is the first thing it shows, so the missing ones are
rendered here once, while a library is being set up, by running the episode to its title card and photographing that
frame at twice the tile's size. Episodes that open without a title card keep `missingEpisodePreview.jpg`.
"""
import logging
from pathlib import Path
import tempfile

import pygame

from .ad_intro import play_option
from .content import ContentError
from .episode_index import preview_names
from .engine import POLL_WAIT_MS
from .runtime import Session

FRAME = (768, 1024)
SIZE = (432, 580)                 # 2x the picker's 216 x 290 tile
MAX_STEPS = 300
CHOICE_PACE_MS = 300
BUNDLE = 'Payload/Surviving_HS.app/'
MISSING = 'missingEpisodePreview.jpg'
# The content of the `.none` marker an episode without a title card gets. Bumped when `run_to_title_card` learns to get
# past something new, so episodes marked by an older pipeline are tried once more (2: the High School Story ad's choice;
# 3: minigames and paced choices, CoD's Sunset).
MARKER = b'3'


def thumbnail_path(library, record):
    return library.directory / 'thumbs' / f'{record["id"]}.jpg'


def bundled_preview(library, record):
    """The app bundle's own preview for an episode: JPEG bytes, or None."""
    if library.hd_ipa is None:
        return None
    names = getattr(library, '_bundle_names', None)
    if names is None:
        names = library._bundle_names = set(library.hd_ipa.namelist())
    for name in preview_names(record):
        if BUNDLE + name in names:
            return library.hd_ipa.read(BUNDLE + name)
    return None


def missing_preview(library):
    if library.hd_ipa is None:
        return None
    try:
        library.hd_ipa.getinfo(BUNDLE + MISSING)
    except KeyError:
        return None
    return library.hd_ipa.read(BUNDLE + MISSING)


def run_to_title_card(session):
    """Advance an episode to its title card without a player: fixed answers to whatever it asks on the way.
    Returns whether it got there."""
    session.advance()
    for _ in range(MAX_STEPS):
        pending = session.pending
        if pending is None:
            return False
        name = pending.name
        if name == 'presentation':
            return True
        if session.transitioning:
            session.tick(100)
            continue
        if name == 'dialogue':
            if not session.engine.dialogue_animation.complete:
                session.answer()
                session.tick(2000)
            session.answer()
        elif name in ('vm_pause', 'message_panel'):
            session.tick(5000)
            session.answer()
        elif name == 'loading':
            session.tick(3001)
        elif name == 'download_poll':
            session.tick(POLL_WAIT_MS)
        elif name == 'choice':
            # Some episodes ask something before their title card: take the first option on offer -- except the High
            # School Story ad's (ad_intro.py), whose first option ends the script: there, the one that plays the episode.
            # Tapped at a person's pace: CoD's fights (Sunset's "Squeeze!") repeat their choice until their clock runs out,
            # which never happens when every answer comes at once.
            session.tick(CHOICE_PACE_MS)
            if session.pending is not pending:
                continue
            play = play_option(pending)
            session.answer(play if play is not None else
                           next((i for i, ok in enumerate(pending.details['enabled']) if ok), 0))
        elif name in ('word_game', 'word_grid', 'football'):
            session.skip_minigame(True)
        elif name == 'character_picker':
            session.answer(0)
        elif name == 'text_input':
            session.answer('Player')
        else:
            return False
    return False


def capture_title_card(library, record):
    """The episode's title card as a SIZE surface, or None when it has none (or cannot be run)."""
    from .desktop import Desktop
    session = Session(library.open_episode(record['id']), ephemeral=True)
    if not run_to_title_card(session):
        return None
    window = pygame.Surface(FRAME).convert()
    view = Desktop(session, audio=False, window=window, capture=True)
    for _ in range(300):
        view.tick(16)
    if session.engine.title_screen:
        session.engine.title_screen.elapsed_ms = 10000
    view.render()
    if view.error:
        return None
    return pygame.transform.smoothscale(window, SIZE)


def generate(library, record):
    """Render and cache one episode's preview; True when a file was written."""
    path = thumbnail_path(library, record)
    try:
        image = capture_title_card(library, record)
    except (ContentError, pygame.error, OSError, ValueError, KeyError, AttributeError, RecursionError) as error:
        logging.warning('No preview for %s: %s', record['titles'][0], error)
        return False
    if image is None:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.thumb-', suffix='.jpg', delete=False) as stream:
        temporary = Path(stream.name)
    try:
        pygame.image.save(image, str(temporary), 'jpg')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def missing_records(library, records):
    """Episodes with neither a bundled nor a cached preview, and not yet tried (a failed try is remembered)."""
    return [r for r in records
            if not thumbnail_path(library, r).exists() and not marked(thumbnail_path(library, r).with_suffix('.none'))
            and bundled_preview(library, r) is None]


def marked(marker):
    """Whether the current pipeline already found no title card (an older marker is tried again)."""
    try:
        return marker.read_bytes() == MARKER
    except OSError:
        return False


def ensure(library, records, progress=None):
    """Generate every missing preview for `records`; returns how many were made."""
    todo = missing_records(library, records)
    made = 0
    for index, record in enumerate(todo):
        if progress:
            progress(index, len(todo), record['titles'][0])
        if generate(library, record):
            made += 1
        else:
            marker = thumbnail_path(library, record).with_suffix('.none')
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_bytes(MARKER)
    return made
