"""Side-panel rendering for DTView (the decision-tree/progression timeline)
and Faceplace (the message wall) -- see dtview_faceplace.py for the
underlying data model and docs/ENGINE_ABI.md sections 6.1/6.2 for the
recovered native semantics.

Real, decompiled facts this follows:
- DTView's own bounds are a fixed 768x224 in portrait, Faceplace's a fixed
  224x768, both sliding on/off screen from a native offsetOffScreen
  convention (see legacy/findings.md, "DTView/Faceplace layout finally
  understood"). In the real app this is toggled by a portrait<->landscape
  device rotation; this desktop app has no such gesture, so the user chose
  to bind it to the Tab key instead (see Desktop.handle_event).
- Confirmed against both a user-supplied reference screenshot and a real
  device's own landscape app-switcher snapshot (see legacy/findings.md):
  in landscape, both panels render as vertical strips flanking a *narrower*
  center game view -- the window's own aspect ratio goes from 3:4 to 4:3,
  with the center content keeping its original 3:4 shape and pixel size
  rather than shrinking to make room. `Desktop._present()` mirrors this by
  actually resizing the OS window when panels toggle (snapping instantly,
  like a real device rotation) and drawing each panel directly into the
  newly-revealed window-space margin -- not overlaid on top of the game
  canvas, and not funneled through that canvas's fixed 480x720 budget, so
  panel text renders at real window resolution instead of picking up the
  same blur that budget causes elsewhere (see legacy/findings.md's
  bitmap-font-blur investigation).
- DTView's real layout is a recursive Reingold-Tilford-style algorithm
  (parent centered over an average of up to 5 children, tracked via
  running min/max/avg accumulators across the whole tree) with per-node-
  type scale constants, confirmed via raw disassembly of -[SHSDTView
  layoutNodeInSubview:withParent:] and DTNode's shared drawing vtable
  methods (offsets 0x74/0x7c/0x84 -- identical function pointers across
  all 23 real node-type subclasses, confirmed by reading every one of
  their vtables directly, so there is exactly one drawing algorithm to
  match, not 23). The exact recursive accumulator math and CSGraphics
  vector drawing (rounded-rect geometry, stroke widths) were not fully
  reconstructed -- real, but past a point of sharply diminishing returns
  for this pass (see legacy/findings.md). This module lays out the same
  real tree shape (parent above its children, connector lines, real label
  and exit-label text) with a simpler direct positioning algorithm instead
  of replicating the native accumulator-based one node-for-node.
- The real tree persists *across* playthroughs (confirmed from a real
  device's own tree_<serial>.sav debug dump; see `dtview_faceplace.DTView`
  and `Session.dt_view_path`/`_save_dt_view`) -- revisiting the same
  branch reuses the existing child instead of overwriting it, so a fresh
  playthrough starts back at the root but with every previously-explored
  branch still present in the tree. A node shows full color if it's on the
  current node's *lineage* -- an ancestor (already walked this
  playthrough) or a descendant (an already-recorded continuation lying
  ahead of it, even before this playthrough has actually reached that far)
  -- and desaturated otherwise, i.e. only on a *sibling* branch that
  diverges somewhere behind the current node. Confirmed against real
  device screenshots: ancestors-only was tried first and was wrong -- a
  continuation nothing has diverged from yet reads as "still my future,"
  not as an unrelated branch.
- Faceplace message formatting (author-name prefix, $USR-style
  replacement) is confirmed via -[SHSFSView drawMessage:...]; this
  engine's FaceplaceMessage already carries that content as clean fields
  rather than the native encoded key string, so no replication was needed
  there.

Neither panel's exact colors/fonts are recovered native constants -- both
are styled to look at home next to the rest of this desktop app's own
host-UI chrome (matching Desktop._draw_menu's approach), not matched pixel
for pixel to native art that was never decompiled here.
"""
import pygame


