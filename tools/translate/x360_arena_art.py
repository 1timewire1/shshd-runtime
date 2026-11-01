"""The X360 look for New Rules' minigame arena, for the X360 addon (reference/Other Games/docs/NR_ARENA_X360_SKIN.md):
the cancelled prototype's own 2D minigame art, fonts, effect sounds and Diss Practice music, cut from its data.pak, and
New Rules' item pictures with an ink outline and a drop shadow, so they sit with it (owner, 2026-10-31).

The skin is data only: a JSON spec (SPEC) naming every picture, font, sound and the music by resource ID, all within
SKIN_IDS. The player reads it straight from the imported addon (ContentLibrary.addon), so New Rules' episodes need no
rebuild. The turntable deck, the location backdrops and the score digits (3D models in the prototype) are rendered
separately and aren't part of this first set.
"""
import io
import json
import shutil
import subprocess

from PIL import Image, ImageChops, ImageFilter, ImageOps

FORMAT, VERSION = 'shshd-arena-skin-x360', 1
SPEC = 26300
SKIN_IDS = range(26300, 26420)
PICTURE_BASE = 26301                    # PICTURES then New Rules' outlined items, in order
FONT_PAGE_BASE = 26360
SOUND_BASE = 26380
MUSIC = 26390
# Shot in Xenia (reference tools x360_dbpbooth.py / x360_dbpcut.py; Additional Resources/x360-dbp-booth): the deck, the
# record, every digit in every slot as one atlas, and Diss Practice's places, people taken out.
BOOTH_BASE = 26400
BOOTH_PIECES = ('deck', 'table', 'record')              # 26400-26402; the digit atlas 26403; the places from 26404
PLACES = ('school_front_diss_002', 'school_hallway_b_diss_001', 'josh_house_in_diss_001', 'school_front_diss_001',
          'school_hallway_b_diss_002')                  # each practice's own view first
DIGIT_SLOTS, DIGITS = 8, 10
HUD = 'data/art/hud/'
FX = 'data/art/fx/'
# (name, file, its alpha file or None, the 64-pixel cell to cut or None for the whole picture). A cut is trimmed to
# what shows.
PICTURES = (
    ('note', HUD + 'icons_2.png', None, (128, 0)),          # the red note: New Rules' good note (20)
    ('note_broken', HUD + 'icons_2.png', None, (64, 0)),    # broken notes: the bent note (18)
    ('remix', HUD + 'icons_2.png', None, (0, 0)),           # the remix arrows: the swap (28)
    ('beamed', HUD + 'icons.jpg', HUD + 'icons_a.jpg', (128, 64)),   # white beamed notes, for the double note (17)
    ('cross', HUD + 'icons.jpg', HUD + 'icons_a.jpg', (0, 0)),        # the X: the no-entry sign (21)
    ('stamp_pow', HUD + 'onomatopeias/pow.png', None, None),          # POW! (23)
    ('stamp_yeah', HUD + 'onomatopeias/yeah.png', None, None),        # "correct!"
    ('stamp_ooops', HUD + 'onomatopeias/ooops.png', None, None),      # "wrong!"
    ('power_bar', HUD + 'power_bar_bk.jpg', HUD + 'power_bar_bk_a.jpg', None),     # the meter's frame
    ('power_fill_green', HUD + 'green_bar_fl.jpg', HUD + 'power_bar_fl_a.jpg', None),
    ('power_fill_yellow', HUD + 'yellow_bar_fl.jpg', HUD + 'power_bar_fl_a.jpg', None),
    ('power_fill_blue', HUD + 'blue_bar_fl.jpg', HUD + 'power_bar_fl_a.jpg', None),
    ('bubble', HUD + 'dialog.png', None, None),             # speech bubbles (762/763)
    ('info_box', HUD + 'narrator_box.png', None, None),     # the info box (10)
    ('sticker', HUD + 'little_box.png', None, None),        # a text item's box
    ('tutorial_1', HUD + 'dbp_tutorial_001.png', None, None),         # Diss Practice's cards: good notes,
    ('tutorial_2', HUD + 'dbp_tutorial_002.png', None, None),         # broken notes,
    ('tutorial_3', HUD + 'dbp_tutorial_003.png', None, None),         # the remix arrows
    ('particles', FX + 'particles.jpg', None, None),        # additive: black is clear
    ('big_particles', FX + 'big_particles.jpg', None, None),
    ('flames', FX + 'flames.jpg', None, None),
    ('smoke', FX + 'smoke.jpg', None, None),
    ('deck_texture', 'data/art/minigame/soundhwheel.jpg', None, None),   # the turntable's texture
)
# Composed from the above (_derived), after them: the good-note tiers, and the hit effects' sprites (white, their
# brightness as alpha, so the player tints them as Diss Practice's emitters do).
SPARK_CELLS = ((64, 0), (0, 64))        # big_particles' two flares (64-pixel cells): eat_good_note
PUFF_CELLS = ((0, 0), (64, 0), (0, 64)) # smoke's three puffs: eat_bad_note
DERIVED = ('note_double', 'note_fire', *(f'fx_spark_{i}' for i in range(len(SPARK_CELLS))),
           *(f'fx_puff_{i}' for i in range(len(PUFF_CELLS))))
