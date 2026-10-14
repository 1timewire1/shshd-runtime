"""App-wide preferences, independent of either game's imported library."""
import json
import logging
import os
from pathlib import Path
import tempfile

from .launcher import user_data_directory


class AppSettings:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else user_data_directory() / 'settings.json'
        self.check_for_updates = True
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if (not isinstance(data, dict) or data.get('version') != 1
                    or type(data.get('check_for_updates')) is not bool):
                raise ValueError('Invalid application settings')
            self.check_for_updates = data['check_for_updates']
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as error:
            # A damaged/unreadable preference must not silently re-enable
            # networking the player may have disabled.
            self.check_for_updates = False
            logging.warning('Could not read application settings: %s', error)

    def set_update_check(self, enabled):
        if type(enabled) is not bool:
            raise ValueError('Update preference must be a boolean')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent,
                                             prefix='.settings-', delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(dict(version=1, check_for_updates=enabled), stream)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.path)
            self.check_for_updates = enabled
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
