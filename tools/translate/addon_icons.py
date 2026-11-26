"""shshd-runtime: the add-on games' picker icons (owner, 2026-11-21; ROADMAP 3.31): each translated game's icon, packed in
its add-on now so that a game chooser listing the add-on games later needs no add-on update.

Resources (free in every add-on; checked 2026-11-21):
- 26950, the spec (JSON): {"version": 1, "games": [{"key", "title", "icon", "smooth", ["edition"]}, ...]}, a game per
  entry: `key` the game's tag ('nr', 'brew07', 'brew08', 'shs11', 'shw', 'x360'), `title` its name for the chooser,
  `icon` the resource of its picture, `smooth` false for pixel art (scaled nearest), `edition` where one add-on holds
  two games (BREW's '07 and '08, as the Title Screen Looks tell them apart).
- 26951 on: the pictures, square PNGs at their source size (the chooser scales them to its icon size).

The pictures come from the player's own files and the owner's reference folder (Web Archive store art), never shipped
with this project: see ICONS for each game's source (owner's picks, 2026-11-21).

Usage:
    addon_icons.py patch IN.exp OUT.exp [--reference OTHER_GAMES]   add the icon records to a built add-on and raise its
                                                                    revision by one (every other record kept as it is)
    addon_icons.py preview OUT_FOLDER [--reference OTHER_GAMES]     write each game's icon as a PNG
Builders call `icon_resources(addon_id)` to put the same records in a fresh build.
"""
import argparse
import io
import json
import sys
import zipfile
from pathlib import Path

from PIL import Image

SPEC_ID, FIRST_ICON = 26950, 26951
SPEC_VERSION = 1
REFERENCE = Path(__file__).resolve().parents[3] / 'reference' / 'Other Games'
EA = Path('Additional Resources') / 'EA Mobile store art (Wayback)'
VIVENDI = Path('Additional Resources') / 'Vivendi Games Mobile art (Wayback)'
X360_GUI = Path('Surviving High School (Cancelled X360 Game) - extracted') / 'MS4-20090526' / 'data' / 'art' / 'gui'


def _load(path):
    return Image.open(path).convert('RGBA')


