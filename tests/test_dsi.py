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

    def test_every_episode_takes_its_stand_in_times(self):
        # (owner, 2026-11-18: at first only the DSi's own stories did; 29 more episodes qualify this way)
        other = resources(*host_call(11, 0, 1009))
        self.assertEqual(dsi.episode_pictures(other), {1009: 'Backyard_Night'})
        story = resources(*host_call(11, 0, 1009), title='01: Making Some Dough')
        self.assertEqual(dsi.episode_pictures(story), {1009: 'Backyard_Night'})
        self.assertEqual(dsi.picture_for(story, 1009), 'Backyard_Night')

    def test_an_own_black_screen_needs_no_counterpart(self):
        def picture(colour):
            out = io.BytesIO()
            Image.new('RGB', (96, 144), colour).save(out, 'JPEG')
            return out.getvalue()
        own = {26000: picture((0, 0, 0)), 26001: picture((40, 90, 160))}
        found = resources(*host_call(11, 0, 1015), *host_call(11, 0, 26000))
        found.raw_asset = own.__getitem__
        self.assertEqual(dsi.episode_pictures(found), {1015: 'GuyBedRoom_Day'})
        found = resources(*host_call(11, 0, 1015), *host_call(11, 0, 26001))
        found.raw_asset = own.__getitem__
        self.assertIsNone(dsi.episode_pictures(found))                    # a picture of its own, not a black one
        found = resources(*host_call(11, 0, 1015), *host_call(11, 0, 26002))
        found.raw_asset = own.__getitem__
        self.assertIsNone(dsi.episode_pictures(found))                    # one it can't read

    def test_the_episode_list_learns_once_which_episodes_qualify(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            library = Library()
            library.directory = folder
            opened = []
            episode = resources(*host_call(11, 0, 1015))

            def open_episode(record_id):
                opened.append(record_id)
                return episode
            library.open_episode = open_episode
            record = dict(id='abc', name='Story.exp')
            self.assertIsNone(dsi.known(library, record))                 # not yet measured
            self.assertTrue(dsi.measure(library, record))
            self.assertTrue(dsi.known(library, record))
            del library._dsi_coverage                                      # a new start reads the library's record
            self.assertTrue(dsi.known(library, record))
            self.assertEqual(opened, ['abc'])
            import json
            from pathlib import Path
            path = Path(folder) / dsi.COVERAGE_FILE
            saved = json.loads(path.read_text(encoding='utf-8'))
            path.write_text(json.dumps(dict(saved, rule=1)), encoding='utf-8')
            del library._dsi_coverage
            self.assertIsNone(dsi.known(library, record))                 # measured under the old rule: again
            dsi.measure(library, record)
            library.addon = lambda addon_id: (dict(file='b.exp', revision=3), library.archive)
            self.assertIsNone(dsi.known(library, record))                 # another add-on: measured again
            library.held = False
            library.addon = lambda addon_id: None
            self.assertFalse(dsi.known(library, record))                  # no add-on: no tag

    def test_translations_and_add_on_episodes_keep_their_own_art(self):
        self.assertIsNone(dsi.episode_pictures(resources(*host_call(11, 0, 1015), pack=31300)))
        self.assertIsNone(dsi.episode_pictures(resources(*host_call(11, 0, 1015), requires=(('shsnr', 3),))))

    def test_a_background_chosen_at_run_time_is_looked_up_too(self):
        found = resources(*host_call(11, 0, 1015))
        self.assertEqual(dsi.picture_for(found, 1010), 'Backyard_Night')    # exact: any episode that qualifies
        self.assertEqual(dsi.picture_for(found, 1009), 'Backyard_Night')    # a stand-in: any episode too (2026-11-18)
        self.assertIsNone(dsi.picture_for(found, 1003))

    def test_titles_are_matched_without_their_number(self):
        self.assertEqual(dsi.story_key('01: Making Some Dough'), 'making some dough')
        self.assertTrue(dsi.is_story(dict(titles=['Football Star'], aliases=['Football Season']),
                                     dict(stories=['football season'])))


class SwitchTests(unittest.TestCase):
    def test_the_settings_are_kept_and_offered_as_one_choice_on_extras(self):
        # Owner, 2026-11-19: one "DSi Backgrounds" choice on Extras, Off / Sharp / Smooth, in place of Add-Ons' switch and
        # DSi Pixels; the two settings stay as they were saved.
        from exp_runtime.menu import SHARED_PREFERENCES
        from exp_runtime.desktop_pause_hd import (ADDON_KEYS, CHOICE_NAMES, CHOICE_PARENTS, HdPauseMenu, PER_GAME_CHOICES,
                                                  SWITCH_BADGES, dsi_backgrounds_value, switch_badge)
        self.assertIs(SHARED_PREFERENCES['dsi_backgrounds'], bool)
        self.assertEqual(SHARED_PREFERENCES['dsi_pixels'], ('sharp', 'smooth'))
        self.assertNotIn('dsi_backgrounds', ADDON_KEYS)
        self.assertEqual(CHOICE_NAMES['dsi_backgrounds'], {'off': 'Off', 'sharp': 'Sharp', 'smooth': 'Smooth'})
        self.assertEqual(CHOICE_PARENTS['dsi_backgrounds'], 'options:extras')
        self.assertNotIn('dsi_pixels', CHOICE_NAMES)
        self.assertEqual([dsi_backgrounds_value(*pair) for pair in ((False, 'smooth'), (True, 'sharp'), (True, 'smooth'))],
                         ['off', 'sharp', 'smooth'])
        self.assertEqual(switch_badge('dsi_backgrounds')[0], 'DSi')
        self.assertEqual(SWITCH_BADGES['dsi_backgrounds'], 'SHSDSI')
        self.assertEqual(HdPauseMenu.addon_choices(dict(dsi_backgrounds='Off')), [])
        self.assertEqual(PER_GAME_CHOICES, ('ch_dialogue', 'claire_powerups'))       # (Claire Hart Dialogue's, CoD)
        menu = HdPauseMenu.__new__(HdPauseMenu)
        menu.SWITCH_LABELS = HdPauseMenu.SWITCH_LABELS
        rows = HdPauseMenu.option_rows(menu, 'extras', dict(undo=True, dsi_backgrounds='Smooth'), [''] * 273)
        self.assertEqual(rows[-1], ('choice', 'DSi Backgrounds', 'dsi_backgrounds'))


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


# ---------- the translations ----------

import dsi_text  # noqa: E402

TABLE = dict(languages=['fr', 'it', 'de', 'es'],
             lines={'hey there $usr': {'fr': 'Salut, $USR\u00a0!', 'de': 'Hallo, $USR!'},
                    'sure': {'fr': 'Bien s\u00fbr.', 'de': 'Klar.'},
                    'make your choice': {'fr': 'Fais ton choix\u00a0!', 'de': 'Entscheide dich!'},
                    'brendan': {'fr': 'Brendan', 'de': 'Michael'}},
             context={'sure': {'are you coming': {'fr': "D'accord.", 'de': 'Okay.'}}},
             menu={'making some dough': {'fr': 'La main \u00e0 la p\u00e2te', 'de': 'Kekse und Kohle'},
                   'dad': {'fr': 'Papa', 'de': 'Vater'}},
             words={'sugar|flour': {'fr': 'farine|sucre'}})


class TextLibrary(Library):
    def __init__(self):
        super().__init__()
        spec = dict(SPEC, text=26900)
        self.archive = SimpleNamespace(read=lambda resource: json.dumps(spec if resource == dsi.SPEC else TABLE).encode(),
                                       entries={dsi.SPEC, 26900})
        self.dsi_language = 'fr'


def story(title='01: Making Some Dough', pack=101):
    library = TextLibrary()
    found = SimpleNamespace(library=library, record=dict(titles=[title], pack_id=pack), required_addons=())
    found.dsi_translation = lambda language=None: dsi.translation(
        found, library.dsi_language if language is None else language)
    return found


class TranslationTests(unittest.TestCase):
    def test_a_line_is_found_by_its_words_and_keeps_its_tokens(self):
        fr = dsi.translation(story(), 'fr')
        self.assertEqual(fr.line('Hey there, $USR!'), 'Salut, $USR\u00a0!')
        self.assertEqual(fr.line('A line the DSi cut.'), 'A line the DSi cut.')
        self.assertIsNone(dsi.translation(story(), 'off'))
        self.assertIsNone(dsi.translation(story('06: The Outcast'), 'fr'))          # not a DSi story
        self.assertIsNone(dsi.translation(story(pack=31300), 'fr'))                 # a New Rules translation of it

    def test_a_line_translated_two_ways_follows_the_line_before(self):
        fr = dsi.translation(story(), 'fr')
        self.assertEqual(fr.line('Sure.'), 'Bien s\u00fbr.')
        fr.line('Are you coming?')
        self.assertEqual(fr.line('Sure!'), "D'accord.")

    def test_names_follow_the_dsi_but_the_players_own_never_changes(self):
        de = dsi.translation(story(), 'de')
        self.assertEqual(de.token('$Player', 'Brendan'), 'Michael')
        self.assertEqual(de.token('$Brendan', 'Brendan'), 'Michael')
        self.assertEqual(de.token('$USR', 'Brendan'), 'Brendan')
        self.assertEqual(de.token('$Kat', 'Kat'), 'Kat')
        self.assertEqual(de.line('Dad'), 'Vater')                    # a name plate, from the menu text

    def test_a_grid_takes_its_own_list_by_the_english_exactly(self):
        fr = dsi.translation(story(), 'fr')
        self.assertEqual(fr.line('sugar|flour'), 'farine|sucre')
        self.assertEqual(fr.line('stir|mix'), 'stir|mix')
        self.assertEqual(dsi.translation(story(), 'de').line('sugar|flour'), 'sugar|flour')

    def test_the_engine_shows_the_language_picked_in_hd_only(self):
        from exp_runtime.engine import EngineState
        resources = story()
        engine = EngineState()
        engine.game_key = 'shs'
        engine.strings = {'$USR': 'Sam', '$Player': 'Brendan'}
        engine.translation_source = resources.dsi_translation
        self.assertEqual(engine.substitute('Hey there, $USR!'), 'Hey there, Sam!')      # no HD build: as before
        engine.hd_version = '1.4.38'
        self.assertEqual(engine.substitute('Hey there, $USR!'), 'Salut, Sam\u00a0!')
        self.assertEqual(engine.substitute('Hey there, $USR!', display=False), 'Hey there, Sam!')
        self.assertEqual(engine.translated_raw('Make your choice!'), 'Fais ton choix\u00a0!')
        resources.library.dsi_language = 'de'
        self.assertEqual(engine.substitute('$Player attacks!'), 'Michael attacks!')
        forms = engine.shown_forms('Hey there, $USR!')
        self.assertTrue({'Hey there, Sam!', 'Salut, Sam\u00a0!', 'Hallo, Sam!'} <= forms)

    def test_a_story_keeps_its_number_in_the_episode_list(self):
        library = TextLibrary()
        self.assertEqual(dsi.episode_title(library, dict(titles=['01: Making Some Dough']), 'fr'),
                         '01: La main \u00e0 la p\u00e2te')
        self.assertIsNone(dsi.episode_title(library, dict(titles=['06: The Outcast']), 'fr'))
        # Owner, 2026-11-18: New Rules' Making Some Dough (a translated game's pack) keeps its own title, as its lines do.
        self.assertIsNone(dsi.episode_title(library, dict(pack_id=31301, titles=['Making Some Dough']), 'fr'))
        self.assertIsNotNone(dsi.episode_title(library, dict(pack_id=1, titles=['01: Making Some Dough']), 'fr'))
        TABLE['lines']['the wrong side of town'] = {'de': '`Falsches Ende der Stadt`'}
        TABLE['menu']['football season'] = {'de': 'Football-Saison'}
        try:
            library = TextLibrary()
            SPEC['stories'] += ['the wrong side of town', 'football star']
            self.assertEqual(dsi.episode_title(library, dict(titles=['10: The Wrong Side of Town']), 'de'),
                             '10: Falsches Ende der Stadt')
            self.assertEqual(dsi.episode_title(library, dict(titles=['Football Star'], aliases=['Football Season']), 'de'),
                             'Football-Saison')
        finally:
            del TABLE['lines']['the wrong side of town'], TABLE['menu']['football season']
            SPEC['stories'][:] = ['making some dough']
        self.assertIsNone(dsi.episode_title(library, dict(titles=['01: Making Some Dough']), 'off'))


class TableBuilderTests(unittest.TestCase):
    def test_text_is_written_as_latin1_and_grids_as_their_font_draws(self):
        self.assertEqual(dsi_text.latin1('C\u0153ur\u2026 l\u2019\u00e9t\u00e9'), "Coeur... l'\u00e9t\u00e9")
        self.assertEqual(dsi_text.grid_letters('W\u00fcrfe|Sto\u00df'), 'wurfe|stoss')
        self.assertEqual(dsi_text.grid_letters('est\u00e1|ma\u00f1o'), 'esta|mano')
        self.assertIsNone(dsi_text.grid_letters('two words'))

    def test_a_pairing_must_keep_its_lines_tokens_and_bars(self):
        self.assertTrue(dsi_text.plausible('Hey, $USR!', 'Salut, $USR\u00a0!'))
        self.assertFalse(dsi_text.plausible('Hey, $USR!', 'Salut\u00a0!'))
        self.assertFalse(dsi_text.plausible('Yes.|No.', 'Oui.'))
        self.assertTrue(dsi_text.plausible('Are you coming?', 'Tu viens.'))             # a question may become a statement
        self.assertFalse(dsi_text.plausible('To my left was a pretty blonde girl, and to my right...', 'Matt'))

    def test_loads_pair_in_code_order_and_a_copied_register_counts(self):
        ldr = lambda register: ('ldr', register)
        mov = 0xE1A01000                                     # mov r1, r0
        english = ([ldr(0), 0xEB, ldr(0), ldr(1), 0xEB], [None] * 5, ['One', None, 'Two', 'Three', None], [None] * 5,
                   [None] * 5)
        same = ([ldr(0), 0xEB, ldr(0), ldr(1), 0xEB], [None] * 5, ['Un', None, 'Deux', 'Trois', None], [None] * 5,
                [None] * 5)
        self.assertEqual([p[1:] for p in dsi_text.pairs(english, same)],
                         [('One', 'Un'), ('Two', 'Deux'), ('Three', 'Trois')])
        reused = ([ldr(0), 0xEB, ldr(0), mov, 0xEB], [None] * 5, ['Un', None, 'Deux', None, None], [None] * 5, [None] * 5)
        self.assertEqual([p[1:] for p in dsi_text.pairs(english, reused)],
                         [('One', 'Un'), ('Two', 'Deux'), ('Three', 'Deux')])

    def test_records_pair_word_by_word_until_they_differ(self):
        self.assertEqual(dsi_text._record_pairs((4, 'Add sugar', 'sugar|flour', 1, 'Next'),
                                                (4, 'Ajoute', 'farine|sucre', 2, 'X')),
                         [(2, 'Add sugar', 'Ajoute'), (3, 'sugar|flour', 'farine|sucre')])

    def test_the_table_keeps_matched_lines_rewrites_contexts_and_grids(self):
        lines = {8: [('Hello there.', {'fr': 'Salut.'}), ('Sure.', {'fr': 'Bien sûr.'}),
                     ('Play on the game thing!', {'fr': 'Joue au truc !'}), ('Bye now.', {'fr': 'Salut !'}),
                     ('Sure.', {'fr': "D'accord."}), ('sugar|flour', {'fr': 'Farine|Sucre'})]}
        phone = {8: ['Hello there.', 'Sure.', 'Play on the Weebox 360!', 'Bye now.', 'Sure.']}
        menu = {name: {1: 'Make your choice!' if name == 'en' else 'Choix'} for name in ('en', 'fr', 'it', 'de', 'es')}
        table, report = dsi_text.translations(lines, phone, menu)
        self.assertEqual(table['lines']['play on the weebox 360'], {'fr': 'Joue au truc !'})    # by its place
        self.assertEqual(table['lines']['sure'], {'fr': 'Bien sûr.'})
        self.assertEqual(table['context']['sure'], {'bye now': {'fr': "D'accord."}})
        self.assertEqual(table['words'], {'sugar|flour': {'fr': 'farine|sucre'}})
        self.assertEqual(table['lines']['make your choice'], {'fr': 'Choix', 'it': 'Choix', 'de': 'Choix', 'es': 'Choix'})
        self.assertEqual(report['rewritten'], 1)
