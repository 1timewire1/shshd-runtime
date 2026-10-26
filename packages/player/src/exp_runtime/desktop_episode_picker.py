"""The iOS HD episode picker (`SHSMTXMenu`): rows of episode tiles over the main-menu photo.

Decompiled (`reloadContents_VT`, `addVTRow:withWidth:addDivider:`, `MTXEpisodeViewController`, `MTXEpisodeButton`,
`showResumePopup:`) and measured on the owner's photos (`reference/screenshots/main menu`, IMG_0154 and IMG_0244).
Everything is in frame points (768 x 1024); the canvas is drawn at twice that.

* Rows are horizontal scroll views 320 points tall, the first at y 0, one per catalog category, stacked in a
  vertical scroll view; the tiles are 216 x 290 at x = 20 + 236 i, y = row + 15, each with a drop shadow, its
  caption drawn over the top-left corner (ArialRoundedMTBold 24, white, dark outline and shadow), and a 4-point
  divider (`VT_divider.png`) at the row's bottom.
* An episode with a save is cut in two by a zigzag: the top is its preview under mask resource 14 (216 x 160), the
  bottom its saved-game screenshot under mask 13 (216 x 136, bottom-aligned), the screenshot sitting 50 points below
  the tile's top; the masks hide where they are 255. Either half opens the resume popup.
* The popup dims the screen and centers `popupBackground.png` (502 x 444): "New Game" over the preview at card
  (22, 44), "Continue" over the screenshot at (260, 44), and a blue back button at (22, 359). It and the alerts zoom
  in from the centre as the HD menus' windows do (`pause_scale`, 400 ms) while the dim fades in: this fork's choice
  (owner, 2026-10-21), not measured on the iPad.
* The bottom bar is a blue arrow button (layout 70/71 with pack 32 frame 12) at (97, 965) and an orange "Restore"
  button (layout 72/73) mirrored at 768 - 97 - 156; Restore shows the app's "Restore Not Necessary" message.
* The backdrop is the main menu's: wood (resource 6), photo (9), ribbon (8) and title (7), art 640 wide shown at
  768 (x1.2).

Not verified against a photo: the backdrop's exact placement, the sepia "not owned" and download-badge tile states
(nothing here is unowned), scroll inertia, and the standard-edition marker, which is this player's own addition.

Two further additions, neither measured against a reference photo: the backdrop is dimmed behind the rows (the app
appears to darken the main menu it is drawn over, going by the owner's own screenshots, but the exact shade is a
guess -- `BACKDROP_DIM_ALPHA`); and each row's catalog category is captioned in the otherwise-empty gutter above its
tiles, which is this player's own addition with no native equivalent to measure.
"""
from functools import lru_cache
from io import BytesIO

import pygame

from .desktop_pause import PAUSE_OPEN_MS, pause_scale
from .graphics import faded
from .episode_picker import EpisodeInfo
from .episode_thumbnails import BUNDLE
from .hd_layout import HdLayouts
from .hd_ui import HdUi

