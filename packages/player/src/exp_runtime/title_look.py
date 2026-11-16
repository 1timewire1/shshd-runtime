"""shshd-runtime: Add-Ons' Title Screen Look (owner, 2026-11-16; reference/TITLE_SCREENS_PLAN.md): a translated game's own
title art in place of the HD main menu's wood, photo, ribbon and title (HdUi.main_layers), from that game's addon.

The addon carries a spec, a JSON resource (the game profile's TITLE_LOOKS gives its number), whose pictures follow it:

    {"version": 1,
     "background": {"cover": PICTURE}  or  {"top": PICTURE, "middle": PICTURE, "bottom": PICTURE}  or  {"hd_wood": true},
     "scene": {"picture": PICTURE, "left": x, "bottom": y},       (optional)
     "photo": {"picture": PICTURE, "centre": [x, y], "fit": w, "drop": true, "hd_scale": k},
                                                                  (optional; `fit`, `drop`, `hd_scale` optional)
     "title": {"picture": PICTURE, "centre": [x, y], "follow": f}}              (optional; `follow` optional)
    PICTURE = {"id": resource, "scale": points per pixel, "smooth": false for pixel art (scaled nearest)}

Coordinates are HD's points in its 768 x 1024 frame. In a taller frame (General's Aspect Ratio) each part goes where HD's
own does (HdUi.main_layout): a "cover" background is scaled to cover the frame and centred, as the wood is; "hd_wood" is the
smartphone's own wood, placed as HD places it ('11's photo, cut from its wood, on the smartphone's: owner, 2026-11-16); a
sliced one is built at the frame's height (its top at the top, its bottom at the bottom, the middle repeated between); the
scene keeps its distance above the buttons, so it moves down with them; the photo moves and grows as HD's photo does, but no
wider than the frame (`fit`, the width that must stay inside, else the picture's); the title keeps its place at the top, or
moves down by `follow` of what the buttons do (X360's, which centres between the top and its scene: owner, 2026-11-16).
The photo is what the first launch drops in, and the title what fades in (desktop_main_hd).
"""
from dataclasses import dataclass, field
from io import BytesIO
import json
import logging

from . import graphics as pygame

VERSION = 1
SMALL_UNTIL = 1152      # points tall (2:3) by which a photo's `hd_scale` has eased back to its full size
TITLE_CLEARANCE = 8     # points a title keeps below a phone's status bar (HdUi's top_pad)


