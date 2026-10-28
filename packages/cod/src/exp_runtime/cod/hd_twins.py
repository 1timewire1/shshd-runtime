"""Cause of Death's backgrounds in HD, from the player's own SHS HD art (this fork).

Many of CoD's location pictures are SHS HD backgrounds at half size: the same picture, the same picture at other
levels, or SHS's picture edited (blurred, lit, desaturated, hazed) for CoD. The owner reviewed every pair
(cod-portrait-catalog/shs_hd_backgrounds.md, outside the project) and the reviewed ones ship as `hd_twin_map.py`:
fingerprints, sizes and where to look only, never a picture. `build` fills the CoD library's twin store from the
player's own files -- the SHS library's HD episodes and the linked SHS HD bundle -- under each CoD picture's
fingerprint, the way `hd_twins.build_from_map` does for SHS. Where CoD changed the picture, the change is fitted to
the player's own CoD picture and applied to the HD one (`apply_effect`), so the HD picture looks like CoD's:

- None: the HD picture as it is.
- 'levels': a per-channel gain and offset (CoD's art is mostly brighter than SHS HD's).
- ('blur', radius): a Gaussian blur, `radius` px at CoD's size, then 'levels'.
- ('local', saturation): optionally desaturated (ImageEnhance.Color), then a local levels transfer: a gain and offset
  per channel fitted over cells about an eighth of the picture wide and smoothed, so a glow or a haze carries over
  and the HD picture keeps its own detail.

CoD episodes then show the twin in place of their picture (`EpisodeResources.read_asset`: twins only, never the 2x
fill SHS's standard episodes get). Pillow only: the app has no numpy.
"""
import io
import json
import logging
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageMath

from ..hd_twins import fingerprint, image_size

CELL = .04              # the local transfer's cell, as a fraction of the CoD picture's width
EPSILON = 25.           # its variance floor: flat areas keep a gain near 0 rather than amplifying noise
JPEG_QUALITY = 95


def _product(a, b):
    """a * b for float images (ImageMath: `lambda_eval` from Pillow 10.3, `eval` before)."""
    if hasattr(ImageMath, 'lambda_eval'):
        return ImageMath.lambda_eval(lambda x: x['a'] * x['b'], a=a, b=b)
    return ImageMath.eval('a * b', a=a, b=b)                    # pragma: no cover (Pillow < 10.3)


def _gain_offset(a, gain, offset):
    """a * gain + offset for float images."""
    if hasattr(ImageMath, 'lambda_eval'):
        return ImageMath.lambda_eval(lambda x: x['a'] * x['g'] + x['o'], a=a, g=gain, o=offset)
    return ImageMath.eval('a * g + o', a=a, g=gain, o=offset)     # pragma: no cover (Pillow < 10.3)


def _float(channel):
    return channel.convert('F')


def _mean(image):
    """The mean of a float image."""
    return image.resize((1, 1), Image.BOX).getpixel((0, 0))


def _levels(source, target):
    """Per-channel (gain, offset) taking `source` to `target` (same size, RGB)."""
    fits = []
    for x, y in zip(source.split(), target.split()):
        fx, fy = _float(x), _float(y)
        mx, my = _mean(fx), _mean(fy)
        var = _mean(_product(fx, fx)) - mx * mx
        cov = _mean(_product(fx, fy)) - mx * my
        gain = cov / var if var > 1e-6 else 1.
        fits.append((gain, my - gain * mx))
    return fits


def _apply_levels(image, fits):
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


def _local(hd_small, cod, hd):
    """The local levels transfer: fitted between `hd_small` and `cod` (CoD's size), applied to `hd`."""
    width, height = cod.size
    cell = max(2, round(width * CELL))
    grid = (max(1, round(width / cell)), max(1, round(height / cell)))
    channels = []
    for x, y, full in zip(hd_small.split(), cod.split(), hd.split()):
        fx, fy = _float(x), _float(y)
        means = [image.resize(grid, Image.BOX) for image in
                 (fx, fy, _product(fx, fx), _product(fx, fy))]
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
            maps.append(image.resize(full.size, Image.BICUBIC))
        result = _gain_offset(_float(full), maps[0], maps[1])
        channels.append(result.convert('L'))
    return Image.merge('RGB', channels)


