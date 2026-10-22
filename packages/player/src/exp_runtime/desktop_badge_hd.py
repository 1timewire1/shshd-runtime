"""The iOS HD scene label ("Before School", "Free Time", "Counselor's Office", ...).

Decompiled (`GameModel::displayScheduleCaption`, `GameModel::render(ctx, 4)`, `GameModel::setBubbleSex`,
`SHSEngine::initFonts`): the caption is a Core Animation layer of 362 x 120 points at (30, 100) in the
768 x 1024 point frame, drawn by layout 67 of the HD bank: node 1 the tab image (slot 2 = the current bubble
theme's pack, frame 13), node 2 (26, 10, 100 x 100) the scene icon, drawn centered, and node 3 (136, 30,
216 x 60) the text, wrapped in that region, left aligned and vertically centered (`drawTextInRegion` flags
0x19). The text is ArialMT, 28 pt, colored by the bubble theme when the caption last redrew: blue (47, 90, 168),
pink (180, 78, 78), gray (137, 137, 137), otherwise gold (180, 109, 26). Lines are 26 pt apart (photo). Like every
ArialMT CSFont it advances by Arial Rounded MT Bold's widths (`SHSEngine::initFonts` 0002b04a builds the ArialMT
advance table from the Rounded face; see desktop_faceplace_alert.py): "Before School" is 194 pt, the photographed
~97 units, where Arial's own advances give 179.

Motion: shown after a 0.5 s delay, position x runs -362 -> 33 -> 30 over 0.6 s, each half eased in and out;
`displayScheduleCaption(-1)` slides it back to -362 in 0.3 s (ease out; the drawn label is the one that was showing). The engine keeps its own 200 ms
counter for the label, so this renderer runs the (purely visual) animation on its own clock.

Everything is drawn 2x supersampled into a full-frame layer (a point is `S` layer pixels).
"""
from functools import lru_cache

from . import graphics as pygame

S = 2
FRAME = (768, 1024)
TAB = (362, 120)
TAB_TOP = 100
REST_X = 30
ICON_CENTER = (76, 60)                     # node 2: (26, 10, 100, 100)
TEXT_REGION = (136, 30, 216, 60)           # node 3
FONT_POINTS, LINE_PITCH = 28, 26
DELAY_S, SLIDE_S, LEAVE_S = 0.5, 0.6, 0.3
KEYS = (-TAB[0], 33, REST_X)
TEXT_COLORS = {1: (47, 90, 168), 2: (180, 78, 78), 3: (137, 137, 137)}
DEFAULT_TEXT_COLOR = (180, 109, 26)


def ease_in_out(t):
    """CAMediaTimingFunction ease-in-ease-out (cubic bezier .42, 0, .58, 1), by bisection."""
    def bez(u, a, b):
        return 3 * (1 - u) ** 2 * u * a + 3 * (1 - u) * u ** 2 * b + u ** 3
    lo, hi = 0., 1.
    for _ in range(30):
        mid = (lo + hi) / 2
        if bez(mid, .42, .58) < t:
            lo = mid
        else:
            hi = mid
    return bez((lo + hi) / 2, 0., 1.)


def ease_out(t):
    """CAMediaTimingFunction ease-out (cubic bezier 0, 0, .58, 1), by bisection."""
    def bez(u, a, b):
        return 3 * (1 - u) ** 2 * u * a + 3 * (1 - u) * u ** 2 * b + u ** 3
    lo, hi = 0., 1.
    for _ in range(30):
        mid = (lo + hi) / 2
        if bez(mid, 0., .58) < t:
            lo = mid
        else:
            hi = mid
    return bez((lo + hi) / 2, 0., 1.)


def leave_x(from_x, seconds):
    """The tab's left edge `seconds` after its dismissal began, starting from `from_x`."""
    t = min(1., max(0., seconds / LEAVE_S))
    return from_x + (KEYS[0] - from_x) * ease_out(t)


def slide_x(seconds):
    """The tab's left edge, in points, `seconds` after the caption was requested."""
    t = (seconds - DELAY_S) / SLIDE_S
    if t <= 0:
        return KEYS[0]
    if t >= 1:
        return KEYS[2]
    segment, local = (0, t * 2) if t < .5 else (1, t * 2 - 1)
    a, b = KEYS[segment], KEYS[segment + 1]
    return a + (b - a) * ease_in_out(local)


