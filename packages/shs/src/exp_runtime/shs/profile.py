"""Surviving High School content and host-service profile."""
from .audio import music_cue as MUSIC_CUE
from .content import BUILTIN, extract_builtin, _inspect_apk as inspect_apk
from .services import dispatch as DISPATCH
from .audio import IOS_DOWNLOADED_MUSIC as DOWNLOADED_MUSIC
from .football import Football
from .word_grid import WordGrid
from .scene_transition import SceneTransition
from ..fade_transition import FadeTransition

STATE_TYPES = {'word_grid': WordGrid | None, 'football': Football | None,
               'scene_transition': SceneTransition | FadeTransition | None}
# Android's transition is a nonvisual callback boundary (scene_transition.py). With the HD (iPad) bundle the session runs
# SHS HD's own SHSFadeLayer blinds and fade (fade_transition.FadeTransition, the same code as CoD's).
SCENE_TRANSITION = SceneTransition
HD_SCENE_TRANSITION = FadeTransition
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
# HD's initFonts (1.4.38 0002af38): narration is +0xe274, TrebuchetMS-Italic in 0xffb46d1a, switching on '`' to +0xfa90, the
# same face and colour with a stroke of 1.2 at its 32 (0.6 at 16 points). Bold, then, not the Android build's darker colour.
NARRATION_EMPHASIS_FONT = 'TrebuchetMS_Italic16NarrationEmphasis'
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
# -[SHSViewController toggleDTZ] (0004d0dc): every toggle of the tree zoom tab (desktop_tree_zoom.py).
TREE_ZOOM_SOUND = 8017
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
# shshd-runtime: episodes translated from SHS: New Rules (tools/translate, pack 31300) keep New Rules' own right/wrong
# jingles, its music tracks 13 and 1, which the smartphone versions replaced with 8007/8003 at the same beats (~590
# each across the 45 paired stories). They play as episode sound effects (service 79; music, 80, in translations made
# before 2026-10-25) at the translator's MUSIC_BASE (26980) + track, so for that pack those requests are answer
# feedback too. Pack -> {resource ID: feedback}. SHS '11's (31600, tools/translate shs11_story.CUE_TRACKS) are its tracks 0
# and 2, at the beats of 8007 and 8003 too.
TRANSLATED_FEEDBACK_MUSIC = {31300: {26980 + 13: 1, 26980 + 1: -1}, 31600: {26980: 1, 26980 + 2: -1}}
# shshd-runtime: a translated episode's own picture for the whole 384x512-unit frame, drawn under the location art
# where SHS leaves black (desktop.py _draw_background_layer). New Rules' location strips are 3:1, so they leave bands
# above and below; the translator stores New Rules' UI backdrop at its FRAME_BACKDROP (26999). Pack -> resource ID.
# The X360 prototype's translations (31400) show the same strips, so they carry the same backdrop.
TRANSLATED_FRAME_BACKDROP = {31300: 26999, 31400: 26999, 31000: 26999, 31100: 26999, 31200: 26999}
# shshd-runtime: a pack's backdrop for a speaker's box colour (key 651), in place of the one above: pack -> {theme: resource}.
# BREW's dialogue panel turns pink behind a pink box and back for anyone else (screens.js DialogueScreen, seen in the real game).
TRANSLATED_THEME_BACKDROP = {pack: {2: 26991} for pack in (31000, 31100, 31200)}
# shshd-runtime: where a translated pack's portrait picker (service 78) puts its portraits, by how many there are, in
# place of the native slots (character_picker.POSITIONS), which leave one side empty for four. King of Diss offers four
# faces: the chosen one in the middle, one above it, one either side. Pack -> {count: [(x, y) per slot]}.
TRANSLATED_PICKER_LAYOUTS = {31300: {4: [(160, 275), (52, 241), (160, 170), (269, 241)]}}
# shshd-runtime: a translated pack's second portrait set, shown while the player keeps "hi-res portraits" on
# (ContentLibrary.hires_portraits): pack -> (first, end, offset), portrait resources in [first, end) moved by offset.
# New Rules' translations keep the WinMo portraits at 26200 and the X1i jar's redrawn ones, tripled (HD-sized), at
# 27200 on (tools/translate newrules.PORTRAIT_BASE / HIRES_PORTRAIT_OFFSET).
# The cancelled Xbox 360 prototype's translations (pack 31400, tools/translate x360.py) store theirs the same way.
TRANSLATED_PORTRAIT_ART = {31300: (26200, 26980, 1000), 31400: (26200, 26980, 1000)}
# Whose two sets the "Hi-Res Portraits" switch chooses between: New Rules' WinMo and X1i art. The X360's are two sizes of
# one render, so it always shows the larger (owner, 2026-11-01: the switch doesn't belong in its episodes).
HIRES_SWITCH_PACKS = (31300,)
# shshd-runtime: the "MS3 Characters" switch (ContentLibrary.ms3_characters): pack -> how far above a portrait's ID its
# April 2009 look is (tools/translate x360.MS3_LOOKS). A portrait with none stays as it is.
MS3_CHARACTER_ART = {31400: 2000}
# shshd-runtime: a translated pack's own pictures for the relationship icons, on the smartphone's places and motion
# (DialogueRenderer.indicator_image): pack -> {SHS's icon: the pack's}. The ring that grows under a new icon stays SHS's.
TRANSLATED_BADGE_ART = {pack: {3010: 26992, 3011: 26993, 3012: 26994, 3014: 26995, 3016: 26996, 3018: 26997}
                        for pack in (31600, 31000, 31100, 31200)}
