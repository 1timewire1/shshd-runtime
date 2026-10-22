"""The iOS HD build's pause menu (the gear), drawn in HD's 768 x 1024 point frame.

It is UIKit, not game art: the running scene is dimmed and tinted sepia, and a
white rounded panel with a blue border (Pause -> Options / Help & About, and
text pages) is centered on it. Only the blue back button (resource 32) and the
two speaker icons (resource 155) are art; the rest is drawn here from
measurements of `reference/screenshots/pause gear menu`. Text is bold Helvetica
in HD (Arial Bold here). Colors come from the owner's light-mode photos (the first
set had an iOS dark-mode tweak): rows alternate lavender-gray / pink down every card,
1 pt gray rules, a near-white translucent card, and the classic blue/white UISwitch.

The layer is 2x supersampled (1536 x 2048) so the caller's resample stays sharp.
"""
from dataclasses import dataclass, field
from functools import lru_cache
import re

import pygame
from PIL import Image

from .desktop_pause import ease_in_out
from .help_text_overrides import HELP_TEXT_OVERRIDES
from .menu import MenuStrings
from .pointer import step_focus
from .ui_assets import ImagePack

FRAME = (768, 1024)
S = 2
BLUE = (41, 104, 221)
HEADER_COLOR, FOOTER_COLOR = (248, 246, 245), (253, 251, 249)
PANEL = FOOTER_COLOR
SWITCH_ROW, SLIDER_ROW_COLOR = (231, 230, 238), (247, 234, 245)     # light-mode photos: rows alternate
PLAIN_ROW = SWITCH_ROW
ROW_BACKGROUND = (250, 249, 247)      # a text page's body
# The card is slightly see-through (the photos show the scene faintly through every row); the
# colors above are what was measured over the sepia backdrop, so the fill is brightened to match.
CARD_ALPHA, TYPICAL_BACKDROP = 240, (150, 130, 100)
LABEL_BLUE = (85, 130, 215)           # row labels are a lighter blue than the title
SEPARATOR = (135, 135, 137)
PANEL_X, PANEL_W, BORDER, RADIUS = 82, 604, 6, 18
HEADER, ROW, FOOT = 112, 88, 86
TALL = (30, 993)                      # text pages fill the frame
TITLE_PX, ROW_PX, TEXT_PX, TEXT_PITCH = 56, 28, 28.8, 31
BACK = (14, 13)                       # back button inset from the panel's left / bottom
SLIDER_ROW = 130
SIDE_PANELS_LABEL = 'Side Panels'
CHOICE_HINTS_LABEL = 'Choice Hints'
SKIP_MINIGAMES_LABEL = 'Ask to Skip Mini-Games'
SKIP_AD_INTROS_LABEL = 'Skip Ad Intros'
SKIP_UPSELL_INTROS_LABEL = 'Skip Upsell Intros'    # the store plugs some SHS episodes open with (upsell_intro.py)
VIBRATION_SOUND_LABEL = 'Simulated Vibration Sound'
AUTOPLAY_LABEL = 'Autoplay Dialogue'           # dialogue advances by itself (this player's); choices still wait
DISABLE_CHOICE_TIMER_LABEL = 'Disable Choice Timer'     # timed choices wait (this player's)
HD_BACKDROP_LABEL = 'SHS HD Backdrop'          # SHS HD's collage beside the frame, else a dark fill (this player's)
CHECK_UPDATES_LABEL = 'Check for Updates'      # the release check at launch (updates.py); main menu only
# Options lists categories, each opening a page of its own switches (owner, 2026-10-14; no native strings, this
# player's own: SHS HD's Options is one page). A row shows when its setting is offered (`layout`'s `settings`), so a
# game leaves out what does not apply to it.
# Extras holds the play aids that change how a story plays (owner, 2026-10-21).
OPTION_CATEGORIES = (('general', 'General'), ('sound', 'Sound'), ('extras', 'Extras'), ('data', 'Data Management'))
GENERAL_KEYS = ('side_panels', 'autoplay', 'skip_ad_intros', 'skip_upsell_intros', 'hd_backdrop', 'check_updates')
EXTRAS_KEYS = ('disable_choice_timer', 'choice_hints', 'skip_minigames')
# General's last row on the main menu: the episode title language, a button that steps through the languages
# (`settings['title_language']` is the current one's name). Data Management's rows are actions, tapped like Help &
# About's rows; both are offered by the main menu only.
TITLE_LANGUAGE_LABEL = 'Episode Titles'
DATA_ACTIONS = (('add_episodes', 'Add Episodes'), ('open_library', 'Open Another Library'))
# A row's control sits against the card's right side, CONTROL_RIGHT points in (owner, 2026-10-14; SHS HD's own
# switches sat 168 in): the switch (79 x 27) and the value button, a little bigger (104 x 34, its label at 18 points).
CONTROL_RIGHT = 26
CYCLE_SIZE, CYCLE_POINTS = (104, 34), 18
SWITCH_LABELS = {'side_panels': SIDE_PANELS_LABEL, 'autoplay': AUTOPLAY_LABEL,
                 'disable_choice_timer': DISABLE_CHOICE_TIMER_LABEL, 'choice_hints': CHOICE_HINTS_LABEL,
                 'skip_minigames': SKIP_MINIGAMES_LABEL, 'skip_ad_intros': SKIP_AD_INTROS_LABEL,
                 'skip_upsell_intros': SKIP_UPSELL_INTROS_LABEL,
                 'hd_backdrop': HD_BACKDROP_LABEL, 'check_updates': CHECK_UPDATES_LABEL}
