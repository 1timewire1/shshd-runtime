"""New Rules' minigame arena drawn from the X1i build's own art (480x800, about 1.5x New Rules' WinMo art), for the New
Rules addon (reference/Other Games/docs/NR_ARENA.md §5).

The Java panel (renamed `class_13`) draws the arena from New Rules' UI layout bank (resource 2) and the UI packs in its
image slots (`class_6.method_185` / `method_247`): a scrolling background tile, layout 31 (the stripe, the table, its
stand and the bottom band) and layout 66 (the top band with the timer and score dials) at layout 31's node 47. Those
static layers are drawn here once; the moving parts (items, meter, digits, buttons, popups) are exported as frames, and
every node the panel places things at is measured, so the player only composes pictures.
"""
from PIL import Image

import nr_art
from exp_runtime.ui_assets import LayoutBank, Rect

LAYOUT_BANK = 2
SCREEN = (480, 650)                     # the X1i game area: 480 wide, above its 150-pixel soft-key bar (layout 86)
STATIC_BELOW = 54                       # rows of the static screen below it, for the base's added row (_extend_base)
# Columns of the static screen either side of it: the table and the bottom band reach past New Rules' 480 pixels, and
# the player's frame is a few wider, so they run on to its edges rather than stopping short (owner, 2026-10-30).
STATIC_MARGIN = 8
# The UI packs in the layout bank's image slots (class_6.method_185, method_247 and the boot sequence), with the RGB565
# tint each is loaded with: New Rules' default theme (method_184(true); King of Diss never changes it, service 38).
THEME = (15154, -166, -2416, -2416, -567, -342)
SLOT_PACKS = {0: (4, None), 1: (106, THEME[4]), 2: (83, THEME[3]), 3: (65, THEME[1]), 4: (146, None),
              5: (62, THEME[0]), 6: (173, -342), 7: (183, -567), 8: (123, THEME[5]), 9: (73, THEME[2]),
              10: (140, None), 11: (251, None), 12: (189, None)}
BACKGROUND_SLOT = 5                     # its frame 0 tiles the screen, scrolling 1 pixel a 100 ms over 128 (method_358)
ARENA_LAYOUT, BAND_LAYOUT, BAND_NODE = 31, 66, 47
STRIPE_NODE = 1                         # layout 31's stripe (layout 26) down the middle, behind the table
TIMER_DIAL, SCORE_DIAL = 33, 34         # layout 66's dials, hidden until the panel shows them
ITEM_ICONS = 8018                       # the 29 minigame item pictures (o.java's part IDs 0-28 -> 8018-8046)
METER_PACK, DIAL_PACK = 146, 51         # the meter strip (class_6.field_227) and the dial art (field_203)


def slots(source):
    packs = {slot: nr_art.Pack(source[rid], source, tint=tint) for slot, (rid, tint) in SLOT_PACKS.items()
             if rid in source}
    if BASE_SLOT in packs:
        _extend_base(packs[BASE_SLOT])
    return packs


# The table's base (slot 7's composite -1) ends at row 626, where the X1i's soft-key bar began; the frame here goes on
# below. Its legs are rows of 54-pixel slices: each row the outer edge (frames 0 and 3) moves 27 pixels out and the
# inner one (the last of frames 1 and 2) 18, one slice more filling between. One more row continuing both edges (owner,
# 2026-10-30), and the fills under it as long, reach the bottom.
BASE_SLOT, BASE_ROWS_ADDED = 7, 1
LEGS = ((0, 1, min, max), (3, 2, max, min))     # each leg: (outer frame, inner frame, its outer side, its inner side)


def _extend_base(pack):
    """The base composite with BASE_ROWS_ADDED more rows: each leg's outer slice and its inner slices again, as far on
    as each edge moved from the row before, with a slice more at the inner edge."""
    parts = pack.groups[0]
    rows = sorted({dy for _, _, dy in parts})
    if len(rows) < 2:
        return
    before, last = rows[-2], rows[-1]
    height = last - before

    def xs(frame, dy):
        return [x for f, x, y in parts if f == frame and y == dy]
    added, shifts = [], []
    for outer, inner, out_side, in_side in LEGS:
        if not (xs(outer, last) and xs(outer, before) and xs(inner, last) and xs(inner, before)):
            return
        out_shift = out_side(xs(outer, last)) - out_side(xs(outer, before))
        in_shift = in_side(xs(inner, last)) - in_side(xs(inner, before))
        shifts.append(out_shift)
        for k in range(1, BASE_ROWS_ADDED + 1):
            dy = last + k * height
            added += [(outer, x + k * out_shift, dy) for x in xs(outer, last)]
            slices = {x + k * out_shift for x in xs(inner, last)} | {in_side(xs(inner, last)) + k * in_shift}
            # From the outside in, as the composite lists them: each slice covers the lit edge of the one before.
            added += [(inner, x, dy) for x in sorted(slices, reverse=in_side is min)]
    pack.groups[0] = parts + added
    pack.base_extension = (shifts[0] * BASE_ROWS_ADDED, shifts[1] * BASE_ROWS_ADDED, height * BASE_ROWS_ADDED)


