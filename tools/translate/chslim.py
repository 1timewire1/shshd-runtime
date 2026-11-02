"""The `chslim` addon, "Claire Hart (Slim)": Claire Hart Classic's sharper originals of Cause of Death's portraits, and a little
of Claire Hart's interface for its translated episodes, built from the player's own files.

    python tools/translate/chslim.py --mirror CLAIRE_HART_DIR --pairs PAIRS.txt --catalog COD_CATALOG --cod-library LIBRARY --extras DIR --out DIR

CoD's episodes can't name an addon, so this one is optional (cod/profile.py PORTRAIT_ADDON): the player finds a picture by a
hash of CoD's bytes in the map at SPEC. Every portrait of Claire Hart has a lasting ID (PORTRAIT_BASE + its place in the mirror's
sorted list), so a complete addon can hold the same ones under the same IDs and supersede this one. Besides the pairs the owner
confirmed, it holds the rest of the people EXTRA_PEOPLE names, for the Claire Hart episodes they complete; those go in no map.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import sys

from PIL import Image

from exp_runtime.addons import RESOURCE as ADDON_RECORD, provides_bytes
from exp_runtime.exp import ExpArchive, Metadata, encode_exp

ADDON_ID, ADDON_TITLE, ADDON_REVISION = 'chslim', 'Claire Hart (Slim)', 1
PACK_ID = 31500                         # its metadata's pack: no episode of it exists yet
SPEC = 28000                            # the map and contents (cod/profile.py PORTRAIT_ADDON)
BACKDROP, SPEAKER_BOX, NARRATOR_BOX, FONT, FONT_BOLD = 28001, 28002, 28003, 28004, 28005
PORTRAIT_BASE = 28010                   # Claire Hart's portraits, in order
EDITED_BASE = 29000                     # pictures for CoD only, made for this addon
SCALE = 2                               # CoD's 110 x 120 at twice its size, as HD portraits are
# Left out of the map, though confirmed as the same art (owner, 2026-11-02). Sophie's red hair is plot-relevant.
NOT_MAPPED = frozenset({'1272', '1273', '1274', '1275'})
# The rest of these three bring the Claire Hart episodes it covers from 16 to 57 of 266 (owner, 2026-11-02).
EXTRA_PEOPLE = ('TroyHarris', 'PaulClayton', 'ClaireHart')
# Pictures of CoD's that Claire Hart has none for, as (CoD picture, file in the extras folder, resource or None).
# Natara's shocked face over Claire Hart's jacket and tie, as her other four wear them. Kai's shocked face is SHS HD's
# (April Fools' #26023, framed as CoD's): CoD shows his sad picture for it, so it only goes on that expression's resource.
EDITED = (('0699', 'natara_0699.png', None), ('0923', 'kai_shocked.png', 2229))
INTERFACE = ((BACKDROP, 'textures/new/loadingscreen_bg16_9'), (SPEAKER_BOX, 'textures/SD/dialog/speakerbox'),
             (NARRATOR_BOX, 'textures/SD/dialog/narratorbox'), (FONT, 'font/Romic/Romic'), (FONT_BOLD, 'font/Romic/Romic-Bold'))
PAIR = re.compile(r'portrait (\d+) = (\S+)(?: \[crop (-?\d+),(-?\d+),(\d+),(\d+)\])?')


def read_pairs(text):
    """{CoD picture: (Claire Hart path, crop or None)} of the confirmed pairs."""
    pairs = {}
    for line in text.splitlines():
        match = PAIR.match(line)
        if match and match.group(2) != 'none':
            crop = tuple(int(v) for v in match.groups()[2:]) if match.group(3) is not None else None
            pairs[match.group(1)] = (match.group(2), crop)
    return pairs


def portrait_ids(paths):
    """{Claire Hart path: its lasting ID}."""
    return {path: PORTRAIT_BASE + index for index, path in enumerate(sorted(paths))}


def png(image):
    out = io.BytesIO()
    image.save(out, 'PNG', optimize=True)
    return out.getvalue()


def framed(picture, crop, cod):
    """Claire Hart's `picture` in CoD's frame at SCALE, by the pair's crop. A strip the crop runs past its picture takes CoD's own
    picture (`cod`), enlarged."""
    x, y, w, h = crop
    frame = Image.new('RGBA', (w, h))
    frame.paste(picture, (-x, -y))
    size = cod.width * SCALE, cod.height * SCALE
    out = frame.resize(size, Image.LANCZOS)
    under = cod.resize(size, Image.LANCZOS)
    k = SCALE * cod.width / w
    left, top = max(0, round(-x * k)), max(0, round(-y * k))
    right, bottom = min(size[0], round((picture.width - x) * k)), min(size[1], round((picture.height - y) * k))
    for box in ((0, 0, left, size[1]), (right, 0, size[0], size[1]), (0, 0, size[0], top), (0, bottom, size[0], size[1])):
        if box[2] > box[0] and box[3] > box[1]:
            out.paste(under.crop(box), box[:2])
    return out


def whole(picture):
    """A picture no CoD frame crops, at about the same scale (458 x 500 to 220 x 240)."""
    return picture.resize((round(picture.width * 110 * SCALE / 458), round(picture.height * 110 * SCALE / 458)), Image.LANCZOS)


def pixels(data):
    image = Image.open(io.BytesIO(data)).convert('RGBA')
    return image.size, hashlib.sha1(image.tobytes()).hexdigest()


def hashes(wanted, sources):
    """{CoD picture: {hash of its bytes}}: `wanted` {picture: its pixels' key} looked for in `sources`, the bytes of every picture
    the library holds, since a catalogue's copy is re-encoded and builds may re-save a picture."""
    by_pixels = {key: number for number, key in wanted.items()}
    found = {number: set() for number in wanted}
    for data in sources:
        if data[:8] != b'\x89PNG\r\n\x1a\n':
            continue
        try:
            number = by_pixels.get(pixels(data))
        except (OSError, ValueError):
            continue
        if number is not None:
            found[number].add(hashlib.sha1(data).hexdigest()[:20])
    return found


def library_pictures(folder):
    """The bytes of every portrait-sized resource in a CoD library's episode files and app bundle."""
    from exp_runtime.content import ContentLibrary
    library = ContentLibrary(folder)
    seen = set()
    for record in library.episodes:
        if record.get('file'):
            archive = ExpArchive((Path(folder) / record['file']).read_bytes())
            for resource in archive.entries:
                if resource >= 2000:
                    data = archive.read(resource)
                    key = hashlib.sha1(data).digest()
                    if key not in seen:
                        seen.add(key)
                        yield data
    for resource in range(2000, 2600):
        try:
            data = library.android_asset(resource)
        except Exception:
            continue
        key = hashlib.sha1(data).digest()
        if key not in seen:
            seen.add(key)
            yield data


def build(mirror, pairs, catalog, sources, extras):
    """The addon's `.exp` bytes and a report. `mirror`: the Claire Hart Classic folder (bundle_names.csv and raw/), `pairs`: read_pairs',
    `catalog`: the CoD catalogue's portraits folder, `sources`: library_pictures', `extras`: the EDITED pictures' folder."""
    mirror = Path(mirror)
    with open(mirror / 'bundle_names.csv', encoding='utf-8-sig', newline='') as file:
        rows = [row for row in csv.DictReader(file) if row['part'] == 'native']
    files = {row['real_path']: mirror / row['local_path'] for row in rows}
    characters = {path for path, row in ((r['real_path'], r) for r in rows) if row['kind'] == 'portrait'}
    ids = portrait_ids(characters)
    resources = {}
    crops = {}
    for number, (path, crop) in sorted(pairs.items()):
        crops.setdefault(path, (number, crop))
    catalog = Path(catalog)
    for path, (number, crop) in crops.items():
        cod = Image.open(catalog / f'{number}.png').convert('RGBA')
        picture = Image.open(files[path]).convert('RGBA')
        resources[ids[path]] = png(framed(picture, crop or (0, 0, *picture.size), cod))
    extra = sorted(p for p in characters if p.split('/')[2] in EXTRA_PEOPLE and p not in crops)
    for path in extra:
        resources[ids[path]] = png(whole(Image.open(files[path]).convert('RGBA')))
    mapped = {number: pair for number, pair in pairs.items() if number not in NOT_MAPPED}
    wanted = {number: pixels((catalog / f'{number}.png').read_bytes())
              for number in {*mapped, *(number for number, _, _ in EDITED)}}
    found = hashes(wanted, sources)
    spec = dict(portraits={}, resources={}, backdrop=BACKDROP, speaker_box=SPEAKER_BOX, narrator_box=NARRATOR_BOX, font=FONT,
                font_bold=FONT_BOLD, characters={path: ids[path] for path in sorted(crops) + extra})
    for number, (path, _) in mapped.items():
        for key in found[number]:
            spec['portraits'][key] = ids[path]
    for index, (number, name, resource) in enumerate(EDITED):
        resources[EDITED_BASE + index] = png(Image.open(Path(extras) / name).convert('RGBA'))
        for key in found[number]:
            if resource is None:
                spec['portraits'][key] = EDITED_BASE + index
            else:
                spec['resources'][f'{key}:{resource}'] = EDITED_BASE + index
    for resource, path in INTERFACE:
        resources[resource] = files[path].read_bytes()
    resources[SPEC] = json.dumps(spec, separators=(',', ':')).encode('utf-8')
    resources[ADDON_RECORD] = provides_bytes(ADDON_ID, ADDON_TITLE, ADDON_REVISION)
    resources[1] = Metadata(PACK_ID, 0, (ADDON_TITLE + ' (addon)',) * 5).to_bytes()
    report = dict(pictures=len(crops), extra=len(extra), edited=len(EDITED), mapped=len(mapped),
                  unfound=sorted(number for number, keys in found.items() if not keys), hashes=len(spec['portraits']))
    return encode_exp(resources), report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--mirror', type=Path, required=True)
    parser.add_argument('--pairs', type=Path, required=True)
    parser.add_argument('--catalog', type=Path, required=True, help="the CoD catalogue's portraits folder")
    parser.add_argument('--cod-library', type=Path, required=True)
    parser.add_argument('--extras', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    data, report = build(args.mirror, read_pairs(args.pairs.read_text(encoding='utf-8')), args.catalog,
                         library_pictures(args.cod_library), args.extras)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'CH_Slim.exp').write_bytes(data)
    print(f'addon: {ADDON_TITLE!r} -> {args.out / "CH_Slim.exp"} ({len(data) // 1024} KB), {report}')
    return 1 if report['unfound'] else 0


if __name__ == '__main__':
    sys.exit(main())
