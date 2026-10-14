"""Original dialogue artwork at native logical coordinates."""
from functools import lru_cache
from io import BytesIO

from . import graphics as pygame

from .content import ContentError
from .dialogue_notice import NOTICE_FONT, NOTICE_STYLE, NoticeMotion
from .fonts import TextStyle
from .menu import MenuStrings
from .ui_assets import ImagePack, Raster, UIAssetError, read_ui


class DialogueRenderer:
    def __init__(self, resources, text_renderer, image_loader):
        self.resources = resources
        self.text = text_renderer
        self.image = image_loader
        self.canvas = pygame.Surface((320, 480)).convert(32)
        self.cached_key = None
        self.cached_page = None
        self.name_layer = pygame.Surface((320, 480), pygame.SRCALPHA).convert_alpha()

    def draw_background(self, target, engine):
        background = self.image(engine.panel.background_id)
        if background is not None:
            target.blit(background, engine.background_pan.origin(*background.get_size()))

    @lru_cache(maxsize=8)
    def pack(self, asset_id):
        return ImagePack.parse(read_ui(self.resources, asset_id))

    @lru_cache(maxsize=32)
    def ui_image(self, role):
        library = getattr(self.resources, 'library', self.resources)
        if getattr(library, 'kind', 'apk') != 'ipa':
            return self.image(role)
        data = read_ui(self.resources, role)
        if data.startswith((b'\x89PNG', b'\xff\xd8')):
            return pygame.image.load(BytesIO(data)).convert_alpha()
        frame = ImagePack.parse(data).images[0]
        return pygame.image.frombytes(frame.pixels, (frame.width, frame.height), frame.mode).convert_alpha()

    @lru_cache(maxsize=64)
    def frame(self, asset_id, index):
        frame = self.pack(asset_id).images[index]
        return pygame.image.frombytes(frame.pixels, (frame.width, frame.height), frame.mode).convert_alpha()

    @lru_cache(maxsize=32)
    def portrait(self, asset_id, flipped):
        """Native portrait texture: normalize, mask, remove 12 rows, then flip."""
        image = self.image(asset_id)
        if image is None:
            return None
        raster = Raster(*image.get_size(), pygame.image.tobytes(image, 'RGBA'))
        mask = self.pack(268).images[0]
        masked = raster.normalize_portrait(mask).portrait_mask(mask)
        # FUN_0005afbc shortens the masked texture before FUN_0009c034
        # aligns its bottom to the circle. Keeping the discarded rows lifts
        # the visible character by 12 pixels inside its frame.
        height = masked.height - 12
        if height <= 0:
            raise UIAssetError(f'Portrait height {masked.height} cannot accommodate the native 12-row crop')
        pixels = masked.pixels[:masked.width * height * 4]
        # Match the display format after creating the masked RGBA buffer.
        # Cocoa's opaque BGRA canvas can otherwise copy transparent RGB
        # instead of blending it, exposing white pixels and black mask corners.
        image = pygame.image.frombytes(pixels, (masked.width, height), 'RGBA').convert_alpha()
        return pygame.transform.flip(image, flipped, False) if flipped else image

    def portrait_rect(self, image, center=(0, 0)):
        """FUN_0009c034 positions the sprite center within the bubble."""
        x, y = center
        offset = self.frame(126, 39).get_height() // 2 - image.get_height() // 2
        # The native routine halves each height separately. A midbottom
        # anchor puts odd-height artwork one pixel above this center.
        return image.get_rect(center=(x, y + offset))

    def box(self, target, rect, theme, *, alpha=255):
        """FUN_00081920 places the eight border pieces outside the center."""
        pack = {1: 204, 2: 220, 3: 252}.get(theme, 236)
        x, y, width, height = rect.x, rect.y, rect.width, rect.height
        center = self.frame(126, 0).copy()
        center.set_alpha(alpha)
        target.blit(pygame.transform.scale(center, (width, height)), (x, y))
        for index, column, row in ((6, 0, 0), (7, 1, 0), (8, 2, 0), (4, 0, 1),
                                   (5, 2, 1), (0, 0, 2), (1, 1, 2), (2, 2, 2)):
            image = self.frame(pack, index).copy()
            image.set_alpha(alpha)
            w, h = image.get_size()
            size = (width if column == 1 else w, height if row == 1 else h)
            position = (x - w if column == 0 else x + width if column == 2 else x,
                        y - h if row == 0 else y + height if row == 2 else y)
            target.blit(pygame.transform.scale(image, size), position)

    @lru_cache(maxsize=32)
    def portrait_group(self, portrait, clip=None, old=None, old_alpha=0, alpha=255):
        """The art and both rings are children of the native scaled node."""
        rings = [self.frame(126, index)
                 for index in (37, {1: 38, 2: 39}.get(portrait.theme, 40))]
        if clip is not None:
            # drawInContext's even-odd path cuts only housing frame 37.
            # Its polygon has 10px bevels at the two upper corners.
            housing = rings[0].copy()
            origin = housing.get_rect(center=(0, 0))
            x, y, w, h = clip
            x, y = x - origin.x, y - origin.y
            pygame.draw.polygon(housing, (0, 0, 0, 0),
                                ((x, y + h), (x, y + 10), (x + 10, y),
                                 (x + w - 10, y), (x + w, y + 10), (x + w, y + h)))
            rings[0] = housing
        pieces = [(ring, ring.get_rect(center=(0, 0))) for ring in rings]
        for art, opacity in ((old, old_alpha), (portrait, alpha)):
            if art is None or opacity <= 0:
                continue
            image = self.portrait(art.asset_id, art.mode == 2 and art.theme != 3)
            if image is not None:
                if opacity < 255:
                    image = image.copy()
                    image.set_alpha(opacity)
                pieces.append((image, self.portrait_rect(image)))
        bounds = pieces[0][1].unionall([rect for _, rect in pieces[1:]])
        layer = pygame.Surface(bounds.size, pygame.SRCALPHA).convert_alpha()
        for piece, rect in pieces:
            layer.blit(piece, rect.move(-bounds.x, -bounds.y))
        return layer, bounds.topleft

    def draw_portrait(self, portrait, scale, *, box=None, old=None, alphas=(0, 255)):
        if portrait is None or scale <= 0:
            return
        rect = self.resources.dialogue_layout().bank.rectangle(17, 0x30 if portrait.mode == 1 else 0x4e)
        cx, cy = rect.center
        cy -= 5  # FUN_000aaa40 uses 485-y when converting to GL.
        clip = None if box is None else (box.x - 7 - cx, box.y - 7 - cy,
                                         box.width + 14, box.height + 34)
        layer, (x, y) = self.portrait_group(portrait, clip, old, *alphas)
        if scale != 1:
            size = max(1, round(layer.get_width() * scale)), max(1, round(layer.get_height() * scale))
            layer = pygame.transform.smoothscale(layer, size)
        self.canvas.blit(layer, (round(cx + x * scale), round(cy + y * scale)))

    def draw_relationship(self, motion):
        if motion.relationship is None or motion.portrait is None:
            return
        rect = self.resources.dialogue_layout().bank.rectangle(17, 0x30 if motion.portrait.mode == 1 else 0x4e)
        cx, cy = rect.center
        cy -= 5
        # Indicator parents are siblings of the head's scaled node. They
        # appear after its entrance and do not inherit the head-only flip.
        for pose in motion.relationship.poses():
            icon = self.ui_image(pose.asset_id)
            if icon is None:
                continue
            image = pygame.transform.rotozoom(icon, -pose.rotation, 1)
            center = round(cx + pose.x), round(cy + pose.y)
            self.canvas.blit(image, image.get_rect(center=center))
            if pose.flash_alpha:
                flash = self.ui_image(pose.flash_asset)
                if flash is not None:
                    flash = pygame.transform.rotozoom(flash, -pose.rotation, pose.flash_scale)
                    flash.set_alpha(pose.flash_alpha)
                    self.canvas.blit(flash, flash.get_rect(center=center))

    def draw_notice(self, engine):
        portrait = engine.dialogue_animation.portrait
        # This label belongs to the current portrait parent, which the native
        # panel hides for narration and dialogue without character artwork.
        if not engine.notice_ms or portrait is None:
            return
        motion = NoticeMotion(engine.notice, engine.notice_ms)
        rect = self.resources.dialogue_layout().bank.rectangle(17, 0x30 if portrait.mode == 1 else 0x4e)
        x, y = motion.origin(rect, portrait.mode)
        # Native alignment 5 is top-left, with no automatic wrapping. Preserve
        # the font's baked-in red lettering and white outline by using white RGB.
        layout = self.text.layout(NOTICE_FONT, engine.notice, 2**31, NOTICE_STYLE)
        for index, glyph in enumerate(layout.glyphs):
            image = self.text._glyph_image(NOTICE_FONT, glyph, motion.scale)
            if motion.alpha < 255:
                image = image.copy()
                image.set_alpha(motion.alpha)
            self.canvas.blit(image, (round(x + glyph.x * motion.scale),
                                     round(y + glyph.y * motion.scale - motion.glyph_rise(index))))

    @lru_cache(maxsize=4)
    def continue_tab(self, theme):
        # GameModel::setBubbleSex chooses the supplied skin's frames 3–6.
        tab = self.frame(126, {1: 5, 2: 3, 3: 6}.get(theme, 4)).copy()
        font = 'TrebuchetMS_Bold14'
        metrics = self.text.font(font)
        height = getattr(metrics, 'cap_height', 14)
        label = self.text.layout(font, MenuStrings.load(self.resources)[29], tab.get_width(), TextStyle(height))
        left, top, right, bottom = label.ink_bounds
        self.text.draw_layout(tab, font, label, (tab.get_width() - right - left) / 2,
                              (tab.get_height() - bottom - top) / 2)
        return tab

    def draw_continue(self, box, theme, motion):
        scale = motion.continue_scale
        if scale <= 0:
            return
        tab = self.continue_tab(theme)
        width, height = tab.get_size()
        if scale < 1:
            tab = pygame.transform.smoothscale(tab, (width, max(1, round(height * scale))))
        # expandContinue: center = (bubble.width - 49.5, bubble.height + 8.5).
        self.canvas.blit(tab, (box.x + box.width - width,
                               box.y + box.height + round((height - tab.get_height()) / 2)))

    @lru_cache(maxsize=1)
    def footer_hint(self):
        # GameModel::init / layout 18 node 2: ArialMT 11, white alpha 0xb0,
        # centered in the 252x18 tooltip region below the story panel.
        strings = MenuStrings.load(getattr(self.resources, 'library', self.resources))
        name = 'ArialMT11'
        label = self.text.layout(name, strings[36], 252, TextStyle(11, 0))
        layer = pygame.Surface((252, 18), pygame.SRCALPHA).convert_alpha()
        left, top, right, bottom = label.ink_bounds
        self.text.draw_layout(layer, name, label,
                              (252 - (right - left)) / 2 - left,
                              (18 - (bottom - top)) / 2 - top)
        layer.set_alpha(176)
        return layer

    def draw(self, target, session):
        details = session.pending.details
        key = id(session), session.scene, session.vm.steps_executed, details['page_start']
        if key != self.cached_key:
            self.cached_page = session.dialogue_page()
            self.cached_key = key
            self.name_layer.fill((0, 0, 0, 0))
            if self.cached_page is not None:
                page = self.cached_page
                self.text.draw_layout(self.name_layer, page.name_font, page.name,
                                      *page.name_origin, scale=page.name_scale)
        page = self.cached_page
        if page is None:
            raise ContentError('Dialogue requires the imported APK layout and fonts')
        self.canvas.fill((0, 0, 0))
        self.draw_background(self.canvas, session.engine)
        motion = session.engine.dialogue_animation
        angle = motion.box_rotation
        if angle or motion.box_scale != 1:
            from .ui_assets import Rect
            box = page.box
            layer = pygame.Surface((box.width + 20, box.height + 20), pygame.SRCALPHA).convert_alpha()
            self.box(layer, Rect(10, 10, box.width, box.height), details['theme'])
            layer = pygame.transform.rotozoom(layer, -angle, motion.box_scale)
            layer.set_alpha(motion.box_alpha)
            self.canvas.blit(layer, layer.get_rect(center=box.center))
        else:
            origin = page.portrait
            if origin is None and motion.anchor_mode:
                origin = self.resources.dialogue_layout().bank.rectangle(17, 0x30 if motion.anchor_mode == 1 else 0x4e)
            self.box(self.canvas, motion.box_rect(page.box, origin), details['theme'], alpha=motion.box_alpha)
        self.draw_portrait(motion.previous, motion.previous_scale)
        self.draw_portrait(motion.portrait, motion.portrait_scale,
                           box=page.box if motion.housing_clipped else None,
                           old=motion.initial_portrait, alphas=motion.expression_alphas)
        self.draw_relationship(motion)
        self.draw_notice(session.engine)
        self.text.draw_layout(self.canvas, page.body_font, page.body, *page.body_origin,
                              source_end=motion.revealed)
        self.name_layer.set_alpha(motion.name_alpha)
        self.canvas.blit(self.name_layer, (0, 0))
        self.draw_continue(page.box, details['theme'], motion)
        # Layout 18's footer and its original instruction, separate from the
        # animated Continue tab attached to the dialogue box.
        self.canvas.blit(self.frame(126, 47), (0, 431))
        self.canvas.blit(self.footer_hint(), (63, 459))
        target.blit(pygame.transform.smoothscale(self.canvas, target.get_size()), (0, 0))
        return page
