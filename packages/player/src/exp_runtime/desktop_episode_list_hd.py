"""A scrollable text list of episodes at HD's frame size, standing in for the tile grid
(`desktop_episode_picker.py`) when Episodes On Demand is pressed -- or, grouped by release year instead of
category, when Now Airing is (`episode_picker.PickerModel`'s own `chronological` flag decides which; see
`episode_index.build_chronological_rows` and `docs/EPISODE_RELEASE_DATES.md` for where the dates come from).

Not decompiled from the HD .ipa (`SHSMTXMenu` has no such screen of its own) but built to look like the one the
standard-edition app already has (`MenuRenderer`'s "episodes" screen in `desktop_menu.py`, native to the base
APK's own asset bank, 320 x 480 points): a blue-bordered white card, a blue or orange category strip per group
(orange only for the "Mega Packs" bundle group -- sampled from the APK's own pack 16 frames 73 and 76, which
`MenuRenderer` does not yet tell apart, always drawing 76), alternating near-white/pale-cyan rows in blue text
(pack 16 frames 82/83/84, `(238,249,249)`/`(255,255,255)`/`(168,224,249)`), and a pale blue play/pause icon per
row (frames 101/96, a translucent ring and glyph, sampled and reproduced here as flat shapes -- see below for why).
The orange/blue split is native to the *category* screen specifically; grouped by year instead, no group is ever
named "Mega Packs", so every header simply draws blue -- not a separate code path, just the same rule never
matching.

Colors and layout are sampled straight from the APK's own art (`tools`-less, via `MenuRenderer.art.frame`, in a
throwaway script) rather than eyeballed from a photo, so they match exactly; the shapes themselves (the card's
border, the header strips, the row bands, the play/pause icon) are drawn as flat vectors in those exact colors
instead of the APK's own low-density bitmaps stretched to HD size, since scaling 1x Android art up to HD's frame
would look soft next to the crisp HD chrome around it -- the one deliberate departure from the source art, in
service of the same screen looking right at this size.

`HdEpisodeList` subclasses `HdEpisodePicker` and shares its `PickerModel`, its input-command shape (a tap still
resolves to `('tile', id)`, opening the tile grid's own resume popup unchanged) and its dimmed main-menu backdrop
and footer buttons; only the list's own interior is drawn differently. Every category starts expanded (the
standard app itself starts them collapsed, but this being a new addition without an established default worth
preserving, expanded reads better on a first visit); tapping a header's own strip folds or unfolds just that one.

**The card (owner's design, 2026-10-20).** With a menu card renderer (`card`: the shell's `HdPauseMenu`, or CoD's
`CodPauseMenu`), the list is drawn as the game's other menus are: no dim over the main menu, a tall card like a
Help & About text page (`desktop_pause_hd.TALL`, the title header, two lines for a long title), the solid rows
scrolling in its body, and the back button inside its footer. Without one (a test, or no shell), the free-standing
card and back button below it are drawn instead.

Every row also carries a second, smaller line under its title (`PickerModel.subtitle()`) -- native to neither
screen, so no reference to sample: the episode's own category and its researched airdate on Now Airing (whose rows
aren't grouped by category, so each one names its own), or just the airdate on Episodes On Demand (its header
already names the category). Dulled down from the title's own blue via alpha rather than a second invented color.
"""
import pygame

from .desktop_episode_picker import BACK_X, BUTTON_SIZE, BUTTON_Y, FRAME, HdEpisodePicker, S
from .desktop_main_hd import STRING_AIRING, STRING_DEMAND

PANEL_MARGIN_X = 56
PANEL_TOP = 48
PANEL_BOTTOM = BUTTON_Y - 20
PANEL_RADIUS = 22
PANEL_BORDER = 5
PANEL_FILL = (255, 255, 255)
PANEL_BORDER_COLOR = (41, 104, 221)
# `MenuRenderer.panel()` draws this exact card as `art.box(canvas, rect, 1, alpha=248)` -- one 248/255 layer, not
# fully opaque. A row or header bar paints a second, fully-opaque layer over it and so looks solid; the bare card
# behind the title (nothing drawn over it there) shows a faint bleed of whatever is behind the screen, same as
# the native card does (confirmed against the owner's own zoomed-in screenshot of the real thing).
PANEL_ALPHA = 248
TITLE_HEIGHT = 76
TITLE_POINTS = 34

