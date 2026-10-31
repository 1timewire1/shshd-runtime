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
# The UI packs in the layout bank's image slots (class_6.method_185, method_247 and the boot sequence), with the RGB565
# tint each is loaded with: New Rules' default theme (method_184(true); King of Diss never changes it, service 38).
THEME = (15154, -166, -2416, -2416, -567, -342)
SLOT_PACKS = {0: (4, None), 1: (106, THEME[4]), 2: (83, THEME[3]), 3: (65, THEME[1]), 4: (146, None),
              5: (62, THEME[0]), 6: (173, -342), 7: (183, -567), 8: (123, THEME[5]), 9: (73, THEME[2]),
              10: (140, None), 11: (251, None), 12: (189, None)}
BACKGROUND_SLOT = 5                     # its frame 0 tiles the screen, scrolling 1 pixel a 100 ms over 128 (method_358)
ARENA_LAYOUT, BAND_LAYOUT, BAND_NODE = 31, 66, 47
TIMER_DIAL, SCORE_DIAL = 33, 34         # layout 66's dials, hidden until the panel shows them
ITEM_ICONS = 8018                       # the 29 minigame item pictures (o.java's part IDs 0-28 -> 8018-8046)
METER_PACK, DIAL_PACK = 146, 51         # the meter strip (class_6.field_227) and the dial art (field_203)


def slots(source):
    return {slot: nr_art.Pack(source[rid], source, tint=tint) for slot, (rid, tint) in SLOT_PACKS.items()
            if rid in source}


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
    """A layout's nodes into `rect` as `w.a(v, ...)` draws them (class_0.method_14): image nodes (kind 1: slot, frame)
    tiled over their rectangles (from the right with flag 0x40, the bottom with 0x80), colour fills (kinds 2-4: the
    bank's colour, its low 24 bits), outlines (kind 5) and nested layouts (kind 7). A node shows with flag 0x10, or when
    its index (node_rect's numbering) is in `show`, unless it is in `hide`. Returns how many nodes it numbered."""
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
                frames = packs[node.payload[0]].frames
                if 0 <= node.payload[1] < len(frames):
                    nr_art.tile(canvas, frames[node.payload[1]], (child.x, child.y, child.width, child.height),
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


def compose(source, show=()):
    """The arena's static screen (SCREEN, RGBA): layout 31 and the top band, without the scrolling background (the
    player tiles it underneath). `show`: layout 31's hidden nodes to draw too (node_rect's numbering)."""
    bank = LayoutBank.parse(source[LAYOUT_BANK])
    packs = slots(source)
    width, height = SCREEN
    canvas = Image.new('RGBA', SCREEN, (0, 0, 0, 0))
    draw(canvas, bank, ARENA_LAYOUT, Rect(0, 0, width, height), packs, frozenset(show))
    band = node_rect(bank, ARENA_LAYOUT, BAND_NODE, Rect(0, 0, width, height))
    draw(canvas, bank, BAND_LAYOUT, Rect(0, band.y, width, band.height), packs)
    return canvas


def background_tile(source):
    return slots(source)[BACKGROUND_SLOT].frames[0]


# -- the skin the player draws from ---------------------------------------------------------------------------------
# Layouts the player draws itself, at sizes that change: the text item box (25, `o.a(25)`), the bubble (70) and the
# dials (33 timer, 34 score), with the layouts they nest.
DRAWN_LAYOUTS = (25, 33, 34, 70)
# Layout 31's nodes the panel places things at (node_rect numbering), and layout 66's.
ARENA_NODES = {'field': 76, 'wide': 88, 'band': 47, 'ok': 77, 'second': 72, 'left': 78, 'right': 79, 'hint': 87,
               'hud1_label': 82, 'hud1_item': 83, 'hud1_label_alt': 84, 'hud1_item_alt': 85, 'hud1_text': 86,
               'hud2_label': 42, 'hud2_item': 43, 'hud2_label_alt': 44, 'hud2_item_alt': 45, 'hud2_text': 46}
# The dials are layouts 33 (timer) and 34 (score), drawn into 'timer' and 'meter'.
BAND_NODES = {'hud0_label': 11, 'hud0_item': 12, 'hud0_label_alt': 13, 'hud0_item_alt': 14, 'hud0_text': 15,
              'timer': 16, 'meter': 19, 'meter_frame': 20}
# Where a marker sits on the score dial for each meter value (class_13's static tables), X1i pixels.
MARKER_X = (43, 50, 51, 45, 32, 20, 9, 9, 16, 29)
MARKER_Y = (11, 21, 36, 46, 52, 50, 38, 20, 11, 7)
BUTTON_COLOURS = dict(right=0x33FF33, wrong=0xFF3333, idle=0x9966FF, pressed=0x66CCCC, alternate=0xFFA033)
METER_SLOT, TIMER_SLOT = 4, 2           # pack 146 (meter, markers, plates, hint) and pack 83 (the timer's 17 steps)


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


def build_skin(source):
    """The arena skin for the addon: {name: bytes} with 'skin.json' (node rectangles, layouts, sprite table, colours),
    'static.png', 'tile.png' and 'atlas.png' (every sprite the player draws)."""
    import json
    bank = LayoutBank.parse(source[LAYOUT_BANK])
    packs = slots(source)
    width, height = SCREEN
    screen = Rect(0, 0, width, height)
    band = node_rect(bank, ARENA_LAYOUT, BAND_NODE, screen)
    band_rect = Rect(0, band.y, width, band.height)
    nodes = {name: node_rect(bank, ARENA_LAYOUT, index, screen) for name, index in ARENA_NODES.items()}
    nodes.update({name: node_rect(bank, BAND_LAYOUT, index, band_rect) for name, index in BAND_NODES.items()})
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
                background=dict(period=128, step_ms=100))
    return {'skin.json': json.dumps(skin, separators=(',', ':')).encode('utf-8'),
            'static.png': nr_art.png(compose(source)), 'tile.png': nr_art.png(background_tile(source)),
            'atlas.png': nr_art.png(atlas)}
