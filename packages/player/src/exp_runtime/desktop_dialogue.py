"""Original dialogue artwork at native logical coordinates."""
from functools import lru_cache
from io import BytesIO

from .graphics import faded
from . import graphics as pygame

from .content import ContentError
from .dialogue import BODY_FONT, DUET_RING_SCALE, NOTE_CODE
from .dialogue_animation import BOX_TRAVEL_MS
from .dialogue_notice import NOTICE_FONT, NOTICE_STYLE, NoticeMotion, hd_letter_state, notice_lifetime
from .fonts import TextStyle
from .games import GAMES
from .menu import MenuStrings
from .portrait_effects import BALL_FRAMES, BALL_UNITS, STARBURST_FRAME, ball_alpha, starburst
from . import emoticon_effects
from .ui_assets import ImagePack, Raster, Rect, UIAssetError, read_ui


def _decoded_size(data: bytes) -> tuple[int, int]:
    if data.startswith((b'\x89PNG', b'\xff\xd8')):
        return pygame.image.load(BytesIO(data)).get_size()
    frame = ImagePack.parse(data).images[0]
    return frame.width, frame.height


# Android's fixed portrait-mask reference (resource 268, 128x150). Every
# ring/border/panel around a portrait keeps this apparent size regardless
# of which actual mask ends up doing the clipping -- content.py's
# ContentLibrary.hd_asset() may transparently hand back a real HD-native
# mask (id 311, a clean 256x300) for the same call when an HD ipa was
# imported, but the scale a portrait gets rendered at must always be
# relative to this fixed constant, not to whichever mask happens to be
# loaded. See legacy/findings.md, "HD chrome assets may be directly usable
# after all".
ANDROID_MASK_SIZE = (128, 150)
# shshd-runtime: where a translated speaker's emoticon (draw_portrait_effect) is anchored, as fractions of the portrait
# housing's width (toward the box) and height (up) from its center: the ring's upper corner on the box's side.
EFFECT_ANCHOR = (0.30, 0.30)


