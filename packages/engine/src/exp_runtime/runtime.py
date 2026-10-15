"""Presentation-independent game session and versioned, local JSON saves."""
from copy import deepcopy
from dataclasses import asdict, fields, is_dataclass
import gzip
import json
import logging
import os
from pathlib import Path
import tempfile
from types import UnionType
from typing import get_args, get_origin, get_type_hints

from .content import EpisodeResources, digest
from .games import GAMES, game_id
from .engine import POLL_WAIT_MS, EngineAction, EngineState
from .dialogue_animation import DialogueAnimation, DialoguePortrait, DialogueHistory, EXPRESSION_MS
from .background import BackgroundPan
from .scene_fade import resolve
from .dialogue_notice import hd_letter_start_ms, hd_notice_lifetime, notice_limit
from .dt_state import install_state
from .dtview_faceplace import DTNode, DTView, FaceplaceWall
from .relationships import RelationshipAnimation, RelationshipChange
from .speaker_names import SpeakerNames
from .title_screen import TitleScreen
from .loading import loading_waits, retained_word
from .text_input import input_fonts, validate_name
from .randomness import NativeRandom, RAND48_INITIAL, RAND48_MASK
from .vm import KiwiVM, StopKind, VMError, VMStop, signed16


class SaveError(ValueError):
    pass


def _typed_value(value, annotation, *, state_types=None):
    """Decode dataclass state without permitting arbitrary object construction."""
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is UnionType:
        for candidate in args:
            try:
                return _typed_value(value, candidate)
            except SaveError:
                pass
        raise SaveError('Invalid optional state value')
    if is_dataclass(annotation):
        names = {f.name for f in fields(annotation)}
        if not isinstance(value, dict) or set(value) != names:
            raise SaveError('Engine snapshot fields do not match this runtime')
        hints = get_type_hints(annotation)
        if annotation is EngineState:
            # Only the selected installed adapter supplies these concrete
            # dataclasses. Other games must have null fields, even when SHS
            # happens to be installed. Saved input cannot select a type.
            hints.update(word_grid=type(None), football=type(None))
            hints.update(state_types or {})
        return annotation(**{key: _typed_value(item, hints[key]) for key, item in value.items()})
    if origin is dict:
        if not isinstance(value, dict):
            raise SaveError('Expected a state map')
        result = {}
        for key, item in value.items():
            if args[0] is int and isinstance(key, str):
                try:
                    converted = int(key)
                except ValueError:
                    raise SaveError('Invalid numeric state key') from None
                if str(converted) != key:
                    raise SaveError('Noncanonical numeric state key')
                key = converted
            result[_typed_value(key, args[0])] = _typed_value(item, args[1])
        return result
    if origin in (list, tuple):
        if not isinstance(value, (list, tuple)):
            raise SaveError('Expected a state sequence')
        if origin is list:
            return [_typed_value(item, args[0]) for item in value]
        if len(value) != len(args):
            raise SaveError('Invalid state tuple size')
        return tuple(_typed_value(item, hint) for item, hint in zip(value, args))
    if type(value) is not annotation:
        raise SaveError(f'Expected state value of type {annotation.__name__}')
    return deepcopy(value)


def _validate_choice(details):
    try:
        options, values, enabled = (details[k] for k in ('options', 'values', 'enabled'))
        if not (isinstance(options, list) and isinstance(values, list) and isinstance(enabled, list)
                and len(options) == len(values) == len(enabled)
                and all(isinstance(v, str) for v in options)
                and all(type(v) is int and -32768 <= v <= 32767 for v in values)
                and all(type(v) is bool for v in enabled)
                and type(details['timeout_ms']) is int and 0 <= details['timeout_ms'] <= 32767
                and type(details['timeout_result']) is int
                and -32768 <= details['timeout_result'] <= 32767
                and all(isinstance(details[k], str) for k in ('title', 'text'))
                and all(type(details[k]) is int for k in ('character_id', 'portrait_mode'))):
            raise SaveError('Invalid choice data')
    except (KeyError, TypeError) as error:
        raise SaveError('Incomplete choice data') from error


