"""The Java '08 demo's art for the BREW stories' "Java '08 Look" (SHS_BREW_PLAN.md, Stage 2d), read from the demo's jar when the
shsbrew addon is built (brew.build_addon). Nothing from the jar is kept in the repository.

The jar's numbered resources are CMB0 bundles (n, n ids, n+1 absolute offsets). Pictures are Java's own format (decompile:
q.a(InputStream, ...) and i.java): a sheet header (frames, animations, composites), then a pixel block of a palette and
8-bit images whose index 0 is transparent. Fonts are a short header (spacing, the character count and height, the
characters), then the same pixel block, one picture per character. See reference/Other Games/docs/SHS_08_JAVA.md.
"""
import io
import struct
import zipfile

from PIL import Image

UI_SHEET = 8018                         # tiles, box pieces, name bar, heart, skull, smiley, arrows...
SMALL_PICTURES = [8093 + k for k in range(29)] + [8123 + k for k in range(27)]   # d.java's table c: Java's 56 small pictures
OUTLINED_FONT = 5                       # white capitals with a black edge: the catch game's SCORE and its end panel
TILE, BAR = 4, 24                       # 8018's "SHS" tile and the name bar's straight piece
HEART, SKULL, SMILEY = 17, 49, 50       # 8018's relationship icons, 13 pixels
CREAM, FIELD = (255, 235, 211), (162, 198, 239)     # the catch screen's border and field (l.java: 16772308, 10667759)
BAR_FILL, BAR_BACK = (248, 200, 0), (255, 255, 255)


def resources(jar):
    """{resource ID: bytes} of the jar's numbered members, bundles opened."""
    out = {}
    with zipfile.ZipFile(jar) as archive:
        for name in archive.namelist():
            if not name.isdigit():
                continue
            data = archive.read(name)
            if data[:4] != b'CMB0':
                out[int(name)] = data
                continue
            n = data[4]
            ids = struct.unpack_from('>' + 'H' * n, data, 5)
            at = 5 + 2 * n
            offsets = list(struct.unpack_from('>' + 'I' * (n + 1), data, at))
            if offsets[0] != at + 4 * (n + 1):          # some bundles give n offsets
                offsets = list(struct.unpack_from('>' + 'I' * n, data, at)) + [len(data)]
            for k in range(n):
                out[ids[k]] = data[offsets[k]:offsets[k + 1]]
    return out


def pixel_block(data, at=0):
    """(images, end) of a pixel block at `at`: u16 palette size, RGB each, u16 count, then per image u8 width, u8 height and
    its palette indexes."""
    n = struct.unpack_from('>H', data, at)[0]; at += 2
    palette = [tuple(data[at + 3 * k:at + 3 * k + 3]) for k in range(n)]; at += 3 * n
    count = struct.unpack_from('>H', data, at)[0]; at += 2
    images = []
    for _ in range(count):
        w, h = data[at], data[at + 1]; at += 2
        image = Image.new('RGBA', (w, h))
        image.putdata([(0, 0, 0, 0) if c == 0 else palette[c] + (255,) for c in data[at:at + w * h]])
        images.append(image)
        at += w * h
    return images, at


def sheet(data):
    """The frames of a picture sheet (i.java): its header skipped, its pixel block read."""
    flags, at = data[0], 1
    at += 2                                             # frame count
    animations = data[at]; at += 1
    if animations:
        at += 4
        for _ in range(animations):
            count = data[at]; at += 1
            at += count * (2 if flags & 4 else 1)
    composites = struct.unpack_from('>h', data, at)[0]; at += 4
    for _ in range(composites):
        count = data[at]; at += 1
        at += count * ((2 if flags & 1 else 1) + (4 if flags & 2 else 2))
    return pixel_block(data, at)[0]


def font(data):
    """({character: picture}, space width, step) of a Java font: the space's width, a line gap, the step between letters
    (signed: -2, their outlines overlapping), the count, the height, the characters, then the pixel block."""
    space, gap, count = data[0], struct.unpack_from('>b', data, 2)[0], data[4]
    characters = data[6:6 + count].decode('latin-1')
    glyphs = pixel_block(data, 6 + count)[0]
    return dict(zip(characters, glyphs)), space, gap


