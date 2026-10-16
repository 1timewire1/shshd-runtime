"""SHSUIMinigameBase's final view fade, outside the capped game clock."""
from .. import graphics as pygame
from ..animation_curves import ease_in_out


def draw_exit(canvas, remaining_ms, resources):
    # SHS iOS 00085738 fades the GL view over .8 seconds and returns its
    # callback after 960ms. Android 000b0af0 has the timer but no UIView fade.
    if getattr(resources.library, 'kind', 'apk') == 'ipa':
        layer = pygame.Surface(canvas.get_size(), pygame.SRCALPHA)
        layer.fill((0, 0, 0, round(255 * ease_in_out((960 - remaining_ms) / 800))))
        canvas.blit(layer, (0, 0))
