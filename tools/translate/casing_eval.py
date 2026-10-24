"""Measure the casing dictionary leave-one-out on the paired New Rules stories.

    python tools/translate/casing_eval.py EXPD_FOLDER LIBRARY PAIRS.json [--show STORY.expd]

For each paired story: learn from the other 44, case its strings, and compare word by word with the smartphone twin's
strings that have the same words. Prints per-story and overall word and string accuracy.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from exp_runtime.decode.bytecode import decode_program  # noqa: E402
from exp_runtime.exp import ExpArchive  # noqa: E402
import casing  # noqa: E402
import newrules  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('expd_folder', type=Path)
    parser.add_argument('library', type=Path)
    parser.add_argument('pairs', type=Path)
    parser.add_argument('--show')
    args = parser.parse_args()
    data = {}
    for pair in json.loads(args.pairs.read_text()):
        if not pair['paired']:
            continue
        episode = newrules.read_expd((args.expd_folder / pair['expd']).read_bytes())
        _, names = newrules.discover(episode)
        ours = [t for p in episode.scripts.values() for _, t in casing.strings(p)]
        archive = ExpArchive((args.library / pair['file']).read_bytes())
        theirs = [t for r in archive.entries if archive.read(r)[:4] == b'kiwi'
                  for _, t in casing.strings(decode_program(archive.read(r)))]
        data[pair['expd']] = (ours, theirs, names, episode.title)
    total = Counter()
    for story, (ours, theirs, names, title) in data.items():
        dictionary = casing.learn([(o, t) for k, (o, t, *_) in data.items() if k != story])
        cased = {casing.norm(t): t for t in theirs}
        name_words = {w for n in names for w in casing.WORD.findall(n)}
        counts, examples = Counter(), []
        for text in ours:
            twin = cased.get(casing.norm(text))
            if twin is None or len(text) < 8:
                continue
            if text == title.lower():
                mine = title
            elif text in names:
                mine = casing.title_case(text)
            else:
                mine = casing.apply(text, dictionary, name_words)
            a, b = casing.WORD.findall(mine), casing.WORD.findall(twin)
            if [x.lower() for x in a] != [x.lower() for x in b]:
                continue
            a = [x for x, y in zip(a, b) if not y.startswith('$')]          # $KEY spelling is the script's own
            b = [y for y in b if not y.startswith('$')]
            counts['strings'] += 1
            counts['exact'] += a == b
            counts['words'] += len(a)
            counts['right'] += sum(x == y for x, y in zip(a, b))
            if a != b and story == args.show and len(examples) < 30:
                examples.append((mine[:90], twin[:90]))
        total.update(counts)
        print(f"{story:9} words {counts['right'] / max(1, counts['words']):.2%}  strings "
              f"{counts['exact'] / max(1, counts['strings']):.1%}  ({counts['strings']})")
        for mine, twin in examples:
            print('   ours:', mine, '\n   twin:', twin)
    print(f"overall words {total['right'] / total['words']:.2%}  strings {total['exact'] / total['strings']:.1%}  "
          f"({total['strings']} strings, {total['words']} words)")


if __name__ == '__main__':
    main()
