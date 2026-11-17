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

WORD_HEIGHT = 32                        # native pixels at the record's middle depth
WORD_COLOUR = None                      # the font's own: tinting it white also whitened its thin dark edge, so the
                                        # letters swelled and ran together (owner, 2026-11-16: "a glow")
WORD_FONT = 'casual_white'              # Blambot Casual: the badaboom face blurred at this size (owner, 2026-11-16)
WORD_DEPTH = (.85, 1.15)                # how far the camera's depth may shrink or grow a word, to keep it readable
WORD_PLATE = (10, 12, 20, 140)          # the plate behind a word, see-through (None: none), and its edge
WORD_EDGE = None
WORD_OUTLINE = 2                        # canvas pixels of black outline round the letters (0: none)
WORD_CUT = 60                           # the letters' alpha from which a pixel counts as letter, with an outline
TARGET_Y, TARGET_HEIGHT = 40, 30        # "crash rhymes with...", along the top
STAMPS = {'good': 'stamp_yeah', 'bad': 'stamp_ooops'}
STAMP_MS, STAMP_WIDTH = 700, 230
TAUNT_EVERY_MS, TAUNT_MS = 9000, 3500   # a taunt from Spike every 9 s, up for 3.5
TAUNT_X, TAUNT_Y, TAUNT_HEIGHT = 12, 84, 20     # left, under the target, clear of the score (top right)
TUTORIAL_LINES = ('Diss battle!', 'Catch the word that rhymes', 'with the needle.', 'A wrong word costs points;',
                  'five right in a row doubles them,', 'ten triples them.')
RISE = 420



def silhouette(image, cut):
    """`image` as black where its alpha is above `cut` and clear elsewhere, as pygame's mask makes it. The iOS drawing
    backend has no mask module (the Diss Battle stopped there on the iPad, 2026-11-17), so it's built from the alpha bytes
    there, the same rule."""
    mask = getattr(pygame, 'mask', None)
    if mask is not None:
        return mask.from_surface(image, cut).to_surface(setcolor=(0, 0, 0, 255), unsetcolor=(0, 0, 0, 0))
    data = pygame.image.tobytes(image, 'RGBA')
    out = bytearray(len(data))
    out[3::4] = data[3::4].translate(bytes(255 if alpha > cut else 0 for alpha in range(256)))
    return pygame.image.frombytes(bytes(out), image.get_size(), 'RGBA')

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
            self._warm_up()
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

    def _warm_up(self):
        """While the rules card waits for its press, what play draws first, a piece a frame: the deck's pictures (else
        all loaded on the first countdown frame: 105 ms on a PC, ~430 ms on the g54 after a cold start, 2026-11-16),
        the countdown and score digits, the stamps, the hit sprites and the fonts. Once a renderer; later battles reuse it."""
        if self._warm is None:
            spec = self.x360()[0]
            parts, pictures = spec['booth']['parts'], spec['pictures']
            loads = [parts['body']['id'], parts['record']['id'], parts['spindle']['id'], parts['seams']['id'],
                     parts['arm']['atlas'], spec['booth']['digits']['atlas']]
            loads += [pictures[name] for name in STAMPS.values() if name in pictures]
            loads += [pictures[name] for name in pictures if name.startswith(('fx_spark_', 'fx_puff_'))]
            self._warm = [lambda resource=resource: self.image(resource) for resource in loads]
            self._warm += [lambda: self._text('A', WORD_HEIGHT, WORD_COLOUR, font=WORD_FONT),
                           lambda: self._text('A', TARGET_HEIGHT, font=WORD_FONT),
                           lambda: self._text('A', TAUNT_HEIGHT, (20, 20, 30), font='badaboom')]
        if self._warm:
            self._warm.pop(0)()

    _warm = None

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
            if WORD_PLATE is not None:
                self._plate(surface, nx - w / 2 - 8, ny - h - 2, w + 16, h + 4, WORD_PLATE, WORD_EDGE)
            if WORD_OUTLINE:
                image = self._outlined(image, WORD_OUTLINE)
                pad = WORD_OUTLINE / self.k
                w, h = w + 2 * pad, h + 2 * pad
                self.blit(surface, image, nx, ny + pad, w, h, anchor='midbottom')
            else:
                self.blit(surface, image, nx, ny, w, h, anchor='midbottom')
            if game.tier >= 2:
                self._sparks(surface, centre, size, now, index)

    def _outlined(self, image, width):
        """`image` (white letters) with a black outline `width` pixels round them, kept for the next frames."""
        key = ('outline', id(image), width)
        found = self._scaled.get(key)
        if found is None or found[0] is not image:
            # The outline follows the letters as drawn (their own thin dark edge included) from WORD_CUT's strength.
            black = silhouette(image, WORD_CUT)
            image_drawn = image
            out = pygame.Surface((image.get_width() + 2 * width, image.get_height() + 2 * width), pygame.SRCALPHA)
            for dx in range(-width, width + 1):
                for dy in range(-width, width + 1):
                    if dx * dx + dy * dy <= width * width:
                        out.blit(black, (width + dx, width + dy))
            out.blit(image_drawn, (width, width))
            found = self._scaled[key] = (image, out)
        return found[1]

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
        turn, into = divmod(played + 3000, TAUNT_EVERY_MS)     # the first at 6 s, then 15, 24 and 33
        if turn == 0 or into >= TAUNT_MS:                       # (turn 0 would flash for its last half second at the start)
            return
        text = taunts[(turn - 1) % len(taunts)]
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

