"""Parsers for the native string bank and embedded menu bitmap font."""
from dataclasses import dataclass

from .exp import MAX_PAYLOAD
from .ui_assets import Raster, UIAssetError, _Reader


@dataclass(frozen=True)
class MenuStrings:
    strings: tuple[str, ...]
    roles: dict[int, int] | None = None

    @classmethod
    def load(cls, resources):
        """Read host UI strings using the selected game's semantic roles."""
        from .games import game_id
        from .ui_assets import read_ui
        bank = cls.parse(read_ui(resources, 13))
        if game_id(resources) == 'cod':
            from .cod.assets import STRING_IDS
            return cls(bank.strings, STRING_IDS)
        return bank

    @classmethod
    def parse(cls, data):
        r = _Reader(data)
        version, flags, bank, count = r.unpack('iBhh')
        if (version, flags, bank) != (1, 0, 0) or count < 1:
            raise UIAssetError('Unsupported menu string bank')
        offsets = [r.integer() for _ in range(count)]
        start, strings = r.pos, []
        for offset in offsets:
            end = data.find(b'\0', offset)
            if not start <= offset <= end < len(data):
                raise UIAssetError('Invalid menu string offset')
            # This older UI bank uses byte characters, unlike EXP metadata's
            # length-prefixed UTF-8 titles.
            strings.append(data[offset:end].decode('latin-1'))
        return cls(tuple(strings))

    def __getitem__(self, index):
        if self.roles is not None:
            try:
                index = self.roles[index]
            except KeyError:
                raise UIAssetError(f'Unverified game UI string role {index}') from None
        try:
            return self.strings[index]
        except IndexError:
            raise UIAssetError(f'Absent menu string {index}') from None


@dataclass(frozen=True)
class MenuFont:
    """Embedded ARGB glyphs in resources 532/533 (the menu's CS font path)."""
    space: int
    tracking: int
    height: int
    glyphs: dict[str, Raster]

    @classmethod
    def parse(cls, data):
        r = _Reader(data)
        space, style, tracking, count, height = r.unpack('bBbhb')
        if space < 0 or style != 0 or not 0 < count <= 256 or height <= 0:
            raise UIAssetError('Unsupported embedded menu font')
        codes = r.take(count).decode('latin-1')
        if len(set(codes)) != count or r.integer() != -1 or r.count() != count:
            raise UIAssetError('Invalid menu glyph table')
        glyphs, total = {}, 0
        for code in codes:
            width, h = r.unpack('BB')
            total += width * h * 4
            if width <= 0 or h != height or total > MAX_PAYLOAD:
                raise UIAssetError('Invalid menu glyph dimensions')
            argb = r.take(width * h * 4)
            rgba = bytearray(len(argb))
            rgba[0::4], rgba[1::4], rgba[2::4], rgba[3::4] = argb[1::4], argb[2::4], argb[3::4], argb[0::4]
            glyphs[code] = Raster(width, h, bytes(rgba))
        r.finish()
        return cls(space, tracking, height, glyphs)

    def glyph(self, char):
        return self.glyphs.get(char, self.glyphs.get(char.upper()))

