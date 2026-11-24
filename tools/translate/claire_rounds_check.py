"""Check a built `chcrounds` against the mirror: each scene redrawn from the add-on alone (its base, then every object's
normal sprite from its sprite pack at its place, in the layout's order) against Classic's own `template.png`, which is
"base + every normal sprite", inset 1 pixel (CLAIRE_HART_ENGINE.md section 5.1). Many templates are 256-colour PNGs (noise
everywhere) and some of the 62 older scenes' templates show a few objects where their layout no longer has them (ClairesOffice's
second ship), so the test is gross misplacement: the share of pixels more than 60 levels off.

    python tools/translate/claire_rounds_check.py ADDON.exp MIRROR [SCENE ...]

Prints each scene's mean difference and share of pixels far off; a scene over LIMIT_FAR is listed as a failure."""
import io
import json
from pathlib import Path
import sys

from PIL import Image, ImageChops

from exp_runtime.exp import LazyExpArchive

FAR, LIMIT_FAR = 60, 0.02


def redraw(archive, entry):
    from exp_runtime.claire_rounds import sprite_from_pack
    base = Image.open(io.BytesIO(archive.read(entry['base']))).convert('RGBA')
    pack = archive.read(entry['sprites'])
    for _, normal, _, _ in entry['objects']:
        number, w, h, left, top = normal
        sprite = Image.open(io.BytesIO(sprite_from_pack(pack, number))).convert('RGBA')
        if sprite.size != (w, h):
            raise ValueError(f'sprite {number}: {sprite.size}, the spec says {(w, h)}')
        base.alpha_composite(sprite, (left, top))
    return base


def difference(a, b):
    diff = ImageChops.difference(a.convert('RGB'), b.convert('RGB')).convert('L')
    histogram = diff.histogram()
    total = sum(histogram)
    mean = sum(i * n for i, n in enumerate(histogram)) / total
    return mean, sum(histogram[FAR + 1:]) / total


def main(argv):
    archive = LazyExpArchive(argv[0])
    spec = json.loads(archive.read(26000))
    root = Path(argv[1]) / 'raw/157/res/raw-assets/references/backgrounds'
    folders = argv[2:] or sorted(spec['scenes'])
    failures = []
    for folder in folders:
        entry = spec['scenes'][folder]
        drawn = redraw(archive, entry)
        template = Image.open(root / folder / 'hd' / 'template.png').convert('RGBA')
        crop = drawn.crop((1, 1, 1 + template.width, 1 + template.height))
        mean, far = difference(crop, template)
        ok = far <= LIMIT_FAR
        if not ok:
            failures.append(folder)
        if not ok or len(folders) <= 20:
            print(f'{folder}: mean {mean:.2f}, far off {100 * far:.2f}%{"" if ok else "  FAIL"}')
    print(f'{len(folders) - len(failures)} of {len(folders)} scenes match their template')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
