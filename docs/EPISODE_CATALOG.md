# Episode catalog and category sections

SHS reference: Android 1.0.9 `libshs09.so`, SHA-256
`b17aa4c71bc46666d414cafae6fac92bbcd755f3dcccd73975cf05f4a119665b`.
The locally supplied `decomp/shs/Episodes/shs_options.sav` supplies additional
original catalog evidence. CoD uses its supplied iOS 1.3.4 executable and
`decomp/cod/CoD Episodes/cod_options.sav` as references. These are user content
and are excluded from distributions. Game profiles select their own filenames
and validated save layouts; normalized catalog records remain shared.

## Native list behavior

`FUN_00078714` sorts downloaded records by the packed numeric key returned by
`FUN_0009794c`: `(signed16(pack_id) << 16) | signed16(episode_id)`. The first
two built-in entries are handled separately. `FUN_00078910` gets each record's
**category string** through `FUN_00097ea0` and inserts a header when that string
changes. The category pointer is at record `+0x2c`; the English episode title
is a separate pointer at `+0x18`, returned by `FUN_00097ecc`.

Consequently, `pack_id / 100` is not a reliable season name. In the original
catalog, pack 301 includes episodes under both Season 3 and Season 4. The
later A New Start and Troublemakers groups span several pack IDs. EXP resource
1 contains five localized **episode titles**, not these category names.

`FUN_0009b220` obtains the category from a download archive's `contents.bin`
(`DownloadContents` signature), passes it to `FUN_00097f24`, and attaches that
category to its episode records. `FUN_0009795c` serializes these records to the
native options save; `FUN_000980e4` reads them back. The Android reader consumes
all translations but its constructor currently retains the English title and
category for all locales.

`FUN_00078dd8` begins the built-in story section using APK string 82, Mega
Packs. `FUN_00079428` inserts string 238, My Saved Games, before saved episode
shortcuts. Built-in creation functions `0008d334`, `00092318`, and `000924b8`
assign Mega Packs to Football Star, the bundled Season 1 story, and The New
Girl. `00092170` assigns the novel bonus story APK string 302. These native
catalog IDs can differ from the IDs embedded in the corresponding EXP.

Headers use APK image pack 16, frame 76 (296 × 12), and font registry 2
(`ArialRoundedMTBold11`). Episode rows use alternating frames 82/83, pressed
frame 84 (all 296 × 42), with the existing play/resume icons.

The store list is a different path: `FUN_00070984` interprets
`EPISODE_LISTING_START/END` and `Orange Header:` / `Blue Header:` lines from
server configuration. Those store/purchase services remain outside the local
runtime.

## SHS native options wire schema

