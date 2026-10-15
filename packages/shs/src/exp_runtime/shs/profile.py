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
