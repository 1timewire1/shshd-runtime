"""Plays a translated X360 story (x360.py) down many answer paths in the production Session and checks it.

    python tools/translate/x360_check.py STORY.expproj [--runs 400] [--seed 1]

The .exp beside the .expproj is played; the .expproj says which lines exist. Each run answers every choice at
random among its enabled options (seeded, so a run can be replayed), until the episode exits. Reported: runs that
stop anywhere but the episode exit (a VM error, an unhandled panel, the step limit), the authored dialogue/message/
notice texts no run showed, and how many runs reached each ending text.
"""
import argparse
from collections import Counter
from pathlib import Path
import random
import sys

from exp_runtime.creator import load_project

sys.path.insert(0, str(Path(__file__).resolve().parent))
from playthrough import session  # noqa: E402


def run(data, rng, limit=20000, taken=None):
    """(events, outcome): events are ('line'|'choice'|'message', text), outcome 'exit' or why it stopped. With
    `taken` (a set of (choice text, answer) pairs), an answer no earlier run took is preferred."""
    s, events = session(data), []
    s.engine.random.state = 1
    action = s.advance()
    for _ in range(limit):
        while s.transitioning:
            action = s.tick(s.engine.scene_transition.duration_ms)
        if action is None or s.pending is None:
            return events, 'stopped without a pending action'
        kind, details = action.name, action.details
        if kind == 'episode_exit':
            return events, 'exit'
        if kind == 'dialogue':
            events.append(('line', details.get('text')))
            if not s.engine.dialogue_animation.complete:
                s.answer(); s.tick(2000)
            action = s.answer()
        elif kind == 'choice':
            events.append(('choice', details.get('text')))
            if not s.choice_ready:
                s.tick(250)
            enabled = [i for i, on in enumerate(details['enabled']) if on]
            if not enabled:
                return events, f'choice with no enabled option: {details.get("text")!r}'
            fresh = [i for i in enabled if taken is not None and (details.get('text'), details['options'][i]) not in taken]
            pick = rng.choice(fresh or enabled)
            if taken is not None:
                taken.add((details.get('text'), details['options'][pick]))
            events.append(('answer', details['options'][pick]))
            action = s.answer(pick)
        elif kind == 'message_panel':
            panel = s.engine.message_panel
            events.append(('message', panel.text))
            action = s.tick(4000)
            if s.pending is not None and s.pending.name == kind:
                action = s.answer()
        else:
            return events, f'stopped at {kind}'
        if action is None:
            action = s.pending
    return events, 'step limit'


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('project', type=Path)
    parser.add_argument('--runs', type=int, default=400)
    parser.add_argument('--seed', type=int, default=1)
    args = parser.parse_args()
    project = load_project(args.project)
    data = args.project.with_suffix('.exp').read_bytes()
    authored = Counter(n.text for n in project.nodes if n.kind in ('dialogue', 'message') and n.text)
    options = Counter(o.text for n in project.nodes if n.kind == 'choice' for o in n.options)
    seen, answered, outcomes, endings, problems, taken = set(), set(), Counter(), Counter(), [], set()
    for i in range(args.runs):
        rng = random.Random(args.seed * 100003 + i)
        # Half the runs prefer untaken answers (coverage); the rest are plain random (deep combinations).
        events, outcome = run(data, rng, taken=taken if i % 2 == 0 else None)
        outcomes[outcome] += 1
        seen.update(text for kind, text in events if kind in ('line', 'message'))
        answered.update(text for kind, text in events if kind == 'answer')
        last = [text for kind, text in events if kind in ('line', 'message')][-1:]
        endings[last[0] if last else None] += 1
        if outcome != 'exit':
            problems.append((args.seed * 100003 + i, outcome, events[-3:]))
    unseen = [t for t in authored if t not in seen]
    unanswered = [t for t in options if t not in answered]
    print(f'{args.runs} runs: {dict(outcomes)}')
    print(f'lines/messages shown: {len(set(authored) & seen)} of {len(authored)}; '
          f'answers taken: {len(set(options) & answered)} of {len(options)}')
    for text in unseen:
        print('  never shown:', text[:100])
    for text in unanswered:
        print('  never answered:', text[:100])
    for text, count in endings.most_common():
        print(f'  ending x{count}: {str(text)[:90]}')
    for seed, outcome, tail in problems[:5]:
        print(f'  run seed {seed}: {outcome}; last events {tail}')
    return 1 if problems or unseen else 0


if __name__ == '__main__':
    sys.exit(main())
