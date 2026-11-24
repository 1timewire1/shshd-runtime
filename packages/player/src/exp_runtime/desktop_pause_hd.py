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

from . import graphics as pygame
from PIL import Image

from .desktop_pause import ease_in_out
from .help_text_overrides import HELP_TEXT_OVERRIDES
from .menu import MenuStrings
from .pointer import step_focus
from .ui_assets import ImagePack

FRAME = (768, 1024)
from .hd_scale import S
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
INTRO_PAD = 14                          # points above and below a host row page's text in the skin (the legal page's)
INTRO_LEFT = 31                         # ...and its inset, the rows' labels'
BACK = (14, 13)                       # back button inset from the panel's left / bottom
SLIDER_ROW = 130
SIDE_PANELS_LABEL = 'Side Panels'
CHOICE_HINTS_LABEL = 'Choice Hints'
SKIP_MINIGAMES_LABEL = 'Ask to Skip Mini-Games'
SKIP_AHEAD_LABEL = 'Skip Ahead'                # the pause menu's row, and its key's action (skip_ahead.py)
UNDO_LABEL = 'Undo'                            # the pause menu's row: back to the last stop kept (undo.py)
JOURNAL_LABEL = 'Quest Journal'                # the pause menu's row in a story with a journal (quest_journal.py)
ALLOW_UNDO_LABEL = 'Allow Undo'                # Extras: keeps a save at each stop and offers that row (owner, 2026-11-06)
ALLOW_SKIP_AHEAD_LABEL = 'Allow Skip Ahead'    # Extras: offers that row and key (owner, 2026-11-04)
GRIDS_AS_MEMORY_LABEL = "Use '11's Memory for Word Grid"     # SHS '11's game in place of letter grids (owner, 2026-11-04)
SKIP_AD_INTROS_LABEL = 'Skip Ad Intros'
SKIP_UPSELL_INTROS_LABEL = 'Skip Upsell Intros'    # the store plugs some SHS episodes open with (upsell_intro.py)
VIBRATION_SOUND_LABEL = 'Simulated Vibration Sound'
# General's switch for the device's own vibrator (owner, 2026-10-29), offered where the host has one
# (graphics.supports_vibration: Android's, the iPhone's); the simulated sound stays in Sound.
DEVICE_VIBRATION_LABEL = 'Vibration'
AUTOPLAY_LABEL = 'Autoplay Dialogue'           # dialogue advances by itself (this player's); choices still wait
DISABLE_CHOICE_TIMER_LABEL = 'Disable Choice Timer'     # timed choices wait (this player's)
HIRES_PORTRAITS_LABEL = 'Hi-Res Portraits'      # translated New Rules episodes: the X1i's redrawn faces
MS3_CHARACTERS_LABEL = 'MS3 Characters'         # translated X360 episodes: the April build's looks, else the May build's
JAVA_LOOK_LABEL = "Java '08 Look"               # translated BREW episodes: the Java '08 demo's backdrop, icons and catch game
BREW_08_BACKGROUNDS_LABEL = "'08 Backgrounds"   # '07-badged BREW episodes: '08's art for the shared locations (decision 7B)
HOLLYWOOD_ART_LABEL = 'Use SHW Art in Preview'  # the BREW Surviving Hollywood Preview: the demo's own art (`shshw`; owner,
                                                # 2026-11-19: it was "Hollywood Art")
DSI_BACKGROUNDS_LABEL = 'DSi Backgrounds'       # SHS's own episodes the DSiWare game drew: its two screens (`shsdsi`)
DSI_PIXELS_NAMES = {'sharp': 'Sharp', 'smooth': 'Smooth'}      # ...enlarged with nearest neighbour (Sharp) or smoothly
# Extras' DSi Backgrounds (owner, 2026-11-19): one choice, Off or on with its pixels Sharp or Smooth, in place of Add-Ons'
# switch and its DSi Pixels. The two stay separate settings underneath (menu.MenuState dsi_backgrounds, dsi_pixels).
DSI_BACKGROUNDS_NAMES = {'off': 'Off', **DSI_PIXELS_NAMES}


def dsi_backgrounds_value(enabled, pixels):
    """DSi Backgrounds' choice (DSI_BACKGROUNDS_NAMES) for the two settings."""
    return pixels if enabled and pixels in DSI_PIXELS_NAMES else 'sharp' if enabled else 'off'
# The values Preferred Language gives the stories' translations (languages.language_settings; HD presentation only): the
# DSi's eight stories in its translations, SHS '11's in their own Italian and Creator episodes in their project's other
# languages (resource 6). Each was a choice of its own until 2026-11-18 (DSi Language, '11 Language, Story Language).
DSI_LANGUAGE_NAMES = {'off': 'Off', 'fr': 'Français', 'it': 'Italiano', 'de': 'Deutsch', 'es': 'Español'}
SHS11_LANGUAGE_NAMES = {'off': 'English', 'it': 'Italiano'}
STORY_LANGUAGE_NAMES = {'off': 'Off', 'en': 'English', 'fr': 'Français', 'it': 'Italiano', 'de': 'Deutsch', 'es': 'Español'}
SMARTPHONE_MUSIC_LABEL = 'Smartphone Music'     # translated SHS '11 episodes: the smartphone's music, else none
WORD_GRID_SKIN_LABEL = 'Use Word Grid Skin'     # ...their minigames in the HD word game's look (with its art imported)
CH_PORTRAITS_LABEL = 'HD Portraits in CoD'      # CoD with its portrait addon: Claire Hart's sharper originals
CH_BACKDROP_LABEL = 'Backdrop'                  # ...and Claire Hart's green backdrop, in place of SHS HD's collage
DIM_BACKDROPS_LABEL = 'Dim Backdrops'           # Claire Hart's translations: backdrops darkened as the game drew them
CH_43_LABEL = 'Claire Hart 4:3'                # ...their cases in Claire Hart's own 4:3 where the window has room (owner, 2026-11-22)
# Claire Hart UI (owner, 2026-11-19 as Claire Hart Dialogue; renamed 2026-11-22 when it took CoD's other screens): CoD's
# dialogue in Claire Hart's speech bubbles and Romic, its choices, windows and pause menu in Classic's dress. Everywhere ('all')
# is every episode and the main menu's screens too (but the episode grid); Claire Hart Cases leaves the menus CoD's.
CH_DIALOGUE_LABEL = 'Claire Hart UI'
CH_DIALOGUE_NAMES = {'off': 'Off', 'cases': 'Claire Hart Cases', 'all': 'Everywhere'}
CLAIRE_POWERUPS_LABEL = 'Power-Ups'           # Claire Hart's rounds' four power-ups (R2, owner, 2026-11-20)
CLAIRE_POWERUPS_NAMES = {'once': 'Once Each Round', 'unlimited': 'Unlimited', 'off': 'Off'}
ARENA_MINIGAMES_LABEL = 'Use Translated Mini-Games'      # translated episodes' real minigames, else timed choices
ARENA_SKIN_LABEL = 'Use X360 Arena Skin'        # ...New Rules' arena in the X360 prototype's look (its addon imported)
# A switch that only concerns one legacy game's translated episodes shows that game's tag before its label (owner,
# 2026-10-26): key -> the tag in a game profile's LEGACY_GAMES. The switch itself is offered only when such episodes
# are there (application.hires_portraits_offered, Desktop.hires_switch). Use Translated Mini-Games concerns several.
SWITCH_BADGES = {'hires_portraits': 'SHSNR', 'ms3_characters': 'SHSX360', 'java_look': 'SHS08', 'brew_08_backgrounds': 'SHS07', 'hollywood_art': 'SHS07', 'dsi_backgrounds': 'SHSDSI', 'smartphone_music': 'SHS11', 'word_grid_skin': 'SHS11', 'arena_skin': 'SHSNR',
                 'ch_portraits': 'CHC',
                 'ch_backdrop': 'CHC', 'dim_backdrops': 'CHC', 'ch_43': 'CHC', 'ch_dialogue': 'CHC', 'claire_powerups': 'CHC'}