NODE_HEIGHT = 52
NODE_SPACING = 10
BG = (30, 34, 48, 235)
BOX = (52, 62, 90)
BOX_CURRENT = (48, 110, 78)
BOX_INACTIVE = (40, 44, 56)
BORDER = (110, 150, 200)
BORDER_INACTIVE = (70, 76, 92)
TEXT = (230, 235, 245)
TEXT_INACTIVE = (130, 136, 150)
TAG = (255, 210, 120)
NAME_COLOR = (120, 165, 235)

# Real per-node-type icon indices, recovered by raw-disassembling each of
# the 23 real DTNode_* C++ subclasses' own get_image_id() getters (each a
# one-line `return CONSTANT;` function) -- see legacy/findings.md, "Real
# per-node-type icon IDs recovered". -1 covers the pure branch/join
# connector types, which a real completed-save screenshot showed getting a
# distinct triangular connector glyph rather than a story-content icon.
NODE_TYPE_IMAGE_ID = {
    1202: 2, 1203: 2,          # Terminal, Event_Generic
    1204: 3,                   # Event_Buff_Club
    1205: 4,                   # Event_Homecoming
    1206: 5,                   # Event_Meet
    1207: 6,                   # Event_Talk
    1208: 1, 1209: 1,          # Date_Event, Date
    1210: 8, 1211: 8,          # Game_Menu2, Game_Menu3
    1212: 9, 1213: 9,          # Game_Word2, Game_Word3
    1214: 7,                   # FootballGame
    1215: 0, 1216: 0,          # Choice, Choice3
    1217: 10, 1218: 10,        # Quiz, Final
    1219: 0, 1220: 0,          # ChoiceBranch, ChoiceBranch3
    1221: -1, 1222: -1, 1223: -1, 1224: -1,  # AutoBranch2/3/4, Join
}

ICON_SIZE = 20
ICON_COLORS = {
    -1: (100, 84, 140),   # branch/join connector -- triangle
    0: (66, 100, 156),    # choice -- diamond, paired dots (real screenshot)
    1: (196, 74, 96),     # date -- heart (real screenshot)
    2: (100, 106, 120),   # terminal/generic -- plain circle
    3: (74, 122, 100),    # buff/club -- circle, grouped dots
    4: (168, 132, 62),    # homecoming -- oval, star
    5: (72, 118, 162),    # meet -- circle, paired faces
    6: (80, 140, 118),    # talk -- square, paired faces (real screenshot)
    7: (120, 78, 40),     # football -- brown oval with laces (real screenshot)
    8: (58, 140, 148),    # game menu -- square, swirl (real screenshot)
    9: (86, 148, 96),     # game word -- square, letter mark
    10: (66, 100, 156),   # quiz/final -- diamond, "?" (real screenshot)
}


def _wrap(text, font, width):
    lines = []
    for paragraph in text.split('\n'):
        line = ''
        for word in paragraph.split():
            proposed = f'{line} {word}' if line else word
            if line and font.size(proposed)[0] > width:
                lines.append(line)
                line = word
            else:
                line = proposed
        lines.append(line)
    return lines or ['']


