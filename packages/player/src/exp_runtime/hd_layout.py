"""The iOS HD build's layout bank (resource 16) and image packs, read directly.

HD renumbered its low resource ids: 13/14 are image packs, 15 the string bank and
16 the layout bank, which `LayoutBank.parse` reads unchanged (see
legacy/findings.md, "HD layout bank decoded"). Every layout is Android's doubled,
and the root screens are the full 768x1024 frame, so results here are reported in
the same layout *units* the renderers use (half an HD layout unit), in the
coordinates of whatever rectangle the caller supplies.

Widget nodes name an image as (slot, frame); `SHSEngine::initPermanents` attaches
slot -> pack as `SLOT_PACKS` (slot 2 is the per-theme box pack).
"""
from functools import lru_cache

from . import graphics as pygame

from .content import ContentError
from .ui_assets import ImagePack, LayoutBank, Rect, UIAssetError

BANK_ID = 16
STRINGS_ID = 15
SLOT_PACKS = {0: 155, 1: 311, 3: 32, 5: 315, 8: 67}
# Android box packs 204/220/236/252 (themes 1, 2, 0, 3) ship as 247/263/279/295.
THEME_BOX_PACKS = {1: 247, 2: 263, 3: 295}
DEFAULT_BOX_PACK = 279
# HD's frame is 384x512 layout units; the 320x480 column every renderer draws in
# starts 32 units in and ends 5.5 above the frame's bottom (see Desktop._present).
FRAME_TO_COLUMN = (-32, -26.5)


class HdLayouts:
    density = 2                 # bank units per layout unit: HD's bank is Android's doubled

    def __init__(self, library):
        self.library = library

    _bank = _UNREAD = object()

    def bank(self):
        """The HD `LayoutBank`, or None when no HD app bundle was imported. Kept per instance: a shared
        `lru_cache(maxsize=1)` let two screens' instances evict each other, re-parsing the bank twice a frame."""
        if self._bank is self._UNREAD:
            try:
                data = self.library.hd_raw_resource(BANK_ID)
                self._bank = None if data is None else LayoutBank.parse(data)
            except (AttributeError, ContentError, UIAssetError):
                self._bank = None
        return self._bank

    @lru_cache(maxsize=16)
    def pack(self, pack_id):
        try:
            data = self.library.hd_raw_resource(pack_id)
            return None if data is None else ImagePack.parse(data)
        except (AttributeError, ContentError, UIAssetError):
            return None

    @lru_cache(maxsize=256)
    def frame(self, pack_id, index):
        """The native (2x) frame as a display-format surface, or None."""
        pack = self.pack(pack_id)
        if pack is None or not 0 <= index < len(pack.images):
            return None
        image = pack.images[index]
        return pygame.image.frombytes(image.pixels, (image.width, image.height), image.mode).convert_alpha()

    @staticmethod
    def pack_for(slot, theme):
        if slot == 2:
            return THEME_BOX_PACKS.get(theme, DEFAULT_BOX_PACK)
        return SLOT_PACKS.get(slot)

    def nodes(self, layout_id, origin=(0, 0), *, size=None, hidden=(), shown=()):
        """The layout's visible nodes as (node, (x, y, width, height)) in layout
        units, translated by `origin`. `hidden`/`shown` are 1-based node numbers
        (in flattened walk order) forced invisible/visible, as
        `CSLightWeightWidget::setVisible` does; a hidden reference hides its
        whole subtree."""
        bank = self.bank()
        if bank is None:
            return []
        layout = bank.layouts[layout_id]
        d = self.density
        width, height = (layout.width, layout.height) if size is None else (round(size[0] * d), round(size[1] * d))
        walked = list(bank.walk(layout_id, Rect(0, 0, width, height)))
        result, hide_until = [], 0
        for number, (node, rect) in enumerate(walked, 1):
            if number <= hide_until:
                continue
            visible = (bool(node.flags & 16) or number in shown) and number not in hidden
            if node.kind == 7 and not visible:
                hide_until = number + sum(1 for _ in bank.walk(node.payload[0]))
                continue
            result.append((number, node, visible,
                           (origin[0] + rect.x / d, origin[1] + rect.y / d, rect.width / d, rect.height / d)))
        return result

    def rectangle(self, layout_id, node_number, origin=(0, 0), *, size=None):
        """One node's rectangle in layout units, or None."""
        bank = self.bank()
        if bank is None:
            return None
        layout = bank.layouts[layout_id]
        d = self.density
        width, height = (layout.width, layout.height) if size is None else (round(size[0] * d), round(size[1] * d))
        for number, (_, rect) in enumerate(bank.walk(layout_id, Rect(0, 0, width, height)), 1):
            if number == node_number:
                return (origin[0] + rect.x / d, origin[1] + rect.y / d, rect.width / d, rect.height / d)
        return None


class BankLayouts(HdLayouts):
    """An iPhone build's own layout bank (resource 14, one bank unit per layout unit), with HdLayouts' node walk:
    Cause of Death's choice panel is laid out from it (hd_choice.COD_GEOMETRY)."""
    density = 1

    def __init__(self, bank):
        self.library = None
        self._bank = bank

    def bank(self):
        return self._bank
