"""Shared gameplay frontend; all story decisions remain in the KiWi runtime."""
from collections import OrderedDict
from dataclasses import astuple
from io import BytesIO
from copy import deepcopy
import logging
import os
import random
import re
from types import SimpleNamespace
import webbrowser

os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
from .graphics import faded
from . import graphics as pygame

from .app_icon import set_window_icon
from .content import ContentError, presentation_feature
from .audio import music_cue
from .games import GAMES, game_id, has_translated_minigames
from .content import feature_pack, free_setting, pack_setting
from .desktop_text import BitmapTextRenderer
from .desktop_dialogue import DialogueRenderer
from .desktop_choice import ChoiceRenderer
from .desktop_pause import PAUSE_OPEN_MS, PauseRenderer, pause_scale
try:
    # SHS HD's football and word grid draw with SHS's own layout helpers (exp_runtime.shs), which a CoD-only install
    # lacks; CoD never plays either (tools/test_packages.py's cod-player case).
    from .desktop_football_hd import HdFootballRenderer
    from .desktop_word_hd import HdWordRenderer
    from .desktop_shs11_hd import Shs11HdRenderer
except ImportError:
    HdFootballRenderer = HdWordRenderer = Shs11HdRenderer = None
from .location_pan import LocationPan, default_ease
from .desktop_message_hd import CodMessageRenderer, HdMessageRenderer
from .desktop_nr_arena import NRArenaRenderer
from .desktop_nr_arena_x360 import X360ArenaRenderer
from .desktop_x360_diss import X360DissRenderer
from .desktop_x360_leash import X360LeashRenderer, drag_direction, stick_direction
from .desktop_cutscene import CutsceneRenderer
from .desktop_x360_puzzle import X360PuzzleRenderer, cell_at, on_board
from .desktop_x360_slot import X360SlotRenderer
from .desktop_shs11_memory import Shs11MemoryRenderer, memory_spec
from .desktop_brew_catch import BrewCatchRenderer
from .desktop_shs11_reflex import Shs11ReflexRenderer
from .gamepad import REPEAT_DELAY_MS, REPEAT_MS
from .x360_games import DOWN, LEFT, RIGHT, SHAKE_WINDOW_STICK_MS, UP
from .shs11_games import GAME_SOUNDS as SHS11_GAME_SOUNDS, GRID_SOUNDS, PLAY
from . import desktop_tree_zoom, frame_log, momentum, scene_fade
from .desktop_pause_hd import ASPECT_NAMES, CONFIRM_NAMES, GRID_CONTROLS_NAMES, HdPauseMenu, KEYS_ACTIVATE, focus_step
from . import backdrop_fit, frame_shape
from .desktop_hd_menu import HdMenuWindows
from .desktop_badge_hd import HdSceneBadge
from .ad_intro import has_links, play_option
from .hd_choice import SELECT_MS, TRANSITION_MS, panel_alpha
from .hd_ui import FRAME as HD_FRAME, S as HD_S
from .menu_engine import MenuEngineData, MenuEngineError, MenuStack
from .desktop_picker import CharacterPickerRenderer, CodCharacterPickerRenderer, HdCharacterPickerRenderer
from .animation_curves import ease_in_out
from .desktop_loading import HdLoadingRenderer, LOADING_CLOSE_MS, LoadingRenderer
from .desktop_message import MessageRenderer
from .desktop_panels import DTViewRenderer, FaceplacePanelRenderer
from .desktop_title import CodTitleRenderer, HdTitleRenderer, TitleRenderer
from .desktop_faceplace_alert import ALERT_SOUND as FACEPLACE_ALERT_SOUND, FaceplaceAlertRenderer
from .desktop_input import InputRenderer, INPUT_RECT
from .desktop_side_panels import SidePanels
from .dtview_faceplace import NOT_WARPABLE
from .fonts import TextStyle
from .loading import LoadingScreen
from .runtime import SaveError, Session
from .skip_ahead import can_skip, skip_ahead
from .undo import chain_for
from .minigames import MINIGAMES
from .choice_hints import ARENA_RESULTS, arena_outcomes, brew_catch_outcomes, shs11_outcomes, word_game_outcomes, x360_slot_outcomes
from .scene_badge import outline_badge_text
from .pointer import ButtonPress, step_focus
from .text_input import accept_name_character, validate_name
from .ui_sound import UiSounds
from .music_stream import FADE_MS, MusicStream
from .ui_assets import ImagePack, Rect
from .vibration import buzz_wav
from .vm import VMError


def _decoded_size(data: bytes) -> tuple[int, int]:
    if data.startswith((b'\x89PNG', b'\xff\xd8')):
        return pygame.image.load(BytesIO(data)).get_size()
    frame = ImagePack.parse(data).images[0]
    return frame.width, frame.height


SIZE = (480, 720)
# Pixels per logical unit for screens drawn at HD density (see DialogueRenderer.scale).
STORY_SCALE = 2
# HD's own main game view is a fixed 768x1024 (3:4) in every orientation --
# confirmed from SHSViewController::setupLocalInterfaceOrientation:, which
# only ever rotates that rectangle, never resizes it (see docs/UI_FIDELITY.md
# and legacy/findings.md's DTView/Faceplace layout section). The UI chrome
# below stays at SIZE's 2:3 (Android-authored, unchanged); only the initial
# window is wider so there's real room for the background layer to use it.
DEFAULT_WINDOW_SIZE = (round(SIZE[1] * 3 / 4), SIZE[1])
FRAME_UNITS = (384, 512)
HD_BG_SHIFT = (48, -20.5)
UI_BOTTOM_INSET = 5.5
INK = (245, 241, 233)
MUTED = (183, 187, 198)
ACCENT = (247, 190, 94)
PANEL = (23, 29, 45)
# shshd-runtime: a tap on a dialogue line or page in its first CONTINUE_GUARD_MS is ignored, so a double click or tap
# that advanced the last line does not also finish (or skip) the next one (owner, 2026-10-25; this player's own).
CONTINUE_GUARD_MS = 250


# Links a browser can open (an App Store link's itms:// becomes its web page in _offer_link).
WEB_LINK = re.compile(r'(https?|itms(-apps)?)://', re.I)


OPAQUE_ENOUGH = 250


def frame_wide(size):
    """Whether a story layer of `size` pixels is frame-wide: the 320 x 480-unit column with HD's 32-unit margins either
    side (384 x 480). Within a pixel of that shape: at a density like 2.4 pixels a unit (a frame narrower than HD's) the
    margins round to whole pixels (77 for 76.8), and such a layer squeezed into the column warped every portrait."""
    width, height = size
    return abs(width * 480 - height * FRAME_UNITS[0]) <= 480


def set_story_scale(renderer, scale):
    """A story renderer (DialogueRenderer, ChoiceRenderer, InputRenderer, MessageRenderer) drawing at `scale` pixels
    per layout unit from now on: its canvases made again at that density and everything it cached at the old one
    dropped. Nothing changes when it already draws at that scale (3:4 always: STORY_SCALE)."""
    if renderer is None or getattr(renderer, 'scale', scale) == scale:
        return
    renderer.scale = scale
    size = (round(320 * scale), round(480 * scale))
    if hasattr(renderer, 'wide'):
        renderer.margin = round(32 * scale)
        renderer.wide = pygame.Surface((size[0] + 2 * renderer.margin, size[1]), pygame.SRCALPHA).convert_alpha()
        renderer.canvas = renderer.wide.subsurface((renderer.margin, 0, *size))
    else:
        renderer.canvas = pygame.Surface(size, pygame.SRCALPHA).convert_alpha()
    if hasattr(renderer, 'name_layer'):
        renderer.name_layer = pygame.Surface(size, pygame.SRCALPHA).convert_alpha()
    for name in ('cached_key', 'cached_page', 'hint_key'):
        if hasattr(renderer, name):
            setattr(renderer, name, None)
    for kind in type(renderer).__mro__:
        for value in vars(kind).values():
            if hasattr(value, 'cache_clear'):
                value.cache_clear()


def window_margins(size, frame):
    """The parts of a window of `size` outside the rect `frame`."""
    width, height = size
    areas = (pygame.Rect(0, 0, width, frame.top), pygame.Rect(0, frame.bottom, width, height - frame.bottom),
             pygame.Rect(0, frame.top, frame.left, frame.height),
             pygame.Rect(frame.right, frame.top, width - frame.right, frame.height))
    return [area for area in areas if area.width > 0 and area.height > 0]


def word_game_options(outcomes):
    """(option labels, the score each finishes the quiz with) for the skip prompt, best first, then "Play" (labels
    only): Win / Lose for two outcomes (or when the previews cannot tell), Skip for one, the score ranges for more
    ("Score 6 or more", "Score 4 to 5", "Score 0 to 3"). The best outcome scores the most a quiz can, as Win always did;
    any other its lowest score."""
    if outcomes is None or len(outcomes) == 2:
        return ('Win', 'Lose', 'Play'), (32767, 0)
    if len(outcomes) == 1:
        return ('Skip', 'Play'), (32767,)
    labels, scores = [], []
    for index, (low, high) in enumerate(reversed(outcomes)):
        labels.append(f'Score {low} or more' if high is None else f'Score {low}' if low == high
                      else f'Score {low} to {high}')
        scores.append(32767 if index == 0 else low)
    return (*labels, 'Play'), tuple(scores)


def arena_skip_options(outcomes):
    """(option labels, the result each hands the story) for a New Rules arena game's skip prompt, as word_game_options
    labels them (Win / Lose, Skip, or the result ranges), then "Play" (labels only). Each outcome hands its lowest
    result: every result in it leads the same way to the episode's end (checked on all 50 episodes, 2026-10-31)."""
    labels, _ = word_game_options(outcomes)
    if outcomes is None:
        return labels, (ARENA_RESULTS - 1, 0)
    return labels, tuple(low for low, _ in reversed(outcomes))


def brew_catch_skip_options(outcomes, target):
    """(option labels, the score each finishes the BREW catch game with) for its skip prompt, as word_game_options labels
    them (Win / Lose, Skip, or the score ranges), then "Play" (labels only). The best outcome scores the target, as
    the game itself can at most; any other its lowest score."""
    labels, _ = word_game_options(outcomes)
    if outcomes is None or len(outcomes) == 2:
        return labels, (target, 0)
    if len(outcomes) == 1:
        return labels, (target,)
    best = outcomes[-1][0]                      # nothing scores more than the target, so the best names it
    labels = (f'Score {target}' if best >= target else f'Score {best} to {target}', *labels[1:])
    return labels, tuple(target if index == 0 else low for index, (low, _) in enumerate(reversed(outcomes)))


def shs11_skip_options(outcomes, best=2):
    """(option labels, the result each hands the story) for an SHS '11 game's skip prompt, best first, then "Play" (labels only):
    Win / Lose for two outcomes (or when the previews cannot tell), Skip for one, Win / Come close / Lose for its three."""
    if outcomes is None or len(outcomes) == 2:
        return ('Win', 'Lose', 'Play'), (best, 0)
    if len(outcomes) == 1:
        return ('Skip', 'Play'), (best,)
    return ('Win', 'Come close', 'Lose', 'Play'), (2, 1, 0)


# shshd-runtime: a skip prompt's outcomes are worked out on this worker, from a copy of the session, with the loading band on
# show if they take longer than PROMPT_QUICK_S (owner, 2026-11-07: M.A.S.H. 3 and 4's took 2 s on the g54).
_PROMPT_WORKER = None
PROMPT_SEARCHING = object()


def _prompt_worker():
    global _PROMPT_WORKER
    if _PROMPT_WORKER is None:
        from concurrent.futures import ThreadPoolExecutor
        _PROMPT_WORKER = ThreadPoolExecutor(max_workers=1, thread_name_prefix='skip-prompt')
    return _PROMPT_WORKER


class _PromptEngine:
    """The engine as a host prompt's stand-in session shows it: the same state, but no word quiz, so a prompt over
    one is drawn as an ordinary choice."""
    word_game = None

    def __init__(self, engine):
        self._engine = engine

    def __getattr__(self, name):
        return getattr(self._engine, name)


# Disable Choice Timer's extra row: picking it lets the choice's time run out (Session.expire_choice).
LET_TIME_RUN_OUT_LABEL = 'Let the Timer Run Out'


class _UntimedChoice:
    """A timed choice as Disable Choice Timer shows it (this player's option): no clock, and one more row, last, that
    lets the time run out for the scenes that need no answer. Everything else is the real session's."""
    remaining_ms = None

    def __init__(self, session):
        self.real_session = session
        details = session.pending.details
        shown = dict(details, timeout_ms=0, options=list(details['options']) + [LET_TIME_RUN_OUT_LABEL],
                     values=list(details['values']) + [details.get('timeout_result', -1)],
                     enabled=list(details['enabled']) + [True])
        self.pending = SimpleNamespace(name='choice', details=shown, request=session.pending.request)

    def __getattr__(self, name):
        return getattr(self.real_session, name)


# New Rules' minigame arena (desktop_nr_arena.py): its frames, its menu and its info box draw over it.
ARENA_ACTIONS = ('arena_entrance', 'arena_frame', 'arena_menu', 'arena_info', 'arena_exit')
# Keys as New Rules' Nokia key codes (nr_arena.KEY_BITS): OK / fire, the joystick, the right soft key.
LEASH_KEYS = {pygame.K_LEFT: LEFT, pygame.K_RIGHT: RIGHT, pygame.K_UP: UP, pygame.K_DOWN: DOWN,
              pygame.K_a: LEFT, pygame.K_d: RIGHT, pygame.K_w: UP, pygame.K_s: DOWN}
MEMORY_DIGITS = {**{getattr(pygame, f'K_{n}'): n - 1 for n in range(1, 10)},
                 **{getattr(pygame, f'K_KP{n}'): n - 1 for n in range(1, 10)}}
MEMORY_MOVES = {pygame.K_LEFT: (-1, 0), pygame.K_RIGHT: (1, 0), pygame.K_UP: (0, -1), pygame.K_DOWN: (0, 1),
                pygame.K_a: (-1, 0), pygame.K_d: (1, 0), pygame.K_w: (0, -1), pygame.K_s: (0, 1)}
ARENA_KEYS = {pygame.K_RETURN: -5, pygame.K_KP_ENTER: -5, pygame.K_SPACE: -5, pygame.K_UP: -1, pygame.K_DOWN: -2,
              pygame.K_LEFT: -3, pygame.K_RIGHT: -4, pygame.K_BACKSPACE: -7}
ARENA_NUMBER_KEYS = {**{getattr(pygame, f'K_{n}'): 48 + n for n in range(10)},
                     **{getattr(pygame, f'K_KP{n}'): 48 + n for n in range(10)}}


# New Rules' text is all lowercase (its fonts had only capitals); a game's name in its menus, word by word, where
# capitalising the word isn't enough (owner, 2026-10-31: "welcome to the dj fever game").
ARENA_GAME_WORDS = {'dj': 'DJ'}


def arena_menu_prompt(details):
    """(title, text, options) for New Rules' menu shown as SHS's choice: its last sentence, a question ("view
    tutorial?"), is the title and the rest ("welcome to the `rhyming` game.") the text, without New Rules' font
    switches and in sentence case, as SHS's own menus are written. The words it highlights (between backticks) are
    the game's name, written as a name (ARENA_GAME_WORDS: "DJ Fever")."""
    def name(match):
        return ' '.join(ARENA_GAME_WORDS.get(word, word.capitalize()) for word in match.group(1).split())

    def sentences(string):
        string = re.sub(r'`([^`]*)`', name, string)
        string = re.sub(r'\s+', ' ', string.replace('`', '').replace('~', '')).strip()
        return re.sub(r'(^|[.!?] )([a-z])', lambda m: m.group(1) + m.group(2).upper(), string)
    body = sentences(details.get('title') or '')
    parts = re.split(r'(?<=[.!])\s+(?=[^.!?]*\?$)', body, maxsplit=1)
    title, text = (parts[1], parts[0]) if len(parts) == 2 else (body, '')
    return title, text, [sentences(option) for option in details.get('options', [])]


# After New Rules' exit the arena's last picture (the bare frame) fades out over the story's next screen, rather than
# cutting to it (owner, 2026-10-30; this player's own, as New Rules shows the next screen at once).
ARENA_HANDOVER_MS = 400
MINIGAME_EXITS = {'football': 26, 'word_grid': 7}       # each game's phase while `finishGame` runs
MINIGAME_FADE_MS, MINIGAME_EXIT_MS = 800, 960
# Football's nine plays (football.py SLOTS: three rows of three, top left first) by controller position (owner,
# 2026-10-29): the face buttons are the edges' middles, the triggers the top corners, the bumpers the bottom corners
# and the right stick's click the centre. The number pad matches the field (7 8 9 above 1 2 3); the number row keeps
# reading order (1 is the top left).
FOOTBALL_BUTTONS = {'lt': 0, 'north': 1, 'rt': 2, 'west': 3, 'r3': 4, 'east': 5, 'lb': 6, 'south': 7, 'rb': 8}
# Hold mode's drag (Options' Word Grid Controls): a push steps one cell at once, then one every GRID_HOLD_STEP_MS while
# it is held (this player's pace; a finger moves as fast as it likes).
GRID_HOLD_FIRST_MS, GRID_HOLD_STEP_MS = 0, 220
FOOTBALL_KEYPAD = {pygame.K_KP7: 0, pygame.K_KP8: 1, pygame.K_KP9: 2, pygame.K_KP4: 3, pygame.K_KP5: 4,
                   pygame.K_KP6: 5, pygame.K_KP1: 6, pygame.K_KP2: 7, pygame.K_KP3: 8}


class _DateFirstCard:
    """shshd-runtime: a session as a date-first card's renderer sees it (Desktop._date_first): the pending card's title and subtitle
    swapped, everything else the session's own."""

    def __init__(self, session):
        self._session = session
        details = session.pending.details
        self.pending = _Swapped(session.pending, dict(details, title=details['subtitle'], subtitle=details['title']))

    def __getattr__(self, name):
        return getattr(self._session, name)


class _Swapped:
    def __init__(self, pending, details):
        self._pending, self.details = pending, details

    def __getattr__(self, name):
        return getattr(self._pending, name)


