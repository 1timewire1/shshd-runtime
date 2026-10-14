"""Cause of Death host-service differences, recovered from its iOS dispatcher."""
from ..vm import VMError


def dispatch(engine, vm, *, resource_exists=None):
    from ..engine import EngineAction
    request = vm.pending
    service, args = request.yield_id, request.args

    def complete(name, result=0, **details):
        vm.resume(result)
        return EngineAction(name, request, True, dict(result=result, **details))

    if service == 15:
        # SHSScript::syscall 0003354c, case 0x0f: named dialogue on panel 3.
        # Only the first two words are read, even in the four-word EXP form.
        if len(args) < 2:
            raise VMError(f'yield 15 at pc {request.pc}: needs at least 2 arguments')
        speaker, text = (engine.read_text(vm, ref) for ref in args[:2])
        return EngineAction('dialogue', request, False,
                            engine.present_dialogue(-1, 0, text, 0, speaker=speaker))
    if service == 70:
        # 000335d6 reads stack[SP - argc], including retained backing for a
        # zero-word call. Extra frame words are ignored, then popped normally.
        selector = args[0] if args else vm.read_word(vm.stack_base + vm.sp)
        if selector == 6:
            # 000341fe writes CFBundleVersion to the first dynamic string.
            # Bare EXP tracing has no native bundle; do not invent a version.
            if engine.app_version is None:
                return EngineAction('unhandled_yield', request, False, dict(
                    selector=selector, reason='CoD version query requires CFBundleVersion from its IPA'))
            engine.dynamic_strings[0] = engine.app_version
        # 000341bc: selector 10 returns 1 when MTX_IsStoreAvailable is false.
        # The offline desktop has no MTX store. This is its unavailable branch,
        # not a claim that every native iOS device returned a constant.
        result = {2: 2, 3: 6, 6: 0x7ff5, 9: 1, 10: 1}.get(selector, 0)
        return complete('query_build', result, selector=selector)
    if service in (94, 96, 100):
        # 94/96 target 00033778 through the table; 100 reaches it through the
        # unsigned >99 branch at 000335cc, without reading any frame words.
        # This reproduces the supplied CoD 1.3.4 default, including callers
        # with promotional URLs. It does not implement a later URL launcher.
        # The completion tail at 00034b74 narrows the internal sentinel to R=0
        # and pops the frame.
        # No minigame, score write or random draw occurs in this native build.
        return complete('native_noop')
    if service == 99:
        if len(args) != 1:
            raise VMError(f'yield 99 at pc {request.pc}: expected 1 arguments, got {len(args)}')
        # Offline desktop adaptation of the native no-ad completion path.
        # No ad SDK or network request is made; resume the original continuation.
        return complete('offline_ad')
    if service in (9, 91, 95):
        return EngineAction('unhandled_yield', request, False,
                            dict(reason='This service is not implemented for Cause of Death'))
    return None
