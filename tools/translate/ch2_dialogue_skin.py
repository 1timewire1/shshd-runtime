"""Secret in the Shadows UI: the art of the sequel's dialogue skin for Cause of Death (CLAIRE_HART_PLAN.md S2b; owner,
2026-11-24: a skin of its own beside Claire Hart Classic's, chosen by Claire Hart UI's Auto or by name).

The sequel's dialogue box (its dialogboxprefab, ENGINE 4.4): a dark teal frame (`cmp_scriptBacking_dialog`, 534 x 113, a
one-pixel mint rim, the speaker's name tab rising from its top left with a slanted right end; the narrator's
`cmp_scriptBacking_narrator` has none) holding a cream paper (`cmp_scriptBacking_paper`, 510 x 80, 90% opaque), the name
upper-cased in teal Roboto Slab Bold on the tab, the text #212121 Roboto Condensed. Its art is the 800 x 600 game's, so the
boxes are redrawn here from its measured colours and shapes at DENSITY pixels a CoD unit (sharp at any size), as Classic's
ring is; the frame keeps its corners and rims and stretches between them as CoD's boxes take the size of their text.

    build(mirror) -> {resource: bytes}     (SPEC and the pieces after it, in ch2: claire_hart_shadows.py addon)

The units: the game's 600-pixel height is CoD's 512-unit frame, so a game pixel is UNIT (0.853) units.
"""
import csv
import io
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

SPEC = 29100                        # the spec, JSON; its pieces follow (as chc's skin's)
SPEAKER, TAB, NARRATOR, RING, DISC, PILL, PILL_PRESSED, SLOT = range(29101, 29109)
FONT_BODY, FONT_BOLD, FONT_ITALIC = 29190, 29191, 29192
DENSITY = 4                         # stored pixels a CoD unit
UNIT = 512 / 600                    # CoD units a game pixel
FRAME = (0, 48, 41)                 # cmp_scriptBacking_*: the frame's teal (opaque in the art; the box node draws it at 204)
FRAME_ALPHA = 232                   # (a little see-through, as the game's: but the tab overlaps the box's top, so not 204)
RIM = (140, 246, 200, 210)          # its one-pixel mint rim
PAPER = (239, 236, 226, 232)        # cmp_scriptBacking_paper
TEXT = (33, 33, 33)                 # the driver's #212121
NAME = (27, 245, 208)               # the header's colour (dialogboxprefab: 0xFFD0F51B, ABGR)
EMPHASIS = (110, 40, 170)           # CoD's emphasised words: the sequel's purple (its PLAY and CONTINUE buttons)
# In CoD units: the frame's corner radius, the paper's inset from the frame's outer edge (12 game pixels at the sides,
# 9 above; the game's box stands on the screen's foot, CoD's floats, so below as above), the paper's radius, and how far
# the box reaches past its text (the paper's own margin, 5 game pixels, plus the inset).
RADIUS, PAPER_SIDE, PAPER_TOP, PAPER_RADIUS = 4.0, 10.0, 8.0, 2.5
OUTSET = [15, 13, 15, 13]
CAP = 14                            # units each corner keeps when the box stretches
# The tab (the game's 23 pixels above the box, its right end slanting over 22): its height above the box's outer top,
# how far it reaches into the box (covering the rim there), its slant, the band its name is centred in, its insets.
TAB_HIGH, TAB_INTO, TAB_SLANT, TAB_RADIUS = 19.5, 2.0, 18.0, 3.5
TAB_NAME = (3.0, 18.5)
TAB_INSET = 12.0
FONT_FILES = {FONT_BODY: 'font/Roboto_Condensed/RobotoCondensed-Regular', FONT_BOLD: 'font/Roboto_Slab/RobotoSlab-Bold',
              FONT_ITALIC: 'font/Roboto_Condensed/RobotoCondensed-Italic'}
FRAMES = 'claire_hart_shadows_ui_frames.json'     # (beside the mirror: claire_hart_shadows_frames.py)


def png(image):
    out = io.BytesIO()
    image.save(out, 'PNG', optimize=True)
    return out.getvalue()


def px(units):
    return round(units * DENSITY)


