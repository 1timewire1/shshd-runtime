"""This player's own screens in HD (owner, 2026-10-30): the game chooser, Bulk Import and each game's Setup, and the
message / update / busy cards over them, in the HD frame (768 x 1024 points) instead of the SD renderer's 320 x 480.

No HD art exists before a library (it comes from the player's own SHS HD app; none ships), so these are drawn in
the HD pause menu's card (desktop_pause_hd.HdPauseMenu: its measurements, colours, rows and Arial Bold) with
`AppCard` drawing the parts that card takes from the art -- the blue back button and the orange buttons -- as
shapes. They look the same on a first launch as later, on a computer and a phone. SHS HD's blue dress throughout
(the app's own look), on a dark gradient, with the kiwi above the card; the chooser shows each imported game's own
app icon (from the player's APK / IPA).

Commands are the SD screens' (`Application.command`): this only draws, and lists its buttons in frame points.
"""
from functools import lru_cache
from pathlib import Path
import time

import pygame

from .app_icon import game_icon_surface, icon_surface
from .desktop_pause import ease_in_out
from .desktop_pause_hd import (BACK, BLUE, BORDER, CYCLE_POINTS, FOOT, HEADER, LABEL_BLUE, PANEL_W, PANEL_X, ROW,
                               ROW_BACKGROUND, SEPARATOR, HdPauseMenu)
from .games import GAMES
from .hd_scale import S

FRAME = (768, 1024)
APP_SCREENS = ('games', 'bulk', 'setup')        # drawn here (the rest of the SD screens follow: docs/MAIN_MENU.md)
BACKDROP = ((28, 42, 72), (8, 12, 20))          # the dark gradient behind the cards, top to bottom
GRAY = (104, 112, 128)                          # body text and status lines
ORANGE = ((246, 168, 76), (226, 128, 40), (200, 100, 24))    # HD's orange button, top / middle / bottom
BUTTON_BLUE = ((96, 156, 246), (54, 116, 226), (34, 88, 196))
BUTTON_SIZE = (156, 58)
KIWI, KIWI_Y = 96, 28                           # the app's icon above the card
TEXT_PT, TEXT_PITCH, HEADING_PT = 26, 33, 34
GAME_ROW, GAME_ICON = 132, 84
SLIDE_MS = 400                                  # a page change slides, as the HD pause pages do
FOCUS = (255, 214, 102)                          # the keyboard / controller highlight
WINDOW_TOP = 260
SHORT_FOOT = 26                                 # a card's footer with nothing in it: a closing band
BROWSER_ROW = 72                                # a file browser row
# The busy card's note (owner, 2026-10-30): an import takes minutes, longer on a phone.
IMPORT_NOTE = ('Importing can take a while: a few minutes on a computer, longer on a phone. Keep SHSHD Runtime open '
               'until it finishes.')


class AppCard(HdPauseMenu):
    """HD's card without HD's art: what HdPauseMenu takes from the SHS HD app (resource 32's buttons) drawn as
    shapes, its fonts the system's Arial Bold (else pygame's own)."""

    def __init__(self):
        super().__init__(None)
        self.pressed = None

    def raw(self, resource_id):
        return None

    def available(self):
        return True

    @lru_cache(maxsize=16)
    def font(self, points):
        return pygame.font.Font(pygame.font.match_font('arial', bold=True), round(points * self.scale))

    def gradient_box(self, box, stops, radius):
        """A rounded box whose colour runs down through `stops` (evenly spaced), at the layer's density."""
        x, y, w, h = box
        width, height = round(w * S), round(h * S)
        surface = pygame.Surface((width, height), pygame.SRCALPHA)
        for row in range(height):
            t = row / max(1, height - 1) * (len(stops) - 1)
            i = min(int(t), len(stops) - 2)
            f = t - i
            surface.fill(tuple(round(a + (b - a) * f) for a, b in zip(stops[i], stops[i + 1])) + (255,), (0, row, width, 1))
        mask = pygame.Surface((width, height), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, width, height), border_radius=round(radius * S))
        surface.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        return surface

    def button(self, layer, box, label=None, *, orange=True, lit=False, arrow=False):
        """A footer button (HD's are 156 x 58): orange, or blue with the back arrow; darker while held or lit."""
        x, y, w, h = box
        stops = ORANGE if orange else BUTTON_BLUE
        if lit:
            stops = tuple(tuple(round(c * .8) for c in color) for color in stops)
        layer.blit(self.gradient_box(box, stops, 10), (round(x * S), round(y * S)))
        self.rect(layer, tuple(round(c * .75) for c in stops[-1]), box, 10, 2)
        if arrow:
            cx, cy = x + w / 2, y + h / 2
            points = [(cx - 22, cy), (cx - 4, cy - 17), (cx - 4, cy - 7), (cx + 22, cy - 7), (cx + 22, cy + 7),
                      (cx - 4, cy + 7), (cx - 4, cy + 17)]
            pygame.draw.polygon(layer, (255, 255, 255), [(round(px * S), round(py * S)) for px, py in points])
        if label:
            points = 26
            while points > 16 and self.font(points).size(label)[0] / S > w - 20:
                points -= 2
            surface = self.font(points).render(label, True, (255, 255, 255))
            layer.blit(surface, surface.get_rect(center=(round((x + w / 2) * S), round((y + h / 2 - 1) * S))))
        return pygame.Rect(box)

    def cycle_button(self, layer, box, label, *, pressed=False):
        """A value button (Start In, the browser's Up...): HD's orange, a rounded box as the back button is (owner,
        2026-10-30), its label in white."""
        x, y, w, h = box
        stops = ORANGE if not pressed else tuple(tuple(round(c * .8) for c in color) for color in ORANGE)
        layer.blit(self.gradient_box(box, stops, 10), (round(x * S), round(y * S)))
        self.rect(layer, tuple(round(c * .75) for c in stops[-1]), box, 10, 2)
        text = self.font(CYCLE_POINTS).render(label, True, (255, 255, 255))
        layer.blit(text, text.get_rect(center=(round((x + w / 2) * S), round((y + h / 2 - 1) * S))))

    def speaker(self, layer, x, middle, waves):
        """A slider's speaker (HD's are art, resource 155): a body and cone, and `waves` sound arcs."""
        body = [(x, middle - 5), (x + 6, middle - 5), (x + 14, middle - 12), (x + 14, middle + 12), (x + 6, middle + 5),
                (x, middle + 5)]
        pygame.draw.polygon(layer, GRAY, [(round(px * S), round(py * S)) for px, py in body])
        for wave in range(waves):
            r = 7 + wave * 6
            rect = pygame.Rect(round((x + 12 - r) * S), round((middle - r) * S), round(2 * r * S), round(2 * r * S))
            pygame.draw.arc(layer, GRAY, rect, -0.8, 0.8, max(1, round(2 * S)))

    def slider(self, layer, top, value):
        """A volume row's control line, as HdPauseMenu.slider draws it with shape speakers."""
        middle = top + 86
        self.speaker(layer, 112, middle, 0)
        self.speaker(layer, 618, middle, 2)
        left, right = 143, 603
        self.rect(layer, (74, 132, 213), (left, middle - 3, right - left, 6), 3)
        self.rect(layer, (150, 185, 235), (left, middle - 3, right - left, 2), 1)
        knob = round((left + (right - left) * value) * S)
        pygame.draw.circle(layer, (214, 214, 214), (knob, round(middle * S)), round(10.5 * S))
        pygame.draw.circle(layer, (160, 160, 160), (knob, round(middle * S)), round(10.5 * S), S)
        pygame.draw.circle(layer, (245, 245, 245), (knob, round((middle - 2) * S)), round(6 * S))
        return pygame.Rect(left - 10, middle - 22, right - left + 20, 44)

    def back_button(self, layer, bottom, *, lit=False):
        lit = lit or self.pressed in (('back',), ('pause_back',))
        left, top = PANEL_X + BACK[0], bottom - BACK[1] - BUTTON_SIZE[1]
        return self.button(layer, (left, top, *BUTTON_SIZE), orange=False, lit=lit, arrow=True)

    def wrap(self, text, points, width):
        """`text` as lines of at most `width` points, broken at spaces."""
        font, lines = self.font(points), []
        for paragraph in text.split('\n'):
            line = ''
            for word in paragraph.split(' '):
                trial = f'{line} {word}' if line else word
                if line and font.size(trial)[0] / S > width:
                    lines.append(line)
                    line = word
                else:
                    line = trial
            lines.append(line)
        return lines


