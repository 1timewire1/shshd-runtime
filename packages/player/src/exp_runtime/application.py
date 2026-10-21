"""Shared application lifecycle: import, menu, episode sessions and shutdown.

The executable starts here with no game data. A host supplies graphics/input
primitives; imports run on a worker and publish a validated library atomically.
"""
import argparse
import webbrowser
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
from .desktop import Desktop, SIZE, DEFAULT_WINDOW_SIZE
from .application_hd import HdShell
from .desktop_episode_list_hd import HdEpisodeList
from .desktop_episode_picker import FRAME as PICKER_FRAME, HdEpisodePicker
from .animation_curves import ease_in_out
from .desktop_pause import PAUSE_OPEN_MS, pause_scale
from .desktop_pause_hd import HdPauseMenu
from .desktop_menu import MenuRenderer
from .episode_picker import PickerModel
from . import episode_thumbnails
from .languages import TITLE_LANGUAGES
from .launcher import APP_NAME
from .games import GAMES
from .ui_sound import UiSounds
from .music_stream import FADE_MS
from .menu import (EPISODE_HEADER_HEIGHT, EPISODE_ROW_HEIGHT, MenuState,
                   default_library, group_episodes, remember_library)
from .runtime import SaveError, Session
from .settings import AppSettings
from .updates import UPDATE_TITLE, UpdateCheck, update_message
from .pointer import ButtonPress
from .staged_import import (ARCHIVE_SUFFIXES, discover as discover_staged_import, import_bulk, import_staged,
                            staged_archive, staged_import_directory)
from .vm import VMError


ERRORS = (ContentError, SaveError, VMError, OSError, ValueError, pygame.error)
AUTOSAVE_MS = 60000     # SHSEngine::onTick saves the game every 60 s of play
# This fork: the HD launch waits at most this long past its loading screen for the update check (it usually finishes
# during loading), so an offer comes before "Play with sound?"; a later answer waits for the idle main menu.
UPDATE_WAIT = 2.5


