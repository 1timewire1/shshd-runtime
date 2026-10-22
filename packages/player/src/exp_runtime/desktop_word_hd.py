"""The iOS HD word game's presentation (service 96), drawn at HD's density.

`SHSUIMinigameWord` draws in the whole 768 x 1024 frame: the scene background,
a spinning haze and four scrolling cloud edges, the two portraits in their
rings, the time/score bar, real 3D letter cubes (`draw3DCube`: a 450 x 450 x 100
box seen through a 30 degree tilt) and the question and keyword text. The game
logic (`word_grid.py`) is shared with the Android build; only the presentation
differs. See legacy/findings.md, "HD word game".

Atlas 512 holds the cube faces, arrows, clouds, haze and ring; 569-584 are the
bitmap fonts (sheet/metrics pairs); 564 is the portrait mask.

Numbers marked "decoded" come from the binary; "fitted" ones were matched to HD
photos (reference/screenshots/word game) because the decompile loses the argument.
"""
from functools import lru_cache
import math
import random

from . import graphics as pygame

from .graphics import faded
from .shs.grid_layout import clamp, ease
from .desktop_football_hd import HdStrings
from .hd_gl import GLAtlas, ImageFont, draw_quad, to_pil
from .menu import MenuStrings

FRAME = (768, 1024)
ATLAS, PORTRAIT_MASK = 512, 564
FONT_IDS = {'tile': (583, 584), 'status': (571, 572), 'big': (569, 570), 'body': (575, 576),
            'title': (579, 580)}
# 512's frames (37-42, the glint sweep, are not drawn: not verified).
RING, CLOUD_BOTTOM, CLOUD_LEFT, CLOUD_RIGHT, HAZE, CLOUD_TOP, PUFF = 0, 1, 2, 3, 4, 5, 6
BLUE_ARROW = 7
# Cube faces by mode: 0 blue, 1 orange (selected), 2 green (start), 4 red (wrong prefix).
TOP_FACE = {0: 17, 1: 45, 2: 43, 4: 35}
SIDE_FACE = {0: 18, 1: 46, 2: 44, 4: 36}
POPUP_BODY, POPUP_FOOT, POPUP_HEAD = 47, 48, 49

# `drawBackground` (decoded): the haze frame is centered on the screen and scaled
# 5.688 (2 x 2.844), spinning -20 degrees a second; the cloud strips scroll at
# 15 px/s.
BACKGROUND_ORIGIN = (-64, -220)      # fitted against four photos (the image is a touch squashed)
BACKGROUND_SCALE_Y = .9875
HAZE_SCALE, HAZE_SPIN = 2 * 2.844, -20.
CLOUD_SPEED = 15

# The cube: 450 wide, 100 deep, cells 522 apart; the camera (`setup3DTransform`,
# `frustum(-96, 96, -128, 128, 200, 5000)` over the 768 x 1024 frame) is a
# 30 degree tilt about the x axis, (0, -600) and the per-board depth below.
CUBE, GAP, DEPTH = 450, 72, 100
# `drawTileChar` scales the 85 px font to the 450 unit face (Android: 450 / 105); fitted.
LETTER_SCALE, LETTER_LIFT = 450 / 105, 0.
TILT = math.radians(30)
FOCAL = 800
BOARD_SLIDE = -600


def board_depth(width, height):
    """`initGridSize`'s depth table (identical to Android's)."""
    return -3800 if height == 5 else -3400 if (width, height) in ((5, 3), (4, 4), (5, 4)) else -3000


def project(width, height, x, y, z):
    """A board-space point (the cube grid's own 2D coordinates, y down, and z toward
    the viewer) to frame pixels."""
    board_w = width * CUBE + (width - 1) * GAP
    board_h = height * CUBE + (height - 1) * GAP
    px, py, pz = x - board_w / 2, 1024 - y + board_h / 2, z
    ty = py * math.cos(TILT) + pz * math.sin(TILT) + BOARD_SLIDE
    tz = -py * math.sin(TILT) + pz * math.cos(TILT) + board_depth(width, height)
    return 384 + FOCAL * px / -tz, 512 - FOCAL * ty / -tz


# `drawQuestionText`: the three heading lines' left edge and top (each slid in from
# the right by up to 352 px), and `drawKeyword`'s route: from the screen's right
# through the center to the bottom-left list.
HEADING_LINES = ((280, 120), (268, 160), (250, 200))
HEADING_SLIDE = 352
KEYWORD_FINAL_Y, KEYWORD_PITCH = 754, 50
KEYWORD_LEFT, KEYWORD_STEP, KEYWORD_SCALE = 30, 46, .65


