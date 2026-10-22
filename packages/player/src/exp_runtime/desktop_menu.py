"""Original menu artwork and native geometry, plus desktop content setup."""
from functools import lru_cache
from collections import Counter
from io import BytesIO
import math

from .graphics import faded
from . import graphics as pygame

from .app_icon import icon_surface
from .app_info import runtime_version
from .content import is_bundled
from .launcher import APP_NAME
from .desktop_dialogue import DialogueRenderer
from .desktop_text import BitmapTextRenderer
from .fonts import TextStyle
from .languages import TITLE_LANGUAGES
from .games import GAMES
from .menu import MenuFont, MenuStrings, main_button_rects, main_button_x
from .animation_curves import power_in_out
from .ui_assets import ImagePack, LayoutBank, Rect, read_ui
from .vector_text import system_font_path
from .app_info import UPDATE_REPOSITORY
from .updates import update_message


BLUE = (41, 104, 221)
GRAY = (105, 105, 105)
TEXT_SUPERSAMPLE = 3


class MenuRenderer:
    def __init__(self, library=None):
        self.library = library
        self.canvas = pygame.Surface((320, 480)).convert(32)
        self.background = self.layer = None
        self.buttons = []
        self.pressed = None
        # Before a library exists there's no player-supplied font yet (it's copied in during import), and no
        # native bitmap font either -- a real installed face (same search `vector_text.py` uses for everything
        # else) reads far more cleanly here than pygame's own built-in default font. `None` falls back to that
        # default only if this machine has nothing matching 'arial' at all.
        self.fallback_path = system_font_path('arial')
        if library:
            self.bank = LayoutBank.parse(read_ui(library, 14))
            self.strings = MenuStrings.load(library)
            self.text = BitmapTextRenderer(library)
            self.art = DialogueRenderer(library, self.text, self.image)
            self.menu_fonts = [MenuFont.parse(read_ui(library, asset)) for asset in (532, 533)]

    @lru_cache(maxsize=16)
    def image(self, asset):
        data = read_ui(self.library, asset)
        if data.startswith((b'\x89PNG', b'\xff\xd8')):
            return pygame.image.load(BytesIO(data)).convert_alpha()
        r = ImagePack.parse(data).images[0]
        return pygame.image.frombytes(r.pixels, (r.width, r.height), r.mode).convert_alpha()

    @lru_cache(maxsize=48)
    def menu_label(self, text, variant=0):
        f = self.menu_fonts[variant]
        widths = [f.space if c == ' ' else f.glyph(c).width + f.tracking if f.glyph(c) else f.space
                  for c in text]
        surface = pygame.Surface((max(1, sum(widths) - f.tracking), f.height), pygame.SRCALPHA).convert_alpha()
        x = 0
        for c, width in zip(text, widths):
            r = f.glyph(c)
            if c != ' ' and r:
                surface.blit(pygame.image.frombytes(r.pixels, (r.width, r.height), 'RGBA').convert_alpha(), (x, 0))
            x += width
        return surface

    def label(self, text, rect, *, size=14, color=BLUE, center=False, title=False):
        rect = pygame.Rect(rect)
        clip = self.canvas.get_clip()
        self.canvas.set_clip(rect.clip(clip))
        native = False
        if self.library:
            name = 'PajamaHip26' if title else 'ArialRoundedMTBold16'
            font = self.text.font(name)
            native = all(c == '\n' or ord(c) in font.glyphs for c in text)
        if native:
            layout = self.text.layout(name, text, rect.width, TextStyle(size, 3, color))
            x = rect.x + (rect.width - layout.width) / 2 if center else rect.x
            self.text.draw_layout(self.canvas, name, layout, x, rect.y)
        else:
            # Desktop metadata is UTF-8, but Android's supplied bitmap fonts
            # only cover ASCII. Keep translated titles/language names intact;
            # this menu-only fallback never changes story layout or saves.
            if self.library:
                font, hq = self.unicode_font(size), self.unicode_font(size * TEXT_SUPERSAMPLE)
            else:
                font, hq = self.fallback_font(size), self.fallback_font(size * TEXT_SUPERSAMPLE)
            y, line = rect.y, ''
            for word in (text + ' \n').split(' '):
                if word == '\n' or (line and font.size(line + word)[0] > rect.width):
                    stripped = line.rstrip()
                    width, height = font.size(stripped)
                    if width > 0 and height > 0:
                        image = pygame.transform.smoothscale(hq.render(stripped, True, color), (width, height))
                        self.canvas.blit(image, (rect.centerx - width / 2 if center else rect.x, y))
                    y += font.get_linesize() + 3
                    line = ''
                line += word + ' '
        self.canvas.set_clip(clip)

    @lru_cache(maxsize=16)
    def fallback_font(self, size):
        # Before a library exists there's no player-supplied font yet (it's copied in during import), and no
        # native bitmap font either -- a real installed face (same search `vector_text.py` uses for everything
        # else) reads far more cleanly here than pygame's own built-in default font. `None` falls back to that
        # default only if this machine has nothing matching 'arial' at all. Each label keeps its own size (this
        # fork; one 20 px face for every size overflowed the setup and chooser text). The canvas is native
        # 320x480 and smoothscaled up afterward, so `label` renders each line TEXT_SUPERSAMPLE times larger and
        # downscales it -- the same trade `desktop_badge_hd.py` makes for HD badge text.
        return pygame.font.Font(self.fallback_path, round(size + 1))

    @lru_cache(maxsize=8)
    def unicode_font(self, size):
        # Prefer the original installed UI face; pygame supplies its default
        # when the system has no matching font. No font data are imported.
        path = pygame.font.match_font('Arial Rounded MT Bold,Arial Rounded', bold=True)
        return pygame.font.Font(path, round(size))

    def button(self, label, rect, command, *, pressed=None, enabled=True, selected=False):
        rect = pygame.Rect(rect)
        pressed = (self.pressed if pressed is None else pressed) if enabled else None
        if self.library:
            # Native list buttons: layouts 70/71 (blue), 72/73 (orange).
            layout = (72 if selected else 70) + int(pressed == command)
            self.layout(layout, Rect(*rect))
        else:
            pygame.draw.rect(self.canvas, (223, 230, 238) if pressed != command else (185, 204, 227), rect, border_radius=5)
        self.label(label, rect.inflate(-8, -8).move(0, -1), size=14, center=True,
                   color=(255, 255, 255) if enabled and self.library else BLUE if enabled else GRAY)
        if enabled:
            self.buttons.append((rect, command))

    def layout(self, index, rect):
        for node, bounds in self.bank.walk(index, rect):
            if node.kind == 1:
                slot, frame = node.payload
                pack = {0: 126, 3: 16, 5: 272}[slot]
                image = self.art.frame(pack, frame)
                if bounds.width > 0 and bounds.height > 0:
                    self.canvas.blit(pygame.transform.scale(image, (bounds.width, bounds.height)), (bounds.x, bounds.y))

    def backdrop(self, *, age=None):
        paused = getattr(self, 'pause_background', None)
        if paused is not None:
            self.canvas.blit(pygame.transform.smoothscale(paused, (320, 480)), (0, 0))
            return
        if not self.library:
            self.canvas.fill((243, 244, 247))
            return
        self.canvas.blit(self.image(6), (0, 0))
        photo = self.image(9)
        if age is not None and age < 1000:
            scale = 1 + 5 * (1 - age / 1000)
            photo = pygame.transform.smoothscale(photo, (round(photo.get_width() * scale), round(photo.get_height() * scale)))
        self.canvas.blit(photo, photo.get_rect(center=(160, 240)))
        if age is None or age >= 1100:
            ribbon = self.image(8)
            height = 1 if age is not None and age < 1100 else min(1, (age - 1100) / 400) if age is not None else 1
            ribbon = pygame.transform.smoothscale(ribbon, (336, max(1, round(69 * (.1 + .9 * height)))))
            ribbon = pygame.transform.rotate(ribbon, 5)
            self.canvas.blit(ribbon, ribbon.get_rect(center=(160, 96)))
            self.canvas.blit(self.image(7), self.image(7).get_rect(center=(160, 96)))

    def main(self, app, *, exit_ms=None):
        age = app.menu_age
        self.backdrop(age=age if app.intro and exit_ms is None else None)
        self.begin_layer()
        start = 1600 if app.intro else 0
        progress = min(1, max(0, (age - start) / 500)) if exit_ms is None else 1
        shift = round(-275 * (1 - progress))
        if exit_ms is not None:
            # 000de9fc -> 000de7fc moves the strip after the last row.
            shift = -round(275 * min(1, max(0, (exit_ms - 1550) / 500)))
        self.layout(79, Rect(shift, 353, 275, 109))
        labels = [self.strings[126 if app.can_resume() else 125], self.strings[127],
                  self.strings[91], 'Switch Game']
        commands = [('episodes', 'play'), ('episodes', 'weekly'), ('episodes', 'all'), ('switch_games',)]
        for i, (rect, label, command) in enumerate(zip(main_button_rects(self.bank), labels, commands)):
            if exit_ms is None:
                t = min(1, max(0, (age - start - 400) / ((i + 1) * 250))) if app.intro else progress
                t = power_in_out(t)
            else:
                # 000df168 -> 000dede4 -> 000df270: gear 250ms,
                # info 300ms, then four rate-10 moves of 250..1000ms.
                t = 1 - power_in_out(min(1, max(0, (exit_ms - 550) / ((i + 1) * 250))))
            x = main_button_x(self.bank, i, 1 - t if exit_ms is not None else t,
                              exiting=exit_ms is not None)
            bounds = Rect(x, rect.y, rect.width, rect.height)
            self.layout(77 if app.pressed == command else 75, bounds)
            image = self.menu_label(label, int(i == 3))
            self.canvas.blit(image, image.get_rect(center=(x + rect.width // 2, rect.y + rect.height // 2 - 1)))
            if app.ready and exit_ms is None:
                self.buttons.append((pygame.Rect(rect.x, rect.y, rect.width, rect.height), command))
        if progress == 1 and (exit_ms is not None or not app.intro or age >= 3000):
            # 000dede4 fades info for 300ms; its completion schedules
            # 000df168's 250ms gear scale from .1 to 1.
            # The exit runs a child scale/fade while its menu parent is
            # already hidden (CCMenu vtable +0x6c -> 0013b518). Preserve
            # those callback intervals without drawing the hidden children.
            if exit_ms is None and (not app.intro or age >= 3300):
                scale = min(1, .1 + .9 * (age - 3300) / 250) if app.intro else 1
                original = self.canvas
                self.canvas = pygame.Surface((320, 480), pygame.SRCALPHA).convert_alpha()
                try:
                    self.layout(77 if app.pressed == ('options',) else 75, Rect(180, 443, 39, 28))
                    image = self.art.frame(272, 13)
                    self.canvas.blit(image, image.get_rect(center=(200, 457)))
                    image = self.canvas.subsurface((180, 443, 40, 28))
                    image = pygame.transform.smoothscale(image, (max(1, round(40 * scale)), max(1, round(28 * scale))))
                finally:
                    self.canvas = original
                self.canvas.blit(image, image.get_rect(center=(200, 457)))
                self.buttons.append((pygame.Rect(180, 440, 41, 35), ('options',)))
            if exit_ms is None or exit_ms < 250:
                image = self.art.frame(272, 15 if app.pressed == ('help',) else 14).copy()
                opacity = min(1, (age - 3000) / 300) if app.intro and exit_ms is None else 1
                image = faded(image, round(255 * opacity))
                self.canvas.blit(image, (278, 437))
                if exit_ms is None:
                    self.buttons.append((pygame.Rect(278, 437, 42, 41), ('help',)))

    def panel(self, title, *, back=True):
        self.backdrop()
        self.begin_layer()
        if self.library:
            self.art.box(self.canvas, Rect(19, 88, 282, 324), 1, alpha=248)
        else:
            pygame.draw.rect(self.canvas, (255, 255, 255), (9, 65, 302, 357), border_radius=8)
        self.label(title, (24, 69, 278, 46), size=26, title=True)
        if back:
            self.button('Back', (12, 436, 78, 29), ('back',))

    def draw(self, app):
        self.background = self.layer = None
        self.pause_background = (app.game.pause_renderer.background
                                 if app.paused_menu and app.game.pause_renderer is not None else None)
        self.buttons = []
        self.pressed = app.pressed
        screen = app.screen
        outgoing = None
        if getattr(app, 'main_exit_ms', None) is not None:
            self.main(app, exit_ms=app.main_exit_ms)
            outgoing = self.canvas
            self.canvas = self.background.copy()
        if screen == 'main':
            self.main(app)
        elif screen == 'games':
            self.panel(APP_NAME, back=False)
            self.canvas.blit(icon_surface(64), (128, 0))
            self.label('Choose a game', (25, 128, 270, 30), size=20, center=True)
            for index, (key, game) in enumerate(GAMES.items()):
                y = 193 + 99 * index
                self.button(game.TITLE, (25, y, 270, 36), ('choose_game', key), pressed=app.pressed)
                ready = (app.library_path(key) / 'library.json').is_file()
                self.label('Open your library' if ready else 'Import your game assets to play',
                           (25, y + 44, 270, 32), color=GRAY, center=True)
            self.label('Each game uses its own assets, episodes and saves.',
                       (30, 377, 260, 45), color=GRAY, center=True)
            self.button('Bulk Import', (12, 436, 143, 29), ('bulk',))
            self.button('Options', (165, 436, 143, 29), ('options',))
        elif screen == 'bulk':
            # This fork's first-boot page: one .zip/.rar holding both games' files (staged_import.py).
            self.panel('Bulk Import')
            self.canvas.blit(icon_surface(64), (128, 0))
            self.label('Bring your games', (25, 123, 270, 30), size=20)
            self.label('Choose the one ZIP or RAR file that holds your game files: the SHS APK, the SHS HD '
                       'and Cause of Death IPAs, the font, and the episode folders.',
                       (25, 160, 268, 110), color=GRAY)
            self.label(('Choose it below.' if app.file_picker else 'Drag it here, or choose it below.')
                       + ' Back leads to each game\'s own setup.', (25, 268, 268, 55), color=GRAY)
            if not app.file_picker:
                self.label('Or put it in the import folder beside the app before starting it.',
                           (25, 323, 268, 40), size=11, color=GRAY)
            self.button('Choose File', (85, 370, 150, 32), ('browse', 'bulk'))
        elif screen == 'setup':
            self.panel(app.game_title)
            self.label('Bring your game', (25, 123, 270, 30), size=20)
            self.label(f'Choose your {GAMES[app.selected_game].SOURCES}. It includes the base assets and bundled episodes.',
                       (25, 169, 265, 66), color=GRAY)
            self.label(('You can add EXP files or ZIP/RAR archives afterward. Choose your files below.' if app.file_picker else
                        'Add EXP files, ZIP/RAR archives or folders afterward. Drag files here, or browse below.')
                       + (' Add your HD (iPad) ipa alongside the APK too, if you have one, for HD art.'
                          if app.selected_game == 'shs' else ''),
                       (25, 238, 265, 118), color=GRAY)
            self.button('Choose Game', (30, 362, 124, 32), ('browse', 'apk'))
            self.button('Open Library', (166, 362, 124, 32), ('browse', 'library'))
        elif screen == 'episodes':
            title = {'play': 'Play / Resume', 'weekly': self.strings[127], 'all': self.strings[91]}[app.scope]
            self.panel(title)
            query = app.query or 'Search episodes...'
            pygame.draw.rect(self.canvas, (230, 236, 244), (19, 113, 170, 29), border_radius=4)
            self.label(query, (26, 119, 156, 21), color=BLUE if app.query else GRAY)
            self.buttons.append((pygame.Rect(19, 113, 170, 29), ('search',)))
            self.button('By Number' if app.state.order == 'episode' else 'By Title',
                        (196, 113, 105, 29), ('order',), pressed=app.pressed)
            clip = pygame.Rect(9, 150, 302, 252)
            self.canvas.set_clip(clip)
            duplicates = Counter(app.state.title(e) for e in app.library.episodes)
            rows, total = app.episode_rows()
            app.scroll = min(app.scroll, max(0, total - clip.height))
            index = 0
            for top, height, section, record in rows:
                y = clip.top + top - app.scroll
                if record is not None:
                    index += 1
                if y + height <= clip.top or y >= clip.bottom:
                    continue
                if record is None:
                    # Native category strip: pack 16 frame 73 (blue, 296 x 12) or, for Mega Packs only, frame 76
                    # (the same strip, orange) -- with registry font 2. Padding makes the fold target usable with
                    # a mouse while retaining the original art.
                    strip = 76 if section.title == self.strings[82] else 73
                    self.canvas.blit(self.art.frame(16, strip), (12, y + 6))
                    expanded = bool(app.query) or section.key in app.expanded_groups
                    points = ((18, y + 9), (24, y + 9), (21, y + 15)) if expanded else (
                        (18, y + 8), (18, y + 16), (24, y + 12))
                    pygame.draw.polygon(self.canvas, (255, 255, 255), points)
                    label = self.text.layout('ArialRoundedMTBold11', section.title, 243,
                                             TextStyle(11, 0, (255, 255, 255)))
                    self.text.draw_layout(self.canvas, 'ArialRoundedMTBold11', label,
                                          29, y + (height - label.height) / 2)
                    count = self.text.layout('ArialRoundedMTBold11', str(len(section.episodes)), 25,
                                             TextStyle(11, 0, (255, 255, 255)))
                    self.text.draw_layout(self.canvas, 'ArialRoundedMTBold11', count,
                                          300 - count.width, y + (height - count.height) / 2)
                    if not app.query:
                        self.buttons.append((pygame.Rect(9, y, 302, height).clip(clip), ('episode_group', section.key)))
                    continue
                rect = pygame.Rect(12, y, 296, height)
                selected = app.pressed == ('episode', record['id'])
                image = self.art.frame(16, 84 if selected else 83 if index % 2 == 0 else 82)
                self.canvas.blit(image, rect)
                title = app.state.title(record)
                duplicate = duplicates[title] > 1
                self.label(title, (27, y + (2 if duplicate else 7), 224, 21 if duplicate else 31), size=14)
                if duplicate:
                    self.label('Bundled version' if is_bundled(record) else 'Imported version',
                               (27, y + 25, 224, 16), size=11, color=GRAY)
                saved = record['id'] in app.saved
                icon = self.art.frame(16, 96 if saved else 101)
                self.canvas.blit(icon, icon.get_rect(center=(277, y + 21)))
                self.buttons.append((rect.clip(clip), ('episode', record['id'])))
            self.canvas.set_clip(None)
            maximum = max(0, total - clip.height)
            if maximum:
                pygame.draw.rect(self.canvas, (208, 219, 231), (305, clip.y, 3, clip.height))
                thumb = max(18, round(clip.height * clip.height / (maximum + clip.height)))
                y = clip.y + round((clip.height - thumb) * app.scroll / maximum)
                pygame.draw.rect(self.canvas, BLUE, (305, y, 3, thumb))
            if not app.visible_episodes():
                self.label('No episodes found. Add EXP files or ZIP/RAR archives below.', (30, 191, 260, 85), color=GRAY)
            sections = app.episode_sections()
            group_count = sum(section.key != 'saved' for section in sections)
            count = self.text.layout('ArialRoundedMTBold11',
                                     f'{len(app.visible_episodes())} episodes in {group_count} groups',
                                     280, TextStyle(11, 0, GRAY))
            self.text.draw_layout(self.canvas, 'ArialRoundedMTBold11', count, 160 - count.width / 2, 403)
            if app.query:
                self.button('Clear Search', (99, 436, 121, 29), ('clear_search',))
            else:
                expanded = all(section.key in app.expanded_groups for section in sections)
                self.button('Collapse All' if expanded else 'Expand All', (99, 436, 121, 29), ('episode_groups',))
            self.button('Add', (230, 436, 78, 29), ('browse', 'episodes'))
        elif screen in ('episode', 'restart'):
            record = app.library.select(app.selected)
            self.panel('Restart Episode?' if screen == 'restart' else 'Play Episode')
            self.label(app.state.title(record), (29, 127, 262, 80), size=22, center=True)
            if screen == 'restart':
                self.label('Start from the beginning? Your next automatic checkpoint will replace the previous one. Manual saves are kept.',
                           (30, 224, 260, 110), color=GRAY)
                self.button('Restart', (99, 349, 122, 32), ('start', False))
            else:
                self.label('Bundled with your game' if is_bundled(record) else 'Imported episode',
                           (30, 231, 260, 35), color=GRAY, center=True)
                can_resume = app.can_resume(record['id'])
                self.button('Resume' if can_resume else 'Play', (83, 298, 154, 33), ('start', True))
                if can_resume:
                    self.button('New Game', (83, 350, 154, 33), ('restart',))
        elif screen == 'options':
            self.panel('Options')
            y = 120
            if app.state is not None:
                settings = [('Music', app.state.music, 'music'), ('Sound', app.state.sound, 'sound')]
                spacing = 44
                if pygame.supports_vibration():
                    settings.append(('Vibration', app.state.vibration, 'vibration'))
                    y, spacing = 108, 34
                for label, value, setting in settings:
                    self.label(label, (31, y + 5, 147, 30), size=20)
                    self.button('On' if value else 'Off', (213, y, 78, 29), ('toggle', setting))
                    y += spacing
            if UPDATE_REPOSITORY is not None:          # only with a release source (app_info)
                self.label('Update checks', (31, y + 5, 173, 30), size=16)
                self.button('On' if app.settings.check_for_updates else 'Off', (213, y, 78, 29), ('toggle_updates',))
            if app.state is None:
                if UPDATE_REPOSITORY is not None:
                    self.label(f'Check for newer releases when {APP_NAME} starts. This setting applies to both games.',
                               (31, 175, 258, 100), color=GRAY)
            elif app.paused_menu:
                self.button('Cheats', (30, 257, 260, 34), ('cheats',))
                self.label('Runtime save slot', (31, 298, 258, 25), color=GRAY)
                self.button('Save Progress', (30, 329, 260, 34), ('save',))
                self.button('Load Progress', (30, 377, 260, 34), ('load',))
            else:
                self.label('Episode title language', (31, 246, 258, 25))
                language = self.strings[118 + TITLE_LANGUAGES.index(app.state.title_language)]
                self.button(language, (30, 273, 260, 29), ('title_languages',))
                self.button('Add Episodes', (30, 310, 260, 29), ('browse', 'episodes'))
                self.button('Content Library', (30, 347, 260, 29), ('library',))
                self.button('Cheats', (30, 384, 260, 29), ('cheats',))
                self.button('Switch Game', (165, 436, 143, 29), ('switch_games',))
        elif screen == 'cheats':
            self.panel('Cheats')
            # Four switches, each with a short note, inside the box (its bottom is y 412).
            rows = (('Answer hints', 'choice_hints', 'Green: gain or right. Red: loss or wrong. Amber: mixed effects.'),
                    ('Skip mini-games', 'skip_minigames', 'Football and word games first ask: Win, Lose or Play.'),
                    ('Skip ad intros', 'skip_ad_intros', 'Starts High School Story ad episodes at the story.'),
                    ('Skip upsell intros', 'skip_upsell_intros', 'Skips the store plugs some episodes open with.'))
            for index, (label, setting, note) in enumerate(rows):
                y = 122 + index * 72
                self.label(label, (31, y + 2, 178, 30), size=20)
                self.button('On' if getattr(app.state, setting) else 'Off', (213, y, 78, 29), ('toggle', setting))
                self.label(note, (30, y + 32, 260, 38), color=GRAY)
        elif screen == 'title_languages':
            self.panel('Episode Titles')
            self.label('Choose episode names where translations are available. Story text stays in the language of each supplied episode.',
                       (30, 120, 260, 80), color=GRAY)
            for index, language in enumerate(TITLE_LANGUAGES):
                selected = language == app.state.title_language
                label = self.strings[118 + index] + (' (selected)' if selected else '')
                self.button(label, (30, 210 + index * 39, 260, 32), ('title_language', language),
                            pressed=app.pressed, selected=selected)
        elif screen == 'library':
            self.panel('Content Library')
            self.label(f'{len(app.library.episodes)} imported episodes', (29, 129, 262, 45), size=20)
            if (app.library.game_id, app.library.kind) == ('shs', 'ipa'):
                count = len(app.library.missing_music_ids)
                caption = (f'{count} music tracks are missing. Optionally add your Android APK to supply them.'
                           if count else 'All separately downloaded music tracks are available.')
                self.label(caption, (29, 191, 262, 95), color=GRAY)
                self.button('Add Episodes', (30, 299, 260, 32), ('browse', 'episodes'))
                if count:
                    self.button('Add APK Music', (30, 343, 260, 32), ('browse', 'music_apk'))
                self.button('Open Another Library', (30, 387, 260, 32), ('browse', 'library'))
            else:
                self.label(f'Your {app.library.kind.upper()} supplies the {app.game_title} assets. Episode files supply their own stories and artwork. Your originals are kept intact.',
                           (29, 197, 262, 95), color=GRAY)
                self.button('Add Episodes', (30, 315, 260, 34), ('browse', 'episodes'))
                self.button('Open Another Library', (30, 369, 260, 34), ('browse', 'library'))
        elif screen == 'help':
            self.panel('Help / About')
            self.label('Tap to reveal text and continue. The lower-left button opens Pause. Save and load progress under Options.' if app.file_picker else
                       'Click or press Space to reveal text and continue. Escape opens the pause menu. F5 saves; F9 loads your manual save.',
                       (29, 125, 262, 100), color=GRAY)
            self.label('Add EXP files or ZIP/RAR archives in Options using Files. Play/Resume lists your installed episodes.' if app.file_picker else
                       'Add EXP files or ZIP/RAR archives in Options, or drop files and folders onto the menu. Play/Resume lists your episodes.',
                       (29, 235, 262, 100), color=GRAY)
            self.label(f'SHSHD Runtime v{runtime_version()}', (29, 334, 262, 25), color=GRAY)
            self.label('Independent game engine.', (29, 361, 262, 22), size=11, color=GRAY)
            self.button('GitHub Project', (30, 390, 260, 29), ('project',), pressed=app.pressed)
        elif screen == 'browser':
            self.panel({'apk': 'Choose Game', 'music_apk': 'Add APK Music', 'episodes': 'Add Episodes',
                        'library': 'Open Library', 'bulk': 'Bulk Import'}[app.browser_kind])
            pygame.draw.rect(self.canvas, (230, 236, 244), (19, 110, 282, 37), border_radius=4)
            self.label(app.path_text, (24, 114, 272, 30), size=11)
            self.buttons.append((pygame.Rect(19, 110, 282, 37), ('path',)))
            self.button('Up', (20, 155, 60, 27), ('up',))
            self.label('Click a folder to open it', (91, 161, 210, 23), size=11, color=GRAY)
            clip = pygame.Rect(19, 190, 282, 210)
            self.canvas.set_clip(clip)
            for i, path in enumerate(app.files):
                rect = pygame.Rect(19, 190 + i * 35 - app.scroll, 282, 35)
                if not rect.colliderect(clip):
                    continue
                color = ((170, 225, 249) if app.pressed == ('file', path) else
                         (240, 242, 246) if i % 2 else (255, 255, 255))
                pygame.draw.rect(self.canvas, color, rect)
                self.label(('[+] ' if path.is_dir() else '') + path.name, rect.inflate(-10, -8), size=14)
                self.buttons.append((rect.clip(clip), ('file', path)))
            self.canvas.set_clip(None)
            if not app.files:
                self.label('No matching files in this folder.', (30, 230, 260, 70), color=GRAY)
            if app.browser_kind in ('episodes', 'library'):
                self.button('Use This Folder', (162, 436, 146, 29), ('folder',))
        if app.busy:
            if app.job_kind == 'previews':
                self.overlay('Preparing episodes', app.progress_text)
            else:
                self.overlay('Importing content', 'Checking and copying your files...')
            self.buttons = []
            # Small animated progress indicator; work runs outside the UI thread.
            x = 55 + round((math.sin(pygame.time.get_ticks() / 250) + 1) * 90)
            pygame.draw.circle(self.canvas, BLUE, (x, 290), 5)
        elif app.update_prompt is not None:
            self.confirmation(update_message(app.update_prompt.version, can_quit=app.can_quit), single=not app.can_quit)
        elif app.message:
            self.overlay(app.game_title, app.message)
            self.buttons = []
            self.button('OK', (121, 355, 78, 29), ('dismiss',))
        if self.background is not None:
            self.layer = self.canvas
            if outgoing is not None:
                self.background.blit(outgoing, (0, 0))
            self.canvas = self.background.copy()
            self.canvas.blit(self.layer, (0, 0))
        return self.canvas

    def begin_layer(self):
        """exp-runtime v0.6.0: draw the screen's own layer apart from its backdrop, for the menu transitions."""
        self.background = self.canvas.copy()
        self.canvas = pygame.Surface((320, 480), pygame.SRCALPHA).convert_alpha()

    def confirmation(self, message, *, single=False):
        """Original two-button menu skin, with No on the left and Yes right (`single`: one OK, centred, which
        dismisses; the iOS update notice).

        SHSWidgetMenu::generateNewMenu/finalizeMenu select header 33,
        footer 39 and orange normal/held buttons 72/73 for this menu style.
        The new app message uses that skin without invoking a story service.
        """
        self.buttons = []
        if self.library:
            shade = pygame.Surface((320, 480), pygame.SRCALPHA).convert_alpha()
            shade.fill((0, 0, 0, 150))
            self.canvas.blit(shade, (0, 0))
            pygame.draw.rect(self.canvas, (239, 239, 239), (9, 155, 302, 169))
            self.layout(33, Rect(9, 155, 302, 56))
            footer = Rect(9, 281, 302, 43)
            self.layout(39, footer)
            self.label(APP_NAME, (24, 166, 272, 36), size=20, center=True)
            # This fork's longer update text: a smaller size over the whole space between header and footer.
            self.label(message, (24, 207, 272, 72), size=13, color=GRAY, center=True)
            # LayoutBank uses flattened one-based IDs: nodes 1/2 are the
            # footer art and separator, and nodes 3/4 are its button regions.
            if single:
                left, right = self.bank.rectangle(39, 3, footer), self.bank.rectangle(39, 4, footer)
                x = round((left.x + right.x + right.width) / 2 - left.width / 2)
                self.button('OK', (x, left.y, left.width, left.height), ('update_no',), selected=True)
                return
            for index, role, command in ((3, 26, 'update_no'), (4, 25, 'update_yes')):
                rect = self.bank.rectangle(39, index, footer)
                self.button(self.strings[role], (rect.x, rect.y, rect.width, rect.height),
                            (command,), selected=True)
        else:
            # No game files exist yet; retain the launcher's authored fallback.
            self.overlay(APP_NAME, message)
            if single:
                self.button('OK', (121, 355, 78, 29), ('update_no',))
                return
            self.button('No', (34, 355, 78, 29), ('update_no',))
            self.button('Yes', (208, 355, 78, 29), ('update_yes',))

    def overlay(self, title, text):
        shade = pygame.Surface((320, 480), pygame.SRCALPHA).convert_alpha()
        shade.fill((0, 0, 0, 150))
        self.canvas.blit(shade, (0, 0))
        if self.library:
            self.art.box(self.canvas, Rect(29, 143, 262, 244), 1)
        else:
            pygame.draw.rect(self.canvas, (255, 255, 255), (19, 133, 282, 264), border_radius=8)
        self.label(title, (35, 146, 250, 41), size=20, center=True)
        self.label(text, (35, 195, 250, 145), size=14, color=GRAY)
