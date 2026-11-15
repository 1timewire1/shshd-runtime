"""Read a Nintendo DS(i) image in pure Python: its header, ARM9 binary and overlays (BLZ-compressed), NitroFS files, the BIOS
compressions (LZ10, LZ11, Huffman, RLE, the diff filters), and A2M's ".urf" archives, as SHS DSiWare stores them.

Used by dsi.py, which builds the DSiWare add-on from the player's own image (`.nds`, or the CDN content file, the same bytes).
Ported from the reference study's tools (reference/Other Games/tools: nds_unpack.py, nds_compress.py, shs_dsi_urf.py).
"""
import struct
import zlib


def u16(data, offset):
    return struct.unpack_from('<H', data, offset)[0]


def u32(data, offset):
    return struct.unpack_from('<I', data, offset)[0]


# ---------- the BIOS compressions ----------

def _header(data):
    size, position = u32(data, 0) >> 8, 4
    if size == 0:
        size, position = u32(data, 4), 8
    return size, position


def lz10(data):
    size, p = _header(data)
    out = bytearray()
    while len(out) < size:
        flags = data[p]
        p += 1
        for bit in range(8):
            if len(out) >= size:
                break
            if flags & (0x80 >> bit):
                b1, b2 = data[p], data[p + 1]
                p += 2
                length, back = (b1 >> 4) + 3, ((b1 & 0xF) << 8 | b2) + 1
                for _ in range(length):
                    out.append(out[-back])
            else:
                out.append(data[p])
                p += 1
    return bytes(out[:size])


def lz11(data):
    size, p = _header(data)
    out = bytearray()
    while len(out) < size:
        flags = data[p]
        p += 1
        for bit in range(8):
            if len(out) >= size:
                break
            if flags & (0x80 >> bit):
                b1 = data[p]
                kind = b1 >> 4
                if kind == 0:
                    b2, b3 = data[p + 1], data[p + 2]
                    length, back = ((b1 & 0xF) << 4 | b2 >> 4) + 0x11, ((b2 & 0xF) << 8 | b3) + 1
                    p += 3
                elif kind == 1:
                    b2, b3, b4 = data[p + 1], data[p + 2], data[p + 3]
                    length, back = ((b1 & 0xF) << 12 | b2 << 4 | b3 >> 4) + 0x111, ((b3 & 0xF) << 8 | b4) + 1
                    p += 4
                else:
                    length, back = kind + 1, ((b1 & 0xF) << 8 | data[p + 1]) + 1
                    p += 2
                for _ in range(length):
                    out.append(out[-back])
            else:
                out.append(data[p])
                p += 1
    return bytes(out[:size])


def huffman(data):
    bits = data[0] & 0xF
    size, p = _header(data)
    tree_size = (data[p] + 1) * 2
    tree = data[p:p + tree_size]
    p += tree_size
    out, byte, nibbles, word, word_bits, node = bytearray(), 0, 0, 0, 0, 1
    while len(out) < size:
        if word_bits == 0:
            if p + 4 > len(data):
                break
            word, word_bits = u32(data, p), 32
            p += 4
        bit = (word >> 31) & 1
        word, word_bits = (word << 1) & 0xFFFFFFFF, word_bits - 1
        entry = tree[node]
        leaf = entry & (0x40 if bit else 0x80)
        node = (node & ~1) + (entry & 0x3F) * 2 + 2 + bit
        if leaf:
            value, node = tree[node], 1
            if bits == 8:
                out.append(value)
            else:
                byte |= (value & 0xF) << (4 * nibbles)
                nibbles += 1
                if nibbles == 2:
                    out.append(byte)
                    byte, nibbles = 0, 0
    return bytes(out[:size])


def rle(data):
    size, p = _header(data)
    out = bytearray()
    while len(out) < size:
        flag = data[p]
        p += 1
        if flag & 0x80:
            out += bytes([data[p]]) * ((flag & 0x7F) + 3)
            p += 1
        else:
            out += data[p:p + flag + 1]
            p += flag + 1
    return bytes(out[:size])