# The skin concerns New Rules' episodes, so it wears their tag; the other game it comes from is named in that game's
# colour (owner, 2026-11-02). key -> the tag whose name in the label is coloured.
LABEL_TINTS = {'arena_skin': 'SHSX360', 'hollywood_art': 'SHW'}
BADGE_PX, BADGE_PAD, BADGE_HEIGHT, BADGE_GAP = 20, 9, 30, 12


def legacy_tag(tag):
    """(text, colour) of a game's tag in a profile's LEGACY_GAMES, or None."""
    from .games import GAMES
    for game in ('shs', 'cod'):
        legacy = getattr(GAMES.get(game), 'LEGACY_GAMES', {}).get(tag)
        if legacy is not None:
            return legacy['badge'], legacy['color']
    return None


def switch_badge(key):
    """(text, colour) of the switch's game tag, or None."""
    return legacy_tag(SWITCH_BADGES.get(key))
HD_BACKDROP_LABEL = 'SHS HD Backdrop'          # SHS HD's collage beside the frame, else a dark fill (this player's)
CHECK_UPDATES_LABEL = 'Check for Updates'      # the release check at launch (updates.py); main menu only
# Options lists categories, each opening a page of its own switches (owner, 2026-10-14; no native strings, this
# player's own: SHS HD's Options is one page). A row shows when its setting is offered (`layout`'s `settings`), so a
# game leaves out what does not apply to it.
# Extras holds the play aids that change how a story plays (owner, 2026-10-21). Add-Ons holds what only concerns translated
# games and addons (owner, 2026-11-02), so the others stay short; like any category, it's hidden when it has no rows.
OPTION_CATEGORIES = (('general', 'General'), ('sound', 'Sound'), ('controller', 'Controller'), ('extras', 'Extras'),
                     ('addons', 'Add-Ons'), ('data', 'Data Management'))
GENERAL_KEYS = ('side_panels', 'device_vibration', 'autoplay', 'skip_ad_intros', 'skip_upsell_intros', 'hd_backdrop',
                'check_updates')
EXTRAS_KEYS = ('disable_choice_timer', 'choice_hints', 'skip_minigames', 'skip_ahead', 'undo', 'grids_as_memory')
# In the episode lists' order of their games (owner, 2026-11-19): '07, '08, New Rules, X360, '11, then CoD's; last the two
# that need two add-ons, Use SHW Art in Preview ('07's story with `shshw`) and the X360 Arena Skin.
ADDON_KEYS = ('arena_minigames', 'brew_08_backgrounds', 'java_look', 'hires_portraits', 'ms3_characters', 'smartphone_music',
              'word_grid_skin', 'ch_portraits', 'ch_backdrop', 'dim_backdrops', 'ch_43', 'hollywood_art', 'arena_skin')
# General's Preferred Language (owner, 2026-11-18; it was Episode Titles): the episode titles, and the stories of the
# add-ons that have a translation (DSi, SHS '11, the Creator's), in it where each has it (languages.language_settings);
# `settings['preferred_language']` is the current one's name. Data Management's rows are actions, tapped like Help &
# About's rows; it is offered by the main menu only.
PREFERRED_LANGUAGE_LABEL = 'Preferred Language'
# General's Start In, also offered by the main menus only (owner, 2026-10-29): which game the app opens in
# (settings.AppSettings.start_in); `settings['start_in']` is the current choice's name.
START_IN_LABEL = 'Start In'
START_IN_NAMES = {'auto': 'Last Played', 'games': 'Choose a Game', 'shs': 'Surviving High School',
                  'cod': 'Cause of Death'}
# General's Aspect Ratio (owner, 2026-11-11; frame_shape.py): the frame's shape, this device's own (settings.AppSettings),
# offered by every Options page that has General, the pause menu's too.
ASPECT_LABEL = 'Aspect Ratio'
ASPECT_NAMES = {'3:4': '3:4 (HD)', '2:3': '2:3 (Whole Picture)', '9:16': '9:16', 'fit': 'Fit Screen'}
# Extras' Unlock Warping (owner, 2026-10-29): SHS's story-tree lock (`SHSEngine +0x6490a`, cleared by finishing
# Football Season) undone at once, with the app's own notice (menu 29); offered only while warping is locked.
UNLOCK_WARP_LABEL = 'Unlock Warping'
# Sound's last row on the main menu (owner, 2026-10-29): launch without asking "Play with sound?" (the music and sound
# switches as set).
SKIP_SOUND_PROMPT_LABEL = 'Skip Sound Prompt'
# Controller (owner, 2026-10-29), offered while a controller is connected: which face button confirms, the bottom one
# or the right one (a Nintendo layout; the other face buttons swap with it). Football's plays stay by position.
CONFIRM_BUTTON_LABEL = 'Confirm Button'
CONFIRM_NAMES = {'south': 'Bottom', 'east': 'Right'}
# How a controller draws a word in the word grid: Hold (the default), confirm held drags; Tap, confirm adds the
# highlighted cell.
GRID_CONTROLS_LABEL = 'Word Grid Controls'
GRID_CONTROLS_NAMES = {'tap': 'Tap', 'hold': 'Hold'}
# The preferred languages (languages.PREFERRED_LANGUAGES), by their own names; the main menu names them from the game's
# strings instead (settings['preferred_language_names']).
LANGUAGE_NAMES = {'en': 'English', 'fr': 'Français', 'it': 'Italiano', 'de': 'Deutsch', 'es': 'Español'}
# An option that is one of a few values (owner, 2026-11-09): its row opens a menu page of them (screen 'choice:<key>', a
# row each, the current one ticked) instead of a button that steps through them, and shows the current one under its name
# in smaller letters, as the episode lists show a category or airdate under a title (desktop_episode_list_hd: 13 points
# under 19, at alpha 150). Picking one sends ('pause_cycle', key, value), and the host slides back to the option's page.
# Add-Ons' Title Screen Music (main menu only; owner, 2026-11-09): the tune the main menu plays, the game's own, a translated
# game's from its addon, or Auto (the game last played). The host offers those whose addon it has (`title_music_names`).
TITLE_MUSIC_LABEL = 'Title Screen Music'
# The games are listed in the episode lists' order ('07, Surviving Hollywood, '08, New Rules, X360, '11; owner, 2026-11-19);
# BREW's one tune stands for '07 and '08 together, before Surviving Hollywood.
TITLE_MUSIC_NAMES = {'default': 'Default', 'auto': 'Auto', 'brew': "'07 / '08", 'shw': 'Surviving Hollywood', 'nr': 'New Rules',
                     'x360': 'X360', 'shs11': "'11", 'chc': 'Claire Hart'}
# Add-Ons' Title Screen Look (main menu only; owner, 2026-11-16): the main menu's art, the same way; BREW's editions are two.
TITLE_LOOK_LABEL = 'Title Screen Look'
TITLE_LOOK_NAMES = {'default': 'Default', 'auto': 'Auto', 'brew07': "'07", 'shw': 'Surviving Hollywood', 'brew08': "'08",
                    'nr': 'New Rules', 'x360': 'X360', 'shs11': "'11", 'chc': 'Claire Hart'}
