"""Desktop entry point and headless project export command."""
import argparse
from pathlib import Path

from exp_runtime.exp import ContentError
from .compiler import export_project, export_native_slot
from .model import load_project, save_project


def attach_std_streams():
    """A windowed Windows build starts without Python's standard streams even when its parent hands it pipes (an MCP client,
    the media worker's caller): open them from the process's own handles, so stdio works as from a console. Elsewhere, and
    with streams already there, nothing changes."""
    import sys
    if sys.platform != 'win32' or (sys.stdin is not None and sys.stdout is not None):
        return
    import ctypes
    import io
    import msvcrt
    import os
    kernel = ctypes.windll.kernel32
    for which, name, mode in ((-10, 'stdin', 'rb'), (-11, 'stdout', 'wb'), (-12, 'stderr', 'wb')):
        if getattr(sys, name) is not None:
            continue
        handle = kernel.GetStdHandle(which)
        if handle in (0, -1, None):
            continue
        try:
            raw = os.fdopen(msvcrt.open_osfhandle(handle, os.O_RDONLY if mode == 'rb' else os.O_WRONLY), mode, buffering=0)
        except OSError:
            continue
        buffered = io.BufferedReader(raw) if mode == 'rb' else io.BufferedWriter(raw)
        setattr(sys, name, io.TextIOWrapper(buffered, encoding='utf-8', line_buffering=mode == 'wb'))


def main(argv=None):
    parser = argparse.ArgumentParser(description='SHSHD Runtime episode creator')
    parser.add_argument('project', nargs='?', type=Path, help='Editable .expproj document')
    parser.add_argument('--import-exp', type=Path, help='Import an EXP; save to the project argument')
    parser.add_argument('--language', choices=('en', 'fr', 'it', 'de', 'es'), help='Story language for export')
    parser.add_argument('--smoke-test', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--export', type=Path, help='Compile a project without starting the GUI')
    parser.add_argument('--pack-addons', action='store_true',
                        help='with --native-slot and --library: pack the pictures and sounds the project takes from add-ons into the .exp')
    parser.add_argument('--native-slot', type=Path, help='With --export, retain this original EXP catalog identity')
    parser.add_argument('--preview', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--library', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--game', choices=('shs', 'cod'), default='shs', help=argparse.SUPPRESS)
    # shshd-runtime (owner, 2026-11-17, decision 5): the standalone Creator is also its MCP server, `--mcp --workspace DIR`.
    parser.add_argument('--mcp', action='store_true', help='Run the MCP server over stdio for --workspace (no window)')
    parser.add_argument('--workspace', type=Path, help='With --mcp, the folder of projects and assets it may read and write')
    parser.add_argument('--media-worker', action='store_true', help=argparse.SUPPRESS)       # media.worker's child, frozen
    parser.add_argument('--data-folder', action='store_true', help=argparse.SUPPRESS)        # the packaged smoke test's check
    args = parser.parse_args(argv)
    try:
        if args.mcp:
            if not args.workspace:
                parser.error('--mcp requires --workspace')
            attach_std_streams()
            from .mcp_server import main as mcp_main
            mcp_main(['--workspace', str(args.workspace)])
            return
        if args.media_worker:
            attach_std_streams()
            from .media import main as media_main
            media_main()
            return
        if args.data_folder:
            # Where this build looks for the player's data and library: the player's own folder (one app name, both apps).
            import json
            import sys
            from exp_runtime.launcher import default_library, user_data_directory
            attach_std_streams()
            sys.stdout.write(json.dumps(dict(data=str(user_data_directory()), library=str(default_library(args.game)))) + chr(10))
            sys.stdout.flush()
            return
        if args.smoke_test:
            from PySide6.QtWidgets import QApplication
            from .ui import Editor
            from .compiler import compile_project
            app = QApplication.instance() or QApplication([])
            editor = Editor(discover_library=False); editor.show(); app.processEvents()
            assert compile_project(editor.project)
            assert not editor.grab().isNull()
            editor.close(); app.processEvents()
            return
        if args.import_exp:
            if not args.project: parser.error('--import-exp requires an output .expproj path')
            from .native import import_exp
            if args.project.exists(): parser.error('Import destination already exists')
            save_project(import_exp(args.import_exp.read_bytes(), game=args.game), args.project)
            return
        if args.export:
            if not args.project:
                parser.error('--export requires an .expproj document')
            project = load_project(args.project)
            if args.language: project.language = args.language
            if args.native_slot:
                if args.pack_addons:
                    from exp_runtime.content import ContentLibrary
                    if not args.library:
                        parser.error('--pack-addons requires --library')
                    with ContentLibrary(args.library) as library:
                        export_native_slot(project, args.native_slot, args.export, pack_from=library)
                else:
                    export_native_slot(project, args.native_slot, args.export)
            else:
                export_project(project, args.export)
            return
        if args.native_slot:
            parser.error('--native-slot requires --export')
        if args.preview:
            if not args.library:
                parser.error('--preview requires --library')
            from .preview import play_preview
            play_preview(args.preview, args.library, args.game)
            return
        try:
            from .ui import launch
        except ModuleNotFoundError as error:
            if error.name and error.name.startswith('PySide6'):
                parser.error('The visual editor requires shshd-runtime[creator] or shshd-runtime-creator[desktop]')
            raise
        launch(args.project)
    except (ContentError, OSError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
