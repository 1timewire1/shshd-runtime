"""shshd-runtime: Claire Hart Classic's hidden-object round on screen (Claire Hart plan Stage 3, step 3; reference/Other Games/
docs/CLAIRE_HART_ROUNDS_PLAN.md). The rules are claire_rounds.ClaireRound's; this draws one and turns taps, drags, the wheel,
pinches, keys and the edge arrows into its moves. Art from `chcrounds` (its spec at 26000: the scene's base and sprite pack, the
HUD) and `chc` (Romic). Nothing here decides anything in the game.

The owner's framing (R1, 2026-11-20): the round fills the whole frame, whatever its shape from 3:4 to 9:21; the scene fits the
frame's height (zoom 1-2x on top), panned across by dragging, by the arrows at either edge (hovered, held or touched) and by
L / R; Classic's HUD runs across the frame's width at its 800-wide design's scale (the top bar; the bottom bar with the list
and the power-up wheel). Places are Classic's (the play-test photos chc_05 and chc_07 and its own mock-up UI-FULL, measured in
its 800 x 600 design units). Pieces measured rather than read from its scene: the wheel's segments (matched against the
bottom bar's art) and the list's centre.
"""
import io
import json
import math

from . import graphics as pygame
from . import claire_rounds as cr

ADDON, SPEC = 'chcrounds', 26000
CHC, ROMIC, ROMIC_BOLD = 'chc', 28004, 28005
PILL, PILL_PRESSED = 29106, 29107          # chc's Play Now button (Claire Hart Dialogue's Continue): the summary's Continue
DESIGN_WIDTH = 800
TOP_BAR, BOTTOM_BAR = 41, 131              # cmp_UIbar_top, cmp_UIbar_bottom: Classic's own design-size bars
HI_RES = 1 / 1.5625                        # the HUD's large pieces (ui-top-combobar...) to design units
SEGMENT_SCALE = 0.576
SEGMENTS = {cr.CLAIRVOYANCE: ('extraobjs', (690, 6)), cr.FOCUS: ('zoom', (755, 6)), cr.TIME_WARP: ('time', (662, 37)),
            cr.LOCATOR: ('clicks', (661, 91))}      # on the bottom bar, its top left
ORB_CENTRE, ORB_DIAMETER = (749.5, 95.5), 87
LIST_CENTRE = (382, 89)                    # the six names' node, from the bottom bar's top
LABELS = ((-175, 5), (-175, -15), (0, 5), (0, -15), (175, 17), (175, -3))      # activeobjectlist.labelPositions (y up)
FOUND_LINE = (287, 51)
COMBO_SLOT = (21, 6, 182, 23)              # the combo bar in the top bar: x, y, width, height
NAME_PLATE, SCORE_AT, STAR_AT = (400, 19), (651, 19), (579, 19)
MENU_AT = (25, 91)
TEXT, NAME_TEXT, LIST_TEXT, BLUE_TEXT = (110, 50, 20), (110, 50, 20), (239, 236, 226), (18, 224, 188)
SCORE_TEXT, VALUE_TEXT = (255, 255, 255), (255, 236, 90)
ARROW_SIZE = (54, 120)                     # the edge arrows (new: Classic has none), in canvas pixels at 768 wide
ARROW_SPEED = 900                          # canvas pixels a second, as the scene scrolls under a held arrow
ZOOM_STEP = 0.05                           # touchdetector: the wheel's 0.05 a notch, 1x to 2x
FOUND_POP = 1.08
FOUND_NAME_ALPHA = 90                      # a found name, greyed until it leaves (chc_06's "Marker")


def clamp(value, low=0., high=1.):
    return max(low, min(high, value))


