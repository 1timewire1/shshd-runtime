"""This player's own screens in HD (owner, 2026-10-30): the game chooser, Bulk Import and each game's Setup, and the
message / update / busy cards over them, in the HD frame (768 x 1024 points) instead of the SD renderer's 320 x 480.

No HD art exists before a library (it comes from the player's own SHS HD app; none ships), so these are drawn in
the HD pause menu's card (desktop_pause_hd.HdPauseMenu: its measurements, colours, rows and Arial Bold) with
`AppCard` drawing the parts that card takes from the art -- the blue back button and the orange buttons -- as
shapes. They look the same on a first launch as later, on a computer and a phone. SHS HD's blue dress throughout
(the app's own look), on a dark gradient, with the kiwi above the card; the chooser shows each imported game's own
app icon (from the player's APK / IPA).

Commands are the SD screens' (`Application.command`): this only draws, and lists its buttons in frame points.
"""
from functools import lru_cache
import time

import pygame

from .app_icon import game_icon_surface, icon_surface
from .desktop_pause import ease_in_out
from .desktop_pause_hd import (BACK, BLUE, BORDER, FOOT, HEADER, LABEL_BLUE, PANEL_W, PANEL_X, ROW, ROW_BACKGROUND,
                               SEPARATOR, HdPauseMenu)
from .games import GAMES
from .hd_scale import S

FRAME = (768, 1024)
APP_SCREENS = ('games', 'bulk', 'setup')        # drawn here (the rest of the SD screens follow: docs/MAIN_MENU.md)
BACKDROP = ((28, 42, 72), (8, 12, 20))          # the dark gradient behind the cards, top to bottom
GRAY = (104, 112, 128)                          # body text and status lines
ORANGE = ((246, 168, 76), (226, 128, 40), (200, 100, 24))    # HD's orange button, top / middle / bottom
BUTTON_BLUE = ((96, 156, 246), (54, 116, 226), (34, 88, 196))
BUTTON_SIZE = (156, 58)
KIWI, KIWI_Y = 96, 28                           # the app's icon above the card
TEXT_PT, TEXT_PITCH, HEADING_PT = 26, 33, 34
GAME_ROW, GAME_ICON = 132, 84
SLIDE_MS = 400                                  # a page change slides, as the HD pause pages do
FOCUS = (255, 214, 102)                          # the keyboard / controller highlight
WINDOW_TOP = 260
SHORT_FOOT = 26                                 # a card's footer with nothing in it: a closing band
# The busy card's note (owner, 2026-10-30): an import takes minutes, longer on a phone.
IMPORT_NOTE = ('Importing can take a while: a few minutes on a computer, longer on a phone. Keep SHSHD Runtime open '
               'until it finishes.')


