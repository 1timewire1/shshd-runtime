"""The X360 look for New Rules' minigame arena, for the X360 addon (docs/X360.md):
the cancelled prototype's own 2D minigame art, fonts, effect sounds and Diss Practice music, cut from its data.pak, and
New Rules' item pictures with an ink outline and a drop shadow, so they sit with it (owner, 2026-10-31).

The skin is data only: a JSON spec (SPEC) naming every picture, font, sound and the music by resource ID, all within
SKIN_IDS. The player reads it straight from the imported addon (ContentLibrary.addon), so New Rules' episodes need no
rebuild. The turntable deck, Diss Practice's places and the score digits (3D models in the prototype) come from a Xenia
booth (booth); the title screen's layers make the arena's backdrop (title).
"""
import io
import json
import shutil
import subprocess

from PIL import Image, ImageChops, ImageFilter, ImageOps

FORMAT, VERSION = 'shshd-arena-skin-x360', 1
SPEC = 26300
SKIN_IDS = range(26300, 26900)
PICTURE_BASE = 26301                    # PICTURES then New Rules' outlined items, in order
FONT_PAGE_BASE = 26360
SOUND_BASE = 26380
MUSIC = 26390
TUTORIAL_MUSIC = 26391
# Shot in Xenia (reference tools x360_dbpbooth.py / x360_dbpcut.py; Additional Resources/x360-dbp-booth): the deck, the
# record, every digit in every slot as one atlas, and Diss Practice's places, people taken out.
BOOTH_BASE = 26400
BOOTH_PIECES = ('deck', 'table', 'record')              # 26400-26402; the digit atlas 26403; the places from 26404
PLACES = ('school_front_diss_002', 'school_hallway_b_diss_001', 'josh_house_in_diss_001', 'school_front_diss_001',
          'school_hallway_b_diss_002')                  # each practice's own view first
DIGIT_SLOTS, DIGITS = 8, 10
# The title screen's layered background (templates guigroup.wxr menus/splash/main), the arena's backdrop in place of a
# place, whatever the episode's location (owner, 2026-11-01): the sky, its clouds (scrolling), the ray glints, and the
# still front layers merged into one. Each layer fills the 16:9 screen; placements, the clouds' opacity and the school's
# rectangle were matched to the owner's Xenia screenshot of the title.
TITLE_BASE = 26410                      # sky, clouds, the ray glints' atlas, the front
PARTS_BASE = 26414                      # the deck split: body, record, its seams, spindle, the tone arm's atlas
OPENING_BASE = 26796                    # Day of Diss's opening (opening): its spec, then its pictures and whip, 10 in all
OPENING_FRAME = 768, 1024
OPENING_ART = 'data/art/hud/characters_presentation/josh/'
OPENING_SUBTITLE = "King of Diss '08"   # (guilabel hud/characters_presentation/josh/subtitle)
OPENING_WHIP = 14510                    # the card and its whip, in the music
OPENING_CLIMB_WINDOW = 978              # of josh_tall's 1440 wide: the width that lines his face up with the card's
NOTES_BASE = 26790                      # Diss Practice's notes (the Monday Planner; desktop_x360_diss), past the later renders
NOTE_KINDS = ('note', 'bad', 'swap', 'double')
DANCE_BASE, DANCE_ATLAS_WIDTH = 26794, 2048     # Josh's dance behind that deck, one atlas; MS3's the next
PUZZLE_BASE = 26436                     # the jewel puzzle (Puzzle Test; exp_runtime.x360_puzzle, desktop_x360_puzzle)
LEASH_BASE = 26431                      # the leash game (Dating Beth; exp_runtime.x360_games, desktop_x360_leash)
SLOT_BASE = 26420                       # the slot machine (Dating Beth; exp_runtime.x360_games, desktop_x360_slot)
# Cells of hud/icons (bubbles/minigames/slot_machine's menus/icons pictures): 64 x 64, four to a row.
SLOT_ICONS = (('bulb', 1), ('cross', 0), ('question', 3), ('off', 2))
SLOT_SOUNDS = ('data/sound/gui/success.wav', 'data/sound/gui/miss.wav', 'data/sound/gui/timer.wav')
GUI = 'data/art/gui/'
TITLE_SIZE = (1280, 720)                # the sky and the front as stored (the textures are 512 to 1024 square)
TITLE_CLOUDS = dict(opacity=0.35, speed=0.01)   # shader gui/menus/images/sky_clouds: ShifterSpeed 0.01 0 a second
TITLE_SCHOOL = (0.53, 0.451, 0.48, 0.575)       # x, y, width, height in the screen, at rest after sliding in
TITLE_RAYS, TITLE_RAY_MS, TITLE_RAY_EVERY = 7, 50, 3000     # raylights' OnStep: each shown 0.05 s, every 3 s
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
# Diss Practice's good-note tiers as New Rules' good-note pictures (docs/X360.md); the other X360
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
MUSIC_BITRATE = '128k'                  # mono, as the source
# The tutorials' music (owner, 2026-11-01): New Rules plays none until the game starts. Brought down to the practice
# music's level: its RMS is -8.0 dB against dbp_bg_music's -13.1.
TUTORIAL_MUSIC_FILE, TUTORIAL_MUSIC_GAIN_DB = 'data/sound/music/diss_001.ogg', -5


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


