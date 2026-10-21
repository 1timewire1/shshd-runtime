"""Validated EXP containers, independent of game profiles and presentation."""
from dataclasses import dataclass
from functools import lru_cache
import lzma
import struct
from collections.abc import Mapping

from .decode.bytecode import decode_program

MAX_PAYLOAD = 64 * 1024 * 1024


class ContentError(ValueError):
    """Missing, incompatible, or malformed user content."""


@dataclass(frozen=True)
class Metadata:
    pack_id: int
    episode_id: int
    titles: tuple[str, ...]

    @property
    def title(self):
        return self.titles[0]

    def to_bytes(self) -> bytes:
        """Encode the native five-title metadata record (resource 1)."""
        for value in (self.pack_id, self.episode_id):
            if type(value) is not int or not 0 <= value <= 65535:
                raise ContentError('Metadata IDs must be unsigned 16-bit integers')
        if len(self.titles) != 5 or any(not isinstance(t, str) for t in self.titles):
            raise ContentError('Metadata requires exactly five title strings')
        data = bytearray(struct.pack('>HH', self.pack_id, self.episode_id))
        for title in self.titles:
            try:
                encoded = title.encode('utf-8')
            except UnicodeError as error:
                raise ContentError('Invalid Unicode in localized title') from error
            if len(encoded) > 65535:
                raise ContentError('Localized title exceeds the native 16-bit length')
            data.extend(struct.pack('>H', len(encoded)))
            data.extend(encoded)
        return bytes(data)


def encode_exp(resources: Mapping[int, bytes]) -> bytes:
    """Write a deterministic native CSPUD archive with literal records.

    This constructs a new archive; it does not preserve an existing archive's
    physical offsets, compression, aliases or padding. Resource IDs and payload
    bytes are retained exactly. No game profile or image dependency is needed.
    """
    if not resources or len(resources) > 65536:
        raise ContentError('An EXP needs between 1 and 65536 resources')
    for resource, data in resources.items():
        if type(resource) is not int or not 0 <= resource <= 65535:
            raise ContentError('EXP resource IDs must be unsigned 16-bit integers')
        if not isinstance(data, bytes) or len(data) > MAX_PAYLOAD:
            raise ContentError(f'Invalid payload for resource {resource}')
    offset = 9 + 6 * len(resources)
    index, records = bytearray(), bytearray()
    for resource, data in sorted(resources.items()):
        if offset + 12 + len(data) > 0xffffffff:
            raise ContentError('EXP exceeds the native 32-bit archive size')
        index.extend(struct.pack('>HI', resource, offset))
        records.extend(struct.pack('>III', len(data), len(data), 0))
        records.extend(data)
        offset += 12 + len(data)
    return b'CSPUD' + struct.pack('>I', len(resources)) + index + records


class ExpArchive:
    """Validated, exact-ID CSPUD reader; native grouped fallback is unsupported."""

    def __init__(self, data: bytes):
        self.data = data
        if len(data) < 9 or data[:5] != b'CSPUD':
            raise ContentError('Not a CSPUD EXP archive')
        count, = struct.unpack_from('>I', data, 5)
        index_end = 9 + 6 * count
        if not count or index_end > len(data):
            raise ContentError('Invalid EXP index extent')
        self.entries = {}
        extents = {}
        for i in range(count):
            resource_id, offset = struct.unpack_from('>HI', data, 9 + 6 * i)
            if resource_id in self.entries:
                raise ContentError(f'Duplicate EXP resource ID {resource_id}')
            if offset < index_end or offset + 12 > len(data):
                raise ContentError(f'Invalid record offset for resource {resource_id}')
            stored, raw, flags = struct.unpack_from('>III', data, offset)
            end = offset + 12 + stored
            if end > len(data) or raw > MAX_PAYLOAD or stored > MAX_PAYLOAD:
                raise ContentError(f'Invalid record size for resource {resource_id}')
            if flags & ~1:
                raise ContentError(f'Unsupported EXP flags 0x{flags:x}')
            if not flags & 1 and stored != raw:
                raise ContentError('Literal EXP record has conflicting sizes')
            self.entries[resource_id] = offset
            extents[offset] = end
        last_end = index_end
        for start, end in sorted(extents.items()):
            if start < last_end:
                raise ContentError('Partially overlapping EXP records')
            last_end = end

    @lru_cache(maxsize=32)
    def read(self, resource_id: int) -> bytes:
        try:
            offset = self.entries[resource_id]
        except KeyError:
            raise ContentError(f'EXP resource {resource_id} is absent; grouped lookup is unsupported') from None
        stored, raw, flags = struct.unpack_from('>III', self.data, offset)
        payload = self.data[offset + 12:offset + 12 + stored]
        if not flags & 1:
            return payload
        if len(payload) < 13:
            raise ContentError('Truncated EXP LZMA wrapper')
        prop, dictionary, size1, size2 = struct.unpack_from('<BIII', payload)
        if prop >= 225 or dictionary > MAX_PAYLOAD or size1 != raw or size2 != raw:
            raise ContentError('Inconsistent or unsupported EXP LZMA header')
        try:
            # EXP supplies the output boundary; native streams need no end
            # marker. Raw decoding also avoids older liblzma versions rejecting
            # a known-size Alone header when an encoder includes an end marker.
            decoder = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=[dict(
                id=lzma.FILTER_LZMA1, dict_size=max(4096, dictionary),
                lc=prop % 9, lp=(prop // 9) % 5, pb=prop // 45)])
            result = decoder.decompress(payload[13:], max_length=raw)
        except lzma.LZMAError as error:
            raise ContentError(f'Invalid EXP LZMA stream: {error}') from error
        if len(result) != raw:
            raise ContentError('Truncated or oversized decoded EXP payload')
        return result

    def metadata(self) -> Metadata:
        data = self.read(1)
        if len(data) < 4:
            raise ContentError('Truncated episode metadata')
        pack, episode = struct.unpack_from('>HH', data)
        pos, titles = 4, []
        try:
            for _ in range(5):
                length, = struct.unpack_from('>H', data, pos)
                pos += 2
                if pos + length > len(data):
                    raise ContentError('Truncated localized title')
                titles.append(data[pos:pos + length].decode('utf-8'))
                pos += length
        except (struct.error, UnicodeError) as error:
            raise ContentError('Invalid localized episode metadata') from error
        if pos != len(data):
            raise ContentError('Unsupported trailing episode metadata')
        return Metadata(pack, episode, tuple(titles))

    def programs(self):
        programs = {}
        for resource_id in self.entries:
            data = self.read(resource_id)
            if data.startswith(b'kiwi'):
                try:
                    programs[resource_id] = decode_program(data)
                except ValueError as error:
                    raise ContentError(f'Invalid KiWi resource {resource_id}: {error}') from error
        return programs