# HD dims and sepia-tints what was on screen; a fit to IMG_0110's untouched margins
# (rms ~2 levels): out = M . (r, g, b) + c.
SEPIA = (0.779, 0.166, 0.0, 102.1,
         0.703, 0.144, 0.0, 90.5,
         0.549, 0.110, 0.0, 70.5)
# The native app's own CFBundleShortVersionString (1.4.38) is irrelevant to a player here -- the only place the
# string bank's ~276~ token appears at all is the About page (checked against a real HD string bank), and only
# this project's own override of it (`help_text_overrides.py`) is ever shown, so this reports shshd-runtime's
# own release instead. The one line to edit on a release; nothing else about the About text needs to change.
VERSION = '1.0.2'
# The upstream exp-runtime release this fork last merged (owner, 2026-10-21: shown under the version, About pages'
# `~upstream~`). Change it with each upstream merge.
UPSTREAM_VERSION = 'v0.6.1'
# A text page's own body never carries a literal URL natively (EULA/Privacy/Terms are full menu rows, never
# inline text); these only ever match inside override text (`help_text_overrides.py`), making it tappable: a bare
# URL, or `[label](url)` shown as the label (this fork, 2026-10-15: the About page's project links). A page may have
# any number.
LINK_PATTERN = re.compile(r'https?://\S+')
LABELED_LINK = re.compile(r'\[([^\]]+)\]\((https?://[^)\s]+)\)')


def link_words(paragraph):
    """A paragraph's words, each a list of (text, url or None) pieces: `[label](url)` keeps its url on the label's
    words, a bare URL links itself. Splitting on single spaces keeps the text's own double spaces, as before."""
    pieces, position = [], 0
    for match in LABELED_LINK.finditer(paragraph):
        pieces += [(paragraph[position:match.start()], None), (match.group(1), match.group(2))]
        position = match.end()
    pieces.append((paragraph[position:], None))
    words = [[]]
    for text, url in pieces:
        for index, part in enumerate(text.split(' ')):
            if index:
                words.append([])
            if part:
                words[-1].append((part, url or (part if LINK_PATTERN.fullmatch(part) else None)))
    return words

PAGES = {'intro': (133, 136), 'controls': (134, 137), 'airing': (119, 138),
         'demand': (83, 139), 'network': (135, 140), 'about': (16, 0), 'push': (238, 240)}
HELP_ORDER = ('intro', 'controls', 'airing', 'demand', 'network', 'about')
# The main menu's Help & About (menu 15 of the menu engine) also lists Push Notifications and, last, the legal page
# (Privacy Policy / EULA / Terms & Conditions), which the main menu draws itself.
MAIN_HELP_ORDER = ('intro', 'controls', 'airing', 'demand', 'network', 'push', 'about', 'privacy')
# A page that is not the pause card itself (menu-engine entrance other than 20) slides: `SHSEngine::notifyNewMenu`
# (SHS HD 00027f1a) starts the new menu one width to the right and moves it, and the old one a width to the left, in a
# 0.4 s UIKit ease-in-out (curve 0) with no delay (0.4 s only under a loading screen).
SLIDE_MS = 400
# Keyboard navigation (not native): arrows highlight a row, Enter or Space taps it, Left / Right move a slider.
FOCUS_SHADE, VOLUME_STEP = .85, .1
KEYS_ACTIVATE = (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE)
PAGE_KEYS = {pygame.K_UP: -40, pygame.K_DOWN: 40, pygame.K_PAGEUP: -400, pygame.K_PAGEDOWN: 400}


