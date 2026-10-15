"""Cause of Death content and host-service profile (iOS 1.3.4 reference)."""
from .audio import music_cue as MUSIC_CUE
from .content import BUILTIN, extract_builtin
from .services import dispatch as DISPATCH

STATE_TYPES = {}

KEY = 'cod'
TITLE = 'Cause of Death'
SOURCES = 'Cause of Death IPA'
CATALOG_FILENAME = 'cod_options.sav'
# This fork: 1.4.7's store listing (Documents/mtxprods), imported beside the episodes for the episode info card.
STORE_FILENAME = 'mtxprods'


def read_store_listing(data):
    """`mtxprods` bytes -> the kept listing's JSON bytes (products only; store.py)."""
    from .store import read_store, store_bytes
    return store_bytes(read_store(data))
# Native loadOptions 00019098 / saveOptions 000195b4: five flag bytes and
# two s32 values precede the current entry; EOF follows the rename table.
CATALOG_LAYOUTS = {17: ((33, 0),)}
PROFILES = {'cod-ios-assets-v1': 'ipa'}
# `com.ea.causeofdeathfree.bv` is the free edition (1.4.7); its resources are renumbered (assets.logical_members).
BUNDLE_PATTERN = r'com\.ea\.causeofdeath(?:free)?(?:\.[A-Za-z0-9-]+)*'


def in_game_banner(library) -> bool:
    """Whether the library is the free edition, whose layout leaves room for its in-game ad banner.

    1.4.7 reads `SHSEngine::g_bEnableInGameBanner` (zero-filled, set at run time by the ad code) in the SHSUIDialog
    constructor (0003c27c: narrator anchor y 135 instead of 120), GameModel::init (00012964: the schedule caption's
    y, +0x1c20, 55 instead of 10) and SHSUIChapterScreen::initChapterScreen (00040720). No banner is drawn here, but
    the owner's 1.4.7 device shows the shifted layout (IMG_0309: the narrator box 15 units lower than 1.3.4 puts it),
    so a free-edition library keeps it. 1.3.4 has no banner and no flag."""
    app = getattr(library, 'manifest', {}).get('ipa', {}).get('app', {})
    return str(app.get('CFBundleIdentifier', '')).startswith('com.ea.causeofdeathfree')


NAME_FONT = ('VerdanaBoldItalic', 291)
# SHSEngine::initFonts 000234da..000237ee; normal/gray/default dialogue
# uses black body text and dark-red names. Theme 2 retains its rose color.
DIALOGUE_COLORS = {1: (0, 0, 0), 2: (180, 78, 78), 3: (0, 0, 0), -1: (0, 0, 0)}
# initFonts (1.3.4 armv7 00025e68), case 7. Narration is CSFont +0xe254, TrebuchetMS-Italic 16 black, switching on '`'
# to +0xfa74 (the same face in 0xffb46d1a, stroke 0.6). Body text switches only on '`' (CSFont::handleSwitchChar
# 00004b54 toggles the base font's own switch characters; a ';' in body text is an ordinary character): theme 1's
# +0x142d4 goes to +0x15af4, red 0xfffe3535 italic; theme 2's +0x1d394 (rose) to +0x1ebb4, blue 0xff2968dd; the gray
# and default sets (+0x26454, +0x2f514) to black. The switch face is TrebuchetMS-Italic (+0x1ec) with stroke 0.5.
NARRATION_COLORS = ((0, 0, 0), (180, 109, 26))
BODY_MARKERS = ('`', {1: (254, 53, 53), 2: (41, 104, 221), 3: (0, 0, 0), -1: (0, 0, 0)})
NAME_COLORS = {'PajamaHip24': (0, 0, 0), 'PajamaHip26': (139, 0, 0),
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
# A timed incremental choice (services 2-4) whose timeout selection is -1, "no option" (Volume 7's "Let go." /
# "Hang on."): SHSUIMenu::tick (0003f12c) takes the timeout selection, and setReturnValue (0003e994) returns
# mapping[-1], the short at +0x98 just before the table at +0x9a. Only loadElement (0003ed88) writes that slot, and
# each service-2 menu is a new operator-new allocation, so it holds the allocation's initial memory: zero, the
# fresh-heap value (a reused menu-sized block keeps the same untouched slot). Not guaranteed natively; the scripts
# seen test the result against the options' values, so any non-option value takes the same branch.
TIMEOUT_NO_OPTION_RESULT = 0
# A timeout selection past the options (only Volume 2 script 25011's number puzzle: 1000 with values 0-3) reads
# mapping[1000], far past the 0x114-byte menu: undefined heap memory. Adaptation, owner's choice (2026-10-08): return
# the selection unmapped, which matches no option, so the script's wrong-answer branch plays -- what players would
# almost always have seen. The owner will compare it on device.
TIMEOUT_PAST_OPTIONS_UNMAPPED = True
# CoD's authoring tool stored U+2019 (right single quote) truncated to 0x19: "You're", "I'll", "couples'" in Volumes 6,
# 7 and 8. The device has no glyph for it and draws the font's missing-glyph box (IMG_0512 / IMG_0513, Volume 6
# Chapter Three). Adaptation, owner's choice (2026-10-14): show the apostrophe the line means. Display only
# (engine.substitute); scripts keep the byte. 0x09 (a truncated thin space) already lays out as a space. U+2018 as
# 0x18 has not been seen in CoD but is mapped as in SHS (shs/profile.py).
DISPLAY_CHARACTERS = {'\x18': "'", '\x19': "'"}
# Service 71 builds the quiz with SHSUIMenu::initActionMenu (dispatcher case 0x47, 1.3.4 armv7 00038f5a table):
# the iOS action menu SHS HD ported as WordGame.hd -- setFlyDurations(0.3, 0.5) (0004003e), the 0.7 s flyOnFinished
# timer (0003fed8, literal 0003ff40), skip-input 400.0 and tick 0.2 (00040ab8 / 00040aac), arc4random deal with 20
# swaps (resetActionMenu 0003fb60). Its answer sounds differ: handleMenuSelection (0003ea4e) plays 8003 for a
# positive weight, 8004 for a negative one, nothing for zero.
IOS_ACTION_MENU = True
WORD_GAME_SOUNDS = (8003, 8004)
# Service 78 creates UI type 5, SHSUIPortraitSelect (createUIElement 00037e5c): the same swap-to-front model, returning
# the front portrait's original index (setReturnValue 0004f840). touchesEnded (0004fe00) plays 8005, CoD's click, for
# both a swap and the confirm button; tapping the front portrait is silent.
PICKER_SOUNDS = (8005, 8005)
# SHS answer-feedback resource IDs do not establish semantics for CoD assets.
CHOICE_FEEDBACK_SOUNDS = {}
# Score notices (service 88) are SHS HD's letter effect (`SHSUIDialog::startLetterEffectAnimation`, 1.4.7
# 00038d84: the same timings), not Android's typed notice: dialogue_notice.COD_NOTICE.
LETTER_NOTICE = True