def extended_bank(source, packs):
    """The layout bank with the base's node grown to hold _extend_base's rows (its box as much wider each side and
    taller as the composite's bounding box grew), and each fill that ends with it continued below in a fill of its
    own, set out as far as the legs move, so the box between them widens with them. The added nodes renumber the ones
    after them (node_rect), so node boxes are looked up in the original bank; this one is for drawing."""
    from dataclasses import replace
    bank = LayoutBank.parse(source[LAYOUT_BANK])
    left, right, taller = getattr(packs.get(BASE_SLOT), 'base_extension', (0, 0, 0))
    if not taller:
        return bank
    layouts = list(bank.layouts)
    for i, layout in enumerate(layouts):
        base = next((n for n in layout.nodes if n.kind == 1 and tuple(n.payload) == (BASE_SLOT, -1)), None)
        if base is None:
            continue
        bottom = base.base[3]
        nodes = []
        for n in layout.nodes:
            if n is base:
                x1, y1, x2, y2 = n.base
                n = replace(n, base=(x1 + left, y1, x2 + right, y2 + taller))
            nodes.append(n)
            if n.kind in (2, 3, 4) and n.base[3] == bottom:
                x1, _, x2, y2 = n.base
                nodes.append(replace(n, base=(x1 + left, y2, x2 + right, y2 + taller)))
        layouts[i] = replace(layout, nodes=tuple(nodes))
    return replace(bank, layouts=tuple(layouts))


def node_rect(bank, layout_id, index, rect):
    """Node `index` of a layout drawn into `rect`, numbered as the Java numbers them (`w.a(int, short[])`): 0 is the
    layout itself, then each node in turn, a nested layout's own nodes following it. None when there is no such node."""
    found = _walk(bank, layout_id, index, rect)
    return found if isinstance(found, Rect) else None


def _walk(bank, layout_id, index, rect):
    if index == 0:
        return rect
    layout = bank.layouts[layout_id]
    remaining = index - 1
    for node in layout.nodes:
        child = node.rectangle(rect, (layout.width, layout.height))
        if node.kind != 7:
            if remaining == 0:
                return child
            remaining -= 1
            continue
        found = _walk(bank, node.payload[0], remaining, child)
        if isinstance(found, Rect):
            return found
        remaining -= found
    return index - remaining                    # how many nodes this layout held


def draw(canvas, bank, layout_id, rect, packs, show=frozenset(), hide=frozenset(), _first=1):
    """A layout's nodes into `rect` as `w.a(v, ...)` draws them (class_0.method_14): image nodes (kind 1: slot,
    frame or composite) tiled over their rectangles (from the right with flag 0x40, the bottom with 0x80), colour fills
    (kinds 2-4: the bank's colour, its low 24 bits), outlines (kind 5) and nested layouts (kind 7). A node shows with
    flag 0x10, or when its index (node_rect's numbering) is in `show`, unless it is in `hide`. Returns how many nodes
    it numbered."""
    from PIL import ImageDraw
    layout = bank.layouts[layout_id]
    index = _first
    for node in layout.nodes:
        child = node.rectangle(rect, (layout.width, layout.height))
        visible = (bool(node.flags & 16) or index in show) and index not in hide
        if node.kind == 7:
            count = draw(canvas, bank, node.payload[0], child, packs, show if visible else frozenset(),
                         hide if visible else frozenset(range(index + 1, index + 10000)), index + 1) if visible \
                else _count(bank, node.payload[0])
            index += 1 + count
            continue
        if visible and child.width > 0 and child.height > 0:
            if node.kind == 1 and node.payload[0] in packs:
                # A frame, or a composite (-k-1, such as the table's base and legs) tiled by its bounding box
                # (class_4.method_106 draws each copy with method_109(..., false)).
                found = _group_image(packs[node.payload[0]], node.payload[1])
                if found is not None:
                    nr_art.tile(canvas, found[0], (child.x, child.y, child.width, child.height),
                                bool(node.flags & 64), bool(node.flags & 128))
            elif node.kind in (2, 3, 4, 5) and 0 <= node.payload[0] < len(bank.colors):
                colour = bank.colors[node.payload[0]] & 0xFFFFFF
                rgb = (colour >> 16, colour >> 8 & 255, colour & 255, 255)
                box = (child.x, child.y, child.x + child.width - 1, child.y + child.height - 1)
                if node.kind == 5:
                    ImageDraw.Draw(canvas).rectangle(box, outline=rgb)
                else:
                    ImageDraw.Draw(canvas).rectangle(box, fill=rgb)
        index += 1
    return index - _first


