"""Pair New Rules downloads with their smartphone EXPs in an imported library, by shared lines.

    python tools/translate/pairs.py EXPD_FOLDER LIBRARY [--out pairs.json]

A pair is the library episode sharing the most normalised lines (25+ characters) with the download; the share is
reported, and anything under half is listed as unpaired. It reads the library without changing it.
"""
import argparse
import functools
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from exp_runtime.decode.bytecode import decode_program  # noqa: E402
from exp_runtime.exp import ExpArchive  # noqa: E402
from casing import norm, strings  # noqa: E402
import newrules  # noqa: E402


def lines_of(programs):
    return {norm(text) for program in programs for _, text in strings(program) if len(text) >= 25}


def library_episodes(library):
    manifest = json.loads((library / 'library.json').read_text(encoding='utf-8'))
    for record in manifest['episodes']:
        if 'file' not in record or record.get('pack_id') == newrules.PACK_ID:
            continue                            # a translation already imported is never its own twin
        archive = ExpArchive((library / record['file']).read_bytes())
        programs = [decode_program(archive.read(r)) for r in archive.entries if archive.read(r)[:4] == b'kiwi']
        yield record, programs


@functools.lru_cache(maxsize=4)
def pair(expd_folder, library):
    """[{expd, title, twin, file, share, paired}] for every download in the folder (cached: the translator asks twice)."""
    expd_folder, library = Path(expd_folder), Path(library)
    library_lines = [(record, lines_of(programs)) for record, programs in library_episodes(library)]
    result = []
    for path in sorted(expd_folder.glob('*.expd'), key=lambda p: int(p.stem) if p.stem.isdigit() else 0):
        episode = newrules.read_expd(path.read_bytes())
        ours = lines_of(episode.scripts.values())
        best = max(library_lines, key=lambda item: len(ours & item[1]))
        share = len(ours & best[1]) / max(1, len(ours))
        result.append(dict(expd=path.name, title=episode.title, twin=best[0]['name'], file=best[0]['file'],
                           share=round(share, 3), paired=share >= 0.5))
    return result


def twin_word_games(expd_folder, library, expd_name):
    """The word games (71) of a download's smartphone twin, as (good words, bad words) lists; [] if it has none."""
    found = next((p for p in pair(Path(expd_folder), Path(library)) if p['expd'] == expd_name and p['paired']), None)
    if found is None:
        return []
    archive = ExpArchive((Path(library) / found['file']).read_bytes())
    games = []
    for rid in archive.entries:
        data = archive.read(rid)
        if data[:4] != b'kiwi':
            continue
        program = decode_program(data)
        for instruction in program.instructions:
            if instruction.opcode == 0x1f and instruction.operand >> 8 == 71 and instruction.operand & 255 == 8:
                args = newrules.pushed_values(program, instruction.pc, 8)
                lists = [newrules.text_at(program, a) if a is not None else None for a in args[2:4]]
                if None not in lists:
                    games.append(tuple([w for w in text.split('|') if w.strip()] for text in lists))
    return games


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('expd_folder', type=Path)
    parser.add_argument('library', type=Path)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    result = pair(args.expd_folder, args.library)
    for item in result:
        print(f"{item['expd']:9} {item['share']:5.2f} {'pair ' if item['paired'] else 'none '} {item['title'][:34]:34} {item['twin']}")
    if args.out:
        args.out.write_text(json.dumps(result, indent=1), encoding='utf-8')
