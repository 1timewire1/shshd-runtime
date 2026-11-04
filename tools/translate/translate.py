"""Translate other SHS games' episodes into shshd-runtime `.exp` files (docs/NEW_RULES.md, docs/X360.md).

    python tools/translate/translate.py newrules EPISODE.expd --pud RES_LARGE_PUD [--x1i X1I_JAR]
        [--synth java|sf2|none] [--soundfont SF2] [--library LIB] --out OUT_DIR
    python tools/translate/translate.py x360 DATA_PAK --pud RES_LARGE_PUD [--x1i X1I_JAR] --looks NR_LOOKS_JSON
        [--story day-of-diss|puzzle-test|all] [--music CUE=RESOURCE ...] [--music-file CUE=PATH ...] --out OUT_DIR

The x360 command reads the cancelled Xbox 360 prototype's (MS4) data.pak and writes its two new stories as creator
projects and .exp files (x360.py); nr_looks.json is the New Rules portrait catalog's, for the cast's looks.

    python tools/translate/translate.py shs11 --art IT_480X800_JAR --english N73_JAR --sounds KG800_JAR --out OUT_DIR
    python tools/translate/translate.py shs11 --english N73_JAR --story "The New Girl" --twin THE_NEW_GIRL_EXP --out OUT_DIR

The shs11 command writes SHS '11's addon (shs11.py): every background, look and interface picture, and its music.

EPISODE can also be `king-of-diss` or `dancing-queen`, the stories built into res_large.pud, or `king-of-diss-lite`, the
condensed retelling in a Lite Java build (`--lite JAR`); `--downloads DIR` names the .expd folder to learn their
capitals from. `addon` writes the New Rules addon (every background, the music and the frame backdrop, which the
translations share, and New Rules' minigame library and the arena's art); with `--addon ADDON.exp` the episodes leave
those out and declare the addon instead. `--arena` plays their minigames in New Rules' own arena where the player has it.

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
    nr.add_argument('--addon', type=Path,
                    help="the New Rules addon (`addon` writes it): the episodes leave out what it holds and declare it")
    nr.add_argument('--arena', action='store_true',
                    help="where the player has New Rules' minigame arena, play the episodes' minigames there (needs "
                         "--addon: the addon holds the minigame library and the arena's art)")
    xb = sub.add_parser('x360', help="the cancelled Xbox 360 prototype's new stories (creator projects)")
    xb.add_argument('pak', type=Path, help="the MS4 prototype's data.pak")
    xb.add_argument('--story', choices=('day-of-diss', 'puzzle-test', 'dating-beth', 'monday-planner', 'all', 'addon'),
                    default='all',
                    help="a story, all of them, or `addon`: the X360 addon (what the stories share, with the arena's "
                         "X360 skin), built from all of them with the same art and music arguments")
    xb.add_argument('--addon', type=Path,
                    help="the X360 addon (`--story addon` writes it): the stories leave out what it holds and declare "
                         "it")
    xb.add_argument('--pud', type=Path, required=True)
    xb.add_argument('--x1i', type=Path)
    xb.add_argument('--looks', type=Path, required=True,
                    help='nr_looks.json from the New Rules portrait catalog (the cast\'s looks)')
    xb.add_argument('--music', action='append', default=[], metavar='CUE=RESOURCE',
                    help="play an SHS music resource where the prototype starts a cue (dont_trust_me, chilled...)")
    xb.add_argument('--music-file', action='append', default=[], metavar='CUE=PATH',
                    help="embed the prototype's own audio for a cue (a WAV or MP3); a cue with a CUE_loop file plays "
                         "once and runs into that loop (dont_trust_me + dont_trust_me_loop)")
    xb.add_argument('--portraits', type=Path,
                    help="a folder of the prototype's characters rendered as SHS HD busts (x360_portrait.py: "
                         "<id>_<emotion>.png); those cast members use them instead of their New Rules looks")
    xb.add_argument('--backgrounds', type=Path,
                    help="a folder of the prototype's own backgrounds (x360_bgshots.py cuts: <location>.jpg, "
                         "<location>_<who>.jpg for a talk); those locations use them instead of New Rules art")
    xb.add_argument('--dbp', type=Path,
                    help="with --story addon: the Diss Practice booth's shots (Additional Resources/x360-dbp-booth: "
                         "the deck, the record, the digits and the practice places) for the arena's X360 skin")
    xb.add_argument('--opening', type=Path,
                    help="with --story addon: Day of Diss's opening stills (Additional Resources/x360-opening)")
    xb.add_argument('--puzzle', type=Path,
                    help="with --story addon: the jewel puzzle's art (Additional Resources/x360-puzzle-booth): its jewels, "
                         'cursor and boards')
    xb.add_argument('--out', type=Path, required=True)
    s11 = sub.add_parser('shs11', help="SHS '11, the J2ME game: its addon (shs11.py) or, with --story, a story (shs11_story.py)")
    s11.add_argument('--art', type=Path, help='a jar with the sharpest art: an Italian 480x800 or 360x640 build')
    s11.add_argument('--english', type=Path, required=True, help='an English 30-script jar, for the cast tables: N73')
    s11.add_argument('--sounds', type=Path, help='a jar with all 11 tracks, for the music: KG800')
    s11.add_argument('--story', help="with --twin: a story to translate instead of the addon, by title: 'The New Girl', 'Best Party Ever', 'Foreign Exchange', 'Lost Recipe' or 'Secret Ingredient'")
    s11.add_argument('--twin', type=Path, help="the story's smartphone .exp, for the minigames' words")
    s11.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    if args.game == 'x360':
        return translate_x360(args)
    if args.game == 'shs11':
        return translate_shs11(args)
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
    addon = None
    if args.arena and not args.addon:
        parser.error('--arena needs --addon')
    if args.addon:
        from exp_runtime.exp import ExpArchive
        addon = set(ExpArchive(args.addon.read_bytes()).entries)
    for path in args.episodes:
        downloads, twin, twin_files, full = args.downloads, None, (), None
        if str(path) == 'addon':
            data = newrules.build_addon(art, music, library=newrules.decode_program(portraits[newrules.LIBRARY]),
                                        arena_source=x1i)
            target = args.out / f'{ADDON_FILE}.exp'
            target.write_bytes(data)
            print(f'addon: {newrules.ADDON_TITLE!r} revision {newrules.ADDON_REVISION} -> {target} '
                  f'({len(data) // 1024} KB)')
            continue
        if str(path) == 'king-of-diss':
            episode = newrules.read_builtin(portraits, linked=args.arena)
        elif str(path) == 'dancing-queen':
            episode = newrules.read_dancing_queen(portraits, linked=args.arena)
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
                                          borrow_from=full, addon=addon, arena=args.arena)
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


def translate_shs11(args):
    """Writes SHS '11's addon, or with --story, that story."""
    import shs11
    if args.story:
        import shs11_story
        if not args.twin:
            raise SystemExit('--story needs --twin')
        name, data = shs11_story.build(shs11.jar_file(args.english), args.story, args.twin)
        (args.out / name).write_bytes(data)
        print(f'{args.out / name}: {len(data) / 1024:.0f} KB')
        return 0
    if not args.art or not args.sounds:
        raise SystemExit('the addon needs --art and --sounds')
    data, spec = shs11.build_addon(shs11.jar_file(args.art), shs11.jar_file(args.english), shs11.jar_file(args.sounds))
    path = args.out / 'S11_Addon.exp'
    path.write_bytes(data)
    print(f"{path}: {len(data) / 1048576:.1f} MB, {sum(map(len, spec['backgrounds'].values()))} backgrounds, {len(spec['looks'])} looks, "
          f"{len(spec['parts'])} loose parts, {len(spec['interface'])} interface pictures, {len(spec['music'])} tracks")
    return 0


def translate_x360(args):
    """Writes each story's .expproj (editable in the creator) and its exported .exp; with `--story addon`, the X360
    addon instead."""
    import json
    from exp_runtime.creator import compile_project, save_project
    from exp_runtime.exp import ExpArchive
    import x360
    if args.addon and args.story == 'addon':
        raise SystemExit('--addon is for the stories; --story addon writes the addon')
    if args.story == 'addon' and not args.opening:
        raise SystemExit("--story addon needs --opening: Day of Diss's opening reads its stills from the addon")
    addon = ExpArchive(args.addon.read_bytes()) if args.addon else None
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
    names = list(x360.STORIES) if args.story in ('all', 'addon') else [args.story]
    stories = []
    for name in names:
        story = x360.STORIES[name]
        rendered = x360.rendered_portraits(args.portraits, story) if args.portraits else {}
        backgrounds = x360.scene_backgrounds(args.backgrounds, story) if args.backgrounds else {}
        project = x360.translate(proto, story, art, hires_art, looks, music, music_files, rendered, backgrounds)
        data = compile_project(project)
        if args.story == 'addon':
            stories.append(data)
            continue
        if rendered:
            print(f'{name}: rendered portraits for {", ".join(sorted(rendered))}')
        if backgrounds:
            print(f'{name}: own backgrounds {", ".join(sorted(backgrounds))}')
        left_out = []
        if addon is not None:
            # Checks every resource left out is the addon's own, byte for byte; then the project says it takes those from the addon,
            # so its .expproj re-exports the same and importing the .exp brings them back.
            _, left_out = x360.strip_addon(data, addon, story.addon_revision)
            x360.use_addon(project, left_out, story.addon_revision)
            data = compile_project(project)
        stem = args.out / f'X360_{story.episode_id:02d}_{safe(story.title)}'
        save_project(project, stem.with_suffix('.expproj'))
        stem.with_suffix('.exp').write_bytes(data)
        kinds = {}
        for node in project.nodes:
            kinds[node.kind] = kinds.get(node.kind, 0) + 1
        print(f'{name}: {story.title!r} -> {stem}.exp ({len(data) // 1024} KB, {len(project.nodes)} nodes: '
              f'{dict(sorted(kinds.items()))}' + (f', {len(left_out)} resources from the addon' if addon else '') + ')')
    if args.story == 'addon':
        import x360_arena_art
        skin = x360_arena_art.build_skin(proto.files, nr_art.load(args.x1i) if args.x1i else None,
                                         pcm_wav=x360.pcm_wav, booth_folder=args.dbp, puzzle_folder=args.puzzle)
        opening = x360_arena_art.opening(proto.files, x360.pcm_wav, args.opening)
        data = x360.build_addon(stories, {**skin, **opening, **x360.ms3_portraits(args.portraits)})
        target = args.out / f'{x360.ADDON_FILE}.exp'
        target.write_bytes(data)
        print(f'addon: {x360.ADDON_TITLE!r} revision {x360.ADDON_REVISION} -> {target} ({len(data) // 1024} KB, '
              f'{len(ExpArchive(data).entries)} resources, {len(skin)} of them the arena skin)')


# Dancing Queen's smartphone version, Homecoming Queen, as a library holds it: the capitals it learns from.
DANCING_QUEEN_TWIN = 'Dancing_Queen.exp'
ADDON_FILE = 'NR_Addon_New_Rules'               # `newrules addon` writes OUT/NR_Addon_New_Rules.exp


def safe(title):
    return ''.join(c if c.isalnum() else '_' for c in title).strip('_')


if __name__ == '__main__':
    main()