def _decode(data):
    image = Image.open(io.BytesIO(data))
    image.load()
    return image.convert('RGB')


def _encode(image):
    stream = io.BytesIO()
    image.save(stream, 'JPEG', quality=JPEG_QUALITY, subsampling=0)
    return stream.getvalue()


def recreate(cod_image, hd_image, effect):
    """`hd_image` (RGB) with `effect` fitted to `cod_image` (RGB); see the module docstring."""
    if effect is None:
        return hd_image
    small = hd_image.resize(cod_image.size, Image.LANCZOS)
    if effect == 'levels':
        return _apply_levels(hd_image, _levels(small, cod_image))
    kind, value = effect
    if kind == 'blur':
        scale = hd_image.width / cod_image.width
        blurred_small = small.filter(ImageFilter.GaussianBlur(value))
        return _apply_levels(hd_image.filter(ImageFilter.GaussianBlur(value * scale)),
                             _levels(blurred_small, cod_image))
    if kind == 'local':
        if value is not None:
            small, hd_image = (ImageEnhance.Color(image).enhance(value) for image in (small, hd_image))
        return _local(small, cod_image, hd_image)
    raise ValueError(f'Unknown HD background effect {effect!r}')


def apply_effect(cod_data, hd_data, effect):
    """The bytes to store for a CoD picture: the HD picture's own bytes when there is no effect, else the recreation
    as a JPEG."""
    if effect is None:
        return hd_data
    return _encode(recreate(_decode(cod_data), _decode(hd_data), effect))


# ---------------------------------------------------------------------------------------------------------- building

def _hd_sources(shs_library, cod_library):
    """Readers of SHS HD pictures: (by episode name and resource id, by bank id), from the SHS library (its HD
    episodes and HD bundle) and the CoD library's linked SHS HD bundle; either may be missing."""
    names = {}
    if shs_library is not None:
        for record in shs_library.episodes:
            names.setdefault(record.get('name'), record['id'])
    opened = {}

    def episode(name, resource_id):
        record_id = names.get(name)
        if record_id is None:
            return None
        try:
            if record_id not in opened:
                opened[record_id] = shs_library.open_episode(record_id).archive
            return opened[record_id].read(resource_id)
        except Exception:
            return None

    def bank(resource_id):
        for reader in (getattr(cod_library, 'shs_hd_resource', None),
                       getattr(shs_library, 'hd_raw_resource', None)):
            if reader is None:
                continue
            try:
                data = reader(resource_id)
            except Exception:
                data = None
            if data is not None:
                return data
        return None
    return episode, bank


def cod_pictures(cod_library, wanted):
    """{CoD fingerprint: bytes} for the `wanted` fingerprints, from the CoD library's bundle and episodes."""
    found = {}
    for resource_id in sorted(getattr(cod_library, 'base_members', ())):
        try:
            data = cod_library.android_asset(resource_id)
        except Exception:
            continue
        key = fingerprint(data)
        if key in wanted:
            found[key] = data
    for record in cod_library.episodes:
        if len(found) == len(wanted):
            break
        try:
            archive = cod_library.open_episode(record['id']).archive
        except Exception as error:
            logging.warning('CoD HD art: skipped %s: %s', record.get('name'), error)
            continue
        for resource_id in archive.entries:
            if resource_id < 26000:
                continue
            try:
                data = archive.read(resource_id)
            except Exception:
                continue
            key = fingerprint(data)
            if key in wanted and key not in found:
                found[key] = data
    return found


