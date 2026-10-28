"""Xbox / PlayStation-style controllers on the desktop (this player's addition: the originals were touch-only).

SDL's game-controller layer gives every supported pad the same Xbox-style button names, so DualShock, DualSense,
Switch Pro and Xbox pads share one mapping. Buttons are read as the keys the player already answers (docs/RUNTIME.md,
"Controls"): no screen needs its own controller code, and whatever a key does there the button does too. The left
stick moves like the D-pad, and a held direction repeats like a held key.

A connected controller is also the desktop's vibrator: `graphics.supports_vibration` reports it, so General's
Vibration switch is offered and service 82 rumbles it, as on a phone; Sound's Simulated Vibration Sound stays a
separate switch.
"""
import logging

import pygame

from . import graphics

# Button -> key. A confirms, B and Start go back / pause (Escape), X erases a typed name's last letter, Y opens an
# episode's info card, Back / View / Share opens the side panels (Tab), the shoulders page long lists.
BUTTON_KEYS = {
    pygame.CONTROLLER_BUTTON_A: pygame.K_RETURN,
    pygame.CONTROLLER_BUTTON_B: pygame.K_ESCAPE,
    pygame.CONTROLLER_BUTTON_START: pygame.K_ESCAPE,
    pygame.CONTROLLER_BUTTON_X: pygame.K_BACKSPACE,
    pygame.CONTROLLER_BUTTON_Y: pygame.K_i,
    pygame.CONTROLLER_BUTTON_BACK: pygame.K_TAB,
    pygame.CONTROLLER_BUTTON_LEFTSHOULDER: pygame.K_PAGEUP,
    pygame.CONTROLLER_BUTTON_RIGHTSHOULDER: pygame.K_PAGEDOWN,
    pygame.CONTROLLER_BUTTON_DPAD_UP: pygame.K_UP,
    pygame.CONTROLLER_BUTTON_DPAD_DOWN: pygame.K_DOWN,
    pygame.CONTROLLER_BUTTON_DPAD_LEFT: pygame.K_LEFT,
    pygame.CONTROLLER_BUTTON_DPAD_RIGHT: pygame.K_RIGHT,
}
DIRECTIONS = (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT)

# The left stick: a direction is pressed past STICK_PRESS of full travel and released inside STICK_RELEASE, so a stick
# resting near the edge of its dead zone does not chatter.
STICK_PRESS, STICK_RELEASE = .5, .3
AXIS_RANGE = 32768

# A held direction repeats after REPEAT_DELAY_MS, then every REPEAT_MS.
REPEAT_DELAY_MS, REPEAT_MS = 400, 90

# Service 82: `FUN_000a3040` asks Android's vibrator for 1000 ms. Both motors at RUMBLE_STRENGTH stand in for a
# phone's single motor (the strength is this player's choice).
RUMBLE_MS = 1000
RUMBLE_STRENGTH = .7


def key_event(key):
    return pygame.event.Event(pygame.KEYDOWN, key=key, mod=pygame.KMOD_NONE, scancode=0, unicode='', window=None)


def stick_direction(x, y, held):
    """The arrow key the left stick at (x, y) (each -1..1) holds, given the one it `held` before, or None. A held
    direction lasts until the stick falls inside STICK_RELEASE or swings further toward another direction."""
    if held is not None:
        value = {pygame.K_LEFT: -x, pygame.K_RIGHT: x, pygame.K_UP: -y, pygame.K_DOWN: y}[held]
        other = abs(y) if held in (pygame.K_LEFT, pygame.K_RIGHT) else abs(x)
        if value > STICK_RELEASE and not (other >= STICK_PRESS and other > value):
            return held
    if max(abs(x), abs(y)) < STICK_PRESS:
        return None
    if abs(x) > abs(y):
        return pygame.K_RIGHT if x > 0 else pygame.K_LEFT
    return pygame.K_DOWN if y > 0 else pygame.K_UP


class Gamepads:
    """The connected controllers. `events` replaces `pygame.event.get()` in a desktop run loop."""

    def __init__(self, controller_module=None):
        self.controller = controller_module
        self.pads = {}                  # SDL instance id -> Controller
        self.sticks = {}                # SDL instance id -> [x, y], each -1..1
        self.stick_held = {}            # SDL instance id -> the arrow key its stick holds
        self.held = None                # (key, next repeat in ms) of the direction last pressed and still held

    @classmethod
    def start(cls):
        """Open SDL's controller subsystem and become graphics' vibrator; None where SDL has no controller support."""
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
    def vibration_available(self):
        return bool(self.pads)

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
                key = BUTTON_KEYS.get(event.button)
                if key is not None:
                    result.append(self._press(key, now))
            elif event.type == pygame.CONTROLLERBUTTONUP:
                if self.held is not None and BUTTON_KEYS.get(event.button) == self.held[0]:
                    self.held = None
            elif event.type == pygame.CONTROLLERAXISMOTION:
                result.extend(self._axis(event, now))
            else:
                result.append(event)
        if self.held is not None and now >= self.held[1]:
            self.held = self.held[0], now + REPEAT_MS
            result.append(key_event(self.held[0]))
        return result

    def _press(self, key, now):
        self.held = (key, now + REPEAT_DELAY_MS) if key in DIRECTIONS else None
        return key_event(key)

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
            if self.stick_held.pop(event.instance_id, None) is not None:
                self.held = None
            if pad is not None:
                logging.info('Game controller disconnected: %s', pad.name)
                pad.quit()

    def _axis(self, event, now):
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
