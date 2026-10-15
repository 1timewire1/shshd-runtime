"""Extract and verify the iOS HD build's own bundled Football Star hub.

This is a genuinely different thing from `Football_Star.exp` (the Android
APK's built-in copy, extracted by `builtin_episode.extract_football` and
already covered by the regular test suite / audit_runtime.py). HD's own
copy lives inside the HD ipa itself, at `Payload/Surviving_HS.app/
res_generated/25001`-`25021` -- the game's hub screen, closest to the
DTView/Faceplace-only services (see docs/ENGINE_ABI.md section 6) that
never appear in ordinary downloadable episodes. audit_hd_visual_fidelity.py
deliberately excludes both the Android built-in and this HD one from its
195-episode sweep (they're not part of that download library); this tool
exists so HD's own Football Star doesn't go permanently unverified just
because it isn't a normal file on disk.

Needs both the Android APK and the optional HD ipa. Also needs one
test-only seed: HD's own Football Star queries character art for ids
0/13/14 before ever setting it (a real, pre-existing, deliberately
unfixed gap -- see legacy/findings.md, "Art requested for uninitialized
character 0"), expecting app-wide name/avatar-creation state a real
playthrough establishes before ever reaching the hub, which a standalone
extraction never runs. This tool seeds past that one query, the same way
earlier sessions verified this content interactively.
"""
import argparse
from pathlib import Path
import struct
import tempfile

from exp_runtime.shs.builtin_episode import FOOTBALL_SCRIPTS
from exp_runtime.content import ContentError, ContentLibrary, ExpArchive, import_game
from exp_runtime.menu import MenuStrings

from audit_hd_visual_fidelity import ANDROID_BACKGROUND_WIDTH, ANDROID_MASK_SIZE, classify, drive_episode

HD_RESOURCE_PREFIX = 'Payload/Surviving_HS.app/res_generated/'
HD_FOOTBALL_NAME = 'Football_Star_HD.exp'

# Character ids HD's own Football Star queries art for before this engine
# ever sets it -- see the module docstring. The specific asset id doesn't
# matter (nothing here claims it's the "real" art); it only needs to be a
# valid, decodable portrait so the query stops raising.
SEED_CHARACTER_IDS = (0, 13, 14)
SEED_ASSET_ID = 2010


def extract_hd_football(apk, ipa):
    """Mirrors builtin_episode.extract_football's CSPUD construction
    exactly, sourced from the HD ipa's own resource bank instead of the
    Android APK's."""
    names = set(ipa.namelist())
    if HD_RESOURCE_PREFIX + '25001' not in names:
        return None
    titles = MenuStrings.parse(apk.read('assets/Assets/13'))
    metadata = bytearray(struct.pack('>HH', 0, 0))
    for index in range(193, 198):
        title = titles[index].encode('utf-8')
        if not title or len(title) > 65535:
            raise ContentError('Invalid built-in episode title')
        metadata += struct.pack('>H', len(title)) + title
    records = {1: bytes(metadata)}
    for resource_id in FOOTBALL_SCRIPTS:
        member = HD_RESOURCE_PREFIX + str(resource_id)
        if member not in names:
            continue  # Confirmed: HD's own bank is missing 25023; the rest decode fine.
        data = ipa.read(member)
        if not data.startswith(b'kiwi'):
            raise ContentError(f'HD built-in story resource {resource_id} is not KiWi')
        records[resource_id] = data
    index, bodies = bytearray(), bytearray()
    start = 9 + 6 * len(records)
    for resource_id, data in sorted(records.items()):
        index += struct.pack('>HI', resource_id, start + len(bodies))
        bodies += struct.pack('>III', len(data), len(data), 0) + data
    result = b'CSPUD' + struct.pack('>I', len(records)) + index + bodies
    ExpArchive(result).programs()  # Validate every copied script before publishing.
    return bytes(result)


def seed_character_art(session):
    for character_id in SEED_CHARACTER_IDS:
        session.engine.character_art_bases[character_id] = SEED_ASSET_ID
        session.engine.character_art_variants[character_id] = [SEED_ASSET_ID] * 5


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk', type=Path, required=True)
    parser.add_argument('--hd-ipa', type=Path, required=True)
    args = parser.parse_args()

    import pygame
    pygame.display.init()
    from zipfile import ZipFile
    with ZipFile(args.apk) as apk, ZipFile(args.hd_ipa) as ipa:
        data = extract_hd_football(apk, ipa)
    if data is None:
        print('HD ipa has no bundled Football Star (res_generated/25001 missing).')
        return 1
    with tempfile.TemporaryDirectory(prefix='shs-runtime-hd-football-') as temporary:
        temp_dir = Path(temporary)
        exp_path = temp_dir / HD_FOOTBALL_NAME
        exp_path.write_bytes(data)
        directory = temp_dir / 'library'
        manifest = import_game(args.apk, [exp_path], directory, hd_ipa_path=args.hd_ipa)
        episode_id = [e['id'] for e in manifest['episodes'] if e['name'] == HD_FOOTBALL_NAME][-1]
        with ContentLibrary(directory) as library:
            resources = library.open_episode(episode_id)
            outcome = drive_episode(resources, before_start=seed_character_art)
    backgrounds = classify(outcome['backgrounds'], reference_width=ANDROID_BACKGROUND_WIDTH)
    portraits = classify(outcome['portraits'], reference_size=ANDROID_MASK_SIZE)
    print(f"stop_reason: {outcome['stop_reason']} (steps={outcome['steps']})")
    print(f"backgrounds: {backgrounds} ({len(outcome['backgrounds'])} unique)")
    print(f"portraits: {portraits} ({len(outcome['portraits'])} unique)")
    failed = (backgrounds['decode_errors'] or portraits['decode_errors']
             or outcome['stop_reason'].split(':')[0] in
             ('VMError', 'ContentError', 'ValueError', 'RuntimeError', 'KeyError', 'AttributeError'))
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
