"""Claire Hart Classic's sprite frames (Cocos Creator 2.4), read from the mirror's packed import JSON: each frame's name, its
texture's rectangle (rotated a quarter turn when `rotated`), its offset and original size. Pieces of an atlas page are cut back
out as they were drawn (their original size, trimmed transparent margins restored).

The packed files are Cocos's compiled form, a list: [version, uuids, strings, classes, masks, instances, ...]; a sprite
frame's instance is [[{name, rect, offset, originalSize, rotated?, capInsets}], ..., [uuid index]] with its texture's uuid last.
"""
import json
from pathlib import Path

IMPORT = 'raw/157/assets/resources/import'
NATIVE = 'raw/157/assets/resources/native'


def frames(mirror_root, packs=None):
    """{name: [frame dict + 'texture': uuid, 'pack': file]} for every sprite frame in the import JSONs (or `packs`, files
    relative to IMPORT). A name may occur more than once (another atlas's frame of the same name)."""
    root = Path(mirror_root) / IMPORT
    files = [root / p for p in packs] if packs else sorted(root.rglob('*.json'))
    out = {}
    for path in files:
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (ValueError, UnicodeDecodeError):
            continue
        if not (isinstance(data, list) and len(data) > 5 and isinstance(data[1], list) and isinstance(data[5], list)):
            continue
        uuids = data[1]
        for item in data[5]:
            if not (isinstance(item, list) and item and isinstance(item[0], list) and item[0]
                    and isinstance(item[0][0], dict) and 'rect' in item[0][0] and 'name' in item[0][0]):
                continue
            frame = dict(item[0][0])
            last = item[-1]
            if isinstance(last, list) and last and isinstance(last[0], int) and last[0] < len(uuids):
                frame['texture'] = uuids[last[0]]
            frame['pack'] = str(path.relative_to(root)).replace('\\', '/')
            out.setdefault(frame['name'], []).append(frame)
    return out


BASE64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'


def full_uuid(uuid):
    """Cocos's compressed 22-character uuid (2 hex digits, then base64 pairs of 3 hex digits each) as its 36-character
    form; any other as it is."""
    if len(uuid) != 22:
        return uuid
    digits = uuid[:2]
    for i in range(2, 22, 2):
        value = (BASE64.index(uuid[i]) << 6) | BASE64.index(uuid[i + 1])
        digits += f'{value:03x}'
    return f'{digits[:8]}-{digits[8:12]}-{digits[12:16]}-{digits[16:20]}-{digits[20:]}'


def texture_path(mirror_root, uuid):
    uuid = full_uuid(uuid)
    folder = Path(mirror_root) / NATIVE / uuid[:2]
    for ext in ('.png', '.jpg'):
        if (folder / (uuid + ext)).exists():
            return folder / (uuid + ext)
    found = sorted(folder.glob(uuid + '*')) if folder.exists() else []
    return found[0] if found else None


def cut(mirror_root, frame, *, trimmed=False, cache=None):
    """The frame's picture (RGBA): its original size with the trimmed margins restored (Cocos's offset: from the middle,
    y up), or `trimmed` just its rectangle."""
    from PIL import Image
    cache = {} if cache is None else cache
    uuid = frame['texture']
    if uuid not in cache:
        cache[uuid] = Image.open(texture_path(mirror_root, uuid)).convert('RGBA')
    sheet = cache[uuid]
    x, y, w, h = frame['rect']
    if frame.get('rotated'):
        piece = sheet.crop((x, y, x + h, y + w)).rotate(90, expand=True)
    else:
        piece = sheet.crop((x, y, x + w, y + h))
    if trimmed:
        return piece
    ow, oh = frame.get('originalSize') or (w, h)
    ox, oy = frame.get('offset') or (0, 0)
    whole = Image.new('RGBA', (int(ow), int(oh)), (0, 0, 0, 0))
    left = round((ow - w) / 2 + ox)
    top = round((oh - h) / 2 - oy)
    whole.alpha_composite(piece, (left, top))
    return whole