def rounded(draw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def box_picture(paper=True):
    """A box as CoD stretches it: the frame with its rim, the paper inside, CAP units kept at each corner."""
    over = 4                                                  # drawn 4x over, then reduced: smooth edges
    size = px(2 * CAP + 2) * over
    image = Image.new('RGBA', (size, size))
    draw = ImageDraw.Draw(image)
    s = DENSITY * over
    rounded(draw, (0, 0, size - 1, size - 1), RADIUS * s, RIM)
    rounded(draw, (s * 0.85, s * 0.85, size - 1 - s * 0.85, size - 1 - s * 0.85), (RADIUS - 0.85) * s,
            FRAME + (FRAME_ALPHA,))
    if paper:
        rounded(draw, (PAPER_SIDE * s, PAPER_TOP * s, size - 1 - PAPER_SIDE * s, size - 1 - PAPER_TOP * s),
                PAPER_RADIUS * s, PAPER)
    return image.resize((size // over, size // over), Image.LANCZOS)


def tab_picture():
    """The name tab: flat top, rounded top-left corner, its right end slanting down to the box; its rim on its top, left and
    slant, none along its foot (it runs on into the box)."""
    over = 4
    s = DENSITY * over
    width = (2 * TAB_INSET + TAB_SLANT + 20) * s
    height = (TAB_HIGH + TAB_INTO) * s
    image = Image.new('RGBA', (round(width), round(height)))
    draw = ImageDraw.Draw(image)

    def shape(inset):
        r = (TAB_RADIUS - inset / s) * s
        top, left, foot = inset, inset, height + s           # (its foot runs past the picture's edge: no rim there)
        right_top, right_foot = width - TAB_SLANT * s - inset * 1.3, width - inset * 1.3   # (the slant's rim as thick as the others)
        points = [(left, foot), (left, top + r)]
        for k in range(9):                                    # the rounded corner, a quarter circle
            a = math.pi + k * math.pi / 2 / 8
            points.append((left + r + r * math.cos(a), top + r + r * math.sin(a)))
        points += [(right_top - r * 0.5, top), (right_top, top + r * 0.3), (right_foot, foot)]
        return points
    draw.polygon(shape(0), fill=RIM)
    draw.polygon(shape(0.85 * s), fill=FRAME + (FRAME_ALPHA,))
    return image.resize((round(width / over), round(height / over)), Image.LANCZOS)


def ring_pictures():
    """The portrait ring and its disc in the box's style (CoD's sizes: the ring 128 units across, the disc 105): the frame's
    teal with a mint rim in and out; the disc the sequel's photo backing, grey-mauve to plum, lighter at the top."""
    k = DENSITY * 4
    size = 128 * k
    ring = Image.new('RGBA', (size, size))
    draw = ImageDraw.Draw(ring)
    c = size / 2
    for radius, colour in ((64.0, RIM), (63.1, FRAME + (240,)), (56.0, RIM), (55.1, FRAME + (240,))):
        r = radius * k
        draw.ellipse((c - r, c - r, c + r, c + r), fill=colour)
    hole = 52.0 * k
    draw.ellipse((c - hole, c - hole, c + hole, c + hole), fill=(0, 0, 0, 0))
    ring = ring.resize((128 * DENSITY, 128 * DENSITY), Image.LANCZOS)
    size = 105 * k
    gradient = Image.new('RGBA', (1, size))
    top, bottom = (132, 126, 124), (72, 48, 62)
    for y in range(size):
        t = y / (size - 1)
        gradient.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)) + (255,))
    disc = gradient.resize((size, size))
    mask = Image.new('L', (size, size))
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    disc.putalpha(mask)
    return ring, disc.resize((105 * DENSITY, 105 * DENSITY), Image.LANCZOS)


# The rest of CoD's screens (as Classic's `ui`, desktop_ch_ui.ChUi; owner, 2026-11-24): the sequel's dark teal glass panels
# with their mint rim (its round summary, its selector), a centred title tab like the dialogue's, its rows with the selector's
# orange edge on the picked one, its purple buttons, its teal accents and Roboto Slab Bold. Drawn here at their own pixels
# (the renderer scales each to its place), the spec saying where each is cut.
(UI_PANEL, UI_POPUP, UI_ROW, UI_ROW_LIT, UI_CAPSULE, UI_TIMER, UI_TIMER_FILL, UI_CLOSE, UI_CLOSE_PRESSED,
 UI_PILL_HOVER) = range(29109, 29119)
PANEL_SIZE, PANEL_RADIUS, PANEL_RIM = (720, 500), 18, 3
PANEL_TAB = (210, 250, 470, 510)          # the title tab's columns: its slanted ends 40 across
PANEL_TAB_HIGH = 46                       # ...its height over the panel's top edge
PANEL_ROWS = (100, 404)                   # the header and footer the panel keeps when it stretches
POPUP_SIZE = (360, 250)
UI_COLOURS = {'title': list(NAME), 'text': [234, 240, 236], 'gold': list(NAME), 'lit': [255, 196, 92],
              'teal': list(NAME), 'wrong': [240, 80, 70]}
GLASS = FRAME + (236,)
ROW, ROW_LIT, EDGE = (0, 36, 31, 230), (6, 74, 63, 240), (236, 150, 46, 255)


