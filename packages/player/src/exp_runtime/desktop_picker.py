"""Original service-78 portrait layout, artwork, and confirmation control."""
from functools import lru_cache

from .graphics import faded
from . import graphics as pygame
from .desktop_pause import draw_pause_gear

from .fonts import TextStyle
from .menu import MenuStrings
from .ui_assets import Rect, read_ui


class CharacterPickerRenderer:
    def __init__(self, resources, text_renderer, artwork):
        self.resources, self.text, self.art = resources, text_renderer, artwork
        # SRCALPHA: the background is composited separately by Desktop, at
        # real window resolution -- see desktop_dialogue.py's DialogueRenderer.
        self.canvas = pygame.Surface((320, 480), pygame.SRCALPHA).convert_alpha()
        self.hint = None
        self.pending_background = None
        self.pending_background_origin = (160, 180)

    @lru_cache(maxsize=32)
    def portrait(self, asset, theme):
        # The selector passes the fifth portrait flag as 1: FUN_0009bd40
        # uses the combined selection ring (43/44), rather than dialogue rings.
        # HD's selection rings are frames 46/47/48 of pack 155 (Android 0/43/44).
        ring = (self.art.frame(126, {1: 43, 2: 44}.get(theme, 0)) if not self.art.hd_chrome()
                else self.art._hd_frame({1: 47, 2: 48}.get(theme, 46), 1))
        pieces = [(ring, ring.get_rect(center=(0, 0)))]
        image = self.art.portrait(asset, False, crop=True)  # Expression zero, portrait mode 1.
        if image is not None:
            pieces.append((image, self.art.portrait_rect(image)))
        bounds = pieces[0][1].unionall([rect for _, rect in pieces[1:]])
        layer = pygame.Surface(bounds.size, pygame.SRCALPHA).convert_alpha()
        for piece, rect in pieces:
            layer.blit(piece, rect.move(-bounds.x, -bounds.y))
        return layer, bounds.topleft

    def draw(self, target, session):
        picker, engine = session.engine.character_picker, session.engine
        self.canvas.fill((0, 0, 0, 0))
        self.pending_background = self.art.image(engine.panel.background_id)
        self.pending_background_origin = self.art.background_origin(self.pending_background, engine)
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
            layer = faded(layer, motion.opacity)
            self.canvas.blit(layer, (round(x + ox * scale), round(y + oy * scale)))
        title = self.text.layout('PajamaHip26', session.pending.details['text'], 300,
                                 TextStyle(16, -16, (255, 255, 255)))
        self.text.draw_layout(self.canvas, 'PajamaHip26', title, 30, 67.5)
        self.canvas.blit(self.art.frame(126, 41), (205, 347))
        # Desktop draws the bar and gear edge to edge (see DialogueRenderer.bottom_bar_layer).
        self.edge_bar = 'bar'
        if self.hint is None:
            self.hint = MenuStrings.load(self.resources.library)[37]
        hint = self.text.layout('ArialRoundedMTBold11', self.hint,
                                247, TextStyle(11, 0, (185, 185, 185)))
        self.text.draw_layout(self.canvas, 'ArialRoundedMTBold11', hint, 63 + (252 - hint.width) / 2, 460)
        target.blit(pygame.transform.smoothscale(self.canvas, target.get_size()), (0, 0))
        return [(pygame.Rect(-32, 422, 92, 58), ('menu',))]

    @staticmethod
    def confirm_hit(point):
        x, y = point
        # FUN_000d2008: the explicit 50x50 area plus the flipped sprite rectangle.
        return (210 <= x <= 260 and 330 <= y <= 380) or (205 <= x <= 275 and 344 <= y <= 389)


