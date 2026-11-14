"""The `shshw` addon, "Surviving Hollywood": the Surviving Hollywood demo's own art, built from the player's copy of its jar.

    python tools/translate/shw.py --demo-jar SURVIVING_HOLLYWOOD_DEMO_JAR --out DIR

Phase 1 of the owner's plan (reference/Other Games/docs/SURVIVING_HOLLYWOOD_ADDON_PLAN.md, 2026-11-13): an optional addon whose
portraits and backgrounds the BREW Classic *Surviving Hollywood Preview* (31100, 73; brew.py) draws instead of SHS's paper dolls
and school locations while the "Hollywood Art" switch is on. The Preview names them in its presentation record (`optional_art`,
built here by `preview_art`), and no episode requires the addon yet. Later phases (the demo's chapters) will require it, at later
revisions: every resource keeps its ID once shipped.

The art comes from the 240 x 320 build (the Nokia 5610's 1.0.2, `560_ver1.0_b2_hs92_english.jar`), the largest of the six:
- **Portraits** (2001-2052): painted busts, 64 x 64 or narrower, one face per character. Each is drawn at 3.5 times its pixels,
  as brew.py's paper dolls are (7 times with no smoothing, then halved; owner, 2026-11-13: 4 times filled the ring too much),
  standing PORTRAIT_LIFT art pixels above the foot of a 256 x 300 picture (twice the player's portrait mask), so the ring hides
  none of it. PORTRAIT_BASE + (id - 2000), and the same turned the other way at FLIPPED_BASE + (id - 2000): the player mirrors a
  right-hand portrait, so a face the demo drew turned to its left would look away from the middle there (case by case, owner).
- **The frame** (FRAME): the demo's dialogue panel around the strip, in the shape of brew.py's frame backdrop: its orange panel
  (sprites 4 and 5 of resource 16, shw_sprites.py) away from the strip and its copper rim (sprites 20 and 22 over 9 and 11) along
  each edge, at 6 times. The demo's panel never turns pink, so the Preview shows it behind both box colours.
- **Music** (3001-3014): the demo's 14 MIDI cues, rendered through Java's built-in synthesizer as brew.py's are (midi_render),
  at MUSIC_BASE + (id - 3000).
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

# 2: portraits at 3.5 times, their turned copies, the frame and the music (owner, 2026-11-13)
# 3: the catch game's skin (its board, score, bar, star and icons) and the status bar's moon as a time badge icon (owner, 2026-11-13)
ADDON_ID, ADDON_TITLE, ADDON_REVISION = 'shshw', 'Surviving Hollywood', 3
PACK_ID = 31700                         # its metadata's pack: the demo's chapters, when a later phase brings them
SPEC = 26998                            # what the addon holds, JSON
SPEC_FORMAT, SPEC_VERSION = 'shshw', 1
PORTRAIT_BASE, FLIPPED_BASE = 27000, 27100      # + the demo's portrait ID - 2000
PORTRAITS = range(2001, 2053)
PORTRAIT_CANVAS, PORTRAIT_LIFT = (256, 300), 7
FRAME = 26990
FRAME_SIZE, STRIP_TOP, STRIP_BOTTOM, FRAME_SCALE = (1152, 1536), 334, 814, 6    # as brew.frame_backdrop's: the strip's band
MUSIC_BASE = 26900                      # + the demo's cue ID - 3000
MUSIC = range(3001, 3015)
# The catch game (i.b / i.e, layout 44; Tardy-Slip web/shw/screens.js Catch), at CATCH_SCALE as brew.py's catch art: the board (layouts
# 4 and 44 drawn as the demo does, its field filled with i.java's 0x9198FE from y 39 down), "Score: " and the digits in its main font
# (8), its two closing lines (strings 47 and 48), the star the player steers (sprite 59, the code's drawable 75) and its 45 icons
# (2501-2545) as catch pictures. Where the score and bar go is layout 44's (children 29 and 25), kept in the spec.
CATCH_SCALE = 3
CATCH_BOARD, CATCH_PREFIX, CATCH_DIGITS, CATCH_CAPTIONS, CATCH_STAR = 26600, 26601, 26610, 26620, 26630
CATCH_ICON_BASE = 26700                 # + the icon's ID - 2500
CATCH_FIELD_COLOUR, CATCH_FIELD_TOP = (0x91, 0x98, 0xFE), 39
CATCH_STAR_SPRITE, CATCH_LABEL_RECT, CATCH_BAR_RECT, CATCH_LAYOUTS = 59, 29, 25, (4, 44)
CATCH_LABEL, CATCH_CLOSING = 44, (47, 48)    # UI strings: "Score"; "Time is up!" (out of items), "Max Points!"
ICONS = range(2501, 2546)
# The status bar's night icon (sprite 43; its day one is 67), as a time badge's icon: brew.event_icons' size and treatment.
MOON, MOON_SPRITE = 26631, 43
BACKGROUND_BASE, SKY_MODES = 26000, 3   # + SKY_MODES x (the demo's background ID - 1500) + BREW's sky mode
BACKGROUNDS = range(1504, 1537)
BACKGROUND_SCALE = 6
SKY_STRIPS = {0: 1501, 1: 1503, 2: 1502}    # BREW's sky modes (brew_art.SKIES: day, night, sunset) -> the demo's strips
MAGENTA = (255, 0, 255)

# -- the Preview (owner's picks, 2026-11-13: reference/screenshots/verify/surviving_hollywood/addon_phase1/) -------------------
PREVIEW_FILE = 'clsc_073_Hollywood.exp'     # brew.build_classic's name for it
PREVIEW_VERSION = 4                     # 1 had no Hollywood art; 3 added the frame and music, portraits turned case by case; 4 the
                                        # catch game's skin and the moon
# Each speaker's look, by a hash of the look's list (brew.py's spec key: its 23 entries, comma-joined), to the demo's portrait and
# whether it's turned: every one but the player speaks on the right, where the player mirrors it, so a face drawn turned to its
# left would look away from the middle (owner, 2026-11-13, case by case). Every speaker in the Preview has one look. Event (the
# narrator) has no picture.
PREVIEW_FACES = {
    '3fb0f4669b3c': (2015, False),  # You (Kate): New Game's photo 1; on the left, as drawn
    'b63268b6a528': (2049, False),  # Tony: faces front
    '9ec86a720706': (2006, True),   # Chelsea
    '0194a386edcc': (2048, True),   # The Jeff
    'f317d0377f98': (2043, False),  # Sergei: as drawn (owner, 2026-11-13: turned, he looked away)
    '07da36ebe57c': (2034, True),   # Milan
    '01dae5f47cc8': (2047, False),  # Tad Small: already turned toward the middle
    'dc6071a8749e': (2016, False),  # Director: as drawn (owner, 2026-11-13: turned, he looked away)
    '32201fc04e25': (2003, False),  # Bouncer (Bobo, the shot-putter in both games): faces front
    'a5a23103ed3a': (2003, False),  # Club Bouncer (the VIP door): Bobo too
    'b104a25a2068': (2025, True),   # Donny Stepp (a face no demo character uses)
    '25c6bd5df2e1': (2038, False),  # Mrs. Stepp (likewise): faces front
    '855a233a0f23': (2046, False),  # Guard, the jail ending (likewise): faces front
}
# The Preview's music by role (shw: the plan's table, owner to judge by ear, 2026-11-13): (the pcs of its 9s in 26000, the BREW
# track there, the demo's cue). Each role plays under a number of its own (PREVIEW_MUSIC_BASE + n), an alias of the BREW cue, which
# the map draws as the demo's: so the welcome, the club and the chase, all BREW's `action`, can each have their own.
PREVIEW_MUSIC = (
    ((2690,), 8000, 3007),                  # the welcome: the main menu's tune
    ((440,), 8007, 3013),                   # the red-carpet dream: success
    ((656, 1307), 8013, 3012),              # the audition, "Sorry. VIPs only.": stressed
    ((786,), 8007, 3003),                   # Excess Hollywood on TV: comic
    ((1079, 1179, 1453), 8000, 3002),       # the club: The Jeff, Sergei, Chelsea: club
    ((1124, 1206, 1667), 8008, 3006),       # BREW's ominous sting (a sound): the fail tone
    ((1246, 1808), 8010, 3011),             # Sergei's "transience", the drive to the Sign: sentimental
    ((1937, 2007, 2477), 8000, 3004),       # the Sign climb, the chase, Donny's "Lonnie" talk: exciting
    ((2572, 2637), 8005, 3005),             # the mega-ouch and jail endings: failure
)
PREVIEW_MUSIC_BASE = 30010              # free in the BREW addon, under 32768
# The catch game ("Be cool!", BREW's angled kind; owner, 2026-11-13): BREW's board becomes the demo's, and its pictures the demo's
# by BREW picture number: the player's face (151) the star the demo's player steers, the smile (152) 2522, the laughing face (128)
# 2525, the lightning (130) 2534's "pow".
PREVIEW_CATCH = {'151': 'star', '152': '2522', '128': '2525', '130': '2534'}
# The time badge (`7:30 PM - Pheno what?`): BREW's moon (event icon 139) becomes the demo's status bar moon.
PREVIEW_BADGE_ICONS = {139: 'moon'}
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
    """A demo portrait at 3.5 times (7 with no smoothing, then halved, so every art pixel is the same size) on the PORTRAIT_CANVAS,
    centred, its foot PORTRAIT_LIFT art pixels above the bottom."""
    face = face.convert('RGBA')
    big = face.resize((face.width * 7, face.height * 7), Image.NEAREST)
    big = big.resize((big.width // 2, big.height // 2), Image.BOX)
    canvas = Image.new('RGBA', PORTRAIT_CANVAS, (0, 0, 0, 0))
    bottom = PORTRAIT_CANVAS[1] - PORTRAIT_LIFT * 7 // 2
    canvas.paste(big, ((PORTRAIT_CANVAS[0] - big.width) // 2, bottom - big.height))
    return canvas


def frame(sprites):
    """The frame backdrop (FRAME): the demo's panel (sprites 4 | 5: 240 x 133) with its copper rim (20 | 22 over 9 | 11: 240 x 14)
    along each edge of the strip's band, the middle 192 art pixels across, at FRAME_SCALE; the upper half is the lower turned over,
    as the demo's own title bar has the rim's mirror image. The band itself stays black (the strip covers it)."""
    def pair(left, right):
        a, b = sprites[left], sprites[right]
        out = Image.new('RGBA', (a.width + b.width, max(a.height, b.height)), (0, 0, 0, 255))
        out.alpha_composite(a, (0, 0))
        out.alpha_composite(b, (a.width, 0))
        return out
    panel = pair(4, 5)
    rim = Image.new('RGBA', (panel.width, 14), (0, 0, 0, 255))
    rim.alpha_composite(pair(20, 22), (0, 0))
    rim.alpha_composite(pair(9, 11), (0, 7))
    art_width = FRAME_SIZE[0] // FRAME_SCALE

    def crop(image):
        return image.crop(((image.width - art_width) // 2, 0, (image.width + art_width) // 2, image.height))
    below = Image.new('RGBA', (art_width, rim.height + panel.height), (0, 0, 0, 255))
    below.alpha_composite(crop(rim), (0, 0))
    below.alpha_composite(crop(panel), (0, rim.height))
    below = below.convert('RGB').resize((below.width * FRAME_SCALE, below.height * FRAME_SCALE), Image.NEAREST)
    bottom_colour = sprites[4].getpixel((sprites[4].width // 2, sprites[4].height - 1))[:3]
    out = Image.new('RGB', FRAME_SIZE, bottom_colour)
    out.paste(Image.new('RGB', (FRAME_SIZE[0], STRIP_BOTTOM - STRIP_TOP), (0, 0, 0)), (0, STRIP_TOP))
    out.paste(below, (0, STRIP_BOTTOM))
    above = below.transpose(Image.FLIP_TOP_BOTTOM)
    out.paste(above.crop((0, max(0, above.height - STRIP_TOP), above.width, above.height)), (0, max(0, STRIP_TOP - above.height)))
    return out.quantize(255)


def scaled(image, k=CATCH_SCALE):
    return image.resize((image.width * k, image.height * k), Image.NEAREST)


def catch_art(found, sprites, comps):
    """{resource: PNG} and the spec's `catch` member: the catch game's skin (CATCH_*)."""
    import shw_ui
    slots = {0: picture(found[1001]).convert('RGBA'), 1: picture(found[1002]).convert('RGBA')}
    layouts = shw_ui.Layouts(found[15], sprites, comps, slots)
    board = Image.new('RGBA', (shw_ui.W, shw_ui.H), (0, 0, 0, 255))
    for layout in CATCH_LAYOUTS:
        layouts.paint(board, layout)
    board.paste(CATCH_FIELD_COLOUR + (255,), (0, CATCH_FIELD_TOP, shw_ui.W, shw_ui.H))
    font, words = shw_ui.Font(found[8]), shw_ui.strings(found[14])
    prefix = words[CATCH_LABEL] + ': '
    resources = {CATCH_BOARD: png(scaled(board.convert('RGB')).quantize(255)),
                 CATCH_PREFIX: png(scaled(font.image(prefix))),
                 CATCH_STAR: png(scaled(sprites[CATCH_STAR_SPRITE]))}
    for d in range(10):
        resources[CATCH_DIGITS + d] = png(scaled(font.image(str(d))))
    for n, string in enumerate(CATCH_CLOSING):
        resources[CATCH_CAPTIONS + n] = png(scaled(font.image(words[string])))
    pictures = {'star': [CATCH_STAR, *sprites[CATCH_STAR_SPRITE].size]}
    for number in ICONS:
        icon = picture(found.get(number, b''))
        if icon is not None:
            resources[CATCH_ICON_BASE + number - 2500] = png(scaled(icon.convert('RGBA')))
            pictures[str(number)] = [CATCH_ICON_BASE + number - 2500, *icon.size]
    spec = dict(board=CATCH_BOARD, field_top=CATCH_FIELD_TOP, label=list(layouts.rect(44, CATCH_LABEL_RECT)),
                bar=list(layouts.rect(44, CATCH_BAR_RECT)), prefix=CATCH_PREFIX, prefix_width=font.width(prefix) + font.tracking,
                digits=[CATCH_DIGITS + d for d in range(10)], digit_widths=[font.width(str(d)) for d in range(10)],
                tracking=font.tracking, height=font.height, captions=[CATCH_CAPTIONS, CATCH_CAPTIONS + 1], pictures=pictures)
    return resources, spec


def moon_icon(sprites):
    """The status bar's moon as a time badge icon, as brew.event_icons makes BREW's: 8 times with no smoothing, then fitted to
    brew.EVENT_ICON_SIZE."""
    import brew
    image = sprites[MOON_SPRITE]
    big = image.resize((image.width * 8, image.height * 8), Image.NEAREST)
    k = brew.EVENT_ICON_SIZE / max(big.size)
    return big.resize((max(1, round(big.width * k)), max(1, round(big.height * k))), Image.LANCZOS)


def render_music(data):
    """MP3 bytes for a MIDI cue, through Java's synthesizer (midi_render.render_java; needs java and ffmpeg on PATH)."""
    import midi_render
    return midi_render.mp3(midi_render.render_java(data))


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


