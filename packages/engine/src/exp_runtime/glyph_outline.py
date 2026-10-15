"""TrueType glyph outlines and CoreGraphics-style fill-and-stroke text.

`CSFont::activateFont` (HD 1.4.38, 00004a1c) draws a stroked font with `CGContextSetTextDrawingMode(2)` (fill, then
stroke) and `CGContextSetLineWidth(width)`: the stroke straddles each glyph contour by half the width on either side,
with CoreGraphics' default mitered joins (miter limit 10). A round dilation of the rendered glyph instead rounds every
corner (the "th" of a flair notice) and leaves a notch where two stems' outlines meet (under the "n"). This module
reads the outlines from the face's `glyf` table and rasterizes fill and stroke itself, supersampled for antialiasing.
"""
import math
import struct

from PIL import Image, ImageChops, ImageDraw

MITER_LIMIT = 10
SUPERSAMPLE = 4


class Outlines:
    """The `glyf` outlines of one TrueType face, or `available` False (CFF / unreadable)."""

    def __init__(self, data: bytes):
        self.available = False
        try:
            count = struct.unpack_from('>H', data, 4)[0]
            self.tables = {}
            for n in range(count):
                tag, _, start, length = struct.unpack_from('>4sIII', data, 12 + n * 16)
                self.tables[tag] = data[start:start + length]
            head = self.tables[b'head']
            self.units = struct.unpack_from('>H', head, 18)[0]
            long_offsets = struct.unpack_from('>h', head, 50)[0] == 1
            glyphs = struct.unpack_from('>H', self.tables[b'maxp'], 4)[0]
            loca = self.tables[b'loca']
            if long_offsets:
                self.offsets = struct.unpack_from(f'>{glyphs + 1}I', loca)
            else:
                self.offsets = tuple(2 * v for v in struct.unpack_from(f'>{glyphs + 1}H', loca))
            self.glyf = self.tables[b'glyf']
            self.cmap = self._cmap(self.tables[b'cmap'])
            self.available = bool(self.cmap)
        except (KeyError, struct.error, IndexError):
            self.available = False

    @staticmethod
    def _cmap(table):
        count = struct.unpack_from('>H', table, 2)[0]
        best = None
        for n in range(count):
            platform, encoding, offset = struct.unpack_from('>HHI', table, 4 + n * 8)
            fmt = struct.unpack_from('>H', table, offset)[0]
            if fmt in (4, 12) and (platform, encoding) in ((3, 1), (3, 10), (0, 3), (0, 4), (0, 6)):
                if best is None or fmt == 12:
                    best = offset
        if best is None:
            return {}
        fmt = struct.unpack_from('>H', table, best)[0]
        mapping = {}
        if fmt == 4:
            segments = struct.unpack_from('>H', table, best + 6)[0] // 2
            base = best + 14
            ends = struct.unpack_from(f'>{segments}H', table, base)
            starts = struct.unpack_from(f'>{segments}H', table, base + 2 * segments + 2)
            deltas = struct.unpack_from(f'>{segments}h', table, base + 4 * segments + 2)
            ranges_at = base + 6 * segments + 2
            ranges = struct.unpack_from(f'>{segments}H', table, ranges_at)
            for i in range(segments):
                for code in range(starts[i], min(ends[i], 0xfffe) + 1):
                    if code > 0x2ff:
                        break
                    if ranges[i] == 0:
                        glyph = (code + deltas[i]) & 0xffff
                    else:
                        at = ranges_at + 2 * i + ranges[i] + 2 * (code - starts[i])
                        glyph = struct.unpack_from('>H', table, at)[0]
                        if glyph:
                            glyph = (glyph + deltas[i]) & 0xffff
                    if glyph:
                        mapping[code] = glyph
        else:
            groups = struct.unpack_from('>I', table, best + 12)[0]
            for i in range(groups):
                start, end, first = struct.unpack_from('>III', table, best + 16 + 12 * i)
                for code in range(start, min(end, 0x2ff) + 1):
                    mapping[code] = first + code - start
        return mapping

    def contours(self, code):
        """Closed contours of the glyph for character `code`, as lists of (x, y, on_curve) in font units."""
        glyph = self.cmap.get(code)
        return [] if glyph is None else self._glyph(glyph, 0)

    def _glyph(self, glyph, depth):
        start, end = self.offsets[glyph], self.offsets[glyph + 1]
        if end <= start or depth > 8:
            return []
        data = self.glyf[start:end]
        contours = struct.unpack_from('>h', data, 0)[0]
        if contours >= 0:
            return self._simple(data, contours)
        return self._composite(data, depth)

    @staticmethod
    def _simple(data, contours):
        ends = struct.unpack_from(f'>{contours}H', data, 10)
        points = ends[-1] + 1 if ends else 0
        at = 10 + 2 * contours
        at += 2 + struct.unpack_from('>H', data, at)[0]
        flags = []
        while len(flags) < points:
            flag = data[at]
            at += 1
            flags.append(flag)
            if flag & 8:
                flags.extend([flag] * data[at])
                at += 1
        coordinates = []
        for short, same in ((2, 16), (4, 32)):
            value, values = 0, []
            for flag in flags[:points]:
                if flag & short:
                    delta = data[at]
                    at += 1
                    value += delta if flag & same else -delta
                elif not flag & same:
                    value += struct.unpack_from('>h', data, at)[0]
                    at += 2
                values.append(value)
            coordinates.append(values)
        xs, ys = coordinates
        result, first = [], 0
        for last in ends:
            result.append([(xs[i], ys[i], bool(flags[i] & 1)) for i in range(first, last + 1)])
            first = last + 1
        return result

    def _composite(self, data, depth):
        at, result = 10, []
        while True:
            flags, glyph = struct.unpack_from('>HH', data, at)
            at += 4
            if flags & 1:
                dx, dy = struct.unpack_from('>hh', data, at)
                at += 4
            else:
                dx, dy = struct.unpack_from('>bb', data, at)
                at += 2
            a, b, c, d = 1., 0., 0., 1.
            if flags & 8:
                a = d = struct.unpack_from('>h', data, at)[0] / 16384
                at += 2
            elif flags & 0x40:
                a, d = (v / 16384 for v in struct.unpack_from('>hh', data, at))
                at += 4
            elif flags & 0x80:
                a, b, c, d = (v / 16384 for v in struct.unpack_from('>hhhh', data, at))
                at += 8
            if not flags & 2:
                dx = dy = 0          # point-matched components are not used by these faces
            for contour in self._glyph(glyph, depth + 1):
                result.append([(a * x + c * y + dx, b * x + d * y + dy, on) for x, y, on in contour])
            if not flags & 0x20:
                return result