# The HD menu strings the pause menu's layout reads (SHS HD's own words, its resource 15), for a card drawn with no
# SHS HD app at hand.
OPTION_STRINGS = {8: 'Pause', 9: 'Main Menu', 10: 'Options', 12: 'Game Music', 13: 'Music Volume', 14: 'Sound FX',
                  15: 'Sound FX Volume', 20: 'Resume', 120: 'Help & About'}
LANGUAGE_NAMES = {'en': 'English', 'fr': 'Français', 'it': 'Italiano', 'de': 'Deutsch', 'es': 'Español'}
# The chooser's Library page rows that act on each game's library in turn (AppOptions' methods of these names).
BOTH_GAMES_ACTIONS = ('library_info', 'storage', 'verify_library', 'rebuild_previews', 'rebuild_hd_art', 'back_up',
                      'reset_names', 'delete_saves')
# The Episodes page's lists (application.EPISODE_CHOICES): from the chooser, the game is picked first.
EPISODE_LISTS = ('delete_episodes', 'export_episodes', 'reset_trees')
SHORT_TITLES = {'shs': 'SHS', 'cod': 'CoD'}     # a backup's row names its game short
SLIDER = (143, 460)                     # a volume slider's track: its left and width in points (HdShell's)
# Options only one game offers are not listed before a game is chosen (owner, 2026-10-30): SHS's High School Story ad
# intros and store plugs (CodPauseMenu leaves both out), its New Rules Hi-Res Portraits (TRANSLATED_PORTRAIT_ART) and
# translated Episode Titles (no CoD episode has one). Each game's own Options still has them.
ONE_GAME_OPTIONS = ('skip_ad_intros', 'skip_upsell_intros', 'hires_portraits', 'title_language')


class AppOptionsMenu(AppCard):
    """The pause menu's Options pages on the app's card."""
    main_menu = True

    def strings(self):
        return [OPTION_STRINGS.get(index, '') for index in range(273)]