def build_addon(jar, music=True):
    """(addon bytes, spec) from the demo's jar. `music` False leaves the cues out (no java to render them)."""
    import shw_sprites
    found = jar_resources(jar)
    resources, spec = {}, dict(format=SPEC_FORMAT, version=SPEC_VERSION, portraits={}, flipped={}, backgrounds={}, music={})
    for number in PORTRAITS:
        face = picture(found.get(number, b''))
        if face is None:
            continue
        drawn = portrait(face)
        resources[PORTRAIT_BASE + number - 2000] = png(drawn)
        resources[FLIPPED_BASE + number - 2000] = png(drawn.transpose(Image.FLIP_LEFT_RIGHT))
        spec['portraits'][str(number)] = PORTRAIT_BASE + number - 2000
        spec['flipped'][str(number)] = FLIPPED_BASE + number - 2000
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
    sprites, _, comps = shw_sprites.parse(found[16])
    resources[FRAME] = png(frame(sprites))
    spec['frame'] = FRAME
    catch_resources, spec['catch'] = catch_art(found, sprites, comps)
    resources.update(catch_resources)
    resources[MOON] = png(moon_icon(sprites))
    spec['moon'] = MOON
    for number in MUSIC if music else ():
        resources[MUSIC_BASE + number - 3000] = render_music(found[number])
        spec['music'][str(number)] = MUSIC_BASE + number - 3000
    resources[SPEC] = json.dumps(spec, separators=(',', ':')).encode()
    resources[ADDON_RECORD] = provides_bytes(ADDON_ID, ADDON_TITLE, ADDON_REVISION)
    resources[1] = Metadata(PACK_ID, 0, (ADDON_TITLE + ' (addon)',) * 5).to_bytes()
    return encode_exp(resources), spec


