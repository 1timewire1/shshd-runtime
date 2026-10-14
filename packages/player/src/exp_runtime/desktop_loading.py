"""Service 91's original loading panels, strings, fonts, and five-frame art."""
from functools import lru_cache

from . import graphics as pygame

from .fonts import TextStyle
from .menu import MenuStrings
from .ui_assets import Rect, read_ui


class LoadingRenderer:
    def __init__(self, resources, text_renderer, artwork):
        self.resources, self.text, self.art = resources, text_renderer, artwork
        self.canvas = pygame.Surface((320, 480)).convert(32)

    @lru_cache(maxsize=1)
    def panel(self):
        layer = pygame.Surface((320, 480), pygame.SRCALPHA).convert_alpha()
        bank = self.resources.dialogue_layout().bank
        # FUN_0008d43c: top panel at GL (0,160), bottom at (-20,133).
        # A zero height argument preserves layout 22's native height of 60.
        for index, root in ((50, Rect(0, 170, 320, 150)), (22, Rect(-20, 287, 350, 60))):
            for node_id, (node, rect) in enumerate(bank.walk(index, root), 1):
                # Layout 22 node 13 (the timer label) and its subtree are hidden.
                if index == 22 and 13 <= node_id <= 17:
                    continue
                if node.kind == 1 and node.flags & 16 and rect.width > 0 and rect.height > 0:
                    slot, frame = node.payload
                    image = self.art.frame({0: 126, 2: 204}[slot], frame)
                    layer.blit(pygame.transform.scale(image, (rect.width, rect.height)), (rect.x, rect.y))
        strings = MenuStrings.load(self.resources.library)
        title = self.text.layout('ArialRoundedMTBold20', strings[31], 320, TextStyle(20, 0, (41, 104, 221)))
        message = self.text.layout('ArialRoundedMTBold16', strings[35], 300, TextStyle(15, 0, (41, 104, 221)))
        self.text.draw_layout(layer, 'ArialRoundedMTBold20', title, 160 - title.width / 2, 170 + title.height)
        self.text.draw_layout(layer, 'ArialRoundedMTBold16', message, 160 - message.width / 2, 245)
        return layer

    def draw(self, target, session):
        self.canvas.fill((0, 0, 0))
        self.art.draw_background(self.canvas, session.engine)
        self.canvas.blit(self.panel(), (0, 0))
        icon = self.art.frame(126, session.engine.loading.frame)
        self.canvas.blit(icon, icon.get_rect(center=(155, 317)))
        target.blit(pygame.transform.smoothscale(self.canvas, target.get_size()), (0, 0))
        return []  # Completion comes from the active timer, never a click.
