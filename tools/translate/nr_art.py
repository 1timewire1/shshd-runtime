"""New Rules art, pre-rendered for the SHS presentation: paper-doll portraits and location backgrounds.

Ported from the research decoders (reference/Other Games/tools: nr_decode.py, nr_portraits.py, nr_backgrounds.py);
the formats are in reference/Other Games/docs/SHS_NEW_RULES_ENGINE.md sections 3 and 5.

Sizes (the owner's decision 2: pixel-exact integer upscaling):
* portraits: the WinMo busts (about 50 x 65) doubled, about the size of a smartphone SD portrait (113 x 120); and the
  X1i jar's redrawn ones (about 1.5x) tripled (HIRES_PORTRAIT_SCALE), which the player takes as HD-sized art;
* backgrounds: the X1i jar's 360 x 120 strips times 6 = 2160 x 720, the height of an SHS background (480 x 720), so
  the strip pans by speaker side. Without the X1i jar, the WinMo 240 x 96 strips times 7 (672 high).
"""
from io import BytesIO
import struct
import zipfile
from pathlib import Path

from PIL import Image

from exp_runtime.exp import ExpArchive

PORTRAIT_SCALE = 2
HIRES_PORTRAIT_SCALE = 3
BACKGROUND_SCALE = {120: 6, 96: 7}
# o.java d[]: (PNG id, the colour behind indoor windows or -1) per location 0-28. Locations 4 and 5 are swapped.
LOCATIONS = [(5000, 860478), (5001, 7109535), (5002, -1), (5003, 6587046), (5005, 11232097), (5004, 14406236),
             (5006, 13206375), (5007, 12619081), (5008, 10074438), (5009, 7240591), (5010, 8280971), (5011, 12690538),
             (5012, 7375936), (5013, -1), (5014, 7517393), (5015, -1), (5016, -1), (5017, 9354079), (5018, -1),
             (5019, 7908764), (5020, -1), (5021, 6389914), (5022, 15910002), (5023, -1), (5024, 14318406), (5025, -1),
             (5026, 7310637), (5027, 1574662), (5028, -1)]
# The scene's sky by time-of-day mode (service 35's first argument), h.a in the Java build: top and bottom of an
# 8-band gradient over the top three quarters of the scene, then the ground colour. Mode 0 (day) adds the cloud strip,
# group 0 of image pack 4, 6 pixels down. The background picture goes over it, magenta transparent, so windows show the
# sky; a location's colour only fills the scene above a picture shorter than the scene (h.java, a(v, int, int, int,
# int, boolean, short, short, int, ...)).
SKY_MODES = ((0x99CCFF, 0x5EAEFE, 0x74726F), (0x29479F, 0x041138, 0x5D5B58), (0x8C9496, 0xB5CFC9, 0xA39898),
             (0xB38DCE, 0xFCFCB4, 0x655F64), (0xD53813, 0xF5B056, 0x7D674B), (0xEEEFF0, 0xC9C9CA, 0x8B7B77))
CLOUDS, CLOUD_WIDTH = 4, 357

