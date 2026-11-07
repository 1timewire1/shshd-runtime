"""Patch an official episode with lines from the player's own copy of the book it adapts, leaving the original alone.

    python tools/translate/novel_patch.py PATCH.json --exp EPISODE.exp --epub BOOK.epub --out OUT.exp [--show]

PATCH.json lives with the player's reference files, never in this repository: it holds where each change goes, chapter
and paragraph references into the EPUB, and any narration written for the patch. The book's words are read from the
EPUB here, so neither this tool nor the patch carries them.

Every existing instruction keeps its address (`kiwi_rewrite`), so art, music, staging and everything not named in the
patch stay as they were. The result is a separate episode with its own pack and title. The operations:

    {"op": "replace", "find": PREFIX, "text": TEXT, "all": false}   new words for a line; its speaker and face are kept
    {"op": "remove", "find": PREFIX}                                skip a line
    {"op": "before" | "after", "find": PREFIX, "do": [STEP, ...]}   new material next to a line

A STEP is {"say": CHARACTER NAME, "expr": 0-4, "text": TEXT}, {"narrate": TEXT}, {"bg": ID} or {"music": ID}. A TEXT is
{"own": "..."} or a reference {"ch": 1, "p": 10, "q": [0, 1], "s": [0, 2], "join": "..."}: quotations `q` of paragraph
`p` (every one if omitted), joined, optionally only sentences `s`. Long text becomes several lines, split at sentences.
"""
import argparse
from dataclasses import dataclass
import hashlib
import html
import json
from pathlib import Path, PurePosixPath
import re
import sys
import unicodedata
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))

from exp_runtime.decode.bytecode import decode_program  # noqa: E402
from exp_runtime.exp import ExpArchive, Metadata, encode_exp  # noqa: E402
from casing import strings  # noqa: E402
from kiwi_rewrite import Rewriter, RewriteError  # noqa: E402

PUSH, PUSH_PAIR, PUSH_R, HOST_CALL, JUMP = 0x1a, 0x1b, 0x5a, 0x1f, 0x29
SAY, SAY_MODE, NARRATE, BACKGROUND, MUSIC = 13, 3, 65, 11, 80
NARRATION_THEME = 32
LONGEST_LINE = 190          # characters; the longest line in the Chapter 1-4 episode is 199
SENTENCE_END = r'(?<!Mr\.)(?<!Ms\.)(?<!Mrs\.)(?<!Dr\.)(?<=[.!?])\s+|(?<=[.!?]`)\s+'   # not after a title


class PatchError(ValueError):
    pass


def read_paragraphs(path, offset):
    """{chapter: [paragraph text]} from an EPUB, the chapter number being the file's number minus `offset`. Paragraph
    numbers count from the top of the chapter, the empty first entry and the printed heading included."""
    book = zipfile.ZipFile(path)
    root = re.search(r'full-path="([^"]+)"', book.read('META-INF/container.xml').decode('utf-8')).group(1)
    folder = PurePosixPath(root).parent
    package = book.read(root).decode('utf-8')
    items = {}
    for tag in re.findall(r'<item\b[^>]*>', package):
        ident, href = re.search(r'\bid="([^"]+)"', tag), re.search(r'href="([^"]+)"', tag)
        if ident and href:
            items[ident.group(1)] = href.group(1)
    chapters = {}
    for ident in re.findall(r'<itemref[^>]*idref="([^"]+)"', package):
        name = items[ident]
        found = re.fullmatch(r'chapter(\d+)\.html', name)
        if not found:
            continue
        text = book.read(str(folder / name)).decode('utf-8')
        text = re.sub(r'.*<body[^>]*>', '', text, flags=re.S)
        text = re.sub(r'</p>|</h\d>|<br[^>]*>|</div>', '\n', text)
        text = re.sub(r'<em>|</em>', '*', text)
        text = html.unescape(re.sub(r'<[^>]+>', '', text))
        text = re.sub(r'\n\s*\n+', '\n', text).strip()
        chapters[int(found.group(1)) - offset] = [''] + text.split('\n')
    return chapters


