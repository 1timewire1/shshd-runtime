"""THIRD_PARTY_NOTICES.txt for a standalone app (owner, 2026-11-17, decision 2: both the player and the Creator).

Every Python distribution the app's own packages depend on in the build environment (their requirements followed through, with
the extras the app is built with), each with its version, its licence as its metadata states it, and the text of the licence
files it ships; then the native libraries those carry that have their own terms (SDL, Qt, libarchive). Written at build time, so
it lists what the build bundled from, not a hand-kept copy.

    python tools/notices.py OUT.txt [--creator]
"""
import argparse
from importlib import metadata
from pathlib import Path
import re

PLAYER_ROOTS = ('shshd-runtime-formats', 'shshd-runtime-engine', 'shshd-runtime-player', 'shshd-runtime-shs',
                'shshd-runtime-cod')
PLAYER_EXTRAS = {'shshd-runtime-player': ('desktop',)}
CREATOR_ROOTS = (*PLAYER_ROOTS, 'shshd-runtime-creator')
CREATOR_EXTRAS = {**PLAYER_EXTRAS, 'shshd-runtime-creator': ('desktop', 'mcp')}
OWN = re.compile(r'^shshd-runtime(-|$)')
LICENSE_FILE = re.compile(r'(^|/)(licen[cs]e|copying|notice|authors)[^/]*$', re.IGNORECASE)
# Native code inside the bundled wheels, whose terms travel with the app.
NATIVE = {
    'pygame-ce': 'pygame-ce is LGPL 2.1 and loaded as a library you may replace; its source: '
                 'https://github.com/pygame-community/pygame-ce . It bundles SDL 2 (zlib licence), SDL_image, SDL_mixer and SDL_ttf '
                 '(zlib), FreeType (FreeType licence), libpng and zlib; their licence texts are in pygame-ce\'s files below.',
    'pyside6-essentials': 'Qt 6 (LGPL 3.0), bundled in PySide6-Essentials\' wheel and dynamically linked. You may replace the Qt '
                          'libraries in this app with your own build. Qt\'s source: https://download.qt.io/official_releases/qt/ ; '
                          'PySide\'s: https://code.qt.io/cgit/pyside/pyside-setup.git/',
    'shiboken6': 'Shiboken 6 (LGPL 3.0), PySide\'s binding runtime; source as PySide\'s.',
}


def normal(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def _requirements(dist, extras):
    """The names `dist` requires, with these extras, on this platform."""
    try:
        from packaging.requirements import Requirement
    except ImportError:                     # (pip's vendored copy, in a bare environment)
        from pip._vendor.packaging.requirements import Requirement
    found = []
    for line in dist.requires or ():
        requirement = Requirement(line)
        if requirement.marker is not None:
            environments = [{'extra': extra} for extra in extras] or [{'extra': ''}]
            if not any(requirement.marker.evaluate(env) for env in environments):
                continue
        found.append((normal(requirement.name), tuple(requirement.extras)))
    return found


def closure(roots, extras=None):
    """{normalised name: Distribution} of the roots and everything they require here."""
    extras = {normal(k): v for k, v in (extras or {}).items()}
    seen, queue = {}, [(normal(root), extras.get(normal(root), ())) for root in roots]
    while queue:
        name, wanted = queue.pop()
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        if name in seen and not wanted:
            continue
        seen[name] = dist
        queue.extend(_requirements(dist, wanted))
    return seen


def license_of(dist):
    meta = dist.metadata
    expression = meta.get('License-Expression')
    if expression:
        return expression
    field = (meta.get('License') or '').strip()
    if field and len(field) < 120 and '\n' not in field:
        return field
    classifiers = [c.split(' :: ')[-1] for c in meta.get_all('Classifier') or () if c.startswith('License ::')]
    return ', '.join(classifiers) or ('see its licence text below' if field else 'not stated')


def license_texts(dist):
    out = []
    for file in dist.files or ():
        if LICENSE_FILE.search(str(file).replace('\\', '/')) and not str(file).endswith(('.py', '.pyc')):
            try:
                text = file.read_text(encoding='utf-8')
            except (OSError, UnicodeDecodeError):
                continue
            if text.strip():
                out.append((str(file).replace('\\', '/'), text.strip()))
    return out


def notices(roots, extras=None, app='SHSHD Runtime'):
    import platform
    dists = closure(roots, extras)
    parts = [f'{app}: third-party notices', '',
             f'{app} is free software under its own LICENSE. It is built with the components below, each under its own terms.',
             'Names are as their packages publish them; versions are those this build used.', '']
    for name in sorted(dists):
        if OWN.match(name):
            continue
        dist = dists[name]
        parts += ['=' * 78, f'{dist.metadata["Name"]} {dist.version}', f'Licence: {license_of(dist)}']
        home = dist.metadata.get('Home-page') or next(
            (url.split(', ', 1)[-1] for url in dist.metadata.get_all('Project-URL') or ()), '')
        if home:
            parts.append(f'Home: {home}')
        if name in NATIVE:
            parts.append(NATIVE[name])
        for path, text in license_texts(dist):
            parts += ['', f'--- {path} ---', text]
        parts.append('')
    parts += ['=' * 78, f'Python {platform.python_version()}', 'Licence: PSF-2.0',
              'The interpreter and standard library the app runs on, bundled by PyInstaller: https://docs.python.org/3/license.html',
              '', '=' * 78, 'PyInstaller bootloader',
              'Licence: GPL-2.0-or-later with the bootloader exception, which allows it in programs under any licence: '
              'https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt', '']
    return '\n'.join(parts).rstrip() + '\n'


def write(destination, creator=False):
    text = notices(CREATOR_ROOTS if creator else PLAYER_ROOTS, CREATOR_EXTRAS if creator else PLAYER_EXTRAS,
                   'SHSHD Runtime Creator' if creator else 'SHSHD Runtime')
    Path(destination).write_text(text, encoding='utf-8', newline='\n')
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--creator', action='store_true')
    args = parser.parse_args(argv)
    write(args.destination, args.creator)
    print(f'Notices written to {args.destination}')


if __name__ == '__main__':
    main()
