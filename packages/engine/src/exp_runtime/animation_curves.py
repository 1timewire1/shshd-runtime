"""Native timing curves shared by the presentation models and drawing hosts."""


def power_in_out(progress, rate=10):
    """Android CCEaseInOut (001436a8), used by the main menu's slides."""
    value = min(1., max(0., progress))
    return .5 * (2 * value)**rate if value < .5 else 1 - .5 * (2 - 2 * value)**rate


def ease_in_out(progress):
    """UIKit curve 0: cubic-bezier(.42, 0, .58, 1)."""
    if progress <= 0:
        return 0.
    if progress >= 1:
        return 1.
    low, high = 0., 1.
    for _ in range(24):
        t = (low + high) / 2
        x = 3 * (1 - t)**2 * t * .42 + 3 * (1 - t) * t*t * .58 + t**3
        if x < progress:
            low = t
        else:
            high = t
    return 3 * (1 - t) * t*t + t**3
