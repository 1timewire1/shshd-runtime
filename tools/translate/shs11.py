"""SHS '11 (the J2ME game, EA Mobile Montréal, 2010): reading its jars, its art and sounds. The player's own jars go in;
nothing this reads or writes belongs in the repo.

A jar's archives are chunked members: `gamelib.N` (interface, sounds, text) and, in the larger builds, `default_N`
(backgrounds, character parts, scripts). All big builds hold the same 314 `default` resources at the same indices at
their own sizes, and the images hold no text, so the sharpest art serves every language.
"""
from dataclasses import dataclass
import io
import json
import re
import struct
import zipfile
import zlib

from PIL import Image

ADDON_ID, ADDON_TITLE, ADDON_REVISION = 'shs11', "Surviving High School '11", 2
PACK_ID, ADDON_EPISODE = 31600, 999     # (chslim.py's metadata has 31500)
SPEC_FORMAT, SPEC_VERSION = 'shshd-shs11', 1
BACKGROUND_BASE = 26000                 # + 2 x location + variant
INTERFACE_BASE = 26100                  # gamelib's pictures, in order
SPEC = 26199                            # what the addon holds, JSON
PORTRAIT_BASE = 26200                   # + 5 x look + expression
PART_BASE = 26800                       # parts no look draws
MUSIC_BASE, SOUNDS = 26980, 11          # as New Rules' are
SURPRISE_TRACK, SURPRISE_COPY_OF = 11, 2  # after them, a copy: the story's selector 2 (shs11_story.CUE_TRACKS)
KIND_SCRIPT, KIND_TABLE, KIND_PALETTE, KIND_FLAGS, KIND_IMAGE = 2, 3, 4, 7, 8
LOCATIONS = 25                          # resources 0-24 are the location backgrounds
BAND_RESOURCE = 25                      # the strip under them
HIDDEN_ROWS = 15                        # how far the picture sits above the frame's top (`j` on N73, a.java 89 at 480 wide)
STACK_SIZE, STACK_WINDOW_TOP = (480, 720), 168  # a location as the player shows it (desktop._background_placement)
STACK_SCALE = 2                         # doubled, as SHS HD's are: a letter grid draws its background pixel for pixel
EXPRESSIONS = 5                         # the faces a line can ask for
PORTRAIT_SCALE = 1.19                   # '11's heads to SHS's size; its widest look just stays within 2x art's 256 (shown_faces)
PORTRAIT_HEIGHT, PORTRAIT_LIFT = 246, 20  # a shorter look rises toward SHS's (241-249), by what its flat bottom can hide under the ring
PAIRS = 21                            # a character's (part, palette) pairs
EYES, MOUTH = range(3, 8), range(9, 14)
CAST_RECORD = 45                        # words: character, type, name, then the 21 pairs
MAGENTA = b'\xff\x00\xff'               # the engine's transparent key
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
BADGE_BASE = 26992                      # heart, skull, smiley, each whole then each broken (profile TRANSLATED_BADGE_ART)
BADGE_ROOTS, BADGE_BROKEN_FRAME = (25, 26, 27), 6
BADGE_MARGIN = 2                        # clear pixels round a badge: scaled up, its ink would otherwise run off the picture's edge
BADGE_SMILEY, BADGE_REPAIR_ROWS = 2, 4   # the smiley's sprite sheet (42 rows) cuts off its bottom; the top's first rows mirror it
MEMORY_ENTRY = 33                       # the last of gamelib's entries Memory's screen needs (its fonts)
MEMORY_TEXT_LINE, MEMORY_LETTER_LINE = 40, 85   # which of the 480x800 build's fonts it uses, by line height
PICTURE_TAG, SPRITE_TAGS = 0x5b, (0x25, 0x2b)   # b.java a(byte, boolean, bd): 91 a picture, 37 and 43 sprites round one
FRAME_WORDS = 8                         # a sprite frame in gamelib: source x, source y, w, h, x, y, box w, box h


class Shs11Error(ValueError):
    """A jar isn't what this reads, named with what was looked for."""


def members(jar, base):
    """An archive's chunks joined, in number order; b'' when the jar has none."""
    names = [n for n in jar.namelist() if re.fullmatch(base + r'[._]\d+', n)]
    names.sort(key=lambda n: int(re.split(r'[._]', n)[-1]))
    return b''.join(jar.read(n) for n in names)


def resources(jar):
    """The `default` archive, {index: (kind, bytes)}: skip 4, u32 count, count x u32 offset; at each offset u32 kind,
    u32 size, u8 flag, then u32 stored + a gzip member when the flag is 1, else `size` raw bytes (N73 `s`, `co`)."""
    data = members(jar, 'default')
    if not data:
        raise Shs11Error('this jar has no default archive')
    count = struct.unpack_from('>I', data, 4)[0]
    found = {}
    for index in range(count):
        offset = struct.unpack_from('>I', data, 8 + 4 * index)[0]
        if offset + 9 > len(data):
            continue
        kind, size, flag = struct.unpack_from('>IIB', data, offset)
        if flag == 1:
            stored = struct.unpack_from('>I', data, offset + 9)[0]
            payload = zlib.decompressobj(31).decompress(data[offset + 13:offset + 13 + stored])
        else:
            payload = data[offset + 9:offset + 9 + size]
        found[index] = (kind, payload)
    return found