def house_style(text, renames):
    """A book quotation in the episode's conventions: straight quotes, `emphasis`, ... for dashes and ellipses, and a
    capital after ... as the episode writes it."""
    for old, new in renames.items():
        text = re.sub(rf'\b{re.escape(old)}\b', new, text)
    text = text.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"').replace('*', '`')
    text = re.sub(r'\s*…\s*\.?', '... ', text)
    text = re.sub(r'\s*—\s*', '... ', text).strip()
    text = re.sub(r'\.\.\. (`?)([a-z])', lambda m: f'... {m.group(1)}{m.group(2).upper()}', text)
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')    # naive, resume, as EA has them


def reference(item, chapters, renames):
    try:
        paragraph = chapters[item['ch']][item['p']]
    except (KeyError, IndexError):
        raise PatchError(f'no paragraph {item}') from None
    quotes = [q for q in re.findall(r'“([^”]*)”', paragraph)]
    chosen = [quotes[i] for i in item.get('q', range(len(quotes)))]
    if not chosen:
        raise PatchError(f'no quotation in {item}')
    joined = ''
    for index, part in enumerate(chosen):
        part = part.strip()
        last = index == len(chosen) - 1
        if 'join' in item and not last:
            part = part.rstrip(',') + item['join']
        elif part.endswith(','):
            following = None if last else chosen[index + 1].strip()
            part = part if following and following[0].islower() else part[:-1] + '.'
        joined += part + ('' if last else ' ')
    text = house_style(joined, renames)
    if 's' in item:
        first, end = item['s']
        text = ' '.join(re.split(SENTENCE_END, text)[first:end])
    return text


def text_of(item, chapters, renames):
    return item['own'] if 'own' in item else reference(item, chapters, renames)


def split_long(text):
    """Lines of at most LONGEST_LINE characters, at sentence ends, as the episode's own long speeches are."""
    lines, current = [], ''
    for sentence in re.split(SENTENCE_END, text):
        if current and len(current) + 1 + len(sentence) > LONGEST_LINE:
            lines.append(current)
            current = sentence
        else:
            current = f'{current} {sentence}'.strip()
    lines.append(current)
    return lines


@dataclass
class Line:
    """A dialogue or narration call in the original code."""
    start: int              # its first instruction
    text: int               # the instruction pushing the text
    call: int               # its host call


class Script:
    def __init__(self, rid, data):
        self.rid = rid
        self.program = decode_program(data)
        self.rewriter = Rewriter(self.program)
        self.addresses = {}
        for address, text in strings(self.program):
            self.addresses.setdefault(text, address)
        self.original = [(i.opcode, i.operand) for i in self.program.instructions]    # as the patch's finds read it
        self.before, self.after = {}, {}    # pc -> steps, in the order the patch gives them; a line's own "after" first
        self.removed = set()

    def lines(self, prefix):
        """Every use of the text starting with `prefix`, or nothing."""
        matches = {address for text, address in self.addresses.items() if text.startswith(prefix)}
        if len(matches) > 1:
            raise PatchError(f'{prefix!r} matches {len(matches)} lines')
        found = []
        code = self.original
        for address in matches:
            for pc, (opcode, operand) in enumerate(code):
                if opcode == PUSH and operand == address:
                    line = self.line_at(pc, code)
                    if line:
                        found.append(line)
        return found

    @staticmethod
    def line_at(pc, code):
        call = pc
        while call < len(code) and code[call][0] != HOST_CALL:
            if call - pc > 3 or code[call][0] not in (PUSH, PUSH_PAIR, PUSH_R):
                return None
            call += 1
        if call >= len(code):
            return None
        count, start = code[call][1] & 255, call
        while count > 0:
            start -= 1
            opcode = code[start][0]
            if opcode not in (PUSH, PUSH_PAIR, PUSH_R):
                return None
            count -= 2 if opcode == PUSH_PAIR else 1
        return Line(start, pc, call) if count == 0 else None

    def copy_line(self, line, text):
        """Steps repeating `line`'s call with other words."""
        return [('text', text) if pc == line.text else self.original[pc] for pc in range(line.start, line.call + 1)]

    def finish(self):
        for pc in {*self.after, *self.before}:
            def build(shim, steps=self.after.get(pc, []) + self.before.get(pc, [])):
                for step in steps:
                    for opcode, operand in step:
                        if opcode == 'text':
                            shim.emit(PUSH, self.rewriter.text(operand))
                        elif operand is None:
                            shim.emit(opcode)
                        else:
                            shim.emit(opcode, operand)
            self.rewriter.insert(pc, build)
        return self.rewriter.finish()


