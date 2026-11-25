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
EMPHASIS_FONT = 'TrebuchetMS_Italic16Emphasis'
BLUE = (41, 104, 221)
# Layout units added to the dialogue body origin when HD vector text is used.
HD_TEXT_SHIFT = (6, 6)
COD_TYPING_PAD = 4
# Cause of Death's typed lines sit 2.4 units lower than this renderer's baseline (origin + cap - 1, the atlas's own) puts
# them, in both faces: IMG_0309 (TrebuchetMS-Italic narration, lines 1-2 +2.4 / +2.5) and IMG_0310 (Arial Rounded
# body, line bottoms +2.4 / +2.4 / +2.2). Not found in the decompile; kept as measured (cf. HD_TEXT_SHIFT).
COD_BASELINE_DROP = 2.4
# SHSEngine::initPermanents (HD 1.4.38, 0002bdf4, load step 8): each colored dialogue theme's body and emphasis fonts
# draw '{' as a music note from master image 155 (`CSFont::addCharImage(master, frame, '{', (1, 2), 22)`) -- frame 34
# (blue, theme 1), 35 (rose, 2) or 36 (gray, 3), its bottom-left 1 point right of the pen and 2 below the baseline,
# advancing 22 points. The gold narrator fonts register none; this fork draws them the gray note in their text color
# (page()). Songs are written this way ("{ some people say... {"), and the frames are 20x28 HD pixels; layout units
# are half HD points.
NOTE_CODE = 0x7B
NOTE_FRAMES = {1: 34, 2: 35, 3: 36}
NOTE_SIZE, NOTE_OFFSET, NOTE_ADVANCE = (10, 14), (0.5, 1), 11
# The iPhone builds have their own. Cause of Death's SHSEngine::initPermanents (1.3.4 armv7 0002720a..000272a6; the
# 1.4.7 free edition 0002733c..000273dc, the same arguments) calls `CSFont::addCharImage(master, frame, '{', (1, 2),
# 12)` with the master image of common pack 126 (resource 0x7e, engine +0x2980) on each colored set's body font and its
# '`' switch font: +0x142d4 / +0x15af4 frame 29 (theme 1), +0x1d394 / +0x1ebb4 frame 30 (theme 2), +0x26454 / +0x27c74
# frame 31 (theme 3), three gray 10x14 notes at 1x. The default set (+0x2f514, which updateFonts 0003a5b0 binds for any
# other theme) and narration (+0xe254) register none, so they draw the face's own '{'. CSFont::drawChar (00003ef0)
# draws through the active switch font, so a note inside '`' is the switch font's (the same frame), untinted. SHS's
# iPhone build (1.3.7, armv6 initPermanents 00032238..000322e6) makes the same six calls on the same sets (+0x20 on:
# +0x142f4 ... +0x27c94; updateFonts 00059fe0, default +0x2f534) with its common pack, resource 0x7d (the UI role 126,
# shs/ios_assets.py), whose frames 29-31 are blue, rose and gray. Layout units are iPhone points, so the place and
# advance are used as they stand. Songs are written "{{ some words {{".
IPHONE_NOTE_FRAMES = {1: 29, 2: 30, 3: 31}
IPHONE_NOTE_PACK = 126
IPHONE_NOTE_SIZE, IPHONE_NOTE_OFFSET, IPHONE_NOTE_ADVANCE = (10, 14), (1, 2), 12
IPHONE_NOTE = (IPHONE_NOTE_SIZE, IPHONE_NOTE_OFFSET, IPHONE_NOTE_ADVANCE)


# A two-speaker line's portraits are drawn at this scale about their housings' centres, so the title between them
# has room for a name like "Gangsta Bot" on one line (owner, 2026-10-24).
DUET_RING_SCALE = .8
DUET_NAME_MARGIN = 2                    # a two-speaker title's room either side, inside the gap between the rings
# Its most lines: smaller until it wraps to two (owner: three-line names do not look good). Every name a two-speaker
# line has fits at 57% or more between 80% rings.
DUET_TITLE_LINES = 2
# shshd-runtime: the room a bubble keeps above it in the column when it moves up (DialogueLayout.page `dialogue_offset`).
# Its border art sits outside the box (desktop_dialogue's `box`: a 10-unit strip above it, its line near the outer edge),
# so the room is that strip and 2 units more; 8 cut a narrator bubble's top line at the layer's top (owner, 2026-11-12,
# the g54 at 20:9).
DIALOGUE_TOP_ROOM = 12


