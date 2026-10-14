# EXP archive specification

Revision: 2026-09-13. Profile: the local **Surviving High School** corpus and the Android 1.0.9 native reader. This replaces the earlier abbreviated schema. [VM_SPEC.md](VM_SPEC.md) specifies embedded KiWi programs; [ENGINE_ABI.md](ENGINE_ABI.md) records their game services.

The ordinary archive, record, compression, and metadata layouts account for every indexed payload in the audited corpus. Native grouped resources and the EXPD prefix are documented separately because no matching fixtures have been identified. This does not establish compatibility with every other game or iOS engine version.

The compatible runtime's strict reader is [`content.ExpArchive`](../packages/engine/src/exp_runtime/content.py). Its user-supplied APK/episode library, resource-bank selection, supported-input restrictions, and new JSON save format are documented in [RUNTIME.md](RUNTIME.md); those are separate from the EXP wire format. Current reader restrictions are listed in section 10 below. Evidence snapshot names refer to private research files; see [PROVENANCE.md](PROVENANCE.md).

## 1. Evidence and notation

- **Native**: established from `libshs09.so`, an ARM little-endian 32-bit ELF loaded at Ghidra image base `0x10000`. Native addresses below are Ghidra virtual addresses, not file offsets.
- **Corpus**: observed in applicable local files; not necessarily enforced by the native reader.
- **Inferred / unresolved**: identified explicitly where evidence is incomplete.
- `u8`, `u16be`, `u32be`, and `u32le` mean unsigned integers of the stated width and byte order. Sizes and offsets count **bytes**. Preserve unsigned bit patterns even where native code later interprets a field as signed.

The APK member `lib/armeabi/libshs09.so` and Ghidra's backing library have the same SHA-256:

```text
b17aa4c71bc46666d414cafae6fac92bbcd755f3dcccd73975cf05f4a119665b
```

Primary evidence: `native-exp-loader.c` and `native-exp-index-lookup.asm`. Decompiled types and generated names are not original source declarations.

## 2. Top-level grammar

```text
EXP :=
    magic             : bytes[5] = "CSPUD"
    entry_count       : u32be
    index             : IndexEntry[entry_count]
    record_storage    : bytes[...]          # addressed by index offsets
    trailing_data     : bytes[...]          # optional; preserve if present

IndexEntry :=
    resource_id       : u16be
    record_offset     : u32be               # from byte 0 of this EXP

Record at record_offset :=
    stored_size       : u32be
    decoded_size      : u32be
    flags             : u32be
    stored_payload    : bytes[stored_size]
```

There is no filename, extension, timestamp, checksum, or payload-type field. Resource IDs belong to the game's resource namespace. Extraction names such as `file25001.kiw` are tool conventions, not stored filenames.

### 2.1 Header

| Absolute offset | Bytes | Field | Meaning |
| --- | ---: | --- | --- |
| `0x00` | 5 | `magic` | Hex `43 53 50 55 44`, ASCII `CSPUD` |
| `0x05` | 4 | `entry_count` | Number of index entries, big-endian |
| `0x09` | `6 * entry_count` | `index` | Packed entries without alignment padding |

The index ends at `9 + 6 * entry_count`. Native `FUN_0005e4c0` reads the count at `base + 5` and the index at `base + 9`; it does not itself compare the signature. A standalone reader should validate it. There is no independent archive version field in the recovered header.

### 2.2 Index entries and aliases

Entry `i` begins at `9 + 6*i`:

| Relative offset | Bytes | Field |
| --- | ---: | --- |
| `0` | 2 | `resource_id`, big-endian |
| `2` | 4 | Absolute `record_offset`, big-endian |

Different IDs may point to **exactly the same record offset**. These are aliases, not duplicate records to read sequentially. The corpus contains 16,800 index entries but 15,991 distinct physical record locations: 809 additional aliases across 215 shared records. For example, `Episodes/11_0_April_Fools.exp` maps IDs 26034–26038 to offset 1,787,546.

All audited indexes have unique IDs in ascending order and start with ID 1. These are corpus properties. Native lookup is a linear scan, so ascending order is not required by that routine. Do not calculate record lengths by subtracting adjacent index offsets: offsets can repeat, and index order is not a physical layout contract.

