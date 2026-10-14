"""Optional hints from native word scores or isolated story-choice previews.

These are near-term outcome hints, not a solver for an episode's best ending.
Recognized relationship changes, score notices and per-game answer-feedback
sounds establish outcomes. Arbitrary counters and dialogue words do not.
"""
from copy import deepcopy
from dataclasses import dataclass

from .content import ContentError
from .games import GAMES
from .vm import VMError


# Observed in the supplied SHS and CoD scripts. Unrecognized/localized notices
# stay unknown; ordinary dialogue containing these words is not evidence.
SCORE_NOTICES = frozenset(('Score Up!', 'Detective Score Up!'))
DECISIONS = frozenset(('choice', 'character_picker', 'text_input', 'word_game',
                       'word_grid', 'football', 'finished', 'episode_exit'))
PANELS = frozenset(('dialogue', 'presentation', 'message_panel'))


@dataclass(frozen=True)
class ChoiceHint:
    kind: str  # gain, loss, no_gain, mixed, unknown


def preview_choices(session, *, max_steps=6000, max_panels=48, max_options=16,
                    max_decisions=4, max_branches=192):
    """Compare native outcomes on bounded, isolated runtime copies.

    Immediate feedback takes precedence. For deferred feedback, compare the
    same later answers across every initial option. An option dominates another
    only if it is never worse and is better for at least one continuation.
    Unmatched decisions, unknown services or exhausted budgets remain unknown.
    """
    if session.pending and session.pending.name == 'word_game':
        # Service 71 supplies explicit good/bad answers. Read the current deal's
        # weights, including duplicate labels and its native random order.
        game = session.engine.word_game
        return tuple(ChoiceHint('gain' if weight > 0 else 'loss' if weight < 0 else 'no_gain')
                     for weight in game.weights) if game else ()
    if not session.pending or session.pending.name != 'choice':
        return ()
    if min(max_steps, max_panels, max_options, max_decisions, max_branches) < 1:
        raise ValueError('Preview budgets must be positive')
    details = session.pending.details
    feedback_sounds = GAMES[session.engine.game_key].CHOICE_FEEDBACK_SOUNDS
    deadline = session.vm.steps_executed + max_steps
    branches = 0

    def follow(source, value, effects=None, panels=0):
        nonlocal branches
        branches += 1
        if branches > max_branches:
            return None
        preview = deepcopy(source, {id(source.resources): source.resources,
                                    id(source.vm.program): source.vm.program})
        effects = dict(effects or {})

        def observe(action):
            if action.name == 'set_next_dialogue_notice' and action.details['text'] in SCORE_NOTICES:
                effects['score_notice'] = effects.get('score_notice', 0) + 1
            elif action.name == 'request_audio' and action.request.yield_id == 79:
                feedback = feedback_sounds.get(action.details['asset_id'], 0)
                if feedback:
                    # Explicit correct/wrong feedback can accompany script-local
                    # quiz scoring without a relationship or Score Up! notice.
                    # Keep opposite cues separate so mixed feedback cannot cancel.
                    key = 'correct_feedback' if feedback > 0 else 'incorrect_feedback'
                    effects[key] = effects.get(key, 0) + feedback
            elif action.name in ('set_number', 'set_number_bit'):
                owner, key = action.details['owner'], action.details['key']
                if owner > 0 and key == 407:
                    address = preview.engine.number_key(owner, key)
                    effects[address] = preview.engine.numbers[address] - session.engine.numbers.get(address, 0)

        try:
            preview._complete_choice(value)
            while preview.vm.steps_executed < deadline:
                action = preview.advance(max_steps=deadline - preview.vm.steps_executed,
                                         max_events=2000, observe=observe)
                if action.name in DECISIONS:
                    return preview, effects, panels
                if action.name not in PANELS or panels == max_panels:
                    break
                panels += 1
                preview._complete_panel()
                preview.engine.title_screen = preview.engine.message_panel = None
        except (ContentError, VMError, OSError, ValueError):
            pass
        return None

    nodes = [follow(session, value) if enabled and index < max_options else None
             for index, (value, enabled) in enumerate(zip(details['values'], details['enabled']))]
    hints = [ChoiceHint(_kind(node[1]) if node else 'unknown') for node in nodes]
    if not any(node and any(node[1].values()) for node in nodes):
        enabled = [i for i, value in enumerate(details['enabled']) if value]

        def outcomes(group, depth):
            if not group or any(node is None for node in group):
                return None
            if any(any(node[1].values()) for node in group):
                return [[node[1] for node in group]]
            actions = [node[0].pending for node in group]
            if all(a.name in ('finished', 'episode_exit') for a in actions):
                return [[{} for _ in group]]
            if depth >= max_decisions or any(a.name != 'choice' for a in actions):
                return None
            # Match the actual script decision and result values, independently
            # of native randomized display order. Do not guess how unrelated
            # questions, disabled options or minigames correspond.
            signatures = [(node[0].scene, a.request.pc,
                           tuple(sorted(v for v, on in zip(a.details['values'], a.details['enabled']) if on)))
                          for node, a in zip(group, actions)]
            if any(s != signatures[0] for s in signatures) or not signatures[0][2]:
                return None
            values = tuple(dict.fromkeys(signatures[0][2]))
            if len(values) > max_options:
                return None
            result = []
            for value in values:
                children = [follow(preview, value, effects, panels) for preview, effects, panels in group]
                leaves = outcomes(children, depth + 1)
                if leaves is None:
                    return None
                result.extend(leaves)
            return result

        leaves = outcomes([nodes[i] for i in enabled], 1)
        if leaves is not None:
            dominates = set()
            for a in range(len(enabled)):
                for b in range(len(enabled)):
                    deltas = [row[a].get(key, 0) - row[b].get(key, 0)
                              for row in leaves for key in row[a].keys() | row[b].keys()]
                    if deltas and min(deltas) >= 0 and max(deltas) > 0:
                        dominates.add((a, b))
            for index, original in enumerate(enabled):
                if any(b == index for _, b in dominates):
                    hints[original] = ChoiceHint('no_gain')
                elif any(a == index for a, _ in dominates):
                    hints[original] = ChoiceHint('gain')
    # Absence of recognized feedback alone is not proof of a wrong answer.
    # Mark non-scoring alternatives only when this decision has a known gain.
    has_gain = any(hint.kind == 'gain' for hint in hints)
    return tuple(ChoiceHint('unknown') if hint.kind == 'no_gain' and not has_gain else hint
                 for hint in hints)


def _kind(effects):
    gain, loss = any(v > 0 for v in effects.values()), any(v < 0 for v in effects.values())
    return 'mixed' if gain and loss else 'gain' if gain else 'loss' if loss else 'no_gain'
