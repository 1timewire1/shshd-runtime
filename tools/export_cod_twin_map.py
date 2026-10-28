"""Export Cause of Death's shipped HD twin map (packages/cod/src/exp_runtime/cod/hd_twin_map.py) from the owner's
reviewed catalogue of CoD backgrounds that share their art with SHS HD (cod-portrait-catalog/shs_hd_backgrounds.md).

    python tools/export_cod_twin_map.py --cod-library COD --shs-library SHS --catalogs DIR [--cod-ipa IPA ...]

DIR holds both catalogues (cod-portrait-catalog/ from tools/export_cod_art_catalog.py, portrait-catalog/ from
tools/export_art_catalog.py, and shs_hd_backgrounds.md). Taken from the document's sections:
- "Same picture" and "The HD picture as it is": the HD picture unchanged;
- "Same picture, other levels": 'levels';
- "The HD picture with CoD's edit recreated": EFFECTS below, by CoD catalogue number.
Each catalogue number is traced to its original bytes through the catalogues' "In" columns (a CoD bundle id or a CoD
episode resource; an SHS HD episode resource or an SHS HD bank id) and checked against the catalogue's picture. A
`--cod-ipa` (another CoD release: 1.3.4 re-saved the bundle's backgrounds) adds its bundle pictures' fingerprints for
the same HD pictures. Fingerprints, sizes and where to look only: no picture is written (cod/hd_twins.build).
"""
import argparse
import hashlib
import io
import re
import zipfile
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

from exp_runtime.content import ContentLibrary
from exp_runtime.hd_twins import fingerprint, image_size

OUTPUT = Path(__file__).resolve().parents[1] / 'packages/cod/src/exp_runtime/cod/hd_twin_map.py'
# The recreated edits (shs_hd_backgrounds.md "The HD picture with CoD's edit recreated"), by CoD catalogue number.
EFFECTS = {'0425': ('blur', 9.0), '0429': ('local', None), '0431': ('local', 0.3), '0444': ('local', None)}
SECTIONS = {'Same picture': None, 'Same picture, other levels': 'levels', 'The HD picture as it is': None,
            "The HD picture with CoD's edit recreated": 'recreated'}
ROW = re.compile(r'^\| <img src="backgrounds/(\d{4})\.png".*?<img src="\.\./portrait-catalog/(bg-hd|bank-hd)/(\d{4})\.png"')


def reviewed(document):
    """[(CoD number, 'hd' | 'bank', HD number, effect)] from the reviewed document."""
    rows, effect, wanted = [], None, False
    for line in document.read_text(encoding='utf-8').splitlines():
        heading = re.match(r'^#{2,3} (.+)$', line)
        if heading:
            wanted = heading.group(1) in SECTIONS
            effect = SECTIONS.get(heading.group(1))
            continue
        match = ROW.match(line)
        if wanted and match:
            number, folder, hd = match.groups()
            row_effect = EFFECTS[number] if effect == 'recreated' else effect
            rows.append((number, 'bank' if folder == 'bank-hd' else 'hd', hd, row_effect))
    return rows


def catalogue(path, column):
    """{number: first (place, resource id)} from a catalogue table's "In" column ('app bundle', an episode, or a bank
    id for bank_backgrounds.md)."""
    found = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        cells = [c.strip() for c in line.strip('|').split(' | ')]
        if path.name == 'bank_backgrounds.md':
            if len(cells) > 2 and re.fullmatch(r'\d{4}', cells[0]):
                found[cells[0]] = ('bank', int(cells[1]))
            continue
        if not line.startswith('| <img') or len(cells) <= column:
            continue
        first = cells[column].split('; ')[0]
        place = re.match(r'(.+) #(\d+)$', first)
        if place:
            found[cells[1]] = (place.group(1), int(place.group(2)))
    return found