def scan_shs(shs_library, wanted):
    """{HD fingerprint: bytes} for the `wanted` fingerprints, from the SHS library's episodes (HD ones first)."""
    found = {}
    records = sorted(shs_library.episodes, key=lambda record: record.get('variant') != 'hd')
    for record in records:
        if len(found) == len(wanted):
            break
        try:
            archive = shs_library.open_episode(record['id']).archive
        except Exception as error:
            logging.warning('CoD HD art: skipped SHS %s: %s', record.get('name'), error)
            continue
        for resource_id in archive.entries:
            if resource_id < 26000:
                continue
            try:
                data = archive.read(resource_id)
            except Exception:
                continue
            key = fingerprint(data)
            if key in wanted and key not in found:
                found[key] = data
    return found


def shs_hd_episode_count(shs_library):
    return 0 if shs_library is None else sum(1 for r in shs_library.episodes if r.get('variant') == 'hd')


def shs_hd_episodes_listed(directory):
    """How many HD episodes an SHS library's manifest lists (0 without one): cheap enough for the UI thread."""
    try:
        manifest = json.loads((Path(directory) / 'library.json').read_text(encoding='utf-8'))
        return sum(1 for record in manifest.get('episodes', ()) if record.get('variant') == 'hd')
    except (OSError, ValueError, AttributeError):
        return 0


def due(cod_library, shs_hd_episodes, twin_map):
    """Whether the CoD library's store has to be (re)built: a new map, or a build that missed pictures while the SHS
    library has changed since (`shs_hd_episodes`, its HD episode count, differs: more episodes, or the library newly
    found)."""
    source = cod_library.twin_store().source()
    if source.get('map') != twin_map.VERSION:
        return True
    return bool(source.get('missing')) and source.get('shs_hd_episodes') != shs_hd_episodes


def build(cod_library, shs_library, twin_map, progress=None):
    """Fill the CoD library's twin store from the map (see the module docstring); returns how many pictures it holds
    afterwards. `shs_library` may be None (then only the bundle's pictures are found). `progress(done, total)` reports
    the pictures handled. Runs off the UI thread (the app's preview job)."""
    store = cod_library.twin_store()
    wanted = {key: entry for key, entry in twin_map.TWINS.items() if key not in store.index}
    cod = cod_pictures(cod_library, set(wanted)) if wanted else {}
    episode, bank = _hd_sources(shs_library, cod_library)
    hd_found = {}
    for key, (hd_key, _, _, _, hint) in wanted.items():
        if key not in cod or hd_key in hd_found:
            continue
        hd = episode(*hint[1:]) if hint[0] == 'episode' else bank(hint[1])
        if hd is not None and fingerprint(hd) == hd_key:
            hd_found[hd_key] = hd
    lost = {entry[0] for key, entry in wanted.items() if key in cod and entry[0] not in hd_found}
    if lost and shs_library is not None:
        hd_found.update(scan_shs(shs_library, lost))   # the hinted episode is not this player's: look in the rest
    pictures, missing = {}, 0
    for done, (key, (hd_key, width, height, effect, hint)) in enumerate(sorted(wanted.items())):
        if progress is not None:
            progress(done, len(wanted))
        cod_data = cod.get(key)
        if cod_data is None:
            continue                                    # this player's CoD does not have that picture
        hd = hd_found.get(hd_key)
        if hd is None:
            missing += 1
            continue
        try:
            pictures[key] = ((width, height), apply_effect(cod_data, hd, effect))
        except (OSError, ValueError) as error:
            logging.warning('CoD HD art: %s not recreated: %s', key, error)
            missing += 1
            continue
        if len(pictures) >= 8:                          # written as it goes: a long build keeps what it made
            store.add_pictures(pictures)
            pictures = {}
    if pictures:
        store.add_pictures(pictures)
    store.directory.mkdir(parents=True, exist_ok=True)
    (store.directory / 'source.json').write_text(json.dumps(
        {'map': twin_map.VERSION, 'missing': missing, 'shs_hd_episodes': shs_hd_episode_count(shs_library)}),
        encoding='utf-8')
    logging.info('CoD HD art: %d pictures in the store, %d not found', len(store.index), missing)
    return len(store.index)
