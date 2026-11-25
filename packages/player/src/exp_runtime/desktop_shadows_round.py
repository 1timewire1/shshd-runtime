"""shshd-runtime: Claire Hart: Secret in the Shadows' hidden-object round on screen (Claire Hart plan S3, step 4; reference/
Other Games/docs/CLAIRE_HART_SHADOWS_ROUNDS_PLAN.md). The rules are shadows_rounds.ShadowsRound's; this draws one and turns
taps, drags, the wheel, pinches and keys into its moves. Art from `ch2rounds` (its spec at 26000: the scenes, the HUD's
frames, fonts, sounds, the spotlight's overlay and How To Play). Nothing here decides anything in the game.

The scene itself (its view, framing R1, zoom, pan, the edge arrows, the composed picture and the pixel hit test) is the
Classic screen's (desktop_claire_round.ClaireRoundRenderer, whose scene code reads either add-on's scenes: Round Style).
The HUD is the sequel's, placed from build 232's own round scene (HogPTSDcomboScene, decoded by reference/Other Games/tools/
claire_hart_shadows_scene_tree.py; ENGINE 5.13) in its 800 x 600 design units across the frame's width, as Classic's is:
- the top bar: TIME and SCORE, Time Warp's stopwatch with its count, the combo meter x2-x6, and How To Play's "?" (the
  game's gear and close button there are the pause menu's here);
- the bottom bar: the pause menu's gear where the game's journal button was (owner, 2026-11-25: the case notes stay in the
  pause menu's Case Journal), "ITEMS FOUND n/12", the Gold Key's slot, the six names 3 x 2, and the crystal ball (the
  Psychic Sensor) with the magnifier (Hint) and eye (Clairvoyance) under it;
- the close-up (vignette, its backing and objects, the close button, the hotspot's glow after 6 finds), the multi-part note,
  the sensor's ring with its pulses and heartbeats, the Hint's markers, a spotlight round's overlay, "Not So Fast", and the
  summary ("Scene Cleared!", the rows, stars, CONTINUE) with Claire beside it;
- How To Play (owner, 2026-11-25): the game's own `howToHOG` tutorial behind the "?", Claire's lines over its pictures,
  the round's clock held while it shows.
Taller frames grow the bars as Classic's (R7): their heights and pieces, not their places across the width.
"""
import io
import math
import random as _random

from . import graphics as pygame
from . import shadows_rounds as sr
from .desktop_claire_round import ClaireRoundRenderer, clamp

ADDON, SPEC = 'ch2rounds', 26000
NO_OBJECT = sr.NO_OBJECT
DESIGN_WIDTH, DESIGN_HEIGHT = 800, 600
ROUND_HEIGHT = 600                          # a scene is 600 of the round's units tall (sceneloader)
# Colours (the scene's labels and the driver's)
TEAL, CREAM, WHITE = (18, 224, 188), (239, 236, 226), (255, 255, 255)
TEAL_BRIGHT = (27, 246, 208)
DARK_TEXT = (33, 33, 33)
KEY_TEXT = (143, 143, 143)
BUTTON_TINT = (226, 226, 226)
SCRIM_ALPHA, BACKING_ALPHA = 225, 225
# The top bar (UpperUI: y down from the frame's top)
TOP_HEIGHT = 60
TIME_LABEL, SCORE_LABEL = (-359.8, 13), (-275.6, 13)
TIME_DIGITS, SCORE_DIGITS = (-380.8, 35), (-302.1, 35.7)     # their left ends
LABEL_PX, DIGITS_PX = 16, 24                # RobotoSlab-Bold 32 and Roboto-Black 96 at 0.5 x 0.5
STOPWATCH = (-170, 26)
COMBO_LEFT, COMBO_Y = -140.4, 34.8          # the meter's left end and middle
COMBO_SIZE = (328, 26)
COMBO_FILL = (13.5, 292, 6)                 # the fill's left, length and height in the meter
COMBO_MARKS = {2: 0.0, 3: 0.35, 4: 0.65, 5: 0.87, 6: 1.0}
BULBS = {2: -5, 3: 105, 4: 193, 5: 258, 6: 301.5}            # from the fill's left
BULB_TEXT = {2: (8.9, 19), 3: (119.9, 19), 4: (208, 19), 5: (270.7, 19), 6: (315, 24)}   # from the meter's left, y up
HELP_AT = (373, 25.9)                       # "?" (Btn_HowToPlay) where the game's close button was: the bar's right end
ROUND_BUTTON = (35, 34)
# The bottom bar (LowerUI: y up from the frame's bottom)
BOTTOM_HEIGHT = 110
BACKING_CENTRE, BACKING_SIZE = -21, (542, 110)
ITEMS_HEADER, ITEMS_COUNT = (-225, 95), (-227, 66)
COUNT_PX = 24
KEY_SLOT, KEY_SLOT_SIZE = (-226, 27), (110, 44)
KEY_BACKING, KEY_TEXT_AT = (-32, 0.5), (18, 0)
NAME_COLUMNS, NAME_ROWS = (-85, 44, 174), (60, 28)          # (measured on chs_06: the list's layout)
NAME_PX, NAME_LINE, NAME_WIDTH = 15, 15.5, 87.5             # RobotoCondensed-Bold 30 at 0.5, wrapped at 175 x 0.5
FOUND_NAME_ALPHA = 90
SENSOR_AT, SENSOR_SIZE = (325, 87), 87
HINT_AT, EYE_AT, SMALL = (292.5, 28), (359.3, 28), 0.47
GEAR_AT, GEAR_SIZE = (-346, 46), (56, 54)                   # (the journal button's place; owner 2026-11-25)
COUNT_BUBBLE = (33, -33)                    # a power-up's count, from its button (y up), at the button's scale
# Growth in taller frames (R7): the bars' heights and pieces, from 3:4 to 20:9
TALL_TOP, TALL_BOTTOM = 1.12, 1.25
# The close-up
VIGNETTE_ALPHA = 200
PIP_OPEN_MS = 350
PIP_GLOW_MS = 2000                          # its hotspot's glow: 1 s in, 1 s out
CLOSE_SIZE = 28
# The multi-part note (ComponentObjectDialog: 60 below the frame's top, sliding down 0.3 s)
NOTE_Y, NOTE_SIZE, NOTE_TEXT_Y, NOTE_MS = 60, (487, 110), 80, 300
NOTE_TEXT = "It looks like there's another part to this object."
# The sensor's ring, in the round's units (hotcoldindicatorprefab in the effects layer at 0.781)
RING, RING_GLOW = 71, 107
RING_EASE_MS = 250
# The Hint's marker (powerup_Hint 136 in the hint layer at 0.781), its flight from the magnifier (1 s, cubic-out)
MARKER_SIZE, MARKER_FLIGHT_MS, MARKER_SPIN = 106 * 0.6, 1000, 90
# A find: the found sprite pops, then flies to its name (1.67 s, 130 up, 60 to the name's side)
FOUND_MS = 1670
TRAIL_RISE, TRAIL_SIDE = 130, 60
# The Gold Key: grows to 1.33 (0.47 s), settles (0.36 s), waits 1 s, flies to its slot (0.36 s)
KEY_GROW_MS, KEY_SETTLE_MS, KEY_WAIT_MS, KEY_FLY_MS = 470, 360, 1000, 360
# "Not So Fast" (inGameMessagePrefab)
SPAM_TITLE, SPAM_BODY = 'Not So Fast', 'Looking at too many objects at once confuses Claire!'
# The summary (GameOverUI), measured on chs_25 in design units from the frame's middle (y up)
CLEARED_MS, ROW_GAP_MS = 1500, 250
BOX_TOP, BOX_CENTRE, BOX_SIZE = 222.5, 58.5, (535, 420.7)
STARS_X, STARS_Y = (-44.7, 5.8, 56.8, 107.8, 159.3), 197.6
ROWS = (('Object Found', 'found', 132), ('Time Bonus', 'time_bonus', 90), ('Psychic Sensor Bonus', 'sensor_bonus', 46),
        ('Gold Key Bonus', 'key_bonus', 1), ('Perfect Score Bonus', 'perfect_bonus', -46))
