"""Claire Hart Dialogue: the art of the speech-bubble skin, cut from Claire Hart Classic's own (CLAIRE_HART_PLAN.md, Stage 0,
"Claire Hart's speech bubbles as a dialogue skin"; owner, 2026-11-19: a hybrid of Claire Hart's bubble and Romic with CoD's
attached portrait ring).

Claire Hart scales one big picture per box (textures/SD/dialog/speakerbox, narratorbox); CoD's boxes take the size of their
text. So the boxes are cut into corners and stretchable edges here and stored at DENSITY pixels a layout unit, with a spec
saying where to cut. The speaker box's tail (its left side) is dropped: its body is the right half, mirrored. Its name tab
is cut on its own (caps and a stretchable middle) to lie over the body's top edge, which it matches, being the same art.
The ring is new, drawn here in the box's style. The Play Now button (loading_atlas btn_idle, btn_pressed) is the Continue
pill and storyobj_backing the story objects' square.

    build(mirror) -> {resource: bytes}     (SPEC and the pictures after it; chc carries them: chslim.py --chc)
"""
import io
import json
from pathlib import Path

from PIL import Image, ImageDraw

SPEC = 29100                        # the spec, JSON; its pictures follow
SPEAKER, TAB, NARRATOR, RING, DISC, PILL, PILL_PRESSED, SLOT = range(29101, 29109)
DENSITY = 4                         # stored pixels a layout unit
ART_PER_UNIT = 12                   # Claire Hart's box pixels a CoD layout unit (its rim then about CoD's border's width)
TEXT = (112, 45, 25)                # the dialogue's text and names: the darkest letters in photos chc_03, 04 and 09
EMPHASIS = (166, 132, 22)           # CoD's emphasised words: one of Claire Hart's own text colours (driver.js textColors '#A68416')
NATIVE = 'raw/157/assets/resources/native/'
SOURCES = {'speaker': '08/081904fa-0350-48e6-86ea-d5b0f6c9a233.png', 'narrator': '87/8700dbaf-dbb6-4c2b-a147-ee58ba438310.png',
           'atlas': '17/170baf746.png', 'slot': 'fb/fb827b5d-5647-4bd4-baf2-28138c55dbcf.png'}
# In the speaker box's own pixels (2855 x 1752): its body without the tab (the rim's outer top at 311) and its tab, the tab cut
# a little into the body below its rim (412), so it covers the rim there; the tab's caps are its rounded ends and fillets.
SPEAKER_BODY = (169, 311, 2808, 1716)
SPEAKER_TAB = (520, 0, 2510, 430)
TAB_CAPS = (280, 280)
NAME_BAND = (20, 311)               # the tab's rows the name is centred in (its top to the body's top)
TAB_INSET = 150                     # the tab's pixels from each end to where its name may start
BUTTONS = {'idle': (3, 453, 212, 510), 'pressed': (218, 390, 427, 447)}


def png(image):
    out = io.BytesIO()
    image.convert('RGBA').save(out, 'PNG', optimize=True)
    return out.getvalue()


def scaled(image, factor):
    return image.resize((max(1, round(image.width * factor)), max(1, round(image.height * factor))), Image.LANCZOS)


def speaker_body(box):
    """The speaker box's body, its tail side replaced by its other side mirrored."""
    body = box.crop(SPEAKER_BODY)
    half = body.width // 2
    right = body.crop((body.width - half, 0, body.width, body.height))
    whole = Image.new('RGBA', (2 * half, body.height))
    whole.paste(right.transpose(Image.FLIP_LEFT_RIGHT), (0, 0))
    whole.paste(right, (half, 0))
    return whole


