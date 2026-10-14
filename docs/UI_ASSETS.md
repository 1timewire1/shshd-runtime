# SHS native UI asset schemas

Revision: 2026-09-13. Reference: Android 1.0.9 `libshs09.so`, native SHA-256
`b17aa4c71bc46666d414cafae6fac92bbcd755f3dcccd73975cf05f4a119665b`.
These are resource **payload** formats used by the engine, separate from the
[EXP envelope](./SCHEMA.md) and [KiWi bytecode](./VM_SPEC.md).
All artwork and layout records come from each player's APK/IPA and episodes.
The numeric IDs below describe Android. [IPA.md](IPA.md#resource-banks-and-local-extraction)
records the inspected iOS mapping and its separate host UI role lookup.

The compatible readers live in `packages/formats/src/exp_runtime/ui_assets.py`. Signed counts must
be nonnegative in supported inputs; reads must fit the payload, and decoded
pixel allocations are bounded. Reject unsupported encodings explicitly.
The defensive checks are reader policy, not evidence that the original engine
handled malformed files safely.

## 1. Resource paths

Native numeric APK resources normally use `assets/Assets/<decimal ID>`.
`FUN_0004b4fc` appends **`.mp3`** for IDs 16, 290, 446, 496, 499, and 502.
That suffix does not determine the payload encoding: **16.mp3 is an image
pack**, with 108 images. Named `fonts/` and `images/` resources have their own
namespace and do not alias numeric IDs.

`FUN_0008981c` loads the following UI resources:

| ID | Contents / role |
| --- | --- |
| 14 | Layout bank: 82 layouts, 7,025 bytes |
| 126 | Common image pack: 60 images, portrait frames, box fill, footer |
| 16 | Additional image pack: 108 images and composite-part records |
| 204 | Theme 1 box skin: 14 images |
| 220 | Theme 2 box skin: 14 images |
| 236 | Default/gold box skin: 14 images |
| 252 | Theme 3 gray box skin: 14 images |
| 268 | 128 × 150, one-byte portrait mask |

The layout bank binds image slot 0 to 126, slot 1 to 268, slot 2 to the active
skin, and slot 3 to 16. Other slots participate in other screens and have not
all been traced. Do not treat a layout image-slot number as an APK resource ID.

## 2. Layout bank

Evidence: `FUN_0005f998`, `FUN_0005760c`, `FUN_0005892c`, `FUN_00057400`,
`FUN_000575c8`; research output in `native-ui-layout.c`.
All multibyte fields are **big-endian**. There is no magic signature.

```text
LayoutBank {
    image_slot_count : s8
    font_slot_count  : s8
    other_slot_count : s8
    color_count      : s8
    colors           : s32[color_count]
    layout_count     : s16
    layouts          : Layout[layout_count]
}

Layout {
    design_width  : s16
    design_height : s16
    node_count    : s16
    nodes         : Node[node_count]
}

Node {
    base     : s16[4]     // x1, y1, x2, y2
    relative : s16[4]     // matching Q12 coefficients
    flags    : u8
    payload  : variant(flags & 15)
}
```

Resource 14's slot counts are `(6,2,0,0)`. Zero colors means no color words
follow the counts. Node payload sizes are:

| Low nibble | Payload | Established use |
| --- | --- | --- |
| 0 | s16 | Single reference/index; screen-dependent |
| 1 | s16, s16 | Image bank slot and frame index in observed image nodes |
| 2, 3, 4, 5 | s8 | Typed node reference; complete rendering semantics unresolved |
| 6 | empty | Geometry-only rectangle |
| 7 | s8 | Referenced layout index |

Bit `0x10` initializes a visibility bit. Visibility and geometry are distinct:
hidden nodes still occupy IDs and can be queried for placement. Other flag
semantics and the complete legacy layout renderer are not implemented.
Kinds 8–15 are unsupported by the compatible parser.

For current parent rectangle `(x,y,w,h)` and design dimensions `(W,H)`:

```text
dx = w - W; dy = h - H
left   = x + base.x1 + ((dx * relative.x1) >> 12)
top    = y + base.y1 + ((dy * relative.y1) >> 12)
right  = x + base.x2 + ((dx * relative.x2) >> 12)
bottom = y + base.y2 + ((dy * relative.y2) >> 12)
```

The shifts are signed arithmetic shifts, including negative products. Return
`(left,top,right-left,bottom-top)`. Rectangle corners are not stored as widths.

Native node ID zero is the layout's current root rectangle. Other IDs enumerate
nodes in recursive preorder, starting at one. A kind-7 reference contributes
one ID for its own rectangle, followed by every node of the referenced layout.
The child's current rectangle is the reference rectangle; its design size
comes from its own header. Reject cycles and bound recursive expansion.

`FUN_000a9a0c` selects layout **17** and sets its root to `(0,0,320,480)`.
Some resulting node IDs are:

| ID | Rectangle `(x,y,w,h)` | Dialogue use |
| --- | --- | --- |
| 2 | `(0,-188,480,720)` | Background geometry reference |
| 3 | `(20,296,280,126)` | Dialogue group |
| 8 | `(37,304,246,98)` | Body measurement rectangle |
| 46 / 0x2e | `(122,265,194,31)` | Main-character name reference |
| 48 / 0x30 | `(-7,225,128,128)` | Main-character portrait reference |
| 76 / 0x4c | `(4,265,194,31)` | Other-character name reference |
| 78 / 0x4e | `(199,225,128,128)` | Other-character portrait reference |
| 106 / 0x6a | `(17,265,286,31)` | Name without portrait |

These are queried rectangles, not necessarily final sprite bounds. Cocos
anchors, name sizing, portrait offsets and text overhang apply afterward.
See [UI_FIDELITY.md](UI_FIDELITY.md#dialogue-panel-composition).

## 3. Image packs

Evidence: `FUN_0005afbc` and `FUN_00054f90` in `native-image-pack.c`.
The entry point first recognizes PNG or JPEG and sends it to the platform
image decoder. Otherwise it consumes this **big-endian** binary structure:

```text
ImagePack {
    flags                : u8
    declared_frame_count : s16
    sequence_count       : s8
    if sequence_count > 0 {
        sequence_base        : s16
        sequence_entry_count : s16
        sequences            : Sequence[sequence_count]
    }
    part_group_count : s16
    part_entry_count : s16
    part_groups      : PartGroup[part_group_count]
    transform_count  : s16
    transforms       : Transform[transform_count]
    if !(flags & 8) {
        pixel_marker : s16
    }
    image_count : s16
    images      : Image[image_count]
}

Sequence {
    count   : s8
    entries : (flags & 4 ? s16 : s8)[count]
    // Add sequence_base to each stored entry.
}

PartGroup {
    count : s8
    parts : Part[count]
}
Part {
    image_ref : flags & 1 ? s16 : s8
    dx        : flags & 2 ? s16 : s8
    dy        : flags & 2 ? s16 : s8
}

Transform { source : s16; destination : s16; operation : s8; }

Image {
    width : flags & 32 ? s16 : u8
    if width != 0 {
        height : flags & 32 ? s16 : u8
        pixels : pixel[pixel_count = width * height]
    }
}
```

Sequence and part-entry totals describe the sums of the individual group
counts. Signed negative references occur in real composite records; preserve
them. The current dialogue renderer accesses positive primitive image indices,
and does not execute sequence animations or composite-reference rendering.
The declared frame count and the later image count are separate fields; do
not infer payload length from the former. Flag `0x10` is retained without
assigning an unverified meaning.

### Pixel encodings

| Marker / condition | Stored pixels | Compatible representation |
| --- | --- | --- |
| -1, bit 8 clear | Four bytes **A,R,G,B** per pixel | R,G,B,A |
| -2, bit 8 clear | One byte per pixel | A / mask byte |
| Other marker, or bit 8 set | Legacy path; not decoded by the inspected sprite upload branch | Explicitly unsupported |

Rows are tightly packed in the resource. The native loader copies them into
power-of-two GPU allocations, but that GPU stride is **not** an on-disk stride.
There is no universal 52-byte image header and these supported records are not
RGB565. Earlier experimental asset converters do not define this format.

Zero width consumes no height or pixel bytes: the slot is a placeholder for a
generated image. Transform records specify its source and orientation. For
source coordinates `(x,y)` in a `w × h` image:

| Operation | Destination `(x,y)` | Destination size |
| --- | --- | --- |
| 0 | `(x,y)` | `w,h` |
| 1 | `(x,h-1-y)` | `w,h` |
| 2 | `(w-1-x,y)` | `w,h` |
| 3 | `(w-1-x,h-1-y)` | `w,h` |
| 4 | `(y,x)` | `h,w` |
| 5 | `(h-1-y,x)` | `h,w` |
| 6 | `(y,w-1-x)` | `h,w` |
| 7 | `(h-1-y,w-1-x)` | `h,w` |

The supported transform path requires literal RGBA sources and distinct
placeholder destinations. A separate native caller flag can remap operations;
that path is not used by the UI packs decoded here and remains unsupported.

### Portrait mask

For ordinary PNG/JPEG portraits, `FUN_0005afbc` passes resource 268 to
`FUN_00059eb4`. Align a portrait of size `(w,h)` within the mask at
`((128-w)/2,150-h)`, using integer division. The mask acts on each pixel's four
channels with the integer multiplier `(255-mask_byte)/255`. Therefore a zero
mask byte keeps the pixel; every nonzero mask byte clears its RGBA channels.
It is not a conventional continuous alpha mask.

After applying the mask, `FUN_0005afbc` subtracts 12 from the decoded image's
height before calling `FUN_001755f0` to upload its texture. The image accessors
`FUN_00139d68` and `FUN_00139d70` return width at offset 4 and height at offset 0,
respectively. Width and row stride stay unchanged: the final 12 rows are
omitted from the texture, and the portrait sprite uses the reduced height.
This crop is a runtime operation, not an on-disk PNG or image-pack header field.
`DialogueRenderer.portrait()` performs it after masking and before horizontal
flipping, returning the same cropped texture to dialogue, choices and the
appearance picker. Consumers position its center using the separately halved
texture and frame heights (see [UI_FIDELITY.md](UI_FIDELITY.md#box-portrait-and-text-placement));
they must not crop it a second time or trim additional transparent rows.
Source resources remain unchanged.

Imported `SHS_The_New_Girl.exp` includes 256 × 256 and 226 × 256 indexed PNG
portraits, larger than the Android mask. The EXP metadata has no density field,
and the available Android PNG loader does not rescale them. The desktop renderer
therefore applies an explicit compatibility conversion before masking: an
oversized RGBA portrait with even dimensions that fits within twice the mask's
dimensions is reduced by two on both axes. Pillow's BOX resampling uses
premultiplied alpha, preserving aspect ratio without mixing hidden RGB into
visible edges. These variants become 128 × 128 and 113 × 128, respectively.
The subsequent native 12-row crop yields 128 × 116 and 113 × 116 textures.
Normalization leaves native-size portraits byte-for-byte unchanged; other
oversized images still fail explicitly with their dimensions and modes.
Normalization does not modify imported resources. The 2× scale and resampling
filter are compatibility inferences, not verified behavior from an original
release supporting these larger variants. The native mask alignment and binary
rule then apply normally.

## Sprite atlases and glyph fonts

The main menu additionally uses the resource-13 offset string bank and
resource-532/533 fonts with embedded ARGB glyphs. Their schemas and native
consumers are documented in [MAIN_MENU.md](MAIN_MENU.md#3-additional-resource-schemas).

Episode/week titles use PNGs 528/530 with external glyph descriptors 529/531.
These use the six-byte font header and byte glyph records described in the
mini-game schema, with the PNG dimensions supplying atlas bounds.
[TITLE_SCREENS.md](TITLE_SCREENS.md) records their metrics, consumers and
title-specific positioning; they are not ABGR sprite packs or the dialogue's
named bitmap-font format.

Mini games also use a different payload path: big-endian atlas metadata followed
by square **ABGR** pixels. Football atlas 290 includes signed nested composites;
grid atlas 446 includes tile/arrow art, while 522/523 pair a glyph atlas with
binary font metrics. The complete supported schemas and evidence are in
[MINIGAMES.md](MINIGAMES.md#6-sprite-atlas-and-glyph-font-payload-schemas).
Do not parse these as the literal ARGB image packs above, even when their APK
filenames use a misleading `.mp3` extension.

## 4. Verification boundary

All 82 supplied layouts parse to the exact end of resource 14 and expand without
cycles. Common/UI skins, resource 16, and the portrait mask also parse to their
exact ends, including generated frames. Authored tests exercise signed layout
scaling, recursive node numbering, every orientation with an asymmetric image,
ARGB channel order, mask alignment, truncation and invalid references.

This documents the complete record sequences for the recovered profiles. The
remaining legacy pixel path, composite renderer, typed-node behavior outside
the dialogue subset, and animation semantics are explicitly unresolved. Full
game fidelity still requires those features and comparison with an original
running game; successful parsing alone does not establish visual equivalence.