class AppOptions:
    """The chooser's Options (owner, 2026-10-30): the shared Options (both games share them, menu.SHARED_PREFERENCES)
    as the HD main menu shows them, from the app's settings.json, since no library is open here. The next game opened
    takes them: the shared copy wins over its player.json. Input as HdShell's pause menu takes it: taps, a slider's
    drag, the wheel, keys and a controller (focus); a question or a notice is a window over it (`ask`)."""

    def __init__(self, app):
        self.app = app
        self.menu = AppOptionsMenu()
        self.pressed = self.drag = None
        self.buttons = []
        self.ask = None                 # (title, text, labels, actions): a window over the page
        self.next_screen = None         # the page to open on entering (a folder chosen from Data Management)
        self.next_ask = None            # and the window to show there
        self.clock = None

    def enter(self):
        """Options appears: on its list, or on the page (and with the notice) asked for (`next_screen`, `next_ask`)."""
        self.menu.reset()
        self.menu.state.screen = self.next_screen or 'options'
        self.pressed = self.drag = None
        self.ask, self.next_screen, self.next_ask = self.next_ask, None, None

    def values(self):
        from .menu import preference_defaults, shared_preference
        saved = {key: value for key, value in self.app.settings.preferences.items() if shared_preference(key, value)}
        return dict(preference_defaults(), **saved)

    def settings(self):
        """What the pages offer, as HdShell.settings has it for the main menu (less a library's own rows)."""
        from . import graphics
        from .desktop_pause_hd import CONFIRM_NAMES, GRID_CONTROLS_NAMES, START_IN_NAMES
        v, app = self.values(), self.app
        settings = {key: v[key] for key in ('vibration', 'music', 'sound', 'choice_hints', 'skip_minigames',
                                            'skip_ad_intros', 'skip_upsell_intros', 'autoplay', 'disable_choice_timer',
                                            'hd_backdrop', 'hires_portraits', 'skip_sound_prompt')}
        settings.update(music_volume=v['music_volume'] / 100, sound_volume=v['sound_volume'] / 100,
                        title_language=LANGUAGE_NAMES.get(v['title_language'], v['title_language']),
                        check_updates=app.settings.check_for_updates,
                        start_in=START_IN_NAMES[app.settings.start_in], reset_settings=True)
        if graphics.supports_vibration():
            settings['device_vibration'] = v['device_vibration']
        if graphics.controller_connected():
            settings['controller_confirm'] = CONFIRM_NAMES[v['controller_confirm']]
            settings['grid_controls'] = GRID_CONTROLS_NAMES[v['grid_controls']]
            settings['controller_vibration'] = graphics.vibration_source() == 'controller'
        if getattr(app, 'file_picker', None) is None:
            for key in ('backup_folder', 'export_folder'):
                settings[key] = app.folder_label(key)
        # Data Management for both games (owner, 2026-10-30): what has a library to act on.
        games = app.games_with_libraries()
        if games:
            for key in BOTH_GAMES_ACTIONS + ('restore',) + EPISODE_LISTS:
                settings[key] = True
            for game in games:
                settings[f'delete_library_{game}'] = True
            if len(games) > 1:
                settings['delete_libraries'] = True
        return {key: value for key, value in settings.items() if key not in ONE_GAME_OPTIONS}

    def draw(self, layer):
        now = time.monotonic() * 1000
        if self.clock is not None:
            self.menu.advance(now - self.clock)
        self.clock = now
        self.menu.pressed = self.pressed
        page, self.buttons = self.menu.layout(self.settings())
        layer.blit(page, (0, 0))

    # -- what a row does ---------------------------------------------------------------------------------------

    def set(self, key, value):
        self.app.settings.set_preferences({key: value})

    def activate(self, command):
        from .settings import START_IN
        from .languages import TITLE_LANGUAGES
        kind, app, v = command[0], self.app, self.values()
        if kind == 'pause_open':
            self.menu.open(command[1])
        elif kind == 'pause_back':
            if self.menu.back():
                app.back()                              # past Options: back to the chooser
        elif kind == 'pause_toggle':
            key = command[1]
            if key == 'check_updates':
                app.set_update_check(not app.settings.check_for_updates)
            else:
                self.set(key, not v[key])
                if key == 'device_vibration' and not v[key]:
                    from . import graphics
                    graphics.vibrate()
        elif kind == 'pause_cycle':
            key = command[1]
            if key == 'start_in':
                app.settings.set_start_in(START_IN[(START_IN.index(app.settings.start_in) + 1) % len(START_IN)])
            elif key == 'title_language':
                self.set(key, TITLE_LANGUAGES[(TITLE_LANGUAGES.index(v[key]) + 1) % len(TITLE_LANGUAGES)])
            elif key == 'controller_confirm':
                self.set(key, 'east' if v[key] == 'south' else 'south')
                app.sync_controller()
            elif key == 'grid_controls':
                self.set(key, 'hold' if v[key] == 'tap' else 'tap')
            elif key in ('backup_folder', 'export_folder'):
                app.choose_folder(key)
        elif kind == 'pause_action' and command[1] in BOTH_GAMES_ACTIONS:
            getattr(self, command[1])()
        elif kind == 'pause_action' and command[1] in EPISODE_LISTS:
            self.pick_game(command[1])
        elif kind == 'pause_action' and command[1].startswith('pick:'):
            _, action, game = command[1].split(':')
            app.app_screens.open_choice(action, game)
        elif kind == 'pause_action' and command[1] == 'restore':
            self.show_backups()
        elif kind == 'pause_action' and command[1].startswith('restore:'):
            self.restore_backup(command[1])
        elif kind == 'pause_action' and command[1] == 'delete_libraries':
            self.confirm_delete(app.games_with_libraries())
        elif kind == 'pause_action' and command[1].startswith('delete_library_'):
            self.confirm_delete([command[1][len('delete_library_'):]])
        elif kind == 'pause_action' and command[1] == 'reset_settings':
            self.ask = ('Reset Settings?', 'Every option (both games share them) goes back to its default: Start In, '
                        'Check for Updates and the chosen folders too. Saves and names stay.', ('No', 'Reset'),
                        (None, self.reset))

    def reset(self):
        """Reset Settings, with no library open: the shared options at their defaults, Start In, the chosen folders
        and Check for Updates too (Application.reset_settings does the same with one)."""
        from .menu import preference_defaults
        from .settings import FOLDERS
        app = self.app
        app.settings.set_preferences(preference_defaults())
        app.settings.set_start_in('auto')
        for key in FOLDERS:
            if getattr(app.settings, key, None) is not None:
                app.settings.set_folder(key, None)
        if not app.settings.check_for_updates:
            app.set_update_check(True)
        app.sync_controller()
        self.notice('Settings Reset', 'Every option is back to its default.')

    def notice(self, title, text):
        self.ask = (title, text, ('OK',), (None,))

    def confirm(self, title, text, verb, action):
        self.ask = (title, text, ('No', verb), (None, action))

    # -- Data Management for both games (owner, 2026-10-30) ---------------------------------------------------

    def each(self, title, work, done):
        """`work(library, state)` for each game that has a library, opened for it, off the UI thread under the busy
        card; then `done([(game, result)])` on the UI thread."""
        app = self.app

        def job(_):
            results = []
            for game in app.games_with_libraries():
                app.progress_text = GAMES[game].TITLE
                with app.opened_library(game) as (library, state):
                    results.append((game, work(library, state)))
            return results
        app.start_data_job(title, job, done)

    def page(self, screen, title, text):
        """A text page under Library (the pause menu's own, scrolled as Help's are)."""
        self.menu.show_text(screen, title, text, 'data:library')

    def library_info(self):
        self.each('Reading libraries', lambda library, state: self.app.library_info(library, state),
                  lambda results: self.page('data:info', 'Library Info',
                                            '\n\n\n'.join(text for _, text in results)))

    def storage(self):
        from .application import disk_size, size_text

        def measure(library, state):
            text = self.app.storage_text(library).split('\n')
            return [line for line in text if line and not line.startswith(('Total', 'Free'))], disk_size(library.directory)

        def done(results):
            import shutil
            folder = self.app.library_path(results[0][0]).parent if results else None
            lines = []
            for game, (rows, total) in results:
                lines += [GAMES[game].TITLE, *rows, f'Total: {size_text(total)}', '']
            if len(results) > 1:
                lines.append(f'Both games: {size_text(sum(total for _, (_, total) in results))}')
            if folder is not None:
                lines.append(f'Free on this drive: {size_text(shutil.disk_usage(folder).free)}')
            self.page('data:storage', 'Storage', '\n'.join(lines))
        self.each('Measuring storage', measure, done)

    def verify_library(self):
        def done(results):
            problems = [(game, result) for game, result in results if result[1] or result[2]]
            restored = sum(result[3] for _, result in results)
            again = f' {restored} built-in episode{"s were" if restored != 1 else " was"} restored.' if restored else ''
            if not problems:
                counts = ' and '.join(f'{result[0]} of {GAMES[game].TITLE}' for game, result in results)
                self.notice('Libraries Verified', f'All {counts} files are intact.{again}')
                return
            lines = []
            for game, (checked, missing, damaged, _) in results:
                lines += [GAMES[game].TITLE, f'{checked} files checked.']
                lines += [f'Missing: {name}' for name in missing] + [f'Damaged: {name}' for name in damaged] + ['']
            lines.append('Add Episodes (in that game) restores an episode when given its file again; a damaged file '
                         'was removed. A missing or damaged app comes back only by importing the game again.' + again)
            self.page('data:verify', 'Verify Library', '\n'.join(lines))
        self.confirm('Verify Libraries?', 'Every file of both games is checked against its checksum, which can take a '
                     'few minutes. A damaged episode\'s file is removed: adding the episode again restores it.', 'Verify',
                     lambda: self.each('Verifying libraries', lambda library, state: self.app.verify_library(library),
                                       done))

    def rebuild_previews(self):
        def done(results):
            self.notice('Previews Rebuilt', ' '.join(
                f'{GAMES[game].TITLE}: {made} drawn again.' for game, made in results))
        self.confirm('Rebuild Previews?', 'Every episode preview of both games is drawn again from its title card, which '
                     'can take a few minutes.', 'Rebuild',
                     lambda: self.each('Drawing previews', lambda library, state: self.app.rebuild_previews(library),
                                       done))

    def rebuild_hd_art(self):
        app = self.app

        def work(library, state):
            return app.rebuild_hd_art(library) if app.hd_art_offered(library) else None

        def done(results):
            built = [f'{GAMES[game].TITLE}: {count} HD pictures.' for game, count in results if count is not None]
            self.notice('HD Art Rebuilt', ' '.join(built) or 'Neither library has HD art to build.')
        self.confirm('Rebuild HD Art?', 'The HD pictures both games show in standard episodes are found again in your HD '
                     'files (Surviving High School first: Cause of Death takes its own from it), which can take a few '
                     'minutes.', 'Rebuild', lambda: self.each('Building HD art', work, done))

    # -- Episodes -----------------------------------------------------------------------------------------------

    def pick_game(self, action):
        """Delete / Export Episodes and Reset Decision Tree from the chooser (owner, 2026-10-30): the game first (one
        list per game, not one long list of both), then its own episode list."""
        games = self.app.games_with_libraries()
        if len(games) == 1:
            self.app.app_screens.open_choice(action, games[0])
            return
        titles = {'delete_episodes': 'Delete Episodes', 'export_episodes': 'Export Episodes',
                  'reset_trees': 'Reset Decision Tree'}
        self.menu.show_rows('data:pick', titles[action], [(f'pick:{action}:{game}', GAMES[game].TITLE)
                                                          for game in games], 'data:episodes')

    # -- Progress -----------------------------------------------------------------------------------------------

    def titles(self):
        """The games that have a library, as a sentence names them ("Surviving High School and Cause of Death")."""
        return ' and '.join(GAMES[game].TITLE for game in self.app.games_with_libraries())

    def back_up(self):
        """Back Up Progress: one file for both games (the default: Enter takes it), or a file for each."""
        self.ask = ('Back Up Progress', f'The saved games, Decision Trees and names of {self.titles()}: in one file, '
                    'or a file for each game?', ('Combined', 'Separate'),
                    (lambda: self.start_back_up(True), lambda: self.start_back_up(False)))

    def start_back_up(self, combined):
        import shutil
        import tempfile
        from datetime import datetime
        from .launcher import APP_NAME
        from .progress_bundle import write_bundle, write_set
        app = self.app

        def job(_):
            made, parts = [], {}
            folder = Path(tempfile.mkdtemp(prefix='shshd-backup-'))
            try:
                for game in app.games_with_libraries():
                    app.progress_text = GAMES[game].TITLE
                    with app.opened_library(game) as (library, state):
                        player = app.player_data(state)
                        if combined:
                            titles = {record['id']: record['titles'][0] for record in library.episodes}
                            parts[game] = folder / f'{game}.zip'
                            write_bundle(library.directory, game, player, titles, parts[game])
                        else:
                            made.append(app.back_up_progress(library, player)[0])
                if combined:
                    stamp = datetime.now().strftime('%Y-%m-%d %H%M%S')
                    target = app.backup_folder() / f'{APP_NAME} {stamp} (both games).zip'
                    write_set(target, parts)
                    made.append(target)
            finally:
                shutil.rmtree(folder, ignore_errors=True)
            return made

        def done(made):
            self.notice('Progress Backed Up', f'Saved to {app.folder_text(made[0].parent)}, as '
                        + ' and '.join(f'"{path.stem}"' for path in made) + '.')
        app.start_data_job('Backing up progress', job, done)

    def backups(self):
        """Every backup in the backups folder (and the default one, when another was chosen), a game's or both
        games', newest first: [(file, manifest)]."""
        from .progress_bundle import BundleError, read_backup
        app = self.app
        folders = [app.backup_folder()]
        if app.chosen_folder('backup_folder') is not None:
            folders.append(app.user_folder('Backups'))
        found, seen = [], set()
        for folder in folders:
            for path in sorted(folder.glob('*.zip')) if folder.is_dir() else ():
                if path.resolve() in seen:
                    continue
                seen.add(path.resolve())
                try:
                    found.append((path, read_backup(path)))
                except BundleError:
                    continue
        return sorted(found, key=lambda item: (item[1].get('created', ''), item[0].stat().st_mtime_ns), reverse=True)

    def backup_label(self, manifest):
        when = self.app.backup_when(manifest, short=True)
        games = manifest['games']
        if manifest.get('note'):
            return f'{when} ({manifest["note"]})'
        what = 'Both' if len(games) > 1 else SHORT_TITLES.get(games[0], games[0])   # (short: the row is one line)
        count = sum(manifest.get('saved', {}).values())
        return f'{when}: {what}, {count} save{"s" if count != 1 else ""}'

    restore_choices = {}

    def show_backups(self):
        from .application import RESTORE_ROWS
        backups = self.backups()[:RESTORE_ROWS]
        if not backups:
            self.notice('No Backups', f'Back Up Progress makes one, in {self.app.folder_text(self.app.backup_folder())}.')
            return
        self.restore_choices = {f'restore:{index}': item for index, item in enumerate(backups)}
        rows = [(key, self.backup_label(manifest)) for key, (_, manifest) in self.restore_choices.items()]
        self.menu.show_rows('data:restore', 'Restore Progress', rows, 'data:progress')

    def restore_backup(self, key):
        """A backup's row: each game it holds that has a library here is backed up as it is now, then restored."""
        import shutil
        import tempfile
        from .progress_bundle import bundle_options, restore_bundle, set_member
        app = self.app
        path, manifest = self.restore_choices[key]
        have = app.games_with_libraries()
        held = [game for game in GAMES if game in manifest['games']]       # in the games' own order, SHS first
        games = [game for game in held if game in have]
        missing = [GAMES[game].TITLE for game in held if game not in have]
        if not games:
            self.notice('Nothing to Restore', f'This backup holds {" and ".join(missing)}, which has no library here. '
                        'Import the game first.')
            return
        titles = ' and '.join(GAMES[game].TITLE for game in games)
        current = self.values()

        def job(_):
            folder = Path(tempfile.mkdtemp(prefix='shshd-restore-'))
            results, options = [], {}
            try:
                for game in games:
                    app.progress_text = GAMES[game].TITLE
                    bundle = set_member(path, game, folder)
                    restored_options = bundle_options(bundle) or {}
                    with app.opened_library(game) as (library, state):
                        kept = {key: current[key] for key in restored_options if key in current}
                        app.back_up_progress(library, app.player_data(state), note='before restore',
                                             options=kept or None)
                        restored, player = restore_bundle(library.directory, bundle, game)
                        app.restore_player(state, player)
                        here = {record['id'] for record in library.episodes}
                    saved = [entry.get('id') for entry in restored.get('saved', ())]
                    results.append((game, sum(1 for key in saved if key in here), sum(1 for key in saved if key not in here)))
                    options.update(restored_options)
            finally:
                shutil.rmtree(folder, ignore_errors=True)
            return results, options

        def done(result):
            from .menu import shared_preference
            results, options = result
            accepted = {key: value for key, value in options.items() if shared_preference(key, value)}
            if accepted:
                app.settings.set_preferences(accepted)
            lines = [f'{GAMES[game].TITLE}: {restored} saved game{"s" if restored != 1 else ""} restored'
                     + (f', {waiting} more for episodes it lacks' if waiting else '') + '.'
                     for game, restored, waiting in results]
            if missing:
                lines.append(f'{" and ".join(missing)} has no library here and was skipped.')
            self.notice('Progress Restored', ' '.join(lines))

        when = app.backup_when(manifest)
        skipped = f' {" and ".join(missing)} has no library here and is skipped.' if missing else ''
        self.confirm('Restore Progress?', f'The saved games, Decision Trees and names of {titles} will be replaced by '
                     f'the backup\'s from {when}. The current progress is backed up first.{skipped}', 'Restore',
                     lambda: app.start_data_job('Restoring progress', job, done))

    def reset_names(self):
        def done(results):
            self.notice('Names Reset', f'{self.titles()} will ask for the names again.')
        self.confirm('Reset Names?', f'The names you typed in {self.titles()} will be forgotten: new games ask for them '
                     'again (or take their defaults). Saved games keep the names they were saved with.', 'Reset',
                     lambda: self.each('Resetting names', lambda library, state: self.app.reset_names(state), done))

    def delete_saves(self):
        def done(results):
            self.notice('Saves Deleted', ' '.join(message for _, (_, message) in results))
        self.confirm('Delete All Saves?', f'Every saved game of {self.titles()} will be deleted, with the Decision '
                     'Trees\' saved scenes. Episodes, names and settings stay.', 'Delete',
                     lambda: self.each('Deleting saves', lambda library, state: self.app.delete_all_saves(library, state),
                                       done))

    def confirm_delete(self, games):
        """Delete a library (or both): asked twice, as each game's own Delete Library is."""
        from .application import remove_library
        titles = ' and '.join(GAMES[game].TITLE for game in games)
        which = 'both libraries' if len(games) > 1 else 'its library'

        def delete():
            # What earlier jobs left cached of these libraries (a preview's fonts from a library's fonts/ folder stay
            # open while cached) goes first, as letting a library go does.
            import gc
            from . import episode_thumbnails
            episode_thumbnails.release_game_caches()
            gc.collect()
            left = sum(remove_library(self.app.library_path(game)) for game in games)
            self.notice('Libraries Deleted' if len(games) > 1 else 'Library Deleted',
                        f'The {"libraries" if len(games) > 1 else "library"} of {titles} '
                        f'{"were" if len(games) > 1 else "was"} deleted.'
                        + (f' {left} files were in use and stay in their folder.' if left else ''))

        self.confirm('Delete Both Libraries?' if len(games) > 1 else 'Delete Library?',
                     f'Everything {titles} keep{"" if len(games) > 1 else "s"} in this app will be deleted: episodes, '
                     f'saved games, Decision Trees, names, previews and HD art. The files you imported from stay where '
                     f'they are. Back Up Progress first to keep your saves.', 'Delete',
                     lambda: self.confirm('Delete Everything?', f'This cannot be undone. To play {titles} again, import '
                                          f'{"their" if len(games) > 1 else "its"} files again.', 'Delete', delete))

    def step_back(self):
        """Escape / Back: close the window, else go up a page; False once past the list (Options is left)."""
        if self.ask is not None:
            self.ask = None
            return True
        return not self.menu.back()

    def set_volume(self, which, value):
        self.set('music_volume' if which == 'music' else 'sound_volume', round(min(1., max(0., value)) * 100))

    # -- input -------------------------------------------------------------------------------------------------

    def event(self, event, point):
        """A window event (`point`: the pointer in frame points, or None)."""
        if self.ask is not None:
            return self.ask_event(event, point)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.menu.state.focus = None                # the pointer takes over from the keys
            self.pressed = next((command for rect, command in reversed(self.buttons) if rect.collidepoint(point)), None)
            if self.pressed is not None and self.pressed[0] == 'pause_slider':
                self.drag = ('slider', self.pressed[1])
                self.set_volume(self.pressed[1], (point[0] - SLIDER[0]) / SLIDER[1])
            elif self.pressed is not None and self.pressed[0] == 'pause_scroll':
                self.drag = ('scroll', self.menu.state.scroll, point[1])
        elif event.type == pygame.MOUSEMOTION and self.drag is not None:
            if self.drag[0] == 'slider':
                self.set_volume(self.drag[1], (point[0] - SLIDER[0]) / SLIDER[1])
            else:
                state = self.menu.state
                state.scroll = min(state.max_scroll, max(0., self.drag[1] - (point[1] - self.drag[2])))
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            pressed, drag, self.pressed, self.drag = self.pressed, self.drag, None, None
            if pressed is not None and drag is None and any(rect.collidepoint(point) and command == pressed
                                                            for rect, command in self.buttons):
                self.app._click_sound()
                self.activate(pressed)
        elif event.type == pygame.MOUSEWHEEL:
            state = self.menu.state
            state.scroll = min(state.max_scroll, max(0., state.scroll - event.y * 40))
        elif event.type == pygame.KEYDOWN:
            command = self.menu.key(event.key)
            if command is not None and command[0] == 'pause_volume':
                self.set_volume(command[1], self.settings()[command[1] + '_volume'] + command[2])
            elif command is not None:
                self.activate(command)
        return True

    def ask_event(self, event, point):
        """The window's buttons; Enter takes the first (No, or OK), Escape closes it."""
        title, text, labels, actions = self.ask
        chosen = None
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE,
                                                          pygame.K_ESCAPE):
            chosen = 0
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.pressed = next((command for rect, command in self.buttons if rect.collidepoint(point)), None)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            pressed, self.pressed = self.pressed, None
            hit = next((command for rect, command in self.buttons if rect.collidepoint(point)), None)
            if hit is not None and hit == pressed:
                chosen = hit[1]
        if chosen is not None:
            self.ask = None
            self.app._click_sound()
            if actions[chosen] is not None:
                actions[chosen]()
        return True


