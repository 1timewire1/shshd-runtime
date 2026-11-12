"""shshd-runtime: draws a storyboard cutscene (cutscene.py) on the frame: its shot's window, then its overlays over that. It only
reads the clock. A window at the frame's own size is a blit; anything else is scaled each frame, with an overlay cut to what shows first,
as a stamp can start several times the frame's size.

General's Aspect Ratio: the canvas is `size`'s width and the frame's shape, no taller than the spec serves (version 1: 3:4;
version 2: its `tallest`); the desktop shows a shorter canvas at the frame's width, centred, with the backdrop above and below. A
version 2 shot is cropped about its window's centre ('crop') or zoomed by height about its anchor ('height'), and an overlay may follow
a shot's picture (cutscene_spec._check_version_2)."""
import io
import math

from . import graphics as pygame
from .cutscene import moved, read_spec


def _kept(centre, half, low, high):
    """A centre moved so its box (`half` either side) lies within [low, high]; one larger than that is centred in it."""
    if 2 * half >= high - low:
        return (low + high) / 2
    return min(max(centre, low + half), high - half)


class CutsceneRenderer:
    frame_units = (384, 512)            # the frame's shape in layout units (Desktop sets it)

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
            self.canvas = None
            self._images, self._scaled = {}, {}
            for item in self._spec['shots'] + self._spec.get('overlays', []):       # so that none stalls a frame later on
                self._image(item['image'])
        size = self.canvas_size()
        if self.canvas is None or self.canvas.get_size() != size:
            self.canvas = pygame.Surface(size).convert()
        return self._spec

    def canvas_size(self):
        """`size`'s width; as tall as the frame's shape, within what the spec serves (3:4 at least, its tallest at most)."""
        spec = self._spec
        width, height = spec['size']
        tallest = spec.get('tallest', spec['size']) if spec['version'] >= 2 else spec['size']
        frame_width, frame_height = self.frame_units
        shape = max(frame_width / frame_height, tallest[0] / tallest[1])
        return width, max(height, min(tallest[1], round(width / shape)))

    def _image(self, resource):
        found = self._images.get(resource)
        if found is None:
            surface = pygame.image.load(io.BytesIO(self.resources.read_asset(resource)), f'{resource}.png')
            found = self._images[resource] = surface.convert_alpha() if surface.get_masks()[3] else surface.convert()
        return found

    def window(self, shot, ms, size=None):
        """The shot's window at `ms` for a canvas of `size` (this one's): version 1's as stored; version 2's cropped about
        its centre to the canvas's shape ('crop') or narrowed about its anchor, its height kept ('height'). An anchor with
        `anchor_to` travels there at the window's own pace and easing."""
        x, y, w, h = moved(shot, ms)
        if self._spec['version'] < 2:
            return x, y, w, h
        width, height = size or self.canvas.get_size()
        if shot.get('fit', 'crop') == 'height':
            anchor = shot['anchor'][0]
            if 'anchor_to' in shot:
                anchor = moved(dict(shot, **{'from': shot['anchor'], 'to': shot['anchor_to']}), ms)[0]
            narrow = h * width / height
            return anchor - (anchor - x) * narrow / w, y, narrow, h
        short = w * height / width
        return x, y + (h - short) / 2, w, short

    def _shot(self, shot, ms):
        image = self._image(shot['image'])
        x, y, w, h = self.window(shot, ms)
        width, height = self.canvas.get_size()
        if (round(w), round(h)) == (width, height):
            self.canvas.blit(image, (-round(x), -round(y)))
            return
        box = pygame.Rect(round(x), round(y), round(w), round(h)).clip(image.get_rect())
        self.canvas.blit(pygame.transform.smoothscale(image.subsurface(box), (width, height)), (0, 0))

    def _placed(self, overlay, ms):
        """The overlay's (cx, cy, w, h) on this canvas. Its spec places it on the 3:4 frame (`size`): a taller canvas keeps
        it as far from the middle, or (version 2's `follow`) on the same place in that shot's picture.

        A following overlay keeps on the canvas: as its picture zooms, its centre moves out while its size stays, so
        near an edge it would run off (the card's subtitle at 20:9: reference/handoff_x360_storyboard_v2_reply.md). It
        goes no further past an edge than it is at 3:4, so one that slides in from outside still does."""
        cx, cy, w, h = moved(overlay, ms)
        size = tuple(self._spec['size'])
        width, height = self.canvas.get_size()
        if (width, height) == size:
            return cx, cy, w, h
        follow = overlay.get('follow')
        lower = (height - size[1]) / 2
        if follow is None:
            return cx, cy + lower, w, h
        shot = self._spec['shots'][follow]
        x0, y0, w0, h0 = self.window(shot, ms, size)                # where the picture is at 3:4
        x1, y1, w1, h1 = self.window(shot, ms)                      # and on this canvas
        px, py = x0 + cx * w0 / size[0], y0 + cy * h0 / size[1]
        fx, fy = (px - x1) * width / w1, (py - y1) * height / h1
        fx = _kept(fx, w / 2, min(0., cx - w / 2), max(float(width), cx + w / 2))
        fy = _kept(fy, h / 2, min(0., cy + lower - h / 2), max(float(height), cy + lower + h / 2))
        return fx, fy, w, h

    def _overlay(self, overlay, ms):
        image = self._image(overlay['image'])
        cx, cy, w, h = self._placed(overlay, ms)
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