def same_picture(data, png_path):
    a = Image.open(io.BytesIO(data)).convert('RGB')
    b = Image.open(png_path).convert('RGB')
    if a.size != b.size:
        return False
    return max(ImageStat.Stat(ImageChops.difference(a, b)).mean) < 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--cod-library', type=Path, required=True)
    parser.add_argument('--shs-library', type=Path, required=True)
    parser.add_argument('--catalogs', type=Path, required=True)
    parser.add_argument('--cod-ipa', type=Path, action='append', default=[])
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    cod_dir, shs_dir = args.catalogs / 'cod-portrait-catalog', args.catalogs / 'portrait-catalog'
    rows = reviewed(cod_dir / 'shs_hd_backgrounds.md')
    cod_places = catalogue(cod_dir / 'cod_backgrounds.md', 4)
    hd_places = catalogue(shs_dir / 'hd_backgrounds.md', 4)
    bank_places = catalogue(shs_dir / 'bank_backgrounds.md', 0)
    others = []
    for path in args.cod_ipa:
        ipa = zipfile.ZipFile(path)
        prefix = next(n for n in ipa.namelist() if re.fullmatch(r'Payload/[^/]+\.app/res_generated/', n.rsplit('/', 1)[0] + '/')
                      ).rsplit('/', 1)[0] + '/'
        others.append((ipa, prefix))
    twins = {}
    with ContentLibrary(args.cod_library) as cod, ContentLibrary(args.shs_library) as shs:
        cod.hd_art_mode = shs.hd_art_mode = 'off'
        cod_names = {r['name'].removesuffix('.exp'): r for r in cod.episodes}
        shs_names = {r['name'].removesuffix('.exp'): r for r in shs.episodes}
        for number, kind, hd_number, effect in rows:
            place, resource_id = cod_places[number]
            if place == 'app bundle':
                cod_data = cod.android_asset(resource_id)
            else:
                cod_data = cod.open_episode(cod_names[place]['id']).archive.read(resource_id)
            if not same_picture(cod_data, cod_dir / 'backgrounds' / f'{number}.png'):
                raise SystemExit(f'CoD {number}: {place} #{resource_id} is not the catalogue picture')
            if kind == 'bank':
                hd_id = bank_places[hd_number][1]
                hd_data, hint = shs.hd_raw_resource(hd_id), ('bank', hd_id)
                png = shs_dir / 'bank-hd' / f'{hd_number}.png'
            else:
                hd_place, hd_id = hd_places[hd_number]
                record = shs_names[hd_place]
                hd_data, hint = shs.open_episode(record['id']).archive.read(hd_id), ('episode', record['name'], hd_id)
                png = shs_dir / 'bg-hd' / f'{hd_number}.png'
            if hd_data is None or not same_picture(hd_data, png):
                raise SystemExit(f'HD {hd_number}: {hint} is not the catalogue picture')
            entry = (fingerprint(hd_data), *image_size(cod_data), effect, hint)
            twins[fingerprint(cod_data)] = entry
            if place == 'app bundle':
                for ipa, prefix in others:
                    try:
                        other = ipa.read(prefix + str(resource_id))
                    except KeyError:
                        continue
                    if fingerprint(other) != fingerprint(cod_data) and image_size(other):
                        twins[fingerprint(other)] = (entry[0], *image_size(other), effect, hint)
    body = repr(sorted(twins.items())).encode()
    version = hashlib.sha1(body).hexdigest()[:12]
    lines = ['"""Cause of Death\'s HD twin map, shipped with the app: %d CoD backgrounds (both bundle releases\' bytes) with'
             % len(twins),
             'the SHS HD picture each one is, and how CoD changed it. Generated by tools/export_cod_twin_map.py from the',
             "owner's reviewed catalogue (shs_hd_backgrounds.md); do not edit by hand. Fingerprints (`hd_twins.fingerprint`),",
             'sizes and where to look only: the app finds every picture in the player\'s own files (`cod.hd_twins.build`)."""',
             '', f"VERSION = '{version}'", '',
             '# CoD picture fingerprint: (SHS HD picture fingerprint, CoD width, CoD height, effect, where the HD picture is:',
             "# ('episode', SHS episode name, resource id) or ('bank', SHS HD bundle id))",
             'TWINS = {']
    for key, (hd, width, height, effect, hint) in sorted(twins.items()):
        lines.append(f'    {key!r}: ({hd!r}, {width}, {height}, {effect!r}, {hint!r}),')
    lines.append('}')
    args.output.write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    print(f'{len(twins)} entries ({len(rows)} reviewed pairs), version {version} -> {args.output}')


if __name__ == '__main__':
    main()
