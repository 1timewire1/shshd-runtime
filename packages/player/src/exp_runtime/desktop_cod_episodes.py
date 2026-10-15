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

import pygame

from .desktop_cod_main import title_layer
from .desktop_cod_menu import CodButtons
from .desktop_episode_list_hd import HdEpisodeList
from .desktop_episode_picker import BOTTOM_MASK, TOP_MASK, HdEpisodePicker
from .hd_ui import BUNDLE
from .menu import MenuStrings

BORDER = (85, 95, 176)
HD_BORDER = (117, 137, 255)
BUNDLE_IMAGES = ('popupBackground.png', 'VT_divider.png')


def recolor_border(image, color):
    """`image` (SHS HD's popup card) with its flat border colour, and the antialiased blend from it to white, moved to
    `color`. Each pixel's place on the white-to-border blend is read from its green channel."""
    surface = image.copy()
    span = 255 - HD_BORDER[1]
    pixels = pygame.PixelArray(surface)
    cache = {}
    for x in range(surface.get_width()):
        for y in range(surface.get_height()):
            mapped = surface.unmap_rgb(pixels[x, y])
            r, g, b, a = mapped
            if a == 0 or not (b > 240 and r < 250):
                continue
            key = (g, a)
            if key not in cache:
                t = max(0.0, min(1.0, (255 - g) / span))
                cache[key] = surface.map_rgb((round(255 + (color[0] - 255) * t), round(255 + (color[1] - 255) * t),
                                              round(255 + (color[2] - 255) * t), a))
            pixels[x, y] = cache[key]
    del pixels
    return surface


class CodPickerStyle(CodButtons):
    TEXT_COLOR = (0, 0, 0)
    NEW_GAME, CONTINUE, RESTORE = 19, 26, 194
    RESTORE_TITLE, RESTORE_TEXT = 188, 189
    # Pack 16's play / pause icon (frames 101 / 96) at the frames' own alphas; the info button takes them too.
    ICON_RING_COLOR, PLAY_COLOR, PAUSE_COLOR = (102, 120, 213), (60, 85, 205), (50, 70, 161)
    RING_ALPHA, PLAY_ALPHA, PAUSE_ALPHA = 128, 102, 128

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

    def main_backdrop(self):
        return title_layer(self.library)


class CodEpisodePicker(CodPickerStyle, HdEpisodePicker):
    """Play/Resume: SHS HD's tile grid of title-card previews, CoD's backdrop and buttons."""


class CodEpisodeList(CodPickerStyle, HdEpisodeList):
    """Episodes On Demand and Now Airing: SHS HD's list, CoD's colours."""
    TITLE_COLOR, BORDER_COLOR = (0, 0, 0), BORDER
    HEADER_COLOR = MEGA_HEADER_COLOR = BORDER
    ROW_COLORS, SELECTED_COLOR, SEPARATOR_COLOR = ((239, 243, 247), (255, 255, 255)), (181, 195, 236), (222, 222, 222)
    TEXT_ROW_COLOR, LIST_FILL = (0, 0, 0), (255, 255, 255)