def supersampled(size, draw_on, over=3):
    """A picture `size` drawn by `draw_on(draw, scale)` at `over` times, then reduced (smooth edges)."""
    image = Image.new('RGBA', (size[0] * over, size[1] * over))
    draw_on(ImageDraw.Draw(image), over)
    return image.resize(size, Image.LANCZOS)


def panel_picture():
    """The panel: its body below the tab, rounded, glass teal in a mint rim; the tab centred on its top with slanted ends,
    the rim running round both (the tab's foot open into the body)."""
    w, h = PANEL_SIZE
    t0, t1, t2, t3 = PANEL_TAB
    top = PANEL_TAB_HIGH

    def draw_on(draw, k):
        for inset, colour in ((0, RIM), (PANEL_RIM, GLASS)):
            i = inset * k
            draw.rounded_rectangle((i, top * k + i, w * k - 1 - i, h * k - 1 - i), radius=(PANEL_RADIUS - inset) * k,
                                   fill=colour)
            draw.polygon([(t0 * k + i * 1.4, (top + PANEL_RIM + 3) * k), (t1 * k + i * 0.4, i), (t2 * k - i * 0.4, i),
                          (t3 * k - i * 1.4, (top + PANEL_RIM + 3) * k)], fill=colour)
    return supersampled(PANEL_SIZE, draw_on)


def popup_picture():
    w, h = POPUP_SIZE

    def draw_on(draw, k):
        draw.rounded_rectangle((0, 0, w * k - 1, h * k - 1), radius=16 * k, fill=RIM)
        draw.rounded_rectangle((3 * k, 3 * k, w * k - 1 - 3 * k, h * k - 1 - 3 * k), radius=13 * k, fill=GLASS)
        draw.line((24 * k, 84 * k, (w - 24) * k, 84 * k), fill=RIM[:3] + (110,), width=2 * k)    # (under the title)
    return supersampled(POPUP_SIZE, draw_on)


def row_picture(lit=False):
    size = (240, 60)

    def draw_on(draw, k):
        if lit:
            draw.rounded_rectangle((0, 0, size[0] * k - 1, size[1] * k - 1), radius=6 * k, fill=ROW_LIT)
            draw.rounded_rectangle((0, 0, 7 * k, size[1] * k - 1), radius=3 * k, fill=EDGE)
        else:
            draw.rounded_rectangle((0, 0, size[0] * k - 1, size[1] * k - 1), radius=6 * k, fill=RIM[:3] + (60,))
            draw.rounded_rectangle((2 * k, 2 * k, size[0] * k - 1 - 2 * k, size[1] * k - 1 - 2 * k), radius=5 * k,
                                   fill=ROW)
    return supersampled(size, draw_on)


def capsule_picture():
    size = (240, 40)

    def draw_on(draw, k):
        draw.rounded_rectangle((0, 0, size[0] * k - 1, size[1] * k - 1), radius=20 * k, fill=RIM)
        draw.rounded_rectangle((2 * k, 2 * k, size[0] * k - 1 - 2 * k, size[1] * k - 1 - 2 * k), radius=18 * k,
                               fill=(0, 30, 26, 245))
    return supersampled(size, draw_on)


def timer_pictures():
    size = (600, 40)

    def back(draw, k):
        draw.rounded_rectangle((0, 0, size[0] * k - 1, size[1] * k - 1), radius=20 * k, fill=RIM)
        draw.rounded_rectangle((2 * k, 2 * k, size[0] * k - 1 - 2 * k, size[1] * k - 1 - 2 * k), radius=18 * k,
                               fill=(0, 24, 21, 250))

    # The fill: the round's teal bar, lighter at its top, a capsule inside the back's rim (its ends rounded as the bar's).
    k = 3
    w, h = size[0] * k, size[1] * k
    fill = Image.new('RGBA', (w, h))
    lines = ImageDraw.Draw(fill)
    for y in range(5 * k, h - 5 * k):
        t = (y - 5 * k) / (h - 10 * k)
        lines.line((0, y, w, y), fill=tuple(round(a + (b - a) * t) for a, b in zip((120, 250, 220), (20, 170, 140))) + (255,))
    mask = Image.new('L', (w, h))
    ImageDraw.Draw(mask).rounded_rectangle((5 * k, 5 * k, w - 1 - 5 * k, h - 1 - 5 * k), radius=15 * k, fill=255)
    fill.putalpha(mask)
    return supersampled(size, back), fill.resize(size, Image.LANCZOS)