class HdCharacterPickerRenderer:
    """HD's portrait selector (`SHSUIPortraitSelect`, decompiled) in the whole 768 x 1024 point frame.

    The panel is the speaker theme's bubble box over layout 47's rectangle (0, 240, 768 x 480 pt), 243/255 opaque, so
    it spans the frame (its side borders fall off-screen). The five portraits keep the motion model of the
    Android selector (`ARR_PORTRAIT_POSITIONS` = (320, 550), (104, 482), (230, 340), (412, 340), (538, 482);
    `ARR_PORTRAIT_SCALE` = 1, .6, .6, .6, .6; opacity = scale squared) -- the frame position is the column
    position + (32 units, 3 pt). The check button is pack 32 frame 0 (frame 1 while pressed) centered at
    (608, 737) pt (`initPortraitSelect`), and the title is the theme font at 52 pt, centered on the panel's
    top edge. Drawn 1:1 in points (2 px per layout unit), so HD art is never resampled here.
    """
    hd_layer = True
    edge_bar = 'bar'
    U = 2
    BUTTON_CENTER = (608, 737)
    TITLE_CENTER = (384, 233)
    PANEL = (0, 120, 384, 240)          # frame units

    def __init__(self, resources, text_renderer, artwork):
        self.resources, self.text, self.art = resources, text_renderer, artwork
        self.canvas = pygame.Surface((768, 1024), pygame.SRCALPHA).convert_alpha()
        self.footer_text = ''
        self.pending_background = None
        self.pending_background_origin = (160, 180)
        self.pressed = False

    def available(self):
        try:
            return (self.art.hd_chrome() and self.resources.library.hd_raw_resource(32) is not None
                    and self.resources.library.hd_raw_resource(15) is not None)
        except (AttributeError, KeyError):
            return False

    @lru_cache(maxsize=1)
    def strings(self):
        return MenuStrings.parse(self.resources.library.hd_raw_resource(15))

    @lru_cache(maxsize=2)
    def button(self, frame):
        from .ui_assets import ImagePack
        image = ImagePack.parse(self.resources.library.hd_raw_resource(32)).images[frame]
        return pygame.image.frombytes(image.pixels, (image.width, image.height), image.mode).convert_alpha()

    @lru_cache(maxsize=32)
    def portrait(self, asset, theme):
        """The selection ring and the cropped portrait as one layer, at this layer's 2 px per unit."""
        ring = self.art._hd_frame({1: 47, 2: 48}.get(theme, 46), self.U)
        pieces = [(ring, ring.get_rect(center=(0, 0)))]
        image = self.art.portrait(asset, False, self.U, crop=True)
        if image is not None:
            pieces.append((image, self.art.portrait_rect(image, density=self.U)))
        bounds = pieces[0][1].unionall([rect for _, rect in pieces[1:]])
        layer = pygame.Surface(bounds.size, pygame.SRCALPHA).convert_alpha()
        for piece, rect in pieces:
            layer.blit(piece, rect.move(-bounds.x, -bounds.y))
        return layer, bounds.topleft

    def draw(self, target, session):
        picker, engine = session.engine.character_picker, session.engine
        canvas, U = self.canvas, self.U
        canvas.fill((0, 0, 0, 0))
        self.pending_background = self.art.image(engine.panel.background_id)
        theme = engine.numbers.get(engine.number_key(picker.characters[0], 651), 0)
        x, y, width, height = self.PANEL
        self.art.box(canvas, Rect(x, y, width, height), theme, alpha=243, scale=U)
        for index, character in enumerate(picker.characters):
            variants = engine.character_art_variants.get(character, [-1])
            color = engine.numbers.get(engine.number_key(character, 651), 0)
            layer, (ox, oy) = self.portrait(variants[0], color)
            motion = picker.portraits[index]
            px, py, scale = motion.pose
            layer = pygame.transform.smoothscale(layer, (max(1, round(layer.get_width() * scale)),
                                                        max(1, round(layer.get_height() * scale))))
            layer = faded(layer, motion.opacity)
            canvas.blit(layer, (round((px + 32) * U + ox * scale), round(py * U + 3 + oy * scale)))
        title = self.text.layout('PajamaHip26', session.pending.details['text'], 300,
                                 TextStyle(16, -16, (255, 255, 255)))
        left, top, right, bottom = title.ink_bounds
        self.text.draw_layout(canvas, 'PajamaHip26', title,
                              round(self.TITLE_CENTER[0] - (left + right) * U / 2),
                              round(self.TITLE_CENTER[1] - (top + bottom) * U / 2), scale=U)
        button = self.button(1 if self.pressed else 0)
        canvas.blit(button, button.get_rect(center=self.BUTTON_CENTER))
        self.footer_text = self.strings()[34]
        return [(pygame.Rect(-32, 422, 92, 58), ('menu',))]

    @staticmethod
    def confirm_hit(point):
        """`point` is in the column's units; the button is 140 x 90 pt around (608, 737) in the frame."""
        x, y = point[0] + 32, point[1] + 26.5
        return abs(x - 304) <= 40 and abs(y - 368.5) <= 28


