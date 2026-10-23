"""Original episode intros and week cards, drawn from the player's APK."""
from functools import lru_cache

from .graphics import faded
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
        # SRCALPHA: the background is composited separately by Desktop, at
        # real window resolution -- see desktop_dialogue.py's DialogueRenderer.
        self.canvas = pygame.Surface((320, 480), pygame.SRCALPHA).convert_alpha()
        self.pending_background = None
        self.pending_background_origin = None  # stretch to fill, not centered-crop

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
        self.canvas.fill((0, 0, 0, 0))
        self.pending_background = None
        self.pending_background_alpha = round(255 * motion.background_alpha)
        if motion.background_alpha > 0:
            self.pending_background = self.art.image(details['asset_id'])
        title, subtitle = self.labels(details['title'], details['subtitle'])
        self.canvas.set_clip((0, 0, motion.reveal_width, 480))
        self.draw_label(title)
        self.canvas.set_clip(None)
        self.draw_label(subtitle, motion.subtitle_scale_y)
        # Desktop draws the bar and gear edge to edge (see DialogueRenderer.bottom_bar_layer).
        self.edge_bar = 'bar'
        self.text.draw_layout(self.canvas, 'ArialMT14', self.hint(), 180, 455)
        target.blit(pygame.transform.smoothscale(self.canvas, target.get_size()), (0, 0))
        return [(pygame.Rect(-32, 422, 92, 58), ('menu',)),
                (pygame.Rect(0, 0, 320, 480), ('continue',))]


