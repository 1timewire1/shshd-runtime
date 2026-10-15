# Cause of Death store listing (`mtxprods`)

Cause of Death 1.4.7 (the free edition, `com.ea.causeofdeathfree.bv`) caches EA's in-app store catalogue in its
Documents folder as `Documents/mtxprods`. EA's MTX client downloads it from EA's store server at run time; it is not in
the IPA, so only a player with a device backup of the app has one. 1.3.4 has none. The SHS HD saves examined hold an
`mtxprods` too, but with the user record only and no products.

This fork reads it as an optional import for the episode info card (docs/COD.md, "Episode info"). The parser is
`cod/store.py`. Everything below was read from the owner's 1.4.7 listing (267 products), not decompiled; the field
meanings come from their names and values.

## Container

An Apple **NSKeyedArchiver** binary plist (`$archiver` `NSKeyedArchiver`, `$version` 100000). `$top.root` is an
`NSMutableArray` of three entries:

| Index | Class | Contents |
| --- | --- | --- |
| 0 | `EAMTX_UserInfo` | The player's record (below). **Personal data: never read further or kept.** |
| 1 | `NSMutableDictionary` | The products: sell id (string) -> `EAMTX_MTXProduct`. |
| 2 | `NSMutableDictionary` | Two lists of the same 267 sell ids (keys `" "` and `"new"`). |

Archive classes seen: `EAMTX_UserInfo` (1), `EAMTX_MTXProduct` (267), `NSMutableData` (267), `NSDate` (267),
`NSMutableDictionary` (8), `NSMutableArray` (6), `NSMutableString` (3).

### The user record (`EAMTX_UserInfo`)

Field names only, for recognising it: `hwid`, `eauid`, `anoneauid`, `devToken` (push token), `dmgId`, `bundle_Id`,
`appSellId`, `appProdId`, `appVersion`, `langCode`, `country`, `dob`, `email`, `username`, `passcode`, `registered`,
`marketOpt`, `facebookAppId`, `mayhemGamecode`, `trackingData` (analytics events with session ids and timestamps),
`eventsCounter`, `disabledEvents`, `messages`, `excludedMessages`, `userLoggingDisabled`, `appLoggingDisabled`,
`listUpdatedTime`, `itemsUpdatedTime`. It identifies the device and account it came from, so a raw `mtxprods` should
not be shared. The import never keeps any of it.

## A product (`EAMTX_MTXProduct`)

Every field is a string unless noted.

| Field | Meaning | Values in the owner's listing |
| --- | --- | --- |
| `sellId` | EA's store id; also the dictionary key | 828906-869087 |
| `prodIdentifier` | App Store product id | `com.ea.mtx.<sellId>` |
| `title` | Store name | e.g. "Chapter Eight: Endgame", "Volume 6: Mad Stranger" |
| `desc` | Store description, English | 41-258 characters; some start with blank lines |
| `releaseDate` | `NSDate` (seconds since 2001-01-01 UTC): the store upload, usually days before release | 2010-11-24 to 2014-07-04 |
| `itemPrice` | Price, six decimals | `0.990000` (145), `0.000000` (82), `1.990000` (22), up to `9.990000` |
| `currency` | Symbol | `$` (all) |
| `localCurrency` | Store region's currency | `CAD` (185, every paid product), `USD` (82, every free one) |
| `freeItem` | `1` for the free (Now Airing) copies | `0` (185), `1` (82) |
| `granted` | `1` when the device owns it. **The player's own; not kept.** | `0` / `1` |
| `version` | Content version | `1.0.0` (156), `1.0.1` (84), `1.0.2` (23), `1.0.3` (2), `3.0.0` (2) |
| `packSize` | Download size in bytes | |
| `consumable`, `downloadable`, `itemNew`, `category` | Constant | `0`, `1`, `0`, `" "` |
| `binPack` | `NSData`: a ZIP describing the download (below) | |

### `binPack`

A ZIP of two members:

- **`pack.info`:** text, e.g. `version: 1.0.0` / `build-by: CS MTX Utility 1.0` / `language: en` (`en` in all 267).
- **`contents.bin`:** binary, big-endian. Every record parses to its last byte with this layout. A `str` is a u16 byte
  length and that many UTF-8 bytes, with no terminator.

| Field | Type | Notes |
| --- | --- | --- |
| magic | 16 bytes | `DownloadContents` |
| version | u16 | 4 |
| name | str | Internal name; Now Airing copies end in " NOW AIRING" |
| unknown | i32, u16 | (9, 26) in 241 products, (65536, 0) in 15, (65540, 1) in 11; meaning unknown |
| categories | 5 x str | One per language slot, e.g. "VOLUME SIX", "Season 10", "SIDE STORIES" |
| file count | u16 | 1 (244 products), 2 (21), 6 (2) |
| files | count x file | |