def flatten(contour, scale, step=1.0):
    """A closed quadratic contour as a polyline in pixels (y down, origin at the glyph origin)."""
    if not contour:
        return []
    points = [(x * scale, -y * scale, on) for x, y, on in contour]
    # Start on an on-curve point (or the midpoint of two off-curve ones).
    start = next((i for i, p in enumerate(points) if p[2]), None)
    if start is None:
        a, b = points[0], points[1]
        points.insert(0, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, True))
        start = 0
    points = points[start:] + points[:start]
    result = [points[0][:2]]
    current = points[0][:2]
    count = len(points)
    i = 1
    while i <= count:
        p = points[i % count]
        if p[2]:
            result.append(p[:2])
            current = p[:2]
            i += 1
            continue
        nxt = points[(i + 1) % count]
        end = nxt[:2] if nxt[2] else ((p[0] + nxt[0]) / 2, (p[1] + nxt[1]) / 2)
        length = math.hypot(p[0] - current[0], p[1] - current[1]) + math.hypot(end[0] - p[0], end[1] - p[1])
        pieces = max(2, int(length / step))
        for k in range(1, pieces + 1):
            t = k / pieces
            u = 1 - t
            result.append((u * u * current[0] + 2 * u * t * p[0] + t * t * end[0],
                           u * u * current[1] + 2 * u * t * p[1] + t * t * end[1]))
        current = end
        i += 2 if nxt[2] else 1
    # Drop repeats (zero-length segments have no direction).
    cleaned = [result[0]]
    for point in result[1:]:
        if math.hypot(point[0] - cleaned[-1][0], point[1] - cleaned[-1][1]) > 1e-6:
            cleaned.append(point)
    if len(cleaned) > 1 and math.hypot(cleaned[0][0] - cleaned[-1][0], cleaned[0][1] - cleaned[-1][1]) < 1e-6:
        cleaned.pop()
    return cleaned


