"""The HD build's landscape side panels: the story tree (left) and the
faceplace wall (right), drawn from HD's own art.

Both are UIKit views laid out in code, not layout-bank content (see
legacy/findings.md, "HD side panels, from the binary"). They sit in the two
224-point-wide bands beside the game view, which the desktop reproduces by
widening its window; every number below is in those points (an iPad point is
one pixel of the 1024x768 landscape screen) and each panel is drawn at
`rect.height / 768` pixels per point.

What the binary states:
- `SHSDTUnderView` / `SHSFSBGView` `drawRect:` fill the panel white when the
  feature is enabled for the episode and otherwise black with the collage
  (resource 10, drawn at (0, 0) of the screen, alpha 0.5) -- the same faded
  collage as beside the main menu -- so an episode without a story tree or
  faceplace wall shows exactly that, with the "... feature is not supported in
  this episode" string (HD strings 267/268) in gray Arial 12.
- The dark divider between panel and game is pack-155 frame 0, 23 px wide
  drawn half as wide; the story tree's title and footer bars are frames 3
  ("Rewind" chevrons) and 1 ("Fast Forward"), 36 tall, with the words drawn in
  white Arial Rounded 16; the wall's header is frame 72 ("faceplace" baked in).
- Tree nodes are the frames of resource 18 (a 12-frame pack), drawn at `sz / 105` of their pixel size with `sz` (`DTNode::sz`);
  everything else about the tree -- where each node class puts its children, its rows, stubs, outlines, labels, which lines
  are yellow, black or gray, which icons are in color -- is `dt_layout.py`, ported from the app's `DTNode` classes; this
  module lays the result out in the panel (scrolling, zooming, the Rewind / Fast Forward bars) and paints it.
- Wall messages are `SHSFSView.drawMessage` at width 224: text 75 in and 146
  wide beside the face (the alert's face, `drawFace`), each with a 0xe0e0e0
  rule under it. The wall is a scroll view (0, 36, 224 x 732, no bounce), newest on top, back at the top when a post arrives;
  a linked post opens its URL when tapped; `{`, `>` and `}` are pack-155 frames 69-71 (legacy/findings.md, "The faceplace wall,
  decompiled").

Measured from the app's screenshots rather than read: the default `sz` (52.7; the static starts at 50), and the first row's top
below the title bar (48.5 points).
"""
from dataclasses import dataclass, replace
from functools import lru_cache
import logging

from . import graphics as pygame

from .graphics import faded
from .cgbi import CgBIError, decode as decode_cgbi
from .content import ContentError
from .dt_layout import DEFAULT_SZ as DT_DEFAULT_SZ, FONT_UNIT, SZ_RANGE, Layout, Metrics
from .fonts import TextStyle
from .menu import MenuStrings
from .ui_assets import ImagePack, UIAssetError
from .vector_text import cap_height, descent, load_font_sized

PANEL = (224, 768)
DIVIDER_WIDTH = 11.5
BAR = 36
COLLAGE_ID, NODES_ID = 10, 18
COLLAGE_ALPHA = 128
# The collage point drawn at each panel's top-left, 1 point per collage pixel. The
# binary draws it center-aligned inside each view (`renderCutupAligned` under a
# translate to the view's center), so these come from matching IMG_0082's two
# panels against the resource (correlation 0.996 and 0.979 on the panel content).
COLLAGE_ORIGIN = {'left': (409, 92), 'right': (522, 128)}
# Pack 155.
DIVIDER, FAST_FORWARD, REWIND, WALL_HEADER, DARK_BAR = 0, 1, 3, 72, 56
# Strings (HD bank 15).
STR_REWIND, STR_FAST_FORWARD, STR_NO_WALL, STR_NO_TREE = 269, 270, 267, 268

TREE_TOP = BAR + 48.5   # the first row's top: below the title bar, plus the margin measured from the app's screenshots
NA_COLOR = (191, 191, 191)
RULE = (224, 224, 224)

# `SHSFSView drawMessage:index:atX:atY:withWidth:...` (000878d8), drawn at x 0 and width 224 in its row's own view.
MESSAGE_FACE_X, MESSAGE_FACE_WIDTH = 75, 224 - 78
MESSAGE_PLAIN_X, MESSAGE_PLAIN_WIDTH = 15, 224 - 18
TEXT_TOP = 3            # a message (not a continuation) starts its text 3 points down
# `drawFace` at (x + 18, y - 11), scale 0.2: the housing's ring and disc are centred 25.5 and 38.5 further.
MESSAGE_FACE_CENTER = (18 + 25.5, -11 + 38.5)
FACE_MIN_HEIGHT = 56    # `measureMessageMinimumHeight`: a face message's group is at least this tall
ROW_PAD = 3             # ... and every row but a group's last is 3 taller when it has text
LAST_PAD = 7            # `measureMessageHeight`: the last row of a group is 4 + 3 taller
PICTURE_PAD = 4         # a picture row is its image's height plus 4 (20 when the image does not load)
MISSING_PICTURE = 20
RULE_X, RULE_RISE = 11, 2   # the rule: from x 11 (the width less 2 long, so to the view's edge), 1 tall, 2 above the next row
# `checkInit` makes the body and sender fonts at 14 points; `CSFont::setFontSize` takes the cap height and the descent (also
# its line gap) from the iOS font, so a line is cap + descent. The device's lines are 13.3 apart and the first baseline 13.25
# below a post's top, `TEXT_TOP` + cap (IMG_0245, IMG_0299), where desktop Arial 14 gives 13.0 and 13.03: each font's cap
# and descent are scaled to that pitch.
DEVICE_PITCH = 13.3
ARIAL_CAP, ARIAL_DESCENT = 1467 / 2048, 434 / 2048     # without a TrueType face (CSFont +0x24 / +0x14 per point)
NAME_COLOR = (107, 128, 167)                            # FSSenderName, ARGB 0xff6b80a7


