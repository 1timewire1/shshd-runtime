"""Original service-78 portrait layout, artwork, and confirmation control."""
from functools import lru_cache

from . import graphics as pygame
from .desktop_pause import draw_pause_gear

from .fonts import TextStyle
from .menu import MenuStrings
from .ui_assets import Rect, read_ui


class CharacterPickerRenderer:
    def __init__(self, resources, text_renderer, artwork):
        self.resources, self.text, self.art = resources, text_renderer, artwork
        self.canvas = pygame.Surface((320, 480)).convert(32)
        self.hint = None

    @lru_cache(maxsize=32)
    def portrait(self, asset, theme):
        # The selector passes the fifth portrait flag as 1: FUN_0009bd40
        # uses the combined selection ring (43/44), rather than dialogue rings.
        ring = self.art.frame(126, {1: 43, 2: 44}.get(theme, 0))
        pieces = [(ring, ring.get_rect(center=(0, 0)))]
        image = self.art.portrait(asset, False)  # Expression zero, portrait mode 1.
        if image is not None:
            pieces.append((image, self.art.portrait_rect(image)))
        bounds = pieces[0][1].unionall([rect for _, rect in pieces[1:]])
        layer = pygame.Surface(bounds.size, pygame.SRCALPHA).convert_alpha()
        for piece, rect in pieces:
            layer.blit(piece, rect.move(-bounds.x, -bounds.y))
        return layer, bounds.topleft

    def draw(self, target, session):
        picker, engine = session.engine.character_picker, session.engine
        self.canvas.fill((0, 0, 0))
        self.art.draw_background(self.canvas, engine)
        theme = engine.numbers.get(engine.number_key(picker.characters[0], 651), 0)
        # FUN_000d2238/FUN_000d2558 override layout 47's root to this rectangle.
        self.art.box(self.canvas, Rect(0, 120, 320, 240), theme)
        for index, character in enumerate(picker.characters):
            variants = engine.character_art_variants.get(character, [-1])
            color = engine.numbers.get(engine.number_key(character, 651), 0)
            layer, (ox, oy) = self.portrait(variants[0], color)
            motion = picker.portraits[index]
            x, y, scale = motion.pose
            layer = pygame.transform.smoothscale(layer, (max(1, round(layer.get_width() * scale)),
                                                        max(1, round(layer.get_height() * scale))))
            layer.set_alpha(motion.opacity)
            self.canvas.blit(layer, (round(x + ox * scale), round(y + oy * scale)))
        title = self.text.layout('PajamaHip26', session.pending.details['text'], 300,
                                 TextStyle(16, -16, (255, 255, 255)))
        self.text.draw_layout(self.canvas, 'PajamaHip26', title, 30, 67.5)
        self.canvas.blit(self.art.frame(126, 41), (205, 347))
        self.canvas.blit(self.art.frame(126, 47), (0, 431))
        draw_pause_gear(self.canvas, self.art)
        if self.hint is None:
            self.hint = MenuStrings.load(self.resources.library)[37]
        hint = self.text.layout('ArialRoundedMTBold11', self.hint,
                                247, TextStyle(11, 0, (185, 185, 185)))
        self.text.draw_layout(self.canvas, 'ArialRoundedMTBold11', hint, 63 + (252 - hint.width) / 2, 460)
        target.blit(pygame.transform.smoothscale(self.canvas, target.get_size()), (0, 0))
        return [(pygame.Rect(0, 422, 60, 58), ('menu',))]

    @staticmethod
    def confirm_hit(point):
        x, y = point
        # FUN_000d2008: the explicit 50x50 area plus the flipped sprite rectangle.
        return (210 <= x <= 260 and 330 <= y <= 380) or (205 <= x <= 275 and 344 <= y <= 389)