def ring_pictures():
    """The portrait ring and its disc in the boxes' style: the rim's dark green (a little translucent, as the boxes' is) with
    its lighter inner band, then the olive bevel; the disc the boxes' cream-green, lighter at the top. CoD's sizes: the ring 128
    units across, the disc 105."""
    k = DENSITY * 4                                     # drawn 4x over, then reduced: smooth edges
    size = 128 * k
    ring = Image.new('RGBA', (size, size))
    draw = ImageDraw.Draw(ring)
    c = size / 2
    for radius, colour in ((64.0, (32, 57, 55, 212)), (62.5, (51, 87, 82, 214)), (59.0, (55, 96, 90, 214)),
                           (57.5, (201, 201, 131, 255)), (56.0, (206, 209, 158, 255)), (54.5, (213, 220, 196, 255))):
        r = radius * k
        draw.ellipse((c - r, c - r, c + r, c + r), fill=colour)
    hole = 52.0 * k                                   # (inside the disc's edge: no gap between them)
    draw.ellipse((c - hole, c - hole, c + hole, c + hole), fill=(0, 0, 0, 0))
    ring = ring.resize((128 * DENSITY, 128 * DENSITY), Image.LANCZOS)
    size = 105 * k
    gradient = Image.new('RGBA', (1, size))
    top, bottom = (220, 226, 212), (191, 198, 150)
    for y in range(size):
        t = y / (size - 1)
        gradient.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)) + (255,))
    disc = gradient.resize((size, size))
    mask = Image.new('L', (size, size))
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    disc.putalpha(mask)
    return ring, disc.resize((105 * DENSITY, 105 * DENSITY), Image.LANCZOS)


def build(mirror):
    """The skin's resources from a Claire Hart Classic mirror (its folder)."""
    root = Path(mirror) / NATIVE
    factor = DENSITY / ART_PER_UNIT
    speaker = Image.open(root / SOURCES['speaker']).convert('RGBA')
    narrator = Image.open(root / SOURCES['narrator']).convert('RGBA')
    atlas = Image.open(root / SOURCES['atlas']).convert('RGBA')
    body, tab, plain = (scaled(image, factor) for image in (speaker_body(speaker), speaker.crop(SPEAKER_TAB), narrator))
    ring, disc = ring_pictures()
    px = lambda value: round(value * factor)                           # noqa: E731 (art pixels -> stored pixels)
    spec = {
        'version': 1, 'density': DENSITY, 'text': list(TEXT), 'emphasis': list(EMPHASIS),
        'fonts': {'body': 28004, 'bold': 28005},
        # Each box: its picture, the stored pixels its corners keep on each side (left, top, right, bottom; the rest
        # stretches), and the units it reaches past the text's rectangle on each side, as CoD's border does.
        'speaker': {'picture': SPEAKER, 'slice': [px(240), px(200), px(240), px(170)], 'outset': [10, 10, 10, 10]},
        'narrator': {'picture': NARRATOR, 'slice': [px(190), px(190), px(190), px(190)], 'outset': [10, 10, 10, 10]},
        # The tab: its caps (stored pixels, left and right) and the row where the body's outer top falls; the name is
        # centred in the band of rows `name`.
        # The tab: its size and caps (stored pixels, left and right), the row where the body's outer top falls, the band of
        # rows the name is centred in, and how far in from each end the name may start (past the fillet and the corner).
        'tab': {'picture': TAB, 'size': [tab.width, tab.height], 'caps': [px(TAB_CAPS[0]), px(TAB_CAPS[1])],
                'base': px(SPEAKER_BODY[1] - SPEAKER_TAB[1]), 'name': [px(NAME_BAND[0]), px(NAME_BAND[1])],
                'inset': px(TAB_INSET)},
        'ring': RING, 'disc': DISC, 'pill': [PILL, PILL_PRESSED], 'slot': SLOT,
    }
    return {SPEC: json.dumps(spec, separators=(',', ':')).encode(), SPEAKER: png(body), TAB: png(tab),
            NARRATOR: png(plain), RING: png(ring), DISC: png(disc),
            PILL: png(atlas.crop(BUTTONS['idle'])), PILL_PRESSED: png(atlas.crop(BUTTONS['pressed'])),
            SLOT: png(Image.open(root / SOURCES['slot']).convert('RGBA'))}
