"""Translate other SHS games' episodes into shshd-runtime `.exp` files (reference/Other Games/docs/TRANSLATOR_PLAN.md).

    python tools/translate/translate.py newrules EPISODE.expd --pud RES_LARGE_PUD [--x1i X1I_JAR]
        [--soundfont SF2] [--library LIB] --out OUT_DIR

EPISODE can also be `king-of-diss`, the story built into res_large.pud, or `king-of-diss-lite`, the condensed retelling
in a Lite Java build (`--lite JAR`); `--downloads DIR` names the .expd folder to learn their capitals from.

It reads the owner's own game files and writes `.exp` files to OUT_DIR. Nothing it reads or writes belongs in the repo.
`res_large.pud` is New Rules' base pack (`RES_LA~1.005` in its .cab: `expand.exe -F:* CAB DIR`); the X1i jar, if
given, supplies the backgrounds. With a General MIDI soundfont (Tardy-Slip's TimGM6mb.sf2) and ffmpeg on PATH, the
episode's music is rendered to MP3 (midi_render.py); without one, music calls are removed.
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
    nr.add_argument('--soundfont', type=Path, help='a General MIDI .sf2 bank to render the music with')
    nr.add_argument('--downloads', type=Path,
                    help="the folder of .expd downloads to learn capitals from, for a built-in story (with --library)")
    nr.add_argument('--lite', type=Path, help="a Lite Java build's jar, for king-of-diss-lite")
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    portraits = nr_art.load(args.pud)
    x1i = nr_art.load(args.x1i) if args.x1i else None
    art = nr_art.Art(portraits, x1i)
    hires_art = nr_art.Art(x1i, x1i) if x1i is not None else None      # the second, HD-sized portrait set
    music = None
    if args.soundfont:
        import midi_render
        bank, rendered = midi_render.SoundFont(args.soundfont.read_bytes()), {}

        def music(index):
            if index not in rendered:
                song = midi_render.parse_midi(portraits[newrules.music_resource(index)])
                rendered[index] = midi_render.mp3(midi_render.render(song, bank))
            return rendered[index]
    for path in args.episodes:
        downloads, twin = args.downloads, None
        if str(path) == 'king-of-diss':
            episode = newrules.read_builtin(portraits)
        elif str(path) == 'king-of-diss-lite':
            if not args.lite:
                parser.error('king-of-diss-lite needs --lite, a Lite Java build')
            episode = newrules.read_lite(nr_art.load(args.lite))
        else:
            episode = newrules.read_expd(path.read_bytes())
            downloads, twin = path.parent, path.name
        dictionary = exact = None
        titles = []
        games = []
        if args.library and downloads:
            import casing
            import pairs
            dictionary, exact, titles = casing.learn_from_library(downloads, args.library, twin_of=twin)
            if twin is not None:
                games = pairs.twin_word_games(downloads, args.library, twin)
        data, report = newrules.translate(episode, art, music=music, casing_dictionary=dictionary, casing_exact=exact,
                                          twin_games=games, casing_titles=titles, hires_art=hires_art)
        target = args.out / f'NR_{episode.download_id:02d}_{safe(episode.title)}.exp'
        target.write_bytes(data)
        print(f'{path.name}: {episode.title!r} -> {target} ({len(data) // 1024} KB, {report.looks} looks, '
              f'{report.music} tracks, {report.notices} notices, {report.word_games} word games'
              + (f', library calls {report.library_games}' if report.library_games else '') + ')')
        if report.unmapped:
            print('  unmapped services (removed):', dict(sorted(report.unmapped.items())))
        if report.unknown:
            review = target.with_suffix('.casing-review.txt')
            review.write_text(''.join(f'{count}\t{word}\n' for word, count in report.unknown.most_common()),
                              encoding='utf-8')
            print(f'  {len(report.unknown)} words left lowercase for review: {review.name}')


def safe(title):
    return ''.join(c if c.isalnum() else '_' for c in title).strip('_')


if __name__ == '__main__':
    main()
