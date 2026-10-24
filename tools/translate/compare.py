"""Compare two playthrough records (playthrough.py): a translation against its smartphone twin.

    python tools/translate/compare.py TRANSLATED.json TWIN.json

Lines are matched on their text with case, punctuation and spacing ignored (New Rules is lowercase); the report gives
the share matched, then each difference in order: lines only one side shows, and matched lines whose speaker, character
or expression differ.
"""
import difflib
import json
import re
import sys


def norm(text):
    return re.sub(r'[^a-z0-9$]+', ' ', (text or '').lower()).strip()


def key(item):
    if item['kind'] == 'line':
        return 'L ' + norm(item['text'])
    if item['kind'] == 'choice':
        return 'C ' + ' | '.join(norm(o) for o in item['options'])
    if item['kind'] in ('title', 'message'):
        return item['kind'][0].upper() + ' ' + norm(item.get('title'))
    return item['kind']


def compare(ours, theirs, show=40):
    a, b = [key(x) for x in ours], [key(x) for x in theirs]
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    lines_ours = sum(1 for k in a if k.startswith('L '))
    lines_theirs = sum(1 for k in b if k.startswith('L '))
    matched = sum(1 for tag, i1, i2, j1, j2 in matcher.get_opcodes() if tag == 'equal'
                  for k in a[i1:i2] if k.startswith('L '))
    print(f'lines: ours {lines_ours}, twin {lines_theirs}, matched {matched}')
    print(f'events: ours {len(a)}, twin {len(b)}, matching blocks ratio {matcher.ratio():.3f}')
    shown, mismatched = 0, {}
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            for x, y in zip(ours[i1:i2], theirs[j1:j2]):
                if x['kind'] == 'line':
                    for field in ('character', 'expression', 'presentation'):
                        if x.get(field) != y.get(field):
                            mismatched.setdefault(field, []).append((x.get(field), y.get(field), x['text'][:50]))
            continue
        if shown < show:
            print(f'--- {tag}: ours {i1}-{i2}, twin {j1}-{j2}')
            for x in ours[i1:i2][:6]:
                print('  ours :', json.dumps(x, ensure_ascii=False)[:150])
            for y in theirs[j1:j2][:6]:
                print('  twin :', json.dumps(y, ensure_ascii=False)[:150])
            shown += 1
    for field, rows in mismatched.items():
        pairs = {}
        for x, y, _ in rows:
            pairs[(x, y)] = pairs.get((x, y), 0) + 1
        print(f'{field} differs on {len(rows)} matched lines:', sorted(pairs.items(), key=lambda kv: -kv[1])[:12])


if __name__ == '__main__':
    compare(*(json.load(open(path, encoding='utf-8')) for path in sys.argv[1:3]))
