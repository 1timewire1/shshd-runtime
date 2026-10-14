"""Original menu artwork and native geometry, plus desktop content setup."""
from functools import lru_cache
from collections import Counter
from io import BytesIO
import math

from . import graphics as pygame

from .app_icon import icon_surface
from .app_info import runtime_version
from .content import is_bundled
from .desktop_dialogue import DialogueRenderer
from .desktop_text import BitmapTextRenderer
from .fonts import TextStyle
from .languages import TITLE_LANGUAGES
from .games import GAMES
from .menu import MenuFont, MenuStrings, main_button_rects
from .ui_assets import ImagePack, LayoutBank, Rect, read_ui
from .updates import UPDATE_MESSAGE


BLUE = (41, 104, 221)
GRAY = (105, 105, 105)


class MenuRenderer:
    def __init__(self, library=None):
        self.library = library
        self.canvas = pygame.Surface((320, 480)).convert(32)
        self.buttons = []
        self.pressed = None
        self.fallback = pygame.font.Font(None, 20)
        self.small = pygame.font.Font(None, 17)
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
            font = self.unicode_font(size) if self.library else self.small if size < 14 else self.fallback
            y, line = rect.y, ''
            for word in (text + ' \n').split(' '):
                if word == '\n' or (line and font.size(line + word)[0] > rect.width):
                    image = font.render(line.rstrip(), True, color)
                    self.canvas.blit(image, (rect.centerx - image.get_width() / 2 if center else rect.x, y))
                    y += font.get_linesize() + 3
                    line = ''
                line += word + ' '
        self.canvas.set_clip(clip)

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

    def main(self, app):
        age = app.menu_age
        self.backdrop(age=age if app.intro else None)
        start = 1600 if app.intro else 0
        progress = min(1, max(0, (age - start) / 500))
        shift = round(-275 * (1 - progress))
        self.layout(79, Rect(shift, 353, 275, 109))
        labels = [self.strings[126 if app.can_resume() else 125], self.strings[127],
                  self.strings[91], 'Switch Game']
        commands = [('episodes', 'play'), ('episodes', 'weekly'), ('episodes', 'all'), ('switch_games',)]
        for i, (rect, label, command) in enumerate(zip(main_button_rects(self.bank), labels, commands)):
            t = min(1, max(0, (age - start - 400) / ((i + 1) * 250))) if app.intro else progress
            # Exponential slide-in; native actions use a rate-10 ease.
            t = 1 if t == 1 else 1 - 2 ** (-10 * t) if t > 0 else 0
            x = round(rect.x - (rect.x + rect.width) * (1 - t))
            bounds = Rect(x, rect.y, rect.width, rect.height)
            self.layout(77 if app.pressed == command else 75, bounds)
            image = self.menu_label(label, int(i == 3))
            self.canvas.blit(image, image.get_rect(center=(x + rect.width // 2, rect.y + rect.height // 2 - 1)))
            if app.ready:
                self.buttons.append((pygame.Rect(rect.x, rect.y, rect.width, rect.height), command))
        if progress == 1 and (not app.intro or age >= 3000):
            gear = Rect(180, 443, 39, 28)
            self.layout(77 if app.pressed == ('options',) else 75, gear)
            image = self.art.frame(272, 13)
            self.canvas.blit(image, image.get_rect(center=(200, 457)))
            image = self.art.frame(272, 15 if app.pressed == ('help',) else 14)
            self.canvas.blit(image, (278, 437))
            self.buttons.extend([(pygame.Rect(180, 440, 41, 35), ('options',)),
                                 (pygame.Rect(278, 437, 42, 41), ('help',))])

    def panel(self, title, *, back=True):
        self.backdrop()
        if self.library:
            self.art.box(self.canvas, Rect(19, 88, 282, 324), 1, alpha=248)
        else:
            pygame.draw.rect(self.canvas, (255, 255, 255), (9, 65, 302, 357), border_radius=8)
        self.label(title, (24, 69, 278, 46), size=26, title=True)
        if back:
            self.button('Back', (12, 436, 78, 29), ('back',))

    def draw(self, app):
        self.buttons = []
        self.pressed = app.pressed
        screen = app.screen
        if screen == 'main':
            self.main(app)
        elif screen == 'games':
            self.panel('EXP Runtime', back=False)
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
            self.button('Options', (165, 436, 143, 29), ('options',))
        elif screen == 'setup':
            self.panel(app.game_title)
            self.label('Bring your game', (25, 123, 270, 30), size=20)
            self.label(f'Choose your {GAMES[app.selected_game].SOURCES}. It includes the base assets and bundled episodes.',
                       (25, 169, 265, 95), color=GRAY)
            self.label('You can add EXP files or ZIP/RAR archives afterward. Choose your files below.' if app.file_picker else
                       'Add EXP files, ZIP/RAR archives or folders afterward. Drag files here, or browse below.',
                       (25, 265, 265, 85), color=GRAY)
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
                    # Native category strip: pack 16 frame 76, 296 x 12,
                    # with registry font 2. Padding makes the fold target
                    # usable with a mouse while retaining the original art.
                    self.canvas.blit(self.art.frame(16, 76), (12, y + 6))
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
            if app.state is not None:
                for y, label, value, setting in ((120, 'Music', app.state.music, 'music'), (164, 'Sound', app.state.sound, 'sound')):
                    self.label(label, (31, y + 5, 147, 30), size=20)
                    self.button('On' if value else 'Off', (213, y, 78, 29), ('toggle', setting))
            y = 208 if app.state is not None else 120
            self.label('Update checks', (31, y + 5, 173, 30), size=16)
            self.button('On' if app.settings.check_for_updates else 'Off', (213, y, 78, 29), ('toggle_updates',))
            if app.state is None:
                self.label('Check for newer releases when EXP Runtime starts. This setting applies to both games.',
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
            self.label('Choice hints', (31, 126, 170, 30), size=20)
            self.button('On' if app.state.choice_hints else 'Off', (213, 124, 78, 29),
                        ('toggle', 'choice_hints'))
            self.label('Green: gain or correct answer.\nRed: loss, wrong answer, or no gain where another answer gains.\nAmber: mixed effects.',
                       (30, 184, 260, 120), color=GRAY)
            self.label('Includes classroom and word quizzes, and short sequences with delayed rewards. Uncertain outcomes stay unmarked.',
                       (30, 321, 260, 95), color=GRAY)
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
            self.label(f'EXP Runtime v{runtime_version()}', (29, 334, 262, 25), color=GRAY)
            self.label('Independent game engine.', (29, 361, 262, 22), size=11, color=GRAY)
            self.button('GitHub Project', (30, 390, 260, 29), ('project',), pressed=app.pressed)
        elif screen == 'browser':
            self.panel({'apk': 'Choose Game', 'music_apk': 'Add APK Music',
                        'episodes': 'Add Episodes', 'library': 'Open Library'}[app.browser_kind])
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
            self.overlay('Importing content', 'Checking and copying your files...')
            self.buttons = []
            # Small animated progress indicator; work runs outside the UI thread.
            x = 55 + round((math.sin(pygame.time.get_ticks() / 250) + 1) * 90)
            pygame.draw.circle(self.canvas, BLUE, (x, 290), 5)
        elif app.update_prompt is not None:
            self.confirmation(UPDATE_MESSAGE)
        elif app.message:
            self.overlay(app.game_title, app.message)
            self.buttons = []
            self.button('OK', (121, 355, 78, 29), ('dismiss',))
        return self.canvas

    def confirmation(self, message):
        """Original two-button menu skin, with No on the left and Yes right.

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
            self.label('EXP Runtime', (24, 166, 272, 36), size=20, center=True)
            self.label(message, (24, 219, 266, 54), size=16, color=GRAY, center=True)
            # LayoutBank uses flattened one-based IDs: nodes 1/2 are the
            # footer art and separator, and nodes 3/4 are its button regions.
            for index, role, command in ((3, 26, 'update_no'), (4, 25, 'update_yes')):
                rect = self.bank.rectangle(39, index, footer)
                self.button(self.strings[role], (rect.x, rect.y, rect.width, rect.height),
                            (command,), selected=True)
        else:
            # No game files exist yet; retain the launcher's authored fallback.
            self.overlay('EXP Runtime', message)
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