class HdTitleRenderer:
    """HD's chapter / week card (`SHSUIChapterScreen`, decompiled) in the whole 768 x 1024 frame.

    The location picture is stretched over the frame under a black layer ("revealLocation": opacity 1, 1, 0 at
    keyTimes 0, .6, 1 over 3.0 s, 0004bcda) that stays opaque for 1.8 s and then fades out by 3.0 s (TouchHLE
    recordings of Cause of Death's card agree: the picture starts showing at 1.84 s); the title ("Week 1 of 8", image font 589/590, 66 px cells) is wiped in from
    its left edge over 2 s (a clip layer slides right while the text slides left inside it); the
    subtitle (font 591/592) is invisible for 1 s and fades in over the next. Both are laid out by
    `CSImageFont::drawTextInRegion` in layout 48's node rectangles: the title in (20, 68, 738 x 400) left/top
    (flags 0x15), the subtitle in (20, 544, 714 x 360) right/bottom (0x1f). The title's top is pushed
    down 80 pt when the in-game banner ad is enabled (`g_bEnableInGameBanner`; the photographed device
    has it), measured: the title's ink starts at y 160.
    """
    hd_layer = True
    edge_bar = 'bar'
    FRAME = (768, 1024)
    TITLE_REGION, SUBTITLE_REGION = (20, 68 + 80, 738, 400), (20, 544, 714, 360)
    WIPE_S, BLACK_HOLD_S, BLACK_END_S, SUBTITLE_FROM_S, SUBTITLE_TO_S = 2., 1.8, 3., 1., 2.

    def __init__(self, resources, art):
        self.resources, self.art = resources, art
        self.canvas = pygame.Surface(self.FRAME, pygame.SRCALPHA).convert_alpha()
        self.pending_background = None
        self.pending_background_origin = None      # stretched to the frame
        self.pending_background_alpha = 255
        self.footer_text = ''

    def available(self):
        try:
            return all(self.resources.library.hd_raw_resource(i) is not None for i in (15, 589, 590, 591, 592))
        except (AttributeError, KeyError):
            return False

    @lru_cache(maxsize=2)
    def font(self, sheet, metrics):
        from .cgbi import decode
        from .hd_gl import ImageFont
        from .ui_assets import Raster
        library = self.resources.library
        image = decode(library.hd_raw_resource(sheet)).convert('RGBA')
        surface = pygame.image.frombytes(image.tobytes(), image.size, 'RGBA').convert_alpha()
        return ImageFont(AtlasFont.parse(library.hd_raw_resource(metrics),
                                         Raster(image.width, image.height, image.tobytes())), surface)

    def region_text(self, font, text, region, flags, alpha=1., clip=None):
        """`CSImageFont::drawTextInRegion`: wrap (0x10) in the region width, align by the low bits."""
        x, y, width, height = region
        lines = font.wrap(text, width) if flags & 0x10 else text.split('\n')
        block = font.text_height(lines)
        top = y + ((height - block) if flags & 0xc == 0xc else (height - block) // 2 if flags & 0xc == 8 else 0)
        for index, line in enumerate(lines):
            w = font.width(line)
            left = x + ((width - w) if flags & 3 == 3 else (width - w) // 2 if flags & 3 == 2 else 0)
            font.draw_line(self.canvas, line, left, top + index * (font.height + font.font.line_gap), alpha)
        return lines

    def wipe_clip(self, left, visible):
        """The title's reveal clip on the canvas: `visible` points of its region from `left`."""
        return pygame.Rect(left, 0, visible, self.FRAME[1])

    def draw(self, target, session):
        details, motion = session.pending.details, session.engine.title_screen
        canvas = self.canvas
        self.pending_background = self.art.image(details['asset_id'])
        seconds = motion.elapsed_ms / 1000
        # The black layer over the location picture (the text layers sit above it).
        if seconds < self.BLACK_END_S:
            level = 1. if seconds <= self.BLACK_HOLD_S else 1 - (seconds - self.BLACK_HOLD_S) / (
                self.BLACK_END_S - self.BLACK_HOLD_S)
            canvas.fill((0, 0, 0, round(255 * level)))
        else:
            canvas.fill((0, 0, 0, 0))
        title_font, subtitle_font = self.fonts()
        # Title: revealed left to right.
        left, top, region_width, region_height = self.TITLE_REGION
        width = min(region_width, title_font.width(details['title']))
        visible = round(width * min(1., seconds / self.WIPE_S))
        if visible:
            canvas.set_clip(self.wipe_clip(left, visible))
            self.region_text(title_font, details['title'], (left, top, width, region_height), 0x15)
            canvas.set_clip(None)
        fade = max(0., min(1., (seconds - self.SUBTITLE_FROM_S) / (self.SUBTITLE_TO_S - self.SUBTITLE_FROM_S)))
        if fade:
            self.region_text(subtitle_font, details['subtitle'], self.SUBTITLE_REGION, 0x1f, alpha=fade)
        self.footer_text = self.footer()
        return [(pygame.Rect(-32, 422, 92, 58), ('menu',)), (pygame.Rect(0, 0, 320, 480), ('continue',))]

    def fonts(self):
        """(title, subtitle) image fonts: HD's own 589/590 and 591/592."""
        return self.font(589, 590), self.font(591, 592)

    def footer(self):
        return MenuStrings.parse(self.resources.library.hd_raw_resource(15))[33]


class CodTitleRenderer(HdTitleRenderer):
    """Cause of Death's chapter card: SHS HD's `SHSUIChapterScreen` in a 320 x 480 screen (1.4.7: the same
    `animate` constants 2.0, 3.0 and 0.6, with 320 x 480 in place of 768 x 1024). `initChapterScreen` (00040720)
    lays layout 48 (the game's own bank, resource 14) at (0, 0, 320, 480): the title in node 9 (10, 34, 305 x 200;
    30 lower with the in-game banner) in the image font +0x4efc8, the subtitle in node 10 (10, 240, 293 x 180) in
    +0x4efcc (1.3.4's 292/293 and 294/295). The location layer is the whole picture fitted to the screen
    (`animate`: bounds 320 x 480 at (160, 240); IMG_0479 matches the 480 x 720 art at 2/3, error 2.0 of 255). In the 3:4
    frame it is scaled evenly to cover the frame instead (owner, 2026-10-14: no dead space).

    Drawn on the whole HD frame (768 x 1024 points), as SHS HD's card is, so the black opening layer covers the frame
    the picture covers, not only the CoD column. The text keeps CoD's layout: wrapping, alignment and each glyph's
    place are CoD's (fonts 528 / 530, CoD points), mapped to the frame at 2 points each from the column's origin. Each
    glyph is SHS HD's 2x one (589 / 590, 591 / 592: the same faces at twice the height, 66 / 46 against 33 / 23, with
    slightly wider cells) centred on CoD's cell when the SHS HD art source is linked, else CoD's own at twice its
    size."""
    FRAME = (768, 1024)
    COD_FRAME = (320, 480)
    ORIGIN, SCALE = (64, 53), 2            # the CoD column in the HD frame, frame points per CoD point
    BANNER = 30

    def __init__(self, resources, art, title_renderer):
        super().__init__(resources, art)
        self.title_renderer = title_renderer
        self.pending_background_origin = 'cover'      # scaled evenly to cover the frame (Desktop)
        bank = resources.dialogue_layout().bank
        from .cod.profile import in_game_banner
        title, subtitle = bank.rectangle(48, 9), bank.rectangle(48, 10)
        banner = self.BANNER if in_game_banner(resources.library) else 0
        self.TITLE_REGION = (title.x, title.y + banner, title.width, title.height)
        self.SUBTITLE_REGION = (subtitle.x, subtitle.y, subtitle.width, subtitle.height)

    def available(self):
        try:
            return self.art.game_id() == 'cod'
        except AttributeError:
            return False

    @lru_cache(maxsize=2)
    def fonts(self):
        from .hd_gl import ImageFont
        image = getattr(self.art, 'ui_image', self.art.image)
        return tuple(ImageFont(self.title_renderer.font(asset), image(asset).convert_alpha()) for asset in (528, 530))

    @lru_cache(maxsize=1)
    def hd_glyphs(self):
        """SHS HD's 2x twins of `fonts()` (title, subtitle) with the SHS HD art source, else ()."""
        from .cgbi import decode
        from .hd_gl import ImageFont
        from .ui_assets import Raster
        library = self.resources.library
        try:
            twins = []
            for sheet, metrics in ((589, 590), (591, 592)):
                sheet_data, metrics_data = library.shs_hd_resource(sheet), library.shs_hd_resource(metrics)
                if sheet_data is None or metrics_data is None:
                    return ()
                image = decode(sheet_data).convert('RGBA')
                surface = pygame.image.frombytes(image.tobytes(), image.size, 'RGBA').convert_alpha()
                twins.append(ImageFont(AtlasFont.parse(metrics_data, Raster(image.width, image.height, image.tobytes())),
                                       surface))
        except (AttributeError, ContentError, ValueError, pygame.error):
            return ()
        return tuple(twins)

    def wipe_clip(self, left, visible):
        x, _ = self.ORIGIN
        return pygame.Rect(x + left * self.SCALE, 0, visible * self.SCALE, self.FRAME[1])

    def region_text(self, font, text, region, flags, alpha=1., clip=None):
        """HdTitleRenderer.region_text in CoD points, each glyph placed on the HD frame (see the class docstring)."""
        x, y, width, height = region
        lines = font.wrap(text, width) if flags & 0x10 else text.split('\n')
        block = font.text_height(lines)
        top = y + ((height - block) if flags & 0xc == 0xc else (height - block) // 2 if flags & 0xc == 8 else 0)
        for index, line in enumerate(lines):
            w = font.width(line)
            left = x + ((width - w) if flags & 3 == 3 else (width - w) // 2 if flags & 3 == 2 else 0)
            self.draw_line(font, line, left, top + index * (font.height + font.font.line_gap), alpha)
        return lines

    def draw_line(self, font, text, x, y, alpha):
        twins, scale = self.hd_glyphs(), self.SCALE
        twin = next((twins[i] for i, own in enumerate(self.fonts()) if own is font and i < len(twins)), None)
        ox, oy = self.ORIGIN
        for char in text:
            glyph = font.font.glyph(char)
            if glyph is not None and char != ' ':
                hd = twin.font.glyph(char) if twin is not None else None
                if hd is not None:
                    gx, gy, gw = hd
                    piece = twin.sheet.subsurface((gx, gy, gw, twin.font.height))
                    shift = (gw - glyph[2] * scale) / 2           # SHS HD's cell is a little wider: centre it
                else:
                    gx, gy, gw = glyph
                    piece = pygame.transform.smoothscale(font.sheet.subsurface((gx, gy, gw, font.font.height)),
                                                         (gw * scale, font.font.height * scale))
                    shift = 0
                if alpha < 1:
                    piece = piece.copy()
                    piece = faded(piece, round(255 * alpha))
                self.canvas.blit(piece, (round(ox + x * scale - shift), round(oy + y * scale)))
            x += font.font.char_width(char) + font.font.tracking

    def footer(self):
        return self.art.footer_hint(36, 'Touch the screen to continue')