class RoundView:
    """Where the scene is: its zoom (1 to 2 over fitting the frame's height) and the middle of what shows, in the scene's
    pixels. Kept by the renderer, not the save: a resumed round opens centred."""

    def __init__(self, scene_size, canvas_size):
        self.scene = scene_size
        self.canvas = canvas_size
        self.zoom = 1.0
        self.cx, self.cy = scene_size[0] / 2, scene_size[1] / 2

    @property
    def scale(self):
        return self.canvas[1] / self.scene[1] * self.zoom

    def clamp(self):
        half_w, half_h = self.canvas[0] / self.scale / 2, self.canvas[1] / self.scale / 2
        self.cx = clamp(self.cx, half_w, self.scene[0] - half_w) if self.scene[0] > 2 * half_w else self.scene[0] / 2
        self.cy = clamp(self.cy, half_h, self.scene[1] - half_h) if self.scene[1] > 2 * half_h else self.scene[1] / 2

    def source(self):
        """The scene's rectangle showing, in its pixels."""
        w, h = self.canvas[0] / self.scale, self.canvas[1] / self.scale
        return (self.cx - w / 2, self.cy - h / 2, w, h)

    def to_scene(self, x, y):
        left, top, _, _ = self.source()
        return left + x / self.scale, top + y / self.scale

    def to_canvas(self, sx, sy):
        left, top, _, _ = self.source()
        return (sx - left) * self.scale, (sy - top) * self.scale

    def pan(self, dx, dy):
        """Move what shows by (dx, dy) canvas pixels (a drag moves the scene with the finger: the view the other way)."""
        self.cx -= dx / self.scale
        self.cy -= dy / self.scale
        self.clamp()

    def zoom_at(self, delta, x, y):
        """touchdetector.updateZoom: 1x to 2x, about the point (x, y) of the canvas."""
        sx, sy = self.to_scene(x, y)
        self.zoom = clamp(round((self.zoom + delta) * 100) / 100, 1.0, 2.0)
        self.cx += sx - self.to_scene(x, y)[0]
        self.cy += sy - self.to_scene(x, y)[1]
        self.clamp()

    def centre_on(self, sx, sy):
        self.cx, self.cy = sx, sy
        self.clamp()


