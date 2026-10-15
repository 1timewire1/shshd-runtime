"""Cause of Death's menu-engine windows ("Play with sound?", "Exit Game?", "Delete Saved Game?", the notices, the
Privacy Policy / EULA / Terms list and the end-of-episode menus), in SHS HD's layout and CoD's dress.

The windows come from CoD's menu engine data (logical resource 15) and string bank (resource 13). By the owner's
choice (2026-10-14) every CoD menu keeps SHS HD's scaling and layout (`desktop_hd_menu.HdMenuWindows`: the 604-point
card centred in the 768 x 1024 frame, its title, message, rows, button strip and 156 x 58 buttons) and takes only its
styling from CoD's own windows (IMG_0514 "Exit Game?", IMG_0473 "Play with sound?"):

* The card is CoD's window (pack 16 frames 78-80, pack 204 frame 3) drawn as vectors at HD's size, as SHS HD draws
  its own cards (`draw_cod_card`): a 6-point (85, 95, 176) border with 20-point corners around a white face, both at
  alpha 242, and the grey edge (89, 90, 90) in place of the border between the 112-point top and the 86-point
  footer (IMG_0514). Stretching the 1x pieces 2x left their corners soft and off the grey strips.
* Text is Arial Rounded in black (title and message) and (60, 60, 62) (rows); rows alternate lavender and pink; rules
  are (166, 166, 166).
* Every button is CoD's blue one (pack 16 frames 90-92, pressed 93-95; layout 70 / 71) with a white label, or the
  back arrow (frame 89). With the SHS HD art source they are SHS HD's doubles in CoD's colours
  (cod/hd_art.positional_frames). CoD has no orange alert buttons.
* Items whose condition fails are hidden (`checkItemConditions`): flag 2 shows "Enable Usage Sharing" only while
  sharing is disabled, flag 4 "Disable Usage Sharing" only while it is on; Vibration (8) and the Pause "Alert" row
  (16) never show here.
"""
from functools import lru_cache

import pygame

from .content import ContentError
from .desktop_hd_menu import CARD_LEFT, CARD_W, HdMenuWindows
from .hd_ui import BUTTON_SIZE, S
from .menu import MenuStrings
from .ui_assets import ImagePack

EXIT_GAME, EXIT_ACTION = 16, 24
BUTTON_PIECES = {False: (90, 91, 92), True: (93, 94, 95)}     # left cap, middle, right cap; True = pressed
ARROW = 89
TOP_HEIGHT, BOTTOM_HEIGHT = 112, 86                              # frames 80 / 79 at HD's size (56 / 43 CoD points)
# CoD's window card, measured on its pieces: pack 16 frames 78-80 (3 px border, 10 px corners, alpha 242) and pack 204
# frame 3 (the grey edge beside a window's body), at HD's size.
CARD_BORDER, CARD_EDGE, CARD_FACE, CARD_ALPHA = (85, 95, 176), (89, 90, 90), (255, 255, 255), 242
CARD_LINE, CARD_RADIUS = 6, 20


def draw_cod_card(layer, box, edge=None, *, scale=S):
    """CoD's window card over `box` (x, y, width, height in frame points) as vectors: the border and face, and the
    grey edge from `edge`'s top to its bottom (frame points) in place of the border, as beside a window's body."""
    x, y, w, h = box
    surface = pygame.Surface((round(w * scale), round(h * scale)), pygame.SRCALPHA)
    line, radius = round(CARD_LINE * scale), round(CARD_RADIUS * scale)
    pygame.draw.rect(surface, (*CARD_BORDER, CARD_ALPHA), surface.get_rect(), border_radius=radius)
    pygame.draw.rect(surface, (*CARD_FACE, CARD_ALPHA), surface.get_rect().inflate(-2 * line, -2 * line),
                     border_radius=max(0, radius - line))
    if edge is not None:
        top, bottom = (round((value - y) * scale) for value in edge)
        if bottom > top:
            for left in (0, surface.get_width() - line):
                surface.fill((*CARD_EDGE, 254), (left, top, line, bottom - top))
    layer.blit(surface, (round(x * scale), round(y * scale)))
SHOWN_WHEN = {2: lambda disabled: disabled, 4: lambda disabled: not disabled}
NEVER = (8, 16)