def _square(image, box=None):
    """A square crop: `box` (left, top, side) or the centred largest square."""
    if box is None:
        side = min(image.size)
        box = ((image.width - side) // 2, (image.height - side) // 2, side)
    left, top, side = box
    return image.crop((left, top, left + side, top + side))


def _jar_member(folder, pattern, member):
    jar = next(folder.glob(pattern))
    with zipfile.ZipFile(jar) as archive:
        return Image.open(io.BytesIO(archive.read(member))).convert('RGBA')


def _masked(gui, picture, mask, colour=None):
    alpha = Image.open(gui / mask).convert('L')
    image = Image.new('RGBA', alpha.size, colour) if colour else Image.open(gui / picture).convert('RGBA')
    image.putalpha(alpha)
    return image.crop(image.getbbox())


def _fit_width(image, width):
    return image.resize((round(width), round(image.height * width / image.width)), Image.LANCZOS)


def _x360_icon(reference, size=512, out=256):
    """The prototype has no icon: its title logo and the logo's black splat on its rayed sky (MS4's title art)."""
    gui = reference / X360_GUI
    sky = Image.open(gui / 'background.jpg').convert('RGBA').crop((0, 0, 1024, 1024)).resize((size, size), Image.LANCZOS)
    logo = _fit_width(_masked(gui, 'logo.jpg', 'logo_a.jpg'), size * 0.84)
    splat = _fit_width(_masked(gui, None, 'stain_a.jpg', (10, 10, 14, 255)), size * 0.84 * 1.18)
    block = Image.new('RGBA', (splat.width, max(splat.height, logo.height) + 10), (0, 0, 0, 0))
    block.alpha_composite(splat, (0, (block.height - splat.height) // 2))
    block.alpha_composite(logo, ((block.width - logo.width) // 2, (block.height - logo.height) // 2))
    sky.alpha_composite(block, ((size - block.width) // 2, (size - block.height) // 2))
    return sky.resize((out, out), Image.LANCZOS)


CLASSIC = Path('Claire Hart Classic')                         # the Pogo mirrors (claire_hart.py, claire_hart_shadows.py)
SHADOWS = Path('Claire Hart Secret in the Shadows')
SHADOWS_ELSEWHERE = Path('D:/SHSHD/reference/Other Games')     # where the owner keeps the sequel's mirror (2026-11-20)


def _mirror_picture(root, real_path):
    """A picture of a Pogo mirror by its game path (bundle_names.csv: several local files can carry one name)."""
    import csv
    with open(root / 'bundle_names.csv', encoding='utf-8-sig', newline='') as file:
        for row in csv.DictReader(file):
            if row['real_path'] == real_path:
                try:
                    image = Image.open(root / row['local_path'])
                    image.load()
                    return image.convert('RGBA')
                except OSError:
                    continue
    raise FileNotFoundError(f'{real_path} in {root}')


def _centre_square(image):
    side = min(image.size)
    return image.crop(((image.width - side) // 2, (image.height - side) // 2,
                       (image.width + side) // 2, (image.height + side) // 2))


def _chc_icon(reference, size=256):
    """Claire Hart Classic (owner, 2026-11-25): its title logo (Claire and Paul over the gem banner, as `chc`'s Title
    Screen Look has it) centred on its teal loading backdrop (`chc`'s frame backdrop)."""
    root = reference / CLASSIC
    logo = _load(root / 'raw/157/assets/resources/native/17/170baf746.png').crop((3, 3, 459, 384))
    logo = logo.crop(logo.getbbox())
    icon = _centre_square(_mirror_picture(root, 'textures/new/loadingscreen_bg16_9')).resize((size, size), Image.LANCZOS)
    logo = _fit_width(logo, size * 0.9) if logo.width >= logo.height else logo.resize(
        (round(logo.width * size * 0.9 / logo.height), round(size * 0.9)), Image.LANCZOS)
    icon.alpha_composite(logo, ((size - logo.width) // 2, (size - logo.height) // 2))
    return icon


def _ch2_icon(reference, size=256):
    """Claire Hart: Secret in the Shadows (owner, 2026-11-25): Claire's own portrait (her sd normal face, head to waist)
    centred on the episode select's violet backdrop (`ch2`'s frame backdrop)."""
    root = reference / SHADOWS if (reference / SHADOWS).is_dir() else SHADOWS_ELSEWHERE / SHADOWS
    claire = _mirror_picture(root, 'references/characters/Avatar_ClaireHart/sd/avatar_clairehart_normal')
    claire = claire.crop(claire.getbbox())
    icon = _centre_square(_mirror_picture(root, 'textures/SD/episodeSelector/episodeselector_bg')).resize(
        (size, size), Image.LANCZOS)
    k = size * 0.96 / max(claire.size)
    claire = claire.resize((round(claire.width * k), round(claire.height * k)), Image.LANCZOS)
    icon.alpha_composite(claire, ((size - claire.width) // 2, size - claire.height))
    return icon


# Each game: (key, chooser title, how its icon is made from the reference folder, smooth, edition). Owner's picks 2026-11-21.
ICONS = {
    'shsnr': [('nr', 'Surviving High School: New Rules',
               lambda r: _square(_load(r / EA / 'product-thumbnail_shsnr.jpg')), True, None)],          # EA's store thumbnail
    'shsbrew': [('brew07', "Surviving High School '07",                                                # Centerscore's box
                 lambda r: _square(_load(r / 'Additional Resources' / "Surviving High School '07 (mobile)" / '92046_front.jpg'),
                                   (0, 0, 150)), True, '07'),
                ('brew08', "Surviving High School '08",
                 lambda r: _square(_load(r / EA / 'product-thumbnail_SHS.jpg')), True, '08')],          # EA's store thumbnail
    'shs11': [('shs11', "Surviving High School '11",                                                    # its own app icon
               lambda r: _jar_member(r / "Surviving High School '11 (Java)", '*480x800_173360.jar', 'icon.png'), True, None)],
    'shshw': [('shw', 'Surviving Hollywood',                                                             # Vivendi's banner
               lambda r: _square(_load(r / VIVENDI / 'bannerhollywood.jpg'), (6, 10, 178)), True, None)],
    'shsx360': [('x360', 'Surviving High School (Xbox 360 prototype)', _x360_icon, True, None)],
    # Cause of Death's Claire Hart add-ons (owner, 2026-11-25): its title logo, and Claire on the sequel's violet.
    'chc': [('chc', 'Claire Hart Classic', _chc_icon, True, None)],
    'ch2': [('ch2', 'Claire Hart: Secret in the Shadows', _ch2_icon, True, None)],
}


def _png(image):
    out = io.BytesIO()
    image.save(out, 'PNG', optimize=True)
    return out.getvalue()


def icon_resources(addon_id, reference=REFERENCE):
    """{resource: bytes} of `addon_id`'s picker icons (spec at SPEC_ID, pictures from FIRST_ICON), or {} for an add-on with
    none. Raises FileNotFoundError without the reference files."""
    games = ICONS.get(addon_id)
    if not games:
        return {}
    resources, entries = {}, []
    for number, (key, title, make, smooth, edition) in enumerate(games):
        resource = FIRST_ICON + number
        resources[resource] = _png(make(Path(reference)))
        entry = dict(key=key, title=title, icon=resource, smooth=smooth)
        if edition:
            entry['edition'] = edition
        entries.append(entry)
    resources[SPEC_ID] = json.dumps(dict(version=SPEC_VERSION, games=entries), sort_keys=True).encode('utf-8')
    return resources


def add_icons(resources, addon_id, reference=None):
    """A builder's step: put `addon_id`'s icon records in `resources` (a dict of the add-on's records). Without the
    reference folder (REFERENCE, read at the call: tests point it elsewhere) it leaves them out quietly, and with a file
    of it missing it warns, so an add-on built elsewhere still builds (without its icon)."""
    reference = Path(REFERENCE if reference is None else reference)
    if not reference.is_dir():
        return
    try:
        resources.update(icon_resources(addon_id, reference))
    except (FileNotFoundError, StopIteration) as error:
        print(f'warning: {addon_id} built without its picker icon ({error}); see addon_icons.py', file=sys.stderr)


def read_spec(data):
    """The icon spec's games, checked: [{key, title, icon, smooth, edition?}, ...]. Raises ValueError."""
    spec = json.loads(data)
    if spec.get('version') != SPEC_VERSION or not isinstance(spec.get('games'), list) or not spec['games']:
        raise ValueError('not an add-on icon spec')
    for game in spec['games']:
        if not isinstance(game.get('key'), str) or not isinstance(game.get('icon'), int):
            raise ValueError('an icon entry needs a key and an icon resource')
    return spec['games']


def patch(source, target, reference=REFERENCE):
    """Write `source` (a built add-on) to `target` with its icon records and its revision raised by one. Returns
    (addon id, old revision, new revision)."""
    sys.path[:0] = [str(Path(__file__).resolve().parents[2] / 'packages' / 'formats' / 'src')]
    from exp_runtime.addons import RESOURCE as ADDON_RECORD, addon_record, provides_bytes
    from exp_runtime.exp import LazyExpArchive, encode_exp
    archive = LazyExpArchive(source)
    record = addon_record(archive)                       # ('provides', {id, title, revision[, supersedes]}) or None
    if record is None or record[0] != 'provides':
        raise ValueError(f'{source} is not an add-on')
    provides = record[1]
    icons = icon_resources(provides['id'], reference)
    if not icons:
        raise ValueError(f"{provides['id']} has no picker icon")
    resources = {resource: archive.read(resource) for resource in archive.entries}
    resources.update(icons)
    supersedes = list(provides.get('supersedes', ()))     # normalized: [(id, revision), ...]
    revision = provides['revision'] + 1
    resources[ADDON_RECORD] = provides_bytes(provides['id'], provides['title'], revision, supersedes)
    Path(target).write_bytes(encode_exp(resources))
    return provides['id'], provides['revision'], revision


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    patching = commands.add_parser('patch')
    patching.add_argument('source', type=Path)
    patching.add_argument('target', type=Path)
    patching.add_argument('--reference', type=Path, default=REFERENCE)
    preview = commands.add_parser('preview')
    preview.add_argument('folder', type=Path)
    preview.add_argument('--reference', type=Path, default=REFERENCE)
    args = parser.parse_args(argv)
    if args.command == 'patch':
        addon, old, new = patch(args.source, args.target, args.reference)
        print(f'{addon}: revision {old} -> {new}, icons added: {args.target}')
    else:
        args.folder.mkdir(parents=True, exist_ok=True)
        for addon in ICONS:
            for resource, data in icon_resources(addon, args.reference).items():
                if resource != SPEC_ID:
                    (args.folder / f'{addon}_{resource}.png').write_bytes(data)
                    print(addon, resource, Image.open(io.BytesIO(data)).size)


if __name__ == '__main__':
    main()