class Application:
    shell = None            # the HD launch flow / main menu, when an HD bundle is imported
    menu_sound = None       # the main menu's music (a Sound, so a paused episode keeps its own stream)
    menu_fade = None        # ticks when the Music switch started fading it out (music_stream.FADE_MS)
    ui_sounds = None        # the selected game's interface sounds (ui_sound.py), loaded on first use
    end_record = None

    def __init__(self, directory=None, *, audio=True, game_key=None, file_picker=None,
                 library_root=None, url_opener=None, settings_path=None,
                 update_fetcher=None, check_updates=True, game_libraries=None, can_quit=True):
        if game_key is not None and game_key not in GAMES:
            GAMES[game_key]  # Explain which optional game component is missing.
        if not GAMES:
            raise ContentError('No game adapters are installed. Install "exp-runtime[shs]", '
                               '"exp-runtime[cod]", or "exp-runtime[player]" for both.')
        default_game = next(iter(GAMES))
        pygame.display.init()
        pygame.font.init()
        # Wider than the 2:3 menu/UI layout so an HD episode's background can
        # show real extra content around it once one is opened (see Desktop).
        self.window = pygame.display.set_mode(DEFAULT_WINDOW_SIZE, pygame.RESIZABLE)
        pygame.display.set_caption('Surviving High School')
        self.remember_location = directory is None and library_root is None
        # One RuntimeProcess per game and package kind (exp-runtime v0.6.0): the native app keeps its random
        # generators and fonts across episodes, so reopening a library continues them (process.py).
        self.processes = {}
        self.file_picker = file_picker
        self.url_opener = url_opener
        self.settings = AppSettings(settings_path)
        self.updates = UpdateCheck(update_fetcher)
        self.check_updates = check_updates  # Diagnostics can remain entirely offline.
        self.update_prompt = None
        # Whether the app may close itself: Yes on the update offer opens the release page and quits (desktop). The iOS
        # host passes False (an iOS app cannot quit or update itself), so the offer only informs, with an OK.
        self.can_quit = can_quit
        self.quit_requested = False
        located = (default_library if library_root is None else
                   lambda key: Path(library_root) / key)
        # This fork: per-game libraries given on the command line (--game-library), used for Switch Game and never
        # remembered, so a test setup leaves the player's own launcher.json alone.
        given = {key: Path(path) for key, path in (game_libraries or {}).items()}
        self.library_path = lambda key: given[key] if key in given else located(key)
        self.selected_game = game_key
        self.directory = Path(directory) if directory is not None else self.library_path(game_key or default_game)
        self.library = self.state = self.game = None
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
        # exp-runtime v0.6.0's native submenu transitions for the Android / iPhone menus (no HD shell): the outgoing
        # and incoming layers, their direction, and the main rows' 2050 ms departure (`main_exit_ms`).
        self.transition_layer = None
        self.transition_direction = 1
        self.transition_zoom = False
        self.transition_source = None
        self.main_exit_ms = None
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
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='exp-content')
        self.job = None
        self.job_kind = None
        self.progress_text = ''
        self.picker = None
        self.picker_style = None
        self.shell = None
        self.end_record = None
        self.shot_cache = {}
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
        elif self.screen != 'games':
            start = game_key or default_game
            try:
                folder = staged_import_directory()
                staged = discover_staged_import(folder)
                archive = staged_archive(folder) if staged is None else None
            except ERRORS as error:
                self.message = str(error)
            else:
                if staged is not None:
                    # Every game the folder holds whose library does not exist yet (this fork: both at once).
                    targets = {game: path for game, path in self.library_targets(start).items()
                               if game in staged.games and not path.exists()}
                    if targets:
                        self.job_kind = 'staged'
                        self.job = self.executor.submit(import_staged, staged, targets)
                elif archive is not None:
                    self.start_bulk(archive, start)     # the same, from one .zip/.rar in the folder
            if self.job is None and directory is None:
                # This fork: with nothing to import, a player with no library lands on Bulk Import, and one whose
                # only library is the other game's opens that game.
                other = next((key for key in GAMES if key != start
                              and (self.library_path(key) / 'library.json').is_file()), None)
                if other is not None:
                    self.choose_game(other)
                else:
                    self.screen = 'bulk'
        if self.screen == 'setup' and self.selected_game is None:
            self.selected_game = default_game
        if self.check_updates and self.settings.check_for_updates:
            self.updates.start()

    shell_prompt = ()

    def shell_idle(self):
        """Where the update prompt may appear with the HD menus showing: at the end of the launch's loading screen
        (before "Play with sound?"), or on the main menu with no window, pause card or fade over it."""
        shell = self.shell
        return (shell is None or self.screen != 'main' or shell.loaded
                or (shell.stage == 'main' and not shell.overlay_active and not shell.pause_open and not shell.fading))

    def update_holds_launch(self, waited):
        """Whether the HD launch holds before "Play with sound?": the update offer is up, or the launch's check is
        still out, or its answer is still to be shown, for less than UPDATE_WAIT seconds past the loading screen."""
        if self.update_prompt is not None:
            return True
        return (self.updates.future is not None or self.updates.available is not None) and waited < UPDATE_WAIT

    def set_update_check(self, enabled):
        """The launch update check on or off (settings.json), from the SD Options or the HD General page."""
        self.settings.set_update_check(enabled)
        if not enabled:
            self.updates.cancel()
            self.dismiss_update()
        elif self.check_updates:
            self.updates.start()

    def input_token(self):
        return self.screen, self.message, self.update_prompt

    @property
    def game_title(self):
        return GAMES[self.selected_game].TITLE if self.selected_game else APP_NAME

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
            self.state.checkpoint(self.game.session)
        if self.audio:
            self.menu_music.stop()
            self.menu_music_token = None
            self.menu_music_loaded = self.menu_music_paused = False
            pygame.mixer.music.stop()
            pygame.mixer.stop()
        if self.library:
            self.library.close()
        self.library = self.state = self.game = None
        self.saved = set()
        self.selected = None
        self.ui_sounds = None

    def switch_games(self):
        other = next((key for key in GAMES if key != self.selected_game
                      and (self.library_path(key) / 'library.json').is_file()), None)
        if other is not None:
            if self.shell is not None and self.screen == 'main':
                if not self.shell.fading:
                    self.shell.leave(lambda: self._switch_to(other))       # the HD menu fades to black first
                return
            self._switch_to(other)
            return
        self.show_game_chooser()

    def _switch_to(self, other):
        self.choose_game(other)
        if self.shell is not None and self.screen == 'main':
            self.shell.arrive()         # a switch is not a launch: no loading screen or sound question

    def other_game_title(self):
        """The title of the game Switch Game leads to (the HD main menu's fourth button carries it)."""
        other = next((key for key in GAMES if key != self.selected_game), None)
        return GAMES[other].TITLE if other else None

    def show_game_chooser(self):
        self.release_library()
        self.selected_game = None
        self.renderer = MenuRenderer()
        self.screen, self.history, self.message = 'games', [], ''
        self.focus = None
        self.cancel_pointer()
        self.transition_from = None
        self.transition_age = 200
        pygame.key.stop_text_input()
        pygame.display.set_caption(APP_NAME)

    @property
    def busy(self):
        return self.job is not None

    # An episode picker opened from the HD main menu zooms in over it (`setAppMode` -> `animateView(20)`, 0.4 s, as
    # the menus do: docs/MAIN_MENU.md, "Menu entrances") while the menu's buttons slide out; ms into that, or done.
    picker_zoom = PAUSE_OPEN_MS

    def picker_over_menu(self):
        """Whether the picker is drawn over the live HD main menu: while it zooms in and until the menu's buttons have
        slid out. Only the picker's own layer (its dim, tiles and buttons) zooms; the menu shows through it."""
        if self.shell is None or self.screen != 'picker':
            return False
        main = getattr(self.shell, 'main', None)
        leaving = main is not None and main.leaving is not None and not main.left
        return self.picker_zoom < PAUSE_OPEN_MS or leaving

    @property
    def ready(self):
        if self.shell is not None and self.screen == 'main':
            return not self.busy
        if self.screen == 'picker' and self.picker_zoom < PAUSE_OPEN_MS:
            return False
        return (not self.busy
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
        if 'SHS_HD_ART' not in os.environ:
            library.hd_art_mode = state.hd_art          # the player's choice (player.json), unless the environment sets it
        self.expanded_groups = {'saved'}
        self.episode_scroll = 0
        self.picker, self.shot_cache = None, {}
        # CoD's front end is SHS HD's shell on CoD's own menus (application_cod.py); SHS's needs its HD bundle.
        from .application_cod import CodShell
        self.shell = (CodShell(self) if CodShell.available(library) else HdShell(self) if HdShell.available(library)
                      else None)
        self.ui_sounds = None
        self.screen, self.history, self.selected = 'main', [], state.selected
        self.menu_age, self.intro = 0, True
        self.main_exit_ms = None
        self.message = state.warning
        pygame.display.set_caption(self.game_title)
        self.refresh_saves()
        if self.shell is not None:
            self.shell.set_switch_title(self.other_game_title())
            self.shell.begin()
        self.prepare_previews()

    def library_targets(self, start=None):
        """Where each game's new library goes: `start`'s at this app's own directory, the others' at their own."""
        return {key: self.directory if key == start else self.library_path(key) for key in GAMES}

    def start_bulk(self, archive, start=None):
        """Import every game a bulk .zip/.rar holds (staged_import.import_bulk), on the worker."""
        self.job_kind = 'bulk'
        self.job = self.executor.submit(import_bulk, Path(archive), self.library_targets(start))
        self.focus = None
        self.cancel_pointer()
        pygame.key.stop_text_input()

    def show_bulk(self):
        """The Bulk Import page (first boot, or the game chooser's Bulk Import): no game is open there."""
        if self.library is not None:
            self.release_library()
        self.selected_game = None
        self.renderer = MenuRenderer()
        pygame.display.set_caption(APP_NAME)
        self.show('bulk')

    def _open_staged(self, result):
        """A staged import's libraries (staged_import.import_staged): each remembered, the starting game's opened
        (else the other's), and any game that failed reported."""
        imported, errors = result
        if self.remember_location:
            for game, path in imported.items():
                remember_library(path, game)
        if not imported:
            raise errors[0]
        game = self.selected_game if self.selected_game in imported else next(iter(imported))
        self.selected_game, self.directory = game, imported[game]
        self.open_library(self.directory)
        if errors:
            self.message = ' '.join(str(error) for error in errors)

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

    def picker_classes(self):
        """The tile grid and list screens for this library's game: SHS HD's, or the same in CoD's dress."""
        if getattr(self.library, 'game_id', None) == 'cod':
            from .desktop_cod_episodes import CodEpisodeList, CodEpisodePicker
            return CodEpisodePicker, CodEpisodeList
        return HdEpisodePicker, HdEpisodeList

    def picker_available(self):
        return bool(self.library) and self.picker_classes()[0].available(self.library)

    def ensure_picker(self, style='tile'):
        """The HD picker, as a tile grid, a scrollable text list grouped by category (`style='list'`), or the
        same list grouped by release year instead (`style='airing'`) -- kept for whichever style was last
        opened, and rebuilt if another one is asked for."""
        if self.picker is None or self.picker_style != style:
            if getattr(self.library, 'game_id', None) == 'cod':
                model = PickerModel(self.library, chronological=style == 'airing')
            else:
                strings = self.renderer.strings
                model = PickerModel(self.library, mega_label=strings[82], novel_label=strings[302],
                                    chronological=style == 'airing', title_language=self.state.title_language)
            cls = self.picker_classes()[0 if style == 'tile' else 1]
            self.picker = cls(self.library, model, self.saved_shot)
            if style != 'tile' and self.shell is not None:
                self.picker.card = self.shell.pause       # the lists wear the game's menu card (HD / CoD)
            self.picker_style = style
        return self.picker

    def saved_shot(self, record):
        """A saved game's screenshot (432 x 580), or None."""
        try:
            path = self.state.shot_path(record['id'])
            stamp = path.stat().st_mtime_ns
        except (OSError, ContentError):
            return None
        cached = self.shot_cache.get(record['id'])
        if cached is None or cached[0] != stamp:
            try:
                image = pygame.image.load(str(path)).convert()
            except (pygame.error, OSError):
                return None
            cached = self.shot_cache[record['id']] = (stamp, image)
        return cached[1]

    def save_screenshot(self):
        """Photograph the running game for the picker's "Continue" half (its last frame, clean)."""
        try:
            record = self.game.session.resources.record
            path = self.state.shot_path(record['id'])
            if self.game.session.episode_exited:
                path.unlink(missing_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                pygame.image.save(self.game.snapshot(), str(path), 'jpg')
            self.shot_cache.pop(record['id'], None)
        except (ContentError, OSError, pygame.error, ValueError) as error:
            logging.warning('Could not save a screenshot: %s', error)

    def prepare_previews(self):
        """First-time setup for the HD picker: index episodes, build the HD twin store from the shipped twin map when
        it is due (this fork), and render the missing previews, off the UI thread."""
        if self.busy or not self.picker_available():
            return
        if (not self.library.unindexed() and not self.hd_art_due()
                and not episode_thumbnails.missing_records(self.library, self.ensure_picker().model.records)):
            return
        self.job_kind = 'previews'
        self.progress_text = 'Starting...'
        self.job = self.executor.submit(self._prepare_previews, self.library)

    def twin_map(self):
        """The library's game's shipped HD twin map (SHS's), or None."""
        loader = getattr(GAMES.get(self.library.game_id), 'twin_map', None) if self.library else None
        return loader() if loader else None

    def hd_art_due(self):
        """Whether the library's twin store still has to be built (or rebuilt) from the shipped twin map: an SHS
        library with HD episodes whose store did not come from this map version. A v1.0.0 library (no store) gets
        it on its next open; no re-import is needed (the HD episodes it holds are the source)."""
        twin_map = self.twin_map()
        if twin_map is None or not any(r.get('variant') == 'hd' for r in self.library.episodes):
            return False
        return self.library.twin_store().source().get('map') != twin_map.VERSION

    def _prepare_previews(self, library):
        library.index_missing()
        if self.hd_art_due():
            from .hd_twins import build_from_map

            def found(done, total):
                self.progress_text = f'HD art: {done + 1} of {total} episodes'[:44]
            build_from_map(library, self.twin_map(), found)
        model = PickerModel(library)

        def progress(done, total, title):
            self.progress_text = f'{done + 1} of {total}: {title}'[:44]
        return episode_thumbnails.ensure(library, model.records, progress)

    # -- the HD shell's hooks ------------------------------------------------------------------------------
    def external_music(self):
        """Whether music from another app is playing (the iOS app then asks "Continue playing your music?")."""
        return False

    def play_asset(self, asset_id):
        if self.audio and self.library and self.state.sound:
            try:
                sound = pygame.mixer.Sound(file=BytesIO(self.library.read_asset(asset_id)))
                sound.set_volume(self.state.sound_volume / 100)
                sound.play()
            except (ContentError, pygame.error) as error:
                logging.debug('Sound %s unavailable: %s', asset_id, error)

    def play_menu_music(self):
        """The music the app plays out of an episode (`doSoundManagerTransition`: playMusic once, no loop; SHS HD's
        0x2017, CoD's 0x2011 at 00025c60; the game profile's MENU_MUSIC). It is a separate Sound, not the music
        stream, so an episode left with the pause menu still resumes its own cue where it stopped."""
        self.stop_menu_music()
        if not (self.audio and self.library and self.state.music):
            return
        try:
            asset = GAMES[self.library.game_id].MENU_MUSIC
            self.menu_sound = pygame.mixer.Sound(file=BytesIO(self.library.read_asset(asset)))
            self.menu_sound.set_volume(self.state.music_volume / 100)
            self.menu_sound.play()
        except (ContentError, pygame.error) as error:
            logging.debug('Menu music unavailable: %s', error)
            self.menu_sound = None

    @staticmethod
    def _stop_sounds_but(kept):
        """Stop every effect channel except the one playing `kept`."""
        try:
            for index in range(pygame.mixer.get_num_channels()):
                channel = pygame.mixer.Channel(index)
                if channel.get_sound() is not kept:
                    channel.stop()
        except (AttributeError, pygame.error):
            pass

    def stop_menu_music(self):
        self.menu_fade = None
        if self.menu_sound is not None:
            self.menu_sound.stop()
            self.menu_sound = None

    def menu_music_changed(self, *, switched=False):
        """The Music switch (`switched`) or volume changed while the main menu shows. As `setMusicEnabled` /
        `doSoundManagerTransition` do: off fades the menu's music out over 1000 ms; on plays it again from the start,
        unless it is still fading, when the fade is cancelled and it plays on (playMusic of the same cue)."""
        if not self.state.music:
            if self.menu_sound is not None and self.menu_fade is None:
                self.menu_fade = pygame.time.get_ticks()
            return
        if self.menu_fade is not None:
            self.menu_fade = None
        elif switched:
            if self.shell is not None and self.screen == 'main':
                self.play_menu_music()
            return
        if self.menu_sound is not None:
            self.menu_sound.set_volume(self.state.music_volume / 100)

    def _fade_menu_music(self):
        """One frame of the Music switch's fade-out (linear, as `-[SHSSound getFadeLevel]`)."""
        if self.menu_fade is None or self.menu_sound is None:
            return
        level = 1 - (pygame.time.get_ticks() - self.menu_fade) / FADE_MS
        if level <= 0:
            self.stop_menu_music()
        else:
            self.menu_sound.set_volume(self.state.music_volume / 100 * level)

    def open_url(self, url):
        try:
            webbrowser.open(url)
        except webbrowser.Error as error:
            logging.warning('Cannot open %s: %s', url, error)

    def open_picker(self, *, restore=True, style='tile'):
        self.refresh_saves()
        self.ensure_picker(style).enter(self.state.selected)
        self.picker.show_restore = restore
        zoom = self.shell is not None and self.screen == 'main' and self.shell.stage == 'main'
        self.show('picker')
        self.picker_zoom = 0 if zoom else PAUSE_OPEN_MS

    def end_menu_backdrop(self):
        # When an episode has ended: (the last frame dimmed sepia, whether it was Football Season), else None.
        if self.shell is None or not self.game.session.episode_exited:
            return None
        record = self.game.session.resources.record
        self.end_record = record['id']
        try:
            frame = self.game.snapshot(PICKER_FRAME)
        except (pygame.error, ValueError):
            return None
        return HdPauseMenu.sepia(frame), record.get('builtin') == 'football-star'

    def leave_end_menu(self, *, picker=False, replay=False, style='tile'):
        """The end-of-episode menu is done: back to the main menu, the picker, or the same episode again."""
        if replay and self.end_record:
            self.game = None
            self.selected = self.end_record
            self.start(resume=False)
        elif picker and self.picker_available():
            self.show('main', remember=False)
            self.open_picker(style=style)
        else:
            self.show('main', remember=False)

    def present_frame(self, canvas):
        """Show a 768 x 1024 point canvas, fitted to the window (with the collage HD shows beside its frame)."""
        width, height = self.window.get_size()
        factor = min(width / PICKER_FRAME[0], height / PICKER_FRAME[1])
        size = max(1, round(PICKER_FRAME[0] * factor)), max(1, round(PICKER_FRAME[1] * factor))
        self.viewport = pygame.Rect((width - size[0]) // 2, (height - size[1]) // 2, *size)
        self.buttons = []
        self.window.fill((8, 12, 20))
        if size != (width, height) and self.shell is not None:      # beside the frame, or above and below it
            self.window.blit(self.shell.main.side_art((width, height)), (0, 0))
        self.window.blit(pygame.transform.smoothscale(canvas, size), self.viewport)

    def render_shell(self):
        canvas = self.shell.render()
        if self.busy:
            self.shell.main.draw_busy(canvas, 'Preparing episodes' if self.job_kind == 'previews' else 'Importing content',
                                      self.progress_text if self.job_kind == 'previews' else 'Checking and copying your files...')
        elif self.message:
            self.shell.main.draw_busy(canvas, self.game_title, self.message)
        elif self.update_prompt is not None:
            # Drawn by the shell's window renderer, which has each game's own footer buttons.
            commands = (('update_no',), ('update_yes',)) if self.can_quit else (('update_no',),)
            rects = self.shell.windows.draw_prompt(
                canvas, UPDATE_TITLE, update_message(self.update_prompt.version, can_quit=self.can_quit),
                ('No', 'Yes') if self.can_quit else ('OK',))
            self.shell_prompt = list(zip(rects, commands))
        self.present_frame(canvas)
        pygame.display.flip()

    def shell_event(self, event):
        shell = self.shell
        if event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
            shell.focus = shell.pause.state.focus = None         # the pointer takes over from the arrow keys
        if event.type == pygame.KEYDOWN:
            command = shell.key(event.key)
            if command is not None and command[0] != 'pause_toggle':      # as a tap's (below)
                self._click_sound()
        elif event.type == pygame.MOUSEWHEEL:
            shell.wheel(event.y)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            shell.pointer_down(self.picker_point(event.pos))
        elif event.type == pygame.MOUSEMOTION and event.buttons[0]:
            shell.pointer_move(self.picker_point(event.pos))
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            pressed = shell.pressed
            shell.pointer_up(self.picker_point(event.pos))
            # Switches and sliders do not click (`SHSWidgetMenu::buttonPressed` tags 10-12, `sliderChanged`).
            if pressed is not None and pressed[0] not in ('pause_slider', 'pause_scroll', 'pause_toggle'):
                self._click_sound()
        return True

    def show(self, screen, *, remember=True):
        if self.screen == 'episodes':
            self.episode_scroll = self.scroll
        self.transition_from = self.renderer.canvas.copy()
        self.transition_layer = self.renderer.layer.copy() if getattr(self.renderer, 'layer', None) is not None else None
        if self.screen == 'game' and self.game and self.game.pause_renderer is not None:
            self.transition_layer = self.game.pause_renderer.canvas.copy()
        self.transition_direction = 1 if remember else -1
        self.transition_zoom = self.screen in ('main', 'game') or screen == 'main'
        self.transition_source = self.screen
        if (self.screen == 'main' and screen != 'main' and self.shell is None
                and getattr(self.library, 'kind', 'apk') == 'apk'):
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
            if self.shell is not None and self.shell.stage not in ('loading', 'sound', 'flash'):
                self.shell.enter_main()
        self.buttons = []

    def back(self):
        if self.message:
            self.message = ''
        elif self.screen == 'main' and self.shell is not None:
            self.shell.back()
        elif self.screen == 'picker' and self.shell is not None and self.shell.overlay_active:
            self.shell.close_window()
        elif self.history:
            screen = self.history.pop()
            self.show(screen, remember=False)
        elif self.library and self.screen != 'main':
            self.show('main', remember=False)
        elif self.screen in ('setup', 'bulk'):
            self.show_game_chooser()

    def _attempt(self, operation):
        try:
            return operation()
        except ERRORS as error:
            self.message = str(error)
            logging.warning('%s', error)

    def _click_sound(self):
        self.ui_sound('CLICK_SOUND')

    def play_buzz(self):
        """The vibration stand-in's buzz (vibration.py) at the Sound FX volume, while Sound is on; a device that can
        vibrate vibrates instead."""
        if pygame.supports_vibration():
            pygame.vibrate()
            return
        if not (self.audio and self.state.sound):
            return
        from .vibration import buzz_wav
        try:
            sound = pygame.mixer.Sound(file=BytesIO(buzz_wav()))
            sound.set_volume(self.state.sound_volume / 100)
            sound.play()
        except pygame.error as error:
            logging.warning('Vibration buzz cannot be played: %s', error)

    def ui_sound(self, name, *, volume=None, stop_others=False, when_idle=False):
        """Play the selected game's interface sound `name` (a profile attribute) from its base bank: at the Sound FX
        volume and only with Sound on, unless a `volume` of its own is given (the Music slider's preview)."""
        if not (self.audio and self.library and self.selected_game) or (volume is None and not self.state.sound):
            return
        if self.ui_sounds is None:
            self.ui_sounds = UiSounds()
        self.ui_sounds.play(self.library, getattr(GAMES[self.selected_game], name),
                            self.state.sound_volume / 100 if volume is None else volume,
                            stop_others=stop_others, when_idle=when_idle)

    def _sync_menu_music(self):
        if not self.audio:
            return
        enabled = bool(self.library and self.shell is None and self.state.music and self.screen != 'game'
                       and not self.paused_menu)
        token = (id(self.library), enabled)
        if token != self.menu_music_token:
            self.menu_music_token = token
            self.menu_music_loaded = self.menu_music_paused = False
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

    def start(self, *, resume=True, load_path=None):
        self.main_exit_ms = None
        episode = self.selected
        if self.game and resume and not load_path and self.game.session.resources.record['id'] == episode:
            self.game.menu_open = False
        else:
            if load_path:
                session = Session.load(self.library.open_episode(episode), load_path)
                self.state.process.attach(session, restored=True)
                self.state.selected = episode
                self.state.persist()
            else:
                path = self.state.resume_path(episode) if resume else None
                try:
                    session = self.state.session(episode, resume=resume)
                except SaveError:
                    if path is None:
                        raise
                    self.discard_unloadable_save(path)
                    return
            # A fresh renderer per episode prevents local image IDs from
            # accidentally reusing the previous episode's cached artwork.
            self.game = Desktop(session, audio=self.audio, window=self.window, on_main_menu=self.return_to_menu,
                                names=self.state.names, vibration_enabled=self.state.vibration,
                                episode_title=self.state.title(session.resources.record), on_menu_page=self.show)
        self.stop_menu_music()
        self.game.episode_title = self.state.title(self.game.session.resources.record)
        pygame.display.set_caption(self.game_title + ' — ' + self.game.episode_title)
        self.game.music_enabled, self.game.sound_enabled = self.state.music, self.state.sound
        self.game.vibration_enabled = self.state.vibration
        self.game.music_volume, self.game.sound_volume = self.state.music_volume / 100, self.state.sound_volume / 100
        self.game.choice_hints = self.state.choice_hints
        self.game.skip_minigames = self.state.skip_minigames
        self.game.skip_ad_intros = self.state.skip_ad_intros
        self.game.autoplay = self.state.autoplay
        self.game.disable_choice_timer = self.state.disable_choice_timer
        self.game.hd_backdrop = self.state.hd_backdrop
        self.game.warp_unlocked = self.state.warp_unlocked
        self.game.on_settings = self.save_game_settings
        self.game.active = self.active
        self.screen, self.history, self.focus = 'game', [], None
        self.autosave_age, self.unsaved_entry = 0, True                      # setAppMode(playing)
        self.game.screen_token = None
        pygame.key.stop_text_input()
        if self.game.session.episode_exited:
            self.return_to_menu()
            return
        self._sync_menu_music()
        self.game._sync_music()
        self.refresh_saves()

    autosave_age = 0            # ms of play since the game was last saved (`SHSEngine +0x649d0`)
    unsaved_entry = False       # the game has not been saved since it was entered (`SHSEngine +0x649ce`)

    def autosave(self, *, screenshot=False, only_if_unsaved=False):
        """The app's own saving: every 60 s of play (`onTick`), and once when the app is left (`onExit`, from
        `applicationWillResignActive:` and `applicationWillTerminate:`, only while `+0x649ce` is set, which entering the game sets
        and this clears). Returns the saved path or None; a failure is logged, never shown."""
        self.autosave_age = 0
        if only_if_unsaved:
            if not self.unsaved_entry:
                return None
            self.unsaved_entry = False
        session = self.game.session if self.game else None
        if session is None or session.episode_exited or session.pending is None:
            return None
        try:
            path = self.state.checkpoint(session)
            if screenshot:
                self.save_screenshot()
            self.refresh_saves()
            return path
        except ERRORS as error:
            logging.warning('Automatic save failed: %s', error)
            return None

    def discard_unloadable_save(self, path):
        """`SHSEngine::onTick`, a load that fails (`loadGame` result 1): the save file is deleted and the error dialog "Save file was
        corrupt. Save file could not be loaded. Deleting save file." (string 228) is shown at the episode menu. The file is kept
        beside as `.corrupt` here rather than deleted, so a fault in this loader cannot cost a player their game."""
        try:
            path.replace(path.with_name(path.name + '.corrupt'))
        except OSError as error:
            logging.warning('Could not set aside the unloadable save %s: %s', path, error)
        try:
            from .menu import MenuStrings
            self.message = MenuStrings.parse(self.library.hd_raw_resource(15))[228]
        except (AttributeError, ContentError, ValueError, IndexError, TypeError):
            self.message = 'Save file was corrupt. Save file could not be loaded. Deleting save file.'
        self.refresh_saves()

    def save_game_settings(self):
        """The in-game pause menu's music / sound switches are the same host options as the main menu's."""
        self.state.music, self.state.sound = self.game.music_enabled, self.game.sound_enabled
        self.state.vibration = self.game.vibration_enabled
        self.state.choice_hints = self.game.choice_hints
        self.state.skip_minigames = self.game.skip_minigames
        self.state.skip_ad_intros = self.game.skip_ad_intros
        self.state.autoplay = self.game.autoplay
        self.state.disable_choice_timer = self.game.disable_choice_timer
        self.state.hd_backdrop = self.game.hd_backdrop
        self.state.music_volume = round(self.game.music_volume * 100)
        self.state.sound_volume = round(self.game.sound_volume * 100)
        self.state.persist()

    def unlock_warp_if_football_finished(self):
        """`SHSEngine::invokeEndOfGameMenu`: at the end of the episode with id 0 (Football Season) the tree's lock (+0x6490a) is cleared,
        for good (it is one of the saved options)."""
        record = self.game.session.resources.record
        if (self.game.session.episode_exited and record.get('builtin') == 'football-star' and not self.state.warp_unlocked):
            self.state.warp_unlocked = True
            self._attempt(self.state.persist)

    def return_to_menu(self, pause_box=None):
        # The menu's song the pause menu was playing carries on in the main menu (Desktop.take_pause_song). It is taken
        # first: anything that renders the game now (the screenshot, the music sync) would start fading it, since the
        # pause menu has closed.
        kept = self.game.take_pause_song() if self.audio and not self.game.session.episode_exited else None
        self.unlock_warp_if_football_finished()
        # Keep the live session even if a filesystem error prevents a checkpoint.
        if self.game.session.engine.word_grid:
            self.game.session.grid_pointer('cancel')
        end = self.end_menu_backdrop()
        checkpoint = self._attempt(lambda: self.state.checkpoint(self.game.session))
        self.save_screenshot()
        # A live session retains its mixer stream and playhead through menu
        # navigation. A fresh Desktop or explicit save load selects a new cue.
        self.game.active = False
        if not self.game.session.episode_exited:
            self.game._sync_music()
        if self.audio:
            if kept is None:
                pygame.mixer.stop()
            else:
                self._stop_sounds_but(kept)
        self.game.menu_open = False
        if self.game.session.episode_exited:
            # Completed sessions cannot resume. The terminal automatic save
            # masks older progress without deleting the player's manual slot.
            if self.audio:
                pygame.mixer.music.stop()
            if checkpoint is not None:
                self.game = None
        self.history = []
        self.show('main', remember=False)
        if end is not None:
            self.shell.show_end_menu(*end)
        elif pause_box is not None and self.shell is not None:
            self.shell.zoom_out(pause_box)
        if kept is not None and self.shell is not None:
            self.stop_menu_music()
            self.menu_sound = kept
        elif self.shell is not None and self.shell.stage != 'flash':
            self.play_menu_music()
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
                      if self.browser_kind == 'music_apk' else {'.exp', '.zip', '.rar'} if self.browser_kind == 'episodes'
                      else set(ARCHIVE_SUFFIXES) if self.browser_kind == 'bulk' else set())
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
        paths = [Path(p).expanduser() for p in paths]
        # One .zip/.rar while no library is open is a bulk import (both games); with a library open, archives are
        # that library's episodes as before.
        if self.library is None and len(paths) == 1 and paths[0].suffix.lower() in ARCHIVE_SUFFIXES:
            self.start_bulk(paths[0], self.selected_game)
            return
        if getattr(self, 'screen', None) == 'bulk':
            raise ContentError('Choose the one .zip or .rar file that holds your games.')
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
        if (self.busy or self.main_exit_ms is not None and self.transition_source == 'main'
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
                if release is not None and kind == 'update_yes' and self.can_quit:
                    # Yes: the release page in the browser, then the game closes as it would from the window's close
                    # button (run() ends and close() checkpoints as usual).
                    self.open_url(release.url)
                    self.quit_requested = True
            elif kind == 'choose_game':
                self.choose_game(command[1])
            elif kind == 'bulk':
                self.show_bulk()
            elif kind == 'switch_games':
                self.switch_games()
            elif kind == 'episodes':
                self.scope, self.query = command[1], ''
                self.episode_scroll = self.scroll = 0
                self.refresh_saves()
                if self.picker_available():
                    self.ensure_picker().enter(self.state.selected)
                    self.show('picker')
                else:
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
                self.start(resume=command[1])
            elif kind == 'project':
                self.open_url(PROJECT_URL)
            elif kind == 'toggle_updates':
                self.set_update_check(not self.settings.check_for_updates)
            elif kind == 'toggle':
                key = command[1]
                if key not in ('music', 'sound', 'vibration', 'choice_hints', 'skip_minigames', 'skip_ad_intros',
                               'autoplay', 'disable_choice_timer'):
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
                    self.game.skip_minigames = self.state.skip_minigames
                    self.game.skip_ad_intros = self.state.skip_ad_intros
                    self.game.autoplay = self.state.autoplay
                    self.game.disable_choice_timer = self.state.disable_choice_timer
                    self.game._sync_music()
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
                    had_library = self.library is not None
                    self.open_library(self.folder, remember=True)
                    if had_library and self.shell is not None and self.screen == 'main':
                        self.shell.arrive()
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
                elif kind in ('staged', 'bulk'):
                    self._open_staged(result)
                elif kind == 'previews':
                    self.picker, self.transition_age = None, 200
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
                    self.picker = None
                    self.show('main' if self.shell is not None else 'episodes', remember=False)
                    self.message = f'Added {result} episodes.' if result else 'Library updated. No new episodes were added.'
                    self.prepare_previews()
            except ERRORS as error:
                self.message = str(error)
        self.flush_drops()
        if self.settings.check_for_updates:
            available = self.updates.poll()
            if (available is not None and self.update_prompt is None and self.active
                    and not self.busy and not self.message and self.ready
                    and self.screen in ('games', 'setup', 'bulk', 'main') and self.shell_idle()):
                self.update_prompt = available
                self.cancel_pointer()
                self.focus, self.focus_index = None, 0
                self.buttons = []
                pygame.key.stop_text_input()
        if not self.active or self.busy or self.message or self.update_prompt is not None:
            return
        if self.screen == 'game':
            self.game.tick(elapsed)
            self.autosave_age += elapsed
            if self.autosave_age > AUTOSAVE_MS:                            # SHSEngine::onTick, in the playing mode
                self.autosave()
            if self.game.session.episode_exited:
                self.return_to_menu()
        else:
            if self.main_exit_ms is not None:
                self.main_exit_ms += elapsed
                if self.main_exit_ms >= 2050:
                    self.main_exit_ms = None
            # Android recreates the main rows in the submenu's 400 ms exit
            # callback. Its entry clock starts only after that callback.
            delay = (max(0, self.transition_duration - self.transition_age)
                     if self.screen == 'main' and self.shell is None and self.transition_from is not None
                     and getattr(self.library, 'kind', 'apk') == 'apk' else 0)
            self.menu_age += max(0, elapsed - delay)
            self.transition_age = min(self.transition_duration, self.transition_age + elapsed)
            if self.shell is not None and self.screen == 'main':
                self.shell.tick(elapsed / 1000)
            elif self.picker_over_menu():
                self.picker_zoom = min(PAUSE_OPEN_MS, self.picker_zoom + elapsed)
                self.shell.tick(elapsed / 1000)                # the buttons sliding out behind it

    def render_picker(self):
        picker = self.ensure_picker(self.picker_style)
        picker.saved = self.saved
        pending = picker.alert
        if self.message:
            picker.alert = (self.game_title, self.message)
        live = self.picker_over_menu()
        canvas = picker.draw(backdrop=not live)
        picker.alert = pending
        if self.shell is not None and self.shell.overlay_active:
            self.shell.draw_overlay(canvas)
        if live:
            menu = self.shell.render().copy()
            if menu.get_size() != canvas.get_size():
                menu = pygame.transform.smoothscale(menu, canvas.get_size())
            scale = pause_scale(self.picker_zoom)
            if scale < 1:
                size = tuple(max(1, round(length * scale)) for length in canvas.get_size())
                canvas = pygame.transform.smoothscale(canvas, size)
            menu.blit(canvas, canvas.get_rect(center=menu.get_rect().center))
            canvas = menu
        self.present_frame(canvas)
        pygame.display.flip()

    def render(self):
        self._sync_menu_music()
        self._fade_menu_music()
        if self.screen == 'game':
            if self.game.session.episode_exited:
                self.return_to_menu()
            else:
                self.game.render()
                return
        if self.screen == 'picker' and not self.busy:
            self.render_picker()
            return
        if self.screen == 'main' and self.shell is not None:
            self.render_shell()
            return
        canvas = self.renderer.draw(self)
        if (self.transition_from is not None and self.transition_age < self.transition_duration
                and not self.message and not self.busy and self.update_prompt is None):
            if (self.library and self.transition_layer is not None
                    and getattr(self.renderer, 'layer', None) is not None):
                canvas = self._menu_transition()
            else:
                layer = canvas.copy()
                layer.set_alpha(round(255 * self.transition_age / self.transition_duration))
                canvas = self.transition_from.copy()
                canvas.blit(layer, (0, 0))
        self.buttons = self.renderer.buttons if self.ready or self.message or self.update_prompt else []
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
        """exp-runtime v0.6.0's recovered submenu transitions: iOS zooms or slides (UIKit ease, 400 ms); Android's
        submenus zoom from or slide over the departing main rows."""
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
            if event.type == pygame.WINDOWFOCUSLOST and self.screen == 'game':
                self.autosave(screenshot=True, only_if_unsaved=True)      # applicationWillResignActive: -> SHSEngine::onExit
            self._sync_menu_music()
        if (self.screen != 'game' and self.main_exit_ms is not None and self.transition_source == 'main'
                and self.transition_age < self.transition_duration):
            return True                     # the Android main rows are still leaving (exp-runtime v0.6.0)
        if self.screen == 'game':
            return self.game.handle_event(event)
        if self.update_prompt is not None:
            if self.screen == 'main' and self.shell is not None:
                # The HD menus' prompt (render_shell): its two buttons, in frame points. Keys mean No, as the SD
                # prompt's Escape and initial Enter do (docs/MAIN_MENU.md); only a click on Yes opens the page.
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                    self.command(('update_no',))
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    point = self.picker_point(event.pos)
                    hit = next((command for rect, command in self.shell_prompt if rect.collidepoint(point)), None)
                    if hit is not None:
                        self.command(hit)
                return True
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
            if self.screen == 'picker' and self.picker and (self.picker.popup or self.picker.alert) and not self.message:
                self.picker.popup = self.picker.alert = self.picker.pressed = None
            else:
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
        if self.screen == 'picker':
            return self.picker_event(event)
        if self.screen == 'main' and self.shell is not None:
            return self.shell_event(event)
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

    def picker_point(self, position):
        return ((position[0] - self.viewport.x) * PICKER_FRAME[0] / self.viewport.width,
                (position[1] - self.viewport.y) * PICKER_FRAME[1] / self.viewport.height)

    def picker_event(self, event):
        picker = self.ensure_picker(self.picker_style)
        command = None
        if self.shell is not None and self.shell.overlay_active:
            return self.shell_event(event)
        if event.type == pygame.KEYDOWN:
            command = picker.key(event.key)
        elif event.type == pygame.MOUSEWHEEL:
            picker.wheel(event.x, event.y, self.picker_point(pygame.mouse.get_pos()))
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            picker.pointer_down(self.picker_point(event.pos))
        elif event.type == pygame.MOUSEMOTION and event.buttons[0]:
            picker.pointer_move(self.picker_point(event.pos))
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            command = picker.pointer_up(self.picker_point(event.pos))
        if command is not None:
            self._click_sound()
            self._attempt(lambda: self.picker_command(command))
        return True

    def picker_command(self, command):
        picker, kind = self.picker, command[0]
        if kind == 'back':
            self.back()
        elif kind == 'restore':
            picker.alert = picker.restore_alert()
        elif kind == 'dismiss':
            picker.alert = None
        elif kind == 'info':
            # The episode info card (this fork; an imported CoD store listing).
            info = picker.model.info(picker.model.by_id[command[1]])
            if info is not None:
                picker.alert = info
        elif kind == 'close':
            picker.popup = None
        elif kind == 'tile':
            picker.selected = command[1]
            record = picker.model.by_id[command[1]]
            if command[1] in self.saved:
                picker.popup = record
                # Opened from the keyboard: Continue starts highlighted (the popup's own keys move it).
                picker.popup_focus = ('continue', command[1]) if picker.keyboard else None
            else:
                self.selected = command[1]
                self.start(resume=False)
        elif kind == 'new' and self.shell is not None and command[1] in self.saved:
            record = picker.model.by_id[command[1]]
            picker.popup = None
            self.selected = command[1]
            self.shell.confirm_new_game(picker.model.label(record), lambda: self.start(resume=False))
        elif kind in ('new', 'continue'):
            picker.popup = None
            self.selected = command[1]
            self.start(resume=kind == 'continue')
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
                self.state.checkpoint(self.game.session)
                self.save_screenshot()
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
                    running = self.handle_event(event) and not self.quit_requested
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
    parser = argparse.ArgumentParser(description=f'{APP_NAME} — play SHS or Cause of Death with your own assets')
    parser.add_argument('--library', type=Path, help='Local content library (default: per-user application data)')
    parser.add_argument('--game', choices=GAMES, default='shs',
                        help='The game to open (default: shs)')
    parser.add_argument('--game-library', nargs=2, action='append', default=[], metavar=('GAME', 'PATH'),
                        help="A game's library for Switch Game, not remembered (repeatable; this fork's option)")
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
    unknown = [key for key, _ in args.game_library if key not in GAMES]
    if unknown:
        parser.error(f'unknown game for --game-library: {unknown[0]}')
    Application(args.library, audio=not args.no_audio, game_key=args.game,
                game_libraries=dict(args.game_library)).run()


if __name__ == '__main__':
    main()