# The UI backdrop New Rules draws behind its scene (h.java a(v, short) then the game-screen layout 2, h.c(v)): image
# pack 62 tiled over the screen, then the layout's stripe, pack 65's bars between pack 106's edge frames 10-12. The
# packs are greyscale, tinted by o.java's default colours (service 38 sets others; no download calls it). The X1i jar's
# IDs, then WinMo's (role table, SHS_NEW_RULES_ENGINE.md section 2.2). Layout image slots: 5 tile, 3 bars, 1 edges.
BACKDROP_PACKS = ((62, 65, 106), (56, 59, 99))
BACKDROP_TINTS = (15154, -166, -567)    # RGB565: blue #396594, cream #FFEBD6, orange #FFBA4A
BACKDROP_SLOTS = (5, 3, 1)
LAYOUT_BANK, GAME_LAYOUT = 2, 2
# The frame around New Rules' scene (h.java draws o.f, the edge pack 106 / WinMo 99 tinted orange, at the scene's
# corner; its group 0 for the full scene): 15-pixel bars of frame 0 just above and below the picture. Its sides lie
# past SHS's frame, which the panned strip always covers, so only the bars are drawn.
SCENE_FRAME_BAR, SCENE_FRAME_SIDE = 0, 9
# The stripe's share of the backdrop's width: 192 of WinMo's 240 pixels (X1i's is 290 of 480).
STRIPE_SHARE = 192 / 240
# Where the runtime centres a background: frame unit y = 32 + 180 + HD_BG_SHIFT[1] (player desktop.py).
STRIP_CENTRE_UNITS = 191.5
# SHS's frame (shshd-runtime's 384 x 512 units) and the width a background picture is shown at, in the same units.
FRAME_UNITS, BACKGROUND_UNITS = (384, 512), 480

MASK_BASE = 8126705 | 14
MASK_EXPR = (8448, 8448, 16896, 67584, 33792, 135168)
S = (11, 15, 17, 18, 12, 13, 16, 14, 24, 25, 26, 27, 28, 19, 20, 21, 22, 23, 29, 30, 10, 31, 32)
T = (0, 1, 3, 4, 1, 1, 2, 1, -1, -1, -1, -1, -1, 1, 1, 1, 1, 1, 6, 7, 0, 8, 9)
REGISTRY = [(1100, 15), (1200, 17), (1300, 4), (1400, 7), (1500, 6), (1600, 9), (1700, 18), (1800, 3), (1900, 3),
            (2000, 3), (2100, 3), (2200, 3), (2300, 1), (2400, 3), (2500, 2), (2600, 2), (2700, 2), (2800, 1),
            (2900, 2), (3000, 2), (3100, 17), (3200, 6), (3300, 2), (3400, 1), (3500, 12), (3600, 6), (3700, 9),
            (3800, 9), (3900, 10), (4000, 4), (8018, 29)]
TRANSFORMS = {0: [], 1: [Image.FLIP_TOP_BOTTOM], 2: [Image.FLIP_LEFT_RIGHT], 3: [Image.ROTATE_180],
              4: [Image.FLIP_LEFT_RIGHT, Image.ROTATE_90], 5: [Image.ROTATE_270], 6: [Image.ROTATE_90],
              7: [Image.FLIP_LEFT_RIGHT, Image.ROTATE_270]}


class Reader:
    def __init__(self, data, position=0):
        self.data, self.p = data, position

    def u8(self):
        value = self.data[self.p]; self.p += 1; return value

    def s8(self):
        value = struct.unpack_from('>b', self.data, self.p)[0]; self.p += 1; return value

    def s16(self):
        value = struct.unpack_from('>h', self.data, self.p)[0]; self.p += 2; return value

    def take(self, n):
        if self.p + n > len(self.data):
            raise ValueError('truncated image pack')
        value = self.data[self.p:self.p + n]; self.p += n; return value


def cmb0(data, resource):
    """A `CMB0` bundle's members: the Java form lists member IDs; BREW's numbers them resource + 1 + k."""
    n = data[4]
    head = 5 + 2 * n + 4 * (n + 1)
    if head <= len(data) and struct.unpack_from('>I', data, 5 + 2 * n)[0] == head:
        ids = [struct.unpack_from('>H', data, 5 + 2 * i)[0] for i in range(n)]
        starts = [struct.unpack_from('>I', data, 5 + 2 * n + 4 * i)[0] for i in range(n)]
    else:
        ids = [resource + 1 + k for k in range(n)]
        starts = [struct.unpack_from('>I', data, 5 + 4 * i)[0] for i in range(n)]
    starts.append(len(data))
    return {ids[i]: data[starts[i]:starts[i + 1]] for i in range(n)}


