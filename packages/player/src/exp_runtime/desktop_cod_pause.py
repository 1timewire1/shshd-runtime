"""Cause of Death's pause menu (the gear): Pause, Options and Help & About, in SHS HD's layout and CoD's dress.

CoD's menus are its menu engine's windows (logical resource 15): Pause is menu 24 (Resume / Options / Help & About /
Main Menu), Options menu 20, Help & About menu 13, with SHS HD's string ids (8, 9, 10, 20, 120, 12-15; the pages
133-140, 16 / 0) in CoD's bank 13. As in SHS HD the rows are a UIKit table with a UISwitch and UISlider.

By the owner's choice (2026-10-14) every CoD menu keeps SHS HD's scaling and layout (`desktop_pause_hd.HdPauseMenu`:
the 604-point card in the 768 x 1024 frame, 88-point rows, HD's UIKit control sizes, HD's centring and text pages) and
takes only its styling from CoD's own menus, measured on IMG_0460 (Pause), IMG_0461 (Options) and IMG_0462 / 0463
(Help & About):

* The card is CoD's window drawn as vectors at HD's size, as SHS HD draws its own (`desktop_cod_menu.draw_cod_card`,
  measured on pack 16 frames 78-80 and 74 and pack 204 frame 3): the purple-blue border around the header and
  footer, the grey edge beside the rows, the footer's rule.
* Text is Arial Rounded: titles black, row labels (60, 60, 62), a help page's text black on white; rules (166, 166,
  166); rows alternate lavender and pink from the first.
* The back button, its arrow and the speakers are CoD's art, at SHS HD's sizes. With the SHS HD art source they are
  SHS HD's doubles filled with CoD's colours (cod/hd_art.positional_frames).
* Switches and sliders are UIKit's, as in SHS HD (CoD's photos show no slider; it is drawn as SHS HD's is).

Options lists SHS HD's categories (General, Sound, Extras; `desktop_pause_hd.OPTION_CATEGORIES`): Sound has Game Music,
Music Volume, Sound FX and Sound FX Volume; General has Autoplay Dialogue and SHS HD Backdrop; Extras has Disable Choice
Timer, Choice & Answer Hints (CoD's typed puzzles also get faint answers, input_hints.py) and Ask to Skip Mini-Games
(CoD's word quizzes, service 71). Left out by the owner's
choice: Play My Music (the device's music library), and Side Panels and Skip Ad Intros (CoD has no side panels or ad
intros). The Help & About pages show CoD's own text; SHS's text overrides are SHS's.
"""
from functools import lru_cache

from . import graphics as pygame

from .content import ContentError
from .desktop_cod_menu import draw_cod_card
from .desktop_pause_hd import (COD_JOURNAL_LABEL, BORDER, FOOT, HEADER, PANEL_W, PANEL_X, PAGES, ROW, S, SWITCH_LABELS, UPSTREAM_VERSION, VERSION,
                               HdPauseMenu)
from .menu import MenuStrings

# HD pack / frame -> CoD art: the back button's caps and middle (32: 13-15 -> pack 16: 90-92), its arrow (32: 12 ->
# 16: 89) and the slider row's speakers (155: 53 / 54 -> common pack 126: 45 / 46).
ART = {(32, 13): (16, 90), (32, 14): (16, 91), (32, 15): (16, 92), (32, 12): (16, 89),
       (155, 53): (126, 45), (155, 54): (126, 46)}
RULE = (166, 166, 166)                  # pack 16 frame 74, the footer's rule inside the border


