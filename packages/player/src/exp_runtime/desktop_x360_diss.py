"""shshd-runtime: Diss Practice drawn over the story's scene (x360_diss.DissPractice), with the X360 addon's skin (spec
`booth`; tools/translate/x360_arena_art.py).

The deck, digits and hit effects are the arena's X360 look's (desktop_x360_deck.py), with nothing of New Rules' panel. The
notes stand where the game's camera sees them on the record, with its depth, as the booth shot them; they keep facing the
camera as the record turns, as the X360's do. Their smoke, sparks and flames are drawn here, as they move. Nothing here
decides anything in the game.
"""
import math

from . import graphics as pygame
from .desktop_nr_arena_x360 import BMFont, addon_skin
from .desktop_x360_deck import FX, SCORE_BOX, X360Deck
from .x360_diss import (BAD, BLANK, COUNTDOWN, COUNTDOWN_MS, COUNTDOWN_STEPS_MS, CLOSING_MS, DOUBLE, ENDED, ELEMENTS, FIRE,
                        NOTE, REMIX, RUNNING, SPIN_DOWN, TUTORIAL, TUTORIAL_MS, arm_angle)
from .x360_games import CLOSING, OPENING, OPENING_MS, READY

FRAME = (768, 1024)
NOTE_PICTURE = {NOTE: 'note', BAD: 'bad', REMIX: 'swap', DOUBLE: 'double', FIRE: 'double'}
GROW_MS = 500                           # a new note scales in, as its effect's emitter has it
RISE = 420                              # the deck comes up from below, as the arena's does
FADE_MS = CLOSING_MS
START_TEXT, START_Y, START_HEIGHT, START_FONT = 'Press OK to start', 150, 30, 'badaboom_white'
POPUP_MS, POPUP_GROW_MS, POPUP_GONE_MS = 1100, 500, 900     # minigame/multiplier's script
POPUP_RED = (255, 0, 0)                 # me.msg.TextColor
COUNTDOWN_HEIGHT = 70                   # native pixels, at its smallest
# hud/tutorial: each card's final place (the group's own, as fractions of the frame's size from its centre), scaled to fit
# the 3:4 frame's width and stacked; where it comes from; and when, one a second. Then the prompt.
CARD_WIDTH = 610
CARDS = (('tutorial_1', (.06, -.27), (.06, 1.2), 0), ('tutorial_2', (-.05, -.03), (1.2, -.03), 1000),
         ('tutorial_3', (.03, .21), (.03, -1.2), 2000))
CARD_MOVE_MS, CARD_FADE_MS = 1000, 1500
TUTORIAL_PROMPT_MS = 4000
TUTORIAL_PROMPT_Y = 915
DANCE_WAIT_MS = 2000                    # the first practice's Wait(2), before Josh dances


