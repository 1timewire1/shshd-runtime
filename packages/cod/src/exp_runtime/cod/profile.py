"""Cause of Death asset layouts, normalized to the iOS 1.3.4 reference.

Free packages share a duplicate Volume One at 13 and English strings at 14.
The compact layout shifts later UI members by one; the reported multilingual
layout inserts four more string banks and shifts them by five. Bundle IDs do
not distinguish these layouts. See docs/COD.md for evidence and limits.
"""
from ..exp import ContentError
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
PAID_PROFILE = 'cod-ios-assets-v1'
FREE_PROFILE = 'cod-ios-free-assets-v1'
LOCALIZED_FREE_PROFILE = 'cod-ios-free-localized-assets-v1'
UI_SHIFTS = {PAID_PROFILE: 0, FREE_PROFILE: 1, LOCALIZED_FREE_PROFILE: 5}
PROFILES = dict.fromkeys(UI_SHIFTS, 'ipa')
# Reference UI members. Character/background/audio banks retain their IDs.
SHIFTED_UI = range(14, 298)

BUNDLE_PATTERN = r'com\.ea\.causeofdeath(?:free)?(?:\.[A-Za-z0-9-]+)*'
# Explicit compatibility exceptions for observed out-of-range script defaults.
# Native setReturnValue reads outside the mapping; it does not define a result.
# Preserve these sentinels instead of guessing heap contents. See docs/COD.md.
CHOICE_TIMEOUT_FALLBACKS = frozenset((-1, 1000))
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


def profile_for(read):
    """Select the one layout whose complete required asset bank validates.

    Import and reopen use payload validation rather than bundle suffixes.
    Keep the compact-free profile ID readable for existing libraries.
    """
    from .assets import validate_assets

    matches, failures = [], []
    for profile in PROFILES:
        try:
            validate_assets(lambda resource: read(base_resource(profile, resource)))
        except ContentError as error:
            failures.append(f'{profile}: {error}')
        else:
            matches.append(profile)
    if len(matches) > 1:
        raise ContentError('Ambiguous CoD asset layout: multiple resource banks validate')
    if not matches:
        raise ContentError('Unsupported CoD asset layout; ' + '; '.join(failures))
    return matches[0]


def base_resource(profile, resource):
    """The package member number holding reference resource ``resource``."""
    shift = UI_SHIFTS[profile]
    if shift and resource == 13:
        return 14  # English precedes any other language banks.
    if resource in SHIFTED_UI:
        return resource + shift
    return resource


def translate_members(profile, members):
    """Re-key a package's numeric members by reference resource ID."""
    if profile == PAID_PROFILE:
        return members
    aliases = {base_resource(profile, resource): resource for resource in (13, *SHIFTED_UI)}
    omitted = {13, *range(15, 19)} if profile == LOCALIZED_FREE_PROFILE else {13}
    translated = {}
    for number, member in members.items():
        if number not in omitted:
            translated[aliases.get(number, number)] = member
    return translated
