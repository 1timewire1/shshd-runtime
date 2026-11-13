"""A translated pack's frame backdrop in a frame taller than 3:4 (General's Aspect Ratio).

The translators build the backdrop (profile TRANSLATED_FRAME_BACKDROP: New Rules' UI pattern, BREW's checks) for the
3:4 frame: a pattern tiled down the picture from its top, with two bars drawn just above and below where the player
shows a location strip. Stretched or cropped to a taller frame the bars would leave the strip, so the picture is
lengthened instead: whole repeats of the pattern are inserted in each plain stretch (above the upper bar, behind the
strip, below the lower bar), in the picture's own pixels before it is scaled. The repeat is measured where the picture
is plainest, the middle of the stretch below the strip; anything short of a whole repeat is cut from the picture's own
end (its top above the strip, its bottom below).
"""
from . import graphics as pygame

LONGEST_REPEAT = 512        # source rows
FRAME_WIDTH = 384           # the backdrop's width in frame units
CLEAR_OF_BARS = 30          # frame units from the strip's edge: past either backdrop's bar (New Rules' is 21)


def _rows(surface):
    width, height = surface.get_size()
    data = pygame.image.tobytes(surface, 'RGBA')
    pitch = width * 4
    return [data[y * pitch:(y + 1) * pitch] for y in range(height)]


def repeat(rows, lo, hi):
    """The shortest p with every row in [lo, hi) equal to the row p below it, seen over two whole repeats at least, or
    None. A stretch of identical rows repeats every row; one with a change in it (a checkerboard's square edges) needs
    the pattern's whole repeat."""
    for p in range(1, min(LONGEST_REPEAT, (hi - lo) // 2) + 1):
        if rows[lo] != rows[lo + p]:
            continue
        if all(rows[i] == rows[i + p] for i in range(lo, hi - p)):
            return p
    return None


def _grow(rows, start, at, length, crop, row_at):
    """rows[start:...] (this part, `len(rows)` long) made `length` long: whole repeats inserted at `at`, then the
    excess cut from the `crop` end; shorter, cut from that end ('middle': about its middle)."""
    if length <= len(rows):
        cut = len(rows) - length
        if crop == 'top':
            return rows[cut:]
        if crop == 'bottom':
            return rows[:length]
        middle = len(rows) // 2 - cut // 2
        return rows[:middle] + rows[middle + cut:]
    needed = length - len(rows)
    if row_at is None:
        # No repeat found: the row at `at` is repeated (a plain stretch's own colour).
        source = rows[min(at, len(rows) - 1)] if rows else b''
        return rows[:at] + [source] * needed + rows[at:]
    period, at_row = row_at
    whole = -(-needed // period) * period
    grown = rows[:at] + [at_row(start + at + t) for t in range(whole)] + rows[at:]
    excess = whole - needed
    if crop == 'top':
        return grown[excess:]
    return grown[:len(grown) - excess]


def lengthen(image, strip, wanted, height):
    """`image` (the 3:4 backdrop, source pixels) with its rows rearranged for a frame `height` source rows tall: the
    strip it was drawn around, rows `strip` = (top, bottom) at 3:4, now at rows `wanted` = (top, bottom)."""
    rows = _rows(image)
    count = len(rows)
    top, bottom = (min(max(round(v), 0), count) for v in strip)
    new_top, new_bottom = max(0, round(wanted[0])), max(0, round(wanted[1]))
    # The repeat, measured clear of the bars and of the stripe's shaded ends (New Rules'): below the strip first, its
    # middle, then nearer the bar, then the stretch above.
    clear = round(CLEAR_OF_BARS * image.get_width() / FRAME_WIDTH)
    below_len = count - bottom
    row_at = None
    for lo, hi in ((bottom + below_len // 6, count - below_len // 6), (bottom + clear, count - below_len // 3),
                   (top // 6, top * 5 // 6)):
        period = repeat(rows, lo, hi) if hi - lo >= 4 else None
        if period is not None:
            row_at = (period, lambda y, lo=lo, p=period: rows[lo + (y - lo) % p])
            break
    above, behind, below = rows[:top], rows[top:bottom], rows[bottom:]
    # Inserted just clear of the bars (the stretch beside a bar is plain, the picture's ends may be shaded).
    parts = (_grow(above, 0, max(0, len(above) - clear), new_top, 'top', row_at)
             + _grow(behind, top, len(behind) // 2, max(0, new_bottom - new_top), 'middle', row_at)
             + _grow(below, bottom, min(len(below), clear), max(0, height - new_bottom), 'bottom', row_at))
    parts = (parts + parts[-1:] * height)[:height]
    return pygame.image.frombytes(b''.join(parts), (image.get_width(), height), 'RGBA')


_extended = {}


def extend(image, height):
    """`image` (a backdrop with no bars: the arena's frame picture) made `height` rows tall: whole repeats of its pattern
    inserted at its middle, then resampled to exactly `height`, so nothing of its own shaded top or bottom is cut and
    the repeat never breaks. The same picture and height give the same surface (kept), so a game drawing the bottom of
    it and the player drawing the rest above match."""
    key = (id(image), image.get_size(), height)
    found = _extended.get(key)
    if found is not None:
        return found
    rows = _rows(image)
    count = len(rows)
    needed = height - count
    if needed <= 0:
        return image
    middle = count // 2
    period = None
    for lo, hi in ((middle + count // 12, count - count // 6), (count // 6, middle - count // 12)):
        period = repeat(rows, lo, hi) if hi - lo >= 4 else None
        if period is not None:
            break
    if period is None:
        grown = rows[:middle] + [rows[middle]] * needed + rows[middle:]
    else:
        whole = -(-needed // period) * period
        grown = rows[:middle] + [rows[lo + (middle + t - lo) % period] for t in range(whole)] + rows[middle:]
    surface = pygame.image.frombytes(b''.join(grown), (image.get_width(), len(grown)), 'RGBA')
    if len(grown) != height:
        surface = pygame.transform.smoothscale(surface, (image.get_width(), height))
    if len(_extended) > 8:
        _extended.clear()
    found = _extended[key] = surface
    return found
