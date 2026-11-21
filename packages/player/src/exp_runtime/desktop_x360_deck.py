"""shshd-runtime: the cancelled Xbox 360 prototype's Diss Practice deck, as its booth shots draw it (tools/translate/
x360_arena_art.py, docs/X360.md): the deck in its parts with the record turning under a
fixed light and the tone arm swinging, the score's digits and the hit effects. Used by the arena's X360 look over New Rules'
panel (desktop_nr_arena_x360.py) and by Diss Practice itself (desktop_x360_diss.py). Coordinates are the arena's native
pixels until they are drawn, times `self.k`. A host gives `x360()`, the skin's spec and archive, and `k`, and its `_images`,
`_scaled`, `_seams`, `effects` and `hits` start empty.
"""
import io
import math
import random

from . import graphics as pygame

from .desktop_nr_arena import OX, SCREEN_WIDTH

# Where the X360 pieces go in the arena's native frame (489 x 652; the gear's bar covers below about 560).
DECK_WIDTH = 469                        # the deck centred, 10 pixels in from each edge
RECORD_Y = 380                          # the record's centre: the New Rules ring's height, a little lower
SEAM_STEP = 3                           # degrees between the kept pictures of the record's seams
SCORE_BOX = (250, 104, 229)             # the score's six digits: left, top, width (top right, as in Diss Practice)
# Diss Practice's hit effects (templates particleemitter.wxr: minigame/bps/eat_good_note, eat_bad_note), in its world
# units: sizes at FX_SIZE native pixels a unit, speeds and gravity at FX_SPEED (a note there is about 0.15 units; the
# owner's recording shows the burst about a deck's eighth across). A good note: 8 flares shot out at 3-8 units/s, red to orange, falling
# (gravity 12), shrinking to nothing over 0.5 s. A bad note: 10 smoke puffs, dark green, rising (gravity 2) at
# 0.5-1 units/s, turning +-45 degrees/s and growing 5 times over 1 s.
FX_SIZE, FX_SPEED = 180, 45
FX = {'good': dict(count=8, life=500, speed=(3, 8), colours=((255, 0, 0), (255, 128, 0)), size=(0.1, 0.4),
                   gravity=12, grow=0, spin=0, sprites='fx_spark'),
      # The X360's own greens (62 74 53 to 17 47 44) are lost on the black record here: the same hues, lighter.
      'bad': dict(count=10, life=1000, speed=(0.5, 1), colours=((150, 176, 128), (70, 130, 120)), size=(0.1, 0.4),
                  gravity=-2, grow=5, spin=45, sprites='fx_puff')}
ARM_SPEED = 4                           # the tone arm's AnimSpeed: PUSH's 967 ms play in 242 (x360_diss.PUSH)
SWING = ((47, 1300), (35, 2100), (62, 1700), (41, 2700), (55, 1100), (30, 2300), (38, 1900), (66, 2500))

# A remix arrow's burst (minigame/bps/eat_swap), as a good note's in its colours.
FX['swap'] = dict(FX['good'], colours=((90, 170, 255), (255, 150, 30)))
ADDED = ('good', 'swap')                # the flares that glow over what's under them
FX_SIDE_STEP = 1.06                     # an effect sprite's sizes go up in 6% steps, so each is made once and kept
FX_TURN_STEP = 6                        # a native host's puffs turn in 6 degree steps (`_draw_effect`)
FX_CACHE = 3000                         # effect sprites kept (`_fx_cache`)


def fx_side(pixels):
    """An effect sprite's side in whole pixels, on FX_SIDE_STEP's ladder above 8: the particles shrink or grow every
    frame, and at a new size each frame every frame tinted (and on iOS encoded) a new picture."""
    if pixels <= 8:
        return max(1, round(pixels))
    return round(FX_SIDE_STEP ** round(math.log(pixels, FX_SIDE_STEP)))


