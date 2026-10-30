"""App-wide preferences, independent of either game's imported library.

Besides the update check: the preferences both games share (menu.SHARED_PREFERENCES: the switches and volumes of
Options, owner 2026-10-29), which game the app opens in (`start_in`, General's Start In) and the game an episode was
last started in (`last_game`, what Start In's Last Played opens).
"""
import json
import logging
import os
from pathlib import Path
import tempfile

from .launcher import user_data_directory

# General's Start In: the game chooser, the game an episode was last played in, or one game.
START_IN = ('games', 'auto', 'shs', 'cod')


class AppSettings:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else user_data_directory() / 'settings.json'
        self.check_for_updates = True
        self.preferences = {}           # shared game preferences (MenuState checks each value as it reads it)
        self.start_in = 'games'
        self.last_game = None
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if (not isinstance(data, dict) or data.get('version') != 1
                    or type(data.get('check_for_updates')) is not bool):
                raise ValueError('Invalid application settings')
            self.check_for_updates = data['check_for_updates']
        except FileNotFoundError:
            return
        except (OSError, ValueError) as error:
            # A damaged/unreadable preference must not silently re-enable
            # networking the player may have disabled.
            self.check_for_updates = False
            logging.warning('Could not read application settings: %s', error)
            return
        # The rest is optional (older files have only the update check); a damaged value is left at its default.
        if isinstance(data.get('preferences'), dict):
            self.preferences = {key: value for key, value in data['preferences'].items()
                                if isinstance(key, str) and isinstance(value, (bool, int, str))}
        if data.get('start_in') in START_IN:
            self.start_in = data['start_in']
        if isinstance(data.get('last_game'), str) and data['last_game'] in START_IN[2:]:
            self.last_game = data['last_game']

    def set_update_check(self, enabled):
        if type(enabled) is not bool:
            raise ValueError('Update preference must be a boolean')
        self._write(check_for_updates=enabled)

    def set_preferences(self, values):
        """The shared preferences as they now are (MenuState.persist); written only when one changed."""
        values = dict(self.preferences, **values)
        if values != self.preferences:
            self._write(preferences=values)

    def set_start_in(self, choice):
        if choice not in START_IN:
            raise ValueError('Unknown start-up choice')
        self._write(start_in=choice)

    def set_last_game(self, game):
        if game not in START_IN[2:]:
            raise ValueError('Unknown game')
        if game != self.last_game:
            self._write(last_game=game)

    def boot_game(self, has_library):
        """The game the app opens in when it is not told one (`has_library(game)`: whether it has a library), or None
        for the game chooser."""
        game = self.last_game if self.start_in == 'auto' else self.start_in
        return game if game in START_IN[2:] and has_library(game) else None

    def _write(self, **changes):
        values = dict(check_for_updates=self.check_for_updates, preferences=self.preferences,
                      start_in=self.start_in, last_game=self.last_game)
        values.update(changes)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent,
                                             prefix='.settings-', delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(dict(version=1, **values), stream)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.path)
            for key, value in values.items():
                setattr(self, key, value)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