def _draw_node_icon(panel, glyph_font, image_id, box, dim):
    """A small badge at the box's left edge standing in for the real
    per-node-type icon art. The *shapes* below (diamond/heart/oval/square/
    triangle) and which image_id gets which one are read directly off a
    real completed-save screenshot (see NODE_TYPE_IMAGE_ID's docstring);
    the exact glyph pixels inside each shape are this renderer's own
    design, not recovered art -- finding the real sprite resource ids was
    out of scope (see legacy/findings.md's "Next up"). `dim` mutes the
    badge to the same desaturated palette an inactive/ghost box already
    uses, keeping the on-path/off-path read consistent.
    """
    cx, cy = box.x + 10 + ICON_SIZE // 2, box.y + box.height // 2
    r = ICON_SIZE // 2
    outline = BORDER_INACTIVE if dim else BORDER
    fill = None if dim else ICON_COLORS.get(image_id, ICON_COLORS[2])
    glyph = TEXT_INACTIVE if dim else TEXT

    if image_id == -1:
        points = [(cx, cy - r), (cx - r, cy + r), (cx + r, cy + r)]
        if fill:
            pygame.draw.polygon(panel, fill, points)
        pygame.draw.polygon(panel, outline, points, 1)
    elif image_id in (0, 10):
        points = [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)]
        if fill:
            pygame.draw.polygon(panel, fill, points)
        pygame.draw.polygon(panel, outline, points, 1)
        if image_id == 10:
            mark = glyph_font.render('?', True, glyph)
            panel.blit(mark, mark.get_rect(center=(cx, cy + 1)))
        elif fill:
            pygame.draw.circle(panel, glyph, (cx - 3, cy + 1), 2)
            pygame.draw.circle(panel, glyph, (cx + 3, cy + 1), 2)
    elif image_id == 1:
        pygame.draw.circle(panel, fill or outline, (cx - 4, cy - 2), 5, 0 if fill else 1)
        pygame.draw.circle(panel, fill or outline, (cx + 4, cy - 2), 5, 0 if fill else 1)
        if fill:
            pygame.draw.polygon(panel, fill, [(cx - 8, cy - 1), (cx + 8, cy - 1), (cx, cy + 8)])
    elif image_id == 7:
        oval = pygame.Rect(0, 0, ICON_SIZE, ICON_SIZE - 6)
        oval.center = (cx, cy)
        if fill:
            pygame.draw.ellipse(panel, fill, oval)
        pygame.draw.ellipse(panel, outline, oval, 1)
        if fill:
            pygame.draw.line(panel, glyph, oval.midleft, oval.midright, 1)
            for dx in (-4, 0, 4):
                pygame.draw.line(panel, glyph, (cx + dx, cy - 2), (cx + dx, cy + 2), 1)
    else:
        square = pygame.Rect(0, 0, ICON_SIZE - 2, ICON_SIZE - 2)
        square.center = (cx, cy)
        if fill:
            pygame.draw.rect(panel, fill, square, border_radius=4)
        pygame.draw.rect(panel, outline, square, 1, border_radius=4)
        if fill and image_id in (3, 5, 6):
            pygame.draw.circle(panel, glyph, (cx - 3, cy), 2)
            pygame.draw.circle(panel, glyph, (cx + 3, cy), 2)
        elif fill and image_id == 4:
            mark = glyph_font.render('*', True, glyph)
            panel.blit(mark, mark.get_rect(center=(cx, cy)))
        elif fill and image_id in (8, 9):
            mark = glyph_font.render('~' if image_id == 8 else 'W', True, glyph)
            panel.blit(mark, mark.get_rect(center=(cx, cy)))


class _GhostChild:
    """A result slot the player has seen offered (its button text is known
    from `DTNode.choice_labels`, see dtview_faceplace.py) but never actually
    taken on any playthrough -- real device trees show these too ("see all
    the choices map out"), not just previously-taken branches. Carries only
    a label; nothing is known past it since it was never explored, so it
    never has children or a lineage of its own."""
    children = {}
    exit_label = ''

    def __init__(self, label):
        self.lower_label = label


def _child_slots(node):
    """Real children merged with ghost placeholders for offered-but-untaken
    slots, keyed by the same result-slot index both use."""
    if isinstance(node, _GhostChild):
        return {}
    slots = dict(node.children)
    for slot, label in node.choice_labels.items():
        if slot not in slots and label:
            slots[slot] = _GhostChild(label)
    for slot, label in node.result_labels.items():          # taken, but nothing has followed it yet
        if slot not in slots:
            slots[slot] = _GhostChild(label)
    return slots


