"""The `shsdsi` add-on, "SHS DSiWare": the DSiWare game's (2010, A2M) redrawn backgrounds for the smartphone episodes, built
from the player's own DSiWare image (the EUR `.nds`, or its CDN content file: the same bytes).

    python tools/translate/dsi.py --nds DSI_IMAGE --out OUT_DIR

The add-on is optional: no episode declares it. While it's imported and **DSi Backgrounds** is on, an episode whose every
background has a DSi counterpart shows the DSi's two screens in place of the smartphone's picture: the left screen while the
location is aligned left (a speaker on the left), the right while it's aligned right (exp_runtime/dsi.py). The owner's
decisions are in reference/Other Games/docs/DSI_ADDON_SCOPE.md (2026-11-15).

How the map was found (2026-11-15):
- A DSi scene changes background with `FUN_0203ff20(time, location)` (Football Season through a wrapper); the screens are
  `table[location + time]`, a table of name hashes the game fills at start-up. Its groups of three are a location by day,
  night and sunset, the DSi repeating a time it didn't draw (INDEX_GROUPS, decoded from both regions' ARM9: identical).
- The smartphone's bank has the same layout: a location at `1000 + 3k`, its night at +1 and sunset at +2.
- Aligning the eight stories' background changes by the first line each shows paired the two numberings (BANK_GROUPS); the
  rest were matched by eye. 1003 (the arcade's pool table), 1024 (bus stop), 1075 (music room), 1099 and 1102 (washrooms)
  have no DSi drawing.
"""
import argparse
import io
import json
from pathlib import Path
import struct
import sys

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nds import Rom, Urf  # noqa: E402

from exp_runtime.addons import RESOURCE as ADDON_RECORD, provides_bytes  # noqa: E402
from exp_runtime.exp import Metadata, encode_exp  # noqa: E402

ADDON_ID, ADDON_TITLE, ADDON_REVISION = 'shsdsi', 'SHS DSiWare', 1
PACK_ID = 31800                         # its metadata's pack: it has no episodes
SPEC = 26000                            # the spec, JSON (exp_runtime/dsi.py)
SCREEN_BASE = 26001                     # each picture's left screen at 26001 + 2 x its place in PICTURES, its right one after
GAME_CODES = ('K3VV', 'K3VE')           # EUR, USA (the backgrounds are the same in both)

# The scenes' background table, `table[1 + 3k + time]` (time 0 day, 1 night, 2 sunset): each group's left screens. A right
# screen's name is its left one's with Right for Left.
INDEX_GROUPS = (
    ('ClassRoom01Left_Day', 'Classroom01Left_Night', 'ClassRoom01Left_Day'),
    ('HallwayLeft_Day',) * 3,
    ('GuyBedRoomLeft_Day', 'GuyBedRoomLeft_Night', 'GuyBedRoomLeft_Sunset'),
    ('TracksLeft_Day',) * 3,
    ('CafeteriaLeft_Day',) * 3,
    ('ParkingLeft_Day', 'ParkingLeft_Night', 'ParkingLeft_Night'),
    ('GymLeft_Day',) * 3,
    ('BeachLeft_Day', 'BeachLeft_Night', 'BeachLeft_Sunset'),
    ('HomeLeft_Day', 'HomeLeft_Night', 'HomeLeft_Night'),
    ('BackyardLeft_Night',) * 3,
    ('UrbanLeft_Day', 'UrbanLeft_Night', 'UrbanSunset_Left'),
    ('NeighborhoodLeft_Sunset',) * 3,
    ('GirlBedRoomLeft_Day', 'GirlBedRoomLeft_Night', 'GirlBedRoomLeft_Day'),
    ('LushParkLeft_Night',) * 3,
    ('DiningRoomLeft_Day', 'DinningRoomLeft_Night', 'DiningRoomLeft_Day'),
    ('ParkingLeft_Day', 'ParkingLeft_Night', 'ParkingLeft_Night'),
    ('TheaterLeft_Day',) * 3,
    ('StoreLeft_Day',) * 3,
    ('RestaurantFancyLeft_Day',) * 3,
    ('WeightRoomLeft_Day',) * 3,
    ('ClassRoom02Left_Day',) * 3,
    ('OfficeLeft_Day',) * 3,
    ('SchoolLeft_Day',) * 3,
    ('InsideCarLeft_Day', 'InsideCarLeft_Night', 'InsideCarLeft_Night'),
    ('DanceActiveLeft_Day',) * 3,
    ('DanceInactiveLeft_Day',) * 3,
    ('BloodBabyInactiveLeft_Day',) * 3,
    ('ArcadeLeft_Day',) * 3,
    ('LibraryLeft_Day',) * 3,
    ('StageLeft_Day',) * 3,
    ('StageSpotLightLeft_Day',) * 3,
    ('UrbanLeft_Day', 'UrbanLeft_Night', 'UrbanLeft_Day'),
    ('FootballFieldLeft_Day', 'FootballFieldLeft_Night', 'FootballFieldLeft_Sunset'),
    ('DiningRoomLeft_Day', 'DinningRoomLeft_Night', 'DiningRoomLeft_Day'),
    ('LockersLeft_Day',) * 3,
    ('UniversityLeft_Day',) * 3,
    ('DenLeft_Day',) * 3,
    ('BasementLeft_Day',) * 3,
    ('RivalSchoolLeft_Night',) * 3,
    ('VistaLakeLeft_Day', 'VistaLakeLeft_Night', 'VistaLakeLeft_Sunset'),
    ('NurseyLeft_Day',) * 3,
    ('ClassRoom02Left_Day',) * 3,
    ('AutoShopLeft_Day',) * 3,
    ('BedRoomMDay_Left', 'BedRoomMNight_Left', 'BedRoomMDay_Left'),
    ('RestaurantDay_Left', 'RestaurantNight_Left', 'RestaurantDay_Left'),
    ('SkateparkDay_Left',) * 3,
)
# The smartphone bank's locations (1000 + 3k) and the group of INDEX_GROUPS the DSi shows for each. AutoShop is the DSi's
# own pairing: it drew the shop from outside, where the bank's three pictures are inside.
BANK_GROUPS = {
    1000: 27, 1006: 42, 1009: 9, 1012: 7, 1015: 2, 1018: 12, 1021: 43, 1027: 4, 1030: 0, 1033: 41, 1036: 24, 1039: 26,
    1042: 23, 1045: 36, 1048: 14, 1051: 32, 1054: 6, 1057: 8, 1060: 39, 1063: 28, 1066: 34, 1069: 13, 1072: 15, 1078: 10,
    1081: 11, 1084: 40, 1087: 21, 1090: 5, 1093: 44, 1096: 18, 1105: 38, 1108: 22, 1111: 1, 1114: 45, 1117: 29, 1120: 30,
    1123: 17, 1126: 16, 1129: 3, 1132: 35, 1135: 31, 1138: 19}
