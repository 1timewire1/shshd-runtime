"""Desktop entry point and headless project export command."""
import argparse
from pathlib import Path

from exp_runtime.exp import ContentError
from .compiler import export_project, export_native_slot
from .model import load_project


def main(argv=None):
    parser = argparse.ArgumentParser(description='EXP Runtime episode creator')
    parser.add_argument('project', nargs='?', type=Path, help='Editable .expproj document')
    parser.add_argument('--export', type=Path, help='Compile a project without starting the GUI')
    parser.add_argument('--native-slot', type=Path, help='With --export, retain this original EXP catalog identity')
    parser.add_argument('--preview', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--library', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--game', choices=('shs', 'cod'), default='shs', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        if args.export:
            if not args.project:
                parser.error('--export requires an .expproj document')
            project = load_project(args.project)
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
