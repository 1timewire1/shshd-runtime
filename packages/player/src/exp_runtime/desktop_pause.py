"""Shared native system-menu skin for an episode's pause menu."""
from . import graphics as pygame
from .animation_curves import ease_in_out
from .fonts import TextStyle
from .menu import MenuStrings
from .ui_assets import LayoutBank, Rect, read_ui


PAUSE_OPEN_MS = 400
SEPIA = ((.393, .769, .189), (.349, .686, .168), (.272, .534, .131))
PAUSE_TINT = (184, 131, 36, 110)  # Android 0008b900, packed ccColor4B 0x6e2483b8.


def pause_scale(elapsed_ms):
    """Native system-menu zoom: 0.001 -> 1, UIKit ease-in/out, 400ms."""
    return .001 + .999 * ease_in_out(elapsed_ms / PAUSE_OPEN_MS)


def draw_pause_gear(target, art, *, scale=1):
    image = art.frame(126, 50 if getattr(art, 'gear_pressed', False) else 49)
    if scale != 1:
        image = pygame.transform.smoothscale(image, (round(image.get_width() * scale),
                                                      round(image.get_height() * scale)))
    target.blit(image, (0, round(408 * scale)))


class PauseRenderer:
    def __init__(self, library, text, art):
        self.bank = LayoutBank.parse(read_ui(library, 14))
        self.strings = MenuStrings.load(library)
        self.text, self.art = text, art
        self.ios = getattr(library, 'kind', 'apk') == 'ipa'
        self.background = None
        self.canvas = pygame.Surface((320, 480), pygame.SRCALPHA).convert_alpha()
        self.dimmer = self.canvas.copy()
        self.dimmer.fill(PAUSE_TINT)

    def label(self, text, rect, name, size, *, center=False):
        layout = self.text.layout(name, text, rect.width, TextStyle(size, 0, (41, 104, 221)))
        left, top, right, bottom = layout.ink_bounds
        x = rect.x + (rect.width - (right - left)) / 2 - left if center else rect.x
        self.text.draw_layout(self.canvas, name, layout, x,
                              rect.y + (rect.height - (bottom - top)) / 2 - top)

    def layout(self, index, bounds, *, frames=None):
        for node, rect in self.bank.walk(index, bounds):
            if node.kind != 1 or rect.width <= 0 or rect.height <= 0:
                continue
            slot, frame = node.payload
            if frames is not None and frame not in frames:
                continue
            image = self.art.frame({0: 126, 3: 16}[slot], frame)
            self.canvas.blit(pygame.transform.scale(image, (rect.width, rect.height)), (rect.x, rect.y))

    def draw(self, target, *, application=True, main_menu=True, pressed=None,
             elapsed_ms=PAUSE_OPEN_MS, closing=False, entries=None, title=None, extra_entries=(),
             row_colors=None):
        if entries is None:
            entries = [(self.strings[21], ('resume',))]
            if application:
                entries += [(self.strings[11], ('pause_page', 'options')),
                            (self.strings[128], ('pause_page', 'help'))]
            else:
                # The standalone story viewer has no application settings pages.
                entries += [('Save', ('save',)), ('Load', ('load',))]
            if main_menu:
                entries.append((self.strings[10], ('main_menu',)))
            entries.extend(extra_entries)
        # SHSWidgetMenu::solveMetrics centers the system menu in 480 pixels;
        # UIKit heightForRowAtIndexPath returns 44 for these ordinary rows.
        header, footer = self.bank.layouts[33].height, self.bank.layouts[36].height
        top = (480 - header - 44 * len(entries) - footer) // 2
        self.canvas.fill((0, 0, 0, 0))
        self.layout(33, Rect(9, top, 302, header))
        heading = self.bank.rectangle(33, 2, Rect(9, top, 302, header))
        self.label(self.strings[9] if title is None else title, heading, 'ArialRoundedMTBold28', 28, center=True)
        buttons = []
        for index, (label, command) in enumerate(entries):
            y = top + header + index * 44
            row = Rect(9, y, 302, 44)
            # Native table cells occupy the 296px interior. Stretching their
            # art to the 302px outer box painted over its three-pixel borders.
            color = row_colors.get(command) if row_colors else None
            if color is not None:
                if pressed == command:
                    color = tuple(round(channel * .9) for channel in color)
            else:
                color = ((170, 225, 249, 243) if pressed == command else
                         (255, 242, 255, 239) if index % 2 else (239, 239, 249, 239))
            pygame.draw.rect(self.canvas, color, (12, y, 296, 44))
            edge = self.art.frame(16, 74)
            for x, source in ((9, 0), (308, 299)):
                border = edge.subsurface((source, 0, 3, 1))
                self.canvas.blit(pygame.transform.scale(border, (3, 44)), (x, y))
            image = self.art.frame(16, 75)
            self.canvas.blit(pygame.transform.scale(image, (296, 1)), (12, y))
            self.label(label, Rect(27, y + 3, 266, 38), 'ArialRoundedMTBold14', 14)
            buttons.append((pygame.Rect(row.x, row.y, row.width, row.height), command))
        self.layout(36, Rect(9, top + header + 44 * len(entries), 302, footer), frames={74, 79})
        if closing:
            pass
        elif self.ios:
            # SHS 0003b9a8 / CoD 00018728 capture once, transform RGB with
            # these double coefficients, truncate, and clamp each channel.
            if self.background is None:
                self.background = pygame.color_matrix(target, SEPIA)
            target.blit(self.background, (0, 0))
        else:
            target.blit(pygame.transform.smoothscale(self.dimmer, target.get_size()), (0, 0))
        scale = 1 - .99999 * ease_in_out(1 - elapsed_ms / PAUSE_OPEN_MS) if closing else pause_scale(elapsed_ms)
        size = tuple(max(1, round(length * scale)) for length in target.get_size())
        image = pygame.transform.smoothscale(self.canvas, size)
        target.blit(image, image.get_rect(center=target.get_rect().center))
        return buttons if elapsed_ms >= PAUSE_OPEN_MS and not closing else []
