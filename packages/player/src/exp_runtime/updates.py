"""One optional, nonblocking public-release check per application launch.

Only metadata is fetched. The browser opens a release page after an explicit
Yes; this module never downloads, installs or executes release assets.
"""
from concurrent.futures import Future
from dataclasses import dataclass
from http.client import HTTPException
import json
import logging
import re
import ssl
import subprocess
import sys
from threading import Thread
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .app_info import PROJECT_REPOSITORY, PROJECT_URL, runtime_version


RELEASE_API = f'https://api.github.com/repos/{PROJECT_REPOSITORY}/releases/latest'
MAX_RESPONSE = 1024 * 1024
TIMEOUT = 8
REQUEST_HEADERS = {'Accept': 'application/vnd.github+json',
                   'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'EXP-Runtime-update-check'}
UPDATE_MESSAGE = 'Update available. Download here.'


@dataclass(frozen=True)
class Release:
    version: str
    url: str


def _version(text):
    # Released app versions are three numeric components. Recognize the
    # project's possible PEP 440 prerelease/dev builds without lexicographic
    # comparisons (0.10.0 > 0.9.0) or guessing about unknown tag formats.
    if not isinstance(text, str) or len(text) > 100:
        return None
    match = re.fullmatch(r'v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)'
                         r'(?:(a|b|rc)\d+)?(?:\.(dev|post)\d+)?(?:\+[a-zA-Z0-9.-]+)?', text)
    if match is None:
        return None
    return (*map(int, match.group(1, 2, 3)), int(match[4] is None and match[5] != 'dev'))


def newer_release(payload, current):
    installed = _version(current)
    if installed is None or not isinstance(payload, (str, bytes)) or len(payload) > MAX_RESPONSE:
        return None
    try:
        data = json.loads(payload)
    except (ValueError, UnicodeError):
        return None
    if (not isinstance(data, dict) or data.get('draft') is not False
            or data.get('prerelease') is not False):
        return None
    tag = data.get('tag_name')
    # The endpoint excludes prereleases; independently require a stable
    # release tag before constructing a URL on our own project's domain.
    if not isinstance(tag, str) or re.fullmatch(r'v?\d+\.\d+\.\d+', tag) is None:
        return None
    latest = _version(tag)
    if latest is None or latest <= installed:
        return None
    return Release(tag.removeprefix('v'), f'{PROJECT_URL}/releases/tag/{quote(tag, safe="")}')


def _ssl_context():
    context = ssl.create_default_context()
    if sys.platform == 'darwin':
        # Frozen macOS apps cannot depend on the build machine's Homebrew
        # CA path. Read Apple's public root certificates using its system tool.
        roots = subprocess.run(['/usr/bin/security', 'find-certificate', '-a', '-p',
                                '/System/Library/Keychains/SystemRootCertificates.keychain'],
                               check=True, capture_output=True, text=True, timeout=TIMEOUT)
        context.load_verify_locations(cadata=roots.stdout)
    return context


def fetch_release():
    """Desktop transport; a daemon worker never delays startup or shutdown."""
    result = Future()

    def work():
        payload = None
        try:
            request = Request(RELEASE_API, headers=REQUEST_HEADERS)
            with urlopen(request, timeout=TIMEOUT, context=_ssl_context()) as response:
                if response.status == 200:
                    data = response.read(MAX_RESPONSE + 1)
                    if len(data) <= MAX_RESPONSE:
                        payload = data
        except (OSError, ValueError, HTTPException, subprocess.SubprocessError) as error:
            if isinstance(error, HTTPError):
                error.close()
            logging.debug('Update check unavailable: %s', error)
        # set_running_or_notify_cancel also makes cancellation during shutdown
        # race-free, without joining a DNS/TLS operation on the UI thread.
        if result.set_running_or_notify_cancel():
            result.set_result(payload)

    Thread(target=work, name='exp-update-check', daemon=True).start()
    return result


class UpdateCheck:
    def __init__(self, fetcher=None, *, current=None):
        self.fetcher = fetcher or fetch_release
        self.current = runtime_version() if current is None else current
        self.started = False
        self.future = None
        self.available = None

    def start(self):
        if self.started or _version(self.current) is None:
            return
        self.started = True
        try:
            self.future = self.fetcher()
        except (OSError, RuntimeError) as error:
            logging.debug('Update check could not start: %s', error)

    def poll(self):
        if self.future is not None and self.future.done():
            future, self.future = self.future, None
            if not future.cancelled():
                try:
                    self.available = newer_release(future.result(), self.current)
                except Exception as error:
                    logging.debug('Update check unavailable: %s', error)
        return self.available

    def dismiss(self):
        self.available = None

    def cancel(self):
        if self.future is not None:
            self.future.cancel()
            self.future = None
        self.dismiss()
