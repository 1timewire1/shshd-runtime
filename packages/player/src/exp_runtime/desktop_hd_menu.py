"""The iOS HD menu windows ("Play with sound?", "Help & About", "Options", "Want More Content?", the info pages).

Which windows exist, their titles, rows and actions come from the menu engine data (`menu_engine.py`). The look is measured
on the owner's photos `reference/screenshots/main menu` (IMG_0125-0127, IMG_0235) and `dialouge/IMG_0243`; all sizes are
frame points (768 x 1024), drawn at 2x.

* The window is a blue-bordered translucent card 604 wide, centered on the frame; its height is header + rows + footer.
* Header: the title (Arial Rounded 56, centered, blue) whose first line is centered 58 points below the top with a 43.5
  point pitch; when the menu has a message it follows in 28 point text (26.6 pitch, left at 41 points, 522 wide) and the
  header ends 24.4 below its last line; without one the header ends 53.7 below the title's last line (111.7 for one line).
* Rows are 88 points (a slider row 130), alternately lavender (238, 237, 243) and pink (247, 234, 245) over a 1 point gray
  rule; their text is 28 point (88, 134, 224) at x 31 from the card's left. The footer is 85 points with the blue back
  button (156 x 58) at x 26 from the card's left, 14 below the footer's top.
* An alert (style 2: "Play with sound?", "Delete Saved Game?") has no rows but an 83 point strip of orange buttons whose
  centers sit 174 points either side of the card's center.

Options and the info pages are not drawn here: the main menu reuses the pause menu's (desktop_pause_hd.py), which was
measured on the same photos with the light-mode switches.

Not photographed: the notices' single button (an orange OK, string 154), the pressed row shade (drawn as the pause
menu's highlighted row, a shade darker; the arrow keys' highlight looks the same) and the info-page form (unused by the
main menu, which shows the pause menu's pages).
"""
from . import graphics as pygame

from .desktop_pause_hd import FOCUS_SHADE
from .hd_ui import HdUi, S, FRAME, BLUE
from .menu_engine import ENGINE, NO_STRING, QUEUE
from .ui_assets import Rect

CARD_W = 604
CARD_LEFT = (FRAME[0] - CARD_W) // 2
TITLE_POINTS, SMALL_TITLE_POINTS, BODY_POINTS = 56, 44, 28      # a title that needs two lines is set smaller
TITLE_FIRST, SMALL_TITLE_FIRST, TITLE_PITCH = 58, 55, 43.5
TITLE_WIDTH = CARD_W - 40
BODY_LEFT, BODY_WIDTH, BODY_PITCH = 41, 522, 26.6
ROW_HEIGHT, FOOTER_HEIGHT, BUTTON_STRIP = 88, 85, 83
ROW_TEXT_LEFT, ROW_WIDTH = 31, 500
ROW_COLORS = ((234, 235, 244), (252, 240, 249))
ROW_TEXT = (88, 134, 224)
RULE = (150, 150, 150)
HEADER_FILL, FILL_ALPHA = (255, 255, 255), 243          # the dialogue box's 243 / 255
CORNER = 22
ALERT_OFFSET = 174
BACK_LEFT = 26
FORM_TOTAL = 901                       # the Help & About card's height, used by the info pages
NO_STYLE = 0xff
FORM_LAST = 6                          # menus 0-6 are the info pages


class Row:
    def __init__(self, action, top, height, kind, lines):
        self.action, self.top, self.height, self.kind, self.lines = action, top, height, kind, lines


