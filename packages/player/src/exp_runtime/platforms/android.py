"""Android SDL host. Picker callbacks hand results back to the game thread."""
from concurrent.futures import Future, ThreadPoolExecutor
import logging
import os
from pathlib import Path
from queue import Empty, Queue
import shutil
import time


# Android ships none of the faces the HD and CoD screens draw with (Arial, Arial Rounded MT Bold, Trebuchet MS).
# A player supplies them as font files (a bulk import copies them into each library's `fonts/` folder), under their
# Windows/macOS file names or the face's name. `pygame.font.match_font` family -> file stems by (bold, italic).
FONT_FILES = {
    'arial': {(False, False): ('arial', 'arialmt'), (True, False): ('arialbd', 'arial-boldmt', 'arial bold'),
              (False, True): ('ariali', 'arial-italicmt', 'arial italic'),
              (True, True): ('arialbi', 'arial-bolditalicmt', 'arial bold italic')},
    'arialroundedmtbold': {style: ('arialroundedmtbold', 'arlrdbd', 'arial rounded bold')
                           for style in ((False, False), (True, False), (False, True), (True, True))},
    'trebuchetms': {(False, False): ('trebuc', 'trebuchetms', 'trebuchet ms'),
                    (True, False): ('trebucbd', 'trebuchetms-bold', 'trebuchet ms bold'),
                    (False, True): ('trebucit', 'trebuchetms-italic', 'trebuchet ms italic'),
                    (True, True): ('trebucbi', 'trebuchetms-bolditalic', 'trebuchet ms bold italic')},
}
FONT_FILES['arialrounded'] = FONT_FILES['arialroundedmtbold']
FONT_FILES['trebuchet'] = FONT_FILES['trebuchetms']
FONT_SUFFIXES = ('.ttf', '.otf', '.ttc')
SYSTEM_FONTS = Path('/system/fonts')


def font_finder(directories):
    """pygame's `match_font` for Android: a face the player supplied (FONT_FILES, in `directories()`'s folders),
    else Android's own Roboto in the asked style, so text still draws (in another face) without the files."""
    def match_font(name, bold=False, italic=False):
        families = [part.strip().lower().replace(' ', '') for part in str(name).split(',')]
        files = {}
        for directory in directories():
            try:
                for path in directory.iterdir():
                    if path.is_file() and path.suffix.lower() in FONT_SUFFIXES:
                        files.setdefault(path.stem.lower(), str(path))
            except OSError:
                continue
        for family in families:
            for stem in FONT_FILES.get(family, {}).get((bool(bold), bool(italic)), (family,)):
                if stem in files:
                    return files[stem]
        style = 'BoldItalic' if bold and italic else 'Bold' if bold else 'Italic' if italic else 'Regular'
        for fallback in (f'Roboto-{style}.ttf', 'Roboto-Regular.ttf', 'Roboto[wdth,wght].ttf', 'NotoSans-Regular.ttf'):
            if (SYSTEM_FONTS / fallback).is_file():
                return str(SYSTEM_FONTS / fallback)
        return None
    return match_font


