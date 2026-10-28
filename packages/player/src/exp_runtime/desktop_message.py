"""Service 33's original blue message panel, bitmap text and reading gate."""
from dataclasses import replace
from functools import lru_cache

from . import graphics as pygame
from .desktop_pause import draw_pause_gear

from .fonts import TextStyle
from .menu import MenuStrings
from .ui_assets import Rect, read_ui


BLUE = (41, 104, 221)
# CoD's iOS panel (owner screenshot: "Cause of Death" / "Thanks for playing!") draws its title and message black.
INK = {'shs': BLUE, 'cod': (0, 0, 0)}


class MessageRenderer:
    # Drawn at story density (`scale` pixels per layout unit, Desktop's STORY_SCALE) and handed to Desktop as its
    # story layer, resampled once to the window as the dialogue is: text drawn at 1x and scaled twice looked soft.
    hd_layer = True

    def __init__(self, resources, text_renderer, artwork, scale=1):
        self.resources, self.text, self.art, self.scale = resources, text_renderer, artwork, scale
        # SRCALPHA: the background is composited separately by Desktop, at
        # real window resolution -- see desktop_dialogue.py's DialogueRenderer.
        self.canvas = pygame.Surface((320 * scale, 480 * scale), pygame.SRCALPHA).convert_alpha()
        self.pending_background = None
        self.pending_background_origin = (160, 240)
        self.footer_text = ''

    def cod(self):
        return getattr(self.resources.library, 'game_id', 'shs') == 'cod'

    def ink(self):
        return INK.get(getattr(self.resources.library, 'game_id', 'shs'), BLUE)

    @lru_cache(maxsize=1)
    def strings(self):
        return MenuStrings.load(self.resources.library)

    @lru_cache(maxsize=8)
    def layout_image(self, index, width, height):
        layer = pygame.Surface((width, height), pygame.SRCALPHA).convert_alpha()
        bank = self.resources.dialogue_layout().bank
        for number, (node, rect) in enumerate(bank.walk(index, Rect(0, 0, width, height)), 1):
            # Layout 24's headers/footer lie outside the body texture. They
            # are rendered as separate sprites by 000abd0c, not stretched in.
            if index == 24 and number > 5:
                continue
            if node.kind == 1 and node.flags & 16 and rect.width > 0 and rect.height > 0:
                slot, frame = node.payload
                image = self.art.frame({0: 126, 2: 204}[slot], frame)
                layer.blit(pygame.transform.scale(image, (rect.width, rect.height)), (rect.x, rect.y))
        return layer

    @lru_cache(maxsize=16)
    def panel(self, title, text):
        bank = self.resources.dialogue_layout().bank
        root = bank.layouts[24]
        builtin = self.resources.record['episode_id'] == 0
        if builtin:
            # 000abd0c explicitly uses width-40 for episode ID zero,
            # including the built-in Football Star / Football Season story.
            height = root.width - 40
        else:
            body_rect = bank.rectangle(24, 24)
            measure = self.text.layout('ArialRoundedMTBold14', text, body_rect.width,
                                       TextStyle(14, 5, self.ink()))
            # 00058a54 expands the root to fit node 24, with its original
            # minimum. The unused legacy-font padding read is unresolved;
            # zero padding is used here (see STORY_SERVICES.md).
            requested = int(measure.height + 1)
            requested += requested % 2
            height = max(root.height, requested + root.height - body_rect.height)
        width = root.width
        top = 240 - height / 2
        k = self.scale
        layer = pygame.Surface((320, 480), pygame.SRCALPHA).convert_alpha()
        layer.blit(self.layout_image(24, width, height), (160 - width // 2, round(top)))
        header = bank.layouts[15]
        header_top = top - header.height + 2
        layer.blit(self.layout_image(15, header.width, header.height),
                   (160 - header.width // 2, round(header_top)))
        footer = bank.layouts[25]
        footer_top = 240 + height / 2 - 2
        layer.blit(pygame.transform.flip(self.layout_image(25, footer.width, footer.height), False, True),
                   (160 - footer.width // 2, round(footer_top)))
        if k != 1:
            layer = pygame.transform.smoothscale(layer, (320 * k, 480 * k))

        heading = self.text.layout('ArialRoundedMTBold20', title, 2**31, TextStyle(10, 7, self.ink()))
        scale = 1 if len(title) < 31 else .88
        # Alignment 10: each line centered; preserve the BM node's downward
        # line origin and atlas overhang rather than centering the ink bounds.
        shifts = {i: (heading.width - line.width) / 2 for line in heading.lines
                  for i in range(line.start, line.end)}
        heading = replace(heading, glyphs=tuple(replace(g, x=g.x + shifts[g.index]) for g in heading.glyphs))
        self.text.draw_layout(layer, 'ArialRoundedMTBold20', heading,
                              (160 - heading.width * scale / 2) * k,
                              (header_top + header.height / 2 + heading.height * scale / 2) * k, scale=scale * k)
        body = self.text.layout('ArialRoundedMTBold16', text, root.width - 25, TextStyle(10, 3, self.ink()))
        # Alignment 21, child anchor (1/2,1/2). Both native episode-ID paths
        # use a label height equal to layout 24's original height, even when
        # the surrounding sprite has expanded.
        body_y = top + 15 if builtin else height + root.height / 2
        self.text.draw_layout(layer, 'ArialRoundedMTBold16', body,
                              (160 - (root.width - 25) / 2) * k, body_y * k, scale=k)
        return layer, footer_top + footer.height

    def draw(self, target, session):
        panel = session.engine.message_panel
        self.canvas.fill((0, 0, 0, 0))
        cod, k = self.cod(), self.scale
        # 000ac4dc places this panel's background at GL (160,240). CoD's panel stands on black: the owner's
        # recording shows the scene picture fading out under it (Desktop._location_change).
        self.pending_background = None if cod else self.art.image(session.engine.panel.background_id)
        layer, button_y = self.panel(panel.title, panel.text)
        self.canvas.blit(layer, (0, 0))
        strings = self.strings()
        caption = strings[29] if panel.ready else f'{strings[30]} ({panel.countdown})'
        label = self.text.layout('TrebuchetMS_Bold14', caption, 2**31,
                                 TextStyle(16, 5, (255, 255, 255)))
        # 000acc28 grows the shared continuation node over 250 ms (SHS). Its
        # anchor is zero; 00098940 attaches the artwork centered at (0,0).
        # The text child has position (-6,8), size (40,0), anchor (1/2,1/2).
        control = pygame.Surface((140 * k, 60 * k), pygame.SRCALPHA).convert_alpha()
        image = self.art.frame(126, 5)
        if k != 1:
            image = pygame.transform.smoothscale(image, (image.get_width() * k, image.get_height() * k))
        control.blit(image, image.get_rect(center=(60 * k, 30 * k)))
        self.text.draw_layout(control, 'TrebuchetMS_Bold14', label, 34 * k, 22 * k, scale=k)
        # CoD's control arrives at full size with the panel (owner's recording, 60 fps).
        scale = 1. if cod else max(.001, min(1., panel.elapsed_ms / 250))
        self.canvas.blit(pygame.transform.smoothscale(control, (max(1, round(140 * k * scale)),
                                                               max(1, round(60 * k * scale)))),
                         (round((245 - 60 * scale) * k), round((button_y - 30 * scale) * k)))
        # Desktop draws the bar and gear edge to edge (see DialogueRenderer.bottom_bar_layer).
        self.edge_bar = 'bar'
        hint_text = strings[36 if panel.ready else 39]
        if cod:
            # CoD's hint is the dialogue's own: ArialMT 11 at Arial Rounded's advances (footer_font).
            self.footer_text = hint_text
        else:
            self.footer_text = ''
            hint = self.text.layout('ArialRoundedMTBold11', hint_text, 247, TextStyle(11, 0, (185, 185, 185)))
            self.text.draw_layout(self.canvas, 'ArialRoundedMTBold11', hint,
                                  (63 + (252 - hint.width) / 2) * k, 460 * k, scale=k)
        return [(pygame.Rect(-32, 422, 92, 58), ('menu',)),
                (pygame.Rect(0, 0, 320, 480), ('continue',))]
