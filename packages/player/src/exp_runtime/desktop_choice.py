"""Original choice-panel artwork; selection values remain in the session."""
import math
from functools import lru_cache

from . import graphics as pygame

from .choice import BODY_FONT, FOOTER_FONT, ChoiceLayout
from .content import ContentError
from .desktop_dialogue import DialogueRenderer
from .choice_hints import preview_choices
from .fonts import TextStyle
from .ui_assets import Rect


# Choice hints' row tints (choice_hints.preview_choices), shared with exp-runtime's minigame prompt colours.
HINT_COLORS = {'gain': (189, 237, 199), 'loss': (251, 201, 199),
               'no_gain': (251, 201, 199), 'mixed': (251, 228, 175)}
# `SHSWidgetMenu::setPortrait` keeps three ARGB colors per theme: (even row, odd row, pressed row). Blue, pink
# and gold are (white, near-white tint, saturated tint); theme 3 (gray) holds opaque green / red / blue, which
# reads as an unfinished placeholder (no gray character ever has a choice). The odd-row values below are the
# binary's, darkened by the ~8 levels the light-mode photos show over them (blue and gold measured, pink assumed).
ROW_COLORS = {1: ((255, 255, 255, 243), (233, 243, 242, 243), (170, 225, 249, 180)),
              2: ((255, 255, 255, 243), (242, 231, 230, 243), (250, 214, 211, 180)),
              3: ((0, 255, 0, 255), (255, 0, 0, 255), (0, 0, 255, 180)),
              0: ((255, 255, 255, 243), (226, 208, 188, 243), (238, 188, 130, 180))}
RULE, END_RULE = (136, 136, 136), (175, 175, 175)     # HD's row rules and the closing rule (light-mode photos)


