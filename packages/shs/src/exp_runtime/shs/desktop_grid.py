"""Service-96 artwork, CS bitmap fonts and native 320 x 480 layout."""
from functools import lru_cache
import math

from .. import graphics as pygame
from ..desktop_pause import draw_pause_gear

from ..ui_assets import read_ui
from ..atlas import AtlasFont, SpriteAtlas
from .grid_layout import clamp, ease, heading_lines, prompt_position, tutorial_box
from .grid_motion import project, cube_faces
from ..projection import draw_quad
from ..menu import MenuStrings


class GridRenderer:
    def __init__(self, resources, text, art):
        self.resources, self.text, self.art = resources, text, art
        self.canvas = pygame.Surface((320, 480)).convert(32)
        self.cells = []

    @lru_cache(maxsize=12)
    def atlas(self, asset):
        return SpriteAtlas.parse(read_ui(self.resources, asset))

    @lru_cache(maxsize=96)
    def frame(self, asset, index):
        frame = self.atlas(asset).raster(index)
        return pygame.image.frombytes(frame.pixels, (frame.width, frame.height), 'RGBA').convert_alpha()

    @lru_cache(maxsize=4)
    def font(self, image):
        return AtlasFont.parse(read_ui(self.resources, image + 1), self.atlas(image).image)

    @lru_cache(maxsize=1)
    def strings(self):
        return MenuStrings.load(self.resources)

    @lru_cache(maxsize=512)
    def glyph(self, asset, char):
        font = self.font(asset)
        glyph = font.glyph(char)
        if glyph is None:
            return None
        x, y, width = glyph
        return self.frame(asset, 0).subsurface((x, y, width, font.height))

    @lru_cache(maxsize=256)
    def text_image(self, asset, text, width=0, monospace=None):
        font = self.font(asset)
        lines = font.wrap(text, width) if width else tuple(text.lstrip(' ').split('\n')) if text else ()
        size = max((font.width(line, monospace) for line in lines), default=0), font.text_height(lines)
        image = pygame.Surface((max(1, size[0]), max(1, size[1])), pygame.SRCALPHA).convert_alpha()
        for row, line in enumerate(lines):
            x = 0
            for char in line:
                glyph = self.glyph(asset, char)
                if glyph is not None and char != ' ':
                    image.blit(glyph, (x, row * (font.height + font.line_gap)))
                x += font.char_width(char, monospace) + font.tracking
        return image

    def blit(self, image, x, y, *, scale=1., alpha=1., center=False, angle=0.):
        if scale <= 0 or alpha <= 0:
            return
        if angle:
            image = pygame.transform.rotozoom(image, angle, scale)
        elif scale != 1:
            image = pygame.transform.smoothscale(image, (max(1, round(image.get_width() * scale)),
                                                          max(1, round(image.get_height() * scale))))
        if alpha < 1:
            image = image.copy()
            image.set_alpha(round(255 * clamp(alpha)))
        self.canvas.blit(image, image.get_rect(center=(round(x), round(y))) if center else (int(x), int(y)))

    def label(self, asset, text, x, y, *, width=0, scale=1., alpha=1., center=False, monospace=None):
        self.blit(self.text_image(asset, text, width, monospace), x, y,
                  scale=scale, alpha=alpha, center=center)

    @staticmethod
    def project(width, height, x, y):
        return project(width, height, x, y)[:2]

    def geometry(self, game):
        self.cells = self.board_geometry(game.problem)

    def board_geometry(self, problem):
        cells = []
        for row in range(problem.height):
            for col in range(problem.width):
                x, y = col * 522, row * 522
                quad = tuple(self.project(problem.width, problem.height, x + dx, y + dy)
                             for dx, dy in ((0, 0), (450, 0), (450, 450), (0, 450)))
                center = self.project(problem.width, problem.height, x + 225, y + 225)
                w = max(v[0] for v in quad) - min(v[0] for v in quad)
                h = quad[3][1] - quad[0][1]
                cells.append((quad, pygame.FRect(center[0] - w / 2, center[1] - h / 2, w, h)))
        return cells

    def hit(self, position, game):
        self.geometry(game)
        # Native accepts a whole-cell hit at drag start, then a 65% inset.
        for col in range(game.problem.width):
            for row in range(game.problem.height):
                i = row * game.problem.width + col
                rect = self.cells[i][1].copy()
                if game.selection:
                    rect.inflate_ip(-rect.width * .35, -rect.height * .35)
                if rect.collidepoint(position):
                    return i
        return None

    def quad(self, image, points):
        """Scanline projection of the original sprite onto the board plane."""
        pygame.project_quad(self.canvas, image, points)

    @lru_cache(maxsize=256)
    def cell_image(self, frame, char, picture, glint=-1):
        tile = self.frame(446, frame).copy()
        if glint >= 0:
            tile.blit(pygame.transform.smoothscale(self.frame(446, 35 + glint), tile.get_size()), (0, 0))
        glyph = self.art.image(picture) if picture is not None else self.glyph(522, char)
        if glyph is not None:
            # 000c8c30: pictures occupy 382.5 of the 450 world units;
            # the 85px letter font is drawn at scale 4.285714.
            ratio = tile.get_height() * (.85 if picture is not None else 85 / 105) / glyph.get_height()
            letter = pygame.transform.smoothscale(glyph, (max(1, round(glyph.get_width() * ratio)),
                                                           max(1, round(glyph.get_height() * ratio))))
            tile.blit(letter, letter.get_rect(center=tile.get_rect().center))
        return tile

    def backdrop(self, game, background_id):
        self.canvas.fill((0, 0, 0))
        background = self.art.image(background_id)
        if background is not None:
            self.blit(background, 160, 240, center=True)
        # 000c1ca8 and 000c6220: rotating haze and four scrolling cloud edges.
        self.blit(self.frame(446, 3), 160, 240, scale=1.8, center=True,
                  angle=game.visual_ms / 1000 * 20)
        if game.phase == -2:
            return
        entry = game.phase_ms / 1500 if game.phase == -1 else 0
        travel = int(game.visual_ms / 1000 * 15)
        for frame, y, step, offset in ((0, 429 + int(entry * 51), 280, travel % 280 - 280),
                                        (4, int(-entry * 256), 256, -(travel % 256))):
            x = offset
            x -= x % 2
            while x < 640:
                self.blit(self.frame(446, frame), x - step / 2, y)
                x += step
        for frame, x in ((1, int(-entry * 41)), (2, 273 + int(entry * 47))):
            y = -(travel % 289) - (289 if frame == 1 else 0)
            y += y % 2
            while y < 960:
                self.blit(self.frame(446, frame), x, (480 - y if frame == 1 else y) - 289 / 2)
                y += 289

    def portraits(self, session):
        game, details = session.engine.word_grid, session.pending.details
        if game.phase in (-2, -1):
            return
        progress = 1 - game.phase_ms / 2800 if game.phase == 0 else 1.
        scale = ease(progress, .2, .52, .9) if game.phase == 0 else 1.
        alpha = ease(progress, .2, .52) if game.phase == 0 else 1.
        for side in ('left', 'right'):
            char = details[side + '_character']
            variants = session.engine.character_art_variants.get(char, ())
            if not variants:
                continue
            portrait = self.art.image(variants[max(0, details[side + '_expression']) % len(variants)])
            if portrait is None:
                continue
            w, h = portrait.get_size()
            cx, cy = (w // 2 + 10, h // 2 + 5) if side == 'left' else (310 - w // 2, 475 - h // 2)
            angle = game.visual_ms / 1000 * 40
            self.blit(self.frame(502, 0), cx + .5, cy + 10, scale=scale,
                      alpha=alpha, center=True, angle=angle)
            if side == 'right' and session.engine.numbers.get(session.engine.number_key(char, 651), 0) != 3:
                portrait = pygame.transform.flip(portrait, True, False)
            self.blit(portrait, cx, cy + 12, scale=scale, alpha=alpha, center=True)
            self.blit(self.frame(499, 0), cx, cy, scale=scale, alpha=alpha, center=True, angle=angle)

    def hud(self, game):
        if game.phase in (-2, -1):
            return
        scale = clamp((2800 - game.phase_ms) / 500) if game.phase == 0 else 1.
        for text, edge, y, mono in ((self.strings()[32], 196, 2, None),
                                    (f'{math.ceil(game.remaining_ms / 1000):03}', 206, 22, '3'),
                                    (self.strings()[33], 278, 2, None),
                                    (f'{game.score:05}', 310, 22, '3')):
            width = self.font(512).width(text, mono)
            self.label(512, text, edge - width * scale, y, scale=scale, alpha=scale, monospace=mono)
        if game.delta_ms:
            text = f'+{game.last_delta}'
            self.label(512, text, 310 - self.font(512).width(text), 42)

    def board(self, game):
        p, board, starts, cells = game.problem, game.board, game.starts, self.cells
        transition = game.transition
        outgoing = transition and transition.mode == 'shrink' and game.phase == 4
        if outgoing:
            p, board, starts = transition.problem, transition.board, transition.starts
            cells = self.board_geometry(p)
        hidden = (transition.tutorial and transition.problem.hide_board
                  if transition and game.phase == 4 else game.tutorial and p.hide_board)
        if game.phase in (-2, -1) or hidden:
            return
        faces = []
        for i, (_, rect) in enumerate(cells):
            col, row = i % p.width, i // p.width
            delay = (p.height - 1 + col - row) * 80
            size, angle = 1., 0.
            if outgoing:
                size = ease(1 - clamp((800 - game.phase_ms - delay) / 600), bounce=.8)
            elif transition and transition.mode == 'flip' and game.phase in (4, 2):
                age = 800 - game.phase_ms if game.phase == 4 else 2600 - game.phase_ms
                angle = (1 - clamp((age - max(1, delay)) / 700)) * math.pi
            elif game.phase in (2, 6) and (not transition or transition.mode == 'shrink'):
                size = ease(clamp((game.board_entry_ms - delay) / 600), bounce=.8)
            elif game.phase == 0:
                size = clamp((2800 - game.phase_ms) / 1400)
            if not outgoing and i in game.pop_ms:
                size = ease(clamp((600 - game.pop_ms[i]) / 600), bounce=.8)
            if size <= 0:
                continue
            selected = not outgoing and i in game.selection
            bad = not outgoing and i in game.bad_prefix
            frame = 33 if bad else 43 if selected else 41 if p.highlight and i in starts else 15
            shine = game.glint_ms - delay
            glint = min(5, shine // 100) if 0 <= shine <= 600 else -1
            for depth, face, quad in cube_faces(p.width, p.height, col, row, angle, size):
                if face == 'side':
                    tile = self.frame(446, frame + 1)
                else:
                    char = transition.board[i] if face == 'back' and transition else board[i]
                    tile = self.cell_image(frame, char, game.symbols.get(ord(char)), glint if face == 'front' else -1)
                faces.append((depth, tile, quad))
        for _, tile, quad in sorted(faces, key=lambda item: item[0]):
            draw_quad(self.canvas, tile, quad)
        if outgoing or game.phase == 4:
            return
        paths = [(game.selection, False)]
        if p.show_hints:
            for start in starts:
                path = next((path for word in p.words if (path := game.find_path(start, word))), None)
                if path:
                    paths.append((path, True))
        for path, hint in paths:
            for a, b in zip(path, path[1:]):
                if hint and (a, b) in tuple(zip(game.selection, game.selection[1:])):
                    continue
                ax, ay, bx, by = a % p.width, a // p.width, b % p.width, b // p.width
                dx, dy = bx - ax, by - ay
                # 000c6a48: orange directional art for the player's trace;
                # the blue arrow rotates for hints. Both occupy the board plane.
                if hint:
                    arrow = pygame.transform.rotate(self.frame(446, 5), math.degrees(math.atan2(-dy, dx)))
                else:
                    frame = {(1, 0): 6, (1, -1): 12, (0, -1): 13, (-1, -1): 7,
                             (-1, 0): 8, (-1, 1): 9, (0, 1): 10, (1, 1): 11}[dx, dy]
                    arrow = self.frame(446, frame)
                cx, cy = (ax + bx) * 261 + 225, (ay + by) * 261 + 225
                w, h = arrow.get_width() * 3, (arrow.get_height() - (0 if hint else 8)) * 3
                quad = tuple(self.project(p.width, p.height, cx + x, cy + y)
                             for x, y in ((-w/2, -h/2), (w/2, -h/2), (w/2, h/2), (-w/2, h/2)))
                self.quad(arrow, quad)

    def prompts(self, game):
        p = game.transition.problem if game.transition and game.phase == 4 else game.problem
        for line, x, y, alpha in heading_lines(game, p):
            self.label(512, line, x, y, alpha=alpha)
        if game.phase in (-2, -1, 6):
            return
        lines = p.prompt.split('\n')[:3] if p.prompt else ()
        alpha = max(0., game.phase_ms / 800 - .2) if game.phase == 4 else 1.
        progress = 1 - game.phase_ms / (2800 if game.phase == 0 else 1800) if game.phase in (0, 2) else 1.
        for index, line in enumerate(lines):
            age = progress - index * .05 if game.phase in (0, 2) else progress
            if age < .2:
                continue
            width = self.font(510).width(line)
            x, y, scale = prompt_position(age, index, width, len(lines), self.font(510).height)
            self.label(510, line, x, y, scale=scale, alpha=alpha, center=True)

    def banner(self, game):
        banner = game.banner
        if banner is None:
            return
        text = {'ready': lambda: self.strings()[80], 'target': lambda: self.strings()[59] % game.target,
                'success': lambda: game.success_text, 'failure': lambda: game.failure_text,
                'time_up': lambda: self.strings()[57],
                'result': lambda: self.strings()[81] % (game.score, game.target)}[banner.kind]()
        age = banner.age_ms
        scale = clamp(age / banner.enter_ms)
        alpha = scale if age < banner.enter_ms else clamp(1 - ((age - banner.enter_ms) / banner.hold_ms - .6) / .6)
        # 000c8408: whole block centered; each line left-aligned within it.
        self.label(510, text, 160, 240, scale=scale, alpha=alpha, center=True)

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
        if not p.tutorial_text:
            return
        if scale <= 0:
            return
        font = self.font(516)
        box = tutorial_box(font.text_height(font.wrap(p.tutorial_text, 286)), p.tutorial_position, scale)
        self.blit(self.frame(446, 47), box.x, box.top, scale=scale, alpha=scale)
        middle = pygame.transform.scale(self.frame(446, 45), (306, box.body_height))
        self.blit(middle, box.x, box.body_y, scale=scale, alpha=scale)
        self.blit(self.frame(446, 46), box.x, box.body_y + box.body_height * scale, scale=scale, alpha=scale)
        self.label(516, p.tutorial_text, box.x + 10 * scale, box.body_y + 10 * scale,
                   width=286, scale=scale, alpha=scale)
        self.label(512, p.tutorial_title, box.x + 22 * scale, box.top - 6 * scale,
                   width=306, scale=scale, alpha=scale)

    def draw(self, target, session):
        game = session.engine.word_grid
        self.geometry(game)
        self.backdrop(game, session.pending.details['background_id'])
        self.portraits(session)
        self.hud(game)
        self.board(game)
        self.prompts(game)
        for burst in game.explosions:
            for fragment in burst:
                self.blit(self.frame(446, 17 + int(fragment.age_ms * 12 / 1000) % 16),
                          fragment.x, fragment.y, scale=fragment.scale, angle=-fragment.angle, center=True)
        self.banner(game)
        self.tutorial(game)
        # Keep the desktop pause control clear of the original bottom word list.
        draw_pause_gear(self.canvas, self.art)
        target.blit(pygame.transform.smoothscale(self.canvas, target.get_size()), (0, 0))
        return [(pygame.Rect(0, 422, 60, 58), ('menu',))]