def _flatten_positions(root):
    """Depth = row (top-to-bottom story progression); siblings spread
    horizontally within a row, matching the real tree shape without the
    native accumulator-based layout math (see module docstring). Also
    returns each node's ordered child list (real + ghost) so the caller
    doesn't need to recompute _child_slots with fresh, non-matching ghost
    object identities."""
    boxes = []
    child_map = {}

    def walk(node, depth, order):
        boxes.append((node, depth, order))
        ordered = [child for _, child in sorted(_child_slots(node).items())]
        child_map[id(node)] = ordered
        for index, child in enumerate(ordered):
            walk(child, depth + 1, index)

    walk(root, 0, 0)
    return boxes, child_map


def _active_path(root, current):
    """Node ids "on lineage" with the current node: its ancestors (root
    down to current -- what this playthrough already walked) *and* its
    descendants (whatever already-recorded continuation lies ahead of it).
    Confirmed against real device screenshots this is the right rule, not
    ancestors alone: nodes further along the *same*, already-explored
    continuation as the current one show in full color even before this
    playthrough has actually reached them, while a *sibling* branch that
    diverges at some point behind current (a different choice made on an
    earlier playthrough) shows desaturated. DTNode keeps no parent
    back-reference (see dtview_faceplace.py -- a parent<->children cycle
    broke the save format once already), so ancestors are found by
    searching down from the root instead of up from `current`.
    """
    if root is None:
        return set()
    if current is None:
        return _subtree_ids(root)  # Nothing has diverged yet: nothing to gray out.

    def find(node, path):
        if node is current:
            return path
        for child in node.children.values():
            found = find(child, path + [id(child)])
            if found is not None:
                return found
        return None

    ancestors = find(root, [id(root)])
    if ancestors is None:
        return set()
    return set(ancestors) | _subtree_ids(current)


def _subtree_ids(node):
    ids = {id(node)}
    for child in node.children.values():
        ids |= _subtree_ids(child)
    return ids


class DTViewRenderer:
    def __init__(self, resources, text_renderer, image_loader):
        self.resources = resources
        self.image = image_loader
        self.font = pygame.font.Font(None, 18)
        self.icon_font = pygame.font.Font(None, 15)

    def draw(self, window, session, progress, rect):
        """rect is the window-space margin this panel may use; nothing is
        drawn once progress<=0 or the margin has no width to slide into."""
        dt = session.engine.dt_view
        if dt.root is None or progress <= 0 or rect.width <= 0:
            return
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel.fill(BG)
        positions, child_map = _flatten_positions(dt.root)
        active_path = _active_path(dt.root, dt.current)
        y = 16
        node_rects = {}
        for node, depth, order in positions:
            indent = 12 + order * 20
            width = rect.width - indent - 12
            box = pygame.Rect(indent, y, max(80, width), NODE_HEIGHT)
            node_rects[id(node)] = box
            y = box.bottom + NODE_SPACING
        for node, depth, order in positions:
            box = node_rects[id(node)]
            for child in child_map[id(node)]:
                child_box = node_rects.get(id(child))
                if child_box is not None:
                    on_path = id(child) in active_path
                    pygame.draw.line(panel, BORDER if on_path else BORDER_INACTIVE,
                                     box.midbottom, child_box.midtop, 2)
        for node, depth, order in positions:
            box = node_rects[id(node)]
            is_ghost = isinstance(node, _GhostChild)
            is_current = node is dt.current
            on_path = id(node) in active_path
            color, border, text_color = ((BOX_CURRENT, BORDER, TEXT) if is_current
                                         else (BOX, BORDER, TEXT) if on_path
                                         else (BOX_INACTIVE, BORDER_INACTIVE, TEXT_INACTIVE))
            if is_ghost:
                # Offered but never taken on any playthrough -- outline only,
                # no fill, so it reads as "known but unexplored" rather than
                # "explored on some other path" (see _GhostChild docstring).
                pygame.draw.rect(panel, border, box, 1, border_radius=8)
            else:
                pygame.draw.rect(panel, color, box, border_radius=8)
                pygame.draw.rect(panel, border, box, 2, border_radius=8)
            # Ghosts have no icon: their node_type is never known since they
            # were never actually visited (see _GhostChild docstring).
            text_x = box.x + 6
            if not is_ghost:
                image_id = NODE_TYPE_IMAGE_ID.get(node.node_type, 2)
                _draw_node_icon(panel, self.icon_font, image_id, box, dim=not (is_current or on_path))
                text_x = box.x + 10 + ICON_SIZE + 6
            label = node.lower_label or f'Node {node.node_type}'
            for index, line in enumerate(_wrap(label, self.font, box.right - 6 - text_x)[:2]):
                panel.blit(self.font.render(line, True, text_color), (text_x, box.y + 5 + index * 17))
            if node.exit_label:
                tag = self.font.render(node.exit_label, True, TAG if on_path else TEXT_INACTIVE)
                panel.blit(tag, (box.right - tag.get_width() - 6, box.bottom - 19))
        offset = round(rect.width * progress) - rect.width
        window.blit(panel, (rect.x + offset, rect.y))


