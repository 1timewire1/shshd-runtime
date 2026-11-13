"""SHS '11's reader, addon and stories (tools/translate/shs11.py, shs11_story.py), from authored jars: its archives, the stored PNGs in gamelib, a
location's two palettes and its band, portraits, and what the addon holds."""
import importlib.util
import io
import json
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools' / 'translate'))
HAS_PIL = importlib.util.find_spec('PIL') is not None
if HAS_PIL:
    from PIL import Image
    import playthrough
    import shs11
    import shs11_story
    from exp_runtime.addons import addon_record
    from exp_runtime.decode.bytecode import OPERAND_OPCODES, decode_program
    from exp_runtime.exp import ExpArchive, encode_exp
    from exp_runtime.vm import KiwiVM, StopKind

RED, GREEN, BLUE, WHITE, MAGENTA = b'\xdd\x11\x11', b'\x11\xdd\x11', b'\x11\x11\xdd', b'\xff\xff\xff', b'\xff\x00\xff'


def small(value):
    """The archive's small number, as b.a(bd) reads it."""
    if value < 128:
        return bytes([value << 1])
    return bytes([(value & 127) << 1 | 1, value >> 7 << 1 & 0xFF])


def stored_picture(width, height, colours, transparent=b'', palettes=1):
    """A PNG as gamelib stores it, every pixel index 0. `colours` is RGB bytes; further palettes reverse them."""
    raw = b''.join(b'\0' + bytes(width) for _ in range(height))
    idat = zlib.compress(raw)
    ihdr = struct.pack('>IIBBBBB', width, height, 8, 3, 0, 0, 0)
    head = ihdr + struct.pack('>I', zlib.crc32(b'IHDR' + ihdr))
    count = len(colours) // 3
    size = 21 + len(idat) + 4 + 2 + (len(transparent) + 4 if transparent else 0)
    out = bytes([shs11.PICTURE_TAG]) + struct.pack('>I', size) + small(count) + small(len(transparent)) + b'\0' + head
    if transparent:
        out += transparent + struct.pack('>I', zlib.crc32(b'tRNS' + transparent))
    out += struct.pack('>I', len(idat)) + idat + struct.pack('>I', zlib.crc32(b'IDAT' + idat)) + b'\0\0'
    for number in range(palettes):
        rgb = colours if number == 0 else b''.join(colours[i:i + 3] for i in range(len(colours) - 3, -1, -3))
        out += b'\0' + small(count) + rgb + struct.pack('>I', zlib.crc32(b'PLTE' + rgb))
    return out


def frame_table(frames):
    return bytes([shs11.SPRITE_TAGS[0]]) + b'\0' + small(len(frames)) + b''.join(small(v) for f in frames for v in f)


def gamelib(entries):
    offset, offsets = 9 + 4 * len(entries), []
    for entry in entries:
        offsets.append(offset)
        offset += len(entry)
    return struct.pack('>II', 8192, offset) + bytes([len(entries) * 2]) + b''.join(struct.pack('>I', o) for o in offsets) + b''.join(entries)


def default_archive(res):
    count = max(res) + 1
    offset, offsets, body = 8 + 4 * count, [], b''
    for index in range(count):
        kind, data = res.get(index, (9, b''))
        offsets.append(offset + len(body))
        body += struct.pack('>IIB', kind, len(data), 0) + data
    return b'\0\0\0\0' + struct.pack('>I', count) + b''.join(struct.pack('>I', o) for o in offsets) + body


def record(items):
    offset, offsets = 4 + 4 * len(items), []
    for item in items:
        offsets.append(offset)
        offset += len(item)
    return struct.pack('>I', len(items)) + b''.join(struct.pack('>I', o) for o in offsets) + b''.join(items)


def palette(rgb):
    return struct.pack('>I', len(rgb)) + rgb


def location(lights, width=2, height=2):
    """A location record, its pixels all index 1: 5 items when `lights`, else 2."""
    pixels = struct.pack('>II', width, height) + bytes([1]) * (width * height)
    if lights:
        return record([pixels + palette(MAGENTA + WHITE), palette(MAGENTA + BLUE), palette(MAGENTA + WHITE),
                       palette(MAGENTA + RED), palette(MAGENTA + GREEN)])
    return record([pixels + palette(MAGENTA + BLUE), palette(MAGENTA + GREEN)])


def character_part(colour, x=0, y=0, width=2, height=2, box=(4, 4)):
    frame = struct.pack('>h8h', 1, box[0], box[1], x, y, width, height, 0, 0)
    return record([frame, struct.pack('>II', width, height) + bytes(width * height) + palette(colour)])


def pairs(**chosen):
    found = [(-1, -1)] * shs11.PAIRS
    for name, value in chosen.items():
        found[int(name[1:])] = value
    return tuple(found)


def jar(members):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    out.seek(0)
    return zipfile.ZipFile(out)


def midi(notes=1):
    track = bytes(notes)
    return b'MThd' + struct.pack('>IHHH', 6, 0, 1, 480) + b'MTrk' + struct.pack('>I', len(track)) + track


@unittest.skipUnless(HAS_PIL, 'needs Pillow')
class ArchiveTests(unittest.TestCase):
    def test_small_numbers(self):
        self.assertEqual(shs11.varint(small(5), 0), (5, 1))
        self.assertEqual(shs11.varint(small(65), 0), (65, 1))
        self.assertEqual(shs11.varint(small(200), 0), (200, 2))

    def test_the_default_archive_and_gamelib_read_back_in_chunks(self):
        data = default_archive({0: (shs11.KIND_IMAGE, b'pic'), 2: (shs11.KIND_SCRIPT, b'run')})
        built = jar({'default_1': data[10:], 'default_0': data[:10], 'gamelib.0': gamelib([b'one', b'two'])})
        self.assertEqual(shs11.resources(built)[0], (shs11.KIND_IMAGE, b'pic'))
        self.assertEqual(shs11.resources(built)[2], (shs11.KIND_SCRIPT, b'run'))
        self.assertEqual(shs11.gamelib_entries(built), [b'one', b'two'])

    def test_a_jar_without_them_says_so(self):
        with self.assertRaises(shs11.Shs11Error):
            shs11.resources(jar({'x': b''}))
        with self.assertRaises(shs11.Shs11Error):
            shs11.gamelib_entries(jar({'x': b''}))

    def test_a_gzip_entry_is_undone(self):
        out = zlib.compressobj(wbits=31)
        packed = out.compress(b'hello') + out.flush()
        self.assertEqual(shs11.gamelib_entries(jar({'gamelib.0': gamelib([b'head' + packed])})), [b'hello'])

    def test_midis_are_cut_at_their_last_track(self):
        one, two = midi(3), midi(5)
        self.assertEqual(shs11.midis(jar({'gamelib.0': gamelib([b'xx' + one, one + two + b'tail'])})), [one, one, two])