def _count(bank, layout_id):
    total = 0
    for node in bank.layouts[layout_id].nodes:
        total += 1 + (_count(bank, node.payload[0]) if node.kind == 7 else 0)
    return total


def compose(source, show=(), hide=()):
    """The arena's static screen (SCREEN, with STATIC_MARGIN columns each side and STATIC_BELOW rows under it, RGBA;
    the screen's origin at (STATIC_MARGIN, 0)): layout 31 and the top band, without
    the scrolling background (the player tiles it underneath). `show`: layout 31's hidden nodes to draw too; `hide`: its
    visible ones to leave out (STRIPE_NODE, where the player draws the dialogue screens' frame instead). Both are
    numbered in the extended bank (extended_bank), the same as node_rect's up to the table's base."""
    packs = slots(source)
    bank = extended_bank(source, packs)
    width, height = SCREEN
    m = STATIC_MARGIN
    canvas = Image.new('RGBA', (width + 2 * m, height + STATIC_BELOW), (0, 0, 0, 0))
    draw(canvas, bank, ARENA_LAYOUT, Rect(m, 0, width, height), packs, frozenset(show), frozenset(hide))
    band = node_rect(LayoutBank.parse(source[LAYOUT_BANK]), ARENA_LAYOUT, BAND_NODE, Rect(m, 0, width, height))
    draw(canvas, bank, BAND_LAYOUT, Rect(m, band.y, width, band.height), packs)
    return canvas


def background_tile(source):
    return slots(source)[BACKGROUND_SLOT].frames[0]


# -- the skin the player draws from ---------------------------------------------------------------------------------
# Layouts the player draws itself, at sizes that change: the text item box (25, `o.a(25)`), the bubble (70) and the
# dials (33 timer, 34 score), with the layouts they nest; 27 is a menu's highlighted row (class_6.method_239).
# 11 (the table), 66 (the top band) and 67 (the bottom band, with the stand) for the entrance (class_13.method_383).
DRAWN_LAYOUTS = (11, 25, 27, 33, 34, 66, 67, 70)
# Layout 31's nodes the panel places things at (node_rect numbering), and layout 66's.
ARENA_NODES = {'field': 76, 'wide': 88, 'band': 47, 'bottom_band': 14, 'table': 69,
               'ok': 77, 'second': 72, 'left': 78, 'right': 79, 'hint': 87,
               'hud1_label': 82, 'hud1_item': 83, 'hud1_label_alt': 84, 'hud1_item_alt': 85, 'hud1_text': 86,
               'hud2_label': 42, 'hud2_item': 43, 'hud2_label_alt': 44, 'hud2_item_alt': 45, 'hud2_text': 46}
# The dials are layouts 33 (timer) and 34 (score), drawn into 'timer' and 'meter'.
BAND_NODES = {'hud0_label': 11, 'hud0_item': 12, 'hud0_label_alt': 13, 'hud0_item_alt': 14, 'hud0_text': 15,
              'timer': 16, 'meter': 19, 'meter_frame': 20}
