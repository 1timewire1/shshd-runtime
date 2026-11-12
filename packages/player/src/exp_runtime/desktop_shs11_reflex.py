"""shshd-runtime: SHS '11's Reflex drawn over the story's scene (shs11_games.ReflexGame), with its own art from the addon (spec
`reflex`; tools/translate/shs11.py reflex_ui). Its frame is Memory's (desktop_shs11_memory.py), with the grid 7 of N73's rows
higher (`av`.j) and the gauge at (8, 69) of N73's in the banner's place. As there, nothing here decides anything in the game."""
from . import graphics as pygame
from .desktop_shs11_memory import ART, FRAME, Shs11MemoryRenderer
from .shs11_games import (AGE, BARS, BARS_SHOWN, DELAY, ENTER, ENTER_MS, FLASH_MS_WORD, GAUGE, GOAL, PENALTY, PICTURE, READY,
                          RIGHT_PICTURE, SELECT, SHUTTING, SKULL, TIME_UP, WRONG_PICTURE)

GAUGE_PLACE = (26, 221)
LOW_BOX_Y = 333                         # the box over the grid (`av`.d, `r.a` 104 of N73's)
TEXT_TOP = 179                          # the others' (`r.a` 56)
BAR_FRAMES = (14, 15, 16)               # `am`: one, two, three bars
FLASH_FRAMES = (17, 18, 19, 20)         # an icon coming in
SHUT_FRAMES = (18, 17)                  # and going
BOXES = {GOAL: ('goal', TEXT_TOP), GAUGE: ('gauge', LOW_BOX_Y), SELECT: ('select', TEXT_TOP), BARS: ('bars', TEXT_TOP),
         PENALTY: ('penalty', TEXT_TOP), SKULL: ('skull', TEXT_TOP), READY: ('ready', TEXT_TOP)}


class Shs11ReflexRenderer(Shs11MemoryRenderer):
    grid_y = 333

    def _reflex(self):
        spec = self._spec()[0]['reflex']
        if spec is None:
            raise ValueError("SHS '11's addon has no Reflex art: import its latest build")
        return spec

    def icon(self, surface, frame_number, centre):
        """A frame of the icon sheet, in its box, with the box's middle at `centre`."""
        spec = self._reflex()['icons']
        frame = spec['frames'][frame_number]
        left, top = centre[0] - round(spec['box'][0] * ART / 2), centre[1] - round(spec['box'][1] * ART / 2)
        surface.blit(self.piece(spec['picture'], frame), (left + round(frame[4] * ART), top + round(frame[5] * ART)))

    def draw_cell(self, surface, game, cell):
        icon = game.cells[cell]
        if not icon:
            return
        centre = self.tile_centre(cell)
        if icon[SHUTTING] >= 0:
            self.icon(surface, SHUT_FRAMES[0 if icon[SHUTTING] < 50 else 1], centre)
            return
        into = icon[AGE] - icon[DELAY]
        if into < 0:
            return
        flash = game.row[FLASH_MS_WORD]
        if into < flash:
            self.icon(surface, FLASH_FRAMES[min(3, into * 4 // max(1, flash))], centre)
            return
        self.icon(surface, icon[PICTURE], centre)
        for bars in range(icon[BARS_SHOWN]):
            self.icon(surface, BAR_FRAMES[bars], centre)

    def draw_gauge(self, surface, game):
        spec = self._reflex()
        x, y = GAUGE_PLACE
        drop = 0
        if game.phase == ENTER:
            left = max(0, game.phase_ms) / ENTER_MS         # `b`.q: its icons drop in
            drop = round(left * left * (y + 100))
        bar = spec['bar']
        picture = self.image(bar['picture'])
        size = (round(picture.get_width() * ART), round(picture.get_height() * ART))
        key = ('bar', size)
        scaled = self._images.get(key)
        if scaled is None:
            scaled = self._images[key] = pygame.transform.smoothscale(picture, size)
        surface.blit(scaled, (x + round(bar['place'][0] * ART), y + round(bar['place'][1] * ART)))
        marker = spec['marker']
        picture = self.image(marker['pictures'][game.marker_look])
        size = (round(picture.get_width() * ART), round(picture.get_height() * ART))
        key = (marker['pictures'][game.marker_look], size)
        scaled = self._images.get(key)
        if scaled is None:
            scaled = self._images[key] = pygame.transform.smoothscale(picture, size)
        along = marker['travel'] * game.marker_at / 1000
        surface.blit(scaled, (x + round((marker['place'][0] + along) * ART), y + round(marker['place'][1] * ART)))
        box = spec['icons']['box']
        self.icon(surface, game.row[WRONG_PICTURE], (x + round(box[0] * ART / 2), y + round(box[1] * ART / 2) - drop))
        self.icon(surface, game.row[RIGHT_PICTURE],
                  (x + round((spec['width'] - box[0] / 2) * ART), y + round(box[1] * ART / 2) - drop))

    def draw_game(self, session, surface):
        game = session.engine.shs11_reflex
        text = self._reflex()['text']
        surface.fill((0, 0, 0, 0))
        self.draw_clock(surface, game)
        self.draw_score(surface, game)
        self.draw_grid(surface, game)
        if game.row and game.phase != GOAL:
            self.draw_gauge(surface, game)
        if game.tutorial and game.wait_ms <= 0 and game.phase in BOXES:
            name, top = BOXES[game.phase]
            self.text_box(surface, text[name], top=top)
        self.draw_floats(surface, game)
        if game.phase == TIME_UP:
            self.box(surface, 620, 190, x=60, width=648)
            self.centred(surface, 'letters', self._spec()[0]['text']['time_up'].upper(), (FRAME[0] // 2, 715), 1.1)

