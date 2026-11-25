"""shshd-runtime: the open mini-game as a player would read it (its score, time left, round and what it waits for), for the
Creator's playtests (creator/playtest.py, MCP's `minigame` field) and the app's test channel (`state`'s `minigame`, owner
2026-11-21). Moved here from the Creator so both read one report; headless (no pygame).

A Claire Hart round also lists its names (each with its object and whether it's found), the score, the hint and the Power-Ups
left, so a driver can find what's listed."""
from dataclasses import asdict, is_dataclass

# The translated mini-games, as the player plays them: a press (the go-ahead, then the game's own button), or a cell for SHS
# '11's; New Rules' arena takes key codes on its frames (nr_arena.KEY_BITS), a pick from its menu and an OK on its info box.
PRESS_GAMES = frozenset(('x360_slot', 'x360_leash', 'x360_puzzle', 'x360_diss', 'x360_battle', 'brew_catch', 'cutscene'))
CELL_GAMES = frozenset(('shs11_memory', 'shs11_reflex'))
ARENA = frozenset(('arena_frame', 'arena_menu', 'arena_info', 'arena_skip'))
OK_PHASES = frozenset(('ready', 'tutorial', 'score', 'ended', 'goal', 'look', 'shown', 'bad'))  # screens a press goes on from
STATES = ('word_game', 'football', 'word_grid', 'x360_slot', 'x360_leash', 'x360_puzzle', 'x360_diss', 'x360_battle',
          'shs11_memory', 'shs11_reflex', 'brew_catch', 'claire_round', 'cutscene')


def describe(session, *, skippable=False):
    """The pending mini-game (or arena screen, or cutscene) as a dict, or None. `skippable`: its skip prompt is up (or would
    be offered now), so it waits for that or the go-ahead."""
    action = session.pending
    name = action.name if action is not None else None
    arena = session.engine.nr_arena
    if name in ARENA | {'arena_entrance', 'arena_exit'} and arena is not None:
        # New Rules' arena: its keys (nr_arena.KEY_BITS: -5 OK, -1 to -4 the joystick, 48-57 the number keys); after
        # time's up, its score waits for OK.
        waits = ('time' if name in ('arena_entrance', 'arena_exit') else 'ok (key -5) for the score' if arena.time_up == 2
                 else 'keys' if name == 'arena_frame' else 'answer' if name == 'arena_menu' else 'continue')
        return dict(kind='nr_arena', time_up=arena.time_up, labels=[l for l in arena.labels if l], waits_for=waits)
    if name not in STATES:
        return None
    live = getattr(session.engine, name, None)
    if not is_dataclass(live):
        return None
    if name == 'claire_round':
        return claire_round(live, skippable=skippable)
    game = asdict(live)
    summary = dict(kind=name, started=not session.minigame_unstarted if name != 'cutscene' else live.elapsed_ms > 0)
    for key in ('phase', 'score', 'points', 'round', 'target', 'level', 'right', 'wrong', 'found', 'remaining'):
        if key in game:
            summary[key] = game[key]
    result = getattr(live, 'result', None)
    if isinstance(result, int) and not isinstance(result, bool):
        summary['result'] = result
    if name == 'x360_slot':
        from .x360_games import DURATION_MS
        summary['time_left_ms'] = DURATION_MS - live.clock_ms
    elif name in CELL_GAMES:
        summary['time_left_ms'] = live.clock_ms
    elif name in ('x360_puzzle', 'x360_diss', 'x360_battle'):
        summary['time_left_ms'] = live.total_time * 1000
    elif name == 'cutscene':
        summary.update(elapsed_ms=live.elapsed_ms, skip_ms=live.skip_ms, hold_ms=live.hold_ms, held=live.held)
    phase = getattr(live, 'phase', None)
    if name == 'cutscene':
        summary['waits_for'] = 'press' if live.held else 'time or press'
    elif skippable:
        summary['waits_for'] = 'skip prompt or go-ahead'
    elif name in CELL_GAMES:
        # '11's tutorial screens take an OK (a press with no cell); its rounds take cells.
        summary['waits_for'] = ('cell' if phase == 'play' else 'press' if live.tutorial or phase in OK_PHASES
                                else 'time')
    elif name == 'word_game':
        summary.update(options=list(live.options), waits_for='an option (press N)')
    elif name == 'word_grid':
        # The board row by row and its width, for `play cells`; its rules pages and results take a tap off the board.
        summary.update(board=''.join(live.board), width=live.problem.width,
                       waits_for='cells (play cells A B C...)' if getattr(live, 'input_enabled', False) else 'press or time')
    elif name == 'football':
        # Its rules pages (phases 20-23) take a tap once shown a moment; its play (phase 3) one of the nine targets
        # (`play press N`, 0-8); the rest runs by itself (v1.1.1 check, 2026-11-22: all read "time").
        summary['waits_for'] = 'press' if 20 <= phase <= 23 else 'a play (press 0-8)' if phase == 3 else 'time'
    elif phase in OK_PHASES or name == 'brew_catch' and not live.started:
        summary['waits_for'] = 'press'      # a go-ahead, a tutorial page or the score screen's OK
    elif phase in ('running', None):
        summary['waits_for'] = 'press'
    else:
        summary['waits_for'] = 'time'       # an opening, countdown, time-up or closing
    return summary


