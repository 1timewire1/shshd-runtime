"""Cause of Death's three episode screens: SHS HD's tile grid (Play/Resume) and list pickers (Episodes On Demand by
category, Now Airing by year), in CoD's dress (owner's choice, 2026-10-14). CoD's own iPhone "Play My Episodes" list
(IMG_0467) is not used; only its styling is.

The screens are `desktop_episode_picker.HdEpisodePicker` and `desktop_episode_list_hd.HdEpisodeList` with their style
overridden; the episodes, categories and dates are CoD's own (`cod/episodes.py`, through `PickerModel`). They need
the SHS HD art source linked to the library (`add-hd-art`): the tile masks (resources 13 / 14), the popup card and the
row divider are SHS HD's. Without it the main menu's buttons open the plain episode browser.

CoD's styling:
* **Backdrop.** CoD's title painting, placed as on the main menu (`desktop_cod_main.title_layer`), dimmed as SHS HD
  dims its own.
* **Buttons.** CoD's blue back arrow and a blue "Restore" (CoD has no orange button; IMG_0467), SHS HD's doubles in
  CoD's colours (`desktop_cod_menu.CodButtons`).
* **Popup card.** SHS HD's `popupBackground.png` with its periwinkle border (117, 137, 255) recoloured to CoD's window
  border (85, 95, 176), pack 16's. Labels and alert text are black, as CoD's window titles are.
* **List card.** Episodes On Demand and Now Airing sit in CoD's own menu card (`desktop_cod_pause.CodPauseMenu`, as
  the pause menu's pages are), undimmed, with the back button in its footer (see desktop_episode_list_hd.py).
* **List.** Sampled from CoD's pack 16, the same pieces the SHS list took from the APK's: category bands (85, 95, 176)
  (frames 73 / 76), rows alternating (239, 243, 247) and white starting with the tinted one (frames 82 / 83, the order
  IMG_0467 shows), the selected row (181, 195, 236) (frame 84), the play / pause icons' ring (102, 120, 213) and
  glyphs (60, 85, 205) / (50, 70, 161) (frames 101 / 96) at the frames' own alphas (ring 128, play 102, pause
  128; the SHS list draws its glyphs at 220), black text, and the card border (85, 95, 176) (frame 81).
  Separators are (222, 222, 222), measured on IMG_0467.
* **Strings** are CoD's bank 13: New Game 19, Continue 26, Restore 194, "Restore Not Necessary" 188 / 189, the titles
  Episodes On Demand 83 and Now Airing 119.
"""
from functools import lru_cache
from io import BytesIO

from . import graphics as pygame

from .desktop_cod_main import title_backdrop
from .desktop_cod_menu import CodButtons
from .desktop_episode_list_hd import HdEpisodeList
from .desktop_episode_picker import BOTTOM_MASK, TOP_MASK, HdEpisodePicker
from .hd_scale import S
from .hd_ui import BUNDLE
from .menu import MenuStrings

BORDER = (85, 95, 176)
HD_BORDER = (117, 137, 255)
BUNDLE_IMAGES = ('popupBackground.png', 'VT_divider.png')


def recolor_border(image, color):
    """`image` (SHS HD's popup card) with its flat border colour, and the antialiased blend from it to white, moved to
    `color`. Each pixel's place on the white-to-border blend is read from its green channel."""
    span = 255 - HD_BORDER[1]
    # As RGBA bytes (not pygame's PixelArray, which the iOS drawing backend has no counterpart for).
    pixels = bytearray(pygame.image.tobytes(image, 'RGBA'))
    cache = {}
    for i in range(0, len(pixels), 4):
        r, g, b, a = pixels[i:i + 4]
        if a == 0 or not (b > 240 and r < 250):
            continue
        key = (g, a)
        if key not in cache:
            t = max(0.0, min(1.0, (255 - g) / span))
            cache[key] = bytes((round(255 + (color[0] - 255) * t), round(255 + (color[1] - 255) * t),
                                round(255 + (color[2] - 255) * t), a))
        pixels[i:i + 4] = cache[key]
    return pygame.image.frombytes(bytes(pixels), image.get_size(), 'RGBA')


