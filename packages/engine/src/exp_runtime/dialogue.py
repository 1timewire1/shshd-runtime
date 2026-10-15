"""Shared SHS/CoD dialogue skin in the original 320 by 480 coordinates.

The v0.1.3 SHS skin is shared by both games. Font adapters supply native
metrics for bitmap/outline text within this common layout and renderer.
"""
from copy import deepcopy
import math
from dataclasses import dataclass, replace
from functools import lru_cache

from .fonts import load_font, TextLayout, TextStyle, layout_text
from .games import GAMES, game_id
from .ui_assets import ImagePack, LayoutBank, Rect, read_ui
from .speaker_names import (NAME_FONTS, SpeakerNames, fit_speaker_ink, hd_speaker_label, preview_speaker,
                            speaker_label)


BODY_FONT = 'ArialRoundedMTBold16'
NARRATOR_FONT = 'TrebuchetMS_Italic16'
HD_NARRATOR_WRAP, HD_NARRATOR_GAP, HD_NARRATOR_TOP = 226, 10.9, 110
BLUE = (41, 104, 221)
# Layout units added to the dialogue body origin when HD vector text is used.
HD_TEXT_SHIFT = (6, 6)
COD_TYPING_PAD = 4
# Cause of Death's typed lines sit 2.4 units lower than this renderer's baseline (origin + cap - 1, the atlas's own) puts
# them, in both faces: IMG_0309 (TrebuchetMS-Italic narration, lines 1-2 +2.4 / +2.5) and IMG_0310 (Arial Rounded
# body, line bottoms +2.4 / +2.4 / +2.2). Not found in the decompile; kept as measured (cf. HD_TEXT_SHIFT).
COD_BASELINE_DROP = 2.4


def dialogue_styles(theme: int, *, narrator: bool = False, emphasis_theme: int = 1,
                    game: str = 'shs'):
    profile = GAMES[game]
    if narrator:
        body_font = NARRATOR_FONT
        color, emphasis = getattr(profile, 'NARRATION_COLORS', ((223, 163, 52), (125, 67, 0)))
        body = TextStyle(10, 7, color, (('`', emphasis),))
    else:
        body_font = BODY_FONT
        colors = profile.DIALOGUE_COLORS
        color = colors.get(theme, colors[-1])
        markers = getattr(profile, 'BODY_MARKERS', None)
        if markers is not None:
            body = TextStyle(14, 7, color, ((markers[0], markers[1].get(theme, markers[1][-1])),))
        else:
            emphasis = BLUE if emphasis_theme == 2 else (254, 53, 0)
            body = TextStyle(14, 7, color, (('`', emphasis), (';', (1, 76, 215))))
    return NAME_FONTS.get(theme, 'PajamaHip26'), TextStyle(16, -16), body_font, body


@dataclass(frozen=True)
class DialoguePage:
    box: Rect  # The stretchable center; borders extend outside this rectangle.
    body_origin: tuple[float, float]
    body_font: str
    body: TextLayout
    portrait: Rect | None
    name_font: str
    name: TextLayout
    name_origin: tuple[float, float]
    name_scale: float
    start: int
    end: int
    name_bounds: Rect | None = None