# Diss Practice's good-note tiers as New Rules' good-note pictures (NR_ARENA_X360_SKIN.md §3); the other X360
# counterparts. Every other item is New Rules' own, outlined.
ITEMS = {20: 'note', 17: 'note_double', 19: 'note_fire', 18: 'note_broken', 28: 'remix', 21: 'cross', 23: 'stamp_pow'}
NR_ITEMS, NR_ITEM_ICONS = 29, 8018      # New Rules' item pictures (nr_arena_art.ITEM_ICONS)
ITEM_SCALE, OUTLINE, SHADOW = 2, 3, (3, 4)              # New Rules' items: x2, a 3-pixel ink line, a shadow offset
INK, SHADOW_ALPHA = (24, 16, 16), 110
FONTS = (('casual', 'data/art/fonts/blambot_casual.fnt'), ('casual_white', 'data/art/fonts/blambot_casual_white.fnt'),
         ('badaboom', 'data/art/fonts/blambot_badaboom.fnt'),
         ('badaboom_white', 'data/art/fonts/blambot_badaboom_white.fnt'),
         ('turntablz', 'data/art/fonts/blambot_turntablz.fnt'))
# The effects Diss Practice's notes make (templates fx.wxr / sound.wxr): a good note one of three whooshes at random,
# a broken note the fail, a remix arrow the swap; the countdown is silent.
SOUNDS = (('whoosh_1', 'data/sound/fx/whoosh_001.wav'), ('whoosh_2', 'data/sound/fx/whoosh_002.wav'),
          ('whoosh_3', 'data/sound/fx/whoosh_003.wav'), ('fail', 'data/sound/fx/dbp_fail.wav'),
          ('swap', 'data/sound/fx/dbp_swap.wav'))
# What they replace while the skin is on (owner, 2026-10-31): New Rules' track (the addon's 26980 + track) -> the X360
# sounds, one picked at random. Time's up (#02) and the score's #05 stay New Rules'.
SOUND_TRACKS = {13: ('whoosh_1', 'whoosh_2', 'whoosh_3'), 1: ('fail',), 11: ('swap',)}
# The practice maps' music cue (music/dbp_bg_music_001, looping), in place of the games' track 14 (owner, 2026-10-31).
MUSIC_FILE, MUSIC_TRACK = 'data/sound/music/dbp_bg_music.ogg', 14


class SkinError(ValueError):
    pass


def _png(image):
    out = io.BytesIO()
    image.save(out, 'PNG', optimize=True)
    return out.getvalue()


def _picture(files, path, alpha, cell):
    """One prototype picture as RGBA: a JPEG takes its `_a` file's grey as alpha. A cell is trimmed to what shows."""
    image = Image.open(io.BytesIO(files[path])).convert('RGBA')
    if alpha is not None:
        image.putalpha(Image.open(io.BytesIO(files[alpha])).convert('L').resize(image.size))
    if cell is not None:
        x, y = cell
        image = image.crop((x, y, x + 64, y + 64))
        box = image.getchannel('A').point(lambda v: 255 if v > 16 else 0).getbbox()
        if box is not None:
            image = image.crop(box)
    return image