def compile_step(step, cast, chapters, renames):
    if 'bg' in step:
        return [[(PUSH_R, None), (PUSH, step['bg']), (PUSH, 0xffff), (HOST_CALL, BACKGROUND << 8 | 3)]]
    if 'music' in step:
        return [[(PUSH, step['music']), (PUSH_R, None), (HOST_CALL, MUSIC << 8 | 2)]]
    if 'narrate' in step:
        return [[(PUSH, NARRATION_THEME), ('text', line), (PUSH_R, None), (HOST_CALL, NARRATE << 8 | 3)]
                for line in split_long(text_of(step['narrate'], chapters, renames))]
    character = cast[step['say']]
    expression = step.get('expr', 0) << 8 | character
    return [[('text', line), (PUSH_PAIR, expression), (HOST_CALL, SAY << 8 | SAY_MODE)]
            for line in split_long(text_of(step['text'], chapters, renames))]


def apply(patch, exp, chapters):
    """The new archive's bytes, and a report of what each operation did."""
    archive = ExpArchive(exp)
    resources = {rid: archive.read(rid) for rid in archive.entries}
    scripts = [Script(rid, data) for rid, data in sorted(resources.items()) if data[:4] == b'kiwi']
    renames, cast, report = patch.get('renames', {}), patch['cast'], []

    def find(prefix, many=False):
        found = [(script, line) for script in scripts for line in script.lines(prefix)]
        if not found or (len(found) > 1 and not many):
            raise PatchError(f'{prefix!r} matches {len(found)} places')
        return found

    for op in patch['ops']:
        kind, prefix = op['op'], op['find']
        if kind == 'replace':
            lines = split_long(text_of(op['text'], chapters, renames))
            for script, line in find(prefix, op.get('all', False)):
                script.rewriter.code[line.text] = (PUSH, script.rewriter.text(lines[0]))
                extras = [script.copy_line(line, more) for more in lines[1:]]
                if extras:
                    script.after.setdefault(line.call + 1, []).extend(extras)
            report.append(('replace', prefix, lines))
        elif kind == 'remove':
            for script, line in find(prefix):
                script.rewriter.code[line.start] = (JUMP, line.call + 1)
                script.removed.add(line.start)
            report.append(('remove', prefix, []))
        elif kind in ('before', 'after'):
            script, line = find(prefix)[0]
            steps = [call for step in op['do'] for call in compile_step(step, cast, chapters, renames)]
            if kind == 'before':
                script.before.setdefault(line.start, []).extend(steps)
            else:
                script.after.setdefault(line.call + 1, []).extend(steps)
            report.append((kind, prefix, [text for call in steps for opcode, text in call if opcode == 'text']))
        else:
            raise PatchError(f'unknown operation {kind!r}')
    for script in scripts:
        resources[script.rid] = script.finish().to_bytes()
    metadata = archive.metadata()
    from exp_runtime.episode_version import RESOURCE as VERSION_RECORD, version_bytes
    resources[VERSION_RECORD] = version_bytes(patch.get('version', 1))     # (episode_version.py: newer replaces older)
    resources[1] = Metadata(patch['pack_id'], patch.get('episode_id', metadata.episode_id),
                            (patch['title'],) * 5).to_bytes()
    return encode_exp(resources), report


def check_source(patch, exp, epub):
    for key, data in (('exp_sha256', exp), ('epub_sha256', epub)):
        if key in patch and hashlib.sha256(data).hexdigest() != patch[key]:
            raise PatchError(f'{key}: this is not the file the patch was written for')


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('patch', type=Path)
    parser.add_argument('--exp', type=Path, required=True)
    parser.add_argument('--epub', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--show', action='store_true', help='print every operation and the lines it adds')
    args = parser.parse_args()
    patch = json.loads(args.patch.read_text(encoding='utf-8'))
    exp = args.exp.read_bytes()
    check_source(patch, exp, args.epub.read_bytes())
    try:
        data, report = apply(patch, exp, read_paragraphs(args.epub, patch.get('chapter_offset', 0)))
    except (PatchError, RewriteError) as error:
        parser.error(str(error))
    args.out.write_bytes(data)
    for kind, prefix, lines in report if args.show else ():
        print(f'{kind} {prefix!r}')
        for line in lines:
            print(f'    {line}')
    print(f'{args.out}: {len(report)} operations, {len(data)} bytes')


if __name__ == '__main__':
    main()