# shshd-runtime: a translated pack's own sounds for a relationship icon, for and against (`dc` in SHS '11: its value going up
# or down, whichever icons that shows), in place of SHS's (engine._relationship).
TRANSLATED_BADGE_SOUNDS = {31600: (26980 + 6, 26980 + 5)}
# shshd-runtime: a translated pack's sounds that have only one channel between them, as SHS '11's player has (`dk`: a new one
# stops the last, co.a(dd, dd)): pack -> their resources (Desktop._play_sounds). SHS's own and the music go on as they do.
TRANSLATED_ONE_SOUND_CHANNEL = {31600: range(26980, 26992)}
# shshd-runtime: where the "Smartphone Music" switch changes something (Desktop.smartphone_switch): translated packs whose
# stories carry the smartphone's music (shs11_story.smartphone_music). Off, those calls stay in the story and go unheard.
# Their sound effects are the game's own either way (owner, 2026-11-03).
SMARTPHONE_MUSIC_PACKS = (31600,)
# shshd-runtime: where the "Use Translated Mini-Games" switch changes something: pack -> its episodes, or None for all of
# them. Day of Diss (31400's episode 1) has no minigame.
TRANSLATED_MINIGAMES = {31300: None, 31400: (2, 3, 4), 31600: None}
# shshd-runtime: a translated game's own name-replacement table (MenuState.names_for): pack -> its set's key in
# player.json `name_sets`. New Rules' stories share theirs, never the smartphone stories' (`$Emily`, `$Kenji` and
# `$Date` are in both Dancing Queen and Homecoming Queen).
# SHS '11's (31600) share theirs too: its `$ZOE` is another playthrough's, kept apart from the smartphone stories'.
TRANSLATED_NAME_SETS = {31300: 'new_rules', 31600: 'shs11', 31000: 'brew', 31100: 'brew', 31200: 'brew'}
# shshd-runtime: two-speaker lines in a translated pack (Session.dialogue_duet): pack -> (partner key, expression
# key), global numbers the translator sets around a line two characters say together ("Both", "Andy and Laura"),
# the partner as its ID + 1 (0: none). The line shows the gray box with a portrait on each side and the name
# centered (owner, 2026-10-24). An app without this entry shows the first speaker alone, as SHS 13 does.
TRANSLATED_DUETS = {31300: (31310, 31311)}
# shshd-runtime: emoticons over a translated speaker's portrait (Session.portrait_effect, emoticon_effects): pack ->
# (key, first image), the global number the translator sets around the line (an emoticon_effects effect, 1-6; 0 none)
# and the episode image of effect 1, the other five following it. The cancelled X360 prototype's translations (31400,
# tools/translate x360.py) carry its emoticon sheet's six cells at 26990-26995.
TRANSLATED_PORTRAIT_EFFECTS = {31400: (31410, 26990)}
# shshd-runtime: a translated pack's colour for a named line without a portrait (Session.narration_theme): pack -> the
# global number the translator sets around the line (1 blue, 2 pink, 3 gray; 0 keeps SHS's own). New Rules shows an
# object or unseen voice ("TV", "Radio") in a gray bubble and an off-stage character in their own colour (owner,
# 2026-10-25); without this entry they keep the yellow named-line box.
TRANSLATED_NARRATION_THEMES = {31300: 31312}
# shshd-runtime: a translated pack's music that is an intro running into a loop (music_stream.MusicStream.chain):
# pack -> {intro resource: loop resource}. The intro plays once, then the loop repeats without a gap. The X360
# prototype's Day of Diss plays `dont_trust_me` into `dont_trust_me_loop` (tools/translate/x360.py MUSIC_INTRO /
# MUSIC_LOOP; owner, 2026-10-26).
TRANSLATED_MUSIC_LOOPS = {31400: {26900: 26901}}
# shshd-runtime: any other episode may declare the four features above for itself (presentation.py, resource 3: the
# episode creator writes it) and the runtime honours it (content.presentation_feature); the tables above win for
# their packs. An app without them shows one speaker, the yellow named-line box, no emoticon, and the intro alone.
PRESENTATION_RECORD = True
# shshd-runtime: episodes translated from other SHS games, recognised on import by their title's tag (content.py
# legacy_fields: "Lovers' Lane (SHSNR)" imports as "Lovers' Lane"): tag -> the picker's badge, its colour in the list
# view (the game's own: New Rules' was blue) and the category the episode is filed under (owner, 2026-10-25). `order`
# places an episode by another position than its id: New Rules' second built-in story, Dancing Queen (101), follows
# King of Diss (1), ahead of the downloads (2-48); King of Diss Lite (100) stays last, as the alternative version.
# The cancelled Xbox 360 prototype's translations (tools/translate/x360.py TITLE_SUFFIX) are tagged "X360" in the Xbox
# 360's green, under their own category (owner, 2026-10-31); their old place was Now Airing's "Date Unknown".
LEGACY_GAMES = {'SHSNR': dict(badge='NR', color=(41, 104, 221), category='New Rules', order={101: 1.5}),
                # Day of Diss, Monday Planner, Dating Beth, Puzzle Test (owner, 2026-11-02).
                'SHSX360': dict(badge='X360', color=(16, 124, 16), category='Xbox 360', order={4: 2, 3: 3, 2: 4}),
                # SHS '11, the J2ME game (tools/translate shs11_story.py), in the orange of the 11 in its logo: between that
                # 11's outline (216, 96, 32) and its gold fill (248, 176, 8), which is too pale to read on a menu's rows.
                'SHS11': dict(badge="'11", color=(232, 120, 16), category="SHS '11"),
                # The BREW games (tools/translate brew.py). The '08 Campaign's unnumbered stories go by their in-game dates
                # (owner, 2026-11-05): Quizzes 1-3 and Special 1 Halloween.
                'SHS07': dict(badge="'07", color=(80, 112, 200), category="SHS '07"),
                'SHS08': dict(badge="'08", color=(200, 64, 96), category="SHS '08",
                              order={9001: 302.5, 9002: 303.5, 9003: 401.5, 9101: 707.5})}