# shshd-runtime: story-object pictures (service 225, Claire Hart plan P) in framed squares along the box's bottom, right-
# aligned as Classic's are (photos chc_09, chc_12: a slot is a fifth of the box's width there), the box a row taller for them.
STORY_OBJECT_SLOT = 36                  # a square's side, in units, when the row fits at it (else they share the room)
STORY_OBJECT_GAP = 3                    # between squares
STORY_OBJECT_MARGIN = 6                 # from the box's right and bottom edges, and above the row
STORY_OBJECT_ROOM = 270                 # the widest a narrator's box grows to hold its row
# Secret in the Shadows' one photo (the profile's STORY_OBJECT_PHOTO): its 123 x 124 frame in its 800 x 600 design, at the
# frame's 512 units for the scene's 600 (0.853), right-aligned with the box and STORY_PHOTO_GAP above it (owner's pick B,
# 2026-11-24: the sequel's own place, low right of centre, lands on CoD's text). Its picture area as the game draws it
# (chs_11 measured, 2026-11-24): 94% of the frame's width, 79% of its height, 3% below its top, a deeper foot (the
# prefab's 93 x 74 constraint is the photo's own fit, not the area).
STORY_PHOTO_SIZE, STORY_PHOTO_PICTURE, STORY_PHOTO_PICTURE_TOP = (105, 106), (99, 83), 4
STORY_PHOTO_GAP = 6
# shshd-runtime: Add-Ons' Claire Hart Dialogue (content.EpisodeResources.dialogue_skin; owner, 2026-11-19): Claire Hart's Romic
# (vector_text.skin_font: the add-on's own faces) for the text, its bold for emphasis and the name, which goes in the tab.
# Claire Hart's text is Romic Bold, as its names are (its Romic lacks '/', '&', '#' and most accented letters); CoD's emphasis
# takes the skin's `emphasis` colour (one of Claire Hart's text colours), not a font.
SKIN_BODY, SKIN_BOLD, SKIN_NAME = 'CHRomicBold16', 'CHRomicBold16', 'CHRomicBold18'
# ...and narration slanted, as CoD's narration is italic (owner, 2026-11-19; Romic has no italic: vector_text.SKIN_SLANT).
SKIN_NARRATION = 'CHRomicBoldItalic16'
# The skin's ring is whole over the bubble (desktop_dialogue: no housing clip) and larger and darker than CoD's, so its
# text wraps around the ring's own circle rather than CoD's two fixed insets: each line clears it by SKIN_RING_CLEAR
# where the circle reaches into its row (owner, 2026-11-20: a third line ran under the ring).
SKIN_RING_RADIUS = 64                   # the ring picture's 128 units, opaque to its edge, centred on the housing
SKIN_RING_CLEAR = 4
SKIN_RING_ROWS = 8
# A narrator's ring is smaller, to tell narration from speech besides its missing name tab (owner, 2026-11-20); its
# text wraps around it in turn, so narration keeps nearly CoD's own lines.
SKIN_NARRATION_RING = 0.8


def skin_ring_insets(portrait, mode, rect, style, cod, radius=SKIN_RING_RADIUS):
    """Line insets (fonts.TextStyle.indents: positive from the left for a portrait on the left, mode 1; negative from the
    right for one on the right) that keep each line of text laid at `rect` (layout 17's node 8, as CoD draws it: up and
    left by COD_TYPING_PAD, down by COD_BASELINE_DROP) clear of a ring of SKIN_RING_RADIUS around the housing's centre."""
    cx, cy = portrait.x + portrait.width / 2, portrait.y + portrait.height / 2
    x0 = rect.x - (COD_TYPING_PAD if cod else 0)
    y0 = rect.y - (COD_TYPING_PAD - COD_BASELINE_DROP if cod else 0)
    pitch = int(style.height + style.gap) if cod else style.height + style.gap
    insets = []
    for row in range(SKIN_RING_ROWS):
        top, bottom = y0 + row * pitch - 2, y0 + row * pitch + style.height + 4     # (its ink: caps to descenders)
        dy = 0 if top <= cy <= bottom else min(abs(top - cy), abs(bottom - cy))
        if dy >= radius:
            insets.append(0)
            continue
        reach = math.sqrt(radius ** 2 - dy ** 2) + SKIN_RING_CLEAR
        inset = cx + reach - x0 if mode == 1 else x0 + rect.width - (cx - reach)
        insets.append(math.ceil(max(0, inset)) * (1 if mode == 1 else -1))
    return tuple(insets)
TITLE_JOINS = ('and', '&', ',')         # a two-speaker title's words that name no one ("Kay and Kel")


