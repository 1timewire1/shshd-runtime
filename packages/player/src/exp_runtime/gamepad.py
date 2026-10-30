"""Game controllers on the desktop (this player's addition: the originals were touch-only).

SDL's game-controller layer reads XInput, DirectInput, PlayStation, Switch Pro and Stadia pads alike. Its buttons are
taken by position (SDL_GAMECONTROLLER_USE_BUTTON_LABELS off): `south` is the bottom face button on every pad, an
Xbox pad's A and a Switch Pro's B alike. Each press arrives as a KEYDOWN whose `controller` names the button
(BUTTONS) and whose `key` is what it does in the menus and the story (`menu_key`: the keys the player already
answers, docs/RUNTIME.md "Controls"), so most screens need no controller code, and the screens that place buttons by
position read `controller` (Football's nine plays, desktop.FOOTBALL_BUTTONS). The confirm button is the bottom one or,
for a Nintendo layout, the right one (Options' Controller page, `Gamepads.confirm`). The left stick moves like the
D-pad, and a held direction repeats like a held key.

A connected controller is also the desktop's vibrator: `graphics.supports_vibration` reports it, so General's
Vibration switch is offered and service 82 rumbles it, as on a phone; Sound's Simulated Vibration Sound stays a
separate switch.
"""
import logging
import math
import os

import pygame

from . import graphics

# SDL button -> its position (the face buttons by compass point, then the rest by name).
BUTTONS = {
    pygame.CONTROLLER_BUTTON_A: 'south', pygame.CONTROLLER_BUTTON_B: 'east',
    pygame.CONTROLLER_BUTTON_X: 'west', pygame.CONTROLLER_BUTTON_Y: 'north',
    pygame.CONTROLLER_BUTTON_BACK: 'back', pygame.CONTROLLER_BUTTON_START: 'start',
    pygame.CONTROLLER_BUTTON_LEFTSTICK: 'l3', pygame.CONTROLLER_BUTTON_RIGHTSTICK: 'r3',
    pygame.CONTROLLER_BUTTON_LEFTSHOULDER: 'lb', pygame.CONTROLLER_BUTTON_RIGHTSHOULDER: 'rb',
    pygame.CONTROLLER_BUTTON_DPAD_UP: 'up', pygame.CONTROLLER_BUTTON_DPAD_DOWN: 'down',
    pygame.CONTROLLER_BUTTON_DPAD_LEFT: 'left', pygame.CONTROLLER_BUTTON_DPAD_RIGHT: 'right',
}
TRIGGERS = {pygame.CONTROLLER_AXIS_TRIGGERLEFT: 'lt', pygame.CONTROLLER_AXIS_TRIGGERRIGHT: 'rt'}
DIRECTIONS = ('up', 'down', 'left', 'right')

# What a button does in the menus and the story, as the key it stands for. The face buttons follow the confirm
# button (CONFIRM): confirm is Enter, back is Escape, the one left of confirm erases a typed name's last letter
# (Backspace), the one above it opens an episode's info card (I); a Nintendo layout swaps the pairs, as its labels
# are. Start pauses (Escape), Back / View / Share opens the side panels (Tab), the shoulders page long lists, the
# triggers and stick clicks are no key (Football reads them by position).
FACE_KEYS = {'south': {'south': pygame.K_RETURN, 'east': pygame.K_ESCAPE, 'west': pygame.K_BACKSPACE,
                       'north': pygame.K_i},
             'east': {'east': pygame.K_RETURN, 'south': pygame.K_ESCAPE, 'north': pygame.K_BACKSPACE,
                      'west': pygame.K_i}}
CONFIRM = tuple(FACE_KEYS)
OTHER_KEYS = {'start': pygame.K_ESCAPE, 'back': pygame.K_TAB, 'lb': pygame.K_PAGEUP, 'rb': pygame.K_PAGEDOWN,
              'up': pygame.K_UP, 'down': pygame.K_DOWN, 'left': pygame.K_LEFT, 'right': pygame.K_RIGHT}

