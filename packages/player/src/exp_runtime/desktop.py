"""Shared gameplay frontend; all story decisions remain in the KiWi runtime."""
from collections import OrderedDict
from io import BytesIO
import logging
import os

os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
from . import graphics as pygame

from .app_icon import icon_surface
from .content import ContentError
from .audio import music_cue
from .games import GAMES, game_id
from .desktop_text import BitmapTextRenderer
from .desktop_dialogue import DialogueRenderer
from .desktop_choice import ChoiceRenderer
from .desktop_pause import PAUSE_OPEN_MS, PauseRenderer, draw_pause_gear
from .desktop_picker import CharacterPickerRenderer
from .desktop_loading import LoadingRenderer
from .desktop_message import MessageRenderer
from .desktop_title import TitleRenderer
from .desktop_input import InputRenderer, INPUT_RECT
from .fonts import TextStyle
from .runtime import SaveError, Session
from .scene_badge import outline_badge_text
from .pointer import ButtonPress
from .text_input import accept_name_character, validate_name
from .ui_assets import ImagePack, Rect
from .vm import VMError


SIZE = (480, 720)
INK = (245, 241, 233)
MUTED = (183, 187, 198)
ACCENT = (247, 190, 94)
PANEL = (23, 29, 45)


class Desktop:
    def __init__(self, session: Session, *, audio: bool = True, window=None, on_main_menu=None,
                 episode_title=None, on_menu_page=None):
        pygame.display.init()
        pygame.font.init()
        if window is None:
            pygame.display.set_icon(icon_surface())
        self.window = window if window is not None else pygame.display.set_mode(SIZE, pygame.RESIZABLE)
        self.on_main_menu = on_main_menu
        self.on_menu_page = on_menu_page
        self.pause_renderer = None
        self.pause_elapsed_ms = PAUSE_OPEN_MS
        self.gear_pointer_down = False
        self.ui_sounds = {}
        self.episode_title = episode_title if episode_title is not None else session.resources.record['titles'][0]
        pygame.display.set_caption(GAMES[game_id(session.resources)].TITLE + ' — ' + self.episode_title)
        # Cocoa's default opaque surface still carries an alpha bitmask.
        # Explicit RGB avoids its incorrect blending of translucent layers.
        self.canvas = pygame.Surface(SIZE).convert(32)
        self.font = pygame.font.Font(None, 27)
        self.heading = pygame.font.Font(None, 34)
        self.small = pygame.font.Font(None, 22)
        self.session = session
        self.story_text = BitmapTextRenderer(session.resources.library)
        self.dialogue_renderer = DialogueRenderer(session.resources, self.story_text, self._image)
        self.choice_renderer = ChoiceRenderer(session.resources, self.story_text, self.dialogue_renderer)
        self.grid_renderer = self.football_renderer = None
        if game_id(session.resources) == 'shs':
            from .shs.desktop_grid import GridRenderer
            from .shs.desktop_football import FootballRenderer
            self.grid_renderer = GridRenderer(session.resources, self.story_text, self.dialogue_renderer)
            self.football_renderer = FootballRenderer(session.resources, self.story_text, self.dialogue_renderer)
        self.picker_renderer = CharacterPickerRenderer(session.resources, self.story_text, self.dialogue_renderer)
        self.loading_renderer = LoadingRenderer(session.resources, self.story_text, self.dialogue_renderer)
        self.message_renderer = MessageRenderer(session.resources, self.story_text, self.dialogue_renderer)
        self.title_renderer = TitleRenderer(session.resources, self.story_text, self.dialogue_renderer)
        self.input_renderer = InputRenderer(session.resources, self.story_text, self.dialogue_renderer)
        self.input_action = None
        self.input_error = None
        self.input_keyboard = False
        self.text_input_started = None  # Force the first sync to set SDL's state.
        self.picker_pointer_down = False
        self.press = ButtonPress()
        self.images = OrderedDict()
        self.buttons = []
        self.scroll = self.max_scroll = 0
        self.screen_token = None
        self.message = ''
        self.message_until = 0
        self.error = None
        self.music_token = None
        self.music_loaded = False
        self.music_paused = False
        self.sound_serial = session.engine.sound_serial
        self.audio = False
        self.music_enabled = self.sound_enabled = True
        self.choice_hints = False
        self.active = True
        self.menu_open = False
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

    def _sync_music(self):
        """Apply the requested cue and hold its playhead while play is inactive."""
        if not self.audio:
            return
        engine = self.session.engine
        token = (engine.music_id, engine.music_flag, self.music_enabled)
        if token != self.music_token:
            self.music_token = token
            self.music_loaded = self.music_paused = False
            try:
                pygame.mixer.music.stop()
                if engine.music_id >= 0 and self.music_enabled:
                    cue = music_cue(engine.music_id, game=game_id(self.session.resources))
                    pygame.mixer.music.load(BytesIO(self.session.resources.read_asset(cue.asset_id)))
                    # Both native iOS games pass service 80's flag to
                    # SHSSound.setLoop: (-1 repeats, 0 plays once).
                    pygame.mixer.music.play(loops=-1 if engine.music_flag else 0,
                                            start=cue.start_ms / 1000)
                    self.music_loaded = True
            except (ContentError, pygame.error) as error:
                logging.warning('Music %s cannot be played: %s', engine.music_id, error)
        paused = self.menu_open or not self.active
        if self.music_loaded and paused != self.music_paused:
            self.music_paused = paused
            try:
                if paused:
                    pygame.mixer.music.pause()
                else:
                    pygame.mixer.music.unpause()
            except pygame.error as error:
                logging.warning('Music %s cannot change pause state: %s', engine.music_id, error)

    def _sync_audio(self):
        if not self.audio:
            return
        self._sync_music()
        engine = self.session.engine
        if engine.sound_serial != self.sound_serial:
            self.sound_serial = engine.sound_serial
            if not self.sound_enabled:
                return
            try:
                for asset in engine.sound_ids or [engine.sound_id]:
                    pygame.mixer.Sound(file=BytesIO(self.session.resources.read_asset(asset))).play()
            except (ContentError, pygame.error) as error:
                logging.warning('Sound %s cannot be played: %s', engine.sound_id, error)

    def _sync_text_input(self):
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
        library = self.session.resources.library
        if not self.audio or not self.sound_enabled or not hasattr(library, 'read_asset'):
            return
        profile = GAMES[game_id(self.session.resources)]
        asset = profile.PAUSE_SOUND if opening else profile.CLICK_SOUND
        try:
            if asset not in self.ui_sounds:
                self.ui_sounds[asset] = pygame.mixer.Sound(file=BytesIO(library.read_asset(asset)))
            self.ui_sounds[asset].play()
        except (ContentError, pygame.error) as error:
            logging.debug('Pause sound %s unavailable: %s', asset, error)

    def render(self):
        self.buttons = []
        action = self.session.pending
        self._sync_text_input()
        token = self._screen_token()
        self.press.validate(self._press_token())
        self.dialogue_renderer.gear_pressed = self.press.pressed == ('menu',) and not self.menu_open
        if token != self.screen_token:
            self.screen_token, self.scroll = token, 0
        self.canvas.fill((14, 20, 32))
        details = action.details if action else {}
        if action and action.name in ('word_grid', 'football', 'character_picker', 'loading', 'message_panel', 'survey_confirmation', 'presentation', 'text_input') and not self.error:
            try:
                renderer = {'word_grid': self.grid_renderer, 'football': self.football_renderer,
                            'character_picker': self.picker_renderer, 'loading': self.loading_renderer,
                            'message_panel': self.message_renderer, 'presentation': self.title_renderer,
                            'survey_confirmation': self.message_renderer,
                            'text_input': self.input_renderer}[action.name]
                options = (dict(error=self.input_error,
                                cursor_visible=self.text_input_started and pygame.time.get_ticks() % 1000 < 500)
                           if action.name == 'text_input' else {})
                buttons = renderer.draw(self.canvas, self.session, **options)
                self.buttons = [(pygame.Rect(*(round(value * 1.5) for value in rect)), command)
                                for rect, command in buttons]
                self.scroll = self.max_scroll = 0
                self._present()
                return
            except (ContentError, pygame.error, OSError, ValueError) as error:
                self.error = str(error)
                logging.error('Panel rendering stopped: %s', error)
        if (action and action.name in ('choice', 'word_game') and not self.error
                and hasattr(self.session.resources, 'read_asset')):
            try:
                page = self.choice_renderer.page(self.session)
                self.max_scroll = page.max_scroll * 1.5
                self.scroll = min(self.scroll, self.max_scroll)
                pointer = None
                if hasattr(self, 'viewport') and self.press.origin is None and not self.menu_open:
                    x, y = pygame.mouse.get_pos()
                    if self.viewport.collidepoint(x, y):
                        pointer = ((x - self.viewport.x) * 320 / self.viewport.width,
                                   (y - self.viewport.y) * 480 / self.viewport.height)
                _, buttons = self.choice_renderer.draw(self.canvas, self.session,
                                                        scroll=self.scroll / 1.5, pointer=pointer,
                                                        pressed=self.press.pressed if not self.menu_open else None,
                                                        choice_hints=self.choice_hints)
                self.buttons = [(pygame.Rect(*(round(value * 1.5) for value in rect)), command)
                                for rect, command in buttons]
                if pygame.time.get_ticks() < self.message_until:
                    self._text(self.message, 90, 672, 375, font=self.small)
                self._present()
                return
            except (ContentError, pygame.error, OSError, ValueError) as error:
                self.error = str(error)
                logging.error('Choice rendering stopped: %s', error)
        if action and action.name == 'dialogue' and not self.error:
            try:
                self.dialogue_renderer.draw(self.canvas, self.session)
                self.scroll = self.max_scroll = 0
                draw_pause_gear(self.canvas, self.dialogue_renderer, scale=1.5)
                self.buttons = [(pygame.Rect(0, 633, 90, 87), ('menu',)),
                                (pygame.Rect(0, 0, *SIZE), ('continue',))]
                if pygame.time.get_ticks() < self.message_until:
                    self._text(self.message, 20, 701, 450, font=self.small, color=MUTED)
                self._present()
                return
            except (ContentError, pygame.error, OSError, ValueError) as error:
                self.error = str(error)
                logging.error('Dialogue rendering stopped: %s', error)
        background_id = details.get('asset_id', -1) if action and action.name == 'presentation' else self.session.engine.panel.background_id
        background = self._image(background_id)
        if background is not None:
            self.canvas.blit(pygame.transform.smoothscale(background, SIZE), (0, 0))
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
        message = self.message if pygame.time.get_ticks() < self.message_until else 'F5 save · F9 load · Esc menu'
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

    def _present(self):
        engine = self.session.engine
        if engine.scene_badge and not self.error:
            try:
                self._draw_scene_badge(engine.scene_badge)
            except (ContentError, pygame.error, OSError, ValueError) as error:
                self.error = str(error)
                logging.error('Scene label rendering stopped: %s', error)
        if self.menu_open:
            self._draw_menu()
        self._sync_audio()
        width, height = self.window.get_size()
        scale = min(width / SIZE[0], height / SIZE[1])
        scaled = pygame.transform.smoothscale(self.canvas, (max(1, int(480 * scale)), max(1, int(720 * scale))))
        self.viewport = scaled.get_rect(center=(width // 2, height // 2))
        self.window.fill((8, 12, 20))
        self.window.blit(scaled, self.viewport)
        pygame.display.flip()

    def _draw_scene_badge(self, badge):
        layer = self.dialogue_renderer.frame(204 if badge.blue else 236, 13).copy()
        icon = self._image(badge.asset_id)
        if icon is not None:
            layer.blit(icon, icon.get_rect(center=(38, 30)))  # Layout 67 node 2.
        color = (69, 107, 176) if badge.text == 'Free Time' else (223, 163, 52)
        name = 'ArialRoundedMTBold16'
        if getattr(self.story_text.font(name), 'cap_height', None) is not None:
            name = 'ArialMT14'
            region = self.session.resources.dialogue_layout().bank.rectangle(67, 3)
            text, (x, y), scale = outline_badge_text(badge.text, self.story_text.font(name), region, color)
        else:
            text = self.story_text.layout(name, badge.text, 110, TextStyle(14, 1, color))
            x, y, scale = badge.text_origin
        self.story_text.draw_layout(layer, name, text, x, y, scale=scale)
        # 200ms MoveTo from x=-width/2 to center x=100. Ad-free top inset=10.
        left = -171 + (100 + 171 / 2) * badge.elapsed_ms / 200
        self.canvas.blit(pygame.transform.smoothscale(layer, (257, 90)), (round(left * 1.5), 15))

    def _draw_menu(self):
        if self.pause_renderer is None:
            self.pause_renderer = PauseRenderer(self.session.resources.library,
                                                 self.story_text, self.dialogue_renderer)
        buttons = self.pause_renderer.draw(self.canvas, application=self.on_menu_page is not None,
                                            main_menu=self.on_main_menu is not None,
                                            pressed=self.press.pressed,
                                            elapsed_ms=self.pause_elapsed_ms)
        self.buttons = [(pygame.Rect(*(round(value * 1.5) for value in rect)), command)
                        for rect, command in buttons]
        if pygame.time.get_ticks() < self.message_until:
            self._text(self.message, 30, 640, 420, font=self.small)

    def command(self, command):
        self.press.cancel()
        self.gear_pointer_down = False
        self._sync_text_input()
        kind = command[0]
        if self.menu_open and kind in ('save', 'load'):
            self._menu_sound()
        if kind == 'menu':
            if self.menu_open:
                return
            self.picker_pointer_down = False
            if self.session.engine.word_grid:
                self.session.grid_pointer('cancel')
            self.menu_open = True
            self.pause_elapsed_ms = 0
            self._sync_music()
            self._menu_sound(opening=True)
        elif kind == 'resume':
            self.menu_open = False
            self._sync_music()
            self._menu_sound()
        elif kind == 'pause_page' and self.on_menu_page:
            self.on_menu_page(command[1])
            self._menu_sound()
        elif kind == 'main_menu' and self.on_main_menu:
            self.on_main_menu()
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
                self.session = restored
                self.error, self.music_token = None, None
                self.sound_serial = restored.engine.sound_serial
                self.menu_open = False
                self._notice('Progress loaded')
            except (SaveError, OSError) as error:
                self._notice(str(error))
        elif not self.error:
            action = self.session.pending
            if action and action.name == 'text_input' and not self.menu_open and self.active:
                if kind in ('input_dismiss', 'input_focus'):
                    self.input_error, self.input_keyboard = None, True
                elif kind == 'continue':
                    self._submit_input(action)
            if action and action.name == 'character_picker' and kind in ('choose', 'continue'):
                self._attempt(lambda: self.session.answer(command[1] if kind == 'choose' else None))
            if kind == 'choose' and action and action.name in ('choice', 'word_game'):
                self._attempt(lambda: self.session.answer(command[1]))
            elif kind == 'continue' and action and action.name in ('presentation', 'dialogue', 'message_panel', 'survey_confirmation'):
                self._attempt(self.session.answer)
            elif action and action.name == 'football' and kind in ('continue', 'choose'):
                self._attempt(lambda: self.session.answer(command[1] if kind == 'choose' else None))
        self._sync_text_input()

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
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.menu_open:
                self.command(('resume',))
                return True
            self.command(('menu',))
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
        pointer = (event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION)
                   and (event.type == pygame.MOUSEMOTION or event.button == 1))
        if self.menu_open and self.pause_elapsed_ms < PAUSE_OPEN_MS and pointer:
            self.press.cancel()
            return True
        if pointer and not self.menu_open and hasattr(self, 'viewport'):
            x = (event.pos[0] - self.viewport.x) * SIZE[0] / self.viewport.width
            y = (event.pos[1] - self.viewport.y) * SIZE[1] / self.viewport.height
            hit = (self.viewport.collidepoint(event.pos) and any(
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
                if self.picker_renderer.confirm_hit((x, y)):
                    self.command(('continue',))
                else:
                    index = self.session.engine.character_picker.hit((x, y))
                    if index is not None:
                        self.command(('choose', index))
            return True
        if (action and action.name == 'football' and not self.menu_open and not self.error
                and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1):
            x = (event.pos[0] - self.viewport.x) * 320 / self.viewport.width
            y = (event.pos[1] - self.viewport.y) * 480 / self.viewport.height
            if 0 <= x <= 320 and 0 <= y <= 480:
                self._attempt(lambda: self.session.answer(self.football_renderer.hit((x, y))))
            return True
        if (action and action.name == 'word_grid' and not self.menu_open and not self.error
                and event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION)
                and (event.type == pygame.MOUSEMOTION or event.button == 1)):
            x = (event.pos[0] - self.viewport.x) * 320 / self.viewport.width
            y = (event.pos[1] - self.viewport.y) * 480 / self.viewport.height
            phase = {pygame.MOUSEBUTTONDOWN: 'down', pygame.MOUSEMOTION: 'move',
                     pygame.MOUSEBUTTONUP: 'up'}[event.type]
            index = self.grid_renderer.hit((x, y), self.session.engine.word_grid)
            self._attempt(lambda: self.session.grid_pointer(phase, index))
            return True
        if self.menu_open and event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_F5, pygame.K_F9):
                self.command(('save' if event.key == pygame.K_F5 else 'load',))
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
            command = self.press.update(phase, hit, self._press_token())
            if command is not None:
                self.command(command)
            return True
        if event.type == pygame.KEYDOWN:
            self.press.cancel()
            if event.key in (pygame.K_F5, pygame.K_F9):
                self.command(('save' if event.key == pygame.K_F5 else 'load',))
            elif event.key == pygame.K_RETURN or (event.key == pygame.K_SPACE and action and action.name != 'text_input'):
                self.command(('continue',))
            elif action and action.name == 'character_picker' and pygame.K_1 <= event.key <= pygame.K_5:
                if event.key - pygame.K_1 < len(self.session.engine.character_picker.characters):
                    self.command(('choose', event.key - pygame.K_1))
            elif action and action.name in ('choice', 'word_game', 'football') and pygame.K_1 <= event.key <= pygame.K_9:
                index = event.key - pygame.K_1
                if action.name == 'football' or (action.name == 'word_game' and index < 4) or (action.name == 'choice'
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
            if self.viewport.collidepoint(event.pos):
                x = (event.pos[0] - self.viewport.x) * SIZE[0] / self.viewport.width
                y = (event.pos[1] - self.viewport.y) * SIZE[1] / self.viewport.height
                for rect, command in self.buttons:
                    if rect.collidepoint(x, y):
                        self.command(command)
                        break
        self._sync_text_input()
        return True

    def tick(self, elapsed_ms):
        if self.active and self.menu_open:
            self.pause_elapsed_ms = min(PAUSE_OPEN_MS, self.pause_elapsed_ms + elapsed_ms)
        if self.active and not self.error and not self.menu_open:
            self._attempt(lambda: self.session.tick(elapsed_ms))

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
