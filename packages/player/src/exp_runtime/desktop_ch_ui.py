"""shshd-runtime: Claire Hart Dialogue's pieces for Cause of Death's other screens (CLAIRE_HART_SKIN_PLAN.md; owner,
2026-11-21): Classic's own panel (its title on its cream tab), dark rows with the gold-edged highlight, the Play Now pill,
the teal capsule, its combo bar as a timer, and its Yes/No popup, in Romic Bold. The art is chc's from revision 2 (29109 on;
tools/translate/ch_dialogue_skin.py), and the spec's `ui` says where each piece is cut; a library with chc revision 1 has no
`ui`, so `ChUi.of` gives None and the screens keep CoD's own look.

Pieces are drawn at an art scale `s` (canvas pixels a piece's own pixel): their caps keep that scale, their middles stretch.
Everything made is kept by its size (a screen draws the same panel every frame)."""
from io import BytesIO

from . import graphics as pygame

ADDON = 'chc'


class ChUi:
    TAB_CLEAR = 40                          # the panel tab's slanted ends: art pixels from each end a title keeps clear of

    def __init__(self, library, spec):
        self.library, self.spec, self.ui = library, spec, spec['ui']
        self.addon = spec.get('addon', ADDON)          # (the skin's own add-on: chc's, or the sequel's ch2)
        self._pictures, self._made, self._fonts = {}, {}, {}
        colours = self.ui.get('colours', {})
        self.TITLE = tuple(colours.get('title', (125, 66, 14)))
        self.TEXT = tuple(colours.get('text', (239, 235, 226)))
        self.GOLD = tuple(colours.get('gold', (255, 205, 78)))
        self.LIT = tuple(colours.get('lit', (238, 226, 90)))
        self.TEAL = tuple(colours.get('teal', (18, 224, 188)))
        self.WRONG = tuple(colours.get('wrong', (240, 80, 70)))

    @classmethod
    def of(cls, resources):
        """The skin's pieces for this episode's screens, or None: the switch off for it, or chc without them (revision 1).
        Resources with no episode (the main menu's: a bare `library`) take the menus' skin (Claire Hart UI's Everywhere:
        ContentLibrary.menu_skin)."""
        episode = getattr(resources, 'dialogue_skin', None)
        # (the main menu's art holds the library itself as its resources)
        library = resources if episode is None and hasattr(resources, 'menu_skin') else getattr(resources, 'library', None)
        try:
            spec = episode() if episode is not None else library.menu_skin()
        except Exception:                                   # (a stand-in without either, a damaged spec)
            return None
        if not spec or 'ui' not in spec:
            return None
        key = id(spec)
        cache = library.__dict__.setdefault('_ch_ui', {}) if library is not None and hasattr(library, '__dict__') else {}
        found = cache.get(key)
        if found is None:
            found = cache[key] = cls(library, spec)
        return found

    # -- art -------------------------------------------------------------------------------------------------------------
    def picture(self, resource):
        found = self._pictures.get(resource)
        if found is None:
            data = self.library.addon_resource(self.addon, resource)
            if data is None:
                raise ValueError(f'{self.addon} is missing resource {resource}: import its latest build')
            found = self._pictures[resource] = pygame.image.load(BytesIO(data), 'piece.png').convert_alpha()
        return found

    def font(self, px):
        """Romic Bold at `px` pixels (regular Romic lacks "&", "/" and more: the dialogue skin's choice)."""
        px = max(6, round(px))
        found = self._fonts.get(px)
        if found is None:
            found = self._fonts[px] = pygame.font.Font(
                BytesIO(self.library.addon_resource(self.addon, self.spec['fonts'].get('ui', self.spec['fonts']['bold']))), px)
        return found

    def _sliced(self, picture, size, cols, rows, s):
        """`picture` cut at `cols` / `rows` ((start, end, mode) in its pixels; mode 'fix' keeps scale `s`, 'grow' shares
        what's left, a number is that many pixels) and laid out at `size`."""
        width, height = (max(1, round(v)) for v in size)

        def spans(parts, total):
            def fixed(a, b, mode):
                return (b - a) * s if mode == 'fix' else mode if isinstance(mode, (int, float)) else None
            taken = sum(fixed(*p) for p in parts if fixed(*p) is not None)
            grow = sum(b - a for a, b, mode in parts if mode == 'grow') or 1
            out, at = [], 0.
            for a, b, mode in parts:
                length = fixed(a, b, mode)
                if length is None:
                    length = (b - a) / grow * max(0., total - taken)
                out.append((a, b, round(at), round(at + length)))
                at += length
            return out
        surface = pygame.Surface((width, height), pygame.SRCALPHA).convert_alpha()
        surface.fill((0, 0, 0, 0))
        for sy0, sy1, dy0, dy1 in spans(rows, height):
            row_cols = cols(sy0) if callable(cols) else cols
            for sx0, sx1, dx0, dx1 in spans(row_cols, width):
                if dx1 > dx0 and dy1 > dy0 and sx1 > sx0 and sy1 > sy0:
                    piece = picture.subsurface(pygame.Rect(sx0, sy0, sx1 - sx0, sy1 - sy0))
                    surface.blit(pygame.transform.smoothscale(piece, (dx1 - dx0, dy1 - dy0)), (dx0, dy0))
        return surface

    def _nine(self, name, size, s, resource=None, slice_=None):
        entry = self.ui[name]
        resource = resource or entry['picture']
        left, top, right, bottom = slice_ or entry['slice']
        picture = self.picture(resource)
        w, h = picture.get_size()
        key = (name, resource, round(size[0]), round(size[1]), round(s, 3))
        found = self._made.get(key)
        if found is None:
            cols = [(0, left, 'fix'), (left, w - right, 'grow'), (w - right, w, 'fix')]
            rows = ([(0, top, 'fix'), (top, h - bottom, 'grow'), (h - bottom, h, 'fix')] if top or bottom
                    else [(0, h, 'grow')])
            found = self._made[key] = self._sliced(picture, size, cols, rows, s)
        return found

    # -- the pieces ----------------------------------------------------------------------------------------------------
    def header_height(self, s):
        """The panel's header band (the dark top with the tab) at art scale `s`, canvas pixels."""
        return self.ui['panel']['rows'][0] * s

    def footer_height(self, s):
        p = self.ui['panel']
        return (p['size'][1] - p['rows'][1]) * s

    def tab_bounds(self, width, s, title_width=0, tab_centre=None):
        """(middle, before): the tab's middle's length and the header's run before the tab, pixels, for a panel `width`
        across with the tab centred on `tab_centre` (pixels from its left; None: the middle), kept off the caps."""
        p = self.ui['panel']
        w = p['size'][0]
        left, right = p['caps']
        t0, t1, t2, t3 = p['tab']
        # The tab's ends are slanted: a title may run into each but for its outer TAB_CLEAR pixels.
        middle = max((t2 - t1) * s, title_width - ((t1 - t0) + (t3 - t2) - 2 * self.TAB_CLEAR) * s)
        tab = (t1 - t0 + t3 - t2) * s + middle
        room = max(0., width - (left + right) * s - tab)
        if tab_centre is None:
            return middle, room * (t0 - left) / max(1, (t0 - left) + (w - right - t3))
        return middle, max(0., min(room, tab_centre - left * s - tab / 2))

    TAB_MARGIN = 16                         # art pixels the widest tab keeps from each of the header's caps

    def title_room(self, width, s):
        """The widest title, pixels, whose tab still fits a panel `width` across: TAB_MARGIN short of each cap (a wider
        one ran the tab over the frame's right edge, owner 2026-11-22: the legal page's long title)."""
        p = self.ui['panel']
        left, right = p['caps']
        t0, t1, t2, t3 = p['tab']
        middle = width - (left + right + 2 * self.TAB_MARGIN) * s - (t1 - t0 + t3 - t2) * s
        return max(0., middle + ((t1 - t0) + (t3 - t2) - 2 * self.TAB_CLEAR) * s)

    def panel(self, size, s, title_width=0, tab_centre=None):
        """Classic's panel at `size`: its header (with the cream tab) and footer kept at scale `s`, its teal middle
        stretched; the tab's middle wide enough for a title `title_width` pixels across, the tab centred on `tab_centre`
        (pixels from the left; None: the middle, as Classic's)."""
        p = self.ui['panel']
        w, h = p['size']
        left, right = p['caps']
        top, bottom = p['rows']
        t0, t1, t2, t3 = p['tab']
        middle, before = self.tab_bounds(size[0], s, title_width, tab_centre)
        after = max(0., size[0] - (left + right) * s - (t1 - t0 + t3 - t2) * s - middle - before)
        key = ('panel', round(size[0]), round(size[1]), round(s, 3), round(middle), round(before))
        found = self._made.get(key)
        if found is None:
            def cols(row_top):
                if row_top == 0:
                    return [(0, left, 'fix'), (left, t0, before), (t0, t1, 'fix'), (t1, t2, middle), (t2, t3, 'fix'),
                            (t3, w - right, after), (w - right, w, 'fix')]
                return [(0, left, 'fix'), (left, w - right, 'grow'), (w - right, w, 'fix')]
            found = self._made[key] = self._sliced(self.picture(p['picture']), size, cols,
                                                   [(0, top, 'fix'), (top, bottom, 'grow'), (bottom, h, 'fix')], s)
        return found

    def title_centre(self, s):
        """The tab's title band's middle, pixels below the panel's top."""
        a, b = self.ui['panel'].get('title', (6, 74))
        return (a + b) / 2 * s

    def draw_panel(self, target, rect, s, title, title_px, *, alpha=255, tab_centre=None):
        """The panel at `rect` with `title` on its tab in Romic Bold, Classic's brown; the tab centred on `tab_centre`
        (pixels from the panel's left, beside a portrait) or the panel's middle. A title too wide for the tab to fit
        is set smaller until it does."""
        room = self.title_room(rect.width, s)
        while title and title_px > 8 and self.font(title_px).size(title)[0] > room:
            title_px -= 1
        font = self.font(title_px)
        words = font.render(title, True, self.TITLE) if title else None
        width = words.get_width() if words else 0
        piece = self.panel(rect.size, s, width, tab_centre)
        if alpha < 255:
            piece = piece.copy()
            piece.set_alpha(alpha)
        target.blit(piece, rect.topleft)
        if words is not None:
            if alpha < 255:
                words.set_alpha(alpha)
            p = self.ui['panel']
            t0, t1, t2, t3 = p['tab']
            middle, before = self.tab_bounds(rect.width, s, width, tab_centre)
            centre = rect.x + (p['caps'][0] + (t1 - t0)) * s + before + middle / 2
            target.blit(words, words.get_rect(center=(round(centre), round(rect.y + self.title_centre(s)))))

    def row(self, size, s, lit=False):
        """A dark option row; `lit` the gold-edged highlight over it (the picked or focused row)."""
        base = self._nine('row', size, s)
        if not lit:
            return base
        key = ('row lit', round(size[0]), round(size[1]), round(s, 3))
        found = self._made.get(key)
        if found is None:
            found = base.copy()
            found.blit(self._nine('row_lit', size, s), (0, 0))
            self._made[key] = found
        return found

    def capsule(self, size, s):
        return self._nine('capsule', size, s)

    def pill(self, size, s, state='idle'):
        """The Play Now pill (chc's Continue: idle and pressed; the hover one lit) at `size`, its caps at scale `s`."""
        resource = {'pressed': self.spec['pill'][1], 'lit': self.ui.get('pill_lit', self.spec['pill'][0])}.get(
            state, self.spec['pill'][0])
        key = ('pill', resource, round(size[0]), round(size[1]), round(s, 3))
        found = self._made.get(key)
        if found is None:
            picture = self.picture(resource)
            w, h = picture.get_size()
            found = self._made[key] = self._sliced(picture, size, [(0, 28, 'fix'), (28, w - 28, 'grow'), (w - 28, w, 'fix')],
                                                   [(0, h, 'grow')], s)
        return found

    def timer(self, size, s, fraction):
        """Classic's combo bar running down: its dark backing, the gold fill cut to `fraction` (1 full, 0 empty)."""
        t = self.ui['timer']
        left, _, right, _ = t['slice']
        back = self._nine('timer', size, s, resource=t['back'], slice_=(left, 0, right, 0))
        fill = self._nine('timer', size, s, resource=t['fill'], slice_=(left, 0, right, 0))
        surface = back.copy()
        shown = max(0, min(fill.get_width(), round(fill.get_width() * fraction)))
        if shown:
            surface.blit(fill, (0, 0), pygame.Rect(0, 0, shown, fill.get_height()))
        return surface

    # Classic's Yes/No popup as a window, in a layer's frame points (HD's 768-point frame): its width, the title / body /
    # button sizes, a button pill and the gap between two buttons' centres.
    POPUP_W, POPUP_TITLE, POPUP_BODY, POPUP_LABEL, POPUP_PILL, POPUP_GAP = 640, 40, 25, 27, (230, 64), 260

    def window(self, layer, unit, frame_width, title, message, labels, *, pressed=None, spinner=None, dense=False):
        """Classic's popup centred on `layer` (`unit` pixels a frame point, the frame `frame_width` points wide): its
        curved backing scaled whole (stretched a little for a long message), the title in gold, the message off-white,
        a Play Now pill for each label (`pressed`: the index held down), or three pulsing dots at `spinner` (a phase).
        `dense`: the glass drawn twice, for a window over a list whose rows would show through it (the main menu's).
        Returns (the pills' rectangles, the backing's top and height, all in frame points; the message's lines)."""
        spec = self.ui['popup']
        art_w, art_h = spec['size']
        k = self.POPUP_W / art_w                                # frame points an art pixel
        body_px = self.POPUP_BODY * unit
        lines = self.wrap(message, body_px, round(self.POPUP_W * 0.74 * unit)) if message else []
        pitch = self.pitch(body_px) / unit
        room = (spec['text'][1] - spec['text'][0]) * k          # the backing's text band, frame points
        height = art_h * k + max(0., pitch * len(lines) - room)
        top = (layer.get_height() / unit - height) / 2
        left = (frame_width - self.POPUP_W) / 2
        stretch = height / (art_h * k)
        backing = self.popup((round(self.POPUP_W * unit), round(height * unit)))
        for _ in range(2 if dense else 1):
            layer.blit(backing, (round(left * unit), round(top * unit)))
        middle_x = round(frame_width / 2 * unit)
        self.text(layer, title, self.POPUP_TITLE * unit, self.GOLD, (middle_x, round((top + spec['title'] * k * stretch) * unit)))
        y = top + spec['text'][0] * k * stretch + (room * stretch - pitch * len(lines)) / 2 + pitch / 2
        for line in lines:
            if line:
                self.text(layer, line, body_px, self.TEXT, (middle_x, round(y * unit)))
            y += pitch
        middle = top + spec['buttons'] * k * stretch
        if spinner is not None:
            for i in range(3):
                bright = .35 + .65 * max(0., 1 - abs(((spinner - i * .35) % 3) - 1))
                colour = tuple(round(c * bright) for c in self.GOLD)
                pygame.draw.circle(layer, colour, (round((frame_width / 2 - 32 + 32 * i) * unit), round(middle * unit)),
                                   round(8 * unit))
        rects = []
        centres = ([frame_width / 2] if len(labels) == 1
                   else [frame_width / 2 + self.POPUP_GAP * (i - (len(labels) - 1) / 2) for i in range(len(labels))])
        w, h = self.POPUP_PILL
        for index, (label, centre) in enumerate(zip(labels, centres)):
            rect = pygame.Rect(round(centre - w / 2), round(middle - h / 2), w, h)
            piece = self.pill((w * unit, h * unit), h * unit / 57, 'pressed' if pressed == index else 'idle')
            layer.blit(piece, (rect.x * unit, rect.y * unit))
            self.text(layer, label, self.POPUP_LABEL * unit, self.TEXT, (rect.centerx * unit, rect.centery * unit + unit))
            rects.append(rect)
        return rects, top, height, lines

    def arrow(self, target, centre, unit):
        """Classic's back arrow, white with a soft shadow, pointing left, centred on `centre` (`unit` pixels a point of
        the 156 x 58 back button)."""
        cx, cy = centre
        u = unit
        shape = [(cx - 22 * u, cy), (cx - 4 * u, cy - 15 * u), (cx - 4 * u, cy - 6 * u), (cx + 24 * u, cy - 6 * u),
                 (cx + 24 * u, cy + 6 * u), (cx - 4 * u, cy + 6 * u), (cx - 4 * u, cy + 15 * u)]
        pygame.draw.polygon(target, (0, 0, 0, 110), [(x + 2 * u, y + 3 * u) for x, y in shape])
        pygame.draw.polygon(target, self.TEXT + (255,), shape)

    def sized(self, resource, size):
        """A chc picture scaled whole to `size` (the dialogue skin's portrait ring and disc)."""
        key = ('sized', resource, round(size[0]), round(size[1]))
        found = self._made.get(key)
        if found is None:
            found = self._made[key] = pygame.transform.smoothscale(self.picture(resource),
                                                                   (max(1, round(size[0])), max(1, round(size[1]))))
        return found

    def popup(self, size):
        """Classic's Yes/No popup backing, scaled whole (its sides are curved)."""
        key = ('popup', round(size[0]), round(size[1]))
        found = self._made.get(key)
        if found is None:
            found = self._made[key] = pygame.transform.smoothscale(self.picture(self.ui['popup']['picture']),
                                                                   (round(size[0]), round(size[1])))
        return found

    def text(self, target, words, px, colour, centre=None, *, topleft=None, alpha=255, shadow=True):
        """Romic Bold `words`, centred on `centre` (or from `topleft`), with Classic's soft drop shadow."""
        font = self.font(px)
        surface = font.render(words, True, colour)
        rect = surface.get_rect(center=centre) if centre is not None else surface.get_rect(topleft=topleft)
        if shadow:
            shade = font.render(words, True, (0, 0, 0))
            shade.set_alpha(round(150 * alpha / 255))
            target.blit(shade, rect.move(max(1, px // 22), max(1, px // 14)))
        if alpha < 255:
            surface.set_alpha(alpha)
        target.blit(surface, rect)
        return rect

    def pitch(self, px):
        """A line's height for Romic Bold at `px`: its file's own line size is too tight (lines overlapped), so 1.3 x."""
        return max(self.font(px).get_linesize(), round(px * 1.3))

    def fit(self, words, px, width, height, smallest=None):
        """(px, lines): `words` wrapped to `width` at `px`, made smaller (down to `smallest`, two thirds of `px` by
        default) until its lines' pitch fits `height`."""
        smallest = smallest or px * 2 / 3
        while True:
            lines = self.wrap(words, px, width)
            if px <= smallest or self.pitch(px) * len(lines) <= height:
                return px, lines
            px = max(smallest, px - max(1, px / 14))

    def wrap(self, words, px, width):
        """Lines of `words` at `px` that fit `width` pixels; explicit newlines break."""
        font, lines = self.font(px), []
        for paragraph in words.split('\n'):
            current = ''
            for word in paragraph.split(' '):
                trial = f'{current} {word}' if current else word
                if current and font.size(trial)[0] > width:
                    lines.append(current)
                    current = word
                else:
                    current = trial
            lines.append(current)
        return lines