class CodButtons:
    """CoD's blue footer buttons and back arrow (pack 16 frames 89-95) at SHS HD's 156 x 58, for any HD-layout screen
    with `library` and `font` (these windows, the episode pickers). With the SHS HD art source they are SHS HD's
    doubles in CoD's colours; `fallback_piece` serves CoD's own frame otherwise."""

    @lru_cache(maxsize=1)
    def hd_pieces(self):
        from .cod.hd_art import positional_menu_buttons
        try:
            hd = self.library.shs_hd_resource(32)
            if hd is None:
                return {}
            return positional_menu_buttons(self.library.android_asset(16), hd)
        except (AttributeError, ContentError, ValueError):
            return {}

    @lru_cache(maxsize=16)
    def piece(self, frame):
        """A pack 16 frame at HD's size, at the layer's density (the HD-derived one when the art source has it)."""
        derived = self.hd_pieces().get(frame)
        if derived is not None:
            pixels, size = derived
            image = pygame.image.frombytes(pixels, size, 'RGBA').convert_alpha()
            return pygame.transform.smoothscale(image, (size[0] * S, size[1] * S))
        return self.fallback_piece(frame)

    def fallback_piece(self, frame):
        image = ImagePack.parse(self.library.android_asset(16)).images[frame]
        surface = pygame.image.frombytes(image.pixels, (image.width, image.height), image.mode).convert_alpha()
        return pygame.transform.smoothscale(surface, (image.width * 2 * S, image.height * 2 * S))

    def draw_button(self, layer, x, y, orange=False, label=None, pressed=False):
        """CoD's blue button at HD's 156 x 58: caps and middle, then a white label or the back arrow. CoD has no
        orange button, so `orange` draws blue too."""
        width, height = BUTTON_SIZE
        first, middle, last = (self.piece(i) for i in BUTTON_PIECES[pressed])
        cap = first.get_width() / S
        layer.blit(pygame.transform.smoothscale(first, (round(cap * S), height * S)), (round(x * S), round(y * S)))
        layer.blit(pygame.transform.smoothscale(middle, (round((width - 2 * cap) * S), height * S)),
                   (round((x + cap) * S), round(y * S)))
        layer.blit(pygame.transform.smoothscale(last, (round(cap * S), height * S)),
                   (round((x + width - cap) * S), round(y * S)))
        center = ((x + width / 2) * S, (y + height / 2) * S)
        if label:
            text = self.font(28).render(label, True, (255, 255, 255))
            layer.blit(text, text.get_rect(center=(center[0], center[1] - 2 * S)))
        else:
            arrow = self.piece(ARROW)
            layer.blit(arrow, arrow.get_rect(center=(center[0], center[1] - 2 * S)))


class CodMenuWindows(CodButtons, HdMenuWindows):
    SWITCH_ACTION = 30                  # CoD's end-menu "More EA Games"
    # Usage sharing: CoD's privacy window has its own Disable / Enable rows, opening windows 18 / 19 (actions 26 / 27).
    HIDDEN_ACTIONS, HIDDEN_MENUS = (26, 27), (18, 19)
    TITLE_COLOR = MESSAGE_COLOR = (0, 0, 0)
    ROW_TEXT_COLOR, ROW_FILLS, RULE_COLOR, CARD_FILL = (60, 60, 62), ((240, 240, 248), (255, 243, 253)), (166, 166, 166), \
        (255, 255, 255)

    def __init__(self, library, data, art, *, logging_disabled=lambda: False):
        super().__init__(library, data, art)
        self.logging_disabled = logging_disabled

    @lru_cache(maxsize=1)
    def strings(self):
        return MenuStrings.parse(self.library.android_asset(13))

    def items(self, menu_id):
        shown = []
        for action in self.data.items(menu_id):
            flag = action.flags[0]
            if (flag in NEVER or flag in SHOWN_WHEN and not SHOWN_WHEN[flag](self.logging_disabled())
                    or not self.shown(action)):
                continue
            shown.append(action)
        return shown

    # -- art ----------------------------------------------------------------------------------------------------
    def fallback_piece(self, frame):
        return self.art.frame_scaled(16, frame, 2 * S)

    def draw_card(self, layer, top, total):
        """CoD's card at HD's size: blue-bordered over the top 112 points and the footer's 86, grey-edged between."""
        top_height = min(TOP_HEIGHT, total / 2)
        bottom_height = min(BOTTOM_HEIGHT, total - top_height)
        draw_cod_card(layer, (CARD_LEFT, top, CARD_W, total), (top + top_height, top + total - bottom_height))
