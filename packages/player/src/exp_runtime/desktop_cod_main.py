"""Cause of Death's title screen and launch screen, in SHS HD's layout (owner's choice, 2026-10-14).

CoD's main menu is SHS HD's (`desktop_main_hd.HdMainMenu`): the same layout 74 (its wedge, Play/Resume, Now Airing,
Episodes On Demand, More EA Games, the gear and the info button; SHS HD's is exactly twice CoD's), the same pack of
button art (CoD's 272 is SHS HD's 315 at 1x, frames 14 / 15, the info button's two states, swapped) and the same
label fonts (CoD's 532 / 533 are SHS HD's 593 / 594 at 1x). What differs is the picture behind them: CoD's title
(resource 6) is one 320 x 480 painting (sky, Natara and Mal, the logo, the brick wall; resources 7-9 are empty), not
SHS HD's four animated layers. Here it fills the 3:4 frame's width (2.4x, against the buttons' 2x), placed so its
rows meet the button group where they do on the device (IMG_0464): the logo stays just above Play/Resume, and the
taller picture loses 77 points of sky and 51 of the brick floor. Being one layer, the entrance is the buttons
sliding in alone (owner's choice). The labels are CoD's own strings (118 Play/Resume, 119 Now Airing, 83 Episodes On Demand, 227 More EA Games).

With the SHS HD art source the buttons and labels are SHS HD's 2x art; without it, CoD's own at twice its size.

The launch screen is CoD's own `Default@2x.png` (the EA logo on flat grey, 640 x 960) fitted to the frame's height
and centred on the same grey, so the whole ring stays in view as on the device, under the "Play with sound?"
question (IMG_0473).
"""
from functools import lru_cache
from io import BytesIO

import pygame

from .desktop_main_hd import HdMainMenu
from .hd_layout import BankLayouts
from .hd_ui import DARK, FRAME, S, HdUi, window_backdrop
from .menu import MenuFont, MenuStrings
from .ui_assets import ImagePack, read_ui

TITLE_ART = 6
BUTTON_PACK, HD_BUTTON_PACK = 272, 315
INFO_SWAP = {14: 15, 15: 14}            # CoD's info button states sit in SHS HD's pack the other way round
LABELS = (118, 119, 83, 227)
FONTS, HD_FONTS = (532, 533), (593, 594)
PLAY_TOP = (346, 753)                   # Play/Resume's top edge: CoD points on the device, frame points here


def _image(data):
    if b'CgBI' in data[:16]:
        from .cgbi import decode
        image = decode(data).convert('RGBA')
        return pygame.image.frombytes(image.tobytes(), image.size, 'RGBA').convert_alpha()
    return pygame.image.load(BytesIO(data)).convert_alpha()