@dataclass(eq=False)
class TitleLook:
    """One game's look: its spec and its pictures, read from `library` (addon `addon`, the spec at `spec_id`)."""
    library: object
    addon: str
    spec_id: int
    spec: dict
    _pictures: dict = field(default_factory=dict)

    @classmethod
    def load(cls, library, addon, spec_id):
        """The look, or None when the addon lacks it (an older revision) or its spec is one this player can't read."""
        data = library.addon_resource(addon, spec_id) if hasattr(library, 'addon_resource') else None
        if data is None:
            return None
        try:
            spec = json.loads(data)
        except ValueError:
            logging.warning('Title Screen Look: %s %d is not a spec', addon, spec_id)
            return None
        if not isinstance(spec, dict) or spec.get('version') != VERSION or 'background' not in spec:
            return None
        return cls(library, addon, spec_id, spec)

    @property
    def photo_drops(self):
        """Whether the first launch drops the photo in (`"drop": false` keeps it in place: BREW '07's, whose logo is painted
        onto it; owner, 2026-11-16)."""
        return bool(self.spec.get('photo', {}).get('drop', True))

    def picture(self, entry, S):
        """A spec PICTURE at the canvas's S pixels per point (cached)."""
        key = (entry['id'], S)
        if key not in self._pictures:
            data = self.library.addon_resource(self.addon, entry['id'])
            if data is None:
                raise KeyError(f'{self.addon} has no picture {entry["id"]}')
            image = pygame.image.load(BytesIO(data)).convert_alpha()
            factor = entry.get('scale', 1) * S
            size = max(1, round(image.get_width() * factor)), max(1, round(image.get_height() * factor))
            if size != image.get_size():
                image = (pygame.transform.smoothscale if entry.get('smooth', True) else pygame.transform.scale)(image, size)
            self._pictures[key] = image
        return self._pictures[key]

    def layers(self, height, frame, S, *, extra, photo_shift, photo_grow, scaled, hd_wood=None, top_pad=0):
        """[(background, centre), (photo, centre) or None, None (no ribbon), (title, centre) or None] for a frame
        `frame[0]` x `height` points: `extra` is how far the buttons moved down from HD's place, `photo_shift` and
        `photo_grow` what HD's photo does in this frame (HdUi.main_layout), `scaled(surface, factor)` a smooth scale,
        `hd_wood()` the smartphone's own wood."""
        width = frame[0]
        background = self.background(height, width, S, scaled, hd_wood)
        scene = self.spec.get('scene')
        if scene:
            image = self.picture(scene['picture'], S)
            background = background.copy()
            background.blit(image, (round(scene.get('left', 0) * S), round((scene['bottom'] + extra) * S) - image.get_height()))
        layers = [(background, (width / 2, height / 2))]
        photo = self.spec.get('photo')
        if photo:
            image = self.picture(photo['picture'], S)
            # It grows as HD's does, but never wider than the frame: `fit` is the width (points) that must stay inside it,
            # the picture's own unless the spec says less (BREW '07's band may run off the sides; its letters may not).
            fit = photo.get('fit') or image.get_width() / S
            x, y = photo['centre']
            room = 2 * min(x, width - x)                # the widest it can be about its centre and stay inside
            grow = min(photo_grow, max(1.0, room / fit))
            # `hd_scale`: smaller in HD's own 3:4 frame, easing to full size by SMALL_UNTIL points tall (Hollywood's map,
            # which would cover its logo there: owner, 2026-11-16)
            small = photo.get('hd_scale', 1.0)
            if small != 1.0:
                grow *= small + (1 - small) * max(0.0, min(1.0, (height - frame[1]) / (SMALL_UNTIL - frame[1])))
            if grow != 1:
                image = scaled(image, grow)
            layers.append((image, (x, y + photo_shift)))
        else:
            layers.append(None)
        layers.append(None)
        title = self.spec.get('title')
        if title:
            x, y = title['centre']
            image = self.picture(title['picture'], S)
            y += extra * title.get('follow', 0)
            # Below a phone's status bar and camera cutout, if they'd cover it ('11's logo on the g54: owner, 2026-11-16)
            y = max(y, top_pad + TITLE_CLEARANCE + image.get_height() / S / 2) if top_pad else y
            layers.append((image, (x, y)))
        else:
            layers.append(None)
        return layers

    def background(self, height, width, S, scaled, hd_wood=None):
        """The background for a frame `width` x `height` points, the frame's size exactly. `hd_wood()` gives the smartphone's
        own wood at the canvas's scale, for a look that uses it."""
        spec = self.spec['background']
        size = (round(width * S), round(height * S))
        surface = pygame.Surface(size).convert()
        if 'cover' in spec or spec.get('hd_wood'):
            image = hd_wood() if spec.get('hd_wood') else self.picture(spec['cover'], S)
            factor = max(size[0] / image.get_width(), size[1] / image.get_height())
            if factor > 1:
                image = scaled(image, factor)
            surface.blit(image, image.get_rect(center=(size[0] // 2, size[1] // 2)))
            return surface
        top, middle, bottom = (self.picture(spec[part], S) for part in ('top', 'middle', 'bottom'))
        y = top.get_height()
        end = size[1] - bottom.get_height()
        while y < end:
            surface.blit(middle, (0, y))
            y += middle.get_height()
        surface.blit(top, (0, 0))
        surface.blit(bottom, (0, end))
        return surface
