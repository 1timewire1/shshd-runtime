"""Original episode intros and week cards, drawn from the player's APK."""
from functools import lru_cache

from . import graphics as pygame
from .desktop_pause import draw_pause_gear

from .atlas import AtlasFont
from .content import ContentError
from .fonts import TextStyle, layout_label
from .menu import MenuStrings
from .title_screen import title_labels
from .ui_assets import Rect, read_ui


class TitleRenderer:
    def __init__(self, resources, text_renderer, artwork):
        self.resources, self.text, self.art = resources, text_renderer, artwork
        self.canvas = pygame.Surface((320, 480)).convert(32)

    @lru_cache(maxsize=2)
    def font(self, asset):
        image = getattr(self.art, 'ui_image', self.art.image)(asset)
        if image is None:
            raise ContentError(f'Title font atlas {asset} is missing')
        return AtlasFont.parse(read_ui(self.resources, asset + 1), Rect(0, 0, *image.get_size()))

    @lru_cache(maxsize=64)
    def labels(self, title, subtitle):
        return title_labels(self.resources.dialogue_layout().bank, self.font(528), self.font(530),
                            title, subtitle)

    @lru_cache(maxsize=128)
    def label_image(self, label):
        font = self.font(label.asset_id)
        atlas = getattr(self.art, 'ui_image', self.art.image)(label.asset_id)
        if not label.glyphs:
            return None, (0, 0)
        left, top = min(g.x for g in label.glyphs), min(g.y for g in label.glyphs)
        right = max(g.x + font.glyph(g.character)[2] for g in label.glyphs)
        bottom = max(g.y + font.height for g in label.glyphs)
        image = pygame.Surface((max(1, right - left), max(1, bottom - top)), pygame.SRCALPHA).convert_alpha()
        for g in label.glyphs:
            x, y, width = font.glyph(g.character)
            image.blit(atlas, (g.x - left, g.y - top), (x, y, width, font.height))
        return image, (left, top)

    def draw_label(self, label, scale_y=1.):
        image, (left, top) = self.label_image(label)
        if image is None:
            return
        sx, sy = label.scale, label.scale * scale_y
        size = max(1, round(image.get_width() * sx)), max(1, round(image.get_height() * sy))
        self.canvas.blit(pygame.transform.smoothscale(image, size),
                         (round(label.origin[0] + left * sx), round(label.origin[1] + top * sy)))

    @lru_cache(maxsize=1)
    def hint(self):
        strings = MenuStrings.load(self.resources.library)
        # 0007cbbc / 0007d4c8: font registry 11, zero content size,
        # center/center alignment, GL position (180,25), white text.
        font = self.text.font('ArialMT14')
        return layout_label(font, strings[36], 0, 0, TextStyle(14, 8), 0x0a)

    def draw(self, target, session):
        details, motion = session.pending.details, session.engine.title_screen
        self.canvas.fill((0, 0, 0))
        background = self.art.image(details['asset_id'])
        if background is not None and motion.background_alpha > 0:
            background = pygame.transform.smoothscale(background, (320, 480))
            background.set_alpha(round(255 * motion.background_alpha))
            self.canvas.blit(background, (0, 0))
        title, subtitle = self.labels(details['title'], details['subtitle'])
        self.canvas.set_clip((0, 0, motion.reveal_width, 480))
        self.draw_label(title)
        self.canvas.set_clip(None)
        self.draw_label(subtitle, motion.subtitle_scale_y)
        self.canvas.blit(self.art.frame(126, 47), (0, 431))
        draw_pause_gear(self.canvas, self.art)
        self.text.draw_layout(self.canvas, 'ArialMT14', self.hint(), 180, 455)
        target.blit(pygame.transform.smoothscale(self.canvas, target.get_size()), (0, 0))
        return [(pygame.Rect(0, 422, 60, 58), ('menu',)),
                (pygame.Rect(0, 0, 320, 480), ('continue',))]
