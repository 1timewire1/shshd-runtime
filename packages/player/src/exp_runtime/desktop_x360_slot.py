"""shshd-runtime: the X360 translations' slot machine drawn over the story's scene (x360_games.SlotMachine), with the art
of the X360 addon's skin (spec `slot`; tools/translate/x360_arena_art.py).

The places come from the prototype's own group (bubbles/minigames/slot_machine) as MS3 draws it at 1280 x 720, a little
larger and moved to fit the 3:4 frame: the five slots along the panel, the one in focus larger over its window, the clock
over the panel's right end, and the title above. Nothing here decides anything in the game."""
from . import graphics as pygame
from .desktop_nr_arena_x360 import BMFont, addon_skin, clock_face
from .x360_games import (BULB, CLOSING, CROSS, DURATION_MS, FLASH_MS, OFF, OPENING, OPENING_MS, QUESTION, READY, SLOTS,
                         TIME_UP)

FRAME = (768, 1024)
PANEL = (20, 590, 728, 328)
SLOT_X, SLOT_Y = (114, 246, 378, 511, 643), 768
ICON, ICON_FOCUS = 106, 132             # the slot's picture at 2.0 and, in focus, 2.5 (slot.OnMouseOver)
WINDOW = (120, 144)
CLOCK_CENTRE, CLOCK_SIZE, CLOCK_FACE = (705, 592), 92, 31
CLOCK_FACE_DROP = 3                     # the ring's centre sits below its picture's, under the crown
TITLE, TITLE_Y, TITLE_HEIGHT = 'Hit the light bulbs!', 556, 40
START_TEXT, START_Y, START_HEIGHT = 'Press OK to start', 480, 52   # Diss Practice's words, here for the clock's wait
TIME_UP_TEXT, TIME_UP_Y, TIME_UP_HEIGHT = "Time's Up!", 420, 70
TIME_UP_PULSE_MS = 800                  # bubbles/minigames/timeup: 1.5 to 2 and back, 0.4 s each way
ENTER_MS, ENTER_RISE = OPENING_MS, 420  # choice/enter_from_bottom
EXIT_MS = 300                           # choice/exit_fade
NAMES = {OFF: 'off', BULB: 'bulb', CROSS: 'cross', QUESTION: 'question'}


