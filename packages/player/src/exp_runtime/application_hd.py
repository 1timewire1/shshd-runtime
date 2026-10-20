"""The HD launch flow and main menu: boot screens, the sound question, the main menu, Help & About, Options, the legal
windows and the end-of-episode menu, driven by the app's menu engine data (resource 17).

`HdShell` owns the screens (frame points, 768 x 1024) and asks the application for what only it can do (opening the
episode picker, starting an episode, playing a sound, opening a link). Coordinates in and out are frame points.

Stages: `loading` (the EA loading screen), `sound` (menu 7 over it), `flash` (the EA flash), `main`, `end` (the menu shown
when an episode ends: 23 "Want More Content?" after Football Season, else 24 "Miss An Episode?"). Windows of the menu
engine (`stack`) and the pause menu's Options / Help pages (`pause`, drawn by desktop_pause_hd.py) open over `main`.

"More EA Games" (the main menu's fourth button, and the end menus' row, engine action 23) is upstream's Switch Game
(`Application.switch_games`) instead of EA's store page, labelled with the other game's title (owner's choice,
2026-10-14). The native Connection Error window (menu 41) is no longer reached.
"""
from types import SimpleNamespace
import webbrowser

import pygame

from .desktop_boot_hd import FLASH_TOTAL, HdBootScreen, JINGLE, LOADING_TIME
from .desktop_hd_menu import HdMenuWindows
from .desktop_main_hd import HdMainMenu
from .desktop_pause import PAUSE_OPEN_MS, pause_scale
from .desktop_pause_hd import HdPauseMenu, MAIN_HELP_ORDER, PAGES
from .hd_ui import S, FRAME
from .languages import TITLE_LANGUAGES

# The fade to black before a game switch: this player's own (owner's choice). CoD's from its EA screen to its menu, and
# in from black after, are decompiled and timed in application_cod.py.
FADE_TIME = 0.5
# A frame that opens a library (a game switch) lasts about half a second, which would otherwise skip a whole fade or
# flash in one step: a step longer than HITCH counts as MAX_STEP. Ordinary frames, however slow (a full-screen window
# scaling SHS HD's intro can take 100+ ms a frame), count in full, so animations keep their real duration.
HITCH, MAX_STEP = 0.25, 1 / 20
from .menu_engine import MenuEngineData, MenuStack

SOUND_MENU, MUSIC_MENU = 7, 8
PRIVACY_MENU, LEAVE_MENU, DISABLE_MENU, ENABLE_MENU = 16, 17, 19, 20
DELETE_MENU, CONNECTION_MENU = 12, 41
END_MENU, MISS_MENU = 23, 24
SOUND_DELAY = 0.3                 # seconds the finished loading screen shows before the question
URLS = {14: 204, 15: 205, 16: 203}        # engine actions 14 / 15 / 16 -> the string holding the EULA / privacy / terms link
SETTLE = 0.05


