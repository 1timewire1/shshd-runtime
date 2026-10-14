"""Native service-94 art, fonts, panels, play targets and feedback."""
from dataclasses import replace
from functools import lru_cache
from io import BytesIO
import math

from .. import graphics as pygame
from ..desktop_pause import draw_pause_gear

from ..atlas import AtlasFont, SpriteAtlas
from .football import PLAY_FRAMES, TARGET_CENTERS
from .football_layout import (FONT, HELP_STYLE, LABEL_STYLE, TITLE_STYLE, clamp,
                              countdown_motion, feedback_motion, feedback_text,
                              footer_id, heading_id, help_motion, legend_codes,
                              target_position, team_name, yard_glyphs, score_strip)
from ..menu import MenuStrings
from ..ui_assets import ImagePack, Raster, read_ui


class FootballRenderer:
    def __init__(self, resources, text, art):
        self.resources, self.text, self.art = resources, text, art
        self.canvas = pygame.Surface((320, 480)).convert(32)

    @lru_cache(maxsize=1)
    def atlas(self):
        return SpriteAtlas.parse(read_ui(self.resources, 290))

    @lru_cache(maxsize=154)
    def frame(self, index):
        r = self.atlas().raster(index)
        return pygame.image.frombytes(r.pixels, (r.width, r.height), 'RGBA').convert_alpha()

    @lru_cache(maxsize=10)
    def image(self, asset):
        data = read_ui(self.resources, asset)
        if data.startswith((b'\x89PNG', b'\xff\xd8')):
            return pygame.image.load(BytesIO(data)).convert_alpha()
        raster = ImagePack.parse(data).images[0]
        return pygame.image.frombytes(raster.pixels, (raster.width, raster.height), raster.mode).convert_alpha()

    @lru_cache(maxsize=1)
    def strings(self):
        return MenuStrings.load(self.resources)

    @lru_cache(maxsize=1)
    def feedback_font(self):
        # Unlike grid glyph sheets, 540 is a PNG; 541 uses the CS metrics.
        image = self.image(540)
        return AtlasFont.parse(read_ui(self.resources, 541),
                               Raster(*image.get_size(), pygame.image.tobytes(image, 'RGBA')))

    @lru_cache(maxsize=128)
    def feedback_image(self, text):
        font, atlas = self.feedback_font(), self.image(540)
        lines = font.wrap(text, 300)
        width = max((font.width(line) for line in lines), default=0)
        image = pygame.Surface((max(1, width), max(1, font.text_height(lines))), pygame.SRCALPHA)
        for row, line in enumerate(lines):
            x = (width - font.width(line)) // 2
            for char in line:
                glyph = font.glyph(char)
                if glyph is not None and char != ' ':
                    gx, gy, gw = glyph
                    image.blit(atlas, (x, row * (font.height + font.line_gap)), (gx, gy, gw, font.height))
                x += font.char_width(char) + font.tracking
        return image

    @lru_cache(maxsize=1)
    def score_font(self):
        # loadImageFont(523,522) at SHS iOS 00088094. Both supplied asset
        # profiles contain the same CS glyph sheet in semantic roles 524/525.
        raster = SpriteAtlas.parse(read_ui(self.resources, 524)).raster(0)
        return (AtlasFont.parse(read_ui(self.resources, 525), raster),
                pygame.image.frombytes(raster.pixels, (raster.width, raster.height), 'RGBA').convert_alpha())

    @lru_cache(maxsize=64)
    def score_text(self, text):
        font, atlas = self.score_font()
        image = pygame.Surface((max(1, font.width(text)), font.height), pygame.SRCALPHA)
        x = 0
        for char in text:
            glyph = font.glyph(char)
            if glyph is not None and char != ' ':
                gx, gy, gw = glyph
                image.blit(atlas, (x, 0), (gx, gy, gw, font.height))
            x += font.char_width(char) + font.tracking
        return image

    def scoreboard(self, game):
        font, _ = self.score_font()
        home, away = (team_name(self.strings(), selector) for selector in game.teams)
        frame, offset = score_strip(font.width(home), font.width(away))
        literals = self.atlas().literals(frame)
        center = 253 + min(x for _, x, _ in literals) + offset
        self.composite(frame, 253, 50)
        for text, x, width in ((home, center - 28 - font.width(home), 0),
                               (str(game.home), center - 24, 17), ('-', center - 3, 6),
                               (str(game.away), center + 7, 17), (away, center + 28, 0)):
            image = self.score_text(text)
            self.canvas.blit(image, (x + int((width - font.width(text)) / 2) if width else x, 42))

    def blit(self, image, x, y, *, scale=1., scale_y=None, alpha=1., angle=0., center=False):
        scale_y = scale if scale_y is None else scale_y
        if scale <= 0 or scale_y <= 0 or alpha <= 0:
            return
        if scale != 1 or scale_y != 1:
            image = pygame.transform.smoothscale(image, (max(1, round(image.get_width() * scale)),
                                                          max(1, round(image.get_height() * scale_y))))
        if angle:
            image = pygame.transform.rotate(image, -angle)
        if alpha < 1:
            image = image.copy()
            image.set_alpha(round(255 * clamp(alpha)))
        self.canvas.blit(image, image.get_rect(center=(round(x), round(y))) if center else (round(x), round(y)))

    def node(self, index, x, y, **transform):
        """0009936c positions the returned sprite at x+w/2, y+h/2.

        Play and glyph composites each contain one literal. Their serialized
        negative origin is replaced by this node placement; applying it again
        would shift the art out of its fixed touch box.
        """
        literals = self.atlas().literals(index)
        if len(literals) != 1:
            raise ValueError('Football node requires a single-literal sprite')
        image = self.frame(literals[0][0])
        self.blit(image, x + image.get_width() / 2, y + image.get_height() / 2,
                  center=True, **transform)

    def composite(self, index, x, y):
        # Field chalk uses the direct composite path, retaining child offsets.
        for ref, dx, dy in self.atlas().literals(index):
            self.blit(self.frame(ref), x + dx, y + dy)

    def label(self, text, x, y, *, width=320, style=LABEL_STYLE, center=False):
        """Native line-box origin, with per-line horizontal centering."""
        layout = self.text.layout(FONT, text, width, style)
        if center:
            offsets = {line.start: -line.width / 2 for line in layout.lines}
            glyphs = tuple(replace(g, x=g.x + offsets[line.start]) for line in layout.lines
                           for g in layout.glyphs if line.start <= g.index < line.end)
            layout = replace(layout, glyphs=glyphs)
        self.text.draw_layout(self.canvas, FONT, layout, x, y)

    @staticmethod
    def hit(position):
        # 000bc2ec: inclusive fixed bounds, independent of target zoom.
        px, py = position
        return next((i for i, (x, y) in enumerate(TARGET_CENTERS)
                     if x - 35 <= px <= x + 35 and y - 53 <= py <= y + 17), None)

    def field(self, game):
        # 000b8410 / 000b82f4: field camera, turf, authored chalk and haze.
        position = game.camera_position
        y = -position * 45
        x = (y * -.40613848) % 320
        y = -((-y) % 480)
        for dx, dy in ((0, 0), (-320, 0), (0, 480), (-320, 480)):
            self.blit(self.frame(86), x + dx, y + dy)
        frames = (-83, -65, -69, -73, -77, -79, -76, -72, -68, -64, -84)
        start = int(position) - 6
        for yard in range(start, start + 14):
            if 0 <= yard <= 100 and yard % 5 == 0:
                y = 240 + (yard - position) * 45
                self.composite(frames[yard // 10] if yard % 10 == 0 else -80,
                               int(y * -.4354067), int(y - 56))
        x, y = -(int(game.visual_ms * .02) % 320), int(game.visual_ms * .05) % 480
        for dx, dy in ((0, 0), (0, -480), (320, 0), (320, -480)):
            self.blit(self.frame(75), x + dx, y + dy, scale=4, alpha=.14705883)

    def hud_digits(self, text, x, y, width=0, *, clock=False):
        """000b6818 / 000b68b4 / 000b9e90: measured and drawn spacing differ."""
        indices = [128 + int(c) if c.isdigit() else {'-': 138, '+': 139, ':': 150}[c] for c in text]
        measure = sum(self.frame(i).get_width() for i in indices) + len(indices) - 1
        x += int((width - measure) / 2)
        for char, index in zip(text, indices):
            image = self.frame(index)
            w, h = image.get_size()
            if clock:
                height = 4 if char == ':' else h
                native_y = int(480 - y - height + h * 1.5)
                native_y -= native_y % 2
                self.blit(image, x - 1 - w / 2, 480 - (native_y - 5) - h)
                x += w + {'1': 2, ':': 4}.get(char, 0)
            else:
                height = {'-': 6, '+': 7, ':': 8}.get(char, h)
                self.blit(image, x + 2 - w / 2, y + height - 2 * h)
                x += w + 3

    def hud(self, game):
        strings = self.strings()
        self.node(30, 10, 13)
        self.node(153 if game.defense else 152, 19, 4)
        # BM labels draw downward from local zero; center alignment adds
        # half the measured line height (14), unlike ordinary sprite anchors.
        self.label(strings[heading_id(game)], 109, 7, center=True)
        self.blit(self.image(701 + min(game.down, 3)), 99, 33, center=True)
        distance = int(100 - game.hud_position if game.defense else game.hud_position)
        self.hud_digits(str(max(0, min(100, distance))), 186, 37, 20)
        seconds = max(0, math.ceil(game.remaining_ms / 1000))
        self.hud_digits(f'{seconds // 60}:{seconds % 60:02}', 165, 37, clock=True)
        self.scoreboard(game)

    def targets(self, game):
        for target, (x, y) in zip(game.targets, TARGET_CENTERS):
            if not target.visible:
                continue
            scale = target.scale
            if target.phase == 2:
                for growth, alpha in ((scale, 1 - .8 * scale), (scale + .2, 1 - 1.25 * scale)):
                    # Native changes the ripple anchor to top-left after
                    # setting a center position; its sheet is half-height.
                    self.blit(self.frame(127), x - 2 - growth * 33, y - 7 - growth * 16.5,
                              scale=growth, scale_y=growth * .5, alpha=alpha)
            if target.phase in (3, 6):
                alpha = math.sin(game.visual_ms / 1000 * 4) * .3 + .7
                if getattr(self.resources.library, 'kind', 'apk') == 'ipa':
                    # ItemSlot::drawSelectionRing (0008efa8): the iOS asset is
                    # frame 125, rotating at 360 degrees/s then halved in Y.
                    shadow = pygame.transform.rotate(self.frame(125), -(game.visual_ms * .36 % 360))
                    self.blit(shadow, x, y, scale_y=.5, alpha=alpha, center=True)
                else:
                    # 000c0ac0: 110ms per exported Android shadow frame.
                    shadow = self.image(720 + (target.elapsed_ms // 110) % 4)
                    self.blit(shadow, x, 600 - y, scale=1.3, scale_y=1.2, alpha=alpha / 1.5, center=True)
            elif target.phase == 7 and target.elapsed_ms >= 100:
                progress = (target.elapsed_ms - 100) / 500
                for growth in (progress, min(1., 1.3 - progress), min(1., 1.5 - progress)):
                    self.blit(self.frame(126), x - 2 - growth * 33, y - 7 - growth * 16.5,
                              scale=growth, scale_y=growth * .5, alpha=1 - progress)
            self.node(PLAY_FRAMES[target.code], *target_position(target, (x, y)), scale=scale, alpha=scale)
            if abs(target.code) == 4:
                self.node(-1, x, y - 38, scale=scale, alpha=scale)
            elif abs(target.code) != 5:
                for frame, gx, gy in yard_glyphs(target.yards, x, y - 38):
                    self.node(frame, gx, gy, scale=scale, alpha=scale)

    def effects(self, game):
        """000b2494 / 000b4bd0: selected play squashes and spins away."""
        for effect in game.effects:
            remaining = effect.remaining_ms
            if effect.selected:
                if remaining >= 1000:
                    r = (remaining - 1000) / 500
                    sx, sy, alpha, angle = 1 + (1 - r) * 3, .2 + r * .8, 1., 1.
                else:
                    r = remaining / 1000
                    sx, sy, alpha, angle = r * 4, .2 - r * .2, r, r * 180
                _, dx, dy = self.atlas().literals(effect.frame)[0]
                self.node(effect.frame, effect.x + dx, effect.y + dy,
                          scale=sx, scale_y=sy, alpha=alpha, angle=angle)
            else:
                r = remaining / 1300
                scale = r * effect.scale
                self.node(effect.frame, effect.x, effect.y - 18 * scale,
                          scale=scale, alpha=r)

    def help(self, game):
        strings = self.strings()
        coach = self.frame(game.field_variant)
        m = help_motion(game, coach.get_width())
        self.node(64, m.x, m.y, scale=m.scale, alpha=m.alpha)
        if m.alpha > 0:
            self.node(153 if game.defense else 152, m.x + 6, m.y - 9,
                      scale=m.scale, alpha=m.alpha)
            # BM labels follow the moving panel, but do not inherit its scale.
            self.label(strings[77 if game.defense else 76], m.x + 97, m.y - 6,
                       width=166, style=TITLE_STYLE, center=True)
            self.label(game.instruction, m.x + 25, m.y + 26, width=256, style=HELP_STYLE)
            self.label(strings[166], m.x + 18, m.y + 183)
            best = self.text.layout(FONT, strings[165], 320, LABEL_STYLE)
            self.label(strings[165], m.x + 289 - best.width, m.y + 183)
            codes = legend_codes(game)
            spacing = 217 // (len(codes) - 1) if len(codes) > 1 else 0
            for i, code in enumerate(codes):
                frame = self.frame(self.atlas().literals(PLAY_FRAMES[code])[0][0])
                x = m.x + 45 + i * spacing - 35 + frame.get_width() / 2
                # 000be110 sets anchor (.5,0) after node placement.
                bottom = m.y + 141 + frame.get_height() / 2
                s = m.scale / 1.1
                self.blit(frame, x - frame.get_width() * s / 2, bottom - frame.get_height() * s,
                          scale=s, alpha=m.alpha)
        self.blit(coach, m.coach_x, 457 - coach.get_height(), alpha=m.coach_alpha)

    def feedback(self, game):
        motion = feedback_motion(game)
        if motion is None:
            return
        self.node(66, motion.x, 240)
        if motion.shine_x is not None:
            self.node(65, motion.shine_x, 240)
        if motion.visible:
            image = self.feedback_image(feedback_text(game, self.strings(), motion.index))
            height = self.feedback_font().height
            y = 259 - (height >> 2) if image.get_height() <= height else 259
            self.blit(image, 160, y, scale=motion.scale, angle=motion.angle, center=True)

    def draw(self, target, session):
        game = session.engine.football
        self.canvas.fill((0, 0, 0))
        self.field(game)
        self.targets(game)
        self.effects(game)
        self.hud(game)
        self.feedback(game)
        if game.phase in (20, 21, 22, 23, 25):
            self.help(game)
        elif game.phase == 0:
            motion = countdown_motion(game.phase_ms)
            self.blit(self.frame(motion.frame), 159.5, 240, scale=motion.scale,
                      alpha=motion.alpha, angle=motion.angle, center=True)
        self.canvas.blit(self.art.frame(126, 47), (0, 431))
        draw_pause_gear(self.canvas, self.art)
        footer = footer_id(game)
        if footer is not None:
            self.label(self.strings()[footer], 180, 462, center=True)
        target.blit(pygame.transform.smoothscale(self.canvas, target.get_size()), (0, 0))
        return [(pygame.Rect(0, 422, 60, 58), ('menu',))]
