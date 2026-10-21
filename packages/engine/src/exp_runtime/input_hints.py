"""Optional CoD answer hints from bounded, isolated script continuations.

Comparison operands propose answers; explicit feedback or an unambiguous retry
loop establishes acceptance. A compared string alone can be a wrong guess or
an Easter egg in a freely chosen name. Never use it alone as an answer key.
"""
from copy import deepcopy
from dataclasses import dataclass

from .choice_hints import DECISIONS, PANELS, observe_effects
from .content import ContentError
from .text_input import accept_name_character, validate_name
from .vm import VMError


@dataclass
class _Outcome:
    candidates: list[str]
    effects: dict
    route: list[tuple]


def _location(session, action):
    return session.scene, action.request.pc, action.name


def _trace(session, text, max_steps, max_panels, max_candidates):
    preview = deepcopy(session, {id(session.resources): session.resources,
                                 id(session.vm.program): session.vm.program})
    outcome = _Outcome([], {}, [])
    deadline = preview.vm.steps_executed + max_steps

    def observe(action):
        observe_effects(session, preview, action, outcome.effects)
        if action.name == 'text_equal':
            left, right = (preview.engine.read_text(preview.vm, ref) for ref in action.request.args)
            # Two distinct probes below distinguish input-dependent comparisons
            # (including copy_last_input/formatting) from unrelated constants.
            other = right if left == text else left if right == text else None
            if other is not None and other != text and other not in outcome.candidates:
                outcome.candidates.append(other)
                if len(outcome.candidates) > max_candidates:
                    raise VMError('Answer hint candidate budget exceeded')

    try:
        preview._complete_text_input(text)
        while preview.vm.steps_executed < deadline:
            if preview.transitioning and preview.engine.scene_transition.phase == 4:
                preview._finish_transition(advance=False)
            action = preview.advance(max_steps=deadline - preview.vm.steps_executed,
                                     max_events=2000, observe=observe)
            if preview.transitioning and preview.engine.scene_transition.phase == 3:
                preview.engine.scene_transition.clear()
            outcome.route.append(_location(preview, action))
            if action.name in DECISIONS:
                return outcome
            if action.name not in PANELS or len(outcome.route) > max_panels:
                break
            if action.name == 'vm_pause':
                preview.vm.continue_after_pause()
                preview.pending = None
            elif action.name == 'loading':
                if preview.engine.loading.blocking:
                    preview.vm.resume(0)
                preview.engine.loading = preview.pending = None
            elif action.name == 'survey_confirmation':
                preview._complete_survey(action)
            else:
                preview._complete_panel()
                preview.engine.title_screen = preview.engine.message_panel = None
    except (ContentError, VMError, OSError, ValueError):
        pass
    return None


def _improves(effects, baseline):
    deltas = [effects.get(key, 0) - baseline.get(key, 0) for key in effects.keys() | baseline.keys()]
    return bool(deltas) and min(deltas) >= 0 and max(deltas) > 0


def preview_answer(session, *, max_steps=12000, max_panels=96, max_candidates=32):
    """Return one script-accepted spelling, or None when evidence is uncertain.

    No mutations, input drafts, sound/vibration requests or random draws escape
    these copies. Stop at the next decision; never guess an unknown host result.
    """
    if session.engine.game_key != 'cod' or not session.pending or session.pending.name != 'text_input':
        return None
    if min(max_steps, max_panels, max_candidates) < 1:
        raise ValueError('Preview budgets must be positive')
    budgets = max_steps, max_panels, max_candidates
    baselines = [_trace(session, value, *budgets) for value in ('ExpHintA', 'ExpHintB')]
    if any(result is None for result in baselines):
        return None
    candidates = [text for text in baselines[0].candidates if text in baselines[1].candidates]
    metrics = session.name_input_metrics()
    origin = _location(session, session.pending)
    accepted, uncertain = [], False
    for text in candidates:
        try:
            validate_name(text, **metrics)
        except ValueError:
            continue
        # Preserve exact script spelling, including case. Do not suggest a
        # value the native first-character capitalization cannot produce.
        first, _ = accept_name_character('', text[0], capitalize_first=True, **metrics)
        if not text.startswith(first) or not first:
            continue
        result = _trace(session, text, *budgets)
        if result is None:
            uncertain = True
            continue
        if result.route[-1] == origin:
            continue
        if all(_improves(result.effects, base.effects) for base in baselines):
            return text
        if not any(value < 0 for value in result.effects.values()):
            accepted.append((text, result))
    # Some puzzles have no feedback cue and simply repeat until accepted. Only
    # use that evidence when every accepted spelling takes the same continuation;
    # distinct silent branches could include a wrong guess corrected by the story.
    if (not uncertain and accepted and all(base.route[-1] == origin for base in baselines)
            and all(result.route == accepted[0][1].route for _, result in accepted)):
        return accepted[0][0]
    return None