The native index expands each six-byte entry to an eight-byte in-memory structure. That padding is not stored. Native lookup reads IDs as signed shorts; preserve the wire `u16` and apply the caller's signed interpretation at the engine boundary.

### 2.3 Record header and extent

| Relative to `record_offset` | Bytes | Field | Meaning |
| --- | ---: | --- | --- |
| `+0` | 4 | `stored_size` | Stored payload length, excluding this 12-byte header |
| `+4` | 4 | `decoded_size` | Expected payload length after decompression |
| `+8` | 4 | `flags` | Bit 0 selects LZMA; other bits unresolved |
| `+12` | `stored_size` | `stored_payload` | Literal bytes or an EXP LZMA wrapper |

The record ends at `record_offset + 12 + stored_size`. `FUN_0005ded4` decodes the three big-endian fields; `FUN_0005e0fc` opens the stream at `record_offset + 12`.

Native `FUN_00059b10` tests **`flags & 1`**. A size mismatch is not a native compression indicator. Only flags 0 and 1 occur locally:

| Flags | Logical entries | Corpus relationship |
| --- | ---: | --- |
| `0` | 7,545 | `stored_size == decoded_size`; literal payload |
| `1` | 9,255 | `stored_size < decoded_size`; section 3 compression |

For literal records, native code returns the stored stream. A robust reader should report a size mismatch rather than guessing compression. Preserve unknown flag bits and report that their meaning is unsupported.

### 2.4 Physical ordering and trailing bytes

Sorting the **distinct** record offsets gives contiguous extents immediately after the index in all 274 archives. No alignment bytes are needed between records. This is validation evidence, not a reason to ignore explicit offsets.

`Episodes/61_SKI_TRIP.exp` has 70 zero bytes after its final record, starting at offset 4,621,683. Thus `last_record_end == file_size` is not universal. Preserve trailing bytes for a lossless edit; their purpose is unresolved. There is no verified footer structure.

## 3. EXP LZMA wrapper

Offsets here are relative to `stored_payload`. Its integers are little-endian, unlike the archive.

| Payload offset | Bytes | Field | Observed / native meaning |
| --- | ---: | --- | --- |
| `0` | 1 | `properties` | LZMA1 `lc`, `lp`, `pb` encoding |
| `1` | 4 | `dictionary_field` | Little-endian LZMA dictionary field; native adapter consumes and ignores it |
| `5` | 4 | `output_size` | LE output allocation and decode limit used by native adapter |
| `9` | 4 | `output_size_copy` | Equals `output_size` throughout corpus; consumed but unused by adapter |
| `13` | `stored_size - 13` | `lzma_body` | Raw LZMA1 stream |

For property byte `p`, `lc = p % 9`, `lp = (p // 9) % 5`, and `pb = p // 45`. The native reader rejects `p >= 225`. Every compressed entry starts with `5d 00 10 00 00`: `lc=3`, `lp=0`, `pb=2`, dictionary field 4096. Both inner size words equal the outer `decoded_size` for all 9,255 entries.