def gamelib_entries(jar):
    """`gamelib`'s entries in order, gzip undone: u32 chunk size, u32 total, a count byte, then u32 offsets from byte 9,
    the first being 9 + 4n."""
    data = members(jar, 'gamelib')
    if not data:
        raise Shs11Error('this jar has no gamelib archive')
    n = (struct.unpack_from('>I', data, 9)[0] - 9) // 4
    offsets = [struct.unpack_from('>I', data, 9 + 4 * i)[0] for i in range(n)] + [len(data)]
    found = []
    for start, end in zip(offsets, offsets[1:]):
        entry = data[start:end]
        at = entry.find(b'\x1f\x8b\x08', 0, 64)
        found.append(zlib.decompressobj(31).decompress(entry[at:]) if at >= 0 else entry)
    return found


def varint(data, pos):
    """The archive's small number (N73 b.a(bd)): 7 bits, then 7 more while the low bit of a byte is set. (value, end)"""
    first = data[pos]
    value, pos = first >> 1, pos + 1
    if first & 1:
        second = data[pos]
        value, pos = (second << 6 & 0x3F80) | value & 127, pos + 1
        if second & 1:
            value, pos = (data[pos] << 13 & 0xC000) | value & 16383, pos + 1
    return value, pos


def chunk(tag, payload):
    return struct.pack('>I', len(payload)) + tag + payload + struct.pack('>I', zlib.crc32(tag + payload))


@dataclass(frozen=True)
class Interface:
    """An interface picture: where gamelib has it, its PNG and any sprite frames over it."""
    entry: int
    order: int
    palette: int
    png: bytes
    frames: list

    @property
    def name(self):
        return f'{self.entry}.{self.order}.{self.palette}'


IHDR_SHAPE = re.compile(rb'\x00\x00..\x00\x00..[\x01\x02\x04\x08][\x00\x02\x03\x04\x06]\x00\x00[\x00\x01]', re.S)


def inline_palette(data, pos):
    """The palette object at `pos`, as (its RGB and CRC, its end), or None: 0, the number of colours, then the bytes."""
    try:
        reference, after = varint(data, pos)
        if reference:
            return None
        count, after = varint(data, after)
    except IndexError:
        return None
    if not 0 < count <= 256 or after + 3 * count + 4 > len(data):
        return None
    body = data[after:after + 3 * count + 4]
    if zlib.crc32(b'PLTE' + body[:-4]) != int.from_bytes(body[-4:], 'big'):
        return None
    return body, after + 3 * count + 4


def picture_header(data, start):
    """(colours, transparency's length, where its tag is) of the stored PNG whose IHDR data is at `start`, or None: the tag
    PICTURE_TAG, u32 size, the two small numbers, a flag."""
    for back in range(2, 7):
        at = start - 1 - back
        if at < 5 or data[at - 5] != PICTURE_TAG:
            continue
        colours, after = varint(data, at)
        if after >= start - 1:
            continue
        transparent, after = varint(data, after)
        if after == start - 1:
            return colours, transparent, at - 5
    return None