def focus_step(key):
    """-1 or 1 for a key that moves a menu's highlight back or on (Up / Left / Shift-Tab, Down / Right / Tab), else
    None."""
    if key in (pygame.K_UP, pygame.K_LEFT) or key == pygame.K_TAB and pygame.key.get_mods() & pygame.KMOD_SHIFT:
        return -1
    if key in (pygame.K_DOWN, pygame.K_RIGHT, pygame.K_TAB):
        return 1
    return None


@dataclass
class PauseState:
    screen: str = 'pause'
    scroll: float = 0.
    drag: str | None = None
    max_scroll: float = 0.
    focus: tuple | None = None      # the command the arrow keys have highlighted


class HdPauseMenu:
    main_menu = False               # the main menu's copy: the longer Help & About list
    scale = S                       # layer pixels per frame point
    PAGES = PAGES                   # page -> (title, body) string ids
    # Style, overridable by a game that keeps this layout in its own dress (desktop_cod_pause.CodPauseMenu).
    TITLE_COLOR, LABEL_COLOR, TEXT_COLOR = BLUE, LABEL_BLUE, BLUE
    CYCLE_FRAMES = ((26, 27, 28), (30, 31, 32))   # pack 32: the orange button (layouts 72 / 73), up and pressed
    SEPARATOR_COLOR, PAGE_BACKGROUND, ROW_COLORS = SEPARATOR, ROW_BACKGROUND, (PLAIN_ROW, SLIDER_ROW_COLOR)

    def __init__(self, resources):
        self.resources = resources
        self.state = PauseState()

    # -- assets ---------------------------------------------------------
    def raw(self, resource_id):
        try:
            return self.resources.library.hd_raw_resource(resource_id)
        except AttributeError:
            return None

    def available(self):
        try:
            return all(self.raw(i) is not None for i in (15, 32, 155)) and pygame.font.match_font('arial', bold=True)
        except (AttributeError, KeyError):
            return False

    @lru_cache(maxsize=1)
    def strings(self):
        hd = MenuStrings.parse(self.raw(15))
        return [hd[i] for i in range(273)]

    @lru_cache(maxsize=None)
    def pack(self, resource_id):
        return ImagePack.parse(self.raw(resource_id))

    @lru_cache(maxsize=None)
    def art(self, resource_id, index):
        image = self.pack(resource_id).images[index]
        surface = pygame.image.frombytes(image.pixels, (image.width, image.height), 'RGBA').convert_alpha()
        # Art pixels are frame points here; the layer is S times denser.
        return pygame.transform.smoothscale(surface, (image.width * S, image.height * S))

    @lru_cache(maxsize=16)
    def font(self, points):
        return pygame.font.Font(pygame.font.match_font('arial', bold=True), round(points * self.scale))

    def control_font(self, points):
        """A UIKit control's own label (the switches' ON / OFF): the system bold face, whatever the menu's text face."""
        return HdPauseMenu.font(self, points)

    def text_lines(self, page):
        override = HELP_TEXT_OVERRIDES.get(page)
        if override is not None:
            title, body = override
            return title, body.replace('~276~', VERSION).replace('~upstream~', UPSTREAM_VERSION)
        title_id, body_id = self.PAGES[page]
        strings = self.strings()
        # HD's string bank stores the trademark sign as control byte 2 (EA, Arts).
        body = strings[body_id].replace('~276~', VERSION).replace('', '™')
        return strings[title_id], body

    # -- state ----------------------------------------------------------
    slide = None
    shown = None

    def reset(self):
        self.state = PauseState()
        self.slide = self.shown = None

    def open(self, screen):
        """A row's page, pushed in from the right."""
        self.state.screen, self.state.scroll = screen, 0.
        self.start_slide(1)

    def back(self):
        """One step out: returns True once the pause panel itself was showing."""
        state = self.state
        if state.screen == 'pause':
            return True
        state.screen = ('help' if state.screen in PAGES else 'options' if state.screen.startswith('options:')
                        else 'pause')
        if self.main_menu and state.screen == 'pause':
            return True
        state.scroll, state.drag = 0., None
        self.start_slide(-1)
        return False

    def start_slide(self, direction):
        self.slide = (direction, self.shown, 0.) if self.shown is not None else None

    def advance(self, ms):
        if self.slide is not None:
            direction, previous, elapsed = self.slide
            self.slide = (direction, previous, elapsed + ms) if elapsed + ms < SLIDE_MS else None

    # -- drawing helpers (points; S scales to the layer) -----------------
    @staticmethod
    def see_through(color):
        a = CARD_ALPHA / 255
        return tuple(min(255, round((c - (1 - a) * b) / a)) for c, b in zip(color, TYPICAL_BACKDROP)) + (CARD_ALPHA,)

    def rect(self, layer, color, box, radius=0, width=0):
        x, y, w, h = box
        S = self.scale
        pygame.draw.rect(layer, color, (round(x * S), round(y * S), round(w * S), round(h * S)),
                         round(width * S), border_radius=round(radius * S))

    def text(self, layer, text, x, y, points, color=BLUE, *, center=False, font=None):
        surface = (font or self.font(points)).render(text, True, color)
        S = self.scale
        if center:
            x -= surface.get_width() / S / 2
        layer.blit(surface, (round(x * S), round(y * S)))
        return surface.get_height() / S

    def cap_offset(self, points, font=None):
        """Distance from a rendered line's top to the middle of its capitals."""
        font = font or self.font(points)
        bounds = font.render('H', True, (0, 0, 0)).get_bounding_rect()
        return (bounds.y + bounds.height / 2) / self.scale

    def title_lines(self, text):
        if self.font(TITLE_PX).size(text)[0] / S <= PANEL_W - 60:
            return [text]
        # Long titles wrap onto two lines ("Episodes On Demand"), 52 points apart.
        words = text.split(' ')
        half = len(words) // 2 + (len(words) % 2)
        return [' '.join(words[:half]), ' '.join(words[half:])]

    def title(self, layer, text, top, height):
        lines = self.title_lines(text)
        pitch = 52 if len(lines) > 1 else self.font(TITLE_PX).get_linesize() / S * .92
        y = top + height / 2 - pitch * len(lines) / 2
        for line in lines:
            self.text(layer, line, 384, y + (pitch - self.font(TITLE_PX).get_height() / S) / 2 + 3, TITLE_PX, self.TITLE_COLOR,
                      center=True)
            y += pitch

    def panel(self, layer, top, bottom, title, *, header=HEADER):
        """The rounded bordered card: white header, `ROW_BACKGROUND` body, white footer."""
        self.rect(layer, BLUE, (PANEL_X, top, PANEL_W, bottom - top), RADIUS)
        self.rect(layer, self.see_through(FOOTER_COLOR), (PANEL_X + BORDER, top + BORDER, PANEL_W - 2 * BORDER, bottom - top - 2 * BORDER),
                  RADIUS - 4)
        self.rect(layer, self.see_through(HEADER_COLOR), (PANEL_X + BORDER, top + BORDER, PANEL_W - 2 * BORDER, header - BORDER),
                  RADIUS - 4)
        self.rect(layer, self.see_through(HEADER_COLOR), (PANEL_X + BORDER, top + header - 20, PANEL_W - 2 * BORDER, 20))
        self.title(layer, title, top, header)
        return top + header

    def back_button(self, layer, bottom, *, lit=False):
        left, lift = PANEL_X + BACK[0], BACK[1]
        top = bottom - lift - 58

        def art(index):
            image = self.art(32, index)
            if lit:
                image = image.copy()
                image.fill((round(255 * FOCUS_SHADE),) * 3, special_flags=pygame.BLEND_RGB_MULT)
            return image
        # Frames 13/14/15 are the button's cap, middle and cap (10 + 136 + 10 = 156 wide).
        x = left
        for index in (13, 14, 15):
            image = art(index)
            layer.blit(image, (x * S, top * S))
            x += image.get_width() / S
        arrow = art(12)
        layer.blit(arrow, (round((left + 78) * S - arrow.get_width() / 2), round((top + 29) * S - arrow.get_height() / 2)))
        return pygame.Rect(left, top, 156, 58)

    def gradient_pill(self, box, stops):
        """A pill whose color runs down through `stops` [(t, (r, g, b))], at the layer's density."""
        x, y, w, h = box
        S = self.scale
        width, height = round(w * S), round(h * S)
        surface = pygame.Surface((width, height), pygame.SRCALPHA).convert_alpha()
        for row in range(height):
            t = row / max(1, height - 1)
            for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
                if t0 <= t <= t1:
                    f = (t - t0) / (t1 - t0) if t1 > t0 else 0
                    surface.fill(tuple(round(a + (b - a) * f) for a, b in zip(c0, c1)) + (255,), (0, row, width, 1))
                    break
        mask = pygame.Surface((width, height), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, width, height), border_radius=height // 2)
        surface.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        return surface

    def switch(self, layer, right, middle, on):
        """A classic UISwitch (light mode, from the owner's photo): 79 x 27 points. ON is a blue
        glossy track with a white label and the knob on the right; OFF a white track with a gray
        label and the knob on the left."""
        width, height, knob = 79, 27, 27
        S = self.scale
        left, top = right - width, middle - height / 2
        rim = self.gradient_pill((left, top, width, height), [(0, (110, 110, 112)), (1, (150, 150, 152))])
        layer.blit(rim, (round(left * S), round(top * S)))
        if on:
            stops = [(0, (15, 98, 163)), (.08, (0, 123, 227)), (.5, (2, 126, 232)), (.55, (30, 143, 238)),
                     (1, (107, 178, 243))]
        else:
            stops = [(0, (170, 170, 172)), (.12, (215, 215, 217)), (.55, (240, 240, 242)), (1, (252, 252, 253))]
        inner = self.gradient_pill((left + .5, top + .5, width - 1, height - 1), stops)
        layer.blit(inner, (round((left + .5) * S), round((top + .5) * S)))
        kx = right - knob if on else left
        shade = self.gradient_pill((kx, top, knob, knob), [(0, (120, 120, 122)), (1, (140, 140, 142))])
        layer.blit(shade, (round(kx * S), round(top * S)))
        face = self.gradient_pill((kx + .6, top + .6, knob - 1.2, knob - 1.2),
                                  [(0, (205, 205, 205)), (.5, (232, 232, 232)), (1, (252, 252, 252))])
        layer.blit(face, (round((kx + .6) * S), round((top + .6) * S)))
        label = 'ON' if on else 'OFF'
        color = (255, 255, 255) if on else (128, 128, 128)
        x = left + (25 if on else 52)
        control = self.control_font(15)
        self.text(layer, label, x, top + height / 2 - self.cap_offset(15, control), 15, color, center=True, font=control)

    def slider(self, layer, top, value):
        """A UISlider row's control line (track between the two speaker icons)."""
        middle = top + 86
        small, large = self.art(155, 53), self.art(155, 54)
        layer.blit(small, (round(108 * S), round(middle * S - small.get_height() / 2)))
        layer.blit(large, (round(620 * S), round(middle * S - large.get_height() / 2)))
        left, right = 143, 603
        self.rect(layer, (74, 132, 213), (left, middle - 3, right - left, 6), 3)
        self.rect(layer, (150, 185, 235), (left, middle - 3, right - left, 2), 1)
        knob = round((left + (right - left) * value) * S)
        pygame.draw.circle(layer, (214, 214, 214), (knob, round(middle * S)), round(10.5 * S))
        pygame.draw.circle(layer, (160, 160, 160), (knob, round(middle * S)), round(10.5 * S), S)
        pygame.draw.circle(layer, (245, 245, 245), (knob, round((middle - 2) * S)), round(6 * S))
        return pygame.Rect(left - 10, middle - 22, right - left + 20, 44)

    @staticmethod
    def slider_value(x):
        """The volume a pointer at frame x sets: the slider's track runs from 143 to 603."""
        return (x - 143) / 460

    def rows_body(self, layer, top, height, color=None, *, lit=False):
        color = color or self.ROW_COLORS[0]
        if lit:
            color = tuple(round(c * FOCUS_SHADE) for c in color)
        self.rect(layer, self.see_through(color), (PANEL_X + BORDER, top, PANEL_W - 2 * BORDER, height))
        self.rect(layer, self.SEPARATOR_COLOR, (PANEL_X + BORDER, top, PANEL_W - 2 * BORDER, 1))

    def row_color(self, index):
        return self.ROW_COLORS[index % 2]

    def row(self, layer, top, label, *, height=ROW, color=None, background=None, lit=False):
        color = color or self.LABEL_COLOR
        self.rows_body(layer, top, height, background, lit=lit)
        font, lines, current = self.font(ROW_PX), [], ''
        for word in label.split(' '):
            trial = f'{current} {word}' if current else word
            if current and font.size(trial)[0] / S > 500:       # "Privacy Policy/ EULA/ Terms & Conditions" wraps
                lines.append(current)
                current = word
            else:
                current = trial
        lines.append(current)
        pitch = 26.6
        for index, line in enumerate(lines):
            middle = top + ROW / 2 + (index - (len(lines) - 1) / 2) * pitch
            self.text(layer, line, PANEL_X + 31, middle - self.cap_offset(ROW_PX), ROW_PX, color)

    # -- screens ---------------------------------------------------------
    def layout(self, settings, host_rows=(), *, message=''):
        """(layer, buttons): buttons are (Rect in points, command). Commands:
        ('pause_open', screen), ('pause_back',), ('resume',), ('main_menu',), ('save',), ('load',),
        ('pause_toggle', 'vibration'|'music'|'sound'|'side_panels'|'choice_hints'|'skip_minigames'|'skip_ad_intros'|'skip_upsell_intros'|'hd_backdrop'),
        ('pause_slider', 'music'|'sound', Rect), ('pause_link', url). Options is a list of categories
        ('pause_open', 'options:<category>'), each a page of its switches and sliders. While a page slides in
        (`open` / `back`) the layer holds both cards and there are no buttons."""
        layer, buttons = self.screen_layout(settings, host_rows, message=message)
        self.shown = layer
        if self.slide is None:
            return layer, buttons
        direction, previous, elapsed = self.slide
        shift = ease_in_out(elapsed / SLIDE_MS) * layer.get_width()
        both = pygame.Surface(layer.get_size(), pygame.SRCALPHA).convert_alpha()
        both.blit(previous, (round(-direction * shift), 0))
        both.blit(layer, (round(direction * (layer.get_width() - shift)), 0))
        return both, []

    def screen_layout(self, settings, host_rows=(), *, message=''):
        """The current screen alone, at rest: `layout`'s (layer, buttons)."""
        layer = pygame.Surface((FRAME[0] * S, FRAME[1] * S), pygame.SRCALPHA).convert_alpha()
        strings, state, buttons = self.strings(), self.state, []
        bottom_rule = None
        focus = state.focus
        if state.screen == 'pause':
            entries = [(strings[20], ('resume',)), (strings[10], ('pause_open', 'options')),
                       (strings[120], ('pause_open', 'help'))]
            entries.append((strings[9], ('main_menu',)))
            entries += list(host_rows)
            height = HEADER + ROW * len(entries) + FOOT
            top = (FRAME[1] - height) / 2
            body = self.panel(layer, top, top + height, strings[8])
            for i, (label, command) in enumerate(entries):
                y = body + i * ROW
                self.row(layer, y, label, background=self.row_color(i), lit=focus == command)
                buttons.append((pygame.Rect(PANEL_X, y, PANEL_W, ROW), command))
            bottom_rule = body + len(entries) * ROW
        elif state.screen == 'options':
            # The categories that have rows here, laid out as Help & About's list is.
            categories = [(category, label) for category, label in OPTION_CATEGORIES
                          if self.option_rows(category, settings, strings)]
            height = HEADER + ROW * len(categories) + FOOT
            top = (FRAME[1] - height) / 2
            body = self.panel(layer, top, top + height, strings[10])
            for i, (category, label) in enumerate(categories):
                y = body + i * ROW
                command = ('pause_open', 'options:' + category)
                self.row(layer, y, label, background=self.row_color(i), lit=focus == command)
                buttons.append((pygame.Rect(PANEL_X, y, PANEL_W, ROW), command))
            bottom_rule = top + height - FOOT
            buttons.append((self.back_button(layer, top + height, lit=focus == ('pause_back',)), ('pause_back',)))
        elif state.screen.startswith('options:'):
            # Sound: the app's own Music / Sound switches and sliders. General: in a story, the side panels (a native
            # feature: the device shows them on rotation, so it has no switch or string of its own), then this
            # player's switches (exp-runtime's Options -> Cheats; no native strings, so the labels are this project's).
            category = state.screen.split(':', 1)[1]
            rows = self.option_rows(category, settings, strings)
            sliders = sum(1 for kind, _, _ in rows if kind == 'slider')
            height = HEADER + (len(rows) - sliders) * ROW + sliders * SLIDER_ROW + FOOT
            top = (FRAME[1] - height) / 2
            title = dict(OPTION_CATEGORIES).get(category, strings[10])
            body = self.panel(layer, top, top + height, title)
            y = body
            for index, (kind, label, key) in enumerate(rows):
                if kind == 'slider':
                    self.rows_body(layer, y, SLIDER_ROW, self.row_color(index),
                                   lit=focus is not None and focus[:2] == ('pause_slider', key))
                    self.text(layer, label, PANEL_X + 31, y + 39 - self.cap_offset(ROW_PX), ROW_PX, self.LABEL_COLOR)
                    track = self.slider(layer, y, settings[key + '_volume'])
                    buttons.append((track, ('pause_slider', key, track)))
                    y += SLIDER_ROW
                    continue
                command = ({'switch': 'pause_toggle', 'cycle': 'pause_cycle'}.get(kind, 'pause_action'), key)
                self.row(layer, y, label, background=self.row_color(index), lit=focus == command)
                if kind == 'switch':
                    self.switch(layer, PANEL_X + PANEL_W - CONTROL_RIGHT, y + ROW / 2, settings.get(key, False))
                    buttons.append((pygame.Rect(PANEL_X + PANEL_W - 250, y, 250, ROW), ('pause_toggle', key)))
                elif kind == 'cycle':
                    box = pygame.Rect(PANEL_X + PANEL_W - CONTROL_RIGHT - CYCLE_SIZE[0],
                                      y + (ROW - CYCLE_SIZE[1]) / 2, *CYCLE_SIZE)
                    self.cycle_button(layer, box, settings[key], pressed=self.pressed == ('pause_cycle', key))
                    buttons.append((box, ('pause_cycle', key)))
                else:
                    buttons.append((pygame.Rect(PANEL_X, y, PANEL_W, ROW), ('pause_action', key)))
                y += ROW
            bottom_rule = top + height - FOOT
            buttons.append((self.back_button(layer, top + height, lit=focus == ('pause_back',)), ('pause_back',)))
        elif state.screen == 'help':
            order = MAIN_HELP_ORDER if self.main_menu else HELP_ORDER
            height = HEADER + ROW * len(order) + FOOT
            top = (FRAME[1] - height) / 2
            body = self.panel(layer, top, top + height, strings[120])
            for i, page in enumerate(order):
                y = body + i * ROW
                self.row(layer, y, strings[170 if page == 'privacy' else self.PAGES[page][0]], background=self.row_color(i),
                         lit=focus == ('pause_open', page))
                buttons.append((pygame.Rect(PANEL_X, y, PANEL_W, ROW), ('pause_open', page)))
            bottom_rule = top + height - FOOT
            buttons.append((self.back_button(layer, top + height, lit=focus == ('pause_back',)), ('pause_back',)))
        else:
            self.text_page(layer, buttons)
        if bottom_rule is not None:
            self.rect(layer, self.SEPARATOR_COLOR, (PANEL_X + BORDER, bottom_rule, PANEL_W - 2 * BORDER, 1))
        if message:
            self.text(layer, message, 384, FRAME[1] - 90, 22, (255, 255, 255), center=True)
        self.buttons = buttons
        return layer, buttons

    pressed = None                  # the command under the pointer, for buttons drawn pressed (set by the host)
    buttons = ()                    # the last layout's buttons, for `key`

    def key(self, key):
        state = self.state
        commands = [command for _, command in self.buttons]
        if ('pause_scroll',) in commands and key in PAGE_KEYS:
            state.scroll = min(state.max_scroll, max(0., state.scroll + PAGE_KEYS[key]))
            return None
        targets = [command for command in commands if command[0] not in ('pause_scroll', 'pause_link')]
        focus = state.focus if state.focus in targets else None
        if focus is not None and focus[0] == 'pause_slider' and key in (pygame.K_LEFT, pygame.K_RIGHT):
            return 'pause_volume', focus[1], VOLUME_STEP if key == pygame.K_RIGHT else -VOLUME_STEP
        if focus_step(key):
            state.focus = step_focus(targets, focus, focus_step(key))
        elif key in KEYS_ACTIVATE and focus is not None and focus[0] != 'pause_slider':
            return focus
        return None

    SWITCH_LABELS = SWITCH_LABELS        # a game's own wording (desktop_cod_pause.CodPauseMenu)

    def option_rows(self, category, settings, strings):
        """[(kind, label, key)] of an Options category: 'switch', 'slider', 'cycle' or 'action' rows, those whose
        setting the host offers."""
        if category == 'sound':
            # This player's buzz in place of the iPhone's vibration (PR #10): last, under its own name. On a device that
            # can vibrate (exp-runtime's iOS host, graphics.supports_vibration) the same preference is the game's own
            # Vibration switch (string 11), and the buzz is not played.
            from . import graphics
            label = strings[11] if graphics.supports_vibration() else VIBRATION_SOUND_LABEL
            vibration = [('switch', label, 'vibration')] if 'vibration' in settings else []
            return [('switch', strings[12], 'music'), ('slider', strings[13], 'music'),
                    ('switch', strings[14], 'sound'), ('slider', strings[15], 'sound')] + vibration
        if category == 'general':
            rows = [('switch', self.SWITCH_LABELS[key], key) for key in GENERAL_KEYS if key in settings]
            if 'title_language' in settings:
                rows.append(('cycle', TITLE_LANGUAGE_LABEL, 'title_language'))
            return rows
        if category == 'extras':
            return [('switch', self.SWITCH_LABELS[key], key) for key in EXTRAS_KEYS if key in settings]
        if category == 'data':
            return [('action', label, key) for key, label in DATA_ACTIONS if key in settings]
        return []

    def cycle_button(self, layer, box, label, *, pressed=False):
        """A footer-style button holding a value: caps and middle from pack 32 scaled to `box` (the caps keep their
        shape), the label in white."""
        S = self.scale
        first, middle, last = (self.art(32, i) for i in self.CYCLE_FRAMES[bool(pressed)])
        x, y, width, height = box
        cap = first.get_width() / S * height / (first.get_height() / S)
        layer.blit(pygame.transform.smoothscale(first, (round(cap * S), round(height * S))), (round(x * S), round(y * S)))
        layer.blit(pygame.transform.smoothscale(middle, (round((width - 2 * cap) * S), round(height * S))),
                   (round((x + cap) * S), round(y * S)))
        layer.blit(pygame.transform.smoothscale(last, (round(cap * S), round(height * S))),
                   (round((x + width - cap) * S), round(y * S)))
        text = self.font(CYCLE_POINTS).render(label, True, (255, 255, 255))
        layer.blit(text, text.get_rect(center=(round((x + width / 2) * S), round((y + height / 2 - 2) * S))))

    def text_page(self, layer, buttons):
        state = self.state
        title, body = self.text_lines(state.screen)
        top, bottom = TALL
        # Two-line titles get a taller header, as photographed (152 points).
        header = HEADER + 40 if len(self.title_lines(title)) > 1 else HEADER
        self.panel(layer, top, bottom, title, header=header)
        first = top + header
        area = pygame.Rect(PANEL_X + BORDER, first, PANEL_W - 2 * BORDER, bottom - FOOT - first)
        self.rect(layer, self.see_through(self.PAGE_BACKGROUND), area)
        self.rect(layer, self.SEPARATOR_COLOR, (area.x, area.y, area.width, 1))
        font = self.font(TEXT_PX)
        lines = []                                  # each a list of words, each a list of (text, url) pieces
        for paragraph in body.split('\n'):
            current = []
            for word in link_words(paragraph):
                trial = current + [word]
                if font.size(' '.join(''.join(t for t, _ in w) for w in trial))[0] / S > area.width - 36 and current:
                    lines.append(current)
                    current = [word]
                else:
                    current = trial
            lines.append(current)
        pitch = TEXT_PITCH
        state.max_scroll = max(0., len(lines) * pitch + 24 - area.height)
        state.scroll = max(0., min(state.max_scroll, state.scroll))
        clip = pygame.Rect(area.x * S, area.y * S, area.width * S, area.height * S)
        layer.set_clip(clip)
        y = area.y + 16 - state.scroll
        links = []
        for line in lines:
            if area.y - pitch < y < area.bottom:
                self.text(layer, ' '.join(''.join(t for t, _ in word) for word in line), area.x + 21, y, TEXT_PX,
                          self.TEXT_COLOR)
                # Each linked piece is underlined and tappable where it sits in its line (this player's own addition;
                # a native text page's body never carries a link, see `LINK_PATTERN`).
                prefix, spans = '', []              # [left, right, url]; a link's words join across their spaces
                for index, word in enumerate(line):
                    if index:
                        prefix += ' '
                    for text, url in word:
                        left, right = font.size(prefix)[0] / S, font.size(prefix + text)[0] / S
                        if url is not None:
                            if spans and spans[-1][2] == url and spans[-1][1] >= font.size(prefix.rstrip(' '))[0] / S:
                                spans[-1][1] = right
                            else:
                                spans.append([left, right, url])
                        prefix += text
                underline_y = round(y + TEXT_PX - 2)
                for left, right, url in spans:
                    pygame.draw.line(layer, self.TEXT_COLOR, (round((area.x + 21 + left) * S), underline_y * S),
                                     (round((area.x + 21 + right) * S), underline_y * S), max(1, S))
                    links.append((pygame.Rect(area.x + 21 + left, y, right - left, pitch), url))
            y += pitch
        layer.set_clip(None)
        self.rect(layer, self.SEPARATOR_COLOR, (area.x, area.bottom, area.width, 1))
        buttons.append((self.back_button(layer, bottom, lit=state.focus == ('pause_back',)), ('pause_back',)))
        buttons.append((area, ('pause_scroll',)))
        for rect, url in links:
            buttons.append((rect.clip(area), ('pause_link', url)))

    # -- dimming ----------------------------------------------------------
    @staticmethod
    def sepia(surface):
        """The frame dimmed and tinted the way the pause overlay does."""
        image = Image.frombytes('RGB', surface.get_size(), pygame.image.tobytes(surface, 'RGB'))
        image = image.convert('RGB', SEPIA)
        return pygame.image.frombytes(image.tobytes(), image.size, 'RGB')
