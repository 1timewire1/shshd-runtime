"""Original choice-panel artwork; selection values remain in the session."""
import math
from functools import lru_cache

from . import graphics as pygame
from .desktop_pause import draw_pause_gear

from .choice import BODY_FONT, FOOTER_FONT, ChoiceLayout
from .choice_hints import preview_choices
from .fonts import TextStyle
from .ui_assets import Rect


class ChoiceRenderer:
    def __init__(self, resources, text_renderer, artwork):
        self.resources, self.text, self.art = resources, text_renderer, artwork
        self.layout = None
        self.canvas = pygame.Surface((320, 480)).convert(32)
        self.cached_key = self.cached_page = None
        self.hint_key = None
        self.hints = ()
        self.viewport = pygame.Rect(0, 0, 320, 421)

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
            self.cached_page = self.layout.page(details, theme=theme,
                                               has_portrait=character >= 0 and bool(variants) and variants[0] > 0)
            self.cached_key = key
        return self.cached_page

    @lru_cache(maxsize=8)
    def timer_panel(self, theme, width, height):
        layer = pygame.Surface((width, height), pygame.SRCALPHA).convert_alpha()
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
                image = self.art.frame({0: 126, 2: pack}[slot], frame)
                layer.blit(pygame.transform.scale(image, (rect.width, rect.height)), (rect.x, rect.y))
        return layer

    def draw_timer(self, position, elapsed_fraction):
        """00082744: base 708, then 709 swept clockwise from twelve o'clock."""
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
                image = self.art.frame(126, 7 + index).copy()
                quadrant = index // 4
                x = 25 - image.get_width() if quadrant >= 2 else 25
                y = 25 - image.get_height() if quadrant in (0, 3) else 25
                image.set_alpha(round(opacity * 255))
                self.canvas.blit(image, (position[0] + 6 + x, position[1] + 5 + y))
            return
        self.canvas.blit(self.art.frame(708, 0), position)
        if fraction <= 0:
            return
        timer = self.art.frame(709, 0).copy()
        if fraction < 1:
            mask = pygame.Surface(timer.get_size(), pygame.SRCALPHA)
            cx, cy = timer.get_width() / 2, timer.get_height() / 2
            radius = math.hypot(cx, cy) + 1
            points = [(cx, cy)] + [(cx + radius * math.sin(t), cy - radius * math.cos(t))
                                  for t in (fraction * 2 * math.pi * i / 120 for i in range(121))]
            pygame.draw.polygon(mask, (255, 255, 255, 255), points)
            timer.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        self.canvas.blit(timer, position)

    def draw(self, target, session, *, scroll=0, pointer=None, pressed=None, choice_hints=False):
        page = self.page(session)
        if choice_hints and self.hint_key != self.cached_key:
            self.hints = preview_choices(session)
            self.hint_key = self.cached_key
        scroll = min(page.max_scroll, max(0, scroll))
        self.viewport.height = page.timer_panel.y if page.timer_panel else 421
        self.canvas.set_clip(None)
        self.canvas.fill((0, 0, 0))
        if session.engine.word_game:
            # The word game's separate background is centered at GL (160,240).
            background = self.art.image(session.engine.panel.background_id)
            if background is not None:
                self.canvas.blit(background, background.get_rect(center=(160, 240)))
        else:
            self.art.draw_background(self.canvas, session.engine)
        self.canvas.set_clip(self.viewport)
        box = page.box
        body_height = box.height - page.timer_panel.height + 10 if page.timer_panel else box.height
        self.art.box(self.canvas, Rect(box.x + 10, box.y + 10 - scroll,
                                       box.width - 20, body_height - 20), page.theme, alpha=243)
        buttons = []
        for row in page.rows:
            rect = pygame.Rect(row.rect.x, row.rect.y - scroll, row.rect.width, row.rect.height)
            hit = rect.clip(self.viewport)
            hint = (self.hints[row.index].kind if choice_hints and row.enabled
                    and self.hint_key == self.cached_key and row.index < len(self.hints) else 'unknown')
            color = {'gain': (189, 237, 199), 'loss': (251, 201, 199),
                     'no_gain': (251, 201, 199), 'mixed': (251, 228, 175)}.get(hint)
            if color is not None:
                pygame.draw.rect(self.canvas, color, rect)
            if row.enabled and (pressed == ('choose', row.index)
                                or pointer is not None and hit.collidepoint(pointer)):
                color = (tuple(round(channel * .9) for channel in color) + (255,) if color else
                         (250, 214, 211, 180) if page.theme == 2 else (170, 225, 249, 180))
                highlight = pygame.Surface(rect.size, pygame.SRCALPHA)
                highlight.fill(color)
                self.canvas.blit(highlight, rect)
            pygame.draw.line(self.canvas, (178, 179, 179), rect.topleft, (rect.right - 1, rect.top))
            game = session.engine.word_game
            offset = 0
            if game and game.animation_ms:
                offset = (game.animation_ms / 200) * (-210 if row.index % 2 == 0 else 410)
            self.canvas.set_clip(hit)
            self.text.draw_layout(self.canvas, BODY_FONT, row.text, row.origin[0] + offset, row.origin[1] - scroll)
            self.canvas.set_clip(self.viewport)
            if row.enabled and hit.height:
                buttons.append((hit, ('choose', row.index)))
        if page.rows:
            rect = page.rows[-1].rect
            y = rect.y + rect.height - scroll
            pygame.draw.line(self.canvas, (178, 179, 179), (rect.x, y), (rect.x + rect.width - 1, y))

        if page.portrait is not None:
            cx, cy = page.portrait.center
            cy -= scroll
            for index in (37, {1: 38, 2: 39}.get(page.theme, 40)):
                image = self.art.frame(126, index)
                self.canvas.blit(image, image.get_rect(center=(cx, cy)))
            details = session.pending.details
            asset = session.engine.character_art_variants[details['character_id']][0]
            # FUN_000ae5d4 requests expression zero, independently of dialogue.
            image = self.art.portrait(asset, details['portrait_mode'] == 2 and page.theme != 3)
            if image is not None:
                self.canvas.blit(image, self.art.portrait_rect(image, (cx, cy)))
        self.text.draw_layout(self.canvas, page.title_font, page.title,
                              page.title_origin[0], page.title_origin[1] - scroll)
        self.text.draw_layout(self.canvas, BODY_FONT, page.description,
                              page.description_origin[0], page.description_origin[1] - scroll)
        self.canvas.set_clip(None)
        if page.timer_panel is not None:
            panel = page.timer_panel
            self.canvas.blit(self.timer_panel(page.theme, panel.width, panel.height), (panel.x, panel.y))
            clock = self.layout.bank.rectangle(22, 10, panel)
            self.draw_timer((clock.x, clock.y),
                            1 - session.remaining_ms / session.pending.details['timeout_ms'])
        game = session.engine.word_game
        if game:
            pack = {1: 204, 2: 220, 3: 252}.get(page.theme, 236)
            self.canvas.blit(self.art.frame(pack, 9), (130, 353))
            self.canvas.blit(self.art.frame(pack, 10), (182, 375))
            self.canvas.blit(pygame.transform.scale(self.art.frame(pack, 11), (12, 39)), (221, 375))
            self.canvas.blit(self.art.frame(pack, 12), (233, 375))
            self.draw_timer((130, 353), 1 - game.remaining_ms / game.duration_ms)
            # Native score text is at (230,88) in GL coordinates (top y=392).
            score = self.text.layout(BODY_FONT, str(game.score), 60, TextStyle(14, 0, (255, 255, 255)))
            self.text.draw_layout(self.canvas, BODY_FONT, score, 230 - score.width / 2, 392)
            if game.animation_ms and game.last_delta:
                color = (37, 147, 56) if game.last_delta > 0 else (255, 0, 0)
                delta = self.text.layout(BODY_FONT, f'{game.last_delta:+d}', 40, TextStyle(14, 0, color))
                self.text.draw_layout(self.canvas, BODY_FONT, delta, 275, 365 + game.animation_ms / 10)
        self.canvas.blit(self.art.frame(126, 47), (0, 431))
        draw_pause_gear(self.canvas, self.art)
        hint = 'Touch the best choice'
        style = TextStyle(11, 0, (185, 185, 185))
        footer = self.text.layout(FOOTER_FONT, hint, 246, style)
        self.text.draw_layout(self.canvas, FOOTER_FONT, footer, 63 + (252 - footer.width) / 2, 460)
        if page.max_scroll:
            # A desktop affordance for unusually long options; no choices are
            # discarded or mapped to a different script-visible index.
            track = pygame.Rect(310, 40, 3, self.viewport.height - 43)
            pygame.draw.rect(self.canvas, (100, 100, 100), track)
            visible_height = self.viewport.height - 31
            thumb = max(20, int(track.height * visible_height / (visible_height + page.max_scroll)))
            y = track.y + int((track.height - thumb) * scroll / page.max_scroll)
            pygame.draw.rect(self.canvas, (225, 225, 225), (track.x, y, track.width, thumb))
        buttons.append((pygame.Rect(0, 422, 60, 58), ('menu',)))
        target.blit(pygame.transform.smoothscale(self.canvas, target.get_size()), (0, 0))
        return page, buttons
