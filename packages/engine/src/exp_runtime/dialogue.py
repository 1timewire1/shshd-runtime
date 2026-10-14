"""Shared SHS/CoD dialogue skin in the original 320 by 480 coordinates.

The v0.1.3 SHS skin is shared by both games. Font adapters supply native
metrics for bitmap/outline text within this common layout and renderer.
"""
from copy import deepcopy
from dataclasses import dataclass, replace
from functools import lru_cache

from .fonts import load_font, TextLayout, TextStyle, layout_text
from .games import GAMES, game_id
from .ui_assets import ImagePack, LayoutBank, Rect, read_ui
from .speaker_names import NAME_FONTS, SpeakerNames, fit_speaker_ink, preview_speaker, speaker_label


BODY_FONT = 'ArialRoundedMTBold16'
NARRATOR_FONT = 'TrebuchetMS_Italic16'
BLUE = (41, 104, 221)


def dialogue_styles(theme: int, *, narrator: bool = False, emphasis_theme: int = 1,
                    game: str = 'shs'):
    if narrator:
        body_font = NARRATOR_FONT
        body = TextStyle(10, 7, (223, 163, 52), (('`', (125, 67, 0)),))
    else:
        body_font = BODY_FONT
        colors = GAMES[game].DIALOGUE_COLORS
        color = colors.get(theme, colors[-1])
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
        return load_font(self.resources.library, name)

    @lru_cache(maxsize=4)
    def border_widths(self, theme):
        skin = {1: 204, 2: 220, 3: 252}.get(theme, 236)
        frames = ImagePack.parse(read_ui(self.resources, skin)).images
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
        if mode == 4:
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
        else:
            label = preview_speaker(details, self.bank, self.font, names)
            name, name_origin, name_scale, extra = label.layout, label.origin, label.scale, label.extra
            rect = self.bank.rectangle(17, 8)
            cap_height = getattr(font, 'cap_height', None)
            if cap_height is not None:
                # CSFont uses the face's cap height, not the nominal Cocos
                # label height. Both iOS games set ordinary line gap 10.
                body_style = replace(body_style, height=cap_height, gap=10)
            if mode in (1, 2):
                portrait = self.bank.rectangle(17, 0x30 if mode == 1 else 0x4e)
                insets = (80, 70, 0, 0) if cap_height is not None else (85, 75, 0, 0)
                body_style = replace(body_style, indents=insets if mode == 1 else tuple(-n for n in insets))
            measured = layout_text(font, sizing_text, rect.width, body_style)
            capacity = int((rect.height + body_style.gap) / (body_style.height + body_style.gap))
            count = min(capacity, max(3, len(measured.lines)))
            height = int(count * (body_style.height + body_style.gap) - body_style.gap + 7) if count else 8
            height += height % 2
            box = Rect(rect.x - 7, rect.y - extra, rect.width + 14, height + extra)
            origin = (rect.x - 7, rect.y - extra // 2)
            if cap_height is not None:
                # animateTextLayer (CoD 0003788a / SHS 0007d628) positions
                # text at node 8, independently of the expanded frame. The
                # title's extra 8/40 pixels are not additional body capacity.
                origin = (rect.x, rect.y)
                body_width = rect.width
                body_height = height + int(font.descent) + 3
        body_width = box.width if body_width is None else body_width
        body_height = box.height if body_height is None else body_height
        full = layout_text(font, text, body_width, body_style)
        capacity = max(1, int((body_height + body_style.gap) / (body_style.height + body_style.gap)))
        end = full.lines[capacity].start if len(full.lines) > capacity else len(text)
        body = layout_text(font, text[:end], body_width, body_style)
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
            name, name_origin, name_scale = fit_speaker_ink(label, name_bounds)
        return DialoguePage(box, origin, body_font, body, portrait, name_font,
                            name, name_origin, name_scale, start, start + end, name_bounds)
