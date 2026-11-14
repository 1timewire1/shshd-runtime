"""The `shshw` addon, "Surviving Hollywood": the Surviving Hollywood demo's own art, built from the player's copy of its jar.

    python tools/translate/shw.py --demo-jar SURVIVING_HOLLYWOOD_DEMO_JAR --out DIR

Phase 1 of the owner's plan (reference/Other Games/docs/SURVIVING_HOLLYWOOD_ADDON_PLAN.md, 2026-11-13): an optional addon whose
portraits and backgrounds the BREW Classic *Surviving Hollywood Preview* (31100, 73; brew.py) draws instead of SHS's paper dolls
and school locations while the "Hollywood Art" switch is on. The Preview names them in its presentation record (`optional_art`,
built here by `preview_art`), and no episode requires the addon yet. Later phases (the demo's chapters) will require it, at later
revisions: every resource keeps its ID once shipped.

The art comes from the 240 x 320 build (the Nokia 5610's 1.0.2, `560_ver1.0_b2_hs92_english.jar`), the largest of the six:
- **Portraits** (2001-2052): painted busts, 64 x 64 or narrower, one face per character. Each is drawn at 4 times its pixels with
  no smoothing, standing PORTRAIT_LIFT art pixels above the foot of a 256 x 300 picture (twice the player's portrait mask), as
  brew.py's paper dolls do, so the ring hides none of it. PORTRAIT_BASE + (id - 2000).
- **Backgrounds** (1504-1536, 28 pictures): 240 x 80 strips whose magenta is a window onto one of three 386 x 66 sky strips (day
  1501, sunset 1502, night 1503), centred as the demo's dialogue screen draws it (Tardy-Slip `web/shw/screens.js`). Each is drawn
  at each of BREW's sky modes (0 day, 1 night, 2 sunset) at 6 times with no smoothing, as brew.py's locations are:
  BACKGROUND_BASE + SKY_MODES x (id - 1500) + mode. A strip with no window is the same picture under all three, so an episode
  can name any background at any sky without reading the addon.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import zipfile

from PIL import Image

from exp_runtime.addons import RESOURCE as ADDON_RECORD, provides_bytes
from exp_runtime.exp import Metadata, encode_exp

sys.path.insert(0, str(Path(__file__).resolve().parent))

ADDON_ID, ADDON_TITLE, ADDON_REVISION = 'shshw', 'Surviving Hollywood', 1
PACK_ID = 31700                         # its metadata's pack: the demo's chapters, when a later phase brings them
SPEC = 26998                            # what the addon holds, JSON
SPEC_FORMAT, SPEC_VERSION = 'shshw', 1
PORTRAIT_BASE = 27000                   # + the demo's portrait ID - 2000
PORTRAITS = range(2001, 2053)
PORTRAIT_SCALE, PORTRAIT_CANVAS, PORTRAIT_LIFT = 4, (256, 300), 7
BACKGROUND_BASE, SKY_MODES = 26000, 3   # + SKY_MODES x (the demo's background ID - 1500) + BREW's sky mode
BACKGROUNDS = range(1504, 1537)
BACKGROUND_SCALE = 6
SKY_STRIPS = {0: 1501, 1: 1503, 2: 1502}    # BREW's sky modes (brew_art.SKIES: day, night, sunset) -> the demo's strips
MAGENTA = (255, 0, 255)

# -- the Preview (owner's picks, 2026-11-13: reference/screenshots/verify/surviving_hollywood/addon_phase1/) -------------------
PREVIEW_FILE = 'clsc_073_Hollywood.exp'     # brew.build_classic's name for it
PREVIEW_VERSION = 2                     # 1 had no Hollywood art
# Each speaker's look, by a hash of the look's list (brew.py's spec key: its 23 entries, comma-joined), to the demo's portrait.
# Every speaker in the Preview has one look. Event (the narrator) has no picture.
PREVIEW_FACES = {
    '3fb0f4669b3c': 2015,   # You (Kate): New Game's photo 1
    'b63268b6a528': 2049,   # Tony
    '9ec86a720706': 2006,   # Chelsea
    '0194a386edcc': 2048,   # The Jeff
    'f317d0377f98': 2043,   # Sergei
    '07da36ebe57c': 2034,   # Milan
    '01dae5f47cc8': 2047,   # Tad Small
    'dc6071a8749e': 2016,   # Director
    '32201fc04e25': 2003,   # Bouncer (Bobo, the shot-putter in both games)
    'a5a23103ed3a': 2003,   # Club Bouncer (the VIP door): Bobo too
    'b104a25a2068': 2025,   # Donny Stepp (a face no demo character uses)
    '25c6bd5df2e1': 2038,   # Mrs. Stepp (likewise)
    '855a233a0f23': 2046,   # Guard, the jail ending (likewise)
}
# The Preview's scenes by the location its scripts name (13, 14) to the demo's background. '07's shared locations (1000-1027) and
# the story's own pictures (26518-26520), each at whatever sky the scene has.
PREVIEW_SCENES = {
    1007: 1505,             # home: Tony calls from the living room
    1014: 1519,             # outside Club Franken-stein: the line, the bouncer
    1023: 1518,             # inside the club (the dream's two scenes are DREAM_LOCATION below)
    1018: 1521,             # the VIP room
    1017: 1516,             # the car
    1027: 1523,             # the jail ending: the city at night
    26518: 1536,            # the audition: the nice studio
    26519: 1523,            # the Hollywood Sign: the city at night
    26520: 1530,            # Miguel Bayo's party
}
# The welcome and the red-carpet dream show '07's dance floor (1023) as the club does, so their two scene changes (14) name a
# location of their own, which the BREW addon draws as 1023 (presentation `aliases`) and this one as the red carpet.
DREAM_SITES = (438, 2688)               # the Preview's 26000: the pcs of those 14s (checked in brew.fix_hollywood_preview)
# Its pictures are BREW's BACKGROUND_BASE + 3 x DREAM_INDEX + sky: 30002-30004, free in the BREW addon and under 32768, as a KiWi
# number must be (a negative picture keeps the one showing).
DREAM_LOCATION, DREAM_INDEX = 9023, 1334
DREAM_SHOWN_AS, DREAM_PICTURE = 1023, 1534


def jar_resources(path):
    """The jar's numbered resources, CMB0 bundles opened: {id: bytes}. A bundle is "CMB0", u8 n, n x u16 member IDs, n x u32
    absolute offsets; a member runs to the next offset, the last to the end (SURVIVING_HOLLYWOOD_ENGINE.md section 4)."""
    out = {}
    with zipfile.ZipFile(path) as jar:
        for name in jar.namelist():
            if not name.isdigit():
                continue
            data = jar.read(name)
            if data[:4] != b'CMB0':
                out.setdefault(int(name), data)
                continue
            count = data[4]
            ids = struct.unpack_from('>' + 'H' * count, data, 5)
            offsets = list(struct.unpack_from('>' + 'I' * count, data, 5 + 2 * count)) + [len(data)]
            for k in range(count):
                out[ids[k]] = data[offsets[k]:offsets[k + 1]]
    return out


def png(image):
    buffer = io.BytesIO()
    image.save(buffer, 'PNG', optimize=True)
    return buffer.getvalue()


def picture(data):
    try:
        return Image.open(io.BytesIO(data))
    except Exception:
        return None


def portrait(face):
    """A demo portrait at PORTRAIT_SCALE on the PORTRAIT_CANVAS, centred, its foot PORTRAIT_LIFT art pixels above the bottom."""
    face = face.convert('RGBA')
    big = face.resize((face.width * PORTRAIT_SCALE, face.height * PORTRAIT_SCALE), Image.NEAREST)
    canvas = Image.new('RGBA', PORTRAIT_CANVAS, (0, 0, 0, 0))
    bottom = PORTRAIT_CANVAS[1] - PORTRAIT_LIFT * PORTRAIT_SCALE
    canvas.paste(big, ((PORTRAIT_CANVAS[0] - big.width) // 2, bottom - big.height))
    return canvas


def has_window(strip):
    return MAGENTA in {colour for _, colour in strip.convert('RGB').getcolors(1 << 16) or ()}


def over_sky(strip, sky):
    """A background over a sky strip, centred on it as the demo draws a scene ((W - sky.w) >> 1), opaque."""
    strip, sky = strip.convert('RGB'), sky.convert('RGB')
    scene = Image.new('RGB', strip.size, sky.getpixel((sky.width // 2, sky.height - 1)))
    scene.paste(sky, ((strip.width - sky.width) // 2, 0))
    keep = Image.new('L', strip.size, 255)
    keep.putdata([0 if pixel == MAGENTA else 255 for pixel in strip.getdata()])
    scene.paste(strip, (0, 0), keep)
    return scene


def strip_png(scene):
    return png(scene.resize((scene.width * BACKGROUND_SCALE, scene.height * BACKGROUND_SCALE), Image.NEAREST).quantize(255))


def build_addon(jar):
    """(addon bytes, spec) from the demo's jar."""
    found = jar_resources(jar)
    resources, spec = {}, dict(format=SPEC_FORMAT, version=SPEC_VERSION, portraits={}, backgrounds={})
    for number in PORTRAITS:
        face = picture(found.get(number, b''))
        if face is None:
            continue
        resources[PORTRAIT_BASE + number - 2000] = png(portrait(face))
        spec['portraits'][str(number)] = PORTRAIT_BASE + number - 2000
    skies = {mode: picture(found[number]) for mode, number in SKY_STRIPS.items()}
    for number in BACKGROUNDS:
        strip = picture(found.get(number, b''))
        if strip is None or strip.width < 8:
            continue
        base = BACKGROUND_BASE + SKY_MODES * (number - 1500)
        windowless = None if has_window(strip) else strip_png(strip.convert('RGB'))
        for mode in range(SKY_MODES):
            resources[base + mode] = windowless or strip_png(over_sky(strip, skies[mode]))
        spec['backgrounds'][str(number)] = [base + mode for mode in range(SKY_MODES)]
    if len(spec['portraits']) < 50 or len(spec['backgrounds']) < 28:
        raise ValueError(f'{jar}: not the 240 x 320 demo ({len(spec["portraits"])} portraits, {len(spec["backgrounds"])} backgrounds)')
    resources[SPEC] = json.dumps(spec, separators=(',', ':')).encode()
    resources[ADDON_RECORD] = provides_bytes(ADDON_ID, ADDON_TITLE, ADDON_REVISION)
    resources[1] = Metadata(PACK_ID, 0, (ADDON_TITLE + ' (addon)',) * 5).to_bytes()
    return encode_exp(resources), spec