class HdMenuWindows(HdUi):
    # Style, overridable by a game that keeps this layout in its own dress (desktop_cod_menu.CodMenuWindows).
    TITLE_COLOR = MESSAGE_COLOR = BLUE
    SWITCH_ACTION = 23                  # the end menus' "More EA Games" (doMenuEngineAction 23), now Switch Game
    ROW_TEXT_COLOR, ROW_FILLS, RULE_COLOR, CARD_FILL = ROW_TEXT, ROW_COLORS, RULE, HEADER_FILL

    def __init__(self, library, data, art):
        super().__init__(library)
        self.data, self.art = data, art
        self.hits = []
        self.body_rect = None        # an info page's scrolling text area
        self.body_height = 0
        self.switch_title = None        # the other game's title for the Switch Game rows; None keeps the native label

    # ------------------------------------------------------------ text

    def text_for(self, string_id, variables=None):
        if string_id == NO_STRING:
            return ''
        text = self.strings()[string_id]
        for key, value in (variables or {}).items():
            text = text.replace(f'~{key}~', value)
        return text

    def item_label(self, action, variables):
        if self.switch_title and (ENGINE, self.SWITCH_ACTION) in action.steps:
            return self.switch_title
        return '' if action.label == 3 else self.text_for(action.label, variables)      # string 3 is empty: an arrow button

    # Rows never shown (this fork): usage sharing's, by the engine action or the window they open (SHS HD's row is
    # action 17, which opens the Disable / Enable windows 19 / 20). The runtime sends no usage data, so the switch
    # would only confuse (owner, 2026-10-15).
    HIDDEN_ACTIONS, HIDDEN_MENUS = (17,), (19, 20)

    def shown(self, action):
        return not (any((ENGINE, number) in action.steps for number in self.HIDDEN_ACTIONS)
                    or any((QUEUE, number) in action.steps for number in self.HIDDEN_MENUS))

    def items(self, menu_id):
        """The window's items (a game may hide the ones its conditions rule out, `checkItemConditions`)."""
        return [action for action in self.data.items(menu_id) if self.shown(action)]

    # ------------------------------------------------------------ geometry

    def kind_of(self, menu):
        if menu.style == 2:
            return 'alert'
        if menu.style == NO_STYLE:
            return 'form' if menu.id <= FORM_LAST else 'notice'
        return 'list'

    def layout(self, menu_id, variables=None):
        menu = self.data.menu(menu_id)
        kind = self.kind_of(menu)
        items = self.items(menu_id)
        title_text = self.text_for(menu.title, variables)
        points, first = TITLE_POINTS, TITLE_FIRST
        title = self.wrap(title_text, points, TITLE_WIDTH)
        if len(title) > 1:
            points, first = SMALL_TITLE_POINTS, SMALL_TITLE_FIRST
            title = self.wrap(title_text, points, TITLE_WIDTH)
        message = self.wrap(self.text_for(menu.message, variables), BODY_POINTS, BODY_WIDTH) if menu.message != NO_STRING else []
        last_title = first + TITLE_PITCH * (len(title) - 1)
        if message and kind != 'form':
            first_message = last_title + 78
            header = first_message + BODY_PITCH * (len(message) - 1) + 24.4
        else:
            first_message = None
            header = last_title + 53.7
        g = dict(menu=menu, kind=kind, title=title, title_points=points, title_first=first, message=message, first_message=first_message, header=header, items=items,
                 rows=[], footer=None, strip=header)
        if kind == 'list':
            footer = next((a for a in items if a.is_footer_button), None)
            position = header
            for action in items:
                if action is footer:
                    continue
                g['rows'].append(Row(action, position, ROW_HEIGHT, 'text',
                                     self.wrap(self.item_label(action, variables), BODY_POINTS, ROW_WIDTH)))
                position += ROW_HEIGHT
            g.update(footer=footer, strip=position)
            total = position + FOOTER_HEIGHT
        elif kind == 'form':
            g.update(footer=items[0] if items else None, strip=FORM_TOTAL - FOOTER_HEIGHT)
            total = FORM_TOTAL
        else:
            total = header + BUTTON_STRIP
        g.update(total=total, top=(FRAME[1] - total) / 2)
        return g

    # ------------------------------------------------------------ drawing

    def draw_card(self, layer, top, total):
        """The blue-bordered translucent card (the dialogue box art), its border 20 points outside the inner rectangle."""
        inner_w, inner_h = CARD_W - 40, total - 40
        self.art.box(layer, Rect((FRAME[0] - inner_w) / 4, (top + 20) / 2, inner_w / 2, inner_h / 2), 1,
                     alpha=self.art.box_alpha(), scale=2 * S)

    def draw(self, layer, menu_id, *, variables=None, pressed=None, body_scroll=0):
        """Draw the window. Fills `self.hits` and, for info pages, `body_rect`."""
        g = self.layout(menu_id, variables)
        top, total, left = g['top'], g['total'], CARD_LEFT
        self.hits, self.body_rect = [], None
        self.draw_card(layer, top, total)
        clip = pygame.Rect((left + 6) * S, round((top + 6) * S), (CARD_W - 12) * S, round((total - 12) * S))
        band = pygame.Surface(clip.size, pygame.SRCALPHA)
        pygame.draw.rect(band, (*self.CARD_FILL, FILL_ALPHA), band.get_rect(), border_radius=CORNER * S)
        layer.blit(band, clip.topleft)
        layer.set_clip(clip)
        for index, row in enumerate(g['rows']):
            fill = pygame.Surface((clip.width, round(row.height * S)), pygame.SRCALPHA)
            color = self.ROW_FILLS[index % 2]
            if pressed == ('item', row.action.id):
                color = tuple(round(c * FOCUS_SHADE) for c in color)
            fill.fill((*color, FILL_ALPHA))
            layer.blit(fill, (clip.x, round((top + row.top) * S)))
        layer.set_clip(None)
        rules = [g['header']] + [row.top + row.height for row in g['rows']]
        if g['kind'] == 'form':
            rules.append(g['strip'])
        for y in rules:
            pygame.draw.line(layer, self.RULE_COLOR, ((left + 6) * S, round((top + y) * S)), ((left + CARD_W - 6) * S, round((top + y) * S)), S)
        for index, line in enumerate(g['title']):
            self.centered_line(layer, line, g['title_points'], FRAME[0] / 2, top + g['title_first'] + index * TITLE_PITCH,
                               self.TITLE_COLOR)
        for index, line in enumerate(g['message']) if g['kind'] != 'form' else ():
            self.line_left(layer, line, BODY_POINTS, left + BODY_LEFT, top + g['first_message'] + index * BODY_PITCH,
                           self.MESSAGE_COLOR)
        if g['kind'] == 'form':
            self.draw_body(layer, g, top, body_scroll)
        for row in g['rows']:
            self.draw_row(layer, row, top)
        self.draw_buttons(layer, g, top, pressed)
        return g

    def line_left(self, layer, text, points, x, center_y, color=BLUE):
        surface = self.font(points).render(text, True, color)
        layer.blit(surface, surface.get_rect(midleft=(round(x * S), round(center_y * S))))

    def draw_body(self, layer, g, top, scroll):
        """An info page's text, scrolled by `scroll` points inside the area between the rule and the footer."""
        area = pygame.Rect(CARD_LEFT + BODY_LEFT, round(top + g['header'] + 14), BODY_WIDTH, round(g['strip'] - g['header'] - 24))
        lines = g['message']
        self.body_rect, self.body_height = area, len(lines) * BODY_PITCH
        layer.set_clip(pygame.Rect(area.x * S, area.y * S, area.width * S, area.height * S))
        for index, line in enumerate(lines):
            y = area.y + BODY_PITCH / 2 + index * BODY_PITCH - scroll
            if -BODY_PITCH < y - area.y < area.height + BODY_PITCH and line:
                self.line_left(layer, line, BODY_POINTS, area.x, y, self.MESSAGE_COLOR)
        layer.set_clip(None)

    def draw_row(self, layer, row, top):
        left, y = CARD_LEFT, top + row.top
        first = y + row.height / 2 - BODY_PITCH * (len(row.lines) - 1) / 2
        for index, line in enumerate(row.lines):
            self.line_left(layer, line, BODY_POINTS, left + ROW_TEXT_LEFT, first + index * BODY_PITCH, self.ROW_TEXT_COLOR)
        self.hits.append((pygame.Rect(left + 6, y, CARD_W - 12, row.height), ('item', row.action.id)))

    def draw_buttons(self, layer, g, top, pressed):
        y = top + g['strip'] + 14
        if g['kind'] == 'alert':
            actions = g['items']
            centers = [FRAME[0] / 2] if len(actions) == 1 else [FRAME[0] / 2 + ALERT_OFFSET * (2 * i - 1) for i in range(len(actions))]
            for action, center in zip(actions, centers):
                self.orange_button(layer, center - 78, y, self.item_label(action, None), action, pressed)
        elif g['kind'] == 'notice':
            self.orange_button(layer, FRAME[0] / 2 - 78, y, self.strings()[154], g['items'][0], pressed)
        elif g['footer'] is not None:
            action = g['footer']
            x = CARD_LEFT + BACK_LEFT
            label = self.item_label(action, None) if g['kind'] == 'list' else ''
            self.draw_button(layer, x, y, label=label or None, pressed=pressed == ('item', action.id))
            self.hits.append((pygame.Rect(x, y, 156, 58), ('item', action.id)))

    def orange_button(self, layer, x, y, label, action, pressed):
        self.draw_button(layer, x, y, orange=True, label=label, pressed=pressed == ('item', action.id))
        self.hits.append((pygame.Rect(round(x), round(y), 156, 58), ('item', action.id)))