Each file:

| Field | Type | Notes |
| --- | --- | --- |
| filename | str | The `.exp` the product installs, e.g. `6_8_Endgame.exp`, `Volume_6.exp` |
| pack | u16 | The EXP's pack id |
| episode | u16 | The EXP's episode id |
| titles | 5 x str | One per language slot |

Five language slots, as the episode catalogue's and the EXPs' own titles have (their order here is not verified). In
this listing all five hold the English text, in every product, so the listing has **no translated titles or
categories**.

## What it covers

- **Files:** the products name 187 distinct files.
  - 73 of the owner's 74 library episodes are named, and their (pack, episode) ids match. Volume One, the base game,
    was never sold.
  - The other 114 files: every chapter inside the Volume 2-13 and 15 sets (each with its own product and
    description), the Volume 14 and 16 sets, Magic School Books 1 and 2 (SHS cross-sells), "Surviving High School
    Preview", and a Side Stories 17-24 bundle.
- **docs/COD_RELEASE_DATES.md:** 184 of its 186 rows have a product. The missing two are Volume One and Volume 13's
  Interlude: The Break-Up.
- **Copies of one file:**
  - Most chapters from mid-2011 on have a paid On Demand product and a free Now Airing one, sometimes with a
    `_NA` / `_OD` / `_airing` / `_NOW_AIRING_ONLY` filename variant.
  - Sets and combos ("Chapters 1 & 2", "Side Stories Bundle: Detective Kalaba") are products that name several
    files.
- **Store data errors, left as they are:**
  - 7.6's file title says "Chapter Five".
  - Three products have a chapter name for their category: 5.5's and 5.6's Now Airing copies, and 5.8.
  - Typos: "Reatreats", "Prt a1".
  - One Now Airing description has lost its apostrophes to U+FFFD (5.5).
  - The 11.1 + 11.2 Now Airing combo reuses Black Magic Part 1's file with Chapter One's text.

## What the library keeps

Importing reads the products and nothing else (`read_store`). The library stores them as JSON in
`content/<sha256>.json`, and `library.json` records it:

```text
store : { file: "content/<sha256>.json", sha256: <sha256 of that file> }      (CoD libraries only)
```

The JSON file:

```text
{ format: "cod-mtxprods-products", version: 1,
  products: { <sellId>: Product } }
Product := every product field above except `granted` and `$class`, as stored (strings; releaseDate as the NSDate
           float), plus
           binPack  : the original ZIP bytes, base64 (byte for byte)
           contents : { name, unknown: [i32, u16], categories: [5 x str],
                        files: [{ file, pack, episode, titles: [5 x str] }] }
```

Keeping every product, including the set chapters, is deliberate: a later feature to split the Volume sets into
their chapters can use each chapter's own entry. The owner's listing keeps 462 KB of JSON.

## Import

- **Where it is found:** a file named `mtxprods` (any case) among the paths of a CoD import, as a loose file or
  anywhere inside a folder (`content._store_listing`). Archives are not searched for it. That means:
  - `cod_episodes/`, or beside the IPAs, in the import folder (staged_import.py);
  - the same places in a bulk .zip / .rar (extraction keeps it);
  - Add Episodes or a drop onto a CoD library, alone or with episodes. An existing library can gain one later.
- **Validation:** the file must be an NSKeyedArchiver plist of at most 16 MiB, with 1-5000 products. Each product's
  `binPack` must be a ZIP whose `contents.bin` parses exactly. Otherwise the import stops with an error and the
  library is unchanged.
- **Replacing:** two different listings in one batch are refused. A new listing replaces the library's.

## Matching an episode

`Store.product(record)`:
- Takes the products that name **exactly one file** whose name, without `.exp` and the variant suffixes above,
  matches the episode's filename or one of its aliases (case-insensitive).
- Products naming several files describe a set and are skipped.
- **Preference:** the On Demand (paid) copy, then text without U+FFFD, then the earliest upload.
- A Volume set's EXP (`Volume_6.exp`) takes its own set product, not its chapters'.

The info card (`PickerModel.info`) shows:
- the picker's own title;
- the airdate from docs/COD_RELEASE_DATES.md, not `releaseDate`;
- "Free", or the currency symbol and `itemPrice` ("$0.99");
- `desc`, trimmed.

Volume One has no product: with a listing imported, it shows the App Store listing's description (supplied by the
owner, `VOLUME_ONE_DESCRIPTION`), priced Free.
