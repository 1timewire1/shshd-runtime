"""The HD build's "faceplace alert" card, drawn at HD's own density.

`SHSFSView.checkInit` builds the card from four pack-155 frames -- 73 (the
title with "faceplace alert" baked in), 38/39/40 (bottom cap, stretched middle,
top cap) -- and `finalizeAutoAnim` slides them in from x = 1020 to their resting
place over 0.2 s (`setAnimationDuration 0.2`). The view is the narrow faceplace
strip (224 x 768 px, `setupViewOrientation_internal`), centered at x = 672,
y = 400 in portrait, so its right 16 px hang off the 768-px frame and the
card is cut by the screen's edge. The message is `drawMessage`'s: a face
(`drawFace`: frame-46 ring, the theme's ellipse disc and the masked portrait,
all at scale 0.2) with the sender's name in Arial Rounded 14 px (107, 128, 167)
leading the message in Arial 14 px, wrapped 78 px in from the strip's width
(204 in portrait, so 126 px).

Everything is in the frame's own pixels (768 x 1024); the caller resamples the
layer once. Positions the decompile does not state (the card's top, the text
baseline, the card height for a given number of lines) are calibrated against
a photo of a real HD alert (reference/IMG_0092.PNG) and marked below.
"""
from dataclasses import dataclass, replace
from functools import lru_cache

import pygame

from .dialogue_animation import DialoguePortrait
from .fonts import Glyph, TextStyle
from .vector_text import load_font_sized

FRAME = (768, 1024)
# `animationDidStop:` of the slide on plays sound 0x1f52.
ALERT_SOUND = 0x1f52
# 155's frames.
TITLE, BOTTOM, MIDDLE, TOP = 73, 38, 39, 40
CARD_WIDTH = 214
# The strip's left edge (center 672 - 112) and the card's offset inside it
# (image center 116 - 107); the title image (194 wide, center 111) is 5 further.
STRIP_LEFT = 560
CARD_LEFT = STRIP_LEFT + 9
TITLE_INSET = 5
# Where the card starts, photo-measured (the strip's top is y = 16; 70 below it).
CARD_TOP = 86
TITLE_TOP = 3
SLIDE_FROM = 1020 - 116
SLIDE_SECONDS = 0.2
# `checkInit` makes both fonts at 14 points. The body font is Arial drawn at Arial Rounded Bold's advances: `initFonts`
# (0002b04a) builds the ArialMT CSFontInfo (+0x7024, the glyph advance table every ArialMT CSFont copies) from the
# CGFont at +0x21c, Arial Rounded MT Bold, right after storing ArialMT at +0x218. Its lines are therefore wider than
# Arial's (what an earlier fit read as Arial at 15.1) while its letters are Arial 14's height, and the wraps follow
# (IMG_0299: "Raven When you end" fits 146 points at 141.7, "Wilson! We're coming" at 146.4 does not).
FONT_PX = 14
LINE_PITCH = 13.3
# Between a post's text and its continuation paragraph (photo: 23 units baseline to baseline).
PARAGRAPH_GAP = 9.5
# `drawMessage`: face text starts 75 px in from the message's x (4) and is
# (width 204) - 78 wide; a message without a face starts 15 in and is 18 narrower.
FACE_TEXT_X = 4 + 75 - 9 - 1
FACE_TEXT_WIDTH = 204 - 78
PLAIN_TEXT_X = 4 + 15 - 9
PLAIN_TEXT_WIDTH = 204 - 18
# First baseline of the text below the card's top, photo-measured.
BASELINE = 44.7
# `drawFace` centers the 42 px disc at (atX + 25.5, atY + 38.5); measured
# against the photo the face's center sits at this card-relative point.
FACE_CENTER = (38.5, 54.8)
FACE_SCALE = 0.2
# `measureMessageMinimumHeight`: a face message is at least 56 px tall.
MIN_MESSAGE_HEIGHT = 56
CHROME = 39.1
TEXT_PAD = 3
BODY = (0, 0, 0)
NAME = (107, 128, 167)
# `checkInit`: `addCharImage` makes three characters of the body font (`FSTextBody`) pack-155 frames -- 'E' for '{', 'F' for
# '>' and 'G' for '}' -- so a post's braces are a frown, a heart and a smile. The layout measures them through these stand-in
# codes (a Latin-1 control character the font has no glyph for) and the frames are drawn in their place.
EMOTICON_FRAMES = {'{': 69, '>': 70, '}': 71}
EMOTICON_CODES = {'{': 1, '>': 2, '}': 3}
# Where the frame sits on the line: `addCharImage(master, frame, char, (-1, 6), 16)` and `drawChar` draws it with
# `renderCutupAligned` anchor 0x24 (bottom | left) at the pen plus that offset, so its bottom-left corner is 1 point left
# of the pen and 6 below the baseline; the character advances 16 points (the frames are 18 wide, so they overlap 2).
EMOTICON_OFFSET = (-1, 6)
EMOTICON_ADVANCE = 16