# Where a marker sits on the score dial for each meter value (class_13's static tables), X1i pixels.
MARKER_X = (43, 50, 51, 45, 32, 20, 9, 9, 16, 29)
MARKER_Y = (11, 21, 36, 46, 52, 50, 38, 20, 11, 7)
# A button's fill under its picture (class_13's paint): while pressed, OK's and the second's feedback (708) green or
# red; else orange in the alternate style (buttons bit 0), or light purple while pressed and dark when not.
BUTTON_COLOURS = dict(right=0x33FF33, wrong=0xFF3333, pressed=0x9966FF, idle=0x6600CC, alternate=0xFF9933)
METER_SLOT, TIMER_SLOT = 4, 2           # pack 146 (meter, markers, plates, hint) and pack 83 (the timer's 17 steps)
MENU_SLOT = 0                           # pack 4 (class_6.field_202): a menu's arrow and bullets
BUBBLE_SLOT = 8                         # pack 123 (class_6.field_209): the bubble's frame and its pointer sequences
# The panel's fonts (class_6's boot sequence: t.a(InputStream, extra)), resource -> the extra pixels each glyph
# advances.
# 56 is field_229 and, after the boot swaps it in, field_231 too; 61 is field_232 (the score digits); 59 is field_230;
# 57 is field_234 (the info box). An item's font byte picks 0 -> 56, 1 -> 61, 2 -> 59, 3 -> 56 (o.a(t)).
FONTS = {56: 0, 57: 0, 59: 1, 61: 0}
ITEM_FONTS = (56, 61, 59, 56)
SCORE_FONT, INFO_FONT = 61, 57


def read_font(data):
    """A New Rules bitmap font (t.a(InputStream, int)): the space width, line gap, tracking (signed), glyph height and
    {character code: RGBA glyph} (palette index 0 is clear)."""
    import struct
    space, gap, track, count, height = struct.unpack_from('>BBbhB', data, 0)
    at = 6
    chars = data[at:at + count]
    at += count
    (colours,) = struct.unpack_from('>h', data, at)
    palette = data[at + 2:at + 2 + colours * 3]
    at += 2 + colours * 3
    (total,) = struct.unpack_from('>h', data, at)
    at += 2
    glyphs = {}
    for code in chars[:total]:
        width = data[at]
        at += 1
        if width == 0:
            continue
        rows = data[at]
        pixels = data[at + 1:at + 1 + width * rows]
        at += 1 + width * rows
        image = Image.new('RGBA', (width, rows), (0, 0, 0, 0))
        image.putdata([(0, 0, 0, 0) if i == 0 else (palette[i * 3], palette[i * 3 + 1], palette[i * 3 + 2], 255)
                       for i in pixels])
        glyphs[code] = image
    return dict(space=space, gap=gap, track=track, height=height, glyphs=glyphs)


def _group_image(pack, index):
    """A frame or a composite (-k-1) drawn on its own: (image, offset of its origin), or None."""
    if index >= 0:
        frame = pack.frames[index] if index < len(pack.frames) else None
        return (frame, (0, 0)) if frame is not None else None
    parts = pack.groups[-index - 1] if -index - 1 < len(pack.groups) else []
    boxes = []
    for frame, dx, dy in parts:
        found = _group_image(pack, frame)
        if found is not None:
            image, (ox, oy) = found
            boxes.append((image, dx + ox, dy + oy))
    if not boxes:
        return None
    left = min(x for _, x, _ in boxes)
    top = min(y for _, _, y in boxes)
    right = max(x + i.width for i, x, _ in boxes)
    bottom = max(y + i.height for i, _, y in boxes)
    canvas = Image.new('RGBA', (right - left, bottom - top), (0, 0, 0, 0))
    for image, x, y in boxes:
        canvas.alpha_composite(image, (x - left, y - top))
    return canvas, (left, top)