class PanelMetrics(Metrics):
    """The tree's label measures, from the real fonts: an outer label is Arial Rounded 10 and an exit label Arial 6 at their original
    size (the layout scales lengths by `sz / 35`)."""
    FONTS = {'outer': ('ArialRoundedMTBold14', 10), 'exit': ('ArialMT14', 6)}

    def __init__(self, panels):
        self.panels, self.cache = panels, {}

    def length(self, text, kind):
        if not text:
            return 0.0
        key = (text, kind)
        if key not in self.cache:
            family, size = self.FONTS[kind]
            name = self.panels.font(family, size)
            if name is None:
                self.cache[key] = super().length(text, kind)
            else:
                self.cache[key] = self.panels.text.layout(name, text, 2 ** 31, TextStyle(size * 1.15, 0, (0, 0, 0))).width
        return self.cache[key]


class TreePainter:
    """Paints `Layout.draw_ops()` onto the panel: tree points to panel pixels by `shift` and the panel's scale."""

    def __init__(self, panels, panel, s, cam_x, cam_y, frames, sz, clip):
        self.panels, self.panel, self.s, self.frames, self.sz = panels, panel, s, frames, sz
        self.shift = (-cam_x, TREE_TOP - cam_y)
        left, top, width, height = clip
        self.clip = pygame.Rect(round(left * s), round(top * s), round(width * s), round(height * s))
        self.area = pygame.Rect(self.clip)
        panel.set_clip(self.clip)

    def point(self, x, y):
        return (x + self.shift[0]) * self.s, (y + self.shift[1]) * self.s

    def visible(self, points, pad=0.0):
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        return (max(xs) + pad >= self.area.left and min(xs) - pad <= self.area.right
                and max(ys) + pad >= self.area.top and min(ys) - pad <= self.area.bottom)

    def stroke(self, width):
        return max(1, round(width * self.s))

    def paint(self, ops):
        try:
            for op in ops:
                getattr(self, 'do_' + op[0])(*op[1:])
        finally:
            self.panel.set_clip(None)

    def do_path(self, points, color, width):
        pixels = [self.point(*p) for p in points]
        if len(pixels) < 2 or not self.visible(pixels, width * self.s):
            return
        wide = self.stroke(width)
        if wide <= 1:
            pygame.draw.aalines(self.panel, color, False, pixels)
        else:
            pygame.draw.lines(self.panel, color, False, pixels, wide)
            if wide > 3:
                for x, y in pixels[1:-1]:
                    pygame.draw.circle(self.panel, color, (round(x), round(y)), wide // 2)

    def do_rect(self, x, y, w, h, color, width):
        left, top = self.point(x, y)
        box = pygame.Rect(round(left), round(top), round(w * self.s), round(h * self.s))
        if box.colliderect(self.area):
            pygame.draw.rect(self.panel, color, box, self.stroke(width))

    def do_ellipse(self, x, y, w, h, color, width, fill):
        left, top = self.point(x, y)
        box = pygame.Rect(round(left), round(top), max(1, round(w * self.s)), max(1, round(h * self.s)))
        if not box.colliderect(self.area):
            return
        if fill:
            pygame.draw.ellipse(self.panel, color, box)
        else:
            pygame.draw.ellipse(self.panel, color, box, min(self.stroke(width), max(1, min(box.size) // 2)))

    def do_polygon(self, points, color, width):
        pixels = [self.point(*p) for p in points]
        if self.visible(pixels, width * self.s):
            pygame.draw.polygon(self.panel, color, pixels, self.stroke(width))

    def do_bezier(self, origin, start, curves, color, width):
        ox, oy = origin
        pixels, here = [], start
        for c1, c2, end in curves:
            for step in range(17):
                t = step / 16
                a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t ** 2, t ** 3
                x = a * here[0] + b * c1[0] + c * c2[0] + d * end[0]
                y = a * here[1] + b * c1[1] + c * c2[1] + d * end[1]
                pixels.append(self.point(ox + x, oy + y))
            here = end
        if self.visible(pixels, width * self.s):
            pygame.draw.polygon(self.panel, color, pixels, self.stroke(width))

    def do_image(self, image, mono, cx, cy, scale):
        if image >= len(self.frames):
            return
        surface = self.frames[image][1 if mono else 0]
        w, h = surface.get_size()
        size = max(1, round(w * scale * self.s)), max(1, round(h * scale * self.s))
        x, y = self.point(cx, cy)
        box = pygame.Rect(0, 0, *size)
        box.center = round(x), round(y)
        if box.colliderect(self.area):
            self.panel.blit(pygame.transform.smoothscale(surface, size), box)

    def do_fill(self, x, y, w, h, color):
        left, top = self.point(x, y)
        box = pygame.Rect(round(left), round(top), round(w * self.s), round(h * self.s))
        if box.colliderect(self.area):
            pygame.draw.rect(self.panel, color, box)

    def do_text(self, lines, kind, left, centre, width, color):
        family, original = PanelMetrics.FONTS[kind]
        size = int(self.sz * original / FONT_UNIT)         # `FPToFixed(sz * size / 35)`: whole points
        if size < 1:
            return
        name = self.panels.font(family, size)
        if name is None:
            return
        step = self.panels._metrics().line_height(kind) * self.sz / FONT_UNIT
        top = centre - len(lines) * step / 2
        for index, line in enumerate(lines):
            if not line:
                continue
            layout = self.panels.text.layout(name, line, 2 ** 31, TextStyle(step, 0, color))
            x = left if width is None else left + (width - layout.width) / 2
            px, py = self.point(x, top + index * step)
            if self.area.collidepoint(round(px), round(py)) or self.area.collidepoint(round(px + layout.width * self.s), round(py)):
                self.panels.text.draw_layout(self.panel, name, layout, px, py, scale=self.s)


@dataclass
class WallRow:
    """One `SHSFSMessageContentView`: a post, or one continuation of it, as `drawMessage` lays it out."""
    key: object             # the post's AlertKey; its face is drawn on the post's own row
    face: bool              # `isFaceMessage`: the text starts beside the face
    first: bool             # not a continuation: the text starts `TEXT_TOP` down and the face is drawn
    last: bool              # `isLastMessage`: the bottom row of its group, with the rule under it
    url: str
    name: object            # the sender's name on the post's own row, else None
    layout: object          # the text, or None for a picture
    font_key: str
    picture: object
    height: float           # `measureMessageHeight`
    advance: float = 0.0    # `measureMessageMinimumHeight`: where the next row starts

    @property
    def x(self):
        return MESSAGE_FACE_X if self.face else MESSAGE_PLAIN_X


class SidePanels:
    def __init__(self, resources, text_renderer, dialogue_renderer, alert_renderer):
        self.resources, self.text, self.art, self.alert = resources, text_renderer, dialogue_renderer, alert_renderer

    # -- assets ---------------------------------------------------------
    def _raw(self, resource_id):
        try:
            return self.resources.library.hd_raw_resource(resource_id)
        except (AttributeError, ContentError):
            return None

    @lru_cache(maxsize=1)
    def collage(self):
        data = self._raw(COLLAGE_ID)
        if data is None:
            return None
        try:
            image = decode_cgbi(data).convert('RGB')
        except CgBIError:
            return None
        return pygame.image.frombytes(image.tobytes(), image.size, 'RGB').convert()

    @lru_cache(maxsize=1)
    def node_frames(self):
        """[(color, grayscale)] surfaces of the resource-18 pack, native size."""
        data = self._raw(NODES_ID)
        if data is None:
            return None
        try:
            pack = ImagePack.parse(data)
        except UIAssetError:
            return None
        from PIL import Image, ImageOps
        frames = []
        for raster in pack.images:
            image = Image.frombytes('RGBA', (raster.width, raster.height), raster.pixels)
            gray = ImageOps.grayscale(image.convert('RGB')).convert('RGB')
            gray.putalpha(image.getchannel('A'))
            frames.append(tuple(pygame.image.frombytes(im.tobytes(), im.size, 'RGBA').convert_alpha()
                                for im in (image, gray)))
        return frames

    @lru_cache(maxsize=1)
    def strings(self):
        data = self._raw(15)
        try:
            return None if data is None else MenuStrings.parse(data)
        except (ContentError, ValueError):
            return None

    def available(self):
        try:
            return (self.alert.available() and self.collage() is not None and self.node_frames() is not None
                    and len(self.art.pack(155).images) > WALL_HEADER)
        except (AttributeError, ValueError, pygame.error):
            return False

    def string(self, index, fallback):
        strings = self.strings()
        try:
            return strings[index]
        except (TypeError, ValueError, ContentError, IndexError):
            return fallback

    # -- shared pieces --------------------------------------------------
    def frame(self, index, size, flip=False):
        surface = self.art.frame_native(155, index)
        size = max(1, size[0]), max(1, size[1])
        if surface.get_size() != size:
            surface = pygame.transform.smoothscale(surface, size)
        return pygame.transform.flip(surface, True, False) if flip else surface

    @lru_cache(maxsize=4)
    def scaled_collage(self, size):
        return pygame.transform.smoothscale(self.collage(), size)

    def backdrop(self, panel, side, enabled, s, divider=True):
        if enabled:
            panel.fill((255, 255, 255))
        else:
            panel.fill((0, 0, 0))
            image = self.scaled_collage((round(1045 * s), round(1024 * s))).copy()
            image = faded(image, COLLAGE_ALPHA)
            x, y = COLLAGE_ORIGIN[side]
            panel.blit(image, (-round(x * s), -round(y * s)))
        if divider:
            self.divider(panel, side, s)

    def divider(self, panel, side, s):
        width = max(1, round(DIVIDER_WIDTH * s))
        strip = self.frame(DIVIDER, (width, panel.get_height()), flip=side == 'right')
        panel.blit(strip, (panel.get_width() - width if side == 'left' else 0, 0))

    def font(self, family, size):
        name = f'SidePanel{family}{size:.2f}'
        if name not in self.text.fonts:
            font = load_font_sized(self.resources.library, family, size)
            if font is None:
                return None
            if family == 'ArialMT14':
                # `DTcheckFontInit` (000916c4) and `-[SHSFSView checkInit]` build the exit-line, help-line and N/A
                # labels from the ArialMT face with the +0x7024 CSFontInfo, which `initFonts` fills from Arial Rounded
                # MT Bold: Arial's letters at Rounded's advances, as on the faceplace wall.
                rounded = load_font_sized(self.resources.library, 'ArialRoundedMTBold14', size)
                if rounded is not None:
                    font = replace(font, glyphs={code: replace(glyph, advance=rounded.glyphs[code].advance)
                                                 if code in rounded.glyphs else glyph
                                                 for code, glyph in font.glyphs.items()})
            self.text.fonts[name] = (font, None)
        return name

    def centered(self, panel, family, size, text, cx, top, width, color, s):
        """Wrapped, centered lines starting `top` points down; returns the bottom."""
        name = self.font(family, size)
        if name is None or not text:
            return top
        step = size * 1.15
        for line in self.text.layout(name, text, width, TextStyle(step, 0, color)).lines:
            one = self.text.layout(name, text[line.start:line.end].strip(), 2**31, TextStyle(step, 0, color))
            self.text.draw_layout(panel, name, one, (cx - one.width / 2) * s, top * s, scale=s)
            top += step
        return top

    def not_supported(self, panel, message, s, bar):
        if bar:
            panel.blit(self.frame(DARK_BAR, (panel.get_width(), round(48 * s))), (0, panel.get_height() - round(48 * s)))
        self.centered(panel, 'ArialMT14', 12, message, PANEL[0] / 2, PANEL[1] / 2 - 12, PANEL[0] - 24, NA_COLOR, s)

    # -- the story tree -------------------------------------------------
    BLANK = 2                   # pack-155 frame of a title / footer bar with nothing to offer

    def draw_tree(self, window, session, progress, rect):
        dt = session.engine.dt_view
        s = rect.height / PANEL[1]
        panel = pygame.Surface((round(PANEL[0] * s), rect.height)).convert()
        origin = (rect.right - panel.get_width() - round(rect.width * (1 - progress)), rect.y)
        self.tree_targets = []
        self._origin, self._scale = origin, s
        self.tree_scale = s
        self.tree_rect = pygame.Rect(origin, panel.get_size())
        enabled = dt.enabled        # `script_enable`: per episode (the saved tree persists, the flag does not)
        self.backdrop(panel, 'left', enabled, s, divider=False)
        if enabled:
            if dt.root is not None:
                self._tree(panel, dt, s)
            content = round((PANEL[0] - DIVIDER_WIDTH) * s)
            # Rewind needs a scene before the current one, Fast Forward one after it that is on the story followed; a bar
            # with nothing to go to is drawn empty and does nothing (`SHSDTTitleOverView` / `SHSDTHelpOverView drawRect:`).
            # While warping is locked (`SHSEngine +0x6490a`, until Football Season is finished) both show anyway (Rewind
            # only once there is a current scene) and a tap on either brings up the "Locked" notice.
            current = dt.current
            parent = dt.real_parent(current) if current is not None else None
            child = dt.real_child(current) if current is not None else None
            usable = {STR_REWIND: current is not None and (parent is not None or self.warp_locked),
                      STR_FAST_FORWARD: (child is not None and child.active) or self.warp_locked}
            for index, key, top in ((REWIND, STR_REWIND, 0), (FAST_FORWARD, STR_FAST_FORWARD, PANEL[1] - BAR)):
                shown = usable[key]
                panel.blit(self.frame(index if shown else self.BLANK, (content, round(BAR * s))), (0, round(top * s)))
                # Either way a black 1-point line closes the bar against the tree: the title view's last row (`fillRect(0,
                # h - 1, w, 1)`), the help view's first (IMG_0299: points 35 and 732).
                line = BAR - 1 if key == STR_REWIND else top
                panel.fill((0, 0, 0), pygame.Rect(0, round(line * s), content, max(1, round(s))))
                if shown:
                    self.tree_targets.append((pygame.Rect(origin[0], origin[1] + round(top * s), content, round(BAR * s)),
                                              ('rewind',) if key == STR_REWIND else ('forward',)))
                    text = self.string(key, 'Rewind' if key == STR_REWIND else 'Fast Forward')
                    self.centered(panel, 'ArialRoundedMTBold14', 16, text, 88, top + 9, 160, (255, 255, 255), s)
            self.divider(panel, 'left', s)
        else:
            self.not_supported(panel, self.string(STR_NO_TREE, 'The Decision Tree feature is not supported in this episode'),
                               s, bar=False)
            self.divider(panel, 'left', s)
        window.blit(panel, origin)

    warp_locked = False         # the app's warp lock (`Desktop.warp_unlocked` false): both bars show (see draw_tree)
    tree_targets = ()           # (window rectangle, ('node', node) | ('rewind',) | ('forward',)) of the last drawn tree
    tree_rect = None            # where the tree panel was drawn (window pixels)
    tree_scroll = 0.0           # the tree's y (points) at the top of the tree view, less its top margin
    tree_scroll_x = 0.0         # the tree's x (points) at the left edge of the panel
    tree_follow = True          # bring the current scene into view at the next draw (`scrollToNode:animated:`)
    tree_scale = 1.0            # window pixels per panel point
    tree_sz = None              # `DTNode::sz`, the icon size the player zoomed to; None is the app's 50
    tree_sz_now = DT_DEFAULT_SZ     # the size the tree was last drawn at
    TREE_MARGIN = 48.5          # the first row's top below the view's top (measured from the app's screenshots)
    ZOOM_STEP = 1.15
    ZOOM_RANGE = SZ_RANGE       # `setMinimumZoomScale: 10 / sz`, `setMaximumZoomScale: 60 / sz`
    _layout = None
    _followed = None

    def scroll_tree(self, points, across=0.0):
        self.tree_scroll += points
        self.tree_scroll_x += across
        self.tree_follow = False

    def zoom_tree(self, notches, position):
        """Zoom about a window point (the pointer), keeping the scene under it where it is."""
        if self.tree_rect is None:
            return
        s, (ox, oy) = self.tree_scale or 1.0, self._origin
        old = self.tree_sz_now
        new = min(self.ZOOM_RANGE[1], max(self.ZOOM_RANGE[0], old * self.ZOOM_STEP ** notches))
        if new == old:
            return
        ratio = new / old
        px, py = (position[0] - ox) / s, (position[1] - oy) / s - BAR - self.TREE_MARGIN
        self.tree_scroll = (self.tree_scroll + py) * ratio - py
        self.tree_scroll_x = (self.tree_scroll_x + px) * ratio - px
        self.tree_sz, self.tree_follow = new, False

    def reset_tree_zoom(self):
        self.tree_sz, self.tree_follow = None, True

    def _metrics(self):
        if self._metrics_cache is None:
            self._metrics_cache = PanelMetrics(self)
        return self._metrics_cache

    _metrics_cache = None

    def _layout_for(self, dt, sz):
        key = (id(dt), dt.version, sz, id(dt.current), dt.last_was_result)
        if self._layout is None or self._layout[0] != key:
            self._layout = (key, Layout(dt.root, sz, self._metrics(), dt.current, dt.last_was_result))
        return self._layout[1]

    def _tree(self, panel, dt, s):
        frames = self.node_frames()
        sz = min(SZ_RANGE[1], max(SZ_RANGE[0], self.tree_sz or DT_DEFAULT_SZ))
        self.tree_sz_now = sz
        layout = self._layout_for(dt, sz)
        width, height = PANEL[0] - DIVIDER_WIDTH, PANEL[1] - 2 * BAR
        margin = self.TREE_MARGIN
        current = layout.by_src.get(id(dt.current)) or layout.root
        if self.tree_follow or self._followed != id(dt.current):
            self.tree_scroll_x = current.x - (width / 2 - 0.75 * sz)
            self.tree_scroll = current.y + 0.5 * current.overhead() + margin - height / 2
            self.tree_follow, self._followed = False, id(dt.current)
        root = layout.root
        self.tree_scroll = min(max(0.0, root.ypos + 2 * margin - height), max(0.0, self.tree_scroll))
        self.tree_scroll_x = min(root.xpos - width / 2, max(-root.xneg - width / 2, self.tree_scroll_x))
        cam_x, cam_y = self.tree_scroll_x, self.tree_scroll
        painter = TreePainter(self, panel, s, cam_x, cam_y, frames, sz, (0, BAR, width, height))
        painter.paint(layout.draw_ops())
        # The touch areas of the scenes on show.
        for node in layout.nodes():
            image = node.image_id()
            if image < 0 or image >= len(frames):
                continue
            w, h = frames[image][0].get_size()
            half_w, half_h = w * 0.6 * sz / node.spec.image_scale, h * 0.6 * sz / node.spec.image_scale
            cx, cy = node.x - cam_x, node.y + sz - cam_y + margin + BAR
            if not BAR <= cy <= PANEL[1] - BAR or not -half_w <= cx <= width + half_w:
                continue
            ox, oy = self._origin
            self.tree_targets.append((pygame.Rect(round(ox + (cx - half_w) * s), round(oy + (cy - half_h) * s),
                                                  max(1, round(2 * half_w * s)), max(1, round(2 * half_h * s))),
                                      ('node', node.src)))

    _wall_painted = None        # (key, the painted panel, its link targets): the wall as last painted

    def draw_wall(self, window, session, progress, rect):
        engine = session.engine
        s = rect.height / PANEL[1]
        size = (round(PANEL[0] * s), rect.height)
        origin = (rect.x + round(rect.width * (1 - progress)), rect.y)
        wall = engine.faceplace
        enabled = wall.enabled
        self.wall_rect = pygame.Rect(origin, size)
        self.wall_scale = s
        # The wall is painted again only when something on it changed (its posts, its scroll, its size or place, the
        # scroll indicator's fade): every row repainted each frame cost ~150 ms a frame on a phone.
        indicator = (self.wall_scrolled_at is not None
                     and pygame.time.get_ticks() - self.wall_scrolled_at < self.INDICATOR_SECONDS * 1000)
        key = (size, origin, enabled, self._wall_state(engine, wall) if enabled else None, self.wall_scroll)
        if self._wall_painted is not None and self._wall_painted[0] == key and not indicator:
            window.blit(self._wall_painted[1], origin)
            self.wall_targets = list(self._wall_painted[2])
            return
        panel = pygame.Surface(size).convert()
        self.wall_targets = []
        self.backdrop(panel, 'right', enabled, s, divider=False)
        if enabled:
            self._wall(panel, engine, wall, s, origin)
            width = round((PANEL[0] - DIVIDER_WIDTH) * s)
            panel.blit(self.frame(WALL_HEADER, (width, round(BAR * s))), (round(DIVIDER_WIDTH * s), 0))
            self.divider(panel, 'right', s)
        else:
            self.not_supported(panel, self.string(STR_NO_WALL, 'The faceplace feature is not supported in this episode'),
                               s, bar=True)
            self.divider(panel, 'right', s)
        window.blit(panel, origin)
        # Keyed after painting: _wall settles the scroll (a new post scrolls to the top, the range clamps it). Not kept
        # while the scroll indicator fades: the next paint after it would keep its last faint frame.
        key = key[:4] + (self.wall_scroll,)
        self._wall_painted = None if indicator else (key, panel, list(self.wall_targets))

    # -- the message wall (`SHSFSView`: a scroll view, newest message on top) -----------------------------------------

    wall_targets = ()           # (window rectangle, url) of the posts on show that open a link when tapped
    wall_rect = None            # where the wall panel was drawn (window pixels)
    wall_scale = 1.0            # window pixels per panel point
    wall_scroll = 0.0           # `contentOffset.y` of the message scroll view (points)
    wall_scrolled_at = None     # when the wall last scrolled (the scroll indicator shows for a moment)
    _wall_key = None
    _wall_posts = None
    _wall_arrival = None
    INDICATOR_SECONDS = 0.8

    def scroll_wall(self, points):
        self.wall_scroll += points
        self.wall_scrolled_at = pygame.time.get_ticks()

    @staticmethod
    def _wall_state(engine, wall):
        """What the wall's posts depend on: a change of it lays the rows out (and paints them) again."""
        return (id(wall), len(wall.messages), sum(len(message.continuations) for message in wall.messages),
                id(wall.messages[-1]) if wall.messages else None, id(engine.character_names))

    def _wall_layout(self, engine, wall):
        """(rows, content height): every row laid out once per change of the wall (`measureMessageHeight`); the content is
        the sum of the rows' advances (`measureAllMessagesFull`)."""
        key = self._wall_state(engine, wall)
        if self._wall_key != key:
            self._wall_posts, self._wall_key = self._build_wall(engine, wall), key
        rows = self._wall_posts
        return rows, sum(row.advance for row in rows)

    def _font_metrics(self, font_key):
        """(cap, descent) per point of a wall font: CSFont +0x24 and +0x14 over its size."""
        font = self.text.font(font_key)
        size = getattr(font, 'logical_size', None)
        cap, depth = cap_height(font), descent(font)
        if not size or cap is None or depth is None:
            return ARIAL_CAP, ARIAL_DESCENT
        return cap / size, depth / size

    def _wall_styles(self):
        """{font key: (cap, descent)} in points for the body, emoticon and sender fonts, each scaled to `DEVICE_PITCH`:
        IMG_0299's five rules put the sender font's pitch between 13.2 and 13.4 as well (the desktop stand-in's own
        13.15 and Arial's scale, 13.46, both miss one of them)."""
        emoticons, _ = self.alert.emoticon_font()
        body, name = self.alert.fonts()
        styles = {}
        for key in (body, name):
            cap, depth = self._font_metrics(key)
            styles[key] = (DEVICE_PITCH * cap / (cap + depth), DEVICE_PITCH * depth / (cap + depth))
        styles[emoticons] = styles[body]
        return styles

    def _row_text(self, font_key, styles, text, width, color, indent=0):
        cap, depth = styles[font_key]
        return self.text.layout(font_key, text, width, TextStyle(cap, depth, color, indents=(indent,)))

    def _build_wall(self, engine, wall):
        """The rows top to bottom, newest post first. Each post is a group: its own row, then its continuations, the
        newest directly under the post (`incomingContinuation*` insert below the post's own entry)."""
        body_font, _ = self.alert.emoticon_font()
        _, name_font = self.alert.fonts()
        styles = self._wall_styles()
        space = self.text.font(body_font).glyph(' ').advance
        rows = []
        for message in reversed(wall.messages):
            key = self.alert.key(engine, message)
            face = message.from_id >= 0                 # `isFaceMessage`: from >= 0 (its continuations: an even expression)
            width = MESSAGE_FACE_WIDTH if face else MESSAGE_PLAIN_WIDTH
            url = message.url if message.kind != 'message' else ''
            text = key.text or (message.url if message.kind != 'message' else '')
            indent, name = 0, None
            if key.name:                                # `|Name| text`: the sender font up to the second `|`
                name = self._row_text(name_font, styles, key.name, 2 ** 31, NAME_COLOR)
                indent = round(name.width + space)
            # `getURLOfMessageWithIndex` picks the sender font for a linked message, else the body font.
            font_key = name_font if url else body_font
            layout = self._row_text(font_key, styles, text if url else self.alert.with_emoticons(text), width,
                                    NAME_COLOR if url else (0, 0, 0), indent)
            rows.append(WallRow(key, face, True, False, url, name, layout, font_key, None, 0.0))
            for continuation in reversed(message.continuations):
                caption = (continuation.text or '').split('~', 1)[0]
                link = continuation.url or ''
                font_key = name_font if link else body_font
                # A text continuation is `-1 -12` under a face post and `-1 -11` under one without (`from >> 31 | -12`
                # on the unsigned sender); the script's picture continuation is two messages, the picture (`-1 -14` /
                # `-13`) and then its caption, so the caption sits above the picture.
                rows.append(WallRow(key, face, False, False, link, None,
                                    self._row_text(font_key, styles, caption, width, NAME_COLOR if link else (0, 0, 0)),
                                    font_key, None, 0.0))
                if continuation.kind == 'continuation_image':
                    rows.append(WallRow(key, face, False, False, link, None, None, font_key, self._picture(continuation), 0.0))
        for index, row in enumerate(rows):
            row.last = index + 1 == len(rows) or rows[index + 1].first
            row.height = self._row_height(row, styles)
        group = 0.0
        for row in rows:
            group = row.height if row.first else group + row.height
            if not row.last:
                row.advance = row.height + (ROW_PAD if row.layout is None or row.layout.lines else 0)
            else:                                       # the group's own heights (not its padding) made up to 56
                row.advance = row.height + (max(0.0, FACE_MIN_HEIGHT - group) if row.face else 0)
        return rows

    @staticmethod
    def _row_height(row, styles):
        """`measureMessageHeight`: the text's height and the font's descent below it (or the picture's height + 4), 3
        above a post's own text, 7 under a group's last row."""
        if row.layout is None:
            height = row.picture.get_height() + PICTURE_PAD if row.picture is not None else MISSING_PICTURE
        else:
            height = row.layout.height + (styles[row.font_key][1] if row.layout.lines else 0)
        return height + (TEXT_TOP if row.first else 0) + (LAST_PAD if row.last else 0)

    def _picture(self, message):
        """The image of a continuation that carries one (`GameModel::loadImage`, frame 0), or None."""
        if message.kind != 'continuation_image' or message.image_id < 0:
            return None
        try:
            return self.art.frame_native(message.image_id, 0)
        except (ContentError, UIAssetError, CgBIError, AttributeError, IndexError, ValueError, pygame.error):
            return None

    def _wall(self, panel, engine, wall, s, origin):
        _, inline = self.alert.emoticon_font()
        _, name_font = self.alert.fonts()
        rows, content = self._wall_layout(engine, wall)
        view = PANEL[1] - BAR
        # `incomingMessage` scrolls the view back to the top; a continuation leaves it where it is.
        arrival = (id(wall), sum(1 for m in wall.messages if m.kind == 'message'))
        if self._wall_arrival is not None and self._wall_arrival != arrival:
            self.wall_scroll = 0.0
        self._wall_arrival = arrival
        self.wall_scroll = min(max(0.0, content - view), max(0.0, self.wall_scroll))
        clip = pygame.Rect(0, round(BAR * s), panel.get_width(), panel.get_height() - round(BAR * s))
        panel.set_clip(clip)
        try:
            # `scrollViewDidScroll:` puts each row's view at the running sum of the advances, truncated.
            offset = 0.0
            for row in rows:
                y = BAR + int(offset) - self.wall_scroll
                if y >= PANEL[1]:
                    break
                if y + self._row_view_height(row) > BAR:
                    self._paint_row(panel, clip, row, y, s, origin, name_font, inline)
                offset += row.advance
            if content > view and self.wall_scrolled_at is not None:
                shown = (pygame.time.get_ticks() - self.wall_scrolled_at) / 1000
                if 0 <= shown < self.INDICATOR_SECONDS:
                    self._indicator(panel, s, content, view, 1 - shown / self.INDICATOR_SECONDS)
        finally:
            panel.set_clip(None)

    def _indicator(self, panel, s, content, view, fade):
        """UIKit's vertical scroll indicator (`setShowsVerticalScrollIndicator:YES`): a thin rounded bar at the right edge."""
        length = max(30.0, view * view / content)
        top = BAR + 2 + (view - 4 - length) * (self.wall_scroll / (content - view))
        bar = pygame.Surface((max(2, round(3 * s)), max(1, round(length * s))), pygame.SRCALPHA)
        pygame.draw.rect(bar, (0, 0, 0, round(140 * fade)), bar.get_rect(), border_radius=bar.get_width() // 2)
        panel.blit(bar, (panel.get_width() - bar.get_width() - round(2 * s), round(top * s)))

    @staticmethod
    def _row_view_height(row):
        """`makeMessageView`: the row's view is its advance + 2 tall (a face post's at least 56 + 2); `drawRect:` cannot
        draw outside it."""
        return max(row.advance, FACE_MIN_HEIGHT if row.face and row.first else 0) + 2

    def _paint_row(self, panel, clip, row, y, s, origin, name_font, inline):
        """`drawMessage` for one row whose view's top is at panel point `y`."""
        band = pygame.Rect(0, round(y * s), panel.get_width(), round(self._row_view_height(row) * s)).clip(clip)
        if not band.width or not band.height:
            return
        panel.set_clip(band)
        try:
            top = y + (TEXT_TOP if row.first else 0)
            if row.layout is not None:
                if row.name is not None:
                    self._draw_text(panel, name_font, row.name, row.x, top, s)
                self._draw_text(panel, row.font_key, row.layout, row.x, top, s,
                                inline=None if row.font_key == name_font else inline)
            else:
                self._picture_row(panel, row, top, s)
            if row.url:                                         # `getURLOfMessageWithIndex`: the row is a link
                self._link(row.url, row.x, y, row.height, s, origin)
            if row.first and row.face and row.key.portrait is not None:
                group, (gx, gy) = self.art.portrait_group(row.key.portrait)
                factor = 0.2 * 2 / self.art.scale * s
                size = max(1, round(group.get_width() * factor)), max(1, round(group.get_height() * factor))
                panel.blit(self.alert.shrink(group, size), (round(MESSAGE_FACE_CENTER[0] * s + gx * factor),
                                                            round((y + MESSAGE_FACE_CENTER[1]) * s + gy * factor)))
            if row.last:                                        # `fillRect(11, y + advance - 4 + 2, width - 2, 1)`, 0xe0e0e0
                line = y + int(row.advance - RULE_RISE)
                panel.fill(RULE, pygame.Rect(round(RULE_X * s), round(line * s), round((PANEL[0] - 2) * s),
                                             max(1, round(s))).clip(band))
        finally:
            panel.set_clip(clip)

    def _draw_text(self, panel, font_key, layout, x, top, s, inline=None):
        """CSFont's lines from a region's top: the first baseline is one cap height down."""
        font = self.text.font(font_key)
        self.text.draw_layout(panel, font_key, layout, x * s, (top + font.line_height - font.base) * s, scale=s, inline=inline)

    @staticmethod
    def _picture_row(panel, row, top, s):
        """`drawMessage` with an image: the picture 2 points in, and a 0.75 point frame (the link's blue when the message
        has a link, else black) around the picture and that margin, its rectangle truncated to 0.75-point steps."""
        if row.picture is None:
            return
        image, w, h = row.picture, row.picture.get_width(), row.picture.get_height()
        size = max(1, round(w * s)), max(1, round(h * s))
        panel.blit(pygame.transform.smoothscale(image, size) if s != 1 else image,
                   (round(int(row.x + 2) * s), round(int(top + 2) * s)))
        x0, y0, fw, fh = (int(v * .75) / .75 for v in (row.x, top, w + 4, h + 4))
        # CGContextStrokeRect centres the 0.75 line on the rectangle's edge.
        pygame.draw.rect(panel, NAME_COLOR if row.url else (0, 0, 0),
                         pygame.Rect(round((x0 - .375) * s), round((y0 - .375) * s), round((fw + .75) * s), round((fh + .75) * s)),
                         max(1, round(0.75 * s)))

    def _link(self, url, x, top, height, s, origin):
        """The touch area of a linked message (`SHSFSMessageContentView touchIsIn:y:`: from the text's left edge to the
        panel's right, over the message's height), clipped to the scroll view."""
        band, bottom = max(BAR, top), min(PANEL[1], top + height)
        if bottom <= band:
            return
        self.wall_targets.append((pygame.Rect(round(origin[0] + (x - 3) * s), round(origin[1] + band * s),
                                              round((PANEL[0] - x + 3) * s), max(1, round((bottom - band) * s))), url))

    def draw(self, window, session, progress, left, right):
        try:
            self.draw_tree(window, session, progress, left)
            self.draw_wall(window, session, progress, right)
        except (ContentError, pygame.error, ValueError, OSError) as error:
            logging.error('Side panel rendering stopped: %s', error)
            raise
