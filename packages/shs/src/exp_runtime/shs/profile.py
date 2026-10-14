"""Surviving High School content and host-service profile."""
from .audio import music_cue as MUSIC_CUE
from .content import BUILTIN, extract_builtin, _inspect_apk as inspect_apk
from .services import dispatch as DISPATCH
from .audio import IOS_DOWNLOADED_MUSIC as DOWNLOADED_MUSIC
from .football import Football
from .word_grid import WordGrid

STATE_TYPES = {'word_grid': WordGrid | None, 'football': Football | None}

KEY = 'shs'
TITLE = 'Surviving High School'
SOURCES = 'SHS Android 1.0.9 APK or SHS IPA'
CATALOG_FILENAME = 'shs_options.sav'
# Legacy and Android envelopes: (current-entry offset, trailing flag count).
CATALOG_LAYOUTS = {version: ((32, version - 16), (36, version - 16)) for version in (16, 17, 18)}
PROFILES = {'shs-android-1.0.9': 'apk', 'shs-ios-assets-v1': 'ipa'}
BUNDLE_PATTERN = r'com\.ea\.shs(?:\.[A-Za-z0-9-]+)*'
NAME_FONT = ('PajamaHip', 505)
DIALOGUE_COLORS = {1: (41, 104, 221), 2: (180, 78, 78), 3: (108, 108, 108), -1: (223, 163, 52)}
NAME_COLORS = {'PajamaHip24': (41, 104, 221), 'PajamaHip26': (41, 104, 221),
               'PajamaHip266': (180, 78, 78), 'PajamaHipG26': (137, 137, 137),
               'PajamaHipY26': (223, 163, 52), 'PajamaHipS26': (254, 53, 0)}
MUSIC_RANGE = range(8201, 8233)
# SHS iOS doSoundManagerTransition (0003b44c), splashScreenFlewIn (0002adb0).
MENU_MUSIC = 8215
DEFAULT_EPISODE = (5, 9)
RELATIONSHIP_ASSETS = (3010, 3011, 3012)
RELATIONSHIP_FLASH = {3010: 3013, 3011: 3015, 3012: 3017}
RELATIONSHIP_LOSS = {3010: 3014, 3011: 3016, 3012: 3018}
CLICK_SOUND = 8010
# SHSEngine::buttonPressed pause branch (iOS 00051214).
PAUSE_SOUND = 8011
# Original quiz scripts dispatch these through service 79 for correct/wrong
# feedback (Football Star's shared classroom routine also covers finals).
# They are fixed SHS base-bank IDs, not episode counters or text heuristics.
CHOICE_FEEDBACK_SOUNDS = {8007: 1, 8003: -1}
