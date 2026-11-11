"""The display's aspect ratio: General's Aspect Ratio (owner, 2026-11-11; reference/ASPECT_RATIO_PLAN.md).

SHS HD's frame is 384 x 512 layout units, 3:4. The other shapes keep its width and only grow it taller, so text wraps as
it always has and the extra height shows more of the scene above the story's column: 576 units at 2:3 (a location
picture's own shape, so all of it shows and nothing pans), 683 at 9:16. Fit Screen takes the window's shape, from 3:4 to
about 9:21; a wider window keeps 3:4 (the side panels or the backdrop beside it, as before).

Phones open in Fit Screen and a computer in 3:4. On a computer Fit Screen keeps 3:4 for windows between 3:4 and 2:3,
where a location's panning would fade out: 2:3 shows only when it is picked (owner, 2026-11-11).
"""
CHOICES = ('3:4', '2:3', '9:16', 'fit')
RATIOS = {'3:4': 3 / 4, '2:3': 2 / 3, '9:16': 9 / 16}
FRAME_WIDTH = 384                       # layout units, whatever the shape
TALLEST = 9 / 21                        # Fit Screen's narrowest: past it there is no picture left to pan


def default(fixed_window):
    """The shape when none is chosen: Fit Screen on a phone (its window is its screen), 3:4 on a computer."""
    return 'fit' if fixed_window else '3:4'


def ratio(choice, window_size, fixed_window=False):
    """The frame's width over its height for a choice (CHOICES) in a window of `window_size` pixels."""
    if choice in RATIOS:
        return RATIOS[choice]
    width, height = window_size
    shape = width / height if width > 0 and height > 0 else RATIOS['3:4']
    if shape >= RATIOS['3:4']:
        return RATIOS['3:4']
    if not fixed_window and shape >= RATIOS['2:3']:
        return RATIOS['3:4']
    return max(shape, TALLEST)


def frame_units(choice, window_size, fixed_window=False):
    """The frame's size in layout units: always FRAME_WIDTH wide, as tall as the shape makes it."""
    return FRAME_WIDTH, FRAME_WIDTH / ratio(choice, window_size, fixed_window)