class FaceplacePanelRenderer:
    MAX_SHOWN = 20
    PORTRAIT_SIZE = 32

    def __init__(self, resources, text_renderer, image_loader, dialogue_renderer):
        self.resources = resources
        self.image = image_loader
        self.dialogue_renderer = dialogue_renderer
        self.font = pygame.font.Font(None, 18)
        self.heading = pygame.font.Font(None, 20)

    def _portrait(self, engine, character_id, expression):
        variants = engine.character_art_variants.get(character_id)
        if not variants:
            return None
        image = self.dialogue_renderer.portrait(variants[max(0, expression) % len(variants)], False)
        if image is None:
            return None
        size = self.PORTRAIT_SIZE
        scale = min(size / image.get_width(), size / image.get_height())
        return pygame.transform.smoothscale(image, (round(image.get_width() * scale), round(image.get_height() * scale)))

    def draw(self, window, session, progress, rect):
        engine = session.engine
        wall = engine.faceplace
        if not wall.messages or progress <= 0 or rect.width <= 0:
            return
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel.fill(BG)
        panel.blit(self.heading.render('faceplace', True, TEXT), (12, 10))
        y = 40
        for message in reversed(wall.messages[-self.MAX_SHOWN:]):
            if y > rect.height:
                break
            name = engine.character_names.get(message.from_id, '') if message.from_id >= 0 else ''
            portrait = self._portrait(engine, message.from_id, message.expression) if name else None
            text_x = 6 + (self.PORTRAIT_SIZE + 6 if portrait is not None else 0)
            text_width = rect.width - 24 - (text_x - 6)
            body = message.text or (f'[image] {message.url}' if message.image_id >= 0 else message.url)
            combined = f'{name} {body}'.strip() if name else body
            lines = _wrap(combined, self.font, max(20, text_width))[:5]
            box_h = 10 + max(len(lines) * 17, self.PORTRAIT_SIZE if portrait is not None else 0)
            box = pygame.Rect(12, y, rect.width - 24, box_h)
            pygame.draw.rect(panel, BOX, box, border_radius=6)
            pygame.draw.rect(panel, BORDER, box, 1, border_radius=6)
            if portrait is not None:
                panel.blit(portrait, (box.x + 6, box.y + 5))
            for index, line in enumerate(lines):
                if index == 0 and name and line.startswith(name):
                    name_surface = self.font.render(name, True, NAME_COLOR)
                    panel.blit(name_surface, (box.x + text_x, box.y + 5))
                    rest = line[len(name):]
                    if rest:
                        panel.blit(self.font.render(rest, True, TEXT),
                                   (box.x + text_x + name_surface.get_width(), box.y + 5))
                else:
                    panel.blit(self.font.render(line, True, TEXT), (box.x + text_x, box.y + 5 + index * 17))
            y = box.bottom + 10
        offset = rect.width - round(rect.width * progress)
        window.blit(panel, (rect.x + offset, rect.y))