# On the main menu, Add-Ons keeps Use Translated Mini-Games, Title Screen Music and Title Screen Look, and the other add-on switches go one page
# further in, Per-Game Settings (owner, 2026-11-09); the pause menu lists them all on Add-Ons, as before.
PER_GAME_LABEL = 'Per-Game Settings'
PAGE_TITLES = {'per_game': PER_GAME_LABEL}
PAGE_PARENTS = {'options:per_game': 'options:addons'}
# General's Text Animation (owner, 2026-11-22): a dialogue page's text letter by letter (Android's, the default), in the
# iOS builds' line wipe, or at once (dialogue_animation.TEXT_ANIMATIONS)
TEXT_ANIMATION_LABEL = 'Text Animation'
TEXT_ANIMATION_NAMES = {'letters': 'Letter by Letter', 'wipe': 'Line Wipe', 'instant': 'Instant'}
CHOICE_NAMES = {'aspect_ratio': ASPECT_NAMES, 'preferred_language': LANGUAGE_NAMES, 'start_in': START_IN_NAMES,
                'text_animation': TEXT_ANIMATION_NAMES, 'controller_confirm': CONFIRM_NAMES,
                'grid_controls': GRID_CONTROLS_NAMES, 'title_music': TITLE_MUSIC_NAMES, 'title_look': TITLE_LOOK_NAMES,
                'dsi_backgrounds': DSI_BACKGROUNDS_NAMES, 'ch_dialogue': CH_DIALOGUE_NAMES,
                'claire_powerups': CLAIRE_POWERUPS_NAMES}
CHOICE_LABELS = {'aspect_ratio': ASPECT_LABEL, 'preferred_language': PREFERRED_LANGUAGE_LABEL, 'start_in': START_IN_LABEL,
                 'text_animation': TEXT_ANIMATION_LABEL,
                 'controller_confirm': CONFIRM_BUTTON_LABEL, 'grid_controls': GRID_CONTROLS_LABEL,
                 'title_music': TITLE_MUSIC_LABEL, 'title_look': TITLE_LOOK_LABEL, 'dsi_backgrounds': DSI_BACKGROUNDS_LABEL,
                 'ch_dialogue': CH_DIALOGUE_LABEL, 'claire_powerups': CLAIRE_POWERUPS_LABEL}
CHOICE_PARENTS = {'aspect_ratio': 'options:general', 'preferred_language': 'options:general', 'start_in': 'options:general',
                  'text_animation': 'options:general',
                  'controller_confirm': 'options:controller', 'grid_controls': 'options:controller',
                  'title_music': 'options:addons', 'title_look': 'options:addons', 'dsi_backgrounds': 'options:extras',
                  'ch_dialogue': 'options:per_game', 'claire_powerups': 'options:per_game'}
# Add-on choices the main menu keeps on Per-Game Settings rather than Add-Ons: their page's way back goes there.
PER_GAME_CHOICES = ('ch_dialogue', 'claire_powerups')
VALUE_PX, VALUE_GAP, VALUE_ALPHA = 19, 3, 150
# Data Management (owner, 2026-10-29) lists Add Content, its pages, then Add-Ons and Reset Settings; each page's rows are
# the actions the main menu offers (`settings` has the key). A row is (key, label); a page is (screen, title, rows).
# Add Content (episodes, add-ons and fonts) is on Data Management's own page, first (owner, 2026-11-21; it was the
# Episodes page's Add Episodes).
DATA_FIRST = (('add_episodes', 'Add Content'),)
DATA_PAGES = (('data:library', 'Library', (('library_info', 'Library Info'), ('storage', 'Storage'),
                                           ('verify_library', 'Verify Library'), ('rebuild_previews', 'Rebuild Previews'),
                                           ('rebuild_hd_art', 'Rebuild HD Art'), ('open_library', 'Open Another Library'),
                                           ('delete_library', 'Delete Library'),
                                           # The chooser's (both games, owner 2026-10-30): a row per game, then both.
                                           ('delete_library_shs', 'Delete Surviving High School'),
                                           ('delete_library_cod', 'Delete Cause of Death'),
                                           ('delete_libraries', 'Delete Both Libraries'))),
              ('data:episodes', 'Episodes', (('mark_read', 'Mark as Finished'), ('delete_episodes', 'Delete Episodes'),
                                             ('export_episodes', 'Export Episodes'), ('export_folder', 'Exports Folder'),
                                             ('reset_trees', 'Reset Decision Tree'))),
              ('data:progress', 'Progress', (('back_up', 'Back Up Progress'), ('restore', 'Restore Progress'),
                                             ('backup_folder', 'Backups Folder'), ('reset_names', 'Reset Names'),
                                             ('delete_saves', 'Delete All Saves'))),
              ('data:sync', 'Sync Devices', (('sync_send', 'Send to Another Device'),
                                             ('sync_receive', 'Receive from Another Device'))))
# Add-Ons opens the host's page of them (desktop_addons), as Restore Progress does its rows.
DATA_LAST = (('manage_addons', 'Add-Ons'), ('reset_settings', 'Reset Settings'))
DATA_ACTIONS = DATA_FIRST + tuple(row for _, _, rows in DATA_PAGES for row in rows) + DATA_LAST
# A row's control sits against the card's right side, CONTROL_RIGHT points in (owner, 2026-10-14; SHS HD's own
# switches sat 168 in): the switch (79 x 27) and the value button, a little bigger (104 x 34, its label at 18 points).
CONTROL_RIGHT = 26
CYCLE_SIZE, CYCLE_POINTS = (104, 34), 18
SWITCH_LABELS = {'side_panels': SIDE_PANELS_LABEL, 'device_vibration': DEVICE_VIBRATION_LABEL,
                 'autoplay': AUTOPLAY_LABEL, 'disable_choice_timer': DISABLE_CHOICE_TIMER_LABEL, 'choice_hints': CHOICE_HINTS_LABEL,
                 'skip_minigames': SKIP_MINIGAMES_LABEL, 'skip_ad_intros': SKIP_AD_INTROS_LABEL,
                 'grids_as_memory': GRIDS_AS_MEMORY_LABEL, 'skip_ahead': ALLOW_SKIP_AHEAD_LABEL, 'undo': ALLOW_UNDO_LABEL,
                 'skip_upsell_intros': SKIP_UPSELL_INTROS_LABEL,
                 'hd_backdrop': HD_BACKDROP_LABEL, 'hires_portraits': HIRES_PORTRAITS_LABEL,
                 'ms3_characters': MS3_CHARACTERS_LABEL, 'java_look': JAVA_LOOK_LABEL, 'brew_08_backgrounds': BREW_08_BACKGROUNDS_LABEL, 'hollywood_art': HOLLYWOOD_ART_LABEL, 'dsi_backgrounds': DSI_BACKGROUNDS_LABEL, 'smartphone_music': SMARTPHONE_MUSIC_LABEL, 'word_grid_skin': WORD_GRID_SKIN_LABEL,
                 'ch_portraits': CH_PORTRAITS_LABEL,
                 'ch_backdrop': CH_BACKDROP_LABEL, 'dim_backdrops': DIM_BACKDROPS_LABEL, 'ch_43': CH_43_LABEL,
                 'arena_minigames': ARENA_MINIGAMES_LABEL, 'arena_skin': ARENA_SKIN_LABEL,
                 'check_updates': CHECK_UPDATES_LABEL}
# HD dims and sepia-tints what was on screen; a fit to IMG_0110's untouched margins
# (rms ~2 levels): out = M . (r, g, b) + c.
SEPIA = (0.779, 0.166, 0.0, 102.1,
         0.703, 0.144, 0.0, 90.5,
         0.549, 0.110, 0.0, 70.5)
