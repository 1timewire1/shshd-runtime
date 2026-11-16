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
