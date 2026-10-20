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
from .dt_state import CLEARED_WITH_CHARACTER, read_state
from .dtview_faceplace import DTView, FaceplaceToast, FaceplaceWall
from .vm import KiwiVM, StopKind, VMError, VMStop, signed16


# How long the poll's "Loading / Please wait..." bar shows before the failed download returns 0 to the script (the app waits for the
# network to fail, which takes as long as it takes; this is a fixed stand-in).
POLL_WAIT_MS = 1000


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
    # HD's location layer pans by speaker (GameModel::alignLocation): 1 left edge flush, 2 centered, 3 right
    # edge flush. `location_follow` is the pan flag every script load sets; `location_fixed` the mode a
    # script pinned with yield 97 (GameModel::setLocationPan).
    location_align: int = 1
    location_follow: bool = True
    location_fixed: int = 0


NATIVE_DEFAULT_YIELDS = frozenset((12, 14, 19, 20, 21, 23, 31, 41, 42, 48, 62, 67, 68, 69, 77, 92, 93, 100))
# Services this fork models from SHS HD's syscall table (NATIVE_DEFAULT_YIELDS included). Other games keep
# exp-runtime's handling: their own dispatch first, and these remain explicit unsupported stops.
SHS_HD_YIELDS = NATIVE_DEFAULT_YIELDS | frozenset((
    6, 15, 22, 26, 30, 32, 36, 37, 38, 43, 56, 57, 58, 59, 60, 61, 66, 83, 84, 85, 87, 98,
    *range(101, 121)))