HEADER_HEIGHT = 46
ROW_HEIGHT = 72
TITLE_SIZE = 19
SUBTITLE_SIZE = 13
SUBTITLE_GAP = 4
BLUE_HEADER = (41, 104, 221)
ORANGE_HEADER = (213, 138, 58)
ROW_WHITE = (255, 255, 255)
ROW_ALT = (238, 249, 249)
ROW_SELECTED = (168, 224, 249)
ROW_SEPARATOR = (222, 227, 233)
ROW_TEXT = (41, 104, 221)
# The category/airdate subtitle (this player's own addition, no native screen to sample) is the same blue as
# the title, just dulled down via alpha so it reads as a secondary line without a second colour to invent.
ROW_SUBTITLE_ALPHA = 150
ICON_SIZE = 34
ICON_RING = (60, 157, 255)
ICON_GLYPH = (10, 133, 255)


class HdEpisodeList(HdEpisodePicker):
    # Style, overridable like the tile grid's (desktop_cod_episodes.CodEpisodeList).
    TITLES = (STRING_DEMAND, STRING_AIRING)            # the card's title: by category / by airdate
    TITLE_COLOR = BORDER_COLOR = PANEL_BORDER_COLOR
    HEADER_COLOR, MEGA_HEADER_COLOR = BLUE_HEADER, ORANGE_HEADER
    ROW_COLORS, SELECTED_COLOR, SEPARATOR_COLOR = (ROW_WHITE, ROW_ALT), ROW_SELECTED, ROW_SEPARATOR
    TEXT_ROW_COLOR, LIST_FILL = ROW_TEXT, ROW_WHITE
    ICON_RING_COLOR, PLAY_COLOR, PAUSE_COLOR = ICON_RING, ICON_GLYPH, ICON_GLYPH
    RING_ALPHA, PLAY_ALPHA, PAUSE_ALPHA = 140, 220, 220

    card = None                     # the game's menu card renderer (HdPauseMenu / CodPauseMenu), set by the app

    def __init__(self, library, model, shots):
        super().__init__(library, model, shots)
        self.expanded = {row.key for row in model.rows}

    def title_text(self):
        return self.strings()[self.TITLES[1 if self.model.chronological else 0]]

    def card_layout(self):
        """(top, header, bottom) of the menu card, in frame points."""
        from .desktop_pause_hd import HEADER, TALL
        top, bottom = TALL
        header = HEADER + 40 if len(self.card.title_lines(self.title_text())) > 1 else HEADER
        return top, header, bottom

    def list_area(self):
        """The rectangle (points) the rows scroll in."""
        if self.card is not None:
            from .desktop_pause_hd import BORDER, FOOT, PANEL_W, PANEL_X
            top, header, bottom = self.card_layout()
            return pygame.Rect(PANEL_X + BORDER, top + header + 1, PANEL_W - 2 * BORDER, bottom - FOOT - top - header - 1)
        divider_y = PANEL_TOP + TITLE_HEIGHT
        return pygame.Rect(PANEL_MARGIN_X + PANEL_BORDER, divider_y + 2,
                           FRAME[0] - 2 * PANEL_MARGIN_X - 2 * PANEL_BORDER, PANEL_BOTTOM - divider_y - 2 - PANEL_RADIUS)

    # ------------------------------------------------------------ layout

    def entries(self):
        """[(top, height, row, record_or_None)] for every header and, if its row is expanded, its episodes."""
        result, y = [], 0
        for row in self.model.rows:
            result.append((y, HEADER_HEIGHT, row, None))
            y += HEADER_HEIGHT
            if row.key in self.expanded:
                for record in row.episodes:
                    result.append((y, ROW_HEIGHT, row, record))
                    y += ROW_HEIGHT
        return result, y

    def content_height(self):
        return self.entries()[1]

    def list_height(self):
        # The same rectangle `draw()` clips the rows to (`list_area`), so scrolling to `max_scroll_y()` always shows
        # the last row whole.
        return self.list_area().height

    def max_scroll_y(self):
        return max(0, self.content_height() - self.list_height())

    def clamp(self):
        self.scroll_y = max(0, min(self.max_scroll_y(), self.scroll_y))

    def row_at(self, point):
        return None            # no per-row horizontal scroll in a flat list; every drag is vertical

    def reveal(self, record_id):
        for top, height, _row, record in self.entries()[0]:
            if record is not None and record['id'] == record_id:
                if top < self.scroll_y:
                    self.scroll_y = top
                elif top + height > self.scroll_y + self.list_height():
                    self.scroll_y = top + height - self.list_height()
                self.clamp()
                return

    # ------------------------------------------------------------ input

    def pointer_up(self, point):
        command = super().pointer_up(point)
        if command is not None and command[0] == 'toggle':
            self.expanded.symmetric_difference_update({command[1]})
            self.clamp()
            return None
        return command

    def key(self, key):
        if self.alert:
            return ('dismiss',) if key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE) else None
        if self.popup:
            return self.popup_key(key)
        if key == self.INFO_KEY:
            return self.info_key()
        if key not in (pygame.K_UP, pygame.K_DOWN, pygame.K_RETURN, pygame.K_SPACE):
            return None
        episodes = [record for row in self.model.rows if row.key in self.expanded for record in row.episodes]
        if not episodes:
            return None
        ids = {record['id'] for record in episodes}
        if not self.keyboard or self.selected not in ids:
            self.keyboard = True
            if self.selected not in ids:
                self.selected = episodes[0]['id']
            self.reveal(self.selected)
            return None
        if key in (pygame.K_RETURN, pygame.K_SPACE):
            return ('tile', self.selected)
        index = next(i for i, record in enumerate(episodes) if record['id'] == self.selected)
        index = max(0, min(len(episodes) - 1, index + (1 if key == pygame.K_DOWN else -1)))
        self.selected = episodes[index]['id']
        self.reveal(self.selected)
        return None

    # ------------------------------------------------------------ drawing

    def draw_icon(self, layer, cx, cy, saved):
        """The pale blue play/pause icon a row carries instead of a preview (frames 101/96 of the APK's own
        pack 16, reproduced as flat shapes in their sampled colors -- see the module docstring)."""
        size = ICON_SIZE * S
        surface = pygame.Surface((size, size), pygame.SRCALPHA)
        center = (size / 2, size / 2)
        radius = ICON_SIZE / 2 * S
        pygame.draw.circle(surface, (*self.ICON_RING_COLOR, self.RING_ALPHA), center, radius)
        pygame.draw.circle(surface, (255, 255, 255, 235), center, radius - 4 * S)
        if saved:
            for dx in (-5, 5):
                bar = pygame.Rect(0, 0, 4 * S, 14 * S)
                bar.center = (center[0] + dx * S, center[1])
                pygame.draw.rect(surface, (*self.PAUSE_COLOR, self.PAUSE_ALPHA), bar, border_radius=2 * S)
        else:
            points = [(center[0] - 5 * S, center[1] - 8 * S), (center[0] - 5 * S, center[1] + 8 * S),
                      (center[0] + 8 * S, center[1])]
            pygame.draw.polygon(surface, (*self.PLAY_COLOR, self.PLAY_ALPHA), points)
        layer.blit(surface, (round(cx * S - size / 2), round(cy * S - size / 2)))

    def draw_standard_mark(self, layer, x, y):
        """A small "SD" tag on episodes that come from the standard (non-HD) release; this player's own addition,
        restyled from the tile grid's dark plate to sit on this screen's white rows."""
        width, height = 32, 18
        plate = pygame.Surface((width * S, height * S), pygame.SRCALPHA)
        pygame.draw.rect(plate, (*PANEL_BORDER_COLOR, 30), plate.get_rect(), border_radius=6 * S)
        pygame.draw.rect(plate, (*PANEL_BORDER_COLOR, 200), plate.get_rect(), max(1, S), border_radius=6 * S)
        text = self.font(11).render('SD', True, PANEL_BORDER_COLOR)
        plate.blit(text, text.get_rect(center=plate.get_rect().center))
        layer.blit(plate, (x * S, y * S))

    def draw_header(self, layer, row, rect):
        # `episode_index.build_rows()` title-cases every row's own label (`MEGA PACKS` -> `Mega Packs`) before
        # storing it, but `PickerModel.mega_label` keeps the raw string it was passed -- an exact `==` here never
        # matched, so every header, including Mega Packs itself, always drew blue (`build_rows()`'s own sort key
        # already compares case-insensitively for the same reason; this needs to as well).
        color = (self.MEGA_HEADER_COLOR if row.title.casefold() == self.model.mega_label.casefold()
                 else self.HEADER_COLOR)
        pygame.draw.rect(layer, color, (rect.x * S, rect.y * S, rect.width * S, rect.height * S))
        cx, cy = rect.x + 22, rect.centery
        points = ([(cx - 5, cy - 3), (cx + 5, cy - 3), (cx, cy + 4)] if row.key in self.expanded
                  else [(cx - 4, cy - 5), (cx - 4, cy + 5), (cx + 5, cy)])
        pygame.draw.polygon(layer, (255, 255, 255), [(round(px * S), round(py * S)) for px, py in points])
        self.text(layer, row.title.upper(), 16, rect.x, rect.y + (rect.height - 20) / 2, color=(255, 255, 255),
                 width=rect.width, outline=False)
        count = str(len(row.episodes))
        width = self.measure(count, 14)
        self.text(layer, count, 14, rect.right - 16 - width, rect.y + (rect.height - 18) / 2,
                  color=(255, 255, 255), outline=False)
        self.hits.append((rect, ('toggle', row.key)))

    def draw_row(self, layer, record, rect, alternate):
        selected = self.keyboard and record['id'] == self.selected
        color = self.SELECTED_COLOR if selected else self.ROW_COLORS[0 if alternate else 1]
        pygame.draw.rect(layer, color, (rect.x * S, rect.y * S, rect.width * S, rect.height * S))
        pygame.draw.line(layer, self.SEPARATOR_COLOR, (rect.x * S, (rect.bottom - 1) * S),
                         (rect.right * S, (rect.bottom - 1) * S), max(1, S))
        right = rect.right - 16
        icon_cx = right - ICON_SIZE / 2
        self.draw_icon(layer, icon_cx, rect.centery, record['id'] in self.saved)
        right = icon_cx - ICON_SIZE / 2 - 10
        info = None
        if self.model.has_info(record):
            # The info button (this fork), left of the play / pause icon.
            info = pygame.Rect(0, 0, ICON_SIZE, ICON_SIZE)
            info.center = (round(right - ICON_SIZE / 2), rect.centery)
            self.draw_info_icon(layer, right - ICON_SIZE / 2, rect.centery, ICON_SIZE)
            right -= ICON_SIZE + 10
        if self.model.is_standard(record):
            right -= 32
            self.draw_standard_mark(layer, right, rect.y + (rect.height - 18) / 2)
            right -= 8
        text_width = right - rect.x - 18
        title = self.wrap(self.model.label(record), TITLE_SIZE, text_width, 1)[0]
        subtitle = self.model.subtitle(record)
        title_height = self.font(TITLE_SIZE).get_height() / S
        if subtitle:
            subtitle_height = self.font(SUBTITLE_SIZE).get_height() / S
            title_y = rect.y + (rect.height - (title_height + SUBTITLE_GAP + subtitle_height)) / 2
            self.text(layer, title, TITLE_SIZE, rect.x + 18, title_y, color=self.TEXT_ROW_COLOR, outline=False)
            subtitle = self.wrap(subtitle, SUBTITLE_SIZE, text_width, 1)[0]
            self.text(layer, subtitle, SUBTITLE_SIZE, rect.x + 18, title_y + title_height + SUBTITLE_GAP,
                     color=self.TEXT_ROW_COLOR, outline=False, alpha=ROW_SUBTITLE_ALPHA)
        else:
            self.text(layer, title, TITLE_SIZE, rect.x + 18, rect.y + (rect.height - title_height) / 2,
                     color=self.TEXT_ROW_COLOR, outline=False)
        self.hits.append((rect, ('tile', record['id'])))
        if info is not None:                  # after the row's own hit, so it wins
            self.hits.append((info.inflate(8, 8), ('info', record['id'])))

    def draw_panel(self, layer, panel):
        """The card's own translucent base layer (`PANEL_ALPHA`); rows and headers paint fully opaque over it."""
        surface = pygame.Surface((panel.width * S, panel.height * S), pygame.SRCALPHA)
        box = surface.get_rect()
        pygame.draw.rect(surface, (*PANEL_FILL, PANEL_ALPHA), box, border_radius=PANEL_RADIUS * S)
        pygame.draw.rect(surface, (*self.BORDER_COLOR, PANEL_ALPHA), box, PANEL_BORDER * S, border_radius=PANEL_RADIUS * S)
        layer.blit(surface, (panel.x * S, panel.y * S))

    def draw(self, *, backdrop=True):
        """Render into the 2x canvas; returns it. `self.hits` lists the clickable rectangles (points). With
        `backdrop` off it renders onto a transparent layer instead (`begin_layer`)."""
        self.clamp()
        layer = self.begin_layer(backdrop, dim=self.card is None)
        self.hits = []
        strings = self.strings()
        title = self.title_text()
        if self.card is not None:
            # The game's own menu card (see the module docstring): its header, its footer rule and its back button.
            from .desktop_pause_hd import BORDER, FOOT, PANEL_W, PANEL_X
            top, header, bottom = self.card_layout()
            self.card.panel(layer, top, bottom, title, header=header)
            for rule in (top + header, bottom - FOOT):
                self.card.rect(layer, self.card.SEPARATOR_COLOR, (PANEL_X + BORDER, rule, PANEL_W - 2 * BORDER, 1))
        else:
            panel = pygame.Rect(PANEL_MARGIN_X, PANEL_TOP, FRAME[0] - 2 * PANEL_MARGIN_X, PANEL_BOTTOM - PANEL_TOP)
            self.draw_panel(layer, panel)
            self.text(layer, title, TITLE_POINTS, panel.x, panel.y + (TITLE_HEIGHT - TITLE_POINTS - 6) / 2,
                     color=self.TITLE_COLOR, width=panel.width, outline=False)
            divider_y = panel.y + TITLE_HEIGHT
            pygame.draw.line(layer, self.BORDER_COLOR, ((panel.x + 10) * S, divider_y * S),
                             ((panel.right - 10) * S, divider_y * S), max(1, S))
        # Inset clear of the card's rounded corners; the height is `list_height()`'s, so the scroll clamp matches.
        list_rect = self.list_area()
        clip = pygame.Rect(list_rect.x * S, list_rect.y * S, list_rect.width * S, list_rect.height * S)
        layer.set_clip(clip)
        pygame.draw.rect(layer, self.LIST_FILL, clip)
        alternate = True
        for top, height, row, record in self.entries()[0]:
            y = list_rect.y + top - self.scroll_y
            if y + height <= list_rect.y or y >= list_rect.bottom:
                if record is not None:
                    alternate = not alternate
                continue
            rect = pygame.Rect(list_rect.x, y, list_rect.width, height)
            if record is None:
                self.draw_header(layer, row, rect)
            else:
                self.draw_row(layer, record, rect, alternate)
                alternate = not alternate
        layer.set_clip(None)
        dim = bool(self.popup or self.alert)
        if self.card is not None:
            back = self.card.back_button(layer, bottom)
            restore = pygame.Rect(0, 0, *BUTTON_SIZE)
            restore.bottomright = (PANEL_X + PANEL_W - 14, bottom - 13)
        else:
            back = pygame.Rect(BACK_X, BUTTON_Y, *BUTTON_SIZE)
            restore = pygame.Rect(FRAME[0] - BACK_X - BUTTON_SIZE[0], BUTTON_Y, *BUTTON_SIZE)
            self.draw_button(layer, back.x, back.y, pressed=self.pressed == ('back',))
        if self.show_restore:
            self.draw_button(layer, restore.x, restore.y, orange=True, label=strings[self.RESTORE],
                             pressed=self.pressed == ('restore',))
        if not dim:
            self.hits.append((back, ('back',)))
            if self.show_restore:
                self.hits.append((restore, ('restore',)))
        self.draw_overlay(layer, strings)
        return layer