# A bank picture's time of day is its place after the location's (day, night, sunset), except a location drawn once at
# another time.
BANK_TIMES = {1081: 'Sunset'}
TIMES = ('Day', 'Night', 'Sunset')
# The eight stories the DSi ported (normalised titles, as exp_runtime/dsi.story_key reads a record's): there, a background
# shows whatever the DSi showed at that place, its stand-in times included (owner, 2026-11-15, decision 15).
STORIES = ('football star', 'football season', 'making some dough', 'as time goes by', 'break a leg', 'surviving europe',
           'from europe with love', 'the wrong side of town', 'wrong side of town', 'best party ever')

BACKGROUND, BITMAP, PALETTE = 0x709A6C0A, 0xB54AECF3, 0xFE8C1231


def time_of(name):
    return next((t for t in TIMES[1:] if t in name), 'Day')


def picture_key(left):
    """A location picture's name in the spec: BeachLeft_Night -> Beach_Night, BedRoomMDay_Left -> BedRoomMDay."""
    return left.replace('_Left', '').replace('Left', '').strip('_')


PICTURES = sorted({left for group in INDEX_GROUPS for left in group})


def bank_map():
    """{bank picture: [DSi picture, exact]}: what the DSi shows for it, and whether that is the same time of day."""
    result = {}
    for base, group in BANK_GROUPS.items():
        for offset in range(3):
            shown = INDEX_GROUPS[group][offset]
            bank_time = BANK_TIMES.get(base + offset, TIMES[offset])
            result[str(base + offset)] = [picture_key(shown), time_of(shown) == bank_time]
    return result


def screen(urf, name):
    """One DSi screen, upright (the game is held sideways: a 192 x 256 page stored as 256 x 192), RGB."""
    _, bitmap, _, palette = struct.unpack_from('<4I', urf.read(BACKGROUND, name))
    pixels, colours = urf.read(BITMAP, bitmap), urf.read(PALETTE, palette)
    width, height = struct.unpack_from('<HH', pixels)
    count = struct.unpack_from('<I', colours, 8)[0] // 2
    rgb = []
    for i in range(count):
        c = struct.unpack_from('<H', colours, 16 + 2 * i)[0]
        rgb += [(c & 31) * 255 // 31, (c >> 5 & 31) * 255 // 31, (c >> 10 & 31) * 255 // 31]
    image = Image.frombytes('P', (width, height), pixels[12:12 + width * height])
    image.putpalette(rgb + [0] * (768 - len(rgb)))
    return image.convert('RGB').crop((0, 0, 256, 192)).rotate(90, expand=True)


def png(image):
    out = io.BytesIO()
    image.save(out, 'PNG', optimize=True)
    return out.getvalue()


def build(rom):
    """The add-on's `.exp` bytes and a report, from a `nds.Rom`."""
    if rom.code not in GAME_CODES:
        raise SystemExit(f'Not Surviving High School for DSiWare (game code {rom.code}; expected {" or ".join(GAME_CODES)})')
    urf = Urf(rom.file('Rom_2D.urf'))
    resources, screens = {}, {}
    for place, left in enumerate(PICTURES):
        ids = SCREEN_BASE + 2 * place, SCREEN_BASE + 2 * place + 1
        for resource, name in zip(ids, (left, left.replace('Left', 'Right'))):
            if not urf.has(BACKGROUND, name):
                raise SystemExit(f'The image has no background {name}')
            resources[resource] = png(screen(urf, name))
        screens[picture_key(left)] = list(ids)
    spec = dict(revision=ADDON_REVISION, screens=screens, bank=bank_map(), stories=list(STORIES))
    resources[SPEC] = json.dumps(spec, separators=(',', ':')).encode('utf-8')
    resources[ADDON_RECORD] = provides_bytes(ADDON_ID, ADDON_TITLE, ADDON_REVISION)
    resources[1] = Metadata(PACK_ID, 0, (ADDON_TITLE + ' (addon)',) * 5).to_bytes()
    report = dict(pictures=len(screens), bank=len(spec['bank']),
                  exact=sum(1 for _, exact in spec['bank'].values() if exact))
    return encode_exp(resources), report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--nds', required=True, help="the DSiWare game's image (.nds, or the CDN content file)")
    parser.add_argument('--out', required=True, help='folder to write the add-on into')
    args = parser.parse_args(argv)
    data, report = build(Rom(Path(args.nds).read_bytes()))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / 'DSi_Addon_SHS_DSiWare.exp'
    path.write_bytes(data)
    print(json.dumps(dict(report, file=str(path), size=len(data))))


if __name__ == '__main__':
    main()