@dataclass(frozen=True)
class AlertKey:
    text: str
    name: str
    portrait: DialoguePortrait | None
    extra: tuple[str, ...] = ()      # continuation paragraphs (link text), drawn in the sender font


class FaceplaceAlertRenderer:
    def __init__(self, resources, text_renderer, dialogue_renderer):
        self.resources, self.text, self.art = resources, text_renderer, dialogue_renderer

    def fonts(self):
        """(body, name) font keys registered in the text renderer, or None."""
        library = self.resources.library
        body = load_font_sized(library, 'ArialMT14', FONT_PX)
        name = load_font_sized(library, 'ArialRoundedMTBold14', FONT_PX)
        if body is None or name is None:
            return None
        if self._advance_source != (id(body), id(name)):
            glyphs = {code: replace(glyph, advance=name.glyphs[code].advance) if code in name.glyphs else glyph
                      for code, glyph in body.glyphs.items()}
            self._advance_source, self._body = (id(body), id(name)), replace(body, glyphs=glyphs)
        body = self._body
        self.text.fonts['FaceplaceBody'] = (body, None)
        self.text.fonts['FaceplaceName'] = (name, None)
        return 'FaceplaceBody', 'FaceplaceName'

    def emoticon_font(self):
        """The body font with the emoticons' stand-in glyphs, registered in the text renderer: (key, {code: frame})."""
        body_key, _ = self.fonts()
        images = self.emoticons()
        body = self.text.font(body_key)
        if self._emoticon_source is not body:
            glyphs = dict(body.glyphs)
            for code, image in images.items():
                glyphs[code] = Glyph(code, 0, 0, image.get_width(), image.get_height(), EMOTICON_OFFSET[0],
                                     body.base + EMOTICON_OFFSET[1] - image.get_height(), EMOTICON_ADVANCE)
            self.text.fonts['FaceplaceBodyEmoticons'] = (replace(body, glyphs=glyphs), None)
            self._emoticon_source = body
        return 'FaceplaceBodyEmoticons', images

    _emoticon_source = None
    _advance_source = _body = None

    def emoticons(self):
        """{stand-in code: frame surface} of the three emoticons."""
        return {code: self.art.frame_native(155, EMOTICON_FRAMES[char]) for char, code in EMOTICON_CODES.items()}

    @staticmethod
    def with_emoticons(text):
        return ''.join(chr(EMOTICON_CODES[c]) if c in EMOTICON_CODES else c for c in text)

    def available(self):
        try:
            return (self.art.hd_chrome() and len(self.art.pack(155).images) > TITLE
                    and self.fonts() is not None)
        except (AttributeError, ValueError, pygame.error):
            return False

    def portrait(self, engine, message):
        variants = engine.character_art_variants.get(message.from_id)
        if message.from_id < 0 or not variants:
            return None
        asset = variants[max(0, message.expression) % len(variants)]
        if asset < 0:
            return None
        theme = engine.numbers.get(engine.number_key(message.from_id, 651), 0)
        # `drawFace` is called with hflip 0, so mode 1 (art never mirrored).
        return DialoguePortrait(message.from_id, asset, 1, theme)

    def key(self, engine, message):
        name = engine.character_names.get(message.from_id, '') if message.from_id >= 0 else ''
        extra = tuple((c.text or c.url).split('~', 1)[0] for c in message.continuations)
        return AlertKey(message.text.split('~', 1)[0], name, self.portrait(engine, message), extra)

    @lru_cache(maxsize=8)
    def card(self, key):
        """The finished card, `CARD_WIDTH` px wide, at HD's own pixels."""
        body_font, name_font = self.fonts()
        face = key.portrait is not None
        x, width = (FACE_TEXT_X, FACE_TEXT_WIDTH) if face else (PLAIN_TEXT_X, PLAIN_TEXT_WIDTH)
        indent = 0
        if key.name:
            name = self.text.layout(name_font, key.name, 2**31, TextStyle(LINE_PITCH, 0, NAME))
            space = self.text.font(body_font).glyph(' ').advance
            indent = round(name.width + space)
        body_font, inline = self.emoticon_font()
        body = self.text.layout(body_font, self.with_emoticons(key.text), width,
                                TextStyle(LINE_PITCH, 0, BODY, indents=(indent,)))
        extras = [self.text.layout(name_font, text, width, TextStyle(LINE_PITCH, 0, NAME)) for text in key.extra]
        lines = max(1, len(body.lines)) + sum(len(extra.lines) for extra in extras)
        message = max(MIN_MESSAGE_HEIGHT if face else 0, LINE_PITCH * lines + PARAGRAPH_GAP * len(extras) + TEXT_PAD)
        height = round(CHROME + message)
        card = pygame.Surface((CARD_WIDTH, height), pygame.SRCALPHA).convert_alpha()
        frame = self.art.frame_native
        card.blit(frame(155, TOP), (0, 0))
        middle = height - frame(155, TOP).get_height() - frame(155, BOTTOM).get_height()
        card.blit(pygame.transform.scale(frame(155, MIDDLE), (CARD_WIDTH, max(1, middle))),
                  (0, frame(155, TOP).get_height()))
        card.blit(frame(155, BOTTOM), (0, height - frame(155, BOTTOM).get_height()))
        card.blit(frame(155, TITLE), (TITLE_INSET, TITLE_TOP))
        if face:
            group, (gx, gy) = self.art.portrait_group(key.portrait)
            # The group is built in canvas pixels; 2 per unit is HD's native.
            factor = FACE_SCALE * 2 / self.art.scale
            size = max(1, round(group.get_width() * factor)), max(1, round(group.get_height() * factor))
            card.blit(self.shrink(group, size),
                      (round(FACE_CENTER[0] + gx * factor), round(FACE_CENTER[1] + gy * factor)))
        font = self.text.font(body_font)
        top = BASELINE - font.base
        if key.name:
            self.text.draw_layout(card, name_font, name, x, top, scale=1)
        self.text.draw_layout(card, body_font, body, x, top, scale=1, inline=inline)
        below = (len(body.lines) if body.lines else 1) * LINE_PITCH
        for extra in extras:
            # A gap, then the continuation (the "Tap here to ..." link) in the sender's font.
            below += PARAGRAPH_GAP
            self.text.draw_layout(card, name_font, extra, x, top + below, scale=1)
            below += len(extra.lines) * LINE_PITCH
        return card

    # shrink's results by (the source surface, size): the wall panel and the alert shrink the same faces every frame
    # (a Lanczos pass each, ~14 ms on a phone). The source is kept in the entry so its id cannot be reused meanwhile.
    _shrunk = {}

    @classmethod
    def shrink(cls, surface, size):
        """Resample down with premultiplied alpha (a plain filter smears the
        transparent pixels' color into the ring's thin lines)."""
        key = (id(surface), tuple(size))
        kept = cls._shrunk.get(key)
        if kept is None or kept[0] is not surface:
            kept = cls._shrunk[key] = (surface, cls._shrink(surface, size))
            while len(cls._shrunk) > 64:
                del cls._shrunk[next(iter(cls._shrunk))]
        return kept[1]

    @staticmethod
    def _shrink(surface, size):
        try:
            from PIL import Image
        except ImportError:
            return pygame.transform.smoothscale(surface, size)
        image = Image.frombytes('RGBA', surface.get_size(), pygame.image.tobytes(surface, 'RGBA'))
        image = image.resize(size, Image.Resampling.BOX if size[0] * 2 < surface.get_width() else Image.Resampling.LANCZOS)
        return pygame.image.frombytes(image.tobytes(), size, 'RGBA').convert_alpha()

    @staticmethod
    def slide(progress):
        """UIView's default ease-in-out over the 0.2 s slide."""
        p = min(1.0, max(0.0, progress))
        return p * p * (3 - 2 * p)

    def draw(self, engine, toast):
        """The alert as a frame-sized (768 x 1024 px) layer."""
        layer = pygame.Surface(FRAME, pygame.SRCALPHA).convert_alpha()
        card = self.card(self.key(engine, toast.message))
        offset = round(SLIDE_FROM * (1 - self.slide(toast.enter_progress)))
        layer.blit(card, (CARD_LEFT + offset, CARD_TOP))
        return layer