# The left stick and the triggers: pressed past PRESS of full travel and released inside RELEASE, so one resting near
# the edge of its dead zone does not chatter.
STICK_PRESS, STICK_RELEASE = .5, .3
AXIS_RANGE = 32768

# A held direction repeats after REPEAT_DELAY_MS, then every REPEAT_MS.
REPEAT_DELAY_MS, REPEAT_MS = 400, 90

# Service 82: `FUN_000a3040` asks Android's vibrator for 1000 ms. Both motors at RUMBLE_STRENGTH stand in for a
# phone's single motor (the strength is this player's choice).
RUMBLE_MS = 1000
RUMBLE_STRENGTH = .7


def menu_key(button, confirm='south'):
    """The key `button` stands for in the menus and the story, with the confirm button `confirm`; K_UNKNOWN for one
    that is none (a trigger, a stick click)."""
    return FACE_KEYS.get(confirm, FACE_KEYS['south']).get(button, OTHER_KEYS.get(button, pygame.K_UNKNOWN))


def key_event(key, button=None):
    """A KEYDOWN as the keyboard's, with the controller `button` that made it (None for the keyboard's own)."""
    return pygame.event.Event(pygame.KEYDOWN, key=key, mod=pygame.KMOD_NONE, scancode=0, unicode='', window=None,
                              controller=button)


def stick_direction(x, y, held):
    """The direction the left stick at (x, y) (each -1..1) holds, given the one it `held` before, or None. A held
    direction lasts until the stick falls inside STICK_RELEASE or swings further toward another direction."""
    if held is not None:
        value = {'left': -x, 'right': x, 'up': -y, 'down': y}[held]
        other = abs(y) if held in ('left', 'right') else abs(x)
        if value > STICK_RELEASE and not (other >= STICK_PRESS and other > value):
            return held
    if max(abs(x), abs(y)) < STICK_PRESS:
        return None
    if abs(x) > abs(y):
        return 'right' if x > 0 else 'left'
    return 'down' if y > 0 else 'up'


