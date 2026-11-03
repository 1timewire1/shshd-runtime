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

ADDON_ID, ADDON_TITLE, ADDON_REVISION = 'shs11', "Surviving High School '11", 1
PACK_ID, ADDON_EPISODE = 31600, 999     # (chslim.py's metadata has 31500)
SPEC_FORMAT, SPEC_VERSION = 'shshd-shs11', 1
BACKGROUND_BASE = 26000                 # + 2 x location + variant
BAND_BASE = 26050                       # the same, for the strip under it
INTERFACE_BASE = 26100                  # gamelib's pictures, in order
SPEC = 26199                            # what the addon holds, JSON
PORTRAIT_BASE = 26200                   # + 5 x look + expression
PART_BASE = 26800                       # parts no look draws
MUSIC_BASE, SOUNDS = 26980, 11          # as New Rules' are
KIND_SCRIPT, KIND_TABLE, KIND_PALETTE, KIND_FLAGS, KIND_IMAGE = 2, 3, 4, 7, 8
LOCATIONS = 25                          # resources 0-24 are the location backgrounds
BAND_RESOURCE = 25                      # the strip under them
BAND_OVERLAP = 15                       # at the 240-wide frame, how far the picture sits above the frame's top (N73 `j`)
EXPRESSIONS = 5                         # the faces a line can ask for
PAIRS = 21                              # a character's (part, palette) pairs
EYES, MOUTH = range(3, 8), range(9, 14)
CAST_RECORD = 45                        # words: character, type, name, then the 21 pairs
MAGENTA = b'\xff\x00\xff'               # the engine's transparent key
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
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
    """The strip under a location's picture in its palette, as PNG: N73 `j` tiles resource 25 (`band`: u32 w, u32 h,
    indices) across the frame, under the picture and overlapping it by BAND_OVERLAP."""
    width, height = struct.unpack_from('>II', band, 0)
    return indexed_png(width, height, band[8:8 + width * height], location_palettes(resource, variant)[1])


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
            scene, strip = BACKGROUND_BASE + 2 * location + variant, BAND_BASE + 2 * location + variant
            resources_out[scene] = location_png(data, variant)
            resources_out[strip] = band_png(band, data, variant)
            ids.append(dict(picture=scene, band=strip))
        spec['backgrounds'][str(location)] = ids
    for number, look in enumerate(looks):
        faces = PORTRAIT_BASE + EXPRESSIONS * number
        pictures = [portrait(res, look.pairs, expression) for expression in range(EXPRESSIONS)]
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
    tunes = midis(sounds)
    if len(tunes) != SOUNDS:
        raise Shs11Error(f'the sounds jar has {len(tunes)} tracks, not {SOUNDS}: use one of the builds with them all')
    for index, data in enumerate(tunes):
        resources_out[MUSIC_BASE + index] = render(data)
        spec['music'].append(MUSIC_BASE + index)
    resources_out[SPEC] = json.dumps(spec, separators=(',', ':')).encode()
    resources_out[ADDON_RECORD] = provides_bytes(ADDON_ID, ADDON_TITLE, ADDON_REVISION)
    resources_out[1] = Metadata(PACK_ID, ADDON_EPISODE, (ADDON_TITLE + ' (addon)',) * 5).to_bytes()
    return encode_exp(resources_out), spec


def jar_file(path):
    return zipfile.ZipFile(path)