def _stroke_polygons(polyline, half):
    """Each segment as a quad and each vertex's outer join (miter, or bevel past the limit)."""
    count = len(polyline)
    if count < 2 or half <= 0:
        return []
    shapes = []
    directions = []
    for i in range(count):
        (x0, y0), (x1, y1) = polyline[i], polyline[(i + 1) % count]
        length = math.hypot(x1 - x0, y1 - y0)
        directions.append(((x1 - x0) / length, (y1 - y0) / length))
        nx, ny = -directions[-1][1] * half, directions[-1][0] * half
        shapes.append([(x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)])
    for i in range(count):
        d1, d2 = directions[i - 1], directions[i]
        cross = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(cross) < 1e-9:
            continue
        side = -1 if cross > 0 else 1                       # the outer side of the turn
        n1 = (-d1[1] * side, d1[0] * side)
        n2 = (-d2[1] * side, d2[0] * side)
        vx, vy = polyline[i]
        a = (vx + n1[0] * half, vy + n1[1] * half)
        b = (vx + n2[0] * half, vy + n2[1] * half)
        dot = n1[0] * n2[0] + n1[1] * n2[1]
        if dot > -1 + 1e-9 and math.sqrt(2 / (1 + dot)) <= MITER_LIMIT:
            m = (vx + (n1[0] + n2[0]) * half / (1 + dot), vy + (n1[1] + n2[1]) * half / (1 + dot))
            shapes.append([(vx, vy), a, m, b])
        else:
            shapes.append([(vx, vy), a, b])
    return shapes


def coverage(outlines, code, px, stroke_width=0., fill=True):
    """(mask, left, top): the glyph's fill plus a mitered stroke `stroke_width` pixels wide (only the stroke when
    `fill` is False), as an 'L' alpha mask at `px` pixels per em, with the mask's top-left relative to the pen
    position on the baseline. None when the face has no outline for `code`."""
    contours = outlines.contours(code)
    if not contours:
        return None
    s = SUPERSAMPLE
    scale = px * s / outlines.units
    polylines = [p for p in (flatten(c, scale, step=max(.5, s / 2)) for c in contours) if len(p) > 2]
    if not polylines:
        return None
    half = stroke_width * s / 2
    shapes = [shape for p in polylines for shape in _stroke_polygons(p, half)] if half > 0 else []
    xs = [x for p in polylines + shapes for x, _ in p]
    ys = [y for p in polylines + shapes for _, y in p]
    left = math.floor(min(xs) / s) - 1
    top = math.floor(min(ys) / s) - 1
    right = math.ceil(max(xs) / s) + 1
    bottom = math.ceil(max(ys) / s) + 1
    size = ((right - left) * s, (bottom - top) * s)
    ox, oy = -left * s, -top * s
    image = Image.new('1', size, 0)
    if fill:
        for polyline in polylines:
            layer = Image.new('1', size, 0)
            ImageDraw.Draw(layer).polygon([(x + ox, y + oy) for x, y in polyline], fill=1)
            image = ImageChops.logical_xor(image, layer)    # even-odd: holes are the inner contours
    draw = ImageDraw.Draw(image)
    for shape in shapes:
        draw.polygon([(x + ox, y + oy) for x, y in shape], fill=1)
    mask = image.convert('L').resize((right - left, bottom - top), Image.BOX)
    return mask, left, top