class Gamepads:
    """The connected controllers. `events` replaces `pygame.event.get()` in a desktop run loop."""

    def __init__(self, controller_module=None):
        self.controller = controller_module
        self.confirm = 'south'          # the confirm button: 'south', or 'east' for a Nintendo layout (CONFIRM)
        self.pads = {}                  # SDL instance id -> Controller
        self.sticks = {}                # SDL instance id -> [x, y], each -1..1
        self.stick_held = {}            # SDL instance id -> the direction its stick holds
        self.triggers = set()           # (SDL instance id, 'lt' / 'rt') held past STICK_PRESS
        self.down = set()               # (SDL instance id, button) of the buttons held now (pressed, not yet let go)
        self.held = None                # (direction, next repeat in ms) of the direction last pressed and still held

    @classmethod
    def start(cls):
        """Open SDL's controller subsystem and become graphics' vibrator; None where SDL has no controller support."""
        # Buttons by position, not by the labels printed on them (a Switch Pro's A is its right button).
        os.environ.setdefault('SDL_GAMECONTROLLER_USE_BUTTON_LABELS', '0')
        try:
            from pygame._sdl2 import controller
            controller.init()
        except (ImportError, pygame.error) as error:
            logging.info('Game controllers are unavailable: %s', error)
            return None
        gamepads = cls(controller)
        graphics.install_gamepads(gamepads)
        return gamepads           # (SDL reports controllers already connected as CONTROLLERDEVICEADDED events)

    def stop(self):
        previous = graphics.install_gamepads(None)
        if previous is not self:
            graphics.install_gamepads(previous)
        for pad in self.pads.values():
            pad.quit()
        self.pads.clear()

    @property
    def connected(self):
        return bool(self.pads)

    vibration_available = connected

    def holding(self, button):
        """Whether `button` is held on any controller ('confirm' for the confirm button, as Gamepads.confirm has it)."""
        button = self.confirm if button == 'confirm' else button
        return any(held == button for _, held in self.down)

    def steering(self):
        """Where the D-pad or the left stick points, eight ways: (dx, dy), each -1, 0 or 1. Two D-pad directions held
        together are a diagonal; the stick past STICK_PRESS points to the nearest of its eight 45-degree sectors (a
        word grid's drag goes diagonally as often as straight)."""
        held = {button for _, button in self.down}
        dx = ('right' in held) - ('left' in held)
        dy = ('down' in held) - ('up' in held)
        if dx or dy:
            return dx, dy
        for x, y in self.sticks.values():
            if max(abs(x), abs(y)) >= STICK_PRESS:
                sector = round(math.atan2(y, x) / (math.pi / 4)) % 8
                return ((1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1))[sector]
        return 0, 0

    def vibrate(self):
        for pad in self.pads.values():
            try:
                pad.rumble(RUMBLE_STRENGTH, RUMBLE_STRENGTH, RUMBLE_MS)
            except pygame.error as error:
                logging.debug('Rumble failed on %s: %s', pad.name, error)

    def events(self, now=None):
        """This frame's events with controller input read as key presses, and a held direction's repeats."""
        now = pygame.time.get_ticks() if now is None else now
        result = []
        for event in pygame.event.get():
            if event.type in (pygame.CONTROLLERDEVICEADDED, pygame.CONTROLLERDEVICEREMOVED):
                self._device(event)
            elif event.type == pygame.CONTROLLERBUTTONDOWN:
                button = BUTTONS.get(event.button)
                if button is not None:
                    self.down.add((event.instance_id, button))
                    result.append(self._press(button, now))
            elif event.type == pygame.CONTROLLERBUTTONUP:
                self.down.discard((event.instance_id, BUTTONS.get(event.button)))
                if self.held is not None and BUTTONS.get(event.button) == self.held[0]:
                    self.held = None
            elif event.type == pygame.CONTROLLERAXISMOTION:
                result.extend(self._axis(event, now))
            else:
                result.append(event)
        if self.held is not None and now >= self.held[1]:
            self.held = self.held[0], now + REPEAT_MS
            result.append(key_event(menu_key(self.held[0], self.confirm), self.held[0]))
        return result

    def _press(self, button, now):
        self.held = (button, now + REPEAT_DELAY_MS) if button in DIRECTIONS else None
        return key_event(menu_key(button, self.confirm), button)

    def _device(self, event):
        if event.type == pygame.CONTROLLERDEVICEADDED:
            try:
                pad = self.controller.Controller(event.device_index)
            except pygame.error as error:
                logging.warning('Game controller %s cannot be opened: %s', event.device_index, error)
                return
            self.pads[pad.as_joystick().get_instance_id()] = pad
            logging.info('Game controller connected: %s', pad.name)
        else:
            pad = self.pads.pop(event.instance_id, None)
            self.sticks.pop(event.instance_id, None)
            self.triggers = {held for held in self.triggers if held[0] != event.instance_id}
            self.down = {held for held in self.down if held[0] != event.instance_id}
            if self.stick_held.pop(event.instance_id, None) is not None:
                self.held = None
            if pad is not None:
                logging.info('Game controller disconnected: %s', pad.name)
                pad.quit()

    def _axis(self, event, now):
        trigger = TRIGGERS.get(event.axis)
        if trigger is not None:
            # A trigger is a button pressed past STICK_PRESS of its travel, let go inside STICK_RELEASE.
            value, held = event.value / AXIS_RANGE, (event.instance_id, trigger)
            if held not in self.triggers and value >= STICK_PRESS:
                self.triggers.add(held)
                return [self._press(trigger, now)]
            if held in self.triggers and value <= STICK_RELEASE:
                self.triggers.discard(held)
            return []
        if event.axis not in (pygame.CONTROLLER_AXIS_LEFTX, pygame.CONTROLLER_AXIS_LEFTY):
            return []
        stick = self.sticks.setdefault(event.instance_id, [0., 0.])
        stick[event.axis == pygame.CONTROLLER_AXIS_LEFTY] = max(-1., event.value / AXIS_RANGE)
        before = self.stick_held.get(event.instance_id)
        after = stick_direction(*stick, before)
        if after == before:
            return []
        self.stick_held[event.instance_id] = after
        if after is None:
            if self.held is not None and self.held[0] == before:
                self.held = None
            return []
        return [self._press(after, now)]
