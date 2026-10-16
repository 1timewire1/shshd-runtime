"""Cause of Death's launch flow and main menu: SHS HD's (`application_hd.HdShell`) on CoD's own menu engine.

CoD's menu engine (logical resource 15, strings in bank 13) has SHS HD's windows under other numbers; this shell keeps
HdShell's flow and translates them (owner's choice, 2026-10-14: every CoD menu in SHS HD's layout, CoD's style).

| Window | SHS HD | CoD |
| --- | --- | --- |
| Play with sound? / Continue playing your music? | 7 / 8 | 7 / 8 |
| Privacy Policy / EULA / Terms | 16 | 15 (its usage-sharing rows are two conditional items, not a ~275~ label) |
| Exit Game? | 17 | 16 |
| Disable / Enable Usage Sharing | 19 / 20 | 18 / 19 |
| Delete Saved Game? | 12 (~277~) | 52 (~260~) |
| Connection Error (no longer reached: More EA Games is Switch Game) | 41 | 38 |
| Want More Content? / Miss An Episode? | 23 / 24 | 22 / 23 |

Engine actions (`doMenuEngineAction`): CoD's 0-4 are SHS HD's (sound answers); 21 / 22 / 23 open the EULA / privacy /
terms links (strings 201 / 202 / 200; SHS HD's 14 / 15 / 16); 24 is Exit Game's Yes (SHS HD 18); 26 / 27 disable /
enable usage sharing (19 / 20); 28 / 29 / 30 / 31 / 32 are the end menus' Now Airing / Episodes On Demand / More EA
Games / Main Menu / Replay (21 / 22 / 23 / 24 / 25); 36 is Delete Saved Game's Yes (10). 25 closes the window (9) and,
outside the end menu, so does 31.

Differences from SHS HD's flow: the launch screen is CoD's own (`desktop_cod_main.CodBootScreen`) and the answer goes
through black to the main menu, which slowly fades in (no EA flash; timings below); Play/Resume, Now Airing and Episodes On Demand (the main menu's and the end
menus') open SHS HD's pickers in CoD's dress (`desktop_cod_episodes.py`), or the plain episode browser when the
library has no SHS HD art source. "More EA Games" (main menu, and end-menu action 30) is Switch Game, as in SHS HD.
"""
from types import SimpleNamespace

from .application_hd import HdShell
from .desktop_cod_main import CodBootScreen, CodMainMenu
from .desktop_cod_menu import CodMenuWindows
from .desktop_cod_pause import CodPauseMenu
from .menu_engine import MenuEngineData, MenuStack
from .ui_assets import LayoutBank, read_ui

ACTIONS = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 21: 14, 22: 15, 23: 16, 24: 18, 25: 9, 26: 19, 27: 20,
           28: 21, 29: 22, 30: 23, 32: 25, 36: 10}
MAIN_MENU = 31
SCOPES = {'play': 'play', 'airing': 'weekly', 'demand': 'all'}
END_BROWSER = {28: 'weekly', 29: 'all'}             # end menu: Now Airing / Episodes On Demand
ENGINE_RESOURCES, UI_RESOURCES = (13, 15, 16), (6, 14, 272, 532, 533)
# CoD 1.4.7's way from the EA screen to the main menu (SHS HD's flash code with no flare): `setAppMode(102)` (00022cd4)
# adds a black layer that fades in (opacity 0 -> 1) over 1.0 s, beginning 1.0 s later. When it stops
# (`SHSAnimationDelegate animationDidStop:finished:` 00017388, "flash-all-white") the main menu is set up
# (`setAppMode(101)`) and the black fades out over 1.0 s from 0.2 s on; the buttons slide in from 1.5 s
# (`animateMainMenuButtonsIn(1.5)`, desktop_cod_main.BUTTONS_START_INTRO).
BLACK_HOLD, BLACK_FADE, REVEAL_DELAY = 1.0, 1.0, 0.2


class CodShell(HdShell):
    PRIVACY_MENU, LEAVE_MENU, DISABLE_MENU, ENABLE_MENU = 15, 16, 18, 19
    DELETE_MENU, CONNECTION_MENU, END_MENU, MISS_MENU = 52, 38, 22, 23
    URLS = {14: 201, 15: 202, 16: 200}

    def __init__(self, app):
        self.app = app
        library = app.library
        self.library = library
        art = app.renderer.art
        bank = LayoutBank.parse(read_ui(library, 14))
        self.boot = CodBootScreen(library)
        self.main = CodMainMenu(library, bank)
        self.data = MenuEngineData(library.android_asset(15))
        self.windows = CodMenuWindows(library, self.data, art, logging_disabled=lambda: app.state.logging_disabled)
        self.stack = MenuStack(self.data, self.perform)
        self.main.backdrop_enabled = lambda: app.state.hd_backdrop
        self.pause = CodPauseMenu(SimpleNamespace(library=library), art)
        self.pause.main_menu = True
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

    @staticmethod
    def available(library):
        """A CoD library with what the shell reads: the menu engine (15), its strings (13), the window art (16), the
        title painting (6), the layout bank (14), the button pack (272) and the label fonts (532 / 533)."""
        if getattr(library, 'game_id', None) != 'cod':
            return False
        try:
            for resource in ENGINE_RESOURCES:
                library.android_asset(resource)
            for role in UI_RESOURCES:
                read_ui(library, role)
        except Exception:
            return False
        return True

    def arrive(self):
        """From black (after the EA screen, or another game): the main menu, slowly fading in. CoD has no EA flash."""
        self.stack.clear()
        self.pause_open = False
        self.enter_main(intro=True)
        self.fade = ('in', -REVEAL_DELAY, None, BLACK_FADE)

    def backdrop_available(self):
        """The "SHS HD Backdrop" switch shows when the SHS HD art source can supply the collage."""
        from .desktop_cod_main import hd_collage
        return hd_collage(self.library) is not None

    def variables(self):
        return {'260': self.pending_title or ''}

    def activate(self, command):
        kind = command[0]
        if kind in SCOPES and not self.app.picker_available():
            self.app.command(('episodes', SCOPES[kind]))             # no SHS HD art source: the plain browser
            return
        super().activate(command)

    def perform(self, number):
        """CoD's `doMenuEngineAction` numbers, run through HdShell's (see the table above)."""
        if number == 1:                   # the sound answer is in: no EA flash; the EA screen fades to black, then the menu
            self.stack.clear()
            self.leave(self.arrive, hold=BLACK_HOLD, time=BLACK_FADE)
            return
        if number == MAIN_MENU and self.stage != 'end':
            self.stack.clear()
            return
        if number in END_BROWSER and not self.app.picker_available():    # no SHS HD art source: the browser
            self.stack.clear()
            self.app.leave_end_menu()
            self.app.command(('episodes', END_BROWSER[number]))
            return
        if number == MAIN_MENU:
            number = 24
        else:
            number = ACTIONS.get(number)
            if number is None:
                return
        super().perform(number)
