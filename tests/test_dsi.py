"""shshd-runtime: the SHS DSiWare add-on (`shsdsi`): its builder's readers (tools/translate/nds.py), its map
(tools/translate/dsi.py), which episodes show it (exp_runtime/dsi.py) and its switches. Authored bytes only; no game content."""
import io
import json
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import unittest
import zlib

from PIL import Image

from exp_runtime import dsi
from test_runtime import host_call
from test_vm import program

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools' / 'translate'))
import nds  # noqa: E402
import dsi as builder  # noqa: E402


def lz10_literals(data):
    """LZ10 that stores every byte as a literal (flags 0)."""
    out = bytearray([0x10]) + struct.pack('<I', len(data))[:3]
    for i in range(0, len(data), 8):
        out += b'\0' + data[i:i + 8]
    return bytes(out)


def crc(name):
    return zlib.crc32(name.upper().encode('cp1252')) & 0xFFFFFFFF


def urf(entries):
    """An A2M archive with one locale: entries [(type hash, name, payload)], grouped by type in the order given."""
    types = []
    for type_hash, _, _ in entries:
        if not types or types[-1][0] != type_hash:
            types.append([type_hash, len([t for t in types for _ in range(t[2])]), 0])
        types[-1][2] += 1
    header = b'KTUN' + struct.pack('<II', 0x01000001, 0) + b'RFMN' + struct.pack('<II', len(entries), len(types))
    header += b''.join(struct.pack('<III', *t) for t in types)
    locale_at = len(header) + 8 + 8
    header += b'COLN' + struct.pack('<I', 1) + struct.pack('<II', crc('ENGLISH'), locale_at)
    table_size = 4 + 12 * len(entries)
    body, rows = bytearray(), []
    start = (locale_at + table_size + 31) // 32 * 32
    for type_hash, name, payload in entries:
        payload = payload + b'\0' * (-len(payload) % 4)
        at = start + len(body)
        rows.append(struct.pack('<III', crc(name), len(payload) // 4, at // 32))
        body += payload + b'\0' * (-len(payload) % 32)
    table = b'TAFN' + b''.join(rows)
    data = header + table
    return data + b'\0' * (start - len(data)) + bytes(body)


class ReaderTests(unittest.TestCase):
    def test_lz10_lz11_rle_and_a_diff_layer(self):
        self.assertEqual(nds.decompress(lz10_literals(b'abcdefghij')), b'abcdefghij')
        # LZ11: 'ab', then a back-reference of 4 bytes 2 back
        lz11 = bytes([0x11]) + struct.pack('<I', 6)[:3] + bytes([0b00100000]) + b'ab' + bytes([0x30, 0x01])
        self.assertEqual(nds.decompress(lz11), b'ababab')
        rle = bytes([0x30]) + struct.pack('<I', 7)[:3] + bytes([0x80 | 2, ord('x'), 1]) + b'yz'
        self.assertEqual(nds.decompress(rle), b'xxxxxyz')
        diff = bytes([0x81]) + struct.pack('<I', 4)[:3] + bytes([5, 1, 1, 1])
        self.assertEqual(nds.decompress(diff), bytes([5, 6, 7, 8]))
        self.assertEqual(nds.decompress(b'\x04plain'), b'\x04plain')
        with self.assertRaises(ValueError):
            nds.blz(b'\0' * 16)

    def test_an_archive_keeps_same_named_entries_of_two_types_apart(self):
        data = urf([(1, 'Shared', lz10_literals(b'bitmap!!')), (2, 'Shared', b'\x04\0\0\0palette!')])
        archive = nds.Urf(data)
        self.assertEqual(archive.read(1, 'Shared'), b'bitmap!!')
        self.assertEqual(archive.read(2, 'shared')[:12], b'\x04\0\0\0palette!')       # names are case-blind
        self.assertTrue(archive.has(2, crc('SHARED')))
        self.assertFalse(archive.has(3, 'Shared'))

    def test_an_image_names_its_files(self):
        rom = bytearray(0x400)
        rom[0:12], rom[12:16] = b'S.HIGHSCHOOL', b'K3VV'
        fnt = struct.pack('<IHH', 8, 0, 1) + bytes([len('Rom_2D.urf')]) + b'Rom_2D.urf' + b'\0'
        payload = b'URF!'
        fat = struct.pack('<II', 0x300, 0x300 + len(payload))
        rom[0x200:0x200 + len(fnt)] = fnt
        rom[0x280:0x288] = fat
        rom[0x300:0x304] = payload
        struct.pack_into('<6I', rom, 0x40, 0x200, len(fnt), 0x280, 8, 0x290, 0)
        image = nds.Rom(bytes(rom))
        self.assertEqual((image.title, image.code), ('S.HIGHSCHOOL', 'K3VV'))
        self.assertEqual(image.files(), {'Rom_2D.urf': 0})
        self.assertEqual(image.file('Rom_2D.urf'), b'URF!')


class BuilderTests(unittest.TestCase):
    def test_a_screen_is_turned_upright(self):
        pixels = bytearray(256 * 256)
        pixels[0] = 1                                               # stored top-left
        bitmap = struct.pack('<HHHHI', 256, 256, 0, 0, len(pixels)) + bytes(pixels)
        palette = struct.pack('<IIII', 4, 0, 4, 16) + struct.pack('<HH', 0, 0x7FFF)
        descriptor = struct.pack('<4I', 0, crc('Pic'), 0, crc('Pic'))
        archive = nds.Urf(urf([(builder.BACKGROUND, 'PicLeft_Day', descriptor), (builder.BITMAP, 'Pic', bitmap),
                               (builder.PALETTE, 'Pic', palette)]))
        image = builder.screen(archive, 'PicLeft_Day')
        self.assertEqual(image.size, (192, 256))
        self.assertEqual(image.getpixel((0, 255)), (255, 255, 255))   # turned a quarter: the stored corner is bottom-left
        self.assertEqual(image.getpixel((0, 0)), (0, 0, 0))

    def test_the_bank_map_follows_the_dsi_and_marks_same_time_pictures(self):
        bank = builder.bank_map()
        self.assertEqual(bank['1015'], ['GuyBedRoom_Day', True])
        self.assertEqual(bank['1016'], ['GuyBedRoom_Night', True])
        self.assertEqual(bank['1017'], ['GuyBedRoom_Sunset', True])
        self.assertEqual(bank['1009'], ['Backyard_Night', False])           # the DSi drew the backyard at night only
        self.assertEqual(bank['1010'], ['Backyard_Night', True])
        self.assertEqual(bank['1081'], ['Neighborhood_Sunset', True])       # the bank's one picture is a sunset
        self.assertEqual(bank['1046'], ['Den_Day', False])                  # the DSi's stand-in for a night
        for missing in (1003, 1024, 1075, 1099, 1102):
            self.assertNotIn(str(missing), bank)
        self.assertEqual(len(builder.INDEX_GROUPS), 46)
        self.assertTrue(all(len(group) == 3 for group in builder.INDEX_GROUPS))
        self.assertEqual(builder.picture_key('BedRoomMDay_Left'), 'BedRoomMDay')
        self.assertEqual(builder.picture_key('UrbanSunset_Left'), 'UrbanSunset')
        pictures = {name for name, _ in bank.values()}
        self.assertTrue(pictures <= {builder.picture_key(left) for left in builder.PICTURES})


SPEC = dict(screens={'GuyBedRoom_Day': [26001, 26002], 'Backyard_Night': [26003, 26004]},
            bank={'1015': ['GuyBedRoom_Day', True], '1009': ['Backyard_Night', False], '1010': ['Backyard_Night', True]},
            stories=['making some dough'])


class Library:
    def __init__(self, held=True):
        self.archive = SimpleNamespace(read=lambda resource: json.dumps(SPEC).encode() if resource == dsi.SPEC
                                       else f'png{resource}'.encode(), entries={dsi.SPEC, 26001, 26002})
        self.held = held

    def addon(self, addon_id):
        return (dict(file='a.exp', revision=1), self.archive) if self.held and addon_id == dsi.ADDON else None


def resources(*calls, title='06: The Outcast', pack=101, held=True, requires=()):
    found = SimpleNamespace(library=Library(held), record=dict(titles=[title], pack_id=pack),
                            programs={25001: program(*calls, 0x33)}, exists=lambda resource: resource in (1009, 1010, 1015),
                            required_addons=requires)
    found.dsi_pictures = lambda: dsi.episode_pictures(found)
    return found


class EligibilityTests(unittest.TestCase):
    def test_the_scan_reads_constant_backgrounds_and_title_cards(self):
        shown = dsi.shown_backgrounds([program(*host_call(11, 1, 1009), *host_call(34, 0, 1015),
                                               *host_call(8, -1, 2, 1010, 0), *host_call(11, 2, 1015), 0x33)],
                                      lambda resource: resource in (1009, 1010, 1015))
        self.assertEqual(shown, {1010, 1015})        # 1009 + night; 1015's sunset isn't there, so 1015 itself

    def test_an_episode_qualifies_only_when_every_background_has_a_counterpart(self):
        self.assertEqual(dsi.episode_pictures(resources(*host_call(11, 0, 1015))), {1015: 'GuyBedRoom_Day'})
        self.assertIsNone(dsi.episode_pictures(resources(*host_call(11, 0, 1015), *host_call(11, 0, 1003))))
        self.assertIsNone(dsi.episode_pictures(resources(*host_call(11, 0, 1015), held=False)))

    def test_only_the_dsi_stories_take_its_stand_in_times(self):
        other = resources(*host_call(11, 0, 1009))
        self.assertIsNone(dsi.episode_pictures(other))
        story = resources(*host_call(11, 0, 1009), title='01: Making Some Dough')
        self.assertEqual(dsi.episode_pictures(story), {1009: 'Backyard_Night'})
        self.assertEqual(dsi.picture_for(story, 1009), 'Backyard_Night')

    def test_translations_and_add_on_episodes_keep_their_own_art(self):
        self.assertIsNone(dsi.episode_pictures(resources(*host_call(11, 0, 1015), pack=31300)))
        self.assertIsNone(dsi.episode_pictures(resources(*host_call(11, 0, 1015), requires=(('shsnr', 3),))))

    def test_a_background_chosen_at_run_time_is_looked_up_too(self):
        found = resources(*host_call(11, 0, 1015))
        self.assertEqual(dsi.picture_for(found, 1010), 'Backyard_Night')    # exact: any episode that qualifies
        self.assertIsNone(dsi.picture_for(found, 1009))                     # a stand-in: the DSi stories only
        self.assertIsNone(dsi.picture_for(found, 1003))

    def test_titles_are_matched_without_their_number(self):
        self.assertEqual(dsi.story_key('01: Making Some Dough'), 'making some dough')
        self.assertTrue(dsi.is_story(dict(titles=['Football Star'], aliases=['Football Season']),
                                     dict(stories=['football season'])))


class SwitchTests(unittest.TestCase):
    def test_the_settings_are_kept_and_offered_on_add_ons(self):
        from exp_runtime.menu import SHARED_PREFERENCES
        from exp_runtime.desktop_pause_hd import (ADDON_KEYS, CHOICE_NAMES, HdPauseMenu, PER_GAME_CHOICES, SWITCH_BADGES,
                                                  switch_badge)
        self.assertIs(SHARED_PREFERENCES['dsi_backgrounds'], bool)
        self.assertEqual(SHARED_PREFERENCES['dsi_pixels'], ('sharp', 'smooth'))
        self.assertIn('dsi_backgrounds', ADDON_KEYS)
        self.assertEqual(CHOICE_NAMES['dsi_pixels'], {'sharp': 'Sharp', 'smooth': 'Smooth'})
        self.assertEqual(switch_badge('dsi_backgrounds')[0], 'DSi')
        self.assertEqual(SWITCH_BADGES['dsi_backgrounds'], 'SHSDSI')
        self.assertEqual(HdPauseMenu.addon_choices(dict(dsi_pixels='Sharp')), [('choice', 'DSi Pixels', 'dsi_pixels')])
        self.assertEqual(HdPauseMenu.addon_choices({}), [])
        self.assertIn('dsi_pixels', PER_GAME_CHOICES)


class DesktopTests(unittest.TestCase):
    def test_the_speaker_side_picks_the_screen_and_narration_keeps_it(self):
        import os
        os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
        from collections import OrderedDict
        from exp_runtime import graphics as pygame
        from exp_runtime.desktop import Desktop
        pygame.init()
        pygame.display.set_mode((8, 8))

        def picture(colour):
            out = io.BytesIO()
            Image.new('RGB', (192, 256), colour).save(out, 'PNG')
            return out.getvalue()
        found = resources(*host_call(11, 0, 1015))
        found.dsi_screens = lambda name: (picture((255, 0, 0)), picture((0, 0, 255)))
        ui = Desktop.__new__(Desktop)
        panel = SimpleNamespace(location_align=1)
        ui.session = SimpleNamespace(resources=found, engine=SimpleNamespace(panel=panel))
        scene = pygame.Surface((480, 720))
        ui.images = OrderedDict({1015: scene})
        ui.dsi_backgrounds, ui.dsi_pixels = False, 'sharp'
        self.assertIsNone(ui._dsi_screen(scene))                    # off by default
        ui.dsi_backgrounds = True
        self.assertEqual(ui._dsi_screen(scene).get_at((5, 5))[:3], (255, 0, 0))
        panel.location_align = 3
        right = ui._dsi_screen(scene)
        self.assertEqual(right.get_at((5, 5))[:3], (0, 0, 255))
        panel.location_align = 2
        self.assertIs(ui._dsi_screen(scene), right)
        self.assertTrue(ui._sharp_art(right))
        ui.dsi_pixels = 'smooth'
        self.assertFalse(ui._sharp_art(right))
        self.assertIsNone(ui._dsi_screen(pygame.Surface((480, 720))))      # a picture of no mapped id


if __name__ == '__main__':
    unittest.main()
