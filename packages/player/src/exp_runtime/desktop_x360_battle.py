"""shshd-runtime: the Monday Planner's Diss Battle drawn over the story's scene (x360_battle.DissBattle; owner, 2026-11-16,
plan `reference/Other Games/docs/DISS_BATTLE_X360_PLAN.md`), on Diss Practice's deck (desktop_x360_diss, which this
extends: the same deck, arm, digits, countdown and fade).

- **The words** stand on the record where the practice's notes would, each on a dark plate in the X360 font, the deck's
  camera giving their size by depth. On a streak they take the practice's tier looks: sparks for x2, flames for x3.
- **The target** sits along the top: "`crash` rhymes with...".
- **A right or wrong word** stamps YEAH! or OOOPS! over the record (the arena's X360 look's stamps), and the tier's
  change shows as the practice's red "x2" / "x3" on the record's label.
- **Spike's taunts**, when the X360 addon's skin lists them (its `battle` entry), come up in a bubble in turn.
- **The tutorial** is a card of the rules, held for a press as the practice's is.

Josh doesn't dance here: he's battling. Nothing here decides anything in the game.
"""
from . import graphics as pygame
from .desktop_x360_diss import (FRAME, START_FONT, START_HEIGHT, START_TEXT, START_Y, TUTORIAL_PROMPT_MS,
                                TUTORIAL_PROMPT_Y, X360DissRenderer)
from .x360_battle import NO_WORD, SECONDS
from .x360_diss import COUNTDOWN, ENDED, RUNNING, SPIN_DOWN, TUTORIAL, TUTORIAL_MS
from .x360_games import CLOSING, OPENING, OPENING_MS, READY

WORD_HEIGHT = 44                        # native pixels at the record's middle depth
WORD_COLOUR = (255, 255, 255)
WORD_FONT = 'casual_white'              # Blambot Casual: the badaboom face blurred at this size (owner, 2026-11-16)
WORD_DEPTH = (.85, 1.15)                # how far the camera's depth may shrink or grow a word, to keep it readable
WORD_PLATE = (10, 12, 20, 235)          # the plate behind a word, and its edge
WORD_EDGE = (255, 255, 255, 255)
TARGET_Y, TARGET_HEIGHT = 40, 30        # "crash rhymes with...", along the top
STAMPS = {'good': 'stamp_yeah', 'bad': 'stamp_ooops'}
STAMP_MS, STAMP_WIDTH = 700, 230
TAUNT_EVERY_MS, TAUNT_MS = 9000, 3500   # a taunt from Spike every 9 s, up for 3.5
TAUNT_X, TAUNT_Y, TAUNT_HEIGHT = 12, 84, 20     # left, under the target, clear of the score (top right)
TUTORIAL_LINES = ('Diss battle!', 'Catch the word that rhymes', 'with the needle.', 'A wrong word costs points;',
                  'five right in a row doubles them,', 'ten triples them.')
RISE = 420