The supported catalog reader validates the entire following envelope. Numeric
fields below are big endian unless explicitly marked as uninterpreted bytes.
It accepts versions 16–18 through this envelope, and version 19 (the iOS HD
build) through the distinct envelope in [Version 19](#version-19-ios-hd-build)
below; other versions are rejected.

```text
OptionsCatalog :=
    signature       : bytes[12] = "SHS_OPTIONS\0"
    version         : s32 = 16 | 17 | 18
    ignored_header  : bytes[16 | 20]
    current_episode : OptionalCatalogEntry
    entry_count     : s32, 0..4096
    entries         : OptionalCatalogEntry[entry_count]
    pair_count      : s16, 0..4096
    ignored_pairs   : (String, String)[pair_count]
    if version >= 17:
        ignored_flag_17 : u8 = 0 | 1
    if version >= 18:
        ignored_flag_18 : u8 = 0 | 1
    EOF

OptionalCatalogEntry :=
    present         : u8 = 0 | 1
    if present:
        pack_id     : u16
        episode_id  : u16
        titles      : String[5]
        categories  : String[5]
        filename    : String
        download_id : s32

String :=
    byte_length     : u16, 0..32767
    bytes           : bytes[byte_length], no NUL
```

The Android `FUN_00092734` reader puts the current episode at byte 36. Its
ignored header comprises a discarded s32, four flag bytes, two native raw
four-byte values (`FUN_0004a568`), and four more flag bytes. The supplied
version-18 legacy file instead puts the current episode at byte 32. The
runtime tries these two fixed layouts and accepts exactly one that validates
all records, string pairs, versioned flags, and EOF. This difference is
recorded as a legacy envelope variant; it is not evidence that the platform
save formats are identical. Versions 16/17 and the 36-byte envelope have
authored test coverage; the original supplied file verifies version 18 and
the 32-byte envelope.

### Version 19 (iOS HD build)

A user-supplied HD iPad `shs_options.sav` (48549 bytes) uses signature
version 19, and does not fit either 16-18 layout: the entry count is not an
`s32` and no combination of the two fixed prefixes validates through EOF.
Byte-level analysis of that one file (cross-checked against `read_page`-style
manual decoding, not guessed) found a distinct, self-consistent envelope,
implemented in `_read_v19_catalog`:

```text
OptionsCatalogV19 :=
    signature       : bytes[12] = "SHS_OPTIONS\0"
    version         : s32 = 19
    ignored_header  : bytes[22]
    entry_count     : u16, 0..4096
    entries         : CatalogEntryV19[entry_count]
    pair_count      : s16, 0..4096
    ignored_pairs   : (String, String)[pair_count]
    ignored_trailer : bytes[200]
    EOF

CatalogEntryV19 :=
    present         : u8 = 0 | 1
    pack_id         : u16
    episode_id      : u16
    titles          : String[5]
    categories      : String[5]
    filename        : String
    alias           : String   -- plain-text, punctuation-stripped title;
                                   not present in versions 16-18, unused here
    download_id     : s32
```

There is no separate current-episode slot: the list starts immediately after
`entry_count`, and its first record in the one sample seen is a built-in
`pack_id=0, episode_id=0, download_id=-1` placeholder ("Football Season" /
"MEGA PACKS"). The 200-byte trailer's structure is unconfirmed -- it was
entirely zero in the one sample available, so the reader only requires it to
be present and to land exactly on EOF afterward; it does not validate its
content. This decode recovered 195 real serialized entries (183 after
deduplication, 25 categories, including "A New Start", numbered "Season N"
groups, "PREMIUM CONTENT", and several "Classic Set" packs) with filenames
matching the known EXP corpus, plus real string pairs such as `$USR`. That
end-to-end coverage across every entry is the evidence for this layout;
version 19 has authored synthetic test coverage in `test_episode_catalog.py`,
but only one real file has verified it so far.

Most strings decode as UTF-8. Some translated strings in the original options
file contain legacy byte values, so this reader falls back to Latin-1 for
those strings. This compatibility rule does not relax the strict UTF-8
validation of EXP metadata. The runtime currently uses English title/category
only. The file is limited to 4 MiB.

The supplied file contains 277 serialized list entries, plus a current-entry
record. Deduplication leaves 274 catalog records. Filename or exact
`(pack_id, episode_id, English title)` matching categorizes all 271 external
EXPs in `decomp/shs/Episodes`. Checks with the supplied APK and IPA produce
272 and 273 episode records respectively, including bundled stories, in 28
original groups with no numeric pack fallback. Adding the catalog to existing
libraries preserves content identities; repeating a full-folder import adds
zero episodes and leaves the manifest unchanged. These counts describe the
supplied inputs and establish catalog coverage, not full-story execution.

## CoD native options wire schema

CoD retains `SHS_OPTIONS\0`, so the signature alone cannot identify the game.
Native `SHSEngine::loadOptions` (`00019098`) accepts exactly version 17. Both
it and `saveOptions` (`000195b4`) place the current episode at byte 33:

```text
CoDOptionsCatalog :=
    signature       : bytes[12] = "SHS_OPTIONS\0"
    version         : s32 = 17
    ignored_value   : s32
    ignored_flags   : bytes[5]
    ignored_values  : s32[2]
    current_episode : OptionalCatalogEntry
    entry_count     : s32, 0..4096
    entries         : OptionalCatalogEntry[entry_count]
    pair_count      : s16, 0..4096
    ignored_pairs   : (String, String)[pair_count]
    EOF
```

`SHSEpisode::createFromStream:` (`00050b10`) consumes the same presence flag,
two shorts, five titles, five categories, filename and download ID as the
shared `OptionalCatalogEntry` above. Native `loadOptions` calls `loadRenames`
at `0001923e` and then destroys its stream. The writer calls `saveRenames` at
`0001975e` and immediately writes the file; there are no SHS trailing flags.

This was checked through Ghidra MCP. The decompiler truncates the Objective-C
continuations and misdecodes the load function's entry; read-only LLVM Thumb
disassembly supplied the continuation. Bytes at `00019130`, `00019232` and
`00019752` were cross-checked with Ghidra `read_memory`. No analysis mutations
or raw native output are shipped.

The supplied file validates to EOF with 80 list entries and a repeated current
entry, yielding 80 unique catalog records. It categorizes 79 of 80 distinct
external EXP hashes (103 filenames). One uncatalogued holiday story remains
under its numeric pack. The reader preserves supplied labels, including their
original mix of Volume and Season naming; it does not derive them from IDs.
Unknown CoD versions, wrong envelopes, extra data and incomplete records are
rejected. Only normalized English catalog metadata is retained; native runtime
strings, preferences and progress are discarded.

## Local import and persistence

Adding an episode folder also reads its `shs_options.sav` (SHS) or
`cod_options.sav` (CoD), when present. Matching is case-insensitive and uses the
selected game, determined from the supplied package on initial import or the
existing library on later imports. Other games' sidecars in a folder are
ignored; directly selecting the other game's catalog is rejected.
Selecting an individual EXP discovers a sibling sidecar. A catalog can also
be added explicitly through the episode file picker, drag/drop, or
`ContentLibrary.add_episodes([path])` without adding any new EXPs. The sidecar
is optional; the selected game's APK/IPA and EXP inputs remain sufficient to play.

Episode ZIPs use the same import path on desktop, iOS and the CLI, during
initial setup or later additions. The importer scans every subfolder inside
the archive for EXPs and the selected game's catalog, and also finds ZIPs
inside selected filesystem folders. A ZIP containing just a catalog can
update existing categories. ZIPs nested inside another ZIP are not expanded.
`__MACOSX` entries and AppleDouble `._` files are ignored.

Members are read individually and stored under their EXP hashes; archive paths
are never extracted. The library remains usable after the source ZIP is removed
or the library is relocated. Duplicate paths, absolute/traversing paths,
links, encrypted/unreadable members and invalid EXPs/catalogs reject the batch
without changing the library. ZIP limits are 10,000 entries, 64 MiB per EXP,
4 MiB per catalog and 2 GiB of selected uncompressed data per archive.

Only normalized catalog metadata is retained in the library. The native
options file, user strings, flags, and native progress are not copied or
applied. Optional `library.json` field:

```text
episode_catalog : CatalogEntry[], maximum 4096
CatalogEntry := {
    pack_id: u16,
    episode_id: u16,
    title: string,
    category: string,
    filename: string
}
```

Filenames are normalized to a case-insensitive basename and are only lookup
keys. No catalog path is opened. A matching filename handles native synthetic
IDs; an exact ID/title match handles renamed EXPs. Identical EXPs imported under
different filenames retain those names in the existing episode's `aliases`
field, and catalog matching considers those aliases too. Conflicting category
matches remain unknown. New catalog records replace the same ID/title/filename key;
unrelated entries remain available for episodes imported later.

Catalog and episode changes publish together by the existing atomic manifest
replacement. Invalid catalogs or EXPs abort the whole batch. Catalog-only
updates return zero newly added episodes. Category changes do not change the
APK/EXP content identities, save names, preferences, or saved progress. No
catalog or copied game titles are embedded in the executable.

Both initial and incremental import deduplicate by full EXP SHA-256, including
duplicates of bundled content, duplicates within one batch, repeated folders
and renamed byte-identical copies. Alias/catalog updates publish atomically
with new episodes and roll back on validation failure. Repeating the same
import is a no-op once its aliases and categories are known. Equal titles or
pack/episode IDs do not imply equal scripts/assets: differing hashes remain
separate editions with separate progress. Deduplication is local to each
game's library; the game's base assets continue to be part of save identity.

## Desktop browser contract

The desktop consolidates each category into one section, retaining its original
name. Mega Packs comes first; other groups are ordered by their minimum numeric
pack/episode key. The saved-game shortcuts precede these groups in Play/Resume.
Unknown loose episodes get an explicit numeric `Pack N` section; the runtime
does not invent a season label. Known bundled stories can use the categories
read from APK strings even without an options sidecar.

Collapsible headers, counts, 24px header hit areas, and Expand/Collapse All are
desktop browsing additions. The original 12px header artwork is unscaled and
centered within that hit area. Saved games start expanded; category sections
start collapsed. These fold states are view state, not episode visibility or
save state. Every installed episode remains present and searchable.

Search matches titles, filenames, aliases, and original category names. Search
results expand matching sections temporarily, without changing fold state.
Episode/title ordering applies within each section. Returning from an episode
detail screen restores the list's scroll and folds. Episode totals count unique
installed records, not duplicated saved-game shortcuts.

Tests cover both validated envelopes, truncation and corrupt counts/strings,
native alias IDs, ambiguous categories, atomic catalog/EXP imports, persistence,
original corpus coverage, category-based season boundaries, collapsible search,
scrolled/resized pointer targets, and navigation back to the same list position.