class AppCard(HdPauseMenu):
    """HD's card without HD's art: what HdPauseMenu takes from the SHS HD app (resource 32's buttons) drawn as
    shapes, its fonts the system's Arial Bold (else pygame's own)."""

    def __init__(self):
        super().__init__(None)
        self.pressed = None

    def raw(self, resource_id):
        return None

    def available(self):
        return True

    @lru_cache(maxsize=16)
    def font(self, points):
        return pygame.font.Font(pygame.font.match_font('arial', bold=True), round(points * self.scale))

    def gradient_box(self, box, stops, radius):
        """A rounded box whose colour runs down through `stops` (evenly spaced), at the layer's density."""
        x, y, w, h = box
        width, height = round(w * S), round(h * S)
        surface = pygame.Surface((width, height), pygame.SRCALPHA)
        for row in range(height):
            t = row / max(1, height - 1) * (len(stops) - 1)
            i = min(int(t), len(stops) - 2)
            f = t - i
            surface.fill(tuple(round(a + (b - a) * f) for a, b in zip(stops[i], stops[i + 1])) + (255,), (0, row, width, 1))
        mask = pygame.Surface((width, height), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, width, height), border_radius=round(radius * S))
        surface.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        return surface

    def button(self, layer, box, label=None, *, orange=True, lit=False, arrow=False):
        """A footer button (HD's are 156 x 58): orange, or blue with the back arrow; darker while held or lit."""
        x, y, w, h = box
        stops = ORANGE if orange else BUTTON_BLUE
        if lit:
            stops = tuple(tuple(round(c * .8) for c in color) for color in stops)
        layer.blit(self.gradient_box(box, stops, 10), (round(x * S), round(y * S)))
        self.rect(layer, tuple(round(c * .75) for c in stops[-1]), box, 10, 2)
        if arrow:
            cx, cy = x + w / 2, y + h / 2
            points = [(cx - 22, cy), (cx - 4, cy - 17), (cx - 4, cy - 7), (cx + 22, cy - 7), (cx + 22, cy + 7),
                      (cx - 4, cy + 7), (cx - 4, cy + 17)]
            pygame.draw.polygon(layer, (255, 255, 255), [(round(px * S), round(py * S)) for px, py in points])
        if label:
            points = 26
            while points > 16 and self.font(points).size(label)[0] / S > w - 20:
                points -= 2
            surface = self.font(points).render(label, True, (255, 255, 255))
            layer.blit(surface, surface.get_rect(center=(round((x + w / 2) * S), round((y + h / 2 - 1) * S))))
        return pygame.Rect(box)

    def back_button(self, layer, bottom, *, lit=False):
        lit = lit or self.pressed == ('back',)
        left, top = PANEL_X + BACK[0], bottom - BACK[1] - BUTTON_SIZE[1]
        return self.button(layer, (left, top, *BUTTON_SIZE), orange=False, lit=lit, arrow=True)

    def wrap(self, text, points, width):
        """`text` as lines of at most `width` points, broken at spaces."""
        font, lines = self.font(points), []
        for paragraph in text.split('\n'):
            line = ''
            for word in paragraph.split(' '):
                trial = f'{line} {word}' if line else word
                if line and font.size(trial)[0] / S > width:
                    lines.append(line)
                    line = word
                else:
                    line = trial
            lines.append(line)
        return lines