class CodCharacterPickerRenderer(CharacterPickerRenderer):
    """Cause of Death's portrait selector: SHS HD's `SHSUIPortraitSelect` at iPhone size (1.4.7: widget 47 at
    (0, 120, 320 x 240); `ARR_PORTRAIT_POSITIONS` = (160, 275), (52, 241), (115, 170), (206, 170), (269, 241), SHS HD's
    halved, and no frame offset; the same `ARR_PORTRAIT_SCALE`). Drawn at 2 px per unit over the column.

    - Each portrait is an `SHSPortraitLayer` with the picker's ring (frame 43 / 44) and the art in its housing, at
      opacity scale x scale (`selectPortrait` 0004fc5c). That opacity is applied to the ring and the art separately:
      CoD's iOS composites a layer's sublayers one by one (no group opacity), so where they overlap the side
      portraits read stronger than one flattened layer at 0.36 (IMG_0458).
    - The title is the speaker theme's name face (26, its stroked twin), its ink centred at (160, 112), about 8
      above the panel (IMG_0458: 112.2). The check button is frame 41 at (205, 347), centred at (240, 369): the
      panel's bottom + 9 (`initPortraitSelect`, SHS HD + 17).
    - The hint goes on the shared bottom bar.
    """
    hd_layer = True
    edge_bar = 'bar'
    U = 2
    TITLE_CENTER = (160, 112)

    def __init__(self, resources, text_renderer, artwork):
        super().__init__(resources, text_renderer, artwork)
        self.canvas = pygame.Surface((320 * self.U, 480 * self.U), pygame.SRCALPHA).convert_alpha()
        self.footer_text = ''

    def available(self):
        try:
            return self.art.game_id() == 'cod' and self.art.cod_hd_common() is not None
        except AttributeError:
            return False

    @lru_cache(maxsize=32)
    def pieces(self, asset, theme):
        """[(image, top-left)] of one portrait at this canvas's density, relative to its centre."""
        U = self.U
        ring = self.art.frame_scaled(126, {1: 43, 2: 44}.get(theme, 43), U)
        pieces = [(ring, ring.get_rect(center=(0, 0)).topleft)]
        composed = self.art.hd_portrait(asset, False, U)
        if composed is not None:
            art, lift = composed
            housing = ring.get_rect(center=(0, 0))
            pieces.append((art, (housing.x, housing.y - lift)))
        return pieces

    def draw(self, target, session):
        picker, engine = session.engine.character_picker, session.engine
        canvas, U = self.canvas, self.U
        canvas.fill((0, 0, 0, 0))
        self.pending_background = self.art.image(engine.panel.background_id)
        self.pending_background_origin = self.art.background_origin(self.pending_background, engine)
        theme = engine.numbers.get(engine.number_key(picker.characters[0], 651), 0)
        self.art.box(canvas, Rect(0, 120, 320, 240), theme, alpha=243, scale=U)
        for index, character in enumerate(picker.characters):
            variants = engine.character_art_variants.get(character, [-1])
            color = engine.numbers.get(engine.number_key(character, 651), 0)
            motion = picker.portraits[index]
            px, py, scale = motion.pose
            cx, cy = px * U, py * U                     # the pose is the portrait's centre
            for image, (ox, oy) in self.pieces(variants[0], color):
                piece = pygame.transform.smoothscale(image, (max(1, round(image.get_width() * scale)),
                                                             max(1, round(image.get_height() * scale))))
                piece = faded(piece, motion.opacity)
                canvas.blit(piece, (round(cx + ox * scale), round(cy + oy * scale)))
        title = self.text.layout('PajamaHip26', session.pending.details['text'], 300,
                                 TextStyle(16, -16, (255, 255, 255)))
        left, top, right, bottom = title.ink_bounds
        self.text.draw_layout(canvas, 'PajamaHip26', title,
                              round((self.TITLE_CENTER[0] - (left + right) / 2) * U),
                              round((self.TITLE_CENTER[1] - (top + bottom) / 2) * U), scale=U)
        canvas.blit(self.art.frame_scaled(126, 41, U), (205 * U, 347 * U))
        if self.hint is None:
            self.hint = MenuStrings.load(self.resources.library)[37]
        self.footer_text = self.hint
        return [(pygame.Rect(-32, 422, 92, 58), ('menu',))]
