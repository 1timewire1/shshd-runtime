"""Desktop entry point and headless project export command."""
import argparse
from pathlib import Path

from exp_runtime.exp import ContentError
from .compiler import export_project, export_native_slot
from .model import load_project, save_project


def main(argv=None):
    parser = argparse.ArgumentParser(description='EXP Runtime episode creator')
    parser.add_argument('project', nargs='?', type=Path, help='Editable .expproj document')
    parser.add_argument('--import-exp', type=Path, help='Import an EXP; save to the project argument')
    parser.add_argument('--language', choices=('en', 'fr', 'it', 'de', 'es'), help='Story language for export')
    parser.add_argument('--smoke-test', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--export', type=Path, help='Compile a project without starting the GUI')
    parser.add_argument('--native-slot', type=Path, help='With --export, retain this original EXP catalog identity')
    parser.add_argument('--preview', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--library', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--game', choices=('shs', 'cod'), default='shs', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
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
                parser.error('The visual editor requires exp-runtime[creator] or exp-runtime-creator[desktop]')
            raise
        launch(args.project)
    except (ContentError, OSError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
