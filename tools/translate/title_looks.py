"""shshd-runtime: Add-Ons' Title Screen Look (owner, 2026-11-16; reference/TITLE_SCREENS_PLAN.md and
reference/Other Games/docs/TITLE_SCREENS.md): each translated game's title art for the HD main menu, built from the player's
own files into its addon, read by the player's title_look.py.

Each builder returns {resource: bytes}: the spec (JSON, at the look's number in the game profile's TITLE_LOOKS) and its
pictures (PNG), numbered after it. Coordinates are HD's points in its 768 x 1024 frame; a picture's `scale` is points per
pixel, and `smooth` false keeps pixel art sharp (scaled nearest).
"""
import io
import json
from pathlib import Path

from PIL import Image, ImageFilter

SPEC_VERSION = 1
FRAME = (768, 1024)
TALLEST = 2048          # points: the backgrounds cover frames up to this tall without being scaled (9:19.5 is 1664)
PHOTO_BORDER, PHOTO_TURN = 14, 5        # the photos' white border (points) and tilt (degrees), as the mock-ups
LOOK_IDS = {'nr': 26960, 'brew07': 26960, 'brew08': 26970, 'shw': 26960, 'shs11': 26960, 'x360': 26960}


def png(image):
    out = io.BytesIO()
    image.save(out, 'PNG', optimize=True)
    return out.getvalue()


def picture(resource, scale=1, smooth=True):
    return {'id': resource, 'scale': scale, 'smooth': smooth}


def spec_bytes(spec):
    return json.dumps(dict(version=SPEC_VERSION, **spec), sort_keys=True).encode('utf-8')