def look_key_hash(key):
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def preview_art(brew_spec, shw_spec=None):
    """The Preview's presentation members: `aliases` for the dream's own location (the BREW addon's dance floor), and
    `optional_art` {shshw: {BREW addon picture: shshw picture}} for every portrait and background PREVIEW_FACES and
    PREVIEW_SCENES name. `shw_spec` is this addon's spec, else the fixed layout build_addon writes (every background at every
    sky)."""
    import brew
    looks = brew_spec['stories'].get(PREVIEW_FILE)
    if looks is None:
        raise brew.StoryError(f'the BREW addon has no looks for {PREVIEW_FILE}')
    own = brew_spec.get('backgrounds', {}).get(PREVIEW_FILE, {})
    if shw_spec is None:
        shw_spec = dict(portraits={str(n): PORTRAIT_BASE + n - 2000 for n in PORTRAITS},
                        backgrounds={str(n): [BACKGROUND_BASE + SKY_MODES * (n - 1500) + m for m in range(SKY_MODES)]
                                     for n in BACKGROUNDS})
    art = {}
    for key, bank in looks.items():
        face = PREVIEW_FACES.get(look_key_hash(key))
        if bank < 0:
            continue
        if face is None:
            raise brew.StoryError(f'{PREVIEW_FILE}: a look with no Hollywood face ({look_key_hash(key)})')
        for offset in range(brew.EXPRESSIONS):
            art[bank + offset] = shw_spec['portraits'][str(face)]

    def scene(first, demo):
        for mode in range(SKY_MODES):
            art[first + mode] = shw_spec['backgrounds'][str(demo)][mode]
    for location, demo in PREVIEW_SCENES.items():
        if 1000 <= location < 1000 + brew.LOCATIONS_08:
            scene(brew.BACKGROUND_BASE + SKY_MODES * (brew.LOCATION_07_OFFSET + location - 1000), demo)
        elif str(location) in own:
            scene(brew.OWN_BACKGROUND_BASE + SKY_MODES * own[str(location)], demo)
        else:
            raise brew.StoryError(f'{PREVIEW_FILE}: the BREW addon has no picture for its location {location}')
    dream = brew.BACKGROUND_BASE + SKY_MODES * DREAM_INDEX
    shown = brew.BACKGROUND_BASE + SKY_MODES * (brew.LOCATION_07_OFFSET + DREAM_SHOWN_AS - 1000)
    scene(dream, DREAM_PICTURE)
    aliases = {str(dream + mode): [brew.ADDON_ID, shown + mode] for mode in range(SKY_MODES)}
    return dict(aliases=aliases, optional_art={ADDON_ID: {str(k): v for k, v in sorted(art.items())}})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--demo-jar', required=True, help="the 240 x 320 demo's jar (1.0.2)")
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    data, spec = build_addon(args.demo_jar)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f'{ADDON_ID}.exp').write_bytes(data)
    print(f'{ADDON_ID}.exp: revision {ADDON_REVISION}, {len(spec["portraits"])} portraits, {len(spec["backgrounds"])} backgrounds, '
          f'{len(data) // 1024} KB')


if __name__ == '__main__':
    main()
