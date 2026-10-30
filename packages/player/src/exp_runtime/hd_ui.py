"""Shared drawing helpers of the iOS HD menu screens (picker, main menu, menu windows).

Everything draws into a 2x canvas in frame points (768 x 1024), like the other HD renderers. Fonts are Arial Rounded MT
Bold, or Arial Bold when it is not installed (widths then differ by about 1%, `FALLBACK_WIDTH`).
"""
from functools import lru_cache
from io import BytesIO
import pygame

from .graphics import faded
from .hd_layout import HdLayouts, STRINGS_ID
from .menu import MenuStrings
from .vector_text import system_font_path

from .hd_scale import S
FRAME = (768, 1024)
BUNDLE = 'Payload/Surviving_HS.app/'
BLUE = (41, 104, 221)
BUTTON_SIZE = (156, 58)
DARK = (8, 12, 20)                      # the window's fill beside the frame without the backdrop
FALLBACK_WIDTH = 1.0104


def window_backdrop(collage, size):
    """The window around HD's 3:4 frame, at `size`: the faded collage (resource 10, at alpha 0.5 on a dark green-grey)
    scaled to cover the whole window and centred, as the main menu shows it. Used wherever the frame does not fill the
    window: beside it, above and below it, and beyond the side panels."""
    width, height = size
    surface = pygame.Surface((width, height)).convert()
    surface.fill((34, 36, 32))
    factor = max(width / collage.get_width(), height / collage.get_height())
    art = pygame.transform.smoothscale(collage, (round(collage.get_width() * factor), round(collage.get_height() * factor)))
    art = faded(art, 128)
    surface.blit(art, art.get_rect(center=(width // 2, height // 2)))
    return surface


class HdUi:
    def __init__(self, library):
        self.library = library
        self.layouts = HdLayouts(library)

    # ------------------------------------------------------------ resources

    @lru_cache(maxsize=16)
    def font(self, points):
        return pygame.font.Font(system_font_path('arial-rounded', self.library), round(points * S))

    @lru_cache(maxsize=1)
    def strings(self):
        return MenuStrings.parse(self.library.hd_raw_resource(STRINGS_ID))

    @lru_cache(maxsize=16)
    def resource(self, resource_id):
        """An HD app resource that is a plain PNG (the main menu's art, the boot screen's)."""
        data = self.library.hd_raw_resource(resource_id)
        if b'CgBI' in data[:16]:
            from .cgbi import decode
            image = decode(data).convert('RGBA')
            return pygame.image.frombytes(image.tobytes(), image.size, 'RGBA').convert_alpha()
        return pygame.image.load(BytesIO(data)).convert_alpha()

    @lru_cache(maxsize=8)
    def bundle_image(self, name):
        """A loose image of the app bundle (often Apple's CgBI PNG variant)."""
        data = self.library.hd_ipa.read(BUNDLE + name)
        if b'CgBI' not in data[:16]:
            return pygame.image.load(BytesIO(data)).convert_alpha()
        from .cgbi import decode
        image = decode(data).convert('RGBA')
        return pygame.image.frombytes(image.tobytes(), image.size, 'RGBA').convert_alpha()

    def scaled(self, surface, factor):
        size = max(1, round(surface.get_width() * factor)), max(1, round(surface.get_height() * factor))
        return pygame.transform.smoothscale(surface, size)

    # ------------------------------------------------------------ the main menu's backdrop

    @lru_cache(maxsize=1)
    def main_layers(self):
        """The main menu's four art layers as (surface, center in points): wood (resource 6), photo (9), ribbon (8,
        tilted 6 degrees) and title (7). `setAppMode(101)`: the wood is scaled 1.25 at the frame's center, the photo
        1.0 there, the ribbon and title 1.25 at (384, 212) and (384, 218). Fitted to `main menu/IMG_0124` to a mean
        colour error of 1.4 / 255 over the top 700 points."""
        def layer(resource_id, factor, angle=0):
            image = self.scaled(self.resource(resource_id), factor * S)
            return pygame.transform.rotate(image, angle) if angle else image
        return [(layer(6, 1.25), (384, 512)), (layer(9, 1.0), (384, 512)),
                (layer(8, 1.25, 6), (384, 212)), (layer(7, 1.25), (384, 218))]

    @lru_cache(maxsize=1)
    def main_backdrop(self):
        surface = pygame.Surface((FRAME[0] * S, FRAME[1] * S)).convert()
        for image, (cx, cy) in self.main_layers():
            surface.blit(image, image.get_rect(center=(round(cx * S), round(cy * S))))
        return surface

    # ------------------------------------------------------------ text

    _factor = None

    def factor(self):
        # Looked up once: the search scans the library's fonts folder, and text is measured many times a frame.
        if self._factor is None:
            path = (system_font_path('arial-rounded', self.library) or '').lower()
            self._factor = 1. if 'round' in path else FALLBACK_WIDTH
        return self._factor

    def measure(self, text, points):
        return self.font(points).size(text)[0] / S * self.factor()

    def wrap(self, text, points, width, lines=None):
        """Lines of `text` wrapped at `width` points (explicit newlines break); more than `lines` end in an ellipsis."""
        font, out = self.font(points), []
        for paragraph in text.split('\n'):
            current = ''
            for word in paragraph.split(' '):
                trial = f'{current} {word}' if current else word
                if current and font.size(trial)[0] / S * self.factor() > width:
                    out.append(current)
                    current = word
                else:
                    current = trial
            out.append(current)
        if lines is not None and len(out) > lines:
            last = ' '.join(out[lines - 1:])
            while last and font.size(last + '…')[0] / S * self.factor() > width:
                last = last[:-1]
            out = out[:lines - 1] + [last.rstrip() + '…']
        return out

    def text(self, layer, text, points, x, y, *, color=(255, 255, 255), outline=True, width=None, alpha=255):
        """Text with its top-left at (x, y) points. With `outline` a dark outline and soft shadow (tile captions);
        `width` centers it in that width."""
        # Rendered once each: the picker draws every tile's outlined caption each frame (nine renders and a fade a
        # caption took ~2 ms each on a phone).
        key = (text, points, color, outline, alpha)
        cache = self.__dict__.setdefault('_texts', {})
        rendered = cache.get(key)
        if rendered is None:
            if len(cache) > 400:
                cache.clear()
            rendered = cache[key] = self._render_text(text, points, color, outline, alpha)
        if width is not None:
            x += (width - (rendered[0].get_width() - (6 * S if outline else 0)) / S) / 2
        if outline:
            shade, plate = rendered
            layer.blit(shade, (round(x * S) - 3 * S, round(y * S) - 3 * S))
            layer.blit(plate, (round(x * S) - 3 * S, round(y * S) - 3 * S))
            return
        layer.blit(rendered[0], (round(x * S), round(y * S)))

    def _render_text(self, text, points, color, outline, alpha):
        font = self.font(points)
        surface = font.render(text, True, color)
        if outline:
            dark = font.render(text, True, (20, 20, 30))
            plate = pygame.Surface((surface.get_width() + 6 * S, surface.get_height() + 6 * S), pygame.SRCALPHA)
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)):
                plate.blit(dark, (3 * S + dx * S, 3 * S + dy * S))
            shade = pygame.Surface(plate.get_size(), pygame.SRCALPHA)
            shade.blit(dark, (3 * S + 2 * S, 3 * S + 2 * S))
            shade = faded(shade, 110)
            plate.blit(surface, (3 * S, 3 * S))
            return shade, plate
        return (faded(surface, alpha) if alpha < 255 else surface,)

    def centered_line(self, layer, text, points, center_x, center_y, color=BLUE):
        """One line of text centered on a point (points)."""
        surface = self.font(points).render(text, True, color)
        layer.blit(surface, surface.get_rect(center=(round(center_x * S), round(center_y * S))))

    # ------------------------------------------------------------ controls

    def draw_button(self, layer, x, y, orange=False, label=None, pressed=False):
        """A footer button: layout 70/71 (blue) or 72/73 (orange), 156 x 58, with an arrow (pack 32 frame 12) or a label."""
        layout = (73 if pressed else 72) if orange else (71 if pressed else 70)
        for _, node, visible, (nx, ny, w, h) in self.layouts.nodes(layout, size=(BUTTON_SIZE[0] / 2, BUTTON_SIZE[1] / 2)):
            if node.kind != 1 or w <= 0 or h <= 0:
                continue
            pack = self.layouts.pack_for(*node.payload)
            image = self.layouts.frame(pack, node.payload[1]) if pack else None
            if image is not None:
                layer.blit(pygame.transform.smoothscale(image, (round(w * 2 * S), round(h * 2 * S))),
                           (round((x + nx * 2) * S), round((y + ny * 2) * S)))
        center = ((x + BUTTON_SIZE[0] / 2) * S, (y + BUTTON_SIZE[1] / 2) * S)
        if label:
            text = self.font(28).render(label, True, (255, 255, 255))
            layer.blit(text, text.get_rect(center=(center[0], center[1] - 2 * S)))
        else:
            arrow = self.layouts.frame(32, 12)
            if arrow is not None:
                arrow = pygame.transform.smoothscale(arrow, (arrow.get_width() * S, arrow.get_height() * S))
                layer.blit(arrow, arrow.get_rect(center=(center[0], center[1] - 2 * S)))

    # ------------------------------------------------------------ window furniture

    backdrop_enabled = staticmethod(lambda: True)      # the shell binds the player's "SHS HD Backdrop" switch

    def side_art(self, size):
        """What HD shows beside its 3:4 frame on a wider window: the faded collage (resource 10) on dark, or with the
        "SHS HD Backdrop" switch off, the dark fill alone."""
        return self.side_surface(size, self.backdrop_enabled())

    @lru_cache(maxsize=4)
    def side_surface(self, size, enabled):
        if enabled:
            return window_backdrop(self.resource(10), size)
        surface = pygame.Surface(size).convert()
        surface.fill(DARK)
        return surface

    def draw_prompt(self, canvas, title, text, labels):
        """The busy card, taller, with a footer button per label (left to right, the last orange as a Yes is); returns
        each button's rect in points."""
        width, height = 600, 320
        left, top = (FRAME[0] - width) // 2, (FRAME[1] - height) // 2
        card = pygame.Surface((width * S, height * S), pygame.SRCALPHA)
        pygame.draw.rect(card, (20, 24, 40, 235), card.get_rect(), border_radius=24 * S)
        pygame.draw.rect(card, (*BLUE, 255), card.get_rect(), 3 * S, border_radius=24 * S)
        canvas.blit(card, (left * S, top * S))
        self.text(canvas, title, 36, 0, top + 26, outline=False, width=FRAME[0])
        for index, line in enumerate(self.wrap(text, 24, width - 60, 4)):
            self.text(canvas, line, 24, 0, top + 92 + index * 30, outline=False, width=FRAME[0])
        rects, gap = [], 24
        x = (FRAME[0] - len(labels) * BUTTON_SIZE[0] - (len(labels) - 1) * gap) // 2
        for index, label in enumerate(labels):
            rect = pygame.Rect(x, top + height - BUTTON_SIZE[1] - 26, *BUTTON_SIZE)
            self.draw_button(canvas, rect.x, rect.y, orange=index == len(labels) - 1, label=label)
            rects.append(rect)
            x += BUTTON_SIZE[0] + gap
        return rects

    def draw_busy(self, canvas, title, text):
        """A dim card with a title and a line of text over the screen (a running import, or a message)."""
        card = pygame.Surface((560 * S, 220 * S), pygame.SRCALPHA)
        pygame.draw.rect(card, (20, 24, 40, 225), card.get_rect(), border_radius=24 * S)
        pygame.draw.rect(card, (*BLUE, 255), card.get_rect(), 3 * S, border_radius=24 * S)
        canvas.blit(card, ((FRAME[0] - 560) // 2 * S, (FRAME[1] - 220) // 2 * S))
        self.text(canvas, title, 36, 0, (FRAME[1] - 220) // 2 + 24, outline=False, width=FRAME[0])
        for index, line in enumerate(self.wrap(text, 24, 500, 3)):
            self.text(canvas, line, 24, 0, (FRAME[1] - 220) // 2 + 90 + index * 30, outline=False, width=FRAME[0])
