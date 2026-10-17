"""Android SDL host. Picker callbacks hand results back to the game thread."""
from concurrent.futures import ThreadPoolExecutor
import logging
import os
from pathlib import Path
from queue import Empty, Queue
import shutil
import time


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
        self.results = Queue()
        self.copier = ThreadPoolExecutor(max_workers=1)
        self.pending = False
        self.closed = False
        self.imported = []
        self.app = Application(file_picker=self.pick, library_root=self.root / 'libraries',
                               settings_path=self.root / 'settings.json', url_opener=self.open_url,
                               can_quit=False)
        activity.bind(on_activity_result=self.on_result)

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
        if self.app.busy:
            return
        try:
            kind, value = self.results.get_nowait()
        except Empty:
            return
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
        if self.app.active == active:
            return
        self.app.handle_event(pygame.event.Event(pygame.WINDOWFOCUSGAINED if active else pygame.WINDOWFOCUSLOST))
        if not active:
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