ROW_LABEL_X, VALUE_X, ROW_PX = -139, 225, 19
TOTAL = ('TOTAL SCORE', -157, -100, 38)
CONTINUE_AT, CONTINUE_SIZE = (56, -229), (144, 36)
SUMMARY_SHADE = 150
# How To Play: an 800 x 600 stage across the frame; Claire at +-200 at 0.81, the box at its foot (dialogboxprefab)
TUTORIAL_CLAIRE_X, TUTORIAL_CLAIRE_SCALE, TUTORIAL_ENTER_MS = 200, 0.81, 1000
BOX, PAPER = (534, 113), (510, 80)
BOX_NAME_AT, BOX_NAME_PX = (-164, 110), 21
BOX_BODY_AT, BOX_BODY_WIDTH, BOX_BODY_PX, BOX_BODY_LINE = (-250, 75), 465, 18, 21
TYPE_RATE = 80                              # characters a second
# Sliced (9-patch) frames: their insets (left, top, right, bottom) from the UI atlases
SLICES = {'modal_bg': (9, 9, 9, 9), 'modal_backing_bodycopy': (11, 7, 11, 9),
          'cmp_chapterresult_backing_club': (0, 54, 0, 10), 'cmp_chapterresult_backing_scenecleared': (11, 37, 11, 37),
          'backing_chapterresult_clubupsell': (1, 1, 1, 1)}
# The sequel's sounds (ch2rounds' spec names them without the game's "Claire_Hart_2_")
SOUND_FIND, SOUND_FIND_X6 = 'GS_Object_1_Combo', 'GS_Object_6_Combo'
SOUND_NAME, SOUND_HINT, SOUND_WARP = 'GS_Object_In_Objectlist', 'GS_Hint_Power_Up', 'GS_Time_Wrap_Power_Up'
SOUND_SENSOR, SOUND_REFILL = 'GS_Psychic_Power_Up', 'GS_Psychic_Sensor_Refill'
SOUND_POPUP, SOUND_CLEARED, SOUND_ROW = 'GS_Pop_UP_Notification', 'GS_Scene_Cleard', 'GS_Line_Appearing_Chapter_Result'
SOUND_BUTTON, SOUND_SPEAKER = 'GES_Button_Click', 'DS_Focus_Different_Character'