def _speaker_colors(layout, partner_name, first_font, second_font):
    """A two-speaker title with each speaker's name in that speaker's title font (colour): words in `partner_name`
    take `second_font`, the other names `first_font`, joins keep the gray. A title naming neither ("Both") stays
    gray."""
    runs, current = [], []
    for g in sorted(layout.glyphs, key=lambda g: g.index):
        if current and (g.index != current[-1].index + 1 or chr(g.glyph.code) in ' \n'):
            runs.append(current)
            current = []
        if chr(g.glyph.code) not in ' \n':
            current.append(g)
    if current:
        runs.append(current)
    partner = partner_name.lower()

    def theirs(word):
        return len(word) >= 3 and (word in partner.split() or word in partner.replace(' ', ''))
    words = [(run, ''.join(chr(g.glyph.code) for g in run).lower().strip(',.!?')) for run in runs]
    if not any(theirs(word) for _, word in words):
        return layout
    fonts = {}
    for run, word in words:
        if word and word not in TITLE_JOINS:
            for g in run:
                fonts[g.index] = second_font if theirs(word) else first_font
    return replace(layout, glyphs=tuple(replace(g, font=fonts[g.index]) if g.index in fonts else g
                                        for g in layout.glyphs))


def _shift_lines(layout, shifts):
    """`layout` with line i (and its glyphs) moved `shifts[i]` units across; lines past the list stay."""
    moves = {index: shifts[index] for index in range(min(len(shifts), len(layout.lines))) if shifts[index]}
    if not moves:
        return layout
    lines = tuple(replace(line, x=line.x + moves.get(index, 0)) for index, line in enumerate(layout.lines))
    owner = [(line.start, line.end, moves.get(index, 0)) for index, line in enumerate(layout.lines)]
    glyphs = tuple(replace(g, x=g.x + next((move for start, end, move in owner if start <= g.index < end), 0))
                   for g in layout.glyphs)
    return replace(layout, lines=lines, glyphs=glyphs)


def with_note(font, size=NOTE_SIZE, offset=NOTE_OFFSET, advance=NOTE_ADVANCE):
    """`font` with '{' measured as the note image (NOTE_FRAMES; the iPhone builds pass IPHONE_NOTE): `size` units, its
    bottom-left `offset` right of the pen and below the baseline, advancing `advance`. One copy per font and metrics."""
    key = (id(font), size, offset, advance)
    cached = _NOTE_FONTS.get(key)
    if cached is None or cached[0] is not font:
        from .fonts import Glyph
        # The baseline in glyph coordinates: the vector faces' `base`; the iPhone builds' installed faces (ios_fonts.
        # IOSFont) leave BMFont's base unset, their glyphs standing on the line box's bottom (line_height).
        baseline = font.base or font.line_height
        glyph = Glyph(NOTE_CODE, 0, 0, size[0], size[1], offset[0], baseline + offset[1] - size[1], advance)
        cached = _NOTE_FONTS[key] = (font, replace(font, glyphs={**font.glyphs, NOTE_CODE: glyph}))
    return cached[1]


_NOTE_FONTS = {}


def dialogue_styles(theme: int, *, narrator: bool = False, emphasis_theme: int = 1,
                    game: str = 'shs', outline: bool = False):
    profile = GAMES[game]
    if narrator:
        body_font = NARRATOR_FONT
        color, emphasis = getattr(profile, 'NARRATION_COLORS', ((223, 163, 52), (125, 67, 0)))
        body = TextStyle(10, 7, color, (('`', emphasis),))
    else:
        body_font = BODY_FONT
        markers = getattr(profile, 'BODY_MARKERS', None)
        colors = profile.IOS_DIALOGUE_COLORS if outline and markers is None else profile.DIALOGUE_COLORS
        color = colors.get(theme, colors[-1])
        if markers is not None:
            body = TextStyle(14, 7, color, ((markers[0], markers[1].get(theme, markers[1][-1])),))
        elif outline:
            # initFonts: each body face registers its own italic switch font.
            # Only backticks toggle it; semicolons remain punctuation here.
            emphasis = BLUE if theme == 2 else (254, 53, 53)
            body = TextStyle(14, 7, color, (('`', emphasis),))
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
    note_frame: int | None = None  # pack 155's frame drawn for '{' (NOTE_FRAMES), when HD's fonts give it one
    note_tint: tuple | None = None  # the color it is drawn in instead of its own (the gold fonts' note, this fork's)
    note_pack: int = 155            # the pack note_frame is in: SHS HD's 155 (2 px a unit) or the iPhone's 126 role
    theme: int | None = None        # the box's theme when it is not the line's own (a two-speaker line's)
    # shshd-runtime (General's Aspect Ratio): how far the whole bubble (box, text, title, portrait) was moved up for the
    # rows it holds past HD's own (DialogueLayout.page's `extra_rows`), so its bottom stays where HD's is.
    lift: float = 0
    # shshd-runtime: the story-object pictures shown with the line, (picture, its square) each (story_object_slots).
    story_objects: tuple = ()
    # ...or the sequel's one photo: (picture, its frame's Rect), right-aligned above the box; () for none. And the one fading out
    # as this line starts, in the same place.
    story_photo: tuple = ()
    story_photo_leaving: tuple = ()
    # shshd-runtime (Claire Hart Dialogue): the skin's spec with `box` ('speaker' or 'narrator'), and the name's tab, or None.
    skin: dict | None = None
    tab: Rect | None = None
    # shshd-runtime: the width the body wraps in (SHSTextLayer's drawRegion): Text Animation's wipe crosses it per line.
    body_width: float = 0