# Service 71's quiz: Android's own pacing unless the HD bundle is present (engine.py); right/wrong answer sounds.
IOS_ACTION_MENU = False
WORD_GAME_SOUNDS = (8001, 8002)
# shshd-runtime: a translated pack's own right/wrong sounds for service 71's quiz, pack -> (right, wrong) episode
# resources. Translated New Rules episodes play its own jingles (tracks 13 and 1, at the translator's MUSIC_BASE
# 26980 + track) there instead of SHS's (owner, 2026-10-25). An episode without both keeps WORD_GAME_SOUNDS.
TRANSLATED_WORD_GAME_SOUNDS = {31300: (26980 + 13, 26980 + 1), 31600: (26980 + 8, 26980 + 7)}
# Service 78's portrait selector: swapping a portrait to the front, then confirming (Android FUN_000d1b48).
PICKER_SOUNDS = (8013, 8010)
# Curly single quotes truncated to one byte by the authoring tool, as in Cause of Death (cod/profile.py): U+2019 as
# 0x19 (23 strings: "Ben\x19s", "haven\x19t") and U+2018 as 0x18 (6: cupcakes that say "\x18BEN\x19"). Neither
# font has a glyph for them. Adaptation, owner's choice (2026-10-14): show the straight quote. Display only
# (engine.substitute); 0x09 already lays out as a space.
DISPLAY_CHARACTERS = {'\x18': "'", '\x19': "'"}
# A timed incremental choice (service 4) whose timeout selection is -1, "no option" (What Happened to Colt, Part 1's
# "Dodge!" / "Collide!"): as in Cause of Death (cod/profile.py), SHS HD's SHSUIMenu::setReturnValue (00046100)
# returns mapping[-1], the short at +0xa4 before the table at +0xa6. The constructor (00047d94) never writes it and
# only loadElement (0004649a, a restored menu) does, so a new menu returns its allocation's initial memory: zero.
TIMEOUT_NO_OPTION_RESULT = 0
# Android's typed notice; an HD build (engine.hd_version) uses the letter effect instead.
LETTER_NOTICE = False
