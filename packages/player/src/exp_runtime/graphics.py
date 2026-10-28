"""Drawing/platform primitives for the shared presentation code.

Desktop uses pygame directly. A mobile host installs its backend before it
imports the application; menus, panel geometry and event handling stay shared.
"""
_backend = None
_gamepads = None        # the desktop's connected controllers (gamepad.py), which rumble for a device's vibrator


def supports_vibration():
    return bool(getattr(_backend, 'vibration_available', False)) or bool(_gamepads and _gamepads.vibration_available)


def vibrate():
    if getattr(_backend, 'vibration_available', False):
        _backend.vibrate()
    elif _gamepads and _gamepads.vibration_available:
        _gamepads.vibrate()


def install_gamepads(gamepads):
    global _gamepads
    previous, _gamepads = _gamepads, gamepads
    return previous


class _MenuMusic:
    """An SDL channel independent of the paused story's streaming music."""
    def __init__(self, mixer):
        self.mixer = mixer
        self.sound = self.channel = None

    def load(self, stream):
        self.sound = self.mixer.Sound(file=stream)

    def play(self):
        self.channel = self.sound.play()
        if self.channel is None:
            raise ValueError('No audio channel is available for menu music')
        self.channel.set_volume(1)

    def stop(self):
        if self.channel is not None:
            self.channel.stop()
        self.sound = self.channel = None

    def pause(self):
        if self.channel is not None:
            self.channel.pause()

    def unpause(self):
        if self.channel is not None:
            self.channel.unpause()

    def get_busy(self):
        return bool(self.channel is not None and self.channel.get_sound() is self.sound and self.channel.get_busy())

    def set_volume(self, volume):
        if self.get_busy():
            self.channel.set_volume(volume)


def create_menu_music():
    mixer = __getattr__('mixer')
    return mixer.menu_music if hasattr(mixer, 'menu_music') else _MenuMusic(mixer)


def play_sound(stream, start_ms=0):
    mixer = __getattr__('mixer')
    if hasattr(mixer, 'play_sound'):
        return mixer.play_sound(stream, start_ms)
    from .platforms.sdl_audio import Sound
    return Sound(stream, start_ms)


def music_position(start_ms=0):
    music = __getattr__('mixer').music
    if hasattr(music, 'position_ms'):
        return music.position_ms()
    from .platforms.sdl_audio import position_ms
    position = position_ms()
    return position if position is not None else start_ms + max(0, music.get_pos())


def set_music_repeat(repeat, *, start_ms=0, paused=False):
    music = __getattr__('mixer').music
    loops = -1 if repeat else 0
    if hasattr(music, 'set_loops'):
        music.set_loops(loops)
    else:
        # SDL2_mixer cannot alter loop count on an active stream. Reuse its
        # decoder at the actual current position; do not reload or rewind.
        position = music_position(start_ms)
        music.play(loops=loops, start=position / 1000)
        if paused:
            music.pause()


def faded(surface, alpha):
    """The surface to draw for `surface` at opacity `alpha` (0-255; None or 255: opaque). A pygame surface with its
    own per-pixel alpha gets a copy with that channel multiplied: SDL's whole-surface alpha over per-pixel alpha
    drew wrongly on macOS (the image's own transparency was lost while fading: the main menu title's white box and
    the info button's dark square, owner's report, 2026-10-21), and a multiply draws the same everywhere. Other
    surfaces take the whole-surface alpha as before (set in place, as `set_alpha` did). `surface`'s pixels are never
    changed, so a cached surface stays as it was."""
    if alpha is not None and alpha >= 255:
        alpha = None
    # Per-pixel alpha is the pixel format's own alpha channel (pygame-ce also reports SRCALPHA in get_flags once a
    # plain surface has had a whole-surface alpha, so that flag cannot tell them apart).
    get_masks = getattr(surface, 'get_masks', None)
    per_pixel = get_masks is not None and bool(get_masks()[3])
    if alpha is None and per_pixel:
        return surface              # (set_alpha(None) would also switch off its per-pixel blending)
    if alpha is None or not per_pixel:
        # 255 rather than None: pygame-ce's set_alpha(None) keeps the last alpha of a surface faded before.
        surface.set_alpha(255 if alpha is None else max(0, round(alpha)))
        return surface
    result = surface.copy()
    result.fill((255, 255, 255, max(0, round(alpha))), special_flags=__getattr__('BLEND_RGBA_MULT'))
    return result


def opaque(surface):
    """`surface` with every pixel's alpha at 255, in place, when its pixel format has an alpha channel. A display that
    has one (macOS) gives `convert()`ed canvases one, and a canvas built there can carry alpha 0 where its colour is
    right; anything later composed on it shows that alpha. Surfaces without per-pixel alpha (and the native
    backend's) are left as they are."""
    get_masks = getattr(surface, 'get_masks', None)
    if get_masks is not None and get_masks()[3]:
        surface.fill((0, 0, 0, 255), special_flags=__getattr__('BLEND_RGBA_MAX'))
    return surface


def color_matrix(surface, matrix):
    native = getattr(__getattr__('transform'), 'color_matrix', None)
    if native is not None:
        return native(surface, matrix)
    from .color_transform import transform_rgb
    image = __getattr__('image')
    pixels = transform_rgb(image.tobytes(surface, 'RGB'), matrix)
    return image.frombytes(pixels, surface.get_size(), 'RGB')


def project_quad(target, image, points):
    """Project a sprite with the shared scanline rule, batching on native hosts.

    Board-plane quads have horizontal top/bottom edges. Geometry and rounding
    stay here; the platform only draws the resulting textured rows.
    """
    tl, tr, br, bl = points
    top, bottom = round(tl[1]), round(bl[1])
    height = max(1, bottom - top)
    rows = []
    for y in range(height):
        t = (y + .5) / height
        left = tl[0] + (bl[0] - tl[0]) * t
        right = tr[0] + (br[0] - tr[0]) * t
        rows.append((round(left), max(1, round(right - left))))
    batch = getattr(__getattr__('draw'), 'textured_rows', None)
    if batch is not None:
        batch(target, image, top, rows)
        return
    transform = __getattr__('transform')
    source = transform.smoothscale(image, (image.get_width(), height))
    for y, (left, width) in enumerate(rows):
        row = source.subsurface((0, y, source.get_width(), 1))
        target.blit(transform.smoothscale(row, (width, 1)), (left, top + y))


def install(backend):
    global _backend
    previous, _backend = _backend, backend
    return previous


def __getattr__(name):
    global _backend
    if _backend is None:
        import pygame
        _backend = pygame
    return getattr(_backend, name)
