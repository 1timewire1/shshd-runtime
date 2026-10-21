"""Surviving High School content and host-service profile."""
from .audio import music_cue as MUSIC_CUE
from .content import BUILTIN, extract_builtin, _inspect_apk as inspect_apk
from .services import dispatch as DISPATCH
from .audio import IOS_DOWNLOADED_MUSIC as DOWNLOADED_MUSIC
from .football import Football
from .word_grid import WordGrid
from .scene_transition import SceneTransition

STATE_TYPES = {'word_grid': WordGrid | None, 'football': Football | None,
               'scene_transition': SceneTransition | None}
# This fork leaves exp-runtime's engine-level SceneTransition (SCENE_TRANSITION) unset: its scene changes are
# scene_fade.py's binary-verified fades, drawn by the player, and the main menu's entry is application.py's.
MENU_TRANSITION = 0

KEY = 'shs'
TITLE = 'Surviving High School'
SOURCES = 'SHS Android 1.0.9 APK or SHS IPA'
CATALOG_FILENAME = 'shs_options.sav'


def twin_map():
    """This fork's shipped HD twin map (`hd_twin_map.py`, fingerprints only), which `hd_twins.build_from_map` turns
    into a library's twin store from the player's own HD episodes."""
    from . import hd_twin_map
    return hd_twin_map
# Legacy and Android envelopes: (current-entry offset, trailing flag count).
CATALOG_LAYOUTS = {version: ((32, version - 16), (36, version - 16)) for version in (16, 17, 18)}
PROFILES = {'shs-android-1.0.9': 'apk', 'shs-ios-assets-v1': 'ipa'}
# `com.ea.shslite.row` is the free edition of the same app (1.4.2, build 1.4.3.53): its res_generated passes the
# full ios_assets contract and it ships the same three bundled stories (shshd-runtime).
BUNDLE_PATTERN = r'com\.ea\.shs(?:lite)?(?:\.[A-Za-z0-9-]+)*'
NAME_FONT = ('PajamaHip', 505)
# Android 000a92f4 scales this location's X axis only. Alignment still uses
# unscaled content width (0007b790 -> CCNode::getContentSize 0013b5b8).
BACKGROUND_SCALE_X = {1013: 1.01}
DIALOGUE_COLORS = {1: (41, 104, 221), 2: (180, 78, 78), 3: (108, 108, 108), -1: (223, 163, 52)}
IOS_DIALOGUE_COLORS = {1: (41, 104, 221), 2: (180, 78, 78), 3: (137, 137, 137), -1: (180, 109, 26)}
NARRATION_COLORS = (223, 163, 52), (125, 67, 0)
NAME_COLORS = {'PajamaHip24': (41, 104, 221), 'PajamaHip26': (41, 104, 221),
               'PajamaHip266': (180, 78, 78), 'PajamaHipG26': (137, 137, 137),
               'PajamaHipY26': (180, 109, 26), 'PajamaHipS26': (254, 53, 0)}
NOTICE_FONTS = {}
MUSIC_RANGE = range(8201, 8233)
# SHS iOS doSoundManagerTransition (0003b44c), splashScreenFlewIn (0002adb0).
MENU_MUSIC = 8215
DEFAULT_EPISODE = (5, 9)
RELATIONSHIP_ASSETS = (3010, 3011, 3012)
RELATIONSHIP_FLASH = {3010: 3013, 3011: 3015, 3012: 3017}
RELATIONSHIP_LOSS = {3010: 3014, 3011: 3016, 3012: 3018}
CLICK_SOUND = 8010
# SHSUIMenu::handleMenuSelection: Android 000afee8, iOS 00084600.
WORD_CHOICE_SOUNDS = {1: 8001, -1: 8002}
# SHSEngine::buttonPressed pause branch (iOS 00051214).
PAUSE_SOUND = 8011
# SHS HD's Options (ui_sound.py): switching Sound on plays 0x1f44 with the other effects stopped
# (SHSEngine::setSoundEnabled 00022280, from SHSWidgetMenu::buttonPressed tag 11); the Sound FX slider previews
# getToggleSoundID (0001ae18, 0x1f47) and the Music slider 0x1f49 at its own volume (sliderChanged 0004f1cc).
SOUND_ON_SOUND = 8004
SOUND_SLIDER_SOUND = 8007
MUSIC_SLIDER_SOUND = 8009
# Original quiz scripts dispatch these through service 79 for correct/wrong
# feedback (Football Star's shared classroom routine also covers finals).
# They are fixed SHS base-bank IDs, not episode counters or text heuristics.
CHOICE_FEEDBACK_SOUNDS = {8007: 1, 8003: -1}
# Service 71's quiz: Android's own pacing unless the HD bundle is present (engine.py); right/wrong answer sounds.
IOS_ACTION_MENU = False
WORD_GAME_SOUNDS = (8001, 8002)
# Service 78's portrait selector: swapping a portrait to the front, then confirming (Android FUN_000d1b48).
PICKER_SOUNDS = (8013, 8010)
# Curly single quotes truncated to one byte by the authoring tool, as in Cause of Death (cod/profile.py): U+2019 as
# 0x19 (23 strings: "Ben\x19s", "haven\x19t") and U+2018 as 0x18 (6: cupcakes that say "\x18BEN\x19"). Neither
# font has a glyph for them. Adaptation, owner's choice (2026-10-14): show the straight quote. Display only
# (engine.substitute); 0x09 already lays out as a space.
DISPLAY_CHARACTERS = {'\x18': "'", '\x19': "'"}
# Android's typed notice; an HD build (engine.hd_version) uses the letter effect instead.
LETTER_NOTICE = False