class CodPickerStyle(CodButtons):
    TEXT_COLOR = (0, 0, 0)
    FOCUS_TEXT_COLOR = BORDER                           # the keyboard's choice in the popup: CoD's window blue
    NEW_GAME, CONTINUE, RESTORE = 19, 26, 194
    RESTORE_TITLE, RESTORE_TEXT = 188, 189
    # Pack 16's play / pause icon (frames 101 / 96) at the frames' own alphas; the info button takes them too.
    ICON_RING_COLOR, PLAY_COLOR, PAUSE_COLOR = (102, 120, 213), (60, 85, 205), (50, 70, 161)
    RING_ALPHA, PLAY_ALPHA, PAUSE_ALPHA = 128, 102, 128
    FINISHED_RING_COLOR, FINISHED_GLYPH_COLOR = (88, 176, 112), (48, 150, 78)     # a finished episode's, CoD's tones

    @staticmethod
    def available(library):
        """A CoD library with the SHS HD art source: the tile masks and the popup's and dividers' bundle images."""
        try:
            if getattr(library, 'game_id', None) != 'cod' or library.shs_hd_art is None:
                return False
            names = set(library.shs_hd_art.namelist())
            return (all(library.shs_hd_resource(i) is not None for i in (TOP_MASK, BOTTOM_MASK, 32))
                    and all(BUNDLE + name in names for name in BUNDLE_IMAGES))
        except Exception:
            return False

    def raw(self, resource_id):
        return self.library.shs_hd_resource(resource_id)

    @lru_cache(maxsize=1)
    def strings(self):
        return MenuStrings.parse(self.library.android_asset(13))

    @lru_cache(maxsize=8)
    def bundle_image(self, name):
        data = self.library.shs_hd_art.read(BUNDLE + name)
        if b'CgBI' not in data[:16]:
            return pygame.image.load(BytesIO(data)).convert_alpha()
        from .cgbi import decode
        image = decode(data).convert('RGBA')
        return pygame.image.frombytes(image.tobytes(), image.size, 'RGBA').convert_alpha()

    @lru_cache(maxsize=1)
    def card_image(self):
        return recolor_border(self.bundle_image('popupBackground.png'), BORDER)

    def main_backdrop(self, height=1024):
        if self.title_look() is not None:           # (a Title Screen Look: the pickers show it too, as SHS HD's do)
            return super().main_backdrop(height)
        return title_backdrop(self.library, height)


class CodEpisodePicker(CodPickerStyle, HdEpisodePicker):
    """Play/Resume: SHS HD's tile grid of title-card previews, CoD's backdrop and buttons."""


