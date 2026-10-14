"""Drawing/platform primitives for the shared presentation code.

Desktop uses pygame directly. A mobile host installs its backend before it
imports the application; menus, panel geometry and event handling stay shared.
"""
_backend = None


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


def create_menu_music():
    mixer = __getattr__('mixer')
    return mixer.menu_music if hasattr(mixer, 'menu_music') else _MenuMusic(mixer)


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