def stripped_png(data, start, palettes):
    """A stored PNG whose IHDR data is at `start`, rebuilt, as ([PNG bytes, one for each palette it has], its end), or
    None. N73 b.java 4084 stores it without a signature, tags or IEND: u32 size, number of colours, length of its
    transparency, a flag, IHDR's 13 + 4 bytes, tRNS's data and CRC if any, u32 IDAT length, IDAT's data and CRC, two zero
    bytes, then the palette as an object. A palette can be a reference to one read before: `palettes`, the entry's so far,
    gives the latest with its number of colours. Right after can come more palettes for the same picture (b.java 4084's
    case 4: a button's other states), which only a CRC tells from what follows."""
    header = picture_header(data, start)
    if header is None:
        return None
    colours, transparent, _tag = header
    pos = start + 17
    head = [PNG_SIGNATURE, struct.pack('>I', 13), b'IHDR', data[start:start + 17]]
    tail = []
    if transparent:
        tail.append(struct.pack('>I', transparent) + b'tRNS' + data[pos:pos + transparent + 4])
        pos += transparent + 4
    length = struct.unpack_from('>I', data, pos)[0]
    if not 0 < length <= len(data) - pos - 8:
        return None
    tail.append(struct.pack('>I', length) + b'IDAT' + data[pos + 4:pos + 8 + length])
    tail.append(chunk(b'IEND', b''))
    pos += 8 + length + 2               # (the stored size runs on into IEND's length, two zero bytes)
    bodies = []
    found = inline_palette(data, pos)
    if found is not None:
        bodies.append(found[0])
        palettes.append(found[0])
        pos = found[1]
        while True:
            found = inline_palette(data, pos)
            if found is None or len(found[0]) != len(bodies[0]):
                break
            if found[0] not in bodies:
                bodies.append(found[0])
            palettes.append(found[0])
            pos = found[1]
    else:
        reference, after = varint(data, pos)
        body = next((b for b in reversed(palettes) if (len(b) - 4) // 3 == colours), None)
        if reference < 2 or body is None:
            return None
        bodies.append(body)
        pos = after
    pictures = [b''.join([*head, struct.pack('>I', len(body) - 4), b'PLTE', body, *tail]) for body in bodies]
    return pictures, pos


def frames_before(data, tag):
    """The sprite frames stored just before the picture whose tag is at `tag`, or []: a sprite is its tag, 0, the number of
    frames, FRAME_WORDS small numbers for each, then 0 and the picture (b.java 4084's case 2)."""
    if data[tag - 1] != 0:
        return []
    for start in range(tag - 2, max(0, tag - 6000), -1):
        if data[start] not in SPRITE_TAGS or data[start + 1] != 0:
            continue
        try:
            count, pos = varint(data, start + 2)
            words = []
            for _ in range(count * FRAME_WORDS):
                value, pos = varint(data, pos)
                words.append(value)
        except IndexError:
            continue
        if pos == tag - 1:
            return [words[i:i + FRAME_WORDS] for i in range(0, len(words), FRAME_WORDS)]
    return []


def frames_after(data, pos, width, height):
    """The sprite frames stored after a picture and pointing back at it, as (frames, the end), or None: 0, a sprite's tag,
    0, the number of frames, the frames, then a reference. They have to fit the picture."""
    if pos + 3 > len(data) or data[pos] != 0 or data[pos + 1] not in SPRITE_TAGS or data[pos + 2] != 0:
        return None
    try:
        count, at = varint(data, pos + 3)
        words = []
        for _ in range(count * FRAME_WORDS):
            value, at = varint(data, at)
            words.append(value)
        reference, at = varint(data, at)
    except IndexError:
        return None
    frames = [words[i:i + FRAME_WORDS] for i in range(0, len(words), FRAME_WORDS)]
    if not frames or reference < 2 or any(f[0] + f[2] > width or f[1] + f[3] > height for f in frames):
        return None
    return frames, at


def interface_pictures(jar):
    """Every picture `gamelib` holds, as [Interface]. An IHDR is found by its shape and its CRC, and each picture is checked
    by decoding it."""
    found = []
    for index, entry in enumerate(gamelib_entries(jar)):
        order, palettes, pos = 0, [], 0
        while True:
            match = IHDR_SHAPE.search(entry, pos)
            if match is None:
                break
            start = match.start()
            pos = start + 1
            head, crc = entry[start:start + 13], entry[start + 13:start + 17]
            if len(crc) < 4 or zlib.crc32(b'IHDR' + head) != int.from_bytes(crc, 'big'):
                continue
            rebuilt = stripped_png(entry, start, palettes)
            if rebuilt is None:
                raise Shs11Error(f'gamelib entry {index}: a picture at {start} could not be rebuilt')
            frames = frames_before(entry, picture_header(entry, start)[2])
            pos = rebuilt[1]
            width, height = struct.unpack_from('>II', entry, start)
            while True:
                more = frames_after(entry, pos, width, height)
                if more is None:
                    break
                frames, pos = frames + more[0], more[1]
            for palette, png in enumerate(rebuilt[0]):
                Image.open(io.BytesIO(png)).load()
                found.append(Interface(index, order, palette, png, frames))
            order += 1
    return found


def image_items(data):
    """A kind-8 record's items: u32 n, n x u32 offset."""
    n = struct.unpack_from('>I', data, 0)[0]
    offsets = [struct.unpack_from('>I', data, 4 + 4 * i)[0] for i in range(n)] + [len(data)]
    return [data[offsets[i]:offsets[i + 1]] for i in range(n)]


def indexed(pixels, width, height, palette):
    """RGBA from 8-bit indices and RGB bytes, the magenta entry clear."""
    image = Image.frombytes('P', (width, height), pixels)
    image.putpalette(palette + bytes(768 - len(palette)))
    rgba = image.convert('RGBA')
    keys = {i for i in range(len(palette) // 3) if palette[3 * i:3 * i + 3] == MAGENTA}
    if keys:
        rgba.putalpha(Image.frombytes('L', (width, height), bytes(0 if p in keys else 255 for p in pixels)))
    return rgba


def lightings(resource):
    """How many lighting variants a location has: a record of 5 items has two."""
    return 2 if len(image_items(resource)) == 5 else 1


def background_id(location, variant=0):
    return BACKGROUND_BASE + 2 * location + variant


def own_palette(item, offset):
    """The u32 length and RGB bytes at `offset` in an item."""
    length = struct.unpack_from('>I', item, offset)[0]
    return item[offset + 4:offset + 4 + length]


def location_palettes(resource, variant=0):
    """A location's (picture's palette, band's palette), as N73 co case 3 picks them. Of 5 items: the picture by item 3 at
    variant 0 and item 4 at any other, the band by item 1 or 2. Of 2 items, there's one lighting whatever the variant: the
    picture by its own palette, stored after its pixels, the band by item 1."""
    items = image_items(resource)
    if len(items) == 5:
        return own_palette(items[4 if variant else 3], 0), own_palette(items[2 if variant else 1], 0)
    width, height = struct.unpack_from('>II', items[0], 0)
    return own_palette(items[0], 8 + width * height), own_palette(items[1], 0)


def indexed_png(width, height, pixels, palette):
    """A flat-colour picture as an indexed PNG, far smaller than RGB. Magenta, the engine's key, is clear."""
    image = Image.frombytes('P', (width, height), pixels)
    image.putpalette(palette + bytes(768 - len(palette)))
    keys = [i for i in range(len(palette) // 3) if palette[3 * i:3 * i + 3] == MAGENTA]
    out = io.BytesIO()
    image.save(out, 'PNG', optimize=True, **(dict(transparency=keys[0]) if keys else {}))
    return out.getvalue()


def location_png(resource, variant=0):
    """A location's picture in a lighting, as PNG."""
    items = image_items(resource)
    width, height = struct.unpack_from('>II', items[0], 0)
    return indexed_png(width, height, items[0][8:8 + width * height], location_palettes(resource, variant)[0])


def band_png(band, resource, variant=0):
    """The strip under a location's picture in its palette, as PNG: `j` tiles resource 25 (`band`: u32 w, u32 h, indices)
    across the frame, straight under the picture."""
    width, height = struct.unpack_from('>II', band, 0)
    return indexed_png(width, height, band[8:8 + width * height], location_palettes(resource, variant)[1])


def stacked_png(band, resource, variant=0):
    """A location as a whole SHS background (owner, 2026-11-03): its picture over the tiled band at full width, in a
    480 x 720 picture (doubled, STACK_SCALE) the player places and pans as it does any other. Scene row HIDDEN_ROWS meets
    the top of the frame's window (rows 168-680), as `j` hangs the picture over its own frame's top; the first row carries
    on above, where a screen with another window (a letter grid's, a title card's) can show it."""
    scene = Image.open(io.BytesIO(location_png(resource, variant))).convert('RGB')
    strip = Image.open(io.BytesIO(band_png(band, resource, variant))).convert('RGB')
    top = STACK_WINDOW_TOP - HIDDEN_ROWS
    image = Image.new('RGB', STACK_SIZE)
    if top > 0:
        image.paste(scene.crop((0, 0, scene.width, 1)).resize((scene.width, top)), ((STACK_SIZE[0] - scene.width) // 2, 0))
    for y in range(top + scene.height, STACK_SIZE[1], strip.height):
        for x in range(0, STACK_SIZE[0], strip.width):
            image.paste(strip, (x, y))
    image.paste(scene, ((STACK_SIZE[0] - scene.width) // 2, top))
    image = image.resize((STACK_SIZE[0] * STACK_SCALE, STACK_SIZE[1] * STACK_SCALE), Image.NEAREST)
    paletted = image.quantize(256)                      # flat art: far smaller, when it loses nothing
    return png_bytes(paletted if paletted.convert('RGB').tobytes() == image.tobytes() else image)


def palette_of(res, palette_id):
    kind, data = res[palette_id & 1023]
    if kind != KIND_PALETTE:
        raise Shs11Error(f'resource {palette_id & 1023} is not a palette')
    return data[4:4 + struct.unpack_from('>I', data, 0)[0]]


def part(res, part_id, palette_id=-1):
    """A character part: (frame, RGBA) (N73 co case 4). Item 0 is s16 frames x 8 s16: box w, box h, x, y, w, h, source x,
    source y. Item 1 is u32 w, u32 h, indices, u32 n and n bytes of its own palette, unless a palette resource is given."""
    kind, data = res.get(part_id & 1023, (None, None))
    if kind != KIND_IMAGE:
        return None
    items = image_items(data)
    frame = struct.unpack_from('>8h', items[0], 2)
    width, height = struct.unpack_from('>II', items[1], 0)
    pixels = items[1][8:8 + width * height]
    if palette_id is not None and palette_id >= 0:
        palette = palette_of(res, palette_id)
    else:
        colours = struct.unpack_from('>I', items[1], 8 + width * height)[0]
        palette = items[1][12 + width * height:12 + width * height + colours]
    return frame, indexed(pixels, width, height, palette)


def drawn_pairs(expression):
    """The 13 pairs a portrait draws, in order: 0, 1, 2, the eyes, 8, the mouth, 14-20 (N73 k.f_)."""
    return [0, 1, 2, EYES[expression], 8, MOUTH[expression], *range(14, PAIRS)]


def portrait(res, pairs, expression=0):
    """A look's picture in its whole box, so that expressions line up, or None if it draws nothing."""
    canvas = None
    for pair in drawn_pairs(expression):
        part_id, palette_id = pairs[pair]
        if part_id < 0:
            continue
        got = part(res, part_id, palette_id)
        if got is None:
            continue
        (box_w, box_h, x, y, w, h, sx, sy), image = got
        if canvas is None:
            canvas = Image.new('RGBA', (box_w, box_h), (0, 0, 0, 0))
        canvas.alpha_composite(image.crop((sx, sy, sx + w, sy + h)), (x, y))
    return canvas


def facing_right(picture):
    """A portrait the way SHS's art faces. '11's art faces left: it mirrors the player and its look picker (`k.c`, co.java
    2762, cl.java 298) and leaves the others on the right, where SHS mirrors the others instead."""
    return None if picture is None else picture.transpose(Image.FLIP_LEFT_RIGHT)


def shown_faces(pictures):
    """A look's faces the size SHS's sit in the ring. '11's fill a 215 x 235 box with room to spare and SHS's are cut to their
    pixels, so cut the look to what any of its faces draws, down to the box's bottom (so that one floating above it still
    does), and enlarge it: the player reads a picture this size as 2x art and centers it, so it stays pixel for pixel on HD.
    It stands each on the ring's bottom, so a short one (most of '11's men, Puddles) gets empty rows under it to sit as high."""
    boxes = [picture.getchannel('A').getbbox() for picture in pictures if picture is not None]
    boxes = [box for box in boxes if box is not None]
    if not boxes:
        return pictures
    left, top, right = min(box[0] for box in boxes), min(box[1] for box in boxes), max(box[2] for box in boxes)
    shown = []
    for picture in pictures:
        if picture is None:
            shown.append(None)
            continue
        cut = picture.crop((left, top, right, picture.height))
        cut = cut.resize((round(cut.width * PORTRAIT_SCALE), round(cut.height * PORTRAIT_SCALE)), Image.LANCZOS)
        lifted = Image.new('RGBA', (cut.width, cut.height + min(PORTRAIT_LIFT, max(0, PORTRAIT_HEIGHT - cut.height))), (0, 0, 0, 0))
        lifted.paste(cut, (0, 0))
        shown.append(lifted)
    return shown


@dataclass(frozen=True)
class Look:
    """A look: its (part, palette) pairs, with who has it in which script's cast table."""
    pairs: tuple
    kind: int
    wearers: tuple                      # (script, character, name)


def script_memory(script):
    """A KiWi script's memory image: data words, zeroed locals, then constants."""
    pos = 5
    if script[4] >= 2:
        if script[pos]:
            pos += 4
        pos += 1
    reserved = script[pos]
    pos += 1
    main, gap, extra, _count = struct.unpack_from('>hhhh', script, pos)
    pos += 8
    if reserved:
        pos += 2
    words = [struct.unpack_from('>h', script, pos + 2 * i)[0] for i in range(main + extra)]
    return words[:main] + [0] * gap + words[main:]


def text_at(memory, address):
    out = bytearray()
    for word in memory[address:address + 80]:
        word &= 0xFFFF
        for byte in (word >> 8, word & 255):
            if not byte:
                return out.decode('cp1252', 'replace')
            out.append(byte)
    return out.decode('cp1252', 'replace')


def cast_tables(res):
    """{script: [(character, kind, name, pairs)]} from the setup scripts, which define a cast in a loop over a table:
    service 5 on `mem[C] + 45 * k`, compiled as LOAD C, a load of k, PUSH 45, so found by that shape; the push before it
    is the table's length (reference/Other Games/docs/SHS_11_JAVA_ENGINE.md, service 5)."""
    from exp_runtime.decode.bytecode import decode_program
    tables = {}
    for index, (kind, data) in sorted(res.items()):
        if kind != KIND_SCRIPT:
            continue
        instructions = decode_program(data).instructions
        if not any(x.opcode == 0x1f and x.operand is not None and x.operand >> 8 == 5 for x in instructions):
            continue
        memory = script_memory(data)
        for i in range(len(instructions) - 2):
            if instructions[i].opcode != 0x40 or instructions[i + 2].opcode != 0x1a or instructions[i + 2].operand != CAST_RECORD:
                continue
            count = next((instructions[j].operand for j in range(i - 1, max(-1, i - 6), -1) if instructions[j].opcode == 0x1a), None)
            if count is None or not 0 < count < 200:
                continue
            base, rows = memory[instructions[i].operand], []
            for k in range(count):
                record = memory[base + CAST_RECORD * k:base + CAST_RECORD * (k + 1)]
                pairs = tuple((record[3 + 2 * p], record[4 + 2 * p]) for p in range(PAIRS))
                rows.append((record[0], record[1], text_at(memory, record[2]), pairs))
            tables[index] = rows
            break
    return tables


def looks_of(tables):
    """Every distinct look in the cast tables, as [Look], in the order the stories first have them. This order gives a look
    its lasting ID, so new ones go at the end."""
    found = {}
    for script, rows in sorted(tables.items()):
        for character, kind, name, pairs in rows:
            look = found.setdefault(pairs, dict(kind=kind, wearers=[]))
            look['wearers'].append((script, character, name))
    return [Look(pairs, look['kind'], tuple(look['wearers'])) for pairs, look in found.items()]


def unused_parts(res, looks):
    """The character parts no look draws, by index: the art has pieces left over from looks cut along the way."""
    used = {part_id & 1023 for look in looks for part_id, _ in look.pairs if part_id >= 0}
    return [index for index, (kind, _) in sorted(res.items()) if kind == KIND_IMAGE and index >= LOCATIONS and index not in used]


def png_bytes(image):
    out = io.BytesIO()
    image.save(out, 'PNG', optimize=True)
    return out.getvalue()


def midis(jar):
    """Every MIDI in gamelib, in archive order: each ends with its last track."""
    found = []
    for entry in gamelib_entries(jar):
        starts = [m.start() for m in re.finditer(b'MThd', entry)]
        for start, end in zip(starts, [*starts[1:], None]):
            data = entry[start:end]
            pos = 14
            for _ in range(int.from_bytes(data[10:12], 'big')):
                if data[pos:pos + 4] != b'MTrk':
                    break
                pos += 8 + int.from_bytes(data[pos + 4:pos + 8], 'big')
            found.append(data[:pos])
    return found


def rendered_music(data):
    """A MIDI as MP3, the way New Rules' music is made (translate.py): Java's synthesizer, as the emulator has it."""
    import midi_render
    return midi_render.mp3(midi_render.render_java(data))


class UiReader:
    """One of gamelib's interface entries as objects (N73 b.java 8588 and 6709, the screens' own loader): a flag, a list of
    entries it depends on, the number of its roots, the number of its objects, then the roots. An object is a small number
    (1 none, 2 and up a reference, 0 here it comes) and usually a tag. The 480x800 build's are a little longer (`wide`)."""

    def __init__(self, data, wide=False, borrowed=0):
        self.data, self.pos, self.wide, self.objects, self.pictures, self.borrowed = data, 0, wide, [], 0, borrowed

    def byte(self):
        value = self.data[self.pos]
        self.pos += 1
        return value

    def int32(self):
        self.pos += 4
        return struct.unpack_from('>i', self.data, self.pos - 4)[0]

    def number(self):
        value, self.pos = varint(self.data, self.pos)
        return value

    def read(self):
        self.byte()
        for _ in range(self.int32()):
            self.number()
        roots = self.int32()
        self.int32()
        return [self.object() for _ in range(roots)]

    def object(self, tag=None):
        reference = self.number()
        if reference == 1:
            return None
        if reference:
            return dict(reference=reference - 2)
        kind = self.byte() if tag is None else tag
        slot = len(self.objects)
        self.objects.append(None)
        self.objects[slot] = self.body(kind)
        return self.objects[slot]

    def box(self, found):
        found.update(x=self.number(), y=self.number(), w=self.number(), h=self.number())
        self.byte()
        return found

    def body(self, kind):
        found = dict(kind=kind)
        if kind in (1, 2):
            return self.byte()
        if kind == 3:
            return self.number()
        if kind == 5:
            return self.int32()
        if kind == 33:                  # a palette: its RGB and CRC
            size = self.number() * 3 + 4
            self.pos += size
            return self.data[self.pos - size:self.pos]
        if kind == 35:                  # text
            size = self.number()
            self.pos += size
            return self.data[self.pos - size:self.pos].split(b'\0')[0].decode('latin-1')
        if kind == 36:                  # a font
            found.update(font=self.object(), sprite=self.object())
            if self.wide and any(self.object() is not None for _ in range(3)):
                raise Shs11Error('a font with parts this does not read')
            return found
        if kind == 37:                  # a sprite: frames over a picture
            return dict(found, frames=self.object(52), picture=self.object())
        if kind == 43:                  # a picture again, with another palette
            return dict(found, picture=self.object(), palette=self.object(33))
        if kind == 51:                  # a font's table
            found.update(frames=self.object(52), table=self.int32())
            self.pos += 17
            found['line'] = self.data[self.pos - 16]
            if self.data[self.pos - 17] > 3 and self.number():
                raise Shs11Error('a font with kerning, which this does not read')
            return found
        if kind == 52:
            words = [self.number() for _ in range(self.number() * FRAME_WORDS)]
            return [words[i:i + FRAME_WORDS] for i in range(0, len(words), FRAME_WORDS)]
        if kind == 53:
            self.box(found)
            found['sprite'] = self.object()
            self.byte()
            return found
        if kind == 68:
            return self.container(found)
        if kind == 71:                  # a text box
            self.box(found)
            found.update(text=self.object(35), font=self.object(36))
            self.byte()
            fonts = self.number()
            if self.wide:
                for _ in range(1, fonts):
                    self.object(36)
                self.byte()
                self.number()
            self.byte()
            return found
        if kind == 76:
            self.box(found)
            self.pos += 3
            return found
        if kind == 83:                  # a sound
            self.byte()
            self.pos += self.int32()
            return found
        if kind == 85:
            self.int32()
            self.byte()
            self.int32()
            for _ in range(self.int32()):
                self.object()
            return found
        if kind == 88:
            self.object()
            self.int32()
            self.byte()
            self.object(89)
            return found
        if kind == 89:
            return [self.number() for _ in range(self.number())]
        if kind == 90:                  # a sprite's frame in a box
            self.box(found)
            self.object()
            self.byte()
            found.update(sprite=self.object(), frame=self.int32())
            return found
        if kind == 91:                  # a picture
            size = self.int32()
            self.number()
            transparent = self.number()
            self.byte()
            self.pos += 17
            if transparent:
                self.pos += transparent + 4
                size -= transparent + 4
            self.pos += 4 + size - 21
            self.object(33)
            found['order'] = self.pictures
            self.pictures += 1
            return found
        if kind == 97:
            self.container(found)
            self.object()
            self.byte()
            self.byte()
            self.number()
            return found
        raise Shs11Error(f'a kind of interface object this does not read: {kind}, at {self.pos}')

    def container(self, found):
        self.box(found)
        self.number()
        self.number()
        self.byte()
        self.byte()
        found['children'] = [self.object() for _ in range(self.number())]
        return found

    def resolve(self, found):
        """An object, following its references inside this entry. `borrowed`: the roots of the entries it depends on, which
        a reference counts first."""
        while isinstance(found, dict) and 'reference' in found:
            found = self.objects[found['reference'] - self.borrowed]
        return found


def with_palette(png, body):
    """A stored picture, its colours swapped for a palette object's."""
    at = png.index(b'PLTE') - 4
    size = struct.unpack_from('>I', png, at)[0]
    return png[:at] + struct.pack('>I', len(body) - 4) + b'PLTE' + body + png[at + 12 + size:]


def font_spec(reader, font, entry, ids):
    """A font's table: its picture's ID, its line height and each character's source x, y, w, h, offset x, y and advance."""
    table = font['font']
    sprite = reader.resolve(font['sprite'])
    picture = reader.resolve(sprite['picture'])
    picture = reader.resolve(picture['picture']) if picture['kind'] == 43 else picture
    return dict(picture=ids[f"{entry}.{picture['order']}.0"], line=table['line'],
                glyphs={str(frame[7] & 255): frame[:7] for frame in table['frames']})


def memory_ui(art, english, ids):
    """(The Memory game's art and text, for the spec; {name: PNG} of the tile states, which only its screen's objects say),
    read from the art build's interface and the English build's text. N73 `bg`, `cv`, `am`."""
    arts, words = gamelib_entries(art), gamelib_entries(english)

    def entry(number, jar=arts, wide=True, borrowed=0):
        reader = UiReader(jar[number], wide, borrowed)
        return reader, reader.read()

    grid, roots = entry(11)
    parts = roots[0]['children']
    edges = parts[0]['children'][0]['sprite']
    tiles = parts[1]['sprite']
    tile_states = [grid.resolve(root) for root in roots[2:5]]
    numbers = parts[10]['sprite']
    clock, clock_roots = entry(9)
    score, score_roots = entry(16)
    fonts, font_roots = entry(MEMORY_ENTRY, borrowed=1)
    by_line = {fonts.resolve(found['font'])['line']: found for found in font_roots if found is not None}
    for found in by_line.values():
        found['font'] = fonts.resolve(found['font'])
    text = entry(17, words, False)[1]
    time_up = entry(16, words, False)[1][1]
    return dict(
        clock=dict(picture=ids['9.0.0'], frames=clock_roots[0]['children'][0]['sprite']['frames'], box=[14, 23, 114, 112]),
        score=dict(picture=ids['16.0.0'], frames=score_roots[3]['children'][0]['sprite']['frames']),
        grid=dict(picture=ids['11.0.0'], frames=edges['frames'], size=[parts[0]['w'], parts[0]['h']],
                  places=[[child['x'], child['w']] for child in parts[0]['children']]),
        tiles=dict(frames=tiles['frames'], cells=[[c['x'], c['y'], c['w'], c['h']] for c in parts[1:10]]),
        numbers=dict(picture=ids['11.2.0'], frames=numbers['frames'][:9], places=[[c['x'], c['y']] for c in parts[10:19]]),
        floats=[ids['16.2.0'], ids['16.1.0']],
        fonts=dict(text=font_spec(fonts, by_line[MEMORY_TEXT_LINE], MEMORY_ENTRY, ids),
                   letters=font_spec(fonts, by_line[MEMORY_LETTER_LINE], MEMORY_ENTRY, ids)),
        text=dict(spelling=text[3], goal=text[4], look=text[5], select=text[6], careful=text[7], ready=text[8], time_up=time_up),
    ), {f'11.1.{state + 1}': grid.resolve(found['picture'])['palette'] for state, found in enumerate(tile_states)}


def reflex_ui(art, english, ids):
    """(Reflex's art and text, for the spec; {name: palette} of the marker's three colours), N73 `av` and `am`: gamelib entry 18,
    which borrows 13 objects from the entry it depends on."""
    reader = UiReader(gamelib_entries(art)[18], True, 13)
    roots = reader.read()
    gauge = roots[3]
    inner, bar = roots[9], roots[8]
    words = UiReader(gamelib_entries(english)[18]).read()
    return dict(
        icons=dict(picture=ids['18.0.0'], frames=roots[2]['frames'], box=[roots[0]['w'], roots[0]['h']]),
        bar=dict(picture=ids['18.2.0'], place=[inner['x'] + bar['x'], inner['y'] + bar['y']]),
        marker=dict(place=[inner['x'], inner['y']], travel=inner['w'] - roots[7]['w']),
        width=gauge['w'],
        text=dict(goal=words[10], gauge=words[11], select=words[12], bars=words[13], penalty=words[14], skull=words[15],
                  ready=words[16]),
    ), {f'18.1.m{look}': reader.resolve(roots[4 + look]['palette']) for look in range(3)}


def badge_pictures(art, pictures):
    """{resource: PNG} of '11's relationship icons, each whole and broken (gamelib entry 10's sprites, N73 `dc`: frame 0 a
    whole one, frame 6 its break). `pictures`: the interface's, by name."""
    reader = UiReader(gamelib_entries(art)[10], True)
    roots = reader.read()
    found = {}
    for number, root in enumerate(BADGE_ROOTS):
        sprite = roots[root]
        sheet = Image.open(io.BytesIO(pictures[f"10.{sprite['picture']['order']}.0"].png)).convert('RGBA')
        for offset, frame in ((0, sprite['frames'][0]), (3, sprite['frames'][BADGE_BROKEN_FRAME])):
            x, y, w, h = frame[:4]
            picture = sheet.crop((x, y, x + w, y + h))
            if number == BADGE_SMILEY and offset == 0:
                picture = rounded_bottom(picture)
            margin = Image.new('RGBA', (picture.width + 2 * BADGE_MARGIN, picture.height + 2 * BADGE_MARGIN), (0, 0, 0, 0))
            margin.paste(picture, (BADGE_MARGIN, BADGE_MARGIN))
            found[BADGE_BASE + offset + number] = png_bytes(without_key_colour(margin))
    return found


def rounded_bottom(picture, rows=BADGE_REPAIR_ROWS):
    """A round icon whose sprite sheet cut off its last row or two: its top, mirrored, in place of its last rows, one taller."""
    width, height = picture.size
    whole = Image.new('RGBA', (width, height + 1), (0, 0, 0, 0))
    whole.paste(picture.crop((0, 0, width, height + 1 - rows)), (0, 0))
    whole.paste(picture.crop((0, 0, width, rows)).transpose(Image.FLIP_TOP_BOTTOM), (0, height + 1 - rows))
    return whole


def without_key_colour(picture):
    """A picture whose fully clear pixels have the colour of the ink beside them, not the engine's magenta: scaling blends
    colour in from clear pixels, and it shows as a purple edge."""
    pixels = picture.load()
    width, height = picture.size
    fixes = {}
    for y in range(height):
        for x in range(width):
            if pixels[x, y][3]:
                continue
            near = [pixels[a, b] for a, b in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1), (x - 1, y - 1), (x + 1, y - 1), (x - 1, y + 1), (x + 1, y + 1))
                    if 0 <= a < width and 0 <= b < height and pixels[a, b][3]]
            if near:
                fixes[x, y] = (*(sum(p[c] for p in near) // len(near) for c in range(3)), 0)
            else:
                fixes[x, y] = (64, 64, 64, 0)
    for place, colour in fixes.items():
        pixels[place] = colour
    return picture


def build_addon(art, english, sounds, render=rendered_music):
    """The addon's `.exp` bytes and its spec, from three open jars: `art` for the pictures (the sharpest build), `english` for
    the cast tables, `sounds` for the full set of music. Every background, look and part goes in, used or not (owner,
    2026-11-03). A resource keeps its ID once shipped: new ones go at the end of their range."""
    from exp_runtime.addons import RESOURCE as ADDON_RECORD, provides_bytes
    from exp_runtime.exp import Metadata, encode_exp
    res, looks = resources(art), looks_of(cast_tables(resources(english)))
    kind, band = res[BAND_RESOURCE]
    if kind != KIND_TABLE:
        raise Shs11Error(f'resource {BAND_RESOURCE} is not the location band')
    resources_out, spec = {}, dict(format=SPEC_FORMAT, version=SPEC_VERSION, backgrounds={}, looks=[], parts={}, interface={}, music=[])
    for location in range(LOCATIONS):
        kind, data = res[location]
        if kind != KIND_IMAGE:
            raise Shs11Error(f'resource {location} is not a background')
        ids = []
        for variant in range(lightings(data)):
            scene = background_id(location, variant)
            resources_out[scene] = stacked_png(band, data, variant)
            ids.append(scene)
        spec['backgrounds'][str(location)] = ids
    for number, look in enumerate(looks):
        faces = PORTRAIT_BASE + EXPRESSIONS * number
        pictures = shown_faces([facing_right(portrait(res, look.pairs, expression)) for expression in range(EXPRESSIONS)])
        for expression, picture in enumerate(pictures):
            if picture is not None:                     # (a voice with no picture: a cat behind a door)
                resources_out[faces + expression] = png_bytes(picture)
        spec['looks'].append(dict(id=faces if pictures[0] is not None else None, kind=look.kind,
                                  names=sorted({name for _, _, name in look.wearers}),
                                  wearers=[list(w) for w in look.wearers]))
    if PORTRAIT_BASE + EXPRESSIONS * len(looks) > PART_BASE:
        raise Shs11Error('the looks run into the parts')
    for offset, index in enumerate(unused_parts(res, looks)):
        frame, image = part(res, index)
        resources_out[PART_BASE + offset] = png_bytes(image)
        spec['parts'][str(index)] = dict(id=PART_BASE + offset, frame=list(frame))
    pictures = interface_pictures(art)
    if INTERFACE_BASE + len(pictures) > PORTRAIT_BASE:
        raise Shs11Error('the interface runs into the looks')
    for offset, picture in enumerate(pictures):
        resources_out[INTERFACE_BASE + offset] = picture.png
        spec['interface'][picture.name] = dict(id=INTERFACE_BASE + offset, frames=picture.frames)
    if MEMORY_ENTRY < len(gamelib_entries(art)):
        ids = {name: found['id'] for name, found in spec['interface'].items()}
        spec['memory'], palettes = memory_ui(art, english, ids)
        offset = INTERFACE_BASE + len(pictures)
        states = [resources_out[ids['11.1.0']]]
        for name, body in palettes.items():
            states.append(with_palette(states[0], body))
            resources_out[offset] = states[-1]
            spec['interface'][name] = dict(id=offset, frames=[])
            ids[name] = offset
            offset += 1
        spec['memory']['tiles']['pictures'] = [ids['11.1.0'], *(ids[name] for name in palettes)]
        spec['reflex'], palettes = reflex_ui(art, english, ids)
        marker = resources_out[ids['18.1.0']]
        looks = []
        for name, body in palettes.items():
            resources_out[offset] = with_palette(marker, body)
            spec['interface'][name] = dict(id=offset, frames=[])
            looks.append(offset)
            offset += 1
        spec['reflex']['marker']['pictures'] = looks
        for found in spec['interface'].values():
            resources_out[found['id']] = png_bytes(without_key_colour(Image.open(io.BytesIO(resources_out[found['id']])).convert('RGBA')))
        resources_out.update(badge_pictures(art, {picture.name: picture for picture in pictures}))
    tunes = midis(sounds)
    if len(tunes) != SOUNDS:
        raise Shs11Error(f'the sounds jar has {len(tunes)} tracks, not {SOUNDS}: use one of the builds with them all')
    for index, data in enumerate(tunes):
        resources_out[MUSIC_BASE + index] = render(data)
        spec['music'].append(MUSIC_BASE + index)
    resources_out[MUSIC_BASE + SURPRISE_TRACK] = resources_out[MUSIC_BASE + SURPRISE_COPY_OF]
    resources_out[SPEC] = json.dumps(spec, separators=(',', ':')).encode()
    resources_out[ADDON_RECORD] = provides_bytes(ADDON_ID, ADDON_TITLE, ADDON_REVISION)
    resources_out[1] = Metadata(PACK_ID, ADDON_EPISODE, (ADDON_TITLE + ' (addon)',) * 5).to_bytes()
    return encode_exp(resources_out), spec


def jar_file(path):
    return zipfile.ZipFile(path)