class X360Deck:
    def _arm_press(self, arena, now):
        """What starts the tone arm's swing, in a host whose frames have to work that out."""

    def image(self, resource):
        found = self._images.get(resource)
        if found is None:
            spec, archive = self.x360()
            found = pygame.image.load(io.BytesIO(archive.read(resource)), 'x360.png').convert_alpha()
            self._images[resource] = found
        return found

    def picture(self, name):
        return self.image(self.x360()[0]['pictures'][name])

    def scaled(self, image, size):
        """`image` (a surface, or a skin resource ID) smoothly scaled to `size` pixels, kept for the next frames."""
        if isinstance(image, int):
            image = self.image(image)
        key = (id(image), size)
        found = self._scaled.get(key)
        if found is None or found[0] is not image:          # an id reused by another surface since
            if len(self._scaled) > 400:
                self._scaled.clear()
            found = (image, pygame.transform.smoothscale(image, (max(1, size[0]), max(1, size[1]))))
            self._scaled[key] = found
        return found[1]

    def _deck(self):
        """(scale, record centre x, y, record half-width, half-height) in native pixels: the booth's camera frame onto
        the arena's, the deck centred DECK_WIDTH wide, the record's centre at RECORD_Y."""
        booth = self.x360()[0]['booth']
        deck, record = booth['pieces']['deck']['box'], booth['pieces']['record']['box']
        u = DECK_WIDTH / (deck[2] - deck[0])
        record_cx, record_cy = (record[0] + record[2]) / 2, (record[1] + record[3] - 12) / 2   # its top face
        cx = OX + SCREEN_WIDTH / 2 - ((deck[0] + deck[2]) / 2 - record_cx) * u
        return u, cx, RECORD_Y, (record[2] - record[0]) * u / 2, (record[3] - record[1] - 12) * u / 2, record_cx, \
            record_cy

    def _to_native(self, box):
        """A booth box (camera-frame pixels) placed by the deck's transform, as a native-pixel rect (floats)."""
        u, cx, cy, _, _, record_cx, record_cy = self._deck()
        return (cx + (box[0] - record_cx) * u, cy + (box[1] - record_cy) * u, (box[2] - box[0]) * u,
                (box[3] - box[1]) * u)

    def _score_transform(self):
        """The score's six digits as a group: their booth boxes scaled to SCORE_BOX's width, at its corner."""
        digits = self.x360()[0]['booth']['digits']
        boxes = [digits['slots'][i][0]['box'] for i in digits['score']]
        left, top = min(b[0] for b in boxes), min(b[1] for b in boxes)
        right = max(b[2] for b in boxes)
        u = SCORE_BOX[2] / (right - left)
        return u, left, top

    def blit(self, surface, image, x, y, w=None, h=None, alpha=255, anchor='topleft'):
        """An image at native (x, y), `w` x `h` native pixels (its own size scaled with the frame by default)."""
        k = self.k
        if w is None:
            w, h = image.get_width() / k, image.get_height() / k
        size = (max(1, round(w * k)), max(1, round(h * k)))
        scaled = self.scaled(image, size) if image.get_size() != size else image
        rect = scaled.get_rect(**{anchor: (round(x * k), round(y * k))})
        if alpha < 255:
            scaled = scaled.copy()
            scaled.set_alpha(alpha)
        surface.blit(scaled, rect)
        return rect

    def _deck_piece(self, surface, image, box, size, deck_dy):
        """A piece of the deck at its booth `box`, following the deck's shake (`size`) and rise."""
        u, cx, cy, _, _, _, _ = self._deck()
        x, y, w, h = self._to_native(box)
        self.blit(surface, image, cx + (x - cx) * size, cy + (y - cy) * size + deck_dy, w * size, h * size)

    def _deck_parts(self, surface, arena, parts, size, deck_dy, now):
        """The deck in its parts, as the X360 has them: the record turns with the panel's angle, so the items stay on it,
        under a light that stays (only its seams move), and the tone arm swings on OK."""
        self._deck_piece(surface, self.image(parts['body']['id']), parts['body']['box'], size, deck_dy)
        self._deck_piece(surface, self.image(parts['record']['id']), parts['record']['box'], size, deck_dy)
        self._record_seams(surface, arena, parts['seams'], size, deck_dy)
        self._deck_piece(surface, self.image(parts['spindle']['id']), parts['spindle']['box'], size, deck_dy)
        self._arm_press(arena, now)
        frame = self._arm_frame(parts['arm'], now)
        self._deck_piece(surface, self._arm_cell(parts['arm'], frame), frame['box'], size, deck_dy)

    def _record_seams(self, surface, arena, seams, size, deck_dy):
        """The label's seams at the record's turn: turned, then squashed to the record's ellipse, about the hole. Two
        lines through it look the same half a turn on, so SEAM_STEP-degree steps of half a turn are kept."""
        u, cx, cy, _, _, _, _ = self._deck()
        hx, hy, _, _ = self._to_native(seams['centre'] * 2)
        k = self.k
        width = max(1, round(2 * seams['radius'] * u * size * k))
        height = max(1, round(width / seams['squash']))
        # The ring's angles run clockwise on screen; pygame's rotate, anticlockwise.
        turn = round(arena.angle / SEAM_STEP) * SEAM_STEP % 180
        key = (turn, width, height)
        found = self._seams.get(key)
        if found is None:
            if len(self._seams) > 2 * 180 // SEAM_STEP:
                self._seams.clear()
            image = self.image(seams['id'])
            turned = pygame.transform.rotate(image, -turn)
            found = pygame.transform.smoothscale(turned, (max(1, round(width * turned.get_width() / image.get_width())),
                                                          max(1, round(height * turned.get_height() / image.get_height()))))
            self._seams[key] = found
        x = (cx + (hx - cx) * size) * k
        y = (cy + (hy - cy) * size + deck_dy) * k
        surface.blit(found, found.get_rect(center=(round(x), round(y))))

    def _arm_frame(self, arm, now):
        """The tone arm's frame now: PUSH while it runs (_arm_press), at rest otherwise."""
        angle = 0
        if self._arm_start is not None:
            elapsed, push = (now - self._arm_start) * ARM_SPEED, arm['push']
            if 0 <= elapsed < push[-1][0]:
                for (t0, a0), (t1, a1) in zip(push, push[1:]):
                    if elapsed < t1:
                        angle = a0 + (a1 - a0) * (elapsed - t0) / (t1 - t0) if t1 > t0 else a1
                        break
            else:
                self._arm_start = None
        return min(arm['frames'], key=lambda frame: abs(frame['angle'] - angle))

    # -- the camera, and the notes it sees --------------------------------------------------------------------------------------------
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

    def _stand_note(self, surface, name, effects, nx, ny, depth, grow, now, index):
        """The booth's note `name` standing at native (nx, ny), as large as the camera sees it at `depth`, with its effects
        (minigame/bps: 'stink', 'flames' under it, 'sparks' over it). The rect drawn, in canvas pixels, or None."""
        booth = self.x360()[0]['booth']
        spec = booth['notes']
        picture = spec['kinds'][name]
        per_pixel = self._deck()[0] * booth['frame'][0] / spec['frame'][0]
        scale = per_pixel * picture['depth'] / depth * grow * self.k
        if scale <= 0:
            return None
        image = self.image(picture['id'])
        size = (max(1, round(image.get_width() * scale)), max(1, round(image.get_height() * scale)))
        left = nx * self.k - picture['anchor'][0] * scale
        top = ny * self.k - picture['anchor'][1] * scale
        centre = (left + size[0] / 2, top + size[1] / 2)
        if 'stink' in effects:
            self._stink(surface, centre, size, now, index)
        if 'flames' in effects:
            self._flames(surface, centre, size, now, index)
        surface.blit(self.scaled(image, size), (round(left), round(top)))
        if 'sparks' in effects:
            self._sparks(surface, centre, size, now, index)
        return pygame.Rect(round(left), round(top), *size)

    # minigame/bps/bad_note_stink, hot_note_sparks and hot_note_flames, as their looks go: they only ever drift past.
    def _stink(self, surface, centre, size, now, index):
        sprites = self._sprites('fx_puff')
        for i in range(3):
            phase = (now / 1400 + i / 3 + index * .13) % 1
            side = fx_side(size[0] * (.4 + .5 * phase))
            self._faded_sprite(surface, self._tinted(sprites[i % len(sprites)], (150, 176, 128), side),
                               round(110 * (1 - phase)), (round(centre[0] + (i - 1) * size[0] * .18),
                                                          round(centre[1] - size[1] * (.1 + .7 * phase))))

    def _sparks(self, surface, centre, size, now, index):
        sprites = self._sprites('fx_spark')
        for i in range(3):
            phase = (now / 900 + i / 3 + index * .17) % 1
            side = fx_side(size[0] * .16 * (1 - phase))
            x = centre[0] + size[0] * .55 * math.sin(i * 2.4 + index) * (.4 + phase)
            y = centre[1] - size[1] * .3 + size[1] * phase * phase
            self._light(surface, sprites[i % len(sprites)], (255, 190, 60), side, (round(x), round(y)))

    def _flames(self, surface, centre, size, now, index):
        sprites = self._sprites('fx_spark')
        for i in range(5):
            phase = (now / 500 + i / 5 + index * .11) % 1
            side = fx_side(size[0] * (.55 - .35 * phase))
            colour = (255, round(200 - 150 * phase), 20)
            x = centre[0] + size[0] * .32 * math.sin(i * 1.9 + now / 170)
            y = centre[1] + size[1] * .3 - size[1] * .9 * phase
            self._light(surface, sprites[i % len(sprites)], colour, side, (round(x), round(y)))

    def _light(self, surface, name, colour, side, centre):
        """A glowing sprite added over what is under it (BLEND_RGB_ADD), as the X360 adds its sparks and flames; on a
        native host (iOS), which adds light only onto opaque pixels and did each one here in Python, the sprite in its
        colour with its brightness as alpha: the same light over the dark record and notes (iPad, 2026-11-19)."""
        if getattr(surface, 'native', False):
            image = self._tinted(name, colour, side)
            surface.blit(image, image.get_rect(center=centre))
            return
        image = self._tinted(name, colour, side, additive=True)
        surface.blit(image, image.get_rect(center=centre), special_flags=pygame.BLEND_RGB_ADD)

    @staticmethod
    def _faded_sprite(surface, image, alpha, centre):
        """A kept sprite drawn at `alpha`: a native host takes the alpha with the blit (no copy, so no new picture to send
        it); pygame fades a copy, the sprite kept as it was."""
        if getattr(surface, 'native', False):
            image.set_alpha(alpha // 8 * 8)
            surface.blit(image, image.get_rect(center=centre))
            image.set_alpha(None)
            return
        image = image.copy()
        image.set_alpha(alpha)
        surface.blit(image, image.get_rect(center=centre))

    def _sprites(self, prefix):
        return [name for name in self.x360()[0]['pictures'] if name.startswith(prefix + '_')]

    def _arm_cell(self, arm, frame):
        key = ('arm', frame['angle'])
        found = self._images.get(key)
        if found is None:
            found = self._images[key] = self.image(arm['atlas']).subsurface(pygame.Rect(frame['rect'])).copy()
        return found

    def _digit(self, surface, slot, n, rect, now):
        """Slot `slot`'s digit `n` from the atlas into `rect` (native x, y, w, h), swinging as Diss Practice's do:
        30-70 degrees about the digit's upright axis and back, drawn as its width narrowing."""
        digits = self.x360()[0]['booth']['digits']
        ax, ay, aw, ah = digits['slots'][slot][n]['rect']
        atlas = self.image(digits['atlas'])
        cell = self._scaled.get(('cell', slot, n))
        if cell is None:
            cell = atlas.subsurface(pygame.Rect(ax, ay, aw, ah)).copy()
            self._scaled[('cell', slot, n)] = cell
        amplitude, period = SWING[slot % len(SWING)]
        phase = (now % (2 * period)) / period                   # 0-2: there and back
        angle = amplitude * (1 - abs(1 - phase)) - amplitude / 2
        x, y, w, h = rect
        narrow = max(0.55, math.cos(math.radians(angle)))
        self.blit(surface, cell, x + w * (1 - narrow) / 2, y, w * narrow, h)

    def _spawn(self, kind, x, y, now):
        self.hits = [*self.hits[-3:], kind]
        sprites = [name for name in self.x360()[0]['pictures'] if name.startswith(FX[kind]['sprites'] + '_')]
        if not sprites:
            return                          # a skin from before the effects' sprites: none
        spec, rng = FX[kind], random.Random(now * 31 + round(x) * 7 + round(y))       # the same frames each run
        particles = []
        for _ in range(spec['count']):
            angle = rng.uniform(0, 2 * math.pi)
            speed = rng.uniform(*spec['speed']) * FX_SPEED
            particles.append((math.cos(angle) * speed, math.sin(angle) * speed * 0.6, rng.uniform(*spec['size']),
                              rng.choice(sprites), rng.uniform(-spec['spin'], spec['spin']), rng.uniform(0, 360)))
        self.effects.append((kind, x, y, now, particles))
        if len(self.effects) > 12:
            self.effects = self.effects[-12:]

    def _draw_effect(self, surface, effect, now):
        kind, x0, y0, start, particles = effect
        spec = FX[kind]
        t = (now - start) / spec['life']
        seconds = (now - start) / 1000
        (r0, g0, b0), (r1, g1, b1) = spec['colours']
        colour = (round(r0 + (r1 - r0) * t), round(g0 + (g1 - g0) * t), round(b0 + (b1 - b0) * t))
        k = self.k
        native = getattr(surface, 'native', False)
        for vx, vy, size, name, spin, turn in particles:
            x = x0 + vx * seconds
            y = y0 + vy * seconds + 0.5 * spec['gravity'] * FX_SPEED * seconds * seconds
            scale = (1 - t) if not spec['grow'] else 1 + (spec['grow'] - 1) * t
            side = fx_side(size * FX_SIZE * scale * k)
            if kind in ADDED and native:
                # A native host (iOS) can only add light onto an opaque surface; on this see-through canvas its drawing
                # backend added each flare in Python, about 4 ms apiece (iPad, 2026-11-19). The sprite drawn in its
                # colour with its brightness as its alpha is the same light over the dark record they burst on.
                image = self._tinted(name, colour, side)
                surface.blit(image, image.get_rect(center=(round(x * k), round(y * k))))
                continue
            image = self._tinted(name, colour, side, additive=kind in ADDED)
            if kind in ADDED:                  # the flares glow over what's under them, as the X360 adds them
                surface.blit(image, image.get_rect(center=(round(x * k), round(y * k))),
                             special_flags=pygame.BLEND_RGB_ADD)
                continue
            alpha = round(255 * (1 - t)) if kind == 'bad' else None
            if native:
                # A native host (iOS) takes each new picture across as a PNG: the puffs' turn in steps, each turned
                # sprite kept, and their fade as the blit's own alpha, not a copy (iPad, 2026-11-19: the Diss Battle's
                # effects made a picture a particle each frame and held it near 30 fps).
                if spec['spin']:
                    image = self._turned(image, round((turn + spin * seconds) / FX_TURN_STEP) * FX_TURN_STEP)
                if alpha is not None:
                    image.set_alpha(alpha // 16 * 16)
                surface.blit(image, image.get_rect(center=(round(x * k), round(y * k))))
                if alpha is not None:
                    image.set_alpha(None)
                continue
            if spec['spin']:
                image = pygame.transform.rotate(image, turn + spin * seconds)
            if alpha is not None:
                image = image.copy()
                image.set_alpha(alpha)
            surface.blit(image, image.get_rect(center=(round(x * k), round(y * k))))

    def _turned(self, image, angle):
        """`image` turned by `angle` degrees (a multiple of FX_TURN_STEP), kept while that image is."""
        key = ('fx-turn', id(image), angle % 360)
        cache = self._fx_cache()
        found = cache.get(key)
        if found is None or found[0] is not image:
            found = (image, pygame.transform.rotate(image, angle))
            cache[key] = found
        return found[1]

    def _fx_cache(self):
        """The effect sprites' own store: in `_scaled`, the record's pictures emptied it every 400 and the sprites were
        made again over and over (iPad, 2026-11-19). Capped well above what one battle's effects use."""
        cache = self.__dict__.get('_fx')
        if cache is None or len(cache) > FX_CACHE:
            cache = self._fx = {}
        return cache

    def _tinted(self, name, colour, side, additive=False):
        """An effect sprite (white, its brightness as alpha) in `colour`, `side` pixels square; kept, by colour step.
        `additive`: premultiplied on black, for adding (BLEND_RGB_ADD), so only its light is added."""
        step = tuple(c // 16 * 16 for c in colour)
        key = ('fx', name, step, side, additive)
        cache = self._fx_cache()
        found = cache.get(key)
        if found is None:
            # Tinted at the picture's own size, once a colour, then scaled: the same pixels (the multiply and the
            # smoothing are each per channel), and a scale alone is no new picture on a native host. Tinted after the
            # scale, each new size was a multiply worked in Python and a new PNG there: a wrong answer's puffs, growing
            # five times over a second, made one a puff each frame, up to 1027 x 1027 (iPad, 2026-11-20: 400 ms frames).
            tint = ('fx-tint', name, step)
            source = cache.get(tint)
            if source is None:
                source = cache[tint] = self.picture(name).copy()
                source.fill((*step, 255), special_flags=pygame.BLEND_RGBA_MULT)
            found = pygame.transform.smoothscale(source, (side, side))
            if additive:
                light = pygame.Surface((side, side))
                light.fill((0, 0, 0))
                light.blit(found, (0, 0))
                found = light
            cache[key] = found
        return found