class Desktop:
    story_layer = None
    story_over_scene = False        # the story layer is HD's frame over the scene (the look picker)
    story_lift = 0                  # units the story layer is drawn above its place (a picker centred in a tall frame)
    story_fills_frame = False       # the story layer is the whole frame, of its shape (a title card)
    story_centred = False           # the story layer is a picture at the frame's width, centred (a storyboard)
    # An HD choice being closed after a pick: {'action', 'index', 'ms'}. The row shows its pressed colour, the panel
    # fades out (hd_choice.SELECT_MS, TRANSITION_MS), then the choice is answered.
    choice_closing = None
    # An HD choice kept faded out after its pick opened a prompt (a script link, _answer): {'action', 'index'}. The scene
    # under the prompt is the one without the panel; once the prompt has closed, the choice fades in again with its
    # whole entrance, unless the pick went on.
    choice_held = None
    # The app's own way to open a link (Application.open_url: a mobile host's), or None for webbrowser.
    url_opener = None
    # The host's window is its screen (a mobile host's): the side panels never widen it; landscape gives them room.
    fixed_window = False
    # General's Aspect Ratio (frame_shape.CHOICES), as the app gives it: the frame's shape (frame_units).
    aspect_ratio = '3:4'
    # The option the arrow keys have selected. Enter or Space picks it. Mouse clears it.
    choice_focus = None
    # The same for the Android pause menu's rows (HD's pause menu keeps its own, `pause_hd.state.focus`).
    menu_focus = None
    # A narrator-style choice of this player's own over the pending screen (`_open_prompt`): "Ask to skip mini-games"
    # before a football game or word grid (Win, Lose or Play), and whether to skip the High School Story ad intros.
    # {'action', 'session', 'options', 'resolve'} while it is up (`session` stands in for the real one when drawing it).
    # `minigame_played` is the game the player chose to play and `ad_asked` the ad choice already asked about.
    _skip_minigames = False
    skip_ad_intros = False
    # Autoplay Dialogue (this player's option): dialogue, title cards and message panels take no taps; once their text
    # is out they wait AUTOPLAY_WAIT_MS (a title card AUTOPLAY_TITLE_WAIT_MS) and advance by themselves (owner's
    # choice, 2026-10-21: longer than the Continue pill's 250 ms expansion, to be safe).
    autoplay = False
    skip_ahead = False  # Extras' Allow Skip Ahead: the pause menu's row and the N key (skip_ahead.py)
    undo = False        # Extras' Allow Undo: a save at each stop, the pause menu's Undo row and the U key (undo.py)
    _undo_chain = None  # (record id, its UndoChain)
    _undo_seen = None   # the pending screen last looked at for a save
    AUTOPLAY_WAIT_MS = 750
    AUTOPLAY_TITLE_WAIT_MS = 1500
    autoplay_ms = 0
    _disable_choice_timer = False
    _untimed = None                 # (action, _UntimedChoice) for the pending timed choice
    hd_backdrop = True              # CoD: SHS HD's collage beside the frame (the player's "SHS HD Backdrop" switch)
    hires_portraits = True          # translated New Rules episodes: the "Hi-Res Portraits" switch (set_hires_portraits)
    ms3_characters = False          # translated X360 episodes: the "MS3 Characters" switch (set_ms3_characters)
    java_look = False               # translated BREW episodes: the "Java '08 Look" switch (set_java_look)
    brew_08_backgrounds = False     # '07-badged BREW episodes: the "'08 Backgrounds" switch (set_brew_08_backgrounds)
    smartphone_music = True         # translated SHS '11 episodes: the "Smartphone Music" switch (smartphone_switch)
    _word_grid_skin = False         # ...their minigames in the HD word game's look: the "Use Word Grid Skin" switch
    ch_portraits = True             # CoD with its portrait addon: the CH "HD Portraits in CoD" switch (set_ch_portraits)
    ch_backdrop = True              # ...and its "Backdrop", in place of SHS HD's collage (_window_backdrop)
    _arena_minigames = True         # translated episodes: the "Use Translated Mini-Games" switch (arena_minigames)
    x360_tutorial = None            # a tutorial taken in the X360 look: the game's music request it began under
    arena_skin = False              # ...drawn in the X360 prototype's look: the "Use X360 Arena Skin" switch (x360_arena_switch)
    host_prompt = None
    minigame_played = None
    ad_asked = None
    panel_alpha = None          # the HD menu view's alpha for this frame (None: drawn whole)
    panel_overlay = None        # the HD timer layers for this frame (outside the view's fades)
    edge_layer = None
    _edge_scaled = (None, None, None)   # (edge_layer, size, the layer at that size)
    minigame_shown = None               # (the minigame's state, when it first showed) for its fade in
    loading_handover = None             # {layer, since} the HD band, to close over what follows it
    _blank_canvas = b''
    fade = None
    # Warping through the story tree: `warp_unlocked` is the app's option (the iOS app keeps it locked until Football
    # Season has been completed once); touches on the tree are ignored until `warp_lockout` (a warp locks them for a second).
    warp_unlocked = True
    controller_confirm = 'south'    # a controller's confirm button (Options' Controller page; the app's MenuState)
    grid_controls = 'hold'          # the word grid with a controller: 'hold' or 'tap' (Options' Controller page)
    warp_lockout = 0
    panels_open = False
    panels_progress = 0.0
    # Milliseconds spent computing Choice hints (choice_hints.preview_choices runs inside render()). That time shows
    # up in the next frame's elapsed; tick() leaves it off the story clock so a slow preview never shortens a timed
    # choice's countdown.
    hint_discount_ms = 0
    _panels_wide = False

    # The library's name-replacement table (MenuState.names, player.json): every session this window plays shares it
    # (Session.share_names), so a name typed in one episode is the one every later episode shows. None plays alone.
    names = None
    notice_stack = None             # the native notice/confirm windows, when an HD bundle provides them (see __init__)
    notice_shown = None             # the notice window last drawn, and ms since it opened (its zoom, `pause_scale`)
    notice_ms = PAUSE_OPEN_MS
    pause_closing = False

    @property
    def session(self):
        return self._session

    @session.setter
    def session(self, session):
        if self.names is not None:
            session.share_names(self.names)
        session.choice_click = False        # the tap plays it (`_menu_sound`), not the later answer
        session.choice_timer = not self._disable_choice_timer
        session.nr_arena = self._arena_minigames
        session.grids_as_memory = self._grids_as_memory
        session.shs11_hd_sounds = self._skin_has_its_sounds()
        session.shs11_seen_this_run = self._shs11_seen_this_run
        session.skip_arena = self._skip_minigames
        session.cutscenes = True            # (this player draws them: desktop_cutscene)
        self._session = session

    @property
    def word_grid_skin(self):
        """The "Use Word Grid Skin" switch: SHS '11's games in the HD word game's look, and with its sounds (Session.shs11_hd_sounds)."""
        return self._word_grid_skin

    @word_grid_skin.setter
    def word_grid_skin(self, value):
        self._word_grid_skin = bool(value)
        if getattr(self, '_session', None) is not None:
            self._session.shs11_hd_sounds = self._skin_has_its_sounds()

    def _skin_has_its_sounds(self):
        """Only where the skin really draws: without the HD bundle's art, '11's own look keeps '11's own sounds."""
        hd = getattr(self, 'shs11_hd', None)
        return self._word_grid_skin and hd is not None and hd.available()

    _shs11_seen_this_run = None

    @property
    def shs11_seen_this_run(self):
        """The SHS '11 tutorials finished since the app started, a set the Application keeps from episode to episode."""
        return self._shs11_seen_this_run

    @shs11_seen_this_run.setter
    def shs11_seen_this_run(self, seen):
        self._shs11_seen_this_run = seen
        if getattr(self, '_session', None) is not None:
            self._session.shs11_seen_this_run = seen

    _grids_as_memory = False

    @property
    def grids_as_memory(self):
        """shshd-runtime's "Use '11's Memory for Word Grid" (owner, 2026-11-04): letter grids play as SHS '11's Memory.
        Asked as each grid opens (shs11_games.grid_memory), so one already open stays as it is."""
        return self._grids_as_memory

    @grids_as_memory.setter
    def grids_as_memory(self, value):
        self._grids_as_memory = bool(value) and self.memory_grid_switch()
        if getattr(self, '_session', None) is not None:
            self._session.grids_as_memory = self._grids_as_memory

    def memory_grid_switch(self):
        """Whether the switch is offered: in SHS, with what can draw the game: the HD word game's art (the Word Grid skin, which it
        always has), or failing that SHS '11's addon (its own look)."""
        if game_id(self.session.resources) != 'shs':
            return False
        if self.shs11_hd is not None and self.shs11_hd.art_available():
            return True
        try:
            return memory_spec(self.session.resources) is not None
        except (ContentError, OSError, ValueError):
            return False

    @property
    def skip_minigames(self):
        """Ask to Skip Mini-Games: football, the word grid and the word quiz first ask Win, Lose or Play, and so do
        New Rules' arena games (Session.skip_arena: their stories wait at service 213)."""
        return self._skip_minigames

    @skip_minigames.setter
    def skip_minigames(self, value):
        self._skip_minigames = bool(value)
        if getattr(self, '_session', None) is not None:
            self._session.skip_arena = self._skip_minigames

    @property
    def arena_minigames(self):
        """shshd-runtime's "Use Translated Mini-Games" (owner, 2026-10-31, as Minigame Arena): translated episodes play
        their minigames for real, New Rules' in its arena; off, as the timed choices they carry for players without it.
        A story asks as each game starts (service 70's arena query), so a game already playing keeps its form."""
        return self._arena_minigames

    @arena_minigames.setter
    def arena_minigames(self, value):
        self._arena_minigames = bool(value)
        if getattr(self, '_session', None) is not None:
            self._session.nr_arena = self._arena_minigames

    @property
    def disable_choice_timer(self):
        """Disable Choice Timer (this player's option): timed choices hold their clock and gain a row that lets it
        run out. The quiz (service 71) keeps its clock; that is Ask to Skip Mini-Games'."""
        return self._disable_choice_timer

    @disable_choice_timer.setter
    def disable_choice_timer(self, value):
        self._disable_choice_timer = bool(value)
        if getattr(self, '_session', None) is not None:
            self._session.choice_timer = not self._disable_choice_timer

    def _choice_source(self):
        """What the choice renderer draws: the session, or its untimed stand-in under Disable Choice Timer."""
        action = self.session.pending
        if (not self._disable_choice_timer or action is None or action.name != 'choice'
                or self.session.remaining_ms is None):
            return self.session
        if self._untimed is None or self._untimed[0] is not action:
            self._untimed = (action, _UntimedChoice(self.session))
        return self._untimed[1]

    def _timeout_row(self, action, index):
        """Whether `index` is the untimed stand-in's last row, Let the Timer Run Out."""
        source = self._choice_source()
        return (source is not self.session and action is source.real_session.pending
                and index == len(action.details['options']))

    def __init__(self, session: Session, *, audio: bool = True, window=None, on_main_menu=None, capture=False,
                 episode_title=None, on_menu_page=None, names=None, vibration_enabled=False,
                 device_vibration_enabled=False):
        self.names = names
        pygame.display.init()
        pygame.font.init()
        # A capture draws one clean frame into `window` (a plain surface): no display, caption, or edge bar.
        self.capture = capture
        if window is None:
            set_window_icon(session.resources.library)
        self.window = window if window is not None else pygame.display.set_mode(DEFAULT_WINDOW_SIZE, pygame.RESIZABLE)
        self.on_main_menu = on_main_menu
        self.on_menu_page = on_menu_page
        self.pause_renderer = None
        self.pause_elapsed_ms = PAUSE_OPEN_MS
        self.gear_pointer_down = False
        self.ui_sounds = UiSounds()
        self.episode_title = episode_title if episode_title is not None else session.resources.record['titles'][0]
        if not capture:
            pygame.display.set_caption(GAMES[game_id(session.resources)].TITLE + ' — ' + self.episode_title)
        # SRCALPHA (was opaque .convert(32)): backgrounds for dialogue and
        # the generic/text-input path are now composited separately by
        # _present(), directly at window resolution instead of this fixed
        # SIZE canvas, so this canvas is left transparent where a
        # background belongs -- see _present() and self.pending_background.
        self.canvas = pygame.Surface(SIZE, pygame.SRCALPHA).convert_alpha()
        self.font = pygame.font.Font(None, 27)
        self.heading = pygame.font.Font(None, 34)
        self.small = pygame.font.Font(None, 22)
        self.session = session
        self.story_text = BitmapTextRenderer(session.resources.library)
        self.dialogue_renderer = DialogueRenderer(session.resources, self.story_text, self._image, scale=STORY_SCALE)
        self.choice_renderer = ChoiceRenderer(session.resources, self.story_text, self.dialogue_renderer,
                                             scale=STORY_SCALE)
        self.grid_renderer = self.football_renderer = None
        if game_id(session.resources) == 'shs':
            from .shs.desktop_grid import GridRenderer
            from .shs.desktop_football import FootballRenderer
            self.grid_renderer = GridRenderer(session.resources, self.story_text, self.dialogue_renderer)
            self.football_renderer = FootballRenderer(session.resources, self.story_text, self.dialogue_renderer)
        self.football_hd = HdFootballRenderer(session.resources) if HdFootballRenderer else None
        self.word_hd = HdWordRenderer(session.resources, self.dialogue_renderer) if HdWordRenderer else None
        self.shs11_hd = Shs11HdRenderer(session.resources, self.dialogue_renderer) if Shs11HdRenderer else None
        self.nr_arena_renderer = NRArenaRenderer(session.resources)
        self.x360_arena_renderer = X360ArenaRenderer(session.resources)
        self.x360_slot_renderer = X360SlotRenderer(session.resources)
        self.shs11_memory_renderer = Shs11MemoryRenderer(session.resources)
        self.shs11_reflex_renderer = Shs11ReflexRenderer(session.resources)
        self.brew_catch_renderer = BrewCatchRenderer(session.resources)
        self.x360_leash_renderer = X360LeashRenderer(session.resources)
        self.x360_puzzle_renderer = X360PuzzleRenderer(session.resources)
        self.cutscene_renderer = CutsceneRenderer(session.resources)
        self.x360_diss_renderer = X360DissRenderer(session.resources)
        self.puzzle_key = None          # the jewel puzzle: (key, direction, ms to its next repeat) of a held direction key
        self.puzzle_pad = False         # OK came from a controller's confirm, and is held
        self.leash_anchor = None        # where a drag last turned, in frame units, while one is shaking the leash
        self._x360_arena = None             # whether the X360 addon's arena skin is there (x360_arena_switch)
        self.pause_hd = HdPauseMenu(session.resources)
        # Released drags gliding on: the tree slows as HD's does (UIScrollView's fast rate), the wall at the normal one.
        self.tree_fling, self.wall_fling = momentum.Fling(momentum.RATE_FAST), momentum.Fling()
        self.choice_fling = momentum.Fling()        # a long choice's rows gliding on after a flick (touch hosts)
        if self.dialogue_renderer.game_id() == 'cod':
            # Cause of Death's own Pause / Options / Help & About (its menu engine windows in its own art).
            from .desktop_cod_pause import CodPauseMenu
            self.pause_hd = CodPauseMenu(session.resources, self.dialogue_renderer, self.story_text)
        self.badge_hd = HdSceneBadge(self.dialogue_renderer, self._image)
        self.pause_buttons = []
        self.music_volume = self.sound_volume = 1.0
        self.on_settings = None       # called after the pause menu changes music / sound
        self.picker_renderer = CharacterPickerRenderer(session.resources, self.story_text, self.dialogue_renderer)
        self.picker_hd = HdCharacterPickerRenderer(session.resources, self.story_text, self.dialogue_renderer)
        self.picker_cod = CodCharacterPickerRenderer(session.resources, self.story_text, self.dialogue_renderer)
        self.loading_renderer = LoadingRenderer(session.resources, self.story_text, self.dialogue_renderer)
        self.loading_hd = HdLoadingRenderer(session.resources, self.dialogue_renderer)
        self.message_renderer = MessageRenderer(session.resources, self.story_text, self.dialogue_renderer,
                                                scale=STORY_SCALE)
        self.message_hd = HdMessageRenderer(session.resources, self.dialogue_renderer)
        self.message_cod = CodMessageRenderer(session.resources, self.dialogue_renderer)
        self.title_renderer = TitleRenderer(session.resources, self.story_text, self.dialogue_renderer)
        self.title_hd = HdTitleRenderer(session.resources, self.dialogue_renderer)
        self.title_cod = None
        self.dtview_renderer = DTViewRenderer(session.resources, self.story_text, self._image)
        self.faceplace_panel_renderer = FaceplacePanelRenderer(session.resources, self.story_text,
                                                                self._image, self.dialogue_renderer)
        self.input_renderer = InputRenderer(session.resources, self.story_text, self.dialogue_renderer,
                                            scale=STORY_SCALE)
        self.faceplace_alert = FaceplaceAlertRenderer(session.resources, self.story_text, self.dialogue_renderer)
        self.side_panels = SidePanels(session.resources, self.story_text, self.dialogue_renderer, self.faceplace_alert)
        # The menu engine's own native notice/confirm windows (resource 17), drawn modally over the running
        # episode instead of the game's usual toast: a faceplace wall link opens through the app's own
        # "Exit Game?" confirmation (menu 17) instead of straight to the browser -- this player's own addition
        # (see `_wall_pointer`'s own note) -- and the Decision Tree's own "Locked" notice (menu 28, string 271,
        # `touchesEnded:` while `warp_unlocked` is false) reuses the same stack rather than a one-off. Absent
        # without an HD bundle imported (no resource 17 to read); a wall link opens directly without confirming,
        # and the lock falls back to the toast, matching the base app either way.
        self.notice_data = self.notice_windows = self.notice_stack = None
        # The "Exit Game?" window and its Yes action: SHS HD's menu 17 / action 18, CoD's menu 16 / action 24. The
        # Connection Error window (SHS HD's 41, CoD's 38) answers a link only another app could open (_answer).
        self.exit_menu, self.exit_action, self.connection_menu = 17, 18, 41
        raw = self.pause_hd.raw(17)
        if raw is not None:
            try:
                self.notice_data = MenuEngineData(raw)
                self.notice_windows = HdMenuWindows(session.resources.library, self.notice_data, self.dialogue_renderer)
                self.notice_stack = MenuStack(self.notice_data, self._wall_perform)
            except MenuEngineError as error:
                logging.warning('Native notice/confirm windows unavailable: %s', error)
        elif self.dialogue_renderer.game_id() == 'cod' and self.dialogue_renderer.cod_hd_common() is not None:
            # Cause of Death's own menu engine (logical resource 15) and its "Exit Game?" alert (desktop_cod_menu.py),
            # with the SHS HD art source like the rest of its HD presentation.
            from .desktop_cod_menu import CONNECTION_ERROR, EXIT_ACTION, EXIT_GAME, CodMenuWindows
            try:
                self.notice_data = MenuEngineData(session.resources.library.android_asset(15))
                self.notice_windows = CodMenuWindows(session.resources.library, self.notice_data, self.dialogue_renderer)
                self.notice_stack = MenuStack(self.notice_data, self._wall_perform)
                self.exit_menu, self.exit_action, self.connection_menu = EXIT_GAME, EXIT_ACTION, CONNECTION_ERROR
            except (MenuEngineError, ContentError) as error:
                logging.warning('Native notice/confirm windows unavailable: %s', error)
                self.notice_data = self.notice_windows = self.notice_stack = None
        self.wall_link = ''
        self.link_answer = None         # a choice answered once its link's "Exit Game?" prompt closes (_answer)
        self.link_resources = None      # (resources, whether their scripts hold links)
        self.notice_pressed = None
        self.input_action = None
        self.input_error = None
        self.input_keyboard = False
        self.text_input_started = None  # Force the first sync to set SDL's state.
        self.picker_pointer_down = False
        self.press = ButtonPress()
        self.images = OrderedDict()
        self._background_layer_cache = None   # (key, scaled surface) from the last _draw_background_layer call
        self._frame_backdrop_cache = (None, {})     # (key, {resource: scaled surface or None}), see _frame_backdrop
        self.buttons = []
        self.scroll = self.max_scroll = 0
        self.screen_token = None
        self.message = ''
        self.message_until = 0
        self.error = None
        self.pending_background = None
        self.pending_background_origin = (160, 180)
        self.pending_background_alpha = 255
        self.last_background_id = -1         # the last real scene background seen (render()); episode_exit clears
                                              # panel.background_id to -1, so the end-of-episode screen falls back
                                              # to this instead of showing no background at all
        self.location_pan = LocationPan()
        # The location layer's last picture, placement and card flag, and its running implicit animation
        # (_location_change).
        self.location_shown = self.location_changing = None
        # The last dialogue frame's UI layers, and CoD's message panel fading them out over itself (_panel_handover).
        self.ui_layers, self.ui_handover = None, None
        self.fade = None                     # the player's own fade from black (a warp; scene_fade.py)
        self.music_token = None
        self.music_stream = MusicStream()
        self.music_stream.chain = self._music_loop
        self.music_was_enabled = True
        # The menu's song in the pause menu (see `_sync_pause_song`): its Sound, the ticks its fade-out began, and
        # whether the Music switch has asked for it (SHSEngine +0xb22c), and the pause page that switch was on.
        self.pause_song = self.pause_song_fade = None
        self.pause_song_wanted = False
        self.pause_song_page = None
        self.sound_serial = session.engine.sound_serial
        self.vibration_serial = session.engine.vibration_serial
        self.audio = False
        self.music_enabled = self.sound_enabled = True
        # Off by default (the buzz is an opt-in addition, PR #10); set here so the first script's requests obey it.
        self.vibration_enabled = vibration_enabled
        # General's Vibration: the device's own vibrator (graphics.set_vibrator), where there is one.
        self.device_vibration_enabled = device_vibration_enabled
        self.choice_hints = False
        self.active = True
        self.menu_open = False
        # DTView/Faceplace panels: toggled by a device rotation in the real
        # app (see desktop_panels.py); this desktop app has no such
        # gesture, so the user chose the Tab key instead. progress is a
        # 0..1 slide fraction, not a recovered native animation constant.
        self.panels_open = False
        self.panels_progress = 0.0
        self._panels_wide = False
        if audio:
            try:
                pygame.mixer.init()
                self.audio = True
            except pygame.error as error:
                logging.warning('Audio unavailable: %s', error)
        self._attempt(session.advance)

    def _attempt(self, operation):
        try:
            operation()
        except (ContentError, VMError, SaveError, OSError, ValueError) as error:
            self.error = str(error)
            logging.error('Playback stopped: %s', error)
        finally:
            self._sync_vibration()

    def _sync_vibration(self):
        """exp-runtime v0.6.0's device vibration (graphics.vibrate: the iOS backend; nothing on a desktop). This fork's
        simulated buzz is separate (`_buzz`, from service 82's serial)."""
        count = self.session.take_vibrations()
        if not count or not self.device_vibration_enabled or not self.active or self.menu_open:
            return
        for _ in range(count):
            pygame.vibrate()

    def capture_audio(self):
        """exp-runtime's checkpoint hook (platforms/ios.py): its own player stores the playing cue's playhead in
        `engine.music_playback`. This fork's music is music_stream.py's and is not captured, so the hook does nothing."""

    def _notice(self, message):
        self.message, self.message_until = message, pygame.time.get_ticks() + 3500

    def _image(self, asset_id):
        if asset_id < 0:
            return None
        if asset_id not in self.images:
            try:
                data = self.session.resources.read_asset(asset_id)
                if data.startswith((b'\x89PNG', b'\xff\xd8')):
                    self.images[asset_id] = pygame.image.load(BytesIO(data)).convert_alpha()
                else:
                    pack = ImagePack.parse(data)
                    if len(pack.images) != 1 or pack.images[0].mode != 'RGBA':
                        raise ContentError(f'Resource {asset_id} is not a single RGBA image')
                    frame = pack.images[0]
                    self.images[asset_id] = pygame.image.frombytes(frame.pixels, (frame.width, frame.height), 'RGBA').convert_alpha()
            except (ContentError, pygame.error, OSError) as error:
                self.images[asset_id] = None
                logging.warning('Image %s cannot be displayed: %s', asset_id, error)
                self._notice(f'Image {asset_id} could not be displayed')
            if len(self.images) > 64:
                self.images.popitem(last=False)
        self.images.move_to_end(asset_id)
        return self.images[asset_id]

    def _chrome_image(self, asset_id):
        """Like _image(), but normalized back to the Android apparent size
        for small UI icons/badges that have no HD-scale compensation of
        their own -- unlike backgrounds and portraits, which are meant to
        gain real extra density and explicitly compensate for it elsewhere.
        Confirmed live: relationship icons (ids 3010-3012) silently double
        in size (22x24 -> 44x48) through the same HD_SHARED_CONTENT_RANGE
        fallback that correctly upgrades backgrounds/portraits, because
        nothing downstream of it was scaling these back down. See
        legacy/findings.md, "Chrome icons render oversized with an HD ipa".
        """
        image = self._image(asset_id)
        if image is None:
            return None
        try:
            android_size = _decoded_size(self.session.resources.android_asset(asset_id))
        except (ContentError, pygame.error, OSError):
            return image
        if image.get_size() != android_size:
            image = pygame.transform.smoothscale(image, android_size)
        return image

    def _lines(self, text, font, width):
        # Backticks delimit native emphasis. Font styling is currently simplified.
        lines = []
        for paragraph in text.replace('`', '').split('\n'):
            line = ''
            for word in paragraph.split():
                proposed = f'{line} {word}' if line else word
                if line and font.size(proposed)[0] > width:
                    lines.append(line)
                    line = ''
                for char in word:
                    proposed = line + char
                    if line and font.size(proposed)[0] > width:
                        lines.append(line)
                        line = ''
                    line += char
                line += ' '
            lines.append(line.rstrip())
        return lines

    def _text(self, text, x, y, width, *, font=None, color=INK):
        font = font or self.font
        for line in self._lines(text, font, width):
            self.canvas.blit(font.render(line, True, color), (x, y))
            y += font.get_linesize() + 3
        return y

    def _button(self, label, rect, command, *, enabled=True, small=False):
        pygame.draw.rect(self.canvas, (49, 62, 84) if enabled else (33, 37, 46), rect, border_radius=8)
        if enabled and command == ('choose', self.choice_focus):
            pygame.draw.rect(self.canvas, ACCENT, rect, 2, border_radius=8)
        else:
            pygame.draw.rect(self.canvas, (102, 115, 135), rect, 1, border_radius=8)
        self._text(label, rect.x + 12, rect.y + 10, rect.width - 24,
                   font=self.small if small else self.font, color=INK if enabled else MUTED)
        if enabled:
            self.buttons.append((rect.clip(self.canvas.get_clip()), command))

    def _portrait(self, character, expression, bottom):
        variants = self.session.engine.character_art_variants.get(character)
        if not variants:
            return
        # FUN_00095c60 takes expression modulo five; panel setup clamps
        # negative expression overrides to zero.
        portrait = self._image(variants[max(0, expression) % len(variants)])
        if portrait is not None:
            width, height = portrait.get_size()
            scale = min(160 / width, 180 / height)
            portrait = pygame.transform.smoothscale(portrait, (int(width * scale), int(height * scale)))
            self.canvas.blit(portrait, (SIZE[0] - portrait.get_width() - 22, bottom - portrait.get_height()))

    @property
    def music_loaded(self):
        """Whether the story's music holds a cue (playing, fading, paused or kept by the pause menu)."""
        return self.music_stream.loaded

    def _sync_music(self):
        """The story's music, as SHSSoundManager plays it (music_stream.py): requests and service 81's fading stop from
        the engine, the Music switch, the pause menu's store and restore, and the immediate pause while the window is
        inactive or the script has paused the music (service 83)."""
        if not self.audio:
            return
        engine, stream, now = self.session.engine, self.music_stream, pygame.time.get_ticks()
        if stream.volume != self.music_volume:
            stream.set_volume(self.music_volume)
        # A translated episode's smartphone music, with its switch off, goes as it does with Music off.
        enabled = self.music_enabled and (self.smartphone_music or not self.smartphone_switch())
        if enabled != self.music_was_enabled:
            self.music_was_enabled = enabled
            if not enabled:
                stream.disable(now)                  # setMusicEnabled(false): stopMusic(-1, true)
        token = (engine.music_id, engine.music_flag, engine.music_serial)
        if token != self.music_token:
            if self.music_token is None:
                stream.reset()                       # a new or reloaded session starts its own cue
            self.music_token = token
            if engine.music_id >= 0:
                if enabled:                          # playMusic ignores requests while Music is off
                    music_id, opener = engine.music_id, self._open_cue
                    swaps = self._x360_swaps()
                    if swaps is not None and music_id in swaps[1]:
                        # The X360 look's own music for the games' track (owner, 2026-10-31), under its own ID, so
                        # a later request for New Rules' track isn't taken for it.
                        archive, music_id = swaps[2], swaps[1][music_id]
                        opener = lambda _id: (archive.read(music_id), 0)       # noqa: E731
                    stream.play(music_id, engine.music_flag, opener, now, held=self.menu_open,
                                takes_loop=self.smartphone_switch())
            else:
                stream.stop(engine.music_stop_ms, now)
        self._x360_tutorial_music(stream, now)
        self._end_x360_music(stream, engine, now)
        stream.update(now, enabled=enabled, menu_open=self.menu_open,
                      paused=not self.active or engine.music_paused, held_back=self.pause_song is not None)
        self._sync_pause_song(now)

    def _sync_pause_song(self, now):
        """The menu's song in the pause menu. Switching Music on sets `SHSEngine` +0xb22c, which
        `doSoundManagerTransition` (SHS HD 0002a830, CoD 00025c60) turns into the menu's song (MENU_MUSIC, once) as
        soon as the paused episode's music has gone quiet. Switching Music off again fades it over 1000 ms; Resume
        fades it too, and the episode's song comes back only after it has stopped (`restoreGameAudio`). Leaving the
        page whose switch turned Music on (Options > Sound) fades it as Resume does (owner's choice, 2026-10-23). The
        Main Menu row hands a song still playing to the main menu (`take_pause_song`)."""
        song = self.pause_song
        if song is not None and song.get_num_channels() == 0:
            song = self.pause_song = self.pause_song_fade = None             # it played out
        left_page = self.pause_hd.state.screen != self.pause_song_page
        if left_page:
            self.pause_song_wanted = False
        if (self.pause_song_wanted and song is None and self.menu_open and self.music_enabled and self.active
                and self.music_stream.silent):
            self.pause_song_wanted = False
            library = self.session.resources.library
            try:
                song = pygame.mixer.Sound(file=BytesIO(library.read_asset(GAMES[game_id(self.session.resources)].MENU_MUSIC)))
                song.set_volume(self.music_volume)
                song.play()
                self.pause_song = song
            except (AttributeError, ContentError, pygame.error) as error:
                logging.warning('Menu music cannot be played: %s', error)
            return
        if not self.menu_open:
            self.pause_song_wanted = False
        if song is None:
            return
        if self.pause_song_fade is None and (not self.menu_open or not self.music_enabled or left_page):
            self.pause_song_fade = now                                      # Resume, Music off or Back: stop(false)
        if self.pause_song_fade is None:
            song.set_volume(self.music_volume)
            return
        level = 1 - (now - self.pause_song_fade) / FADE_MS
        if level <= 0:
            song.stop()
            self.pause_song = self.pause_song_fade = None
        else:
            song.set_volume(self.music_volume * level)

    def take_pause_song(self):
        """The menu's song if the pause menu is playing it (not fading): the main menu keeps it going, where the
        original fades it out and leaves the main menu silent (owner's choice, 2026-10-20)."""
        song = self.pause_song
        if song is None or self.pause_song_fade is not None or song.get_num_channels() == 0:
            return None
        self.pause_song = None
        return song

    def _open_cue(self, music_id):
        """A music request's MP3 and where it starts (s): SHS's segment cues name a place in another track."""
        cue = music_cue(music_id, game=game_id(self.session.resources))
        return self.session.resources.read_asset(cue.asset_id), cue.start_ms / 1000

    def _music_loop(self, music_id):
        """shshd-runtime: the loop a translated pack's intro cue runs into (the game profile's TRANSLATED_MUSIC_LOOPS,
        or the episode's own declaration: content.presentation_feature), as bytes, or None (MusicStream.chain)."""
        resources = self.session.resources
        loops = presentation_feature(resources, 'music_loops') or {}
        if music_id not in loops:
            return None
        try:
            return resources.read_asset(loops[music_id])
        except ContentError as error:
            logging.warning('Music loop %s cannot be read: %s', loops[music_id], error)
            return None

    def _sync_audio(self):
        if not self.audio:
            return
        self._sync_music()
        engine = self.session.engine
        if engine.sound_serial != self.sound_serial:
            self.sound_serial = engine.sound_serial
            self._play_sounds(engine.sound_ids or [engine.sound_id])
        if engine.vibration_serial != self.vibration_serial:
            if engine.vibration_serial > self.vibration_serial:
                self._buzz()
            self.vibration_serial = engine.vibration_serial
        # `animationDidStop:` of the alert's slide on: sound 0x1f52. The strip is only on show in portrait, so there is
        # none while the panels are open.
        toast = engine.faceplace_toast
        if toast is not None and toast is not self.alert_sounded and toast.enter_progress >= 1 and not self.panels_open:
            self.alert_sounded = toast
            self._play_sounds([FACEPLACE_ALERT_SOUND])

    alert_sounded = None        # the alert whose sound has played
    buzz_sound = None           # service 82's stand-in for the vibrator (vibration.py), built on first use

    def _buzz(self):
        if not (self.vibration_enabled and self.sound_enabled):
            return                          # (a device's own vibrator is General's Vibration: `_sync_vibration`)
        try:
            if self.buzz_sound is None:
                self.buzz_sound = pygame.mixer.Sound(file=BytesIO(buzz_wav()))
            self.buzz_sound.set_volume(self.sound_volume)
            self.buzz_sound.play()
        except pygame.error as error:
            logging.warning('Vibration buzz cannot be played: %s', error)

    def _end_x360_music(self, stream, engine, now):
        """The X360 look's game music fades out as the game ends: as "Time's up!" appears (the panel's time_up; owner,
        2026-11-01, at first "your score"), or once the arena is gone. Diss Practice's music belongs to the game, and
        the story doesn't stop it."""
        from .desktop_nr_arena_x360 import MUSIC_FADE_MS
        current = stream.current
        if current is None or stream.fade is not None or getattr(self, '_x360_arena', None) is not True:
            return                          # (the addon's skin is known to be there once the switch was offered)
        try:
            spec = self.x360_arena_renderer.x360()[0]
        except ValueError:
            return
        music = {*spec.get('music_track', {}).values(), spec.get('tutorial_music')}
        if current['id'] not in music:
            return
        arena = engine.nr_arena
        if arena is None or arena.time_up:
            stream.stop(MUSIC_FADE_MS, now)

    def _in_x360_tutorial(self):
        """Whether a tutorial is running in the X360 look: from a yes to "view tutorial?" until the game's own music
        request, which comes as the game starts. Not kept in a save: a tutorial resumed from one plays as New Rules' does."""
        if self.x360_tutorial is None:
            return False
        engine = self.session.engine
        if engine.music_serial != self.x360_tutorial or self._x360_swaps() is None:
            self.x360_tutorial = None
            return False
        return True

    def _x360_tutorial_music(self, stream, now):
        """New Rules plays no music in a tutorial; the X360 look plays the tutorials' own (owner, 2026-11-01)."""
        if not self.music_enabled or not self._in_x360_tutorial():
            return
        spec, archive = self.x360_arena_renderer.x360()
        resource = spec.get('tutorial_music')
        if resource is not None:
            stream.play(resource, True, lambda _id: (archive.read(resource), 0), now, held=self.menu_open)

    def _x360_tutorial_sounds(self):
        """New Rules plays no sound in a tutorial's practice; the X360 look plays the game's for each hit effect there."""
        if self._in_x360_tutorial() and self.x360_arena_renderer.hits:
            from .desktop_nr_arena_x360 import HIT_TRACKS, NR_TRACK_BASE
            hits = self.x360_arena_renderer.hits
            self._play_sounds([NR_TRACK_BASE + HIT_TRACKS[kind] for kind in hits])
            hits.clear()

    def _x360_swaps(self):
        """While the arena is open in the X360 look: ({New Rules sound: [X360 sounds]}, {New Rules music: X360 music},
        the X360 addon's archive), from its skin's spec (owner, 2026-10-31: right, wrong and the swaps' bonus noise,
        and the games' track, Diss Practice's); else None. Nothing the script sees changes."""
        if not (self.arena_skin and self.session.engine.nr_arena is not None and self.x360_arena_switch()):
            return None
        from .desktop_nr_arena_x360 import NR_TRACK_BASE
        spec, archive = self.x360_arena_renderer.x360()
        return ({NR_TRACK_BASE + int(track): ids for track, ids in spec.get('sound_tracks', {}).items()},
                {NR_TRACK_BASE + int(track): music for track, music in spec.get('music_track', {}).items()}, archive)

    def _play_sounds(self, assets):
        if not self.sound_enabled:
            return
        swaps = self._x360_swaps()
        try:
            for asset in assets:
                if swaps is not None and swaps[0].get(asset):
                    name = random.choice(swaps[0][asset])       # one of the X360's, as it picks
                    sound = self._sound(name, lambda: swaps[2].read(name))
                else:
                    sound = self._sound(asset, lambda: self.session.resources.read_asset(asset))
                sound.set_volume(self.sound_volume)
                if asset in self._one_channel():
                    if self._channel_sound is not None:
                        self._channel_sound.stop()
                    self._channel_sound = sound
                sound.play()
        except (ContentError, pygame.error) as error:
            logging.warning('Sound %s cannot be played: %s', assets, error)

    _channel_sound = None               # the last of a translated pack's one-channel sounds (TRANSLATED_ONE_SOUND_CHANNEL)

    def _one_channel(self):
        return pack_setting(self.session.resources, 'TRANSLATED_ONE_SOUND_CHANNEL', ()) or ()

    SOUNDS_KEPT = 32
    SOUND_KEPT_SECONDS = 5
    _sounds_kept = (None, {})           # (the resources they came from, {key: decoded Sound})

    def _sound(self, key, read):
        """A sound effect, decoded once: read and decoded at every play, each hit in a minigame cost a phone's frame 45 ms.
        The last few short ones are kept, per episode (its ids are its own)."""
        resources = self.session.resources
        if self._sounds_kept[0] is not resources:
            self._sounds_kept = (resources, {})
        kept = self._sounds_kept[1]
        sound = kept.pop(key, None)
        if sound is None:
            sound = pygame.mixer.Sound(file=BytesIO(read()))
            if sound.get_length() > self.SOUND_KEPT_SECONDS:
                return sound
            if len(kept) >= self.SOUNDS_KEPT:
                del kept[next(iter(kept))]
        kept[key] = sound
        return sound

    def _sync_text_input(self):
        if self.capture:
            return
        action = self.session.pending
        if action is not None and action.name != 'text_input':
            action = None
        if action is not self.input_action:
            self.input_action, self.input_error = action, None
            self.input_keyboard = action is not None
            if action is not None:
                action.details.setdefault('draft', action.details['default'])
        enabled = bool(action and self.input_keyboard and self.active and not self.menu_open
                       and not self.input_error and not self.error)
        if enabled != self.text_input_started:
            (pygame.key.start_text_input if enabled else pygame.key.stop_text_input)()
            self.text_input_started = enabled
        if enabled and hasattr(self, 'viewport'):
            x, y, w, h = INPUT_RECT
            pygame.key.set_text_input_rect(pygame.Rect(
                self.viewport.x + x * self.viewport.width / 320,
                self.viewport.y + y * self.viewport.height / 480,
                w * self.viewport.width / 320, h * self.viewport.height / 480))

    def _answer(self, *value):
        """Answer the pending element. A queued transition (service 16) is the session's (fade_transition.py): the
        element stays up under the closing blinds, the script runs once they are shut, and the next one is revealed."""
        if self.fade or self.session.transitioning:
            return
        # A choice that opens a link (service 100, a no-op in HD) is offered behind the "Exit Game?" prompt. One that
        # then ends the script -- the High School Story ad's "Go to the High School Story app!" -- would leave the
        # episode stopped: it stays on the choice. Any other (the novels' "Yes, please!") goes on, to the survey, once
        # the prompt has closed.
        probe = self._link_probe(value)
        if probe is not None:
            link, finished = probe
            if self._hd_choice_drawn():
                self.choice_held = dict(action=self.session.pending, index=value[0] if value else None)
            if not WEB_LINK.match(link):
                # An app's own scheme (CoD's Halloween special: `ghostharvest://crosspromotion`, to unlock a ghost in
                # Ghost Harvest) has nothing to open here: the Connection Error window, and the choice stays up (owner's
                # choice, 2026-10-21).
                self.wall_link = ''
                if self.notice_stack is not None:
                    self.notice_stack.queue(self.connection_menu)
                else:
                    self._notice('Connection Error')
                return
            self._offer_link(link)
            if finished:
                return
            if self.notice_stack is not None and self.notice_stack.stack:
                self.link_answer = value
                return
        self._answer_now(value)

    def _answer_now(self, value):
        self.session.engine.store_link = ''
        self._attempt(lambda: self.session.answer(*value))
        self.session.engine.store_link = ''

    def _link_probe(self, value):
        """(link, whether the script then finishes) if answering the pending choice with `value` opens a link, found on
        a throwaway copy of the session (as choice_hints previews a branch), else None."""
        session = self.session
        if session.pending is None or session.pending.name != 'choice':
            return None
        if self.link_resources is None or self.link_resources[0] is not session.resources:
            self.link_resources = (session.resources, has_links(session.resources))
        if not self.link_resources[1]:
            return None
        try:
            probe = deepcopy(session, {id(session.resources): session.resources,
                                       id(session.vm.program): session.vm.program})
            probe.ephemeral, probe.durable = True, False
            probe.engine.store_link = ''
            probe.answer(*value)
        except (VMError, ValueError) as error:
            logging.debug('Link probe failed: %s', error)
            return None
        link = probe.engine.store_link
        if not link:
            return None
        return link, probe.episode_exited or (probe.pending is not None and probe.pending.name == 'finished')

    def _offer_link(self, link):
        """Open a script's link in the browser, behind the app's "Exit Game?" confirmation as the wall's links are. An
        App Store link (`itms://`) becomes its web page."""
        url = re.sub(r'^itms(-apps)?://itunes\.apple\.com/', 'https://apps.apple.com/', link)
        if self.notice_stack is not None:
            self.wall_link = url
            self.notice_stack.queue(self.exit_menu)
        else:
            self._open_link(url)

    SKIP_OPTIONS = ('Win', 'Lose', 'Play')

    PROMPT_QUICK_S = 0.1        # a skip prompt's outcomes found this fast show it at once; slower, the loading band first
    prompt_job = None           # the outcome search under way: {action, future, started}

    def _search_outcomes(self, action, search, wait=False):
        """`search(session)`'s outcomes for the skip prompt of `action`, worked out on the prompt worker from a copy of the
        session; PROMPT_SEARCHING while it runs past PROMPT_QUICK_S (the loading band shows meanwhile: _loading_prompt), or
        at once with `wait`. A search that fails gives None, as the outcome functions do when they can't tell."""
        from concurrent.futures import TimeoutError as Pending
        job = self.prompt_job
        if job is None or job['action'] is not action:
            session = self.session
            vm = getattr(session, 'vm', None)
            if vm is None:
                return search(session)          # (a stand-in session, as tests use: nothing to copy)
            copy = deepcopy(session, {id(session.resources): session.resources, id(vm.program): vm.program})
            copy.ephemeral = True
            job = self.prompt_job = dict(action=action, future=_prompt_worker().submit(search, copy),
                                         started=pygame.time.get_ticks())
        try:
            outcomes = job['future'].result(timeout=None if wait else 0 if job.get('waited') else self.PROMPT_QUICK_S)
        except Pending:
            job['waited'] = True
            return PROMPT_SEARCHING
        except Exception:               # noqa: BLE001 -- a search that fails: the prompt offers what it can without one
            outcomes = None
        self.prompt_job = None
        return outcomes

    def _loading_prompt(self, action):
        """A stand-in prompt while its outcomes are worked out: it holds the game as the prompt does, takes no picks, and is
        drawn as the loading band (render)."""
        self.host_prompt = dict(action=action, session=None, options=(), resolve=lambda index: None, loading=True)
        return self.host_prompt

    def _host_prompt(self, wait=False):
        """The host prompt over the pending screen, or None; the mini-game prompt opens the first time a football game,
        word grid or word quiz (service 71, both games) is seen. `wait`: don't stand in while its outcomes are worked out."""
        action = self.session.pending
        prompt = self.host_prompt
        if prompt is not None and (prompt['action'] is not action or prompt.get('loading')):
            prompt = self.host_prompt = None
        if (prompt is None and self.skip_minigames and action is not None
                and action.name in ('football', 'word_grid', 'word_game')
                and self.minigame_played is not action and not self.error):
            if action.name == 'word_game':
                # shshd-runtime: a quiz offers each outcome its story has (choice_hints.word_game_outcomes): most have
                # two, some three (Football Star's movie date: 0-3, 4-5, 6 or more), a vote package's one.
                outcomes = self._search_outcomes(action, word_game_outcomes, wait)
                if outcomes is PROMPT_SEARCHING:
                    return self._loading_prompt(action)
                options, scores = word_game_options(outcomes)
                prompt = self._open_prompt(action, 'Skip this mini-game?', self._minigame_summary(action, outcomes),
                                           options, lambda index: self._resolve_word_game(action, scores, index))
            else:
                prompt = self._open_prompt(action, 'Skip this mini-game?', self._minigame_summary(action),
                                           self.SKIP_OPTIONS, lambda index: self._resolve_minigame(action, index))
        if (prompt is None and self.skip_minigames and action is not None and action.name == 'x360_slot'
                and self.minigame_played is not action and self.session.minigame_unstarted and not self.error):
            # shshd-runtime: the X360's slot machine offers each outcome its story has.
            outcomes = self._search_outcomes(action, x360_slot_outcomes, wait)
            if outcomes is PROMPT_SEARCHING:
                return self._loading_prompt(action)
            options, points = arena_skip_options(outcomes)
            options = tuple(option.replace(' or more', '') for option in options)       # (5 is all there is)
            prompt = self._open_prompt(action, 'Skip this mini-game?', 'The slot machine: hit the light bulbs.', options,
                                       lambda index: self._resolve_x360_slot(action, points, index))
        if (prompt is None and self.skip_minigames and action is not None and action.name in ('shs11_memory', 'shs11_reflex')
                and self.minigame_played is not action and self.session.minigame_unstarted and not self.error):
            # shshd-runtime: SHS '11's games offer each result their story treats differently.
            outcomes = self._search_outcomes(action, shs11_outcomes, wait)
            if outcomes is PROMPT_SEARCHING:
                return self._loading_prompt(action)
            options, results = shs11_skip_options(outcomes, getattr(getattr(self.session.engine, action.name), 'best_result', 2))
            prompt = self._open_prompt(action, 'Skip this mini-game?', self._minigame_summary(action, len(results)), options,
                                       lambda index: self._resolve_shs11(action, results, index))
        if (prompt is None and self.skip_minigames and action is not None and action.name == 'brew_catch'
                and self.minigame_played is not action and self.session.minigame_unstarted and not self.error):
            # shshd-runtime: it offers each outcome its story has (choice_hints.brew_catch_outcomes): most two, some three.
            target = self.session.engine.brew_catch.target
            outcomes = self._search_outcomes(action, brew_catch_outcomes, wait)
            if outcomes is PROMPT_SEARCHING:
                return self._loading_prompt(action)
            options, scores = brew_catch_skip_options(outcomes, target)
            prompt = self._open_prompt(action, 'Skip this mini-game?', self._brew_catch_summary(outcomes, target),
                                       options, lambda index: self._resolve_brew_catch(action, scores, index))
        if (prompt is None and self.skip_minigames and action is not None and action.name == 'x360_leash'
                and self.minigame_played is not action and self.session.minigame_unstarted and not self.error):
            prompt = self._open_prompt(action, 'Skip this mini-game?', 'The leash: shake the way the arrows point.',
                                       self.SKIP_OPTIONS, lambda index: self._resolve_x360_leash(action, index))
        if (prompt is None and self.skip_minigames and action is not None and action.name == 'x360_diss'
                and self.minigame_played is not action and self.session.minigame_unstarted and not self.error):
            prompt = self._open_prompt(action, 'Skip this mini-game?', 'Diss practice: catch the good notes with the needle.',
                                       self.SKIP_OPTIONS, lambda index: self._resolve_x360_diss(action, index))
        if (prompt is None and self.skip_minigames and action is not None and action.name == 'x360_puzzle'
                and self.minigame_played is not action and self.session.minigame_unstarted and not self.error):
            prompt = self._open_prompt(action, 'Skip this mini-game?', 'A jewel puzzle. Its score changes nothing that follows.',
                                       ('Skip', 'Play'), lambda index: self._resolve_x360_puzzle(action, index))
        if prompt is None and action is not None and action.name == 'arena_skip' and not self.error:
            if self.skip_minigames and hasattr(self.session.resources, 'read_asset'):
                # shshd-runtime: a New Rules arena game offers each outcome its story has (choice_hints.arena_outcomes,
                # the results 0-15): most two, a few three.
                outcomes = self._search_outcomes(action, arena_outcomes, wait)
                if outcomes is PROMPT_SEARCHING:
                    return self._loading_prompt(action)
                options, results = arena_skip_options(outcomes)
                prompt = self._open_prompt(action, 'Skip this mini-game?', self._arena_summary(outcomes), options,
                                           lambda index: self._resolve_arena_skip(action, results, index))
            else:
                self._attempt(lambda: self.session.answer(-1))     # switched off meanwhile: it plays
        if (prompt is None and action is not None and action.name == 'arena_menu' and not self.error
                and hasattr(self.session.resources, 'read_asset')):
            # shshd-runtime (owner, 2026-10-31): New Rules' menu over the arena (its tutorial offer) is SHS's choice,
            # drawn over the arena (render's under_layer); the pick goes back to the library as its option's index.
            title, text, options = arena_menu_prompt(action.details)
            prompt = self._open_prompt(action, title, text, options,
                                       lambda index: self._resolve_arena_menu(action, index))
        return prompt

    @staticmethod
    def _arena_summary(outcomes):
        """What the arena game about to start decides, for its skip prompt."""
        game = 'A New Rules minigame, in its arena.'
        if outcomes is None or len(outcomes) == 2:
            passed = f' (a result of {outcomes[1][0]} or more)' if outcomes else ''
            return f'{game} Win passes it{passed}; Lose fails it.'
        if len(outcomes) == 1:
            return f'{game} Its result changes nothing that follows.'
        return f'{game} Its story goes {len(outcomes)} ways, by result.'

    def _resolve_arena_skip(self, action, results, index):
        """The arena game's skip prompt: an outcome hands its story that result instead of the game; Play plays it."""
        if self.session.pending is action:
            value = results[index] if index < len(results) else -1
            self._attempt(lambda: self.session.answer(value))

    def _resolve_x360_slot(self, action, points, index):
        """The slot machine's skip prompt: an outcome hands its story those points; Play plays it."""
        if self.session.pending is not action:
            return
        if index >= len(points):
            self.minigame_played = action
            self.session.engine.x360_slot.start()       # the prompt was its go-ahead: no second one
            return
        self._attempt(lambda: self.session.skip_x360_slot(points[index]))

    def _resolve_shs11(self, action, results, index):
        """An SHS '11 game's skip prompt: an outcome finishes it with that result, Play plays it."""
        if self.session.pending is not action:
            return
        if index >= len(results):
            self.minigame_played = action
            return
        self._attempt(lambda: self.session.skip_shs11(results[index]))

    @staticmethod
    def _brew_catch_summary(outcomes, target):
        """What the catch game about to start decides, for its skip prompt."""
        game = 'The catch game: catch the good things, dodge the bad.'
        if outcomes is None or len(outcomes) == 2:
            return f'{game} Win scores {target}; Lose scores nothing.'
        if len(outcomes) == 1:
            return f'{game} Its score changes nothing that follows.'
        return f'{game} Its story goes {len(outcomes)} ways, by score (at most {target}).'

    def _resolve_brew_catch(self, action, scores, index):
        """The catch game's skip prompt: an outcome finishes it with that score (brew_catch_skip_options), Play plays it."""
        if self.session.pending is not action:
            return
        if index >= len(scores):
            self.minigame_played = action
            return
        self._attempt(lambda: self.session.skip_brew_catch(scores[index]))

    def _resolve_x360_leash(self, action, index):
        """The leash game's skip prompt: Win / Lose finish it with that result, Play plays it."""
        if self.session.pending is not action:
            return
        if index == 2:
            self.minigame_played = action
            self.session.engine.x360_leash.start()      # the prompt was its go-ahead: no second one
            return
        self._attempt(lambda: self.session.skip_minigame(index == 0))

    def _resolve_x360_diss(self, action, index):
        """Diss Practice's skip prompt: Win / Lose finish it with that result, Play plays it."""
        if self.session.pending is not action:
            return
        if index == 2:
            self.minigame_played = action
            self.session.engine.x360_diss.start()       # the prompt was its go-ahead: no second one
            return
        self._attempt(lambda: self.session.skip_minigame(index == 0))

    def _resolve_x360_puzzle(self, action, index):
        """The jewel puzzle's skip prompt: Skip goes straight on, Play plays it."""
        if self.session.pending is not action:
            return
        if index == 1:
            self.minigame_played = action
            self.session.engine.x360_puzzle.start()     # the prompt was its go-ahead: no second one
            return
        self._attempt(lambda: self.session.skip_minigame(False))

    def _resolve_arena_menu(self, action, index):
        if self.session.pending is action:
            details = action.details
            taken = ('view tutorial' in (details.get('title') or '').casefold()
                     and details['options'][index].casefold() == 'yes' and self._x360_swaps() is not None)
            self.x360_tutorial = self.session.engine.music_serial if taken else None
            if taken:
                self.x360_arena_renderer.hits.clear()   # (the game before's)
            self._attempt(lambda: self.session.answer(index))

    PROMPT_PAGE = 5             # outcomes on a page of a skip prompt with more than PROMPT_ROWS rows
    PROMPT_ROWS = 7
    # The HD panel's height limit for these prompts, past the native 964 points: seven rows under a four-line description (a catch
    # game's, with its page) need 975 (owner, 2026-11-07: a bit taller rather than a scroll).
    PROMPT_PANEL_LIMIT = 984

    def _open_prompt(self, action, title, text, options, resolve, page=0):
        """A narrator-style choice (no character: the gold theme, no portrait) over `action`; `resolve(index)` runs
        once the pick has closed it. A skip prompt with more outcomes than its panel shows at once (more than
        PROMPT_ROWS rows, its last Play) goes in pages of PROMPT_PAGE outcomes, each with Next Page (the last back to the
        first) and Play (owner, 2026-11-07: M.A.S.H.'s catch games go fifteen ways)."""
        options = tuple(options)
        if len(options) > self.PROMPT_ROWS and options[-1] == 'Play':
            outcomes, size = options[:-1], self.PROMPT_PAGE
            pages = -(-len(outcomes) // size)
            shown = outcomes[page * size:(page + 1) * size]

            def turn(index):
                if index < len(shown):
                    resolve(page * size + index)
                elif index == len(shown):
                    # The next page is there at once: no closing, fade-in or fly-on (owner, 2026-11-07: paging felt slow).
                    self._open_prompt(action, title, text, options, resolve, (page + 1) % pages)['instant'] = True
                else:
                    resolve(len(outcomes))                  # Play
            prompt = self._open_prompt(action, title, f'{text} Page {page + 1} of {pages}.', shown + ('Next Page', 'Play'),
                                       turn)
            prompt['next_row'] = len(shown)
            return prompt
        details = dict(title=title, text=text, options=list(options), values=list(range(len(options))),
                       enabled=[True] * len(options), timeout_ms=0, timeout_result=0, character_id=-1, portrait_mode=0,
                       panel_limit=self.PROMPT_PANEL_LIMIT)
        stand_in = SimpleNamespace(pending=SimpleNamespace(name='choice', details=details, request=None),
                                   engine=_PromptEngine(self.session.engine), vm=SimpleNamespace(steps_executed=0),
                                   scene=self.session.scene, remaining_ms=None, resources=self.session.resources)
        self.host_prompt = dict(action=action, session=stand_in, options=tuple(options), resolve=resolve)
        return self.host_prompt

    def _pick(self, action, index):
        """Answer the script's choice: the ad's "Play the Surviving High School episode!" first asks whether to skip
        these intros from now on (ad_intro.py), unless the player already chose to. Disable Choice Timer's last row
        lets the time run out."""
        if self._timeout_row(action, index):
            self._attempt(self.session.expire_choice)
            return
        if play_option(action) == index and not self.skip_ad_intros and self.ad_asked is not action:
            self.ad_asked = action
            self._open_prompt(action, 'Skip ad intros?',
                              'Go straight to the title card when an episode opens with High School Story news? '
                              'It can be turned off again in Options.', ('Yes', 'No'),
                              lambda answer: self._resolve_ad(action, index, answer))
            return
        self._answer(index)

    def _resolve_ad(self, action, index, answer):
        if answer == 0:
            self.skip_ad_intros = True
            if self.on_settings:
                self.on_settings()
        if self.session.pending is action:
            self._answer(index)

    def _minigame_summary(self, action, outcomes=None):
        """What the game about to start holds, for the skip prompt: football's half and starting score, the quiz's
        outcomes (word_game_outcomes), the grid's target and its puzzles' words."""
        engine = self.session.engine
        if action.name == 'football':
            game = engine.football
            try:
                from .shs.football_layout import team_name
                strings = self._football().strings()
                home, away = team_name(strings, game.teams[0]) or 'Home', team_name(strings, game.teams[1]) or 'Away'
            except (ContentError, pygame.error, OSError, ValueError, AttributeError, IndexError):
                home, away = 'Home', 'Away'
            half = {1: 'First half', 2: 'Second half'}.get(game.half, 'Overtime')
            side = 'defense' if game.defense else 'offense'
            return f'Football. {half}, starting on {side}. {home} {game.home}, {away} {game.away}.'
        if action.name == 'word_game':
            game = engine.word_game
            seconds = round(game.duration_ms / 1000)
            quiz = f'Word quiz. Pick the right word, again and again, for {seconds} seconds.'
            if outcomes is None or len(outcomes) == 2:
                passed = f' (a score of {outcomes[1][0]} or more)' if outcomes else ''
                return f'{quiz} Win passes it{passed}; Lose scores nothing.'
            if len(outcomes) == 1:
                return f'{quiz} Its score changes nothing that follows.'
            return f'{quiz} Its story goes {len(outcomes)} ways, by score.'
        if action.name == 'shs11_memory':
            game = engine.shs11_memory
            words = list(dict.fromkeys(round_[1] for round_ in game.rounds))
            shown = ', '.join(words[:8]) + (' ...' if len(words) > 8 else '')
            return f'Memory. Score {game.win_score} in {round(game.clock_ms / 1000)} seconds. Words: {shown}.'
        if action.name == 'shs11_reflex':
            game = engine.shs11_reflex
            middle = f' {game.close_score} or more comes close.' if outcomes == 3 else ''
            return (f'Reflex. Score {game.win_score} in {round(game.clock_ms / 1000)} seconds, '
                    f'picking the right icons to fill the gauge.{middle}')
        game = engine.word_grid
        words = []
        for problem in game.problems:
            for word in problem.words:
                if word.upper() not in words:
                    words.append(word.upper())
        shown = ', '.join(words[:8]) + (' ...' if len(words) > 8 else '')
        seconds = round(game.remaining_ms / 1000)
        return f'Word game. Score {game.target} in {seconds} seconds. Words: {shown}.'

    def _resolve_word_game(self, action, scores, index):
        """The quiz's skip prompt: an outcome finishes it with that score (word_game_options), Play starts it."""
        if self.session.pending is not action:
            return
        if index >= len(scores):
            self.minigame_played = action
            return
        self._attempt(lambda: self.session.skip_word_game(scores[index]))

    def _resolve_minigame(self, action, index):
        """The skip prompt's answer: Win / Lose finish the game with that result, Play starts it."""
        if self.session.pending is not action:
            return
        if index == 2:
            self.minigame_played = action
            return
        self._attempt(lambda: self.session.skip_minigame(index == 0))

    def _hd_choice_closes(self, action, index):
        """Whether a pick of `index` closes the HD choice panel natively (pressed row, then a fade) rather than at once:
        an enabled row of an HD-drawn choice."""
        return self._choice_pickable(action, index) and self._hd_choice_drawn()

    @staticmethod
    def _choice_enabled(action, index):
        enabled = action.details.get('enabled', ())
        return 0 <= index < len(enabled) and bool(enabled[index])

    def _choice_pickable(self, action, index):
        return self._choice_enabled(action, index) or self._timeout_row(action, index)

    def _hd_choice_drawn(self):
        return hasattr(self.choice_renderer.cached_page, 'rows_top')

    def _tick_choice_closing(self, elapsed_ms):
        closing = self.choice_closing
        if closing['action'] is not self.session.pending:
            self.choice_closing = None          # loaded, restarted or answered elsewhere
            return
        closing['ms'] += elapsed_ms
        if closing['ms'] >= SELECT_MS + TRANSITION_MS:
            self.choice_closing = None
            if closing.get('prompt'):           # a host prompt (not the script's choice)
                self.host_prompt = None
                closing['prompt']['resolve'](closing['index'])
            elif closing['index'] is None and closing['action'].name == 'choice':     # timed out: run out now
                self._attempt(self.session.expire_choice)
            elif closing['index'] is None:      # the quiz's clock: let it run out now, as before
                self._attempt(lambda: self.session.tick(max(1, self.session.remaining_ms or 0)))
            else:
                self._pick(closing['action'], closing['index'])

    def _release_choice(self):
        """Show a held choice again as a new menu is: the panel fades in, its labels fly on and taps wait out its
        attachment."""
        held, self.choice_held = self.choice_held, None
        if held['action'] is self.session.pending:          # (not loaded, restarted or answered elsewhere)
            self.choice_renderer.age_ms = 0
            self.session.engine.choice_ms = 0

    def _tick_autoplay(self, elapsed_ms):
        """Autoplay Dialogue: once a dialogue page's text is out (or a title card or message panel is ready), wait
        AUTOPLAY_WAIT_MS (a title card AUTOPLAY_TITLE_WAIT_MS), then advance it as a tap would. Anything that wants an answer (a choice, name entry, a
        mini-game, the portrait picker) waits for the player as usual."""
        action, engine = self.session.pending, self.session.engine
        ready = False
        if self.autoplay and action is not None and not self.session.transitioning and self.host_prompt is None:
            if action.name == 'dialogue':
                ready = engine.dialogue_animation is not None and engine.dialogue_animation.complete
            elif action.name in ('message_panel', 'survey_confirmation'):
                ready = engine.message_panel is not None and engine.message_panel.ready
            elif action.name == 'presentation':
                ready = engine.title_screen is not None and engine.title_screen.ready
            elif action.name == 'cutscene':
                ready = engine.cutscene is not None and engine.cutscene.held
        if not ready:
            self.autoplay_ms = 0
            return
        self.autoplay_ms += elapsed_ms
        wait = self.AUTOPLAY_TITLE_WAIT_MS if action.name in ('presentation', 'cutscene') else self.AUTOPLAY_WAIT_MS
        if self.autoplay_ms >= wait:
            self.autoplay_ms = 0
            self._answer()

    def _sync_cutscene(self):
        """A cutscene that names a track runs on that track's position, so its sounds land on their beats. With Music off, or
        once a press has jumped, it runs on the session's clock."""
        action = self.session.pending
        if action is None or action.name != 'cutscene':
            return
        stream = self.music_stream
        if stream.current is None or stream.paused:
            return
        game = self.session.engine.cutscene
        if game is not None and stream.current['id'] == game.music:
            game.sync(round(stream.position() * 1000))

    def _tick_fade(self, elapsed_ms):
        fade = self.fade
        ms = pygame.time.get_ticks() - fade['since']
        if fade['phase'] == 'out' and ms >= scene_fade.out_ms(fade['kind']):
            fade.update(phase='in', since=pygame.time.get_ticks(), frozen=None)
        elif fade['phase'] == 'in' and ms >= scene_fade.in_ms(fade['kind']):
            self.fade = None

    def _draw_fade(self):
        fade = self.fade
        if fade['frozen'] is not None:
            self.window.blit(fade['frozen'], (0, 0))
        ms = pygame.time.get_ticks() - fade['since']
        self._draw_cover(fade['kind'], scene_fade.coverage(fade['kind'], fade['phase'], ms))

    def _fade_minigame(self, action, renderer):
        """HD's minigame is a view over the scene: `internalTransitionOn` eases its alpha up over 0.8 s, and `finishGame`
        eases it back to 0 over 0.8 s (UIKit's curve 0, 1.4.38 00048728 / 000485b0), the callback following at 960 ms."""
        engine = self.session.engine
        game = engine.football if action.name == 'football' else engine.word_grid
        faded(renderer.canvas, None)                # (a plain surface keeps the whole-surface alpha it was last given)
        now = pygame.time.get_ticks()
        if self.minigame_shown is None or self.minigame_shown[0] is not game:
            self.minigame_shown = (game, now)
        if game.phase == MINIGAME_EXITS[action.name]:
            alpha = 1 - ease_in_out((MINIGAME_EXIT_MS - game.phase_ms) / MINIGAME_FADE_MS)
        else:
            alpha = ease_in_out((now - self.minigame_shown[1]) / MINIGAME_FADE_MS)
        if alpha < 1 and not self.capture:
            self.panel_alpha = alpha
            background = self.dialogue_renderer.image(engine.panel.background_id)
            self.pending_background = background
            self.pending_background_origin = self.dialogue_renderer.background_origin(background, engine)

    def _draw_loading_handover(self):
        """The band closing over what follows it (`hideLoadingScreen`: desktop_loading.LOADING_CLOSE_MS)."""
        handover = self.loading_handover
        action = self.session.pending
        if handover is None or (action is not None and action.name == 'loading') or not hasattr(self, 'bg_viewport'):
            return
        now = pygame.time.get_ticks()
        if handover['since'] is None:
            handover['since'] = now
        ms = now - handover['since']
        if ms >= LOADING_CLOSE_MS or self.capture:
            self.loading_handover = None
            return
        area = getattr(self, 'picture_frame', self.bg_viewport)
        scale = 1 - ease_in_out(ms / LOADING_CLOSE_MS)
        height = max(1, round(area.height * scale))
        band = pygame.transform.smoothscale(handover['layer'], (area.width, height))
        self.window.blit(band, (area.x, area.y + round(area.height * (1 - scale) / 2)))

    def _draw_arena_handover(self):
        """The arena's last picture fading out over the screen that follows it (ARENA_HANDOVER_MS)."""
        handover = getattr(self, 'arena_handover', None)
        action = self.session.pending
        if (handover is None or (action is not None and action.name in ARENA_ACTIONS)
                or not hasattr(self, 'bg_viewport')):
            return
        now = pygame.time.get_ticks()
        if handover['since'] is None:
            handover['since'] = now
        ms = now - handover['since']
        if ms >= ARENA_HANDOVER_MS or self.capture:
            self.arena_handover = None
            return
        area = getattr(self, 'picture_frame', self.bg_viewport)
        if handover['scaled'] is None or handover['scaled'].get_size() != area.size:
            handover['scaled'] = pygame.transform.smoothscale(handover['layer'], area.size)
        self.window.blit(faded(handover['scaled'], round(255 * (1 - ms / ARENA_HANDOVER_MS))), area)

    def _draw_transition(self):
        """The session's queued transition over the frame (fade_transition.FadeTransition; Android's has no layers)."""
        transition = self.session.engine.scene_transition
        if transition is not None and transition.active and transition.coverage > 0:
            self._draw_cover(transition.selector, transition.coverage)

    def _ui_closed(self, action):
        """Whether `action` is an answered menu, entry or picker waiting under the queued fade-out: it has closed
        (the menu's view faded out, the entry's panel gone), so only the scene shows under the closing blinds."""
        transition = self.session.engine.scene_transition
        return (action is not None and transition is not None and transition.phase == 4
                and action.name in ('choice', 'text_input', 'character_picker', 'word_game'))

    def _draw_cover(self, kind, amount):
        area = getattr(self, 'bg_viewport', self.window.get_rect()).clip(self.window.get_rect())
        if kind == 6:
            shade = pygame.Surface(area.size)
            shade = faded(shade, round(255 * amount))
            self.window.blit(shade, area)
        else:
            for x, y, w, h in scene_fade.blind_rects(kind, amount, area.size):
                self.window.fill((0, 0, 0), (area.x + x, area.y + y, w, h))

    def _submit_input(self, action):
        if self.input_error:
            self.input_error, self.input_keyboard = None, True
            return
        value = action.details.get('draft', action.details['default'])
        if not value:
            self.input_keyboard = False  # Empty Return hides the native keyboard.
            return
        try:
            validate_name(value, **self.session.name_input_metrics())
        except ValueError as error:
            self.input_error, self.input_keyboard = str(error), False
            return
        self._attempt(lambda: self.session.answer(value))

    def _menu_sound(self, *, opening=False):
        self._ui_sound('PAUSE_SOUND' if opening else 'CLICK_SOUND')

    def _ui_sound(self, name, *, volume=None, stop_others=False, when_idle=False):
        """Play the game profile's interface sound `name` from the base bank (ui_sound.py): at the Sound FX volume,
        and only with Sound on, unless a `volume` of its own is given (the Music slider's preview)."""
        library = self.session.resources.library
        if not self.audio or not hasattr(library, 'read_asset') or (volume is None and not self.sound_enabled):
            return
        asset = getattr(GAMES[game_id(self.session.resources)], name)
        self.ui_sounds.play(library, asset, self.sound_volume if volume is None else volume,
                            stop_others=stop_others, when_idle=when_idle)

    # A speaker's bubble may hold extra rows in a frame taller than HD's (owner, 2026-11-11): as many whole rows (HD's
    # 26-unit line step) as fit in this share of the height the frame adds.
    EXTRA_ROWS_SHARE = .5
    ROW_UNITS = 26

    def _sync_story_scale(self):
        """The story's renderers draw the frame 768 pixels wide whatever its width in units (General's Aspect Ratio:
        384 at 3:4 and 2:3, 2 pixels a unit; 320 from 9:16, 2.4), so on a phone, whose drawing surface is 768 pixels
        wide, their layers need no resampling; `_edge_units` is the frame's margin each side of the column (32, 0)."""
        width, tall = self.frame_units()
        self._edge_units = (width - 320) / 2
        self.session.dialogue_extra_rows = max(0, int((tall - FRAME_UNITS[1]) * self.EXTRA_ROWS_SHARE / self.ROW_UNITS))
        # A narrator's bubble keeps HD's distance from the frame's edge (its 32-unit margin less this frame's) and is
        # centred in a taller frame as the choice is (owner, 2026-11-11: it was cut at a phone's edge, and low).
        self.session.narration_offset = (FRAME_UNITS[0] / 2 - 160 - self._edge_units,
                                         (tall - FRAME_UNITS[1]) / 2)
        self.dialogue_renderer.lift = 0
        for card in (getattr(self, 'title_hd', None), getattr(self, 'title_cod', None),
                     getattr(self, 'cutscene_renderer', None)):
            if card is not None:
                card.frame_units = (width, tall)        # drawn over the whole frame, its shape (desktop_title)
        scale = STORY_SCALE * FRAME_UNITS[0] / width
        self.dialogue_renderer.edge_units = self._edge_units        # its bar's margins (cached with its scale)
        for renderer in (self.dialogue_renderer, self.choice_renderer, self.input_renderer, self.message_renderer):
            set_story_scale(renderer, scale)

    def render(self):
        self._sync_story_scale()
        self.buttons = []
        action = self.session.pending
        if self.session.engine.panel.background_id >= 0:
            self.last_background_id = self.session.engine.panel.background_id
        self._sync_text_input()
        token = self._screen_token()
        self.press.validate(self._press_token())
        self.dialogue_renderer.gear_pressed = self.press.pressed == ('menu',) and not self.menu_open
        if token != self.screen_token:
            self.screen_token, self.scroll, self.choice_focus = token, 0, None
        self.canvas.fill((0, 0, 0, 0))
        self.story_layer = None
        self.story_over_scene = False
        self.story_fills_frame = False
        self.story_centred = False
        self.story_lift = 0
        self.under_layer = None
        self.edge_layer = None
        self.pending_background = None
        self.pending_background_alpha = 255
        details = action.details if action else {}
        ask = self._host_prompt()
        closed = self._ui_closed(action)
        if ask and action.name in ARENA_ACTIONS and not self.error:
            # The arena's menu as SHS's choice (_host_prompt): the arena, without its own menu, under the choice.
            try:
                renderer = self._arena_renderer()
                renderer.draw(None, self.session, overlay=False)
                self.under_layer = renderer.canvas
            except (ContentError, pygame.error, OSError, ValueError) as error:
                self.error = str(error)
                logging.error('Panel rendering stopped: %s', error)
        if ask and ask.get('loading') and not self.error:
            # A skip prompt's outcomes being worked out (_search_outcomes): service 91's loading band over the scene (HD's, or
            # Android's where HD's can't be drawn, as service 91 picks), from a stand-in for the state it reads, as the poll's
            # bar is; it takes no clicks but the gear.
            job = self.prompt_job or {}
            elapsed = max(0, pygame.time.get_ticks() - job.get('started', pygame.time.get_ticks()))
            renderer = self.loading_hd if self.loading_hd.available() else self.loading_renderer
            loading = LoadingScreen(blocking=False, elapsed_ms=min(3000, elapsed))
            loading.elapsed_ms = elapsed                    # (its own clock, past service 91's 3 s cap: the runner keeps running)
            view = SimpleNamespace(engine=SimpleNamespace(panel=self.session.engine.panel, loading=loading))
            buttons = renderer.draw(self.canvas, view) or [((-32, 422, 92, 58), ('menu',))]     # (the gear: the pause menu)
            if getattr(renderer, 'hd_layer', False):
                self.story_layer = renderer.canvas
            self.pending_background = getattr(renderer, 'pending_background', None)
            self.pending_background_origin = getattr(renderer, 'pending_background_origin', (160, 180))
            self.buttons = [(pygame.Rect(*(round(value * 1.5) for value in rect)), command) for rect, command in buttons]
            edge_bar = getattr(renderer, 'edge_bar', None)
            if edge_bar:
                # No hint under it: service 91's "Touch the screen to continue" asks for a tap this band doesn't take.
                self.edge_layer = self.dialogue_renderer.bottom_bar_layer('', self.dialogue_renderer.gear_pressed,
                                                                          edge_bar == 'bar')
            self.scroll = self.max_scroll = 0
            self._present()
            return
        if action and not ask and not closed and action.name in ('word_grid', 'football', 'character_picker', 'loading', 'download_poll', 'message_panel', 'survey_confirmation', 'presentation', 'text_input', *ARENA_ACTIONS) and not self.error:
            try:
                # A dict of values here would build every branch eagerly -- each an `available()` gate that
                # reads and (pre-caching) re-decompressed an HD resource -- for the one the dict ends up
                # indexing out; a dict of zero-argument callables evaluates only the selected action's own.
                message = lambda: (self.message_hd if self.message_hd.available()
                                   else self.message_cod if self.message_cod.available() else self.message_renderer)
                selectors = {
                    'word_grid': self._word_grid, 'football': self._football, 'character_picker': self._picker,
                    'loading': lambda: self.loading_hd if self.loading_hd.available() else self.loading_renderer,
                    'download_poll': lambda: self.loading_hd if self.loading_hd.available() else self.loading_renderer,
                    'message_panel': message, 'survey_confirmation': message,
                    'presentation': self._title_renderer,
                    'text_input': lambda: self.input_renderer,
                    **{name: self._arena_renderer for name in ARENA_ACTIONS},
                }
                renderer = selectors[action.name]()
                options = (dict(error=self.input_error,
                                cursor_visible=self.text_input_started and pygame.time.get_ticks() % 1000 < 500,
                                choice_hints=self.choice_hints)
                           if action.name == 'text_input' else {})
                # The name-entry screen draws at story density (see STORY_SCALE)
                # and is composited by _present(), like dialogue and choices.
                if action.name == 'download_poll':
                    # `showLoadingBar` is the same band and runner wheel as service 91's overlay. The loading renderers are drawn
                    # from a stand-in for the state they read (the scene's background and the runner's frame), so service 91's own
                    # state and drawing are untouched; the poll's bar takes no clicks (`g_pauseButton setEnabled:NO`).
                    engine = self.session.engine
                    poll = LoadingScreen(blocking=False, elapsed_ms=min(3000, details['elapsed_ms']))
                    poll.elapsed_ms = details['elapsed_ms']        # the poll's own clock, past service 91's 3 s cap
                    view = SimpleNamespace(engine=SimpleNamespace(panel=engine.panel, loading=poll))
                    renderer.draw(self.canvas, view)
                    buttons = []
                elif action.name == 'presentation' and self._date_first(details):
                    buttons = renderer.draw(self.canvas, _DateFirstCard(self.session))
                else:
                    buttons = renderer.draw(None if action.name == 'text_input' else self.canvas,
                                            self.session, **options)
                if action.name == 'text_input' or getattr(renderer, 'hd_layer', False):
                    self.story_layer = renderer.canvas
                    self.story_over_scene = getattr(renderer, 'over_scene', False)
                    self.story_fills_frame = getattr(renderer, 'fills_frame', False)
                    if action.name == 'character_picker':
                        # A taller frame centres the picker as HD's frame does (owner, 2026-11-11): its layer moves
                        # up by half the height added (its taps follow, _picker_point).
                        self.story_lift = (self.__dict__.get('_frame_tall', FRAME_UNITS[1]) - FRAME_UNITS[1]) / 2
                if action.name in ARENA_ACTIONS:
                    self.arena_handover = dict(layer=renderer.canvas, since=None, scaled=None)
                self.pending_background = getattr(renderer, 'pending_background', None)
                self.pending_background_origin = getattr(renderer, 'pending_background_origin', (160, 180))
                self.pending_background_alpha = getattr(renderer, 'pending_background_alpha', 255)
                if action.name in MINIGAME_EXITS and getattr(renderer, 'hd_layer', False):
                    self._fade_minigame(action, renderer)
                elif action.name == 'loading' and renderer is self.loading_hd:
                    self.loading_handover = dict(layer=renderer.canvas, since=None)
                if action.name == 'text_input':
                    # The gear opens the pause menu here too (owner, 2026-10-29). The originals leave it inert, but their
                    # keyboard covered it; this player's gear stays in sight (on a desktop always), so an inert one read as
                    # broken. The pause menu stops text input, which hides the keyboard (_sync_text_input) until Resume.
                    buttons = [*buttons, ((-32, 422, 92, 58), ('menu',))]
                # The gear's button is at the frame's left edge, 32 units outside the column in HD's frame.
                buttons = [((rect[0] + 32 - self._edge_units, *rect[1:]) if command == ('menu',) and rect[0] == -32
                            else rect, command) for rect, command in buttons]
                self.buttons = [(pygame.Rect(*(round(value * 1.5) for value in rect)), command)
                                for rect, command in buttons]
                edge_bar = getattr(renderer, 'edge_bar', None)
                if edge_bar:
                    # Bar and gear (or the gear alone) run to the frame's edges;
                    # the renderer's own canvas draws any hint text over them.
                    self.edge_layer = self.dialogue_renderer.bottom_bar_layer(
                        getattr(renderer, 'footer_text', ''), self.dialogue_renderer.gear_pressed,
                        edge_bar == 'bar')
                self.scroll = self.max_scroll = 0
                self._present()
                return
            except (ContentError, pygame.error, OSError, ValueError) as error:
                self.error = str(error)
                logging.error('Panel rendering stopped: %s', error)
        # The skip prompt (`_minigame_ask`) is drawn as a choice, from a stand-in for the session.
        source = ask['session'] if ask else self._choice_source()
        if (action and (action.name in ('choice', 'word_game') or ask) and not self.error and not closed
                and not (ask and ask.get('loading'))
                and hasattr(self.session.resources, 'read_asset')):
            try:
                page = self.choice_renderer.page(source)
                if ask and ask.get('instant'):
                    self.choice_renderer.age_ms, ask['instant'] = 60_000, False      # a prompt's next page: shown at once
                self.max_scroll = page.max_scroll * 1.5
                self.scroll = min(self.scroll, self.max_scroll)
                # A taller frame centres the choice as HD's frame does (owner, 2026-11-11): its layer, its rows' taps
                # and its timer move up by half the height added; the gear stays at the bottom.
                lift = (self.__dict__.get('_frame_tall', FRAME_UNITS[1]) - FRAME_UNITS[1]) / 2
                pointer = None
                if hasattr(self, 'viewport') and self.press.origin is None and not self.menu_open:
                    x, y = pygame.mouse.get_pos()
                    if self.viewport.collidepoint(x, y):
                        pointer = ((x - self.viewport.x) * 320 / self.viewport.width,
                                   (y - self.viewport.y) * 480 / self.viewport.height + lift)
                closing = self.choice_closing if self.choice_closing and self.choice_closing['action'] is action else None
                if closing is None and self.choice_held is not None and self.choice_held['action'] is action:
                    closing = dict(index=self.choice_held['index'], ms=SELECT_MS + TRANSITION_MS)     # faded out
                pressed = self.press.pressed if not self.menu_open else None
                focus = self.choice_focus if not self.menu_open else None
                if focus is not None:
                    pointer = None
                if closing is not None:
                    pointer, pressed, focus = None, ('choose', closing['index']), None
                _, buttons = self.choice_renderer.draw(None, source,
                                                        scroll=self.scroll / 1.5, pointer=pointer,
                                                        pressed=pressed, focus=focus,
                                                        choice_hints=self.choice_hints and not ask)
                if hasattr(page, 'rows_top'):
                    # HD: the menu view fades in and, after a pick, out (hd_choice.panel_alpha); the timer layers do not
                    # fade and are hidden when the fade-out starts.
                    self.panel_alpha = panel_alpha(self.choice_renderer.age_ms, closing['ms'] if closing else None)
                    if ((closing is None or closing['ms'] < SELECT_MS)
                            and (getattr(page, 'timer_center', None) is not None or getattr(page, 'scored', False))):
                        self.panel_overlay = self.choice_renderer.overlay     # (only a timer or a quiz draws on it)
                if closing is not None:
                    buttons = [button for button in buttons if button[1] == ('menu',)]
                self.hint_discount_ms += self.choice_renderer.take_hint_ms()
                self.story_layer = self.choice_renderer.wide
                self.story_lift = lift
                self.edge_layer = self.dialogue_renderer.bottom_bar_layer(self.choice_renderer.footer_text,
                                                                          self.dialogue_renderer.gear_pressed)
                self.pending_background = self.choice_renderer.pending_background
                self.pending_background_origin = self.choice_renderer.pending_background_origin
                buttons = [(rect if command == ('menu',) else (rect[0], rect[1] - lift, rect[2], rect[3]), command)
                           for rect, command in buttons]
                self.buttons = [(pygame.Rect(*(round(value * 1.5) for value in rect)), command)
                                for rect, command in buttons]
                if pygame.time.get_ticks() < self.message_until:
                    self._text(self.message, 90, 672, 375, font=self.small)
                self._present()
                return
            except (ContentError, pygame.error, OSError, ValueError) as error:
                self.error = str(error)
                logging.error('Choice rendering stopped: %s', error)
        if action and action.name == 'cutscene' and not ask and not closed and not self.error:
            try:
                engine = self.session.engine
                self.cutscene_renderer.draw(self.session)
                self.story_layer = self.cutscene_renderer.canvas
                self.story_centred = True           # no taller than its spec serves: centred, backdrop round it
                self.panel_alpha = None
                self.pending_background = self.dialogue_renderer.image(engine.panel.background_id)
                self.pending_background_origin = self.dialogue_renderer.background_origin(self.pending_background, engine)
                self.edge_layer = None              # it has the whole frame
                self.buttons = [(pygame.Rect(0, 0, *SIZE), ('continue',))]
                self.scroll = self.max_scroll = 0
                self._present()
                return
            except (ContentError, pygame.error, OSError, ValueError) as error:
                self.error = str(error)
                logging.error('Cutscene rendering stopped: %s', error)
        if (action and action.name in ('x360_slot', 'x360_leash', 'x360_puzzle', 'x360_diss', 'shs11_memory', 'shs11_reflex', 'brew_catch') and not ask and not closed
                and not self.error):
            try:
                engine = self.session.engine
                renderer = {'x360_leash': self.x360_leash_renderer, 'x360_puzzle': self.x360_puzzle_renderer,
                            'x360_slot': self.x360_slot_renderer, 'x360_diss': self.x360_diss_renderer, 'brew_catch': self.brew_catch_renderer,
                            'shs11_memory': self.shs11_renderer(action), 'shs11_reflex': self.shs11_renderer(action)}[action.name]
                if action.name in ('shs11_memory', 'shs11_reflex'):
                    self._warm_shs11_sounds(getattr(engine, action.name))
                renderer.draw(self.session)
                self.story_layer = renderer.canvas
                self.panel_alpha = renderer.alpha(getattr(engine, action.name))
                # The Word Grid skin draws the whole frame, its background too: nothing goes under it.
                self.pending_background = None if renderer is self.shs11_hd else self.dialogue_renderer.image(
                    action.details.get('background_id', engine.panel.background_id))     # (a grid names its own)
                if self.pending_background is not None:
                    self.pending_background_origin = self.dialogue_renderer.background_origin(self.pending_background, engine)
                self.edge_layer = self.dialogue_renderer.bottom_bar_layer('', self.dialogue_renderer.gear_pressed,
                                                                          getattr(renderer, 'edge_bar', 'bar') == 'bar')
                self.buttons = [(pygame.Rect(-round(self._edge_units * 1.5), 633, 150, 87), ('menu',))]
                self.scroll = self.max_scroll = 0
                self._present()
                return
            except (ContentError, pygame.error, OSError, ValueError) as error:
                self.error = str(error)
                logging.error('Minigame rendering stopped: %s', error)
        if closed and not self.error:
            # An answered menu, entry or picker under the closing blinds: the scene and the bottom bar alone.
            engine = self.session.engine
            self.pending_background = self.dialogue_renderer.image(engine.panel.background_id)
            self.pending_background_origin = self.dialogue_renderer.background_origin(self.pending_background, engine)
            self.edge_layer = self.dialogue_renderer.bottom_bar_layer('', False)
            self.buttons = []
            self._present()
            return
        if action and action.name == 'dialogue' and not self.error:
            try:
                self.dialogue_renderer.autoplay = self.autoplay
                self.dialogue_renderer.draw(None, self.session)
                self.story_layer = self.dialogue_renderer.wide
                if action.details.get('presentation_mode') == 4:
                    # A narrator's bubble is centred in a taller frame as the choice is (Session.narration_offset).
                    self.story_lift = self.session.narration_offset[1]
                self.edge_layer = self.dialogue_renderer.bottom_bar_layer(self.dialogue_renderer.footer_text,
                                                                          self.dialogue_renderer.gear_pressed)
                self.pending_background = self.dialogue_renderer.pending_background
                self.pending_background_origin = self.dialogue_renderer.pending_background_origin
                self.scroll = self.max_scroll = 0
                # The gear is flush with the frame's left edge, 48 canvas pixels (32 units) outside the UI column.
                self.buttons = [(pygame.Rect(-round(self._edge_units * 1.5), 633, 150, 87), ('menu',)),
                                (pygame.Rect(0, 0, *SIZE), ('continue',))]
                if pygame.time.get_ticks() < self.message_until:
                    self._text(self.message, 20, 701, 450, font=self.small, color=MUTED)
                self._present()
                return
            except (ContentError, pygame.error, OSError, ValueError) as error:
                self.error = str(error)
                logging.error('Dialogue rendering stopped: %s', error)
        if action and action.name in ('finished', 'episode_exit') and not self.error:
            # Live gameplay never actually renders this state (application.py's `render()` calls
            # `return_to_menu()` the moment `episode_ended` is set, instead of `Desktop.render()`), so the only
            # real caller is `snapshot()` building the end-of-episode card's sepia backdrop. That backdrop should
            # read as a frozen scene photo, the same as pausing mid-dialogue already does (a clean early return,
            # no bar drawn over it) -- not this class's own placeholder "Episode complete" bar, title strip and
            # Save/Load buttons below, which a real device never shows here and which this player only ever
            # draws today because 'finished'/'episode_exit' fall to the same catch-all as a genuine error or the
            # "not supported yet" screen, both of which do need that bar to stay usable.
            background_id = self.session.engine.panel.background_id
            if background_id < 0:
                background_id = self.last_background_id
            self.pending_background = self._image(background_id)
            self.pending_background_origin = None
            if self._frame_backdrop(getattr(self, 'bg_viewport', self.window.get_rect()).size) is not None:
                # shshd-runtime: a translated pack's strip stays where the episode showed it, over its frame
                # backdrop (owner: New Rules' end card keeps the frame under the sepia), not stretched over both.
                self.pending_background_origin = self.dialogue_renderer.background_origin(self.pending_background,
                                                                                          self.session.engine)
            # Settled, not mid-crossfade: this snapshot follows the last screen at once, so a picture of that screen's
            # own (New Rules' King of Diss ends on a download notice over a full-frame SHS lot) would otherwise still
            # cover the scene at full strength, the 0.25 s location change not yet begun.
            self.location_shown = self.location_changing = None
            self._present()
            return
        if action and action.name == 'presentation':
            background_id = details.get('asset_id', -1)
        else:
            # episode_exit (and 'finished') clear panel.background_id to -1 -- the episode is over, so the script
            # no longer has a "current scene" -- but the screen behind "Episode complete" (and, through it, the
            # end-of-episode card's sepia snapshot) should still freeze on the last real scene rather than show
            # nothing, the same as pausing mid-scene already does by reading a still-valid panel.background_id.
            background_id = self.session.engine.panel.background_id
            if background_id < 0:
                background_id = self.last_background_id
        background = self._image(background_id)
        self.pending_background = background
        self.pending_background_origin = None  # stretch to fill, not centered-crop
        bar = pygame.Surface((480, 38), pygame.SRCALPHA)
        bar.fill((15, 20, 33, 230))
        self.canvas.blit(bar, (0, 0))
        title = self.episode_title
        self.canvas.set_clip(pygame.Rect(12, 0, 456, 38))
        self._text(title, 14, 10, 900, font=self.small)
        self.canvas.set_clip(None)
        panel_top = 420 if action and action.name == 'dialogue' else 320
        if action and action.name in ('dialogue', 'choice') and not self.error:
            character = details.get('character_id', -1)
            expression = details.get('expression', self.session.engine.character_expressions.get(character, 0))
            self._portrait(character, expression, panel_top + 2)
        overlay = pygame.Surface((480, 720 - panel_top), pygame.SRCALPHA)
        overlay.fill((*PANEL, 245))
        self.canvas.blit(overlay, (0, panel_top))
        pygame.draw.line(self.canvas, ACCENT, (0, panel_top), (480, panel_top), 2)
        clip = pygame.Rect(0, panel_top + 2, 480, 638 - panel_top)
        self.canvas.set_clip(clip)
        y = panel_top + 18 - self.scroll
        if self.error:
            y = self._text('Playback paused', 24, y, 432, font=self.heading, color=ACCENT)
            y = self._text(self.error, 24, y + 16, 432)
        elif action is None:
            y = self._text('Loading…', 24, y, 432)
        elif action.name == 'presentation':
            y = self._text(details['title'], 24, y, 432, font=self.heading, color=ACCENT)
            y = self._text(details['subtitle'], 24, y + 18, 432)
        elif action.name == 'choice':
            y = self._text(details['title'], 24, y, 432, font=self.heading, color=ACCENT)
            y = self._text(details['text'], 24, y + 8, 432) + 14
            if self.session.remaining_ms is not None:
                y = self._text(f'{self.session.remaining_ms / 1000:.1f}s remaining', 24, y, 432,
                               font=self.small, color=MUTED) + 6
            for index, label in enumerate(details['options']):
                label = f'{index + 1}. {label}'
                height = max(48, len(self._lines(label, self.font, 404)) * (self.font.get_linesize() + 3) + 20)
                rect = pygame.Rect(24, y, 432, height)
                self._button(label, rect, ('choose', index), enabled=details['enabled'][index])
                y += height + 10
        elif action.name in ('finished', 'episode_exit'):
            y = self._text('Episode complete', 24, y, 432, font=self.heading, color=ACCENT)
        elif action.name == 'unhandled_yield':
            y = self._text('This part is not supported yet', 24, y, 432, font=self.heading, color=ACCENT)
            y = self._text('Your progress can be saved here. This episode needs an engine feature that is still being implemented.',
                           24, y + 18, 432)
            y = self._text(f'Scene {self.session.scene} · service {action.request.yield_id} · PC {action.request.pc}',
                           24, y + 16, 432, font=self.small, color=MUTED)
            if details.get('reason'):
                y = self._text(details['reason'], 24, y + 10, 432, font=self.small, color=MUTED)
        self.max_scroll = max(0, y + self.scroll - 630)
        self.scroll = min(self.scroll, self.max_scroll)
        self.canvas.set_clip(None)
        pygame.draw.rect(self.canvas, PANEL, (0, 640, 480, 80))
        if action and action.name in ('dialogue', 'presentation') and not self.error:
            self._button('Continue  ›', pygame.Rect(310, 650, 148, 44), ('continue',), small=True)
        self._button('Save', pygame.Rect(22, 650, 83, 44), ('save',), small=True)
        self._button('Load', pygame.Rect(115, 650, 83, 44), ('load',), small=True)
        message = (self.message if pygame.time.get_ticks() < self.message_until
                  else 'F5 save · F9 load · Esc menu · Tab panels')
        self._text(message, 22, 700, 450, font=self.small, color=MUTED)
        self._present()

    def _screen_token(self):
        details = self.session.pending.details if self.session.pending else {}
        game = self.session.engine.word_game
        grid = self.session.engine.word_grid
        football = self.session.engine.football
        dialogue = self.session.engine.dialogue_animation
        picker = self.session.engine.character_picker
        title = self.session.engine.title_screen
        return (id(self.session), self.session.scene, self.session.vm.steps_executed,
                details.get('page_start', 0), game.round if game else None,
                grid.round if grid else None, (football.round, football.phase) if football else None,
                (dialogue.finish_requested, dialogue.complete) if dialogue else None,
                tuple(picker.order) if picker else None,
                (title.reveal_width == 320, title.ready) if title else None,
                details.get('draft'), self.input_error, self.menu_open)

    def _football(self):
        """HD's football art when an HD app bundle is imported, else the Android renderer."""
        return self.football_hd if self.football_hd is not None and self.football_hd.available() else self.football_renderer

    def _picker(self):
        if self.picker_cod.available():
            return self.picker_cod
        return self.picker_hd if self.picker_hd.available() else self.picker_renderer

    def _word_grid(self):
        """HD's word game art when an HD app bundle is imported, else the Android renderer (with the keys' highlighted
        cell, grid_cursor)."""
        renderer = self.word_hd if self.word_hd is not None and self.word_hd.available() else self.grid_renderer
        if renderer is not None:
            renderer.cursor = self.grid_cursor
        return renderer

    _backdrop = (None, None)        # (window size, surface) of the last window backdrop

    def _canvas_empty(self):
        """Whether the canvas is still as render() cleared it. All zero bytes, so a compare: get_bounding_rect costs as
        much as the scale it would save."""
        buffer = self.canvas.get_buffer()
        if len(self._blank_canvas) != buffer.length:
            self._blank_canvas = bytes(buffer.length)
        return self._blank_canvas.startswith(buffer)

    def _window_backdrop(self, size):
        """While the "SHS HD Backdrop" switch is on, SHS HD's faded main-menu collage around the frame
        (hd_ui.window_backdrop), else None (the dark fill)."""
        key = size, self.hd_backdrop, self.ch_backdrop
        if self._backdrop[0] != key:
            surface = None
            try:
                if self.ch_backdrop and self.ch_switch():
                    from .desktop_cod_main import addon_backdrop
                    surface = addon_backdrop(self.session.resources.library, size)
                collage = self.backdrop_collage() if self.hd_backdrop and surface is None else None
                if collage is not None:
                    from .hd_ui import window_backdrop
                    surface = window_backdrop(collage, size)
            except (ContentError, pygame.error, OSError, ValueError, AttributeError):
                surface = None
            self._backdrop = (key, surface)
        return self._backdrop[1]

    _collage = ()                   # not looked up yet

    def backdrop_collage(self):
        """SHS HD's collage (resource 10): the HD bundle's for SHS, the SHS HD art source's for CoD; None without."""
        if self._collage == ():
            library = self.session.resources.library
            try:
                if getattr(library, 'game_id', None) == 'cod':
                    from .desktop_cod_main import hd_collage
                    self._collage = hd_collage(library)
                else:
                    self._collage = self.side_panels.collage()
            except (ContentError, pygame.error, OSError, ValueError, AttributeError, TypeError):
                self._collage = None
        return self._collage

    def backdrop_switch(self):
        """Whether the "SHS HD Backdrop" switch has a collage to show."""
        return self.backdrop_collage() is not None

    def hires_switch(self):
        """shshd-runtime: whether this episode has a second, hi-res portrait set to choose (the game profile's
        HIRES_SWITCH_PACKS: translated New Rules episodes), so the "Hi-Res Portraits" switch changes something."""
        return feature_pack(self.session.resources) in getattr(GAMES.get(game_id(self.session.resources)), 'HIRES_SWITCH_PACKS', ())

    def ms3_switch(self):
        """shshd-runtime: whether this episode has the April build's looks to choose (MS3_CHARACTER_ART: translated X360
        episodes), so the "MS3 Characters" switch changes something."""
        return feature_pack(self.session.resources) in getattr(GAMES.get(game_id(self.session.resources)), 'MS3_CHARACTER_ART', ())

    def java_look_switch(self):
        """shshd-runtime: whether this episode has the Java '08 demo's look to choose (JAVA_LOOK_ART: translated BREW
        episodes, with an addon that carries it), so the "Java '08 Look" switch changes something."""
        resources = self.session.resources
        if feature_pack(resources) not in getattr(GAMES.get(game_id(resources)), 'JAVA_LOOK_ART', ()):
            return False
        from .desktop_brew_catch import library_has_java_look
        return library_has_java_look(getattr(resources, 'library', None))

    def brew_08_switch(self):
        """shshd-runtime: whether this episode shows BREW's shared locations in '07's art (BREW_08_BACKGROUNDS), so the "'08
        Backgrounds" switch changes something."""
        return feature_pack(self.session.resources) in getattr(GAMES.get(game_id(self.session.resources)), 'BREW_08_BACKGROUNDS', ())

    def smartphone_switch(self):
        """shshd-runtime: whether this episode has the smartphone's music (SMARTPHONE_MUSIC_PACKS: translated SHS '11
        episodes), so the "Smartphone Music" switch changes something. It only picks what's heard: the engine and a save
        hold the same requests either way, so changing it needs nothing else."""
        resources = self.session.resources
        record = getattr(resources, 'record', None) or {}
        return record.get('pack_id') in getattr(GAMES.get(game_id(resources)), 'SMARTPHONE_MUSIC_PACKS', ())

    def word_grid_switch(self):
        """shshd-runtime: whether the "Use Word Grid Skin" switch is offered: Use Translated Mini-Games on, the games having
        been asked for by this episode (smartphone_switch's pack), and the HD bundle's word game art there."""
        return self.arena_minigames and self.shs11_hd is not None and self.shs11_hd.available()

    def ch_switch(self):
        """shshd-runtime: whether the library has the game's optional portrait addon (PORTRAIT_ADDON), so the CH
        switches change something."""
        library = getattr(self.session.resources, 'library', None)
        addon = getattr(GAMES.get(game_id(self.session.resources)), 'PORTRAIT_ADDON', None)
        return addon is not None and hasattr(library, 'addon') and library.addon(addon[0]) is not None

    def minigames_switch(self):
        """shshd-runtime: whether this episode has minigames the "Use Translated Mini-Games" switch changes (the game
        profile's TRANSLATED_MINIGAMES)."""
        resources = self.session.resources
        record = getattr(resources, 'record', None) or {}
        return has_translated_minigames(GAMES.get(game_id(resources)), record, getattr(resources, 'presentation', None))

    def set_hires_portraits(self, enabled):
        """shshd-runtime: the "Hi-Res Portraits" switch, from either Options page. The library reads the other set
        from the next portrait drawn (EpisodeResources._hires_portrait), and every cached portrait is dropped, so the
        story shows it at once: both sets fill the ring alike, so nothing else moves. Saves name the standard
        portraits, so a story always loads with the current set."""
        self.hires_portraits = enabled
        library = getattr(self.session.resources, 'library', None)
        if library is not None:
            library.hires_portraits = enabled
        self._drop_portraits()

    def set_ms3_characters(self, enabled):
        """shshd-runtime: the "MS3 Characters" switch, as set_hires_portraits: the next portrait drawn is the other set's,
        and a save names the standard portraits, so it needs nothing of its own."""
        self.ms3_characters = enabled
        library = getattr(self.session.resources, 'library', None)
        if library is not None:
            library.ms3_characters = enabled
        self._drop_portraits()

    def set_java_look(self, enabled):
        """shshd-runtime: the "Java '08 Look" switch: the library serves the Java copies of the BREW addon's pictures from the
        next one drawn (EpisodeResources._java_look), so every cached picture is dropped; the catch game picks its skin as it
        draws. Saves name the addon's own pictures, so they need nothing of their own."""
        self.java_look = enabled
        library = getattr(self.session.resources, 'library', None)
        if library is not None:
            library.java_look = enabled
        self._drop_portraits()
        self.dialogue_renderer.drop_translated_badges()
        self.brew_catch_renderer.drop_images()
        self._frame_backdrop_cache = (None, {})          # both box colours' backdrops, as scaled so far
        self.badge_hd._tab_cache = None                  # a time badge on screen, with its icon

    def set_brew_08_backgrounds(self, enabled):
        """shshd-runtime: the "'08 Backgrounds" switch: the library serves '08's shared locations from the next picture drawn
        (EpisodeResources._brew_08_background), so cached pictures are dropped. Saves name '07's, so they need nothing."""
        self.brew_08_backgrounds = enabled
        library = getattr(self.session.resources, 'library', None)
        if library is not None:
            library.brew_08_backgrounds = enabled
        self._drop_portraits()

    def set_ch_portraits(self, enabled):
        """shshd-runtime: the CH "HD Portraits in CoD" switch, as set_hires_portraits."""
        self.ch_portraits = enabled
        library = getattr(self.session.resources, 'library', None)
        if library is not None:
            library.ch_portraits = enabled
        self._drop_portraits()

    def _drop_portraits(self):
        self.images.clear()
        cached = [DialogueRenderer.portrait, DialogueRenderer.hd_portrait, DialogueRenderer.portrait_parts,
                  CharacterPickerRenderer.portrait, HdCharacterPickerRenderer.portrait]
        if HdWordRenderer is not None:
            cached.append(HdWordRenderer.portrait_image)
        for method in cached:
            method.cache_clear()

    def _present(self):
        engine = self.session.engine
        hd_badge = None
        if (engine.scene_badge or self.badge_hd.leaving()) and not self.error:
            try:
                if self.badge_hd.available():
                    hd_badge = self.badge_hd.draw(engine.scene_badge, engine.panel.theme)
                else:
                    self._draw_scene_badge(engine.scene_badge,
                                           previous_glyph=engine.text_history.initial('scene_badge'))
            except (ContentError, pygame.error, OSError, ValueError) as error:
                self.error = str(error)
                logging.error('Scene label rendering stopped: %s', error)
        # Confirmed against a real device: the corner alert doesn't fire
        # while the Faceplace panel itself is open -- the same content is
        # already visible there, so the redundant popup is suppressed.
        hd_alert = None
        if engine.faceplace_toast and not self.panels_open and not self.error:
            try:
                if self.faceplace_alert.available():
                    hd_alert = self.faceplace_alert.draw(engine, engine.faceplace_toast)
                else:
                    self._draw_faceplace_toast(engine.faceplace_toast)
            except (ContentError, pygame.error, OSError, ValueError) as error:
                self.error = str(error)
                logging.error('Faceplace alert rendering stopped: %s', error)
        hd_pause = self.menu_open and self.pause_hd.available() and not self.error
        if self.menu_open and not hd_pause:
            self._draw_menu()
        self._sync_audio()
        width, height = self.window.get_size()
        # HD's frame is 384x512 layout units (an iPad's 768x1024 points at half
        # size). The 320x480 UI column sits in it bottom-anchored and centered,
        # 32 units in from each side, with a 32-unit band of background above
        # it; the background fills the whole frame and the bottom bar and gear
        # run to its edges. Measured from HD photos: the UI is ~3.9 px per
        # unit at 1500x2000 (this build used to fit it to the window height at
        # 4.17), with the bar's 24-unit strip exactly 24 units tall.
        # General's Aspect Ratio (frame_shape.py) keeps the frame's width and makes it taller: the column stays at the
        # bottom, the extra height above it. A screen drawn as a whole 3:4 picture (a minigame, the arena) sits at the
        # bottom too (picture_frame), so its own bar and gear are where the story's are; a card over the scene (the
        # pause menu, a notice) is centred (card_frame); the Faceplace alert's strip keeps to the top (alert_frame).
        # At 3:4 all four are the frame.
        units = self.frame_units()
        self._frame_width, self._frame_tall = units
        edge = (units[0] - 320) / 2                 # the frame's margin each side of the column: 32 units, 0 from 9:16
        scale = min(width / units[0], height / units[1])
        frame = pygame.Rect(0, 0, max(1, round(units[0] * scale)), max(1, round(units[1] * scale)))
        frame.center = (width // 2, height // 2)
        # A whole 3:4 picture is as wide as the frame (narrower than HD's from 9:16, so a fifth smaller there).
        picture = pygame.Rect(0, 0, frame.width, max(1, round(units[0] * 4 / 3 * scale)))
        self._frames = (frame, picture.move(frame.x, frame.bottom - picture.height),
                        picture.move(frame.x, frame.centery - picture.height // 2), picture.move(frame.x, frame.y))
        target_size = (max(1, round(320 * scale)), max(1, round(480 * scale)))
        with frame_log.section('present'):
            # A screen with its own layer leaves the canvas empty: no pass, and nothing to blit.
            if self._canvas_empty():
                scaled = None
            elif self.canvas.get_size() == target_size:
                scaled = self.canvas
            else:
                scaled = pygame.transform.smoothscale(self.canvas, target_size)
        alpha, overlay = self.panel_alpha, self.panel_overlay
        self.panel_alpha = self.panel_overlay = None
        if scaled is not None and alpha is not None and alpha < 1:
            scaled = faded(scaled, round(255 * alpha))
        # The column also sits 5.5 units above the frame's bottom edge (box
        # top and bottom lines both measured 21.5 px lower than HD's at
        # 3.9 px per unit; the right border matched to a pixel).
        self.viewport = pygame.Rect(frame.x + round(edge * scale),
                                    frame.bottom - target_size[1] - round(UI_BOTTOM_INSET * scale), *target_size)
        self.bg_viewport = frame
        bg_size = frame.size
        with frame_log.section('backdrop'):
            backdrop = self._window_backdrop(self.window.get_size())
            # Only around the frame: the background layer starts by filling the frame itself.
            for area in window_margins((width, height), frame):
                if backdrop is not None:
                    self.window.blit(backdrop, area, area)
                else:
                    self.window.fill((8, 12, 20), area)
            self._draw_background_layer(bg_size, self.bg_viewport, self._frame_covered(alpha))
        under = getattr(self, 'under_layer', None)
        if under is not None:
            # A screen under the choice that covers the whole frame (New Rules' arena under its menu).
            self.window.blit(pygame.transform.smoothscale(under, self.picture_frame.size), self.picture_frame)
            self._draw_picture_band(backdrop, height)
        ui_layers = []
        if self.story_layer is not None:
            # Drawn at HD density and resampled once, straight to the window.
            layer = self.story_layer
            if self.story_centred:
                # A picture as wide as the frame and no taller (a storyboard: desktop_cutscene), centred; past the shape
                # its spec serves the backdrop shows above and below it.
                tall = round(frame.width * layer.get_height() / layer.get_width())
                area = frame if abs(tall - frame.height) <= 1 else pygame.Rect(
                    frame.x, frame.centery - tall // 2, frame.width, tall)
                self._draw_bands(area, backdrop)
            elif self.story_fills_frame:
                # A card drawn over the whole frame in its own shape (desktop_title: HD's 768 x 1024 at 3:4).
                area = frame
            elif layer.get_width() * FRAME_UNITS[1] == layer.get_height() * FRAME_UNITS[0] and self.story_over_scene:
                # HD's frame drawn over the scene (the look picker): at the story's scale with the column, its bottom
                # the frame's, cut by a narrower frame's sides; the scene shows above it.
                margin = round(32 * scale)
                tall = round(FRAME_UNITS[1] * scale)
                area = pygame.Rect(self.viewport.x - margin, frame.bottom - tall, self.viewport.width + 2 * margin, tall)
            elif layer.get_width() * FRAME_UNITS[1] == layer.get_height() * FRAME_UNITS[0]:
                # The whole 384x512-unit frame (HD's football): 3:4, at the bottom of a taller frame.
                area = self.picture_frame
                self._draw_picture_band(backdrop, height)
            elif frame_wide(layer.get_size()):
                # A frame-wide layer (its column plus HD's 32-unit side margins), cut by a narrower frame's edges.
                margin = round(32 * scale)
                area = pygame.Rect(self.viewport.x - margin, self.viewport.y, self.viewport.width + 2 * margin,
                                   self.viewport.height)
            else:
                area = self.viewport
            if self.story_lift:
                area = area.move(0, -round(self.story_lift * scale))
            with frame_log.section('present'):
                # Already the area's size when the window is drawn at the story's own density (Android): no pass.
                layer = layer if layer.get_size() == area.size else pygame.transform.smoothscale(layer, area.size)
            if alpha is not None and alpha < 1:
                layer = faded(layer, round(255 * alpha))
            clip = self.window.get_clip()
            self.window.set_clip(frame.clip(clip))
            self.window.blit(layer, area)
            self.window.set_clip(clip)
            ui_layers.append((layer, area))
        if self.edge_layer is not None and not self.capture:
            # HD's bottom bar and gear run to the edges of its frame.
            edge_height = round(self.viewport.height * 72 / 480)
            edge_size = (self.bg_viewport.width, edge_height)
            # The layer is the same surface until the bar changes (bottom_bar_layer's cache).
            if self._edge_scaled[:2] != (self.edge_layer, edge_size):
                self._edge_scaled = (self.edge_layer, edge_size, pygame.transform.smoothscale(self.edge_layer, edge_size))
            self.window.blit(self._edge_scaled[2], (self.bg_viewport.x, self.bg_viewport.bottom - edge_height))
        if scaled is not None:
            self.window.blit(scaled, self.viewport)
            ui_layers.append((scaled, self.viewport))
        if overlay is not None:
            self.window.blit(pygame.transform.smoothscale(overlay, target_size),
                             self.viewport.move(0, -round(self.story_lift * scale)))
        self._panel_handover(ui_layers)
        hd_frame = (self.__dict__.get('_frame_width', FRAME_UNITS[0]), self._frame_tall) == FRAME_UNITS
        if hd_alert is not None:
            # HD's alert is a strip of the frame, cut by the frame's own edge: in another shape, at the story's scale,
            # against the frame's right edge and top as on HD's.
            if hd_frame:
                self.window.blit(pygame.transform.smoothscale(hd_alert, self.alert_frame.size), self.alert_frame)
            else:
                # HD's card is small on a phone: enlarged towards ALERT_ZOOM as the frame narrows to the column's
                # width (owner, 2026-11-11), about its top-right corner.
                narrow = (FRAME_UNITS[0] - self.__dict__.get('_frame_width', FRAME_UNITS[0])) / (FRAME_UNITS[0] - 320)
                zoom = 1 + (self.ALERT_ZOOM - 1) * max(0., min(1., narrow))
                width = round(FRAME_UNITS[0] * scale * zoom)
                self._blit_part(hd_alert, pygame.Rect(frame.right - width, frame.y, width,
                                                      round(FRAME_UNITS[1] * scale * zoom)), frame)
        if hd_badge is not None:
            # The scene label's tab at HD's (15, 50) units: in another shape, at the story's scale, as far from the
            # frame's left edge, and centred in a taller frame as the narration it sits over is.
            if hd_frame:
                self.window.blit(pygame.transform.smoothscale(hd_badge, self.picture_frame.size), self.picture_frame)
            else:
                lift = round((self._frame_tall - FRAME_UNITS[1]) / 2 * scale)
                self._blit_part(hd_badge, pygame.Rect(frame.x, frame.y + lift, round(FRAME_UNITS[0] * scale),
                                                      round(FRAME_UNITS[1] * scale)), frame)
        if hd_pause:
            self._draw_hd_pause(frame)
        if self.notice_stack is not None and self.notice_stack.stack:
            self._draw_notice(frame, dim=not hd_pause)
        elif not hd_pause:
            self._tinted = None             # the next pause menu or notice tints the scene as it is then
        # Real device confirmed: panels occupy the window space *beside*
        # the game view -- not overlaid on top of it -- and render at real
        # window resolution instead of being funneled through self.canvas's
        # fixed budget (see desktop_panels.py's module docstring).
        #
        # Real device correction: these margins used to start at
        # self.viewport's own edge, but the background layer above is
        # deliberately drawn *wider* than that (bg_viewport, showing more
        # of HD's true 3:4 background beyond the narrower Android-authored
        # UI canvas) -- so a panel starting at self.viewport's edge covered
        # the outermost strip of that wider background instead of sitting
        # fully beside it. Margins now start at bg_viewport's own edge.
        zoom_mode = self._tree_zoom_mode()
        if zoom_mode is None:
            self.tree_zoom.close(instantly=True)
            self.tree_zoom.tab = self.tree_zoom.portrait_tab = None
        if zoom_mode is not None and self.tree_zoom.showing:
            try:
                with frame_log.section('panels'):
                    self._draw_tree_zoom(zoom_mode, width, height)
            except (ContentError, pygame.error, OSError, ValueError) as error:
                self.error = str(error)
                logging.error('Tree zoom rendering stopped: %s', error)
        elif (self.panels_open or self.panels_progress > 0) and not self.error:
            left_margin = pygame.Rect(0, 0, self.bg_viewport.x, height)
            right_margin = pygame.Rect(self.bg_viewport.right, 0, width - self.bg_viewport.right, height)
            try:
                with frame_log.section('panels'):
                    if self.side_panels.available():
                        self.side_panels.warp_locked = not self.warp_unlocked
                        self.side_panels.draw(self.window, self.session, self.panels_progress, left_margin, right_margin)
                    else:
                        self.dtview_renderer.draw(self.window, self.session, self.panels_progress, left_margin)
                        self.faceplace_panel_renderer.draw(self.window, self.session, self.panels_progress,
                                                           right_margin)
            except (ContentError, pygame.error, OSError, ValueError) as error:
                self.error = str(error)
                logging.error('DTView/Faceplace panel rendering stopped: %s', error)
        if zoom_mode is not None and not self.capture:
            self.tree_zoom.draw_tab(self.window, self.tree_zoom.tab_rect(zoom_mode, self.bg_viewport))
            if zoom_mode == 'portrait':
                self.tree_zoom.draw_portrait_tab(self.window, self.tree_zoom.portrait_tab_rect(self.bg_viewport))
            else:
                self.tree_zoom.portrait_tab = None      # `SHSPZButton` is off the screen in landscape
        self._draw_arena_handover()
        self._draw_loading_handover()
        self._draw_transition()
        if self.fade:
            self._draw_fade()
        if not self.capture:
            with frame_log.section('flip'):
                pygame.display.flip()

    @property
    def tree_zoom(self):
        """HD's tree zoom tab and portrait zoom button (desktop_tree_zoom.py; exploration), made when first used."""
        zoom = self.__dict__.get('_tree_zoom')
        if zoom is None:
            zoom = self.__dict__['_tree_zoom'] = desktop_tree_zoom.TreeZoom()
        return zoom

    def _tree_zoom_mode(self):
        """Where HD's tree zoom tab is (desktop_tree_zoom.py): 'landscape' beside the open side panels, 'portrait' in
        an upright window without them, or None (switched off, no tree in this episode, the panels moving, an error)."""
        if not desktop_tree_zoom.ENABLED or self.error or not hasattr(self, 'bg_viewport'):
            return None
        if not self.session.engine.dt_view.enabled or not self.side_panels.available():
            return None                 # `setEnable:` follows the tree panels' own switch for the episode
        if self.panels_open and self.panels_progress >= 1:
            return 'landscape'
        if not self.panels_open and self.panels_progress <= 0:
            return desktop_tree_zoom.TreeZoom.mode(self.window.get_size(), False)
        return None

    def _draw_tree_zoom(self, mode, width, height):
        """The screen while the tree zoom is in or moving (desktop_tree_zoom.py has HD's numbers): the game drawn so
        far moves off as one, and the panels are drawn where the zoom has them now."""
        from .desktop_side_panels import PANEL
        zoom, panels = self.tree_zoom, self.side_panels
        a = zoom.amount
        s, left, top = zoom.screen(mode, self.bg_viewport)
        panels.warp_locked = not self.warp_unlocked
        game = self.window.copy()
        self.window.fill((0, 0, 0))
        if mode == 'landscape':
            self.window.blit(game, (round(desktop_tree_zoom.GAME_SHIFT * s * a), 0))
            wall = pygame.Rect(self.bg_viewport.right + round(desktop_tree_zoom.LANDSCAPE_WALL_SHIFT * s * a), 0,
                               width - self.bg_viewport.right, height)
            panels.draw_wall(self.window, self.session, 1.0, wall)
            column = round(PANEL[0] * height / PANEL[1])
            start, end = self.bg_viewport.x - column, (width - column) // 2
            panels.draw_tree(self.window, self.session, 1.0,
                             pygame.Rect(round(start + (end - start) * a), 0, column, height))
            return
        shut, zoomed = desktop_tree_zoom.PORTRAIT_TREE_Y
        w, h = desktop_tree_zoom.PORTRAIT_TREE
        middle = shut + (zoomed - shut) * a
        panels.tree_shape = desktop_tree_zoom.PORTRAIT_TREE
        try:
            panels.draw_tree(self.window, self.session, 1.0, pygame.Rect(
                round(left), round(top + (middle - h / 2) * s), round(w * s), round(h * s)))
        finally:
            panels.tree_shape = PANEL
        # `SHSEngine::onStart` adds the wall after the tree, so where they overlap the wall is on top. The game comes
        # last: it is brought to the front (`bringSubviewToFront:`).
        x, y, w, h = desktop_tree_zoom.PORTRAIT_WALL
        panels.draw_wall(self.window, self.session, 1.0,
                         pygame.Rect(round(left + x * s), round(top + y * s), round(w * s), round(h * s)))
        frame = self.bg_viewport
        rect = zoom.game_rect(frame)
        if rect.size == frame.size:
            self.window.blit(game, (rect.x - frame.x, rect.y - frame.y))
        else:
            source = frame.clip(game.get_rect())
            self.window.blit(pygame.transform.smoothscale(game.subsurface(source), rect.size), rect.topleft)

    def _tree_zoom_toggled(self):
        """`toggleDTZ`: zooming in during the story pauses it (`invokePauseMenu`, with its sound 8011); either way
        8017 plays. The pause menu is on the game, off the screen until the tree is put back."""
        if self.tree_zoom.zoomed:
            self.tree_drag = self.wall_drag = None
            self.tree_fling.stop()
            if not self.menu_open and self.session.pending is not None:
                self.open_pause()
        if hasattr(GAMES[game_id(self.session.resources)], 'TREE_ZOOM_SOUND'):
            self._ui_sound('TREE_ZOOM_SOUND')

    def _tree_zoom_pointer(self, event):
        """Input while the tree zoom tab is there: the tab toggles the zoom; zoomed, the tree (and the wall beside it in
        portrait) take the pointer and the game, off the screen, takes none. True when the event is used up."""
        result = self.tree_zoom.pointer(event, down=pygame.MOUSEBUTTONDOWN, up=pygame.MOUSEBUTTONUP)
        if result == 'toggled':
            self._tree_zoom_toggled()
        # `togglePZ` has no sound and no pause: the story carries on in the smaller game.
        result = result or self.tree_zoom.portrait_pointer(event, down=pygame.MOUSEBUTTONDOWN, up=pygame.MOUSEBUTTONUP)
        if result:
            return True
        if not self.tree_zoom.showing:
            return False
        if not self.tree_zoom.tree_showing:
            return self._portrait_zoom_pointer(event)
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.tree_zoom.toggle()
            self._tree_zoom_toggled()
            return True
        pointer = event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION, pygame.MOUSEWHEEL)
        if not pointer or not self.tree_zoom.settled:
            return pointer
        return self._zoomed_panels_pointer(event)

    def _zoomed_panels_pointer(self, event):
        """A pointer event on the panels a zoom has uncovered. In portrait the wall lies over the tree's right end, so
        it comes first there. Always used up."""
        position = pygame.mouse.get_pos() if event.type == pygame.MOUSEWHEEL else event.pos
        wall = self.side_panels.wall_rect
        if not self.tree_drag and wall is not None and wall.collidepoint(position):
            self._wall_pointer(event)
            return True
        if self._tree_pointer(event) or self._wall_pointer(event):
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._tree_click(event.pos)
        return True

    def _portrait_zoom_pointer(self, event):
        """Input with only the portrait zoom in: what the shrunken game covers is the game's (False, and
        _portrait_game_event moves it), what it uncovers is the tree's and the wall's. A press stays with whichever got
        it. True when the event is used up."""
        zoom = self.tree_zoom
        pointer = event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION, pygame.MOUSEWHEEL)
        if not pointer:
            return False
        if zoom.game_down:
            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                zoom.game_down = False
            return False
        if not zoom.settled:
            return True
        position = pygame.mouse.get_pos() if event.type == pygame.MOUSEWHEEL else event.pos
        if not (self.tree_drag or self.wall_drag) and zoom.game_rect(self.bg_viewport).collidepoint(position):
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                zoom.game_down = True
            return False
        return self._zoomed_panels_pointer(event)

    def _portrait_game_event(self, event):
        """A pointer event the shrunken game takes, at the same place on the game at full size."""
        zoom = self.tree_zoom
        if zoom.portrait_t <= 0 or not hasattr(event, 'pos'):
            return event
        return pygame.event.Event(event.type, {**event.dict, 'pos': zoom.to_game(self.bg_viewport, event.pos)})

    def _frame_covered(self, alpha):
        """Whether this frame's story layer hides all of the frame (the arena's): nothing under it needs drawing. Not with
        any alpha channel, which a `convert()`ed canvas has on a Mac and can hold at 0 (graphics.opaque)."""
        layer = self.story_layer
        return (layer is not None and self.pending_background is None and (alpha is None or alpha >= 1)
                and not layer.get_masks()[3]
                and layer.get_width() * FRAME_UNITS[1] == layer.get_height() * FRAME_UNITS[0])

    _background_cover = None        # what `_blit_art` last covered the whole frame with, opaquely
    _edge_units = 32                # the frame's margin each side of the column (_sync_story_scale)

    def _draw_background_layer(self, target_size, viewport, covered=False):
        """Composited directly at window resolution, under the UI canvas.

        self.canvas is left transparent where a background belongs (see
        render()) specifically so this can source from the background's own
        real pixel density in one resampling step, instead of that density
        being capped by self.canvas's fixed 480x720 size first and then
        resampled a second time to fit the window. A background asset wider
        than the 480px Android reference (HD content; confirmed exactly 2x
        in the one real case measured) is real extra detail, not something
        to discard before it reaches the screen.

        target_size/viewport cover a wider 3:4 area than the UI canvas's own
        2:3 footprint (see DEFAULT_WINDOW_SIZE): HD's real game view is a
        fixed 768x1024 regardless of orientation (confirmed from
        SHSViewController::setupLocalInterfaceOrientation:, see
        legacy/findings.md), so showing more background around the edges of
        the unchanged, Android-authored UI chrome is closer to HD's own
        proportions without needing HD's still-undeciphered chrome layout.
        """
        # The game view is black under its background: a scene with none (the Spirit Week and Series Finale intros
        # open before any is set, issue #8) or one still fading in shows black, not the window's backdrop.
        background = self.pending_background
        placement = None if background is None else self._background_placement(background, target_size)
        change = self._location_change(background, placement)
        # What is under an opaque picture that filled the frame last frame and does again needn't be drawn.
        hidden = (change is None and self.pending_background_alpha >= 255 and placement is not None
                  and self._background_cover == (id(background), tuple(placement), tuple(viewport)))
        if not covered and not hidden:
            self.window.fill((0, 0, 0), viewport)
            # shshd-runtime: a translated episode may carry its own picture for that (profile TRANSLATED_FRAME_BACKDROP).
            if placement is not None and background.get_width() >= 2 * background.get_height():
                # A location strip: where it is in the frame, as frame units from the top (the backdrop's bars hug it).
                unit = target_size[1] / self.__dict__.get('_frame_tall', FRAME_UNITS[1])
                self._strip_units = (placement[1] / unit, (placement[1] + placement[3]) / unit)
            frame_backdrop = self._frame_backdrop(viewport.size)
            if frame_backdrop is not None:
                self.window.blit(frame_backdrop, viewport)
        self._background_cover = None
        if placement is not None:
            if change is not None and change['from'] is not None:
                placement = tuple(a + (b - a) * change['p'] for a, b in zip(change['from'], placement))
            self._blit_art(background, placement, target_size, viewport, self.pending_background_alpha)
        if change is not None and change['old'] is not None and change['p'] < 1:
            # The outgoing picture, in the same (animated) layer, fading out over the incoming one.
            alpha = (self.pending_background_alpha if placement is not None else 255) * (1 - change['p'])
            self._blit_art(change['old'], placement or change['from'], target_size, viewport, alpha, cache=False)

    def _frame_backdrop(self, size):
        """The playing episode's picture for the whole frame, scaled to `size`, or None for black: the resource its
        pack names in the game profile's TRANSLATED_FRAME_BACKDROP (New Rules' UI backdrop for its translations,
        whose 3:1 location strips leave bands above and below), when the episode carries it. A pack may have another for
        the speaker's box colour (TRANSLATED_THEME_BACKDROP: BREW's panel is pink behind a pink box)."""
        resources = self.session.resources
        record = getattr(resources, 'record', None) or {}
        game = GAMES.get(self.session.engine.game_key)
        asset_id = pack_setting(resources, 'TRANSLATED_FRAME_BACKDROP')
        exists = getattr(resources, 'exists', None)
        if asset_id is None or exists is None or not exists(asset_id):
            return None
        engine = self.session.engine
        theme = engine.panel.theme
        picker, pending = engine.character_picker, self.session.pending
        if picker is not None and pending is not None and pending.name == 'character_picker' and picker.characters:
            # On a portrait picker it follows the highlighted portrait: a boy's blue, a girl's pink (owner, 2026-11-07).
            theme = engine.numbers.get(engine.number_key(picker.characters[picker.selected], 651), 0)
        elif pending is not None and pending.name == 'choice':
            # On a choice it follows the choice's own box (desktop_choice: its character's theme), not the last line's
            # speaker: the player's choices are blue after a girl's pink line (owner, 2026-11-09).
            theme = engine.numbers.get(engine.number_key((pending.details or {}).get('character_id', -1), 651), 0)
        themed = (pack_setting(resources, 'TRANSLATED_THEME_BACKDROP', {}) or {}).get(theme)
        if themed is not None and exists(themed):
            asset_id = themed
        tall = self.__dict__.get('_frame_tall', FRAME_UNITS[1])
        strip = (None if (self.__dict__.get('_frame_width', FRAME_UNITS[0]), tall) == FRAME_UNITS
                 else self._backdrop_strip(tall))
        key = (id(resources), size, getattr(getattr(resources, 'library', None), 'java_look', False),
               strip and tuple(round(v, 1) for part in strip for v in part))
        if self._frame_backdrop_cache[0] != key:
            self._frame_backdrop_cache = (key, {})      # (the surfaces of this episode at this size: one per colour)
        surfaces = self._frame_backdrop_cache[1]
        if asset_id not in surfaces:
            image = self._image(asset_id)
            if image is None:
                surfaces[asset_id] = None
            elif strip is None:
                surfaces[asset_id] = pygame.transform.smoothscale(image, size)      # the 3:4 frame, as always
            else:
                # Taller (General's Aspect Ratio): lengthened so its bars stay round the strip (backdrop_fit.py).
                k = image.get_width() / FRAME_UNITS[0]                          # source pixels per frame unit
                (top, bottom), (new_top, new_bottom) = strip
                long = backdrop_fit.lengthen(image.convert_alpha(), (top * k, bottom * k), (new_top * k, new_bottom * k),
                                             round(tall * k))
                # A frame narrower than HD's (from 9:16) shows the middle of it, cut at the sides as the strip is.
                wide = self.__dict__.get('_frame_width', FRAME_UNITS[0])
                cut = round((FRAME_UNITS[0] - wide) / 2 * k)
                if cut > 0:
                    long = long.subsurface((cut, 0, long.get_width() - 2 * cut, long.get_height()))
                surfaces[asset_id] = pygame.transform.smoothscale(long, size)
        return surfaces[asset_id]

    # Where a location strip sits in the 3:4 frame, in frame units from its top (DialogueRenderer.background_origin's
    # y 180 less HD_BG_SHIFT's 20.5, 32 in, half the strip's 160 units either side): the backdrops' bars hug it.
    STRIP_AT_3_4 = (111.5, 271.5)

    def _backdrop_strip(self, tall):
        """The strip's rows in frame units, ((top, bottom) in the 3:4 frame, (top, bottom) in this one): where this
        frame's strip was drawn (`_strip_units`), else where `_shaped_placement` puts one (above the column, risen by
        STRIP_RISE of the added height)."""
        lift = tall - 480 - 32 - (tall - FRAME_UNITS[1]) * self.STRIP_RISE      # below HD's place
        now = self.__dict__.get('_strip_units') or (self.STRIP_AT_3_4[0] + lift, self.STRIP_AT_3_4[1] + lift)
        return self.STRIP_AT_3_4, now

    # `GameModel::setLocationImageID` changes the location layer's contents and bounds with Core Animation's implicit
    # actions on, so a new scene picture crossfades in (0.25 s); `SHSUIChapterScreen::animate` turns the actions off
    # around its own picture (`[CATransaction begin]`, `setValue:forKey:`, `commit`), and its `internalTransitionOff`
    # puts the layer's scale and position back implicitly, so the card's picture glides into the scene's framing as
    # the next picture fades in (CoD 1.4.7 000408f0, SHS HD 0004b37c). Duration: Core Animation's default 0.25 s
    # (`animateLocationLayer` returns 0.25 too); the curve is measured, not in the binaries: lighttouch recordings of
    # Cause of Death fit the default ease best (findings, 2026-10-23).
    LOCATION_CHANGE_MS = 250

    def _location_change(self, background, placement):
        """The location layer's implicit animation this frame: None, or {'p': eased progress, 'old': the outgoing
        picture or None, 'from': the outgoing placement to glide from, or None}."""
        action = self.session.pending
        card = action is not None and action.name == 'presentation'
        previous, now = self.location_shown, pygame.time.get_ticks()
        self.location_shown = (background, placement, card) if background is not None else previous
        animated = self.dialogue_renderer.has_hd_bundle() or self.dialogue_renderer.game_id() == 'cod'
        if (background is None and previous is not None and previous[0] is not None and animated
                and action is not None and action.name == 'message_panel'):
            # CoD's message panel stands on black: the owner's recording (60 fps) shows the scene picture fading out
            # in about 0.2 s as the panel appears, read here as the same implicit animation clearing the layer.
            # Whether a picture after the panel fades back in is unrecorded; it cuts in.
            self.location_changing = dict(since=now, old=previous[0], start=previous[1])
            self.location_shown = None
            return self._location_progress(now)
        if background is None or previous is None or not animated or card:
            if card:
                self.location_changing = None        # the card sets its picture with the actions off
            return self._location_progress(now)
        old, old_placement, old_card = previous
        if old_card or old is not background:
            self.location_changing = dict(since=now, old=None if old is background else old,
                                          start=old_placement if old_card else None)
        return self._location_progress(now)

    # CoD's message panel replaces a dialogue panel at once, while the dialogue's name, text, portrait and button fade
    # out over it (owner's recording, 60 fps: the panel's body is opaque in the first changed frame; the old lines
    # are gone within about 0.2 s). Timed like the location layer's fade. Unmodelled: the panel's title fading in.
    HANDOVER_MS = LOCATION_CHANGE_MS

    def _panel_handover(self, layers):
        """Remember a dialogue frame's UI layers; over CoD's message panel that follows one, draw them fading out."""
        action, now = self.session.pending, pygame.time.get_ticks()
        name = action.name if action is not None else None
        if name == 'dialogue':
            self.ui_layers, self.ui_handover = (action, layers), None
            return
        previous, self.ui_layers = self.ui_layers, None
        if (name == 'message_panel' and previous is not None and previous[0] is not action
                and self.dialogue_renderer.game_id() == 'cod'):
            self.ui_handover = dict(since=now, action=action, layers=previous[1])
        handover = self.ui_handover
        if handover is None or handover['action'] is not action:
            self.ui_handover = None
            return
        t = (now - handover['since']) / self.HANDOVER_MS
        if t >= 1:
            self.ui_handover = None
            return
        alpha = round(255 * (1 - default_ease(max(0., t))))
        for layer, area in handover['layers']:
            self.window.blit(faded(layer, alpha), area)

    def _location_progress(self, now):
        change = self.location_changing
        if change is None:
            return None
        t = (now - change['since']) / self.LOCATION_CHANGE_MS
        if t >= 1:
            self.location_changing = None
            return None
        return dict(p=default_ease(max(0., t)), old=change['old'], **{'from': change['start']})

    def _background_placement(self, background, target_size):
        """Where the whole picture lies, (x, y, width, height) in target pixels from the frame's top-left: the
        location layer's bounds as scaled and positioned on screen."""
        bw, bh = background.get_size()
        tw, th = target_size
        # General's Aspect Ratio (frame_shape.py): the frame is `wide` x `tall` units, HD's 384 x 512 at 3:4.
        wide = self.__dict__.get('_frame_width', FRAME_UNITS[0])
        tall = self.__dict__.get('_frame_tall', FRAME_UNITS[1])
        if (wide, tall) != FRAME_UNITS and self.pending_background_origin is not None:
            return self._shaped_placement(background, target_size, wide, tall)
        if self.pending_background_origin is None:
            if (wide, tall) == FRAME_UNITS:
                return (0., 0., float(tw), float(th))
            # Stretched to the 3:4 frame as before; another shape takes the picture scaled evenly until it covers,
            # centred (a 2:3 picture shows whole at 2:3).
            k = max(tw / bw, th / bh)
            return ((tw - bw * k) / 2, (th - bh * k) / 2, bw * k, bh * k)
        if self.pending_background_origin == 'cover':
            # Cause of Death's chapter card: its iPhone screen shows the whole picture fitted to the 320x480 column;
            # here it is scaled evenly until it covers the 3:4 frame, centred where the column's centre is (owner:
            # no dead space, as SHS fills the frame -- without the stretch SHS HD's own card applies).
            centre = 26.5 + 240                                  # the column's centre, frame units from the top
            k = min(bw / 384, bh / (2 * centre), bh / (2 * (512 - centre)))   # art pixels per frame unit
            crop = pygame.Rect(round(bw / 2 - 192 * k), round(bh / 2 - centre * k), round(384 * k), round(512 * k))
            sx, sy = tw / crop.width, th / crop.height
            return (-crop.x * sx, -crop.y * sy, bw * sx, bh * sy)
        else:
            cx, cy = self.pending_background_origin
            # In HD's frame the art sits 48 units further right and 20.5
            # higher than its Android focal point implies: feature-matched
            # against two HD photos of the same hall (the portrait one and the
            # landscape IMG_0069 both gave dx=-188, dy=80 px at 1500x2000,
            # i.e. this build's image lay that far left and down). Measured
            # for the dialogue scene; assumed constant for other screens.
            bg_scale = bw / 480
            # Cause of Death draws its scenes the way SHS draws its SD backgrounds in the HD frame (owner's choice,
            # 2026-10-14): the 480x720 art panned with the speaker so the frame is always covered. Its own iPhone
            # screen shows the art 1 px per point from the plain focal point (IMG_0483), which leaves the 3:4
            # frame's margins past the art's edge.
            if self._location_pans(cy):
                # HD pans the location layer by speaker (location_pan.py): its center is `x` points from
                # the frame's left edge, i.e. x / 2 - 32 in this crop's UI units. The pan takes the art's width in
                # HD points: 960 for a 480-pixel picture as for its 960-pixel HD twin.
                x = self.location_pan.x(self.session.engine.panel.location_align, bw / bg_scale * 2,
                                        pygame.time.get_ticks())
                cx = x / 2 - 32
            else:
                cx += HD_BG_SHIFT[0]
            cy += HD_BG_SHIFT[1]
            # Frame coordinates (see _present): the frame's top-left is UI
            # (-32, -32) as far as this crop is concerned -- the 5.5-unit inset
            # of the UI column was measured against the same photos after the
            # background, so it moves the column, not the background. The image
            # is drawn 1 px per unit (HD: 2) centered on (cx, cy) in that
            # space, so crop exactly the frame's window out of it.
            window = pygame.Rect(round(bw / 2 + (-32 - cx) * bg_scale), round(bh / 2 + (-32 - cy) * bg_scale),
                                 round(384 * bg_scale), round(512 * bg_scale))
            sx, sy = tw / window.width, th / window.height
            return (-window.x * sx, -window.y * sy, bw * sx, bh * sy)

    def _location_pans(self, cy):
        """Whether the location layer pans by speaker (location_pan.py): a dialogue scene's picture (focal y 180)
        with HD's art, and every Cause of Death scene."""
        return cy == 180 and (self.dialogue_renderer.has_hd_bundle() or self.dialogue_renderer.game_id() == 'cod')

    # How far a strip (New Rules, BREW) rises in a frame taller than HD's: by this share of the added height (the
    # owner's pick B, 2026-11-11).
    STRIP_RISE = .5
    # How much larger the Faceplace alert is drawn in a frame the column's width (a phone) than at HD's scale.
    ALERT_ZOOM = 1.5

    def _shaped_placement(self, background, target_size, wide, tall):
        """`_background_placement` in a frame of another shape than HD's 3:4 (General's Aspect Ratio), `wide` x `tall`
        units with the column at its bottom, centred: (x, y, width, height) in target pixels.

        A location picture (480 units wide, 720 tall: one that covers HD's frame) is shown
        - at 2:3 (384 wide) whole: scaled to the frame, nothing panned (owner, 2026-11-11);
        - from 9:16 (the column's 320 wide) as SD SHS and Cause of Death show it on an iPhone's screen, one art unit a
          unit about SD's own focal point, panned by speaker as HD pans; past its height (Fit Screen past 9:20)
          enlarged to the frame's height;
        - in between, at a scale between the two;
        always covering the frame, sliding down or across rather than leave an edge. HD's focal shift (HD_BG_SHIFT,
        measured in its frame) fades out towards SD's layout. A strip (New Rules, BREW) keeps its size and rises with
        the frame (STRIP_RISE); its frame backdrop shows round it (_frame_backdrop). Cause of Death's chapter card
        (`cover`) covers the frame about the column's centre."""
        bw, bh = background.get_size()
        tw, th = target_size
        unit_x, unit_y = tw / wide, th / tall              # target pixels per frame unit
        if self.pending_background_origin == 'cover':
            centre = tall - FRAME_UNITS[1] + 26.5 + 240     # the column's centre, as far from the bottom as in HD's
            k = max(wide / bw, centre * 2 / bh, (tall - centre) * 2 / bh)      # frame units per art pixel
            return ((wide - bw * k) / 2 * unit_x, (centre - bh * k / 2) * unit_y, bw * k * unit_x, bh * k * unit_y)
        cx, cy = self.pending_background_origin
        bg_scale = bw / 480                                 # art pixels per art unit (the picture is 480 units wide)
        high = bh / bg_scale
        side = (wide - 320) / 2                             # the frame's margin each side of the column
        top = tall - 480                                    # the column's top as the background counts it (HD: 32)
        between = (FRAME_UNITS[0] - wide) / (FRAME_UNITS[0] - 320)      # 0 at HD's width, 1 at the column's
        shift_x, shift_y = HD_BG_SHIFT[0] * (1 - between), HD_BG_SHIFT[1] * (1 - between)
        pans = self._location_pans(cy)
        picture = cy + HD_BG_SHIFT[1] + 32 - high / 2 <= 0 and cy + HD_BG_SHIFT[1] + 32 + high / 2 >= FRAME_UNITS[1]
        if picture:
            whole = max(wide / 480, tall / high)            # the picture fitted to the frame (2:3: exactly)
            scale = max(whole + (1 - whole) * between, wide / 480, tall / high)
            width, height = 480 * scale, high * scale
            ay = min(max(top + cy + shift_y, tall - height / 2), height / 2)
        else:
            width, height = 480., high
            # (HD's own offset from the column kept: the strip's place was chosen in HD's frame.)
            ay = top + cy + HD_BG_SHIFT[1] - (tall - FRAME_UNITS[1]) * self.STRIP_RISE
        if pans:
            ax = self.location_pan.x(self.session.engine.panel.location_align, width * 2, pygame.time.get_ticks(),
                                     wide * 2) / 2
        else:
            ax = side + cx + shift_x
        if picture:
            ax = min(max(ax, wide - width / 2), width / 2)
        return ((ax - width / 2) * unit_x, (ay - height / 2) * unit_y, width * unit_x, height * unit_y)

    def _blit_art(self, background, placement, target_size, viewport, alpha, *, cache=True):
        """Draw `background` laid over `placement` (see _background_placement), clipped to the frame. Where the
        picture does not reach the frame's edge (Cause of Death's art is exactly its screen wide, so the frame's side
        margins can reach past it), the art keeps its scale and the rest stays uncovered."""
        bw, bh = background.get_size()
        x, y, w, h = placement
        tw, th = target_size
        left, top, right, bottom = max(0., x), max(0., y), min(float(tw), x + w), min(float(th), y + h)
        if right - left < 1 or bottom - top < 1:
            return
        if (x, y, w, h) == (0, 0, tw, th):
            crop, area = None, viewport
        else:
            kx, ky = bw / w, bh / h                              # art pixels per target pixel
            crop = pygame.Rect(round((left - x) * kx), round((top - y) * ky),
                               round((right - left) * kx), round((bottom - top) * ky)).clip(background.get_rect())
            if crop.width <= 0 or crop.height <= 0:
                return
            area = pygame.Rect(viewport.x + round(left), viewport.y + round(top),
                               round(right - left), round(bottom - top))
        key = (id(background), None if crop is None else tuple(crop), area.size)
        # Between two frames of the same scene only the location pan and the implicit animations above change this
        # layer -- each settles after 0.25s -- so a frame whose key matches the last one reuses that scaled surface
        # instead of smoothscaling the same pixels again. Alpha is set fresh every time regardless (never left over
        # from a cache hit): a mid-transition frame's lowered alpha must not stick to a later, fully-opaque one
        # reusing the same cached surface.
        cached_key, cached_surface = self._background_layer_cache or (None, None)
        if cache and key == cached_key:
            scaled_bg = cached_surface
        else:
            source = background if crop is None else background.subsurface(crop)
            if bw >= 2 * bh and (self.__dict__.get('_frame_width', FRAME_UNITS[0]),
                                 self.__dict__.get('_frame_tall', FRAME_UNITS[1])) != FRAME_UNITS:
                # A strip (New Rules, BREW: pixel art the translators enlarged with nearest-neighbour) outside HD's
                # frame: pixel-perfect, its pixels kept square-edged (owner, 2026-11-11).
                scaled_bg = pygame.transform.scale(source, area.size)
            else:
                scaled_bg = pygame.transform.smoothscale(source, area.size)
            if min(pygame.image.tobytes(scaled_bg, 'RGBA')[3::4]) >= OPAQUE_ENOUGH:     # smoothscale leaves an opaque picture at 253 or 254
                scaled_bg = scaled_bg.convert()
            if cache:
                self._background_layer_cache = (key, scaled_bg)
        if scaled_bg.get_masks()[3]:
            scaled_bg = faded(scaled_bg, round(alpha))
        elif alpha < 255:
            scaled_bg = faded(scaled_bg.copy(), round(alpha))
        else:
            # Never given a whole-surface alpha, even 255: that takes a blit from about 1 ms to 33 on a phone.
            if cache and area == viewport:
                self._background_cover = (id(background), tuple(placement), tuple(viewport))
        self.window.blit(scaled_bg, area)

    def _draw_scene_badge(self, badge, *, previous_glyph=-1):
        layer = self.dialogue_renderer.frame(204 if badge.blue else 236, 13).copy()
        icon = self._chrome_image(badge.asset_id)
        if icon is not None:
            layer.blit(icon, icon.get_rect(center=(38, 30)))  # Layout 67 node 2.
        color = (69, 107, 176) if badge.text == 'Free Time' else (223, 163, 52)
        name = 'ArialRoundedMTBold16'
        if getattr(self.story_text.font(name), 'cap_height', None) is not None:
            name = 'ArialMT14'
            region = self.session.resources.dialogue_layout().bank.rectangle(67, 3)
            text, (x, y), scale = outline_badge_text(badge.text, self.story_text.font(name), region, color)
        else:
            text = self.story_text.layout(name, badge.text, 110, TextStyle(14, 1, color),
                                          previous_glyph=previous_glyph)
            x, y, scale = badge.text_origin
        self.story_text.draw_layout(layer, name, text, x, y, scale=scale)
        # 200ms MoveTo from x=-width/2 to center x=100. Ad-free top inset=10.
        left = -171 + (100 + 171 / 2) * badge.elapsed_ms / 200
        self.canvas.blit(pygame.transform.smoothscale(layer, (257, 90)), (round(left * 1.5), 15))

    def _draw_faceplace_toast(self, toast):
        """Corner alert for a newly-arrived Faceplace post: a card reading
        "faceplace alert", the poster's portrait + name + message text,
        persisting until explicitly dismissed -- confirmed from a real HD
        gameplay screenshot and real-device testing (see
        dtview_faceplace.FaceplaceToast), not decompiled; no method matching
        an alert/toast/badge exists anywhere in SHSFSView or
        SHSViewController's own symbol tables (checked exhaustively). Card
        size/colors/exact wording are a best-effort visual match to that
        screenshot, not a recovered native layout constant.
        """
        message = toast.message
        width, margin, padding = 220, 12, 10
        header_h, portrait_size = 26, 44
        name = (self.session.engine.character_names.get(message.from_id, '')
                if message.from_id >= 0 else '')
        text_x = padding + (portrait_size + padding if name else 0)
        text_width = width - padding * 2 - (portrait_size + padding if name else 0)
        # The name leads the message text as one flowing paragraph (e.g.
        # "Beth is remembering..."), not its own line -- matching the real
        # reference screenshot.
        combined = f'{name} {message.text}' if name else message.text
        lines = self._lines(combined, self.small, text_width)
        text_block_h = (self.small.get_linesize() + 3) * len(lines)
        body_h = padding * 2 + max(portrait_size if name else 0, text_block_h)
        layer = pygame.Surface((width, header_h + body_h), pygame.SRCALPHA)
        header_color, border_color = (59, 89, 152), (120, 150, 210)
        pygame.draw.rect(layer, header_color, (0, 0, width, header_h), border_top_left_radius=8,
                         border_top_right_radius=8)
        layer.blit(self.small.render('faceplace alert', True, (255, 255, 255)), (padding, 5))
        pygame.draw.rect(layer, (255, 255, 255), (0, header_h, width, body_h))
        if name:
            portrait = self._faceplace_toast_portrait(message.from_id, message.expression)
            if portrait is not None:
                layer.blit(portrait, (padding, header_h + padding))
        y = header_h + padding
        for index, line in enumerate(lines):
            if index == 0 and name and line.startswith(name):
                name_surface = self.small.render(name, True, (41, 104, 221))
                layer.blit(name_surface, (text_x, y))
                rest = line[len(name):]
                if rest:
                    layer.blit(self.small.render(rest, True, (30, 30, 30)), (text_x + name_surface.get_width(), y))
            else:
                layer.blit(self.small.render(line, True, (30, 30, 30)), (text_x, y))
            y += self.small.get_linesize() + 3
        pygame.draw.rect(layer, border_color, (0, 0, width, header_h + body_h), 2,
                         border_top_left_radius=8, border_top_right_radius=8,
                         border_bottom_left_radius=8, border_bottom_right_radius=8)
        layer = faded(layer, toast.alpha)
        slide = round(16 * (1 - toast.enter_progress))
        self.canvas.blit(layer, (SIZE[0] - width - margin, margin - slide))

    def _faceplace_toast_portrait(self, character_id, expression):
        variants = self.session.engine.character_art_variants.get(character_id)
        if not variants:
            return None
        image = self.dialogue_renderer.portrait(variants[max(0, expression) % len(variants)], False)
        if image is None:
            return None
        size = 44
        scale = min(size / image.get_width(), size / image.get_height())
        return pygame.transform.smoothscale(image, (round(image.get_width() * scale), round(image.get_height() * scale)))

    def _draw_menu(self):
        if self.pause_renderer is None:
            self.pause_renderer = PauseRenderer(self.session.resources.library,
                                                 self.story_text, self.dialogue_renderer)
        buttons = self.pause_renderer.draw(self.canvas, application=self.on_menu_page is not None,
                                            main_menu=self.on_main_menu is not None,
                                            pressed=self.press.pressed or self.menu_focus,
                                            elapsed_ms=self.pause_elapsed_ms, closing=self.pause_closing,
                                            extra_entries=((('Skip Ahead', ('skip_ahead',)),)
                                                           if self.skip_ahead and can_skip(self.session) else ())
                                            + ((('Undo', ('undo',)),) if self._undo_ready() else ()))
        self.buttons = [(pygame.Rect(*(round(value * 1.5) for value in rect)), command)
                        for rect, command in buttons]
        if pygame.time.get_ticks() < self.message_until:
            self._text(self.message, 30, 640, 420, font=self.small)

    def _date_first(self, details):
        """shshd-runtime: whether this card shows its date as the title (TRANSLATED_DATE_FIRST_PACKS: the BREW games). Not in a
        capture: an episode's preview picture keeps the story's name as the title (owner, 2026-11-07)."""
        if self.capture or not details.get('subtitle'):
            return False
        return free_setting(self.session.resources, 'TRANSLATED_DATE_FIRST_PACKS', 'date_first')

    def _title_renderer(self):
        """The chapter / week card: Cause of Death's own (SHS HD's at iPhone size), HD's with an HD bundle, else
        Android's."""
        if self.dialogue_renderer.game_id() == 'cod':
            if self.title_cod is None:
                self.title_cod = CodTitleRenderer(self.session.resources, self.dialogue_renderer, self.title_renderer)
            return self.title_cod
        return self.title_hd if self.title_hd.available() else self.title_renderer

    _tinted = None          # (area, window size, the sepia scene) while a pause menu or notice is open
    _pause_card = None      # (key, the scaled card, its buttons) while the pause menu rests

    def _draw_tinted(self, area):
        """The scene under a pause menu or notice, dimmed sepia. The game is held while one is open, so the tint is
        made once (as the original captures the scene) and reused, not recomputed every frame (~18 ms at 1080p)."""
        key = (tuple(area), self.window.get_size())
        if self._tinted is None or self._tinted[0] != key:
            self._tinted = key, self.pause_hd.sepia(self.window.subsurface(area).copy())
        self.window.blit(self._tinted[1], area)

    def _frame_part(self, index):
        """One of _present's 3:4 places in the frame, while it's the frame they were made for; else the frame itself
        (the same at 3:4)."""
        frames = self.__dict__.get('_frames')
        return frames[index] if frames is not None and frames[0] is self.bg_viewport else self.bg_viewport

    picture_frame = property(lambda self: self._frame_part(1), doc="A whole 3:4 picture: at the frame's bottom.")
    card_frame = property(lambda self: self._frame_part(2), doc='A card over the scene: centred in the frame.')
    alert_frame = property(lambda self: self._frame_part(3), doc="The Faceplace alert's strip: at the frame's top.")

    def _blit_part(self, layer, area, clip):
        """`layer` laid over `area` (resampled to it), within `clip`: only the part with something drawn on it is
        resampled (an HD overlay's frame-sized layer holds one small card)."""
        bounds = layer.get_bounding_rect()
        if bounds.width <= 0 or bounds.height <= 0:
            return
        kx, ky = area.width / layer.get_width(), area.height / layer.get_height()
        dest = pygame.Rect(area.x + round(bounds.x * kx), area.y + round(bounds.y * ky),
                           max(1, round(bounds.width * kx)), max(1, round(bounds.height * ky)))
        before = self.window.get_clip()
        self.window.set_clip(clip.clip(before))
        self.window.blit(pygame.transform.smoothscale(layer.subsurface(bounds), dest.size), dest)
        self.window.set_clip(before)

    def _draw_bands(self, area, backdrop):
        """The frame above and below `area` (a picture narrower in shape than the frame): the episode's frame backdrop
        where it has one (TRANSLATED_FRAME_BACKDROP), else the window's backdrop, as beside the frame."""
        frame = self.bg_viewport
        bands = [pygame.Rect(frame.x, frame.y, frame.width, area.y - frame.y),
                 pygame.Rect(frame.x, area.bottom, frame.width, frame.bottom - area.bottom)]
        bands = [band.clip(self.window.get_rect()) for band in bands if band.height > 0]
        if not bands:
            return
        own = self._frame_backdrop(frame.size)
        for band in bands:
            if own is not None:
                self.window.blit(own, band, band.move(-frame.x, -frame.y))
            elif backdrop is not None:
                self.window.blit(backdrop, band, band)
            else:
                self.window.fill((8, 12, 20), band)

    def _draw_picture_band(self, backdrop, height):
        """Above a 3:4 picture in a taller frame (picture_frame), the window's backdrop, as beside the frame."""
        band = pygame.Rect(self.bg_viewport.x, self.bg_viewport.y, self.bg_viewport.width,
                           self.picture_frame.y - self.bg_viewport.y).clip(self.window.get_rect())
        if band.height <= 0:
            return
        if backdrop is not None:
            self.window.blit(backdrop, band, band)
        else:
            self.window.fill((8, 12, 20), band)

    def _draw_hd_pause(self, frame):
        """HD's pause menu: the frame dimmed sepia with UIKit panels over it (desktop_pause_hd.py), its 3:4 card centred
        in a taller frame (card_frame)."""
        area = frame.clip(self.window.get_rect())
        frame = getattr(self, 'card_frame', frame)
        if area.width <= 0 or area.height <= 0:
            return
        if not self.pause_closing:           # Resume takes the tint away at once; only the card zooms out
            self._draw_tinted(area)
        settings = self._pause_settings()
        message = self.message if pygame.time.get_ticks() < self.message_until else ''
        scale = pause_scale(self.pause_elapsed_ms)
        size = tuple(max(1, round(length * scale)) for length in frame.size)
        # At rest (fully zoomed, no page sliding, no switch moving) the card only changes with what it shows, so the
        # drawn and scaled card is kept until then (~15 ms a frame at 1080p).
        resting = self.pause_elapsed_ms >= PAUSE_OPEN_MS and not self.pause_closing and not self.pause_hd.animating()
        key = (repr(settings), message, astuple(self.pause_hd.state), getattr(self.pause_hd, 'pressed', None), size)
        if resting and self._pause_card is not None and self._pause_card[0] == key:
            card, self.pause_buttons = self._pause_card[1:]
        else:
            layer, self.pause_buttons = self.pause_hd.layout(settings, message=message)
            if self.pause_closing:
                self.pause_buttons = []
            card = pygame.transform.smoothscale(layer, size)
            # A switch drawn with a new value has only just started moving.
            self._pause_card = (key, card, self.pause_buttons) if resting and not self.pause_hd.animating() else None
        self.window.blit(card, pygame.Rect((0, 0), size).move(frame.centerx - size[0] // 2, frame.centery - size[1] // 2))

    def _pause_settings(self):
        # No Skip Ad / Upsell Intros here: they only act as an episode starts, so the main menu's Options alone lists
        # them (owner).
        return dict(vibration=self.vibration_enabled, music=self.music_enabled, sound=self.sound_enabled,
                    aspect_ratio=ASPECT_NAMES[self.aspect_ratio],
                    **({'device_vibration': self.device_vibration_enabled} if pygame.supports_vibration() else {}),
                    **(dict(controller_confirm=CONFIRM_NAMES[self.controller_confirm],
                            grid_controls=GRID_CONTROLS_NAMES[self.grid_controls],
                            controller_vibration=pygame.vibration_source() == 'controller')
                       if pygame.controller_connected() else {}),
                    music_volume=self.music_volume,
                    sound_volume=self.sound_volume, side_panels=self.panels_open, choice_hints=self.choice_hints,
                    skip_minigames=self.skip_minigames, skip_ahead=self.skip_ahead,
                    **({'skip_ahead_row': True} if self.skip_ahead and can_skip(self.session) else {}),
                    undo=self.undo, **({'undo_row': True} if self._undo_ready() else {}),
                    autoplay=self.autoplay, disable_choice_timer=self.disable_choice_timer,
                    **({'hd_backdrop': self.hd_backdrop} if self.backdrop_switch() else {}),
                    **({'hires_portraits': self.hires_portraits} if self.hires_switch() else {}),
                    **({'ms3_characters': self.ms3_characters} if self.ms3_switch() else {}),
                    **({'java_look': self.java_look} if self.java_look_switch() else {}),
                    **({'brew_08_backgrounds': self.brew_08_backgrounds} if self.brew_08_switch() else {}),
                    **({'smartphone_music': self.smartphone_music} if self.smartphone_switch() else {}),
                    **({'word_grid_skin': self.word_grid_skin} if self.smartphone_switch() and self.word_grid_switch() else {}),
                    **({'grids_as_memory': self.grids_as_memory} if self.memory_grid_switch() else {}),
                    **(dict(ch_portraits=self.ch_portraits, ch_backdrop=self.ch_backdrop) if self.ch_switch() else {}),
                    **({'arena_minigames': self.arena_minigames} if self.minigames_switch() else {}),
                    **({'arena_skin': self.arena_skin} if self.hires_switch() and self.x360_arena_switch() else {}))

    def frame_units(self):
        """The frame's size in layout units for General's Aspect Ratio in this window (frame_shape.frame_units)."""
        return frame_shape.frame_units(self.aspect_ratio, self.window.get_size(), self.fixed_window)

    def x360_arena_switch(self):
        """shshd-runtime: whether the "Use X360 Arena Skin" switch is offered: in a translated New Rules episode (hires_switch)
        with Use Translated Mini-Games on, and the X360 addon's arena skin imported (desktop_nr_arena_x360; owner,
        2026-10-31)."""
        if not (self.hires_switch() and self.arena_minigames):
            return False
        if self._x360_arena is None:
            self._x360_arena = self.x360_arena_renderer.available()
        return self._x360_arena

    def pause_box(self):
        if self.pause_hd.available() and not self.error:
            return self.pause_hd.layout(self._pause_settings())[0]
        return None if self.pause_renderer is None else self.pause_renderer.canvas.copy()

    def _draw_notice(self, frame, dim=True):
        """Whichever native menu-engine window is on top of `self.notice_stack` -- the "Exit Game?" confirmation
        (menu 17, a faceplace wall link tap, see `_wall_pointer`'s own note) or the Decision Tree's "Locked"
        notice (menu 28, see `_tree_click`). The scene under it is dimmed sepia the same way the pause menu
        dims it (an HD photo of the "Locked" notice over a dialogue scene shows exactly that), and the tint goes
        when the window's button closes it. `dim` is False when the pause menu has already tinted the frame."""
        area = frame.clip(self.window.get_rect())
        if area.width <= 0 or area.height <= 0:
            return
        if dim:
            self._draw_tinted(area)
        current = self.notice_stack.current
        if current != self.notice_shown:
            # A window that has just opened zooms in over the tinted scene, as "Play with sound?" does
            # (`notifyNewMenu`'s 0.4 s zoom; the owner, on the device).
            self.notice_shown, self.notice_ms = current, 0
        layer = pygame.Surface((HD_FRAME[0] * HD_S, HD_FRAME[1] * HD_S), pygame.SRCALPHA)
        self.notice_windows.draw(layer, current, pressed=self.notice_pressed or self.notice_focus)
        scale = pause_scale(self.notice_ms)
        card = getattr(self, 'card_frame', area)        # the window's 3:4 picture, centred in a taller frame
        size = tuple(max(1, round(length * scale)) for length in card.size)
        self.window.blit(pygame.transform.smoothscale(layer, size),
                         pygame.Rect((0, 0), size).move(card.centerx - size[0] // 2, card.centery - size[1] // 2))

    def _pause_point(self, position):
        frame = self.card_frame
        return ((position[0] - frame.x) * 768 / frame.width, (position[1] - frame.y) * 1024 / frame.height)

    def _set_volume(self, which, value):
        value = min(1., max(0., value))
        changed = value != (self.music_volume if which == 'music' else self.sound_volume)
        if which == 'music':
            self.music_volume = value
            if self.audio:
                self.music_stream.set_volume(value)
        else:
            self.sound_volume = value
        if changed:
            # `SHSWidgetMenu::sliderChanged`: the Music slider previews its sound at its own volume while Music is on
            # (a volume of 0 plays nothing); the Sound FX slider previews at the new Sound FX volume. Neither restarts
            # a preview still playing.
            if which == 'music' and self.music_enabled and value > 0:
                self._ui_sound('MUSIC_SLIDER_SOUND', volume=value, when_idle=True)
            elif which != 'music':
                self._ui_sound('SOUND_SLIDER_SOUND', when_idle=True)
        if self.on_settings:
            self.on_settings()

    def _pause_mouse(self, event):
        """Pointer input for HD's pause menu; returns True when it consumed the event."""
        state = self.pause_hd.state
        if event.type == pygame.MOUSEWHEEL:
            state.scroll = min(state.max_scroll, max(0., state.scroll - event.y * 40))
            return True
        if event.type not in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
            return False
        if event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
            state.focus = None                      # the pointer takes over from the arrow keys
        x, y = self._pause_point(event.pos)
        if event.type == pygame.MOUSEBUTTONUP:
            state.drag = None
            return True
        if event.type == pygame.MOUSEMOTION:
            if state.drag and state.drag[0] == 'slider':
                self._set_volume(state.drag[1], self.pause_hd.slider_value(x))
            elif state.drag and state.drag[0] == 'scroll':
                state.scroll = min(state.max_scroll, max(0., state.drag[1] - (y - state.drag[2])))
            return True
        if event.button != 1:
            return True
        for rect, command in self.pause_buttons:
            if not rect.collidepoint(x, y):
                continue
            if command[0] == 'pause_slider':
                state.drag = ('slider', command[1])
                self._set_volume(command[1], self.pause_hd.slider_value(x))
            elif command[0] == 'pause_scroll':
                state.drag = ('scroll', state.scroll, y)
            else:
                self.command(command)
            break
        return True

    def open_pause(self, *, sound=True):
        if self.menu_open and not self.pause_closing:
            return
        self.pause_hd.reset()
        self.menu_focus = None
        self.picker_pointer_down = False
        if self.session.engine.word_grid:
            self.session.grid_pointer('cancel')
        self.menu_open = True
        self.session.engine.faceplace_toast = None
        self.pause_elapsed_ms, self.pause_closing = 0, False
        self._sync_music()
        if sound:
            self._menu_sound(opening=True)

    def command(self, command):
        self.press.cancel()
        self.gear_pointer_down = False
        self._sync_text_input()
        kind = command[0]
        if (self.fade or self.session.transitioning) and kind == 'menu':
            return                                   # the pause button is off during a transition
        if kind == 'pause_open':
            # A row of the menu (`SHSWidgetMenu::itemSelected`) and its back button (`buttonPressed`, tags 1-4) both
            # click; switches and sliders do not.
            self.pause_hd.open(command[1])
            self._menu_sound()
            return
        if kind == 'pause_back':
            self.pause_hd.back()
            self._menu_sound()
            return
        if kind == 'pause_cycle' and command[1] == 'aspect_ratio':
            # General's Aspect Ratio: a shape picked on its choice page (or the next one), kept by the app (on_settings).
            choices = frame_shape.CHOICES
            self.aspect_ratio = (command[2] if len(command) > 2 else
                                 choices[(choices.index(self.aspect_ratio) + 1) % len(choices)])
            if self.on_settings:
                self.on_settings()
            if len(command) > 2:
                self.pause_hd.back()
            self._menu_sound()
            return
        if kind == 'pause_cycle' and len(command) > 2 and command[1] in ('grid_controls', 'controller_confirm'):
            # A value picked on the option's choice page (desktop_pause_hd.CHOICE_NAMES): as a step to it, then back.
            if getattr(self, command[1]) != command[2]:
                self.command(command[:2])
            self.pause_hd.back()
            self._menu_sound()
            return
        if kind == 'pause_cycle' and command[1] == 'grid_controls':
            self.grid_controls = 'hold' if self.grid_controls == 'tap' else 'tap'
            if self.on_settings:
                self.on_settings()
            return
        if kind == 'pause_cycle' and command[1] == 'controller_confirm':
            # Options' Controller page: the confirm button, bottom or right (gamepad.py); the app keeps it.
            self.controller_confirm = 'east' if self.controller_confirm == 'south' else 'south'
            pads = pygame.gamepads()
            if pads is not None:
                pads.confirm = self.controller_confirm
            if self.on_settings:
                self.on_settings()
            return
        if kind == 'pause_link':
            # A link in a help page's text (an About page's override): behind the game's "Exit Game?" prompt, as the
            # main menu's copy of the page already does (application_hd.HdShell.activate).
            self._offer_link(command[1])
            return
        if kind == 'pause_toggle':
            if command[1] == 'music':
                self.music_enabled = not self.music_enabled
                self.pause_song_wanted = self.music_enabled                 # SHSEngine::setMusicEnabled(on, true)
                self.pause_song_page = self.pause_hd.state.screen
                self._sync_music()
            elif command[1] == 'side_panels':
                self.toggle_panels()
                self._menu_sound()
                return
            elif command[1] == 'choice_hints':
                self.choice_hints = not self.choice_hints
            elif command[1] == 'skip_minigames':
                self.skip_minigames = not self.skip_minigames
            elif command[1] == 'skip_ahead':
                self.skip_ahead = not self.skip_ahead
            elif command[1] == 'undo':
                self.undo = not self.undo
            elif command[1] == 'skip_ad_intros':
                self.skip_ad_intros = not self.skip_ad_intros
            elif command[1] == 'autoplay':
                self.autoplay, self.autoplay_ms = not self.autoplay, 0
            elif command[1] == 'disable_choice_timer':
                self.disable_choice_timer = not self.disable_choice_timer
            elif command[1] == 'hd_backdrop':
                self.hd_backdrop = not self.hd_backdrop
            elif command[1] == 'hires_portraits':
                self.set_hires_portraits(not self.hires_portraits)
            elif command[1] == 'ms3_characters':
                self.set_ms3_characters(not self.ms3_characters)
            elif command[1] == 'java_look':
                self.set_java_look(not self.java_look)
            elif command[1] == 'brew_08_backgrounds':
                self.set_brew_08_backgrounds(not self.brew_08_backgrounds)
            elif command[1] == 'smartphone_music':
                self.smartphone_music = not self.smartphone_music
            elif command[1] == 'word_grid_skin':
                self.word_grid_skin = not self.word_grid_skin
            elif command[1] == 'grids_as_memory':
                self.grids_as_memory = not self.grids_as_memory
            elif command[1] == 'ch_portraits':
                self.set_ch_portraits(not self.ch_portraits)
            elif command[1] == 'ch_backdrop':
                self.ch_backdrop = not self.ch_backdrop
            elif command[1] == 'arena_minigames':
                self.arena_minigames = not self.arena_minigames
            elif command[1] == 'arena_skin':
                self.arena_skin = not self.arena_skin
            elif command[1] == 'vibration':
                self.vibration_enabled = not self.vibration_enabled
                if self.vibration_enabled and self.audio:
                    self._buzz()            # SHSEngine::setVibrationEnabled vibrates once when it is switched on
            elif command[1] == 'device_vibration':
                self.device_vibration_enabled = not self.device_vibration_enabled
                if self.device_vibration_enabled and pygame.supports_vibration():
                    pygame.vibrate()        # (the same: the device's own vibrator)
            else:
                self.sound_enabled = not self.sound_enabled
            if command[1] == 'sound':
                if self.sound_enabled:
                    # `SHSEngine::setSoundEnabled(true, true)`: the switch's own sound, other effects stopped.
                    self._ui_sound('SOUND_ON_SOUND', stop_others=True)
            else:
                # The other switches are silent natively; they click as the menu's rows do (owner's choice,
                # 2026-10-23).
                self._menu_sound()
            if self.on_settings:
                self.on_settings()
            return
        if self.menu_open and kind in ('save', 'load'):
            self._menu_sound()
        if kind == 'menu':
            self.open_pause()
        elif kind == 'skip_ahead':
            self._menu_sound()
            self._skip_ahead()
        elif kind == 'undo':
            self._menu_sound()
            self._undo()
        elif kind == 'resume':
            # The menu scales from 1 to 0.00001 over 400 ms before the story resumes (`notifyNewMenu`'s zoom run
            # backwards, docs/MAIN_MENU.md); `tick` closes it once the zoom is done.
            if not self.pause_closing:
                self._menu_sound()
            self.pause_closing = self.menu_open
        elif kind == 'pause_page' and self.on_menu_page:
            self.on_menu_page(command[1])
            self._menu_sound()
        elif kind == 'main_menu':
            # HD's Main Menu row saves the game, then returns to the main menu (the application's automatic
            # checkpoint does the saving as it leaves the episode). The menu's box goes along: it zooms out over
            # the main menu while that screen's buttons slide in.
            box = self.pause_box() if self.on_main_menu else None
            self.menu_open = False
            if self.on_main_menu:
                self.on_main_menu(pause_box=box)
                self._menu_sound()
        elif kind == 'save':
            try:
                self.session.save()
                self._notice('Progress saved')
            except (OSError, ValueError) as error:
                self._notice(f'Save failed: {error}')
        elif kind == 'load':
            try:
                restored = Session.load(self.session.resources, self.session.save_path)
                if hasattr(self.session, 'process'):
                    self.session.process.attach(restored, restored=True)
                self.session = restored
                self.error, self.music_token = None, None
                self.sound_serial = restored.engine.sound_serial
                self.vibration_serial = restored.engine.vibration_serial
                self.menu_open = False
                self._notice('Progress loaded')
            except (SaveError, OSError) as error:
                self._notice(str(error))
        elif not self.error and not self.fade and not self.session.transitioning:
            action = self.session.pending
            if action and action.name == 'text_input' and not self.menu_open and self.active:
                if kind in ('input_dismiss', 'input_focus'):
                    self.input_error, self.input_keyboard = None, True
                    if self.text_input_started:
                        # A phone's keyboard closed by Back (owner's g54) leaves SDL's text input on, so nothing
                        # changes here; asking again shows the on-screen keyboard (SDL_StartTextInput shows it when
                        # it is hidden). A desktop has no on-screen keyboard: nothing to see.
                        pygame.key.start_text_input()
                elif kind == 'continue':
                    self._submit_input(action)
            if action and action.name == 'character_picker' and kind in ('choose', 'continue'):
                self._attempt(lambda: self.session.answer(command[1] if kind == 'choose' else None))
            ask = self.host_prompt if self.host_prompt and self.host_prompt['action'] is action else None
            if self._choice_busy(action):
                pass                    # `SHSMenu`: one selection per menu; input is over until it has closed
            elif ask is not None:
                if kind == 'choose' and 0 <= command[1] < len(ask['options']):
                    self._menu_sound()
                    if self._hd_choice_drawn() and command[1] != ask.get('next_row'):
                        self.choice_closing = dict(action=action, index=command[1], ms=0, prompt=ask)
                    else:
                        self.host_prompt = None
                        ask['resolve'](command[1])
            elif kind == 'choose' and action and action.name == 'choice' and not self.session.choice_ready:
                pass                    # SHSUIMenu ignores selections during its 250 ms attachment (Session.choice_ready)
            elif kind == 'choose' and action and action.name == 'choice' and self._hd_choice_closes(action, command[1]):
                self._menu_sound()      # `SHSUIMenu::handleMenuSelection`, modes 1 and 3 (a timeout is silent)
                self.choice_closing = dict(action=action, index=command[1], ms=0)
            elif kind == 'choose' and action and action.name == 'choice':
                if self._choice_pickable(action, command[1]):
                    self._menu_sound()
                self._pick(action, command[1])
            elif kind == 'choose' and action and action.name == 'word_game':
                self._answer(command[1])
            elif kind == 'continue' and action and action.name in ('presentation', 'dialogue', 'message_panel',
                                                                     'survey_confirmation', 'cutscene'):
                if not self.autoplay and not self._continue_guarded(action):   # Autoplay: `_tick_autoplay`
                    if (action.name == 'message_panel' and self.dialogue_renderer.game_id() == 'cod'
                            and self.session.engine.message_panel is not None
                            and self.session.engine.message_panel.ready):
                        self._menu_sound()      # owner: CoD clicks when its panel's Continue is tapped
                    self._answer()
            elif action and action.name == 'football' and kind in ('continue', 'choose'):
                self._attempt(lambda: self.session.answer(command[1] if kind == 'choose' else None))
            elif kind == 'arena_key' and action and action.name == 'arena_frame':
                self.session.arena_press(command[1])
            elif kind == 'arena_answer' and action and action.name in ('arena_menu', 'arena_info'):
                self._attempt(lambda: self.session.answer(command[1]))
        self._sync_text_input()

    def _continue_guarded(self, action):
        """Whether a continue tap lands in a dialogue line's or page's first CONTINUE_GUARD_MS (ignored)."""
        motion = self.session.engine.dialogue_animation if action.name == 'dialogue' else None
        return motion is not None and motion.elapsed_ms < CONTINUE_GUARD_MS

    def _choice_busy(self, action):
        """Whether `action`'s choice is closing after a pick, or held faded out behind a link's prompt."""
        return any(state is not None and state['action'] is action for state in (self.choice_closing, self.choice_held))

    def _choice_focus_rows(self, action, asking):
        """The rows the arrow keys step through, top to bottom: a choice's enabled options, the quiz's answers or a
        host prompt's options; none while the pause menu, an error or a closing choice holds the screen."""
        if (self.menu_open or self.error or self.fade or self.session.transitioning or action is None
                or not (asking or action.name in ('choice', 'word_game'))
                or self._choice_busy(action)):
            return []
        if not hasattr(self.session.resources, 'read_asset'):
            if asking or action.name != 'choice':
                return []
            return [SimpleNamespace(index=index, rect=None)
                    for index, enabled in enumerate(action.details['enabled']) if enabled]
        try:
            if asking and self.host_prompt.get('loading'):
                return []
            page = self.choice_renderer.page(self.host_prompt['session'] if asking else self._choice_source())
        except (ContentError, pygame.error, OSError, ValueError):
            return []
        return sorted((row for row in page.rows if row.enabled), key=lambda row: row.rect.y)

    def _move_choice_focus(self, rows, step):
        indices = [row.index for row in rows]
        if self.choice_focus in indices:
            position = max(0, min(len(rows) - 1, indices.index(self.choice_focus) + step))
        else:
            position = 0 if step > 0 else len(rows) - 1
        row = rows[position]
        self.choice_focus = row.index
        if row.rect is None:
            return
        page = self.choice_renderer.cached_page
        area = page.table if hasattr(page, 'rows_top') else self.choice_renderer.viewport
        scroll = self.scroll / 1.5
        if row.rect.y - scroll < area.y:
            scroll = row.rect.y - area.y
        elif row.rect.y + row.rect.height - scroll > area.y + area.height:
            scroll = row.rect.y + row.rect.height - area.y - area.height
        self.scroll = min(self.max_scroll, max(0, scroll * 1.5))

    def _press_token(self):
        action = self.session.pending
        game = self.session.engine.word_game
        return (id(self.session), id(action), self.menu_open,
                self.session.vm.steps_executed, game.round if game else None, self.scroll)

    def cancel_pointer(self):
        self.press.cancel()
        self.gear_pointer_down = False
        self.picker_pointer_down = False
        if self.session.engine.word_grid:
            self.session.grid_pointer('cancel')

    def handle_event(self, event):
        self._sync_text_input()
        if event.type == pygame.QUIT:
            return False
        if self.notice_stack is not None and self.notice_stack.stack:
            # A native notice/confirm window (the wall's "Exit Game?" confirmation, or the Decision Tree's
            # "Locked" notice) is modal: it takes every event ahead of everything else below, including the
            # pause menu's own Escape handling right after this.
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.notice_stack.pop()
            elif event.type == pygame.KEYDOWN:
                self._notice_key(event.key)
            else:
                self._notice_pointer(event)
            return True
        if self.pause_closing and self.menu_open and event.type in (
                pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION, pygame.MOUSEWHEEL,
                pygame.TEXTINPUT):
            return True                         # the menu is zooming out after Resume: input waits for the story
        if self.tree_zoom.tab is not None or self.tree_zoom.showing:
            if self._tree_zoom_pointer(event):
                return True
            event = self._portrait_game_event(event)
        if event.type == pygame.KEYUP:
            self._puzzle_key_up(event)
        if event.type == pygame.KEYDOWN and (self._arena_key(event) or self._slot_key(event) or self._memory_key(event) or self._leash_key(event) or self._puzzle_key(event) or self._football_key(event) or self._grid_key(event)):
            return True
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.menu_open:
                if not self.pause_hd.available() or self.pause_hd.back():
                    self.command(('resume',))
                return True
            self.command(('menu',))
            return True
        if event.type == pygame.KEYDOWN and event.key == pygame.K_TAB and not self.menu_open:
            self.toggle_panels()
            return True
        if event.type in (pygame.WINDOWFOCUSLOST, pygame.WINDOWFOCUSGAINED):
            self.active = event.type == pygame.WINDOWFOCUSGAINED
            self._sync_music()
            self.cancel_pointer()
            self._sync_text_input()
            return True
        action = self.session.pending
        if action and action.name == 'text_input' and (not self.active or self.error):
            return True
        if self.panels_open and self.panels_progress >= 1 and not self.menu_open and not self.error:
            if self._tree_pointer(event):
                return True
        if self.panels_open and self.panels_progress >= 1 and not self.menu_open and not self.error:
            if self._wall_pointer(event):
                return True
        if (self.panels_open and self.panels_progress >= 1 and not self.menu_open and not self.error
                and event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self._tree_click(event.pos)):
            return True
        pointer = (event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION)
                   and (event.type == pygame.MOUSEMOTION or event.button == 1))
        if self.menu_open and self.pause_elapsed_ms < PAUSE_OPEN_MS and pointer:
            self.press.cancel()
            return True
        if pointer and not self.menu_open and hasattr(self, 'viewport'):
            x = (event.pos[0] - self.viewport.x) * SIZE[0] / self.viewport.width
            y = (event.pos[1] - self.viewport.y) * SIZE[1] / self.viewport.height
            hit = self._gear_hit(event.pos) or (self.viewport.collidepoint(event.pos) and any(
                command == ('menu',) and self._button_hit(rect, command, x, y) for rect, command in self.buttons))
            if event.type == pygame.MOUSEBUTTONDOWN and hit:
                self.gear_pointer_down = True
                self.press.update('down', ('menu',), self._press_token())
                return True
            if self.gear_pointer_down:
                phase = 'up' if event.type == pygame.MOUSEBUTTONUP else 'move'
                command = self.press.update(phase, ('menu',) if hit else None, self._press_token())
                if phase == 'up':
                    self.gear_pointer_down = False
                if command:
                    self.command(command)
                return True
        if (action and action.name == 'character_picker' and not self.menu_open and not self.error
                and event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP) and event.button == 1):
            x = (event.pos[0] - self.viewport.x) * 320 / self.viewport.width
            y = (event.pos[1] - self.viewport.y) * 480 / self.viewport.height + self.story_lift     # (centred)
            if event.type == pygame.MOUSEBUTTONDOWN:
                self.picker_pointer_down = 0 <= x <= 320 and 0 <= y <= 480
            elif self.picker_pointer_down:
                self.picker_pointer_down = False
                if self._picker().confirm_hit((x, y)):
                    self.command(('continue',))
                else:
                    index = self.session.engine.character_picker.hit((x, y))
                    if index is not None:
                        self.command(('choose', index))
            return True
        asking = self.host_prompt is not None and self.host_prompt['action'] is action
        if (action and action.name in ARENA_ACTIONS and not self.menu_open and not self.error and not asking
                and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1):
            frame = self.picture_frame
            command = self._arena_tap(action, (event.pos[0] - frame.x) * 768 / frame.width,
                                      (event.pos[1] - frame.y) * 1024 / frame.height)
            if command is not None:
                self.command(command)
            return True
        if (action and action.name in ('x360_slot', 'x360_diss', 'brew_catch') and not self.menu_open and not self.error and not asking
                and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1):
            frame = self.picture_frame
            x = (event.pos[0] - frame.x) * 768 / frame.width
            y = (event.pos[1] - frame.y) * 1024 / frame.height
            if 0 <= x < 150 and 880 <= y <= 1024:
                self.command(('menu',))
            elif 0 <= x <= 768 and 0 <= y <= 1024:
                self._attempt(lambda: self.session.answer(None))
            return True
        if (action and action.name in ('shs11_memory', 'shs11_reflex') and not self.menu_open and not self.error and not asking
                and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1):
            frame = self.picture_frame
            x = (event.pos[0] - frame.x) * 768 / frame.width
            y = (event.pos[1] - frame.y) * 1024 / frame.height
            if 0 <= x < 150 and 880 <= y <= 1024:
                self.command(('menu',))
            elif 0 <= x <= 768 and 0 <= y <= 1024:
                game, renderer = self._shs11_game(action)
                cell = None if game.phase != PLAY else renderer.cell_at(x, y)
                renderer.cursor_shown = False
                if game.phase != PLAY or cell is not None:
                    self._attempt(lambda: self.session.answer(cell))
            return True
        if (action and action.name == 'x360_leash' and not self.menu_open and not self.error and not asking
                and (event.type == pygame.MOUSEMOTION
                     or (event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP) and event.button == 1))):
            self._leash_pointer(event)
            return True
        if (action and action.name == 'x360_puzzle' and not self.menu_open and not self.error and not asking
                and (event.type == pygame.MOUSEMOTION
                     or (event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP) and event.button == 1))):
            self._puzzle_pointer(event)
            return True
        if (action and action.name == 'football' and not self.menu_open and not self.error and not asking
                and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1):
            if self._football().__class__ is HdFootballRenderer:
                frame = self.picture_frame
                x = (event.pos[0] - frame.x) * 768 / frame.width
                y = (event.pos[1] - frame.y) * 1024 / frame.height
                if 0 <= x < 150 and 880 <= y <= 1024:
                    self.command(('menu',))
                elif 0 <= x <= 768 and 0 <= y <= 1024:
                    self._attempt(lambda: self.session.answer(self.football_hd.hit((x, y))))
                return True
            x = (event.pos[0] - self.viewport.x) * 320 / self.viewport.width
            y = (event.pos[1] - self.viewport.y) * 480 / self.viewport.height
            if 0 <= x <= 320 and 0 <= y <= 480:
                self._attempt(lambda: self.session.answer(self.football_renderer.hit((x, y))))
            return True
        if (action and action.name == 'word_grid' and not self.menu_open and not self.error and not asking
                and event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION)
                and (event.type == pygame.MOUSEMOTION or event.button == 1)):
            hd = self._word_grid().__class__ is HdWordRenderer
            if hd:
                frame = self.picture_frame
                x = (event.pos[0] - frame.x) * 768 / frame.width
                y = (event.pos[1] - frame.y) * 1024 / frame.height
                (cx, cy), radius = self.GEAR_FRAME_CENTRE, self.GEAR_FRAME_RADIUS     # (in points, twice the units)
                gear = (x - 2 * cx) ** 2 + (y - 2 * cy) ** 2 <= (2 * radius) ** 2
            else:
                x = (event.pos[0] - self.viewport.x) * 320 / self.viewport.width
                y = (event.pos[1] - self.viewport.y) * 480 / self.viewport.height
                gear = 0 <= x < 60 and 422 <= y < 480
            if event.type == pygame.MOUSEBUTTONDOWN and gear:
                self.command(('menu',))
            else:
                phase = {pygame.MOUSEBUTTONDOWN: 'down', pygame.MOUSEMOTION: 'move',
                         pygame.MOUSEBUTTONUP: 'up'}[event.type]
                self.grid_cursor = None
                renderer = self.word_hd if hd else self.grid_renderer
                index = renderer.hit((x, y), self.session.engine.word_grid)
                self._attempt(lambda: self.session.grid_pointer(phase, index))
            return True
        if self.menu_open and self.pause_hd.available() and self._pause_mouse(event):
            return True
        if self.menu_open and event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_F5, pygame.K_F9):
                self.command(('save' if event.key == pygame.K_F5 else 'load',))
            elif self.pause_hd.available() and not self.error:
                command = self.pause_hd.key(event.key)
                if command is not None and command[0] == 'pause_volume':
                    volume = self.music_volume if command[1] == 'music' else self.sound_volume
                    self._set_volume(command[1], volume + command[2])
                elif command is not None:
                    self.command(command)
            else:
                targets = [command for _, command in self.buttons]
                focus = self.menu_focus if self.menu_focus in targets else None
                if focus_step(event.key):
                    self.menu_focus = step_focus(targets, focus, focus_step(event.key))
                elif event.key in KEYS_ACTIVATE and focus is not None:
                    self.command(focus)
            return True
        if self.menu_open and event.type in (pygame.MOUSEWHEEL, pygame.TEXTINPUT):
            return True
        # Native table rows remain selected under the finger and dispatch on
        # release. Keep the originating panel/deal so expiry cannot answer a
        # successor, and dragging off a row cannot activate a different one.
        if ((self.menu_open or action and action.name in ('choice', 'word_game'))
                and event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION)
                and (event.type == pygame.MOUSEMOTION or event.button == 1)):
            x = (event.pos[0] - self.viewport.x) * SIZE[0] / self.viewport.width
            y = (event.pos[1] - self.viewport.y) * SIZE[1] / self.viewport.height
            hit = (next((command for rect, command in self.buttons if self._button_hit(rect, command, x, y)), None)
                   if self.viewport.collidepoint(event.pos) else None)
            phase = {pygame.MOUSEBUTTONDOWN: 'down', pygame.MOUSEBUTTONUP: 'up',
                     pygame.MOUSEMOTION: 'move'}[event.type]
            if event.type == pygame.MOUSEMOTION:
                self.choice_focus = self.menu_focus = None
            if self._choice_drag(phase, y):
                return True
            command = self.press.update(phase, hit, self._press_token())
            if command is not None:
                self.command(command)
            return True
        if event.type == pygame.KEYDOWN:
            self.press.cancel()
            # The letter shortcuts are letters while a name is typed (owner, 2026-11-07: a name with a `u` undid the game).
            typing = action is not None and action.name == 'text_input'
            if event.key == pygame.K_n and not typing and self.skip_ahead and self._skip_ahead_ready():
                self._skip_ahead()
            if event.key == pygame.K_u and not typing and self._undo_ready():
                self._undo()
                return True
            rows = (self._choice_focus_rows(action, asking)
                    if event.key in (pygame.K_UP, pygame.K_DOWN, pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE)
                    else [])
            if event.key in (pygame.K_F5, pygame.K_F9):
                self.command(('save' if event.key == pygame.K_F5 else 'load',))
            elif event.key in (pygame.K_UP, pygame.K_DOWN) and rows:
                self._move_choice_focus(rows, -1 if event.key == pygame.K_UP else 1)
            elif (event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE)
                    and any(row.index == self.choice_focus for row in rows)):
                self.command(('choose', self.choice_focus))
            elif event.key == pygame.K_RETURN or (event.key == pygame.K_SPACE and action and action.name != 'text_input'):
                self.command(('continue',))
            elif action and action.name == 'character_picker' and event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                # Left / Right bring the previous / next portrait (by its original place) to the front, as tapping it
                # does; Enter confirms. Keyboard play is this player's addition.
                picker = self.session.engine.character_picker
                if picker is not None and picker.characters and not picker.moving:
                    step = 1 if event.key == pygame.K_RIGHT else -1
                    self.command(('choose', (picker.selected + step) % len(picker.characters)))
            elif action and action.name == 'character_picker' and (pygame.K_1 <= event.key <= pygame.K_9 or event.key == pygame.K_0):
                picker = self.session.engine.character_picker
                # 1-9, and 0 for a tenth (a translated pack's ten photos, BREW's M.A.S.H.; owner, 2026-11-07).
                # Keys wait for a running swap to end (CharacterPicker.moving): mashed keys left the rings misplaced.
                index = 9 if event.key == pygame.K_0 else event.key - pygame.K_1
                if index < len(picker.characters) and not picker.moving:
                    self.command(('choose', index))
            elif action and (action.name in ('choice', 'word_game', 'football') or asking) and pygame.K_1 <= event.key <= pygame.K_9:
                index = event.key - pygame.K_1
                if asking:
                    if index < len(self.host_prompt['options']):
                        self.command(('choose', index))
                elif action.name == 'football' or (action.name == 'word_game' and index < len(self.session.engine.word_game.options)) or (action.name == 'choice'
                        and index < len(action.details['options']) and action.details['enabled'][index]):
                    self.command(('choose', index))
            elif action and action.name == 'text_input' and event.key == pygame.K_BACKSPACE:
                action.details['draft'] = action.details.get('draft', '')[:-1]
                self.input_error, self.input_keyboard = None, True
            elif event.key in (pygame.K_UP, pygame.K_DOWN, pygame.K_PAGEUP, pygame.K_PAGEDOWN):
                delta = -60 if event.key in (pygame.K_UP, pygame.K_PAGEUP) else 60
                self.scroll = min(self.max_scroll, max(0, self.scroll + delta))
        elif event.type == pygame.TEXTINPUT and action and action.name == 'text_input':
            if not self.input_error:
                metrics = self.session.name_input_metrics()
                for char in event.text:
                    draft, error = accept_name_character(action.details['draft'], char, **metrics)
                    action.details['draft'] = draft
                    if error:
                        self.input_error, self.input_keyboard = error, False
                        break  # A modal alert also stops the rest of a paste.
                    self.input_keyboard = True
        elif event.type == pygame.MOUSEWHEEL:
            self.press.cancel()
            self.scroll = min(self.max_scroll, max(0, self.scroll - event.y * 40))
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._gear_hit(event.pos):
                self.command(('menu',))
            elif self.viewport.collidepoint(event.pos):
                x = (event.pos[0] - self.viewport.x) * SIZE[0] / self.viewport.width
                y = (event.pos[1] - self.viewport.y) * SIZE[1] / self.viewport.height
                for rect, command in self.buttons:
                    if self._button_hit(rect, command, x, y):
                        self.command(command)
                        break
            elif getattr(self, 'bg_viewport', None) is not None and self.bg_viewport.collidepoint(event.pos):
                # Outside the column but in the frame (HD's margins; a taller frame's height above the column): a
                # screen that continues on a tap anywhere in the column does here too, as HD's whole view does.
                whole = pygame.Rect(0, 0, *SIZE)
                if any(command == ('continue',) and rect.contains(whole) for rect, command in self.buttons):
                    self.command(('continue',))
        self._sync_text_input()
        return True

    # HD's gear (pack 155 frame 58, 74 x 72 units placed at (-3.5, 441)) sits flush with the frame's left and bottom
    # edges, partly in the 32-unit margin outside the UI column, so its touch area is tested in frame units, not column
    # units. Its frame is mostly transparent: the gear itself fills (0, 462)-(47, 511), centred at (23.5, 486.5), 26.4
    # units at most from the centre (the pressed glow 30.8). The touch area is that circle at the glow's radius; the
    # frame's box and the column buttons' rect (-32, 422, 92, 58) reached twice as far right and 24 units above, so taps
    # on the bar opened the pause menu (owner, 2026-11-07).
    GEAR_FRAME_CENTRE, GEAR_FRAME_RADIUS = (23.5, 486.5), 30

    def _hd_gear_shown(self):
        try:
            return self.dialogue_renderer.hd_bar() is not None
        except (AttributeError, ValueError, pygame.error):
            return False

    def _gear_hit(self, position):
        if not any(command == ('menu',) for _, command in self.buttons) or self.menu_open or not self._hd_gear_shown():
            return False
        # The gear is at the frame's bottom left whatever its shape (General's Aspect Ratio), at the story's scale.
        frame = self.bg_viewport
        unit = frame.width / self.__dict__.get('_frame_width', FRAME_UNITS[0])
        x, y = (position[0] - frame.x) / unit, (position[1] - frame.bottom) / unit + FRAME_UNITS[1]
        (cx, cy), radius = self.GEAR_FRAME_CENTRE, self.GEAR_FRAME_RADIUS
        return (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2

    def _button_hit(self, rect, command, x, y):
        """A button under column point (x, y). With HD's gear, the gear's own button is `_gear_hit`, not its rect."""
        if command == ('menu',) and self._hd_gear_shown():
            return False
        return rect.collidepoint(x, y)

    # -- warping through the story tree (SHSDTView touchesEnded / SHSDTTitleOverView / SHSDTHelpOverView) --------

    # -- a choice too long for its panel (hd_choice: the rows that don't fit scroll) ------------------------------------

    choice_drag = None          # [y at the press (column units), scroll then, moved] while a finger is down on a choice
    CHOICE_DRAG_START = 4       # column units a finger moves before it scrolls the rows instead of pressing one

    def _choice_drag(self, phase, y):
        """A drag scrolls a choice's rows when they don't all fit, as native's table view scrolls under the finger
        (owner, 2026-11-08: the scroll bar showed on the g54 but touch couldn't move it; only the wheel and keys did).
        Once the finger has moved it picks nothing on release, and a flick glides on (momentum, on touch hosts; owner,
        2026-11-09). A touch that catches a gliding list only stops it. True when the event was the drag's."""
        if phase == 'down':
            caught = self.choice_fling.stop()
            self.choice_drag = [y, self.scroll, False, caught] if self.max_scroll > 0 and not self.menu_open else None
            if caught and self.choice_drag is not None:
                self.press.cancel()
                return True
            return False
        drag = self.choice_drag
        if drag is None:
            return False
        if phase == 'up':
            self.choice_drag = None
            if drag[2]:
                self.choice_fling.release()
            if drag[2] or drag[3]:
                self.press.cancel()
                return True
            return False
        if not drag[2] and abs(y - drag[0]) < self.CHOICE_DRAG_START:
            return drag[3]
        if not drag[2]:
            drag[2] = True
            self.press.cancel()
        self.scroll = min(self.max_scroll, max(0, drag[1] - (y - drag[0]) * 1.5))
        self.choice_fling.track(self.scroll)
        return True

    def _coast_choice(self):
        """Each frame: a flicked choice's rows gliding on, until they slow to nothing or reach the first or last row."""
        fling = getattr(self, 'choice_fling', None)
        if fling is None:
            return
        if getattr(self, 'max_scroll', 0) <= 0:
            fling.stop()
            return
        values = fling.step(self.scroll)
        if values is not None:
            self.scroll = min(self.max_scroll, max(0, values[0]))
            fling.settled(self.scroll)

    tree_drag = None            # [pointer, scroll (y, x) at the start, moved] while a finger is down on the tree

    def _tree_pointer(self, event):
        """The wheel and a drag scroll a tree taller than its panel; a drag that moved is not a tap."""
        panels = self.side_panels
        area = panels.tree_rect
        if area is None:
            return False
        s = panels.tree_scale or 1.0
        if event.type == pygame.MOUSEWHEEL:
            if not area.collidepoint(pygame.mouse.get_pos()):
                return False
            self.tree_fling.stop()
            if pygame.key.get_mods() & pygame.KMOD_SHIFT:          # shift: the wheel scrolls instead of zooming
                panels.scroll_tree(-event.y * 40 / s, event.x * 40 / s)
            else:
                panels.zoom_tree(event.y, pygame.mouse.get_pos())
                panels.scroll_tree(0, event.x * 40 / s)
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 2 and area.collidepoint(event.pos):
            panels.reset_tree_zoom()                               # the middle button fits the tree to the panel again
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and area.collidepoint(event.pos):
            # A touch that catches the gliding tree only stops it; it is not a tap on the scene under it.
            self.tree_drag = [event.pos, (panels.tree_scroll, panels.tree_scroll_x), self.tree_fling.stop()]
            return True
        elif event.type == pygame.MOUSEMOTION and self.tree_drag:
            (x, y), (down, across) = event.pos, (self.tree_drag[0], self.tree_drag[1])
            if max(abs(x - down[0]), abs(y - down[1])) > 6:
                self.tree_drag[2] = True
            if self.tree_drag[2]:
                panels.tree_scroll = across[0] - (y - down[1]) / s
                panels.tree_scroll_x = across[1] - (x - down[0]) / s
                panels.tree_follow = False
                self.tree_fling.track(panels.tree_scroll, panels.tree_scroll_x)
                return True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.tree_drag:
            dragged, self.tree_drag = self.tree_drag[2], None
            if dragged:
                self.tree_fling.release()
            return dragged
        return False

    # -- the faceplace wall (`SHSFSView`'s scroll view and `SHSFSMessageContentView touchesEnded:`) -------------------

    wall_drag = None            # [pointer, scroll at the start, moved] while a finger is down on the wall

    def _wall_pointer(self, event):
        """The wheel and a drag scroll the wall; a tap (a touch that did not move) on a linked message opens its
        link -- natively straight to the browser (`SHSFSMessageContentView touchesEnded:`), but through the app's
        own "Exit Game?" confirmation first when one is available (`self.notice_stack`; see its own setup note),
        this player's own addition."""
        panels = self.side_panels
        area = panels.wall_rect
        if area is None:
            return False
        s = panels.wall_scale or 1.0
        if event.type == pygame.MOUSEWHEEL:
            if not area.collidepoint(pygame.mouse.get_pos()):
                return False
            self.wall_fling.stop()
            panels.scroll_wall(-event.y * 40 / s)
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and area.collidepoint(event.pos):
            # As the tree's: catching the gliding wall is not a tap on a link.
            self.wall_drag = [event.pos, panels.wall_scroll, self.wall_fling.stop()]
            return True
        if event.type == pygame.MOUSEMOTION and self.wall_drag:
            down = self.wall_drag[0]
            if max(abs(event.pos[0] - down[0]), abs(event.pos[1] - down[1])) > 6:
                self.wall_drag[2] = True
            if self.wall_drag[2]:
                panels.wall_scroll = self.wall_drag[1] - (event.pos[1] - down[1]) / s
                panels.wall_scrolled_at = pygame.time.get_ticks()
                self.wall_fling.track(panels.wall_scroll)
                return True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.wall_drag:
            dragged, self.wall_drag = self.wall_drag[2], None
            if dragged:
                self.wall_fling.release()
            if not dragged:
                url = next((url for rect, url in panels.wall_targets if rect.collidepoint(event.pos)), None)
                if url:
                    if self.notice_stack is not None:
                        self.wall_link = url
                        self.notice_stack.queue(self.exit_menu)
                    else:
                        self._open_link(url)
            return dragged or area.collidepoint(event.pos)
        return False

    def _wall_perform(self, number):
        """`SHSEngine::doMenuEngineAction` action 18 ("Exit Game?" -> Yes; CoD: menu 16's action 24): the only action menu 17's two buttons
        ever reach here -- its "No" button is a plain back step, popped by `MenuStack.press()` itself without
        calling this (the Decision Tree's "Locked" notice, menu 28, is the same: its one OK button is also a
        plain back step, so `self.notice_stack`'s shared `perform` callback never runs for it either)."""
        self.notice_stack.clear()
        if number == self.exit_action and self.wall_link:
            self._open_link(self.wall_link)

    notice_focus = None             # the notice window's button the arrow keys (or a controller) have highlighted

    def _notice_key(self, key):
        """Keys while a notice window is open: the arrows highlight its buttons and Enter presses the highlighted one;
        with none highlighted, Enter presses a window's only button, or highlights the first of several (Escape steps
        back: handle_event)."""
        if self.notice_ms < PAUSE_OPEN_MS:
            return
        targets = [command for _, command in self.notice_windows.hits]
        focus = self.notice_focus if self.notice_focus in targets else None
        if focus_step(key):
            self.notice_focus = step_focus(targets, focus, focus_step(key))
        elif key in KEYS_ACTIVATE and targets:
            if focus is None and len(targets) > 1:
                self.notice_focus = targets[0]
                return
            self.notice_focus = None
            self.notice_stack.press(self.notice_data.action((focus or targets[0])[1]))

    def _arena_renderer(self):
        """New Rules' arena, told how tall the frame is in the window so it scales its art up to there: in the X360
        look where the "Use X360 Arena Skin" switch is on and the X360 addon is imported, else New Rules' own."""
        renderer = (self.x360_arena_renderer if self.arena_skin and self.x360_arena_switch()
                    else self.nr_arena_renderer)
        viewport = getattr(self, 'picture_frame', None)
        if viewport is not None:
            renderer.target_height = viewport.height
        return renderer

    def _arena_tap(self, action, x, y):
        """The command for a click at (x, y) in frame pixels (768 x 1024) on New Rules' arena: the gear, bottom left,
        opens the pause menu as on football's frame; Sequences' items (their number keys, 765) and the info box take
        clicks. Anywhere else a tap is the OK key, the only key the turning games play by (owner, 2026-10-31)."""
        if 0 <= x < 150 and 880 <= y <= 1024:
            return ('menu',)
        if not (0 <= x <= 768 and 0 <= y <= 1024):
            return None
        command = self._arena_renderer().hit((x, y))
        if command is None and action.name == 'arena_frame':
            command = ('arena_key', -5)
        return command

    def _arena_key(self, event):
        """New Rules' arena by keys (a controller's arrive as these, gamepad.py): Enter / Space (a controller's
        confirm) are its OK, the arrows its joystick, Backspace its right soft key and 0-9 its number keys; on its menu
        the arrows move the highlight and Enter picks. Escape stays the pause menu. True when the key was one."""
        action = self.session.pending
        if (action is None or action.name not in ARENA_ACTIONS or self.menu_open or self.error
                or self.host_prompt is not None):
            return False
        key = event.key
        if action.name in ('arena_entrance', 'arena_exit'):
            return key in ARENA_KEYS or key in ARENA_NUMBER_KEYS          # New Rules takes no keys meanwhile
        if action.name == 'arena_frame':
            code = ARENA_KEYS.get(key)
            if code is None:
                code = ARENA_NUMBER_KEYS.get(key)
            if code is None:
                return False
            self.command(('arena_key', code))
            return True
        if action.name == 'arena_menu' and key in (pygame.K_UP, pygame.K_DOWN):
            self._arena_renderer().move_focus(action, -1 if key == pygame.K_UP else 1)
            return True
        if key in KEYS_ACTIVATE:
            focus = self._arena_renderer().focus(action)
            self.command(('arena_answer', focus if focus is not None else 0))
            return True
        return False

    def _football_input(self):
        action = self.session.pending
        return (action is not None and action.name == 'football' and not self.menu_open and not self.error
                and self.host_prompt is None)

    def _slot_key(self, event):
        """The slot machine and Diss Practice take one input: Enter, Space or a controller's confirm. True when the key
        was one."""
        action = self.session.pending
        if (action is None or action.name not in ('x360_slot', 'x360_diss', 'brew_catch') or self.menu_open or self.error
                or self.host_prompt is not None or event.key not in KEYS_ACTIVATE):
            return False
        self._attempt(lambda: self.session.answer(None))
        return True

    def shs11_renderer(self, action):
        """What draws an SHS '11 game: its own look, or the word game's with the switch on and its art there."""
        game = self.session.engine.shs11_memory if action.name == 'shs11_memory' else None
        stands_in = game is not None and game.grid          # in a grid's place it always has a grid's look (owner, 2026-11-04)
        if self.shs11_hd is not None and (self.shs11_hd.art_available() if stands_in else self.word_grid_skin and self.shs11_hd.available()):
            return self.shs11_hd
        return self.shs11_memory_renderer if action.name == 'shs11_memory' else self.shs11_reflex_renderer

    def _warm_shs11_sounds(self, game):
        """Decode a game's sounds as it opens, so that the first of each isn't decoded in the frame it plays in."""
        if game is self._shs11_warmed or not self.sound_enabled:
            return
        self._shs11_warmed = game
        hd_sounds = getattr(game, 'grid', False) or self.session.shs11_hd_sounds
        for asset in {a for assets in GRID_SOUNDS.values() for a in assets} if hd_sounds else SHS11_GAME_SOUNDS:
            try:
                self._sound(asset, lambda name=asset: self.session.resources.read_asset(name))
            except (ContentError, pygame.error) as error:
                logging.warning('Sound %s cannot be played: %s', asset, error)

    _shs11_warmed = None

    def _shs11_game(self, action):
        """(The SHS '11 game in play, its renderer)."""
        game = self.session.engine.shs11_memory if action.name == 'shs11_memory' else self.session.engine.shs11_reflex
        return game, self.shs11_renderer(action)

    def _memory_key(self, event):
        """SHS '11's games: 1 to 9 pick their cells, as '11's keys do. The arrows, WASD and a D-pad move a cursor over the grid and
        Enter, Space or confirm pick under it, or go on from the tutorial's boxes. True when the key was one."""
        action = self.session.pending
        if (action is None or action.name not in ('shs11_memory', 'shs11_reflex') or self.menu_open or self.error
                or self.host_prompt is not None):
            return False
        game, renderer = self._shs11_game(action)
        playing = game.phase == PLAY
        cell = MEMORY_DIGITS.get(event.key)
        if cell is not None:
            if playing:
                renderer.cursor = cell
                self._attempt(lambda: self.session.answer(cell))
            return True
        if event.key in KEYS_ACTIVATE:
            chosen = renderer.cursor if playing else None
            self._attempt(lambda: self.session.answer(chosen))
            return True
        move = MEMORY_MOVES.get(event.key)
        if move is None:
            return False
        if playing:
            column, row = renderer.cursor % 3, renderer.cursor // 3
            renderer.cursor = (row + move[1]) % 3 * 3 + (column + move[0]) % 3
            renderer.cursor_shown = True
        return True

    def _leash_ready(self):
        action = self.session.pending
        return (action is not None and action.name == 'x360_leash' and not self.menu_open and not self.error
                and self.host_prompt is None)

    def _leash_key(self, event):
        """The leash game: OK starts it; the arrows, WASD and a controller's D-pad shake it. A controller's stick reads as
        arrows too, but _leash_stick reads it for itself. True when the key was one."""
        if not self._leash_ready():
            return False
        if event.key in KEYS_ACTIVATE:
            self._attempt(lambda: self.session.answer(None))
            return True
        direction = LEASH_KEYS.get(event.key)
        if direction is None:
            return False
        button = getattr(event, 'controller', None)
        if button is None or pygame.gamepads().holding(button):
            self.session.engine.x360_leash.shake(direction)
        return True

    def _leash_stick(self):
        """The leash game, each frame: a controller's stick, read as the prototype reads it."""
        if not self._leash_ready():
            self.leash_anchor = None
            return
        pads = pygame.gamepads()
        for x, y in pads.sticks.values() if pads is not None else ():
            direction = stick_direction(x, y)
            if direction is not None:
                self.session.engine.x360_leash.shake(direction, SHAKE_WINDOW_STICK_MS)

    def _leash_pointer(self, event):
        """The leash game's mouse and touch: a press is OK, or the gear; holding it and dragging back and forth shakes."""
        frame = self.picture_frame
        x = (event.pos[0] - frame.x) * 768 / frame.width
        y = (event.pos[1] - frame.y) * 1024 / frame.height
        if event.type == pygame.MOUSEBUTTONUP:
            self.leash_anchor = None
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if 0 <= x < 150 and 880 <= y <= 1024:
                self.command(('menu',))
            elif 0 <= x <= 768 and 0 <= y <= 1024:
                self.leash_anchor = (x, y)
                self._attempt(lambda: self.session.answer(None))
        elif self.leash_anchor is not None:
            direction = drag_direction(self.leash_anchor, x, y)
            if direction is not None:
                self.leash_anchor = (x, y)
                self.session.engine.x360_leash.shake(direction)

    def _puzzle_ready(self):
        action = self.session.pending
        return (action is not None and action.name == 'x360_puzzle' and not self.menu_open and not self.error
                and self.host_prompt is None)

    def _puzzle_key(self, event):
        """The jewel puzzle: OK starts it, is held to drag, and goes on past the score; the arrows, WASD and a controller's
        D-pad or stick move the cursor, repeating while held. True when the key was one."""
        if not self._puzzle_ready():
            return False
        if event.key in KEYS_ACTIVATE:
            self.puzzle_pad = getattr(event, 'controller', None) is not None
            self._attempt(lambda: self.session.answer(None))
            return True
        direction = LEASH_KEYS.get(event.key)
        if direction is None:
            return False
        self.session.engine.x360_puzzle.move(direction)
        if getattr(event, 'controller', None) is None:          # (a controller's direction repeats by itself)
            self.puzzle_key = (event.key, direction, REPEAT_DELAY_MS)
        return True

    def _puzzle_key_up(self, event):
        if self.puzzle_key is not None and self.puzzle_key[0] == event.key:
            self.puzzle_key = None
        action = self.session.pending
        if event.key in KEYS_ACTIVATE and action is not None and action.name == 'x360_puzzle':
            self.session.engine.x360_puzzle.release()

    def _puzzle_frame(self, elapsed_ms):
        """The jewel puzzle, each frame: a held key's repeats, and a controller's confirm let go."""
        action = self.session.pending
        if action is None or action.name != 'x360_puzzle':
            self.puzzle_key, self.puzzle_pad = None, False
            return
        game = self.session.engine.x360_puzzle
        if not self._puzzle_ready():
            game.let_go()
            self.puzzle_key, self.puzzle_pad = None, False
            return
        if self.puzzle_pad:
            pads = pygame.gamepads()
            if pads is None or not pads.holding('confirm'):
                game.release()
                self.puzzle_pad = False
        if self.puzzle_key is not None:
            key, direction, left = self.puzzle_key
            left -= elapsed_ms
            if left <= 0:
                game.move(direction)
                left = REPEAT_MS
            self.puzzle_key = (key, direction, left)

    def _puzzle_pointer(self, event):
        """The jewel puzzle's mouse and touch: a press on a jewel holds it and a drag takes its row or column along; off
        the board a press is OK, or the gear; a mouse over the board with its button up points the cursor."""
        frame = self.picture_frame
        x = (event.pos[0] - frame.x) * 768 / frame.width
        y = (event.pos[1] - frame.y) * 1024 / frame.height
        game = self.session.engine.x360_puzzle
        if event.type == pygame.MOUSEBUTTONUP:
            game.let_go()
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if 0 <= x < 150 and 880 <= y <= 1024:
                self.command(('menu',))
            elif on_board(x, y) and game.phase == 'running':
                game.grab(*cell_at(x, y))
            elif 0 <= x <= 768 and 0 <= y <= 1024:
                self._attempt(lambda: self.session.answer(None))
                if game.button:                                 # (not a hold of its own: nothing to let go of)
                    game.release()
        elif game.target is not None:
            game.drag(*cell_at(x, y))
        elif on_board(x, y):
            game.point(*cell_at(x, y))

    def _football_key(self, event):
        """A play picked by its position (FOOTBALL_BUTTONS, FOOTBALL_KEYPAD); True when the key was one."""
        if not self._football_input():
            return False
        slot = FOOTBALL_BUTTONS.get(getattr(event, 'controller', None), FOOTBALL_KEYPAD.get(event.key))
        if slot is None:
            return False
        self.command(('choose', slot))
        return True

    grid_cursor = None              # the word grid's cell the arrow keys (or a controller) have highlighted

    def _grid_key(self, event):
        """The word grid by keys (this player's; a finger draws the word natively): the arrows move a highlighted
        cell, Enter adds it to the word (starting one; only a neighbour of the last letter joins, as under a finger),
        Backspace lets the word go as lifting the finger would (its error sound when it was no word). The first key
        only shows the highlight. True when the key was one of these."""
        action = self.session.pending
        game = self.session.engine.word_grid
        if (action is None or action.name != 'word_grid' or game is None or self.menu_open or self.error
                or self.host_prompt is not None):
            return False
        key, width = event.key, game.problem.width
        cells = len(game.board)
        moves = {pygame.K_LEFT: (-1, 0), pygame.K_RIGHT: (1, 0), pygame.K_UP: (0, -1), pygame.K_DOWN: (0, 1)}
        if key not in moves and key not in KEYS_ACTIVATE and key != pygame.K_BACKSPACE:
            return False
        if self._grid_holding_mode(event):
            if key in KEYS_ACTIVATE and self.grid_cursor is not None and 0 <= self.grid_cursor < cells:
                cursor = self.grid_cursor
                self._attempt(lambda: self.session.grid_pointer('down', cursor))
                self.grid_drag, self.grid_step_ms = True, GRID_HOLD_FIRST_MS
                return True
            if key in moves and self.grid_drag:
                return True                     # the held drag steers itself (_grid_hold)
        if self.grid_cursor is None or not 0 <= self.grid_cursor < cells:
            if key == pygame.K_BACKSPACE and game.selection:
                self._attempt(lambda: self.session.grid_pointer('up'))
            else:
                self.grid_cursor = cells // 2 if not game.selection else game.selection[-1]
            return True
        if key in moves:
            dx, dy = moves[key]
            col, row = self.grid_cursor % width, self.grid_cursor // width
            col = min(width - 1, max(0, col + dx))
            row = min(cells // width - 1, max(0, row + dy))
            self.grid_cursor = row * width + col
        elif key == pygame.K_BACKSPACE:
            if game.selection:
                self._attempt(lambda: self.session.grid_pointer('up'))
        else:
            cursor = self.grid_cursor
            self._attempt(lambda: self.session.grid_pointer('move' if game.selection else 'down', cursor))
        return True

    grid_drag = False               # Hold mode: the confirm button is down on the grid (a finger laid on it)
    grid_step_ms = 0                # Hold mode: ms until the held drag steps to the next cell

    def _grid_holding_mode(self, event):
        """Whether a controller key works the grid in Hold mode (Options' Word Grid Controls)."""
        return (self.grid_controls == 'hold' and getattr(event, 'controller', None) is not None
                and pygame.gamepads() is not None)

    def _grid_hold(self, elapsed_ms):
        """Hold mode, each frame: while the confirm button is held the highlighted cell follows the D-pad or the stick,
        eight ways (gamepad.Gamepads.steering), every GRID_HOLD_STEP_MS, and each cell it reaches joins the word as
        under a dragged finger; letting go lifts the finger (a word that was none gets its error sound)."""
        if not self.grid_drag:
            return
        pads, game = pygame.gamepads(), self.session.engine.word_grid
        action = self.session.pending
        if (pads is None or game is None or action is None or action.name != 'word_grid' or self.menu_open
                or not pads.holding('confirm')):
            self.grid_drag = False
            if game is not None and action is not None and action.name == 'word_grid':
                self._attempt(lambda: self.session.grid_pointer('up'))
            return
        dx, dy = pads.steering()
        if not (dx or dy):
            self.grid_step_ms = 0                     # a fresh push steps at once
            return
        self.grid_step_ms -= elapsed_ms
        if self.grid_step_ms > 0:
            return
        self.grid_step_ms = GRID_HOLD_STEP_MS
        width = game.problem.width
        col = min(width - 1, max(0, self.grid_cursor % width + dx))
        row = min(len(game.board) // width - 1, max(0, self.grid_cursor // width + dy))
        if row * width + col != self.grid_cursor:
            self.grid_cursor = cursor = row * width + col
            self._attempt(lambda: self.session.grid_pointer('move', cursor))

    def _notice_pointer(self, event):
        """Pointer input while a native notice/confirm window is open (same hit-list convention as
        `HdShell.pointer_down`/`pointer_up`, driven here instead of there)."""
        if event.type not in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP) or self.notice_ms < PAUSE_OPEN_MS:
            return                          # nothing takes input while the window zooms in
        point = self._pause_point(event.pos)
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.notice_pressed = next((c for r, c in reversed(self.notice_windows.hits) if r.collidepoint(point)), None)
            return
        pressed, self.notice_pressed = self.notice_pressed, None
        if pressed is None:
            return
        for rect, command in reversed(self.notice_windows.hits):
            if rect.collidepoint(point) and command == pressed:
                self.notice_stack.press(self.notice_data.action(command[1]))
                return

    def _open_link(self, url):
        """`UIApplication openURL:` -- the system's handler for the link."""
        if self.url_opener is not None:
            self.url_opener(url)
            return
        try:
            opened = webbrowser.open(url)
        except webbrowser.Error:
            opened = False
        if not opened:
            logging.warning("failed to open URL: '%s'", url)

    def _tree_click(self, position):
        """A tap on the Decision Tree: a node warps to that scene, Rewind to the scene before the current one and
        Fast Forward to the next one already seen. Returns whether the tap landed on the tree's controls."""
        target = next((command for rect, command in self.side_panels.tree_targets if rect.collidepoint(position)), None)
        if target is None:
            return False
        engine = self.session.engine
        if (self.fade or self.session.transitioning or pygame.time.get_ticks() < self.warp_lockout
                or engine.dt_view.current is None):
            return True
        view = engine.dt_view
        if not self.warp_unlocked:
            # `touchesEnded:` -- while the lock flag is set a touch on any scene (or on Rewind / Fast Forward)
            # shows the native "Locked" notice (menu 28, string 271) -- a modal window pausing the game behind
            # it, not the toast `_notice()` draws for host-side messages; falls back to the toast only without
            # an HD bundle imported (no resource 17 to read menu 28 from either).
            if self.notice_stack is not None and self.exit_menu == 17:      # SHS HD's menus (CoD's 28 is an info page)
                self.notice_stack.queue(28)
            else:
                self._notice(self._locked_message())
            return True
        if target[0] == 'node':
            # Only a scene on the followed story (`DTNode` flag +0x1b1, `active`) is a target; the grayed ones and the automatic
            # branches and joins are not.
            node = target[1] if target[1].active and target[1].node_type not in NOT_WARPABLE else None
        elif target[0] == 'rewind':
            node = view.real_parent(view.current)
        else:
            node = view.real_child(view.current)
        if node is None or not self.session.has_tree_state(node):
            return True
        self._warp(node)
        return True

    def _locked_message(self):
        try:
            from .menu import MenuStrings
            return MenuStrings.parse(self.session.resources.library.hd_raw_resource(15))[271]
        except (AttributeError, ContentError, ValueError, IndexError):
            return 'Please complete Football Season episode to unlock this feature.'

    def _skip_ahead_ready(self):
        """Nothing is holding the story up that a skip shouldn't run over."""
        return (not self.error and not self.fade and self.host_prompt is None and can_skip(self.session)
                and not (self.notice_stack is not None and self.notice_stack.stack))

    def _skip_ahead(self):
        """Skip Ahead (skip_ahead.py): the session goes to the next stop, and the screen fades in from black on it, as a
        warp's does. Its music is whichever should be playing there. The sounds and buzzes along the way are dropped."""
        if not self._skip_ahead_ready():
            return
        moved = []
        self._attempt(lambda: moved.append(skip_ahead(self.session)))
        if self.error:
            return
        if not moved[0]:
            self._notice('Nothing left to skip')
            return
        engine = self.session.engine
        self.sound_serial, self.vibration_serial = engine.sound_serial, engine.vibration_serial
        self.menu_open = self.pause_closing = False
        self.autoplay_ms = 0
        self.side_panels.tree_follow = True
        self.location_pan = LocationPan()
        self.location_shown = self.location_changing = None
        self.ui_layers = self.ui_handover = None
        self.fade = dict(kind=6, phase='in', since=pygame.time.get_ticks(), frozen=None)

    def _undo_for(self, session):
        """The undo chain of the episode `session` plays (undo.py), or None."""
        record_id = (getattr(session.resources, 'record', None) or {}).get('id')
        if self._undo_chain is None or self._undo_chain[0] != record_id:
            self._undo_chain = (record_id, chain_for(session))
        return self._undo_chain[1]

    def _record_undo(self):
        """Each frame, while Allow Undo is on: a save when a new stop has come up; the chain goes once the episode ends."""
        session = self.session
        if not self.undo or self.error or getattr(session, 'ephemeral', False):
            return
        chain = self._undo_for(session)
        if chain is None:
            return
        if session.episode_ended:
            if self._undo_seen is not False:
                chain.clear()
                self._undo_seen = False
            return
        action = session.pending
        if action is None or action is self._undo_seen or session.transitioning:
            return
        self._undo_seen = action
        self._attempt(lambda: chain.record(session))

    def _undo_ready(self):
        """Undo is on, nothing holds the story up, and there's a save to go back to. A mini-game's skip prompt doesn't
        hold it: the pause menu opens over the prompt, which is a stop of its own (undoing there goes back one)."""
        if not self.undo or self.error or self.fade or self.session.episode_ended:
            return False
        chain = self._undo_for(self.session)
        return chain is not None and (chain.can_undo(self.session) or self._undo_restarts())

    def _undo_restarts(self):
        """Whether Undo restarts the mini-game under way rather than going back (owner, 2026-11-06): one of the engine's
        games is being played (with Skip Mini-games on, Play was picked: at its skip prompt it goes back as at any
        stop) and its save is the chain's latest. New Rules' arena games are the story's own script, stops and all."""
        action = self.session.pending
        if action is None or action.name not in MINIGAMES:
            return False
        if self.host_prompt is not None and self.host_prompt['action'] is action:
            return False                                            # (still at its skip prompt)
        chain = self._undo_for(self.session)
        return chain is not None and chain.at_latest(self.session)

    def _undo(self):
        """Undo (undo.py): back to the last stop kept, faded in from black as Skip Ahead's and a warp's are. In a
        mini-game under way, that game from its start, without its skip prompt (Play was already picked)."""
        if not self._undo_ready():
            return
        restart = self._undo_restarts()
        try:
            chain = self._undo_for(self.session)
            restored = chain.restart(self.session) if restart else chain.undo(self.session)
        except (SaveError, VMError, OSError, ValueError) as error:
            self._notice(f'Could not undo: {error}')
            return
        if restored is None:
            return
        restored.share_names(self.session.engine.strings)          # the one names table (Session.share_names)
        if hasattr(self.session, 'process'):
            self.session.process.attach(restored, restored=True)
        self.session = restored
        self._undo_seen = restored.pending                          # (it's the chain's end already)
        self.error, self.music_token = None, None
        self.sound_serial = restored.engine.sound_serial
        self.vibration_serial = restored.engine.vibration_serial
        self.menu_open = self.pause_closing = False
        self.host_prompt = None
        self.minigame_played = None
        self.autoplay_ms = 0
        self.side_panels.tree_follow = True
        self.location_pan = LocationPan()
        self.location_shown = self.location_changing = None
        self.ui_layers = self.ui_handover = None
        self.fade = dict(kind=6, phase='in', since=pygame.time.get_ticks(), frozen=None)
        if restart:
            prompt = self._host_prompt(wait=True)                   # (Skip Mini-games: its prompt, answered Play)
            if prompt is not None and prompt['action'] is restored.pending:
                self.host_prompt = None
                prompt['resolve'](len(prompt['options']) - 1)

    def _warp(self, node):
        """`SHSDTView warpToNode:animatedScroll:`: load the scene's saved game and fade the game back in from black; the
        side panels stay open and the tree scrolls to the scene."""
        self.tree_zoom.close()          # `warpToNode:` -> `closeDTZ`
        try:
            restored = self.session.warp(node)
        except (SaveError, VMError, OSError, ValueError) as error:
            self._notice(f'Could not warp: {error}')
            return
        if hasattr(self.session, 'process') and restored is not self.session:
            self.session.process.attach(restored, restored=True)
        self.session = restored
        self.error, self.music_token = None, None
        self.sound_serial = restored.engine.sound_serial
        self.vibration_serial = restored.engine.vibration_serial
        self.menu_open = False
        self.side_panels.tree_follow = True
        self.location_pan = LocationPan()
        self.location_shown = self.location_changing = None
        self.ui_layers = self.ui_handover = None
        now = pygame.time.get_ticks()
        self.fade = dict(kind=6, phase='in', since=now, frozen=None)
        self.warp_lockout = now + 1000

    def snapshot(self, size=(432, 580)):
        """The game's frame as a saved-game screenshot for the episode picker (the pause menu left out)."""
        opened, self.menu_open = self.menu_open, False
        shape, self.aspect_ratio = self.aspect_ratio, '3:4'
        # A live (non-capture) Desktop's own render() ends with pygame.display.flip(), presenting straight to the
        # real screen -- fine for its normal per-frame use, but this method also runs mid-transition (the
        # end-of-episode card's sepia source, a resume tile's screenshot) purely to read pixels back off `window`,
        # not to be seen. Without this, that flip briefly shows the live, un-sepia'd frame (this method's own
        # render(), menu_open forced off) before the real next frame replaces it -- confirmed live: the
        # "Want More Content?" card flashing over raw gameplay chrome first instead of appearing straight over
        # the sepia backdrop, the one the pause menu's own equivalent path never does.
        was_capture, self.capture = self.capture, True
        try:
            self.render()
        finally:
            self.menu_open = opened
            self.capture = was_capture
            self.aspect_ratio = shape
        frame = self.bg_viewport.clip(self.window.get_rect())
        return pygame.transform.smoothscale(self.window.subsurface(frame).copy(), size)

    def _coast_panels(self):
        """Each frame: the story tree and the wall gliding on after a drag (momentum); the panels' own clamps end a
        glide at an edge."""
        panels = getattr(self, 'side_panels', None)
        if panels is None:
            return
        values = self.tree_fling.step(panels.tree_scroll, panels.tree_scroll_x)
        if values is not None:
            (panels.tree_scroll, panels.tree_scroll_x), panels.tree_follow = values, False
        values = self.wall_fling.step(panels.wall_scroll)
        if values is not None:
            panels.wall_scroll, = values
            panels.wall_scrolled_at = pygame.time.get_ticks()

    def tick(self, elapsed_ms):
        self._record_undo()
        if self.active:
            self._coast_panels()
            self._coast_choice()
            self._grid_hold(elapsed_ms)
            self._leash_stick()
            self._puzzle_frame(elapsed_ms)
            self._x360_tutorial_sounds()
        self.tree_zoom.advance(elapsed_ms)
        if self.hint_discount_ms:
            discount = min(elapsed_ms, self.hint_discount_ms)
            self.hint_discount_ms -= discount
            elapsed_ms -= discount
        if self.active and self.notice_stack is not None and self.notice_stack.stack:
            self.notice_ms = min(PAUSE_OPEN_MS, self.notice_ms + elapsed_ms)
        elif self.notice_stack is not None and not self.notice_stack.stack:
            self.notice_shown = None
            if self.link_answer is not None:
                value, self.link_answer = self.link_answer, None
                self.choice_held = None
                self._answer_now(value)
        if self.active and self.menu_open and self.pause_closing:
            remaining, self.pause_elapsed_ms = self.pause_elapsed_ms, max(0, self.pause_elapsed_ms - elapsed_ms)
            if not self.pause_elapsed_ms:
                self.menu_open = self.pause_closing = False
                self._sync_music()
                elapsed_ms -= remaining             # the story runs on only from the moment the menu has gone
        elif self.active and self.menu_open:
            self.pause_elapsed_ms = min(PAUSE_OPEN_MS, self.pause_elapsed_ms + elapsed_ms)
            self.pause_hd.advance(elapsed_ms)
        if self.fade:
            self._tick_fade(elapsed_ms)
        # A native notice (the "Locked" notice, the wall link's "Exit Game?") holds the game like the pause menu does:
        # it is modal, and the scene behind it is dimmed sepia, so typing and clocks wait for its button (owner's report).
        notice_open = self.notice_stack is not None and bool(self.notice_stack.stack)
        if (self.active and not self.error and not self.menu_open and not notice_open
                and not (self.fade and self.fade['phase'] == 'out')):
            pending, remaining = self.session.pending, self.session.remaining_ms
            game = self.session.engine.word_game
            if pending is not None and pending.name == 'word_game' and game is not None and game.hd:
                remaining = game.remaining_ms if game.selected < 0 and game.duration_ms > 0 else None
            ask = self._host_prompt()
            if self.choice_closing is not None:
                # The selection is pending: the menu's own clock no longer runs out (`SHSUIMenu::tick`).
                self._tick_choice_closing(elapsed_ms)
            elif self.choice_held is not None:
                self._release_choice()          # the prompt has closed (this runs only without one)
            elif ask is not None:
                # The mini-game has not started: its clocks wait for the skip prompt. A scene transition still runs to
                # its end (fade-in included), the game held, or the prompt would wait under a black screen.
                if self.session.transitioning:
                    self._attempt(lambda: self.session.tick(elapsed_ms, pause_minigame=True))
            elif (pending is not None and pending.name in ('choice', 'word_game') and remaining is not None
                  and (pending.name == 'word_game' or self.session.choice_timer)
                  and remaining < elapsed_ms and self._hd_choice_drawn()):     # exactly 0 is still selectable
                # `SHSUIMenu::tick`: out of time with nothing selected -> `finishUI`, the same fade-out (no pressed row);
                # for the quiz this is how the game ends. The clock is held at 0 and runs out after the fade.
                if pending.name == 'choice':
                    self.session.remaining_ms = 0
                else:
                    game.remaining_ms = 0
                self.choice_closing = dict(action=pending, index=None, ms=SELECT_MS)
            else:
                self._attempt(lambda: self.session.tick(elapsed_ms))
                self._sync_cutscene()
            if self.session.pending is not None and (self.session.pending.name in ('choice', 'word_game')
                                                     or self.host_prompt is not None):
                self.choice_renderer.age_ms += elapsed_ms     # the HD panel's fade-in and its labels' fly-on
            self._tick_autoplay(elapsed_ms)
        target = 1.0 if self.panels_open else 0.0
        step = elapsed_ms / 250  # Not a recovered native duration; a reasonable slide speed.
        if self.panels_progress < target:
            self.panels_progress = min(target, self.panels_progress + step)
        elif self.panels_progress > target:
            self.panels_progress = max(target, self.panels_progress - step)
        # The window itself snaps to its new shape instantly (like a real
        # device's own rotation-driven bounds change), while the panel
        # content slides into the newly-available margin over `progress`.
        # Closing leaves the window as it is (owner's choice): the game stays
        # centred in whatever shape the player has.
        should_be_wide = self.panels_open or self.panels_progress > 0
        if should_be_wide != self._panels_wide:
            if should_be_wide:
                self._widen_for_panels()
            self._panels_wide = should_be_wide

    def toggle_panels(self):
        """Open or close the story tree and Faceplace panels (Tab, or the Side Panels switch in Options)."""
        self.panels_open = not self.panels_open
        self.side_panels.tree_follow = True
        if self.panels_open:
            # Real device confirmed: opening the side panels dismisses a
            # showing Faceplace toast, not just hides it -- that data is
            # visible in the panel already (see FaceplaceToast).
            self.session.engine.faceplace_toast = None

    def _widen_for_panels(self):
        """Real device confirmed: opening both panels turns the window's
        own 3:4 shape into 4:3, with the center game view keeping its
        original 3:4 pixel size rather than shrinking -- see
        desktop_panels.py's module docstring. Each panel is 224x768 points
        beside the 576x768 game, so they fit at full height once the window
        is 4:3 or wider: a window already that wide is left alone, and a
        narrower one is widened to 4:3 at its own height (owner's choice)."""
        if self.fixed_window:
            return
        width, height = self.window.get_size()
        needed = max(1, round(height * 4 / 3))
        if width >= needed - 1:          # a pixel of rounding either way
            return
        self.window = pygame.display.set_mode((needed, height), pygame.RESIZABLE)

    def run(self):
        from .gamepad import Gamepads
        clock = pygame.time.Clock()
        running = True
        gamepads = Gamepads.start()
        try:
            while running:
                elapsed = clock.tick(60)
                # Draw before hit-testing to keep button positions in sync after a load.
                self.render()
                for event in gamepads.events() if gamepads else pygame.event.get():
                    running = self.handle_event(event)
                    if not running:
                        break
                    # One game input per frame prevents queued double-clicks
                    # from accidentally answering the next dialogue or choice.
                    if self.screen_token != self._screen_token():
                        break
                if running:
                    self.tick(elapsed)
        finally:
            if gamepads:
                gamepads.stop()
            pygame.quit()


def play(resources, *, load_path=None, audio=True):
    session = Session.load(resources, load_path) if load_path else Session(resources)
    Desktop(session, audio=audio).run()