S = 2
FRAME = (768, 1024)
ROW_HEIGHT = 320
TILE = (216, 290)
TILE_X, TILE_STEP, TILE_Y = 20, 236, 15
# HD resources 14 (216 x 160) and 13 (216 x 136) are image masks, CGImageMask style: a sample of 0 shows the picture and
# 255 hides it, and the hidden triangles are a zigzag along the bottom of 14 and the top of 13. The top half is the
# preview under 14, the bottom half the screenshot under 13, bottom-aligned; the black tile behind shows through
# where the two zigzags leave a gap.
TOP_MASK, BOTTOM_MASK = 14, 13
BOTTOM_MASK_TOP = TILE[1] - 136
SHOT_OFFSET = 50                            # the saved screenshot sits this far below the tile's top (measured)
BUTTON_SIZE = (156, 58)
BUTTON_Y, BACK_X = 965, 97
CARD = (502, 444)
CARD_TOP_LEFT = ((FRAME[0] - CARD[0]) // 2, (FRAME[1] - CARD[1]) // 2)
BLUE = (41, 104, 221)
SCALE_ART = FRAME[0] / 640                  # the backdrop art is 640 wide
STRING_NEW_GAME, STRING_BACK, STRING_CONTINUE, STRING_RESTORE = 19, 22, 26, 197
STRING_RESTORE_TITLE, STRING_RESTORE_TEXT = 191, 192
DRAG_THRESHOLD = 10
SCROLL_STEP = 80
BACKDROP_DIM_ALPHA = 90       # unverified guess (see module docstring); the popup/alert dim to 140 on top of this
DIM_ALPHA = 140
ROW_LABEL_POINTS = 14         # unverified (see module docstring); drawn in the row's empty top gutter, TILE_Y tall
# The episode info button and card (this fork; no native screen). In the lists it is the play / pause icon with an
# "i"; on a tile it is the SD mark's dark plate (owner, 2026-10-15) holding an "i" in a ring, where that mark sits.
# The card is the alert's, its text fitted between the title and the OK button.
INFO_ICON = 34
INFO_PLATE = (34, 26)         # the SD plate's width; a little taller, for the ring
MARK_COLOR = (235, 238, 245)  # the SD mark's text
MARK_TINT = .35               # a legacy game's tag colour, this much toward white to read on the dark plate
INFO_TITLE_POINTS, INFO_META_POINTS = 26, 18
INFO_TEXT_POINTS = (20, 19, 18, 17, 16, 15)


def rgba_from_alpha(alpha, size):
    data = bytearray(4 * len(alpha))
    data[0::4] = data[1::4] = data[2::4] = b'\xff' * len(alpha)
    data[3::4] = alpha
    return pygame.image.frombytes(bytes(data), size, 'RGBA').convert_alpha()


class HdEpisodePicker(HdUi):
    hd_layer = True
    # Style, overridable by a game that keeps this screen in its own dress (desktop_cod_episodes.py).
    TEXT_COLOR = BLUE                                   # the popup's labels and the alert's text
    FOCUS_TEXT_COLOR = (213, 138, 58)                   # the keyboard's choice in the popup: SHS HD's orange accent
    # The list's play / pause icon colours (desktop_episode_list_hd.py), shared by the info button.
    ICON_RING_COLOR, PLAY_COLOR, PAUSE_COLOR = (60, 157, 255), (10, 133, 255), (10, 133, 255)
    RING_ALPHA, PLAY_ALPHA, PAUSE_ALPHA = 140, 220, 220
    NEW_GAME, CONTINUE, RESTORE = STRING_NEW_GAME, STRING_CONTINUE, STRING_RESTORE
    RESTORE_TITLE, RESTORE_TEXT = STRING_RESTORE_TITLE, STRING_RESTORE_TEXT

    def __init__(self, library, model, shots):
        """`shots(record)` gives a record's saved-game screenshot (432 x 580) or None."""
        super().__init__(library)
        self.model, self.shots = model, shots
        self.canvas = pygame.Surface((FRAME[0] * S, FRAME[1] * S)).convert()
        self.scroll_y = 0
        self.row_x = {}
        self.selected = None
        self.keyboard = False
        self.popup = None            # the record whose resume popup is open
        self.popup_focus = None      # the popup's highlighted command, while the keyboard drives it
        self.alert = None            # (title, text)
        self.hits = []
        self.pressed = None
        self.saved = set()
        self.drag = None
        self.show_restore = True     # only the Play/Resume picker has the Restore button

    # ------------------------------------------------------------ availability and resources

    @staticmethod
    def available(library):
        if library is None or library.hd_ipa is None:
            return False
        try:
            layouts = HdLayouts(library)
            return (layouts.bank() is not None and library.hd_raw_resource(6) is not None
                    and library.hd_raw_resource(TOP_MASK) is not None)
        except Exception:
            return False

    def raw(self, resource_id):
        """An HD app resource's bytes (the tile masks)."""
        return self.library.hd_raw_resource(resource_id)

    def restore_alert(self):
        """Restore's answer: "Restore Not Necessary" (title, text)."""
        strings = self.strings()
        return strings[self.RESTORE_TITLE], strings[self.RESTORE_TEXT]

    @lru_cache(maxsize=2)
    def mask(self, resource_id):
        from .ui_assets import ImagePack
        image = ImagePack.parse(self.raw(resource_id)).images[0]
        surface = rgba_from_alpha(bytes(255 - value for value in image.pixels), (image.width, image.height))
        return pygame.transform.smoothscale(surface, (image.width * S, image.height * S))

    # ------------------------------------------------------------ navigation state

    def content_height(self):
        return len(self.model.rows) * ROW_HEIGHT

    def max_scroll_y(self):
        return max(0, self.content_height() - FRAME[1] + (FRAME[1] - BUTTON_Y))

    def max_scroll_x(self, row):
        return max(0, TILE_X + len(row.episodes) * TILE_STEP - FRAME[0])

    def clamp(self):
        self.scroll_y = max(0, min(self.max_scroll_y(), self.scroll_y))
        for index, row in enumerate(self.model.rows):
            if row.key in self.row_x:
                self.row_x[row.key] = max(0, min(self.max_scroll_x(row), self.row_x[row.key]))

    def reveal(self, record_id):
        """Scroll so a record's tile is fully on screen."""
        place = self.model.position.get(record_id)
        if place is None:
            return
        row_index, column = place
        row = self.model.rows[row_index]
        top = row_index * ROW_HEIGHT
        if top < self.scroll_y:
            self.scroll_y = top
        elif top + ROW_HEIGHT > self.scroll_y + BUTTON_Y:
            self.scroll_y = top + ROW_HEIGHT - BUTTON_Y
        offset = self.row_x.get(row.key, 0)
        left = TILE_X + column * TILE_STEP
        if left < offset + TILE_X:
            offset = left - TILE_X
        elif left + TILE[0] > offset + FRAME[0] - TILE_X:
            offset = left + TILE[0] - FRAME[0] + TILE_X
        self.row_x[row.key] = offset
        self.clamp()

    def enter(self, selected):
        self.popup = self.alert = self.drag = self.pressed = None
        self.selected = selected if selected in self.model.position else None
        self.keyboard = False
        if self.selected:
            self.reveal(self.selected)

    def tile_at(self, point):
        for rect, command in self.hits:
            if command[0] == 'tile' and rect.collidepoint(point):
                return command[1]
        return None

    # ------------------------------------------------------------ input

    def command_at(self, point):
        for rect, command in reversed(self.hits):
            if rect.collidepoint(point):
                return command
        return None

    def pointer_down(self, point):
        command = self.command_at(point)
        self.pressed = command
        self.drag = dict(start=point, last=point, mode=None, row=self.row_at(point))
        self.keyboard = False
        self.popup_focus = None

    def row_at(self, point):
        index = int((point[1] + self.scroll_y) // ROW_HEIGHT)
        return self.model.rows[index] if 0 <= index < len(self.model.rows) else None

    def pointer_move(self, point):
        drag = self.drag
        if drag is None or self.popup or self.alert:
            return
        dx, dy = point[0] - drag['start'][0], point[1] - drag['start'][1]
        if drag['mode'] is None and max(abs(dx), abs(dy)) > DRAG_THRESHOLD:
            drag['mode'] = 'x' if abs(dx) > abs(dy) and drag['row'] is not None else 'y'
            self.pressed = None
        if drag['mode'] == 'x':
            self.row_x[drag['row'].key] = self.row_x.get(drag['row'].key, 0) - (point[0] - drag['last'][0])
        elif drag['mode'] == 'y':
            self.scroll_y -= point[1] - drag['last'][1]
        drag['last'] = point
        self.clamp()

    def pointer_up(self, point):
        """The command a click ends in, or None (a drag, or a release somewhere else)."""
        drag, pressed = self.drag, self.pressed
        self.drag = self.pressed = None
        if drag is not None and drag['mode'] is not None:
            return None
        command = self.command_at(point)
        return command if command is not None and command == pressed else None

    def wheel(self, dx, dy, point):
        if self.popup or self.alert:
            return
        row = self.row_at(point)
        if dx and row is not None:
            self.row_x[row.key] = self.row_x.get(row.key, 0) - dx * SCROLL_STEP
        if dy:
            self.scroll_y -= dy * SCROLL_STEP
        self.clamp()

    INFO_KEY = pygame.K_i            # the highlighted episode's info card (an episode that has one)

    def popup_commands(self):
        """The popup's New Game, Continue and back, in keyboard order."""
        record = self.popup
        return [('new', record['id']), ('continue', record['id']), ('close',)]

    def popup_key(self, key):
        """The New Game / Continue popup's keys: arrows or Tab move a highlight over its two cards and its back button,
        Enter or Space taps the highlighted one, Escape closes it. Continue is highlighted first."""
        if key == pygame.K_ESCAPE:
            return ('close',)
        commands = self.popup_commands()
        if self.popup_focus not in commands:
            if key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN, pygame.K_TAB):
                self.popup_focus = commands[1]
            elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self.popup_focus = commands[1]
            return None
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            return self.popup_focus
        step = (-1 if key in (pygame.K_LEFT, pygame.K_UP) or key == pygame.K_TAB and pygame.key.get_mods() & pygame.KMOD_SHIFT
                else 1 if key in (pygame.K_RIGHT, pygame.K_DOWN, pygame.K_TAB) else 0)
        if step:
            self.popup_focus = commands[(commands.index(self.popup_focus) + step) % len(commands)]
        return None

    def info_key(self):
        """`I` on a highlighted episode with an info card: that card."""
        if self.keyboard and self.selected is not None:
            record = next((r for row in self.model.rows for r in row.episodes if r['id'] == self.selected), None)
            if record is not None and self.model.has_info(record):
                return ('info', record['id'])
        return None

    def key(self, key):
        """A keyboard navigation key -> a command, or None."""
        if self.alert:
            return ('dismiss',) if key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE) else None
        if self.popup:
            return self.popup_key(key)
        if key == self.INFO_KEY:
            return self.info_key()
        if key not in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN, pygame.K_RETURN, pygame.K_SPACE):
            return None
        if not self.model.rows:
            return None
        if not self.keyboard or self.selected not in self.model.position:
            self.keyboard = True
            if self.selected not in self.model.position:
                self.selected = self.model.rows[0].episodes[0]['id']
            self.reveal(self.selected)
            return None
        if key in (pygame.K_RETURN, pygame.K_SPACE):
            return ('tile', self.selected)
        row_index, column = self.model.position[self.selected]
        if key in (pygame.K_UP, pygame.K_DOWN):
            row_index = max(0, min(len(self.model.rows) - 1, row_index + (1 if key == pygame.K_DOWN else -1)))
        else:
            column += 1 if key == pygame.K_RIGHT else -1
        episodes = self.model.rows[row_index].episodes
        self.selected = episodes[max(0, min(len(episodes) - 1, column))]['id']
        self.reveal(self.selected)
        return None

    # ------------------------------------------------------------ drawing

    @lru_cache(maxsize=1)
    def backdrop(self):
        """The main menu's backdrop, dimmed behind the rows (see module docstring)."""
        layer = self.main_backdrop().copy()
        shade = pygame.Surface(layer.get_size(), pygame.SRCALPHA)
        shade.fill((0, 0, 0, BACKDROP_DIM_ALPHA))
        layer.blit(shade, (0, 0))
        return layer

    @lru_cache(maxsize=1)
    def shadow(self):
        """A soft drop shadow for a tile: 216 x 290 plus a 16-point blur margin on every side."""
        margin = 16
        w, h = TILE[0] + 2 * margin, TILE[1] + 2 * margin
        small = pygame.Surface((w // 4, h // 4), pygame.SRCALPHA)
        pygame.draw.rect(small, (0, 0, 0, 200), (margin // 4, margin // 4, TILE[0] // 4, TILE[1] // 4))
        return pygame.transform.smoothscale(small, (w * S, h * S))

    def caption(self, layer, record, x, y):
        """The tile's caption over its top-left corner."""
        text = self.model.label(record)
        for points in (24, 20):
            lines = self.wrap(text, points, TILE_STEP - 4, 2)
            if len(lines) == 1 or points == 20:
                break
        for index, line in enumerate(lines):
            self.text(layer, line, points, x - 10, y - 12 + index * (points + 4))

    def tile_image(self, record):
        """The tile's face at 2x: the preview, or preview above / saved screenshot below the zigzag."""
        preview = self.model.preview(record)
        shot = self.shots(record) if record['id'] in self.saved else None
        if shot is None:
            return preview
        face = pygame.Surface((TILE[0] * S, TILE[1] * S), pygame.SRCALPHA)
        face.fill((0, 0, 0, 255))
        top = preview.subsurface((0, 0, TILE[0] * S, self.mask(TOP_MASK).get_height())).convert_alpha()
        top.blit(self.mask(TOP_MASK), (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        face.blit(top, (0, 0))
        bottom_mask = self.mask(BOTTOM_MASK)
        window = shot_window(shot, BOTTOM_MASK_TOP - SHOT_OFFSET, bottom_mask.get_height() // S)
        window.blit(bottom_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        face.blit(window, (0, BOTTOM_MASK_TOP * S))
        return face

    def draw_tile(self, layer, record, x, y):
        shadow = self.shadow()
        layer.blit(shadow, ((x - 16 + 6) * S, (y - 16 + 6) * S))
        layer.blit(self.tile_image(record), (x * S, y * S))
        if self.keyboard and record['id'] == self.selected:
            pygame.draw.rect(layer, (255, 255, 255), (x * S - 3 * S, y * S - 3 * S, TILE[0] * S + 6 * S, TILE[1] * S + 6 * S),
                             2 * S, border_radius=4 * S)
        mark = self.model.mark(record)
        if mark is not None:
            self.draw_standard_mark(layer, x + TILE[0] - 42, y + TILE[1] - 30, mark, self.model.mark_color(record))
        info = self.info_rect(record, x, y)
        if info is not None:
            self.draw_info_mark(layer, info)
        self.caption(layer, record, x, y)

    def info_rect(self, record, x, y):
        """A tile's info button (points), where SHS's SD mark sits (bottom-aligned with it, left of it if both
        show); None without an info card."""
        if not self.model.has_info(record):
            return None
        right = x + TILE[0] - 8 - (42 if self.model.mark(record) is not None else 0)
        return pygame.Rect(right - INFO_PLATE[0], y + TILE[1] - 10 - INFO_PLATE[1], *INFO_PLATE)

    def draw_info_mark(self, layer, rect):
        """The tile's info button in the SD mark's style: its dark plate, an "i" in a ring in its text colour."""
        plate = pygame.Surface((rect.width * S, rect.height * S), pygame.SRCALPHA)
        pygame.draw.rect(plate, (0, 0, 0, 150), plate.get_rect(), border_radius=6 * S)
        center = plate.get_rect().center
        pygame.draw.circle(plate, MARK_COLOR, center, 9 * S, round(1.5 * S))
        pygame.draw.circle(plate, MARK_COLOR, (center[0], center[1] - 4 * S), 2 * S)
        stem = pygame.Rect(0, 0, 3 * S, 7 * S)
        stem.midtop = (center[0], center[1] - 1 * S)
        pygame.draw.rect(plate, MARK_COLOR, stem, border_radius=1 * S)
        layer.blit(plate, (rect.x * S, rect.y * S))

    def draw_info_icon(self, layer, cx, cy, size=INFO_ICON):
        """The info button: the list's play / pause icon ring with an "i" for its glyph."""
        surface = pygame.Surface((size * S, size * S), pygame.SRCALPHA)
        center = (size * S / 2, size * S / 2)
        pygame.draw.circle(surface, (*self.ICON_RING_COLOR, self.RING_ALPHA), center, size / 2 * S)
        pygame.draw.circle(surface, (255, 255, 255, 235), center, (size / 2 - 4) * S)
        glyph = (*self.PLAY_COLOR, self.PLAY_ALPHA)
        pygame.draw.circle(surface, glyph, (center[0], center[1] - 6.5 * S), 2.5 * S)
        stem = pygame.Rect(0, 0, 4 * S, 11 * S)
        stem.midtop = (center[0], center[1] - 2 * S)
        pygame.draw.rect(surface, glyph, stem, border_radius=2 * S)
        layer.blit(surface, (round(cx * S - size * S / 2), round(cy * S - size * S / 2)))

    def draw_standard_mark(self, layer, x, y, mark='SD', color=None):
        """A small "SD" tag on episodes that come from the standard (non-HD) release; this player's own addition.
        An episode translated from another SHS game shows its game's tag ("NR") on the same plate, in its game's
        colour lightened for the dark plate (owner, 2026-10-25)."""
        width, height = 34, 20
        plate = pygame.Surface((width * S, height * S), pygame.SRCALPHA)
        pygame.draw.rect(plate, (0, 0, 0, 150), plate.get_rect(), border_radius=6 * S)
        tint = MARK_COLOR if color is None else tuple(round(c + (255 - c) * MARK_TINT) for c in color)
        text = self.font(13).render(mark, True, tint)
        plate.blit(text, text.get_rect(center=plate.get_rect().center))
        layer.blit(plate, (x * S, y * S))

    def draw_row_label(self, layer, row, top):
        """The row's catalog category, right-aligned in the otherwise-empty gutter above its tiles; this player's
        own addition (see module docstring) -- fixed to the frame rather than the row's own horizontal scroll, and
        drawn last over the tiles on a small dark plate (like the SD mark), so a wide row's last tile can never
        bury it."""
        width = round(self.measure(row.title, ROW_LABEL_POINTS))
        x, y, pad = FRAME[0] - 16 - width, top + 1, 6
        plate = pygame.Surface(((width + 2 * pad) * S, (ROW_LABEL_POINTS + 4) * S), pygame.SRCALPHA)
        pygame.draw.rect(plate, (0, 0, 0, 130), plate.get_rect(), border_radius=5 * S)
        layer.blit(plate, ((x - pad) * S, (y - 2) * S))
        self.text(layer, row.title, ROW_LABEL_POINTS, x, y, outline=False)

    @lru_cache(maxsize=1)
    def plain_backdrop(self):
        """The main menu's backdrop, undimmed (the list screens' card sits over it as the menus' cards do)."""
        return self.main_backdrop()

    def begin_layer(self, backdrop=True, *, dim=True):
        """The layer a draw starts from: the canvas over the main-menu backdrop (dimmed for the tile grid), or, with
        `backdrop` off, a transparent layer holding only that dim, for zooming in over the live main menu while its
        buttons slide out (Application.render_picker)."""
        if backdrop:
            self.canvas.blit(self.backdrop() if dim else self.plain_backdrop(), (0, 0))
            return self.canvas
        if getattr(self, 'see_through', None) is None:
            self.see_through = pygame.Surface(self.canvas.get_size(), pygame.SRCALPHA).convert_alpha()
        self.see_through.fill((0, 0, 0, BACKDROP_DIM_ALPHA if dim else 0))
        return self.see_through

    def draw(self, *, backdrop=True):
        """Render into the 2x canvas; returns it. `self.hits` lists the clickable rectangles (points). With
        `backdrop` off it renders onto a transparent layer instead (`begin_layer`)."""
        self.clamp()
        layer = self.begin_layer(backdrop)
        self.hits = []
        strings = self.strings()
        for index, row in enumerate(self.model.rows):
            top = index * ROW_HEIGHT - self.scroll_y
            if top + ROW_HEIGHT <= 0 or top >= FRAME[1]:
                continue
            offset = self.row_x.get(row.key, 0)
            for column, record in enumerate(row.episodes):
                x = TILE_X + column * TILE_STEP - offset
                if x + TILE[0] + 20 <= 0 or x - 20 >= FRAME[0]:
                    continue
                self.draw_tile(layer, record, x, top + TILE_Y)
                self.hits.append((pygame.Rect(x, top + TILE_Y, *TILE).clip(pygame.Rect(0, 0, *FRAME)), ('tile', record['id'])))
                info = self.info_rect(record, x, top + TILE_Y)
                if info is not None:          # after the tile's own hit, so it wins
                    self.hits.append((info.inflate(8, 8).clip(pygame.Rect(0, 0, *FRAME)), ('info', record['id'])))
            self.draw_row_label(layer, row, top)
            divider = self.bundle_image('VT_divider.png')
            layer.blit(pygame.transform.smoothscale(divider, (748 * S, 4 * S)), (10 * S, (top + ROW_HEIGHT - 2) * S))
        back = pygame.Rect(BACK_X, BUTTON_Y, *BUTTON_SIZE)
        restore = pygame.Rect(FRAME[0] - BACK_X - BUTTON_SIZE[0], BUTTON_Y, *BUTTON_SIZE)
        dim = bool(self.popup or self.alert)
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

    overlay_shown = None
    overlay_opened = 0

    def overlay_ms(self):
        shown = ('popup', self.popup['id']) if self.popup else ('alert', self.alert) if self.alert else None
        now = pygame.time.get_ticks()
        if shown != self.overlay_shown:
            self.overlay_shown, self.overlay_opened = shown, now
        return now - self.overlay_opened

    def draw_overlay(self, layer, strings):
        if not (self.popup or self.alert):
            self.overlay_shown = None
            return
        ms = self.overlay_ms()
        if ms >= PAUSE_OPEN_MS:
            self.dim(layer)
            self.draw_overlay_card(layer, strings)
            return
        self.dim(layer, alpha=round(DIM_ALPHA * min(1.0, ms / PAUSE_OPEN_MS)))
        card = pygame.Surface(layer.get_size(), pygame.SRCALPHA).convert_alpha()
        self.draw_overlay_card(card, strings)
        scale = pause_scale(ms)
        card = pygame.transform.smoothscale(card, tuple(max(1, round(length * scale)) for length in card.get_size()))
        layer.blit(card, card.get_rect(center=layer.get_rect().center))

    def draw_overlay_card(self, layer, strings):
        if self.popup:
            self.draw_popup(layer, self.popup, strings)
        else:
            self.draw_message(layer)

    def draw_message(self, layer):
        """The open alert: an episode's info card or a (title, text) message."""
        if isinstance(self.alert, EpisodeInfo):
            self.draw_info(layer, self.alert)
        else:
            self.draw_alert(layer, *self.alert)

    def dim(self, layer, alpha=DIM_ALPHA):
        shade = pygame.Surface(layer.get_size(), pygame.SRCALPHA)
        shade.fill((0, 0, 0, alpha))
        layer.blit(shade, (0, 0))
        self.hits = []

    def card_image(self):
        return self.bundle_image('popupBackground.png')

    def draw_card(self, layer):
        card = self.card_image()
        layer.blit(pygame.transform.smoothscale(card, (CARD[0] * S, CARD[1] * S)),
                   (CARD_TOP_LEFT[0] * S, CARD_TOP_LEFT[1] * S))

    def draw_popup(self, layer, record, strings):
        self.draw_card(layer)
        left, top = CARD_TOP_LEFT
        preview = self.model.preview(record)
        shot = self.shots(record) if record['id'] in self.saved else None
        for label, image, x, command in ((strings[self.NEW_GAME], preview, left + 22, ('new', record['id'])),
                                         (strings[self.CONTINUE], shot or preview, left + 260, ('continue', record['id']))):
            shade = self.shadow()
            layer.blit(shade, ((x - 16 + 6) * S, (top + 44 - 16 + 6) * S))
            layer.blit(image, (x * S, (top + 44) * S))
            font = self.font(28)
            text = font.render(label, True, self.FOCUS_TEXT_COLOR if self.popup_focus == command else self.TEXT_COLOR)
            layer.blit(text, text.get_rect(midbottom=((x + TILE[0] / 2) * S, (top + 40) * S)))
            self.hits.append((pygame.Rect(x, top + 44, *TILE), command))
            if self.popup_focus == command:          # the keyboard's highlight, as on the grid's tiles
                pygame.draw.rect(layer, (255, 255, 255), ((x - 3) * S, (top + 44 - 3) * S, (TILE[0] + 6) * S,
                                                          (TILE[1] + 6) * S), 2 * S, border_radius=4 * S)
        back = pygame.Rect(left + 22, top + 359, *BUTTON_SIZE)
        self.draw_button(layer, back.x, back.y, pressed=self.pressed == ('close',) or self.popup_focus == ('close',))
        self.hits.append((back, ('close',)))
        # A click outside the card closes it.
        self.hits.insert(0, (pygame.Rect(0, 0, *FRAME), ('close',)))

    def draw_alert(self, layer, title, text):
        self.draw_card(layer)
        left, top = CARD_TOP_LEFT
        font = self.font(32)
        heading = font.render(title, True, self.TEXT_COLOR)
        layer.blit(heading, heading.get_rect(midtop=(FRAME[0] // 2 * S, (top + 30) * S)))
        body = self.font(24)
        for index, line in enumerate(self.wrap(text, 24, CARD[0] - 60, 8)):
            surface = body.render(line, True, self.TEXT_COLOR)
            layer.blit(surface, surface.get_rect(midtop=(FRAME[0] // 2 * S, (top + 100 + index * 32) * S)))
        button = pygame.Rect(FRAME[0] // 2 - BUTTON_SIZE[0] // 2, top + 359, *BUTTON_SIZE)
        self.draw_button(layer, button.x, button.y, label='OK', pressed=self.pressed == ('dismiss',))
        self.hits.append((button, ('dismiss',)))

    def draw_info(self, layer, info):
        """An episode's info card on the alert's card: its title, airdate and price, then the store description at
        the largest size that fits above the OK button."""
        self.draw_card(layer)
        left, top = CARD_TOP_LEFT
        width = CARD[0] - 60
        y = top + 24
        for line in self.wrap(info.title, INFO_TITLE_POINTS, width, 2):
            surface = self.font(INFO_TITLE_POINTS).render(line, True, self.TEXT_COLOR)
            layer.blit(surface, surface.get_rect(midtop=(FRAME[0] // 2 * S, y * S)))
            y += INFO_TITLE_POINTS + 6
        meta = '    '.join(part for part in (info.airdate, info.price and f'Price: {info.price}') if part)
        if meta:
            surface = self.font(INFO_META_POINTS).render(meta, True, self.TEXT_COLOR)
            surface = faded(surface, 190)
            layer.blit(surface, surface.get_rect(midtop=(FRAME[0] // 2 * S, (y + 2) * S)))
            y += INFO_META_POINTS + 10
        y += 8
        bottom = top + 359 - 12
        for points in INFO_TEXT_POINTS:
            step = round(points * 1.3)
            lines = self.wrap(info.description, points, width)
            if len(lines) * step <= bottom - y or points == INFO_TEXT_POINTS[-1]:
                break
        lines = lines[:max(1, (bottom - y) // step)]
        for index, line in enumerate(lines):
            surface = self.font(points).render(line, True, self.TEXT_COLOR)
            layer.blit(surface, ((left + 30) * S, (y + index * step) * S))
        button = pygame.Rect(FRAME[0] // 2 - BUTTON_SIZE[0] // 2, top + 359, *BUTTON_SIZE)
        self.draw_button(layer, button.x, button.y, label='OK', pressed=self.pressed == ('dismiss',))
        self.hits.append((button, ('dismiss',)))
        self.hits.insert(0, (pygame.Rect(0, 0, *FRAME), ('dismiss',)))      # a click outside the card closes it


def shot_window(shot, top, height):
    """`height` points of a 2x saved screenshot starting `top` points down it, as a new alpha surface."""
    window = pygame.Surface((TILE[0] * S, height * S), pygame.SRCALPHA)
    window.fill((0, 0, 0, 255))
    window.blit(shot, (0, -top * S))
    return window
