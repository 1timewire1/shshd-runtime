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

# The rest of CoD's screens (CLAIRE_HART_SKIN_PLAN.md; owner, 2026-11-21: Classic's panel, the dark rows with the gold-edged
# highlight, Classic's bar as the timer, Romic Bold, chc revision 2): Classic's own UI pieces, kept at their own pixels, the
# spec saying where each is cut (the boxes' DENSITY doesn't apply: the renderer scales each to its place).
(UI_PANEL, UI_POPUP, UI_ROW, UI_ROW_LIT, UI_CAPSULE, UI_TIMER, UI_TIMER_FILL, UI_CLOSE, UI_CLOSE_PRESSED,
 UI_PILL_HOVER) = range(29109, 29119)
UI_SOURCES = {
    UI_PANEL: ('d6/d6bb0206-f11a-4329-a562-9de5f4302306.png', None),         # panel_background 718 x 498
    UI_POPUP: ('19/192aa5599.png', (1259, 3, 328, 244)),                   # UI_modal_backing: Classic's Yes/No popup
    UI_ROW: ('53/53c1157c-6d27-4017-85e5-b4bab356fb84.png', None),        # cmp_chapterresult_backing_scenecleared
    UI_ROW_LIT: ('15/15c463ceb.png', (1357, 410, 225, 82)),                # cmp_menu_selectedstate: the gold left edge
    UI_CAPSULE: ('18/18e2fa278.png', (381, 809, 494, 37)),                 # cmp_panelresult_scorecontainer
    UI_TIMER: ('19/192aa5599.png', (3, 3, 1250, 141)),                     # ui-top-combobacking
    UI_TIMER_FILL: ('19/192aa5599.png', (3, 150, 1249, 148)),              # ui-top-combobar
    UI_CLOSE: ('18/18e2fa278.png', (918, 660, 45, 45)),                    # btn_close_idle
    UI_CLOSE_PRESSED: ('18/18e2fa278.png', (763, 718, 45, 45)),            # btn_close_pressed
    UI_PILL_HOVER: ('17/170baf746.png', (3, 390, 209, 57)),               # btn_hover
}
UI_HALVED = (UI_TIMER, UI_TIMER_FILL)        # (stored at half their size: a timer bar is never that big on screen)
UI_COLOURS = {'title': (125, 66, 14), 'text': (239, 235, 226), 'gold': (255, 205, 78), 'lit': (238, 226, 90),
              'teal': (18, 224, 188), 'wrong': (240, 80, 70)}


def ui_pieces(root):
    """{resource: picture} of Classic's UI pieces (UI_SOURCES), cut from the mirror's files or atlases."""
    out = {}
    for resource, (path, rect) in UI_SOURCES.items():
        image = Image.open(root / path).convert('RGBA')
        if rect is not None:
            x, y, w, h = rect
            image = image.crop((x, y, x + w, y + h))
        out[resource] = scaled(image, 0.5) if resource in UI_HALVED else image
    return out


def ui_spec():
    """Where each UI piece is cut (its own pixels: left, top, right, bottom kept; the rest stretches), and the panel's header,
    tab and title band. A renderer that finds no `ui` (chc revision 1) keeps CoD's own art."""
    return {
        'panel': {'picture': UI_PANEL, 'size': [718, 498], 'caps': [60, 60], 'rows': [102, 402],
                  'tab': [180, 270, 450, 540], 'title': [6, 74]},
        'popup': {'picture': UI_POPUP, 'size': [328, 244], 'title': 62, 'text': [100, 182], 'buttons': 205},
        'row': {'picture': UI_ROW, 'slice': [37, 11, 37, 11]},
        'row_lit': {'picture': UI_ROW_LIT, 'slice': [12, 6, 12, 6]},
        'capsule': {'picture': UI_CAPSULE, 'slice': [18, 0, 18, 0]},
        'timer': {'back': UI_TIMER, 'fill': UI_TIMER_FILL, 'slice': [56, 0, 56, 0]},
        'close': [UI_CLOSE, UI_CLOSE_PRESSED], 'pill_lit': UI_PILL_HOVER, 'colours': UI_COLOURS,
    }


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
        'ui': ui_spec(),                                 # (chc revision 2: the other screens' pieces)
    }
    resources = {SPEC: json.dumps(spec, separators=(',', ':')).encode(), SPEAKER: png(body), TAB: png(tab),
                 NARRATOR: png(plain), RING: png(ring), DISC: png(disc),
                 PILL: png(atlas.crop(BUTTONS['idle'])), PILL_PRESSED: png(atlas.crop(BUTTONS['pressed'])),
                 SLOT: png(Image.open(root / SOURCES['slot']).convert('RGBA'))}
    resources.update({resource: png(picture) for resource, picture in ui_pieces(root).items()})
    return resources