class X360DissRenderer(X360Deck):
    hd_layer = True

    def __init__(self, resources):
        self.resources = resources
        self.canvas = None
        self.k = FRAME[1] / 652
        self._x360 = None
        self._images = {}
        self._scaled = {}
        self._seams = {}
        self._texts = {}
        self._fonts = {}
        self._notes = {}
        self.effects = []
        self.hits = []
        self.game = None
        self._shown_effects = []
        self._dancer = None
        self._dance_from = None
        self._josh_frame = None, None

    def x360(self):
        if self._x360 is None:
            found = addon_skin(self.resources)
            if found is None:
                raise ValueError('The X360 addon\'s skin is missing')
            self._x360 = found
        return self._x360

    def alpha(self, game):
        """The game's fade as it closes (None: whole)."""
        if game.phase == CLOSING:
            return max(0.0, game.phase_ms / FADE_MS)
        return None

    def _arm_frame(self, arm, now):
        """The tone arm's frame: the game's swing decides what it catches, so it's the game's angle that's drawn."""
        angle = arm_angle(self.game.arm_ms)
        return min(arm['frames'], key=lambda frame: abs(frame['angle'] - angle))

    # -- the camera --------------------------------------------------------------------------------------------
    def _project(self, x, z):
        """A point on the record over its centre, at the notes' height, in the booth's frame: (x, y, depth)."""
        booth = self.x360()[0]['booth']
        notes, camera = booth['notes'], booth['parts']['camera']
        wheel = notes['wheel']
        dx = wheel[0] + x * notes['out'] - camera[0]
        dy = wheel[1] + notes['height'] - camera[1]
        dz = wheel[2] + z * notes['out'] - camera[2]
        vx, vy, vz = self._to_camera(dx, dy, dz, camera)
        width, height = booth['frame']
        f = (height / 2) / math.tan(math.radians(camera[6]))
        return width / 2 + f * vx / vz, height / 2 - f * vy / vz, vz

    @staticmethod
    def _to_camera(x, y, z, camera):
        yaw, pitch, roll = (math.radians(a) for a in camera[3:6])
        x, z = x * math.cos(yaw) - z * math.sin(yaw), x * math.sin(yaw) + z * math.cos(yaw)
        y, z = y * math.cos(pitch) + z * math.sin(pitch), -y * math.sin(pitch) + z * math.cos(pitch)
        x, y = x * math.cos(roll) + y * math.sin(roll), -x * math.sin(roll) + y * math.cos(roll)
        return x, y, z

    def _native_point(self, x, z, dy):
        bx, by, depth = self._project(x, z)
        nx, ny, _, _ = self._to_native([bx, by, bx, by])
        return nx, ny + dy, depth

    # -- text --------------------------------------------------------------------------------------------------
    def _text(self, words, height, colour=None, font='badaboom'):
        key = (words, height, colour, font)
        found = self._texts.get(key)
        if found is None:
            spec = self.x360()[0]['fonts'][font]
            fkey = (font, colour)
            if fkey not in self._fonts:
                self._fonts[fkey] = BMFont(spec, [self.image(page) for page in spec['pages']], colour)
            face = self._fonts[fkey]
            line = face.render([(words.upper(), None)])
            scale = height * self.k / face.line_height
            found = self._texts[key] = pygame.transform.smoothscale(
                line, (max(1, round(line.get_width() * scale)), max(1, round(line.get_height() * scale))))
        return found

    # -- drawing -----------------------------------------------------------------------------------------------
    def draw(self, session):
        game = self.game = session.engine.x360_diss
        if self.canvas is None:
            self.canvas = pygame.Surface(FRAME, pygame.SRCALPHA)
        surface = self.canvas
        surface.fill((0, 0, 0, 0))
        now = game.now_ms
        self._josh(surface, game, session.engine.panel.background_id)
        if game.phase == TUTORIAL or (game.phase == OPENING and game.tutorial):
            self._tutorial(surface, game)
            return
        rise = 0
        if game.phase == OPENING:
            rise = RISE * (max(0, game.phase_ms) / OPENING_MS) ** 2
        parts = self.x360()[0]['booth']['parts']
        self._deck_piece(surface, self.image(parts['body']['id']), parts['body']['box'], 1, rise)
        self._deck_piece(surface, self.image(parts['record']['id']), parts['record']['box'], 1, rise)
        self._record_seams(surface, game, parts['seams'], 1, rise)
        self._deck_piece(surface, self.image(parts['spindle']['id']), parts['spindle']['box'], 1, rise)
        frame = self._arm_frame(parts['arm'], now)
        self._deck_piece(surface, self._arm_cell(parts['arm'], frame), frame['box'], 1, rise)
        self._notes_on_record(surface, game, now)
        self._hit_effects(surface, game, now)
        if game.phase in (RUNNING, SPIN_DOWN, ENDED, CLOSING):
            self._digits(surface, game, now)
        self._combo(surface, game, now)
        if game.phase == READY:
            words = self._text(START_TEXT, START_HEIGHT, font=START_FONT)
            surface.blit(words, words.get_rect(center=(FRAME[0] // 2, round(START_Y * self.k))))
        if game.phase == COUNTDOWN:
            self._countdown_digit(surface, game)

    def _dance_ms(self, game):
        """How far into his dance Josh is (None: he's still standing). The first practice has him stand until two seconds
        after its tutorial returns, as the countdown starts (episode3/practice_diss_001: Wait(2)), and the others start him
        at once, before theirs. Whether it's that round goes by the tutorial's being due, which is only different if the
        player skipped the morning's practice. Only the drawing depends on this, so it's kept here, not in the game."""
        if self._dancer is not game:
            self._dancer, self._dance_from = game, None if game.tutorial else 0
        if self._dance_from is None and game.phase not in (OPENING, TUTORIAL, READY):
            into = COUNTDOWN_MS - game.phase_ms if game.phase == COUNTDOWN else COUNTDOWN_MS
            self._dance_from = round(game.now_ms - into + DANCE_WAIT_MS)
        if self._dance_from is None or game.now_ms < self._dance_from:
            return None
        return game.now_ms - self._dance_from

    def _josh(self, surface, game, background):
        """Josh behind the deck (reference tools x360_dbpdance.py), the frames drawn one to one as the game's camera has him
        on the front's steps. The hallway's and his room's marks are off this frame's deck, so he stays on this side there,
        at the size their backgrounds need (the spec's `places`, by background: scale, about his feet, and where those
        are). The loop's jump where it wraps is the game's."""
        dance = self.x360()[0]['booth'].get('dance')
        if dance is None:                               # an addon from before he danced
            return
        ms = self._dance_ms(game)
        if ms is None:
            cell = dance['stand']
        else:
            frames = dance['frames']
            cell = frames[(ms % dance['period_ms']) * len(frames) // dance['period_ms']]
        x, y, _, _ = self._to_native(cell['box'])
        place = dance.get('places', {}).get(str(background))
        if place is None:
            image = self.image(dance['atlas']).subsurface(pygame.Rect(cell['rect']))
        else:
            left, top, width, height = self._to_native(dance['stand']['box'])
            feet_x, feet_y = left + width / 2, top + height
            to_x, to_y = place.get('feet', (feet_x, feet_y))
            x, y = to_x + (x - feet_x) * place['scale'], to_y + (y - feet_y) * place['scale']
            image = self._josh_scaled(dance, cell, place['scale'])
        surface.blit(image, (round(x * self.k), round(y * self.k)))

    def _josh_scaled(self, dance, cell, scale):
        """A frame at a place's size, kept for the draws it stays up: only the last one, as 171 of them would be a lot."""
        key = cell['rect'][0], cell['rect'][1], scale
        if self._josh_frame[0] != key:
            image = self.image(dance['atlas']).subsurface(pygame.Rect(cell['rect']))
            size = round(image.get_width() * scale), round(image.get_height() * scale)
            self._josh_frame = key, pygame.transform.smoothscale(image, size)
        return self._josh_frame[1]

    def _tutorial(self, surface, game):
        """hud/tutorial: the three cards come in, a second apart, then the prompt."""
        t = TUTORIAL_MS - game.phase_ms if game.phase == TUTORIAL else 0
        for name, place, start, at in CARDS:
            if t <= at:
                continue
            image = self.picture(name)
            into = min(1, (t - at) / CARD_MOVE_MS)
            x = start[0] + (place[0] - start[0]) * into
            y = start[1] + (place[1] - start[1]) * into
            size = (CARD_WIDTH, CARD_WIDTH * image.get_height() // image.get_width())
            card = self.scaled(image, size)
            fade = min(1, (t - at) / CARD_FADE_MS)
            if fade < 1:
                card = card.copy()
                card.set_alpha(round(255 * fade))
            surface.blit(card, card.get_rect(center=(round(FRAME[0] * (.5 + x)), round(FRAME[1] * (.5 + y)))))
        if t >= TUTORIAL_PROMPT_MS:
            words = self._text(START_TEXT, START_HEIGHT, font=START_FONT)
            grow = 1 + .1 * (1 - abs(1 - (t % 1000) / 500))     # B2Scale2ToAndBackLoop, (1,1) to (1.1,1.1) over 1 s
            size = (round(words.get_width() * grow), round(words.get_height() * grow))
            surface.blit(pygame.transform.smoothscale(words, size),
                         pygame.transform.smoothscale(words, size).get_rect(center=(FRAME[0] // 2, TUTORIAL_PROMPT_Y)))

    def _notes_on_record(self, surface, game, now):
        spec = self.x360()[0]['booth']['notes']
        u = self._deck()[0]
        per_pixel = u * self.x360()[0]['booth']['frame'][0] / spec['frame'][0]
        shown = []
        for index in range(len(ELEMENTS)):
            element = game.elements[index]
            if element['shown'] != BLANK:
                x, z = game.element_at(index)
                nx, ny, depth = self._native_point(x, z, 0)
                shown.append((depth, index, element, nx, ny))
        for depth, index, element, nx, ny in sorted(shown, key=lambda item: -item[0]):
            kind = element['shown']
            picture = spec['kinds'][NOTE_PICTURE[kind]]
            grow = min(1, max(0, now - element['born_ms']) / GROW_MS)
            scale = per_pixel * picture['depth'] / depth * grow * self.k
            if scale <= 0:
                continue
            image = self.image(picture['id'])
            size = (max(1, round(image.get_width() * scale)), max(1, round(image.get_height() * scale)))
            left = nx * self.k - picture['anchor'][0] * scale
            top = ny * self.k - picture['anchor'][1] * scale
            centre = (left + size[0] / 2, top + size[1] / 2)
            if kind == BAD:
                self._stink(surface, centre, size, now, index)
            elif kind == FIRE:
                self._flames(surface, centre, size, now, index)
            surface.blit(self.scaled(image, size), (round(left), round(top)))
            if kind in (DOUBLE, FIRE):
                self._sparks(surface, centre, size, now, index)

    # minigame/bps/bad_note_stink, hot_note_sparks and hot_note_flames, as their looks go: they only ever drift past.
    def _stink(self, surface, centre, size, now, index):
        sprites = self._sprites('fx_puff')
        for i in range(3):
            phase = (now / 1400 + i / 3 + index * .13) % 1
            side = max(1, round(size[0] * (.4 + .5 * phase)))
            image = self._tinted(sprites[i % len(sprites)], (150, 176, 128), side).copy()
            image.set_alpha(round(110 * (1 - phase)))
            surface.blit(image, image.get_rect(center=(round(centre[0] + (i - 1) * size[0] * .18),
                                                       round(centre[1] - size[1] * (.1 + .7 * phase)))))

    def _sparks(self, surface, centre, size, now, index):
        sprites = self._sprites('fx_spark')
        for i in range(3):
            phase = (now / 900 + i / 3 + index * .17) % 1
            side = max(1, round(size[0] * .16 * (1 - phase)))
            image = self._tinted(sprites[i % len(sprites)], (255, 190, 60), side, additive=True)
            x = centre[0] + size[0] * .55 * math.sin(i * 2.4 + index) * (.4 + phase)
            y = centre[1] - size[1] * .3 + size[1] * phase * phase
            surface.blit(image, image.get_rect(center=(round(x), round(y))), special_flags=pygame.BLEND_RGB_ADD)

    def _flames(self, surface, centre, size, now, index):
        sprites = self._sprites('fx_spark')
        for i in range(5):
            phase = (now / 500 + i / 5 + index * .11) % 1
            side = max(1, round(size[0] * (.55 - .35 * phase)))
            colour = (255, round(200 - 150 * phase), 20)
            image = self._tinted(sprites[i % len(sprites)], colour, side, additive=True)
            x = centre[0] + size[0] * .32 * math.sin(i * 1.9 + now / 170)
            y = centre[1] + size[1] * .3 - size[1] * .9 * phase
            surface.blit(image, image.get_rect(center=(round(x), round(y))), special_flags=pygame.BLEND_RGB_ADD)

    def _sprites(self, prefix):
        return [name for name in self.x360()[0]['pictures'] if name.startswith(prefix + '_')]

    def _hit_effects(self, surface, game, now):
        for effect in game.effects:
            if effect not in self._shown_effects:
                x, y, _ = self._native_point(effect[1], effect[2], 0)
                self._spawn(effect[0], x, y, effect[3])
        self._shown_effects = [list(e) for e in game.effects]
        self.effects = [e for e in self.effects if 0 <= now - e[3] < FX[e[0]]['life']]
        for effect in self.effects:
            self._draw_effect(surface, effect, now)

    def _digits(self, surface, game, now):
        digits = self.x360()[0]['booth']['digits']
        u, left, top = self._score_transform()
        for slot, ch in zip(digits['score'], f'{min(game.score, 999999):06d}'):
            box = digits['slots'][slot][int(ch)]['box']
            self._digit(surface, slot, int(ch), (SCORE_BOX[0] + (box[0] - left) * u, SCORE_BOX[1] + (box[1] - top) * u,
                                                  (box[2] - box[0]) * u, (box[3] - box[1]) * u), now)
        for slot, ch in zip(digits['time'], f'{max(0, game.total_time):02d}'):
            x, y, w, h = self._to_native(digits['slots'][slot][int(ch)]['box'])
            self._digit(surface, slot, int(ch), (x, y, w, h), now)

    def _combo(self, surface, game, now):
        """minigame/multiplier: the streak in red on the record's label, growing in, then gone."""
        streak, since = game.popup
        age = now - since
        if streak < 2 or not 0 <= age < POPUP_MS:
            return
        grow = min(1, .5 + .5 * age / POPUP_GROW_MS)
        words = self._text(f'x{streak}', 30, POPUP_RED)
        size = (max(1, round(words.get_width() * grow)), max(1, round(words.get_height() * grow)))
        image = pygame.transform.smoothscale(words, size)
        if age > POPUP_GONE_MS:
            image.set_alpha(round(255 * (POPUP_MS - age) / (POPUP_MS - POPUP_GONE_MS)))
        _, cx, cy, _, _, _, _ = self._deck()
        surface.blit(image, image.get_rect(center=(round(cx * self.k), round(cy * self.k))))

    def _countdown_digit(self, surface, game):
        """The HUD's 3, 2, 1, each scaling up and back."""
        elapsed = COUNTDOWN_MS - game.phase_ms
        digits = self.x360()[0]['booth']['digits']
        for n, length in zip((3, 2, 1), COUNTDOWN_STEPS_MS):
            if elapsed < length:
                grow = 1 + math.sin(math.pi * elapsed / length)
                ax, ay, aw, ah = digits['slots'][7][n]['rect']
                cell = self.image(digits['atlas']).subsurface(pygame.Rect(ax, ay, aw, ah))
                h = COUNTDOWN_HEIGHT * grow
                _, cx, cy, _, _, _, _ = self._deck()
                self.blit(surface, cell, cx, cy - 20, h * aw / ah, h, anchor='midbottom')
                return
            elapsed -= length
