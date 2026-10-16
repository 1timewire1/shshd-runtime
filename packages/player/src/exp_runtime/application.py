"""Shared application lifecycle: import, menu, episode sessions and shutdown.

The executable starts here with no game data. A host supplies graphics/input
primitives; imports run on a worker and publish a validated library atomically.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import logging
import os
from pathlib import Path
import tempfile

os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
from . import graphics as pygame

from .app_icon import icon_surface
from .app_info import PROJECT_URL
from .content import ContentError, ContentLibrary, import_game, is_bundled
from .desktop import Desktop, SIZE
from .desktop_menu import MenuRenderer
from .desktop_transition import draw_transition
from .languages import TITLE_LANGUAGES
from .games import GAMES
from .menu import (EPISODE_HEADER_HEIGHT, EPISODE_ROW_HEIGHT, MenuState,
                   default_library, group_episodes, remember_library)
from .runtime import SaveError, Session
from .settings import AppSettings
from .updates import UpdateCheck
from .pointer import ButtonPress
from .animation_curves import ease_in_out
from .vm import VMError


ERRORS = (ContentError, SaveError, VMError, OSError, ValueError, pygame.error)


class Application:
    def __init__(self, directory=None, *, audio=True, game_key=None, file_picker=None,
                 library_root=None, url_opener=None, settings_path=None,
                 update_fetcher=None, check_updates=True):
        if game_key is not None and game_key not in GAMES:
            GAMES[game_key]  # Explain which optional game component is missing.
        if not GAMES:
            raise ContentError('No game adapters are installed. Install "exp-runtime[shs]", '
                               '"exp-runtime[cod]", or "exp-runtime[player]" for both.')
        default_game = next(iter(GAMES))
        pygame.display.init()
        pygame.font.init()
        pygame.display.set_icon(icon_surface())
        self.window = pygame.display.set_mode(SIZE, pygame.RESIZABLE)
        pygame.display.set_caption('EXP Runtime')
        self.remember_location = directory is None and library_root is None
        self.file_picker = file_picker
        self.url_opener = url_opener
        self.settings = AppSettings(settings_path)
        self.updates = UpdateCheck(update_fetcher)
        self.check_updates = check_updates  # Diagnostics can remain entirely offline.
        self.update_prompt = None
        self.library_path = (default_library if library_root is None else
                             lambda key: Path(library_root) / key)
        self.selected_game = game_key
        self.directory = Path(directory) if directory is not None else self.library_path(game_key or default_game)
        self.library = self.state = self.game = None
        self.processes = {}
        self.renderer = MenuRenderer()
        self.screen = 'games' if directory is None and game_key is None else 'setup'
        self.history = []
        self.message = ''
        self.scope = 'all'
        self.selected = None
        self.saved = set()
        self.query = ''
        self.scroll = 0
        self.episode_scroll = 0
        self.expanded_groups = set()
        self.focus = None
        self.press = ButtonPress()
        self.focus_index = 0
        self.active = True
        self.intro = True
        self.menu_age = 0
        self.transition_age = 200
        self.transition_from = None
        self.transition_layer = None
        self.transition_direction = 1
        self.transition_zoom = False
        self.transition_source = None
        self.main_exit_ms = None
        self.game_entry = None
        self.game_entry_resume = True
        self.buttons = []
        self.viewport = pygame.Rect(0, 0, *SIZE)
        self.browser_kind = None
        self.folder = Path.cwd()
        self.path_text = str(self.folder)
        self.files = []
        self.dropped_files = []
        self.dropping = False
        self.audio = False
        self.menu_music = pygame.create_menu_music()
        self.menu_music_token = None
        self.menu_music_loaded = self.menu_music_paused = False
        self.menu_music_fade_ms = 0
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='exp-content')
        self.job = None
        self.job_kind = None
        if audio:
            try:
                pygame.mixer.init()
                self.audio = True
            except pygame.error as error:
                logging.warning('Audio unavailable: %s', error)
        if self.screen != 'games' and self.directory.exists():
            try:
                self.open_library(self.directory)
            except ERRORS as error:
                self.message = str(error)
        if self.screen == 'setup' and self.selected_game is None:
            self.selected_game = default_game
        if self.check_updates and self.settings.check_for_updates:
            self.updates.start()

    def input_token(self):
        return self.screen, self.message, self.update_prompt

    @property
    def game_title(self):
        return GAMES[self.selected_game].TITLE if self.selected_game else 'EXP Runtime'

    @property
    def pressed(self):
        return self.press.pressed

    def cancel_pointer(self):
        self.press.cancel()
        if self.game:
            self.game.cancel_pointer()

    @property
    def paused_menu(self):
        return bool(self.game and self.game.menu_open and 'game' in self.history)

    def choose_game(self, key):
        if key not in GAMES:
            raise ContentError(f'Unknown game: {key}')
        self.release_library()
        self.selected_game, self.directory = key, self.library_path(key)
        self.renderer = MenuRenderer()
        self.screen, self.history, self.message = 'setup', [], ''
        pygame.display.set_caption(self.game_title)
        if self.directory.exists():
            self.open_library(self.directory)

    def release_library(self, *, checkpoint=True):
        # Do not discard a live session if its checkpoint cannot be written.
        if checkpoint and self.game:
            self.game.capture_audio()
            self.state.checkpoint(self.game.session)
        if self.audio:
            self.menu_music.stop()
            self.menu_music_token = None
            self.menu_music_loaded = self.menu_music_paused = False
            self.menu_music_fade_ms = 0
            pygame.mixer.music.stop()
            pygame.mixer.stop()
            if self.game:
                self.game._stop_sounds()
        if self.library:
            self.library.close()
        self.library = self.state = self.game = None
        self.game_entry = None
        self.saved = set()
        self.selected = None
        if hasattr(self, 'click_sound'):
            del self.click_sound

    def switch_games(self):
        other = next((key for key in GAMES if key != self.selected_game
                      and (self.library_path(key) / 'library.json').is_file()), None)
        if other is not None:
            self.choose_game(other)
            return
        self.show_game_chooser()

    def show_game_chooser(self):
        self.release_library()
        self.selected_game = None
        self.renderer = MenuRenderer()
        self.screen, self.history, self.message = 'games', [], ''
        self.focus = None
        self.cancel_pointer()
        self.transition_from = None
        self.transition_age = 200
        self.main_exit_ms = None
        pygame.key.stop_text_input()
        pygame.display.set_caption('EXP Runtime')

    @property
    def busy(self):
        return self.job is not None

    @property
    def ready(self):
        return (not self.busy and self.game_entry is None
                and (self.transition_from is None or self.transition_age >= self.transition_duration)
                and (self.screen != 'main' or self.menu_age >= (3000 if self.intro else 500)))

    @property
    def transition_duration(self):
        if getattr(self.library, 'kind', 'apk') == 'ipa':
            return 400
        if self.library and self.transition_source == 'main':
            return 300 if self.screen == 'options' else 400
        if self.library and self.screen == 'main':
            return 400
        return 200

    def open_library(self, directory, *, remember=False):
        library = ContentLibrary(directory)
        try:
            if self.selected_game and library.game_id != self.selected_game:
                raise ContentError(f'This library belongs to {library.game_title}. '
                                   f'Select {library.game_title} in the game chooser to open it.')
            library.ensure_builtin_episodes()
            process_key = (library.game_id, library.kind)
            state = MenuState(library, process=self.processes.get(process_key))
            renderer = MenuRenderer(library)
            if self.game:
                self.game.capture_audio()
                self.state.checkpoint(self.game.session)
            if remember and self.remember_location:
                remember_library(directory, library.game_id)
        except Exception:
            library.close()
            raise
        self.release_library(checkpoint=False)
        self.directory, self.library = Path(directory), library
        self.selected_game = library.game_id
        self.state, self.renderer, self.game = state, renderer, None
        self.processes[process_key] = state.process
        self.expanded_groups = {'saved'}
        self.episode_scroll = 0
        if hasattr(self, 'click_sound'):
            del self.click_sound
        self.screen, self.history, self.selected = 'main', [], state.selected
        self.menu_age, self.intro = 0, True
        self.main_exit_ms = None
        self.message = state.warning
        pygame.display.set_caption(self.game_title)
        self.refresh_saves()

    def refresh_saves(self):
        self.saved = {e['id'] for e in self.library.episodes if self.state.resume_path(e['id'])}
        if self.game and not self.game.session.episode_exited:
            self.saved.add(self.game.session.resources.record['id'])

    def can_resume(self, episode=None):
        return (episode or self.state.selected) in self.saved

    def visible_episodes(self):
        records = self.library.episodes
        if self.scope == 'weekly':
            records = [e for e in records if not is_bundled(e)]
        if self.query:
            query = self.query.casefold()
            matching_groups = {e['id'] for section in self._episode_sections(records)
                               if query in section.title.casefold() for e in section.episodes}
            records = [e for e in records if any(query in title.casefold() for title in e['titles'])
                       or query in e['name'].casefold()
                       or any(query in alias.casefold() for alias in e.get('aliases', []))
                       or e['id'] in matching_groups]
        def key(record):
            title = self.state.title(record).casefold()
            identity = record['pack_id'], record['episode_id']
            # Distinct versions retain their content identity; bundle first
            # when their numeric IDs and titles coincide.
            tie = not is_bundled(record), record['name'].casefold(), record['id']
            return (title, *identity, *tie) if self.state.order == 'title' else (*identity, title, *tie)
        return sorted(records, key=key)

    def episode_sections(self):
        return self._episode_sections(self.visible_episodes())

    def _episode_sections(self, records):
        return group_episodes(records, self.library.catalog,
                             mega_label=self.renderer.strings[82], novel_label=self.renderer.strings[302],
                             saved_label=self.renderer.strings[238],
                             saved=self.saved if self.scope == 'play' else ())

    def episode_rows(self):
        rows, y = [], 0
        for section in self.episode_sections():
            rows.append((y, EPISODE_HEADER_HEIGHT, section, None))
            y += EPISODE_HEADER_HEIGHT
            if self.query or section.key in self.expanded_groups:
                for record in section.episodes:
                    rows.append((y, EPISODE_ROW_HEIGHT, section, record))
                    y += EPISODE_ROW_HEIGHT
        return rows, y

    def show(self, screen, *, remember=True):
        if self.screen == 'episodes':
            self.episode_scroll = self.scroll
        self.transition_from = self.renderer.canvas.copy()
        self.transition_layer = self.renderer.layer.copy() if self.renderer.layer is not None else None
        if self.screen == 'game' and self.game and self.game.pause_renderer is not None:
            self.transition_layer = self.game.pause_renderer.canvas.copy()
        self.transition_direction = 1 if remember else -1
        self.transition_zoom = self.screen in ('main', 'game') or screen == 'main'
        self.transition_source = self.screen
        if self.screen == 'main' and screen != 'main' and getattr(self.library, 'kind', 'apk') == 'apk':
            self.main_exit_ms = 0
        elif screen == 'main':
            self.main_exit_ms = None
        if remember and screen != self.screen:
            self.history.append(self.screen)
        self.screen = screen
        self.scroll = self.episode_scroll if screen == 'episodes' else 0
        self.focus_index = 0
        self.focus = None
        self.cancel_pointer()
        pygame.key.stop_text_input()
        self.transition_age = 0
        if screen == 'main':
            self.menu_age, self.intro = 0, False
        self.buttons = []

    def back(self):
        if self.message:
            self.message = ''
        elif self.history:
            screen = self.history.pop()
            self.show(screen, remember=False)
        elif self.library and self.screen != 'main':
            self.show('main', remember=False)
        elif self.screen == 'setup':
            self.show_game_chooser()

    def _attempt(self, operation):
        try:
            return operation()
        except ERRORS as error:
            self.message = str(error)
            logging.warning('%s', error)

    def _click_sound(self):
        sound = GAMES[self.selected_game].CLICK_SOUND if self.selected_game else None
        if self.audio and self.library and self.state.sound and sound is not None:
            try:
                if not hasattr(self, 'click_sound'):
                    self.click_sound = pygame.mixer.Sound(file=BytesIO(self.library.read_asset(sound)))
                self.click_sound.play()
            except (ContentError, pygame.error) as error:
                logging.debug('Menu sound unavailable: %s', error)

    def _sync_menu_music(self):
        if not self.audio:
            return
        native = getattr(self.library, 'kind', 'apk') == 'ipa'
        enabled = bool(self.library and self.state.music and self.screen != 'game' and not self.paused_menu
                       and self.game_entry is None)
        outgoing = bool(native and self.game and self.game.audio_stored and
                        (self.game.music_loaded or self.game.sound_players))
        enabled = enabled and not outgoing
        if enabled and self.menu_music_fade_ms:
            self.menu_music_fade_ms = 0
            self.menu_music.set_volume(1)
        token = (id(self.library), enabled)
        if token != self.menu_music_token:
            if (native and not enabled and self.menu_music_loaded and self.state.music
                    and self.menu_music.get_busy() and not outgoing):
                if not self.menu_music_fade_ms:
                    self.menu_music_fade_ms = 1000
                if self.game:
                    self.game.audio_wait = True
            else:
                self.menu_music_token = token
                self.menu_music_loaded = self.menu_music_paused = False
                self.menu_music_fade_ms = 0
                self.menu_music.stop()
                if enabled:
                    try:
                        resource = GAMES[self.selected_game].MENU_MUSIC
                        self.menu_music.load(BytesIO(self.library.read_asset(resource)))
                        self.menu_music.play()
                        self.menu_music_loaded = True
                    except (ContentError, pygame.error, ValueError) as error:
                        logging.warning('Menu music cannot be played: %s', error)
        paused = not self.active
        if self.menu_music_loaded and paused != self.menu_music_paused:
            self.menu_music_paused = paused
            if paused:
                self.menu_music.pause()
            else:
                self.menu_music.unpause()
        if self.game:
            self.game.audio_wait = bool(self.menu_music_fade_ms)

    def _tick_menu_audio(self, elapsed):
        if not self.audio:
            return
        if self.menu_music_fade_ms:
            self.menu_music_fade_ms = max(0, self.menu_music_fade_ms - elapsed)
            if self.menu_music_fade_ms and self.menu_music.get_busy():
                self.menu_music.set_volume(self.menu_music_fade_ms / 1000)
            else:
                self.menu_music.stop()
                self.menu_music_loaded = False
                self.menu_music_fade_ms = 0
                self.menu_music_token = (id(self.library), False)
                if self.game:
                    self.game.audio_wait = False
        if self.game and self.screen != 'game':
            self.game._tick_music(elapsed)
        self._sync_menu_music()

    def start_from_menu(self, *, resume=True):
        selector = GAMES[self.selected_game].MENU_TRANSITION
        if not selector:
            self.start(resume=resume)
            return
        self.game_entry = GAMES[self.selected_game].SCENE_TRANSITION()
        self.game_entry.start(selector, 0)
        self.game_entry_resume = resume
        self._sync_menu_music()
        self.cancel_pointer()
        self.buttons = []

    def start(self, *, resume=True, load_path=None):
        self.main_exit_ms = None
        self.game_entry = None
        episode = self.selected
        if self.game and resume and not load_path and self.game.session.resources.record['id'] == episode:
            self.game.menu_open = False
        else:
            if self.game:
                self.game._stop_sounds()
            if load_path:
                session = Session.load(self.library.open_episode(episode), load_path)
                self.state.process.attach(session, restored=True)
                self.state.selected = episode
                self.state.persist()
            else:
                session = self.state.session(episode, resume=resume)
            # A fresh renderer per episode prevents local image IDs from
            # accidentally reusing the previous episode's cached artwork.
            self.game = Desktop(session, audio=self.audio, window=self.window, on_main_menu=self.return_to_menu,
                                episode_title=self.state.title(session.resources.record), on_menu_page=self.show,
                                vibration_enabled=self.state.vibration, minigame_skips=self.state.minigame_skips)
        self.game.episode_title = self.state.title(self.game.session.resources.record)
        self.game.entry_transition = None
        self.game.audio_menu = False
        pygame.display.set_caption(self.game_title + ' — ' + self.game.episode_title)
        self.game.music_enabled, self.game.sound_enabled = self.state.music, self.state.sound
        self.game.vibration_enabled = self.state.vibration
        self.game.choice_hints = self.state.choice_hints
        self.game.minigame_skips = self.state.minigame_skips
        self.game.active = self.active
        self.screen, self.history, self.focus = 'game', [], None
        self.game.screen_token = None
        pygame.key.stop_text_input()
        if self.game.session.episode_exited:
            self.return_to_menu()
            return
        self._sync_menu_music()
        self.game._sync_music()
        self.refresh_saves()

    def return_to_menu(self):
        # Keep the live session even if a filesystem error prevents a checkpoint.
        if self.game.session.engine.word_grid:
            self.game.session.grid_pointer('cancel')
        def save():
            self.game.capture_audio()
            return self.state.checkpoint(self.game.session)
        checkpoint = self._attempt(save)
        # A live session retains its mixer stream and playhead through menu
        # navigation. A fresh Desktop or explicit save load selects a new cue.
        native = getattr(self.library, 'kind', 'apk') == 'ipa'
        self.game.audio_menu = True
        self.game.active = self.active if native else False
        if not self.game.session.episode_exited:
            self.game._sync_music()
        if self.audio:
            pygame.mixer.stop()
        self.game.menu_open = False
        if self.game.session.episode_exited:
            # Completed sessions cannot resume. The terminal automatic save
            # masks older progress without deleting the player's manual slot.
            if self.audio:
                pygame.mixer.music.stop()
                self.game._stop_sounds()
            if checkpoint is not None:
                self.game = None
        self.history = []
        self.show('main', remember=False)
        self.refresh_saves()
        pygame.display.set_caption(self.game_title)

    def browse(self, kind):
        if self.file_picker is not None:
            pygame.key.stop_text_input()
            self.file_picker(kind)
            return
        self.browser_kind = kind
        self.show('browser')
        self.read_folder(self.folder)

    def read_folder(self, folder):
        folder = Path(folder).expanduser().resolve()
        extensions = ({'.apk', '.ipa'} if self.browser_kind == 'apk' else {'.apk'}
                      if self.browser_kind == 'music_apk' else {'.exp', '.zip', '.rar'} if self.browser_kind == 'episodes' else set())
        catalog_name = GAMES[self.selected_game].CATALOG_FILENAME if self.selected_game else None
        files = [p for p in folder.iterdir() if not p.name.startswith('.')
                 and (p.is_dir() or p.suffix.lower() in extensions
                      or (self.browser_kind == 'episodes' and p.name.lower() == catalog_name))]
        # Existing hidden content libraries are useful in the library picker.
        if self.browser_kind == 'library':
            files.extend(p for p in folder.iterdir() if p.name.startswith('.')
                         and p.is_dir() and (p / 'library.json').is_file())
        self.files = sorted(files, key=lambda p: (not p.is_dir(), p.name.casefold()))
        self.folder, self.path_text, self.scroll = folder, str(folder), 0
        self.focus = None
        pygame.key.stop_text_input()

    def import_paths(self, paths):
        if self.busy:
            return
        if self.selected_game is None:
            raise ContentError('Choose SHS or Cause of Death before importing that game’s files.')
        paths = [Path(p).expanduser() for p in paths]
        if not self.library:
            ipas = [p for p in paths if p.suffix.lower() == '.ipa']
            apks = [p for p in paths if p.suffix.lower() == '.apk']
            if len(ipas) > 1 or len(apks) > 1 or not (ipas or apks):
                raise ContentError('Choose one APK or IPA. An IPA can also include one APK for missing music.')
            source = ipas[0] if ipas else apks[0]
            music_apk = apks[0] if ipas and apks else None
            episodes = [p for p in paths if p not in ipas + apks]
            self.job_kind = 'library'
            self.job = self.executor.submit(import_game, source, episodes, self.directory,
                                            music_apk=music_apk, game=self.selected_game)
        elif any(p.suffix.lower() == '.apk' for p in paths):
            if len(paths) != 1:
                raise ContentError('Add one music APK at a time; add episode files separately.')
            self.job_kind = 'music'
            self.job = self.executor.submit(self.library.add_music_apk, paths[0])
        else:
            self.job_kind = 'episodes'
            self.job = self.executor.submit(self.library.add_episodes, paths)
        self.focus = None
        self.cancel_pointer()
        pygame.key.stop_text_input()

    def flush_drops(self):
        if self.dropped_files and not self.busy and not self.dropping:
            paths, self.dropped_files = self.dropped_files, []
            self._attempt(lambda: self.import_paths(paths))

    def command(self, command):
        kind = command[0]
        self.cancel_pointer()
        if (self.busy or self.game_entry is not None
                or self.main_exit_ms is not None and self.transition_source == 'main'
                and self.transition_age < self.transition_duration):
            return
        if self.update_prompt is not None and kind not in ('update_yes', 'update_no', 'back'):
            return
        if kind == 'dismiss':
            self.message = ''
            return
        self._click_sound()
        def perform():
            if kind == 'back':
                if self.update_prompt is not None:
                    self.dismiss_update()
                else:
                    self.back()
            elif kind in ('update_yes', 'update_no'):
                release = self.update_prompt
                self.dismiss_update()
                if release is not None and kind == 'update_yes':
                    self.open_url(release.url)
            elif kind == 'choose_game':
                self.choose_game(command[1])
            elif kind == 'switch_games':
                self.switch_games()
            elif kind == 'episodes':
                self.scope, self.query = command[1], ''
                self.episode_scroll = self.scroll = 0
                self.refresh_saves()
                self.show('episodes')
            elif kind == 'episode':
                self.selected = command[1]
                self.show('episode')
            elif kind in ('options', 'help', 'library', 'restart', 'title_languages', 'cheats'):
                self.show(kind)
            elif kind == 'title_language':
                language = command[1]
                if language not in TITLE_LANGUAGES:
                    raise ValueError('Unsupported episode title language')
                previous = self.state.title_language
                self.state.title_language = language
                try:
                    self.state.persist()
                except OSError:
                    self.state.title_language = previous
                    raise
                self.episode_scroll = self.scroll = 0
            elif kind == 'start':
                self.start_from_menu(resume=command[1])
            elif kind == 'project':
                self.open_url(PROJECT_URL)
            elif kind == 'toggle_updates':
                self.settings.set_update_check(not self.settings.check_for_updates)
                if not self.settings.check_for_updates:
                    self.updates.cancel()
                    self.dismiss_update()
                elif self.check_updates:
                    self.updates.start()
            elif kind == 'toggle':
                key = command[1]
                if key not in ('music', 'sound', 'choice_hints', 'vibration', 'minigame_skips'):
                    raise ValueError('Unknown preference')
                previous = getattr(self.state, key)
                setattr(self.state, key, not previous)
                try:
                    self.state.persist()
                except OSError:
                    setattr(self.state, key, previous)
                    raise
                if self.game:
                    self.game.music_enabled, self.game.sound_enabled = self.state.music, self.state.sound
                    self.game.vibration_enabled = self.state.vibration
                    self.game.choice_hints = self.state.choice_hints
                    self.game.minigame_skips = self.state.minigame_skips
                    self.game._sync_music()
                if key == 'vibration' and self.state.vibration and self.active:
                    pygame.vibrate()
            elif kind in ('save', 'load') and self.paused_menu:
                self.game.command((kind,))
                if kind == 'load' and not self.game.menu_open:
                    self.screen, self.history = 'game', []
                    self.game._sync_music()
                else:
                    self.message = self.game.message
            elif kind == 'order':
                self.state.order = 'title' if self.state.order == 'episode' else 'episode'
                self.state.persist()
                self.scroll = 0
            elif kind == 'episode_group':
                key = command[1]
                self.expanded_groups.symmetric_difference_update({key})
                self._scroll(0)
            elif kind == 'episode_groups':
                keys = {section.key for section in self.episode_sections()}
                if keys <= self.expanded_groups:
                    self.expanded_groups.difference_update(keys)
                else:
                    self.expanded_groups.update(keys)
                self.scroll = 0
            elif kind == 'clear_search':
                self.query, self.scroll, self.focus = '', 0, None
                pygame.key.stop_text_input()
            elif kind == 'browse':
                self.browse(command[1])
            elif kind == 'up':
                self.read_folder(self.folder.parent)
            elif kind == 'file':
                if command[1].is_dir():
                    self.read_folder(command[1])
                else:
                    self.import_paths([command[1]])
            elif kind == 'folder':
                if self.browser_kind == 'library':
                    self.open_library(self.folder, remember=True)
                else:
                    self.import_paths([self.folder])
            elif kind in ('search', 'path'):
                self.focus = kind
                if kind == 'path':
                    self.path_text = ''
                pygame.key.start_text_input()
        self._attempt(perform)

    def open_url(self, url):
        if self.url_opener is not None:
            self.url_opener(url)
        else:
            import webbrowser
            if not webbrowser.open(url):
                self.message = f'Open this page in your browser: {url}'

    def dismiss_update(self):
        self.update_prompt = None
        self.updates.dismiss()
        self.cancel_pointer()
        self.focus, self.focus_index = None, 0
        self.buttons = []

    def tick(self, elapsed):
        if self.job and self.job.done():
            job, kind = self.job, self.job_kind
            self.job = self.job_kind = None
            try:
                result = job.result()
                if kind == 'library':
                    self.open_library(self.directory, remember=True)
                elif kind == 'music':
                    # Retry the current cue on Resume if its earlier load failed.
                    # Keep the live story and all existing checkpoints intact.
                    if self.game and result and not self.game.music_loaded:
                        self.game.music_token = None
                    self.history = ['main']
                    self.show('library', remember=False)
                    self.message = (f'Added {result} missing music tracks.' if result
                                    else 'No missing music tracks to add.')
                else:
                    self.refresh_saves()
                    self.scope, self.query, self.history = 'all', '', ['main']
                    self.episode_scroll = self.scroll = 0
                    self.show('episodes', remember=False)
                    self.message = f'Added {result} episodes.' if result else 'Library updated. No new episodes were added.'
            except ERRORS as error:
                self.message = str(error)
        self.flush_drops()
        if self.settings.check_for_updates:
            available = self.updates.poll()
            if (available is not None and self.update_prompt is None and self.active
                    and not self.busy and not self.message and self.ready
                    and self.screen in ('games', 'setup', 'main')):
                self.update_prompt = available
                self.cancel_pointer()
                self.focus, self.focus_index = None, 0
                self.buttons = []
                pygame.key.stop_text_input()
        if not self.active or self.busy or self.message or self.update_prompt is not None:
            return
        self._tick_menu_audio(elapsed)
        if self.main_exit_ms is not None:
            self.main_exit_ms += elapsed
            if self.main_exit_ms >= 2050:
                self.main_exit_ms = None
        if self.game_entry is not None:
            fade = self.game_entry
            if not fade.tick(elapsed):
                if fade.phase == 3:
                    self.game._tick_music(elapsed)
                return
            if fade.phase == 4:
                # Native mode 103 switches under the opaque layer, without
                # posting a story callback or using either random stream.
                self.game_entry = None
                self._attempt(lambda: self.start(resume=self.game_entry_resume))
                if self.screen == 'game' and not self.message:
                    fade.reveal()
                    self.game_entry = self.game.entry_transition = fade
                    motion = self.game.session.engine.dialogue_animation
                    if motion is not None:
                        motion.stop_layers()
                return
            self.game_entry = self.game.entry_transition = None
        if self.screen == 'game':
            self.game.tick(elapsed)
            if self.game.session.episode_exited:
                self.return_to_menu()
        else:
            # Android recreates the main rows in the submenu's 400 ms exit
            # callback. Its entry clock starts only after that callback.
            delay = (max(0, self.transition_duration - self.transition_age)
                     if self.screen == 'main' and self.transition_from is not None
                     and getattr(self.library, 'kind', 'apk') == 'apk' else 0)
            self.menu_age += max(0, elapsed - delay)
            self.transition_age = min(self.transition_duration, self.transition_age + elapsed)

    def render(self):
        self._sync_menu_music()
        if self.screen == 'game':
            if self.game.session.episode_exited:
                self.return_to_menu()
            else:
                self.game.render()
                return
        canvas = self.renderer.draw(self)
        if (self.transition_from is not None and self.transition_age < self.transition_duration
                and not self.message and not self.busy and self.update_prompt is None):
            if self.library and self.transition_layer is not None and self.renderer.layer is not None:
                canvas = self._menu_transition()
            else:
                layer = canvas.copy()
                layer.set_alpha(round(255 * self.transition_age / self.transition_duration))
                canvas = self.transition_from.copy()
                canvas.blit(layer, (0, 0))
        self.buttons = self.renderer.buttons if self.ready or self.message or self.update_prompt else []
        if self.game_entry is not None:
            draw_transition(canvas, self.game_entry)
        if self.buttons and self.focus == 'buttons':
            rect, _ = self.buttons[self.focus_index % len(self.buttons)]
            pygame.draw.rect(canvas, (255, 255, 255), rect.inflate(4, 4), 1, border_radius=4)
        width, height = self.window.get_size()
        factor = min(width / 320, height / 480)
        size = max(1, round(320 * factor)), max(1, round(480 * factor))
        self.viewport = pygame.Rect((width - size[0]) // 2, (height - size[1]) // 2, *size)
        self.window.fill((8, 12, 20))
        self.window.blit(pygame.transform.smoothscale(canvas, size), self.viewport)
        pygame.display.flip()

    def _menu_transition(self):
        canvas = self.renderer.background.copy()
        incoming, outgoing = self.renderer.layer, self.transition_layer
        if getattr(self.library, 'kind', 'apk') == 'ipa':
            progress = ease_in_out(self.transition_age / 400)
            if self.transition_zoom:
                for layer, scale in ((outgoing, 1 - .99999 * progress), (incoming, .001 + .999 * progress)):
                    size = (max(1, round(320 * scale)), max(1, round(480 * scale)))
                    image = pygame.transform.smoothscale(layer, size)
                    canvas.blit(image, image.get_rect(center=(160, 240)))
            else:
                offset = round(320 * progress) * self.transition_direction
                canvas.blit(outgoing, (-offset, 0))
                canvas.blit(incoming, (320 * self.transition_direction - offset, 0))
        else:
            progress = self.transition_age / self.transition_duration
            if self.transition_source == 'main' or self.screen == 'main':
                # Android 00090818, 00077e00, 0006eb7c and 0007aaa8:
                # zero-size CCNode parents at GL (160,464), linear scale.
                if self.transition_source == 'main':
                    start = .1 if self.screen == 'help' else .2
                    scale, layer = start + (1 - start) * progress, incoming
                elif self.transition_source == 'episodes':
                    scale, layer = 1 - .9 * progress, outgoing
                else:
                    # Help/Options remove themselves in a delayed callback;
                    # unlike Play/Resume they do not scale on this path.
                    scale, layer = 1, outgoing
                size = max(1, round(320 * scale)), max(1, round(480 * scale))
                image = pygame.transform.smoothscale(layer, size)
                canvas.blit(image, (round(160 * (1 - scale)), round(16 * (1 - scale))))
            else:
                offset = round(320 * progress) * self.transition_direction
                canvas.blit(outgoing, (-offset, 0))
                canvas.blit(incoming, (320 * self.transition_direction - offset, 0))
        return canvas

    def _scroll(self, delta):
        self.press.cancel()
        total, height = (len(self.files) * 35, 210) if self.screen == 'browser' else (self.episode_rows()[1], 252)
        self.scroll = max(0, min(max(0, total - height), self.scroll + delta))

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            return False
        if event.type in (pygame.WINDOWFOCUSLOST, pygame.WINDOWFOCUSGAINED):
            self.active = event.type == pygame.WINDOWFOCUSGAINED
            self.cancel_pointer()
            self._sync_menu_music()
            if self.screen == 'game':
                return self.game.handle_event(event)
            if self.game and getattr(self.library, 'kind', 'apk') == 'ipa':
                self.game.handle_event(event)
        if (self.game_entry is not None
                or self.main_exit_ms is not None and self.transition_source == 'main'
                and self.transition_age < self.transition_duration):
            return True
        if self.screen == 'game':
            return self.game.handle_event(event)
        if self.update_prompt is not None:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.command(('update_no',))
                elif event.key in (pygame.K_TAB, pygame.K_UP, pygame.K_DOWN):
                    self.focus, self.focus_index = 'buttons', 1 - self.focus_index % 2
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE) and self.buttons:
                    self.command(self.buttons[self.focus_index % len(self.buttons)][1])
            elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
                self._pointer_event(event)
            return True
        if event.type == pygame.DROPBEGIN:
            self.dropping = True
        if event.type == pygame.DROPFILE:
            self.dropped_files.append(Path(event.file))
            return True
        if event.type == pygame.DROPCOMPLETE:
            self.dropping = False
            self.flush_drops()
        if self.busy:
            return True
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.back()
            return True
        if self.message:
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.command(('dismiss',))
            elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
                self._pointer_event(event)
            return True
        if not self.ready:
            return True
        if event.type == pygame.TEXTINPUT and self.focus in ('search', 'path'):
            value = ''.join(c for c in event.text if c.isprintable())
            if self.focus == 'search':
                self.query = (self.query + value)[:100]
                self.scroll = 0
            else:
                self.path_text = (self.path_text + value)[:4096]
        elif event.type == pygame.KEYDOWN:
            if self.focus in ('search', 'path'):
                if event.key == pygame.K_BACKSPACE:
                    if self.focus == 'search':
                        self.query = self.query[:-1]
                        self.scroll = 0
                    else:
                        self.path_text = self.path_text[:-1]
                elif event.key == pygame.K_RETURN:
                    if self.focus == 'path':
                        self._attempt(lambda: self.read_folder(self.path_text))
                    else:
                        self.focus = None
                        pygame.key.stop_text_input()
            elif event.key in (pygame.K_TAB, pygame.K_UP, pygame.K_DOWN):
                if self.focus == 'buttons':
                    self.focus_index += -1 if event.key == pygame.K_UP else 1
                self.focus = 'buttons'
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE) and self.buttons:
                self.command(self.buttons[self.focus_index % len(self.buttons)][1])
            elif event.key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN) and self.screen in ('browser', 'episodes'):
                self._scroll(-210 if event.key == pygame.K_PAGEUP else 210)
        elif event.type == pygame.MOUSEWHEEL and self.screen in ('browser', 'episodes'):
            self._scroll(-event.y * 35)
        elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
            self._pointer_event(event)
        return True

    def _pointer_event(self, event):
        if event.type != pygame.MOUSEMOTION and event.button != 1:
            return
        point = ((event.pos[0] - self.viewport.x) * 320 / self.viewport.width,
                 (event.pos[1] - self.viewport.y) * 480 / self.viewport.height)
        hit = (next((command for rect, command in self.buttons if rect.collidepoint(point)), None)
               if self.viewport.collidepoint(event.pos) else None)
        phase = {pygame.MOUSEBUTTONDOWN: 'down', pygame.MOUSEBUTTONUP: 'up',
                 pygame.MOUSEMOTION: 'move'}[event.type]
        command = self.press.update(phase, hit, self.input_token())
        if command is not None:
            self.command(command)

    def close(self):
        self.updates.cancel()
        # Worker must finish its atomic publication before its ZIP is closed.
        self.executor.shutdown(wait=True)
        if self.game and self.screen == 'game':
            try:
                self.game.capture_audio()
                self.state.checkpoint(self.game.session)
            except ERRORS as error:
                logging.error('Automatic checkpoint failed: %s', error)
        if self.library:
            self.library.close()
        pygame.quit()

    def run(self):
        clock = pygame.time.Clock()
        running = True
        try:
            while running:
                elapsed = clock.tick(60)
                self.render()
                token = self.input_token()
                for event in pygame.event.get():
                    running = self.handle_event(event)
                    # Do not deliver a queued click to a newly opened screen.
                    if not running or self.input_token() != token:
                        break
                    if self.screen == 'game' and self.game.screen_token != self.game._screen_token():
                        break
                if running:
                    self.tick(elapsed)
        finally:
            self.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description='EXP Runtime — play SHS or Cause of Death with your own assets')
    parser.add_argument('--library', type=Path, help='Local content library (default: per-user application data)')
    parser.add_argument('--game', choices=GAMES, help='Open this game directly instead of the chooser')
    parser.add_argument('--no-audio', action='store_true')
    parser.add_argument('--smoke-test', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.smoke_test:
        from .app_info import runtime_version
        from .rar import library
        library()  # Frozen downloads must include a usable RAR4/RAR5 decoder.
        if runtime_version() == 'development':
            raise RuntimeError('Packaged runtime version is missing')
        # A packaged-build check must never open or alter the player's library.
        with tempfile.TemporaryDirectory(prefix='exp-setup-test-') as temporary:
            app = Application(audio=False, check_updates=False)
            try:
                if app.screen != 'games' or app.library is not None:
                    raise RuntimeError('Expected game chooser without game content')
                app.render()
                # Exercise both setup screens without opening any real library.
                app.directory = Path(temporary) / 'library'
                for key in GAMES:
                    app.selected_game, app.screen = key, 'setup'
                    app.render()
                app.screen = 'help'
                app.render()
            finally:
                app.close()
        return
    Application(args.library, audio=not args.no_audio, game_key=args.game).run()


if __name__ == '__main__':
    main()
