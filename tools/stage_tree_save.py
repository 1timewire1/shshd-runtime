"""Copy an iOS app save and replace the copy's tree_nodes.txt with a tree of ours (from `explore_tree.py`).

The original folder is never touched. The copy keeps every file, including the saved games (`tree_<serial>.sav`), so the
scenes the saved tree already had keep their serials and their saves; scenes only our playthroughs reached are numbered on
from the highest serial and have no saved game. The result is checked against what the app's loader (`DTNode::readFile`)
needs before it is written: a file it cannot read makes the app delete the game's main save.
"""
import argparse
import json
from pathlib import Path
import shutil

from exp_runtime import native_tree
from exp_runtime.dtview_faceplace import DTView


def stage(source, tree_file, destination):
    if destination.exists():
        raise SystemExit(f'{destination} already exists; choose a new folder')
    dumps = list(source.glob('**/Library/Caches/tree_nodes.txt'))
    if len(dumps) != 1:
        raise SystemExit(f'Expected one Library/Caches/tree_nodes.txt under {source}, found {len(dumps)}')
    real = native_tree.parse(dumps[0].read_text(encoding='ascii'))
    tree = DTView.from_dict(json.loads(tree_file.read_text(encoding='utf-8')))
    made, report = native_tree.export(real, tree)
    problems = native_tree.check(made)
    if problems:
        raise SystemExit('The app could not load the tree:\n' + '\n'.join(problems[:10]))
    shutil.copytree(source, destination)
    dump = destination / dumps[0].relative_to(source)
    with dump.open('w', encoding='ascii', newline='\n') as stream:
        stream.write(native_tree.format_nodes(made))
    last = max(node.serial for node in real.values())
    (destination / 'STAGED.txt').write_text(
        f'A copy of "{source.name}" whose Library/Caches/tree_nodes.txt is replaced by a tree built by simulated '
        f'playthroughs: {report["nodes"]} nodes, {report["new_scenes"]} of them scenes the original {len(real)}-scene '
        f'tree did not have.\n'
        f'Serials 1-{last} are the original scenes and keep their saved games (tree_<serial>.sav); serials above {last} '
        f'have none, so tapping those scenes cannot load a game.\n'
        f'{report["left_out"]} branches were left out because the node type has fewer result slots than the simulated '
        f'run used.\n', encoding='utf-8')
    return real, made, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--save', type=Path, required=True, help='the save folder to copy')
    parser.add_argument('--tree', type=Path, required=True, help="the library's dtview_tree.json")
    parser.add_argument('--out', type=Path, required=True, help='the new folder to create')
    args = parser.parse_args()
    real, made, report = stage(args.save, args.tree, args.out)
    print(f'{len(real)} scenes in the save -> {report["nodes"]} nodes in the copy: {report["matched"]} original scenes, '
          f'{report["new_scenes"]} new, {report["left_out"]} branches left out')


if __name__ == '__main__':
    main()