class ChooserList:
    """An episode list of the chooser's Episodes page (owner, 2026-10-30): one game's own list (desktop_episode_list_hd,
    its rows and tick boxes) on the app's card over the kiwi, its library opened for it; no game menu opens."""

    def __init__(self, app, kind, game, card):
        from .application import EPISODE_CHOICES
        from .content import ContentLibrary
        from .desktop_episode_list_hd import EpisodeChoice
        from .episode_picker import PickerModel
        from .menu import MenuState
        self.app, self.kind, self.game = app, kind, game
        self.library = ContentLibrary(app.library_path(game))
        try:
            state = MenuState(self.library, shared=app.settings)
            self.allowed = app.choice_allowed(kind, self.library)
            if game == 'cod':
                model = PickerModel(self.library)
            else:                                       # as Application.ensure_picker builds SHS's
                from .desktop_menu import MenuRenderer
                strings = MenuRenderer(self.library).strings
                model = PickerModel(self.library, mega_label=strings[82], novel_label=strings[302],
                                    title_language=state.title_language)
            self.picker = app.picker_classes(self.library)[1](self.library, model, lambda record: None)
            self.picker.card = card
            self.picker.show_restore = False
            self.picker.enter(None)
            title, verb = EPISODE_CHOICES[kind][:2]
            self.picker.choosing = EpisodeChoice(title, verb, self.allowed)
        except Exception:
            self.library.close()
            raise

    def close(self):
        from . import episode_thumbnails
        self.library.close()
        episode_thumbnails.release_game_caches()        # its menus' art and fonts go with it


