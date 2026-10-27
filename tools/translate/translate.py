"""Translate other SHS games' episodes into shshd-runtime `.exp` files (reference/Other Games/docs/TRANSLATOR_PLAN.md).

    python tools/translate/translate.py newrules EPISODE.expd --pud RES_LARGE_PUD [--x1i X1I_JAR]
        [--synth java|sf2|none] [--soundfont SF2] [--library LIB] --out OUT_DIR
    python tools/translate/translate.py x360 DATA_PAK --pud RES_LARGE_PUD [--x1i X1I_JAR] --looks NR_LOOKS_JSON
        [--story day-of-diss|puzzle-test|all] [--music CUE=RESOURCE ...] [--music-file CUE=PATH ...] --out OUT_DIR

The x360 command reads the cancelled Xbox 360 prototype's (MS4) data.pak and writes its two new stories as creator
projects and .exp files (x360.py); nr_looks.json is the New Rules portrait catalog's, for the cast's looks.

EPISODE can also be `king-of-diss` or `dancing-queen`, the stories built into res_large.pud, or `king-of-diss-lite`, the
condensed retelling in a Lite Java build (`--lite JAR`); `--downloads DIR` names the .expd folder to learn their
capitals from.

It reads the owner's own game files and writes `.exp` files to OUT_DIR. Nothing it reads or writes belongs in the repo.
`res_large.pud` is New Rules' base pack (`RES_LA~1.005` in its .cab: `expand.exe -F:* CAB DIR`); the X1i jar, if
given, supplies the backgrounds. The episode's music is rendered to MP3 (midi_render.py, ffmpeg on PATH) through Java's
built-in synthesizer, as the J2ME emulator plays it (`java` on PATH), or through a General MIDI soundfont with
`--synth sf2 --soundfont SF2` (Tardy-Slip's TimGM6mb.sf2); `--synth none` removes the music calls.
"""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import newrules  # noqa: E402
import nr_art  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='game', required=True)
    nr = sub.add_parser('newrules', help='a New Rules .expd download')
    nr.add_argument('episodes', nargs='+', type=Path)
    nr.add_argument('--pud', type=Path, required=True)
    nr.add_argument('--x1i', type=Path)
    nr.add_argument('--out', type=Path, required=True)
    nr.add_argument('--library', type=Path,
                    help="an imported SHS library: restores capitals from the downloads paired with its episodes, "
                         "and a story's own smartphone version where it has one")
    nr.add_argument('--synth', choices=('java', 'sf2', 'none'), default='java',
                    help="how the music is rendered: Java's built-in synthesizer, as the J2ME emulator plays it "
                         "(default), the SF2 mixer with --soundfont, or none (music calls removed)")
    nr.add_argument('--soundfont', type=Path, help='a General MIDI .sf2 bank for --synth sf2')
    nr.add_argument('--downloads', type=Path,
                    help="the folder of .expd downloads to learn capitals from, for a built-in story (with --library)")
    nr.add_argument('--lite', type=Path, help="a Lite Java build's jar, for king-of-diss-lite")
    xb = sub.add_parser('x360', help="the cancelled Xbox 360 prototype's new stories (creator projects)")
    xb.add_argument('pak', type=Path, help="the MS4 prototype's data.pak")
    xb.add_argument('--story', choices=('day-of-diss', 'puzzle-test', 'all'), default='all')
    xb.add_argument('--pud', type=Path, required=True)
    xb.add_argument('--x1i', type=Path)
    xb.add_argument('--looks', type=Path, required=True,
                    help='nr_looks.json from the New Rules portrait catalog (the cast\'s looks)')
    xb.add_argument('--music', action='append', default=[], metavar='CUE=RESOURCE',
                    help="play an SHS music resource where the prototype starts a cue (dont_trust_me, chilled...)")
    xb.add_argument('--music-file', action='append', default=[], metavar='CUE=PATH',
                    help="embed the prototype's own audio for a cue (a WAV or MP3); a cue with a CUE_loop file plays "
                         "once and runs into that loop (dont_trust_me + dont_trust_me_loop)")
    xb.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    if args.game == 'x360':
        return translate_x360(args)
    portraits = nr_art.load(args.pud)
    x1i = nr_art.load(args.x1i) if args.x1i else None
    art = nr_art.Art(portraits, x1i)
    hires_art = nr_art.Art(x1i, x1i) if x1i is not None else None      # the second, HD-sized portrait set
    music = None
    if args.synth == 'sf2' and not args.soundfont:
        parser.error('--synth sf2 needs --soundfont')
    if args.synth != 'none':
        import midi_render
        bank, rendered = midi_render.SoundFont(args.soundfont.read_bytes()) if args.synth == 'sf2' else None, {}

        def music(index):
            if index not in rendered:
                data = portraits[newrules.music_resource(index)]
                samples = (midi_render.render(midi_render.parse_midi(data), bank) if bank is not None
                           else midi_render.render_java(data))
                rendered[index] = midi_render.mp3(samples)
            return rendered[index]
    for path in args.episodes:
        downloads, twin, twin_files, full = args.downloads, None, (), None
        if str(path) == 'king-of-diss':
            episode = newrules.read_builtin(portraits)
        elif str(path) == 'dancing-queen':
            episode = newrules.read_dancing_queen(portraits)
            twin_files = (DANCING_QUEEN_TWIN,)
        elif str(path) == 'king-of-diss-lite':
            if not args.lite:
                parser.error('king-of-diss-lite needs --lite, a Lite Java build')
            episode = newrules.read_lite(nr_art.load(args.lite))
            full = newrules.read_builtin(portraits)         # whose expressions and voice colours it borrows
        else:
            episode = newrules.read_expd(path.read_bytes())
            downloads, twin = path.parent, path.name
        dictionary = exact = None
        titles = []
        games = []
        if args.library and downloads:
            import casing
            import pairs
            dictionary, exact, titles = casing.learn_from_library(downloads, args.library, twin_of=twin,
                                                                  twin_files=twin_files)
            if twin is not None:
                games = pairs.twin_word_games(downloads, args.library, twin)
        data, report = newrules.translate(episode, art, music=music, casing_dictionary=dictionary, casing_exact=exact,
                                          twin_games=games, casing_titles=titles, hires_art=hires_art,
                                          borrow_from=full)
        target = args.out / f'NR_{episode.download_id:02d}_{safe(episode.title)}.exp'
        target.write_bytes(data)
        print(f'{path.name}: {episode.title!r} -> {target} ({len(data) // 1024} KB, {report.looks} looks, '
              f'{report.music} tracks, {report.notices} notices, {report.word_games} word games'
              + (f', library calls {report.library_games}' if report.library_games else '')
              + (f', {report.borrowed} expressions from {full.title}' if full is not None else '') + ')')
        if report.unmapped:
            print('  unmapped services (removed):', dict(sorted(report.unmapped.items())))
        if report.unknown:
            review = target.with_suffix('.casing-review.txt')
            review.write_text(''.join(f'{count}\t{word}\n' for word, count in report.unknown.most_common()),
                              encoding='utf-8')
            print(f'  {len(report.unknown)} words left lowercase for review: {review.name}')