def ogg_mp3(data, gain_db=0):
    """The music as an MP3 (ffmpeg), a sixth of its size as a WAV. Its loop comes 29 ms later than the source's (the
    encoder's delay), and the games end before its 92.5 s are up. No Xing frame: it would count as playing time."""
    ffmpeg = shutil.which('ffmpeg')
    if ffmpeg is None:
        raise SkinError("the skin's music needs ffmpeg on PATH")
    gain = ['-af', f'volume={gain_db}dB'] if gain_db else []
    result = subprocess.run([ffmpeg, '-v', 'error', '-i', 'pipe:0', *gain, '-f', 'mp3', '-acodec', 'libmp3lame', '-b:a', MUSIC_BITRATE,
                             '-write_xing', '0', '-id3v2_version', '0', 'pipe:1'], input=data, capture_output=True,
                            check=True)
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
    if 'parts' in info:
        resources_parts, entry['parts'] = deck_parts(folder, info['parts'])
        resources.update(resources_parts)
    if 'notes' in info:
        notes = info['notes']
        kinds = {}
        for i, kind in enumerate(NOTE_KINDS):
            resources[NOTES_BASE + i] = (folder / notes['kinds'][kind]['file']).read_bytes()
            kinds[kind] = dict(id=NOTES_BASE + i, anchor=notes['kinds'][kind]['anchor'], depth=notes['kinds'][kind]['depth'])
        entry['notes'] = dict(kinds=kinds, frame=notes['frame'], height=notes['height'], wheel=notes['wheel'], out=notes['out'])
    if 'dance' in info:
        resources[DANCE_BASE], entry['dance'] = dance_atlas(folder, info['dance'])
    if 'dance_ms3' in info:                     # the MS3 Characters switch's, in the same places
        resources[DANCE_BASE + 1], entry['dance_ms3'] = dance_atlas(
            folder, dict(info['dance_ms3'], places=info['dance'].get('places', {})), 'dance_ms3', DANCE_BASE + 1)
    return resources, entry


def dance_atlas(folder, dance, name='dance', base=DANCE_BASE):
    """The atlas's bytes and the spec's entry: Josh's dance behind the deck (reference tools x360_dbpdance.py), its frames
    on shelves in one atlas, each with its box in the booth's camera frame, and how he stands before he starts."""
    names = ['stand'] + [str(i) for i in range(len(dance['frames']))]
    cells = [Image.open(folder / name / f'{frame}.png').convert('RGBA') for frame in names]
    placed, x, y, shelf = [], 0, 0, 0
    for cell in cells:
        if x + cell.width > DANCE_ATLAS_WIDTH:
            x, y, shelf = 0, y + shelf, 0
        placed.append([x, y, cell.width, cell.height])
        x, shelf = x + cell.width, max(shelf, cell.height)
    atlas = Image.new('RGBA', (DANCE_ATLAS_WIDTH, y + shelf), (0, 0, 0, 0))
    for cell, rect in zip(cells, placed):
        atlas.paste(cell, tuple(rect[:2]))
    boxes = [dance['stand']] + dance['frames']
    cells = [dict(rect=rect, box=box) for rect, box in zip(placed, boxes)]
    return _png(atlas), dict(atlas=base, period_ms=dance['period_ms'], stand=cells[0], frames=cells[1:],
                             places=dance.get('places', {}))