class CodEpisodeList(CodPickerStyle, HdEpisodeList):
    """Episodes On Demand and Now Airing: SHS HD's list, CoD's colours."""
    TITLE_COLOR, BORDER_COLOR = (0, 0, 0), BORDER
    HEADER_COLOR = MEGA_HEADER_COLOR = BORDER
    ROW_COLORS, SELECTED_COLOR, SEPARATOR_COLOR = ((239, 243, 247), (255, 255, 255)), (181, 195, 236), (222, 222, 222)
    TEXT_ROW_COLOR, LIST_FILL = (0, 0, 0), (255, 255, 255)

    # -- the Claire Hart skin (Claire Hart UI's Everywhere: desktop_ch_ui.ChUi.of(library); owner, 2026-11-22) --------------
    # The list (Now Airing, Episodes On Demand, Data Management's tick lists; not the grid) in Classic's dress: its card is
    # the skinned CodPauseMenu's, the rows dark teal with Romic Bold in off-white, the category bands darker, the play /
    # pause icons and tick boxes gold, the buttons the Play Now pill, and the New Game / Continue and info cards
    # Classic's popup. The places and taps stay. `ui` is set for each frame (the setting may change between two).
    ui = None
    SKIN_TEXT = .9                                       # Romic Bold against Arial Rounded's points (it runs wider)
    SKIN_STYLE = dict(TEXT_COLOR=None, FOCUS_TEXT_COLOR=None, TEXT_ROW_COLOR=None, ICON_RING_COLOR=None,
                      ROW_COLORS=((13, 50, 45), (9, 41, 37)), SELECTED_COLOR=(28, 78, 68), SEPARATOR_COLOR=(4, 22, 20),
                      LIST_FILL=(9, 41, 37), HEADER_COLOR=(4, 26, 23), MEGA_HEADER_COLOR=(4, 26, 23),
                      PLAY_COLOR=(150, 105, 10), PAUSE_COLOR=(150, 105, 10))

    def skin(self):
        from .desktop_ch_ui import ChUi
        ui = ChUi.of(self.library)
        if ui is not self.ui:
            self.ui = ui
            self.__dict__.pop('_texts', None)           # (rendered text is kept by its words and colour, not its face)
            self.__dict__.pop('_card', None)
            for name in self.SKIN_STYLE:
                self.__dict__.pop(name, None)
            if ui is not None:
                colours = dict(TEXT_COLOR=ui.TEXT, FOCUS_TEXT_COLOR=ui.LIT, TEXT_ROW_COLOR=ui.TEXT, ICON_RING_COLOR=ui.GOLD)
                for name, value in self.SKIN_STYLE.items():
                    setattr(self, name, colours.get(name, value))
        if self.card is not None and hasattr(self.card, 'skin'):
            self.card.skin()
        return ui

    def draw(self, *, backdrop=True):
        self.skin()
        return super().draw(backdrop=backdrop)

    def mark_width(self, mark):
        if self.ui is None:
            return super().mark_width(mark)
        from .desktop_pause_hd import BADGE_PAD, BADGE_PX
        return self.font(BADGE_PX).size(mark)[0] / S + 2 * BADGE_PAD

    def draw_standard_mark(self, layer, x, y, mark='SD', color=None):
        """A row's tag; in the skin Options' badge (CodPauseMenu.row, HdPauseMenu.badge): gold, at its size, centred where
        the list's smaller tag is (`y` is that one's top, 18 points tall). Claire Hart's own dark green was near invisible
        on the dark rows (owner, g54, 2026-11-22: "make them match the Claire Hart tag in options")."""
        if self.ui is None:
            return super().draw_standard_mark(layer, x, y, mark, color)
        from .desktop_pause_hd import BADGE_HEIGHT, BADGE_PX
        color = self.ui.GOLD
        label = self.font(BADGE_PX).render(mark, True, color)
        width, height = self.mark_width(mark), BADGE_HEIGHT
        plate = pygame.Surface((round(width * S), round(height * S)), pygame.SRCALPHA)
        pygame.draw.rect(plate, (*color, 30), plate.get_rect(), border_radius=round(8 * S))
        pygame.draw.rect(plate, (*color, 200), plate.get_rect(), max(1, round(2 * S)), border_radius=round(8 * S))
        plate.blit(label, label.get_rect(center=plate.get_rect().center))
        layer.blit(plate, (round(x * S), round((y + 9 - height / 2) * S)))

    def font(self, points):
        if self.ui is not None:
            return self.ui.font(points * S * self.SKIN_TEXT)
        return super().font(points)

    def factor(self):
        return 1. if self.ui is not None else super().factor()

    def line_height(self, points):
        """In the skin, Romic's pitch (desktop_ch_ui.ChUi.pitch): its own line size is too tight (a row's airdate ran into its
        title)."""
        if self.ui is not None:
            return self.ui.pitch(points * S * self.SKIN_TEXT) / S
        return super().line_height(points)

    SKIN_CARD_GROW = (130, 90)                  # points Classic's popup is drawn wider and taller than CoD's card

    def draw_card(self, layer):
        """CoD's popup card (New Game / Continue, an episode's info, an alert); in the skin Classic's popup, grown round
        the card so its curved glass clears the tiles and text laid out for CoD's card."""
        if self.ui is None:
            return super().draw_card(layer)
        from .desktop_episode_picker import CARD
        gw, gh = self.SKIN_CARD_GROW
        left, top = self.card_top_left
        backing = self.ui.popup(((CARD[0] + gw) * S, (CARD[1] + gh) * S))
        for _ in range(2):                      # (twice: the glass denser, the list's rows less through it)
            layer.blit(backing, (round((left - gw / 2) * S), round((top - gh / 2) * S)))

    def draw_button(self, layer, x, y, orange=False, label=None, pressed=False):
        if self.ui is None:
            return super().draw_button(layer, x, y, orange=orange, label=label, pressed=pressed)
        from .desktop_episode_picker import BUTTON_SIZE
        width, height = BUTTON_SIZE
        pill = self.ui.pill((width * S, height * S), height * S / 57, 'pressed' if pressed else 'idle')
        layer.blit(pill, (round(x * S), round(y * S)))
        centre = (round((x + width / 2) * S), round((y + height / 2 - 1) * S))
        if label:
            self.ui.text(layer, label, 24 * S, self.ui.TEXT, centre)
        else:
            self.ui.arrow(layer, (centre[0] - 4 * S, centre[1]), S)