def claire_round(game, *, skippable=False):
    """A Claire Hart round (claire_rounds.ClaireRound): the list as shown (each name with its object, found or not), the
    count, score, clock, the hint and the Power-Ups left, and what it waits for."""
    from .claire_rounds import NO_OBJECT, POWERUPS
    from .shadows_rounds import ShadowsRound
    if isinstance(game, ShadowsRound):
        return shadows_round(game, skippable=skippable)
    listed = [dict(slot=slot, name=game.names[obj], object=obj, found=obj in game.found, extra=bool(game.extra[slot]))
              for slot, obj in enumerate(game.slots) if obj != NO_OBJECT]
    waits = ('skip prompt or go-ahead' if skippable and not game.started else 'continue' if game.over
             else 'a listed name (the Psychic Locator)' if game.locating else 'taps on the listed objects')
    return dict(kind='claire_round', scene=game.scene, title=game.title, started=game.started, listed=listed,
                found=game.found_count, to_find=game.to_find, score=game.score, multiplier=game.multiplier,
                seconds=game.seconds, misclicks=game.misclicks, locked_ms=game.lock_ms,
                hint=dict(ready=game.hint_ready, refill_ms=game.hint_refill_ms, used=game.hints),
                powerups={p: dict(left=game.uses_left(p), usable=game.can_use(p)) for p in POWERUPS},
                marker=dict(hint=game.hint_target, focus=game.focus_target, locator=game.locator_target),
                time_warp=game.time_warp, over=game.over, waits_for=waits)


def shadows_round(game, *, skippable=False):
    """A round under Secret in the Shadows' rules (shadows_rounds.ShadowsRound): the list (each name with its object and
    kind), the count, score, clock, the close-up, the Gold Key, a multi-part object's parts collected, the Psychic Sensor,
    the Power-Ups left, the Hint's markers, and what it waits for."""
    from .shadows_rounds import NO_OBJECT, POWERUPS
    listed = [dict(slot=slot, name=game.names[obj], object=obj, kind=game.kinds[obj], found=obj in game.found,
                   extra=bool(game.extra[slot])) for slot, obj in enumerate(game.slots) if obj != NO_OBJECT]
    waits = ('skip prompt or go-ahead' if skippable and not game.started else 'continue' if game.over
             else 'taps on the listed objects')
    return dict(kind='claire_round', rules='shadows', source=game.source, scene=game.scene, title=game.title,
                started=game.started, listed=listed, found=game.found_count, to_find=game.to_find,
                score=game.find_points, multiplier=game.multiplier, seconds=game.seconds, misclicks=game.misclicks,
                locked_ms=game.lock_ms, close_up=dict(open=game.pip_open, glow=game.pip_glow), key=game.key,
                key_found_ms=game.key_found_ms, collecting=list(game.collecting),
                sensor=dict(on=game.sensor_on, ready=game.sensor_ready, target=game.sensor_target, uses=game.sensor_uses,
                            cooldown_ms=game.sensor_cooldown_ms),
                powerups={p: dict(left=game.uses_left(p), usable=game.can_use(p)) for p in POWERUPS},
                markers=list(game.markers), time_warp=game.time_warp, spotlight=game.spotlight, over=game.over,
                waits_for=waits)