# The native app's own CFBundleShortVersionString (1.4.38) is irrelevant to a player here -- the only place the
# string bank's ~276~ token appears at all is the About page (checked against a real HD string bank), and only
# this project's own override of it (`help_text_overrides.py`) is ever shown, so this reports shshd-runtime's
# own release instead. The one line to edit on a release; nothing else about the About text needs to change.
VERSION = '1.1.1'
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
# A switch's knob slides to its new side, carrying the track (the blue ON half and the white OFF half) with it, as the
# classic UISwitch's does. The duration and the ease-in-out are not measured from the device.
SWITCH_MS = 200
# Keyboard navigation (not native): arrows highlight a row, Enter or Space taps it, Left / Right move a slider.
FOCUS_SHADE, VOLUME_STEP = .85, .1
KEYS_ACTIVATE = (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE)
PAGE_KEYS = {pygame.K_UP: -40, pygame.K_DOWN: 40, pygame.K_PAGEUP: -400, pygame.K_PAGEDOWN: 400}
# shshd-runtime: how far (points) a press on a scrolling page moves before it scrolls the page instead of pressing what
# it began on (a row, a link).
DRAG_SLOP = 8


def row_command(kind, key):
    """The command an Options row of `kind` sends (a slider's: its first two parts; the track's Rect follows)."""
    if kind == 'slider':
        return 'pause_slider', key
    if kind == 'pick':
        return ('pause_cycle',) + tuple(key)
    if kind == 'choice':
        return 'pause_open', 'choice:' + key
    if kind == 'folder':
        return 'pause_cycle', key
    return {'switch': 'pause_toggle', 'cycle': 'pause_cycle', 'page': 'pause_open'}.get(kind, 'pause_action'), key


def drag_scroll(state, drag, y):
    """A press on a scrolling page (`HdPauseMenu.scroll_area`) followed to frame point `y`: `drag` is ('scroll', the scroll
    it began at, its y, moved). Returns the drag as it now stands, moved once past DRAG_SLOP, the page scrolled with it."""
    _kind, start, origin, moved = drag[:4]
    if not moved and abs(y - origin) < DRAG_SLOP:
        return drag
    state.scroll = min(state.max_scroll, max(0., start - (y - origin)))
    return ('scroll', start, origin, True) + tuple(drag[4:])


def place_controls(renderer, centre, scale, *, space='window', alpha=1.0):
    """Hand the host this frame's controls (graphics.native_controls), the card being drawn `scale` times its size
    about `centre` (where the frame's centre lands): in the window's pixels, or with `space='frame'` in the frame's
    points (the HD menus' canvas, which the host maps to the window). `scale` is that space's units per point."""
    if pygame.native_controls is None:
        return
    cx, cy = centre
    for control in renderer.placed_controls():
        placed = dict(control, space=space, alpha=alpha, scale=scale, middle=cy + (control['middle'] - FRAME[1] / 2) * scale)
        for edge in ('left', 'right'):
            if edge in control:
                placed[edge] = cx + (control[edge] - FRAME[0] / 2) * scale
        pygame.native_controls.append(placed)