def unfilter(data):
    """The BIOS's Diff8bitUnFilter (0x81) and Diff16bitUnFilter (0x82)."""
    size, p = _header(data)
    out, total = bytearray(), 0
    if data[0] == 0x81:
        for value in data[p:p + size]:
            total = (total + value) & 0xFF
            out.append(total)
    else:
        for i in range(size // 2):
            total = (total + u16(data, p + 2 * i)) & 0xFFFF
            out += struct.pack('<H', total)
    return bytes(out)


DECODERS = {0x10: lz10, 0x11: lz11, 0x24: huffman, 0x28: huffman, 0x30: rle, 0x81: unfilter, 0x82: unfilter}


def decompress(data):
    """Undo the compressions a payload's first byte names, repeatedly (Huffman, then a diff filter), up to four layers. A
    payload that isn't compressed comes back as it is."""
    for _ in range(4):
        decoder = DECODERS.get(data[0]) if data else None
        if decoder is None:
            break
        try:
            unpacked = decoder(data)
        except (IndexError, struct.error):
            break
        if not unpacked:
            break
        data = unpacked
    return data


def blz(data):
    """Nintendo's bottom-up LZ, as ARM9 binaries and overlays use."""
    header = data[-5]
    packed = u32(data, len(data) - 8) & 0xFFFFFF
    extra = u32(data, len(data) - 4)
    if not 8 <= header <= 11 or packed > len(data):
        raise ValueError('not BLZ-compressed')
    out = bytearray(data) + bytearray(extra)
    source, target, end = len(data) - header, len(data) + extra, len(data) - packed
    while source > end:
        source -= 1
        flags = out[source]
        for _ in range(8):
            if source <= end:
                break
            if flags & 0x80:
                source -= 2
                value = out[source] | out[source + 1] << 8
                back = (value & 0xFFF) + 3
                for _ in range((value >> 12) + 3):
                    target -= 1
                    out[target] = out[target + back]
            else:
                source -= 1
                target -= 1
                out[target] = out[source]
            flags = (flags << 1) & 0xFF
    return bytes(out)


# ---------- the image ----------

class Rom:
    """A DS(i) image: `rom.title`, `rom.code` (game code), `rom.arm9()` (decompressed, from `arm9_ram`), `rom.overlay(n)`
    (decompressed, from `overlay_ram(n)`), `rom.file(name)` (NitroFS, by its path)."""

    def __init__(self, data):
        if len(data) < 0x200:
            raise ValueError('too short for a DS image')
        self.data = data
        self.title = data[0:12].rstrip(b'\0').decode('latin-1')
        self.code = data[12:16].decode('latin-1')
        self.arm9_rom, _, self.arm9_ram, self.arm9_size = struct.unpack_from('<4I', data, 0x20)
        fnt, fnt_size, fat, fat_size, ovt, ovt_size = struct.unpack_from('<6I', data, 0x40)
        self._fat = data[fat:fat + fat_size]
        self._fnt = data[fnt:fnt + fnt_size]
        table = data[ovt:ovt + ovt_size]
        self._overlays = {}
        for i in range(0, len(table), 32):
            number, ram, size, bss, _, _, file_id, flags = struct.unpack_from('<8I', table, i)
            self._overlays[number] = (ram, file_id, bool(flags & 0x01000000))
        self._files = None
        self._cache = {}

    def _member(self, file_id):
        start, end = struct.unpack_from('<II', self._fat, 8 * file_id)
        return self.data[start:end]

    def overlay_ram(self, number):
        return self._overlays[number][0]

    def overlay(self, number):
        key = ('overlay', number)
        if key not in self._cache:
            _, file_id, packed = self._overlays[number]
            data = self._member(file_id)
            self._cache[key] = blz(data) if packed else data
        return self._cache[key]

    def arm9(self):
        """The ARM9 binary, its BLZ-compressed part unpacked (the module parameters name where that part ends)."""
        if 'arm9' not in self._cache:
            data = self.data[self.arm9_rom:self.arm9_rom + self.arm9_size]
            found = data.find(struct.pack('<II', 0xDEC00621, 0x2106C0DE))
            end = u32(data, found - 0x1C + 0x14) if found >= 0x1C else 0
            if end:
                data = blz(data[:end - self.arm9_ram]) + data[end - self.arm9_ram:]
            self._cache['arm9'] = data
        return self._cache['arm9']

    def files(self):
        """{path: file id} of NitroFS."""
        if self._files is None:
            self._files = {}

            def walk(directory, path):
                offset = u32(self._fnt, (directory & 0xFFF) * 8)
                file_id = u16(self._fnt, (directory & 0xFFF) * 8 + 4)
                while True:
                    kind = self._fnt[offset]
                    offset += 1
                    if kind == 0:
                        return
                    length = kind & 0x7F
                    name = self._fnt[offset:offset + length].decode('latin-1')
                    offset += length
                    if kind & 0x80:
                        walk(u16(self._fnt, offset), path + name + '/')
                        offset += 2
                    else:
                        self._files[path + name] = file_id
                        file_id += 1
            walk(0xF000, '')
        return self._files

    def file(self, path):
        return self._member(self.files()[path])


# ---------- A2M's archives ----------

def name_hash(name):
    """An entry's key in a ".urf": the CRC-32 of its upper-cased name."""
    return zlib.crc32(name.upper().encode('cp1252')) & 0xFFFFFFFF


class Urf:
    """An A2M resource archive (Rom_2D.urf, Rom_Audio.urf): 'KTUN', then the types ('RFMN'), the locales ('COLN') and
    each locale's table ('TAFN': name hash, size in words | flags << 30, offset in 32-byte units | flags << 27). Block tags
    are stored byte-reversed. Entries of different types can share a name (a background's bitmap and its palette do), so
    one is found by its type and name: `read(type_hash, name, locale=0)` gives it, decompressed."""

    def __init__(self, data):
        if data[:4] != b'KTUN' or data[12:16] != b'RFMN':
            raise ValueError('not an A2M archive')
        self.data = data
        total, count = struct.unpack_from('<II', data, 16)
        types = [struct.unpack_from('<III', data, 24 + 12 * i) for i in range(count)]
        kind = [None] * total
        for type_hash, first, size in types:
            for index in range(first, first + size):
                kind[index] = type_hash
        offset = 24 + 12 * count
        if data[offset:offset + 4] != b'COLN':
            raise ValueError('no locale table')
        locales = [struct.unpack_from('<II', data, offset + 8 + 8 * i) for i in range(u32(data, offset + 4))]
        self.tables = []
        for _, at in locales:
            if data[at:at + 4] != b'TAFN':
                raise ValueError('a locale has no entry table')
            self.tables.append({(kind[i], u32(data, at + 4 + 12 * i)): struct.unpack_from('<II', data, at + 8 + 12 * i)
                                for i in range(total)})

    def has(self, type_hash, name):
        return (type_hash, name if isinstance(name, int) else name_hash(name)) in self.tables[0]

    def read(self, type_hash, name, locale=0):
        size, offset = self.tables[locale][(type_hash, name if isinstance(name, int) else name_hash(name))]
        start = (offset & 0x07FFFFFF) * 32
        return decompress(self.data[start:start + (size & 0x3FFFFFFF) * 4])