def deck_parts(folder, parts):
    """{resource ID: bytes} and the spec's `parts` entry: the deck split so its record can turn and its tone arm swing
    (reference tools x360_dbparm.py). The arm's frames are packed into one atlas, and `push` is its angle over time."""
    resources = {PARTS_BASE + i: (folder / f'{name}.png').read_bytes()
                 for i, name in enumerate(('body', 'record_base', 'record_seams', 'spindle'))}
    arm = parts['arm']
    cells = [Image.open(folder / 'arm' / f'{k}.png').convert('RGBA') for k in range(len(arm['frames']))]
    atlas = Image.new('RGBA', (max(c.width for c in cells), sum(c.height for c in cells)), (0, 0, 0, 0))
    frames, y = [], 0
    for cell, frame in zip(cells, arm['frames']):
        atlas.paste(cell, (0, y))
        frames.append(dict(angle=frame['angle'], rect=[0, y, cell.width, cell.height], box=frame['box'], tip=frame['tip']))
        y += cell.height
    resources[PARTS_BASE + 4] = _png(atlas)
    return resources, dict(body=dict(id=PARTS_BASE, box=parts['body']),
                           record=dict(id=PARTS_BASE + 1, box=parts['record_base']),
                           seams=dict(id=PARTS_BASE + 2, **parts['seams']),
                           spindle=dict(id=PARTS_BASE + 3, box=parts['spindle']),
                           arm=dict(atlas=PARTS_BASE + 4, frames=frames, push=arm['push']), camera=parts.get('camera'))


