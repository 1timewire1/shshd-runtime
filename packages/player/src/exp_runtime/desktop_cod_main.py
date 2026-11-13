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

from . import graphics as pygame

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




# shshd-runtime (General's Aspect Ratio, owner 2026-11-12: mock-up E2, revised). At 2:3 the painting is shown whole at
# the frame's width, the buttons where the device has them (its Play/Resume at CoD point 346), as the iPhone app shows
# it (owner's iPad photo); taller, the painting grows towards the widest the logo allows, most of the added height is
# its sky continued above it (its top tenth stretched, its edge faded in) and a quarter black below, the brick wall
# fading into it; the buttons rise a tenth of that height above the bottom, as SHS HD's (HdUi.buttons_raise).
FULL_HEIGHT = 1152                                  # 2:3: the 320 x 480 painting whole at the frame's width
DEVICE_SHIFT = PLAY_TOP[0] * FRAME[0] / 320 - PLAY_TOP[1]       # 77.4: the buttons' move down at 2:3, as on the device
BUTTONS_RAISE = 0.1                                 # of the height past 2:3 (SHS HD's share)
BLACK_SHARE = 0.25                                  # of the height past 2:3 that is black below the painting
GROW_MAX, GROW_AT = 0.98 / 0.93, 1707               # the logo is 93% of the painting's width; fully grown at 20:9
SKY_BAND, SKY_FADE = 0.10, 60                       # the painting's top share stretched up, its edge's fade (points)
FADE_SHARE, FADE_PER_BLACK = 0.28, 1.5              # the wall's fade to black: at most this share of the painting


def buttons_shift(height):
    """Points the buttons move down in a frame `height` points tall: to the device's place at 2:3, then with the frame
    less a tenth of what it adds."""
    if height <= FRAME[1]:
        return 0.
    if height <= FULL_HEIGHT:
        return (height - FRAME[1]) * DEVICE_SHIFT / (FULL_HEIGHT - FRAME[1])
    return DEVICE_SHIFT + (height - FULL_HEIGHT) * (1 - BUTTONS_RAISE)


def painting(library):
    image = ImagePack.parse(read_ui(library, TITLE_ART)).images[0]
    return pygame.image.frombytes(image.pixels, (image.width, image.height), image.mode).convert_alpha()


@lru_cache(maxsize=2)
def title_backdrop(library, height):
    """The title painting in a frame `height` points tall at 2x (title_layer at HD's 1024)."""
    if height <= FRAME[1]:
        return title_layer(library)
    art = painting(library)
    beyond = max(0, height - FULL_HEIGHT)
    k = FRAME[0] / art.get_width() * (1 + (GROW_MAX - 1) * min(1., beyond / (GROW_AT - FULL_HEIGHT)))
    size = (round(art.get_width() * k * S), round(art.get_height() * k * S))
    picture = pygame.transform.smoothscale(art, size)
    top = (PLAY_TOP[1] + buttons_shift(height) - PLAY_TOP[0] * k - beyond * BLACK_SHARE) * S
    left = (FRAME[0] * S - size[0]) / 2
    layer = pygame.Surface((FRAME[0] * S, round(height * S))).convert()
    layer.fill((0, 0, 0))
    if top > 0:
        band = picture.subsurface((0, 0, size[0], max(1, round(size[1] * SKY_BAND))))
        layer.blit(pygame.transform.smoothscale(band, (size[0], round(band.get_height() + top))), (round(left), 0))
        picture = picture.copy()
        fade = round(SKY_FADE * S)
        for y in range(fade):           # the painting's top edge faded into the sky above it
            picture.fill((255, 255, 255, round(255 * y / fade)), (0, y, size[0], 1), special_flags=pygame.BLEND_RGBA_MULT)
    layer.blit(picture, (round(left), round(top)))
    bottom = top + size[1]
    black = layer.get_height() - bottom
    if black > 1:
        length = min(size[1] * FADE_SHARE, black * FADE_PER_BLACK)
        shade = pygame.Surface((layer.get_width(), round(length) + 1), pygame.SRCALPHA)
        for y in range(shade.get_height()):
            shade.fill((0, 0, 0, round(255 * (y / max(1, shade.get_height() - 1)) ** 1.2)), (0, y, shade.get_width(), 1))
        layer.blit(shade, (0, round(bottom - length)))
        layer.fill((0, 0, 0), (0, round(bottom), layer.get_width(), layer.get_height()))
    return layer


@lru_cache(maxsize=2)
def hd_collage(library):
    """SHS HD's main-menu collage (resource 10) from the art source, or None."""
    try:
        data = library.shs_hd_resource(10)
        return _image(data) if data is not None else None
    except (AttributeError, pygame.error, ValueError):
        return None


def addon_backdrop(library, size):
    """The portrait addon's backdrop covering `size`, its middle kept, or None without the addon."""
    from .games import GAMES
    addon = getattr(GAMES.get(getattr(library, 'game_id', None)), 'PORTRAIT_ADDON', None)
    found = library.addon(addon[0]) if addon is not None and hasattr(library, 'addon') else None
    if found is None:
        return None
    try:
        image = _image(found[1].read(library.portrait_addon_map(addon)['backdrop']))
    except (KeyError, pygame.error, ValueError):
        return None
    factor = max(size[0] / image.get_width(), size[1] / image.get_height())
    scaled = pygame.transform.smoothscale(image, (round(image.get_width() * factor), round(image.get_height() * factor)))
    surface = pygame.Surface(size).convert()
    surface.blit(scaled, ((size[0] - scaled.get_width()) // 2, (size[1] - scaled.get_height()) // 2))
    return surface


@lru_cache(maxsize=4)
def side_backdrop(library, size, enabled, ch_enabled=False):
    """What fills the window beside the frame: the portrait addon's backdrop when `ch_enabled`, else SHS HD's faded collage
    when `enabled` and available (as SHS HD's menus and episodes show it), else the dark fill."""
    backdrop = addon_backdrop(library, size) if ch_enabled else None
    if backdrop is not None:
        return backdrop
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
    INFO_FRAMES = (14, 15)              # CoD's own at rest / pressed (through INFO_SWAP), unchanged
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

    def main_layout(self, height=FRAME[1]):
        """The painting in a frame `height` points tall (title_backdrop), one frame-sized layer."""
        return [(title_backdrop(self.library, height), (384, height / 2))]

    @property
    def extra(self):
        """Points the buttons move down: to the device's place at 2:3, then on (buttons_shift)."""
        return buttons_shift(self.height)

    def draw_photo(self, layer):
        pass

    def draw_ribbon_title(self, layer):
        pass

    def side_art(self, size):
        """Beside the frame: SHS HD's collage, or the dark fill (owner, 2026-10-14: never the painting stretched)."""
        return side_backdrop(self.library, size, self.backdrop_enabled(), self.ch_backdrop_enabled())

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
    grows = True
    height = FRAME[1]               # the menu frame's (the shell sets it): the grey fills it, the logo centred

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
        size = (FRAME[0] * S, round(self.height * S))
        if self.canvas.get_size() != size:
            self.canvas = pygame.Surface(size).convert()
        self.canvas.fill((105, 105, 105))         # Default@2x.png's own grey
        image = self.launch_image()
        if image is not None:
            self.canvas.blit(image, (0, round((self.height - FRAME[1]) / 2 * S)))
        return self.canvas

    def draw_flash(self, seconds):
        return self.draw_loading(1.0)

    @staticmethod
    def flash_done(seconds):
        return True
