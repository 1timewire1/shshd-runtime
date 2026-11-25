"""Build the SD Portraits add-on (`shssd`): the standard originals of the HD portraits an install shows, which its own
files do not hold, from the player's own standard episodes.

    python tools/build_sd_addon.py --source LIBRARY [--source LIBRARY ...] --install INSTALL [--install ...] --out DIR

SD Portraits (Options > Extras, owner 2026-11-25) draws every portrait in its standard original, or only the
redesigned ones. A standard episode keeps its own; an HD episode needs the original from somewhere, and the shipped
twin map (`shs/hd_twin_map.py`: SD_OF, SD_OF_EPISODE) names which. The app finds each in the library's standard
episodes or in this add-on (`hd_twins.build_from_map`, the SD Portraits store).

INSTALL is what a player installs: a zip (the tester bulk zip), a folder or an `.exp`. Every HD portrait its EXP
files hold is looked up in the map; when none of that portrait's originals is in INSTALL either, the first is added,
found in the SOURCE libraries (which must hold the standard episodes: a reference library). An HD episode whose story
shows a different look of the original (SD_OF_EPISODE's strict entries) gets that one. The shared bank needs nothing:
the APK holds Android's portraits, drawn by id.

Writes DIR/SD_Addon_SD_Portraits.exp; import it as any add-on (docs/ADDONS.md). No picture comes from the project.
"""
import argparse
import hashlib
from pathlib import Path
import zipfile

from exp_runtime.addons import RESOURCE as ADDON_RECORD, provides_bytes
from exp_runtime.content import ContentLibrary
from exp_runtime.exp import ExpArchive, Metadata, encode_exp
from exp_runtime.hd_twins import LOCAL_ART, SD_ADDON, fingerprint

TITLE = 'SD Portraits'
REVISION = 1
PACK_ID = 32100             # its metadata's pack: it has no episodes (past Novel Extended's 32000)
FIRST = 26000
NAME = 'SD_Addon_SD_Portraits.exp'


def install_files(paths):
    """(record id: the sha256, fingerprints of its local resources) of every EXP in the install."""
    def exps():
        for path in paths:
            path = Path(path)
            if path.is_dir():
                for member in sorted(path.rglob('*.exp')):
                    yield member.read_bytes()
            elif path.suffix.lower() == '.zip':
                with zipfile.ZipFile(path) as archive:
                    for member in archive.namelist():
                        if member.lower().endswith('.exp'):
                            yield archive.read(member)
            else:
                yield path.read_bytes()
    for data in exps():
        try:
            archive = ExpArchive(data)
        except Exception:
            continue
        keys = set()
        for resource_id in archive.entries:
            if resource_id >= LOCAL_ART:
                try:
                    keys.add(fingerprint(archive.read(resource_id)))
                except Exception:
                    continue
        yield hashlib.sha256(data).hexdigest(), keys


def needed(twin_map, files):
    """The originals the add-on must carry for an install whose EXP files are `files` [(record id, fingerprints)]."""
    held = set().union(*(keys for _, keys in files)) if files else set()
    need = []
    for hd, candidates in sorted(twin_map.SD_OF.items()):
        if hd in held and not any(key in held for key in candidates):
            need.append(candidates[0])
    for record, keys in files:
        for hd, (key, strict) in sorted(twin_map.SD_OF_EPISODE.get(record, {}).items()):
            if strict and hd in keys and key not in held:
                need.append(key)
    return list(dict.fromkeys(need))


def find(libraries, wanted):
    """{fingerprint: bytes} from the libraries' standard episodes (and any other)."""
    found = {}
    for library in libraries:
        for record in sorted(library.episodes, key=lambda r: r.get('variant') != 'standard'):
            if len(found) == len(wanted):
                return found
            try:
                archive = library.open_episode(record['id']).archive
            except Exception:
                continue
            for resource_id in archive.entries:
                if resource_id < LOCAL_ART:
                    continue
                try:
                    data = archive.read(resource_id)
                except Exception:
                    continue
                key = fingerprint(data)
                if key in wanted and key not in found:
                    found[key] = data
    return found


def build(pictures):
    """The add-on's bytes: the originals at 26000 on (their order is the add-on's own; the app finds them by content)."""
    resources = {FIRST + index: data for index, data in enumerate(pictures)}
    resources[ADDON_RECORD] = provides_bytes(SD_ADDON, TITLE, REVISION)
    resources[1] = Metadata(PACK_ID, 0, (TITLE + ' (addon)',) * 5).to_bytes()
    return encode_exp(resources)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, action='append', required=True)
    parser.add_argument('--install', type=Path, action='append', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    from exp_runtime.shs import hd_twin_map
    libraries = [ContentLibrary(path) for path in args.source]
    for library in libraries:
        library.hd_art_mode = 'off'
    files = list(install_files(args.install))
    # The shared bank's portraits are in the APK every install holds: never carried (the app reads them by id).
    bank = set()
    for resource_id in hd_twin_map.BANK_PORTRAITS:
        try:
            bank.add(fingerprint(libraries[0].android_asset(resource_id)))
        except Exception:
            continue
    need = needed(hd_twin_map, [*files, ('apk', bank)])
    found = find(libraries, set(need))
    missing = [key for key in need if key not in found]
    data = build([found[key] for key in need if key in found])
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / NAME).write_bytes(data)
    print(f'{len(files)} install files; {len(need)} originals needed, {len(need) - len(missing)} found '
          f'-> {args.out / NAME} ({len(data) // 1024} KB)')
    for key in missing:
        print('  not found:', key)
    for library in libraries:
        library.close()


if __name__ == '__main__':
    main()