def slot(files, pcm_wav):
    """{resource ID: bytes} and the spec's `slot` entry: the slot machine's icons, panel, focus window, clock ring,
    sounds (at x360_games.SOUND_SUCCESS...) and its labels' font, which names no page the pak has: bleeker_black."""
    icons = _picture(files, 'data/art/hud/icons.jpg', 'data/art/hud/icons_a.jpg', None)
    resources, entry = {}, dict(icons={})
    for i, (name, cell) in enumerate(SLOT_ICONS):
        left = cell % 4 * 64
        resources[SLOT_BASE + i] = _png(icons.crop((left, cell // 4 * 64, left + 64, cell // 4 * 64 + 64)))
        entry['icons'][name] = SLOT_BASE + i
    for i, (name, path, alpha) in enumerate((('panel', 'data/art/hud/narrator.png', None),
                                             ('window', 'data/art/hud/slot_window.png', None),
                                             ('clock', 'data/art/hud/clock.jpg', 'data/art/hud/clock_a.jpg'))):
        resources[SLOT_BASE + 4 + i] = _png(_picture(files, path, alpha, None))
        entry[name] = SLOT_BASE + 4 + i
    for i, path in enumerate(SLOT_SOUNDS):
        resources[SLOT_BASE + 7 + i] = pcm_wav(files[path])
    font, _ = read_font(files['data/art/fonts/bleeker.fnt'].decode('utf-8'))
    font['pages'] = [SLOT_BASE + 10]
    resources[SLOT_BASE + 10] = _png(Image.open(io.BytesIO(files['data/art/fonts/bleeker_black.png'])).convert('RGBA'))
    entry['font'] = font
    return resources, entry


def leash(files):
    """{resource ID: bytes} and the spec's `leash` entry: the leash game's power-bar fill, the two arrows from the icons'
    sheet (hud/icons/leftright and updown) and the joystick flipbooks over them. The bar's frame is `power_bar`."""
    fill = _picture(files, 'data/art/hud/power_bar_fl.jpg', 'data/art/hud/power_bar_fl_a.jpg', None)
    icons = _picture(files, 'data/art/hud/icons.jpg', 'data/art/hud/icons_a.jpg', None)
    resources = {LEASH_BASE: _png(fill)}
    entry = dict(fill=LEASH_BASE, arrows={}, stick={})
    for i, (name, flipbook) in enumerate((('leftright', 'stick_shake_side'), ('updown', 'stick_shake_frontback'))):
        resources[LEASH_BASE + 1 + i] = _png(icons.crop((i * 64, 64, i * 64 + 64, 128)))
        entry['arrows'][name] = LEASH_BASE + 1 + i
        resources[LEASH_BASE + 3 + i] = _png(_picture(files, f'data/art/hud/{flipbook}.jpg',
                                                      f'data/art/hud/{flipbook}_a.jpg', None))
        entry['stick'][name] = LEASH_BASE + 3 + i
    return resources, entry


PUZZLE_FILLS = (('fill_red', 'red_bar_fl.jpg'), ('fill_purple', 'purple_bar_fl.jpg'))
PUZZLE_SOUNDS = ('data/sound/fx/move.wav', 'data/sound/fx/move3.wav')       # at x360_puzzle.SOUND_DRAG, SOUND_CLEAR
PUZZLE_JEWELS = PUZZLE_BASE + 14                                            # then each jewel's shine frames


def puzzle(files, pcm_wav, folder):
    """{resource ID: bytes} and the spec's `puzzle` entry: the jewels, cursor and boards shot from above in Xenia
    (reference tools x360_puzzlebooth.py; `folder`: Additional Resources/x360-puzzle-booth, with puzzle.json placing each
    in cell units), the two bars the skin hasn't got, and the two sounds."""
    from pathlib import Path
    folder = Path(folder)
    entry = json.loads((folder / 'puzzle.json').read_text(encoding='utf-8'))
    placed = dict(jewels=entry['jewels'], cursor=entry['cursor'], board=entry['board'])
    spec = dict(placed=placed, shine_ms=entry['shine_ms'], jewels={})
    resources = {}
    for n, name in enumerate(('cursor', 'board', 'board_metal')):
        resources[PUZZLE_BASE + n] = (folder / f'{name}.png').read_bytes()
        spec[name] = PUZZLE_BASE + n
    for n, (name, path) in enumerate(PUZZLE_FILLS):
        resources[PUZZLE_BASE + 3 + n] = _png(_picture(files, HUD + path, HUD + 'power_bar_fl_a.jpg', None))
        spec[name] = PUZZLE_BASE + 3 + n
    for n, path in enumerate(PUZZLE_SOUNDS):
        resources[PUZZLE_BASE + 5 + n] = pcm_wav(files[path])
    next_id = PUZZLE_JEWELS
    for kind in sorted(entry['jewels']):
        spec['jewels'][kind] = []
        for phase in range(entry['phases']):
            resources[next_id] = (folder / f'jewel_{kind}_{phase}.png').read_bytes()
            spec['jewels'][kind].append(next_id)
            next_id += 1
    return resources, spec


def opening(files, pcm_wav, folder):
    """{resource ID: bytes} of Day of Diss's opening, a storyboard cutscene (exp_runtime.cutscene; owner, 2026-11-02). `folder`
    (Additional Resources/x360-opening; reference tools x360_opening_booth*.py) holds a still per camera move, 2560 x 1440, and
    josh_tall, 1440 x 2560: Josh from the place of the camera the card is painted over, on its side, hair to shoes. All are stored at
    the frame's scale, so a window is a blit. The pans follow the prototype's, the cuts are timed to the music by the owner (2026-11-02), and the whip is where the
    prototype's fires against it, measured from a slowed capture (music 14.51 s, 0.3 s before its drop). The card then holds, as the
    episode's title card."""
    from pathlib import Path
    folder = Path(folder)
    size = OPENING_FRAME
    spec_id, *pictures = range(OPENING_BASE, OPENING_BASE + 10)
    first, lot, low, climb, back_id, stains_id, name_id, subtitle_id, whip_id = pictures

    def still(name, scale, target):
        image = Image.open(folder / f'{name}.jpg').convert('RGB')
        image = image.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, 'JPEG', quality=88, optimize=True)
        resources[target] = buffer.getvalue()
        return image

    def layered(name):
        image = Image.open(io.BytesIO(files[OPENING_ART + name + '.jpg'])).convert('RGB')
        image.putalpha(Image.open(io.BytesIO(files[OPENING_ART + name + '_a.jpg'])).convert('L').resize(image.size))
        return image

    resources = {}
    sweep = size[1] / 1440
    for name, target in (('sweep_first', first), ('sweep_lot', lot), ('sweep_low', low)):
        travel = still(name, sweep, target).width - size[0]
    tall = still('josh_tall', size[0] / OPENING_CLIMB_WINDOW, climb)
    # The card: the art keeps the shape the X360 stretches its square texture to, with the window on Josh.
    art = Image.open(io.BytesIO(files[OPENING_ART + 'background.jpg'])).convert('RGB').resize((1772, size[1]), Image.LANCZOS)
    buffer = io.BytesIO()
    art.crop((950, 0, 950 + size[0], size[1])).save(buffer, 'JPEG', quality=90, optimize=True)
    resources[back_id] = buffer.getvalue()
    resources[stains_id], resources[name_id] = _png(layered('yellow_stains')), _png(layered('name'))
    font, _ = read_font(files['data/art/fonts/blambot_badaboom_white.fnt'].decode('utf-8'))
    page = Image.open(io.BytesIO(files['data/art/fonts/blambot_badaboom_white_00.png'])).convert('RGBA')
    glyphs = [font['chars'][str(ord(c))] for c in OPENING_SUBTITLE]
    line = Image.new('RGBA', (sum(g[6] for g in glyphs), font['line_height']), (0, 0, 0, 0))
    x = 0
    for g in glyphs:
        line.alpha_composite(page.crop((g[0], g[1], g[0] + g[2], g[1] + g[3])), (x + g[4], g[5]))
        x += g[6]
    line = line.resize((round(line.width * 1.25), round(line.height * 1.25)), Image.LANCZOS)
    resources[subtitle_id] = _png(line)
    resources[whip_id] = pcm_wav(files['data/sound/fx/whip.wav'])
    whole = [0, 0, *size]
    # The climb ends where his eyes and green headphone land on the card's, read off both pictures.
    k = size[0] / OPENING_CLIMB_WINDOW
    shots = [dict(image=first, start=0, end=3300, **{'from': [travel, 0, *size], 'to': whole}),
             dict(image=lot, start=3300, end=7000, **{'from': whole, 'to': [travel, 0, *size]}),
             dict(image=low, start=7000, end=10680, **{'from': whole, 'to': [travel, 0, *size]}),
             dict(image=climb, start=10680, end=OPENING_WHIP, ease='out',
                  **{'from': [tall.width - size[0], tall.height - size[1], *size], 'to': [round(221 * k), round(145 * k), *size]}),
             dict(image=back_id, start=OPENING_WHIP, end=OPENING_WHIP, **{'from': whole, 'to': whole})]
    middle = 300, 690                   # the name's centre, clear of his face
    name_w, name_h = 614, 346
    w, h = 768, 820
    overlays = [
        # The X360's hud/characters_presentation/josh: the stains shrink in over 0.2 s; 0.1 s on, the name does and the subtitle
        # slides in. Its places against each other are the X360's, at this scale.
        dict(image=stains_id, start=OPENING_WHIP, end=OPENING_WHIP + 200,
             **{'from': [middle[0] - 72, middle[1] + 78, w * 4, round(h / 1.9 * 4.9)], 'to': [middle[0] - 72, middle[1] + 78, w, h]}),
        dict(image=name_id, start=OPENING_WHIP + 100, end=OPENING_WHIP + 300,
             **{'from': [*middle, round(name_w * 1.75), round(name_h * 1.75)], 'to': [*middle, name_w, name_h]}),
        dict(image=subtitle_id, start=OPENING_WHIP + 100, end=OPENING_WHIP + 300,
             **{'from': [-line.width / 2, 818, line.width, line.height], 'to': [middle[0] + 110, 818, line.width, line.height]})]
    resources[spec_id] = json.dumps(dict(format='shshd-cutscene', version=1, size=list(size), music=26900, hold=OPENING_WHIP + 300,
                                         skip=OPENING_WHIP, shots=shots, overlays=overlays,
                                         sounds=[dict(at=OPENING_WHIP, sound=whip_id)])).encode('utf-8')
    return resources


def title(files):
    """{resource ID: bytes} and the spec's `title` entry: the title screen's layers (TITLE_BASE). Boxes are fractions
    of the 16:9 screen; a ray glint is white, its mask as alpha, cut to what shows and packed into one atlas."""
    def layer(rgb, alpha=None, colour=None):
        mask = Image.open(io.BytesIO(files[GUI + alpha])).convert('L') if alpha else None
        image = (Image.open(io.BytesIO(files[GUI + rgb])).convert('RGBA') if rgb
                 else Image.new('RGBA', mask.size, colour + (255,)))
        if mask is not None:
            image = image.resize(mask.size)
            image.putalpha(mask)
        return image
    resources = {}
    sky = io.BytesIO()
    layer('background.jpg').convert('RGB').resize(TITLE_SIZE, Image.LANCZOS).save(sky, 'JPEG', quality=90)
    resources[TITLE_BASE] = sky.getvalue()
    resources[TITLE_BASE + 1] = _png(layer('clouds.jpg', 'clouds_a.jpg'))
    masks = [Image.open(io.BytesIO(files[f'{GUI}raylight_{i + 1}_a.jpg'])).convert('L') for i in range(TITLE_RAYS)]
    boxes = [mask.point(lambda v: 255 if v > 12 else 0).getbbox() for mask in masks]     # past the JPEG's noise
    cuts = [(mask.crop(box), box, mask.size) for mask, box in zip(masks, boxes)]
    atlas = Image.new('RGBA', (sum(c.width for c, _, _ in cuts), max(c.height for c, _, _ in cuts)), (255, 255, 255, 0))
    frames, x = [], 0
    for cut, box, size in cuts:
        atlas.paste(Image.new('RGBA', cut.size, (255, 255, 255, 255)), (x, 0), cut)
        frames.append(dict(rect=[x, 0, cut.width, cut.height],
                           box=[round(v / size[i % 2], 5) for i, v in enumerate(box)]))
        x += cut.width
    resources[TITLE_BASE + 2] = _png(atlas)
    w, h = TITLE_SIZE
    front = layer('stain_clouds.png').resize(TITLE_SIZE, Image.LANCZOS)
    sx, sy, sw, sh = TITLE_SCHOOL
    school = layer('school_building.jpg', 'school_building_a.jpg').resize((round(sw * w), round(sh * h)), Image.LANCZOS)
    left, top = round(sx * w), round(sy * h)
    front.alpha_composite(school.crop((0, 0, min(school.width, w - left), min(school.height, h - top))), (left, top))
    front.alpha_composite(layer('city.jpg', 'city_a.jpg').resize(TITLE_SIZE, Image.LANCZOS))
    front.alpha_composite(layer(None, 'black_line_a.jpg', (0, 0, 0)).resize(TITLE_SIZE, Image.LANCZOS))
    resources[TITLE_BASE + 3] = _png(front)
    entry = dict(sky=TITLE_BASE, clouds=dict(id=TITLE_BASE + 1, **TITLE_CLOUDS),
                 rays=dict(atlas=TITLE_BASE + 2, frames=frames, ms=TITLE_RAY_MS, every=TITLE_RAY_EVERY),
                 front=TITLE_BASE + 3)
    return resources, entry


def build_skin(files, items_source=None, *, pcm_wav, music=True, booth_folder=None, puzzle_folder=None):
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
        resources[MUSIC] = ogg_mp3(files[MUSIC_FILE])
        spec['music_track'][str(MUSIC_TRACK)] = MUSIC
        if TUTORIAL_MUSIC_FILE in files:
            resources[TUTORIAL_MUSIC] = ogg_mp3(files[TUTORIAL_MUSIC_FILE], TUTORIAL_MUSIC_GAIN_DB)
            spec['tutorial_music'] = TUTORIAL_MUSIC
    if 'data/art/hud/narrator.png' in files:
        made, spec['slot'] = slot(files, pcm_wav)
        resources.update(made)
    if 'data/art/hud/stick_shake_side.jpg' in files:
        made, spec['leash'] = leash(files)
        resources.update(made)
    if puzzle_folder is not None:
        made, spec['puzzle'] = puzzle(files, pcm_wav, puzzle_folder)
        resources.update(made)
    if booth_folder is not None:
        shot, spec['booth'] = booth(booth_folder)
        resources.update(shot)
    shot, spec['title'] = title(files)
    resources.update(shot)
    resources[SPEC] = json.dumps(spec, sort_keys=True, separators=(',', ':')).encode('utf-8')
    assert all(i in SKIN_IDS for i in resources)
    return resources
