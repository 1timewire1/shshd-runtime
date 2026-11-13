"""The display's aspect ratio: General's Aspect Ratio (owner, 2026-11-11; reference/ASPECT_RATIO_PLAN.md).

SHS HD's frame is 384 x 512 layout units, 3:4, built from HD's own photos: that stays exactly as it is. 2:3 keeps its
width and grows taller, 384 x 576, a location picture's own shape, so the whole picture shows and nothing pans. From
9:16 and narrower the frame is the story's 320-unit column wide, as SD SHS and Cause of Death fill an iPhone's screen
with it: everything is a fifth larger than at 3:4, and what overhangs the column (a portrait's ring) is cut at the
screen's edge as theirs is (owner, 2026-11-11). Between 2:3 and 9:16 the width goes from one to the other. The frame is
as tall as its shape makes it (9:16: 569 units, a 9:20 phone: 711); every unit past the column's own height is above it.

Fit Screen takes the window's shape, from 3:4 to about 9:21; a wider window keeps 3:4 (the side panels or the backdrop
beside it, as before). Phones open in Fit Screen and a computer in 3:4. On a computer Fit Screen keeps 3:4 for windows
between 3:4 and 2:3, where a location's panning would fade out: 2:3 shows only when it is picked (owner, 2026-11-11).
"""
CHOICES = ('3:4', '2:3', '9:16', 'fit')
RATIOS = {'3:4': 3 / 4, '2:3': 2 / 3, '9:16': 9 / 16}
FRAME_WIDTH = 384                       # layout units: HD's frame, at 3:4 and 2:3
COLUMN_WIDTH = 320                      # the story's column: the frame's width from 9:16 on
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


def width_for(shape):
    """The frame's width in layout units for a shape (width over height): HD's 384 to 2:3, the column's 320 from 9:16,
    in between along the way."""
    if shape >= RATIOS['2:3']:
        return FRAME_WIDTH
    if shape <= RATIOS['9:16']:
        return COLUMN_WIDTH
    along = (shape - RATIOS['9:16']) / (RATIOS['2:3'] - RATIOS['9:16'])
    return COLUMN_WIDTH + (FRAME_WIDTH - COLUMN_WIDTH) * along


def frame_units(choice, window_size, fixed_window=False):
    """The frame's size in layout units: width_for its shape, as tall as the shape makes it."""
    shape = ratio(choice, window_size, fixed_window)
    width = width_for(shape)
    return width, width / shape