class ShadowsRoundRenderer(ClaireRoundRenderer):
    ADDON = ADDON

    def __init__(self, resources):
        super().__init__(resources)
        self.pointer = None                 # the pointer's last place on the canvas (the ring and the spotlight follow it)
        self.ring_at = None                 # the sensor ring's place (touch: eased to a tap)
        self._ring_from = None              # (from, start clock) of the ring's ease
        self.ring = sr.SensorRing()
        self.light = sr.Spotlight()
        self.tutorial = None                # How To Play: {page, start clock, shown characters} while it shows
        self._pip_opened_at = None
        self._note_at = None
        self._key_found_at = None
        self._marker_since = {}             # object -> clock its marker was sent
        self._summary_at = None
        self._random = _random.Random(1)
        self._marks = (NO_OBJECT, (), False)

    # -- the add-on -----------------------------------------------------------------------------------------------------------
    def font(self, name, size):
        key = (name, size)
        if key not in self._fonts:
            self._fonts[key] = pygame.font.Font(io.BytesIO(self.addon(ADDON, self.spec()['fonts'][name])), max(6, size))
        return self._fonts[key]

    def hud_scaled(self, name, size, flip=False):
        """A HUD frame at `size` canvas pixels (cached)."""
        size = (max(1, round(size[0])), max(1, round(size[1])))
        key = ('hud scaled', name, size, flip)
        found = self._images.get(key)
        if found is None:
            picture = pygame.transform.smoothscale(self.hud(name), size)
            found = self._images[key] = pygame.transform.flip(picture, True, False) if flip else picture
        return found

    def scaled_now(self, name, size):
        """A HUD frame at a size that changes every frame (a pulse): not cached."""
        return pygame.transform.smoothscale(self.hud(name), (max(1, round(size[0])), max(1, round(size[1]))))

    def piece(self, name, centre, size, alpha=255, tint=None):
        picture = self.hud_scaled(name, size)
        if tint is not None or alpha != 255:
            picture = picture.copy()
            if tint is not None:
                picture.fill((*tint, 255), special_flags=pygame.BLEND_RGBA_MULT)
            if alpha != 255:
                picture.set_alpha(alpha)
        rect = picture.get_rect(center=(round(centre[0]), round(centre[1])))
        self.canvas.blit(picture, rect)
        return rect

    def sliced(self, name, rect, unit, alpha=255):
        """A 9-patch frame (SLICES) stretched over `rect`, its corners at `unit` canvas pixels a design unit."""
        key = ('sliced', name, rect.size, round(unit * 100), alpha)
        found = self._images.get(key)
        if found is None:
            art = self.hud(name)
            left, top, right, bottom = SLICES.get(name, (0, 0, 0, 0))
            w, h = art.get_size()
            found = pygame.Surface(rect.size, pygame.SRCALPHA)
            found.fill((0, 0, 0, 0))
            xs = (0, left, w - right, w)
            ys = (0, top, h - bottom, h)
            cl, ct, cr_, cb = (round(v * unit) for v in (left, top, right, bottom))
            cl, cr_ = min(cl, rect.width // 2), min(cr_, rect.width // 2)
            ct, cb = min(ct, rect.height // 2), min(cb, rect.height // 2)
            dxs = (0, cl, rect.width - cr_, rect.width)
            dys = (0, ct, rect.height - cb, rect.height)
            for i in range(3):
                for j in range(3):
                    sw, sh = xs[i + 1] - xs[i], ys[j + 1] - ys[j]
                    dw, dh = dxs[i + 1] - dxs[i], dys[j + 1] - dys[j]
                    if sw <= 0 or sh <= 0 or dw <= 0 or dh <= 0:
                        continue
                    part = art.subsurface((xs[i], ys[j], sw, sh))
                    found.blit(pygame.transform.smoothscale(part, (dw, dh)), (dxs[i], dys[j]))
            if alpha != 255:
                found.set_alpha(alpha)
            self._images[key] = found
        self.canvas.blit(found, rect.topleft)

    def say(self, text, font, size, colour, centre, scale, anchor='center', alpha=255):
        """Text in `font` at `size` design units (`scale` canvas pixels a unit)."""
        surface = self.font(font, round(size * scale)).render(str(text), True, colour)
        if alpha != 255:
            surface.set_alpha(alpha)
        rect = surface.get_rect(**{anchor: (round(centre[0]), round(centre[1]))})
        self.canvas.blit(surface, rect)
        return rect

    def wrapped(self, text, font, size, width):
        """`text`'s lines within `width` pixels."""
        lines, line = [], ''
        for word in str(text).split():
            trial = f'{line} {word}'.strip()
            if line and font.size(trial)[0] > width:
                lines.append(line)
                line = word
            else:
                line = trial
        if line:
            lines.append(line)
        return lines

    def sound_resource(self, name):
        return self.spec()['sounds'].get(name)

    # -- geometry -------------------------------------------------------------------------------------------------------------
    @property
    def kt(self):
        return self.k * self.grown(TALL_TOP)

    @property
    def kb(self):
        return self.k * self.grown(TALL_BOTTOM)

    def top(self, x, y):
        """A design point on the top bar (y down from the frame's top, under a phone's status bar)."""
        return self.canvas.get_width() / 2 + x * self.k, self.top_pad + y * self.kt

    def bottom(self, x, y):
        """A design point on the bottom bar (y up from the frame's foot)."""
        return self.canvas.get_width() / 2 + x * self.k, self.canvas.get_height() - y * self.kb

    def top_bar_bottom(self):
        return self.top_pad + TOP_HEIGHT * self.kt

    def bar_top(self):
        return self.canvas.get_height() - BOTTOM_HEIGHT * self.kb

    def round_unit(self, game=None):
        """Canvas pixels a round unit (the scene 600 tall), at the view's zoom."""
        return self.view.scale * self.view.scene[1] / ROUND_HEIGHT if self.view is not None else self.k

    def button_rect(self, centre, size):
        return pygame.Rect(round(centre[0] - size[0] / 2), round(centre[1] - size[1] / 2), round(size[0]), round(size[1]))

    def sensor_rect(self):
        size = SENSOR_SIZE * self.kb
        return self.button_rect(self.bottom(*SENSOR_AT), (size, size))

    def small_rect(self, at):
        size = SENSOR_SIZE * SMALL * self.kb
        return self.button_rect(self.bottom(*at), (size, size))

    def stopwatch_rect(self):
        size = SENSOR_SIZE * SMALL * self.kt
        return self.button_rect(self.top(*STOPWATCH), (size, size))

    def help_rect(self):
        return self.button_rect(self.top(*HELP_AT), (ROUND_BUTTON[0] * self.kt, ROUND_BUTTON[1] * self.kt))

    def gear_rect(self):
        return self.button_rect(self.bottom(*GEAR_AT), (GEAR_SIZE[0] * self.kb, GEAR_SIZE[1] * self.kb))

    def label_point(self, slot):
        return self.bottom(NAME_COLUMNS[slot % 3], NAME_ROWS[slot // 3])

    def label_rect(self, slot):
        x, y = self.label_point(slot)
        half_w, half_h = 64 * self.k, 16 * self.kb
        return pygame.Rect(round(x - half_w), round(y - half_h), round(2 * half_w), round(2 * half_h))

    def key_slot_point(self):
        return self.bottom(KEY_SLOT[0] + KEY_BACKING[0], KEY_SLOT[1] + KEY_BACKING[1])

    # -- the scene (the Classic screen's, with the sequel's kinds) -------------------------------------------------------------
    def kinds(self, game):
        return game.kinds

    def scene_state(self, game):
        return (len(game.found), tuple(game.collecting), game.key_found_ms >= 0)

    def in_scene(self, game, index):
        """Drawn (and tappable) in the scene: not found, not a multi-part object's whole (it has no sprite there), not a part
        being collected (its found sprite shows), not a close-up object (in the close-up), the Gold Key until found."""
        kind = game.kinds[index]
        if kind == sr.GOLD_KEY:
            return game.key_found_ms < 0
        if kind in (sr.WHOLE, sr.CLOSE_UP) or index in game.collecting:
            return False
        if kind == sr.PART:
            whole = next((w for w, ps in game.parts.items() if index in ps), None)
            return whole is None or whole not in game.found
        return index not in game.found

    def scene_picture(self, game):
        """The Classic screen's composition, with the close-up's hotspot (its cutout) drawn into the scene."""
        key = (self.scene_addon(game), game.scene, self.scene_state(game))
        if self._scene != key:
            super().scene_picture(game)
            close_up = self.close_up(game)
            if close_up is not None:
                number, _, _, left, top = close_up['cutout']
                self._composed.blit(self.sprite(game, number), (left, top))
        return self._composed

    def close_up(self, game):
        entry = self.scene_entry(game)
        return entry.get('close_up') if sr.CLOSE_UP in game.kinds else None

    def sprite_box(self, game, obj):
        """An object's sprite (normal, else found) as (centre x, centre y, width, height) in the scene's pixels."""
        normal, found, _ = self.objects(game)[obj]
        sprite = normal or found
        return sprite[3] + sprite[1] / 2, sprite[4] + sprite[2] / 2, sprite[1], sprite[2]

    def pip_map(self, game):
        """The open close-up on the canvas: (its backing's rect, canvas pixels a scene pixel, the backing's top left in the
        scene). At the scene's own scale where it fits the play area between the bars (as the game's 4:3 frame shows
        it); in a narrower frame, made smaller to fit and centred there (its backing is wider than a 3:4 frame). It
        opens from 0.975 of its size (0.35 s, quint-out)."""
        _, w, h, left, top = self.close_up(game)['backing']
        rect = self.scene_rect((left, top, w, h))
        width = self.canvas.get_width()
        area = pygame.Rect(0, round(self.top_bar_bottom()), width, round(self.bar_top() - self.top_bar_bottom()))
        room = area.inflate(-round(2 * CLOSE_SIZE * self.k), -round(2 * CLOSE_SIZE * self.k))
        if rect.width > room.width or rect.height > room.height or not area.contains(rect):
            fit = min(room.width / rect.width, room.height / rect.height, 1.0)
            rect = pygame.Rect(0, 0, round(rect.width * fit), round(rect.height * fit))
            rect.center = room.center
        if self._pip_opened_at is not None:
            t = clamp((self.clock - self._pip_opened_at) / PIP_OPEN_MS)
            grow = 0.975 + 0.025 * (1 - (1 - t) ** 5)
            rect = rect.inflate(round(rect.width * (grow - 1)), round(rect.height * (grow - 1)))
        return rect, rect.width / w, (left, top)

    def pip_rect(self, game):
        return self.pip_map(game)[0]

    def in_pip(self, game, obj):
        return game.pip_open and game.kinds[obj] == sr.CLOSE_UP and self.close_up(game) is not None

    def to_canvas(self, game, obj, sx, sy):
        """Scene point (sx, sy) on the canvas: through the open close-up for one of its objects, else the view."""
        if self.in_pip(game, obj):
            rect, scale, (left, top) = self.pip_map(game)
            return rect.x + (sx - left) * scale, rect.y + (sy - top) * scale
        return self.view.to_canvas(sx, sy)

    def to_scene(self, game, obj, x, y):
        """Canvas point (x, y) in the scene, as `to_canvas` places object `obj` (the sensor's distance to a close-up's object
        is measured within the close-up, at the scene's scale, as the game's)."""
        if self.in_pip(game, obj):
            rect, scale, (left, top) = self.pip_map(game)
            return left + (x - rect.x) / scale, top + (y - rect.y) / scale
        return self.view.to_scene(x, y)

    def pip_spot(self, game, sprite):
        """A close-up object's sprite ([number, w, h, left, top] in the scene) on the canvas, while the close-up is open."""
        rect, scale, (left, top) = self.pip_map(game)
        _, w, h, x, y = sprite
        return pygame.Rect(round(rect.x + (x - left) * scale), round(rect.y + (y - top) * scale), max(1, round(w * scale)),
                           max(1, round(h * scale)))

    def close_rect(self, game):
        rect = self.pip_rect(game)
        size = round(CLOSE_SIZE * self.k * 1.4)
        return pygame.Rect(rect.right - size // 2 - 2, rect.top - size // 2 + 2, size, size)

    # -- a frame -----------------------------------------------------------------------------------------------------------
    def draw_game(self, game, elapsed_ms=0):
        self.clock += elapsed_ms
        size = self.canvas_size()
        if self.canvas is None or self.canvas.get_size() != size:
            self.canvas = pygame.Surface(size).convert()
            self._scaled = None
        if self.held and self.view is not None:
            self.view.pan(-self.held * 900 * elapsed_ms / 1000, 0)
            if not self.arrow_shown(self.held):
                self.held = 0
        if self.tutorial is not None:
            self.draw_tutorial(elapsed_ms)
            return
        self.start_effects(game)
        self.sound_cues(game)
        self.follow_marks(game)
        self.step_ring(game, elapsed_ms)
        self.draw_scene(game)
        self.draw_glow(game)
        self.draw_collecting(game)
        if game.pip_open and self.close_up(game) is not None:
            self.draw_pip(game)
        self.draw_key(game, in_scene=True)
        self.draw_found(game)
        self.draw_markers(game)
        if game.spotlight:
            self.draw_spotlight(game, elapsed_ms)
        if game.sensor_on:
            self.draw_ring(game)
        self.draw_note(game)
        self.draw_top(game)
        self.draw_bottom(game)
        self.draw_key(game, in_scene=False)
        if not game.pip_open:
            self.draw_arrows()
        if game.lock_ms:
            self.draw_spam_popup()
        if game.over:
            self.draw_summary(game)

    def preload_steps(self, game):
        yield from super().preload_steps(game)
        self.spec()['fonts']
        yield

    # -- sounds and effects -----------------------------------------------------------------------------------------------
    def sound_cues(self, game):
        now = dict(found=len(game.found), multiplier=game.multiplier, names=tuple(game.slots), markers=len(game.markers),
                   warp=game.time_warp, lock=bool(game.lock_ms), over=game.over, sensor=game.sensor_on,
                   ready=game.sensor_ready, collecting=len(game.collecting), key=game.key_found_ms >= 0,
                   to_find=game.to_find, pip=game.pip_open)
        was, self._was = self._was, now
        if was is None:
            return
        if now['found'] > was['found'] or (now['key'] and not was['key']):
            self.sounds.append(SOUND_FIND_X6 if now['multiplier'] == sr.MAX_MULTIPLIER else SOUND_FIND)
        if now['collecting'] > was['collecting']:
            self.sounds.append(SOUND_FIND)
            self._note_at = self.clock if was['collecting'] == 0 else self._note_at
            if was['collecting'] == 0:
                self.sounds.append(SOUND_POPUP)
        if now['collecting'] == 0:
            self._note_at = None
        if any(o != NO_OBJECT and o != before for o, before in zip(now['names'], was['names'])):
            self.sounds.append(SOUND_NAME)
        if now['markers'] > was['markers'] or now['to_find'] > was['to_find']:
            self.sounds.append(SOUND_HINT)
        if now['to_find'] > was['to_find']:
            self._expanded_at = self.clock              # (Clairvoyance's six more: the count grows and shrinks)
        if now['warp'] and not was['warp']:
            self.sounds.append(SOUND_WARP)
        if now['sensor'] and not was['sensor']:
            self.sounds.append(SOUND_SENSOR)
            self.ring = sr.SensorRing()
            if self.ring_at is None:
                self.ring_at = self.pointer or (self.canvas.get_width() / 2, self.canvas.get_height() / 2)
        if now['ready'] and not was['ready'] and not now['sensor'] and game.sensor_uses:
            self.sounds.append(SOUND_REFILL)
        if now['lock'] and not was['lock']:
            self.sounds.append(SOUND_POPUP)
        if now['over'] and not was['over']:
            self.sounds.append(SOUND_CLEARED)
            self._summary_at = self.clock
        if now['pip'] and not was['pip']:
            self._pip_opened_at = self.clock
        if now['key'] and not was['key']:
            self._key_found_at = self.clock

    def start_effects(self, game):
        if self._seen_found is None or self._seen_found[0] is not game:
            self._seen_found = (game, len(game.found))
            self.effects.clear()
            self._marker_since.clear()
            self._summary_at = self.clock if game.over else None
            self._key_found_at = None
            self._pip_opened_at = None
        self._seen_found = (game, len(game.found))
        for obj in game.markers:
            self._marker_since.setdefault(obj, self.clock)
        for obj in list(self._marker_since):
            if obj not in game.markers:
                del self._marker_since[obj]

    def follow_marks(self, game):
        """The sensor and the Hint reset the zoom to 1x (ENGINE 5.3) and bring their object into view; an opened close-up is
        brought into view."""
        marks = (game.sensor_target if game.sensor_on else NO_OBJECT, tuple(game.markers), game.pip_open)
        if self.view is not None and marks != self._marks:
            old = self._marks if isinstance(self._marks, tuple) and len(self._marks) == 3 else (NO_OBJECT, (), False)
            target = None
            if marks[0] != NO_OBJECT and old[0] == NO_OBJECT:
                self.view.zoom = 1.0                # (the sensor resets the zoom, but where to look is the player's)
                self.view.clamp()
                self._scaled = None
            new_markers = [o for o in marks[1] if o not in old[1]]
            if new_markers:
                target = new_markers[-1]
            if target is not None:
                parts = game.parts.get(target)
                obj = parts[0] if parts else target
                if game.kinds[obj] != sr.CLOSE_UP:
                    self.view.zoom = 1.0
                    cx, cy, _, _ = self.sprite_box(game, obj)
                    self.view.centre_on(cx, cy)
                    self._scaled = None
            if marks[2] and not old[2] and self.close_up(game) is not None:
                _, w, h, left, top = self.close_up(game)['backing']
                self.view.zoom = 1.0
                self.view.centre_on(left + w / 2, top + h / 2)
                self._scaled = None
        self._marks = marks

    @property
    def zoom_locked(self):
        """The sensor locks the zoom while it runs (ENGINE 5.3)."""
        game = self._seen_found[0] if self._seen_found else None
        return bool(game is not None and game.sensor_on)

    # -- the scene's extras -----------------------------------------------------------------------------------------------
    def draw_glow(self, game):
        """The close-up hotspot's glow, pulsing after 6 finds until it's opened."""
        close_up = self.close_up(game)
        if close_up is None or not game.pip_glow or not close_up.get('glow'):
            return
        number, w, h, left, top = close_up['glow']
        phase = (self.clock % PIP_GLOW_MS) / PIP_GLOW_MS
        alpha = round(255 * (phase * 2 if phase < 0.5 else 2 - phase * 2))
        rect = self.scene_rect((left, top, w, h))
        picture = pygame.transform.smoothscale(self.sprite(game, number), rect.size)
        picture.set_alpha(alpha)
        self.canvas.blit(picture, rect)

    def draw_collecting(self, game):
        """A multi-part object's parts collected so far: their found sprites in place."""
        objects = self.objects(game)
        for obj in game.collecting:
            _, found, _ = objects[obj]
            number, w, h, left, top = found
            rect = self.scene_rect((left, top, w, h))
            self.canvas.blit(pygame.transform.smoothscale(self.sprite(game, number), rect.size), rect)

    def draw_pip(self, game):
        """The open close-up: the vignette over the scene, its backing, its objects not yet found, the close button."""
        shade = pygame.Surface(self.canvas.get_size(), pygame.SRCALPHA)
        shade.fill((0, 0, 0, VIGNETTE_ALPHA))
        self.canvas.blit(shade, (0, 0))
        number = self.close_up(game)['backing'][0]
        rect = self.pip_rect(game)
        self.canvas.blit(pygame.transform.smoothscale(self.sprite(game, number), rect.size), rect)
        objects = self.objects(game)
        for index, kind in enumerate(game.kinds):
            if kind != sr.CLOSE_UP or index in game.found or objects[index][0] is None:
                continue
            spot = self.pip_spot(game, objects[index][0])
            self.canvas.blit(pygame.transform.smoothscale(self.sprite(game, objects[index][0][0]), spot.size), spot)
        button = self.close_rect(game)
        self.piece('btn_secondary_round', button.center, button.size, tint=(172, 172, 172))
        self.piece('icn_close', button.center, (button.width * 15 / 28, button.height * 15 / 28), tint=BUTTON_TINT)

    def draw_key(self, game, in_scene):
        """The Gold Key's find: it grows to 1.33 and settles where it was, waits, then flies into its slot (drawn over the
        bottom bar for its last flight: `in_scene` False)."""
        if game.key == NO_OBJECT or self._key_found_at is None:
            return
        age = self.clock - self._key_found_at
        flying = KEY_GROW_MS + KEY_SETTLE_MS + KEY_WAIT_MS
        if age >= flying + KEY_FLY_MS or (age >= flying) == in_scene:
            return
        _, found, _ = self.objects(game)[game.key]
        number, w, h, left, top = found
        start = self.view.to_canvas(left + w / 2, top + h / 2)
        if age < KEY_GROW_MS:
            grow = 1 + 0.33 * (age / KEY_GROW_MS)
        elif age < KEY_GROW_MS + KEY_SETTLE_MS:
            grow = 1.33 - 0.33 * ((age - KEY_GROW_MS) / KEY_SETTLE_MS)
        else:
            grow = 1.0
        centre = start
        if age >= flying:
            t = (age - flying) / KEY_FLY_MS
            end = self.key_slot_point()
            centre = (start[0] + (end[0] - start[0]) * t, start[1] + (end[1] - start[1]) * t)
            grow *= 1 - 0.6 * t
        size = (max(1, round(w * self.view.scale * grow)), max(1, round(h * self.view.scale * grow)))
        picture = pygame.transform.smoothscale(self.sprite(game, number), size)
        self.canvas.blit(picture, picture.get_rect(center=(round(centre[0]), round(centre[1]))))

    def draw_found(self, game):
        """A find: its found sprite pops where it was, then flies to its name along a Catmull-Rom curve, sparkling."""
        objects = self.objects(game)
        for obj, left in game.leaving:
            age = sr.FOUND_MS + sr.NAME_GAP_MS - left
            if age >= FOUND_MS or obj not in game.slots:
                continue
            _, found, _ = objects[obj]
            number, w, h, x, y = found
            start = self.view.to_canvas(x + w / 2, y + h / 2)
            end = self.label_point(game.slots.index(obj))
            side = TRAIL_SIDE if end[0] > start[0] else -TRAIL_SIDE
            middle = (start[0] + side * self.k, start[1] - TRAIL_RISE * self.k)
            t = age / FOUND_MS
            pop = 1 + 0.15 * math.sin(math.pi * min(1, t * 4)) if t < 0.25 else 1.0
            eased = 0 if t < 0.2 else (t - 0.2) / 0.8
            cx, cy = self.catmull_rom((start, middle, end), eased) if eased else start
            shrink = 1 - 0.7 * eased
            size = (max(1, round(w * self.view.scale * pop * shrink)), max(1, round(h * self.view.scale * pop * shrink)))
            picture = pygame.transform.smoothscale(self.sprite(game, number), size)
            if eased > 0.8:
                picture.set_alpha(round(255 * (1 - (eased - 0.8) / 0.2)))
            self.canvas.blit(picture, picture.get_rect(center=(round(cx), round(cy))))
            if eased:
                for n in range(1, 6):
                    back = max(0.0, eased - n * 0.03)
                    sx, sy = self.catmull_rom((start, middle, end), back)
                    spark = self.hud_scaled('vfx_glowDot', ((22 - 3 * n) * self.k, (22 - 3 * n) * self.k))
                    self.canvas.blit(spark, spark.get_rect(center=(round(sx), round(sy))))

    def draw_markers(self, game):
        """The Hint's markers: each flies from the magnifier (1 s, cubic-out), then spins and pulses on its object (every
        part of a multi-part object) until it's found."""
        u = self.round_unit()
        for obj, since in self._marker_since.items():
            targets = game.parts.get(obj) or [obj]
            for target in targets:
                if target in game.found or target in game.collecting:
                    continue
                if game.kinds[target] == sr.CLOSE_UP and not game.pip_open:
                    continue
                cx, cy, _, _ = self.sprite_box(game, target)
                _, _, hint = self.objects(game)[target]
                end = self.to_canvas(game, target, cx + hint[0], cy - hint[1])
                age = self.clock - since
                if age < MARKER_FLIGHT_MS:
                    t = 1 - (1 - age / MARKER_FLIGHT_MS) ** 3
                    start = self.small_rect(HINT_AT).center
                    centre = (start[0] + (end[0] - start[0]) * t, start[1] + (end[1] - start[1]) * t)
                else:
                    centre = end
                pulse = 1 + 0.08 * math.sin(self.clock / 160)
                size = MARKER_SIZE * u * pulse
                picture = pygame.transform.rotozoom(self.scaled_now('powerup_Hint', (size, size)),
                                                    -(self.clock * MARKER_SPIN / 1000) % 360, 1)
                self.canvas.blit(picture, picture.get_rect(center=(round(centre[0]), round(centre[1]))))

    def step_ring(self, game, elapsed_ms):
        """The sensor's ring: it follows the pointer (a tap moves it, easing 0.25 s), its feel from its distance to the
        target (shadows_rounds.SensorRing), a heartbeat a pulse."""
        if not game.sensor_on or self.view is None:
            self.ring_at = None
            return
        if self._ring_from is not None:
            (fx, fy), (tx, ty), start = self._ring_from
            t = clamp((self.clock - start) / RING_EASE_MS)
            eased = 1 - (1 - t) ** 3
            self.ring_at = (fx + (tx - fx) * eased, fy + (ty - fy) * eased)
            if t >= 1:
                self._ring_from = None
        elif self.pointer is not None:
            self.ring_at = self.pointer
        if self.ring_at is None:
            self.ring_at = (self.canvas.get_width() / 2, self.canvas.get_height() / 2)
        target = game.sensor_target
        if target == NO_OBJECT:
            return
        scale = ROUND_HEIGHT / self.view.scene[1]
        cx, cy, w, h = self.sprite_box(game, target)
        _, _, hint = self.objects(game)[target]
        point = self.to_scene(game, target, *self.ring_at)
        distance = sr.sensor_distance((cx * scale, cy * scale, w * scale, h * scale), (hint[0] * scale, -hint[1] * scale),
                                      (point[0] * scale, point[1] * scale))
        for beat in self.ring.step(elapsed_ms / 1000, distance):
            self.sounds.append(sr.SENSOR_SOUNDS[beat])

    def move_ring(self, x, y):
        """A tap or drag on touch: the ring eases there (0.25 s)."""
        if self.ring_at is not None:
            self._ring_from = (self.ring_at, (x, y), self.clock)
        self.pointer = (x, y)

    def draw_ring(self, game):
        if self.ring_at is None:
            return
        u = self.round_unit()
        pulses, strength, colour, opacity, outer_opacity, _, _, near = self.ring.feel
        pulse = max(0.85, min(1.35, self.ring.goal))
        centre = (round(self.ring_at[0]), round(self.ring_at[1]))
        glow = self.scaled_now('cmp_powerUp_HotCold_targetglow', (RING_GLOW * u * pulse, RING_GLOW * u * pulse))
        glow.fill((*colour, 255), special_flags=pygame.BLEND_RGBA_MULT)
        glow.set_alpha(round(opacity))
        self.canvas.blit(glow, glow.get_rect(center=centre))
        outer = RING * u * 1.5 * (1 + self.ring.outer) / 1.5
        picture = self.scaled_now('cmp_powerUp_HotCold_targetcircle_outer', (outer, outer))
        picture.set_alpha(round(outer_opacity))
        self.canvas.blit(picture, picture.get_rect(center=centre))
        ring = self.scaled_now('cmp_powerUp_HotCold_targetcircle', (RING * u * pulse, RING * u * pulse))
        self.canvas.blit(ring, ring.get_rect(center=centre))
        if near:
            for n in range(6):
                angle = self.clock / 300 + n * math.pi / 3
                radius = RING * u * 0.55
                dot = self.hud_scaled('vfx_glowDot', (16 * u, 16 * u))
                self.canvas.blit(dot, dot.get_rect(center=(round(centre[0] + radius * math.cos(angle)),
                                                           round(centre[1] + radius * math.sin(angle)))))

    def draw_spotlight(self, game, elapsed_ms):
        """A spotlight round: the dark overlay with its soft hole, following the pointer on a spring with its jitter
        (shadows_rounds.Spotlight)."""
        u = self.round_unit()
        middle = self.view.to_canvas(self.view.scene[0] / 2, self.view.scene[1] / 2)
        pointer = self.pointer or middle
        self.light.step(elapsed_ms / 1000, ((pointer[0] - middle[0]) / u, (pointer[1] - middle[1]) / u),
                        self._random.random, touch=self.last_touch)
        size = (sr.SPOTLIGHT_SIZE[0] * u, sr.SPOTLIGHT_SIZE[1] * u)     # (its breathing scale left out: one size a zoom)
        key = ('spotlight', round(size[0]), round(size[1]))
        overlay = self._images.get(key)
        if overlay is None:
            picture = self.image(('spotlight',), lambda: self.addon(ADDON, self.spec()['spotlight']))
            overlay = self._images[key] = pygame.transform.smoothscale(picture, (round(size[0]), round(size[1])))
        centre = (middle[0] + self.light.x * u, middle[1] + self.light.y * u)
        rect = overlay.get_rect(center=(round(centre[0]), round(centre[1])))
        self.canvas.blit(overlay, rect)
        shade = (0, 0, 0)                   # (past the overlay's edges: as dark as its own)
        width, height = self.canvas.get_size()
        for area in ((0, 0, width, rect.top), (0, rect.bottom, width, height - rect.bottom),
                     (0, rect.top, rect.left, rect.height), (rect.right, rect.top, width - rect.right, rect.height)):
            if area[2] > 0 and area[3] > 0:
                self.canvas.fill(shade, area)

    last_touch = False                      # (the desktop sets it: the spotlight's spring is softer on touch)

    def light_point(self):
        """The spotlight's place on the canvas (the touch rule's indicator)."""
        u = self.round_unit()
        middle = self.view.to_canvas(self.view.scene[0] / 2, self.view.scene[1] / 2)
        return middle[0] + self.light.x * u, middle[1] + self.light.y * u

    def draw_note(self, game):
        """The multi-part note, sliding down from behind the top bar (0.3 s) while parts are being collected."""
        if not game.collecting or self._note_at is None:
            return
        t = clamp((self.clock - self._note_at) / NOTE_MS)
        drop = (1 - (1 - t) ** 3) * NOTE_Y + (1 - (1 - (1 - t) ** 3)) * (-NOTE_SIZE[1] / 2)
        centre = self.top(0, drop)
        self.piece('componentObject_messaging_bg', centre, (NOTE_SIZE[0] * self.kt, NOTE_SIZE[1] * self.kt))
        self.say(NOTE_TEXT, 'RobotoCondensed-Regular', 18, DARK_TEXT, (centre[0], centre[1] + (NOTE_TEXT_Y - NOTE_Y)
                                                                       * self.kt), self.kt)

    # -- the bars ----------------------------------------------------------------------------------------------------------
    def draw_top(self, game):
        width = self.canvas.get_width()
        kt, pad = self.kt, round(self.top_pad)
        scrim = self.hud_scaled('cmp_backing_scrim_top', (width, 167 * kt)).copy()
        scrim.set_alpha(SCRIM_ALPHA)
        self.canvas.blit(scrim, (0, pad))
        if pad:
            colour = self.hud('cmp_backing_Top').get_at((self.hud('cmp_backing_Top').get_width() // 2, 20))
            self.canvas.fill(colour[:3], (0, 0, width, pad))
        bar = self.hud_scaled('cmp_backing_Top', (width, TOP_HEIGHT * kt)).copy()
        bar.set_alpha(BACKING_ALPHA)
        self.canvas.blit(bar, (0, pad))
        self.say('TIME', 'RobotoSlab-Bold', LABEL_PX, TEAL, self.top(*TIME_LABEL), kt)
        self.say('SCORE', 'RobotoSlab-Bold', LABEL_PX, TEAL, self.top(*SCORE_LABEL), kt)
        seconds = game.seconds
        self.say(f'{seconds // 60:02d}:{seconds % 60:02d}', 'Roboto-Black', DIGITS_PX, CREAM, self.top(*TIME_DIGITS), kt,
                 anchor='midleft')
        self.say(str(game.find_points), 'Roboto-Black', DIGITS_PX, CREAM, self.top(*SCORE_DIGITS), kt, anchor='midleft')
        self.draw_powerup(sr.TIME_WARP, self.stopwatch_rect(), 'icn_timer', (12.4, 2.3), (44, 39), 2.2, kt,
                          glow=game.time_warp, game=game)
        self.draw_combo(game)
        rect = self.help_rect()
        self.piece('btn_secondary_round', rect.center, rect.size, tint=BUTTON_TINT)
        self.piece('icn_HowToPlay', rect.center, (16 * kt, 23 * kt), tint=BUTTON_TINT)

    def draw_combo(self, game):
        kt = self.kt
        left = self.top(COMBO_LEFT, COMBO_Y)
        x6 = game.multiplier == sr.MAX_MULTIPLIER and game.combo_running
        name = ('cmp_comboMeter_bg_Activatedpup' if game.time_warp else 'cmp_comboMeter_bg_Full' if x6
                else 'cmp_comboMeter_bg_idle')
        size = {'cmp_comboMeter_bg_Activatedpup': (332, 30), 'cmp_comboMeter_bg_Full': (338, 36)}.get(name, COMBO_SIZE)
        self.piece(name, (left[0] + 164.3 * self.k, left[1]), (size[0] * self.k, size[1] * kt))
        fill_left, length, height = COMBO_FILL
        outline = (left[0] + 14.5 * self.k, left[1] - 1 * kt)
        self.canvas.blit(self.hud_scaled('cmp_comboMeter_progressbar_black', (length * self.k, 9 * kt)),
                         (round(outline[0]), round(outline[1] - 4.5 * kt)))
        progress = 0.0
        if game.combo_running and game.multiplier >= 2:
            low = COMBO_MARKS[game.multiplier]
            high = COMBO_MARKS.get(game.multiplier + 1, 1.0)
            progress = 1.0 if game.multiplier == sr.MAX_MULTIPLIER else low + (high - low) * game.combo
        if progress > 0:
            bar = self.hud_scaled('cmp_comboMeter_progressbar', (length * self.k, height * kt))
            shown = max(1, round(length * self.k * progress))
            self.canvas.blit(bar, (round(left[0] + fill_left * self.k), round(left[1] - 1 * kt - height * kt / 2)),
                             pygame.Rect(0, 0, shown, bar.get_height()))
        for multiplier, at in BULBS.items():
            centre = (left[0] + (fill_left + at) * self.k, left[1] - 0.5 * kt)
            reached = game.combo_running and game.multiplier >= multiplier
            big = multiplier == sr.MAX_MULTIPLIER
            outline_name = 'cmp_comboMeter_progressbar_circle6x_black' if big else 'cmp_comboMeter_progressbar_circle_black'
            self.piece(outline_name, centre, ((26 if big else 17) * kt, (26 if big else 17) * kt))
            if reached:
                lit = 'cmp_comboMeter_progressbar_circle6x' if big else 'cmp_comboMeter_progressbar_circle'
                self.piece(lit, centre, ((22 if big else 13) * kt, (22 if big else 13) * kt))
            tx, ty = BULB_TEXT[multiplier]
            self.piece(f'cmp_comboMeter_{multiplier}x', (left[0] + tx * self.k, left[1] - ty * kt), (18 * kt, 14 * kt),
                       alpha=255 if reached else 120)
        if x6:
            self.piece('cmp_comboMeter_rays', (left[0] + 315 * self.k, left[1] + 1 * kt), (47 * kt, 41 * kt))

    def draw_powerup(self, powerup, rect, icon, offset, icon_size, icon_scale, unit, glow=False, game=None):
        """A power-up button (stopwatch, magnifier, eye): its round base, its icon (greyed when it can't be used), its count
        in a bubble (Once Each Round's 1; none for Unlimited)."""
        scale = rect.width / SENSOR_SIZE
        if glow:
            self.piece('btn_powerUp_HotCold_hover', rect.center, (109 * scale, 109 * scale))
        self.piece('btn_powerUp_HotCold_disable', rect.center, rect.size)
        usable = game.can_use(powerup)
        centre = (rect.centerx + offset[0] * scale, rect.centery - offset[1] * scale)
        size = (icon_size[0] * icon_scale * scale, icon_size[1] * icon_scale * scale)
        self.piece(f'{icon}_idle' if usable else f'{icon}_disabled', centre, size, alpha=255 if usable else 150)
        left = game.uses_left(powerup)
        if left:
            bubble = (rect.centerx + COUNT_BUBBLE[0] * scale, rect.centery - COUNT_BUBBLE[1] * scale)
            self.piece('cmp_quantity_backing_idle', bubble, (24 * 2.13 * scale, 24 * 2.13 * scale))
            self.say(left, 'Roboto-Black', 13, WHITE, bubble, unit)

    def draw_bottom(self, game):
        width, height = self.canvas.get_size()
        k, kb = self.k, self.kb
        scrim = self.hud_scaled('cmp_backing_scrim_bottom', (width, 177 * kb)).copy()
        scrim.set_alpha(SCRIM_ALPHA)
        self.canvas.blit(scrim, (0, round(height - 177 * kb)))
        left = width / 2 + (BACKING_CENTRE - BACKING_SIZE[0] / 2) * k
        backing = self.hud_scaled('cmp_backing_bottom', (BACKING_SIZE[0] * k, BACKING_SIZE[1] * kb)).copy()
        backing.set_alpha(BACKING_ALPHA)
        self.canvas.blit(backing, (round(left), round(height - BACKING_SIZE[1] * kb)))
        self.say('ITEMS FOUND', 'RobotoSlab-Bold', LABEL_PX, TEAL, self.bottom(*ITEMS_HEADER), kb)
        grow = 1.0
        if self._expanded_at is not None and self.clock - self._expanded_at < 850:
            grow = round(1 + 0.35 * math.sin(math.pi * (self.clock - self._expanded_at) / 850), 1)
        self.say(f'{game.found_count}/{game.to_find}', 'Roboto-Black', round(COUNT_PX * grow), WHITE,
                 self.bottom(*ITEMS_COUNT), kb)
        self.draw_key_slot(game)
        self.draw_names(game)
        gear = self.gear_rect()
        self.piece('btn_secondary_round', gear.center, gear.size, tint=BUTTON_TINT)
        self.piece('icn_Options', gear.center, (gear.width * 20 / 35 * 1.15, gear.height * 22 / 34 * 1.15), tint=BUTTON_TINT)
        self.draw_sensor(game)
        self.draw_powerup(sr.HINT, self.small_rect(HINT_AT), 'icn_hint', (3, 3), (39, 39), 2.12, kb, game=game)
        self.draw_powerup(sr.CLAIRVOYANCE, self.small_rect(EYE_AT), 'icn_clairvoyance', (-1, -6), (22, 34), 2.1, kb,
                          game=game)

    def draw_key_slot(self, game):
        if game.key == NO_OBJECT:
            return                              # (2 of the sequel's scenes, and Classic's under Round Style, have none)
        kb = self.kb
        centre = self.bottom(*KEY_SLOT)
        rect = self.button_rect(centre, (KEY_SLOT_SIZE[0] * self.k, KEY_SLOT_SIZE[1] * kb))
        self.sliced('backing_chapterresult_clubupsell', rect, kb, alpha=180)
        found = game.key_found_ms >= 0 and (self._key_found_at is None or self.clock - self._key_found_at
                                            >= KEY_GROW_MS + KEY_SETTLE_MS + KEY_WAIT_MS + KEY_FLY_MS)
        slot = self.key_slot_point()
        self.piece('cmp_backing_premiumobject', slot, (36 * kb, 36 * kb))
        self.piece('icn_premiumObject_found', slot, (33 * kb, 33 * kb), tint=None if found else (0, 0, 0))
        self.say(' Gold Key ', 'RobotoCondensed-Bold', 15, CREAM if found else KEY_TEXT,
                 self.bottom(KEY_SLOT[0] + KEY_TEXT_AT[0], KEY_SLOT[1] + KEY_TEXT_AT[1]), kb)

    def draw_names(self, game):
        kb = self.kb
        font = self.font('RobotoCondensed-Bold', round(NAME_PX * kb))
        for slot, obj in enumerate(game.slots):
            if obj == NO_OBJECT:
                continue
            leaving = next((left for o, left in game.leaving if o == obj), None)
            alpha = 255 if leaving is None else FOUND_NAME_ALPHA if leaving >= sr.NAME_GAP_MS else round(
                FOUND_NAME_ALPHA * leaving / sr.NAME_GAP_MS)
            colour = TEAL if game.extra[slot] else CREAM
            lines = self.wrapped(game.names[obj], font, NAME_PX, NAME_WIDTH * self.k * 1.45)
            x, y = self.label_point(slot)
            line = NAME_LINE * kb
            top = y - line * len(lines) / 2
            for n, text in enumerate(lines[:2]):
                surface = font.render(text, True, colour)
                if surface.get_width() > NAME_WIDTH * self.k * 1.5:
                    surface = pygame.transform.smoothscale(surface, (round(NAME_WIDTH * self.k * 1.5), surface.get_height()))
                surface.set_alpha(alpha)
                self.canvas.blit(surface, surface.get_rect(center=(round(x), round(top + line * (n + 0.5)))))

    def draw_sensor(self, game):
        """The crystal ball: its glow when ready, its green backing refilling while it cools down, the ball full or empty."""
        rect = self.sensor_rect()
        scale = rect.width / SENSOR_SIZE
        ready = game.sensor_ready
        if ready:
            pulse = 0.85 + 0.15 * math.sin(self.clock / 400)
            self.piece('btn_powerUp_HotCold_hover', rect.center, (109 * scale, 109 * scale), alpha=round(255 * pulse))
        self.piece('btn_powerUp_HotCold_disable', rect.center, rect.size)
        if game.sensor_cooldown_ms and not game.sensor_on:
            filled = 1 - game.sensor_cooldown_ms / sr.SENSOR_COOLDOWN_MS
            backing = self.hud_scaled('btn_powerUp_HotCold_greenbacking', (87 * 0.9 * scale, 87 * 0.9 * scale))
            shown = max(1, round(backing.get_height() * filled))
            area = pygame.Rect(0, backing.get_height() - shown, backing.get_width(), shown)
            box = backing.get_rect(center=rect.center)
            part = backing.subsurface(area).copy()
            part.set_alpha(200)
            self.canvas.blit(part, (box.x, box.bottom - shown))
        self.piece('icn_HotCold_idle' if ready else 'icn_HotCold_empty', rect.center, (60 * scale, 67 * scale))

    # -- pop-ups -----------------------------------------------------------------------------------------------------------
    def draw_spam_popup(self):
        width, height = self.canvas.get_size()
        shade = pygame.Surface((width, height), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 166))
        self.canvas.blit(shade, (0, 0))
        u = self.k * self.grown(1.2)
        centre = (width / 2, height / 2)
        rect = self.button_rect((centre[0], centre[1] + 4 * u), (422 * u, 209 * u))
        self.sliced('modal_bg', rect, u)
        self.say(SPAM_TITLE, 'RobotoSlab-Bold', 28, TEAL_BRIGHT, (centre[0], centre[1] - 76.45 * u), u)
        body = self.button_rect(centre, (400 * u, 100 * u))
        self.sliced('modal_backing_bodycopy', body, u, alpha=115)
        font = self.font('RobotoCondensed-Regular', round(18 * u))
        lines = self.wrapped(SPAM_BODY, font, 18, 380 * u)
        for n, text in enumerate(lines):
            self.say(text, 'RobotoCondensed-Regular', 18, CREAM,
                     (centre[0], centre[1] + (n - (len(lines) - 1) / 2) * 21 * u), u)

    def summary_unit(self):
        return self.k

    def summary_point(self, x, y):
        """A point of the summary's 800 x 600 design (y up from its middle), centred in the frame."""
        width, height = self.canvas.get_size()
        u = self.summary_unit()
        return width / 2 + x * u, height / 2 - y * u

    def continue_rect(self):
        u = self.summary_unit()
        return self.button_rect(self.summary_point(*CONTINUE_AT), (CONTINUE_SIZE[0] * u, CONTINUE_SIZE[1] * u))

    def summary_rects(self):
        return None, None, self.continue_rect()

    def draw_summary(self, game):
        """"Scene Cleared!", then the box: the stars, the rows one by one (0.25 s apart), the total, CONTINUE; Claire beside
        it (GameOverUI, the club layout: the Gold Key's row for everyone)."""
        if self._summary_at is None:
            self._summary_at = self.clock
        age = self.clock - self._summary_at
        u = self.summary_unit()
        width, height = self.canvas.get_size()
        shade = pygame.Surface((width, height), pygame.SRCALPHA)
        shade.fill((0, 0, 0, round(SUMMARY_SHADE * clamp(age / 400))))
        self.canvas.blit(shade, (0, 0))
        if age < CLEARED_MS:
            t = clamp(age / 300)
            centre = self.summary_point(-24.1 + 78, -5.8)
            band = self.button_rect(centre, (541 * u, max(2, 76 * u * t)))
            self.sliced('cmp_chapterresult_backing_scenecleared', band, u)
            if t >= 1:
                self.piece('chapterresult_text_scenecleared', self.summary_point(-24.1 - 50.5, -5.8), (325 * u, 37 * u))
            return
        age -= CLEARED_MS
        slide = 1 - (1 - clamp(age / 500)) ** 3
        size = (261 * u, 541 * u)
        left = self.summary_point(-400, -300)
        self.canvas.blit(self.hud_scaled('chapterresult_claire', size),
                         (round(left[0] - size[0] * (1 - slide)), round(left[1] - size[1])))
        box_left, box_top = self.summary_point(BOX_CENTRE - BOX_SIZE[0] / 2, BOX_TOP)
        box = pygame.Rect(round(box_left), round(box_top), round(BOX_SIZE[0] * u), round(BOX_SIZE[1] * u))
        self.sliced('cmp_chapterresult_backing_club', box, u)
        s = game.summary()
        for i, x in enumerate(STARS_X):
            centre = self.summary_point(x, STARS_Y)
            star = self.hud_scaled('icn_chapterresult_Star', (31 * u, 30 * u))
            dim = star.copy()
            dim.fill((40, 60, 55, 200), special_flags=pygame.BLEND_RGBA_MULT)
            rect = star.get_rect(center=(round(centre[0]), round(centre[1])))
            self.canvas.blit(dim, rect)
            filled = clamp(s['half_stars'] / 2 - i)
            if filled > 0:
                self.canvas.blit(star, rect, pygame.Rect(0, 0, round(rect.width * filled), rect.height))
        shown = int(age // ROW_GAP_MS)
        if shown > getattr(self, '_rows_sounded', -1) and shown <= len(ROWS) + 1:
            self._rows_sounded = shown
            self.sounds.append(SOUND_ROW)
        for n, (label, key, y) in enumerate(ROWS):
            if n >= shown:
                break
            self.say(label, 'RobotoSlab-Bold', ROW_PX, TEAL_BRIGHT, self.summary_point(ROW_LABEL_X, y), u, anchor='midleft')
            self.say(s[key], 'Roboto-Bold', ROW_PX, CREAM, self.summary_point(VALUE_X, y), u)
        if shown > len(ROWS):
            label, x, y, px = TOTAL
            self.say(label, 'RobotoSlab-Bold', px, TEAL_BRIGHT, self.summary_point(x, y), u, anchor='midleft')
            self.say(s['total'], 'Roboto-Bold', px, CREAM, self.summary_point(VALUE_X, y), u)
        button = self.continue_rect()
        self.canvas.blit(self.hud_scaled('btn_primary_press' if self.pressed == 'continue' else 'btn_primary_idle',
                                         button.size), button)
        self.say('CONTINUE', 'Roboto-Black', 22, CREAM, button.center, u)

    def summary_ready(self):
        """Continue answers once the rows are all in."""
        return self._summary_at is not None and self.clock - self._summary_at >= CLEARED_MS

    # -- How To Play --------------------------------------------------------------------------------------------------------
    def has_tutorial(self):
        try:
            return bool(self.spec().get('tutorial'))
        except (ValueError, KeyError):
            return False

    def open_tutorial(self):
        if self.has_tutorial():
            self.tutorial = dict(page=0, start=self.clock, side=None, entered=self.clock)
            self.sounds.append(SOUND_BUTTON)

    def tutorial_tap(self):
        """A tap on How To Play: it finishes the line, else turns the page; after the last, it closes."""
        if self.tutorial is None:
            return
        pages = self.spec()['tutorial']['pages']
        page = pages[self.tutorial['page']]
        typed = (self.clock - self.tutorial['start']) * TYPE_RATE / 1000
        if typed < len(page['text']):
            self.tutorial['start'] = self.clock - len(page['text']) * 1000 / TYPE_RATE - 1
            return
        if self.tutorial['page'] + 1 >= len(pages):
            self.tutorial = None
            return
        self.tutorial['page'] += 1
        self.tutorial['start'] = self.clock

    def stage_unit(self):
        return self.k

    def stage_point(self, x, y):
        width, height = self.canvas.get_size()
        return width / 2 + x * self.stage_unit(), height / 2 - y * self.stage_unit()

    def draw_tutorial(self, elapsed_ms):
        spec = self.spec()['tutorial']
        page = spec['pages'][self.tutorial['page']]
        u = self.stage_unit()
        self.canvas.fill((0, 0, 0))
        for name, x, y in page['sprites']:
            resource, w, h = spec['pictures'][name]
            picture = self.image(('tutorial', name), lambda r=resource: self.addon(ADDON, r))
            size = (round(w * u), round(h * u))
            key = ('tutorial scaled', name, size)
            scaled = self._images.get(key) or self._images.setdefault(key, pygame.transform.smoothscale(picture, size))
            self.canvas.blit(scaled, scaled.get_rect(center=tuple(round(v) for v in self.stage_point(x, y))))
        side = page['claire']
        if side != self.tutorial['side']:
            self.tutorial['side'], self.tutorial['entered'] = side, self.clock
        if side:
            resource, w, h = spec['claire']
            picture = self.image(('tutorial', 'claire'), lambda: self.addon(ADDON, resource))
            scale = TUTORIAL_CLAIRE_SCALE * u
            size = (round(w * scale), round(h * scale))
            flip = side == 'right'
            key = ('tutorial claire', size, flip)
            standing = self._images.get(key)
            if standing is None:
                standing = pygame.transform.smoothscale(picture, size)
                standing = self._images[key] = pygame.transform.flip(standing, True, False) if flip else standing
            sign = 1 if flip else -1
            t = clamp((self.clock - self.tutorial['entered']) / TUTORIAL_ENTER_MS)
            x = sign * (500 + (TUTORIAL_CLAIRE_X - 500) * (1 - (1 - t) ** 5))
            foot = self.stage_point(x, -300)
            self.canvas.blit(standing, standing.get_rect(midbottom=(round(foot[0]), round(foot[1]))))
        foot = self.stage_point(0, -300)
        box = pygame.Rect(0, 0, round(BOX[0] * u), round(BOX[1] * u))
        box.midbottom = (round(foot[0]), round(foot[1]))
        frame = self.hud_scaled('cmp_scriptBacking_dialog', box.size).copy()
        frame.set_alpha(204)
        self.canvas.blit(frame, box)
        paper = pygame.Rect(0, 0, round(PAPER[0] * u), round(PAPER[1] * u))
        paper.midbottom = box.midbottom
        self.canvas.blit(self.hud_scaled('cmp_scriptBacking_paper', paper.size), paper)
        name_at = (box.centerx + BOX_NAME_AT[0] * u, box.bottom - BOX_NAME_AT[1] * u)
        self.say(page['name'].upper(), 'RobotoSlab-Bold', BOX_NAME_PX, TEAL_BRIGHT, name_at, u, anchor='midtop')
        typed = int((self.clock - self.tutorial['start']) * TYPE_RATE / 1000)
        font = self.font('RobotoCondensed-Regular', round(BOX_BODY_PX * u))
        lines = self.wrapped(page['text'], font, BOX_BODY_PX, BOX_BODY_WIDTH * u)
        left, top = box.left + (BOX[0] / 2 + BOX_BODY_AT[0]) * u, box.bottom - BOX_BODY_AT[1] * u
        left_over = typed
        for n, line in enumerate(lines):
            shown = line[:max(0, left_over)]
            left_over -= len(line) + 1
            if shown:
                surface = font.render(shown, True, DARK_TEXT)
                self.canvas.blit(surface, (round(left), round(top + n * BOX_BODY_LINE * u)))

    # -- input --------------------------------------------------------------------------------------------------------------
    def objects_at(self, game, x, y):
        """The objects a tap at canvas (x, y) hits, topmost first: the Gold Key, the open close-up's objects, then the
        scene's (the Classic screen's pixel test)."""
        hits = []
        if game.pip_open and self.close_up(game) is not None:
            rect, scale, (left, top) = self.pip_map(game)
            sx, sy = left + (x - rect.x) / scale, top + (y - rect.y) / scale
            objects = self.objects(game)
            for index in reversed(range(len(objects))):
                if game.kinds[index] != sr.CLOSE_UP or index in game.found or objects[index][0] is None:
                    continue
                number, w, h, left, top = objects[index][0]
                if left <= sx < left + w and top <= sy < top + h:
                    sprite = self.sprite(game, number)
                    if self.alpha_hit(sprite, sx - left, sy - top):
                        hits.append(index)
        under = super().objects_at(game, x, y)
        key = game.key
        if key != NO_OBJECT and key in under:
            under.remove(key)
            hits.insert(0, key)
        return hits if game.pip_open else hits + under

    @staticmethod
    def alpha_hit(sprite, px, py):
        from . import claire_rounds as cr
        return cr.pixel_hit(lambda ax, ay: sprite.get_at((ax, ay))[3], sprite.get_width(), sprite.get_height(), px, py)

    def hotspot_hit(self, game, x, y):
        close_up = self.close_up(game)
        if close_up is None or not close_up.get('cutout'):
            return False
        number, w, h, left, top = close_up['cutout']
        sx, sy = self.view.to_scene(x, y)
        return left <= sx < left + w and top <= sy < top + h and self.alpha_hit(self.sprite(game, number), sx - left,
                                                                                 sy - top)

    def hit(self, game, x, y):
        """What a tap at canvas (x, y) means: ('tutorial',), ('continue',), ('help',), ('menu',), ('sensor',),
        ('powerup', name), ('arrow', -1|1), ('close_pip',), ('backing',), ('open_pip',), ('scene', [objects]), or None."""
        if self.tutorial is not None:
            return ('tutorial',)
        if game.over:
            return ('continue',) if self.continue_rect().collidepoint(x, y) and self.summary_ready() else None
        if y < self.top_bar_bottom():
            if self.help_rect().collidepoint(x, y):
                return ('help',)
            if self.stopwatch_rect().collidepoint(x, y):
                return ('powerup', sr.TIME_WARP)
            return None
        if self.sensor_rect().collidepoint(x, y):
            return ('sensor',)
        if self.small_rect(HINT_AT).collidepoint(x, y):
            return ('powerup', sr.HINT)
        if self.small_rect(EYE_AT).collidepoint(x, y):
            return ('powerup', sr.CLAIRVOYANCE)
        if self.gear_rect().collidepoint(x, y):
            return ('menu',)
        if y >= self.bar_top():
            return None
        for side, rect in zip((-1, 1), self.arrows()):
            if rect.collidepoint(x, y) and self.arrow_shown(side) and not game.pip_open:
                return ('arrow', side)
        if game.pip_open and self.close_up(game) is not None:
            if self.close_rect(game).collidepoint(x, y):
                return ('close_pip',)
            hits = self.objects_at(game, x, y)
            if hits:
                return ('scene', hits)
            return ('backing',) if self.pip_rect(game).collidepoint(x, y) else ('close_pip',)
        hits = self.objects_at(game, x, y)
        if not hits and self.hotspot_hit(game, x, y):
            return ('open_pip',)
        return ('scene', hits)

    def indicator(self):
        """The ring's or the light's last place on the canvas (the touch rule), or None."""
        game = self._seen_found[0] if self._seen_found else None
        if game is None:
            return None
        if game.sensor_on and self.ring_at is not None:
            return self.ring_at
        if game.spotlight and self.view is not None:
            return self.light_point()
        return None

    def touch_counts(self, x, y, drag):
        """The touch rule (plan S1): with the sensor or a spotlight on, a tap counts only near its indicator."""
        at = self.indicator()
        if at is None:
            return True
        u = self.round_unit()
        return sr.touch_counts((x / u, y / u), (at[0] / u, at[1] / u), drag / u)
