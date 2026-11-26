"""HD pictures recreated to match a standard picture's look (this fork): fitted from the two pictures the player
already has, so no art ships.

Cause of Death's backgrounds (cod/hd_twins.py) are SHS HD pictures that CoD blurred, lit, desaturated or hazed; SHS's
own standard episodes have a few pictures the HD release shows differently (34_Andy_Cannelloni_PI's noir scenes are
greyscale in the standard release and in colour in HD; a green-tinted hallway; a motion-blurred lab; a mirrored copy
of a portrait). The twin store keeps, for such a standard picture, the HD picture with the same change applied, so the
standard episode keeps its look at HD sharpness (owner, 2026-11-25).

SHS's effects (`apply`, the shipped map's optional fifth field):
- ('E',)       greyscale: the HD picture through the standard picture's own colour-to-grey mix (sharp detail), with the
               large-scale light of a local levels fit (`local`), which follows the original's brighter lighting.
- ('Ecolour',) the same for a picture tinted in colour (a blue-graded cave): the mix is a full colour matrix.
- ('F',)       a tinted monochrome (the green hallway): E's grey picture, each grey level given the standard picture's
               mean colour at that level.
- ('M', n)     a horizontal motion blur `n` px long at HD size (rounded to a power of two), then levels.
- ('MIRROR',)  the HD picture mirrored left to right (a standard episode that ships a mirrored copy of a portrait).

Pillow only: the app has no numpy.
"""
import io

from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageMath

CELL = .04              # the local transfer's cell, as a fraction of the standard picture's width
EPSILON = 25.           # its variance floor: flat areas keep a gain near 0 rather than amplifying noise
FIT_SIZE = (120, 180)   # the colour mixes are fitted on pictures this size (enough samples, quick in pure Python)
LIGHT = 1 / 12          # E's lighting: detail finer than this fraction of the width is the mix's, coarser the fit's
JPEG_QUALITY = 95


# -------------------------------------------------------------------------------------------- float image arithmetic

def _eval(function, **images):
    """`function` over float images (ImageMath: `lambda_eval` from Pillow 10.3, `eval` before)."""
    if hasattr(ImageMath, 'lambda_eval'):
        return ImageMath.lambda_eval(lambda x: function(**{key: x[key] for key in images}), **images)
    names = ', '.join(images)                                   # pragma: no cover (Pillow < 10.3)
    return ImageMath.eval(f'f({names})', f=function, **images)  # pragma: no cover


def product(a, b):
    return _eval(lambda a, b: a * b, a=a, b=b)


def gain_offset(a, gain, offset):
    return _eval(lambda a, g, o: a * g + o, a=a, g=gain, o=offset)


def _float(channel):
    return channel.convert('F')


def _mean(image):
    """The mean of a float image."""
    return image.resize((1, 1), Image.BOX).getpixel((0, 0))


# --------------------------------------------------------------------------------------------------- levels and local

def levels(source, target):
    """Per-channel (gain, offset) taking `source` to `target` (same size, RGB)."""
    fits = []
    for x, y in zip(source.split(), target.split()):
        fx, fy = _float(x), _float(y)
        mx, my = _mean(fx), _mean(fy)
        var = _mean(product(fx, fx)) - mx * mx
        cov = _mean(product(fx, fy)) - mx * my
        gain = cov / var if var > 1e-6 else 1.
        fits.append((gain, my - gain * mx))
    return fits


def apply_levels(image, fits):
    return Image.merge('RGB', [channel.point(lambda v, g=g, o=o: g * v + o)
                               for channel, (g, o) in zip(image.split(), fits)])


def _smooth(grid, width, height, passes=1):
    """A 3 x 3 mean over a small row-major grid, edges clamped."""
    for _ in range(passes):
        out = []
        for j in range(height):
            for i in range(width):
                total = count = 0
                for dj in (-1, 0, 1):
                    for di in (-1, 0, 1):
                        jj, ii = min(height - 1, max(0, j + dj)), min(width - 1, max(0, i + di))
                        total += grid[jj * width + ii]
                        count += 1
                out.append(total / count)
        grid = out
    return grid


def local(small, target, full):
    """The local levels transfer: a gain and offset per channel fitted over cells between `small` (the HD picture at the
    target's size) and `target`, smoothed, and applied to `full` (the HD picture at its own size)."""
    width, height = target.size
    cell = max(2, round(width * CELL))
    grid = (max(1, round(width / cell)), max(1, round(height / cell)))
    channels = []
    for x, y, whole in zip(small.split(), target.split(), full.split()):
        fx, fy = _float(x), _float(y)
        means = [image.resize(grid, Image.BOX) for image in (fx, fy, product(fx, fx), product(fx, fy))]
        mx, my, mxx, mxy = (list(image.getdata()) for image in means)
        gains, offsets = [], []
        for i in range(len(mx)):
            gain = (mxy[i] - mx[i] * my[i]) / (mxx[i] - mx[i] * mx[i] + EPSILON)
            gains.append(gain)
            offsets.append(my[i] - gain * mx[i])
        maps = []
        for values in (_smooth(gains, *grid), _smooth(offsets, *grid)):
            image = Image.new('F', grid)
            image.putdata(values)
            maps.append(image.resize(whole.size, Image.BICUBIC))
        channels.append(gain_offset(_float(whole), maps[0], maps[1]).convert('L'))
    return Image.merge('RGB', channels)


