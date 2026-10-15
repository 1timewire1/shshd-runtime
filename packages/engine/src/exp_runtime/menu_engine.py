"""The HD app's menu engine data (`CSMenuEngine`, resource 17) and its stack.

Every window of the iOS HD menus ("Play with sound?", "Help & About", "Options", "Want More Content?", the info pages
and confirmations) is defined in one 2484-byte resource, read by `CSMenuEngine::loadMenuEngine`:

    u8 menu count, u8 (twice the count), u16 action-table offset, u16 length, then `length` bytes of data.

The data starts with a u16 offset per menu. A menu record is 16 header bytes then one u16 action id per item:
title string id, message string id (or 0xffff), ... , u8 style at +12, the two window layout ids at +13/+14 and the item
count at +15 (`getActionID`, `checkItemConditions`). Action `n` is at `data[table + 2 n]` (an offset): u16 label string id,
two flag bytes and a step count, then 3-byte steps (`CSMenuEngine::menuAction`): a step type and a u16 argument.

Step types the shipped data uses: 1 go back, 2 go back to a menu, 3 queue a menu, 8 show a menu as an info page (a
"form"), 9 clear the stack, 15 run an engine action (`SHSEngine::doMenuEngineAction`). The other types the native switch
knows never appear in this resource. Option rows (Vibration, Game Music, Music Volume, Sound FX, Sound FX Volume) have no
steps: their second flag byte names the state they show (10 vibration switch, 11 sound switch, 12 music switch,
13 sound volume slider, 14 music volume slider; `SHSWidgetMenu::getStateValueForIndex`). An item whose first flag byte is 1
is the window's footer button (a blue arrow when its label is empty).
"""
from dataclasses import dataclass
import struct

BACK, BACK_TO, QUEUE, FORM, CLEAR, ENGINE = 1, 2, 3, 8, 9, 15
STYLE_ALERT = 2                          # a title and a row of buttons (No / Yes)
STATE_VIBRATION, STATE_SOUND, STATE_MUSIC, STATE_SOUND_VOLUME, STATE_MUSIC_VOLUME = 10, 11, 12, 13, 14
NO_STRING = 0xffff


class MenuEngineError(ValueError):
    pass


@dataclass(frozen=True)
class Action:
    id: int
    label: int
    flags: tuple
    steps: tuple                 # ((type, argument), ...)

    @property
    def is_footer_button(self):
        """The window's Back-style button (blue, in the footer): an arrow when its label is empty."""
        return self.flags[0] == 1

    @property
    def state(self):
        """The option state a switch / slider row shows, or None."""
        return self.flags[1] if not self.steps and self.flags[1] in range(STATE_VIBRATION, STATE_MUSIC_VOLUME + 1) else None


@dataclass(frozen=True)
class Menu:
    id: int
    title: int
    message: int
    style: int
    layouts: tuple
    header: bytes
    items: tuple                 # Action ids

    @property
    def is_form(self):
        """Menus 0-6 are the info pages: text under a title with only a Back item."""
        return self.message != NO_STRING and len(self.items) == 1


class MenuEngineData:
    def __init__(self, raw):
        if len(raw) < 6:
            raise MenuEngineError('Truncated menu engine resource')
        self.count, _, self.table, length = raw[0], raw[1], *struct.unpack('>HH', raw[2:6])
        self.data = raw[6:6 + length]
        if len(self.data) != length or self.count * 2 > length:
            raise MenuEngineError('Truncated menu engine data')
        self.menus = tuple(self._menu(index) for index in range(self.count))
        self._actions = {}

    def _u16(self, offset):
        try:
            return struct.unpack_from('>H', self.data, offset)[0]
        except struct.error:
            raise MenuEngineError('Menu engine offset out of range') from None

    def _menu(self, index):
        offset = self._u16(index * 2)
        header = self.data[offset:offset + 16]
        if len(header) != 16:
            raise MenuEngineError('Truncated menu record')
        count = header[15]
        items = tuple(self._u16(offset + 16 + 2 * i) for i in range(count))
        return Menu(index, self._u16(offset), self._u16(offset + 2), header[12], (header[13], header[14]), header, items)

    def action(self, action_id):
        if action_id not in self._actions:
            offset = self._u16(self.table + 2 * action_id)
            head = self.data[offset:offset + 5]
            if len(head) != 5:
                raise MenuEngineError('Truncated menu action')
            steps = tuple((self.data[offset + 5 + 3 * i], self._u16(offset + 6 + 3 * i)) for i in range(head[4]))
            self._actions[action_id] = Action(action_id, struct.unpack('>H', head[0:2])[0], (head[2], head[3]), steps)
        return self._actions[action_id]

    def menu(self, menu_id):
        try:
            return self.menus[menu_id]
        except IndexError:
            raise MenuEngineError(f'Unknown menu {menu_id}') from None

    def items(self, menu_id):
        return [self.action(a) for a in self.menu(menu_id).items]


class MenuStack:
    """`CSMenuEngine`'s stack of open menus. `press` performs an item's steps; engine actions go to `perform`."""

    def __init__(self, data, perform):
        self.data, self.perform = data, perform
        self.stack = []

    @property
    def current(self):
        return self.stack[-1] if self.stack else None

    def queue(self, menu_id):
        self.data.menu(menu_id)
        self.stack.append(menu_id)

    def pop(self):
        if self.stack:
            self.stack.pop()

    def clear(self):
        self.stack.clear()

    def back_to(self, menu_id):
        while self.stack and self.stack[-1] != menu_id:
            self.stack.pop()

    def press(self, action):
        """Run an item's steps in order (`CSMenuEngine::menuAction`); an engine action may itself change the stack."""
        for kind, argument in action.steps:
            if kind == BACK:
                self.pop()
            elif kind == BACK_TO:
                self.back_to(argument)
            elif kind == QUEUE:
                self.queue(argument)
            elif kind == FORM:
                self.queue(argument)
            elif kind == CLEAR:
                self.clear()
            elif kind == ENGINE:
                self.perform(argument)
