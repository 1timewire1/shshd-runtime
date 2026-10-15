"""Play an episode through repeatedly, varying every choice and mini-game result, to fill in its Decision Tree."""
import argparse
from pathlib import Path

from exp_runtime.tree_explorer import explore_library


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, required=True, help='the library whose tree and warp saves are written')
    parser.add_argument('--episode', help='episode id (default: the built-in Football Star)')
    parser.add_argument('--runs', type=int, default=60, help='most playthroughs to make (default 60)')
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--reset', action='store_true', help='forget the existing tree and warp saves first')
    args = parser.parse_args()

    def report(playthrough, explorer):
        nodes = len(list(explorer.view.nodes()))
        status = 'finished' if playthrough.finished else f'STOPPED {playthrough.error}'.strip()
        print(f'run {playthrough.number:3}: {playthrough.screens:5} screens, {len(playthrough.decisions):3} decisions, '
              f'+{playthrough.new_nodes} scenes (tree {nodes}), +{playthrough.new_alternatives} new results, {status}')

    explorer, runs = explore_library(args.library, args.episode, runs=args.runs, seed=args.seed, reset=args.reset,
                                     report=report)
    left = explorer.unexplored()
    print(f'\n{len(runs)} playthroughs, {len(list(explorer.view.nodes()))} scenes in the tree, '
          f'{sum(len(counts) for counts in explorer.taken.values())} results taken at {len(explorer.taken)} decisions')
    print('every alternative taken at least once' if not left else
          f'{len(left)} decisions still have untried alternatives: {left}')
    return any(run.error for run in runs)


if __name__ == '__main__':
    raise SystemExit(main())
