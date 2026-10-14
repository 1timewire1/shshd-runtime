"""Host UI roles for the validated iOS package, separate from KiWi IDs.

Roles use the existing Android renderer's IDs. Numeric resource reads always
retain the source package's IDs. This table records inspected equivalents;
missing Android-only UI exports must never be guessed from adjacent IDs.
"""
from io import BytesIO

from ..content import ContentError, MAX_PAYLOAD


UI_IDS = {
    13: 12, 14: 13, 15: 14, 16: 15, 126: 125,
    188: 187, 204: 203, 220: 219, 236: 235, 252: 251, 268: 267, 272: 271,
    290: 289, 446: 445, 496: 495, 499: 498, 502: 501,
    505: 504, 506: 505,
    **{role: role - 2 for role in range(508, 534)},
    541: 509,
    **{role: role - 395 for role in range(3010, 3019)},
}


def validate_assets(read):
    """Check the asset contract, independent of app version or binary hash.

    IDs, formats and available frame/node ranges determine compatibility.
    Episode-specific art/audio remains lazy, as for APK libraries.
    """
    from PIL import Image
    from ..atlas import AtlasFont, SpriteAtlas
    from ..menu_assets import MenuFont, MenuStrings
    from ..ui_assets import ImagePack, LayoutBank, Rect

    def check(resource, parser):
        try:
            return parser(read(resource))
        except (ContentError, ValueError, OSError, IndexError, Image.DecompressionBombError) as error:
            raise ContentError(f'Incompatible or missing IPA asset {resource}: {error}') from error

    strings = check(12, MenuStrings.parse)
    if len(strings.strings) < 303:
        raise ContentError('IPA string bank 12 is missing required UI strings')
    layout = check(13, LayoutBank.parse)
    if len(layout.layouts) < 80:
        raise ContentError('IPA layout bank 13 is missing required UI layouts')
    try:
        for index, last in ((7, 9), (8, 9), (17, 87), (22, 18), (46, 46), (65, 4)):
            layout.rectangle(index, last)
        for index in range(len(layout.layouts)):
            tuple(layout.walk(index))
    except ContentError as error:
        raise ContentError(f'Incompatible IPA layout bank 13: {error}') from error
    for resource, count in ((15, 108), (125, 60), (203, 14), (219, 14),
                            (235, 14), (251, 14), (267, 1), (271, 8)):
        pack = check(resource, ImagePack.parse)
        if len(pack.images) < count or any(image.mode != ('A' if resource == 267 else 'RGBA')
                                          for image in pack.images):
            raise ContentError(f'IPA image pack {resource} has incompatible frames or pixel mode')
        if resource == 267 and (pack.images[0].width, pack.images[0].height) != (128, 150):
            raise ContentError('IPA portrait mask 267 must be 128 by 150')
    for resource, count in ((289, 154), (445, 48), (495, 1), (498, 1), (501, 1),
                            *((n, 1) for n in range(506, 526, 2))):
        atlas = check(resource, SpriteAtlas.parse)
        if len(atlas.frames) < count:
            raise ContentError(f'IPA sprite atlas {resource} is missing required frames')
        if 506 <= resource <= 524:
            check(resource + 1, lambda data: AtlasFont.parse(data, atlas.image))
    def png(data):
        with Image.open(BytesIO(data)) as image:
            if image.format != 'PNG' or image.width * image.height * 4 > MAX_PAYLOAD:
                raise ContentError('Unsupported or oversized UI image')
            image.load()
            return Rect(0, 0, image.width, image.height)
    for resource in (6, 7, 8, 9, 526, 528, *range(2615, 2624)):
        rect = check(resource, png)
        if resource in (526, 528):
            check(resource + 1, lambda data: AtlasFont.parse(data, rect))
    for resource in (530, 531):
        check(resource, MenuFont.parse)


def _png(raster):
    from PIL import Image
    image = Image.frombytes(raster.mode, (raster.width, raster.height), raster.pixels)
    stream = BytesIO()
    image.save(stream, format='PNG')
    return stream.getvalue()


def ui_resource(library, role):
    if 701 <= role <= 704:
        # SHSUIMinigameFootball::drawHUD, English down table at 00312772.
        from ..atlas import SpriteAtlas
        return _png(SpriteAtlas.parse(library.read_asset(289)).raster((10, 15, 20, 25)[role - 701]))
    if role == 540:
        from ..atlas import SpriteAtlas
        return _png(SpriteAtlas.parse(library.read_asset(508)).raster(0))
    if 700 <= role <= 723:
        raise ContentError(f'IPA UI role {role} has no verified desktop mapping yet')
    return library.read_asset(UI_IDS.get(role, role))
