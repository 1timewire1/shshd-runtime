"""Shared drawing of the adapter's verified whole-screen fade tracks."""
from . import graphics as pygame


def draw_transition(canvas, transition):
    coverage = transition.coverage
    if coverage <= 0:
        return
    width, height = canvas.get_size()
    if transition.selector == 6:
        layer = pygame.Surface((width, height), pygame.SRCALPHA)
        layer.fill((0, 0, 0, round(255 * coverage)))
        canvas.blit(layer, (0, 0))
    elif transition.selector in (1, 2):
        # Native zero-anchored layers grow down/right, in sixteen equal
        # strips. Screen scaling is shared with all the other game artwork.
        for index in range(16):
            if transition.selector == 1:
                y = round(index * height / 16)
                bottom = round((index + coverage) * height / 16)
                rect = (0, y, width, bottom - y)
            else:
                x = round(index * width / 16)
                right = round((index + coverage) * width / 16)
                rect = (x, 0, right - x, height)
            pygame.draw.rect(canvas, (0, 0, 0), rect)