The standard `.lzma` header has the same property/dictionary prefix but one **64-bit** little-endian output size at bytes 5–12. EXP instead repeats a 32-bit size. Passing the original header to a standard decoder therefore declares the wrong size. The standard prefix and formula are defined in the official [LZMA SDK specification](https://www.7-zip.org/sdk.html).

### 3.1 Native behavior

`FUN_00059b10` reads the property byte, discards four bytes through the BE integer reader, then reads eight bytes. It reconstructs only the first four of those eight as a **little-endian** output length. Consuming and discarding the dictionary field through a BE helper does not establish BE dictionary semantics.

It allocates the entire output and calls `FUN_0005940c` with property components, remaining compressed bytes, and output size. It does not pass the dictionary field to that decoder. Neither the second size copy nor the outer `decoded_size` is checked by this adapter. Native handling of inconsistent sizes is weaker than the reader profile below.

### 3.2 Portable decoding recipe

Decode the raw LZMA1 body using the wrapper's properties and an output limit
of exactly `decoded_size`:

```python
import lzma
import struct

def decode_exp_lzma(payload: bytes, decoded_size: int) -> bytes:
    if len(payload) < 13:
        raise ValueError("truncated EXP LZMA wrapper")
    props, dictionary, size1, size2 = struct.unpack_from("<BIII", payload)
    limit = 64 * 1024 * 1024  # Runtime profile's allocation limit.
    if (props >= 225 or dictionary > limit or not 0 <= decoded_size <= limit
            or size1 != decoded_size or size2 != decoded_size):
        raise ValueError("unsupported or inconsistent EXP LZMA header")
    decoder = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=[dict(
        id=lzma.FILTER_LZMA1, dict_size=max(4096, dictionary),
        lc=props % 9, lp=(props // 9) % 5, pb=props // 45)])
    result = decoder.decompress(payload[13:], max_length=decoded_size)
    if len(result) != decoded_size:
        raise ValueError("wrong decoded size")
    return result
```

Checking both size copies and limiting allocations are runtime validation
policies, not native checks. Invalid or unsupported LZMA properties and corrupt
streams raise `lzma.LZMAError`; the runtime reports these as `ContentError`.

The historical corpus audit compared this bounded raw decoder with a rebuilt
LZMA-Alone header containing one LE 64-bit decoded size. All 9,255 entries
produced identical bytes with both approaches and with the previous decoder's
oversized 1 MiB dictionary. That oversized dictionary explains why the BE
assumption worked locally; it does not establish the field's byte order.

The raw recipe also supports authored streams containing an end marker.
Rebuilding a known-size Alone header for those streams fails with liblzma
5.2.5 and earlier, as documented in the upstream
[LZMA format notes](https://github.com/tukaani-project/xz/blob/master/doc/lzma-file-format.txt).
CPython's [Windows build dependencies](https://github.com/python/cpython/blob/3.14/PCbuild/get_externals.bat)
include xz 5.2.5, explaining why this combination failed in Windows CI while
passing with newer liblzma on macOS. Retain raw decoding on every platform;
the fixture encoder does not need a platform-specific workaround.

Do not require an LZMA end marker for completion. The audited raw decoders have not reached EOS when the required output size is produced, and known-size LZMA-Alone decoding succeeds. Decoding beyond that size can produce extra bytes from remaining range-coder state. Output length is the boundary; returning fewer bytes is not success. Exact compressed-byte consumption and optional end-marker behavior for other encoders remain uncharacterized.

## 4. Episode metadata, resource ID 1

The decoded payload of ID 1 has no signature. All 274 archives use:

```text
EpisodeMetadata :=
    pack_id           : u16be
    episode_id        : u16be
    localized_titles  : LengthPrefixedUTF8[5]

LengthPrefixedUTF8 :=
    byte_length       : u16be
    utf8_bytes        : bytes[byte_length]
```

The first string length is at byte 4. Subsequent lengths follow the preceding string immediately. There is no language-count field, NUL terminator, alignment padding, or description field in this observed structure. Consume all five strings, including repeated titles and empty strings if encountered. Lengths count encoded bytes, not characters.

All 1,370 titles are valid UTF-8, contain no NUL bytes, and consume their payloads exactly. Native general string reader `FUN_0004b138` also decodes UTF-8 sequences into its byte-string representation; its limited character conversion is not a Latin-1 wire encoding. The exact caller selecting an episode's locale remains unresolved.

The language order is **inferred from translated title content**, corroborated
by the same order in native menu strings 118–122:

| Index | Language | Example from `10_The_Wrong_Side_of_Town.exp` |
| --- | --- | --- |
| 0 | English | `10: The Wrong Side of Town` |
| 1 | French | `10 - En territoire hostile` |
| 2 | Italian | `10: Il quartiere sbagliato` |
| 3 | German | `10. Falsches Ende der Stadt` |
| 4 | Spanish | `10: La zona chunga` |

These are title translations, not a directory of translated scene scripts.
The desktop can select a title slot independently of gameplay; see
[title-language behavior and package inspection](MAIN_MENU.md#episode-title-languages).

The old schema's `description` was the French title. Repeated English titles obscured the distinction. `pack_id` and `episode_id` are retained descriptive names. Native menu categories are separate strings supplied by the download catalog and retained in `shs_options.sav`; they cannot be inferred universally from these two IDs. See [the catalog schema](EPISODE_CATALOG.md) for the recovered record and grouping rules. Complete download-version semantics remain unresolved.

## 5. Payload types and resource IDs

After removing the record wrapper and compression, identify content from its signature or the engine's explicit resource use. There is no archive type tag.

| Payload | Signature / identification | Logical entries |
| --- | --- | ---: |
| Episode metadata | ID 1, section 4 | 274 |
| KiWi script | `6b 69 77 69 02` (`kiwi`, version 2) | 987 |
| PNG | `89 50 4e 47 0d 0a 1a 0a` | 14,891 |
| JPEG | `ff d8`, then JPEG markers | 516 |
| RIFF WAVE | `RIFF` at 0, `WAVE` at 8 | 17 |
| ID3-tagged audio | `ID3`; inspect following frames for codec | 103 |
| MPEG audio candidates | MPEG sync prefix without leading ID3 | 12 |

Audio categories are signature classifications, not complete codec validation. No other payload signature was found locally. Grouped-resource payloads have not been identified among these files.

`.dat` is the extractor's fallback extension, not a single binary format. In particular, not every `.dat` is episode metadata. PNG, JPEG, and audio retain their own codec specifications inside the archive. Separate custom asset files and Android base resource banks are outside the CSPUD container schema. See [UI_ASSETS.md](UI_ASSETS.md) for layout/image packs and [MINIGAMES.md](MINIGAMES.md#6-sprite-atlas-and-glyph-font-payload-schemas) for ABGR sprite atlases, signed composites and binary glyph-font payloads.

Numeric ranges do not establish resource types. `Episodes/1_1_Magic_School.exp` has WAVE/audio at IDs 26051–26059. Treating every value in 20000–30000 as a scene link is incorrect. Scripts also refer to assets supplied by the application, so absence from an EXP alone does not prove a broken reference.

## 6. Native grouped-resource lookup extension

This is **native evidence without an identified corpus fixture**. It differs from aliases and is not implemented by the Python extractor.

At `0x0005de4c`, lookup returns the first exact ID match. Otherwise it returns the entry with the greatest signed ID below the request, with the candidate initialized to -1. Fallback candidates are therefore nonnegative; no candidate returns -1. The routine does not require sorting.

`FUN_0005e1b0` decompresses that record. An exact ID match returns the entire payload. Otherwise it interprets the decoded payload as:

```text
GroupPayload :=
    unknown_header    : bytes[4]             # consumed, not compared
    member_count      : u8                   # native reads signed byte
    member_ids        : u16be[member_count]
    member_offsets    : u32be[member_count]   # from decoded group start
    member_data       : bytes[...]
```

For matching member `j`, start is `member_offsets[j]`; end is the next member's offset or decoded stream length for the last member. The offset origin follows from subtracting the current header/table position before skipping forward. There is no extra sentinel offset after the last member.

The group signature, count limits beyond positive signed-byte values, member ordering requirements, and content usage remain open. Native missing-member handling is unsafe for some malformed inputs. Require a matching member and valid extents in a new reader; report unsupported groups explicitly. Do not return the nearest lower resource as if it were the requested one.

## 7. EXPD outer prefix

`FUN_0008b0d8` checks the filename for `.expd`. That path consumes one BE 16-bit value and one length-prefixed string before passing the remaining bytes to the EXP loader:

```text
EXPD candidate :=
    unknown_value     : u16be
    prefix_string     : LengthPrefixedUTF8
    archive           : EXP
```

Offsets then refer to the embedded `CSPUD` start, because the loader receives a new buffer containing only the remaining archive. The prefix fields are not established as a version or title. No `.expd` files are present locally; this extension lacks fixture and round-trip validation.

## 8. Concrete decoding example

`Episodes/10_1_300s_A_Crowd.exp` is 567,705 bytes. Its first bytes are:

```text
43 53 50 55 44 00 00 00 3c   # CSPUD, 60 entries
00 01 00 00 01 71            # ID 1, record offset 369
61 a9 00 00 01 a9            # ID 25001, offset 425
61 aa 00 00 2b 61            # ID 25002, offset 11105
```

The first record starts at `9 + 6*60 = 369`:

```text
00 00 00 2c 00 00 00 5e 00 00 00 01   # stored=44, decoded=94, flags=1
5d 00 10 00 00 5e 00 00 00 5e 00 00 00
00 01 ba 6a 00 11 7e fe d0 4d 66 2a 94 bf de 25
0a 3a 3d 1c dc 93 3d 96 32 e3 da 13 68 00 00
```

After the record header are the 13-byte wrapper and 31 compressed bytes. The record ends at `369 + 12 + 44 = 425`. Its decoded payload is:

```text
03 e9 00 01                  # pack 1001, episode 1
# The following 18-byte field occurs five times:
00 10 31 3a 20 33 30 30 27 73 20 41 20 43 72 6f 77 64
# length 16, UTF-8 "1: 300's A Crowd"
```

Total: `4 + 5*(2 + 16) = 94` bytes. String boundaries come from lengths, not a NUL scan.

## 9. Reader and writer requirements

For the documented reader profile:

1. Validate `CSPUD`, index extent, and all record/header extents using checked arithmetic. Bound decompression allocations.
2. Use absolute offsets and retain IDs and aliases. Cache physical records without losing logical entries.
3. Use bit 0 for compression. Verify all three decoded-size values agree for compressed records in this profile; report discrepancies.
4. Decode before signature detection. Read all five metadata titles and parse scripts with [VM_SPEC.md](VM_SPEC.md).
5. Preserve opaque payloads, unknown flags, and trailing bytes. Investigate partial overlaps rather than silently normalizing them away.

A writer targeting known files emits BE outer fields, the LE compression wrapper, recalculated absolute offsets, and preserved resource IDs. Literal records use flags 0 and equal sizes. Compressed records use flags 1, a property/dictionary prefix, two LE size copies, and raw LZMA1 data. Retaining original compressed records is the only currently verified way to preserve their byte identity. New encoders may produce different bytes for identical content; recompressed archives have not been tested in a live game. Grouped-resource and EXPD writing remain unverified.

UI image/layout resource payloads used by the same engine are specified in
[UI_ASSETS.md](UI_ASSETS.md). The compatible runtime reads the original
layout bank and supported ARGB/alpha image packs for dialogue. These payload
schemas do not change the EXP archive envelope or resource-bank ID rules.

## 10. Reproduction and implementation gaps

```sh
uv run --locked python tools/audit_format.py Episodes extract/assets/Assets > docs/format-audit.json
```

`format-audit.json` records input hashes, counts, alias/title examples, compression comparisons, and trailing bytes. It covers 274 paths, 480,375,126 archive bytes, and 520,872,272 decoded bytes counted per logical entry, with no reported structural issues. Duplicate archives and aliases are included. The audit checks contiguous records as a corpus property, beyond the requirements of a general offset-based reader.

The standalone runtime uses the strict `content.ExpArchive` reader:

| Component | Implemented behavior / remaining limit |
| --- | --- |
| Compression | Bit 0 selects compression; LE wrapper fields and all three decoded sizes are validated |
| Metadata | All five length-prefixed UTF-8 titles are read |
| Resource lookup | Exact numeric IDs and aliases; grouped fallback and EXPD remain unsupported |
| Input validation | Rejects unknown flags, malformed extents, conflicting sizes and partial overlaps; decoded payloads are bounded |
| Bytecode | Lossless KiWi decoding and actual VM control flow; linked execution remains unsupported |
| Writing | Built-in Football Star extraction emits literal records; general recompression and grouped/EXPD writing are unverified |

The earlier heuristic extractor and Ren'Py converter remain in the original
research project. Their legacy dictionary and metadata interpretations do not
define this runtime's reader or the EXP wire format.

## 11. Runtime libraries and game identity

The EXP wire format is shared by SHS and CoD; its pack/episode numbers do not
reliably identify a game. The selected runtime library supplies that identity.
New `library.json` files use `format: exp-content-library`, `version: 1`, and
`game: shs|cod`. Profiles are `shs-android-1.0.9`, `shs-ios-assets-v1` and
`cod-ios-assets-v1`; the game, profile and source package must agree.

Legacy `shs-content-library` versions 1 (APK), 2 (IPA) and 3 (IPA plus music
APK) remain readable in place. Primary source and episode records retain
complete SHA-256 identities; filenames use those hashes. SHS's optional music
APK stays outside the save identity and never contributes artwork/scripts/fonts.
See [IPA.md](IPA.md) and [COD.md](COD.md) for platform-specific resource contracts.
