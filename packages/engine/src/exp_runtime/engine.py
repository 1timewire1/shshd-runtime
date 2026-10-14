"""Verified subset of the native yield dispatcher for headless tracing.

These handlers reconstruct game state. Presentation requests and unknown
handlers remain pending; episode exits are terminal application handoffs.
See docs/ENGINE_ABI.md for native addresses and current limitations.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import ClassVar

from .games import GAMES

from .randomness import NativeRandom, Random48, pipe_list
from .minigames import WordGame
from .game_state import GameState
from .character_picker import CharacterPicker
from .scene_badge import SceneBadge
from .loading import LoadingScreen
from .message_panel import MessagePanel
from .speaker_names import SpeakerNames
from .title_screen import TitleScreen
from .relationships import RelationshipChange
from .dialogue_animation import DialogueAnimation, DialogueHistory
from .background import BackgroundPan
from .dialogue_notice import notice_lifetime
from .vm import KiwiVM, StopKind, VMError, VMStop, signed16


@dataclass(frozen=True)
class EngineAction:
    name: str
    request: VMStop
    completed: bool
    details: dict = field(default_factory=dict)


@dataclass
class PanelState:
    background_id: int = -1
    character_id: int = -1
    expression: int = 0
    speaker: str = ''
    text: str = ''
    mode: int = 0
    presentation_mode: int = 0
    theme: int = -1
    emphasis_theme: int = 1


@dataclass
class EngineState:
    # Derived from the validated library, never accepted from saved engine data.
    game_key: ClassVar[str] = 'shs'
    app_version: ClassVar[str | None] = None
    numbers: dict[int, int] = field(default_factory=dict)
    strings: dict[str, str] = field(default_factory=dict)
    character_names: dict[int, str] = field(default_factory=dict)
    character_art_bases: dict[int, int] = field(default_factory=dict)
    dynamic_strings: list[str] = field(default_factory=lambda: [''] * 11)
    ui_defaults: dict[int, int] = field(default_factory=dict)
    scheduled_scripts: list[tuple[int, bool]] = field(default_factory=list)
    audio_stopped: bool = False
    character_art_variants: dict[int, list[int]] = field(default_factory=dict)
    character_expressions: dict[int, int] = field(default_factory=dict)
    panel: PanelState = field(default_factory=PanelState)
    background_pan: BackgroundPan = field(default_factory=BackgroundPan)
    music_id: int = -1
    music_flag: bool = False
    sound_id: int = -1
    sound_serial: int = 0
    sound_ids: list[int] = field(default_factory=list)
    scene_value: int = 0
    last_input: str = ''
    result_cells: list[int | None] = field(default_factory=lambda: [None] * 10)
    choice_builder: dict | None = None
    random48: Random48 = field(default_factory=Random48)
    word_game: WordGame | None = None
    random: NativeRandom = field(default_factory=NativeRandom)
    word_grid: GameState | None = None
    grid_tutorials_seen: bool = False
    football: GameState | None = None
    football_scores: list[int | None] = field(default_factory=lambda: [None, None])
    next_dialogue_notice: str = ''
    notice: str = ''
    notice_ms: int = 0
    dialogue_animation: DialogueAnimation | None = None
    dialogue_history: DialogueHistory = field(default_factory=DialogueHistory)
    character_picker: CharacterPicker | None = None
    scene_badge: SceneBadge | None = None
    next_dialogue_wobble: bool = False
    loading: LoadingScreen | None = None
    message_panel: MessagePanel | None = None
    speaker_names: SpeakerNames = field(default_factory=SpeakerNames)
    title_screen: TitleScreen | None = None

    def clear_scene_expressions(self):
        """loadScript09NoGUI clears both 200-byte expression tables."""
        for table in (self.character_expressions, self.dialogue_history.expressions):
            for character in list(table):
                if 0 <= character < 200:
                    del table[character]

    def close_episode(self):
        """FUN_0007e614/0007e59c: dispose scene UI and cancel its work."""
        self.scheduled_scripts.clear()
        self.numbers.clear()  # FUN_0009623c frees the numeric key/value arrays.
        # The same reset zeros 200 expression bytes, but retains names, art,
        # replacement strings, dynamic strings, UI results and random streams.
        self.clear_scene_expressions()
        self.panel = PanelState()
        self.background_pan.center()
        self.background_pan.automatic = True  # 0007e59c resets automatic panning.
        self.dialogue_animation = self.scene_badge = None
        self.dialogue_history = DialogueHistory()
        self.word_game = self.word_grid = self.football = None
        self.character_picker = self.loading = self.message_panel = self.title_screen = None
        self.choice_builder = None
        self.next_dialogue_notice = self.notice = self.last_input = ''
        self.notice_ms = self.scene_value = 0

    @staticmethod
    def number_key(owner: int, key: int) -> int:
        # Native addition of signed short operands, not OR of unsigned halves.
        return (signed16(owner) * 0x10000 + signed16(key)) & 0xFFFFFFFF

    def dialogue_presentation(self, character: int, expression: int):
        """FUN_000ab048/000ab344: visible character and panel variant.

        Service 75 selects the narrator by ID. Its script name is metadata;
        no string (including the usual name 'Event') identifies narration.
        """
        if character == self.ui_defaults.get(75, -1):
            return 4, -1, -1
        variants = self.character_art_variants.get(character, ())
        if character < 0 or not variants or variants[expression % len(variants)] < 0:
            return 3, -1, -1
        mode = 1 if character == self.ui_defaults.get(74, -1) else 2
        return mode, character, self.numbers.get(self.number_key(character, 651), 0)

    def present_dialogue(self, character: int, expression: int, raw_text: str, mode: int, *,
                         settled_relationship=False, speaker: str | None = None):
        """Keep script prefixes separate from panel modes and explicit speakers."""
        text = '(' + raw_text + ')' if mode == -2 else '`' + raw_text + '`' if mode == -3 else raw_text
        text = self.substitute(text)
        old = self.dialogue_animation.portrait if self.dialogue_animation else None
        initial_expression = self.dialogue_history.expressions.get(character, 0) if (
            old is not None and old.character_id == character) else 0
        if speaker is None:
            presentation, visible, theme = self.dialogue_presentation(character, expression)
            if presentation in (1, 2) and self.dialogue_presentation(character, initial_expression)[0] == 3:
                presentation, visible, theme = 3, -1, -1
            if presentation in (1, 2):
                self.panel.speaker = self.substitute(self.character_names.get(character, ''))
        else:
            # Service 76: ab344(3) -> ab048(-1,0), then aa028(name).
            # This is named dialogue without an NPC or portrait, not narration.
            presentation, visible, theme = 3, -1, -1
            self.panel.speaker = self.substitute(speaker)
        # The name remains on the panel; narrator mode 4 only hides it.
        speaker = '' if presentation == 4 else self.panel.speaker
        if theme in (1, 2):
            self.panel.emphasis_theme = theme
        self.panel.character_id, self.panel.expression = visible, expression
        self.panel.text, self.panel.mode = text, mode
        self.panel.presentation_mode, self.panel.theme = presentation, theme
        self.background_pan.dialogue(presentation)
        if self.next_dialogue_notice:
            self.notice, self.next_dialogue_notice = self.next_dialogue_notice, ''
            self.notice_ms = notice_lifetime(self.notice)
        wobble, self.next_dialogue_wobble = self.next_dialogue_wobble, False
        relationship = self.prepare_relationship(visible if presentation in (1, 2) else -1, settled=settled_relationship)
        return dict(text=text, raw_text=raw_text, character_id=character,
                    visible_character_id=visible, speaker=speaker, expression=expression,
                    initial_expression=initial_expression,
                    mode=mode, presentation_mode=presentation, theme=theme,
                    emphasis_theme=self.panel.emphasis_theme, box_wobble=wobble,
                    relationship=asdict(relationship) if relationship else None)

    def prepare_relationship(self, character: int, *, settled=False):
        """FUN_000ab048: snapshot and write UI caches once per NPC dialogue."""
        if character <= 0:
            return None
        owned = lambda key: self.numbers.get(self.number_key(character, key), 0)
        value = owned(407)  # 0x197 in FUN_000ab048 and FUN_000a90f0.
        heart, skull, smile = GAMES[self.game_key].RELATIONSHIP_ASSETS
        asset = (-1 if owned(629) == 1 else skull if value < 0 else
                 heart if character == self.numbers.get(self.number_key(0, 601), 0) else smile)
        count = {-3: 3, -2: 2, -1: 1, 0: 1, 1: 2, 2: 3}.get(value, 4)
        change = RelationshipChange(character, asset, count,
                                    asset if settled else signed16(owned(3000)),
                                    count if settled else owned(3001))
        change.validate()
        self.numbers[self.number_key(character, 3000)] = asset
        self.numbers[self.number_key(character, 3001)] = count
        if not settled and change.sound is not None:
            self.sound_id, self.sound_ids = change.sound, [change.sound]
            self.sound_serial += 1
        return change

    def read_text(self, vm: KiwiVM, reference: int) -> str:
        """FUN_0009f420/0009f258: packed text or a runtime string slot."""
        reference = signed16(reference)
        if reference == -1:
            return ''
        if reference >= 0x7FF5:
            return self.dynamic_strings[reference - 0x7FF5]
        chars = bytearray()
        for address in range(reference, 0x7FF5):
            word = vm.read_word(address) & 0xFFFF
            for byte in (word >> 8, word & 0xFF):
                if byte == 0:
                    return chars.decode('latin-1')
                chars.append(byte)
        raise VMError(f'unterminated text at data word {reference}')

    def substitute(self, text: str) -> str:
        """FUN_00096c9c; retain cycle checks for unsupported replacement loops."""
        seen = set()
        for _ in range(100):
            if text in seen:
                raise VMError('cyclic text substitution')
            seen.add(text)
            changed = False
            for key, value in self.strings.items():
                if key and key in text:
                    if key in value:
                        raise VMError(f'self-referencing text substitution {key!r}')
                    text = text.replace(key, value)
                    changed = True
            if not changed:
                return text
        raise VMError('text substitution limit exceeded')

    def resolve_text(self, vm: KiwiVM, reference: int) -> str:
        """FUN_0009f9fc/00096c9c applies stored text substitutions repeatedly."""
        return self.substitute(self.read_text(vm, reference))

    def title_details(self, vm: KiwiVM, args):
        # 0009fa3c does not dereference a negative title. Its Android
        # promotional branch is separate from the title card itself.
        return dict(title='' if args[0] < 0 else self.resolve_text(vm, args[0]),
                    subtitle=self.resolve_text(vm, args[1]), asset_id=args[2], flag=args[3])

    @staticmethod
    def write_text(vm: KiwiVM, address: int, text: str):
        """FUN_00056b78: complete packed words, including NUL and zero padding."""
        data = text.split('\0', 1)[0].encode('latin-1') + b'\0'
        if len(data) % 2:
            data += b'\0'
        addresses = [signed16(address + i) for i in range(len(data) // 2)]
        if any(not (0 <= a < len(vm.data) or vm.stack_base <= a < 0x7ff5) for a in addresses):
            raise VMError('Packed string destination exceeds writable VM memory')
        for offset, destination in enumerate(addresses):
            vm.write_word(destination, int.from_bytes(data[offset * 2:offset * 2 + 2], 'big'))

    @staticmethod
    def _format_name(text: str) -> str:
        # Case 49 changes case at spaces, preserving $VARIABLE tokens.
        if text.startswith('$'):
            return text
        result = []
        first = True
        for char in text:
            byte = ord(char)
            if byte == 0x20:
                first = True
            else:
                if first and (0x61 <= byte <= 0x7A or 0xE0 <= byte <= 0xFC):
                    byte -= 0x20
                elif not first and (0x41 <= byte <= 0x5A or 0xC0 <= byte <= 0xDC):
                    byte += 0x20
                first = False
            result.append(chr(byte))
        return ''.join(result)

    def dispatch(self, vm: KiwiVM, *, resource_exists=None, dialogue_override=None) -> EngineAction:
        request = vm.pending
        if request is None or request.kind != StopKind.YIELD:
            raise VMError('engine dispatch requires a pending yield')
        y, args = request.yield_id, request.args
        if GAMES[self.game_key].DISPATCH is not None:
            action = GAMES[self.game_key].DISPATCH(self, vm, resource_exists=resource_exists)
            if action is not None:
                return action

        def need(count):
            if len(args) != count:
                raise VMError(f'yield {y} at pc {request.pc}: expected {count} arguments, got {len(args)}')

        def at_least(count):
            if len(args) < count:
                raise VMError(f'yield {y} at pc {request.pc}: needs at least {count} arguments')

        def complete(action_name, result=0, **details):
            vm.resume(result)
            return EngineAction(action_name, request, True, dict(result=result, **details))

        if y in (7, 63):
            # Both cases enter 0007e614 without reading any arguments. The
            # native scene destroys its VMs; there is no script continuation.
            # Retain this final frame for diagnostics/save validation, never
            # as a callback that could run the following instruction.
            self.close_episode()
            return EngineAction('episode_exit', request, False)
        if y == 0:
            at_least(1)
            slot, format_at = (1 - args[0], 1) if args[0] < 0 else (0, 0)
            if not 0 <= slot < len(self.dynamic_strings):
                raise VMError('Formatting destination is outside the native string slots')
            at_least(format_at + 1)
            pattern = self.read_text(vm, args[format_at])  # Copy before clearing aliased scratch slot 10.
            self.dynamic_strings[10] = ''
            position, argument = 0, format_at + 1
            while position < len(pattern):
                char = pattern[position]
                if char == '%' and position + 1 < len(pattern) and pattern[position + 1] in 'cds':
                    at_least(argument + 1)
                    spec, value = pattern[position + 1], args[argument]
                    char = (self.read_text(vm, value) if spec == 's' else str(signed16(value))
                            if spec == 'd' else chr(value & 0xff))
                    position += 1
                    argument += 1
                self.dynamic_strings[10] += char
                position += 1
            self.dynamic_strings[slot] = self.dynamic_strings[10]
            return complete('format_string', 0x7ff5 + slot, slot=slot)
        if y in (50, 51):
            need(4 if y == 50 else 3)
            owner, key, bit = args[:3]
            address = self.number_key(owner, key)
            value = self.numbers.get(address, 0)
            shift = bit & 0xff  # ARM register-shift amount, not modulo 32.
            if y == 51:
                return complete('get_number_bit', (value >> shift) & 1, owner=owner, key=key, bit=bit)
            mask = (1 << shift) if shift < 32 else 0
            value = (value | mask) if args[3] == 1 else (value & ~mask)
            value &= 0xffffffff
            self.numbers[address] = value - 0x100000000 if value & 0x80000000 else value
            return complete('set_number_bit', owner=owner, key=key, bit=bit, value=args[3])
        if y in (44, 54, 52):
            need(3 if y == 52 else 2)
            owner, key, value = args if y == 52 else (0, *args)
            self.numbers[self.number_key(owner, key)] = value
            return complete('set_number', owner=owner, key=key, value=value)
        if y in (45, 55, 53):
            need(2 if y == 53 else 1)
            owner, key = args if y == 53 else (0, args[0])
            result = self.numbers.get(self.number_key(owner, key), 0)
            return complete('get_number', result, owner=owner, key=key)
        if y == 46:
            need(2)
            key, value = (self.read_text(vm, ref) for ref in args)
            self.strings[key] = value
            return complete('set_string', key=key, value=value)
        if y == 47:
            need(3)
            slot = ~args[2]
            if not 0 <= slot < len(self.dynamic_strings):
                raise VMError(f'yield 47: invalid string slot selector {args[2]}')
            key = self.read_text(vm, args[0])
            value = self.strings.get(key, '')
            if not value:
                value = self.read_text(vm, args[1])
                self.strings[key] = value
            self.dynamic_strings[slot] = value
            return complete('get_string_with_default', 0x7FF5 + slot,
                            key=key, value=value, slot=slot)
        if y in (49, 64):
            need(3 if y == 49 else 2)
            name = self.read_text(vm, args[1])
            if y == 49 and args[2]:
                name = self._format_name(name)
            self.character_names[args[0]] = name
            return complete('set_character_name', character_id=args[0], name=name)
        if y == 72:
            need(2)
            self.character_art_bases[args[0]] = args[1]
            base = args[1]
            self.character_art_variants[args[0]] = [
                base + n if base > 0 and resource_exists and resource_exists(base + n) else base
                for n in range(5)]
            return complete('set_character_art_base', character_id=args[0], asset_id=args[1])
        if y == 73:
            need(1)
            if args[0] not in self.character_art_bases:
                raise VMError(f'Art requested for uninitialized character {args[0]}')
            return complete('get_character_art_base', self.character_art_bases[args[0]])
        if y == 5:
            need(2)
            byte = args[1] & 255
            self.character_expressions[args[0]] = byte - 256 if byte > 127 else byte
            return complete('set_character_expression')
        if y == 39:
            # FUN_000a7cd0 marks panel 3 for removal; no arguments are read
            # and no UI callback is requested. Retire its presentation state.
            self.panel = PanelState()
            self.background_pan.center()
            self.dialogue_animation = None
            self.next_dialogue_notice, self.notice, self.notice_ms = '', '', 0
            return complete('close_dialogue_panel')
        if y in (11, 34, 35, 86):
            at_least(4 if y == 35 else 3 if y == 86 else 2)
            base, variant = (args[2], args[1]) if y == 35 else ((args[0], args[1]) if y == 86 else (args[1], args[0]))
            if base != -2:
                candidate = base + variant if base >= 0 and variant in (1, 2) else base
                self.panel.background_id = candidate if not resource_exists or resource_exists(candidate) else base
                if base >= 0:
                    # 000a92f4 replaces the node even when its ID is unchanged.
                    self.background_pan.center()
            if y == 35:
                self.panel.character_id, self.panel.expression = args[0], max(0, args[3])
                self.panel.presentation_mode, _, _ = self.dialogue_presentation(
                    self.panel.character_id, self.panel.expression)
            self.background_pan.dialogue(self.panel.presentation_mode)
            return complete('set_background', asset_id=self.panel.background_id)
        if y == 97:
            at_least(2)
            self.background_pan.configure(args[0] != 0, args[1])
            return complete('set_background_pan', automatic=self.background_pan.automatic,
                            alignment=self.background_pan.alignment)
        if y == 16:
            need(1)
            self.scene_value = args[0]
            return complete('set_scene_value', value=args[0])
        if y in (74, 75):
            need(1)
            self.ui_defaults[y] = args[0]
            return complete('set_ui_default', slot=y, value=args[0])
        if y == 10:
            need(2)
            self.scheduled_scripts.append((args[0], args[1] != 0))
            return complete('schedule_script', file_id=args[0], flag=args[1] != 0)
        if y == 81:
            need(1)
            self.audio_stopped = True
            self.music_id = -1
            return complete('stop_audio')
        if y == 82:
            need(0)
            # FUN_000a3040 requests 1000ms from the optional vibrator, only
            # when present and enabled. Desktop has no vibrator backend.
            return complete('vibrate', duration_ms=1000)
        if y in (79, 80):
            need(1 if y == 79 else 2)
            if y == 80 or args[0] in GAMES[self.game_key].MUSIC_RANGE:
                self.music_id = args[0]
                self.music_flag = bool(args[1]) if y == 80 else False
                self.audio_stopped = False
            else:
                self.sound_id = args[0]
                self.sound_ids = [args[0]]
                self.sound_serial += 1
            return complete('request_audio', asset_id=args[0])
        if y == 18:  # Explicit default/no-op in this Android dispatcher.
            need(0)
            return complete('native_noop')
        if y == 99:
            need(1)
            # The supported release's FUN_00082adc is literally MOV R0,#0;
            # BX LR. The dispatcher takes its ordinary completion path.
            return complete('native_noop')
        if y == 88:
            need(1)
            self.next_dialogue_notice = self.resolve_text(vm, args[0])
            return complete('set_next_dialogue_notice', text=self.next_dialogue_notice)
        if y == 89:
            need(0)
            self.next_dialogue_wobble = True
            return complete('wobble_next_dialogue')
        if y == 90:
            need(2)
            text = self.resolve_text(vm, args[1]) if args[1] != -1 else ''
            if args[0] == -1:
                self.scene_badge = None
            else:
                previous = self.scene_badge
                self.scene_badge = SceneBadge(args[0], text, previous.blue if previous else text == 'Free Time',
                                             previous.elapsed_ms if previous else 0)
                self.scene_badge.validate()
            return complete('set_scene_badge', asset_id=args[0], text=text)
        if y == 8:
            need(4)
            self.title_screen = TitleScreen()
            return EngineAction('presentation', request, False, self.title_details(vm, args))
        if y == 33:
            at_least(3)
            # 0009f420, not 0009f9fc: these two texts are NOT substituted.
            panel = MessagePanel(self.read_text(vm, args[0]), self.read_text(vm, args[1]), args[2])
            panel.validate()
            self.message_panel = panel
            return EngineAction('message_panel', request, False)
        if y in (1, 2):
            need(8 if y == 1 else 6)
            title = self.resolve_text(vm, args[0])
            text = self.resolve_text(vm, args[2]) if y == 1 and args[2] >= 0 else ''
            if y == 1:
                options = self.resolve_text(vm, args[1]).split('|')
                # FUN_000b04b8 leaves a blank last field when it is whitespace.
                if options and not options[-1].strip():
                    options[-1] = ''
                character = self.ui_defaults.get(74, -1) if args[5] == -2 else args[5]
                return EngineAction('choice', request, False, dict(
                    title=title, text=text, options=options, values=list(range(len(options))),
                    enabled=[True] * len(options), timeout_ms=max(0, args[3]),
                    timeout_result=args[4], character_id=character, portrait_mode=args[7],
                ))
            self.choice_builder = dict(title=title, text=self.resolve_text(vm, args[1]),
                                       options=[], values=[], enabled=[], timeout_ms=max(0, args[2]),
                                       timeout_result=args[3], character_id=args[4], portrait_mode=args[5])
            return complete('begin_choice')
        if y == 78:
            need(3)
            text, count, address = args
            if not 1 <= count <= 5:
                raise VMError('Character selection requires 1 to 5 character IDs')
            characters = [signed16(vm.read_word(address + i)) for i in range(count)]
            prompt = self.resolve_text(vm, text)
            self.character_picker = CharacterPicker.start(characters)
            return EngineAction('character_picker', request, False, dict(text=prompt))
        if y == 71:
            need(8)
            good, bad = (pipe_list(self.read_text(vm, ref)) for ref in args[2:4])
            if len(good) < 2 or len(bad) < 3 or args[4] <= 0:
                return EngineAction('unhandled_yield', request, False, dict(
                    reason='Unsupported word-game lists or nonpositive duration'))
            game = WordGame(good, bad, args[4], args[7], args[4], args[7])
            game.deal(self.random48)
            self.word_game = game
            # FUN_000b06bc deliberately supplies an empty title to b033c;
            # unlike ordinary choices these text arguments are not substituted.
            return EngineAction('word_game', request, False, dict(
                title='', text=self.read_text(vm, args[1]),
                character_id=args[5], portrait_mode=args[6]))
        if y == 3:
            need(3)
            if self.choice_builder is None:
                raise VMError('Choice option without a choice builder')
            builder = self.choice_builder
            builder['options'].append(self.resolve_text(vm, args[0]))
            builder['values'].append(len(builder['values']) if args[1] == -999 else args[1])
            builder['enabled'].append(args[2] != 0)
            return complete('add_choice_option')
        if y == 4:
            need(1)
            if self.choice_builder is None:
                raise VMError('Choice display without a choice builder')
            details = deepcopy(self.choice_builder)
            if args[0]:
                # 000aeee4: one draw per row from the shared game LCG, with
                # every partner drawn from the full list (not Fisher-Yates).
                # Only labels and return mappings move; row flags stay put.
                count = len(details['options'])
                for index in range(count):
                    other = self.random.below(count)
                    for key in ('options', 'values'):
                        items = details[key]
                        items[index], items[other] = items[other], items[index]
            self.choice_builder = None
            return EngineAction('choice', request, False, details)
        if y in (17, 40):
            need(3)
            return EngineAction('text_input', request, False, dict(
                title=self.resolve_text(vm, args[0]), prompt=self.resolve_text(vm, args[1]),
                default=self.resolve_text(vm, args[2])))
        if y == 24:
            need(2)
            return complete('text_equal', int(self.read_text(vm, args[0]) == self.read_text(vm, args[1])))
        if y == 25:
            need(2)
            text = self.read_text(vm, args[0]) + self.read_text(vm, args[1])
            self.write_text(vm, args[0], text)
            return complete('append_text', destination=args[0])
        if y == 27:
            need(1)
            return complete('random_below', self.random.below(args[0]) if args[0] > 0 else 0, bound=args[0])
        if y == 28:
            need(1)
            self.write_text(vm, args[0], self.last_input)
            return complete('copy_last_input', destination=args[0])
        if y == 29:
            need(1)
            if not 0 <= args[0] < len(self.result_cells) or self.result_cells[args[0]] is None:
                raise VMError('Read of uninitialized UI result cell')
            return complete('get_ui_result', self.result_cells[args[0]])
        if y == 76:
            at_least(2)
            speaker, text = (self.read_text(vm, ref) for ref in args[:2])
            return EngineAction('dialogue', request, False,
                                self.present_dialogue(-1, 0, text, 0, speaker=speaker))
        if y in (13, 65):
            if len(args) < 2:
                raise VMError(f'yield 13 at pc {request.pc}: incomplete dialogue arguments')
            text_index = 1 if y == 65 or args[0] < 0 else 0
            if y == 65:
                need(3)
            if len(args) <= text_index + 1:
                raise VMError(f'yield 13 at pc {request.pc}: missing speaker argument')
            character_id = args[0] if y == 65 else args[text_index + 1]
            override_at = 2 if y == 65 else text_index + 2
            expression = self.character_expressions.get(character_id, 0)
            if len(args) > override_at and args[override_at] != -1:
                expression = (args[override_at] + 128) % 256 - 128
            expression = max(0, expression)
            raw_text = (self.read_text(vm, args[text_index]) if dialogue_override is None
                        else dialogue_override)
            mode = args[0] if y == 13 and text_index and args[0] in (-2, -3) else 0
            return EngineAction('dialogue', request, False,
                                self.present_dialogue(character_id, expression, raw_text, mode))
        return EngineAction('unhandled_yield', request, False)