def framed_photo(art, border=PHOTO_BORDER, turn=PHOTO_TURN):
    """`art` (RGB, at 1 pixel per point) as a white-bordered photo turned `turn` degrees, with a soft shadow below and to
    the right, as the mock-ups draw it. RGBA."""
    photo = Image.new('RGBA', (art.width + 2 * border, art.height + 2 * border), (250, 250, 246, 255))
    photo.paste(art.convert('RGB'), (border, border))
    turned = photo.rotate(turn, resample=Image.BICUBIC, expand=True)
    pad = 24
    out = Image.new('RGBA', (turned.width + 2 * pad, turned.height + 2 * pad), (0, 0, 0, 0))
    shadow = Image.new('RGBA', turned.size, (0, 0, 0, 0))
    shadow.putalpha(turned.getchannel('A').point(lambda v: v * 110 // 255))
    out.alpha_composite(shadow, (pad + 8, pad + 10))
    out = out.filter(ImageFilter.GaussianBlur(8))
    out.alpha_composite(turned, (pad, pad))
    return out


def tiled(tile, size):
    out = Image.new('RGBA', size, (0, 0, 0, 255))
    for y in range(0, size[1], tile.height):
        for x in range(0, size[0], tile.width):
            out.alpha_composite(tile, (x, y))
    return out


# ---------------------------------------------------------------------------------------------------- New Rules

NR_STORE_HEADER = 'header_mob_shsnr.jpg'    # EA Mobile's store header (Wayback, 2009-12-17)
NR_STORE_CROP = (485, 31, 719, 262)         # Paula, Spike and Raven, right of the store logo's outline
NR_LOGO, NR_LOGO_SCALE, NR_LOGO_CENTRE = 215, 3, (384, 192)      # the WinMo logo, with "New Rules"
NR_PHOTO_CENTRE = (384, 560)


def nr_look(x1i, pud, store_art, base=LOOK_IDS['nr']):
    """New Rules: the X1i jar's menu backdrop (the blue tile, the cream stripe between the orange edges; nr_art), the WinMo
    res_large.pud's logo 215, and the store header's three as a photo. `store_art`: the folder of EA Mobile's store art."""
    import nr_art
    from exp_runtime.ui_assets import LayoutBank, Rect
    res = nr_art.load(x1i)
    packs = [nr_art.Pack(res[i], res, tint=t) for i, t in zip(nr_art.BACKDROP_PACKS[0], nr_art.BACKDROP_TINTS)]
    w, h = FRAME[0] // 2, TALLEST // 2              # built at half the points, shown at 2 (nearest)
    backdrop = tiled(packs[0].frames[0].convert('RGBA'), (w, h))
    bank = LayoutBank.parse(res[nr_art.LAYOUT_BANK])
    stripe = round(w * 290 / 480)
    stripe_id = next(n.payload[0] for n in bank.layouts[nr_art.GAME_LAYOUT].nodes if n.kind == 7 and n.flags & 16)
    nr_art.draw_layout(backdrop, bank, stripe_id, Rect((w - stripe) // 2, 0, stripe, h),
                       {nr_art.BACKDROP_SLOTS[1]: packs[1], nr_art.BACKDROP_SLOTS[2]: packs[2]})
    logo = Image.open(io.BytesIO(nr_art.load(pud)[NR_LOGO])).convert('RGBA')
    art = Image.open(Path(store_art) / NR_STORE_HEADER).convert('RGB').crop(NR_STORE_CROP)
    photo = framed_photo(art.resize((art.width * 2, art.height * 2), Image.LANCZOS))
    spec = {'background': {'cover': picture(base + 1, 2, False)},
            'photo': {'picture': picture(base + 2), 'centre': list(NR_PHOTO_CENTRE)},
            'title': {'picture': picture(base + 3, NR_LOGO_SCALE, False), 'centre': list(NR_LOGO_CENTRE)}}
    return {base: spec_bytes(spec), base + 1: png(backdrop.convert('RGB')), base + 2: png(photo), base + 3: png(logo)}


# ---------------------------------------------------------------------------------------------------- Surviving Hollywood

SHW_MENU_LAYOUT, SHW_HIDDEN = 9, {31, 32}       # the main menu's layout, and the children MainMenu hides
SHW_SCALE = 3                                   # painted at a third of the points, tripled (nearest)
SHW_BOTTOM_ROWS = 103                           # rows that stay the same at any height, from the bottom
SHW_CITY_MAP, SHW_CITY_SCALE, SHW_PHOTO_CENTRE = 1100, 1.35, (424, 585)


def hollywood_look(jar, base=LOOK_IDS['shw']):
    """Surviving Hollywood: the main menu's layout 9 (the spotlight panel, its rims, the film strip and the round logo 1001,
    which stays under the photo: owner, 2026-11-16) painted as the game would on a screen the frame's shape, and the city
    map (1100, its transparent sky filled) as a photo. The layout stretches between a top and a bottom that stay the same
    at any height, its middle a two-row scanline, so it ships as those three slices (built at the frame's height)."""
    import shw
    import shw_sprites
    import shw_ui
    found = shw.jar_resources(jar)
    sprites, _, comps = shw_sprites.parse(found[16])
    slots = {0: shw.picture(found[1001]).convert('RGBA'), 1: shw.picture(found[1002]).convert('RGBA')}
    layouts = shw_ui.Layouts(found[15], sprites, comps, slots)
    hidden = layouts.hidden(SHW_MENU_LAYOUT) | SHW_HIDDEN

    def paint(h):
        canvas = Image.new('RGBA', (FRAME[0] // SHW_SCALE + 1, h), (0, 0, 0, 255))
        layouts.paint(canvas, SHW_MENU_LAYOUT, 0, 0, canvas.width, h, hidden=hidden)
        return canvas.convert('RGB')
    short = paint(-(-FRAME[1] // SHW_SCALE))            # HD's own frame: its top and bottom meet with nothing between
    split = short.height - SHW_BOTTOM_ROWS
    tall = paint(short.height + 40)
    top, bottom, middle = short.crop((0, 0, short.width, split)), short.crop((0, split, short.width, short.height)), \
        tall.crop((0, split + 16, tall.width, split + 18))      # past the 16 rows of gradient the top runs into
    city = shw.picture(found[SHW_CITY_MAP]).convert('RGBA')
    sky = Image.new('RGBA', city.size)
    for y in range(city.height):
        t = min(1.0, y / 120)
        sky.paste((round(120 + 80 * t), round(170 + 60 * t), round(225 + 20 * t), 255), (0, y, city.width, y + 1))
    sky.alpha_composite(city)
    art = sky.convert('RGB')
    photo = framed_photo(art.resize((round(art.width * SHW_CITY_SCALE), round(art.height * SHW_CITY_SCALE)), Image.LANCZOS))
    spec = {'background': {'top': picture(base + 1, SHW_SCALE, False), 'middle': picture(base + 2, SHW_SCALE, False),
                           'bottom': picture(base + 3, SHW_SCALE, False)},
            'photo': {'picture': picture(base + 4), 'centre': list(SHW_PHOTO_CENTRE)}}
    return {base: spec_bytes(spec), base + 1: png(top), base + 2: png(middle), base + 3: png(bottom), base + 4: png(photo)}


# ---------------------------------------------------------------------------------------------------- SHS '11

SHS11_WOOD, SHS11_LOGO = (1, 0, 0), (21, 0, 0)      # gamelib pictures (entry, order, palette): wood with the photo; logo
SHS11_SCALE, SHS11_LOGO_CENTRE = 1.6, (384, 130)     # the frame's width over the 480-wide art


def shs11_look(art_jar, base=LOOK_IDS['shs11']):
    """SHS '11 (the 480 x 800 build's art, `art_jar` an open zipfile): gamelib picture 1, the wood with the photo painted
    on (so nothing drops in), covering the frame, and the logo, picture 21, on top. Both shown at the frame's width."""
    import shs11
    pictures = {(p.entry, p.order, p.palette): p.png for p in shs11.interface_pictures(art_jar)}
    wood, logo = Image.open(io.BytesIO(pictures[SHS11_WOOD])), Image.open(io.BytesIO(pictures[SHS11_LOGO]))
    if wood.width != 480:
        raise ValueError(f"'11's wood is {wood.width} wide: use the 480 x 800 build's art")
    spec = {'background': {'cover': picture(base + 1, SHS11_SCALE)},
            'title': {'picture': picture(base + 2, SHS11_SCALE), 'centre': list(SHS11_LOGO_CENTRE)}}
    return {base: spec_bytes(spec), base + 1: png(wood.convert('RGB')), base + 2: png(logo.convert('RGBA'))}


# ---------------------------------------------------------------------------------------------------- BREW '07 and '08

BREW_TITLE = 47                 # the whole title, logo and photo in one picture (res_xlarge.pud)
BREW_TILE_ART = 14              # the UI tile (sheet 12 frame 2), the lilac check behind it
BREW_07_ROWS = 225              # '07's picture down to HIGH SCHOOL: its rows 225..251 are the gap and CENTERSCORE (owner: dropped)
BREW_SCALE, BREW_CENTRE = 3, (384, 375)     # tripled, nearest; centred between the top and the buttons
BREW_MARGIN = 12                # points kept clear at each side when '07's picture grows in a taller frame
JAVA_08_TILES, JAVA_08_SCALE = (4, 5), 4    # the Java '08 demo's blue "SHS" tiles (sheet 8018), checkered, quadrupled
STORE_THUMBNAIL = 'product-thumbnail_SHS.jpg'   # EA Mobile's '08 store thumbnail (Wayback), its own logo on it
BREW_08_PHOTO_CENTRE = (384, 390)


def brew_07_look(base_07_pud, base=LOOK_IDS['brew07']):
    """BREW '07: picture 47 without CENTERSCORE on the lilac tile, tripled. The pink band behind the photo is carried out to
    the frame's edges, each row by its edge pixel, as the phone's 240-wide screen showed it edge to edge. The picture takes
    the photo's place, the band with it, but doesn't drop in: its logo is painted onto the photo (owner, 2026-11-16)."""
    import brew_art
    art = brew_art.Art([brew_art.base_pack(base_07_pud)])
    title = art.image(BREW_TITLE).convert('RGBA')
    title = title.crop(title.getbbox())
    title = title.crop((0, 0, title.width, BREW_07_ROWS))
    tile = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    art.draw(tile, BREW_TILE_ART, 0, 0)
    tile = tile.crop(tile.getbbox())
    width = -(-FRAME[0] // BREW_SCALE)
    backdrop = tiled(tile, (width, -(-TALLEST // BREW_SCALE)))
    photo = Image.new('RGBA', (width, title.height), (0, 0, 0, 0))
    left = (width - title.width) // 2
    for y in range(title.height):
        for x0, xs in ((0, range(0, left)), (title.width - 1, range(left + title.width, width))):
            pixel = title.getpixel((x0, y))
            if pixel[3] == 255:
                for x in xs:
                    photo.putpixel((x, y), pixel)
    photo.alpha_composite(title, (left, 0))
    spec = {'background': {'cover': picture(base + 1, BREW_SCALE, False)},
            'photo': {'picture': picture(base + 2, BREW_SCALE, False), 'centre': list(BREW_CENTRE),
                      'fit': title.width * BREW_SCALE + 2 * BREW_MARGIN,      # the letters stay inside; the band may not
                      'drop': False}}           # in place from the start: its logo is painted on (owner, 2026-11-16)
    return {base: spec_bytes(spec), base + 1: png(backdrop.convert('RGB')), base + 2: png(photo)}


def brew_08_look(java_08_jar, store_art, base=LOOK_IDS['brew08']):
    """BREW '08 (owner's concept B): the Java '08 demo's blue SHS tile, checkered as its menu lays it, quadrupled, and EA's
    store thumbnail (its own logo) as a photo, smoothly quadrupled. No separate title."""
    import brew_java
    frames = brew_java.sheet(brew_java.resources(java_08_jar)[brew_java.UI_SHEET])
    tiles = [frames[k].convert('RGBA') for k in JAVA_08_TILES]
    size = tiles[0].size
    width, height = -(-FRAME[0] // JAVA_08_SCALE), -(-TALLEST // JAVA_08_SCALE)
    backdrop = Image.new('RGBA', (width, height), (0, 0, 0, 255))
    for ty, y in enumerate(range(0, height, size[1])):
        for tx, x in enumerate(range(0, width, size[0])):
            backdrop.alpha_composite(tiles[(tx + ty) % 2], (x, y))
    thumbnail = Image.open(Path(store_art) / STORE_THUMBNAIL).convert('RGB')
    photo = framed_photo(thumbnail.resize((thumbnail.width * 4, thumbnail.height * 4), Image.LANCZOS))
    spec = {'background': {'cover': picture(base + 1, JAVA_08_SCALE, False)},
            'photo': {'picture': picture(base + 2), 'centre': list(BREW_08_PHOTO_CENTRE)}}
    return {base: spec_bytes(spec), base + 1: png(backdrop.convert('RGB')), base + 2: png(photo)}
