"""Verified Cause of Death IPA UI roles. Script-visible IDs remain exact.

CoD retains SHS's layout bank, but its title/menu fonts and relationship art
have different numeric IDs. There is no fallback into an SHS library.
"""
from io import BytesIO

from ..content import ContentError, MAX_PAYLOAD


UI_IDS = {528: 292, 529: 293, 530: 294, 531: 295, 532: 296, 533: 297}
# Host string roles use the existing SHS renderer's indices. These are
# inspected semantic equivalents in CoD's own resource 13, never SHS text.
STRING_IDS = {
    9: 8, 10: 9, 11: 10, 21: 20, 23: 22, 25: 24, 26: 25, 128: 120,
    29: 26, 30: 27, 31: 28, 35: 32, 36: 33, 37: 34, 38: 35, 39: 36, 40: 37,
    82: 79, 91: 82, 125: 117, 126: 118, 127: 119, 164: 154,
    238: 213, 252: 227, 258: 232, 260: 234, 302: 80,
    **{role: role - 8 for role in range(118, 123)},
}


def ui_resource(library, role):
    # Shared panel/art IDs retain their native values. Absent assets fail in
    # this library; a coincident SHS role must not acquire unrelated CoD data.
    if role in (290, 446, 496, 499, 502, 540, 541) or 508 <= role < 528 or 700 <= role <= 723:
        raise ContentError(f'Cause of Death has no verified UI resource for role {role}')
    return library.read_asset(UI_IDS.get(role, role))


def validate_assets(read):
    from PIL import Image, ImageFont
    from ..atlas import AtlasFont
    from ..content import ExpArchive
    from ..menu_assets import MenuFont, MenuStrings
    from ..ui_assets import ImagePack, LayoutBank, Rect

    def check(resource, parser):
        try:
            return parser(read(resource))
        except (ValueError, OSError, IndexError, Image.DecompressionBombError) as error:
            raise ContentError(f'Incompatible or missing CoD asset {resource}: {error}') from error

    episode = check(12, ExpArchive)
    episode.metadata()
    if 25001 not in episode.programs():
        raise ContentError('CoD asset 12 is missing the bundled episode entry script')
    if len(check(13, MenuStrings.parse).strings) < 257:
        raise ContentError('CoD string bank 13 is missing required UI strings')
    bank = check(14, LayoutBank.parse)
    if len(bank.layouts) < 80:
        raise ContentError('CoD layout bank 14 is missing required UI layouts')
    for index, last in ((7, 9), (8, 9), (17, 87), (22, 18), (46, 46), (65, 4)):
        bank.rectangle(index, last)
    for index in range(len(bank.layouts)):
        tuple(bank.walk(index))
    for resource, count in ((6, 1), (7, 1), (8, 1), (9, 1), (16, 108), (126, 60),
                            (204, 14), (220, 14), (236, 14), (252, 14), (268, 1), (272, 16)):
        pack = check(resource, ImagePack.parse)
        mode = 'A' if resource == 268 else 'RGBA'
        if len(pack.images) < count or any(p.mode != mode for p in pack.images):
            raise ContentError(f'CoD image pack {resource} has incompatible frames or pixel mode')
        if resource == 268 and (pack.images[0].width, pack.images[0].height) != (128, 150):
            raise ContentError('CoD portrait mask 268 must be 128 by 150')
    check(291, lambda data: ImageFont.truetype(BytesIO(data), 24))
    def png(data):
        with Image.open(BytesIO(data)) as image:
            if image.format != 'PNG' or image.width * image.height * 4 > MAX_PAYLOAD:
                raise ContentError('Unsupported or oversized CoD UI image')
            image.load()
            return Rect(0, 0, image.width, image.height)
    for resource in (292, 294):
        rect = check(resource, png)
        check(resource + 1, lambda data: AtlasFont.parse(data, rect))
    for resource in (296, 297):
        check(resource, MenuFont.parse)
