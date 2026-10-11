"""Cause of Death content and host-service profile (iOS 1.3.4 reference).

The free edition (com.ea.causeofdeathfree.*, inspected at 1.4.7) carries the
same script-visible banks (Volume One at 12, backgrounds, portraits, audio,
relationship art) but inserts a second copy of the Volume One EXP at 13, so
every host UI resource from the string bank onward sits one ID higher than in
the 1.3.4 paid build: strings 14, layouts 15, image pack 17, box skins
205/221/237/253, portrait mask 269, fonts 292-298. ``translate_members`` maps
that bank back onto the reference numbering so the rest of the engine is
unchanged; script-visible IDs are never translated.
"""
import re
from .audio import music_cue as MUSIC_CUE
from .content import BUILTIN, extract_builtin
from .services import dispatch as DISPATCH

STATE_TYPES = {}

KEY = 'cod'
TITLE = 'Cause of Death'
SOURCES = 'Cause of Death IPA'
CATALOG_FILENAME = 'cod_options.sav'
# Native loadOptions 00019098 / saveOptions 000195b4: five flag bytes and
# two s32 values precede the current entry; EOF follows the rename table.
CATALOG_LAYOUTS = {17: ((33, 0),)}
PROFILES = {'cod-ios-assets-v1': 'ipa', 'cod-ios-free-assets-v1': 'ipa'}
FREE_PROFILE = 'cod-ios-free-assets-v1'
FREE_BUNDLE = re.compile(r'com\.ea\.causeofdeathfree(?:\.[A-Za-z0-9-]+)*', re.IGNORECASE)
# Reference (1.3.4) host UI IDs that the free edition stores one slot higher.
SHIFTED_UI = range(13, 299)


def profile_for(identifier):
    return FREE_PROFILE if FREE_BUNDLE.fullmatch(identifier or '') else 'cod-ios-assets-v1'


def base_resource(profile, resource):
    """The package member number holding reference resource ``resource``."""
    if profile == FREE_PROFILE and resource in SHIFTED_UI:
        return resource + 1
    return resource


def translate_members(profile, members):
    """Re-key a package's numeric members by reference resource ID."""
    if profile != FREE_PROFILE:
        return members
    translated = {}
    for number, member in members.items():
        if number == 13:
            continue                      # duplicate Volume One EXP; 12 is canonical
        if number - 1 in SHIFTED_UI:
            translated[number - 1] = member
        else:
            translated[number] = member
    return translated
BUNDLE_PATTERN = r'com\.ea\.causeofdeath(?:free)?(?:\.[A-Za-z0-9-]+)*'
NAME_FONT = ('VerdanaBoldItalic', 291)
# SHSEngine::initFonts 000234da..000237ee; normal/gray/default dialogue
# uses black body text and dark-red names. Theme 2 retains its rose color.
DIALOGUE_COLORS = {1: (0, 0, 0), 2: (180, 78, 78), 3: (0, 0, 0), -1: (0, 0, 0)}
NAME_COLORS = {'PajamaHip24': (41, 104, 221), 'PajamaHip26': (139, 0, 0),
               'PajamaHip266': (180, 78, 78), 'PajamaHipG26': (139, 0, 0),
               'PajamaHipY26': (139, 0, 0), 'PajamaHipS26': (254, 53, 0)}
MUSIC_RANGE = range(8201, 8210)
# CoD doSoundManagerTransition (00022b04), splashScreenFlewIn (00014c0c).
MENU_MUSIC = 8209
DEFAULT_EPISODE = (101, 1)
RELATIONSHIP_ASSETS = (3000, 3001, 3002)
RELATIONSHIP_FLASH = {3000: 3003, 3001: 3005, 3002: 3007}
RELATIONSHIP_LOSS = {3000: 3004, 3001: 3006, 3002: 3008}
# SHSEngine::buttonPressed 000249d0 and SHSWidgetMenu::buttonPressed 0003fd60.
CLICK_SOUND = 8005
# SHSEngine::buttonPressed pause branch (00024d86).
PAUSE_SOUND = 8006
# SHS answer-feedback resource IDs do not establish semantics for CoD assets.
CHOICE_FEEDBACK_SOUNDS = {}
