"""The iOS HD football minigame's presentation (service 94), drawn at HD's density.

HD re-implemented the minigame's art on GL sprite atlases and bitmap image
fonts and lays it out in the whole 768 x 1024 frame (not the 320-unit column),
so this renderer draws an entire frame-sized layer. The game logic that drives
it (`football.py`: phases, timers, plays, scoring) is shared with the Android
build; only presentation differs. See legacy/findings.md, "HD football".

Atlases (HD resource ids; `SHSUIMinigameFootball::init`, `loadFonts`):
333 the HUD, plays, digits and plaques; 471 the field lines, countdown and
banner letters; 509 the 512-px turf tile; 569/570, 573/574, 575/576, 577/578,
581/582, 585/586, 587/588 the bitmap fonts (sheet/metrics); 2070/2075 the coach.

Everything is in frame pixels. Numbers marked "decoded" come straight from the
binary's draw functions (`drawGrassAndLines`, `drawHUD`, `ItemSlot::drawItem`,
...); those marked "fitted" were matched against HD photos (reference/
screenshots/football) because the decompile loses the argument.
"""
from functools import lru_cache
import math
import random

from . import graphics as pygame

from .graphics import faded
from .shs.football import SELECTED_FRAMES, PLAY_FRAMES as ANDROID_PLAY_FRAMES
from .shs.football_layout import feedback_text, footer_id, heading_id, help_motion, legend_codes, team_name
from .hd_gl import GLAtlas, ImageFont

FRAME = (768, 1024)
MAIN, FIELD_ATLAS, TURF = 333, 471, 509
FONT_IDS = {'big': (569, 570), 'digits': (573, 574), 'white': (575, 576), 'cyan': (577, 578),
            'red': (581, 582), 'team': (585, 586), 'footer': (587, 588)}
COACH_IDS = {0: 2070, 1: 2075}
# 471.
HAZE = 22
LINE_TABLE = (-27, -9, -13, -17, -21, -23, -20, -16, -12, -8, -28)   # C_141
FIVE_YARD_LINE = -24
COUNTDOWN_FRAMES = {1: 0, 2: 1, 3: 2}
GO = -2
# 333.
HUD_STRIP = -2          # the English strip; -1..-5 are the per-language variants
PLAQUE = {False: 134, True: 135}
SCORE_STRIP = ((183, -47, 103), (227, -46, 125), (10**9, -45, 147))
DOWN_FRAMES = (0, 5, 10, 15, 15)
SCORE_DIGITS = 110      # 110..119
TIME_DIGITS = 122       # 122..131, ':' 132
PANEL, NOTIFY_BAND, BAR = -6, -7, -68
SHINE = 68
TURNOVER_LABEL = -8     # -8..-12 by language
YARDS_RED, YARDS_BLUE = (73, 83, 84), (89, 99, 100)   # digits, sign, suffix (English)
# `g_arrIconTypeMapping`: play code -> composite.
PLAY_COMPOSITE = {-2: -64, -1: -58, -3: -48, -4: -66, -5: -52, -6: -49,
                  1: -54, 2: -60, 3: -48, 4: -66, 5: -52, 6: -61, 7: -55}
# `HitEffect::initHit`: a selected play's flash silhouette.
SELECTED = {-66: -67, -64: -65, -61: -62, -60: -63, -58: -59, -55: -56, -54: -57,
            -52: -53, -49: -51, -48: -50}
# The nine slots (`setupGame`): x = table + 64, y = table.
SLOTS = tuple((x + 64, y) for y in (440, 600, 760) for x in (120, 320, 520))
DIGIT_ADVANCE = (28, 25, 26, 28, 28, 26, 28, 26, 28, 28)   # C_278
RING_RED, RING_YELLOW, RING_CYAN = 108, 109, 107


def wrap_positive(value, span):
    """`value` wrapped into (-span, 0]."""
    value %= span
    return value - span if value else 0


class HdStrings:
    def __init__(self, android, hd):
        self.android, self.hd, self.cache = android, hd, {}

    def __getitem__(self, index):
        if index not in self.cache:
            text = self.android[index]
            if text not in self.hd:
                import difflib
                match = difflib.get_close_matches(text, self.hd, 1, .85)
                text = match[0] if match else text
            self.cache[index] = text
        return self.cache[index]