class DialogueLayout:
    def __init__(self, resources):
        self.resources = resources
        self.bank = LayoutBank.parse(read_ui(resources, 14))

    @lru_cache(maxsize=8)
    def font(self, name):
        try:
            from .vector_text import load_font as vector_load_font  # needs pygame, the desktop extra
        except ImportError:
            return load_font(self.resources.library, name)
        return vector_load_font(self.resources.library, name)

    @lru_cache(maxsize=64)
    def hd_rectangle(self, node):
        """Layout 17's node from the HD bank (resource 16), in column units, or None without an HD bundle."""
        library = getattr(self.resources, 'library', None)
        if library is None or getattr(library, 'hd_raw_resource', None) is None:
            return None
        from .hd_layout import FRAME_TO_COLUMN, HdLayouts
        try:
            rect = HdLayouts(library).rectangle(17, node)
        except Exception:
            return None
        if rect is None:
            return None
        x, y, width, height = rect
        return Rect(x + FRAME_TO_COLUMN[0], y + FRAME_TO_COLUMN[1], width, height)

    def hd_label(self, details):
        """SHSUIDialog's own title (speaker_names.hd_speaker_label) when the name is drawn in HD's vector Pajama Hip
        and the HD layout bank is present; else None."""
        from .vector_text import cap_height
        mode = details['presentation_mode']
        if mode not in (1, 2, 3):
            return None
        font_name = NAME_FONTS.get(details['theme'], 'PajamaHip26')
        font = self.font(font_name)
        cap = cap_height(font)
        if game_id(self.resources) == 'cod':
            # Cause of Death's iPhone SHSUIDialog has the same title code over its own layout 17 (resource 14, already
            # in column units), with its short-title threshold and shift in its own points (hd_speaker_label).
            if cap is None:
                return None
            return hd_speaker_label(details['speaker'], mode, font_name, lambda node: self.bank.rectangle(17, node),
                                    font, cap, points_per_unit=1, shift=15)
        if cap is None or self.hd_rectangle(0x2e) is None:
            return None
        return hd_speaker_label(details['speaker'], mode, font_name, self.hd_rectangle, font, cap)

    @lru_cache(maxsize=4)
    def border_widths(self, theme):
        skin = {1: 204, 2: 220, 3: 252}.get(theme, 236)
        # Layout units are the Android skin's own pixels. With the HD (iPad) bundle imported, read_ui serves its
        # 2x-density substitute for these skins (content.HD_ASSET_MAP), so measure the APK's originals instead.
        android = getattr(self.resources, 'android_asset', None)
        library = getattr(self.resources, 'library', self.resources)
        if android is not None and getattr(library, 'kind', 'apk') == 'apk':
            data = android(skin)
        else:
            data = read_ui(self.resources, skin)
        frames = ImagePack.parse(data).images
        return frames[4].width, frames[5].width

    def prepare_name(self, details, names: SpeakerNames):
        names.basis = deepcopy(names.fonts)
        label = speaker_label(details['speaker'], details['presentation_mode'], details['theme'],
                              self.bank, self.font, names.fonts)
        return label.text

    def page(self, details, start=0, *, names: SpeakerNames | None = None):
        mode, theme = details['presentation_mode'], details['theme']
        name_font, name_style, body_font, body_style = dialogue_styles(
            theme, narrator=mode == 4, emphasis_theme=details['emphasis_theme'],
            game=game_id(self.resources))
        font = self.font(body_font)
        text = details['text'][start:]
        sizing_text = details['text']  # Page turns keep the original box size.
        portrait = name_bounds = None
        body_width = body_height = None
        cod = game_id(self.resources) == 'cod'
        if mode == 4 and cod:
            name = layout_text(self.font(name_font), '', 1, name_style)
            name_origin, name_scale = (0, 0), .9
            # CoD's SHSUIDialog::animateTextLayer (1.3.4 armv7 0003c4e4), speaker type 4: the narration CSFont
            # (+0xcc = engine +0xe254, set in `init` 0003d8d8) both measures and draws. Its block width at 220 plus 1,
            # rounded up to even and at least 120, and its text height plus 4, rounded up to even, size sub-element
            # 10; the bubble is that plus 10, centred on it, and the text layer sits at (30, 120) (the constructor's
            # 0x94/0x96), as wide as the block. The free edition anchors at y 135 (cod.profile.in_game_banner).
            from .cod.profile import in_game_banner
            top = 135 if in_game_banner(getattr(self.resources, 'library', self.resources)) else 120
            cap = getattr(font, 'cap_height', None)
            if cap is None:
                from .vector_text import cap_height as vector_cap_height
                cap = vector_cap_height(font)
            body_style = replace(body_style, height=cap if cap is not None else 16, gap=9)
            measured = layout_text(font, sizing_text, 220, body_style)
            width = max(120, (int(measured.width) + 2) // 2 * 2)
            height = (int(measured.height) + 5) // 2 * 2
            box = Rect(25, top - 5, width + 10, height + 10)
            origin = (30, top)
            body_width = width
        elif mode == 4:
            name = layout_text(self.font(name_font), '', 1, name_style)
            name_origin, name_scale = (0, 0), .9
            # FUN_000858cc configures state+0xd180 with registry font 5,
            # height 16 and gap 9. Narrator sizing and drawing deliberately
            # use different fonts. This measuring object has no color markers.
            measured = layout_text(self.font(BODY_FONT), sizing_text, 220, TextStyle(16, 9))
            width = max(120, (int(measured.width) + 2) // 2 * 2)
            height = (int(min(200, measured.height)) + 5) // 2 * 2
            box = Rect(25, 115, width + 10, height + 10)
            origin = (30, 120)
            if getattr(font, 'source', None) is not None:
                # HD (photos of ten narrator boxes, 1-5 lines): measured and drawn with the same
                # font, wrapped at HD_NARRATOR_WRAP; the box is text + 24 wide, its outer edge 17
                # units in from the frame (15 before the column's 32-unit inset), its top 115 down,
                # and 46.5 + 20.9 per extra line tall. The body lines are 20.9 apart.
                body_style = replace(body_style, gap=HD_NARRATOR_GAP)
                measured = layout_text(font, sizing_text, HD_NARRATOR_WRAP, body_style)
                lines = max(1, len(measured.lines))
                box = Rect(-6, 96, math.ceil(measured.width) + 6, round(8.6 + 20.9 * lines))
                origin = (0, HD_NARRATOR_TOP)
        else:
            hd_label = self.hd_label(details)
            label = hd_label or preview_speaker(details, self.bank, self.font, names)
            name, name_origin, name_scale, extra = label.layout, label.origin, label.scale, label.extra
            rect = self.bank.rectangle(17, 8)
            cap_height = getattr(font, 'cap_height', None)
            if cap_height is None and cod:
                # CoD's vector text (the SHS HD art source) is still CoD's own iPhone CSFont, so it takes the
                # iPhone branch below, not SHS HD's photo-fitted one.
                from .vector_text import cap_height as vector_cap_height
                cap_height = vector_cap_height(font)
            if cap_height is not None:
                # CSFont uses the face's cap height, not the nominal Cocos
                # label height. Both iOS games set ordinary line gap 10.
                body_style = replace(body_style, height=cap_height, gap=10)
            if mode in (1, 2):
                portrait = self.bank.rectangle(17, 0x30 if mode == 1 else 0x4e)
                # CSFont line offsets: the iPhone build's and HD's ARR_TEXT_LINE_OFFSETS_LEFT/RIGHT ({160, 140} points);
                # Android's bitmap labels keep their own 85/75.
                vector = getattr(font, 'source', None) is not None
                insets = (80, 70, 0, 0) if cap_height is not None or vector else (85, 75, 0, 0)
                body_style = replace(body_style, indents=insets if mode == 1 else tuple(-n for n in insets))
            measured = layout_text(font, sizing_text, rect.width, body_style)
            capacity = int((rect.height + body_style.gap) / (body_style.height + body_style.gap))
            count = min(capacity, max(3, len(measured.lines)))
            height = int(count * (body_style.height + body_style.gap) - body_style.gap + 7) if count else 8
            height += height % 2
            box = Rect(rect.x - 7, rect.y - extra, rect.width + 14, height + extra)
            # The box's own top moves up by the full `extra` (a native, decompiled constant: `speaker_label`'s 40 for
            # a name that wraps to two lines) so the background bubble is tall enough to hold it; the body text
            # itself does not need to follow, since fit_speaker_ink() below already positions the name relative to
            # wherever body_top ends up, not the reverse. Moving the body up too (an unexplained `extra // 2` this
            # project's own code carried with no decompiled source) shrank the last line's clearance from the
            # portrait exactly when a name wraps -- confirmed against a two-line name ("Beastmaster Kimuko") whose
            # third line dipped under the portrait housing; a single-line name (`extra == 8`, matching the real HD
            # photos this file's HD_TEXT_SHIFT comment is measured from) is untouched by this change.
            origin = (rect.x - 7, rect.y - (extra // 2 if extra <= 8 else 0))
            if getattr(font, 'source', None) is not None and not cod:
                # Two real HD photos (`IMG_0069`, `IMG_0070`: a portrait on each
                # side, three lines each) put the body text ~7 units lower in
                # the box (6 once the vector baseline is the bitmap's, see
                # vector_text._baseline) and ~6 further from its left edge than
                # the Android origin, where a portrait-side line cleared the
                # ring by a few units instead of overlapping it. Lines sit 24,
                # 46 and 67 below the box's top line; the first starts 17 from
                # its left edge.
                # x: the text layer sits at the text node's own x (SHSUIDialog::animateTextLayer positions it at node
                # 8), with the line offsets above (photo IMG_0075: first, second and third lines at 149, 139 and 69
                # frame units, i.e. 69 + 80 / 70 / 0). y keeps the photo-measured shift from the one-line-name
                # position: animateTextLayer places the text at node 8 whatever the title does, so a wrapped (tall)
                # name does not move it (photo IMG_0298, "Mrs. / Sworelin": the body was 4 units low before).
                origin = (rect.x, rect.y - 4 + HD_TEXT_SHIFT[1])
                # Wrap width. The body box is 14 wider than the 246 the text is measured
                # at; Android wraps at the box width, but the HD screenshots (the
                # "Um... You're... I / mean... Um... Let's do / that kissing thing?"
                # line, `IMG_0069`) only reproduce with real HD glyph advances at the
                # measured 246, so vector-font text wraps there.
                body_width = rect.width
            elif cap_height is not None:
                # animateTextLayer (CoD 0003788a / SHS 0007d628) positions
                # text at node 8, independently of the expanded frame. The
                # title's extra 8/40 pixels are not additional body capacity.
                origin = (rect.x, rect.y)
                body_width = rect.width
                descent = getattr(font, 'descent', None)
                if descent is None:
                    # A vector face (CoD with the SHS HD art source): CSFont's own descent.
                    from .vector_text import descent as vector_descent
                    descent = vector_descent(font)
                body_height = height + int(descent) + 3
        if mode == 4 and not cod and getattr(font, 'source', None) is not None:
            body_width = HD_NARRATOR_WRAP
        if cod:
            # CoD 1.3.4 -[SHSTextLayer setupTypingLayers] (0004db50): the typed (and settled) text is one line layer
            # per line inside a container placed at (x - pad, line top - pad), the line layer itself at (-pad, -pad)
            # in it (positionLayer:boundsPadding:, 0004e7e4) with its text at (pad, pad). Net: every line sits pad
            # units up and left of the text layer's origin. pad is 4 (8 with the double-font flag, unused here).
            # Matches IMG_0309 / IMG_0310 (both 4.2 units left of the layer origin). Only the drawn text moves; the
            # title is fitted against the layer's own origin below. COD_BASELINE_DROP is photo-measured, not decompiled.
            drawn_origin = (origin[0] - COD_TYPING_PAD, origin[1] - COD_TYPING_PAD + COD_BASELINE_DROP)
        else:
            drawn_origin = origin
        body_width = box.width if body_width is None else body_width
        body_height = box.height if body_height is None else body_height
        full = layout_text(font, text, body_width, body_style)
        capacity = max(1, int((body_height + body_style.gap) / (body_style.height + body_style.gap)))
        end = full.lines[capacity].start if len(full.lines) > capacity else len(text)
        # setupTypingLayers steps each CoD line container by FPToFixed(gap + cap), a whole number of points; the box
        # was sized from CSFont::getTextHeight's fractional pitch above.
        drawn_style = (replace(body_style, gap=int(body_style.height + body_style.gap) - body_style.height) if cod
                       else body_style)
        body = layout_text(font, text[:end], body_width, drawn_style)
        if mode != 4:
            # Allow for any glyph becoming the first line on a later page.
            # The whole dialogue supplies one stable name position; neither
            # the native body box nor its byte offsets change for this fit.
            all_body = layout_text(font, sizing_text, body_width, body_style)
            ink_tops = (body_style.height - font.line_height + g.glyph.yoffset
                        for g in all_body.glyphs)
            body_top = origin[1] + min(ink_tops, default=0)
            # Bound the visible title to the actual skin, not the viewport.
            # The native title has normal and tall regions. A tall name may
            # straddle the box border; forcing it wholly above the box shrinks
            # multiline titles and discards the purpose of the taller header.
            border_left, border_right = self.border_widths(theme)
            left = max(0, box.x - border_left,
                       portrait.x + portrait.width if mode == 1 else 0)
            right = min(320, box.x + box.width + border_right,
                        portrait.x if mode == 2 else 320)
            header = label.header or self.bank.rectangle(
                17, ({1: 0x25, 2: 0x43, 3: 0x61} if extra == 40 else
                     {1: 0x2e, 2: 0x4c, 3: 0x6a})[mode])
            bottom = min(header.y + header.height, body_top)
            top = max(0, min(header.y, bottom - 1))
            name_bounds = Rect(left, top, right - left, bottom - top)
            if hd_label is None:
                # (HD's title is drawn exactly where SHSUIDialog puts it; this fit corrects Android/iPhone labels.)
                name, name_origin, name_scale = fit_speaker_ink(label, name_bounds)
        return DialoguePage(box, drawn_origin, body_font, body, portrait, name_font,
                            name, name_origin, name_scale, start, start + end, name_bounds)