@dataclass
class EngineState:
    # Not saved: the HD build's app version when an HD app bundle is imported (Session sets it); switches the
    # few services whose HD handler differs from Android's.
    hd_version = None
    # Not saved: the last link a script asked service 100 to open (a no-op in HD; see dispatch), for the host.
    store_link = ''
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
    # SHSEntityTable's int-array properties (services 56-59), keyed like `numbers`, and the two values of the
    # last setStatusIcons (service 38). `music_paused` is SHSSoundManager::pauseMusic (service 83).
    int_arrays: dict[int, list[int]] = field(default_factory=dict)
    status_icons: list[int] = field(default_factory=lambda: [-1, -1])
    music_paused: bool = False
    panel: PanelState = field(default_factory=PanelState)
    background_pan: BackgroundPan = field(default_factory=BackgroundPan)
    music_id: int = -1
    music_flag: bool = False
    # Playback state, not saved fields: the last service 81's fade-out, and a count of music requests and stops so the
    # player sees the same cue asked for again (music_stream.py).
    music_stop_fade_ms = 0
    music_requests = 0
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
    notice_mode: int = 0
    dialogue_animation: DialogueAnimation | None = None
    dialogue_history: DialogueHistory = field(default_factory=DialogueHistory)
    character_picker: CharacterPicker | None = None
    scene_badge: SceneBadge | None = None
    next_dialogue_wobble: bool = False
    loading: LoadingScreen | None = None
    message_panel: MessagePanel | None = None
    speaker_names: SpeakerNames = field(default_factory=SpeakerNames)
    title_screen: TitleScreen | None = None
    dt_view: DTView = field(default_factory=DTView)
    faceplace: FaceplaceWall = field(default_factory=FaceplaceWall)
    faceplace_toast: FaceplaceToast | None = None

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
        self.int_arrays.clear()
        self.music_paused = False
        # The same reset zeros 200 expression bytes, but retains names, art,
        # replacement strings, dynamic strings, UI results and random streams.
        self.clear_scene_expressions()
        self.panel = PanelState()
        self.background_pan.center()
        self.background_pan.automatic = True  # 0007e59c resets automatic panning.
        self.dialogue_animation = self.scene_badge = self.faceplace_toast = None
        self.dialogue_history = DialogueHistory()
        self.word_game = self.word_grid = self.football = None
        self.character_picker = self.loading = self.message_panel = self.title_screen = None
        self.choice_builder = None
        self.next_dialogue_notice = self.notice = self.last_input = ''
        self.notice_ms = self.notice_mode = self.scene_value = 0

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
                         settled_relationship=False, speaker: str | None = None, status_icons=None):
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
        self.align_location()
        self.background_pan.dialogue(presentation)
        if self.next_dialogue_notice:
            self.notice, self.next_dialogue_notice = self.next_dialogue_notice, ''
            self.notice_ms, self.notice_mode = notice_lifetime(self.notice), 0
        wobble, self.next_dialogue_wobble = self.next_dialogue_wobble, False
        if status_icons is not None and visible > 0 and presentation in (1, 2):
            # Service 37 does not call setCurrentSpeaker: the icons stay as they were (or as service 38 set
            # them) and are shown settled, without reading or writing the relationship properties.
            relationship = RelationshipChange(visible, *status_icons, *status_icons)
            try:
                relationship.validate()
            except ValueError:
                relationship = None
        else:
            relationship = self.prepare_relationship(visible if presentation in (1, 2) else -1,
                                                     settled=settled_relationship)
        extra = dict(status_icons=True) if status_icons is not None else {}
        return dict(**extra, text=text, raw_text=raw_text, character_id=character,
                    visible_character_id=visible, speaker=speaker, expression=expression,
                    initial_expression=initial_expression,
                    mode=mode, presentation_mode=presentation, theme=theme,
                    emphasis_theme=self.panel.emphasis_theme, box_wobble=wobble,
                    relationship=asdict(relationship) if relationship else None)

    def dt_add_node(self, node_type: int, label: str, exw: int, pc: int = 0):
        """`SHSDTView addNode`, with the node's ids: the entity properties 2000 * 1000 + 0x3e9 of owner 0, and the
        short at `SHSEngine+0x62ef8` = GameModel+0x2a4 = the running script's (GameModel+0x274) +0x30, its program
        counter: where in the script the node was added. A join reached again from another branch therefore has the
        ids of the first join there and merges into it."""
        uid = self.numbers.get(self.number_key(0, 2000), 0) * 1000 + self.numbers.get(self.number_key(0, 0x3e9), 0)
        return self.dt_view.add_node(node_type, label, exw, uid, pc, state=read_state(self))

    def align_location(self):
        """SHSUIDialog::animateLocationLayer: speaker type 1 aligns the location left, type 2 right; the
        narrator and named voices leave it where it is. A pinned pan mode (yield 97) overrides the speaker."""
        panel = self.panel
        side = {1: 1, 2: 3}.get(panel.presentation_mode)
        if side is None:
            return
        mode = side if panel.location_follow else panel.location_fixed
        if mode in (1, 2, 3):
            panel.location_align = mode

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

    def _alert_for(self, post) -> None:
        """A continuation of the post whose alert is still showing extends that alert; otherwise it alerts."""
        toast = self.faceplace_toast
        if (toast is not None and toast.message.kind == post.kind and toast.message.text == post.text
                and toast.message.from_id == post.from_id):
            toast.message = post
        else:
            self.faceplace_toast = FaceplaceToast(post)

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

    def substitute(self, text: str, *, display=True) -> str:
        """FUN_00096c9c; retain cycle checks for unsupported replacement loops. Everything shown on screen passes
        through here (scripts compare and store raw text through `read_text`), so a game's DISPLAY_CHARACTERS apply
        last, and only to what is shown (`display=False` gives the native result)."""
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
                if display:
                    for character, shown in getattr(GAMES[self.game_key], 'DISPLAY_CHARACTERS', {}).items():
                        text = text.replace(character, shown)
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
        if self.game_key != 'shs' and y in SHS_HD_YIELDS:
            return EngineAction('unhandled_yield', request, False)

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
            # Real HD Football Star bytecode calls this on a character with
            # no prior yield-72 (confirmed live: byte-identical to Android's
            # script through this point, then diverges -- Android calls a
            # subroutine here that HD's compiled script doesn't, going
            # straight to this yield instead). Native's own entity table is
            # zero-initialized storage, not a sentinel/error path, so an
            # unset character's base portrait reads as 0 -- raising here
            # was an untested assumption from Android-only evidence.
            return complete('get_character_art_base', self.character_art_bases.get(args[0], 0))
        if y == 5:
            need(2)
            byte = args[1] & 255
            self.character_expressions[args[0]] = byte - 256 if byte > 127 else byte
            return complete('set_character_expression')
        if y == 39:
            # FUN_000a7cd0 marks panel 3 for removal; no arguments are read
            # and no UI callback is requested. Retire its presentation state.
            #
            # Real device correction: resetting to a fully blank PanelState()
            # also discarded background_id, whose own dataclass default is
            # -1 -- confirmed live, this is the real cause of the black
            # background seen immediately after the football minigame (whose
            # script closes the dialogue panel via this yield right before
            # entering it): the scene background is conceptually a separate
            # layer from the closing text-box widget, not something a script
            # would expect a bare panel-close to erase; the very next
            # dialogue lines after football rendered as -1 (blank) for
            # several steps until an explicit yield 35 set a new background.
            self.panel = PanelState(background_id=self.panel.background_id)
            self.dialogue_animation = None
            self.next_dialogue_notice, self.notice, self.notice_ms, self.notice_mode = '', '', 0, 0
            return complete('close_dialogue_panel')
        if y in (11, 34, 35, 86):
            at_least(4 if y == 35 else 3 if y == 86 else 2)
            base, variant = (args[2], args[1]) if y == 35 else ((args[0], args[1]) if y == 86 else (args[1], args[0]))
            # Real device correction: this only special-cased base == -2 as
            # "keep the current background," so base == -1 fell through and
            # got written as panel.background_id literally -- rendering as a
            # blank/black background (confirmed live: the real dialogue line
            # immediately after the football minigame, whose script sets
            # base=-1 right beforehand, rendered solid black instead of
            # showing the story scene that was on screen already). The
            # sibling KiWi engine's own native disassembly (see reference/
            # codkiwi-main's KIWI_CALL_REFERENCE.txt, "Locations": "GameModel
            # ::setLocationImageID returns without change for negative base")
            # confirms this is a KEEP sentinel for *any* negative base, not
            # just -2 specifically.
            if base >= 0:
                candidate = base + variant if variant in (1, 2) else base
                self.panel.background_id = candidate if not resource_exists or resource_exists(candidate) else base
                # 000a92f4 replaces the node even when its ID is unchanged.
                self.background_pan.center()
            if y == 35:
                self.panel.character_id, self.panel.expression = args[0], max(0, args[3])
                self.panel.presentation_mode, _, _ = self.dialogue_presentation(
                    self.panel.character_id, self.panel.expression)
            self.background_pan.dialogue(self.panel.presentation_mode)
            return complete('set_background', asset_id=self.panel.background_id)
        if y == 97:
            # SHSScript::syscall case 0x61: GameModel::setLocationPan(args[0] != 0, args[1]); Android's
            # 0007b790 (background.BackgroundPan) is the same request. HD's frame pans by location_align
            # (location_pan.py); the 320-unit Android/iPhone frame by background_pan.
            at_least(2)
            self.panel.location_follow, self.panel.location_fixed = args[0] != 0, args[1]
            if args[1] in (1, 2, 3):
                self.panel.location_align = args[1]
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
            self.music_requests += 1
            # SHSSoundManager::stopMusic(short, true) (SHS HD case 0x51 -> 00053424, CoD 1.4.7 00046a10): 0 stops at once,
            # 0xffff means 1000 ms and any other value is the fade in ms (-[SHSSound setFadeTime:] divides it by 1000.0).
            # Other negative shorts would never finish natively; they stop at once here. (Android's stop is unverified.)
            fade = args[0] & 0xffff
            self.music_stop_fade_ms = 1000 if fade == 0xffff else fade if fade < 0x8000 else 0
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
                self.music_requests += 1
                self.audio_stopped = False
            else:
                self.sound_id = args[0]
                self.sound_ids = [args[0]]
                self.sound_serial += 1
            return complete('request_audio', asset_id=args[0])
        if y == 18:  # Explicit default/no-op in this Android dispatcher.
            need(0)
            return complete('native_noop')
        if y in (6, 61):
            # getEntityName(entity) copied into VM memory at args[1]; case 6 (which prints a "not supposed to be
            # using" warning natively) also takes a negative destination as a host-string slot.
            need(2)
            name = self.character_names.get(args[0], '') if 0 <= args[0] < 200 else ''
            if y == 6 and args[1] < 0:
                slot = ~args[1]
                if not 0 <= slot < len(self.dynamic_strings):
                    raise VMError(f'yield 6: invalid string slot selector {args[1]}')
                self.dynamic_strings[slot] = name
                return complete('get_entity_name', 0x7ff5 + slot, entity=args[0])
            self.write_text(vm, args[1], name)
            return complete('get_entity_name', entity=args[0])
        if y == 22:
            # my_sprintf(destination, format, values...): only %s and %d are formats (%s reads a text, %d the
            # signed value); any other `%x` drops the percent sign and keeps x. An empty format writes nothing.
            at_least(2)
            pattern = self.read_text(vm, args[1])
            if pattern:
                out, argument, keep_last, index = '', 2, True, 0
                while index < len(pattern) - 1:
                    char = pattern[index]
                    if char == '%':
                        following = pattern[index + 1]
                        keep_last = index != len(pattern) - 2
                        if following == 's':
                            at_least(argument + 1)
                            out += self.read_text(vm, args[argument])
                            argument += 1
                            index += 1
                        elif following == 'd':
                            at_least(argument + 1)
                            out += str(signed16(args[argument]))
                            argument += 1
                            index += 1
                    else:
                        keep_last = True
                        out += char
                    index += 1
                if keep_last:
                    out += pattern[-1]
                self.write_text(vm, args[0], out)
            return complete('format_into_memory', destination=args[0])
        if y == 26:
            # my_atoi() parses a text but its result is never returned (the dispatcher's result stays the
            # "no result" sentinel), so the call has no effect.
            at_least(1)
            return complete('native_noop')
        if y == 30:
            # SHSEngine::playSound(id): a sound effect, immediately.
            need(1)
            self.sound_id = args[0]
            self.sound_ids = [args[0]]
            self.sound_serial += 1
            return complete('request_audio', asset_id=args[0])
        if y == 32:
            # GameModel::addMaster(id, ...): registers an image master; art is loaded on demand here.
            at_least(1)
            return complete('add_master')
        if y == 36:
            # Title of the top-most dialogue (no name replacement).
            need(1)
            self.panel.speaker = self.read_text(vm, args[0])
            return complete('set_dialogue_title', text=self.panel.speaker)
        if y == 37:
            # Text of the top-most dialogue, animated, and the script waits: the current speaker says it.
            need(1)
            panel = self.panel
            raw_text = self.read_text(vm, args[0])
            if panel.presentation_mode in (1, 2):
                character = panel.character_id
                icons = (self.status_icons if self.status_icons != [-1, -1] else
                         [signed16(self.numbers.get(self.number_key(character, 3000), -1)),
                          self.numbers.get(self.number_key(character, 3001), 1)])
                details = self.present_dialogue(character, panel.expression, raw_text, 0, status_icons=tuple(icons))
                self.status_icons = [-1, -1]
            elif panel.presentation_mode == 4:
                details = self.present_dialogue(self.ui_defaults.get(75, -1), 0, raw_text, 0)
            else:
                details = self.present_dialogue(-1, 0, raw_text, 0, speaker=panel.speaker)
            return EngineAction('dialogue', request, False, details)
        if y == 38:
            # SHSUIDialog::setStatusIcons(icon, count, animated = false, ...): the relationship icons the top
            # dialogue draws; kept as state, the relationship model still derives its own from properties.
            need(2)
            # Stored as (icon asset, icon count); the next service 37 shows them.
            self.status_icons = [signed16(args[0]), args[1]]
            return complete('set_status_icons')
        if y == 43:
            # setNameReplacement("$USR", text).
            need(1)
            self.strings['$USR'] = self.read_text(vm, args[0])
            return complete('set_string', key='$USR', value=self.strings['$USR'])
        if y in (56, 57, 58, 59):
            need({56: 3, 57: 3, 58: 2, 59: 3}[y])
            key = self.number_key(args[0], args[1])
            values = self.int_arrays.get(key)
            if y == 56:
                self.int_arrays.setdefault(key, []).append(signed16(args[2]))
                return complete('append_int_array')
            if y == 58:
                return complete('count_int_array', len(values) if values else 0)
            if not values or not 0 <= args[2] < len(values):
                # Native reads / removes through a null or out-of-range vector element; nothing sane to do.
                return complete('int_array_miss', 0)
            if y == 57:
                return complete('get_int_array', values[args[2]])
            del values[args[2]]
            return complete('remove_int_array')
        if y == 60:
            # getIndexOfRegisteredName: the first of the 200 entity names equal to the text, or -1.
            need(1)
            text = self.read_text(vm, args[0])
            index = next((i for i in range(200) if self.character_names.get(i, '') == text), -1)
            return complete('index_of_name', index)
        if y == 66:
            # Weighted random pick: the index whose cumulative weight first exceeds rand() % total.
            total = sum(signed16(weight) for weight in args)
            if total <= 0:
                return complete('weighted_random', max(0, len(args) - 1))
            roll, running = self.random.below(total), 0
            for index, weight in enumerate(args):
                running += signed16(weight)
                if running > roll:
                    return complete('weighted_random', index)
            return complete('weighted_random', len(args) - 1)
        if y in (83, 84):
            need(0)
            self.music_paused = y == 83
            return complete('pause_music' if y == 83 else 'resume_music')
        if y == 85:
            # GameModel::locationWipe() is an empty function in the HD build.
            return complete('native_noop')
        if y == 87:
            # Reads GameModel+0x260, which nothing but a save load ever writes: 0.
            return complete('native_noop')
        if y == 98:
            # SHSEngine::hideLoadingBar: dismisses a loading screen that is showing without waiting.
            if self.loading is not None and not self.loading.blocking:
                self.loading = None
            return complete('hide_loading_bar')
        if y in (104, 105):
            # Cases 0x68 / 0x69: addNode(type, three labels read without name replacement); exw not passed.
            need(4)
            texts = [self.read_text(vm, ref) for ref in args[1:4]]
            self.dt_add_node(args[0], texts[2], 0, pc=request.pc)
            return complete('dt_add_node')
        if y == 109:
            return complete('dt_update')
        if y == 110:
            return complete('dt_save')
        if y in NATIVE_DEFAULT_YIELDS:
            # These ids have no case in SHSScript::syscall's jump table: the native default returns 0 without
            # side effects, arguments consumed (see legacy/findings.md, "Script services").
            if y == 100 and args:
                # Episodes made for a later app open a link with it (the High School Story ads: the App Store
                # page), then end their script. HD 1.4.38 ignores it; the link is kept for the host to offer.
                try:
                    text = self.read_text(vm, args[0])
                except VMError:
                    text = ''
                if '://' in text:
                    self.store_link = text
            return complete('native_noop')
        if y == 111:
            # Case 0x6f: SHSDTView addBranchNode:condition:innerLabel:upperLabel:lowerLabel:exw: =
            # addNode(...) then the node's branch condition (`+0x1b4`). The three labels are script strings read
            # without name replacement (the model keeps only the lower one; the order of the three is assumed:
            # inner, upper, lower); exw is not passed at this call site (0 assumed).
            need(5)
            for ref in args[2:4]:
                self.read_text(vm, ref)
            node = self.dt_add_node(args[0], self.read_text(vm, args[4]), 0, pc=request.pc)
            node.condition = args[1]
            return complete('dt_add_node')
        if y == 112:
            # Case 0x70: addNode(0x4c8, "", "", "") -- a join node; `DTView.add_node` carries the story on from the
            # node that owns its ids when it repeats them (`find_prototype`), and the panel draws the merge.
            need(0)
            self.dt_add_node(0x4c8, '', 0, pc=request.pc)
            return complete('dt_add_node')
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
            if self.hd_version is not None or GAMES[self.game_key].IOS_ACTION_MENU:
                # The HD build's own pacing (WordGame.hd); its first labels fly on with input open. CoD's iOS
                # SHSUIMenu quiz is the same code (cod/profile.py, IOS_ACTION_MENU).
                game.hd, game.entry_ms = True, 0
            game.deal(self.random48)
            self.word_game = game
            # args[0] is a real category banner ("Snacks!", "Concentrate!", "Bonfire!", ...), confirmed by
            # statically decoding real host_call(71, ...) sites in an imported episode's own compiled bytecode
            # (Football_Star.exp's "Get Snacks" scene: args[0]='Snacks!', args[1]='Pick sweet foods!') -- not a
            # discarded argument, despite an earlier, unverified assumption to that effect. `ChoiceLayout.page()`
            # already lays this out at the portrait-adjacent banner position in the decorative PajamaHip title
            # font for every choice type, title included; a word_game choice just never supplied one before.
            return EngineAction('word_game', request, False, dict(
                title=self.read_text(vm, args[0]), text=self.read_text(vm, args[1]),
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
        if y in (15, 76):
            # SHSScript::syscall cases 0xf and 0x4c are the same code: the top-most dialogue gets speaker type 3,
            # a title and a text (both name-replaced), animates, and the script waits.
            at_least(2)
            # Only the first two arguments are read (title, text); the rest of a 4- or 5-argument call is
            # ignored. A negative pointer other than -1 dereferences unmapped memory natively (an empty
            # string): 20_Party_Fowl passes a `-3` style marker as the title, the way service 13 takes one.
            speaker, text = ('' if ref < 0 else self.read_text(vm, ref) for ref in args[:2])
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
        if y in (101, 114):
            # SHSScript::syscall cases 0x65 and 0x72, from the HD iOS build's
            # own Surviving_HS binary (neither present in the Android 1.0.9
            # reference; this build's syscall range runs 0-0x78, all densely
            # populated via a Thumb-2 TBH jump table). Both decompile to the
            # identical bare objc_msgSend(<view>, @selector(scriptEnable)),
            # differing only in the receiver: g_engineDTView for 101, versus
            # g_engineFSView (Faceplace) for 114. Neither call's return value
            # is consumed by the caller. g_engineFSView's neighboring cases
            # 115-120 message the same object with incomingMessage:from:
            # expression:, incomingContinuationMessageText:/Image:, clearWall,
            # nameChosen: and faceChosen: -- the actual Faceplace wall/
            # notification content and the avatar/name picker -- and remain
            # unimplemented pending their own argument verification.
            need(0)
            (self.dt_view if y == 101 else self.faceplace).enabled = True
            return complete('script_enable', view='dt' if y == 101 else 'faceplace')
        if y == 103:
            # SHSScript::syscall case 0x67, g_engineDTView (see 101/114 above).
            # Ghidra's decompile of this function is not trustworthy at the
            # argument level here (it shows real VM-stack strings fetched via
            # getStringFromStackNoTranslation and then discarded, which cannot
            # be real behavior; the function also triggers 300+ "unreachable
            # block" warnings during decompilation). Content fidelity resolved
            # by hand-disassembling the raw Thumb-2 call site instead of
            # trusting the decompile (see docs/ENGINE_ABI.md section 6.2):
            # addNode:innerLabel:upperLabel:lowerLabel:exw:(nodeType=args[0],
            # innerLabel="", upperLabel="", lowerLabel=read_text(args[1]),
            # exw=args[2]) -- innerLabel/upperLabel are hardcoded empty
            # CSString literals at this call site, confirmed in the raw
            # instructions, not omitted. Return value still never captured by
            # the caller, same safe "fire and forget" shape as 101/114. The
            # one real instance seen (Football Star scene 25008) pushed
            # exactly 3 words, matching this argument count exactly.
            need(3)
            self.dt_add_node(args[0], self.read_text(vm, args[1]), args[2], pc=request.pc)
            return complete('dt_add_node')
        if y == 113:
            # SHSScript::syscall case 0x71 (HD 0004069a..): reads two strings (key first, then value, as service 46) and,
            # only while SHSEntityTable::getNameReplacement("$USR") is empty, stores key = value; then redraws Faceplace
            # (g_engineFSView setNeedsDisplay). Football Star 25008 uses it once, ("$USR", "John"): the player's name
            # before any was typed -- the "John" a fresh install's shs_options.sav holds. The table is the library's
            # shared one (Session.share_names).
            need(2)
            key, value = (self.read_text(vm, ref) for ref in args)
            if not self.strings.get('$USR', ''):
                self.strings[key] = value
            return complete('faceplace_needs_display', key=key, value=value)
        if y == 108:
            # SHSScript::syscall case 0x6c: `SHSDTView clearGlobalAccumulator:(id)`. The id joins `DTNode::accumulators_set` (its
            # changes are kept by the next scene as absolute values, `dt_state.compute_deltas`) and the counter is emptied:
            # `setIntProperty(entity id, 0x197, 0)` for an id below 600 (a character's relationship value), else
            # `setIntProperty(0, id, 0)`. Football Star clears the relationship values and the 3038 / 3100 / 3105 counters this
            # way; the game reads them again afterwards.
            need(1)
            identifier = signed16(args[0])
            self.dt_view.accumulators.append(identifier)
            owner, key = (identifier, 0x197) if identifier < CLEARED_WITH_CHARACTER else (0, identifier)
            self.numbers[self.number_key(owner, key)] = 0
            return complete('dt_clear_global_accumulator')
        if y in (119, 120):
            # SHSScript::syscall cases 0x77/0x78, g_engineFSView (Faceplace):
            # objc_msgSend(g_engineFSView, @selector(nameChosen:) or
            # @selector(faceChosen:)). Despite the colon, the real call site
            # passes no visible second argument, and the VM confirms this
            # empirically -- both are observed with zero pushed arguments.
            # Confirmed live: this is exactly the old avatar-picker gap from
            # the original bytecode-only research (a `derefPointer`-fed
            # portrait picker whose 5 real ids were never recovered there) --
            # running HD's own Football Star through this engine reached the
            # real character_picker with characters=[88, 89, 90, 91, 92],
            # confirmed the picker's completion (already correctly modeled,
            # not from this session's work) resumes straight into yield 120.
            # Return value not captured by the caller, same confirmed-safe
            # shape as 101/103/108/114 above; the actual selection is already
            # applied through the existing character_picker completion path
            # (_complete_choice), so this is just a native redraw/notify hook.
            need(0)
            return complete('faceplace_name_chosen' if y == 119 else 'faceplace_face_chosen')
        if y == 115:
            # SHSScript::syscall case 0x73, g_engineFSView (Faceplace):
            # objc_msgSend(g_engineFSView, @selector(incomingMessage:from:
            # expression:), message, from, expression). from=args[1] and
            # expression=args[2] (both raw shorts read directly off the
            # script's own argument buffer via the same `local_7c0`-style
            # addressing every other handler in this engine already uses
            # for its own args list). Return value still confirmed
            # discarded by the caller.
            #
            # Real device correction: an earlier pass read message text with
            # read_text (no substitution) based on this call site using the
            # native getStringFromStackNoTranslation helper, distinct from
            # getStringFromStack (confirmed WITH substitution, see yield 113
            # above) -- but real gameplay clearly substitutes $USR in
            # Faceplace wall posts ("Say what you will about $USR..." showed
            # up literally, unsubstituted, in this engine; real HD shows the
            # player's chosen name there). "NoTranslation" more plausibly
            # means "skip locale/language selection" (the string is already
            # one fixed literal, not a localized string-table reference),
            # not "skip token substitution" -- resolve_text matches
            # present_dialogue's own established pattern (substitute once at
            # creation, matching real dialogue's raw_text/text split).
            need(3)
            self.faceplace.incoming_message(self.resolve_text(vm, args[0]), args[1], args[2])
            self.faceplace_toast = FaceplaceToast(self.faceplace.messages[-1])
            return complete('faceplace_incoming_message')
        if y == 102:
            # SHSScript::syscall case 0x66, g_engineDTView: another
            # @selector(addNode:innerLabel:upperLabel:lowerLabel:exw:)
            # invocation (same selector as yield 103/case 0x67 above).
            # Raw disassembly: nodeType=args[0], innerLabel=upperLabel=""
            # (hardcoded empty CSString literals, same as case 0x67),
            # lowerLabel=read_text(args[1]), exw=0 (hardcoded, not read from
            # the script at all at this call site). Same confirmed-safe
            # discarded-return shape as every other case in this cluster.
            need(2)
            self.dt_add_node(args[0], self.read_text(vm, args[1]), 0, pc=request.pc)
            return complete('dt_add_node')
        if y == 106:
            # SHSScript::syscall case 0x6a, g_engineDTView:
            # objc_msgSend(g_engineDTView, @selector(addResult:exitLabel:),
            # args[0], read_text(args[1])) -- verified from raw Thumb
            # disassembly (docs/ENGINE_ABI.md section 6.2). Return value not
            # captured (falls straight to buffer cleanup and break), same
            # confirmed-safe shape as the rest of this cluster.
            need(2)
            self.dt_view.add_result(args[0], self.read_text(vm, args[1]))
            return complete('dt_add_result')
        if y == 116:
            # SHSScript::syscall case 0x74, g_engineFSView (Faceplace):
            # objc_msgSend(g_engineFSView, @selector(
            # incomingContinuationMessageText:url:), text(args[0]),
            # url(args[1])), verified from raw Thumb disassembly. Return
            # value confirmed discarded. args[0] is caption text --
            # resolve_text, matching yield 115's real-device correction
            # above (substitution applies to displayed text, not the URL).
            need(2)
            post = self.faceplace.incoming_continuation_text(self.resolve_text(vm, args[0]), self.read_text(vm, args[1]))
            self._alert_for(post)
            return complete('faceplace_continuation_text')
        if y == 117:
            # SHSScript::syscall case 0x75, g_engineFSView (Faceplace).
            # Raw disassembly (docs/ENGINE_ABI.md section 6.2) shows this
            # case is NOT the same shape as 116 despite the similar selector
            # name -- it reads 3 words, not 2 (need(2) here was an
            # unverified guess before this session; 117 was never reached
            # live until now), and fires two objc_msgSend calls back to
            # back: @selector(incomingContinuationMessageImage:url:) with
            # (args[0] raw int, url(args[2])), immediately followed by
            # @selector(incomingContinuationMessageText:url:) with
            # (text(args[1]), url(args[2])) -- the same url both times. Both
            # return values confirmed discarded. args[1] is caption text --
            # resolve_text, matching yield 115's real-device correction.
            need(3)
            post = self.faceplace.incoming_continuation_image(
                args[0], self.resolve_text(vm, args[1]), self.read_text(vm, args[2]))
            self._alert_for(post)
            return complete('faceplace_continuation_image')
        if y == 118:
            # SHSScript::syscall case 0x76, g_engineFSView:
            # objc_msgSend(g_engineFSView, @selector(clearWall)). Bare,
            # argument-less (no colon in the selector), same confirmed-safe
            # shape as scriptEnable/nameChosen/faceChosen above.
            need(0)
            self.faceplace.clear()
            return complete('faceplace_clear_wall')
        if y == 107:
            # SHSScript::syscall case 0x6b, g_engineDTView: another
            # @selector(addResult:exitLabel:) invocation (same selector as
            # yield 106/case 0x6a above). Raw disassembly: exitLabel is built
            # by sprintf-formatting args[0] itself as a decimal string (not a
            # separate script argument) -- resultIndex=exitLabel=str(args[0])
            # exactly. Return value not captured, same confirmed-safe shape
            # as the rest of this cluster.
            need(1)
            self.dt_view.add_result(args[0], str(args[0]))
            return complete('dt_add_result')
        return EngineAction('unhandled_yield', request, False)