class AppScreens:
    """Draws APP_SCREENS and their cards into an HD canvas; `buttons` are [(rect in frame points, command)]."""

    def __init__(self):
        self.card = AppCard()
        self.buttons = []
        self.icons = {}                 # game -> (library.json's stamp, its app icon at GAME_ICON, or None)
        self.last = None                # (screen, its last canvas without cards)
        self.slide = None               # (direction, previous canvas, start ms)

    # -- the frame --------------------------------------------------------------------------------------------

    @lru_cache(maxsize=1)
    def backdrop(self):
        size = (FRAME[0] * S, FRAME[1] * S)
        surface = pygame.Surface(size)
        top, bottom = BACKDROP
        for y in range(size[1]):
            f = y / (size[1] - 1)
            surface.fill(tuple(round(a + (b - a) * f) for a, b in zip(top, bottom)), (0, y, size[0], 1))
        kiwi = icon_surface(KIWI * S)
        surface.blit(kiwi, ((size[0] - kiwi.get_width()) // 2, KIWI_Y * S))
        return surface

    def draw(self, app):
        """The screen and, over it, a busy / message / update card; returns the canvas."""
        self.card.pressed = app.pressed
        self.buttons = []
        layer = self.backdrop().copy()
        getattr(self, 'draw_' + app.screen)(app, layer)
        screen = app.screen
        now = time.monotonic() * 1000
        if self.last is not None and self.last[0] != screen:
            self.slide = (getattr(app, 'transition_direction', 1), self.last[1], now)
        self.last = (screen, layer)
        canvas = layer
        if self.slide is not None:
            direction, previous, start = self.slide
            progress = ease_in_out(min(1., (now - start) / SLIDE_MS))
            if progress >= 1:
                self.slide = None
            else:
                canvas = self.backdrop().copy()
                width = FRAME[0] * S
                offset = round(width * progress) * direction
                canvas.blit(previous, (-offset, 0))
                canvas.blit(layer, (width * direction - offset, 0))
                self.buttons = []                       # nothing takes a tap while it slides
        if app.busy or app.message or app.update_prompt is not None:
            canvas = canvas.copy() if canvas is layer else canvas
            self.buttons = []
            self.draw_card(app, canvas)
        if getattr(app, 'focus', None) == 'buttons' and self.buttons:
            rect = self.buttons[app.focus_index % len(self.buttons)][0]
            self.card.rect(canvas, FOCUS, rect.inflate(8, 8), 12, 3)
        return canvas

    # -- pieces -----------------------------------------------------------------------------------------------

    def header(self, title):
        """The card's header height: taller for a title that wraps ("Surviving High School"), as HD's lists do."""
        return HEADER + 40 if len(self.card.title_lines(title)) > 1 else HEADER

    def card_frame(self, layer, top, title, height, foot):
        """The card at `top`: its header, `height` body points of page background, then a footer `foot` high (a
        short closing band when nothing sits in it); returns (body top, card bottom)."""
        header = self.header(title)
        bottom = top + header + height + foot
        body = self.card.panel(layer, top, bottom, title, header=header)
        self.card.rect(layer, self.card.see_through(ROW_BACKGROUND), (PANEL_X + BORDER, body, PANEL_W - 2 * BORDER, height))
        self.card.rect(layer, SEPARATOR, (PANEL_X + BORDER, body, PANEL_W - 2 * BORDER, 1))
        if foot == FOOT:
            self.card.rect(layer, SEPARATOR, (PANEL_X + BORDER, bottom - FOOT, PANEL_W - 2 * BORDER, 1))
        return body, bottom

    def page(self, layer, title, height, *, back=True):
        """A card of `height` body points under `title`, below the kiwi; returns (body top, card bottom)."""
        foot = FOOT if back else SHORT_FOOT
        total = self.header(title) + height + foot
        top = max(KIWI_Y + KIWI + 20, (FRAME[1] + KIWI_Y + KIWI - total) / 2)
        body, bottom = self.card_frame(layer, top, title, height, foot)
        if back:
            self.buttons.append((self.card.back_button(layer, bottom), ('back',)))
        return body, bottom

    def text(self, layer, text, y, *, points=TEXT_PT, color=GRAY, center=False, width=PANEL_W - 70):
        """Wrapped text from `y`; returns the y after it."""
        for line in self.card.wrap(text, points, width):
            x = 384 if center else PANEL_X + 35
            self.card.text(layer, line, x, y, points, color, center=center)
            y += TEXT_PITCH * points / TEXT_PT
        return y

    def text_height(self, text, points=TEXT_PT, width=PANEL_W - 70):
        return len(self.card.wrap(text, points, width)) * TEXT_PITCH * points / TEXT_PT

    def action(self, layer, top, label, command, index):
        """An action row (HD's Data Management rows): the whole row is the button."""
        lit = self.card.pressed == command
        self.card.row(layer, top, label, background=self.card.row_color(index), lit=lit)
        rect = pygame.Rect(PANEL_X + BORDER, top, PANEL_W - 2 * BORDER, ROW)
        self.chevron(layer, rect)
        self.buttons.append((rect, command))
        return top + ROW

    def chevron(self, layer, rect):
        x, y = rect.right - 34, rect.centery
        points = [(x - 7, y - 12), (x + 5, y), (x - 7, y + 12)]
        pygame.draw.lines(layer, LABEL_BLUE, False, [(round(px * S), round(py * S)) for px, py in points], 3 * S)

    def icon(self, app, key):
        """A game's own app icon at GAME_ICON points (from its library), or None before it is imported."""
        path = app.library_path(key) / 'library.json'
        try:
            stamp = path.stat().st_mtime_ns
        except OSError:
            return None
        cached = self.icons.get(key)
        if cached is None or cached[0] != stamp:
            image = None
            try:
                from .content import ContentLibrary
                with ContentLibrary(path.parent) as library:
                    image = game_icon_surface(library)
            except Exception:                           # an unreadable library still lists its game, iconless
                image = None
            if image is not None:
                size = round(GAME_ICON * S)
                image = pygame.transform.smoothscale(image.convert_alpha(), (size, size))
                mask = pygame.Surface((size, size), pygame.SRCALPHA)
                pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, size, size), border_radius=round(18 * S))
                image.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            cached = self.icons[key] = (stamp, image)
        return cached[1]

    # -- screens ----------------------------------------------------------------------------------------------

    def draw_games(self, app, layer):
        card = self.card
        note = 'Each game keeps its own episodes, saves and library.'
        height = 70 + GAME_ROW * len(GAMES) + 16 + self.text_height(note) + 16 + 2 * ROW
        body, _ = self.page(layer, 'SHSHD Runtime', height, back=False)
        card.text(layer, 'Choose a game', 384, body + 18, HEADING_PT, BLUE, center=True)
        y = body + 70
        for index, (key, game) in enumerate(GAMES.items()):
            command = ('choose_game', key)
            ready = (app.library_path(key) / 'library.json').is_file()
            card.rows_body(layer, y, GAME_ROW, card.row_color(index), lit=card.pressed == command)
            icon = self.icon(app, key) if ready else None
            left = PANEL_X + 30
            if icon is not None:
                layer.blit(icon, (round(left * S), round((y + (GAME_ROW - GAME_ICON) / 2) * S)))
            else:
                box = (left, y + (GAME_ROW - GAME_ICON) / 2, GAME_ICON, GAME_ICON)
                card.rect(layer, (222, 226, 234), box, 18)
                cx, cy = left + GAME_ICON / 2, box[1] + GAME_ICON / 2
                card.rect(layer, LABEL_BLUE, (cx - 18, cy - 3, 36, 6), 3)
                card.rect(layer, LABEL_BLUE, (cx - 3, cy - 18, 6, 36), 3)
            x = left + GAME_ICON + 26
            card.text(layer, game.TITLE, x, y + 30, 32, BLUE)
            card.text(layer, 'Open your library' if ready else 'Import your game files to play', x, y + 76, 22, GRAY)
            rect = pygame.Rect(PANEL_X + BORDER, y, PANEL_W - 2 * BORDER, GAME_ROW)
            self.chevron(layer, rect)
            self.buttons.append((rect, command))
            y += GAME_ROW
        y = self.text(layer, note, y + 16, points=22, center=True) + 16
        for index, (label, command) in enumerate((('Bulk Import', ('bulk',)), ('Options', ('options',)))):
            y = self.action(layer, y, label, command, index)

    def draw_bulk(self, app, layer):
        intro = ('Choose the one ZIP or RAR file that holds your game files: the SHS APK, the SHS HD and Cause of '
                 'Death IPAs, the font, and the episode folders.')
        how = ('Choose it below.' if app.file_picker else 'Drag it here, or choose it below.') + \
            ' Back leads to each game\'s own setup.'
        extra = '' if app.file_picker else 'Or put it in the import folder beside the app before starting it.'
        height = 76 + self.text_height(intro) + 18 + self.text_height(how) + (
            18 + self.text_height(extra, 22) if extra else 0) + 26 + ROW
        body, _ = self.page(layer, 'Bulk Import', height)
        self.card.text(layer, 'Bring your games', PANEL_X + 35, body + 22, HEADING_PT, BLUE)
        y = self.text(layer, intro, body + 76) + 18
        y = self.text(layer, how, y)
        if extra:
            y = self.text(layer, extra, y + 18, points=22)
        self.action(layer, y + 26, 'Choose File', ('browse', 'bulk'), 0)

    def draw_setup(self, app, layer):
        game = GAMES[app.selected_game]
        intro = f'Choose your {game.SOURCES}. It includes the base assets and bundled episodes.'
        later = ('You can add EXP files or ZIP/RAR archives afterward.' if app.file_picker else
                 'Add EXP files, ZIP/RAR archives or folders afterward: drag them here, or browse.')
        hd = ' Add your HD (iPad) IPA alongside the APK too, if you have one, for HD art.' \
            if app.selected_game == 'shs' else ''
        height = 76 + self.text_height(intro) + 18 + self.text_height(later + hd) + 26 + 2 * ROW
        body, _ = self.page(layer, game.TITLE, height)
        self.card.text(layer, 'Bring your game', PANEL_X + 35, body + 22, HEADING_PT, BLUE)
        y = self.text(layer, intro, body + 76) + 18
        y = self.text(layer, later + hd, y) + 26
        y = self.action(layer, y, 'Choose Game Files', ('browse', 'apk'), 0)
        self.action(layer, y, 'Open Library', ('browse', 'library'), 1)

    # -- cards over a screen -----------------------------------------------------------------------------------

    def window(self, layer, title, text, labels, commands, *, note=None, spinner=False):
        """A centred window: `title`, `text` (and a gray `note`), then orange buttons in a row; dims what is under."""
        dim = pygame.Surface(layer.get_size(), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 120))
        layer.blit(dim, (0, 0))
        card = self.card
        height = 30 + self.text_height(text, 28) + (16 + self.text_height(note, 22) if note else 0) + (60 if spinner else 0) + 20
        foot = FOOT if labels else SHORT_FOOT
        top = max(WINDOW_TOP, (FRAME[1] - (self.header(title) + height + foot)) / 2)
        body, bottom = self.card_frame(layer, top, title, height, foot)
        y = self.text(layer, text, body + 30, points=28, color=BLUE, center=True)
        if note:
            y = self.text(layer, note, y + 16, points=22, center=True)
        if spinner:
            phase = time.monotonic() * 2.5
            for i in range(3):
                bright = .45 + .55 * max(0., 1 - abs(((phase - i * .35) % 3) - 1))
                color = tuple(round(c * bright + 255 * (1 - bright)) for c in BLUE)
                card.rect(layer, color, (384 - 40 + i * 32 - 8, y + 22, 16, 16), 8)
        y = bottom - BACK[1] - BUTTON_SIZE[1]
        if labels:
            spread = 0 if len(labels) == 1 else (PANEL_W - 2 * 40 - BUTTON_SIZE[0])
            for index, (label, command) in enumerate(zip(labels, commands)):
                x = (384 - BUTTON_SIZE[0] / 2 if len(labels) == 1
                     else PANEL_X + 40 + spread * index / (len(labels) - 1))
                box = (x, y, *BUTTON_SIZE)
                self.buttons.append((card.button(layer, box, label, lit=card.pressed == command), command))

    def draw_card(self, app, layer):
        if app.busy:
            title = {'previews': 'Preparing episodes', 'data': getattr(app, 'job_title', '')}.get(
                app.job_kind, 'Importing content')
            line = app.progress_text if app.job_kind in ('previews', 'data') and app.progress_text else \
                'Checking and copying your files...'
            self.window(layer, title, line, (), (), note=None if app.job_kind in ('previews', 'data') else IMPORT_NOTE,
                        spinner=True)
        elif app.message:
            self.window(layer, app.game_title, app.message, ('OK',), (('dismiss',),))
        elif app.update_prompt is not None:
            from .updates import UPDATE_TITLE, update_message
            commands = (('update_no',), ('update_yes',)) if app.can_quit else (('update_no',),)
            self.window(layer, UPDATE_TITLE, update_message(app.update_prompt.version, can_quit=app.can_quit),
                        ('No', 'Yes') if app.can_quit else ('OK',), commands)