@unittest.skipUnless(HAS_PIL, 'needs Pillow')
class InterfaceTests(unittest.TestCase):
    def pictures(self, *entries):
        return shs11.interface_pictures(jar({'gamelib.0': gamelib(list(entries))}))

    def colour(self, picture):
        return Image.open(io.BytesIO(picture.png)).convert('RGBA').getpixel((0, 0))

    def test_a_stored_picture_comes_back_with_its_palette(self):
        found = self.pictures(b'\0\0' + stored_picture(3, 2, RED + GREEN))
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].name, '0.0.0')
        self.assertEqual(Image.open(io.BytesIO(found[0].png)).size, (3, 2))
        self.assertEqual(self.colour(found[0])[:3], (0xdd, 0x11, 0x11))

    def test_transparency_comes_back_too(self):
        found = self.pictures(b'\0\0' + stored_picture(2, 2, MAGENTA + RED, transparent=b'\0'))
        self.assertEqual(self.colour(found[0])[3], 0)

    def test_more_than_63_colours_still_finds_the_palette(self):
        # These came out black when the header's number of colours was misread as 0.
        colours = RED + b''.join(bytes([i, i, i]) for i in range(64))
        found = self.pictures(b'\0\0\0' + stored_picture(2, 2, colours))
        self.assertEqual(self.colour(found[0])[:3], (0xdd, 0x11, 0x11))

    def test_further_palettes_are_the_same_picture_in_other_colours(self):
        found = self.pictures(b'\0\0' + stored_picture(2, 2, RED + GREEN, palettes=2))
        self.assertEqual([p.name for p in found], ['0.0.0', '0.0.1'])
        self.assertEqual(self.colour(found[0])[:3], (0xdd, 0x11, 0x11))
        self.assertEqual(self.colour(found[1])[:3], (0x11, 0xdd, 0x11))

    def test_several_pictures_in_order(self):
        found = self.pictures(b'\0' + stored_picture(2, 2, RED + GREEN) + b'\0' + stored_picture(3, 3, BLUE + WHITE), b'none')
        self.assertEqual([p.name for p in found], ['0.0.0', '0.1.0'])
        self.assertEqual(self.colour(found[1])[:3], (0x11, 0x11, 0xdd))

    def test_frames_stored_before_a_picture(self):
        frames = [[0, 0, 2, 2, 1, 1, 4, 4], [2, 0, 2, 2, 1, 1, 4, 4]]
        found = self.pictures(b'\0\0' + frame_table(frames) + b'\0' + stored_picture(4, 2, RED + GREEN))
        self.assertEqual(found[0].frames, frames)

    def test_frames_stored_after_a_picture_pointing_back(self):
        frames = [[0, 0, 2, 2, 1, 1, 4, 4]]
        found = self.pictures(b'\0\0' + stored_picture(4, 2, RED + GREEN) + b'\0' + frame_table(frames) + small(2))
        self.assertEqual(found[0].frames, frames)

    def test_frames_that_dont_fit_the_picture_arent_its(self):
        frames = [[0, 0, 200, 2, 1, 1, 4, 4]]
        found = self.pictures(b'\0\0' + stored_picture(4, 2, RED + GREEN) + b'\0' + frame_table(frames) + small(2))
        self.assertEqual(found[0].frames, [])

    def test_a_picture_that_cant_be_rebuilt_is_an_error_rather_than_a_gap(self):
        whole = stored_picture(2, 2, RED + GREEN)
        at = whole.index(b'\0\0\0\x02\0\0\0\x02')
        with self.assertRaises(shs11.Shs11Error):
            self.pictures(whole[at:])                   # (no header before its IHDR)


@unittest.skipUnless(HAS_PIL, 'needs Pillow')
class LocationTests(unittest.TestCase):
    def colour(self, png):
        return Image.open(io.BytesIO(png)).convert('RGB').getpixel((0, 0))

    def test_two_lightings_each_have_a_picture_palette_and_a_band_palette(self):
        data = location(True)
        self.assertEqual(shs11.lightings(data), 2)
        self.assertEqual(shs11.location_palettes(data, 0), (MAGENTA + RED, MAGENTA + BLUE))
        self.assertEqual(shs11.location_palettes(data, 1), (MAGENTA + GREEN, MAGENTA + WHITE))
        self.assertEqual(self.colour(shs11.location_png(data, 0)), (0xdd, 0x11, 0x11))
        self.assertEqual(self.colour(shs11.location_png(data, 1)), (0x11, 0xdd, 0x11))

    def test_any_variant_past_0_is_the_other_lighting(self):
        data = location(True)
        self.assertEqual(shs11.location_palettes(data, 2), shs11.location_palettes(data, 1))

    def test_one_lighting_keeps_its_palette_after_its_pixels(self):
        # Item 1 is the band's: using it for the picture left half the locations nearly black.
        data = location(False)
        self.assertEqual(shs11.lightings(data), 1)
        self.assertEqual(shs11.location_palettes(data, 0), (MAGENTA + BLUE, MAGENTA + GREEN))
        self.assertEqual(shs11.location_palettes(data, 1), shs11.location_palettes(data, 0))
        self.assertEqual(self.colour(shs11.location_png(data)), (0x11, 0x11, 0xdd))

    def test_the_band_is_one_strip_in_each_locations_colours(self):
        band = struct.pack('>II', 1, 3) + bytes([1, 1, 1])
        self.assertEqual(Image.open(io.BytesIO(shs11.band_png(band, location(True), 1))).size, (1, 3))
        self.assertEqual(self.colour(shs11.band_png(band, location(True), 1)), (0xff, 0xff, 0xff))
        self.assertEqual(self.colour(shs11.band_png(band, location(False))), (0x11, 0xdd, 0x11))

    def test_a_location_is_a_whole_background_with_its_band_under_it(self):
        band = struct.pack('>II', 1, 3) + bytes([1, 1, 1])
        image = Image.open(io.BytesIO(shs11.stacked_png(band, location(False)))).convert('RGB')
        scale = shs11.STACK_SCALE
        self.assertEqual(image.size, (480 * scale, 720 * scale))
        scene_bottom = (shs11.STACK_WINDOW_TOP - shs11.HIDDEN_ROWS + 2) * scale     # the authored scene is 2 x 2
        self.assertEqual(image.getpixel((0, scene_bottom)), (0x11, 0xdd, 0x11))     # the band, tiled
        self.assertEqual(image.getpixel((image.width - 1, image.height - 1)), (0x11, 0xdd, 0x11))

    def test_magenta_is_clear(self):
        png = shs11.indexed_png(1, 1, bytes(1), MAGENTA + RED)
        self.assertEqual(Image.open(io.BytesIO(png)).convert('RGBA').getpixel((0, 0))[3], 0)