class HdShell:
    # The menu engine's window ids and link strings (SHS HD's resource 17); `application_cod.CodShell` names CoD's.
    SOUND_MENU, MUSIC_MENU, PRIVACY_MENU, LEAVE_MENU = SOUND_MENU, MUSIC_MENU, PRIVACY_MENU, LEAVE_MENU
    DISABLE_MENU, ENABLE_MENU, DELETE_MENU, CONNECTION_MENU = DISABLE_MENU, ENABLE_MENU, DELETE_MENU, CONNECTION_MENU
    END_MENU, MISS_MENU, URLS = END_MENU, MISS_MENU, URLS

    def __init__(self, app):
        self.app = app
        library = app.library
        self.library = library
        self.boot = HdBootScreen(library)
        self.main = HdMainMenu(library)
        self.data = MenuEngineData(library.hd_raw_resource(17))
        self.windows = HdMenuWindows(library, self.data, app.renderer.art)
        self.stack = MenuStack(self.data, self.perform)
        self.pause = HdPauseMenu(SimpleNamespace(library=library))
        self.pause.main_menu = True
        self.main.backdrop_enabled = lambda: app.state.hd_backdrop
        self.stage = 'loading'
        self.age = 0.0
        self.flash_age = 0.0
        self.pause_open = False
        self.pressed = None
        self.link = ''
        self.pending_yes = None
        self.end_backdrop = None
        self.body_scroll = 0.0
        self.drag = None
        self.silent = False
        self.fade = None                # ('out', seconds, then, time) to black, or ('in', seconds, None, time) from it
        self.flash_over_black = False   # the flash after a game switch starts from black, not the loading screen

    # ------------------------------------------------------------ availability

    @staticmethod
    def available(library):
        return HdBootScreen.available(library) and HdMainMenu.available(library)

    # ------------------------------------------------------------ flow

    def set_switch_title(self, title):
        """Label the Switch Game buttons (main menu, end menus) with the other game's title."""
        self.main.switch_title = self.windows.switch_title = title

    def begin(self):
        """Start the launch flow: the loading screen, then the sound question."""
        self.stage, self.age, self.flash_age = 'loading', 0.0, 0.0
        self.stack.clear()
        self.pause_open = False
        self.pause.reset()

    def enter_main(self, *, intro=False):
        if intro:
            self.app.play_menu_music()          # the first arrival at the main menu
        self.stage = 'main'
        self.stack.clear()
        self.pause_open = False
        self.pause.reset()
        self.main.start(intro=intro)

    def zoom_out(self, box):
        self.leaving = (pygame.transform.smoothscale(box, (FRAME[0] * S, FRAME[1] * S)), 0.0)
        self.replay_launch()

    def replay_launch(self):
        """Back from an episode's Main Menu row: the main menu's first-launch entrance from the photo animation on
        (`HdMainMenu.start(intro=True)`), without the EA flash or its jingle (owner, on the device, 2026-10-20)."""
        self.main.start(intro=True)

    def show_end_menu(self, backdrop, football):
        """The menu shown when an episode ends, over `backdrop` (the last frame, already sepia, as a 768 x 1024 surface)."""
        self.stage = 'end'
        self.end_backdrop = pygame.transform.smoothscale(backdrop, (FRAME[0] * S, FRAME[1] * S))
        self.stack.clear()
        self.stack.queue(self.END_MENU if football else self.MISS_MENU)

    @property
    def overlay_active(self):
        """Whether a menu-engine window is open (over the main menu, the picker or the end-of-episode scene)."""
        return bool(self.stack.stack)

    @property
    def fading(self):
        return self.fade is not None

    @property
    def loaded(self):
        """The launch's loading screen has run its course (what follows is "Play with sound?", unless the update
        offer comes first: Application.update_holds_launch)."""
        return self.stage == 'loading' and self.age >= LOADING_TIME + SOUND_DELAY

    def leave(self, then, *, hold=0.0, time=FADE_TIME):
        """Fade the screen to black over `time` after `hold` seconds, then call `then` (a game switch, or CoD's way
        from its EA screen to its menu). A fade's age starts at minus its hold, so the frame stays as it is until 0."""
        self.pressed = self.drag = None
        self.fade = ('out', -hold, then, time)

    def arrive(self):
        """Arriving from another game (the frame is black): SHS HD's flash, with its jingle, into the main menu."""
        self.stack.clear()
        self.pause_open = False
        self.stage, self.flash_age, self.flash_over_black = 'flash', 0.0, True
        self.app.play_asset(JINGLE)

    def tick(self, seconds):
        if seconds > HITCH:
            seconds = MAX_STEP
        if self.fade is not None:
            kind, age, then, time = self.fade
            age += seconds
            if age >= time:
                self.fade = None
                if kind == 'out':
                    then()                  # may replace this shell (a game switch): nothing more to do here
                    return
            else:
                self.fade = (kind, age, then, time)
        self.age += seconds
        if self.pause_open:
            self.pause_ms = min(PAUSE_OPEN_MS, self.pause_ms + seconds * 1000)
            self.pause.advance(seconds * 1000)          # a page sliding in or out (its buttons wait for it)
        if self.leaving is not None:
            box, ms = self.leaving
            ms += seconds * 1000
            self.leaving = (box, ms) if ms < PAUSE_OPEN_MS else None
        if self.stack.stack:
            self.window_ms = min(PAUSE_OPEN_MS, self.window_ms + seconds * 1000)
        covered = self.overlay_active or self.pause_open
        if self.stage == 'main' and self.was_covered and not covered:
            self.main.start(intro=False)          # the buttons slide in again when a window closes
        self.was_covered = covered
        if (self.stage == 'loading' and self.age >= LOADING_TIME + SOUND_DELAY
                and not self.app.update_holds_launch(self.age - LOADING_TIME - SOUND_DELAY)):
            self.stage = 'sound'
            self.stack.queue(self.MUSIC_MENU if self.app.external_music() else self.SOUND_MENU)
            self.window_ms = 0
        elif self.stage == 'flash':
            self.flash_age += seconds
            if self.boot.flash_done(self.flash_age):
                self.enter_main(intro=True)
        elif self.stage == 'main' and not self.overlay_active and not self.pause_open:
            self.main.tick(seconds)
        elif self.stage == 'main':
            self.main.tick(seconds)         # the buttons keep sliding in behind an opened window

    # ------------------------------------------------------------ settings shown by the pause menu's pages

    def settings(self):
        state = self.app.state
        settings = dict(music=state.music, sound=state.sound, music_volume=state.music_volume / 100,
                        sound_volume=state.sound_volume / 100, choice_hints=state.choice_hints,
                        skip_minigames=state.skip_minigames, skip_ad_intros=state.skip_ad_intros)
        if self.backdrop_available():
            settings['hd_backdrop'] = state.hd_backdrop
        if self.translated_titles():
            settings['title_language'] = self.language_name(state.title_language)
        settings['add_episodes'] = settings['open_library'] = True
        settings['check_updates'] = self.app.settings.check_for_updates
        return settings

    def translated_titles(self):
        """Whether any episode has a title in another language, so the Episode Titles button changes something."""
        if self._translated is None:
            self._translated = any(len(set(record['titles'])) > 1 for record in self.library.episodes)
        return self._translated

    _translated = None

    def language_name(self, language):
        """A title language's name from the game's own menu strings (SD's 118-122), else its code."""
        try:
            return self.app.renderer.strings[118 + TITLE_LANGUAGES.index(language)]
        except (AttributeError, IndexError, KeyError, TypeError, ValueError):
            return language

    def backdrop_available(self):
        """Whether the "SHS HD Backdrop" switch has a backdrop to show: SHS HD's own collage (resource 10)."""
        return True

    def set_volume(self, which, value):
        value = min(1.0, max(0.0, value))
        state = self.app.state
        key = 'music_volume' if which == 'music' else 'sound_volume'
        changed = round(value * 100) != getattr(state, key)
        setattr(state, key, round(value * 100))
        state.persist()
        self.app.menu_music_changed()
        if changed:
            # `SHSWidgetMenu::sliderChanged` previews (ui_sound.py), as in the pause menu (desktop.Desktop._set_volume).
            if which == 'music' and state.music and value > 0:
                self.app.ui_sound('MUSIC_SLIDER_SOUND', volume=value, when_idle=True)
            elif which != 'music':
                self.app.ui_sound('SOUND_SLIDER_SOUND', when_idle=True)

    def toggle(self, which):
        if which == 'check_updates':
            self.app.set_update_check(not self.app.settings.check_for_updates)
            return
        state = self.app.state
        setattr(state, which, not getattr(state, which))
        state.persist()
        self.app.menu_music_changed()
        if which == 'sound' and state.sound:
            # `SHSEngine::setSoundEnabled(true, true)`: the switch's own sound, other effects stopped.
            self.app.ui_sound('SOUND_ON_SOUND', stop_others=True)

    # ------------------------------------------------------------ rendering

    def render(self):
        """The current screen as a 2x canvas."""
        if self.stage in ('loading', 'sound'):
            canvas = self.boot.draw_loading(min(1.0, self.age / LOADING_TIME))
        elif self.stage == 'flash':
            canvas = self.boot.draw_flash(self.flash_age, over_black=self.flash_over_black)
            self.draw_leaving(canvas)
            self.draw_fade(canvas)
            return canvas
        elif self.stage == 'end':
            canvas = self.boot.canvas
            canvas.blit(self.end_backdrop, (0, 0))
        else:
            self.main.pressed = self.pressed if self.pressed and self.pressed[0] in ('play', 'airing', 'demand', 'more', 'options', 'help') else None
            # The buttons also show while they slide out under a window that has just opened.
            leaving = self.main.leaving is not None and not self.main.left
            canvas = self.main.draw(buttons=leaving or not (self.overlay_active or self.pause_open))
        self.draw_overlay(canvas)
        if self.stage == 'main':
            self.draw_leaving(canvas)
        self.draw_fade(canvas)
        return canvas

    def draw_leaving(self, canvas):
        """The in-game pause menu's box zooming out (`zoom_out`)."""
        if self.leaving is not None:
            box, ms = self.leaving
            scale = pause_scale(PAUSE_OPEN_MS - ms)
            box = pygame.transform.smoothscale(box, tuple(max(1, round(length * scale)) for length in box.get_size()))
            canvas.blit(box, box.get_rect(center=canvas.get_rect().center))

    def fade_level(self):
        """How far the frame is faded to black, 0..1. Only the frame fades: the backdrop beside it stays (owner)."""
        if self.fade is None:
            return 0.0
        kind, age, _, time = self.fade
        t = min(1.0, max(0.0, age) / time)
        return t if kind == 'out' else 1 - t

    def draw_fade(self, canvas):
        level = self.fade_level()
        if level > 0:
            keep = round(255 * (1 - level))
            canvas.fill((keep, keep, keep), special_flags=pygame.BLEND_RGB_MULT)

    def draw_overlay(self, canvas):
        """The open menu-engine window, or the pause menu's Options / Help page, over `canvas`."""
        self.windows.hits = []
        if self.stack.stack:
            current = self.stack.current
            scale = pause_scale(self.window_ms)
            if scale >= 1:
                self.windows.draw(canvas, current, variables=self.variables(), pressed=self.pressed,
                                  body_scroll=self.body_scroll)
                return
            layer = pygame.Surface(canvas.get_size(), pygame.SRCALPHA).convert_alpha()
            self.windows.draw(layer, current, variables=self.variables(), pressed=self.pressed,
                              body_scroll=self.body_scroll)
            size = tuple(max(1, round(length * scale)) for length in layer.get_size())
            layer = pygame.transform.smoothscale(layer, size)
            canvas.blit(layer, layer.get_rect(center=canvas.get_rect().center))
        elif self.pause_open and self.stage == 'main':
            self.pause.pressed = self.pressed
            layer, self.pause_buttons = self.pause.layout(self.settings())
            scale = pause_scale(self.pause_ms)
            size = tuple(max(1, round(length * scale)) for length in layer.get_size())
            if size != layer.get_size():
                layer = pygame.transform.smoothscale(layer, size)
            canvas.blit(layer, layer.get_rect(center=canvas.get_rect().center))

    def variables(self):
        strings = self.windows.strings()
        return {'275': strings[173 if self.app.state.logging_disabled else 172],
                '277': self.pending_title or ''}

    pending_title = ''
    was_covered = False
    # Defaults for shells built by their own constructor (CodShell's): no fade, a launch flash over the loading screen.
    fade = None
    flash_over_black = False
    pause_buttons = ()
    pause_ms = PAUSE_OPEN_MS
    leaving = None
    window_ms = PAUSE_OPEN_MS

    # ------------------------------------------------------------ input (frame points)

    def hits(self):
        if self.fade is not None or self.leaving is not None:
            return []                   # nothing takes input while the screen fades or the pause box zooms out
        if self.stack.stack:
            return self.windows.hits if self.window_ms >= PAUSE_OPEN_MS else []
        if self.pause_open and self.stage == 'main':
            if self.pause_ms < PAUSE_OPEN_MS:
                return []
            return [(rect, command) for rect, command in self.pause_buttons]
        return self.main.hits if self.stage == 'main' and self.main.ready else []

    def pointer_down(self, point):
        self.pressed = None
        for rect, command in reversed(self.hits()):
            if rect.collidepoint(point):
                self.pressed = command
                if command[0] == 'pause_slider':
                    self.drag = ('slider', command[1])
                    self.set_volume(command[1], (point[0] - 143) / 460)
                elif command[0] == 'pause_scroll':
                    self.drag = ('scroll', self.pause.state.scroll, point[1])
                return

    def pointer_move(self, point):
        if self.drag is None:
            return
        if self.drag[0] == 'slider':
            self.set_volume(self.drag[1], (point[0] - 143) / 460)
        elif self.drag[0] == 'scroll':
            state = self.pause.state
            state.scroll = min(state.max_scroll, max(0.0, self.drag[1] - (point[1] - self.drag[2])))

    def pointer_up(self, point):
        pressed, self.pressed, drag, self.drag = self.pressed, None, self.drag, None
        if pressed is None or drag is not None:
            return
        for rect, command in reversed(self.hits()):
            if rect.collidepoint(point) and command == pressed:
                self.activate(command)
                return

    def wheel(self, dy):
        if self.pause_open and self.stage == 'main':
            state = self.pause.state
            state.scroll = min(state.max_scroll, max(0.0, state.scroll - dy * 40))
        elif self.stack.stack and self.windows.body_rect is not None:
            limit = max(0.0, self.windows.body_height - self.windows.body_rect.height + 30)
            self.body_scroll = min(limit, max(0.0, self.body_scroll - dy * 40))

    def back(self):
        """Escape / back: close the topmost window or page. Returns whether anything was open."""
        if self.fade is not None:
            return True
        if self.stack.stack:
            self.close_window()
            return True
        if self.pause_open:
            if self.pause.back():
                self.pause_open = False
            return True
        return False

    def close_window(self):
        if self.stage == 'sound':
            return                       # the question has to be answered
        self.stack.pop()
        self.body_scroll = 0.0
        if self.stage == 'end' and not self.stack.stack:
            self.app.leave_end_menu()

    # ------------------------------------------------------------ commands

    MAIN_OPTIONS = ('play', 'airing', 'demand', 'more', 'options', 'help')

    def activate(self, command):
        kind = command[0]
        if kind in self.MAIN_OPTIONS and self.stage == 'main' and not (self.overlay_active or self.pause_open):
            self.main.leave()           # `animateMainMenuButtonsOut(0)`, under whatever opens
        if kind in ('play', 'airing', 'demand'):
            style = {'demand': 'list', 'airing': 'airing'}.get(kind, 'tile')
            self.app.open_picker(restore=kind == 'play', style=style)
        elif kind == 'more':
            self.app.command(('switch_games',))         # upstream's Switch Game, in place of EA's store page
        elif kind == 'options':
            self.pause.reset()
            self.pause.state.screen, self.pause_open, self.pause_ms = 'options', True, 0
        elif kind == 'help':
            self.pause.reset()
            self.pause.state.screen, self.pause_open, self.pause_ms = 'help', True, 0
        elif kind == 'item':
            self.body_scroll = 0.0
            self.stack.press(self.data.action(command[1]))
        elif kind == 'pause_open':
            if command[1] == 'privacy':
                self.stack.queue(self.PRIVACY_MENU)
            else:
                self.pause.open(command[1])
        elif kind == 'pause_back':
            if self.pause.back():
                self.pause_open = False
        elif kind == 'pause_toggle':
            self.toggle(command[1])
        elif kind == 'pause_cycle' and command[1] == 'title_language':
            state = self.app.state
            state.title_language = TITLE_LANGUAGES[(TITLE_LANGUAGES.index(state.title_language) + 1)
                                                   % len(TITLE_LANGUAGES)]
            state.persist()
            self.app.picker = None                      # the pickers' captions follow the language
        elif kind == 'pause_action' and command[1] == 'add_episodes':
            self.app.command(('browse', 'episodes'))
        elif kind == 'pause_action' and command[1] == 'open_library':
            self.app.command(('browse', 'library'))
        elif kind == 'pause_link':
            # Not a native row (EULA/Privacy/Terms are full menu rows, never an inline link in a text page's own
            # body) -- a link inside override text (`help_text_overrides.py`) reuses the app's own "Exit Game?"
            # confirmation (menu 17, title/body strings 93/94) exactly the way those rows do: action 18 behind
            # its own Yes button already opens whatever `self.link` holds.
            self.link = command[1]
            self.stack.queue(self.LEAVE_MENU)

    def perform(self, number):
        """`SHSEngine::doMenuEngineAction` for the actions the menus of this shell use."""
        state = self.app.state
        if number == 0:                                   # "Play with sound?" -> No
            state.music = state.sound = False
            state.persist()
        elif number in (2, 3):                            # Yes
            state.music = state.sound = True
            state.persist()
        elif number == 4:                                 # "Continue playing your music?" -> Yes: keep the other app's
            state.music, state.sound = False, True
            state.persist()
        elif number == 1:                                 # the answer is in: on to the EA flash
            self.stack.clear()
            self.stage, self.flash_age = 'flash', 0.0
            self.app.play_asset(JINGLE)
        elif number == 9:                                 # close every window
            self.stack.clear()
            if self.stage == 'end':
                self.app.leave_end_menu()
        elif number in self.URLS:                              # EULA / privacy policy / terms: remember the link, ask to leave
            self.link = self.windows.strings()[self.URLS[number]]
        elif number == 17:                                # usage sharing
            self.stack.queue(self.ENABLE_MENU if state.logging_disabled else self.DISABLE_MENU)
        elif number in (19, 20):
            state.logging_disabled = number == 19
            state.persist()
        elif number == 18:                                # "Exit Game?" -> Yes: open the link in the browser
            self.stack.clear()
            if self.link:
                self.app.open_url(self.link)
        elif number in (21, 22):                          # end menu: Now Airing / Episodes On Demand -> the picker
            self.stack.clear()
            self.app.leave_end_menu(picker=True, style='list' if number == 22 else 'airing')
        elif number == 23:                                # More EA Games -> Switch Game
            self.stack.clear()
            self.app.command(('switch_games',))
        elif number == 24:                                # Main Menu
            self.stack.clear()
            self.app.leave_end_menu()
        elif number == 25:                                # Replay
            self.stack.clear()
            self.app.leave_end_menu(replay=True)
        elif number == 10 and self.pending_yes is not None:    # Delete Saved Game? -> Yes
            callback, self.pending_yes = self.pending_yes, None
            self.stack.clear()
            callback()

    def confirm_new_game(self, title, callback):
        """Ask "Delete Saved Game?" before starting over an episode that has a save."""
        self.pending_title, self.pending_yes = title, callback
        self.stack.queue(self.DELETE_MENU)