def story_object_slots(box, pictures, *, widen=False):
    """(box, ((picture, square), ...)): the box a row taller at its bottom, and the pictures' squares along it from the
    right. They share the box's width when the row is too long at STORY_OBJECT_SLOT; a narrator's box (`widen`) grows to
    hold them first, up to STORY_OBJECT_ROOM."""
    count = len(pictures)
    if not count:
        return box, ()
    wanted = count * STORY_OBJECT_SLOT + (count - 1) * STORY_OBJECT_GAP + 2 * STORY_OBJECT_MARGIN
    if widen and box.width < wanted:
        box = replace(box, width=min(max(box.width, STORY_OBJECT_ROOM), wanted))
    room = box.width - 2 * STORY_OBJECT_MARGIN
    side = min(STORY_OBJECT_SLOT, (room - (count - 1) * STORY_OBJECT_GAP) / count)
    box = replace(box, height=box.height + side + STORY_OBJECT_MARGIN)
    top = box.y + box.height - STORY_OBJECT_MARGIN - side
    right = box.x + box.width - STORY_OBJECT_MARGIN
    slots = tuple((picture, Rect(right - (count - i) * side - (count - 1 - i) * STORY_OBJECT_GAP, top, side, side))
                  for i, picture in enumerate(pictures))
    return box, slots