def _derived(pictures):
    """The good-note tiers the X360 shows as 3D notes, in its 2D style: the double note is the white beamed notes in the
    red note's colours (double notes come in pairs), the on-fire note the red note over the flames texture's glow."""
    note, beamed = pictures['note'], pictures['beamed']
    solid = [p[:3] for p in note.getdata() if p[3] > 200]
    colour = tuple(sum(p[i] for p in solid) // len(solid) for i in range(3))
    red = ImageChops.multiply(beamed, Image.new('RGBA', beamed.size, colour + (255,)))
    red.putalpha(beamed.getchannel('A'))
    # The flames texture is grey (the X360 tints its particles): coloured here from deep red through orange to yellow.
    grey = pictures['flames'].convert('L').resize((note.width * 3 // 2, note.height * 3 // 2), Image.LANCZOS)
    flames = ImageOps.colorize(grey, black=(120, 10, 0), white=(255, 236, 120), mid=(255, 120, 0))
    fire = Image.new('RGBA', flames.size, (0, 0, 0, 0))
    fire.paste(flames, (0, 0), grey.point(lambda v: min(255, v * 2)))
    fire.alpha_composite(note, ((fire.width - note.width) // 2, fire.height - note.height))
    out = {'note_double': red, 'note_fire': fire}
    for name, sheet, cells in (('fx_spark', 'big_particles', SPARK_CELLS), ('fx_puff', 'smoke', PUFF_CELLS)):
        for i, (x, y) in enumerate(cells):
            out[f'{name}_{i}'] = sprite(pictures[sheet].crop((x, y, x + 64, y + 64)))
    return out


def sprite(cell):
    """A particle texture's cell (light on black, which the X360 adds or blends by brightness) as a white sprite
    whose alpha is that brightness."""
    white = Image.new('RGBA', cell.size, (255, 255, 255, 0))
    white.putalpha(cell.convert('L'))
    return white


def outlined(image):
    """A New Rules item drawn for the X360 look (owner, 2026-10-31): smoothly enlarged ITEM_SCALE times, an ink line
    OUTLINE pixels round what shows, and a soft drop shadow."""
    image = image.convert('RGBA')
    image = image.resize((image.width * ITEM_SCALE, image.height * ITEM_SCALE), Image.LANCZOS)
    pad = OUTLINE + max(SHADOW) + 2
    canvas = Image.new('RGBA', (image.width + 2 * pad, image.height + 2 * pad), (0, 0, 0, 0))
    canvas.alpha_composite(image, (pad, pad))
    shape = canvas.getchannel('A').point(lambda v: 255 if v > 40 else 0)
    line = shape.filter(ImageFilter.MaxFilter(2 * OUTLINE + 1))
    shadow = line.filter(ImageFilter.GaussianBlur(2)).point(lambda v: v * SHADOW_ALPHA // 255)
    out = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
    out.paste(Image.new('RGBA', canvas.size, INK + (255,)), SHADOW, shadow)
    out.alpha_composite(Image.composite(Image.new('RGBA', canvas.size, INK + (255,)),
                                        Image.new('RGBA', canvas.size, (0, 0, 0, 0)), line))
    out.alpha_composite(canvas)
    return out.crop(out.getchannel('A').getbbox())


def read_font(text):
    """A BMFont text descriptor: (spec without pages, [page file names]). Each character is [x, y, width, height,
    x offset, y offset, x advance, page]."""
    spec, pages, chars, kerning = {}, {}, {}, {}
    for line in text.splitlines():
        tag, _, rest = line.partition(' ')
        fields = {}
        for key, _, value in (part.partition('=') for part in _fields(rest)):
            fields[key] = value.strip('"')
        if tag == 'common':
            spec.update(line_height=int(fields['lineHeight']), base=int(fields['base']))
        elif tag == 'page':
            pages[int(fields['id'])] = fields['file']
        elif tag == 'char':
            chars[int(fields['id'])] = [int(fields[k]) for k in ('x', 'y', 'width', 'height', 'xoffset', 'yoffset',
                                                                   'xadvance', 'page')]
        elif tag == 'kerning':
            kerning[f'{fields["first"]},{fields["second"]}'] = int(fields['amount'])
    if not chars or 'line_height' not in spec:
        raise SkinError('not a BMFont text descriptor')
    spec.update(chars={str(k): v for k, v in sorted(chars.items())}, kerning=kerning)
    return spec, [pages[i] for i in sorted(pages)]


def _fields(rest):
    """`key=value` fields, a quoted value kept whole."""
    out, current, quoted = [], '', False
    for ch in rest:
        if ch == '"':
            quoted = not quoted
        if ch == ' ' and not quoted:
            if current:
                out.append(current)
            current = ''
        else:
            current += ch
    if current:
        out.append(current)
    return out


def ogg_wav(data):
    """The music as a 16-bit PCM WAV (ffmpeg), which loops without a gap as Day of Diss's own music does."""
    ffmpeg = shutil.which('ffmpeg')
    if ffmpeg is None:
        raise SkinError('the skin\'s music needs ffmpeg on PATH')
    result = subprocess.run([ffmpeg, '-v', 'error', '-i', 'pipe:0', '-f', 'wav', '-acodec', 'pcm_s16le', 'pipe:1'],
                            input=data, capture_output=True, check=True)
    return result.stdout


def booth(folder):
    """{resource ID: bytes} and the spec's `booth` entry from a Diss Practice booth folder (booth.json, the deck pieces,
    digits/slot_<i>_<n>.png, places/<name>.png). Every piece keeps its box in the booth's camera frame, so the player
    can place them as the game's camera saw them; the digits are packed into one atlas, slot by slot."""
    from pathlib import Path
    folder = Path(folder)
    info = json.loads((folder / 'booth.json').read_text(encoding='utf-8'))
    resources, entry = {}, dict(frame=info['frame'], camera=info['camera'], pieces={}, places={})
    for i, name in enumerate(BOOTH_PIECES):
        resources[BOOTH_BASE + i] = (folder / f'{name}.png').read_bytes()
        entry['pieces'][name] = dict(id=BOOTH_BASE + i, box=info['boxes'][name])
    cells = [[Image.open(folder / 'digits' / f'slot_{i}_{n}.png').convert('RGBA') for n in range(DIGITS)]
             for i in range(DIGIT_SLOTS)]
    width = max(sum(c.width for c in row) for row in cells)
    atlas = Image.new('RGBA', (width, sum(max(c.height for c in row) for row in cells)), (0, 0, 0, 0))
    slots, y = [], 0
    for i, row in enumerate(cells):
        x, placed = 0, []
        for n, cell in enumerate(row):
            atlas.paste(cell, (x, y))
            placed.append(dict(rect=[x, y, cell.width, cell.height], box=info['boxes'][f'slot_{i}_{n}']))
            x += cell.width
        slots.append(placed)
        y += max(c.height for c in row)
    resources[BOOTH_BASE + len(BOOTH_PIECES)] = _png(atlas)
    entry['digits'] = dict(atlas=BOOTH_BASE + len(BOOTH_PIECES), slots=slots, score=list(range(6)), time=[6, 7])
    for k, name in enumerate(PLACES):
        out = io.BytesIO()
        Image.open(folder / 'places' / f'{name}.png').convert('RGB').save(out, 'JPEG', quality=90)
        resources[BOOTH_BASE + len(BOOTH_PIECES) + 1 + k] = out.getvalue()
        entry['places'][name] = BOOTH_BASE + len(BOOTH_PIECES) + 1 + k
    return resources, entry


def build_skin(files, items_source=None, *, pcm_wav, music=True, booth_folder=None):
    """{resource ID: bytes} for the X360 skin from the prototype's files (x360.Prototype.files); `items_source` (the
    New Rules X1i jar's resources, nr_art.load) adds New Rules' item pictures outlined; `pcm_wav` is the translator's
    IMA ADPCM decoder (x360.pcm_wav); `music` False leaves the music out (no ffmpeg); `booth_folder` adds what the
    Xenia booth shot (booth)."""
    import nr_art
    resources, spec = {}, dict(format=FORMAT, version=VERSION, pictures={}, items={}, fonts={}, sounds={},
                               sound_tracks={}, music_track={})
    pictures = {name: _picture(files, path, alpha, cell) for name, path, alpha, cell in PICTURES}
    pictures.update(_derived(pictures))
    next_id = PICTURE_BASE
    for name in [p[0] for p in PICTURES] + list(DERIVED):
        resources[next_id] = _png(pictures[name])
        spec['pictures'][name] = next_id
        next_id += 1
    if items_source is not None:
        icons = nr_art.Pack(items_source[NR_ITEM_ICONS], items_source)
        for index in range(NR_ITEMS):
            frame = icons.frames[index] if index < len(icons.frames) else None
            if index in ITEMS:
                spec['items'][str(index)] = spec['pictures'][ITEMS[index]]
            elif frame is not None:
                resources[next_id] = _png(outlined(frame))
                spec['items'][str(index)] = next_id
                next_id += 1
    if next_id > FONT_PAGE_BASE:
        raise SkinError('too many pictures for the skin\'s IDs')
    page_id = FONT_PAGE_BASE
    for name, path in FONTS:
        font, pages = read_font(files[path].decode('utf-8'))
        folder = path.rsplit('/', 1)[0]
        font['pages'] = []
        for page in pages:
            resources[page_id] = _png(Image.open(io.BytesIO(files[f'{folder}/{page}'])).convert('RGBA'))
            font['pages'].append(page_id)
            page_id += 1
        spec['fonts'][name] = font
    if page_id > SOUND_BASE:
        raise SkinError('too many font pages for the skin\'s IDs')
    for i, (name, path) in enumerate(SOUNDS):
        resources[SOUND_BASE + i] = pcm_wav(files[path])
        spec['sounds'][name] = SOUND_BASE + i
    for track, names in SOUND_TRACKS.items():
        spec['sound_tracks'][str(track)] = [spec['sounds'][n] for n in names]
    if music:
        resources[MUSIC] = ogg_wav(files[MUSIC_FILE])
        spec['music_track'][str(MUSIC_TRACK)] = MUSIC
    if booth_folder is not None:
        shot, spec['booth'] = booth(booth_folder)
        resources.update(shot)
    resources[SPEC] = json.dumps(spec, sort_keys=True, separators=(',', ':')).encode('utf-8')
    assert all(i in SKIN_IDS for i in resources)
    return resources