def heading_lines(game, problem):
    """`drawQuestionText` (Android's schedule at HD's positions): (line, x, y, alpha)."""
    if game.phase in (-2, -1, 6):
        return ()
    alpha = max(0., game.phase_ms / 800 - .2) if game.phase == 4 else 1.
    result = []
    for index, (line, (x, y)) in enumerate(zip(problem.heading.split('\n')[:3], HEADING_LINES)):
        if game.phase in (0, 2):
            progress = 1 - game.phase_ms / (2800 if game.phase == 0 else 1800)
            limit, delay = (.4, .05) if game.phase == 0 else (.9, .1)
            x += int((1 - ease(progress + (2 - index) * delay, 0, limit, .85)) * HEADING_SLIDE)
        result.append((line, x, y, alpha))
    return tuple(result)


def keyword_pose(age, index, width, count, height):
    """`drawKeyword`: (center x, center y, scale) of keyword `index` at `age`
    (`progress - index * .05`), or None before it appears."""
    if age < .2:
        return None
    first = (1024 - count * height) / 2
    mid_y = first + index * height
    final_x = KEYWORD_LEFT + index * KEYWORD_STEP + width * KEYWORD_SCALE / 2
    final_y = KEYWORD_FINAL_Y + index * KEYWORD_PITCH
    if age <= .5:
        t = ease(age, .2, .5, .9)
        return 520 - 136 * t, 840 + (mid_y - 840) * t, max(.1, t)
    if age <= .74:
        return 384., mid_y, 1.
    if age <= .89:
        t = ease(age, .74, .89, .9)
        return 384 + (final_x - 384) * t, mid_y + (final_y - mid_y) * t, 1 - (1 - KEYWORD_SCALE) * t
    return final_x, final_y, KEYWORD_SCALE


SHARD_FRAME, SHARDS, EFFECT_SLOTS = 19, 8, 20
FLY_MS = 400
SCORE_EFFECT_TARGET = (520, 84)
COUNT_RATE = 800            # points a second while the score catches up
GRAVITY = 1600


class Shard:
    """`CubeExplosion`'s pieces: a tumbling sprite thrown from a found cube."""
    __slots__ = ('x', 'y', 'scale', 'vx', 'vy', 'spin', 'angle', 'age')

    def __init__(self, x, y, scale, vx, vy, spin, angle, age):
        self.x, self.y, self.scale, self.vx, self.vy = x, y, scale, vx, vy
        self.spin, self.angle, self.age = spin, angle, age


class EffectState:
    """Cosmetic follow-up of a found word, kept beside (never inside) the game state."""
    def __init__(self, game):
        self.game, self.last = game, game.visual_ms
        self.serial = getattr(game, 'found_serial', 0)
        self.rng = random.Random(0x5EED)
        self.reset(game)

    def reset(self, game):
        self.score, self.shown, self.pending, self.inflight = game.score, game.score, 0, 0
        self.flying, self.shards = [], []

    def tick(self, dt):
        seconds = dt / 1000
        for effect in self.flying[:]:
            effect[2] += dt
            if effect[2] >= FLY_MS:
                self.flying.remove(effect)
                self.inflight -= effect[0]
                self.pending += effect[0]
        if self.pending > 0:
            step = min(self.pending, int(seconds * COUNT_RATE))
            self.pending -= step
            self.shown += step
        # The digits never run ahead of the real score, nor behind what is still to arrive.
        self.shown = min(self.shown, self.score - self.pending - self.inflight)
        for shard in self.shards[:]:
            shard.age += dt
            shard.x += shard.vx * seconds
            shard.y += shard.vy * seconds
            shard.angle += shard.spin * seconds
            if shard.y < 1024:
                shard.vy += GRAVITY * seconds
            else:
                self.shards.remove(shard)