def build_skin(source, backdrop=None):
    """The arena skin for the addon: {name: bytes} with 'skin.json' (node rectangles, layouts, sprite table, colours),
    'static.png', 'tile.png' and 'atlas.png' (every sprite the player draws). With `backdrop` (a picture of the whole
    3:4 frame: the dialogue screens' backdrop without its bars, nr_art.Art.backdrop), 'frame.png' too, which the player
    draws behind the arena in place of the scrolling tile, and the static screen leaves out its own stripe."""
    import json
    packs = slots(source)
    bank = extended_bank(source, packs)
    original = LayoutBank.parse(source[LAYOUT_BANK])     # node numbering: the extension's fills renumber the rest
    width, height = SCREEN
    screen = Rect(0, 0, width, height)
    band = node_rect(original, ARENA_LAYOUT, BAND_NODE, screen)
    band_rect = Rect(0, band.y, width, band.height)
    nodes = {name: node_rect(original, ARENA_LAYOUT, index, screen) for name, index in ARENA_NODES.items()}
    nodes.update({name: node_rect(original, BAND_LAYOUT, index, band_rect) for name, index in BAND_NODES.items()})
    sprites, images = {}, []

    def add(name, found):
        if found is not None:
            image, offset = found
            sprites[name] = dict(index=len(images), offset=list(offset))
            images.append(image)

    icons = nr_art.Pack(source[ITEM_ICONS], source)
    for i in range(len(icons.frames)):
        add(f'icon/{i}', _group_image(icons, i))
    meter = packs[METER_SLOT]
    for s, sequence in enumerate(meter.sequences):
        for step, index in enumerate(sequence):
            add(f'meter/{s}/{step}', _group_image(meter, index))
    for g in range(len(meter.groups)):
        add(f'group/{METER_SLOT}/{g}', _group_image(meter, -g - 1))
    for f in range(len(meter.frames)):
        add(f'frame/{METER_SLOT}/{f}', _group_image(meter, f))
    timer = packs[TIMER_SLOT]
    for step, index in enumerate(timer.sequences[0] if timer.sequences else ()):
        add(f'timer/{step}', _group_image(timer, index))
    layouts, used = {}, set()

    def keep(layout_id):
        if layout_id in layouts:
            return
        layout = bank.layouts[layout_id]
        layouts[layout_id] = dict(size=[layout.width, layout.height], nodes=[
            dict(kind=n.kind, flags=n.flags, payload=list(n.payload), base=list(n.base), relative=list(n.relative))
            for n in layout.nodes])
        for n in layout.nodes:
            if n.kind == 7:
                keep(n.payload[0])
            elif n.kind in (0, 1) and len(n.payload) >= 2:
                used.add((n.payload[0], n.payload[1]))
    for layout_id in DRAWN_LAYOUTS:
        keep(layout_id)
    for slot, frame in sorted(used):
        if slot in packs:
            add(f'slot/{slot}/{frame}', _group_image(packs[slot], frame))
    for name, node in (('ok', 1), ('second', 0), ('left', 2), ('right', 5)):
        add(f'button/{name}', _group_image(packs[6], node))
    menu = packs[MENU_SLOT]
    for step, index in enumerate(menu.sequences[0] if menu.sequences else ()):
        add(f'menu/arrow/{step}', _group_image(menu, index))       # the highlighted option's arrow, 200 ms a step
    add('menu/bullet', _group_image(menu, 0))                       # the other options' square
    dials = nr_art.Pack(source[DIAL_PACK], source)
    for f in range(min(2, len(dials.frames))):
        add(f'dial/{f}', _group_image(dials, f))       # 0 the score dial's face, 1 the timer's
    bubble = packs[BUBBLE_SLOT]
    for s, sequence in enumerate(bubble.sequences[:2]):
        for step, index in enumerate(sequence):
            add(f'pointer/{s}/{step}', _group_image(bubble, index))
    fonts = {}
    for resource, extra in FONTS.items():
        if resource not in source:
            continue
        font = read_font(source[resource])
        for code, image in font.pop('glyphs').items():
            add(f'font/{resource}/{code}', (image, (0, 0)))
        fonts[str(resource)] = dict(font, extra=extra)
    atlas_width = 1024
    x = y = row = 0
    placed = []
    for image in images:
        if x + image.width > atlas_width:
            x, y, row = 0, y + row + 1, 0
        placed.append((x, y))
        x += image.width + 1
        row = max(row, image.height)
    atlas = Image.new('RGBA', (atlas_width, y + row + 1), (0, 0, 0, 0))
    for (px, py), image in zip(placed, images):
        atlas.paste(image, (px, py))
    for sprite in sprites.values():
        image, (px, py) = images[sprite['index']], placed[sprite.pop('index')]
        sprite['rect'] = [px, py, image.width, image.height]
    skin = dict(format='shshd-nr-arena-skin', version=1, screen=list(SCREEN),
                nodes={name: [r.x, r.y, r.width, r.height] for name, r in nodes.items() if r is not None},
                layouts={str(k): v for k, v in layouts.items()}, colors=[c & 0xFFFFFF for c in bank.colors],
                sprites=sprites, markers=[list(MARKER_X), list(MARKER_Y)], buttons=BUTTON_COLOURS,
                background=dict(period=128, step_ms=100), fonts=fonts,
                static_origin=[-STATIC_MARGIN, 0], item_fonts=list(ITEM_FONTS),
                score_font=SCORE_FONT, info_font=INFO_FONT)
    return {'skin.json': json.dumps(skin, separators=(',', ':')).encode('utf-8'),
            'static.png': nr_art.png(compose(source, hide=() if backdrop is None else (STRIPE_NODE,))),
            'tile.png': nr_art.png(background_tile(source)),
            **({'frame.png': nr_art.png(backdrop)} if backdrop is not None else {}),
            'atlas.png': nr_art.png(atlas)}