def local_fit(target, hd, saturation=None):
    """`hd` (RGB) relit to `target` (RGB, the standard picture) by `local`; desaturated first when `saturation` is given
    (0: grey)."""
    small = hd.resize(target.size, Image.LANCZOS)
    if saturation is not None:
        small, hd = (ImageEnhance.Color(image).enhance(saturation) for image in (small, hd))
    return local(small, target, hd)


# --------------------------------------------------------------------------------------------------------- the mixes

def _solve(matrix, vector):
    """Gaussian elimination with partial pivoting for a small dense system."""
    size = len(vector)
    rows = [list(row) + [value] for row, value in zip(matrix, vector)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda r: abs(rows[r][column]))
        rows[column], rows[pivot] = rows[pivot], rows[column]
        if abs(rows[column][column]) < 1e-9:
            rows[column][column] = 1e-9
        for r in range(size):
            if r != column:
                factor = rows[r][column] / rows[column][column]
                rows[r] = [a - factor * b for a, b in zip(rows[r], rows[column])]
    return [rows[i][size] / rows[i][i] for i in range(size)]


def mix(target, hd, channels):
    """Least-squares weights taking the HD picture's (R, G, B, 1) to the target's grey (channels 1) or to each of its
    R, G, B (channels 3), fitted at FIT_SIZE: [(r, g, b, offset)] per output channel."""
    source = list(hd.resize(FIT_SIZE, Image.LANCZOS).getdata())
    goal = target.resize(FIT_SIZE, Image.LANCZOS)
    goals = [list(goal.convert('L').getdata())] if channels == 1 else [list(band.getdata()) for band in goal.split()]
    normal = [[0.] * 4 for _ in range(4)]
    for r, g, b in source:
        x = (r, g, b, 1.)
        for i in range(4):
            for j in range(4):
                normal[i][j] += x[i] * x[j]
    weights = []
    for values in goals:
        rhs = [0.] * 4
        for (r, g, b), y in zip(source, values):
            rhs[0] += r * y
            rhs[1] += g * y
            rhs[2] += b * y
            rhs[3] += y
        weights.append(_solve(normal, rhs))
    return weights


def grey_mix(target, hd):
    """The HD picture in grey through the target's own colour-to-grey mix (as RGB)."""
    (weights,) = mix(target, hd, 1)
    return hd.convert('L', tuple(weights)).convert('RGB')


def colour_mix(target, hd):
    """The HD picture through the target's colour grade: each channel a mix of the HD picture's R, G and B."""
    matrix = tuple(value for weights in mix(target, hd, 3) for value in weights)
    return hd.convert('RGB', matrix)


def lighting(sharp, lit):
    """`sharp` with its large-scale brightness replaced by `lit`'s: sharp + blur(lit) - blur(sharp), so the detail is
    the sharp picture's and the light the other's."""
    radius = max(2, round(sharp.width * LIGHT))
    channels = []
    for s, a, b in zip(sharp.split(), lit.filter(ImageFilter.GaussianBlur(radius)).split(),
                       sharp.filter(ImageFilter.GaussianBlur(radius)).split()):
        channels.append(_eval(lambda s, a, b: s + a - b, s=_float(s), a=_float(a), b=_float(b)).convert('L'))
    return Image.merge('RGB', channels)


def tint(grey, target):
    """`grey` coloured by the target's mean colour at each grey level (a 256-entry lookup, gaps filled, smoothed)."""
    sums = [[0., 0., 0.] for _ in range(256)]
    counts = [0] * 256
    for (r, g, b), level in zip(target.getdata(), target.convert('L').getdata()):
        sums[level][0] += r
        sums[level][1] += g
        sums[level][2] += b
        counts[level] += 1
    filled = [i for i in range(256) if counts[i]]
    tables = []
    for c in range(3):
        known = {i: sums[i][c] / counts[i] for i in filled}
        values = []
        for i in range(256):
            if i in known:
                values.append(known[i])
                continue
            lower = max((k for k in filled if k < i), default=None)
            upper = min((k for k in filled if k > i), default=None)
            if lower is None or upper is None:
                values.append(known[upper if lower is None else lower])
            else:
                t = (i - lower) / (upper - lower)
                values.append(known[lower] * (1 - t) + known[upper] * t)
        padded = [values[0]] * 4 + values + [values[-1]] * 4
        tables.append([max(0, min(255, round(sum(padded[i:i + 9]) / 9))) for i in range(256)])
    level = grey.convert('L')
    return Image.merge('RGB', [level.point(table) for table in tables])