class DialogueRenderer:
    portrait_factor = 1             # every portrait's scale on this line (a two-speaker line's: DUET_RING_SCALE)
    # shshd-runtime: (animation, partner, portrait factor) of the line last drawn, and of the one before it, whose
    # portraits zoom out at their own size under the next line (a two-speaker line's partner with its speaker).
    _line = _leaving = None
    gear_pressed = False    # set by Desktop while the pause gear is held
    def __init__(self, resources, text_renderer, image_loader, scale=1):
        self.resources = resources
        self.text = text_renderer
        self.image = image_loader
        # Pixels per logical (320x480) unit. Every position and size in this
        # renderer is still written in logical units; `scale` only sets how
        # many real pixels each one gets, so HD art (2x the Android pixel
        # size) can be drawn at its own density instead of being shrunk to
        # 1x here and stretched back up later.
        self.scale = scale
        # SRCALPHA: the background is composited separately by Desktop, at
        # real window resolution instead of this canvas's fixed 320x480, so
        # this canvas must stay transparent where the background belongs.
        size = (320 * scale, 480 * scale)
        # HD's frame is 32 units wider than the UI column on each side, and its
        # portrait housing reaches into those margins (the ring sits at x = -7
        # on the left, 199..327 on the right). `wide` is the whole frame's
        # width; `canvas` is a view of its column, so everything written in
        # column coordinates still is, and only what crosses the column edge
        # draws on `wide` with `margin` added.
        self.margin = round(32 * scale)
        self.wide = pygame.Surface((320 * scale + 2 * self.margin, 480 * scale), pygame.SRCALPHA).convert_alpha()
        self.canvas = self.wide.subsurface((self.margin, 0, *size))
        self.cached_key = None
        self.cached_page = None
        self.name_layer = pygame.Surface(size, pygame.SRCALPHA).convert_alpha()
        self.pending_background = None

    def draw_background(self, target, engine):
        background = self.image(engine.panel.background_id)
        if background is not None:
            x, y = engine.background_pan.origin(*background.get_size())
            # exp-runtime v0.6.0: Android stretches some locations' X axis (profile BACKGROUND_SCALE_X), aligned by the
            # unscaled width.
            scale = getattr(GAMES[engine.game_key], 'BACKGROUND_SCALE_X', {}).get(engine.panel.background_id, 1)
            if scale != 1:
                width = background.get_width()
                background = self.scaled_background(engine.panel.background_id, scale)
                x = round(x + (width - background.get_width()) / 2)
            target.blit(background, (x, y))

    @lru_cache(maxsize=8)
    def scaled_background(self, asset_id, scale):
        image = self.image(asset_id)
        return pygame.transform.smoothscale(image, (round(image.get_width() * scale), image.get_height()))

    @staticmethod
    def background_origin(background, engine):
        """The panned background's center in UI units (BackgroundPan), for Desktop's window-resolution compositing,
        which treats any image as 480 units wide. With an HD bundle, Desktop replaces x with HD's own location pan
        (location_pan.py) for this node centered at y 180."""
        if background is None:
            return 160, 180
        width, height = background.get_size()
        width, height = 480, round(height * 480 / width)
        x, _ = engine.background_pan.origin(width, height)
        return x + width / 2, 180

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
    @lru_cache(maxsize=8)
    def note_image(self, frame, tint=None):
        """Pack 155's song note (dialogue.NOTE_FRAMES); `tint` recolors it, keeping its alpha (the gold fonts' note)."""
        image = self.frame_native(155, frame)
        if tint is None:
            return image
        image = image.copy()
        image.fill(tuple(tint[:3]) + (0,), special_flags=pygame.BLEND_RGBA_MAX)
        image.fill(tuple(tint[:3]) + (255,), special_flags=pygame.BLEND_RGBA_MIN)
        return image

    def frame_native(self, asset_id, index):
        """The frame at whatever density read_asset() actually returned --
        including a real HD substitute (content.HD_ASSET_MAP), which for
        chrome packs is 2x the Android original's pixel size. Cause of Death
        with the SHS HD art source takes its common frames' 2x stand-ins
        (cod_hd_common)."""
        if asset_id == 126 and self.cod_hd_common() is not None:
            from .cod.hd_art import BAR_CAP, BAR_FRAME, BAR_STRIP, BAR_STRIP_TOP, COMMON_FRAMES
            if index in COMMON_FRAMES:
                return self.frame_native('cod-hd', COMMON_FRAMES[index])
            if index == BAR_FRAME:
                cap, strip = self.frame_native('cod-hd', BAR_CAP), self.frame_native('cod-hd', BAR_STRIP)
                original = self._android_pack(126).images[BAR_FRAME]
                bar = pygame.Surface((original.width * 2, original.height * 2), pygame.SRCALPHA).convert_alpha()
                bar.blit(cap, (0, 0))
                bar.blit(pygame.transform.smoothscale(strip, (bar.get_width() - cap.get_width(), strip.get_height())),
                         (cap.get_width(), BAR_STRIP_TOP * 2))
                return bar
        frame = (self.cod_hd_common() if asset_id == 'cod-hd' else self.pack(asset_id)).images[index]
        return pygame.image.frombytes(frame.pixels, (frame.width, frame.height), frame.mode).convert_alpha()

    @lru_cache(maxsize=1)
    def cod_hd_common(self):
        """CoD's common frames at 2x (ContentLibrary.cod_hd_common), parsed, or None."""
        library = getattr(self.resources, 'library', self.resources)
        try:
            data = library.cod_hd_common()
        except (AttributeError, ContentError, ValueError):
            return None
        return None if data is None else ImagePack.parse(data)

    def game_id(self):
        return getattr(getattr(self.resources, 'library', self.resources), 'game_id', 'shs')

    def ios_housing(self):
        """Whether portraits sit in SHSPortraitLayer's housing (hd_portrait, the ring clipped against the bubble):
        SHS HD, and Cause of Death, whose iPhone build has the same layer, always."""
        return self.hd_chrome() or self.game_id() == 'cod'

    @lru_cache(maxsize=8)
    def _android_pack(self, asset_id):
        return ImagePack.parse(self.resources.android_asset(asset_id))

    def logical_size(self, asset_id, index):
        """The frame's size in the 320x480 layout units every renderer's
        geometry is written in: the Android original's own pixel size. An
        HD substitute is 2x that many pixels for the same logical size."""
        native = self.frame_native(asset_id, index)
        from .cod.hd_art import BAR_FRAME, COMMON_FRAMES
        if asset_id == 126 and (index in COMMON_FRAMES or index == BAR_FRAME) and self.cod_hd_common() is not None:
            # A 2x stand-in keeps its own size, as SHS HD draws it: the timer wedges are not exact doubles (19x50 for
            # 10x25) and only tile into a clean circle at theirs.
            return native.get_width() / 2, native.get_height() / 2
        try:
            original = self._android_pack(asset_id).images[index]
        except (ContentError, AttributeError, IndexError, ValueError):
            return native.get_size()
        return original.width, original.height

    @lru_cache(maxsize=64)
    def frame(self, asset_id, index):
        """The frame at logical (Android) size, whatever density was loaded.

        Before this, an HD-substituted chrome pack came back at its native
        2x pixel size and every caller drew it as if it were 1x -- e.g. box
        borders twice as thick as they should be (measured against a real
        HD screenshot: ~2.7 logical px, this build drew ~6).
        """
        return self.frame_scaled(asset_id, index, 1)

    @lru_cache(maxsize=128)
    def frame_scaled(self, asset_id, index, scale):
        """The frame sized for a canvas with `scale` pixels per logical
        unit, resampled once from the densest source available."""
        native = self.frame_native(asset_id, index)
        width, height = self.logical_size(asset_id, index)
        size = max(1, round(width * scale)), max(1, round(height * scale))
        return native if native.get_size() == size else pygame.transform.smoothscale(native, size)

    # FUN_0005afbc removes the final 12 rows of a masked portrait before
    # FUN_0009c034 aligns it to the ring (Android 1.0.9; upstream's decompile
    # of the same routine, and this build's HD-photo-measured anchor, agree:
    # cropped art aligned to the inner ring's bottom == uncropped art aligned
    # to the outer ring's). Applied only on request, so panels with no
    # verified native crop keep the whole cutout.
    PORTRAIT_CROP_ROWS = 12

    def portrait_source(self, asset_id):
        """(image, logical_size): the portrait's own pixels and the layout units they occupy, or None."""
        image = self.image(asset_id)
        if image is None:
            return None
        # The portrait's logical size (the layout units it occupies) is its
        # own pixel size at the density it ships in: HD art is 2x, so 226x256
        # is 113x128 units; Android art is 1x. Measured against a real HD
        # photo of the player avatar (reference/IMG_0069.PNG). An HD substitute
        # is recognized as art larger than its Android original; art inside an
        # episode file has no Android copy and is judged against the mask.
        width, height = image.get_size()
        # shshd-runtime: a translated episode's hi-res portrait (EpisodeResources.standard_portrait) fills its own
        # portrait's height, in its own proportions, so either set sits the same in the ring.
        standard = getattr(self.resources, 'standard_portrait', lambda _: None)(asset_id)
        if standard is not None:
            standard_size = self._episode_portrait_size(Raster(*_decoded_size(standard), b''))
            return image, (width * standard_size[1] / height, standard_size[1])
        try:
            android_size = _decoded_size(self.resources.android_asset(asset_id))
            hd_art = width > android_size[0] or height > android_size[1]
            return image, ((width / 2, height / 2) if hd_art else (width, height))
        except (ContentError, pygame.error, OSError, AttributeError):
            return image, self._episode_portrait_size(Raster(width, height, b''))

    @lru_cache(maxsize=32)
    def portrait(self, asset_id, flipped, density=1, *, crop=False):
        source = self.portrait_source(asset_id)
        if source is None:
            return None
        image, logical_size = source
        raster = Raster(*image.get_size(), pygame.image.tobytes(image, 'RGBA'))
        # self.pack(268) already transparently prefers a real HD-native mask
        # (content.py's ContentLibrary.hd_asset()) over Android's 128x150
        # original when an HD ipa was imported -- no separate fetch needed
        # here. (The HD player composes its portraits with hd_portrait instead.)
        mask = self.pack(268).images[0]
        # `density` is pixels per logical unit of the canvas this will be
        # drawn on: the result comes back at logical_size * density, so a 2x
        # canvas gets the HD pixels instead of a copy already shrunk to 1x,
        # and 1x art (a standard episode's own portrait with no HD twin, e.g.
        # As Time Goes By's Mr. Hotpants) is enlarged to fill the same ring
        # instead of being drawn at half size.
        scale = max(raster.width / logical_size[0], raster.height / logical_size[1]) / density
        if raster.width > mask.width or raster.height > mask.height:
            mask = self._scaled_mask(mask, raster.width, raster.height)
        masked = raster.portrait_mask(mask)
        # Match the display format after creating the masked RGBA buffer.
        # Cocoa's opaque BGRA canvas can otherwise copy transparent RGB
        # instead of blending it, exposing white pixels and black mask corners.
        image = pygame.image.frombytes(masked.pixels, (masked.width, masked.height), 'RGBA').convert_alpha()
        if abs(scale - 1.0) > 1e-9:
            # An HD portrait is real extra pixels, not a bigger portrait --
            # every ring/border/panel around it is still Android-sized, so
            # rendering it at native density makes it comically oversized
            # relative to everything else. Scale the finished cutout back
            # down to the size an Android portrait would have occupied;
            # the supersampled source still buys cleaner mask-edge
            # antialiasing than a native low-res portrait would have had.
            size = max(1, round(image.get_width() / scale)), max(1, round(image.get_height() / scale))
            image = pygame.transform.smoothscale(image, size)
        if crop:
            # 12 logical rows, in this canvas's pixels (density per unit).
            height = image.get_height() - self.PORTRAIT_CROP_ROWS * density
            if height <= 0:
                raise UIAssetError(f'Portrait height {image.get_height()} cannot accommodate the native crop')
            image = image.subsurface((0, 0, image.get_width(), height))
        return pygame.transform.flip(image, flipped, False) if flipped else image

    @staticmethod
    def _episode_portrait_size(raster):
        """The Android-scale size of art that ships inside an episode file.

        Downloadable HD episodes carry their portraits already at 2x
        (226x256, 256x256, ...) with no density field and no separate
        Android copy to compare against. The available Android engine
        loads them unscaled, so an oversized cutout that fits within twice
        the 128x150 mask is 2x art (imported New Girl's variants are the
        documented case, see docs/UI_ASSETS.md); anything else keeps the
        mask's own size as the reference.
        """
        mask_w, mask_h = ANDROID_MASK_SIZE
        if raster.width <= mask_w and raster.height <= mask_h:
            return raster.width, raster.height              # 1x art: its own size
        if raster.width <= 2 * mask_w and raster.height <= 2 * mask_h:
            return round(raster.width / 2), round(raster.height / 2)
        return ANDROID_MASK_SIZE

    @staticmethod
    def _scaled_mask(mask, width, height):
        """HD portrait art (per-episode, >=26000) ships well past the
        Android-reference 128x150 mask. Scale the mask's geometry up to
        cover it instead: the mask is a plain rounded cutout shape (see
        docs/UI_FIDELITY.md), not detailed art, so smooth-scaling it loses
        nothing a native HD-resolution mask would have shown. This avoids
        depending on the iOS HD build's own low-id chrome container format,
        which is a different, undeciphered layout from Android's (see
        legacy/findings.md, "HD retargeting feasibility") -- used as a
        fallback when no verified HD-native mask is available (see
        _hd_mask).
        """
        scale = max(width / mask.width, height / mask.height)
        if width <= 2 * ANDROID_MASK_SIZE[0] and height <= 2 * ANDROID_MASK_SIZE[1]:
            # 2x art: the mask's own 2x, which is what a real HD mask is.
            scale = max(scale, 2 * ANDROID_MASK_SIZE[0] / mask.width)
        size = max(mask.width, round(mask.width * scale)), max(mask.height, round(mask.height * scale))
        # pygame has no single-channel surface format; replicate the 'A'
        # bytes across RGB, scale, then take one channel back out.
        rgb = b''.join(bytes([value, value, value]) for value in mask.pixels)
        surface = pygame.transform.smoothscale(pygame.image.frombytes(rgb, (mask.width, mask.height), 'RGB'), size)
        scaled = pygame.image.tobytes(surface, 'RGB')
        return Raster(*size, bytes(scaled[index] for index in range(0, len(scaled), 3)), mode='A')

    # SHSPortraitLayer (HD 1.4.38), in iPad points (2 per layout unit). The housing is layout 11 node 1, a 256-point
    # square holding the ring (frame 46) and the 210-point disc. Each expression is drawn in its own 256x320 character
    # layer anchored at its bottom centre, which `init` (00056b58) puts on the housing's bottom centre. Its
    # `drawLayer:inContext:` (00056914) first clips to the mask, the master image's frame 0 (resource 311,
    # 256x300), at (0, 20) -- layout 11 node 2 at (0, -44) in the housing. It then translates to
    # ((256 - width) / 2, 318 - height) and draws the portrait at its own size, so every portrait's bottom sits 2
    # points above the housing's bottom edge, whatever its height. A right-hand speaker (side 2, theme != 3) is
    # mirrored in place by a CTM flip made after the clip, so the mask itself is never mirrored.
    # CGContextClipToMask with a CGImageMaskCreate mask is soft: sample 0 paints, 255 clips, and values between
    # blend.
    # Cause of Death's iPhone SHSPortraitLayer (1.3.4 `init` 0004c680, `drawLayer:inContext:` 0004c3f0) is the same
    # layer at 1 point per unit: 128x160, mask frame 0 at (0, 10, 128, 150) -- the HD numbers halved -- but it
    # translates to 160 - height, so its portraits sit flush on the housing's bottom edge (COD_PORTRAIT_BOTTOM).
    HD_PORTRAIT_LAYER = (256, 320)
    HD_PORTRAIT_MASK = (0, 20, 256, 300)
    HD_PORTRAIT_BOTTOM = 318
    COD_PORTRAIT_BOTTOM = 320

    @lru_cache(maxsize=32)
    def hd_portrait(self, asset_id, flipped, density):
        """(layer, lift): HD's character layer in canvas pixels (`density` per unit). Its left, right and bottom
        edges are the housing's; its top is `lift` pixels above the housing's (64 units). None without art.

        The art is drawn at its logical size (portrait_source). A standard episode's 1x art is therefore enlarged
        to HD's 2x like everything else, and the composition is the same for every source density.
        """
        source = self.portrait_source(asset_id)
        if source is None:
            return None
        image, (width, height) = source
        layer_w, layer_h = self.HD_PORTRAIT_LAYER
        k = density / 2                                 # canvas pixels per point
        layer = pygame.Surface((round(layer_w * k), round(layer_h * k)), pygame.SRCALPHA).convert_alpha()
        size = max(1, round(width * density)), max(1, round(height * density))
        art = image if image.get_size() == size else pygame.transform.smoothscale(image, size)
        if flipped:
            art = pygame.transform.flip(art, True, False)
        # C integer division: (256 - w) / 2 truncates toward zero.
        x = int((layer_w - round(width * 2)) / 2)
        bottom = self.HD_PORTRAIT_BOTTOM
        if self.game_id() == 'cod':
            x, bottom = 2 * int((layer_w / 2 - round(width)) / 2), self.COD_PORTRAIT_BOTTOM   # truncated in units
        layer.blit(art, (round(x * k), round((bottom - round(height * 2)) * k)))
        mask = self.pack(268).images[0]
        mx, my, mw, mh = self.HD_PORTRAIT_MASK
        shape = pygame.image.frombytes(bytes(b for value in mask.pixels for b in (255, 255, 255, 255 - value)),
                                       (mask.width, mask.height), 'RGBA')
        shape = pygame.transform.smoothscale(shape, (round(mw * k), round(mh * k)))
        clip = pygame.Surface(layer.get_size(), pygame.SRCALPHA).convert_alpha()
        clip.fill((255, 255, 255, 0))                   # nothing outside the mask's rectangle is drawn
        clip.blit(shape, (round(mx * k), round(my * k)))
        layer.blit(clip, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        return layer, round((layer_h - layer_w) * k)

    def portrait_rect(self, image, center=(0, 0), density=1):
        """FUN_0009c034 positions the sprite center within the bubble.

        The native routine halves the ring's and the (cropped) texture's
        heights separately, so odd heights land where they do natively.
        """
        x, y = center
        offset = self.frame_scaled(126, 39, density).get_height() // 2 - image.get_height() // 2
        return image.get_rect(center=(x, y + offset))

    def box_alpha(self):
        """HD's bubble is 243/255 opaque (`0xf3ffffff`, the same as its choice panel); Android's is solid."""
        try:
            return 243 if self.hd_chrome() else 255
        except (AttributeError, ContentError, ValueError):
            return 255

    def box(self, target, rect, theme, *, alpha=255, scale=1):
        """FUN_00081920 places the eight border pieces outside the center.

        `rect` is in logical units; `scale` is the target's pixels per
        logical unit. Pieces are sized from the logical (Android) frame
        size times `scale`, resampled once from the densest source.
        """
        pack = {1: 204, 2: 220, 3: 252}.get(theme, 236)
        x, y, width, height = (round(v * scale) for v in (rect.x, rect.y, rect.width, rect.height))
        center = self.frame_scaled(126, 0, scale).copy()
        center = faded(center, alpha)
        target.blit(pygame.transform.scale(center, (width, height)), (x, y))
        # HD's border art already carries its 242/255 translucency; only the (opaque) center takes the
        # bubble's alpha, so edges and middle show the scene equally (message-panel photos IMG_0240-0242).
        piece_alpha = 255 if self.hd_chrome() else alpha
        for index, column, row in ((6, 0, 0), (7, 1, 0), (8, 2, 0), (4, 0, 1),
                                   (5, 2, 1), (0, 0, 2), (1, 1, 2), (2, 2, 2)):
            image = self.frame_scaled(pack, index, scale).copy()
            image = faded(image, piece_alpha)
            w, h = image.get_size()
            size = (width if column == 1 else w, height if row == 1 else h)
            position = (x - w if column == 0 else x + width if column == 2 else x,
                        y - h if row == 0 else y + height if row == 2 else y)
            target.blit(pygame.transform.scale(image, size) if size != (w, h) else image, position)

    # The bottom border strip is 10 logical px tall; its colored line sits
    # ~8.25 logical px into it (padding baked into the art), measured by
    # sampling this renderer's own canvas. Anything positioned against the
    # box's *visible* bottom edge starts from rect.bottom + this.
    BORDER_LINE_OFFSET = 8.25

    def portrait_group(self, portrait):
        """The art and both rings as one layer (see portrait_layers)."""
        rings, art, topleft = self.portrait_layers(portrait)
        layer = rings.copy()
        layer.blit(art, (0, 0))
        return layer, topleft

    # HD's portrait housing (`SHSPortraitLayer.drawInContext`, 000564bc): the
    # outer ring is frame 46 of pack 155 (Android's 37, renumbered; a 256x256
    # white ring, 128 layout units, with none of the transparent margin of the
    # stretched Android frame), and the disc is NOT an image but
    # `CGContextFillEllipseInRect`, 210 device px (105 units) wide, filled by
    # the speaker's theme: 1 blue, 2 pink, otherwise gray. The ring is clipped
    # even-odd against the dialogue bubble (`clipPortraitHousingAgainstBubble`)
    # so it is never drawn inside the box; the disc is filled after the clip
    # is restored and is not clipped.
    _HD_RING = 46
    DISC_UNITS = 105
    DISC_COLORS = {1: (188, 214, 226), 2: (246, 174, 168)}
    DISC_GRAY = (142, 155, 156)

    def ring_frame(self, k):
        return self._hd_frame(self._HD_RING, k) if self.hd_chrome() else self.frame_scaled(126, 37, k)

    @lru_cache(maxsize=16)
    def disc_frame(self, theme, k):
        """The inner disc for `theme` at `k` pixels per unit: a vector-drawn
        circle in HD (antialiased by 4x supersampling), Android's frame
        38/39/40 otherwise. Cause of Death still draws its frames (one flat
        grey each); with the SHS HD art source they become the same vector
        circle in the frame's own colour."""
        index = {1: 38, 2: 39}.get(theme, 40)
        cod_hd = not self.hd_chrome() and self.cod_hd_common() is not None
        if not self.hd_chrome() and not cod_hd:
            return self.frame_scaled(126, index, k)
        diameter = max(1, round(self.DISC_UNITS * k))
        big = pygame.Surface((diameter * 4, diameter * 4), pygame.SRCALPHA)
        if cod_hd:
            frame = self._android_pack(126).images[index]
            at = ((frame.height // 2) * frame.width + frame.width // 2) * 4
            color = tuple(frame.pixels[at:at + 3])
        else:
            color = self.DISC_COLORS.get(theme, self.DISC_GRAY)
        pygame.draw.circle(big, (*color, 255), (diameter * 2, diameter * 2), diameter * 2)
        return pygame.transform.smoothscale(big, (diameter, diameter))

    @staticmethod
    def bubble_polygon(box, corner=5):
        """The housing's clip outline in layout units (`clipPortraitHousingAgainstBubble` + `clipPortraitHousing`): the
        bubble layer's frame, which is the box grown by its 10-unit border, inset 6 points (3 units) on every side,
        so 7 units past the box; the two top corners are cut 10 points (5 units). The ring is therefore drawn over
        the border's outer few units, and the colored border line, as in the owner's photos. Cause of Death's
        iPhone build (1.3.4 00010768/00010850, `drawInContext:` 0004bfcc) uses the same points at 1 per unit:
        the same 7-unit outline with 10-unit corners (housing_polygon)."""
        x0, y0, x1, y1 = box.x - 7, box.y - 7, box.x + box.width + 7, box.y + box.height + 7
        return [(x0, y1), (x0, y0 + corner), (x0 + corner, y0), (x1 - corner, y0), (x1, y0 + corner), (x1, y1)]

    def housing_polygon(self, box):
        return self.bubble_polygon(box, 10 if self.game_id() == 'cod' else 5)

    def portrait_layers(self, portrait):
        """(rings, art, topleft) with the ring and disc merged (see portrait_parts)."""
        ring, disc, art, topleft = self.portrait_parts(portrait)
        rings = ring.copy()
        rings.blit(disc, (0, 0))
        return rings, art, topleft

    @lru_cache(maxsize=32)
    def portrait_parts(self, portrait):
        """(ring, disc, art, topleft): three same-sized layers sharing one
        bounds rectangle (the pieces are children of the native scaled node);
        separate surfaces because HD draws the rings beneath the body text,
        clips only the ring against the bubble, and puts the portrait art
        above the relationship icon.

        Built in canvas pixels (logical units times self.scale)."""
        k = self.scale
        rings = [self.ring_frame(k), self.disc_frame(portrait.theme, k)]
        flipped = portrait.mode == 2 and portrait.theme != 3
        pieces = [(ring, ring.get_rect(center=(0, 0))) for ring in rings]
        image = None
        if self.ios_housing():
            # SHSPortraitLayer's own composition (hd_portrait); the housing is the ring frame's square.
            composed = self.hd_portrait(portrait.asset_id, flipped, k)
            if composed is not None:
                art, lift = composed
                housing = pieces[0][1]
                pieces.append((art, art.get_rect(topleft=(housing.x, housing.y - lift))))
        else:
            image = self.portrait(portrait.asset_id, flipped, k, crop=True)
        if image is not None:
            # The cropped art's bottom aligns to the inner ring's (frame 39,
            # 105px). Without the native 12-row crop that alignment sat the
            # art ~12px too high, letting hair spill out above the outer ring
            # (frame 37, 128px) with a gap of backdrop below the chin; with
            # it, the visible art ends where uncropped art aligned to the
            # outer ring would. Both were confirmed independently: this by
            # decompiling FUN_0005afbc/FUN_0009c034, the other against a
            # real-device screenshot of this exact dialogue line
            # (reference/football_star_beth_greeting_hd.webp), where the
            # real hair just grazes the outer ring's own edge.
            pieces.append((image, self.portrait_rect(image, density=k)))
        bounds = pieces[0][1].unionall([rect for _, rect in pieces[1:]])
        layers = []
        for group in (pieces[:1], pieces[1:2], pieces[2:]):
            layer = pygame.Surface(bounds.size, pygame.SRCALPHA).convert_alpha()
            for piece, rect in group:
                layer.blit(piece, rect.move(-bounds.x, -bounds.y))
            layers.append(layer)
        return layers[0], layers[1], layers[2], bounds.topleft

    # The Android layout bank's own portrait housing rect floats the portrait
    # ring higher above the dialogue box than the real HD build does. Measured
    # against two real-device HD photos of named dialogue (reference/IMG_0069.PNG
    # "You", IMG_0070.PNG "Adam"), whose UI is 1.94/2.98 px per layout unit
    # depending on the crop: HD's ring center sits ~1.5 units below the box's top
    # line (ring diameter 127 units, matching frame 37's 128). This renderer's
    # top line is 287.25 units down and the housing rect's center is 284 - 5, so
    # the offset that reproduces HD is ~5. (The original 29 was calibrated
    # against the old, too-thick box borders; 18 and 9 were intermediate
    # readings taken by eye, the latter measured against the rendered layer
    # itself.) With it, text lines 1-3 of the standard three-line dialogue clear
    # the ring as they do in HD. See legacy/findings.md, "The dialogue
    # portrait sits too high above the box".
    _HD_PORTRAIT_VERTICAL_OFFSET = 5

    def _portrait_rect(self, mode):
        """The housing rect for the portrait ring, the relationship icon and
        the notice label alike -- all three are positioned relative to this
        same native rect, so the HD vertical correction lives here once
        instead of being repeated at each call site.
        """
        rect = self.resources.dialogue_layout().bank.rectangle(17, 0x30 if mode == 1 else 0x4e)
        return Rect(rect.x, rect.y + self._HD_PORTRAIT_VERTICAL_OFFSET, rect.width, rect.height)

    # HD's common-frame pack (155) draws the bottom bar and the settings gear
    # at 2x, with different frame numbers than Android's pack 126: the bar is
    # a 64x49-unit left cap with the gear's notch (55) followed by a 64x24
    # strip (56) stretched across the rest (Android's frame 47 is one 320x49
    # piece whose straight part starts 25 units down); the gear is frame 58
    # (exactly twice Android 49's 74x72) and 59 is the same gear with the
    # yellow pressed glow. See legacy/findings.md, "HD resource 155".
    _HD_BAR_CAP, _HD_BAR_STRIP, _HD_GEAR, _HD_GEAR_PRESSED = 55, 56, 58, 59
    # Layout 17 places frame 58 at 74x72 units, and a grid search against an HD
    # photo (IMG_0091) confirms the scale (1.0) and puts its box 6.5 units left
    # of and 4 below the layout's (3, 437), i.e. (-3.5, 441): the left teeth run
    # off the screen and the bottom is 1 unit past the frame's edge.
    _HD_GEAR_SCALE = 1.0
    _HD_GEAR_ORIGIN = (-3.5, 441 - 512)

    def has_hd_bundle(self):
        """Whether an HD app bundle supplies pack 155 (cached: finding out reads the bundle)."""
        if getattr(self, '_has_hd_bundle', None) is None:
            try:
                self._has_hd_bundle = self.resources.hd_asset(155) is not None
            except (AttributeError, ContentError, ValueError):
                self._has_hd_bundle = False
        return self._has_hd_bundle

    def hd_chrome(self):
        # Asked several times a frame; the answer only depends on the imported bundle, and finding it means
        # reading (and inflating) a member of the app bundle, so it is remembered.
        if getattr(self, '_hd_chrome', None) is None:
            try:
                self._hd_chrome = (self.resources.hd_asset(155) is not None
                                   and len(self.pack(155).images) > 59)
            except (AttributeError, ContentError, ValueError):
                self._hd_chrome = False
        return self._hd_chrome

    def hd_bar(self):
        """The pack holding HD's bar cap, strip and gear: SHS HD's 155, Cause of Death's derived stand-ins
        ('cod-hd', the same bar and CoD's grey gear) with the SHS HD art source, or None for Android's bar."""
        if self.hd_chrome():
            return 155
        return 'cod-hd' if self.cod_hd_common() is not None else None

    def _hd_frame(self, index, scale, pack=155):
        """HD pack-155 frame `index` at `scale` pixels per layout unit (the
        frames ship at 2x)."""
        native = self.frame_native(pack, index)
        size = max(1, round(native.get_width() / 2 * scale)), max(1, round(native.get_height() / 2 * scale))
        return native if native.get_size() == size else pygame.transform.smoothscale(native, size)

    def draw_bottom_bar(self, canvas, scale=None, *, gear_pressed=False):
        """The bar along the screen's bottom edge and the gear over its left
        end, in HD's own art when an HD bundle is imported."""
        k = self.scale if scale is None else scale
        pack = self.hd_bar()
        if pack is not None:
            cap = self._hd_frame(self._HD_BAR_CAP, k, pack)
            canvas.blit(cap, (0, round(431 * k)))
            left = cap.get_width()
            strip = pygame.transform.smoothscale(self._hd_frame(self._HD_BAR_STRIP, k, pack),
                                                 (max(1, round(320 * k) - left), max(1, round(24 * k))))
            canvas.blit(strip, (left, round(456 * k)))
            self.draw_gear(canvas, k, pressed=gear_pressed)
        else:
            canvas.blit(self.frame_scaled(126, 47, k), (0, round(431 * k)))
            canvas.blit(self.frame_scaled(126, 49, k), (0, round(408 * k)))

    def _hd_gear(self, k, pressed=False):
        native = self.frame_native(self.hd_bar(), self._HD_GEAR_PRESSED if pressed else self._HD_GEAR)
        size = (max(1, round(native.get_width() / 2 * self._HD_GEAR_SCALE * k)),
                max(1, round(native.get_height() / 2 * self._HD_GEAR_SCALE * k)))
        return pygame.transform.smoothscale(native, size)

    def draw_gear(self, canvas, scale=None, *, pressed=False):
        k = self.scale if scale is None else scale
        if self.hd_bar() is not None:
            gear = self._hd_gear(k, pressed)
            canvas.blit(gear, (0, round(480 * k) - gear.get_height()))
        else:
            canvas.blit(self.frame_scaled(126, 49, k), (0, round(408 * k)))

    FOOTER_FONT = 'ArialMT11'
    FOOTER_COLOR = (185, 185, 185)

    @lru_cache(maxsize=1)
    def menu_strings(self):
        try:
            return MenuStrings.load(self.resources.library)
        except (AttributeError, ContentError, ValueError):
            return None

    def footer_hint(self, index, fallback):
        """Bank-13 string `index` (36 "Touch the screen to continue", 38 "Touch
        the best choice", 40 "Touch choice before time runs out"), or the
        English `fallback` when the bank is unavailable. Indices are SHS's
        roles; MenuStrings.load maps them to Cause of Death's bank, which
        lacks three of SHS's strings and so sits three lower here."""
        strings = self.menu_strings()
        try:
            return strings[index]
        except (TypeError, ValueError, ContentError):
            return fallback

    # HD's bottom bar and gear anchor to the edges of its 384x512-unit frame,
    # 32 layout units wider on each side than the 320-unit UI column.
    EDGE_UNITS = 32

    @lru_cache(maxsize=16)
    def bottom_bar_layer(self, text, gear_pressed=False, bar=True):
        """The bar, gear and hint as one layer 384 units wide and 72 tall, to
        be placed along the bottom of the frame. HD's bar runs edge to edge
        with the gear flush at the left; Android's 320-unit bar sits in the UI
        column, 32 units in. Cause of Death with the SHS HD art source takes
        HD's layout (its bar is SHS's), so the bar fills the 3:4 frame too."""
        k, edge = self.scale, self.EDGE_UNITS
        layer = pygame.Surface((round((320 + 2 * edge) * k), round(72 * k)), pygame.SRCALPHA).convert_alpha()
        pack = self.hd_bar()
        if pack is not None:
            if bar:
                cap = self._hd_frame(self._HD_BAR_CAP, k, pack)
                layer.blit(cap, (0, round(23 * k)))
                strip = self._hd_frame(self._HD_BAR_STRIP, k, pack)
                width = layer.get_width() - cap.get_width()
                layer.blit(pygame.transform.smoothscale(strip, (width, round(24 * k))),
                           (cap.get_width(), round(48 * k)))
            gear = self._hd_gear(k, gear_pressed)
            layer.blit(gear, (round(self._HD_GEAR_ORIGIN[0] * k), layer.get_height() + round(self._HD_GEAR_ORIGIN[1] * k)))
        else:
            if bar:
                layer.blit(self.frame_scaled(126, 47, k), (round(edge * k), round(23 * k)))
            # Frame 50 is the orange gear held under the pointer (desktop_pause.draw_pause_gear).
            layer.blit(self.frame_scaled(126, 50 if gear_pressed else 49, k), (round(edge * k), 0))
        if not text:
            return layer
        name = self.footer_font()
        hint = self.text.layout(name, text, 246, TextStyle(11, 0, self.FOOTER_COLOR))
        # Cause of Death: the hint sits where CoD puts it within the bar (9 units under the band's top, IMG_0483);
        # the whole bar is 5.5 units lower than CoD's, because it is anchored to the frame's bottom edge as SHS HD's
        # is, not to the iPhone screen's (owner's choice, 2026-10-14: a lifted bar broke the strip's gradient).
        self.text.draw_layout(layer, name, hint, (edge + 63 + (252 - hint.width) / 2) * k,
                              (460 - 408 + 4.5) * k, scale=k)
        return layer

    def footer_font(self):
        """The hint's font key. Both iOS builds draw it in an ArialMT 11 CSFont (CoD engine +0xca48), and both
        `initFonts` build the ArialMT advance table from the Arial Rounded MT Bold face (CoD case 4: `CSFontInfo::init(
        +0x7010, *(+0x208))`; SHS HD 0002b04a, the faceplace text's bug): Arial's letters at Arial Rounded's advances.
        The photos agree: "Touch the screen to continue" is 154.0 units in SHS HD's IMG_0132 / IMG_0133 (Rounded
        advances 154.4, Arial's own 141.2) and 152 points in CoD's IMG_0496. Android's bitmap hint is unaffected."""
        from dataclasses import replace
        fonts = getattr(self.text, 'fonts', None)
        if fonts is None or self.game_id() != 'cod' and not self.has_hd_bundle():
            return self.FOOTER_FONT
        key = self.FOOTER_FONT + '@rounded-advances'
        if key not in fonts:
            try:
                body, rounded = self.text.font(self.FOOTER_FONT), self.text.font('ArialRoundedMTBold11')
            except (ContentError, OSError, ValueError):
                return self.FOOTER_FONT
            glyphs = {code: replace(glyph, advance=rounded.glyphs[code].advance) if code in rounded.glyphs else glyph
                      for code, glyph in body.glyphs.items()}
            # The glyphs keep their own images (an atlas font's rectangles are unchanged).
            self.text.fonts[key] = replace(body, glyphs=glyphs), self.text.fonts[self.FOOTER_FONT][1]
        return key

    def draw_footer_hint(self, text):
        """The bottom bar's hint, centered on x = 189 as layout 18 places it."""
        k = self.scale
        layout = self.text.layout(self.FOOTER_FONT, text, 246, TextStyle(11, 0, self.FOOTER_COLOR))
        self.text.draw_layout(self.canvas, self.FOOTER_FONT, layout, (63 + (252 - layout.width) / 2) * k,
                              460 * k, scale=k)

    def draw_portrait(self, portrait, scale, part='all', clip=None, alpha=255, factor=None):
        """`part` is 'rings', 'art' or both ('all'). `clip` is a polygon in
        layout units that the HD ring is not drawn inside (the bubble). `factor`: the portrait's size on its line
        (shshd-runtime: a leaving two-speaker line's), else this line's."""
        if portrait is None or scale <= 0:
            return
        scale *= self.portrait_factor if factor is None else factor
        rect = self._portrait_rect(portrait.mode)
        cx, cy = rect.center
        cy -= 5  # FUN_000aaa40 uses 485-y when converting to GL.
        ring, disc, art, (x, y) = self.portrait_parts(portrait)
        rings = None
        if part == 'rings' and clip is not None and self.ios_housing():
            k = self.scale
            rings = ring.copy()
            origin = cx * k + x * scale, cy * k + y * scale
            pygame.draw.polygon(rings, (0, 0, 0, 0),
                                [((px * k - origin[0]) / scale, (py * k - origin[1]) / scale) for px, py in clip])
            rings.blit(disc, (0, 0))
        layer = rings if rings is not None else {'rings': None, 'art': art}.get(part)
        if layer is None:
            layer = self.portrait_layers(portrait)[0] if part == 'rings' else self.portrait_group(portrait)[0]
        if scale != 1:
            size = max(1, round(layer.get_width() * scale)), max(1, round(layer.get_height() * scale))
            layer = pygame.transform.smoothscale(layer, size)
        k = self.scale
        if alpha < 255:
            layer = layer.copy()
            layer = faded(layer, alpha)
        self.wide.blit(layer, (round(cx * k + x * scale) + self.margin, round(cy * k + y * scale)))

    def draw_expression_art(self, motion):
        """The portrait's art: the expression it entered with (`initial_portrait`: neutral for a new speaker, else
        the last one shown) until `changeExpression` crossfades to the line's own (requested on the first tick in
        SHS HD and CoD, a second in on Android: DialogueAnimation.expression_ms), on two independent tracks
        (expression_alphas: the new art in over 0.2 s from 0.4 s after the request, the old out over 0.8 s from
        0.6 s). Since exp-runtime v0.6.0 a running crossfade is its own track, which can outlast the line that
        started it, so the pair drawn is the track's (`expression_portraits`)."""
        old, portrait = motion.expression_portraits
        if portrait is None:
            return
        if old is None or old.asset_id == portrait.asset_id:
            self.draw_portrait(portrait, motion.portrait_scale, 'art')
            return
        old_alpha, new_alpha = motion.expression_alphas
        if old_alpha:
            self.draw_portrait(old, motion.portrait_scale, 'art', alpha=old_alpha)
        if new_alpha:
            self.draw_portrait(portrait, motion.portrait_scale, 'art', alpha=new_alpha)

    def draw_emotion(self, motion):
        """The emotion effect behind the art, above the ring and disc (expressions 6 to 9)."""
        portrait = motion.portrait
        old = motion.initial_portrait
        if portrait is None or old is None or old.expression == portrait.expression or not self.hd_chrome():
            return                                 # only an expression change brings its effect
        k = self.scale
        cx, cy = self._portrait_rect(portrait.mode).center
        center = round(cx * k) + self.margin, round((cy - 5) * k)
        burst = starburst(motion.age_ms) if portrait.expression == 6 else None
        if burst is not None:
            scale, degrees = burst
            image = self.frame_native(155, STARBURST_FRAME)
            size = round(image.get_width() / 2 * k * scale), round(image.get_height() / 2 * k * scale)
            image = pygame.transform.rotate(pygame.transform.smoothscale(image, size), -degrees)
            self.wide.blit(image, image.get_rect(center=center))
        alpha = ball_alpha(portrait.expression, motion.age_ms)
        if alpha > 0:
            size = round(BALL_UNITS * k)
            ball = pygame.transform.smoothscale(self.frame_native(155, BALL_FRAMES[portrait.expression]), (size, size))
            ball = faded(ball, round(255 * alpha))
            self.wide.blit(ball, ball.get_rect(center=center))

    def chrome_image(self, asset_id, density=1):
        """Like self.image(), but normalized back to the Android apparent
        size for small UI icons that have no HD-scale compensation of their
        own -- unlike portraits/backgrounds, which are meant to gain real
        extra density and explicitly compensate for it elsewhere. Confirmed
        live: relationship icons (ids 3010-3012) silently double in size
        (22x24 -> 44x48) through the same HD_SHARED_CONTENT_RANGE fallback
        that correctly upgrades backgrounds/portraits, because nothing
        downstream of it was scaling these back down. See
        legacy/findings.md, "Chrome icons render oversized with an HD ipa".

        `density` is the drawing canvas's pixels per logical unit: the icon
        comes back at android_size * density, resampled once from the HD
        source, so a 2x canvas keeps the HD icon's real pixels.
        """
        if asset_id < 0:
            return None
        image = self.image(asset_id)
        if image is None:
            return None
        try:
            android_size = _decoded_size(self.resources.android_asset(asset_id))
        except (ContentError, pygame.error, OSError):
            return image
        size = round(android_size[0] * density), round(android_size[1] * density)
        if image.get_size() != size:
            image = pygame.transform.smoothscale(image, size)
        return image

    def indicator_image(self, asset_id, k):
        """A relationship icon at canvas density: chrome_image() for the APK (and its HD supplement), or the
        iPhone IPA's own UI image (ui_image), which is already at its logical size."""
        library = getattr(self.resources, 'library', self.resources)
        if getattr(library, 'kind', 'apk') != 'ipa':
            return self.chrome_image(asset_id, k)
        icon = self.ui_image(asset_id)
        if icon is None or k == 1:
            return icon
        return pygame.transform.smoothscale(icon, (round(icon.get_width() * k), round(icon.get_height() * k)))

    def relationship_slots(self, mode):
        """Where the relationship icons rest, as offsets from the portrait housing's center in layout units.

        The layout bank carries two separately authored sets of slot nodes, not one mirrored at runtime: 54-57
        sit around the left (mode 1) housing (node 0x30), 0x54-0x57 around the right (mode 2) one (node 0x4e) --
        confirmed by rendering Kelly's own portrait (mode 1) in Battle of the Schools: Girl, whose relationship
        badge clipped off the left edge of the screen while using the mode-2 nodes unconditionally."""
        bank = self.resources.dialogue_layout().bank
        nodes = (54, 55, 56, 57) if mode == 1 else (0x54, 0x55, 0x56, 0x57)
        center = bank.rectangle(17, 0x30 if mode == 1 else 0x4e).center
        return [(bank.rectangle(17, node).center[0] - center[0], bank.rectangle(17, node).center[1] - center[1])
                for node in nodes]

    def draw_portrait_effect(self, session, motion):
        """shshd-runtime: a translated pack's emoticon over the speaker (Session.portrait_effect, emoticon_effects),
        anchored at the portrait ring's upper corner on the box's side and drawn over the art, in layout units like the
        portrait itself. Nothing before the portrait has come in, or without the pack's image."""
        effect = session.portrait_effect() if hasattr(session, 'portrait_effect') else None
        if effect is None or motion.portrait is None:
            return
        number, asset_id = effect
        image = self.image(asset_id)
        if image is None:
            return
        rect = self._portrait_rect(motion.portrait.mode)
        side = 1 if motion.portrait.mode == 1 else -1      # a left portrait's box is to its right
        k = self.scale * self.portrait_factor
        ax = rect.center[0] + side * rect.width * EFFECT_ANCHOR[0]
        ay = rect.center[1] - 5 - rect.height * EFFECT_ANCHOR[1]
        for sprite in emoticon_effects.sprites(number, motion.age_ms - emoticon_effects.start_ms(motion)):
            size = max(1, round(emoticon_effects.SIZE * sprite.scale * k))
            if size < 2 or sprite.alpha <= 0:
                continue
            icon = pygame.transform.smoothscale(image, (size, size))
            if sprite.rotation:
                icon = pygame.transform.rotate(icon, -sprite.rotation * side)
            if sprite.alpha < 1:
                icon = faded(icon, round(255 * sprite.alpha))
            center = (round((ax + side * sprite.x) * self.scale) + self.margin, round((ay + sprite.y) * self.scale))
            self.wide.blit(icon, icon.get_rect(center=center))

    def draw_relationship(self, motion):
        if motion.relationship is None or motion.portrait is None:
            return
        # Deliberately *not* _portrait_rect(): that method's +29 HD
        # correction pulls the ring/box overlap into line (see
        # _HD_PORTRAIT_VERTICAL_OFFSET), but the relationship icon isn't
        # anchored to the ring the same way -- applying the same shift to
        # it dragged it down onto the speaker name/body text, confirmed
        # against a real-device screenshot of this exact dialogue line
        # (reference/football_star_beth_greeting_hd.webp) where the icon
        # sits above the text, not overlapping it.
        rect = self.resources.dialogue_layout().bank.rectangle(
            17, 0x30 if motion.portrait.mode == 1 else 0x4e)
        if self.hd_chrome():
            # HD's status layers are sublayers of the SHSPortraitLayer, placed by setStatusIconAnimated (00054a30)
            # at layout 17 nodes 0x36-0x39 / 0x54-0x57 less the housing's own origin (50, 503) / (462, 503) points:
            # they share the ring's centre, which draw_portrait puts at _portrait_rect's centre less 5. (Measured
            # against IMG_0070, Adam's skull: 5 units too high before.)
            rect = self._portrait_rect(motion.portrait.mode)
        k = self.scale
        cx, cy = rect.center[0] * k, (rect.center[1] - 5) * k
        # Indicator parents are siblings of the head's scaled node. They
        # appear after its entrance and do not inherit the head-only flip.
        poses = (motion.relationship.hd_poses(self.relationship_slots(motion.portrait.mode),
                                              mirror=motion.portrait.mode == 1) if self.hd_chrome()
                 else motion.relationship.poses())
        ring_under = self.hd_chrome()             # HD's ring-effect layers sit under the icon layers
        for pose in poses:
            icon = self.indicator_image(pose.asset_id, k)
            if icon is None:
                continue
            image = pygame.transform.rotozoom(icon, -pose.rotation, 1)
            center = round(cx + pose.x * k), round(cy + pose.y * k)
            flash = None
            if pose.flash_alpha:
                flash = self.indicator_image(pose.flash_asset, k)
                if flash is not None:
                    flash = pygame.transform.rotozoom(flash, -pose.rotation, pose.flash_scale)
                    flash = faded(flash, pose.flash_alpha)
            if flash is not None and ring_under:
                self.canvas.blit(flash, flash.get_rect(center=center))
            self.canvas.blit(image, image.get_rect(center=center))
            if flash is not None and not ring_under:
                self.canvas.blit(flash, flash.get_rect(center=center))

    def draw_notice(self, engine):
        portrait = engine.dialogue_animation.portrait
        # This label belongs to the current portrait parent, which the native
        # panel hides for narration and dialogue without character artwork.
        # An iOS letter notice keeps the side it started on (engine.notice_mode).
        mode = engine.notice_mode or (portrait.mode if portrait is not None else 0)
        if not engine.notice_ms or not mode:
            return
        motion = NoticeMotion(engine.notice, engine.notice_ms)
        rect = self._portrait_rect(mode)
        k = self.scale
        x, y = (v * k for v in motion.origin(rect, mode))
        # Native alignment 5 is top-left, with no automatic wrapping. Preserve
        # the font's baked-in red lettering and white outline by using white RGB.
        name = self.cod_notice_font() if self.game_id() == 'cod' else None
        name = name or NOTICE_FONT
        layout = self.text.layout(name, engine.notice, 2**31, NOTICE_STYLE)
        font = self.text.font(name)
        if getattr(font, 'source', None) is not None:
            self._draw_hd_notice(engine, layout, font, mode, name)
            return
        for index, glyph in enumerate(layout.glyphs):
            image = self.text._glyph_image(NOTICE_FONT, glyph, motion.scale * k)
            if motion.alpha < 255:
                image = image.copy()
                image = faded(image, motion.alpha)
            self.canvas.blit(image, (round(x + glyph.x * motion.scale * k),
                                     round(y + (glyph.y * motion.scale - motion.glyph_rise(index)) * k)))

    COD_NOTICE_FONT = 'COD_NOTICE'

    def cod_notice_font(self):
        """Cause of Death's letter-effect fonts (`SHSUIDialog::updateFonts` 00038b18, theme 1, which every CoD speaker
        has): TrebuchetMS-Italic 20 in 0xfff0513c with a 1.5 stroke (+0x17328) over its black twin with a 6 stroke
        (+0x18b48). IMG_0412 shows red italic letters edged in black inside a white outline: drawn here as the
        white 6-point outline, the red fill and a black 1.5-point edge. None without vector fonts."""
        library = getattr(self.resources, 'library', self.resources)
        if getattr(self, '_cod_notice', None) is None:
            from .fonts import load_font as base_load_font
            from .vector_text import FaceSource, system_font_path, vector_font
            try:
                path = system_font_path('trebuchet-italic', library)
                if path is None or getattr(library, 'shs_hd_art', None) is None:
                    self._cod_notice = False
                else:
                    base = base_load_font(library, 'TrebuchetMS_Italic16')
                    self.text.register(self.COD_NOTICE_FONT, vector_font(
                        base, FaceSource(path=path, label='cod-notice'), 20, fill=(240, 81, 60), stroke=6 / 20,
                        embolden=1.5 / 20, embolden_color=(0, 0, 0)))
                    self._cod_notice = True
            except (ContentError, OSError, ValueError, pygame.error):
                self._cod_notice = False
        return self.COD_NOTICE_FONT if self._cod_notice else None

    def _draw_hd_notice(self, engine, layout, font, mode, name=NOTICE_FONT):
        """HD's letter effect: `startLetterEffectAnimation` places each letter of the Trebuchet MS Italic fill font
        (dialogue_notice.hd_letter_origins) over the portrait layer's frame, and animates it from the time the
        portrait animation ends plus 0.25 s (dialogue_notice.hd_letter_state, hd_letter_start_ms)."""
        from .dialogue_notice import COD_NOTICE, HD_EMPTY_LETTER, HD_NOTICE, hd_letter_origins, hd_notice_lifetime
        from .vector_text import cap_height
        animation = engine.dialogue_animation
        if animation is None:
            return
        k = self.scale
        elapsed = hd_notice_lifetime(engine.notice) - engine.notice_ms
        cap = cap_height(font) or font.glyph('H').height
        cx, cy = self._portrait_rect(mode).center
        cod = name != NOTICE_FONT
        # The housing in the build's points: HD's 768x1024 frame (2 per unit), or CoD's own 320x480 screen.
        d, ox0, oy0 = (1, 0, 0) if cod else (2, 32, 26.5)
        frame_x, frame_y = (cx + ox0) * d - 64 * d, (cy - 5 + oy0) * d - 64 * d
        text = engine.notice
        # CSFont::getDisplayLength skips leading spaces, so a lone space measures 0, which the letter loop replaces
        # with 5 points (00042596: `vmoveq s24, #5.0`); the whole string's length counts the space's own advance.
        widths = [font.glyph(c).advance * d for c in text]
        constants = COD_NOTICE if cod else HD_NOTICE
        origins = hd_letter_origins([HD_EMPTY_LETTER if c == ' ' else w for c, w in zip(text, widths)], frame_x,
                                    frame_y, cap * d,
                                    sum(widths[len(text) - len(text.lstrip(' ')):]), **constants)
        # layout_text's line-0 baseline, to place each glyph by its own offsets from its pen and baseline.
        baseline = NOTICE_STYLE.height - font.line_height + font.base
        pens, pen = [], 0
        for c in text:
            pens.append(pen)
            pen += font.glyph(c).advance
        for glyph in layout.glyphs:
            state = hd_letter_state(text, elapsed, glyph.index)
            if state is None:
                continue
            alpha, offset = state
            image, dx, dy = self.text._glyph(name, glyph, k)
            if alpha < 1:
                image = image.copy()
                image = faded(image, round(255 * alpha))
            ox, oy = origins[glyph.index]
            left = (ox / d - ox0 + glyph.x - pens[glyph.index]) * k + dx
            top = (oy / d - oy0 + cap + glyph.y - baseline + offset * cap) * k + dy
            # On the frame-wide layer: a long notice centred over a left-hand portrait can start left of the column.
            self.wide.blit(image, (round(left) + self.margin, round(top)))

    # Real HD device confirmed (SHSEngine::initPermanents resource 0x9b=155,
    # GameModel::expandContinue/g_layerContinue/g_layerContinueLabel): once
    # the dialogue text finishes revealing, HD shows a "Continue" pill
    # button rather than this build's implicit tap-anywhere affordance.
    # Frame index per theme read directly off GameModel::setBubbleSex's own
    # CSMasterImage::getImage branches (param_1 0/1/2/3 -> index 9/10/8/11);
    # `theme` here is the same per-character number (entity property 651)
    # that native's "sex" parameter already is, so the branches line up
    # directly. Genuinely HD-only content -- Android's build never had
    # this, so it only appears once an HD ipa unlocks resource 155 (see
    # content.HD_ASSET_MAP), same as the choice-panel timer wheel.
    _CONTINUE_FRAME_BY_THEME = {1: 10, 2: 8, 3: 11}
    CONTINUE_FONT = 'TrebuchetMS_Bold14'

    autoplay = False        # Desktop's Autoplay: no Continue pill or tab, the page advances by itself

    def draw_continue(self, session, page, theme):
        if self.autoplay:
            return
        if not self.has_hd_bundle():
            self.draw_continue_tab(page.box, theme, session.engine.dialogue_animation)
            return
        if not session.engine.dialogue_animation.complete:
            return
        index = self._CONTINUE_FRAME_BY_THEME.get(theme, 9)
        # Resource 155 is HD-only (no Android original to define a logical
        # size from), and like the rest of HD's chrome it ships at 2x, so
        # its logical size is half its native pixel size.
        native = self.frame_native(155, index)
        k = self.scale
        width, height = native.get_width() / 2, native.get_height() / 2
        size = max(1, round(width * k)), max(1, round(height * k))
        image = native if native.get_size() == size else pygame.transform.smoothscale(native, size)
        # Measured against real-device photos of settled dialogue
        # (reference/IMG_0069.PNG "Beth", IMG_0070.PNG "Adam", and
        # IMG_0084.PNG's narrator box, the last with no portrait to
        # complicate the measurement): the pill sits right-inset about 3%
        # of the box's own width from its right edge; its own top sits
        # about 42% of its height above the box's *visible* bottom border,
        # which is BORDER_LINE_OFFSET below page.box's own bottom edge (the
        # border art has padding before its colored line starts).
        box = page.box
        border_y = box.y + box.height + self.BORDER_LINE_OFFSET
        x = box.x + box.width - round(box.width * 0.031) - width
        # Not from a photo: every measured reference (see above) is a box wide enough to hold the pill inset from
        # its own right edge. A narrator box tightly hugs short text (dialogue.py's own DialoguePage.page()), so a
        # one-word line ("Except...", "SMASH!") can be narrower than the pill itself, pushing this past the box's
        # left edge and leaving it overlapping the bubble's corner instead of sitting inside it. Clamping here to
        # never go left of the box keeps it visibly anchored to the bubble it belongs to; the true native behavior
        # for this specific case (an HD device showing a single-word narrator line) is not confirmed.
        x = max(x, box.x)
        # A negative box.x (a narrator box reaching left of the column, same as its own background art -- see
        # the `self.wide` comment above) only has room to its left on `self.wide`, not on `self.canvas`, which is
        # a *subsurface* of it starting `self.margin` in (so x=0 there is already `self.wide`'s own margin-wide
        # edge, not further left): blitting the pill there at a negative x clipped it against that subsurface's
        # own boundary instead of actually running out of room. Match the box's own `+ self.margin` shift and
        # draw on `self.wide` too, so the pill has the same margin to sit in that its box does.
        y = border_y - height * 0.42
        # GameModel::expandContinue animates the pill's (and its label's) y scale
        # from ~0 to 1 over 0.25 s, about its center, once the text has settled
        # (visible in an HD photo taken mid-animation).
        progress = self.continue_progress(session)
        if progress <= 0:
            return
        piece = pygame.Surface(image.get_size(), pygame.SRCALPHA).convert_alpha()
        piece.blit(image, (0, 0))
        # g_layerContinueLabel is TrebuchetMS-Bold 28 pt (SHSEngine+0xb23c), white, centered (flags 10).
        font = self.CONTINUE_FONT if self.hd_chrome() else BODY_FONT
        style = TextStyle(12, 0, (255, 255, 255))
        label = self.text.layout(font, 'Continue', width, style)
        left, top, right, bottom = label.ink_bounds
        self.text.draw_layout(
            piece, font, label,
            ((width - (right - left)) / 2 - left) * k,
            ((height - (bottom - top)) / 2 - top) * k, scale=k)
        if progress < 1:
            squashed = max(1, round(piece.get_height() * progress))
            piece = pygame.transform.smoothscale(piece, (piece.get_width(), squashed))
        centre_y = (y + height / 2) * k
        self.wide.blit(piece, (round(x * k) + self.margin, round(centre_y - piece.get_height() / 2)))

    CONTINUE_EXPAND_MS = 250

    def previous_box(self, motion, page):
        """The last line's final box, which a retained speaker's box resizes from (DialogueAnimation.box_rect). Kept
        by the renderer, not the save: a restored line already shows its own frame."""
        if getattr(self, '_box_motion', None) is not motion:
            self._box_from = getattr(self, '_box_final', None) if getattr(self, '_box_motion', None) else None
            self._box_motion = motion
        self._box_final = page.box
        return self._box_from

    def continue_progress(self, session):
        """0..1 through the pill's 250 ms expansion, counted from when this
        dialogue page first shows its text complete. Purely visual, so it
        runs on the renderer's own clock rather than engine or saved state."""
        now = pygame.time.get_ticks()
        key = (id(session), getattr(session, 'scene', None),
               getattr(getattr(session, 'vm', None), 'steps_executed', None),
               session.engine.dialogue_animation.revealed if hasattr(session.engine.dialogue_animation, 'revealed') else 0)
        if getattr(self, '_continue_key', None) != key:
            self._continue_key, self._continue_since = key, now
        return min(1.0, max(0.0, (now - self._continue_since) / self.CONTINUE_EXPAND_MS))

    @lru_cache(maxsize=4)
    def continue_tab(self, theme):
        # GameModel::setBubbleSex chooses the supplied skin's frames 3–6.
        k = self.scale
        index = {1: 5, 2: 3, 3: 6}.get(theme, 4)
        tab = (self.frame(126, index) if k == 1 else self.frame_scaled(126, index, k)).copy()
        font = 'TrebuchetMS_Bold14'
        metrics = self.text.font(font)
        height = getattr(metrics, 'cap_height', 14)
        width, tall = tab.get_width() / k, tab.get_height() / k
        label = self.text.layout(font, MenuStrings.load(self.resources)[29], width, TextStyle(height))
        left, top, right, bottom = label.ink_bounds
        self.text.draw_layout(tab, font, label, (width - right - left) / 2 * k,
                              (tall - bottom - top) / 2 * k, scale=k)
        return tab

    def draw_continue_tab(self, box, theme, motion):
        """The supplied skin's Continue tab (Android and the iPhone IPA); an HD bundle shows its pill instead."""
        scale = motion.continue_scale
        if scale <= 0:
            return
        k = self.scale
        tab = self.continue_tab(theme)
        width, height = tab.get_size()
        if scale < 1:
            tab = pygame.transform.smoothscale(tab, (width, max(1, round(height * scale))))
        # expandContinue: center = (bubble.width - 49.5, bubble.height + 8.5).
        self.canvas.blit(tab, (round((box.x + box.width) * k) - width,
                               round((box.y + box.height) * k) + round((height - tab.get_height()) / 2)))

    def draw(self, target, session):
        details = session.pending.details
        key = id(session), session.scene, session.vm.steps_executed, details['page_start']
        if key != self.cached_key:
            self.cached_page = session.dialogue_page()
            self.cached_key = key
            self.name_layer.fill((0, 0, 0, 0))
            if self.cached_page is not None:
                page = self.cached_page
                k = self.scale
                self.text.draw_layout(self.name_layer, page.name_font, page.name,
                                      page.name_origin[0] * k, page.name_origin[1] * k,
                                      scale=page.name_scale * k)
        page = self.cached_page
        if page is None:
            raise ContentError('Dialogue requires the imported APK layout and fonts')
        # shshd-runtime: a translated pack's two-speaker line (Session.dialogue_duet): the box the page chose (gray, or
        # the speakers' shared colour), the partner's portrait on the other side.
        duet = session.dialogue_duet() if hasattr(session, 'dialogue_duet') else None
        theme = page.theme if page.theme is not None else details['theme']
        self.portrait_factor = DUET_RING_SCALE if duet is not None else 1
        motion = session.engine.dialogue_animation
        if self._line is None or self._line[0] is not motion:
            self._leaving = self._line
        self._line = (motion, duet, self.portrait_factor)
        # The last line's portraits leave at the size they had there: its speaker (motion.previous) and, from a
        # two-speaker line, its partner too, unless this line keeps that partner. A speaker who goes on alone stays;
        # only the partner zooms out.
        leaving_factor, leaving = self.portrait_factor, None
        if self._leaving is not None and not motion.page_turn:
            leaving_factor = self._leaving[2]
            partner = self._leaving[1]
            if (partner is not None and (motion.previous is not None or not motion.changed)
                    and (duet is None or duet.character_id != partner.character_id)):
                leaving = partner
        self.wide.fill((0, 0, 0, 0))
        background = self.image(session.engine.panel.background_id)
        self.pending_background = background
        self.pending_background_origin = self.background_origin(background, session.engine)
        # FUN_000a92f4: unscaled image centered at GL (160,300), then panned
        # (background.BackgroundPan). The real
        # pixel content used to draw here is now composited separately by
        # Desktop._present() directly at window resolution (see there for
        # why: this canvas is permanently capped at 320x480 true pixels no
        # matter how it's sourced, so compositing a higher-density HD
        # background into it and only then upscaling the whole canvas to
        # the window cannot recover real detail -- confirmed visually
        # against the real app, not assumed). This canvas is left
        # transparent where the background belongs; draw() still returns
        # everything needed for Desktop to reproduce the same crop
        # (pending_background) at whatever resolution the window actually
        # affords.
        motion = session.engine.dialogue_animation
        # DialogueAnimation (exp-runtime v0.4.2, both iOS games): service 89's shake holds the box hidden, then scales
        # and rotates it in (GameModel::shakeDialog); a new speaker's box otherwise grows out of the portrait, through
        # a full-width strip, to its final height (setupAnimationsForTextLayer, `box_rect`).
        angle, zoom = motion.box_rotation, motion.box_scale
        k = self.scale
        previous = self.previous_box(motion, page)
        if motion.box_alpha == 0:
            pass                                   # the shake keeps the box hidden until it starts
        elif angle or zoom != 1:
            box = page.box
            layer = pygame.Surface(((box.width + 20) * k, (box.height + 20) * k), pygame.SRCALPHA).convert_alpha()
            self.box(layer, Rect(10, 10, box.width, box.height), theme, alpha=self.box_alpha(), scale=k)
            layer = pygame.transform.rotozoom(layer, -angle, zoom)
            self.canvas.blit(layer, layer.get_rect(center=(box.center[0] * k, box.center[1] * k)))
        else:
            # Drawn on the wide layer (the column plus HD's side margins): a narrator box reaches
            # left of the column's edge. The entrance starts at the portrait housing (the retained one for a
            # speaker without art), the same origin draw_portrait uses.
            mode = motion.portrait.mode if motion.portrait is not None else motion.anchor_mode
            origin = self._portrait_rect(mode) if mode else None
            # shshd-runtime: a two-speaker line's box grows from between its two portraits, and around one (into it,
            # or out of it) the box is not drawn until it sets off: its 1x1 start would otherwise sit alone where the
            # last portrait was while the pair waits to come in.
            if duet is not None:
                (lx, ly), (rx, ry) = self._portrait_rect(1).center, self._portrait_rect(2).center
                origin = Rect((lx + rx) // 2, (ly + ry) // 2, 0, 0)
            pair = duet is not None or (self._leaving is not None and self._leaving[1] is not None)
            waiting = (pair and motion.box_grow and not motion.page_turn and not motion.visuals_finished
                       and motion.elapsed_ms < motion.name_delay_ms - BOX_TRAVEL_MS)
            box = motion.box_rect(page.box, origin, previous)
            m = self.margin / k
            if not waiting:
                self.box(self.wide, Rect(box.x + m, box.y, box.width, box.height),
                         theme, alpha=self.box_alpha(), scale=k)
        # HD draws the portrait's rings under the body text: the third line's
        # top edge crosses the ring's bottom arc (white on the white box, so
        # invisible there), and drawing the ring over it clipped the glyphs.
        # The ring is clipped once the box has finished its entrance (`dialog-bubble-grow` completing calls
        # clipPortraitHousingAgainstBubble; for a shake, when its rotation ends): `housing_clipped`.
        bubble = self.housing_polygon(page.box) if motion.housing_clipped else None
        self.draw_portrait(motion.previous, motion.previous_scale, 'rings', bubble, factor=leaving_factor)
        self.draw_portrait(leaving, motion.previous_scale, 'rings', bubble, factor=leaving_factor)
        self.draw_portrait(motion.portrait, motion.portrait_scale, 'rings', bubble)
        self.draw_portrait(duet, motion.portrait_scale, 'rings', bubble)
        self.draw_notice(session.engine)
        # HD's song notes: '{' drawn as pack 155's note in the theme's color (dialogue.NOTE_FRAMES), at 2 px a unit.
        notes = ({NOTE_CODE: self.note_image(page.note_frame, getattr(page, 'note_tint', None))}
                 if getattr(page, 'note_frame', None) is not None else None)
        self.text.draw_layout(self.canvas, page.body_font, page.body,
                              page.body_origin[0] * k, page.body_origin[1] * k,
                              scale=k, source_end=motion.revealed, inline=notes, inline_density=2)
        self.canvas.blit(faded(self.name_layer, motion.name_alpha), (0, 0))
        # Real-device confirmed (reference/football_star_beth_greeting_hd.webp):
        # the relationship icon sits above the box, the body text and the
        # speaker name -- everything except the portrait itself, which
        # still draws after it.
        # HD adds the status (icon) layers to the portrait layer last, above the emotion effect and the art
        # (photo IMG_0229: the skull over the angry starburst); Android draws them under the art.
        hd = self.hd_chrome()
        if not hd:
            self.draw_relationship(motion)
        self.draw_portrait(motion.previous, motion.previous_scale, 'art', factor=leaving_factor)
        self.draw_portrait(leaving, motion.previous_scale, 'art', factor=leaving_factor)
        self.draw_emotion(motion)
        self.draw_expression_art(motion)
        self.draw_portrait(duet, motion.portrait_scale, 'art')
        if hd:
            self.draw_relationship(motion)
        self.draw_portrait_effect(session, motion)
        self.draw_continue(session, page, theme)
        # Layout 18's footer. Runtime save/load affordances remain host UI
        # until the original menu callbacks are implemented.
        # The bar, gear and hint (HD shows string 36, `IMG_0069`) are drawn by
        # Desktop from bottom_bar_layer(), edge to edge, not in this column.
        self.footer_text = self.footer_hint(36, 'Touch the screen to continue')
        if target is not None:
            target.blit(pygame.transform.smoothscale(self.canvas, target.get_size()), (0, 0))
        return page
