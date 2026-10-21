"""Cause of Death's dialogue/choice skins at HD density, derived from the SHS HD (iPad) bundle's skins.

CoD's skin packs 204/220/236/252 have exactly the geometry of SHS's (same 14 frames and sizes); 252 is byte-identical,
204 and 236 are grey recolours of SHS's blue and gold, 220 keeps SHS's colours, and every box frame caps SHS's opaque
interior at alpha 242. SHS HD ships the same packs redrawn at 2x (content.HD_ASSET_MAP: 247/263/279/295). Each of
their literal frames is turned into CoD's look with per-frame tables fitted against CoD's own 1x frame: RGB from
min(R, G, B) (the recolour is a smooth function of it) and alpha from alpha. For each frame the transform that scales
back closest to CoD's frame is kept -- "keep as is" wins where CoD did not change the art. Presentation only: the
pixels go into a copy of the HD pack's own bytes, so it parses and draws like any HD pack. legacy/findings.md,
"Cause of Death HD skins".
"""
from functools import lru_cache

from ..ui_assets import ImagePack

# CoD (= SHS Android) skin pack -> its SHS HD counterpart (content.HD_ASSET_MAP).
SKIN_PACKS = {204: 247, 220: 263, 236: 279, 252: 295}
# The portrait mask is byte-identical to SHS Android's 268, so SHS HD's 311 is its HD version as it stands.
IDENTICAL = {268: 311}


def _table(pairs, width):
    """A 256-entry lookup from (key, value-tuple) pairs: the mean value per key, gaps interpolated linearly."""
    sums = {}
    for key, value in pairs:
        s = sums.setdefault(key, [0.0] * (width + 1))
        for c in range(width):
            s[c] += value[c]
        s[width] += 1
    known = {key: tuple(s[c] / s[width] for c in range(width)) for key, s in sums.items()}
    keys = sorted(known)
    table = []
    for key in range(256):
        if key in known:
            table.append(known[key])
            continue
        lower = max((k for k in keys if k < key), default=None)
        upper = min((k for k in keys if k > key), default=None)
        if lower is None or upper is None:
            table.append(known[upper if lower is None else lower])
            continue
        t = (key - lower) / (upper - lower)
        table.append(tuple(a + (b - a) * t for a, b in zip(known[lower], known[upper])))
    return table


def _box_downscale(pixels, width, height, out_width, out_height):
    """Area-average RGBA (straight alpha, colour weighted by alpha) to the 1x size."""
    out = []
    for y in range(out_height):
        y0, y1 = y * height / out_height, (y + 1) * height / out_height
        for x in range(out_width):
            x0, x1 = x * width / out_width, (x + 1) * width / out_width
            acc, area = [0.0, 0.0, 0.0, 0.0], 0.0
            for sy in range(int(y0), min(height, int(y1 + 0.999))):
                wy = min(y1, sy + 1) - max(y0, sy)
                for sx in range(int(x0), min(width, int(x1 + 0.999))):
                    w = wy * (min(x1, sx + 1) - max(x0, sx))
                    if w <= 0:
                        continue
                    i = (sy * width + sx) * 4
                    a = pixels[i + 3]
                    for c in range(3):
                        acc[c] += pixels[i + c] * a * w
                    acc[3] += a * w
                    area += w
            alpha = acc[3] / area if area else 0
            out.append(tuple(acc[c] / acc[3] if acc[3] else 0 for c in range(3)) + (alpha,))
    return out


def _error(candidate, target):
    """Mean premultiplied difference between two 1x pixel lists (0-255 scale)."""
    total = 0.0
    for (r1, g1, b1, a1), (r2, g2, b2, a2) in zip(candidate, target):
        total += max(abs(r1 * a1 - r2 * a2), abs(g1 * a1 - g2 * a2), abs(b1 * a1 - b2 * a2)) / 255 + abs(a1 - a2)
    return total / max(1, len(target))