class AppScreens:
    """Draws APP_SCREENS and their cards into an HD canvas; `buttons` are [(rect in frame points, command)]."""

    choice = None                       # the chooser's open episode list (ChooserList), on screen 'choice'

    def open_choice(self, kind, game):
        """The chooser's Episodes page: `game`'s list to choose from (a game with none to offer says so instead)."""
        from .application import EPISODE_CHOICES
        from .content import ContentError
        try:
            choice = ChooserList(self.app, kind, game, self.card)
        except (ContentError, OSError) as error:
            self.options.notice('Cannot Open', str(error))
            return
        if not choice.allowed:
            choice.close()
            self.options.notice(*EPISODE_CHOICES[kind][2])
            return
        self.choice = choice
        self.app.show('choice')

    def leave_choice(self, ask=None):
        """Back to the chooser's Episodes page (with `ask` there: the action's question, or its notice)."""
        choice, self.choice = self.choice, None
        if choice is not None:
            choice.close()
        self.options.next_screen, self.options.next_ask = 'data:episodes', ask
        self.app.history = ['games']
        self.app.show('options', remember=False)

    def choice_event(self, event):
        """The list's input, as the app's picker takes it: taps and drags, the wheel, keys; Back and the verb."""
        app, picker = self.app, self.choice.picker
        command = None
        if event.type == pygame.KEYDOWN:
            command = picker.key(event.key)
        elif event.type == pygame.MOUSEWHEEL:
            picker.wheel(event.x, event.y, app.picker_point(pygame.mouse.get_pos()))
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            picker.pointer_down(app.picker_point(event.pos))
        elif event.type == pygame.MOUSEMOTION and event.buttons[0]:
            picker.pointer_move(app.picker_point(event.pos))
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            command = picker.pointer_up(app.picker_point(event.pos))
        if command == ('back',):
            app._click_sound()
            self.leave_choice()
        elif command == ('act',) and picker.choosing.chosen:
            app._click_sound()
            self.choice_act()
        return True

    def choice_act(self):
        """The list's verb: back on the Episodes page, Delete and Reset ask there first; the job opens the library for
        itself, and its notice shows there."""
        from .application import EPISODE_CHOICES
        app, choice = self.app, self.choice
        kind, game, chosen = choice.kind, choice.game, set(choice.picker.choosing.chosen)
        count = f'{len(chosen)} episode{"s" if len(chosen) != 1 else ""}'

        def run():
            def job(_):
                with app.opened_library(game) as (library, state):
                    return getattr(app, kind)(library, chosen)
            app.start_data_job(EPISODE_CHOICES[kind][3], job, lambda result: self.options.notice(*result))
        title = GAMES[game].TITLE
        if kind == 'delete_episodes':
            ask = ('Delete Episodes?', f'{count} will be deleted from {title}, with their saved games and Decision '
                   'Trees. Add Episodes brings one back from its file.', ('No', 'Delete'), (None, run))
        elif kind == 'reset_trees':
            ask = ('Reset Decision Tree?', f'The Decision Tree of {count} will be cleared, with its saved scenes. Saved '
                   'games stay.', ('No', 'Reset'), (None, run))
        else:
            ask = None
        self.leave_choice(ask)
        if ask is None:
            run()

    def draw_choice(self, app, layer):
        layer.blit(self.choice.picker.draw(backdrop=False), (0, 0))

    def __init__(self, app=None):
        self.card = AppCard()
        self.buttons = []
        self.icons = {}                 # game -> (library.json's stamp, its app icon at GAME_ICON, or None)
        self.last = None                # (screen, its last canvas without cards)
        self.slide = None               # (direction, previous canvas, start ms)
        self.options = AppOptions(app) if app is not None else None
        self.app = app

    @staticmethod
    def handles(app):
        """Whether the app's screen is one of these: APP_SCREENS, Options with no library open (the chooser's), and
        the file browser (in either dress)."""
        return (app.screen in APP_SCREENS or app.screen in ('browser', 'choice')
                or (app.screen == 'options' and app.library is None))

    browser_scroll = 0.0                # the file list's scroll, in points
    browser_folder = None               # the folder it was scrolled in (a new one starts at the top)
    browser_area = None                 # the list's rectangle (points), for scrolling

    # -- the frame --------------------------------------------------------------------------------------------

    @lru_cache(maxsize=1)
    def backdrop(self):
        """The dark gradient with the kiwi at the top: it stays put under every page (a tall card covers it)."""
        size = (FRAME[0] * S, FRAME[1] * S)
        surface = pygame.Surface(size)
        top, bottom = BACKDROP
        for y in range(size[1]):
            f = y / (size[1] - 1)
            surface.fill(tuple(round(a + (b - a) * f) for a, b in zip(top, bottom)), (0, y, size[0], 1))
        icon = icon_surface(KIWI * S)
        surface.blit(icon, ((size[0] - icon.get_width()) // 2, KIWI_Y * S))
        return surface

    def draw(self, app):
        """The screen and, over it, a busy / message / update card; returns the canvas."""
        self.card.pressed = app.pressed
        self.buttons = []
        screen = app.screen
        if screen == 'options' and (self.last is None or self.last[0] != 'options'):
            self.options.enter()                        # Options opens on its list (or the page asked for)
        # The pages are drawn on a clear layer over a backdrop that stays put (owner, 2026-10-30): the gradient with the
        # kiwi, which only a card over it hides; a library's browser has its game's main menu there instead.
        canvas = (self.game_backdrop(app) if screen == 'browser' else None) or self.backdrop().copy()
        layer = pygame.Surface(canvas.get_size(), pygame.SRCALPHA)
        getattr(self, 'draw_' + screen)(app, layer)
        now = time.monotonic() * 1000
        if self.last is not None and self.last[0] != screen:
            self.slide = (getattr(app, 'transition_direction', 1), self.last[1], now)
        self.last = (screen, layer)
        if self.slide is not None:
            direction, previous, start = self.slide
            progress = ease_in_out(min(1., (now - start) / SLIDE_MS))
            if progress >= 1:
                self.slide = None
            else:
                width = FRAME[0] * S
                offset = round(width * progress) * direction
                canvas.blit(previous, (-offset, 0))
                canvas.blit(layer, (width * direction - offset, 0))
                self.buttons = []                       # nothing takes a tap while it slides
        if self.slide is None:
            canvas.blit(layer, (0, 0))
        if app.busy or app.message or app.update_prompt is not None:
            self.buttons = []
            self.draw_card(app, canvas)
        if getattr(app, 'focus', None) == 'buttons' and self.buttons:
            rect = self.buttons[app.focus_index % len(self.buttons)][0]
            self.card.rect(canvas, FOCUS, rect.inflate(8, 8), 12, 3)
        return canvas

    # -- pieces -----------------------------------------------------------------------------------------------

    def header(self, title):
        """The card's header height: taller for a title that wraps ("Surviving High School"), as HD's lists do."""
        return HEADER + 40 if len(self.card.title_lines(title)) > 1 else HEADER

    def card_frame(self, layer, top, title, height, foot):
        """The card at `top`: its header, `height` body points of page background, then a footer `foot` high (a
        short closing band when nothing sits in it); returns (body top, card bottom)."""
        header = self.header(title)
        bottom = top + header + height + foot
        body = self.card.panel(layer, top, bottom, title, header=header)
        self.card.rect(layer, self.card.see_through(ROW_BACKGROUND), (PANEL_X + BORDER, body, PANEL_W - 2 * BORDER, height))
        self.card.rect(layer, SEPARATOR, (PANEL_X + BORDER, body, PANEL_W - 2 * BORDER, 1))
        if foot == FOOT:
            self.card.rect(layer, SEPARATOR, (PANEL_X + BORDER, bottom - FOOT, PANEL_W - 2 * BORDER, 1))
        return body, bottom

    def page(self, layer, title, height, *, back=True):
        """A card of `height` body points under `title`, below the kiwi; returns (body top, card bottom)."""
        foot = FOOT if back else SHORT_FOOT
        total = self.header(title) + height + foot
        top = max(KIWI_Y + KIWI + 20, (FRAME[1] + KIWI_Y + KIWI - total) / 2)
        body, bottom = self.card_frame(layer, top, title, height, foot)
        if back:
            self.buttons.append((self.card.back_button(layer, bottom), ('back',)))
        return body, bottom

    def text(self, layer, text, y, *, points=TEXT_PT, color=GRAY, center=False, width=PANEL_W - 70):
        """Wrapped text from `y`; returns the y after it."""
        for line in self.card.wrap(text, points, width):
            x = 384 if center else PANEL_X + 35
            self.card.text(layer, line, x, y, points, color, center=center)
            y += TEXT_PITCH * points / TEXT_PT
        return y

    def text_height(self, text, points=TEXT_PT, width=PANEL_W - 70):
        return len(self.card.wrap(text, points, width)) * TEXT_PITCH * points / TEXT_PT

    def action(self, layer, top, label, command, index):
        """An action row (HD's Data Management rows): the whole row is the button."""
        lit = self.card.pressed == command
        self.card.row(layer, top, label, background=self.card.row_color(index), lit=lit)
        rect = pygame.Rect(PANEL_X + BORDER, top, PANEL_W - 2 * BORDER, ROW)
        self.chevron(layer, rect)
        self.buttons.append((rect, command))
        return top + ROW

    def chevron(self, layer, rect, color=LABEL_BLUE):
        x, y = rect.right - 34, rect.centery
        points = [(x - 7, y - 12), (x + 5, y), (x - 7, y + 12)]
        pygame.draw.lines(layer, color, False, [(round(px * S), round(py * S)) for px, py in points], 3 * S)

    def icon(self, app, key):
        """A game's own app icon at GAME_ICON points (from its library), or None before it is imported."""
        path = app.library_path(key) / 'library.json'
        try:
            stamp = path.stat().st_mtime_ns
        except OSError:
            return None
        cached = self.icons.get(key)
        if cached is None or cached[0] != stamp:
            image = None
            try:
                from .content import ContentLibrary
                with ContentLibrary(path.parent) as library:
                    image = game_icon_surface(library)
            except Exception:                           # an unreadable library still lists its game, iconless
                image = None
            if image is not None:
                size = round(GAME_ICON * S)
                image = pygame.transform.smoothscale(image.convert_alpha(), (size, size))
                mask = pygame.Surface((size, size), pygame.SRCALPHA)
                pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, size, size), border_radius=round(18 * S))
                image.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            cached = self.icons[key] = (stamp, image)
        return cached[1]

    # -- screens ----------------------------------------------------------------------------------------------

    def draw_games(self, app, layer):
        card = self.card
        note = 'Each game keeps its own episodes, saves and library.'
        height = 70 + GAME_ROW * len(GAMES) + 16 + self.text_height(note) + 16 + 2 * ROW
        body, _ = self.page(layer, 'SHSHD Runtime', height, back=False)
        card.text(layer, 'Choose a game', 384, body + 18, HEADING_PT, BLUE, center=True)
        y = body + 70
        for index, (key, game) in enumerate(GAMES.items()):
            command = ('choose_game', key)
            ready = (app.library_path(key) / 'library.json').is_file()
            card.rows_body(layer, y, GAME_ROW, card.row_color(index), lit=card.pressed == command)
            icon = self.icon(app, key) if ready else None
            left = PANEL_X + 30
            if icon is not None:
                layer.blit(icon, (round(left * S), round((y + (GAME_ROW - GAME_ICON) / 2) * S)))
            else:
                box = (left, y + (GAME_ROW - GAME_ICON) / 2, GAME_ICON, GAME_ICON)
                card.rect(layer, (222, 226, 234), box, 18)
                cx, cy = left + GAME_ICON / 2, box[1] + GAME_ICON / 2
                card.rect(layer, LABEL_BLUE, (cx - 18, cy - 3, 36, 6), 3)
                card.rect(layer, LABEL_BLUE, (cx - 3, cy - 18, 6, 36), 3)
            x = left + GAME_ICON + 26
            card.text(layer, game.TITLE, x, y + 30, 32, BLUE)
            card.text(layer, 'Open your library' if ready else 'Import your game files to play', x, y + 76, 22, GRAY)
            rect = pygame.Rect(PANEL_X + BORDER, y, PANEL_W - 2 * BORDER, GAME_ROW)
            self.chevron(layer, rect)
            self.buttons.append((rect, command))
            y += GAME_ROW
        y = self.text(layer, note, y + 16, points=22, center=True) + 16
        for index, (label, command) in enumerate((('Bulk Import', ('bulk',)), ('Options', ('options',)))):
            y = self.action(layer, y, label, command, index)

    def draw_bulk(self, app, layer):
        intro = ('Choose the one ZIP or RAR file that holds your game files: the SHS APK, the SHS HD and Cause of '
                 'Death IPAs, the font, and the episode folders.')
        how = ('Choose it below.' if app.file_picker else 'Drag it here, or choose it below.') + \
            ' Back leads to each game\'s own setup.'
        extra = '' if app.file_picker else 'Or put it in the import folder beside the app before starting it.'
        height = 76 + self.text_height(intro) + 18 + self.text_height(how) + (
            18 + self.text_height(extra, 22) if extra else 0) + 26 + ROW
        body, _ = self.page(layer, 'Bulk Import', height)
        self.card.text(layer, 'Bring your games', PANEL_X + 35, body + 22, HEADING_PT, BLUE)
        y = self.text(layer, intro, body + 76) + 18
        y = self.text(layer, how, y)
        if extra:
            y = self.text(layer, extra, y + 18, points=22)
        self.action(layer, y + 26, 'Choose File', ('browse', 'bulk'), 0)

    def draw_setup(self, app, layer):
        game = GAMES[app.selected_game]
        intro = f'Choose your {game.SOURCES}. It includes the base assets and bundled episodes.'
        later = ('You can add EXP files or ZIP/RAR archives afterward.' if app.file_picker else
                 'Add EXP files, ZIP/RAR archives or folders afterward: drag them here, or browse.')
        hd = ' Add your HD (iPad) IPA alongside the APK too, if you have one, for HD art.' \
            if app.selected_game == 'shs' else ''
        height = 76 + self.text_height(intro) + 18 + self.text_height(later + hd) + 26 + 2 * ROW
        body, _ = self.page(layer, game.TITLE, height)
        self.card.text(layer, 'Bring your game', PANEL_X + 35, body + 22, HEADING_PT, BLUE)
        y = self.text(layer, intro, body + 76) + 18
        y = self.text(layer, later + hd, y) + 26
        y = self.action(layer, y, 'Choose Game Files', ('browse', 'apk'), 0)
        self.action(layer, y, 'Open Library', ('browse', 'library'), 1)

    # -- the file browser (Add Episodes, Open Library, Choose Game, Bulk Import, Add APK Music, the folders) -------

    @staticmethod
    def game_card(app):
        """The open game's own menu card (HdPauseMenu / CodPauseMenu), or None before a library."""
        shell = getattr(app, 'shell', None)
        return shell.pause if app.library is not None and shell is not None else None

    def game_backdrop(self, app):
        """The open game's HD main menu without its buttons, under its own card (as On Demand's list sits), or None."""
        if self.game_card(app) is None:
            return None
        try:
            return app.shell.main.draw(buttons=False).copy()
        except Exception:                               # the menu's art unavailable: the app's backdrop instead
            return None

    def scroll_browser(self, delta):
        """Scroll the file list by `delta` points (the wheel, Page Up / Down)."""
        if self.browser_area is not None:
            self.browser_scroll = max(0., min(self.browser_max, self.browser_scroll + delta))

    browser_max = 0.

    def draw_browser(self, app, layer):
        """A tall card in the game's dress (else the app's): the folder's path (a tap types one), Up (and Default for
        a folder setting), the folder's entries as rows, Back and Use This Folder."""
        from .desktop_pause_hd import TALL
        card = self.game_card(app) or self.card
        titles = {'apk': 'Choose Game', 'music_apk': 'Add APK Music', 'episodes': 'Add Episodes',
                  'library': 'Open Library', 'bulk': 'Bulk Import', 'backups': 'Backups Folder',
                  'exports': 'Exports Folder'}
        folder_kind = app.browser_kind in ('backups', 'exports')
        top, bottom = TALL
        body = card.panel(layer, top, bottom, titles.get(app.browser_kind, 'Files'))
        inner = PANEL_X + BORDER, PANEL_W - 2 * BORDER
        pressed = app.pressed
        # The path: tapped, it takes a typed one (Enter opens it).
        typing = getattr(app, 'focus', None) == 'path'
        card.rect(layer, card.see_through(ROW_BACKGROUND), (inner[0], body, inner[1], 64))
        text = (app.path_text + '|') if typing else str(app.folder)
        font, width = card.font(22), PANEL_W - 70
        while font.size(text)[0] / S > width and len(text) > 4:
            text = '…' + text[2:] if text.startswith('…') else '…' + text[1:]
        card.text(layer, text, PANEL_X + 35, body + 20, 22, BLUE if typing else GRAY)
        self.buttons.append((pygame.Rect(inner[0], body, inner[1], 64), ('path',)))
        # Up, a hint, and Default for the folder settings.
        strip = body + 64
        card.rect(layer, card.see_through(ROW_BACKGROUND), (inner[0], strip, inner[1], 70))
        card.rect(layer, SEPARATOR, (inner[0], strip, inner[1], 1))
        up = pygame.Rect(PANEL_X + 26, strip + 13, 110, 44)
        card.cycle_button(layer, up, 'Up', pressed=pressed == ('up',))
        self.buttons.append((up, ('up',)))
        card.text(layer, 'Click a folder to open it', up.right + 20, strip + 22, 20, GRAY)
        if folder_kind:
            default = pygame.Rect(PANEL_X + PANEL_W - 26 - 130, strip + 13, 130, 44)
            card.cycle_button(layer, default, 'Default', pressed=pressed == ('default_folder',))
            self.buttons.append((default, ('default_folder',)))
        # The entries, scrolled; a new folder starts at the top.
        area = pygame.Rect(inner[0], strip + 70, inner[1], bottom - FOOT - strip - 70)
        self.browser_area = area
        if self.browser_folder != app.folder:
            self.browser_folder, self.browser_scroll = app.folder, 0.
        files = list(app.files)
        self.browser_max = max(0., len(files) * BROWSER_ROW - area.height)
        self.browser_scroll = min(self.browser_scroll, self.browser_max)
        card.rect(layer, SEPARATOR, (inner[0], area.top, inner[1], 1))
        clip = pygame.Rect(round(area.x * S), round(area.y * S), round(area.width * S), round(area.height * S))
        layer.set_clip(clip)
        card.rect(layer, card.see_through(ROW_BACKGROUND), area)
        first = int(self.browser_scroll // BROWSER_ROW)
        for index in range(first, min(len(files), first + area.height // BROWSER_ROW + 2)):
            path = files[index]
            y = area.top + index * BROWSER_ROW - self.browser_scroll
            command = ('file', path)
            card.rows_body(layer, y, BROWSER_ROW, card.row_color(index), lit=pressed == command)
            self.file_icon(layer, card, PANEL_X + 30, y + BROWSER_ROW / 2, path)
            name, font = path.name, card.font(24)
            while font.size(name)[0] / S > PANEL_W - 170 and len(name) > 4:
                name = name[:-2] + '…'
            card.text(layer, name, PANEL_X + 92, y + BROWSER_ROW / 2 - card.cap_offset(24), 24, card.LABEL_COLOR)
            row = pygame.Rect(inner[0], y, inner[1], BROWSER_ROW).clip(area)
            if path.is_dir():
                self.chevron(layer, row.move(0, (y + BROWSER_ROW / 2) - row.centery), card.LABEL_COLOR)
            if row.height > BROWSER_ROW / 2:
                self.buttons.append((row, command))
        if not files:
            message = 'No folders in this folder.' if folder_kind else 'No matching files in this folder.'
            self.text(layer, message, area.top + 40, center=True)
        layer.set_clip(None)
        if self.browser_max:
            track = area.height - 16
            thumb = max(40., track * area.height / (area.height + self.browser_max))
            y = area.top + 8 + (track - thumb) * self.browser_scroll / self.browser_max
            card.rect(layer, (150, 160, 178), (area.right - 10, y, 5, thumb), 3)
        card.rect(layer, SEPARATOR, (inner[0], bottom - FOOT, inner[1], 1))
        self.buttons.append((card.back_button(layer, bottom, lit=pressed == ('back',)), ('back',)))
        if app.browser_kind in ('episodes', 'library', 'backups', 'exports'):
            use = pygame.Rect(PANEL_X + PANEL_W - 14 - 230, bottom - 13 - 58, 230, 58)
            card.cycle_button(layer, use, 'Use This Folder', pressed=pressed == ('folder',))
            self.buttons.append((use, ('folder',)))

    @staticmethod
    def file_icon(layer, card, x, middle, path):
        """A folder (its tab and body) or a file (a page, its kind's letters under it), as shapes."""
        if path.is_dir():
            card.rect(layer, (226, 170, 64), (x, middle - 15, 20, 8), 3)
            card.rect(layer, (240, 190, 84), (x, middle - 11, 44, 28), 5)
            return
        card.rect(layer, (214, 220, 230), (x + 6, middle - 20, 32, 40), 4)
        card.rect(layer, (150, 160, 178), (x + 6, middle - 20, 32, 40), 4, 2)
        kind = path.suffix.lstrip('.').upper()[:4]
        if kind:
            label = card.font(12).render(kind, True, (90, 100, 120))
            layer.blit(label, label.get_rect(center=(round((x + 22) * S), round((middle + 6) * S))))

    def draw_options(self, app, layer):
        """The chooser's Options (AppOptions): the pause menu's pages, and a question / notice window over them.
        They take their own input (AppOptions.event), so this screen lists no buttons of its own."""
        options = self.options
        options.draw(layer)
        if options.ask is not None:
            title, text, labels, _ = options.ask
            self.card.pressed = options.pressed
            self.window(layer, title, text, labels, [('ask', index) for index in range(len(labels))])
            options.buttons, self.buttons = self.buttons, []

    # -- cards over a screen -----------------------------------------------------------------------------------

    def window(self, layer, title, text, labels, commands, *, note=None, spinner=False):
        """A centred window: `title`, `text` (and a gray `note`), then orange buttons in a row; dims what is under."""
        dim = pygame.Surface(layer.get_size(), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 120))
        layer.blit(dim, (0, 0))
        card = self.card
        height = 30 + self.text_height(text, 28) + (16 + self.text_height(note, 22) if note else 0) + (60 if spinner else 0) + 20
        foot = FOOT if labels else SHORT_FOOT
        top = max(WINDOW_TOP, (FRAME[1] - (self.header(title) + height + foot)) / 2)
        body, bottom = self.card_frame(layer, top, title, height, foot)
        y = self.text(layer, text, body + 30, points=28, color=BLUE, center=True)
        if note:
            y = self.text(layer, note, y + 16, points=22, center=True)
        if spinner:
            phase = time.monotonic() * 2.5
            for i in range(3):
                bright = .45 + .55 * max(0., 1 - abs(((phase - i * .35) % 3) - 1))
                color = tuple(round(c * bright + 255 * (1 - bright)) for c in BLUE)
                card.rect(layer, color, (384 - 40 + i * 32 - 8, y + 22, 16, 16), 8)
        y = bottom - BACK[1] - BUTTON_SIZE[1]
        if labels:
            spread = 0 if len(labels) == 1 else (PANEL_W - 2 * 40 - BUTTON_SIZE[0])
            for index, (label, command) in enumerate(zip(labels, commands)):
                x = (384 - BUTTON_SIZE[0] / 2 if len(labels) == 1
                     else PANEL_X + 40 + spread * index / (len(labels) - 1))
                box = (x, y, *BUTTON_SIZE)
                self.buttons.append((card.button(layer, box, label, lit=card.pressed == command), command))

    def draw_card(self, app, layer):
        if app.busy:
            title = {'previews': 'Preparing episodes', 'data': getattr(app, 'job_title', '')}.get(
                app.job_kind, 'Importing content')
            line = app.progress_text if app.job_kind in ('previews', 'data') and app.progress_text else \
                'Checking and copying your files...'
            self.window(layer, title, line, (), (), note=None if app.job_kind in ('previews', 'data') else IMPORT_NOTE,
                        spinner=True)
        elif app.message:
            self.window(layer, app.game_title, app.message, ('OK',), (('dismiss',),))
        elif app.update_prompt is not None:
            from .updates import UPDATE_TITLE, update_message
            commands = (('update_no',), ('update_yes',)) if app.can_quit else (('update_no',),)
            self.window(layer, UPDATE_TITLE, update_message(app.update_prompt.version, can_quit=app.can_quit),
                        ('No', 'Yes') if app.can_quit else ('OK',), commands)