class X360BattleRenderer(X360DissRenderer):
    def draw(self, session):
        game = self.game = session.engine.x360_battle
        width, height = self.canvas_size()
        if self.canvas is None or self.canvas.get_size() != (width, height):
            self.canvas = pygame.Surface((width, height), pygame.SRCALPHA)
        self.canvas.fill((0, 0, 0, 0))
        surface = self.canvas
        now = game.now_ms
        if game.phase == TUTORIAL or (game.phase == OPENING and game.tutorial):
            self._rules(surface, game)
            return
        rise = 0
        if game.phase == OPENING:
            rise = (RISE + surface.get_height() - FRAME[1]) * (max(0, game.phase_ms) / OPENING_MS) ** 2
        parts = self.x360()[0]['booth']['parts']
        self._deck_piece(surface, self.image(parts['body']['id']), parts['body']['box'], 1, rise)
        self._deck_piece(surface, self.image(parts['record']['id']), parts['record']['box'], 1, rise)
        self._record_seams(surface, game, parts['seams'], 1, rise)
        self._deck_piece(surface, self.image(parts['spindle']['id']), parts['spindle']['box'], 1, rise)
        frame = self._arm_frame(parts['arm'], now)
        self._deck_piece(surface, self._arm_cell(parts['arm'], frame), frame['box'], 1, rise)
        if game.phase in (RUNNING, SPIN_DOWN):
            self._words(surface, game, now)
            self._target(surface, game)
        self._hit_effects(surface, game, now)
        self._stamp(surface, game, now)
        if game.phase in (RUNNING, SPIN_DOWN, ENDED, CLOSING):
            self._digits(surface, game, now)
        self._tier(surface, game, now)
        self._taunt(surface, game, now)
        if game.phase == READY:
            words = self._text(START_TEXT, START_HEIGHT, font=START_FONT)
            surface.blit(words, words.get_rect(center=(FRAME[0] // 2, round(START_Y * self.k))))
        if game.phase == COUNTDOWN:
            self._countdown_digit(surface, game)

    # -- the record ------------------------------------------------------------------------------------------------
    def _words(self, surface, game, now):
        shown = []
        for index, slot in enumerate(game.slots):
            if slot['shown'] != NO_WORD:
                x, z = game.slot_at(index)
                nx, ny, depth = self._native_point(x, z, 0)
                shown.append((depth, index, slot['shown'], nx, ny))
        middle = self._project(0, 0)[2]
        for depth, index, word, nx, ny in sorted(shown, key=lambda item: -item[0]):
            text = game.words[word] if 0 <= word < len(game.words) else ''
            scale = min(WORD_DEPTH[1], max(WORD_DEPTH[0], middle / depth if depth else 1))
            image = self._text(text, max(8, round(WORD_HEIGHT * scale)), WORD_COLOUR, font=WORD_FONT)
            w, h = image.get_width() / self.k, image.get_height() / self.k
            edge = FRAME[0] / self.k                    # kept on screen: a long word near the side slides in
            nx = min(max(nx, w / 2 + 10), edge - w / 2 - 10)
            centre = (nx * self.k, (ny - h / 2) * self.k)
            size = (round(w * self.k), round(h * self.k))
            if game.tier == 3:
                self._flames(surface, centre, size, now, index)
            self._plate(surface, nx - w / 2 - 8, ny - h - 2, w + 16, h + 4, WORD_PLATE, WORD_EDGE)
            self.blit(surface, image, nx, ny, w, h, anchor='midbottom')
            if game.tier >= 2:
                self._sparks(surface, centre, size, now, index)

    def _plate(self, surface, x, y, w, h, fill=(12, 14, 24, 170), edge=None):
        k = self.k
        rect = pygame.Rect(round(x * k), round(y * k), max(1, round(w * k)), max(1, round(h * k)))
        key = ('plate', rect.size, fill, edge)
        plate = self._scaled.get(key)
        if plate is None:
            plate = pygame.Surface(rect.size, pygame.SRCALPHA)
            radius = max(2, round(8 * k))
            pygame.draw.rect(plate, fill, plate.get_rect(), border_radius=radius)
            if edge is not None:
                pygame.draw.rect(plate, edge, plate.get_rect(), max(1, round(2 * k)), border_radius=radius)
            self._scaled[key] = plate
        surface.blit(plate, rect)

    def _target(self, surface, game):
        image = self._text(f'{game.target} rhymes with...', TARGET_HEIGHT, font=WORD_FONT)
        w, h = image.get_width() / self.k, image.get_height() / self.k
        if w > FRAME[0] / self.k - 20:
            w, h = FRAME[0] / self.k - 20, h * (FRAME[0] / self.k - 20) / w
        x = FRAME[0] / self.k / 2
        self._plate(surface, x - w / 2 - 8, TARGET_Y, w + 16, h)
        self.blit(surface, image, x, TARGET_Y, w, h, anchor='midtop')

    def _hit_effects(self, surface, game, now):
        """The practice's hit flares, at the word's place on the record."""
        from .desktop_x360_deck import FX
        for effect in game.effects:
            if effect not in self._shown_effects and effect[0] in FX:
                x, z = game.slot_at(effect[1])
                nx, ny, _ = self._native_point(x, z, 0)
                self._spawn(effect[0], nx, ny, effect[2])
        self._shown_effects = [list(e) for e in game.effects]
        self.effects = [e for e in self.effects if 0 <= now - e[3] < FX[e[0]]['life']]
        for effect in self.effects:
            self._draw_effect(surface, effect, now)

    def _stamp(self, surface, game, now):
        """YEAH! or OOOPS! over the record for the last answer, growing in."""
        if not game.effects:
            return
        kind, _, since = game.effects[-1]
        age = now - since
        name = STAMPS.get(kind)
        if name is None or not 0 <= age < STAMP_MS or name not in self.x360()[0]['pictures']:
            return
        image = self.picture(name)
        grow = 1 + .15 * max(0, 1 - age / 150)
        _, cx, cy, _, _, _, _ = self._deck()
        w = STAMP_WIDTH * grow
        alpha = 255 if age < STAMP_MS - 200 else round(255 * (STAMP_MS - age) / 200)
        self.blit(surface, image, cx, cy - 150, w, w * image.get_height() / image.get_width(), alpha=alpha, anchor='center')

    def _tier(self, surface, game, now):
        """The tier's change as the practice's red popup on the record's label: x2, x3."""
        self._combo(surface, game, now)         # (its popup holds the tier where the practice's holds the streak)

    def _taunt(self, surface, game, now):
        """One of Spike's taunts, in turn, every TAUNT_EVERY_MS of play (the skin's `battle` taunts, if it has them)."""
        taunts = self.x360()[0].get('battle', {}).get('taunts') or []
        if not taunts or game.phase != RUNNING:
            return
        played = (SECONDS - game.total_time) * 1000
        turn, into = divmod(played + 3000, TAUNT_EVERY_MS)
        if into >= TAUNT_MS:
            return
        text = taunts[turn % len(taunts)]
        image = self._text(text, TAUNT_HEIGHT, (20, 20, 30), font='badaboom')
        w, h = image.get_width() / self.k, image.get_height() / self.k
        if w > 215:                                     # (the score's digits start at 250)
            w, h = 215, h * 215 / w
        rect = pygame.Rect(round(TAUNT_X * self.k), round((TAUNT_Y - 6) * self.k),
                           round((w + 20) * self.k), round((h + 12) * self.k))
        pygame.draw.rect(surface, (250, 250, 246), rect, border_radius=round(12 * self.k))
        pygame.draw.rect(surface, (20, 20, 30), rect, max(1, round(2 * self.k)), border_radius=round(12 * self.k))
        self.blit(surface, image, TAUNT_X + 10, TAUNT_Y, w, h)

    def _rules(self, surface, game):
        """The tutorial: the rules on a plate, then the prompt, held for a press as the practice's cards are."""
        t = TUTORIAL_MS - game.phase_ms if game.phase == TUTORIAL else 0
        lines = [self._text(line, 40 if i == 0 else 28, None if i else (255, 60, 40), font='badaboom_white' if i else 'badaboom')
                 for i, line in enumerate(TUTORIAL_LINES)]
        heights = [im.get_height() / self.k for im in lines]
        widest = max(im.get_width() / self.k for im in lines)
        x = FRAME[0] / self.k / 2
        top = 140
        self._plate(surface, x - widest / 2 - 20, top - 16, widest + 40, sum(heights) + 32)
        for image, h in zip(lines, heights):
            self.blit(surface, image, x, top, anchor='midtop')
            top += h
        if t >= TUTORIAL_PROMPT_MS:
            words = self._text(START_TEXT, START_HEIGHT, font=START_FONT)
            surface.blit(words, words.get_rect(center=(FRAME[0] // 2, TUTORIAL_PROMPT_Y)))