class Host:
    REQUEST = 4107

    def __init__(self):
        from android import activity
        from jnius import autoclass
        from ..application import Application
        self.activity_api = activity
        self.activity = autoclass('org.kivy.android.PythonActivity').mActivity
        self.bridge = autoclass('org.shshd.runtime.DocumentBridge')
        self.intent = autoclass('android.content.Intent')
        self.uri = autoclass('android.net.Uri')
        self.root = Path(str(self.activity.getFilesDir().getAbsolutePath())) / 'SHSHD Runtime'
        self.root.mkdir(parents=True, exist_ok=True)
        self.staging = self.root / 'imports'
        # Previous process may have been killed during a document copy.
        shutil.rmtree(self.staging, ignore_errors=True)
        self.staging.mkdir()
        os.environ['XDG_DATA_HOME'] = str(self.root.parent)
        import pygame
        pygame.font.match_font = font_finder(self.font_directories)
        self.results = Queue()
        self.copier = ThreadPoolExecutor(max_workers=1)
        self.pending = False
        self.closed = False
        self.backgrounded = False
        self.imported = []
        self.app = Application(file_picker=self.pick, library_root=self.root / 'libraries',
                               settings_path=self.root / 'settings.json', url_opener=self.open_url,
                               can_quit=False)
        activity.bind(on_activity_result=self.on_result)

    def font_directories(self):
        """Where supplied faces are found: the app's own `fonts/` folder, then every library's (bulk imports copy a
        player's font files into each library they create)."""
        libraries = self.root / 'libraries'
        found = [self.root / 'fonts']
        try:
            found += sorted(path / 'fonts' for path in libraries.iterdir() if (path / 'fonts').is_dir())
        except OSError:
            pass
        return found

    def pick(self, kind):
        if self.pending:
            return
        if kind == 'library':
            self.app.message = ('Android keeps imported libraries inside the app. '
                                'Choose Game to import APK/IPA files, or Bulk Import for a ZIP collection.')
            return
        self.pending = True
        try:
            self.bridge.choose(self.activity, self.REQUEST)
        except Exception as error:
            self.pending = False
            self.app.message = f'Could not open Android file picker: {error}'

    def on_result(self, request, result, data):
        if request != self.REQUEST or self.closed:
            return
        if result != -1 or data is None:
            self.results.put(('cancel', None))
            return
        # Read Java Intent while the callback owns it; copy on a worker.
        try:
            clips = data.getClipData()
            uris = ([str(clips.getItemAt(i).getUri().toString()) for i in range(clips.getItemCount())]
                    if clips is not None else [str(data.getData().toString())])
            self.results.put(('copying', None))
            self.copier.submit(self.copy_documents, uris)
        except Exception as error:
            self.results.put(('error', str(error)))

    def copy_documents(self, uris):
        paths = []
        try:
            for value in uris:
                paths.append(Path(str(self.bridge.copy(self.activity, self.uri.parse(value), str(self.staging)))))
            self.results.put(('paths', paths))
        except Exception as error:
            self.remove_staged(paths)
            self.results.put(('error', str(error)))

    @staticmethod
    def remove_staged(paths):
        for path in paths:
            shutil.rmtree(path.parent, ignore_errors=True)

    def poll(self):
        # Content import is asynchronous; never remove its source mid-job.
        if self.imported and not self.app.busy:
            self.remove_staged(self.imported)
            self.imported = []
        if self.app.busy and self.app.job_kind != 'copying':
            return
        try:
            kind, value = self.results.get_nowait()
        except Empty:
            return
        if kind == 'copying':
            # The picked files are being copied into the app (a 1 GB zip takes a while): the busy screen shows, and
            # nothing else can start meanwhile. The copy's result ends it.
            self.app.job, self.app.job_kind = Future(), 'copying'
            return
        if self.app.job_kind == 'copying':
            self.app.job = self.app.job_kind = None
        self.pending = False
        if kind == 'error':
            self.app.message = f'Could not read selected files: {value}'
        elif kind == 'paths':
            self.imported = value
            self.app._attempt(lambda: self.app.import_paths(value))

    def open_url(self, url):
        self.activity.startActivity(self.intent(self.intent.ACTION_VIEW, self.uri.parse(url)))

    def event(self, event):
        import pygame
        if event.type in (pygame.APP_WILLENTERBACKGROUND, pygame.APP_DIDENTERBACKGROUND):
            self.active(False)
            return True
        if event.type in (pygame.APP_WILLENTERFOREGROUND, pygame.APP_DIDENTERFOREGROUND):
            if event.type == pygame.APP_DIDENTERFOREGROUND:
                self.active(True)
            return True
        if event.type in (pygame.KEYDOWN, pygame.KEYUP) and event.key == pygame.K_AC_BACK:
            event = pygame.event.Event(event.type, dict(event.dict, key=pygame.K_ESCAPE))
        return self.app.handle_event(event)

    def active(self, active):
        import pygame
        was_backgrounded = getattr(self, 'backgrounded', False)
        self.backgrounded = not active
        if self.app.active != active:
            self.app.handle_event(pygame.event.Event(pygame.WINDOWFOCUSGAINED if active else pygame.WINDOWFOCUSLOST))
        if not active and not was_backgrounded:
            # Persist even an existing save, then stop one-shot sound effects.
            if self.app.game:
                self.app._attempt(lambda: self.app.state.checkpoint(self.app.game.session))
            if pygame.mixer.get_init():
                pygame.mixer.stop()

    def run(self):
        import pygame
        clock = pygame.time.Clock()
        running = True
        try:
            while running:
                elapsed = clock.tick(60)
                self.poll()
                was_active = self.app.active
                token = self.app.input_token()
                for event in pygame.event.get():
                    running = self.event(event) and not self.app.quit_requested
                    if not running or self.app.input_token() != token:
                        break
                    if (self.app.screen == 'game'
                            and self.app.game.screen_token != self.app.game._screen_token()):
                        break
                if running:
                    # A resumed frame must not advance timers by the sleep duration.
                    self.app.tick(elapsed if was_active and self.app.active else 0)
                    if self.app.active:
                        self.app.render()
                    else:
                        time.sleep(.05)
        finally:
            self.closed = True
            self.activity_api.unbind(on_activity_result=self.on_result)
            self.copier.shutdown(wait=True)
            try:
                self.app.close()
            finally:
                shutil.rmtree(self.staging, ignore_errors=True)


def main():
    logging.basicConfig(level=logging.INFO)
    Host().run()