class ClaireRoundRenderer:
    fills_frame = True                     # the whole frame, whatever its shape (R1)
    frame_units = (384, 512)               # (the player sets this to the frame's shape)

    def __init__(self, resources):
        self.resources = resources
        self.canvas = None
        self._spec = None
        self._images = {}
        self._packs = {}
        self._fonts = {}
        self.view = None
        self._scene = None                 # (scene folder, found count) the composed picture is of
        self._composed = None
        self._scaled = None                # (view key, surface)
        self.held = 0                      # -1 / 1: an edge arrow held (or hovered), 0 none
        self.pressed = None
        self.clock = 0                     # ms, for the renderer's own animations
        self._marks = (cr.NO_OBJECT,) * 3     # the hint's, Focus's and the Locator's objects last drawn

    # -- the add-ons ----------------------------------------------------------------------------------------------------------
    def addon(self, addon, resource):
        data = self.resources.library.addon_resource(addon, resource)
        if data is None:
            raise ValueError(f'The {addon} add-on is missing resource {resource}: import its latest build')
        return data

    def spec(self):
        if self._spec is None:
            self._spec = json.loads(self.addon(ADDON, SPEC))
        return self._spec

    def image(self, key, data_source):
        found = self._images.get(key)
        if found is None:
            found = self._images[key] = pygame.image.load(io.BytesIO(data_source()), 'piece.png').convert_alpha()
        return found

    def hud(self, name):
        return self.image(('hud', name), lambda: self.addon(ADDON, self.spec()['hud'][name]))

    def pack(self, resource):
        found = self._packs.get(resource)
        if found is None:
            found = self._packs[resource] = self.addon(ADDON, resource)
        return found

    def frame(self, animation, number):
        resource, count = self.spec()['hud'][animation]
        number = max(0, min(count - 1, number))
        return self.image((animation, number), lambda: cr.sprite_from_pack(self.pack(resource), number))

    def sprite(self, scene, number):
        return self.image(('sprite', scene, number),
                          lambda: cr.sprite_from_pack(self.pack(self.spec()['scenes'][scene]['sprites']), number))

    def font(self, bold, size):
        key = (bold, size)
        if key not in self._fonts:
            self._fonts[key] = pygame.font.Font(io.BytesIO(self.addon(CHC, ROMIC_BOLD if bold else ROMIC)), max(6, size))
        return self._fonts[key]

    def drop_images(self):
        self._images.clear()
        self._packs.clear()
        self._scene = self._composed = self._scaled = None

    def alpha(self, game):
        return None

    # -- geometry -------------------------------------------------------------------------------------------------------------
    def canvas_size(self):
        wide, tall = self.frame_units
        return 768, max(1024, round(768 * tall / wide))

    @property
    def k(self):
        """Canvas pixels a design unit."""
        return self.canvas.get_width() / DESIGN_WIDTH

    def bar_top(self):
        return self.canvas.get_height() - BOTTOM_BAR * self.k

    def design(self, x, y, bottom=False):
        """A design point (from the top bar's top, or the bottom bar's) in canvas pixels."""
        return x * self.k, (self.bar_top() if bottom else 0) + y * self.k

    def scaled(self, surface, factor):
        size = (max(1, round(surface.get_width() * factor)), max(1, round(surface.get_height() * factor)))
        key = ('scaled', id(surface), size)
        found = self._images.get(key)
        if found is None:
            found = self._images[key] = pygame.transform.smoothscale(surface, size)
        return found

    def arrows(self):
        """The two edge arrows' rectangles (left, right), at the scene's middle height between the bars."""
        w, h = ARROW_SIZE[0] * self.k * 800 / 768, ARROW_SIZE[1] * self.k * 800 / 768
        middle = (TOP_BAR * self.k + self.bar_top()) / 2
        return (pygame.Rect(0, round(middle - h / 2), round(w), round(h)),
                pygame.Rect(round(self.canvas.get_width() - w), round(middle - h / 2), round(w), round(h)))

    def orb_rect(self):
        cx, cy = self.design(*ORB_CENTRE, bottom=True)
        r = ORB_DIAMETER * self.k / 2
        return pygame.Rect(round(cx - r), round(cy - r), round(2 * r), round(2 * r))

    def segment_rects(self):
        out = {}
        for powerup, (name, (x, y)) in SEGMENTS.items():
            piece = self.hud(name)
            w, h = piece.get_width() * SEGMENT_SCALE * self.k, piece.get_height() * SEGMENT_SCALE * self.k
            px, py = self.design(x, y, bottom=True)
            out[powerup] = pygame.Rect(round(px), round(py), round(w), round(h))
        return out

    def label_point(self, slot):
        dx, dy = LABELS[slot]
        return self.design(LIST_CENTRE[0] + dx, LIST_CENTRE[1] - dy, bottom=True)

    def label_rect(self, slot):
        x, y = self.label_point(slot)
        return pygame.Rect(round(x - 80 * self.k), round(y - 10 * self.k), round(160 * self.k), round(20 * self.k))

    # -- the scene --------------------------------------------------------------------------------------------------------------
    def scene_picture(self, game):
        """The scene's base with every unfound object's normal sprite on it, in the layout's order (remade on a find)."""
        key = (game.scene, len(game.found))
        if self._scene != key:
            entry = self.spec()['scenes'][game.scene]
            base = self.image(('base', game.scene), lambda: self.addon(ADDON, entry['base'])).copy()
            for index, (_, normal, _, _) in enumerate(entry['objects']):
                if index in game.found:
                    continue
                number, _, _, left, top = normal
                base.blit(self.sprite(game.scene, number), (left, top))
            self._scene, self._composed, self._scaled = key, base, None
        return self._composed

    def draw_scene(self, game):
        picture = self.scene_picture(game)
        size = self.canvas.get_size()
        if self.view is None or self.view.scene != picture.get_size() or self.view.canvas != size:
            self.view = RoundView(picture.get_size(), size)
            self.view.clamp()
        view_key = (id(picture), round(self.view.cx), round(self.view.cy), self.view.zoom, size)
        if self._scaled is None or self._scaled[0] != view_key:
            left, top, w, h = self.view.source()
            area = pygame.Rect(math.floor(left), math.floor(top), math.ceil(w) + 1, math.ceil(h) + 1).clip(picture.get_rect())
            scaled = pygame.transform.smoothscale(picture.subsurface(area),
                                                  (round(area.width * self.view.scale), round(area.height * self.view.scale)))
            self._scaled = (view_key, scaled, self.view.to_canvas(area.x, area.y))
        _, scaled, at = self._scaled
        self.canvas.fill((0, 0, 0))
        self.canvas.blit(scaled, (round(at[0]), round(at[1])))

    def scene_rect(self, scene_rect):
        """A rectangle of the scene's pixels on the canvas."""
        x, y = self.view.to_canvas(scene_rect[0], scene_rect[1])
        return pygame.Rect(round(x), round(y), round(scene_rect[2] * self.view.scale), round(scene_rect[3] * self.view.scale))

    # -- the frame ------------------------------------------------------------------------------------------------------------
    def draw(self, session):
        self.draw_game(session.engine.claire_round)

    def draw_game(self, game, elapsed_ms=0):
        self.clock += elapsed_ms
        size = self.canvas_size()
        if self.canvas is None or self.canvas.get_size() != size:
            self.canvas = pygame.Surface(size).convert()
            self._scaled = None
        if self.held and self.view is not None:
            self.view.pan(-self.held * ARROW_SPEED * elapsed_ms / 1000, 0)
        self.follow_marks(game)
        self.draw_scene(game)
        self.draw_marks(game)
        self.draw_found(game)
        self.draw_top(game)
        self.draw_bottom(game)
        self.draw_arrows()
        if game.lock_ms:
            self.draw_spam_popup()
        if game.over:
            self.draw_summary(game)

    def text(self, text, bold, size, colour, centre, outline=None):
        font = self.font(bold, round(size * self.k))
        surface = font.render(text, True, colour)
        rect = surface.get_rect(center=(round(centre[0]), round(centre[1])))
        if outline is not None:
            shade = font.render(text, True, outline)
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                self.canvas.blit(shade, rect.move(dx, dy))
        self.canvas.blit(surface, rect)
        return rect

    def draw_top(self, game):
        k = self.k
        self.canvas.blit(self.scaled(self.hud('cmp_UIbar_top'), k), (0, 0))
        x, y, w, h = COMBO_SLOT
        if game.combo > 0:
            bar = self.hud('ui-top-combobarfrozen' if game.time_warp else 'ui-top-combobar')
            fitted = pygame.transform.smoothscale(bar, (max(1, round(w * k)), max(1, round(h * k))))
            shown = max(1, round(w * k * game.combo))
            self.canvas.blit(fitted, (round(x * k), round(y * k)), pygame.Rect(0, 0, shown, fitted.get_height()))
        if game.combo_running:
            self.text(f'Combo x{game.multiplier}', True, 15, TEXT, self.design(x + w / 2, y + h / 2))
        self.text(self.spec_name(game), True, 17, NAME_TEXT, self.design(*NAME_PLATE))
        star = self.scaled(self.hud('icn_star'), 0.6 * k)
        self.canvas.blit(star, star.get_rect(center=tuple(round(v) for v in self.design(*STAR_AT))))
        self.text(str(game.score), True, 18, SCORE_TEXT, self.design(*SCORE_AT))

    def spec_name(self, game):
        """The scene's name as its plate shows it (the round's own scene name, given by the service; else the folder's)."""
        return getattr(game, 'title', None) or game.scene

    def draw_bottom(self, game):
        k = self.k
        top = self.bar_top()
        self.canvas.blit(self.scaled(self.hud('cmp_UIbar_bottom'), k), (0, round(top)))
        self.text(f'{game.found_count}/{game.to_find} Items Found', True, 16, TEXT, self.design(*FOUND_LINE, bottom=True))
        for slot, obj in enumerate(game.slots):
            if obj == cr.NO_OBJECT:
                continue
            name = game.names[obj]
            leaving = next((left for o, left in game.leaving if o == obj), None)
            alpha = 255
            if leaving is not None:
                alpha = FOUND_NAME_ALPHA if leaving >= cr.NAME_HIDE_MS else round(FOUND_NAME_ALPHA * leaving / cr.NAME_HIDE_MS)
            colour = BLUE_TEXT if game.extra[slot] else LIST_TEXT
            if game.locating and obj not in game.found:
                colour = VALUE_TEXT                                                 # (the Psychic Locator's glow)
            if game.focus_target == obj and (self.clock // 300) % 2:
                colour = VALUE_TEXT                                                 # (Focus: its name blinks)
            font = self.font(False, round(17 * k))
            surface = font.render(name, True, colour)
            surface.set_alpha(alpha)
            x, y = self.label_point(slot)
            self.canvas.blit(surface, surface.get_rect(center=(round(x), round(y))))
        menu = self.scaled(self.hud('icn_menu'), 0.75 * k)
        self.canvas.blit(menu, menu.get_rect(center=tuple(round(v) for v in self.design(*MENU_AT, bottom=True))))
        self.draw_wheel(game)

    def draw_wheel(self, game):
        k = self.k
        for powerup, rect in self.segment_rects().items():
            name = SEGMENTS[powerup][0]
            piece = self.scaled(self.hud(name), SEGMENT_SCALE * k)
            usable = game.can_use(powerup)
            if not usable:
                piece = piece.copy()
                piece.fill((110, 110, 110, 255), special_flags=pygame.BLEND_RGBA_MULT)
            self.canvas.blit(piece, rect.topleft)
            left = game.uses_left(powerup)
            if left:
                self.text(str(left), True, 13, VALUE_TEXT, (rect.x + 14 * k, rect.bottom - 12 * k), outline=(60, 40, 0))
        orb = self.orb_rect()
        back = self.scaled(self.hud('hint_empty_back'), orb.width / 84)
        self.canvas.blit(back, back.get_rect(center=orb.center))
        count = self.spec()['hud']['vfx_HintFill'][1]
        if game.hint_ready:
            fill_frame = count - 1
        elif game.hint_refill_ms:
            fill_frame = round((1 - game.hint_refill_ms / cr.HINT_REFILL_MS) * (count - 1))
        else:
            fill_frame = 0
        fill = self.frame('vfx_HintFill', fill_frame)
        fill = self.scaled(fill, orb.width / 104)
        self.canvas.blit(fill, fill.get_rect(center=orb.center))
        glass = self.scaled(self.hud('hint_glass_reflection'), orb.width / 84)
        self.canvas.blit(glass, glass.get_rect(center=orb.center))
        self.text('HINT', True, 22, (226, 255, 200) if game.hint_ready else (150, 170, 150), orb.center, outline=(20, 110, 40))

    def draw_arrows(self):
        for side, rect in enumerate(self.arrows()):
            key = ('arrow', side, rect.size, self.held == (1 if side else -1))
            tab = self._images.get(key)
            if tab is None:
                tab = pygame.Surface(rect.size, pygame.SRCALPHA)
                tab.fill((0, 0, 0, 0))
                active = key[3]
                pygame.draw.rect(tab, (18, 110, 104, 215 if active else 165), tab.get_rect(), border_radius=rect.width // 3)
                pygame.draw.rect(tab, (160, 235, 220, 230), tab.get_rect(), width=3, border_radius=rect.width // 3)
                w, h = rect.size
                tip, back = (w * 0.30, w * 0.62) if side == 0 else (w * 0.70, w * 0.38)
                pygame.draw.lines(tab, (239, 236, 226), False, [(back, h * 0.26), (tip, h * 0.5), (back, h * 0.74)],
                                  max(4, round(w / 7)))
                self._images[key] = tab
            self.canvas.blit(tab, rect.topleft)

    def mark_centre(self, game, obj):
        """Where a mark on object `obj` goes, in the scene's pixels: its normal sprite's middle, moved by its hint offset."""
        _, normal, _, hint = self.spec()['scenes'][game.scene]['objects'][obj]
        return normal[3] + normal[1] / 2 + hint[0], normal[4] + normal[2] / 2 - hint[1]

    def follow_marks(self, game):
        """A new mark (the hint's star, Focus, the Psychic Locator) brings its object into view, the zoom back to 1x as
        Classic's hint resets it (touchTracker.resetZoomLevel): with the scene wider than the frame, it might be off screen."""
        marks = (game.hint_target, game.focus_target, game.locator_target)
        if self.view is not None and marks != self._marks:
            for new, old in zip(marks, self._marks):
                if new != cr.NO_OBJECT and new != old:
                    self.view.zoom = 1.0
                    self.view.centre_on(*self.mark_centre(game, new))
                    self._scaled = None
        self._marks = marks

    def draw_marks(self, game):
        """The hint's star, Focus's spotlight and the Psychic Locator's marker on their objects."""
        entry = self.spec()['scenes'][game.scene]['objects']
        if game.focus_target != cr.NO_OBJECT:
            _, normal, _, hint = entry[game.focus_target]
            centre = self.view.to_canvas(normal[3] + normal[1] / 2 + hint[0], normal[4] + normal[2] / 2 - hint[1])
            dark = pygame.Surface(self.canvas.get_size(), pygame.SRCALPHA)
            dark.fill((0, 0, 0, 150))
            pygame.draw.circle(dark, (0, 0, 0, 0), (round(centre[0]), round(centre[1])), round(110 * self.k))
            self.canvas.blit(dark, (0, 0))
        for target in (game.hint_target, game.locator_target):
            if target == cr.NO_OBJECT:
                continue
            _, normal, _, hint = entry[target]
            centre = self.view.to_canvas(normal[3] + normal[1] / 2 + hint[0], normal[4] + normal[2] / 2 - hint[1])
            count = self.spec()['hud']['vfx_hint_starburst'][1]
            star = self.frame('vfx_hint_starburst', (self.clock // 33) % count)
            star = self.scaled(star, 0.7 * self.k)
            self.canvas.blit(star, star.get_rect(center=(round(centre[0]), round(centre[1]))))

    def draw_found(self, game):
        """A found object's found sprite pops up where it was (objectClicked: 0.83 s), then is gone."""
        entry = self.spec()['scenes'][game.scene]['objects']
        for obj, left in game.leaving:
            age = cr.FOUND_MS + cr.NAME_HIDE_MS - left
            if age >= cr.FOUND_MS:
                continue
            _, _, found, _ = entry[obj]
            number, w, h, x, y = found
            t = age / cr.FOUND_MS
            grow = 1 + (FOUND_POP - 1) * math.sin(math.pi * min(1, t * 1.5))
            picture = self.sprite(game.scene, number)
            size = (max(1, round(w * self.view.scale * grow)), max(1, round(h * self.view.scale * grow)))
            shown = pygame.transform.smoothscale(picture, size)
            shown.set_alpha(round(255 * clamp(2 - 2 * t)))
            cx, cy = self.view.to_canvas(x + w / 2, y + h / 2)
            self.canvas.blit(shown, shown.get_rect(center=(round(cx), round(cy))))

    def draw_spam_popup(self):
        panel = self.scaled(self.hud('panel_background'), 0.62 * self.k)
        rect = panel.get_rect(center=(self.canvas.get_width() // 2, self.canvas.get_height() // 2))
        self.canvas.blit(panel, rect)
        self.text('Clicking Too Fast', True, 24, TEXT, (rect.centerx, rect.y + 24 * self.k))
        self.text("Claire can't focus with all", False, 19, LIST_TEXT, (rect.centerx, rect.centery))
        self.text('those clicks happening!', False, 19, LIST_TEXT, (rect.centerx, rect.centery + 26 * self.k))

    def summary_rects(self):
        panel = self.hud('panel_summary')
        scale = 460 / 372 * self.k
        size = (round(panel.get_width() * scale), round(panel.get_height() * scale))
        rect = pygame.Rect(0, 0, *size)
        rect.center = (self.canvas.get_width() // 2, round(self.canvas.get_height() * 0.45))
        button = pygame.Rect(0, 0, round(210 * self.k), round(57 * self.k))
        button.center = (rect.centerx, round(rect.bottom - 32 * self.k * 460 / 372))
        return rect, scale, button

    def draw_summary(self, game):
        rect, scale, button = self.summary_rects()
        shade = pygame.Surface(self.canvas.get_size(), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 90))
        self.canvas.blit(shade, (0, 0))
        self.canvas.blit(self.scaled(self.hud('panel_summary'), scale), rect)
        s = self.summary_values(game)
        u = rect.width / 460                                  # chc_07's panel, 460 wide in its 800 x 600
        self.text('Level Summary', True, 27, TEXT, (rect.centerx, rect.y + 28 * u))
        self.text('Your Performance', False, 19, LIST_TEXT, (rect.centerx, rect.y + 84 * u))
        star = self.hud('STAR')
        size = round(40 * u)
        whole = self.scaled(star, size / star.get_width())
        dim = whole.copy()
        dim.fill((60, 60, 60, 160), special_flags=pygame.BLEND_RGBA_MULT)
        for i in range(5):
            centre = (round(rect.centerx + (i - 2) * 54 * u), round(rect.y + 128 * u))
            box = whole.get_rect(center=centre)
            self.canvas.blit(dim, box)
            filled = clamp(s['half_stars'] / 2 - i)
            if filled > 0:
                self.canvas.blit(whole, box, pygame.Rect(0, 0, round(box.width * filled), box.height))
        rows = (('Level Score', s['score'], 178), ('Time Bonus', s['time_bonus'], 212), ('Skill Bonus', s['skill_bonus'], 246),
                ('Total Score', s['total'], 306))
        for label, value, y in rows:
            self.text(label, False, 19, LIST_TEXT, (rect.x + 150 * u, rect.y + y * u))
            self.text(str(value), True, 19, VALUE_TEXT, (rect.x + 350 * u, rect.y + y * u))
        pygame.draw.line(self.canvas, (90, 220, 200), (rect.x + 22 * u, rect.y + 278 * u), (rect.right - 22 * u, rect.y + 278 * u),
                         max(1, round(2 * u)))
        pill = self.image(('chc', PILL_PRESSED if self.pressed == 'continue' else PILL),
                          lambda: self.addon(CHC, PILL_PRESSED if self.pressed == 'continue' else PILL))
        self.canvas.blit(pygame.transform.smoothscale(pill, button.size), button)
        self.text('Continue', True, 24, (255, 251, 236), button.center, outline=(20, 70, 30))

    def summary_values(self, game):
        return game.summary()

    # -- input ----------------------------------------------------------------------------------------------------------------
    def objects_at(self, game, x, y):
        """The objects whose normal sprites a tap at canvas (x, y) hits (claire_rounds.pixel_hit), topmost first."""
        sx, sy = self.view.to_scene(x, y)
        entry = self.spec()['scenes'][game.scene]['objects']
        hits = []
        for index in reversed(range(len(entry))):
            if index in game.found:
                continue
            number, w, h, left, top = entry[index][1]
            if not (left <= sx < left + w and top <= sy < top + h):
                continue
            sprite = self.sprite(game.scene, number)
            if cr.pixel_hit(lambda px, py: sprite.get_at((px, py))[3], w, h, sx - left, sy - top):
                hits.append(index)
        return hits

    def hit(self, game, x, y):
        """What a tap at canvas (x, y) means: ('continue',), ('hint',), ('powerup', name), ('label', slot), ('arrow', -1|1),
        ('menu',), ('scene', [objects]) or None (the HUD's bare art)."""
        if game.over:
            _, _, button = self.summary_rects()
            return ('continue',) if button.collidepoint(x, y) else None
        for side, rect in zip((-1, 1), self.arrows()):
            if rect.collidepoint(x, y):
                return ('arrow', side)
        if y >= self.bar_top() + 20 * self.k or y < TOP_BAR * self.k:
            if self.orb_rect().collidepoint(x, y):
                return ('hint',)
            for powerup, rect in self.segment_rects().items():
                if rect.collidepoint(x, y):
                    return ('powerup', powerup)
            for slot in range(len(game.slots)):
                if self.label_rect(slot).collidepoint(x, y):
                    return ('label', slot)
            menu = self.design(*MENU_AT, bottom=True)
            if math.hypot(x - menu[0], y - menu[1]) < 40 * self.k:
                return ('menu',)
            return None
        return ('scene', self.objects_at(game, x, y))