class ChoiceRenderer:
    def __init__(self, resources, text_renderer, artwork, scale=1):
        self.resources, self.text, self.art = resources, text_renderer, artwork
        self.layout = None
        # `scale` is canvas pixels per 320x480 logical unit (see
        # DialogueRenderer): every position below is logical and multiplied
        # by it, so HD art keeps its own density instead of being shrunk to
        # 1x and stretched back up.
        self.scale = scale
        # SRCALPHA: the background is composited separately by Desktop, at
        # real window resolution instead of this canvas's fixed 320x480 --
        # see desktop_dialogue.py's DialogueRenderer for the same treatment.
        # `wide` spans HD's whole 384-unit frame; `canvas` is a view of the
        # 320-unit column (see DialogueRenderer), and the portrait housing,
        # which reaches 7 units past the column's left edge, draws on `wide`.
        self.margin = round(32 * scale)
        self.wide = pygame.Surface((320 * scale + 2 * self.margin, 480 * scale), pygame.SRCALPHA).convert_alpha()
        self.canvas = self.wide.subsurface((self.margin, 0, 320 * scale, 480 * scale))
        self.footer_text = ''
        self.cached_key = self.cached_page = None
        self.hint_key = None
        self.hints = ()
        self.hint_ms = 0            # preview time not yet handed to Desktop (take_hint_ms)
        self.viewport = pygame.Rect(0, 0, 320, 421)
        self.pending_background = None
        self.pending_background_origin = (160, 180)

    def take_hint_ms(self):
        """Milliseconds spent on Choice hints since the last call."""
        spent, self.hint_ms = self.hint_ms, 0
        return spent

    def hd(self):
        try:
            return bool(self.art.hd_chrome())
        except AttributeError:
            return False

    def hd_timer(self):
        """Whether the HD build's own timed-choice wheel applies: it needs
        HD-only resource 155 (see content.HD_ASSET_MAP). Without an HD app
        bundle -- e.g. an episode that never shipped on HD -- a timed choice
        falls back to Android's lower timer panel (layout 22, assets 708/709)."""
        try:
            return self.art.has_hd_bundle()
        except (AttributeError, ContentError):
            return False

    def page(self, session):
        details = session.pending.details
        game = session.engine.word_game
        key = id(session), session.scene, session.vm.steps_executed, game.round if game else None
        if game:
            details = dict(details, options=game.options, enabled=[True] * 4, minigame=True)
        if key != self.cached_key:
            if self.layout is None:
                self.layout = ChoiceLayout(self.resources)
            character = details['character_id']
            theme = session.engine.numbers.get(session.engine.number_key(character, 651), 0)
            variants = session.engine.character_art_variants.get(character, ())
            has_portrait = character >= 0 and bool(variants) and variants[0] > 0
            page = None
            if game and getattr(game, 'hd', False) and self.hd() and self.hd_timer():
                # SHSUIMenu::initActionMenu: the same menu, timed and scored.
                page = self.hd_page(dict(details, timeout_ms=game.duration_ms), theme, has_portrait, scored=True)
            elif not game and self.hd() and self.hd_timer():
                page = self.hd_page(details, theme, has_portrait)
            elif game and getattr(game, 'hd', False) and self.cod():
                page = self.cod_page(dict(details, timeout_ms=game.duration_ms), theme, has_portrait, scored=True)
            elif not game and self.cod():
                page = self.cod_page(details, theme, has_portrait)
            if page is None:
                page = self.layout.page(details, theme=theme, has_portrait=has_portrait,
                                        text_history=getattr(session, 'bitmap_history', None),
                                        timer_panel=not self.hd_timer())
            self.cached_page = page
            if game is None or self.cached_key is None or self.cached_key[0] != key[0] or self.cached_key[3] is None:
                self.age_ms = 0          # a new choice (or the quiz's first deal): it fades in, its labels fly on again
            self.cached_key = key
        return self.cached_page

    OPTION_FONT = 'ArialRoundedMTBold16@15'     # SHSEngine::initFonts: the option labels are 30 points

    age_ms = 0          # since the current choice appeared (Desktop.tick), for its labels' fly-on and its fade-in
    overlay = None      # the HD timer layers (circle timer, running man), outside the menu view's fades

    def hd_page(self, details, theme, has_portrait, scored=False):
        """SHSWidgetMenu's own panel (hd_choice.py), or None when the HD layout bank or vector fonts are missing."""
        from .choice import TITLE_FONTS
        from .hd_choice import FontMetrics, hd_choice_page, TITLE_GAP, DESCRIPTION_GAP, OPTION_GAP
        from .vector_text import cap_height, descent, load_font_sized
        library = getattr(self.resources, 'library', None)
        layouts = self.hd_layouts()
        if library is None or layouts is None:
            return None
        title_font = TITLE_FONTS.get(theme, 'PajamaHipY26')
        title = self.text.font(title_font)
        body = self.text.font(BODY_FONT)
        option = load_font_sized(library, BODY_FONT, 15)
        if option is None or None in (cap_height(title), cap_height(body), cap_height(option), descent(title)):
            return None
        self.text.register(self.OPTION_FONT, option)
        color = {1: (1, 76, 215), 2: (166, 45, 45), 3: (108, 108, 108)}.get(theme, (223, 163, 52))
        # The option font is the theme color itself (SHSEngine::initFonts); the two half-alpha labels make it
        # lighter (draw_hd), so the photo-fitted OPTION_COLORS do not apply here.
        return hd_choice_page(
            layouts, details, theme=theme, has_portrait=has_portrait,
            title=FontMetrics(title, cap_height(title), TITLE_GAP / 2, descent(title)), title_font=title_font,
            description=FontMetrics(body, cap_height(body), DESCRIPTION_GAP / 2), description_font=BODY_FONT,
            option=FontMetrics(option, cap_height(option), OPTION_GAP / 2), color=color,
            option_color=color, scored=scored)

    def cod(self):
        """Cause of Death: its iPhone SHSWidgetMenu, which is SHS HD's at half scale (hd_choice.COD_GEOMETRY)."""
        try:
            return self.art.game_id() == 'cod'
        except AttributeError:
            return False

    def cod_page(self, details, theme, has_portrait, scored=False):
        """CoD's own panel from its layout bank (resource 14), or None without vector fonts (an IPA library with no
        art source draws with fixed atlases, so it keeps the Android page). initFonts (1.4.7 00026234), per theme:
        the title is the bundled name face 26 in dark red (theme 2 rose 0xffb44e4e) with its stroke twin (4.0), gap
        8; the description Arial Rounded 16, black (theme 2 rose), gap 10; the options Arial Rounded 15, black
        (theme 2 rose), gap 8."""
        from .choice import TITLE_FONTS
        from .hd_choice import COD_GEOMETRY, FontMetrics, hd_choice_page
        from .hd_layout import BankLayouts
        from .vector_text import cap_height, descent, load_font
        library = getattr(self.resources, 'library', None)
        if library is None:
            return None
        if self.layout is None:
            self.layout = ChoiceLayout(self.resources)
        title_font = TITLE_FONTS.get(theme, 'PajamaHipY26')
        title = self.text.font(title_font)
        body = self.text.font(BODY_FONT)
        option = load_font(library, 'ArialRoundedMTBold15')
        if None in (cap_height(title), cap_height(body), cap_height(option), descent(title)):
            return None
        self.text.register(self.OPTION_FONT, option)
        color = (180, 78, 78) if theme == 2 else (0, 0, 0)
        return hd_choice_page(
            BankLayouts(self.layout.bank), details, theme=theme, has_portrait=has_portrait,
            title=FontMetrics(title, cap_height(title), 8, descent(title)), title_font=title_font,
            description=FontMetrics(body, cap_height(body), 10), description_font=BODY_FONT,
            option=FontMetrics(option, cap_height(option), 8), color=color, option_color=color,
            scored=scored, geometry=COD_GEOMETRY)

    def hd_layouts(self):
        if getattr(self, '_hd_layouts', None) is None:
            from .hd_layout import HdLayouts
            library = getattr(self.resources, 'library', None)
            layouts = HdLayouts(library) if library is not None else None
            self._hd_layouts = layouts if layouts is not None and layouts.bank() is not None else False
        return self._hd_layouts or None

    # Real HD device confirmed (reference/IMG_0084.PNG, and a screenshot of
    # this exact "parking ticket" choice sent directly): a timed choice
    # shows a 12-slice wheel straddling the choice box's own bottom border,
    # horizontally centered -- not the top-right icon this build first
    # guessed at, and not this build's original "Xs" text appended to the
    # footer hint. Measured directly against that screenshot: the wheel's
    # diameter is ~22% of the box's own width (re-measured at HD's true
    # ~3.9 px per unit; the first pass assumed 4.27 and read 17.6%), and its center sits
    # almost exactly on the border (~5.7% of its own diameter above it).
    # Colors sampled from the same screenshot: a fixed cyan fill/light-gray
    # unfilled split (not theme-colored -- unlike the box border, this
    # didn't visibly vary between the one blue-theme and one default-theme
    # reference available), with the box's own border color carried
    # through as the wheel's outer rim so it reads as one continuous
    # shape instead of a circle sitting on top of a straight line.
    #
    # SHSCircleTimerLayer's native mechanism -- 16 pre-baked frame images
    # cross-fading in over the countdown, from HD-only resource 155's
    # frames 12-27 (see content.HD_ASSET_MAP) -- is understood at the
    # decompile level, but Ghidra's float-heavy per-frame position formula
    # didn't resolve to a geometrically consistent layout on inspection.
    # This renders the same real-device-measured *appearance* (a 12-slice
    # wheel, not literally the 16 native frames) with plain pygame drawing
    # instead of compositing the real frames at guessed positions.
    _WHEEL_SEGMENTS = 12
    _WHEEL_FILL = (90, 225, 255)
    _WHEEL_EMPTY = (226, 226, 226)
    _WHEEL_RING = (245, 245, 245)

    @lru_cache(maxsize=8)
    def timer_panel(self, theme, width, height):
        """Android's timed-choice lower panel (layout 22), at canvas density."""
        k = self.scale
        layer = pygame.Surface((width * k, height * k), pygame.SRCALPHA).convert_alpha()
        bank = self.layout.bank
        hidden_until = 0
        for number, (node, rect) in enumerate(bank.walk(22, Rect(0, 0, width, height)), 1):
            if number <= hidden_until:
                continue
            # 000d9038 hides the score capsule (root 13) for ordinary choices.
            visible = node.flags & 16 and number != 13
            if node.kind == 7 and not visible:
                hidden_until = number + sum(1 for _ in bank.walk(node.payload[0]))
                continue
            if node.kind == 1 and visible and rect.width > 0 and rect.height > 0:
                slot, frame = node.payload
                pack = {1: 204, 2: 220, 3: 252}.get(theme, 236)
                image = self.art.frame_scaled({0: 126, 2: pack}[slot], frame, k)
                layer.blit(pygame.transform.scale(image, (round(rect.width * k), round(rect.height * k))),
                           (round(rect.x * k), round(rect.y * k)))
        return layer

    def draw_timer(self, position, elapsed_fraction):
        """00082744: base 708, then 709 swept clockwise from twelve o'clock."""
        k = self.scale
        position = round(position[0] * k), round(position[1] * k)
        fraction = min(1., max(0., elapsed_fraction))
        if getattr(getattr(self.resources, 'library', None), 'kind', 'apk') == 'ipa':
            # GameModel::init passes common frames 7..22 to the native iOS
            # circle layer. Each wedge fades over its own 1/16 interval,
            # holding opacity .8 for the first .4 of that interval.
            for index in range(16):
                progress = fraction * 16 - index
                opacity = min(1., max(0., (1 - progress) / .6)) * .8
                if opacity <= 0:
                    continue
                image = self.art.frame_scaled(126, 7 + index, k).copy()
                quadrant = index // 4
                x = 25 * k - image.get_width() if quadrant >= 2 else 25 * k
                y = 25 * k - image.get_height() if quadrant in (0, 3) else 25 * k
                image.set_alpha(round(opacity * 255))
                self.canvas.blit(image, (position[0] + 6 * k + x, position[1] + 5 * k + y))
            return
        self.canvas.blit(self.art.frame_scaled(708, 0, k), position)
        if fraction <= 0:
            return
        timer = self.art.frame_scaled(709, 0, k).copy()
        if fraction < 1:
            mask = pygame.Surface(timer.get_size(), pygame.SRCALPHA)
            cx, cy = timer.get_width() / 2, timer.get_height() / 2
            radius = math.hypot(cx, cy) + 1
            points = [(cx, cy)] + [(cx + radius * math.sin(t), cy - radius * math.cos(t))
                                  for t in (fraction * 2 * math.pi * i / 120 for i in range(121))]
            pygame.draw.polygon(mask, (255, 255, 255, 255), points)
            timer.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        self.canvas.blit(timer, position)

    def draw_timer_wheel(self, page, remaining_ms, timeout_ms):
        box = page.box
        k = self.scale
        # The rim carries the box's own border color, which follows the theme.
        rim_color = {1: (41, 104, 221), 2: (196, 90, 90), 3: (100, 100, 100)}.get(page.theme, (207, 152, 62))
        diameter = max(16, round((box.width - 20) * 0.22))
        radius = diameter / 2 * k
        cx = (box.x + box.width / 2) * k
        # The box's visible bottom line sits BORDER_LINE_OFFSET below the
        # rect box() is given (here inset 10 from page.box); see
        # DialogueRenderer.BORDER_LINE_OFFSET.
        border_y = box.y + box.height - 10 + DialogueRenderer.BORDER_LINE_OFFSET
        cy = (border_y - diameter * 0.057) * k
        # The wheel starts fully cyan and loses segments as time runs out,
        # not the other way around (direct user guidance -- a real
        # sequence of frames confirming the animation's own time direction
        # wasn't available, but this matches the more common "draining"
        # countdown convention and is what was actually asked for).
        fraction = max(0, remaining_ms) / timeout_ms if timeout_ms else 0
        filled = fraction * self._WHEEL_SEGMENTS

        # HD's wheel (light-mode photo): a thin gray rim where it stands inside the box, the box's own
        # colored border bulging below the border line, a white ring, then the pie (0.85 of the radius)
        # with faint seams.
        hd = self.hd()
        if hd:
            clip = self.canvas.get_clip()
            below = clip.clip(pygame.Rect(0, round(border_y * k) - 1, self.canvas.get_width(),
                                          self.canvas.get_height()))
            above = clip.clip(pygame.Rect(0, 0, self.canvas.get_width(), round(border_y * k) - 1))
            self.canvas.set_clip(above)
            pygame.draw.circle(self.canvas, (177, 177, 177), (cx, cy), radius)
            self.canvas.set_clip(below)
            pygame.draw.circle(self.canvas, rim_color, (cx, cy), radius * 1.1)
            self.canvas.set_clip(clip)
            pygame.draw.circle(self.canvas, (255, 255, 255), (cx, cy), radius * 0.965)
            pie_radius = radius * 0.85
        else:
            pygame.draw.circle(self.canvas, rim_color, (cx, cy), radius)
            pygame.draw.circle(self.canvas, self._WHEEL_RING, (cx, cy), radius * 0.85)
            pie_radius = radius * 0.74
        for index in range(self._WHEEL_SEGMENTS):
            level = min(1.0, max(0.0, filled - index))
            if level <= 0:
                color = self._WHEEL_EMPTY
            elif level >= 1:
                color = self._WHEEL_FILL
            else:
                color = tuple(round(e + (f - e) * level) for e, f in zip(self._WHEEL_EMPTY, self._WHEEL_FILL))
            # Counter-clockwise from 12 o'clock: confirmed from a real
            # half-elapsed screenshot (reference/IMG_0086.PNG) showing the
            # filled half on the wheel's left side, not the right.
            start = -math.pi / 2 - index * 2 * math.pi / self._WHEEL_SEGMENTS
            end = start - 2 * math.pi / self._WHEEL_SEGMENTS
            points = [(cx, cy)] + [(cx + pie_radius * math.cos(t), cy + pie_radius * math.sin(t))
                                   for t in (start + (end - start) * i / 8 for i in range(9))]
            pygame.draw.polygon(self.canvas, color, points)
        if hd:
            for index in range(self._WHEEL_SEGMENTS):
                angle = -math.pi / 2 - index * 2 * math.pi / self._WHEEL_SEGMENTS
                pygame.draw.line(self.canvas, (110, 226, 250), (cx, cy),
                                 (cx + pie_radius * math.cos(angle), cy + pie_radius * math.sin(angle)), max(1, round(k * .5)))
        # A divider line at every one of the 12 segment seams read as too
        # prominent against the small wheel (direct user feedback against
        # a live render, matched against the real screenshots' own much
        # subtler lines) -- the color transitions between filled and
        # unfilled wedges already read as segments without them.

    # -- HD (hd_choice.py) ---------------------------------------------------------------------------------------
    @lru_cache(maxsize=64)
    def hd_piece(self, slot, frame, theme, cod=False):
        """A widget node's image at canvas density (the HD packs are one pixel per point). Cause of Death's widgets
        name its common pack 126 (slot 0) and its theme's box pack (slot 2), drawn as its dialogue draws them (2x with
        the SHS HD art source)."""
        if cod:
            pack = 126 if slot == 0 else {1: 204, 2: 220, 3: 252}.get(theme, 236) if slot == 2 else None
            try:
                return None if pack is None else self.art.frame_scaled(pack, frame, self.scale)
            except (ContentError, IndexError, ValueError):
                return None
        layouts = self.hd_layouts()
        image = layouts.frame(layouts.pack_for(slot, theme), frame)
        if image is None:
            return None
        k = self.scale / 2
        if k == 1:
            return image
        return pygame.transform.smoothscale(image, (max(1, round(image.get_width() * k)),
                                                    max(1, round(image.get_height() * k))))

    def tile(self, image, rect):
        """`CSMasterImage::drawTiledNoCP`: the image repeated from the rectangle's top-left, clipped to it."""
        clip = self.canvas.get_clip()
        self.canvas.set_clip(rect.clip(clip))
        w, h = image.get_size()
        for y in range(rect.y, rect.bottom, h):
            for x in range(rect.x, rect.right, w):
                self.canvas.blit(image, (x, y))
        self.canvas.set_clip(clip)

    def panel_layouts(self, geometry):
        """The layout bank a panel of `geometry` is drawn from: HD's, or (CoD) the game's own resource 14."""
        from .hd_choice import HD_GEOMETRY
        if geometry is HD_GEOMETRY:
            return self.hd_layouts()
        from .hd_layout import BankLayouts
        return BankLayouts(self.layout.bank)

    def hd_widget(self, layout_id, x, y, width, height, theme, *, hidden=(), shown=(), geometry=None):
        """`CSLightWeightWidget::setLocation` + `draw` at the build's points (x, y, width, height)."""
        from .hd_choice import HD_GEOMETRY
        g = geometry or HD_GEOMETRY
        k, d = self.scale, g.density
        ox, oy = g.units(x, y)
        for _, node, visible, (nx, ny, w, h) in self.panel_layouts(g).nodes(
                layout_id, (ox, oy), size=(width / d, height / d), hidden=hidden, shown=shown):
            if not visible or node.kind != 1 or w <= 0 or h <= 0:
                continue
            image = self.hd_piece(*node.payload, theme, g is not HD_GEOMETRY)
            if image is not None:
                self.tile(image, pygame.Rect(round(nx * k), round(ny * k), round(w * k), round(h * k)))

    def hd_line(self, color, x, y, width, geometry=None):
        """A one-point rule at the build's points."""
        from .hd_choice import HD_GEOMETRY
        g = geometry or HD_GEOMETRY
        k = self.scale
        ux, uy = g.units(x, y)
        self.canvas.fill(color, (round(ux * k), round(uy * k), round(width / g.density * k),
                                 max(1, round(k / g.density))))

    def draw_hd(self, target, session, page, scroll, pointer, pressed, choice_hints, focus=None):
        from .hd_choice import (DESCRIPTION_WIDGET, SCORE_CAPSULE, SEPARATOR, ROW_SEPARATOR, HEADER_NORMAL_ROOT,
                                HEADER_TALL_ROOT)
        k = self.scale
        g = page.geometry
        x0, width, inset = g.panel_x, g.panel_width, g.table_inset

        def px(rect):
            return pygame.Rect(round(rect.x * k), round(rect.y * k), round(rect.width * k), round(rect.height * k))

        self.canvas.set_clip(None)
        self.wide.fill((0, 0, 0, 0))
        # The circle timer and the running man are layers of the engine view, not of the menu's view: they do not take
        # part in its fades (hd_choice.TRANSITION_MS), so they are drawn apart.
        if self.overlay is None or self.overlay.get_size() != self.canvas.get_size():
            self.overlay = pygame.Surface(self.canvas.get_size(), pygame.SRCALPHA).convert_alpha()
        self.overlay.fill((0, 0, 0, 0))
        self.pending_background = self.art.image(session.engine.panel.background_id)
        self.pending_background_origin = self.art.background_origin(self.pending_background, session.engine)
        theme = page.theme
        # drawSelf: header, description, its separator, title, description text, footer, side strips.
        tall = (HEADER_NORMAL_ROOT,), (HEADER_TALL_ROOT,)
        hidden, shown = (tall if page.tall_title else tall[::-1])
        self.hd_widget(page.header_widget, x0, page.top, width, page.header_height, theme,
                       hidden=hidden, shown=shown, geometry=g)
        body_top = page.top + page.header_height
        self.hd_widget(DESCRIPTION_WIDGET, x0, body_top, width, page.description_height, theme, geometry=g)
        self.hd_line(SEPARATOR, x0 + inset, body_top + page.description_height - 1, width - 2 * inset, g)
        x, y = page.title_origin
        # On the frame-wide layer: a title's stroke and italic overhang may pass the column's edge.
        self.text.draw_layout(self.wide, page.title_font, page.title, x * k + self.margin, y * k, scale=k)
        x, y = page.description_origin
        self.text.draw_layout(self.canvas, page.description_font, page.description, x * k, y * k, scale=k)
        self.hd_widget(page.footer_widget, x0, page.footer_top, width, page.footer_height, theme,
                       hidden=(SCORE_CAPSULE,) if page.timer_center and not page.scored else (), geometry=g)
        strip = self.hd_piece(2, 3, theme, g.density == 1)
        if strip is not None:
            _, top = g.units(0, body_top)
            height = (page.description_height + page.rows_height) / g.density
            for left in (x0, x0 + width - inset):
                ux, _ = g.units(left, 0)
                self.tile(strip, px(Rect(ux, top, inset / g.density, height)))
        # SHSMenu's table view.
        buttons = []
        table = px(page.table)
        self.canvas.set_clip(table)
        even, odd, selected = page.row_colors
        game = session.engine.word_game if page.scored else None
        for row in page.rows:
            rect = Rect(row.rect.x, row.rect.y - scroll, row.rect.width, row.rect.height)
            area = px(rect)
            hit = pygame.Rect(rect.x, rect.y, rect.width, rect.height).clip(
                pygame.Rect(page.table.x, page.table.y, page.table.width, page.table.height))
            hint = (self.hints[row.index].kind if choice_hints and self.hint_key == self.cached_key
                    and row.index < len(self.hints) else 'unknown')
            hint_color = HINT_COLORS.get(hint)
            down = (pressed == ('choose', row.index) or focus == row.index
                    or pointer is not None and hit.collidepoint(pointer))
            if game is not None:
                down = game.selected == row.index or game.selected < 0 and focus == row.index
            if down:
                color = (tuple(round(c * .9) for c in hint_color) + (255,)) if hint_color else selected
            else:
                color = (hint_color + (255,)) if hint_color else odd if row.position % 2 else even
            band = pygame.Surface(area.size, pygame.SRCALPHA)
            band.fill(color)
            self.canvas.blit(band, area.topleft)
            rule = max(1, round(k / g.density))
            self.canvas.fill(ROW_SEPARATOR, (area.x, area.bottom - rule, area.width, rule))
            self.draw_hd_label(row, rect, scroll, self.label_home(row, game), g)
            if hit.height > 0:
                buttons.append((hit, ('choose', row.index)))
        self.canvas.set_clip(None)
        if page.portrait is not None:
            self.draw_hd_portrait(session, page)
        if game is not None:
            self.draw_hd_timer(page.timer_center, max(0, game.remaining_ms), game.duration_ms, g)
            self.draw_hd_quiz(page, game)
        elif page.timer_center is not None and session.remaining_ms is not None:
            self.draw_hd_timer(page.timer_center, session.remaining_ms, session.pending.details['timeout_ms'], g)
        # initActionMenu calls setTimed: the quiz shows the timed hint (CoD IMG_0516-0521).
        timed = session.remaining_ms is not None or page.scored
        hint = 'Touch choice before time runs out' if timed else 'Touch the best choice'
        if hasattr(self.art, 'footer_hint'):
            hint = self.art.footer_hint(40 if timed else 38, hint)
        self.footer_text = hint
        if page.max_scroll:
            # A desktop affordance: the table view scrolls, as native, but has no visible indicator here otherwise.
            track = Rect(page.table.x + page.table.width - 4, page.table.y + 2, 3, page.table.height - 4)
            pygame.draw.rect(self.canvas, (100, 100, 100), px(track))
            thumb = max(20, track.height * page.table.height / (page.table.height + page.max_scroll))
            y = track.y + (track.height - thumb) * scroll / page.max_scroll
            pygame.draw.rect(self.canvas, (225, 225, 225), px(Rect(track.x, y, track.width, thumb)))
        buttons.append((pygame.Rect(-32, 422, 92, 58), ('menu',)))
        if target is not None:
            target.blit(pygame.transform.smoothscale(self.canvas, target.get_size()), (0, 0))
            target.blit(pygame.transform.smoothscale(self.overlay, target.get_size()), (0, 0))
        return page, buttons

    def label_home(self, row, game):
        """How far `row`'s labels have flown home (hd_choice.fly_on / fly_off)."""
        from .hd_choice import QUIZ_FLY_ON_SECONDS, fly_off, fly_on
        if game is None:
            return fly_on(row.position, self.age_ms / 1000)
        if game.fly_off_ms:
            return 1 - fly_off(row.position, game.fly_off_row, (game.HD_FLY_OFF_MS - game.fly_off_ms) / 1000)
        if game.fly_off_row >= 0:
            return 0.
        return fly_on(row.position, game.shown_ms / 1000, QUIZ_FLY_ON_SECONDS)

    def draw_hd_label(self, row, rect, scroll, home, geometry=None):
        """The cell's two SHSLabels (alpha 0.5 each) at their flight offsets (points)."""
        from .hd_choice import label_offsets
        k = self.scale
        width, height = round(rect.width * k), round(rect.height * k)
        key = (row.text, width, height)
        cache = self.__dict__.setdefault('_labels', {})
        if key not in cache:
            if len(cache) > 32:
                cache.clear()
            label = pygame.Surface((width, height), pygame.SRCALPHA).convert_alpha()
            x, y = row.origin
            self.text.draw_layout(label, self.OPTION_FONT, row.text, (x - rect.x) * k, (y - row.rect.y) * k, scale=k)
            label.set_alpha(128)
            cache[key] = label
        density = geometry.density if geometry is not None else 2
        for offset in label_offsets(home, geometry):
            self.canvas.blit(cache[key], (round((rect.x + offset / density) * k), round(rect.y * k)))

    def draw_hd_portrait(self, session, page):
        """The menu's SHSPortraitLayer: ring clipped by clipPortraitHousing, disc, then the expression-zero art."""
        k, m = self.scale, self.margin
        cx, cy = page.portrait.center
        ring = self.art.ring_frame(k).copy()
        left, top = round(cx * k) - ring.get_width() // 2, round(cy * k) - ring.get_height() // 2
        pygame.draw.polygon(ring, (0, 0, 0, 0), [(x * k - left, y * k - top) for x, y in page.portrait_clip])
        center = (round(cx * k) + m, round(cy * k))
        self.wide.blit(ring, ring.get_rect(center=center))
        disc = self.art.disc_frame(page.theme, k)
        self.wide.blit(disc, disc.get_rect(center=center))
        details = session.pending.details
        asset = session.engine.character_art_variants[details['character_id']][0]
        # FUN_000ae5d4 requests expression zero, independently of dialogue.
        composed = self.art.hd_portrait(asset, details['portrait_mode'] == 2 and page.theme != 3, k)
        if composed is not None:
            art, lift = composed
            housing = ring.get_rect(center=center)
            self.wide.blit(art, (housing.x, housing.y - lift))

    def quiz_fonts(self):
        """drawScore's TrebuchetMS-Bold 50 (white, with a 0.6-point 0xffb4b4b4 stroke over it: initFonts 0002bab0) and
        drawScoreEffect's 32 (0xff08851f / 0xfff41111)."""
        if getattr(self, '_quiz_fonts', None) is None:
            from .fonts import BitmapFont
            from .vector_text import FaceSource, system_font_path, vector_font
            library = self.resources.library
            try:
                base = BitmapFont.parse(library.read_ui_asset('fonts/TrebuchetMS_Bold14.fnt'))
            except ContentError:
                # An IPA (Cause of Death: initFonts +0x3e668 TrebuchetMS-Bold 25, stroke 0.3, the same ratio; the
                # effects +0x3fe88 / +0x416a8 at 16) has no Android descriptor: its own Trebuchet atlas sets the
                # glyph set.
                base = self.text.font('TrebuchetMS_Bold16')
            path = system_font_path('trebuchet-bold', library)
            self._quiz_fonts = (
                self.text.register('HD_QUIZ_SCORE', vector_font(base, FaceSource(path=path, label='trebuchet-bold'),
                                                                25, fill=(255, 255, 255), embolden=.6 / 50,
                                                                embolden_color=(180, 180, 180))),
                self.text.register('HD_QUIZ_EFFECT', vector_font(base, FaceSource(path=path, label='trebuchet-bold'),
                                                                 16)))
        return self._quiz_fonts

    def draw_hd_quiz(self, page, game):
        from .hd_choice import FontMetrics, text_in_region
        from .vector_text import cap_height
        k, g = self.scale, page.geometry
        d, cod = g.density, page.geometry.density == 1
        cx, cy = page.timer_center
        first, count, seconds = g.running_man
        frame = int((game.duration_ms - max(0, game.remaining_ms)) / 1000 / seconds) % count
        image = self.hd_piece(0, first + frame, 0, cod)
        if image is not None:
            # g_layerRunningMan's frames are centred on the layer, a point below the wheel's centre.
            self.overlay.blit(image, image.get_rect(center=(round(cx * k), round((cy + g.running_drop / d) * k))))
        score_font, effect_font = self.quiz_fonts()
        x, y, w, h = g.score_box
        ux, uy = g.units(g.panel_x + x, page.footer_top + y)
        layout, origin = text_in_region(FontMetrics(score_font, cap_height(score_font), 0), str(game.score),
                                        Rect(ux, uy, w / d, h / d), 10, (255, 255, 255), density=d)
        self.text.draw_layout(self.canvas, 'HD_QUIZ_SCORE', layout, origin[0] * k, origin[1] * k, scale=k)
        if game.effect_ms:
            # doScoreEffectAnimation: opacity 0, 1, 1, 0 at 0, 0.1, 0.9, 1 of 1 s while rising 30 points.
            t = 1 - game.effect_ms / game.HD_EFFECT_MS
            alpha = t / .1 if t < .1 else 1 if t < .9 else (1 - t) / .1
            x, y, w, h = g.effect_box
            ux, uy = g.units(g.panel_x + x, page.footer_top + y - g.effect_rise * t)
            delta = game.last_delta
            color = (8, 133, 31) if delta >= 0 else (244, 17, 17)
            layout, origin = text_in_region(FontMetrics(effect_font, cap_height(effect_font), 0),
                                            f'+{delta}' if delta >= 0 else str(delta),
                                            Rect(ux, uy, w / d, h / d), 10, color, density=d)
            layer = pygame.Surface(self.canvas.get_size(), pygame.SRCALPHA).convert_alpha()
            self.text.draw_layout(layer, 'HD_QUIZ_EFFECT', layout, origin[0] * k, origin[1] * k, scale=k)
            layer.set_alpha(round(255 * max(0., min(1., alpha))))
            self.canvas.blit(layer, (0, 0))

    def draw_hd_timer(self, center, remaining_ms, timeout_ms, geometry=None):
        """SHSCircleTimerLayer over the timed footer's notch: resource 155's frames 12-27 (CoD: its common pack 126's
        7-22), each fading in its own sixteenth of the timeout (hd_choice.wedge_opacity / wedge_position)."""
        from .hd_choice import HD_GEOMETRY, wedge_opacity, wedge_position
        g = geometry or HD_GEOMETRY
        k, d, size = self.scale, g.density, g.timer_size
        cod = g is not HD_GEOMETRY
        elapsed = max(0, timeout_ms - remaining_ms)
        left, top = center[0] - size / 2 / d, center[1] - size / 2 / d
        for index in range(16):
            opacity = wedge_opacity(index, elapsed, timeout_ms)
            if opacity <= 0:
                continue
            image = self.hd_piece(0, (7 if cod else 12) + index, 0, cod)
            if image is None:
                continue
            points = (self.art.logical_size(126, 7 + index) if cod
                      else self.hd_layouts().frame(155, 12 + index).get_size())
            x, y = wedge_position(index, *points, centre=size / 2)
            image = image.copy()
            image.set_alpha(round(255 * opacity))
            self.overlay.blit(image, (round((left + x / d) * k), round((top + y / d) * k)))

    def draw(self, target, session, *, scroll=0, pointer=None, pressed=None, focus=None, choice_hints=False):
        page = self.page(session)
        if choice_hints and self.hint_key != self.cached_key:
            started = pygame.time.get_ticks()
            self.hints = preview_choices(getattr(session, 'real_session', session))     # (Disable Choice Timer's stand-in)
            self.hint_key = self.cached_key
            self.hint_ms += pygame.time.get_ticks() - started
        scroll = min(page.max_scroll, max(0, scroll))
        from .hd_choice import HdChoicePage
        if isinstance(page, HdChoicePage):
            return self.draw_hd(target, session, page, scroll, pointer, pressed, choice_hints, focus)
        k = self.scale

        def px(rect):
            """A logical rect in canvas pixels."""
            return pygame.Rect(round(rect.x * k), round(rect.y * k),
                               round(rect.width * k), round(rect.height * k))

        self.viewport.height = page.timer_panel.y if page.timer_panel else 421
        self.canvas.set_clip(None)
        self.wide.fill((0, 0, 0, 0))
        self.pending_background = self.art.image(session.engine.panel.background_id)
        # The word game's separate background is centered at GL (160,240); the story's own pans with the speaker.
        self.pending_background_origin = ((160, 240) if session.engine.word_game else
                                          self.art.background_origin(self.pending_background, session.engine))
        self.canvas.set_clip(px(self.viewport))
        box = page.box
        body_height = box.height - page.timer_panel.height + 10 if page.timer_panel else box.height
        self.art.box(self.canvas, Rect(box.x + 10, box.y + 10 - scroll,
                                       box.width - 20, body_height - 20), page.theme, alpha=243, scale=k)
        buttons = []
        for row in page.rows:
            rect = pygame.Rect(row.rect.x, row.rect.y - scroll, row.rect.width, row.rect.height)
            hit = rect.clip(self.viewport)
            hint = (self.hints[row.index].kind if choice_hints and row.enabled
                    and self.hint_key == self.cached_key and row.index < len(self.hints) else 'unknown')
            hint_color = HINT_COLORS.get(hint)
            if hint_color is not None:
                pygame.draw.rect(self.canvas, hint_color, px(rect))
            if row.enabled and (pressed == ('choose', row.index) or focus == row.index
                                or pointer is not None and hit.collidepoint(pointer)):
                if hint_color is not None:
                    color = tuple(round(channel * .9) for channel in hint_color) + (255,)
                else:
                    color = ROW_COLORS.get(page.theme, ROW_COLORS[0])[2] if self.hd() else (
                        (250, 214, 211, 180) if page.theme == 2 else (170, 225, 249, 180))
                highlight = pygame.Surface(px(rect).size, pygame.SRCALPHA)
                highlight.fill(color)
                self.canvas.blit(highlight, px(rect).topleft)
            elif self.hd() and hint_color is None:
                # Every second row has its own tint; a pressed row shows the pressed color instead.
                even, odd, _ = ROW_COLORS.get(page.theme, ROW_COLORS[0])
                tint = odd if row.index % 2 else even
                if tint[:3] != (255, 255, 255):
                    band = pygame.Surface(px(rect).size, pygame.SRCALPHA)
                    band.fill(tint)
                    self.canvas.blit(band, px(rect).topleft)
            self.canvas.fill(RULE if self.hd() else (178, 179, 179),
                             (round(rect.x * k), round(rect.y * k), round(rect.width * k), k))
            game = session.engine.word_game
            offset = 0
            if game and game.animation_ms:
                offset = (game.animation_ms / 200) * (-210 if row.index % 2 == 0 else 410)
            self.canvas.set_clip(px(hit))
            self.text.draw_layout(self.canvas, BODY_FONT, row.text, (row.origin[0] + offset) * k,
                                  (row.origin[1] - scroll) * k, scale=k * page.text_scale)
            self.canvas.set_clip(px(self.viewport))
            if row.enabled and hit.height:
                buttons.append((hit, ('choose', row.index)))
        if page.rows:
            rect = page.rows[-1].rect
            y = rect.y + rect.height - scroll
            self.canvas.fill(END_RULE if self.hd() else (178, 179, 179),
                             (round(rect.x * k), round(y * k), round(rect.width * k), k))

        if page.portrait is not None:
            cx, cy = page.portrait.center
            cy -= scroll
            cx, cy = cx * k, cy * k
            ring = self.art.ring_frame(k)
            disc_image = self.art.disc_frame(page.theme, k)
            if self.art.ios_housing():
                # HD's ring is not drawn inside the panel (clipped against the
                # bubble, see DialogueRenderer.ring_frame); the disc is.
                ring = ring.copy()
                left, top = round(cx) - ring.get_width() // 2, round(cy) - ring.get_height() // 2
                pygame.draw.polygon(ring, (0, 0, 0, 0), [
                    (px * k - left, (py - scroll) * k - top)
                    # The panel's art is drawn from the inner rect (10 in), so its
                    # outer edge is page.box itself.
                    for px, py in self.art.housing_polygon(
                        Rect(page.box.x + 10, page.box.y + 10, page.box.width - 20, page.box.height - 20))])
            m = self.margin
            self.wide.blit(ring, ring.get_rect(center=(round(cx) + m, round(cy))))
            self.wide.blit(disc_image, disc_image.get_rect(center=(round(cx) + m, round(cy))))
            details = session.pending.details
            asset = session.engine.character_art_variants[details['character_id']][0]
            # FUN_000ae5d4 requests expression zero, independently of dialogue.
            flipped = details['portrait_mode'] == 2 and page.theme != 3
            image = None
            if self.art.ios_housing():
                # HD's menu portrait is an SHSPortraitLayer too (SHSUIMenu::addPortraitToMenu), composed as the
                # dialogue's (DialogueRenderer.hd_portrait) in the ring's square.
                composed = self.art.hd_portrait(asset, flipped, k)
                if composed is not None:
                    art, lift = composed
                    housing = ring.get_rect(center=(round(cx) + m, round(cy)))
                    self.wide.blit(art, (housing.x, housing.y - lift))
            else:
                image = self.art.portrait(asset, flipped, k, crop=True)
            if image is not None:
                # portrait(crop=True) already removed FUN_0005afbc's final
                # 12 rows after masking.
                # Top-anchored to the fixed outer ring (37, 128px, shared by
                # every theme), not bottom-anchored like the dialogue
                # panel's own portrait. Measured directly against a real
                # device screenshot of this exact choice
                # (reference/IMG_0085.PNG, pixel-traced): the portrait
                # nearly fills the ring's own diameter top to bottom (hair
                # sits ~3% of the ring's diameter below the ring's own top,
                # chin/shoulders reach to ~97% of the way down) -- bottom-
                # anchoring it (this file's first pass, copying the
                # dialogue panel's own anchor without checking whether the
                # same model applied here) left a large empty gap of ring
                # backdrop showing above the hair instead.
                #
                # portrait()'s own HD-vs-Android scale (this session's
                # earlier fix, for the dialogue panel) fits the HD source
                # to *contain* within the Android original's own bounding
                # box (scaling by whichever axis needs it more, so neither
                # exceeds the Android size). That's the right call for
                # dialogue, where the portrait is meant to stay within a
                # fixed frame. It's the wrong one here: this asset's HD
                # source (226x256) and Android original (94x123) don't
                # share an aspect ratio, so containing by width leaves the
                # result short on height (94px trimmed, not the ~120px
                # needed) -- direct user feedback confirmed with a
                # zoomed-in comparison against the real device (the
                # portrait's own bottom curve should line up with the
                # ring's, not fall short of it). Re-scaled here,
                # specifically for this panel, to the real measured target
                # instead: real device confirmed
                # (reference/IMG_0085.PNG) the portrait fills ~94% of the
                # ring's own diameter.
                ring_radius = self.art.ring_frame(k).get_height() / 2
                target_height = ring_radius * 2 * 0.94
                if image.get_height() != target_height:
                    scale = target_height / image.get_height()
                    size = (max(1, round(image.get_width() * scale)), max(1, round(target_height)))
                    image = pygame.transform.smoothscale(image, size)
                # Direct user feedback against a live render: the bottom
                # (shoulders) escaped past the ring's own bottom edge,
                # unlike the real device where they stay inside it --
                # shifted up from the first pass's +3% offset.
                top = round(cy - ring_radius + ring_radius * 2 * -0.02)
                left = round(cx) - image.get_width() // 2
                # Real HD clips the portrait's lower half to the colored
                # inner disc's own curve (user's zoomed comparison: HD's
                # shirt follows the blue circle's edge, ours spilled past
                # it onto the white below). The disc frame's own alpha is
                # that curve; only rows below its center are clipped, so
                # the hair above is left alone.
                disc = self.art.disc_frame(page.theme, k)
                mask = pygame.Surface(image.get_size(), pygame.SRCALPHA)
                mask.fill((255, 255, 255, 255))
                dx, dy = round(cx - disc.get_width() / 2) - left, round(cy - disc.get_height() / 2) - top
                lower = max(0, round(cy) - top)
                if lower < image.get_height():
                    mask.fill((255, 255, 255, 0), (0, lower, image.get_width(), image.get_height() - lower))
                    below = disc.subsurface((0, disc.get_height() // 2, disc.get_width(), disc.get_height() - disc.get_height() // 2))
                    mask.blit(below, (dx, dy + disc.get_height() // 2), special_flags=pygame.BLEND_RGBA_MAX)
                image = image.copy()
                image.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
                self.wide.blit(image, (left + self.margin, top))
        # exp-runtime v0.6.0's overflow fit (choice.ChoiceLayout.page) shrinks the text instead of scrolling.
        self.text.draw_layout(self.canvas, page.title_font, page.title, page.title_origin[0] * k,
                              (page.title_origin[1] - scroll) * k, scale=k * page.text_scale)
        self.text.draw_layout(self.canvas, BODY_FONT, page.description, page.description_origin[0] * k,
                              (page.description_origin[1] - scroll) * k, scale=k * page.text_scale)
        self.canvas.set_clip(None)
        if page.timer_panel is not None:
            panel = page.timer_panel
            self.canvas.blit(self.timer_panel(page.theme, panel.width, panel.height),
                             (round(panel.x * k), round(panel.y * k)))
            clock = self.layout.bank.rectangle(22, 10, panel)
            self.draw_timer((clock.x, clock.y),
                            1 - session.remaining_ms / session.pending.details['timeout_ms'])
        game = session.engine.word_game
        if game:
            pack = {1: 204, 2: 220, 3: 252}.get(page.theme, 236)
            frame = lambda asset, index: self.art.frame_scaled(asset, index, k)
            self.canvas.blit(frame(pack, 9), (130 * k, 353 * k))
            self.canvas.blit(frame(pack, 10), (182 * k, 375 * k))
            self.canvas.blit(pygame.transform.scale(frame(pack, 11), (12 * k, 39 * k)), (221 * k, 375 * k))
            self.canvas.blit(frame(pack, 12), (233 * k, 375 * k))
            self.draw_timer((130, 353), 1 - game.remaining_ms / game.duration_ms)
            # Native score text is at (230,88) in GL coordinates (top y=392).
            score = self.text.layout(BODY_FONT, str(game.score), 60, TextStyle(14, 0, (255, 255, 255)))
            self.text.draw_layout(self.canvas, BODY_FONT, score, (230 - score.width / 2) * k, 392 * k, scale=k)
            if game.animation_ms and game.last_delta:
                color = (37, 147, 56) if game.last_delta > 0 else (255, 0, 0)
                delta = self.text.layout(BODY_FONT, f'{game.last_delta:+d}', 40, TextStyle(14, 0, color))
                self.text.draw_layout(self.canvas, BODY_FONT, delta, 275 * k,
                                      (365 + game.animation_ms / 10) * k, scale=k)
        # The bar's hint is bank-13 string 40 for a timed choice (HD shows it:
        # "Touch choice before time runs out", `IMG_0085`), otherwise 38.
        hint = 'Touch the best choice'
        if hasattr(self.art, 'footer_hint'):
            timed = session.remaining_ms is not None
            hint = self.art.footer_hint(40 if timed else 38,
                                        'Touch choice before time runs out' if timed else hint)
        if session.remaining_ms is not None and page.timer_panel is None:
            timeout_ms = session.pending.details['timeout_ms']
            self.draw_timer_wheel(page, session.remaining_ms, timeout_ms)
        # Desktop draws the bar, gear and this hint edge to edge (see
        # DialogueRenderer.bottom_bar_layer).
        self.footer_text = hint
        if page.max_scroll:
            # A desktop affordance for unusually long options; no choices are
            # discarded or mapped to a different script-visible index.
            track = pygame.Rect(310, 40, 3, self.viewport.height - 43)
            pygame.draw.rect(self.canvas, (100, 100, 100), px(track))
            visible_height = self.viewport.height - 31
            thumb = max(20, int(track.height * visible_height / (visible_height + page.max_scroll)))
            y = track.y + int((track.height - thumb) * scroll / page.max_scroll)
            pygame.draw.rect(self.canvas, (225, 225, 225), px(pygame.Rect(track.x, y, track.width, thumb)))
        # The gear is flush with the frame's left edge, 32 units outside this column.
        buttons.append((pygame.Rect(-32, 422, 92, 58), ('menu',)))
        if target is not None:
            target.blit(pygame.transform.smoothscale(self.canvas, target.get_size()), (0, 0))
        return page, buttons
