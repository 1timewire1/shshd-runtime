"""shshd-runtime: draws a storyboard cutscene (cutscene.py) on the 3:4 frame: its shot's window, then its overlays over that. It only
reads the clock. A window at the frame's own size is a blit; anything else is scaled each frame, with an overlay cut to what shows first,
as a stamp can start several times the frame's size."""
import io
import math

from . import graphics as pygame
from .cutscene import moved, read_spec


class CutsceneRenderer:
    def __init__(self, resources):
        self.resources = resources
        self.canvas = None
        self._spec_id = None
        self._spec = None
        self._images = {}
        self._scaled = {}

    def spec(self, spec_id):
        if self._spec_id != spec_id:
            self._spec_id, self._spec = spec_id, read_spec(self.resources.read_asset(spec_id))
            self.canvas = pygame.Surface(tuple(self._spec['size'])).convert()
            self._images, self._scaled = {}, {}
            for item in self._spec['shots'] + self._spec.get('overlays', []):       # so that none stalls a frame later on
                self._image(item['image'])
        return self._spec

    def _image(self, resource):
        found = self._images.get(resource)
        if found is None:
            surface = pygame.image.load(io.BytesIO(self.resources.read_asset(resource)), f'{resource}.png')
            found = self._images[resource] = surface.convert_alpha() if surface.get_masks()[3] else surface.convert()
        return found

    def _shot(self, shot, ms):
        image = self._image(shot['image'])
        x, y, w, h = moved(shot, ms)
        width, height = self.canvas.get_size()
        if (round(w), round(h)) == (width, height):
            self.canvas.blit(image, (-round(x), -round(y)))
            return
        box = pygame.Rect(round(x), round(y), round(w), round(h)).clip(image.get_rect())
        self.canvas.blit(pygame.transform.smoothscale(image.subsurface(box), (width, height)), (0, 0))

    def _overlay(self, overlay, ms):
        image = self._image(overlay['image'])
        cx, cy, w, h = moved(overlay, ms)
        key = overlay['image'], round(w), round(h)
        settled = self._scaled.get(key)
        if settled is None and ms >= overlay['end']:
            settled = self._scaled[key] = pygame.transform.smoothscale(image, (max(1, round(w)), max(1, round(h))))
        if settled is not None:
            self.canvas.blit(settled, (round(cx - w / 2), round(cy - h / 2)))
            return
        # What shows of it: a part of the picture, scaled on its own, however large the whole would be.
        left, top = cx - w / 2, cy - h / 2
        width, height = self.canvas.get_size()
        x0, y0, x1, y1 = max(0, left), max(0, top), min(width, left + w), min(height, top + h)
        if x1 <= x0 or y1 <= y0:
            return
        sx, sy = image.get_width() / w, image.get_height() / h
        a, b = math.floor((x0 - left) * sx), math.floor((y0 - top) * sy)
        c, d = math.ceil((x1 - left) * sx), math.ceil((y1 - top) * sy)
        part = image.subsurface(pygame.Rect(a, b, c - a, d - b).clip(image.get_rect()))
        size = max(1, round((c - a) / sx)), max(1, round((d - b) / sy))
        self.canvas.blit(pygame.transform.smoothscale(part, size), (round(left + a / sx), round(top + b / sy)))

    def draw(self, session):
        game = session.engine.cutscene
        spec, ms = self.spec(game.spec), game.elapsed_ms
        shot = [s for s in spec['shots'] if s['start'] <= ms][-1]
        self._shot(shot, ms)
        for overlay in spec.get('overlays', ()):
            if overlay['start'] <= ms:
                self._overlay(overlay, ms)