def motion(image, length):
    """A horizontal box blur `length` px long (rounded down to a power of two; wrapping at the edges)."""
    out = image
    step = 1
    while step * 2 <= max(1, length):
        out = ImageChops.add(out, ImageChops.offset(out, step, 0), scale=2.0)
        step *= 2
    return ImageChops.offset(out, -((step - 1) // 2), 0)        # centred on each pixel, as a box blur is


# ------------------------------------------------------------------------------------------------------------ shape

SHAPE_TOLERANCE = .03       # a background's HD picture whose shape differs more than this from its standard picture's


def misshapen(standard_size, hd_size):
    """Whether a background pair's HD picture has another shape than its standard picture (the Magic School cave:
    480 x 720 against an HD episode's own 768 x 1024), so drawn as HD art it would leave part of the frame black."""
    if not standard_size or not hd_size or max(standard_size) < 300:
        return False                                            # portraits have their own shapes and are fitted apart
    sx, sy = hd_size[0] / standard_size[0], hd_size[1] / standard_size[1]
    return abs(sx - sy) / max(sx, sy) > SHAPE_TOLERANCE


def cover(image, size):
    """`image` scaled evenly until it covers `size`, then cropped to it about the centre."""
    k = max(size[0] / image.width, size[1] / image.height)
    scaled = image.resize((max(size[0], round(image.width * k)), max(size[1], round(image.height * k))), Image.LANCZOS)
    left, top = (scaled.width - size[0]) // 2, (scaled.height - size[1]) // 2
    return scaled.crop((left, top, left + size[0], top + size[1]))


def fitted_bytes(data, standard_size):
    """An HD background's bytes in its standard picture's shape at twice its size (`cover`), as JPEG; `data` itself
    when the shapes already agree or the picture can't be read."""
    try:
        picture = _open(data)
    except (OSError, ValueError):
        return data
    if not misshapen(standard_size, picture.size):
        return data
    stream = io.BytesIO()
    cover(picture.convert('RGB'), (2 * standard_size[0], 2 * standard_size[1])).save(
        stream, 'JPEG', quality=JPEG_QUALITY, subsampling=0)
    return stream.getvalue()


# ------------------------------------------------------------------------------------------------------------ apply

def recreate(target, hd, effect):
    """`hd` with `effect` (see the module docstring) fitted to `target`, both PIL images; the result is RGB, or RGBA for
    a mirrored portrait."""
    kind = effect[0]
    if kind == 'MIRROR':
        return hd.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    target, hd = target.convert('RGB'), hd.convert('RGB')
    if kind == 'E':
        return lighting(grey_mix(target, hd), local_fit(target, hd, 0))
    if kind == 'Ecolour':
        return lighting(colour_mix(target, hd), local_fit(target, hd, None))
    if kind == 'F':
        return tint(lighting(grey_mix(target, hd), local_fit(target, hd, 0)), target)
    if kind == 'M':
        scale = target.width / hd.width
        small = motion(hd.resize(target.size, Image.LANCZOS), round(effect[1] * scale))
        return apply_levels(motion(hd, effect[1]), levels(small, target))
    raise ValueError(f'Unknown HD picture effect {effect!r}')


def _open(data):
    """A picture's bytes as a loaded PIL image: a PNG through `cgbi.decode` (the HD bundle's CgBI PNGs as well as
    ordinary ones), anything else (JPEG) through Pillow."""
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        from .cgbi import decode
        return decode(data)
    image = Image.open(io.BytesIO(data))
    image.load()
    return image


def apply(standard, hd, effect):
    """The bytes to store for a standard picture: the HD picture's own bytes without an effect, else the recreation (a
    JPEG for a background, a PNG for a picture with transparency)."""
    if not effect:
        return hd
    source, picture = _open(standard), _open(hd)
    if misshapen(source.size, picture.size):
        # The HD picture in the standard one's shape first, so the fit compares the same places (the cave).
        picture = cover(picture.convert('RGB'), (2 * source.width, 2 * source.height))
    keeps_alpha = effect[0] == 'MIRROR' and picture.mode in ('RGBA', 'LA', 'P')
    out = recreate(source, picture.convert('RGBA') if keeps_alpha else picture, effect)
    stream = io.BytesIO()
    if out.mode == 'RGBA':
        out.save(stream, 'PNG')
    else:
        out.convert('RGB').save(stream, 'JPEG', quality=JPEG_QUALITY, subsampling=0)
    return stream.getvalue()