class HdSceneBadge:
    def __init__(self, art, image):
        self.art, self.image = art, image
        self.key = self.since = None
        self.last = None                 # (badge, theme) as last drawn, kept to slide out
        self.gone = None                 # (since ms, x it left from) once dismissed
        self._tab_cache = None           # (content key, composed tab surface) -- see draw()'s own note

    @staticmethod
    @lru_cache(maxsize=1)
    def _font():
        # `pygame.font.match_font` searches the filesystem and `Font(path, ...)` parses the file from disk --
        # neither depends on anything but FONT_POINTS, so this loads once per process rather than every draw().
        return pygame.font.Font(pygame.font.match_font('arial'), FONT_POINTS * S)

    @staticmethod
    @lru_cache(maxsize=1)
    def _advance_font():
        """The face whose advances the ArialMT CSFont carries (Arial Rounded MT Bold, or its stand-in), else None."""
        from .vector_text import system_font_path
        path = system_font_path('arial-rounded')
        return pygame.font.Font(path, FONT_POINTS * S) if path else None

    @classmethod
    def advances(cls, font, text):
        source = cls._advance_font() or font
        return [metric[4] if metric else 0 for metric in source.metrics(text)]

    @classmethod
    def render_line(cls, font, text, color):
        """Arial's glyphs, each at the pen the Rounded advances put it."""
        advances = cls.advances(font, text)
        line = pygame.Surface((max(1, sum(advances) + font.size(text[-1:])[0] if text else 1), font.get_height()),
                              pygame.SRCALPHA)
        pen = 0
        for character, advance in zip(text, advances):
            if character != ' ':
                line.blit(font.render(character, True, color), (pen, 0))
            pen += advance
        return line

    def available(self):
        try:
            return self.art.hd_chrome() and bool(pygame.font.match_font('arial'))
        except (AttributeError, ValueError, pygame.error):
            return False

    def seconds(self, badge):
        """Seconds since this caption first drew (the engine's own counter stops at 200 ms)."""
        key = (badge.asset_id, badge.text)
        now = pygame.time.get_ticks()
        if key != self.key:
            self.key, self.since = key, now
        return (now - self.since) / 1000

    def tab(self, badge, theme):
        pack = {1: 204, 2: 220, 3: 252}.get(theme, 204 if badge.blue and theme < 0 else 236)
        tab = self.art.frame_native(pack, 13)
        size = TAB[0] * S, TAB[1] * S
        return tab if tab.get_size() == size else pygame.transform.smoothscale(tab, size)

    @classmethod
    def wrap(cls, font, text, width):
        lines, current = [], ''
        for word in text.split(' '):
            trial = f'{current} {word}' if current else word
            if current and sum(cls.advances(font, trial)) > width:
                lines.append(current)
                current = word
            else:
                current = trial
        return lines + [current]

    def leaving(self):
        return self.last is not None

    def draw(self, badge, theme=-1):
        layer = pygame.Surface((FRAME[0] * S, FRAME[1] * S), pygame.SRCALPHA).convert_alpha()
        now = pygame.time.get_ticks()
        if badge is None:
            if self.last is None:
                return layer
            badge, theme = self.last
            if self.gone is None:
                self.gone = now, slide_x(self.seconds(badge))
            left = leave_x(self.gone[1], (now - self.gone[0]) / 1000)
            if left <= -TAB[0]:
                self.last = self.gone = self.key = None
                return layer
        else:
            self.last, self.gone = (badge, theme), None
            left = slide_x(self.seconds(badge))
            if left <= -TAB[0]:
                return layer
        # The composed tab (background art, icon and wrapped text) depends only on the badge's own content, never
        # on the slide animation's position -- cached so a 0.6-0.9s slide doesn't reload the font, re-wrap the
        # text and re-scale the icon on every one of its frames, only once per distinct badge actually shown.
        content_key = (badge.asset_id, badge.text, theme)
        cached_key, cached_tab = self._tab_cache or (None, None)
        if content_key == cached_key:
            tab = cached_tab
        else:
            tab = pygame.Surface((TAB[0] * S, TAB[1] * S), pygame.SRCALPHA).convert_alpha()
            tab.blit(self.tab(badge, theme), (0, 0))
            icon = self.image(badge.asset_id)
            if icon is not None:
                # Icons ship at 2x like the rest of HD's art, so native pixels are frame points.
                icon = pygame.transform.smoothscale(icon, (icon.get_width() * S, icon.get_height() * S))
                tab.blit(icon, icon.get_rect(center=(ICON_CENTER[0] * S, ICON_CENTER[1] * S)))
            font = self._font()
            color = TEXT_COLORS.get(theme, DEFAULT_TEXT_COLOR)
            x, y, width, height = TEXT_REGION
            lines = self.wrap(font, badge.text, width * S)
            cap = font.render('H', True, (0, 0, 0)).get_bounding_rect()
            for index, line in enumerate(lines):
                middle = (y + height / 2 + (index - (len(lines) - 1) / 2) * LINE_PITCH) * S
                tab.blit(self.render_line(font, line, color), (x * S, round(middle - cap.y - cap.height / 2)))
            self._tab_cache = (content_key, tab)
        layer.blit(tab, (round(left * S), TAB_TOP * S))
        return layer
