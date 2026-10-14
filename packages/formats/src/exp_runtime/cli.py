"""Import, inspect and launch player-supplied EXP game content."""

import argparse
from dataclasses import asdict
from importlib.util import find_spec
import json
import logging
import sys
import tempfile

from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="exp-tool",
        description="Inspect EXP files and play SHS or Cause of Death with your own game data.",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (-v for INFO, -vv for DEBUG).",
    )
    subparsers = parser.add_subparsers(dest="command")

    inspect_parser = subparsers.add_parser('inspect', help='Inspect an EXP without installing the engine or games.')
    inspect_parser.add_argument('archive', type=Path)
    extract_parser = subparsers.add_parser('extract', help='Extract EXP resources by numeric ID into a new directory.')
    extract_parser.add_argument('archive', type=Path)
    extract_parser.add_argument('--output', type=Path, required=True)

    trace_parser = subparsers.add_parser(
        "trace", help="Execute KiWi to the first pending action and print a JSON trace.",
    )
    trace_parser.add_argument("archive", type=Path, help="Path to the .exp archive.")
    trace_parser.add_argument("--max-steps", type=int, default=100_000)
    trace_parser.add_argument("--max-events", type=int, default=10_000)
    trace_parser.add_argument('--game', choices=('shs', 'cod'), default='shs', help='Native host profile (default: shs).')

    import_parser = subparsers.add_parser("import", help="Create a local library from your APK or IPA and episode files.")
    source = import_parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--apk", type=Path, help="Your SHS Android 1.0.9 APK.")
    source.add_argument("--ipa", type=Path, help="Your SHS or Cause of Death IPA with compatible game assets.")
    import_parser.add_argument('--game', choices=('shs', 'cod'), help='Require assets for this game (otherwise detected).')
    import_parser.add_argument("--music-apk", type=Path,
                               help="Optional Android 1.0.9 APK supplying missing IPA music.")
    import_parser.add_argument("--episodes", type=Path, nargs="+", action="extend", default=[],
                               help="EXP files, episode ZIPs/RARs or directories; subfolders are scanned recursively.")
    import_parser.add_argument("--library", type=Path, required=True,
                               help="New library directory for this game.")

    list_parser = subparsers.add_parser("list", help="List episodes in a local content library.")
    list_parser.add_argument("--library", type=Path, default=Path(".shs-library"))
    from .languages import TITLE_LANGUAGES
    list_parser.add_argument('--title-language', choices=TITLE_LANGUAGES,
                             help='Episode title language; defaults to the library preference. Does not translate story text.')

    music_parser = subparsers.add_parser("add-music", help="Add missing music to an existing IPA library.")
    music_parser.add_argument("--apk", type=Path, required=True, help="Your SHS Android 1.0.9 APK.")
    music_parser.add_argument("--library", type=Path, required=True, help="Existing IPA library.")

    play_parser = subparsers.add_parser("play", help="Open the main menu, or start a selected episode.")
    play_parser.add_argument("--library", type=Path, help="Content library; defaults to the existing local library or user application data.")
    play_parser.add_argument("--episode", help="Start directly: unique ID prefix, filename, or title from list.")
    saves = play_parser.add_mutually_exclusive_group()
    saves.add_argument("--resume", action="store_true", help="Load this episode's local save slot.")
    saves.add_argument("--load", type=Path, help="Load a specific runtime JSON save.")
    play_parser.add_argument("--no-audio", action="store_true")
    play_parser.add_argument('--game', choices=('shs', 'cod'), help='Open this game directly instead of the chooser.')

    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Configure logging
    log_level = logging.WARNING
    if args.verbose >= 2:
        log_level = logging.DEBUG
    elif args.verbose >= 1:
        log_level = logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    if args.command in ('inspect', 'extract'):
        from .exp import ContentError, ExpArchive
        try:
            archive = ExpArchive(args.archive.read_bytes())
            if args.command == 'inspect':
                result = dict(resources=sorted(archive.entries), scripts=sorted(archive.programs()))
                if 1 in archive.entries:
                    result['metadata'] = asdict(archive.metadata())
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                destination = args.output
                if destination.exists():
                    raise ContentError(f'Output already exists: {destination}; choose a new directory')
                destination.parent.mkdir(parents=True, exist_ok=True)
                # A corrupt record must not leave a partial extraction. IDs
                # are validated integers; original archive paths are not used.
                with tempfile.TemporaryDirectory(dir=destination.parent, prefix='.exp-extract-') as temporary:
                    staged = Path(temporary) / 'resources'
                    staged.mkdir()
                    for resource in archive.entries:
                        (staged / f'{resource}.bin').write_bytes(archive.read(resource))
                    staged.rename(destination)
                print(f'Extracted {len(archive.entries)} resources into {destination}')
        except (ContentError, OSError) as error:
            parser.error(str(error))
        return

    if args.command in ('import', 'list', 'play', 'add-music', 'trace'):
        if find_spec('exp_runtime.engine') is None:
            parser.error('This command needs the engine and a game adapter. '
                         'Install "exp-runtime[engine,shs]" or "exp-runtime[engine,cod]".')
    if args.command == 'play' and find_spec('exp_runtime.application') is None:
        parser.error('The player is not installed. Install "exp-runtime[player]".')

    if args.command in ("import", "list", "play", "add-music"):
        from .content import ContentError, ContentLibrary, import_game
        from .runtime import SaveError
        from .vm import VMError

        try:
            if args.command == "import":
                manifest = import_game(args.apk or args.ipa, args.episodes, args.library,
                                       music_apk=args.music_apk, game=args.game)
                print(f"Imported {len(manifest['episodes'])} episodes into {args.library}")
                return
            if args.command == 'play':
                if (args.load or args.resume) and not args.episode:
                    parser.error('--load and --resume require --episode; omit them to use the main menu')
                try:
                    from .application import Application
                except ModuleNotFoundError as error:
                    if error.name != 'pygame':
                        raise
                    parser.error('Desktop support is not installed. Run uv sync --extra desktop '
                                 'or install the package with its [desktop] extra.')
                app = Application(args.library, audio=not args.no_audio, game_key=args.game)
                try:
                    if args.episode:
                        if not app.library:
                            raise ContentError(app.message or 'Import your APK or IPA before selecting an episode')
                        app.selected = app.library.select(args.episode)['id']
                        app.start(resume=args.resume, load_path=args.load)
                except Exception:
                    app.close()
                    raise
                app.run()
                return
            with ContentLibrary(args.library) as library:
                if args.command == 'add-music':
                    count = library.add_music_apk(args.apk)
                    print(f'Added {count} missing music tracks.' if count else 'No missing music tracks to add.')
                    return
                library.ensure_builtin_episodes()
                if args.command == "list":
                    from .menu import MenuState
                    state = MenuState(library)
                    if args.title_language is not None:
                        state.title_language = args.title_language
                    for record in library.episodes:
                        print(f"{record['id'][:12]}  {state.title(record)}  ({record['name']})")
                    return
        except (ContentError, SaveError, VMError, OSError) as error:
            parser.error(str(error))

    elif args.command == "trace":
        from .trace import trace_archive

        try:
            result = trace_archive(args.archive, max_steps=args.max_steps, max_events=args.max_events, game=args.game)
        except (ValueError, OSError) as error:
            parser.error(str(error))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if result["status"] in ("vm_error", "missing_script"):
            sys.exit(1)

    else:
        parser.print_help()
        sys.exit(1)
