"""Main-menu contracts and original APK string/glyph resources.

No game artwork, glyphs, or episode metadata are embedded in the engine.
Native evidence and deliberate desktop adaptations: docs/MAIN_MENU.md.
"""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile

from .content import is_bundled
from .languages import TITLE_LANGUAGES, episode_title
from .games import GAMES, game_id
from .launcher import default_library, remember_library
from .runtime import SaveError, Session
from .menu_assets import MenuFont, MenuStrings
from .ui_assets import Rect


EPISODE_HEADER_HEIGHT = 24
EPISODE_ROW_HEIGHT = 42


@dataclass(frozen=True)
class EpisodeSection:
    key: str
    title: str
    episodes: tuple[dict, ...]


def group_episodes(records, catalog, *, mega_label, novel_label, saved_label, saved=()):
    """Native category headers with one consolidated section per category.

    EXP IDs do not determine category names. Keep unidentified loose episodes
    in numeric pack sections until the user supplies their original catalog.
    """
    from .episode_catalog import basename
    groups = {}
    for record in records:
        label = catalog.category(record)
        if label is None and is_bundled(record):
            label = novel_label if basename(record['name']) == 'novel_bonus_content.exp' else mega_label
        key = f'category:{label.casefold()}' if label is not None else f'pack:{record["pack_id"]}'
        label = label if label is not None else f'Pack {record["pack_id"]}'
        if key not in groups:
            groups[key] = (label, [])
        groups[key][1].append(record)
    sections = [EpisodeSection(key, label, tuple(episodes)) for key, (label, episodes) in groups.items()]
    sections.sort(key=lambda section: (
        section.title.casefold() != mega_label.casefold(),
        min((e['pack_id'], e['episode_id']) for e in section.episodes), section.key))
    resumed = tuple(e for e in records if e['id'] in saved)
    if resumed:
        sections.insert(0, EpisodeSection('saved', saved_label, resumed))
    return sections



class MenuState:
    """Per-library preferences and selection; saves remain content-bound.

    Automatic checkpoints have their own file, preserving the player's F5
    slot. Resume uses the newer of those two saves and validates it on load.
    """
    def __init__(self, library):
        self.library = library
        self.path = library.directory / 'player.json'
        self.music = self.sound = True
        self.choice_hints = False
        self.order = 'episode'
        self.title_language = 'en'
        self.selected = None
        self.warning = ''
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding='utf-8'))
                if (not isinstance(data, dict) or data.get('version') != 1
                        or type(data.get('music')) is not bool or type(data.get('sound')) is not bool
                        or type(data.get('choice_hints', False)) is not bool
                        or not isinstance(data.get('selected'), (str, type(None)))
                        or data.get('order', 'episode') not in ('episode', 'title')
                        or data.get('title_language', 'en') not in TITLE_LANGUAGES):
                    raise ValueError('Invalid player preferences')
                self.music, self.sound, self.selected = data['music'], data['sound'], data['selected']
                self.order = data.get('order', 'episode')
                self.title_language = data.get('title_language', 'en')
                self.choice_hints = data.get('choice_hints', False)
            except (ValueError, OSError) as error:
                self.warning = f'Could not read preferences: {error}'
        ids = {e['id'] for e in library.episodes}
        if self.selected not in ids:
            saved = [(self.resume_path(e['id']), e['id']) for e in library.episodes]
            saved = [(p.stat().st_mtime_ns, key) for p, key in saved if p]
            preferred = GAMES[game_id(library)].DEFAULT_EPISODE
            default = next((e for e in library.episodes if (e.get('pack_id'), e.get('episode_id')) == preferred),
                           library.episodes[0])
            self.selected = max(saved)[1] if saved else default['id']

    def title(self, record):
        return episode_title(record, self.title_language)

    def save_path(self, episode, *, automatic=False):
        # Never use an arbitrary selector as part of a host path.
        record = self.library.select(episode)
        suffix = '.shs-auto.json' if automatic else '.shs-save.json'
        return self.library.directory / 'saves' / (record['id'] + suffix)

    def resume_path(self, episode):
        paths = [self.save_path(episode, automatic=auto) for auto in (False, True)]
        path = max((p for p in paths if p.is_file()), key=lambda p: p.stat().st_mtime_ns, default=None)
        if path is not None:
            try:
                if path.stat().st_size > 8 * 1024 * 1024:
                    return path  # Session.load reports the existing size limit.
                saved = json.loads(path.read_text(encoding='utf-8'))
                pending = saved.get('pending') if isinstance(saved, dict) else None
                if isinstance(pending, dict) and pending.get('name') == 'episode_exit':
                    # A validated terminal checkpoint masks older progress.
                    # Keep the manual slot available for an explicit load.
                    session = Session.from_snapshot(self.library.open_episode(episode), saved)
                    if session.episode_exited:
                        return None
            except (SaveError, OSError, ValueError, AttributeError):
                # Invalid saves remain resumable so loading reports the error;
                # a malformed completion marker must not discard progress.
                pass
        return path

    def persist(self):
        data = dict(version=1, selected=self.selected, music=self.music, sound=self.sound,
                    order=self.order, title_language=self.title_language, choice_hints=self.choice_hints)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.library.directory,
                                             prefix='.player-', delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(data, stream)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def session(self, episode, *, resume=True):
        resources = self.library.open_episode(episode)
        path = self.resume_path(episode) if resume else None
        session = Session.load(resources, path) if path else Session(resources)
        self.selected = resources.record['id']
        self.persist()
        return session

    def checkpoint(self, session):
        path = session.save(self.save_path(session.resources.record['id'], automatic=True))
        self.selected = session.resources.record['id']
        self.persist()
        return path


def main_button_rects(bank):
    """000df488 + 00147df8: native four-item vertical menu, 5px gaps.

    The background is layout 74; live buttons are layout 75 (184x28),
    independently positioned over it. The fourth uses the paid/ad-free width.
    """
    group = bank.rectangle(74, 0)
    button = bank.rectangle(75, 0)
    widths = (button.width, button.width, button.width, 155)
    total_height = button.height * 4 + 15
    top = 480 - (group.height // 2 + 5) - total_height / 2
    travel = int(button.width * 2.6)
    offsets = (-50, -5, 2, -35)
    return tuple(Rect(round(-group.width / 2 - w + offsets[i] + travel - 20 * i - w / 2),
                      round(top + i * (button.height + 5)), w, button.height)
                 for i, w in enumerate(widths))
