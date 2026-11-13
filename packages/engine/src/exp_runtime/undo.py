"""Undo (shshd-runtime; owner, 2026-11-06): Skip Ahead's inverse. Reference: reference/Other Games/docs/UNDO_PLAN.md.

While the player has "Allow Undo" on, the game keeps a save each time the story reaches a point Skip Ahead stops at (a
choice, name entry, the look picker, a quiz, a mini-game or its skip prompt, a title card), taken as it comes up, before
any answer. They form a chain, one file each, beside the episode's autosave. Undo loads the latest: the choice just
answered, the game just lost. Pressed while sitting at that very point, it deletes it and loads the one before (owner).
Either way the chain then ends where it lands, so a new path never meets saves made on the old one. In a mini-game
under way (not at its skip prompt), Undo restarts that game from its own save instead (owner, 2026-11-06: `restart`). The chain is kept
until the episode ends or is started over, and isn't synced or backed up.

A save is the whole game (Session.snapshot), randomness included, so a random pick comes out as it did; the story tree
isn't part of it (as with every save), so scenes already seen stay seen.
"""
from dataclasses import dataclass, field
import gzip
import json
from pathlib import Path
import shutil
import tempfile

from .runtime import SaveError, Session
from .skip_ahead import ENDS, PASSES

SUFFIX = '.shs-undo'
NOT_STOPS = frozenset(('unhandled_yield',))     # an error stop, not a point in the story
MOST_SAVES = 400                                # one episode never has this many stops; past it the oldest go


def is_stop(action):
    """Whether `action` is a point Skip Ahead would stop at (a title card included): one worth a save."""
    return action is not None and action.name not in PASSES and action.name not in ENDS and action.name not in NOT_STOPS


def directory(library_directory, record_id):
    """Where an episode's chain lives: beside its autosave, in the library's `saves`."""
    return Path(library_directory) / 'saves' / (record_id + SUFFIX)


def chain_for(session):
    """The chain of the episode `session` plays, or None for one with no library (a preview, a test's resources)."""
    library = getattr(session.resources, 'library', None)
    record = getattr(session.resources, 'record', None) or {}
    if library is None or getattr(library, 'directory', None) is None or not record.get('id'):
        return None
    return UndoChain(directory(library.directory, record['id']))


def clear(library_directory, record_id):
    """Forget an episode's chain (it ended, or starts over)."""
    shutil.rmtree(directory(library_directory, record_id), ignore_errors=True)


def point(session):
    """What tells one stop from another: the scene, the screen, and where the script is."""
    return [session.scene, session.pending.name if session.pending else None, session.vm.pc, session.vm.steps_executed]


@dataclass
class UndoChain:
    folder: Path
    _known: tuple | None = field(default=None, compare=False, repr=False)    # (numbers, the latest's point), as last read

    def _state(self):
        """The chain's numbers and its latest save's point, read once and kept until the chain changes (the pause menu
        asks every frame)."""
        if self._known is None:
            try:
                numbers = sorted(int(path.name.split('.')[0]) for path in self.folder.glob('*.json.gz'))
            except (OSError, ValueError):
                numbers = []
            latest = None
            if numbers:
                try:
                    latest = self._read(numbers[-1]).get('point')
                except (OSError, ValueError, EOFError):
                    latest = None
            self._known = (numbers, latest)
        return self._known

    def numbers(self):
        return list(self._state()[0])

    def _path(self, number):
        return self.folder / f'{number}.json.gz'

    def _read(self, number):
        with gzip.open(self._path(number), 'rt', encoding='utf-8') as stream:
            return json.load(stream)

    def _latest_point(self):
        return self._state()[1]

    def record(self, session):
        """Keep a save of `session` if it's at a stop the chain doesn't already end on. True if one was written."""
        if session.episode_exited or not is_stop(session.pending) or getattr(session, 'ephemeral', False):
            return False
        here = point(session)
        if self._latest_point() == here:
            return False
        numbers = self.numbers()
        number = numbers[-1] + 1 if numbers else 1
        self.folder.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.folder, prefix='.undo-', delete=False) as raw:
                temporary = Path(raw.name)
                with gzip.GzipFile(fileobj=raw, mode='wb', compresslevel=5) as stream:
                    stream.write(json.dumps(dict(point=here, save=session.snapshot()), ensure_ascii=False,
                                            separators=(',', ':')).encode('utf-8'))
            temporary.replace(self._path(number))
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        dropped = numbers[:max(0, len(numbers) + 1 - MOST_SAVES)]
        for old in dropped:
            self._path(old).unlink(missing_ok=True)
        self._known = ([n for n in numbers if n not in dropped] + [number], here)
        return True

    def at_latest(self, session):
        """Whether the story sits on the chain's latest save now (its point: a game under way is still on it)."""
        return (bool(self.numbers()) and session is not None and session.pending is not None
                and self._latest_point() == point(session))

    def _load(self, session, number):
        try:
            return Session.from_snapshot(session.resources, self._read(number)['save'])
        except (OSError, ValueError, EOFError, KeyError) as error:
            if isinstance(error, SaveError):
                raise
            raise SaveError(f'Cannot undo: {error}') from error

    def restart(self, session):
        """The story back at the latest save, which stays (a mini-game under way starts over), or None if it isn't
        sitting on it."""
        if not self.at_latest(session):
            return None
        return self._load(session, self.numbers()[-1])

    def _target(self, session):
        """The save Undo would load, and the ones it deletes first: the latest, unless the story sits on it now."""
        numbers = self.numbers()
        if self.at_latest(session):
            return (numbers[-2] if len(numbers) > 1 else None), numbers[-1:]
        return (numbers[-1] if numbers else None), []

    def can_undo(self, session):
        return self._target(session)[0] is not None

    def undo(self, session):
        """The session Undo goes to, or None. The save it leaves stays, as the chain's end."""
        target, dropped = self._target(session)
        if target is None:
            return None
        restored = self._load(session, target)
        for number in dropped + [n for n in self.numbers() if n > target]:
            self._path(number).unlink(missing_ok=True)
        self._known = None
        return restored

    def clear(self):
        shutil.rmtree(self.folder, ignore_errors=True)
        self._known = None