class X360SlotRenderer:
    # shshd-runtime (General's Aspect Ratio, owner 2026-11-12): in a frame taller than HD's the canvas goes on below
    # HD's 768 x 1024, as far as the frame's bottom once that 3:4 is centred (`canvas_size`), and the player sets it
    # against the frame's bottom (Desktop: story_below). What's drawn keeps its places; what rises in from below (the
    # slots' panel) comes up from the frame's edge. The gear is the player's, at the frame's bottom. Leash and the
    # puzzle draw the same way (their renderers are this one's); Diss Practice waits on its backgrounds (its own class).
    frame_units = (384, 512)

    @property
    def extended_below(self):
        return self.canvas_size() != FRAME

    def canvas_size(self):
        wide, tall = self.frame_units
        whole = round(FRAME[0] * tall / wide)
        if whole <= FRAME[1]:
            return FRAME
        return FRAME[0], whole - (whole - FRAME[1]) // 2

    def fresh_canvas(self):
        """The canvas at this frame's size (canvas_size), cleared by the caller."""
        size = self.canvas_size()
        if self.canvas is None or self.canvas.get_size() != size:
            self.canvas = pygame.Surface(size, pygame.SRCALPHA)
        return self.canvas

    hd_layer = True

    def __init__(self, resources):
        self.resources = resources
        self.canvas = None
        self._images = {}
        self._scaled = {}
        self._font = None
        self._face = (None, None)

    def _spec(self):
        return addon_skin(self.resources)

    def image(self, resource):
        found = self._images.get(resource)
        if found is None:
            import io
            found = self._images[resource] = pygame.image.load(io.BytesIO(self._spec()[1].read(resource)),
                                                               'x360.png').convert_alpha()
        return found

    def scaled(self, resource, size):
        key = (resource, size)
        found = self._scaled.get(key)
        if found is None:
            found = self._scaled[key] = pygame.transform.smoothscale(self.image(resource), size)
        return found

    def text(self, spec, words, height):
        key = (words, height)
        found = self._scaled.get(key)
        if found is None:
            if self._font is None:
                font = spec['font']
                self._font = BMFont(font, [self.image(page) for page in font['pages']])
            line = self._font.render([(words, None)])
            scale = height / self._font.line_height
            found = self._scaled[key] = pygame.transform.smoothscale(
                line, (max(1, round(line.get_width() * scale)), max(1, round(line.get_height() * scale))))
        return found

    def alpha(self, game):
        """The machine's fade as it closes (None: whole)."""
        if game.phase in (CLOSING, TIME_UP) and game.phase_ms < EXIT_MS:
            return max(0.0, game.phase_ms / EXIT_MS)
        return None

    def draw(self, session):
        game = session.engine.x360_slot
        spec = self._spec()[0]['slot']
        surface = self.fresh_canvas()
        surface.fill((0, 0, 0, 0))
        rise = 0
        if game.phase == OPENING:
            left = max(0, game.phase_ms) / ENTER_MS
            rise = round(ENTER_RISE * left * left)
        x, y, w, h = PANEL
        surface.blit(self.scaled(spec['panel'], (w, h)), (x, y + rise))
        for slot in range(SLOTS):
            self._slot(surface, spec, game, slot, rise)
        self._clock(surface, spec, game, rise)
        title = self.text(spec, TITLE, TITLE_HEIGHT)
        surface.blit(title, title.get_rect(center=(FRAME[0] // 2, TITLE_Y + rise)))
        if game.phase == READY:
            start = self.text(spec, START_TEXT, START_HEIGHT)
            surface.blit(start, start.get_rect(center=(FRAME[0] // 2, START_Y)))
        if game.phase == TIME_UP:
            into = (3000 - game.phase_ms) % TIME_UP_PULSE_MS / TIME_UP_PULSE_MS
            size = 1.5 + 0.5 * (1 - abs(1 - 2 * into))
            words = self.text(spec, TIME_UP_TEXT, TIME_UP_HEIGHT)
            big = pygame.transform.smoothscale(words, (round(words.get_width() * size / 1.5),
                                                       round(words.get_height() * size / 1.5)))
            surface.blit(big, big.get_rect(center=(FRAME[0] // 2, TIME_UP_Y)))

    def _slot(self, surface, spec, game, slot, rise):
        centre = (SLOT_X[slot], SLOT_Y + rise)
        focused = game.focus == slot + 1
        if focused:
            window = self.scaled(spec['window'], WINDOW)
            surface.blit(window, window.get_rect(center=centre))
        if game.flash_slot == slot and game.flash_ms > 0 and (FLASH_MS - game.flash_ms) // 50 % 2 == 0:
            return                              # the slot's three 0.05 s blinks as it is taken
        size = ICON_FOCUS if focused else ICON
        icon = self.scaled(spec['icons'][NAMES[game.shown[slot]]], (size, size))
        surface.blit(icon, icon.get_rect(center=centre))

    def _clock(self, surface, spec, game, rise):
        cx, cy = CLOCK_CENTRE[0], CLOCK_CENTRE[1] + rise
        step = round(game.clock_ms / DURATION_MS * 180)     # half-degree... 2 degrees a step: drawn once each
        if self._face[0] != step:
            self._face = (step, clock_face(step, CLOCK_FACE))
        face = self._face[1]
        surface.blit(face, face.get_rect(center=(cx, cy + CLOCK_FACE_DROP)))
        ring = self.scaled(spec['clock'], (CLOCK_SIZE, CLOCK_SIZE))
        surface.blit(ring, ring.get_rect(center=(cx, cy)))