def text(found, string):
    """`string` in a Java font (its capitals are its lower-case letters)."""
    glyphs, space, gap = found
    widths = [space if c == ' ' else glyphs[c.lower()].width for c in string]
    height = max(g.height for g in glyphs.values())
    image = Image.new('RGBA', (max(1, sum(widths) + gap * (len(string) - 1) + max(0, -gap)), height), (0, 0, 0, 0))
    x = 0
    for c, width in zip(string, widths):
        if c != ' ':
            image.alpha_composite(glyphs[c.lower()], (x, height - glyphs[c.lower()].height))
        x += width + gap
    return image


def pairs(brew_pictures):
    """{BREW picture ID: Java small picture index}: the k-th of BREW's 56 small pictures (IDs 100-180 in order) is Java's
    k-th, but at the end: Java 54 is a startled face BREW doesn't have, and its 55 is BREW's zombie (165); BREW's house (166)
    has no Java copy."""
    ids = sorted(brew_pictures)
    found = {picture: k for k, picture in enumerate(ids[:54])}
    if 165 in ids:
        found[165] = 55
    return found


def small_picture(jar_resources, index):
    return Image.open(io.BytesIO(jar_resources[SMALL_PICTURES[index]])).convert('RGBA')


def backdrop(frames, size, strip_top, strip_bottom, scale):
    """Java's look for the frame around a BREW strip: its "SHS" tile everywhere, and its name bar's straight piece just above and
    below the strip (where BREW's look has its yellow bar), the upper one turned over. Art pixels at the strip's density (one
    Java pixel to one BREW pixel), then `scale` times with no smoothing. `strip_top` and `strip_bottom` are in the scaled
    picture."""
    width, height = size
    canvas = Image.new('RGBA', (width, height), (0, 0, 0, 255))
    tile = frames[TILE]
    for x in range(0, width, tile.width):
        for y in range(0, height, tile.height):
            canvas.alpha_composite(tile, (x, y))
    image = canvas.resize((width * scale, height * scale), Image.NEAREST)
    bar = frames[BAR]
    band = Image.new('RGBA', (image.width // scale + bar.width, bar.height), (0, 0, 0, 0))
    for x in range(0, band.width, bar.width):
        band.alpha_composite(bar, (x, 0))
    band = band.resize((band.width * scale, band.height * scale), Image.NEAREST)
    image.alpha_composite(band.transpose(Image.FLIP_TOP_BOTTOM), (0, max(0, strip_top - band.height)))
    image.alpha_composite(band, (0, strip_bottom))
    return image.convert('RGB')


def catch_frame(frames, header_height=26):
    """Java's catch screen at BREW's 240 x 320 (its layout l.java d(Graphics); measured on its 176 x 220 screen): a cream
    border, a blue header with rounded top corners (solid light blue, then the name bar's gradient piece along its foot,
    as Java's has), and the light-blue field."""
    image = Image.new('RGBA', (240, 320), CREAM + (255,))
    bar = frames[BAR]
    top = bar.getpixel((bar.width // 2, 0))
    image.paste(top, (2, 3, 238, 3 + header_height - bar.height))
    for x in range(2, 238, bar.width):
        image.alpha_composite(bar.crop((0, 0, min(bar.width, 238 - x), bar.height)), (x, 3 + header_height - bar.height))
    for corner, x in ((frames[10], 2), (frames[11], 233)):            # its top corners (8 and 9 are the bottom's)
        image.alpha_composite(corner, (x, 3))
    image.paste(FIELD + (255,), (2, 3 + header_height, 238, 318))
    return image


def finished_panel(found, label='Minigame finished!'):
    """Java's end panel (l.java: string 53 on layout 27), a rounded blue box with the words in its outlined font."""
    words = text(found, label)
    width, height = words.width + 24, words.height + 16
    image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=7, fill=(54, 132, 219, 255), outline=(31, 52, 137, 255))
    draw.rounded_rectangle((2, 2, width - 3, height - 3), radius=5, outline=(97, 166, 244, 255))
    image.alpha_composite(words, ((width - words.width) // 2, (height - words.height) // 2))
    return image