def look_key_hash(key):
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def preview_art(brew_spec, shw_spec=None):
    """The Preview's presentation members: `aliases` for the dream's own location (the BREW addon's dance floor), and
    `optional_art` {shshw: {BREW addon picture: shshw picture}} for every portrait and background PREVIEW_FACES and
    PREVIEW_SCENES name, the frame, and the music roles (PREVIEW_MUSIC, each an alias of the BREW cue it stands in for). `shw_spec` is this addon's spec, else the fixed layout build_addon writes (every background at every
    sky)."""
    import brew
    looks = brew_spec['stories'].get(PREVIEW_FILE)
    if looks is None:
        raise brew.StoryError(f'the BREW addon has no looks for {PREVIEW_FILE}')
    own = brew_spec.get('backgrounds', {}).get(PREVIEW_FILE, {})
    if shw_spec is None:
        shw_spec = dict(portraits={str(n): PORTRAIT_BASE + n - 2000 for n in PORTRAITS},
                        flipped={str(n): FLIPPED_BASE + n - 2000 for n in PORTRAITS},
                        backgrounds={str(n): [BACKGROUND_BASE + SKY_MODES * (n - 1500) + m for m in range(SKY_MODES)]
                                     for n in BACKGROUNDS},
                        music={str(n): MUSIC_BASE + n - 3000 for n in MUSIC}, frame=FRAME, moon=MOON,
                        catch=dict(board=CATCH_BOARD, pictures={'star': [CATCH_STAR], **{str(n): [CATCH_ICON_BASE + n - 2500]
                                                                                          for n in ICONS}}))
    art = {}
    for key, bank in looks.items():
        face = PREVIEW_FACES.get(look_key_hash(key))
        if bank < 0:
            continue
        if face is None:
            raise brew.StoryError(f'{PREVIEW_FILE}: a look with no Hollywood face ({look_key_hash(key)})')
        number, turned = face
        for offset in range(brew.EXPRESSIONS):
            art[bank + offset] = shw_spec['flipped' if turned else 'portraits'][str(number)]

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
    # The frame, behind both box colours; the music by role (PREVIEW_MUSIC)
    art[brew.FRAME_BACKDROP] = art[brew.PINK_BACKDROP] = shw_spec['frame']
    # The time badge's icon, and the catch game's board and pictures (desktop_brew_catch draws the skin where the board is mapped)
    for icon, name in PREVIEW_BADGE_ICONS.items():
        art[brew.EVENT_ICON_BASE + icon] = shw_spec[name]
    catch = brew_spec.get('catch')
    if catch is None:
        raise brew.StoryError('the BREW addon has no catch game art')
    art[catch['frame']] = shw_spec['catch']['board']
    for number, ours in PREVIEW_CATCH.items():
        art[catch['pictures'][number][0]] = shw_spec['catch']['pictures'][ours][0]
    for n, (_, track, cue) in enumerate(PREVIEW_MUSIC):
        aliases[str(PREVIEW_MUSIC_BASE + n)] = [brew.ADDON_ID, brew.MUSIC_BASE + track - 8000]
        art[PREVIEW_MUSIC_BASE + n] = shw_spec['music'][str(cue)]
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