class DialogueLayout:
    def __init__(self, resources):
        self.resources = resources
        self.bank = LayoutBank.parse(read_ui(resources, 14))

    def skin(self):
        """Add-Ons' Claire Hart Dialogue's spec for this episode (content.EpisodeResources.dialogue_skin), or None. Asked
        each page: the player may change it while the line is up."""
        found = getattr(self.resources, 'dialogue_skin', None)
        return found() if found is not None else None

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

    def hd_label(self, details, *, between_rings=False):
        """SHSUIDialog's own title (speaker_names.hd_speaker_label) when the name is drawn in HD's vector Pajama Hip
        and the HD layout bank is present; else None. `between_rings` (a two-speaker line, shshd-runtime): the
        portrait-less title regions narrowed to the gap between the two portrait housings, so the title wraps and
        shrinks there as a long name does in its own region."""
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
        rectangle = self.hd_rectangle
        if between_rings:
            left, right = self.bank.rectangle(17, 0x30), self.bank.rectangle(17, 0x4e)
            x0 = left.x + left.width / 2 * (1 + DUET_RING_SCALE) + DUET_NAME_MARGIN
            x1 = right.x + right.width / 2 * (1 - DUET_RING_SCALE) - DUET_NAME_MARGIN

            def rectangle(node):
                rect = self.hd_rectangle(node)
                return None if rect is None else replace(rect, x=x0, width=x1 - x0)
        return hd_speaker_label(details['speaker'], mode, font_name, rectangle, font, cap,
                                max_lines=DUET_TITLE_LINES if between_rings else None)

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

    def prepare_name(self, details, names: SpeakerNames, *, text_history=None):
        names.basis = deepcopy(names.fonts)
        label = speaker_label(details['speaker'], details['presentation_mode'], details['theme'],
                              self.bank, self.font, names.fonts)
        if text_history is not None and details['presentation_mode'] != 4:
            text_history.update('dialogue_name', self.font(label.font), label.text, label.layout)
        return label.text

    def page(self, details, start=0, *, names: SpeakerNames | None = None, text_history=None, duet=None,
             partner_name=None, narration_theme=None, extra_rows=0, dialogue_offset=(0, 0)):
        """`duet` (shshd-runtime, Session.dialogue_duet): a second speaker's portrait, `partner_name` its name. The
        line is then laid out with a portrait on each side, its name centered between them and its first lines clear
        of both rings. Two speakers of one color (both blue, both pink) take that color for the box, the name and
        the text; otherwise the box is gray and each speaker's name in the title takes its own color (owner,
        2026-10-25). `narration_theme` (shshd-runtime, Session.narration_theme): a named line without a portrait
        (mode 3) drawn in that theme's box, name and text (1 blue, 2 pink, 3 gray) instead of its own. `extra_rows`
        (shshd-runtime, Session.dialogue_extra_rows: a frame taller than HD's 3:4, owner 2026-11-11): a speaker's
        bubble may hold that many rows more than HD's, so a long line takes fewer bubbles; the bubble then grows
        upward (DialoguePage.lift) and its bottom stays where HD's is. A line HD fits in one bubble is unchanged.
        `dialogue_offset` (shshd-runtime, Session.dialogue_offset: the same frames), (right, up) in units: a narrator's
        bubble moves right so it stays in a narrower frame as far from its edge as HD's from the iPad's; every bubble
        (speaker or narrator) moves up by `up`, so in a taller frame it sits nearer the middle as the choice does (owner,
        2026-11-11), as far as the room above it in the column allows (DIALOGUE_TOP_ROOM). Only where it is drawn: the
        page's text is the same."""
        colors = None
        if narration_theme in (1, 2, 3) and duet is None and details['presentation_mode'] == 3:
            details = dict(details, theme=narration_theme)
        else:
            narration_theme = None
        if duet is not None and details['presentation_mode'] in (1, 2):
            first, second = details['theme'], duet.theme
            shared = first if first == second and first in (1, 2) else None
            if shared is None:
                colors = (NAME_FONTS.get(first, 'PajamaHip26'), NAME_FONTS.get(second, 'PajamaHip26'))
            details = dict(details, presentation_mode=3, theme=shared or 3)
        else:
            duet = None
        mode, theme = details['presentation_mode'], details['theme']
        # shshd-runtime (narration_portrait): a narrator's line in a speaker's box beside the portrait, in narration's
        # text and without a name plate (owner, 2026-11-19).
        narration = bool(details.get('narration')) and mode in (1, 2)
        skin = self.skin() if duet is None else None
        skin_body = SKIN_NARRATION if mode == 4 or narration else SKIN_BODY
        font = self.font(skin_body if skin else NARRATOR_FONT if mode == 4 or narration else BODY_FONT)
        cap_height = getattr(font, 'cap_height', None)
        name_font, name_style, body_font, body_style = dialogue_styles(
            theme, narrator=mode == 4 or narration, emphasis_theme=details['emphasis_theme'],
            game=game_id(self.resources), outline=cap_height is not None)
        if skin:
            # Claire Hart's one colour for the text and every name (CoD has none per character), emphasis in Romic Bold.
            colour = tuple(skin['text'])
            name_font, name_style = SKIN_NAME, TextStyle(18, 0, colour)
            body_font, body_style = skin_body, TextStyle(14, 7, colour, (('`', tuple(skin.get('emphasis', colour))),))
        switch_fonts = note_frame = None
        text = details['text'][start:]
        sizing_text = details['text']  # Page turns keep the original box size.
        portrait = name_bounds = None
        body_width = body_height = None
        lift = 0
        cod = game_id(self.resources) == 'cod'
        note_tint = None
        note_pack, note_metrics = 155, (NOTE_SIZE, NOTE_OFFSET, NOTE_ADVANCE)
        colored = mode != 4 and not narration and theme in IPHONE_NOTE_FRAMES
        if cod:
            # CoD's own notes (IPHONE_NOTE_FRAMES), in every font configuration (installed faces or vector text): only
            # the colored sets have them, so narration and default-theme lines keep a plain '{', as on the iPhone.
            if colored:
                note_pack, note_metrics = IPHONE_NOTE_PACK, IPHONE_NOTE
                font = with_note(font, *note_metrics)
                note_frame = IPHONE_NOTE_FRAMES[theme]
        elif getattr(getattr(self.resources, 'library', None), 'kind', 'apk') == 'ipa':
            # SHS's iPhone build (a base-game IPA library: its installed faces, no HD bundle): the same notes from its
            # own common pack. As with HD's, this fork gives narration and default-theme lines, which the iPhone leaves
            # with a plain '{', the gray note in the text's own color, so every song line keeps its notes.
            note_pack, note_metrics = IPHONE_NOTE_PACK, IPHONE_NOTE
            font = with_note(font, *note_metrics)
            note_frame = IPHONE_NOTE_FRAMES[theme] if colored else IPHONE_NOTE_FRAMES[3]
            note_tint = None if colored else body_style.color
        elif getattr(font, 'source', None) is not None:
            # HD's song notes (NOTE_FRAMES). This fork also gives the gold fonts (narration, and named lines without a
            # portrait), which HD leaves with a plain '{', the gray note in the text's own color (owner's request:
            # translated New Rules stories narrate songs), so every song line keeps its notes.
            font = with_note(font)
            colored = mode != 4 and theme in NOTE_FRAMES
            note_frame = NOTE_FRAMES[theme] if colored else NOTE_FRAMES[3]
            note_tint = None if colored else body_style.color
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
            # Narration switches to +0xfa74 on '`': the same face with a 0.6-point edge (cod/profile.py).
            emphasis = GAMES['cod'].NARRATION_EMPHASIS_FONT
            switch_fonts = None if skin else {'`': (emphasis, self.font(emphasis))}
            width = max(120, (int(measured.width) + 2) // 2 * 2)
            height = (int(measured.height) + 5) // 2 * 2
            box = Rect(25, top - 5, width + 10, height + 10)
            origin = (30, top)
            body_width = width
        elif mode == 4:
            if cap_height is not None or getattr(font, 'source', None) is not None:
                # The iOS builds' outline text switches to a stroked twin in the same colour (shs/profile.py).
                emphasis = GAMES[game_id(self.resources)].NARRATION_EMPHASIS_FONT
                face = self.font(emphasis)
                switch_fonts = {'`': (emphasis, with_note(face, *note_metrics) if note_frame is not None else face)}
                body_style = replace(body_style, markers=(('`', body_style.color),))
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
                right = dialogue_offset[0]
                box = Rect(-6 + right, 96, math.ceil(measured.width) + 6, round(8.6 + 20.9 * lines))
                origin = (right, HD_NARRATOR_TOP)
        else:
            if narration:
                name, name_origin, name_scale, extra = layout_text(self.font(name_font), '', 1, name_style), (0, 0), .9, 0
            elif skin:
                # The name goes in the skin's tab (skin_tab, below), on one line, at its own size.
                name = layout_text(self.font(name_font), details['speaker'], 10000, name_style)
                name_origin, name_scale, extra = (0, 0), 1, 8
            else:
                hd_label = self.hd_label(details, between_rings=duet is not None)
                label = hd_label or preview_speaker(
                    details, self.bank, self.font, names,
                    previous_glyph=text_history.initial('dialogue_name') if text_history else -1)
                name, name_origin, name_scale, extra = label.layout, label.origin, label.scale, label.extra
            rect = self.bank.rectangle(17, 8)
            cap_height = getattr(font, 'cap_height', None)
            if cap_height is None and cod:
                # CoD's vector text (the SHS HD art source) is still CoD's own iPhone CSFont, so it takes the
                # iPhone branch below, not SHS HD's photo-fitted one.
                from .vector_text import cap_height as vector_cap_height
                cap_height = vector_cap_height(font)
            if skin and cap_height is not None:
                body_style = replace(body_style, height=cap_height, gap=10)       # (emphasis by colour: no switch font)
            elif narration and cap_height is not None:
                # Narration's own emphasis face (cod/profile.py, shs/profile.py NARRATION_EMPHASIS_FONT).
                emphasis = GAMES[game_id(self.resources)].NARRATION_EMPHASIS_FONT
                switch_fonts = {'`': (emphasis, self.font(emphasis))}
                body_style = replace(body_style, height=cap_height, gap=10)
            elif cap_height is not None and cod:
                # CSFont uses the face's cap height, not the nominal Cocos label height. CoD keeps this fork's
                # photo-verified pitch (IMG_0309 / IMG_0310) with BODY_MARKERS' colours, and draws emphasis in its
                # own switch font (cod/profile.py EMPHASIS_FONTS: TrebuchetMS-Italic 16 with a 0.5-point edge).
                body_style = replace(body_style, height=cap_height, gap=10)
                fonts = GAMES['cod'].EMPHASIS_FONTS
                emphasis = fonts.get(theme, fonts[-1])
                switch_fonts = {'`': (emphasis, self.font(emphasis))}
            elif cap_height is not None:
                # The tallest registered face determines the
                # line step, even in a paragraph with no emphasized words.
                emphasis = self.font(EMPHASIS_FONT)
                switch_fonts = {'`': (EMPHASIS_FONT, emphasis)}
                body_style = replace(body_style, height=max(cap_height, emphasis.cap_height), gap=10)
            if note_frame is not None and switch_fonts:
                switch_fonts = {key: (name, with_note(face, *note_metrics))
                                for key, (name, face) in switch_fonts.items()}
            if mode in (1, 2):
                portrait = self.bank.rectangle(17, 0x30 if mode == 1 else 0x4e)
                # CSFont line offsets: the iPhone build's and HD's ARR_TEXT_LINE_OFFSETS_LEFT/RIGHT ({160, 140} points);
                # Android's bitmap labels keep their own 85/75.
                vector = getattr(font, 'source', None) is not None
                insets = (80, 70, 0, 0) if cap_height is not None or vector else (85, 75, 0, 0)
                body_style = replace(body_style, indents=insets if mode == 1 else tuple(-n for n in insets))
                if skin:
                    radius = SKIN_RING_RADIUS * (SKIN_NARRATION_RING if narration else 1)
                    body_style = replace(body_style, indents=skin_ring_insets(portrait, mode, rect, body_style, cod,
                                                                              radius))
            elif duet is not None:
                # Both sides' insets: one indent narrows the line by both (fonts.layout_text takes one side), and the
                # lines move back by the right one once laid out (_shift_lines).
                vector = getattr(font, 'source', None) is not None
                insets = (80, 70, 0, 0) if cap_height is not None or vector else (85, 75, 0, 0)
                # The smaller rings (DUET_RING_SCALE) give back their lost radius on each side.
                gained = self.bank.rectangle(17, 0x30).width / 2 * (1 - DUET_RING_SCALE)
                insets = tuple(max(0, n - gained) if n else 0 for n in insets)
                body_style = replace(body_style, indents=tuple(2 * n for n in insets))
            measured = layout_text(font, sizing_text, rect.width, body_style, switch_fonts=switch_fonts)
            capacity = int((rect.height + body_style.gap) / (body_style.height + body_style.gap))
            # (A narration box holds just its lines: small, beside the portrait.)
            count = min(capacity + max(0, extra_rows), max(1 if narration else 3, len(measured.lines)))
            # Rows past HD's own: the bubble grows that much upward (the whole of it is moved up below).
            lift = max(0, count - capacity) * (body_style.height + body_style.gap)
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
                # The text starts at node 8 whatever the title does, so a tall title's extra 40 units (the box grows
                # upward for it) hold no body lines: a page holds what fits in `height`. Counting them let a two-line
                # name's page take two lines too many, which ran past the box (issue #11, Spud The Stud).
                body_height = height
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
        full = layout_text(font, text, body_width, body_style, switch_fonts=switch_fonts)
        capacity = max(1, int((body_height + body_style.gap) / (body_style.height + body_style.gap)))
        end = full.lines[capacity].start if len(full.lines) > capacity else len(text)
        # setupTypingLayers steps each CoD line container by FPToFixed(gap + cap), a whole number of points; the box
        # was sized from CSFont::getTextHeight's fractional pitch above.
        drawn_style = (replace(body_style, gap=int(body_style.height + body_style.gap) - body_style.height) if cod
                       else body_style)
        body = layout_text(font, text[:end], body_width, drawn_style,
                           previous_glyph=text_history.initial('dialogue_body') if text_history else -1,
                           switch_fonts=switch_fonts)
        if duet is not None:
            body = _shift_lines(body, [-n / 2 for n in body_style.indents])
        if mode != 4 and not narration and not skin:     # (narration has no name to place; the skin's goes in its tab)
            # Allow for any glyph becoming the first line on a later page.
            # The whole dialogue supplies one stable name position; neither
            # the native body box nor its byte offsets change for this fit.
            all_body = layout_text(font, sizing_text, body_width, body_style, switch_fonts=switch_fonts)
            baseline = cap_height if switch_fonts else body_style.height
            ink_tops = (baseline - self.font(g.font or body_font).line_height + g.glyph.yoffset
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
            if hd_label is None and not getattr(self.font(name_font), 'native_face', False):
                # HD's title is drawn exactly where SHSUIDialog puts it, and native outline titles keep their
                # 26-point size and region origin; this fit corrects Android labels and substitute faces.
                name, name_origin, name_scale = fit_speaker_ink(label, name_bounds)
            if duet is not None and name.lines:
                # Centered between the two rings, at the height SHSUIDialog gives a portrait-less title.
                inner_left = self.bank.rectangle(17, 0x30)
                inner_right = self.bank.rectangle(17, 0x4e)
                middle = (inner_left.x + inner_left.width + inner_right.x) / 2
                ink = (min(line.x for line in name.lines), max(line.x + line.width for line in name.lines))
                name_origin = (middle - (ink[0] + ink[1]) / 2 * name_scale, name_origin[1])
                if colors is not None:
                    name = _speaker_colors(name, partner_name or '', *colors)
        tab = None
        if skin and mode != 4 and not narration and details['speaker']:
            tab, name_origin = self.skin_tab(skin, box, portrait, mode, name)
        pictures = tuple(details.get('story_objects') or ())
        story_objects = ()
        if pictures:
            # A narrator's box (top-anchored) grows down for the row; a speaker's grows up, so its bottom stays put.
            grown, story_objects = story_object_slots(box, pictures, widen=mode == 4)
            if mode != 4:
                lift += grown.height - box.height      # (the whole bubble moves up by it below)
            box = grown
        up = dialogue_offset[1]
        if up:
            # Centred in a taller frame, as far as the bubble's top (its box, its title, its portrait) has room.
            tops = [box.y] + [r.y for r in (portrait, name_bounds, tab) if r is not None]
            lift += max(0., min(up, min(tops) - lift - DIALOGUE_TOP_ROOM))
        if lift:
            box = replace(box, y=box.y - lift)
            drawn_origin = (drawn_origin[0], drawn_origin[1] - lift)
            name_origin = (name_origin[0], name_origin[1] - lift)
            portrait = None if portrait is None else replace(portrait, y=portrait.y - lift)
            name_bounds = None if name_bounds is None else replace(name_bounds, y=name_bounds.y - lift)
            story_objects = tuple((picture, replace(r, y=r.y - lift)) for picture, r in story_objects)
            tab = None if tab is None else replace(tab, y=tab.y - lift)
        # Above the box at its right (the narrator's too), and above a speaker's name plate, which rises over the box's
        # top edge at its right (the pilot, 2026-11-24: the plate covered the photo's foot); kept inside the column.
        width, height = STORY_PHOTO_SIZE
        top = box.y
        if details.get('speaker') and name_bounds is not None and getattr(name, 'lines', None):
            top = min(top, name_bounds.y)
        if tab is not None:
            top = min(top, tab.y)
        place = Rect(box.x + box.width - width, max(2, top - STORY_PHOTO_GAP - height), width, height)
        story_photo = (details['story_photo'], place) if details.get('story_photo', -1) >= 0 else ()
        leaving = (details['story_photo_leaving'], place) if details.get('story_photo_leaving', -1) >= 0 else ()
        return DialoguePage(box, drawn_origin, body_font, body, portrait, name_font,
                            name, name_origin, name_scale, start, start + end, name_bounds, note_frame, note_tint,
                            note_pack=note_pack, theme=details['theme'] if duet is not None or narration_theme else None, lift=lift,
                            story_objects=story_objects, story_photo=story_photo, story_photo_leaving=leaving,
                            skin=dict(skin, box='narrator' if mode == 4 or narration else 'speaker') if skin else None, tab=tab,
                            body_width=body_width)

    @staticmethod
    def skin_tab(skin, box, portrait, mode, name):
        """(the tab's rectangle, the name's origin) for Claire Hart Dialogue: the tab as wide as the name and its insets, its
        base on the bubble's outer top, beside the ring (to its right for a left speaker, its left for a right one; at the
        bubble's left without a portrait), the name centred in the tab's band."""
        k, tab = skin['density'], skin['tab']
        width = max((tab['caps'][0] + tab['caps'][1]) / k, name.width + 2 * tab['inset'] / k)
        height = tab['size'][1] / k
        outset = skin['speaker']['outset']
        left, right = box.x - outset[0], box.x + box.width + outset[2]
        if portrait is not None and mode == 1:
            x = portrait.x + portrait.width - 6
        elif portrait is not None and mode == 2:
            x = portrait.x + 6 - width
        else:
            x = left + 12
        x = max(left + 4, min(x, right - 4 - width))
        top = box.y - outset[1] - tab['base'] / k
        rect = Rect(x, top, width, height)
        x0, y0, x1, y1 = name.ink_bounds
        middle = top + (tab['name'][0] + tab['name'][1]) / 2 / k
        return rect, (x + (width - (x1 - x0)) / 2 - x0, middle - (y1 - y0) / 2 - y0)