class HdWordRenderer:
    def __init__(self, resources, art):
        self.resources, self.art = resources, art
        self.canvas = pygame.Surface(FRAME).convert()
        self.edge_bar = 'gear'
        self.hd_layer = True
        self._effects = None

    # -- assets ---------------------------------------------------------
    def raw(self, resource_id):
        try:
            return self.resources.library.hd_raw_resource(resource_id)
        except AttributeError:
            return None

    @lru_cache(maxsize=None)
    def atlas(self, resource_id):
        return GLAtlas(self.raw(resource_id))

    @lru_cache(maxsize=None)
    def font(self, name):
        sheet, metrics = FONT_IDS[name]
        return ImageFont.load(self.raw(sheet), self.raw(metrics))

    @lru_cache(maxsize=1)
    def strings(self):
        """Android string ids (what the game carries) read as HD's own wording, matched by text."""
        library = self.resources.library
        android = MenuStrings.parse(library.read_asset(13))
        hd = MenuStrings.parse(library.hd_raw_resource(15))
        return HdStrings(android, [hd[i] for i in range(273)])

    def available(self):
        try:
            return all(self.raw(i) is not None for i in (ATLAS, PORTRAIT_MASK, 15, 569, 570, 571, 572,
                                                         575, 576, 579, 580, 583, 584))
        except (AttributeError, KeyError):
            return False

    @lru_cache(maxsize=128)
    def letter(self, char):
        """The tile font's glyph as an RGBA image, with its cell size."""
        font = self.font('tile')
        glyph = font.font.glyph(char)
        if glyph is None:
            return None
        gx, gy, gw = glyph
        piece = font.sheet.subsurface((gx, gy, gw, font.height)).copy()
        return to_pil(piece), gw, font.height

    @lru_cache(maxsize=64)
    def face(self, frame):
        return to_pil(self.atlas(ATLAS).frame(frame))

    # -- text -----------------------------------------------------------
    def text(self, name, text, x, y, *, alpha=1., monospace=None, right=False, center=False):
        font = self.font(name)
        width = font.width(text, monospace)
        if right:
            x -= width
        elif center:
            x -= width / 2
        font.draw_line(self.canvas, text, x, y, alpha, monospace)

    # -- backdrop -------------------------------------------------------
    @lru_cache(maxsize=4)
    def background(self, background_id):
        image = self.art.image(background_id)
        if image is not None and BACKGROUND_SCALE_Y != 1:
            image = pygame.transform.smoothscale(image, (image.get_width(),
                                                         round(image.get_height() * BACKGROUND_SCALE_Y)))
        return image

    def backdrop(self, game, background_id):
        canvas = self.canvas
        canvas.fill((0, 0, 0))
        image = self.background(background_id)
        if image is not None:
            canvas.blit(image, BACKGROUND_ORIGIN)
        atlas = self.atlas(ATLAS)
        # The haze is soft, so it is turned at half size and enlarged (a 1456 px turn every frame is slow).
        half = pygame.Surface((384, 512), pygame.SRCALPHA).convert_alpha()
        atlas.draw(half, HAZE, 192 - 128, 256 - 128, sx=HAZE_SCALE / 2, angle=HAZE_SPIN * game.visual_ms / 1000,
                   pivot=(128, 128))
        canvas.blit(pygame.transform.smoothscale(half, FRAME), (0, 0))
        if game.phase == -2:
            return
        entry = game.phase_ms / 1500 if game.phase == -1 else 0.
        travel = int(game.visual_ms / 1000 * CLOUD_SPEED)
        x = travel % 280 - 280
        while x < 1048:
            atlas.draw(canvas, CLOUD_BOTTOM, x, int(entry * 51 + 973))
            x += 280
        x = -(travel % 256)
        while x < 1024:
            atlas.draw(canvas, CLOUD_TOP, x, int(entry * -51))
            x += 256
        y = travel % 289 - 289
        while y < 1024:
            atlas.draw(canvas, CLOUD_LEFT, int(entry * -41), y)
            y += 289
        y = -(travel % 289)
        while y < 1024:
            atlas.draw(canvas, CLOUD_RIGHT, int(entry * 47 + 721), y)
            y += 289

    # -- HUD ------------------------------------------------------------
    def status(self, game, shown):
        """`drawStatusBar`: each label and number is right-aligned to its column; during the
        introduction they grow in (from their right edge, as Android's do)."""
        if game.phase in (-2, -1):
            return
        scale = clamp((2800 - game.phase_ms) / 500) if game.phase == 0 else 1.
        if scale <= 0:
            return
        strings = self.strings()
        seconds = math.ceil(game.remaining_ms / 1000)
        for text, edge, y, mono in ((strings[32], 412, 4, None), (f'{seconds:03}', 412, 44, '3'),
                                    (strings[33], 620, 4, None), (f'{shown:05}', 620, 44, '3')):
            font = self.font('status')
            width = font.width(text, mono)
            if scale == 1:
                self.text('status', text, edge, y, right=True, monospace=mono)
                continue
            layer = pygame.Surface((width + 4, font.height + 4), pygame.SRCALPHA).convert_alpha()
            font.draw_line(layer, text, 2, 2, monospace=mono)
            layer = pygame.transform.smoothscale(layer, (max(1, round(layer.get_width() * scale)),
                                                        max(1, round(layer.get_height() * scale))))
            layer = faded(layer, round(255 * scale))
            self.canvas.blit(layer, (round(edge - width * scale - 2 * scale), y))

    # -- question and keywords --------------------------------------------
    def scaled_text(self, name, text, cx, cy, scale, alpha):
        """`drawKeywordFont`: the text centered on (cx, cy) at `scale`."""
        font = self.font(name)
        width, height = max(1, font.width(text)), font.height
        layer = pygame.Surface((width + 4, height + 4), pygame.SRCALPHA).convert_alpha()
        font.draw_line(layer, text, 2, 2)
        if scale != 1:
            layer = pygame.transform.smoothscale(layer, (max(1, round(layer.get_width() * scale)),
                                                        max(1, round(layer.get_height() * scale))))
        if alpha < 1:
            layer = faded(layer, round(255 * clamp(alpha)))
        self.canvas.blit(layer, layer.get_rect(center=(round(cx), round(cy))))

    def prompts(self, game):
        # HD has already loaded the next round's question and keywords while the old board
        # turns over (the photos show the new text fading out), unlike Android.
        p = game.problem
        for line, x, y, alpha in heading_lines(game, p):
            self.text('status', line, x, y, alpha=alpha)
        if game.phase in (-2, -1, 6):
            return
        lines = p.prompt.split('\n')[:3] if p.prompt else ()
        alpha = max(0., game.phase_ms / 800 - .2) if game.phase == 4 else 1.
        progress = 1 - game.phase_ms / (2800 if game.phase == 0 else 1800) if game.phase in (0, 2) else 1.
        font = self.font('big')
        for index, line in enumerate(lines):
            age = progress - index * .05 if game.phase in (0, 2) else progress
            pose = keyword_pose(age, index, font.width(line), len(lines), font.height)
            if pose is not None:
                self.scaled_text('big', line, *pose, alpha)

    # -- score effects and shards ---------------------------------------
    def effects(self, game):
        """The renderer's own clock for what a found word sets off (`scoreValidWordSelection`,
        `generateExplosionEffectForSelected`): the '+N' that flies to the score, the digits
        counting up behind it, and the cubes' shards."""
        state = self._effects
        if state is None or state.game is not game or game.visual_ms < state.last:
            state = self._effects = EffectState(game)
        dt = min(250, game.visual_ms - state.last)
        state.last = game.visual_ms
        serial = getattr(game, 'found_serial', 0)
        if serial != state.serial:
            if serial > state.serial:
                self.found(state, game)
            state.serial = serial
        elif game.score < state.score:
            state.reset(game)
        state.score = game.score
        state.tick(dt)
        return state

    def found(self, state, game):
        p = game.problem
        cells = [self.cell_center(p, i) for i in getattr(game, 'found_cells', ())]
        if not cells:
            return
        state.flying.append([game.last_delta, cells[-1], 0.])
        state.inflight += game.last_delta
        for x, y in cells[-EFFECT_SLOTS:]:
            scale = 1 + (y - 300) * .00110497
            for _ in range(SHARDS):
                state.shards.append(Shard(x + state.rng.randrange(50), y + state.rng.randrange(50), scale,
                                          state.rng.randrange(250), state.rng.randrange(350) - 250,
                                          state.rng.randrange(360), state.rng.randrange(360),
                                          state.rng.randrange(5000)))

    @staticmethod
    def cell_center(p, index):
        col, row = index % p.width, index // p.width
        return project(p.width, p.height, col * (CUBE + GAP) + CUBE / 2, row * (CUBE + GAP) + CUBE / 2, -DEPTH / 2)

    def draw_effects(self, state):
        atlas = self.atlas(ATLAS)
        for shard in state.shards:
            frame = SHARD_FRAME + int(shard.age / 1000 * 12) % 16
            atlas.draw(self.canvas, frame, round(shard.x), round(shard.y), sx=shard.scale, angle=shard.angle,
                       pivot=(26, 21))
        for value, (x, y), age in state.flying:
            f = ease(age / FLY_MS)
            self.text('status', f'+{value}', x + (SCORE_EFFECT_TARGET[0] - x) * f,
                      y + (SCORE_EFFECT_TARGET[1] - y) * f)
        if state.pending > 0:
            self.text('status', f'+{state.pending}', 620, SCORE_EFFECT_TARGET[1], right=True)

    # -- notifications ----------------------------------------------------
    def banner(self, game):
        """`drawNotificationEffects`: the message grows in at the screen's center and fades out
        over the last 40% of its hold (wrapped and centered as one block)."""
        banner = game.banner
        if banner is None:
            return
        strings = self.strings()
        text = {'ready': lambda: strings[80], 'target': lambda: strings[59] % game.target,
                'success': lambda: game.success_text, 'failure': lambda: game.failure_text,
                'time_up': lambda: strings[57],
                'result': lambda: strings[81] % (game.score, game.target)}[banner.kind]()
        age = banner.age_ms
        scale = clamp(age / banner.enter_ms)
        alpha = scale if age < banner.enter_ms else clamp(1 - ((age - banner.enter_ms) / banner.hold_ms - .6) / .6)
        lines = text.split('\n')
        font = self.font('big')
        top = 512 - len(lines) * font.height * scale / 2
        for index, line in enumerate(lines):
            self.scaled_text('big', line, 384, top + (index + .5) * font.height * scale, scale, alpha)

    # -- tutorial popup ---------------------------------------------------
    POPUP_WIDTH, POPUP_TEXT_WIDTH = 612, 572

    @lru_cache(maxsize=16)
    def popup(self, title, text):
        """`drawTutorialPopup` at scale 1: the 46 px head with its title tab, the stretched
        body (text 20 px in) and the 30 px foot, as one surface; returns (surface, text height)."""
        atlas, body = self.atlas(ATLAS), self.font('body')
        lines = body.wrap(text, self.POPUP_TEXT_WIDTH) if text else ()
        text_height = body.text_height(lines)
        inner = text_height + 40
        surface = pygame.Surface((self.POPUP_WIDTH, inner + 76), pygame.SRCALPHA).convert_alpha()
        surface.blit(atlas.frame(POPUP_BODY) if False else pygame.transform.scale(
            atlas.frame(POPUP_BODY), (self.POPUP_WIDTH, inner)), (0, 45))
        surface.blit(atlas.frame(POPUP_HEAD), (0, 0))
        surface.blit(atlas.frame(POPUP_FOOT), (0, 45 + inner))
        y = 65
        for line in lines:
            body.draw_line(surface, line, 20, y)
            y += body.height + body.font.line_gap
        title_font = self.font('title')
        title_font.draw_line(surface, title, 216 - title_font.width(title) / 2, 2)
        return surface, text_height

    def tutorial(self, game):
        p = game.problem
        if game.phase == 4 and not game.feedback and game.transition and game.transition.tutorial:
            p = game.transition.problem
            scale = clamp(1 - (800 - game.phase_ms) / 500)
        else:
            if not game.tutorial or game.phase in (-2, -1, 4, 6):
                return
            scale = (clamp((game.phase_ms - 600) / 500) if game.phase == 3
                     else clamp(1 - game.tutorial_entry_ms / 500))
        if not p.tutorial_text or scale <= 0:
            return
        surface, text_height = self.popup(p.tutorial_title, p.tutorial_text)
        inner = text_height + 40
        center = ((inner / 2 + 60) if p.tutorial_position == 0 else
                  1024 - (inner / 2 + 60) if p.tutorial_position == 2 else 512)
        total = surface.get_height() * scale
        left, top = 384 - self.POPUP_WIDTH * scale / 2, center - total / 2
        if scale != 1:
            surface = pygame.transform.smoothscale(surface, (max(1, round(surface.get_width() * scale)),
                                                             max(1, round(surface.get_height() * scale))))
            surface = faded(surface, round(255 * scale))
        self.canvas.blit(surface, (round(left), round(top)))

    # -- portraits ------------------------------------------------------
    @lru_cache(maxsize=1)
    def mask(self):
        return self.atlas(PORTRAIT_MASK).frame(0)

    @lru_cache(maxsize=8)
    def portrait_image(self, asset_id):
        """The portrait at its size in iPad points: twice its logical size (DialogueRenderer.portrait_source), so a
        standard episode's 1x art fills the same space HD's own 2x art does, as in the dialogue."""
        source = self.art.portrait_source(asset_id)
        if source is None:
            return None
        image, (width, height) = source
        size = max(1, round(width * 2)), max(1, round(height * 2))
        return image if image.get_size() == size else pygame.transform.smoothscale(image, size)

    def masked_portrait(self, image, mirrored):
        """The portrait cut by the 266 x 300 mask (`drawPortrait`'s masked draw)."""
        mask = self.mask()
        surface = pygame.Surface(mask.get_size(), pygame.SRCALPHA).convert_alpha()
        if mirrored:
            image = pygame.transform.flip(image, True, False)
        surface.blit(image, (133 - image.get_width() // 2, 308 - image.get_height()))
        surface.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        return surface

    def portraits(self, session, game):
        """`drawPortrait` and `drawPortraitRings`. Introduction: the art grows in (Android's
        curve) while three rings ripple out, each 0.15 of the intro behind the last."""
        if game.phase in (-2, -1):
            return
        details, engine = session.pending.details, session.engine
        atlas = self.atlas(ATLAS)
        t = game.visual_ms / 1000
        intro = game.phase == 0
        progress = 1 - game.phase_ms / 2800 if intro else 1.
        grow = ease(progress, .2, .52, .9) if intro else 1.
        fade = ease(progress, .2, .52) if intro else 1.
        for side in ('left', 'right'):
            char = details[side + '_character']
            variants = engine.character_art_variants.get(char, ())
            if not variants:
                continue
            asset_id = variants[max(0, details[side + '_expression']) % len(variants)]
            image = self.portrait_image(asset_id)
            if image is None:
                continue
            w, h = image.get_size()
            left = side == 'left'
            cx, cy = (20 + w // 2, 20 + h // 2) if left else (748 - w // 2, 1004 - h // 2)
            angle = -40 * t
            atlas.draw(self.canvas, PUFF, cx - 128, cy - 113, alpha=fade, sx=1.23, angle=angle, pivot=(128, 113))
            if intro:
                for ring in range(3):
                    age = progress - ring * .15
                    if age <= 0:
                        continue
                    if age < .7:
                        size = ease(age, 0, .7) * 1.3
                    else:
                        size = 1 + .3 * (1 - ease(age, .7, 1.))
                    atlas.draw(self.canvas, RING, cx - 124, cy - 128, sx=size * 1.17, angle=angle, pivot=(124, 128))
            else:
                pulse = abs(math.sin(game.visual_ms / 1000 * .8 * math.pi))
                size = 1.17 * (1 - (.15 - pulse)) if pulse < .15 else 1.17
                atlas.draw(self.canvas, RING, cx - 124, cy - 128, sx=size, angle=angle, pivot=(124, 128))
            if grow <= 0:
                continue
            mirrored = not left and engine.numbers.get(engine.number_key(char, 651), 0) != 3
            piece = self.masked_portrait(image, mirrored)
            if grow != 1:
                piece = pygame.transform.smoothscale(piece, (max(1, round(piece.get_width() * grow)),
                                                              max(1, round(piece.get_height() * grow))))
            if fade < 1:
                piece = faded(piece, round(255 * fade))
            self.canvas.blit(piece, piece.get_rect(center=(cx, cy - 8)))

    # -- board ----------------------------------------------------------
    @lru_cache(maxsize=64)
    def icon(self, asset_id):
        """A picture tile's art (`drawTileIcon`: scaled to 382.5 board units tall), as a PIL image
        with its width in board units."""
        image = self.art.image(asset_id)
        if image is None:
            return None
        return to_pil(image), image.get_width() * 382.5 / image.get_height()

    def glyph_quad(self, char, vertex, depth, mirrored, symbols):
        """The letter (or picture) on a face: `vertex(x, y, z)` maps face units to the screen."""
        picture = self.icon(symbols[ord(char)]) if ord(char) in symbols else None
        if picture is not None:
            image, w = picture
            h = 382.5
        else:
            letter = self.letter(char)
            if letter is None:
                return None
            image, gw, gh = letter
            w, h = gw * LETTER_SCALE, gh * LETTER_SCALE
        left, up = -w / 2, -h / 2 + (0 if picture else LETTER_LIFT)
        xs = (left + w, left) if mirrored else (left, left + w)
        return image, [vertex(xs[0], up, depth), vertex(xs[1], up, depth),
                       vertex(xs[1], up + h, depth), vertex(xs[0], up + h, depth)]

    def cube(self, width, height, col, row, mode, front='', back='', *, alpha=1., size=1., angle=0.,
             symbols=None):
        """`draw3DCube`: a 450 x 450 x 100 box whose two big faces carry the tile art (and the
        letters), turned `angle` degrees about its vertical axis and scaled about its center.
        Drawn once per pose (cached), then blitted."""
        symbols = symbols or {}
        pictures = tuple(symbols.get(ord(c)) if c else None for c in (front, back))
        image, left, top = self.cube_image(width, height, col, row, mode, front, back, round(alpha * 50),
                                           round(size * 200), round(angle * 2), pictures)
        if image is not None:
            self.canvas.blit(image, (left, top))

    @lru_cache(maxsize=512)
    def cube_image(self, width, height, col, row, mode, front, back, alpha50, size200, angle2, pictures):
        alpha, size, angle = alpha50 / 50, size200 / 200, angle2 / 2
        symbols = {ord(c): asset for c, asset in zip((front, back), pictures) if c and asset is not None}
        cx, cy = col * (CUBE + GAP) + CUBE / 2, row * (CUBE + GAP) + CUBE / 2
        half, depth = CUBE / 2, DEPTH / 2
        sin, cos = -math.sin(math.radians(angle)), math.cos(math.radians(angle))

        def vertex(vx, vy, vz):
            vx, vy, vz = vx * size, vy * size, vz * size
            return project(width, height, cx + vx * cos + vz * sin, cy + vy, -depth - vx * sin + vz * cos)

        tile, side = self.face(TOP_FACE[mode]), self.face(SIDE_FACE[mode])
        faces = (
            (side, [(-half, -half, depth), (-half, -half, -depth), (-half, half, -depth), (-half, half, depth)], None),
            (side, [(half, -half, -depth), (half, -half, depth), (half, half, depth), (half, half, -depth)], None),
            (side, [(-half, half, depth), (half, half, depth), (half, half, -depth), (-half, half, -depth)], None),
            (side, [(-half, -half, -depth), (half, -half, -depth), (half, -half, depth), (-half, -half, depth)], None),
            (tile, [(half, -half, -depth), (-half, -half, -depth), (-half, half, -depth), (half, half, -depth)],
             (back, True)),
            (tile, [(-half, -half, depth), (half, -half, depth), (half, half, depth), (-half, half, depth)],
             (front, False)),
        )
        operations = []
        for image, corners, letter in faces:
            quad = [vertex(*c) for c in corners]
            if not self.facing(quad):
                continue
            operations.append((image, quad, alpha))
            if letter and letter[0]:
                # A back face's letter runs the other way so it reads when the cube is turned round.
                found = self.glyph_quad(letter[0], vertex, corners[0][2], letter[1], symbols)
                if found:
                    operations.append((found[0], found[1], 1.))
        if not operations:
            return None, 0, 0
        xs = [x for _, quad, _ in operations for x, _ in quad]
        ys = [y for _, quad, _ in operations for _, y in quad]
        left, top = math.floor(min(xs)), math.floor(min(ys))
        surface = pygame.Surface((math.ceil(max(xs)) - left + 1, math.ceil(max(ys)) - top + 1),
                                 pygame.SRCALPHA).convert_alpha()
        for image, quad, opacity in operations:
            draw_quad(surface, image, [(x - left, y - top) for x, y in quad], opacity)
        return surface, left, top

    @staticmethod
    def facing(quad):
        """Screen-space winding: front faces run clockwise (y down)."""
        area = sum(quad[i][0] * quad[(i + 1) % 4][1] - quad[(i + 1) % 4][0] * quad[i][1] for i in range(4))
        return area > 0

    def hint_offsets(self, game):
        """`setTimeOffsetsForHighlighted`: each starting cell gets a share of 3000 ms, dealt out in
        shuffled order (cosmetic here, so a private shuffle keyed by the round)."""
        starts = sorted(game.starts)
        shares = [round(k * 3000 / len(starts)) for k in range(len(starts))] if starts else []
        order = list(range(len(starts)))
        state = (game.round * 2654435761 + len(starts)) & 0xffffffff
        for i in range(len(order)):
            state = (state * 1664525 + 1013904223) & 0xffffffff
            j = state % len(order)
            order[i], order[j] = order[j], order[i]
        return {cell: shares[order[k]] for k, cell in enumerate(starts)}

    def board(self, game):
        p, board, starts = game.problem, game.board, game.starts
        transition = game.transition
        outgoing = transition and transition.mode == 'shrink' and game.phase == 4
        if outgoing:
            p, board, starts = transition.problem, transition.board, transition.starts
        hidden = (transition.tutorial and transition.problem.hide_board
                  if transition and game.phase == 4 else game.tutorial and p.hide_board)
        if game.phase in (-2, -1) or hidden:
            return
        offsets = self.hint_offsets(game) if p.highlight and not outgoing else {}
        for row in range(p.height):
            for col in range(p.width):
                i = row * p.width + col
                delay = (p.height - 1 + col - row) * 80
                size, angle, front, back = 1., 0., board[i], ''
                if outgoing:
                    size = ease(1 - clamp((800 - game.phase_ms - delay) / 600), bounce=.8)
                elif transition and transition.mode == 'flip' and game.phase in (4, 2):
                    age = 800 - game.phase_ms if game.phase == 4 else 2600 - game.phase_ms
                    angle = (1 - clamp((age - max(1, delay)) / 700)) * 180
                    back = transition.board[i]
                elif game.phase in (2, 6) and (not transition or transition.mode == 'shrink'):
                    size = ease(clamp((game.board_entry_ms - delay) / 600), bounce=.8)
                elif game.phase == 0:
                    size = clamp((2800 - game.phase_ms) / 1400)
                if size <= 0:
                    continue
                mode, alpha = 0, 1.
                if not outgoing and i in game.bad_prefix:
                    mode = 4
                elif not outgoing and i in game.selection:
                    mode, alpha = 1, .7
                elif i in offsets:
                    mode = 2
                    alpha = max(.1, clamp((game.round_ms - offsets[i]) / 3500))
                if mode and alpha < 1:
                    self.cube(p.width, p.height, col, row, 0, size=size, angle=angle)
                self.cube(p.width, p.height, col, row, mode, front, back, alpha=alpha, size=size, angle=angle,
                          symbols=game.symbols)
        if outgoing or game.phase == 4:
            return
        self.arrows(game, p)

    # -- arrows ---------------------------------------------------------
    DIRECTIONS = ((1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1))
    ORANGE_FRAMES = (8, 14, 15, 9, 10, 11, 12, 13)

    def arrow(self, p, hint, col, row, direction):
        """`draw3DArrow`: the arrow art on a quad centered between two cells, 50 units above
        the board (a hint's blue arrow is turned to point the way; the orange trace has art for
        each direction, two of them mirrored)."""
        atlas = self.atlas(ATLAS)
        frame = BLUE_ARROW if hint else self.ORANGE_FRAMES[direction]
        fw, fh = atlas.size(frame)
        w, h = fw * 3, (fh - (0 if hint else 8)) * 3
        dx, dy = self.DIRECTIONS[direction]
        cx = col * (CUBE + GAP) + CUBE / 2 + dx * (CUBE + GAP) / 2
        cy = row * (CUBE + GAP) + CUBE / 2 + dy * (CUBE + GAP) / 2
        angle = math.radians(direction * -45 + 360) if hint else 0.
        sin, cos = math.sin(angle), math.cos(angle)
        corners = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
        if not hint and direction in (1, 7):
            corners = [(-x, y) for x, y in corners]
        quad = [project(p.width, p.height, cx + x * cos - y * sin, cy + x * sin + y * cos, 50) for x, y in corners]
        draw_quad(self.canvas, self.face(frame), quad)

    def arrows(self, game, p):
        if p.show_hints:
            trace = tuple(zip(game.selection, game.selection[1:]))
            for start in game.starts:
                path = next((path for word in p.words if (path := game.find_path(start, word))), None) or ()
                for a, b in zip(path, path[1:]):
                    if (a, b) not in trace:
                        self.arrow(p, True, a % p.width, a // p.width, self.direction(p, a, b))
        for a, b in zip(game.selection, game.selection[1:]):
            self.arrow(p, False, a % p.width, a // p.width, self.direction(p, a, b))

    def direction(self, p, a, b):
        return self.DIRECTIONS.index((b % p.width - a % p.width, b // p.width - a // p.width))

    # -- input ----------------------------------------------------------
    def hit(self, position, game):
        """`calcTouchRects`: each cell's rectangle is the bounds of its projected top face; once a
        drag has begun only the middle 65% of it counts."""
        p = game.problem
        for col in range(p.width):
            for row in range(p.height):
                x, y = col * (CUBE + GAP), row * (CUBE + GAP)
                points = [project(p.width, p.height, x + dx, y + dy, 0) for dx, dy in
                          ((0, 0), (CUBE, 0), (CUBE, CUBE), (0, CUBE))]
                rect = pygame.FRect(min(q[0] for q in points), min(q[1] for q in points),
                                    max(q[0] for q in points) - min(q[0] for q in points),
                                    max(q[1] for q in points) - min(q[1] for q in points))
                if game.selection:
                    rect.inflate_ip(-rect.width * .35, -rect.height * .35)
                if rect.collidepoint(position):
                    return row * p.width + col
        return None

    # -- frame ----------------------------------------------------------
    def draw(self, target, session):
        game = session.engine.word_grid
        fx = self.effects(game)
        self.backdrop(game, session.pending.details['background_id'])
        self.portraits(session, game)
        self.status(game, fx.shown)
        self.board(game)
        self.prompts(game)
        self.draw_effects(fx)
        self.banner(game)
        self.tutorial(game)
        return [(pygame.Rect(-32, 422, 92, 58), ('menu',))]