@unittest.skipUnless(HAS_PIL, 'needs Pillow')
class CharacterTests(unittest.TestCase):
    def res(self):
        return {60: (shs11.KIND_IMAGE, character_part(RED)), 61: (shs11.KIND_IMAGE, character_part(GREEN, x=2)),
                62: (shs11.KIND_IMAGE, character_part(BLUE, x=2)), 63: (shs11.KIND_IMAGE, character_part(WHITE, y=2)),
                26: (shs11.KIND_PALETTE, palette(WHITE) + b'\0\0\0\0')}

    def test_a_part_is_drawn_with_its_own_palette_or_a_given_one(self):
        res = self.res()
        self.assertEqual(shs11.part(res, 60)[1].getpixel((0, 0))[:3], (0xdd, 0x11, 0x11))
        self.assertEqual(shs11.part(res, 60, 26)[1].getpixel((0, 0))[:3], (0xff, 0xff, 0xff))
        self.assertIsNone(shs11.part(res, 999))

    def test_a_portrait_fills_its_box_and_changes_only_its_face(self):
        res = self.res()
        look = pairs(p0=(60, -1), p3=(61, -1), p4=(62, -1))
        neutral, other = shs11.portrait(res, look, 0), shs11.portrait(res, look, 1)
        self.assertEqual(neutral.size, (4, 4))
        self.assertEqual(neutral.getpixel((0, 0))[:3], (0xdd, 0x11, 0x11))
        self.assertEqual(neutral.getpixel((2, 0))[:3], (0x11, 0xdd, 0x11))
        self.assertEqual(other.getpixel((0, 0))[:3], (0xdd, 0x11, 0x11))
        self.assertEqual(other.getpixel((2, 0))[:3], (0x11, 0x11, 0xdd))
        self.assertEqual(neutral.getpixel((0, 2))[3], 0)

    def test_a_look_with_no_parts_draws_nothing(self):
        self.assertIsNone(shs11.portrait(self.res(), pairs(), 0))

    def test_a_portrait_is_mirrored_to_face_as_shss_do(self):
        face = shs11.facing_right(shs11.portrait(self.res(), pairs(p0=(60, -1)), 0))
        self.assertEqual(face.getpixel((3, 0))[3], 255)     # the authored part is at the left of its 4 x 4 box
        self.assertEqual(face.getpixel((0, 0))[3], 0)
        self.assertIsNone(shs11.facing_right(None))

    def test_a_looks_faces_are_cut_to_what_any_of_them_draws_and_enlarged_together(self):
        one, two = Image.new('RGBA', (100, 100)), Image.new('RGBA', (100, 100))
        one.paste((255, 0, 0, 255), (10, 20, 60, 80))
        two.paste((0, 255, 0, 255), (30, 10, 90, 80))
        shown = shs11.shown_faces([one, None, two])
        self.assertIsNone(shown[1])
        size = round(80 * shs11.PORTRAIT_SCALE), round(90 * shs11.PORTRAIT_SCALE) + shs11.PORTRAIT_LIFT    # 10-90 across, 10 down
        self.assertEqual([shown[0].size, shown[2].size], [size, size])
        self.assertEqual(shown[0].getpixel((0, size[1] // 2))[0], 255)              # its left edge is the look's
        self.assertEqual(shown[0].getpixel((0, size[1] - 1))[3], 0)                 # the room under it stays

    def test_a_short_look_rises_only_as_far_as_it_needs_and_can(self):
        def height_of(rows):
            picture = Image.new('RGBA', (100, 300))
            picture.paste((255, 0, 0, 255), (0, 300 - rows, 100, 300))
            return shs11.shown_faces([picture])[0].height
        tall = round(250 / shs11.PORTRAIT_SCALE)
        self.assertEqual(height_of(tall), round(tall * shs11.PORTRAIT_SCALE))       # already that high
        near = round(236 / shs11.PORTRAIT_SCALE)
        self.assertEqual(height_of(near), shs11.PORTRAIT_HEIGHT)                    # lifted to the line
        short = round(180 / shs11.PORTRAIT_SCALE)
        self.assertEqual(height_of(short), round(short * shs11.PORTRAIT_SCALE) + shs11.PORTRAIT_LIFT)

    def test_the_widest_look_is_still_read_as_2x_art(self):
        self.assertLessEqual(round(215 * shs11.PORTRAIT_SCALE), 256)
        self.assertLessEqual(round(235 * shs11.PORTRAIT_SCALE), 300)

    def test_a_look_that_draws_nothing_stays_as_it_is(self):
        self.assertEqual(shs11.shown_faces([None, None]), [None, None])

    def test_the_same_look_in_two_tables_is_one_look_with_both_wearers(self):
        one, two = pairs(p0=(60, -1)), pairs(p0=(61, -1))
        looks = shs11.looks_of({270: [(5, 2, 'Sam', one), (6, 1, 'Hector', two)], 277: [(9, 2, 'Samantha', one)]})
        self.assertEqual([look.pairs for look in looks], [one, two])
        self.assertEqual(looks[0].wearers, ((270, 5, 'Sam'), (277, 9, 'Samantha')))

    def test_parts_no_look_draws_are_found(self):
        res = {0: (shs11.KIND_IMAGE, b''), 60: (shs11.KIND_IMAGE, b''), 61: (shs11.KIND_IMAGE, b''), 70: (shs11.KIND_PALETTE, b'')}
        looks = shs11.looks_of({1: [(1, 1, 'A', pairs(p0=(60, -1)))]})
        self.assertEqual(shs11.unused_parts(res, looks), [61])

    def test_a_cast_table_is_read_from_its_loop(self):
        memory_words = [0] * 40
        base = 40
        name = b'Sam\0'
        rows = [5, 2, 30] + [60, -1] + [-1, -1] * (shs11.PAIRS - 1)
        memory_words[30:32] = struct.unpack('>hh', name)
        memory_words[20] = base
        data = memory_words + rows
        script = b'kiwi' + bytes([2, 0, 0]) + struct.pack('>hhhh', len(data), 0, 0, 0) + struct.pack(f'>{len(data)}h', *data)
        instructions = [SimpleNamespace(opcode=0x1a, operand=1), SimpleNamespace(opcode=0x40, operand=20),
                        SimpleNamespace(opcode=0x41, operand=-1), SimpleNamespace(opcode=0x1a, operand=shs11.CAST_RECORD),
                        SimpleNamespace(opcode=0x1f, operand=5 << 8 | 1)]
        with patch('exp_runtime.decode.bytecode.decode_program', return_value=SimpleNamespace(instructions=instructions)):
            tables = shs11.cast_tables({270: (shs11.KIND_SCRIPT, script), 1: (shs11.KIND_IMAGE, b'')})
        self.assertEqual(list(tables), [270])
        self.assertEqual(tables[270][0][:3], (5, 2, 'Sam'))
        self.assertEqual(tables[270][0][3][0], (60, -1))


@unittest.skipUnless(HAS_PIL, 'needs Pillow')
class AddonTests(unittest.TestCase):
    def build(self, sounds=11):
        res = {i: (shs11.KIND_IMAGE, location(i % 2 == 0)) for i in range(shs11.LOCATIONS)}
        res[shs11.BAND_RESOURCE] = (shs11.KIND_TABLE, struct.pack('>II', 1, 2) + bytes([1, 1]))
        res[60] = (shs11.KIND_IMAGE, character_part(RED))
        res[61] = (shs11.KIND_IMAGE, character_part(GREEN))
        art = jar({'default_0': default_archive(res), 'gamelib.0': gamelib([b'\0\0' + stored_picture(2, 2, RED + GREEN)])})
        english = jar({'default_0': default_archive({0: (shs11.KIND_IMAGE, b'')})})
        tracks = jar({'gamelib.0': gamelib([midi(n + 1) for n in range(sounds)])})
        tables = {270: [(5, 2, 'Sam', pairs(p0=(60, -1))), (6, 3, 'Cat', pairs())]}
        with patch.object(shs11, 'cast_tables', return_value=tables), patch.object(shs11, 'stacked_png', return_value=b'png'):
            return shs11.build_addon(art, english, tracks, render=lambda data: b'mp3' + data[:4])

    def test_the_addon_holds_everything_and_says_where(self):
        data, spec = self.build()
        archive = ExpArchive(data)
        self.assertEqual(addon_record(archive), ('provides', dict(id='shs11', title="Surviving High School '11", revision=2)))
        self.assertEqual(json.loads(archive.read(shs11.SPEC)), spec)
        self.assertEqual(len(spec['backgrounds']), shs11.LOCATIONS)
        self.assertEqual(spec['backgrounds']['0'], [26000, 26001])
        self.assertEqual(spec['backgrounds']['1'], [26002])
        for lightings in spec['backgrounds'].values():
            for picture in lightings:
                self.assertIn(picture, archive.entries)

    def test_a_looks_five_faces_have_lasting_ids(self):
        _, spec = self.build()
        look = spec['looks'][0]
        self.assertEqual((look['id'], look['names'], look['kind']), (shs11.PORTRAIT_BASE, ['Sam'], 2))

    def test_a_voice_with_no_picture_keeps_its_place_with_no_picture(self):
        data, spec = self.build()
        look = spec['looks'][1]
        self.assertIsNone(look['id'])
        self.assertEqual(look['names'], ['Cat'])
        self.assertNotIn(shs11.PORTRAIT_BASE + shs11.EXPRESSIONS, ExpArchive(data).entries)

    def test_parts_no_look_draws_go_in_too(self):
        data, spec = self.build()
        self.assertEqual(spec['parts']['61']['id'], shs11.PART_BASE)
        self.assertIn(shs11.PART_BASE, ExpArchive(data).entries)

    def test_the_interface_and_music_are_there(self):
        data, spec = self.build()
        archive = ExpArchive(data)
        self.assertEqual(spec['interface']['0.0.0']['id'], shs11.INTERFACE_BASE)
        self.assertEqual(spec['music'], list(range(shs11.MUSIC_BASE, shs11.MUSIC_BASE + shs11.SOUNDS)))
        self.assertEqual(archive.read(shs11.MUSIC_BASE + shs11.SURPRISE_TRACK), archive.read(shs11.MUSIC_BASE + shs11.SURPRISE_COPY_OF))
        self.assertEqual(archive.read(shs11.MUSIC_BASE), b'mp3MThd')

    def test_it_builds_the_same_twice(self):
        self.assertEqual(self.build()[0], self.build()[0])

    def test_a_looks_faces_are_stored_cut_and_enlarged(self):
        data, spec = self.build()
        face = Image.open(io.BytesIO(ExpArchive(data).read(spec['looks'][0]['id']))).convert('RGBA')
        self.assertEqual(face.size, (2, 5 + shs11.PORTRAIT_LIFT))   # the part's 2 across, its box's 4 down, by 1.19, raised
        self.assertGreater(face.getpixel((0, 0))[3], 200)   # (smoothed by the enlarging)
        self.assertLess(face.getpixel((0, 4))[3], 50)

    def test_a_jar_without_all_the_sounds_is_refused(self):
        with self.assertRaises(shs11.Shs11Error):
            self.build(sounds=4)

    def test_the_id_ranges_dont_overlap(self):
        self.assertLessEqual(shs11.BACKGROUND_BASE + 2 * shs11.LOCATIONS, shs11.INTERFACE_BASE)
        self.assertLess(shs11.SPEC, shs11.PORTRAIT_BASE)
        self.assertLess(shs11.PART_BASE, shs11.MUSIC_BASE)


def program(*instructions, words=()):
    code = bytearray()
    for item in instructions:
        op, arg = item if isinstance(item, tuple) else (item, None)
        code.append(op)
        if op in OPERAND_OPCODES:
            code.extend(struct.pack('>H', arg & 0xFFFF))
    header = b'kiwi\x02\x00\x00' + struct.pack('>4H', len(words), 0, 0, len(instructions))
    return header + struct.pack(f'>{len(words)}H', *(w & 0xFFFF for w in words)) + bytes(code)


def text_words(text):
    data = text.encode('latin-1') + b'\0'
    data += b'\0' * (len(data) % 2)
    return [data[i] << 8 | data[i + 1] for i in range(0, len(data), 2)]


def call(service, argc):
    return (0x1F, service << 8 | argc)


def push(*values):
    return [(0x1A, value) for value in values]


FIRST = 270
SAM, ZOE = 61, 84


def setup_script(*body, table=()):
    """A setup script: `body`, a halt, and behind it the shape cast_tables finds, over a cast of Sam and Zoe. Its words:
    the cast's address at 0, `table` at 1, then the records and their names."""
    records, text = [], []
    start = 1 + len(table) + shs11.CAST_RECORD * 2
    for character, name in ((SAM, 'sam'), (ZOE, 'Zoe')):
        pairs = [(60 + character, -1)] + [(-1, -1)] * (shs11.PAIRS - 1)
        records += [character, 2, start + len(text)] + [word for pair in pairs for word in pair]
        text += text_words(name)
    words = [1 + len(table), *table, *records, *text]
    return program(*body, 0x33, *push(2), (0x40, 0), (0x41, 0), *push(shs11.CAST_RECORD), call(5, 1), words=words)


def story_jar(*scripts, fallbacks=None):
    res = {FIRST + i: (shs11.KIND_SCRIPT, data) for i, data in enumerate(scripts)}
    for index in range(shs11.LOCATIONS):
        res[index] = (shs11.KIND_IMAGE, location(index == 3))
    return res, shs11_story.Story('Test', 7, range(FIRST, FIRST + len(scripts)), fallbacks or {})


def translated(*scripts, fallbacks=None):
    res, story = story_jar(*scripts, fallbacks=fallbacks)
    return ExpArchive(shs11_story.translate(res, story, None))


def yields(data, results=(), limit=200):
    """(service, args) of every yield until the script halts, and the VM; each yield is answered from `results`, then 0."""
    vm, out, results = KiwiVM(decode_program(data)), [], list(results)
    for _ in range(limit):
        stop = vm.run()
        if stop.kind == StopKind.HALT:
            return out, vm
        out.append((stop.yield_id, tuple(a - 65536 if a >= 32768 else a for a in stop.args)))
        vm.resume(results.pop(0) if results else 0)
    raise AssertionError('the script did not halt')


PROLOGUE = 3                            # the narrator's three calls at the start of a setup script


def said_script(*lines, words=()):
    """A '11 script saying `lines` (word addresses), through its function around 24; the odd ones by narration (33)."""
    body = []
    speaker = 2
    for k, address in enumerate(lines):
        if k % 2:
            body += [*push(address), call(33, 1)]
        else:
            body += [*push(address, SAM, 0, 0), 0x42, (0x29, speaker), 0x18]
    return program((0x29, 10), 0x33, 0x48, 0x4A, (0x41, 0xFFFA), (0x41, 0xFFFB), (0x41, 0xFFFC), call(24, 3), 0x22, 0x43, *body, 0x33,
                   words=words)


class SceneMusicTests(unittest.TestCase):
    def test_an_episode_that_starts_its_story_in_its_first_script_has_no_setup_to_run_between_scenes(self):
        words = text_words('Hello')
        twin = ExpArchive(encode_exp({25001: program(*push(8201, 0), call(80, 2), *push(0, SAM), call(13, 2), 0x33, words=words)}))
        self.assertIsNone(shs11_story.twin_setup(twin))
        self.assertEqual(shs11_story.scene_music(twin), [])

    def test_the_smartphones_setup_script_stops_its_music_between_scenes(self):
        twin = ExpArchive(encode_exp({25001: program(*push(1000), call(81, 1), 0x33)}))
        self.assertEqual(shs11_story.scene_music(twin), [(81, 1000)])


class MusicPlacementTests(unittest.TestCase):
    TEXTS = ('Hello', 'Goodbye', 'Again', 'Unknown', 'Other')

    def setUp(self):
        self.words, self.at = [], {}
        for text in self.TEXTS:
            self.at[text] = len(self.words)
            self.words += text_words(text)

    def said(self, *texts):
        return said_script(*(self.at[text] for text in texts), words=self.words)

    def music(self, story_scripts, *twin_scripts):
        """smartphone_music over '11's scripts (each a tuple of texts) and the smartphone's (raw instructions)."""
        res, story = {}, shs11_story.Story('Test', 7, range(FIRST, FIRST + len(story_scripts)), {})
        for k, texts in enumerate(story_scripts):
            res[FIRST + k] = (shs11.KIND_SCRIPT, self.said(*texts))
        twin = ExpArchive(encode_exp({25002 + k: program(*script, words=self.words) for k, script in enumerate(twin_scripts)}))
        return shs11_story.smartphone_music(res, story, twin)

    def line(self, text):
        return [*push(self.at[text], SAM), call(13, 2)]

    def test_the_lines_of_a_script_are_found_with_where_to_run_something(self):
        sites = shs11_story.spoken_sites(self.said('Hello', 'Goodbye', 'Again'))
        self.assertEqual([site[1:] for site in sites], [('Hello', False), ('Goodbye', True), ('Again', False)])
        self.assertEqual(sites[0][0], 10)                               # the first of its pushes
        self.assertEqual(sites[1][0], 10 + 7)

    def test_a_thought_has_its_text_second(self):
        data = program((0x29, 10), 0x33, 0x48, 0x4A, (0x41, 0xFFFA), (0x41, 0xFFFB), (0x41, 0xFFFC), call(24, 3), 0x22, 0x43,
                       *push(-2, self.at['Hello'], SAM, 0), 0x42, (0x29, 2), 0x18, 0x33, words=self.words)
        self.assertEqual([site[1] for site in shs11_story.spoken_sites(data)], ['Hello'])

    def test_music_goes_before_the_line_it_comes_before(self):
        plan, lost = self.music([('Hello', 'Goodbye')], [*self.line('Hello'), *push(8201, 0), call(80, 2), *self.line('Goodbye'), 0x33])
        self.assertEqual(lost, [])
        pc = shs11_story.spoken_sites(self.said('Hello', 'Goodbye'))[1][0]
        self.assertEqual(plan, {FIRST: {pc: [(80, 8201, 0)]}})

    def test_a_line_said_twice_is_told_apart_by_the_line_before_it(self):
        twin = [*self.line('Hello'), *self.line('Again'), *self.line('Goodbye'), *push(1000), call(81, 1), *self.line('Again'), 0x33]
        plan, lost = self.music([('Hello', 'Again', 'Goodbye', 'Again')], twin)
        self.assertEqual(lost, [])
        pc = shs11_story.spoken_sites(self.said('Hello', 'Again', 'Goodbye', 'Again'))[3][0]
        self.assertEqual(plan, {FIRST: {pc: [(81, 1000)]}})

    def test_a_line_said_twice_is_told_apart_by_the_line_after_it_too(self):
        twin = [*self.line('Hello'), *self.line('Goodbye'), *self.line('Again'), *push(1000), call(81, 1), *self.line('Goodbye'), *self.line('Other'), 0x33]
        said = ('Unknown', 'Goodbye', 'Other')
        plan, lost = self.music([said], twin)
        self.assertEqual((lost, list(plan[FIRST])), ([], [shs11_story.spoken_sites(self.said(*said))[1][0]]))

    def test_music_after_a_game_stays_after_it_though_a_card_comes_before_the_game(self):
        # 'Other', narrated, is the game's instruction: '11's own card, with the game between it and the line.
        text = lambda name: self.at[name]
        story = program((0x29, 10), 0x33, 0x48, 0x4A, (0x41, 0xFFFA), (0x41, 0xFFFB), (0x41, 0xFFFC), call(24, 3), 0x22, 0x43,
                        *push(text('Other')), call(33, 1), call(49, 0), 0x21, 0x18,
                        *push(text('Hello'), SAM, 0, 0), 0x42, (0x29, 2), 0x18, 0x33, words=self.words)
        sites = {said: pc for pc, said, _ in shs11_story.spoken_sites(story)}
        res = {FIRST: (shs11.KIND_SCRIPT, story)}
        twin = ExpArchive(encode_exp({25002: program(*push(8205, 0), call(80, 2), *self.line('Hello'), 0x33, words=self.words)}))
        plan, lost = shs11_story.smartphone_music(res, shs11_story.Story('Test', 7, range(FIRST, FIRST + 1), {}), twin)
        self.assertEqual(plan, {FIRST: {sites['Hello']: [(80, 8205, 0)]}})
        self.assertEqual(lost, [])

    def test_music_goes_before_a_card_11_adds_just_before_its_line(self):
        said = ('Hello', 'Unknown', 'Goodbye')                  # 'Unknown', second, is narration
        plan, lost = self.music([said], [*self.line('Hello'), *push(8201, 0), call(80, 2), *self.line('Goodbye'), 0x33])
        self.assertEqual((lost, list(plan[FIRST])), ([], [shs11_story.spoken_sites(self.said(*said))[1][0]]))

    def test_a_line_said_twice_with_no_matching_line_before_it_has_no_place(self):
        twin = [*self.line('Hello'), *self.line('Again'), *self.line('Goodbye'), *push(1000), call(81, 1), *self.line('Again'), 0x33]
        plan, lost = self.music([('Other', 'Again')], twin)
        self.assertEqual((plan, lost), ({}, [(81, 1000)]))

    def test_a_line_said_once_takes_the_music_wherever_11_says_it(self):
        plan, lost = self.music([('Other', 'Goodbye', 'Again', 'Goodbye')],
                                [*self.line('Hello'), *push(8201, 0), call(80, 2), *self.line('Goodbye'), *self.line('Hello'), 0x33])
        self.assertEqual(lost, [])
        sites = shs11_story.spoken_sites(self.said('Other', 'Goodbye', 'Again', 'Goodbye'))
        self.assertEqual(plan[FIRST], {sites[1][0]: [(80, 8201, 0)], sites[3][0]: [(80, 8201, 0)]})

    def test_music_passes_lines_11_lacks_but_not_too_many(self):
        near = [*push(8201, 0), call(80, 2), *self.line('Unknown'), *self.line('Goodbye'), 0x33]
        self.assertEqual(self.music([('Hello', 'Goodbye')], near)[1], [])
        far = [*push(8201, 0), call(80, 2), *self.line('Unknown') * (shs11_story.MUSIC_REACH + 1), *self.line('Goodbye'), 0x33]
        self.assertEqual(self.music([('Hello', 'Goodbye')], far)[1], [(80, 8201, 0)])

    def test_music_in_a_function_goes_before_the_line_after_its_call(self):
        function = [(0x29, 9), 0x48, 0x4A, *push(8201, 0), call(80, 2), 0x22, 0x43, 0x42, (0x29, 1), *self.line('Goodbye'), 0x33]
        plan, lost = self.music([('Hello', 'Goodbye')], function)
        self.assertEqual((lost, list(plan[FIRST])), ([], [shs11_story.spoken_sites(self.said('Hello', 'Goodbye'))[1][0]]))

    def test_music_before_a_branch_goes_before_both_ways(self):
        branch = [*push(8201, 0), call(80, 2), *push(1), (0x2B, 7), *self.line('Hello'), 0x33, *self.line('Goodbye'), 0x33]
        plan, lost = self.music([('Hello', 'Goodbye')], branch)
        sites = shs11_story.spoken_sites(self.said('Hello', 'Goodbye'))
        self.assertEqual((lost, sorted(plan[FIRST])), ([], [sites[0][0], sites[1][0]]))


@unittest.skipUnless(HAS_PIL, 'needs Pillow')
class StoryTests(unittest.TestCase):
    def script(self, *body, table=()):
        """A translated setup script's calls, after the prologue's."""
        calls, _ = yields(translated(setup_script(*body, table=table)).read(shs11_story.FIRST_SCRIPT))
        return calls[PROLOGUE:]

    def number_vm(self, *body):
        """A translated script's calls, with SHS's numbers kept as the VM's own (53 and 52 answered from a dict)."""
        vm = KiwiVM(decode_program(translated(setup_script(*body)).read(shs11_story.FIRST_SCRIPT)))
        numbers, calls = {}, []
        for _ in range(400):
            stop = vm.run()
            if stop.kind == StopKind.HALT:
                return calls, numbers
            args = tuple(a - 65536 if a >= 32768 else a for a in stop.args)
            calls.append((stop.yield_id, args))
            result = 0
            if stop.yield_id == 52:
                numbers[args[:2]] = args[2]
            elif stop.yield_id == 53:
                result = numbers.get(args[:2], 0)
            vm.resume(result)
        raise AssertionError('the script did not halt')

    def test_an_unset_number_has_all_its_bits_set_as_in_11(self):
        body = [*push(0, 6000, 3), call(3, 3), 0x21, *push(0), 0x0A, (0x2B, 3), *push(1), call(19, 1)]
        calls, _ = self.number_vm(*body)
        self.assertNotIn((79, (shs11.MUSIC_BASE + shs11_story.CUE_TRACKS[1],)), calls)      # read 1: != 0, no cue

    def test_setting_a_bit_keeps_the_others_and_stores_plus_one(self):
        body = [*push(0, 6000, 0), call(0, 3), *push(0, 6000, 2, 1), call(2, 4), *push(0, 6000, 0, 1), call(2, 4)]
        _, numbers = self.number_vm(*body)
        self.assertEqual(numbers[(0, 6000)], 5 + 1)
        body += [*push(0, 6000, 2, 0), call(2, 4)]
        _, numbers = self.number_vm(*body)
        self.assertEqual(numbers[(0, 6000)], 1 + 1)

    def test_a_bit_reads_back(self):
        set_up = [*push(0, 6000, 0), call(0, 3), *push(0, 6000, 2, 1), call(2, 4)]
        for bit, answer in ((2, 1), (1, 0)):
            body = [*set_up, *push(0, 6000, bit), call(3, 3), 0x21, (0x2B, 3), *push(1), call(19, 1)]
            calls, _ = self.number_vm(*body)
            cue = (79, (shs11.MUSIC_BASE + shs11_story.CUE_TRACKS[1],))
            self.assertEqual(cue in calls, bool(answer), bit)

    def test_a_stored_name_goes_in_its_key_and_on_its_character(self):
        calls = self.script(*push(62, 1, 2), call(12, 3))
        self.assertEqual([call[0] for call in calls[:3]], [47, 46, 64])
        self.assertEqual(calls[0][1][-1], -1)
        self.assertEqual(calls[2][1][0], 62)

    def test_a_key_set_directly_and_a_random_number_are_shss_own(self):
        self.assertEqual(self.script(*push(1, 2), call(6, 2))[0], (46, (1, 2)))
        self.assertEqual(self.script(*push(4), call(54, 1))[0], (27, (4,)))

    def game_results(self, plan, twin=None):
        """49's result for scores 0, 3 and 6 in a word game with this stand-in."""
        data = setup_script(call(49, 0))
        site = next(pc for pc, i in enumerate(decode_program(data).instructions) if i.opcode == 0x1F)
        res = story_jar(data)[0]
        story = shs11_story.Story('Test', 7, range(FIRST, FIRST + 1), {(FIRST, site): plan})
        script = decode_program(ExpArchive(shs11_story.translate(res, story, twin)).read(shs11_story.FIRST_SCRIPT))
        results = []
        for score in (0, 3, 6):
            vm = KiwiVM(script)
            while True:
                stop = vm.run()
                if stop.yield_id == 71:
                    vm.resume(score)
                    stop = vm.run()             # (the game's song stopping, which leaves 49's result in R after it)
                    self.assertEqual(stop.yield_id, 81)
                    vm.resume(0)
                    vm.run()
                    results.append(vm.result)
                    break
                vm.resume(0)
        return results

    def test_a_word_games_result_is_a_win_or_not_unless_it_has_tiers(self):
        self.assertEqual(self.game_results(shs11_story.OwnWords('a', 'b', 'c')), [0, 0, 2])
        words = text_words('Do it')
        twin = program(0x48, 0x4A, *push(0, 0, 0, 0, 20000, 4, 1, 3000), call(71, 8), 0x33, words=words)
        archive = ExpArchive(encode_exp({25002: twin}))
        plan = shs11_story.TwinWords(25002, 10, tiers=3)
        self.assertEqual(self.game_results(plan, archive), [0, 1, 2])

    def test_the_smartphones_music_runs_before_its_line(self):
        body = (*push(1), call(33, 1))                      # (a line's first push is its first instruction here)
        res, story = story_jar(setup_script(*body))
        plan = {FIRST: {0: [(81, 1000), (80, 8201, 0)]}}
        with patch.object(shs11_story, 'smartphone_music', return_value=(plan, [])), patch.object(shs11_story, 'scene_music', return_value=[]):
            archive = ExpArchive(shs11_story.translate(res, story, object()))
        calls, _ = yields(archive.read(shs11_story.FIRST_SCRIPT))
        self.assertEqual([call[0] for call in calls[PROLOGUE:PROLOGUE + 3]], [81, 80, 13])
        self.assertEqual(calls[PROLOGUE:PROLOGUE + 2], [(81, (1000,)), (80, (8201, 0))])

    def test_the_smartphones_music_between_scenes_runs_in_the_setup_script_only(self):
        res, story = story_jar(setup_script(*push(FIRST + 1), call(18, 1)), program(*push(FIRST), call(18, 1), 0x33))
        with patch.object(shs11_story, 'smartphone_music', return_value=({}, [])), patch.object(shs11_story, 'scene_music', return_value=[(81, 1000)]):
            archive = ExpArchive(shs11_story.translate(res, story, object()))
        setup = yields(archive.read(shs11_story.FIRST_SCRIPT))[0]
        self.assertEqual(setup[PROLOGUE:PROLOGUE + 2], [(81, (1000,)), (10, (shs11_story.FIRST_SCRIPT + 1, 0))])
        self.assertEqual([call[0] for call in yields(archive.read(shs11_story.FIRST_SCRIPT + 1))[0]], [10])

    def test_the_switch_covers_this_pack(self):
        from exp_runtime.shs import profile
        self.assertIn(shs11.PACK_ID, profile.SMARTPHONE_MUSIC_PACKS)

    def test_the_right_and_wrong_cues_are_answer_feedback_as_shss_are(self):
        from exp_runtime.shs import profile
        self.assertEqual(profile.TRANSLATED_FEEDBACK_MUSIC[shs11.PACK_ID],
                         {shs11.MUSIC_BASE + shs11_story.CUE_TRACKS[1]: 1, shs11.MUSIC_BASE + shs11_story.CUE_TRACKS[0]: -1})

    def test_a_relationship_is_also_what_shs_shows(self):
        # 0-3 show 4-1 skulls and 4-7 show 1-4 smileys ('11's dc and b.n); SHS's 407 runs -4..3 for the same icons.
        for value, shown in ((0, -4), (3, -1), (4, 0), (7, 3)):
            calls = self.script(*push(SAM, 4000, value), call(0, 3))
            self.assertEqual(calls, [(52, (SAM, 4000, value + 1)), (52, (SAM, 407, shown)), (52, (SAM, 629, 0))])

    def test_no_relationship_hides_the_badge(self):
        self.assertEqual(self.script(*push(SAM, 4000, -1), call(0, 3))[-1], (52, (SAM, 629, 1)))

    def test_the_love_interest_is_also_shss(self):
        calls = self.script(*push(0, 4001, SAM), call(0, 3))
        self.assertEqual(calls, [(52, (0, 4001, SAM + 1)), (52, (0, 601, SAM))])

    def test_an_opening_table_sets_each_badge(self):
        calls = self.script(*push(2, 1), call(10, 2), table=(SAM, 6))
        self.assertEqual(calls, [(52, (SAM, 4000, 7)), (52, (SAM, 407, 2)), (52, (SAM, 629, 0))])

    def test_a_reset_sets_each_number_to_0(self):
        calls = self.script(*push(2, 1), call(11, 2), table=(6500, 6501))
        self.assertEqual(calls, [(52, (0, 6500, 1)), (52, (0, 6501, 1))])

    def test_an_unset_number_reads_minus_one(self):
        # Stored plus one, as an SHS number reads 0 unset. The push of R after the read becomes a push of B.
        data = translated(setup_script(*push(0, 6500), call(1, 2), 0x21, 0x04)).read(shs11_story.FIRST_SCRIPT)
        calls, vm = yields(data)
        self.assertEqual(calls[-1], (53, (0, 6500)))
        self.assertEqual(vm.b, -1)
        _, vm = yields(data, results=[0] * PROLOGUE + [6])
        self.assertEqual(vm.b, 5)

    def test_a_read_with_no_push_of_its_result_is_refused(self):
        with self.assertRaises(shs11_story.StoryError):
            translated(setup_script(*push(0, 6500), call(1, 2), 0x15))

    def test_a_cast_member_gets_a_capital_a_colour_and_a_look(self):
        calls = self.script(*push(1), call(5, 1))
        self.assertEqual(calls[:2], [(52, (SAM, 651, 2)), (52, (SAM, 629, 1))])
        self.assertEqual(calls[2][0], 64)
        self.assertEqual(calls[3], (72, (SAM, shs11.PORTRAIT_BASE)))
        self.assertEqual(len(calls), 4)

    def test_the_scripts_queue_as_the_smartphones(self):
        calls = self.script(*push(FIRST), call(18, 1), *push(FIRST + 2), call(18, 1))
        self.assertEqual(calls, [(10, (25001, 1)), (10, (25003, 0))])

    def test_a_location_with_one_lighting_has_it_whatever_the_variant(self):
        calls = self.script(*push(2, 3), call(36, 2), *push(2, 4), call(36, 2))
        self.assertEqual([args[1] for service, args in calls if service == 54],
                         [shs11.background_id(3, 1), shs11.background_id(4, 0)])
        self.assertEqual([service for service, _ in calls], [54, 55, 11, 54, 55, 11])

    def test_cues_are_the_sounds_the_full_builds_slots_give(self):
        # (Selector -> slot -> entry 5's object, where object 2 is a second reference to object 0.)
        self.assertEqual({selector: track for selector, track in shs11_story.CUE_TRACKS.items()},
                         {0: 2, 1: 0, 2: shs11.SURPRISE_TRACK, 3: 4, 4: 3})
        self.assertEqual(shs11.SURPRISE_COPY_OF, shs11_story.CUE_TRACKS[0])

    def test_a_cue_is_an_effect_and_8_has_none(self):
        self.assertEqual(self.script(*push(0), call(19, 1), *push(8), call(19, 1)), [(79, (shs11.MUSIC_BASE + 2,))])

    def test_a_service_with_no_translation_is_refused(self):
        with self.assertRaises(shs11_story.StoryError):
            translated(setup_script(call(34, 0)))

    def test_a_game_with_no_stand_in_is_refused(self):
        with self.assertRaises(shs11_story.StoryError):
            translated(setup_script(call(49, 0)))

    def test_own_words_answer_as_the_game_would(self):
        fallbacks = {(FIRST, 0): shs11_story.OwnWords('Roll!', 'A|B', 'C|D|E')}
        data = translated(setup_script(call(49, 0), 0x21, 0x04), fallbacks=fallbacks).read(shs11_story.FIRST_SCRIPT)
        for score, result in ((6, shs11_story.WON), (5, shs11_story.LOST)):
            calls, vm = yields(data, results=[0] * (PROLOGUE + 2) + [score])
            self.assertEqual([c[0] for c in calls[-2:]], [71, 81])
            self.assertEqual(vm.b, result)

    def test_a_memory_game_stands_in_as_one_word_boards(self):
        memory = [*text_words('DECAF'), 0, 0]           # the table, (cue, word), after the word
        problems = shs11_story.memory_problems(SimpleNamespace(text=lambda text: text), memory, len(memory) - 2, rounds=1)
        self.assertEqual(problems, [4, 4, 'Decaf!', 'Decaf', 'decaf', 'decafwb', 1, 0, 1, -1])

    def test_a_twins_game_is_read_from_its_constants_and_locals(self):
        twin = decode_program(program(0x48, 0x4A, *push(1234), *push(9), 0x5F, 0x3F, *push(5), call(96, 3), 0x33))
        self.assertEqual(shs11_story.call_arguments(twin, 7), [9, 1234, 5])

    def test_a_story_says_its_addon_and_pack(self):
        archive = translated(setup_script())
        self.assertEqual(addon_record(archive), ('requires', ((shs11.ADDON_ID, shs11.ADDON_REVISION),)))
        metadata = archive.metadata()
        self.assertEqual((metadata.pack_id, metadata.episode_id, metadata.titles[0]), (shs11.PACK_ID, 7, 'Test (SHS11)'))

    def test_it_plays_in_the_real_session(self):
        title, default, key = 0, 2, 4
        words = [*text_words('Hi'), *text_words('Zoe'), *text_words('$ZOE')]
        line = len(words)
        words += text_words('Hi, $ZOE!')
        scene = program(*push(title, default, key, ZOE), call(32, 4), *push(line, SAM, 0), call(24, 3), call(27, 0), 0x33,
                        words=words)
        data = shs11_story.translate(*story_jar(setup_script(*push(FIRST + 1), call(18, 1)), scene), None)
        record = playthrough.play(data, name='Maya')
        self.assertEqual([item['kind'] for item in record], ['input', 'line', 'message', 'exit'])
        self.assertEqual(record[1]['text'], 'Hi, Maya!')
        self.assertEqual(record[2]['title'], shs11_story.END_TITLE)


if __name__ == '__main__':
    unittest.main()
