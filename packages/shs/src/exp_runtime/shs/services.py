"""SHS-specific yields; common KiWi host services live in engine.py."""
from copy import deepcopy

from ..loading import LoadingScreen, loading_waits
from ..vm import VMError
from .football import read_football
from .word_grid import read_grid
from .survey import confirmation as survey_confirmation, is_survey, script_response


def named_dialogue_refs(request):
    """Service 15 ignores a negative prefix and all words after its two texts."""
    args = request.args
    offset = 1 if args and args[0] < 0 else 0
    if len(args) < offset + 2:
        raise VMError(f'yield 15 at pc {request.pc}: needs at least {offset + 2} arguments')
    return args[offset:offset + 2]


def dispatch(self, vm, *, resource_exists=None):
    from ..engine import EngineAction
    request = vm.pending
    y, args = request.yield_id, request.args

    def need(count):
        if len(args) != count:
            raise VMError(f'yield {y} at pc {request.pc}: expected {count} arguments, got {len(args)}')

    def at_least(count):
        if len(args) < count:
            raise VMError(f'yield {y} at pc {request.pc}: needs at least {count} arguments')

    def complete(action_name, result=0, **details):
        vm.resume(result)
        return EngineAction(action_name, request, True, dict(result=result, **details))

    if y == 9:
        at_least(2)
        if not is_survey(args):
            return EngineAction('unhandled_yield', request, False,
                                dict(reason=f'Unsupported survey upload type {args[1]}'))
        response = script_response(vm, self.read_text)
        if response is None:
            return EngineAction('unhandled_yield', request, False,
                                dict(reason='Unsupported survey response continuation'))
        # Hold the submission through the local receipt. Acknowledgement
        # follows the verified not-uploaded branch, without poll results.
        self.message_panel = survey_confirmation()
        return EngineAction('survey_confirmation', request, False, dict(response_pc=response.pc))
    if y in (14, 21):
        # Android table entries 0009fedc/0009fef8 -> 000a00f8; SHS iOS
        # entries 0006de74/0006de90 -> 00071abc. Both complete with R=0
        # and pop the supplied frame without changing panel or game state.
        return complete('native_noop')
    if y == 15:
        # Android 000a1bd4 and SHS iOS 0006f8d8 both select mode 3 and
        # skip a negative first word before reading speaker/body strings.
        # The prefix does not add parentheses or emphasis as service 13 does.
        speaker, text = (self.read_text(vm, ref) for ref in named_dialogue_refs(request))
        return EngineAction('dialogue', request, False,
                            self.present_dialogue(-1, 0, text, 0, speaker=speaker))
    if y == 91:
        self.loading = LoadingScreen(loading_waits(vm, request), self.loading.elapsed_ms if self.loading else 0)
        details = {}
        if not self.loading.blocking:
            # Compact calls retain their count in bytecode. Register-count
            # calls lose it on completion; keep nonlegacy counts for saves.
            if vm.program.instructions[request.pc].opcode == 0x1e and len(args) != 1:
                details['argument_count'] = len(args)
            vm.resume(0)  # The call completes, but host +0x118 still gates execution.
        return EngineAction('loading', request, False, details)
    if y == 70:
        at_least(1)
        selector = args[0]
        if selector == 11:
            # 0009fe3c compares the current episode object with the native
            # weekly-episode slot. Local imports do not establish that identity.
            return EngineAction('unhandled_yield', request, False, dict(
                selector=selector, reason='Service 70 selector 11 needs native weekly-episode state'))
        # Android 1.0.9 constants; all other selectors explicitly return 0.
        # Selector 6 returns the existing dynamic slot, without writing it.
        result = {2: 2, 3: 6, 6: 0x7ff5, 9: 1}.get(selector, 0)
        return complete('query_build', result, selector=selector)
    if y == 94:
        need(22)
        game = read_football(vm, args, lambda ref: self.read_text(vm, ref))
        game.validate()
        self.football = game
        return EngineAction('football', request, False)
    if y == 95:
        need(1)
        result = self.football_scores[0 if args[0] == 1 else 1]
        if result is None:
            raise VMError('Read of uninitialized football score')
        return complete('get_football_score', result)
    if y == 96:
        need(20)
        game = read_grid(vm, args, lambda ref: self.read_text(vm, ref),
                         lambda ref: self.resolve_text(vm, ref),
                         tutorials_seen=self.grid_tutorials_seen)
        # Construct transactionally: invalid content leaves the frame and
        # engine random stream available for inspection and a saved stop.
        random = deepcopy(self.random)
        game.initialize(random)
        self.word_grid, self.random = game, random
        self.grid_tutorials_seen |= bool(game.tutorials)
        base, variant = args[5], args[4]
        background = base + variant if base >= 0 and variant in (1, 2) else base
        if resource_exists and not resource_exists(background):
            background = base
        return EngineAction('word_grid', request, False, dict(
            background_id=background, left_character=args[6], left_expression=args[7],
            right_character=args[8], right_expression=args[9]))
    return None