class Session:
    """Execute original KiWi code until real player input is required.

    Unknown engine services stay suspended. A bounded advance prevents an
    unsupported script loop from freezing the desktop event loop forever.
    """

    def __init__(self, resources: EpisodeResources, *, start_script: int = 25001, ephemeral: bool = False):
        GAMES[game_id(resources)]  # Fail before executing with a missing adapter.
        self.resources = resources
        # An ephemeral session (a preview capture) never writes the library's shared tree file.
        self.ephemeral = ephemeral
        self.scene = start_script
        self.vm = KiwiVM(resources.program(start_script))
        self.engine = EngineState()
        self._set_build()
        self.engine.game_key = game_id(resources)
        self.engine.app_version = getattr(resources.library, 'app_info', {}).get('CFBundleVersion')
        self.pending: EngineAction | None = None
        self.remaining_ms: int | None = None
        self.scene_loads = 0
        self.transition_kind = 0    # the blind / fade the last completed panel queued (scene_fade.py); not saved
        self._load_dt_view()

    @property
    def save_path(self) -> Path:
        return (self.resources.library.directory / 'saves'
                / (self.resources.identity['episode_sha256'] + '.shs-save.json'))

    def _set_build(self):
        library = getattr(self.resources, 'library', None)
        version = library.hd_app_version() if hasattr(library, 'hd_app_version') else None
        self.engine.hd_version = version

    @property
    def dt_view_path(self) -> Path:
        """Library-wide, not tied to any one episode/save -- matching the
        real app's own tree_<serial>.sav files, which live in the app's
        shared cache directory and persist across separate playthroughs of
        whatever content calls into the DTView cluster (confirmed from a
        real device's own data; see legacy/findings.md)."""
        return self.resources.library.directory / 'dtview_tree.json'

    durable = True      # forced to disk after every write; a bulk run (tree_explorer) turns it off

    def _load_dt_view(self) -> None:
        try:
            data = json.loads(self.dt_view_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return
        try:
            self.engine.dt_view = DTView.from_dict(data)
        except (KeyError, TypeError, AttributeError):
            pass  # Corrupt or foreign file: keep playing with an empty tree.

    def _save_dt_view(self) -> None:
        if self.ephemeral:
            return
        path = self.dt_view_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                             prefix='.dtview-', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(json.dumps(self.engine.dt_view.to_dict(), ensure_ascii=False, separators=(',', ':')))     # dump() streams token by token
                stream.write('\n')
                stream.flush()
                if self.durable:
                    os.fsync(stream.fileno())
            temporary.replace(path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    # -- the story tree's per-node saves and warping --------------------------------------------------------------

    TREE_STATE_DIRECTORY = 'dtsaves'
    # Entity 0's integer properties `warpToNode:` keeps across the load (their meaning is not known).
    WARP_KEPT_PROPERTIES = (0xbbc, 0xbbd, 0xbbe, 0xbda, 0xbdc, 0xbdf)

    def _tree_state_path(self, serial: int) -> Path:
        return self.resources.library.directory / self.TREE_STATE_DIRECTORY / f'{serial}.json.gz'

    def tree_serials(self) -> set:
        """The tree nodes that have a saved game (the app's `tree_<serial>.sav` files): the ones that can be warped to."""
        if self._tree_serials is None:
            try:
                names = (self.resources.library.directory / self.TREE_STATE_DIRECTORY).glob('*.json.gz')
                self._tree_serials = {int(path.name.split('.')[0]) for path in names}
            except (OSError, ValueError, AttributeError):
                self._tree_serials = set()
        return self._tree_serials

    _tree_serials = None

    def has_tree_state(self, node) -> bool:
        return node is not None and node.serial in self.tree_serials()

    def _save_tree_state(self, node) -> None:
        """`SHSEngine::saveGameFile("tree_<serial>.sav")` at the end of `addNode`: the whole game as it is now."""
        if self.ephemeral or node is None or not node.serial:
            return
        path = self._tree_state_path(node.serial)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # No screen is pending yet, so the previous screen's animation is not part of this point. Nor is the tree
            # (a warp keeps the live one), which would make every save grow with it.
            engine = self.engine
            animation = engine.dialogue_animation
            engine.dialogue_animation = None
            try:
                state = self.snapshot()
            finally:
                engine.dialogue_animation = animation
            data = gzip.compress(json.dumps(state, ensure_ascii=False, separators=(',', ':')).encode('utf-8'), 3)
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.tree-', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
            temporary.replace(path)
        except (OSError, AttributeError) as error:
            logging.warning('Could not save tree node %s: %s', node.serial, error)
            return
        self.tree_serials().add(node.serial)

    def share_names(self, table: dict) -> None:
        """Make the engine's name-replacement table (`$USR`, `$ZOE`, `$DATE`... -- services 46, 47 and 113 and every
        `$KEY` in shown text) the library's own `table` (player.json `names`), as the app's `SHSEntityTable` renames
        are one table for the whole install: saved in shs_options.sav, loaded at start and never cleared by a new game,
        episode or loaded save. Keys only this session's save holds (written before the table was shared) join it; a
        key the table already has keeps the table's value."""
        for key, value in self.engine.strings.items():
            table.setdefault(key, value)
        self.engine.strings = table

    def warp(self, node) -> 'Session':
        """`SHSDTView warpToNode:` -- load the game saved at `node`, then put back what a load must not change: the
        tree itself (its shape is not part of a save) with `node` current, the six kept properties, the 200 entity
        names and `$USR`; the message wall is emptied. Returns the new session, run to its next input."""
        if not self.has_tree_state(node):
            raise SaveError('There is no saved game for that scene')
        try:
            state = json.loads(gzip.decompress(self._tree_state_path(node.serial).read_bytes()))
        except (OSError, ValueError) as error:
            raise SaveError(f'Cannot read the saved game of that scene: {error}') from error
        restored = Session.from_snapshot(self.resources, state)
        live, engine = self.engine, restored.engine
        view = live.dt_view
        if view.root is not None and node.deltas is not None:
            view.sweep_forward(view.root)                   # the scene's state as the story followed now leaves it
            if node.active:
                install_state(engine, node.snapshot)       # `installStateData`: the 67 tracked variables, then what is kept below
        engine.character_names = dict(live.character_names)
        engine.strings['$USR'] = live.strings.get('$USR', '')
        for property_id in self.WARP_KEPT_PROPERTIES:
            key = live.number_key(0, property_id)
            if key in live.numbers:
                engine.numbers[key] = live.numbers[key]
            else:
                engine.numbers.pop(key, None)
        view.accumulators.clear()                           # (`accumulators_set` is emptied before the sweep)
        view.current, view.pending_result_index, view.awaiting_result = node, 0, False
        view.sweep_forward(node)                        # `warpToNode:` sweeps the flags forward from the target
        engine.dt_view = view
        wall = live.faceplace
        wall.clear()
        engine.faceplace, engine.faceplace_toast = wall, None
        restored._tree_serials = self._tree_serials
        restored.advance()
        return restored

    @property
    def episode_exited(self) -> bool:
        return self.pending is not None and self.pending.name == 'episode_exit'

    def dialogue_page(self):
        """Layout is a session contract, shared by headless and desktop input."""
        action = self.pending
        if not action or action.name != 'dialogue' or not hasattr(self.resources, 'dialogue_layout'):
            return None
        return self.resources.dialogue_layout().page(action.details, action.details.get('page_start', 0),
                                                    names=self.engine.speaker_names)

    def name_input_metrics(self):
        """Use the selected game's glyph advances for both input paths.

        `hd` follows the engine build being emulated: an imported HD app
        bundle (its HD-only resource 155 is present) brings the HD build's
        name-entry rules, otherwise Android's. Cause of Death is iOS-only, so
        it always takes the iOS rules (this fork): its 1.4.7
        `SHSUITextEntry::tick` (0003ee0e-0003ee96) keeps letters and digits
        as typed with no length cap, and the first letter is capitalized by
        the iPhone keyboard (a UITextView's default), not by the game. Its
        typed answers expect that capital ("Ipconfig"); desktop keyboards do
        not add it, and Android's rules also lowercased later capitals."""
        try:
            hd = self.resources.hd_asset(155) is not None or game_id(self.resources) == 'cod'
        except AttributeError:
            hd = game_id(self.resources) == 'cod'
        if not hasattr(self.resources, 'dialogue_layout'):
            return dict(font=None, cursor_width=0, hd=hd)
        layout = self.resources.dialogue_layout()
        name, cursor = input_fonts(self.resources)
        return dict(font=layout.font(name), cursor_width=layout.font(cursor).glyph('|').advance, hd=hd)

    def _prepare_dialogue(self, *, new_name=False):
        details = self.pending.details
        if new_name and hasattr(self.resources, 'dialogue_layout'):
            displayed = self.resources.dialogue_layout().prepare_name(details, self.engine.speaker_names)
            if details['presentation_mode'] != 4:
                # Native display-only spacing corrections modify the panel's
                # retained string; the script's character metadata stays intact.
                self.engine.panel.speaker = displayed
        details.setdefault('page_start', 0)
        page = self.dialogue_page()
        details['page_end'] = page.end if page else len(details['text'])

    def advance(self, *, max_steps: int = 100_000, max_events: int = 10_000,
                observe=None) -> EngineAction:
        if self.pending is not None:
            return self.pending
        if max_steps < 1 or max_events < 1:
            raise ValueError('Execution budgets must be positive')
        deadline = self.vm.steps_executed + max_steps
        for _ in range(max_events):
            remaining = deadline - self.vm.steps_executed
            if remaining <= 0:
                raise VMError('Session instruction budget exceeded before the next input')
            request = self.vm.run(remaining)
            if request.kind == StopKind.YIELD:
                action = self.engine.dispatch(self.vm, resource_exists=self.resources.exists)
                if action.name in ('dt_add_node', 'dt_add_result', 'dt_save'):
                    # Real native behavior: every addNode/addResult call
                    # auto-saves its own tree_<serial>.sav immediately, not
                    # just at the next regular checkpoint.
                    self._save_dt_view()
                    if action.name == 'dt_add_node':
                        self._save_tree_state(self.engine.dt_view.current)
                if observe is not None:
                    observe(action)
                if action.completed:
                    continue
                if action.name == 'choice':
                    _validate_choice(action.details)
                    self.remaining_ms = action.details['timeout_ms'] or None
                    # Real device confirmed (see dtview_faceplace.py module
                    # docstring): the DTView tree labels every result slot
                    # with the choice button text the player actually saw,
                    # not just the one taken. dt_add_node already set
                    # `current` to this decision's own node; the matching
                    # dt_add_result that resolves it is still ahead, so this
                    # is the only point where both the node and the button
                    # text/slot-index pairing are available together.
                    current = self.engine.dt_view.current
                    if current is not None and self.engine.dt_view.awaiting_result:
                        current.choice_labels = dict(zip(action.details['values'], action.details['options']))
                self.pending = action
                if action.name == 'dialogue':
                    self._prepare_dialogue(new_name=True)
                    self.engine.dialogue_animation = DialogueAnimation.start(
                        action.details, self.engine.character_art_variants, self.engine.dialogue_animation,
                        self.engine.dialogue_history)
                    if self.engine.notice and (self.engine.hd_version is not None
                                               or GAMES[self.engine.game_key].LETTER_NOTICE):
                        # HD's letters wait for the portrait (dialogue_notice.hd_letter_start_ms).
                        self.engine.notice_ms = (hd_letter_start_ms(self.engine.dialogue_animation)
                                                 + hd_notice_lifetime(self.engine.notice))
                # Native addUIElement covers the dialogue panel; removing the
                # temporary panel returns to the same speaker/expression.
                # Hidden dialogue does not tick. Only explicit teardown or a
                # new scene discards it.
                return action
            if request.kind == StopKind.HALT and self.engine.scheduled_scripts:
                scene, _flag = self.engine.scheduled_scripts[-1]
                program = self.resources.program(scene)
                self.engine.scheduled_scripts.pop()
                self.vm.load_next(program)
                # runScript09 clears the old scene UI before loadScript09.
                # The global hidden portrait position outlives that panel.
                self.engine.dialogue_animation = None
                self.engine.clear_scene_expressions()
                self.scene, self.scene_loads = scene, self.scene_loads + 1
                self.engine.panel.location_follow = True   # GameModel::loadScript09NoGUI
                continue
            if request.kind == StopKind.BUDGET:
                raise VMError('Session instruction budget exceeded before the next input')
            self.pending = EngineAction('finished' if request.kind == StopKind.HALT else 'vm_pause',
                                        request, False)
            if self.pending.name == 'finished':
                self.engine.dialogue_animation = None
            return self.pending
        raise VMError('Session service budget exceeded before the next input')

    def _complete_choice(self, result: int):
        self.engine.result_cells[0] = signed16(result)  # FUN_000add90
        self.vm.resume(result)
        self.pending, self.remaining_ms = None, None

    def answer(self, value=None) -> EngineAction:
        action = self.pending
        if action is None:
            raise VMError('There is no pending input')
        if self.episode_exited:
            raise VMError('The episode has ended; there is no pending input')
        if action.name == 'choice':
            options = action.details
            if (type(value) is not int or not 0 <= value < len(options['values'])
                    or not options['enabled'][value]):
                raise ValueError('Choose an enabled option by its zero-based index')
            self._complete_choice(options['values'][value])
        elif action.name == 'character_picker':
            picker = self.engine.character_picker
            swap_sound, confirm_sound = GAMES[self.engine.game_key].PICKER_SOUNDS
            if value is not None:
                if picker.select(value):
                    self.engine.sound_id, self.engine.sound_ids = swap_sound, [swap_sound]
                    self.engine.sound_serial += 1
                return action
            self.engine.sound_id, self.engine.sound_ids = confirm_sound, [confirm_sound]
            self.engine.sound_serial += 1
            self._complete_choice(picker.selected)  # FUN_000d1b48: original index, not ID.
            self.engine.character_picker = None
        elif action.name == 'word_game':
            game = self.engine.word_game
            if game.pick(value, self.engine.random48):
                right, wrong = GAMES[self.engine.game_key].WORD_GAME_SOUNDS
                self.engine.sound_id = right if game.last_delta > 0 else wrong
                self.engine.sound_ids = [self.engine.sound_id]
                self.engine.sound_serial += 1
            return action
        elif action.name == 'word_grid':
            if value is not None:
                raise ValueError('Grid input uses pointer phases and cell indices')
            return self.grid_pointer('down', None)
        elif action.name == 'football':
            game = self.engine.football
            before = game.sound_serial
            game.tap(value, self.engine.random)
            self._game_sound(game, before)
            return action
        elif action.name == 'text_input':
            validate_name(value, **self.name_input_metrics())
            self.engine.dynamic_strings[0] = self.engine.last_input = value
            self.vm.resume(0x7ff5)  # FUN_000d3f5c
            self.pending = None
        elif action.name in ('message_panel', 'survey_confirmation'):
            if value is not None:
                raise ValueError('This screen expects an acknowledgement')
            if not self.engine.message_panel.ready:
                return action  # 000abb3c ignores early input; it is not queued.
            if action.name == 'survey_confirmation':
                self._complete_survey(action)
            else:
                self._complete_panel()
                self.engine.message_panel = None
        elif action.name == 'presentation':
            if value is not None:
                raise ValueError('This screen expects an acknowledgement')
            if not self.engine.title_screen.acknowledge():
                return action
            self._complete_panel()
            self.engine.title_screen = None
        elif action.name == 'download_poll':
            return action                            # the bar takes no input; the download's end completes it
        elif action.name in ('dialogue', 'vm_pause'):
            if value is not None:
                raise ValueError('This screen expects an acknowledgement')
            if action.name == 'dialogue':
                # 000a9868 hides the notice even when this tap only requests
                # the unfinished text reveal, or turns a page in the same call.
                self.engine.notice, self.engine.notice_ms = '', 0
                # Real device confirmed: a Faceplace toast has no timer of its
                # own and instead persists until the player advances dialogue
                # (or opens the menu/side panels -- see Desktop), so any
                # dialogue-advance tap dismisses it here, same as the notice.
                self.engine.faceplace_toast = None
            if action.name == 'dialogue' and not self.engine.dialogue_animation.complete:
                self.engine.dialogue_animation.finish()
                return action
            if action.name == 'dialogue' and action.details['page_end'] < len(action.details['text']):
                action.details['page_start'] = action.details['page_end']
                self._prepare_dialogue()
                self.engine.dialogue_animation.next_page(len(action.details['text']) - action.details['page_start'])
                return action
            if action.name == 'vm_pause':
                self.vm.continue_after_pause()
            else:
                self._complete_panel()
            self.pending = None
        else:
            raise VMError(f'Cannot answer {action.name}; its native contract is not implemented')
        return self.advance()

    def _complete_survey(self, action):
        from .shs.survey import RESPONSE_STEPS, SURVEY_TEXT, script_response
        response = script_response(self.vm, self.engine.read_text)
        if response is None or response.pc != action.details['response_pc']:
            raise VMError('Survey response continuation changed while awaiting acknowledgement')
        self.vm.resume(0)  # Local status: not uploaded; leave aggregate memory alone.
        request = self.vm.run(RESPONSE_STEPS)
        if request != response:
            raise VMError('Survey response did not match its verified continuation')
        # The player has already acknowledged the replacement for this exact
        # connection-error notice. Execute its real frame and callback once,
        # preserving speaker/panel state and the queued transition's effects.
        self.pending = self.engine.dispatch(self.vm, resource_exists=self.resources.exists,
                                            dialogue_override=SURVEY_TEXT)
        self._prepare_dialogue(new_name=True)
        self._complete_panel()
        self.engine.message_panel = None

    def _complete_panel(self):
        # 000ab8b8 / 0007efe8, shared by title, message and dialogue panels. A queued
        # random transition consumes one libc draw, even before its animation
        # is implemented. 000a6448 returns zero without writing result cells.
        draw = self.engine.random48.next() if self.engine.scene_value == 20 else 0
        self.transition_kind = resolve(self.engine.scene_value, draw)
        self.engine.scene_value = 0
        self.vm.resume(0)
        self.pending = None

    def skip_minigame(self, won: bool):
        """Finish the pending football game or word grid as a win or a loss without playing it: the player's
        "Ask to skip mini-games" option (off by default). The script gets the result a real game hands it (football:
        home minus away, its scores recorded as `football_scores`; the grid: pass or fail), decided the way the tree
        explorer decides it rather than played. A game can start mid-match (the second half from 35-21), so the
        winning side ends one touchdown (7) ahead of the higher starting score and the other keeps its own."""
        kind = self.pending.name if self.pending else None
        if kind == 'football':
            game = self.engine.football
            lead = max(game.home, game.away) + 7
            home, away = (lead, game.away) if won else (game.home, lead)
            self.engine.football_scores = [home, away]
            result = home - away
        elif kind == 'word_grid':
            result = int(won)
        else:
            raise VMError('No football game or word grid is waiting')
        self.vm.resume(result)
        self.pending = None
        setattr(self.engine, kind, None)
        return self.advance()

    def _game_sound(self, game, before):
        if game.sound_serial != before:
            self.engine.sound_ids = game.sound_ids[:]
            self.engine.sound_id = game.sound_ids[0]
            self.engine.sound_serial += 1

    def grid_pointer(self, phase, index=None):
        """Feed a down/move/up/cancel event to the pending original grid."""
        if not self.pending or self.pending.name != 'word_grid':
            raise VMError('There is no pending grid game')
        game = self.engine.word_grid
        before = game.sound_serial
        game.pointer(phase, index, self.engine.random)
        self._game_sound(game, before)
        return self.pending

    def tick(self, elapsed_ms: int) -> EngineAction:
        """Advance active time only; time spent outside the app is excluded."""
        if type(elapsed_ms) is not int or elapsed_ms < 0:
            raise ValueError('Elapsed time must be nonnegative milliseconds')
        if self.episode_exited:
            return self.pending
        self.engine.background_pan.tick(elapsed_ms)
        if self.engine.scene_badge:
            self.engine.scene_badge.tick(elapsed_ms)
        self.engine.notice_ms = max(0, self.engine.notice_ms - elapsed_ms)
        if not self.engine.notice_ms:
            self.engine.notice = ''
        if self.engine.faceplace_toast:
            self.engine.faceplace_toast.tick(elapsed_ms)
        if self.engine.loading:
            if self.engine.loading.tick(elapsed_ms):
                if self.engine.loading.blocking:
                    self.vm.resume(0)  # No choice-result cell is written.
                self.engine.loading = None
                self.pending = None
                return self.advance()
            return self.pending
        if self.pending and self.pending.name == 'vm_pause':
            return self.answer()
        if self.pending and self.pending.name == 'download_poll':
            details = self.pending.details
            details['elapsed_ms'] += elapsed_ms
            if details['elapsed_ms'] >= POLL_WAIT_MS:
                self.vm.resume(0)                   # `finishPollDownload(false)`: the script gets 0
                self.pending = None
                return self.advance()
            return self.pending
        if self.pending and self.pending.name == 'dialogue':
            motion = self.engine.dialogue_animation
            motion.tick(elapsed_ms)
            if motion.portrait is not None and motion.presentation_ms >= EXPRESSION_MS:
                value = motion.expression & 255
                self.engine.dialogue_history.expressions[motion.portrait.character_id] = value - 256 if value > 127 else value
            return self.pending
        if self.pending and self.pending.name == 'character_picker':
            self.engine.character_picker.tick(elapsed_ms)
            return self.pending
        if self.pending and self.pending.name in ('message_panel', 'survey_confirmation'):
            self.engine.message_panel.tick(elapsed_ms)
            return self.pending  # Reading time never acknowledges the panel.
        if self.pending and self.pending.name == 'presentation':
            self.engine.title_screen.tick(elapsed_ms)
            return self.pending
        if self.pending and self.pending.name == 'word_game':
            game = self.engine.word_game
            finished = game.tick(elapsed_ms, self.engine.random48)
            if game.scored:
                right, wrong = GAMES[self.engine.game_key].WORD_GAME_SOUNDS
                self.engine.sound_id = right if game.scored > 0 else wrong
                self.engine.sound_ids = [self.engine.sound_id]
                self.engine.sound_serial += 1
                game.scored = 0
            if finished:
                self._complete_choice(game.score)  # FUN_000add90, mode 2.
                self.engine.word_game = None
                return self.advance()
            return self.pending
        if self.pending and self.pending.name in ('word_grid', 'football'):
            kind = self.pending.name
            game = getattr(self.engine, kind)
            before = game.sound_serial
            finished = game.tick(elapsed_ms, self.engine.random)
            self._game_sound(game, before)
            if finished:
                if kind == 'football':
                    self.engine.football_scores = [game.home, game.away]
                self.vm.resume(game.result)  # 000b10d8: result cells are unchanged.
                self.pending = None
                setattr(self.engine, kind, None)
                return self.advance()
            return self.pending
        if self.remaining_ms is not None:
            remaining = self.remaining_ms - elapsed_ms
            self.remaining_ms = max(0, remaining)
            if remaining < 0:  # 000ae4f4: exactly zero remains selectable.
                # For incremental choices the native callback maps the timeout
                # selection through the per-option return-value table as well.
                details = self.pending.details
                selected = details['timeout_result']
                if self.pending.request.yield_id == 4:
                    profile = GAMES[self.engine.game_key]
                    unset = getattr(profile, 'TIMEOUT_NO_OPTION_RESULT', None)
                    if 0 <= selected < len(details['values']):
                        selected = details['values'][selected]
                    elif selected == -1 and unset is not None:
                        selected = unset
                    elif (getattr(profile, 'TIMEOUT_PAST_OPTIONS_UNMAPPED', False) and selected >= len(details['values'])
                          and selected not in details['values']):
                        pass    # the selection itself, matching no option (cod/profile.py)
                    else:
                        raise VMError('Incremental choice timeout index is out of range')
                self._complete_choice(selected)
                return self.advance()
        return self.advance()

    def _engine_state(self) -> dict:
        """The engine as a save keeps it. The story tree is not part of a save: `SHSDTView saveGame:` writes only the current scene's
        serial, the result index and the last-was-result flag (the tree itself is `tree_nodes.txt`, kept whatever the game), so the
        tree is left out and the current scene is its serial."""
        engine, view = self.engine, self.engine.dt_view
        engine.dt_view = DTView(enabled=view.enabled, pending_result_index=view.pending_result_index,
                                awaiting_result=view.awaiting_result, last_was_result=view.last_was_result,
                                accumulators=list(view.accumulators))
        try:
            state = asdict(engine)
        finally:
            engine.dt_view = view
        state['dt_view']['current_serial'] = view.current.serial if view.current is not None else 0
        return state

    def snapshot(self) -> dict:
        return dict(format='shs-runtime-save', version=25,
                    content=self.resources.identity, scene=self.scene,
                    script_sha256=digest(self.vm.program.to_bytes()),
                    vm=self.vm.snapshot(), engine=self._engine_state(),
                    pending=dict(name=self.pending.name, details=deepcopy(self.pending.details))
                    if self.pending else None,
                    remaining_ms=self.remaining_ms, scene_loads=self.scene_loads)

    def _link_tree(self, library_view: DTView, serial, embedded: dict | None, wanted: dict | None) -> None:
        """`SHSDTView loadGame:` -- the saved game names its current scene by serial and that scene is looked up in the tree the
        game already has (`root->find(serial)`). The engine restored from a save carries only the flags; an older save that embeds
        its own tree (`embedded`, with the scene it was at as `wanted`) is used only when the library's tree does not have that scene."""
        saved = self.engine.dt_view
        if serial is None and wanted is not None:
            serial = wanted.get('serial') or None
        view, target = library_view, None
        if serial and view.root is not None:
            target = view.by_serial(serial)
            if target is not None and wanted is not None and (
                    (target.node_type, target.uid, target.script)
                    != (wanted.get('node_type'), wanted.get('uid', 0), wanted.get('script', 0))):
                target = None
        if target is None and embedded:
            view = DTView(root=DTNode.from_dict(embedded))
            view.ensure_serials()
            target = view.by_serial(serial) if serial else None
            if target is None and wanted is not None:
                target = view.find(wanted.get('uid', 0), wanted.get('script', 0))
        if target is None and serial:
            logging.warning('The saved game names scene %s, which the story tree does not have', serial)
        view.enabled = saved.enabled
        view.pending_result_index, view.awaiting_result = saved.pending_result_index, saved.awaiting_result
        view.last_was_result, view.accumulators = saved.last_was_result, saved.accumulators
        view.current = target
        if view.root is not None:
            view.refresh_flags()
        self.engine.dt_view = view

    @classmethod
    def from_snapshot(cls, resources: EpisodeResources, state: dict):
        try:
            if state['format'] != 'shs-runtime-save' or state['version'] not in range(1, 26):
                raise SaveError('Unsupported save format or version')
            # Version 24 adds the HD word game's own pacing (minigames.WordGame.hd and its phase clocks).
            if state['version'] < 24 and (state.get('engine') or {}).get('word_game') is not None:
                state = deepcopy(state)
                state['engine']['word_game'].update(hd=False, selected=-1, select_ms=0, fly_off_ms=0, fly_off_row=-1,
                                                    fly_on_ms=0, shown_ms=0, effect_ms=0, scored=0)
            legacy = state['version'] == 1
            # Version 25 adds exp-runtime v0.4.2's dialogue lifecycle (its own versions 20-21): the iOS box entrance,
            # the native shake and housing clip, delayed expressions and the hidden portrait history. It replaces this
            # fork's own expression memory (the engine's last_speaker / last_expressions, the animation's
            # expression_committed, the portraits' from_asset_id). An older save keeps its already full-size box.
            if state['version'] < 25:
                state = deepcopy(state)
                engine_state = state['engine']
                engine_state.pop('last_speaker', None)
                engine_state.pop('last_expressions', None)
                motion = engine_state.get('dialogue_animation')
                history = DialogueHistory()
                if motion is not None:
                    motion.pop('expression_committed', None)
                    for key in ('portrait', 'previous'):
                        if motion.get(key) is not None:
                            motion[key].pop('from_asset_id', None)
                    portrait = motion.get('portrait')
                    expression = engine_state['panel']['expression']
                    mode = portrait['mode'] if portrait else 0
                    history.anchor_mode = mode
                    if portrait:
                        byte = expression & 255
                        history.expressions[portrait['character_id']] = byte - 256 if byte > 127 else byte
                    defaults = dict(native_lifecycle=False, anchor_mode=mode,
                                    initial_portrait=dict(portrait) if portrait else None,
                                    initial_expression=expression, expression=expression,
                                    presentation_ms=2400, visuals_finished=False, housing_clipped=False,
                                    box_grow=False)
                    for key, value in defaults.items():
                        motion.setdefault(key, value)
                engine_state.setdefault('dialogue_history', asdict(history))
                if state.get('pending') and state['pending']['name'] == 'dialogue':
                    details = state['pending']['details']
                    details.pop('expression_from', None)
                    details.setdefault('initial_expression', details['expression'])
            # Version 23 adds exp-runtime v0.4.1's state (its own versions 17-19, numbered independently of this
            # fork's 17-22): the background pan, the Continue tab's expansion and the word grid's tile effects.
            if state['version'] < 23:
                state = deepcopy(state)
                # Preserve the older renderer's centered view until the next
                # native alignment request; never replay dialogue on load.
                state['engine']['background_pan'] = asdict(BackgroundPan())
                if state['engine'].get('word_grid') is not None:
                    state['engine']['word_grid'].update(pop_ms={}, explosions=[], glint_ms=100_000_000)
                motion = state['engine'].get('dialogue_animation')
                if motion is not None:
                    motion['continue_ms'] = 250 if motion['complete'] else 0
            if state['version'] < 18:
                state = deepcopy(state)
                state['engine'].update(int_arrays={}, status_icons=[-1, -1], music_paused=False)
            if state['version'] < 20:
                state = deepcopy(state)

                def add_serials(node):
                    node.setdefault('serial', 0)
                    for child in node.get('children', {}).values():
                        add_serials(child)
                tree = state['engine'].get('dt_view') or {}
                for key in ('root', 'current'):
                    if tree.get(key):
                        add_serials(tree[key])
            if state['version'] < 19:
                state = deepcopy(state)

                def add_ids(node):
                    node.setdefault('uid', 0)
                    node.setdefault('script', 0)
                    node.setdefault('primary', True)
                    for child in node.get('children', {}).values():
                        add_ids(child)
                root = (state['engine'].get('dt_view') or {}).get('root')
                if root:
                    add_ids(root)
            if state['version'] < 17:
                state = deepcopy(state)
                # Portrait expression changes (portrait_effects.py) did not exist yet: nothing is mid-change.

                def add_condition(node):
                    node.setdefault('condition', 0)
                    for child in node.get('children', {}).values():
                        add_condition(child)
                root = (state['engine'].get('dt_view') or {}).get('root')
                if root:
                    add_condition(root)
                motion = state['engine'].get('dialogue_animation')
                if motion is not None:
                    motion.update(age_ms=60000)
                    for key in ('portrait', 'previous', 'initial_portrait'):
                        if motion.get(key) is not None:
                            motion[key].setdefault('expression', 0)
            if state['version'] < 16:
                state = deepcopy(state)
                # The location pan state (speaker-side background alignment) did not exist yet.
                state['engine']['panel'].update(location_align=1, location_follow=True, location_fixed=0)
            if state['version'] < 15 and state['version'] >= 13:
                state = deepcopy(state)
                # Continuations used to be posts of their own; older saves keep them that way.
                for message in state['engine']['faceplace']['messages']:
                    message.setdefault('continuations', [])
                toast = state['engine'].get('faceplace_toast')
                if toast:
                    toast['message'].setdefault('continuations', [])
            if state['version'] < 14 and state['version'] >= 13:
                state = deepcopy(state)
                # The script-enable flags were approximated by "has content" before this version.
                state['engine']['dt_view']['enabled'] = state['engine']['dt_view'].get('root') is not None
                state['engine']['faceplace']['enabled'] = bool(state['engine']['faceplace'].get('messages'))
            if state['version'] < 13:
                state = deepcopy(state)
                # DTView/Faceplace state didn't exist before this version --
                # every real save predating it was written by a build that
                # never reached the iOS-HD-only services (101-120) these
                # model, so an empty tree/wall and no pending toast is
                # exactly what that save's engine state actually had.
                state['engine'].update(dt_view=asdict(DTView()), faceplace=asdict(FaceplaceWall()),
                                       faceplace_toast=None)
            if state['version'] < 11:
                state = deepcopy(state)
                state['engine']['title_screen'] = None
            if state['version'] < 10:
                state = deepcopy(state)
                state['engine']['speaker_names'] = asdict(SpeakerNames())
            if state['version'] < 9:
                state = deepcopy(state)
                state['engine']['message_panel'] = None
            if state['version'] < 8 and state['engine'].get('football') is not None:
                state = deepcopy(state)
                football = state['engine']['football']
                # Old saves lack both camera history and individual native
                # messages. Keep their current text/timers until the next play.
                football.update(visual_ms=0, camera_position=float(football['position']),
                                hud_position=float(football['position']), message_ids=[],
                                message_values=[], message_hold_ms=800, effects=[])
            if state['version'] < 7 and state['engine'].get('word_grid') is not None:
                state = deepcopy(state)
                # Older saves have no decorative clock or outgoing tile face.
                # Resume their board and VM exactly, with settled decoration.
                state['engine']['word_grid'].update(visual_ms=0, board_entry_ms=2000,
                                                    banner=None, transition=None)
            if state['version'] < 6:
                state = deepcopy(state)
                state['engine']['loading'] = None
                if state['engine'].get('dialogue_animation') is not None:
                    state['engine']['dialogue_animation']['relationship'] = None
            if state['version'] < 5:
                state = deepcopy(state)
                state['engine']['character_picker'] = None
                state['engine']['scene_badge'] = None
                state['engine']['next_dialogue_wobble'] = False
                if state['engine'].get('dialogue_animation') is not None:
                    state['engine']['dialogue_animation']['wobble_direction'] = 0
            if state['version'] < 4:
                state = deepcopy(state)
                state['engine']['dialogue_animation'] = None
            if state['version'] < 3:
                state = deepcopy(state)
                state['engine'].update(random48=dict(state=RAND48_INITIAL), word_game=None,
                                       random=asdict(NativeRandom()), word_grid=None,
                                       grid_tutorials_seen=False, sound_ids=[],
                                       football=None, football_scores=[None, None],
                                       next_dialogue_notice='', notice='', notice_ms=0)
            if legacy:
                state = deepcopy(state)
                state['engine']['panel'].update(presentation_mode=0, theme=-1, emphasis_theme=1)
            if state['content'] != resources.identity:
                raise SaveError('Save requires the same imported game and episode')
            if type(state['scene']) is not int or not 0 <= state['scene'] <= 65535:
                raise SaveError('Invalid saved scene ID')
            session = cls(resources, start_script=state['scene'])
            if state['script_sha256'] != digest(session.vm.program.to_bytes()):
                raise SaveError('Saved script does not match the loaded script')
            session.vm = KiwiVM.from_snapshot(session.vm.program, state['vm'])
            library_view = session.engine.dt_view          # the library's own tree, read when the session was made
            engine_state = dict(state['engine'])
            saved_view = dict(engine_state['dt_view'])
            serial = saved_view.pop('current_serial', None)     # (an older save embeds the tree and its current scene instead)
            embedded, wanted = saved_view.pop('root', None), saved_view.pop('current', None)
            for key, default in (('pending_result_index', 0), ('awaiting_result', False), ('enabled', False),
                                 ('last_was_result', False), ('version', 0), ('accumulators', [])):
                saved_view.setdefault(key, default)               # (fields older saves lack)
            engine_state['dt_view'] = dict(saved_view, root=None, current=None)
            session.engine = _typed_value(engine_state, EngineState,
                                          state_types=GAMES[game_id(resources)].STATE_TYPES)
            session._link_tree(library_view, serial, embedded, wanted)
            session._set_build()
            engine = session.engine
            engine.game_key = game_id(resources)
            engine.app_version = getattr(resources.library, 'app_info', {}).get('CFBundleVersion')
            engine.background_pan.validate()
            engine.dialogue_history.validate()
            engine.speaker_names.validate()
            if engine.title_screen is not None:
                engine.title_screen.validate()
            if not 0 <= engine.random48.state <= RAND48_MASK:
                raise SaveError('Invalid random generator state')
            if not 0 <= engine.random.state <= 0xffffffff:
                raise SaveError('Invalid native random generator state')
            if engine.word_game is not None:
                engine.word_game.validate()
            if engine.word_grid is not None:
                engine.word_grid.validate()
            if engine.football is not None:
                engine.football.validate()
            if engine.character_picker is not None:
                engine.character_picker.validate()
            if engine.scene_badge is not None:
                engine.scene_badge.validate()
            if engine.loading is not None:
                engine.loading.validate()
            if engine.message_panel is not None:
                engine.message_panel.validate()
            if (len(engine.football_scores) != 2 or
                    any(v is not None and not -32768 <= v <= 32767 for v in engine.football_scores)):
                raise SaveError('Invalid football scores')
            hd_motion = (engine.dialogue_animation if engine.hd_version is not None
                         or GAMES[engine.game_key].LETTER_NOTICE else None)
            if not 0 <= engine.notice_ms <= notice_limit(engine.notice, hd_motion):
                raise SaveError('Invalid dialogue notice timer')
            if len(engine.dynamic_strings) != 11 or len(engine.result_cells) != 10:
                raise SaveError('Invalid engine slot count')
            if any(v is not None and not -32768 <= v <= 32767 for v in engine.result_cells):
                raise SaveError('Invalid engine result word')
            if engine.choice_builder is not None:
                _validate_choice(engine.choice_builder)
            pending = state['pending']
            if pending is None and session.vm.pending is not None:
                raise SaveError('Suspended VM is missing its pending screen')
            if pending is not None:
                request = session.vm.pending
                name, details = pending['name'], pending['details']
                if not isinstance(details, dict):
                    raise SaveError('Invalid pending screen details')
                if name == 'loading' and engine.loading and not engine.loading.blocking:
                    # A nonwaiting service 91 has already popped its frame. The host
                    # gate pauses before the very next instruction, so the
                    # completed call is recoverable from the program and stack
                    # backing without inventing a suspended VM frame.
                    pc = session.vm.pc - 1
                    if request is not None or not 0 <= pc < len(session.vm.program.instructions):
                        raise SaveError('Invalid completed loading call')
                    instruction = session.vm.program.instructions[pc]
                    if (not ((instruction.opcode == 0x1f and instruction.operand >> 8 == 91)
                             or (instruction.opcode == 0x1e and instruction.operand == 91))
                            or session.vm.result != 0
                            or retained_word(session.vm) != 0):
                        raise SaveError('Loading gate does not match the completed VM call')
                    # Older register-count saves could only contain one argument.
                    count = (instruction.operand & 255 if instruction.opcode == 0x1f
                             else details.get('argument_count', 1))
                    address = session.vm.stack_base + session.vm.sp
                    if type(count) is not int or not 0 <= count <= 0x7ff5 - address:
                        raise SaveError('Invalid completed loading argument count')
                    args = tuple(session.vm.read_word(address + i) for i in range(count))
                    request = VMStop(StopKind.YIELD, pc, instruction.byte_offset, 91, args)
                if request is None:
                    raise SaveError('Pending screen has no suspended VM request')
                expected_kind = {'finished': StopKind.HALT, 'vm_pause': StopKind.PAUSE}.get(name, StopKind.YIELD)
                if request.kind != expected_kind:
                    raise SaveError('Pending screen does not match the VM stop')
                allowed = {'choice': (1, 4), 'character_picker': (78,), 'word_game': (71,), 'word_grid': (96,), 'football': (94,), 'dialogue': (13, 65, 15, 37, 76), 'text_input': (17, 40),
                           'presentation': (8,), 'loading': (91,), 'message_panel': (33,), 'download_poll': (9,),
                           'survey_confirmation': (9,), 'episode_exit': (7, 63),
                           'finished': (None,), 'vm_pause': (None,)}
                if game_id(resources) == 'cod':
                    for unsupported in ('word_grid', 'football', 'loading', 'survey_confirmation'):
                        allowed.pop(unsupported)
                if name != 'unhandled_yield' and (name not in allowed or request.yield_id not in allowed[name]):
                    raise SaveError('Pending screen does not match its native service')
                if name == 'choice':
                    _validate_choice(details)
                elif name == 'episode_exit':
                    closed = deepcopy(engine)
                    closed.close_episode()
                    if state['version'] < 12 or details or engine != closed:
                        raise SaveError('Episode exit does not match its cleared scene')
                elif name == 'survey_confirmation':
                    from .shs.survey import SURVEY_TEXT, SURVEY_TITLE, is_survey, script_response
                    panel = engine.message_panel
                    response = script_response(session.vm, engine.read_text)
                    # Survey receipts arrived with this fork's version 23 (exp-runtime's own 13).
                    if (state['version'] < 23 or not is_survey(request.args) or response is None
                            or details != dict(response_pc=response.pc)
                            or type(details['response_pc']) is not int or panel is None
                            or (panel.title, panel.text, panel.argument) != (SURVEY_TITLE, SURVEY_TEXT, 0)):
                        raise SaveError('Survey confirmation does not match its submission frame')
                elif name == 'loading':
                    expected_details = {}
                    if (engine.loading and not engine.loading.blocking and len(request.args) != 1
                            and session.vm.program.instructions[request.pc].opcode == 0x1e):
                        expected_details['argument_count'] = len(request.args)
                    if (engine.loading is None or details != expected_details
                            or engine.loading.blocking != loading_waits(session.vm, request)):
                        raise SaveError('Loading screen does not match its VM arguments')
                elif name == 'download_poll':
                    if (set(details) != {'elapsed_ms'} or type(details['elapsed_ms']) is not int
                            or not 0 <= details['elapsed_ms'] < POLL_WAIT_MS):
                        raise SaveError('Invalid poll download state')
                elif name == 'message_panel':
                    panel = engine.message_panel
                    if (panel is None or len(request.args) < 3 or details
                            or panel.argument != request.args[2]
                            or panel.title != engine.read_text(session.vm, request.args[0])
                            or panel.text != engine.read_text(session.vm, request.args[1])):
                        raise SaveError('Message panel does not match its VM arguments')
                elif name == 'character_picker':
                    _typed_value(details['text'], str)
                    if engine.character_picker is None or len(request.args) != 3:
                        raise SaveError('Character selection is missing its native state')
                    text, count, address = request.args
                    if (not 1 <= count <= 5 or
                            engine.character_picker.characters != [signed16(session.vm.read_word(address + i))
                                                               for i in range(count)]
                            or details['text'] not in (engine.resolve_text(session.vm, text), engine.substitute(
                                engine.read_text(session.vm, text), display=False))):
                        raise SaveError('Character selection does not match its VM arguments')
                elif name == 'word_game':
                    for key in ('title', 'text'):
                        _typed_value(details[key], str)
                    for key in ('character_id', 'portrait_mode'):
                        _typed_value(details[key], int)
                elif name == 'word_grid':
                    for key in ('background_id', 'left_character', 'left_expression', 'right_character', 'right_expression'):
                        _typed_value(details[key], int)
                elif name == 'dialogue':
                    for key in ('text', 'raw_text', 'speaker'):
                        _typed_value(details[key], str)
                    for key in ('character_id', 'expression', 'initial_expression', 'mode'):
                        _typed_value(details[key], int)
                    if legacy:
                        details = engine.present_dialogue(details['character_id'], details['expression'],
                                                          details['raw_text'], details['mode'], settled_relationship=True)
                        engine.background_pan.center()
                    else:
                        for key in ('visible_character_id', 'presentation_mode', 'theme',
                                    'emphasis_theme', 'page_start', 'page_end'):
                            _typed_value(details[key], int)
                        if (details['presentation_mode'] not in (1, 2, 3, 4)
                                or details['emphasis_theme'] not in (1, 2)
                                or not 0 <= details['page_start'] <= details['page_end'] <= len(details['text'])):
                            raise SaveError('Invalid dialogue presentation or page')
                    if state['version'] < 6:
                        change = engine.prepare_relationship(details['visible_character_id'], settled=True)
                        details['relationship'] = asdict(change) if change else None
                    change = _typed_value(details['relationship'], RelationshipChange | None)
                    if change is not None and details.get('status_icons'):
                        change.validate()          # service 37's settled icons: not from the property cache
                    elif change is not None:
                        change.validate()
                        if ((change.asset_id != -1 and change.asset_id not in GAMES[engine.game_key].RELATIONSHIP_ASSETS)
                                or change.character_id != details['visible_character_id']
                                or details['presentation_mode'] not in (1, 2)
                                or engine.numbers.get(engine.number_key(change.character_id, 3000)) != change.asset_id
                                or engine.numbers.get(engine.number_key(change.character_id, 3001)) != change.count):
                            raise SaveError('Relationship indicators do not match their NPC cache')
                    elif details['visible_character_id'] > 0 and details['presentation_mode'] in (1, 2):
                        raise SaveError('NPC dialogue is missing its relationship state')
                    if request.yield_id in (15, 76):
                        # HD's own case 0xf reads its first two words (engine.py); Android's and the
                        # iPhone's skip a negative prefix (shs/services.py).
                        refs = request.args
                        if request.yield_id == 15 and game_id(resources) == 'shs' and engine.hd_version is None:
                            from .shs.services import named_dialogue_refs
                            refs = named_dialogue_refs(request)
                        if (len(refs) < 2
                                or details['speaker'] not in (engine.resolve_text(session.vm, refs[0]), engine.substitute(
                                    engine.read_text(session.vm, refs[0]), display=False))
                                or details['raw_text'] != engine.read_text(session.vm, refs[1])
                                or details['text'] not in (engine.substitute(details['raw_text']),
                                                           engine.substitute(details['raw_text'], display=False))
                                or (details['character_id'], details['visible_character_id'],
                                    details['expression'], details['mode'], details['presentation_mode'],
                                    details['theme'], details['relationship']) != (-1, -1, 0, 0, 3, -1, None)):
                            raise SaveError('Named dialogue does not match its VM arguments')
                elif name == 'presentation':
                    for key in ('title', 'subtitle'):
                        _typed_value(details[key], str)
                    for key in ('asset_id', 'flag'):
                        _typed_value(details[key], int)
                    if len(request.args) != 4 or details != engine.title_details(session.vm, request.args):
                        raise SaveError('Title screen does not match its VM arguments')
                    if state['version'] < 11:
                        engine.title_screen = TitleScreen.settled()
                elif name == 'text_input':
                    for key in ('title', 'prompt', 'default'):
                        _typed_value(details[key], str)
                    if 'draft' in details:
                        _typed_value(details['draft'], str)
                session.pending = EngineAction(name, request, False, deepcopy(details))
                if name == 'dialogue':
                    saved_end = details.get('page_end')
                    # exp-runtime's own IPA save versions 14-15; this fork's saves gained IPA libraries only
                    # with its version 23, so none of them reflow.
                    reflow_ipa = (state['format'] == 'exp-runtime-save' and state['version'] < 16
                                  and getattr(getattr(resources, 'library', None), 'kind', None) == 'ipa')
                    rebuild_names = reflow_ipa and state['version'] < 15
                    if rebuild_names:
                        # v14 used a separate IPA layout with no name history.
                        # Earlier IPA saves retain the state before this name:
                        # use that basis so we do not advance it twice.
                        engine.speaker_names = SpeakerNames(deepcopy(engine.speaker_names.basis or {}))
                    if state['version'] >= 10 and not rebuild_names and hasattr(resources, 'dialogue_layout'):
                        names = engine.speaker_names
                        if names.basis is None:
                            raise SaveError('Dialogue is missing its speaker layout state')
                        check = SpeakerNames(deepcopy(names.basis))
                        resources.dialogue_layout().prepare_name(session.pending.details, check)
                        if check.fonts != names.fonts:
                            raise SaveError('Speaker layout does not match its saved font state')
                    session._prepare_dialogue(new_name=state['version'] < 10 or rebuild_names)
                    # Earlier saves either lack font history or used different
                    # IPA placement/metrics. Keep the read offset and reflow
                    # that page once without executing the pending VM call.
                    if state['version'] >= 10 and not reflow_ipa and session.pending.details['page_end'] != saved_end:
                        raise SaveError('Saved dialogue page does not match its layout')
                    if state['version'] < 4:
                        session.pending.details['initial_expression'] = session.pending.details['expression']
                        engine.dialogue_animation = DialogueAnimation.start(
                            session.pending.details, engine.character_art_variants,
                            history=engine.dialogue_history)
                        engine.dialogue_animation.native_lifecycle = False
                        engine.dialogue_animation.box_grow = False
                        engine.dialogue_animation.settle()
                    if state['version'] < 6 and engine.dialogue_animation is not None:
                        engine.dialogue_animation.relationship = RelationshipAnimation(change, 0) if change else None
                        if engine.dialogue_animation.relationship:
                            engine.dialogue_animation.relationship.settle()
            motion = engine.dialogue_animation
            if motion is not None:
                motion.validate()
                if not session.pending or session.pending.name in ('finished', 'episode_exit'):
                    raise SaveError('Dialogue animation does not match its pending screen')
                if motion.native_lifecycle and motion.portrait is not None:
                    expression = motion.expression if motion.presentation_ms >= EXPRESSION_MS else motion.initial_expression
                    byte = expression & 255
                    if (engine.dialogue_history.anchor_mode != motion.anchor_mode or
                            engine.dialogue_history.expressions.get(motion.portrait.character_id) !=
                            (byte - 256 if byte > 127 else byte)):
                        raise SaveError('Dialogue expression does not match its portrait history')
            if session.pending and session.pending.name == 'dialogue':
                details = session.pending.details
                if (motion is None or motion.text_length != len(details['text']) - details['page_start']
                        or motion.portrait != DialoguePortrait.from_details(details, engine.character_art_variants)
                        or motion.initial_portrait != DialoguePortrait.from_details(
                            dict(details, expression=details['initial_expression']), engine.character_art_variants)
                        or motion.expression != details['expression']
                        or motion.initial_expression != details['initial_expression']
                        or (asdict(motion.relationship.change) if motion.relationship else None) != details['relationship']):
                    raise SaveError('Dialogue animation does not match its text or portrait')
            if (engine.word_game is not None) != bool(session.pending and session.pending.name == 'word_game'):
                raise SaveError('Word game does not match its pending screen')
            if (engine.word_grid is not None) != bool(session.pending and session.pending.name == 'word_grid'):
                raise SaveError('Grid game does not match its pending screen')
            if (engine.football is not None) != bool(session.pending and session.pending.name == 'football'):
                raise SaveError('Football game does not match its pending screen')
            if (engine.character_picker is not None) != bool(session.pending and session.pending.name == 'character_picker'):
                raise SaveError('Character selection does not match its pending screen')
            if (engine.loading is not None) != bool(session.pending and session.pending.name == 'loading'):
                raise SaveError('Loading state does not match its pending screen')
            if (engine.message_panel is not None) != bool(session.pending and session.pending.name in
                                                         ('message_panel', 'survey_confirmation')):
                raise SaveError('Message panel does not match its pending screen')
            if (engine.title_screen is not None) != bool(session.pending and session.pending.name == 'presentation'):
                raise SaveError('Title screen does not match its pending screen')
            session.remaining_ms = state['remaining_ms']
            if session.remaining_ms is not None:
                if (session.pending is None or session.pending.name != 'choice'
                        or type(session.remaining_ms) is not int
                        or not 0 <= session.remaining_ms <= session.pending.details['timeout_ms']):
                    raise SaveError('Invalid saved choice timer')
            elif session.pending and session.pending.name == 'choice' and session.pending.details['timeout_ms']:
                raise SaveError('Timed choice is missing its remaining time')
            session.scene_loads = _typed_value(state['scene_loads'], int)
            if session.scene_loads < 0:
                raise SaveError('Invalid scene transition count')
            if (game_id(resources) == 'shs' and state['version'] < 3 and session.pending and session.pending.name == 'unhandled_yield'
                    and session.pending.request.yield_id in (71, 94, 96)):
                session.pending = engine.dispatch(session.vm, resource_exists=resources.exists)
            if (game_id(resources) == 'shs' and state['version'] < 5 and session.pending and session.pending.name == 'unhandled_yield'
                    and session.pending.request.yield_id == 78):
                session.pending = engine.dispatch(session.vm, resource_exists=resources.exists)
                engine.dialogue_animation = None
            if (game_id(resources) == 'shs' and state['version'] < 6 and session.pending and session.pending.name == 'unhandled_yield'
                    and session.pending.request.yield_id == 91):
                session.pending = engine.dispatch(session.vm, resource_exists=resources.exists)
                engine.dialogue_animation = None
            newly_supported = ((70, 94, 96, 97, 100) if game_id(resources) == 'cod'
                               else (4, 7, 9, 14, 15, 21, 33, 39, 63, 70, 76, 97))
            if (session.pending and session.pending.name == 'unhandled_yield'
                    and session.pending.request.yield_id in newly_supported):
                # Dispatch only the newly supported call from its validated
                # frame, without replaying previous input or random draws.
                if session.pending.request.yield_id == 4:
                    if len(session.pending.request.args) != 1 or engine.choice_builder is None:
                        raise SaveError('Choice stop is missing its builder or shuffle argument')
                if session.pending.request.yield_id == 9 and len(session.pending.request.args) < 2:
                    raise SaveError('Survey stop is missing its submission arguments')
                if (engine.dialogue_animation is None and engine.panel.presentation_mode and
                        (game_id(resources) == 'cod' or session.pending.request.yield_id in (14, 15, 21, 70, 76, 97))):
                    # Unsupported stops discarded their animation, but retained
                    # the visible panel. Recover its outgoing portrait identity
                    # for the new dialogue's entrance, without replaying its text.
                    panel = engine.panel
                    previous = dict(visible_character_id=panel.character_id,
                                    presentation_mode=panel.presentation_mode,
                                    expression=panel.expression, theme=panel.theme)
                    portrait = DialoguePortrait.from_details(previous, engine.character_art_variants)
                    engine.dialogue_animation = DialogueAnimation(
                        0, portrait=portrait, initial_portrait=portrait,
                        anchor_mode=portrait.mode if portrait else 0,
                        expression=panel.expression, initial_expression=panel.expression)
                    engine.dialogue_animation.settle()
                    if portrait is not None:
                        engine.dialogue_history.anchor_mode = portrait.mode
                        byte = panel.expression & 255
                        engine.dialogue_history.expressions[portrait.character_id] = byte - 256 if byte > 127 else byte
                session.pending = None
                session.advance()
            return session
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            if isinstance(error, SaveError):
                raise
            raise SaveError(f'Invalid save: {error}') from error

    def save(self, path: Path | None = None) -> Path:
        if self.pending is None:
            raise SaveError('Save requires a suspended screen or completed episode')
        path = Path(path) if path is not None else self.save_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                             prefix='.save-', delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(self.snapshot(), stream, ensure_ascii=False, separators=(',', ':'))
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return path

    @classmethod
    def load(cls, resources: EpisodeResources, path: Path):
        try:
            path = Path(path)
            if path.stat().st_size > 8 * 1024 * 1024:
                raise SaveError('Save exceeds supported size')
            return cls.from_snapshot(resources, json.loads(path.read_text(encoding='utf-8')))
        except (OSError, ValueError) as error:
            if isinstance(error, SaveError):
                raise
            raise SaveError(f'Cannot load save: {error}') from error
