"""Shared gameplay frontend; all story decisions remain in the KiWi runtime."""
from collections import OrderedDict
from dataclasses import astuple
from io import BytesIO
from copy import deepcopy
import logging
import os
import re
from types import SimpleNamespace
import webbrowser

os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
from . import graphics as pygame

from .app_icon import set_window_icon
from .content import ContentError
from .audio import music_cue
from .games import GAMES, game_id
from .desktop_text import BitmapTextRenderer
from .desktop_dialogue import DialogueRenderer
from .desktop_choice import ChoiceRenderer
from .desktop_pause import PAUSE_OPEN_MS, PauseRenderer, pause_scale
try:
    # SHS HD's football and word grid draw with SHS's own layout helpers (exp_runtime.shs), which a CoD-only install
    # lacks; CoD never plays either (tools/test_packages.py's cod-player case).
    from .desktop_football_hd import HdFootballRenderer
    from .desktop_word_hd import HdWordRenderer
except ImportError:
    HdFootballRenderer = HdWordRenderer = None
from .location_pan import LocationPan
from .desktop_message_hd import HdMessageRenderer
from . import frame_log, scene_fade
from .desktop_pause_hd import HdPauseMenu, KEYS_ACTIVATE, focus_step
from .desktop_hd_menu import HdMenuWindows
from .desktop_badge_hd import HdSceneBadge
from .ad_intro import has_links, play_option
from .hd_choice import SELECT_MS, TRANSITION_MS, panel_alpha
from .hd_ui import FRAME as HD_FRAME, S as HD_S
from .menu_engine import MenuEngineData, MenuEngineError, MenuStack
from .desktop_picker import CharacterPickerRenderer, CodCharacterPickerRenderer, HdCharacterPickerRenderer
from .desktop_loading import HdLoadingRenderer, LoadingRenderer
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


# Links a browser can open (an App Store link's itms:// becomes its web page in _offer_link).
WEB_LINK = re.compile(r'(https?|itms(-apps)?)://', re.I)


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