def translate_x360(args):
    """Writes each story's .expproj (editable in the creator) and its exported .exp."""
    import json
    from exp_runtime.creator import export_project, save_project
    import x360
    proto = x360.Prototype(args.pak.read_bytes())
    art = nr_art.Art(nr_art.load(args.pud), nr_art.load(args.x1i) if args.x1i else None)
    hires_art = nr_art.Art(nr_art.load(args.x1i), nr_art.load(args.x1i)) if args.x1i else None
    looks = json.loads(args.looks.read_text(encoding='utf-8'))
    music = {}
    for item in args.music:
        cue, _, resource = item.partition('=')
        music[cue] = int(resource)
    music_files = {}
    for item in args.music_file:
        cue, _, path = item.partition('=')
        music_files[cue] = Path(path).read_bytes()
    names = list(x360.STORIES) if args.story == 'all' else [args.story]
    for name in names:
        story = x360.STORIES[name]
        project = x360.translate(proto, story, art, hires_art, looks, music, music_files)
        stem = args.out / f'X360_{story.episode_id:02d}_{safe(story.title)}'
        save_project(project, stem.with_suffix('.expproj'))
        export_project(project, stem.with_suffix('.exp'))
        kinds = {}
        for node in project.nodes:
            kinds[node.kind] = kinds.get(node.kind, 0) + 1
        print(f'{name}: {story.title!r} -> {stem}.exp ({stem.with_suffix(".exp").stat().st_size // 1024} KB, '
              f'{len(project.nodes)} nodes: {dict(sorted(kinds.items()))})')


# Dancing Queen's smartphone version, Homecoming Queen, as a library holds it: the capitals it learns from.
DANCING_QUEEN_TWIN = 'Dancing_Queen.exp'


def safe(title):
    return ''.join(c if c.isalnum() else '_' for c in title).strip('_')


if __name__ == '__main__':
    main()