def fit(image, size):
    """`image` scaled evenly to fit inside `size` (pixels), centred, the rest left transparent."""
    width, height = size
    factor = min(width / image.get_width(), height / image.get_height())
    scaled = pygame.transform.smoothscale(image, (round(image.get_width() * factor), round(image.get_height() * factor)))
    surface = pygame.Surface(size, pygame.SRCALPHA).convert_alpha()
    surface.blit(scaled, ((width - scaled.get_width()) // 2, (height - scaled.get_height()) // 2))
    return surface


@lru_cache(maxsize=2)
def title_layer(library):
    """The title painting as a frame-sized layer at 2x: the frame's width, placed so the device's Play/Resume top
    (CoD point 346 on IMG_0464) falls on SHS HD's (frame point 753). The main menu's backdrop and the pickers'."""
    image = ImagePack.parse(read_ui(library, TITLE_ART)).images[0]
    art = pygame.image.frombytes(image.pixels, (image.width, image.height), image.mode).convert_alpha()
    factor = FRAME[0] / art.get_width()
    scaled = pygame.transform.smoothscale(art, (FRAME[0] * S, round(art.get_height() * factor * S)))
    layer = pygame.Surface((FRAME[0] * S, FRAME[1] * S)).convert()
    layer.blit(scaled, (0, round((PLAY_TOP[1] - factor * PLAY_TOP[0]) * S)))
    return layer




@lru_cache(maxsize=2)
def hd_collage(library):
    """SHS HD's main-menu collage (resource 10) from the art source, or None."""
    try:
        data = library.shs_hd_resource(10)
        return _image(data) if data is not None else None
    except (AttributeError, pygame.error, ValueError):
        return None


@lru_cache(maxsize=4)
def side_backdrop(library, size, enabled):
    """What fills the window beside the frame: SHS HD's faded collage when `enabled` and available (as SHS HD's
    menus and episodes show it), else the dark fill."""
    collage = hd_collage(library) if enabled else None
    if collage is not None:
        return window_backdrop(collage, size)
    surface = pygame.Surface(size).convert()
    surface.fill(DARK)
    return surface


class CodButtonLayouts:
    """What HdMainMenu reads from its layouts: CoD's own layout bank (one unit per point, as SHS HD's units are half
    points, so the numbers agree) and the button pack, served at SHS HD's size."""

    def __init__(self, library, bank):
        self.library, self._layouts = library, BankLayouts(bank)

    def bank(self):
        return self._layouts.bank()

    def nodes(self, *args, **kwargs):
        return self._layouts.nodes(*args, **kwargs)

    @staticmethod
    def pack_for(slot, theme=None):
        return BUTTON_PACK if slot == 5 else None

    @lru_cache(maxsize=32)
    def frame(self, pack, index):
        if pack not in (BUTTON_PACK, HD_BUTTON_PACK):
            return None
        hd = self.library.shs_hd_resource(HD_BUTTON_PACK)
        if hd is not None:
            image = ImagePack.parse(hd).images[INFO_SWAP.get(index, index)]
            return pygame.image.frombytes(image.pixels, (image.width, image.height), image.mode).convert_alpha()
        image = ImagePack.parse(read_ui(self.library, BUTTON_PACK)).images[index]
        surface = pygame.image.frombytes(image.pixels, (image.width, image.height), image.mode).convert_alpha()
        return pygame.transform.smoothscale(surface, (image.width * 2, image.height * 2))


class CodMainMenu(HdMainMenu):
    LABELS = LABELS

    def __init__(self, library, bank):
        super().__init__(library)
        self.layouts = CodButtonLayouts(library, bank)

    @staticmethod
    def available(library):
        return getattr(library, 'game_id', None) == 'cod'

    @lru_cache(maxsize=1)
    def strings(self):
        return MenuStrings.parse(self.library.android_asset(13))

    @lru_cache(maxsize=1)
    def main_layers(self):
        # One layer, frame-sized; HdMainMenu blits the first layer centred.
        return [(title_layer(self.library), (384, 512))]

    def draw_photo(self, layer):
        pass

    def draw_ribbon_title(self, layer):
        pass

    def side_art(self, size):
        """Beside the frame: SHS HD's collage, or the dark fill (owner, 2026-10-14: never the painting stretched)."""
        return side_backdrop(self.library, size, self.backdrop_enabled())

    def glyph_fonts(self):
        if self.fonts is None:
            hd = [self.library.shs_hd_resource(i) for i in HD_FONTS]
            if all(data is not None for data in hd):
                self.fonts, self.font_scale = [MenuFont.parse(data) for data in hd], 1
            else:
                self.fonts, self.font_scale = [MenuFont.parse(read_ui(self.library, i)) for i in FONTS], 2
        return self.fonts

    @lru_cache(maxsize=16)
    def label(self, text, variant):
        image = super().label(text, variant)
        factor = getattr(self, 'font_scale', 1)
        if factor == 1:
            return image
        return pygame.transform.smoothscale(image, (image.get_width() * factor, image.get_height() * factor))


class CodBootScreen(HdUi):
    """The launch screen: CoD's EA logo (`Default@2x.png`) fitted to the frame on its grey. There is no EA flash."""

    def __init__(self, library):
        super().__init__(library)
        self.canvas = pygame.Surface((FRAME[0] * S, FRAME[1] * S)).convert()

    @lru_cache(maxsize=1)
    def launch_image(self):
        library = self.library
        for name in ('Default@2x.png', 'Default.png'):
            try:
                return fit(_image(library.package.read(library.app_root + name)), (FRAME[0] * S, FRAME[1] * S))
            except (KeyError, AttributeError, pygame.error, ValueError):
                continue
        return None

    def draw_loading(self, phase):
        self.canvas.fill((105, 105, 105))         # Default@2x.png's own grey
        image = self.launch_image()
        if image is not None:
            self.canvas.blit(image, (0, 0))
        return self.canvas

    def draw_flash(self, seconds):
        return self.draw_loading(1.0)

    @staticmethod
    def flash_done(seconds):
        return True
