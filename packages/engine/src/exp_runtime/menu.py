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


MAX_NAMES = 4096               # player.json `names`: far more keys than the whole library writes


class MenuState:
    """Per-library preferences and selection; saves remain content-bound.

    Automatic checkpoints have their own file, preserving the player's F5
    slot. Resume uses the newer of those two saves and validates it on load.
    """
    def __init__(self, library):
        self.library = library
        self.path = library.directory / 'player.json'
        self.music = self.sound = True
        self.vibration = False         # Options' Vibration switch: service 82's buzz (vibration.py); off by default
        # HD's option sliders (0-100; `CSEngine::init` starts both at 50) and its usage-sharing switch.
        self.music_volume = self.sound_volume = 50
        self.logging_disabled = False
        # The story tree's warping: the iOS app locks it until Football Season has been completed once; this player
        # starts it unlocked so scenes can be visited (set false in player.json for the app's behavior).
        self.hd_art = 'fill'           # higher-density art for standard episodes: 'off', 'twins' or 'fill' (hd_twins.py);
                                        # 'fill' is the only one reachable without hand-editing player.json
        self.warp_unlocked = False     # `SHSEngine +0x6490a` (a lock) is set at first run and cleared when Football Season ends
        self.choice_hints = False
        self.skip_minigames = False    # ask whether to play, win or lose each football game / word grid
        self.skip_ad_intros = False    # start the High School Story ad episodes at their title card (ad_intro.py)
        self.hd_backdrop = True        # CoD: SHS HD's faded collage beside the frame, else a dark fill (this player's)
        self.order = 'episode'
        self.title_language = 'en'
        self.selected = None
        # The app's name-replacement table (`SHSEntityTable` renames, kept in shs_options.sav): `$USR`, a series lead's
        # `$ZOE` / `$Scott` / `$Travis`, `$DATE`... written by the scripts (services 46, 47, 113) and shown wherever text
        # says `$KEY`. One table for the whole library, shared by every episode's session (Session.share_names) and
        # never cleared, so a name typed once is the one later episodes use instead of their defaults.
        self.names = {}
        self.warning = ''
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding='utf-8'))
                if (not isinstance(data, dict) or data.get('version') != 1
                        or type(data.get('music')) is not bool or type(data.get('sound')) is not bool
                        or type(data.get('choice_hints', False)) is not bool
                        or type(data.get('skip_minigames', False)) is not bool
                        or type(data.get('skip_ad_intros', False)) is not bool
                        or not isinstance(data.get('selected'), (str, type(None)))
                        or data.get('order', 'episode') not in ('episode', 'title')
                        or data.get('title_language', 'en') not in TITLE_LANGUAGES):
                    raise ValueError('Invalid player preferences')
                self.music, self.sound, self.selected = data['music'], data['sound'], data['selected']
                self.order = data.get('order', 'episode')
                for key in ('music_volume', 'sound_volume'):
                    if type(data.get(key)) is int and 0 <= data[key] <= 100:
                        setattr(self, key, data[key])
                if type(data.get('logging_disabled')) is bool:
                    self.logging_disabled = data['logging_disabled']
                if type(data.get('warp_unlocked')) is bool:
                    self.warp_unlocked = data['warp_unlocked']
                if type(data.get('vibration')) is bool:
                    self.vibration = data['vibration']
                if type(data.get('hd_backdrop')) is bool:
                    self.hd_backdrop = data['hd_backdrop']
                if data.get('hd_art') in ('off', 'twins', 'fill'):
                    self.hd_art = data['hd_art']
                self.title_language = data.get('title_language', 'en')
                self.choice_hints = data.get('choice_hints', False)
                self.skip_minigames = data.get('skip_minigames', False)
                self.skip_ad_intros = data.get('skip_ad_intros', False)
                names = data.get('names', {})
                if (not isinstance(names, dict) or len(names) > MAX_NAMES
                        or any(not isinstance(k, str) or not isinstance(v, str) or not 0 < len(k) <= 255
                               or len(v) > 32767 for k, v in names.items())):
                    raise ValueError('Invalid saved names')
                self.names.update(names)
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

    def shot_path(self, episode):
        """The saved-game screenshot the HD picker shows for an episode."""
        record = self.library.select(episode)
        return self.library.directory / 'saves' / (record['id'] + '.shs-shot.jpg')

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
        data = dict(version=1, selected=self.selected, music=self.music, sound=self.sound, vibration=self.vibration,
                    order=self.order,
                    music_volume=self.music_volume, sound_volume=self.sound_volume, logging_disabled=self.logging_disabled,
                    warp_unlocked=self.warp_unlocked, hd_art=self.hd_art,
                    title_language=self.title_language, choice_hints=self.choice_hints,
                    skip_minigames=self.skip_minigames, skip_ad_intros=self.skip_ad_intros,
                    hd_backdrop=self.hd_backdrop, names=self.names)      # in the order written: replacement walks the table in that order
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
        if path is None and self.skip_ad_intros:
            from .ad_intro import skip_ad_intro
            session = skip_ad_intro(session)
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
