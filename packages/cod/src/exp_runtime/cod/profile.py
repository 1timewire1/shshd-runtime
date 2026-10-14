"""Cause of Death content and host-service profile (iOS 1.3.4 reference)."""
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
PROFILES = {'cod-ios-assets-v1': 'ipa'}
BUNDLE_PATTERN = r'com\.ea\.causeofdeath(?:\.[A-Za-z0-9-]+)*'
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
