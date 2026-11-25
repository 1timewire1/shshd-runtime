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
BAR_LEFT, BAR_RIGHT = 95, 145              # the bottom bar's menu socket and wheel socket, from either end (R7)
HI_RES = 1 / 1.5625                        # the HUD's large pieces (ui-top-combobar...) to design units
SEGMENT_SCALE = 0.576
SEGMENTS = {cr.CLAIRVOYANCE: ('extraobjs', (690, 6)), cr.FOCUS: ('zoom', (755, 6)), cr.TIME_WARP: ('time', (662, 37)),
            cr.LOCATOR: ('clicks', (661, 91))}      # on the bottom bar, its top left
ORB_CENTRE, ORB_DIAMETER = (749.5, 95.5), 87
# Where each segment's uses left show, as fractions of its picture (UI-FULL's "10"s: by the eye, the frame, the stopwatch, the
# crosshair).
COUNT_AT = {cr.CLAIRVOYANCE: (0.22, 0.35), cr.FOCUS: (0.30, 0.22), cr.TIME_WARP: (0.22, 0.72), cr.LOCATOR: (0.18, 0.72)}
ORB_TINT = (120, 255, 150, 255)             # the fill's pink smoke made Classic's green
LIST_CENTRE = (375, 86)                    # the six names' node, from the bottom bar's top (chc_05's names, 2026-11-22)
LABELS = ((-175, 5), (-175, -15), (0, 5), (0, -15), (175, 17), (175, -3))      # activeobjectlist.labelPositions (y up)
FOUND_LINE = (287, 51)
COMBO_SLOT = (21, 6, 182, 23)              # the combo bar in the top bar: x, y, width, height
NAME_PLATE, SCORE_AT = (370, 18), (596, 17)     # (the score's star is the top bar art's own: R7 dropped a second)
# Classic's HUD text is Romic regular throughout, its sizes fitted to chc_05-chc_10's widths (owner, 2026-11-22: "match
# Claire Hart's layout exactly"; the bold face ran short) but the count, bold: the scene's name, the combo, the score, the
# count, HINT, a name.
NAME_PX, COMBO_PX, SCORE_PX, COUNT_PX, HINT_PX, LABEL_PX = 19, 20, 22, 19, 27, 17     # (the count bold: regular has no /)
HINT_SHIFT = (5, -2)                        # HINT's centre from the orb's, as Classic's sits
MENU_SCALE = 1.0                            # icn_menu at Classic's size (its bars 47 units long; 0.75 drew them short)
MENU_AT = (32, 91)                         # (Classic's bars' centre, chc_05)
TEXT, NAME_TEXT, LIST_TEXT, BLUE_TEXT = (110, 50, 20), (110, 50, 20), (239, 236, 226), (18, 224, 188)
SCORE_TEXT, VALUE_TEXT = (255, 255, 255), (255, 236, 90)
ARROW_SIZE = (54, 120)                     # the edge arrows (new: Classic has none), in canvas pixels at 768 wide
ARROW_SPEED = 900                          # canvas pixels a second, as the scene scrolls under a held arrow
ZOOM_STEP = 0.05                           # touchdetector: the wheel's 0.05 a notch, 1x to 2x
FOUND_POP = 1.08
COUNT_EXPAND_MS = 850                       # Clairvoyance's six more: "n/18 Items Found" grows and shrinks (itemCountExpand)
BLUE_DARK = (10, 120, 110)
FOUND_NAME_ALPHA = 90                      # a found name, greyed until it leaves (chc_06's "Marker")
# hogscene.doHiddenObjectRemovalAnimation: the found particle flies to the object's name along a Catmull-Rom curve through a
# point 130 units above the object and 60 to the name's side, in 1.67 s (its trail: the particle system's, drawn here as fading
# sparks behind a twinkle).
TRAIL_MS, TRAIL_RISE, TRAIL_SIDE = 1670, 130, 60
TRAIL_SPARKS, TRAIL_SPACING_MS = 14, 28
TRAIL_COLOUR = (190, 255, 160)
# hintpowerup.sendIndicatorToPosition: the star drops from the orb to its object in (distance / 400 x 1.2) s, easing out;
# the orb's explosion (hint_explosion: 0.5 s) as it goes.
HINT_SPEED, HINT_TIME = 400, 1.2
EXPLOSION_MS = 500
# Classic's sounds (references/gamesfx): a find (Object_6_Combo at x5, as combometer.increment), a name coming into the list
# (activeobjectlist.queueShowName), the hint (hintpowerup), Time Warp (addtimepowerup), "Clicking Too Fast", the scene cleared
# (levelsummary) and a button.
SOUND_FIND, SOUND_FIND_X5 = 'Claire_Hart_2_GS_Object_1_Combo', 'Claire_Hart_2_GS_Object_6_Combo'
SOUND_NAME, SOUND_HINT = 'Claire_Hart_2_GS_Object_In_Objectlist', 'Claire_Hart_2_GS_Hint_Power_Up'
SOUND_WARP, SOUND_POPUP = 'Claire_Hart_2_GS_Time_Wrap_Power_Up', 'Claire_Hart_2_GS_Pop_UP_Notification'
SOUND_CLEARED, SOUND_BUTTON = 'Claire_Hart_2_GS_Scene_Cleard', 'Claire_Hart_2_GES_Button_Click'
SOUND_FOCUS = 'Claire_Hart_2_DS_Focus_Different_Character'


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
        self.effects = []                  # [kind, start clock, data]: trails, the hint's flight, the orb's explosion
        self.sounds = []                   # Classic's sounds due (their names), for the player to play and empty
        self._was = None                   # what the last frame showed, for the sounds
        self._ticks = None                 # the wall clock at the last draw (draw: the renderer's own animations)
        self.drag = None                   # (start, last) canvas points of a press on the scene, panning once it moves
        self._seen_found = None            # (game, how many found) last drawn: a new find starts its trail
        self._expanded_at = None           # when Clairvoyance last added its six (the count's expansion)

    # -- the add-ons ----------------------------------------------------------------------------------------------------------
    def addon(self, addon, resource):
        data = self.resources.library.addon_resource(addon, resource)
        if data is None:
            raise ValueError(f'The {addon} add-on is missing resource {resource}: import its latest build')
        return data

    def base_picture(self, entry):
        """A scene's base: the rounds add-on's own resource, or (chcrounds revision 2, ch2rounds) [add-on, resource] in the
        story add-on that holds the same picture as a backdrop (the cases need it, so it is always there; 2026-11-25:
        319 MB of chcrounds and 282 MB of ch2rounds were copies)."""
        base = entry['base']
        return self.addon(*base) if isinstance(base, list) else self.addon(ADDON, base)

    def spec(self):
        if self._spec is None:
            shared = getattr(self.resources.library, 'addon_json', None)     # (parsed once for the library, the engine's too)
            self._spec = shared(ADDON, SPEC) if shared is not None else None
            if self._spec is None:
                self._spec = json.loads(self.addon(ADDON, SPEC))
        return self._spec

    def preload_steps(self, game):
        """What the round's first frame reads and draws, a piece at a time (a generator: one piece a step), so the player can
        spread it over the frames its skip prompt shows (owner, 2026-11-21: entering a round held a frame ~200 ms on the
        g54, 1.8 s the first time). The scene's base, each sprite still to find, the composed and scaled scene, then both
        bars once into the canvas (their pieces and text sizes cached). Nothing here changes the round."""
        entry = self.spec()['scenes'][game.scene]
        yield
        self.image(('base', game.scene), lambda: self.base_picture(entry))
        yield
        for index, (_, normal, _, _) in enumerate(entry['objects']):
            if index not in game.found:
                self.sprite(game.scene, normal[0])
                yield
        self.scene_picture(game)
        yield
        size = self.canvas_size()
        if self.canvas is None or self.canvas.get_size() != size:
            self.canvas = pygame.Surface(size).convert()
            self._scaled = None
        self.draw_scene(game)
        yield
        self.draw_top(game)
        yield
        self.draw_bottom(game)

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
        return 768, round(768 * tall / wide)        # (the frame's own shape: 3:4 to 9:21, a little wider on a desktop)

    @property
    def k(self):
        """Canvas pixels a design unit."""
        return self.canvas.get_width() / DESIGN_WIDTH

    # Taller frames (rounds plan R7, the owner's B, 2026-11-21): Classic's HUD, drawn for 800 x 600, would shrink with the
    # width. From 3:4 (Classic's size) to 20:9 and taller it grows: the bottom bar to TALL_BAR times its height (its menu
    # and wheel sockets scaled with it, its middle stretched across what's left of the width), the names and count and
    # the top bar to TALL_TEXT, the Level Summary from Classic's 57.5% of the width to TALL_SUMMARY.
    TALL_BAR, TALL_TEXT, TALL_SUMMARY = 1.45, 1.3, 0.88
    top_pad = 0                            # canvas pixels of the top under a phone's status bar (Desktop._sync_story_scale)

    def tallness(self):
        """0 at 3:4 (or wider) to 1 at 20:9 (or taller)."""
        width, height = self.canvas.get_size()
        return clamp((height / width - 4 / 3) / (20 / 9 - 4 / 3))

    def grown(self, most):
        return 1 + (most - 1) * self.tallness()

    @property
    def kb(self):
        """The bottom bar's pieces (its sockets, the menu, the wheel and orb): canvas pixels a design unit."""
        return self.k * self.grown(self.TALL_BAR)

    @property
    def kt(self):
        """The top bar's height and the HUD's text (the names, the count, the plate, the score)."""
        return self.k * self.grown(self.TALL_TEXT)

    def bar_slices(self):
        """The bottom bar drawn in three: (its menu socket's width, its middle's, its wheel socket's), canvas pixels."""
        left, right = BAR_LEFT * self.kb, BAR_RIGHT * self.kb
        return left, self.canvas.get_width() - left - right, right

    def bar_top(self):
        return self.canvas.get_height() - BOTTOM_BAR * self.kb

    def top_bar_bottom(self):
        """Where the top bar ends: below a phone's status bar, at the grown height."""
        return self.top_pad + TOP_BAR * self.kt

    def design(self, x, y, bottom=False):
        """A design point (from the top bar's top, or the bottom bar's) in canvas pixels. On the bottom bar, a point in a
        socket keeps to its corner and one in the middle stretches with it (bar_slices)."""
        if not bottom:
            return x * self.k, self.top_pad + y * self.kt
        left, middle, _ = self.bar_slices()
        if x < BAR_LEFT:
            px = x * self.kb
        elif x >= DESIGN_WIDTH - BAR_RIGHT:
            px = self.canvas.get_width() - (DESIGN_WIDTH - x) * self.kb
        else:
            px = left + (x - BAR_LEFT) / (DESIGN_WIDTH - BAR_LEFT - BAR_RIGHT) * middle
        return px, self.bar_top() + y * self.kb

    def scaled(self, surface, factor):
        size = (max(1, round(surface.get_width() * factor)), max(1, round(surface.get_height() * factor)))
        key = ('scaled', id(surface), size)
        found = self._images.get(key)
        if found is None:
            found = self._images[key] = pygame.transform.smoothscale(surface, size)
        return found

    def arrow_shown(self, side):
        """Whether the scene goes on that way (-1 left, 1 right): at its edge, that arrow goes (owner, 2026-11-20)."""
        if self.view is None:
            return True
        left, _, width, _ = self.view.source()
        return left > 0.5 if side < 0 else left + width < self.view.scene[0] - 0.5

    def arrows(self):
        """The two edge arrows' rectangles (left, right), at the scene's middle height between the bars."""
        w, h = ARROW_SIZE[0] * self.k * 800 / 768, ARROW_SIZE[1] * self.k * 800 / 768
        middle = (self.top_bar_bottom() + self.bar_top()) / 2
        return (pygame.Rect(0, round(middle - h / 2), round(w), round(h)),
                pygame.Rect(round(self.canvas.get_width() - w), round(middle - h / 2), round(w), round(h)))

    def orb_rect(self):
        cx, cy = self.design(*ORB_CENTRE, bottom=True)
        r = ORB_DIAMETER * self.kb / 2
        return pygame.Rect(round(cx - r), round(cy - r), round(2 * r), round(2 * r))

    def segment(self, name):
        """A wheel segment's own picture: chcrounds holds each whole (Classic's 303 x 235 canvas, the segment inside it), and
        SEGMENTS places what it shows."""
        key = ('segment', name)
        found = self._images.get(key)
        if found is None:
            whole = self.hud(name)
            found = self._images[key] = whole.subsurface(whole.get_bounding_rect()).copy()
        return found

    def segment_rects(self):
        out = {}
        for powerup, (name, (x, y)) in SEGMENTS.items():
            piece = self.segment(name)
            w, h = piece.get_width() * SEGMENT_SCALE * self.kb, piece.get_height() * SEGMENT_SCALE * self.kb
            px, py = self.design(x, y, bottom=True)
            out[powerup] = pygame.Rect(round(px), round(py), round(w), round(h))
        return out

    def label_point(self, slot):
        dx, dy = LABELS[slot]
        return self.design(LIST_CENTRE[0] + dx, LIST_CENTRE[1] - dy, bottom=True)

    def label_rect(self, slot):
        x, y = self.label_point(slot)
        half = 80 * self.k * self.bar_slices()[1] / ((DESIGN_WIDTH - BAR_LEFT - BAR_RIGHT) * self.k)   # (its column's)
        return pygame.Rect(round(x - half), round(y - 10 * self.kt), round(2 * half), round(20 * self.kt))

    # -- the scene --------------------------------------------------------------------------------------------------------------
    def scene_picture(self, game):
        """The scene's base with every unfound object's normal sprite on it, in the layout's order (remade on a find)."""
        key = (game.scene, len(game.found))
        if self._scene != key:
            entry = self.spec()['scenes'][game.scene]
            base = self.image(('base', game.scene), lambda: self.base_picture(entry)).copy()
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
        now = pygame.time.get_ticks()
        elapsed = 0 if self._ticks is None else max(0, min(250, now - self._ticks))
        self._ticks = now
        self.draw_game(session.engine.claire_round, elapsed)

    def sound_cues(self, game):
        """Queue Classic's sounds for what changed since the last frame."""
        now = dict(found=len(game.found), x5=game.x5_finds, to_find=game.to_find, names=tuple(game.slots), hint=game.hint_target,
                   warp=game.time_warp, lock=bool(game.lock_ms), over=game.over, focus=game.focus_target,
                   locator=game.locator_target)
        was, self._was = self._was, now
        if was is None:
            return
        if now['found'] > was['found']:
            self.sounds.append(SOUND_FIND_X5 if now['x5'] > was['x5'] else SOUND_FIND)
        if any(o != cr.NO_OBJECT and o != before for o, before in zip(now['names'], was['names'])):
            self.sounds.append(SOUND_NAME)
        if now['hint'] != cr.NO_OBJECT and now['hint'] != was['hint']:
            self.sounds.append(SOUND_HINT)
        if (now['focus'] != was['focus'] and now['focus'] != cr.NO_OBJECT) or \
                (now['locator'] != was['locator'] and now['locator'] != cr.NO_OBJECT):
            self.sounds.append(SOUND_FOCUS)
        if now['warp'] and not was['warp']:
            self.sounds.append(SOUND_WARP)
        if now['to_find'] > was['to_find']:
            self.sounds.append(SOUND_HINT)
            self._expanded_at = self.clock
            self.effects.append(['explosion_at', self.clock, self.segment_rects()[cr.CLAIRVOYANCE].center])
        if now['lock'] and not was['lock']:
            self.sounds.append(SOUND_POPUP)
        if now['over'] and not was['over']:
            self.sounds.append(SOUND_CLEARED)

    def sound_resource(self, name):
        return self.spec()['sounds'].get(name)

    def draw_game(self, game, elapsed_ms=0):
        self.clock += elapsed_ms
        size = self.canvas_size()
        if self.canvas is None or self.canvas.get_size() != size:
            self.canvas = pygame.Surface(size).convert()
            self._scaled = None
        if self.held and self.view is not None:
            self.view.pan(-self.held * ARROW_SPEED * elapsed_ms / 1000, 0)
            if not self.arrow_shown(self.held):
                self.held = 0                   # (at the edge: its arrow has gone)
        self.start_effects(game)
        self.sound_cues(game)
        self.follow_marks(game)
        self.draw_scene(game)
        self.draw_marks(game)
        self.draw_found(game)
        self.draw_top(game)
        self.draw_bottom(game)
        self.draw_effects(game)
        self.draw_arrows()
        if game.lock_ms:
            self.draw_spam_popup()
        if game.over:
            self.draw_summary(game)

    def text(self, text, bold, size, colour, centre, outline=None, scale=None):
        """`size` in design units, at `scale` canvas pixels a unit (the width's, `k`, unless given: kb, kt, a panel's)."""
        font = self.font(bold, round(size * (self.k if scale is None else scale)))
        surface = font.render(text, True, colour)
        rect = surface.get_rect(center=(round(centre[0]), round(centre[1])))
        if outline is not None:
            shade = font.render(text, True, outline)
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                self.canvas.blit(shade, rect.move(dx, dy))
        self.canvas.blit(surface, rect)
        return rect

    STRIP_DARK = 235                       # the faded strip's darkness at the screen's top (0-255)

    def draw_top(self, game):
        """The top bar (Classic's: the combo, the scene's name, the score), its height grown in a taller frame (R7) and below
        a phone's status bar, the strip above it the bar's own colour run up under the status bar and fading darker
        toward the screen's edge (owner, 2026-11-21). The score's star is the bar art's own (the renderer drew a second,
        icn_star, beside it)."""
        k, kt, pad = self.k, self.kt, round(self.top_pad)
        art = self.hud('cmp_UIbar_top')
        width = self.canvas.get_width()
        key = ('top bar', width, round(TOP_BAR * kt), pad)
        drawn = self._images.get(key)
        if drawn is None:
            drawn = pygame.Surface((width, pad + round(TOP_BAR * kt)), pygame.SRCALPHA)
            drawn.fill((0, 0, 0, 0))
            if pad:
                row = art.subsurface((0, 3, art.get_width(), 2))
                drawn.blit(pygame.transform.smoothscale(row, (width, pad)), (0, 0))
                shade = pygame.Surface((width, pad), pygame.SRCALPHA)
                for y in range(pad):
                    shade.fill((0, 0, 0, round(self.STRIP_DARK * (1 - y / pad) ** 0.8)), (0, y, width, 1))
                drawn.blit(shade, (0, 0))
            drawn.blit(pygame.transform.smoothscale(art, (width, round(TOP_BAR * kt))), (0, pad))
            self._images[key] = drawn
        self.canvas.blit(drawn, (0, 0))
        x, y, w, h = COMBO_SLOT
        if game.combo > 0:
            bar = self.hud('ui-top-combobarfrozen' if game.time_warp else 'ui-top-combobar')
            fitted = pygame.transform.smoothscale(bar, (max(1, round(w * k)), max(1, round(h * kt))))
            shown = max(1, round(w * k * game.combo))
            self.canvas.blit(fitted, (round(x * k), round(pad + y * kt)), pygame.Rect(0, 0, shown, fitted.get_height()))
        if game.combo_running:
            self.text(f'Combo x{game.multiplier}', False, COMBO_PX, TEXT, self.design(x + w / 2, y + h / 2), scale=kt)
        self.text(self.spec_name(game), False, NAME_PX, NAME_TEXT, self.design(*NAME_PLATE), scale=kt)
        self.text(str(game.score), False, SCORE_PX, SCORE_TEXT, self.design(*SCORE_AT), scale=kt)

    def spec_name(self, game):
        """The scene's name as its plate shows it (the round's own scene name, given by the service; else the folder's)."""
        return getattr(game, 'title', None) or game.scene

    def draw_bottom(self, game):
        kb, kt = self.kb, self.kt
        top = self.bar_top()
        self.canvas.blit(self.bottom_bar(), (0, round(top)))
        grow = 1.0
        if self._expanded_at is not None and self.clock - self._expanded_at < COUNT_EXPAND_MS:
            grow = 1 + 0.35 * math.sin(math.pi * (self.clock - self._expanded_at) / COUNT_EXPAND_MS)   # (itemCountExpand)
        self.text(f'{game.found_count}/{game.to_find} Items Found', True, round(COUNT_PX * grow), TEXT if grow == 1.0 else BLUE_DARK,
                  self.design(*FOUND_LINE, bottom=True), scale=kt)
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
            font = self.font(False, round(LABEL_PX * kt))
            surface = font.render(name, True, colour)
            surface.set_alpha(alpha)
            x, y = self.label_point(slot)
            self.canvas.blit(surface, surface.get_rect(center=(round(x), round(y))))
        menu = self.scaled(self.hud('icn_menu'), MENU_SCALE * kb)
        self.canvas.blit(menu, menu.get_rect(center=tuple(round(v) for v in self.design(*MENU_AT, bottom=True))))
        self.draw_wheel(game)

    def bottom_bar(self):
        """The bottom bar's art at this frame: its menu and wheel sockets scaled by kb, its middle stretched between them
        (bar_slices; at 3:4 Classic's bar as it is). Made once a size."""
        width = self.canvas.get_width()
        height = round(BOTTOM_BAR * self.kb)
        key = ('bottom bar', width, height)
        found = self._images.get(key)
        if found is None:
            art = self.hud('cmp_UIbar_bottom')
            left, middle, right = self.bar_slices()
            found = pygame.Surface((width, height), pygame.SRCALPHA)
            found.fill((0, 0, 0, 0))
            for x0, x1, at, size in ((0, BAR_LEFT, 0, left), (BAR_LEFT, DESIGN_WIDTH - BAR_RIGHT, left, middle),
                                     (DESIGN_WIDTH - BAR_RIGHT, DESIGN_WIDTH, left + middle, right)):
                piece = art.subsurface((x0, 0, x1 - x0, art.get_height()))
                found.blit(pygame.transform.smoothscale(piece, (max(1, round(at + size) - round(at)), height)),
                           (round(at), 0))
            self._images[key] = found
        return found

    def draw_wheel(self, game):
        k = self.kb
        for powerup, rect in self.segment_rects().items():
            name = SEGMENTS[powerup][0]
            piece = self.scaled(self.segment(name), SEGMENT_SCALE * k)
            usable = game.can_use(powerup)
            if not usable:
                piece = piece.copy()
                piece.fill((110, 110, 110, 255), special_flags=pygame.BLEND_RGBA_MULT)
            self.canvas.blit(piece, rect.topleft)
            left = game.uses_left(powerup)
            if left:
                fx, fy = COUNT_AT[powerup]
                self.text(str(left), True, 13, VALUE_TEXT, (rect.x + fx * rect.width, rect.y + fy * rect.height),
                          outline=(60, 40, 0), scale=k)
        orb = self.orb_rect()
        back = self.scaled(self.hud('hint_empty_back'), orb.width / 84)
        self.canvas.blit(back, back.get_rect(center=orb.center))
        count = self.spec()['hud']['vfx_HintFill'][1]
        if game.hint_refill_ms > cr.HINT_FILL_MS:          # (hint_empty: draining)
            fill_frame = round((game.hint_refill_ms - cr.HINT_FILL_MS) / cr.HINT_EMPTY_MS * (count - 1))
        elif game.hint_refill_ms:                          # (hint_full_fill: refilling)
            fill_frame = round((1 - game.hint_refill_ms / cr.HINT_FILL_MS) * (count - 1))
        else:
            fill_frame = count - 1
        fill = self.scaled(self.green_fill(fill_frame), orb.width / 104)
        self.canvas.blit(fill, fill.get_rect(center=orb.center))
        glass = self.scaled(self.hud('hint_glass_reflection'), orb.width / 84)
        self.canvas.blit(glass, glass.get_rect(center=orb.center))
        self.text('HINT', False, HINT_PX, (232, 255, 236) if game.hint_ready else (150, 170, 150),
                  (orb.centerx + HINT_SHIFT[0] * k, orb.centery + HINT_SHIFT[1] * k), outline=(20, 110, 40),
                  scale=k)

    def green_fill(self, number):
        """The orb's fill: vfx_HintFill's frames are pink smoke, which Classic tints green (its orb is green glass, UI-FULL)."""
        key = ('green fill', number)
        found = self._images.get(key)
        if found is None:
            found = self.frame('vfx_HintFill', number).copy()
            found.fill(ORB_TINT, special_flags=pygame.BLEND_RGBA_MULT)
            self._images[key] = found
        return found

    def draw_arrows(self):
        for side, rect in enumerate(self.arrows()):
            if not self.arrow_shown(1 if side else -1):
                continue
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

    # -- effects --------------------------------------------------------------------------------------------------------------
    def start_effects(self, game):
        """A new find starts its trail to its name; a new hint, the star's flight from the orb and the orb's explosion."""
        if self._seen_found is None or self._seen_found[0] is not game:
            self._seen_found = (game, len(game.found))
            self.effects.clear()
        for obj in game.found[self._seen_found[1]:]:
            if obj in game.slots:
                slot = game.slots.index(obj)
                start = self.view.to_canvas(*self.found_centre(game, obj)) if self.view else (0, 0)
                self.effects.append(['trail', self.clock, (start, self.label_point(slot))])
        self._seen_found = (game, len(game.found))
        if game.hint_target != cr.NO_OBJECT and game.hint_target != self._marks[0]:
            self.effects.append(['hint', self.clock, game.hint_target])
            self.effects.append(['explosion', self.clock, None])
        self.effects = [e for e in self.effects if self.clock - e[1] < self.effect_length(e)]

    def effect_length(self, effect):
        kind = effect[0]
        if kind == 'trail':
            return TRAIL_MS + TRAIL_SPARKS * TRAIL_SPACING_MS
        if kind in ('explosion', 'explosion_at'):
            return EXPLOSION_MS
        return self.flight_ms(effect)

    def found_centre(self, game, obj):
        _, _, found, _ = self.spec()['scenes'][game.scene]['objects'][obj]
        return found[3] + found[1] / 2, found[4] + found[2] / 2

    def flight_ms(self, effect):
        """The hint star's flight time (hintpowerup: distance / 400 x 1.2 s, in design units)."""
        game_target = effect[2]
        start, end = self.flight_ends(game_target)
        return max(200, round(math.hypot(end[0] - start[0], end[1] - start[1]) / self.k / HINT_SPEED * HINT_TIME * 1000))

    def flight_ends(self, target):
        game = self._seen_found[0]
        return self.orb_rect().center, self.view.to_canvas(*self.mark_centre(game, target))

    def flying(self, target):
        return any(e[0] == 'hint' and e[2] == target for e in self.effects)

    @staticmethod
    def catmull_rom(points, t):
        """A point along a Catmull-Rom curve through `points` (ends doubled), t from 0 to 1."""
        pts = [points[0], *points, points[-1]]
        segments = len(points) - 1
        f = min(segments - 1e-9, max(0.0, t * segments))
        i = int(f)
        u = f - i
        p0, p1, p2, p3 = pts[i], pts[i + 1], pts[i + 2], pts[i + 3]
        return tuple(0.5 * ((2 * p1[n]) + (-p0[n] + p2[n]) * u + (2 * p0[n] - 5 * p1[n] + 4 * p2[n] - p3[n]) * u * u
                            + (-p0[n] + 3 * p1[n] - 3 * p2[n] + p3[n]) * u ** 3) for n in (0, 1))

    def draw_effects(self, game):
        for kind, start, data in self.effects:
            age = self.clock - start
            if kind == 'trail':
                self.draw_trail(age, *data)
            elif kind == 'hint':
                self.draw_flight(age, data)
            elif kind in ('explosion', 'explosion_at'):
                count = self.spec()['hud']['vfx_explosion'][1]
                frame = self.frame('vfx_explosion', min(count - 1, age * count // EXPLOSION_MS))
                frame = self.scaled(frame, self.orb_rect().width / 120)
                self.canvas.blit(frame, frame.get_rect(center=self.orb_rect().center if kind == 'explosion' else data))

    def draw_trail(self, age, start, end):
        side = TRAIL_SIDE if end[0] > start[0] else -TRAIL_SIDE
        middle = (start[0] + side * self.k, start[1] - TRAIL_RISE * self.k)
        points = (start, middle, end)
        for n in range(TRAIL_SPARKS):
            t = (age - n * TRAIL_SPACING_MS) / TRAIL_MS
            if not 0 <= t <= 1:
                continue
            x, y = self.catmull_rom(points, t)
            fade = 1 - n / TRAIL_SPARKS
            radius = max(1, round((6 - 4 * n / TRAIL_SPARKS) * self.k))
            spark = pygame.Surface((radius * 4, radius * 4), pygame.SRCALPHA)
            spark.fill((0, 0, 0, 0))
            pygame.draw.circle(spark, (*TRAIL_COLOUR, round(90 * fade)), (radius * 2, radius * 2), radius * 2)
            pygame.draw.circle(spark, (255, 255, 240, round(230 * fade)), (radius * 2, radius * 2), radius)
            self.canvas.blit(spark, (round(x) - radius * 2, round(y) - radius * 2))
        t = age / TRAIL_MS
        if 0 <= t <= 1:
            count = self.spec()['hud']['vfx_sparkles'][1]
            twinkle = self.scaled(self.frame('vfx_sparkles', (age // 40) % count), 0.5 * self.k)
            x, y = self.catmull_rom(points, t)
            self.canvas.blit(twinkle, twinkle.get_rect(center=(round(x), round(y))))

    def draw_flight(self, age, target):
        """The hint's star on its way: easing out from the orb to the object, its tail behind it."""
        start, end = self.flight_ends(target)
        length = self.flight_ms(['hint', 0, target])
        t = min(1.0, age / length)
        eased = 1 - (1 - t) ** 2
        x, y = start[0] + (end[0] - start[0]) * eased, start[1] + (end[1] - start[1]) * eased
        tails = self.spec()['hud']['vfx_hint_tail'][1]
        tail = self.scaled(self.frame('vfx_hint_tail', min(tails - 1, round(t * (tails - 1)))), 0.6 * self.k)
        angle = math.degrees(math.atan2(-(end[1] - start[1]), end[0] - start[0])) - 90
        tail = pygame.transform.rotate(tail, angle)
        dx, dy = end[0] - start[0], end[1] - start[1]
        norm = math.hypot(dx, dy) or 1
        behind = (x - dx / norm * tail.get_height() * 0.25, y - dy / norm * tail.get_height() * 0.25)
        self.canvas.blit(tail, tail.get_rect(center=(round(behind[0]), round(behind[1]))))
        count = self.spec()['hud']['vfx_hint_starburst'][1]
        star = self.scaled(self.frame('vfx_hint_starburst', (age // 33) % count), (1.0 - 0.3 * eased) * 0.7 * self.k)
        self.canvas.blit(star, star.get_rect(center=(round(x), round(y))))

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
            if target == cr.NO_OBJECT or (target == game.hint_target and self.flying(target)):
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

    @property
    def ku(self):
        """The centred panels' (the Level Summary's, "Clicking Too Fast"'s) canvas pixels a design unit: the width's at 3:4
        (the summary 460 of Classic's 800), growing to TALL_SUMMARY of the width at 20:9 (R7)."""
        share = 460 / DESIGN_WIDTH
        return self.canvas.get_width() * (share + (self.TALL_SUMMARY - share) * self.tallness()) / 460

    def draw_spam_popup(self):
        u = self.ku
        panel = self.scaled(self.hud('panel_background'), 0.62 * u)
        rect = panel.get_rect(center=(self.canvas.get_width() // 2, self.canvas.get_height() // 2))
        self.canvas.blit(panel, rect)
        self.text('Clicking Too Fast', True, 24, TEXT, (rect.centerx, rect.y + 24 * u), scale=u)
        self.text("Claire can't focus with all", False, 19, LIST_TEXT, (rect.centerx, rect.centery), scale=u)
        self.text('those clicks happening!', False, 19, LIST_TEXT, (rect.centerx, rect.centery + 26 * u), scale=u)

    def summary_rects(self):
        panel = self.hud('panel_summary')
        u = self.ku
        scale = 460 / 372 * u
        size = (round(panel.get_width() * scale), round(panel.get_height() * scale))
        rect = pygame.Rect(0, 0, *size)
        rect.center = (self.canvas.get_width() // 2, round(self.canvas.get_height() * 0.45))
        button = pygame.Rect(0, 0, round(210 * u), round(57 * u))
        button.center = (rect.centerx, round(rect.bottom - 32 * u * 460 / 372))
        return rect, scale, button

    def draw_summary(self, game):
        rect, scale, button = self.summary_rects()
        shade = pygame.Surface(self.canvas.get_size(), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 90))
        self.canvas.blit(shade, (0, 0))
        self.canvas.blit(self.scaled(self.hud('panel_summary'), scale), rect)
        s = self.summary_values(game)
        u = rect.width / 460                                  # chc_07's panel, 460 wide in its 800 x 600
        self.text('Level Summary', True, 27, TEXT, (rect.centerx, rect.y + 28 * u), scale=u)
        self.text('Your Performance', False, 19, LIST_TEXT, (rect.centerx, rect.y + 84 * u), scale=u)
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
            self.text(label, False, 19, LIST_TEXT, (rect.x + 150 * u, rect.y + y * u), scale=u)
            self.text(str(value), True, 19, VALUE_TEXT, (rect.x + 350 * u, rect.y + y * u), scale=u)
        pygame.draw.line(self.canvas, (90, 220, 200), (rect.x + 22 * u, rect.y + 278 * u), (rect.right - 22 * u, rect.y + 278 * u),
                         max(1, round(2 * u)))
        pill = self.image(('chc', PILL_PRESSED if self.pressed == 'continue' else PILL),
                          lambda: self.addon(CHC, PILL_PRESSED if self.pressed == 'continue' else PILL))
        self.canvas.blit(pygame.transform.smoothscale(pill, button.size), button)
        self.text('Continue', True, 24, (255, 251, 236), button.center, outline=(20, 70, 30), scale=u)

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
            if rect.collidepoint(x, y) and self.arrow_shown(side):
                return ('arrow', side)
        if y >= self.bar_top() + 20 * self.kb or y < self.top_bar_bottom():
            if self.orb_rect().collidepoint(x, y):
                return ('hint',)
            for powerup, rect in self.segment_rects().items():
                if rect.collidepoint(x, y):
                    return ('powerup', powerup)
            for slot in range(len(game.slots)):
                if self.label_rect(slot).collidepoint(x, y):
                    return ('label', slot)
            menu = self.design(*MENU_AT, bottom=True)
            if math.hypot(x - menu[0], y - menu[1]) < 40 * self.kb:
                return ('menu',)
            return None
        return ('scene', self.objects_at(game, x, y))