DATA_TITLES = {screen: title for screen, title, _ in DATA_PAGES}


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

    _available = None

    def available(self):
        # Asked every frame while paused; the bundle and fonts stay as they are for the episode (a font lookup took
        # ~1.7 ms a frame on a phone).
        if self._available is None:
            try:
                self._available = bool(all(self.raw(i) is not None for i in (15, 32, 155))
                                       and pygame.font.match_font('arial', bold=True))
            except (AttributeError, KeyError):
                self._available = False
        return self._available

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

    def show_text(self, screen, title, body, parent):
        """Open a text page the host wrote (Data Management's Library Info): `title` over `body`, its back step to
        `parent`."""
        self.text_pages = dict(self.text_pages, **{screen: (title, body, parent)})      # (the class's stays empty)
        self.open(screen)

    def show_rows(self, screen, title, rows, parent, text=None):
        """Open a page of rows the host wrote (Restore Progress's backups, Sync's pages): `rows` are (key, label), each
        a ('pause_action', key), or (key, label, kind) for another kind ('switch': its value is `settings[key]`); its
        back step to `parent`. `text`: a few lines over the rows (the legal page's, from its window's message)."""
        self.row_pages = dict(self.row_pages, **{screen: (title, tuple(rows), parent)})
        self.row_texts = dict(self.row_texts, **{screen: text})
        self.open(screen)

    row_texts = {}                  # screen -> the text over a host row page's rows, or None (show_rows)

    # The game's own menu window's header, as desktop_hd_menu.layout lays it out: its title at 56 points 58 down, or at 44
    # points from 55 down when it takes two lines (TITLE_WIDTH 564), the lines 43.5 apart; its message at 28 points, 41 in,
    # its lines 26.6 apart, the first 78 under the last title line; the header ending 24.4 under the last message line.
    WINDOW_TITLE = (56, 58), (44, 55), 43.5, PANEL_W - 40
    WINDOW_MESSAGE = 28, 41, 26.6, 522, 78, 24.4

    def window_header(self, title, text):
        """(header height, title lines, their points, the first's centre, message lines, the first's centre) of a page
        whose header is the game's window's (the legal page's)."""
        (big, first_big), (small, first_small), pitch, width = self.WINDOW_TITLE
        points, first = big, first_big
        lines = self.wrapped(title, points, width)
        if len(lines) > 1:
            points, first = small, first_small
            lines = self.wrapped(title, points, width)
        size, _left, line_pitch, message_width, gap, below = self.WINDOW_MESSAGE
        message = self.wrapped(text, size, message_width)
        first_message = first + pitch * (len(lines) - 1) + gap
        return first_message + line_pitch * (len(message) - 1) + below, lines, points, first, message, first_message

    def draw_window_header(self, layer, top, head):
        _header, lines, points, first, message, first_message = head
        S, pitch = self.scale, self.WINDOW_TITLE[2]
        size, left, line_pitch = self.WINDOW_MESSAGE[:3]
        for index, line in enumerate(lines):
            surface = self.font(points).render(line, True, self.TITLE_COLOR)
            layer.blit(surface, surface.get_rect(center=(round(FRAME[0] / 2 * S), round((top + first + index * pitch) * S))))
        for index, line in enumerate(message):
            surface = self.font(size).render(line, True, self.TEXT_COLOR)
            layer.blit(surface, surface.get_rect(
                midleft=(round((PANEL_X + left) * S), round((top + first_message + index * line_pitch) * S))))

    def wrapped(self, text, points, width):
        """`text`'s lines at `points`, broken at spaces to `width` points (paragraphs kept)."""
        font, lines = self.font(points), []
        for paragraph in text.split('\n'):
            current = ''
            for word in paragraph.split(' '):
                trial = f'{current} {word}' if current else word
                if current and font.size(trial)[0] / self.scale > width:
                    lines.append(current)
                    current = word
                else:
                    current = trial
            lines.append(current)
        return lines

    def text_lines(self, page):
        if page in self.text_pages:
            return self.text_pages[page][:2]
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
    text_pages = {}                 # screen -> (title, body, parent) of the host's own text pages (show_text)
    row_pages = {}                  # screen -> (title, rows, parent) of the host's own row pages (show_rows)
    slide = None
    shown = None
    drawn = None
    switches = None                 # key -> (from, to, elapsed ms): each drawn switch's knob, 0 off .. 1 on

    def reset(self):
        self.state = PauseState()
        self.slide = self.shown = self.drawn = self.switches = None

    def open(self, screen):
        """A row's page, pushed in from the right."""
        self.state.screen, self.state.scroll = screen, 0.
        self.start_slide(1)

    def back(self):
        """One step out: returns True once the pause panel itself was showing."""
        state = self.state
        if state.screen == 'pause':
            return True
        leaving = state.screen
        host = self.text_pages.get(state.screen) or self.row_pages.get(state.screen)
        state.screen = (('options:per_game' if self.main_menu and state.screen[7:] in PER_GAME_CHOICES
                         else CHOICE_PARENTS[state.screen[7:]]) if state.screen.startswith('choice:')
                        else PAGE_PARENTS[state.screen] if state.screen in PAGE_PARENTS
                        else 'help' if state.screen in PAGES else host[2]
                        if host is not None else 'options:data' if state.screen in DATA_TITLES
                        else 'options' if state.screen.startswith('options:') else 'pause')
        if self.main_menu and state.screen == 'pause':
            return True
        if self.shown is not None and self.drawn is not None:
            screen, state.screen = state.screen, leaving
            pressed, self.pressed = self.pressed, ('pause_back',)
            self.shown = self.screen_layout(*self.drawn[0], **self.drawn[1])[0]
            state.screen, self.pressed = screen, pressed
        state.scroll, state.drag = 0., None
        self.start_slide(-1)
        return False

    def start_slide(self, direction):
        self.slide = (direction, self.shown, 0.) if self.shown is not None else None
        self.slid_controls = self.shown_controls     # the page sliding out takes its host controls along
        self.switches = None        # a page's switches first show at rest

    # A page's host controls (graphics.native_controls), in frame points: {'kind': 'switch', 'key', 'right', 'middle',
    # 'on'} or {'kind': 'slider', 'key', 'left', 'right', 'middle', 'value'}.
    screen_controls = shown_controls = slid_controls = ()

    def placed_controls(self):
        """Where the last laid-out screen's host controls are, sliding with their pages (`layout`) as UIKit's
        subviews would."""
        if self.slide is None:
            return list(self.shown_controls)
        direction, _, elapsed = self.slide
        shift = ease_in_out(elapsed / SLIDE_MS) * FRAME[0]

        def moved(control, by):
            return dict(control, **{edge: control[edge] + by for edge in ('left', 'right') if edge in control})
        return ([moved(control, -direction * shift) for control in self.slid_controls]
                + [moved(control, direction * (FRAME[0] - shift)) for control in self.shown_controls])

    def advance(self, ms):
        if self.slide is not None:
            direction, previous, elapsed = self.slide
            self.slide = (direction, previous, elapsed + ms) if elapsed + ms < SLIDE_MS else None
        if self.switches:
            self.switches = {key: (start, end, min(SWITCH_MS, elapsed + ms))
                             for key, (start, end, elapsed) in self.switches.items()}

    def animating(self):
        """Whether a page is sliding or a switch's knob is moving."""
        return self.slide is not None or any(elapsed < SWITCH_MS for _, _, elapsed in (self.switches or {}).values())

    def switch_position(self, key, on):
        """Where switch `key`'s knob is drawn (0 off .. 1 on). A value unlike the last one drawn starts it moving, from
        wherever it is."""
        if self.switches is None:
            self.switches = {}
        target = 1. if on else 0.
        start, end, elapsed = self.switches.get(key, (target, target, SWITCH_MS))
        position = start + (end - start) * ease_in_out(elapsed / SWITCH_MS)
        self.switches[key] = (position, target, 0.) if end != target else (start, end, elapsed)
        return position

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
        lit = lit or self.pressed == ('pause_back',)        # held or just clicked, the blue turns darker
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
        """A pill whose color runs down through `stops` [(t, (r, g, b))], at the layer's density (shared: draw it,
        copy it to change it)."""
        S = self.scale
        return self._pill(round(box[2] * S), round(box[3] * S), tuple(stops))

    # Kept, as the pill's mask is a blend the iOS host draws in Python (the Options page's switches, every frame).
    @lru_cache(maxsize=32)
    def _pill(self, width, height, stops):
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
        label and the knob on the left. `on` may be a knob position between them (`switch_position`): the track
        moves with the knob, the blue side and its label to its left, the white side and its label to its right."""
        width, height, knob = 79, 27, 27
        S = self.scale
        left, top = right - width, middle - height / 2
        rim = self.gradient_pill((left, top, width, height), [(0, (110, 110, 112)), (1, (150, 150, 152))])
        layer.blit(rim, (round(left * S), round(top * S)))
        layer.blit(self.switch_track(on), (round((left + .5) * S), round((top + .5) * S)))
        kx = left + float(on) * (width - knob)
        shade = self.gradient_pill((kx, top, knob, knob), [(0, (120, 120, 122)), (1, (140, 140, 142))])
        layer.blit(shade, (round(kx * S), round(top * S)))
        face = self.gradient_pill((kx + .6, top + .6, knob - 1.2, knob - 1.2),
                                  [(0, (205, 205, 205)), (.5, (232, 232, 232)), (1, (252, 252, 252))])
        layer.blit(face, (round((kx + .6) * S), round((top + .6) * S)))

    @lru_cache(maxsize=4)
    def switch_track(self, on):
        """The switch's track (inset half a point in its rim) with the knob at `on`, cut to its pill; it does not
        depend on where the switch sits, so a still switch is drawn once (its mask is a Python blend on iOS)."""
        width, height, knob = 79, 27, 27
        S = self.scale
        box = (.5, .5, width - 1, height - 1)
        track = self.gradient_pill(box, [(0, (15, 98, 163)), (.08, (0, 123, 227)), (.5, (2, 126, 232)),
                                         (.55, (30, 143, 238)), (1, (107, 178, 243))]).copy()
        off = self.gradient_pill(box, [(0, (170, 170, 172)), (.12, (215, 215, 217)), (.55, (240, 240, 242)),
                                       (1, (252, 252, 253))])
        kx = float(on) * (width - knob)
        split = round((kx + knob / 2 - box[0]) * S)
        track.fill((0, 0, 0, 0), (split, 0, track.get_width() - split, track.get_height()))
        track.blit(off, (split, 0), (split, 0, off.get_width() - split, off.get_height()))
        # The labels ride on the track, cut off by the pill: ON 27 points left of the knob, OFF 52 points right.
        control = self.control_font(15)
        y = height / 2 - self.cap_offset(15, control) - .5
        for label, x, color in (('ON', kx - 27, (255, 255, 255)), ('OFF', kx + 52, (128, 128, 128))):
            # (HdPauseMenu's own text: the label is the control's, not the page's. The Claire Hart skin's `text` turns
            # grey text off-white for its teal pages, and the OFF label vanished on the white track; g54, 2026-11-22.)
            HdPauseMenu.text(self, track, label, x - box[0], y, 15, color, center=True, font=control)
        mask = pygame.Surface(track.get_size(), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=track.get_height() // 2)
        track.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        return track

    def slider(self, layer, top, value, key=None, *, place=True):
        """A UISlider row's control line (track between the two speaker icons). Where the host shows its own (iOS:
        a UISlider, graphics.native_controls), the icons are drawn and the track is placed for it instead (`place`
        False: not placed, a row scrolled partly out)."""
        middle = top + 86
        small, large = self.art(155, 53), self.art(155, 54)
        layer.blit(small, (round(108 * S), round(middle * S - small.get_height() / 2)))
        layer.blit(large, (round(620 * S), round(middle * S - large.get_height() / 2)))
        left, right = 143, 603
        if pygame.native_controls is not None and key is not None:
            if place:
                self.screen_controls.append(dict(kind='slider', key=key, left=left, right=right, middle=middle,
                                                 value=float(value)))
            return pygame.Rect(left - 10, middle - 22, right - left + 20, 44)
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

    def row(self, layer, top, label, *, height=ROW, color=None, background=None, lit=False, badge=None, tint=None,
            value=None):
        """`badge`: (text, colour) of a tag before the label (SWITCH_BADGES), in the episode list's style. `tint`: (word,
        colour) of a word in the label to colour (LABEL_TINTS). `value`: a line under the label in smaller letters (an
        option's current choice, CHOICE_NAMES)."""
        color = color or self.LABEL_COLOR
        self.rows_body(layer, top, height, background, lit=lit)
        x = PANEL_X + 31
        if badge is not None:
            x += self.badge(layer, x, top + ROW / 2, *badge) + BADGE_GAP
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
        centre = top + ROW / 2
        if value is not None:
            # The label and its value line, centred together as the episode lists' title and subtitle are.
            label_height, value_height = font.get_height() / S, self.font(VALUE_PX).get_height() / S
            label_top = top + (ROW - (label_height + VALUE_GAP + value_height)) / 2
            centre = label_top + self.cap_offset(ROW_PX)
            shown = self.font(VALUE_PX).render(value, True, color)
            shown.set_alpha(VALUE_ALPHA)
            layer.blit(shown, (round(x * S), round((label_top + label_height + VALUE_GAP) * S)))
        for index, line in enumerate(lines):
            middle = centre + (index - (len(lines) - 1) / 2) * pitch
            y = middle - self.cap_offset(ROW_PX)
            self.text(layer, line, x, y, ROW_PX, color)
            if tint is not None and tint[0] in line:
                self.text(layer, tint[0], x + font.size(line.partition(tint[0])[0])[0] / self.scale, y, ROW_PX, tint[1])

    def badge(self, layer, x, middle, text, color):
        """A game's tag at (x, vertical middle), as the episode list draws it (desktop_episode_list_hd
        draw_standard_mark): a light plate in the colour, its border and its text. Returns its width."""
        S = self.scale
        label = self.font(BADGE_PX).render(text, True, color)
        width, height = label.get_width() / S + 2 * BADGE_PAD, BADGE_HEIGHT
        plate = pygame.Surface((round(width * S), round(height * S)), pygame.SRCALPHA)
        pygame.draw.rect(plate, (*color, 30), plate.get_rect(), border_radius=round(8 * S))
        pygame.draw.rect(plate, (*color, 200), plate.get_rect(), max(1, round(2 * S)), border_radius=round(8 * S))
        plate.blit(label, label.get_rect(center=plate.get_rect().center))
        layer.blit(plate, (round(x * S), round((middle - height / 2) * S)))
        return width

    # -- screens ---------------------------------------------------------
    def layout(self, settings, host_rows=(), *, message=''):
        """(layer, buttons): buttons are (Rect in points, command). Commands:
        ('pause_open', screen), ('pause_back',), ('resume',), ('main_menu',), ('save',), ('load',),
        ('pause_toggle', 'vibration'|'device_vibration'|'music'|'sound'|'side_panels'|'choice_hints'|'skip_minigames'|'skip_ad_intros'|'skip_upsell_intros'|'hd_backdrop'|'hires_portraits'|'arena_minigames'|'arena_skin'),
        ('pause_slider', 'music'|'sound', Rect), ('pause_link', url). Options is a list of categories
        ('pause_open', 'options:<category>'), each a page of its switches and sliders. While a page slides in
        (`open` / `back`) the layer holds both cards and there are no buttons."""
        layer, buttons = self.screen_layout(settings, host_rows, message=message)
        self.shown, self.drawn = layer, ((settings, host_rows), {'message': message})
        self.shown_controls = self.screen_controls
        if self.slide is None:
            return layer, buttons
        direction, previous, elapsed = self.slide
        shift = ease_in_out(elapsed / SLIDE_MS) * layer.get_width()
        both = pygame.Surface(layer.get_size(), pygame.SRCALPHA).convert_alpha()
        both.blit(previous, (round(-direction * shift), 0))
        both.blit(layer, (round(direction * (layer.get_width() - shift)), 0))
        return both, []

    # shshd-runtime (General's Aspect Ratio): the frame's height in points the pages are laid out in. HD's 1024 for the
    # pause menu over a story (its card is centred in a taller frame: Desktop.card_frame); the app's own Options
    # (desktop_app_hd) set the menu frame's (Application.menu_frame), so a page is centred in it and a text page's card
    # runs taller, showing more lines.
    frame_height = FRAME[1]

    def screen_layout(self, settings, host_rows=(), *, message=''):
        """The current screen alone, at rest: `layout`'s (layer, buttons)."""
        layer = pygame.Surface((FRAME[0] * S, round(self.frame_height * S)), pygame.SRCALPHA).convert_alpha()
        strings, state, buttons = self.strings(), self.state, []
        self.screen_controls = []
        # (a page that scrolls sets these again; one that doesn't keeps no scroll a text page or wheel left)
        self.scroll_area, self.scroll_rows, state.max_scroll = None, False, 0.
        bottom_rule = None
        focus = state.focus
        if state.screen == 'pause':
            entries = [(strings[20], ('resume',)), (strings[10], ('pause_open', 'options')),
                       (strings[120], ('pause_open', 'help'))]
            entries.append((strings[9], ('main_menu',)))
            if settings.get('journal_row'):
                entries.insert(1, (JOURNAL_LABEL, ('journal',)))
            if settings.get('undo_row'):
                entries.insert(1, (UNDO_LABEL, ('undo',)))
            if settings.get('skip_ahead_row'):
                entries.insert(1, (SKIP_AHEAD_LABEL, ('skip_ahead',)))
            entries += list(host_rows)
            height = HEADER + ROW * len(entries) + FOOT
            top = (self.frame_height - height) / 2
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
            top = (self.frame_height - height) / 2
            body = self.panel(layer, top, top + height, strings[10])
            for i, (category, label) in enumerate(categories):
                y = body + i * ROW
                command = ('pause_open', 'options:' + category)
                self.row(layer, y, label, background=self.row_color(i), lit=focus == command)
                buttons.append((pygame.Rect(PANEL_X, y, PANEL_W, ROW), command))
            bottom_rule = top + height - FOOT
            buttons.append((self.back_button(layer, top + height, lit=focus == ('pause_back',)), ('pause_back',)))
        elif (state.screen.startswith(('options:', 'choice:')) or state.screen in DATA_TITLES
              or state.screen in self.row_pages):
            # Sound: the app's own Music / Sound switches and sliders. General: in a story, the side panels (a native
            # feature: the device shows them on rotation, so it has no switch or string of its own), then this
            # player's switches (exp-runtime's Options -> Cheats; no native strings, so the labels are this project's).
            category = (state.screen if state.screen in DATA_TITLES or state.screen in self.row_pages
                        or state.screen.startswith('choice:') else state.screen.split(':', 1)[1])
            rows = self.option_rows(category, settings, strings)
            heights = [SLIDER_ROW if kind == 'slider' else ROW for kind, _, _ in rows]
            # A host page's text over its rows (the legal page's, from its window's message). Plainly, the header is the
            # window's own (desktop_hd_menu.layout: a two-line title set smaller, the message in the header under it);
            # in the Claire Hart skin, whose panel keeps the title on its tab, the text sits on the panel over the rows
            # at their labels' inset (owner, 2026-11-22: the first version's big title and band read wrong in both).
            text = self.row_texts.get(category) if category in self.row_pages else None
            skinned = getattr(self, 'ui', None) is not None
            header, intro, intro_lines, window_head = HEADER, 0, [], None
            if text and skinned:
                intro_lines = self.wrapped(text, TEXT_PX, PANEL_W - 2 * BORDER - 2 * INTRO_LEFT)
                intro = len(intro_lines) * TEXT_PITCH + 2 * INTRO_PAD
            elif text:
                window_head = self.window_header(self.row_pages[category][0], text)
                header = window_head[0]
            height = header + intro + sum(heights) + FOOT
            top, bottom = (self.frame_height - height) / 2, None
            title = (DATA_TITLES.get(category) or (self.row_pages[category][0] if category in self.row_pages else None)
                     or CHOICE_LABELS.get(category[7:] if category.startswith('choice:') else None)
                     or PAGE_TITLES.get(category)
                     or dict(OPTION_CATEGORIES).get(category, strings[10]))
            low, high = self.page_bounds()
            # shshd-runtime: a page too tall to be centred whole (General's ten rows at 3:4, its back button cut off;
            # owner, 2026-11-22) fills a text page's bounds, and its rows scroll as a text page's lines do.
            scrolling = height > high - low
            top, bottom = (low, high) if scrolling else (top, top + height)
            if window_head is not None:
                body = self.panel(layer, top, bottom, '', header=header)
                self.draw_window_header(layer, top, window_head)
            else:
                body = self.panel(layer, top, bottom, title)
            if intro_lines:
                for index, line in enumerate(intro_lines):
                    self.text(layer, line, PANEL_X + INTRO_LEFT, body + INTRO_PAD + index * TEXT_PITCH, TEXT_PX,
                              self.TEXT_COLOR)
                body += intro
            area = pygame.Rect(PANEL_X + BORDER, body, PANEL_W - 2 * BORDER, bottom - FOOT - body)
            if scrolling:
                self.scroll_area, self.scroll_rows = area, True
                state.max_scroll = max(0., sum(heights) - area.height)
                offset = 0.
                for (kind, _label, key), row_height in zip(rows, heights):
                    command = row_command(kind, key)
                    if focus is not None and (focus[:2] if kind == 'slider' else focus) == command:
                        # The row the arrow keys reached comes into view.
                        state.scroll = min(max(state.scroll, offset + row_height - area.height), offset)
                    offset += row_height
                state.scroll = max(0., min(state.max_scroll, state.scroll))
                layer.set_clip(pygame.Rect(area.x * S, area.y * S, area.width * S, area.height * S))
            y = body - state.scroll

            def add(rect, command):
                """A row's button, cut to what shows of it: a row scrolled out keeps an empty one, which no pointer
                hits but the arrow keys still reach (the next layout scrolls it into view)."""
                rect = pygame.Rect(rect)
                buttons.append((rect.clip(area) if scrolling else rect, command))

            def whole(row_top, row_height):
                """Whether a row shows whole: only then does the host place its own control over it (a UISwitch or
                UISlider is not cut by the card)."""
                return area.top - .5 <= row_top and row_top + row_height <= area.bottom + .5

            for index, (kind, label, key) in enumerate(rows):
                if kind == 'slider':
                    self.rows_body(layer, y, SLIDER_ROW, self.row_color(index),
                                   lit=focus is not None and focus[:2] == ('pause_slider', key))
                    self.text(layer, label, PANEL_X + 31, y + 39 - self.cap_offset(ROW_PX), ROW_PX, self.LABEL_COLOR)
                    track = self.slider(layer, y, settings[key + '_volume'], key=key,
                                        place=not scrolling or whole(y, SLIDER_ROW))
                    add(track, ('pause_slider', key, track))
                    y += SLIDER_ROW
                    continue
                command = row_command(kind, key)
                if kind == 'pick':
                    # A choice page's row: `key` is (option, value); the option's current value is ticked.
                    option, _value = key
                    self.row(layer, y, label, background=self.row_color(index), lit=focus == command)
                    if label == settings.get(option):
                        self.check(layer, PANEL_X + PANEL_W - CONTROL_RIGHT - 6, y + ROW / 2)
                    add((PANEL_X, y, PANEL_W, ROW), command)
                    y += ROW
                    continue
                if kind == 'folder':
                    # Data Management's Backups / Exports Folder: the folder in use under the label; the row opens the
                    # host's folder browser (the command its value button sent).
                    self.row(layer, y, label, background=self.row_color(index), lit=focus == command, value=settings[key])
                    self.chevron(layer, PANEL_X + PANEL_W - CONTROL_RIGHT - 8, y + ROW / 2)
                    add((PANEL_X, y, PANEL_W, ROW), command)
                    y += ROW
                    continue
                if kind == 'choice':
                    self.row(layer, y, label, background=self.row_color(index), lit=focus == command,
                             badge=switch_badge(key), tint=legacy_tag(LABEL_TINTS.get(key)), value=settings[key])
                    self.chevron(layer, PANEL_X + PANEL_W - CONTROL_RIGHT - 8, y + ROW / 2)
                    add((PANEL_X, y, PANEL_W, ROW), command)
                    y += ROW
                    continue
                self.row(layer, y, label, background=self.row_color(index), lit=focus == command,
                         badge=switch_badge(key), tint=legacy_tag(LABEL_TINTS.get(key)))
                if kind == 'switch' and pygame.native_controls is not None:
                    # The host's own control (the iOS host's UISwitch), placed over the row (place_controls).
                    if not scrolling or whole(y, ROW):
                        self.screen_controls.append(dict(kind='switch', key=key, right=PANEL_X + PANEL_W - CONTROL_RIGHT,
                                                         middle=y + ROW / 2, on=bool(settings.get(key, False))))
                    add((PANEL_X + PANEL_W - 250, y, 250, ROW), ('pause_toggle', key))
                elif kind == 'switch':
                    self.switch(layer, PANEL_X + PANEL_W - CONTROL_RIGHT, y + ROW / 2,
                                self.switch_position(key, settings.get(key, False)))
                    add((PANEL_X + PANEL_W - 250, y, 250, ROW), ('pause_toggle', key))
                elif kind == 'cycle':
                    # As wide as its value needs (Start In's "Surviving High School"), at least CYCLE_SIZE.
                    width = max(CYCLE_SIZE[0], self.font(CYCLE_POINTS).size(settings[key])[0] / self.scale + 28)
                    box = pygame.Rect(PANEL_X + PANEL_W - CONTROL_RIGHT - width,
                                      y + (ROW - CYCLE_SIZE[1]) / 2, width, CYCLE_SIZE[1])
                    self.cycle_button(layer, box, settings[key], pressed=self.pressed == ('pause_cycle', key))
                    add(box, ('pause_cycle', key))
                else:
                    add((PANEL_X, y, PANEL_W, ROW), command)     # an action or a page
                y += ROW
            if scrolling:
                layer.set_clip(None)
                self.rect(layer, self.SEPARATOR_COLOR, (area.x, area.y, area.width, 1))
                buttons.insert(0, (area, ('pause_scroll',)))   # (under the rows: a press scrolls once it moves)
            bottom_rule = bottom - FOOT
            buttons.append((self.back_button(layer, bottom, lit=focus == ('pause_back',)), ('pause_back',)))
        elif state.screen == 'help':
            order = MAIN_HELP_ORDER if self.main_menu else HELP_ORDER
            height = HEADER + ROW * len(order) + FOOT
            top = (self.frame_height - height) / 2
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
        if self.scroll_area is None:
            state.scroll = 0.
        if bottom_rule is not None:
            self.rect(layer, self.SEPARATOR_COLOR, (PANEL_X + BORDER, bottom_rule, PANEL_W - 2 * BORDER, 1))
        if message:
            self.text(layer, message, 384, self.frame_height - 90, 22, (255, 255, 255), center=True)
        self.buttons = buttons
        return layer, buttons

    pressed = None                  # the command under the pointer, for buttons drawn pressed (set by the host)
    buttons = ()                    # the last layout's buttons, for `key`
    # shshd-runtime: the last layout's scrolling area (points), or None: a text page's body, or the rows of a page too
    # tall for its frame (General's ten rows at 3:4, 2026-11-22). A press in it scrolls once it moves (`drag_scroll`).
    scroll_area = None
    scroll_rows = False             # the scrolling page is one of rows: the arrow keys move between them, not the page

    def key(self, key):
        state = self.state
        commands = [command for _, command in self.buttons]
        if ('pause_scroll',) in commands and key in PAGE_KEYS and (
                not self.scroll_rows or key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN)):
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
        elif key in KEYS_ACTIVATE and focus is None and targets:
            state.focus = targets[0]        # nothing highlighted: Enter (a controller's confirm) shows where it is
        return None

    SWITCH_LABELS = SWITCH_LABELS        # a game's own wording (desktop_cod_pause.CodPauseMenu)

    def option_rows(self, category, settings, strings):
        """[(kind, label, key)] of an Options category: 'switch', 'slider', 'cycle' or 'action' rows, those whose
        setting the host offers."""
        if category == 'sound':
            # This player's buzz in place of the iPhone's vibration (PR #10): last, under its own name. A device's own
            # vibrator is General's Vibration (DEVICE_VIBRATION_LABEL), a separate switch.
            vibration = [('switch', VIBRATION_SOUND_LABEL, 'vibration')] if 'vibration' in settings else []
            prompt = [('switch', SKIP_SOUND_PROMPT_LABEL, 'skip_sound_prompt')] if 'skip_sound_prompt' in settings else []
            return [('switch', strings[12], 'music'), ('slider', strings[13], 'music'),
                    ('switch', strings[14], 'sound'), ('slider', strings[15], 'sound')] + vibration + prompt
        if category == 'general':
            # General's Vibration is the Controller page's when only a controller vibrates (settings['controller_vibration'])
            rows = [('switch', self.SWITCH_LABELS[key], key) for key in GENERAL_KEYS if key in settings
                    and not (key == 'device_vibration' and settings.get('controller_vibration'))]
            if 'text_animation' in settings:
                rows.append(('choice', TEXT_ANIMATION_LABEL, 'text_animation'))
            if 'aspect_ratio' in settings:
                rows.append(('choice', ASPECT_LABEL, 'aspect_ratio'))
            if 'preferred_language' in settings:
                rows.append(('choice', PREFERRED_LANGUAGE_LABEL, 'preferred_language'))
            if 'start_in' in settings:
                rows.append(('choice', START_IN_LABEL, 'start_in'))
            return rows
        if category == 'controller':
            if 'controller_confirm' not in settings:
                return []
            rows = [('choice', CONFIRM_BUTTON_LABEL, 'controller_confirm')]
            if 'grid_controls' in settings:
                rows.append(('choice', GRID_CONTROLS_LABEL, 'grid_controls'))
            if 'device_vibration' in settings and settings.get('controller_vibration'):
                rows.append(('switch', self.SWITCH_LABELS['device_vibration'], 'device_vibration'))
            return rows
        if category == 'extras':
            rows = [('switch', self.SWITCH_LABELS[key], key) for key in EXTRAS_KEYS if key in settings]
            if 'dsi_backgrounds' in settings:
                rows.append(('choice', DSI_BACKGROUNDS_LABEL, 'dsi_backgrounds'))
            if 'unlock_warp' in settings:
                rows.append(('action', UNLOCK_WARP_LABEL, 'unlock_warp'))
            return rows
        if category == 'addons' and self.main_menu:
            rows = [('switch', self.SWITCH_LABELS['arena_minigames'], 'arena_minigames')] if 'arena_minigames' in settings else []
            if self.option_rows('per_game', settings, strings):
                rows.append(('page', PER_GAME_LABEL, 'options:per_game'))
            if 'title_music' in settings:
                rows.append(('choice', TITLE_MUSIC_LABEL, 'title_music'))
            if 'title_look' in settings:
                rows.append(('choice', TITLE_LOOK_LABEL, 'title_look'))
            return rows
        if category == 'addons':
            return [('switch', self.SWITCH_LABELS[key], key) for key in ADDON_KEYS if key in settings] + self.addon_choices(settings)
        if category == 'per_game':
            return [('switch', self.SWITCH_LABELS[key], key) for key in ADDON_KEYS
                    if key in settings and key != 'arena_minigames'] + self.addon_choices(settings)
        if category == 'data':
            first = [('action', label, key) for key, label in DATA_FIRST if key in settings]
            pages = [('page', title, screen) for screen, title, rows in DATA_PAGES
                     if any(key in settings for key, _ in rows)]
            return first + pages + [('action', label, key) for key, label in DATA_LAST if key in settings]
        if category in DATA_TITLES:
            # A row whose setting is a name (Backups / Exports Folder: the folder's) shows it under its label, as General's
            # choices show theirs (owner, 2026-11-19; it was on a value button).
            rows = next(rows for screen, _, rows in DATA_PAGES if screen == category)
            return [('folder' if isinstance(settings[key], str) else 'action',
                     label, key) for key, label in rows if key in settings]
        if category in self.row_pages:
            return [(kind[0] if kind else 'action', label, key) for key, label, *kind in self.row_pages[category][1]]
        if category.startswith('choice:'):
            option = category[7:]
            names = settings.get(option + '_names') or CHOICE_NAMES.get(option, {})
            return [('pick', name, (option, value)) for value, name in names.items()] if option in settings else []
        return []

    @staticmethod
    def addon_choices(settings):
        """The add-on options that are one of a few values, after the switches (Claire Hart Dialogue)."""
        return [('choice', CHOICE_LABELS[key], key) for key in PER_GAME_CHOICES if key in settings]

    def check(self, layer, right, middle):
        """The tick on a choice page's current row, ending `right`, centred on `middle`."""
        S = self.scale
        points = [(right - 26, middle), (right - 16, middle + 10), (right, middle - 12)]
        pygame.draw.lines(layer, self.TITLE_COLOR, False, [(round(x * S), round(y * S)) for x, y in points], round(5 * S))

    def chevron(self, layer, right, middle):
        """The `>` on a row that opens a page of choices."""
        S = self.scale
        points = [(right - 10, middle - 12), (right, middle), (right - 10, middle + 12)]
        pygame.draw.lines(layer, self.LABEL_COLOR, False, [(round(x * S), round(y * S)) for x, y in points], round(4 * S))

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

    # Points of the frame's top and bottom that a phone's status bar and navigation or gesture bar cover (the host's
    # menu_top_pad / menu_bottom_pad): a text page, which otherwise runs the frame's height, keeps BAR_GAP clear of them
    # (owner, g54, 2026-11-19: About and Help's pages came close to both).
    top_pad = bottom_pad = 0
    BAR_GAP = 12

    def page_bounds(self):
        """(top, bottom) a card may fill: a text page's, and a page of rows too tall to be centred whole."""
        top, bottom = TALL[0], TALL[1] + self.frame_height - FRAME[1]
        if self.top_pad:
            top = max(top, self.top_pad + self.BAR_GAP)
        if self.bottom_pad:
            bottom = min(bottom, self.frame_height - self.bottom_pad - self.BAR_GAP)
        return top, bottom

    def text_page(self, layer, buttons):
        state = self.state
        title, body = self.text_lines(state.screen)
        top, bottom = self.page_bounds()
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
        self.scroll_area = area
        for rect, url in links:
            buttons.append((rect.clip(area), ('pause_link', url)))

    # -- dimming ----------------------------------------------------------
    @staticmethod
    def sepia(surface):
        """The frame dimmed and tinted the way the pause overlay does."""
        native = getattr(pygame.transform, 'color_matrix', None)
        if native is not None:
            return native(surface, SEPIA)       # the iOS host's color_matrix: no Python pass over the frame
        image = Image.frombytes('RGB', surface.get_size(), pygame.image.tobytes(surface, 'RGB'))
        image = image.convert('RGB', SEPIA)
        return pygame.image.frombytes(image.tobytes(), image.size, 'RGB')