class HdFootballRenderer:
    def __init__(self, resources):
        self.resources = resources
        self.canvas = pygame.Surface(FRAME).convert()
        self.edge_bar = 'gear'
        self.hd_layer = True
        self.cosmetic = random.Random(0)
        self.stars = []
        self.star_key = self.star_start = None

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

    @lru_cache(maxsize=2)
    def coach(self, variant):
        from io import BytesIO
        from PIL import Image
        from .cgbi import decode
        image = decode(self.raw(COACH_IDS[variant])).convert('RGBA')
        coach = pygame.image.frombytes(image.tobytes(), image.size, 'RGBA').convert_alpha()
        # `drawPortrait` mirrors the coach (fitted: IMG_0093/0212 face the other way).
        return pygame.transform.flip(coach, True, False)

    @lru_cache(maxsize=1)
    def strings(self):
        """Android string ids (what the game state carries) read as HD's own text.

        HD's string bank is renumbered and slightly reworded; the football ids
        are matched by text (exact, else the closest wording).
        """
        from .menu import MenuStrings
        library = self.resources.library
        android = MenuStrings.parse(library.read_asset(13))
        hd = MenuStrings.parse(library.hd_raw_resource(15))
        return HdStrings(android, [hd[i] for i in range(273)])

    def available(self):
        try:
            return all(self.raw(i) is not None for i in (MAIN, FIELD_ATLAS, TURF, 15, 569, 570, 575, 576, 585, 586, 587, 588))
        except (AttributeError, KeyError):
            return False

    # -- text -----------------------------------------------------------
    def text(self, name, text, x, y, *, center=False, alpha=1.):
        """One line of the bitmap font `name`; `x` is its left edge or its center."""
        font = self.font(name)
        if center:
            x -= font.width(text) / 2
        font.draw_line(self.canvas, text, x, y, alpha)

    def paragraph(self, text, x, y, width, *, alpha=1.):
        """A paragraph in the white font; ` and ; switch to the cyan and red fonts."""
        base = self.font('white')
        marks = {'`': 'cyan', ';': 'red'}
        plain = ''.join(c for c in text if c not in marks)
        fonts, mode = [], None
        for c in text:
            if c in marks:
                mode = None if mode == c else c
            else:
                fonts.append(marks.get(mode, 'white'))
        index = 0
        for line in base.wrap(plain, width):
            # Leading spaces are dropped by the wrap; keep the marks aligned.
            while index < len(plain) and plain[index] == ' ' and not plain.startswith(line, index):
                index += 1
            pen = x
            for offset, c in enumerate(line):
                font = self.font(fonts[index + offset])
                font.draw_line(self.canvas, c, pen, y, alpha)
                pen += font.font.char_width(c) + font.font.tracking
            index += len(line)
            y += base.height + base.font.line_gap
        return y

    # -- field ----------------------------------------------------------
    def field(self, game):
        """`drawGrassAndLines` / `drawField`: turf tiles sheared by the camera, the yard
        lines and the moving haze."""
        turf = self.atlas(TURF).frame(0)
        field = self.atlas(FIELD_ATLAS)
        position = game.camera_position
        y0 = wrap_positive(position * -90, 1024)
        x0 = (y0 * -0.40613848) % 768
        for i in range(4):
            for j in range(4):
                self.canvas.blit(turf, (j * 512 - 1024 + x0, i * 512 + y0))
        start = int(position) - 6
        for yard in range(start, start + 15):
            if yard % 5 or not 0 <= yard <= 100:
                continue
            y = (yard - position) * 90 + 512
            ref = LINE_TABLE[yard // 10] if yard % 10 == 0 else FIVE_YARD_LINE
            field.draw(self.canvas, ref, int(y * -0.4354067 + 140), int(y - 56), origin=True)
        haze = self.haze()
        ms = game.visual_ms
        hx = int(math.fmod(int(ms * -0.02), 640))   # C's remainder keeps the sign
        hy = int(ms * 0.05) % 960
        for column in range(3):
            for row in range(2):
                self.canvas.blit(haze, (hx + column * 640, hy - row * 960))

    @lru_cache(maxsize=1)
    def haze(self):
        """The green-cloud frame at 4x and alpha 0.25 (`renderCutupEx` 4, 4, 0.25)."""
        tile = self.atlas(FIELD_ATLAS).frame(HAZE)
        haze = pygame.transform.smoothscale(tile, (tile.get_width() * 4, tile.get_height() * 4))
        haze = faded(haze, 64)
        return haze

    # -- HUD ------------------------------------------------------------
    def hud(self, game):
        main = self.atlas(MAIN)
        strings = self.strings()
        main.draw(self.canvas, HUD_STRIP, 20, 26)
        main.draw(self.canvas, PLAQUE[game.defense], 38, 7)
        self.text('white', strings[heading_id(game)], 220, 11, center=True)
        main.draw(self.canvas, DOWN_FRAMES[min(game.down, 4)], 176, 56)
        distance = int(100 - game.hud_position if game.defense else game.hud_position)
        distance = max(0, min(100, distance))
        self.number(str(distance), 372, 75, 40, SCORE_DIGITS, 2, center=True)
        seconds = max(0, math.ceil(game.remaining_ms / 1000))
        self.number(f'{seconds // 60}:{seconds % 60:02}', 306, 74, 0, TIME_DIGITS, 2)
        team = self.font('team')
        names = (team_name(strings, game.teams[0]), team_name(strings, game.teams[1]))
        width = team.width(names[0]) + team.width(names[1]) + 158
        _, ref, _ = next(s for s in SCORE_STRIP if width < s[0])
        main.draw(self.canvas, ref, 199, 85)
        # Fitted against IMG_0101 ("You 7  0 Opp."): the score plaque's text row.
        self.text('team', names[0], 249, 84)
        self.text('team', str(game.home), 311, 84)
        self.text('team', str(game.away), 366, 84)
        self.text('team', names[1], 398, 84)

    def number(self, digits, x, bottom, width, base, gap, *, center=False):
        """`drawHUDNumber`: digit frames 110.. / 122.. (':' is 132), `gap` apart, each hung
        from `bottom` by its own height (a colon by 19)."""
        main = self.atlas(MAIN)
        frames = [TIME_DIGITS + 10 if c == ':' else base + int(c) for c in digits]
        sizes = [main.size(f) for f in frames]
        total = sum(w for w, _ in sizes) + gap * (len(frames) - 1)
        if center:
            x += (width - total) / 2
        for c, frame, (w, h) in zip(digits, frames, sizes):
            main.draw(self.canvas, frame, x, bottom - (19 if c == ':' else h))
            x += w + gap

    # -- targets --------------------------------------------------------
    def yards(self, value, code, x, y, alpha=1., scale=1.):
        """`ItemSlot::drawItemYards`: red (negative) or blue digits, then 'yrds'."""
        if abs(code) == 5:
            return
        main = self.atlas(MAIN)
        if abs(code) == 4:
            main.draw(self.canvas, TURNOVER_LABEL, x, y, origin=True, alpha=alpha, sx=scale, sy=scale)
            return
        digits, sign, suffix = YARDS_BLUE if value >= 0 else YARDS_RED
        text = str(abs(value))
        widths = [DIGIT_ADVANCE[int(c)] for c in text]
        pen = x - (sum(widths) + 46) / 2
        bottom = y
        for index, (c, advance) in enumerate(zip(text, widths)):
            frame = digits + int(c)
            main.draw(self.canvas, frame, pen, bottom - main.size(frame)[1], alpha=alpha, sx=scale, sy=scale)
            pen += advance
            if index == 0 and len(text) > 1:
                # The ones digit sits 0.1 of the tens' advance lower (`drawItemYards`).
                bottom += advance * .1
        main.draw(self.canvas, suffix, pen, bottom - 19, alpha=alpha, sx=scale, sy=scale)

    def targets(self, game):
        main = self.atlas(MAIN)
        field = self.atlas(FIELD_ATLAS)
        timer = game.visual_ms
        for target, (x, y) in zip(game.targets, SLOTS):
            if not target.visible:
                continue
            scale = target.scale
            if target.phase == 2:
                self.emitter(x, y, scale)
            if target.phase in (3, 6):
                self.selection_ring(x, y, timer)
            elif target.phase == 7 and target.elapsed_ms >= 100:
                self.falling_rings(x, y, (target.elapsed_ms - 100) / 500)
            bob = math.sin(target.elapsed_ms / target.hold_ms * math.pi) * 3.5 if target.phase in (3, 6) else 0.
            code = target.code
            main.draw(self.canvas, PLAY_COMPOSITE[code], x, int(y - int(scale * 36) + bob),
                      origin=True, alpha=scale, sx=scale, sy=scale)
            self.yards(target.yards, code, x, y - 76, alpha=scale, scale=scale)

    def emitter(self, x, y, r):
        main = self.atlas(MAIN)
        for growth, alpha in ((r, 1 - .8 * r), (r + .2, 1 - 1.25 * r)):
            if alpha > 0 and growth > 0:
                main.draw(self.canvas, RING_YELLOW, x - 66 * growth, y - 33 * growth,
                          alpha=alpha, sx=growth, sy=growth * .5)

    def falling_rings(self, x, y, t):
        main = self.atlas(MAIN)
        for base in (1.0, 1.3, 1.5):
            growth, alpha = min(1., base - t), 1 - t
            if alpha > 0 and growth > 0:
                main.draw(self.canvas, RING_RED, x - 66 * growth, y - 33 * growth,
                          alpha=alpha, sx=growth, sy=growth * .5)

    def selection_ring(self, x, y, timer):
        """`ItemSlot::drawSelectionRing`: the spinning cyan arc under a live play."""
        main = self.atlas(MAIN)
        alpha = math.sin(timer / 1000 * 4) * .3 + .7
        angle = (timer / 1000 * 360) % 360
        image = main.image(RING_CYAN)
        w, h = image.get_size()
        ring = pygame.transform.rotate(image, -angle)
        ring = pygame.transform.smoothscale(ring, (ring.get_width(), max(1, ring.get_height() // 2)))
        ring = faded(ring, round(255 * alpha))
        self.canvas.blit(ring, ring.get_rect(center=(x, y)))

    # -- effects ---------------------------------------------------------
    def effects(self, game):
        """`HitEffect`: the tapped play's flash and the other plays' fade."""
        main = self.atlas(MAIN)
        android_to_hd = {v: PLAY_COMPOSITE[k] for k, v in ANDROID_PLAY_FRAMES.items()}
        selected_to_base = {v: k for k, v in SELECTED_FRAMES.items()}
        for effect in game.effects:
            remaining = effect.remaining_ms
            x, y = SLOTS_BY_COLUMN[effect.x][0], effect.y * 2
            if effect.selected:
                base = android_to_hd[selected_to_base[effect.frame]]
                ref = SELECTED[base]
                if remaining >= 1000:
                    r = (remaining - 1000) / 500
                    sx, sy, alpha, angle = 1 + (1 - r) * 3, .2 + r * .8, 1., 1.
                else:
                    r = remaining / 1000
                    sx, sy, alpha, angle = r * 4, .2 - r * .2, r, r * 180
                main.draw(self.canvas, ref, x, y, origin=True, alpha=alpha, sx=sx, sy=sy, angle=angle)
            else:
                ref = android_to_hd[effect.frame]
                r = remaining / 1300
                scale = r * effect.scale
                main.draw(self.canvas, ref, x, y - 36 * scale, origin=True, alpha=r, sx=scale, sy=scale)
                if remaining <= 700:
                    self.falling_rings(x, y, 1 - remaining / 700)

    # -- touchdown stars -------------------------------------------------
    STAR = 72
    STARS = 50

    def touchdown_stars(self, game):
        """`TouchdownEffect` (phases 9/10): 50 stars that rise from y 503 with a random
        velocity, gravity 0.0001 px/ms^2, spin and fade. The native code draws its
        randomness from the game's cosmetic stream; here it is a private generator, so
        the pattern differs from the device's but nothing script-visible does."""
        if game.phase not in (9, 10):
            self.stars = []
            self.star_key = None
            return
        key = (game.round, game.phase, game.home, game.away)
        if self.star_key != key:
            rng = self.cosmetic = random.Random(hash(key) & 0xffffffff)
            self.star_key, self.star_start = key, game.visual_ms
            self.stars = [dict(
                delay=rng.randrange(1000) + 300,
                x=rng.randrange(748) + 10,
                vx=rng.randrange(120) / 1000,
                vy=(-50 - rng.randrange(190)) / 1000,
                angle=rng.randrange(360),
                spin=rng.randrange(720) / 1000,
                fade=(-100 - rng.randrange(1500)) / 1e6) for _ in range(self.STARS)]
        age = game.visual_ms - self.star_start
        main = self.atlas(MAIN)
        for star in self.stars:
            t = age - star['delay']
            if t <= 0:
                continue
            alpha = 1 + star['fade'] * t
            y = 503 + star['vy'] * t + .5 * .0001 * t * t
            if alpha <= 0 or y >= 1024:
                continue
            main.draw(self.canvas, self.STAR, star['x'] + star['vx'] * t, y, alpha=alpha,
                      angle=star['angle'] + star['spin'] * t, pivot=(31, 31))

    # -- notification banners -------------------------------------------
    NOTIFY_DURATION = {0: 800, 1: 300, 3: 100, 4: 100, 6: 300, 7: 100, 8: 100, 10: 300, 11: 800}

    def notification(self, game):
        """`drawNotificationEffects`: the dark band swipes in from the left, up to three
        messages take turns on it (each fading in and out, with a shine sweep), and the
        band leaves to the right while the last message spins away."""
        phase = game.message_phase
        if phase == -1:
            return
        main = self.atlas(MAIN)
        hold = game.message_hold_ms
        duration = self.NOTIFY_DURATION.get(phase, hold or 1)
        r = max(0., min(1., game.message_ms / duration))
        alphas = [0., 0., 0.]
        scale, angle = 1., 0.
        band_x, shine = -15., None
        sweep = (1 - r) * 888 - 120
        if phase == 0:
            band_x = -15 - 798 * r
            alphas[0] = 1 - r
            scale, angle = 1 - r, r * 180
        elif phase in (1, 2, 3):
            alphas[0] = {1: 1., 2: 1., 3: r}[phase]
            shine = sweep if phase == 1 else None
        elif phase in (4, 5, 6, 7):
            alphas[1] = {4: 1 - r, 5: 1., 6: 1., 7: r}[phase]
            shine = sweep if phase == 6 else None
        elif phase in (8, 9, 10):
            alphas[2] = {8: 1 - r, 9: 1., 10: 1.}[phase]
            shine = sweep if phase == 10 else None
        elif phase == 11:
            band_x = -15 + 783 * (1 - r)
            alphas[min(game.message_lines, 3) - 1] = r
            scale, angle = r, (1 - r) * 180
        # Decoded: the band is placed by its top-left at (x, 512); text is centered on y 551.
        main.draw(self.canvas, NOTIFY_BAND, band_x, 512)
        if shine is not None:
            main.draw(self.canvas, SHINE, shine, 512)
        texts = game.message_ids or [None]
        for index, alpha in enumerate(alphas):
            if alpha > 0 and scale > 0 and index < len(texts):
                self.big_text(feedback_text(game, self.strings(), index), alpha, scale, angle)

    def big_text(self, text, alpha, scale=1., angle=0.):
        """`drawNotificationText`: wrapped at 748, centered on x 384; y is 551 less half its
        height (a single line sits a quarter of the line height higher). Spinning text
        turns about its own center."""
        font = self.font('big')
        lines = font.wrap(text, 748)
        height = font.text_height(lines)
        width = max(font.width(line) for line in lines)
        top = 551
        if height <= font.height:
            top -= font.height // 4
        top -= height // 2
        if scale == 1 and not angle:
            y = top
            for line in lines:
                font.draw_line(self.canvas, line, (768 - font.width(line)) / 2, y, alpha)
                y += font.height + font.font.line_gap
            return
        layer = pygame.Surface((width + 8, height + 8), pygame.SRCALPHA).convert_alpha()
        y = 4
        for line in lines:
            font.draw_line(layer, line, (width - font.width(line)) / 2 + 4, y)
            y += font.height + font.font.line_gap
        if scale != 1:
            layer = pygame.transform.smoothscale(layer, (max(1, round(layer.get_width() * scale)),
                                                         max(1, round(layer.get_height() * scale))))
        if angle:
            layer = pygame.transform.rotate(layer, -angle)
        layer = faded(layer, round(255 * min(1., alpha)))
        self.canvas.blit(layer, layer.get_rect(center=(384, top + height / 2)))

    # -- countdown, help, bar -------------------------------------------
    def countdown(self, game):
        field = self.atlas(FIELD_ATLAS)
        remaining = game.phase_ms
        slot = min(3, max(0, int(remaining // 600)))
        r = max(0., min(1., (remaining - slot * 600) / 600))
        if slot:
            frame = COUNTDOWN_FRAMES[slot]
            t = max(0., 2 * (r - .5))
            scale, alpha, angle, ref = 1 + t, 1 - t, 0., frame
            w = h = 274
        else:
            if r >= .7:
                t = (r - .7) / .3
                scale, alpha, angle = (1 - t) * 1.1, 1 - t, 0.
            elif r < .4:
                scale = alpha = r / .4
                angle = (1 - scale) * 180
            else:
                scale, alpha, angle = 1., 1., 0.
            ref, (w, h) = GO, field.size(GO)
        field.draw(self.canvas, ref, (768 - w) // 2, (1024 - h) // 2, alpha=alpha, sx=scale, sy=scale,
                   angle=angle, pivot=(w // 2, h // 2))

    PANEL_ORIGIN = (78, 300)

    def instructions(self, game):
        """`drawInstructions`: the help panel settles at (78, 300). It grows in from its
        far corner: scale `s` about its own top-left while that corner moves from
        (78 + 690, 300 + 684) to (78, 300); the coach slides in from the right."""
        strings = self.strings()
        coach = self.coach(game.field_variant)
        # `help_motion()`'s own coach_x is the SD renderer's 320-wide frame by default; this canvas is the HD
        # frame's own 768 (`FRAME[0]`), so the coach's resting edge has to move with it or it slides in to a
        # position far short of the right edge (SD's 320 is well inside this canvas's own width).
        motion = help_motion(game, coach.get_width(), frame_width=FRAME[0])
        scale = motion.scale if game.phase != 25 else 1.
        alpha = motion.alpha
        if alpha > 0 and scale > 0:
            group = self.help_group(game, strings)
            ox, oy = self.PANEL_ORIGIN
            if scale != 1:
                size = max(1, round(group.get_width() * scale)), max(1, round(group.get_height() * scale))
                group = pygame.transform.smoothscale(group, size)
            group = faded(group, round(255 * min(1., alpha)))
            x = ox + (1 - scale) * 690
            y = oy + (1 - scale) * 684
            self.canvas.blit(group, (round(x + self.HELP_MARGIN[0] * scale), round(y + self.HELP_MARGIN[1] * scale)))
        image = coach if motion.coach_alpha >= 1 else coach.copy()
        if motion.coach_alpha < 1:
            image = faded(image, round(255 * motion.coach_alpha))
        self.canvas.blit(image, (motion.coach_x, 977 - coach.get_height()))

    # The panel group is drawn on a surface whose (0, 0) is this far up-left of its origin.
    HELP_MARGIN = (0, -22)

    def help_group(self, game, strings):
        """The help panel and everything on it, relative to its top-left corner."""
        main = self.atlas(MAIN)
        surface = pygame.Surface((610, 386 + 22), pygame.SRCALPHA).convert_alpha()
        saved, self.canvas = self.canvas, surface
        try:
            mx, my = -self.HELP_MARGIN[0], -self.HELP_MARGIN[1]
            main.draw(surface, PANEL, mx, my)
            main.draw(surface, PLAQUE[game.defense], mx + 12, my - 18)
            self.text('white', strings[77 if game.defense else 76], mx + 12 + 182, my - 14, center=True)
            self.text('white', strings[166], mx + 36, my + 360)
            best = strings[165]
            self.text('white', best, mx + 578 - self.font('white').width(best), my + 360)
            self.paragraph(game.instruction, mx + 50, my + 50, 512)
            codes = legend_codes(game)
            step = 434 // (len(codes) - 1) if len(codes) > 1 else 0
            for i, code in enumerate(codes):
                main.draw(surface, PLAY_COMPOSITE[code], mx + 90 - 0 + i * step, my + 282, origin=True)
        finally:
            self.canvas = saved
        return surface

    def bar(self, game):
        main = self.atlas(MAIN)
        main.draw(self.canvas, BAR, 0, 976, origin=True)
        footer = footer_id(game)
        if footer is not None:
            self.text('footer', self.strings()[footer], 441, 984, center=True)

    # -- input ------------------------------------------------------------
    @staticmethod
    def hit(position):
        """The play under a touch, in frame pixels (`checkForHits`: 140 wide, 140 tall
        from 106 above the slot's center)."""
        px, py = position
        return next((i for i, (x, y) in enumerate(SLOTS)
                     if x - 70 <= px <= x + 70 and y - 106 <= py <= y + 34), None)

    # -- frame ----------------------------------------------------------
    def draw(self, target, session):
        game = session.engine.football
        self.canvas.fill((0, 0, 0))
        self.field(game)
        self.targets(game)
        self.effects(game)
        self.touchdown_stars(game)
        self.hud(game)
        self.notification(game)
        if game.phase in (20, 21, 22, 23, 25):
            self.instructions(game)
        elif game.phase == 0:
            self.countdown(game)
        self.bar(game)
        return [(pygame.Rect(-32, 422, 92, 58), ('menu',))]


SLOTS_BY_COLUMN = {60: (184,), 160: (384,), 260: (584,)}