def load(source):
    """Resources by ID from New Rules' res_large.pud or a '09/'10 jar, CMB0 bundles opened."""
    source = Path(source)
    if source.suffix.lower() == '.jar':
        with zipfile.ZipFile(source) as jar:
            resources = {int(name): jar.read(name) for name in jar.namelist() if name.isdigit()}
    else:
        archive = ExpArchive(source.read_bytes())
        resources = {rid: archive.read(rid) for rid in archive.entries}
    for rid, data in list(resources.items()):
        if data[:4] == b'CMB0':
            for member, payload in cmb0(data, rid).items():
                resources.setdefault(member, payload)
    return resources


def palette_set(data, variant=0):
    r = Reader(data)
    variants, colours = r.u8(), r.u8(); r.u8()
    palette = bytearray(r.take(colours * 3))
    for v in range(1, variants):
        for _ in range(r.u8()):
            i, red, green, blue = r.take(4)
            if v == variant:
                palette[i * 3:i * 3 + 3] = bytes((red, green, blue))
    return bytes(palette)


class Pack:
    """A paletted image pack: frames (atlas cut, transformed copies) and groups."""

    def __init__(self, data, resources, variant=-1, tint=None):
        """`tint`: an RGB565 colour every palette entry is multiplied by (the greyscale UI packs; q.a(stream, tint))."""
        r = Reader(data)
        flags, nframes = r.u8(), r.s16()
        atlas = None
        if flags & 64:
            small = r.u8() != 0
            atlas = [r.u8() if small else r.s16() for _ in range(nframes * 4)]
        sequences = r.s8()
        if sequences > 0:
            r.s16(); r.s16()
            for _ in range(sequences):
                for _ in range(r.s8()):
                    r.s16() if flags & 4 else r.s8()
        ngroups = r.s16(); r.s16()
        self.groups = []
        for _ in range(ngroups):
            parts = []
            for _ in range(r.s8()):
                frame = r.s16() if flags & 1 else r.s8()
                dx, dy = (r.s16(), r.s16()) if flags & 2 else (r.s8(), r.s8())
                parts.append((frame, dx, dy))
            self.groups.append(parts)
        copies = [(r.s16(), r.s16(), r.u8()) for _ in range(r.s16())]
        if flags & 8:
            kind = r.u8()
            if kind == 1:
                palette = palette_set(resources[r.s16()], variant)
            elif kind == 2:
                start = r.p
                palette = palette_set(data[start:], variant)
                rr = Reader(data, start)
                nv, nc = rr.u8(), rr.u8(); rr.u8(); rr.p += nc * 3
                for _ in range(1, nv):
                    rr.p += 4 * rr.u8()
                r.p = rr.p
            else:
                raise ValueError(f'palette kind {kind}')
        else:
            palette = r.take(r.s16() * 3)
        if tint is not None:
            factors = rgb565(tint)
            palette = bytes(c * factors[i % 3] // 256 for i, c in enumerate(palette))
        images = []
        for _ in range(r.s16()):
            width = r.s16() if flags & 32 else r.u8()
            if width == 0:
                images.append(None)
                continue
            height = r.s16() if flags & 32 else r.u8()
            transparent = r.u8() == 1 if flags & 16 else True
            image = Image.frombytes('P', (width, height), r.take(width * height))
            image.putpalette(palette + bytes(768 - len(palette)))
            if transparent:
                image.info['transparency'] = 0
            images.append(image.convert('RGBA'))
        if atlas:
            sheet = images[0]
            self.frames = [sheet.crop((atlas[i * 4], atlas[i * 4 + 1], atlas[i * 4] + atlas[i * 4 + 2],
                                       atlas[i * 4 + 1] + atlas[i * 4 + 3])) for i in range(nframes)]
        else:
            self.frames = images + [None] * max(0, nframes - len(images))
            for source, destination, transform in copies:
                image = self.frames[source]
                if image is not None:
                    for operation in TRANSFORMS.get(transform, []):
                        image = image.transpose(operation)
                if destination < len(self.frames):
                    self.frames[destination] = image
                else:
                    self.frames.append(image)

    def draw(self, canvas, index, x, y, depth=0):
        if index < 0:
            if depth > 8 or -index - 1 >= len(self.groups):
                return
            for frame, dx, dy in self.groups[-index - 1]:
                self.draw(canvas, frame, x + dx, y + dy, depth + 1)
        elif index < len(self.frames) and self.frames[index] is not None:
            canvas.paste(self.frames[index], (x, y), self.frames[index])


def rgb565(colour):
    """o.java a(short): an RGB565 colour (a signed short) as 8-bit channels, low bits copied from the high ones."""
    colour &= 0xFFFF
    red, green, blue = colour >> 8 & 248, colour >> 3 & 252, colour << 3 & 248
    return red | red >> 5, green | green >> 6, blue | blue >> 5


def tile(canvas, image, rect, from_right=False, from_bottom=False):
    """q.a(v, frame, x, y, w, h, top, left): `image` repeated over `rect`, clipped to it, starting at its top-left
    corner, or its right / bottom edge."""
    x, y, w, h = rect
    if w <= 0 or h <= 0 or image is None:
        return
    fw, fh = image.size
    layer = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    for tx in range(w - fw, -fw, -fw) if from_right else range(0, w, fw):
        for ty in range(h - fh, -fh, -fh) if from_bottom else range(0, h, fh):
            layer.paste(image, (tx, ty), image)
    canvas.paste(layer, (x, y), layer)


def draw_layout(canvas, bank, layout_id, rect, slots):
    """w.java a(v, ...): a layout's visible nodes (flag 0x10) into `rect`: image nodes (kind 1: slot, frame) tiled over
    their rectangles, from the right with flag 0x40 and from the bottom with 0x80, and layout references (kind 7)
    drawn into theirs. Other kinds (colour fills, text areas) are skipped; the backdrop layouts have none visible."""
    from exp_runtime.ui_assets import Rect
    layout = bank.layouts[layout_id]
    for node in layout.nodes:
        if not node.flags & 16:
            continue
        child = node.rectangle(rect, (layout.width, layout.height))
        if node.kind == 1 and node.payload[0] in slots:
            frames = slots[node.payload[0]].frames
            frame = node.payload[1]
            if 0 <= frame < len(frames):
                tile(canvas, frames[frame], (child.x, child.y, child.width, child.height),
                     bool(node.flags & 64), bool(node.flags & 128))
        elif node.kind == 7:
            draw_layout(canvas, bank, node.payload[0], Rect(child.x, child.y, child.width, child.height), slots)


# Packs whose X1i copy has groups New Rules' own lacks, inserted before them: base -> New Rules' (WinMo, 240-wide Java)
# group count. The X1i jar's pack 1300 (collars) starts with a white collar, so the black suit collar, the necklace and
# the fur jacket are its groups 1-3; its own King of Diss asks for -1302..-1304 where the other builds ask for
# -1301..-1303. The downloads use New Rules' numbering, so drawing them from X1i art moves those parts up one.
NEW_RULES_GROUPS = {1300: 3}


def pack_of(part):
    n = -(part + 1) if part < 0 else part
    return next((base for base, count in REGISTRY if base <= n <= base + count - 1), None)


class Art:
    def __init__(self, portraits, backgrounds=None):
        """`portraits`: resources holding the part packs (res_large.pud); `backgrounds`: the X1i jar's, if any."""
        self.portraits, self.backgrounds = portraits, backgrounds or portraits
        self._packs = {}

    def pack(self, base, variant):
        key = (base, variant)
        if key not in self._packs:
            self._packs[key] = Pack(self.portraits[base], self.portraits, variant)
        return self._packs[key]

    def portrait(self, slots, expression):
        """A look (33 slots) drawn with one expression (0-5), cropped to its pixels, at the portrait scale."""
        mask = MASK_BASE | MASK_EXPR[expression]
        canvas = Image.new('RGBA', (400, 520), (0, 0, 0, 0))
        ox, oy = 200, 512
        for layer in range(23):
            if not mask & 1 << layer:
                continue
            part = slots[S[layer]]
            base = pack_of(part) if part != -1 else None
            if base is None or base not in self.portraits:
                continue
            if 8 <= layer <= 12:
                variant = slots[5] if base == 3500 else slots[1] if base == 3600 else -1
            else:
                variant = slots[T[layer]] if T[layer] != -1 else -1
            pack = self.pack(base, variant)
            index = part + base if part < 0 else part - base
            if index < 0 and base in NEW_RULES_GROUPS:
                index -= max(0, len(pack.groups) - NEW_RULES_GROUPS[base])      # NEW_RULES_GROUPS: X1i's extra ones
            pack.draw(canvas, index, ox, oy)
        return canvas

    def portrait_bank(self, slots, expressions, scale=PORTRAIT_SCALE):
        """Five pictures for SHS expression slots 0-4, each the New Rules expression `expressions[k]`, all on one
        canvas size (the union of their drawn pixels) so the bust doesn't jump between expressions; `scale` times."""
        pictures = [self.portrait(slots, e) for e in expressions]
        boxes = [p.getbbox() for p in pictures if p.getbbox()]
        if not boxes:
            return [Image.new('RGBA', (1, 1)) for _ in pictures]
        box = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
        size = ((box[2] - box[0]) * scale, (box[3] - box[1]) * scale)
        return [p.crop(box).resize(size, Image.NEAREST) for p in pictures]

    def clouds(self):
        """The cloud pack (the X1i jar's resource 4), or None where the background source has no such pack."""
        if not hasattr(self, '_clouds'):
            try:
                self._clouds = Pack(self.backgrounds[CLOUDS], self.backgrounds)
            except (KeyError, ValueError, struct.error):
                self._clouds = None
        return self._clouds

    def background(self, location, mode=0):
        """Location 0-28 in time-of-day mode 0-5 as an opaque picture, drawn as New Rules draws its scene (SKY_MODES)
        with the picture's height as the scene's: sky, clouds by day, then the picture with magenta transparent."""
        png_id, _ = LOCATIONS[location]
        image = Image.open(BytesIO(self.backgrounds[png_id])).convert('RGBA')
        width, height = image.size
        top, bottom, ground = SKY_MODES[mode if 0 <= mode < len(SKY_MODES) else 0]
        rgb = lambda c: (c >> 16 & 255, c >> 8 & 255, c & 255)
        fill = Image.new('RGBA', image.size, rgb(ground) + (255,))
        sky = height * 75 // 100
        for band in range(8):        # h.java: eight bands; band k is drawn before the colour steps to k/7, so k-1
            step = max(0, band - 1)
            colour = tuple(a + int(step * (b - a) / 7) for a, b in zip(rgb(top), rgb(bottom)))
            fill.paste(colour + (255,), (0, band * sky // 8, width, (band + 1) * sky // 8))
        clouds = self.clouds() if mode == 0 else None
        if clouds is not None:
            for x in range(0, width, CLOUD_WIDTH):
                clouds.draw(fill, -1, x, 6)
        pixels = image.load()
        mask = Image.new('L', image.size, 255)
        mask_pixels = mask.load()
        for y in range(height):
            for x in range(width):
                if pixels[x, y][:3] == (255, 0, 255):
                    mask_pixels[x, y] = 0
        fill.paste(image, (0, 0), mask)
        scale = BACKGROUND_SCALE.get(height, 720 // height)
        return fill.convert('RGB').resize((width * scale, height * scale), Image.NEAREST)

    def backdrop(self):
        """New Rules' UI backdrop (BACKDROP_PACKS) cut to SHS's frame, or None where the background source lacks it.

        It is drawn at the backgrounds' own density and scale: a background strip is shown BACKGROUND_UNITS wide, so
        the frame is FRAME_UNITS times (strip width / BACKGROUND_UNITS) art pixels. The pattern fills it; the game
        screen's stripe (layout 2's child) runs down its middle, STRIPE_SHARE of its width as on WinMo's screen, with
        its bars between the scene frame's thinner side pieces (SCENE_FRAME_SIDE) instead of its own 30-pixel edges
        (the owner's choice). The scene frame's bars (SCENE_FRAME_BAR) go just above and below where the runtime shows
        the strip."""
        from exp_runtime.ui_assets import LayoutBank, Rect, UIAssetError
        source = self.backgrounds
        ids = next((ids for ids in BACKDROP_PACKS if all(i in source for i in ids)), None)
        if ids is None or LAYOUT_BANK not in source:
            return None
        try:
            bank = LayoutBank.parse(source[LAYOUT_BANK])
            packs = [Pack(source[i], source, tint=t) for i, t in zip(ids, BACKDROP_TINTS)]
            stripe_id = next(node.payload[0] for node in bank.layouts[GAME_LAYOUT].nodes
                             if node.kind == 7 and node.flags & 16)
            stripe_layout = bank.layouts[stripe_id]
            # where the stripe's bars start inside it, past its own edge pieces
            inset = min(node.base[0] for node in stripe_layout.nodes
                        if node.kind == 1 and node.payload[0] == BACKDROP_SLOTS[1])
        except (ValueError, KeyError, IndexError, StopIteration, struct.error, UIAssetError):
            return None
        strip = Image.open(BytesIO(source[LOCATIONS[0][0]]))
        units = strip.width / BACKGROUND_UNITS
        width, height = round(FRAME_UNITS[0] * units), round(FRAME_UNITS[1] * units)
        canvas = Image.new('RGBA', (width, height), (0, 0, 0, 255))
        tile(canvas, packs[0].frames[0], (0, 0, width, height))
        stripe = round(width * STRIPE_SHARE)
        left = (width - stripe) // 2
        frames = packs[2].frames
        side = frames[SCENE_FRAME_SIDE] if SCENE_FRAME_SIDE < len(frames) else None
        edge = side.width if side is not None else 0
        draw_layout(canvas, bank, stripe_id, Rect(left + edge - inset, 0, stripe - 2 * (edge - inset), height),
                    {BACKDROP_SLOTS[1]: packs[1]})
        if side is not None:
            tile(canvas, side, (left, 0, edge, height))
            tile(canvas, side, (left + stripe - edge, 0, edge, height))
        scale = BACKGROUND_SCALE.get(strip.height, 720 // strip.height)
        image = canvas.convert('RGB').resize((width * scale, height * scale), Image.NEAREST)
        bar = frames[SCENE_FRAME_BAR] if SCENE_FRAME_BAR < len(frames) else None
        if bar is not None:
            bar = bar.resize((bar.width * scale, bar.height * scale), Image.NEAREST)
            pixels = units * scale                                          # backdrop pixels per frame unit
            half = strip.height * BACKGROUND_UNITS / strip.width / 2        # half the strip's height, in units
            top = round((STRIP_CENTRE_UNITS - half) * pixels)
            bottom = round((STRIP_CENTRE_UNITS + half) * pixels)
            tile(image, bar, (0, top - bar.height, image.width, bar.height))
            tile(image, bar, (0, bottom, image.width, bar.height))
            # One art pixel more of each bar's inner edge, under the strip, so scaling never opens a seam.
            tile(image, bar.crop((0, bar.height - scale, bar.width, bar.height)), (0, top, image.width, scale))
            tile(image, bar.crop((0, 0, bar.width, scale)), (0, bottom - scale, image.width, scale))
        return image


def png(image):
    out = BytesIO()
    image.save(out, format='PNG', optimize=True)
    return out.getvalue()


def jpeg(image):
    out = BytesIO()
    image.save(out, format='JPEG', quality=92)
    return out.getvalue()
