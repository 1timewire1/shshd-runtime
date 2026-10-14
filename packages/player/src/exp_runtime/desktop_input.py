"""Services 17/40's APK layouts, bitmap labels, cursor and input alert."""
from dataclasses import replace
from functools import lru_cache

from . import graphics as pygame

from .content import ContentError
from .fonts import TextStyle, layout_label
from .menu import MenuStrings
from .text_input import CURSOR_FONT, NAME_FONT
from .ui_assets import Rect, read_ui


BLUE = (41, 104, 221)
INPUT_RECT = (30, 177, 260, 40)
ALERT_RECT = (20, 160, 280, 160)


class InputRenderer:
    def __init__(self, resources, text_renderer, artwork):
        self.resources, self.text, self.art = resources, text_renderer, artwork
        self.canvas = pygame.Surface((320, 480)).convert(32)

    @lru_cache(maxsize=1)
    def strings(self):
        return MenuStrings.load(self.resources.library)

    @lru_cache(maxsize=3)
    def layout_image(self, index, width, height):
        layer = pygame.Surface((width, height), pygame.SRCALPHA).convert_alpha()
        bank = self.resources.dialogue_layout().bank
        hidden_until = 0
        for number, (node, rect) in enumerate(bank.walk(index, Rect(0, 0, width, height)), 1):
            if number <= hidden_until:
                continue
            visible = node.flags & 16 and not (index == 46 and number in (1, 10))
            # Visibility belongs to reference roots as well as images. The
            # native layout-43 footer has a hidden button subtree, and
            # 000d4658 explicitly hides layout-46 roots 1 and 10.
            if node.kind == 7 and not visible:
                hidden_until = number + sum(1 for _ in bank.walk(node.payload[0]))
                continue
            if node.kind == 1 and visible and rect.width > 0 and rect.height > 0:
                slot, frame = node.payload
                image = self.art.frame({0: 126, 2: 204, 3: 16}[slot], frame)
                layer.blit(pygame.transform.scale(image, (rect.width, rect.height)), (rect.x, rect.y))
        return layer

    @lru_cache(maxsize=32)
    def title(self, text):
        name = 'ArialRoundedMTBold30'
        font = self.text.font(name)
        # 00165c14 rebuilds this label with BMFont's cumulative kerning when
        # 000d4658 changes its anchor to (1/2,1). Other labels use 0004dc20.
        layout = self.text.layout(name, text, 2**31, TextStyle(font.line_height, 0, BLUE))
        glyphs, widths = [], []
        placed = {g.index: g for g in layout.glyphs}
        for line in layout.lines:
            previous, width = -1, 0
            for i in range(line.start, line.end):
                code = ord(text[i])
                adjustment = font.kernings.get((previous & 0xffff, code), 0)
                if i in placed:
                    g = placed[i]
                    glyphs.append(replace(g, x=width + adjustment + g.glyph.xoffset))
                width += font.glyph(text[i]).advance + adjustment
                previous = code if code < 128 else code - 256
            widths.append(width)
        max_width = self.resources.dialogue_layout().bank.rectangle(46, 18).width
        scale = min(1., max_width / layout.width) if layout.width else 1.
        return replace(layout, glyphs=tuple(glyphs)), max(widths, default=0), scale

    def _image(self, asset):
        image = self.art.ui_image(asset)
        if image is None:
            raise ContentError(f'Name-entry artwork {asset} is missing')
        return image

    def alert(self):
        # 707 is the alert's clickable panel, not the ordinary input screen.
        ios = getattr(self.resources.library, 'kind', 'apk') == 'ipa'
        if ios:
            # The IPA uses UIKit's UIAlertView, with no exported panel image.
            # Use the runtime's existing message skin for the desktop modal.
            self.art.box(self.canvas, Rect(30, 170, 260, 140), 1)
        else:
            self.canvas.blit(self._image(707), ALERT_RECT[:2])
        strings = self.strings()
        for caption, origin, color in ((strings[258], (130, 169), (255, 255, 255)),
                                        (strings[164], (140, 275), (0, 0, 0))):
            label = self.text.layout('ArialRoundedMTBold20', caption, 2**31, TextStyle(16, -16, BLUE if ios else color))
            self.text.draw_layout(self.canvas, 'ArialRoundedMTBold20', label, *origin)
        label = layout_label(self.text.font('ArialRoundedMTBold16'), strings[260],
                             280, 160, TextStyle(16, 2, BLUE if ios else (255, 255, 255)), 0x16)
        # GL node (160,375), size (280,160), anchor (1/2,1/2).
        self.text.draw_layout(self.canvas, 'ArialRoundedMTBold16', label, 20, 185)
        return [(pygame.Rect(ALERT_RECT), ('input_dismiss',))]

    def draw_ipa_entry(self, details, cursor_visible):
        """000a0238/000a0880: layout 46 supplies the entire entry panel."""
        bank = self.resources.dialogue_layout().bank
        prompt_rect = bank.rectangle(46, 23)
        prompt = self.text.layout('ArialRoundedMTBold16', details['prompt'], prompt_rect.width,
                                  TextStyle(16, 10, BLUE))
        height = max(1, round(prompt.height))
        bounds = Rect((320 - bank.layouts[46].width) // 2, 151 - height,
                      bank.layouts[46].width, bank.layouts[46].height + height - prompt_rect.height)
        title_rect = bank.rectangle(46, 18, bounds)
        title = self.text.layout('ArialRoundedMTBold30', details['title'], title_rect.width,
                                 TextStyle(30, 0, BLUE))
        active_header = 1 if title.height > title_rect.height else 10
        hidden_until = 0
        for number, (node, rect) in enumerate(bank.walk(46, bounds), 1):
            if number <= hidden_until:
                continue
            visible = node.flags & 16 and (number not in (1, 10) or number == active_header)
            if node.kind == 7 and not visible:
                hidden_until = number + sum(1 for _ in bank.walk(node.payload[0]))
                continue
            if node.kind == 1 and visible and rect.width > 0 and rect.height > 0:
                slot, frame = node.payload
                image = self.art.frame({0: 126, 2: 204, 3: 16}[slot], frame)
                self.canvas.blit(pygame.transform.scale(image, (rect.width, rect.height)), (rect.x, rect.y))
        title_y = bank.rectangle(46, 9 if active_header == 1 else 18, bounds).y
        self.text.draw_layout(self.canvas, 'ArialRoundedMTBold30', title,
                              title_rect.x + (title_rect.width - title.width) / 2, title_y)
        prompt_rect = bank.rectangle(46, 23, bounds)
        self.text.draw_layout(self.canvas, 'ArialRoundedMTBold16', prompt, prompt_rect.x, prompt_rect.y)
        entry = bank.rectangle(46, 44, bounds)
        draft = details.get('draft', details['default'])
        entered = self.text.layout('PajamaHip24', draft, 2**31, TextStyle(24))
        self.text.draw_layout(self.canvas, 'PajamaHip24', entered, entry.x, entry.y)
        if cursor_visible:
            cursor = self.text.layout('PajamaHip24', '|', 2**31, TextStyle(24))
            self.text.draw_layout(self.canvas, 'PajamaHip24', cursor, entry.x + entered.width, entry.y)
        return [(pygame.Rect(entry.x, entry.y, entry.width, entry.height), ('input_focus',))]

    def draw(self, target, session, *, error=None, cursor_visible=True):
        self.canvas.fill((0, 0, 0))
        self.art.draw_background(self.canvas, session.engine)
        if error:
            buttons = self.alert()
        elif getattr(self.resources.library, 'kind', 'apk') == 'ipa':
            buttons = self.draw_ipa_entry(session.pending.details, cursor_visible)
        else:
            bank = self.resources.dialogue_layout().bank
            width = bank.layouts[46].width + 22
            footer = bank.layouts[43]
            # GL centers (160,415), (160,267), (160,340), in z order.
            self.canvas.blit(self.layout_image(15, width, 50), (160 - width // 2, 40))
            self.canvas.blit(self.layout_image(43, footer.width, footer.height),
                             (160 - footer.width // 2, 213 - footer.height // 2))
            self.canvas.blit(self.layout_image(46, width, 156), (160 - width // 2, 62))
            details = session.pending.details
            title, title_width, scale = self.title(details['title'])
            self.text.draw_layout(self.canvas, 'ArialRoundedMTBold30', title,
                                  160 - title_width * scale / 2, 65, scale=scale)
            prompt = self.text.layout('ArialRoundedMTBold16', details['prompt'], 2**31,
                                      TextStyle(16, -16, BLUE))
            self.text.draw_layout(self.canvas, 'ArialRoundedMTBold16', prompt, 30, 120)
            shadow = self._image(706)
            self.canvas.blit(shadow, shadow.get_rect(center=(160, 197)))
            draft = details.get('draft', details['default'])
            entered = self.text.layout(NAME_FONT, draft, 2**31, TextStyle(26, -26, BLUE))
            self.text.draw_layout(self.canvas, NAME_FONT, entered, 35, 190)
            if cursor_visible:
                cursor = self.text.layout(CURSOR_FONT, '|', 2**31, TextStyle(26, -26, BLUE))
                # 000858cc creates '|' before setting nominal height 26.
                # Unlike the name, the cursor is never assigned text again;
                # its glyph keeps the initial zero-height line origin.
                self.text.draw_layout(self.canvas, CURSOR_FONT, cursor, entered.width + 33, 214 - 26)
            # Native confirmation is keyboard Return. No portrait-picker
            # checkmark or common gear is attached by this panel's setup.
            buttons = [(pygame.Rect(INPUT_RECT), ('input_focus',))]
        target.blit(pygame.transform.smoothscale(self.canvas, target.get_size()), (0, 0))
        return buttons