class CodPauseMenu(HdPauseMenu):
    TITLE_COLOR, LABEL_COLOR, TEXT_COLOR = (0, 0, 0), (60, 60, 62), (0, 0, 0)
    SEPARATOR_COLOR, PAGE_BACKGROUND, ROW_COLORS = (166, 166, 166), (255, 255, 254), ((240, 240, 248), (255, 243, 253))
    # CoD's Push Notifications page is its menu 6: "Push Notifications" (235) and its own text (237), IMG_0522. SHS
    # HD's ids 238 / 240 are CoD's iOS permission prompt ("Would Like to Send You Push Notifications").
    PAGES = {**PAGES, 'push': (235, 237)}
    CYCLE_FRAMES = ((13, 14, 15), (13, 14, 15))      # CoD's blue button: no orange one, no pressed art mapped
    # Choice hints also show faint answers in CoD's typed puzzles (exp-runtime v0.6.0, input_hints.py); only CoD has
    # them, so only CoD's label says so (owner's choice, 2026-10-20).
    SWITCH_LABELS = {**SWITCH_LABELS, 'choice_hints': 'Choice & Answer Hints'}
    # A CoD story's journal is its case's notes (Claire Hart: Secret in the Shadows; owner, 2026-11-24).
    journal_label = COD_JOURNAL_LABEL

    def __init__(self, resources, art, text=None):
        super().__init__(resources)
        self.cod_art = art

    # -- assets -----------------------------------------------------------------------------------------------
    def raw(self, resource_id):
        return None                     # CoD has no SHS HD bundle; its windows are drawn here

    def available(self):
        try:
            return self.cod_art.game_id() == 'cod' and self.font_path() is not None
        except AttributeError:
            return False

    @lru_cache(maxsize=1)
    def font_path(self):
        from .vector_text import system_font_path
        return system_font_path('arial-rounded', getattr(self.resources, 'library', None))

    def font(self, points):
        if self.ui is not None:
            return self.ui.font(points * self.scale * self.SKIN_TEXT)
        return self.arial(points)

    @lru_cache(maxsize=16)
    def arial(self, points):
        return pygame.font.Font(self.font_path(), round(points * self.scale))

    # -- the Claire Hart skin (desktop_ch_ui.ChUi; CLAIRE_HART_SKIN_PLAN.md, owner 2026-11-21) ---------------------------
    # With chc revision 2's pieces for this episode the same pages are drawn in Classic's dress: its panel with the title
    # on the tab, rows as dark bars with the focused one lit gold, Romic Bold in off-white (an option's value line under
    # it too), the back button and the value buttons as the Play Now pill, the tick gold. The places, sizes, taps and
    # UIKit's switches and slider stay (Classic has none of its own). `ui` is set for each layout (the switch may change
    # between two). In HD frame points: the pieces' art scale (Classic's footer band is FOOT tall at it), Romic's size
    # against Arial Rounded's (it runs wider), the title's points on the tab, the gap round a row.
    ui = None
    SKIN_ART, SKIN_TEXT, SKIN_TITLE, SKIN_ROW_GAP = .9, .9, 40, 4
    SKIN_COLOURS = ('TITLE_COLOR', 'LABEL_COLOR', 'TEXT_COLOR', 'SEPARATOR_COLOR', 'PAGE_BACKGROUND')
    SKIN_PAGE, SKIN_RULE = (9, 40, 36), (6, 28, 25)          # a text page's sunken body, the rules

    def skin(self):
        """The skin's pieces for this episode, or None (the app's own menus, the switch off, chc revision 1)."""
        from .desktop_ch_ui import ChUi
        ui = ChUi.of(self.resources)
        if ui is not self.ui:
            self.ui = ui
            for name in self.SKIN_COLOURS:
                self.__dict__.pop(name, None)
            if ui is not None:
                self.TITLE_COLOR, self.LABEL_COLOR, self.TEXT_COLOR = ui.GOLD, ui.TEXT, ui.TEXT
                self.SEPARATOR_COLOR, self.PAGE_BACKGROUND = self.SKIN_RULE, self.SKIN_PAGE
        return ui

    def see_through(self, color):
        """A fill on the card; in the skin, solid, and a light page's (the file browser's path, a text page's body) the
        sunken teal."""
        if self.ui is not None:
            return (self.SKIN_PAGE if sum(color[:3]) > 600 else tuple(color[:3])) + (255,)
        return HdPauseMenu.see_through(color)

    def rect(self, layer, color, box, radius=0, width=0):
        """HdPauseMenu.rect; in the skin, the app screens' grey rules (SEPARATOR) the skin's dark one."""
        from .desktop_pause_hd import SEPARATOR
        if self.ui is not None and tuple(color[:3]) == SEPARATOR:
            color = self.SKIN_RULE
        return super().rect(layer, color, box, radius, width)

    def text(self, layer, text, x, y, points, color=None, *, center=False, font=None):
        """HdPauseMenu.text; in the skin, dark or blue text (the app screens' BLUE and GRAY) off-white on the teal."""
        from .desktop_pause_hd import BLUE
        color = BLUE if color is None else color
        if self.ui is not None and sum(color[:3]) < 450:
            color = self.ui.TEXT
        return super().text(layer, text, x, y, points, color, center=center, font=font)

    def title_lines(self, text):
        return [text] if self.ui is not None else super().title_lines(text)

    def rows_body(self, layer, top, height, color=None, *, lit=False):
        if self.ui is None:
            return super().rows_body(layer, top, height, color, lit=lit)
        S, gap = self.scale, self.SKIN_ROW_GAP
        band = pygame.Rect(round((PANEL_X + BORDER + gap) * S), round((top + gap / 2) * S),
                           round((PANEL_W - 2 * BORDER - 2 * gap) * S), round((height - gap) * S))
        layer.blit(self.ui.row(band.size, self.SKIN_ART * S, lit=lit), band.topleft)

    def row(self, layer, top, label, *, height=ROW, color=None, background=None, lit=False, badge=None, tint=None,
            value=None):
        """HdPauseMenu.row in the skin: the label (and its value line, smaller and fainter) spaced by Romic's pitch
        (its own line size is too tight: a value line ran into its label), gold on the lit row, a badge in gold."""
        if self.ui is None:
            return super().row(layer, top, label, height=height, color=color, background=background, lit=lit,
                               badge=badge, tint=tint, value=value)
        from .desktop_pause_hd import BADGE_GAP, ROW_PX, VALUE_ALPHA, VALUE_PX
        ui, S = self.ui, self.scale
        color = color or (ui.LIT if lit else ui.TEXT)
        self.rows_body(layer, top, height, background, lit=lit)
        x = PANEL_X + 31
        if badge is not None:
            x += self.badge(layer, x, top + ROW / 2, badge[0], ui.GOLD) + BADGE_GAP
        px, small = ROW_PX * S * self.SKIN_TEXT, VALUE_PX * S * self.SKIN_TEXT
        font = ui.font(px)
        lines = ui.wrap(label, px, 500 * S)
        pitch, below = ui.pitch(px), ui.pitch(small) if value is not None else 0
        y = (top + ROW / 2) * S - (pitch * len(lines) + below) / 2
        for line in lines:
            at = (round(x * S), round(y + (pitch - font.get_height()) / 2))
            ui.text(layer, line, px, color, topleft=at)
            if tint is not None and tint[0] in line:
                ui.text(layer, tint[0], px, tint[1], topleft=(at[0] + font.size(line.partition(tint[0])[0])[0], at[1]),
                        shadow=False)
            y += pitch
        if value is not None:
            ui.text(layer, value, small, color, topleft=(round(x * S), round(y + (below - ui.font(small).get_height()) / 2)),
                    alpha=VALUE_ALPHA)

    def back_button(self, layer, bottom, *, lit=False):
        if self.ui is None:
            return super().back_button(layer, bottom, lit=lit)
        from .desktop_pause_hd import BACK
        S = self.scale
        lit = lit or self.pressed == ('pause_back',)
        box = pygame.Rect(PANEL_X + BACK[0], bottom - BACK[1] - 58, 156, 58)
        pill = self.ui.pill((box.width * S, box.height * S), box.height * S / 57, 'pressed' if lit else 'idle')
        layer.blit(pill, (box.x * S, box.y * S))
        self.ui.arrow(layer, ((box.centerx - 4) * S, (box.centery - 1) * S), S)
        return box

    def cycle_button(self, layer, box, label, *, pressed=False):
        if self.ui is None:
            return super().cycle_button(layer, box, label, pressed=pressed)
        from .desktop_pause_hd import CYCLE_POINTS
        S = self.scale
        x, y, width, height = box
        pill = self.ui.pill((width * S, height * S), height * S / 57, 'pressed' if pressed else 'idle')
        layer.blit(pill, (round(x * S), round(y * S)))
        self.ui.text(layer, label, CYCLE_POINTS * S * self.SKIN_TEXT, self.ui.TEXT,
                     (round((x + width / 2) * S), round((y + height / 2) * S)))

    def check(self, layer, right, middle):
        if self.ui is None:
            return super().check(layer, right, middle)
        S = self.scale
        points = [(right - 26, middle), (right - 16, middle + 10), (right, middle - 12)]
        pygame.draw.lines(layer, self.ui.GOLD, False, [(round(x * S), round(y * S)) for x, y in points], round(5 * S))

    @lru_cache(maxsize=1)
    def strings(self):
        return list(MenuStrings.parse(self.resources.library.android_asset(13)).strings)

    def text_lines(self, page):
        """A page's (title, body): this player's CoD text where it has one (help_text_overrides.COD_HELP_TEXT_OVERRIDES),
        else CoD's own. CoD's version token is ~259~."""
        from .help_text_overrides import COD_HELP_TEXT_OVERRIDES
        if page in self.text_pages:                     # one the host wrote (show_text)
            return self.text_pages[page][:2]
        override = COD_HELP_TEXT_OVERRIDES.get(page)
        if override is not None:
            title, body = override
        else:
            title_id, body_id = self.PAGES[page]
            strings = self.strings()
            title, body = strings[title_id], strings[body_id].replace('\x02', '™')
        return title, body.replace('~259~', VERSION).replace('~276~', VERSION).replace('~upstream~', UPSTREAM_VERSION)

    @lru_cache(maxsize=1)
    def hd_pieces(self):
        """{CoD (pack, frame): (RGBA bytes, size)} at SHS HD's size, or {} without the SHS HD art source."""
        from .cod.hd_art import SPEAKER_FRAMES, positional_frames, positional_menu_buttons
        library = self.resources.library
        try:
            hd32, hd155 = library.shs_hd_resource(32), library.shs_hd_resource(155)
            if hd32 is None or hd155 is None:
                return {}
            pieces = {(16, i): v for i, v in positional_menu_buttons(library.android_asset(16), hd32).items()}
            pieces.update({(126, i): v for i, v in positional_frames(library.android_asset(126), hd155,
                                                                      tuple(SPEAKER_FRAMES.items())).items()})
        except (AttributeError, ContentError, ValueError):
            return {}
        return pieces

    @lru_cache(maxsize=None)
    def art(self, resource_id, index):
        """HD's art ids, answered with CoD's art at HD's size (frame points times the layer's density)."""
        pack, frame = ART[(resource_id, index)]
        piece = self.hd_pieces().get((pack, frame))
        if piece is not None:
            pixels, size = piece
            image = pygame.image.frombytes(pixels, size, 'RGBA').convert_alpha()
            return pygame.transform.smoothscale(image, (size[0] * S, size[1] * S))
        return self.cod_art.frame_scaled(pack, frame, 2 * S)        # CoD's 1x art: 2 frame points per pixel

    # -- the card ---------------------------------------------------------------------------------------------
    def panel(self, layer, top, bottom, title, *, header=HEADER):
        """CoD's card at HD's size, as vectors (`desktop_cod_menu.draw_cod_card`): blue-bordered around the header
        and the footer, grey-edged beside the body, with the footer's rule."""
        if self.ui is not None:
            S = self.scale
            title_px = self.SKIN_TITLE * S
            while title_px > 24 * S and self.ui.font(title_px).size(title)[0] > (PANEL_W - 120) * S:
                title_px -= S
            self.ui.draw_panel(layer, pygame.Rect(PANEL_X * S, round(top * S), PANEL_W * S, round((bottom - top) * S)),
                               self.SKIN_ART * S, title, title_px)
            return top + header
        body_top, body_bottom = top + header, bottom - FOOT
        draw_cod_card(layer, (PANEL_X, top, PANEL_W, bottom - top), (body_top, body_bottom), scale=self.scale)
        self.rect(layer, self.see_through(self.PAGE_BACKGROUND),
                  (PANEL_X + BORDER, body_top, PANEL_W - 2 * BORDER, body_bottom - body_top))
        self.rect(layer, RULE, (PANEL_X + BORDER, body_bottom, PANEL_W - 2 * BORDER, 2))
        self.title(layer, title, top, header)
        return top + header

    # -- screens ----------------------------------------------------------------------------------------------
    def layout(self, settings, host_rows=(), *, message=''):
        # CoD has no side panels and no High School Story ad intros (owner's choice: those switches are not listed). Its
        # store plugs take Skip Upsell Intros (upsell_intro.py, owner, 2026-11-17).
        # Its word quizzes (service 71) take Ask to Skip Mini-Games.
        settings = {key: value for key, value in settings.items()
                    if key not in ('side_panels', 'skip_ad_intros')}
        self.skin()
        return super().layout(settings, host_rows, message=message)