def ui_spec():
    """Where each UI piece is cut, as chc's `ui` (desktop_ch_ui.ChUi reads it)."""
    return {
        'panel': {'picture': UI_PANEL, 'size': list(PANEL_SIZE), 'caps': [PANEL_RADIUS + 12, PANEL_RADIUS + 12],
                  'rows': list(PANEL_ROWS), 'tab': list(PANEL_TAB), 'title': [4, PANEL_TAB_HIGH]},
        'popup': {'picture': UI_POPUP, 'size': list(POPUP_SIZE), 'title': 50, 'text': [98, 182], 'buttons': 214},
        'row': {'picture': UI_ROW, 'slice': [10, 10, 10, 10]},
        'row_lit': {'picture': UI_ROW_LIT, 'slice': [12, 10, 10, 10]},
        'capsule': {'picture': UI_CAPSULE, 'slice': [20, 0, 20, 0]},
        'timer': {'back': UI_TIMER, 'fill': UI_TIMER_FILL, 'slice': [20, 0, 20, 0], 'shrink': True},
        'close': [UI_CLOSE, UI_CLOSE_PRESSED], 'pill_lit': UI_PILL_HOVER, 'colours': UI_COLOURS,
    }


def ui_pieces(mirror, frames):
    timer_back, timer_fill = timer_pictures()
    return {UI_PANEL: panel_picture(), UI_POPUP: popup_picture(), UI_ROW: row_picture(), UI_ROW_LIT: row_picture(True),
            UI_CAPSULE: capsule_picture(), UI_TIMER: timer_back, UI_TIMER_FILL: timer_fill,
            UI_CLOSE: frame_picture(mirror, frames, 'btn_global_close_idle'),
            UI_CLOSE_PRESSED: frame_picture(mirror, frames, 'btn_global_close_press'),
            UI_PILL_HOVER: frame_picture(mirror, frames, 'btn_primary_hover')}


def frame_picture(mirror, frames, name):
    """A named UI frame of the game's atlases, unrotated (claire_hart_shadows_frames.py's table)."""
    frame = frames[name]
    x, y, w, h = frame['rect']
    with Image.open(Path(mirror) / frame['texture']) as image:
        image = image.convert('RGBA')
        if frame['rotated']:
            return image.crop((x, y, x + h, y + w)).transpose(Image.ROTATE_90)
        return image.crop((x, y, x + w, y + h))


def bundle_file(mirror, real_path):
    with open(Path(mirror) / 'bundle_names.csv', encoding='utf-8-sig', newline='') as file:
        row = next(r for r in csv.DictReader(file) if r['real_path'] == real_path and r['part'] == 'native')
    return Path(mirror) / row['local_path']


def spec():
    cap = px(CAP)
    return {
        'version': 1, 'density': DENSITY, 'text': list(TEXT), 'emphasis': list(EMPHASIS), 'name_colour': list(NAME),
        'name_upper': True,
        'fonts': {'body': FONT_BODY, 'bold': FONT_BOLD, 'italic': FONT_ITALIC, 'ui': FONT_BOLD},
        'font_names': {'body': 'CH2Roboto16', 'narration': 'CH2RobotoItalic16', 'name': 'CH2RobotoBold17',
                       'pill': 'CH2RobotoBold11'},
        'speaker': {'picture': SPEAKER, 'slice': [cap, cap, cap, cap], 'outset': OUTSET},
        'narrator': {'picture': NARRATOR, 'slice': [cap, cap, cap, cap], 'outset': OUTSET},
        'tab': {'picture': TAB, 'size': None, 'caps': [px(TAB_RADIUS + 2), px(TAB_SLANT + 2)],
                'base': px(TAB_HIGH), 'name': [px(TAB_NAME[0]), px(TAB_NAME[1])], 'inset': px(TAB_INSET)},
        'ring': RING, 'disc': DISC, 'pill': [PILL, PILL_PRESSED], 'slot': SLOT,
        'pill_label': 'CONTINUE', 'pill_text': [255, 255, 255],
        'ui': ui_spec(),
    }


def build(mirror):
    """The sequel's skin resources from its mirror (and the UI frames table beside it)."""
    mirror = Path(mirror)
    frames = json.loads((mirror / FRAMES).read_text(encoding='utf-8'))
    speaker, narrator, tab = box_picture(), box_picture(), tab_picture()
    ring, disc = ring_pictures()
    out = spec()
    out['tab']['size'] = [tab.width, tab.height]
    resources = {SPEC: json.dumps(out, separators=(',', ':')).encode(), SPEAKER: png(speaker), NARRATOR: png(narrator),
                 TAB: png(tab), RING: png(ring), DISC: png(disc),
                 PILL: png(frame_picture(mirror, frames, 'btn_primary_idle')),
                 PILL_PRESSED: png(frame_picture(mirror, frames, 'btn_primary_press')),
                 SLOT: png(frame_picture(mirror, frames, 'cmp_storyObject_backing'))}
    for resource, real_path in FONT_FILES.items():
        resources[resource] = bundle_file(mirror, real_path).read_bytes()
    resources.update({resource: png(picture) for resource, picture in ui_pieces(mirror, frames).items()})
    return resources
