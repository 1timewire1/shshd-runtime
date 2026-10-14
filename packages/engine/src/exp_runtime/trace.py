"""Execute an EXP's KiWi code to the first pending action or diagnostic stop."""
from dataclasses import asdict
import hashlib
from pathlib import Path

from .decode.bytecode import decode_program
from .content import ExpArchive
from .engine import EngineState
from .games import GAMES
from .vm import KiwiVM, StopKind, VMError


def trace_archive(path: Path, *, max_events: int = 10_000, max_steps: int = 100_000, game='shs') -> dict:
    """Trace a fresh game state. Never answer presentation/unknown yields.

    Scheduled scripts are popped in LIFO order, as in FUN_0007f5f4.
    Resource decoding/rendering, native saves, and minigames are outside
    this trace. The result contains only state this handler subset models.
    """
    if max_events < 1 or max_steps < 1:
        raise ValueError('trace budgets must be positive')
    if game not in GAMES:
        raise ValueError(f'Unknown game: {game}')
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    archive = ExpArchive(data)
    programs = {}
    for resource_id in archive.entries:
        payload = archive.read(resource_id)
        if payload.startswith(b'kiwi'):
            programs[resource_id] = decode_program(payload)
    if not programs:
        raise ValueError(f'no KiWi scripts in {path}')
    scene = next(iter(programs))
    vm = KiwiVM(programs[scene])
    engine = EngineState()
    engine.game_key = game
    events = []
    stop = 'event_budget'
    error = None
    for _ in range(max_events):
        remaining = max_steps - vm.steps_executed
        if remaining <= 0:
            stop = 'instruction_budget'
            break
        try:
            event = vm.run(remaining)
            if event.kind == StopKind.YIELD:
                action = engine.dispatch(vm)
                events.append(dict(scene=scene, **asdict(action)))
                if not action.completed:
                    stop = action.name
                    break
            elif event.kind == StopKind.HALT and engine.scheduled_scripts:
                next_scene, flag = engine.scheduled_scripts[-1]
                if next_scene not in programs:
                    stop = 'missing_script'
                    error = f'scheduled script {next_scene} is absent from this archive'
                    break
                engine.scheduled_scripts.pop()
                events.append(dict(scene=scene, name='load_script', file_id=next_scene, flag=flag))
                scene = next_scene
                vm.load_next(programs[scene])
            else:
                stop = event.kind.value
                break
        except VMError as exc:
            stop, error = 'vm_error', str(exc)
            break
    return dict(
        archive=str(path), sha256=digest, status=stop, error=error,
        scene=scene, pc=vm.pc, sp=vm.sp, fp=vm.fp,
        steps=vm.steps_executed, events=events, state=asdict(engine),
        executed_opcodes={f'0x{op:02x}': count for op, count in sorted(vm.opcode_counts.items())},
        recent_pcs=list(vm.recent_pcs),
    )