class Desktop:
    story_layer = None
    # An HD choice being closed after a pick: {'action', 'index', 'ms'}. The row shows its pressed colour, the panel
    # fades out (hd_choice.SELECT_MS, TRANSITION_MS), then the choice is answered.
    choice_closing = None
    # An HD choice kept faded out after its pick opened a prompt (a script link, _answer): {'action', 'index'}. The scene
    # under the prompt is the one without the panel; once the prompt has closed, the choice fades in again with its
    # whole entrance, unless the pick went on.
    choice_held = None
    # The option the arrow keys have selected. Enter or Space picks it. Mouse clears it.
    choice_focus = None
    # The same for the Android pause menu's rows (HD's pause menu keeps its own, `pause_hd.state.focus`).
    menu_focus = None
    # A narrator-style choice of this player's own over the pending screen (`_open_prompt`): "Ask to skip mini-games"
    # before a football game or word grid (Win, Lose or Play), and whether to skip the High School Story ad intros.
    # {'action', 'session', 'options', 'resolve'} while it is up (`session` stands in for the real one when drawing it).
    # `minigame_played` is the game the player chose to play and `ad_asked` the ad choice already asked about.
    skip_minigames = False
    skip_ad_intros = False
    # Autoplay Dialogue (this player's option): dialogue, title cards and message panels take no taps; once their text
    # is out they wait AUTOPLAY_WAIT_MS (a title card AUTOPLAY_TITLE_WAIT_MS) and advance by themselves (owner's
    # choice, 2026-10-21: longer than the Continue pill's 250 ms expansion, to be safe).
    autoplay = False
    AUTOPLAY_WAIT_MS = 750
    AUTOPLAY_TITLE_WAIT_MS = 1500
    autoplay_ms = 0
    _disable_choice_timer = False
    _untimed = None                 # (action, _UntimedChoice) for the pending timed choice
    hd_backdrop = True              # CoD: SHS HD's collage beside the frame (the player's "SHS HD Backdrop" switch)
    host_prompt = None
    minigame_played = None
    ad_asked = None
    panel_alpha = None          # the HD menu view's alpha for this frame (None: drawn whole)
    panel_overlay = None        # the HD timer layers for this frame (outside the view's fades)
    edge_layer = None
    fade = None
    # Warping through the story tree: `warp_unlocked` is the app's option (the iOS app keeps it locked until Football
    # Season has been completed once); touches on the tree are ignored until `warp_lockout` (a warp locks them for a second).
    warp_unlocked = True
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

    @property
    def session(self):
        return self._session

    @session.setter
    def session(self, session):
        if self.names is not None:
            session.share_names(self.names)
        session.choice_click = False        # the tap plays it (`_menu_sound`), not the later answer
        session.choice_timer = not self._disable_choice_timer
        self._session = session

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
                 episode_title=None, on_menu_page=None, names=None, vibration_enabled=False):
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
        self.pause_hd = HdPauseMenu(session.resources)
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
        self.message_renderer = MessageRenderer(session.resources, self.story_text, self.dialogue_renderer)
        self.message_hd = HdMessageRenderer(session.resources, self.dialogue_renderer)
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
        self.fade = None                     # the player's own fade from black (a warp; scene_fade.py)
        self.music_token = None
        self.music_stream = MusicStream()
        self.music_was_enabled = True
        # The menu's song in the pause menu (see `_sync_pause_song`): its Sound, the ticks its fade-out began, and
        # whether the Music switch has asked for it (SHSEngine +0xb22c).
        self.pause_song = self.pause_song_fade = None
        self.pause_song_wanted = False
        self.sound_serial = session.engine.sound_serial
        self.vibration_serial = session.engine.vibration_serial
        self.audio = False
        self.music_enabled = self.sound_enabled = True
        # Off by default (the buzz is an opt-in addition, PR #10); set here so the first script's requests obey it.
        self.vibration_enabled = vibration_enabled
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
        if not count or not self.vibration_enabled or not self.active or self.menu_open:
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
        if self.music_enabled != self.music_was_enabled:
            self.music_was_enabled = self.music_enabled
            if not self.music_enabled:
                stream.disable(now)                  # setMusicEnabled(false): stopMusic(-1, true)
        token = (engine.music_id, engine.music_flag, engine.music_serial)
        if token != self.music_token:
            if self.music_token is None:
                stream.reset()                       # a new or reloaded session starts its own cue
            self.music_token = token
            if engine.music_id >= 0:
                if self.music_enabled:               # playMusic ignores requests while Music is off
                    stream.play(engine.music_id, engine.music_flag, self._open_cue, now, held=self.menu_open)
            else:
                stream.stop(engine.music_stop_ms, now)
        stream.update(now, enabled=self.music_enabled, menu_open=self.menu_open,
                      paused=not self.active or engine.music_paused, held_back=self.pause_song is not None)
        self._sync_pause_song(now)

    def _sync_pause_song(self, now):
        """The menu's song in the pause menu. Switching Music on sets `SHSEngine` +0xb22c, which
        `doSoundManagerTransition` (SHS HD 0002a830, CoD 00025c60) turns into the menu's song (MENU_MUSIC, once) as
        soon as the paused episode's music has gone quiet. Switching Music off again fades it over 1000 ms; Resume
        fades it too, and the episode's song comes back only after it has stopped (`restoreGameAudio`). The Main Menu
        row hands a song still playing to the main menu (`take_pause_song`)."""
        song = self.pause_song
        if song is not None and song.get_num_channels() == 0:
            song = self.pause_song = self.pause_song_fade = None             # it played out
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
        if self.pause_song_fade is None and (not self.menu_open or not self.music_enabled):
            self.pause_song_fade = now                                      # Resume, or Music off: stop(false)
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
        if not (self.vibration_enabled and self.sound_enabled) or pygame.supports_vibration():
            return                          # (a device that vibrates does so instead: `_sync_vibration`)
        try:
            if self.buzz_sound is None:
                self.buzz_sound = pygame.mixer.Sound(file=BytesIO(buzz_wav()))
            self.buzz_sound.set_volume(self.sound_volume)
            self.buzz_sound.play()
        except pygame.error as error:
            logging.warning('Vibration buzz cannot be played: %s', error)

    def _play_sounds(self, assets):
        if not self.sound_enabled:
            return
        try:
            for asset in assets:
                sound = pygame.mixer.Sound(file=BytesIO(self.session.resources.read_asset(asset)))
                sound.set_volume(self.sound_volume)
                sound.play()
        except (ContentError, pygame.error) as error:
            logging.warning('Sound %s cannot be played: %s', assets, error)

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

    def _host_prompt(self):
        """The host prompt over the pending screen, or None; the mini-game prompt opens the first time a football game,
        word grid or word quiz (service 71, both games) is seen."""
        action = self.session.pending
        prompt = self.host_prompt
        if prompt is not None and prompt['action'] is not action:
            prompt = self.host_prompt = None
        if (prompt is None and self.skip_minigames and action is not None
                and action.name in ('football', 'word_grid', 'word_game')
                and self.minigame_played is not action and not self.error):
            prompt = self._open_prompt(action, 'Skip this mini-game?', self._minigame_summary(action), self.SKIP_OPTIONS,
                                       lambda index: self._resolve_minigame(action, index))
        return prompt

    def _open_prompt(self, action, title, text, options, resolve):
        """A narrator-style choice (no character: the gold theme, no portrait) over `action`; `resolve(index)` runs
        once the pick has closed it."""
        details = dict(title=title, text=text, options=list(options), values=list(range(len(options))),
                       enabled=[True] * len(options), timeout_ms=0, timeout_result=0, character_id=-1, portrait_mode=0)
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

    def _minigame_summary(self, action):
        """What the game about to start holds, for the skip prompt: football's half and starting score, the grid's
        target and its puzzles' words."""
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
            return (f'Word quiz. Pick the right word, again and again, for {seconds} seconds. Win scores the most a '
                    f'quiz can; Lose scores nothing.')
        game = engine.word_grid
        words = []
        for problem in game.problems:
            for word in problem.words:
                if word.upper() not in words:
                    words.append(word.upper())
        shown = ', '.join(words[:8]) + (' ...' if len(words) > 8 else '')
        seconds = round(game.remaining_ms / 1000)
        return f'Word game. Score {game.target} in {seconds} seconds. Words: {shown}.'

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
        if not ready:
            self.autoplay_ms = 0
            return
        self.autoplay_ms += elapsed_ms
        wait = self.AUTOPLAY_TITLE_WAIT_MS if action.name == 'presentation' else self.AUTOPLAY_WAIT_MS
        if self.autoplay_ms >= wait:
            self.autoplay_ms = 0
            self._answer()

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
            shade.set_alpha(round(255 * amount))
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

    def render(self):
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
        self.edge_layer = None
        self.pending_background = None
        self.pending_background_alpha = 255
        details = action.details if action else {}
        ask = self._host_prompt()
        closed = self._ui_closed(action)
        if action and not ask and not closed and action.name in ('word_grid', 'football', 'character_picker', 'loading', 'download_poll', 'message_panel', 'survey_confirmation', 'presentation', 'text_input') and not self.error:
            try:
                # A dict of values here would build every branch eagerly -- each an `available()` gate that
                # reads and (pre-caching) re-decompressed an HD resource -- for the one the dict ends up
                # indexing out; a dict of zero-argument callables evaluates only the selected action's own.
                message = lambda: self.message_hd if self.message_hd.available() else self.message_renderer
                selectors = {
                    'word_grid': self._word_grid, 'football': self._football, 'character_picker': self._picker,
                    'loading': lambda: self.loading_hd if self.loading_hd.available() else self.loading_renderer,
                    'download_poll': lambda: self.loading_hd if self.loading_hd.available() else self.loading_renderer,
                    'message_panel': message, 'survey_confirmation': message,
                    'presentation': self._title_renderer,
                    'text_input': lambda: self.input_renderer,
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
                else:
                    buttons = renderer.draw(None if action.name == 'text_input' else self.canvas,
                                            self.session, **options)
                if action.name == 'text_input' or getattr(renderer, 'hd_layer', False):
                    self.story_layer = renderer.canvas
                self.pending_background = getattr(renderer, 'pending_background', None)
                self.pending_background_origin = getattr(renderer, 'pending_background_origin', (160, 180))
                self.pending_background_alpha = getattr(renderer, 'pending_background_alpha', 255)
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
                and hasattr(self.session.resources, 'read_asset')):
            try:
                page = self.choice_renderer.page(source)
                self.max_scroll = page.max_scroll * 1.5
                self.scroll = min(self.scroll, self.max_scroll)
                pointer = None
                if hasattr(self, 'viewport') and self.press.origin is None and not self.menu_open:
                    x, y = pygame.mouse.get_pos()
                    if self.viewport.collidepoint(x, y):
                        pointer = ((x - self.viewport.x) * 320 / self.viewport.width,
                                   (y - self.viewport.y) * 480 / self.viewport.height)
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
                    if closing is None or closing['ms'] < SELECT_MS:
                        self.panel_overlay = self.choice_renderer.overlay
                if closing is not None:
                    buttons = [button for button in buttons if button[1] == ('menu',)]
                self.hint_discount_ms += self.choice_renderer.take_hint_ms()
                self.story_layer = self.choice_renderer.wide
                self.edge_layer = self.dialogue_renderer.bottom_bar_layer(self.choice_renderer.footer_text,
                                                                          self.dialogue_renderer.gear_pressed)
                self.pending_background = self.choice_renderer.pending_background
                self.pending_background_origin = self.choice_renderer.pending_background_origin
                self.buttons = [(pygame.Rect(*(round(value * 1.5) for value in rect)), command)
                                for rect, command in buttons]
                if pygame.time.get_ticks() < self.message_until:
                    self._text(self.message, 90, 672, 375, font=self.small)
                self._present()
                return
            except (ContentError, pygame.error, OSError, ValueError) as error:
                self.error = str(error)
                logging.error('Choice rendering stopped: %s', error)
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
                self.edge_layer = self.dialogue_renderer.bottom_bar_layer(self.dialogue_renderer.footer_text,
                                                                          self.dialogue_renderer.gear_pressed)
                self.pending_background = self.dialogue_renderer.pending_background
                self.pending_background_origin = self.dialogue_renderer.pending_background_origin
                self.scroll = self.max_scroll = 0
                # The gear is flush with the frame's left edge, 48 canvas pixels (32 units) outside the UI column.
                self.buttons = [(pygame.Rect(-48, 633, 150, 87), ('menu',)),
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
            # `return_to_menu()` the moment `episode_exited` is set, instead of `Desktop.render()`), so the only
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
        """HD's word game art when an HD app bundle is imported, else the Android renderer."""
        return self.word_hd if self.word_hd is not None and self.word_hd.available() else self.grid_renderer

    _backdrop = (None, None)        # (window size, surface) of the last window backdrop

    def _window_backdrop(self, size):
        """While the "SHS HD Backdrop" switch is on, SHS HD's faded main-menu collage around the frame
        (hd_ui.window_backdrop), else None (the dark fill)."""
        key = size, self.hd_backdrop
        if self._backdrop[0] != key:
            surface = None
            try:
                collage = self.backdrop_collage() if self.hd_backdrop else None
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
        scale = min(width / FRAME_UNITS[0], height / FRAME_UNITS[1])
        frame = pygame.Rect(0, 0, max(1, round(FRAME_UNITS[0] * scale)), max(1, round(FRAME_UNITS[1] * scale)))
        frame.center = (width // 2, height // 2)
        target_size = (max(1, round(320 * scale)), max(1, round(480 * scale)))
        with frame_log.section('present'):
            scaled = pygame.transform.smoothscale(self.canvas, target_size)
        alpha, overlay = self.panel_alpha, self.panel_overlay
        self.panel_alpha = self.panel_overlay = None
        if alpha is not None and alpha < 1:
            scaled.set_alpha(round(255 * alpha))
        # The column also sits 5.5 units above the frame's bottom edge (box
        # top and bottom lines both measured 21.5 px lower than HD's at
        # 3.9 px per unit; the right border matched to a pixel).
        self.viewport = pygame.Rect(frame.x + round(32 * scale),
                                    frame.bottom - target_size[1] - round(UI_BOTTOM_INSET * scale), *target_size)
        self.bg_viewport = frame
        bg_size = frame.size
        with frame_log.section('backdrop'):
            backdrop = self._window_backdrop(self.window.get_size())
            if backdrop is not None:
                self.window.blit(backdrop, (0, 0))
            else:
                self.window.fill((8, 12, 20))
            self._draw_background_layer(bg_size, self.bg_viewport)
        if self.story_layer is not None:
            # Drawn at HD density and resampled once, straight to the window.
            layer = self.story_layer
            if layer.get_width() * FRAME_UNITS[1] == layer.get_height() * FRAME_UNITS[0]:
                # The whole 384x512-unit frame (HD's football).
                area = self.bg_viewport
            elif layer.get_width() * 480 == layer.get_height() * FRAME_UNITS[0]:
                # A frame-wide layer (its column plus HD's 32-unit side margins).
                area = pygame.Rect(self.bg_viewport.x, self.viewport.y, self.bg_viewport.width, self.viewport.height)
            else:
                area = self.viewport
            with frame_log.section('present'):
                layer = pygame.transform.smoothscale(layer, area.size)
            if alpha is not None and alpha < 1:
                layer.set_alpha(round(255 * alpha))
            self.window.blit(layer, area)
        if self.edge_layer is not None and not self.capture:
            # HD's bottom bar and gear run to the edges of its frame.
            edge_height = round(self.viewport.height * 72 / 480)
            self.window.blit(pygame.transform.smoothscale(self.edge_layer, (self.bg_viewport.width, edge_height)),
                             (self.bg_viewport.x, self.bg_viewport.bottom - edge_height))
        self.window.blit(scaled, self.viewport)
        if overlay is not None:
            self.window.blit(pygame.transform.smoothscale(overlay, target_size), self.viewport)
        if hd_alert is not None:
            # HD's alert is a strip of the frame, cut by the frame's own edge.
            self.window.blit(pygame.transform.smoothscale(hd_alert, frame.size), frame)
        if hd_badge is not None:
            self.window.blit(pygame.transform.smoothscale(hd_badge, frame.size), frame)
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
        if (self.panels_open or self.panels_progress > 0) and not self.error:
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
        self._draw_transition()
        if self.fade:
            self._draw_fade()
        if not self.capture:
            with frame_log.section('flip'):
                pygame.display.flip()

    def _draw_background_layer(self, target_size, viewport):
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
        self.window.fill((0, 0, 0), viewport)
        background = self.pending_background
        if background is None:
            return
        if self.pending_background_origin == 'cover':
            # Cause of Death's chapter card: its iPhone screen shows the whole picture fitted to the 320x480 column;
            # here it is scaled evenly until it covers the 3:4 frame, centred where the column's centre is (owner:
            # no dead space, as SHS fills the frame -- without the stretch SHS HD's own card applies).
            bw, bh = background.get_size()
            centre = 26.5 + 240                                  # the column's centre, frame units from the top
            k = min(bw / 384, bh / (2 * centre), bh / (2 * (512 - centre)))   # art pixels per frame unit
            crop = pygame.Rect(round(bw / 2 - 192 * k), round(bh / 2 - centre * k), round(384 * k), round(512 * k))
            crop = crop.clip(background.get_rect())
            key = (id(background), tuple(crop), target_size)
            cached_key, cached_surface = self._background_layer_cache or (None, None)
            if key != cached_key:
                cached_surface = pygame.transform.smoothscale(background.subsurface(crop), target_size)
                self._background_layer_cache = (key, cached_surface)
            cached_surface.set_alpha(self.pending_background_alpha if self.pending_background_alpha < 255 else None)
            self.window.blit(cached_surface, viewport)
            return
        if self.pending_background_origin is None:
            key = (id(background), None, target_size)
        else:
            cx, cy = self.pending_background_origin
            # In HD's frame the art sits 48 units further right and 20.5
            # higher than its Android focal point implies: feature-matched
            # against two HD photos of the same hall (the portrait one and the
            # landscape IMG_0069 both gave dx=-188, dy=80 px at 1500x2000,
            # i.e. this build's image lay that far left and down). Measured
            # for the dialogue scene; assumed constant for other screens.
            bw, bh = background.get_size()
            bg_scale = bw / 480
            # Cause of Death draws its scenes the way SHS draws its SD backgrounds in the HD frame (owner's choice,
            # 2026-10-14): the 480x720 art panned with the speaker so the frame is always covered. Its own iPhone
            # screen shows the art 1 px per point from the plain focal point (IMG_0483), which leaves the 3:4
            # frame's margins past the art's edge.
            if cy == 180 and (self.dialogue_renderer.has_hd_bundle() or self.dialogue_renderer.game_id() == 'cod'):
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
            crop = window.clip(background.get_rect())
            if crop.width <= 0 or crop.height <= 0:
                return
            # Where the window runs past the art's edge (Cause of Death's art is exactly its screen wide, so the
            # frame's side margins can reach past it), the art keeps its scale and the rest stays uncovered: it
            # used to be stretched across the whole frame.
            sx, sy = target_size[0] / window.width, target_size[1] / window.height
            viewport = pygame.Rect(viewport.x + round((crop.x - window.x) * sx),
                                   viewport.y + round((crop.y - window.y) * sy),
                                   round(crop.width * sx), round(crop.height * sy))
            target_size = viewport.size
            key = (id(background), tuple(crop), target_size)
        # The location pan (above) is the only thing that can change this layer between two frames of the same
        # scene -- and it settles after 0.25s, same as a static background the rest of the time -- so a frame
        # whose key matches the last one reuses that scaled surface instead of smoothscaling the same pixels
        # again. Alpha is set fresh every time regardless (never left over from a cache hit): a mid-transition
        # frame's lowered alpha must not stick to a later, fully-opaque one reusing the same cached surface.
        cached_key, cached_surface = self._background_layer_cache or (None, None)
        if key == cached_key:
            scaled_bg = cached_surface
        else:
            source = background if self.pending_background_origin is None else background.subsurface(crop)
            scaled_bg = pygame.transform.smoothscale(source, target_size)
            self._background_layer_cache = (key, scaled_bg)
        scaled_bg.set_alpha(self.pending_background_alpha if self.pending_background_alpha < 255 else None)
        self.window.blit(scaled_bg, viewport)

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
        layer.set_alpha(toast.alpha)
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
                                            elapsed_ms=self.pause_elapsed_ms)
        self.buttons = [(pygame.Rect(*(round(value * 1.5) for value in rect)), command)
                        for rect, command in buttons]
        if pygame.time.get_ticks() < self.message_until:
            self._text(self.message, 30, 640, 420, font=self.small)

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

    def _draw_hd_pause(self, frame):
        """HD's pause menu: the frame dimmed sepia with UIKit panels over it (desktop_pause_hd.py)."""
        area = frame.clip(self.window.get_rect())
        if area.width <= 0 or area.height <= 0:
            return
        self._draw_tinted(area)
        settings = self._pause_settings()
        message = self.message if pygame.time.get_ticks() < self.message_until else ''
        scale = pause_scale(self.pause_elapsed_ms)
        size = tuple(max(1, round(length * scale)) for length in frame.size)
        # At rest (fully zoomed, no page sliding) the card only changes with what it shows, so the drawn and scaled
        # card is kept until then (~15 ms a frame at 1080p).
        resting = self.pause_elapsed_ms >= PAUSE_OPEN_MS and self.pause_hd.slide is None
        key = (repr(settings), message, astuple(self.pause_hd.state), getattr(self.pause_hd, 'pressed', None), size)
        if resting and self._pause_card is not None and self._pause_card[0] == key:
            card, self.pause_buttons = self._pause_card[1:]
        else:
            layer, self.pause_buttons = self.pause_hd.layout(settings, message=message)
            card = pygame.transform.smoothscale(layer, size)
            self._pause_card = (key, card, self.pause_buttons) if resting else None
        self.window.blit(card, pygame.Rect((0, 0), size).move(frame.centerx - size[0] // 2, frame.centery - size[1] // 2))

    def _pause_settings(self):
        # No Skip Ad Intros here: it only acts as an episode starts, so the main menu's Options alone lists it (owner).
        return dict(vibration=self.vibration_enabled, music=self.music_enabled, sound=self.sound_enabled,
                    music_volume=self.music_volume,
                    sound_volume=self.sound_volume, side_panels=self.panels_open, choice_hints=self.choice_hints,
                    skip_minigames=self.skip_minigames,
                    autoplay=self.autoplay, disable_choice_timer=self.disable_choice_timer,
                    **({'hd_backdrop': self.hd_backdrop} if self.backdrop_switch() else {}))

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
        self.notice_windows.draw(layer, current, pressed=self.notice_pressed)
        scale = pause_scale(self.notice_ms)
        size = tuple(max(1, round(length * scale)) for length in area.size)
        self.window.blit(pygame.transform.smoothscale(layer, size),
                         pygame.Rect((0, 0), size).move(area.centerx - size[0] // 2, area.centery - size[1] // 2))

    def _pause_point(self, position):
        frame = self.bg_viewport
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
        if self.menu_open:
            return
        self.pause_hd.reset()
        self.menu_focus = None
        self.picker_pointer_down = False
        if self.session.engine.word_grid:
            self.session.grid_pointer('cancel')
        self.menu_open = True
        self.session.engine.faceplace_toast = None
        self.pause_elapsed_ms = 0
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
        if kind == 'pause_link':
            # A link in a help page's text (an About page's override): behind the game's "Exit Game?" prompt, as the
            # main menu's copy of the page already does (application_hd.HdShell.activate).
            self._offer_link(command[1])
            return
        if kind == 'pause_toggle':
            if command[1] == 'music':
                self.music_enabled = not self.music_enabled
                self.pause_song_wanted = self.music_enabled                 # SHSEngine::setMusicEnabled(on, true)
                self._sync_music()
            elif command[1] == 'side_panels':
                self.toggle_panels()
                return
            elif command[1] == 'choice_hints':
                self.choice_hints = not self.choice_hints
            elif command[1] == 'skip_minigames':
                self.skip_minigames = not self.skip_minigames
            elif command[1] == 'skip_ad_intros':
                self.skip_ad_intros = not self.skip_ad_intros
            elif command[1] == 'autoplay':
                self.autoplay, self.autoplay_ms = not self.autoplay, 0
            elif command[1] == 'disable_choice_timer':
                self.disable_choice_timer = not self.disable_choice_timer
            elif command[1] == 'hd_backdrop':
                self.hd_backdrop = not self.hd_backdrop
            elif command[1] == 'vibration':
                self.vibration_enabled = not self.vibration_enabled
                if self.vibration_enabled and pygame.supports_vibration():
                    pygame.vibrate()        # SHSEngine::setVibrationEnabled vibrates once when it is switched on
                elif self.vibration_enabled and self.audio:
                    self._buzz()
            else:
                self.sound_enabled = not self.sound_enabled
                if self.sound_enabled:
                    # `SHSEngine::setSoundEnabled(true, true)`: the switch's own sound, other effects stopped.
                    self._ui_sound('SOUND_ON_SOUND', stop_others=True)
            if self.on_settings:
                self.on_settings()
            return
        if self.menu_open and kind in ('save', 'load'):
            self._menu_sound()
        if kind == 'menu':
            self.open_pause()
        elif kind == 'resume':
            self.menu_open = False
            self._sync_music()
            self._menu_sound()
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
                    if self._hd_choice_drawn():
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
                                                                     'survey_confirmation'):
                if not self.autoplay:           # Autoplay advances these itself (`_tick_autoplay`)
                    self._answer()
            elif action and action.name == 'football' and kind in ('continue', 'choose'):
                self._attempt(lambda: self.session.answer(command[1] if kind == 'choose' else None))
        self._sync_text_input()

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
            else:
                self._notice_pointer(event)
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
                command == ('menu',) and rect.collidepoint(x, y) for rect, command in self.buttons))
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
            y = (event.pos[1] - self.viewport.y) * 480 / self.viewport.height
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
        if (action and action.name == 'football' and not self.menu_open and not self.error and not asking
                and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1):
            if self._football().__class__ is HdFootballRenderer:
                frame = self.bg_viewport
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
                frame = self.bg_viewport
                x = (event.pos[0] - frame.x) * 768 / frame.width
                y = (event.pos[1] - frame.y) * 1024 / frame.height
                gear = 0 <= x < 150 and 880 <= y <= 1024
            else:
                x = (event.pos[0] - self.viewport.x) * 320 / self.viewport.width
                y = (event.pos[1] - self.viewport.y) * 480 / self.viewport.height
                gear = 0 <= x < 60 and 422 <= y < 480
            if event.type == pygame.MOUSEBUTTONDOWN and gear:
                self.command(('menu',))
            else:
                phase = {pygame.MOUSEBUTTONDOWN: 'down', pygame.MOUSEMOTION: 'move',
                         pygame.MOUSEBUTTONUP: 'up'}[event.type]
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
            hit = (next((command for rect, command in self.buttons if rect.collidepoint(x, y)), None)
                   if self.viewport.collidepoint(event.pos) else None)
            phase = {pygame.MOUSEBUTTONDOWN: 'down', pygame.MOUSEBUTTONUP: 'up',
                     pygame.MOUSEMOTION: 'move'}[event.type]
            if event.type == pygame.MOUSEMOTION:
                self.choice_focus = self.menu_focus = None
            command = self.press.update(phase, hit, self._press_token())
            if command is not None:
                self.command(command)
            return True
        if event.type == pygame.KEYDOWN:
            self.press.cancel()
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
            elif action and action.name == 'character_picker' and pygame.K_1 <= event.key <= pygame.K_5:
                picker = self.session.engine.character_picker
                # Keys wait for a running swap to end (CharacterPicker.moving): mashed keys left the rings misplaced.
                if event.key - pygame.K_1 < len(picker.characters) and not picker.moving:
                    self.command(('choose', event.key - pygame.K_1))
            elif action and (action.name in ('choice', 'word_game', 'football') or asking) and pygame.K_1 <= event.key <= pygame.K_9:
                index = event.key - pygame.K_1
                if asking:
                    if index < len(self.host_prompt['options']):
                        self.command(('choose', index))
                elif action.name == 'football' or (action.name == 'word_game' and index < 4) or (action.name == 'choice'
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
                    if rect.collidepoint(x, y):
                        self.command(command)
                        break
        self._sync_text_input()
        return True

    # HD's gear (pack 155 frame 58, 74 x 72 units) sits flush with the frame's left and bottom edges, partly in the
    # 32-unit margin outside the UI column, so its touch area is tested in frame units, not column units.
    GEAR_FRAME_RECT = (-3.5, 441, 74, 71)

    def _gear_hit(self, position):
        if not any(command == ('menu',) for _, command in self.buttons) or self.menu_open:
            return False
        try:
            if self.dialogue_renderer.hd_bar() is None:
                return False
        except (AttributeError, ValueError, pygame.error):
            return False
        frame = self.bg_viewport
        unit = frame.width / FRAME_UNITS[0]
        x, y = (position[0] - frame.x) / unit, (position[1] - frame.y) / unit
        left, top, width, height = self.GEAR_FRAME_RECT
        return left <= x <= left + width and top <= y <= top + height

    # -- warping through the story tree (SHSDTView touchesEnded / SHSDTTitleOverView / SHSDTHelpOverView) --------

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
            self.tree_drag = [event.pos, (panels.tree_scroll, panels.tree_scroll_x), False]
            return True
        elif event.type == pygame.MOUSEMOTION and self.tree_drag:
            (x, y), (down, across) = event.pos, (self.tree_drag[0], self.tree_drag[1])
            if max(abs(x - down[0]), abs(y - down[1])) > 6:
                self.tree_drag[2] = True
            if self.tree_drag[2]:
                panels.tree_scroll = across[0] - (y - down[1]) / s
                panels.tree_scroll_x = across[1] - (x - down[0]) / s
                panels.tree_follow = False
                return True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.tree_drag:
            dragged, self.tree_drag = self.tree_drag[2], None
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
            panels.scroll_wall(-event.y * 40 / s)
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and area.collidepoint(event.pos):
            self.wall_drag = [event.pos, panels.wall_scroll, False]
            return True
        if event.type == pygame.MOUSEMOTION and self.wall_drag:
            down = self.wall_drag[0]
            if max(abs(event.pos[0] - down[0]), abs(event.pos[1] - down[1])) > 6:
                self.wall_drag[2] = True
            if self.wall_drag[2]:
                panels.wall_scroll = self.wall_drag[1] - (event.pos[1] - down[1]) / s
                panels.wall_scrolled_at = pygame.time.get_ticks()
                return True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.wall_drag:
            dragged, self.wall_drag = self.wall_drag[2], None
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

    def _warp(self, node):
        """`SHSDTView warpToNode:animatedScroll:`: load the scene's saved game and fade the game back in from black; the
        side panels stay open and the tree scrolls to the scene."""
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
        now = pygame.time.get_ticks()
        self.fade = dict(kind=6, phase='in', since=now, frozen=None)
        self.warp_lockout = now + 1000

    def snapshot(self, size=(432, 580)):
        """The game's frame as a saved-game screenshot for the episode picker (the pause menu left out)."""
        opened, self.menu_open = self.menu_open, False
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
        frame = self.bg_viewport.clip(self.window.get_rect())
        return pygame.transform.smoothscale(self.window.subsurface(frame).copy(), size)

    def tick(self, elapsed_ms):
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
        if self.active and self.menu_open:
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
                pass                            # the mini-game has not started: its clocks wait for the skip prompt
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
        width, height = self.window.get_size()
        needed = max(1, round(height * 4 / 3))
        if width >= needed - 1:          # a pixel of rounding either way
            return
        self.window = pygame.display.set_mode((needed, height), pygame.RESIZABLE)

    def run(self):
        clock = pygame.time.Clock()
        running = True
        try:
            while running:
                elapsed = clock.tick(60)
                # Draw before hit-testing to keep button positions in sync after a load.
                self.render()
                for event in pygame.event.get():
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
            pygame.quit()


def play(resources, *, load_path=None, audio=True):
    session = Session.load(resources, load_path) if load_path else Session(resources)
    Desktop(session, audio=audio).run()
