"""Validation of the supported Surviving High School Android package."""
from zipfile import ZipFile

NATIVE_MEMBER = 'lib/armeabi/libshs09.so'
NATIVE_SHA256 = 'b17aa4c71bc46666d414cafae6fac92bbcd755f3dcccd73975cf05f4a119665b'
BUILTIN = 'football-star'


def extract_builtin(package, asset_root, *, ios):
    from .builtin_episode import FOOTBALL_NAME, extract_football, football_source
    data = extract_football(package, asset_root, ios=ios)
    return None if data is None else (data, FOOTBALL_NAME, football_source())


def _inspect_apk(apk: ZipFile):
    from ..content import ContentError, digest, _zip_read
    names = apk.namelist()
    if len(names) != len(set(names)):
        raise ContentError('APK contains ambiguous duplicate member names')
    actual = digest(_zip_read(apk, NATIVE_MEMBER))
    if actual != NATIVE_SHA256:
        raise ContentError(f'Unsupported game APK native library ({actual}); '
                           'the currently supported profile is SHS Android 1.0.9')
    return actual