def derive_frame(hd, cod):
    """`hd` turned into CoD's look: (RGBA bytes at hd's size, chosen transform name, mean 1x error)."""
    small = _box_downscale(hd.pixels, hd.width, hd.height, cod.width, cod.height)
    target = [tuple(cod.pixels[i:i + 4]) for i in range(0, len(cod.pixels), 4)]
    rgb_pairs = [(min(round(c) for c in s[:3]), t[:3]) for s, t in zip(small, target) if s[3] > 128 and t[3] > 128]
    rgb = _table(rgb_pairs, 3) if rgb_pairs else None
    # CoD's alpha changes are proportional (opaque box art capped at 242; a 242 strip raised to 254), so alpha is
    # scaled by the median ratio where both frames are mostly opaque. A free per-value table would instead bend
    # antialiased edges toward CoD's 1x geometry (jagged timer wedges).
    ratios = sorted(t[3] / s[3] for s, t in zip(small, target) if s[3] > 128 and t[3] > 128)
    ratio = ratios[len(ratios) // 2] if ratios else 1
    alpha = [(min(255, a * ratio),) for a in range(256)]
    best = None
    for use_rgb in (False, True):
        if use_rgb and rgb is None:
            continue
        for use_alpha in (False, True):
            out = bytearray(hd.pixels)
            for i in range(0, len(out), 4):
                if use_rgb:
                    r, g, b = rgb[min(out[i], out[i + 1], out[i + 2])]
                    out[i], out[i + 1], out[i + 2] = round(r), round(g), round(b)
                if use_alpha:
                    out[i + 3] = round(alpha[out[i + 3]][0])
            err = _error(_box_downscale(out, hd.width, hd.height, cod.width, cod.height), target)
            name = ('recolour' if use_rgb else 'colours kept') + (', alpha table' if use_alpha else '')
            # A plain copy wins ties: only transform what CoD actually changed.
            if best is None or err < best[2] - 0.05:
                best = (bytes(out), name, err)
    return best


def derive_pack(cod_bytes, hd_bytes, frames=None):
    """(pack bytes, per-frame report): the HD pack's bytes with each literal frame replaced by its CoD version.
    `frames` maps HD frame -> CoD frame for packs that are numbered differently; only those frames change."""
    cod, hd = ImagePack.parse(cod_bytes), ImagePack.parse(hd_bytes)
    if frames is None:
        if len(cod.images) != len(hd.images):
            raise ValueError('CoD and SHS HD skin packs do not have the same frames')
        frames = {index: index for index in range(len(hd.images))}
    out, report = bytearray(hd_bytes), []
    for index, offset in enumerate(hd.pixel_offsets):
        if offset is None or index not in frames:
            continue                                     # generated from a literal frame, so it follows it
        pixels, name, err = derive_frame(hd.images[index], cod.images[frames[index]])
        argb = bytearray(len(pixels))
        argb[0::4], argb[1::4], argb[2::4], argb[3::4] = pixels[3::4], pixels[0::4], pixels[1::4], pixels[2::4]
        out[offset:offset + len(argb)] = argb
        report.append((index, name, round(err, 2)))
    return bytes(out), report


@lru_cache(maxsize=8)
def derived_pack(cod_bytes, hd_bytes):
    return derive_pack(cod_bytes, hd_bytes)[0]


# Common pack 126 frame -> SHS HD pack 155 frame drawing the same thing at 2x (legacy/findings.md, "Cause of Death
# HD common frames"): the Continue tabs, the 16 timer wedges, the portrait ring, the picker's selection rings and
# the gear. CoD recoloured all of them but the ring, which it shares with SHS; derivation keeps what it did not change.
COMMON_FRAMES = {3: 8, 4: 9, 5: 10, 6: 11, 37: 46, 43: 47, 44: 48, 49: 58, 50: 59}
COMMON_FRAMES.update({7 + wedge: 12 + wedge for wedge in range(16)})
# The widgets' white fill (0 -> 4) and the name-entry field's nine-piece outline (51-59 -> 60-68), exact 2x of
# CoD's; the corners fit at ~9.2 mean error (the wedges at 14-29), the rest exactly.
COMMON_FRAMES.update({0: 4, **{piece: piece + 9 for piece in range(51, 60)}})
# The quiz's running man (23-27 -> 28-32): the same five poses, SHS HD's blue turned to CoD's grey. Like the wedges they
# are not exact doubles (29x71 for 16x36), so they keep their own size; fit 21-47.
COMMON_FRAMES.update({23 + pose: 28 + pose for pose in range(5)})
# Frame 47, the bottom bar (identical in both games), is one 320x49 piece; SHS HD splits it into a 64x49-unit cap
# (55) and a 64x24 strip (56) stretched along the rest, starting 25 units down.
BAR_FRAME, BAR_CAP, BAR_STRIP, BAR_STRIP_TOP = 47, 55, 56, 25


# The menu windows' blue button (CoD pack 16, layout 70 / pressed 71: left cap, middle, right cap) -> SHS HD's pack 32
# (its layouts 70 / 71), exact doubles. The colour-keyed recolour (derive_frame) does not suit it: SHS HD's button has
# an inner bevel and a lighter gradient that CoD's flat-bordered one lacks, so shades that sit in different places in
# the two share a key, and it painted CoD's dark rim across the middle (bands and scratchy caps). These take CoD's
# colours by position instead (its frame upscaled) inside SHS HD's sharper outline (its alpha).
MENU_BUTTON_FRAMES = {90: 13, 91: 14, 92: 15, 93: 16, 94: 17, 95: 18}
# The same treatment for the menus' back arrow (pack 16 frame 89 -> pack 32 frame 12) and the Options rows' speakers
# (common pack 126 frames 45 / 46 -> 155 frames 53 / 54; the large one fits the colour-keyed recolour at only 44.9).
# All exact doubles.
MENU_ARROW_FRAMES = {89: 12}
SPEAKER_FRAMES = {45: 53, 46: 54}


def positional_menu_buttons(cod_bytes, hd_bytes):
    """The menu buttons and back arrow (pack 16 / SHS HD pack 32), as positional_frames gives them."""
    return positional_frames(cod_bytes, hd_bytes, tuple({**MENU_BUTTON_FRAMES, **MENU_ARROW_FRAMES}.items()))


@lru_cache(maxsize=4)
def positional_frames(cod_bytes, hd_bytes, pairs):
    """{CoD frame: (RGBA bytes, size)} at SHS HD's size for each (CoD frame, SHS HD frame) pair: CoD's colours,
    SHS HD's alpha."""
    from PIL import Image
    cod, hd = ImagePack.parse(cod_bytes), ImagePack.parse(hd_bytes)
    frames = {}
    for cod_index, hd_index in pairs:
        source, shape = cod.images[cod_index], hd.images[hd_index]
        colours = Image.frombytes('RGBA', (source.width, source.height), source.pixels).resize(
            (shape.width, shape.height), Image.BILINEAR)
        alpha = Image.frombytes('RGBA', (shape.width, shape.height), shape.pixels).split()[3]
        red, green, blue, _ = colours.split()
        frames[cod_index] = Image.merge('RGBA', (red, green, blue, alpha)).tobytes(), (shape.width, shape.height)
    return frames


@lru_cache(maxsize=2)
def derived_common(cod_bytes, hd_bytes):
    """SHS HD's pack 155 with each COMMON_FRAMES frame turned into CoD's look (other frames untouched). The gear is the
    exception (owner's choice, 2026-10-20, the approved mockup): CoD never changed the normal gear, so SHS HD's frame 58
    stays as it is, and the pressed gear is SHS HD's sharp frame 59 with CoD's grey-white glow (pressed_gear)."""
    frames = {hd: cod for cod, hd in COMMON_FRAMES.items() if hd not in (GEAR, GEAR_PRESSED)}
    out = bytearray(derive_pack(cod_bytes, hd_bytes, frames)[0])
    hd = ImagePack.parse(hd_bytes)
    _write_frame(out, hd, GEAR_PRESSED, pressed_gear(hd.images[GEAR_PRESSED], ImagePack.parse(cod_bytes).images[50]))
    return bytes(out)


GEAR, GEAR_PRESSED = 58, 59             # SHS HD pack 155's gear and pressed gear (CoD 126: 49 / 50)


def pressed_gear(hd_frame, cod_frame):
    """RGBA bytes: SHS HD's pressed gear (sharp, 2x) with its yellow glow replaced by CoD's own pressed gear scaled up.
    Each pixel blends toward CoD's by how saturated SHS HD's is (max - min of RGB, full at 150): the grey gear itself
    keeps SHS HD's pixels, the glow takes CoD's. The colour-keyed recolour (derive_frame) turned that glow into a
    banded, noisy outline."""
    from PIL import Image
    size = (hd_frame.width, hd_frame.height)
    cod = Image.frombytes('RGBA', (cod_frame.width, cod_frame.height), cod_frame.pixels).resize(
        size, Image.BICUBIC).tobytes()
    hd = hd_frame.pixels
    out = bytearray(len(hd))
    for i in range(0, len(hd), 4):
        r, g, b = hd[i], hd[i + 1], hd[i + 2]
        weight = min(1., (max(r, g, b) - min(r, g, b)) / 150)
        for c in range(4):
            out[i + c] = max(0, min(255, round((1 - weight) * hd[i + c] + weight * cod[i + c])))
    return bytes(out)


def _write_frame(out, pack, index, rgba):
    """Put RGBA bytes into `out` (a copy of `pack`'s bytes) as frame `index`, in the pack's own ARGB order."""
    offset = pack.pixel_offsets[index]
    argb = bytearray(len(rgba))
    argb[0::4], argb[1::4], argb[2::4], argb[3::4] = rgba[3::4], rgba[0::4], rgba[1::4], rgba[2::4]
    out[offset:offset + len(argb)] = argb
