"""SHS '11's reader and addon (tools/translate/shs11.py), from authored jars: its archives, the stored PNGs in gamelib, a
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
    import shs11
    from exp_runtime.addons import addon_record
    from exp_runtime.exp import ExpArchive

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
        with patch.object(shs11, 'cast_tables', return_value=tables):
            return shs11.build_addon(art, english, tracks, render=lambda data: b'mp3' + data[:4])

    def test_the_addon_holds_everything_and_says_where(self):
        data, spec = self.build()
        archive = ExpArchive(data)
        self.assertEqual(addon_record(archive), ('provides', dict(id='shs11', title="Surviving High School '11", revision=1)))
        self.assertEqual(json.loads(archive.read(shs11.SPEC)), spec)
        self.assertEqual(len(spec['backgrounds']), shs11.LOCATIONS)
        self.assertEqual(spec['backgrounds']['0'], [dict(picture=26000, band=26050), dict(picture=26001, band=26051)])
        self.assertEqual(spec['backgrounds']['1'], [dict(picture=26002, band=26052)])
        for lightings in spec['backgrounds'].values():
            for lighting in lightings:
                self.assertIn(lighting['picture'], archive.entries)
                self.assertIn(lighting['band'], archive.entries)

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
        self.assertEqual(archive.read(shs11.MUSIC_BASE), b'mp3MThd')

    def test_it_builds_the_same_twice(self):
        self.assertEqual(self.build()[0], self.build()[0])

    def test_a_jar_without_all_the_sounds_is_refused(self):
        with self.assertRaises(shs11.Shs11Error):
            self.build(sounds=4)

    def test_the_id_ranges_dont_overlap(self):
        self.assertLess(shs11.BACKGROUND_BASE + 2 * shs11.LOCATIONS, shs11.BAND_BASE + 1)
        self.assertLessEqual(shs11.BAND_BASE + 2 * shs11.LOCATIONS, shs11.INTERFACE_BASE)
        self.assertLess(shs11.SPEC, shs11.PORTRAIT_BASE)
        self.assertLess(shs11.PART_BASE, shs11.MUSIC_BASE)


if __name__ == '__main__':
    unittest.main()
